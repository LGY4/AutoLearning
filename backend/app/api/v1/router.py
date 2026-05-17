from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import (
    agents,
    agent_workflows,
    auth,
    bilibili,
    conversations,
    courses,
    knowledge,
    learning,
    learning_paths,
    learning_records,
    profiles,
    recommendations,
    resources,
    system,
    tutor,
    tts,
    video,
)


api_router = APIRouter()
# Auth endpoints are public (register, login, me handles its own auth)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# All other endpoints require authentication
_auth = [Depends(get_current_user)]
api_router.include_router(agents.router, prefix="/agents", tags=["agents"], dependencies=_auth)
api_router.include_router(bilibili.router, prefix="/bilibili", tags=["bilibili"], dependencies=_auth)
api_router.include_router(courses.router, prefix="/courses", tags=["courses"], dependencies=_auth)
api_router.include_router(learning.router, prefix="/learning", tags=["learning"], dependencies=_auth)
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"], dependencies=_auth)
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"], dependencies=_auth)
api_router.include_router(learning_paths.router, prefix="/learning-paths", tags=["learning-paths"], dependencies=_auth)
api_router.include_router(resources.router, prefix="/resources", tags=["resources"], dependencies=_auth)
api_router.include_router(agent_workflows.router, prefix="/agent-workflows", tags=["agent-workflows"], dependencies=_auth)
api_router.include_router(learning_records.router, prefix="/learning-records", tags=["learning-records"], dependencies=_auth)
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"], dependencies=_auth)
api_router.include_router(tutor.router, prefix="/tutor", tags=["tutor"], dependencies=_auth)
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"], dependencies=_auth)
api_router.include_router(system.router, prefix="/system", tags=["system"], dependencies=_auth)
api_router.include_router(tts.router, prefix="/tts", tags=["tts"], dependencies=_auth)
api_router.include_router(video.public_router, prefix="/video", tags=["video"])
api_router.include_router(video.router, prefix="/video", tags=["video"], dependencies=_auth)
