import { useState } from "react";
import { apiPost, getFriendlyError } from "../../api/client";

interface QuizQuestion {
  id: number;
  topic: string;
  difficulty: number;
  dimension_test: string;
  question: string;
  options: string[];
  answer: string;
  explanation: string;
}

interface PerQuestionResult {
  question: string;
  user_answer: string;
  correct_answer: string;
  is_correct: boolean;
  explanation: string;
  dimension_test: string;
  difficulty: number;
}

interface QuizSession {
  knowledge_point: string;
  questions: QuizQuestion[];
  answers: Record<number, string>;
  correct_count: number;
  wrong_count: number;
  status: string;
  per_question: PerQuestionResult[];
  dimension_snapshot: Record<string, string>;
}

interface LastFeedback {
  is_correct: boolean;
  correct_answer: string;
  explanation: string;
}

interface ResourceRecommendation {
  knowledge_point: string;
  recommended_types: string[];
  reason: string;
  existing_resources: Array<{ id: string; title: string; resource_type: string }>;
}

interface PostQuizResult {
  quiz_pending: false;
  quiz_result: {
    accuracy: number;
    correct: number;
    total: number;
    per_question: PerQuestionResult[];
  };
  updated_dimension: Record<string, string> | null;
  dimension_change: Record<string, { from: string; to: string }>;
  last_answer_feedback: LastFeedback | null;
  resource_recommendation: ResourceRecommendation;
  next_steps: string[];
}

interface Props {
  question: QuizQuestion;
  quizSession: QuizSession;
  knowledgePoint: string;
  conversationId: string | null;
  onComplete: (result: PostQuizResult) => void;
  onGenerateResource?: (knowledgePoint: string, resourceType: string) => void;
}

const DIM_LABELS: Record<string, string> = {
  mastery: "掌握度",
  application: "应用力",
  memory: "记忆力",
  understanding: "理解力",
};

const DIFFICULTY_LABELS: Record<number, string> = {
  1: "基础",
  2: "中等",
  3: "进阶",
};

const TYPE_LABELS: Record<string, string> = {
  document: "文档",
  mindmap: "思维导图",
  quiz: "测验",
  reading: "阅读",
  video: "视频",
  animation: "动画",
  code_case: "代码实操",
  flowchart: "流程图",
};

type Phase = "quiz" | "analysis";

export function PostQuizPanel({
  question,
  quizSession,
  knowledgePoint,
  conversationId,
  onComplete,
  onGenerateResource,
}: Props) {
  const [currentQuestion, setCurrentQuestion] = useState<QuizQuestion>(question);
  const [session, setSession] = useState<QuizSession>(quizSession);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questionCount, setQuestionCount] = useState(1);
  const [phase, setPhase] = useState<Phase>("quiz");
  const [lastFeedback, setLastFeedback] = useState<LastFeedback | null>(null);
  const [finalResult, setFinalResult] = useState<PostQuizResult | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [correctSoFar, setCorrectSoFar] = useState(0);

  const handleSubmit = async (answer: string) => {
    setSubmitting(true);
    setError(null);
    setLastFeedback(null);
    try {
      const res = await apiPost<{
        quiz_pending?: boolean;
        question?: QuizQuestion;
        quiz_session?: QuizSession;
        last_answer_feedback?: LastFeedback;
        quiz_result?: PostQuizResult["quiz_result"];
        updated_dimension?: Record<string, string> | null;
        dimension_change?: Record<string, { from: string; to: string }>;
        resource_recommendation?: ResourceRecommendation;
        next_steps?: string[];
      }>("/learning/chat/post-quiz-next", {
        answer,
        quiz_session: session,
        knowledge_point: knowledgePoint,
        conversation_id: conversationId,
      });

      // Track per-question feedback
      const feedback = res.last_answer_feedback || null;
      setLastFeedback(feedback);
      setAnsweredCount((c) => c + 1);
      if (feedback?.is_correct) {
        setCorrectSoFar((c) => c + 1);
      }

      if (res.quiz_pending) {
        // Next question
        const nextQ = res.question!;
        const nextSession = res.quiz_session!;
        setCurrentQuestion(nextQ);
        setSession(nextSession);
        setSelected(null);
        setQuestionCount((c) => c + 1);
      } else {
        // Quiz complete — transition to analysis phase
        const result: PostQuizResult = {
          quiz_pending: false,
          quiz_result: res.quiz_result!,
          updated_dimension: res.updated_dimension || null,
          dimension_change: res.dimension_change || {},
          last_answer_feedback: feedback,
          resource_recommendation: res.resource_recommendation!,
          next_steps: res.next_steps || [],
        };
        setFinalResult(result);
        setPhase("analysis");
        onComplete(result);
      }
    } catch (e) {
      setError(e instanceof Error ? getFriendlyError(e.message) : "提交失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = () => handleSubmit("skip");

  // ── Phase: Quiz ──────────────────────────────────────────────
  if (phase === "quiz") {
    return (
      <div className="post-quiz-panel">
        <div className="post-quiz-header">
          <span className="post-quiz-label">课后练习</span>
          <span className="post-quiz-kp">{knowledgePoint}</span>
          <span className="post-quiz-count">第 {questionCount} 题 / 共 5 题</span>
        </div>

        {/* Progress bar */}
        <div className="post-quiz-progress">
          <div className="post-quiz-progress-bar">
            <div
              className="post-quiz-progress-fill"
              style={{ width: `${(answeredCount / 5) * 100}%` }}
            />
          </div>
          <span className="post-quiz-progress-text">
            {answeredCount > 0 && `${correctSoFar}/${answeredCount} 正确`}
          </span>
        </div>

        {/* Last feedback */}
        {lastFeedback && (
          <div className={`post-quiz-feedback ${lastFeedback.is_correct ? "correct" : "wrong"}`}>
            {lastFeedback.is_correct ? "回答正确!" : (
              <>
                回答错误，正确答案是 <strong>{lastFeedback.correct_answer}</strong>
              </>
            )}
            {lastFeedback.explanation && (
              <p className="post-quiz-feedback-explain">{lastFeedback.explanation}</p>
            )}
          </div>
        )}

        {/* Question */}
        <div className="post-quiz-question">
          <div className="post-quiz-q-header">
            <span className="post-quiz-q-diff">{DIFFICULTY_LABELS[currentQuestion.difficulty] || "基础"}</span>
            <span className="post-quiz-q-dim">{DIM_LABELS[currentQuestion.dimension_test] || currentQuestion.dimension_test}</span>
          </div>
          <p className="post-quiz-q-text">{currentQuestion.question}</p>
          <div className="post-quiz-options">
            {currentQuestion.options.map((opt, i) => {
              const letter = String.fromCharCode(65 + i);
              const isSelected = selected === letter;
              return (
                <button
                  key={i}
                  className={`post-quiz-option ${isSelected ? "selected" : ""}`}
                  onClick={() => setSelected(letter)}
                  disabled={submitting}
                  type="button"
                >
                  <span className="post-quiz-option-letter">{letter}</span>
                  <span>{opt}</span>
                </button>
              );
            })}
          </div>
        </div>

        {error && <div className="post-quiz-error">{error}</div>}

        <div className="post-quiz-actions">
          <button
            className="post-quiz-submit"
            onClick={() => selected && handleSubmit(selected)}
            disabled={!selected || submitting}
            type="button"
          >
            {submitting ? "评估中..." : "确认"}
          </button>
          <button
            className="post-quiz-skip"
            onClick={handleSkip}
            disabled={submitting}
            type="button"
          >
            跳过
          </button>
        </div>
      </div>
    );
  }

  // ── Phase: Analysis ──────────────────────────────────────────
  if (phase === "analysis" && finalResult) {
    const { quiz_result, dimension_change, resource_recommendation, next_steps } = finalResult;
    const dimBefore = session.dimension_snapshot || {};

    return (
      <div className="post-quiz-panel post-quiz-analysis">
        {/* Score summary */}
        <div className="post-quiz-score">
          <div className="post-quiz-score-circle">
            <span className="post-quiz-score-pct">{Math.round(quiz_result.accuracy * 100)}%</span>
            <span className="post-quiz-score-label">正确率</span>
          </div>
          <div className="post-quiz-score-detail">
            <span>{quiz_result.correct} / {quiz_result.total} 正确</span>
          </div>
        </div>

        {/* Dimension change */}
        {Object.keys(dimension_change).length > 0 && (
          <div className="post-quiz-dim-change">
            <h4>知识点维度变化</h4>
            <div className="post-quiz-dim-grid">
              {Object.entries(dimension_change).map(([dim, change]) => (
                <div key={dim} className="post-quiz-dim-item">
                  <span className="post-quiz-dim-name">{DIM_LABELS[dim] || dim}</span>
                  <span className={`post-quiz-dim-from ${change.from}`}>{change.from === "high" ? "高" : change.from === "mid" ? "中" : "低"}</span>
                  <span className="post-quiz-dim-arrow">→</span>
                  <span className={`post-quiz-dim-to ${change.to}`}>{change.to === "high" ? "高" : change.to === "mid" ? "中" : "低"}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Per-question analysis */}
        <div className="post-quiz-analysis-list">
          <h4>答题解析</h4>
          {quiz_result.per_question.map((pq, idx) => (
            <details key={idx} className={`post-quiz-analysis-item ${pq.is_correct ? "correct" : "wrong"}`}>
              <summary className="post-quiz-analysis-header">
                <span className="post-quiz-analysis-idx">第 {idx + 1} 题</span>
                <span className="post-quiz-analysis-dim">{DIM_LABELS[pq.dimension_test] || pq.dimension_test}</span>
                <span className={`post-quiz-analysis-result ${pq.is_correct ? "correct" : "wrong"}`}>
                  {pq.is_correct ? "正确" : "错误"}
                </span>
              </summary>
              <div className="post-quiz-analysis-body">
                <p className="post-quiz-analysis-q">{pq.question}</p>
                <div className="post-quiz-analysis-answers">
                  <span>你的答案：<strong>{pq.user_answer}</strong></span>
                  {!pq.is_correct && <span>正确答案：<strong>{pq.correct_answer}</strong></span>}
                </div>
                {pq.explanation && (
                  <p className="post-quiz-analysis-explain">{pq.explanation}</p>
                )}
              </div>
            </details>
          ))}
        </div>

        {/* Resource recommendation */}
        <div className="post-quiz-resources">
          <h4>推荐学习资源</h4>
          <p className="post-quiz-resources-reason">{resource_recommendation.reason}</p>

          {resource_recommendation.existing_resources.length > 0 && (
            <div className="post-quiz-existing">
              <span className="post-quiz-existing-label">已有资源：</span>
              {resource_recommendation.existing_resources.map((r) => (
                <span key={r.id} className="post-quiz-existing-tag">
                  {TYPE_LABELS[r.resource_type] || r.resource_type}: {r.title}
                </span>
              ))}
            </div>
          )}

          <div className="post-quiz-resource-types">
            {resource_recommendation.recommended_types.map((t) => (
              <button
                key={t}
                type="button"
                className="post-quiz-resource-btn"
                onClick={() => onGenerateResource?.(knowledgePoint, t)}
              >
                {TYPE_LABELS[t] || t}
              </button>
            ))}
          </div>
        </div>

        {/* Next steps */}
        {next_steps.length > 0 && (
          <div className="post-quiz-next-steps">
            <h4>下一步学习建议</h4>
            <ul>
              {next_steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return null;
}
