from __future__ import annotations
from typing import List, Dict

"""Learner Archetype Registry — 预定义学习者原型。

原型是自适应管线的真实功能组件，用途：
1. 诊断加速：新用户匹配到最近原型，LLM 从原型基础上精炼
2. 策略校准：确保 strategy_engine 的不同分支被真实触发
3. Mock Store 种子：内存模式下用不同原型初始化多个用户
"""

from datetime import datetime, timezone

from app.schemas.profile import KnowledgeDimension


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _dim(mastery: str, application: str, memory: str, understanding: str) -> dict:
    """Shorthand to build a KnowledgeDimension dict."""
    return {"mastery": mastery, "application": application, "memory": memory, "understanding": understanding}


# ── 8 个原型定义 ─────────────────────────────────────────────────────────
# 每个原型覆盖 strategy_engine.py 中的特定分支

ARCHETYPES: Dict[str, dict] = {
    # ── 初学者组 ──────────────────────────────────────────────────────
    "beginner_visual": {
        "completeness_score": 0.72,
        "confidence_score": 0.68,
        "basic_info": {"major": "计算机科学与技术", "grade": "大一", "school": None},
        "knowledge_profile": {
            "overall_level": "beginner",
            "known_topics": [],
            "weak_topics": ["栈", "队列", "链表", "复杂度分析", "递归"],
            "mastery_level": {"栈": 0.15, "队列": 0.10, "链表": 0.12, "复杂度分析": 0.08},
            "topic_dimensions": {
                "栈": _dim("low", "low", "low", "low"),
                "队列": _dim("low", "low", "low", "low"),
                "链表": _dim("low", "low", "low", "low"),
                "复杂度分析": _dim("low", "low", "low", "low"),
            },
        },
        "learning_goal": {
            "current_goal": "掌握数据结构基础知识，为期末考试做准备",
            "target_course": "数据结构",
            "target_level": "exam_prep",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "visual",
            "resource_preference": {
                "document": 0.6, "mindmap": 0.9, "quiz": 0.5, "reading": 0.4,
                "video": 0.8, "animation": 0.9, "code_case": 0.3, "flowchart": 0.8,
            },
            "difficulty_preference": "step_by_step",
        },
        "learning_behavior": {
            "average_study_minutes": 30,
            "active_period": "evening",
            "completion_rate": 0.45,
            "recent_scores": [35, 42, 38],
            "last_knowledge_point": None,
        },
        "cognitive_profile": {
            "cognitive_style": "visual",
            "abstract_understanding": "low",
            "hands_on_ability": "low",
            "reading_patience": "low",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到视觉型初学者原型",
        },
    },

    "beginner_hands_on": {
        "completeness_score": 0.75,
        "confidence_score": 0.70,
        "basic_info": {"major": "软件工程", "grade": "大一", "school": None},
        "knowledge_profile": {
            "overall_level": "beginner",
            "known_topics": ["Python基础"],
            "weak_topics": ["栈", "队列", "链表", "哈希表"],
            "mastery_level": {"Python基础": 0.55, "栈": 0.18, "队列": 0.12, "链表": 0.15},
            "topic_dimensions": {
                "Python基础": _dim("mid", "low", "mid", "low"),
                "栈": _dim("low", "low", "low", "low"),
                "队列": _dim("low", "low", "low", "low"),
                "链表": _dim("low", "low", "low", "low"),
            },
        },
        "learning_goal": {
            "current_goal": "通过动手编程掌握数据结构，完成课程项目",
            "target_course": "数据结构",
            "target_level": "project_practice",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "hands-on",
            "resource_preference": {
                "document": 0.4, "mindmap": 0.3, "quiz": 0.7, "reading": 0.2,
                "video": 0.5, "animation": 0.4, "code_case": 0.95, "flowchart": 0.5,
            },
            "difficulty_preference": "step_by_step",
        },
        "learning_behavior": {
            "average_study_minutes": 60,
            "active_period": "afternoon",
            "completion_rate": 0.58,
            "recent_scores": [45, 50, 48],
            "last_knowledge_point": "Python基础",
        },
        "cognitive_profile": {
            "cognitive_style": "hands-on",
            "abstract_understanding": "low",
            "hands_on_ability": "medium",
            "reading_patience": "low",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到动手型初学者原型",
        },
    },

    # ── 中级组 ──────────────────────────────────────────────────────
    "intermediate_theory_strong": {
        # strategy_engine 分支: mastery=high, application=low → code_case + quiz
        "completeness_score": 0.82,
        "confidence_score": 0.78,
        "basic_info": {"major": "计算机科学与技术", "grade": "大二", "school": None},
        "knowledge_profile": {
            "overall_level": "intermediate",
            "known_topics": ["栈", "队列", "链表", "数组", "复杂度分析"],
            "weak_topics": ["二叉树", "图", "动态规划"],
            "mastery_level": {
                "栈": 0.80, "队列": 0.75, "链表": 0.78, "数组": 0.82, "复杂度分析": 0.70,
                "二叉树": 0.35, "图": 0.25, "动态规划": 0.20,
            },
            "topic_dimensions": {
                "栈": _dim("high", "low", "high", "high"),
                "队列": _dim("high", "low", "high", "mid"),
                "链表": _dim("high", "mid", "high", "mid"),
                "数组": _dim("high", "mid", "high", "high"),
                "复杂度分析": _dim("high", "low", "mid", "mid"),
                "二叉树": _dim("mid", "low", "low", "low"),
                "图": _dim("low", "low", "low", "low"),
            },
        },
        "learning_goal": {
            "current_goal": "深入理解算法原理，为考研机试做准备",
            "target_course": "数据结构",
            "target_level": "exam_prep",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "reading",
            "resource_preference": {
                "document": 0.9, "mindmap": 0.6, "quiz": 0.7, "reading": 0.95,
                "video": 0.3, "animation": 0.3, "code_case": 0.5, "flowchart": 0.4,
            },
            "difficulty_preference": "step_by_step",
        },
        "learning_behavior": {
            "average_study_minutes": 90,
            "active_period": "evening",
            "completion_rate": 0.75,
            "recent_scores": [72, 68, 75, 70],
            "last_knowledge_point": "复杂度分析",
        },
        "cognitive_profile": {
            "cognitive_style": "verbal",
            "abstract_understanding": "high",
            "hands_on_ability": "low",
            "reading_patience": "high",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到理论强实践弱原型",
        },
    },

    "intermediate_practice_strong": {
        # strategy_engine 分支: mastery=low, understanding=high → 提升难度
        "completeness_score": 0.80,
        "confidence_score": 0.76,
        "basic_info": {"major": "软件工程", "grade": "大二", "school": None},
        "knowledge_profile": {
            "overall_level": "intermediate",
            "known_topics": ["Python基础", "数组", "排序算法"],
            "weak_topics": ["二叉树", "动态规划", "回溯算法"],
            "mastery_level": {
                "Python基础": 0.85, "数组": 0.60, "排序算法": 0.55,
                "二叉树": 0.30, "动态规划": 0.20, "回溯算法": 0.15,
            },
            "topic_dimensions": {
                "Python基础": _dim("high", "high", "mid", "mid"),
                "数组": _dim("low", "mid", "mid", "high"),
                "排序算法": _dim("low", "mid", "mid", "high"),
                "二叉树": _dim("low", "low", "low", "mid"),
                "动态规划": _dim("low", "low", "low", "low"),
            },
        },
        "learning_goal": {
            "current_goal": "提升编程能力，完成课设和参加编程竞赛",
            "target_course": "数据结构",
            "target_level": "project_practice",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "hands-on",
            "resource_preference": {
                "document": 0.4, "mindmap": 0.3, "quiz": 0.8, "reading": 0.2,
                "video": 0.4, "animation": 0.3, "code_case": 0.95, "flowchart": 0.5,
            },
            "difficulty_preference": "challenge",
        },
        "learning_behavior": {
            "average_study_minutes": 75,
            "active_period": "afternoon",
            "completion_rate": 0.68,
            "recent_scores": [62, 58, 65, 70],
            "last_knowledge_point": "排序算法",
        },
        "cognitive_profile": {
            "cognitive_style": "hands-on",
            "abstract_understanding": "medium",
            "hands_on_ability": "high",
            "reading_patience": "low",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到实践强理论弱原型",
        },
    },

    "intermediate_forgetful": {
        # strategy_engine 分支: understanding=high, memory=low → mindmap + 间隔复习
        "completeness_score": 0.78,
        "confidence_score": 0.74,
        "basic_info": {"major": "信息与计算科学", "grade": "大三", "school": None},
        "knowledge_profile": {
            "overall_level": "intermediate",
            "known_topics": ["栈", "队列", "链表", "二叉树", "排序算法"],
            "weak_topics": ["哈希表", "图", "动态规划"],
            "mastery_level": {
                "栈": 0.65, "队列": 0.60, "链表": 0.62, "二叉树": 0.58, "排序算法": 0.55,
                "哈希表": 0.30, "图": 0.25, "动态规划": 0.22,
            },
            "topic_dimensions": {
                "栈": _dim("mid", "mid", "low", "high"),
                "队列": _dim("mid", "mid", "low", "high"),
                "链表": _dim("mid", "mid", "low", "mid"),
                "二叉树": _dim("mid", "low", "low", "high"),
                "排序算法": _dim("mid", "mid", "low", "mid"),
                "哈希表": _dim("low", "low", "low", "mid"),
                "图": _dim("low", "low", "low", "low"),
            },
        },
        "learning_goal": {
            "current_goal": "复习巩固数据结构知识，准备技术面试",
            "target_course": "数据结构",
            "target_level": "interview_prep",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "visual",
            "resource_preference": {
                "document": 0.5, "mindmap": 0.9, "quiz": 0.8, "reading": 0.4,
                "video": 0.7, "animation": 0.8, "code_case": 0.6, "flowchart": 0.9,
            },
            "difficulty_preference": "step_by_step",
        },
        "learning_behavior": {
            "average_study_minutes": 40,
            "active_period": "evening",
            "completion_rate": 0.55,
            "recent_scores": [55, 60, 52, 58],
            "last_knowledge_point": "二叉树",
        },
        "cognitive_profile": {
            "cognitive_style": "visual",
            "abstract_understanding": "high",
            "hands_on_ability": "medium",
            "reading_patience": "medium",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到理解好易遗忘原型",
        },
    },

    # ── 高级组 ──────────────────────────────────────────────────────
    "advanced_interview": {
        # strategy_engine 分支: score >= 0.75 → quiz + code_case，跳过基础
        "completeness_score": 0.92,
        "confidence_score": 0.88,
        "basic_info": {"major": "计算机科学与技术", "grade": "大三", "school": None},
        "knowledge_profile": {
            "overall_level": "advanced",
            "known_topics": [
                "栈", "队列", "链表", "数组", "哈希表", "二叉树",
                "排序算法", "查找算法", "图", "动态规划", "贪心算法",
            ],
            "weak_topics": ["回溯算法", "并查集"],
            "mastery_level": {
                "栈": 0.90, "队列": 0.88, "链表": 0.85, "数组": 0.92, "哈希表": 0.82,
                "二叉树": 0.80, "排序算法": 0.85, "查找算法": 0.78, "图": 0.72,
                "动态规划": 0.70, "贪心算法": 0.68, "回溯算法": 0.45, "并查集": 0.35,
            },
            "topic_dimensions": {
                "栈": _dim("high", "high", "high", "high"),
                "队列": _dim("high", "high", "high", "high"),
                "链表": _dim("high", "high", "high", "mid"),
                "数组": _dim("high", "high", "high", "high"),
                "哈希表": _dim("high", "high", "mid", "high"),
                "二叉树": _dim("high", "mid", "high", "high"),
                "排序算法": _dim("high", "high", "high", "mid"),
                "动态规划": _dim("mid", "mid", "mid", "high"),
                "回溯算法": _dim("mid", "low", "low", "mid"),
            },
        },
        "learning_goal": {
            "current_goal": "系统刷题备战大厂面试，覆盖所有高频考点",
            "target_course": "数据结构",
            "target_level": "interview_prep",
            "deadline": "2026-09-01",
        },
        "learning_preference": {
            "learning_style": "mixed",
            "resource_preference": {
                "document": 0.4, "mindmap": 0.3, "quiz": 0.95, "reading": 0.3,
                "video": 0.2, "animation": 0.2, "code_case": 0.95, "flowchart": 0.3,
            },
            "difficulty_preference": "challenge",
        },
        "learning_behavior": {
            "average_study_minutes": 120,
            "active_period": "evening",
            "completion_rate": 0.85,
            "recent_scores": [82, 78, 85, 88, 80],
            "last_knowledge_point": "动态规划",
        },
        "cognitive_profile": {
            "cognitive_style": "mixed",
            "abstract_understanding": "high",
            "hands_on_ability": "high",
            "reading_patience": "medium",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到面试冲刺型原型",
        },
    },

    "advanced_research": {
        "completeness_score": 0.90,
        "confidence_score": 0.86,
        "basic_info": {"major": "计算机科学与技术", "grade": "研一", "school": None},
        "knowledge_profile": {
            "overall_level": "advanced",
            "known_topics": [
                "栈", "队列", "链表", "数组", "哈希表", "二叉树",
                "排序算法", "查找算法", "图", "动态规划", "贪心算法", "回溯算法",
            ],
            "weak_topics": [],
            "mastery_level": {
                "栈": 0.92, "队列": 0.90, "链表": 0.88, "数组": 0.95, "哈希表": 0.85,
                "二叉树": 0.88, "排序算法": 0.90, "查找算法": 0.82, "图": 0.80,
                "动态规划": 0.78, "贪心算法": 0.75, "回溯算法": 0.72,
            },
            "topic_dimensions": {
                "栈": _dim("high", "high", "high", "high"),
                "队列": _dim("high", "high", "high", "high"),
                "链表": _dim("high", "high", "high", "high"),
                "数组": _dim("high", "high", "high", "high"),
                "二叉树": _dim("high", "high", "high", "high"),
                "图": _dim("high", "mid", "high", "high"),
                "动态规划": _dim("mid", "mid", "high", "high"),
            },
        },
        "learning_goal": {
            "current_goal": "深入研究高级数据结构与算法，为论文和研究做准备",
            "target_course": "数据结构",
            "target_level": "project_practice",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "reading",
            "resource_preference": {
                "document": 0.95, "mindmap": 0.5, "quiz": 0.4, "reading": 0.95,
                "video": 0.2, "animation": 0.2, "code_case": 0.6, "flowchart": 0.4,
            },
            "difficulty_preference": "challenge",
        },
        "learning_behavior": {
            "average_study_minutes": 150,
            "active_period": "morning",
            "completion_rate": 0.90,
            "recent_scores": [88, 92, 85, 90],
            "last_knowledge_point": "动态规划",
        },
        "cognitive_profile": {
            "cognitive_style": "verbal",
            "abstract_understanding": "high",
            "hands_on_ability": "medium",
            "reading_patience": "high",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到研究型深学者原型",
        },
    },

    "struggling_multi_weak": {
        # strategy_engine 分支: score < 0.3 → document + mindmap，从零开始
        "completeness_score": 0.65,
        "confidence_score": 0.60,
        "basic_info": {"major": "电子信息工程", "grade": "大二", "school": None},
        "knowledge_profile": {
            "overall_level": "beginner",
            "known_topics": [],
            "weak_topics": ["栈", "队列", "链表", "数组", "复杂度分析", "排序算法", "二叉树"],
            "mastery_level": {
                "栈": 0.10, "队列": 0.08, "链表": 0.12, "数组": 0.15,
                "复杂度分析": 0.05, "排序算法": 0.08, "二叉树": 0.05,
            },
            "topic_dimensions": {
                "栈": _dim("low", "low", "low", "low"),
                "队列": _dim("low", "low", "low", "low"),
                "链表": _dim("low", "low", "low", "low"),
                "数组": _dim("low", "low", "low", "low"),
                "复杂度分析": _dim("low", "low", "low", "low"),
                "排序算法": _dim("low", "low", "low", "low"),
                "二叉树": _dim("low", "low", "low", "low"),
            },
        },
        "learning_goal": {
            "current_goal": "跟上课程进度，至少通过期末考试",
            "target_course": "数据结构",
            "target_level": "exam_prep",
            "deadline": None,
        },
        "learning_preference": {
            "learning_style": "visual",
            "resource_preference": {
                "document": 0.7, "mindmap": 0.8, "quiz": 0.4, "reading": 0.3,
                "video": 0.9, "animation": 0.9, "code_case": 0.2, "flowchart": 0.7,
            },
            "difficulty_preference": "step_by_step",
        },
        "learning_behavior": {
            "average_study_minutes": 20,
            "active_period": "evening",
            "completion_rate": 0.30,
            "recent_scores": [25, 30, 22, 28],
            "last_knowledge_point": None,
        },
        "cognitive_profile": {
            "cognitive_style": "mixed",
            "abstract_understanding": "low",
            "hands_on_ability": "low",
            "reading_patience": "low",
        },
        "dynamic_update": {
            "last_updated_at": _now_iso(),
            "update_source": "archetype",
            "update_reason": "匹配到多维薄弱型原型",
        },
    },
}

ARCHETYPE_IDS: List[str] = list(ARCHETYPES.keys())


def get_archetype(archetype_id: str) -> dict:
    """获取指定原型的 profile 字典。"""
    if archetype_id not in ARCHETYPES:
        raise KeyError(f"Unknown archetype: {archetype_id}. Available: {ARCHETYPE_IDS}")
    return ARCHETYPES[archetype_id]


def match_archetype(profile: dict) -> str:
    """匹配给定 profile 到最近的原型，返回 archetype_id。

    匹配算法：
    1. 计算 profile 的 overall_level + learning_style + cognitive_style 三维特征
    2. 对每个原型计算特征距离
    3. 用 topic_dimensions 的 composite_score 均值作为辅助排序
    """
    profile_level = _extract_level(profile)
    profile_style = _extract_learning_style(profile)
    profile_cognitive = _extract_cognitive_style(profile)
    profile_score = _extract_avg_score(profile)

    best_id = "beginner_visual"
    best_distance = float("inf")

    for archetype_id, archetype in ARCHETYPES.items():
        a_level = _extract_level(archetype)
        a_style = _extract_learning_style(archetype)
        a_cognitive = _extract_cognitive_style(archetype)
        a_score = _extract_avg_score(archetype)

        # 特征距离：level(3) + style(2) + cognitive(1) + score差值(2)
        distance = (
            _level_distance(profile_level, a_level) * 3
            + _style_distance(profile_style, a_style) * 2
            + _cognitive_distance(profile_cognitive, a_cognitive) * 1
            + abs(profile_score - a_score) * 2
        )

        if distance < best_distance:
            best_distance = distance
            best_id = archetype_id

    return best_id


def build_archetype_context(archetype_id: str) -> str:
    """构建用于 LLM prompt 的原型描述文本。"""
    archetype = ARCHETYPES.get(archetype_id)
    if not archetype:
        return ""

    kp = archetype.get("knowledge_profile", {})
    goal = archetype.get("learning_goal", {})
    pref = archetype.get("learning_preference", {})
    beh = archetype.get("learning_behavior", {})
    cog = archetype.get("cognitive_profile", {})

    return (
        f"该学生最接近「{_archetype_name(archetype_id)}」类型：\n"
        f"- 知识水平：{kp.get('overall_level', '未知')}，"
        f"已掌握：{', '.join(kp.get('known_topics', [])[:3]) or '无'}，"
        f"薄弱点：{', '.join(kp.get('weak_topics', [])[:3]) or '无'}\n"
        f"- 学习风格：{pref.get('learning_style', 'mixed')}，"
        f"认知类型：{cog.get('cognitive_style', 'mixed')}\n"
        f"- 学习目标：{goal.get('target_level', 'project_practice')}，"
        f"日均学习：{beh.get('average_study_minutes', 45)}分钟\n"
        f"- 资源偏好：{_top_resource_types(pref.get('resource_preference', {}))}\n"
        f"请在此基础上根据实际对话数据进行个性化调整。"
    )


# ── 辅助函数 ──────────────────────────────────────────────────────────

_ARCHETYPE_NAMES = {
    "beginner_visual": "视觉型初学者",
    "beginner_hands_on": "动手型初学者",
    "intermediate_theory_strong": "理论强实践弱",
    "intermediate_practice_strong": "实践强理论弱",
    "intermediate_forgetful": "理解好易遗忘",
    "advanced_interview": "面试冲刺型",
    "advanced_research": "研究型深学者",
    "struggling_multi_weak": "多维薄弱型",
}


def _archetype_name(archetype_id: str) -> str:
    return _ARCHETYPE_NAMES.get(archetype_id, archetype_id)


_LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}
_STYLE_ORDER = {"visual": 0, "reading": 1, "hands-on": 2, "mixed": 3}
_COGNITIVE_ORDER = {"visual": 0, "verbal": 1, "hands-on": 2, "mixed": 3}


def _extract_level(profile: dict) -> str:
    kp = profile.get("knowledge_profile", {})
    return kp.get("overall_level", "beginner")


def _extract_learning_style(profile: dict) -> str:
    pref = profile.get("learning_preference", {})
    return pref.get("learning_style", "mixed")


def _extract_cognitive_style(profile: dict) -> str:
    cog = profile.get("cognitive_profile", {})
    return cog.get("cognitive_style", "mixed")


def _extract_avg_score(profile: dict) -> float:
    kp = profile.get("knowledge_profile", {})
    dims = kp.get("topic_dimensions", {})
    if not dims:
        return 0.2
    scores = []
    for v in dims.values():
        if isinstance(v, dict):
            d = KnowledgeDimension(**v)
            scores.append(d.composite_score)
        elif isinstance(v, KnowledgeDimension):
            scores.append(v.composite_score)
    return sum(scores) / len(scores) if scores else 0.2


def _level_distance(a: str, b: str) -> float:
    return abs(_LEVEL_ORDER.get(a, 0) - _LEVEL_ORDER.get(b, 0))


def _style_distance(a: str, b: str) -> float:
    if a == b:
        return 0.0
    return abs(_STYLE_ORDER.get(a, 3) - _STYLE_ORDER.get(b, 3)) * 0.5


def _cognitive_distance(a: str, b: str) -> float:
    if a == b:
        return 0.0
    return abs(_COGNITIVE_ORDER.get(a, 3) - _COGNITIVE_ORDER.get(b, 3)) * 0.5


def _top_resource_types(prefs: Dict[str, float]) -> str:
    if not prefs:
        return "无偏好数据"
    sorted_prefs = sorted(prefs.items(), key=lambda x: x[1], reverse=True)
    return ", ".join(f"{k}({v:.1f})" for k, v in sorted_prefs[:3])
