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
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true&seed={hash(prompt) % 10000}"

    for attempt in range(2):
        try:
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 5000:
                content_type = resp.headers.get("content-type", "")
                if "image" in content_type or resp.content[:8] in (b"\x89PNG\r\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF"):
                    return resp.content
        except Exception:
            if attempt == 0:
                import time
                time.sleep(2)
    return None


def _generate_with_craiyon(prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    """Try generating image via Craiyon/DALL-E mini API (free)."""
    import httpx

    try:
        resp = httpx.post(
            "https://api.craiyon.com/v3",
            json={"prompt": prompt[:200], "negative_prompt": "blurry, low quality", "model": "art"},
            timeout=90,
        )
        if resp.status_code == 200:
            data = resp.json()
            images = data.get("images", [])
            if images:
                import base64 as b64
                img_bytes = b64.b64decode(images[0])
                if len(img_bytes) > 5000:
                    return img_bytes
    except Exception:
        pass
    return None


def _generate_placeholder(prompt: str, size: str = "1024x1024") -> bytes:
    """Generate a visually meaningful placeholder image using PIL."""
    from PIL import Image, ImageDraw, ImageFont
    import random

    w, h = (int(x) for x in size.split("x"))
    img = Image.new("RGB", (w, h), color=(24, 24, 32))
    draw = ImageDraw.Draw(img)

    # Gradient background with color variation based on prompt hash
    seed = hash(prompt) % 1000
    random.seed(seed)
    base_r, base_g, base_b = random.randint(15, 40), random.randint(20, 50), random.randint(40, 80)

    for y in range(h):
        ratio = y / h
        r = int(base_r + ratio * 25)
        g = int(base_g + ratio * 35)
        b = int(base_b + ratio * 50)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Draw decorative circles
    for _ in range(6):
        cx = random.randint(w // 6, w * 5 // 6)
        cy = random.randint(h // 6, h * 5 // 6)
        radius = random.randint(30, 80)
        alpha_color = (random.randint(60, 120), random.randint(80, 160), random.randint(150, 240))
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=alpha_color, width=2)

    # Draw rounded rectangle frame
    draw.rounded_rectangle(
        [w // 6, h // 6, w * 5 // 6, h * 5 // 6],
        radius=24,
        outline=(99, 102, 241),
        width=3,
    )

    # Try to load CJK font
    try:
        font_large = ImageFont.truetype("msyh.ttc", 28)
        font_small = ImageFont.truetype("msyh.ttc", 18)
    except (OSError, IOError):
        try:
            font_large = ImageFont.truetype("arial.ttf", 28)
            font_small = ImageFont.truetype("arial.ttf", 18)
        except (OSError, IOError):
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Icon-like symbol
    icon_y = h // 3
    draw.text((w // 2 - 20, icon_y), "✨", fill=(99, 102, 241), font=font_large)

    # Prompt text wrapped
    lines = []
    display_text = prompt[:60]
    chars_per_line = max(10, w // 24)
    for i in range(0, len(display_text), chars_per_line):
        lines.append(display_text[i : i + chars_per_line])

    y_offset = h // 2 - len(lines) * 18
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_large)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y_offset), line, fill=(220, 220, 240), font=font_large)
        y_offset += 32

    # Status label
    label = "AI Image Placeholder"
    bbox = draw.textbbox((0, 0), label, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, h - 80), label, fill=(140, 140, 180), font=font_small)

    hint = "Configure HF_TOKEN for real images"
    bbox = draw.textbbox((0, 0), hint, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, h - 50), hint, fill=(100, 100, 130), font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _validate_image_bytes(data: bytes) -> bool:
    """Check that data is a valid image (not HTML error page or corrupt)."""
    if len(data) < 1000:
        return False
    # Check magic bytes for common image formats
    if data[:8] in (b"\x89PNG\r\n", b"GIF87a", b"GIF89a"):
        return True
    if data[:2] == b"\xff\xd8":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    # Try opening with PIL as a final check
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        img.verify()
        return True
    except Exception:
        return False


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

    # Fallback: Craiyon (free, no API key)
    if image_bytes is None:
        image_bytes = _generate_with_craiyon(styled_prompt, size)
        generator = "craiyon"

    # Fallback: placeholder
    if image_bytes is None:
        image_bytes = _generate_placeholder(prompt, size)
        generator = "placeholder"

    # Validate and save
    if not _validate_image_bytes(image_bytes):
        image_bytes = _generate_placeholder(prompt, size)
        generator = "placeholder"

    cache_path.write_bytes(image_bytes)

    return {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "image_path": str(cache_path),
        "prompt": prompt,
        "cached": False,
        "generator": generator,
    }
