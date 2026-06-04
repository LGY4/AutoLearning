from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.core.enums import UserRole
from app.core.response import ApiResponse, success
from app.db.models import Course, LearningGoal
from app.db.session import SessionLocal
from app.schemas.auth import UserDTO

router = APIRouter()
_logger = logging.getLogger(__name__)

# ── JSON-file-backed store ────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_COURSES_FILE = _DATA_DIR / "courses.json"
_GOALS_FILE = _DATA_DIR / "goals.json"


def _read_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _logger.warning("Failed to read %s, treating as empty", path)
        return []


def _write_json(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _seed_courses() -> Dict[str, dict]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seeds = [
        ("数据结构与算法", "计算机科学", "涵盖栈、队列、树、图等基本数据结构及排序、搜索算法", "intermediate"),
        ("Python 编程基础", "编程语言", "Python 语法、数据类型、函数、面向对象编程入门", "beginner"),
        ("线性代数", "数学", "向量、矩阵、线性方程组、特征值与特征向量", "intermediate"),
        ("机器学习导论", "人工智能", "监督学习、无监督学习、模型评估与选择", "advanced"),
        ("操作系统原理", "计算机科学", "进程管理、内存管理、文件系统、并发与同步", "intermediate"),
    ]
    result = {}
    for name, subj, desc, diff in seeds:
        cid = str(uuid4())
        result[cid] = {
            "id": cid, "course_name": name, "subject": subj,
            "description": desc, "difficulty_level": diff,
            "created_by": None, "created_at": now,
        }
    return result


class _JsonBackedStore:
    """Courses and goals persisted as JSON files on disk."""

    def __init__(self) -> None:
        self.courses: Dict[str, dict] = {}
        self.goals: Dict[str, dict] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        rows = _read_json(_COURSES_FILE)
        if rows:
            self.courses = {r["id"]: r for r in rows}
        else:
            self.courses = _seed_courses()
            self._save_courses()

        self.goals = {r["id"]: r for r in _read_json(_GOALS_FILE)}

    def _save_courses(self) -> None:
        _write_json(_COURSES_FILE, list(self.courses.values()))

    def _save_goals(self) -> None:
        _write_json(_GOALS_FILE, list(self.goals.values()))

    # ── Course CRUD ────────────────────────────────────────────────────

    def list_courses(self, subject: Optional[str] = None) -> List[dict]:
        self._ensure_loaded()
        courses = list(self.courses.values())
        if subject:
            courses = [c for c in courses if c.get("subject") == subject]
        courses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return courses

    def get_course(self, course_id: str) -> Optional[dict]:
        self._ensure_loaded()
        return self.courses.get(course_id)

    def create_course(self, data: dict) -> dict:
        self._ensure_loaded()
        cid = data["id"]
        self.courses[cid] = data
        self._save_courses()
        return data

    def update_course(self, course_id: str, fields: dict) -> Optional[dict]:
        self._ensure_loaded()
        record = self.courses.get(course_id)
        if not record:
            return None
        record.update(fields)
        self._save_courses()
        return record

    def delete_course(self, course_id: str) -> bool:
        self._ensure_loaded()
        if course_id not in self.courses:
            return False
        del self.courses[course_id]
        self._save_courses()
        return True

    # ── Goal CRUD ──────────────────────────────────────────────────────

    def list_goals(self, user_id: str) -> List[dict]:
        self._ensure_loaded()
        goals = [g for g in self.goals.values() if g["user_id"] == user_id]
        goals.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return goals

    def get_goal(self, goal_id: str) -> Optional[dict]:
        self._ensure_loaded()
        return self.goals.get(goal_id)

    def create_goal(self, data: dict) -> dict:
        self._ensure_loaded()
        gid = data["id"]
        self.goals[gid] = data
        self._save_goals()
        return data

    def update_goal(self, goal_id: str, fields: dict) -> Optional[dict]:
        self._ensure_loaded()
        record = self.goals.get(goal_id)
        if not record:
            return None
        record.update(fields)
        self._save_goals()
        return record

    def delete_goal(self, goal_id: str) -> bool:
        self._ensure_loaded()
        if goal_id not in self.goals:
            return False
        del self.goals[goal_id]
        self._save_goals()
        return True


_mem = _JsonBackedStore()


def _sync_goal_to_profile(user_id: UUID, goal_title: str, target_course: str = "", target_level: str = "project_practice") -> None:
    """Emit a USER_EDIT event to sync goal changes into the student profile."""
    from app.services.profile_event_service import ProfileEventType, emit_event
    try:
        emit_event(
            user_id,
            ProfileEventType.USER_EDIT,
            {"learning_goal": {"current_goal": goal_title, "target_course": target_course or goal_title, "target_level": target_level}},
            confidence=1.0,
        )
    except Exception:
        pass  # Best effort — goal is still saved in the courses system


def _require_admin(current_user: UserDTO) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="管理员权限不足")


# ── Schemas ──────────────────────────────────────────────────────────────

class CourseCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=200)
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
    deadline: Optional[date] = None


class GoalUpdate(BaseModel):
    goal_title: Optional[str] = None
    goal_description: Optional[str] = None
    target_course_id: Optional[UUID] = None
    target_level: Optional[str] = None
    deadline: Optional[date] = None
    status: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────

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


# ── LearningGoal endpoints (must be before /{course_id} to avoid route conflict) ──

@router.get("/goals", response_model=ApiResponse[dict])
def list_goals(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if SessionLocal is None:
        goals = _mem.list_goals(str(current_user.id))
        return success({"total": len(goals), "goals": goals})
    with SessionLocal() as db:
        rows = db.scalars(
            select(LearningGoal)
            .where(LearningGoal.user_id == current_user.id)
            .order_by(LearningGoal.created_at.desc())
        ).all()
        return success({"total": len(rows), "goals": [_goal_to_dict(r) for r in rows]})


@router.post("/goals", response_model=ApiResponse[dict])
def create_goal(payload: GoalCreate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if SessionLocal is None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": str(uuid4()),
            "user_id": str(current_user.id),
            "goal_title": payload.goal_title,
            "goal_description": payload.goal_description,
            "target_course_id": str(payload.target_course_id) if payload.target_course_id else None,
            "target_level": payload.target_level,
            "deadline": payload.deadline.isoformat() if payload.deadline else None,
            "status": "active",
            "created_at": now,
        }
        result = _mem.create_goal(record)
        _sync_goal_to_profile(current_user.id, payload.goal_title, target_level=payload.target_level or "project_practice")
        return success(result)
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
        db.commit()
        _sync_goal_to_profile(current_user.id, payload.goal_title, target_level=payload.target_level or "project_practice")
        return success(_goal_to_dict(row))


@router.patch("/goals/{goal_id}", response_model=ApiResponse[dict])
def update_goal(goal_id: UUID, payload: GoalUpdate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if SessionLocal is None:
        record = _mem.get_goal(str(goal_id))
        if not record:
            raise HTTPException(404, "学习目标不存在")
        if record["user_id"] != str(current_user.id):
            raise HTTPException(403, "无权修改此学习目标")
        fields = {}
        for field, value in payload.model_dump(exclude_none=True).items():
            if field == "deadline" and value is not None:
                value = value.isoformat() if hasattr(value, "isoformat") else value
            fields[field] = value
        result = _mem.update_goal(str(goal_id), fields)
        if result and payload.goal_title:
            _sync_goal_to_profile(current_user.id, payload.goal_title, target_level=payload.target_level or result.get("target_level", "project_practice"))
        return success(result)
    with SessionLocal() as db:
        row = db.get(LearningGoal, goal_id)
        if not row:
            raise HTTPException(404, "学习目标不存在")
        if row.user_id != current_user.id:
            raise HTTPException(403, "无权修改此学习目标")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        db.flush()
        db.commit()
        updated_title = payload.goal_title or row.goal_title
        _sync_goal_to_profile(current_user.id, updated_title, target_level=payload.target_level or row.target_level or "project_practice")
        return success(_goal_to_dict(row))


@router.delete("/goals/{goal_id}", response_model=ApiResponse[dict])
def delete_goal(goal_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if SessionLocal is None:
        record = _mem.get_goal(str(goal_id))
        if not record:
            raise HTTPException(404, "学习目标不存在")
        if record["user_id"] != str(current_user.id):
            raise HTTPException(403, "无权删除此学习目标")
        _mem.delete_goal(str(goal_id))
        # Sync: use next remaining goal or clear
        remaining = _mem.list_goals(str(current_user.id))
        if remaining:
            _sync_goal_to_profile(current_user.id, remaining[0]["goal_title"], target_level=remaining[0].get("target_level", "project_practice"))
        else:
            _sync_goal_to_profile(current_user.id, "")
        return success({"deleted": True})
    with SessionLocal() as db:
        row = db.get(LearningGoal, goal_id)
        if not row:
            raise HTTPException(404, "学习目标不存在")
        if row.user_id != current_user.id:
            raise HTTPException(403, "无权删除此学习目标")
        db.delete(row)
        db.flush()
        # Sync: use next remaining goal or clear
        remaining = db.scalars(
            select(LearningGoal).where(LearningGoal.user_id == current_user.id).order_by(LearningGoal.created_at.desc()).limit(1)
        ).all()
        if remaining:
            _sync_goal_to_profile(current_user.id, remaining[0].goal_title, target_level=remaining[0].target_level or "project_practice")
        else:
            _sync_goal_to_profile(current_user.id, "")
        db.commit()
        return success({"deleted": True})


# ── Course endpoints ─────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[dict])
def list_courses(
    subject: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ApiResponse[dict]:
    if SessionLocal is None:
        courses = _mem.list_courses(subject)
        total = len(courses)
        start = (page - 1) * page_size
        return success({"total": total, "page": page, "page_size": page_size, "courses": courses[start:start + page_size]})
    with SessionLocal() as db:
        q = select(Course)
        if subject:
            q = q.where(Course.subject == subject)
        total = db.scalar(select(func.count()).select_from(q.subquery()))
        rows = db.scalars(q.order_by(Course.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return success({"total": total, "page": page, "page_size": page_size, "courses": [_course_to_dict(r) for r in rows]})


@router.get("/{course_id}", response_model=ApiResponse[dict])
def get_course(course_id: UUID) -> ApiResponse[dict]:
    if SessionLocal is None:
        record = _mem.get_course(str(course_id))
        if not record:
            raise HTTPException(404, "课程不存在")
        return success(record)
    with SessionLocal() as db:
        row = db.get(Course, course_id)
        if not row:
            raise HTTPException(404, "课程不存在")
        return success(_course_to_dict(row))


@router.post("", response_model=ApiResponse[dict])
def create_course(payload: CourseCreate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    if SessionLocal is None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": str(uuid4()),
            "course_name": payload.course_name,
            "subject": payload.subject,
            "description": payload.description,
            "difficulty_level": payload.difficulty_level,
            "created_by": str(current_user.id),
            "created_at": now,
        }
        return success(_mem.create_course(record))
    with SessionLocal() as db:
        row = Course(
            course_name=payload.course_name,
            subject=payload.subject,
            description=payload.description,
            difficulty_level=payload.difficulty_level,
        )
        db.add(row)
        db.flush()
        db.commit()
        return success(_course_to_dict(row))


@router.patch("/{course_id}", response_model=ApiResponse[dict])
def update_course(course_id: UUID, payload: CourseUpdate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    if SessionLocal is None:
        record = _mem.update_course(str(course_id), payload.model_dump(exclude_none=True))
        if not record:
            raise HTTPException(404, "课程不存在")
        return success(record)
    with SessionLocal() as db:
        row = db.get(Course, course_id)
        if not row:
            raise HTTPException(404, "课程不存在")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        db.flush()
        db.commit()
        return success(_course_to_dict(row))


@router.delete("/{course_id}", response_model=ApiResponse[dict])
def delete_course(course_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    if SessionLocal is None:
        if not _mem.delete_course(str(course_id)):
            raise HTTPException(404, "课程不存在")
        return success({"deleted": True})
    with SessionLocal() as db:
        row = db.get(Course, course_id)
        if not row:
            raise HTTPException(404, "课程不存在")
        db.delete(row)
        db.commit()
        return success({"deleted": True})
