interface ResourceActionInput {
  knowledge_point?: string;
  title?: string;
  resource_type?: string;
  generated_by?: string;
  quality_score?: number | null;
  metadata?: Record<string, unknown>;
}

export interface ResourceLearningSummary {
  topic: string;
  typeLabel: string;
  generatedByLabel: string;
  qualityPercent: number | null;
  methodLabels: string[];
  sourceTitles: string[];
  chatPrompt: string;
  practicePath: string;
  mapPath: string;
}

const TYPE_LABELS: Record<string, string> = {
  document: "学习文档",
  reading: "阅读材料",
  quiz: "练习测验",
  mindmap: "思维导图",
  flowchart: "流程图",
  video: "视频分镜",
  animation: "动画脚本",
  code_case: "代码案例",
};

const AGENT_LABELS: Record<string, string> = {
  document_agent: "文档 Agent",
  quiz_agent: "练习 Agent",
  mindmap_agent: "导图 Agent",
  flowchart_agent: "流程图 Agent",
  video_agent: "视频 Agent",
  code_agent: "代码 Agent",
  quality_agent: "质量 Agent",
  user_upload: "用户上传",
  error: "生成异常",
};

function firstText(...values: Array<unknown>): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function normalizeQuality(score: number | null | undefined): number | null {
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  const percent = score <= 1 ? score * 100 : score;
  return Math.max(0, Math.min(100, Math.round(percent)));
}

function referenceTitle(reference: unknown): string {
  if (typeof reference === "string") return reference;
  if (!reference || typeof reference !== "object") return "";
  const item = reference as Record<string, unknown>;
  return firstText(item.title, item.name, item.source, item.url);
}

function readReferences(metadata: Record<string, unknown> | undefined): string[] {
  if (!metadata) return [];

  const ragTitles = Array.isArray(metadata.rag_titles)
    ? metadata.rag_titles.map(referenceTitle)
    : [];

  const draft = metadata.draft && typeof metadata.draft === "object"
    ? metadata.draft as Record<string, unknown>
    : null;
  const draftReferences = draft && Array.isArray(draft.references)
    ? draft.references.map(referenceTitle)
    : [];

  return unique([...ragTitles, ...draftReferences]).slice(0, 3);
}

function readMethodLabels(metadata: Record<string, unknown> | undefined): string[] {
  if (!metadata) return [];

  const labels: string[] = [];
  if (metadata.source === "cache") labels.push("题库缓存");
  if (metadata.source === "web_search") labels.push("网络检索");
  if (metadata.two_stage) labels.push("大纲分段生成");
  if (Array.isArray(metadata.rag_basis) && metadata.rag_basis.length > 0) labels.push("RAG 增强");
  if (metadata.video_url || metadata.video_path || metadata.scene_images) labels.push("多媒体渲染");
  if (metadata.filename) labels.push("用户上传");
  return unique(labels).slice(0, 3);
}

function topicPath(path: string, param: string, topic: string): string {
  return `${path}?${param}=${encodeURIComponent(topic)}`;
}

export function buildResourceLearningSummary(resource: ResourceActionInput): ResourceLearningSummary {
  const topic = firstText(resource.knowledge_point, resource.title) || "当前资源";
  const typeLabel = TYPE_LABELS[resource.resource_type ?? ""] ?? resource.resource_type ?? "学习资源";
  const generatedBy = resource.generated_by ?? "";
  const generatedByLabel = (AGENT_LABELS[generatedBy] ?? generatedBy.replace(/_/g, " ")) || "自动生成";

  return {
    topic,
    typeLabel,
    generatedByLabel,
    qualityPercent: normalizeQuality(resource.quality_score),
    methodLabels: readMethodLabels(resource.metadata),
    sourceTitles: readReferences(resource.metadata),
    chatPrompt: `围绕「${topic}」继续讲解，并结合刚才的${typeLabel}给出下一步学习重点。`,
    practicePath: topicPath("/practice", "knowledge_point", topic),
    mapPath: "/map",
  };
}
