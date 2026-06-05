from __future__ import annotations
"""LLM-based semantic grading for non-multiple-choice questions."""

from typing import Optional, Union

import json
import logging
from uuid import UUID

from app.core.errors import ErrorCode, ServiceError
from app.services.model_gateway import generate_json

logger = logging.getLogger(__name__)

_GRADING_PROMPT = """你是一个专业的学习评估系统。请对比学生的答案和标准答案，给出评分和反馈。

## 题目信息
- 题目类型: {question_type}
- 题干: {stem}
- 标准答案: {standard_answer}
- 解析: {explanation}

## 学生答案
{user_answer}

## 评分要求
请以JSON格式返回:
{{
  "score": 0-100的整数,
  "is_correct": true/false（60分及以上为true）,
  "feedback": "具体的反馈和改进建议，不超过100字",
  "key_points_hit": ["学生答对的关键点"],
  "key_points_missed": ["学生遗漏的关键点"]
}}"""


def grade_answer(
    question_type: str,
    stem: str,
    standard_answer: Union[str, dict, list],
    user_answer: Union[str, dict, list],
    explanation: Optional[str] = None,
) -> dict:
    """Grade a user answer against a standard answer using LLM semantic comparison.

    For choice questions, uses exact match.
    For all other types (blank, short_answer, programming, case_analysis), uses LLM.
    Falls back to 50% credit if LLM grading fails (ported from OpenMAIC pattern).
    """
    if question_type == "choice":
        return _grade_exact(standard_answer, user_answer)

    ans_str = json.dumps(standard_answer, ensure_ascii=False) if not isinstance(standard_answer, str) else standard_answer
    user_str = json.dumps(user_answer, ensure_ascii=False) if not isinstance(user_answer, str) else user_answer

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("grading_semantic_v1", _GRADING_PROMPT, {
        "question_type": question_type,
        "stem": stem,
        "standard_answer": ans_str,
        "user_answer": user_str,
        "explanation": explanation or "无",
    })

    try:
        result = generate_json(prompt, required_keys=["score", "is_correct", "feedback"])
        if "_model_mode" in result:
            raise ServiceError(ErrorCode.GRADING_FAILED, f"评分服务降级: {result['_model_mode']}")
        result["score"] = max(0, min(100, int(result.get("score", 0))))
        result["is_correct"] = result["score"] >= 60
        result["_grading_method"] = "llm_semantic"
        return result
    except (ServiceError, Exception) as exc:
        # Fallback: give 50% credit when LLM grading fails (OpenMAIC pattern)
        return {
            "score": 50,
            "is_correct": False,
            "feedback": "AI 评分暂时不可用，已给出基础分。请参考标准答案自行对照。",
            "key_points_hit": [],
            "key_points_missed": [],
            "_grading_method": "fallback",
            "_grading_error": str(exc),
        }


def _grade_exact(standard_answer: Union[str, dict, list], user_answer: Union[str, dict, list]) -> dict:
    """Exact match grading for multiple-choice questions."""
    s = str(standard_answer).strip().upper()
    u = str(user_answer).strip().upper()
    correct = s == u
    return {
        "score": 100 if correct else 0,
        "is_correct": correct,
        "feedback": "回答正确！" if correct else f"正确答案是 {standard_answer}",
        "key_points_hit": [str(standard_answer)] if correct else [],
        "key_points_missed": [] if correct else [str(standard_answer)],
        "_grading_method": "exact",
    }


def grade_and_record(
    user_id: UUID,
    question_id: str,
    question_type: str,
    stem: str,
    standard_answer: Union[str, dict, list],
    user_answer: Union[str, dict, list],
    explanation: Optional[str] = None,
    time_spent_seconds: Optional[int] = None,
    knowledge_point: Optional[str] = None,
    conversation_id: Optional[UUID] = None,
) -> dict:
    """Grade an answer and save the record to the database."""
    from app.services.resource_library import save_answer_record

    result = grade_answer(question_type, stem, standard_answer, user_answer, explanation)

    record = save_answer_record({
        "user_id": user_id,
        "question_id": question_id,
        "user_answer": user_answer if isinstance(user_answer, dict) else {"answer": user_answer},
        "is_correct": result["is_correct"],
        "score": result["score"],
        "grading_method": result.get("_grading_method", "exact"),
        "grading_detail": result,
        "time_spent_seconds": time_spent_seconds,
    })

    # IRT ability estimation update (fire-and-forget)
    try:
        from app.services.irt_service import estimate_ability, ItemParams
        from app.repositories.vertical_loop_repository import repository as _repo
        # Get recent answers for this user to estimate ability
        recent_answers = _repo.get_user_answer_history(user_id, limit=20)
        responses = [{"question_id": str(a.get("question_id", "")), "is_correct": bool(a.get("is_correct"))} for a in recent_answers]
        ability = estimate_ability(responses, {})
        # Store ability estimate in profile event
        if knowledge_point and ability.n_items >= 3:
            from app.services.profile_event_service import ProfileEventType, emit_event
            emit_event(user_id, ProfileEventType.CONVERSATION_BEHAVIOR, {
                "knowledge_point": knowledge_point,
                "irt_theta": round(ability.theta, 3),
                "irt_se": round(ability.se, 3),
                "irt_items": ability.n_items,
            }, confidence=0.6)
    except Exception:
        logger.debug("IRT ability estimation failed", exc_info=True)

    # 画像反馈闭环：答题后更新四维度 + 创建学习记录
    if knowledge_point:
        try:
            from app.services.profile_service import get_profile
            from app.services.profile_eval_service import evaluate_knowledge_point
            from app.services.profile_event_service import ProfileEventType, emit_event
            from app.services.learning_record_service import create_learning_record
            from app.schemas.learning_record import LearningRecordCreate

            profile = get_profile(user_id, conversation_id=conversation_id)
            if profile:
                quiz_accuracy = result["score"] / 100.0
                dim = evaluate_knowledge_point(
                    profile, knowledge_point,
                    quiz_accuracy=quiz_accuracy, total_questions=1,
                )
                emit_event(user_id, ProfileEventType.EXERCISE_GRADE, {"knowledge_point": knowledge_point, "dimension": dim.model_dump()}, confidence=0.7)

            # 创建学习记录（含错题要点）
            key_points_missed = result.get("key_points_missed") or []
            create_learning_record(LearningRecordCreate(
                user_id=user_id,
                knowledge_point=knowledge_point,
                resource_type="quiz",
                score=result["score"],
                duration_seconds=time_spent_seconds or 0,
                wrong_points=[kp for kp in key_points_missed if isinstance(kp, str)],
                feedback=result.get("feedback"),
            ), conversation_id=conversation_id, skip_event=True)
        except Exception:
            logger.exception("Failed to persist learning record for user=%s kp=%s", user_id, knowledge_point)
            return {**result, "record_id": record["id"], "record_persisted": False}

    return {**result, "record_id": record["id"], "record_persisted": True}
