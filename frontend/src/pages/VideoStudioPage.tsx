import { useCallback, useEffect, useRef, useState } from "react";
import { Film, Play, Loader2, Download, RotateCcw, Trash2, Clock, ChevronLeft, ChevronRight } from "lucide-react";
import { useAppContext } from "../context/AppContext";
import { apiGet, apiPost, apiDelete, getFriendlyError } from "../api/client";

interface SceneResult {
  scene: number;
  narration: string;
  duration: number;
}

interface VideoResult {
  video_id: string;
  video_mode?: string;
  provider_mode?: string;
  generation_status?: string;
  video_url?: string | null;
  thumbnail_url?: string;
  title: string;
  duration_seconds: number;
  scenes: SceneResult[];
  fallback_used?: boolean;
}

interface ProgressEvent {
  stage: string;
  status: string;
  scene?: number;
  hint: string;
}

interface VideoTaskStatus {
  task_id: string;
  status: string;
  progress: ProgressEvent[];
  result: VideoResult | null;
  error: string | null;
}

interface VideoHistoryItem {
  task_id: string;
  mode: string;
  status: string;
  topic: string;
  subject: string;
  result: VideoResult | null;
  created_at: string | null;
}

interface DigitalHumanStatus {
  provider: string;
  configured: boolean;
  api_url: string;
  persona_configured: boolean;
  voice_configured: boolean;
  fallback_available: boolean;
  ffmpeg_available: boolean;
  edge_tts_available: boolean;
  mode: string;
}

const STYLES = [
  { value: "educational", label: "教育风" },
  { value: "cartoon", label: "卡通" },
  { value: "minimal", label: "极简" },
  { value: "tech", label: "科技" },
  { value: "hand_drawn", label: "手绘" },
];

const VOICES = [
  { value: "zh-CN-YunjianNeural", label: "云健（男）" },
  { value: "zh-CN-YunxiNeural", label: "云希（男）" },
  { value: "zh-CN-XiaoxiaoNeural", label: "晓晓（女）" },
  { value: "zh-CN-XiaoyiNeural", label: "晓伊（女）" },
];

const STAGE_LABELS: Record<string, string> = {
  script: "分镜脚本",
  tts: "语音合成",
  image: "配图生成",
  compose: "画面合成",
  segment: "视频片段",
  concat: "最终拼接",
  submit: "任务提交",
  digital_human: "数字人生成",
  download: "资源下载",
};

type Tab = "generate" | "history";

export function VideoStudioPage() {
  const { state } = useAppContext();
  const { user } = state;

  const [tab, setTab] = useState<Tab>("generate");

  // Generate form state
  const [videoMode, setVideoMode] = useState<"classic" | "digital_human">("classic");
  const [topic, setTopic] = useState("");
  const [subject, setSubject] = useState("通用");
  const [numScenes, setNumScenes] = useState(5);
  const [style, setStyle] = useState("educational");
  const [ttsVoice, setTtsVoice] = useState("zh-CN-YunjianNeural");

  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [result, setResult] = useState<VideoResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [digitalHumanStatus, setDigitalHumanStatus] = useState<DigitalHumanStatus | null>(null);

  // History state
  const [historyItems, setHistoryItems] = useState<VideoHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Detail overlay
  const [selectedTask, setSelectedTask] = useState<VideoTaskStatus | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    apiGet<DigitalHumanStatus>("/video/digital-human/status")
      .then(setDigitalHumanStatus)
      .catch(() => setDigitalHumanStatus(null));
  }, [user]);

  // ── History ──

  const loadHistory = useCallback(async (page = 1) => {
    if (!user) return;
    setHistoryLoading(true);
    try {
      const data = await apiGet<{ items: VideoHistoryItem[]; total: number; page: number; page_size: number }>(
        `/video/history?page=${page}&page_size=15`
      );
      setHistoryItems(data.items);
      setHistoryTotal(data.total);
      setHistoryPage(data.page);
    } catch {
      // silent
    } finally {
      setHistoryLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (tab === "history") loadHistory();
  }, [tab, loadHistory]);

  // ── Detail ──

  const handleSelectTask = async (taskId: string) => {
    setDetailLoading(true);
    try {
      const data = await apiGet<VideoTaskStatus>(`/video/detail/${taskId}`);
      setSelectedTask(data);
    } catch {
      // silent
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await apiDelete(`/video/${taskId}`);
      setHistoryItems((prev) => prev.filter((t) => t.task_id !== taskId));
      setHistoryTotal((prev) => prev - 1);
      if (selectedTask?.task_id === taskId) setSelectedTask(null);
    } catch {
      // silent
    }
  };

  const handleRegenerate = (item: VideoHistoryItem) => {
    setTopic(item.topic);
    setSubject(item.subject || "通用");
    setVideoMode(item.mode === "digital_human" ? "digital_human" : "classic");
    setResult(null);
    setProgress([]);
    setError(null);
    setTab("generate");
    setSelectedTask(null);
  };

  // ── Generate ──

  const handleGenerate = useCallback(async () => {
    if (!user) return;
    if (!topic.trim()) return;

    setGenerating(true);
    setProgress([]);
    setResult(null);
    setError(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const endpoint = videoMode === "digital_human" ? "/video/dh-generate-async" : "/video/generate-async";
      const body = videoMode === "digital_human"
        ? { text: topic.trim(), knowledge_point: topic.trim() }
        : { user_id: user.id, topic: topic.trim(), subject, num_scenes: numScenes, style, tts_voice: ttsVoice };
      const { task_id } = await apiPost<{ task_id: string }>(endpoint, body);

      if (pollRef.current) clearInterval(pollRef.current);
      const pollMs = videoMode === "digital_human" ? 120000 : 2000;
      const pollInterval = setInterval(async () => {
        try {
          const status = await apiGet<VideoTaskStatus>(`/video/status/${task_id}`);
          if (status.progress?.length) {
            setProgress(status.progress);
          }
          if (status.status === "done" && status.result) {
            setResult(status.result as unknown as VideoResult);
            clearInterval(pollInterval);
            setGenerating(false);
          } else if (status.status === "failed") {
            setError(status.error || "视频生成失败");
            clearInterval(pollInterval);
            setGenerating(false);
          }
        } catch {
          // Task not found or network error — stop polling
          clearInterval(pollInterval);
          setGenerating(false);
          setError("任务查询失败，请刷新后在历史记录中查看");
        }
      }, pollMs);
      pollRef.current = pollInterval;

      // 30-minute timeout for digital human (longer generation), 10-min for others
      const timeoutMs = videoMode === "digital_human" ? 1800000 : 600000;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        clearInterval(pollInterval);
        setGenerating(false);
        setError("生成超时，请在历史记录中查看结果");
      }, timeoutMs);

    } catch (err) {
      setError(err instanceof Error ? getFriendlyError(err.message) : "请求失败，请重试");
      setGenerating(false);
    }
  }, [user, topic, subject, numScenes, style, ttsVoice, videoMode]);

  const handleReset = () => {
    setResult(null);
    setProgress([]);
    setError(null);
  };

  const digitalHumanStatusLabel = digitalHumanStatus?.configured
    ? "讯飞数字人已配置"
    : digitalHumanStatus?.fallback_available
      ? "本地降级可用"
      : "当前仅分镜预览";

  const digitalHumanStatusDetail = digitalHumanStatus?.configured
    ? `云端接口 ${digitalHumanStatus.api_url}`
    : digitalHumanStatus?.fallback_available
      ? "可使用本地 FFmpeg 合成数字人讲解视频"
      : "请配置讯飞数字人 API，或安装 FFmpeg 启用本地降级";

  // ── Status badge ──

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

  return (
    <div className="video-studio-page">
      <div className="video-studio-header">
        <Film size={28} />
        <h1>视频工坊</h1>
        <p className="video-studio-desc">输入主题，AI 自动生成教学视频</p>
      </div>

      {/* Tab bar */}
      <div className="video-studio-tabs">
        <button className={`video-tab-btn ${tab === "generate" ? "active" : ""}`} onClick={() => setTab("generate")}>生成视频</button>
        <button className={`video-tab-btn ${tab === "history" ? "active" : ""}`} onClick={() => setTab("history")}>历史记录 {historyTotal > 0 && <span className="video-tab-count">{historyTotal}</span>}</button>
      </div>

      {error && !generating && <div className="page-error">{error}</div>}

      {/* ── Generate tab ── */}
      {tab === "generate" && !result && (
        <div className="video-studio-form">
          <div className="video-form-field">
            <label>视频类型</label>
            <div className="video-style-options">
              <button type="button" className={`video-style-btn ${videoMode === "classic" ? "active" : ""}`} onClick={() => setVideoMode("classic")} disabled={generating}>知识讲解视频</button>
              <button type="button" className={`video-style-btn ${videoMode === "digital_human" ? "active" : ""}`} onClick={() => setVideoMode("digital_human")} disabled={generating}>数字人讲解</button>
            </div>
            {videoMode === "digital_human" && (
              <div className="digital-human-status-line">
                <span className={digitalHumanStatus?.configured || digitalHumanStatus?.fallback_available ? "ready" : "warning"}>
                  {digitalHumanStatusLabel}
                </span>
                <em>{digitalHumanStatusDetail}</em>
              </div>
            )}
          </div>

          <div className="video-form-field">
            <label>主题 / 知识点</label>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：什么是栈和队列？二叉树的遍历方式有哪些？"
              rows={3}
              disabled={generating}
            />
          </div>

          {videoMode === "classic" && (
            <>
              <div className="video-form-row">
                <div className="video-form-field">
                  <label>学科</label>
                  <input value={subject} onChange={(e) => setSubject(e.target.value)} disabled={generating} />
                </div>
                <div className="video-form-field">
                  <label>场景数</label>
                  <select value={numScenes} onChange={(e) => setNumScenes(Number(e.target.value))} disabled={generating}>
                    {[3, 4, 5, 6, 7, 8].map((n) => (
                      <option key={n} value={n}>{n} 个场景</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="video-form-row">
                <div className="video-form-field">
                  <label>视觉风格</label>
                  <div className="video-style-options">
                    {STYLES.map((s) => (
                      <button
                        key={s.value}
                        type="button"
                        className={`video-style-btn ${style === s.value ? "active" : ""}`}
                        onClick={() => setStyle(s.value)}
                        disabled={generating}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="video-form-row">
                <div className="video-form-field">
                  <label>语音</label>
                  <select value={ttsVoice} onChange={(e) => setTtsVoice(e.target.value)} disabled={generating}>
                    {VOICES.map((v) => (
                      <option key={v.value} value={v.value}>{v.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          )}

          {generating ? (
            <div className="video-progress">
              <div className="video-progress-header">
                <Loader2 size={20} className="video-spinner" />
                <span>视频生成中...</span>
              </div>
              <div className="video-progress-steps">
                {progress.map((evt, i) => (
                  <div key={`${evt.stage}-${evt.scene ?? i}`} className={`video-step ${evt.status}`}>
                    <span className="video-step-label">
                      {STAGE_LABELS[evt.stage] || evt.stage}
                      {evt.scene != null ? ` (${evt.scene + 1})` : ""}
                    </span>
                    <span className="video-step-hint">{evt.hint}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="video-generate-btn"
              onClick={handleGenerate}
              disabled={!topic.trim() || !user}
            >
              <Play size={20} />
              生成视频
            </button>
          )}
        </div>
      )}

      {/* ── Result view ── */}
      {tab === "generate" && result && (
        <div className="video-result">
          <div className="video-result-header">
            <h2>视频生成完成</h2>
            <button type="button" className="video-action-btn" onClick={handleReset}>
              <RotateCcw size={16} />
              重新生成
            </button>
          </div>
          {result.video_url ? (
            <div className="video-player-container">
              <video
                controls
                src={result.video_url}
                poster={result.thumbnail_url || undefined}
                className="video-player"
              >
                您的浏览器不支持视频播放
              </video>
            </div>
          ) : (
            <div className="video-render-hint">
              数字人视频未生成可播放文件，请配置讯飞数字人 API 或本地 FFmpeg 后重新生成。
            </div>
          )}

          <div className="video-result-info">
            <h2>{result.title}</h2>
            {result.duration_seconds > 0 && (
              <p>时长：{Math.round(result.duration_seconds)}秒 | {result.scenes.length} 个场景</p>
            )}
          </div>

          {result.scenes.length > 0 && (
            <div className="video-scenes-list">
              <h3>分镜脚本</h3>
              {result.scenes.map((scene, i) => (
                <div key={i} className="video-scene-card">
                  <span className="video-scene-idx">场景 {scene.scene + 1}</span>
                  <span className="video-scene-duration">{scene.duration}s</span>
                  <p className="video-scene-narration">{scene.narration}</p>
                </div>
              ))}
            </div>
          )}

          <div className="video-result-actions">
            {result.video_url && (
              <a href={result.video_url} download className="video-action-btn">
                <Download size={16} />
                下载视频
              </a>
            )}
            <button type="button" className="video-action-btn secondary" onClick={handleReset}>
              <RotateCcw size={16} />
              再次生成
            </button>
          </div>
        </div>
      )}

      {/* ── History tab ── */}
      {tab === "history" && (
        <div className="video-history">
          {historyLoading ? (
            <div className="video-history-loading"><Loader2 size={24} className="video-spinner" /></div>
          ) : historyItems.length === 0 ? (
            <div className="video-history-empty">暂无生成记录</div>
          ) : (
            <>
              <div className="video-history-list">
                {historyItems.map((item) => (
                  <div
                    key={item.task_id}
                    className="video-history-card"
                    onClick={() => handleSelectTask(item.task_id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && handleSelectTask(item.task_id)}
                  >
                    <div className="video-history-card-thumb">
                      {item.result?.thumbnail_url ? (
                        <img src={item.result.thumbnail_url} alt="" />
                      ) : item.result?.video_url ? (
                        <video src={item.result.video_url} muted preload="metadata" />
                      ) : (
                        <div className="video-history-card-placeholder"><Film size={24} /></div>
                      )}
                    </div>
                    <div className="video-history-card-info">
                      <div className="video-history-card-title">{item.topic}</div>
                      <div className="video-history-card-meta">
                        {item.mode === "digital_human" ? "数字人" : "经典"} · {item.subject}
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
                <strong>{selectedTask.result?.title || "视频详情"}</strong>
              </div>
              <button className="res-lib-detail-close" onClick={() => setSelectedTask(null)} type="button">✕</button>
            </div>
            <div className="res-lib-detail-body">
              {selectedTask.status === "running" && (
                <div className="video-progress">
                  <div className="video-progress-header">
                    <Loader2 size={20} className="video-spinner" />
                    <span>视频生成中...</span>
                  </div>
                  <div className="video-progress-steps">
                    {selectedTask.progress.map((evt, i) => (
                      <div key={`${evt.stage}-${evt.scene ?? i}`} className={`video-step ${evt.status}`}>
                        <span className="video-step-label">{STAGE_LABELS[evt.stage] || evt.stage}</span>
                        <span className="video-step-hint">{evt.hint}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selectedTask.status === "failed" && (
                <div className="page-error">{selectedTask.error || "视频生成失败"}</div>
              )}

              {selectedTask.result?.video_url && (
                <>
                  <div className="video-player-container">
                    <video controls src={selectedTask.result.video_url} poster={selectedTask.result.thumbnail_url || undefined} className="video-player">
                      您的浏览器不支持视频播放
                    </video>
                  </div>

                  {selectedTask.result.scenes?.length > 0 && (
                    <div className="video-scenes-list">
                      <h3>分镜脚本</h3>
                      {selectedTask.result.scenes.map((scene, i) => (
                        <div key={i} className="video-scene-card">
                          <span className="video-scene-idx">场景 {scene.scene + 1}</span>
                          <span className="video-scene-duration">{scene.duration}s</span>
                          <p className="video-scene-narration">{scene.narration}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              <div className="video-detail-actions">
                {selectedTask.result?.video_url && (
                  <a href={selectedTask.result.video_url} download className="video-action-btn">
                    <Download size={16} />
                    下载视频
                  </a>
                )}
                <button type="button" className="video-action-btn" onClick={() => {
                  const item = historyItems.find((h) => h.task_id === selectedTask.task_id);
                  if (item) handleRegenerate(item);
                }}>
                  <RotateCcw size={16} />
                  重新生成
                </button>
                <button type="button" className="video-action-btn danger" onClick={() => handleDeleteTask(selectedTask.task_id)}>
                  <Trash2 size={16} />
                  删除
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
