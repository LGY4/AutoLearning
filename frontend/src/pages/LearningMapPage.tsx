import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";
import { Spinner } from "../components/common/Spinner";
import { LearningMapDiagramView } from "../components/LearningMapDiagramView";
import { computeLevels } from "../utils/graphToDrawioXml";
import { ChevronRight, ChevronLeft, Route, RefreshCw, Lock, Circle, PlayCircle, CheckCircle2, SkipForward } from "lucide-react";

interface GraphNode {
  id: string;
  name: string;
  description?: string;
  depends_on?: string[];
  prerequisites?: string[];
  next_nodes?: string[];
  path_status?: {
    node_id: string;
    order: number;
    status: string;
    estimated_minutes: number;
  } | null;
}

interface GraphEdge {
  from: string;
  to: string;
}

interface GraphData {
  course: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  learning_paths?: Record<string, string[]>;
}

interface PathInfo {
  path_id: string;
  title: string;
  goal: string;
  status: string;
  completed_count: number;
  total_count: number;
}

interface PathHistoryItem {
  path_id: string;
  title: string;
  goal: string;
  status: string;
  node_count: number;
  completed_count: number;
}

const PATH_STATUS_CONFIG: Record<string, { color: string; icon: typeof Lock; label: string }> = {
  locked: { color: "#6b7280", icon: Lock, label: "未解锁" },
  available: { color: "#3b82f6", icon: Circle, label: "可学习" },
  learning: { color: "#f59e0b", icon: PlayCircle, label: "学习中" },
  completed: { color: "#22c55e", icon: CheckCircle2, label: "已完成" },
  skipped: { color: "#9ca3af", icon: SkipForward, label: "已跳过" },
};

export function LearningMapPage() {
  const { state, dispatch } = useAppContext();
  const navigate = useNavigate();

  const [graph, setGraph] = useState<GraphData | null>(null);
  const [pathInfo, setPathInfo] = useState<PathInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeDetail, setNodeDetail] = useState<GraphNode | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [completedNodes, setCompletedNodes] = useState<Set<string>>(() => {
    const known = state.profile?.knowledge_profile?.known_topics;
    return known ? new Set(known) : new Set();
  });

  // Path panel state
  const [pathPanelOpen, setPathPanelOpen] = useState(false);
  const [pathHistory, setPathHistory] = useState<PathHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Keep completedNodes in sync when profile updates
  useEffect(() => {
    const known = state.profile?.knowledge_profile?.known_topics;
    if (known) setCompletedNodes(new Set(known));
  }, [state.profile?.knowledge_profile?.known_topics]);

  // Load graph with path status
  const loadGraph = useCallback(() => {
    setLoading(true);
    apiGet<{ graph: GraphData; path: PathInfo | null }>("/knowledge/graph/with-path")
      .then((data) => {
        setGraph(data.graph);
        setPathInfo(data.path);
      })
      .catch(() => {
        // Fallback to basic graph
        apiGet<GraphData>("/knowledge/graph")
          .then(setGraph)
          .catch(() => setGraph(null));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadGraph(); }, [loadGraph, state.pathVersion]);

  // Load path history when panel opens
  const loadHistory = useCallback(() => {
    setHistoryLoading(true);
    apiGet<{ items: PathHistoryItem[] }>("/learning-paths/history?page=1&page_size=20")
      .then((data) => setPathHistory(data.items ?? []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false));
  }, []);

  useEffect(() => {
    if (pathPanelOpen) loadHistory();
  }, [pathPanelOpen, loadHistory]);

  const handleSelectNode = useCallback((node: GraphNode) => {
    if (selectedNode?.id === node.id) {
      setSelectedNode(null);
      setNodeDetail(null);
      return;
    }
    setSelectedNode(node);
    setNodeDetail(null);
    setDetailLoading(true);
    apiGet<GraphNode>(`/knowledge/graph/node/${node.id}`)
      .then((detail) => setNodeDetail({ ...node, ...detail }))
      .catch(() => setNodeDetail(node))
      .finally(() => setDetailLoading(false));
  }, [selectedNode]);

  const handleStartLearning = useCallback(async (node: GraphNode) => {
    // Set node to LEARNING status before navigating
    dispatch({ type: "SET_SELECTED_CONVERSATION", payload: null });
    dispatch({ type: "SET_ACTIVE_MESSAGES", payload: [] });
    try {
      await apiPost("/learning-paths/start-node", { knowledge_point: node.name });
    } catch {
      // Non-blocking: user can still proceed to chat even if status update fails
    }
    navigate(`/chat?topic=${encodeURIComponent(node.name)}`);
  }, [navigate, dispatch]);

  const handleMarkComplete = useCallback((node: GraphNode) => {
    // Optimistic update
    setCompletedNodes((prev) => new Set([...prev, node.id]));
    setSelectedNode(null);
    setNodeDetail(null);

    // Use unified completion endpoint
    apiPost("/learning/complete-knowledge-point", { knowledge_point: node.name })
      .then(() => {
        // Refresh profile to sync known_topics
        apiGet<import("../types/baseline").StudentProfile>("/profiles/me")
          .then((p) => dispatch({ type: "SET_PROFILE", payload: p }))
          .catch(() => {});
        // Refresh graph to update path status
        loadGraph();
      })
      .catch(() => {});
  }, [dispatch, loadGraph]);

  const handleGeneratePath = useCallback(() => {
    const goal = state.profile?.learning_goal?.current_goal;
    const subject = state.profile?.basic_info?.major || "数据结构";
    if (!goal) {
      dispatch({ type: "SET_ERROR", payload: "请先在课程管理中设置学习目标" });
      return;
    }
    setGenerating(true);
    apiPost("/learning-paths/generate", { target_goal: goal, subject })
      .then(() => {
        loadGraph();
        loadHistory();
        dispatch({ type: "SET_NOTICE", payload: "学习路径已生成" });
      })
      .catch(() => {
        dispatch({ type: "SET_ERROR", payload: "路径生成失败" });
      })
      .finally(() => setGenerating(false));
  }, [state.profile, dispatch, loadGraph, loadHistory]);

  if (loading) return <div className="page-center"><Spinner /></div>;
  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="page-center">
        <div className="map-empty">
          <h2>暂无学习地图</h2>
          <p>知识图谱尚未构建。你可以：</p>
          <ul style={{ textAlign: "left", margin: "12px 0", lineHeight: 2 }}>
            <li>在聊天中输入学习目标，AI 会自动生成学习路径</li>
            <li>在课程管理中设置学习目标后生成路径</li>
            <li>联系管理员构建完整知识图谱</li>
          </ul>
          <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
            <button type="button" className="map-btn-start" onClick={() => navigate("/chat")}>
              去聊天生成路径
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Build node map and compute levels
  const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]));
  const levels = computeLevels(graph.nodes, graph.edges);

  const completedCount = completedNodes.size;
  const totalCount = graph.nodes.length;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  // Determine the next recommended node (first available in path, or first available by prereqs)
  const nextRecommended = pathInfo
    ? graph.nodes.find((n) => n.path_status?.status === "available")
    : graph.nodes.find((n) => {
        if (completedNodes.has(n.id)) return false;
        return (n.depends_on ?? []).every((pid) => completedNodes.has(pid));
      });

  // Node status: prefer path_status if available, fall back to binary
  const getNodeStatus = (node: GraphNode): string => {
    if (node.path_status) return node.path_status.status;
    if (completedNodes.has(node.id)) return "completed";
    const prereqsMet = (node.depends_on ?? []).every((pid) => completedNodes.has(pid));
    return prereqsMet ? "available" : "locked";
  };

  return (
    <div className="learning-map-page">
      <div className="map-header">
        <h1>{graph.course || "学习地图"}</h1>
        <div className="map-header-right">
          <div className="map-progress">
            <div className="map-progress-bar">
              <div className="map-progress-fill" style={{ width: `${progressPct}%` }} />
            </div>
            <span>{completedCount}/{totalCount} 已完成</span>
          </div>
          <button
            type="button"
            className="map-path-toggle"
            onClick={() => setPathPanelOpen((v) => !v)}
            title="学习路径管理"
          >
            <Route size={16} />
            <span>路径</span>
            {pathPanelOpen ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>
      </div>

      <div className="map-body">
        {/* Main graph area */}
        <div className={`map-graph-area ${pathPanelOpen ? "with-panel" : ""}`}>
          <LearningMapDiagramView
            levels={levels}
            edges={graph.edges}
            getNodeStatus={getNodeStatus}
            onSelectNode={handleSelectNode}
            nodeMap={nodeMap}
          />

          {/* Node detail panel */}
          {selectedNode && (
            <div className="map-detail">
              <h3>{selectedNode.name}</h3>
              {selectedNode.path_status && (
                <div className="map-detail-path-info">
                  <span>路径顺序：第 {selectedNode.path_status.order + 1} 步</span>
                  <span>预估时长：{selectedNode.path_status.estimated_minutes} 分钟</span>
                </div>
              )}
              {detailLoading ? (
                <div className="map-detail-loading">加载详情...</div>
              ) : (
                <>
                  {(nodeDetail ?? selectedNode).description && <p>{(nodeDetail ?? selectedNode).description}</p>}
                  {nodeDetail?.prerequisites && nodeDetail.prerequisites.length > 0 && (
                    <div className="map-detail-deps">
                      <span>前置知识：</span>
                      {nodeDetail.prerequisites.map((pid) => (
                        <span key={pid} className={`map-dep-tag ${completedNodes.has(pid) ? "done" : ""}`}>
                          {nodeMap.get(pid)?.name ?? pid}
                        </span>
                      ))}
                    </div>
                  )}
                  {nodeDetail?.next_nodes && nodeDetail.next_nodes.length > 0 && (
                    <div className="map-detail-deps">
                      <span>后续节点：</span>
                      {nodeDetail.next_nodes.map((nid) => (
                        <span key={nid} className="map-dep-tag">
                          {nodeMap.get(nid)?.name ?? nid}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
              <div className="map-detail-deps">
                <span>前置依赖：</span>
                {(selectedNode.depends_on ?? []).length > 0
                  ? selectedNode.depends_on!.map((pid) => (
                    <span key={pid} className={`map-dep-tag ${completedNodes.has(pid) ? "done" : ""}`}>
                      {nodeMap.get(pid)?.name ?? pid}
                    </span>
                  ))
                  : <span className="map-dep-tag done">无</span>
                }
              </div>
              <div className="map-detail-actions">
                <button
                  type="button"
                  className="map-btn-start"
                  onClick={() => handleStartLearning(selectedNode)}
                >
                  开始学习
                </button>
                <button
                  type="button"
                  className="map-btn-complete"
                  onClick={() => handleMarkComplete(selectedNode)}
                >
                  标记完成
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Path management side panel */}
        {pathPanelOpen && (
          <div className="map-path-panel">
            <div className="map-path-panel-header">
              <h3>学习路径</h3>
            </div>

            {pathInfo ? (
              <div className="map-path-current">
                <div className="map-path-title">{pathInfo.title}</div>
                <div className="map-path-goal">{pathInfo.goal}</div>
                <div className="map-path-progress">
                  <div className="map-progress-bar">
                    <div
                      className="map-progress-fill"
                      style={{ width: `${pathInfo.total_count > 0 ? Math.round((pathInfo.completed_count / pathInfo.total_count) * 100) : 0}%` }}
                    />
                  </div>
                  <span>{pathInfo.completed_count}/{pathInfo.total_count} 已完成</span>
                </div>
                <button
                  type="button"
                  className="map-path-regenerate"
                  onClick={handleGeneratePath}
                  disabled={generating}
                >
                  <RefreshCw size={14} className={generating ? "spinning" : ""} />
                  <span>{generating ? "生成中..." : "重新生成"}</span>
                </button>
              </div>
            ) : (
              <div className="map-path-empty">
                <p>暂无学习路径</p>
                <button
                  type="button"
                  className="map-btn-start"
                  onClick={handleGeneratePath}
                  disabled={generating}
                >
                  {generating ? "生成中..." : "生成学习路径"}
                </button>
              </div>
            )}

            <div className="map-path-legend">
              <span className="map-path-legend-title">图例</span>
              {Object.entries(PATH_STATUS_CONFIG).map(([key, cfg]) => {
                const Icon = cfg.icon;
                return (
                  <div key={key} className="map-path-legend-item">
                    <Icon size={14} style={{ color: cfg.color }} />
                    <span>{cfg.label}</span>
                  </div>
                );
              })}
            </div>

            <div className="map-path-history">
              <span className="map-path-history-title">历史路径</span>
              {historyLoading ? (
                <div className="map-path-history-loading">加载中...</div>
              ) : pathHistory.length === 0 ? (
                <div className="map-path-history-empty">暂无历史</div>
              ) : (
                pathHistory.map((item) => (
                  <div key={item.path_id} className="map-path-history-item">
                    <span className="map-path-history-name">{item.title}</span>
                    <span className="map-path-history-meta">
                      {item.completed_count}/{item.node_count}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
