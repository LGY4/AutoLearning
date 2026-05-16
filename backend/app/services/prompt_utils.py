from __future__ import annotations
"""Shared prompt template loading and building utilities."""

from typing import Dict,  Optional

import json
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
    return load_prompt_templates().get(name, fallback)


def build_prompt(name: str, fallback: str, variables: dict, strategy_prompt: Optional[str] = None) -> str:
    """Load a prompt template, interpolate variables, and optionally prepend a strategy prompt."""
    template = get_template(name, fallback)
    for key, value in variables.items():
        if isinstance(value, (dict, list)):
            placeholder = "{" + key + "}"
            if placeholder in template:
                template = template.replace(placeholder, json.dumps(value, ensure_ascii=False))
        else:
            template = template.replace("{" + key + "}", str(value))

    if strategy_prompt:
        return f"{strategy_prompt}\n\n---\n\n{template}"
    return template


def invalidate_cache() -> None:
    """Clear the prompt template cache (for hot-reload or testing)."""
    global _PROMPT_CACHE
    with _PROMPT_CACHE_LOCK:
        _PROMPT_CACHE = None
