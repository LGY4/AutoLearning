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
    PRACTICE = "practice"
    LEARNING_MAP = "learning_map"
    VIDEO_GENERATION = "video_generation"
    MEDIA_GENERATION = "media_generation"
    DASHBOARD = "dashboard"
    RESOURCE_BROWSE = "resource_browse"
    COURSE_GOAL = "course_goal"
    ANALYTICS = "analytics"
    WELCOME = "welcome"


# Stage 1: keyword rules — order matters, first match wins
# More specific intents MUST come before broader ones to avoid false matches.
# Tutoring is the DEFAULT intent (not listed here) — any unmatched message
# goes to tutoring without an LLM call. Only non-tutoring intents have keywords.
_KEYWORD_RULES: List[tuple[Intent, List[str]]] = [
    # Specific intents first (before broader ones)
    (Intent.PRACTICE, [
        "刷题", "练题", "做练习", "练习一下", "做几道题", "出几道题",
    ]),
    (Intent.LEARNING_MAP, [
        "学习地图", "知识图谱", "知识地图", "看看图", "图谱",
    ]),
    (Intent.VIDEO_GENERATION, [
        "生成视频", "知识视频", "教学视频", "视频教程", "视频生成", "一个视频",
    ]),
    (Intent.MEDIA_GENERATION, [
        "生成动画", "生成图片", "图片生成", "动画生成", "一个动画",
    ]),
    (Intent.DASHBOARD, [
        "学习看板", "学习统计", "学习数据", "看板", "学习情况",
    ]),
    (Intent.ANALYTICS, [
        "学习分析", "学习趋势", "学习效率", "学习时间线", "掌握趋势",
    ]),
    (Intent.RESOURCE_BROWSE, [
        "浏览资源", "资源列表", "我的资源", "资源库",
    ]),
    (Intent.COURSE_GOAL, [
        "学习目标", "课程目标", "设定目标", "我的目标",
    ]),
    # Broader intents after specific ones
    (Intent.EXERCISE, [
        "练习", "习题", "做题", "测试题", "编程题", "quiz",
        "给我出题", "练一练", "考考我",
    ]),
    (Intent.ASSESSMENT, [
        "评估", "测评", "掌握程度", "薄弱", "水平",
        "我学得怎样", "我掌握", "评估一下", "看看我的", "学了多少",
        "进度", "学习报告",
    ]),
    (Intent.LEARNING_PATH, [
        "学习路径", "学习计划", "学习路线", "规划", "路线图",
        "怎么学", "从哪学", "学习顺序", "先学什么", "推荐学",
        "path", "plan", "roadmap",
    ]),
    # RESOURCE_GENERATION trigger words — these are broad ("做一个", "来一个")
    # and must co-occur with a resource-type keyword to avoid false positives
    # like "来一个例子" or "帮我做一个链表".
    (Intent.RESOURCE_GENERATION, [
        "生成", "给我一份", "帮我生成", "帮我制作", "创建一份",
        "制作一个", "做一个", "做一份", "来一份", "来一个",
        "出一份", "出一个",
        "resource", "generate", "document", "video", "animation",
        "PPT", "ppt", "课件",
    ]),
]

# Resource-type keywords — must co-occur with broad triggers above
_RESOURCE_TYPE_KEYWORDS = [
    "文档", "资料", "资源", "课件", "PPT", "ppt", "视频", "动画",
    "思维导图", "脑图", "流程图", "代码示例", "阅读材料", "学习材料",
    "讲义", "教案", "试卷", "报告", "总结", "笔记", "知识卡片",
    "markdown", "document", "video", "animation", "slides", "resource",
]

# Broad trigger words that need resource-type context to match RESOURCE_GENERATION
_RESOURCE_TRIGGERS_NEED_CONTEXT = {"做一个", "做一份", "来一份", "来一个", "出一份", "出一个", "制作一个"}


def _keyword_match(text: str) -> Optional[Intent]:
    """Stage 1: fast keyword matching. Returns None if ambiguous."""
    text_lower = text.lower()
    for intent, keywords in _KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in text_lower:
                # RESOURCE_GENERATION: broad triggers require resource-type
                # context to avoid matching casual requests like "来一个例子"
                if intent == Intent.RESOURCE_GENERATION and kw in _RESOURCE_TRIGGERS_NEED_CONTEXT:
                    has_resource_type = any(rt.lower() in text_lower for rt in _RESOURCE_TYPE_KEYWORDS)
                    if not has_resource_type:
                        continue  # skip — no resource-type context, let LLM classify
                return intent
    return None


# Public alias — callers should use this instead of _keyword_match
keyword_match = _keyword_match


def _parse_resource_types(message: str) -> list:
    """Extract resource types from user message. Default to document+quiz."""
    from app.core.enums import ResourceType
    msg = message.lower()
    type_map = {
        "文档": ResourceType.DOCUMENT, "document": ResourceType.DOCUMENT, "资料": ResourceType.DOCUMENT,
        "讲义": ResourceType.DOCUMENT, "笔记": ResourceType.DOCUMENT,
        "测验": ResourceType.QUIZ, "quiz": ResourceType.QUIZ, "题目": ResourceType.QUIZ,
        "练习": ResourceType.QUIZ, "习题": ResourceType.QUIZ,
        "思维导图": ResourceType.MINDMAP, "脑图": ResourceType.MINDMAP, "mindmap": ResourceType.MINDMAP,
        "流程图": ResourceType.FLOWCHART, "flowchart": ResourceType.FLOWCHART,
        "视频": ResourceType.VIDEO, "video": ResourceType.VIDEO,
        "动画": ResourceType.ANIMATION, "animation": ResourceType.ANIMATION,
        "代码": ResourceType.CODE_CASE, "code": ResourceType.CODE_CASE, "示例": ResourceType.CODE_CASE,
        "阅读": ResourceType.READING, "reading": ResourceType.READING, "材料": ResourceType.READING,
    }
    found = []
    for keyword, rt in type_map.items():
        if keyword in msg and rt not in found:
            found.append(rt)
    return found if found else [ResourceType.DOCUMENT, ResourceType.QUIZ]


_LLM_CLASSIFY_PROMPT = """\
你是意图分类器。根据用户消息，判断其意图类别。

可选类别：
- tutoring: 问答、解释概念、请教问题
- resource_generation: 要求生成文档、视频、动画、图片、代码等学习资源
- learning_path: 规划、查看、调整学习路径/计划
- assessment: 评估学习掌握程度、查看学习报告、分析薄弱点
- exercise: 要求出题、做练习、刷题、编程挑战
- practice: 刷题、专项练习、做练习题
- learning_map: 查看知识图谱、学习地图
- video_generation: 生成教学视频、知识视频
- media_generation: 生成动画、图片
- dashboard: 查看学习统计、学习看板
- resource_browse: 浏览资源库、查看已有资源
- course_goal: 设定学习目标、管理课程
- analytics: 学习分析、学习趋势、学习效率、知识掌握变化
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
    except Exception as exc:
        logger.warning("LLM intent classification failed, degrading to GENERAL_CHAT: %s", exc)
        return Intent.GENERAL_CHAT, 0.3


def detect_intent(message: str) -> tuple[Intent, float, str]:
    """Two-stage intent detection.

    Returns (intent, confidence, method) where method is 'keyword' or 'llm'.
    """
    # Stage 1: keyword (non-tutoring intents only)
    intent = _keyword_match(message)
    if intent is not None:
        return intent, 0.95, "keyword"

    # Stage 2: LLM classification for ambiguous messages
    try:
        intent, confidence = _llm_classify(message)
        return intent, confidence, "llm"
    except Exception:
        logger.debug("LLM intent classification failed, defaulting to tutoring", exc_info=True)
        return Intent.TUTORING, 0.7, "default"


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
                    metadata={
                        "knowledge_point": result.get("knowledge_point"),
                        "intent_result": {
                            "intent": "tutoring", "confidence": confidence, "method": method,
                            "result": {
                                "quiz_pending": True,
                                "question": result.get("question"),
                                "knowledge_point": result.get("knowledge_point"),
                                "original_question": result.get("original_question"),
                                "quiz_session": result.get("quiz_session"),
                                "is_known_kp": result.get("is_known_kp", False),
                                "is_post_test": result.get("is_post_test", False),
                            },
                        },
                    },
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
                metadata={
                    "rag_references": result.get("rag_references", []),
                    "intent_result": {
                        "intent": "tutoring", "confidence": confidence, "method": method,
                        "result": {
                            "answer": result.get("answer", ""),
                            "markdown": result.get("markdown", ""),
                            "rag_references": result.get("rag_references", []),
                            "next_step": result.get("next_step"),
                            "knowledge_point": result.get("knowledge_point"),
                            "videos": result.get("videos", []),
                        },
                    },
                },
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
            changes = update.get("changes", {})
            if changes:
                result["changes"] = changes
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
                metadata={
                    "resource_id": str(resource.resource_id),
                    "intent_result": {
                        "intent": "exercise", "confidence": confidence, "method": method,
                        "result": {
                            "title": resource.title,
                            "content": resource.content,
                            "knowledge_point": resource.knowledge_point,
                            "resource_type": resource.resource_type.value if hasattr(resource.resource_type, "value") else str(resource.resource_type),
                            "difficulty": resource.difficulty,
                        },
                    },
                },
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
            nodes_data = [{"knowledge_point": n.knowledge_point, "status": n.status.value if hasattr(n.status, "value") else str(n.status), "order": n.order} for n in path.nodes]
            conversation_service.append_message(
                user_id, role="assistant", content=f"已生成学习路径：{path.title}",
                conversation_id=session.conversation_id, intent="learning_path",
                metadata={
                    "path_id": str(path.path_id),
                    "intent_result": {
                        "intent": "learning_path", "confidence": confidence, "method": method,
                        "result": {"title": path.title, "nodes": nodes_data},
                    },
                },
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": path.model_dump(mode="json"),
                "conversation_id": str(session.conversation_id),
            }

        elif intent == Intent.RESOURCE_GENERATION:
            # Intelligent resource generation: profile → strategy → generate
            from app.services import resource_service, adaptive_service
            from app.schemas.resource import ResourceGenerateRequest
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="resource_generation",
            )
            kp = knowledge_point or message[:30]

            # 1. Get strategy-recommended params from profile + strategy engine
            update = adaptive_service.post_learning_update(
                user_id=user_id, knowledge_point=kp,
                conversation_context=message, conversation_id=conversation_id,
            )
            strategy_types = update.get("recommended_types", [])
            resource_params = update.get("resource_params", {})
            diff_map = {"easy": "easy", "medium": "medium", "hard": "hard"}
            difficulty = diff_map.get(resource_params.get("difficulty", "medium"), "medium")

            # 2. Merge user-requested types with strategy-recommended types
            user_types = _parse_resource_types(message)
            user_type_strs = {t.value for t in user_types}
            # User-specified types take priority, then add strategy recommendations
            merged_types = list(user_types)
            from app.core.enums import ResourceType
            for rt in strategy_types:
                if rt not in user_type_strs:
                    try:
                        merged_types.append(ResourceType(rt))
                    except ValueError:
                        pass
            if not merged_types:
                merged_types = [ResourceType.DOCUMENT, ResourceType.QUIZ]

            # 3. Generate resources with intelligent parameters
            req = ResourceGenerateRequest(
                user_id=user_id,
                subject=kp,
                knowledge_point=kp,
                resource_types=merged_types,
                difficulty=difficulty,
            )
            result = resource_service.generate_resources(req)
            conversation_service.append_message(
                user_id, role="assistant",
                content=f"已围绕「{kp}」生成 {len(result.resources)} 份学习资源。",
                conversation_id=session.conversation_id, intent="resource_generation",
                metadata={
                    "intent_result": {
                        "intent": "resource_generation", "confidence": confidence, "method": method,
                        "result": {
                            "resources": [r.model_dump(mode="json") for r in result.resources],
                            "status": result.status,
                        },
                    },
                },
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": {
                    "resources": [r.model_dump(mode="json") for r in result.resources],
                    "status": result.status,
                    "conversation_id": str(session.conversation_id),
                },
                "conversation_id": str(session.conversation_id),
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
                metadata={
                    "intent_result": {
                        "intent": "assessment", "confidence": confidence, "method": method,
                        "result": {
                            "mastery_score": result.get("mastery_score") if isinstance(result, dict) else None,
                            "weak_points": result.get("weak_points", []) if isinstance(result, dict) else [],
                            "next_suggestions": result.get("next_suggestions", []) if isinstance(result, dict) else [],
                            "summary": summary,
                        },
                    },
                },
            )
            return {
                "intent": intent.value,
                "confidence": confidence,
                "method": method,
                "result": result,
                "conversation_id": str(session.conversation_id),
            }

        elif intent in (Intent.PRACTICE, Intent.EXERCISE):
            # Practice/Exercise — generate quiz questions
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="practice",
            )
            from app.services import agent_runtime
            from app.core.enums import ResourceType
            kp = knowledge_point or message[:30]
            try:
                resource = agent_runtime.build_learning_resource(
                    user_id=user_id, subject=kp, knowledge_point=kp,
                    resource_type=ResourceType.QUIZ, difficulty="medium", profile=None,
                )
                questions = []
                try:
                    import json as _json
                    quiz_data = _json.loads(resource.content)
                    questions = quiz_data.get("questions", [])
                except Exception:
                    questions = [{"question": resource.content, "type": "open_ended"}]
                result_data = {"questions": questions, "knowledge_point": kp, "title": resource.title}
            except Exception:
                result_data = {"questions": [], "knowledge_point": kp, "error": "题目生成失败"}
            conversation_service.append_message(
                user_id, role="assistant", content=f"已为「{kp}」生成练习题。",
                conversation_id=session.conversation_id, intent="practice",
                metadata={"intent_result": {"intent": "practice", "confidence": confidence, "method": method, "result": result_data}},
            )
            return {"intent": "practice", "confidence": confidence, "method": method, "result": result_data, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.LEARNING_MAP:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="learning_map",
            )
            try:
                from app.services.graph_service import get_graph_with_path_status
                graph_data = get_graph_with_path_status(user_id)
                result_data = {"nodes": graph_data.get("nodes", []), "edges": graph_data.get("edges", []), "path_info": graph_data.get("path_info")}
            except Exception:
                result_data = {"nodes": [], "edges": [], "error": "加载知识图谱失败"}
            conversation_service.append_message(
                user_id, role="assistant", content="以下是你的学习地图。",
                conversation_id=session.conversation_id, intent="learning_map",
                metadata={"intent_result": {"intent": "learning_map", "confidence": confidence, "method": method, "result": result_data}},
            )
            return {"intent": "learning_map", "confidence": confidence, "method": method, "result": result_data, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.DASHBOARD:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="dashboard",
            )
            from app.services import profile_service, recommendation_service
            profile = profile_service.get_profile(user_id)
            recs = recommendation_service.get_recommendations(user_id)
            profile_data = profile.model_dump(mode="json") if profile else {}
            recs_data = [r.model_dump(mode="json") for r in recs] if recs else []
            result_data = {"profile": profile_data, "recommendations": recs_data}
            conversation_service.append_message(
                user_id, role="assistant", content="以下是你的学习看板。",
                conversation_id=session.conversation_id, intent="dashboard",
                metadata={"intent_result": {"intent": "dashboard", "confidence": confidence, "method": method, "result": result_data}},
            )
            return {"intent": "dashboard", "confidence": confidence, "method": method, "result": result_data, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.RESOURCE_BROWSE:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="resource_browse",
            )
            try:
                resources = repository.list_user_resources(user_id)
                result_data = {"resources": resources[:20], "total": len(resources)}
            except Exception:
                result_data = {"resources": [], "total": 0}
            conversation_service.append_message(
                user_id, role="assistant", content=f"找到 {result_data['total']} 份资源。",
                conversation_id=session.conversation_id, intent="resource_browse",
                metadata={"intent_result": {"intent": "resource_browse", "confidence": confidence, "method": method, "result": result_data}},
            )
            return {"intent": "resource_browse", "confidence": confidence, "method": method, "result": result_data, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.VIDEO_GENERATION:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="video_generation",
            )
            kp = knowledge_point or message[:30]
            result_data = {"topic": kp, "status": "pending", "message": f"视频「{kp}」已提交生成，请在知识视频页面查看进度。"}
            conversation_service.append_message(
                user_id, role="assistant", content=result_data["message"],
                conversation_id=session.conversation_id, intent="video_generation",
                metadata={"intent_result": {"intent": "video_generation", "confidence": confidence, "method": method, "result": result_data}},
            )
            return {"intent": "video_generation", "confidence": confidence, "method": method, "result": result_data, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.MEDIA_GENERATION:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="media_generation",
            )
            kp = knowledge_point or message[:30]
            result_data = {"topic": kp, "mode": "animation", "status": "pending", "message": f"动画「{kp}」已提交生成，请在动画图片页面查看进度。"}
            conversation_service.append_message(
                user_id, role="assistant", content=result_data["message"],
                conversation_id=session.conversation_id, intent="media_generation",
                metadata={"intent_result": {"intent": "media_generation", "confidence": confidence, "method": method, "result": result_data}},
            )
            return {"intent": "media_generation", "confidence": confidence, "method": method, "result": result_data, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.ANALYTICS:
            session = conversation_service.append_message(
                user_id, role="user", content=message,
                conversation_id=conversation_id, intent="analytics",
            )
            from app.services import learning_analytics_service
            analytics = learning_analytics_service.compute_analytics(user_id)
            conversation_service.append_message(
                user_id, role="assistant", content="以下是你的学习分析报告。",
                conversation_id=session.conversation_id, intent="analytics",
                metadata={"intent_result": {"intent": "analytics", "confidence": confidence, "method": method, "result": analytics}},
            )
            return {"intent": "analytics", "confidence": confidence, "method": method, "result": analytics, "conversation_id": str(session.conversation_id)}

        elif intent == Intent.WELCOME:
            from app.services import welcome_service
            welcome_data = welcome_service.get_welcome_data(user_id)
            return {"intent": "welcome", "confidence": 1.0, "method": "auto", "result": welcome_data}

        elif intent in (Intent.COURSE_GOAL, Intent.GENERAL_CHAT):
            pass  # fall through to GENERAL_CHAT below

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
                metadata={
                    "intent_result": {
                        "intent": "general_chat", "confidence": confidence, "method": method,
                        "result": {"reply": reply},
                    },
                },
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
    # Build a quiz session from the batch answers and finalize
    questions = quiz.get("questions", []) if isinstance(quiz, dict) else []
    correct_count = 0
    wrong_count = 0
    dimension_results = {}
    for idx, user_answer in answers.items():
        q = questions[idx] if idx < len(questions) else None
        if not q:
            continue
        correct_answer = q.get("answer", "")
        is_correct = str(user_answer).strip().upper() == str(correct_answer).strip().upper()
        if is_correct:
            correct_count += 1
        else:
            wrong_count += 1
        dim_test = q.get("dimension_test", "mastery")
        dim_entry = dimension_results.setdefault(dim_test, {"correct": 0, "total": 0})
        dim_entry["total"] += 1
        if is_correct:
            dim_entry["correct"] += 1

    session = {
        "questions": questions,
        "answers": {str(k): v for k, v in answers.items()},
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "is_known_kp": False,
        "status": "completed",
        "dimension_results": dimension_results,
    }
    result = tutor_service._finalize_quiz(
        user_id=user_id,
        knowledge_point=knowledge_point,
        original_question=question,
        session=session,
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
            "intent_result": {
                "intent": "tutoring", "confidence": 1.0, "method": "quiz_answer",
                "result": {
                    "answer": result.get("answer", ""),
                    "markdown": result.get("markdown", ""),
                    "rag_references": result.get("rag_references", []),
                    "next_step": result.get("next_step"),
                    "knowledge_point": knowledge_point,
                    "videos": result.get("videos", []),
                    "resource_recommendation": result.get("resource_recommendation"),
                    "updated_dimension": result.get("updated_dimension"),
                },
            },
        },
    )

    return {
        "intent": "tutoring",
        "confidence": 1.0,
        "method": "quiz_scored",
        "result": result,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }
