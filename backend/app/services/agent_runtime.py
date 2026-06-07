from __future__ import annotations

from typing import Dict,  List,  Optional

import json
import logging

logger = logging.getLogger(__name__)
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.core.enums import AgentName, PathNodeStatus, ResourceStatus, ResourceType
from app.core.errors import ErrorCode, ServiceError
from app.schemas.agent import (
    CodeCaseDraft,
    FlowchartDraft,
    LearningPathDraft,
    MarkdownResourceDraft,
    MindmapDraft,
    MultimodalDraft,
    ProfileExtractionDraft,
    QuizDraft,
    QuizQuestionDraft,
    ReadingDraft,
    ResourceOutlineDraft,
    TutorAnswerDraft,
    VideoDraft,
)
from app.schemas.base_agent import BaseAgentProfile
from app.schemas.learning_path import LearningPath, LearningPathNode
from app.schemas.profile import (
    BasicInfo,
    CognitiveProfile,
    DynamicUpdate,
    KnowledgeProfile,
    LearningBehavior,
    LearningGoalProfile,
    LearningPreference,
    ProfileExtractRequest,
    StudentProfile,
)
from app.schemas.resource import LearningResource
from app.services import graph_service, model_gateway, rag_service
from app.services.strategy_engine import get_quiz_params, get_teaching_params
from app.prompts.strategy import (
    PROFILE_EVALUATE_SYSTEM,
    TEACHING_STRATEGY_SYSTEM,
    QUIZ_STRATEGY_SYSTEM,
    PATH_PLANNING_SYSTEM,
    DOCUMENT_STRATEGY_SYSTEM,
    MINDMAP_STRATEGY_SYSTEM,
    FLOWCHART_STRATEGY_SYSTEM,
    VISUAL_STRATEGY_SYSTEM,
    CODE_STRATEGY_SYSTEM,
    READING_STRATEGY_SYSTEM,
)
from app.prompts import fallbacks as _fb


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


from app.services.prompt_utils import get_template as _prompt_template, load_prompt_templates as _load_prompt_templates


def _build_prompt(name: str, fallback: str, variables: dict, strategy_prompt: Optional[str] = None) -> str:
    from app.services.prompt_utils import build_prompt as _safe_build
    template = _safe_build(name, fallback, variables)

    # Inject strategy engine params as explicit instruction sentences
    tc = variables.get("teaching_params") or {}
    param_instructions = _format_strategy_params(tc, variables)
    if strategy_prompt:
        parts = [strategy_prompt]
        if param_instructions:
            parts.append(param_instructions)
        parts.append(template)
        return "\n\n---\n\n".join(parts)
    if param_instructions:
        return f"{param_instructions}\n\n---\n\n{template}"
    return template


def _format_strategy_params(teaching_params: dict, variables: dict) -> str:
    """Convert strategy engine params into explicit instruction sentences for the LLM."""
    lines = []
    if teaching_params.get("tutor_style"):
        lines.append(f"【教学风格】{teaching_params['tutor_style']}")
    if teaching_params.get("difficulty"):
        lines.append(f"【难度级别】{teaching_params['difficulty']}（1=基础 2=中等 3=进阶）")
    if teaching_params.get("resource_depth"):
        lines.append(f"【内容深度】{teaching_params['resource_depth']}")
    if teaching_params.get("review_interval_days"):
        days = teaching_params["review_interval_days"]
        if days > 0:
            lines.append(f"【复习间隔】建议{days}天后复习")

    # Learning style adaptation
    style = variables.get("learning_style", "")
    if style:
        style_map = {
            "visual": "视觉型——多用图解、流程图、思维导图结构、类比图示",
            "reading": "阅读型——多用详细文字解释、参考文献、扩展阅读",
            "hands-on": "动手型——多给代码示例、实操步骤、动手练习",
            "mixed": "混合型——平衡文字讲解、图解和代码示例",
        }
        lines.append(f"【学习风格】{style_map.get(style, style)}")

    # Four-dimension adaptation
    topic_dim = variables.get("topic_dimension") or {}
    if topic_dim:
        dim_rules = []
        if topic_dim.get("mastery") == "low":
            dim_rules.append("mastery=low：重点讲解概念定义和基本用法，从最基础开始")
        if topic_dim.get("application") == "low":
            dim_rules.append("application=low：多给实际代码和案例，增加动手练习")
        if topic_dim.get("memory") == "low":
            dim_rules.append("memory=low：增加总结框、记忆口诀、类比帮助记忆")
        if topic_dim.get("understanding") == "low":
            dim_rules.append("understanding=low：多解释'为什么'，给出原理图解和逐步推导")
        if dim_rules:
            lines.append("【四维度适配】" + "；".join(dim_rules))

    return "\n".join(lines)


def _format_quiz_params(quiz_params: dict) -> str:
    """Convert quiz strategy params into explicit instruction sentences for the LLM."""
    lines = []
    total = quiz_params.get("total_questions")
    if total:
        lines.append(f"【题量】共生成 {total} 道题")

    dist = quiz_params.get("difficulty_distribution") or {}
    if dist:
        parts = []
        if dist.get("easy"):
            parts.append(f"简单 {dist['easy']} 题")
        if dist.get("medium"):
            parts.append(f"中等 {dist['medium']} 题")
        if dist.get("hard"):
            parts.append(f"困难 {dist['hard']} 题")
        if parts:
            lines.append("【难度分布】" + "、".join(parts))

    type_dist = quiz_params.get("type_distribution") or {}
    if type_dist:
        type_map = {"choice": "选择题", "fill_blank": "填空题", "code": "编程题", "short_answer": "简答题"}
        parts = []
        for t, n in type_dist.items():
            if n and n > 0:
                parts.append(f"{type_map.get(t, t)} {n} 道")
        if parts:
            lines.append("【题型分布】" + "、".join(parts))

    focus = quiz_params.get("dimension_focus") or []
    if focus:
        dim_map = {
            "mastery": "掌握度（概念定义）",
            "application": "应用力（实操案例）",
            "memory": "记忆力（巩固复习）",
            "understanding": "理解力（原理推导）",
        }
        labels = [dim_map.get(d, d) for d in focus]
        lines.append("【考察维度】" + "、".join(labels))

    return "\n".join(lines)


def _apply_base_agent_prompt(prompt: str, base_agent: Optional[BaseAgentProfile]) -> str:
    if base_agent is None:
        return prompt
    return (
        f"{base_agent.system_prompt}\n\n"
        f"【基层智能体】{base_agent.name}\n"
        f"【描述】{base_agent.description}\n"
        f"【输出风格】{base_agent.output_style}\n\n"
        f"{prompt}"
    )


def _conversation_text(conversation: List[Dict[str, str]]) -> str:
    return "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in conversation).strip()


def _merge_unique(left: List[str], right: List[str]) -> List[str]:
    merged = list(dict.fromkeys([*left, *right]))
    return [item for item in merged if item][:12]


def _get_teaching_context(profile: Optional[StudentProfile], knowledge_point: str) -> dict:
    """从画像获取指定知识点的教学策略参数。"""
    if profile is None:
        return {
            "overall_level": "beginner",
            "learning_style": "mixed",
            "topic_dimension": {},
            "teaching_note": "平衡讲解与练习",
            "teaching_params": {},
        }

    dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
    if dim:
        params = get_teaching_params(dim)
        topic_dimension = dim.model_dump()
    else:
        from app.schemas.profile import KnowledgeDimension
        params = get_teaching_params(KnowledgeDimension())
        topic_dimension = {}

    return {
        "overall_level": profile.knowledge_profile.overall_level,
        "learning_style": profile.learning_preference.learning_style,
        "topic_dimension": topic_dimension,
        "teaching_note": params.get("tutor_style", "平衡讲解与练习"),
        "teaching_params": params,
    }


def _profile_summary(profile: Optional[StudentProfile]) -> str:
    if profile is None:
        return "暂无学生画像信息"
    parts = []
    major = profile.basic_info.major
    grade = profile.basic_info.grade
    if major or grade:
        parts.append(f"该学生是{major or ''}{grade or ''}")
    level = profile.knowledge_profile.overall_level
    if level:
        parts.append(f"整体水平：{level}")
    style = profile.learning_preference.learning_style
    if style:
        parts.append(f"学习风格：{style}")
    weak = profile.knowledge_profile.weak_topics
    if weak:
        parts.append(f"薄弱知识点：{'、'.join(weak[:5])}")
    known = profile.knowledge_profile.known_topics
    if known:
        parts.append(f"已掌握：{'、'.join(known[:5])}")
    goal = profile.learning_goal.current_goal
    if goal:
        parts.append(f"当前学习目标：{goal}")
    course = profile.learning_goal.target_course
    if course:
        parts.append(f"目标课程：{course}")
    last_kp = profile.learning_behavior.last_knowledge_point
    if last_kp:
        parts.append(f"最近学习：{last_kp}")
    # Topic dimensions summary
    dims = profile.knowledge_profile.topic_dimensions
    if dims:
        dim_summaries = []
        for name, dim in list(dims.items())[:3]:
            m = dim.mastery if hasattr(dim, 'mastery') else '?'
            dim_summaries.append(f"{name}(掌握度:{m})")
        parts.append(f"知识点维度：{', '.join(dim_summaries)}")
    return "。".join(parts) + "。" if parts else "暂无详细画像"


# ── Profile extraction ─────────────────────────────────────────────────────


def build_profile(request: ProfileExtractRequest, previous: Optional[StudentProfile], base_agent: Optional[BaseAgentProfile] = None) -> StudentProfile:
    from app.services.learner_archetypes import build_archetype_context, match_archetype

    archetype_hint = ""
    if previous:
        try:
            archetype_id = match_archetype(previous.model_dump())
            archetype_hint = build_archetype_context(archetype_id)
        except Exception:
            pass

    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "profile_extract_v1",
            "你是画像构建Agent。请从对话里抽取并更新学生画像，至少覆盖专业、年级、知识基础、学习风格、学习目标、薄弱点、活跃时段、学习时长等维度，返回严格 JSON。",
            {
                "conversation": request.conversation,
                "previous_profile": _profile_summary(previous),
                "learning_behavior": request.learning_behavior or {},
                "archetype_hint": archetype_hint,
            },
            strategy_prompt=PROFILE_EVALUATE_SYSTEM,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=[
                "basic_info",
                "knowledge_profile",
                "learning_goal",
                "learning_preference",
                "learning_behavior",
                "cognitive_profile",
                "completeness_score",
                "confidence_score",
                "update_reason",
            ],
            schema=ProfileExtractionDraft,
        )
        draft = ProfileExtractionDraft.model_validate(raw)
    except Exception as exc:
        if previous:
            return previous
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"画像构建失败且无历史画像可回退: {exc}") from exc

    version = (previous.version + 1) if previous else 1
    return StudentProfile(
        profile_id=uuid4(),
        user_id=request.user_id,
        version=version,
        completeness_score=draft.completeness_score,
        confidence_score=draft.confidence_score,
        basic_info=draft.basic_info,
        knowledge_profile=draft.knowledge_profile,
        learning_goal=draft.learning_goal,
        learning_preference=draft.learning_preference,
        learning_behavior=draft.learning_behavior,
        cognitive_profile=draft.cognitive_profile,
        dynamic_update=DynamicUpdate(
            last_updated_at=_now_iso(),
            update_source="conversation",
            update_reason=draft.update_reason,
        ),
    )


# ── Learning path ──────────────────────────────────────────────────────────


def build_learning_path(user_id: UUID, goal: str, subject: str, profile: Optional[StudentProfile], base_agent: Optional[BaseAgentProfile] = None) -> LearningPath:
    weak_topics = profile.knowledge_profile.weak_topics if profile else []

    # Enrich with assessment data if available
    assessment_context = {}
    try:
        from app.services import assess_agent
        assessment_data = assess_agent.get_assessment_for_path_planning(user_id)
        if assessment_data.get("mastery_levels"):
            assessment_context = assessment_data
    except Exception:
        pass

    # Enrich prompt with knowledge graph context
    graph_data = graph_service.get_full_graph(subject=subject)
    graph_nodes_summary = [
        {"id": n["id"], "name": n["name"], "level": n["level"], "depends_on": n.get("depends_on", [])}
        for n in graph_data.get("nodes", [])
    ]
    learning_paths = graph_data.get("learning_paths", {})

    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "path_planning_v1",
            "你是路径规划Agent。请根据学生画像、学习目标和薄弱点规划个性化学习路径。要求：\n"
            "1. 输出知识点顺序、推荐资源类型和时间安排\n"
            "2. 根据学生薄弱点优先安排补弱内容\n"
            "3. 每个节点推荐2-3种资源类型\n"
            "4. 总时长控制在120-240分钟\n"
            "5. **必须尊重知识点前置依赖**：若知识点B依赖A，则A必须排在B之前\n"
            "6. 参考下方知识图谱的依赖关系和推荐学习路径\n"
            "返回严格 JSON。",
            {
                "goal": goal,
                "subject": subject,
                "profile": _profile_summary(profile),
                "weak_topics": weak_topics,
                "overall_level": profile.knowledge_profile.overall_level if profile else "beginner",
                "learning_style": profile.learning_preference.learning_style if profile else "mixed",
                "known_topics": profile.knowledge_profile.known_topics if profile else [],
                "teaching_note": "根据画像规划路径",
                "knowledge_graph": {
                    "nodes": graph_nodes_summary,
                    "recommended_paths": learning_paths,
                },
                "assessment": assessment_context,
            },
            strategy_prompt=PATH_PLANNING_SYSTEM,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "strategy", "nodes"],
            schema=LearningPathDraft,
        )
        draft = LearningPathDraft.model_validate(raw)
    except Exception as exc:
        raise ServiceError(ErrorCode.LLM_GENERATION_FAILED, f"路径规划失败: {exc}") from exc

    # Enforce dependency ordering: resolve prerequisite chain for selected nodes
    selected_names = [node.knowledge_point for node in draft.nodes]
    # Map knowledge_point names to graph node IDs
    name_to_id = {n["name"]: n["id"] for n in graph_data.get("nodes", [])}
    selected_ids = [name_to_id.get(name) for name in selected_names if name in name_to_id]

    if selected_ids:
        ordered_ids = graph_service.resolve_prerequisite_chain(selected_ids, subject=subject)
        id_to_name = {v: k for k, v in name_to_id.items()}
        ordered_names = [id_to_name[nid] for nid in ordered_ids if nid in id_to_name]
        # Reorder draft nodes to respect dependency order
        nodes_by_name = {node.knowledge_point: node for node in draft.nodes}
        reordered = [nodes_by_name[name] for name in ordered_names if name in nodes_by_name]
        # Append any nodes not in graph (custom LLM-generated nodes) at the end
        for node in draft.nodes:
            if node.knowledge_point not in reordered:
                reordered.append(node)
        draft.nodes = reordered

    return LearningPath(
        path_id=uuid4(),
        user_id=user_id,
        title=draft.title,
        goal=goal,
        strategy={**draft.strategy, "source_model": model_gateway.get_model_status()["mode"]},
        nodes=[
            LearningPathNode(
                node_id=uuid4(),
                order=index + 1,
                knowledge_point=node.knowledge_point,
                estimated_minutes=node.estimated_minutes,
                recommended_resource_types=node.recommended_resource_types,
                reason=node.reason,
                status=PathNodeStatus.AVAILABLE if index == 0 else PathNodeStatus.LOCKED,
            )
            for index, node in enumerate(draft.nodes)
        ],
    )


# ── RAG context ────────────────────────────────────────────────────────────


def _rag_context(knowledge_point: str, subject: str) -> List[dict]:
    try:
        return rag_service.search_knowledge(knowledge_point, subject=subject, top_k=3)
    except Exception:
        logger.warning("RAG 检索失败，资源将缺少知识库上下文: kp=%s subject=%s", knowledge_point, subject, exc_info=True)
        return []


# ── Resource generation ────────────────────────────────────────────────────


def _rag_sources(rag_hits: List[dict]) -> List[dict]:
    sources: List[dict] = []
    for item in rag_hits:
        sources.append({
            "chunk_id": item.get("chunk_id", ""),
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "source_name": item.get("source_name", ""),
            "source_url": item.get("source_url", ""),
            "source_type": item.get("source_type", ""),
            "license": item.get("license", ""),
            "authority_level": item.get("authority_level", ""),
            "review_status": item.get("review_status", ""),
            "retrieval_engine": item.get("retrieval_engine", ""),
            "score": item.get("score", 0),
        })
    return sources


def build_learning_resource(
    user_id: UUID,
    subject: str,
    knowledge_point: str,
    resource_type: ResourceType,
    difficulty: str,
    profile: Optional[StudentProfile],
    base_agent: Optional[BaseAgentProfile] = None,
    conversation_id: Optional[UUID] = None,
) -> LearningResource:
    rag_hits = _rag_context(knowledge_point, subject)
    rag_titles = [item.get("title", "") for item in rag_hits]
    common_metadata = {
        "model_status": model_gateway.get_model_status(),
        "profile_basis": _profile_summary(profile),
        "rag_basis": [item.get("chunk_id", "") for item in rag_hits],
        "rag_titles": rag_titles,
        "rag_sources": _rag_sources(rag_hits),
        "subject": subject,
        "knowledge_point": knowledge_point,
    }

    if resource_type == ResourceType.DOCUMENT:
        content, generated_by, metadata = _generate_document(
            profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
        )
    elif resource_type == ResourceType.READING:
        content, generated_by, metadata = _generate_reading(
            profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
        )
    elif resource_type == ResourceType.QUIZ:
        content, generated_by, metadata = _generate_quiz(
            profile, knowledge_point, difficulty, rag_hits, common_metadata, base_agent
        )
    elif resource_type == ResourceType.MINDMAP:
        content, generated_by, metadata = _generate_mindmap(
            profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
        )
    elif resource_type in {ResourceType.VIDEO, ResourceType.ANIMATION}:
        content, generated_by, metadata = _generate_video_storyboard(
            profile, knowledge_point, resource_type, subject, difficulty, rag_hits, common_metadata, base_agent
        )
    elif resource_type == ResourceType.FLOWCHART:
        content, generated_by, metadata = _generate_flowchart(
            profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
        )
    else:
        content, generated_by, metadata = _generate_code(
            profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
        )

    is_failed = metadata.pop("_failed", False)
    # Heuristic quality: base 0.7, bonus for content completeness
    if is_failed:
        quality = 0.0
    else:
        content_len = len(content) if content else 0
        quality = min(0.95, 0.7 + 0.05 * (content_len // 500))
    return LearningResource(
        resource_id=uuid4(),
        user_id=user_id,
        conversation_id=conversation_id,
        knowledge_point=knowledge_point,
        resource_type=resource_type,
        title=f"{knowledge_point} - {resource_type.value}",
        difficulty=difficulty,
        content=content,
        recommendation_reason="结合学生画像、学习目标和知识库检索结果生成。",
        generated_by=generated_by,
        quality_score=quality,
        status=ResourceStatus.FAILED if is_failed else ResourceStatus.PUBLISHED,
        metadata=metadata,
    )


def _generate_outline(
    knowledge_point: str,
    subject: str,
    difficulty: str,
    profile: Optional[StudentProfile],
    rag_hits: list,
    base_agent: Optional[BaseAgentProfile],
    resource_kind: str = "document",
) -> Optional[ResourceOutlineDraft]:
    """Stage 1: Generate a structured outline before filling content."""
    tc = _get_teaching_context(profile, knowledge_point)
    kind_label = "学习文档" if resource_kind == "document" else "阅读材料"
    prompt = _apply_base_agent_prompt(
        _build_prompt(
            f"outline_{resource_kind}_v1",
            f"为知识点生成{kind_label}的结构化大纲。\n"
            "返回 JSON：{title, summary, sections: [{heading, key_points, description}]}",
            {
                "student_profile": _profile_summary(profile),
                "knowledge_point": knowledge_point,
                "subject": subject,
                "difficulty": difficulty,
                "rag_context": rag_hits,
                **tc,
            },
        ),
        base_agent,
    )
    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "summary", "sections"],
            schema=ResourceOutlineDraft,
        )
        return ResourceOutlineDraft.model_validate(raw)
    except Exception:
        return None


def _assemble_sections(sections: list, knowledge_point: str) -> str:
    """Assemble section contents into a single markdown document."""
    parts: list[str] = []
    for sec in sections:
        heading = sec.get("heading", "")
        content = sec.get("content", "")
        if heading:
            parts.append(f"## {heading}")
        if content:
            parts.append(content)
    return "\n\n".join(parts) if parts else f"# {knowledge_point}\n\n内容生成中，请稍后重试。"


def _generate_document(
    profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    effective_diff = str(tc["teaching_params"].get("difficulty", difficulty))
    used_two_stage = False

    # Stage 1: Generate outline
    outline = _generate_outline(knowledge_point, subject, effective_diff, profile, rag_hits, base_agent, "document")

    if outline and outline.sections:
        # Stage 2: Fill each section with detailed content
        section_specs = [
            {"heading": s.heading, "key_points": s.key_points, "description": s.description}
            for s in outline.sections
        ]
        prompt = _apply_base_agent_prompt(
            _build_prompt(
                "resource_document_v2",
                "根据大纲逐章节生成详细内容。\n"
                "返回 JSON：{sections: [{heading, content}], examples, common_mistakes, next_steps}",
                {
                    "student_profile": _profile_summary(profile),
                    "knowledge_point": knowledge_point,
                    "subject": subject,
                    "difficulty": effective_diff,
                    "outline": section_specs,
                    "rag_context": rag_hits,
                    **tc,
                },
                strategy_prompt=DOCUMENT_STRATEGY_SYSTEM,
            ),
            base_agent,
        )
        try:
            raw = model_gateway.generate_json(
                prompt,
                required_keys=["sections"],
            )
            sections = raw.get("sections", [])
            markdown_content = _assemble_sections(sections, knowledge_point)
            draft = MarkdownResourceDraft(
                title=outline.title,
                markdown=markdown_content,
                summary=outline.summary,
                outline=[s.heading for s in outline.sections],
                examples=raw.get("examples", []),
                common_mistakes=raw.get("common_mistakes", []),
                next_steps=raw.get("next_steps", []),
            )
            used_two_stage = True
        except Exception:
            # Fallback to single-stage if section fill fails
            draft = None
    else:
        draft = None

    # Fallback: single-stage generation (original behavior)
    if draft is None:
        prompt = _apply_base_agent_prompt(
            _build_prompt(
                "resource_document_v1",
                "根据知识点和学生画像生成结构化 Markdown 学习文档。\n"
                "返回 JSON：{title, markdown, summary, outline, examples, common_mistakes, next_steps}",
                {
                    "student_profile": _profile_summary(profile),
                    "knowledge_point": knowledge_point,
                    "subject": subject,
                    "difficulty": effective_diff,
                    "rag_context": rag_hits,
                    **tc,
                },
                strategy_prompt=DOCUMENT_STRATEGY_SYSTEM,
            ),
            base_agent,
        )
        try:
            raw = model_gateway.generate_json(
                prompt,
                required_keys=["title", "markdown", "summary"],
                schema=MarkdownResourceDraft,
            )
            draft = MarkdownResourceDraft.model_validate(raw)
        except Exception as exc:
            return (
                f"文档生成失败，请稍后重试。",
                AgentName.DOCUMENT.value,
                {**common_metadata, "error": str(exc), "_failed": True},
            )

    content = draft.markdown
    metadata = {**common_metadata, "draft": draft.model_dump(mode="json"), "two_stage": used_two_stage}
    return content, AgentName.DOCUMENT.value, metadata


def _generate_reading(
    profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    effective_diff = str(tc["teaching_params"].get("difficulty", difficulty))
    used_two_stage = False

    # Stage 1: Generate outline
    outline = _generate_outline(knowledge_point, subject, effective_diff, profile, rag_hits, base_agent, "reading")

    if outline and outline.sections:
        # Stage 2: Fill each section with detailed content
        section_specs = [
            {"heading": s.heading, "key_points": s.key_points, "description": s.description}
            for s in outline.sections
        ]
        prompt = _apply_base_agent_prompt(
            _build_prompt(
                "resource_reading_v2",
                "根据大纲逐章节生成深度阅读内容，侧重叙述、案例分析和思考。\n"
                "返回 JSON：{sections: [{heading, content}], key_concepts, discussion_questions, references}",
                {
                    "student_profile": _profile_summary(profile),
                    "knowledge_point": knowledge_point,
                    "subject": subject,
                    "difficulty": effective_diff,
                    "outline": section_specs,
                    "rag_context": rag_hits,
                    **tc,
                },
                strategy_prompt=READING_STRATEGY_SYSTEM,
            ),
            base_agent,
        )
        try:
            raw = model_gateway.generate_json(
                prompt,
                required_keys=["sections"],
            )
            sections = raw.get("sections", [])
            markdown_content = _assemble_sections(sections, knowledge_point)
            draft = ReadingDraft(
                title=outline.title,
                markdown=markdown_content,
                summary=outline.summary,
                key_concepts=raw.get("key_concepts", []),
                discussion_questions=raw.get("discussion_questions", []),
                references=raw.get("references", []),
            )
            used_two_stage = True
        except Exception:
            draft = None
    else:
        draft = None

    # Fallback: single-stage generation
    if draft is None:
        prompt = _apply_base_agent_prompt(
            _build_prompt(
                "resource_reading_v1",
                "生成深度阅读材料，侧重叙述、案例分析和思考。\n"
                "返回 JSON：{title, markdown, summary, key_concepts, discussion_questions, references}",
                {
                    "student_profile": _profile_summary(profile),
                    "knowledge_point": knowledge_point,
                    "subject": subject,
                    "difficulty": effective_diff,
                    "rag_context": rag_hits,
                    **tc,
                },
                strategy_prompt=READING_STRATEGY_SYSTEM,
            ),
            base_agent,
        )
        try:
            raw = model_gateway.generate_json(
                prompt,
                required_keys=["title", "markdown", "summary"],
                schema=ReadingDraft,
            )
            draft = ReadingDraft.model_validate(raw)
        except Exception as exc:
            return (
                "阅读材料生成失败，请稍后重试。",
                AgentName.DOCUMENT.value,
                {**common_metadata, "error": str(exc), "_failed": True},
            )

    content = draft.markdown
    metadata = {**common_metadata, "draft": draft.model_dump(mode="json"), "two_stage": used_two_stage}
    return content, AgentName.DOCUMENT.value, metadata


def _generate_quiz(
    profile, knowledge_point, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point) if profile else None
    quiz_params = get_quiz_params(dim, stage="learning") if dim else {
        "total_questions": 5,
        "difficulty_distribution": {"easy": 1, "medium": 2, "hard": 2},
        "type_distribution": {"choice": 1, "fill_blank": 1, "code": 2, "short_answer": 1},
        "dimension_focus": ["mastery", "application", "understanding"],
    }

    # Check question bank cache first
    total_needed = quiz_params.get("total_questions", 5)
    from app.services.diagnostic_agent import _query_question_bank
    cached = _query_question_bank(knowledge_point, needed=total_needed)
    if len(cached) >= total_needed:
        draft = QuizDraft(
            title=f"{knowledge_point} - 练习题",
            overview=f"来自题库缓存的 {knowledge_point} 练习题",
            questions=[
                QuizQuestionDraft(
                    type=q.get("dimension_test", "choice"),
                    stem=q.get("question", ""),
                    options=q.get("options", []),
                    answer=str(q.get("answer", "")),
                    explanation=q.get("explanation", ""),
                    difficulty={1: "beginner", 2: "intermediate", 3: "advanced"}.get(q.get("difficulty", 2), "intermediate"),
                )
                for q in cached
            ],
        )
        content = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
        metadata = {**common_metadata, "question_types": [q.type for q in draft.questions], "draft": draft.model_dump(mode="json"), "source": "cache"}
        return (content, AgentName.QUIZ.value, metadata)

    quiz_instructions = _format_quiz_params(quiz_params)
    strategy_with_quiz = QUIZ_STRATEGY_SYSTEM
    if quiz_instructions:
        strategy_with_quiz = f"{QUIZ_STRATEGY_SYSTEM}\n\n{quiz_instructions}"

    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "resource_quiz_v1",
            "你是题库生成Agent。请根据知识点生成不同题型和难度的练习题。\n"
            "要求：\n"
            "1. 至少包含选择题、填空题、编程题、案例分析题各1道\n"
            "2. 每道题给出答案和详细解析\n"
            "3. 难度从易到难递进\n"
            "返回严格 JSON，包含 title, overview, questions, scoring_rules。",
            {
                "knowledge_point": knowledge_point,
                "difficulty": str(tc["teaching_params"].get("difficulty", difficulty)),
                "rag_context": rag_hits,
                "overall_level": tc["overall_level"],
                "topic_dimension": tc["topic_dimension"],
                "quiz_strategy": tc["teaching_params"].get("quiz_type", "mixed"),
                **quiz_params,
            },
            strategy_prompt=strategy_with_quiz,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "questions"],
            schema=QuizDraft,
        )
    except Exception as exc:
        fallback = json.dumps({"title": f"{knowledge_point} - 练习题", "questions": [], "error": "题目生成失败，请稍后重试。"}, ensure_ascii=False)
        return (fallback, AgentName.QUIZ.value, {**common_metadata, "error": str(exc), "_failed": True})
    draft = QuizDraft.model_validate(raw)
    content = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
    metadata = {
        **common_metadata,
        "question_types": [q.type for q in draft.questions],
        "draft": draft.model_dump(mode="json"),
    }
    return content, AgentName.QUIZ.value, metadata


def _generate_mindmap(
    profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "resource_mindmap_v1",
            "生成 Markmap 格式的思维导图。\n"
            "返回 JSON：{title, mindmap_markdown, summary, key_branches}",
            {
                "student_profile": _profile_summary(profile),
                "knowledge_point": knowledge_point,
                "subject": subject,
                "difficulty": str(tc["teaching_params"].get("difficulty", difficulty)),
                "rag_context": rag_hits,
                **tc,
            },
            strategy_prompt=MINDMAP_STRATEGY_SYSTEM,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "mindmap_markdown"],
            schema=MindmapDraft,
        )
    except Exception as exc:
        return (
            "思维导图生成失败，请稍后重试。",
            AgentName.MINDMAP.value,
            {**common_metadata, "error": str(exc), "_failed": True},
        )
    draft = MindmapDraft.model_validate(raw)
    content = draft.mindmap_markdown
    metadata = {**common_metadata, "draft": draft.model_dump(mode="json")}
    return content, AgentName.MINDMAP.value, metadata


def _generate_flowchart(
    profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "resource_flowchart_v1",
            "生成 draw.io XML 格式的教学流程图。\n"
            "返回 JSON：{title, drawio_xml, summary, node_count}",
            {
                "student_profile": _profile_summary(profile),
                "knowledge_point": knowledge_point,
                "subject": subject,
                "difficulty": str(tc["teaching_params"].get("difficulty", difficulty)),
                "rag_context": rag_hits,
                **tc,
            },
            strategy_prompt=FLOWCHART_STRATEGY_SYSTEM,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "drawio_xml"],
            schema=FlowchartDraft,
        )
    except Exception as exc:
        return (
            "流程图生成失败，请稍后重试。",
            AgentName.FLOWCHART.value,
            {**common_metadata, "error": str(exc), "_failed": True},
        )
    draft = FlowchartDraft.model_validate(raw)
    content = draft.drawio_xml
    metadata = {**common_metadata, "draft": draft.model_dump(mode="json")}
    return content, AgentName.FLOWCHART.value, metadata


def _generate_video_storyboard(
    profile, knowledge_point, resource_type, subject, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    is_animation = resource_type == ResourceType.ANIMATION

    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "resource_video_v1",
            "生成教学视频分镜脚本。\n"
            "返回 JSON：{title, total_seconds, scenes: [{frame, duration_seconds, visual_description, narration, image_prompt}], summary, key_points}",
            {
                "student_profile": _profile_summary(profile),
                "knowledge_point": knowledge_point,
                "subject": subject,
                "difficulty": str(tc["teaching_params"].get("difficulty", difficulty)),
                "resource_type": "animation" if is_animation else "video",
                "rag_context": rag_hits,
                **tc,
            },
            strategy_prompt=VISUAL_STRATEGY_SYSTEM,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "scenes"],
            schema=VideoDraft,
        )
    except Exception as exc:
        return (
            "视频分镜生成失败，请稍后重试。",
            AgentName.VIDEO.value,
            {**common_metadata, "error": str(exc), "_failed": True},
        )
    draft = VideoDraft.model_validate(raw)

    # Try to generate images for scenes
    scene_images = {}
    try:
        from app.services import image_gen_service
        for scene in draft.scenes[:3]:  # Limit to first 3 scenes to avoid timeout
            if scene.image_prompt:
                img_result = image_gen_service.generate_image(scene.image_prompt, style="educational")
                img_path = img_result.get("image_path", "")
                if img_path:
                    # Convert local path to API URL
                    from pathlib import Path as _Path
                    fname = _Path(img_path).name
                    scene_images[scene.frame] = f"/static/images/{fname}"
    except Exception:
        pass  # Image generation is optional, don't fail the whole resource

    # Try to render actual video via FFmpeg pipeline
    video_path = None
    video_url = None
    thumbnail_url = None
    try:
        from app.services.video_pipeline_service import generate_video
        video_result = generate_video(
            topic=knowledge_point,
            subject=subject,
            num_scenes=min(len(draft.scenes), 5),
            style="educational",
        )
        if video_result:
            video_path = video_result.get("video_path")
            video_url = video_result.get("video_url")
            thumbnail_url = video_result.get("thumbnail_url")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("FFmpeg video rendering failed: %s", exc)

    content = json.dumps(
        {
            "title": draft.title,
            "total_seconds": draft.total_seconds,
            "scenes": [s.model_dump() for s in draft.scenes],
            "scene_images": scene_images,
            "video_path": video_path,
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
            "summary": draft.summary,
            "key_points": draft.key_points,
            "is_animation": is_animation,
        },
        ensure_ascii=False,
    )
    metadata = {
        **common_metadata,
        "draft": draft.model_dump(mode="json"),
        "scene_images": scene_images,
        "video_path": video_path,
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
    }
    return content, AgentName.VIDEO.value, metadata


def _generate_code(
    profile, knowledge_point, subject, difficulty, rag_hits, common_metadata, base_agent
) -> tuple[str, str, dict]:
    tc = _get_teaching_context(profile, knowledge_point)
    prompt = _apply_base_agent_prompt(
        _build_prompt(
            "resource_code_v1",
            "生成可运行的代码示例和实操案例。\n"
            "返回 JSON：{title, language, code, run_instructions, explanation, checkpoints}",
            {
                "student_profile": _profile_summary(profile),
                "knowledge_point": knowledge_point,
                "subject": subject,
                "difficulty": str(tc["teaching_params"].get("difficulty", difficulty)),
                "rag_context": rag_hits,
                **tc,
            },
            strategy_prompt=CODE_STRATEGY_SYSTEM,
        ),
        base_agent,
    )

    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["title", "language", "code", "explanation"],
            schema=CodeCaseDraft,
        )
    except Exception as exc:
        return ("代码示例生成失败，请稍后重试。", AgentName.CODE.value, {**common_metadata, "error": str(exc), "_failed": True})
    draft = CodeCaseDraft.model_validate(raw)

    content = (
        f"# {draft.title}\n\n"
        f"```{draft.language}\n{draft.code}\n```\n\n"
        "## 运行说明\n"
        + "\n".join(f"- {item}" for item in draft.run_instructions)
        + "\n\n## 说明\n"
        + draft.explanation
    )
    metadata = {**common_metadata, "draft": draft.model_dump(mode="json")}
    return content, AgentName.CODE.value, metadata


# ── Tutor answer ───────────────────────────────────────────────────────────


def build_tutor_answer(
    profile: Optional[StudentProfile],
    question: str,
    knowledge_point: Optional[str],
    subject: str,
    references: List[dict],
    base_agent: Optional[BaseAgentProfile] = None,
    conversation_history: Optional[List[dict]] = None,
) -> TutorAnswerDraft:
    tc = _get_teaching_context(profile, knowledge_point or "")
    style = profile.learning_preference.learning_style if profile else "mixed"
    topic_dim = (profile.knowledge_profile.topic_dimensions.get(knowledge_point) if profile and knowledge_point else None)
    variables = {"learning_style": style, "topic_dimension": topic_dim.model_dump() if topic_dim else {}}
    strategy_params = _format_strategy_params(tc, variables)

    # System prompt: strategy + profile + RAG context + format instructions
    history_text = ""
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-6:]:
            role = "学生" if msg.get("role") == "user" else "AI导师"
            content = str(msg.get("content", ""))[:300]
            history_lines.append(f"{role}: {content}")
        history_text = "\n".join(history_lines)

    system_parts = [
        TEACHING_STRATEGY_SYSTEM,
        strategy_params,
        f"学生画像：{_profile_summary(profile)}",
    ]
    if history_text:
        system_parts.append(f"近期对话记录：\n{history_text}")
    if references:
        system_parts.append(f"参考知识库检索结果：\n{json.dumps(references, ensure_ascii=False)}")
    system_parts.append(
        "请结合以上信息回答学生问题。要求：\n"
        "1. 先分析问题，再给出详细解答\n"
        "2. 结合学生薄弱点针对性讲解\n"
        "3. 给出下一步学习建议\n"
        "4. 引用参考资料\n"
        "返回严格 JSON，包含 answer, next_step, references, diagram_prompt, markdown。"
    )
    system_prompt = "\n\n".join(system_parts)
    system_prompt = _apply_base_agent_prompt(system_prompt, base_agent)

    # User prompt: just the question context
    user_parts = []
    if knowledge_point:
        user_parts.append(f"知识点：{knowledge_point}")
    user_parts.append(f"学科：{subject}")
    user_parts.append(f"问题：{question}")
    user_prompt = "\n".join(user_parts)

    try:
        raw = model_gateway.generate_json_with_system(
            system_prompt,
            user_prompt,
            required_keys=["answer", "next_step", "references", "markdown"],
        )
        return TutorAnswerDraft.model_validate(raw)
    except Exception as exc:
        return TutorAnswerDraft(
            answer="抱歉，AI导师暂时无法回答，请稍后重试。",
            next_step="请稍后重试或换个问题",
            references=[],
            markdown="**暂时无法回答**，请稍后重试。",
        )
