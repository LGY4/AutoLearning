import { describe, expect, it } from "vitest";
import { buildStartStreamPayload, normalizeImageMessageContent } from "./ChatPanel";

describe("buildStartStreamPayload", () => {
  it("keeps uploaded images in the learning pipeline payload", () => {
    const payload = buildStartStreamPayload({
      content: "分析这张图并生成学习资源",
      conversationId: "conversation-1",
      baseAgentId: "agent-1",
      images: ["data:image/png;base64,abc"],
    });

    expect(payload).toEqual({
      message: "分析这张图并生成学习资源",
      conversation_id: "conversation-1",
      base_agent_id: "agent-1",
      images: ["data:image/png;base64,abc"],
    });
  });

  it("omits images when no image is attached", () => {
    const payload = buildStartStreamPayload({
      content: "生成学习路径",
      conversationId: null,
      baseAgentId: null,
    });

    expect(payload).toEqual({
      message: "生成学习路径",
      conversation_id: null,
      base_agent_id: null,
    });
  });
});

describe("normalizeImageMessageContent", () => {
  it("uses user text when an image message has text", () => {
    expect(normalizeImageMessageContent(" 分析这张图 ")).toBe("分析这张图");
  });

  it("uses a useful default when an image message has no text", () => {
    expect(normalizeImageMessageContent("")).toBe("请分析这张图片并给出学习建议");
  });
});
