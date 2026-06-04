from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from app.services import model_gateway

logger = logging.getLogger(__name__)


def extract_and_apply_signals(
    user_id: UUID,
    user_message: str,
    ai_response: str,
    knowledge_point: str,
    profile,
) -> None:
    """Extract learning signals from a conversation turn and update the profile."""
    from app.services.profile_event_service import ProfileEventType, emit_event

    try:
        signals = _extract_signals(user_message, ai_response, knowledge_point, profile)
    except Exception as exc:
        logger.debug("Signal extraction failed: %s", exc)
        return

    for sig in signals:
        sig_type = sig.get("signal_type", "")
        confidence = min(max(sig.get("confidence", 0.5), 0.0), 1.0)
        topic = sig.get("topic", "") or knowledge_point

        if confidence < 0.6:
            continue

        if sig_type == "confusion":
            emit_event(
                user_id,
                ProfileEventType.CONVERSATION_BEHAVIOR,
                {
                    "engagement_score": 0.4,
                    "question_types": ["confusion"],
                    "weak_points_add": [topic],
                },
                confidence=confidence,
            )
        elif sig_type == "mastery_confirmed":
            emit_event(
                user_id,
                ProfileEventType.CONVERSATION_BEHAVIOR,
                {
                    "engagement_score": 0.8,
                    "question_types": ["how"],
                    "dimension_boost": {topic: 0.1},
                },
                confidence=confidence,
            )


def _extract_signals(
    user_message: str,
    ai_response: str,
    knowledge_point: str,
    profile,
) -> List[dict]:
    """Use LLM to analyze conversation and extract learning signals."""
    overall_level = profile.knowledge_profile.overall_level if profile else "beginner"
    weak_topics = profile.knowledge_profile.weak_topics if profile else []

    prompt = f"""分析以下师生对话，提取学习信号。

学生水平：{overall_level}
当前知识点：{knowledge_point}
已知薄弱点：{', '.join(weak_topics[:5]) if weak_topics else '无'}

学生消息：{user_message[:500]}
AI回复摘要：{ai_response[:500]}

返回 JSON 格式：
{{"signals": [{{"topic": "知识点名称", "signal_type": "confusion|mastery_confirmed|new_question", "confidence": 0.0-1.0, "evidence": "判断依据"}}]}}

signal_type 说明：
- confusion: 学生表现出困惑、不理解、问"为什么"/"怎么理解"
- mastery_confirmed: 学生确认理解、能正确复述或应用
- new_question: 学生提出新的延伸问题

只返回 JSON，不要其他文字。"""

    try:
        result = model_gateway.generate_json(prompt, fallback='{"signals": []}')
        if isinstance(result, dict):
            return result.get("signals", [])
    except Exception as exc:
        logger.debug("LLM signal extraction failed: %s", exc)

    return []
