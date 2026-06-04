from __future__ import annotations

from typing import List,  Optional

import logging
from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.services.base_agent_service import get_base_agent
from app.services import agent_runtime, profile_service, rag_service
from app.services.bilibili_service import search_and_summarize

logger = logging.getLogger(__name__)


def _format_video_links(videos: List[dict]) -> str:
    """Format Bilibili video results as markdown links."""
    if not videos:
        return ""
    lines = ["\n\n---\n### 推荐视频\n"]
    for v in videos[:3]:
        title = v.get("title", "视频")
        url = v.get("url", "")
        author = v.get("author", "")
        play = v.get("play", 0)
        duration = v.get("duration", "")
        play_str = f"{play // 10000}万" if play >= 10000 else str(play)
        lines.append(f"- [{title}]({url}) — {author} | {play_str}次播放 | {duration}")
    return "\n".join(lines)


def _build_resource_context(user_id, knowledge_point: str, subject: str) -> str:
    """Build a prompt fragment listing the student's existing resources for this topic."""
    try:
        all_resources = repository.list_user_resources(user_id)
    except Exception:
        return ""

    # Filter by knowledge_point
    kp_lower = (knowledge_point or "").lower()
    matched = [r for r in all_resources if kp_lower and kp_lower in (r.get("knowledge_point", "") or "").lower()]
    if not matched:
        return ""

    TYPE_LABELS = {
        "document": "文档", "mindmap": "思维导图", "quiz": "测验", "reading": "阅读",
        "video": "视频", "animation": "动画", "code_case": "代码实操", "flowchart": "流程图",
    }
    lines = ["\n## 学生已有的学习资源"]
    for r in matched[:5]:
        rtype = TYPE_LABELS.get(r.get("resource_type", ""), r.get("resource_type", ""))
        title = r.get("title", r.get("knowledge_point", ""))
        quality = r.get("quality_score", "")
        quality_str = f"，质量分 {quality}" if quality else ""
        lines.append(f"- [{rtype}] {title}{quality_str}")
    lines.append("\n回答时可引用这些资源，帮助学生在已有材料基础上深入学习。")
    return "\n".join(lines)


def _estimate_question_depth(question: str) -> dict:
    """Analyze question depth to estimate engagement and question type."""
    q = question.strip().lower()
    types: list[str] = []
    engagement = 0.5  # baseline

    # Question type detection
    if any(w in q for w in ["为什么", "why", "原理", "原因"]):
        types.append("why")
        engagement += 0.15
    if any(w in q for w in ["怎么", "如何", "how", "实现", "步骤"]):
        types.append("how")
        engagement += 0.1
    if any(w in q for w in ["区别", "比较", "vs", "versus", "不同"]):
        types.append("compare")
        engagement += 0.1
    if any(w in q for w in ["举例", "例子", "example", "比如"]):
        types.append("example")
        engagement += 0.05
    if any(w in q for w in ["什么是", "是什么", "定义", "what is"]):
        types.append("definition")
    if any(w in q for w in ["代码", "code", "实现", "编程"]):
        types.append("code")

    # Length-based engagement (longer questions tend to be more thoughtful)
    if len(question) > 100:
        engagement += 0.1
    elif len(question) > 50:
        engagement += 0.05

    return {
        "types": types if types else ["general"],
        "engagement": min(round(engagement, 2), 1.0),
    }


def _compute_resource_recommendation(profile, knowledge_point: str, subject: str) -> Optional[dict]:
    """根据画像和掌握度决定是否推荐资源及推荐理由。"""
    if not profile or not knowledge_point:
        return None
    dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
    if dim is None:
        return {
            "knowledge_point": knowledge_point,
            "recommended_types": ["document", "mindmap"],
            "reason": f"「{knowledge_point}」是新知识点，建议先阅读文档和思维导图建立基础概念。",
            "decision": "auto",
            "dimension_summary": {},
        }
    from app.services.strategy_engine import get_resource_params
    style = profile.learning_preference.learning_style if profile.learning_preference else "mixed"
    params = get_resource_params(dim, style)
    score = dim.composite_score

    if score < 0.4:
        decision = "auto"
        reason = f"「{knowledge_point}」掌握度较低（{int(score * 100)}%），建议通过{params['emphasis']}类资源巩固基础。"
    elif score < 0.7:
        decision = "ask"
        reason = f"「{knowledge_point}」掌握度中等（{int(score * 100)}%），是否需要{params['emphasis']}类练习资源来提升？"
    else:
        decision = "silent"
        reason = f"「{knowledge_point}」掌握度良好（{int(score * 100)}%）。"

    return {
        "knowledge_point": knowledge_point,
        "recommended_types": params["resource_types"],
        "reason": reason,
        "decision": decision,
        "dimension_summary": {
            "mastery": dim.mastery,
            "application": dim.application,
            "memory": dim.memory,
            "understanding": dim.understanding,
            "composite_score": round(dim.composite_score, 2),
        },
    }


def answer_question(
    user_id: UUID,
    question: str,
    conversation_id: Optional[UUID] = None,
    knowledge_point: Optional[str] = None,
    base_agent_id: Optional[UUID] = None,
    rag_context: Optional[List[dict]] = None,
) -> dict:
    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    base_agent = get_base_agent(user_id, base_agent_id)
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    query = f"{knowledge_point or ''} {question}".strip()
    references = rag_service.search_knowledge_with_graph(query, subject=subject, top_k=5, profile=profile, user_id=user_id)
    # Merge user-provided RAG context with auto-retrieved references
    if rag_context:
        existing_ids = {r.get("chunk_id") for r in references}
        for ctx in rag_context:
            if ctx.get("chunk_id") not in existing_ids:
                ctx.setdefault("retrieval_engine", "user_provided")
                references.append(ctx)

    # Load conversation history for multi-turn context
    from app.services import conversation_service
    conversation_history: List[dict] = []
    if conversation_id:
        try:
            conv = conversation_service.get_conversation(conversation_id)
            if conv and hasattr(conv, "messages"):
                conversation_history = [
                    {"role": m.role, "content": m.content}
                    for m in conv.messages[-6:]
                ]
        except Exception:
            pass

    draft = agent_runtime.build_tutor_answer(
        profile=profile,
        question=question,
        knowledge_point=knowledge_point,
        subject=subject,
        references=references,
        base_agent=base_agent,
        conversation_history=conversation_history,
    )

    # Auto-search Bilibili videos by knowledge point
    video_keyword = knowledge_point or question
    videos = []
    try:
        videos = search_and_summarize(video_keyword, top_k=3)
    except Exception as exc:
        logger.warning("Bilibili search failed for '%s': %s", video_keyword, exc)

    # Append video links to markdown response
    video_section = _format_video_links(videos)
    markdown = draft.markdown + video_section if video_section else draft.markdown

    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "answer": draft.answer,
        "markdown": markdown,
        "rag_references": references,
        "next_step": draft.next_step,
        "diagram_prompt": draft.diagram_prompt,
        "references": draft.references,
        "question": question,
        "videos": videos,
        "knowledge_point": knowledge_point,
        "resource_recommendation": _compute_resource_recommendation(profile, knowledge_point, subject),
    }


def answer_question_streaming(
    user_id: UUID,
    question: str,
    knowledge_point: Optional[str] = None,
    base_agent_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
    rag_context: Optional[List[dict]] = None,
):
    """Stream tutor answer: yield thinking tokens, then yield structured result dict.

    Yields:
        str tokens during thinking phase
        dict with structured result at the end
    """
    from app.services.model_gateway import generate_stream_with_system

    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    base_agent = get_base_agent(user_id, base_agent_id)
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    kp = knowledge_point or question[:30]

    from app.services import conversation_service

    # Load conversation history BEFORE persisting current message (avoid duplicate in prompt)
    history_text = ""
    if conversation_id:
        try:
            conv = conversation_service.get_conversation(conversation_id)
            if conv and hasattr(conv, "messages"):
                recent = conv.messages[-6:]
                history_lines = [f"{'学生' if m.role == 'user' else 'AI导师'}: {m.content[:200]}" for m in recent]
                history_text = "\n".join(history_lines)
        except Exception:
            pass

    # Persist user message
    session = conversation_service.append_message(
        user_id=user_id,
        role="user",
        content=question,
        conversation_id=conversation_id,
        intent="tutoring",
    )
    actual_conversation_id = session.conversation_id

    # Build context with strategy engine
    from app.services.agent_runtime import _get_teaching_context, _format_strategy_params
    teach_ctx = _get_teaching_context(profile, kp)
    topic_dim = teach_ctx["topic_dimension"]
    overall_level = teach_ctx["overall_level"]
    style = teach_ctx["learning_style"]
    teaching_params = teach_ctx["teaching_params"]
    strategy_instructions = _format_strategy_params(teaching_params, {
        "learning_style": style,
        "topic_dimension": topic_dim,
    })

    query = f"{kp} {question}".strip()
    references = rag_service.search_knowledge_with_graph(query, subject=subject, top_k=5, profile=profile, user_id=user_id)
    # Merge user-provided RAG context
    if rag_context:
        existing_ids = {r.get("chunk_id") for r in references}
        for ctx in rag_context:
            if ctx.get("chunk_id") not in existing_ids:
                ctx.setdefault("retrieval_engine", "user_provided")
                references.append(ctx)
    refs_text = "\n".join(f"- {r.get('title', '')}: {r.get('content', '')[:200]}" for r in references) if references else "无参考内容"

    # Resource context: list student's existing resources for this topic
    resource_context = _build_resource_context(user_id, kp, subject)

    from app.services.prompt_utils import build_prompt
    from app.services.agent_runtime import _apply_base_agent_prompt
    system_prompt = build_prompt(
        "tutor_stream_v2",
        "你是一个个性化学习辅导助手。根据学生画像和参考内容回答问题。\n\n"
        "学生水平：{overall_level}\n学习风格：{style}\n知识点四维度：{topic_dim}\n\n"
        "{strategy_instructions}\n\n"
        "{resource_context}"
        "{history_section}"
        "参考知识库：\n{refs_text}\n\n请详细回答学生的问题。先给出思考过程，然后给出完整解答。",
        {
            "overall_level": overall_level,
            "style": style,
            "topic_dim": topic_dim,
            "strategy_instructions": strategy_instructions,
            "resource_context": resource_context + "\n\n" if resource_context else "",
            "refs_text": refs_text,
            "history_section": f"近期对话记录：\n{history_text}\n\n" if history_text else "",
        },
    )
    system_prompt = _apply_base_agent_prompt(system_prompt, base_agent)

    # Stream thinking tokens
    full_response = []
    for chunk in generate_stream_with_system(system_prompt, question):
        full_response.append(chunk)
        yield chunk

    # After streaming, generate structured metadata
    complete_text = "".join(full_response)

    # Persist assistant response
    conversation_service.append_message(
        user_id=user_id,
        role="assistant",
        content=complete_text,
        conversation_id=actual_conversation_id,
        intent="tutoring",
        metadata={
            "knowledge_point": kp,
            "intent_result": {
                "intent": "tutoring", "confidence": 1.0, "method": "streaming",
                "result": {
                    "markdown": complete_text, "answer": complete_text,
                    "knowledge_point": kp,
                    "rag_references": [{"title": r.get("title", ""), "source": r.get("source", "")} for r in references],
                },
            },
        },
    )

    # Emit conversation behavior event to update profile
    # Analyze question depth from the user's question to estimate engagement
    question_depth = _estimate_question_depth(question)
    try:
        from app.services.profile_event_service import ProfileEventType, emit_event
        emit_event(
            user_id,
            ProfileEventType.CONVERSATION_BEHAVIOR,
            {
                "knowledge_point": kp,
                "engagement_score": question_depth["engagement"],
                "question_types": question_depth["types"],
                "response_length": len(complete_text),
            },
            confidence=0.5,
        )
    except Exception:
        logger.warning("Failed to emit conversation behavior event for kp=%s", kp, exc_info=True)

    # Extract conversation signals and update profile (fire-and-forget)
    try:
        from app.services.conversation_signal_service import extract_and_apply_signals
        extract_and_apply_signals(user_id, question, complete_text, kp, profile)
    except Exception:
        logger.debug("Conversation signal extraction failed for kp=%s", kp, exc_info=True)

    # Trigger adaptive update + strategic resource generation after tutor answer
    try:
        from app.services import adaptive_service
        adaptive_service.post_learning_update(
            user_id=user_id,
            knowledge_point=kp,
            conversation_context=question + "\n" + complete_text[:500],
            conversation_id=actual_conversation_id,
        )
    except Exception:
        logger.debug("Post-learning resource generation failed for kp=%s", kp, exc_info=True)

    videos = []
    try:
        videos = search_and_summarize(kp, top_k=3)
    except Exception:
        logger.warning("Bilibili search failed for '%s'", kp, exc_info=True)

    yield {
        "user_id": str(user_id),
        "answer": complete_text[:200],
        "markdown": complete_text,
        "rag_references": references,
        "question": question,
        "videos": videos,
        "knowledge_point": kp,
        "conversation_id": str(actual_conversation_id),
        "resource_recommendation": _compute_resource_recommendation(profile, kp, subject),
    }


def answer_question_with_callback(
    user_id: UUID,
    question: str,
    on_token: callable,
    knowledge_point: Optional[str] = None,
    base_agent_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
) -> dict:
    """Stream tutor answer with real-time token callback for LangGraph integration.

    Calls on_token(text) for each streaming token, then returns the full result dict.
    """
    result = None
    for item in answer_question_streaming(
        user_id=user_id,
        question=question,
        knowledge_point=knowledge_point,
        base_agent_id=base_agent_id,
        conversation_id=conversation_id,
    ):
        if isinstance(item, str):
            on_token(item)
        elif isinstance(item, dict):
            result = item
    return result or {}


def quiz_before_answer_step1(
    user_id: UUID,
    question: str,
    conversation_id: Optional[UUID] = None,
    knowledge_point: Optional[str] = None,
    base_agent_id: Optional[UUID] = None,
) -> dict:
    """Step 1: Start adaptive quiz. Returns first question if KP is new, or direct answer if known."""
    from app.services import diagnostic_agent

    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    kp = knowledge_point or question[:30]

    # Check if this knowledge point exists in profile
    kp_known = bool(profile and kp in profile.knowledge_profile.topic_dimensions)

    if kp_known:
        # Known KP: generate question at higher difficulty based on current dimension
        current_dim = profile.knowledge_profile.topic_dimensions.get(kp)
        subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
        try:
            q = diagnostic_agent.generate_adaptive_quiz_question(
                knowledge_point=kp,
                subject=subject,
                current_dim=current_dim.model_dump() if current_dim else None,
                correct_count=0,
                wrong_count=0,
                questions_answered=0,
            )
            return {
                "quiz_pending": True,
                "is_known_kp": True,
                "question": q,
                "knowledge_point": kp,
                "original_question": question,
                "quiz_session": {
                    "knowledge_point": kp,
                    "original_question": question,
                    "is_known_kp": True,
                    "questions": [q],
                    "answers": {},
                    "correct_count": 0,
                    "wrong_count": 0,
                    "status": "active",
                    "dimension_results": {},
                },
                "conversation_id": str(conversation_id) if conversation_id else None,
            }
        except Exception:
            logger.warning("Adaptive quiz generation failed for known KP '%s', falling back to direct answer", kp)
            return answer_question(
                user_id, question,
                conversation_id=conversation_id,
                knowledge_point=knowledge_point,
                base_agent_id=base_agent_id,
            )

    # New KP: generate first question at easy difficulty
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    try:
        q = diagnostic_agent.generate_adaptive_quiz_question(
            knowledge_point=kp,
            subject=subject,
            correct_count=0,
            wrong_count=0,
            questions_answered=0,
        )
    except Exception:
        logger.warning("Quiz generation failed for '%s', falling back to direct answer", kp)
        return answer_question(
            user_id, question,
            conversation_id=conversation_id,
            knowledge_point=knowledge_point,
            base_agent_id=base_agent_id,
        )

    return {
        "quiz_pending": True,
        "is_known_kp": False,
        "question": q,
        "knowledge_point": kp,
        "original_question": question,
        "quiz_session": {
            "knowledge_point": kp,
            "original_question": question,
            "is_known_kp": False,
            "questions": [q],
            "answers": {},
            "correct_count": 0,
            "wrong_count": 0,
            "status": "active",
        },
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


def quiz_before_answer_next(
    user_id: UUID,
    answer: str,
    quiz_session: dict,
    knowledge_point: str,
    original_question: str,
    conversation_id: Optional[UUID] = None,
    base_agent_id: Optional[UUID] = None,
) -> dict:
    """Process an answer and return either the next question or final results.

    Termination conditions:
    - User answered wrong → score and return results
    - Reached 5 questions → score and return results
    - User sends 'skip' → score and return results
    """
    from app.services import adaptive_service, diagnostic_agent

    session = dict(quiz_session)
    questions = session.get("questions", [])
    correct_count = session.get("correct_count", 0)
    wrong_count = session.get("wrong_count", 0)
    is_known_kp = session.get("is_known_kp", False)

    # Get current question
    current_q = questions[-1] if questions else None
    if not current_q:
        return _finalize_quiz(user_id, knowledge_point, original_question, session, conversation_id, base_agent_id)

    # Record answer
    qid = current_q["id"]
    session["answers"][qid] = answer
    questions_answered = len(session["answers"])

    # Check skip first — skip is not a correctness judgment
    if answer.strip().lower() == "skip":
        session["status"] = "skipped"
        return _finalize_quiz(user_id, knowledge_point, original_question, session, conversation_id, base_agent_id)

    # Check if answer is correct
    is_correct = answer.strip().upper() == current_q.get("answer", "").strip().upper()
    if is_correct:
        correct_count += 1
        session["correct_count"] = correct_count
    else:
        wrong_count += 1
        session["wrong_count"] = wrong_count

    # Track per-dimension correctness
    dim_test = current_q.get("dimension_test", "mastery")
    dim_results = session.setdefault("dimension_results", {})
    dim_entry = dim_results.setdefault(dim_test, {"correct": 0, "total": 0})
    dim_entry["total"] += 1
    if is_correct:
        dim_entry["correct"] += 1

    if wrong_count > 0:
        session["status"] = "completed_wrong"
        return _finalize_quiz(user_id, knowledge_point, original_question, session, conversation_id, base_agent_id)

    if questions_answered >= 5:
        session["status"] = "completed_max"
        return _finalize_quiz(user_id, knowledge_point, original_question, session, conversation_id, base_agent_id)

    # Generate next question with escalating difficulty
    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    current_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point) if profile else None
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"

    try:
        next_q = diagnostic_agent.generate_adaptive_quiz_question(
            knowledge_point=knowledge_point,
            subject=subject,
            current_dim=current_dim.model_dump() if current_dim else None,
            correct_count=correct_count,
            wrong_count=wrong_count,
            questions_answered=questions_answered,
        )
        questions.append(next_q)
        session["questions"] = questions
        session["status"] = "active"

        return {
            "quiz_pending": True,
            "is_known_kp": is_known_kp,
            "question": next_q,
            "knowledge_point": knowledge_point,
            "original_question": original_question,
            "quiz_session": session,
            "conversation_id": str(conversation_id) if conversation_id else None,
        }
    except Exception:
        logger.warning("Next question generation failed, finalizing quiz")
        session["status"] = "completed_error"
        return _finalize_quiz(user_id, knowledge_point, original_question, session, conversation_id, base_agent_id)


def _finalize_quiz(
    user_id: UUID,
    knowledge_point: str,
    original_question: str,
    session: dict,
    conversation_id: Optional[UUID] = None,
    base_agent_id: Optional[UUID] = None,
) -> dict:
    """Score the quiz, update profile, generate tutor answer."""
    from app.services import adaptive_service, learning_record_service
    from app.schemas.learning_record import LearningRecordCreate

    questions = session.get("questions", [])
    answers = session.get("answers", {})
    correct_count = session.get("correct_count", 0)
    total = len(questions)
    accuracy = correct_count / max(total, 1)
    is_known_kp = session.get("is_known_kp", False)

    # Create learning record for the quiz
    try:
        learning_record_service.create_learning_record(
            LearningRecordCreate(
                user_id=user_id,
                knowledge_point=knowledge_point,
                resource_type="quiz",
                score=round(accuracy * 100),
                wrong_points=[knowledge_point] if accuracy < 0.6 else [],
            ),
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("Failed to create learning record for quiz: %s", exc)

    # Profile update: additive for new KP, overwrite for known KP
    update_result = adaptive_service.post_learning_update(
        user_id=user_id,
        knowledge_point=knowledge_point,
        quiz_result={"accuracy": accuracy, "total": total},
        conversation_id=conversation_id,
        dimension_results=session.get("dimension_results"),
    )
    profile = update_result["updated_profile"]
    resource_params = update_result["resource_params"]

    # Extract updated dimension for frontend profile refresh trigger
    updated_dimension = None
    if profile and knowledge_point:
        dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
        if dim:
            updated_dimension = dim.model_dump()

    # Generate tutor answer
    base_agent = get_base_agent(user_id, base_agent_id)
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    query = f"{knowledge_point or ''} {original_question}".strip()
    references = rag_service.search_knowledge_with_graph(query, subject=subject, top_k=5, profile=profile, user_id=user_id)
    draft = agent_runtime.build_tutor_answer(
        profile=profile,
        question=original_question,
        knowledge_point=knowledge_point,
        subject=subject,
        references=references,
        base_agent=base_agent,
    )

    # Bilibili videos
    videos = []
    try:
        videos = search_and_summarize(knowledge_point or original_question, top_k=3)
    except Exception as exc:
        logger.warning("Bilibili search failed: %s", exc)

    video_section = _format_video_links(videos)
    markdown = draft.markdown + video_section if video_section else draft.markdown

    quiz_result = {
        "accuracy": round(accuracy, 2),
        "correct": correct_count,
        "total": total,
        "status": session.get("status", "completed"),
        "resource_strategy": resource_params,
    }

    return {
        "user_id": str(user_id),
        "conversation_id": str(conversation_id) if conversation_id else None,
        "answer": draft.answer,
        "markdown": markdown,
        "rag_references": references,
        "next_step": draft.next_step,
        "diagram_prompt": draft.diagram_prompt,
        "references": draft.references,
        "question": original_question,
        "videos": videos,
        "quiz_result": quiz_result,
        "resource_strategy": resource_params,
        "recommended_types": update_result["recommended_types"],
        "updated_dimension": updated_dimension,
        "changes": update_result.get("changes", {}),
    }


def generate_post_test(
    user_id: UUID,
    knowledge_point: str,
    conversation_id: Optional[UUID] = None,
) -> dict:
    """Generate a post-learning quiz to verify understanding after tutor answer."""
    from app.services import diagnostic_agent

    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    overall_level = profile.knowledge_profile.overall_level if profile else "beginner"
    dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point) if profile else None

    try:
        q = diagnostic_agent.generate_adaptive_quiz_question(
            knowledge_point=knowledge_point,
            subject=subject,
            current_dim=dim.model_dump() if dim else None,
            correct_count=0,
            wrong_count=0,
            questions_answered=0,
        )
        return {
            "quiz_pending": True,
            "is_post_test": True,
            "question": q,
            "knowledge_point": knowledge_point,
            "quiz_session": {
                "knowledge_point": knowledge_point,
                "original_question": f"学习效果检验：{knowledge_point}",
                "is_known_kp": bool(dim),
                "questions": [q],
                "answers": {},
                "correct_count": 0,
                "wrong_count": 0,
                "status": "active",
                "is_post_test": True,
            },
            "conversation_id": str(conversation_id) if conversation_id else None,
        }
    except Exception as exc:
        logger.warning("Post-test generation failed for '%s': %s", knowledge_point, exc)
        return {"post_test_pending": False, "error": str(exc)}


# ── Post-learning quiz (answer analysis + resource recommendation) ────

def quiz_post_learning_step1(
    user_id: UUID,
    knowledge_point: str,
    conversation_id: Optional[UUID] = None,
    base_agent_id: Optional[UUID] = None,
) -> dict:
    """Start a post-learning quiz. Returns first question based on profile dimensions."""
    from app.services import diagnostic_agent

    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    kp = knowledge_point
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    dim = profile.knowledge_profile.topic_dimensions.get(kp) if profile else None

    # Capture dimension snapshot for before/after comparison
    dim_snapshot = dim.model_dump() if dim else {}

    try:
        q = diagnostic_agent.generate_adaptive_quiz_question(
            knowledge_point=kp,
            subject=subject,
            current_dim=dim.model_dump() if dim else None,
            correct_count=0,
            wrong_count=0,
            questions_answered=0,
        )
    except Exception as exc:
        logger.warning("Post-learning quiz generation failed for '%s': %s", kp, exc)
        return {"quiz_pending": False, "error": str(exc)}

    return {
        "quiz_pending": True,
        "question": q,
        "knowledge_point": kp,
        "quiz_session": {
            "knowledge_point": kp,
            "questions": [q],
            "answers": {},
            "correct_count": 0,
            "wrong_count": 0,
            "status": "active",
            "per_question": [],
            "dimension_snapshot": dim_snapshot,
        },
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


def quiz_post_learning_next(
    user_id: UUID,
    answer: str,
    quiz_session: dict,
    knowledge_point: str,
    conversation_id: Optional[UUID] = None,
) -> dict:
    """Process answer for post-learning quiz. Does NOT terminate on wrong answer."""
    from app.services import diagnostic_agent, grading_service
    from app.services.profile_event_service import ProfileEventType, emit_event

    session = dict(quiz_session)
    questions = session.get("questions", [])
    correct_count = session.get("correct_count", 0)
    wrong_count = session.get("wrong_count", 0)
    per_question = session.get("per_question", [])

    current_q = questions[-1] if questions else None
    if not current_q:
        return _finalize_post_quiz(user_id, knowledge_point, session, conversation_id)

    # Handle skip
    if answer.strip().lower() == "skip":
        session["status"] = "skipped"
        return _finalize_post_quiz(user_id, knowledge_point, session, conversation_id)

    # Grade the answer
    q_type = current_q.get("type", "choice")
    correct_answer = current_q.get("answer", "")
    is_correct = answer.strip().upper() == correct_answer.strip().upper()
    explanation = current_q.get("explanation", "")

    if not is_correct and q_type != "choice":
        # Use LLM semantic grading for non-choice questions
        try:
            grade_result = grading_service.grade_answer(
                question_type=q_type,
                stem=current_q.get("question", ""),
                standard_answer=correct_answer,
                user_answer=answer,
                explanation=explanation,
            )
            is_correct = grade_result.get("is_correct", False)
            explanation = grade_result.get("feedback", explanation)
        except Exception:
            pass

    # Record answer
    qid = current_q.get("id", len(per_question))
    session["answers"][qid] = answer

    if is_correct:
        correct_count += 1
        session["correct_count"] = correct_count
    else:
        wrong_count += 1
        session["wrong_count"] = wrong_count

    # Record per-question data
    dim_test = current_q.get("dimension_test", "mastery")
    per_question.append({
        "question": current_q.get("question", ""),
        "user_answer": answer,
        "correct_answer": correct_answer,
        "is_correct": is_correct,
        "explanation": explanation,
        "dimension_test": dim_test,
        "difficulty": current_q.get("difficulty", 1),
    })
    session["per_question"] = per_question

    # Emit EXERCISE_GRADE event for per-question profile update
    try:
        profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
        if profile:
            dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
            if dim:
                # Compute per-question dimension: correct = boost, wrong = reduce
                per_dim = {dim_test: "mid" if is_correct else "low"}
                emit_event(
                    user_id,
                    ProfileEventType.EXERCISE_GRADE,
                    {
                        "knowledge_point": knowledge_point,
                        "dimension": {**dim.model_dump(), **per_dim},
                        "accuracy": 1.0 if is_correct else 0.0,
                        "total": 1,
                    },
                    confidence=0.5,
                )
    except Exception:
        logger.debug("Per-question profile update failed", exc_info=True)

    # Track dimension results
    dim_results = session.setdefault("dimension_results", {})
    dim_entry = dim_results.setdefault(dim_test, {"correct": 0, "total": 0})
    dim_entry["total"] += 1
    if is_correct:
        dim_entry["correct"] += 1

    questions_answered = len(session["answers"])

    # Return last answer feedback
    last_feedback = {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "explanation": explanation,
    }

    # Termination: 5 questions or skip (NOT wrong answer)
    if questions_answered >= 5:
        session["status"] = "completed_max"
        return _finalize_post_quiz(user_id, knowledge_point, session, conversation_id, last_feedback)

    # Generate next question
    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    current_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point) if profile else None
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"

    try:
        next_q = diagnostic_agent.generate_adaptive_quiz_question(
            knowledge_point=knowledge_point,
            subject=subject,
            current_dim=current_dim.model_dump() if current_dim else None,
            correct_count=correct_count,
            wrong_count=wrong_count,
            questions_answered=questions_answered,
        )
        questions.append(next_q)
        session["questions"] = questions
        session["status"] = "active"

        return {
            "quiz_pending": True,
            "question": next_q,
            "knowledge_point": knowledge_point,
            "quiz_session": session,
            "last_answer_feedback": last_feedback,
            "conversation_id": str(conversation_id) if conversation_id else None,
        }
    except Exception:
        logger.warning("Next question generation failed, finalizing post-quiz")
        session["status"] = "completed_error"
        return _finalize_post_quiz(user_id, knowledge_point, session, conversation_id, last_feedback)


def _finalize_post_quiz(
    user_id: UUID,
    knowledge_point: str,
    session: dict,
    conversation_id: Optional[UUID] = None,
    last_feedback: Optional[dict] = None,
) -> dict:
    """Finalize post-learning quiz: score, update profile, generate resources + next steps."""
    from app.services import adaptive_service, learning_record_service
    from app.schemas.learning_record import LearningRecordCreate

    questions = session.get("questions", [])
    answers = session.get("answers", {})
    correct_count = session.get("correct_count", 0)
    total = len(questions)
    accuracy = correct_count / max(total, 1)
    per_question = session.get("per_question", [])
    dimension_snapshot = session.get("dimension_snapshot", {})

    # Create learning record
    try:
        learning_record_service.create_learning_record(
            LearningRecordCreate(
                user_id=user_id,
                knowledge_point=knowledge_point,
                resource_type="quiz",
                score=round(accuracy * 100),
                wrong_points=[knowledge_point] if accuracy < 0.6 else [],
            ),
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("Failed to create learning record for post-quiz: %s", exc)

    # Final profile update
    update_result = adaptive_service.post_learning_update(
        user_id=user_id,
        knowledge_point=knowledge_point,
        quiz_result={"accuracy": accuracy, "total": total},
        conversation_id=conversation_id,
        dimension_results=session.get("dimension_results"),
    )
    profile = update_result["updated_profile"]
    resource_params = update_result["resource_params"]

    # Compute dimension change
    updated_dim = None
    dimension_change = {}
    if profile and knowledge_point:
        updated_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
        if updated_dim and dimension_snapshot is not None:
            new_dump = updated_dim.model_dump()
            for key in ("mastery", "application", "memory", "understanding"):
                old_val = dimension_snapshot.get(key, "low")
                new_val = new_dump.get(key, "low")
                if old_val != new_val:
                    dimension_change[key] = {"from": old_val, "to": new_val}

    # Resource recommendation
    from app.services.strategy_engine import get_resource_params
    style = profile.learning_preference.learning_style if profile else "mixed"
    res_params = get_resource_params(updated_dim, style) if updated_dim else resource_params
    recommended_types = res_params.get("resource_types", ["document", "quiz"])[:3]

    # Existing resources
    existing_resources = []
    try:
        all_res = repository.list_user_resources(user_id)
        kp_lower = knowledge_point.lower()
        existing_resources = [
            {"id": r.get("id", ""), "title": r.get("title", ""), "resource_type": r.get("resource_type", "")}
            for r in all_res
            if kp_lower in (r.get("knowledge_point", "") or "").lower()
        ][:5]
    except Exception:
        pass

    # Generate next steps via LLM
    next_steps = _generate_next_steps(knowledge_point, accuracy, per_question, profile)

    quiz_result = {
        "accuracy": round(accuracy, 2),
        "correct": correct_count,
        "total": total,
        "per_question": per_question,
    }

    return {
        "quiz_pending": False,
        "quiz_result": quiz_result,
        "updated_dimension": updated_dim.model_dump() if updated_dim else None,
        "dimension_change": dimension_change,
        "last_answer_feedback": last_feedback,
        "resource_recommendation": {
            "knowledge_point": knowledge_point,
            "recommended_types": recommended_types,
            "reason": f"基于你在「{knowledge_point}」的答题表现（正确率 {round(accuracy*100)}%），推荐以下资源类型。",
            "existing_resources": existing_resources,
        },
        "next_steps": next_steps,
        "changes": update_result.get("changes", {}),
    }


def _generate_next_steps(knowledge_point: str, accuracy: float, per_question: list, profile) -> list:
    """Generate next-step recommendations via LLM."""
    from app.services.model_gateway import generate_json as _gen_json

    wrong_dims = [pq["dimension_test"] for pq in per_question if not pq.get("is_correct")]
    wrong_summary = ", ".join(wrong_dims[:3]) if wrong_dims else "无"

    prompt = f"""学生刚完成「{knowledge_point}」的课后练习。
正确率：{round(accuracy*100)}%（{sum(1 for pq in per_question if pq.get('is_correct'))}/{len(per_question)}）
薄弱维度：{wrong_summary}

请给出 2-3 条具体的学习建议，每条不超过 30 字。
返回 JSON：{{"steps": ["建议1", "建议2", "建议3"]}}"""

    try:
        result = _gen_json(prompt, fallback={"steps": []})
        if isinstance(result, dict):
            steps = result.get("steps", [])
            if steps:
                return steps[:3]
    except Exception:
        pass

    # Fallback
    if accuracy >= 0.8:
        return [f"「{knowledge_point}」掌握良好，可以尝试更高难度的练习", "继续学习下一个知识点"]
    elif accuracy >= 0.6:
        return [f"建议回顾「{knowledge_point}」的核心概念", "尝试应用类题目加深理解"]
    else:
        return [f"建议重新学习「{knowledge_point}」的基础知识", "先阅读文档再做练习"]
