from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import VideoTask
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


class VideoTaskRepository:

    @staticmethod
    def create(
        user_id: UUID,
        task_id: str,
        mode: str,
        topic: str,
        subject: str = "通用",
        style: str = "educational",
    ) -> VideoTask:
        with _safe_session() as db:
            task = VideoTask(
                user_id=user_id,
                task_id=task_id,
                mode=mode,
                status="pending",
                topic=topic,
                subject=subject,
                style=style,
                progress=[],
            )
            db.add(task)
            db.flush()
            db.refresh(task)
            return task

    @staticmethod
    def get_by_task_id(task_id: str) -> Optional[VideoTask]:
        db = SessionLocal()
        try:
            task = db.query(VideoTask).filter(VideoTask.task_id == task_id).first()
            if task:
                db.expunge(task)
            return task
        finally:
            db.close()

    @staticmethod
    def list_by_user(
        user_id: UUID, page: int = 1, page_size: int = 20
    ) -> Tuple[List[VideoTask], int]:
        db = SessionLocal()
        try:
            q = db.query(VideoTask).filter(VideoTask.user_id == user_id)
            total = q.count()
            items = (
                q.order_by(desc(VideoTask.created_at))
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
            task = db.query(VideoTask).filter(VideoTask.task_id == task_id).first()
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
            task = db.query(VideoTask).filter(VideoTask.task_id == task_id).first()
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
                db.query(VideoTask)
                .filter(VideoTask.task_id == task_id, VideoTask.user_id == user_id)
                .first()
            )
            if not task:
                return False
            db.delete(task)
            return True
