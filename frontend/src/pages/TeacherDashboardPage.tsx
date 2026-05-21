import { useEffect, useState } from "react";
import { BarChart3, Target, Users, AlertTriangle, Send, TrendingUp, Zap } from "lucide-react";
import { apiGet, apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";

interface StudentSummary {
  user_id: string;
  username: string;
  overall_level: string;
  weak_points: string[];
  avg_score: number;
  completed_nodes: number;
  total_nodes: number;
}

interface GroupStats {
  total_students: number;
  avg_score: number;
  common_weak_points: Array<{ topic: string; count: number }>;
  level_distribution: Record<string, number>;
  students: StudentSummary[];
}

export function TeacherDashboardPage() {
  const { state } = useAppContext();
  const [stats, setStats] = useState<GroupStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [pushTopic, setPushTopic] = useState("");
  const [pushing, setPushing] = useState(false);

  useEffect(() => {
    loadStats();
  }, []);

  async function loadStats() {
    setLoading(true);
    try {
      // Simulated group stats (demo mode)
      const data: GroupStats = {
        total_students: 28,
        avg_score: 76.5,
        common_weak_points: [
          { topic: "递归算法", count: 22 },
          { topic: "指针操作", count: 19 },
          { topic: "动态规划", count: 18 },
          { topic: "图算法", count: 15 },
          { topic: "并发编程", count: 12 },
        ],
        level_distribution: { "优秀(>85%)": 5, "良好(70-85%)": 12, "及格(60-70%)": 8, "需努力(<60%)": 3 },
        students: [
          { user_id: "1", username: "张三", overall_level: "优秀", weak_points: ["动态规划"], avg_score: 92, completed_nodes: 18, total_nodes: 20 },
          { user_id: "2", username: "李四", overall_level: "良好", weak_points: ["递归算法", "图算法"], avg_score: 78, completed_nodes: 14, total_nodes: 20 },
          { user_id: "3", username: "王五", overall_level: "及格", weak_points: ["指针操作", "并发编程"], avg_score: 64, completed_nodes: 10, total_nodes: 20 },
          { user_id: "4", username: "赵六", overall_level: "需努力", weak_points: ["递归算法", "动态规划", "图算法"], avg_score: 45, completed_nodes: 6, total_nodes: 20 },
        ],
      };
      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  }

  async function handlePushTask() {
    if (!pushTopic.trim()) return;
    setPushing(true);
    try {
      await apiPost("/courses/goals", {
        goal_title: `[紧急任务] ${pushTopic}`,
        goal_description: "教师统一推送的强化练习任务",
        target_level: "urgent",
      });
      setPushTopic("");
    } catch { /* demo */ }
    finally { setPushing(false); }
  }

  if (loading) return <div className="page-loading">加载中...</div>;

  const levelColors: Record<string, string> = {
    "优秀(>85%)": "#4ade80",
    "良好(70-85%)": "#60a5fa",
    "及格(60-70%)": "#facc15",
    "需努力(<60%)": "#f87171",
  };

  return (
    <div className="page-container" style={{ maxWidth: 1200 }}>
      <div className="page-header">
        <h1><Users size={24} /> 教师看板</h1>
        <span className="tag" style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc" }}>
          {stats?.total_students ?? 0} 名学生
        </span>
      </div>

      {/* Stats row */}
      <div className="profile-stats" style={{ marginBottom: 24 }}>
        <div className="stat-item">
          <span className="stat-label">平均分</span>
          <span className="stat-value">{stats?.avg_score ?? 0}%</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">总人数</span>
          <span className="stat-value">{stats?.total_students ?? 0}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">需关注</span>
          <span className="stat-value" style={{ color: "#f87171" }}>
            {stats?.level_distribution["需努力(<60%)"] ?? 0} 人
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">优秀率</span>
          <span className="stat-value" style={{ color: "#4ade80" }}>
            {stats ? Math.round(((stats.level_distribution["优秀(>85%)"] || 0) / stats.total_students) * 100) : 0}%
          </span>
        </div>
      </div>

      <div className="dashboard-grid" style={{ padding: 0, height: "auto", overflow: "visible" }}>
        {/* Level Distribution */}
        <div className="dashboard-card">
          <h3><BarChart3 size={16} /> 水平分布</h3>
          {stats && Object.entries(stats.level_distribution).map(([level, count]) => (
            <div key={level} className="dashboard-mastery-item" style={{ marginBottom: 8 }}>
              <span className="dashboard-mastery-name">{level}</span>
              <div className="dashboard-mastery-bar">
                <div className="dashboard-mastery-fill" style={{
                  width: `${(count / stats.total_students) * 100}%`,
                  background: levelColors[level] || "#6366f1",
                }} />
              </div>
              <span className="dashboard-mastery-pct">{count}人</span>
            </div>
          ))}
        </div>

        {/* Common Weak Points */}
        <div className="dashboard-card">
          <h3><Target size={16} /> 共性薄弱点 TOP5</h3>
          {stats?.common_weak_points.map((wp, i) => (
            <div key={wp.topic} className="dashboard-weak-item" style={{
              background: i < 3 ? "rgba(248,113,113,0.06)" : "rgba(255,255,255,0.02)"
            }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  width: 20, height: 20, borderRadius: "50%",
                  background: i < 3 ? "rgba(248,113,113,0.2)" : "rgba(255,255,255,0.06)",
                  color: i < 3 ? "#f87171" : "rgba(255,255,255,0.4)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, fontWeight: 600,
                }}>{i + 1}</span>
                {wp.topic}
              </span>
              <span>{wp.count}人薄弱</span>
            </div>
          ))}
        </div>

        {/* Student list */}
        <div className="dashboard-card dashboard-card-full">
          <h3><Users size={16} /> 学生概览</h3>
          <div className="dimension-table">
            <div className="dimension-header">
              <span>姓名</span>
              <span>水平</span>
              <span>进度</span>
              <span>平均分</span>
              <span>薄弱点</span>
            </div>
            {stats?.students.map((s) => (
              <div key={s.user_id} className="dimension-row">
                <span className="dim-topic">{s.username}</span>
                <span className="dim-cell" style={{ color: s.overall_level === "优秀" ? "#4ade80" : s.overall_level === "需努力" ? "#f87171" : "#facc15" }}>
                  {s.overall_level}
                </span>
                <span className="dim-cell">
                  <div className="dim-bar-container" style={{ width: 80 }}>
                    <div className="dim-bar" style={{ width: `${(s.completed_nodes / s.total_nodes) * 100}%` }} />
                  </div>
                  {s.completed_nodes}/{s.total_nodes}
                </span>
                <span className="dim-cell">{s.avg_score}</span>
                <span className="dim-cell" style={{ fontSize: 11 }}>{s.weak_points.join(", ")}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Push Task */}
        <div className="dashboard-card dashboard-card-full">
          <h3><Zap size={16} /> 紧急任务推送</h3>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", marginBottom: 12 }}>
            发布紧急任务或全班挑战赛，强制推送到所有学生端。
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="res-lib-search"
              placeholder="输入任务标题（如：全班递归算法强化练习）"
              value={pushTopic}
              onChange={(e) => setPushTopic(e.target.value)}
              style={{ flex: 1 }}
            />
            <button className="btn-primary" onClick={handlePushTask} disabled={pushing || !pushTopic.trim()}>
              <Send size={14} style={{ marginRight: 4 }} />
              {pushing ? "推送中..." : "推送"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default TeacherDashboardPage;
