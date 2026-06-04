import { Brain, Target, Timer, RefreshCw } from "lucide-react";
import { RadarChart, DIM_KEYS, dimToValue } from "../common/RadarChart";
import type { StudentProfile } from "../../types/baseline";

interface Props {
  profile: StudentProfile;
}

function ReviewReminders({ profile }: { profile: StudentProfile }) {
  const topicDims = profile.knowledge_profile.topic_dimensions;
  if (!topicDims || Object.keys(topicDims).length === 0) return null;

  const reviewTopics = Object.entries(topicDims)
    .filter(([, dims]) => dims.memory === "low" || dims.memory === "mid")
    .sort(([, a], [, b]) => dimToValue(a.memory) - dimToValue(b.memory));

  if (reviewTopics.length === 0) return null;

  return (
    <div className="profile-review">
      <h4><RefreshCw size={14} /> 待复习</h4>
      {reviewTopics.map(([topic, dims]) => (
        <div key={topic} className="profile-review-item">
          <span className="profile-review-topic">{topic}</span>
          <span className="profile-review-dim">记忆: {dims.memory === "low" ? "薄弱" : "一般"}</span>
        </div>
      ))}
    </div>
  );
}

export function ProfilePanel({ profile }: Props) {
  // Compute average dimensions for radar chart
  const topicDims = profile.knowledge_profile.topic_dimensions;
  let avgDimensions: Record<string, number> = { mastery: 0.33, application: 0.33, memory: 0.33, understanding: 0.33 };
  if (topicDims && Object.keys(topicDims).length > 0) {
    const entries = Object.values(topicDims);
    for (const key of DIM_KEYS) {
      const sum = entries.reduce((acc, d) => acc + dimToValue(d[key]), 0);
      avgDimensions[key] = sum / entries.length;
    }
  }

  return (
    <section className="panel">
      <div className="panel-title">
        <Brain size={20} />
        <h2>学生画像</h2>
      </div>
      <div className="profile-grid">
        <div>
          <span>专业 / 年级</span>
          <strong>
            {profile.basic_info.major} / {profile.basic_info.grade}
          </strong>
        </div>
        <div>
          <span>画像完整度</span>
          <strong>{Math.round(profile.completeness_score * 100)}%</strong>
        </div>
        <div>
          <span>当前基础</span>
          <strong>{profile.knowledge_profile.overall_level}</strong>
        </div>
        <div>
          <span>学习风格</span>
          <strong>{profile.learning_preference.learning_style}</strong>
        </div>
      </div>

      {/* Radar chart for four dimensions */}
      {topicDims && Object.keys(topicDims).length > 0 && (
        <div className="profile-radar">
          <h4>四维度评估</h4>
          <RadarChart dimensions={avgDimensions} />
        </div>
      )}

      <div className="inline-list">
        {profile.knowledge_profile.weak_topics.map((topic) => (
          <span key={topic}>{topic}</span>
        ))}
      </div>
      <div className="summary-row">
        <Target size={18} />
        <p>{profile.learning_goal.current_goal}</p>
      </div>
      <div className="summary-row">
        <Timer size={18} />
        <p>建议学习时长：{profile.learning_behavior.average_study_minutes} 分钟 / 次</p>
      </div>

      {/* Review reminders */}
      <ReviewReminders profile={profile} />

      {profile.cognitive_profile && (
        <div className="profile-cognitive">
          <h4>认知特征</h4>
          <div className="profile-grid">
            <div><span>认知风格</span><strong>{profile.cognitive_profile.cognitive_style}</strong></div>
            <div><span>抽象理解</span><strong>{profile.cognitive_profile.abstract_understanding}</strong></div>
            <div><span>动手能力</span><strong>{profile.cognitive_profile.hands_on_ability}</strong></div>
            <div><span>阅读耐心</span><strong>{profile.cognitive_profile.reading_patience}</strong></div>
          </div>
        </div>
      )}
    </section>
  );
}
