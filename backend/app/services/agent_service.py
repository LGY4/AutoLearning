from __future__ import annotations

from typing import Optional

from uuid import UUID

from app.core.enums import ResourceType
from app.repositories.vertical_loop_repository import repository
from app.schemas.agent import (
    CodeCaseDraft,
    MarkdownResourceDraft,
    MultimodalDraft,
    QuizDraft,
)
from app.schemas.learning_path import LearningPath
from app.schemas.profile import ProfileExtractRequest, StudentProfile
from app.services import agent_runtime


def construct_profile(request: ProfileExtractRequest) -> StudentProfile:
    previous = repository.get_profile(request.user_id)
    profile = agent_runtime.build_profile(request, previous)
    return repository.save_profile(profile)


def generate_learning_path(user_id: UUID, goal: str, subject: str) -> LearningPath:
    return repository.create_path(user_id, goal, subject)


def answer_tutor_question(user_id: UUID, question: str, conversation_id: Optional[UUID] = None, knowledge_point: Optional[str] = None) -> dict:
    from app.services import tutor_service

    return tutor_service.answer_question(user_id, question, conversation_id=conversation_id, knowledge_point=knowledge_point)


def build_document_agent_payload(profile: Optional[StudentProfile], knowledge_point: str, subject: str, difficulty: str) -> MarkdownResourceDraft:
    """Generate document content via LLM (not fallback)."""
    resource = agent_runtime.build_learning_resource(
        user_id=UUID("00000000-0000-0000-0000-000000000000"),
        subject=subject,
        knowledge_point=knowledge_point,
        resource_type=ResourceType.DOCUMENT,
        difficulty=difficulty,
        profile=profile,
    )
    import json
    draft_data = resource.metadata.get("draft", {})
    if isinstance(draft_data, str):
        draft_data = json.loads(draft_data)
    return MarkdownResourceDraft.model_validate(draft_data)


def build_quiz_agent_payload(knowledge_point: str, difficulty: str = "beginner") -> QuizDraft:
    """Generate quiz content via LLM (not fallback)."""
    resource = agent_runtime.build_learning_resource(
        user_id=UUID("00000000-0000-0000-0000-000000000000"),
        subject="通用",
        knowledge_point=knowledge_point,
        resource_type=ResourceType.QUIZ,
        difficulty=difficulty,
        profile=None,
    )
    import json
    draft_data = resource.metadata.get("draft", {})
    if isinstance(draft_data, str):
        draft_data = json.loads(draft_data)
    return QuizDraft.model_validate(draft_data)


def build_multimodal_agent_payload(knowledge_point: str, difficulty: str = "beginner") -> MultimodalDraft:
    """Generate multimodal content via LLM (not fallback)."""
    resource = agent_runtime.build_learning_resource(
        user_id=UUID("00000000-0000-0000-0000-000000000000"),
        subject="通用",
        knowledge_point=knowledge_point,
        resource_type=ResourceType.MINDMAP,
        difficulty=difficulty,
        profile=None,
    )
    import json
    draft_data = resource.metadata.get("draft", {})
    if isinstance(draft_data, str):
        draft_data = json.loads(draft_data)
    # For multimodal, the draft is in the assets
    assets = resource.metadata.get("assets", {})
    return MultimodalDraft(
        title=resource.title,
        mindmap_markdown=assets.get("mindmap", ""),
        video_storyboard=assets.get("video_storyboard", []),
        image_prompts=assets.get("image_prompts", []),
        notes=assets.get("notes", []),
    )


def build_code_agent_payload(knowledge_point: str, subject: str, difficulty: str = "beginner") -> CodeCaseDraft:
    """Generate code case content via LLM (not fallback)."""
    resource = agent_runtime.build_learning_resource(
        user_id=UUID("00000000-0000-0000-0000-000000000000"),
        subject=subject,
        knowledge_point=knowledge_point,
        resource_type=ResourceType.CODE_CASE,
        difficulty=difficulty,
        profile=None,
    )
    import json
    draft_data = resource.metadata.get("draft", {})
    if isinstance(draft_data, str):
        draft_data = json.loads(draft_data)
    return CodeCaseDraft.model_validate(draft_data)
