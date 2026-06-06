from __future__ import annotations

from typing import Optional

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

from app.schemas.learning import LearningStartRequest, LearningStartResponse
from app.schemas.learning_path import LearningPath, LearningPathGenerateRequest, LearningPathNode
from app.schemas.profile import KnowledgeDimension, ProfileExtractRequest, StudentProfile
from app.schemas.recommendation import Recommendation
from app.schemas.resource import LearningResource, ResourceGenerateRequest, ResourceGenerateResponse
from app.core.enums import AgentName
from app.core.errors import ErrorCode, ServiceError
from app.schemas.workflow import AgentWorkflow
from app.services import (
    conversation_service,
    learning_path_service,
    model_gateway,
    profile_service,
    recommendation_service,
    resource_service,
    workflow_service,
)
from app.services.model_gateway import ModelOverride, model_override_context


def _infer_subject_and_knowledge(message: str) -> tuple[str, str]:
    """Infer subject and knowledge point from user message using intent parser."""
    from app.services.intent_parser import parse_intent
    parsed = parse_intent(message)
    subject = parsed.subject or "通用"
    knowledge_point = parsed.knowledge_point
    return subject, knowledge_point


# Re-export from profile_eval_service for backward compatibility


def start_learning(
    request: LearningStartRequest,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> LearningStartResponse:
    override = ModelOverride(
        provider=request.model_provider,
        api_base=request.model_api_base,
        api_key=request.model_api_key,
        model_name=request.model_name,
        temperature=request.model_temperature,
    )
    with model_override_context(override):
        return _start_learning_impl(request, emit_progress)


def start_learning_langgraph(
    request: LearningStartRequest,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> LearningStartResponse:
    """LangGraph-first entry point with intent-based routing fallback."""
    from app.workflows.langgraph_runtime import run_langgraph_workflow

    override = ModelOverride(
        provider=request.model_provider,
        api_base=request.model_api_base,
        api_key=request.model_api_key,
        model_name=request.model_name,
        temperature=request.model_temperature,
    )
    with model_override_context(override):
        # Try LangGraph first
        result = run_langgraph_workflow(
            user_id=request.user_id,
            message=request.message,
            conversation_id=request.conversation_id,
            base_agent_id=request.base_agent_id,
            resource_types=[rt.value for rt in request.resource_types],
            difficulty=request.difficulty,
            subject=request.subject or "通用",
            knowledge_point=request.knowledge_point or "",
            emit_progress=emit_progress,
        )

        if result is not None:
            return _convert_langgraph_result(request, result, emit_progress)

        # LangGraph unavailable — intent-based fallback
        return _start_intent_based(request, emit_progress)


def _convert_langgraph_result(
    request: LearningStartRequest,
    result: dict,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> LearningStartResponse:
    """Convert LangGraph workflow result to LearningStartResponse."""
    profile_data = result.get("profile")
    profile = StudentProfile.model_validate(profile_data) if profile_data else profile_service.get_profile(request.user_id, conversation_id=request.conversation_id)
    if profile is None:
        profile = profile_service.get_or_create_profile(request.user_id, conversation_id=request.conversation_id)

    path_data = result.get("learning_path")
    path = LearningPath.model_validate(path_data) if path_data else _default_path(request, request.knowledge_point or "学习内容")

    resources = [LearningResource.model_validate(r) for r in result.get("generated_resources", []) if r.get("status") != "failed"]

    recs_data = result.get("recommendations", [])
    recs = [Recommendation.model_validate(r) for r in recs_data] if recs_data else recommendation_service.get_recommendations(request.user_id)

    wf_id = UUID(result["workflow_id"]) if result.get("workflow_id") else uuid4()
    workflow = workflow_service.get_workflow(wf_id)
    if workflow is None:
        workflow = _build_fallback_workflow(wf_id, result, request.user_id)

    knowledge_point = request.knowledge_point or ""
    session = conversation_service.append_message(
        request.user_id, role="user", content=request.message,
        conversation_id=request.conversation_id, intent="learning_start",
        title=knowledge_point or request.subject or "学习会话",
        profile_id=profile.profile_id,
    )

    intent = result.get("intent", "general_chat")
    if intent == "tutoring":
        tutor = result.get("tutor_answer", {})
        reply = tutor.get("markdown") or tutor.get("answer", "回答完成。")
    elif intent == "general_chat":
        tutor = result.get("tutor_answer", {})
        reply = tutor.get("answer", "你好！")
    else:
        reply = (
            f"已围绕「{knowledge_point}」更新画像，生成 {len(path.nodes)} 步学习路径，"
            f"{len(resources)} 份学习资源。"
        )

    # Build intent_result for frontend rendering on reload
    ir_result: dict = {}
    if intent == "tutoring":
        ta = result.get("tutor_answer", {})
        ir_result = {"answer": ta.get("answer", ""), "markdown": ta.get("markdown", reply), "knowledge_point": knowledge_point}
    elif intent == "resource_generation":
        ir_result = {"resources": [r.model_dump(mode="json") for r in resources]}
    elif intent == "general_chat":
        ir_result = {"reply": reply}
    else:
        ir_result = {
            "title": path.title, "nodes": [{"knowledge_point": n.knowledge_point, "status": n.status, "order": n.order} for n in path.nodes],
            "resources": [r.model_dump(mode="json") for r in resources],
        }

    session = conversation_service.append_message(
        request.user_id, role="assistant", content=reply,
        conversation_id=session.conversation_id, intent="learning_result",
        profile_id=profile.profile_id,
        metadata={
            "workflow_id": str(wf_id),
            "resource_ids": [str(r.resource_id) for r in resources],
            "intent_result": {"intent": intent, "confidence": 1.0, "method": "langgraph", "result": ir_result},
        },
    )

    return LearningStartResponse(
        task_id=uuid4(), workflow_id=wf_id, conversation_id=session.conversation_id,
        status="success", stream_url=f"/api/v1/agent-workflows/{wf_id}/stream",
        profile=profile, path=path, resources=resources, workflow=workflow,
        recommendations=recs, messages=session.messages,
    )


def _start_intent_based(
    request: LearningStartRequest,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> LearningStartResponse:
    """Intent-based sequential pipeline — runs only the agents needed for the detected intent."""
    from app.services.master_agent import detect_intent, Intent

    def emit(payload: dict) -> None:
        if emit_progress is not None:
            emit_progress(payload)

    emit({"agent_name": "master_agent", "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "MasterAgent: 正在识别意图...", "node": "master_agent", "duration_ms": 0})
    try:
        intent, confidence, method = detect_intent(request.message)

        # Parse intent details
        from app.services.intent_parser import parse_intent
        parsed = parse_intent(request.message)

        emit({"agent_name": "master_agent", "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"MasterAgent: 意图={intent.value} 需求={parsed.real_need} ({confidence:.0%})", "node": "master_agent", "duration_ms": 0})
    except Exception:
        logger.exception("Intent detection failed")
        intent = Intent.GENERAL_CHAT
        parsed = None
        emit({"agent_name": "master_agent", "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": "MasterAgent: 意图识别失败，已降级为通用对话", "node": "master_agent", "duration_ms": 0})

    wf_id = uuid4()

    # Enrich request with parsed intent if subject/knowledge_point missing
    if parsed and not request.subject and parsed.subject:
        request.subject = parsed.subject
    if parsed and not request.knowledge_point and parsed.knowledge_point:
        request.knowledge_point = parsed.knowledge_point

    if "resource_types" in request.model_fields_set:
        intent = Intent.RESOURCE_GENERATION

    if intent == Intent.TUTORING:
        return _run_tutoring(request, wf_id, emit)
    elif intent == Intent.ASSESSMENT:
        return _run_assessment(request, wf_id, emit)
    elif intent == Intent.EXERCISE:
        return _run_exercise(request, wf_id, emit)
    elif intent == Intent.RESOURCE_GENERATION:
        return _run_resource_generation(request, wf_id, emit)
    elif intent == Intent.GENERAL_CHAT:
        return _run_general_chat(request, wf_id, emit)
    else:
        return _run_full_pipeline(request, wf_id, emit)


def _default_path(request: LearningStartRequest, kp: str) -> LearningPath:
    return LearningPath(
        path_id=uuid4(), user_id=request.user_id,
        title=f"{kp} 学习路径", goal=request.message,
        nodes=[LearningPathNode(
            node_id=uuid4(), order=1, knowledge_point=kp,
            estimated_minutes=30, recommended_resource_types=["document"],
            reason="默认路径", status="available",
        )],
        status="degraded",
    )


_STEP_AGENT_MAP = {
    "master_agent": AgentName.PROFILE,
    "profile_agent": AgentName.PROFILE,
    "path_agent": AgentName.PATH,
    "resource_agent": AgentName.DOCUMENT,
    "quality_agent": AgentName.QUALITY,
    "recommendation_agent": AgentName.RECOMMENDATION,
    "assess_agent": AgentName.PROFILE,
    "tutor_agent": AgentName.TUTOR,
    "exercise_agent": AgentName.QUIZ,
    "general_chat": AgentName.TUTOR,
    "aggregate": AgentName.PROFILE,
}


def _build_fallback_workflow(wf_id: UUID, result: dict, user_id: Optional[UUID] = None) -> AgentWorkflow:
    from app.core.enums import AgentTaskStatus
    from app.schemas.workflow import AgentEvent, AgentTask
    tasks, events = [], []
    prev_agent = None
    for step in result.get("completed_steps", []):
        agent = _STEP_AGENT_MAP.get(step, AgentName.PROFILE)
        timing = result.get("node_timings", {}).get(step, 0)
        has_error = any(e.get("node") == step for e in result.get("errors", []))
        status = AgentTaskStatus.FAILED if has_error else AgentTaskStatus.SUCCESS
        task = AgentTask(
            task_id=uuid4(), workflow_id=wf_id,
            agent_name=agent, task_type=step,
            status=status, progress=100 if status == AgentTaskStatus.SUCCESS else 0,
            output_payload={}, duration_ms=timing,
        )
        tasks.append(task)
        events.append(AgentEvent(
            event_id=uuid4(), workflow_id=wf_id, task_id=task.task_id,
            from_agent=prev_agent, to_agent=agent,
            action=step, status=status, progress=100 if status == AgentTaskStatus.SUCCESS else 0,
            input_snapshot={}, output_snapshot={}, duration_ms=timing, created_at="",
        ))
        prev_agent = agent
    return AgentWorkflow(
        workflow_id=wf_id,
        user_id=user_id or UUID("00000000-0000-0000-0000-000000000000"),
        status=AgentTaskStatus.SUCCESS,
        tasks=tasks, events=events,
    )


def _run_tutoring(request: LearningStartRequest, wf_id: UUID, emit) -> LearningStartResponse:
    from app.services import adaptive_service, tutor_service

    session = conversation_service.append_message(
        request.user_id, role="user", content=request.message,
        conversation_id=request.conversation_id, intent="tutoring",
        title=request.knowledge_point or "辅导问答",
    )

    emit({"agent_name": "tutor_agent", "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "TutorAgent: 正在回答问题...", "node": "tutor_agent", "duration_ms": 0})
    result = {}
    try:
        # Use real streaming
        for chunk in tutor_service.answer_question_streaming(
            request.user_id, request.message,
            knowledge_point=request.knowledge_point,
            base_agent_id=request.base_agent_id,
            conversation_id=request.conversation_id,
        ):
            if isinstance(chunk, str):
                emit({"agent_name": "tutor_agent", "stage": "text_delta", "status": "running", "delta": chunk})
            elif isinstance(chunk, dict):
                result = chunk
        answer = result.get("markdown") or result.get("answer", "")
        emit({"agent_name": "tutor_agent", "stage": "langgraph_node", "status": "done", "progress": 100, "hint": "TutorAgent: 回答完成", "node": "tutor_agent", "duration_ms": 0, "data": {"tutor_answer": result}})
    except Exception as exc:
        logger.exception("TutorAgent failed")
        answer = "抱歉，回答出现问题，请重试。"
        emit({"agent_name": "tutor_agent", "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"TutorAgent: {exc}", "node": "tutor_agent", "duration_ms": 0})

    profile = profile_service.get_or_create_profile(request.user_id, conversation_id=request.conversation_id)

    # Use shared adaptive_service for post-learning update
    kp = request.knowledge_point or ""
    if kp:
        try:
            update = adaptive_service.post_learning_update(
                user_id=request.user_id,
                knowledge_point=kp,
                conversation_context=request.message + "\n" + answer,
                conversation_id=request.conversation_id,
            )
            if update.get("updated_profile"):
                profile = update["updated_profile"]
        except Exception:
            logger.warning("adaptive_service.post_learning_update failed", exc_info=True)

    path = _default_path(request, request.knowledge_point or "")
    session = conversation_service.append_message(
        request.user_id, role="assistant", content=answer,
        conversation_id=session.conversation_id, intent="tutoring_result",
        profile_id=profile.profile_id,
        metadata={
            "intent_result": {
                "intent": "tutoring", "confidence": 1.0, "method": "learning_service",
                "result": {
                    "markdown": answer, "answer": result.get("answer", answer),
                    "rag_references": result.get("rag_references", []),
                    "knowledge_point": request.knowledge_point or "",
                    "videos": result.get("videos", []),
                    "resource_recommendation": result.get("resource_recommendation"),
                },
            },
        },
    )

    workflow = workflow_service.get_workflow(wf_id)
    if workflow is None:
        workflow = _build_fallback_workflow(wf_id, {"completed_steps": ["tutor_agent"]}, request.user_id)

    return LearningStartResponse(
        task_id=uuid4(), workflow_id=wf_id, conversation_id=session.conversation_id,
        status="success", stream_url=f"/api/v1/agent-workflows/{wf_id}/stream",
        profile=profile, path=path, resources=[], workflow=workflow,
        recommendations=[], messages=session.messages,
    )


def _run_assessment(request: LearningStartRequest, wf_id: UUID, emit) -> LearningStartResponse:
    from app.services import assess_agent

    session = conversation_service.append_message(
        request.user_id, role="user", content=request.message,
        conversation_id=request.conversation_id, intent="assessment", title="学习评估",
    )

    emit({"agent_name": "assess_agent", "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "AssessAgent: 正在进行学习评估...", "node": "assess_agent", "duration_ms": 0})
    try:
        assessment = assess_agent.assess_learning(request.user_id)
        emit({"agent_name": "assess_agent", "stage": "langgraph_node", "status": "done", "progress": 100, "hint": "AssessAgent: 评估完成", "node": "assess_agent", "duration_ms": 0})
    except Exception as exc:
        assessment = {"status": "failed", "error": str(exc)}
        emit({"agent_name": "assess_agent", "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"AssessAgent: {exc}", "node": "assess_agent", "duration_ms": 0})

    profile = profile_service.get_or_create_profile(request.user_id)
    path = _default_path(request, request.knowledge_point or "学习评估")
    session = conversation_service.append_message(
        request.user_id, role="assistant", content="学习评估已完成，请查看右侧评估报告。",
        conversation_id=session.conversation_id, intent="assessment_result",
        profile_id=profile.profile_id,
        metadata={
            "intent_result": {
                "intent": "assessment", "confidence": 1.0, "method": "learning_service",
                "result": {
                    "mastery_score": assessment.get("mastery_score") if isinstance(assessment, dict) else None,
                    "weak_points": assessment.get("weak_points", []) if isinstance(assessment, dict) else [],
                    "next_suggestions": assessment.get("next_suggestions", []) if isinstance(assessment, dict) else [],
                    "summary": assessment.get("summary", "") if isinstance(assessment, dict) else "",
                },
            },
        },
    )

    workflow = workflow_service.get_workflow(wf_id)
    if workflow is None:
        workflow = _build_fallback_workflow(wf_id, {"completed_steps": ["assess_agent"]}, request.user_id)

    return LearningStartResponse(
        task_id=uuid4(), workflow_id=wf_id, conversation_id=session.conversation_id,
        status="success", stream_url=f"/api/v1/agent-workflows/{wf_id}/stream",
        profile=profile, path=path, resources=[], workflow=workflow,
        recommendations=[], messages=session.messages,
    )


def _run_exercise(request: LearningStartRequest, wf_id: UUID, emit) -> LearningStartResponse:
    from app.services import agent_runtime
    from app.core.enums import ResourceType

    session = conversation_service.append_message(
        request.user_id, role="user", content=request.message,
        conversation_id=request.conversation_id, intent="exercise",
        title=request.knowledge_point or "练习生成",
    )

    profile = profile_service.get_or_create_profile(request.user_id)
    kp = request.knowledge_point or "综合练习"

    emit({"agent_name": "exercise_agent", "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "ExerciseAgent: 正在生成练习题...", "node": "exercise_agent", "duration_ms": 0})
    try:
        resource = agent_runtime.build_learning_resource(
            request.user_id, request.subject or "通用", kp,
            ResourceType.QUIZ, request.difficulty, profile,
        )
        resources = [resource]
        emit({"agent_name": "exercise_agent", "stage": "langgraph_node", "status": "done", "progress": 100, "hint": "ExerciseAgent: 练习生成完成", "node": "exercise_agent", "duration_ms": 0, "data": {"resource": resource.model_dump(mode="json")}})
    except Exception as exc:
        resources = []
        emit({"agent_name": "exercise_agent", "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"ExerciseAgent: {exc}", "node": "exercise_agent", "duration_ms": 0})

    path = _default_path(request, kp)
    answer_msg = f"已生成「{kp}」练习题。" if resources else f"「{kp}」练习题生成失败，请稍后重试。"
    session = conversation_service.append_message(
        request.user_id, role="assistant", content=answer_msg,
        conversation_id=session.conversation_id, intent="exercise_result",
        profile_id=profile.profile_id,
        metadata={
            "intent_result": {
                "intent": "exercise", "confidence": 1.0, "method": "learning_service",
                "result": {
                    "title": resources[0].title if resources else "练习题",
                    "content": resources[0].content if resources else "",
                    "knowledge_point": kp,
                },
            },
        } if resources else None,
    )

    workflow = workflow_service.get_workflow(wf_id)
    if workflow is None:
        workflow = _build_fallback_workflow(wf_id, {"completed_steps": ["exercise_agent"]}, request.user_id)

    return LearningStartResponse(
        task_id=uuid4(), workflow_id=wf_id, conversation_id=session.conversation_id,
        status="success", stream_url=f"/api/v1/agent-workflows/{wf_id}/stream",
        profile=profile, path=path, resources=resources, workflow=workflow,
        recommendations=[], messages=session.messages,
    )


def _run_resource_generation(request: LearningStartRequest, wf_id: UUID, emit) -> LearningStartResponse:
    """Intelligent resource generation: profile → strategy → generate."""
    from app.services import resource_service, adaptive_service
    from app.schemas.profile import ProfileExtractRequest
    from app.schemas.resource import ResourceGenerateRequest

    kp = request.knowledge_point or request.message[:30]
    session = conversation_service.append_message(
        request.user_id, role="user", content=request.message,
        conversation_id=request.conversation_id, intent="resource_generation",
        title=kp or "资源生成",
    )

    try:
        profile = profile_service.extract_profile(
            ProfileExtractRequest(
                user_id=request.user_id,
                conversation=conversation_service.as_profile_conversation(session),
                base_agent_id=request.base_agent_id,
            ),
            conversation_id=session.conversation_id,
        )
    except Exception:
        logger.warning("Profile extraction during resource generation failed", exc_info=True)
        profile = profile_service.get_or_create_profile(request.user_id)
    path = _default_path(request, kp)

    # 1. Get strategy-recommended params from profile + strategy engine
    emit({"agent_name": "profile_agent", "stage": "langgraph_node", "status": "running", "progress": 10, "hint": "正在分析画像和策略...", "node": "profile_agent", "duration_ms": 0})
    update = adaptive_service.post_learning_update(
        user_id=request.user_id, knowledge_point=kp,
        conversation_context=request.message, conversation_id=session.conversation_id,
    )
    strategy_types = update.get("recommended_types", [])
    resource_params = update.get("resource_params", {})
    diff_map = {"easy": "easy", "medium": "medium", "hard": "hard"}
    difficulty = diff_map.get(resource_params.get("difficulty", request.difficulty), request.difficulty)
    emit({"agent_name": "profile_agent", "stage": "langgraph_node", "status": "done", "progress": 25, "hint": f"策略分析完成，推荐类型: {strategy_types}", "node": "profile_agent", "duration_ms": 0})

    # 2. Merge request resource_types with strategy recommendations
    merged_types = list(request.resource_types) if request.resource_types else []
    from app.core.enums import ResourceType
    existing = {t.value if hasattr(t, "value") else str(t) for t in merged_types}
    if "resource_types" not in request.model_fields_set:
        for rt in strategy_types:
            if rt not in existing:
                try:
                    merged_types.append(ResourceType(rt))
                except ValueError:
                    pass
    if not merged_types:
        merged_types = [ResourceType.DOCUMENT, ResourceType.QUIZ]

    # 3. Generate resources
    emit({"agent_name": "resource_agent", "stage": "langgraph_node", "status": "running", "progress": 30, "hint": f"ResourceAgent: 正在生成 {len(merged_types)} 类资源...", "node": "resource_agent", "duration_ms": 0})
    generation_result = None
    try:
        result = resource_service.generate_resources(
            ResourceGenerateRequest(
                user_id=request.user_id,
                subject=request.subject or "通用",
                knowledge_point=kp,
                resource_types=merged_types,
                difficulty=difficulty,
                base_agent_id=request.base_agent_id,
            ),
            emit_progress=emit,
        )
        generation_result = result
        resources = result.resources
        emit({"agent_name": "resource_agent", "stage": "langgraph_node", "status": "done", "progress": 100, "hint": f"ResourceAgent: 已生成 {len(resources)} 份资源", "node": "resource_agent", "duration_ms": 0})
    except Exception as exc:
        logger.exception("ResourceAgent failed")
        resources = []
        emit({"agent_name": "resource_agent", "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": f"ResourceAgent: {exc}", "node": "resource_agent", "duration_ms": 0})

    answer_msg = f"已围绕「{kp}」生成 {len(resources)} 份学习资源。" if resources else f"「{kp}」资源生成失败，请稍后重试。"
    session = conversation_service.append_message(
        request.user_id, role="assistant", content=answer_msg,
        conversation_id=session.conversation_id, intent="resource_generation",
        profile_id=profile.profile_id,
        metadata={
            "intent_result": {
                "intent": "resource_generation", "confidence": 1.0, "method": "learning_service",
                "result": {
                    "resources": [r.model_dump(mode="json") for r in resources],
                    "status": "success" if resources else "failed",
                },
            },
        },
    )

    response_wf_id = generation_result.workflow_id if generation_result else wf_id
    response_task_id = generation_result.task_id if generation_result else uuid4()
    workflow = workflow_service.get_workflow(response_wf_id)
    if workflow is None:
        workflow = _build_fallback_workflow(response_wf_id, {"completed_steps": ["resource_agent"]}, request.user_id)

    return LearningStartResponse(
        task_id=response_task_id, workflow_id=response_wf_id, conversation_id=session.conversation_id,
        status="success" if resources else "degraded",
        stream_url=f"/api/v1/agent-workflows/{response_wf_id}/stream",
        profile=profile, path=path, resources=resources, workflow=workflow,
        recommendations=recommendation_service.get_recommendations(request.user_id), messages=session.messages,
    )


def _run_general_chat(request: LearningStartRequest, wf_id: UUID, emit) -> LearningStartResponse:
    session = conversation_service.append_message(
        request.user_id, role="user", content=request.message,
        conversation_id=request.conversation_id, intent="general_chat", title="自由对话",
    )

    _ERROR_REPLY = "AI 服务暂时不可用，请稍后再试。"
    emit({"agent_name": "general_chat", "stage": "langgraph_node", "status": "running", "progress": 0, "hint": "ChatAgent: 正在生成回复...", "node": "general_chat", "duration_ms": 0})
    try:
        from app.services.prompt_utils import build_prompt as _bp
        prompt = _bp("general_chat_v1", f"你是一个友好的学习助手。请简短回复以下消息（不超过100字）：\n{request.message}", {"message": request.message})
        full_text = ""
        try:
            for chunk in model_gateway.generate_stream(prompt):
                full_text += chunk
                emit({"agent_name": "general_chat", "stage": "text_delta", "status": "running", "delta": chunk})
        except Exception:
            full_text = model_gateway.generate_text(prompt, fallback=_ERROR_REPLY)
        if not full_text:
            full_text = _ERROR_REPLY
        emit({"agent_name": "general_chat", "stage": "langgraph_node", "status": "done", "progress": 100, "hint": "ChatAgent: 回复完成", "node": "general_chat", "duration_ms": 0})
    except Exception as exc:
        logger.exception("GeneralChat failed")
        full_text = _ERROR_REPLY
        emit({"agent_name": "general_chat", "stage": "langgraph_node", "status": "failed", "progress": 0, "hint": "ChatAgent: 服务暂时不可用", "node": "general_chat", "duration_ms": 0})

    profile = profile_service.get_or_create_profile(request.user_id)
    path = _default_path(request, request.knowledge_point or "自由对话")
    session = conversation_service.append_message(
        request.user_id, role="assistant", content=full_text,
        conversation_id=session.conversation_id, intent="general_chat_result",
        profile_id=profile.profile_id,
        metadata={
            "intent_result": {
                "intent": "general_chat", "confidence": 1.0, "method": "learning_service",
                "result": {"reply": full_text},
            },
        },
    )

    workflow = workflow_service.get_workflow(wf_id)
    if workflow is None:
        workflow = _build_fallback_workflow(wf_id, {"completed_steps": ["general_chat"]}, request.user_id)

    return LearningStartResponse(
        task_id=uuid4(), workflow_id=wf_id, conversation_id=session.conversation_id,
        status="success", stream_url=f"/api/v1/agent-workflows/{wf_id}/stream",
        profile=profile, path=path, resources=[], workflow=workflow,
        recommendations=[], messages=session.messages,
    )


def _run_full_pipeline(request: LearningStartRequest, wf_id: UUID, emit) -> LearningStartResponse:
    return _start_learning_impl(request, emit, wf_id=wf_id)


def _start_learning_impl(
    request: LearningStartRequest,
    emit_progress: Optional[Callable[[dict], None]] = None,
    wf_id: Optional[UUID] = None,
) -> LearningStartResponse:
    def emit(payload: dict) -> None:
        if emit_progress is not None:
            emit_progress(payload)

    # Analyze images if provided
    image_analysis = ""
    if request.images:
        emit(
            {
                "agent_name": "vision_agent",
                "stage": "image_analysis",
                "status": "running",
                "progress": 5,
                "hint": "正在分析上传的图片...",
            }
        )
        try:
            from app.services.prompt_utils import build_prompt as _bp2
            image_analysis = model_gateway.analyze_images(
                _bp2("vision_analyze_v1", "请分析这张图片中的内容，提取与学习相关的知识点、概念、公式或代码。用中文回答。", {}),
                request.images,
            )
            emit(
                {
                    "agent_name": "vision_agent",
                    "stage": "image_analysis",
                    "status": "done",
                    "progress": 8,
                    "hint": f"图片分析完成：{image_analysis[:100]}...",
                }
            )
        except Exception as exc:
            emit(
                {
                    "agent_name": "vision_agent",
                    "stage": "image_analysis",
                    "status": "failed",
                    "progress": 8,
                    "hint": f"图片分析失败：{exc}",
                }
            )

    # Merge image analysis into message
    effective_message = request.message
    if image_analysis:
        effective_message = f"{request.message}\n\n[图片分析结果]\n{image_analysis}"

    initial_profile = profile_service.get_profile(request.user_id, conversation_id=request.conversation_id)
    emit(
        {
            "agent_name": "system",
            "stage": "thinking",
            "status": "running",
            "progress": 3,
            "hint": "正在理解学习目标和学生上下文...",
        }
    )

    session = conversation_service.append_message(
        request.user_id,
        role="user",
        content=effective_message,
        conversation_id=request.conversation_id,
        intent="learning_start",
        title=request.knowledge_point or request.subject or "学习画像会话",
        profile_id=initial_profile.profile_id if initial_profile else None,
    )

    emit(
        {
            "agent_name": "profile_agent",
            "stage": "profile_extract",
            "status": "running",
            "progress": 12,
            "hint": "画像构建 Agent 正在抽取专业、年级、基础、目标、薄弱点...",
        }
    )
    try:
        profile = profile_service.extract_profile(
            ProfileExtractRequest(
                user_id=request.user_id,
                conversation=conversation_service.as_profile_conversation(session),
                base_agent_id=request.base_agent_id,
            ),
            conversation_id=request.conversation_id,
        )
    except Exception as exc:
        profile = initial_profile or profile_service.get_profile(request.user_id, conversation_id=request.conversation_id)
        emit(
            {
                "agent_name": "profile_agent",
                "stage": "profile_extract",
                "status": "failed",
                "progress": 20,
                "hint": f"画像构建失败，使用已有画像: {exc}",
            }
        )
    else:
        emit(
            {
                "agent_name": "profile_agent",
                "stage": "profile_extract",
                "status": "done",
                "progress": 20,
                "hint": "画像构建 Agent 已完成更新。",
                "data": {"profile": profile.model_dump(mode="json")},
            }
        )

    # Use LLM-based inference if subject/knowledge not provided
    if request.subject and request.knowledge_point:
        subject = request.subject
        knowledge_point = request.knowledge_point
    else:
        inferred_subject, inferred_kp = _infer_subject_and_knowledge(effective_message)
        subject = request.subject or profile.learning_goal.target_course or inferred_subject
        knowledge_point = request.knowledge_point or inferred_kp

    emit(
        {
            "agent_name": "path_agent",
            "stage": "path_generate",
            "status": "running",
            "progress": 28,
            "hint": "路径规划 Agent 正在拆解知识点顺序和学习路径...",
        }
    )
    try:
        path = learning_path_service.generate_path(
            LearningPathGenerateRequest(
                user_id=request.user_id,
                target_goal=request.message,
                subject=subject,
                base_agent_id=request.base_agent_id,
            )
        )
    except Exception as exc:
        from app.schemas.learning_path import LearningPath, LearningPathNode
        path = LearningPath(
            path_id=uuid4(),
            user_id=request.user_id,
            title=f"{knowledge_point} 学习路径",
            goal=request.message,
            nodes=[
                LearningPathNode(
                    node_id=uuid4(), order=1, knowledge_point=knowledge_point,
                    estimated_minutes=30, recommended_resource_types=["document"],
                    reason="默认路径", status="available",
                )
            ],
            status="degraded",
        )
        emit(
            {
                "agent_name": "path_agent",
                "stage": "path_generate",
                "status": "failed",
                "progress": 38,
                "hint": f"路径规划失败，使用默认路径: {exc}",
            }
        )
    else:
        emit(
            {
                "agent_name": "path_agent",
                "stage": "path_generate",
                "status": "done",
                "progress": 38,
                "hint": "路径规划 Agent 已生成个性化学习路径。",
                "data": {"path": path.model_dump(mode="json")},
            }
        )

    emit(
        {
            "agent_name": "document_agent",
            "stage": "resource_generate",
            "status": "running",
            "progress": 45,
            "hint": "文档生成 Agent 正在生成 Markdown 讲解文档...",
        }
    )
    try:
        generated = resource_service.generate_resources(
            ResourceGenerateRequest(
                user_id=request.user_id,
                subject=subject,
                knowledge_point=knowledge_point,
                resource_types=request.resource_types,
                difficulty=request.difficulty,
                base_agent_id=request.base_agent_id,
            ),
            emit_progress=emit,
        )
    except Exception as exc:
        from app.schemas.resource import ResourceGenerateResponse
        generated = ResourceGenerateResponse(
            task_id=uuid4(),
            workflow_id=uuid4(),
            resources=[],
            status="degraded",
        )
        emit(
            {
                "agent_name": "document_agent",
                "stage": "resource_generate",
                "status": "failed",
                "progress": 82,
                "hint": f"资源生成失败: {exc}",
            }
        )
    else:
        emit(
            {
                "agent_name": "document_agent",
                "stage": "resource_generate",
                "status": "done",
                "progress": 82,
                "hint": "文档、题库和多模态资源已生成完成。",
            }
        )

    workflow = workflow_service.get_workflow(generated.workflow_id)
    if workflow is None:
        raise ServiceError(ErrorCode.RESOURCE_GENERATION_FAILED, "学习流程创建失败")

    emit(
        {
            "agent_name": "recommendation_agent",
            "stage": "recommendation_generate",
            "status": "running",
            "progress": 88,
            "hint": "推荐 Agent 正在整合资源排序和推送逻辑...",
        }
    )
    recommendations = recommendation_service.get_recommendations(request.user_id)

    session = conversation_service.append_message(
        request.user_id,
        role="assistant",
        content=(
            f"已围绕「{knowledge_point}」更新画像，生成 {len(path.nodes)} 步学习路径，"
            f"{len(generated.resources)} 份学习资源，并完成推荐排序。"
        ),
        conversation_id=session.conversation_id,
        intent="learning_result",
        profile_id=profile.profile_id,
        metadata={
            "workflow_id": str(generated.workflow_id),
            "resource_ids": [str(item.resource_id) for item in generated.resources],
            "intent_result": {
                "intent": "learning_path", "confidence": 1.0, "method": "pipeline",
                "result": {
                    "title": path.title,
                    "nodes": [{"knowledge_point": n.knowledge_point, "status": n.status, "order": n.order} for n in path.nodes],
                    "resources": [r.model_dump(mode="json") for r in generated.resources],
                },
            },
        },
    )

    emit(
        {
            "agent_name": "recommendation_agent",
            "stage": "recommendation_generate",
            "status": "done",
            "progress": 100,
            "hint": "本轮学习闭环已完成。",
        }
    )

    return LearningStartResponse(
        task_id=generated.task_id,
        workflow_id=generated.workflow_id,
        conversation_id=session.conversation_id,
        status=generated.status,
        stream_url=f"/api/v1/agent-workflows/{generated.workflow_id}/stream",
        profile=profile,
        path=path,
        resources=generated.resources,
        workflow=workflow,
        recommendations=recommendations,
        messages=session.messages,
    )
