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


def test_profile_agent_extracts_multi_dimension_profile() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    response = client.post(
        "/api/v1/agents/profile/extract",
        json={
            "user_id": me["id"],
            "conversation": [
                {"role": "user", "content": "我是计算机专业大二学生，想两周内掌握栈和队列"},
                {"role": "assistant", "content": "你更适合案例驱动学习。"},
                {"role": "user", "content": "我的薄弱点是递归、复杂度分析和栈的应用，喜欢图解和代码。"},
            ],
        },
        headers=headers,
    ).json()["data"]

    assert response["basic_info"]["major"]
    assert response["basic_info"]["grade"]
    assert response["knowledge_profile"]["weak_topics"]
    assert response["learning_goal"]["current_goal"]
    assert response["learning_preference"]["learning_style"]
    assert response["learning_behavior"]["last_knowledge_point"]
    assert response["cognitive_profile"]["cognitive_style"]


def test_agent_resources_generate_backend_artifacts() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    document = client.post(
        "/api/v1/agents/resources/document",
        json={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["document"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]
    quiz = client.post(
        "/api/v1/agents/resources/quiz",
        json={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["quiz"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]
    multimodal = client.post(
        "/api/v1/agents/resources/multimodal",
        json={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["mindmap", "video", "animation"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]
    code = client.post(
        "/api/v1/agents/resources/code",
        json={
            "user_id": me["id"],
            "subject": "数据结构",
            "knowledge_point": "栈的基本概念",
            "resource_types": ["code_case"],
            "difficulty": "beginner",
        },
        headers=headers,
    ).json()["data"]

    assert document[0]["resource_type"] == "document"
    assert "概念" in document[0]["content"]
    assert quiz[0]["resource_type"] == "quiz"
    assert "questions" in quiz[0]["content"]
    assert len(multimodal) == 3
    assert {item["resource_type"] for item in multimodal} == {"mindmap", "video", "animation"}
    assert code[0]["resource_type"] == "code_case"
    assert "运行说明" in code[0]["content"]


def test_base_agent_create_and_list() -> None:
    headers = auth_headers()
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    created = client.post(
        "/api/v1/agents/base-agents",
        json={
            "user_id": me["id"],
            "name": "考试冲刺智能体",
            "description": "面向短期冲刺复习的基层智能体。",
            "system_prompt": "你是考试冲刺型基层智能体，强调高频考点、错题回收和短期提分。",
            "applies_to": ["profile_agent", "path_agent", "quiz_agent", "tutor_agent"],
            "model_provider": "spark",
            "output_style": "concise",
        },
        headers=headers,
    ).json()["data"]

    agents = client.get(f"/api/v1/agents/base-agents/{me['id']}", headers=headers).json()["data"]

    assert created["name"] == "考试冲刺智能体"
    assert any(item["agent_id"] == created["agent_id"] for item in agents)
