from __future__ import annotations
from typing import List, Dict

"""AssessAgent — multi-dimensional learning assessment with cold-start support.

Three data sources:
  1. User self-fill (onboarding info: major, grade, goal)
  2. Diagnostic test (initial quiz results from DiagnosticAgent)
  3. Real learning behavior (learning records, path progress, scores)

Assessment stages (dynamic by data volume):
  - cold_start:  < 3 records  → low confidence, based on diagnostic only
  - developing:  3-10 records → medium confidence, mixed sources
  - mature:      10+ records  → high confidence, behavior-driven

Output fields:
  confidence, is_cold_start, data_sources, mastery_score,
  weak_points, learning_style, next_suggestions + existing fields
"""

import json
from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.services import graph_service, model_gateway


# ── Stage detection ───────────────────────────────────────────────────────

def _detect_stage(data: dict) -> tuple[str, float, List[str]]:
    """Return (stage, base_confidence, data_sources).

    stage: "cold_start" | "developing" | "mature"
    """
    sources: List[str] = []
    record_count = 0

    if data.get("has_profile"):
        sources.append("profile")
        profile = data.get("profile", {})
        # Diagnostic-created profiles have completion_rate=0 and no real study
        cr = profile.get("completion_rate", 0)
        if cr > 0:
            record_count += max(1, int(cr * 10))

    if data.get("has_path"):
        sources.append("learning_path")
        progress = data.get("path_progress", {})
        record_count += progress.get("completed_count", 0)

    if data.get("diagnostic"):
        sources.append("diagnostic")

    if data.get("learning_records"):
        sources.append("learning_records")
        record_count += len(data["learning_records"])

    if record_count < 3:
        return "cold_start", 0.35, sources
    elif record_count < 10:
        return "developing", 0.6, sources
    else:
        return "mature", 0.85, sources


# ── Data gathering ────────────────────────────────────────────────────────

def _gather_assessment_data(user_id: UUID) -> dict:
    """Collect all available data for assessment."""
    profile = repository.get_profile(user_id)
    path = repository.get_path(user_id)
    graph = graph_service.get_full_graph()

    data: dict = {
        "has_profile": profile is not None,
        "has_path": path is not None,
        "knowledge_graph_nodes": len(graph.get("nodes", [])),
    }

    if profile:
        data["profile"] = {
            "major": profile.basic_info.major,
            "grade": profile.basic_info.grade,
            "overall_level": profile.knowledge_profile.overall_level,
            "known_topics": profile.knowledge_profile.known_topics,
            "weak_topics": profile.knowledge_profile.weak_topics,
            "mastery_level": profile.knowledge_profile.mastery_level,
            "learning_style": profile.learning_preference.learning_style,
            "goal": profile.learning_goal.current_goal,
            "target_course": profile.learning_goal.target_course,
            "last_knowledge_point": profile.learning_behavior.last_knowledge_point,
            "average_study_minutes": profile.learning_behavior.average_study_minutes,
            "recent_scores": profile.learning_behavior.recent_scores,
            "completion_rate": profile.learning_behavior.completion_rate,
            "completeness_score": profile.completeness_score,
            "confidence_score": profile.confidence_score,
        }
        # Detect if this is a diagnostic-created profile
        if profile.dynamic_update.update_source == "diagnostic":
            data["diagnostic"] = {
                "source": "onboarding_quiz",
                "mastery_level": profile.knowledge_profile.mastery_level,
                "weak_topics": profile.knowledge_profile.weak_topics,
                "known_topics": profile.knowledge_profile.known_topics,
            }

    if path:
        completed = [n for n in path.nodes if n.status.value == "completed"]
        available = [n for n in path.nodes if n.status.value == "available"]
        locked = [n for n in path.nodes if n.status.value == "locked"]
        learning = [n for n in path.nodes if n.status.value == "learning"]
        skipped = [n for n in path.nodes if n.status.value == "skipped"]
        data["path_progress"] = {
            "title": path.title,
            "total_nodes": len(path.nodes),
            "completed_count": len(completed),
            "available_count": len(available),
            "locked_count": len(locked),
            "learning_count": len(learning),
            "skipped_count": len(skipped),
            "completion_rate": round(len(completed) / max(len(path.nodes), 1), 2),
            "completed_topics": [n.knowledge_point for n in completed],
            "available_topics": [n.knowledge_point for n in available],
            "learning_topics": [n.knowledge_point for n in learning],
            "skipped_topics": [n.knowledge_point for n in skipped],
        }

    # Learning records
    data["learning_records"] = repository.list_learning_records(user_id)

    # Graph context
    data["graph_context"] = {
        "all_topics": [{"id": n["id"], "name": n["name"], "level": n["level"]} for n in graph.get("nodes", [])],
        "learning_paths": graph.get("learning_paths", {}),
    }

    return data


# ── LLM assessment prompt ─────────────────────────────────────────────────

_ASSESSMENT_PROMPT = """\
你是学习评估Agent。根据以下学生数据，生成多维度学习评估报告。

当前评估阶段：{stage}（置信度基准：{base_confidence}）
数据来源：{data_sources}

学生数据：
{data}

请从以下维度评估，**根据数据量调整评估深度和置信度**：
1. **knowledge_mastery** — 各知识点掌握程度（0-1分）
   - 冷启动阶段：基于诊断测验和自填信息推断
   - 发展阶段：结合诊断+学习行为
   - 成熟阶段：基于完整学习记录
2. **weak_points** — 薄弱点分析（topic, severity, suggestion）
3. **learning_style** — 学习风格观察
4. **progress** — 学习进度评估
5. **review_recommendations** — 复习建议
6. **next_suggestions** — 下一步行动（3-5个）
7. **mastery_score** — 综合掌握度（0-1）

返回严格 JSON：
{{
  "knowledge_mastery": {{"topic_name": 0.0-1.0}},
  "weak_points": [{{"topic": "...", "severity": "高/中/低", "suggestion": "..."}}],
  "learning_style": {{"primary_style": "...", "analysis": "..."}},
  "progress": {{"completion_rate": 0.0, "velocity": "...", "quality": "...", "analysis": "..."}},
  "review_recommendations": [{{"topic": "...", "priority": 1, "method": "...", "reason": "..."}}],
  "next_suggestions": ["..."],
  "mastery_score": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "summary": "一句话总结"
}}
"""


def assess_learning(user_id: UUID) -> dict:
    """Generate a multi-dimensional learning assessment for a user."""
    data = _gather_assessment_data(user_id)
    stage, base_confidence, sources = _detect_stage(data)

    # No profile at all — return onboarding prompt
    if not data["has_profile"]:
        return {
            "status": "no_data",
            "is_cold_start": True,
            "confidence": 0.0,
            "data_sources": [],
            "mastery_score": 0.0,
            "message": "尚未收集到学习信息。请先完成初始诊断，系统将生成个性化评估。",
            "knowledge_mastery": {},
            "weak_points": [],
            "learning_style": {"primary_style": "未确定", "analysis": "需要先完成诊断"},
            "progress": {},
            "review_recommendations": [],
            "next_suggestions": ["完成初始诊断测验，获取个性化学习评估"],
            "next_steps": ["完成初始诊断测验，获取个性化学习评估"],
            "overall_score": 0.0,
            "summary": "请先完成初始诊断",
        }

    # Cold-start: return diagnostic-based assessment directly
    if stage == "cold_start":
        if data.get("diagnostic"):
            return _cold_start_assessment(data, base_confidence, sources)
        # Cold-start without diagnostic — use fallback (no LLM call)
        return _fallback_assessment(data, stage, base_confidence, sources)

    # Developing / Mature: use LLM
    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("assessment_v1", _ASSESSMENT_PROMPT, {
        "stage": stage,
        "base_confidence": base_confidence,
        "data_sources": ", ".join(sources),
        "data": json.dumps(data, ensure_ascii=False, indent=2),
    })

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["knowledge_mastery", "weak_points", "mastery_score", "overall_score", "summary"],
        )

        # Adjust confidence based on stage
        llm_confidence = float(raw.get("overall_score", base_confidence))
        final_confidence = min(1.0, max(base_confidence * 0.8, llm_confidence))

        result = {
            "status": "ok",
            "is_cold_start": stage == "cold_start",
            "confidence": round(final_confidence, 2),
            "data_sources": sources,
            "mastery_score": min(1.0, max(0.0, float(raw.get("mastery_score", 0.5)))),
            "knowledge_mastery": raw.get("knowledge_mastery", {}),
            "weak_points": raw.get("weak_points", []),
            "learning_style": raw.get("learning_style", {}),
            "progress": raw.get("progress", {}),
            "review_recommendations": raw.get("review_recommendations", []),
            "next_suggestions": raw.get("next_suggestions", raw.get("next_steps", [])),
            "next_steps": raw.get("next_suggestions", raw.get("next_steps", [])),
            "overall_score": min(1.0, max(0.0, float(raw.get("overall_score", 0.5)))),
            "summary": raw.get("summary", ""),
            "stage": stage,
        }

        # Enrich with graph prerequisite info
        graph_nodes = {n["name"]: n for n in data.get("graph_context", {}).get("all_topics", [])}
        for rec in result["review_recommendations"]:
            topic = rec.get("topic", "")
            if topic in graph_nodes:
                rec["prerequisites"] = graph_nodes[topic].get("depends_on", [])

        return result
    except Exception:
        return _fallback_assessment(data, stage, base_confidence, sources)


def _cold_start_assessment(data: dict, base_confidence: float, sources: List[str]) -> dict:
    """Build assessment from diagnostic data only (no LLM call needed)."""
    profile = data.get("profile", {})
    diagnostic = data.get("diagnostic", {})

    mastery = diagnostic.get("mastery_level", {})
    weak_topics = diagnostic.get("weak_topics", [])
    known_topics = diagnostic.get("known_topics", [])

    # Compute mastery score from diagnostic mastery levels
    if mastery:
        mastery_score = round(sum(mastery.values()) / len(mastery), 2)
    else:
        mastery_score = 0.3

    return {
        "status": "ok",
        "is_cold_start": True,
        "confidence": base_confidence,
        "data_sources": sources,
        "mastery_score": mastery_score,
        "knowledge_mastery": mastery,
        "weak_points": [
            {"topic": t, "severity": "高" if mastery.get(t, 0) < 0.3 else "中", "suggestion": f"建议从{t}基础概念开始学习"}
            for t in weak_topics
        ],
        "learning_style": {
            "primary_style": profile.get("learning_style", "mixed"),
            "analysis": "基于诊断测验初步判断，后续会随学习行为自动优化",
        },
        "progress": {
            "completion_rate": 0.0,
            "velocity": "尚未开始",
            "quality": "基于诊断测验",
            "analysis": "冷启动阶段，评估基于初始诊断结果",
        },
        "review_recommendations": [
            {"topic": t, "priority": i + 1, "method": "学习基础概念并完成配套练习", "reason": "诊断测验中表现薄弱"}
            for i, t in enumerate(weak_topics[:3])
        ],
        "next_suggestions": [
            f"从{profile.get('target_course', '课程')}的基础知识点开始学习",
            f"重点补强：{'、'.join(weak_topics[:3])}" if weak_topics else "按学习路径逐步推进",
            "完成一轮学习后系统将自动优化评估",
        ],
        "next_steps": [
            f"从{profile.get('target_course', '课程')}的基础知识点开始学习",
            f"重点补强：{'、'.join(weak_topics[:3])}" if weak_topics else "按学习路径逐步推进",
            "完成一轮学习后系统将自动优化评估",
        ],
        "overall_score": round(mastery_score * 0.5, 2),
        "summary": f"冷启动评估：已掌握{len(known_topics)}个知识点，{len(weak_topics)}个待加强",
        "stage": "cold_start",
    }


def _fallback_assessment(data: dict, stage: str, base_confidence: float, sources: List[str]) -> dict:
    """Generate assessment from data without LLM when API is unavailable."""
    profile = data.get("profile", {})
    progress = data.get("path_progress", {})

    weak_topics = profile.get("weak_topics", [])
    completion_rate = progress.get("completion_rate", 0.0)

    mastery: Dict[str, float] = {}
    # Use learning records for mastery scores when available
    learning_records = data.get("learning_records", [])
    if learning_records:
        from collections import defaultdict
        scores_by_topic: Dict[str, List[float]] = defaultdict(list)
        for rec in learning_records:
            kp = rec.get("knowledge_point", "")
            score = rec.get("score", 0)
            if kp:
                scores_by_topic[kp].append(score / 100.0 if score > 1 else score)
        for topic, scores in scores_by_topic.items():
            mastery[topic] = round(sum(scores) / len(scores), 2)
    for topic in progress.get("completed_topics", []):
        if topic not in mastery:
            mastery[topic] = 0.8
    for topic in progress.get("available_topics", []):
        if topic not in mastery:
            mastery[topic] = 0.4
    for topic in weak_topics:
        mastery[topic] = max(0.1, mastery.get(topic, 0.3) - 0.2)
    # Merge diagnostic mastery if available
    diag_mastery = profile.get("mastery_level", {})
    for k, v in diag_mastery.items():
        if k not in mastery:
            mastery[k] = v

    mastery_score = round(sum(mastery.values()) / max(len(mastery), 1), 2) if mastery else 0.3

    weak_points = [
        {"topic": t, "severity": "高" if i < 2 else "中", "suggestion": f"建议重点复习{t}的基础概念"}
        for i, t in enumerate(weak_topics[:5])
    ]

    return {
        "status": "ok_fallback",
        "is_cold_start": stage == "cold_start",
        "confidence": base_confidence,
        "data_sources": sources,
        "mastery_score": mastery_score,
        "knowledge_mastery": mastery,
        "weak_points": weak_points,
        "learning_style": {
            "primary_style": profile.get("learning_style", "未确定"),
            "analysis": "基于画像数据的初步分析",
        },
        "progress": {
            "completion_rate": completion_rate,
            "analysis": f"已完成 {progress.get('completed_count', 0)}/{progress.get('total_nodes', 0)} 个知识点",
        },
        "review_recommendations": [
            {"topic": t, "priority": i + 1, "method": "重新学习基础概念并做练习", "reason": "标记为薄弱点"}
            for i, t in enumerate(weak_topics[:3])
        ],
        "next_suggestions": [
            f"复习薄弱知识点：{'、'.join(weak_topics[:3])}" if weak_topics else "继续学习新知识点",
            "完成当前可用的学习节点",
            "尝试做练习题巩固知识",
        ],
        "next_steps": [
            f"复习薄弱知识点：{'、'.join(weak_topics[:3])}" if weak_topics else "继续学习新知识点",
            "完成当前可用的学习节点",
            "尝试做练习题巩固知识",
        ],
        "overall_score": round(completion_rate * 0.6 + 0.2, 2),
        "summary": f"学习进度 {completion_rate:.0%}，{len(weak_topics)} 个薄弱点待加强",
        "stage": stage,
    }


def get_assessment_for_path_planning(user_id: UUID) -> dict:
    """Return assessment data formatted for use by path planning agent."""
    assessment = assess_learning(user_id)
    return {
        "weak_topics": [wp["topic"] for wp in assessment.get("weak_points", [])],
        "mastery_levels": assessment.get("knowledge_mastery", {}),
        "review_topics": [r["topic"] for r in assessment.get("review_recommendations", [])[:3]],
        "overall_score": assessment.get("overall_score", 0.5),
        "is_cold_start": assessment.get("is_cold_start", False),
        "confidence": assessment.get("confidence", 0.5),
    }
