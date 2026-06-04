import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiGet, apiPost, apiDelete, getFriendlyError } from "../api/client";
import { useAppContext } from "../context/AppContext";
import { useRecordLearning } from "../hooks/useRecordLearning";
import { Spinner } from "../components/common/Spinner";

interface Question {
  id: string;
  question_type: string;
  stem: string;
  options?: string[];
  answer?: string;
  explanation?: string;
  difficulty_level?: string;
  knowledge_point?: string;
}

interface GradeResult {
  score: number;
  is_correct: boolean | null;
  feedback: string;
  key_points_hit?: string[];
  key_points_missed?: string[];
  _grading_method?: string;
}

const TYPE_LABELS: Record<string, string> = {
  choice: "选择题",
  blank: "填空题",
  short_answer: "简答题",
  programming: "编程题",
  case_analysis: "案例分析",
};

export function PracticePage() {
  const { state, dispatch } = useAppContext();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const recordLearning = useRecordLearning();
  const resultsSavedRef = useRef(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [userAnswer, setUserAnswer] = useState("");
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [gradeResult, setGradeResult] = useState<GradeResult | null>(null);
  const [grading, setGrading] = useState(false);
  const [answers, setAnswers] = useState<Array<{ questionId: string; correct: boolean; score: number }>>([]);
  const [showSummary, setShowSummary] = useState(false);
  const [filterType, setFilterType] = useState<string>("");
  const [filterDifficulty, setFilterDifficulty] = useState<string>("");
  const [filterKP, setFilterKP] = useState<string>(() => searchParams.get("knowledge_point") || "");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<"practice" | "manage">("practice");
  const [selectedQuestionDetail, setSelectedQuestionDetail] = useState<Question | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Question management state
  const [manageQuestions, setManageQuestions] = useState<Question[]>([]);
  const [manageLoading, setManageLoading] = useState(false);
  const [createForm, setCreateForm] = useState({ question_type: "choice", stem: "", options: ["", "", "", ""], answer: "", explanation: "", knowledge_point: "", difficulty_level: "medium" });
  const [creating, setCreating] = useState(false);
  const [manageError, setManageError] = useState<string | null>(null);

  const loadManageQuestions = useCallback(async () => {
    setManageLoading(true);
    setManageError(null);
    try {
      const res = await apiGet<{ questions: Question[]; total: number }>("/resources/questions/list?page_size=50");
      setManageQuestions(res.questions ?? []);
    } catch (e) {
      setManageError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setManageLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "manage") loadManageQuestions();
  }, [tab, loadManageQuestions]);

  const handleCreateQuestion = useCallback(async () => {
    if (!createForm.stem.trim() || !createForm.answer.trim()) return;
    setCreating(true);
    setManageError(null);
    try {
      await apiPost("/resources/questions", {
        question_type: createForm.question_type,
        stem: createForm.stem,
        options: createForm.question_type === "choice" ? createForm.options.filter((o) => o.trim()) : [],
        answer: createForm.answer,
        explanation: createForm.explanation,
        knowledge_point: createForm.knowledge_point,
        difficulty_level: createForm.difficulty_level,
        subject: state.profile?.learning_goal?.target_course || "通用",
      });
      setCreateForm({ question_type: "choice", stem: "", options: ["", "", "", ""], answer: "", explanation: "", knowledge_point: "", difficulty_level: "medium" });
      loadManageQuestions();
    } catch (e) {
      setManageError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }, [createForm, state.profile, loadManageQuestions]);

  const handleDeleteQuestion = useCallback(async (id: string) => {
    try {
      await apiDelete(`/resources/questions/${id}`);
      setManageQuestions((prev) => prev.filter((q) => q.id !== id));
    } catch (e) {
      setManageError(e instanceof Error ? e.message : "删除失败");
    }
  }, []);

  const handleViewQuestionDetail = useCallback(async (id: string) => {
    setDetailLoading(true);
    try {
      const detail = await apiGet<Question>(`/resources/questions/${id}`);
      setSelectedQuestionDetail(detail);
    } catch (e) {
      setManageError(e instanceof Error ? e.message : "加载题目详情失败");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab !== "practice") return;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams();
    if (filterType) params.set("question_type", filterType);
    if (filterDifficulty) params.set("difficulty", filterDifficulty);
    if (filterKP) params.set("knowledge_point", filterKP);
    params.set("page_size", "20");
    apiGet<{ questions: Question[]; total: number }>(`/resources/questions/list?${params}`)
      .then((res) => { setQuestions(res.questions ?? []); setLoadError(null); })
      .catch((err) => { setQuestions([]); setLoadError(err instanceof Error ? getFriendlyError(err.message) : "加载题目失败"); })
      .finally(() => setLoading(false));
  }, [tab, filterType, filterDifficulty, filterKP]);

  const currentQuestion = questions[currentIdx];

  const handleSubmit = useCallback(async () => {
    if (!currentQuestion || !state.user) return;
    const answer = currentQuestion.question_type === "choice" ? (selectedOption ?? "") : userAnswer.trim();
    if (!answer) return;

    setGrading(true);
    try {
      const result = await apiPost<GradeResult>("/resources/grade", {
        user_id: state.user.id,
        question_id: currentQuestion.id,
        question_type: currentQuestion.question_type,
        stem: currentQuestion.stem,
        standard_answer: currentQuestion.answer ?? "",
        user_answer: answer,
        explanation: currentQuestion.explanation,
        knowledge_point: currentQuestion.knowledge_point,
      });
      setGradeResult(result);
      setAnswers((prev) => [...prev, {
        questionId: currentQuestion.id,
        correct: result.is_correct === true,
        score: result.score,
      }]);
    } catch {
      setGradeResult({ score: 0, is_correct: null, feedback: "评分失败，请重试" });
    } finally {
      setGrading(false);
    }
  }, [currentQuestion, state.user, userAnswer, selectedOption]);

  const handleNext = useCallback(() => {
    setUserAnswer("");
    setSelectedOption(null);
    setGradeResult(null);
    if (currentIdx + 1 >= questions.length) {
      setShowSummary(true);
    } else {
      setCurrentIdx((prev) => prev + 1);
    }
  }, [currentIdx, questions.length]);

  const handleRestart = useCallback(() => {
    setCurrentIdx(0);
    setAnswers([]);
    setShowSummary(false);
    setUserAnswer("");
    setSelectedOption(null);
    setGradeResult(null);
    resultsSavedRef.current = false;
  }, []);

  const handleAutoGenerate = useCallback(async () => {
    const kp = filterKP.trim() || state.profile?.knowledge_profile?.weak_topics?.[0] || "";
    if (!kp) {
      setGenerateError("请输入知识点或系统需有薄弱知识点记录");
      return;
    }
    setGenerating(true);
    setGenerateError(null);
    try {
      await apiPost("/resources/questions/generate", {
        knowledge_point: kp,
        subject: state.profile?.learning_goal?.target_course || "通用",
        overall_level: state.profile?.knowledge_profile?.overall_level || "beginner",
      });
      // Reload questions
      const params = new URLSearchParams();
      if (filterType) params.set("question_type", filterType);
      if (filterDifficulty) params.set("difficulty", filterDifficulty);
      params.set("knowledge_point", kp);
      params.set("page_size", "20");
      const res = await apiGet<{ questions: Question[]; total: number }>(`/resources/questions/list?${params}`);
      setQuestions(res.questions ?? []);
      setFilterKP(kp);
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  }, [filterKP, filterType, filterDifficulty, state.profile]);

  if (loading && tab === "practice") return <div className="page-center"><Spinner /></div>;

  if (tab === "manage") {
    return (
      <div className="practice-page">
        <div className="practice-header">
          <h2>题库管理</h2>
          <button type="button" className="practice-btn-next" onClick={() => setTab("practice")}>返回练习</button>
        </div>

        {manageError && <div className="page-error">{manageError}</div>}

        {/* Create form */}
        <div className="practice-question" style={{ marginBottom: 24 }}>
          <h3>新建题目</h3>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <select value={createForm.question_type} onChange={(e) => setCreateForm((f) => ({ ...f, question_type: e.target.value }))}>
              <option value="choice">选择题</option>
              <option value="blank">填空题</option>
              <option value="short_answer">简答题</option>
              <option value="programming">编程题</option>
            </select>
            <select value={createForm.difficulty_level} onChange={(e) => setCreateForm((f) => ({ ...f, difficulty_level: e.target.value }))}>
              <option value="easy">简单</option>
              <option value="medium">中等</option>
              <option value="hard">困难</option>
            </select>
            <input placeholder="知识点" value={createForm.knowledge_point} onChange={(e) => setCreateForm((f) => ({ ...f, knowledge_point: e.target.value }))} style={{ flex: 1 }} />
          </div>
          <textarea className="practice-input" rows={2} placeholder="题干" value={createForm.stem} onChange={(e) => setCreateForm((f) => ({ ...f, stem: e.target.value }))} />
          {createForm.question_type === "choice" && (
            <div className="practice-options" style={{ marginTop: 8 }}>
              {createForm.options.map((opt, i) => (
                <input key={i} className="practice-input" placeholder={`选项 ${String.fromCharCode(65 + i)}`} value={opt} onChange={(e) => setCreateForm((f) => { const opts = [...f.options]; opts[i] = e.target.value; return { ...f, options: opts }; })} />
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input className="practice-input" placeholder="正确答案" value={createForm.answer} onChange={(e) => setCreateForm((f) => ({ ...f, answer: e.target.value }))} style={{ flex: 1 }} />
            <input className="practice-input" placeholder="解析（可选）" value={createForm.explanation} onChange={(e) => setCreateForm((f) => ({ ...f, explanation: e.target.value }))} style={{ flex: 2 }} />
          </div>
          <button type="button" className="practice-btn-submit" onClick={handleCreateQuestion} disabled={creating || !createForm.stem.trim() || !createForm.answer.trim()} style={{ marginTop: 8 }}>
            {creating ? "创建中..." : "创建题目"}
          </button>
        </div>

        {/* Question list */}
        {manageLoading ? <Spinner /> : (
          <div className="practice-summary-detail">
            {manageQuestions.map((q) => (
              <div key={q.id} className="practice-result-item" style={{ alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <span className="practice-type">{TYPE_LABELS[q.question_type] ?? q.question_type}</span>
                  {q.knowledge_point && <span className="practice-kp">{q.knowledge_point}</span>}
                  <div className="practice-stem" style={{ marginTop: 4 }}>{q.stem.length > 80 ? q.stem.slice(0, 80) + "..." : q.stem}</div>
                </div>
                <button type="button" className="practice-btn-next" onClick={() => handleViewQuestionDetail(q.id)} style={{ marginLeft: 8 }}>详情</button>
                <button type="button" className="practice-btn-next" onClick={() => handleDeleteQuestion(q.id)} style={{ marginLeft: 8 }}>删除</button>
              </div>
            ))}
            {manageQuestions.length === 0 && <p className="res-lib-empty">暂无题目</p>}
          </div>
        )}

        {/* Question detail overlay */}
        {selectedQuestionDetail && (
          <div className="res-lib-detail-overlay" onClick={() => setSelectedQuestionDetail(null)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Escape" && setSelectedQuestionDetail(null)}>
            <div className="res-lib-detail" onClick={(e) => e.stopPropagation()}>
              <div className="res-lib-detail-header">
                <div>
                  <span className="practice-type">{TYPE_LABELS[selectedQuestionDetail.question_type] ?? selectedQuestionDetail.question_type}</span>
                  {selectedQuestionDetail.knowledge_point && <span className="practice-kp">{selectedQuestionDetail.knowledge_point}</span>}
                </div>
                <button className="res-lib-detail-close" onClick={() => setSelectedQuestionDetail(null)} type="button">✕</button>
              </div>
              <div className="res-lib-detail-body">
                <div className="practice-stem">{selectedQuestionDetail.stem}</div>
                {selectedQuestionDetail.options && selectedQuestionDetail.options.length > 0 && (
                  <div className="practice-options">
                    {selectedQuestionDetail.options.map((opt, i) => (
                      <div key={i} className="practice-option">
                        <span className="practice-option-letter">{String.fromCharCode(65 + i)}</span>
                        <span>{opt}</span>
                      </div>
                    ))}
                  </div>
                )}
                {selectedQuestionDetail.answer && (
                  <div style={{ marginTop: 12 }}>
                    <strong>正确答案：</strong> {typeof selectedQuestionDetail.answer === "string" ? selectedQuestionDetail.answer : JSON.stringify(selectedQuestionDetail.answer)}
                  </div>
                )}
                {selectedQuestionDetail.explanation && (
                  <details style={{ marginTop: 8 }}>
                    <summary>解析</summary>
                    <p>{selectedQuestionDetail.explanation}</p>
                  </details>
                )}
              </div>
            </div>
          </div>
        )}
        {detailLoading && <div className="res-lib-loading"><Spinner /></div>}
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="practice-page">
        <div className="practice-empty">
          <h2>📝 练习模式</h2>
          <p>{loadError || "题库暂无题目。可以为薄弱知识点自动生成练习题。"}</p>
          {generateError && <div className="page-error" style={{ marginTop: 8 }}>{generateError}</div>}
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input
              placeholder="输入知识点（留空用薄弱点）"
              value={filterKP}
              onChange={(e) => setFilterKP(e.target.value)}
              className="practice-filter-kp"
            />
            <button type="button" className="practice-btn-submit" onClick={handleAutoGenerate} disabled={generating}>
              {generating ? "生成中..." : "AI 生成题目"}
            </button>
          </div>
          <button type="button" className="practice-btn-next" onClick={() => setTab("manage")} style={{ marginTop: 12 }}>去题库管理</button>
        </div>
      </div>
    );
  }

  if (showSummary) {
    const correctCount = answers.filter((a) => a.correct).length;
    const avgScore = answers.length > 0 ? Math.round(answers.reduce((s, a) => s + a.score, 0) / answers.length) : 0;

    // Save practice results to backend (once)
    if (!resultsSavedRef.current && answers.length > 0) {
      resultsSavedRef.current = true;
      const kp = filterKP || questions[0]?.knowledge_point || "通用";
      recordLearning({
        knowledge_point: kp,
        resource_type: "quiz",
        score: correctCount / answers.length,
        wrong_points: answers.filter((a) => !a.correct).map((a) => a.questionId),
      }).then(() => {
        // Refresh profile to update weak topics
        apiGet<import("../types/baseline").StudentProfile>("/profiles/me").then((p) => dispatch({ type: "SET_PROFILE", payload: p })).catch(() => {});
      }).catch(() => {});
    }
    return (
      <div className="practice-page">
        <div className="practice-summary">
          <h2>练习完成</h2>
          <div className="practice-summary-stats">
            <div className="practice-stat">
              <span className="practice-stat-value">{answers.length}</span>
              <span className="practice-stat-label">总题数</span>
            </div>
            <div className="practice-stat">
              <span className="practice-stat-value">{correctCount}</span>
              <span className="practice-stat-label">正确</span>
            </div>
            <div className="practice-stat">
              <span className="practice-stat-value">{answers.length - correctCount}</span>
              <span className="practice-stat-label">错误</span>
            </div>
            <div className="practice-stat">
              <span className="practice-stat-value">{avgScore}%</span>
              <span className="practice-stat-label">平均分</span>
            </div>
          </div>
          <div className="practice-summary-detail">
            {answers.map((a, i) => (
              <div key={i} className={`practice-result-item ${a.correct ? "correct" : "wrong"}`}>
                <span>第 {i + 1} 题</span>
                <span>{a.correct ? "✓ 正确" : "✗ 错误"}</span>
                <span>{a.score}分</span>
              </div>
            ))}
          </div>
          <button type="button" className="practice-btn-restart" onClick={handleRestart}>重新练习</button>
          <button type="button" className="practice-btn-next" onClick={() => navigate("/map")} style={{ marginLeft: 8 }}>查看学习路径</button>
        </div>
      </div>
    );
  }

  return (
    <div className="practice-page">
      <div className="practice-header">
        <h2>📝 练习模式</h2>
        <div className="practice-filters">
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="">全部题型</option>
            <option value="choice">选择题</option>
            <option value="blank">填空题</option>
            <option value="short_answer">简答题</option>
            <option value="programming">编程题</option>
          </select>
          <select value={filterDifficulty} onChange={(e) => setFilterDifficulty(e.target.value)}>
            <option value="">全部难度</option>
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
          <input
            placeholder="知识点筛选"
            value={filterKP}
            onChange={(e) => setFilterKP(e.target.value)}
            className="practice-filter-kp"
          />
          <button type="button" className="practice-btn-next" onClick={() => setTab("manage")}>题库管理</button>
        </div>
      </div>

      <div className="practice-progress">
        <div className="practice-progress-bar">
          <div className="practice-progress-fill" style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }} />
        </div>
        <span>{currentIdx + 1} / {questions.length}</span>
        <span className="practice-correct-rate">
          正确率 {answers.length > 0 ? Math.round((answers.filter((a) => a.correct).length / answers.length) * 100) : 0}%
        </span>
      </div>

      <div className="practice-question">
        <div className="practice-question-meta">
          <span className="practice-type">{TYPE_LABELS[currentQuestion.question_type] ?? currentQuestion.question_type}</span>
          {currentQuestion.difficulty_level && <span className="practice-diff">{currentQuestion.difficulty_level}</span>}
          {currentQuestion.knowledge_point && <span className="practice-kp">{currentQuestion.knowledge_point}</span>}
        </div>
        <div className="practice-stem">{currentQuestion.stem}</div>

        {currentQuestion.question_type === "choice" && currentQuestion.options ? (
          <div className="practice-options">
            {currentQuestion.options.map((opt, i) => {
              const letter = String.fromCharCode(65 + i);
              return (
                <button
                  key={i}
                  type="button"
                  className={`practice-option ${selectedOption === letter || selectedOption === opt ? "selected" : ""} ${
                    gradeResult ? (opt === currentQuestion.answer || letter === currentQuestion.answer ? "correct-answer" : "") : ""
                  }`}
                  onClick={() => !gradeResult && (setSelectedOption(letter), setGradeResult(null))}
                  disabled={!!gradeResult}
                >
                  <span className="practice-option-letter">{letter}</span>
                  <span>{opt}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <textarea
            className="practice-input"
            value={userAnswer}
            onChange={(e) => setUserAnswer(e.target.value)}
            placeholder="输入你的答案..."
            disabled={!!gradeResult}
            rows={4}
          />
        )}

        {!gradeResult ? (
          <button
            type="button"
            className="practice-btn-submit"
            onClick={handleSubmit}
            disabled={grading || (!userAnswer.trim() && !selectedOption)}
          >
            {grading ? "评分中..." : "提交答案"}
          </button>
        ) : (
          <div className="practice-feedback">
            <div className={`practice-score ${gradeResult.is_correct ? "correct" : "wrong"}`}>
              {gradeResult._grading_method === "fallback" ? `${gradeResult.score}参考分` : `${gradeResult.score}分`}
            </div>
            <div className="practice-feedback-text">{gradeResult.feedback}</div>
            {gradeResult.key_points_hit && gradeResult.key_points_hit.length > 0 && (
              <div className="practice-points">
                <span className="practice-points-label">✓ 答对要点：</span>
                {gradeResult.key_points_hit.map((p, i) => <span key={i} className="practice-point hit">{p}</span>)}
              </div>
            )}
            {gradeResult.key_points_missed && gradeResult.key_points_missed.length > 0 && (
              <div className="practice-points">
                <span className="practice-points-label">✗ 遗漏要点：</span>
                {gradeResult.key_points_missed.map((p, i) => <span key={i} className="practice-point missed">{p}</span>)}
              </div>
            )}
            {currentQuestion.explanation && (
              <details className="practice-explanation">
                <summary>查看解析</summary>
                <p>{currentQuestion.explanation}</p>
              </details>
            )}
            <button type="button" className="practice-btn-next" onClick={handleNext}>
              {currentIdx + 1 >= questions.length ? "查看结果" : "下一题 →"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
