from __future__ import annotations
"""Manim animation generation service.

Uses LLM to generate Manim scene code from knowledge point descriptions,
then renders to MP4.
"""

import hashlib
import os
import tempfile
import textwrap
from pathlib import Path

from app.core.config import get_settings

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "animations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MANIM_PROMPT_TEMPLATE = """\
你是一个 Manim 动画代码生成器。根据以下知识点描述，生成完整的 Manim Scene 代码。

知识点：{knowledge_point}
学科：{subject}
难度：{difficulty}

要求：
1. 使用 `from manim import *` 导入
2. 定义一个名为 `GeneratedScene` 的 Scene 子类
3. 在 `construct` 方法中实现动画
4. 动画要直观展示知识点的核心概念
5. 使用中文文字（用 Text("...", font="Microsoft YaHei")）
6. 代码必须完整可运行，不要有省略号或占位符
7. 时长控制在 10-30 秒

只返回 Python 代码，不要任何解释。
"""


def _generate_manim_code(knowledge_point: str, subject: str, difficulty: str) -> str:
    """Use LLM to generate Manim scene code."""
    from app.services.model_gateway import generate_text

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt(
        "video_manim_v1",
        MANIM_PROMPT_TEMPLATE,
        {"knowledge_point": knowledge_point, "subject": subject, "difficulty": difficulty},
    )
    code = generate_text(prompt)

    # Clean up code block markers
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:])
        if code.rstrip().endswith("```"):
            code = code.rstrip()[:-3].rstrip()

    # Validate basic structure
    if "class GeneratedScene" not in code:
        raise ValueError("Generated code missing 'class GeneratedScene'")
    if "def construct" not in code:
        raise ValueError("Generated code missing 'def construct'")

    return code


_ALLOWED_IMPORTS = frozenset({
    "manim", "math", "numpy", "np", "random", "itertools", "functools",
    "collections", "string", "typing", "dataclasses", "enum", "colorsys",
})

_BLOCKED_CALLS = frozenset({
    "os.system", "os.popen", "subprocess", "exec", "eval",
    "open", "__import__", "importlib", "shutil.rmtree",
    "pathlib.Path.unlink", "pathlib.Path.rmdir",
})


def _validate_manim_code(code: str) -> None:
    """Reject code with dangerous patterns."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Generated code has syntax errors: {exc}") from exc

    for node in ast.walk(tree):
        # Block import of non-whitelisted modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in _ALLOWED_IMPORTS:
                    raise ValueError(f"Blocked import: {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root not in _ALLOWED_IMPORTS:
                    raise ValueError(f"Blocked import from: {node.module}")
        # Block calls to dangerous builtins
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("exec", "eval", "__import__", "open", "compile"):
                raise ValueError(f"Blocked call: {func.id}")
            if isinstance(func, ast.Attribute) and func.attr in ("system", "popen", "remove", "rmdir"):
                raise ValueError(f"Blocked call: .{func.attr}")

    # String-level check for patterns AST might miss
    for pattern in _BLOCKED_CALLS:
        if pattern in code:
            raise ValueError(f"Blocked pattern in code: {pattern}")


def _render_manim(code: str, scene_name: str = "GeneratedScene") -> str:
    """Render Manim code to MP4. Returns output file path."""
    import shutil
    import subprocess
    import sys

    _validate_manim_code(code)

    if not shutil.which("ffmpeg"):
        for candidate in [
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Packages"),
        ]:
            if os.path.isdir(candidate):
                os.environ["PATH"] = candidate + os.pathsep + os.environ.get("PATH", "")
                if shutil.which("ffmpeg"):
                    break
        else:
            raise RuntimeError("ffmpeg not found. Install ffmpeg and add it to PATH.")

    render_hash = hashlib.md5(code.encode()).hexdigest()[:12]
    render_dir = OUTPUT_DIR / render_hash
    render_dir.mkdir(parents=True, exist_ok=True)

    code_file = render_dir / "scene.py"
    code_file.write_text(code, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable, "-m", "manim",
            str(code_file),
            scene_name,
            "-qm",
            "--media_dir", str(render_dir / "media"),
            "--disable_caching",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(render_dir),
    )

    if result.returncode != 0:
        raise RuntimeError(f"Manim render failed: {result.stderr[-500:]}")

    for mp4 in render_dir.rglob("*.mp4"):
        if "partial" not in str(mp4):
            return str(mp4)

    raise RuntimeError("Manim render produced no output MP4")


def generate_animation(knowledge_point: str, subject: str = "数据结构", difficulty: str = "beginner") -> dict:
    """Generate a Manim animation for a knowledge point.

    Returns dict with 'code', 'video_path', 'knowledge_point'.
    """
    # Check cache
    cache_hash = hashlib.md5(f"{knowledge_point}:{subject}:{difficulty}".encode()).hexdigest()[:12]
    cache_dir = OUTPUT_DIR / cache_hash
    cached_mp4 = None
    for mp4 in cache_dir.rglob("*.mp4"):
        if "partial" not in str(mp4):
            cached_mp4 = str(mp4)
            break

    if cached_mp4:
        code_file = cache_dir / "scene.py"
        code = code_file.read_text(encoding="utf-8") if code_file.exists() else ""
        return {
            "code": code,
            "video_path": cached_mp4,
            "knowledge_point": knowledge_point,
            "cached": True,
        }

    # Generate code via LLM
    code = _generate_manim_code(knowledge_point, subject, difficulty)

    # Render
    video_path = _render_manim(code)

    # Save code to cache dir
    (cache_dir / "scene.py").write_text(code, encoding="utf-8")

    return {
        "code": code,
        "video_path": video_path,
        "knowledge_point": knowledge_point,
        "cached": False,
    }
