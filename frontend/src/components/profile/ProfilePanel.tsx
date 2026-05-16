import { Brain, Target, Timer, RefreshCw } from "lucide-react";
import type { StudentProfile } from "../../types/baseline";

interface Props {
  profile: StudentProfile;
}

const DIM_LABELS: Record<string, string> = {
  mastery: "掌握",
  application: "应用",
  memory: "记忆",
  understanding: "理解",
};

const DIM_KEYS = ["mastery", "application", "memory", "understanding"] as const;

function dimToValue(dim: string): number {
  if (dim === "high") return 1.0;
  if (dim === "mid") return 0.6;
  return 0.3;
}

function RadarChart({ dimensions }: { dimensions: Record<string, number> }) {
  const cx = 80, cy = 80, r = 60;
  const angles = [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2]; // top, right, bottom, left
  const labels = ["掌握", "应用", "记忆", "理解"];
  const values = DIM_KEYS.map((k) => dimensions[k] ?? 0.33);

  const points = values.map((v, i) => {
    const angle = angles[i] - Math.PI / 2; // rotate so "mastery" is at top
    const px = cx + r * v * Math.cos(angle);
    const py = cy + r * v * Math.sin(angle);
    return `${px},${py}`;
  });

  const gridLevels = [0.33, 0.67, 1.0];

  return (
    <svg width="160" height="160" viewBox="0 0 160 160" style={{ margin: "8px auto", display: "block" }}>
      {/* Grid */}
      {gridLevels.map((level) => (
        <polygon
          key={level}
          points={angles.map((a) => {
            const angle = a - Math.PI / 2;
            return `${cx + r * level * Math.cos(angle)},${cy + r * level * Math.sin(angle)}`;
          }).join(" ")}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="1"
        />
      ))}
      {/* Axes */}
      {angles.map((a, i) => {
        const angle = a - Math.PI / 2;
        const lx = cx + r * Math.cos(angle);
        const ly = cy + r * Math.sin(angle);
        return <line key={i} x1={cx} y1={cy} x2={lx} y2={ly} stroke="rgba(255,255,255,0.15)" strokeWidth="1" />;
      })}
      {/* Data polygon */}
      <polygon
        points={points.join(" ")}
        fill="rgba(96,165,250,0.25)"
        stroke="#60a5fa"
        strokeWidth="2"
      />
      {/* Data points */}
      {points.map((p, i) => {
        const [px, py] = p.split(",").map(Number);
        return <circle key={i} cx={px} cy={py} r="3" fill="#60a5fa" />;
      })}
      {/* Labels */}
      {angles.map((a, i) => {
        const angle = a - Math.PI / 2;
        const lx = cx + (r + 16) * Math.cos(angle);
        const ly = cy + (r + 16) * Math.sin(angle);
        return (
          <text
            key={i}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="central"
            fill="rgba(255,255,255,0.7)"
            fontSize="11"
          >
            {labels[i]}
          </text>
        );
      })}
    </svg>
  );
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
