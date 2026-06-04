import { useCallback, useEffect, useRef, useState } from "react";
import { Film, Image, Wand2, Play, Loader2, Download, RotateCcw, Trash2, Clock, ChevronLeft, ChevronRight } from "lucide-react";
import { useAppContext } from "../context/AppContext";
import { apiGet, apiPost, apiDelete, getFriendlyError } from "../api/client";

type GenTab = "animation" | "image" | "analyze";
type PageTab = "generate" | "history";

interface ProgressEvent {
  stage: string;
  status: string;
  hint: string;
}

interface MediaTaskStatus {
  task_id: string;
  media_type: string;
  status: string;
  progress: ProgressEvent[];
  result: Record<string, unknown> | null;
  error: string | null;
  topic?: string;
  subject?: string;
  params?: Record<string, unknown>;
}

interface MediaHistoryItem {
  task_id: string;
  media_type: string;
  status: string;
  topic: string;
  subject: string;
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  created_at: string | null;
}

const STAGE_LABELS: Record<string, string> = {
  script: "分镜脚本",
  tts: "语音合成",
  image: "配图生成",
  compose: "画面合成",
  segment: "视频片段",
  concat: "最终拼接",
};

const TYPE_LABELS: Record<string, string> = {
  animation: "动画",
  video: "视频",
  image: "图片",
  analysis: "分析",
};

export function MediaStudioPage() {
  const { state } = useAppContext();
  const { user } = state;

  const [pageTab, setPageTab] = useState<PageTab>("generate");
  const [genTab, setGenTab] = useState<GenTab>("animation");

  // Generate state
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);

  // Animation form
  const [animKP, setAnimKP] = useState("");
  const [animSubject, setAnimSubject] = useState("数据结构");
  const [animDifficulty, setAnimDifficulty] = useState("beginner");
  const [animEngine, setAnimEngine] = useState("pipeline");

  // Image form
  const [imgPrompt, setImgPrompt] = useState("");
  const [imgStyle, setImgStyle] = useState("educational");
  const [imgSize, setImgSize] = useState("1024x1024");

  // Analyze form
  const [analyzePrompt, setAnalyzePrompt] = useState("");
  const [analyzeImages, setAnalyzeImages] = useState<string[]>([]);

  // History state
  const [historyItems, setHistoryItems] = useState<MediaHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Detail overlay
  const [selectedTask, setSelectedTask] = useState<MediaTaskStatus | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  // ── History ──

  const loadHistory = useCallback(async (page = 1) => {
    if (!user) return;
    setHistoryLoading(true);
    try {
      const data = await apiGet<{ items: MediaHistoryItem[]; total: number; page: number }>(
        `/system/media/history?page=${page}&page_size=15`
      );
      setHistoryItems(data.items);
      setHistoryTotal(data.total);
      setHistoryPage(data.page);
    } catch { /* silent */ }
    finally { setHistoryLoading(false); }
  }, [user]);

  useEffect(() => {
    if (pageTab === "history") loadHistory();
  }, [pageTab, loadHistory]);

  const handleSelectTask = async (taskId: string) => {
    setDetailLoading(true);
    try {
      const data = await apiGet<MediaTaskStatus>(`/system/media/detail/${taskId}`);
      setSelectedTask(data);
    } catch { /* silent */ }
    finally { setDetailLoading(false); }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await apiDelete(`/system/media/${taskId}`);
      setHistoryItems((prev) => prev.filter((t) => t.task_id !== taskId));
      setHistoryTotal((prev) => prev - 1);
      if (selectedTask?.task_id === taskId) setSelectedTask(null);
    } catch { /* silent */ }
  };

  // ── Generate ──

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    const readers: Promise<string>[] = [];
    for (const f of Array.from(files)) {
      readers.push(new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(f);
      }));
    }
    Promise.all(readers).then(setAnalyzeImages);
  };

  async function handleGenerate() {
    setError(null);
    setResult(null);
    setProgress([]);

    try {
      if (genTab === "animation") {
        if (!animKP.trim()) { setError("请输入知识点"); return; }
        // Async with polling
        setGenerating(true);
        const { task_id } = await apiPost<{ task_id: string }>("/system/generate-animation", {
          knowledge_point: animKP, subject: animSubject, difficulty: animDifficulty, engine: animEngine,
        });
        startPolling(task_id);
      } else if (genTab === "image") {
        if (!imgPrompt.trim()) { setError("请输入描述"); return; }
        // Async with polling
        setGenerating(true);
        const { task_id } = await apiPost<{ task_id: string }>("/system/generate-image", { prompt: imgPrompt, style: imgStyle, size: imgSize });
        startPolling(task_id);
      } else {
        if (!analyzePrompt.trim()) { setError("请输入分析提示"); return; }
        if (analyzeImages.length === 0) { setError("请上传图片"); return; }
        setLoading(true);
        const res = await apiPost<Record<string, unknown>>("/system/analyze-image", { prompt: analyzePrompt, images: analyzeImages });
        setResult(res);
      }
    } catch (e) {
      setError(e instanceof Error ? getFriendlyError(e.message) : "生成失败");
    } finally {
      if (genTab === "analyze") setLoading(false);
    }
  }

  function startPolling(taskId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    const poll = setInterval(async () => {
      pollRef.current = poll;
      try {
        const status = await apiGet<MediaTaskStatus>(`/system/media/status/${taskId}`);
        if (status.progress?.length) setProgress(status.progress);
        if (status.status === "done" && status.result) {
          setResult(status.result);
          clearInterval(poll);
          setGenerating(false);
        } else if (status.status === "failed") {
          setError(status.error || "生成失败");
          clearInterval(poll);
          setGenerating(false);
        }
      } catch {
        clearInterval(poll);
        setGenerating(false);
        setError("任务查询失败，请在历史记录中查看");
      }
    }, 2000);

    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      clearInterval(poll);
      setGenerating(false);
      setError("生成超时，请在历史记录中查看结果");
    }, 600000);
  }

  const handleReset = () => {
    setResult(null);
    setProgress([]);
    setError(null);
  };

  const statusBadge = (status: string) => {
    const map: Record<string, { label: string; cls: string }> = {
      pending: { label: "排队中", cls: "status-pending" },
      running: { label: "生成中", cls: "status-running" },
      done: { label: "已完成", cls: "status-done" },
      failed: { label: "失败", cls: "status-failed" },
    };
    const s = map[status] || { label: status, cls: "" };
    return <span className={`video-status-badge ${s.cls}`}>{s.label}</span>;
  };

  const renderResult = (res: Record<string, unknown>) => (
    <div className="info-card" style={{ marginTop: 16 }}>
      <h3>生成结果</h3>
      {typeof res.video_url === "string" && (
        <video controls src={res.video_url} style={{ maxWidth: "100%", borderRadius: 8 }} />
      )}
      {typeof res.image_base64 === "string" && (
        <img src={`data:image/png;base64,${res.image_base64}`} alt="生成图片" style={{ maxWidth: "100%", borderRadius: 8 }} />
      )}
      {typeof res.analysis === "string" && (
        <p style={{ whiteSpace: "pre-wrap" }}>{res.analysis}</p>
      )}
      {typeof res.title === "string" && <p><strong>标题：</strong>{res.title}</p>}
      {typeof res.duration_seconds === "number" && <p><strong>时长：</strong>{Math.round(res.duration_seconds as number)}秒</p>}
      {Array.isArray(res.scenes) && (res.scenes as unknown[]).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <strong>分镜脚本：</strong>
          {(res.scenes as Record<string, unknown>[]).map((s, i) => (
            <div key={i} style={{ margin: "8px 0", padding: "8px", background: "rgba(255,255,255,0.04)", borderRadius: 6 }}>
              <span>场景 {(s.scene as number) + 1} · {String(s.duration || 0)}秒</span>
              <p style={{ margin: "4px 0 0" }}>{String(s.narration || "")}</p>
            </div>
          ))}
        </div>
      )}
      {typeof res.video_url === "string" && (
        <a href={res.video_url as string} download className="btn-primary" style={{ display: "inline-block", marginTop: 12, textDecoration: "none" }}>
          <Download size={16} /> 下载视频
        </a>
      )}
    </div>
  );

  const genTabs: { key: GenTab; label: string; icon: React.ReactNode }[] = [
    { key: "animation", label: "动画生成", icon: <Film size={16} /> },
    { key: "image", label: "图片生成", icon: <Image size={16} /> },
    { key: "analyze", label: "图片分析", icon: <Wand2 size={16} /> },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1><Wand2 size={24} /> 媒体工坊</h1>
      </div>

      {/* Outer tabs */}
      <div className="video-studio-tabs">
        <button className={`video-tab-btn ${pageTab === "generate" ? "active" : ""}`} onClick={() => setPageTab("generate")}>生成</button>
        <button className={`video-tab-btn ${pageTab === "history" ? "active" : ""}`} onClick={() => setPageTab("history")}>历史记录 {historyTotal > 0 && <span className="video-tab-count">{historyTotal}</span>}</button>
      </div>

      {error && !generating && !loading && <div className="page-error">{error}</div>}

      {/* ── Generate tab ── */}
      {pageTab === "generate" && !result && (
        <>
          <div className="tab-bar">
            {genTabs.map((t) => (
              <button key={t.key} className={`tab-btn ${genTab === t.key ? "active" : ""}`}
                onClick={() => { setGenTab(t.key); setResult(null); setError(null); }}>
                {t.icon} {t.label}
              </button>
            ))}
          </div>

          <div className="form-card">
            {genTab === "animation" && (
              <>
                <h3>动画生成</h3>
                <p className="form-hint">输入知识点，选择渲染引擎，系统自动生成可视化动画。</p>
                <input placeholder="知识点（如：二叉树遍历）" value={animKP} onChange={(e) => setAnimKP(e.target.value)} disabled={generating} />
                <div className="form-row">
                  <input placeholder="学科" value={animSubject} onChange={(e) => setAnimSubject(e.target.value)} disabled={generating} />
                  <select value={animDifficulty} onChange={(e) => setAnimDifficulty(e.target.value)} disabled={generating}>
                    <option value="beginner">入门</option>
                    <option value="intermediate">中级</option>
                    <option value="advanced">高级</option>
                  </select>
                </div>
                <div className="form-row">
                  <select value={animEngine} onChange={(e) => setAnimEngine(e.target.value)} disabled={generating}>
                    <option value="pipeline">标准管线（默认）</option>
                    <option value="remotion">Remotion 动画</option>
                    <option value="manim">Manim 数学动画</option>
                  </select>
                </div>
              </>
            )}

            {genTab === "image" && (
              <>
                <h3>AI 图片生成</h3>
                <p className="form-hint">描述你需要的图片内容和风格。</p>
                <textarea placeholder="图片描述" value={imgPrompt} onChange={(e) => setImgPrompt(e.target.value)} rows={3} disabled={loading} />
                <div className="form-row">
                  <select value={imgStyle} onChange={(e) => setImgStyle(e.target.value)} disabled={loading}>
                    <option value="educational">教学风格</option>
                    <option value="realistic">写实风格</option>
                    <option value="cartoon">卡通风格</option>
                    <option value="minimal">极简风格</option>
                  </select>
                  <select value={imgSize} onChange={(e) => setImgSize(e.target.value)} disabled={loading}>
                    <option value="1024x1024">1024x1024</option>
                    <option value="1792x1024">1792x1024 (横)</option>
                    <option value="1024x1792">1024x1792 (竖)</option>
                  </select>
                </div>
              </>
            )}

            {genTab === "analyze" && (
              <>
                <h3>图片内容分析</h3>
                <p className="form-hint">上传图片并描述你想了解的内容。</p>
                <input type="file" accept="image/*" multiple onChange={handleImageUpload} disabled={loading} />
                {analyzeImages.length > 0 && (
                  <div className="image-preview-list">
                    {analyzeImages.map((img, i) => (
                      <img key={i} src={img} alt={`预览 ${i + 1}`} className="image-preview-thumb" />
                    ))}
                  </div>
                )}
                <textarea placeholder="分析提示" value={analyzePrompt} onChange={(e) => setAnalyzePrompt(e.target.value)} rows={2} disabled={loading} />
              </>
            )}

            {generating ? (
              <div className="video-progress" style={{ marginTop: 12 }}>
                <div className="video-progress-header">
                  <Loader2 size={20} className="video-spinner" />
                  <span>{genTab === "animation" ? "动画生成中..." : genTab === "image" ? "图片生成中..." : "分析中..."}</span>
                </div>
                <div className="video-progress-steps">
                  {progress.map((evt, i) => (
                    <div key={`${evt.stage}-${i}`} className={`video-step ${evt.status}`}>
                      <span className="video-step-label">{STAGE_LABELS[evt.stage] || evt.stage}</span>
                      <span className="video-step-hint">{evt.hint}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <button className="btn-primary" onClick={handleGenerate} disabled={loading} style={{ marginTop: 12 }}>
                <Play size={16} /> {loading ? "生成中..." : "开始生成"}
              </button>
            )}
          </div>
        </>
      )}

      {/* Result view */}
      {pageTab === "generate" && result && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button className="video-action-btn" onClick={handleReset}><RotateCcw size={16} /> 重新生成</button>
          </div>
          {renderResult(result)}
        </div>
      )}

      {/* ── History tab ── */}
      {pageTab === "history" && (
        <div className="video-history" style={{ marginTop: 16 }}>
          {historyLoading ? (
            <div className="video-history-loading"><Loader2 size={24} className="video-spinner" /></div>
          ) : historyItems.length === 0 ? (
            <div className="video-history-empty">暂无生成记录</div>
          ) : (
            <>
              <div className="video-history-list">
                {historyItems.map((item) => (
                  <div key={item.task_id} className="video-history-card"
                    onClick={() => handleSelectTask(item.task_id)} role="button" tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && handleSelectTask(item.task_id)}>
                    <div className="video-history-card-thumb">
                      {item.result?.video_url ? (
                        <video src={item.result.video_url as string} muted preload="metadata" />
                      ) : item.result?.image_base64 ? (
                        <img src={`data:image/png;base64,${item.result.image_base64}`} alt="" />
                      ) : (
                        <div className="video-history-card-placeholder">
                          {item.media_type === "image" ? <Image size={24} /> : <Film size={24} />}
                        </div>
                      )}
                    </div>
                    <div className="video-history-card-info">
                      <div className="video-history-card-title">{item.topic}</div>
                      <div className="video-history-card-meta">
                        {TYPE_LABELS[item.media_type] || item.media_type}
                        {item.subject && ` · ${item.subject}`}
                        {item.created_at && <span className="video-history-card-time"><Clock size={12} /> {new Date(item.created_at).toLocaleDateString()}</span>}
                      </div>
                    </div>
                    <div className="video-history-card-status">{statusBadge(item.status)}</div>
                  </div>
                ))}
              </div>

              {historyTotal > 15 && (
                <div className="video-history-pagination">
                  <button disabled={historyPage <= 1} onClick={() => loadHistory(historyPage - 1)}><ChevronLeft size={16} /></button>
                  <span>{historyPage} / {Math.ceil(historyTotal / 15)}</span>
                  <button disabled={historyPage * 15 >= historyTotal} onClick={() => loadHistory(historyPage + 1)}><ChevronRight size={16} /></button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Detail overlay ── */}
      {selectedTask && (
        <div className="res-lib-detail-overlay" onClick={() => setSelectedTask(null)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Escape" && setSelectedTask(null)}>
          <div className="res-lib-detail video-detail" onClick={(e) => e.stopPropagation()}>
            <div className="res-lib-detail-header">
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {statusBadge(selectedTask.status)}
                <strong>{selectedTask.topic || "详情"}</strong>
              </div>
              <button className="res-lib-detail-close" onClick={() => setSelectedTask(null)} type="button">✕</button>
            </div>
            <div className="res-lib-detail-body">
              {selectedTask.status === "running" && (
                <div className="video-progress">
                  <div className="video-progress-header">
                    <Loader2 size={20} className="video-spinner" />
                    <span>生成中...</span>
                  </div>
                  <div className="video-progress-steps">
                    {selectedTask.progress.map((evt, i) => (
                      <div key={`${evt.stage}-${i}`} className={`video-step ${evt.status}`}>
                        <span className="video-step-label">{STAGE_LABELS[evt.stage] || evt.stage}</span>
                        <span className="video-step-hint">{evt.hint}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selectedTask.status === "failed" && (
                <div className="page-error">{selectedTask.error || "生成失败"}</div>
              )}

              {selectedTask.result && renderResult(selectedTask.result)}

              <div className="video-detail-actions">
                {typeof selectedTask.result?.video_url === "string" && (
                  <a href={selectedTask.result.video_url} download className="video-action-btn">
                    <Download size={16} /> 下载
                  </a>
                )}
                {typeof selectedTask.result?.image_base64 === "string" && (
                  <a href={`data:image/png;base64,${selectedTask.result.image_base64}`} download={`${selectedTask.topic || "image"}.png`} className="video-action-btn">
                    <Download size={16} /> 下载图片
                  </a>
                )}
                <button type="button" className="video-action-btn danger" onClick={() => handleDeleteTask(selectedTask.task_id)}>
                  <Trash2 size={16} /> 删除
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {detailLoading && (
        <div className="res-lib-detail-overlay" onClick={() => setDetailLoading(false)} role="button" tabIndex={0}>
          <div className="res-lib-detail" onClick={(e) => e.stopPropagation()}>
            <div className="res-lib-detail-body" style={{ textAlign: "center", padding: 40 }}>
              <Loader2 size={24} className="video-spinner" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
