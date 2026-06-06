from __future__ import annotations
from typing import List


from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.profile import ProfileExtractRequest, StudentProfile
from app.services import profile_service


router = APIRouter()


@router.post("/extract", response_model=ApiResponse[StudentProfile])
def extract_profile(payload: ProfileExtractRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[StudentProfile]:
    payload.user_id = current_user.id
    # If no conversation provided, load recent conversations as context
    if not payload.conversation:
        from app.services import conversation_service
        sessions = conversation_service.list_conversations(current_user.id)
        messages = []
        for s in sessions[:3]:  # last 3 conversations
            for msg in s.messages[-10:]:  # last 10 messages each
                messages.append({"role": msg.role, "content": msg.content})
        if messages:
            payload.conversation = messages
        else:
            payload.conversation = [{"role": "user", "content": "初始化学生画像"}]
    return success(profile_service.extract_profile(payload))


@router.get("/profile/{profile_id}", response_model=ApiResponse[StudentProfile])
def get_profile_by_id(profile_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[StudentProfile]:
    profile = profile_service.get_profile_by_id(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return success(profile)


@router.get("/me", response_model=ApiResponse[StudentProfile])
def get_my_profile(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[StudentProfile]:
    profile = profile_service.get_profile(current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return success(profile)


@router.get("/me/versions", response_model=ApiResponse[List[StudentProfile]])
def get_my_profile_versions(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[StudentProfile]]:
    return success(profile_service.get_profile_versions(current_user.id))


@router.get("/{user_id}", response_model=ApiResponse[StudentProfile])
def get_profile_by_user_id(user_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[StudentProfile]:
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    profile = profile_service.get_profile(current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return success(profile)
