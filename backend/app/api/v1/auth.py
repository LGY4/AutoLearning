from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.core.response import ApiResponse, success
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserDTO
from app.services import auth_service


router = APIRouter()


@router.post("/register", response_model=ApiResponse[LoginResponse])
def register(payload: RegisterRequest) -> ApiResponse[LoginResponse]:
    user = auth_service.create_user(payload)
    token = auth_service.issue_access_token(user)

    # Auto-seed demo data for new users
    try:
        from app.ops.seed_demo_full import seed_full_demo_data
        import logging
        seed_full_demo_data(str(user.id))
        logging.getLogger(__name__).info("Demo data seeded for user %s", user.id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Demo data seeding failed (non-fatal)")

    return success(LoginResponse(access_token=token, user=user))


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(payload: LoginRequest) -> ApiResponse[LoginResponse]:
    user = auth_service.authenticate(payload)
    token = auth_service.issue_access_token(user)
    return success(LoginResponse(access_token=token, user=user))


@router.get("/me", response_model=ApiResponse[UserDTO])
def me(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> ApiResponse[UserDTO]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing access token")
    token = authorization[len("Bearer "):].strip()
    return success(auth_service.current_user(token))
