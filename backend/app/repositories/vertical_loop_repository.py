from __future__ import annotations

from typing import List,  Optional

import logging
from contextlib import contextmanager
from collections.abc import Generator
from datetime import datetime, timezone
from uuid import UUID, uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _merge_profiles(conv_profile: "StudentProfile", master: "StudentProfile") -> "StudentProfile":
    """Merge conversation profile changes onto master profile.

    Three-layer merge strategy:
    - Knowledge layer: confidence-weighted merge via merge_dimensions
    - Preference layer: sliding-window weighted blend
    - Basic layer: direct overwrite (latest wins)
    """
    from app.schemas.profile import DynamicUpdate, KnowledgeDimension
    from app.services.strategy_engine import merge_dimensions, compute_known_topics, compute_weak_topics, compute_mastery_level

    # ── Knowledge layer: confidence-weighted merge ──
    master_dims = master.knowledge_profile.topic_dimensions
    conv_dims = conv_profile.knowledge_profile.topic_dimensions
    all_kps = set(master_dims.keys()) | set(conv_dims.keys())
    merged_dims: dict[str, KnowledgeDimension] = {}
    for kp in all_kps:
        m = master_dims.get(kp)
        c = conv_dims.get(kp)
        if m and c:
            # Both have data — use merge_dimensions with medium confidence
            merged_dims[kp] = merge_dimensions(m, c, confidence=0.6)
        elif c:
            merged_dims[kp] = c
        else:
            merged_dims[kp] = m

    # Derive weak/known/mastery from merged dimensions
    merged_weak = compute_weak_topics(merged_dims)
    merged_known = compute_known_topics(merged_dims)
    merged_mastery = compute_mastery_level(merged_dims)

    # overall_level: take conversation's if truthy, else master's
    overall_level = conv_profile.knowledge_profile.overall_level
    if not overall_level or overall_level == "unknown":
        overall_level = master.knowledge_profile.overall_level

    new_kp = master.knowledge_profile.model_copy(update={
        "topic_dimensions": merged_dims,
        "overall_level": overall_level,
        "weak_topics": merged_weak,
        "known_topics": merged_known,
        "mastery_level": merged_mastery,
    })

    # ── Preference layer: sliding-window blend ──
    # For string enums, use majority-vote weighted toward conversation
    def _blend_str(conv_val: str, master_val: str, conv_weight: float = 0.7) -> str:
        if conv_val == master_val:
            return conv_val
        # If conversation has a non-default value, prefer it
        if conv_val and conv_val not in ("mixed", "unknown", "medium"):
            return conv_val
        return master_val

    master_pref = master.learning_preference
    conv_pref = conv_profile.learning_preference
    blended_pref = conv_pref.model_copy(update={
        "learning_style": _blend_str(conv_pref.learning_style, master_pref.learning_style),
    })

    master_cog = master.cognitive_profile
    conv_cog = conv_profile.cognitive_profile
    blended_cog = conv_cog.model_copy(update={
        "cognitive_style": _blend_str(conv_cog.cognitive_style, master_cog.cognitive_style),
        "abstract_understanding": _blend_str(conv_cog.abstract_understanding, master_cog.abstract_understanding),
        "hands_on_ability": _blend_str(conv_cog.hands_on_ability, master_cog.hands_on_ability),
        "reading_patience": _blend_str(conv_cog.reading_patience, master_cog.reading_patience),
    })

    # Behavior: take max for numeric fields
    master_beh = master.learning_behavior
    conv_beh = conv_profile.learning_behavior
    blended_beh = conv_beh.model_copy(update={
        "average_study_minutes": max(master_beh.average_study_minutes, conv_beh.average_study_minutes),
        "completion_rate": max(master_beh.completion_rate, conv_beh.completion_rate),
        "recent_scores": (conv_beh.recent_scores or master_beh.recent_scores)[-10:],
    })

    # ── Basic layer: direct overwrite ──
    new_dynamic = DynamicUpdate(
        last_updated_at=now_iso(),
        update_source="conversation_merge",
        update_reason="对话结束，合并画像",
    )
    return master.model_copy(update={
        "knowledge_profile": new_kp,
        "basic_info": conv_profile.basic_info,
        "learning_goal": conv_profile.learning_goal,
        "learning_preference": blended_pref,
        "learning_behavior": blended_beh,
        "cognitive_profile": blended_cog,
        "dynamic_update": new_dynamic,
        "completeness_score": max(master.completeness_score, conv_profile.completeness_score),
        "confidence_score": max(master.confidence_score, conv_profile.confidence_score),
        "version": master.version + 1,
    })


@contextmanager
def _safe_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

from app.core.config import get_settings
from app.core.enums import AgentName, AgentTaskStatus, ResourceType
from app.db.models import (
    AgentEventLog,
    AgentTaskModel,
    AgentWorkflowModel,
    AnswerRecordModel,
    AppUser,
    AssessmentSnapshotModel,
    LearningPathModel,
    LearningPathNodeModel,
    LearningRecordModel,
    LearningResourceModel,
    ProfileEventModel,
    RecommendationRecord,
    ResourceVersion,
    StudentProfileHistory,
    StudentProfileModel,
)
from app.db.session import SessionLocal
from app.repositories.mock_store import store
from app.schemas.auth import UserDTO
from app.schemas.learning_path import LearningPath
from app.schemas.learning_record import LearningRecordCreate
from app.schemas.profile import StudentProfile
from app.schemas.recommendation import Recommendation
from app.schemas.resource import LearningResource
from app.schemas.workflow import AgentWorkflow
from app.services import agent_runtime
from app.services.base_agent_service import get_base_agent
from app.repositories.base import VerticalLoopRepositoryProtocol
from app.services.runtime_support import resource_score
from app.workflows.learning_graph import run_workflow

# Backward-compatible alias
VerticalLoopRepository = VerticalLoopRepositoryProtocol


class InMemoryVerticalLoopRepository:
    def get_user_by_username(self, username: str) -> Optional[UserDTO]:
        return store.get_user_by_username(username)

    def get_default_user(self) -> UserDTO:
        return next(iter(store.users.values()))

    def get_profile(self, user_id: UUID) -> Optional[StudentProfile]:
        return store.profiles.get(user_id)

    def get_profile_by_id(self, profile_id: UUID) -> Optional[StudentProfile]:
        for p in store.profiles.values():
            if p.profile_id == profile_id:
                return p
        return None

    def get_profile_versions(self, user_id: UUID) -> List[StudentProfile]:
        return store.profile_versions.get(user_id, [])

    def save_profile(self, profile: StudentProfile) -> StudentProfile:
        return store.upsert_profile(profile)

    def snapshot_profile(self, user_id: UUID) -> StudentProfile:
        master = store.profiles.get(user_id)
        if master is None:
            from app.schemas.profile import BasicInfo, CognitiveProfile, DynamicUpdate, KnowledgeProfile, LearningBehavior, LearningGoalProfile, LearningPreference
            master = StudentProfile(
                profile_id=uuid4(), user_id=user_id, version=1,
                completeness_score=0.0, confidence_score=0.0,
                basic_info=BasicInfo(), knowledge_profile=KnowledgeProfile(),
                learning_goal=LearningGoalProfile(), learning_preference=LearningPreference(),
                learning_behavior=LearningBehavior(), cognitive_profile=CognitiveProfile(),
                dynamic_update=DynamicUpdate(update_source="snapshot"),
            )
        snapshot = master.model_copy(update={"profile_id": uuid4(), "version": 1})
        store.profiles[snapshot.profile_id] = snapshot
        return snapshot

    def save_profile_in_place(self, profile_id: UUID, profile: StudentProfile) -> StudentProfile:
        for uid, p in store.profiles.items():
            if p.profile_id == profile_id:
                updated = profile.model_copy(update={"profile_id": profile_id})
                store.profiles[uid] = updated
                return updated
        store.profiles[profile.user_id] = profile.model_copy(update={"profile_id": profile_id})
        return profile

    def merge_conversation_profile(self, conversation_profile_id: UUID, user_id: UUID) -> Optional[StudentProfile]:
        conv_profile = self.get_profile_by_id(conversation_profile_id)
        master = store.profiles.get(user_id)
        if not conv_profile:
            return master
        if not master:
            store.profiles[user_id] = conv_profile.model_copy(update={"profile_id": uuid4(), "version": 1})
            return store.profiles[user_id]
        merged = _merge_profiles(conv_profile, master)
        saved = store.upsert_profile(merged)
        return saved

    def create_path(self, user_id: UUID, goal: str, subject: str, base_agent_id: Optional[UUID] = None) -> LearningPath:
        return store.create_demo_path(user_id, goal, subject, base_agent_id)

    def get_path(self, user_id: UUID) -> Optional[LearningPath]:
        return store.paths.get(user_id)

    def get_path_by_id(self, path_id: UUID, user_id: UUID) -> Optional[LearningPath]:
        paths = store.path_history.get(user_id, [])
        for p in paths:
            if p.path_id == path_id:
                return p
        return None

    def list_paths(self, user_id: UUID, page: int = 1, page_size: int = 20) -> tuple:
        paths = store.path_history.get(user_id, [])
        total = len(paths)
        start = (page - 1) * page_size
        return paths[start:start + page_size], total

    def delete_path(self, path_id: UUID, user_id: UUID) -> bool:
        paths = store.path_history.get(user_id, [])
        store.path_history[user_id] = [p for p in paths if p.path_id != path_id]
        if store.paths.get(user_id) and store.paths[user_id].path_id == path_id:
            store.paths.pop(user_id, None)
        return True

    def complete_path_node(self, user_id: UUID, node_id: UUID) -> Optional[LearningPath]:
        return store.complete_path_node(user_id, node_id)

    def start_learning_node(self, user_id: UUID, knowledge_point: str) -> Optional[LearningPath]:
        return store.start_learning_node(user_id, knowledge_point)

    def create_workflow(self, user_id: UUID, input_payload: Optional[dict] = None, emit_progress=None) -> AgentWorkflow:
        return store.create_workflow(user_id, input_payload)

    def get_workflow(self, workflow_id: UUID) -> Optional[AgentWorkflow]:
        return store.workflows.get(workflow_id)

    def create_resource(self, user_id: UUID, knowledge_point: str, resource_type: ResourceType, difficulty: str, base_agent_id: Optional[UUID] = None, conversation_id: Optional[UUID] = None) -> LearningResource:
        return store.create_resource(user_id, knowledge_point, resource_type, difficulty, base_agent_id)

    def get_resource(self, resource_id: UUID) -> Optional[LearningResource]:
        return store.resources.get(resource_id)

    def create_recommendations(self, user_id: UUID) -> List[Recommendation]:
        return store.create_recommendations(user_id)

    def get_recommendations(self, user_id: UUID) -> List[Recommendation]:
        return store.recommendations.get(user_id, [])

    def get_pending_suggestions(self, user_id: UUID) -> List[dict]:
        return []  # In-memory store doesn't persist suggestions

    def consume_suggested_generation(self, user_id: UUID, rec: dict) -> None:
        pass  # No-op for in-memory store

    def save_learning_record(self, record: LearningRecordCreate) -> Optional[UUID]:
        record_id = uuid4()
        store.learning_records.append({
            "record_id": record_id,
            "user_id": record.user_id,
            "path_id": record.path_id,
            "resource_id": record.resource_id,
            "knowledge_point": record.knowledge_point,
            "resource_type": record.resource_type,
            "score": record.score,
            "duration_seconds": record.duration_seconds,
            "wrong_points": record.wrong_points,
            "feedback": record.feedback,
            "created_at": now_iso(),
        })
        return record_id

    def list_learning_records(self, user_id: UUID) -> List[dict]:
        records = [r for r in store.learning_records if r["user_id"] == user_id]
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records

    def list_questions(self, knowledge_point: Optional[str] = None, question_type: Optional[str] = None, subject: Optional[str] = None, difficulty: Optional[str] = None) -> List[dict]:
        results = store.questions
        if knowledge_point:
            results = [q for q in results if q.get("knowledge_point") == knowledge_point]
        if question_type:
            results = [q for q in results if q.get("question_type") == question_type]
        if subject:
            results = [q for q in results if q.get("subject") == subject]
        if difficulty:
            results = [q for q in results if q.get("difficulty_level") == difficulty]
        return results

    def get_question(self, question_id: UUID) -> Optional[dict]:
        for q in store.questions:
            if str(q.get("id")) == str(question_id):
                return q
        return None

    def save_question(self, data: dict) -> dict:
        qid = str(uuid4())
        record = {"id": qid, "status": "active", **data}
        store.questions.append(record)
        return {"id": qid, "status": "created"}

    def delete_question(self, question_id: UUID) -> bool:
        for q in store.questions:
            if str(q.get("id")) == str(question_id):
                q["status"] = "deleted"
                return True
        return False

    def save_answer_record(self, data: dict) -> dict:
        record_id = uuid4()
        record = {
            "id": str(record_id),
            "user_id": str(data["user_id"]),
            "question_id": str(data["question_id"]),
            "user_answer": data["user_answer"],
            "is_correct": data.get("is_correct"),
            "score": data.get("score"),
            "grading_method": data.get("grading_method", "exact"),
            "grading_detail": data.get("grading_detail"),
            "time_spent_seconds": data.get("time_spent_seconds"),
            "submitted_at": now_iso(),
        }
        store.answer_records.append(record)
        return {"id": str(record_id), "is_correct": record["is_correct"], "score": record["score"]}

    def get_user_answer_history(self, user_id: UUID, question_id: Optional[UUID] = None) -> List[dict]:
        results = [r for r in store.answer_records if r.get("user_id") == str(user_id)]
        if question_id:
            results = [r for r in results if r.get("question_id") == str(question_id)]
        return results[:50]

    def list_user_resources(self, user_id: UUID) -> List[dict]:
        return [
            {
                "resource_id": str(r.resource_id),
                "title": r.title,
                "resource_type": r.resource_type.value if hasattr(r.resource_type, 'value') else r.resource_type,
                "knowledge_point": r.knowledge_point,
                "difficulty": r.difficulty,
                "quality_score": r.quality_score,
                "status": r.status.value if hasattr(r.status, 'value') else r.status,
                "created_at": r.created_at.isoformat() if hasattr(r, 'created_at') and r.created_at else None,
            }
            for r in store.resources.values() if r.user_id == user_id
        ]

    def delete_resource(self, user_id: UUID, resource_id: UUID) -> bool:
        r = store.resources.get(resource_id)
        if r and r.user_id == user_id:
            del store.resources[resource_id]
            return True
        return False

    def emit_event(self, user_id: UUID, event_type: str, event_payload: dict, confidence: float, source_type: str = "agent", source_id: Optional[UUID] = None) -> UUID:
        event_id = uuid4()
        from app.services.runtime_support import now_iso
        store.profile_events.append({
            "id": event_id,
            "user_id": user_id,
            "event_type": event_type,
            "event_payload": event_payload,
            "confidence": confidence,
            "source_type": source_type,
            "source_id": source_id,
            "status": "pending",
            "error_message": None,
            "created_at": now_iso(),
        })
        return event_id

    def list_pending_events(self, user_id: UUID, limit: int = 20) -> List[dict]:
        return [e for e in store.profile_events if e["user_id"] == user_id and e["status"] == "pending"][:limit]

    def list_events_by_type(self, user_id: UUID, event_type: str, limit: int = 50) -> List[dict]:
        events = [e for e in store.profile_events if e["user_id"] == user_id and e["event_type"] == event_type]
        events.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return events[:limit]

    def update_event_status(self, event_id: UUID, status: str, error_message: Optional[str] = None) -> None:
        for e in store.profile_events:
            if e["id"] == event_id:
                e["status"] = status
                e["error_message"] = error_message
                break

    def get_latest_profile_version(self, user_id: UUID) -> Optional[int]:
        profile = store.profiles.get(user_id)
        return profile.version if profile else None

    def save_profile_and_update_event(
        self, profile: StudentProfile, event_id: UUID, event_status: str = "applied", error_message: Optional[str] = None
    ) -> StudentProfile:
        result = self.save_profile(profile)
        self.update_event_status(event_id, event_status, error_message)
        return result

    def save_assessment_snapshot(self, user_id: UUID, data: dict) -> dict:
        record = {
            "id": str(uuid4()),
            "user_id": str(user_id),
            "mastery_score": data["mastery_score"],
            "confidence": data["confidence"],
            "stage": data.get("stage", "unknown"),
            "weak_point_count": data.get("weak_point_count", 0),
            "weak_topics": data.get("weak_topics", []),
            "created_at": now_iso(),
        }
        store.assessment_snapshots.insert(0, record)
        # Keep max 50 per user
        uid = str(user_id)
        count = 0
        trimmed = []
        for r in store.assessment_snapshots:
            if r["user_id"] == uid:
                count += 1
                if count > 50:
                    continue
            trimmed.append(r)
        store.assessment_snapshots = trimmed
        return record

    def list_assessment_history(self, user_id: UUID, limit: int = 20) -> List[dict]:
        return [r for r in store.assessment_snapshots if r["user_id"] == str(user_id)][:limit]


class PostgresVerticalLoopRepository:
    def get_user_by_username(self, username: str) -> Optional[UserDTO]:
        with SessionLocal() as db:
            row = db.scalar(select(AppUser).where(AppUser.username == username).limit(1))
            return UserDTO(id=row.id, username=row.username, role=row.role) if row else None

    def get_default_user(self) -> UserDTO:
        with SessionLocal() as db:
            row = db.scalar(select(AppUser).limit(1))
            if not row:
                raise RuntimeError("No users found")
            return UserDTO(id=row.id, username=row.username, role=row.role)

    def get_profile(self, user_id: UUID) -> Optional[StudentProfile]:
        with SessionLocal() as db:
            row = db.scalar(
                select(StudentProfileModel)
                .where(StudentProfileModel.user_id == user_id)
                .order_by(desc(StudentProfileModel.profile_version), desc(StudentProfileModel.updated_at))
                .limit(1)
            )
            return StudentProfile.model_validate(row.profile_json) if row else None

    def get_profile_by_id(self, profile_id: UUID) -> Optional[StudentProfile]:
        with SessionLocal() as db:
            row = db.scalar(
                select(StudentProfileModel).where(StudentProfileModel.id == profile_id).limit(1)
            )
            return StudentProfile.model_validate(row.profile_json) if row else None

    def get_profile_versions(self, user_id: UUID) -> List[StudentProfile]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(StudentProfileModel)
                .where(StudentProfileModel.user_id == user_id)
                .order_by(StudentProfileModel.profile_version)
                .limit(100)
            ).all()
            return [StudentProfile.model_validate(row.profile_json) for row in rows]

    def get_latest_profile_version(self, user_id: UUID) -> Optional[int]:
        with SessionLocal() as db:
            row = db.scalar(
                select(StudentProfileModel.profile_version)
                .where(StudentProfileModel.user_id == user_id)
                .order_by(desc(StudentProfileModel.profile_version))
                .limit(1)
            )
            return row

    def save_profile(self, profile: StudentProfile) -> StudentProfile:
        with _safe_session() as db:
            latest = db.scalar(
                select(StudentProfileModel)
                .where(StudentProfileModel.user_id == profile.user_id)
                .order_by(desc(StudentProfileModel.profile_version))
                .with_for_update()
                .limit(1)
            )

            next_version = (latest.profile_version + 1) if latest else 1
            new_id = uuid4()
            row = StudentProfileModel(
                id=new_id,
                user_id=profile.user_id,
                profile_json=profile.model_dump(mode="json"),
                profile_version=next_version,
                completeness_score=profile.completeness_score,
                confidence_score=profile.confidence_score,
                updated_by=profile.dynamic_update.update_source,
            )
            db.add(row)
            if latest:
                db.add(
                    StudentProfileHistory(
                        profile_id=latest.id,
                        feature_name="student_profile",
                        old_value=latest.profile_json,
                        new_value=profile.model_dump(mode="json"),
                        change_reason=profile.dynamic_update.update_reason,
                        source_type="agent",
                        confidence_score=profile.confidence_score,
                    )
                )
        # Return profile with the actual version and ID from database
        return profile.model_copy(update={"profile_id": new_id, "version": next_version})

    def snapshot_profile(self, user_id: UUID) -> StudentProfile:
        master = self.get_profile(user_id)
        if master is None:
            from app.schemas.profile import BasicInfo, CognitiveProfile, DynamicUpdate, KnowledgeProfile, LearningBehavior, LearningGoalProfile, LearningPreference
            master = StudentProfile(
                profile_id=uuid4(), user_id=user_id, version=1,
                completeness_score=0.0, confidence_score=0.0,
                basic_info=BasicInfo(), knowledge_profile=KnowledgeProfile(),
                learning_goal=LearningGoalProfile(), learning_preference=LearningPreference(),
                learning_behavior=LearningBehavior(), cognitive_profile=CognitiveProfile(),
                dynamic_update=DynamicUpdate(update_source="snapshot"),
            )
        snapshot_id = uuid4()
        snapshot = master.model_copy(update={"profile_id": snapshot_id, "version": 1})
        with _safe_session() as db:
            db.add(StudentProfileModel(
                id=snapshot_id, user_id=user_id,
                profile_json=snapshot.model_dump(mode="json"),
                profile_version=1,
                completeness_score=snapshot.completeness_score,
                confidence_score=snapshot.confidence_score,
                updated_by="snapshot",
            ))
        return snapshot

    def save_profile_in_place(self, profile_id: UUID, profile: StudentProfile) -> StudentProfile:
        with _safe_session() as db:
            row = db.get(StudentProfileModel, profile_id)
            if row:
                row.profile_json = profile.model_dump(mode="json")
                row.completeness_score = profile.completeness_score
                row.confidence_score = profile.confidence_score
                row.updated_by = profile.dynamic_update.update_source
        return profile.model_copy(update={"profile_id": profile_id})

    def merge_conversation_profile(self, conversation_profile_id: UUID, user_id: UUID) -> Optional[StudentProfile]:
        conv_profile = self.get_profile_by_id(conversation_profile_id)
        master = self.get_profile(user_id)
        if not conv_profile:
            return master
        if not master:
            # No master profile — conversation profile becomes the master
            return self.save_profile(conv_profile.model_copy(update={"version": 1}))
        merged = _merge_profiles(conv_profile, master)
        return self.save_profile(merged)

    def create_path(self, user_id: UUID, goal: str, subject: str, base_agent_id: Optional[UUID] = None) -> LearningPath:
        profile = self.get_profile(user_id)
        base_agent = get_base_agent(user_id, base_agent_id)
        path = agent_runtime.build_learning_path(user_id, goal, subject, profile, base_agent=base_agent)
        with _safe_session() as db:
            db.add(
                LearningPathModel(
                    id=path.path_id,
                    user_id=path.user_id,
                    title=path.title,
                    strategy={"path_payload": path.model_dump(mode="json"), **path.strategy},
                    status=path.status,
                )
            )
            db.flush()
            for node in path.nodes:
                db.add(
                    LearningPathNodeModel(
                        id=node.node_id,
                        path_id=path.path_id,
                        node_order=node.order,
                        expected_duration_minutes=node.estimated_minutes,
                        node_status=node.status.value,
                        unlock_condition={
                            "knowledge_point": node.knowledge_point,
                            "recommended_resource_types": [item.value for item in node.recommended_resource_types],
                            "reason": node.reason,
                        },
                    )
                )
        return path

    def get_path(self, user_id: UUID) -> Optional[LearningPath]:
        with SessionLocal() as db:
            row = db.scalar(
                select(LearningPathModel)
                .where(LearningPathModel.user_id == user_id)
                .order_by(desc(LearningPathModel.updated_at))
                .limit(1)
            )
            if not row or not row.strategy or "path_payload" not in row.strategy:
                return None
            return LearningPath.model_validate(row.strategy["path_payload"])

    def get_path_by_id(self, path_id: UUID, user_id: UUID) -> Optional[LearningPath]:
        with SessionLocal() as db:
            row = db.scalar(
                select(LearningPathModel)
                .where(LearningPathModel.id == path_id, LearningPathModel.user_id == user_id)
            )
            if not row or not row.strategy or "path_payload" not in row.strategy:
                return None
            return LearningPath.model_validate(row.strategy["path_payload"])

    def list_paths(self, user_id: UUID, page: int = 1, page_size: int = 20) -> tuple:
        with SessionLocal() as db:
            q = db.query(LearningPathModel).filter(LearningPathModel.user_id == user_id)
            total = q.count()
            rows = (
                q.order_by(desc(LearningPathModel.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            paths = []
            for row in rows:
                if row.strategy and "path_payload" in row.strategy:
                    paths.append(LearningPath.model_validate(row.strategy["path_payload"]))
            return paths, total

    def delete_path(self, path_id: UUID, user_id: UUID) -> bool:
        with _safe_session() as db:
            row = db.scalar(
                select(LearningPathModel)
                .where(LearningPathModel.id == path_id, LearningPathModel.user_id == user_id)
            )
            if not row:
                return False
            db.delete(row)
            return True

    def complete_path_node(self, user_id: UUID, node_id: UUID) -> Optional[LearningPath]:
        from app.core.enums import PathNodeStatus
        with _safe_session() as db:
            # Lock the row to prevent concurrent modifications
            row = db.scalar(
                select(LearningPathModel)
                .where(LearningPathModel.user_id == user_id)
                .order_by(desc(LearningPathModel.updated_at))
                .limit(1)
                .with_for_update()
            )
            if not row or not row.strategy or "path_payload" not in row.strategy:
                return None

            path = LearningPath.model_validate(row.strategy["path_payload"])
            # Find the target node and validate status
            target_node = None
            for node in path.nodes:
                if node.node_id == node_id:
                    target_node = node
                    break
            if target_node is None:
                return None  # node_id not found in path
            if target_node.status == PathNodeStatus.LOCKED:
                return None  # cannot complete a locked node
            if target_node.status == PathNodeStatus.COMPLETED:
                return path  # already completed, no-op

            updated_nodes = []
            found = False
            for node in path.nodes:
                if node.node_id == node_id:
                    updated_nodes.append(node.model_copy(update={"status": PathNodeStatus.COMPLETED}))
                    found = True
                elif found and node.status == PathNodeStatus.LOCKED:
                    updated_nodes.append(node.model_copy(update={"status": PathNodeStatus.AVAILABLE}))
                    found = False
                else:
                    updated_nodes.append(node)

            new_path = path.model_copy(update={"nodes": updated_nodes})
            row.strategy = {"path_payload": new_path.model_dump(mode="json"), **new_path.strategy}
        return new_path

    def start_learning_node(self, user_id: UUID, knowledge_point: str) -> Optional[LearningPath]:
        """Set a node to LEARNING status if it is currently AVAILABLE."""
        from app.core.enums import PathNodeStatus
        with _safe_session() as db:
            row = db.scalar(
                select(LearningPathModel)
                .where(LearningPathModel.user_id == user_id)
                .order_by(desc(LearningPathModel.updated_at))
                .limit(1)
                .with_for_update()
            )
            if not row or not row.strategy or "path_payload" not in row.strategy:
                return None

            path = LearningPath.model_validate(row.strategy["path_payload"])
            updated_nodes = []
            changed = False
            for node in path.nodes:
                if node.knowledge_point == knowledge_point and node.status == PathNodeStatus.AVAILABLE:
                    updated_nodes.append(node.model_copy(update={"status": PathNodeStatus.LEARNING}))
                    changed = True
                else:
                    updated_nodes.append(node)

            if not changed:
                return path

            new_path = path.model_copy(update={"nodes": updated_nodes})
            row.strategy = {"path_payload": new_path.model_dump(mode="json"), **new_path.strategy}
        return new_path

    def create_workflow(self, user_id: UUID, input_payload: Optional[dict] = None, emit_progress=None) -> AgentWorkflow:
        workflow_id = uuid4()
        tasks, events = run_workflow(workflow_id, user_id, input_payload, emit_progress=emit_progress)
        workflow = AgentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            status=AgentTaskStatus.SUCCESS,
            current_agent=AgentName.RECOMMENDATION,
            tasks=tasks,
            events=events,
            logs=[event.model_dump(mode="json") for event in events],
        )
        with _safe_session() as db:
            db.add(
                AgentWorkflowModel(
                    id=workflow.workflow_id,
                    user_id=workflow.user_id,
                    status=workflow.status.value,
                    current_agent=workflow.current_agent.value if workflow.current_agent else None,
                    input_payload=input_payload or {},
                    output_payload={"workflow_payload": workflow.model_dump(mode="json")},
                )
            )
            db.flush()
            for task in tasks:
                db.add(
                    AgentTaskModel(
                        id=task.task_id,
                        workflow_id=task.workflow_id,
                        task_type=task.task_type,
                        agent_name=task.agent_name.value,
                        user_id=user_id,
                        input_payload=task.input_payload,
                        output_payload=task.output_payload,
                        status=task.status.value,
                        progress=task.progress,
                        error_message=task.error_message,
                        retry_count=task.retry_count,
                    )
                )
            db.flush()
            for event in events:
                db.add(
                    AgentEventLog(
                        id=event.event_id,
                        workflow_id=event.workflow_id,
                        task_id=event.task_id,
                        from_agent=event.from_agent.value if event.from_agent else None,
                        to_agent=event.to_agent.value if event.to_agent else None,
                        action=event.action,
                        input_snapshot=event.input_snapshot,
                        output_snapshot=event.output_snapshot,
                        status=event.status.value,
                        progress=event.progress,
                        duration_ms=event.duration_ms,
                    )
                )
        return workflow

    def get_workflow(self, workflow_id: UUID) -> Optional[AgentWorkflow]:
        with SessionLocal() as db:
            row = db.get(AgentWorkflowModel, workflow_id)
            payload = row.output_payload if row else None
            if not payload or "workflow_payload" not in payload:
                return None
            return AgentWorkflow.model_validate(payload["workflow_payload"])

    def create_resource(self, user_id: UUID, knowledge_point: str, resource_type: ResourceType, difficulty: str, base_agent_id: Optional[UUID] = None, conversation_id: Optional[UUID] = None) -> LearningResource:
        profile = self.get_profile(user_id)
        subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用学习"
        base_agent = get_base_agent(user_id, base_agent_id)
        resource = agent_runtime.build_learning_resource(user_id, subject, knowledge_point, resource_type, difficulty, profile, base_agent=base_agent, conversation_id=conversation_id)
        with _safe_session() as db:
            db.add(
                LearningResourceModel(
                    id=resource.resource_id,
                    user_id=resource.user_id,
                    conversation_id=conversation_id,
                    title=resource.title,
                    resource_type=resource.resource_type.value,
                    content_summary=resource.content[:300],
                    difficulty_level=resource.difficulty,
                    target_profile={"resource_payload": resource.model_dump(mode="json")},
                    status=resource.status.value,
                    quality_score=resource.quality_score,
                )
            )
            db.flush()
            db.add(
                ResourceVersion(
                    resource_id=resource.resource_id,
                    version_no=1,
                    content=resource.content,
                    model_name=get_settings().model_provider,
                    generation_params=resource.metadata,
                    status="active",
                )
            )
        return resource

    def get_resource(self, resource_id: UUID) -> Optional[LearningResource]:
        with SessionLocal() as db:
            row = db.get(LearningResourceModel, resource_id)
            payload = row.target_profile if row else None
            if not payload or "resource_payload" not in payload:
                return None
            return LearningResource.model_validate(payload["resource_payload"])

    def create_recommendations(self, user_id: UUID) -> List[Recommendation]:
        from app.services.strategy_engine import get_resource_params

        with _safe_session() as db:
            profile_row = db.scalar(
                select(StudentProfileModel)
                .where(StudentProfileModel.user_id == user_id)
                .order_by(desc(StudentProfileModel.profile_version), desc(StudentProfileModel.updated_at))
                .limit(1)
            )
            profile = StudentProfile.model_validate(profile_row.profile_json) if profile_row else None

            # Load existing resources
            rows = db.scalars(select(LearningResourceModel).where(LearningResourceModel.user_id == user_id)).all()
            resources: List[LearningResource] = []
            for row in rows:
                payload = row.target_profile or {}
                if "resource_payload" in payload:
                    resources.append(LearningResource.model_validate(payload["resource_payload"]))

            # Get completed resource IDs from learning records
            from app.db.models import LearningRecordModel
            record_rows = db.scalars(
                select(LearningRecordModel.resource_id)
                .where(LearningRecordModel.user_id == user_id)
                .where(LearningRecordModel.resource_id.isnot(None))
            ).all()
            completed_ids = set(record_rows)

            # Score existing resources
            recommendations: List[Recommendation] = []
            existing_types_by_kp: dict[str, set[str]] = {}  # kp -> set of resource types
            for resource in resources:
                score, evidence = resource_score(resource, profile, completed_ids)
                kp = resource.knowledge_point
                existing_types_by_kp.setdefault(kp, set()).add(resource.resource_type.value)
                recommendations.append(
                    Recommendation(
                        recommendation_id=uuid4(),
                        user_id=user_id,
                        resource_id=resource.resource_id,
                        title=resource.title,
                        score=min(1.0, score / 100.0),
                        recommend_reason={
                            "main_reason": "根据画像、薄弱点和资源质量综合排序",
                            "weak_point": kp,
                            "matched_profile": profile.learning_preference.learning_style if profile else "unknown",
                            "evidence": evidence,
                            "recommendation_type": "existing_resource",
                        },
                    )
                )

            # Bridge strategy_engine: generate "should generate" recommendations
            # for weak topics that are missing resource types
            if profile:
                weak_topics = profile.knowledge_profile.weak_topics or []
                style = profile.learning_preference.learning_style
                for kp in weak_topics[:5]:  # limit to top 5 weak topics
                    dim = profile.knowledge_profile.topic_dimensions.get(kp)
                    if not dim:
                        continue
                    params = get_resource_params(dim, style)
                    recommended_types = params.get("resource_types", [])
                    existing_for_kp = existing_types_by_kp.get(kp, set())
                    missing_types = [t for t in recommended_types if t not in existing_for_kp]
                    for rtype in missing_types[:2]:  # max 2 missing types per KP
                        virtual_score = 0.5 + (0.15 if kp in weak_topics else 0)  # base + weak boost
                        recommendations.append(
                            Recommendation(
                                recommendation_id=uuid4(),
                                user_id=user_id,
                                resource_id=uuid4(),  # virtual — not yet generated
                                title=f"生成{rtype}：{kp}",
                                score=virtual_score,
                                recommend_reason={
                                    "main_reason": "根据画像推荐生成该类型资源",
                                    "weak_point": kp,
                                    "matched_profile": style,
                                    "resource_type": rtype,
                                    "dimension_summary": dim.model_dump(),
                                    "recommendation_type": "suggested_generation",
                                },
                            )
                        )

            recommendations.sort(key=lambda item: item.score, reverse=True)
            for item in recommendations:
                db.add(
                    RecommendationRecord(
                        id=item.recommendation_id,
                        user_id=item.user_id,
                        resource_id=item.resource_id,
                        recommend_reason={**item.recommend_reason, "title": item.title},
                        profile_snapshot=profile.model_dump(mode="json") if profile else None,
                        score=item.score,
                    )
                )
        return recommendations

    def get_recommendations(self, user_id: UUID) -> List[Recommendation]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(RecommendationRecord)
                .where(RecommendationRecord.user_id == user_id)
                .order_by(desc(RecommendationRecord.created_at))
                .limit(100)
            ).all()
            return [
                Recommendation(
                    recommendation_id=row.id,
                    user_id=row.user_id,
                    resource_id=row.resource_id,
                    title=(row.recommend_reason or {}).get("title", "推荐资源"),
                    score=float(row.score or 0),
                    recommend_reason=row.recommend_reason or {},
                )
                for row in rows
            ]

    def get_pending_suggestions(self, user_id: UUID) -> List[dict]:
        """Get pending suggested_generation recommendations."""
        with SessionLocal() as db:
            rows = db.scalars(
                select(RecommendationRecord)
                .where(
                    RecommendationRecord.user_id == user_id,
                    RecommendationRecord.completed == False,  # noqa: E712
                )
                .order_by(desc(RecommendationRecord.score))
                .limit(10)
            ).all()
            return [
                {
                    "recommendation_id": row.id,
                    "knowledge_point": (row.recommend_reason or {}).get("knowledge_point", ""),
                    "resource_type": (row.recommend_reason or {}).get("resource_type", "document"),
                    "title": (row.recommend_reason or {}).get("title", ""),
                    "recommendation_type": (row.recommend_reason or {}).get("recommendation_type", ""),
                }
                for row in rows
                if (row.recommend_reason or {}).get("recommendation_type") == "suggested_generation"
            ]

    def consume_suggested_generation(self, user_id: UUID, rec: dict) -> None:
        """Consume a suggested_generation: create the resource and mark recommendation completed."""
        from app.core.enums import ResourceType

        kp = rec.get("knowledge_point", "")
        rtype = rec.get("resource_type", "document")
        if not kp:
            return

        try:
            resource_type = ResourceType(rtype)
        except ValueError:
            resource_type = ResourceType.DOCUMENT

        # Create the resource
        self.create_resource(
            user_id=user_id,
            knowledge_point=kp,
            resource_type=resource_type,
        )

        # Mark recommendation as completed
        rec_id = rec.get("recommendation_id")
        if rec_id:
            with _safe_session() as db:
                row = db.get(RecommendationRecord, rec_id)
                if row:
                    row.completed = True

    def save_learning_record(self, record: LearningRecordCreate) -> Optional[UUID]:
        with _safe_session() as db:
            db_record = LearningRecordModel(
                user_id=record.user_id,
                path_id=record.path_id,
                resource_id=record.resource_id,
                knowledge_point=record.knowledge_point,
                resource_type=record.resource_type,
                score=record.score,
                duration_seconds=record.duration_seconds,
                wrong_points=record.wrong_points,
                feedback=record.feedback,
            )
            db.add(db_record)
            db.flush()
            return db_record.id

    def list_learning_records(self, user_id: UUID) -> List[dict]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(LearningRecordModel)
                .where(LearningRecordModel.user_id == user_id)
                .order_by(desc(LearningRecordModel.created_at))
            ).all()
            return [
                {
                    "record_id": str(row.id),
                    "user_id": str(row.user_id),
                    "score": row.score,
                    "duration_seconds": row.duration_seconds,
                    "wrong_points": row.wrong_points or [],
                    "knowledge_point": row.knowledge_point,
                    "resource_type": row.resource_type,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def list_questions(self, knowledge_point: Optional[str] = None, question_type: Optional[str] = None, subject: Optional[str] = None, difficulty: Optional[str] = None) -> List[dict]:
        from app.db.models import QuestionModel
        with SessionLocal() as db:
            q = select(QuestionModel).where(QuestionModel.status == "active")
            if knowledge_point:
                q = q.where(QuestionModel.knowledge_point == knowledge_point)
            if question_type:
                q = q.where(QuestionModel.question_type == question_type)
            if subject:
                q = q.where(QuestionModel.subject == subject)
            if difficulty:
                q = q.where(QuestionModel.difficulty_level == difficulty)
            rows = db.scalars(q.order_by(desc(QuestionModel.created_at))).all()
            return [
                {
                    "id": str(row.id),
                    "knowledge_point": row.knowledge_point,
                    "question_type": row.question_type,
                    "stem": row.stem,
                    "options": row.options,
                    "answer": row.answer,
                    "explanation": row.explanation,
                    "difficulty_level": row.difficulty_level,
                    "subject": row.subject,
                    "tags": row.tags or [],
                }
                for row in rows
            ]

    def get_question(self, question_id: UUID) -> Optional[dict]:
        with SessionLocal() as db:
            row = db.get(QuestionModel, question_id)
            if not row:
                return None
            return {
                "id": str(row.id),
                "knowledge_point": row.knowledge_point,
                "question_type": row.question_type,
                "stem": row.stem,
                "options": row.options,
                "answer": row.answer,
                "explanation": row.explanation,
                "difficulty_level": row.difficulty_level,
                "subject": row.subject,
                "tags": row.tags or [],
            }

    def save_question(self, data: dict) -> dict:
        with _safe_session() as db:
            q = QuestionModel(
                knowledge_point=data.get("knowledge_point", ""),
                question_type=data["question_type"],
                stem=data["stem"],
                options=data.get("options"),
                answer=data.get("answer"),
                explanation=data.get("explanation"),
                difficulty_level=data.get("difficulty_level", "medium"),
                subject=data.get("subject", ""),
                tags=data.get("tags", []),
            )
            db.add(q)
            db.flush()
            db.refresh(q)
            return {"id": str(q.id), "status": "created"}

    def delete_question(self, question_id: UUID) -> bool:
        with _safe_session() as db:
            row = db.get(QuestionModel, question_id)
            if not row:
                return False
            row.status = "deleted"
            return True

    def save_answer_record(self, data: dict) -> dict:
        with _safe_session() as db:
            record = AnswerRecordModel(
                user_id=data["user_id"],
                question_id=data["question_id"],
                user_answer=data["user_answer"],
                is_correct=data.get("is_correct"),
                score=data.get("score"),
                grading_method=data.get("grading_method", "exact"),
                grading_detail=data.get("grading_detail"),
                time_spent_seconds=data.get("time_spent_seconds"),
            )
            db.add(record)
            db.flush()
            db.refresh(record)
            return {"id": str(record.id), "is_correct": record.is_correct, "score": float(record.score) if record.score else None}

    def get_user_answer_history(self, user_id: UUID, question_id: Optional[UUID] = None) -> List[dict]:
        with SessionLocal() as db:
            q = select(AnswerRecordModel).where(AnswerRecordModel.user_id == user_id)
            if question_id:
                q = q.where(AnswerRecordModel.question_id == question_id)
            q = q.order_by(desc(AnswerRecordModel.submitted_at)).limit(50)
            rows = db.scalars(q).all()
            return [
                {
                    "id": str(r.id),
                    "question_id": str(r.question_id),
                    "user_answer": r.user_answer,
                    "is_correct": r.is_correct,
                    "score": float(r.score) if r.score else None,
                    "grading_method": r.grading_method,
                    "time_spent_seconds": r.time_spent_seconds,
                    "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                }
                for r in rows
            ]

    def list_user_resources(self, user_id: UUID) -> List[dict]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(LearningResourceModel).where(LearningResourceModel.user_id == user_id).order_by(desc(LearningResourceModel.created_at)).limit(100)
            ).all()
            results = []
            for row in rows:
                payload = row.target_profile or {}
                rp = payload.get("resource_payload", {})
                results.append({
                    "resource_id": str(row.id),
                    "title": row.title,
                    "resource_type": row.resource_type,
                    "knowledge_point": rp.get("knowledge_point", ""),
                    "difficulty": row.difficulty_level,
                    "quality_score": float(row.quality_score) if row.quality_score else 0,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            return results

    def delete_resource(self, user_id: UUID, resource_id: UUID) -> bool:
        with _safe_session() as db:
            row = db.get(LearningResourceModel, resource_id)
            if not row or row.user_id != user_id:
                return False
            db.delete(row)
            return True

    def emit_event(self, user_id: UUID, event_type: str, event_payload: dict, confidence: float, source_type: str = "agent", source_id: Optional[UUID] = None) -> UUID:
        with _safe_session() as db:
            row = ProfileEventModel(
                user_id=user_id,
                event_type=event_type,
                event_payload=event_payload,
                confidence=confidence,
                source_type=source_type,
                source_id=source_id,
                status="pending",
            )
            db.add(row)
            db.flush()
            return row.id

    def list_pending_events(self, user_id: UUID, limit: int = 20) -> List[dict]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(ProfileEventModel)
                .where(ProfileEventModel.user_id == user_id, ProfileEventModel.status == "pending")
                .order_by(ProfileEventModel.created_at)
                .limit(limit)
            ).all()
            return [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "event_payload": row.event_payload,
                    "confidence": float(row.confidence),
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                }
                for row in rows
            ]

    def list_events_by_type(self, user_id: UUID, event_type: str, limit: int = 50) -> List[dict]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(ProfileEventModel)
                .where(ProfileEventModel.user_id == user_id, ProfileEventModel.event_type == event_type)
                .order_by(desc(ProfileEventModel.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "event_payload": row.event_payload,
                    "confidence": float(row.confidence),
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def update_event_status(self, event_id: UUID, status: str, error_message: Optional[str] = None) -> None:
        with _safe_session() as db:
            row = db.get(ProfileEventModel, event_id)
            if row:
                row.status = status
                row.error_message = error_message
                if status == "applied":
                    row.applied_at = datetime.now(timezone.utc)

    def save_profile_and_update_event(
        self, profile: StudentProfile, event_id: UUID, event_status: str = "applied", error_message: Optional[str] = None
    ) -> StudentProfile:
        """Atomically save profile and update event status in a single transaction."""
        with _safe_session() as db:
            # Save profile
            latest = db.scalar(
                select(StudentProfileModel)
                .where(StudentProfileModel.user_id == profile.user_id)
                .order_by(desc(StudentProfileModel.profile_version))
                .with_for_update()
                .limit(1)
            )
            next_version = (latest.profile_version + 1) if latest else 1
            new_id = uuid4()
            row = StudentProfileModel(
                id=new_id,
                user_id=profile.user_id,
                profile_json=profile.model_dump(mode="json"),
                profile_version=next_version,
                completeness_score=profile.completeness_score,
                confidence_score=profile.confidence_score,
                updated_by=profile.dynamic_update.update_source,
            )
            db.add(row)
            if latest:
                db.add(
                    StudentProfileHistory(
                        profile_id=latest.id,
                        feature_name="student_profile",
                        old_value=latest.profile_json,
                        new_value=profile.model_dump(mode="json"),
                        change_reason=profile.dynamic_update.update_reason,
                        source_type="agent",
                        confidence_score=profile.confidence_score,
                    )
                )
            db.flush()

            # Update event status in the same transaction
            event_row = db.get(ProfileEventModel, event_id)
            if event_row:
                event_row.status = event_status
                event_row.error_message = error_message
                if event_status == "applied":
                    event_row.applied_at = datetime.now(timezone.utc)

        return profile.model_copy(update={"profile_id": new_id, "version": next_version})

    def save_assessment_snapshot(self, user_id: UUID, data: dict) -> dict:
        with _safe_session() as db:
            record = AssessmentSnapshotModel(
                user_id=user_id,
                mastery_score=data["mastery_score"],
                confidence=data["confidence"],
                stage=data.get("stage", "unknown"),
                weak_point_count=data.get("weak_point_count", 0),
                weak_topics=data.get("weak_topics", []),
            )
            db.add(record)
            db.flush()
            db.refresh(record)
            return {
                "id": str(record.id),
                "user_id": str(user_id),
                "mastery_score": float(record.mastery_score),
                "confidence": float(record.confidence),
                "stage": record.stage,
                "weak_point_count": record.weak_point_count,
                "weak_topics": record.weak_topics or [],
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

    def list_assessment_history(self, user_id: UUID, limit: int = 20) -> List[dict]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(AssessmentSnapshotModel)
                .where(AssessmentSnapshotModel.user_id == user_id)
                .order_by(desc(AssessmentSnapshotModel.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "id": str(r.id),
                    "mastery_score": float(r.mastery_score),
                    "confidence": float(r.confidence),
                    "stage": r.stage,
                    "weak_point_count": r.weak_point_count,
                    "weak_topics": r.weak_topics or [],
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]


class AutoSwitchRepository:
    def __init__(self) -> None:
        backend = get_settings().repository_backend
        self.delegate: VerticalLoopRepository = InMemoryVerticalLoopRepository() if backend == "memory" else PostgresVerticalLoopRepository()

    def _run(self, method: str, *args, **kwargs):
        return getattr(self.delegate, method)(*args, **kwargs)

    def get_user_by_username(self, username: str) -> Optional[UserDTO]:
        return self._run("get_user_by_username", username)

    def get_default_user(self) -> UserDTO:
        return self._run("get_default_user")

    def get_profile(self, user_id: UUID) -> Optional[StudentProfile]:
        return self._run("get_profile", user_id)

    def get_profile_by_id(self, profile_id: UUID) -> Optional[StudentProfile]:
        return self._run("get_profile_by_id", profile_id)

    def get_profile_versions(self, user_id: UUID) -> List[StudentProfile]:
        return self._run("get_profile_versions", user_id)

    def get_latest_profile_version(self, user_id: UUID) -> Optional[int]:
        return self._run("get_latest_profile_version", user_id)

    def save_profile(self, profile: StudentProfile) -> StudentProfile:
        return self._run("save_profile", profile)

    def snapshot_profile(self, user_id: UUID) -> StudentProfile:
        return self._run("snapshot_profile", user_id)

    def save_profile_in_place(self, profile_id: UUID, profile: StudentProfile) -> StudentProfile:
        return self._run("save_profile_in_place", profile_id, profile)

    def merge_conversation_profile(self, conversation_profile_id: UUID, user_id: UUID) -> Optional[StudentProfile]:
        return self._run("merge_conversation_profile", conversation_profile_id, user_id)

    def create_path(self, user_id: UUID, goal: str, subject: str, base_agent_id: Optional[UUID] = None) -> LearningPath:
        return self._run("create_path", user_id, goal, subject, base_agent_id)

    def get_path(self, user_id: UUID) -> Optional[LearningPath]:
        return self._run("get_path", user_id)

    def complete_path_node(self, user_id: UUID, node_id: UUID) -> Optional[LearningPath]:
        return self._run("complete_path_node", user_id, node_id)

    def start_learning_node(self, user_id: UUID, knowledge_point: str) -> Optional[LearningPath]:
        return self._run("start_learning_node", user_id, knowledge_point)

    def create_workflow(self, user_id: UUID, input_payload: Optional[dict] = None, emit_progress=None) -> AgentWorkflow:
        return self._run("create_workflow", user_id, input_payload, emit_progress=emit_progress)

    def get_workflow(self, workflow_id: UUID) -> Optional[AgentWorkflow]:
        return self._run("get_workflow", workflow_id)

    def create_resource(self, user_id: UUID, knowledge_point: str, resource_type: ResourceType, difficulty: str, base_agent_id: Optional[UUID] = None, conversation_id: Optional[UUID] = None) -> LearningResource:
        return self._run("create_resource", user_id, knowledge_point, resource_type, difficulty, base_agent_id, conversation_id)

    def get_resource(self, resource_id: UUID) -> Optional[LearningResource]:
        return self._run("get_resource", resource_id)

    def create_recommendations(self, user_id: UUID) -> List[Recommendation]:
        return self._run("create_recommendations", user_id)

    def get_recommendations(self, user_id: UUID) -> List[Recommendation]:
        return self._run("get_recommendations", user_id)

    def get_pending_suggestions(self, user_id: UUID) -> List[dict]:
        return self._run("get_pending_suggestions", user_id)

    def consume_suggested_generation(self, user_id: UUID, rec: dict) -> None:
        return self._run("consume_suggested_generation", user_id, rec)

    def save_learning_record(self, record: LearningRecordCreate) -> Optional[UUID]:
        return self._run("save_learning_record", record)

    def list_learning_records(self, user_id: UUID) -> List[dict]:
        return self._run("list_learning_records", user_id)

    def list_questions(self, knowledge_point: Optional[str] = None, question_type: Optional[str] = None, subject: Optional[str] = None, difficulty: Optional[str] = None) -> List[dict]:
        return self._run("list_questions", knowledge_point, question_type, subject, difficulty)

    def get_question(self, question_id: UUID) -> Optional[dict]:
        return self._run("get_question", question_id)

    def save_question(self, data: dict) -> dict:
        return self._run("save_question", data)

    def delete_question(self, question_id: UUID) -> bool:
        return self._run("delete_question", question_id)

    def save_answer_record(self, data: dict) -> dict:
        return self._run("save_answer_record", data)

    def get_user_answer_history(self, user_id: UUID, question_id: Optional[UUID] = None) -> List[dict]:
        return self._run("get_user_answer_history", user_id, question_id)

    def list_user_resources(self, user_id: UUID) -> List[dict]:
        return self._run("list_user_resources", user_id)

    def delete_resource(self, user_id: UUID, resource_id: UUID) -> bool:
        return self._run("delete_resource", user_id, resource_id)

    def emit_event(self, user_id: UUID, event_type: str, event_payload: dict, confidence: float, source_type: str = "agent", source_id: Optional[UUID] = None) -> UUID:
        return self._run("emit_event", user_id, event_type, event_payload, confidence, source_type=source_type, source_id=source_id)

    def list_pending_events(self, user_id: UUID, limit: int = 20) -> List[dict]:
        return self._run("list_pending_events", user_id, limit)

    def list_events_by_type(self, user_id: UUID, event_type: str, limit: int = 50) -> List[dict]:
        return self._run("list_events_by_type", user_id, event_type, limit)

    def update_event_status(self, event_id: UUID, status: str, error_message: Optional[str] = None) -> None:
        return self._run("update_event_status", event_id, status, error_message)

    def save_profile_and_update_event(
        self, profile: StudentProfile, event_id: UUID, event_status: str = "applied", error_message: Optional[str] = None
    ) -> StudentProfile:
        return self._run("save_profile_and_update_event", profile, event_id, event_status, error_message)

    def save_assessment_snapshot(self, user_id: UUID, data: dict) -> dict:
        return self._run("save_assessment_snapshot", user_id, data)

    def list_assessment_history(self, user_id: UUID, limit: int = 20) -> List[dict]:
        return self._run("list_assessment_history", user_id, limit)


repository: VerticalLoopRepository = AutoSwitchRepository()
