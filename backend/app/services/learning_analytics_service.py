from __future__ import annotations
"""Learning Analytics Service — computes learning trends, timelines, and efficiency metrics."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def compute_analytics(user_id: UUID) -> dict:
    """Compute comprehensive learning analytics for a user.

    Returns:
        {
            "summary": {total_sessions, total_questions, avg_accuracy, total_minutes},
            "daily_activity": [{date, sessions, questions, accuracy}],
            "topic_mastery": [{topic, score, trend}],
            "dimension_radar": {mastery, application, memory, understanding},
            "efficiency": {questions_per_hour, accuracy_trend, streak_days},
            "recent_events": [{date, type, detail}],
        }
    """
    from app.services import profile_service
    from app.repositories.vertical_loop_repository import repository

    profile = profile_service.get_profile(user_id)
    if not profile:
        return {"error": "暂无学习数据，请先完成入学诊断。"}

    # Topic dimensions
    dims = profile.knowledge_profile.topic_dimensions or {}
    topic_mastery = []
    for name, dim in dims.items():
        score = dim.composite_score
        topic_mastery.append({
            "topic": name,
            "score": round(score, 2),
            "mastery": dim.mastery,
            "application": dim.application,
            "memory": dim.memory,
            "understanding": dim.understanding,
        })
    topic_mastery.sort(key=lambda x: x["score"], reverse=True)

    # Dimension averages
    dim_avg = {"mastery": 0, "application": 0, "memory": 0, "understanding": 0}
    if dims:
        for d in dims.values():
            dim_avg["mastery"] += _level_to_num(d.mastery)
            dim_avg["application"] += _level_to_num(d.application)
            dim_avg["memory"] += _level_to_num(d.memory)
            dim_avg["understanding"] += _level_to_num(d.understanding)
        n = len(dims)
        for k in dim_avg:
            dim_avg[k] = round(dim_avg[k] / n, 2)

    # Learning records
    records = _get_learning_records(user_id)
    daily_activity = _compute_daily_activity(records)
    efficiency = _compute_efficiency(records, profile)
    recent_events = _get_recent_events(user_id)

    # Summary — each record is one session with a score (0-100)
    total_sessions = len(records)
    total_minutes = sum(r.get("duration_seconds", 0) for r in records) / 60
    scores = [r.get("score", 0) for r in records if r.get("score") is not None]
    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "summary": {
            "total_sessions": total_sessions,
            "total_questions": total_sessions,  # each record ≈ one quiz session
            "avg_accuracy": round(avg_score / 100, 2) if avg_score else 0,
            "total_minutes": round(total_minutes, 1),
        },
        "daily_activity": daily_activity[-14:],  # last 14 days
        "topic_mastery": topic_mastery[:10],
        "dimension_radar": dim_avg,
        "efficiency": efficiency,
        "recent_events": recent_events[:10],
        "weak_topics": profile.knowledge_profile.weak_topics or [],
        "known_topics": profile.knowledge_profile.known_topics or [],
        "overall_level": profile.knowledge_profile.overall_level,
    }


def _level_to_num(level: str) -> float:
    return {"high": 1.0, "mid": 0.5, "low": 0.0}.get(level, 0.0)


def _get_learning_records(user_id: UUID) -> List[dict]:
    """Get learning records from repository."""
    try:
        from app.repositories.vertical_loop_repository import repository
        # Try to get records from the repository
        if hasattr(repository, 'list_learning_records'):
            return repository.list_learning_records(user_id)
        # Fallback: construct from profile data
        return []
    except Exception:
        return []


def _compute_daily_activity(records: List[dict]) -> List[dict]:
    """Group records by day and compute daily stats."""
    daily: Dict[str, dict] = defaultdict(lambda: {"sessions": 0, "scores": [], "minutes": 0})

    for r in records:
        date_str = str(r.get("created_at", r.get("date", "")))[:10]
        if not date_str:
            continue
        daily[date_str]["sessions"] += 1
        score = r.get("score")
        if score is not None:
            daily[date_str]["scores"].append(score)
        daily[date_str]["minutes"] += r.get("duration_seconds", 0) / 60

    result = []
    for date_str in sorted(daily.keys()):
        d = daily[date_str]
        scores = d["scores"]
        avg_score = sum(scores) / len(scores) if scores else 0
        result.append({
            "date": date_str,
            "sessions": d["sessions"],
            "questions": d["sessions"],  # each record ≈ one quiz session
            "accuracy": round(avg_score / 100, 2) if avg_score else 0,
            "minutes": round(d["minutes"], 1),
        })
    return result


def _compute_efficiency(records: List[dict], profile) -> dict:
    """Compute learning efficiency metrics."""
    total_sessions = len(records)
    total_minutes = sum(r.get("duration_seconds", 0) for r in records) / 60

    sessions_per_hour = round(total_sessions / (total_minutes / 60), 1) if total_minutes > 0 else 0

    # Accuracy trend (last 5 vs previous 5)
    recent = records[-5:] if len(records) >= 5 else records
    previous = records[-10:-5] if len(records) >= 10 else []

    recent_acc = _avg_accuracy(recent)
    prev_acc = _avg_accuracy(previous)
    accuracy_trend = "up" if recent_acc > prev_acc + 0.05 else ("down" if recent_acc < prev_acc - 0.05 else "stable")

    # Streak days (consecutive days with activity)
    streak = 0
    today = datetime.now().date()
    for i in range(30):
        check_date = today - timedelta(days=i)
        date_str = check_date.isoformat()
        has_activity = any(str(r.get("created_at", r.get("date", "")))[:10] == date_str for r in records)
        if has_activity:
            streak += 1
        elif i > 0:
            break

    return {
        "questions_per_hour": sessions_per_hour,
        "recent_accuracy": round(recent_acc, 2),
        "accuracy_trend": accuracy_trend,
        "streak_days": streak,
    }


def _avg_accuracy(records: List[dict]) -> float:
    """Compute average accuracy from record scores (0-100 → 0-1)."""
    scores = [r.get("score", 0) for r in records if r.get("score") is not None]
    return (sum(scores) / len(scores) / 100) if scores else 0


def _get_recent_events(user_id: UUID) -> List[dict]:
    """Get recent learning events from profile events."""
    try:
        from app.repositories.vertical_loop_repository import repository
        if hasattr(repository, 'list_events_by_type'):
            events = []
            for etype in ["adaptive_quiz", "conversation_behavior", "resource_consumption"]:
                try:
                    evts = repository.list_events_by_type(user_id, etype, limit=5)
                    for e in evts:
                        events.append({
                            "date": str(e.get("created_at", ""))[:10],
                            "type": etype,
                            "detail": str(e.get("event_payload", {}).get("knowledge_point", "")),
                        })
                except Exception:
                    pass
            events.sort(key=lambda x: x["date"], reverse=True)
            return events
    except Exception:
        pass
    return []
