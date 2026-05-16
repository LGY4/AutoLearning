from __future__ import annotations

from typing import Dict,  List,  Optional

from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import AgentName
from app.db.models import BaseAgentModel
from app.db.session import SessionLocal
from app.schemas.base_agent import BaseAgentCreateRequest, BaseAgentProfile


SYSTEM_AGENT_ID = UUID("00000000-0000-0000-0000-000000000001")
SYSTEM_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_MEMORY_BASE_AGENTS: Dict[UUID, List[BaseAgentProfile]] = {}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _system_agent() -> BaseAgentProfile:
    now = _now_iso()
    return BaseAgentProfile(
        agent_id=SYSTEM_AGENT_ID,
        user_id=SYSTEM_USER_ID,
        name="系统默认基层智能体",
        description="统一教学型基层智能体，供画像、路径、资源、辅导等 Agent 复用。",
        system_prompt="你是个性化学习系统的基层智能体。输出必须贴合学生画像、知识点与学习目标，优先结构化、可执行、少废话。",
        applies_to=[
            AgentName.PROFILE,
            AgentName.PATH,
            AgentName.DOCUMENT,
            AgentName.QUIZ,
            AgentName.MINDMAP,
            AgentName.VIDEO,
            AgentName.CODE,
            AgentName.RECOMMENDATION,
            AgentName.TUTOR,
        ],
        model_provider="spark",
        output_style="structured",
        is_system=True,
        created_at=now,
        updated_at=now,
    )


def _model_to_profile(row: BaseAgentModel) -> BaseAgentProfile:
    return BaseAgentProfile(
        agent_id=row.id,
        user_id=row.user_id,
        name=row.name,
        description=row.description,
        system_prompt=row.system_prompt,
        applies_to=[AgentName(item) for item in (row.applies_to or [])],
        model_provider=row.model_provider,
        output_style=row.output_style,
        is_system=row.is_system,
        created_at=row.created_at.isoformat() if row.created_at else _now_iso(),
        updated_at=row.updated_at.isoformat() if row.updated_at else _now_iso(),
    )


def list_base_agents(user_id: UUID) -> List[BaseAgentProfile]:
    if get_settings().repository_backend == "memory":
        return [_system_agent(), *_MEMORY_BASE_AGENTS.get(user_id, [])]
    with SessionLocal() as db:
        rows = db.scalars(
            select(BaseAgentModel)
            .where(BaseAgentModel.user_id == user_id)
            .order_by(BaseAgentModel.is_system.desc(), BaseAgentModel.created_at.asc())
        ).all()
        agents = [_system_agent()]
        agents.extend(_model_to_profile(row) for row in rows if not row.is_system)
        return agents


def create_base_agent(request: BaseAgentCreateRequest) -> BaseAgentProfile:
    item = BaseAgentModel(
        id=uuid4(),
        user_id=request.user_id,
        name=request.name,
        description=request.description,
        system_prompt=request.system_prompt,
        applies_to=[item.value for item in (request.applies_to or [
            AgentName.PROFILE,
            AgentName.PATH,
            AgentName.DOCUMENT,
            AgentName.QUIZ,
            AgentName.MINDMAP,
            AgentName.VIDEO,
            AgentName.CODE,
            AgentName.RECOMMENDATION,
            AgentName.TUTOR,
        ])],
        model_provider=request.model_provider,
        output_style=request.output_style,
        is_system=False,
    )
    if get_settings().repository_backend == "memory":
        profile = BaseAgentProfile(
            agent_id=item.id,
            user_id=item.user_id,
            name=item.name,
            description=item.description,
            system_prompt=item.system_prompt,
            applies_to=list(item.applies_to),
            model_provider=item.model_provider,
            output_style=item.output_style,
            is_system=False,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        _MEMORY_BASE_AGENTS.setdefault(request.user_id, []).append(profile)
        return profile
    with SessionLocal() as db:
        db.add(item)
        db.commit()
        db.refresh(item)
        return _model_to_profile(item)


def get_base_agent(user_id: UUID, agent_id: Optional[UUID]) -> Optional[BaseAgentProfile]:
    if agent_id is None:
        return None
    if agent_id == SYSTEM_AGENT_ID:
        return _system_agent()
    if get_settings().repository_backend == "memory":
        return next((item for item in _MEMORY_BASE_AGENTS.get(user_id, []) if item.agent_id == agent_id), None)
    with SessionLocal() as db:
        row = db.get(BaseAgentModel, agent_id)
        if row and row.user_id == user_id:
            return _model_to_profile(row)
    return None
