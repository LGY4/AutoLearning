import { useState, useEffect } from "react";
import { apiGet } from "../../api/client";
import { useAppContext } from "../../context/AppContext";
import { AssessmentHistory, addAssessmentSnapshot } from "./AssessmentHistory";

interface WeakPoint {
  topic: string;
  severity: string;
  suggestion: string;
}

interface ReviewRec {
  topic: string;
  priority: number;
  method: string;
  reason: string;
}

export interface AssessmentData {
  status: string;
  is_cold_start: boolean;
  confidence: number;
  data_sources: string[];
  mastery_score: number;
  knowledge_mastery: Record<string, number>;
  weak_points: WeakPoint[];
  learning_style: { primary_style: string; analysis: string };
  progress: { completion_rate: number; velocity?: string; quality?: string; analysis: string };
  review_recommendations: ReviewRec[];
  next_suggestions: string[];
  next_steps: string[];
  overall_score: number;
  summary: string;
  stage?: string;
  message?: string;
}

const STAGE_LABELS: Record<string, string> = {
  cold_start: "初始评估",
  developing: "发展中评估",
  mature: "成熟评估",
};

const SOURCE_LABELS: Record<string, string> = {
  profile: "学生画像",
  diagnostic: "诊断测验",
  learning_path: "学习路径",
  learning_records: "学习记录",
};

function ConfidenceBadge({ confidence, stage }: { confidence: number; stage?: string }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 70 ? "#4ade80" : pct >= 40 ? "#facc15" : "#f97316";
  return (
    <span className="assess-confidence" style={{ borderColor: color, color }}>
      {STAGE_LABELS[stage || ""] || "评估"} · 置信度 {pct}%
    </span>
  );
}

function MasteryBar({ topic, score }: { topic: string; score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? "#4ade80" : pct >= 40 ? "#facc15" : "#f97316";
  return (
    <div className="assess-mastery-row">
      <span className="assess-mastery-topic">{topic}</span>
      <div className="assess-mastery-bar">
        <div className="assess-mastery-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="assess-mastery-pct">{pct}%</span>
    </div>
  );
}

export function AssessmentPanel() {
  const { state } = useAppContext();
  const [data, setData] = useState<AssessmentData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const userId = state.user?.id;

  useEffect(() => {
    if (!userId) return;
    setLoading(true);
    apiGet(`/learning/assess`)
      .then((res) => {
        const d = res as AssessmentData;
        setData(d);
        setError(null);
        if (d.status !== "no_data") {
          addAssessmentSnapshot({
            mastery_score: d.mastery_score,
            confidence: d.confidence,
            stage: d.stage,
            weak_points: d.weak_points,
          });
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [userId]);

  if (!userId) return null;
  if (loading) return <div className="assess-panel assess-loading">正在生成评估...</div>;
  if (error) return <div className="assess-panel assess-error">评估加载失败: {error}</div>;
  if (!data) return null;

  // No data at all — prompt onboarding
  if (data.status === "no_data") {
    return (
      <div className="assess-panel assess-cold-start">
        <div className="assess-header">
          <h3>初始学习评估</h3>
          <ConfidenceBadge confidence={0} stage="cold_start" />
        </div>
        <p className="assess-hint">
          完成初始诊断测验后，系统将生成个性化学习评估。后续评估会随学习记录自动优化。
        </p>
        <div className="assess-suggestions">
          {(data.next_suggestions || data.next_steps || []).map((s, i) => (
            <div key={i} className="assess-suggestion-item">{s}</div>
          ))}
        </div>
      </div>
    );
  }

  const masteryEntries = Object.entries(data.knowledge_mastery || {})
    .sort(([, a], [, b]) => a - b);

  return (
    <div className={`assess-panel ${data.is_cold_start ? "assess-cold-start" : ""}`}>
      <div className="assess-header">
        <h3>学习评估</h3>
        <ConfidenceBadge confidence={data.confidence} stage={data.stage} />
      </div>

      {data.is_cold_start && (
        <p className="assess-hint">
          当前为初始评估，基于诊断测验结果。继续学习后评估会自动优化。
        </p>
      )}

      {data.summary && <p className="assess-summary">{data.summary}</p>}

      {/* Data sources */}
      <div className="assess-sources">
        数据来源：{(data.data_sources || []).map((s) => SOURCE_LABELS[s] || s).join("、")}
      </div>

      {/* Mastery score */}
      <div className="assess-overall">
        <span>综合掌握度</span>
        <span className="assess-score">{Math.round(data.mastery_score * 100)}%</span>
      </div>

      {/* Per-topic mastery */}
      {masteryEntries.length > 0 && (
        <div className="assess-mastery-section">
          <h4>知识点掌握度</h4>
          {masteryEntries.map(([topic, score]) => (
            <MasteryBar key={topic} topic={topic} score={score} />
          ))}
        </div>
      )}

      {/* Weak points */}
      {data.weak_points && data.weak_points.length > 0 && (
        <div className="assess-weak-section">
          <h4>薄弱点</h4>
          {data.weak_points.map((wp, i) => (
            <div key={i} className="assess-weak-item">
              <span className={`assess-severity assess-severity-${wp.severity}`}>{wp.severity}</span>
              <span className="assess-weak-topic">{wp.topic}</span>
              <span className="assess-weak-suggestion">{wp.suggestion}</span>
            </div>
          ))}
        </div>
      )}

      {/* Next suggestions */}
      {data.next_suggestions && data.next_suggestions.length > 0 && (
        <div className="assess-next-section">
          <h4>下一步建议</h4>
          {data.next_suggestions.map((s, i) => (
            <div key={i} className="assess-next-item">{s}</div>
          ))}
        </div>
      )}

      {/* Assessment history */}
      <AssessmentHistory />
    </div>
  );
}
