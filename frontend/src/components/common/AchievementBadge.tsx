import { useEffect, useState } from "react";
import { Trophy, Star, Zap, Target, Award } from "lucide-react";

interface Badge {
  id: string;
  title: string;
  subtitle: string;
  icon: typeof Trophy;
  color: string;
}

const BADGES: Badge[] = [
  { id: "first_blood", title: "首次学习", subtitle: "完成第一次对话学习", icon: Star, color: "#facc15" },
  { id: "perfect_score", title: "满分达人", subtitle: "练习获得满分", icon: Trophy, color: "#facc15" },
  { id: "node_master", title: "节点攻克", subtitle: "完成一个学习路径节点", icon: Target, color: "#4ade80" },
  { id: "three_in_row", title: "三连正确", subtitle: "连续答对 3 道题", icon: Zap, color: "#60a5fa" },
  { id: "resource_collector", title: "资源收集者", subtitle: "生成超过 5 个学习资源", icon: Award, color: "#a78bfa" },
];

export function AchievementBadge({ badgeId, onClose }: { badgeId: string; onClose: () => void }) {
  const [visible, setVisible] = useState(true);
  const badge = BADGES.find((b) => b.id === badgeId);

  useEffect(() => {
    const timer = setTimeout(() => { setVisible(false); onClose(); }, 3000);
    return () => clearTimeout(timer);
  }, []);

  if (!visible || !badge) return null;

  const Icon = badge.icon;

  return (
    <div className="achievement-overlay">
      <div className="achievement-card" style={{ borderColor: badge.color }}>
        <div className="achievement-glow" style={{ background: badge.color }} />
        <div className="achievement-icon" style={{ background: badge.color }}>
          <Icon size={32} color="#000" />
        </div>
        <h3 className="achievement-title">成就解锁！</h3>
        <p className="achievement-name" style={{ color: badge.color }}>{badge.title}</p>
        <p className="achievement-subtitle">{badge.subtitle}</p>
      </div>
    </div>
  );
}

export function useAchievement() {
  const [currentBadge, setCurrentBadge] = useState<string | null>(null);

  const trigger = (badgeId: string) => {
    // Only trigger if not already seen
    const key = `achievement_${badgeId}`;
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, "true");
    setCurrentBadge(badgeId);
  };

  return { currentBadge, trigger, close: () => setCurrentBadge(null) };
}
