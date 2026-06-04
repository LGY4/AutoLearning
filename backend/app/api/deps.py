from __future__ import annotations
"""FastAPI dependencies for authentication."""

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import UserDTO
from app.services.auth_service import current_user

_security = HTTPBearer(auto_error=False)


def get_current_user(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> UserDTO:
    """Extract and validate the Bearer token. Returns UserDTO.

    If no token is provided, raises 401.
    """
    if cred is None:
        raise HTTPException(status_code=401, detail="Missing access token")
    return current_user(cred.credentials)


def get_optional_user(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Optional[UserDTO]:
    """Like get_current_user but returns None instead of raising 401."""
    if cred is None:
        return None
    try:
        return current_user(cred.credentials)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise
