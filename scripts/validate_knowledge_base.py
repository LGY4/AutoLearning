from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "backend" / "app" / "data" / "knowledge_base.json"
MANIFEST_PATH = ROOT / "backend" / "app" / "data" / "system_kb_manifest.json"
SCHEMA_PATH = ROOT / "backend" / "app" / "data" / "system_kb_schema.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _merged_chunk(row: dict, defaults: dict) -> dict:
    merged = dict(row)
    for key, value in defaults.items():
        merged.setdefault(key, value)
    merged.setdefault("content_hash", _sha256(str(merged.get("content", ""))))
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

    manifest = _load_json(MANIFEST_PATH)
    schema = _load_json(SCHEMA_PATH)
    rows = _load_json(KB_PATH)
    defaults = manifest.get("default_chunk_metadata", {})
    required = manifest.get("required_chunk_fields", [])
    schema_required = schema.get("$defs", {}).get("chunk", {}).get("required", [])
    allowed_review = set(manifest.get("allowed_review_statuses", []))
    allowed_authority = set(manifest.get("allowed_authority_levels", []))
    allowed_sources = manifest.get("allowed_sources", [])
    source_prefixes = {
        source.get("source_name"): source.get("url_prefixes", [])
        for source in allowed_sources
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
        chunk = _merged_chunk(raw, defaults)
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

        expected_hash = _sha256(str(chunk.get("content", "")))
        actual_hash = str(chunk.get("content_hash", ""))
        if raw.get("content_hash") and actual_hash != expected_hash:
            failures.append(f"{chunk_id}: content_hash does not match content")

    return failures


def main() -> None:
    failures = validate_knowledge_base()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Knowledge base governance validation passed.")


if __name__ == "__main__":
    main()
