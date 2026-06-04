import { useState, useEffect, useCallback } from "react";
import { apiGet, apiPost } from "../../api/client";
import { useAppContext } from "../../context/AppContext";

interface AssessmentSnapshot {
  id: string;
  mastery_score: number;
  confidence: number;
  stage: string;
  weak_point_count: number;
  weak_topics: string[];
  created_at: string;
}

export async function addAssessmentSnapshot(data: {
  mastery_score: number;
  confidence: number;
  stage?: string;
  weak_points?: Array<{ topic: string }>;
}) {
  try {
    await apiPost("/learning-records/assessment-snapshot", {
      mastery_score: data.mastery_score,
      confidence: data.confidence,
      stage: data.stage || "unknown",
      weak_point_count: data.weak_points?.length || 0,
      weak_topics: (data.weak_points || []).map((w) => w.topic),
    });
  } catch {
    // Silently fail — assessment still works, just no history persisted
  }
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function DeltaBadge({ current, previous }: { current: number; previous: number }) {
  const diff = Math.round((current - previous) * 100);
  if (diff === 0) return <span className="assess-history-delta same">-</span>;
  const cls = diff > 0 ? "up" : "down";
  return <span className={`assess-history-delta ${cls}`}>{diff > 0 ? "+" : ""}{diff}%</span>;
}

export function AssessmentHistory() {
  const { state } = useAppContext();
  const [history, setHistory] = useState<AssessmentSnapshot[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    if (!state.user) { setLoading(false); return; }
    try {
      const res = await apiGet<AssessmentSnapshot[]>("/learning-records/assessment-history");
      setHistory(res);
    } catch {
      // Fall back to empty
    } finally {
      setLoading(false);
    }
  }, [state.user]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  if (loading) return <div className="assess-history-empty">加载历史记录...</div>;
  if (history.length === 0) {
    return <div className="assess-history-empty">暂无评估历史记录</div>;
  }

  return (
    <div className="assess-history">
      <h4>评估历史（{history.length} 次）</h4>
      <div className="assess-history-row header">
        <span>时间</span>
        <span>掌握度</span>
        <span>置信度</span>
        <span>变化</span>
      </div>
      {history.map((snap, i) => {
        const prev = history[i + 1];
        return (
          <div key={snap.id} className="assess-history-row">
            <span className="assess-history-date">{formatDate(snap.created_at)}</span>
            <span className="assess-history-score">{Math.round(snap.mastery_score * 100)}%</span>
            <span className="assess-history-prev">{Math.round(snap.confidence * 100)}%</span>
            {prev ? (
              <DeltaBadge current={snap.mastery_score} previous={prev.mastery_score} />
            ) : (
              <span className="assess-history-delta same">-</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
