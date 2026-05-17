from __future__ import annotations
"""MasterAgent — two-stage intent router.

Stage 1: keyword matching (fast, no LLM call)
Stage 2: LLM classification fallback for ambiguous inputs

Routes to 6 intents:
  tutoring          — Q&A, explanations, concept clarification
  resource_generation — generate documents, code, videos, mindmaps
  learning_path     — plan/review/adjust learning paths
  assessment        — evaluate mastery, progress, weak points
  exercise          — practice problems, quizzes, coding challenges
  general_chat      — greeting, off-topic, meta questions
"""

from typing import Dict,  List,  Optional

import json
import logging
from enum import Enum

from app.services import model_gateway

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    TUTORING = "tutoring"
    RESOURCE_GENERATION = "resource_generation"
    LEARNING_PATH = "learning_path"
    ASSESSMENT = "assessment"
    EXERCISE = "exercise"
    GENERAL_CHAT = "general_chat"


# Stage 1: keyword rules — order matters, first match wins
# Tutoring first (most specific question patterns), then others
_KEYWORD_RULES: List[tuple[Intent, List[str]]] = [
    (Intent.TUTORING, [
        "什么是", "怎么理解", "解释一下", "讲一下", "说一下",
        "为什么", "原理是", "区别是", "如何实现", "举例说明",
        "help", "explain", "what is", "how to",
    ]),
    (Intent.EXERCISE, [
        "练习", "习题", "题目", "做题", "刷题", "测试题", "编程题", "quiz",
        "给我出题", "出几道", "做几道", "练一练", "考考我",
    ]),
    (Intent.ASSESSMENT, [
        "评估", "测评", "掌握程度", "学习情况", "薄弱", "水平",
        "我学得怎样", "我掌握", "评估一下", "看看我的", "学了多少",
        "进度", "学习报告",
    ]),
    (Intent.LEARNING_PATH, [
        "学习路径", "学习计划", "学习路线", "规划", "路线图",
        "怎么学", "从哪学", "学习顺序", "先学什么", "推荐学",
        "path", "plan", "roadmap",
    ]),
    (Intent.RESOURCE_GENERATION, [
        "生成", "给我一份", "帮我生成", "帮我制作", "创建一份",
        "制作一个", "做一个", "做一份", "来一份", "来一个",
        "出一份", "出一个",
        "resource", "generate", "document", "video", "animation",
        "PPT", "ppt", "课件",
    ]),
]


def _keyword_match(text: str) -> Optional[Intent]:
    """Stage 1: fast keyword matching. Returns None if ambiguous."""
    text_lower = text.lower()
    for intent, keywords in _KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in text_lower:
                return intent
    return None


_LLM_CLASSIFY_PROMPT = """\
你是意图分类器。根据用户消息，判断其意图类别。

可选类别：
- tutoring: 问答、解释概念、请教问题
- resource_generation: 要求生成文档、视频、动画、图片、代码等学习资源
- learning_path: 规划、查看、调整学习路径/计划
- assessment: 评估学习掌握程度、查看学习报告、分析薄弱点
- exercise: 要求出题、做练习、刷题、编程挑战
- general_chat: 闲聊、打招呼、与学习无关的话题

用户消息：{message}

返回严格 JSON：{{"intent": "类别名", "confidence": 0.0-1.0, "reason": "简短理由"}}
"""


def _llm_classify(message: str) -> tuple[Intent, float]:
    """Stage 2: LLM classification fallback."""
    from app.services.model_gateway import _extract_json_object
    from app.services.prompt_utils import build_prompt

    prompt = build_prompt("intent_classify_v1", _LLM_CLASSIFY_PROMPT, {"message": message})
    try:
        raw = model_gateway.generate_text(prompt)
        obj = _extract_json_object(raw)
        intent_str = obj.get("intent", "general_chat")
        confidence = float(obj.get("confidence", 0.5))
        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.GENERAL_CHAT
        return intent, confidence
    except Exception:
        logger.exception("LLM intent classification failed")
        return Intent.GENERAL_CHAT, 0.3


def detect_intent(message: str) -> tuple[Intent, float, str]:
    """Two-stage intent detection.

    Returns (intent, confidence, method) where method is 'keyword' or 'llm'.
    """
    # Stage 1: keyword
    intent = _keyword_match(message)
    if intent is not None:
        return intent, 0.95, "keyword"

    # Stage 2: LLM fallback
    intent, confidence = _llm_classify(message)
    return intent, confidence, "llm"


# ── Routing dispatch ──────────────────────────────────────────────────────


def route_message(
    user_id,
    message: str,
    conversation_id=None,
    knowledge_point: Optional[str] = None,
    base_agent_id=None,
    model_provider: Optional[str] = None,
) -> dict:
    """Detect intent and dispatch to the appropriate service.

    Returns dict with 'intent', 'confidence', 'method', and 'result'.
    """
    from app.services import conversation_service
    from app.services.model_gateway import ModelOverride, model_override_context

    intent, confidence, method = detect_intent(message)

    override = ModelOverride(provider=model_provider)
    with model_override_context(override):
        if intent == Intent.TUTORING:
            from app.services import tutor_service
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="tutor_question",
                title=knowledge_point or "辅导问答",
            )
            result = tutor_service.quiz_before_answer_step1(
                user_id, message,
                conversation_id=session.conversation_id,
                knowledge_point=knowledge_point,
                base_agent_id=base_agent_id,
            )

            if result.get("quiz_pending"):
                conversation_service.append_message(
                    user_id, role="assistant",
                    content=json.dumps(result.get("question", {}), ensure_ascii=False),
                    conversation_id=session.conversation_id,
                    intent="quiz_pending",
                    metadata={"knowledge_point": result.get("knowledge_point")},
                )
                result["conversation_id"] = str(session.conversation_id)
                return {
                    "intent": intent.value,
                    "confidence": confidence,
                    "method": method,
                    "result": result,
                    "conversation_id": str(session.conversation_id),
                }

            # Normal answer flow (knowledge point already known)
            conversation_service.append_message(
                user_id, role="assistant", content=result.get("markdown", ""),
                conversation_id=session.conversation_id, intent="tutor_answer",
                metadata={"rag_references": result.get("rag_references", [])},
            )
            # Add resource recommendation via adaptive service
            kp = knowledge_point
            if not kp:
                from app.services.intent_parser import parse_intent
                kp = parse_intent(message).knowledge_point
            from app.services import adaptive_service
            update = adaptive_service.post_learning_update(user_id=user_id, knowledge_point=kp, conversation_id=conversation_id)
            result["resource_recommendation"] = {
                "knowledge_point": kp,
                "recommended_types": update["recommended_types"],
                "resource_params": update["resource_params"],
            }
            result["conversation_id"] = str(session.conversation_id)
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": result if isinstance(result, dict) else result.model_dump(mode="json"),
                "conversation_id": str(session.conversation_id),
            }

        elif intent == Intent.EXERCISE:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="exercise",
            )
            from app.services import agent_runtime
            from app.core.enums import ResourceType
            resource = agent_runtime.build_learning_resource(
                user_id=user_id,
                subject=knowledge_point or "通用",
                knowledge_point=knowledge_point or "综合练习",
                resource_type=ResourceType.QUIZ,
                difficulty="medium",
                profile=None,
            )
            conversation_service.append_message(
                user_id, role="assistant", content=f"已生成练习：{resource.title}",
                conversation_id=session.conversation_id, intent="exercise",
                metadata={"resource_id": str(resource.resource_id)},
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": {
                    "resource_id": str(resource.resource_id),
                    "title": resource.title,
                    "content": resource.content,
                    "resource_type": resource.resource_type.value,
                },
                "conversation_id": str(session.conversation_id),
            }

        elif intent == Intent.LEARNING_PATH:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="learning_path",
            )
            from app.services import agent_runtime
            path = agent_runtime.build_learning_path(
                user_id=user_id,
                goal=message,
                subject=knowledge_point or "通用",
                profile=None,
            )
            conversation_service.append_message(
                user_id, role="assistant", content=f"已生成学习路径：{path.title}",
                conversation_id=session.conversation_id, intent="learning_path",
                metadata={"path_id": str(path.path_id)},
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": path.model_dump(mode="json"),
                "conversation_id": str(session.conversation_id),
            }

        elif intent == Intent.RESOURCE_GENERATION:
            # Delegate to learning service for resource generation
            from app.services import learning_service
            from app.schemas.learning import LearningStartRequest
            req = LearningStartRequest(
                user_id=user_id,
                message=message,
                subject=knowledge_point or "通用",
                knowledge_point=knowledge_point,
                model_provider=model_provider,
            )
            result = learning_service.start_learning(req)
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": result.model_dump(mode="json"),
            }

        elif intent == Intent.ASSESSMENT:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="assessment",
            )
            from app.services import assess_agent
            result = assess_agent.assess_learning(user_id)
            summary = result.get("summary", "") if isinstance(result, dict) else ""
            conversation_service.append_message(
                user_id, role="assistant", content=summary or "学习评估完成",
                conversation_id=session.conversation_id, intent="assessment",
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": result,
                "conversation_id": str(session.conversation_id),
            }

        else:  # GENERAL_CHAT
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="general_chat",
            )
            from app.services.prompt_utils import build_prompt as _bp
            reply = model_gateway.generate_text(
                _bp("general_chat_v1", f"你是一个友好的学习助手。请简短回复以下消息（不超过100字）：\n{message}", {"message": message})
            )
            conversation_service.append_message(
                user_id, role="assistant", content=reply,
                conversation_id=session.conversation_id, intent="general_chat_result",
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": {"reply": reply},
                "conversation_id": str(session.conversation_id),
            }


def handle_quiz_answer(
    user_id,
    question: str,
    quiz: dict,
    answers: Dict[int, str],
    knowledge_point: str,
    conversation_id=None,
    base_agent_id=None,
) -> dict:
    """Handle quiz answer submission: score, update profile, generate tutor answer."""
    from app.services import conversation_service, tutor_service

    # Record user's quiz answers in conversation
    answer_summary = "、".join(
        f"第{k}题:{v}" for k, v in sorted(answers.items())
    )
    conversation_service.append_message(
        user_id, role="user", content=f"[测验作答] {answer_summary}",
        conversation_id=conversation_id, intent="quiz_answer",
    )

    # Score quiz + update profile + generate answer
    result = tutor_service.quiz_before_answer_step2(
        user_id=user_id,
        question=question,
        quiz=quiz,
        answers=answers,
        knowledge_point=knowledge_point,
        conversation_id=conversation_id,
        base_agent_id=base_agent_id,
    )

    # Store tutor answer in conversation
    conversation_service.append_message(
        user_id, role="assistant", content=result.get("markdown", ""),
        conversation_id=conversation_id, intent="tutor_answer",
        metadata={
            "rag_references": result.get("rag_references", []),
            "quiz_result": result.get("quiz_result"),
            "resource_strategy": result.get("resource_strategy"),
        },
    )

    return {
        "intent": "tutoring",
        "confidence": 1.0,
        "method": "quiz_scored",
        "result": result,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }
