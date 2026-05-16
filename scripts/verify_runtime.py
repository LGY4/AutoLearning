from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8000/api/v1"


def request_json(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_api() -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            request_json("/system/runtime")
            return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise RuntimeError("Backend API is not reachable at http://127.0.0.1:8000")


def main() -> None:
    wait_for_api()
    runtime = request_json("/system/runtime")["data"]
    knowledge = request_json("/knowledge/status")["data"]
    me = request_json("/auth/me")["data"]
    profile = request_json(f"/profiles/{me['id']}")["data"]
    path = request_json(
        "/learning-paths/generate",
        method="POST",
        payload={
            "user_id": me["id"],
            "target_goal": profile["learning_goal"]["current_goal"],
            "subject": profile["learning_goal"]["target_course"],
        },
    )["data"]
    resources = request_json(
        "/resources/generate",
        method="POST",
        payload={
            "user_id": me["id"],
            "subject": profile["learning_goal"]["target_course"],
            "knowledge_point": "栈的基本概念",
            "resource_types": ["document", "mindmap", "quiz", "reading", "code_case"],
            "difficulty": "beginner",
        },
    )["data"]
    workflow = request_json(f"/agent-workflows/{resources['workflow_id']}")["data"]
    events = request_json(f"/agent-workflows/{resources['workflow_id']}/events")["data"]
    recommendations = request_json(f"/recommendations/{me['id']}")["data"]

    checks = {
        "runtime_repository": runtime["repository_backend"],
        "knowledge_engine": knowledge["active_engine"],
        "knowledge_chunks": knowledge["indexed_chunks"],
        "path_nodes": len(path["nodes"]),
        "resources": len(resources["resources"]),
        "workflow_tasks": len(workflow["tasks"]),
        "events": len(events),
        "recommendations": len(recommendations),
    }
    assert checks["path_nodes"] >= 3, checks
    assert checks["resources"] >= 5, checks
    assert checks["workflow_tasks"] >= 8, checks
    assert checks["events"] >= 8, checks
    assert checks["recommendations"] >= 5, checks
    print(json.dumps({"status": "passed", "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
