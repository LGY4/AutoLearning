"""Embedded prompt templates — used as fallback when prompt_templates.json fails to load.

These are the authoritative prompt definitions. The JSON file serves as a hot-reload overlay.
"""

PROFILE_EXTRACT_V1 = (
    "从多轮对话中抽取并更新学生画像。\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "basic_info": {"major": "专业", "grade": "年级", "school": "学校或null"},\n'
    '  "knowledge_profile": {\n'
    '    "overall_level": "beginner/intermediate/advanced",\n'
    '    "known_topics": ["已掌握知识点"],\n'
    '    "weak_topics": ["薄弱知识点"],\n'
    '    "mastery_level": {"知识点": 0.0-1.0},\n'
    '    "topic_dimensions": {\n'
    '      "知识点名": {"mastery": "low/mid/high", "application": "low/mid/high", "memory": "low/mid/high", "understanding": "low/mid/high"}\n'
    "    }\n"
    "  },\n"
    '  "learning_goal": {"current_goal": "当前学习目标", "target_course": "目标课程", "target_level": "project_practice/interview_prep/exam_prep"},\n'
    '  "learning_preference": {"learning_style": "visual/reading/hands-on/mixed", "resource_preference": {"类型": 0.0-1.0}, "difficulty_preference": "step_by_step/challenge"},\n'
    '  "learning_behavior": {"average_study_minutes": 数字, "active_period": "morning/afternoon/evening", "completion_rate": 0.0-1.0, "recent_scores": [], "last_knowledge_point": "最近学习的知识点或null"},\n'
    '  "cognitive_profile": {"cognitive_style": "visual/verbal/mixed", "abstract_understanding": "low/medium/high", "hands_on_ability": "low/medium/high", "reading_patience": "low/medium/high"},\n'
    '  "completeness_score": 0.0-1.0之间的值,\n'
    '  "confidence_score": 0.0-1.0之间的值,\n'
    '  "update_reason": "更新原因"\n'
    "}\n\n"
    "四维度评估规则（对每个知识点）：\n"
    "- mastery：知道概念定义和基本用法 → mid；能独立使用 → high\n"
    "- application：能在实际问题中使用 → mid；能举一反三 → high\n"
    "- memory：间隔复习仍记得 → mid；长期不忘 → high\n"
    "- understanding：能解释原理 → mid；能迁移应用 → high\n\n"
    "学生原型参考（如有）：\n"
    "{archetype_hint}\n\n"
    "注意：completeness_score和confidence_score必须是0到1之间的小数，不要用百分比。"
)

PATH_PLANNING_V1 = (
    "根据学生画像、学习目标和薄弱点规划个性化学习路径。\n\n"
    "画像信息：\n"
    "- 整体水平：{overall_level}\n"
    "- 学习风格：{learning_style}\n"
    "- 薄弱知识点：{weak_topics}\n"
    "- 已掌握知识点：{known_topics}\n"
    "- 教学策略：{teaching_note}\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "学习路径标题",\n'
    '  "path_type": "beginner/intermediate/advanced",\n'
    '  "strategy": {"approach": "策略描述", "estimated_total_minutes": 总时长数字},\n'
    '  "nodes": [\n'
    "    {\n"
    '      "knowledge_point": "知识点名称",\n'
    '      "status": "new/review/skip",\n'
    '      "estimated_minutes": 预计分钟数,\n'
    '      "recommended_resource_types": ["document", "quiz", "mindmap", "code_case", "video"],\n'
    '      "prerequisites": ["前置知识点"],\n'
    '      "reason": "安排原因"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "要求：\n"
    "1. 薄弱知识点优先安排（weak_topics）\n"
    "2. 已掌握知识点（mastery=high）标记为review或skip\n"
    "3. 检查前置依赖关系\n"
    "4. 每个节点推荐2-3种资源类型\n"
    "5. 根据学习风格调整资源类型推荐"
)

RESOURCE_DOCUMENT_V1 = (
    "面向学生画像生成结构化文档资源。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 学习风格：{learning_style}\n"
    "- 该知识点四维度：{topic_dimension}\n"
    "- 教学策略：{teaching_note}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "知识框架（必须包含以下部分）：\n\n"
    "## 1. 概念定义（200字以内）\n"
    "- 一句话定义\n"
    "- 核心特征（3-5个要点）\n"
    "- 与相关概念的区别\n\n"
    "## 2. 原理讲解（500-800字）\n"
    "- 底层原理\n"
    "- 时间/空间复杂度分析\n"
    "- 关键公式或定理\n\n"
    "## 3. 代码示例\n"
    "- 包含完整注释\n"
    "- 包含测试用例\n\n"
    "## 4. 实际案例（2-3个）\n"
    "- 应用场景描述\n"
    "- 解决的问题\n\n"
    "## 5. 常见误区（3-5个）\n"
    "- 错误理解\n"
    "- 正确的理解方式\n\n"
    "## 6. 总结与下一步\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "文档标题",\n'
    '  "markdown": "完整的Markdown文档内容",\n'
    '  "summary": "一句话摘要",\n'
    '  "outline": ["章节1", "章节2"],\n'
    '  "examples": ["示例1"],\n'
    '  "common_mistakes": ["常见误区1"],\n'
    '  "next_steps": ["下一步建议1"]\n'
    "}"
)

RESOURCE_READING_V1 = (
    "生成深度阅读材料，侧重叙述、案例分析和思考。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 学习风格：{learning_style}\n"
    "- 该知识点四维度：{topic_dimension}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "与 document 的区别：\n"
    "- document 是结构化知识点文档（800-1500字），侧重概念定义和代码\n"
    "- reading 是深度阅读材料（2000-4000字），侧重叙述、案例分析和思考\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "阅读材料标题",\n'
    '  "markdown": "完整的Markdown阅读材料（2000-4000字）",\n'
    '  "summary": "一句话摘要",\n'
    '  "key_concepts": ["核心概念1", "核心概念2"],\n'
    '  "discussion_questions": ["讨论题1", "讨论题2", "讨论题3"],\n'
    '  "references": ["参考来源1"]\n'
    "}\n\n"
    "内容结构：\n"
    "1. 引入：从实际问题或历史背景切入\n"
    "2. 核心叙述：用故事化的方式讲解概念\n"
    "3. 案例分析：1-2个深入的实际案例\n"
    "4. 延伸思考：与其他领域的联系\n"
    "5. 讨论题：开放性问题"
)

RESOURCE_QUIZ_V1 = (
    "根据知识点和学生画像生成练习题。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 该知识点四维度：{topic_dimension}\n"
    "- 出题策略：{quiz_strategy}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "出题要求：\n"
    "- 题目数量：{total_questions}题\n"
    "- 难度分布：{difficulty_distribution}\n"
    "- 题型分布：{type_distribution}\n"
    "- 重点评估维度：{dimension_focus}\n\n"
    "四维度出题对应：\n"
    "- 测mastery：选择题、填空题（概念是否知道）\n"
    "- 测application：编程题、案例分析题（能否实际使用）\n"
    "- 测understanding：简答题（要求解释原理）\n"
    "- 测memory：间隔出现旧知识点的题目\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "题库标题",\n'
    '  "overview": "题库概述",\n'
    '  "questions": [\n'
    "    {\n"
    '      "type": "choice/fill_blank/code/case_analysis/short_answer",\n'
    '      "difficulty": "easy/medium/hard",\n'
    '      "dimension_test": "mastery/application/memory/understanding",\n'
    '      "stem": "题目内容",\n'
    '      "options": ["选项A", "选项B", "选项C", "选项D"],\n'
    '      "answer": "正确答案",\n'
    '      "explanation": "解析"\n'
    "    }\n"
    "  ],\n"
    '  "scoring_rules": "评分规则"\n'
    "}"
)

RESOURCE_MINDMAP_V1 = (
    "生成 Markmap 格式的思维导图。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 学习风格：{learning_style}\n"
    "- 该知识点四维度：{topic_dimension}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "Markmap 格式规则：\n"
    "- 一级标题用 # （只有一个，中心节点）\n"
    "- 二级标题用 ## （3-6个主要分支）\n"
    "- 三级标题用 ### （子节点）\n"
    "- 四级标题用 #### （细节，可选）\n"
    "- 每层 3-6 个子节点，总深度 3-4 层\n"
    "- 节点文字简洁（10-20字）\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "思维导图标题",\n'
    '  "mindmap_markdown": "# 中心主题\\n## 分支1\\n### 子节点1\\n### 子节点2\\n## 分支2\\n### 子节点3",\n'
    '  "summary": "一句话摘要",\n'
    '  "key_branches": ["分支1", "分支2", "分支3"]\n'
    "}\n\n"
    "重要：mindmap_markdown 必须使用 Markdown 标题语法（# ## ###），不要用列表语法或 JSON 结构。"
)

RESOURCE_VIDEO_V1 = (
    "生成教学视频分镜脚本。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 学习风格：{learning_style}\n"
    "- 教学策略：{teaching_note}\n"
    "- 资源类型：{resource_type}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "分镜规则：\n"
    "- 总共 5-8 个镜头\n"
    "- 第1个镜头：引入/问题提出（15-30秒）\n"
    "- 中间镜头：核心概念讲解（每个30-60秒）\n"
    "- 最后1个镜头：总结/回顾（15-30秒）\n"
    "- 每个镜头必须有具体的画面描述和讲解旁白\n"
    "- image_prompt 用英文，描述具体的教学画面\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "视频标题",\n'
    '  "total_seconds": 180,\n'
    '  "scenes": [\n'
    "    {\n"
    '      "frame": 1,\n'
    '      "duration_seconds": 30,\n'
    '      "visual_description": "画面描述",\n'
    '      "narration": "讲解旁白",\n'
    '      "image_prompt": "English prompt for AI image generation"\n'
    "    }\n"
    "  ],\n"
    '  "summary": "一句话摘要",\n'
    '  "key_points": ["核心要点1"]\n'
    "}\n\n"
    "重要：image_prompt 必须用英文，描述具体的教学画面。"
)

RESOURCE_CODE_V1 = (
    "生成可运行代码案例。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 该知识点四维度：{topic_dimension}\n"
    "- 教学策略：{teaching_note}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "代码规则：\n"
    "1. 代码必须完整可运行，不能有省略号或伪代码\n"
    "2. 包含详细注释（每3-5行代码一个注释）\n"
    "3. 包含测试用例或示例调用\n"
    "4. 运行说明必须具体（包含命令行指令）\n"
    '5. 检查点是"修改代码后观察输出"类型的思考题\n\n'
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "代码标题",\n'
    '  "language": "python/java/cpp/javascript",\n'
    '  "code": "完整可运行的代码",\n'
    '  "run_instructions": ["运行步骤1", "运行步骤2"],\n'
    '  "explanation": "代码说明",\n'
    '  "checkpoints": [{"question": "检查问题", "expected_answer": "预期答案"}]\n'
    "}\n\n"
    "代码必须完整可运行，包含详细注释。"
)

QUALITY_CHECK_V1 = (
    "检查资源质量。\n\n"
    "检查维度：\n"
    "1. 内容准确性：知识点是否正确\n"
    "2. 完整性：是否覆盖知识框架的所有部分\n"
    "3. 难度适配：是否与学生水平匹配\n"
    "4. 画像适配：是否符合学习风格和教学策略\n"
    "5. 可读性：排版、代码格式、图表清晰度\n"
    "6. 类型一致性：资源类型与实际内容是否匹配\n"
    "   - video 类型必须包含分镜脚本（scenes 数组）\n"
    "   - mindmap 类型必须包含 Markdown 标题层级结构（# ## ###）\n"
    "   - code_case 类型必须包含完整可运行代码\n"
    "   - document 类型必须包含概念定义和代码示例\n"
    "   - quiz 类型必须包含题目和答案\n"
    "   - 如果资源类型与内容不符，quality_score 扣 0.2\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "quality_score": 0.0-1.0,\n'
    '  "feedback": "总体评价",\n'
    '  "strengths": ["优点1"],\n'
    '  "weaknesses": ["不足1"],\n'
    '  "suggestions": ["改进建议1"],\n'
    '  "difficulty_match": true/false,\n'
    '  "profile_match": true/false,\n'
    '  "type_consistency": true/false\n'
    "}"
)

TUTOR_ANSWER_V1 = (
    "结合学生画像和RAG检索结果回答问题。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 该知识点四维度：{topic_dimension}\n"
    "- 学习风格：{learning_style}\n"
    "- 教学策略：{teaching_note}\n\n"
    "参考知识库检索结果：\n"
    "{references}\n\n"
    "画像适配：\n"
    "- beginner：用简单语言，多举例，避免专业术语\n"
    "- intermediate：适当深度，给出原理和应用\n"
    "- advanced：简洁精准，给进阶内容\n"
    "- visual：多用类比、图解描述\n"
    "- hands-on：多给代码示例\n"
    "- understanding=low：多解释\"为什么\"，给出原理图解\n"
    "- memory=low：用类比帮助记忆，给出总结框\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "answer": "简短回答",\n'
    '  "markdown": "详细的Markdown格式解答",\n'
    '  "next_step": "下一步学习建议",\n'
    '  "references": [{"title": "参考来源", "source": "来源"}],\n'
    '  "diagram_prompt": "图解提示词或null",\n'
    '  "key_points": ["核心要点1", "核心要点2"]\n'
    "}\n\n"
    "回答要结合学生薄弱点针对性讲解。"
)

RESOURCE_FLOWCHART_V1 = (
    "面向学生画像生成 draw.io XML 格式的教学流程图。\n\n"
    "学生画像：\n"
    "- 整体水平：{overall_level}\n"
    "- 学习风格：{learning_style}\n"
    "- 该知识点四维度：{topic_dimension}\n"
    "- 教学策略：{teaching_note}\n\n"
    "参考知识库内容：\n"
    "{rag_context}\n\n"
    "生成要求：\n"
    "1. 流程图展示 {knowledge_point} 的核心流程或算法步骤\n"
    "2. 使用 draw.io mxCell XML 格式\n"
    "3. 只输出 mxCell 元素，不要输出 mxfile/mxGraphModel/root 标签\n"
    '4. 节点 id 从 2 开始，所有元素 parent="1"\n'
    "5. 坐标范围：x:0-800, y:0-600\n"
    "6. 节点 5-15 个，文字简洁（10-15字）\n\n"
    "常用样式：\n"
    "- 圆角矩形（步骤）：rounded=1;whiteSpace=wrap;html=1;\n"
    "- 菱形（判断）：rhombus;whiteSpace=wrap;html=1;\n"
    "- 圆形（开始/结束）：ellipse;whiteSpace=wrap;html=1;\n"
    "- 带颜色：fillColor=#dae8fc;strokeColor=#6c8ebf;\n"
    "- 连线：endArrow=classic;html=1;\n\n"
    "必须返回以下JSON格式：\n"
    "{\n"
    '  "title": "流程图标题",\n'
    '  "drawio_xml": "<mxCell .../>的XML字符串",\n'
    '  "summary": "一句话摘要",\n'
    '  "node_count": 节点数量\n'
    "}"
)

GENERAL_CHAT_V1 = (
    "你是一个友好的学习助手，同时也是一个学习引导者。\n"
    "请简短回复以下消息（不超过100字）。\n\n"
    "规则：\n"
    "1. 如果消息与学习相关，简要回答后引导用户使用对应功能（对话学习、练习、资源生成等）\n"
    "2. 如果消息与学习无关，友好回复后自然地引导回学习\n"
    "3. 保持亲切自然的语气\n\n"
    "用户消息：\n"
    "{message}"
)

VISION_ANALYZE_V1 = (
    "请分析这张图片中的内容，提取与学习相关的知识点、概念、公式或代码。\n"
    "用中文回答，控制在300字以内。\n\n"
    "如果图片与学习无关，请说明图片内容并建议用户上传学习相关的图片。"
)

POST_TEST_V1 = (
    "你是一个教育诊断专家。学生刚刚学习了「{knowledge_point}」，请生成 {num_questions} 道题检验学习效果。\n\n"
    "学科：{subject}\n"
    "学生当前水平：{overall_level}\n"
    "该知识点四维度：{topic_dimension}\n\n"
    "要求：\n"
    "1. 题目紧扣刚学的知识点\n"
    "2. 难度适中（不要过于简单也不要超纲）\n"
    "3. 覆盖不同维度（概念理解 + 应用）\n"
    "4. 每题4选项，仅1个正确答案\n\n"
    "返回严格JSON：\n"
    '{{\n'
    '  "questions": [\n'
    "    {{\n"
    '      "id": 1,\n'
    '      "topic": "{knowledge_point}",\n'
    '      "difficulty": 2,\n'
    '      "dimension_test": "understanding",\n'
    '      "question": "题目内容",\n'
    '      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],\n'
    '      "answer": "A",\n'
    '      "explanation": "解析"\n'
    "    }}\n"
    "  ]\n"
    "}}"
)

# Mapping from template name to constant — used by prompt_utils.py
FALLBACK_TEMPLATES: dict = {
    "profile_extract_v1": PROFILE_EXTRACT_V1,
    "path_planning_v1": PATH_PLANNING_V1,
    "resource_document_v1": RESOURCE_DOCUMENT_V1,
    "resource_reading_v1": RESOURCE_READING_V1,
    "resource_quiz_v1": RESOURCE_QUIZ_V1,
    "resource_mindmap_v1": RESOURCE_MINDMAP_V1,
    "resource_video_v1": RESOURCE_VIDEO_V1,
    "resource_code_v1": RESOURCE_CODE_V1,
    "quality_check_v1": QUALITY_CHECK_V1,
    "tutor_answer_v1": TUTOR_ANSWER_V1,
    "resource_flowchart_v1": RESOURCE_FLOWCHART_V1,
    "general_chat_v1": GENERAL_CHAT_V1,
    "vision_analyze_v1": VISION_ANALYZE_V1,
    "post_test_v1": POST_TEST_V1,
}
