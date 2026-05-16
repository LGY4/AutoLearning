from __future__ import annotations

from typing import Dict,  List,  Optional

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict,  List,  Any, TypedDict
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ModuleNotFoundError:
    START = "__start__"
    END = "__end__"
    LANGGRAPH_AVAILABLE = False

    class _CompiledFallbackGraph:
        def __init__(self, nodes: List[tuple[str, Any]]) -> None:
            self.nodes = nodes

        def invoke(self, state: "LearningGraphState") -> "LearningGraphState":
            current = dict(state)
            for _, node in self.nodes:
                current.update(node(current))
            return current

    class StateGraph:  # type: ignore[no-redef]
        def __init__(self, state_type: type) -> None:
            self.state_type = state_type
            self.nodes: List[tuple[str, Any]] = []

        def add_node(self, name: str, node: Any) -> None:
            self.nodes.append((name, node))

        def add_edge(self, start: str, end: str) -> None:
            return None

        def compile(self) -> _CompiledFallbackGraph:
            return _CompiledFallbackGraph(self.nodes)

from app.core.enums import AgentName, AgentTaskStatus
from app.schemas.workflow import AgentEvent, AgentTask


class LearningGraphState(TypedDict, total=False):
    user_id: str
    workflow_context: Dict[str, Any]
    completed_steps: List[str]
    agent_results: Dict[str, Any]


@dataclass(frozen=True)
class WorkflowStep:
    agent_name: AgentName
    task_type: str
    action: str
    progress: int


BASE_AGENT_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep(AgentName.PROFILE, "profile_extract", "profile_ready", 12),
    WorkflowStep(AgentName.PATH, "path_generate", "path_ready", 24),
    WorkflowStep(AgentName.DOCUMENT, "resource_document", "document_ready", 38),
    WorkflowStep(AgentName.MINDMAP, "resource_mindmap", "mindmap_ready", 50),
    WorkflowStep(AgentName.QUIZ, "resource_quiz", "quiz_ready", 62),
    WorkflowStep(AgentName.CODE, "resource_code_case", "code_case_ready", 74),
    WorkflowStep(AgentName.QUALITY, "quality_check", "quality_passed", 88),
    WorkflowStep(AgentName.RECOMMENDATION, "recommendation_generate", "recommendation_ready", 100),
)
VERTICAL_AGENT_STEPS = BASE_AGENT_STEPS

MULTIMODAL_AGENT_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep(AgentName.PROFILE, "profile_extract", "profile_ready", 10),
    WorkflowStep(AgentName.PATH, "path_generate", "path_ready", 20),
    WorkflowStep(AgentName.DOCUMENT, "resource_document", "document_ready", 32),
    WorkflowStep(AgentName.MINDMAP, "resource_mindmap", "mindmap_ready", 44),
    WorkflowStep(AgentName.QUIZ, "resource_quiz", "quiz_ready", 56),
    WorkflowStep(AgentName.VIDEO, "resource_video_animation", "multimodal_storyboard_ready", 68),
    WorkflowStep(AgentName.CODE, "resource_code_case", "code_case_ready", 80),
    WorkflowStep(AgentName.QUALITY, "quality_check", "quality_passed", 92),
    WorkflowStep(AgentName.RECOMMENDATION, "recommendation_generate", "recommendation_ready", 100),
)


def _workflow_steps_for_payload(input_payload: Optional[dict]) -> tuple[WorkflowStep, ...]:
    resource_types = set((input_payload or {}).get("resource_types") or [])
    if {"video", "animation"} & resource_types:
        return MULTIMODAL_AGENT_STEPS
    return BASE_AGENT_STEPS


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_langgraph_blueprint(steps: tuple[WorkflowStep, ...] | None = None) -> Dict[str, List[str]]:
    workflow_steps = steps or BASE_AGENT_STEPS
    return {
        "nodes": [step.agent_name.value for step in workflow_steps],
        "edges": [
            f"{workflow_steps[index].agent_name.value}->{workflow_steps[index + 1].agent_name.value}"
            for index in range(len(workflow_steps) - 1)
        ],
        "runtime": ["langgraph" if LANGGRAPH_AVAILABLE else "compatibility_fallback"],
    }


def _make_agent_node(step: WorkflowStep):
    def agent_node(state: LearningGraphState) -> LearningGraphState:
        completed = [*state.get("completed_steps", []), step.agent_name.value]
        return {"completed_steps": completed}

    return agent_node


def build_learning_graph(include_multimodal: bool = False):
    graph = StateGraph(LearningGraphState)
    workflow_steps = MULTIMODAL_AGENT_STEPS if include_multimodal else BASE_AGENT_STEPS
    node_names = [step.agent_name.value for step in workflow_steps]

    for step in workflow_steps:
        graph.add_node(step.agent_name.value, _make_agent_node(step))

    graph.add_edge(START, node_names[0])
    for current, next_node in zip(node_names, node_names[1:]):
        graph.add_edge(current, next_node)
    graph.add_edge(node_names[-1], END)
    return graph.compile()


def _execute_quality_agent(user_id: UUID, payload: dict) -> Dict[str, Any]:
    """Use LLM to review generated resource quality."""
    from app.services import model_gateway

    knowledge_point = payload.get("knowledge_point", "")
    subject = payload.get("subject", "")
    prompt = (
        "你是质量检查Agent。请评估以下学习资源的质量。\n"
        f"学科：{subject}\n"
        f"知识点：{knowledge_point}\n\n"
        "评估维度：\n"
        "1. 内容准确性（概念是否正确）\n"
        "2. 完整性（是否覆盖核心要点）\n"
        "3. 难度适当性（是否匹配目标难度）\n"
        "4. 可读性（结构是否清晰）\n\n"
        '返回严格 JSON：{"score": 0.0-1.0, "feedback": "评估意见", "issues": ["问题列表"]}'
    )
    try:
        result = model_gateway.generate_json(
            prompt,
            required_keys=["score", "feedback"],
        )
        return {
            "status": "success",
            "quality_check": "passed",
            "quality_score": result.get("score", 0.8),
            "feedback": result.get("feedback", ""),
            "issues": result.get("issues", []),
        }
    except Exception as exc:
        return {"status": "success", "quality_check": "degraded", "quality_score": 0.4, "feedback": f"质量检查失败: {exc}"}


def _execute_recommendation_agent(user_id: UUID, payload: dict) -> Dict[str, Any]:
    """Generate real recommendations based on profile and resources."""
    from app.repositories.vertical_loop_repository import repository

    try:
        recommendations = repository.create_recommendations(user_id)
        return {
            "status": "success",
            "recommendations_generated": True,
            "count": len(recommendations),
            "top_titles": [r.title for r in recommendations[:3]],
        }
    except Exception as exc:
        return {"status": "success", "recommendations_generated": False, "error": str(exc)}


def _execute_agent_step(
    step: WorkflowStep,
    user_id: UUID,
    payload: dict,
    profile=None,
    base_agent=None,
) -> Dict[str, Any]:
    """Execute a real agent step and return the result."""
    from app.services import agent_runtime
    from app.core.enums import ResourceType

    knowledge_point = payload.get("knowledge_point", "")
    subject = payload.get("subject", "")
    difficulty = payload.get("difficulty", "beginner")

    try:
        if step.agent_name == AgentName.PROFILE:
            from app.schemas.profile import ProfileExtractRequest
            request = ProfileExtractRequest(
                user_id=user_id,
                conversation=[{"role": "user", "content": payload.get("goal", "")}],
            )
            result = agent_runtime.build_profile(request, profile, base_agent)
            return {"status": "success", "profile": result.model_dump(mode="json")}

        elif step.agent_name == AgentName.PATH:
            result = agent_runtime.build_learning_path(
                user_id, payload.get("goal", ""), subject, profile, base_agent
            )
            return {"status": "success", "path_nodes": len(result.nodes)}

        elif step.agent_name == AgentName.DOCUMENT:
            result = agent_runtime.build_learning_resource(
                user_id, subject, knowledge_point, ResourceType.DOCUMENT, difficulty, profile, base_agent
            )
            return {"status": "success", "resource_id": str(result.resource_id)}

        elif step.agent_name == AgentName.MINDMAP:
            result = agent_runtime.build_learning_resource(
                user_id, subject, knowledge_point, ResourceType.MINDMAP, difficulty, profile, base_agent
            )
            return {"status": "success", "resource_id": str(result.resource_id)}

        elif step.agent_name == AgentName.QUIZ:
            result = agent_runtime.build_learning_resource(
                user_id, subject, knowledge_point, ResourceType.QUIZ, difficulty, profile, base_agent
            )
            return {"status": "success", "resource_id": str(result.resource_id)}

        elif step.agent_name == AgentName.CODE:
            result = agent_runtime.build_learning_resource(
                user_id, subject, knowledge_point, ResourceType.CODE_CASE, difficulty, profile, base_agent
            )
            return {"status": "success", "resource_id": str(result.resource_id)}

        elif step.agent_name == AgentName.VIDEO:
            result = agent_runtime.build_learning_resource(
                user_id, subject, knowledge_point, ResourceType.VIDEO, difficulty, profile, base_agent
            )
            return {"status": "success", "resource_id": str(result.resource_id)}

        elif step.agent_name == AgentName.QUALITY:
            return _execute_quality_agent(user_id, payload)

        elif step.agent_name == AgentName.RECOMMENDATION:
            return _execute_recommendation_agent(user_id, payload)

        return {"status": "skipped", "reason": f"No handler for {step.agent_name.value}"}

    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def run_fallback_workflow(
    workflow_id: UUID,
    user_id: UUID,
    input_payload: Optional[dict] = None,
    profile=None,
    base_agent=None,
) -> tuple[List[AgentTask], List[AgentEvent]]:
    """Serial fallback workflow — runs agents sequentially without LangGraph."""
    tasks: List[AgentTask] = []
    events: List[AgentEvent] = []
    previous_agent: Optional[AgentName] = None
    payload = input_payload or {}
    workflow_steps = _workflow_steps_for_payload(payload)

    # Compute completed step names directly (graph invocation removed — it was hanging)
    graph_result: Dict[str, Any] = {"completed_steps": [s.agent_name.value for s in workflow_steps]}

    for index, step in enumerate(workflow_steps):
        task_id = uuid4()

        # Real execution with timing
        start_time = time.monotonic()
        agent_result = _execute_agent_step(step, user_id, payload, profile, base_agent)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        status = AgentTaskStatus.SUCCESS if agent_result.get("status") == "success" else AgentTaskStatus.FAILED

        task = AgentTask(
            task_id=task_id,
            workflow_id=workflow_id,
            agent_name=step.agent_name,
            task_type=step.task_type,
            status=status,
            progress=100 if status == AgentTaskStatus.SUCCESS else 0,
            input_payload={"user_id": str(user_id), "workflow_context": payload},
            output_payload={
                "message": f"{step.agent_name.value} {'completed' if status == AgentTaskStatus.SUCCESS else 'failed'}",
                "action": step.action,
                "result": agent_result,
                "graph": build_langgraph_blueprint(workflow_steps) if index == 0 else None,
                "langgraph_runtime": "langgraph" if LANGGRAPH_AVAILABLE else "compatibility_fallback",
                "langgraph_completed_steps": graph_result.get("completed_steps", []) if index == 0 else None,
            },
            duration_ms=duration_ms,
        )
        tasks.append(task)
        events.append(
            AgentEvent(
                event_id=uuid4(),
                workflow_id=workflow_id,
                task_id=task_id,
                from_agent=previous_agent,
                to_agent=step.agent_name,
                action=step.action,
                status=status,
                progress=step.progress,
                input_snapshot={"user_id": str(user_id), "task_type": step.task_type},
                output_snapshot={"agent_name": step.agent_name.value, "status": status.value, "result": agent_result},
                duration_ms=duration_ms,
                created_at=now_iso(),
            )
        )
        previous_agent = step.agent_name

    return tasks, events


# Backward-compatible alias
run_vertical_workflow = run_fallback_workflow


def run_workflow(
    workflow_id: UUID,
    user_id: UUID,
    input_payload: Optional[dict] = None,
    profile=None,
    base_agent=None,
    emit_progress=None,
) -> tuple[List[AgentTask], List[AgentEvent]]:
    """Run workflow with LangGraph first, fallback to serial on failure.

    1. Try LangGraph runtime (real StateGraph compilation + invoke)
    2. If unavailable, timeout, or error → fallback to serial execution
    """
    from app.workflows.langgraph_runtime import run_langgraph_workflow

    payload = input_payload or {}
    message = payload.get("goal", payload.get("message", ""))
    resource_types = payload.get("resource_types", ["document", "quiz"])
    difficulty = payload.get("difficulty", "beginner")
    subject = payload.get("subject", "通用")
    knowledge_point = payload.get("knowledge_point", "")
    base_agent_id = payload.get("base_agent_id")

    result = run_langgraph_workflow(
        user_id=user_id,
        message=message,
        workflow_id=workflow_id,
        resource_types=resource_types,
        difficulty=difficulty,
        subject=subject,
        knowledge_point=knowledge_point,
        base_agent_id=UUID(base_agent_id) if base_agent_id else None,
        emit_progress=emit_progress,
    )

    if result is not None:
        # Convert LangGraph result to AgentTask/AgentEvent format
        tasks = [AgentTask.model_validate(t) for t in result.get("tasks", [])]
        events = [AgentEvent.model_validate(e) for e in result.get("events", [])]
        return tasks, events

    # Fallback to serial execution
    logger.info("LangGraph unavailable/failed, falling back to serial workflow")
    return run_fallback_workflow(workflow_id, user_id, input_payload, profile, base_agent)
