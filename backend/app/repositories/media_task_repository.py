from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models import MediaTask
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_PROGRESS_CAP = 200


@contextmanager
def _safe_session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class MediaTaskRepository:

    @staticmethod
    def create(
        user_id: UUID,
        task_id: str,
        media_type: str,
        topic: str,
        subject: str = "",
        params: Optional[dict] = None,
    ) -> MediaTask:
        with _safe_session() as db:
            task = MediaTask(
                user_id=user_id,
                task_id=task_id,
                media_type=media_type,
                status="pending",
                topic=topic,
                subject=subject,
                params=params or {},
                progress=[],
            )
            db.add(task)
            db.flush()
            db.refresh(task)
            return task

    @staticmethod
    def get_by_task_id(task_id: str) -> Optional[MediaTask]:
        db = SessionLocal()
        try:
            task = db.query(MediaTask).filter(MediaTask.task_id == task_id).first()
            if task:
                db.expunge(task)
            return task
        finally:
            db.close()

    @staticmethod
    def list_by_user(
        user_id: UUID, page: int = 1, page_size: int = 20
    ) -> Tuple[List[MediaTask], int]:
        db = SessionLocal()
        try:
            q = db.query(MediaTask).filter(MediaTask.user_id == user_id)
            total = q.count()
            items = (
                q.order_by(desc(MediaTask.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return items, total
        finally:
            db.close()

    @staticmethod
    def update_status(
        task_id: str,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        with _safe_session() as db:
            task = db.query(MediaTask).filter(MediaTask.task_id == task_id).first()
            if not task:
                return
            task.status = status
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error

    @staticmethod
    def append_progress(task_id: str, event: dict) -> None:
        with _safe_session() as db:
            task = db.query(MediaTask).filter(MediaTask.task_id == task_id).first()
            if not task:
                return
            progress = list(task.progress or [])
            progress.append(event)
            if len(progress) > _PROGRESS_CAP:
                progress = progress[-_PROGRESS_CAP:]
            task.progress = progress

    @staticmethod
    def delete(task_id: str, user_id: UUID) -> bool:
        with _safe_session() as db:
            task = (
                db.query(MediaTask)
                .filter(MediaTask.task_id == task_id, MediaTask.user_id == user_id)
                .first()
            )
            if not task:
                return False
            db.delete(task)
            return True
