from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
KB_PATH = DATA_DIR / "knowledge_base.json"
MANIFEST_PATH = DATA_DIR / "system_kb_manifest.json"
SCHEMA_PATH = DATA_DIR / "system_kb_schema.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return load_json(MANIFEST_PATH)


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        return {}
    return load_json(SCHEMA_PATH)


def _load_rows() -> list[dict]:
    if not KB_PATH.exists():
        return []
    rows = load_json(KB_PATH)
    return rows if isinstance(rows, list) else []


def merge_chunk_metadata(row: dict, defaults: Optional[dict] = None) -> dict:
    defaults = defaults or load_manifest().get("default_chunk_metadata", {})
    merged = dict(row)
    for key, value in defaults.items():
        merged.setdefault(key, value)
    merged.setdefault("content_hash", sha256_text(str(merged.get("content", ""))))
    return merged


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_knowledge_base() -> list[str]:
    failures: list[str] = []
    if not KB_PATH.exists():
        return [f"Missing knowledge base: {KB_PATH}"]
    if not MANIFEST_PATH.exists():
        return [f"Missing system knowledge manifest: {MANIFEST_PATH}"]
    if not SCHEMA_PATH.exists():
        return [f"Missing system knowledge schema: {SCHEMA_PATH}"]

    manifest = load_manifest()
    schema = load_schema()
    rows = load_json(KB_PATH)
    defaults = manifest.get("default_chunk_metadata", {})
    required = manifest.get("required_chunk_fields", [])
    schema_required = schema.get("$defs", {}).get("chunk", {}).get("required", [])
    allowed_review = set(manifest.get("allowed_review_statuses", []))
    allowed_authority = set(manifest.get("allowed_authority_levels", []))
    source_prefixes = {
        source.get("source_name"): source.get("url_prefixes", [])
        for source in manifest.get("allowed_sources", [])
        if source.get("source_name")
    }

    if not isinstance(rows, list) or not rows:
        failures.append("knowledge_base.json must contain at least one chunk")
        return failures
    if not schema_required:
        failures.append("system_kb_schema.json must define $defs.chunk.required")
    elif set(required) != set(schema_required):
        failures.append("manifest required_chunk_fields must match schema chunk.required")

    seen_ids: set[str] = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            failures.append(f"chunk[{index}] must be an object")
            continue
        chunk = merge_chunk_metadata(raw, defaults)
        chunk_id = str(chunk.get("chunk_id", f"index-{index}"))

        if chunk_id in seen_ids:
            failures.append(f"{chunk_id}: duplicate chunk_id")
        seen_ids.add(chunk_id)

        for field in required:
            value = chunk.get(field)
            if value in (None, "", []):
                failures.append(f"{chunk_id}: missing required field {field}")

        source_name = str(chunk.get("source_name", ""))
        source_url = str(chunk.get("source_url", ""))
        if source_name not in source_prefixes:
            failures.append(f"{chunk_id}: source_name is not in manifest allowlist")
        elif not any(source_url.startswith(prefix) for prefix in source_prefixes[source_name]):
            failures.append(f"{chunk_id}: source_url is outside allowed prefixes")
        if not _valid_url(source_url):
            failures.append(f"{chunk_id}: source_url must be an absolute http(s) URL")

        review_status = str(chunk.get("review_status", ""))
        if review_status not in allowed_review:
            failures.append(f"{chunk_id}: review_status {review_status!r} is not allowed")

        authority = str(chunk.get("authority_level", ""))
        if authority not in allowed_authority:
            failures.append(f"{chunk_id}: authority_level {authority!r} is not allowed")

        expected_hash = sha256_text(str(chunk.get("content", "")))
        actual_hash = str(chunk.get("content_hash", ""))
        if raw.get("content_hash") and actual_hash != expected_hash:
            failures.append(f"{chunk_id}: content_hash does not match content")

    return failures


def chunk_summaries(query: str = "", subject: Optional[str] = None, limit: int = 50) -> list[dict]:
    manifest = load_manifest()
    defaults = manifest.get("default_chunk_metadata", {})
    q = query.strip().lower()
    output: list[dict] = []
    for raw in _load_rows():
        chunk = merge_chunk_metadata(raw, defaults)
        haystack = " ".join(
            [
                str(chunk.get("chunk_id", "")),
                str(chunk.get("title", "")),
                str(chunk.get("subject", "")),
                str(chunk.get("content", "")),
                " ".join(str(tag) for tag in chunk.get("tags", [])),
            ]
        ).lower()
        if subject and subject not in str(chunk.get("subject", "")):
            continue
        if q and q not in haystack:
            continue
        content = str(chunk.get("content", ""))
        output.append(
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "title": str(chunk.get("title", "")),
                "subject": str(chunk.get("subject", "")),
                "content_preview": content[:220],
                "tags": [str(tag) for tag in chunk.get("tags", [])],
                "source_name": str(chunk.get("source_name", "")),
                "source_url": str(chunk.get("source_url", "")),
                "source_type": str(chunk.get("source_type", "")),
                "license": str(chunk.get("license", "")),
                "authority_level": str(chunk.get("authority_level", "")),
                "review_status": str(chunk.get("review_status", "")),
                "content_hash": str(chunk.get("content_hash", "")),
            }
        )
        if len(output) >= limit:
            break
    return output


def governance_report() -> dict:
    manifest = load_manifest()
    schema = load_schema()
    chunks = [merge_chunk_metadata(row, manifest.get("default_chunk_metadata", {})) for row in _load_rows()]
    failures = validate_knowledge_base()

    subjects = Counter(str(chunk.get("subject", "")) for chunk in chunks)
    sources = Counter(str(chunk.get("source_name", "")) for chunk in chunks)
    source_types = Counter(str(chunk.get("source_type", "")) for chunk in chunks)
    review_statuses = Counter(str(chunk.get("review_status", "")) for chunk in chunks)
    authority_levels = Counter(str(chunk.get("authority_level", "")) for chunk in chunks)
    hashes = [str(chunk.get("content_hash", "")) for chunk in chunks if chunk.get("content_hash")]

    return {
        "passed": not failures,
        "failures": failures,
        "manifest_version": manifest.get("version", ""),
        "schema_version": schema.get("version", ""),
        "policy": manifest.get("policy", {}),
        "allowed_sources": manifest.get("allowed_sources", []),
        "required_chunk_fields": manifest.get("required_chunk_fields", []),
        "allowed_review_statuses": manifest.get("allowed_review_statuses", []),
        "allowed_authority_levels": manifest.get("allowed_authority_levels", []),
        "metrics": {
            "chunk_count": len(chunks),
            "subject_count": len([key for key in subjects if key]),
            "source_count": len([key for key in sources if key]),
            "hash_coverage": round(len(hashes) / len(chunks), 4) if chunks else 0,
        },
        "breakdown": {
            "subjects": dict(subjects),
            "sources": dict(sources),
            "source_types": dict(source_types),
            "review_statuses": dict(review_statuses),
            "authority_levels": dict(authority_levels),
        },
        "sample_chunks": chunk_summaries(limit=10),
    }
