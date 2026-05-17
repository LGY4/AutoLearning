from __future__ import annotations

"""Text-to-Speech service with OpenAI-compatible API support."""

import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.errors import ErrorCode, ServiceError

logger = logging.getLogger(__name__)

# Cache directory for generated audio
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "tts_cache"

# Default voices per provider
_DEFAULT_VOICES = {
    "openai": "alloy",
    "deepseek": "alloy",
    "azure": "zh-CN-XiaoxiaoNeural",
}


def _get_tts_config() -> dict:
    """Get TTS configuration from settings."""
    settings = get_settings()
    # Reuse LLM settings for TTS (same API base, same key)
    return {
        "api_base": settings.llm_api_base,
        "api_key": settings.llm_api_key,
        "model": "tts-1",
        "voice": getattr(settings, "tts_voice", None) or "alloy",
        "timeout": 60,
    }


def _cache_key(text: str, voice: str, model: str) -> str:
    """Generate cache key for TTS audio."""
    content = f"{text}|{voice}|{model}"
    return hashlib.md5(content.encode()).hexdigest()


def synthesize(
    text: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
    use_cache: bool = True,
) -> bytes:
    """Convert text to speech using OpenAI-compatible TTS API.

    Returns raw audio bytes (MP3 format).
    Raises ServiceError on failure.
    """
    if not text or not text.strip():
        return b""

    cfg = _get_tts_config()
    voice = voice or cfg["voice"]
    model = model or cfg["model"]

    # Check cache
    if use_cache:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / f"{_cache_key(text, voice, model)}.mp3"
        if cache_file.exists():
            return cache_file.read_bytes()

    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "TTS API Key 未配置")

    # Truncate very long text
    max_chars = 4096
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    url = f"{cfg['api_base'].rstrip('/')}/audio/speech"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }

    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 401:
                raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "TTS API Key 无效")
            response.raise_for_status()
            audio_bytes = response.content
    except httpx.TimeoutException:
        raise ServiceError(ErrorCode.LLM_TIMEOUT, "TTS 请求超时")
    except httpx.HTTPStatusError as exc:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"TTS API 错误: {exc.response.status_code}")
    except Exception as exc:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"TTS 生成失败: {exc}")

    # Save to cache
    if use_cache:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(audio_bytes)
        except Exception:
            pass  # Cache write failure is non-critical

    return audio_bytes


def get_audio_path(text: str, voice: Optional[str] = None, model: Optional[str] = None) -> Optional[Path]:
    """Get cached audio file path, or None if not cached."""
    cfg = _get_tts_config()
    voice = voice or cfg["voice"]
    model = model or cfg["model"]
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(text, voice, model)}.mp3"
    return cache_file if cache_file.exists() else None
