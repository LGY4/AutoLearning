import { useState, useEffect, useCallback } from "react";
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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
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
        user_id: userId,
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
    if (!userId || !form.quiz) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<{ profile: Record<string, unknown>; assessment: Record<string, unknown>; quiz_result: Record<string, unknown> }>(
        "/learning/onboard/submit",
        {
          user_id: userId,
          major: form.major,
          grade: form.grade,
          goal: form.goal,
          subject: form.subject,
          quiz: form.quiz,
          answers: form.answers,
        }
      );
      // Update global profile
      dispatch({ type: "SET_PROFILE", payload: res.profile as unknown as import("../../types/baseline").StudentProfile });
      setForm((f) => ({ ...f, step: "result", result: res }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交答案失败");
    } finally {
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
  if (form.step === "quiz" && form.quiz) {
    const answered = Object.keys(form.answers).length;
    const total = form.quiz.questions.length;
    return (
      <div className="onboard-panel">
        <h3>诊断测验</h3>
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
  if (form.step === "result" && form.result) {
    const assessment = form.result.assessment as Record<string, unknown> | undefined;
    const quizResult = form.result.quiz_result as Record<string, unknown> | undefined;
    const summaryText = typeof assessment?.summary === "string" ? assessment.summary : "";
    return (
      <div className="onboard-panel onboard-result">
        <h3>诊断完成</h3>
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
        <p className="onboard-hint">初始评估已生成。继续学习后评估会自动优化。</p>
        <button className="onboard-btn" onClick={handleFinish}>开始学习</button>
      </div>
    );
  }

  return null;
}
