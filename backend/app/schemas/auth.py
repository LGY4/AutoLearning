from __future__ import annotations

from typing import Optional

from uuid import UUID

from pydantic import BaseModel

from app.core.enums import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    real_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    school: Optional[str] = None

    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    def model_post_init(self, __context: object) -> None:
        self.password = self._validate_password(self.password)


class UserDTO(BaseModel):
    id: UUID
    username: str
    role: UserRole


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: UserDTO
