from __future__ import annotations

from typing import Dict,  List,  Optional

from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class BasicInfo(BaseModel):
    major: str = "未知"
    grade: str = "未知"
    school: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_basic_info(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        # Handle LLM variations
        if not normalized.get("major"):
            for key in ("name", "field", "discipline", "专业"):
                if normalized.get(key):
                    normalized["major"] = str(normalized[key])
                    break
        if not normalized.get("grade"):
            for key in ("education_level", "level", "年级"):
                if normalized.get(key):
                    normalized["grade"] = str(normalized[key])
                    break
        normalized.setdefault("major", "未知")
        normalized.setdefault("grade", "未知")
        return normalized


_DIMENSION_SYNONYMS = {
    "low": "low", "lo": "low", "l": "low", "低": "low", "弱": "low", "差": "low",
    "mid": "mid", "medium": "mid", "m": "mid", "中": "mid", "中等": "mid",
    "high": "high", "hi": "high", "h": "high", "高": "high", "强": "high", "好": "high",
}


def _normalize_dimension(value: str) -> str:
    """Normalize dimension value to low/mid/high, handling LLM variations."""
    return _DIMENSION_SYNONYMS.get(str(value).strip().lower(), "low")


class KnowledgeDimension(BaseModel):
    """单知识点的四维度评估"""
    mastery: str = "low"        # 掌握程度: low/mid/high
    application: str = "low"    # 应用程度: low/mid/high
    memory: str = "low"         # 记忆程度: low/mid/high
    understanding: str = "low"  # 理解程度: low/mid/high

    @field_validator("mastery", "application", "memory", "understanding", mode="before")
    @classmethod
    def _normalize_dim(cls, v: str) -> str:
        return _normalize_dimension(v)

    @property
    def composite_score(self) -> float:
        """综合分 0.0-1.0，用于排序和路径规划"""
        level_map = {"low": 0.2, "mid": 0.6, "high": 1.0}
        return (
            level_map.get(self.mastery, 0.2) * 0.3
            + level_map.get(self.application, 0.2) * 0.25
            + level_map.get(self.memory, 0.2) * 0.2
            + level_map.get(self.understanding, 0.2) * 0.25
        )

    @property
    def archetype(self) -> str:
        """81种组合的语义标签，用于提示词参数映射"""
        return f"{self.mastery}_{self.application}_{self.memory}_{self.understanding}"

    @property
    def overall_label(self) -> str:
        """综合等级标签"""
        score = self.composite_score
        if score >= 0.75:
            return "high"
        if score >= 0.45:
            return "mid"
        return "low"


class KnowledgeProfile(BaseModel):
    overall_level: str = "beginner"
    known_topics: List[str] = Field(default_factory=list)
    weak_topics: List[str] = Field(default_factory=list)
    mastery_level: Dict[str, float] = Field(default_factory=dict)
    topic_dimensions: Dict[str, KnowledgeDimension] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_knowledge_profile(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        # Handle LLM variations for overall_level
        if not normalized.get("overall_level"):
            for key in ("level", "current_level", "proficiency"):
                if normalized.get(key):
                    normalized["overall_level"] = str(normalized[key])
                    break
        # Handle variations for known_topics
        if not normalized.get("known_topics"):
            for key in ("mastered_topics", "prerequisites_mastered", "known"):
                if normalized.get(key) and isinstance(normalized[key], list):
                    normalized["known_topics"] = normalized[key]
                    break
        # Handle variations for weak_topics
        if not normalized.get("weak_topics"):
            for key in ("weaknesses", "prerequisites_weak", "weak"):
                if normalized.get(key) and isinstance(normalized[key], list):
                    normalized["weak_topics"] = normalized[key]
                    break
        normalized.setdefault("overall_level", "beginner")
        normalized.setdefault("known_topics", [])
        normalized.setdefault("weak_topics", [])
        return normalized

    @field_validator("mastery_level", mode="before")
    @classmethod
    def _normalize_mastery_level(cls, value):
        if not isinstance(value, dict):
            return {}
        normalized: Dict[str, float] = {}
        for key, item in value.items():
            if key in (None, "") or item in (None, ""):
                continue
            try:
                normalized[str(key)] = float(item)
            except (TypeError, ValueError):
                continue
        return normalized

    @field_validator("topic_dimensions", mode="before")
    @classmethod
    def _normalize_topic_dimensions(cls, value):
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for key, item in value.items():
            if key in (None, "") or item in (None, ""):
                continue
            if isinstance(item, dict):
                try:
                    normalized[str(key)] = item
                except Exception:
                    continue
            # skip non-dict values silently
        return normalized


class LearningGoalProfile(BaseModel):
    current_goal: str = ""
    target_course: str = ""
    target_level: str = "project_practice"
    deadline: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_learning_goal(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if not normalized.get("current_goal"):
            for key in ("goal", "objective", "learning_goal", "target_goal"):
                if normalized.get(key):
                    normalized["current_goal"] = str(normalized[key])
                    break
        if not normalized.get("target_course"):
            for key in ("subject", "course", "target_subject"):
                if normalized.get(key):
                    normalized["target_course"] = str(normalized[key])
                    break
        normalized.setdefault("current_goal", "")
        normalized.setdefault("target_course", "")
        return normalized


_STYLE_SYNONYMS = {
    "visual": "visual", "视觉": "visual", "图解": "visual", "图表": "visual",
    "reading": "reading", "阅读": "reading", "文字": "reading",
    "hands-on": "hands-on", "动手": "hands-on", "实践": "hands-on", "实操": "hands-on",
    "mixed": "mixed", "混合": "mixed", "平衡": "mixed",
}


class LearningPreference(BaseModel):
    learning_style: str = "mixed"
    resource_preference: Dict[str, float] = Field(default_factory=dict)
    difficulty_preference: str = "step_by_step"

    @field_validator("learning_style", mode="before")
    @classmethod
    def _normalize_learning_style(cls, v: str) -> str:
        return _STYLE_SYNONYMS.get(str(v).strip().lower(), "mixed")


class LearningBehavior(BaseModel):
    average_study_minutes: int = 45
    active_period: str = "evening"
    completion_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    recent_scores: List[int] = Field(default_factory=list)
    last_knowledge_point: Optional[str] = None


_COGNITIVE_LEVEL_SYNONYMS = {
    "low": "low", "lo": "low", "低": "low", "弱": "low", "差": "low",
    "medium": "medium", "mid": "medium", "中": "medium", "中等": "medium",
    "high": "high", "hi": "high", "高": "high", "强": "high", "好": "high",
}


class CognitiveProfile(BaseModel):
    cognitive_style: str = "mixed"
    abstract_understanding: str = "medium"
    hands_on_ability: str = "medium"
    reading_patience: str = "medium"

    @model_validator(mode="before")
    @classmethod
    def _normalize_cognitive_profile(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if not normalized.get("cognitive_style"):
            for key in ("style", "cognitive_type", "learning_style"):
                if normalized.get(key):
                    normalized["cognitive_style"] = str(normalized[key])
                    break
        normalized.setdefault("cognitive_style", "mixed")
        for field in ("abstract_understanding", "hands_on_ability", "reading_patience"):
            if normalized.get(field):
                normalized[field] = _COGNITIVE_LEVEL_SYNONYMS.get(str(normalized[field]).strip().lower(), "medium")
        return normalized


class DynamicUpdate(BaseModel):
    last_updated_at: str = ""
    update_source: str = "unknown"
    update_reason: str = ""


class StudentProfile(BaseModel):
    profile_id: UUID
    user_id: UUID
    version: int = 1
    completeness_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    basic_info: BasicInfo
    knowledge_profile: KnowledgeProfile
    learning_goal: LearningGoalProfile
    learning_preference: LearningPreference
    learning_behavior: LearningBehavior
    cognitive_profile: CognitiveProfile
    dynamic_update: DynamicUpdate


class ProfileExtractRequest(BaseModel):
    user_id: UUID
    conversation: List[Dict[str, str]] = Field(default_factory=list)
    learning_behavior: Optional[dict] = None
    base_agent_id: Optional[UUID] = None
