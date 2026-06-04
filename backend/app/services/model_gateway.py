from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import hmac
import json
import ssl
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Dict,  List,  Optional, Union
from urllib.parse import urlencode, urlparse

import time

import httpx
from pydantic import BaseModel, ValidationError

from app.core.errors import ErrorCode, ServiceError

from app.core.config import get_settings

# ── Shared HTTP client pool ───────────────────────────────────────────────
_clients_by_timeout: Dict[float, httpx.Client] = {}
_http_client_lock = threading.Lock()


def _get_http_client(timeout: float = 120.0) -> httpx.Client:
    """Get or create a shared httpx.Client with connection pooling, keyed by timeout."""
    with _http_client_lock:
        client = _clients_by_timeout.get(timeout)
        if client is None or client.is_closed:
            client = httpx.Client(timeout=timeout, limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ))
            _clients_by_timeout[timeout] = client
        return client


PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "label": "默认模型 (DeepSeek V4 Pro)",
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-pro",
    },
    "spark": {
        "label": "Spark X2",
        "api_base": "",
        "model": "spark-x",
    },
    "ollama": {
        "label": "Ollama (本地)",
        "api_base": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
    },
}


def get_model_status() -> Dict[str, Union[str, bool, int]]:
    settings = get_settings()
    provider = settings.model_provider

    if provider == "spark":
        spark_ready = bool(settings.spark_app_id and settings.spark_api_key and settings.spark_api_secret)
        try:
            import websocket  # noqa: F401
            websocket_ready = True
        except ModuleNotFoundError:
            websocket_ready = False
        return {
            "provider": "spark",
            "spark_ready": spark_ready,
            "spark_model": settings.spark_model,
            "websocket_ready": websocket_ready,
            "mode": "spark" if spark_ready and websocket_ready else "unavailable",
            "json_retries": settings.spark_json_retries,
            "presets": PROVIDER_PRESETS,
        }

    if provider == "openai_compatible":
        return {
            "provider": "openai_compatible",
            "api_base": settings.llm_api_base,
            "model": settings.llm_model,
            "api_key_configured": bool(settings.llm_api_key),
            "mode": "openai_compatible",
            "presets": PROVIDER_PRESETS,
        }

    return {
        "provider": provider,
        "mode": "unavailable",
        "presets": PROVIDER_PRESETS,
    }


# ── Circuit breaker (per-provider isolation) ────────────────────────────────

_CB_FAILURE_THRESHOLD = 5
_CB_RECOVERY_SECONDS = 30
_CB_HALF_OPEN_MAX = 2  # max requests allowed in half-open state

_cb_state: Dict[str, dict] = {}  # provider -> {"failures": int, "open_until": float, "half_open_count": int}
_cb_lock = threading.Lock()


def _cb_provider_key() -> str:
    """Get current provider key for circuit breaker isolation."""
    try:
        override = _model_override_ctx.get()
        if override and override.provider:
            return override.provider
    except Exception:
        pass
    return get_settings().model_provider


def _cb_record_success() -> None:
    key = _cb_provider_key()
    with _cb_lock:
        _cb_state.pop(key, None)


def _cb_record_failure() -> None:
    key = _cb_provider_key()
    with _cb_lock:
        state = _cb_state.setdefault(key, {"failures": 0, "open_until": 0.0, "half_open_count": 0})
        state["failures"] += 1
        if state["failures"] >= _CB_FAILURE_THRESHOLD:
            state["open_until"] = time.monotonic() + _CB_RECOVERY_SECONDS
            state["half_open_count"] = 0


def _cb_is_open() -> bool:
    key = _cb_provider_key()
    with _cb_lock:
        state = _cb_state.get(key)
        if not state:
            return False
        if state["open_until"] == 0:
            return False
        now = time.monotonic()
        if now >= state["open_until"]:
            # Half-open: allow limited requests through to test recovery
            if state.get("half_open_count", 0) < _CB_HALF_OPEN_MAX:
                state["half_open_count"] = state.get("half_open_count", 0) + 1
                return False  # allow this request
            # Still in half-open but hit limit — block until next window
            return True
        return True


# ── Retry helper for transient HTTP errors ────────────────────────────────

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_HTTP_RETRIES = 3
_BASE_DELAY = 1.0  # seconds


def _retry_request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    """Retry transient HTTP errors with exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_HTTP_RETRIES + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code not in _TRANSIENT_STATUS_CODES:
                return response
            if attempt < _MAX_HTTP_RETRIES:
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else _BASE_DELAY * (2 ** attempt)
                time.sleep(delay)
                continue
            raise ServiceError(
                ErrorCode.LLM_GENERATION_FAILED,
                f"LLM 服务暂时不可用 (HTTP {response.status_code})，已重试 {_MAX_HTTP_RETRIES} 次"
            )
        except httpx.ConnectTimeout:
            raise ServiceError(ErrorCode.LLM_AUTH_FAILED, f"LLM 连接失败，请检查 API 地址和网络: {url}")
        except httpx.TimeoutException:
            last_exc = ServiceError(ErrorCode.LLM_TIMEOUT, f"LLM 请求超时（{client.timeout}s）")
            if attempt < _MAX_HTTP_RETRIES:
                time.sleep(_BASE_DELAY * (2 ** attempt))
                continue
            raise last_exc
    raise last_exc or ServiceError(ErrorCode.LLM_GENERATION_FAILED, "LLM 请求失败")


# ── OpenAI-compatible API ──────────────────────────────────────────────────


_ALLOWED_PROVIDERS = set(PROVIDER_PRESETS.keys()) | {"openai_compatible"}


class ModelOverride(BaseModel):
    provider: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None

    def model_post_init(self, __context: object) -> None:
        if self.provider and self.provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"Invalid provider: {self.provider}. Allowed: {list(_ALLOWED_PROVIDERS)}")


# Context variable for per-request model overrides
_model_override_ctx: contextvars.ContextVar[Optional[ModelOverride]] = contextvars.ContextVar(
    "_model_override_ctx", default=None
)


@contextlib.contextmanager
def model_override_context(override: Optional[ModelOverride]):
    """Set a per-request model override for all LLM calls in this context."""
    token = _model_override_ctx.set(override)
    try:
        yield
    finally:
        _model_override_ctx.reset(token)


def _resolve_overrides(override: Optional[ModelOverride]) -> dict:
    settings = get_settings()

    # Check context variable if no explicit override
    if override is None:
        override = _model_override_ctx.get()

    # Start from provider preset if specified
    preset: Dict[str, str] = {}
    if override and override.provider and override.provider in PROVIDER_PRESETS:
        preset = PROVIDER_PRESETS[override.provider]

    api_base = (
        override.api_base if override and override.api_base
        else preset.get("api_base") or settings.llm_api_base
    ).rstrip("/")

    api_key = (
        override.api_key if override and override.api_key
        else preset.get("api_key") or settings.llm_api_key
    )

    model = (
        override.model_name if override and override.model_name
        else preset.get("model") or settings.llm_model
    )

    temperature = (
        override.temperature if override and override.temperature is not None
        else settings.llm_temperature
    )

    # Spark uses WebSocket, not HTTP — override must route to spark
    use_spark = (override and override.provider == "spark") or (
        not override and settings.model_provider == "spark"
    )

    provider = (
        override.provider if override and override.provider
        else settings.model_provider
    )

    return {
        "provider": provider,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
        "timeout": settings.llm_timeout_seconds,
        "max_tokens": settings.llm_max_tokens,
        "use_spark": use_spark,
    }


def _call_openai_compatible(prompt: str, override: Optional[ModelOverride] = None) -> str:
    cfg = _resolve_overrides(override)
    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 未配置")

    url = f"{cfg['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
    }

    client = _get_http_client(timeout=cfg["timeout"])
    response = _retry_request(client, "POST", url, json=payload, headers=headers)
    if response.status_code == 401:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 无效或已过期")
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "AI 服务返回空结果")
    return choices[0].get("message", {}).get("content", "").strip()


def _call_openai_compatible_with_system(system_prompt: str, user_prompt: str, override: Optional[ModelOverride] = None) -> str:
    cfg = _resolve_overrides(override)
    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 未配置")

    url = f"{cfg['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
    }

    client = _get_http_client(timeout=cfg["timeout"])
    response = _retry_request(client, "POST", url, json=payload, headers=headers)
    if response.status_code == 401:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 无效或已过期")
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "AI 服务返回空结果")
    return choices[0].get("message", {}).get("content", "").strip()


def _call_openai_compatible_json(prompt: str, override: Optional[ModelOverride] = None) -> dict:
    """Call with JSON mode enabled."""
    cfg = _resolve_overrides(override)
    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 未配置")

    url = f"{cfg['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {
                "role": "system",
                "content": "You must respond with valid JSON only. No markdown, no explanation, just the JSON object.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
    }

    # Only OpenAI-compatible providers support response_format
    if cfg.get("provider") in ("openai", "openai_compatible", "deepseek"):
        payload["response_format"] = {"type": "json_object"}

    client = _get_http_client(timeout=cfg["timeout"])
    response = _retry_request(client, "POST", url, json=payload, headers=headers)
    if response.status_code == 401:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 无效或已过期")
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "AI 服务返回空结果")
    content = choices[0].get("message", {}).get("content", "").strip()
    return _extract_json_object(content)


def analyze_images(prompt: str, images: List[str], override: Optional[ModelOverride] = None) -> str:
    """Analyze images using vision-capable model (GPT-4o, etc.)."""
    cfg = _resolve_overrides(override)
    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 未配置")

    # Use full model for vision if current model is mini variant
    vision_model = cfg["model"]
    if "mini" in vision_model:
        vision_model = vision_model.replace("-mini", "")
    if "gpt-" not in vision_model and "claude" not in vision_model:
        vision_model = cfg["model"]

    url = f"{cfg['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    # Build content array with text and images
    content_parts: List[dict] = [{"type": "text", "text": prompt}]
    for img_data in images:
        if img_data.startswith("data:"):
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": img_data, "detail": "high"},
            })
        else:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": img_data, "detail": "high"},
            })

    payload = {
        "model": vision_model,
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
    }

    client = _get_http_client(timeout=cfg["timeout"] * 2)
    response = _retry_request(client, "POST", url, json=payload, headers=headers)
    if response.status_code == 401:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "Vision API Key 无效或已过期")
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, "Vision API 返回空结果")
    return choices[0].get("message", {}).get("content", "").strip()


# ── Spark WebSocket (legacy) ───────────────────────────────────────────────


def _spark_authorized_url() -> str:
    settings = get_settings()
    parsed = urlparse(settings.spark_api_url)
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = f"host: {parsed.netloc}\ndate: {date}\nGET {parsed.path} HTTP/1.1"
    signature_sha = hmac.new(
        (settings.spark_api_secret or "").encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{settings.spark_api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    query = urlencode({"authorization": authorization, "date": date, "host": parsed.netloc})
    return f"{settings.spark_api_url}?{query}"


def _call_spark(prompt: str) -> str:
    import websocket

    settings = get_settings()
    payload = {
        "header": {"app_id": settings.spark_app_id, "uid": "autolearning-live"},
        "parameter": {"chat": {"domain": settings.spark_model, "temperature": 0.4, "max_tokens": 2048}},
        "payload": {"message": {"text": [{"role": "user", "content": prompt}]}} ,
    }
    ws = websocket.create_connection(
        _spark_authorized_url(),
        timeout=settings.llm_timeout_seconds,
        sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True},
    )
    try:
        ws.send(json.dumps(payload, ensure_ascii=False))
        chunks: List[str] = []
        while True:
            message = json.loads(ws.recv())
            header = message.get("header", {})
            if header.get("code") != 0:
                raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, header.get("message", "星火模型调用失败"))
            choices = message.get("payload", {}).get("choices", {})
            for item in choices.get("text", []):
                chunks.append(item.get("content", ""))
            if choices.get("status") == 2:
                break
        return "".join(chunks).strip()
    finally:
        ws.close()


# ── Shared utilities ───────────────────────────────────────────────────────


def _repair_json_string(s: str) -> str:
    """Apply repair strategies for common LLM JSON output issues (ported from OpenMAIC)."""
    import re

    # Fix malformed property fragments: "key: value" -> "key": value
    s = re.sub(
        r'([,{]\s*)"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(true|false|null|[+-]?\d+(?:\.\d+)?)"(?=\s*[,}])',
        lambda m: f'{m.group(1)}"{m.group(2)}": {m.group(3)}',
        s,
    )

    # Double-escape LaTeX backslash commands inside JSON strings
    # Preserve valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
    def _fix_latex_in_string(match: re.Match) -> str:
        content = match.group(1)
        fixed = re.sub(
            r'\\([a-zA-Z])',
            lambda m: m.group(0) if m.group(1) in 'bfnrtu' else '\\\\' + m.group(1),
            content,
        )
        return f'"{fixed}"'

    s = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', _fix_latex_in_string, s)

    # Fix remaining invalid escape sequences
    s = re.sub(r'\\([^"\\\/bfnrtu\n\r])', lambda m: '\\\\' + m.group(1) if m.group(1).isalpha() else m.group(0), s)

    # Fix truncated JSON objects
    trimmed = s.strip()
    if trimmed.startswith('{') and not trimmed.endswith('}'):
        open_count = s.count('{')
        close_count = s.count('}')
        if open_count > close_count:
            s += '}' * (open_count - close_count)
    elif trimmed.startswith('[') and not trimmed.endswith(']'):
        last_obj = s.rfind('}')
        if last_obj > 0:
            s = s[:last_obj + 1] + ']'

    # Escape control characters
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)

    # Remove trailing commas before } or ]
    s = re.sub(r',\s*([}\]])', r'\1', s)

    return s


def _extract_json_object(text: str) -> dict:
    """Extract and parse a JSON object from LLM output with multi-strategy repair."""
    cleaned = text.strip()

    # Strategy 1: Extract from markdown code blocks
    import re
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
    for block in code_blocks:
        block = block.strip()
        if block.startswith('{') or block.startswith('['):
            try:
                payload = json.loads(block, strict=False)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                try:
                    payload = json.loads(_repair_json_string(block), strict=False)
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    pass

    # Strategy 2: Bracket-matching extraction
    first_brace = cleaned.find('{')
    first_bracket = cleaned.find('[')
    if first_brace >= 0 or first_bracket >= 0:
        start = min(
            x for x in [first_brace, first_bracket] if x >= 0
        )
        depth = 0
        in_string = False
        escape_next = False
        end = -1
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if ch in '[{':
                    depth += 1
                elif ch in ']}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end > start:
            extracted = cleaned[start:end + 1]
            try:
                payload = json.loads(extracted, strict=False)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                try:
                    payload = json.loads(_repair_json_string(extracted), strict=False)
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    pass

    # Strategy 3: Direct parse (original behavior)
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    for attempt_text in [cleaned, _repair_json_string(cleaned)]:
        try:
            payload = json.loads(attempt_text, strict=False)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        # Try substring extraction
        start = attempt_text.find("{")
        end = attempt_text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(attempt_text[start:end + 1], strict=False)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

    raise ValueError(f"无法从 LLM 输出中提取有效 JSON（前100字符: {text[:100]!r}）")


def _validate_required_keys(payload: dict, required_keys: Optional[Iterable[str]]) -> None:
    missing = [key for key in required_keys or [] if key not in payload]
    if missing:
        raise ValueError(f"Structured model output missing keys: {', '.join(missing)}")


# ── Public API ─────────────────────────────────────────────────────────────


def _dispatch_text(prompt: str, override: Optional[ModelOverride] = None) -> str:
    """Route to the configured LLM provider for text generation."""
    cfg = _resolve_overrides(override)

    if cfg["use_spark"] and not (override and override.api_base):
        status = get_model_status()
        if status["mode"] != "spark":
            raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "星火模型未配置或 websocket-client 未安装")
        return _call_spark(prompt)

    return _call_openai_compatible(prompt, override)


def _dispatch_json(prompt: str, override: Optional[ModelOverride] = None) -> dict:
    """Route to the configured LLM provider for JSON generation."""
    cfg = _resolve_overrides(override)

    if cfg["use_spark"] and not (override and override.api_base):
        status = get_model_status()
        if status["mode"] != "spark":
            raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "星火模型未配置或 websocket-client 未安装")
        return _extract_json_object(_call_spark(prompt))

    return _call_openai_compatible_json(prompt, override)


def generate_text(prompt: str, fallback: Optional[str] = None, model_override: Optional[ModelOverride] = None) -> str:
    """Generate text from the configured LLM. Raises on failure unless fallback is provided."""
    if _cb_is_open():
        if fallback is not None:
            return fallback
        raise ServiceError(ErrorCode.LLM_CIRCUIT_OPEN)
    try:
        result = _dispatch_text(prompt, model_override)
        _cb_record_success()
        return result
    except Exception:
        _cb_record_failure()
        if fallback is not None:
            return fallback
        raise


def generate_with_system_prompt(system_prompt: str, user_prompt: str, fallback: Optional[str] = None, model_override: Optional[ModelOverride] = None) -> str:
    """Generate text with separate system and user messages for better LLM instruction following."""
    if _cb_is_open():
        if fallback is not None:
            return fallback
        raise ServiceError(ErrorCode.LLM_CIRCUIT_OPEN)
    cfg = _resolve_overrides(model_override)
    try:
        if cfg["use_spark"] and not (model_override and model_override.api_base):
            result = _call_spark(f"[SYSTEM]\n{system_prompt}\n[USER]\n{user_prompt}")
        else:
            result = _call_openai_compatible_with_system(system_prompt, user_prompt, model_override)
        _cb_record_success()
        return result
    except Exception:
        _cb_record_failure()
        if fallback is not None:
            return fallback
        raise


def generate_json_with_system(
    system_prompt: str,
    user_prompt: str,
    fallback: Optional[dict] = None,
    required_keys: Optional[Iterable[str]] = None,
    model_override: Optional[ModelOverride] = None,
) -> dict:
    """Generate JSON with separate system/user messages. Falls back to text extraction on parse failure."""
    text = generate_with_system_prompt(system_prompt, user_prompt, model_override=model_override)
    try:
        parsed = json.loads(text)
        if required_keys and not all(k in parsed for k in required_keys):
            raise ValueError("missing required keys")
        return parsed
    except (json.JSONDecodeError, ValueError):
        # Try to extract JSON from markdown code blocks
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
            if required_keys and not all(k in parsed for k in required_keys):
                raise
            return parsed
        if fallback is not None:
            return fallback
        raise


def generate_stream(prompt: str, model_override: Optional[ModelOverride] = None):
    """Yield text chunks from a streaming LLM call (OpenAI-compatible SSE)."""
    if _cb_is_open():
        raise ServiceError(ErrorCode.LLM_CIRCUIT_OPEN)
    cfg = _resolve_overrides(model_override)
    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 未配置")

    url = f"{cfg['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
        "stream": True,
    }

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_HTTP_RETRIES + 1):
        yielded_any = False
        try:
            with httpx.Client(timeout=cfg["timeout"]) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_HTTP_RETRIES:
                        retry_after = response.headers.get("retry-after")
                        time.sleep(float(retry_after) if retry_after else _BASE_DELAY * (2 ** attempt))
                        continue
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yielded_any = True
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
            _cb_record_success()
            return
        except httpx.ConnectTimeout:
            _cb_record_failure()
            raise ServiceError(ErrorCode.LLM_AUTH_FAILED, f"LLM 连接失败，请检查 API 地址和网络: {url}")
        except (httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            _cb_record_failure()
            if yielded_any:
                raise
            if attempt < _MAX_HTTP_RETRIES:
                time.sleep(_BASE_DELAY * (2 ** attempt))
                continue
            raise ServiceError(ErrorCode.LLM_TIMEOUT, f"LLM 流式请求超时（{cfg['timeout']}s）")
        except Exception:
            _cb_record_failure()
            raise
    raise last_exc or ServiceError(ErrorCode.LLM_GENERATION_FAILED, "LLM 流式请求失败")


def generate_stream_with_system(system_prompt: str, user_prompt: str, model_override: Optional[ModelOverride] = None):
    """Yield text chunks from a streaming LLM call with separate system/user messages."""
    if _cb_is_open():
        raise ServiceError(ErrorCode.LLM_CIRCUIT_OPEN)
    cfg = _resolve_overrides(model_override)
    if not cfg["api_key"]:
        raise ServiceError(ErrorCode.LLM_AUTH_FAILED, "LLM API Key 未配置")

    url = f"{cfg['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
        "stream": True,
    }

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_HTTP_RETRIES + 1):
        yielded_any = False
        try:
            with httpx.Client(timeout=cfg["timeout"]) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_HTTP_RETRIES:
                        retry_after = response.headers.get("retry-after")
                        time.sleep(float(retry_after) if retry_after else _BASE_DELAY * (2 ** attempt))
                        continue
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yielded_any = True
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
            _cb_record_success()
            return  # success — exit retry loop
        except httpx.ConnectTimeout:
            _cb_record_failure()
            raise ServiceError(ErrorCode.LLM_AUTH_FAILED, f"LLM 连接失败，请检查 API 地址和网络: {url}")
        except (httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            _cb_record_failure()
            if yielded_any:
                raise  # already yielded partial data, can't retry
            if attempt < _MAX_HTTP_RETRIES:
                time.sleep(_BASE_DELAY * (2 ** attempt))
                continue
            raise ServiceError(ErrorCode.LLM_TIMEOUT, f"LLM 流式请求超时（{cfg['timeout']}s）")
        except Exception:
            _cb_record_failure()
            raise
    raise last_exc or ServiceError(ErrorCode.LLM_GENERATION_FAILED, "LLM 流式请求失败")


def generate_json(
    prompt: str,
    fallback: Optional[dict] = None,
    required_keys: Optional[Iterable[str]] = None,
    schema: Optional[type[BaseModel]] = None,
    max_retries: Optional[int] = None,
    model_override: Optional[ModelOverride] = None,
) -> dict:
    """Generate structured JSON from the configured LLM with retry and validation."""
    if _cb_is_open():
        if fallback is not None:
            return {**fallback, "_model_mode": "circuit_breaker_open", "_retry_count": 0}
        raise ServiceError(ErrorCode.LLM_CIRCUIT_OPEN)

    settings = get_settings()
    retries = settings.spark_json_retries if max_retries is None else max_retries
    last_error: Optional[Exception] = None

    strict_prompt = (
        f"{prompt}\n\n"
        f"Only return one JSON object. Required keys: {', '.join(required_keys or [])}."
    )

    for attempt in range(retries + 1):
        attempt_prompt = strict_prompt if attempt == 0 else f"{strict_prompt}\nFix the previous invalid JSON. Error: {last_error}"
        try:
            payload = _dispatch_json(attempt_prompt, model_override)
            _validate_required_keys(payload, required_keys)
            if schema is not None:
                payload = schema.model_validate(payload).model_dump(mode="json")
            payload["_model_mode"] = get_model_status()["provider"]
            payload["_retry_count"] = attempt
            _cb_record_success()
            return payload
        except (json.JSONDecodeError, ValidationError, ValueError, RuntimeError, httpx.HTTPError) as exc:
            last_error = exc

    _cb_record_failure()
    # All retries exhausted
    if fallback is not None:
        return {**fallback, "_model_mode": "fallback_after_retries", "_retry_count": retries + 1}

    raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"结构化 JSON 生成失败（{retries + 1} 次尝试）: {last_error}")
