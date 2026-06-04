from __future__ import annotations
"""Welcome Service — generates personalized greeting and daily learning suggestions.

Ties together: profile, recommendations, learning path, analytics, and spaced repetition
into a single "what should I do today" summary.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def get_welcome_data(user_id: UUID) -> dict:
    """Compute welcome panel data: greeting, suggestions, progress, streak.

    Returns:
        {
            "greeting": str,
            "streak_days": int,
            "today_goal": {"target_minutes": 30, "completed_minutes": 0, "progress": 0},
            "weak_topics": [{"topic": str, "score": float, "suggestion": str}],
            "path_progress": {"title": str, "completed": int, "total": int, "next_node": str},
            "review_due": [{"topic": str, "days_since": int}],
            "daily_tip": str,
            "stats_yesterday": {"questions": int, "accuracy": float, "minutes": float},
        }
    """
    from app.services import profile_service, recommendation_service
    from app.repositories.vertical_loop_repository import repository

    profile = profile_service.get_profile(user_id)
    if not profile:
        return {
            "greeting": "欢迎来到智能学习系统！",
            "streak_days": 0,
            "today_goal": {"target_minutes": 30, "completed_minutes": 0, "progress": 0},
            "weak_topics": [],
            "path_progress": None,
            "review_due": [],
            "daily_tip": "完成入学诊断，开启个性化学习之旅。",
            "stats_yesterday": None,
        }

    # Greeting based on time
    hour = datetime.now().hour
    if hour < 12:
        time_greeting = "早上好"
    elif hour < 18:
        time_greeting = "下午好"
    else:
        time_greeting = "晚上好"

    name = profile.basic_info.grade or "同学"
    greeting = f"{time_greeting}，{name}！"

    # Streak calculation
    streak = _compute_streak(user_id)

    # Today's goal progress
    today_minutes = _get_today_minutes(user_id)
    target_minutes = 30  # default daily goal
    today_goal = {
        "target_minutes": target_minutes,
        "completed_minutes": round(today_minutes, 1),
        "progress": min(1.0, today_minutes / target_minutes) if target_minutes > 0 else 0,
    }

    # Weak topics with suggestions
    weak_topics = []
    dims = profile.knowledge_profile.topic_dimensions or {}
    for topic in (profile.knowledge_profile.weak_topics or [])[:3]:
        dim = dims.get(topic)
        score = dim.composite_score if dim else 0
        suggestion = _get_topic_suggestion(score, dim)
        weak_topics.append({"topic": topic, "score": round(score, 2), "suggestion": suggestion})

    # Path progress
    path_progress = None
    try:
        path = repository.get_path(user_id)
        if path and path.nodes:
            completed = sum(1 for n in path.nodes if n.status.value in ("completed", "skipped"))
            total = len(path.nodes)
            next_node = None
            for n in path.nodes:
                if n.status.value == "available":
                    next_node = n.knowledge_point
                    break
                elif n.status.value == "learning":
                    next_node = n.knowledge_point
                    break
            path_progress = {
                "title": path.title,
                "completed": completed,
                "total": total,
                "next_node": next_node,
            }
    except Exception:
        pass

    # Review due (spaced repetition: topics not reviewed in 3+ days)
    review_due = _get_review_due(user_id, profile)

    # Yesterday's stats
    stats_yesterday = _get_yesterday_stats(user_id)

    # Daily tip based on profile
    daily_tip = _generate_daily_tip(profile, weak_topics, streak)

    return {
        "greeting": greeting,
        "streak_days": streak,
        "today_goal": today_goal,
        "weak_topics": weak_topics,
        "path_progress": path_progress,
        "review_due": review_due,
        "daily_tip": daily_tip,
        "stats_yesterday": stats_yesterday,
    }


def _compute_streak(user_id: UUID) -> int:
    """Compute consecutive learning days."""
    from app.repositories.vertical_loop_repository import repository
    try:
        records = _get_learning_records(user_id)
        if not records:
            return 0
        dates = set()
        for r in records:
            d = str(r.get("created_at", r.get("date", "")))[:10]
            if d:
                dates.add(d)
        streak = 0
        today = datetime.now().date()
        for i in range(365):
            check = (today - timedelta(days=i)).isoformat()
            if check in dates:
                streak += 1
            elif i > 0:
                break
        return streak
    except Exception:
        return 0


def _get_today_minutes(user_id: UUID) -> float:
    """Get today's learning minutes."""
    try:
        records = _get_learning_records(user_id)
        today = datetime.now().date().isoformat()
        total = 0
        for r in records:
            d = str(r.get("created_at", r.get("date", "")))[:10]
            if d == today:
                total += r.get("duration_seconds", 0) / 60
        return total
    except Exception:
        return 0


def _get_learning_records(user_id: UUID) -> List[dict]:
    """Get learning records from repository."""
    try:
        from app.repositories.vertical_loop_repository import repository
        if hasattr(repository, 'list_learning_records'):
            return repository.list_learning_records(user_id)
    except Exception:
        pass
    return []


def _get_topic_suggestion(score: float, dim) -> str:
    """Generate suggestion based on topic score and dimensions."""
    if score < 0.3:
        return "建议从基础文档开始，配合思维导图建立概念框架"
    elif score < 0.5:
        return "建议做几道练习题巩固，同时看视频加深理解"
    elif score < 0.7:
        return "建议通过代码实操提升应用能力"
    else:
        return "已掌握较好，可尝试综合题和进阶挑战"


def _get_review_due(user_id: UUID, profile) -> List[dict]:
    """Find topics due for review (not practiced in 3+ days)."""
    try:
        from app.repositories.vertical_loop_repository import repository
        events = repository.list_events_by_type(user_id, "adaptive_quiz", limit=50)
        topic_last_seen: Dict[str, str] = {}
        for evt in events:
            payload = evt.get("event_payload") or {}
            kp = payload.get("knowledge_point", "")
            date = str(evt.get("created_at", ""))[:10]
            if kp and date and kp not in topic_last_seen:
                topic_last_seen[kp] = date

        now = datetime.now().date()
        due = []
        for topic, last_date_str in topic_last_seen.items():
            try:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                days_since = (now - last_date).days
                if days_since >= 3:
                    due.append({"topic": topic, "days_since": days_since})
            except ValueError:
                pass
        due.sort(key=lambda x: x["days_since"], reverse=True)
        return due[:3]
    except Exception:
        return []


def _get_yesterday_stats(user_id: UUID) -> Optional[dict]:
    """Get yesterday's learning stats."""
    try:
        records = _get_learning_records(user_id)
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
        sessions = 0
        scores = []
        minutes = 0
        for r in records:
            d = str(r.get("created_at", r.get("date", "")))[:10]
            if d == yesterday:
                sessions += 1
                if r.get("score") is not None:
                    scores.append(r["score"])
                minutes += r.get("duration_seconds", 0) / 60
        if sessions == 0 and minutes == 0:
            return None
        avg_score = sum(scores) / len(scores) if scores else 0
        return {
            "questions": sessions,
            "accuracy": round(avg_score / 100, 2) if avg_score else 0,
            "minutes": round(minutes, 1),
        }
    except Exception:
        return None


def _generate_daily_tip(profile, weak_topics: list, streak: int) -> str:
    """Generate a personalized daily tip."""
    if streak >= 7:
        return f"已连续学习 {streak} 天，保持节奏！今天可以挑战一个进阶题目。"
    elif streak >= 3:
        return f"连续学习 {streak} 天，坚持就是胜利。今天建议巩固薄弱点。"
    elif weak_topics:
        topic = weak_topics[0]["topic"] if weak_topics else ""
        return f"建议今天重点攻克「{topic}」，从基础概念开始逐步提升。"
    else:
        return "今天可以尝试做一套综合练习，检验学习成果。"
