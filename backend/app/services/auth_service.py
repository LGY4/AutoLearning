from __future__ import annotations

from typing import Dict,  Optional

import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import UserRole
from app.db.models import AppUser, StudentProfileModel
from app.db.session import SessionLocal
from app.repositories.mock_store import store
from app.schemas.auth import LoginRequest, RegisterRequest, UserDTO
from app.schemas.profile import (
    BasicInfo,
    CognitiveProfile,
    DynamicUpdate,
    KnowledgeProfile,
    LearningBehavior,
    LearningGoalProfile,
    LearningPreference,
    StudentProfile,
)
from app.services.runtime_support import now_iso




def _hash_password(password: str, salt: Optional[str] = None) -> str:
    resolved_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), resolved_salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${resolved_salt}${base64.b64encode(digest).decode('utf-8')}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, digest = encoded.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(_hash_password(password, salt), encoded)


_MEMORY_PASSWORDS: Dict[UUID, str] = {user.id: _hash_password("123456") for user in store.users.values()}


def _sign(payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    secret = get_settings().secret_key.encode("utf-8")
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest().encode("ascii")
    return base64.urlsafe_b64encode(body + b"." + signature).decode("utf-8")


def _unsign(token: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8"))
        body, signature = raw.rsplit(b".", 1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    expected = hmac.new(get_settings().secret_key.encode("utf-8"), body, hashlib.sha256).hexdigest().encode("ascii")
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid access token")
    payload = json.loads(body.decode("utf-8"))
    exp = payload.get("exp")
    if exp and int(time.time()) > exp:
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def _build_initial_profile(user_id: UUID, profile_hint: RegisterRequest) -> StudentProfile:
    return StudentProfile(
        profile_id=uuid4(),
        user_id=user_id,
        version=1,
        completeness_score=0.0,
        confidence_score=0.0,
        basic_info=BasicInfo(major=profile_hint.major or "待补充", grade=profile_hint.grade or "待补充", school=profile_hint.school),
        knowledge_profile=KnowledgeProfile(overall_level="unknown", known_topics=[], weak_topics=[], mastery_level={}),
        learning_goal=LearningGoalProfile(current_goal="", target_course="", target_level="project_practice", deadline=None),
        learning_preference=LearningPreference(
            learning_style="mixed",
            resource_preference={
                "document": 0.7,
                "mindmap": 0.7,
                "quiz": 0.7,
                "reading": 0.6,
                "video": 0.6,
                "animation": 0.6,
                "code_case": 0.7,
            },
            difficulty_preference="step_by_step",
        ),
        learning_behavior=LearningBehavior(
            average_study_minutes=45,
            active_period="evening",
            completion_rate=0.0,
            recent_scores=[],
            last_knowledge_point=None,
        ),
        cognitive_profile=CognitiveProfile(
            cognitive_style="mixed",
            abstract_understanding="medium",
            hands_on_ability="medium",
            reading_patience="medium",
        ),
        dynamic_update=DynamicUpdate(
            last_updated_at=now_iso(),
            update_source="register",
            update_reason="用户注册后创建初始空画像",
        ),
    )


def create_user(request: RegisterRequest) -> UserDTO:
    if get_settings().repository_backend == "memory":
        if any(u.username == request.username for u in store.users.values()):
            raise HTTPException(status_code=409, detail="Username already exists")
        user = UserDTO(id=uuid4(), username=request.username, role=UserRole.STUDENT)
        store.users[user.id] = user
        _MEMORY_PASSWORDS[user.id] = _hash_password(request.password)
        profile = _build_initial_profile(user.id, request)
        store.profiles[user.id] = profile
        store.profile_versions[user.id] = [profile]
        return user

    with SessionLocal() as db:
        exists = db.scalar(select(AppUser.id).where(AppUser.username == request.username).limit(1))
        if exists is not None:
            raise HTTPException(status_code=409, detail="Username already exists")
        user = AppUser(
            id=uuid4(),
            username=request.username,
            password_hash=_hash_password(request.password),
            real_name=request.real_name,
            email=request.email,
            phone=request.phone,
            role=UserRole.STUDENT.value,
            status="active",
        )
        db.add(user)
        profile = _build_initial_profile(user.id, request)
        db.add(
            StudentProfileModel(
                id=profile.profile_id,
                user_id=user.id,
                profile_json=profile.model_dump(mode="json"),
                profile_version=profile.version,
                completeness_score=profile.completeness_score,
                confidence_score=profile.confidence_score,
                updated_by=profile.dynamic_update.update_source,
            )
        )
        db.commit()
        return UserDTO(id=user.id, username=user.username, role=UserRole(user.role))


def authenticate(request: LoginRequest) -> UserDTO:
    if get_settings().repository_backend == "memory":
        user = next((item for item in store.users.values() if item.username == request.username), None)
        if user is None or not _verify_password(request.password, _MEMORY_PASSWORDS.get(user.id, "")):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        return user

    with SessionLocal() as db:
        user = db.scalar(select(AppUser).where(AppUser.username == request.username).limit(1))
        if user is None or not _verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if user.status != "active":
            raise HTTPException(status_code=403, detail="User is inactive")
        return UserDTO(id=user.id, username=user.username, role=UserRole(user.role))


_TOKEN_TTL_SECONDS = 86400 * 7  # 7 days


def issue_access_token(user: UserDTO) -> str:
    return _sign({
        "user_id": str(user.id),
        "username": user.username,
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    })


def current_user(token: str) -> UserDTO:
    payload = _unsign(token)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    if get_settings().repository_backend == "memory":
        user = store.users.get(UUID(str(user_id)))
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    with SessionLocal() as db:
        user = db.get(AppUser, UUID(str(user_id)))
        if user is None or user.status != "active":
            raise HTTPException(status_code=401, detail="User not found")
        return UserDTO(id=user.id, username=user.username, role=UserRole(user.role))
