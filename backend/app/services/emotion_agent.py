"""Emotion detection agent — lightweight keyword-based analysis for demo mode.

Detects: frustration (太难了/不会/不懂), anxiety (紧张/担心/焦虑),
boredom (无聊/没意思/枯燥), confusion (不明白/搞不懂/晕),
confidence (简单/明白了/懂了/会了), motivation (加油/努力/坚持).

Returns emotion labels with intervention suggestions as per requirements:
- "太难了" → 降级模式（简化内容）+ 鼓励模式
- "厌倦" → 挑战模式（趣味案例）
"""

from __future__ import annotations

from typing import Optional
import re

EMOTION_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, emotion_label, suggestion)
    (r"太难|好难|这么难|很难|不懂|不会|不理解|搞不懂|看不懂|学不会",
     "frustrated",
     "💪 别灰心！学习新知识需要时间。我已经为你切换到**降级模式**，用更简单的方式讲解。\n\n记住：每个高手都曾是新手。Rome wasn't built in a day!"),
    (r"紧张|焦虑|担心|害怕|压力|考试.*怕|面试.*怕",
     "anxious",
     "😌 深呼吸！适度的紧张是正常的。放轻松，我们一步步来。\n\n学习本身就是一种进步，不必给自己太大压力。"),
    (r"无聊|没意思|枯燥|乏味|没劲|不想学|想放弃",
     "bored",
     "🎮 检测到学习疲劳！让我们换个方式——我为你准备了一个**趣味挑战**，用游戏化的方式学习！\n\n试试看你能不能通关？"),
    (r"不明白|不清楚|搞不懂|晕|混乱|复杂|不知道怎么",
     "confused",
     "🤔 我理解你的困惑。让我换个角度重新解释一下这个知识点。\n\n有时候，换一种表达方式就能豁然开朗。"),
    (r"简单|容易|明白了|懂了|会了|掌握了|so easy|easy",
     "confident",
     "🎉 太棒了！看来你已经掌握了这个知识点。要不要挑战一下更高难度？\n\n学习就像升级打怪，你已经准备好进入下一关了！"),
    (r"加油|努力|坚持|继续|冲|come on|fighting",
     "motivated",
     "🔥 这份热情太感染人了！保持这个状态，没有什么能阻挡你。\n\n全力以赴，你可以的！"),
]


def detect_emotion(text: str) -> Optional[dict]:
    """Detect emotion from user text. Returns None if no emotion detected."""
    for pattern, label, suggestion in EMOTION_PATTERNS:
        if re.search(pattern, text):
            return {
                "emotion": label,
                "suggestion": suggestion,
                "intervention": _get_intervention(label),
            }
    return None


def _get_intervention(emotion: str) -> dict:
    """Get intervention strategy based on emotion."""
    strategies = {
        "frustrated": {
            "mode": "simplified",
            "action": "downgrade_difficulty",
            "message": "已切换到简化模式",
        },
        "anxious": {
            "mode": "comforting",
            "action": "reduce_pressure",
            "message": "放松学习模式",
        },
        "bored": {
            "mode": "challenge",
            "action": "gamify_content",
            "message": "已切换到挑战模式",
        },
        "confused": {
            "mode": "re_explain",
            "action": "alternative_perspective",
            "message": "换个角度重新讲解",
        },
        "confident": {
            "mode": "advance",
            "action": "increase_difficulty",
            "message": "推荐进阶内容",
        },
        "motivated": {
            "mode": "accelerate",
            "action": "suggest_next",
            "message": "全力加速学习",
        },
    }
    return strategies.get(emotion, {"mode": "neutral", "action": "none", "message": ""})
