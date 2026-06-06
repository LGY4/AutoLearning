import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, Brain, Compass, Map, MessageSquare, PenTool, Sparkles, TrendingUp } from "lucide-react";
import { useAppContext } from "../context/AppContext";
import { OnboardPanel } from "../components/assessment/OnboardPanel";
import { buildNextLearningActions, getLearningPathProgress } from "../utils/learningActions";

interface Props {
  onAuth: () => void;
}

export function HomePage({ onAuth }: Props) {
  const { state } = useAppContext();
  const navigate = useNavigate();
  const { user, profile, recommendations, conversations, learningPath } = state;

  // Diagnostic completed = localStorage flag OR completeness_score > 0.5 (covers legacy users)
  const diagnosticDone = useMemo(() => {
    if (!user) return true; // not logged in → don't show diagnostic
    if (localStorage.getItem(`diagnostic_completed_${user.id}`)) return true;
    return profile.completeness_score > 0.5;
  }, [user, profile.completeness_score]);
  const hasProfile = diagnosticDone;
  const overviewStats = [
    { label: "画像完整度", value: `${Math.round(profile.completeness_score * 100)}%` },
    { label: "学习路径", value: `${learningPath.nodes.length || 0} 步` },
    { label: "推荐资源", value: `${recommendations.length} 条` },
    { label: "对话会话", value: `${conversations.length} 个` },
  ];
  const pathProgress = useMemo(() => getLearningPathProgress(learningPath), [learningPath]);
  const nextActions = useMemo(
    () => buildNextLearningActions({ profile, learningPath, recommendations }),
    [learningPath, profile, recommendations]
  );

  if (!user) {
    return (
      <div className="home-page">
        <div className="home-hero home-hero-landing">
          <div className="home-hero-copy">
            <span className="home-badge">
              <Sparkles size={14} />
              AI 自适应学习工作台
            </span>
            <h1>让画像、路径、资源与练习在一个界面里协同工作</h1>
            <p className="home-subtitle">AI 驱动的自适应学习系统</p>
            <p className="home-desc">多智能体协作，为你构建个性化学习路径、生成学习资源、智能评测反馈，并根据每轮交互持续更新学习画像。</p>
            <div className="home-hero-actions">
              <button type="button" className="home-btn-primary" onClick={onAuth}>开始学习</button>
              <button type="button" className="home-btn-secondary" onClick={() => navigate("/chat")}>
                进入工作区
                <ArrowRight size={16} />
              </button>
            </div>
          </div>

          <div className="home-hero-panel">
            <div className="home-hero-metric">
              <span>学习流程</span>
              <strong>画像诊断 → 路径规划 → 资源生成 → 练习反馈</strong>
            </div>
            <div className="home-hero-metric">
              <span>支持形态</span>
              <strong>文档、测验、代码、导图、视频、辅导问答</strong>
            </div>
            <div className="home-hero-metric">
              <span>设计目标</span>
              <strong>用更低认知负担完成从提问到掌握的闭环学习</strong>
            </div>
          </div>
        </div>

        <div className="home-features">
          <div className="home-feature">
            <Brain size={32} />
            <h3>智能画像</h3>
            <p>四维度（掌握度/应用力/记忆力/理解力）动态评估知识水平，精准定位薄弱点</p>
          </div>
          <div className="home-feature">
            <Map size={32} />
            <h3>路径规划</h3>
            <p>基于知识图谱自动规划学习路径，前置依赖检查，循序渐进掌握每个节点</p>
          </div>
          <div className="home-feature">
            <BookOpen size={32} />
            <h3>资源生成</h3>
            <p>8 种类型资源（文档/测验/代码/思维导图/视频/动画/阅读/流程图）一站式 LLM 生成</p>
          </div>
          <div className="home-feature">
            <PenTool size={32} />
            <h3>智能评测</h3>
            <p>AI 语义评分 + 自适应出题，答题后实时更新画像维度和推荐策略</p>
          </div>
        </div>

        <div className="home-how-it-works">
          <h2>工作原理</h2>
          <div className="home-steps">
            <div className="home-step">
              <span className="home-step-num">1</span>
              <h4>诊断定位</h4>
              <p>完成初始诊断测试，系统构建你的四维度知识画像</p>
            </div>
            <div className="home-step">
              <span className="home-step-num">2</span>
              <h4>路径规划</h4>
              <p>AI 根据画像和目标生成个性化学习路径</p>
            </div>
            <div className="home-step">
              <span className="home-step-num">3</span>
              <h4>资源生成</h4>
              <p>按需生成文档、视频、练习等学习资源</p>
            </div>
            <div className="home-step">
              <span className="home-step-num">4</span>
              <h4>自适应反馈</h4>
              <p>答题后画像自动更新，推荐策略实时调整</p>
            </div>
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
      <div className="home-dashboard-hero">
        <div className="home-welcome">
          <span className="home-badge">
            <Sparkles size={14} />
            学习中枢
          </span>
          <h2>欢迎回来，{user.username}</h2>
          {profile.learning_goal.current_goal && (
            <p className="home-current-goal">当前目标：{profile.learning_goal.current_goal}</p>
          )}
        </div>

        <div className="home-overview-grid">
          {overviewStats.map((item) => (
            <article className="home-overview-card" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </div>
      </div>

      <section className="home-next-panel" aria-label="下一步学习行动">
        <div className="home-path-progress-card">
          <div className="home-path-progress-head">
            <span className="home-badge">
              <Compass size={14} />
              今日推进
            </span>
            <strong>{pathProgress.summary}</strong>
          </div>
          <div className="home-path-progress-track">
            <div className="home-path-progress-fill" style={{ width: `${pathProgress.percent}%` }} />
          </div>
          <div className="home-path-progress-meta">
            <span>{pathProgress.nextLabel}</span>
            <span>{pathProgress.percent}%</span>
          </div>
        </div>

        <div className="home-next-actions">
          {nextActions.map((action) => (
            <button
              key={`${action.kind}-${action.title}`}
              type="button"
              className={`home-next-action ${action.kind}`}
              onClick={() => navigate(action.to)}
            >
              <span className="home-next-action-label">{action.label}</span>
              <strong>{action.title}</strong>
              <span className="home-next-action-desc">{action.description}</span>
              <span className="home-next-action-cta">
                {action.cta}
                <ArrowRight size={14} />
              </span>
            </button>
          ))}
        </div>
      </section>

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

      <div className="home-dashboard-grid">
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

        <div className="home-focus-card">
          <h3>当前画像摘要</h3>
          <div className="home-focus-list">
            <div>
              <span>当前水平</span>
              <strong>{profile.knowledge_profile.overall_level || "unknown"}</strong>
            </div>
            <div>
              <span>学习风格</span>
              <strong>{profile.learning_preference.learning_style}</strong>
            </div>
            <div>
              <span>活跃时段</span>
              <strong>{profile.learning_behavior.active_period}</strong>
            </div>
            <div>
              <span>建议时长</span>
              <strong>{profile.learning_behavior.average_study_minutes} 分钟 / 次</strong>
            </div>
          </div>
        </div>
      </div>

      {recommendations.length > 0 ? (
        <div className="home-recommendations">
          <h3>📚 推荐学习资源</h3>
          <div className="home-rec-list">
            {recommendations.slice(0, 5).map((rec) => (
              <button
                key={rec.recommendation_id}
                type="button"
                className="home-rec-card"
                onClick={() => navigate(`/chat?topic=${encodeURIComponent(rec.title)}`)}
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
