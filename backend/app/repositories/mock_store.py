from __future__ import annotations

from typing import Dict,  List,  Optional

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4, uuid5


class ProfileVersionConflictError(Exception):
    """Raised when profile version conflicts during save (optimistic lock)."""
    pass

from app.core.enums import (
    AgentName,
    AgentTaskStatus,
    ResourceType,
    UserRole,
)
from app.schemas.auth import UserDTO
from app.schemas.learning_path import LearningPath
from app.schemas.profile import (
    StudentProfile,
)
from app.schemas.recommendation import Recommendation
from app.schemas.resource import LearningResource
from app.schemas.workflow import AgentWorkflow
from app.services import agent_runtime
from app.services.base_agent_service import get_base_agent
from app.services.runtime_support import resource_score
from app.workflows.learning_graph import run_workflow


_UUID_NAMESPACE = UUID("a1a2a3a4-b1b2-c1c2-d1d2-e1e2e3e4e5e6")

# Archetype → user mapping. Each archetype gets one representative user.
_ARCHETYPE_USER_MAP = [
    ("student001", "beginner_visual"),
    ("student002", "beginner_hands_on"),
    ("student003", "intermediate_theory_strong"),
    ("student004", "intermediate_practice_strong"),
    ("student005", "intermediate_forgetful"),
    ("student006", "advanced_interview"),
    ("student007", "advanced_research"),
    ("student008", "struggling_multi_weak"),
]

# student001 is the primary demo user (backward compatible)
DEMO_USER_ID = uuid5(_UUID_NAMESPACE, "student001")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _user_id_for(username: str) -> UUID:
    return uuid5(_UUID_NAMESPACE, username)


class MockStore:
    """In-memory fallback store with the same contract as the PostgreSQL repository."""

    def __init__(self) -> None:
        from app.services.learner_archetypes import get_archetype

        self.users: Dict[UUID, UserDTO] = {}
        self.profiles: Dict[UUID, StudentProfile] = {}
        self.profile_versions: Dict[UUID, List[StudentProfile]] = {}
        self.learning_records: List[dict] = []

        # Create one user per archetype
        for username, archetype_id in _ARCHETYPE_USER_MAP:
            uid = _user_id_for(username)
            self.users[uid] = UserDTO(id=uid, username=username, role=UserRole.STUDENT)
            profile = self._build_archetype_profile(uid, archetype_id, get_archetype)
            self.profiles[uid] = profile
            self.profile_versions[uid] = [profile.model_copy(deep=True)]

            # Generate learning records from archetype's recent_scores and weak_topics
            self._seed_learning_records(uid, archetype_id, get_archetype)

        self.paths: Dict[UUID, LearningPath] = {}
        self.resources: Dict[UUID, LearningResource] = {}
        self.workflows: Dict[UUID, AgentWorkflow] = {}
        self.recommendations: Dict[UUID, List[Recommendation]] = {}
        self.questions: List[dict] = self._load_question_bank()
        self.answer_records: List[dict] = []
        self.profile_history: Dict[UUID, List[dict]] = {}
        self.resource_versions: Dict[UUID, List[dict]] = {}
        self.profile_events: List[dict] = []

    def _load_question_bank(self) -> List[dict]:
        path = Path(__file__).resolve().parents[1] / "data" / "question_bank.json"
        if not path.exists():
            return []
        questions = json.loads(path.read_text(encoding="utf-8"))
        for q in questions:
            if not q.get("id"):
                q["id"] = str(uuid4())
        return questions

    def _build_archetype_profile(
        self,
        user_id: UUID,
        archetype_id: str,
        get_archetype_fn,
    ) -> StudentProfile:
        archetype = get_archetype_fn(archetype_id)
        # Create a copy so we don't mutate the archetype registry
        data = dict(archetype)
        data["profile_id"] = uuid4()
        data["user_id"] = user_id
        data["version"] = 1
        return StudentProfile(**data)

    def _seed_learning_records(
        self,
        user_id: UUID,
        archetype_id: str,
        get_archetype_fn,
    ) -> None:
        """Generate learning records from archetype's recent_scores and weak_topics."""
        archetype = get_archetype_fn(archetype_id)
        beh = archetype.get("learning_behavior", {})
        kp = archetype.get("knowledge_profile", {})
        pref = archetype.get("learning_preference", {})

        scores = beh.get("recent_scores", [])
        weak_topics = kp.get("weak_topics", [])
        if not scores or not weak_topics:
            return

        # Pick the top preferred resource type
        resource_prefs = pref.get("resource_preference", {})
        preferred_type = max(resource_prefs, key=resource_prefs.get) if resource_prefs else "document"

        now = datetime.now(timezone.utc)
        for i, (score, topic) in enumerate(zip(scores, weak_topics)):
            self.learning_records.append({
                "id": uuid4(),
                "user_id": user_id,
                "knowledge_point": topic,
                "resource_type": preferred_type,
                "score": score,
                "is_correct": score >= 60,
                "time_spent_seconds": 300 + i * 60,
                "created_at": (now - timedelta(days=len(scores) - i)).isoformat(timespec="seconds"),
            })

    def get_user_by_username(self, username: str) -> Optional[UserDTO]:
        return next((user for user in self.users.values() if user.username == username), None)

    def upsert_profile(self, profile: StudentProfile) -> StudentProfile:
        existing = self.profiles.get(profile.user_id)
        if existing and profile.version != existing.version + 1 and profile.version != existing.version:
            raise ProfileVersionConflictError(
                f"Version conflict: expected {existing.version + 1}, got {profile.version}"
            )
        if existing:
            self.profile_history.setdefault(profile.user_id, []).append({
                "old_value": existing.model_dump(mode="json"),
                "new_value": profile.model_dump(mode="json"),
                "change_reason": profile.dynamic_update.update_reason,
                "timestamp": now_iso(),
            })
        self.profiles[profile.user_id] = profile
        self.profile_versions.setdefault(profile.user_id, []).append(profile.model_copy(deep=True))
        return profile

    def create_demo_path(self, user_id: UUID, goal: str, subject: str, base_agent_id: Optional[UUID] = None) -> LearningPath:
        profile = self.profiles.get(user_id)
        base_agent = get_base_agent(user_id, base_agent_id)
        path = agent_runtime.build_learning_path(user_id, goal, subject, profile, base_agent=base_agent)
        self.paths[user_id] = path
        return path

    def complete_path_node(self, user_id: UUID, node_id: UUID) -> Optional[LearningPath]:
        """Mark a path node as completed and unlock the next node."""
        from app.core.enums import PathNodeStatus
        path = self.paths.get(user_id)
        if path is None:
            return None
        updated_nodes = []
        found = False
        for i, node in enumerate(path.nodes):
            if node.node_id == node_id:
                updated_nodes.append(node.model_copy(update={"status": PathNodeStatus.COMPLETED}))
                found = True
            elif found and node.status == PathNodeStatus.LOCKED:
                updated_nodes.append(node.model_copy(update={"status": PathNodeStatus.AVAILABLE}))
                found = False
            else:
                updated_nodes.append(node)
        if not found:
            return path
        new_path = path.model_copy(update={"nodes": updated_nodes})
        self.paths[user_id] = new_path
        return new_path

    def create_workflow(self, user_id: UUID, input_payload: Optional[dict] = None) -> AgentWorkflow:
        workflow_id = uuid4()
        tasks, events = run_workflow(workflow_id, user_id, input_payload)
        workflow = AgentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            status=AgentTaskStatus.SUCCESS,
            current_agent=AgentName.RECOMMENDATION,
            tasks=tasks,
            events=events,
            logs=[event.model_dump(mode="json") for event in events],
        )
        self.workflows[workflow_id] = workflow
        return workflow

    def create_resource(
        self,
        user_id: UUID,
        knowledge_point: str,
        resource_type: ResourceType,
        difficulty: str,
        base_agent_id: Optional[UUID] = None,
    ) -> LearningResource:
        profile = self.profiles.get(user_id)
        subject = profile.learning_goal.target_course if profile and profile.learning_goal.target_course else "通用学习"
        base_agent = get_base_agent(user_id, base_agent_id)
        resource = agent_runtime.build_learning_resource(user_id, subject, knowledge_point, resource_type, difficulty, profile, base_agent=base_agent)
        self.resources[resource.resource_id] = resource
        return resource

    def create_recommendations(self, user_id: UUID) -> List[Recommendation]:
        profile = self.profiles.get(user_id)
        recommendations: List[Recommendation] = []
        for resource in self.resources.values():
            if resource.user_id != user_id:
                continue
            score, evidence = resource_score(resource, profile)
            recommendations.append(
                Recommendation(
                    recommendation_id=uuid4(),
                    user_id=user_id,
                    resource_id=resource.resource_id,
                    title=resource.title,
                    score=score,
                    recommend_reason={
                        "main_reason": "根据薄弱点、资源偏好和资源质量排序",
                        "weak_point": resource.knowledge_point,
                        "matched_profile": profile.learning_preference.learning_style if profile else "unknown",
                        "evidence": evidence,
                    },
                )
            )
        recommendations.sort(key=lambda item: item.score, reverse=True)
        self.recommendations[user_id] = recommendations
        return recommendations


store = MockStore()
