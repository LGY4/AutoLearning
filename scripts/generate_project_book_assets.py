from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "generated" / "assets"
SOURCE_ROOT = ROOT / "_analysis" / "AutoLearning-V2-xunfei-v4" / "AutoLearning-V2-xunfei-xunfei-v4"


def _setup_figure(width: float, height: float):
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(width, height), dpi=160)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def _box(ax, x, y, w, h, title, body, facecolor, edgecolor="#274c77", title_color="#0b2545"):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.4,
        facecolor=facecolor,
        edgecolor=edgecolor,
    )
    ax.add_patch(patch)
    ax.text(x + 0.02, y + h - 0.045, title, fontsize=12, fontweight="bold", color=title_color, va="top")
    ax.text(x + 0.02, y + h - 0.09, body, fontsize=9.2, color="#1f2937", va="top", linespacing=1.5)


def _arrow(ax, start, end, color="#2563eb", rad=0.0):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.4,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(arrow)


def build_architecture() -> None:
    fig, ax = _setup_figure(12, 7)
    fig.patch.set_facecolor("#f8fbff")
    ax.text(0.03, 0.95, "AutoLearning V2 总体架构图", fontsize=20, fontweight="bold", color="#0f172a")
    ax.text(0.03, 0.91, "依据实际源码结构整理：前端交互层、后端接口层、智能编排层、业务能力层、数据层", fontsize=10, color="#334155")

    _box(
        ax, 0.05, 0.70, 0.90, 0.14,
        "接入层 / Frontend",
        "React 18 + TypeScript + Vite + TailwindCSS\n17 个页面：工作台、画像、路径、题库、错题本、学情分析、知识图谱、数字人等",
        "#e0f2fe",
    )
    _box(
        ax, 0.05, 0.51, 0.90, 0.12,
        "接口层 / Backend API",
        "FastAPI + SQLAlchemy + Pydantic\n23 个 API 模块，76 个路由；支持认证、SSE 流式、资源生成、分析、讯飞能力接入",
        "#ecfccb",
    )
    _box(
        ax, 0.05, 0.31, 0.90, 0.14,
        "编排层 / Multi-Agent Orchestrator",
        "Orchestrator 统一调度 7 个专职 Agent\nProfile / Doc / Mindmap / Question / Code / Path / Tutor",
        "#fef3c7",
    )
    _box(
        ax, 0.05, 0.12, 0.43, 0.12,
        "业务能力层 / Services",
        "LLMClient、ProfileService、KnowledgeGraph、\nSpacedRepetition、AdaptiveDifficulty、Analytics、XFYunServices",
        "#ede9fe",
    )
    _box(
        ax, 0.52, 0.12, 0.43, 0.12,
        "数据层 / Data",
        "SQLite 业务库 + 本地知识内容 + 静态资源\n8 张核心表，约 20 个知识图谱节点",
        "#fee2e2",
    )

    _arrow(ax, (0.50, 0.70), (0.50, 0.63))
    _arrow(ax, (0.50, 0.51), (0.50, 0.45))
    _arrow(ax, (0.36, 0.31), (0.28, 0.24))
    _arrow(ax, (0.64, 0.31), (0.72, 0.24))
    ax.text(0.53, 0.665, "HTTP / JWT / SSE", fontsize=9, color="#1d4ed8")
    ax.text(0.53, 0.47, "单 Agent / 并行 / 串行", fontsize=9, color="#1d4ed8")
    fig.tight_layout()
    fig.savefig(ASSET_DIR / "system_architecture.png", bbox_inches="tight")
    plt.close(fig)


def build_agent_flow() -> None:
    fig, ax = _setup_figure(12, 6.5)
    fig.patch.set_facecolor("#fbfcfe")
    ax.text(0.03, 0.94, "多智能体协同流程图", fontsize=20, fontweight="bold", color="#0f172a")
    ax.text(0.03, 0.90, "先画像分析，再并行生成学习资源，最后汇总并流式返回", fontsize=10, color="#334155")

    _box(ax, 0.05, 0.54, 0.18, 0.18, "输入请求", "学习主题\n用户身份\n画像参数\n资源类型", "#dbeafe")
    _box(ax, 0.30, 0.54, 0.18, 0.18, "ProfileAgent", "读取 StudentProfile\n补齐 SharedContext\n生成个性化约束", "#dcfce7")

    agent_boxes = [
        (0.58, 0.75, "DocAgent", "课程文档"),
        (0.58, 0.55, "MindmapAgent", "思维导图"),
        (0.58, 0.35, "QuestionAgent", "练习题"),
        (0.78, 0.55, "CodeAgent", "代码案例"),
    ]
    for x, y, title, body in agent_boxes:
        _box(ax, x, y, 0.15, 0.12, title, body, "#fef3c7")

    _box(ax, 0.78, 0.35, 0.15, 0.12, "PathAgent", "学习路径", "#fef3c7")
    _box(ax, 0.30, 0.16, 0.18, 0.16, "TutorAgent", "结合画像答疑\n支持普通对话与流式对话", "#e9d5ff")
    _box(ax, 0.78, 0.13, 0.15, 0.16, "结果汇总", "context.results\nSSE 推送状态\norchestration_complete", "#fee2e2")

    _arrow(ax, (0.23, 0.63), (0.30, 0.63))
    for target in [(0.58, 0.81), (0.58, 0.61), (0.58, 0.41), (0.78, 0.61), (0.78, 0.41), (0.39, 0.32)]:
        _arrow(ax, (0.48, 0.63), target)

    for start in [(0.73, 0.81), (0.73, 0.61), (0.73, 0.41), (0.93, 0.61), (0.93, 0.41), (0.48, 0.24)]:
        _arrow(ax, start, (0.78, 0.21), color="#16a34a")

    ax.text(0.47, 0.69, "Orchestrator 并行调度", fontsize=9, color="#1d4ed8")
    ax.text(0.50, 0.27, "个性化辅导链路", fontsize=9, color="#7c3aed")
    fig.tight_layout()
    fig.savefig(ASSET_DIR / "agent_workflow.png", bbox_inches="tight")
    plt.close(fig)


def build_learning_loop() -> None:
    fig, ax = _setup_figure(12, 6.8)
    fig.patch.set_facecolor("#fbfdff")
    ax.text(0.03, 0.94, "学习闭环与数据回流图", fontsize=20, fontweight="bold", color="#0f172a")
    ax.text(0.03, 0.90, "项目的核心价值不是单次生成，而是路径、练习、复习、分析、画像更新形成闭环", fontsize=10, color="#334155")

    loop_nodes = [
        (0.08, 0.55, "学生画像", "基础信息\n学习风格\n知识水平", "#dbeafe"),
        (0.28, 0.76, "路径规划", "主题分阶段拆解\n阶段目标与里程碑", "#dcfce7"),
        (0.55, 0.76, "资源生成", "文档 / 导图 / 题目 / 代码", "#fef3c7"),
        (0.78, 0.55, "练习作答", "答题记录\n对话记录\n资源使用", "#fee2e2"),
        (0.65, 0.22, "错题复习", "SM-2 调度\n变式题生成", "#ede9fe"),
        (0.35, 0.18, "学情分析", "正确率\n掌握度\n趋势图", "#cffafe"),
    ]
    for x, y, title, body, color in loop_nodes:
        _box(ax, x, y, 0.16, 0.14, title, body, color)

    _arrow(ax, (0.24, 0.62), (0.28, 0.78))
    _arrow(ax, (0.44, 0.83), (0.55, 0.83))
    _arrow(ax, (0.71, 0.76), (0.82, 0.63))
    _arrow(ax, (0.78, 0.55), (0.72, 0.36))
    _arrow(ax, (0.65, 0.22), (0.51, 0.20))
    _arrow(ax, (0.35, 0.18), (0.18, 0.50))
    ax.text(0.51, 0.46, "数据回流", fontsize=11, fontweight="bold", color="#1d4ed8")
    ax.text(0.44, 0.38, "画像动态更新", fontsize=9, color="#2563eb")
    _arrow(ax, (0.43, 0.25), (0.19, 0.55), color="#2563eb", rad=0.18)
    fig.tight_layout()
    fig.savefig(ASSET_DIR / "learning_closed_loop.png", bbox_inches="tight")
    plt.close(fig)


def build_metrics_panel() -> None:
    fig, ax = _setup_figure(12, 5.8)
    fig.patch.set_facecolor("#f8fafc")
    ax.text(0.03, 0.92, "工程实现指标概览", fontsize=20, fontweight="bold", color="#0f172a")
    ax.text(0.03, 0.88, "以下指标来自当前 xunfei/v4 源码盘点，作为项目完成度佐证", fontsize=10, color="#334155")

    metrics = [
        ("7", "专职 Agent"),
        ("23", "API 模块"),
        ("76", "路由接口"),
        ("17", "前端页面"),
        ("8", "核心数据表"),
        ("20+", "知识图谱节点"),
    ]
    colors = ["#dbeafe", "#dcfce7", "#fef3c7", "#fee2e2", "#ede9fe", "#cffafe"]
    x_positions = [0.05, 0.21, 0.37, 0.53, 0.69, 0.85]

    for (value, label), x, color in zip(metrics, x_positions, colors):
        patch = FancyBboxPatch(
            (x, 0.35),
            0.12,
            0.28,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            linewidth=1.2,
            facecolor=color,
            edgecolor="#475569",
        )
        ax.add_patch(patch)
        ax.text(x + 0.06, 0.52, value, ha="center", va="center", fontsize=23, fontweight="bold", color="#0f172a")
        ax.text(x + 0.06, 0.40, label, ha="center", va="center", fontsize=10, color="#334155")

    ax.text(
        0.05,
        0.16,
        "支撑模块：JWT 认证、SSE 流式输出、知识图谱、错题本、SM-2 复习、自适应难度、学情分析、代码沙箱、讯飞数字人/语音/视频/PPT 接口",
        fontsize=10,
        color="#1f2937",
    )
    fig.tight_layout()
    fig.savefig(ASSET_DIR / "engineering_metrics.png", bbox_inches="tight")
    plt.close(fig)


def copy_logo() -> None:
    source = SOURCE_ROOT / "frontend" / "public" / "images" / "eventtuxiang.png"
    if source.exists():
        shutil.copy2(source, ASSET_DIR / "project_logo.png")


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    build_architecture()
    build_agent_flow()
    build_learning_loop()
    build_metrics_panel()
    copy_logo()
    print(str(ASSET_DIR.resolve()))


if __name__ == "__main__":
    main()
