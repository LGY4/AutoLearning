import { useState, useCallback, useEffect } from "react";
import { apiGet, apiPost } from "../../../api/client";
import { useTaskPolling } from "../../../hooks/useTaskPolling";
import type { StudentProfile } from "../../../types/baseline";

// ── Styles ────────────────────────────────────────────────────────────────
const S = {
  card: { border: "1px solid #e5e7eb", borderRadius: 8, padding: 12 } as React.CSSProperties,
  btn: (bg: string, cursor: string) => ({ textAlign: "left" as const, padding: "6px 10px", borderRadius: 6, border: "1px solid #d1d5db", background: bg, cursor, fontSize: 13 } as React.CSSProperties),
  correct: { background: "#f0fdf4", border: "1px solid #86efac" } as React.CSSProperties,
  wrong: { background: "#fef2f2", border: "1px solid #fca5a5" } as React.CSSProperties,
  summary: { padding: 12, borderRadius: 8, border: "1px solid #e5e7eb", background: "#f9fafb" } as React.CSSProperties,
};

/** Practice panel — interactive quiz with grading */
export function PracticePanel({ result }: { result: Record<string, unknown> }) {
  const questions = (result.questions as Array<Record<string, unknown>>) || [];
  const kp = String(result.knowledge_point || "");
  const error = result.error as string | undefined;
  const [currentIdx, setCurrentIdx] = useState(0);
  const [sessionResults, setSessionResults] = useState<Array<{ correct: boolean; score: number }>>([]);
  const [finished, setFinished] = useState(false);

  const handleAnswer = useCallback((correct: boolean, score: number) => {
    setSessionResults(prev => {
      const next = [...prev, { correct, score }];
      if (next.length >= questions.length) {
        setFinished(true);
      } else {
        setCurrentIdx(next.length);
      }
      return next;
    });
  }, [questions.length]);

  if (error) return <div className="chat-content" style={{ color: "#ef4444" }}>{error}</div>;
  if (!questions.length) return <div className="chat-content">暂无题目，请稍后重试。</div>;

  if (finished) {
    const correctCount = sessionResults.filter(r => r.correct).length;
    const avgScore = sessionResults.reduce((s, r) => s + r.score, 0) / sessionResults.length;
    const accuracy = correctCount / questions.length;
    const level = accuracy >= 0.8 ? "excellent" : accuracy >= 0.6 ? "good" : accuracy >= 0.4 ? "fair" : "needs_work";
    const levelConfig = {
      excellent: { label: "优秀", color: "#16a34a", bg: "#f0fdf4", border: "#86efac", emoji: "🎉" },
      good: { label: "良好", color: "#2563eb", bg: "#eff6ff", border: "#93c5fd", emoji: "👍" },
      fair: { label: "一般", color: "#ca8a04", bg: "#fef9c3", border: "#fde68a", emoji: "💪" },
      needs_work: { label: "需加强", color: "#dc2626", bg: "#fef2f2", border: "#fca5a5", emoji: "📚" },
    };
    const lv = levelConfig[level];

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>「{kp}」练习完成</div>

        {/* Score summary */}
        <div style={{ padding: 12, background: lv.bg, borderRadius: 8, border: `1px solid ${lv.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 24 }}>{lv.emoji}</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, color: lv.color }}>{lv.label}</div>
              <div style={{ fontSize: 12, color: "#6b7280" }}>正确率 {Math.round(accuracy * 100)}%</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: 13 }}>
            <div>答对: <strong>{correctCount}/{questions.length}</strong></div>
            <div>平均分: <strong>{avgScore.toFixed(1)}</strong></div>
          </div>
          <div style={{ marginTop: 8, display: "flex", gap: 4 }}>
            {sessionResults.map((r, i) => (
              <span key={i} style={{
                width: 22, height: 22, borderRadius: 11,
                background: r.correct ? "#22c55e" : "#ef4444",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, color: "white", fontWeight: 600,
              }}>{i + 1}</span>
            ))}
          </div>
        </div>

        {/* Learning insight */}
        <div style={{ padding: 10, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>学习建议</div>
          {level === "excellent" && <div>掌握良好！可以尝试进阶题目或学习下一个知识点。</div>}
          {level === "good" && <div>基本掌握，建议再做几道题巩固薄弱的题目类型。</div>}
          {level === "fair" && <div>建议回顾基础概念，配合思维导图或视频加深理解。</div>}
          {level === "needs_work" && <div>建议从基础文档开始，逐步建立概念框架后再做练习。</div>}
        </div>

        {/* Quick follow-up actions */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={() => window.dispatchEvent(new CustomEvent("chat-send-message", { detail: `再出几道${kp}的题` }))}
            style={{ padding: "5px 12px", borderRadius: 14, fontSize: 12, border: "1px solid #3b82f6", background: "white", color: "#3b82f6", cursor: "pointer" }}>
            再练一轮
          </button>
          {level !== "excellent" && (
            <button onClick={() => window.dispatchEvent(new CustomEvent("chat-send-message", { detail: `帮我生成${kp}的学习资料` }))}
              style={{ padding: "5px 12px", borderRadius: 14, fontSize: 12, border: "1px solid #22c55e", background: "white", color: "#22c55e", cursor: "pointer" }}>
              生成学习资料
            </button>
          )}
          <button onClick={() => window.dispatchEvent(new CustomEvent("chat-send-message", { detail: "看看我的学习分析" }))}
            style={{ padding: "5px 12px", borderRadius: 14, fontSize: 12, border: "1px solid #6b7280", background: "white", color: "#6b7280", cursor: "pointer" }}>
            查看分析
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>「{kp}」练习题 ({questions.length} 道)</div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>进度: {sessionResults.length}/{questions.length}</div>
      <PracticeQuestion
        key={currentIdx}
        index={currentIdx}
        question={questions[currentIdx]}
        knowledgePoint={kp}
        onResult={handleAnswer}
      />
    </div>
  );
}

function PracticeQuestion({ index, question, knowledgePoint, onResult }: {
  index: number; question: Record<string, unknown>; knowledgePoint: string;
  onResult: (correct: boolean, score: number) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [gradeResult, setGradeResult] = useState<{ correct: boolean; score: number; explanation: string } | null>(null);
  const [grading, setGrading] = useState(false);

  const q = String(question.question || question.stem || "");
  const options = (question.options as string[]) || [];
  const answer = String(question.answer || "");
  const explanation = String(question.explanation || "");
  const qType = String(question.type || (options.length > 0 ? "choice" : "short_answer"));
  const qId = String(question.id || `q-${index}`);

  const handleSubmit = useCallback(async () => {
    if (submitted || grading) return;

    // For choice questions, do client-side grading first for instant feedback
    if (options.length > 0 && selected) {
      const isCorrect = selected.trim().toUpperCase() === answer.trim().toUpperCase();
      const score = isCorrect ? 1.0 : 0.0;
      setGradeResult({ correct: isCorrect, score, explanation });
      setSubmitted(true);
      onResult(isCorrect, score);
      // Persist to backend (fire-and-forget)
      apiPost("/resources/grade", {
        question_id: qId,
        question_type: qType,
        stem: q,
        standard_answer: answer,
        user_answer: selected,
        explanation,
        knowledge_point: knowledgePoint,
      }).then(() => {
        apiGet<StudentProfile>("/profiles/me").catch(() => {});
      }).catch(() => {});
      return;
    }

    // For open-ended questions, call backend grading API
    if (selected !== null) {
      setGrading(true);
      try {
        const res = await apiPost<{ correct: boolean; score: number; explanation?: string }>("/resources/grade", {
          question_id: qId,
          question_type: qType,
          stem: q,
          standard_answer: answer,
          user_answer: selected,
          explanation,
          knowledge_point: knowledgePoint,
        });
        const isCorrect = res.correct ?? res.score >= 0.6;
        const score = res.score ?? (isCorrect ? 1.0 : 0.0);
        setGradeResult({ correct: isCorrect, score, explanation: res.explanation || explanation });
        setSubmitted(true);
        // Refresh profile after grading
        apiGet<StudentProfile>("/profiles/me").catch(() => {});
        onResult(isCorrect, score);
      } catch {
        // Fallback: compare directly
        const isCorrect = selected.trim().toLowerCase() === answer.trim().toLowerCase();
        setGradeResult({ correct: isCorrect, score: isCorrect ? 1.0 : 0, explanation });
        setSubmitted(true);
        onResult(isCorrect, isCorrect ? 1.0 : 0);
      } finally {
        setGrading(false);
      }
    }
  }, [submitted, grading, selected, options, answer, qType, qId, q, explanation, knowledgePoint, onResult]);

  return (
    <div style={{ ...S.card, ...(submitted ? (gradeResult?.correct ? S.correct : S.wrong) : {}) }}>
      <div style={{ fontWeight: 500, marginBottom: 8 }}>{index + 1}. {q}</div>

      {options.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {options.map((opt, j) => {
            let bg = "white";
            if (submitted) {
              if (opt === answer) bg = "#dcfce7";
              else if (opt === selected) bg = "#fee2e2";
            } else if (opt === selected) bg = "#dbeafe";
            return (
              <button key={j} onClick={() => !submitted && setSelected(opt)} style={S.btn(bg, submitted ? "default" : "pointer")}>
                {opt}
              </button>
            );
          })}
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={selected || ""}
            onChange={(e) => !submitted && setSelected(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !submitted && handleSubmit()}
            placeholder="输入答案..."
            disabled={submitted}
            style={{ flex: 1, padding: "6px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13 }}
          />
        </div>
      )}

      {!submitted && (
        <button
          onClick={handleSubmit}
          disabled={selected === null || grading}
          style={{ marginTop: 8, padding: "6px 16px", borderRadius: 6, border: "1px solid #3b82f6", background: selected === null ? "#e5e7eb" : "#3b82f6", color: selected === null ? "#9ca3af" : "white", cursor: selected === null ? "default" : "pointer", fontSize: 13 }}
        >
          {grading ? "评分中..." : "提交答案"}
        </button>
      )}

      {submitted && gradeResult && (
        <div style={{ marginTop: 8, padding: 8, background: gradeResult.correct ? "#f0fdf4" : "#fef2f2", borderRadius: 6, fontSize: 13, border: `1px solid ${gradeResult.correct ? "#86efac" : "#fca5a5"}` }}>
          <div style={{ fontWeight: 600, color: gradeResult.correct ? "#16a34a" : "#dc2626" }}>
            {gradeResult.correct ? "回答正确" : "回答错误"} {gradeResult.score > 0 && gradeResult.score < 1 ? `(得分: ${Math.round(gradeResult.score * 100)}%)` : ""}
          </div>
          {!gradeResult.correct && <div style={{ marginTop: 4 }}><strong>正确答案：</strong>{answer}</div>}
          {gradeResult.explanation && <div style={{ marginTop: 4, color: "#6b7280" }}><strong>解析：</strong>{gradeResult.explanation}</div>}
        </div>
      )}
    </div>
  );
}

/** Learning Map panel — interactive knowledge graph with node actions */
export function LearningMapPanel({ result }: { result: Record<string, unknown> }) {
  const nodes = (result.nodes as Array<Record<string, unknown>>) || [];
  const edges = (result.edges as Array<Record<string, unknown>>) || [];
  const error = result.error as string | undefined;
  const [selectedNode, setSelectedNode] = useState<Record<string, unknown> | null>(null);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState(false);

  if (error) return <div className="chat-content" style={{ color: "#ef4444" }}>{error}</div>;
  if (!nodes.length) return <div className="chat-content">知识图谱为空，请先导入知识库。</div>;

  const getStatus = (n: Record<string, unknown>) => nodeStatuses[String(n.id)] || String(n.status || "available");

  const handleStartLearning = async (node: Record<string, unknown>) => {
    const nodeId = String(node.id);
    setActionLoading(true);
    try {
      await apiPost("/learning-paths/start-node", { knowledge_point: node.name || node.knowledge_point || nodeId });
      setNodeStatuses(prev => ({ ...prev, [nodeId]: "learning" }));
    } catch { /* ignore */ }
    setActionLoading(false);
  };

  const handleMarkComplete = async (node: Record<string, unknown>) => {
    const nodeId = String(node.id);
    const kp = String(node.name || node.knowledge_point || nodeId);
    setActionLoading(true);
    try {
      await apiPost("/learning/complete-knowledge-point", { knowledge_point: kp });
      setNodeStatuses(prev => ({ ...prev, [nodeId]: "completed" }));
    } catch { /* ignore */ }
    setActionLoading(false);
  };

  // Group by level
  const levels = new Map<number, Record<string, unknown>[]>();
  for (const n of nodes) {
    const lv = Number(n.level ?? 0);
    if (!levels.has(lv)) levels.set(lv, []);
    levels.get(lv)!.push(n);
  }

  const statusColors: Record<string, { bg: string; border: string; icon: string }> = {
    completed: { bg: "#dcfce7", border: "#86efac", icon: "✓" },
    learning: { bg: "#dbeafe", border: "#93c5fd", icon: "📖" },
    available: { bg: "#fef9c3", border: "#fde68a", icon: "○" },
    locked: { bg: "#f3f4f6", border: "#d1d5db", icon: "🔒" },
    skipped: { bg: "#e5e7eb", border: "#9ca3af", icon: "⏭" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>知识图谱 ({nodes.length} 节点, {edges.length} 边)</div>

      {/* Node grid by level */}
      {Array.from(levels.entries()).sort(([a], [b]) => a - b).map(([lv, lnodes]) => (
        <div key={lv} style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "#9ca3af", minWidth: 30 }}>L{lv}</span>
          {lnodes.map((n, i) => {
            const status = getStatus(n);
            const sc = statusColors[status] || statusColors.available;
            const isSelected = selectedNode === n;
            return (
              <button
                key={i}
                onClick={() => setSelectedNode(isSelected ? null : n)}
                style={{
                  padding: "4px 10px", borderRadius: 12, background: sc.bg, fontSize: 12,
                  border: `1px solid ${isSelected ? "#3b82f6" : sc.border}`,
                  cursor: "pointer", fontWeight: isSelected ? 600 : 400,
                  outline: isSelected ? "2px solid #3b82f6" : "none",
                }}
              >
                {sc.icon} {String(n.name || n.knowledge_point || n.id)}
              </button>
            );
          })}
        </div>
      ))}

      {/* Selected node detail panel */}
      {selectedNode && (
        <div style={{ padding: 12, border: "1px solid #3b82f6", borderRadius: 8, background: "#eff6ff", marginTop: 4 }}>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>
            {String(selectedNode.name || selectedNode.knowledge_point || selectedNode.id)}
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
            状态: <strong>{getStatus(selectedNode)}</strong>
            {selectedNode.description != null && <span> — {String(selectedNode.description)}</span>}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {getStatus(selectedNode) === "available" && (
              <button
                onClick={() => handleStartLearning(selectedNode)}
                disabled={actionLoading}
                style={{ padding: "5px 14px", borderRadius: 6, border: "1px solid #3b82f6", background: "#3b82f6", color: "white", cursor: "pointer", fontSize: 12 }}
              >
                开始学习
              </button>
            )}
            {(getStatus(selectedNode) === "learning" || getStatus(selectedNode) === "available") && (
              <button
                onClick={() => handleMarkComplete(selectedNode)}
                disabled={actionLoading}
                style={{ padding: "5px 14px", borderRadius: 6, border: "1px solid #22c55e", background: "#22c55e", color: "white", cursor: "pointer", fontSize: 12 }}
              >
                标记完成
              </button>
            )}
            <button
              onClick={() => setSelectedNode(null)}
              style={{ padding: "5px 14px", borderRadius: 6, border: "1px solid #d1d5db", background: "white", cursor: "pointer", fontSize: 12 }}
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Dashboard panel — profile summary with RadarChart and interactive elements */
export function DashboardPanel({ result }: { result: Record<string, unknown> }) {
  const profile = result.profile as Record<string, unknown> | undefined;
  const recs = (result.recommendations as Array<Record<string, unknown>>) || [];

  if (!profile) return <div className="chat-content">暂无学习数据，请先完成入学诊断。</div>;

  const kp = profile.knowledge_profile as Record<string, unknown> | undefined;
  const goal = profile.learning_goal as Record<string, unknown> | undefined;
  const dims = (kp?.topic_dimensions as Record<string, Record<string, unknown>>) || {};
  const weakTopics = (kp?.weak_topics as string[]) || [];
  const overallLevel = String(kp?.overall_level || "unknown");

  // Compute average four-dimension scores for radar chart
  const dimAvg = { mastery: 0, application: 0, memory: 0, understanding: 0 };
  const dimEntries = Object.values(dims);
  if (dimEntries.length > 0) {
    for (const d of dimEntries) {
      dimAvg.mastery += d.mastery === "high" ? 1 : d.mastery === "mid" ? 0.5 : 0;
      dimAvg.application += d.application === "high" ? 1 : d.application === "mid" ? 0.5 : 0;
      dimAvg.memory += d.memory === "high" ? 1 : d.memory === "mid" ? 0.5 : 0;
      dimAvg.understanding += d.understanding === "high" ? 1 : d.understanding === "mid" ? 0.5 : 0;
    }
    const n = dimEntries.length;
    dimAvg.mastery /= n; dimAvg.application /= n; dimAvg.memory /= n; dimAvg.understanding /= n;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Goal */}
      {goal?.current_goal != null && (
        <div style={{ padding: 10, background: "#eff6ff", borderRadius: 8, border: "1px solid #bfdbfe" }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>学习目标</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>{String(goal.current_goal ?? "")}</div>
          {goal?.target_course != null && <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>课程: {String(goal.target_course)}</div>}
        </div>
      )}

      {/* Level + Radar */}
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div style={{ padding: 10, background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac", minWidth: 100, textAlign: "center" }}>
          <div style={{ fontSize: 11, color: "#6b7280" }}>整体水平</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: overallLevel === "advanced" ? "#16a34a" : overallLevel === "intermediate" ? "#ca8a04" : "#dc2626" }}>
            {overallLevel === "advanced" ? "进阶" : overallLevel === "intermediate" ? "中级" : "初级"}
          </div>
        </div>
        {dimEntries.length > 0 && (
          <MiniRadar dimensions={dimAvg} />
        )}
      </div>

      {/* Knowledge mastery bars */}
      {Object.keys(dims).length > 0 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>知识点掌握度</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {Object.entries(dims).slice(0, 8).map(([name, dim]) => {
              const score = Number(dim.composite_score ?? 0);
              return (
                <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <span style={{ minWidth: 80 }}>{name}</span>
                  <div style={{ flex: 1, height: 6, background: "#e5e7eb", borderRadius: 3 }}>
                    <div style={{ width: `${score * 100}%`, height: "100%", background: score >= 0.7 ? "#22c55e" : score >= 0.4 ? "#eab308" : "#ef4444", borderRadius: 3 }} />
                  </div>
                  <span style={{ minWidth: 30, textAlign: "right" }}>{Math.round(score * 100)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Weak topics — clickable to generate practice */}
      {weakTopics.length > 0 && (
        <div style={{ padding: 10, background: "#fef2f2", borderRadius: 8, border: "1px solid #fecaca" }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>薄弱知识点</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {weakTopics.map((t, i) => (
              <span key={i} style={{ padding: "3px 10px", borderRadius: 10, background: "#fee2e2", fontSize: 12, cursor: "default" }}>
                {t}
              </span>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 6 }}>在对话中输入"帮我出几道题"可针对薄弱点练习</div>
        </div>
      )}

      {/* Recommendations */}
      {recs.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>推荐 ({recs.length})</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {recs.slice(0, 5).map((r, i) => (
              <div key={i} style={{ padding: "6px 10px", border: "1px solid #e5e7eb", borderRadius: 6, fontSize: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <strong>{String(r.knowledge_point || "")}</strong>
                  <span style={{ color: "#6b7280", marginLeft: 6 }}>{String(r.reason || r.recommendation_type || "")}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Mini radar chart — SVG-based four-dimension visualization */
function MiniRadar({ dimensions }: { dimensions: Record<string, number> }) {
  const size = 120;
  const cx = size / 2, cy = size / 2, r = 45;
  const labels = [
    { key: "mastery", label: "掌握", angle: -Math.PI / 2 },
    { key: "application", label: "应用", angle: 0 },
    { key: "understanding", label: "理解", angle: Math.PI / 2 },
    { key: "memory", label: "记忆", angle: Math.PI },
  ];
  const points = labels.map(l => {
    const val = Math.max(0, Math.min(1, dimensions[l.key] || 0));
    return { x: cx + r * val * Math.cos(l.angle), y: cy + r * val * Math.sin(l.angle), ...l };
  });
  const polygon = points.map(p => `${p.x},${p.y}`).join(" ");

  return (
    <svg width={size} height={size} style={{ flexShrink: 0 }}>
      {/* Grid */}
      {[0.33, 0.66, 1].map(s => (
        <polygon key={s} points={labels.map(l => `${cx + r * s * Math.cos(l.angle)},${cy + r * s * Math.sin(l.angle)}`).join(" ")} fill="none" stroke="#e5e7eb" strokeWidth={0.5} />
      ))}
      {/* Axes */}
      {labels.map(l => (
        <line key={l.key} x1={cx} y1={cy} x2={cx + r * Math.cos(l.angle)} y2={cy + r * Math.sin(l.angle)} stroke="#e5e7eb" strokeWidth={0.5} />
      ))}
      {/* Data */}
      <polygon points={polygon} fill="rgba(59,130,246,0.2)" stroke="#3b82f6" strokeWidth={1.5} />
      {/* Labels */}
      {labels.map(l => (
        <text key={l.key} x={cx + (r + 12) * Math.cos(l.angle)} y={cy + (r + 12) * Math.sin(l.angle)} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill="#6b7280">
          {l.label}
        </text>
      ))}
    </svg>
  );
}

/** Resource Browse panel — expandable cards with content preview */
export function ResourceBrowsePanel({ result }: { result: Record<string, unknown> }) {
  const resources = (result.resources as Array<Record<string, unknown>>) || [];
  const total = Number(result.total ?? resources.length);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loadedResource, setLoadedResource] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  if (!resources.length) return <div className="chat-content">暂无资源，请先在对话中说"生成XX资源"。</div>;

  const icons: Record<string, string> = {
    document: "📄", quiz: "📝", mindmap: "🧠", flowchart: "📊",
    video: "🎬", animation: "✨", code_case: "💻", reading: "📚",
  };

  const handleExpand = async (r: Record<string, unknown>) => {
    const rid = String(r.resource_id || "");
    if (expandedId === rid) { setExpandedId(null); setLoadedResource(null); return; }
    setExpandedId(rid);
    setLoading(true);
    try {
      const detail = await apiGet<Record<string, unknown>>(`/resources/${rid}`);
      setLoadedResource(detail);
    } catch {
      setLoadedResource(r); // fallback to basic data
    }
    setLoading(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>资源库 ({total} 份)</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {resources.map((r, i) => {
          const rt = String(r.resource_type || "document");
          const rid = String(r.resource_id || "");
          const isExpanded = expandedId === rid;
          return (
            <div key={i}>
              <button
                onClick={() => handleExpand(r)}
                style={{
                  width: "100%", textAlign: "left", padding: "8px 12px", borderRadius: 8,
                  border: `1px solid ${isExpanded ? "#3b82f6" : "#e5e7eb"}`,
                  background: isExpanded ? "#eff6ff" : "white", cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 10, fontSize: 13,
                }}
              >
                <span style={{ fontSize: 18 }}>{icons[rt] ?? "📄"}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 500 }}>{String(r.title || "未命名")}</div>
                  <div style={{ fontSize: 11, color: "#6b7280" }}>{rt} · {String(r.knowledge_point || "")}</div>
                </div>
                <span style={{ fontSize: 11, color: "#9ca3af" }}>{isExpanded ? "收起" : "展开"}</span>
              </button>
              {isExpanded && (
                <div style={{ padding: 12, border: "1px solid #3b82f6", borderTop: "none", borderRadius: "0 0 8px 8px", background: "#fafafa" }}>
                  {loading ? (
                    <div style={{ textAlign: "center", color: "#9ca3af", fontSize: 13, padding: 16 }}>加载中...</div>
                  ) : loadedResource ? (
                    <div style={{ fontSize: 13 }}>
                      <div style={{ fontWeight: 600, marginBottom: 8 }}>{String(loadedResource.title || "")}</div>
                      <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, maxHeight: 300, overflow: "auto" }}>
                        {String(loadedResource.content || "无内容").slice(0, 2000)}
                        {String(loadedResource.content || "").length > 2000 && "..."}
                      </div>
                      {loadedResource.quality_score != null && (
                        <div style={{ marginTop: 8, fontSize: 11, color: "#6b7280" }}>
                          质量评分: {Number(loadedResource.quality_score).toFixed(1)}
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Video Generation panel — with real progress polling */
export function VideoPanel({ result }: { result: Record<string, unknown> }) {
  const topic = String(result.topic || "");
  const message = String(result.message || "");
  const taskId = String(result.task_id || "");
  const [videoResult, setVideoResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { taskStatus, polling, startPolling } = useTaskPolling({
    endpoint: "/video/status",
    intervalMs: 3000,
    maxAttempts: 100,
    onDone: (r) => setVideoResult(r),
    onError: (e) => setError(e),
  });

  useEffect(() => {
    if (taskId && taskId !== "pending") startPolling(taskId);
  }, [taskId, startPolling]);

  const stages = ["脚本", "配音", "画面", "合成"];
  const progressList = (taskStatus?.progress as Array<Record<string, unknown>>) || [];
  const currentStage = progressList.length > 0 ? String(progressList[progressList.length - 1].stage || "") : "";
  const stageIdx = stages.findIndex(s => currentStage.includes(s));

  if (videoResult) {
    const videoUrl = String(videoResult.video_url || videoResult.url || "");
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🎬 视频生成完成</div>
        {videoUrl && (
          <video controls style={{ width: "100%", maxHeight: 300, borderRadius: 8 }}>
            <source src={videoUrl} />
          </video>
        )}
        {Array.isArray(videoResult.scenes) && (
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {videoResult.scenes.length} 个场景
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>🎬 知识视频 — {topic}</div>
      {error ? (
        <div style={{ padding: 10, background: "#fef2f2", borderRadius: 8, border: "1px solid #fca5a5", fontSize: 13, color: "#dc2626" }}>
          {error}
        </div>
      ) : (
        <>
          <div style={{ padding: 10, background: "#eff6ff", borderRadius: 8, border: "1px solid #bfdbfe", fontSize: 13 }}>
            {polling ? "正在生成..." : message || "视频生成任务已提交。"}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {stages.map((stage, i) => {
              const active = i <= stageIdx;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center",
                    background: active ? "#3b82f6" : "#e5e7eb", color: "white", fontSize: 10,
                  }}>{i + 1}</div>
                  <span style={{ color: active ? "#1e40af" : "#9ca3af" }}>{stage}</span>
                  {i < 3 && <div style={{ width: 16, height: 1, background: active ? "#3b82f6" : "#e5e7eb" }} />}
                </div>
              );
            })}
          </div>
          {!taskId && <a href="/video-studio" style={{ fontSize: 13, color: "#3b82f6", textDecoration: "none" }}>前往视频工作室查看 →</a>}
        </>
      )}
    </div>
  );
}

/** Media Generation panel — with real progress polling */
export function MediaPanel({ result }: { result: Record<string, unknown> }) {
  const topic = String(result.topic || "");
  const mode = String(result.mode || "animation");
  const message = String(result.message || "");
  const taskId = String(result.task_id || "");
  const [mediaResult, setMediaResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { taskStatus, polling, startPolling } = useTaskPolling({
    endpoint: "/system/media/status",
    intervalMs: 3000,
    maxAttempts: 100,
    onDone: (r) => setMediaResult(r),
    onError: (e) => setError(e),
  });

  useEffect(() => {
    if (taskId && taskId !== "pending") startPolling(taskId);
  }, [taskId, startPolling]);

  if (mediaResult) {
    const url = String(mediaResult.url || mediaResult.output_url || "");
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{mode === "image" ? "🖼️ 图片" : "✨ 动画"}生成完成</div>
        {url && <img src={url} alt={topic} style={{ maxWidth: "100%", borderRadius: 8 }} />}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{mode === "image" ? "🖼️ 图片" : "✨ 动画"} — {topic}</div>
      {error ? (
        <div style={{ padding: 10, background: "#fef2f2", borderRadius: 8, border: "1px solid #fca5a5", fontSize: 13, color: "#dc2626" }}>{error}</div>
      ) : (
        <>
          <div style={{ padding: 10, background: "#f5f3ff", borderRadius: 8, border: "1px solid #c4b5fd", fontSize: 13 }}>
            {polling ? "正在生成..." : message || "生成任务已提交。"}
          </div>
          {polling && <div className="inline-panel-loading">轮询进度中...</div>}
          {!taskId && <a href="/media-studio" style={{ fontSize: 13, color: "#7c3aed", textDecoration: "none" }}>前往动画图片工作室查看 →</a>}
        </>
      )}
    </div>
  );
}

/** Course Goal panel — with create form */
export function CourseGoalPanel({ result }: { result: Record<string, unknown> }) {
  const goals = (result.goals as Array<Record<string, unknown>>) || [];
  const message = String(result.message || "");
  const [showForm, setShowForm] = useState(false);
  const [goalTitle, setGoalTitle] = useState("");
  const [goalCourse, setGoalCourse] = useState("");
  const [saving, setSaving] = useState(false);
  const [localGoals, setLocalGoals] = useState(goals);

  const handleCreateGoal = async () => {
    if (!goalTitle.trim()) return;
    setSaving(true);
    try {
      await apiPost("/courses/goals", { title: goalTitle.trim(), target_course: goalCourse.trim() || undefined });
      setLocalGoals(prev => [...prev, { title: goalTitle.trim(), target_course: goalCourse.trim(), status: "active" }]);
      setGoalTitle("");
      setGoalCourse("");
      setShowForm(false);
    } catch { /* ignore */ }
    setSaving(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>📚 课程与目标</div>
      {message && <div style={{ fontSize: 13, color: "#6b7280" }}>{message}</div>}

      {localGoals.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {localGoals.map((g, i) => (
            <div key={i} style={{ padding: "8px 12px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{String(g.title || g.goal || "")}</strong>
                {g.target_course != null && <span style={{ marginLeft: 8, fontSize: 11, color: "#6b7280" }}>{String(g.target_course)}</span>}
              </div>
              {g.status != null && (
                <span style={{
                  padding: "2px 8px", borderRadius: 10, fontSize: 11,
                  background: g.status === "active" ? "#dcfce7" : g.status === "completed" ? "#dbeafe" : "#f3f4f6",
                  color: g.status === "active" ? "#16a34a" : g.status === "completed" ? "#2563eb" : "#6b7280",
                }}>{String(g.status)}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {showForm ? (
        <div style={{ padding: 12, border: "1px solid #3b82f6", borderRadius: 8, background: "#eff6ff" }}>
          <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>设定学习目标</div>
          <input
            type="text" value={goalTitle} onChange={(e) => setGoalTitle(e.target.value)}
            placeholder="目标名称，如：掌握快速排序"
            style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13, marginBottom: 6, boxSizing: "border-box" }}
          />
          <input
            type="text" value={goalCourse} onChange={(e) => setGoalCourse(e.target.value)}
            placeholder="关联课程（可选）"
            style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13, marginBottom: 8, boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={handleCreateGoal} disabled={saving || !goalTitle.trim()}
              style={{ padding: "5px 14px", borderRadius: 6, border: "1px solid #3b82f6", background: goalTitle.trim() ? "#3b82f6" : "#e5e7eb", color: "white", cursor: "pointer", fontSize: 12 }}>
              {saving ? "保存中..." : "创建目标"}
            </button>
            <button onClick={() => setShowForm(false)}
              style={{ padding: "5px 14px", borderRadius: 6, border: "1px solid #d1d5db", background: "white", cursor: "pointer", fontSize: 12 }}>
              取消
            </button>
          </div>
        </div>
      ) : (
        <button onClick={() => setShowForm(true)}
          style={{ padding: "8px 14px", borderRadius: 8, border: "1px dashed #3b82f6", background: "white", cursor: "pointer", fontSize: 13, color: "#3b82f6" }}>
          + 设定新目标
        </button>
      )}
    </div>
  );
}

/** SVG trend chart — questions + accuracy over time */
function TrendChart({ data }: { data: Array<Record<string, unknown>> }) {
  const w = 320, h = 100, pad = 30;
  const chartW = w - pad * 2, chartH = h - pad * 1.5;

  const questions = data.map(d => Number(d.questions || 0));
  const accuracies = data.map(d => Number(d.accuracy || 0));
  const maxQ = Math.max(...questions, 1);
  const dates = data.map(d => String(d.date || "").slice(5));

  const qPoints = questions.map((q, i) => ({
    x: pad + (i / Math.max(data.length - 1, 1)) * chartW,
    y: pad + chartH - (q / maxQ) * chartH,
  }));
  const aPoints = accuracies.map((a, i) => ({
    x: pad + (i / Math.max(data.length - 1, 1)) * chartW,
    y: pad + chartH - a * chartH,
  }));

  const qPath = qPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const aPath = aPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");

  return (
    <svg width={w} height={h} style={{ width: "100%", maxWidth: w }}>
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map(v => (
        <line key={v} x1={pad} y1={pad + chartH * (1 - v)} x2={pad + chartW} y2={pad + chartH * (1 - v)} stroke="#f3f4f6" strokeWidth={0.5} />
      ))}
      {/* Y axis labels */}
      <text x={pad - 4} y={pad + 4} textAnchor="end" fontSize={8} fill="#9ca3af">{maxQ}</text>
      <text x={pad - 4} y={pad + chartH + 4} textAnchor="end" fontSize={8} fill="#9ca3af">0</text>
      {/* Questions line (blue) */}
      <path d={qPath} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
      {qPoints.map((p, i) => <circle key={`q${i}`} cx={p.x} cy={p.y} r={2.5} fill="#3b82f6" />)}
      {/* Accuracy line (green) */}
      <path d={aPath} fill="none" stroke="#22c55e" strokeWidth={1.5} />
      {aPoints.map((p, i) => <circle key={`a${i}`} cx={p.x} cy={p.y} r={2.5} fill="#22c55e" />)}
      {/* X axis labels (first, middle, last) */}
      {dates.length > 0 && <text x={pad} y={h - 4} fontSize={8} fill="#9ca3af">{dates[0]}</text>}
      {dates.length > 2 && <text x={pad + chartW / 2} y={h - 4} textAnchor="middle" fontSize={8} fill="#9ca3af">{dates[Math.floor(dates.length / 2)]}</text>}
      {dates.length > 1 && <text x={pad + chartW} y={h - 4} textAnchor="end" fontSize={8} fill="#9ca3af">{dates[dates.length - 1]}</text>}
      {/* Legend */}
      <line x1={pad} y1={8} x2={pad + 12} y2={8} stroke="#3b82f6" strokeWidth={1.5} />
      <text x={pad + 15} y={11} fontSize={8} fill="#6b7280">答题数</text>
      <line x1={pad + 50} y1={8} x2={pad + 62} y2={8} stroke="#22c55e" strokeWidth={1.5} />
      <text x={pad + 65} y={11} fontSize={8} fill="#6b7280">正确率</text>
    </svg>
  );
}

/** Analytics panel — learning trends, efficiency, mastery timeline */
export function AnalyticsPanel({ result }: { result: Record<string, unknown> }) {
  const error = result.error as string | undefined;
  if (error) return <div className="chat-content" style={{ color: "#ef4444" }}>{error}</div>;

  const summary = result.summary as Record<string, unknown> | undefined;
  const dailyActivity = (result.daily_activity as Array<Record<string, unknown>>) || [];
  const topicMastery = (result.topic_mastery as Array<Record<string, unknown>>) || [];
  const dimRadar = result.dimension_radar as Record<string, number> | undefined;
  const efficiency = result.efficiency as Record<string, unknown> | undefined;
  const weakTopics = (result.weak_topics as string[]) || [];
  const knownTopics = (result.known_topics as string[]) || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ fontWeight: 600, fontSize: 15 }}>📊 学习分析报告</div>

      {/* Summary cards */}
      {summary != null && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {[
            { label: "学习次数", value: String(summary.total_sessions || 0), icon: "📝" },
            { label: "答题数", value: String(summary.total_questions || 0), icon: "❓" },
            { label: "正确率", value: `${Math.round(Number(summary.avg_accuracy || 0) * 100)}%`, icon: "🎯" },
            { label: "学习时长", value: `${Number(summary.total_minutes || 0).toFixed(0)}分`, icon: "⏱" },
          ].map((card, i) => (
            <div key={i} style={{ padding: 10, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb", textAlign: "center" }}>
              <div style={{ fontSize: 18 }}>{card.icon}</div>
              <div style={{ fontSize: 16, fontWeight: 700, marginTop: 2 }}>{card.value}</div>
              <div style={{ fontSize: 11, color: "#6b7280" }}>{card.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Efficiency metrics */}
      {efficiency != null && (
        <div style={{ padding: 10, background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac" }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>学习效率</div>
          <div style={{ display: "flex", gap: 16, fontSize: 13, flexWrap: "wrap" }}>
            <div>每小时答题: <strong>{String(efficiency.questions_per_hour || 0)}</strong></div>
            <div>近期正确率: <strong>{Math.round(Number(efficiency.recent_accuracy || 0) * 100)}%</strong></div>
            <div>趋势: <strong>{efficiency.accuracy_trend === "up" ? "↑ 上升" : efficiency.accuracy_trend === "down" ? "↓ 下降" : "→ 稳定"}</strong></div>
            <div>连续学习: <strong>{String(efficiency.streak_days || 0)}天</strong></div>
          </div>
        </div>
      )}

      {/* Daily activity chart */}
      {dailyActivity.length > 1 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>学习趋势</div>
          <TrendChart data={dailyActivity} />
        </div>
      )}
      {dailyActivity.length > 0 && dailyActivity.length <= 1 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>每日学习活动</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {dailyActivity.map((day, i) => {
              const questions = Number(day.questions || 0);
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
                  <span style={{ minWidth: 50, color: "#6b7280" }}>{String(day.date).slice(5)}</span>
                  <span>{questions}题</span>
                  <span style={{ color: Number(day.accuracy || 0) >= 0.7 ? "#16a34a" : "#dc2626" }}>
                    {Math.round(Number(day.accuracy || 0) * 100)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Topic mastery */}
      {topicMastery.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>知识点掌握度</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {topicMastery.map((t, i) => {
              const score = Number(t.score || 0);
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <span style={{ minWidth: 80 }}>{String(t.topic)}</span>
                  <div style={{ flex: 1, height: 6, background: "#e5e7eb", borderRadius: 3 }}>
                    <div style={{ width: `${score * 100}%`, height: "100%", background: score >= 0.7 ? "#22c55e" : score >= 0.4 ? "#eab308" : "#ef4444", borderRadius: 3 }} />
                  </div>
                  <span style={{ minWidth: 30, textAlign: "right" }}>{Math.round(score * 100)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Dimension averages */}
      {dimRadar != null && (
        <div style={{ padding: 10, background: "#eff6ff", borderRadius: 8, border: "1px solid #bfdbfe" }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>四维度平均</div>
          <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
            {Object.entries(dimRadar).map(([k, v]) => (
              <div key={k} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: v >= 0.7 ? "#16a34a" : v >= 0.4 ? "#ca8a04" : "#dc2626" }}>
                  {Math.round(v * 100)}%
                </div>
                <div style={{ fontSize: 10, color: "#6b7280" }}>
                  {k === "mastery" ? "掌握" : k === "application" ? "应用" : k === "memory" ? "记忆" : "理解"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weak vs known */}
      <div style={{ display: "flex", gap: 12 }}>
        {weakTopics.length > 0 && (
          <div style={{ flex: 1, padding: 10, background: "#fef2f2", borderRadius: 8, border: "1px solid #fecaca" }}>
            <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>薄弱点 ({weakTopics.length})</div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {weakTopics.map((t, i) => <span key={i} style={{ padding: "2px 6px", borderRadius: 8, background: "#fee2e2", fontSize: 10 }}>{t}</span>)}
            </div>
          </div>
        )}
        {knownTopics.length > 0 && (
          <div style={{ flex: 1, padding: 10, background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac" }}>
            <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>已掌握 ({knownTopics.length})</div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {knownTopics.slice(0, 8).map((t, i) => <span key={i} style={{ padding: "2px 6px", borderRadius: 8, background: "#dcfce7", fontSize: 10 }}>{t}</span>)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
