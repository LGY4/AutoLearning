from __future__ import annotations
"""Remotion video generation service.

Uses LLM to generate teaching video content, then renders via Remotion CLI.
"""

from typing import List,  Optional

import hashlib
import json
import logging
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

REMOTION_DIR = Path(__file__).resolve().parents[1] / "data" / "remotion-project"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_RENDER_TIMEOUT = 180  # seconds (first-run Webpack bundling + Chrome rendering)

VIDEO_PROMPT_TEMPLATE = """\
根据以下知识点，生成教学视频的内容结构。

知识点：{knowledge_point}
学科：{subject}
难度：{difficulty}

返回严格 JSON 格式：
{{
  "title": "视频标题",
  "sections": [
    {{
      "heading": "小节标题",
      "content": "讲解内容（50-100字）",
      "highlight": "需要高亮的关键词"
    }}
  ]
}}

要求：
1. 生成 3-5 个小节
2. 每个小节内容简洁明了
3. highlight 必须是 content 中出现的词
4. 总体时长约 15-30 秒
"""


def _preflight_check() -> Optional[str]:
    """Validate Remotion project is ready. Returns error message or None if OK."""
    entry = REMOTION_DIR / "src" / "index.tsx"
    if not entry.exists():
        return f"Remotion entry point missing: {entry}"
    node_modules = REMOTION_DIR / "node_modules"
    if not node_modules.exists():
        return f"node_modules not found: {node_modules}"
    # Find remotion CLI binary
    remotion_bin = node_modules / ".bin" / "remotion.cmd"  # Windows
    if not remotion_bin.exists():
        remotion_bin = node_modules / ".bin" / "remotion"  # Unix
    if not remotion_bin.exists():
        # Fallback to npx
        if not shutil.which("npx"):
            return "Neither remotion binary nor npx found"
    return None


def _get_remotion_cmd() -> List[str]:
    """Return the command to invoke remotion CLI."""
    remotion_cmd = REMOTION_DIR / "node_modules" / ".bin" / "remotion.cmd"
    if remotion_cmd.exists():
        return [str(remotion_cmd)]
    remotion_cmd = REMOTION_DIR / "node_modules" / ".bin" / "remotion"
    if remotion_cmd.exists():
        return [str(remotion_cmd)]
    return ["npx", "remotion"]


def _generate_video_content(knowledge_point: str, subject: str, difficulty: str) -> dict:
    """Use LLM to generate video content structure."""
    from app.services.model_gateway import generate_json

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt(
        "video_remotion_v1",
        VIDEO_PROMPT_TEMPLATE,
        {"knowledge_point": knowledge_point, "subject": subject, "difficulty": difficulty},
    )
    return generate_json(
        prompt,
        required_keys=["title", "sections"],
    )


def _find_chrome() -> Optional[str]:
    """Find system Chrome/Chromium executable."""
    candidates = [
        # Windows
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # Linux
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # Try PATH
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    return chrome


def _render_video(props: dict) -> str:
    """Render Remotion video to MP4."""
    # Preflight
    err = _preflight_check()
    if err:
        raise RuntimeError(f"Remotion preflight failed: {err}")

    # Write props to temp file
    props_file = REMOTION_DIR / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    output_path = OUTPUT_DIR / f"{hashlib.md5(json.dumps(props, sort_keys=True).encode()).hexdigest()[:12]}.mp4"

    # Set NODE_PATH for Remotion
    env = os.environ.copy()
    env["NODE_PATH"] = str(REMOTION_DIR / "node_modules")

    cmd = _get_remotion_cmd() + [
        "render",
        "src/index.tsx",
        "TeachingVideo",
        str(output_path),
        "--props", str(props_file),
    ]

    # Use system Chrome if available (avoids downloading Chrome Headless Shell)
    chrome = _find_chrome()
    if chrome:
        cmd.extend(["--browser-executable", chrome])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=_RENDER_TIMEOUT,
        cwd=str(REMOTION_DIR),
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Remotion render failed: {result.stderr[-500:]}")

    if not output_path.exists():
        raise RuntimeError("Remotion render produced no output")

    return str(output_path)


def generate_video(knowledge_point: str, subject: str = "数据结构", difficulty: str = "beginner") -> dict:
    """Generate a teaching video for a knowledge point."""
    cache_key = hashlib.md5(f"{knowledge_point}:{subject}:{difficulty}".encode()).hexdigest()[:12]
    cached = list(OUTPUT_DIR.glob(f"{cache_key}*.mp4"))
    if cached:
        return {"video_path": str(cached[0]), "knowledge_point": knowledge_point, "cached": True}

    content = _generate_video_content(knowledge_point, subject, difficulty)
    video_path = _render_video(content)
    return {"video_path": video_path, "props": content, "knowledge_point": knowledge_point, "cached": False}


def _extract_highlight(content: str, visual_desc: str) -> str:
    """Extract a meaningful keyword from content for video highlighting."""
    import re
    # Try to find technical terms (English words, Chinese terms with specific patterns)
    # Look for parenthesized terms like "push（入栈）"
    m = re.search(r'([a-zA-Z_]+)\s*[（(]', content)
    if m:
        return m.group(1)
    # Look for quoted or emphasized terms
    m = re.search(r'[""「]([^""」]+)[""」]', content)
    if m:
        return m.group(1)
    # Fall back to first significant word (3+ chars, not common words)
    words = re.findall(r'[一-鿿]{2,}|[a-zA-Z_]{3,}', content)
    stopwords = {"一种", "可以", "通过", "进行", "使用", "实现", "包括", "以及", "其中", "主要"}
    for w in words:
        if w not in stopwords:
            return w
    # Last resort: first 5 chars of content
    return content[:5] if content else ""


def render_from_storyboard(storyboard: dict) -> Optional[dict]:
    """Render a Remotion video from an existing storyboard (VideoDraft format).

    Runs rendering in a thread pool to avoid blocking the event loop.
    Returns dict with 'video_path' or None on failure.
    """
    try:
        title = storyboard.get("title", "教学视频")
        scenes = storyboard.get("scenes", [])
        if not scenes:
            return None

        sections = []
        for scene in scenes:
            content = scene.get("narration", scene.get("visual_description", ""))
            # Extract a keyword from content for highlighting
            highlight = _extract_highlight(content, scene.get("visual_description", ""))
            sections.append({
                "heading": scene.get("narration", "")[:30] or f"第{scene.get('frame', 1)}幕",
                "content": content,
                "highlight": highlight,
            })

        props = {"title": title, "sections": sections}

        cache_key = hashlib.md5(json.dumps(props, sort_keys=True).encode()).hexdigest()[:12]
        cached = list(OUTPUT_DIR.glob(f"{cache_key}*.mp4"))
        if cached:
            return {"video_path": str(cached[0]), "cached": True}

        # Run render in thread pool to avoid blocking
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_render_video, props)
            video_path = future.result(timeout=_RENDER_TIMEOUT + 10)

        return {"video_path": video_path, "cached": False}
    except Exception as e:
        logger.warning("Remotion render failed: %s", e)
        return None
