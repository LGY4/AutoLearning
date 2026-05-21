"""Debate Agent — Socratic dialog simulation for critical thinking.

Generates multi-turn debates between virtual characters (学霸/杠精)
to guide the user's understanding through questioning.
"""

from __future__ import annotations

import random
from typing import Optional

DEBATE_SCRIPTS: dict[str, list[dict]] = {
    "default": [
        {"speaker": "学霸", "role": "challenger", "content": "你有没有想过，为什么这个问题被广泛讨论？它的核心矛盾在哪里？"},
        {"speaker": "杠精", "role": "skeptic", "content": "等等，你说的这个前提假设本身就有问题。我们怎么确定这个假设是成立的？"},
        {"speaker": "学霸", "role": "challenger", "content": "好问题！让我们从最基础的层面重新审视——我们首先需要明确什么是'正确'的定义。"},
        {"speaker": "杠精", "role": "skeptic", "content": "即使定义清楚了，在实际应用中，情况往往比理论复杂得多。你能给出一个反例吗？"},
        {"speaker": "学霸", "role": "challenger", "content": "确实，理论到实践有差距。但正是通过不断质疑和修正，我们才能逼近真相。你觉得呢？"},
    ],
    "数据结构": [
        {"speaker": "学霸", "role": "challenger", "content": "数据结构的选择真的有那么重要吗？大多数时候用list不就行了？"},
        {"speaker": "杠精", "role": "skeptic", "content": "当然重要！如果你需要频繁在中间插入删除，用数组时间复杂度是O(n)，但用链表就是O(1)。这是本质区别。"},
        {"speaker": "学霸", "role": "challenger", "content": "但实际开发中，数据量不大的情况下，list的cache locality优势可能反而更快。你怎么看？"},
        {"speaker": "杠精", "role": "skeptic", "content": "你这叫premature optimization！我们讨论的是算法层面的正确性。先保证算法正确，再谈性能优化。"},
        {"speaker": "学霸", "role": "challenger", "content": "说得好。所以核心结论是：选择数据结构要从操作特征和时间复杂度出发，而不是凭感觉。你同意吗？"},
    ],
    "算法": [
        {"speaker": "学霸", "role": "challenger", "content": "冒泡排序和快排，后者一定更快吗？有没有冒泡反而更好的场景？"},
        {"speaker": "杠精", "role": "skeptic", "content": "如果数据基本有序，冒泡排序的best case是O(n)，而快排如果不优化pivot，可能退化到O(n²)。"},
        {"speaker": "学霸", "role": "challenger", "content": "所以'最优算法'不是一个绝对概念？它依赖于具体的输入特征？"},
        {"speaker": "杠精", "role": "skeptic", "content": "没错。这就是为什么实际工程中TimSort（混合排序）更实用——它根据数据特征自动切换策略。"},
        {"speaker": "学霸", "role": "challenger", "content": "这个讨论让我意识到：算法没有银弹，理解trade-off才是核心能力。"},
    ],
}


def generate_debate(topic: str, rounds: int = 5) -> dict:
    """Generate a Socratic debate on the given topic.

    Returns dict with 'topic', 'messages' (list of speaker/content pairs),
    and 'reflection_question' for the user.
    """
    # Find best matching script
    script = DEBATE_SCRIPTS.get("default")
    for key in DEBATE_SCRIPTS:
        if key != "default" and key in topic:
            script = DEBATE_SCRIPTS[key]
            break

    messages = script[:rounds]

    reflection_questions = [
        f"听完这场辩论，你对「{topic}」的理解有什么变化？你更认同哪一方的观点？",
        f"辩论中提到的trade-off，你在实际学习中有体会到吗？请举例说明。",
        f"如果让你加入这场辩论，你会站在哪一边？你会提出什么新观点？",
    ]

    return {
        "topic": topic,
        "characters": [
            {"name": "学霸", "role": "深度思考者，喜欢挑战假设", "style": "理性、善于引用理论"},
            {"name": "杠精", "role": "怀疑论者，喜欢找反例", "style": "犀利、注重实践反例"},
        ],
        "messages": messages,
        "reflection_question": random.choice(reflection_questions),
        "rounds": len(messages),
    }
