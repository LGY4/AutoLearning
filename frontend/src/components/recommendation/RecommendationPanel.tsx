import { Sparkles, Target, Brain, BarChart3 } from "lucide-react";
import type { Recommendation } from "../../types/baseline";

interface Props {
  recommendations: Recommendation[];
}

export function RecommendationPanel({ recommendations }: Props) {
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
      <div className="recommendation-list">
        {recommendations.map((item) => {
          const reason = item.recommend_reason;
          const mainReason = String(reason.main_reason ?? "匹配当前画像与学习目标");
          const weakPoint = reason.weak_point ? String(reason.weak_point) : null;
          const matchedProfile = reason.matched_profile ? String(reason.matched_profile) : null;
          const evidence = reason.evidence as Record<string, unknown> | undefined;

          return (
            <article className="recommendation-item" key={item.recommendation_id}>
              <div className="recommendation-header">
                <strong>{item.title}</strong>
                <span className="recommendation-score">{Math.round(item.score)} 分</span>
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
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
