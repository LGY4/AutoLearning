from __future__ import annotations

from typing import Dict,  List,  Optional

import json
import urllib.request

import httpx

from app.core.config import get_settings


_LAST_STATUS: Dict[str, str | bool | Optional[int]] = {}

_local_model_cache = None


def _get_local_model():
    global _local_model_cache
    if _local_model_cache is None:
        import os
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        from sentence_transformers import SentenceTransformer
        _local_model_cache = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    return _local_model_cache


def _local_embed(text: str) -> List[float]:
    """Local embedding using sentence-transformers (BGE-small-zh)."""
    model = _get_local_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def _openai_compatible_embed(text: str) -> List[float]:
    """Call OpenAI-compatible embedding API (works with OpenAI, DeepSeek, Ollama, vLLM, etc.)."""
    settings = get_settings()
    api_url = settings.embedding_api_url
    api_key = settings.embedding_api_key

    if not api_url:
        raise RuntimeError("EMBEDDING_API_URL is not configured")
    if not api_key:
        raise RuntimeError("EMBEDDING_API_KEY is not configured")

    url = api_url.rstrip("/")
    if not url.endswith("/embeddings"):
        url = f"{url}/embeddings"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": settings.embedding_model,
        "input": text,
    }

    with httpx.Client(timeout=settings.embedding_timeout_seconds) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    return _parse_embedding_response(data)


def _http_embed_legacy(text: str) -> List[float]:
    """Legacy HTTP embedding endpoint (custom format)."""
    settings = get_settings()
    if not settings.embedding_api_url:
        raise RuntimeError("EMBEDDING_API_URL is not configured")
    body = json.dumps({"model": settings.embedding_model, "input": text}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.embedding_api_key:
        headers["Authorization"] = f"Bearer {settings.embedding_api_key}"
    request = urllib.request.Request(settings.embedding_api_url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=settings.embedding_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _parse_embedding_response(payload)


def _parse_embedding_response(payload: dict) -> List[float]:
    # OpenAI format: {"data": [{"embedding": [...]}]}
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("embedding"), list):
            return [float(item) for item in first["embedding"]]
    # Direct format: {"embedding": [...]} or {"vector": [...]}
    if isinstance(payload.get("embedding"), list):
        return [float(item) for item in payload["embedding"]]
    if isinstance(payload.get("vector"), list):
        return [float(item) for item in payload["vector"]]
    raise ValueError("Embedding response does not contain embedding/vector/data[0].embedding")


def embed_text(text: str) -> List[float]:
    """Embed text using the configured provider. Raises on failure (no silent fallback)."""
    settings = get_settings()
    provider = settings.embedding_provider

    if provider == "local":
        try:
            vector = _local_embed(text)
            _LAST_STATUS.update({
                "provider": "local",
                "active_mode": "local_sentence_transformers",
                "dimension": len(vector),
                "last_error": None,
            })
            return vector
        except Exception as exc:
            _LAST_STATUS.update({"last_error": str(exc)})
            if not settings.embedding_allow_fallback:
                raise

    if provider == "openai_compatible":
        try:
            vector = _openai_compatible_embed(text)
            _LAST_STATUS.update({
                "provider": "openai_compatible",
                "active_mode": "openai_compatible",
                "dimension": len(vector),
                "last_error": None,
            })
            return vector
        except Exception as exc:
            _LAST_STATUS.update({"last_error": str(exc)})
            if not settings.embedding_allow_fallback:
                raise

    if provider == "http":
        try:
            vector = _http_embed_legacy(text)
            _LAST_STATUS.update({
                "provider": "http",
                "active_mode": "http",
                "dimension": len(vector),
                "last_error": None,
            })
            return vector
        except Exception as exc:
            _LAST_STATUS.update({"last_error": str(exc)})
            if not settings.embedding_allow_fallback:
                raise

    # Fallback: simple TF-IDF-like hash embedding (development only)
    if settings.embedding_allow_fallback:
        vector = _deterministic_embed(text)
        _LAST_STATUS.update({
            "provider": provider,
            "active_mode": "deterministic_fallback",
            "dimension": len(vector),
        })
        return vector

    raise RuntimeError(f"Embedding provider '{provider}' is not available and fallback is disabled")


def _deterministic_embed(text: str) -> List[float]:
    """Development-only fallback: hash-based pseudo-embedding matching configured dimension."""
    dim = get_settings().embedding_dimension
    buckets = [0.0] * dim
    for index, char in enumerate(text):
        buckets[index % len(buckets)] += (ord(char) % 97) / 97.0
    norm = sum(value * value for value in buckets) ** 0.5 or 1.0
    return [round(value / norm, 6) for value in buckets]


def get_embedding_status() -> Dict[str, str | bool | Optional[int]]:
    settings = get_settings()
    return {
        "provider": settings.embedding_provider,
        "model": settings.embedding_model,
        "api_configured": bool(settings.embedding_api_url and settings.embedding_api_key),
        "active_mode": _LAST_STATUS.get("active_mode", "not_called"),
        "dimension": _LAST_STATUS.get("dimension"),
        "allow_fallback": settings.embedding_allow_fallback,
        "last_error": _LAST_STATUS.get("last_error"),
        "timeout_seconds": settings.embedding_timeout_seconds,
    }
