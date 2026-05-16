from __future__ import annotations
"""LangGraph runtime orchestration — real StateGraph execution.

Wraps existing agents as LangGraph nodes with:
- Conditional branching by intent (MasterAgent routing)
- Per-node timing, error capture, fallback
- Deep merge state reducer for nested dict fields
- Thread-safe singleton with cache invalidation
- Structured JSON logging per node
- Real-time trace emission via emit_progress callback
- Automatic fallback to serial workflow on failure
- recursion_limit and configurable timeout to prevent hanging
"""

from typing import Dict,  List,  Optional

import json
import logging
import operator
import threading
import time
from collections.abc import Callable
from typing import Dict,  List,  Any, TypedDict
from typing_extensions import Annotated
from uuid import UUID, uuid4

from app.core.enums import AgentName, AgentTaskStatus, ResourceType
from app.schemas.workflow import AgentEvent, AgentTask

logger = logging.getLogger(__name__)

# ── Deep merge reducer ─────────────────────────────────────────────────────


def _merge_dict(old: dict, new: dict) -> dict:
    """Deep merge: new keys override, but existing sibling keys are preserved."""
    merged = dict(old)
    for k, v in new.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _merge_dict(merged[k], v)
        else:
            merged[k] = v
    return merged


_REPLACE_SENTINEL = "__REPLACE_RESOURCES__"


def _resource_adder(old: list, new: list) -> list:
    """Append normally, but replace entire list when sentinel is present."""
    if new == [_REPLACE_SENTINEL]:
        return []
    return old + new


def _unique_append(old: list, new: list) -> list:
    """Append items from new that are not already in old. Order-preserving."""
    seen = set(old)
    result = list(old)
    for item in new:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _merge_timings(old: dict, new: dict) -> dict:
    """Merge timing dicts — new keys add, existing keys update."""
    merged = dict(old)
    merged.update(new)
    return merged


# ── WorkflowState ───────────────────────────────────────────────────────────


class WorkflowState(TypedDict, total=False):
    """Unified state flowing through the LangGraph.

    Dict fields use deep merge; list fields use concatenation;
    scalar fields use last-write-wins.
    """

    # Input (scalars)
    user_id: str
    message: str
    conversation_id: Optional[str]
    base_agent_id: Optional[str]
    resource_types: List[str]
    difficulty: str
    subject: str
    knowledge_point: str

    # Intent routing (scalars)
    intent: str
    intent_confidence: float
    intent_method: str

    # Parsed intent details (dict — deep merge)
    parsed_intent: Annotated[Dict[str, Any], _merge_dict]

    # Resource planning (list — for parallel fan-out)
    resource_plan: List[str]

    # Quality retry tracking
    quality_retry_count: int

    # Agent outputs (dicts — deep merge)
    profile: Annotated[Dict[str, Any], _merge_dict]
    learning_path: Annotated[Dict[str, Any], _merge_dict]
    quality_report: Annotated[Dict[str, Any], _merge_dict]
    assessment: Annotated[Dict[str, Any], _merge_dict]
    tutor_answer: Annotated[Dict[str, Any], _merge_dict]
    exercise: Annotated[Dict[str, Any], _merge_dict]

    # Agent outputs (lists — concatenation)
    generated_resources: Annotated[List[Dict[str, Any]], _resource_adder]
    recommendations: Annotated[List[Dict[str, Any]], operator.add]

    # Tracking (lists — concatenation)
    errors: Annotated[List[Dict[str, Any]], operator.add]

    # Tracking (merge reducers for parallel fan-out safety)
    completed_steps: Annotated[List[str], _unique_append]
    node_timings: Annotated[Dict[str, int], _merge_timings]

    # Workflow metadata
    workflow_id: str
    tasks: Annotated[List[Dict[str, Any]], operator.add]
    events: Annotated[List[Dict[str, Any]], operator.add]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _record_error(state: WorkflowState, node: str, exc: Exception) -> WorkflowState:
    """Return a single-element list for operator.add concatenation."""
    return {"errors": [{"node": node, "error": str(exc), "time": _now_iso()}]}


def _record_timing(state: WorkflowState, node: str, duration_ms: int) -> WorkflowState:
    return {"node_timings": {node: duration_ms}}


def _record_completion(state: WorkflowState, node: str) -> WorkflowState:
    return {"completed_steps": [node]}


# ── Structured logging ─────────────────────────────────────────────────────


def _log_node_event(
    node_name: str,
    duration_ms: int,
    status: str,
    workflow_id: str = "",
    user_id: str = "",
    error: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {
        "node": node_name,
        "duration_ms": duration_ms,
        "status": status,
        "workflow_id": workflow_id,
        "user_id": user_id,
    }
    if error:
        payload["error"] = error
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_workflow_summary(result: dict, user_id: str) -> None:
    summary = {
        "event": "workflow_complete",
        "user_id": user_id,
        "workflow_id": result.get("workflow_id", ""),
        "completed_steps": result.get("completed_steps", []),
        "node_timings": result.get("node_timings", {}),
        "error_count": len(result.get("errors", [])),
    }
    logger.info(json.dumps(summary, ensure_ascii=False))


# ── Trace emission (thread-local callback) ──────────────────────────────────

_trace_ctx = threading.local()


def _emit_trace(event: dict) -> None:
    """Emit a trace event via the thread-local callback, if set."""
    fn = getattr(_trace_ctx, "emit_progress", None)
    if fn is not None:
        try:
            fn(event)
        except Exception:
            pass  # never let trace emission break the workflow


def _emit_text_delta(agent_name: str, delta: str) -> None:
    """Emit a text delta event for token-by-token streaming."""
    fn = getattr(_trace_ctx, "emit_progress", None)
    if fn is not None:
        try:
            fn({"agent_name": agent_name, "stage": "text_delta", "status": "running", "delta": delta})
        except Exception:
            pass


# ── Task/Event builders ─────────────────────────────────────────────────────


def _make_task(
    workflow_id: UUID,
    agent_name: AgentName,
    task_type: str,
    status: AgentTaskStatus,
    duration_ms: int,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> dict:
    return AgentTask(
        task_id=uuid4(),
        workflow_id=workflow_id,
        agent_name=agent_name,
        task_type=task_type,
        status=status,
        progress=100 if status == AgentTaskStatus.SUCCESS else 0,
        output_payload=result or {},
        error_message=error,
        duration_ms=duration_ms,
    ).model_dump(mode="json")


def _make_event(
    workflow_id: UUID,
    task_id: UUID,
    from_agent: Optional[AgentName],
    to_agent: AgentName,
    action: str,
    status: AgentTaskStatus,
    progress: int,
    duration_ms: int,
    input_snap: Optional[dict] = None,
    output_snap: Optional[dict] = None,
) -> dict:
    return AgentEvent(
        event_id=uuid4(),
        workflow_id=workflow_id,
        task_id=task_id,
        from_agent=from_agent,
        to_agent=to_agent,
        action=action,
        status=status,
        progress=progress,
        input_snapshot=input_snap or {},
        output_snapshot=output_snap or {},
        duration_ms=duration_ms,
        created_at=_now_iso(),
    ).model_dump(mode="json")


# ── Node implementations ───────────────────────────────────────────────────


def node_master_agent(state: WorkflowState) -> WorkflowState:
    """MasterAgent: detect intent and route."""
    from app.services.master_agent import detect_intent

    node = "master_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "MasterAgent: 正在识别意图...", "node": node, "duration_ms": 0})
    try:
        intent, confidence, method = detect_intent(state["message"])

        # Parse intent details (keywords, real need, resource preferences)
        from app.services.intent_parser import parse_intent
        parsed = parse_intent(state["message"])

        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"MasterAgent: 意图={intent.value} 需求={parsed.real_need} ({duration_ms}ms)", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "intent": intent.value,
            "intent_confidence": confidence,
            "intent_method": method,
            "parsed_intent": {
                "keywords": parsed.keywords,
                "real_need": parsed.real_need,
                "resource_preferences": parsed.resource_preferences,
                "difficulty_signal": parsed.difficulty_signal,
                "subject": parsed.subject,
                "knowledge_point": parsed.knowledge_point,
            },
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("MasterAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"MasterAgent: 失败 -- {exc}, 已降级", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "intent": "general_chat",
            "intent_confidence": 0.0,
            "intent_method": "fallback",
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_profile_agent(state: WorkflowState) -> WorkflowState:
    """ProfileAgent: extract/update student profile."""
    from app.services import agent_runtime, profile_service
    from app.schemas.profile import ProfileExtractRequest

    node = "profile_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "ProfileAgent: 正在更新学生画像...", "node": node, "duration_ms": 0})
    try:
        user_id = UUID(state["user_id"])
        conv_id = UUID(state["conversation_id"]) if state.get("conversation_id") else None
        previous = profile_service.get_profile(user_id, conversation_id=conv_id)
        request = ProfileExtractRequest(
            user_id=user_id,
            conversation=[{"role": "user", "content": state.get("message", "")}],
            base_agent_id=UUID(state["base_agent_id"]) if state.get("base_agent_id") else None,
        )
        result = agent_runtime.build_profile(request, previous)
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"ProfileAgent: 画像更新完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms, "data": {"profile": result.model_dump(mode="json")}})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "profile": result.model_dump(mode="json"),
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("ProfileAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"ProfileAgent: 失败 -- {exc}, 使用已有画像", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "profile": state.get("profile", {}),
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_path_agent(state: WorkflowState) -> WorkflowState:
    """PathAgent: generate learning path with strategy engine params."""
    from app.services import agent_runtime
    from app.services.strategy_engine import get_path_params
    from app.schemas.profile import KnowledgeDimension, StudentProfile

    node = "path_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "PathAgent: 正在规划学习路径...", "node": node, "duration_ms": 0})
    try:
        user_id = UUID(state["user_id"])
        profile = StudentProfile.model_validate(state["profile"]) if state.get("profile") else None

        # Use strategy engine to get path params based on profile
        if profile and profile.knowledge_profile.topic_dimensions:
            avg_score = sum(d.composite_score for d in profile.knowledge_profile.topic_dimensions.values()) / len(profile.knowledge_profile.topic_dimensions)
            avg_dim = KnowledgeDimension(
                mastery="high" if avg_score >= 0.7 else ("mid" if avg_score >= 0.4 else "low"),
            )
            path_params = get_path_params(avg_dim)
        else:
            path_params = get_path_params(KnowledgeDimension())

        _emit_trace({"agent_name": node, "stage": "strategy", "status": "running", "hint": f"PathAgent: 策略={path_params['path_type']}, 优先{path_params['priority']}", "node": node, "duration_ms": 0})

        result = agent_runtime.build_learning_path(
            user_id,
            state.get("message", ""),
            state.get("subject", "通用"),
            profile,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"PathAgent: 路径规划完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms, "data": {"path": result.model_dump(mode="json"), "path_params": path_params}})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "learning_path": result.model_dump(mode="json"),
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("PathAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"PathAgent: 失败 -- {exc}, 使用默认路径", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "learning_path": state.get("learning_path", {}),
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_resource_planner(state: WorkflowState) -> WorkflowState:
    """Resource planner: determine which resource types to generate in parallel."""
    from app.services.strategy_engine import get_resource_params
    from app.schemas.profile import StudentProfile

    node = "resource_planner"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "ResourcePlanner: 正在规划资源类型...", "node": node, "duration_ms": 0})

    kp = state.get("knowledge_point", state.get("message", "")[:50])
    profile = StudentProfile.model_validate(state["profile"]) if state.get("profile") else None
    requested_types = state.get("resource_types", ["document", "quiz"])
    parsed_intent = state.get("parsed_intent", {})
    intent_prefs = parsed_intent.get("resource_preferences", [])

    if profile:
        dim = profile.knowledge_profile.topic_dimensions.get(kp)
        if dim:
            res_params = get_resource_params(dim, profile.learning_preference.learning_style)
            strategy_types = res_params.get("resource_types", [])
            resource_type_strs = list(dict.fromkeys(intent_prefs + strategy_types + requested_types))
        else:
            resource_type_strs = list(dict.fromkeys(intent_prefs + requested_types)) if intent_prefs else requested_types
    else:
        resource_type_strs = list(dict.fromkeys(intent_prefs + requested_types)) if intent_prefs else requested_types

    # Filter to valid types only
    valid_types = [rt for rt in resource_type_strs if rt in ("document", "quiz", "mindmap", "code_case", "video", "animation", "reading", "flowchart")]

    duration_ms = int((time.monotonic() - t0) * 1000)
    _emit_trace({"agent_name": node, "stage": "strategy", "status": "done", "progress": 100, "hint": f"ResourcePlanner: 将并行生成 {len(valid_types)} 种资源: {valid_types}", "node": node, "duration_ms": duration_ms})
    _log_node_event(node, duration_ms, "success", wf_id, uid)
    return {
        "resource_plan": valid_types,
        **_record_completion(state, node),
        **_record_timing(state, node, duration_ms),
    }


def _make_resource_node(resource_type: str):
    """Factory: create a node function that generates a single resource type."""
    def _node(state: WorkflowState) -> WorkflowState:
        from app.services import agent_runtime
        from app.schemas.profile import StudentProfile

        node = f"gen_{resource_type}"
        wf_id = state.get("workflow_id", "")
        uid = state.get("user_id", "")
        t0 = time.monotonic()
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": f"{resource_type}: 正在生成...", "node": node, "duration_ms": 0})

        try:
            user_id = UUID(state["user_id"])
            subject = state.get("subject", "通用")
            kp = state.get("knowledge_point", state.get("message", "")[:50])
            difficulty = state.get("difficulty", "1")
            profile = StudentProfile.model_validate(state["profile"]) if state.get("profile") else None
            rt = ResourceType(resource_type)

            conv_id = state.get("conversation_id")
            conv_uuid = UUID(conv_id) if conv_id else None
            result = agent_runtime.build_learning_resource(
                user_id, subject, kp, rt, difficulty, profile,
                conversation_id=conv_uuid,
            )
            resource_dict = result.model_dump(mode="json")

            # 持久化到数据库（供推荐 agent 和资源库查询）
            try:
                from app.repositories.vertical_loop_repository import _safe_session
                from app.db.models import LearningResourceModel, ResourceVersion
                from app.core.config import get_settings
                with _safe_session() as db:
                    db.add(LearningResourceModel(
                        id=result.resource_id,
                        user_id=result.user_id,
                        conversation_id=conv_uuid,
                        title=result.title,
                        resource_type=result.resource_type.value,
                        content_summary=result.content[:300],
                        difficulty_level=result.difficulty,
                        target_profile={"resource_payload": resource_dict},
                        status=result.status.value,
                        quality_score=result.quality_score,
                    ))
                    db.flush()
                    db.add(ResourceVersion(
                        resource_id=result.resource_id,
                        version_no=1,
                        content=result.content,
                        model_name=get_settings().model_provider,
                        generation_params=result.metadata,
                        status="active",
                    ))
            except Exception:
                logger.debug("Failed to persist resource %s to DB", result.resource_id)

            duration_ms = int((time.monotonic() - t0) * 1000)
            _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"{resource_type}: 生成完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms, "data": {"resource": resource_dict}})
            _log_node_event(node, duration_ms, "success", wf_id, uid)
            return {
                "generated_resources": [resource_dict],
                **_record_completion(state, node),
                **_record_timing(state, node, duration_ms),
            }
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.exception("Resource generation failed for %s", resource_type)
            _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"{resource_type}: 失败 -- {exc}", "node": node, "duration_ms": duration_ms})
            _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
            return {
                "generated_resources": [{
                    "resource_type": resource_type,
                    "title": f"{state.get('knowledge_point', '')} - {resource_type}",
                    "content": f"{resource_type}生成失败，请稍后重试。",
                    "status": "failed",
                }],
                **_record_error(state, node, exc),
                **_record_completion(state, node),
                **_record_timing(state, node, duration_ms),
            }
    return _node


# Pre-build per-type node functions
node_gen_document = _make_resource_node("document")
node_gen_quiz = _make_resource_node("quiz")
node_gen_mindmap = _make_resource_node("mindmap")
node_gen_code_case = _make_resource_node("code_case")
node_gen_video = _make_resource_node("video")
node_gen_animation = _make_resource_node("animation")
node_gen_reading = _make_resource_node("reading")
node_gen_flowchart = _make_resource_node("flowchart")


def node_quality_agent(state: WorkflowState) -> WorkflowState:
    """QualityAgent: review generated resources with actual content."""
    node = "quality_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "QualityAgent: 正在检查资源质量...", "node": node, "duration_ms": 0})
    try:
        from app.services import model_gateway
        from app.schemas.profile import StudentProfile

        kp = state.get("knowledge_point", "")
        subject = state.get("subject", "")
        generated_resources = state.get("generated_resources", [])
        profile = StudentProfile.model_validate(state["profile"]) if state.get("profile") else None

        # Build resource summaries for quality check
        resource_summaries = []
        for r in generated_resources:
            if isinstance(r, dict) and r.get("status") != "failed":
                resource_summaries.append({
                    "type": r.get("resource_type", "unknown"),
                    "title": r.get("title", ""),
                    "content_preview": str(r.get("content", ""))[:500],
                })

        profile_summary = ""
        if profile:
            profile_summary = (
                f"学生水平：{profile.knowledge_profile.overall_level}\n"
                f"学习风格：{profile.learning_preference.learning_style}\n"
                f"薄弱点：{', '.join(profile.knowledge_profile.weak_topics[:3])}"
            )

        # Use quality_check template from prompt_templates.json
        from app.services.agent_runtime import _prompt_template
        quality_template = _prompt_template(
            "quality_check_v1",
            "检查资源质量。\n\n"
            "检查维度：\n"
            "1. 内容准确性：知识点是否正确\n"
            "2. 完整性：是否覆盖知识框架的所有部分\n"
            "3. 难度适配：是否与学生水平匹配\n"
            "4. 画像适配：是否符合学习风格和教学策略\n"
            "5. 可读性：排版、代码格式、图表清晰度\n"
            "6. 类型一致性：资源类型与实际内容是否匹配\n"
            "   - video 必须有分镜脚本，mindmap 必须有 Markdown 标题层级，code 必须有可运行代码\n"
            "   - 类型不符扣 0.2 分\n\n"
            '返回 JSON：{"quality_score": 0.0-1.0, "feedback": "总体评价", "strengths": [...], "weaknesses": [...], "suggestions": [...], "difficulty_match": true/false, "profile_match": true/false, "type_consistency": true/false}',
        )
        prompt = (
            f"{quality_template}\n\n"
            f"学科：{subject}\n知识点：{kp}\n\n"
            f"学生画像：\n{profile_summary}\n\n"
            f"生成的资源（{len(resource_summaries)}份）：\n"
            f"{json.dumps(resource_summaries, ensure_ascii=False, indent=2)}"
        )
        result = model_gateway.generate_json(prompt, required_keys=["quality_score", "feedback"])
        duration_ms = int((time.monotonic() - t0) * 1000)
        score = result.get("quality_score", 0.8)
        current_retry = state.get("quality_retry_count", 0)
        will_retry = score < 0.7 and current_retry < 2
        hint = f"QualityAgent: 质量分数 {score:.2f}" + (", 将重试生成" if will_retry else ", 检查通过")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": hint, "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        out = {
            "quality_report": {
                "status": "retrying" if will_retry else "passed",
                "quality_score": score,
                "feedback": result.get("feedback", ""),
                "issues": result.get("issues", []),
            },
            "quality_retry_count": current_retry + 1,
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
        if will_retry:
            out["generated_resources"] = [_REPLACE_SENTINEL]
            # Bump difficulty on retry so regenerated content differs
            current_diff = state.get("difficulty", "beginner")
            if current_diff == "beginner":
                out["difficulty"] = "intermediate"
            elif current_diff == "intermediate":
                out["difficulty"] = "advanced"
        return out
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("QualityAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"QualityAgent: 失败 -- {exc}, 已降级", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "quality_report": {"status": "degraded", "quality_score": 0.5, "feedback": str(exc)},
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_recommendation_agent(state: WorkflowState) -> WorkflowState:
    """RecommendationAgent: generate recommendations."""
    node = "recommendation_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "RecommendationAgent: 正在生成推荐...", "node": node, "duration_ms": 0})
    try:
        from app.repositories.vertical_loop_repository import repository
        user_id = UUID(state["user_id"])
        recs = repository.create_recommendations(user_id)
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"RecommendationAgent: 推荐完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "recommendations": [r.model_dump(mode="json") for r in recs],
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("RecommendationAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"RecommendationAgent: 失败 -- {exc}", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "recommendations": [],
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_assess_agent(state: WorkflowState) -> WorkflowState:
    """AssessAgent: multi-dimensional learning assessment."""
    node = "assess_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "AssessAgent: 正在进行学习评估...", "node": node, "duration_ms": 0})
    try:
        from app.services import assess_agent
        user_id = UUID(state["user_id"])
        result = assess_agent.assess_learning(user_id)
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"AssessAgent: 评估完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "assessment": result,
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("AssessAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"AssessAgent: 失败 -- {exc}", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "assessment": {"status": "failed", "error": str(exc)},
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_tutor_agent(state: WorkflowState) -> WorkflowState:
    """TutorAgent: answer student question."""
    node = "tutor_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "TutorAgent: 正在回答问题...", "node": node, "duration_ms": 0})
    try:
        from app.services import tutor_service
        user_id = UUID(state["user_id"])
        result = tutor_service.answer_question(
            user_id,
            state.get("message", ""),
            conversation_id=UUID(state["conversation_id"]) if state.get("conversation_id") else None,
            knowledge_point=state.get("knowledge_point"),
            base_agent_id=UUID(state["base_agent_id"]) if state.get("base_agent_id") else None,
        )
        # Stream the answer text for progressive display
        answer_text = result.get("markdown") or result.get("answer", "")
        if answer_text:
            for i in range(0, len(answer_text), 8):
                _emit_text_delta(node, answer_text[i:i+8])
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"TutorAgent: 回答完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms, "data": {"tutor_answer": result}})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "tutor_answer": result,
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("TutorAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"TutorAgent: 失败 -- {exc}, 已降级", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "tutor_answer": {"answer": "AI导师暂时无法回答，请稍后重试。", "markdown": "**暂时无法回答**，请稍后重试。"},
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_exercise_agent(state: WorkflowState) -> WorkflowState:
    """ExerciseAgent: generate practice quiz."""
    node = "exercise_agent"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "ExerciseAgent: 正在生成练习题...", "node": node, "duration_ms": 0})
    try:
        from app.services import agent_runtime
        user_id = UUID(state["user_id"])
        from app.schemas.profile import StudentProfile
        profile = StudentProfile.model_validate(state["profile"]) if state.get("profile") else None
        result = agent_runtime.build_learning_resource(
            user_id,
            state.get("subject", "通用"),
            state.get("knowledge_point", "综合练习"),
            ResourceType.QUIZ,
            state.get("difficulty", "medium"),
            profile,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"ExerciseAgent: 练习生成完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "exercise": result.model_dump(mode="json"),
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("ExerciseAgent failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"ExerciseAgent: 失败 -- {exc}", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "exercise": {"status": "failed", "error": str(exc)},
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_general_chat(state: WorkflowState) -> WorkflowState:
    """GeneralChat: friendly response for off-topic messages."""
    node = "general_chat"
    wf_id = state.get("workflow_id", "")
    uid = state.get("user_id", "")
    t0 = time.monotonic()
    _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "ChatAgent: 正在生成回复...", "node": node, "duration_ms": 0})
    _ERROR_REPLY = "AI 服务暂时不可用，请稍后再试。"
    try:
        from app.services import model_gateway
        prompt = f"你是一个友好的学习助手。请简短回复以下消息（不超过100字）：\n{state.get('message', '')}"
        full_text = ""
        try:
            for chunk in model_gateway.generate_stream(prompt):
                full_text += chunk
                _emit_text_delta(node, chunk)
        except Exception:
            full_text = model_gateway.generate_text(prompt, fallback=_ERROR_REPLY)
        if not full_text:
            full_text = _ERROR_REPLY
        duration_ms = int((time.monotonic() - t0) * 1000)
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"ChatAgent: 回复完成 ({duration_ms}ms)", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "success", wf_id, uid)
        return {
            "tutor_answer": {"answer": full_text, "markdown": full_text},
            **_record_completion(state, node),
            **_record_timing(state, node, duration_ms),
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("GeneralChat failed")
        _emit_trace({"agent_name": node, "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": "ChatAgent: 服务暂时不可用", "node": node, "duration_ms": duration_ms})
        _log_node_event(node, duration_ms, "failed", wf_id, uid, error=str(exc))
        return {
            "tutor_answer": {"answer": _ERROR_REPLY, "markdown": _ERROR_REPLY},
            **_record_error(state, node, exc),
            **_record_timing(state, node, duration_ms),
            **_record_completion(state, node),
        }


def node_aggregate(state: WorkflowState) -> WorkflowState:
    """Final aggregation node — assemble workflow tasks and events."""
    node = "aggregate"
    t0 = time.monotonic()

    workflow_id = UUID(state.get("workflow_id", str(uuid4())))
    tasks: List[dict] = []
    events: List[dict] = []
    prev_agent = None

    step_map = {
        "master_agent": (AgentName.PROFILE, "intent_routing"),
        "profile_agent": (AgentName.PROFILE, "profile_extract"),
        "path_agent": (AgentName.PATH, "path_generate"),
        "resource_planner": (AgentName.DOCUMENT, "resource_plan"),
        "gen_document": (AgentName.DOCUMENT, "resource_generate"),
        "gen_quiz": (AgentName.QUIZ, "resource_generate"),
        "gen_mindmap": (AgentName.DOCUMENT, "resource_generate"),
        "gen_code_case": (AgentName.DOCUMENT, "resource_generate"),
        "gen_video": (AgentName.DOCUMENT, "resource_generate"),
        "quality_agent": (AgentName.QUALITY, "quality_check"),
        "recommendation_agent": (AgentName.RECOMMENDATION, "recommendation_generate"),
        "assess_agent": (AgentName.PROFILE, "assessment"),
        "tutor_agent": (AgentName.TUTOR, "tutor_answer"),
        "exercise_agent": (AgentName.QUIZ, "exercise_generate"),
        "general_chat": (AgentName.TUTOR, "general_chat"),
    }

    for step in state.get("completed_steps", []):
        agent_enum, task_type = step_map.get(step, (AgentName.PROFILE, step))
        timing = state.get("node_timings", {}).get(step, 0)
        has_error = any(e.get("node") == step for e in state.get("errors", []))
        status = AgentTaskStatus.FAILED if has_error else AgentTaskStatus.SUCCESS

        task = _make_task(workflow_id, agent_enum, task_type, status, timing)
        tasks.append(task)

        event = _make_event(
            workflow_id, UUID(task["task_id"]),
            prev_agent, agent_enum, task_type,
            status, 100 if status == AgentTaskStatus.SUCCESS else 0, timing,
        )
        events.append(event)
        prev_agent = agent_enum

    duration_ms = int((time.monotonic() - t0) * 1000)
    return {
        "tasks": tasks,
        "events": events,
        **_record_completion(state, node),
        **_record_timing(state, node, duration_ms),
    }


# ── Conditional routing ────────────────────────────────────────────────────


def route_after_master(state: WorkflowState) -> str:
    """Route to the appropriate workflow branch based on detected intent."""
    intent = state.get("intent", "general_chat")
    routing = {
        "tutoring": "tutor_agent",
        "resource_generation": "profile_agent",
        "learning_path": "profile_agent",
        "assessment": "assess_agent",
        "exercise": "exercise_agent",
        "general_chat": "general_chat",
    }
    return routing.get(intent, "general_chat")


def route_after_profile(state: WorkflowState) -> str:
    """After profile, always route to path_agent for dependency-aware planning.

    Both resource_generation and learning_path intents go through path_agent,
    which then uses route_after_path to decide whether to continue to resources.
    """
    return "path_agent"


def route_after_path(state: WorkflowState) -> str:
    """After path, route to resource planner or aggregate."""
    intent = state.get("intent", "resource_generation")
    if intent == "learning_path":
        return "aggregate"
    return "resource_planner"


def route_after_planner(state: WorkflowState) -> List[str]:
    """Fan-out: route to all planned resource types in parallel."""
    plan = state.get("resource_plan", ["document", "quiz"])
    node_map = {
        "document": "gen_document",
        "quiz": "gen_quiz",
        "mindmap": "gen_mindmap",
        "code_case": "gen_code_case",
        "video": "gen_video",
        "animation": "gen_animation",
        "reading": "gen_reading",
        "flowchart": "gen_flowchart",
    }
    targets = list(dict.fromkeys(node_map.get(rt, "gen_document") for rt in plan))
    return targets if targets else ["gen_document"]


def route_after_quality(state: WorkflowState) -> str:
    """Quality retry: if score < 0.7 and retries < 2, loop back to resource planner."""
    score = state.get("quality_report", {}).get("quality_score", 1.0)
    retry_count = state.get("quality_retry_count", 0)
    if score < 0.7 and retry_count < 2:
        return "resource_planner"
    return "recommendation_agent"


# ── Graph construction ─────────────────────────────────────────────────────


def build_langgraph_app():
    """Build and compile the LangGraph StateGraph.

    Flow:
    START → master_agent → (conditional) → ... → aggregate → END

    Resource generation uses fan-out/fan-in:
    resource_planner → [gen_document, gen_quiz, gen_mindmap, ...] → quality_agent
    Quality check has retry loop: score < 0.7 → back to resource_planner (max 2 retries).
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError:
        return None

    graph = StateGraph(WorkflowState)

    # Add all nodes
    graph.add_node("master_agent", node_master_agent)
    graph.add_node("profile_agent", node_profile_agent)
    graph.add_node("path_agent", node_path_agent)
    graph.add_node("resource_planner", node_resource_planner)
    graph.add_node("gen_document", node_gen_document)
    graph.add_node("gen_quiz", node_gen_quiz)
    graph.add_node("gen_mindmap", node_gen_mindmap)
    graph.add_node("gen_code_case", node_gen_code_case)
    graph.add_node("gen_video", node_gen_video)
    graph.add_node("gen_animation", node_gen_animation)
    graph.add_node("gen_reading", node_gen_reading)
    graph.add_node("gen_flowchart", node_gen_flowchart)
    graph.add_node("quality_agent", node_quality_agent)
    graph.add_node("recommendation_agent", node_recommendation_agent)
    graph.add_node("assess_agent", node_assess_agent)
    graph.add_node("tutor_agent", node_tutor_agent)
    graph.add_node("exercise_agent", node_exercise_agent)
    graph.add_node("general_chat", node_general_chat)
    graph.add_node("aggregate", node_aggregate)

    # START → master_agent
    graph.add_edge(START, "master_agent")

    # master_agent → conditional routing by intent
    graph.add_conditional_edges(
        "master_agent",
        route_after_master,
        {
            "tutor_agent": "tutor_agent",
            "profile_agent": "profile_agent",
            "assess_agent": "assess_agent",
            "exercise_agent": "exercise_agent",
            "general_chat": "general_chat",
        },
    )

    # profile_agent → path_agent
    graph.add_conditional_edges(
        "profile_agent",
        route_after_profile,
        {"path_agent": "path_agent"},
    )

    # path_agent → resource_planner or aggregate
    graph.add_conditional_edges(
        "path_agent",
        route_after_path,
        {"resource_planner": "resource_planner", "aggregate": "aggregate"},
    )

    # resource_planner → fan-out to per-type gen nodes (parallel)
    graph.add_conditional_edges(
        "resource_planner",
        route_after_planner,
        {
            "gen_document": "gen_document",
            "gen_quiz": "gen_quiz",
            "gen_mindmap": "gen_mindmap",
            "gen_code_case": "gen_code_case",
            "gen_video": "gen_video",
            "gen_animation": "gen_animation",
            "gen_reading": "gen_reading",
            "gen_flowchart": "gen_flowchart",
        },
    )

    # All gen nodes converge on quality_agent (fan-in)
    for gen_node in ("gen_document", "gen_quiz", "gen_mindmap", "gen_code_case", "gen_video", "gen_animation", "gen_reading", "gen_flowchart"):
        graph.add_edge(gen_node, "quality_agent")

    # quality_agent → conditional: retry loop or continue to recommendation
    graph.add_conditional_edges(
        "quality_agent",
        route_after_quality,
        {
            "resource_planner": "resource_planner",
            "recommendation_agent": "recommendation_agent",
        },
    )

    # recommendation_agent → aggregate
    graph.add_edge("recommendation_agent", "aggregate")

    # Terminal nodes → aggregate
    graph.add_edge("tutor_agent", "aggregate")
    graph.add_edge("assess_agent", "aggregate")
    graph.add_edge("exercise_agent", "aggregate")
    graph.add_edge("general_chat", "aggregate")

    # aggregate → END
    graph.add_edge("aggregate", END)

    return graph.compile()


# ── Execution ──────────────────────────────────────────────────────────────

_LANGGRAPH_APP = None
_APP_LOCK = threading.Lock()


def _get_app():
    global _LANGGRAPH_APP
    if _LANGGRAPH_APP is None:
        with _APP_LOCK:
            if _LANGGRAPH_APP is None:
                _LANGGRAPH_APP = build_langgraph_app()
    return _LANGGRAPH_APP


def reset_langgraph_app():
    """Invalidate the cached LangGraph app. Thread-safe."""
    global _LANGGRAPH_APP
    with _APP_LOCK:
        _LANGGRAPH_APP = None


def run_langgraph_workflow(
    user_id: UUID,
    message: str,
    workflow_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
    base_agent_id: Optional[UUID] = None,
    resource_types: Optional[List[str]] = None,
    difficulty: str = "beginner",
    subject: str = "通用",
    knowledge_point: str = "",
    recursion_limit: int = 25,
    timeout_seconds: Optional[int] = None,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> Optional[Dict[str, Any]]:
    """Execute the LangGraph workflow. Returns None if LangGraph unavailable or fails."""
    from app.core.config import get_settings
    settings = get_settings()
    if timeout_seconds is None:
        timeout_seconds = settings.langgraph_timeout_seconds

    app = _get_app()
    if app is None:
        logger.info("LangGraph not available, returning None for fallback")
        return None

    initial_state: WorkflowState = {
        "user_id": str(user_id),
        "message": message,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "base_agent_id": str(base_agent_id) if base_agent_id else None,
        "resource_types": resource_types or ["document", "quiz"],
        "difficulty": difficulty,
        "subject": subject,
        "knowledge_point": knowledge_point,
        "workflow_id": str(workflow_id or uuid4()),
        "errors": [],
        "completed_steps": [],
        "node_timings": {},
        "tasks": [],
        "events": [],
    }

    try:
        import concurrent.futures

        def _invoke():
            _trace_ctx.emit_progress = emit_progress
            try:
                return app.invoke(initial_state, {"recursion_limit": recursion_limit})
            finally:
                if hasattr(_trace_ctx, "emit_progress"):
                    del _trace_ctx.emit_progress

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.langgraph_max_workers,
        ) as pool:
            future = pool.submit(_invoke)
            result = future.result(timeout=timeout_seconds)

        result_dict = {
            "intent": result.get("intent"),
            "intent_confidence": result.get("intent_confidence"),
            "intent_method": result.get("intent_method"),
            "profile": result.get("profile"),
            "learning_path": result.get("learning_path"),
            "generated_resources": result.get("generated_resources", []),
            "quality_report": result.get("quality_report"),
            "quality_retry_count": result.get("quality_retry_count", 0),
            "recommendations": result.get("recommendations", []),
            "assessment": result.get("assessment"),
            "tutor_answer": result.get("tutor_answer"),
            "exercise": result.get("exercise"),
            "errors": result.get("errors", []),
            "completed_steps": result.get("completed_steps", []),
            "node_timings": result.get("node_timings", {}),
            "workflow_id": result.get("workflow_id"),
            "tasks": result.get("tasks", []),
            "events": result.get("events", []),
        }

        _log_workflow_summary(result_dict, str(user_id))
        return result_dict

    except concurrent.futures.TimeoutError:
        logger.error("LangGraph workflow timed out after %ds", timeout_seconds)
        return None
    except Exception:
        logger.exception("LangGraph workflow failed")
        return None
