import { useState, useEffect, useRef, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import java from "react-syntax-highlighter/dist/esm/languages/prism/java";
import c from "react-syntax-highlighter/dist/esm/languages/prism/c";
import cpp from "react-syntax-highlighter/dist/esm/languages/prism/cpp";
import go from "react-syntax-highlighter/dist/esm/languages/prism/go";
import rust from "react-syntax-highlighter/dist/esm/languages/prism/rust";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { LearningResource } from "../../types/baseline";
import { useAppContext } from "../../context/AppContext";
import { apiPost } from "../../api/client";
import { FlowchartView } from "./FlowchartView";

SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("java", java);
SyntaxHighlighter.registerLanguage("c", c);
SyntaxHighlighter.registerLanguage("cpp", cpp);
SyntaxHighlighter.registerLanguage("go", go);
SyntaxHighlighter.registerLanguage("rust", rust);
SyntaxHighlighter.registerLanguage("sql", sql);
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("html", markup);
SyntaxHighlighter.registerLanguage("xml", markup);

interface Props {
  resource: LearningResource;
}

// ── Download utility ─────────────────────────────────────────────────────

function downloadFile(content: string | Blob, filename: string, mimeType?: string) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType || "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadFromUrl(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.target = "_blank";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

const langExtMap: Record<string, string> = {
  python: "py", javascript: "js", typescript: "ts", java: "java",
  c: "c", cpp: "cpp", go: "go", rust: "rs", sql: "sql",
  bash: "sh", html: "html", css: "css", xml: "xml", json: "json",
};

// ── Markdown Renderer ──────────────────────────────────────────────────────

function MarkdownView({ content, title }: { content: string; title?: string }) {
  const handleDownload = () => {
    const filename = (title || "document").replace(/[<>:"/\\|?*]/g, "_").substring(0, 50) + ".md";
    downloadFile(content, filename, "text/markdown;charset=utf-8");
  };

  return (
    <div className="markdown-view">
      <div className="resource-toolbar">
        <button className="resource-download-btn" onClick={handleDownload} type="button">
          下载 Markdown
        </button>
      </div>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const codeString = String(children).replace(/\n$/, "");
            if (match) {
              return (
                <div className="code-block-wrapper">
                  <div className="code-block-header">
                    <span>{match[1]}</span>
                    <button
                      className="copy-btn"
                      onClick={() => navigator.clipboard.writeText(codeString)}
                      type="button"
                    >
                      Copy
                    </button>
                  </div>
                  <SyntaxHighlighter
                    style={oneDark}
                    language={match[1]}
                    PreTag="div"
                    customStyle={{ margin: 0, borderRadius: "0 0 8px 8px", fontSize: "13px" }}
                  >
                    {codeString}
                  </SyntaxHighlighter>
                </div>
              );
            }
            return (
              <code className="inline-code" {...props}>
                {children}
              </code>
            );
          },
          table({ children }) {
            return (
              <div className="table-wrapper">
                <table>{children}</table>
              </div>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ── Markmap Renderer (interactive mindmap via markmap-lib + markmap-view) ────

type MarkmapModule = typeof import("markmap-view");
type TransformerModule = typeof import("markmap-lib");

let _markmapMod: MarkmapModule | null = null;
let _transformerMod: TransformerModule | null = null;

async function loadMarkmap(): Promise<{ Markmap: MarkmapModule["Markmap"]; Transformer: TransformerModule["Transformer"] }> {
  if (!_markmapMod || !_transformerMod) {
    [_markmapMod, _transformerMod] = await Promise.all([
      import("markmap-view"),
      import("markmap-lib"),
    ]);
  }
  return { Markmap: _markmapMod.Markmap, Transformer: _transformerMod.Transformer };
}

function MarkmapView({ content }: { content: string }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const mmRef = useRef<InstanceType<MarkmapModule["Markmap"]> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    let cancelled = false;
    loadMarkmap().then(({ Markmap: MM, Transformer: TF }) => {
      if (cancelled || !svgRef.current) return;
      try {
        const tf = new TF();
        const { root } = tf.transform(content);
        if (!mmRef.current) {
          mmRef.current = MM.create(svgRef.current, {
            maxWidth: 320,
            initialExpandLevel: 2,
          });
        }
        mmRef.current.setData(root);
        mmRef.current.fit();
        setError(null);
      } catch {
        setError("思维导图内容格式错误，无法渲染");
      }
    }).catch(() => setError("思维导图组件加载失败"));
    return () => {
      cancelled = true;
      mmRef.current?.destroy();
      mmRef.current = null;
    };
  }, [content]);

  const handleExportXmind = async () => {
    const [{ Workbook, RootTopic, Topic }, { Transformer: TF }] = await Promise.all([
      import("xmind-generator"),
      loadMarkmap(),
    ]);
    const tf = new TF();
    const { root } = tf.transform(content);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const buildTopics = (nodes: any[]): ReturnType<typeof Topic>[] =>
      nodes.map((node: any) => {
        const topic = Topic(String(node.content).replace(/<[^>]*>/g, ""));
        if (node.children?.length) {
          topic.children(buildTopics(node.children));
        }
        return topic;
      });

    const rootTopic = RootTopic(String(root.content).replace(/<[^>]*>/g, ""));
    if (root.children?.length) {
      rootTopic.children(buildTopics(root.children));
    }
    const wb = Workbook(rootTopic);
    const buffer = await wb.archive();
    const blob = new Blob([buffer], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "mindmap.xmind";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (error) {
    return (
      <div className="resource-error-card">
        <p className="resource-error-msg">{error}</p>
        <p className="resource-error-hint">该资源内容可能生成失败，请尝试重新生成。</p>
      </div>
    );
  }

  return (
    <div className="markmap-container">
      <div className="markmap-toolbar">
        <button className="markmap-export-btn" onClick={handleExportXmind} type="button">
          导出 XMind
        </button>
      </div>
      <svg ref={svgRef} style={{ width: "100%", height: "400px" }} />
    </div>
  );
}

// ── Quiz Renderer (interactive) ────────────────────────────────────────────

interface QuizQuestion {
  type: string;
  stem: string;
  options?: string[];
  answer: string;
  explanation?: string;
  difficulty?: string;
}

interface QuizPayload {
  title?: string;
  overview?: string;
  questions: QuizQuestion[];
  scoring_rules?: string[];
}

interface GradeResult {
  score: number;
  is_correct: boolean;
  feedback: string;
  key_points_hit: string[];
  key_points_missed: string[];
}

function QuizView({ content }: { content: string }) {
  const { state } = useAppContext();
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const [selected, setSelected] = useState<Record<number, string>>({});
  const [userAnswers, setUserAnswers] = useState<Record<number, string>>({});
  const [grading, setGrading] = useState<Record<number, boolean>>({});
  const [gradeResults, setGradeResults] = useState<Record<number, GradeResult>>({});

  const payload = useMemo<QuizPayload | null>(() => {
    try {
      return JSON.parse(content);
    } catch {
      return null;
    }
  }, [content]);
  if (!payload) return <MarkdownView content={content} />;

  const toggleReveal = (index: number) => {
    setRevealed((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  const selectOption = (qIndex: number, option: string) => {
    setSelected((prev) => ({ ...prev, [qIndex]: option }));
    setRevealed((prev) => ({ ...prev, [qIndex]: true }));
  };

  const handleGrade = async (qIndex: number, q: { type: string; stem: string; answer: string; explanation?: string }) => {
    const userAns = userAnswers[qIndex]?.trim();
    if (!userAns || !state.user) return;
    setGrading((prev) => ({ ...prev, [qIndex]: true }));
    try {
      const result = await apiPost<GradeResult>("/resources/grade", {
        user_id: state.user.id,
        question_id: "00000000-0000-0000-0000-000000000000",
        question_type: q.type === "fill_blank" ? "blank" : q.type,
        stem: q.stem,
        standard_answer: q.answer,
        user_answer: userAns,
        explanation: q.explanation,
      });
      if (result) {
        setGradeResults((prev) => ({ ...prev, [qIndex]: result }));
        setRevealed((prev) => ({ ...prev, [qIndex]: true }));
      }
    } catch {
      // Show user feedback on grading failure
      setGradeResults((prev) => ({
        ...prev,
        [qIndex]: { score: 0, is_correct: false, feedback: "评分失败，请稍后重试", key_points_hit: [], key_points_missed: [] },
      }));
    } finally {
      setGrading((prev) => ({ ...prev, [qIndex]: false }));
    }
  };

  const typeLabel: Record<string, string> = {
    choice: "选择题",
    fill_blank: "填空题",
    programming: "编程题",
    case_analysis: "案例分析",
    short_answer: "简答题",
  };

  const handleDownloadQuiz = () => {
    const filename = (payload.title || "quiz").replace(/[<>:"/\\|?*]/g, "_").substring(0, 50) + ".json";
    downloadFile(JSON.stringify(payload, null, 2), filename, "application/json;charset=utf-8");
  };

  return (
    <div className="quiz-view">
      <div className="resource-toolbar">
        <button className="resource-download-btn" onClick={handleDownloadQuiz} type="button">
          下载题目 (JSON)
        </button>
      </div>
      {payload.title && <h3 className="quiz-title">{payload.title}</h3>}
      {payload.overview && <p className="quiz-overview">{payload.overview}</p>}

      {(payload.questions ?? []).map((q, i) => {
        const isRevealed = revealed[i];
        const isCorrect = selected[i] === q.answer;
        const gradeResult = gradeResults[i];

        return (
          <div className={`quiz-question ${isRevealed ? "revealed" : ""}`} key={`q-${i}`}>
            <div className="quiz-question-header">
              <span className="quiz-badge">{typeLabel[q.type] ?? q.type}</span>
              {q.difficulty && <span className={`quiz-difficulty ${q.difficulty}`}>{q.difficulty}</span>}
              <span className="quiz-number">第 {i + 1} 题</span>
            </div>
            <p className="quiz-stem">{q.stem}</p>

            {q.type === "choice" && q.options && (
              <div className="quiz-options">
                {q.options.map((opt, oi) => {
                  const isSelected = selected[i] === opt;
                  const isAnswer = opt === q.answer;
                  let optClass = "quiz-option";
                  if (isRevealed && isAnswer) optClass += " correct";
                  if (isSelected && !isAnswer) optClass += " wrong";
                  if (isSelected) optClass += " selected";

                  return (
                    <button
                      className={optClass}
                      key={`opt-${oi}`}
                      onClick={() => !isRevealed && selectOption(i, opt)}
                      disabled={isRevealed}
                      type="button"
                    >
                      <span className="option-label">{String.fromCharCode(65 + oi)}</span>
                      <span>{opt}</span>
                    </button>
                  );
                })}
              </div>
            )}

            {q.type !== "choice" && !isRevealed && (
              <div className="quiz-input-section">
                <textarea
                  className="quiz-input"
                  placeholder="输入你的答案..."
                  value={userAnswers[i] || ""}
                  onChange={(e) => setUserAnswers((prev) => ({ ...prev, [i]: e.target.value }))}
                  rows={3}
                />
                <div className="quiz-input-actions">
                  <button
                    className="quiz-grade-btn"
                    onClick={() => handleGrade(i, q)}
                    disabled={grading[i] || !userAnswers[i]?.trim()}
                    type="button"
                  >
                    {grading[i] ? "评分中..." : "AI 评分"}
                  </button>
                  <button className="quiz-reveal-btn" onClick={() => toggleReveal(i)} type="button">
                    查看答案
                  </button>
                </div>
              </div>
            )}

            {gradeResult && (
              <div className={`quiz-grade-result ${gradeResult.is_correct ? "correct" : "wrong"}`}>
                <div className="quiz-grade-score">
                  得分：<strong>{gradeResult.score}</strong>/100
                  <span className={`quiz-grade-status ${gradeResult.is_correct ? "pass" : "fail"}`}>
                    {gradeResult.is_correct ? "通过" : "未通过"}
                  </span>
                </div>
                <div className="quiz-grade-feedback">{gradeResult.feedback}</div>
                {gradeResult.key_points_hit.length > 0 && (
                  <div className="quiz-grade-points">答对：{gradeResult.key_points_hit.join("、")}</div>
                )}
                {gradeResult.key_points_missed.length > 0 && (
                  <div className="quiz-grade-points missed">遗漏：{gradeResult.key_points_missed.join("、")}</div>
                )}
              </div>
            )}

            {isRevealed && (
              <div className="quiz-answer-section">
                {q.type === "choice" && (
                  <p className={`quiz-result ${isCorrect ? "correct" : "wrong"}`}>
                    {isCorrect ? "回答正确！" : `正确答案：${q.answer}`}
                  </p>
                )}
                {q.type !== "choice" && !gradeResult && (
                  <div className="quiz-answer-content">
                    <strong>参考答案：</strong>
                    <p>{q.answer}</p>
                  </div>
                )}
                {q.explanation && (
                  <div className="quiz-explanation">
                    <strong>解析：</strong>
                    <p>{q.explanation}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {payload.scoring_rules && payload.scoring_rules.length > 0 && (
        <div className="quiz-scoring">
          <strong>评分规则：</strong>
          <ul>
            {payload.scoring_rules.map((rule, i) => (
              <li key={`rule-${i}`}>{rule}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Code Renderer (with syntax highlighting) ───────────────────────────────

function CodeView({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  // Try to extract language and code from markdown code blocks
  const codeBlockMatch = content.match(/```(\w+)?\n([\s\S]*?)```/);
  const language = codeBlockMatch?.[1] || "text";
  const code = codeBlockMatch?.[2] || content;

  const handleDownload = () => {
    const ext = langExtMap[language] || "txt";
    downloadFile(code.trim(), `code_example.${ext}`);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(code.trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="code-view-container">
      <div className="resource-toolbar">
        <button className="resource-download-btn" onClick={handleDownload} type="button">
          下载代码
        </button>
      </div>
      <div className="code-block-wrapper">
        <div className="code-block-header">
          <span>{language}</span>
          <button className="copy-btn" onClick={handleCopy} type="button">
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
        <SyntaxHighlighter
          style={oneDark}
          language={language}
          PreTag="div"
          showLineNumbers
          customStyle={{ margin: 0, borderRadius: "0 0 8px 8px", fontSize: "13px" }}
        >
          {code.trim()}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

// ── Storyboard / Video Renderer ────────────────────────────────────────────

interface StoryboardScene {
  frame: number;
  duration_seconds?: number;
  visual_description?: string;
  narration?: string;
  image_prompt?: string;
}

function StoryboardView({ content }: { content: string }) {
  const parsed = useMemo(() => {
    try {
      const payload = JSON.parse(content);
      if (payload.scenes && Array.isArray(payload.scenes)) {
        return {
          isLegacy: false as const,
          title: payload.title || "",
          scenes: payload.scenes as StoryboardScene[],
          sceneImages: (payload.scene_images || {}) as Record<string, string>,
          videoPath: (payload.video_path || null) as string | null,
          videoUrl: (payload.video_url || null) as string | null,
          thumbnailUrl: (payload.thumbnail_url || null) as string | null,
          summary: payload.summary || "",
          keyPoints: (payload.key_points || []) as string[],
          isAnimation: payload.is_animation || false,
        };
      }
      return {
        isLegacy: true as const,
        title: payload.title || "",
        legacyStoryboard: (payload.video_storyboard || []) as string[],
        legacyImagePrompts: (payload.image_prompts || []) as string[],
        legacyNotes: (payload.notes || []) as string[],
      };
    } catch {
      if (content.includes("生成失败") || content.includes("error") || content.length < 20) {
        return null;
      }
      return {
        isLegacy: true as const,
        title: "",
        legacyStoryboard: content.split("\n").filter((l) => l.trim()),
        legacyImagePrompts: [] as string[],
        legacyNotes: [] as string[],
      };
    }
  }, [content]);

  if (!parsed) {
    return (
      <div className="resource-error-card">
        <p className="resource-error-msg">视频分镜生成失败</p>
        <p className="resource-error-hint">该资源内容无法解析，请尝试重新生成。</p>
      </div>
    );
  }

  if (parsed.isLegacy) {
    const { title, legacyStoryboard, legacyImagePrompts, legacyNotes } = parsed;
    return (
      <div className="storyboard-view">
        {title && <h3 className="storyboard-title">{title}</h3>}
        {legacyStoryboard.length > 0 && (
          <div className="storyboard-frames">
            <h4>视频分镜脚本</h4>
            {legacyStoryboard.map((frame, i) => (
              <div className="storyboard-frame" key={`frame-${i}`}>
                <div className="frame-number">{i + 1}</div>
                <div className="frame-content"><p>{frame}</p></div>
              </div>
            ))}
          </div>
        )}
        {legacyImagePrompts.length > 0 && (
          <div className="storyboard-prompts">
            <h4>配图提示词</h4>
            {legacyImagePrompts.map((prompt, i) => (
              <div className="prompt-card" key={`prompt-${i}`}>
                <span className="prompt-index">Prompt {i + 1}</span>
                <p>{prompt}</p>
              </div>
            ))}
          </div>
        )}
        {legacyNotes.length > 0 && (
          <div className="storyboard-notes">
            <h4>说明</h4>
            <ul>{legacyNotes.map((note, i) => (<li key={`note-${i}`}>{note}</li>))}</ul>
          </div>
        )}
      </div>
    );
  }

  const { title, scenes, sceneImages, videoPath, videoUrl, thumbnailUrl, summary, keyPoints, isAnimation } = parsed;
  // video_url is preferred (API path), fallback to video_path for backward compat
  const videoSrc = videoUrl || (videoPath && !videoPath.startsWith("/") ? null : videoPath);

  const handleDownloadVideo = () => {
    if (videoSrc) downloadFromUrl(videoSrc, (title || "video") + ".mp4");
  };

  const handleDownloadSceneImage = (imgPath: string, frameNum: number) => {
    downloadFromUrl(imgPath, `scene_${frameNum}.png`);
  };

  const handleDownloadScript = () => {
    const lines = scenes.map((s) => {
      const parts = [`镜头 ${s.frame}`];
      if (s.duration_seconds) parts.push(`时长: ${s.duration_seconds}秒`);
      if (s.visual_description) parts.push(`画面: ${s.visual_description}`);
      if (s.narration) parts.push(`旁白: ${s.narration}`);
      return parts.join("\n");
    });
    const text = `${title || "视频分镜"}\n${"=".repeat(40)}\n\n${lines.join("\n\n")}`;
    downloadFile(text, (title || "storyboard") + ".txt");
  };

  return (
    <div className="storyboard-view">
      <div className="resource-toolbar">
        {videoSrc && (
          <button className="resource-download-btn" onClick={handleDownloadVideo} type="button">
            下载视频
          </button>
        )}
        <button className="resource-download-btn" onClick={handleDownloadScript} type="button">
          下载脚本
        </button>
      </div>
      {title && <h3 className="storyboard-title">{title}</h3>}
      {summary && <p className="storyboard-summary">{summary}</p>}
      {isAnimation && <span className="storyboard-badge">动画</span>}

      {/* Video player */}
      {videoSrc && (
        <div className="storyboard-video">
          <video controls width="100%" src={videoSrc} poster={thumbnailUrl || undefined}>
            您的浏览器不支持视频播放
          </video>
        </div>
      )}

      {/* Scene cards */}
      {scenes.length > 0 && (
        <div className="storyboard-frames">
          <h4>分镜脚本（{scenes.length} 个镜头）</h4>
          {scenes.map((scene) => {
            const imgPath = sceneImages[String(scene.frame)];
            return (
              <div className="storyboard-frame" key={`frame-${scene.frame}`}>
                <div className="frame-number">{scene.frame}</div>
                <div className="frame-content">
                  {imgPath && (
                    <div className="frame-image">
                      <img src={imgPath} alt={`镜头 ${scene.frame}`} loading="lazy" />
                      <button
                        className="resource-download-btn resource-download-btn-sm"
                        onClick={() => handleDownloadSceneImage(imgPath, scene.frame)}
                        type="button"
                      >
                        下载配图
                      </button>
                    </div>
                  )}
                  {scene.visual_description && (
                    <p className="frame-visual"><strong>画面：</strong>{scene.visual_description}</p>
                  )}
                  {scene.narration && (
                    <p className="frame-narration"><strong>旁白：</strong>{scene.narration}</p>
                  )}
                  {scene.duration_seconds && (
                    <span className="frame-duration">{scene.duration_seconds}秒</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Key points */}
      {keyPoints.length > 0 && (
        <div className="storyboard-key-points">
          <h4>核心要点</h4>
          <ul>{keyPoints.map((p, i) => (<li key={`kp-${i}`}>{p}</li>))}</ul>
        </div>
      )}
    </div>
  );
}

// ── Main Renderer ──────────────────────────────────────────────────────────

export function ResourceRenderer({ resource }: Props) {
  // Null/undefined guard
  if (!resource.content) {
    return (
      <div className="resource-error-card">
        <p className="resource-error-msg">资源内容为空</p>
        <p className="resource-error-hint">该资源未生成有效内容，请尝试重新生成。</p>
      </div>
    );
  }

  // Failed status guard
  if (resource.status === "failed") {
    const errMsg = resource.content.includes("生成失败") ? resource.content : "资源生成失败";
    return (
      <div className="resource-error-card">
        <p className="resource-error-msg">{errMsg}</p>
        <p className="resource-error-hint">请尝试重新生成该资源。</p>
      </div>
    );
  }

  if (resource.resource_type === "mindmap") {
    // Detect draw.io XML vs Markmap markdown
    const isDrawioXml = resource.content.includes("<mxCell") || resource.content.includes("<mxfile");
    return isDrawioXml
      ? <FlowchartView content={resource.content} />
      : <MarkmapView content={resource.content} />;
  }
  if (resource.resource_type === "flowchart") {
    return <FlowchartView content={resource.content} />;
  }
  if (resource.resource_type === "quiz") {
    return <QuizView content={resource.content} />;
  }
  if (resource.resource_type === "code_case") {
    return <CodeView content={resource.content} />;
  }
  if (resource.resource_type === "video" || resource.resource_type === "animation") {
    return <StoryboardView content={resource.content} />;
  }
  // document, reading, and default
  return <MarkdownView content={resource.content} title={resource.title} />;
}
