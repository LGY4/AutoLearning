import { Route, Lock, CheckCircle2, PlayCircle, SkipForward, Circle } from "lucide-react";
import type { LearningPath } from "../types/baseline";
import { useAppContext } from "../context/AppContext";
import { apiPost } from "../api/client";

interface Props {
  path: LearningPath;
}

const STATUS_CONFIG: Record<string, { icon: typeof Circle; color: string; label: string }> = {
  locked: { icon: Lock, color: "rgba(255,255,255,0.3)", label: "未解锁" },
  available: { icon: Circle, color: "#60a5fa", label: "可学习" },
  learning: { icon: PlayCircle, color: "#facc15", label: "学习中" },
  completed: { icon: CheckCircle2, color: "#4ade80", label: "已完成" },
  skipped: { icon: SkipForward, color: "rgba(255,255,255,0.4)", label: "已跳过" },
};

export function LearningPathPanel({ path }: Props) {
  const { state, dispatch } = useAppContext();

  const markComplete = async (nodeId: string) => {
    // Optimistic update
    const updatedNodes = path.nodes.map((n, i, arr) => {
      if (n.node_id === nodeId) return { ...n, status: "completed" as const };
      if (i > 0 && arr[i - 1].node_id === nodeId && n.status === "locked") {
        return { ...n, status: "available" as const };
      }
      return n;
    });
    dispatch({ type: "SET_PATH", payload: { ...path, nodes: updatedNodes } });
    // Sync with backend
    try {
      if (state.user?.id) {
        await apiPost("/learning/path/node/complete", { user_id: state.user.id, node_id: nodeId });
      }
    } catch {
      // Rollback on failure
      dispatch({ type: "SET_PATH", payload: path });
    }
  };

  return (
    <section className="panel">
      <div className="panel-title">
        <Route size={20} />
        <h2>学习路径</h2>
      </div>
      <div className="path-list">
        {path.nodes.map((node) => {
          const cfg = STATUS_CONFIG[node.status] ?? STATUS_CONFIG.available;
          const StatusIcon = cfg.icon;
          const canComplete = node.status === "available" || node.status === "learning";
          return (
            <div className="path-node" key={node.node_id} style={{ borderLeftColor: cfg.color }}>
              <div className="node-order">{node.order}</div>
              <div>
                <strong>{node.knowledge_point}</strong>
                <p>{node.reason}</p>
                <span className="path-node-status">
                  <StatusIcon size={14} style={{ color: cfg.color }} />
                  {cfg.label} · {node.estimated_minutes} 分钟
                </span>
                {canComplete && (
                  <button
                    className="path-node-complete-btn"
                    onClick={() => markComplete(node.node_id)}
                    type="button"
                  >
                    <CheckCircle2 size={14} />
                    标记完成
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
