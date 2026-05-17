from __future__ import annotations

from typing import Dict, List, Optional

import json
import logging
import threading
import time
from queue import Queue, Empty
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.learning import ResourceRecommendRequest, ResourceRecommendResponse
from app.services import assess_agent, diagnostic_agent, learning_service, master_agent

_logger = logging.getLogger(__name__)


router = APIRouter()


class IntentRouteRequest(BaseModel):
    user_id: UUID
    message: str
    conversation_id: Optional[UUID] = None
    knowledge_point: Optional[str] = None
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None


class IntentRouteResponse(BaseModel):
    intent: str
    confidence: float
    method: str
    result: dict
    conversation_id: Optional[str] = None


@router.post("/chat", response_model=ApiResponse[IntentRouteResponse])
def intent_chat(payload: IntentRouteRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[IntentRouteResponse]:
    """MasterAgent intent router — detects intent and dispatches to appropriate service."""
    payload.user_id = current_user.id
    result = master_agent.route_message(
        user_id=current_user.id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        knowledge_point=payload.knowledge_point,
        base_agent_id=payload.base_agent_id,
        model_provider=payload.model_provider,
    )
    return success(IntentRouteResponse(
        intent=result.get("intent", "general_chat"),
        confidence=result.get("confidence", 0.0),
        method=result.get("method", "unknown"),
        result=result.get("result", result),
        conversation_id=result.get("conversation_id"),
    ))


@router.post("/chat-stream")
def intent_chat_stream(payload: IntentRouteRequest, current_user: UserDTO = Depends(get_current_user)) -> StreamingResponse:
    """Streaming chat: detect intent first, then stream tutor answer or return structured result."""
    payload.user_id = current_user.id

    # Stage 1: fast keyword intent detection
    detected_intent = master_agent._keyword_match(payload.message)

    # If not tutoring intent, use sync path which handles all intents correctly
    if detected_intent and detected_intent != master_agent.Intent.TUTORING:
        result = master_agent.route_message(
            user_id=current_user.id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            knowledge_point=payload.knowledge_point,
            base_agent_id=payload.base_agent_id,
            model_provider=payload.model_provider,
        )
        response_data = {
            "intent": result.get("intent", "general_chat"),
            "confidence": result.get("confidence", 0.0),
            "method": result.get("method", "unknown"),
            "result": result.get("result", result),
            "conversation_id": result.get("conversation_id"),
        }

        def non_tutor_stream():
            yield f"event: result\ndata: {json.dumps(response_data, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(non_tutor_stream(), media_type="text/event-stream")

    # Tutoring intent: stream LLM response
    def event_stream():
        from app.services import tutor_service
        from app.services.model_gateway import ModelOverride, model_override_context
        override = ModelOverride(provider=payload.model_provider)
        deadline = time.monotonic() + 300  # 5 min limit

        try:
            with model_override_context(override):
                for chunk in tutor_service.answer_question_streaming(
                    user_id=current_user.id,
                    question=payload.message,
                    knowledge_point=payload.knowledge_point,
                    base_agent_id=payload.base_agent_id,
                ):
                    if time.monotonic() > deadline:
                        break
                    if isinstance(chunk, dict):
                        yield f"event: result\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    elif isinstance(chunk, str) and chunk:
                        yield f"event: text_delta\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            _logger.exception("chat-stream failed")
            from app.core.errors import ServiceError, friendly_message, ErrorCode
            if isinstance(exc, ServiceError):
                msg = friendly_message(exc.code)
                code = exc.code.value
            else:
                msg = "AI 服务暂时不可用，请重试"
                code = "INTERNAL_ERROR"
            yield f"event: error\ndata: {json.dumps({'message': msg, 'error_code': code}, ensure_ascii=False)}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Start-Stream (full learning pipeline with SSE) ──────────────────────


class StartStreamRequest(BaseModel):
    user_id: UUID
    message: str
    conversation_id: Optional[UUID] = None
    resource_types: Optional[List[str]] = None
    difficulty: str = "1"
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    model_temperature: Optional[float] = None


@router.post("/start-stream")
def learning_start_stream(
    payload: StartStreamRequest,
    current_user: UserDTO = Depends(get_current_user),
) -> StreamingResponse:
    """Full learning pipeline with SSE progress events."""
    from app.core.enums import ResourceType
    from app.schemas.learning import LearningStartRequest, default_resource_types

    payload.user_id = current_user.id

    def event_stream():
        q = Queue()  # type: Queue[Optional[dict]]

        def emit_progress(event: dict):
            q.put({"type": "agent_step", "data": event})

        def run():
            try:
                resource_types = None
                if payload.resource_types:
                    rts = []
                    for rt in payload.resource_types:
                        try:
                            rts.append(ResourceType(rt))
                        except ValueError:
                            pass
                    resource_types = rts if rts else None

                req = LearningStartRequest(
                    user_id=payload.user_id,
                    message=payload.message,
                    conversation_id=payload.conversation_id,
                    resource_types=resource_types or default_resource_types(),
                    difficulty=payload.difficulty,
                    base_agent_id=payload.base_agent_id,
                    model_provider=payload.model_provider,
                    model_name=payload.model_name,
                    model_temperature=payload.model_temperature,
                )
                result = learning_service.start_learning_langgraph(req, emit_progress)
                q.put({
                    "type": "result",
                    "data": result.model_dump(mode="json"),
                })
            except Exception as exc:
                _logger.exception("start-stream failed")
                from app.core.errors import ServiceError, friendly_message, ErrorCode
                if isinstance(exc, ServiceError):
                    msg = friendly_message(exc.code)
                    code = exc.code.value
                else:
                    msg = "学习流程执行失败，请重试"
                    code = "INTERNAL_ERROR"
                q.put({
                    "type": "error",
                    "data": {"message": msg, "error_code": code},
                })
            finally:
                q.put(None)  # sentinel

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        deadline = time.monotonic() + 600  # 10 min limit
        while time.monotonic() < deadline:
            try:
                msg = q.get(timeout=1.0)
            except Empty:
                continue
            if msg is None:
                break
            yield f"event: {msg['type']}\ndata: {json.dumps(msg['data'], ensure_ascii=False)}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class QuizAnswerResponse(BaseModel):
    intent: str = "tutoring"
    confidence: float = 1.0
    method: str = "quiz_scored"
    result: dict
    conversation_id: Optional[str] = None


class QuizNextRequest(BaseModel):
    user_id: UUID
    answer: str
    quiz_session: dict
    knowledge_point: str
    original_question: str
    conversation_id: Optional[UUID] = None
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None


@router.post("/chat/quiz-next", response_model=ApiResponse[QuizAnswerResponse])
def quiz_next_chat(payload: QuizNextRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[QuizAnswerResponse]:
    """Adaptive quiz: submit answer and get next question or final results."""
    payload.user_id = current_user.id
    from app.services.model_gateway import ModelOverride, model_override_context
    override = ModelOverride(provider=payload.model_provider)
    with model_override_context(override):
        from app.services import tutor_service
        result = tutor_service.quiz_before_answer_next(
            user_id=current_user.id,
            answer=payload.answer,
            quiz_session=payload.quiz_session,
            knowledge_point=payload.knowledge_point,
            original_question=payload.original_question,
            conversation_id=payload.conversation_id,
            base_agent_id=payload.base_agent_id,
        )
    return success(QuizAnswerResponse(
        result=result,
        conversation_id=result.get("conversation_id"),
    ))


class PostTestRequest(BaseModel):
    user_id: UUID
    knowledge_point: str
    conversation_id: Optional[UUID] = None


@router.post("/chat/post-test", response_model=ApiResponse[dict])
def post_test(payload: PostTestRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Generate a post-learning quiz to verify understanding."""
    payload.user_id = current_user.id
    from app.services import tutor_service
    result = tutor_service.generate_post_test(
        user_id=current_user.id,
        knowledge_point=payload.knowledge_point,
        conversation_id=payload.conversation_id,
    )
    return success(result)


@router.get("/assess", response_model=ApiResponse[dict])
def assess_user(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """AssessAgent — multi-dimensional learning evaluation."""
    return success(assess_agent.assess_learning(current_user.id))


# ── Onboarding / Diagnostic ──────────────────────────────────────────────


class OnboardRequest(BaseModel):
    user_id: UUID
    major: str
    grade: str
    goal: str
    subject: str = "数据结构"
    num_questions: int = 8


class OnboardSubmitRequest(BaseModel):
    user_id: UUID
    major: str
    grade: str
    goal: str
    subject: str = "数据结构"
    quiz: dict  # output from /onboard
    answers: Dict[int, str]  # {question_id: "A"/"B"/"C"/"D"}


class OnboardResult(BaseModel):
    profile: dict
    assessment: dict
    quiz_result: dict


class OnboardQuizResponse(BaseModel):
    quiz: dict


@router.post("/onboard", response_model=ApiResponse[OnboardQuizResponse])
def onboard(payload: OnboardRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[OnboardQuizResponse]:
    """Step 1: Generate diagnostic quiz for new user."""
    payload.user_id = current_user.id
    quiz = diagnostic_agent.generate_diagnostic_quiz(
        major=payload.major,
        grade=payload.grade,
        goal=payload.goal,
        subject=payload.subject,
        num_questions=payload.num_questions,
    )
    return success(OnboardQuizResponse(quiz=quiz))


@router.post("/onboard/submit", response_model=ApiResponse[OnboardResult])
def onboard_submit(payload: OnboardSubmitRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[OnboardResult]:
    """Step 2: Score diagnostic answers, create initial profile + assessment."""
    payload.user_id = current_user.id
    result = diagnostic_agent.score_diagnostic(
        user_id=current_user.id,
        major=payload.major,
        grade=payload.grade,
        goal=payload.goal,
        subject=payload.subject,
        quiz=payload.quiz,
        answers=payload.answers,
    )
    return success(OnboardResult(
        profile=result.get("profile", {}),
        assessment=result.get("assessment", {}),
        quiz_result=result.get("quiz_result", {}),
    ))


@router.post("/onboard/quick", response_model=ApiResponse[OnboardQuizResponse])
def onboard_quick(payload: OnboardRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[OnboardQuizResponse]:
    """快速定位：用户已有身份信息时，3道题定位四维度水平。"""
    payload.user_id = current_user.id
    quiz = diagnostic_agent.generate_quick_position_quiz(
        major=payload.major,
        grade=payload.grade,
        goal=payload.goal,
        subject=payload.subject,
    )
    return success(OnboardQuizResponse(quiz=quiz))


# ── Path node completion ────────────────────────────────────────────────


class PathNodeCompleteRequest(BaseModel):
    user_id: UUID
    node_id: UUID


@router.post("/path/node/complete", response_model=ApiResponse[dict])
def complete_path_node(payload: PathNodeCompleteRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Mark a learning path node as completed and unlock the next node."""
    payload.user_id = current_user.id
    from app.repositories.vertical_loop_repository import repository
    path = repository.complete_path_node(current_user.id, payload.node_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found")

    # Update profile for the completed node's knowledge point (timing #4)
    completed_kp = None
    for node in path.nodes:
        if node.node_id == payload.node_id:
            completed_kp = node.knowledge_point
            break
    if completed_kp:
        from app.services.profile_event_service import ProfileEventType, emit_event
        from app.services.profile_eval_service import evaluate_knowledge_point
        from app.services.profile_service import get_profile
        profile = get_profile(current_user.id)
        if profile:
            dim = evaluate_knowledge_point(profile, completed_kp, quiz_accuracy=0.8, total_questions=1)
            emit_event(current_user.id, ProfileEventType.PATH_NODE_COMPLETE, {"knowledge_point": completed_kp, "dimension": dim.model_dump()}, confidence=0.6)

    return success(path.model_dump(mode="json"))


# ── Resource recommendation ─────────────────────────────────────────────


@router.post("/resource-recommend", response_model=ApiResponse[ResourceRecommendResponse])
def recommend_resources(payload: ResourceRecommendRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[ResourceRecommendResponse]:
    """Recommend resource types based on user profile and knowledge point."""
    payload.user_id = current_user.id
    from app.repositories.vertical_loop_repository import repository
    from app.services.strategy_engine import get_resource_params

    profile = repository.get_profile(current_user.id)

    # Get dimension for this knowledge point
    dim = None
    if profile and profile.knowledge_profile.topic_dimensions:
        dim = profile.knowledge_profile.topic_dimensions.get(payload.knowledge_point)

    if dim:
        style = profile.learning_preference.learning_style if profile else "mixed"
        params = get_resource_params(dim, style)
        recommended = params.get("resource_types", ["document", "quiz"])
        composite = dim.composite_score
        label = dim.overall_label
        if composite >= 0.7:
            reason = f"该知识点掌握度已达到 {label}（{composite:.0%}），推荐进阶资源巩固提升。"
        elif composite >= 0.4:
            reason = f"该知识点掌握度为 {label}（{composite:.0%}），推荐实践类资源加强应用。"
        else:
            reason = f"该知识点掌握度较低（{composite:.0%}），推荐基础资源建立概念。"
        dim_summary = {
            "mastery": dim.mastery,
            "application": dim.application,
            "memory": dim.memory,
            "understanding": dim.understanding,
            "composite_score": round(composite, 2),
            "overall_label": label,
        }
    else:
        # No dimension data — recommend all types as starting point
        recommended = ["document", "mindmap", "quiz", "code_case", "video"]
        reason = "该知识点暂无评估数据，推荐全面学习资源建立基础。"
        dim_summary = {}

    return success(ResourceRecommendResponse(
        recommended_types=recommended,
        existing_types=[],
        reason=reason,
        dimension_summary=dim_summary,
    ))
