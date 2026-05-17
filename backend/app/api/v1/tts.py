from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.errors import ServiceError
from app.schemas.auth import UserDTO
from app.services import tts_service

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None


@router.post("/synthesize")
def synthesize_speech(
    payload: TTSRequest,
    current_user: UserDTO = Depends(get_current_user),
) -> Response:
    """Convert text to speech audio (MP3)."""
    try:
        audio = tts_service.synthesize(payload.text, voice=payload.voice)
        return Response(content=audio, media_type="audio/mpeg")
    except ServiceError as exc:
        return Response(content=b"", status_code=503, headers={"X-Error": str(exc.detail)})
