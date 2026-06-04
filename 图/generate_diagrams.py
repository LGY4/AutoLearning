"""生成 AutoLearning 项目的5种UML/架构图"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import os

OUT = os.path.dirname(os.path.abspath(__file__))

# 中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 配色
C_USER = '#4FC3F7'
C_FRONTEND = '#81C784'
C_BACKEND = '#FFB74D'
C_AI = '#CE93D8'
C_DB = '#90A4AE'
C_RESOURCE = '#F48FB1'
C_DECISION = '#FFF176'
C_START_END = '#EF5350'

def _box(ax, x, y, w, h, text, color='#E3F2FD', fontsize=9, textcolor='black'):
    box = FancyBboxPatch((x - w/2, y - h/2), w, h,
                         boxstyle="round,pad=0.05", facecolor=color,
                         edgecolor='#37474F', linewidth=1.2)
    ax.add_patch(box)
    ax.text(x, y, text, ha='center', va='center', fontsize=fontsize,
            color=textcolor, fontweight='bold', wrap=True)

def _arrow(ax, x1, y1, x2, y2, color='#37474F'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5))

def _diamond(ax, x, y, w, h, text, color=C_DECISION, fontsize=8):
    diamond = plt.Polygon([(x, y+h/2), (x+w/2, y), (x, y-h/2), (x-w/2, y)],
                          facecolor=color, edgecolor='#37474F', linewidth=1.2)
    ax.add_patch(diamond)
    ax.text(x, y, text, ha='center', va='center', fontsize=fontsize, fontweight='bold')

# ─── 1. 系统架构流程图 ──────────────────────────────────────────────
def gen_flowchart():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_title('AutoLearning 系统架构流程图', fontsize=16, fontweight='bold', pad=20)

    # 用户层
    _box(ax, 7, 9.3, 2.5, 0.5, '用户 (浏览器)', C_USER, 11)

    # 前端层
    _box(ax, 2.5, 8.2, 2, 0.45, 'ChatPanel\n对话面板', C_FRONTEND, 8)
    _box(ax, 7, 8.2, 2, 0.45, 'LearningMapPage\n学习地图', C_FRONTEND, 8)
    _box(ax, 11.5, 8.2, 2, 0.45, 'ResourceRenderer\n资源渲染', C_FRONTEND, 8)

    # API层
    _box(ax, 2.5, 7, 2, 0.45, 'POST /tutor/chat\n辅导接口', C_BACKEND, 8)
    _box(ax, 7, 7, 2, 0.45, 'POST /learning/chat-stream\n学习流接口', C_BACKEND, 8)
    _box(ax, 11.5, 7, 2, 0.45, 'POST /resources/generate\n资源生成接口', C_BACKEND, 8)

    # 智能体层
    _box(ax, 2.5, 5.8, 2, 0.45, 'MasterAgent\n意图路由', C_AI, 9)
    _box(ax, 7, 5.8, 2, 0.45, 'TutorService\n辅导服务', C_AI, 9)
    _box(ax, 11.5, 5.8, 2, 0.45, 'LangGraph\n工作流引擎', C_AI, 9)

    # 策略层
    _box(ax, 2, 4.5, 1.8, 0.45, 'ProfileService\n画像服务', C_AI, 8)
    _box(ax, 5, 4.5, 1.8, 0.45, 'StrategyEngine\n策略引擎', C_AI, 8)
    _box(ax, 8, 4.5, 1.8, 0.45, 'ResourcePlanner\n资源规划', C_AI, 8)
    _box(ax, 11.5, 4.5, 2, 0.45, 'AdaptiveService\n自适应服务', C_AI, 8)

    # 生成层
    _box(ax, 2, 3.2, 1.5, 0.4, 'Document\n文档', C_RESOURCE, 7)
    _box(ax, 4, 3.2, 1.5, 0.4, 'Quiz\n测验', C_RESOURCE, 7)
    _box(ax, 6, 3.2, 1.5, 0.4, 'Mindmap\n思维导图', C_RESOURCE, 7)
    _box(ax, 8, 3.2, 1.5, 0.4, 'Flowchart\n流程图', C_RESOURCE, 7)
    _box(ax, 10, 3.2, 1.5, 0.4, 'Video\n视频', C_RESOURCE, 7)
    _box(ax, 12, 3.2, 1.5, 0.4, 'Code\n代码', C_RESOURCE, 7)

    # 基础层
    _box(ax, 3, 2, 2, 0.45, 'KnowledgeGraph\n知识图谱', C_DB, 8)
    _box(ax, 7, 2, 2, 0.45, 'RAG/Embedding\n向量检索', C_DB, 8)
    _box(ax, 11, 2, 2, 0.45, 'WebSearch\n网络搜索兜底', C_DB, 8)

    # 数据层
    _box(ax, 5, 0.8, 2.5, 0.45, 'PostgreSQL + ChromaDB\n持久化存储', C_DB, 8)
    _box(ax, 10, 0.8, 2.5, 0.45, 'LLM Provider\n大模型服务', C_DB, 8)

    # 箭头 - 垂直
    for x in [2.5, 7, 11.5]:
        _arrow(ax, x, 8.0, x, 7.25)
        _arrow(ax, x, 6.75, x, 6.05)

    # 水平连接
    _arrow(ax, 3.5, 5.8, 4.1, 4.75)
    _arrow(ax, 6.1, 5.8, 6.2, 4.75)
    _arrow(ax, 7.9, 5.8, 8.1, 4.75)
    _arrow(ax, 10.5, 5.8, 10.6, 4.75)

    # 生成层到策略层
    _arrow(ax, 2, 4.25, 2, 3.45)
    _arrow(ax, 5, 4.25, 5.5, 3.45)
    _arrow(ax, 8, 4.25, 8.5, 3.45)
    _arrow(ax, 11.5, 4.25, 11.5, 3.45)

    # 基础层到生成层
    _arrow(ax, 3, 2.25, 3, 2.95)
    _arrow(ax, 7, 2.25, 7, 2.95)
    _arrow(ax, 11, 2.25, 11, 2.95)

    # 数据层
    _arrow(ax, 5, 1.05, 5, 1.75)
    _arrow(ax, 10, 1.05, 10, 1.75)

    # 图例
    legend_items = [
        mpatches.Patch(color=C_USER, label='用户层'),
        mpatches.Patch(color=C_FRONTEND, label='前端层'),
        mpatches.Patch(color=C_BACKEND, label='API层'),
        mpatches.Patch(color=C_AI, label='智能体/策略层'),
        mpatches.Patch(color=C_RESOURCE, label='资源生成层'),
        mpatches.Patch(color=C_DB, label='基础/数据层'),
    ]
    ax.legend(handles=legend_items, loc='lower right', fontsize=8, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '1_系统架构流程图.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('1_系统架构流程图.png OK')


# ─── 2. 自适应学习时序图 ────────────────────────────────────────────
def gen_sequence():
    fig, ax = plt.subplots(figsize=(14, 11))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 11)
    ax.axis('off')
    ax.set_title('自适应学习时序图', fontsize=16, fontweight='bold', pad=20)

    # 参与者
    actors = ['用户', 'ChatPanel', 'TutorService', 'StrategyEngine', 'ProfileService', 'AdaptiveService', 'ResourcePlanner']
    x_positions = [1, 3, 5, 7, 9, 11, 13]
    colors = [C_USER, C_FRONTEND, C_AI, C_AI, C_AI, C_AI, C_AI]

    for i, (name, x, c) in enumerate(zip(actors, x_positions, colors)):
        _box(ax, x, 10.3, 1.4, 0.45, name, c, 8)
        ax.plot([x, x], [0.5, 10.05], color='#B0BEC5', linestyle='--', linewidth=0.8)

    # 消息序列
    messages = [
        (1, 3, 9.6, '发送问题 "什么是快速排序"'),
        (3, 5, 9.2, 'answer_question()'),
        (5, 6, 8.8, 'detect_intent() -> tutoring'),
        (5, 7, 8.4, 'get_teaching_params(dim)'),
        (7, 5, 8.0, '返回教学参数'),
        (5, 9, 7.6, 'get_profile(user_id)'),
        (9, 5, 7.2, '返回 StudentProfile'),
        (5, 1, 6.8, '返回辅导回答 + quiz'),
        (1, 3, 6.4, '回答测验问题'),
        (3, 5, 6.0, 'grade_and_record()'),
        (5, 7, 5.6, 'evaluate_knowledge_point()'),
        (7, 5, 5.2, '返回更新后维度'),
        (5, 9, 4.8, 'emit_event(ADAPTIVE_QUIZ)'),
        (9, 5, 4.4, '画像更新完成'),
        (5, 11, 4.0, 'post_learning_update()'),
        (11, 13, 3.6, 'plan_resources_for_user()'),
        (13, 11, 3.2, '返回规划列表 [quiz, mindmap, video]'),
        (11, 11, 2.8, '后台线程: 生成资源'),
        (11, 5, 2.4, 'invalidate_recommendations()'),
        (5, 1, 2.0, '推荐更新 + 新资源通知'),
    ]

    for x1, x2, y, label in messages:
        if x1 == x2:
            # 自调用
            ax.annotate('', xy=(x2+0.6, y-0.15), xytext=(x1+0.6, y),
                        arrowprops=dict(arrowstyle='->', color='#37474F', lw=1.2))
            ax.plot([x1+0.6, x2+0.6], [y, y-0.15], color='#37474F', lw=1.2)
            ax.text(x1+1.2, y-0.08, label, fontsize=6.5, va='center')
        else:
            direction = 1 if x2 > x1 else -1
            ax.annotate('', xy=(x2 - direction*0.5, y), xytext=(x1 + direction*0.5, y),
                        arrowprops=dict(arrowstyle='->', color='#37474F', lw=1.2))
            mid = (x1 + x2) / 2
            ax.text(mid, y + 0.12, label, ha='center', fontsize=6.5, va='center')

    # 阶段标注
    ax.axhline(y=7.8, color='#E0E0E0', linestyle=':', linewidth=0.8)
    ax.text(0.3, 9.0, '辅导阶段', fontsize=8, color='#666', rotation=90, va='center')
    ax.axhline(y=5.0, color='#E0E0E0', linestyle=':', linewidth=0.8)
    ax.text(0.3, 6.4, '测验评分', fontsize=8, color='#666', rotation=90, va='center')
    ax.text(0.3, 3.5, '自适应更新', fontsize=8, color='#666', rotation=90, va='center')

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '2_自适应学习时序图.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('2_自适应学习时序图.png OK')


# ─── 3. 资源生成活动图 ─────────────────────────────────────────────
def gen_activity():
    fig, ax = plt.subplots(figsize=(12, 14))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 14)
    ax.axis('off')
    ax.set_title('资源生成活动图', fontsize=16, fontweight='bold', pad=20)

    # 开始
    circle = plt.Circle((6, 13.3), 0.25, color=C_START_END, ec='#37474F', lw=1.5)
    ax.add_patch(circle)

    # 活动节点
    nodes = [
        (6, 12.5, '用户请求 / 画像更新触发 / 目标驱动', C_USER),
        (6, 11.5, 'MasterAgent 意图识别', C_AI),
        (6, 10.5, 'ProfileService 加载画像', C_AI),
        (6, 9.5, 'StrategyEngine 计算推荐参数', C_AI),
        (6, 8.5, 'ResourcePlanner 规划资源列表', C_AI),
    ]

    for x, y, text, color in nodes:
        _box(ax, x, y, 4.5, 0.5, text, color, 9)

    # 决策：资源类型
    _diamond(ax, 6, 7.3, 3, 0.8, '资源类型?', C_DECISION, 9)

    # 并行分支
    types = ['Document', 'Quiz', 'Mindmap', 'Flowchart', 'Video', 'Code']
    type_x = [1.5, 3.5, 5.5, 7.5, 9.5, 11]
    type_colors = [C_RESOURCE]*6

    for i, (tx, name) in enumerate(zip(type_x, types)):
        _box(ax, tx, 5.8, 1.5, 0.45, name, C_RESOURCE, 8)
        _arrow(ax, 6, 6.85, tx, 6.05)

    # 每种类型内部流程
    for tx in type_x:
        _box(ax, tx, 4.8, 1.5, 0.4, 'LLM 生成内容', '#E8F5E9', 7)
        _arrow(ax, tx, 5.55, tx, 5.05)
        _diamond(ax, tx, 3.9, 1.3, 0.6, '质量?', '#FFF9C4', 7)
        _arrow(ax, tx, 4.55, tx, 4.25)

    # 质量分支
    for tx in type_x:
        # 通过
        _arrow(ax, tx, 3.55, tx, 3.1)
        _box(ax, tx, 2.7, 1.2, 0.35, '保存资源', '#C8E6C9', 7)
        # 不通过 - 重试
        if tx < 10:
            _arrow(ax, tx+0.65, 3.9, tx+1.1, 4.5)
            ax.text(tx+0.85, 4.2, '重试', fontsize=6, color='red')

    # 汇聚
    _box(ax, 6, 1.8, 3, 0.45, 'WebSearch 兜底 (生成失败时)', '#FFCCBC', 8)

    # 推荐更新
    _box(ax, 6, 1.0, 3, 0.45, 'invalidate_recommendations()', C_AI, 8)

    # 结束
    circle2 = plt.Circle((6, 0.3), 0.25, color=C_START_END, ec='#37474F', lw=1.5)
    ax.add_patch(circle2)

    # 连接
    _arrow(ax, 6, 12.25, 6, 11.75)
    _arrow(ax, 6, 11.25, 6, 10.75)
    _arrow(ax, 6, 10.25, 6, 9.75)
    _arrow(ax, 6, 9.25, 6, 8.75)
    _arrow(ax, 6, 8.25, 6, 7.75)
    for tx in type_x:
        _arrow(ax, tx, 2.5, 6, 2.05)
    _arrow(ax, 6, 1.55, 6, 1.25)
    _arrow(ax, 6, 0.75, 6, 0.55)

    # 并行标注
    ax.annotate('并行扇出 (Fan-out)', xy=(6, 6.5), fontsize=9, ha='center',
                color='#1565C0', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#E3F2FD', edgecolor='#1565C0'))

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '3_资源生成活动图.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('3_资源生成活动图.png OK')


# ─── 4. 多智能体协作泳道图 ──────────────────────────────────────────
def gen_swimlane():
    fig, ax = plt.subplots(figsize=(16, 12))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 12)
    ax.axis('off')
    ax.set_title('多智能体协作泳道图 (LangGraph 资源生成流程)', fontsize=15, fontweight='bold', pad=15)

    # 泳道定义
    lanes = [
        (0, 3, '用户 / 前端', C_USER),
        (3, 6, 'MasterAgent', C_AI),
        (6, 9, 'ProfileAgent\nPathAgent', C_AI),
        (9, 12, 'ResourcePlanner\n8个生成Agent', C_RESOURCE),
        (12, 16, 'QualityAgent\nRecommendation', '#B39DDB'),
    ]

    for x1, x2, name, color in lanes:
        ax.fill_between([x1, x2], 0, 12, color=color, alpha=0.08)
        ax.plot([x1, x1], [0, 12], color='#37474F', lw=1.5)
        ax.text((x1+x2)/2, 11.6, name, ha='center', va='center',
                fontsize=10, fontweight='bold', color='#37474F',
                bbox=dict(boxstyle='round', facecolor=color, alpha=0.3))

    ax.plot([16, 16], [0, 12], color='#37474F', lw=1.5)

    # 流程步骤
    steps = [
        (1.5, 10.5, '发送学习请求', 0.8),
        (1.5, 9.8, 'POST /learning/chat-stream', 0.8),
        (4.5, 9.0, 'detect_intent()\n意图: resource_generation', 1.0),
        (4.5, 7.8, 'route_after_master()\n-> profile_agent', 0.8),
        (7.5, 7.0, 'extract_profile()\n更新画像', 0.8),
        (7.5, 6.0, 'build_learning_path()\n规划学习路径', 0.8),
        (7.5, 5.0, 'route_after_path()\n-> resource_planner', 0.8),
        (10.5, 4.2, 'plan_resource_types()\n确定8种类型', 0.8),
        (10.5, 3.2, '并行: gen_document, gen_quiz,\ngen_mindmap, gen_video ...', 1.2),
        (10.5, 2.2, 'WebSearch 兜底\n(失败时)', 0.8),
        (14, 1.5, 'quality_check()\n质量分 < 0.7 重试', 0.8),
        (14, 0.7, 'generate_recommendations()\n更新推荐', 0.8),
        (1.5, 0.3, '返回结果 (SSE)', 0.8),
    ]

    for x, y, text, w in steps:
        _box(ax, x, y, w*2.5, 0.55, text, '#E8EAF6', 7)

    # 箭头连接
    arrows = [
        (1.5, 10.2, 1.5, 10.0),
        (1.5, 9.5, 4.5, 9.3),
        (4.5, 8.5, 4.5, 8.1),
        (4.5, 7.5, 7.5, 7.3),
        (7.5, 6.7, 7.5, 6.3),
        (7.5, 5.7, 7.5, 5.3),
        (7.5, 4.7, 10.5, 4.5),
        (10.5, 3.9, 10.5, 3.5),
        (10.5, 2.9, 10.5, 2.5),
        (10.5, 1.9, 14, 1.8),
        (14, 1.2, 14, 1.0),
        (14, 0.4, 1.5, 0.3),
    ]

    for x1, y1, x2, y2 in arrows:
        _arrow(ax, x1, y1, x2, y2)

    # 条件分支标注
    ax.text(6.2, 8.5, 'if resource_generation', fontsize=7, color='#1565C0', style='italic')
    ax.text(8.8, 4.5, 'fan-out', fontsize=7, color='#1565C0', style='italic', fontweight='bold')
    ax.text(12.5, 1.8, 'if score < 0.7\nretry (max 2)', fontsize=7, color='red', style='italic')

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '4_多智能体协作泳道图.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('4_多智能体协作泳道图.png OK')


# ─── 5. 学习路径节点状态图 ──────────────────────────────────────────
def gen_state():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_title('学习路径节点状态图', fontsize=16, fontweight='bold', pad=20)

    # 状态节点
    states = {
        'LOCKED': (2, 7, '#EF9A9A'),
        'AVAILABLE': (7, 7, '#FFF59D'),
        'LEARNING': (7, 4, '#81D4FA'),
        'COMPLETED': (12, 4, '#A5D6A7'),
        'SKIPPED': (12, 7, '#B0BEC5'),
    }

    for name, (x, y, color) in states.items():
        _box(ax, x, y, 2.5, 0.8, name, color, 12, '#37474F')

    # 转换箭头
    transitions = [
        (2, 7, 7, 7, '前置依赖完成\n自动解锁', '#2E7D32'),
        (7, 7, 7, 4, '用户点击\n"开始学习"', '#1565C0'),
        (7, 4, 12, 4, '测验通过\n画像更新', '#2E7D32'),
        (7, 7, 12, 7, '画像显示已掌握\n自动跳过', '#F57F17'),
        (12, 7, 12, 4, '用户主动完成', '#6A1B9A'),
    ]

    for x1, y1, x2, y2, label, color in transitions:
        direction = 1 if x2 > x1 else -1
        y_offset = 0.15 if y2 == y1 else 0
        ax.annotate('', xy=(x2 - direction*1.3, y2 + y_offset), xytext=(x1 + direction*1.3, y1 + y_offset),
                    arrowprops=dict(arrowstyle='->', color=color, lw=2))
        mx, my = (x1+x2)/2, (y1+y2)/2
        if y1 != y2 and x1 == x2:
            mx = x1 + 1.8
        ax.text(mx, my + 0.25, label, ha='center', va='center', fontsize=8,
                color=color, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor=color, alpha=0.9))

    # 初始/终止标记
    ax.annotate('', xy=(2, 7.4), xytext=(0.5, 7.4),
                arrowprops=dict(arrowstyle='->', color='#37474F', lw=2))
    ax.text(0.2, 7.4, '初始', fontsize=9, fontweight='bold', color='#37474F')

    # 子状态说明
    info_text = (
        "状态转换规则:\n"
        "1. LOCKED: 前置依赖未完成，不可操作\n"
        "2. AVAILABLE: 前置已解锁，等待用户开始\n"
        "3. LEARNING: 用户正在学习该节点\n"
        "4. COMPLETED: 测验通过或手动标记完成\n"
        "5. SKIPPED: 画像显示已掌握，自动跳过\n\n"
        "完成节点后自动解锁下游 LOCKED 节点"
    )
    ax.text(3.5, 2.5, info_text, fontsize=9, va='top',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#F5F5F5', edgecolor='#BDBDBD'))

    # 自适应策略说明
    strategy_text = (
        "自适应策略:\n"
        "• 四维度评估: mastery/application/memory/understanding\n"
        "• composite_score = 0.3*m + 0.25*a + 0.2*mem + 0.25*u\n"
        "• score < 0.4: 补弱 (document + mindmap + video)\n"
        "• 0.4-0.7: 巩固 (document + quiz + code)\n"
        "• >= 0.7: 进阶 (quiz + code + reading)"
    )
    ax.text(8.5, 2.5, strategy_text, fontsize=9, va='top',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#E8F5E9', edgecolor='#81C784'))

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '5_学习路径节点状态图.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('5_学习路径节点状态图.png OK')


if __name__ == '__main__':
    gen_flowchart()
    gen_sequence()
    gen_activity()
    gen_swimlane()
    gen_state()
    print('All diagrams generated.')
