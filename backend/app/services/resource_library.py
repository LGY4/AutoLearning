from __future__ import annotations
"""Personal resource library — list, search, save, delete user resources."""

from typing import List,  Optional

from uuid import UUID

from app.repositories.vertical_loop_repository import repository


def list_user_resources(
    user_id: UUID,
    resource_type: Optional[str] = None,
    subject: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    all_resources = repository.list_user_resources(user_id)
    # Apply filters
    if resource_type:
        all_resources = [r for r in all_resources if r.get("resource_type") == resource_type]
    if subject:
        all_resources = [r for r in all_resources if subject.lower() in (r.get("knowledge_point", "") + r.get("title", "")).lower()]
    if keyword:
        kw = keyword.lower()
        all_resources = [r for r in all_resources if kw in (r.get("title", "") + r.get("knowledge_point", "")).lower()]
    total = len(all_resources)
    start = (page - 1) * page_size
    resources = all_resources[start:start + page_size]
    return {"total": total, "page": page, "page_size": page_size, "resources": resources}


def delete_resource(user_id: UUID, resource_id: UUID) -> bool:
    return repository.delete_resource(user_id, resource_id)


# ── Question Bank ─────────────────────────────────────────────────


def list_questions(
    knowledge_point: Optional[str] = None,
    question_type: Optional[str] = None,
    subject: Optional[str] = None,
    difficulty: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    all_questions = repository.list_questions(knowledge_point, question_type, subject, difficulty)
    total = len(all_questions)
    start = (page - 1) * page_size
    questions = all_questions[start:start + page_size]
    return {"total": total, "page": page, "page_size": page_size, "questions": questions}


def get_question(question_id: UUID) -> Optional[dict]:
    return repository.get_question(question_id)


def save_question(data: dict) -> dict:
    required = ("question_type", "stem")
    for key in required:
        if key not in data or not data[key]:
            raise ValueError(f"Missing required field: {key}")
    return repository.save_question(data)


def delete_question(question_id: UUID) -> bool:
    return repository.delete_question(question_id)


def save_answer_record(data: dict) -> dict:
    return repository.save_answer_record(data)


def get_user_answer_history(user_id: UUID, question_id: Optional[UUID] = None) -> List[dict]:
    return repository.get_user_answer_history(user_id, question_id)
