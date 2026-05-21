import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost, apiDelete, apiPostForm } from "../api/client";
import { GraphViz } from "../components/graph/GraphViz";

interface GraphSummary {
  graph_id: string;
  course_id: string;
  course_name: string;
  version: number;
  review_status: string;
  node_count: number;
  edge_count: number;
  confidence: number | null;
  generated_by: string;
  created_at: string;
}

interface GraphNode {
  id: string;
  name: string;
  level: number;
  depends_on: string[];
  description: string;
  chunk_ids: string[];
}

interface GraphDetail {
  metadata: {
    course_id: string;
    course_name: string;
    version: number;
    review_status: string;
    confidence: number;
    node_count: number;
    edge_count: number;
  };
  nodes: GraphNode[];
  edges: { source: string; target: string; type: string }[];
  learning_paths: Record<string, string[]>;
}

interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  stats: Record<string, unknown>;
}

interface DiffResult {
  summary: {
    total_changes: number;
    nodes_added: number;
    nodes_removed: number;
    nodes_changed: number;
    edges_added: number;
    edges_removed: number;
  };
  nodes: {
    added: { id: string; name: string }[];
    removed: { id: string; name: string }[];
    changed: { id: string; changes: Record<string, { old: unknown; new: unknown }> }[];
  };
  edges: {
    added: { source: string; target: string }[];
    removed: { source: string; target: string }[];
  };
}

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  pending: "待审核",
  published: "已发布",
  rejected: "已拒绝",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "rgba(255,255,255,0.4)",
  pending: "#facc15",
  published: "#4ade80",
  rejected: "#f87171",
};

export function GraphManagerPage() {
  const navigate = useNavigate();
  const [graphs, setGraphs] = useState<GraphSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GraphDetail | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Build form
  const [buildCourse, setBuildCourse] = useState("");
  const [buildOutline, setBuildOutline] = useState("");
  const [buildMaxNodes, setBuildMaxNodes] = useState(20);
  const [buildFiles, setBuildFiles] = useState<File[]>([]);

  // Knowledge status
  const [knowledgeStatus, setKnowledgeStatus] = useState<Record<string, unknown> | null>(null);
  const [rebuilding, setRebuilding] = useState(false);

  // Diff form
  const [diffOldId, setDiffOldId] = useState("");
  const [diffNewId, setDiffNewId] = useState("");

  const loadGraphs = useCallback(async () => {
    try {
      const data = await apiGet<GraphSummary[]>("/knowledge/graphs");
      setGraphs(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { loadGraphs(); }, [loadGraphs]);

  const loadKnowledgeStatus = useCallback(async () => {
    try {
      const status = await apiGet<Record<string, unknown>>("/knowledge/status");
      setKnowledgeStatus(status);
    } catch {
      setKnowledgeStatus(null);
    }
  }, []);

  const handleRebuild = useCallback(async () => {
    setRebuilding(true);
    setError(null);
    try {
      await apiPost("/knowledge/rebuild", {});
      await loadKnowledgeStatus();
      await loadGraphs();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "重建失败");
    } finally {
      setRebuilding(false);
    }
  }, [loadGraphs]);

  const loadDetail = async (graphId: string) => {
    setSelectedId(graphId);
    setValidation(null);
    setDiff(null);
    try {
      const data = await apiGet<GraphDetail>(`/knowledge/graphs/${graphId}`);
      setDetail(data);
    } catch {
      setDetail(null);
    }
  };

  const handleBuild = async () => {
    if (!buildCourse.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<{ graph_id: string; validation: ValidationResult }>("/knowledge/graphs/build", {
        course_name: buildCourse,
        outline: buildOutline || undefined,
        max_nodes: buildMaxNodes,
      });
      setValidation(res.validation);
      await loadGraphs();
      await loadDetail(res.graph_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const handleUploadBuild = async () => {
    if (!buildCourse.trim() || buildFiles.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("course_name", buildCourse);
      formData.append("max_nodes", String(buildMaxNodes));
      for (const f of buildFiles) formData.append("files", f);

      const res = await apiPostForm<{ graph_id: string; validation: { valid: boolean; errors: string[]; warnings: string[]; stats: Record<string, unknown> } }>("/knowledge/graphs/upload-build", formData);
      setValidation(res.validation);
      await loadGraphs();
      await loadDetail(res.graph_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "上传生成失败");
    } finally {
      setLoading(false);
    }
  };

  const handleValidate = async () => {
    if (!detail) return;
    setLoading(true);
    try {
      const res = await apiPost<ValidationResult>("/knowledge/graphs/validate", detail);
      setValidation(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "校验失败");
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async (graphId: string, courseId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<{ status: string; diff?: DiffResult }>("/knowledge/graphs/publish", {
        graph_id: graphId,
        course_id: courseId,
      });
      if (res.diff) setDiff(res.diff);
      await loadGraphs();
      await loadDetail(graphId);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setLoading(false);
    }
  };

  const handleDiff = async () => {
    if (!diffOldId || !diffNewId) return;
    setLoading(true);
    try {
      const res = await apiPost<DiffResult>("/knowledge/graphs/diff", {
        old_graph_id: diffOldId,
        new_graph_id: diffNewId,
      });
      setDiff(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "对比失败");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (graphId: string) => {
    try {
      await apiDelete(`/knowledge/graphs/${graphId}`);
      await loadGraphs();
      if (selectedId === graphId) { setSelectedId(null); setDetail(null); }
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除图谱失败");
    }
  };

  return (
    <div className="graph-mgr">
      <h2>知识图谱管理</h2>

      {error && <div className="page-error">{error}</div>}

      <div className="graph-mgr-grid">
        {/* ── Left Column ─────────────────────────────────────────── */}
        <div className="graph-mgr-left">

          {/* Knowledge Status */}
          <div className="graph-mgr-section">
            <h3>知识库状态</h3>
            <div className="graph-mgr-actions">
              <button className="graph-mgr-btn small" onClick={loadKnowledgeStatus}>刷新状态</button>
              <button className="graph-mgr-btn small secondary" onClick={handleRebuild} disabled={rebuilding}>
                {rebuilding ? "重建中..." : "重建知识库"}
              </button>
            </div>
            {knowledgeStatus && (
              <div className="graph-mgr-card-meta" style={{ marginTop: 8 }}>
                <span>后端 {(knowledgeStatus as Record<string,unknown>).configured_backend as string || "—"}</span>
                <span style={{ marginLeft: 12 }}>来源 {(knowledgeStatus as Record<string,unknown>).source_chunks as number ?? "—"} 条</span>
              </div>
            )}
          </div>

          {/* Build Panel */}
          <div className="graph-mgr-section">
            <h3>生成图谱</h3>
            <div className="graph-mgr-form">
              <div className="graph-mgr-field">
                <label>课程名称</label>
                <input value={buildCourse} onChange={(e) => setBuildCourse(e.target.value)} placeholder="如：操作系统" />
              </div>
              <div className="graph-mgr-field">
                <label>课程大纲（可选）</label>
                <textarea value={buildOutline} onChange={(e) => setBuildOutline(e.target.value)} rows={3} placeholder="粘贴课程大纲..." />
              </div>
              <div className="graph-mgr-field">
                <label>最大节点数</label>
                <input type="number" value={buildMaxNodes} onChange={(e) => setBuildMaxNodes(Number(e.target.value))} min={5} max={50} />
              </div>
              <div className="graph-mgr-field">
                <label>上传资料（PDF/Markdown/TXT）</label>
                <input type="file" multiple accept=".pdf,.md,.markdown,.txt,.json" onChange={(e) => setBuildFiles(Array.from(e.target.files || []))} />
                {buildFiles.length > 0 && <span className="graph-mgr-file-info">{buildFiles.length} 个文件已选择</span>}
              </div>
              <div className="graph-mgr-actions">
                <button className="graph-mgr-btn" onClick={handleBuild} disabled={loading || !buildCourse.trim()}>
                  {loading ? "生成中..." : "LLM 生成图谱"}
                </button>
                <button className="graph-mgr-btn secondary" onClick={handleUploadBuild} disabled={loading || !buildCourse.trim() || buildFiles.length === 0}>
                  {loading ? "解析中..." : "从文件生成"}
                </button>
              </div>
            </div>
          </div>

          {/* Graph List */}
          <div className="graph-mgr-section">
            <h3>图谱列表 ({graphs.length})</h3>
            {graphs.length === 0 ? (
              <p className="graph-mgr-empty">暂无图谱，请先生成。</p>
            ) : (
              <div className="graph-mgr-list">
                {graphs.map((g) => (
                  <div key={g.graph_id} className={`graph-mgr-card ${selectedId === g.graph_id ? "selected" : ""}`} onClick={() => loadDetail(g.graph_id)}>
                    <div className="graph-mgr-card-top">
                      <strong>{g.course_name}</strong>
                      <span className="graph-mgr-status" style={{ color: STATUS_COLORS[g.review_status] }}>
                        {STATUS_LABELS[g.review_status] || g.review_status}
                      </span>
                    </div>
                    <div className="graph-mgr-card-meta">
                      {g.node_count} 节点 · {g.edge_count} 边 · v{g.version}
                      {g.confidence != null && ` · 置信度 ${Math.round(g.confidence * 100)}%`}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Right Column ────────────────────────────────────────── */}
        <div className="graph-mgr-right">
          {detail ? (
            <>
              <div className="graph-mgr-section">
                <div className="graph-mgr-detail-header">
                  <h3>{detail.metadata.course_name} — v{detail.metadata.version}</h3>
                  <div className="graph-mgr-detail-actions">
                    <button className="graph-mgr-btn small" onClick={handleValidate} disabled={loading}>校验</button>
                    {detail.metadata.review_status !== "published" && (
                      <button className="graph-mgr-btn small primary" onClick={() => handlePublish(selectedId!, detail.metadata.course_id)} disabled={loading}>
                        发布
                      </button>
                    )}
                  </div>
                </div>

                {validation && (
                  <div className={`graph-mgr-validation ${validation.valid ? "valid" : "invalid"}`}>
                    <strong>{validation.valid ? "校验通过" : "校验失败"}</strong>
                    {validation.errors.map((e, i) => <div key={i} className="graph-mgr-v-error">{e}</div>)}
                    {validation.warnings.map((w, i) => <div key={i} className="graph-mgr-v-warn">{w}</div>)}
                    <div className="graph-mgr-v-stats">
                      节点 {(validation.stats as Record<string, unknown>).node_count as number || 0} ·
                      边 {(validation.stats as Record<string, unknown>).edge_count as number || 0} ·
                      孤立 {(validation.stats as Record<string, unknown>).orphan_count as number || 0}
                    </div>
                  </div>
                )}

                <GraphViz
                  className="graph-viz-container"
                  nodes={detail.nodes}
                  edges={detail.edges}
                />

                <div className="graph-mgr-nodes">
                  <h4>知识点 ({detail.nodes.length}) — 点击跳转学习</h4>
                  <div className="graph-mgr-node-list">
                    {detail.nodes.map((n) => (
                      <div key={n.id} className="graph-mgr-node" style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/chat?topic=${encodeURIComponent(n.name)}`)}
                        title={`点击开始学习: ${n.name}`}>
                        <div className="graph-mgr-node-head">
                          <span className="graph-mgr-node-id">{n.id}</span>
                          <span className="graph-mgr-node-level">L{n.level}</span>
                        </div>
                        <div className="graph-mgr-node-name">{n.name}</div>
                        {n.depends_on.length > 0 && (
                          <div className="graph-mgr-node-deps">前置: {n.depends_on.join(", ")}</div>
                        )}
                        {n.description && <div className="graph-mgr-node-desc">{n.description}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="graph-mgr-section" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 200 }}>
              <p className="graph-mgr-empty">选择左侧图谱查看详情</p>
            </div>
          )}

          {/* Diff Panel */}
          <div className="graph-mgr-section">
            <h3>图谱对比</h3>
            <div className="graph-mgr-diff-form">
              <select value={diffOldId} onChange={(e) => setDiffOldId(e.target.value)}>
                <option value="">选择旧版本</option>
                {graphs.map((g) => <option key={g.graph_id} value={g.graph_id}>{g.course_name} v{g.version} ({STATUS_LABELS[g.review_status]})</option>)}
              </select>
              <span>→</span>
              <select value={diffNewId} onChange={(e) => setDiffNewId(e.target.value)}>
                <option value="">选择新版本</option>
                {graphs.map((g) => <option key={g.graph_id} value={g.graph_id}>{g.course_name} v{g.version} ({STATUS_LABELS[g.review_status]})</option>)}
              </select>
              <button className="graph-mgr-btn small" onClick={handleDiff} disabled={loading || !diffOldId || !diffNewId}>对比</button>
            </div>

            {diff && (
              <div className="graph-mgr-diff-result">
                <div className="graph-mgr-diff-summary">
                  变更 {diff.summary.total_changes} 项：
                  新增 {diff.summary.nodes_added} 节点 ·
                  删除 {diff.summary.nodes_removed} 节点 ·
                  修改 {diff.summary.nodes_changed} 节点 ·
                  新增 {diff.summary.edges_added} 边 ·
                  删除 {diff.summary.edges_removed} 边
                </div>
                {diff.nodes.added.length > 0 && (
                  <div className="graph-mgr-diff-group">
                    <h4>新增节点</h4>
                    {diff.nodes.added.map((n) => <div key={n.id} className="graph-mgr-diff-add">+ {n.id} ({n.name})</div>)}
                  </div>
                )}
                {diff.nodes.removed.length > 0 && (
                  <div className="graph-mgr-diff-group">
                    <h4>删除节点</h4>
                    {diff.nodes.removed.map((n) => <div key={n.id} className="graph-mgr-diff-remove">- {n.id} ({n.name})</div>)}
                  </div>
                )}
                {diff.nodes.changed.length > 0 && (
                  <div className="graph-mgr-diff-group">
                    <h4>修改节点</h4>
                    {diff.nodes.changed.map((n) => (
                      <div key={n.id} className="graph-mgr-diff-change">
                        <strong>{n.id}</strong>
                        {Object.entries(n.changes).map(([field, vals]) => (
                          <div key={field} className="graph-mgr-diff-field">
                            {field}: {JSON.stringify(vals.old)} → {JSON.stringify(vals.new)}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
