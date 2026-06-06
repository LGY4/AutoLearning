import { describe, expect, it } from "vitest";
import { buildResourceLearningSummary } from "./resourceActions";

describe("buildResourceLearningSummary", () => {
  it("builds action targets and metadata for generated resources", () => {
    const summary = buildResourceLearningSummary({
      knowledge_point: "递归",
      resource_type: "document",
      generated_by: "document_agent",
      quality_score: 0.87,
      metadata: {
        rag_basis: ["chunk-1"],
        rag_titles: ["递归基础", "递归基础", "函数调用栈"],
        two_stage: true,
      },
    });

    expect(summary.topic).toBe("递归");
    expect(summary.typeLabel).toBe("学习文档");
    expect(summary.generatedByLabel).toBe("文档 Agent");
    expect(summary.qualityPercent).toBe(87);
    expect(summary.methodLabels).toEqual(["大纲分段生成", "RAG 增强"]);
    expect(summary.sourceTitles).toEqual(["递归基础", "函数调用栈"]);
    expect(summary.practicePath).toBe("/practice?knowledge_point=%E9%80%92%E5%BD%92");
    expect(summary.chatPrompt).toContain("围绕「递归」继续讲解");
  });

  it("falls back safely for uploaded or sparse resources", () => {
    const summary = buildResourceLearningSummary({
      title: "用户上传资料",
      generated_by: "user_upload",
      quality_score: 92,
      metadata: { filename: "notes.md" },
    });

    expect(summary.topic).toBe("用户上传资料");
    expect(summary.typeLabel).toBe("学习资源");
    expect(summary.generatedByLabel).toBe("用户上传");
    expect(summary.qualityPercent).toBe(92);
    expect(summary.methodLabels).toEqual(["用户上传"]);
    expect(summary.sourceTitles).toEqual([]);
  });

  it("reads references from structured drafts", () => {
    const summary = buildResourceLearningSummary({
      knowledge_point: "动态规划",
      resource_type: "reading",
      generated_by: "document_agent",
      metadata: {
        draft: {
          references: [{ title: "最优子结构" }, { source: "状态转移案例" }],
        },
      },
    });

    expect(summary.sourceTitles).toEqual(["最优子结构", "状态转移案例"]);
  });
});
