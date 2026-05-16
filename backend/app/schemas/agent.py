from __future__ import annotations

from typing import List,  Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import ResourceType
from app.schemas.profile import (
    BasicInfo,
    CognitiveProfile,
    KnowledgeProfile,
    LearningBehavior,
    LearningGoalProfile,
    LearningPreference,
)


class ProfileExtractionDraft(BaseModel):
    basic_info: BasicInfo
    knowledge_profile: KnowledgeProfile
    learning_goal: LearningGoalProfile
    learning_preference: LearningPreference
    learning_behavior: LearningBehavior
    cognitive_profile: CognitiveProfile
    completeness_score: float = Field(default=0.88)
    confidence_score: float = Field(default=0.84)
    update_reason: str = "从对话中抽取并更新学生画像"

    @field_validator("completeness_score", "confidence_score", mode="before")
    @classmethod
    def _normalize_score(cls, value):
        """Accept 0-100 or 0-1 scale, always store as 0-1."""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0.5
        if v > 1.0:
            return min(v / 100.0, 1.0)
        return max(0.0, min(v, 1.0))


class PathNodeDraft(BaseModel):
    knowledge_point: str
    estimated_minutes: int = Field(default=30, ge=5)
    recommended_resource_types: List[ResourceType] = Field(default_factory=list)
    reason: str = "根据学生画像与学习目标生成"

    @model_validator(mode="before")
    @classmethod
    def _normalize_reason(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if not normalized.get("reason"):
            for key in ("description", "explanation", "note", "why"):
                if normalized.get(key):
                    normalized["reason"] = str(normalized[key])
                    break
        normalized.setdefault("reason", "根据学生画像与学习目标生成")
        return normalized


class LearningPathDraft(BaseModel):
    title: str
    strategy: dict = Field(default_factory=dict)
    nodes: List[PathNodeDraft] = Field(default_factory=list)

    @field_validator("strategy", mode="before")
    @classmethod
    def _normalize_strategy(cls, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            return {"summary": value.strip()}
        return {}


class QuizQuestionDraft(BaseModel):
    type: str
    stem: str
    options: List[str] = Field(default_factory=list)
    answer: str
    explanation: str
    difficulty: str = "beginner"


class QuizDraft(BaseModel):
    title: str
    overview: str
    questions: List[QuizQuestionDraft] = Field(default_factory=list)
    scoring_rules: List[str] = Field(default_factory=list)


class MarkdownResourceDraft(BaseModel):
    title: str
    markdown: str
    summary: str
    outline: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


class MultimodalDraft(BaseModel):
    title: str
    mindmap_markdown: str
    video_storyboard: List[str] = Field(default_factory=list)
    image_prompts: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MindmapDraft(BaseModel):
    title: str
    mindmap_markdown: str
    summary: str = ""
    key_branches: List[str] = Field(default_factory=list)


class FlowchartDraft(BaseModel):
    title: str
    drawio_xml: str
    summary: str = ""
    node_count: int = 0


class StoryboardScene(BaseModel):
    frame: int
    duration_seconds: int = 30
    visual_description: str
    narration: str
    image_prompt: str = ""


class VideoDraft(BaseModel):
    title: str
    total_seconds: int = 180
    scenes: List[StoryboardScene] = Field(default_factory=list)
    summary: str = ""
    key_points: List[str] = Field(default_factory=list)


class ReadingDraft(BaseModel):
    title: str
    markdown: str
    summary: str
    key_concepts: List[str] = Field(default_factory=list)
    discussion_questions: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)


class CodeCaseDraft(BaseModel):
    title: str
    language: str = "python"
    code: str
    run_instructions: List[str] = Field(default_factory=list)
    explanation: str
    checkpoints: List[str] = Field(default_factory=list)


class TutorAnswerDraft(BaseModel):
    answer: str
    next_step: str
    references: List[str] = Field(default_factory=list)
    diagram_prompt: Optional[str] = None
    markdown: str
