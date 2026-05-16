import { useState, useEffect, useCallback } from "react";
import { User, Route, FileText, HelpCircle, Code, Play, GitBranch, ChevronLeft, ChevronRight, Search, BarChart3 } from "lucide-react";
import { useAppContext } from "../../context/AppContext";
import { ProfilePanel } from "../profile/ProfilePanel";
import { LearningPathPanel } from "../../pages/LearningPathPanel";
import { ResourceRenderer } from "../resource/ResourceRenderer";
import { GraphViz } from "../graph/GraphViz";
import { AssessmentPanel } from "../assessment/AssessmentPanel";
import { apiGet } from "../../api/client";
import type { LearningResource } from "../../types/baseline";

type PanelKey = "profile" | "path" | "assessment" | "document" | "quiz" | "code" | "video" | "graph";

const PANELS: { key: PanelKey; label: string; icon: typeof User }[] = [
  { key: "profile", label: "画像", icon: User },
  { key: "path", label: "路径", icon: Route },
  { key: "assessment", label: "评估", icon: BarChart3 },
  { key: "document", label: "文档", icon: FileText },
  { key: "quiz", label: "题库", icon: HelpCircle },
  { key: "code", label: "代码", icon: Code },
  { key: "video", label: "视频", icon: Play },
  { key: "graph", label: "图谱", icon: GitBranch },
];

interface GraphNode {
  id: string;
  name: string;
  level: number;
  depends_on: string[];
  description: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface AnswerRecord {
  id: string;
  question_id: string;
  user_answer: unknown;
  is_correct: boolean | null;
  score: number | null;
  grading_method: string;
  time_spent_seconds: number | null;
  submitted_at: string;
}

export function ResourcePanelGroup() {
  const { state } = useAppContext();
  const { profile, learningPath, resources } = state;
  const [activePanel, setActivePanel] = useState<PanelKey>("profile");
  const [collapsed, setCollapsed] = useState(false);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [biliKeyword, setBiliKeyword] = useState("");
  const [biliResults, setBiliResults] = useState<Array<{ bvid: string; title: string; author: string; play: number; duration: string; url: string; pic: string }>>([]);
  const [biliLoading, setBiliLoading] = useState(false);
  const [answerRecords, setAnswerRecords] = useState<AnswerRecord[]>([]);
  const [graphError, setGraphError] = useState(false);
  const [answersError, setAnswersError] = useState(false);

  const hasProfile = profile.completeness_score > 0;
  const hasPath = learningPath.nodes.length > 0;
  const hasResources = resources.length > 0;

  const filterResources = useCallback(
    (type: PanelKey): LearningResource[] => {
      if (type === "document") return resources.filter((r) => r.resource_type === "document" || r.resource_type === "mindmap" || r.resource_type === "reading" || r.resource_type === "flowchart");
      if (type === "quiz") return resources.filter((r) => r.resource_type === "quiz");
      if (type === "code") return resources.filter((r) => r.resource_type === "code_case");
      if (type === "video") return resources.filter((r) => r.resource_type === "video" || r.resource_type === "animation");
      return [];
    },
    [resources]
  );

  // Auto-switch to first available panel when data arrives
  useEffect(() => {
    if (activePanel !== "profile") return;
    if (hasProfile) return;
    if (hasPath) { setActivePanel("path"); return; }
    if (hasResources) {
      const t = resources[0].resource_type;
      if (t === "quiz") setActivePanel("quiz");
      else if (t === "code_case") setActivePanel("code");
      else if (t === "video" || t === "animation") setActivePanel("video");
      else setActivePanel("document"); // document, mindmap, reading, flowchart
    }
  }, [hasProfile, hasPath, hasResources, resources, activePanel]);

  // Load knowledge graph
  useEffect(() => {
    if (activePanel === "graph" && !graphData && !graphError) {
      apiGet<GraphData>("/knowledge/graph")
        .then((data) => setGraphData(data))
        .catch(() => setGraphError(true));
    }
  }, [activePanel, graphData, graphError]);

  // Load answer records when quiz tab is active
  useEffect(() => {
    if (activePanel === "quiz" && state.user?.id && answerRecords.length === 0 && !answersError) {
      apiGet<AnswerRecord[]>(`/resources/answers`)
        .then((data) => setAnswerRecords(data))
        .catch(() => setAnswersError(true));
    }
  }, [activePanel, state.user?.id, answerRecords.length, answersError]);

  const handleBiliSearch = async () => {
    if (!biliKeyword.trim()) return;
    setBiliLoading(true);
    try {
      const data = await apiGet<{ results: typeof biliResults }>(`/bilibili/search/${encodeURIComponent(biliKeyword)}?page_size=5`);
      setBiliResults(data.results ?? []);
    } catch {
      setBiliResults([]);
    } finally {
      setBiliLoading(false);
    }
  };

  if (collapsed) {
    return (
      <div className="resource-panel-collapsed">
        <button className="resource-panel-expand" onClick={() => setCollapsed(false)} type="button" title="展开资源面板">
          <ChevronLeft size={16} />
        </button>
        {PANELS.map(({ key, label, icon: Icon }) => {
          const available =
            (key === "profile" && hasProfile) ||
            (key === "path" && hasPath) ||
            (key === "graph") ||
            (key === "assessment") ||
            (key === "quiz" && (filterResources("quiz").length > 0 || answerRecords.length > 0)) ||
            (["document", "code", "video"].includes(key) && filterResources(key).length > 0);
          if (!available) return null;
          return (
            <button
              key={key}
              className="resource-panel-icon-btn"
              onClick={() => { setActivePanel(key); setCollapsed(false); }}
              type="button"
              title={label}
            >
              <Icon size={16} />
            </button>
          );
        })}
      </div>
    );
  }

  const renderContent = () => {
    switch (activePanel) {
      case "profile":
        if (!hasProfile) return <div className="resource-panel-empty">暂无画像数据，请先开始学习对话</div>;
        return <ProfilePanel profile={profile} />;

      case "path":
        if (!hasPath) return <div className="resource-panel-empty">暂无学习路径，请先开始学习对话</div>;
        return <LearningPathPanel path={learningPath} />;

      case "assessment":
        return <AssessmentPanel />;

      case "document":
      case "code": {
        const items = filterResources(activePanel);
        if (items.length === 0) return <div className="resource-panel-empty">暂无{PANELS.find((p) => p.key === activePanel)?.label}资源</div>;
        return (
          <div className="resource-panel-list">
            {items.map((r) => (
              <div key={r.resource_id} className="resource-panel-item">
                <div className="resource-panel-item-title">{r.title}</div>
                <ResourceRenderer resource={r} />
              </div>
            ))}
          </div>
        );
      }

      case "quiz": {
        const quizItems = filterResources("quiz");
        const hasQuiz = quizItems.length > 0;
        const hasAnswers = answerRecords.length > 0;
        if (!hasQuiz && !hasAnswers) return <div className="resource-panel-empty">暂无题库资源或答题记录</div>;
        return (
          <div className="resource-panel-list">
            {quizItems.map((r) => (
              <div key={r.resource_id} className="resource-panel-item">
                <div className="resource-panel-item-title">{r.title}</div>
                <ResourceRenderer resource={r} />
              </div>
            ))}
            {hasAnswers && (
              <div className="answer-records-section">
                <div className="answer-records-title">答题记录</div>
                {answerRecords.map((rec) => (
                  <div key={rec.id} className={`answer-record ${rec.is_correct ? "correct" : "wrong"}`}>
                    <div className="answer-record-row">
                      <span className="answer-record-badge">{rec.is_correct === null ? "?" : rec.is_correct ? "✓" : "✗"}</span>
                      <span className="answer-record-score">{rec.score != null ? `${rec.score}/100` : "-"}</span>
                      {rec.time_spent_seconds != null && (
                        <span className="answer-record-time">{rec.time_spent_seconds}s</span>
                      )}
                      <span className="answer-record-meta">{new Date(rec.submitted_at).toLocaleDateString()}</span>
                    </div>
                    <div className="answer-record-answer">{typeof rec.user_answer === "string" ? rec.user_answer : JSON.stringify(rec.user_answer)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      }

      case "video": {
        const videoItems = filterResources("video");
        return (
          <div className="resource-panel-list">
            {videoItems.map((r) => (
              <div key={r.resource_id} className="resource-panel-item">
                <div className="resource-panel-item-title">{r.title}</div>
                <ResourceRenderer resource={r} />
              </div>
            ))}
            <div className="resource-panel-bili">
              <div className="resource-panel-bili-search">
                <input
                  placeholder="搜索B站教学视频..."
                  value={biliKeyword}
                  onChange={(e) => setBiliKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleBiliSearch()}
                />
                <button onClick={handleBiliSearch} disabled={biliLoading} type="button">
                  <Search size={14} />
                </button>
              </div>
              {biliResults.map((v) => (
                <a key={v.bvid} className="resource-panel-bili-item" href={v.url} target="_blank" rel="noopener noreferrer">
                  {v.pic && <img src={v.pic} alt="" loading="lazy" />}
                  <div>
                    <div className="resource-panel-item-title">{v.title}</div>
                    <div className="resource-panel-item-meta">{v.author} · {v.duration} · {v.play.toLocaleString()} 播放</div>
                  </div>
                </a>
              ))}
            </div>
          </div>
        );
      }

      case "graph":
        if (graphError) return <div className="resource-panel-empty">图谱加载失败</div>;
        if (!graphData) return <div className="resource-panel-empty">加载中...</div>;
        return <GraphViz nodes={graphData.nodes} edges={graphData.edges} />;

      default:
        return null;
    }
  };

  return (
    <div className="resource-panel-group">
      <div className="resource-panel-header">
        <div className="resource-panel-tabs">
          {PANELS.map(({ key, label, icon: Icon }) => {
            const available =
              (key === "profile" && hasProfile) ||
              (key === "path" && hasPath) ||
              (key === "graph") ||
              (key === "quiz" && (filterResources("quiz").length > 0 || answerRecords.length > 0)) ||
              (["document", "code", "video"].includes(key) && filterResources(key).length > 0);
            return (
              <button
                key={key}
                className={`resource-panel-tab ${activePanel === key ? "active" : ""} ${!available ? "disabled" : ""}`}
                onClick={() => available && setActivePanel(key)}
                type="button"
                disabled={!available}
              >
                <Icon size={14} />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
        <button className="resource-panel-collapse" onClick={() => setCollapsed(true)} type="button" title="收起">
          <ChevronRight size={14} />
        </button>
      </div>
      <div className="resource-panel-content">
        {renderContent()}
      </div>
    </div>
  );
}
