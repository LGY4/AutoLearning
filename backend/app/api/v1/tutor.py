from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.services import conversation_service, tutor_service
from app.services.model_gateway import ModelOverride, model_override_context


class TutorChatRequest(BaseModel):
    user_id: UUID
    question: str
    conversation_id: Optional[UUID] = None
    knowledge_point: Optional[str] = None
    base_agent_id: Optional[UUID] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    model_temperature: Optional[float] = None


class TutorChatResponse(BaseModel):
    user_id: UUID
    conversation_id: UUID
    answer: str
    markdown: str
    rag_references: List[dict]
    next_step: Optional[str] = None
    diagram_prompt: Optional[str] = None
    references: Optional[List[str]] = None
    question: str


router = APIRouter()


@router.post("/chat", response_model=ApiResponse[TutorChatResponse])
def chat(payload: TutorChatRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[TutorChatResponse]:
    payload.user_id = current_user.id
    session = conversation_service.append_message(
        current_user.id,
        role="user",
        content=payload.question,
        conversation_id=payload.conversation_id,
        intent="tutor_question",
        title=payload.knowledge_point or "AI 导师辅导",
        conversation_type="tutor",
    )
    override = ModelOverride(
        provider=payload.model_provider,
        model_name=payload.model_name,
        temperature=payload.model_temperature,
    )
    with model_override_context(override):
        result = tutor_service.answer_question(
            current_user.id,
            payload.question,
            conversation_id=session.conversation_id,
            knowledge_point=payload.knowledge_point,
            base_agent_id=payload.base_agent_id,
        )
    conversation_service.append_message(
        current_user.id,
        role="assistant",
        content=result["markdown"],
        conversation_id=session.conversation_id,
        intent="tutor_answer",
        metadata={"rag_references": result.get("rag_references", [])},
        conversation_type="tutor",
    )
    return success(TutorChatResponse(
        user_id=payload.user_id,
        conversation_id=session.conversation_id,
        answer=result["answer"],
        markdown=result["markdown"],
        rag_references=result.get("rag_references", []),
        next_step=result.get("next_step"),
        diagram_prompt=result.get("diagram_prompt"),
        references=result.get("references"),
        question=payload.question,
    ))
