import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, Clock, Compass, PenTool, Target, TrendingUp, AlertTriangle, Activity } from "lucide-react";
import { useAppContext } from "../context/AppContext";
import { apiGet } from "../api/client";
import { ProfilePanel } from "../components/profile/ProfilePanel";
import { RadarChart, DIM_KEYS, DIM_LABELS, dimToValue } from "../components/common/RadarChart";
import { AssessmentPanel } from "../components/assessment/AssessmentPanel";
import { RecommendationPanel } from "../components/recommendation/RecommendationPanel";
import { Spinner } from "../components/common/Spinner";
import type { Recommendation } from "../types/baseline";

interface LearningSummary {
  total_count: number;
  avg_score: number;
  total_duration_seconds: number;
  weak_points: string[];
  recent_records: Array<{ knowledge_point: string; score: number; created_at: string }>;
}

interface WorkflowLog {
  task_id: string;
  agent_name: string;
  status: string;
  result?: unknown;
  error?: string;
  started_at?: string;
  completed_at?: string;
}

interface WorkflowEvent {
  event_type: string;
  agent_name: string;
  message?: string;
  timestamp: string;
  data?: unknown;
}

interface WorkflowDetail {
  workflow_id: string;
  status: string;
  tasks: WorkflowLog[];
  events: WorkflowEvent[];
}

export function DashboardPage() {
  const { state, dispatch } = useAppContext();
  const { profile, recommendations, resources } = state;
  const navigate = useNavigate();
  const [summary, setSummary] = useState<LearningSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshRecommendations = useCallback(async () => {
    try {
      const recs = await apiGet<Recommendation[]>("/recommendations/");
      dispatch({ type: "SET_RECOMMENDATIONS", payload: recs });
    } catch { /* silent */ }
  }, [dispatch]);

  // Workflow viewer
  const [workflowId, setWorkflowId] = useState("");
  const [workflowDetail, setWorkflowDetail] = useState<WorkflowDetail | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  const handleLoadWorkflow = useCallback(async () => {
    if (!workflowId.trim()) return;
    setWorkflowLoading(true);
    setWorkflowError(null);
    setWorkflowDetail(null);
    try {
      const wfId = workflowId.trim();
      const [wf, logs, events] = await Promise.all([
        apiGet<WorkflowDetail>(`/agent-workflows/${wfId}`),
        apiGet<WorkflowLog[]>(`/agent-workflows/${wfId}/logs`).catch(() => []),
        apiGet<WorkflowEvent[]>(`/agent-workflows/${wfId}/events`).catch(() => []),
      ]);
      // Merge logs and events into the workflow detail
      if (logs.length > 0 && (!wf.tasks || wf.tasks.length === 0)) wf.tasks = logs;
      if (events.length > 0 && (!wf.events || wf.events.length === 0)) wf.events = events;
      setWorkflowDetail(wf);
    } catch (e) {
      setWorkflowError(e instanceof Error ? e.message : "加载工作流失败");
    } finally {
      setWorkflowLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    if (!state.user) { setLoading(false); return; }
    setLoading(true);
    apiGet<LearningSummary>("/learning-records/summary")
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [state.user]);

  const hasProfile = profile.completeness_score > 0;
  const masteryLevel = profile.knowledge_profile.overall_level;
  const weakTopics = profile.knowledge_profile.weak_topics;
  const knownTopics = profile.knowledge_profile.known_topics ?? [];
  const masteryEntries = Object.entries(profile.knowledge_profile.mastery_level ?? {});
  const topicDims = profile.knowledge_profile.topic_dimensions;

  // Compute average dimensions for radar
  const avgDimensions: Record<string, number> = { mastery: 0.33, application: 0.33, memory: 0.33, understanding: 0.33 };
  if (topicDims && Object.keys(topicDims).length > 0) {
    const entries = Object.values(topicDims);
    for (const key of DIM_KEYS) {
      const sum = entries.reduce((acc, d) => acc + dimToValue(d[key]), 0);
      avgDimensions[key] = sum / entries.length;
    }
  }

  const DIM_LEVEL_LABELS: Record<string, string> = { high: "高", mid: "中", low: "低" };

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
    return `${(seconds / 3600).toFixed(1)}小时`;
  };

  if (loading) return <div className="page-center"><Spinner /></div>;

  return (
    <div className="dashboard-page">
      <h1 className="dashboard-title">📊 数据看板</h1>

      {!hasProfile ? (
        <div className="dashboard-empty">
          <p>完成初始诊断后，学习数据将在此展示。</p>
          <button type="button" className="dashboard-btn" onClick={() => navigate("/")}>去完成诊断</button>
        </div>
      ) : (
        <>
          {/* Stats cards */}
          <div className="dashboard-stats">
            <div className="dashboard-stat-card">
              <BookOpen size={20} />
              <div>
                <span className="dashboard-stat-value">{summary?.total_count ?? resources.length}</span>
                <span className="dashboard-stat-label">学习次数</span>
              </div>
            </div>
            <div className="dashboard-stat-card">
              <Target size={20} />
              <div>
                <span className="dashboard-stat-value">{summary?.avg_score != null ? Math.round(summary.avg_score) : "—"}%</span>
                <span className="dashboard-stat-label">平均分</span>
              </div>
            </div>
            <div className="dashboard-stat-card">
              <Clock size={20} />
              <div>
                <span className="dashboard-stat-value">{summary?.total_duration_seconds ? formatDuration(summary.total_duration_seconds) : "—"}</span>
                <span className="dashboard-stat-label">累计时长</span>
              </div>
            </div>
            <div className="dashboard-stat-card">
              <TrendingUp size={20} />
              <div>
                <span className="dashboard-stat-value">{masteryLevel || "—"}</span>
                <span className="dashboard-stat-label">整体水平</span>
              </div>
            </div>
          </div>

          <div className="dashboard-grid">
            {/* Active goal & target course */}
            {(profile.learning_goal?.current_goal || profile.learning_goal?.target_course) && (
              <div className="dashboard-card">
                <h3><Target size={18} /> 学习目标</h3>
                <div className="dashboard-pref-grid">
                  {profile.learning_goal?.current_goal && (
                    <div className="dashboard-pref-item">
                      <span className="dashboard-pref-label">当前目标</span>
                      <span className="dashboard-pref-value">{profile.learning_goal.current_goal}</span>
                    </div>
                  )}
                  {profile.learning_goal?.target_course && (
                    <div className="dashboard-pref-item">
                      <span className="dashboard-pref-label">目标课程</span>
                      <span className="dashboard-pref-value">{profile.learning_goal.target_course}</span>
                    </div>
                  )}
                  {profile.learning_goal?.target_level && (
                    <div className="dashboard-pref-item">
                      <span className="dashboard-pref-label">目标水平</span>
                      <span className="dashboard-pref-value">{profile.learning_goal.target_level}</span>
                    </div>
                  )}
                  {profile.learning_goal?.deadline && (
                    <div className="dashboard-pref-item">
                      <span className="dashboard-pref-label">截止日期</span>
                      <span className="dashboard-pref-value">{profile.learning_goal.deadline}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Mastery bars */}
            {masteryEntries.length > 0 && (
              <div className="dashboard-card">
                <h3>📈 知识掌握度</h3>
                <div className="dashboard-mastery-list">
                  {masteryEntries.sort(([, a], [, b]) => (b as number) - (a as number)).slice(0, 8).map(([topic, value]) => (
                    <div key={topic} className="dashboard-mastery-item">
                      <span className="dashboard-mastery-name">{topic}</span>
                      <div className="dashboard-mastery-bar">
                        <div
                          className={`dashboard-mastery-fill ${(value as number) >= 0.7 ? "high" : (value as number) >= 0.4 ? "mid" : "low"}`}
                          style={{ width: `${Math.round((value as number) * 100)}%` }}
                        />
                      </div>
                      <span className="dashboard-mastery-pct">{Math.round((value as number) * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Radar chart (profile) */}
            <div className="dashboard-card">
              <h3>🎯 学生画像</h3>
              <ProfilePanel profile={profile} />
            </div>

            {/* Four-dimension radar chart */}
            {topicDims && Object.keys(topicDims).length > 0 && (
              <div className="dashboard-card dashboard-radar-card">
                <h3>📊 四维度评估</h3>
                <RadarChart dimensions={avgDimensions} size={200} />
                <div className="dashboard-radar-dims">
                  {DIM_KEYS.map((k) => (
                    <div key={k} className="dashboard-radar-dim">
                      <span className="dashboard-radar-dim-label">{DIM_LABELS[k]}</span>
                      <span className="dashboard-radar-dim-value">{Math.round(avgDimensions[k] * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Learning preferences */}
            <div className="dashboard-card">
              <h3>📖 学习偏好</h3>
              <div className="dashboard-pref-grid">
                <div><span>学习风格</span><strong>{profile.learning_preference.learning_style}</strong></div>
                <div><span>难度偏好</span><strong>{profile.learning_preference.difficulty_preference}</strong></div>
                <div><span>资源偏好</span><strong>{Object.keys(profile.learning_preference.resource_preference ?? {}).join("、") || "—"}</strong></div>
                <div><span>建议时长</span><strong>{profile.learning_behavior.average_study_minutes} 分钟/次</strong></div>
                <div><span>活跃时段</span><strong>{profile.learning_behavior.active_period}</strong></div>
              </div>
            </div>

            {/* Cognitive profile */}
            {profile.cognitive_profile && (
              <div className="dashboard-card">
                <h3>🧠 认知特征</h3>
                <div className="dashboard-cog-grid">
                  <div><span>认知风格</span><strong>{profile.cognitive_profile.cognitive_style}</strong></div>
                  <div><span>抽象理解</span><strong>{DIM_LEVEL_LABELS[profile.cognitive_profile.abstract_understanding] || profile.cognitive_profile.abstract_understanding}</strong></div>
                  <div><span>动手能力</span><strong>{DIM_LEVEL_LABELS[profile.cognitive_profile.hands_on_ability] || profile.cognitive_profile.hands_on_ability}</strong></div>
                  <div><span>阅读耐心</span><strong>{DIM_LEVEL_LABELS[profile.cognitive_profile.reading_patience] || profile.cognitive_profile.reading_patience}</strong></div>
                </div>
              </div>
            )}

            {/* Topic dimension table */}
            {topicDims && Object.keys(topicDims).length > 0 && (
              <div className="dashboard-card dashboard-card-full">
                <h3>📋 知识点四维度</h3>
                <div className="dashboard-dim-table">
                  <div className="dashboard-dim-header">
                    <span>知识点</span>
                    <span>掌握</span>
                    <span>应用</span>
                    <span>记忆</span>
                    <span>理解</span>
                    <span>综合</span>
                  </div>
                  {Object.entries(topicDims).map(([topic, dim]) => {
                    const scores = [dim.mastery, dim.application, dim.memory, dim.understanding];
                    const avg = scores.filter((s) => s === "high").length * 3 + scores.filter((s) => s === "mid").length * 2 + scores.filter((s) => s === "low").length;
                    const pct = Math.round((avg / 12) * 100);
                    return (
                      <div className="dashboard-dim-row" key={topic}>
                        <span className="dashboard-dim-topic">{topic}</span>
                        <span className={`dashboard-dim-cell ${dim.mastery}`}>{DIM_LEVEL_LABELS[dim.mastery] || dim.mastery}</span>
                        <span className={`dashboard-dim-cell ${dim.application}`}>{DIM_LEVEL_LABELS[dim.application] || dim.application}</span>
                        <span className={`dashboard-dim-cell ${dim.memory}`}>{DIM_LEVEL_LABELS[dim.memory] || dim.memory}</span>
                        <span className={`dashboard-dim-cell ${dim.understanding}`}>{DIM_LEVEL_LABELS[dim.understanding] || dim.understanding}</span>
                        <span className="dashboard-dim-cell">
                          <div className="dashboard-dim-bar-container">
                            <div className="dashboard-dim-bar" style={{ width: `${pct}%` }} />
                            <span className="dashboard-dim-bar-label">{pct}%</span>
                          </div>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Weak points */}
            {weakTopics.length > 0 && (
              <div className="dashboard-card">
                <h3><AlertTriangle size={16} /> 薄弱知识点</h3>
                <div className="dashboard-weak-list">
                  {weakTopics.map((topic) => (
                    <div key={topic} className="dashboard-weak-item">
                      <span>{topic}</span>
                      <button type="button" className="dashboard-weak-btn" onClick={() => navigate(`/practice?knowledge_point=${encodeURIComponent(topic)}`)}>
                        去练习
                      </button>
                    </div>
                  ))}
                </div>
                <button type="button" className="dashboard-btn" onClick={() => navigate("/practice")}>
                  一键生成薄弱点强化练习
                </button>
              </div>
            )}

            {/* Recommendations */}
            {recommendations.length > 0 && (
              <div className="dashboard-card">
                <h3>💡 学习推荐</h3>
                <RecommendationPanel recommendations={recommendations} onGenerated={refreshRecommendations} />
              </div>
            )}

            {/* Recent records */}
            {summary?.recent_records && summary.recent_records.length > 0 && (
              <div className="dashboard-card">
                <h3>📋 最近学习</h3>
                <div className="dashboard-recent-list">
                  {summary.recent_records.slice(0, 5).map((r, i) => (
                    <div key={i} className="dashboard-recent-item">
                      <span className="dashboard-recent-kp">{r.knowledge_point}</span>
                      <span className={`dashboard-recent-score ${r.score >= 60 ? "pass" : "fail"}`}>{r.score}分</span>
                      <span className="dashboard-recent-time">{new Date(r.created_at).toLocaleDateString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Assessment */}
            <div className="dashboard-card dashboard-card-full">
              <AssessmentPanel />
            </div>

            {/* Workflow viewer */}
            <div className="dashboard-card dashboard-card-full">
              <h3><Activity size={16} /> 工作流查看器</h3>
              <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                <input
                  className="res-lib-search"
                  placeholder="输入工作流 ID"
                  value={workflowId}
                  onChange={(e) => setWorkflowId(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleLoadWorkflow()}
                  style={{ flex: 1 }}
                />
                <button className="dashboard-btn" onClick={handleLoadWorkflow} disabled={workflowLoading}>
                  {workflowLoading ? "加载中..." : "查看"}
                </button>
              </div>
              {workflowError && <div className="page-error">{workflowError}</div>}
              {workflowDetail && (
                <div className="dashboard-recent-list">
                  <div className="dashboard-recent-item">
                    <span className="dashboard-recent-kp">状态</span>
                    <span className={`dashboard-recent-score ${workflowDetail.status === "completed" ? "pass" : "fail"}`}>{workflowDetail.status}</span>
                  </div>
                  {workflowDetail.tasks?.map((t) => (
                    <div key={t.task_id} className="dashboard-recent-item">
                      <span className="dashboard-recent-kp">{t.agent_name}</span>
                      <span className={`dashboard-recent-score ${t.status === "completed" ? "pass" : ""}`}>{t.status}</span>
                    </div>
                  ))}
                  {workflowDetail.events?.slice(-5).map((ev, i) => (
                    <div key={i} className="dashboard-recent-item">
                      <span className="dashboard-recent-kp">{ev.event_type}</span>
                      <span className="dashboard-recent-time">{ev.message ?? ev.agent_name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Quick actions */}
          <div className="dashboard-actions">
            <button type="button" className="dashboard-action-btn" onClick={() => navigate("/map")}>
              <Compass size={20} />
              <span>学习地图</span>
            </button>
            <button type="button" className="dashboard-action-btn" onClick={() => navigate("/practice")}>
              <PenTool size={20} />
              <span>开始练习</span>
            </button>
            <button type="button" className="dashboard-action-btn" onClick={() => navigate("/chat")}>
              <BookOpen size={20} />
              <span>继续学习</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}
