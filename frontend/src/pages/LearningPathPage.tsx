import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Map, RefreshCw, PlayCircle, CheckCircle2, Lock, Circle, SkipForward } from "lucide-react";
import { apiGet, apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";
import type { LearningPath, LearningPathNode } from "../types/baseline";

const STATUS_CONFIG: Record<string, { icon: typeof Circle; color: string; label: string }> = {
  locked: { icon: Lock, color: "rgba(255,255,255,0.3)", label: "未解锁" },
  available: { icon: Circle, color: "#60a5fa", label: "可学习" },
  learning: { icon: PlayCircle, color: "#facc15", label: "学习中" },
  completed: { icon: CheckCircle2, color: "#4ade80", label: "已完成" },
  skipped: { icon: SkipForward, color: "rgba(255,255,255,0.4)", label: "已跳过" },
};

export function LearningPathPage() {
  const { state, dispatch } = useAppContext();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const path = state.learningPath;

  useEffect(() => {
    loadPath();
  }, []);

  async function loadPath() {
    setLoading(true);
    try {
      const p = await apiGet<LearningPath>("/learning-paths");
      dispatch({ type: "SET_PATH", payload: p });
    } catch {
      // No path yet
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (!state.profile?.learning_goal?.current_goal) {
      setError("请先设置学习目标");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const p = await apiPost<LearningPath>("/learning-paths/generate", {
        user_id: state.user?.id,
        goal: state.profile.learning_goal.current_goal,
        subject: state.profile.basic_info?.major || "通用",
      });
      dispatch({ type: "SET_PATH", payload: p });
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  }

  function handleStartLearning(node: LearningPathNode) {
    navigate(`/chat?topic=${encodeURIComponent(node.knowledge_point)}`);
  }

  async function handleMarkComplete(node: LearningPathNode) {
    if (!path || !state.user?.id) return;
    // Optimistic update
    const updatedNodes = path.nodes.map((n, i, arr) => {
      if (n.node_id === node.node_id) return { ...n, status: "completed" as const };
      if (i > 0 && arr[i - 1].node_id === node.node_id && n.status === "locked") {
        return { ...n, status: "available" as const };
      }
      return n;
    });
    dispatch({ type: "SET_PATH", payload: { ...path, nodes: updatedNodes } });
    try {
      await apiPost("/learning/path/node/complete", { user_id: state.user.id, node_id: node.node_id });
    } catch {
      // Backend sync failed, optimistic update already applied
    }
  }

  if (loading) return <div className="page-loading">加载中...</div>;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1><Map size={24} /> 学习路径</h1>
        <button className="btn-primary" onClick={handleGenerate} disabled={generating}>
          <RefreshCw size={16} /> {generating ? "生成中..." : "重新生成"}
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {!path || path.nodes.length === 0 ? (
        <div className="empty-state">
          <p>暂无学习路径。点击"重新生成"基于你的画像创建个性化学习路径。</p>
        </div>
      ) : (
        <>
          <div className="info-card" style={{ marginBottom: 16 }}>
            <div className="info-card-header">
              <h3>{path.title || "学习路径"}</h3>
              <span className="tag">{path.status}</span>
            </div>
            <p className="info-card-desc">版本 v{path.strategy ? 1 : 1} · 共 {path.nodes.length} 个节点</p>
          </div>

          {/* Gantt-style progress overview */}
          <div className="gantt-overview" style={{ marginBottom: 24 }}>
            <div className="gantt-bar-container">
              <div className="gantt-bar" style={{
                width: `${path.nodes.filter(n => n.status === 'completed').length / Math.max(path.nodes.length, 1) * 100}%`
              }} />
            </div>
            <div className="gantt-stats">
              <span>已完成 {path.nodes.filter(n => n.status === 'completed').length}/{path.nodes.length} 节点</span>
              <span>预计总时长 {path.nodes.reduce((s, n) => s + (n.estimated_minutes || 0), 0)} 分钟</span>
              <span>剩余 {path.nodes.filter(n => n.status !== 'completed' && n.status !== 'skipped').reduce((s, n) => s + (n.estimated_minutes || 0), 0)} 分钟</span>
            </div>
          </div>

          <div className="path-timeline">
            {path.nodes
              .sort((a, b) => a.order - b.order)
              .map((node) => {
                const cfg = STATUS_CONFIG[node.status] ?? STATUS_CONFIG.available;
                const StatusIcon = cfg.icon;
                const canInteract = node.status === "available" || node.status === "learning";
                return (
                  <div className="path-node" key={node.node_id}>
                    <div className="path-node-marker" style={{ borderColor: cfg.color }}>
                      <span>{node.order}</span>
                    </div>
                    <div className="path-node-content">
                      <div className="path-node-header">
                        <strong>{node.knowledge_point}</strong>
                        <span className="tag" style={{ color: cfg.color }}>
                          <StatusIcon size={14} /> {cfg.label}
                        </span>
                      </div>
                      {node.reason && <p className="path-node-reason">{node.reason}</p>}
                      <div className="path-node-meta">
                        {node.recommended_resource_types?.map((t) => (
                          <span className="tag" key={t}>{t}</span>
                        ))}
                        {node.estimated_minutes > 0 && (
                          <span className="tag">预计 {node.estimated_minutes} 分钟</span>
                        )}
                      </div>
                      {canInteract && (
                        <div className="path-node-actions">
                          <button className="btn-primary btn-sm" onClick={() => handleStartLearning(node)} type="button">
                            <PlayCircle size={14} /> 开始学习
                          </button>
                          <button className="btn-secondary btn-sm" onClick={() => handleMarkComplete(node)} type="button">
                            <CheckCircle2 size={14} /> 标记完成
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        </>
      )}
    </div>
  );
}
