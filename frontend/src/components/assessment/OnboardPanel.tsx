import { useState, useEffect, useCallback, useRef } from "react";
import { ChevronDown, ChevronRight, CheckCircle, XCircle, Lightbulb } from "lucide-react";
import { apiPost } from "../../api/client";
import { useAppContext } from "../../context/AppContext";

const STORAGE_KEY = "autolearning_onboard";

interface QuizQuestion {
  id: number;
  topic: string;
  difficulty: number;
  question: string;
  options: string[];
  answer: string;
  explanation: string;
}

interface QuizData {
  knowledge_points: string[];
  questions: QuizQuestion[];
}

interface OnboardState {
  step: "form" | "quiz" | "result";
  major: string;
  grade: string;
  goal: string;
  subject: string;
  quiz: QuizData | null;
  answers: Record<number, string>;
  result: Record<string, unknown> | null;
}

function loadState(): OnboardState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return null;
}

function saveState(state: OnboardState) {
  // Strip correct answers before persisting to prevent information leak
  const sanitized = state.quiz
    ? {
        ...state,
        quiz: {
          ...state.quiz,
          questions: state.quiz.questions.map(({ answer: _, ...rest }) => rest),
        },
      }
    : state;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitized));
}

function clearState() {
  localStorage.removeItem(STORAGE_KEY);
}

const DEFAULT_STATE: OnboardState = {
  step: "form",
  major: "",
  grade: "",
  goal: "",
  subject: "数据结构",
  quiz: null,
  answers: {},
  result: null,
};

export function OnboardPanel({ onComplete }: { onComplete?: () => void }) {
  const { state: appState, dispatch } = useAppContext();
  const [form, setForm] = useState<OnboardState>(() => loadState() || DEFAULT_STATE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  // Persist to localStorage on every change
  useEffect(() => {
    saveState(form);
  }, [form]);

  const userId = appState.user?.id;

  const handleGenerateQuiz = useCallback(async (quick = false) => {
    if (!userId || !form.major || !form.grade || !form.goal) return;
    setLoading(true);
    setError(null);
    try {
      const endpoint = quick ? "/learning/onboard/quick" : "/learning/onboard";
      const res = await apiPost<{ quiz: QuizData }>(endpoint, {
        major: form.major,
        grade: form.grade,
        goal: form.goal,
        subject: form.subject,
        ...(quick ? {} : { num_questions: 8 }),
      });
      setForm((f) => ({ ...f, step: "quiz", quiz: res.quiz, answers: {} }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "生成诊断题失败");
    } finally {
      setLoading(false);
    }
  }, [userId, form.major, form.grade, form.goal, form.subject]);

  const handleSubmitAnswers = useCallback(async () => {
    if (!userId || !form.quiz || submittingRef.current) return;
    submittingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<{ profile: Record<string, unknown>; assessment: Record<string, unknown>; quiz_result: Record<string, unknown> }>(
        "/learning/onboard/submit",
        {
          major: form.major,
          grade: form.grade,
          goal: form.goal,
          subject: form.subject,
          quiz: form.quiz,
          answers: form.answers,
        }
      );
      // Update global profile
      const serverProfile = res.profile as unknown as import("../../types/baseline").StudentProfile;
      dispatch({ type: "SET_PROFILE", payload: serverProfile });
      // Only mark diagnostic completed if server confirmed the profile was persisted
      const profileScore = (res.profile as Record<string, unknown>)?.completeness_score;
      if (userId && typeof profileScore === "number" && profileScore > 0.5) {
        localStorage.setItem(`diagnostic_completed_${userId}`, "1");
      }
      setForm((f) => ({ ...f, step: "result", result: res }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交答案失败");
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  }, [userId, form.quiz, form.major, form.grade, form.goal, form.subject, form.answers, dispatch]);

  const handleAnswer = (qid: number, ans: string) => {
    setForm((f) => ({ ...f, answers: { ...f.answers, [qid]: ans } }));
  };

  const handleRestart = () => {
    clearState();
    setForm(DEFAULT_STATE);
  };

  const handleFinish = () => {
    clearState();
    onComplete?.();
  };

  // ── Step: Form ────────────────────────────────────────────────────
  if (form.step === "form") {
    return (
      <div className="onboard-panel">
        <h3>初始诊断</h3>
        <p className="onboard-hint">填写基本信息，系统将生成诊断测验来了解你的知识水平。</p>

        <div className="onboard-field">
          <label>专业</label>
          <input value={form.major} onChange={(e) => setForm((f) => ({ ...f, major: e.target.value }))} placeholder="如：计算机科学与技术" />
        </div>
        <div className="onboard-field">
          <label>年级</label>
          <input value={form.grade} onChange={(e) => setForm((f) => ({ ...f, grade: e.target.value }))} placeholder="如：大二" />
        </div>
        <div className="onboard-field">
          <label>学习目标</label>
          <input value={form.goal} onChange={(e) => setForm((f) => ({ ...f, goal: e.target.value }))} placeholder="如：两周内掌握数据结构基础" />
        </div>
        <div className="onboard-field">
          <label>课程</label>
          <input value={form.subject} onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))} placeholder="数据结构" />
        </div>

        {error && <div className="onboard-error">{error}</div>}

        <div style={{ display: "flex", gap: 8 }}>
          <button className="onboard-btn" onClick={() => handleGenerateQuiz(false)} disabled={loading || !form.major || !form.grade || !form.goal} style={{ flex: 1 }}>
            {loading ? "正在生成题目..." : "完整诊断 (8题)"}
          </button>
          <button className="onboard-btn" onClick={() => handleGenerateQuiz(true)} disabled={loading || !form.major || !form.grade || !form.goal} style={{ flex: 1, opacity: 0.85 }}>
            {loading ? "正在生成题目..." : "快速定位 (3题)"}
          </button>
        </div>
      </div>
    );
  }

  // ── Step: Quiz ────────────────────────────────────────────────────
  if (form.step === "quiz") {
    if (!form.quiz) {
      // Corrupted state — reset to form
      clearState();
      setForm(DEFAULT_STATE);
      return null;
    }
    const answered = Object.keys(form.answers).length;
    const total = form.quiz.questions.length;
    return (
      <div className="onboard-panel">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <button className="onboard-btn" onClick={() => setForm((f) => ({ ...f, step: "form", quiz: null, answers: {} }))} style={{ flex: 0, padding: "4px 12px", fontSize: 13 }}>← 返回修改</button>
          <h3 style={{ margin: 0 }}>诊断测验</h3>
        </div>
        <p className="onboard-hint">共 {total} 题，已答 {answered} 题。知识点：{form.quiz.knowledge_points.join("、")}</p>

        {form.quiz.questions.map((q) => (
          <div key={q.id} className="onboard-question">
            <div className="onboard-q-header">
              <span className="onboard-q-topic">{q.topic}</span>
              <span className="onboard-q-difficulty">难度 {q.difficulty}/3</span>
            </div>
            <p className="onboard-q-text">{q.question}</p>
            <div className="onboard-options">
              {q.options.map((opt, i) => {
                const letter = String.fromCharCode(65 + i);
                const selected = form.answers[q.id] === letter;
                return (
                  <button
                    key={i}
                    className={`onboard-option ${selected ? "onboard-option-selected" : ""}`}
                    onClick={() => handleAnswer(q.id, letter)}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        {error && <div className="onboard-error">{error}</div>}

        <button className="onboard-btn" onClick={handleSubmitAnswers} disabled={loading || answered < total}>
          {loading ? "正在评估..." : "提交答案"}
        </button>
      </div>
    );
  }

  // ── Step: Result ──────────────────────────────────────────────────
  if (form.step === "result") {
    if (!form.result) {
      clearState();
      setForm(DEFAULT_STATE);
      return null;
    }
    const assessment = form.result.assessment as Record<string, unknown> | undefined;
    const quizResult = form.result.quiz_result as Record<string, unknown> | undefined;
    const summaryText = typeof assessment?.summary === "string" ? assessment.summary : "";
    const answerDetails = (quizResult?.answer_details as Record<string, unknown>[]) || [];
    const topicDimensions = (assessment?.topic_dimensions as Record<string, Record<string, string>>) || {};
    const weakPoints = (assessment?.weak_points as Record<string, unknown>[]) || [];
    const reviewRecs = (assessment?.review_recommendations as Record<string, unknown>[]) || [];
    const nextSteps = (assessment?.next_steps as string[]) || [];
    const archetypeId = typeof assessment?.matched_archetype === "string" ? assessment.matched_archetype : "";
    const archetypeHint = typeof assessment?.archetype_hint === "string" ? assessment.archetype_hint : "";

    // Profile overview data
    const profileData = form.result.profile as Record<string, unknown> | undefined;
    const learningStyle = assessment?.learning_style as Record<string, unknown> | undefined;
    const learningStyleAnalysis = typeof learningStyle?.analysis === "string" ? learningStyle.analysis : "";
    const learningStylePrimary = typeof learningStyle?.primary_style === "string" ? learningStyle.primary_style : "";
    const cognitiveProfile = profileData?.cognitive_profile as Record<string, string> | undefined;
    const learningGoal = profileData?.learning_goal as Record<string, string> | undefined;
    const learningPref = profileData?.learning_preference as Record<string, unknown> | undefined;
    const prefStyle = typeof learningPref?.learning_style === "string" ? learningPref.learning_style : "";
    const prefDifficulty = typeof learningPref?.difficulty_preference === "string" ? learningPref.difficulty_preference : "";

    const dimLabel: Record<string, string> = { mastery: "掌握度", application: "应用力", memory: "记忆力", understanding: "理解力" };
    const dimColor: Record<string, string> = { high: "#22c55e", mid: "#f59e0b", low: "#ef4444" };

    return (
      <div className="onboard-panel onboard-result">
        <h3>诊断完成</h3>

        {/* Overall stats */}
        <div className="onboard-result-summary">
          <div className="onboard-result-stat">
            <span>正确率</span>
            <strong>{Math.round(((quizResult?.accuracy as number) || 0) * 100)}%</strong>
          </div>
          <div className="onboard-result-stat">
            <span>掌握度</span>
            <strong>{Math.round(((assessment?.mastery_score as number) || 0) * 100)}%</strong>
          </div>
          <div className="onboard-result-stat">
            <span>置信度</span>
            <strong>{Math.round(((assessment?.confidence as number) || 0) * 100)}%</strong>
          </div>
        </div>

        {summaryText && <p className="onboard-result-text">{summaryText}</p>}

        {/* Per-question answer analysis */}
        {answerDetails.length > 0 && (
          <details className="onboard-section">
            <summary className="onboard-section-title">答题解析 ({(quizResult?.correct as number) || 0}/{(quizResult?.total as number) || 0} 正确)</summary>
            <div className="onboard-answer-list">
              {answerDetails.map((ad, idx) => (
                <div key={ad.id as number} className={`onboard-answer-item ${ad.is_correct ? "onboard-answer-correct" : "onboard-answer-wrong"}`}>
                  <div className="onboard-answer-header">
                    {ad.is_correct ? <CheckCircle size={16} className="onboard-icon-correct" /> : <XCircle size={16} className="onboard-icon-wrong" />}
                    <span className="onboard-answer-idx">第 {idx + 1} 题</span>
                    <span className="onboard-answer-topic">{ad.topic as string}</span>
                    <span className="onboard-answer-dim">{dimLabel[(ad.dimension_test as string)] || (ad.dimension_test as string)}</span>
                  </div>
                  <p className="onboard-answer-q">{ad.question as string}</p>
                  <div className="onboard-answer-choices">
                    {(ad.options as string[]).map((opt, oi) => {
                      const letter = String.fromCharCode(65 + oi);
                      const isUser = letter === (ad.user_answer as string);
                      const isCorrect = letter === (ad.correct_answer as string);
                      let cls = "onboard-choice";
                      if (isCorrect) cls += " onboard-choice-correct";
                      else if (isUser && !isCorrect) cls += " onboard-choice-wrong";
                      return <div key={oi} className={cls}>{opt}</div>;
                    })}
                  </div>
                  {!ad.is_correct && (
                    <div className="onboard-answer-sentence">
                      你的答案 <strong>{ad.user_answer as string}</strong>，正确答案 <strong>{ad.correct_answer as string}</strong>
                    </div>
                  )}
                  {(ad.explanation as string) && (
                    <div className="onboard-answer-explanation">
                      <Lightbulb size={14} /> {ad.explanation as string}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}

        {/* Per-topic dimension breakdown */}
        {Object.keys(topicDimensions).length > 0 && (
          <details className="onboard-section" open>
            <summary className="onboard-section-title">知识画像维度</summary>
            <div className="onboard-dim-list">
              {Object.entries(topicDimensions).map(([topic, dims]) => (
                <div key={topic} className="onboard-dim-item">
                  <span className="onboard-dim-topic">{topic}</span>
                  <div className="onboard-dim-bars">
                    {Object.entries(dims).map(([dim, level]) => (
                      <div key={dim} className="onboard-dim-bar-row">
                        <span className="onboard-dim-label">{dimLabel[dim] || dim}</span>
                        <div className="onboard-dim-track">
                          <div className="onboard-dim-fill" style={{ width: level === "high" ? "100%" : level === "mid" ? "60%" : "25%", backgroundColor: dimColor[level] || "#94a3b8" }} />
                        </div>
                        <span className="onboard-dim-level">{level === "high" ? "高" : level === "mid" ? "中" : "低"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </details>
        )}

        {/* Weak points */}
        {weakPoints.length > 0 && (
          <details className="onboard-section" open>
            <summary className="onboard-section-title">薄弱知识点</summary>
            <div className="onboard-weak-list">
              {weakPoints.map((wp, i) => (
                <div key={i} className="onboard-weak-item">
                  <span className="onboard-weak-topic">{wp.topic as string}</span>
                  <span className="onboard-weak-severity">{wp.severity as string}</span>
                  <span className="onboard-weak-suggestion">{wp.suggestion as string}</span>
                </div>
              ))}
            </div>
          </details>
        )}

        {/* Initial profile overview */}
        {(cognitiveProfile || learningGoal || prefStyle) && (
          <details className="onboard-section" open>
            <summary className="onboard-section-title">初始画像概览</summary>
            <div className="onboard-profile-overview">
              {learningGoal?.current_goal && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">学习目标</span>
                  <span className="onboard-profile-value">{learningGoal.current_goal}</span>
                </div>
              )}
              {learningGoal?.target_course && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">目标课程</span>
                  <span className="onboard-profile-value">{learningGoal.target_course}</span>
                </div>
              )}
              {prefStyle && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">学习风格</span>
                  <span className="onboard-profile-value">{prefStyle}</span>
                </div>
              )}
              {prefDifficulty && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">难度偏好</span>
                  <span className="onboard-profile-value">{prefDifficulty}</span>
                </div>
              )}
              {cognitiveProfile?.cognitive_style && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">认知风格</span>
                  <span className="onboard-profile-value">{cognitiveProfile.cognitive_style}</span>
                </div>
              )}
              {cognitiveProfile?.abstract_understanding && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">抽象理解</span>
                  <span className="onboard-profile-value">{dimLabel[cognitiveProfile.abstract_understanding] || cognitiveProfile.abstract_understanding}</span>
                </div>
              )}
              {cognitiveProfile?.hands_on_ability && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">动手能力</span>
                  <span className="onboard-profile-value">{dimLabel[cognitiveProfile.hands_on_ability] || cognitiveProfile.hands_on_ability}</span>
                </div>
              )}
              {cognitiveProfile?.reading_patience && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">阅读耐心</span>
                  <span className="onboard-profile-value">{dimLabel[cognitiveProfile.reading_patience] || cognitiveProfile.reading_patience}</span>
                </div>
              )}
            </div>
          </details>
        )}

        {/* Profile basis / reasoning */}
        {(learningStyleAnalysis || archetypeHint) && (
          <details className="onboard-section" open>
            <summary className="onboard-section-title">画像依据</summary>
            <div className="onboard-profile-basis">
              {learningStylePrimary && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">主要学习风格</span>
                  <span className="onboard-profile-value">{learningStylePrimary}</span>
                </div>
              )}
              {learningStyleAnalysis && (
                <p className="onboard-profile-analysis">{learningStyleAnalysis}</p>
              )}
              {archetypeId && (
                <div className="onboard-profile-row">
                  <span className="onboard-profile-label">匹配学习者类型</span>
                  <span className="onboard-profile-value">{archetypeId}</span>
                </div>
              )}
              {archetypeHint && (
                <p className="onboard-profile-analysis">{archetypeHint}</p>
              )}
            </div>
          </details>
        )}

        {/* Review recommendations */}
        {reviewRecs.length > 0 && (
          <details className="onboard-section">
            <summary className="onboard-section-title">复习建议</summary>
            <div className="onboard-rec-list">
              {reviewRecs.map((rec, i) => (
                <div key={i} className="onboard-rec-item">
                  <span className="onboard-rec-priority">#{rec.priority as number}</span>
                  <span className="onboard-rec-topic">{rec.topic as string}</span>
                  <span className="onboard-rec-reason">{rec.reason as string}</span>
                </div>
              ))}
            </div>
          </details>
        )}

        {/* Next steps */}
        {nextSteps.length > 0 && (
          <div className="onboard-next-steps">
            <strong>下一步</strong>
            <ul>
              {nextSteps.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}

        <p className="onboard-hint">初始评估已生成。继续学习后评估会自动优化。</p>
        <button className="onboard-btn" onClick={handleFinish}>开始学习</button>
        {weakPoints.length > 0 && (
          <p className="onboard-hint" style={{ marginTop: 8 }}>
            建议从薄弱点「{weakPoints[0]?.topic as string || ""}」开始学习
          </p>
        )}
      </div>
    );
  }

  return null;
}
