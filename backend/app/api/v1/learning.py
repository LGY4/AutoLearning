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

from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.learning import ResourceRecommendRequest, ResourceRecommendResponse
from app.services import assess_agent, diagnostic_agent, learning_service, master_agent

_logger = logging.getLogger(__name__)


router = APIRouter()


@router.get("/welcome")
def get_welcome(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Get personalized welcome data for the current user."""
    from app.services.welcome_service import get_welcome_data
    return success(get_welcome_data(current_user.id))


class IntentRouteRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = None
    knowledge_point: Optional[str] = None
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None
    model_api_base: Optional[str] = None
    model_api_key: Optional[str] = None
    model_name: Optional[str] = None
    model_temperature: Optional[float] = None
    rag_context: Optional[List[dict]] = None


class IntentRouteResponse(BaseModel):
    intent: str
    confidence: float
    method: str
    result: dict
    conversation_id: Optional[str] = None


@router.post("/chat", response_model=ApiResponse[IntentRouteResponse])
def intent_chat(payload: IntentRouteRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[IntentRouteResponse]:
    """MasterAgent intent router — detects intent and dispatches to appropriate service."""
    from app.services.model_gateway import ModelOverride, model_override_context
    override = ModelOverride(
        provider=payload.model_provider,
        api_base=payload.model_api_base,
        api_key=payload.model_api_key,
        model_name=payload.model_name,
        temperature=payload.model_temperature,
    )
    with model_override_context(override):
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

    # Stage 1: fast keyword intent detection
    detected_intent = master_agent.keyword_match(payload.message)

    # Stage 2: if keywords didn't match, use full detection (includes LLM fallback)
    # Without this, messages that should be ASSESSMENT/EXERCISE/etc. get silently
    # misrouted to tutoring when keywords don't fire.
    if detected_intent is None:
        detected_intent, _confidence, _method = master_agent.detect_intent(payload.message)

    # If not tutoring intent, use sync path which handles all intents correctly
    if detected_intent != master_agent.Intent.TUTORING:
        try:
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
        except Exception as exc:
            _logger.exception("non-tutor route_message failed")
            from app.core.errors import ServiceError, friendly_message
            if isinstance(exc, ServiceError):
                msg = friendly_message(exc.code)
                code = exc.code.value
            else:
                msg = "AI 服务暂时不可用，请重试"
                code = "INTERNAL_ERROR"
            def non_tutor_stream():
                yield f"event: error\ndata: {json.dumps({'message': msg, 'error_code': code}, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"
            return StreamingResponse(non_tutor_stream(), media_type="text/event-stream")

        def non_tutor_stream():
            yield f"event: result\ndata: {json.dumps(response_data, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(non_tutor_stream(), media_type="text/event-stream")

    # Tutoring intent: stream LLM response
    def event_stream():
        from app.services import tutor_service
        from app.services.model_gateway import ModelOverride, _model_override_ctx
        override = ModelOverride(
            provider=payload.model_provider,
            api_base=payload.model_api_base,
            api_key=payload.model_api_key,
            model_name=payload.model_name,
            temperature=payload.model_temperature,
        )
        deadline = time.monotonic() + 300  # 5 min limit

        # Set override directly (avoid context manager __exit__ across yield boundary)
        token = _model_override_ctx.set(override)
        try:
            _kp = payload.knowledge_point or ""
            _conv_id = payload.conversation_id
            _streamed_text = ""
            _last_result = None
            for chunk in tutor_service.answer_question_streaming(
                user_id=current_user.id,
                question=payload.message,
                knowledge_point=payload.knowledge_point,
                base_agent_id=payload.base_agent_id,
                conversation_id=payload.conversation_id,
                rag_context=payload.rag_context,
            ):
                if time.monotonic() > deadline:
                    break
                if isinstance(chunk, dict):
                    # Extract knowledge_point from result if available
                    _kp = chunk.get("knowledge_point", _kp) or _kp
                    _last_result = chunk
                    _conv_id = chunk.get("conversation_id", _conv_id) or _conv_id
                    yield f"event: result\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif isinstance(chunk, str) and chunk:
                    _streamed_text += chunk
                    yield f"event: text_delta\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            # Update persisted message with full intent_result (videos, resource_recommendation, etc.)
            if _conv_id and _last_result:
                try:
                    from app.services import conversation_service
                    conversation_service.update_last_assistant_message(
                        user_id=current_user.id,
                        conversation_id=_conv_id if isinstance(_conv_id, UUID) else UUID(_conv_id),
                        metadata_patch={
                            "intent_result": {
                                "intent": "tutoring", "confidence": 1.0, "method": "streaming",
                                "result": {
                                    "markdown": _last_result.get("markdown", _streamed_text),
                                    "answer": _last_result.get("answer", _streamed_text),
                                    "knowledge_point": _kp,
                                    "rag_references": _last_result.get("rag_references", []),
                                    "next_step": _last_result.get("next_step"),
                                    "videos": _last_result.get("videos", []),
                                    "resource_recommendation": _last_result.get("resource_recommendation"),
                                },
                            },
                        },
                    )
                except Exception:
                    _logger.debug("Failed to update streaming message metadata", exc_info=True)

            # Invalidate recommendations so they refresh on next fetch
            if _kp:
                try:
                    from app.services import recommendation_service
                    recommendation_service.invalidate_recommendations(current_user.id)
                except Exception:
                    _logger.warning("Recommendation invalidation failed for kp=%s", _kp, exc_info=True)

                # Emit a follow-up quiz question for self-check
                try:
                    quiz_data = tutor_service.quiz_before_answer_step1(
                        user_id=current_user.id,
                        question=payload.message,
                        knowledge_point=_kp,
                        base_agent_id=payload.base_agent_id,
                        conversation_id=payload.conversation_id,
                    )
                    if quiz_data.get("quiz_pending"):
                        yield f"event: quiz_followup\ndata: {json.dumps(quiz_data, ensure_ascii=False)}\n\n"
                except Exception:
                    _logger.warning("Follow-up quiz generation failed for kp=%s", _kp, exc_info=True)
        except Exception as exc:
            _logger.exception("chat-stream failed")
            from app.core.errors import ServiceError, friendly_message
            if isinstance(exc, ServiceError):
                msg = friendly_message(exc.code)
                code = exc.code.value
            else:
                msg = "AI 服务暂时不可用，请重试"
                code = "INTERNAL_ERROR"
            yield f"event: error\ndata: {json.dumps({'message': msg, 'error_code': code}, ensure_ascii=False)}\n\n"
        finally:
            _model_override_ctx.reset(token)

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Start-Stream (full learning pipeline with SSE) ──────────────────────


class StartStreamRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = None
    resource_types: Optional[List[str]] = None
    difficulty: str = Field(default="1", pattern="^[123]$")
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None
    model_api_base: Optional[str] = None
    model_api_key: Optional[str] = None
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

    def event_stream():
        q = Queue()  # type: Queue[Optional[dict]]
        cancel = threading.Event()

        def emit_progress(event: dict):
            if not cancel.is_set():
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
                    user_id=current_user.id,
                    message=payload.message,
                    conversation_id=payload.conversation_id,
                    resource_types=resource_types or default_resource_types(),
                    difficulty=payload.difficulty,
                    base_agent_id=payload.base_agent_id,
                    model_provider=payload.model_provider,
                    model_api_base=payload.model_api_base,
                    model_api_key=payload.model_api_key,
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
                from app.core.errors import ServiceError, friendly_message
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

        cancel.set()  # signal thread to stop emitting
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class QuizAnswerResponse(BaseModel):
    intent: str = "tutoring"
    confidence: float = 1.0
    method: str = "quiz_scored"
    result: dict
    conversation_id: Optional[str] = None


class QuizNextRequest(BaseModel):
    answer: str
    quiz_session: dict
    knowledge_point: str
    original_question: str
    conversation_id: Optional[UUID] = None
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None
    model_api_base: Optional[str] = None
    model_api_key: Optional[str] = None
    model_name: Optional[str] = None
    model_temperature: Optional[float] = None


@router.post("/chat/quiz-next", response_model=ApiResponse[QuizAnswerResponse])
def quiz_next_chat(payload: QuizNextRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[QuizAnswerResponse]:
    """Adaptive quiz: submit answer and get next question or final results."""
    from app.services.model_gateway import ModelOverride, model_override_context
    override = ModelOverride(
        provider=payload.model_provider,
        api_base=payload.model_api_base,
        api_key=payload.model_api_key,
        model_name=payload.model_name,
        temperature=payload.model_temperature,
    )
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
    knowledge_point: str
    conversation_id: Optional[UUID] = None


@router.post("/chat/post-test", response_model=ApiResponse[dict])
def post_test(payload: PostTestRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Generate a post-learning quiz to verify understanding."""
    from app.services import tutor_service
    result = tutor_service.generate_post_test(
        user_id=current_user.id,
        knowledge_point=payload.knowledge_point,
        conversation_id=payload.conversation_id,
    )
    return success(result)


class PostQuizStartRequest(BaseModel):
    knowledge_point: str
    conversation_id: Optional[UUID] = None


@router.post("/chat/post-quiz-start", response_model=ApiResponse[dict])
def post_quiz_start(payload: PostQuizStartRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Start a post-learning quiz with profile-based questions."""
    from app.services import tutor_service
    result = tutor_service.quiz_post_learning_step1(
        user_id=current_user.id,
        knowledge_point=payload.knowledge_point,
        conversation_id=payload.conversation_id,
    )
    return success(result)


class PostQuizNextRequest(BaseModel):
    answer: str
    quiz_session: dict
    knowledge_point: str
    conversation_id: Optional[UUID] = None


@router.post("/chat/post-quiz-next", response_model=ApiResponse[dict])
def post_quiz_next(payload: PostQuizNextRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Submit answer for post-learning quiz. Returns feedback + next question or final results."""
    from app.services import tutor_service
    result = tutor_service.quiz_post_learning_next(
        user_id=current_user.id,
        answer=payload.answer,
        quiz_session=payload.quiz_session,
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
    major: str
    grade: str
    goal: str
    subject: str = "数据结构"
    num_questions: int = Field(default=8, ge=1, le=50)


class OnboardSubmitRequest(BaseModel):
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
    # Guard: if user already has a completed profile, return it instead of overwriting
    from app.repositories.vertical_loop_repository import repository
    existing = repository.get_profile(current_user.id)
    if existing and existing.completeness_score >= 0.5 and existing.dynamic_update.update_source == "diagnostic":
        from app.services import assessment_service
        return success(OnboardResult(
            profile=existing.model_dump(mode="json"),
            assessment={"status": "already_completed", "mastery_score": existing.completeness_score},
            quiz_result={"status": "already_completed"},
        ))
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
    quiz = diagnostic_agent.generate_quick_position_quiz(
        major=payload.major,
        grade=payload.grade,
        goal=payload.goal,
        subject=payload.subject,
    )
    return success(OnboardQuizResponse(quiz=quiz))


# ── Path node completion ────────────────────────────────────────────────


class PathNodeCompleteRequest(BaseModel):
    node_id: UUID


@router.post("/path/node/complete", response_model=ApiResponse[dict])
def complete_path_node(payload: PathNodeCompleteRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Mark a learning path node as completed and unlock the next node."""
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


class CompleteKnowledgePointRequest(BaseModel):
    knowledge_point: str


@router.post("/complete-knowledge-point", response_model=ApiResponse[dict])
def complete_knowledge_point(payload: CompleteKnowledgePointRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Unified completion: updates both profile known_topics and learning path node status."""
    from app.services.completion_service import mark_knowledge_point_completed
    result = mark_knowledge_point_completed(current_user.id, payload.knowledge_point, source="map")
    return success(result)


# ── Resource recommendation ─────────────────────────────────────────────


@router.post("/resource-recommend", response_model=ApiResponse[ResourceRecommendResponse])
def recommend_resources(payload: ResourceRecommendRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[ResourceRecommendResponse]:
    """Recommend resource types based on user profile and knowledge point."""
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


class TrackConsumptionRequest(BaseModel):
    resource_id: str
    knowledge_point: str
    resource_type: str = ""
    duration_seconds: int = 0
    completion_pct: float = 0.0


@router.post("/resource/track-consumption", response_model=ApiResponse[dict])
def track_consumption(payload: TrackConsumptionRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Track resource consumption for profile update."""
    from app.services.learning_record_service import track_resource_consumption
    result = track_resource_consumption(
        user_id=current_user.id,
        resource_id=payload.resource_id,
        knowledge_point=payload.knowledge_point,
        resource_type=payload.resource_type,
        duration_seconds=payload.duration_seconds,
        completion_pct=payload.completion_pct,
    )
    return success(result)
