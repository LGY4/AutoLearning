import { useCallback, useRef, useState } from "react";
import { Film, Play, Loader2, Download, RotateCcw } from "lucide-react";
import { useAppContext } from "../context/AppContext";
import { apiGet, apiPost, getFriendlyError } from "../api/client";

interface SceneResult {
  scene: number;
  narration: string;
  duration: number;
}

interface VideoResult {
  video_id: string;
  video_url: string;
  thumbnail_url?: string;
  title: string;
  duration_seconds: number;
  scenes: SceneResult[];
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
};

export function VideoStudioPage() {
  const { state } = useAppContext();
  const { user } = state;

  const [topic, setTopic] = useState("");
  const [subject, setSubject] = useState("通用");
  const [numScenes, setNumScenes] = useState(5);
  const [style, setStyle] = useState("educational");
  const [ttsVoice, setTtsVoice] = useState("zh-CN-YunjianNeural");

  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [result, setResult] = useState<VideoResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

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
      // Start async generation
      const { task_id } = await apiPost<{ task_id: string }>("/video/generate-async", {
        user_id: user.id,
        topic: topic.trim(),
        subject,
        num_scenes: numScenes,
        style,
        tts_voice: ttsVoice,
      });

      // Poll for progress and completion (EventSource doesn't support auth headers)
      const pollInterval = setInterval(async () => {
        try {
          const status = await apiGet<VideoTaskStatus>(`/video/status/${task_id}`);
          // Update progress from server
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
        } catch {}
      }, 2000);

      // Cleanup after 10 min
      setTimeout(() => clearInterval(pollInterval), 600000);

    } catch (err) {
      setError(err instanceof Error ? getFriendlyError(err.message) : "请求失败，请重试");
      setGenerating(false);
    }
  }, [user, topic, subject, numScenes, style, ttsVoice]);

  const handleReset = () => {
    setResult(null);
    setProgress([]);
    setError(null);
  };

  return (
    <div className="video-studio-page">
      <div className="video-studio-header">
        <Film size={28} />
        <h1>视频工坊</h1>
        <p className="video-studio-desc">输入主题，AI 自动生成教学视频</p>
      </div>

      {!result ? (
        <div className="video-studio-form">
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

          {error && <div className="page-error">{error}</div>}

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
      ) : (
        <div className="video-result">
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

          <div className="video-result-info">
            <h2>{result.title}</h2>
            <p>时长：{Math.round(result.duration_seconds)}秒 | {result.scenes.length} 个场景</p>
          </div>

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

          <div className="video-result-actions">
            <a href={result.video_url} download className="video-action-btn">
              <Download size={16} />
              下载视频
            </a>
            <button type="button" className="video-action-btn secondary" onClick={handleReset}>
              <RotateCcw size={16} />
              再次生成
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
