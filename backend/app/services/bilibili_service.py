from __future__ import annotations
from typing import List

"""Bilibili video search with WBI signature."""

import hashlib
import time
import urllib.parse
from functools import lru_cache

import httpx

from app.services import model_gateway

_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
_WBI_NAV_API = "https://api.bilibili.com/x/web-interface/nav"

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(raw: str) -> str:
    return "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


def _get_wbi_keys() -> tuple[str, str]:
    import logging
    try:
        resp = httpx.get(_WBI_NAV_API, timeout=10)
        data = resp.json().get("data", {})
        img_url = data.get("wbi_img", {}).get("img_url", "")
        sub_url = data.get("wbi_img", {}).get("sub_url", "")
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
        return img_key, sub_key
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to fetch Bilibili WBI keys: %s", exc)
        return "", ""


def _sign_wbi(params: dict) -> dict:
    img_key, sub_key = _get_wbi_keys()
    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params


def search_videos(keyword: str, page: int = 1, page_size: int = 10, order: str = "totalrank") -> dict:
    """Search bilibili videos with WBI signature. Returns structured results."""
    params = _sign_wbi({
        "keyword": keyword,
        "search_type": "video",
        "page": page,
        "page_size": page_size,
        "order": order,
    })

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://search.bilibili.com",
    }

    try:
        resp = httpx.get(_SEARCH_API, params=params, headers=headers, timeout=15)
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "results": [], "total": 0}

    if data.get("code") != 0:
        return {"error": data.get("message", "API error"), "results": [], "total": 0}

    results_data = data.get("data", {})
    raw_results = results_data.get("result", []) or []

    results = []
    for item in raw_results:
        title = item.get("title", "")
        # Strip HTML tags from title
        import re
        title = re.sub(r"<[^>]+>", "", title)

        results.append({
            "bvid": item.get("bvid", ""),
            "title": title,
            "author": item.get("author", ""),
            "play": item.get("play", 0),
            "danmaku": item.get("video_review", 0),
            "duration": item.get("duration", ""),
            "description": item.get("description", "")[:200],
            "pic": item.get("pic", ""),
            "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            "pubdate": item.get("pubdate", 0),
            "tag": item.get("tag", ""),
        })

    return {
        "keyword": keyword,
        "total": results_data.get("numResults", len(results)),
        "page": page,
        "page_size": page_size,
        "results": results,
    }


def search_and_summarize(keyword: str, top_k: int = 5) -> List[dict]:
    """Search bilibili and return top results with brief summary. For integration into resource generation."""
    data = search_videos(keyword, page_size=top_k)
    if data.get("error"):
        return []
    return data.get("results", [])[:top_k]
