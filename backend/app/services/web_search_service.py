from __future__ import annotations
"""Web search fallback service — searches the web for existing resources when LLM generation fails.

Uses DuckDuckGo Lite (no API key required) for general search,
and bilibili_service for video search.
"""

import logging
import re
from typing import List

import httpx

logger = logging.getLogger(__name__)

_DDG_URL = "https://lite.duckduckgo.com/lite"
_DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# Platform detection from URL
_PLATFORM_PATTERNS = [
    (r"bilibili\.com", "bilibili"),
    (r"youtube\.com|youtu\.be", "youtube"),
    (r"github\.com", "github"),
    (r"csdn\.net", "csdn"),
    (r"zhihu\.com", "zhihu"),
    (r"juejin\.cn", "juejin"),
    (r"jianshu\.com", "jianshu"),
    (r"segmentfault\.com", "segmentfault"),
    (r"stackoverflow\.com", "stackoverflow"),
    (r"runoob\.com", "runoob"),
    (r"w3schools\.com", "w3schools"),
    (r"mdn\.mozilla", "mdn"),
    (r"wikipedia\.org", "wikipedia"),
]

# Search keyword templates per resource type
_TYPE_TEMPLATES = {
    "video": "{kp} 教程 视频",
    "animation": "{kp} 动画 演示 教学",
    "flowchart": "{kp} 流程图 draw.io",
    "mindmap": "{kp} 思维导图 知识图谱",
    "document": "{kp} 教程 文档 入门",
    "reading": "{kp} 学习资料 推荐阅读",
    "quiz": "{kp} 练习题 测试题",
    "code_case": "{kp} 代码示例 实战",
}


def _detect_platform(url: str) -> str:
    for pattern, name in _PLATFORM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return name
    return "web"


def _ddg_search(query: str, max_results: int = 10) -> List[dict]:
    """Search DuckDuckGo Lite and parse results."""
    try:
        resp = httpx.post(
            _DDG_URL,
            data={"q": query, "kl": "cn-zh"},
            headers=_DDG_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.debug("DuckDuckGo search failed: %s", e)
        return []

    results = []
    # Parse the lite HTML: links are in <a> tags with class="result-link"
    # Lite page is simple HTML, parse with regex for speed
    link_pattern = re.compile(
        r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>\s*(.*?)\s*</a>',
        re.DOTALL,
    )
    desc_pattern = re.compile(
        r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
        re.DOTALL,
    )

    links = link_pattern.findall(resp.text)
    descs = desc_pattern.findall(resp.text)

    from itertools import zip_longest
    for (url, title), raw_desc in zip_longest(links[:max_results], descs[:max_results], fillvalue=("", "")):
        # Skip DuckDuckGo internal links
        if "duckduckgo.com" in url or not url.startswith("http"):
            continue
        # Clean HTML from title
        title = re.sub(r"<[^>]+>", "", title).strip()
        desc = re.sub(r"<[^>]+>", "", raw_desc).strip() if raw_desc else ""
        results.append({
            "title": title,
            "url": url,
            "description": desc[:200],
            "platform": _detect_platform(url),
            "thumbnail": None,
        })

    return results


def search_videos(query: str, top_k: int = 5) -> List[dict]:
    """Search for video resources. Uses Bilibili + DuckDuckGo."""
    results = []

    # Bilibili search
    try:
        from app.services.bilibili_service import search_and_summarize
        bili_results = search_and_summarize(query, top_k=top_k)
        for r in bili_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", "")[:200],
                "platform": "bilibili",
                "thumbnail": r.get("pic", ""),
                "metadata": {
                    "play": r.get("play", 0),
                    "duration": r.get("duration", ""),
                    "author": r.get("author", ""),
                },
            })
    except Exception:
        logger.debug("Bilibili search failed, falling back to DuckDuckGo")

    # Supplement with DuckDuckGo if not enough
    if len(results) < top_k:
        ddg_results = _ddg_search(f"{query} 教程 视频", max_results=top_k)
        existing_urls = {r["url"] for r in results}
        for r in ddg_results:
            if r["url"] not in existing_urls and len(results) < top_k:
                results.append(r)

    return results[:top_k]


def search_diagrams(query: str, top_k: int = 5) -> List[dict]:
    """Search for flowchart/mindmap resources."""
    ddg_results = _ddg_search(f"{query} 流程图 思维导图 drawio", max_results=top_k)
    if not ddg_results:
        ddg_results = _ddg_search(f"{query} diagram tutorial", max_results=top_k)
    return ddg_results[:top_k]


def search_documents(query: str, top_k: int = 5) -> List[dict]:
    """Search for documents/tutorials/reading materials."""
    ddg_results = _ddg_search(f"{query} 教程 文档 入门", max_results=top_k)
    if not ddg_results:
        ddg_results = _ddg_search(f"{query} tutorial documentation", max_results=top_k)
    return ddg_results[:top_k]


def search_code_examples(query: str, top_k: int = 5) -> List[dict]:
    """Search for code examples."""
    ddg_results = _ddg_search(f"{query} 代码示例 github", max_results=top_k)
    if not ddg_results:
        ddg_results = _ddg_search(f"{query} code example github", max_results=top_k)
    return ddg_results[:top_k]


def search_resources(query: str, resource_type: str, top_k: int = 5) -> List[dict]:
    """Search for web resources matching the given type. Main entry point."""
    template = _TYPE_TEMPLATES.get(resource_type, "{kp} 教程")
    search_query = template.format(kp=query)

    dispatch = {
        "video": search_videos,
        "animation": search_videos,
        "flowchart": search_diagrams,
        "mindmap": search_diagrams,
        "document": search_documents,
        "reading": search_documents,
        "quiz": lambda q, k: _ddg_search(f"{q} 练习题 测试题", max_results=k),
        "code_case": search_code_examples,
    }

    fn = dispatch.get(resource_type, search_documents)
    # Pass raw query — the dispatch functions already have their own keyword suffixes
    results = fn(query, top_k)

    # Fallback: if specific search returns nothing, try generic
    if not results and resource_type not in ("video", "document"):
        results = _ddg_search(search_query, max_results=top_k)

    return results


def format_as_web_resource(
    results: List[dict],
    resource_type: str,
    knowledge_point: str,
) -> dict:
    """Format web search results as a LearningResource-compatible dict."""
    type_labels = {
        "video": "视频",
        "animation": "动画",
        "flowchart": "流程图",
        "mindmap": "思维导图",
        "document": "文档",
        "reading": "阅读材料",
        "quiz": "练习题",
        "code_case": "代码示例",
    }
    label = type_labels.get(resource_type, "资源")

    # Build markdown content with links
    lines = [f"## {knowledge_point} — 相关{label}（网络资源）\n"]
    lines.append(f"以下是从网络搜索到的 **{knowledge_point}** 相关{label}资源：\n")

    for i, r in enumerate(results, 1):
        platform = r.get("platform", "web")
        title = r.get("title", "无标题")
        url = r.get("url", "#")
        desc = r.get("description", "")
        lines.append(f"### {i}. [{title}]({url})")
        lines.append(f"**来源**: {platform}")
        if desc:
            lines.append(f"\n{desc}")
        lines.append("")

    content = "\n".join(lines)

    return {
        "resource_type": resource_type,
        "title": f"{knowledge_point} - {label}（网络资源）",
        "content": content,
        "status": "web_fallback",
        "metadata": {
            "source": "web_search",
            "results": results,
            "knowledge_point": knowledge_point,
        },
    }
