import { describe, expect, it } from "vitest";
import {
  buildStartStreamPayload,
  buildTutorFollowupResourceRequest,
  mergeLearningResources,
  normalizeImageMessageContent,
  selectFollowupResourceTypes,
} from "./ChatPanel";
import type { LearningResource } from "../../types/baseline";

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

describe("tutor follow-up resources", () => {
  it("selects stable inline resource types and filters heavy media", () => {
    expect(selectFollowupResourceTypes({
      recommended_types: ["video", "document", "quiz", "animation", "mindmap"],
    })).toEqual(["document", "quiz"]);
  });

  it("skips silent recommendations", () => {
    expect(selectFollowupResourceTypes({ decision: "silent", recommended_types: ["document"] })).toEqual([]);
  });

  it("builds a resource generation request from tutor recommendation", () => {
    const request = buildTutorFollowupResourceRequest({
      userId: "user-1",
      baseAgentId: "agent-1",
      fallbackTopic: "回退主题",
      tutorResult: {
        resource_recommendation: {
          knowledge_point: "递归",
          recommended_types: ["mindmap", "flowchart", "video"],
          resource_params: { difficulty: 1 },
        },
      },
    });

    expect(request).toEqual({
      user_id: "user-1",
      subject: "递归",
      knowledge_point: "递归",
      resource_types: ["mindmap", "flowchart"],
      difficulty: "easy",
      base_agent_id: "agent-1",
    });
  });

  it("deduplicates generated resources before appending them to a message", () => {
    const existing = [
      { resource_id: "resource-1", title: "旧资源" },
    ] as LearningResource[];
    const incoming = [
      { resource_id: "resource-1", title: "重复资源" },
      { resource_id: "resource-2", title: "新资源" },
    ] as LearningResource[];

    expect(mergeLearningResources(existing, incoming).map((resource) => resource.resource_id)).toEqual([
      "resource-1",
      "resource-2",
    ]);
  });
});
