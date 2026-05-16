import { useState, useEffect, useCallback } from "react";

interface AssessmentSnapshot {
  timestamp: string;
  mastery_score: number;
  confidence: number;
  stage: string;
  weak_point_count: number;
  weak_topics: string[];
}

const STORAGE_KEY = "autolearning_assess_history";
const MAX_SNAPSHOTS = 20;

function loadHistory(): AssessmentSnapshot[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(snapshots: AssessmentSnapshot[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots.slice(0, MAX_SNAPSHOTS)));
}

export function addAssessmentSnapshot(data: {
  mastery_score: number;
  confidence: number;
  stage?: string;
  weak_points?: Array<{ topic: string }>;
}) {
  const history = loadHistory();
  const snapshot: AssessmentSnapshot = {
    timestamp: new Date().toISOString(),
    mastery_score: data.mastery_score,
    confidence: data.confidence,
    stage: data.stage || "unknown",
    weak_point_count: data.weak_points?.length || 0,
    weak_topics: (data.weak_points || []).map((w) => w.topic),
  };
  history.unshift(snapshot);
  saveHistory(history);
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
  const [history, setHistory] = useState<AssessmentSnapshot[]>([]);

  useEffect(() => {
    setHistory(loadHistory());
  }, []);

  const clearHistory = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setHistory([]);
  }, []);

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
          <div key={snap.timestamp} className="assess-history-row">
            <span className="assess-history-date">{formatDate(snap.timestamp)}</span>
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
      <div className="assess-history-actions">
        <button className="assess-history-btn danger" onClick={clearHistory} type="button">
          清除历史
        </button>
      </div>
    </div>
  );
}
