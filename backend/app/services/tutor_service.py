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


def answer_question(
    user_id: UUID,
    question: str,
    conversation_id: Optional[UUID] = None,
    knowledge_point: Optional[str] = None,
    base_agent_id: Optional[UUID] = None,
) -> dict:
    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
    base_agent = get_base_agent(user_id, base_agent_id)
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    query = f"{knowledge_point or ''} {question}".strip()
    references = rag_service.search_knowledge(query, subject=subject, top_k=2)
    draft = agent_runtime.build_tutor_answer(
        profile=profile,
        question=question,
        knowledge_point=knowledge_point,
        subject=subject,
        references=references,
        base_agent=base_agent,
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
    }


def answer_question_streaming(
    user_id: UUID,
    question: str,
    knowledge_point: Optional[str] = None,
    base_agent_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
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

    # Persist user message
    from app.services import conversation_service
    session = conversation_service.append_message(
        user_id=user_id,
        role="user",
        content=question,
        conversation_id=conversation_id,
        intent="tutoring",
    )
    actual_conversation_id = session.conversation_id

    # Build context
    dim = profile.knowledge_profile.topic_dimensions.get(kp) if profile else None
    topic_dim = dim.model_dump() if dim else {"mastery": "low", "application": "low", "memory": "low", "understanding": "low"}
    overall_level = profile.knowledge_profile.overall_level if profile else "beginner"
    style = profile.learning_preference.learning_style if profile else "mixed"
    query = f"{kp} {question}".strip()
    references = rag_service.search_knowledge(query, subject=subject, top_k=2)
    refs_text = "\n".join(f"- {r.get('title', '')}: {r.get('content', '')[:200]}" for r in references) if references else "无参考内容"

    from app.services.prompt_utils import build_prompt
    system_prompt = build_prompt(
        "tutor_stream_v1",
        "你是一个个性化学习辅导助手。根据学生画像和参考内容回答问题。\n\n"
        "学生水平：{overall_level}\n学习风格：{style}\n知识点四维度：{topic_dim}\n\n"
        "参考知识库：\n{refs_text}\n\n请详细回答学生的问题。先给出思考过程，然后给出完整解答。",
        {"overall_level": overall_level, "style": style, "topic_dim": topic_dim, "refs_text": refs_text},
    )

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
        metadata={"knowledge_point": kp},
    )

    try:
        videos = []
        try:
            videos = search_and_summarize(kp, top_k=3)
        except Exception:
            pass

        yield {
            "user_id": str(user_id),
            "answer": complete_text[:200],
            "markdown": complete_text,
            "rag_references": references,
            "question": question,
            "videos": videos,
            "knowledge_point": kp,
            "conversation_id": str(actual_conversation_id),
        }
    except Exception:
        yield {
            "user_id": str(user_id),
            "answer": complete_text[:200],
            "markdown": complete_text,
            "question": question,
            "conversation_id": str(actual_conversation_id),
        }


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

    # Check if answer is correct
    is_correct = answer.strip().upper() == current_q.get("answer", "").strip().upper()
    if is_correct:
        correct_count += 1
        session["correct_count"] = correct_count
    else:
        wrong_count += 1
        session["wrong_count"] = wrong_count

    # Check termination conditions
    if answer.strip().lower() == "skip":
        session["status"] = "skipped"
        return _finalize_quiz(user_id, knowledge_point, original_question, session, conversation_id, base_agent_id)

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
    from app.services import adaptive_service

    questions = session.get("questions", [])
    answers = session.get("answers", {})
    correct_count = session.get("correct_count", 0)
    total = len(questions)
    accuracy = correct_count / max(total, 1)
    is_known_kp = session.get("is_known_kp", False)

    # Profile update: additive for new KP, overwrite for known KP
    update_result = adaptive_service.post_learning_update(
        user_id=user_id,
        knowledge_point=knowledge_point,
        quiz_result={"accuracy": accuracy, "total": total},
        conversation_id=conversation_id,
    )
    profile = update_result["updated_profile"]
    resource_params = update_result["resource_params"]

    # Generate tutor answer
    base_agent = get_base_agent(user_id, base_agent_id)
    subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用"
    query = f"{knowledge_point or ''} {original_question}".strip()
    references = rag_service.search_knowledge(query, subject=subject, top_k=2)
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
    }


