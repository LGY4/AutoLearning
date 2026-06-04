from __future__ import annotations

from typing import List, Optional, Union

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.resource import (
    AsyncResourceGenerateResponse,
    AsyncTaskStatusResponse,
    LearningResource,
    ResourceGenerateRequest,
)
from app.services import resource_service
from app.services import resource_library
from app.services import grading_service
from app.services import diagnostic_agent


router = APIRouter()


# ── Resource Generation ───────────────────────────────────────────


@router.post("/generate-async", response_model=ApiResponse[AsyncResourceGenerateResponse])
def generate_resources_async(
    payload: ResourceGenerateRequest, current_user: UserDTO = Depends(get_current_user)
) -> ApiResponse[AsyncResourceGenerateResponse]:
    payload.user_id = current_user.id
    return success(resource_service.enqueue_resource_generation(payload))


@router.get("/tasks/{celery_task_id}", response_model=ApiResponse[AsyncTaskStatusResponse])
def get_resource_task_status(
    celery_task_id: str, current_user: UserDTO = Depends(get_current_user)
) -> ApiResponse[AsyncTaskStatusResponse]:
    return success(resource_service.get_async_generation_status(celery_task_id))


class BatchResourceRequest(BaseModel):
    resource_ids: List[UUID]


class QuestionCreate(BaseModel):
    knowledge_point: str
    question_type: str
    stem: str
    options: Union[dict, Optional[list]] = None
    answer: Union[str, dict, Optional[list]] = None
    explanation: Optional[str] = None
    difficulty_level: str = "medium"
    subject: str = ""
    tags: List[str] = []
    status: str = "active"


@router.post("/batch", response_model=ApiResponse[List[LearningResource]])
def batch_get_resources(payload: BatchResourceRequest) -> ApiResponse[List[LearningResource]]:
    if len(payload.resource_ids) > 50:
        raise HTTPException(status_code=400, detail="单次最多查询50个资源")
    resources = []
    for rid in payload.resource_ids:
        r = resource_service.get_resource(rid)
        if r:
            resources.append(r)
    return success(resources)


@router.post("/upload", response_model=ApiResponse[dict])
def upload_resource(
    title: str = Form(...),
    resource_type: str = Form("document"),
    file: UploadFile = File(...),
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    if len(title) > 200:
        raise HTTPException(status_code=400, detail="标题不能超过200字符")
    raw = file.file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过10MB")

    # Try to parse as text for RAG ingestion
    try:
        from app.services.file_parser import parse_uploaded_file
        parsed_content = parse_uploaded_file(file.filename, raw)
    except Exception:
        parsed_content = raw.decode("utf-8", errors="replace")

    content = raw.decode("utf-8", errors="replace")
    resource = resource_service.create_user_resource(
        user_id=current_user.id,
        title=title,
        content=content,
        resource_type=resource_type,
        filename=file.filename or "upload",
    )

    # Ingest into user's RAG knowledge base
    if parsed_content and parsed_content.strip():
        try:
            from app.services.document_ingestion import ingest_document
            ingest_document(
                user_id=current_user.id,
                title=title,
                content=parsed_content,
                subject=resource_type,
                source="resource_upload",
            )
        except Exception:
            pass  # non-blocking

    return success({"resource_id": str(resource.resource_id), "title": resource.title})


# ── Personal Resource Library ─────────────────────────────────────


@router.get("/library", response_model=ApiResponse[dict])
def list_library(
    resource_type: Optional[str] = None,
    subject: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    return success(resource_library.list_user_resources(current_user.id, resource_type, subject, keyword, page, page_size))


@router.delete("/library/{resource_id}", response_model=ApiResponse[dict])
def delete_from_library(resource_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    deleted = resource_library.delete_resource(current_user.id, resource_id)
    return success({"deleted": deleted})


# ── Question Bank ─────────────────────────────────────────────────


@router.get("/questions/list", response_model=ApiResponse[dict])
def list_questions(
    knowledge_point: Optional[str] = None,
    question_type: Optional[str] = None,
    subject: Optional[str] = None,
    difficulty: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse[dict]:
    return success(resource_library.list_questions(knowledge_point, question_type, subject, difficulty, page, page_size))


@router.get("/questions/{question_id}", response_model=ApiResponse[dict])
def get_question(question_id: UUID) -> ApiResponse[dict]:
    q = resource_library.get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return success(q)


@router.post("/questions", response_model=ApiResponse[dict])
def create_question(payload: QuestionCreate) -> ApiResponse[dict]:
    return success(resource_library.save_question(payload.model_dump()))


@router.delete("/questions/{question_id}", response_model=ApiResponse[dict])
def delete_question(question_id: UUID) -> ApiResponse[dict]:
    return success({"deleted": resource_library.delete_question(question_id)})


class QuestionGenerateRequest(BaseModel):
    knowledge_point: str
    subject: str = "通用"
    overall_level: str = "beginner"


@router.post("/questions/generate", response_model=ApiResponse[dict])
def generate_questions(payload: QuestionGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Auto-generate practice questions for a knowledge point and save to question bank."""
    result = diagnostic_agent.generate_knowledge_point_quiz(
        knowledge_point=payload.knowledge_point,
        subject=payload.subject,
        overall_level=payload.overall_level,
    )
    saved = []
    errors = []
    for i, q in enumerate(result.get("questions", [])):
        try:
            saved_q = resource_library.save_question({
                "knowledge_point": payload.knowledge_point,
                "question_type": "choice",
                "stem": q.get("question", ""),
                "options": q.get("options", []),
                "answer": q.get("answer", ""),
                "explanation": q.get("explanation", ""),
                "difficulty_level": {1: "easy", 2: "medium", 3: "hard"}.get(q.get("difficulty", 1), "medium"),
                "subject": payload.subject,
            })
            saved.append(saved_q)
        except Exception as exc:
            errors.append(f"Q{i}: {exc}")
    return success({"generated": len(result.get("questions", [])), "saved": len(saved), "questions": saved, "errors": errors})


# ── Answer Grading ────────────────────────────────────────────────


class GradeRequest(BaseModel):
    question_id: str  # Accept both UUID and generated IDs like "q-0"
    question_type: str
    stem: str
    standard_answer: Union[str, dict, list]
    user_answer: Union[str, dict, list]
    explanation: Optional[str] = None
    time_spent_seconds: Optional[int] = None
    knowledge_point: Optional[str] = None


@router.post("/grade", response_model=ApiResponse[dict])
def grade_answer(payload: GradeRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    result = grading_service.grade_and_record(
        user_id=current_user.id,
        question_id=payload.question_id,
        question_type=payload.question_type,
        stem=payload.stem,
        standard_answer=payload.standard_answer,
        user_answer=payload.user_answer,
        explanation=payload.explanation,
        time_spent_seconds=payload.time_spent_seconds,
        knowledge_point=payload.knowledge_point,
    )
    return success(result)


@router.get("/answers", response_model=ApiResponse[list])
def get_answer_history(question_id: Optional[UUID] = None, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[list]:
    return success(resource_library.get_user_answer_history(current_user.id, question_id))


# ── Resource by ID (must be last — catch-all path param) ──────────


@router.get("/{resource_id}", response_model=ApiResponse[LearningResource])
def get_resource(resource_id: UUID) -> ApiResponse[LearningResource]:
    resource = resource_service.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return success(resource)
