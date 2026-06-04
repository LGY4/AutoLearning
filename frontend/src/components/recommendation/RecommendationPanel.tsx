import { useState } from "react";
import { Sparkles, Target, Brain, BarChart3, Wand2, Loader2, CheckCircle2 } from "lucide-react";
import { apiPost } from "../../api/client";
import type { Recommendation } from "../../types/baseline";

interface Props {
  recommendations: Recommendation[];
  onGenerated?: () => void;
}

export function RecommendationPanel({ recommendations, onGenerated }: Props) {
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [generatedIds, setGeneratedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate(rec: Recommendation) {
    setGeneratingId(rec.recommendation_id);
    setError(null);
    try {
      await apiPost(`/recommendations/${rec.recommendation_id}/generate`, {});
      setGeneratedIds((prev) => new Set(prev).add(rec.recommendation_id));
      onGenerated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGeneratingId(null);
    }
  }

  if (recommendations.length === 0) {
    return (
      <section className="panel">
        <div className="panel-title">
          <Sparkles size={20} />
          <h2>精准推荐</h2>
        </div>
        <div className="empty-state">暂无推荐，完成学习后将自动生成个性化推荐。</div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-title">
        <Sparkles size={20} />
        <h2>精准推荐</h2>
      </div>
      {error && <div className="page-error" style={{ marginBottom: 8 }}>{error}</div>}
      <div className="recommendation-list">
        {recommendations.map((item) => {
          const reason = item.recommend_reason;
          const mainReason = String(reason.main_reason ?? "匹配当前画像与学习目标");
          const weakPoint = reason.weak_point ? String(reason.weak_point) : null;
          const matchedProfile = reason.matched_profile ? String(reason.matched_profile) : null;
          const evidence = reason.evidence as Record<string, unknown> | undefined;
          const recType = reason.recommendation_type as string | undefined;
          const isSuggested = recType === "suggested_generation";
          const isGenerating = generatingId === item.recommendation_id;
          const isGenerated = generatedIds.has(item.recommendation_id);

          return (
            <article className="recommendation-item" key={item.recommendation_id}>
              <div className="recommendation-header">
                <strong>{item.title}</strong>
                <span className="recommendation-score">{Math.round(item.score * 100)} 分</span>
              </div>
              <p className="recommendation-reason">{mainReason}</p>
              <div className="recommendation-details">
                {weakPoint && (
                  <span className="recommendation-tag">
                    <Target size={12} /> 薄弱点: {weakPoint}
                  </span>
                )}
                {matchedProfile && (
                  <span className="recommendation-tag">
                    <Brain size={12} /> 学习风格: {matchedProfile}
                  </span>
                )}
                {evidence && typeof evidence.total === "number" && (
                  <span className="recommendation-tag">
                    <BarChart3 size={12} /> 匹配度: {Math.round(evidence.total * 100)}%
                  </span>
                )}
                {typeof reason.resource_type === "string" && (
                  <span className="recommendation-tag">
                    类型: {reason.resource_type}
                  </span>
                )}
              </div>
              {isSuggested && (
                <div style={{ marginTop: 8 }}>
                  {isGenerated ? (
                    <span className="recommendation-tag" style={{ color: "#4ade80" }}>
                      <CheckCircle2 size={14} /> 已生成
                    </span>
                  ) : (
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => handleGenerate(item)}
                      disabled={isGenerating}
                    >
                      {isGenerating ? (
                        <><Loader2 size={14} className="video-spinner" /> 生成中...</>
                      ) : (
                        <><Wand2 size={14} /> 生成资源</>
                      )}
                    </button>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
