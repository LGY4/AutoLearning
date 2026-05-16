from __future__ import annotations
"""Image generation service for course illustrations.

Uses HuggingFace Inference API (via mirror) for Stable Diffusion,
with fallback to placeholder generation using PIL.
"""

from typing import Optional

import base64
import hashlib
import io
import os
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STYLE_PROMPTS = {
    "educational": "educational illustration, clean design, modern flat style, white background, ",
    "diagram": "technical diagram, clean lines, labeled parts, professional, ",
    "cover": "book cover design, modern, elegant, gradient background, ",
    "ppt": "presentation slide illustration, minimal, corporate style, ",
    "cartoon": "cartoon style illustration, colorful, friendly, educational, ",
}


def _generate_with_hf(prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    """Try generating image via HuggingFace Inference API."""
    from app.core.config import get_settings

    settings = get_settings()
    token = settings.hf_token
    if not token:
        return None

    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    api_base = settings.hf_endpoint.rstrip("/")

    models = [
        "stabilityai/stable-diffusion-xl-base-1.0",
        "runwayml/stable-diffusion-v1-5",
        "CompVis/stable-diffusion-v1-4",
    ]

    for model in models:
        try:
            resp = httpx.post(
                f"{api_base}/models/{model}",
                json={"inputs": prompt},
                headers=headers,
                timeout=60,
            )
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except Exception:
            continue

    return None


def _generate_with_pollinations(prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    """Try generating image via Pollinations.ai (free, no API key)."""
    from urllib.parse import quote
    import httpx

    try:
        w, h = (int(x) for x in size.split("x"))
    except (ValueError, AttributeError):
        w, h = 1024, 1024

    encoded = quote(prompt[:200], safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true"

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            return resp.content
    except Exception:
        pass
    return None


def _generate_placeholder(prompt: str, size: str = "1024x1024") -> bytes:
    """Generate a placeholder image using PIL."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = (int(x) for x in size.split("x"))
    img = Image.new("RGB", (w, h), color=(24, 24, 32))
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    for y in range(h):
        r = int(24 + (y / h) * 20)
        g = int(24 + (y / h) * 30)
        b = int(32 + (y / h) * 40)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Draw decorative elements
    draw.rounded_rectangle(
        [w // 4, h // 4, w * 3 // 4, h * 3 // 4],
        radius=20,
        outline=(99, 102, 241),
        width=3,
    )

    # Draw text
    try:
        font = ImageFont.truetype("msyh.ttc", 24)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Wrap text
    lines = []
    words = prompt[:40]
    for i in range(0, len(words), 15):
        lines.append(words[i : i + 15])

    y_offset = h // 2 - len(lines) * 15
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y_offset), line, fill=(200, 200, 220), font=font)
        y_offset += 30

    # Draw label
    label = "[AI Generated Image]"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, h - 60), label, fill=(100, 100, 120), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_image(prompt: str, style: str = "educational", size: str = "1024x1024") -> dict:
    """Generate an image for educational content.

    Returns dict with 'image_base64', 'image_path', 'prompt'.
    """
    # Check cache
    cache_key = hashlib.md5(f"{prompt}:{style}:{size}".encode()).hexdigest()[:16]
    cache_path = OUTPUT_DIR / f"{cache_key}.png"

    if cache_path.exists():
        return {
            "image_base64": base64.b64encode(cache_path.read_bytes()).decode(),
            "image_path": str(cache_path),
            "prompt": prompt,
            "cached": True,
            "generator": "cache",
        }

    # Build styled prompt
    style_prefix = STYLE_PROMPTS.get(style, "")
    styled_prompt = f"{style_prefix}{prompt}"

    # Try HuggingFace API
    image_bytes = _generate_with_hf(styled_prompt, size)
    generator = "stable-diffusion"

    # Fallback: Pollinations.ai (free, no API key)
    if image_bytes is None:
        image_bytes = _generate_with_pollinations(styled_prompt, size)
        generator = "pollinations"

    # Fallback: placeholder
    if image_bytes is None:
        image_bytes = _generate_placeholder(prompt, size)
        generator = "placeholder"

    # Save
    cache_path.write_bytes(image_bytes)

    return {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "image_path": str(cache_path),
        "prompt": prompt,
        "cached": False,
        "generator": generator,
    }
