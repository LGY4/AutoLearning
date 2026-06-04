import { describe, it, expect } from "vitest";
import { getFriendlyError } from "./client";

describe("getFriendlyError", () => {
  it("returns code-based message when errorCode matches", () => {
    expect(getFriendlyError("some detail", "LLM_TIMEOUT")).toBe("AI 服务响应超时，请稍后重试");
    expect(getFriendlyError("some detail", "LLM_RATE_LIMITED")).toBe("AI 服务繁忙，请稍后再试");
    expect(getFriendlyError("some detail", "LLM_AUTH_FAILED")).toBe("AI 服务认证失败，请检查模型配置");
  });

  it("returns detail when it contains known patterns", () => {
    expect(getFriendlyError("request timed out")).toBe("AI 服务响应超时，请稍后重试");
    expect(getFriendlyError("circuit breaker open")).toBe("AI 服务暂时不可用，请稍后重试");
    expect(getFriendlyError("invalid API key")).toBe("AI 服务认证失败，请检查模型配置");
  });

  it("returns Chinese detail as-is when short", () => {
    expect(getFriendlyError("标题不能为空")).toBe("标题不能为空");
  });

  it("returns generic fallback for unknown errors", () => {
    expect(getFriendlyError("some random error")).toBe("请求失败，请重试");
  });
});
