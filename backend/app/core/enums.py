from __future__ import annotations

from enum import Enum


class ResourceType(str, Enum):
    DOCUMENT = "document"
    MINDMAP = "mindmap"
    QUIZ = "quiz"
    READING = "reading"
    VIDEO = "video"
    ANIMATION = "animation"
    CODE_CASE = "code_case"
    FLOWCHART = "flowchart"
    PPT = "ppt"


class AgentName(str, Enum):
    PROFILE = "profile_agent"
    PATH = "path_agent"
    DOCUMENT = "document_agent"
    QUIZ = "quiz_agent"
    MINDMAP = "mindmap_agent"
    VIDEO = "video_agent"
    CODE = "code_agent"
    QUALITY = "quality_agent"
    RECOMMENDATION = "recommendation_agent"
    TUTOR = "tutor_agent"
    FLOWCHART = "flowchart_agent"


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ResourceStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    GENERATED = "generated"
    REVIEWING = "reviewing"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    FAILED = "failed"


class PathNodeStatus(str, Enum):
    LOCKED = "locked"
    AVAILABLE = "available"
    LEARNING = "learning"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
