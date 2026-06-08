from __future__ import annotations

import os

os.environ["MODEL_PROVIDER"] = "mock"
os.environ["REPOSITORY_BACKEND"] = "memory"
os.environ["RAG_BACKEND"] = "memory"

import redis as redis_lib
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_readyz_skips_redis_when_memory_backend(monkeypatch) -> None:
    def raise_unavailable(*_args, **_kwargs):
        raise OSError("redis unavailable")

    monkeypatch.setattr(redis_lib, "from_url", raise_unavailable)

    response = client.get("/readyz")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["postgres"].startswith("skipped")
    assert payload["checks"]["redis"].startswith("skipped")
