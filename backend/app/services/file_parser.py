from __future__ import annotations
from typing import List

"""File parser — extract text from uploaded PDF and Markdown files."""

import re
from pathlib import Path


def parse_markdown(content: str) -> str:
    """Extract structured text from Markdown content.

    Preserves headings as section markers, strips formatting.
    """
    lines = content.split("\n")
    result: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Keep headings as-is (they indicate structure)
        if stripped.startswith("#"):
            result.append(stripped)
        # Strip markdown formatting but keep text
        else:
            cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', stripped)  # links
            cleaned = re.sub(r'[*_`~]+', '', cleaned)  # bold/italic/code
            cleaned = re.sub(r'^[-*+]\s+', '• ', cleaned)  # list items
            cleaned = re.sub(r'^\d+\.\s+', '', cleaned)  # numbered lists
            if cleaned:
                result.append(cleaned)
    return "\n".join(result)


def parse_pdf_bytes(data: bytes) -> str:
    """Extract text from PDF bytes using PyPDF2 (lightweight, no system deps)."""
    try:
        import io
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages: List[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    except ImportError:
        # Fallback: try pdfplumber
        try:
            import io
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text.strip())
                return "\n\n".join(pages)
        except ImportError:
            raise RuntimeError(
                "No PDF parser installed. Install PyPDF2 or pdfplumber: "
                "pip install PyPDF2  OR  pip install pdfplumber"
            )


def parse_uploaded_file(filename: str, content: bytes) -> str:
    """Parse an uploaded file based on its extension."""
    ext = Path(filename).suffix.lower()

    if ext in (".md", ".markdown"):
        text = content.decode("utf-8", errors="replace")
        return parse_markdown(text)

    elif ext == ".pdf":
        return parse_pdf_bytes(content)

    elif ext in (".txt", ".text"):
        return content.decode("utf-8", errors="replace")

    elif ext in (".json",):
        import json
        data = json.loads(content.decode("utf-8"))
        # If it's a knowledge base format, extract titles + content
        if isinstance(data, list):
            parts = []
            for item in data:
                title = item.get("title", "")
                body = item.get("content", item.get("description", ""))
                if title or body:
                    parts.append(f"## {title}\n{body}" if title else body)
            return "\n\n".join(parts)
        return json.dumps(data, ensure_ascii=False, indent=2)

    else:
        # Try UTF-8 text as last resort
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Unsupported file type: {ext}")
