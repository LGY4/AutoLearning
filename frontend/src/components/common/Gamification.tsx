import { useEffect, useState } from "react";
import { Flame, Zap, Award } from "lucide-react";

interface GameState {
  streak: number;
  lastActiveDate: string;
  xp: number;
  level: number;
}

function loadState(): GameState {
  try {
    const raw = localStorage.getItem("gamification");
    return raw ? JSON.parse(raw) : { streak: 0, lastActiveDate: "", xp: 0, level: 1 };
  } catch { return { streak: 0, lastActiveDate: "", xp: 0, level: 1 }; }
}

function saveState(s: GameState) { localStorage.setItem("gamification", JSON.stringify(s)); }

const XP_PER_LEVEL = 100;

export function useGamification() {
  const [game, setGame] = useState<GameState>(loadState);

  const recordActivity = (xpGain: number = 10) => {
    setGame((prev) => {
      const today = new Date().toDateString();
      const yesterday = new Date(Date.now() - 86400000).toDateString();

      let streak = prev.streak;
      if (prev.lastActiveDate === today) {
        // already active today, just add XP
      } else if (prev.lastActiveDate === yesterday) {
        streak += 1; // consecutive
      } else {
        streak = 1; // reset
      }

      let xp = prev.xp + xpGain;
      let level = prev.level;
      while (xp >= level * XP_PER_LEVEL) {
        xp -= level * XP_PER_LEVEL;
        level += 1;
      }

      const next: GameState = { streak, lastActiveDate: today, xp, level };
      saveState(next);
      return next;
    });
  };

  return { game, recordActivity };
}

export function GamificationBar() {
  const [game, setGame] = useState<GameState>(loadState);

  useEffect(() => {
    const timer = setInterval(() => setGame(loadState()), 5000);
    return () => clearInterval(timer);
  }, []);

  const xpPct = Math.round((game.xp / (game.level * XP_PER_LEVEL)) * 100);

  return (
    <div className="gamification-bar">
      <div className="game-stat" title="连续学习天数">
        <Flame size={14} color={game.streak >= 7 ? "#f97316" : game.streak >= 3 ? "#facc15" : "rgba(255,255,255,0.4)"} />
        <span>{game.streak}天</span>
      </div>
      <div className="game-stat" title={`等级 ${game.level}`}>
        <Award size={14} color="#a78bfa" />
        <span>Lv.{game.level}</span>
      </div>
      <div className="game-xp-bar" title={`${game.xp}/${game.level * XP_PER_LEVEL} XP`}>
        <div className="game-xp-fill" style={{ width: `${xpPct}%` }} />
      </div>
    </div>
  );
}
