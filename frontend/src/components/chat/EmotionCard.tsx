import { useState } from "react";
import { Heart, Zap, Coffee, HelpCircle, Trophy, Flame } from "lucide-react";

interface EmotionData {
  emotion: string;
  suggestion: string;
  intervention: {
    mode: string;
    action: string;
    message: string;
  };
}

interface Props {
  emotion: EmotionData | null;
}

const EMOTION_CONFIG: Record<string, { icon: typeof Heart; color: string; bg: string; label: string }> = {
  frustrated: { icon: Heart, color: "#fca5a5", bg: "rgba(239,68,68,0.08)", label: "感到困难" },
  anxious: { icon: Coffee, color: "#fde047", bg: "rgba(250,204,21,0.08)", label: "有些紧张" },
  bored: { icon: Zap, color: "#facc15", bg: "rgba(250,204,21,0.08)", label: "学习疲劳" },
  confused: { icon: HelpCircle, color: "#93c5fd", bg: "rgba(96,165,250,0.08)", label: "需要帮助" },
  confident: { icon: Trophy, color: "#86efac", bg: "rgba(74,222,128,0.08)", label: "信心满满" },
  motivated: { icon: Flame, color: "#fdba74", bg: "rgba(251,146,60,0.08)", label: "动力十足" },
};

export function EmotionCard({ emotion }: Props) {
  const [dismissed, setDismissed] = useState(false);

  if (!emotion || dismissed) return null;

  const cfg = EMOTION_CONFIG[emotion.emotion];
  if (!cfg) return null;

  const Icon = cfg.icon;

  return (
    <div className="emotion-card" style={{ borderColor: cfg.color, background: cfg.bg }}>
      <div className="emotion-card-header">
        <div className="emotion-card-icon" style={{ background: cfg.color }}>
          <Icon size={16} color="#000" />
        </div>
        <span className="emotion-card-label" style={{ color: cfg.color }}>
          {cfg.label}
        </span>
        <span className="emotion-card-mode">· {emotion.intervention.message}</span>
        <button
          className="emotion-card-dismiss"
          onClick={() => setDismissed(true)}
          type="button"
        >
          ✕
        </button>
      </div>
      <p className="emotion-card-suggestion">{emotion.suggestion}</p>
    </div>
  );
}
