from __future__ import annotations
"""Strategy Engine — 画像标签 → 教学参数映射。

根据四维度组合（81种）动态生成教学参数，注入到提示词中。
不依赖LLM，纯规则引擎，快速响应。
"""

from typing import Dict,  List,  Optional

from app.schemas.profile import KnowledgeDimension, StudentProfile


# ── 四维度组合 → 教学参数映射 ─────────────────────────────────────────────

def get_teaching_params(dim: KnowledgeDimension) -> dict:
    """根据四维度组合，返回教学参数。

    Returns:
        {
            "difficulty": 1-3,
            "resource_depth": "beginner/intermediate/advanced",
            "quiz_type": "choice/case_analysis+code/mixed_with_review/...",
            "tutor_style": "教学风格描述",
            "resource_types": ["document", "quiz", ...],
            "review_interval_days": 0-7,
        }
    """
    score = dim.composite_score

    # 基础参数
    if score < 0.4:
        difficulty = 1
        resource_depth = "beginner"
    elif score < 0.7:
        difficulty = 2
        resource_depth = "intermediate"
    else:
        difficulty = 3
        resource_depth = "advanced"

    params = {
        "difficulty": difficulty,
        "resource_depth": resource_depth,
        "quiz_type": "mixed",
        "tutor_style": "平衡讲解与练习",
        "resource_types": ["document", "quiz"],
        "review_interval_days": 0,
    }

    # 特殊组合修正
    if dim.mastery == "high" and dim.application == "low":
        # 理论强但不会用
        params["quiz_type"] = "case_analysis+code"
        params["tutor_style"] = "多给实际场景和动手练习，少讲概念"
        params["resource_types"] = ["code_case", "quiz"]

    elif dim.understanding == "high" and dim.memory == "low":
        # 理解好但记不住
        params["quiz_type"] = "mixed_with_review"
        params["tutor_style"] = "用类比和图解帮助记忆，安排间隔复习"
        params["review_interval_days"] = 1

    elif dim.mastery == "low" and dim.understanding == "high":
        # 没学过但理解力强
        params["difficulty"] = min(difficulty + 1, 3)
        params["tutor_style"] = "快速过基础，重点放在应用和进阶"
        params["resource_types"] = ["document", "quiz", "code_case"]

    elif dim.mastery == "high" and dim.understanding == "low":
        # 知道概念但不理解原理
        params["tutor_style"] = "多问为什么，要求解释原理，用图解辅助"
        params["quiz_type"] = "short_answer+case_analysis"
        params["resource_types"] = ["document", "mindmap"]

    elif score < 0.3:
        # 全面薄弱
        params["tutor_style"] = "从零开始，每步确认理解，多给例子"
        params["resource_types"] = ["document", "mindmap"]

    elif score >= 0.75:
        # 全面优秀
        params["tutor_style"] = "跳过基础，给综合题和进阶挑战"
        params["quiz_type"] = "hard_comprehensive"
        params["resource_types"] = ["quiz", "code_case"]

    return params


def get_quiz_params(dim: KnowledgeDimension, stage: str = "learning") -> dict:
    """根据四维度和阶段，返回出题参数。

    Args:
        stage: "diagnostic" / "learning" / "review" / "assessment"

    Returns:
        {
            "total_questions": int,
            "difficulty_distribution": {"easy": n, "medium": n, "hard": n},
            "type_distribution": {"choice": n, "fill_blank": n, "code": n, "short_answer": n},
            "dimension_focus": ["mastery", ...],
        }
    """
    score = dim.composite_score

    if stage == "diagnostic":
        return {
            "total_questions": 5,
            "difficulty_distribution": {"easy": 2, "medium": 2, "hard": 1},
            "type_distribution": {"choice": 3, "fill_blank": 1, "short_answer": 1},
            "dimension_focus": ["mastery", "understanding"],
        }

    if stage == "review":
        return {
            "total_questions": 3,
            "difficulty_distribution": {"easy": 1, "medium": 2, "hard": 0},
            "type_distribution": {"choice": 1, "fill_blank": 1, "code": 1},
            "dimension_focus": ["memory", "application"],
        }

    if stage == "assessment":
        return {
            "total_questions": 8,
            "difficulty_distribution": {"easy": 2, "medium": 3, "hard": 3},
            "type_distribution": {"choice": 2, "fill_blank": 2, "code": 2, "short_answer": 2},
            "dimension_focus": ["mastery", "application", "memory", "understanding"],
        }

    # stage == "learning" (default)
    if score < 0.4:
        return {
            "total_questions": 4,
            "difficulty_distribution": {"easy": 2, "medium": 2, "hard": 0},
            "type_distribution": {"choice": 2, "fill_blank": 1, "short_answer": 1},
            "dimension_focus": ["mastery", "understanding"],
        }
    if score < 0.7:
        return {
            "total_questions": 5,
            "difficulty_distribution": {"easy": 1, "medium": 2, "hard": 2},
            "type_distribution": {"choice": 1, "fill_blank": 1, "code": 2, "short_answer": 1},
            "dimension_focus": ["mastery", "application", "understanding"],
        }
    return {
        "total_questions": 5,
        "difficulty_distribution": {"easy": 1, "medium": 1, "hard": 3},
        "type_distribution": {"choice": 1, "fill_blank": 1, "code": 2, "short_answer": 1},
        "dimension_focus": ["application", "understanding"],
    }


def get_resource_params(
    dim: KnowledgeDimension,
    learning_style: str = "mixed",
) -> dict:
    """根据四维度和学习风格，返回资源生成参数。

    Returns:
        {
            "resource_types": ["document", "quiz", ...],
            "difficulty": 1-3,
            "emphasis": "概念/实践/记忆/原理",
            "style_note": "风格描述",
        }
    """
    score = dim.composite_score

    # 基础资源类型
    if score < 0.4:
        resource_types = ["document", "mindmap"]
        emphasis = "概念"
    elif score < 0.7:
        resource_types = ["document", "quiz", "code_case"]
        emphasis = "实践"
    else:
        resource_types = ["quiz", "code_case"]
        emphasis = "综合"

    # 学习风格修正
    if learning_style == "visual":
        if "mindmap" not in resource_types:
            resource_types.insert(0, "mindmap")
    elif learning_style == "hands-on":
        if "code_case" not in resource_types:
            resource_types.insert(0, "code_case")
    elif learning_style == "reading":
        if "document" not in resource_types:
            resource_types.insert(0, "document")

    # 四维度修正
    if dim.mastery == "low":
        emphasis = "概念"
    elif dim.application == "low":
        emphasis = "实践"
        if "code_case" not in resource_types:
            resource_types.append("code_case")
    elif dim.memory == "low":
        emphasis = "记忆"
        if "mindmap" not in resource_types:
            resource_types.append("mindmap")
    elif dim.understanding == "low":
        emphasis = "原理"

    difficulty = 1 if score < 0.4 else (2 if score < 0.7 else 3)

    return {
        "resource_types": resource_types,
        "difficulty": difficulty,
        "emphasis": emphasis,
        "style_note": f"重点{emphasis}，风格适配{learning_style}",
    }


def get_path_params(dim: KnowledgeDimension) -> dict:
    """根据四维度，返回路径规划参数。

    Returns:
        {
            "path_type": "beginner/intermediate/advanced",
            "node_count": int,
            "minutes_per_node": int,
            "skip_mastered": bool,
            "priority": "补弱/进阶/平衡",
        }
    """
    score = dim.composite_score

    if score < 0.4:
        return {
            "path_type": "beginner",
            "node_count": 4,
            "minutes_per_node": 45,
            "skip_mastered": False,
            "priority": "补弱",
        }
    if score < 0.7:
        return {
            "path_type": "intermediate",
            "node_count": 3,
            "minutes_per_node": 30,
            "skip_mastered": True,
            "priority": "平衡",
        }
    return {
        "path_type": "advanced",
        "node_count": 3,
        "minutes_per_node": 20,
        "skip_mastered": True,
        "priority": "进阶",
    }


# ── 画像综合评估 ─────────────────────────────────────────────────────────

def compute_overall_level(topic_dimensions: Dict[str, KnowledgeDimension]) -> str:
    """根据所有知识点的四维度，计算整体水平。"""
    if not topic_dimensions:
        return "beginner"
    avg_score = sum(d.composite_score for d in topic_dimensions.values()) / len(topic_dimensions)
    if avg_score >= 0.7:
        return "advanced"
    if avg_score >= 0.4:
        return "intermediate"
    return "beginner"


def compute_weak_topics(topic_dimensions: Dict[str, KnowledgeDimension]) -> List[str]:
    """根据四维度，识别薄弱知识点。"""
    return [
        name for name, dim in topic_dimensions.items()
        if dim.composite_score < 0.4
    ]


def compute_known_topics(topic_dimensions: Dict[str, KnowledgeDimension]) -> List[str]:
    """根据四维度，识别已掌握知识点。"""
    return [
        name for name, dim in topic_dimensions.items()
        if dim.composite_score >= 0.7
    ]


def compute_mastery_level(topic_dimensions: Dict[str, KnowledgeDimension]) -> Dict[str, float]:
    """将四维度转换为兼容的 mastery_level 字典。"""
    return {
        name: round(dim.composite_score, 2)
        for name, dim in topic_dimensions.items()
    }


def merge_dimensions(
    existing: Optional[KnowledgeDimension],
    new: KnowledgeDimension,
    confidence: float = 0.6,
) -> KnowledgeDimension:
    """合并新旧四维度评估。

    策略：
    - 无旧数据 → 直接用新数据
    - 旧数据是默认全low（无真实信号）→ 直接用新数据
    - 高置信度(confidence >= 0.7) → 直接覆盖
    - 中置信度(0.4-0.7) → 加权平均
    - 低置信度(< 0.4) → 保留旧数据
    """
    if existing is None:
        return new

    # Default all-low means no real assessment data — use new directly
    is_default = (
        existing.mastery == "low"
        and existing.application == "low"
        and existing.memory == "low"
        and existing.understanding == "low"
    )
    if is_default:
        return new

    if confidence >= 0.7:
        return new

    if confidence < 0.4:
        return existing

    level_rank = {"low": 0, "mid": 1, "high": 2}
    rank_level = {0: "low", 1: "mid", 2: "high"}

    def weighted_merge(old: str, new_val: str) -> str:
        old_rank = level_rank.get(old, 0)
        new_rank = level_rank.get(new_val, 0)
        merged = round(old_rank * (1 - confidence) + new_rank * confidence)
        return rank_level[max(0, min(2, merged))]

    return KnowledgeDimension(
        mastery=weighted_merge(existing.mastery, new.mastery),
        application=weighted_merge(existing.application, new.application),
        memory=weighted_merge(existing.memory, new.memory),
        understanding=weighted_merge(existing.understanding, new.understanding),
    )
