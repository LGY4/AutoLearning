from __future__ import annotations

from typing import Dict

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import ServiceError, friendly_message

logger = logging.getLogger(__name__)


settings = get_settings()


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title=settings.app_name,
    description="Personalized learning resource generation and multi-agent learning system.",
    version="0.1.0",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    default_response_class=Utf8JSONResponse,
)

_cors_origins = (
    ["*"]
    if settings.environment != "production"
    else ["http://localhost:5173", "http://127.0.0.1:5173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        status_code=503,
        content={
            "detail": friendly_message(exc.code),
            "error_code": exc.code.value,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试", "error_code": "INTERNAL_ERROR"},
    )


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
