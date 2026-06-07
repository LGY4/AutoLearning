from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ["MODEL_PROVIDER"] = "mock"
os.environ["REPOSITORY_BACKEND"] = "memory"
os.environ["RAG_BACKEND"] = "memory"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import ResourceType
from app.main import app
from app.services import agent_runtime, digital_human_service, image_gen_service


client = TestClient(app)


def auth_headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "student001", "password": "123456"}).json()["data"]
    return {"Authorization": f"Bearer {response['access_token']}"}


def test_digital_human_status_does_not_expose_credentials(monkeypatch) -> None:
    monkeypatch.setenv("XFYUN_DH_APP_ID", "app-id-test")
    monkeypatch.setenv("XFYUN_DH_API_KEY", "api-key-test")
    monkeypatch.setenv("XFYUN_DH_API_SECRET", "api-secret-test")
    monkeypatch.setattr(
        digital_human_service.shutil,
        "which",
        lambda name: f"C:/tools/{name}.exe" if name in {"ffmpeg", "edge-tts"} else None,
    )
    get_settings.cache_clear()

    status = digital_human_service.get_digital_human_status()

    assert status["configured"] is True
    assert status["fallback_available"] is True
    assert status["mode"] == "xfyun_with_local_fallback"
    serialized = json.dumps(status, ensure_ascii=False)
    assert "app-id-test" not in serialized
    assert "api-key-test" not in serialized
    assert "api-secret-test" not in serialized

    get_settings.cache_clear()


def test_digital_human_status_endpoint_returns_capability() -> None:
    response = client.get("/api/v1/video/digital-human/status", headers=auth_headers())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "xfyun"
    assert "configured" in data
    assert "fallback_available" in data
    assert "api_key" not in json.dumps(data).lower()
    assert "api_secret" not in json.dumps(data).lower()


def test_video_learning_resource_uses_digital_human_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        image_gen_service,
        "generate_image",
        lambda prompt, style="educational": {"image_path": ""},
    )
    monkeypatch.setattr(
        digital_human_service,
        "get_digital_human_status",
        lambda: {
            "configured": True,
            "fallback_available": False,
        },
    )
    video_path = tmp_path / "dh_final.mp4"
    video_path.write_bytes(b"fake mp4")
    monkeypatch.setattr(
        digital_human_service,
        "generate_dh_video",
        lambda text, knowledge_point, **kwargs: {
            "task_id": "dh-test-001",
            "video_path": str(video_path),
            "cover_path": "",
            "metadata": {"mode": "fallback"},
        },
    )

    resource = agent_runtime.build_learning_resource(
        user_id=uuid4(),
        subject="数据结构",
        knowledge_point="栈",
        resource_type=ResourceType.VIDEO,
        difficulty="beginner",
        profile=None,
    )
    payload = json.loads(resource.content)

    assert resource.resource_type == ResourceType.VIDEO
    assert resource.metadata["digital_human"] is True
    assert resource.metadata["provider_mode"] == "fallback"
    assert resource.metadata["fallback_used"] is True
    assert resource.metadata["video_url"] == "/api/v1/video/file/dh-test-001"
    assert payload["video_mode"] == "digital_human"
    assert payload["provider_mode"] == "fallback"
    assert payload["video_url"] == "/api/v1/video/file/dh-test-001"
