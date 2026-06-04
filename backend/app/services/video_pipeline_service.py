from __future__ import annotations
"""Video generation pipeline service.

5-step pipeline inspired by Pixelle-Video:
  LLM script → TTS audio → scene images → frame composition → FFmpeg assembly

Reuses existing model_gateway and image_gen_service.
"""

from typing import List,  Optional

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "generated_videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FRAME_W, FRAME_H = 1280, 720

SCRIPT_PROMPT = """\
你是教学视频分镜脚本生成器。根据用户主题，生成 {num_scenes} 个场景的教学视频脚本。

主题：{topic}
学科：{subject}

返回严格 JSON：
{{
  "title": "视频标题（15字以内）",
  "scenes": [
    {{
      "narration": "讲解旁白（50-100字，口语化，适合朗读）",
      "image_prompt": "English image prompt for AI illustration",
      "duration_hint": 8
    }}
  ]
}}

规则：
1. 第1个场景引入问题，中间场景讲解核心概念，最后场景总结
2. narration 必须口语化，适合 TTS 朗读
3. image_prompt 用英文，描述教学画面
4. duration_hint 为建议秒数（5-15）
"""

STYLE_PREFIXES = {
    "educational": "educational illustration, clean design, modern flat style, ",
    "cartoon": "cartoon style illustration, colorful, friendly, educational, ",
    "minimal": "minimalist design, clean lines, simple shapes, ",
    "tech": "futuristic tech style, dark background, neon accents, ",
    "hand_drawn": "hand-drawn sketch style, pencil illustration, warm tones, ",
}

TTS_VOICES = {
    "yunjian": "zh-CN-YunjianNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
}


# ── Step 1: LLM Script Generation ──────────────────────────────────────

def _generate_script(topic: str, subject: str, num_scenes: int) -> dict:
    from app.services.model_gateway import generate_json

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt(
        "video_script_v1",
        SCRIPT_PROMPT,
        {"topic": topic, "subject": subject, "num_scenes": num_scenes},
    )
    return generate_json(prompt, required_keys=["title", "scenes"])


# ── Step 2: TTS Audio Generation ───────────────────────────────────────

async def _generate_tts_async(text: str, voice: str, output_path: str) -> float:
    """Generate TTS audio, return duration in seconds."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate="+10%")
    await communicate.save(output_path)

    # Get duration via ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", output_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 8.0  # fallback


def _generate_tts(text: str, voice: str, output_path: str) -> float:
    """Generate TTS audio. Uses edge-tts CLI to avoid asyncio issues in background threads."""
    import shutil
    import tempfile

    edge_tts_cmd = shutil.which("edge-tts")
    if edge_tts_cmd:
        # Use CLI — works in any thread
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            text_file = f.name
        try:
            result = subprocess.run(
                [edge_tts_cmd, "--voice", voice, "--rate", "+10%", "--file", text_file, "--write-media", output_path],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"edge-tts CLI failed: {result.stderr[:200]}")
        finally:
            os.unlink(text_file)
    else:
        # Fallback: use edge-tts Python module via asyncio
        asyncio.run(_generate_tts_async(text, voice, output_path))

    # Get duration via ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", output_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 8.0  # fallback


# ── Step 3: Scene Image Generation ─────────────────────────────────────

def _generate_scene_image(prompt: str, style: str, output_path: str) -> str:
    """Generate image for a scene. Returns path to image.

    Fallback chain: image_gen_service → pollinations.ai → PIL text card.
    """
    styled_prompt = STYLE_PREFIXES.get(style, "") + prompt

    # Try existing image_gen_service
    try:
        from app.services.image_gen_service import generate_image
        import shutil
        result = generate_image(styled_prompt, style="educational", size="1280x720")
        if result.get("image_path") and Path(result["image_path"]).exists():
            src = Path(result["image_path"])
            dst = Path(output_path)
            if src.resolve() != dst.resolve():
                shutil.copy2(str(src), str(dst))
            return output_path
    except Exception:
        pass

    # Try pollinations.ai (free, no API key)
    try:
        import httpx
        from urllib.parse import quote
        encoded = quote(styled_prompt[:200], safe="")
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true"
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            Path(output_path).write_bytes(resp.content)
            return output_path
    except Exception:
        pass

    # Fallback: PIL text card
    _generate_text_card(prompt, output_path)
    return output_path


def _generate_text_card(text: str, output_path: str) -> None:
    """Generate a simple text card image using PIL."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (FRAME_W, FRAME_H), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(FRAME_H):
        r = int(15 + (y / FRAME_H) * 25)
        g = int(15 + (y / FRAME_H) * 35)
        b = int(25 + (y / FRAME_H) * 45)
        draw.line([(0, y), (FRAME_W, y)], fill=(r, g, b))

    # Decorative border
    draw.rounded_rectangle(
        [80, 80, FRAME_W - 80, FRAME_H - 80],
        radius=16, outline=(99, 102, 241), width=2,
    )

    # Text with wrapping
    try:
        font = ImageFont.truetype("msyh.ttc", 36)
    except (OSError, IOError):
        font = ImageFont.load_default()

    lines = []
    line = ""
    for char in text:
        line += char
        bbox = draw.textbbox((0, 0), line, font=font)
        if bbox[2] - bbox[0] > FRAME_W - 200:
            lines.append(line[:-1])
            line = char
    if line:
        lines.append(line)

    total_h = len(lines) * 48
    y_start = (FRAME_H - total_h) // 2
    for i, ln in enumerate(lines[:8]):
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((FRAME_W - tw) // 2, y_start + i * 48), ln, fill=(220, 220, 240), font=font)

    img.save(output_path, "PNG")


# ── Step 4: Frame Composition ──────────────────────────────────────────

def _compose_frame(narration: str, scene_image_path: str, output_path: str) -> None:
    """Compose a video frame: background image + narration text overlay."""
    from PIL import Image, ImageDraw, ImageFont

    # Load scene image or generate a text card fallback
    try:
        bg = Image.open(scene_image_path).resize((FRAME_W, FRAME_H))
    except Exception:
        fallback_path = scene_image_path + ".fallback.png"
        _generate_text_card(narration[:60], fallback_path)
        try:
            bg = Image.open(fallback_path).resize((FRAME_W, FRAME_H))
        except Exception:
            bg = Image.new("RGB", (FRAME_W, FRAME_H), color=(15, 15, 25))

    # Darken bottom area for text
    overlay = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for y in range(FRAME_H * 2 // 3, FRAME_H):
        alpha = int(180 * (y - FRAME_H * 2 // 3) / (FRAME_H // 3))
        draw_ov.line([(0, y), (FRAME_W, y)], fill=(0, 0, 0, alpha))
    bg = bg.convert("RGBA")
    bg = Image.alpha_composite(bg, overlay)
    bg = bg.convert("RGB")

    draw = ImageDraw.Draw(bg)
    try:
        font = ImageFont.truetype("msyh.ttc", 30)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Narration text at bottom
    lines = []
    line = ""
    for char in narration:
        line += char
        bbox = draw.textbbox((0, 0), line, font=font)
        if bbox[2] - bbox[0] > FRAME_W - 160:
            lines.append(line[:-1])
            line = char
    if line:
        lines.append(line)

    text_y = FRAME_H - 40 - len(lines) * 40
    for ln in lines[:4]:
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        # Text shadow
        draw.text(((FRAME_W - tw) // 2 + 2, text_y + 2), ln, fill=(0, 0, 0), font=font)
        draw.text(((FRAME_W - tw) // 2, text_y), ln, fill=(255, 255, 255), font=font)
        text_y += 40

    bg.save(output_path, "PNG")


# ── Step 5: FFmpeg Video Assembly ──────────────────────────────────────

def _make_segment(image_path: str, audio_path: str, output_path: str, duration: float) -> None:
    """Create a video segment from image + audio."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=120, check=True)


def _concat_segments(segment_paths: List[str], output_path: str) -> None:
    """Concatenate video segments into final video."""
    import tempfile

    list_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    for p in segment_paths:
        list_file.write(f"file '{p}'\n")
    list_file.close()

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file.name,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=300, check=True)
    os.unlink(list_file.name)


# ── Main Pipeline ──────────────────────────────────────────────────────

def generate_video(
    topic: str,
    subject: str = "通用",
    num_scenes: int = 5,
    style: str = "educational",
    tts_voice: str = "zh-CN-YunjianNeural",
    user_id: Optional[str] = None,
    emit_progress: Optional[callable] = None,
) -> dict:
    """Run the full video generation pipeline.

    Returns dict with video_id, video_path, title, duration, scenes.
    """
    task_id = uuid.uuid4().hex[:12]
    task_dir = OUTPUT_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    def _emit(event: dict):
        if emit_progress:
            try:
                emit_progress(event)
            except Exception:
                pass

    # ── Step 1: Generate script ──────────────────────────────────────
    _emit({"stage": "script", "status": "running", "hint": "正在生成分镜脚本..."})
    try:
        script = _generate_script(topic, subject, num_scenes)
    except Exception as exc:
        logger.error("Script generation failed: %s", exc)
        raise RuntimeError(f"分镜脚本生成失败: {exc}") from exc

    title = script.get("title", topic[:15])
    scenes = script.get("scenes", [])
    if not scenes:
        raise RuntimeError("LLM 未生成任何场景")

    _emit({"stage": "script", "status": "done", "hint": f"脚本就绪：{title}，共 {len(scenes)} 个场景"})

    segment_paths = []
    total_duration = 0.0
    scene_results = []

    for idx, scene in enumerate(scenes):
        narration = scene.get("narration", "")
        image_prompt = scene.get("image_prompt", "")
        duration_hint = scene.get("duration_hint", 8)

        scene_dir = task_dir / f"scene_{idx}"
        scene_dir.mkdir(exist_ok=True)

        # ── Step 2: TTS ─────────────────────────────────────────────
        _emit({"stage": "tts", "status": "running", "scene": idx, "hint": f"场景 {idx+1}：生成语音..."})
        audio_path = str(scene_dir / "audio.mp3")
        try:
            actual_duration = _generate_tts(narration, tts_voice, audio_path)
        except Exception as exc:
            logger.warning("TTS failed for scene %d: %s", idx, exc)
            actual_duration = float(duration_hint)
            # Create silent audio as fallback
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                 "-t", str(actual_duration), "-c:a", "aac", audio_path],
                capture_output=True, timeout=30,
            )
        _emit({"stage": "tts", "status": "done", "scene": idx})

        # ── Step 3: Image ───────────────────────────────────────────
        _emit({"stage": "image", "status": "running", "scene": idx, "hint": f"场景 {idx+1}：生成配图..."})
        raw_image_path = str(scene_dir / "raw_image.png")
        try:
            _generate_scene_image(image_prompt, style, raw_image_path)
        except Exception as exc:
            logger.warning("Image gen failed for scene %d: %s", idx, exc)
            _generate_text_card(narration, raw_image_path)
        _emit({"stage": "image", "status": "done", "scene": idx})

        # ── Step 4: Compose frame ───────────────────────────────────
        _emit({"stage": "compose", "status": "running", "scene": idx, "hint": f"场景 {idx+1}：合成画面..."})
        frame_path = str(scene_dir / "frame.png")
        _compose_frame(narration, raw_image_path, frame_path)
        _emit({"stage": "compose", "status": "done", "scene": idx})

        # ── Step 5: Make segment ────────────────────────────────────
        _emit({"stage": "segment", "status": "running", "scene": idx, "hint": f"场景 {idx+1}：合成视频片段..."})
        segment_path = str(scene_dir / "segment.mp4")
        try:
            _make_segment(frame_path, audio_path, segment_path, actual_duration)
            segment_paths.append(segment_path)
            total_duration += actual_duration
            scene_results.append({
                "scene": idx,
                "narration": narration,
                "duration": round(actual_duration, 1),
            })
        except Exception as exc:
            logger.warning("Segment creation failed for scene %d: %s", idx, exc)
        _emit({"stage": "segment", "status": "done", "scene": idx})

    if not segment_paths:
        raise RuntimeError("所有场景视频片段生成失败")

    # ── Concatenate ──────────────────────────────────────────────────
    _emit({"stage": "concat", "status": "running", "hint": "正在拼接最终视频..."})
    final_path = str(task_dir / "final.mp4")
    _concat_segments(segment_paths, final_path)
    _emit({"stage": "concat", "status": "done", "hint": "视频生成完成！"})

    # Generate thumbnail from first frame
    thumbnail_path = str(task_dir / "thumbnail.png")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", final_path, "-vf", "select=eq(n\\,0)",
             "-vframes", "1", "-q:v", "2", thumbnail_path],
            capture_output=True, timeout=15,
        )
    except Exception:
        thumbnail_path = None

    result = {
        "video_id": task_id,
        "video_path": final_path,
        "video_url": f"/api/v1/video/file/{task_id}",
        "thumbnail_url": f"/api/v1/video/thumbnail/{task_id}" if thumbnail_path and Path(thumbnail_path).exists() else None,
        "title": title,
        "duration_seconds": round(total_duration, 1),
        "scenes": scene_results,
        "topic": topic,
        "subject": subject,
    }

    # Save metadata
    meta_path = task_dir / "metadata.json"
    meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result
