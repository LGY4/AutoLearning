from __future__ import annotations

import logging
from typing import List, Optional

from uuid import UUID

from app.repositories.vertical_loop_repository import repository

logger = logging.getLogger(__name__)
from app.services.base_agent_service import get_base_agent
from app.schemas.profile import (
    ProfileExtractRequest,
    StudentProfile,
)
from app.services import agent_runtime


def get_profile(user_id: UUID, conversation_id: Optional[UUID] = None) -> Optional[StudentProfile]:
    if conversation_id:
        from app.services import conversation_service
        session = conversation_service.get_conversation(conversation_id)
        if session and session.profile_id:
            profile = repository.get_profile_by_id(session.profile_id)
            if profile:
                return profile
    return repository.get_profile(user_id)


def get_or_create_profile(user_id: UUID, conversation_id: Optional[UUID] = None) -> StudentProfile:
    """Get existing profile or create a minimal default."""
    existing = get_profile(user_id, conversation_id=conversation_id)
    if existing is not None:
        return existing
    return extract_profile(ProfileExtractRequest(
        user_id=user_id,
        conversation=[{"role": "user", "content": "初始化学生画像"}],
    ))


def get_profile_by_id(profile_id: UUID) -> Optional[StudentProfile]:
    return repository.get_profile_by_id(profile_id)


def get_profile_versions(user_id: UUID) -> List[StudentProfile]:
    return repository.get_profile_versions(user_id)


def extract_profile(request: ProfileExtractRequest, conversation_id: Optional[UUID] = None) -> StudentProfile:
    previous = get_profile(request.user_id, conversation_id=conversation_id)
    base_agent = get_base_agent(request.user_id, request.base_agent_id)
    profile = agent_runtime.build_profile(request, previous, base_agent=base_agent)
    from app.services.profile_event_service import ProfileEventType, emit_event
    emit_event(request.user_id, ProfileEventType.LLM_EXTRACT, {"profile": profile.model_dump(mode="json")}, confidence=0.5)
    saved = repository.get_profile(request.user_id)
    if saved is None:
        logger.warning("Profile extraction event emitted but profile not found for user %s, using in-memory fallback", request.user_id)
        return profile
    return saved
