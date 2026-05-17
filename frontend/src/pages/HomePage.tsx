import { useNavigate } from "react-router-dom";
import { BookOpen, Brain, Compass, Map, MessageSquare, PenTool, TrendingUp } from "lucide-react";
import { useAppContext } from "../context/AppContext";
import { OnboardPanel } from "../components/assessment/OnboardPanel";

interface Props {
  onAuth: () => void;
}

export function HomePage({ onAuth }: Props) {
  const { state } = useAppContext();
  const navigate = useNavigate();
  const { user, profile, recommendations } = state;
  const hasProfile = profile.completeness_score > 0.5;

  if (!user) {
    return (
      <div className="home-page">
        <div className="home-hero">
          <h1>AutoLearning</h1>
          <p className="home-subtitle">AI 驱动的自适应学习系统</p>
          <p className="home-desc">多智能体协作，为你构建个性化学习路径、生成学习资源、智能评测反馈。</p>
          <button type="button" className="home-btn-primary" onClick={onAuth}>开始学习</button>
        </div>
        <div className="home-features">
          <div className="home-feature">
            <Brain size={32} />
            <h3>智能画像</h3>
            <p>四维度评估你的知识掌握度，精准定位薄弱点</p>
          </div>
          <div className="home-feature">
            <Map size={32} />
            <h3>路径规划</h3>
            <p>基于知识图谱自动规划学习路径，循序渐进</p>
          </div>
          <div className="home-feature">
            <BookOpen size={32} />
            <h3>资源生成</h3>
            <p>文档、测验、代码、思维导图、视频一站式生成</p>
          </div>
          <div className="home-feature">
            <PenTool size={32} />
            <h3>智能评测</h3>
            <p>AI 语义评分，实时反馈学习效果</p>
          </div>
        </div>
      </div>
    );
  }

  if (!hasProfile) {
    return (
      <div className="home-page">
        <div className="home-onboard">
          <h2>👋 欢迎，{user.username}</h2>
          <p>完成初始诊断，让系统了解你的知识水平并定制学习方案。</p>
          <OnboardPanel onComplete={() => navigate("/chat")} />
        </div>
      </div>
    );
  }

  return (
    <div className="home-page">
      <div className="home-welcome">
        <h2>欢迎回来，{user.username}</h2>
        {profile.learning_goal.current_goal && (
          <p className="home-current-goal">当前目标：{profile.learning_goal.current_goal}</p>
        )}
      </div>

      <div className="home-shortcuts">
        <button type="button" className="home-shortcut" onClick={() => navigate("/chat")}>
          <MessageSquare size={24} />
          <span>继续对话</span>
        </button>
        <button type="button" className="home-shortcut" onClick={() => navigate("/map")}>
          <Compass size={24} />
          <span>学习地图</span>
        </button>
        <button type="button" className="home-shortcut" onClick={() => navigate("/practice")}>
          <PenTool size={24} />
          <span>开始练习</span>
        </button>
        <button type="button" className="home-shortcut" onClick={() => navigate("/dashboard")}>
          <TrendingUp size={24} />
          <span>数据看板</span>
        </button>
      </div>

      {profile.knowledge_profile.weak_topics.length > 0 && (
        <div className="home-weak-topics">
          <h3>⚠️ 薄弱知识点</h3>
          <div className="home-weak-list">
            {profile.knowledge_profile.weak_topics.slice(0, 5).map((topic) => (
              <span key={topic} className="home-weak-tag">{topic}</span>
            ))}
          </div>
        </div>
      )}

      {recommendations.length > 0 ? (
        <div className="home-recommendations">
          <h3>📚 推荐学习资源</h3>
          <div className="home-rec-list">
            {recommendations.slice(0, 5).map((rec) => (
              <button
                key={rec.recommendation_id}
                type="button"
                className="home-rec-card"
                onClick={() => navigate("/chat")}
              >
                <span className="home-rec-title">{rec.title}</span>
                <span className="home-rec-score">匹配度 {Math.round(rec.score * 100)}%</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="home-empty-rec">
          <p>开始对话或练习，系统将为你推荐个性化学习资源。</p>
        </div>
      )}
    </div>
  );
}
