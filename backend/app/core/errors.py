from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_CIRCUIT_OPEN = "LLM_CIRCUIT_OPEN"
    LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"
    KNOWLEDGE_BASE_EMPTY = "KNOWLEDGE_BASE_EMPTY"
    RESOURCE_GENERATION_FAILED = "RESOURCE_GENERATION_FAILED"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    GRADING_FAILED = "GRADING_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_FRIENDLY_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.LLM_TIMEOUT: "AI 服务响应超时，请稍后重试",
    ErrorCode.LLM_RATE_LIMITED: "AI 服务繁忙，请稍后再试",
    ErrorCode.LLM_AUTH_FAILED: "AI 服务认证失败，请检查 API 配置",
    ErrorCode.LLM_CIRCUIT_OPEN: "AI 服务暂时不可用，请稍后重试",
    ErrorCode.LLM_GENERATION_FAILED: "AI 生成失败，请重试",
    ErrorCode.KNOWLEDGE_BASE_EMPTY: "知识库尚未导入，部分功能受限",
    ErrorCode.RESOURCE_GENERATION_FAILED: "资源生成失败，请重试",
    ErrorCode.PROFILE_NOT_FOUND: "学习档案未找到，请先完成入学诊断",
    ErrorCode.GRADING_FAILED: "评分服务暂时不可用，请重试",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误，请稍后重试",
}


def friendly_message(code: ErrorCode) -> str:
    return _FRIENDLY_MESSAGES.get(code, "发生未知错误，请稍后重试")


def error_http_status(code: ErrorCode) -> int:
    """Map ErrorCode to appropriate HTTP status code."""
    _STATUS_MAP: dict[ErrorCode, int] = {
        ErrorCode.LLM_TIMEOUT: 504,
        ErrorCode.LLM_RATE_LIMITED: 429,
        ErrorCode.LLM_AUTH_FAILED: 502,
        ErrorCode.LLM_CIRCUIT_OPEN: 503,
        ErrorCode.LLM_GENERATION_FAILED: 502,
        ErrorCode.KNOWLEDGE_BASE_EMPTY: 424,
        ErrorCode.RESOURCE_GENERATION_FAILED: 500,
        ErrorCode.PROFILE_NOT_FOUND: 404,
        ErrorCode.GRADING_FAILED: 500,
        ErrorCode.INTERNAL_ERROR: 500,
    }
    return _STATUS_MAP.get(code, 500)


class ServiceError(Exception):
    def __init__(self, code: ErrorCode, detail: str | None = None):
        self.code = code
        self.detail = detail or friendly_message(code)
        super().__init__(self.detail)
