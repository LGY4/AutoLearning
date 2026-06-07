from __future__ import annotations

"""Xfyun Digital Human Video Generation Service.

Based on official docs: 数字人视频大模型 WebAPI 文档 v1
- Auth: HMAC-SHA256 signature passed as URL query parameters
- Submit: POST /api/v1/video/generate (official), /v1/private/video/generate (legacy fallback)
- Query:  POST /api/v1/video/query (official), /v1/private/video/query (legacy fallback)
- Base URL: http://vms.cn-huadong-1.xf-yun.com
- Prompt limit: 300 UTF-8 bytes
- word_count: 50-300, default 80-150
"""

import hashlib
import hmac
import json
import logging
import shutil
import time
from base64 import b64encode
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.errors import ErrorCode, ServiceError

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "generated_videos"


def get_digital_human_status() -> dict:
    """Return digital human capability status without exposing credentials."""
    cfg = get_settings()
    configured = bool(cfg.xfyun_dh_app_id and cfg.xfyun_dh_api_key and cfg.xfyun_dh_api_secret)
    ffmpeg_available = shutil.which("ffmpeg") is not None
    edge_tts_available = shutil.which("edge-tts") is not None
    tts_configured = bool(cfg.llm_api_key)
    fallback_available = ffmpeg_available and (edge_tts_available or tts_configured)
    return {
        "provider": "xfyun",
        "configured": configured,
        "api_url": cfg.xfyun_dh_api_url,
        "persona_configured": bool(cfg.xfyun_dh_persona_id),
        "voice_configured": bool(cfg.xfyun_dh_voice_id),
        "fallback_available": fallback_available,
        "fallback_requires": ["ffmpeg", "edge-tts or configured TTS"],
        "ffmpeg_available": ffmpeg_available,
        "edge_tts_available": edge_tts_available,
        "tts_configured": tts_configured,
        "mode": (
            "xfyun_with_local_fallback"
            if configured
            else "local_fallback"
            if fallback_available
            else "storyboard_only"
        ),
    }


class XfyunDHClient:
    """Client for Xfyun Digital Human Video Generation API.

    Auth: HMAC-SHA256 signature appended as URL query parameters.
    Docs: signature_origin = "host: $host\ndate: $date\n$METHOD $PATH HTTP/1.1"
          authorization = base64('api_key="...", algorithm="hmac-sha256", headers="host date request-line", signature="..."')
    """

    def __init__(
        self,
        app_id: str,
        api_key: str,
        api_secret: str,
        api_url: str = "vms.cn-huadong-1.xf-yun.com",
    ):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = api_url
        self.base_url = f"https://{api_url}"
        self._client = httpx.Client(timeout=30.0)

    def _build_auth_url(self, method: str, path: str) -> str:
        """Build URL with HMAC-SHA256 auth query parameters.

        Per official docs:
        1. signature_origin = "host: $host\ndate: $date\n$METHOD $PATH HTTP/1.1"
        2. signature = base64(hmac-sha256(signature_origin, APISecret))
        3. authorization_origin = 'api_key="...", algorithm="hmac-sha256", headers="host date request-line", signature="..."'
        4. authorization = base64(authorization_origin)
        5. Append host, date, authorization as URL query params.
        """
        date = format_datetime(datetime.now(timezone.utc), usegmt=True)

        # Step 1: signature origin
        signature_origin = f"host: {self.host}\ndate: {date}\n{method} {path} HTTP/1.1"

        # Step 2: HMAC-SHA256 signature
        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature_b64 = b64encode(signature_sha).decode("utf-8")

        # Step 3-4: authorization_origin -> base64
        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature_b64}"'
        )
        authorization = b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

        # Step 5: append as query params (use %20 for spaces, matching Xfyun docs format)
        params = f"authorization={quote(authorization, safe='')}&date={quote(date, safe='')}&host={self.host}"
        return f"{self.base_url}{path}?{params}"

    def submit_task(
        self,
        prompt: str,
        word_count: int = 120,
        callback_url: Optional[str] = None,
    ) -> tuple[str, str]:
        """Submit a digital human video generation task.

        Returns (task_id, used_endpoint).
        Tries official doc endpoint first (/api/v1/video/generate),
        falls back to legacy endpoint (/v1/private/video/generate).
        """
        body: dict = {
            "header": {
                "app_id": self.app_id,
            },
            "parameter": {
                "avatar": {
                    "prompt": prompt,
                    "word_count": word_count,
                },
            },
        }
        if callback_url:
            body["header"]["callback_url"] = callback_url

        logger.info("Submitting digital human task: prompt_len=%d, word_count=%d", len(prompt), word_count)

        for path in ("/api/v1/video/generate", "/v1/private/video/generate"):
            url = self._build_auth_url("POST", path)
            response = self._client.post(url, headers={"Content-Type": "application/json"}, json=body)
            if response.status_code == 403:
                logger.info("Endpoint %s returned 403, trying next", path)
                continue
            response.raise_for_status()
            data = response.json()
            code = data.get("header", {}).get("code", -1)
            if code != 0:
                message = data.get("header", {}).get("message", "Unknown error")
                raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"数字人视频任务提交失败: [{code}] {message}")
            task_id = data.get("header", {}).get("task_id", "")
            if not task_id:
                raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "数字人视频任务提交成功但未返回 task_id")
            logger.info("Digital human task submitted via %s: task_id=%s", path, task_id)
            return task_id, path

        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "数字人视频接口不可用（所有端点均返回 403）")

    def query_task(self, task_id: str) -> dict:
        """Query task status. Returns full response dict."""
        body = {
            "header": {
                "app_id": self.app_id,
                "task_id": task_id,
            },
        }

        for path in ("/api/v1/video/query", "/v1/private/video/query"):
            url = self._build_auth_url("POST", path)
            response = self._client.post(url, headers={"Content-Type": "application/json"}, json=body)
            if response.status_code == 403:
                continue
            response.raise_for_status()
            data = response.json()
            code = data.get("header", {}).get("code", -1)
            if code != 0:
                message = data.get("header", {}).get("message", "Unknown error")
                raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"数字人视频查询失败: [{code}] {message}")
            return data

        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "数字人视频查询接口不可用（所有端点均返回 403）")

    def wait_for_completion(
        self,
        task_id: str,
        used_endpoint: str = "",
        timeout: int = 600,
        poll_interval: int = 15,
        emit_progress: Optional[Callable[[dict], None]] = None,
    ) -> dict:
        """Poll until task completes or timeout.

        Per docs, task_status values:
          "1" = Created / Queued
          "2" = Processing
          "3" = Complete (waiting for callback)
          "4" = Final complete (no callback or callback done)

        Xfyun tasks may stay at status 1 for a while in the queue.
        """
        deadline = time.monotonic() + timeout
        created_since = time.monotonic()
        while time.monotonic() < deadline:
            data = self.query_task(task_id)
            status = data.get("header", {}).get("task_status", "")

            if status in ("3", "4"):
                if emit_progress:
                    emit_progress({"stage": "digital_human", "status": "done", "progress": 100, "hint": "数字人视频生成完成"})
                return data
            elif status == "2":
                created_since = time.monotonic()  # reset timer once processing starts
                if emit_progress:
                    emit_progress({"stage": "digital_human", "status": "running", "progress": 50, "hint": "数字人视频生成中..."})
                time.sleep(poll_interval)
            elif status == "1":
                stuck_seconds = time.monotonic() - created_since
                if stuck_seconds > 300:
                    raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"Xfyun task stuck at status 1 for {int(stuck_seconds)}s")
                if emit_progress:
                    emit_progress({"stage": "digital_human", "status": "running", "progress": 30, "hint": "数字人任务排队中..."})
                time.sleep(poll_interval)
            else:
                message = data.get("header", {}).get("message", "未知状态")
                raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"数字人视频生成异常: status={status}, {message}")

        raise ServiceError(ErrorCode.LLM_TIMEOUT, f"数字人视频生成超时（{timeout}s）")

    def download_assets(self, payload: dict, save_dir: Path) -> dict:
        """Download video assets from payload. Returns local paths.

        Actual response format (per docs):
        payload.video.video = base64-encoded download URL
        """
        from base64 import b64decode

        save_dir.mkdir(parents=True, exist_ok=True)
        paths = {}

        # Extract video URL from payload.video.video (base64-encoded)
        video_section = payload.get("video", {})
        video_b64 = video_section.get("video", "")
        if video_b64:
            try:
                video_url = b64decode(video_b64).decode("utf-8")
                local_path = save_dir / "dh_final.mp4"
                logger.info("Downloading digital human video from %s", video_url[:80])
                with self._client.stream("GET", video_url) as resp:
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                paths["video"] = str(local_path)
                logger.info("Video saved to %s (%d bytes)", local_path, local_path.stat().st_size)
            except Exception:
                logger.warning("Failed to download video from payload", exc_info=True)

        return paths


def get_dh_client() -> XfyunDHClient:
    """Create XfyunDHClient from settings."""
    cfg = get_settings()
    if not cfg.xfyun_dh_app_id or not cfg.xfyun_dh_api_key or not cfg.xfyun_dh_api_secret:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "讯飞数字人凭据未配置（XFYUN_DH_APP_ID/API_KEY/API_SECRET）")
    return XfyunDHClient(
        app_id=cfg.xfyun_dh_app_id,
        api_key=cfg.xfyun_dh_api_key,
        api_secret=cfg.xfyun_dh_api_secret,
        api_url=cfg.xfyun_dh_api_url,
    )


def _try_xfyun(
    text: str,
    knowledge_point: str,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Try Xfyun digital human API. Raises on any failure."""
    client = get_dh_client()

    if emit_progress:
        emit_progress({"stage": "script", "status": "running", "progress": 10, "hint": "正在准备脚本..."})

    prompt = text.strip()
    max_bytes = 300
    prompt_bytes = prompt.encode("utf-8")
    if len(prompt_bytes) > max_bytes:
        prompt = prompt_bytes[:max_bytes].decode("utf-8", errors="ignore")

    if emit_progress:
        emit_progress({"stage": "script", "status": "done", "progress": 20, "hint": "脚本准备完成"})

    if emit_progress:
        emit_progress({"stage": "submit", "status": "running", "progress": 25, "hint": "正在提交数字人视频任务..."})

    word_count = max(50, min(300, len(prompt) * 2))
    task_id, used_endpoint = client.submit_task(prompt=prompt, word_count=word_count)

    if emit_progress:
        emit_progress({"stage": "submit", "status": "done", "progress": 30, "hint": f"任务已提交: {task_id}"})

    result = client.wait_for_completion(
        task_id=task_id, used_endpoint=used_endpoint,
        timeout=600, poll_interval=5, emit_progress=emit_progress,
    )

    if emit_progress:
        emit_progress({"stage": "download", "status": "running", "progress": 90, "hint": "正在下载视频资源..."})

    payload = result.get("payload", {})
    save_dir = _DATA_DIR / task_id
    paths = client.download_assets(payload, save_dir)

    metadata = {
        "task_id": task_id, "knowledge_point": knowledge_point,
        "prompt": prompt, "word_count": word_count,
        "paths": paths, "payload": payload, "mode": "xfyun",
    }
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    if emit_progress:
        emit_progress({"stage": "download", "status": "done", "progress": 100, "hint": "数字人视频就绪"})

    return {
        "task_id": task_id,
        "video_path": paths.get("video", ""),
        "cover_path": paths.get("cover", ""),
        "audio_path": paths.get("audio", ""),
        "metadata": metadata,
    }


def generate_dh_video(
    text: str,
    knowledge_point: str,
    emit_progress: Optional[Callable[[dict], None]] = None,
    reset_progress: Optional[Callable[[], None]] = None,
) -> dict:
    """Generate digital human teaching video.

    Tries Xfyun API first; falls back to local TTS+FFmpeg pipeline on failure.
    """
    try:
        return _try_xfyun(text, knowledge_point, emit_progress)
    except Exception as exc:
        logger.warning("Xfyun digital human failed (%s), falling back to local pipeline", exc)
        if reset_progress:
            reset_progress()

        from app.services.dh_video_fallback import generate_fallback_video
        return generate_fallback_video(text, knowledge_point, emit_progress=emit_progress)
