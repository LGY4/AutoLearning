import { useCallback, useEffect, useState } from "react";
import { User, Save, RefreshCw } from "lucide-react";
import { apiGet, apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";
import type { StudentProfile } from "../types/baseline";

interface DimensionInfo {
  mastery: string;
  application: string;
  memory: string;
  understanding: string;
}

const DIM_LABELS: Record<string, string> = {
  mastery: "掌握度",
  application: "应用力",
  memory: "记忆力",
  understanding: "理解力",
  high: "高",
  mid: "中",
  low: "低",
};

export function ProfileEditPage() {
  const { state, dispatch } = useAppContext();
  const [profile, setProfile] = useState<StudentProfile | null>(state.profile);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<StudentProfile[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [extracting, setExtracting] = useState(false);

  const handleReExtract = useCallback(async () => {
    if (!state.user) return;
    setExtracting(true);
    setError(null);
    try {
      const p = await apiPost<StudentProfile>("/profiles/extract", { user_id: state.user.id });
      setProfile(p);
      dispatch({ type: "SET_PROFILE", payload: p });
    } catch (e) {
      setError(e instanceof Error ? e.message : "重新提取失败");
    } finally {
      setExtracting(false);
    }
  }, [state.user, dispatch]);

  useEffect(() => {
    if (!state.profile) {
      setLoading(true);
      apiGet<StudentProfile>("/profiles/me")
        .then((p) => { setProfile(p); dispatch({ type: "SET_PROFILE", payload: p }); })
        .catch(() => setError("暂无画像数据，请先完成入学诊断"))
        .finally(() => setLoading(false));
    }
  }, []);

  async function loadVersions() {
    try {
      const v = await apiGet<StudentProfile[]>("/profiles/me/versions");
      setVersions(v);
      setShowVersions(true);
    } catch {
      setError("加载版本历史失败");
    }
  }

  if (loading) return <div className="page-loading">加载中...</div>;
  if (!profile) return <div className="page-container"><div className="empty-state">暂无画像数据，请先完成入学诊断或开始学习</div></div>;

  const kp = profile.knowledge_profile;
  const pref = profile.learning_preference;

  const topicEntries = Object.entries(kp.topic_dimensions ?? {}) as [string, DimensionInfo][];

  function renderDimensionBar(dim: DimensionInfo) {
    const scores = [dim.mastery, dim.application, dim.memory, dim.understanding];
    const avg = scores.filter((s) => s === "high").length * 3 + scores.filter((s) => s === "mid").length * 2 + scores.filter((s) => s === "low").length;
    const pct = (avg / 12) * 100;
    return (
      <div className="dim-bar-container">
        <div className="dim-bar" style={{ width: `${pct}%` }} />
        <span className="dim-bar-label">{Math.round(pct)}%</span>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1><User size={24} /> 学习画像</h1>
        <div className="page-header-actions">
          <button className="btn-secondary" onClick={loadVersions}>
            版本历史
          </button>
          <button className="btn-primary" onClick={handleReExtract} disabled={extracting}>
            <RefreshCw size={16} />
            {extracting ? "提取中..." : "重新提取画像"}
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}

      {/* Overview */}
      <div className="info-card" style={{ marginBottom: 24 }}>
        <h3>画像概览</h3>
        <div className="profile-stats">
          <div className="stat-item">
            <span className="stat-label">整体水平</span>
            <span className="stat-value">{kp.overall_level ?? "未评估"}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">掌握程度</span>
            <span className="stat-value">{kp.mastery_level ? Object.entries(kp.mastery_level).map(([k, v]) => `${k}:${Math.round(v * 100)}%`).join(", ") : "未评估"}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">画像版本</span>
            <span className="stat-value">v{profile.version}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">完整度</span>
            <span className="stat-value">{profile.completeness_score ? `${Math.round(profile.completeness_score)}%` : "—"}</span>
          </div>
        </div>
      </div>

      {/* Learning preferences */}
      <div className="info-card" style={{ marginBottom: 24 }}>
        <h3>学习偏好</h3>
        <div className="profile-stats">
          <div className="stat-item">
            <span className="stat-label">学习风格</span>
            <span className="stat-value">{pref.learning_style}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">难度偏好</span>
            <span className="stat-value">{pref.difficulty_preference}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">资源偏好</span>
            <span className="stat-value">{Object.keys(pref.resource_preference ?? {}).join(", ") || "—"}</span>
          </div>
        </div>
      </div>

      {/* Weak topics */}
      {kp.weak_topics && kp.weak_topics.length > 0 && (
        <div className="info-card" style={{ marginBottom: 24 }}>
          <h3>薄弱知识点</h3>
          <div className="tag-list">
            {kp.weak_topics.map((t: string) => (
              <span className="tag warning" key={t}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* Known topics */}
      {kp.known_topics && kp.known_topics.length > 0 && (
        <div className="info-card" style={{ marginBottom: 24 }}>
          <h3>已掌握知识点</h3>
          <div className="tag-list">
            {kp.known_topics.map((t: string) => (
              <span className="tag success" key={t}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* Topic dimensions */}
      <div className="info-card">
        <h3>知识点四维度 ({topicEntries.length})</h3>
        {topicEntries.length === 0 ? (
          <div className="empty-state">暂无知识点评估数据</div>
        ) : (
          <div className="dimension-table">
            <div className="dimension-header">
              <span>知识点</span>
              <span>掌握</span>
              <span>应用</span>
              <span>记忆</span>
              <span>理解</span>
              <span>综合</span>
            </div>
            {topicEntries.map(([topic, dim]) => (
              <div className="dimension-row" key={topic}>
                <span className="dim-topic">{topic}</span>
                <span className={`dim-cell ${dim.mastery}`}>{DIM_LABELS[dim.mastery] ?? dim.mastery}</span>
                <span className={`dim-cell ${dim.application}`}>{DIM_LABELS[dim.application] ?? dim.application}</span>
                <span className={`dim-cell ${dim.memory}`}>{DIM_LABELS[dim.memory] ?? dim.memory}</span>
                <span className={`dim-cell ${dim.understanding}`}>{DIM_LABELS[dim.understanding] ?? dim.understanding}</span>
                <span className="dim-cell">{renderDimensionBar(dim)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Version history */}
      {showVersions && (
        <div className="info-card" style={{ marginTop: 24 }}>
          <h3>画像版本历史</h3>
          {versions.length === 0 ? (
            <div className="empty-state">暂无历史版本</div>
          ) : (
            <div className="version-list">
              {versions.map((v) => (
                <div className="version-item" key={v.profile_id}>
                  <span className="version-tag">v{v.version}</span>
                  <span className="version-info">
                    完整度 {v.completeness_score ? `${Math.round(v.completeness_score)}%` : "—"}
                    {" · "}
                    置信度 {v.confidence_score ? `${Math.round(v.confidence_score)}%` : "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
