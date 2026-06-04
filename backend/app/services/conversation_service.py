from __future__ import annotations

import threading
from typing import Dict,  List,  Optional

from uuid import UUID, uuid4

from app.core.config import get_settings
from app.schemas.conversation import ConversationMessage, ConversationSession
from app.services.runtime_support import now_iso


# ── In-memory fallback (for development without DB) ────────────────────────

_sessions: Dict[UUID, ConversationSession] = {}
_user_sessions: Dict[UUID, List[UUID]] = {}
_mem_lock = threading.Lock()
_MAX_SESSIONS = 500
_MAX_MESSAGES_PER_SESSION = 500


def _use_db() -> bool:
    return get_settings().repository_backend == "postgres"


# ── Database operations ────────────────────────────────────────────────────


def _db_ensure_conversation(
    user_id: UUID,
    conversation_id: Optional[UUID] = None,
    title: Optional[str] = None,
    profile_id: Optional[UUID] = None,
    conversation_type: str = "learning",
) -> ConversationSession:
    from sqlalchemy import select
    from app.db.models import ConversationSessionModel
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        if conversation_id:
            row = db.get(ConversationSessionModel, conversation_id)
            if row:
                if row.user_id != user_id:
                    raise ValueError("Conversation does not belong to this user")
                if profile_id:
                    row.profile_id = profile_id
                    db.commit()
                return _session_from_row(row)

        # Auto-snapshot profile for new conversations
        if profile_id is None:
            from app.repositories.vertical_loop_repository import repository
            snapshot = repository.snapshot_profile(user_id)
            profile_id = snapshot.profile_id

        row = ConversationSessionModel(
            id=conversation_id or uuid4(),
            user_id=user_id,
            title=title or "学习画像会话",
            conversation_type=conversation_type,
            profile_id=profile_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _session_from_row(row)


def _db_append_message(
    user_id: UUID,
    role: str,
    content: str,
    conversation_id: Optional[UUID] = None,
    intent: str = "learning",
    metadata: Optional[dict] = None,
    title: Optional[str] = None,
    profile_id: Optional[UUID] = None,
    conversation_type: str = "learning",
) -> ConversationSession:
    from app.db.models import ConversationMessageModel, ConversationSessionModel
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        try:
            # Ensure session exists
            if conversation_id:
                session_row = db.get(ConversationSessionModel, conversation_id)
            else:
                session_row = None

            if not session_row:
                # Auto-snapshot profile for new conversations
                if profile_id is None:
                    from app.repositories.vertical_loop_repository import repository
                    snapshot = repository.snapshot_profile(user_id)
                    profile_id = snapshot.profile_id
                session_row = ConversationSessionModel(
                    id=conversation_id or uuid4(),
                    user_id=user_id,
                    title=title or "学习画像会话",
                    conversation_type=conversation_type,
                    profile_id=profile_id,
                )
                db.add(session_row)
                db.flush()

            if profile_id:
                session_row.profile_id = profile_id

            msg = ConversationMessageModel(
                id=uuid4(),
                session_id=session_row.id,
                user_id=user_id,
                role=role,
                content=content,
                intent=intent,
                metadata_json=metadata or {},
            )
            db.add(msg)
            db.commit()
            db.refresh(session_row)
            return _session_from_row(session_row, db=db)
        except Exception:
            db.rollback()
            raise


def _db_get_conversation(conversation_id: UUID) -> Optional[ConversationSession]:
    from app.db.models import ConversationSessionModel
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        row = db.get(ConversationSessionModel, conversation_id)
        if not row:
            return None
        return _session_from_row(row, db=db)


def _db_list_conversations(user_id: UUID) -> List[ConversationSession]:
    from sqlalchemy import select, desc
    from app.db.models import ConversationSessionModel
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        rows = db.scalars(
            select(ConversationSessionModel)
            .where(ConversationSessionModel.user_id == user_id)
            .order_by(desc(ConversationSessionModel.updated_at))
            .limit(50)
        ).all()
        return [_session_from_row(row, db=db) for row in rows]


def _session_from_row(row, db=None) -> ConversationSession:
    from app.db.models import ConversationMessageModel
    from app.db.session import SessionLocal
    from sqlalchemy import select

    if db is None:
        with SessionLocal() as new_db:
            return _session_from_row(row, db=new_db)

    msg_rows = db.scalars(
        select(ConversationMessageModel)
        .where(ConversationMessageModel.session_id == row.id)
        .order_by(ConversationMessageModel.created_at)
    ).all()

    return ConversationSession(
        conversation_id=row.id,
        user_id=row.user_id,
        title=row.title,
        conversation_type=getattr(row, "conversation_type", "learning") or "learning",
        profile_id=row.profile_id,
        messages=[
            ConversationMessage(
                id=m.id,
                conversation_id=m.session_id,
                user_id=m.user_id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                intent=m.intent,
                metadata=m.metadata_json or {},
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m in msg_rows
        ],
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


# ── Public API (routes to DB or in-memory) ─────────────────────────────────


def ensure_conversation(
    user_id: UUID,
    conversation_id: Optional[UUID] = None,
    title: Optional[str] = None,
    profile_id: Optional[UUID] = None,
    conversation_type: str = "learning",
) -> ConversationSession:
    if _use_db():
        return _db_ensure_conversation(user_id, conversation_id, title, profile_id, conversation_type)

    # In-memory fallback
    with _mem_lock:
        if conversation_id and conversation_id in _sessions:
            session = _sessions[conversation_id]
            if profile_id:
                session.profile_id = profile_id
            return session

        # Auto-snapshot profile for new conversations
        if profile_id is None:
            from app.repositories.vertical_loop_repository import repository
            snapshot = repository.snapshot_profile(user_id)
            profile_id = snapshot.profile_id

        now = now_iso()
        session = ConversationSession(
            conversation_id=conversation_id or uuid4(),
            user_id=user_id,
            title=title or "学习画像会话",
            conversation_type=conversation_type,
            profile_id=profile_id,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        _sessions[session.conversation_id] = session
        _user_sessions.setdefault(user_id, []).insert(0, session.conversation_id)
        # Evict oldest sessions if over limit
        if len(_sessions) > _MAX_SESSIONS:
            oldest_keys = list(_sessions.keys())[: len(_sessions) - _MAX_SESSIONS]
            for k in oldest_keys:
                removed = _sessions.pop(k, None)
                if removed and removed.user_id in _user_sessions:
                    _user_sessions[removed.user_id] = [s for s in _user_sessions[removed.user_id] if s != k]
        return session


def append_message(
    user_id: UUID,
    role: str,
    content: str,
    conversation_id: Optional[UUID] = None,
    intent: str = "learning",
    metadata: Optional[dict] = None,
    title: Optional[str] = None,
    profile_id: Optional[UUID] = None,
    conversation_type: str = "learning",
) -> ConversationSession:
    if _use_db():
        return _db_append_message(user_id, role, content, conversation_id, intent, metadata, title, profile_id, conversation_type)

    # In-memory fallback — hold lock across both ensure + append to prevent TOCTOU race
    now = now_iso()
    with _mem_lock:
        session = _sessions.get(conversation_id) if conversation_id else None
        if session is None:
            if profile_id is None:
                from app.repositories.vertical_loop_repository import repository
                snapshot = repository.snapshot_profile(user_id)
                profile_id = snapshot.profile_id
            session = ConversationSession(
                conversation_id=conversation_id or uuid4(),
                user_id=user_id,
                title=title or "学习画像会话",
                conversation_type=conversation_type,
                profile_id=profile_id,
                messages=[],
                created_at=now,
                updated_at=now,
            )
            _sessions[session.conversation_id] = session
            _user_sessions.setdefault(user_id, []).insert(0, session.conversation_id)
        elif profile_id and session.profile_id != profile_id:
            session.profile_id = profile_id
        session.messages.append(
            ConversationMessage(
                id=uuid4(),
                conversation_id=session.conversation_id,
                user_id=user_id,
                role=role,  # type: ignore[arg-type]
                content=content,
                intent=intent,
                metadata=metadata or {},
                created_at=now,
            )
        )
        if len(session.messages) > _MAX_MESSAGES_PER_SESSION:
            session.messages = session.messages[-_MAX_MESSAGES_PER_SESSION:]
        session.updated_at = now
    return session


def update_last_assistant_message(
    user_id: UUID,
    conversation_id: UUID,
    metadata_patch: dict,
) -> bool:
    """Merge metadata_patch into the last assistant message of the conversation."""
    if _use_db():
        from app.db.models import ConversationMessageModel
        from app.db.session import SessionLocal
        from sqlalchemy import select, desc
        with SessionLocal() as db:
            row = db.scalars(
                select(ConversationMessageModel)
                .where(ConversationMessageModel.session_id == conversation_id)
                .where(ConversationMessageModel.user_id == user_id)
                .where(ConversationMessageModel.role == "assistant")
                .order_by(desc(ConversationMessageModel.created_at))
                .limit(1)
            ).first()
            if not row:
                return False
            existing = row.metadata_json or {}
            existing.update(metadata_patch)
            row.metadata_json = existing
            db.commit()
            return True

    with _mem_lock:
        session = _sessions.get(conversation_id)
        if not session:
            return False
        for msg in reversed(session.messages):
            if msg.role == "assistant":
                msg.metadata.update(metadata_patch)
                return True
        return False


def get_conversation(conversation_id: UUID) -> Optional[ConversationSession]:
    if _use_db():
        return _db_get_conversation(conversation_id)
    with _mem_lock:
        return _sessions.get(conversation_id)


def list_conversations(user_id: UUID) -> List[ConversationSession]:
    if _use_db():
        return _db_list_conversations(user_id)
    with _mem_lock:
        return [_sessions[item] for item in _user_sessions.get(user_id, []) if item in _sessions]


def rename_conversation(conversation_id: UUID, new_title: str) -> bool:
    if _use_db():
        from app.db.models import ConversationSessionModel
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            row = db.get(ConversationSessionModel, conversation_id)
            if not row:
                return False
            row.title = new_title
            db.commit()
            return True
    with _mem_lock:
        session = _sessions.get(conversation_id)
        if not session:
            return False
        session.title = new_title
        return True


def delete_conversation(conversation_id: UUID) -> bool:
    if _use_db():
        from app.db.models import ConversationMessageModel, ConversationSessionModel, LearningResourceModel
        from app.db.session import SessionLocal
        from sqlalchemy import delete
        with SessionLocal() as db:
            row = db.get(ConversationSessionModel, conversation_id)
            if not row:
                return False
            db.execute(delete(ConversationMessageModel).where(ConversationMessageModel.session_id == conversation_id))
            db.execute(delete(LearningResourceModel).where(LearningResourceModel.conversation_id == conversation_id))
            db.delete(row)
            db.commit()
            return True
    with _mem_lock:
        session = _sessions.pop(conversation_id, None)
        if not session:
            return False
        uid = session.user_id
        if uid in _user_sessions:
            _user_sessions[uid] = [sid for sid in _user_sessions[uid] if sid != conversation_id]
        return True


def as_profile_conversation(session: ConversationSession) -> List[Dict[str, str]]:
    return [{"role": item.role, "content": item.content} for item in session.messages]


def end_conversation(conversation_id: UUID) -> bool:
    """End a conversation. Returns True if profile was merged, False otherwise.

    Events now write directly to master profile, so no merge is needed.
    This function exists for API compatibility.
    """
    return False
