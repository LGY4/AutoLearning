from __future__ import annotations

from typing import Optional

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.enums import UserRole
from app.core.response import ApiResponse, success
from app.db.models import Course, LearningGoal
from app.db.session import SessionLocal
from app.schemas.auth import UserDTO

router = APIRouter()


def _require_admin(current_user: UserDTO) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="管理员权限不足")


# ── Schemas ──────────────────────────────────────────────────────────────

class CourseCreate(BaseModel):
    course_name: str
    subject: Optional[str] = None
    description: Optional[str] = None
    difficulty_level: Optional[str] = None


class CourseUpdate(BaseModel):
    course_name: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    difficulty_level: Optional[str] = None


class GoalCreate(BaseModel):
    goal_title: str
    goal_description: Optional[str] = None
    target_course_id: Optional[UUID] = None
    target_level: Optional[str] = None
    deadline: Optional[str] = None


class GoalUpdate(BaseModel):
    goal_title: Optional[str] = None
    goal_description: Optional[str] = None
    target_course_id: Optional[UUID] = None
    target_level: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None


# ── Course endpoints ─────────────────────────────────────────────────────

def _course_to_dict(row: Course) -> dict:
    return {
        "id": str(row.id),
        "course_name": row.course_name,
        "subject": row.subject,
        "description": row.description,
        "difficulty_level": row.difficulty_level,
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("", response_model=ApiResponse[dict])
def list_courses(subject: Optional[str] = None) -> ApiResponse[dict]:
    with SessionLocal() as db:
        q = select(Course)
        if subject:
            q = q.where(Course.subject == subject)
        rows = db.scalars(q.order_by(Course.created_at.desc())).all()
        return success({"total": len(rows), "courses": [_course_to_dict(r) for r in rows]})


# ── LearningGoal endpoints (MUST be before /{course_id} to avoid route conflict) ──

def _goal_to_dict(row: LearningGoal) -> dict:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "goal_title": row.goal_title,
        "goal_description": row.goal_description,
        "target_course_id": str(row.target_course_id) if row.target_course_id else None,
        "target_level": row.target_level,
        "deadline": row.deadline.isoformat() if row.deadline else None,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/goals", response_model=ApiResponse[dict])
def list_goals(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(LearningGoal)
            .where(LearningGoal.user_id == current_user.id)
            .order_by(LearningGoal.created_at.desc())
        ).all()
        return success({"total": len(rows), "goals": [_goal_to_dict(r) for r in rows]})


@router.post("/goals", response_model=ApiResponse[dict])
def create_goal(payload: GoalCreate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    with SessionLocal() as db:
        row = LearningGoal(
            user_id=current_user.id,
            goal_title=payload.goal_title,
            goal_description=payload.goal_description,
            target_course_id=payload.target_course_id,
            target_level=payload.target_level,
            deadline=payload.deadline,
        )
        db.add(row)
        db.flush()
        return success(_goal_to_dict(row))


@router.patch("/goals/{goal_id}", response_model=ApiResponse[dict])
def update_goal(goal_id: UUID, payload: GoalUpdate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    with SessionLocal() as db:
        row = db.get(LearningGoal, goal_id)
        if not row:
            raise HTTPException(404, "学习目标不存在")
        if row.user_id != current_user.id:
            raise HTTPException(403, "无权修改此学习目标")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        db.flush()
        return success(_goal_to_dict(row))


@router.delete("/goals/{goal_id}", response_model=ApiResponse[dict])
def delete_goal(goal_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    with SessionLocal() as db:
        row = db.get(LearningGoal, goal_id)
        if not row:
            raise HTTPException(404, "学习目标不存在")
        if row.user_id != current_user.id:
            raise HTTPException(403, "无权删除此学习目标")
        db.delete(row)
        return success({"deleted": True})


# ── Course CRUD (after /goals routes to avoid route conflict) ──────

@router.get("/{course_id}", response_model=ApiResponse[dict])
def get_course(course_id: UUID) -> ApiResponse[dict]:
    with SessionLocal() as db:
        row = db.get(Course, course_id)
        if not row:
            raise HTTPException(404, "课程不存在")
        return success(_course_to_dict(row))


@router.post("", response_model=ApiResponse[dict])
def create_course(payload: CourseCreate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    with SessionLocal() as db:
        row = Course(
            course_name=payload.course_name,
            subject=payload.subject,
            description=payload.description,
            difficulty_level=payload.difficulty_level,
        )
        db.add(row)
        db.flush()
        return success(_course_to_dict(row))


@router.patch("/{course_id}", response_model=ApiResponse[dict])
def update_course(course_id: UUID, payload: CourseUpdate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    with SessionLocal() as db:
        row = db.get(Course, course_id)
        if not row:
            raise HTTPException(404, "课程不存在")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        db.flush()
        return success(_course_to_dict(row))


@router.delete("/{course_id}", response_model=ApiResponse[dict])
def delete_course(course_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    with SessionLocal() as db:
        row = db.get(Course, course_id)
        if not row:
            raise HTTPException(404, "课程不存在")
        db.delete(row)
        return success({"deleted": True})
