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
