import { useMemo } from "react";

interface WebResult {
  title: string;
  url: string;
  description: string;
  platform: string;
  thumbnail?: string;
  metadata?: { play?: number; duration?: string; author?: string; [key: string]: unknown };
}

interface Props {
  results: WebResult[];
  resourceType: string;
}

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: "B站",
  youtube: "YouTube",
  github: "GitHub",
  csdn: "CSDN",
  zhihu: "知乎",
  juejin: "掘金",
  jianshu: "简书",
  segmentfault: "思否",
  stackoverflow: "StackOverflow",
  runoob: "菜鸟教程",
  w3schools: "W3Schools",
  mdn: "MDN",
  wikipedia: "维基百科",
  web: "网页",
};

const PLATFORM_COLORS: Record<string, string> = {
  bilibili: "#00a1d6",
  youtube: "#ff0000",
  github: "#333",
  csdn: "#fc5531",
  zhihu: "#0066ff",
  juejin: "#1e80ff",
  jianshu: "#ea6f5a",
  segmentfault: "#009a61",
  stackoverflow: "#f48024",
  runoob: "#27ae60",
  w3schools: "#04aa6d",
  mdn: "#1b1b1b",
  wikipedia: "#636466",
  web: "#6b7280",
};

const TYPE_LABELS: Record<string, string> = {
  video: "视频",
  animation: "动画",
  flowchart: "流程图",
  mindmap: "思维导图",
  document: "文档",
  reading: "阅读材料",
  quiz: "练习题",
  code_case: "代码示例",
};

export function WebFallbackView({ results, resourceType }: Props) {
  const label = TYPE_LABELS[resourceType] || "资源";

  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      // Prefer video platforms for video types
      if (resourceType === "video" || resourceType === "animation") {
        const aIsVideo = ["bilibili", "youtube"].includes(a.platform);
        const bIsVideo = ["bilibili", "youtube"].includes(b.platform);
        if (aIsVideo && !bIsVideo) return -1;
        if (!aIsVideo && bIsVideo) return 1;
      }
      return 0;
    });
  }, [results, resourceType]);

  if (results.length === 0) {
    return (
      <div className="resource-error-card">
        <p className="resource-error-msg">未找到相关{label}资源</p>
        <p className="resource-error-hint">AI 生成失败且未搜索到网络资源，请稍后重试。</p>
      </div>
    );
  }

  return (
    <div className="web-fallback-view">
      <div className="web-fallback-header">
        <span className="web-fallback-badge">网络资源</span>
        <span className="web-fallback-desc">
          AI 生成失败，以下是从网络搜索到的相关{label}资源
        </span>
      </div>

      <div className="web-fallback-list">
        {sortedResults.map((r, i) => {
          const platform = r.platform || "web";
          const platformLabel = PLATFORM_LABELS[platform] || platform;
          const platformColor = PLATFORM_COLORS[platform] || "#6b7280";

          return (
            <a
              key={i}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="web-fallback-item"
            >
              {r.thumbnail && (
                <div className="web-fallback-thumb">
                  <img src={r.thumbnail} alt={r.title} loading="lazy" />
                </div>
              )}
              <div className="web-fallback-content">
                <div className="web-fallback-title">{r.title || "无标题"}</div>
                {r.description && (
                  <div className="web-fallback-item-desc">{r.description}</div>
                )}
                <div className="web-fallback-meta">
                  <span
                    className="web-fallback-platform"
                    style={{ backgroundColor: platformColor }}
                  >
                    {platformLabel}
                  </span>
                  {r.metadata?.play != null && (
                    <span className="web-fallback-stat">
                      {Number(r.metadata.play).toLocaleString()} 播放
                    </span>
                  )}
                  {r.metadata?.duration != null && (
                    <span className="web-fallback-stat">{String(r.metadata.duration)}</span>
                  )}
                </div>
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
}
