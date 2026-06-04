from __future__ import annotations
"""Intent Parser — 从用户消息中提取关键词、真实需求和资源生成策略。

两层解析：
- Layer 1（规则）：正则提取关键词、资源类型偏好、难度信号
- Layer 2（LLM）：当规则置信度低时，用LLM提取深层意图

输出统一的 ParsedIntent，供下游 agent 和资源编排使用。
"""

from typing import Dict,  List,  Optional

import re
from dataclasses import dataclass, field

from app.core.enums import ResourceType


@dataclass
class ParsedIntent:
    """统一的意图解析结果。"""
    keywords: List[str] = field(default_factory=list)
    real_need: str = ""  # 用户真实需求描述
    resource_preferences: List[str] = field(default_factory=list)  # 偏好的资源类型
    difficulty_signal: Optional[str] = None  # "easy" / "medium" / "hard" / None
    subject: Optional[str] = None
    knowledge_point: Optional[str] = None
    confidence: float = 0.0
    method: str = "rule"  # "rule" / "llm"


# ── Layer 1: Rule-based extraction ──────────────────────────────────────────

_RESOURCE_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "document": ["文档", "讲解", "笔记", "资料", "说明", "教程", "讲义", "学习资料"],
    "quiz": ["题", "练习", "测验", "考试", "刷题", "做题", "出题", "quiz"],
    "mindmap": ["思维导图", "脑图", "知识图谱", "mindmap", "图谱", "结构图"],
    "code": ["代码", "编程", "实现", "代码示例", "code", "程序", "函数", "算法实现"],
    "video": ["视频", "动画", "演示", "讲解视频", "video"],
    "flowchart": ["流程图", "流程", "时序图", "状态机", "工作流", "算法流程", "flowchart", "flow", "diagram", "process"],
}

_DIFFICULTY_SIGNALS: Dict[str, List[str]] = {
    "easy": ["基础", "入门", "简单", "初级", "零基础", "刚开始", "初学", "easy", "basic"],
    "medium": ["进阶", "中等", "提高", "中级", "medium", "intermediate"],
    "hard": ["高级", "深入", "复杂", "难题", "挑战", "hard", "advanced", "精通"],
}

_NEED_PATTERNS: List[tuple[str, str]] = [
    (r"什么是(.+?)[，。？\?]", "理解概念"),
    (r"怎么理解(.+?)[，。？\?]", "理解原理"),
    (r"如何(实现|使用|应用)(.+?)[，。？\?]", "学会应用"),
    (r"为什么(.+?)[，。？\?]", "理解原理"),
    (r"(.+?)的区别", "对比理解"),
    (r"(.+?)的原理", "理解原理"),
    (r"帮我(生成|制作|创建)(.+)", "获取资源"),
    (r"给我(一份|一个|几道)(.+)", "获取资源"),
    (r"学[习一]下(.+)", "系统学习"),
    (r"补[一强]下(.+)", "补强薄弱点"),
    (r"复习(.+)", "间隔复习"),
    (r"总结(.+)", "知识梳理"),
]


def _extract_keywords(text: str) -> List[str]:
    """提取核心关键词。"""
    stop_words = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
        "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
        "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "怎么", "如何", "为什么",
        "请", "帮", "我", "想", "能", "可以", "吗", "吧", "呢", "啊", "哦", "嗯",
        "一下", "一点", "一些", "帮我", "给我", "来", "出", "做", "几道", "几份",
        "一份", "一个", "帮我生成", "帮我制作", "帮我写",
    }
    # Remove common prefixes
    cleaned = text
    for prefix in ["帮我生成", "帮我制作", "帮我写", "给我", "帮我", "我想", "请", "来一份", "出一份"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Split on delimiters and common suffixes
    segments = re.split(r"[，。？！、；：\s,\.?!;:\(\)的]", cleaned)
    keywords = []
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= 2 and seg not in stop_words:
            keywords.append(seg)
    return keywords[:10]


def _detect_resource_preferences(text: str) -> List[str]:
    """检测用户偏好的资源类型。"""
    text_lower = text.lower()
    prefs = []
    for rt, keywords in _RESOURCE_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                prefs.append(rt)
                break
    return prefs


def _detect_difficulty(text: str) -> Optional[str]:
    """检测难度信号。"""
    text_lower = text.lower()
    for level, keywords in _DIFFICULTY_SIGNALS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return level
    return None


def _detect_real_need(text: str) -> str:
    """检测用户真实需求。"""
    for pattern, need in _NEED_PATTERNS:
        if re.search(pattern, text):
            return need
    # Fallback: infer from intent keywords
    if any(kw in text for kw in ["学", "了解", "知道", "明白"]):
        return "系统学习"
    if any(kw in text for kw in ["做", "练", "写", "实现"]):
        return "学会应用"
    return "综合学习"


def parse_intent_rule(text: str) -> ParsedIntent:
    """Layer 1: 规则解析。"""
    keywords = _extract_keywords(text)
    resource_prefs = _detect_resource_preferences(text)
    difficulty = _detect_difficulty(text)
    real_need = _detect_real_need(text)

    # Infer subject and knowledge_point from keywords
    subject = None
    knowledge_point = None
    if keywords:
        # First keyword is likely the knowledge point
        knowledge_point = keywords[0]
        if len(keywords) > 1:
            subject = keywords[1]

    confidence = 0.6
    if keywords and resource_prefs:
        confidence = 0.8
    elif keywords:
        confidence = 0.7

    return ParsedIntent(
        keywords=keywords,
        real_need=real_need,
        resource_preferences=resource_prefs,
        difficulty_signal=difficulty,
        subject=subject,
        knowledge_point=knowledge_point,
        confidence=confidence,
        method="rule",
    )


# ── Layer 2: LLM-based extraction ───────────────────────────────────────────

_LLM_PARSE_PROMPT = """\
从以下用户消息中提取结构化意图信息。

用户消息：{message}

提取以下信息并返回严格JSON：
{{
  "keywords": ["核心关键词1", "关键词2"],
  "real_need": "用户的真实需求（一句话）",
  "resource_preferences": ["document", "quiz", "mindmap", "code", "video", "flowchart"],
  "difficulty_signal": "easy/medium/hard或null",
  "subject": "学科名称或null",
  "knowledge_point": "核心知识点或null",
  "confidence": 0.0-1.0
}}

规则：
1. keywords：提取2-5个核心关键词，去掉停用词
2. real_need：用户真正想要什么（不是字面意思，而是深层需求）
3. resource_preferences：根据消息内容推断用户想要的资源类型
4. difficulty_signal：根据用词推断难度需求
5. subject：学科名称
6. knowledge_point：最核心的知识点
"""


def parse_intent_llm(text: str) -> ParsedIntent:
    """Layer 2: LLM解析。"""
    from app.services import model_gateway

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt("intent_parse_v1", _LLM_PARSE_PROMPT, {"message": text})
    try:
        raw = model_gateway.generate_json(
            prompt,
            required_keys=["keywords", "real_need", "confidence"],
        )
        return ParsedIntent(
            keywords=raw.get("keywords", []),
            real_need=raw.get("real_need", ""),
            resource_preferences=raw.get("resource_preferences", []),
            difficulty_signal=raw.get("difficulty_signal"),
            subject=raw.get("subject"),
            knowledge_point=raw.get("knowledge_point"),
            confidence=float(raw.get("confidence", 0.7)),
            method="llm",
        )
    except Exception:
        return ParsedIntent(
            keywords=[text[:20]],
            real_need="综合学习",
            confidence=0.3,
            method="fallback",
        )


def parse_intent(text: str, force_llm: bool = False) -> ParsedIntent:
    """统一入口：解析用户意图。

    先用规则快速解析，置信度低时降级到LLM。
    """
    if force_llm:
        return parse_intent_llm(text)

    result = parse_intent_rule(text)
    if result.confidence < 0.5:
        llm_result = parse_intent_llm(text)
        if llm_result.confidence > result.confidence:
            return llm_result
    return result
