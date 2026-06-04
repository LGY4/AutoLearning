import { useState } from "react";
import { apiGet } from "../../../api/client";
import type { StudentProfile } from "../../../types/baseline";

interface WelcomeData {
  greeting: string;
  streak_days: number;
  today_goal: { target_minutes: number; completed_minutes: number; progress: number };
  weak_topics: Array<{ topic: string; score: number; suggestion: string }>;
  path_progress: { title: string; completed: number; total: number; next_node: string } | null;
  review_due: Array<{ topic: string; days_since: number }>;
  daily_tip: string;
  stats_yesterday: { questions: number; accuracy: number; minutes: number } | null;
}

export function WelcomePanel({ result }: { result: Record<string, unknown> }) {
  const data = result as unknown as WelcomeData;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Greeting + Streak */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{data.greeting}</div>
        {data.streak_days > 0 && (
          <div style={{
            padding: "4px 12px", borderRadius: 16,
            background: data.streak_days >= 7 ? "#fef3c7" : "#dbeafe",
            border: `1px solid ${data.streak_days >= 7 ? "#f59e0b" : "#3b82f6"}`,
            fontSize: 13, fontWeight: 600,
          }}>
            🔥 连续 {data.streak_days} 天
          </div>
        )}
      </div>

      {/* Daily Tip */}
      <div style={{ padding: 10, background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac", fontSize: 13 }}>
        💡 {data.daily_tip}
      </div>

      {/* Today's Goal */}
      <div style={{ padding: 12, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>今日目标</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ flex: 1, height: 8, background: "#e5e7eb", borderRadius: 4, overflow: "hidden" }}>
            <div style={{
              width: `${Math.min(100, data.today_goal.progress * 100)}%`,
              height: "100%",
              background: data.today_goal.progress >= 1 ? "#22c55e" : "#3b82f6",
              borderRadius: 4,
              transition: "width 0.3s",
            }} />
          </div>
          <span style={{ fontSize: 12, color: "#6b7280", minWidth: 80, textAlign: "right" }}>
            {data.today_goal.completed_minutes}/{data.today_goal.target_minutes} 分钟
          </span>
        </div>
        {data.today_goal.progress >= 1 && (
          <div style={{ fontSize: 12, color: "#16a34a", marginTop: 4 }}>✓ 今日目标已完成！</div>
        )}
      </div>

      {/* Yesterday Stats */}
      {data.stats_yesterday && (
        <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
          <div style={{ flex: 1, padding: 8, background: "#eff6ff", borderRadius: 8, textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 700 }}>{data.stats_yesterday.questions}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>昨日答题</div>
          </div>
          <div style={{ flex: 1, padding: 8, background: "#f0fdf4", borderRadius: 8, textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: data.stats_yesterday.accuracy >= 0.7 ? "#16a34a" : "#dc2626" }}>
              {Math.round(data.stats_yesterday.accuracy * 100)}%
            </div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>昨日正确率</div>
          </div>
          <div style={{ flex: 1, padding: 8, background: "#fef9c3", borderRadius: 8, textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 700 }}>{data.stats_yesterday.minutes.toFixed(0)}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>昨日分钟</div>
          </div>
        </div>
      )}

      {/* Path Progress */}
      {data.path_progress && (
        <div style={{ padding: 12, background: "#eff6ff", borderRadius: 8, border: "1px solid #bfdbfe" }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>📚 {data.path_progress.title}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <div style={{ flex: 1, height: 6, background: "#dbeafe", borderRadius: 3 }}>
              <div style={{
                width: `${(data.path_progress.completed / Math.max(data.path_progress.total, 1)) * 100}%`,
                height: "100%", background: "#3b82f6", borderRadius: 3,
              }} />
            </div>
            <span style={{ fontSize: 12 }}>{data.path_progress.completed}/{data.path_progress.total}</span>
          </div>
          {data.path_progress.next_node && (
            <div style={{ fontSize: 12, color: "#1e40af" }}>
              下一步: <strong>{data.path_progress.next_node}</strong>
            </div>
          )}
        </div>
      )}

      {/* Weak Topics */}
      {data.weak_topics.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>🎯 建议攻克</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {data.weak_topics.map((wt, i) => (
              <div key={i} style={{ padding: "8px 12px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 13 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <strong>{wt.topic}</strong>
                  <span style={{ color: wt.score < 0.3 ? "#dc2626" : wt.score < 0.5 ? "#ca8a04" : "#16a34a" }}>
                    {Math.round(wt.score * 100)}%
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>{wt.suggestion}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Review Due */}
      {data.review_due.length > 0 && (
        <div style={{ padding: 10, background: "#fef2f2", borderRadius: 8, border: "1px solid #fecaca" }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>⏰ 待复习</div>
          <div style={{ fontSize: 13 }}>
            {data.review_due.map((r, i) => (
              <span key={i} style={{ marginRight: 12 }}>
                {r.topic} <span style={{ fontSize: 11, color: "#6b7280" }}>({r.days_since}天前)</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {data.weak_topics.length > 0 && (
          <QuickAction label={`练习「${data.weak_topics[0].topic}」`} message={`帮我出几道${data.weak_topics[0].topic}的练习题`} />
        )}
        {data.path_progress?.next_node && (
          <QuickAction label={`学习「${data.path_progress.next_node}」`} message={`帮我讲解${data.path_progress.next_node}`} />
        )}
        {data.review_due.length > 0 && (
          <QuickAction label={`复习「${data.review_due[0].topic}」`} message={`帮我复习${data.review_due[0].topic}`} />
        )}
        <QuickAction label="学习分析" message="看看我的学习分析" />
      </div>
    </div>
  );
}

function QuickAction({ label, message }: { label: string; message: string }) {
  const [sent, setSent] = useState(false);

  const handleClick = async () => {
    // Set pending message via global state
    try {
      const { useAppContext } = await import("../../../context/AppContext");
      // Can't use hook in callback, use window event instead
      window.dispatchEvent(new CustomEvent("chat-send-message", { detail: message }));
      setSent(true);
    } catch {
      // Fallback: copy to clipboard
      navigator.clipboard?.writeText(message);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={sent}
      style={{
        padding: "6px 14px", borderRadius: 16, fontSize: 12,
        border: "1px solid #3b82f6", background: sent ? "#dbeafe" : "white",
        color: "#3b82f6", cursor: sent ? "default" : "pointer",
      }}
    >
      {sent ? "已发送" : label}
    </button>
  );
}
