from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.conversation import ConversationListResponse, ConversationSession
from app.services import conversation_service


router = APIRouter()


class RenameRequest(BaseModel):
    title: str


@router.get("/users/me/list", response_model=ApiResponse[ConversationListResponse])
def list_user_conversations(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[ConversationListResponse]:
    return success(ConversationListResponse(conversations=conversation_service.list_conversations(current_user.id)))


@router.get("/{conversation_id}", response_model=ApiResponse[ConversationSession])
def get_conversation(conversation_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[ConversationSession]:
    session = conversation_service.get_conversation(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return success(session)


@router.patch("/{conversation_id}", response_model=ApiResponse[dict])
def rename_conversation(conversation_id: UUID, payload: RenameRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    session = conversation_service.get_conversation(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    ok = conversation_service.rename_conversation(conversation_id, title)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return success({"renamed": True})


@router.delete("/{conversation_id}", response_model=ApiResponse[dict])
def delete_conversation(conversation_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    session = conversation_service.get_conversation(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    ok = conversation_service.delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return success({"deleted": True})


class EndConversationResponse(BaseModel):
    merged: bool


@router.post("/{conversation_id}/end", response_model=ApiResponse[EndConversationResponse])
def end_conversation(conversation_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[EndConversationResponse]:
    session = conversation_service.get_conversation(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    merged = conversation_service.end_conversation(conversation_id)
    return success(EndConversationResponse(merged=merged))
