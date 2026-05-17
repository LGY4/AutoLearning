from __future__ import annotations

from typing import List, Optional

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid4)


class AppUser(Base):
    __tablename__ = "app_user"

    id = uuid_pk()
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    real_name = Column(String(64))
    role = Column(String(32), nullable=False)
    email = Column(String(128))
    phone = Column(String(32))
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    profiles = relationship("StudentProfileModel", back_populates="user", cascade="all, delete-orphan")


class BaseAgentModel(Base):
    __tablename__ = "base_agent"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    system_prompt = Column(Text, nullable=False)
    applies_to = Column(JSONB, nullable=False, default=list)
    model_provider = Column(String(64), nullable=False, default="spark")
    output_style = Column(String(64), nullable=False, default="structured")
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StudentProfileModel(Base):
    __tablename__ = "student_profile"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_json = Column(JSONB, nullable=False)
    profile_version = Column(Integer, default=1)
    completeness_score = Column(Numeric(5, 2))
    confidence_score = Column(Numeric(5, 2))
    updated_by = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("AppUser", back_populates="profiles")
    history = relationship("StudentProfileHistory", back_populates="profile", cascade="all, delete-orphan")


class StudentProfileHistory(Base):
    __tablename__ = "student_profile_history"

    id = uuid_pk()
    profile_id = Column(UUID(as_uuid=True), ForeignKey("student_profile.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_name = Column(String(128), nullable=False)
    old_value = Column(JSONB)
    new_value = Column(JSONB)
    change_reason = Column(Text)
    source_type = Column(String(64))
    source_id = Column(UUID(as_uuid=True))
    confidence_score = Column(Numeric(5, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("StudentProfileModel", back_populates="history")


class LearningGoal(Base):
    __tablename__ = "learning_goal"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_title = Column(String(255), nullable=False)
    goal_description = Column(Text)
    target_course_id = Column(UUID(as_uuid=True), ForeignKey("course.id", ondelete="SET NULL"), nullable=True, index=True)
    target_level = Column(String(64))
    deadline = Column(Date)
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Course(Base):
    __tablename__ = "course"

    id = uuid_pk()
    course_name = Column(String(128), nullable=False)
    subject = Column(String(128))
    description = Column(Text)
    difficulty_level = Column(String(32))
    created_by = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Chapter(Base):
    __tablename__ = "chapter"

    id = uuid_pk()
    course_id = Column(UUID(as_uuid=True), ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_name = Column(String(128), nullable=False)
    chapter_order = Column(Integer, nullable=False)
    description = Column(Text)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_point"

    id = uuid_pk()
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapter.id", ondelete="CASCADE"), index=True)
    name = Column(String(128), nullable=False, index=True)
    description = Column(Text)
    prerequisite_ids = Column(JSONB)
    difficulty_level = Column(String(32))
    tags = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LearningResourceModel(Base):
    __tablename__ = "learning_resource"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversation_session.id", ondelete="SET NULL"), nullable=True, index=True)
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_point.id", ondelete="SET NULL"), index=True)
    title = Column(String(255), nullable=False)
    resource_type = Column(String(64), nullable=False, index=True)
    content_summary = Column(Text)
    difficulty_level = Column(String(32))
    target_profile = Column(JSONB)
    status = Column(String(32), default="draft", index=True)
    current_version = Column(Integer, default=1)
    generated_by_agent_id = Column(UUID(as_uuid=True))
    quality_score = Column(Numeric(5, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResourceVersion(Base):
    __tablename__ = "resource_version"

    id = uuid_pk()
    resource_id = Column(UUID(as_uuid=True), ForeignKey("learning_resource.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    content = Column(Text)
    content_url = Column(Text)
    prompt_used = Column(Text)
    model_name = Column(String(128))
    generation_params = Column(JSONB)
    change_reason = Column(Text)
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LearningPathModel(Base):
    __tablename__ = "learning_path"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("learning_goal.id", ondelete="SET NULL"), index=True)
    title = Column(String(255))
    path_version = Column(Integer, default=1)
    strategy = Column(JSONB)
    status = Column(String(32), default="active")
    generated_by_agent_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    nodes = relationship("LearningPathNodeModel", back_populates="path", cascade="all, delete-orphan")


class LearningPathNodeModel(Base):
    __tablename__ = "learning_path_node"

    id = uuid_pk()
    path_id = Column(UUID(as_uuid=True), ForeignKey("learning_path.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_point.id", ondelete="SET NULL"), index=True)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("learning_resource.id", ondelete="SET NULL"), index=True)
    node_order = Column(Integer, nullable=False)
    expected_duration_minutes = Column(Integer)
    node_status = Column(String(32), default="locked")
    unlock_condition = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    path = relationship("LearningPathModel", back_populates="nodes")


class AgentWorkflowModel(Base):
    __tablename__ = "agent_workflow"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    current_agent = Column(String(64))
    input_payload = Column(JSONB)
    output_payload = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks = relationship("AgentTaskModel", back_populates="workflow", cascade="all, delete-orphan")
    events = relationship("AgentEventLog", back_populates="workflow", cascade="all, delete-orphan")


class AgentTaskModel(Base):
    __tablename__ = "agent_task"

    id = uuid_pk()
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("agent_workflow.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type = Column(String(64), nullable=False)
    agent_name = Column(String(128), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True)
    input_payload = Column(JSONB)
    output_payload = Column(JSONB)
    status = Column(String(32), default="pending", index=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    parent_task_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))

    workflow = relationship("AgentWorkflowModel", back_populates="tasks")


class AgentEventLog(Base):
    __tablename__ = "agent_event_log"

    id = uuid_pk()
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("agent_workflow.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("agent_task.id", ondelete="SET NULL"), index=True)
    from_agent = Column(String(128))
    to_agent = Column(String(128))
    action = Column(String(128), nullable=False)
    input_snapshot = Column(JSONB)
    output_snapshot = Column(JSONB)
    status = Column(String(32), default="success")
    progress = Column(Integer, default=0)
    duration_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("AgentWorkflowModel", back_populates="events")


class LearningRecordModel(Base):
    __tablename__ = "learning_record"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    path_id = Column(UUID(as_uuid=True), ForeignKey("learning_path.id", ondelete="SET NULL"), index=True)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("learning_resource.id", ondelete="SET NULL"), index=True)
    knowledge_point = Column(String(255))
    resource_type = Column(String(50))
    score = Column(Integer)
    duration_seconds = Column(Integer, default=0)
    wrong_points = Column(JSONB)
    feedback = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RecommendationRecord(Base):
    __tablename__ = "recommendation_record"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("learning_resource.id", ondelete="SET NULL"), index=True)
    path_id = Column(UUID(as_uuid=True), ForeignKey("learning_path.id", ondelete="SET NULL"), index=True)
    recommend_reason = Column(JSONB)
    profile_snapshot = Column(JSONB)
    score = Column(Numeric(5, 2))
    status = Column(String(32), default="pushed")
    clicked = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmbeddingIndex(Base):
    __tablename__ = "embedding_index"
    __table_args__ = (
        UniqueConstraint("business_type", "business_id", "version_no", name="uq_embedding_biz_version"),
    )

    id = uuid_pk()
    business_type = Column(String(64), nullable=False)
    business_id = Column(UUID(as_uuid=True), nullable=False)
    collection_name = Column(String(128), nullable=False)
    embedding_id = Column(String(128), nullable=False)
    text_hash = Column(String(128), nullable=False)
    embedding_model = Column(String(128))
    vector_status = Column(String(32), default="active")
    version_no = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PromptTemplate(Base):
    __tablename__ = "prompt_template"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_name_version"),
    )

    id = uuid_pk()
    name = Column(String(128), nullable=False)
    agent_name = Column(String(64), nullable=False)
    version = Column(String(32), nullable=False)
    template = Column(Text, nullable=False)
    variables = Column(JSONB)
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeGraphModel(Base):
    __tablename__ = "knowledge_graph"

    id = uuid_pk()
    graph_id = Column(String(128), unique=True, nullable=False, index=True)
    course_id = Column(String(128), nullable=False, index=True)
    course_name = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    review_status = Column(String(32), nullable=False, default="draft", index=True)
    graph_json = Column(JSONB, nullable=False)
    node_count = Column(Integer, default=0)
    edge_count = Column(Integer, default=0)
    confidence = Column(Numeric(5, 2))
    generated_by = Column(String(64), default="graph_builder_agent")
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationSessionModel(Base):
    __tablename__ = "conversation_session"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="学习画像会话")
    conversation_type = Column(String(32), nullable=False, default="learning")
    profile_id = Column(UUID(as_uuid=True), ForeignKey("student_profile.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship("ConversationMessageModel", back_populates="session", cascade="all, delete-orphan", order_by="ConversationMessageModel.created_at")


class ConversationMessageModel(Base):
    __tablename__ = "conversation_message"

    id = uuid_pk()
    session_id = Column(UUID(as_uuid=True), ForeignKey("conversation_session.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(64), default="learning")
    metadata_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ConversationSessionModel", back_populates="messages")


class QuestionModel(Base):
    __tablename__ = "question"

    id = uuid_pk()
    knowledge_point = Column(String(255), nullable=False, index=True)
    question_type = Column(String(64), nullable=False)
    stem = Column(Text, nullable=False)
    options = Column(JSONB)
    answer = Column(JSONB)
    explanation = Column(Text)
    difficulty_level = Column(String(32), default="medium")
    subject = Column(String(128), default="")
    tags = Column(JSONB, default=list)
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnswerRecordModel(Base):
    __tablename__ = "answer_record"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question.id", ondelete="CASCADE"), nullable=False, index=True)
    user_answer = Column(JSONB, nullable=False)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Numeric(5, 2))
    grading_method = Column(String(32), default="exact")
    grading_detail = Column(JSONB)
    time_spent_seconds = Column(Integer)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())


class ProfileEventModel(Base):
    __tablename__ = "profile_event"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    event_payload = Column(JSONB, nullable=False)
    confidence = Column(Numeric(5, 2), nullable=False)
    source_type = Column(String(64))
    source_id = Column(UUID(as_uuid=True))
    status = Column(String(32), nullable=False, default="pending")
    applied_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
