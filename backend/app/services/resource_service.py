from __future__ import annotations

from typing import Dict,  Optional

import logging
import threading
import time
from collections.abc import Callable
from uuid import UUID
from uuid import uuid4
import socket
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.enums import ResourceStatus, ResourceType
from app.db.models import LearningResourceModel, ResourceVersion
from app.repositories.vertical_loop_repository import repository, _safe_session
from app.schemas.resource import (
    AsyncResourceGenerateResponse,
    AsyncTaskStatusResponse,
    LearningResource,
    ResourceGenerateRequest,
    ResourceGenerateResponse,
)

logger = logging.getLogger(__name__)

# Local cache for fallback task results when Celery/Redis is unavailable
_fallback_results: Dict[str, dict] = {}
_fallback_lock = threading.Lock()
_FALLBACK_MAX_SIZE = 100
_FALLBACK_TTL_SECONDS = 3600  # 1 hour


def _cleanup_fallback_results() -> None:
    """Remove expired entries and enforce max-size (must be called under lock)."""
    now = time.monotonic()
    expired = [k for k, v in _fallback_results.items() if now - v.get("_created_at", 0) > _FALLBACK_TTL_SECONDS]
    for k in expired:
        del _fallback_results[k]
    # If still over max, remove oldest entries
    while len(_fallback_results) > _FALLBACK_MAX_SIZE:
        oldest = min(_fallback_results, key=lambda k: _fallback_results[k].get("_created_at", 0))
        del _fallback_results[oldest]


def _redis_available() -> bool:
    parsed = urlparse(get_settings().redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def generate_resources(
    request: ResourceGenerateRequest,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> ResourceGenerateResponse:
    def emit(payload: dict) -> None:
        if emit_progress is not None:
            emit_progress(payload)

    workflow = repository.create_workflow(
        request.user_id,
        {
            "subject": request.subject,
            "knowledge_point": request.knowledge_point,
            "resource_types": [resource_type.value for resource_type in request.resource_types],
            "base_agent_id": str(request.base_agent_id) if request.base_agent_id else None,
        },
        emit_progress=emit_progress,
    )
    resources = []
    total = len(request.resource_types)
    for idx, resource_type in enumerate(request.resource_types):
        pct = int(20 + 60 * (idx / max(total, 1)))
        emit(
            {
                "agent_name": resource_type.value,
                "stage": "resource_generate",
                "status": "running",
                "progress": pct,
                "hint": f"{resource_type.value} agent 正在生成（{idx + 1}/{total}）...",
            }
        )
        try:
            resource = repository.create_resource(
                user_id=request.user_id,
                knowledge_point=request.knowledge_point,
                resource_type=resource_type,
                difficulty=request.difficulty,
                base_agent_id=request.base_agent_id,
            )
        except Exception as exc:
            logger.error("Resource generation failed for %s: %s", resource_type.value, exc)
            resource = LearningResource(
                resource_id=uuid4(),
                user_id=request.user_id,
                knowledge_point=request.knowledge_point,
                resource_type=resource_type,
                title=f"{request.knowledge_point} - {resource_type.value}",
                difficulty=request.difficulty,
                content=f"生成失败：{exc}",
                recommendation_reason="生成异常",
                generated_by="error",
                quality_score=0.0,
                status=ResourceStatus.FAILED,
                metadata={"error": str(exc)},
            )
        is_failed = getattr(resource, "status", None) == ResourceStatus.FAILED
        emit(
            {
                "agent_name": resource_type.value,
                "stage": "resource_generate",
                "status": "error" if is_failed else "done",
                "progress": pct + int(60 / max(total, 1)),
                "hint": f"{resource_type.value} 生成失败。" if is_failed else f"{resource_type.value} 已生成完成。",
                "data": {"resource": resource.model_dump(mode="json")},
            }
        )
        resources.append(resource)
    repository.create_recommendations(request.user_id)
    emit(
        {
            "agent_name": "recommendation_agent",
            "stage": "recommendation_generate",
            "status": "done",
            "progress": 100,
            "hint": "推荐 Agent 已完成资源排序与推送。",
        }
    )
    first_task_id = workflow.tasks[0].task_id if workflow.tasks else str(uuid4())
    return ResourceGenerateResponse(
        workflow_id=workflow.workflow_id,
        task_id=first_task_id,
        status=workflow.status,
        resources=resources,
    )


def get_resource(resource_id: UUID) -> Optional[LearningResource]:
    return repository.get_resource(resource_id)


def create_user_resource(
    user_id: UUID,
    title: str,
    content: str,
    resource_type: str = "document",
    filename: str = "upload",
) -> LearningResource:
    resource_id = uuid4()
    try:
        rt = ResourceType(resource_type)
    except ValueError:
        rt = ResourceType.DOCUMENT
    # LLM 快速质量评估
    quality_score = 0.5  # 默认中等
    try:
        from app.services.model_gateway import generate_json
        eval_prompt = (
            f"请对以下学习资源的质量打分（0-100的整数），评估维度：内容完整性、知识准确性、学习价值。\n"
            f"标题：{title}\n类型：{resource_type}\n内容前500字：\n{content[:500]}\n"
            f'只返回JSON：{{"score": 整数}}'
        )
        eval_result = generate_json(eval_prompt, required_keys=["score"])
        raw = int(eval_result.get("score", 50))
        quality_score = max(0.1, min(1.0, raw / 100))
    except Exception:
        logger.warning("Quality assessment failed for '%s', using default score", title, exc_info=True)

    resource = LearningResource(
        resource_id=resource_id,
        user_id=user_id,
        knowledge_point=title,
        resource_type=rt,
        title=title,
        difficulty="custom",
        content=content,
        recommendation_reason="用户上传",
        generated_by="user_upload",
        quality_score=quality_score,
        status=ResourceStatus.PUBLISHED,
        metadata={"filename": filename},
    )
    with _safe_session() as db:
        db.add(
            LearningResourceModel(
                id=resource_id,
                user_id=user_id,
                title=title,
                resource_type=rt.value,
                content_summary=content[:300],
                difficulty_level="custom",
                target_profile={"resource_payload": resource.model_dump(mode="json")},
                status=ResourceStatus.PUBLISHED.value,
                quality_score=quality_score,
            )
        )
        db.flush()
        db.add(
            ResourceVersion(
                resource_id=resource_id,
                version_no=1,
                content=content,
                change_reason="用户上传",
            )
        )
    return resource


def enqueue_resource_generation(request: ResourceGenerateRequest) -> AsyncResourceGenerateResponse:
    if not _redis_available():
        # Fall back to sync generation in a background thread
        task_id = f"local-fallback-{uuid4()}"
        now = time.monotonic()
        with _fallback_lock:
            _cleanup_fallback_results()
            _fallback_results[task_id] = {"status": "pending", "result": None, "_created_at": now}

        def _run_sync():
            with _fallback_lock:
                _fallback_results[task_id] = {"status": "running", "result": None, "_created_at": now}
            try:
                response = generate_resources(request)
                with _fallback_lock:
                    _fallback_results[task_id] = {
                        "status": "done",
                        "result": response.model_dump(mode="json"),
                        "_created_at": now,
                    }
            except Exception as exc:
                logger.error("Sync fallback generation failed: %s", exc)
                with _fallback_lock:
                    _fallback_results[task_id] = {
                        "status": "failed",
                        "result": {"message": str(exc), "error": str(exc)},
                        "_created_at": now,
                    }

        threading.Thread(target=_run_sync, daemon=True).start()
        return AsyncResourceGenerateResponse(
            celery_task_id=task_id,
            status="queued",
            message="资源生成任务已提交（本地同步模式）",
        )
    from app.tasks.agent_tasks import generate_resources_task

    task = generate_resources_task.delay(request.model_dump(mode="json"))
    return AsyncResourceGenerateResponse(
        celery_task_id=task.id,
        status="queued",
        message="资源生成任务已进入 Celery 队列",
    )


def get_async_generation_status(celery_task_id: str) -> AsyncTaskStatusResponse:
    if celery_task_id.startswith("local-fallback-"):
        with _fallback_lock:
            entry = _fallback_results.get(celery_task_id)
        if not entry:
            return AsyncTaskStatusResponse(
                celery_task_id=celery_task_id,
                status="unknown",
                result={"message": "任务不存在"},
            )
        return AsyncTaskStatusResponse(
            celery_task_id=celery_task_id,
            status=entry["status"],
            result=entry["result"],
        )
    try:
        from celery.result import AsyncResult
        from app.tasks.celery_app import celery_app

        result = AsyncResult(celery_task_id, app=celery_app)
        payload = result.result if result.ready() and isinstance(result.result, dict) else None
        return AsyncTaskStatusResponse(
            celery_task_id=celery_task_id,
            status=result.status.lower(),
            result=payload,
        )
    except Exception as exc:
        return AsyncTaskStatusResponse(
            celery_task_id=celery_task_id,
            status="error",
            result={"message": f"Celery 任务状态查询失败：{exc}"},
        )
