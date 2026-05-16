import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";
import { Spinner } from "../components/common/Spinner";

interface GraphNode {
  id: string;
  name: string;
  description?: string;
  depends_on?: string[];
  prerequisites?: string[];
  next_nodes?: string[];
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

export function LearningMapPage() {
  const { state, dispatch } = useAppContext();
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeDetail, setNodeDetail] = useState<GraphNode | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [completedNodes, setCompletedNodes] = useState<Set<string>>(() => {
    const known = state.profile?.knowledge_profile?.known_topics;
    return known ? new Set(known) : new Set();
  });

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

  useEffect(() => {
    setLoading(true);
    apiGet<GraphData>("/knowledge/graph")
      .then(setGraph)
      .catch(() => setGraph(null))
      .finally(() => setLoading(false));
  }, []);

  const navigate = useNavigate();

  const handleStartLearning = useCallback((node: GraphNode) => {
    dispatch({ type: "SET_SELECTED_CONVERSATION", payload: null });
    dispatch({ type: "SET_ACTIVE_MESSAGES", payload: [] });
    navigate(`/chat?topic=${encodeURIComponent(node.name)}`);
  }, [navigate, dispatch]);

  if (loading) return <div className="page-center"><Spinner /></div>;
  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="page-center">
        <div className="map-empty">
          <h2>暂无知识图谱</h2>
          <p>请先在图谱管理中构建知识图谱，或联系管理员发布图谱。</p>
          <button
            type="button"
            className="map-btn-start"
            onClick={() => navigate("/graphs")}
            style={{ marginTop: 16 }}
          >
            前往图谱管理
          </button>
        </div>
      </div>
    );
  }

  const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]));
  const inDegree = new Map<string, number>();
  graph.nodes.forEach((n) => inDegree.set(n.id, 0));
  graph.edges.forEach((e) => inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1));

  const levels: GraphNode[][] = [];
  const assigned = new Set<string>();
  let currentLevel = graph.nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0);
  while (currentLevel.length > 0) {
    levels.push(currentLevel);
    currentLevel.forEach((n) => assigned.add(n.id));
    const nextLevel: GraphNode[] = [];
    currentLevel.forEach((n) => {
      (n.next_nodes ?? []).forEach((nid) => {
        if (!assigned.has(nid)) {
          const node = nodeMap.get(nid);
          if (node) nextLevel.push(node);
        }
      });
    });
    currentLevel = nextLevel;
  }

  const unassigned = graph.nodes.filter((n) => !assigned.has(n.id));
  if (unassigned.length > 0) levels.push(unassigned);

  const completedCount = completedNodes.size;
  const totalCount = graph.nodes.length;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <div className="learning-map-page">
      <div className="map-header">
        <h1>🗺️ {graph.course || "学习地图"}</h1>
        <div className="map-progress">
          <div className="map-progress-bar">
            <div className="map-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <span>{completedCount}/{totalCount} 已完成</span>
        </div>
      </div>

      <div className="map-levels">
        {levels.map((level, li) => (
          <div className="map-level" key={li}>
            <div className="map-level-label">阶段 {li + 1}</div>
            <div className="map-level-nodes">
              {level.map((node) => {
                const isCompleted = completedNodes.has(node.id);
                const isSelected = selectedNode?.id === node.id;
                const prereqsMet = (node.depends_on ?? []).every((pid) => completedNodes.has(pid));
                return (
                  <button
                    key={node.id}
                    type="button"
                    className={`map-node ${isCompleted ? "completed" : prereqsMet ? "available" : "locked"} ${isSelected ? "selected" : ""}`}
                    onClick={() => handleSelectNode(node)}
                  >
                    <span className="map-node-name">{node.name}</span>
                    {isCompleted && <span className="map-node-check">✓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {selectedNode && (
        <div className="map-detail">
          <h3>{selectedNode.name}</h3>
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
              onClick={() => {
                setCompletedNodes((prev) => new Set([...prev, selectedNode.id]));
                if (state.user) {
                  apiPost("/learning/path/node/complete", {
                    user_id: state.user.id,
                    node_id: selectedNode.id,
                  }).catch(() => {});
                }
                setSelectedNode(null);
                setNodeDetail(null);
              }}
            >
              标记完成
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
