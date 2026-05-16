from __future__ import annotations
"""DiagnosticAgent — cold-start onboarding with 4-dimension assessment.

两条路径：
- 路径A（快速定位）：用户已有身份信息 → 3道定位题 → 四维度基线
- 路径B（完整诊断）：用户无身份信息 → 收集信息 + 5道诊断题 → 四维度评估
"""

from typing import Dict,  List,  Optional

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.repositories.vertical_loop_repository import repository
from app.schemas.profile import (
    BasicInfo,
    CognitiveProfile,
    DynamicUpdate,
    KnowledgeDimension,
    KnowledgeProfile,
    LearningBehavior,
    LearningGoalProfile,
    LearningPreference,
    StudentProfile,
)
from app.services import model_gateway
from app.services.learner_archetypes import build_archetype_context, get_archetype, match_archetype


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ── Question Bank Cache ───────────────────────────────────────────────────

_DIMENSION_TO_QUESTION_TYPE = {
    "mastery": "choice",
    "understanding": "short_answer",
    "application": "programming",
    "memory": "choice",
}

_DIFFICULTY_MAP = {1: "easy", 2: "medium", 3: "hard", 4: "hard", 5: "hard"}


def _query_question_bank(knowledge_point: str, needed: int) -> List[dict]:
    """Query the question bank for cached questions. Returns empty list if insufficient."""
    try:
        questions = repository.list_questions(knowledge_point=knowledge_point)
        if len(questions) >= needed:
            import random
            selected = random.sample(questions, needed)
            return [
                {
                    "id": q.get("id", str(uuid4())),
                    "topic": q.get("knowledge_point", knowledge_point),
                    "difficulty": {"easy": 1, "medium": 2, "hard": 3}.get(q.get("difficulty_level", "medium"), 2),
                    "dimension_test": q.get("tags", [None])[0] if q.get("tags") else "mastery",
                    "question": q.get("stem", ""),
                    "options": q.get("options", []),
                    "answer": q.get("answer", ""),
                    "explanation": q.get("explanation", ""),
                }
                for q in selected
            ]
    except Exception:
        pass
    return []


def _cache_questions_to_bank(questions: List[dict], knowledge_point: str, subject: str) -> None:
    """Cache LLM-generated questions to the question bank for future reuse."""
    try:
        for q in questions:
            dim_test = q.get("dimension_test", "mastery")
            q_type = _DIMENSION_TO_QUESTION_TYPE.get(dim_test, "choice")
            difficulty = _DIFFICULTY_MAP.get(q.get("difficulty", 2), "medium")
            repository.save_question({
                "knowledge_point": knowledge_point,
                "question_type": q_type,
                "stem": q.get("question", ""),
                "options": q.get("options", []),
                "answer": q.get("answer", ""),
                "explanation": q.get("explanation", ""),
                "difficulty_level": difficulty,
                "subject": subject,
                "tags": ["auto_generated", dim_test],
                "status": "active",
            })
    except Exception:
        pass  # caching failure should not block the quiz flow


# ── Step 1a: Quick positioning (路径A: 用户有身份信息) ─────────────────────

_QUICK_POSITION_PROMPT = """\
你是一个教育诊断专家。学生已提供身份信息，只需 {num_questions} 道题快速定位水平。

学生信息：
- 专业：{major}
- 年级：{grade}
- 学习目标：{goal}
- 目标课程：{subject}

要求：
1. 第1题：基础概念（判断是否学过）—— 测 mastery
2. 第2题：理解应用（判断是否理解原理）—— 测 understanding
3. 第3题：综合分析/编程（判断能否实际使用）—— 测 application
每题4选项，仅1个正确答案。标注所属知识点和难度(1-3)。

返回严格JSON：
{{
  "knowledge_points": ["知识点1", "知识点2", "知识点3"],
  "questions": [
    {{
      "id": 1,
      "topic": "知识点名称",
      "difficulty": 1,
      "dimension_test": "mastery",
      "question": "题目内容",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "A",
      "explanation": "解析"
    }},
    {{
      "id": 2,
      "topic": "知识点名称",
      "difficulty": 2,
      "dimension_test": "understanding",
      "question": "...",
      "options": [...],
      "answer": "B",
      "explanation": "..."
    }},
    {{
      "id": 3,
      "topic": "知识点名称",
      "difficulty": 3,
      "dimension_test": "application",
      "question": "...",
      "options": [...],
      "answer": "C",
      "explanation": "..."
    }}
  ]
}}
"""


def generate_quick_position_quiz(
    major: str,
    grade: str,
    goal: str,
    subject: str,
) -> dict:
    """Generate 3 quick positioning questions for users with identity info."""
    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("diagnostic_quick_v1", _QUICK_POSITION_PROMPT, {
        "major": major,
        "grade": grade,
        "goal": goal,
        "subject": subject,
        "num_questions": 3,
    })
    raw = model_gateway.generate_json(
        prompt,
        required_keys=["questions", "knowledge_points"],
    )
    questions = raw.get("questions", [])
    return {
        "knowledge_points": raw.get("knowledge_points", []),
        "questions": [
            {
                "id": q.get("id", i + 1),
                "topic": q.get("topic", ""),
                "difficulty": q.get("difficulty", 1),
                "dimension_test": q.get("dimension_test", "mastery"),
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "answer": q.get("answer", ""),
                "explanation": q.get("explanation", ""),
            }
            for i, q in enumerate(questions)
        ],
    }


# ── Step 1a2: Knowledge-point quiz (单一知识点诊断) ───────────────────────

_KP_QUIZ_PROMPT = """\
你是一个教育诊断专家。针对以下知识点，生成 {num_questions} 道诊断题，快速评估学生的掌握水平。

知识点：{knowledge_point}
学科：{subject}
学生水平：{overall_level}

要求：
1. 第1题：基础概念（判断是否学过）—— 测 mastery，难度1
2. 第2题：理解应用（判断是否理解原理）—— 测 understanding，难度2
3. 第3题：综合分析（判断能否实际使用）—— 测 application，难度3
每题4选项，仅1个正确答案。题目必须紧扣该知识点，不要偏离。

返回严格JSON：
{{
  "knowledge_points": ["{knowledge_point}"],
  "questions": [
    {{
      "id": 1,
      "topic": "{knowledge_point}",
      "difficulty": 1,
      "dimension_test": "mastery",
      "question": "题目内容",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "A",
      "explanation": "解析"
    }},
    {{
      "id": 2,
      "topic": "{knowledge_point}",
      "difficulty": 2,
      "dimension_test": "understanding",
      "question": "题目内容",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "B",
      "explanation": "解析"
    }},
    {{
      "id": 3,
      "topic": "{knowledge_point}",
      "difficulty": 3,
      "dimension_test": "application",
      "question": "题目内容",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "C",
      "explanation": "解析"
    }}
  ]
}}
"""


def generate_knowledge_point_quiz(
    knowledge_point: str,
    subject: str = "通用",
    overall_level: str = "beginner",
) -> dict:
    """Generate 3 targeted diagnostic questions for a single knowledge point."""
    # Check question bank cache first
    cached = _query_question_bank(knowledge_point, needed=3)
    if len(cached) >= 3:
        return {"knowledge_points": [knowledge_point], "questions": cached}

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("diagnostic_kp_v1", _KP_QUIZ_PROMPT, {
        "knowledge_point": knowledge_point,
        "subject": subject,
        "overall_level": overall_level,
        "num_questions": 3,
    })
    raw = model_gateway.generate_json(
        prompt,
        required_keys=["questions", "knowledge_points"],
    )
    questions = raw.get("questions", [])
    result_questions = [
        {
            "id": q.get("id", i + 1),
            "topic": q.get("topic", knowledge_point),
            "difficulty": q.get("difficulty", 1),
            "dimension_test": q.get("dimension_test", "mastery"),
            "question": q.get("question", ""),
            "options": q.get("options", []),
            "answer": q.get("answer", ""),
            "explanation": q.get("explanation", ""),
        }
        for i, q in enumerate(questions)
    ]
    # Cache generated questions for future reuse
    _cache_questions_to_bank(result_questions, knowledge_point, subject)
    return {"knowledge_points": raw.get("knowledge_points", [knowledge_point]), "questions": result_questions}


# ── Adaptive quiz: single question with escalating difficulty ──────────────

_ADAPTIVE_QUIZ_PROMPT = """你是一个教育诊断专家。针对知识点「{knowledge_point}」生成 1 道题。

学科：{subject}
学生当前水平：mastery={mastery}, understanding={understanding}, application={application}, memory={memory}
已答对 {correct} 题，已答错 {wrong} 题。
当前难度级别：{current_difficulty}（1=基础 2=中等 3=进阶）
测试维度：{next_dim}

要求：
1. 题目必须紧扣该知识点
2. 难度为 {current_difficulty} 级
3. 测试维度为 {next_dim}
4. 每题4选项，仅1个正确答案

返回严格JSON：{{
  "id": 1,
  "topic": "{knowledge_point}",
  "difficulty": {current_difficulty},
  "dimension_test": "{next_dim}",
  "question": "题目内容",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer": "A",
  "explanation": "解析"
}}"""

_DIM_PROGRESSION = ["mastery", "understanding", "application", "memory"]


def generate_adaptive_quiz_question(
    knowledge_point: str,
    subject: str = "通用",
    current_dim: Optional[dict] = None,
    correct_count: int = 0,
    wrong_count: int = 0,
    questions_answered: int = 0,
) -> dict:
    """Generate a single adaptive quiz question with escalating difficulty.

    Difficulty starts at 1 and increases as the user answers correctly.
    Dimension cycles through mastery → understanding → application → memory.
    """
    dim = current_dim or {"mastery": "low", "understanding": "low", "application": "low", "memory": "low"}

    # Determine next dimension to test
    next_dim = _DIM_PROGRESSION[questions_answered % len(_DIM_PROGRESSION)]

    # Determine difficulty: start at 1, increase on correct answers
    if wrong_count > 0:
        current_difficulty = max(1, min(correct_count + 1, 3) - 1)  # drop one level after wrong
    else:
        current_difficulty = min(1 + correct_count, 3)  # escalate: 1→2→3

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt(
        "diagnostic_adaptive_v1",
        _ADAPTIVE_QUIZ_PROMPT,
        {
            "knowledge_point": knowledge_point,
            "subject": subject,
            "mastery": dim.get("mastery", "low"),
            "understanding": dim.get("understanding", "low"),
            "application": dim.get("application", "low"),
            "memory": dim.get("memory", "low"),
            "correct": correct_count,
            "wrong": wrong_count,
            "current_difficulty": current_difficulty,
            "next_dim": next_dim,
        },
    )
    raw = model_gateway.generate_json(prompt, required_keys=["question", "answer"])
    return {
        "id": questions_answered + 1,
        "topic": raw.get("topic", knowledge_point),
        "difficulty": raw.get("difficulty", current_difficulty),
        "dimension_test": raw.get("dimension_test", next_dim),
        "question": raw.get("question", ""),
        "options": raw.get("options", []),
        "answer": raw.get("answer", ""),
        "explanation": raw.get("explanation", ""),
    }


# ── Step 1b: Full diagnostic quiz (路径B: 用户无身份信息) ──────────────────

_DIAGNOSTIC_PROMPT = """\
你是一个教育诊断专家。根据学生信息，生成 {num_questions} 道诊断题，覆盖该学科的核心基础知识。

学生信息：
- 专业：{major}
- 年级：{grade}
- 学习目标：{goal}
- 目标课程：{subject}

要求：
1. 题目覆盖该课程 3-5 个核心知识点
2. 难度从易到难递进（基础概念 → 理解应用 → 综合分析）
3. 每题 4 个选项，仅 1 个正确答案
4. 每题标注所属知识点、难度(1-3)和测试维度(mastery/application/memory/understanding)

返回严格 JSON：
{{
  "knowledge_points": ["知识点1", "知识点2", ...],
  "questions": [
    {{
      "id": 1,
      "topic": "知识点名称",
      "difficulty": 1,
      "dimension_test": "mastery",
      "question": "题目内容",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "A",
      "explanation": "解析"
    }}
  ]
}}
"""


def generate_diagnostic_quiz(
    major: str,
    grade: str,
    goal: str,
    subject: str,
    num_questions: int = 8,
) -> dict:
    """Generate diagnostic questions for onboarding."""
    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("diagnostic_full_v1", _DIAGNOSTIC_PROMPT, {
        "major": major,
        "grade": grade,
        "goal": goal,
        "subject": subject,
        "num_questions": num_questions,
    })
    raw = model_gateway.generate_json(
        prompt,
        required_keys=["questions", "knowledge_points"],
    )
    questions = raw.get("questions", [])
    return {
        "knowledge_points": raw.get("knowledge_points", []),
        "questions": [
            {
                "id": q.get("id", i + 1),
                "topic": q.get("topic", ""),
                "difficulty": q.get("difficulty", 1),
                "dimension_test": q.get("dimension_test", "mastery"),
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "answer": q.get("answer", ""),
                "explanation": q.get("explanation", ""),
            }
            for i, q in enumerate(questions)
        ],
    }


# ── Step 2: Four-dimension scoring ────────────────────────────────────────

_DIMENSION_SCORING_PROMPT = """\
根据学生答题结果，对每个涉及的知识点进行四维度评估。

学生信息：
- 专业：{major}
- 年级：{grade}
- 学习目标：{goal}
- 目标课程：{subject}

答题结果：
{answer_summary}

知识点覆盖：
{knowledge_points}

对每个知识点，评估四个维度（low/mid/high）：
- mastery（掌握）：是否知道这个概念的定义和基本用法
- application（应用）：能否在实际问题、编程中使用
- memory（记忆）：能否记住核心要点（基于答题正确率推断）
- understanding（理解）：能否解释原理、举一反三

评估规则：
| 信号 | mastery | application | memory | understanding |
|------|---------|-------------|--------|---------------|
| 选择题全对(难度≥2) | high | - | mid | mid |
| 选择题全对(难度1) | mid | - | mid | low |
| 编程/案例题全对 | - | high | - | mid |
| 能解释为什么 | - | - | - | high |
| 答错或未答 | low | low | low | low |

返回严格JSON：
{{
  "topic_dimensions": {{
    "知识点名": {{"mastery": "low/mid/high", "application": "low/mid/high", "memory": "low/mid/high", "understanding": "low/mid/high"}}
  }},
  "overall_level": "beginner/intermediate/advanced",
  "known_topics": ["已掌握知识点"],
  "weak_topics": ["薄弱知识点"],
  "learning_style_guess": "visual/reading/hands-on/mixed",
  "cognitive_style": "visual/verbal/mixed",
  "confidence_score": 0.0-1.0,
  "completeness_score": 0.0-1.0,
  "diagnosis_summary": "一句话诊断总结"
}}
"""


def _evaluate_dimensions(
    major: str,
    grade: str,
    goal: str,
    subject: str,
    quiz: dict,
    answers: Dict[int, str],
) -> dict:
    """Use LLM to evaluate four dimensions per knowledge point."""
    questions = quiz.get("questions", [])

    answer_lines = []
    for q in questions:
        qid = q["id"]
        user_ans = answers.get(qid, "未作答")
        correct_ans = q.get("answer", "?")
        hit = "正确" if user_ans.strip().upper() == correct_ans.strip().upper() else "错误"
        dim_test = q.get("dimension_test", "mastery")
        answer_lines.append(
            f"第{qid}题({q.get('topic', '')}, 难度{q.get('difficulty', 1)}, 测{dim_test}): "
            f"用户选{user_ans}, 正确答案{correct_ans}, {hit}"
        )

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("diagnostic_scoring_v1", _DIMENSION_SCORING_PROMPT, {
        "major": major,
        "grade": grade,
        "goal": goal,
        "subject": subject,
        "answer_summary": "\n".join(answer_lines),
        "knowledge_points": ", ".join(quiz.get("knowledge_points", [])),
    })

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["topic_dimensions", "overall_level", "diagnosis_summary"],
        )
        return raw
    except Exception:
        return None


def _fallback_dimension_scoring(
    quiz: dict,
    answers: Dict[int, str],
) -> dict:
    """Fallback: compute dimensions from raw scores without LLM."""
    questions = quiz.get("questions", [])
    topic_results: Dict[str, Dict[str, List[bool]]] = {}

    for q in questions:
        qid = q["id"]
        topic = q.get("topic", "未知")
        dim_test = q.get("dimension_test", "mastery")
        user_answer = answers.get(qid, "").strip().upper()
        is_correct = user_answer == q.get("answer", "").strip().upper()
        topic_results.setdefault(topic, {}).setdefault(dim_test, []).append(is_correct)

    topic_dimensions = {}
    for topic, dim_results in topic_results.items():
        dims = {}
        for dim_name in ("mastery", "application", "memory", "understanding"):
            results = dim_results.get(dim_name, [])
            if not results:
                dims[dim_name] = "low"
            else:
                rate = sum(results) / len(results)
                dims[dim_name] = "high" if rate >= 0.7 else ("mid" if rate >= 0.4 else "low")
        topic_dimensions[topic] = dims

    # Compute overall
    all_correct = sum(1 for q in questions if answers.get(q["id"], "").strip().upper() == q.get("answer", "").strip().upper())
    total = len(questions)
    rate = all_correct / max(total, 1)

    if rate >= 0.8:
        level = "advanced"
    elif rate >= 0.5:
        level = "intermediate"
    else:
        level = "beginner"

    known = []
    weak = []
    for t, d in topic_dimensions.items():
        try:
            score = KnowledgeDimension(**d).composite_score
        except Exception:
            continue
        if score >= 0.6:
            known.append(t)
        elif score < 0.4:
            weak.append(t)

    return {
        "topic_dimensions": topic_dimensions,
        "overall_level": level,
        "known_topics": known,
        "weak_topics": weak,
        "learning_style_guess": "mixed",
        "cognitive_style": "mixed",
        "confidence_score": 0.4,
        "completeness_score": 0.3,
        "diagnosis_summary": f"诊断完成，正确率 {all_correct}/{total}",
    }


# ── Main scoring function ─────────────────────────────────────────────────

def score_diagnostic(
    user_id: UUID,
    major: str,
    grade: str,
    goal: str,
    subject: str,
    quiz: dict,
    answers: Dict[int, str],
) -> dict:
    """Score diagnostic answers and create initial StudentProfile with 4-dimension assessment.

    Args:
        quiz: output from generate_diagnostic_quiz or generate_quick_position_quiz
        answers: {question_id: "A"/"B"/"C"/"D"}

    Returns dict with profile, assessment, and metadata.
    """
    questions = quiz.get("questions", [])
    total = len(questions)
    correct = 0
    topic_results: Dict[str, List[bool]] = {}

    for q in questions:
        qid = q["id"]
        topic = q.get("topic", "未知")
        user_answer = answers.get(qid, "").strip().upper()
        is_correct = user_answer == q.get("answer", "").strip().upper()
        if is_correct:
            correct += 1
        topic_results.setdefault(topic, []).append(is_correct)

    # Try LLM-based dimension scoring
    raw = _evaluate_dimensions(major, grade, goal, subject, quiz, answers)
    if raw is None:
        raw = _fallback_dimension_scoring(quiz, answers)

    # Build KnowledgeDimension objects
    raw_dims = raw.get("topic_dimensions", {})
    topic_dimensions = {}
    for topic, dims in raw_dims.items():
        if isinstance(dims, dict):
            topic_dimensions[topic] = KnowledgeDimension(
                mastery=dims.get("mastery", "low"),
                application=dims.get("application", "low"),
                memory=dims.get("memory", "low"),
                understanding=dims.get("understanding", "low"),
            )

    # Build mastery_level from dimensions
    mastery_level = {
        topic: round(dim.composite_score, 2)
        for topic, dim in topic_dimensions.items()
    }

    overall_level = raw.get("overall_level", "beginner")
    known_topics = raw.get("known_topics", [])
    weak_topics = raw.get("weak_topics", [])
    confidence_score = min(1.0, max(0.0, float(raw.get("confidence_score", 0.4))))
    completeness_score = min(1.0, max(0.0, float(raw.get("completeness_score", 0.3))))

    # Match to closest archetype for foundation values
    partial_profile = {
        "knowledge_profile": {
            "overall_level": overall_level,
            "known_topics": known_topics,
            "weak_topics": weak_topics,
            "topic_dimensions": {t: d.model_dump() for t, d in topic_dimensions.items()},
        },
    }
    archetype_id = match_archetype(partial_profile)
    archetype = get_archetype(archetype_id)

    # Use archetype as foundation; diagnostic data overrides knowledge parts
    arch_pref = archetype.get("learning_preference", {})
    arch_cog = archetype.get("cognitive_profile", {})
    arch_beh = archetype.get("learning_behavior", {})

    diag_style = raw.get("learning_style_guess", "")
    diag_cognitive = raw.get("cognitive_style", "")

    profile = StudentProfile(
        profile_id=uuid4(),
        user_id=user_id,
        version=1,
        completeness_score=max(completeness_score, 0.7),
        confidence_score=max(confidence_score, 0.6),
        basic_info=BasicInfo(major=major, grade=grade),
        knowledge_profile=KnowledgeProfile(
            overall_level=overall_level,
            known_topics=known_topics,
            weak_topics=weak_topics,
            mastery_level=mastery_level,
            topic_dimensions=topic_dimensions,
        ),
        learning_goal=LearningGoalProfile(
            current_goal=goal,
            target_course=subject,
            target_level=archetype.get("learning_goal", {}).get("target_level", "project_practice"),
        ),
        learning_preference=LearningPreference(
            learning_style=diag_style if diag_style and diag_style != "mixed" else arch_pref.get("learning_style", "mixed"),
            resource_preference=arch_pref.get("resource_preference", {}),
            difficulty_preference=arch_pref.get("difficulty_preference", "step_by_step"),
        ),
        learning_behavior=LearningBehavior(
            average_study_minutes=arch_beh.get("average_study_minutes", 45),
            active_period=arch_beh.get("active_period", "evening"),
            completion_rate=round(correct / max(total, 1), 2),
            recent_scores=[correct],
        ),
        cognitive_profile=CognitiveProfile(
            cognitive_style=diag_cognitive if diag_cognitive and diag_cognitive != "mixed" else arch_cog.get("cognitive_style", "mixed"),
            abstract_understanding=arch_cog.get("abstract_understanding", "medium"),
            hands_on_ability=arch_cog.get("hands_on_ability", "medium"),
            reading_patience=arch_cog.get("reading_patience", "medium"),
        ),
        dynamic_update=DynamicUpdate(
            last_updated_at=_now_iso(),
            update_source="diagnostic",
            update_reason=f"初始诊断测验生成，匹配原型：{archetype_id}",
        ),
    )

    # Save profile
    repository.save_profile(profile)

    # Build assessment snapshot
    assessment = {
        "status": "ok",
        "is_cold_start": True,
        "matched_archetype": archetype_id,
        "archetype_hint": build_archetype_context(archetype_id),
        "confidence": confidence_score,
        "data_sources": ["diagnostic"],
        "mastery_score": round(correct / max(total, 1), 2),
        "topic_dimensions": {
            topic: dim.model_dump()
            for topic, dim in topic_dimensions.items()
        },
        "knowledge_mastery": mastery_level,
        "weak_points": [
            {"topic": t, "severity": "高" if mastery_level.get(t, 0) < 0.3 else "中", "suggestion": f"建议从{t}基础概念开始学习"}
            for t in weak_topics
        ],
        "learning_style": {
            "primary_style": raw.get("learning_style_guess", "mixed"),
            "analysis": "基于诊断测验初步判断",
        },
        "progress": {
            "completion_rate": 0.0,
            "velocity": "尚未开始",
            "quality": f"诊断正确率 {correct}/{total}",
            "analysis": "冷启动阶段，基于诊断测验结果",
        },
        "review_recommendations": [
            {"topic": t, "priority": i + 1, "method": "学习基础概念并完成配套练习", "reason": "诊断测验中表现薄弱"}
            for i, t in enumerate(weak_topics[:3])
        ],
        "next_steps": [
            f"从{subject}的基础知识点开始学习",
            f"重点补强：{'、'.join(weak_topics[:3])}" if weak_topics else "按学习路径逐步推进",
            "完成一轮学习后系统将自动优化评估",
        ],
        "overall_score": round(correct / max(total, 1) * 0.5, 2),
        "summary": raw.get("diagnosis_summary", f"诊断完成，正确率 {correct}/{total}"),
    }

    return {
        "profile": profile.model_dump(mode="json"),
        "assessment": assessment,
        "quiz_result": {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / max(total, 1), 2),
            "topic_breakdown": {t: {"correct": sum(r), "total": len(r)} for t, r in topic_results.items()},
        },
    }
