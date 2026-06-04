"""Fallback digital human video generation.

When Xfyun API is unavailable, generates teaching videos using:
- LLM script expansion → scene-based narration
- Scene image generation (HuggingFace / pollinations.ai / PIL text card)
- TTS audio synthesis (edge-tts CLI / OpenAI-compatible API)
- FFmpeg video assembly (scene images + avatar overlay + subtitles + audio)

No heavy dependencies — works on any machine with FFmpeg.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Optional

from app.services import tts_service

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "generated_videos"
_FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"
_AVATAR_DIR = Path(__file__).resolve().parents[1] / "assets" / "avatars"
_DEFAULT_AVATAR = _AVATAR_DIR / "default_avatar.png"

W, H = 1280, 720

STYLE_PREFIX = "educational illustration, clean design, modern flat style, "

# ── Scene image generation (same fallback chain as video_pipeline_service) ──

def _generate_scene_image(prompt: str, output_path: str) -> None:
    """Generate scene image. Fallback: HuggingFace → pollinations.ai → PIL text card."""
    styled = STYLE_PREFIX + prompt

    # Try HuggingFace
    try:
        from app.services.image_gen_service import generate_image
        result = generate_image(styled, style="educational", size="1280x720")
        if result.get("image_path") and Path(result["image_path"]).exists():
            shutil.copy2(result["image_path"], output_path)
            return
    except Exception:
        pass

    # Try pollinations.ai (free, no API key)
    try:
        import httpx
        from urllib.parse import quote
        encoded = quote(styled[:200], safe="")
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true"
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            Path(output_path).write_bytes(resp.content)
            return
    except Exception:
        pass

    # Fallback: PIL text card
    _generate_text_card(prompt, output_path)


def _generate_text_card(text: str, output_path: str) -> None:
    """Generate a styled text card using PIL."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(H):
        r = int(15 + (y / H) * 25)
        g = int(15 + (y / H) * 35)
        b = int(25 + (y / H) * 45)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Border
    draw.rounded_rectangle([80, 80, W - 80, H - 80], radius=16, outline=(99, 102, 241), width=2)

    # Text
    try:
        font = ImageFont.truetype(_FONT_PATH, 36)
    except (OSError, IOError):
        font = ImageFont.load_default()

    lines, line = [], ""
    for char in text:
        line += char
        bbox = draw.textbbox((0, 0), line, font=font)
        if bbox[2] - bbox[0] > W - 200:
            lines.append(line[:-1])
            line = char
    if line:
        lines.append(line)

    total_h = len(lines) * 48
    y_start = (H - total_h) // 2
    for i, ln in enumerate(lines[:8]):
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y_start + i * 48), ln, fill=(220, 220, 240), font=font)

    img.save(output_path, "PNG")


def _generate_avatar_overlay(save_path: Path) -> None:
    """Generate a simple circular avatar placeholder."""
    from PIL import Image, ImageDraw

    size = 180
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Circle
    draw.ellipse([0, 0, size - 1, size - 1], fill=(74, 144, 217, 230))
    # Inner circle (head placeholder)
    draw.ellipse([55, 25, 125, 95], fill=(255, 220, 180, 255))
    # Body
    draw.ellipse([35, 100, 145, 200], fill=(74, 144, 217, 255))
    save_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(save_path, "PNG")


# ── Script expansion via LLM ──

def _expand_script(text: str, knowledge_point: str) -> list[dict]:
    """Use LLM to expand text into scene-based script.

    Returns list of {narration, image_prompt, duration_hint}.
    Falls back to simple splitting if LLM unavailable.
    """
    try:
        from app.services.model_gateway import generate_json

        prompt = f"""你是教学视频分镜脚本生成器。根据以下内容，生成 3-5 个场景的教学视频脚本。

主题：{knowledge_point or text[:30]}
内容：{text}

返回严格 JSON：
{{
  "scenes": [
    {{
      "narration": "讲解旁白（口语化，适合朗读，50-100字）",
      "image_prompt": "English image prompt for AI illustration of this scene",
      "duration_hint": 8
    }}
  ]
}}

规则：
1. 第1个场景引入主题，中间讲解核心概念，最后总结
2. narration 口语化，适合 TTS 朗读
3. image_prompt 用英文，描述教学画面
4. duration_hint 为建议秒数（5-15）"""

        result = generate_json(prompt, required_keys=["scenes"])
        scenes = result.get("scenes", [])
        if scenes and isinstance(scenes[0], dict):
            return scenes
    except Exception:
        logger.warning("LLM script expansion failed, using simple split", exc_info=True)

    # Fallback: simple split by sentences
    sentences = re.split(r'(?<=[。！？.!?])\s*', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text]

    # Group into scenes of 1-2 sentences
    scenes = []
    for i in range(0, len(sentences), 2):
        chunk = " ".join(sentences[i:i + 2])
        scenes.append({
            "narration": chunk,
            "image_prompt": f"educational illustration about: {knowledge_point or chunk[:50]}",
            "duration_hint": max(5, min(15, len(chunk) // 5)),
        })
    return scenes


# ── TTS generation ──

def _generate_tts(text: str, output_path: str) -> float:
    """Generate TTS audio, return duration in seconds.

    Prefers edge-tts CLI (works in background threads),
    falls back to OpenAI-compatible API via tts_service.
    """
    edge_tts_cmd = shutil.which("edge-tts")
    if edge_tts_cmd:
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(text)
                text_file = f.name
            try:
                result = subprocess.run(
                    [edge_tts_cmd, "--voice", "zh-CN-YunjianNeural", "--rate", "+10%",
                     "--file", text_file, "--write-media", output_path],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    return _get_duration(output_path)
            finally:
                os.unlink(text_file)
        except Exception:
            logger.warning("edge-tts failed, falling back to tts_service", exc_info=True)

    # Fallback: OpenAI-compatible TTS
    audio_bytes = tts_service.synthesize(text=text, voice="alloy", model="tts-1")
    Path(output_path).write_bytes(audio_bytes)
    return _get_duration(output_path)


def _get_duration(media_path: str) -> float:
    """Get media duration via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", media_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 8.0


# ── Subtitle generation ──

def _split_subtitles(text: str, max_chars: int = 18) -> list[str]:
    """Split text into subtitle-length segments."""
    parts = re.split(r'([。！？；\n.!?;,，、])', text)
    sentences: list[str] = []
    buf = ""
    for part in parts:
        if re.match(r'[。！？；\n.!?;,，、]', part):
            buf += part
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
        else:
            buf += part
    if buf.strip():
        sentences.append(buf.strip())

    result: list[str] = []
    for seg in sentences:
        if len(seg) <= max_chars:
            result.append(seg)
        else:
            while len(seg) > max_chars:
                result.append(seg[:max_chars])
                seg = seg[max_chars:]
            if seg:
                result.append(seg)
    return [s for s in result if s]


# ── Frame composition with PIL ──

def _compose_frame(scene_image_path: str, narration: str, avatar_path: Optional[str], output_path: str) -> None:
    """Compose a single frame: scene image + avatar overlay + narration text."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        bg = Image.open(scene_image_path).resize((W, H)).convert("RGBA")
    except Exception:
        bg = Image.new("RGBA", (W, H), (15, 15, 25, 255))

    # Darken bottom area for subtitle
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for y in range(H * 2 // 3, H):
        alpha = int(180 * (y - H * 2 // 3) // (H // 3))
        draw_ov.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    bg = Image.alpha_composite(bg, overlay)

    # Avatar overlay (bottom-left corner)
    if avatar_path and Path(avatar_path).exists():
        try:
            avatar = Image.open(avatar_path).convert("RGBA")
            avatar = avatar.resize((150, 150))
            bg.paste(avatar, (50, H - 220), avatar)
        except Exception:
            pass

    bg = bg.convert("RGB")
    draw = ImageDraw.Draw(bg)

    # Narration text at bottom center
    try:
        font = ImageFont.truetype(_FONT_PATH, 30)
    except (OSError, IOError):
        font = ImageFont.load_default()

    lines, line = [], ""
    for char in narration:
        line += char
        bbox = draw.textbbox((0, 0), line, font=font)
        if bbox[2] - bbox[0] > W - 250:
            lines.append(line[:-1])
            line = char
    if line:
        lines.append(line)

    total_h = len(lines) * 42
    y_start = H - 60 - total_h
    for i, ln in enumerate(lines[:4]):
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y_start + i * 42), ln, fill=(255, 255, 255), font=font)

    bg.save(output_path, "PNG")


# ── Main pipeline ──

def generate_fallback_video(
    text: str,
    knowledge_point: str = "",
    avatar_path: Optional[str] = None,
    emit_progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Generate teaching video with scene images + avatar + subtitles + audio.

    Pipeline:
    1. LLM expands text into scene-based script
    2. Generate images for each scene
    3. Generate TTS audio for each scene
    4. Compose frames (image + avatar + narration)
    5. Assemble final video with FFmpeg
    """
    task_id = uuid.uuid4().hex[:12]
    save_dir = _OUTPUT_DIR / task_id
    save_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Expand script
    if emit_progress:
        emit_progress({"stage": "script", "status": "running", "progress": 5, "hint": "正在生成分镜脚本..."})

    scenes = _expand_script(text, knowledge_point)

    if emit_progress:
        emit_progress({"stage": "script", "status": "done", "progress": 15, "hint": f"脚本就绪（{len(scenes)}个场景）"})

    # Prepare avatar
    avatar_file = save_dir / "avatar.png"
    if avatar_path and Path(avatar_path).exists():
        avatar_file = Path(avatar_path)
    elif not _DEFAULT_AVATAR.exists():
        _generate_avatar_overlay(_DEFAULT_AVATAR)
        avatar_file = _DEFAULT_AVATAR
    else:
        avatar_file = _DEFAULT_AVATAR

    # Step 2-4: Generate per-scene assets and compose frames
    scene_videos: list[str] = []
    total = len(scenes)

    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "")
        image_prompt = scene.get("image_prompt", knowledge_point or text[:50])
        pct_base = 20 + int(70 * i / total)
        pct_end = 20 + int(70 * (i + 1) / total)

        # Generate scene image
        if emit_progress:
            emit_progress({"stage": f"scene_{i}", "status": "running", "progress": pct_base,
                           "hint": f"正在生成场景 {i + 1}/{total} 画面..."})

        scene_img = save_dir / f"scene_{i}.png"
        _generate_scene_image(image_prompt, str(scene_img))

        # Compose frame with avatar + narration
        frame_img = save_dir / f"frame_{i}.png"
        _compose_frame(str(scene_img), narration, str(avatar_file), str(frame_img))

        # Generate TTS audio for this scene
        if emit_progress:
            emit_progress({"stage": f"scene_{i}", "status": "running", "progress": pct_base + 5,
                           "hint": f"正在生成场景 {i + 1}/{total} 语音..."})

        scene_audio = save_dir / f"audio_{i}.mp3"
        duration = _generate_tts(narration, str(scene_audio))

        # Create scene video (image + audio)
        scene_video = save_dir / f"scene_{i}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(frame_img),
            "-i", str(scene_audio),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-shortest",
            str(scene_video),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("FFmpeg scene %d failed: %s", i, result.stderr[-300:])
            continue

        scene_videos.append(str(scene_video))

        if emit_progress:
            emit_progress({"stage": f"scene_{i}", "status": "done", "progress": pct_end,
                           "hint": f"场景 {i + 1}/{total} 完成"})

    if not scene_videos:
        raise RuntimeError("所有场景视频生成失败")

    # Step 5: Concatenate all scene videos
    if emit_progress:
        emit_progress({"stage": "assemble", "status": "running", "progress": 90, "hint": "正在合成最终视频..."})

    concat_file = save_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{v}'" for v in scene_videos), encoding="utf-8")

    final_video = save_dir / "dh_final.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(final_video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error("FFmpeg concat failed: %s", result.stderr[-300:])
        raise RuntimeError(f"视频合成失败: {result.stderr[-200:]}")

    if emit_progress:
        emit_progress({"stage": "assemble", "status": "done", "progress": 95, "hint": "视频合成完成"})

    # Save metadata
    metadata = {
        "task_id": task_id,
        "mode": "fallback",
        "knowledge_point": knowledge_point,
        "num_scenes": len(scenes),
        "scenes": [{"narration": s.get("narration", ""), "image_prompt": s.get("image_prompt", "")} for s in scenes],
        "video_path": str(final_video),
    }
    (save_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    if emit_progress:
        emit_progress({"stage": "done", "status": "done", "progress": 100, "hint": "数字人教学视频就绪"})

    return {
        "task_id": task_id,
        "video_path": str(final_video),
        "cover_path": "",
        "audio_path": "",
        "metadata": metadata,
    }
