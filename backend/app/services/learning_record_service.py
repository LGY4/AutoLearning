from __future__ import annotations

from typing import Optional

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.repositories.vertical_loop_repository import repository
from app.schemas.learning_record import LearningRecordCreate, LearningRecordResponse
from app.services.profile_event_service import ProfileEventType, emit_event
from app.services.runtime_support import now_iso


def _compute_next_review(user_id, knowledge_point: Optional[str], conversation_id: Optional[UUID] = None) -> Optional[str]:
    """Compute next review time based on strategy engine's review_interval_days."""
    if not knowledge_point:
        return None
    from app.services import profile_service
    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    if not profile:
        return None
    from app.services.strategy_engine import get_teaching_params
    topic_dims = profile.knowledge_profile.topic_dimensions or {}
    dim = topic_dims.get(knowledge_point)
    if dim is None:
        from app.schemas.profile import KnowledgeDimension
        dim = KnowledgeDimension(mastery="low", application="low", memory="low", understanding="low")
    params = get_teaching_params(dim)
    interval_days = params.get("review_interval_days", 0)
    if interval_days <= 0:
        return None
    next_time = datetime.now(timezone.utc) + timedelta(days=interval_days)
    return next_time.isoformat(timespec="seconds")


def create_learning_record(request: LearningRecordCreate, conversation_id: Optional[UUID] = None) -> LearningRecordResponse:
    persisted_id = repository.save_learning_record(request)
    from app.services import profile_service
    profile = profile_service.get_profile(request.user_id, conversation_id=conversation_id)
    updated = list(request.wrong_points)
    if profile and request.wrong_points:
        merged = list(dict.fromkeys(profile.knowledge_profile.weak_topics + request.wrong_points))
        emit_event(request.user_id, ProfileEventType.WRONG_POINTS, {"wrong_points": request.wrong_points}, confidence=0.5)
        updated = merged
    next_review = _compute_next_review(request.user_id, request.knowledge_point, conversation_id=conversation_id)
    return LearningRecordResponse(
        record_id=persisted_id or uuid4(),
        profile_update_triggered=bool(request.wrong_points),
        updated_weak_points=updated,
        next_review_at=next_review,
    )


def get_learning_summary(user_id) -> dict:
    """Return aggregated learning stats for a user (combines learning records + answer records)."""
    records = repository.list_learning_records(user_id)
    answer_records = repository.get_user_answer_history(user_id)

    # 合并答题记录到学习统计
    answer_scores = [r["score"] for r in answer_records if r.get("score") is not None]
    answer_duration = sum(r.get("time_spent_seconds", 0) or 0 for r in answer_records)
    answer_correct = sum(1 for r in answer_records if r.get("is_correct"))

    learning_scores = [r["score"] for r in records if r.get("score") is not None]
    learning_duration = sum(r.get("duration_seconds", 0) or 0 for r in records)

    all_scores = learning_scores + answer_scores
    total_duration = learning_duration + answer_duration

    profile = repository.get_profile(user_id)
    weak_points = list(profile.knowledge_profile.weak_topics) if profile else []

    # 最近记录：合并学习记录和答题记录，按时间倒序
    recent_answers = [
        {"type": "answer", "score": r.get("score"), "is_correct": r.get("is_correct"),
         "created_at": r.get("submitted_at"), "question_id": r.get("question_id"),
         "knowledge_point": r.get("knowledge_point") or ""}
        for r in answer_records[:10]
    ]
    recent_learning = [
        {"type": "learning", "score": r.get("score"), "knowledge_point": r.get("knowledge_point") or "",
         "created_at": r.get("created_at") or r.get("submitted_at")}
        for r in records[:10]
    ]
    recent = sorted(recent_learning + recent_answers, key=lambda x: x.get("created_at") or "", reverse=True)[:5]

    return {
        "total_count": len(records) + len(answer_records),
        "answer_count": len(answer_records),
        "answer_correct_rate": round(answer_correct / len(answer_records) * 100, 1) if answer_records else 0,
        "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "total_duration_seconds": total_duration,
        "weak_points": weak_points,
        "recent_records": recent,
    }
