import { useState } from "react";
import { apiPost } from "../../api/client";
import type { IntentResult } from "./ChatMessage";

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

interface QuizSession {
  knowledge_point: string;
  original_question: string;
  is_known_kp: boolean;
  questions: QuizQuestion[];
  answers: Record<number, string>;
  correct_count: number;
  wrong_count: number;
  status: string;
}

interface Props {
  question: QuizQuestion;
  quizSession: QuizSession;
  knowledgePoint: string;
  originalQuestion: string;
  conversationId: string | null;
  isKnownKp: boolean;
  onComplete: (result: IntentResult) => void;
}

const DIM_LABELS: Record<string, string> = {
  mastery: "基础概念",
  understanding: "理解应用",
  application: "综合分析",
  memory: "记忆巩固",
};

const DIFFICULTY_LABELS: Record<number, string> = {
  1: "基础",
  2: "中等",
  3: "进阶",
};

export function InlineQuiz({
  question,
  quizSession,
  knowledgePoint,
  originalQuestion,
  conversationId,
  isKnownKp,
  onComplete,
}: Props) {
  const [currentQuestion, setCurrentQuestion] = useState<QuizQuestion>(question);
  const [session, setSession] = useState<QuizSession>(quizSession);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questionCount, setQuestionCount] = useState(1);

  const handleSubmit = async (answer: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiPost<IntentResult>("/learning/chat/quiz-next", {
        answer,
        quiz_session: session,
        knowledge_point: knowledgePoint,
        original_question: originalQuestion,
        conversation_id: conversationId,
      });

      if (res.result.quiz_pending) {
        // Next question
        const nextQ = res.result.question as QuizQuestion;
        const nextSession = res.result.quiz_session as QuizSession;
        setCurrentQuestion(nextQ);
        setSession(nextSession);
        setSelected(null);
        setQuestionCount((c) => c + 1);
      } else {
        // Quiz complete
        onComplete(res);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = async () => {
    await handleSubmit("skip");
  };

  return (
    <div className="inline-quiz">
      <div className="inline-quiz-header">
        <span className="inline-quiz-label">
          {isKnownKp ? "能力检测" : "快速诊断"}
        </span>
        <span className="inline-quiz-kp">{knowledgePoint}</span>
        <span className="inline-quiz-count">第 {questionCount} 题</span>
      </div>
      <p className="inline-quiz-hint">
        {isKnownKp
          ? `检测你对「${knowledgePoint}」的掌握程度是否有所提升。`
          : `在回答你的问题之前，让我先了解一下你对「${knowledgePoint}」的掌握程度。`}
      </p>

      <div className="inline-quiz-question">
        <div className="inline-quiz-q-header">
          <span className="inline-quiz-q-num">
            {DIFFICULTY_LABELS[currentQuestion.difficulty] || "基础"}
          </span>
          <span className="inline-quiz-q-dim">
            {DIM_LABELS[currentQuestion.dimension_test] || currentQuestion.dimension_test}
          </span>
        </div>
        <p className="inline-quiz-q-text">{currentQuestion.question}</p>
        <div className="inline-quiz-options">
          {currentQuestion.options.map((opt, i) => {
            const letter = String.fromCharCode(65 + i);
            const isSelected = selected === letter;
            return (
              <button
                key={i}
                className={`inline-quiz-option ${isSelected ? "selected" : ""}`}
                onClick={() => setSelected(letter)}
                disabled={submitting}
                type="button"
              >
                <span className="inline-quiz-option-letter">{letter}</span>
                <span>{opt}</span>
              </button>
            );
          })}
        </div>
      </div>

      {error && <div className="inline-quiz-error">{error}</div>}

      <div className="inline-quiz-actions">
        <button
          className="inline-quiz-submit"
          onClick={() => selected && handleSubmit(selected)}
          disabled={!selected || submitting}
          type="button"
        >
          {submitting ? "评估中..." : "确认"}
        </button>
        <button
          className="inline-quiz-skip"
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
