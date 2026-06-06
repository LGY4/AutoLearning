from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import os

os.environ["MODEL_PROVIDER"] = "mock"

from app.services import embedding_service


class EmbeddingHandler(BaseHTTPRequestHandler):
    mode = "ok"

    def do_POST(self):  # noqa: N802
        if self.mode == "fail":
            self.send_response(500)
            self.end_headers()
            return
        payload = {"embedding": [0.1, 0.2, 0.3, 0.4]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, *args):  # noqa: D401
        return


def _server():
    server = HTTPServer(("127.0.0.1", 0), EmbeddingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_http_embedding_provider(monkeypatch) -> None:
    server = _server()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "http")
    monkeypatch.setenv("EMBEDDING_API_URL", f"http://127.0.0.1:{server.server_port}/embedding")
    monkeypatch.setenv("EMBEDDING_ALLOW_FALLBACK", "false")
    embedding_service.get_settings.cache_clear()

    vector = embedding_service.embed_text("栈")

    assert vector == [0.1, 0.2, 0.3, 0.4]
    assert embedding_service.get_embedding_status()["dimension"] == 4
    server.shutdown()
    embedding_service.get_settings.cache_clear()


def test_http_embedding_failure_can_fallback(monkeypatch) -> None:
    server = _server()
    EmbeddingHandler.mode = "fail"
    monkeypatch.setenv("EMBEDDING_PROVIDER", "http")
    monkeypatch.setenv("EMBEDDING_API_URL", f"http://127.0.0.1:{server.server_port}/embedding")
    monkeypatch.setenv("EMBEDDING_ALLOW_FALLBACK", "true")
    embedding_service.get_settings.cache_clear()

    vector = embedding_service.embed_text("栈")

    assert len(vector) == embedding_service.get_settings().embedding_dimension
    assert embedding_service.get_embedding_status()["active_mode"] == "deterministic_fallback"
    EmbeddingHandler.mode = "ok"
    server.shutdown()
    embedding_service.get_settings.cache_clear()
