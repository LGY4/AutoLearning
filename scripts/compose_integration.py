from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
API = "http://127.0.0.1:8000/api/v1"


def run_compose(*args: str) -> str:
    completed = subprocess.run(
        ["docker", "compose", *args],
        cwd=INFRA,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def request_json(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{API}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_api() -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            request_json("/system/runtime")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("Backend API did not become ready within 180 seconds")


def wait_for_task(task_id: str) -> dict:
    deadline = time.monotonic() + 180
    last_payload: dict | None = None
    while time.monotonic() < deadline:
        payload = request_json(f"/resources/tasks/{task_id}")["data"]
        last_payload = payload
        if payload["status"] == "success":
            return payload
        if payload["status"] in {"failed", "failure", "broker_unavailable"}:
            raise RuntimeError(f"Celery task failed: {payload}")
        time.sleep(2)
    raise RuntimeError(f"Celery task timed out: {last_payload}")


def main() -> None:
    wait_for_api()
    ps = run_compose("ps", "--format", "json")
    runtime = request_json("/system/runtime")["data"]
    knowledge = request_json("/knowledge/status")["data"]
    me = request_json("/auth/me")["data"]

    async_response = request_json(
        "/resources/generate-async",
        method="POST",
        payload={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["document", "mindmap", "quiz", "reading", "code_case"],
            "difficulty": "beginner",
        },
    )["data"]
    if async_response["status"] == "broker_unavailable":
        raise RuntimeError(f"Redis/Celery is unavailable: {async_response}")
    task = wait_for_task(async_response["celery_task_id"])

    alembic_version = run_compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "autolearning",
        "-d",
        "autolearning",
        "-tAc",
        "select version_num from alembic_version",
    )
    redis_ping = run_compose("exec", "-T", "redis", "redis-cli", "ping")

    with urllib.request.urlopen("http://127.0.0.1:5173", timeout=30) as response:
        frontend_status = response.status

    checks = {
        "compose_ps": ps,
        "repository_backend": runtime["repository_backend"],
        "knowledge_engine": knowledge["active_engine"],
        "knowledge_chunks": knowledge["indexed_chunks"],
        "embedding_mode": knowledge["embedding"]["active_mode"],
        "celery_task_status": task["status"],
        "celery_resource_count": len((task.get("result") or {}).get("resources", [])),
        "alembic_version": alembic_version,
        "redis_ping": redis_ping,
        "frontend_status": frontend_status,
    }

    assert checks["repository_backend"] == "postgres", checks
    assert checks["knowledge_engine"] == "chroma", checks
    assert checks["knowledge_chunks"] >= 10, checks
    assert checks["celery_task_status"] == "success", checks
    assert checks["celery_resource_count"] >= 5, checks
    assert "20260430_0001" in checks["alembic_version"], checks
    assert checks["redis_ping"] == "PONG", checks
    assert checks["frontend_status"] == 200, checks
    print(json.dumps({"status": "passed", "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False, indent=2))
        sys.exit(1)
