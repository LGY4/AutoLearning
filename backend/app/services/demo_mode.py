"""Demo mode — returns realistic mock LLM responses when API key is unavailable.

All mock data is self-contained and uses the APP_USER_SATISFY_LLM pattern:
every response looks authentic enough to drive the full learning pipeline.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Iterable


def is_demo_mode() -> bool:
    """Check if we're in demo mode (no API key configured or placeholder key)."""
    from app.core.config import get_settings
    settings = get_settings()
    key = (settings.llm_api_key or "").strip()
    if not key:
        return True
    # Placeholder / obviously fake keys
    placeholders = {"sk-your-key-here", "your-key-here", "sk-xxx", "changeme", ""}
    if key.lower() in placeholders:
        return True
    # Keys shorter than 20 chars are unlikely to be real
    if len(key) < 20:
        return True
    return False


# ── Intent detection ──────────────────────────────────────────────────────

_MOCK_INTENTS: dict[str, dict] = {}

def _mock_intent(message: str) -> dict:
    """Mock intent detection based on keyword matching."""
    lower = message.lower()

    if any(k in lower for k in ["生成", "资源", "文档", "题目", "试题", "代码", "导图", "视频", "阅读", "流程图"]):
        return {
            "intent": "resource_generation",
            "confidence": 0.92,
            "method": "keyword_match",
            "resource_types": ["document", "mindmap", "quiz"],
            "knowledge_point": message[:40],
        }
    if any(k in lower for k in ["路径", "计划", "路线", "安排", "规划"]):
        return {
            "intent": "learning_path",
            "confidence": 0.88,
            "method": "keyword_match",
            "knowledge_point": message[:40],
        }
    if any(k in lower for k in ["评测", "评估", "检测", "水平", "掌握"]):
        return {
            "intent": "assessment",
            "confidence": 0.85,
            "method": "keyword_match",
        }
    if any(k in lower for k in ["练习", "做题", "习题", "考试"]):
        return {
            "intent": "exercise",
            "confidence": 0.87,
            "method": "keyword_match",
        }
    if any(k in lower for k in ["你好", "嗨", "帮助", "help", "你是谁"]):
        return {
            "intent": "general_chat",
            "confidence": 0.95,
            "method": "keyword_match",
        }

    # Default: tutoring
    return {
        "intent": "tutoring",
        "confidence": 0.82,
        "method": "keyword_match",
        "knowledge_point": message[:40],
    }


# ── Mock structured JSON generator ────────────────────────────────────────

def _extract_kp_from_prompt(prompt: str) -> str:
    """Try to extract a knowledge point from the prompt text."""
    # Look for quoted text or common patterns
    m = re.search(r"['「「](.+?)['」」]", prompt)
    if m:
        return m.group(1)
    m = re.search(r"知识[点点]?[：:]\s*(.+?)(?:\n|$)", prompt)
    if m:
        return m.group(1).strip()
    # Take first meaningful sentence
    lines = [l.strip() for l in prompt.split("\n") if l.strip() and len(l.strip()) > 5]
    return lines[0][:30] if lines else "未知知识点"


def _mock_generate_text(prompt: str) -> str:
    """Generate mock text response."""
    kp = _extract_kp_from_prompt(prompt)

    if any(k in prompt.lower() for k in ["评估", "assessment", "assess"]):
        return f"""基于对学生学习数据的分析，{kp}的掌握程度如下：

整体评估：
- 知识掌握度：75%
- 应用能力：中等（偏理论理解，需加强实操）
- 记忆保持率：良好
- 薄弱环节：复杂场景下的应用、与其他知识点的关联

建议下一步：
1. 完成{3}个进阶练习题
2. 阅读{2}篇拓展材料
3. 动手完成一个小型项目

数据来源：基于4次学习记录的累计分析。"""

    if any(k in prompt.lower() for k in ["图谱", "graph", "知识结构"]):
        return json.dumps({
            "graph_name": f"{kp}知识图谱",
            "nodes": [
                {"id": f"{kp}_基础", "name": f"{kp}基础概念", "level": 0, "description": "核心概念和定义"},
                {"id": f"{kp}_原理", "name": f"{kp}核心原理", "level": 1, "description": "底层机制和工作原理"},
                {"id": f"{kp}_应用", "name": f"{kp}实际应用", "level": 2, "description": "工程实践和应用场景"},
                {"id": f"{kp}_进阶", "name": f"{kp}进阶话题", "level": 3, "description": "高级特性和优化"},
            ],
            "edges": [
                {"source": f"{kp}_基础", "target": f"{kp}_原理", "relation": "prerequisite"},
                {"source": f"{kp}_原理", "target": f"{kp}_应用", "relation": "prerequisite"},
                {"source": f"{kp}_应用", "target": f"{kp}_进阶", "relation": "prerequisite"},
            ],
            "metadata": {"total_nodes": 4, "depth": 3, "domain": kp},
        }, ensure_ascii=False)

    # Default tutoring response
    return f"""关于「{kp}」的讲解：

## 1. 核心概念

{kp}是计算机科学中的重要知识点。让我们从基础开始理解。

### 1.1 定义

{kp}指的是在特定场景下解决问题的系统化方法。它涉及到数据结构的选择、算法的设计以及时间和空间复杂度的权衡。

### 1.2 关键原理

- **原理一**：分治思想——将大问题分解为小问题，逐个击破
- **原理二**：空间换时间——通过缓存或预处理来加速查询
- **原理三**：抽象与封装——将复杂逻辑隐藏在简洁的接口后面

## 2. 实践应用

在实际开发中，{kp}常用于以下场景：
1. 数据处理和转换
2. 系统性能优化
3. 算法竞赛和面试

## 3. 常见误区

- 过度优化：在不需要高性能的场景下使用复杂算法
- 忽略边界条件：没有充分考虑空值、溢出等特殊情况

## 4. 总结

掌握{kp}需要理论与实践相结合。建议先理解原理，再动手实现，最后在项目中应用。

---

*（演示模式数据 — 仅供参考，实际使用时请配置 LLM API Key）*
"""


def _mock_generate_json(prompt: str, required_keys: Optional[Iterable[str]] = None) -> dict:
    """Generate realistic mock JSON response based on prompt context and required keys."""
    keys = list(required_keys or [])
    kp = _extract_kp_from_prompt(prompt)

    # ── Student Profile ──────────────────────────────────────────────────
    if "profile" in prompt.lower() and any(k in keys for k in ["overall_level", "weak_topics", "known_topics"]):
        return {
            "overall_level": "intermediate",
            "known_topics": ["变量与类型", "控制流", "函数定义"],
            "weak_topics": ["递归算法", "指针操作", "并发编程"],
            "mastery_level": {"数据结构": 0.75, "算法设计": 0.60, "系统设计": 0.40},
            "topic_dimensions": {
                "数据结构": {"mastery": "high", "application": "mid", "memory": "high", "understanding": "mid"},
                "算法设计": {"mastery": "mid", "application": "low", "memory": "mid", "understanding": "mid"},
                "系统设计": {"mastery": "low", "application": "low", "memory": "mid", "understanding": "low"},
            },
            "learning_style": "mixed",
            "cognitive_style": "visual",
            "_demo_mode": True,
        }

    # ── Learning Path ────────────────────────────────────────────────────
    if "path" in prompt.lower() or "path_id" in keys or "nodes" in keys:
        return {
            "path_id": "demo-path-001",
            "title": f"{kp}学习路径",
            "goal": f"系统掌握{kp}的核心概念和实践应用",
            "nodes": [
                {
                    "node_id": "node-1",
                    "knowledge_point": f"{kp}基础概念",
                    "order": 1,
                    "status": "available",
                    "estimated_minutes": 30,
                    "reason": "建立基础知识框架",
                    "recommended_resource_types": ["document", "reading"],
                },
                {
                    "node_id": "node-2",
                    "knowledge_point": f"{kp}核心原理",
                    "order": 2,
                    "status": "locked",
                    "estimated_minutes": 45,
                    "reason": "深入理解底层机制",
                    "recommended_resource_types": ["document", "mindmap", "video"],
                },
                {
                    "node_id": "node-3",
                    "knowledge_point": f"{kp}实践应用",
                    "order": 3,
                    "status": "locked",
                    "estimated_minutes": 60,
                    "reason": "通过实战巩固知识",
                    "recommended_resource_types": ["code_case", "quiz"],
                },
                {
                    "node_id": "node-4",
                    "knowledge_point": f"{kp}进阶优化",
                    "order": 4,
                    "status": "locked",
                    "estimated_minutes": 45,
                    "reason": "掌握高级技巧和最佳实践",
                    "recommended_resource_types": ["document", "code_case", "quiz"],
                },
            ],
            "status": "active",
            "_demo_mode": True,
        }

    # ── Learning Resources ───────────────────────────────────────────────
    if any(k in keys for k in ["title", "resource_type", "content"]):
        resource_type = "document"
        for t in ["document", "mindmap", "quiz", "code_case", "reading", "video", "flowchart"]:
            if t in prompt.lower():
                resource_type = t
                break

        return _mock_resource(resource_type, kp)

    # ── Quiz/Assessment ──────────────────────────────────────────────────
    if "question" in keys or "score" in keys or "quiz" in prompt.lower():
        return {
            "score": 82,
            "is_correct": True,
            "feedback": f"回答正确！你对{kp}的理解很扎实。注意在实际应用中多练习以加深理解。",
            "key_points_hit": [f"{kp}的定义准确", "核心原理解释清楚"],
            "key_points_missed": ["可以补充更多实际案例"],
            "updated_dimension": True,
            "_demo_mode": True,
        }

    # ── Intent detection ─────────────────────────────────────────────────
    if "intent" in keys:
        result = _mock_intent(prompt)
        result["_demo_mode"] = True
        return result

    # ── Graph building ───────────────────────────────────────────────────
    if "graph" in prompt.lower() or "node" in prompt.lower():
        return {
            "graph_id": f"demo-graph-{kp[:10]}",
            "course_name": kp,
            "version": 1,
            "node_count": 8,
            "edge_count": 10,
            "confidence": 0.88,
            "review_status": "draft",
            "nodes": [
                {"id": "1", "name": f"{kp}概述", "level": 0, "depends_on": [], "description": "入门概念"},
                {"id": "2", "name": f"{kp}原理", "level": 1, "depends_on": ["1"], "description": "核心原理"},
                {"id": "3", "name": f"{kp}应用", "level": 2, "depends_on": ["2"], "description": "实际应用"},
                {"id": "4", "name": f"{kp}进阶", "level": 3, "depends_on": ["3"], "description": "高级话题"},
            ],
            "edges": [
                {"source": "1", "target": "2", "type": "prerequisite"},
                {"source": "2", "target": "3", "type": "prerequisite"},
                {"source": "3", "target": "4", "type": "prerequisite"},
            ],
            "_demo_mode": True,
        }

    # ── Generic fallback ─────────────────────────────────────────────────
    return {
        "content": _mock_generate_text(prompt),
        "reply": _mock_generate_text(prompt),
        "_demo_mode": True,
        **(dict.fromkeys(keys, "")),
    }


def _mock_resource(resource_type: str, kp: str) -> dict:
    """Generate mock resource content for each type."""

    base = {
        "resource_id": f"demo-res-{resource_type}-001",
        "title": f"{kp} - {'讲解文档' if resource_type == 'document' else resource_type}",
        "resource_type": resource_type,
        "knowledge_point": kp,
        "status": "generated",
        "_demo_mode": True,
    }

    if resource_type == "document":
        base["content"] = f"""# {kp} 学习指南

## 概述

{kp}是计算机科学中的基础知识点，掌握它对于理解和解决实际问题至关重要。

## 1. 核心概念

### 1.1 基本定义

{kp}指的是在特定场景下，通过系统化的方法来分析和解决问题的过程。

### 1.2 关键特征

- **系统性**：不是孤立的知识点，而是体系化的知识结构
- **实用性**：直接应用于实际工程场景
- **可扩展性**：基础概念可以延伸出更复杂的应用

## 2. 详细讲解

在深入学习{kp}之前，需要先了解以下前置知识：
1. 基础编程概念
2. 基本的数据结构（数组、链表、栈、队列）
3. 时间复杂度分析

### 2.1 核心原理

{kp}的核心思想是：**将复杂问题分解为可管理的小问题，逐个击破后组合成完整方案。**

具体来说：
- **分治**（Divide and Conquer）：将大问题拆分为子问题
- **递归**（Recursion）：通过自调用解决嵌套问题
- **动态规划**（Dynamic Programming）：避免重复计算

### 2.2 实现步骤

1. 分析问题，明确输入和输出
2. 设计数据结构和算法
3. 编写代码实现
4. 测试和优化

## 3. 代码示例

```python
def demo_example(data):
    \"\"\"
    {kp}的简单示例实现
    \"\"\"
    # Step 1: 数据预处理
    processed = preprocess(data)

    # Step 2: 核心逻辑
    result = core_algorithm(processed)

    # Step 3: 结果验证
    assert validate(result), "结果验证失败"

    return result
```

## 4. 常见问题与解答

**Q: {kp}在实际开发中会用到吗？**
A: 是的，{kp}是面试和实际工作中的高频考点。

**Q: 学习{kp}需要多长时间？**
A: 基础概念约1-2小时可掌握，深入理解需要持续练习。

## 5. 延伸阅读

- 《算法导论》相关章节
- LeetCode 相关题目
- 官方文档

---

*（演示模式生成 — 配置 LLM API Key 后可使用真实 AI 生成内容）*
"""
    elif resource_type == "mindmap":
        base["content"] = f"""# {kp} 思维导图

## {kp}
- 基础概念
  - 定义
  - 特征
  - 前置知识
- 核心原理
  - 分治思想
  - 递归方法
  - 动态规划
- 实践应用
  - 数据处理
  - 系统优化
  - 算法竞赛
- 进阶话题
  - 性能优化
  - 分布式扩展
  - 前沿研究
"""
    elif resource_type == "quiz":
        base["content"] = json.dumps({
            "title": f"{kp} 练习题",
            "overview": f"共3道题目，涵盖{kp}的核心概念和应用",
            "questions": [
                {
                    "type": "choice",
                    "stem": f"以下关于{kp}的描述，正确的是？",
                    "options": [
                        f"A. {kp}仅适用于理论学习",
                        f"B. {kp}可用于解决实际问题",
                        f"C. {kp}与其他知识无关",
                        f"D. {kp}只能在特定语言中使用"
                    ],
                    "answer": f"B. {kp}可用于解决实际问题",
                    "explanation": f"{kp}是实用导向的知识点，可直接应用于工程实践。",
                    "difficulty": "beginner",
                },
                {
                    "type": "choice",
                    "stem": f"{kp}中，分治思想的核心是什么？",
                    "options": [
                        "A. 将所有数据一次性处理",
                        "B. 将大问题拆分为子问题，逐个解决后合并",
                        "C. 使用暴力枚举所有可能",
                        "D. 完全依赖外部库实现"
                    ],
                    "answer": "B. 将大问题拆分为子问题，逐个解决后合并",
                    "explanation": "分治思想是{kp}中的核心方法论，通过分解→解决→合并的方式处理复杂问题。",
                    "difficulty": "intermediate",
                },
                {
                    "type": "short_answer",
                    "stem": f"请简要描述{kp}在你实际工作或学习中的一个应用场景。",
                    "options": [],
                    "answer": "答案不唯一，合理即可。需要体现{kp}在实际场景中的具体应用和解决的问题。",
                    "explanation": "考察学生对{kp}的实际理解和应用能力。",
                    "difficulty": "intermediate",
                },
            ],
            "scoring_rules": ["选择题每题30分", "简答题40分，根据完整性和准确性评分"],
        }, ensure_ascii=False)
    elif resource_type == "code_case":
        base["content"] = f"""```python
# {kp} 代码实操案例

def solve_problem(input_data):
    \"\"\"
    使用{kp}相关知识解决实际问题

    Args:
        input_data: 输入数据

    Returns:
        处理后的结果
    \"\"\"
    # 第一步：理解问题
    print(f"处理数据: {{input_data}}")

    # 第二步：应用核心算法
    result = process_data(input_data)

    # 第三步：验证结果
    if validate(result):
        return result
    else:
        raise ValueError("结果验证失败")

def process_data(data):
    \"\"\"核心处理逻辑\"\"\"
    # TODO: 在此实现{kp}的核心算法
    return data

def validate(result):
    \"\"\"结果验证\"\"\"
    return result is not None

# 测试用例
if __name__ == "__main__":
    test_data = [1, 2, 3, 4, 5]
    result = solve_problem(test_data)
    print(f"结果: {{result}}")
```
"""
    elif resource_type == "reading":
        base["content"] = f"""# {kp} 拓展阅读

## 推荐阅读材料

### 基础入门
1. 《{kp}入门指南》— 适合零基础学习
2. 《{kp}核心概念》— 系统梳理知识体系

### 进阶提升
3. 《{kp}实战》— 结合实际案例讲解
4. 《{kp}优化技巧》— 性能调优和最佳实践

### 论文推荐
5. "A Survey of {kp} Techniques" — 综述论文
6. "Practical Applications of {kp}" — 应用论文

## 在线资源

- 官方文档和 API 参考
- Stack Overflow 上的高频问答
- GitHub 上的开源项目和示例代码

---

*阅读建议：按照基础→进阶→论文的顺序学习，每篇材料预留 30-60 分钟。*
"""
    elif resource_type == "flowchart":
        base["content"] = f"""```mermaid
flowchart TD
    A[开始学习{kp}] --> B[理解基本概念]
    B --> C[掌握核心原理]
    C --> D[动手实践]
    D --> E[做练习题]
    E --> F{{掌握程度检测}}
    F -->|通过| G[进入下一阶段]
    F -->|未通过| C
    G --> H[学习进阶话题]
    H --> I[完成学习]
```
"""
    elif resource_type == "video":
        base["content"] = json.dumps({
            "title": f"{kp} - 教学视频",
            "scenes": [
                {"frame": 1, "duration_seconds": 15, "visual_description": f"标题：{kp} 入门", "narration": f"欢迎来到{kp}的学习。今天我们将一起探索这个重要的知识点。"},
                {"frame": 2, "duration_seconds": 20, "visual_description": "核心概念图解", "narration": f"{kp}的核心思想是将复杂问题分解为简单问题。"},
                {"frame": 3, "duration_seconds": 20, "visual_description": "代码示例展示", "narration": "让我们看一个实际的代码示例来加深理解。"},
                {"frame": 4, "duration_seconds": 15, "visual_description": "总结要点", "narration": f"总结一下，{kp}需要理论结合实践，多加练习才能掌握。"},
            ],
            "key_points": [f"理解{kp}的核心思想", "掌握基本实现方法", "能够在项目中应用"],
            "is_animation": False,
        }, ensure_ascii=False)

    return base


def demo_generate_text(prompt: str, fallback: Optional[str] = None) -> str:
    """Demo mode text generation with realistic content."""
    time.sleep(0.1)  # minimal delay for realism
    return _mock_generate_text(prompt)


def demo_generate_json(
    prompt: str,
    fallback: Optional[dict] = None,
    required_keys: Optional[Iterable[str]] = None,
) -> dict:
    """Demo mode JSON generation with realistic structured data."""
    time.sleep(0.1)
    result = _mock_generate_json(prompt, required_keys)
    result["_demo_mode"] = True
    return result


def demo_generate_stream(prompt: str):
    """Demo mode streaming — yield text chunks to simulate streaming."""
    text = _mock_generate_text(prompt)
    # Simulate streaming by yielding text word by word
    words = text.split()
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(0.02)


def demo_generate_stream_with_system(system_prompt: str, user_prompt: str):
    """Demo mode streaming with system prompt."""
    yield from demo_generate_stream(user_prompt)
