from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MODEL_PROVIDER"] = "mock"
os.environ["RAG_BACKEND"] = "memory"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services import rag_service
from scripts.validate_knowledge_base import validate_knowledge_base


def test_knowledge_search_returns_governed_provenance() -> None:
    rag_service.load_knowledge_base.cache_clear()
    results = rag_service.search_knowledge("stack", top_k=1)

    assert results
    result = results[0]
    assert result["source"] == "system_knowledge"
    assert result["source_name"]
    assert result["source_url"].startswith("https://")
    assert result["authority_level"] in {"official", "open_textbook", "curated_seed"}
    assert result["review_status"] in {"approved", "reviewed"}
    assert result["provenance"]["content_hash"]


def test_system_knowledge_manifest_validation_passes() -> None:
    assert validate_knowledge_base() == []
