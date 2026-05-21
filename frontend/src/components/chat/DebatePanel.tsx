import { useEffect, useState } from "react";
import { MessageCircle, Sparkles, Zap, Send } from "lucide-react";
import { apiPost } from "../../api/client";
import { useAppContext } from "../../context/AppContext";

interface DebateMessage {
  speaker: string;
  role: string;
  content: string;
}

interface DebateResult {
  topic: string;
  characters: Array<{ name: string; role: string; style: string }>;
  messages: DebateMessage[];
  reflection_question: string;
  rounds: number;
}

interface Props {
  topic: string;
  onClose: () => void;
  onSendToChat?: (text: string) => void;
}

const SPEAKER_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  "学霸": { bg: "rgba(99,102,241,0.08)", border: "rgba(99,102,241,0.25)", icon: "🎓" },
  "杠精": { bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.25)", icon: "⚡" },
};

export function DebatePanel({ topic, onClose, onSendToChat }: Props) {
  const { state } = useAppContext();
  const [debate, setDebate] = useState<DebateResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [visibleMsgs, setVisibleMsgs] = useState(0);
  const [answer, setAnswer] = useState("");

  useEffect(() => {
    loadDebate();
  }, [topic]);

  async function loadDebate() {
    setLoading(true);
    try {
      const result = await apiPost<DebateResult>("/learning/debate", {
        topic,
        rounds: 5,
      });
      setDebate(result);
      // Animate messages appearing one by one
      result.messages.forEach((_, i) => {
        setTimeout(() => setVisibleMsgs(i + 1), (i + 1) * 800);
      });
    } catch {
      setDebate(null);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="debate-panel">
        <div className="debate-loading">
          <Sparkles size={20} className="pipeline-spin" />
          <span>正在组建辩论小组...</span>
        </div>
      </div>
    );
  }

  if (!debate) {
    return (
      <div className="debate-panel">
        <div className="debate-error">辩论生成失败，请重试</div>
      </div>
    );
  }

  return (
    <div className="debate-panel">
      <div className="debate-header">
        <div>
          <span className="debate-badge">苏格拉底辩论</span>
          <span className="debate-topic">主题：{debate.topic}</span>
        </div>
        <button className="debate-close" onClick={onClose} type="button">✕</button>
      </div>

      <div className="debate-characters">
        {debate.characters.map((c) => (
          <span key={c.name} className="debate-char-tag" title={c.style}>
            {SPEAKER_COLORS[c.name]?.icon || "💬"} {c.name}: {c.role}
          </span>
        ))}
      </div>

      <div className="debate-messages">
        {debate.messages.slice(0, visibleMsgs).map((msg, i) => {
          const colors = SPEAKER_COLORS[msg.speaker] || { bg: "rgba(255,255,255,0.04)", border: "rgba(255,255,255,0.1)", icon: "💬" };
          return (
            <div
              key={i}
              className="debate-msg"
              style={{ background: colors.bg, borderColor: colors.border, animationDelay: `${i * 0.1}s` }}
            >
              <div className="debate-msg-speaker">
                <span>{colors.icon}</span>
                <strong style={{ color: colors.border }}>{msg.speaker}</strong>
                <span className="debate-msg-role">{msg.role === "challenger" ? "追问" : "质疑"}</span>
              </div>
              <p className="debate-msg-content">{msg.content}</p>
            </div>
          );
        })}
      </div>

      {visibleMsgs >= debate.messages.length && (
        <div className="debate-reflection">
          <div className="debate-reflection-header">
            <MessageCircle size={16} />
            <span>请发表你的看法</span>
          </div>
          <p>{debate.reflection_question}</p>
          <textarea
            className="debate-input"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="输入你的观点..."
            rows={3}
          />
          {answer.trim() && (
            <button
              className="btn-primary btn-sm"
              onClick={() => onSendToChat?.(`关于「${topic}」的辩论中，我的看法是：${answer}`)}
              type="button"
              style={{ marginTop: 8 }}
            >
              <Send size={14} /> 发送并继续学习
            </button>
          )}
        </div>
      )}
    </div>
  );
}
