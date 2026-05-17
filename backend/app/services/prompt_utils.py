from __future__ import annotations
"""Shared prompt template loading and building utilities."""

from typing import Dict,  Optional

import json
import re
import threading
from pathlib import Path

_PROMPT_CACHE: Optional[Dict[str, str]] = None
_PROMPT_CACHE_LOCK = threading.Lock()


def load_prompt_templates() -> Dict[str, str]:
    global _PROMPT_CACHE
    with _PROMPT_CACHE_LOCK:
        if _PROMPT_CACHE is not None:
            return _PROMPT_CACHE
        path = Path(__file__).resolve().parents[1] / "data" / "prompt_templates.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            cache = {row["name"]: row["template"] for row in rows if row.get("name") and row.get("template")}
        except (FileNotFoundError, json.JSONDecodeError):
            cache = {}
        _PROMPT_CACHE = cache
        return cache


def get_template(name: str, fallback: str) -> str:
    # Priority: JSON overlay > embedded constants > caller-provided fallback
    from app.prompts.fallbacks import FALLBACK_TEMPLATES
    json_templates = load_prompt_templates()
    return json_templates.get(name) or FALLBACK_TEMPLATES.get(name) or fallback


def build_prompt(name: str, fallback: str, variables: dict, strategy_prompt: Optional[str] = None) -> str:
    """Load a prompt template, interpolate variables, and optionally prepend a strategy prompt.

    Uses single-pass regex replacement to avoid user-content injection into other placeholders.
    """
    template = get_template(name, fallback)

    # Build replacement map: serialize dict/list values once
    serialized: Dict[str, str] = {}
    for key, value in variables.items():
        if isinstance(value, (dict, list)):
            serialized[key] = json.dumps(value, ensure_ascii=False)
        else:
            serialized[key] = str(value)

    # Single-pass regex: replace all {key} placeholders at once
    def _replace(match: re.Match) -> str:
        k = match.group(1)
        return serialized.get(k, match.group(0))

    template = re.sub(r"\{(\w+)\}", _replace, template)

    if strategy_prompt:
        return f"{strategy_prompt}\n\n---\n\n{template}"
    return template


def invalidate_cache() -> None:
    """Clear the prompt template cache (for hot-reload or testing)."""
    global _PROMPT_CACHE
    with _PROMPT_CACHE_LOCK:
        _PROMPT_CACHE = None
