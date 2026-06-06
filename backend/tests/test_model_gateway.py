from __future__ import annotations

import os

os.environ["MODEL_PROVIDER"] = "mock"

from typing import Dict, List

import pytest
from pydantic import BaseModel

from app.services import model_gateway
from app.services.model_gateway import ModelOverride


class QuizPayload(BaseModel):
    questions: List[Dict]


def test_generate_json_retries_until_valid(monkeypatch) -> None:
    model_gateway._cb_state.clear()
    calls = iter(["not-json", '{"questions":[{"stem":"栈是什么","answer":"后进先出"}]}'])

    monkeypatch.setattr(
        model_gateway,
        "get_model_status",
        lambda: {
            "provider": "spark",
            "spark_ready": True,
            "spark_model": "generalv3.5",
            "websocket_ready": True,
            "mode": "spark",
            "json_retries": 2,
        },
    )
    monkeypatch.setattr(model_gateway, "_call_spark", lambda prompt: next(calls))

    payload = model_gateway.generate_json(
        "生成测试",
        fallback={"questions": []},
        required_keys=["questions"],
        schema=QuizPayload,
        model_override=ModelOverride(provider="spark"),
    )

    assert payload["_model_mode"] == "spark"
    assert payload["_retry_count"] == 1
    assert payload["questions"]


def test_generate_json_raises_after_failures(monkeypatch) -> None:
    model_gateway._cb_state.clear()
    monkeypatch.setattr(
        model_gateway,
        "get_model_status",
        lambda: {
            "provider": "spark",
            "spark_ready": True,
            "spark_model": "generalv3.5",
            "websocket_ready": True,
            "mode": "spark",
            "json_retries": 1,
        },
    )
    monkeypatch.setattr(model_gateway, "_call_spark", lambda prompt: '{"items":[]}')

    from app.core.errors import ServiceError

    with pytest.raises(ServiceError, match="结构化 JSON 生成失败"):
        model_gateway.generate_json(
            "生成测试",
            required_keys=["questions"],
            schema=QuizPayload,
            max_retries=1,
            model_override=ModelOverride(provider="spark"),
        )
