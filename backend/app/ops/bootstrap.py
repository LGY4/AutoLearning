from __future__ import annotations

from typing import Optional

import socket
import time
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.ops.import_knowledge_base import import_knowledge_base
from app.ops.seed_demo_data import seed_demo_data


def validate_runtime_configuration() -> None:
    settings = get_settings()
    if settings.model_provider == "spark":
        missing = [
            name
            for name, value in {
                "SPARK_APP_ID": settings.spark_app_id,
                "SPARK_API_KEY": settings.spark_api_key,
                "SPARK_API_SECRET": settings.spark_api_secret,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Spark configuration is missing: {', '.join(missing)}")


def wait_for_tcp(name: str, url: str, timeout_seconds: int = 60) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port
    if port is None:
        port = 5432 if parsed.scheme.startswith("postgres") else 6379

    deadline = time.monotonic() + timeout_seconds
    last_error: Optional[OSError] = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"{name} is not reachable at {host}:{port}: {last_error}")


def run_migrations() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


def bootstrap_application(seed_vertical_loop: bool = False) -> dict:
    validate_runtime_configuration()
    settings = get_settings()
    if settings.repository_backend == "postgres":
        wait_for_tcp("PostgreSQL", settings.database_url)
        wait_for_tcp("Redis", settings.redis_url)
        run_migrations()
    seed_result = seed_demo_data(seed_vertical_loop=seed_vertical_loop)
    rag_result = import_knowledge_base(force=False)
    return {"seed": seed_result, "rag": rag_result}
