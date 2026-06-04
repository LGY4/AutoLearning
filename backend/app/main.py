from __future__ import annotations

from typing import Dict

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import ServiceError, error_http_status, friendly_message
from app.core.logging_config import setup_logging

settings = get_settings()
setup_logging(settings.environment)

logger = logging.getLogger(__name__)


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(
    title=settings.app_name,
    description="Personalized learning resource generation and multi-agent learning system.",
    version="0.1.0",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    default_response_class=Utf8JSONResponse,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

if settings.cors_origins:
    _cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
else:
    _cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"code": 42901, "error_code": "LLM_RATE_LIMITED", "message": "请求过于频繁，请稍后重试", "data": None, "trace_id": None},
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)

# Serve generated video/image files
_data_dir = Path(__file__).resolve().parent / "data"
_generated_dir = _data_dir / "generated_videos"
_generated_dir.mkdir(parents=True, exist_ok=True)
_images_dir = _data_dir / "images"
_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/generated", StaticFiles(directory=str(_generated_dir)), name="generated")
app.mount("/static/images", StaticFiles(directory=str(_images_dir)), name="images")


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    logger.warning("ServiceError on %s %s: [%s] %s", request.method, request.url.path, exc.code.value, exc.detail)
    return JSONResponse(
        status_code=error_http_status(exc.code),
        content={
            "code": error_http_status(exc.code) * 100 + 1,
            "error_code": exc.code.value,
            "message": friendly_message(exc.code),
            "data": None,
            "trace_id": None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": 50001, "error_code": "INTERNAL_ERROR", "message": "服务器内部错误，请稍后重试", "data": None, "trace_id": None},
    )


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz")
def readiness_check() -> Dict[str, object]:
    """Readiness probe — verifies downstream dependencies are reachable."""
    checks: Dict[str, str] = {}
    overall = "ok"

    # Check database
    try:
        from app.db.session import SessionLocal
        if SessionLocal is None:
            checks["postgres"] = "skipped (memory backend)"
        else:
            from sqlalchemy import text
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = "error" if settings.environment == "production" else f"error: {exc}"
        overall = "degraded"

    # Check Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.redis_url, socket_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = "error" if settings.environment == "production" else f"error: {exc}"
        overall = "degraded"

    status_code = 200 if overall == "ok" else 503
    from fastapi import Response
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
    )
