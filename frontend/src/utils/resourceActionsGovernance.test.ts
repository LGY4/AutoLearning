import { describe, expect, it } from "vitest";
import { buildResourceLearningSummary } from "./resourceActions";

describe("resource governance metadata", () => {
  it("formats governed RAG source metadata for resource panels", () => {
    const summary = buildResourceLearningSummary({
      knowledge_point: "Stack",
      resource_type: "document",
      generated_by: "document_agent",
      metadata: {
        rag_sources: [
          {
            title: "Stack basics",
            source_name: "Python Documentation",
            source_url: "https://docs.python.org/3/tutorial/datastructures.html",
            source_type: "official_documentation",
            authority_level: "official",
            review_status: "approved",
          },
        ],
      },
    });

    expect(summary.sourceTitles).toEqual(["Stack basics · Python Documentation · 官方来源 · 已审核"]);
    expect(summary.sources[0]).toEqual({
      title: "Stack basics",
      sourceName: "Python Documentation",
      sourceUrl: "https://docs.python.org/3/tutorial/datastructures.html",
      sourceType: "official_documentation",
      authorityLevel: "official",
      reviewStatus: "approved",
    });
  });
});
