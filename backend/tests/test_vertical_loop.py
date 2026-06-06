from __future__ import annotations

import os

os.environ["MODEL_PROVIDER"] = "mock"
os.environ["REPOSITORY_BACKEND"] = "memory"
os.environ["RAG_BACKEND"] = "memory"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def auth_headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "student001", "password": "123456"}).json()["data"]
    return {"Authorization": f"Bearer {response['access_token']}"}


def test_learning_start_unified_entrypoint() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    response = client.post(
        "/api/v1/learning/start",
        json={
            "user_id": me["id"],
            "message": "两周内掌握数据结构中的栈和队列，并能完成括号匹配练习",
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["document", "mindmap", "quiz", "reading", "video", "animation", "code_case"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]

    assert response["status"] == "success"
    assert response["stream_url"].startswith("/api/v1/agent-workflows/")
    assert len(response["resources"]) == 7
    assert len(response["workflow"]["tasks"]) == 9
    assert response["recommendations"]
    assert response["conversation_id"]
    assert len(response["messages"]) >= 2


def test_learning_start_keeps_multi_turn_profile_chat() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    first = client.post(
        "/api/v1/learning/start",
        json={
            "user_id": me["id"],
            "message": "我要学习快速排序",
            "subject": "算法",
            "knowledge_point": "快速排序",
            "resource_types": ["document", "mindmap", "quiz", "code_case"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]
    second = client.post(
        "/api/v1/learning/start",
        json={
            "user_id": me["id"],
            "conversation_id": first["conversation_id"],
            "message": "我还是不理解 Partition 过程，请继续生成图解和练习",
            "subject": "算法",
            "knowledge_point": "快速排序",
            "resource_types": ["document", "mindmap", "quiz", "code_case"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]

    assert second["conversation_id"] == first["conversation_id"]
    assert len(second["messages"]) >= 4
    assert second["profile"]["version"] > first["profile"]["version"]
    assert any("快速排序" in resource["title"] for resource in second["resources"])


def test_vertical_learning_loop() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    profile = client.get(f"/api/v1/profiles/{me['id']}", headers=headers).json()["data"]
    path = client.post(
        "/api/v1/learning-paths/generate",
        json={
            "user_id": me["id"],
            "target_goal": profile["learning_goal"]["current_goal"],
            "subject": profile["learning_goal"]["target_course"],
        },
        headers=headers,
    ).json()["data"]
    resources = client.post(
        "/api/v1/resources/generate",
        json={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["document", "mindmap", "quiz", "reading", "video", "animation", "code_case"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]
    workflow = client.get(f"/api/v1/agent-workflows/{resources['workflow_id']}", headers=headers).json()["data"]
    events = client.get(f"/api/v1/agent-workflows/{resources['workflow_id']}/events", headers=headers).json()["data"]
    record = client.post(
        "/api/v1/learning-records",
        json={
            "user_id": me["id"],
            "path_id": path["path_id"],
            "resource_id": resources["resources"][0]["resource_id"],
            "score": 68,
            "duration_seconds": 1200,
            "wrong_points": ["栈的应用"],
            "feedback": "仍需练习",
        },
        headers=headers,
    ).json()["data"]

    assert len(resources["resources"]) == 7
    assert len(workflow["tasks"]) == 9
    assert len(events) == 9
    assert any(task["agent_name"] == "video_agent" for task in workflow["tasks"])
    assert {resource["resource_type"] for resource in resources["resources"]} >= {"video", "animation"}
    assert workflow["tasks"][0]["output_payload"]["langgraph_runtime"] in {"langgraph", "compatibility_fallback"}
    assert record["profile_update_triggered"] is True


def test_workflow_keeps_mvp_shape_without_multimodal_resources() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    resources = client.post(
        "/api/v1/resources/generate",
        json={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "队列的基本概念",
            "resource_types": ["document", "mindmap", "quiz", "reading", "code_case"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]
    workflow = client.get(f"/api/v1/agent-workflows/{resources['workflow_id']}", headers=headers).json()["data"]

    assert len(resources["resources"]) == 5
    assert len(workflow["tasks"]) == 8
    assert all(task["agent_name"] != "video_agent" for task in workflow["tasks"])


def test_async_task_status_falls_back_without_redis() -> None:
    headers = auth_headers()
    response = client.get("/api/v1/resources/tasks/local-fallback-test", headers=headers).json()["data"]

    assert response["status"] == "broker_unavailable"
    assert response["result"]["message"]


def test_runtime_and_rag_status() -> None:
    headers = auth_headers()
    runtime = client.get("/api/v1/system/runtime", headers=headers).json()["data"]
    rag = client.post("/api/v1/knowledge/search", json={"query": "栈", "subject": "数据结构"}, headers=headers).json()["data"]

    assert runtime["repository_backend"] == "memory"
    assert rag["results"]
