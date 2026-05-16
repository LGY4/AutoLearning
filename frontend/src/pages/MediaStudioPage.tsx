import { useState } from "react";
import { Film, Image, Wand2 } from "lucide-react";
import { apiPost } from "../api/client";

type Tab = "animation" | "image" | "analyze";

export function MediaStudioPage() {
  const [tab, setTab] = useState<Tab>("animation");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  // Animation form
  const [animKP, setAnimKP] = useState("");
  const [animSubject, setAnimSubject] = useState("数据结构");
  const [animDifficulty, setAnimDifficulty] = useState("beginner");

  // Image form
  const [imgPrompt, setImgPrompt] = useState("");
  const [imgStyle, setImgStyle] = useState("educational");
  const [imgSize, setImgSize] = useState("1024x1024");

  // Analyze form
  const [analyzePrompt, setAnalyzePrompt] = useState("");
  const [analyzeImages, setAnalyzeImages] = useState<string[]>([]);

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "animation", label: "动画生成", icon: <Film size={16} /> },
    { key: "image", label: "图片生成", icon: <Image size={16} /> },
    { key: "analyze", label: "图片分析", icon: <Wand2 size={16} /> },
  ];

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      let res: Record<string, unknown>;
      if (tab === "animation") {
        if (!animKP.trim()) { setError("请输入知识点"); return; }
        res = await apiPost("/system/generate-animation", { knowledge_point: animKP, subject: animSubject, difficulty: animDifficulty });
      } else if (tab === "image") {
        if (!imgPrompt.trim()) { setError("请输入描述"); return; }
        res = await apiPost("/system/generate-image", { prompt: imgPrompt, style: imgStyle, size: imgSize });
      } else {
        if (!analyzePrompt.trim()) { setError("请输入分析提示"); return; }
        if (analyzeImages.length === 0) { setError("请上传图片"); return; }
        res = await apiPost("/system/analyze-image", { prompt: analyzePrompt, images: analyzeImages });
      }
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  }

  function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
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
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1><Wand2 size={24} /> 媒体工坊</h1>
      </div>

      <div className="tab-bar">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`tab-btn ${tab === t.key ? "active" : ""}`}
            onClick={() => { setTab(t.key); setResult(null); setError(null); }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      <div className="form-card">
        {tab === "animation" && (
          <>
            <h3>Manim 动画生成</h3>
            <p className="form-hint">输入知识点，系统自动生成可视化动画。</p>
            <input placeholder="知识点（如：二叉树遍历）" value={animKP} onChange={(e) => setAnimKP(e.target.value)} />
            <div className="form-row">
              <input placeholder="学科" value={animSubject} onChange={(e) => setAnimSubject(e.target.value)} />
              <select value={animDifficulty} onChange={(e) => setAnimDifficulty(e.target.value)}>
                <option value="beginner">入门</option>
                <option value="intermediate">中级</option>
                <option value="advanced">高级</option>
              </select>
            </div>
          </>
        )}

        {tab === "image" && (
          <>
            <h3>AI 图片生成</h3>
            <p className="form-hint">描述你需要的图片内容和风格。</p>
            <textarea placeholder="图片描述（如：二叉树的中序遍历过程示意图）" value={imgPrompt} onChange={(e) => setImgPrompt(e.target.value)} rows={3} />
            <div className="form-row">
              <select value={imgStyle} onChange={(e) => setImgStyle(e.target.value)}>
                <option value="educational">教学风格</option>
                <option value="realistic">写实风格</option>
                <option value="cartoon">卡通风格</option>
                <option value="minimal">极简风格</option>
              </select>
              <select value={imgSize} onChange={(e) => setImgSize(e.target.value)}>
                <option value="1024x1024">1024x1024</option>
                <option value="1792x1024">1792x1024 (横)</option>
                <option value="1024x1792">1024x1792 (竖)</option>
              </select>
            </div>
          </>
        )}

        {tab === "analyze" && (
          <>
            <h3>图片内容分析</h3>
            <p className="form-hint">上传图片并描述你想了解的内容。</p>
            <input type="file" accept="image/*" multiple onChange={handleImageUpload} />
            {analyzeImages.length > 0 && (
              <div className="image-preview-list">
                {analyzeImages.map((img, i) => (
                  <img key={i} src={img} alt={`预览 ${i + 1}`} className="image-preview-thumb" />
                ))}
              </div>
            )}
            <textarea placeholder="分析提示（如：请解释这张图中的算法流程）" value={analyzePrompt} onChange={(e) => setAnalyzePrompt(e.target.value)} rows={2} />
          </>
        )}

        {error && <div className="page-error">{error}</div>}

        <button className="btn-primary" onClick={handleGenerate} disabled={loading} style={{ marginTop: 12 }}>
          {loading ? "生成中..." : "开始生成"}
        </button>
      </div>

      {result && (
        <div className="info-card" style={{ marginTop: 16 }}>
          <h3>生成结果</h3>
          {typeof result.video_url === "string" && (
            <video controls src={result.video_url} style={{ maxWidth: "100%", borderRadius: 8 }} />
          )}
          {typeof result.image_base64 === "string" && (
            <img src={`data:image/png;base64,${result.image_base64}`} alt="生成图片" style={{ maxWidth: "100%", borderRadius: 8 }} />
          )}
          {typeof result.analysis === "string" && (
            <p style={{ whiteSpace: "pre-wrap" }}>{result.analysis}</p>
          )}
          {typeof result.title === "string" && (
            <p><strong>标题：</strong>{result.title}</p>
          )}
          {typeof result.duration_seconds === "number" && (
            <p><strong>时长：</strong>{Math.round(result.duration_seconds)}秒</p>
          )}
          {Array.isArray(result.scenes) && result.scenes.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <strong>分镜脚本：</strong>
              {result.scenes.map((s: Record<string, unknown>, i: number) => (
                <div key={i} style={{ margin: "8px 0", padding: "8px", background: "rgba(255,255,255,0.04)", borderRadius: 6 }}>
                  <span>场景 {(s.scene as number) + 1} · {String(s.duration || 0)}秒</span>
                  <p style={{ margin: "4px 0 0" }}>{String(s.narration || "")}</p>
                </div>
              ))}
            </div>
          )}
          {typeof result.video_url === "string" && (
            <a href={result.video_url} download className="btn-primary" style={{ display: "inline-block", marginTop: 12, textDecoration: "none" }}>
              下载视频
            </a>
          )}
        </div>
      )}
    </div>
  );
}
