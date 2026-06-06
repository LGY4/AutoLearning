from __future__ import annotations

from typing import List,  Optional

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.core.config import get_settings
from app.services import embedding_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    title: str
    subject: str
    content: str
    tags: tuple[str, ...]


DEFAULT_KNOWLEDGE_BASE: tuple[KnowledgeChunk, ...] = (
    KnowledgeChunk(
        chunk_id="kb_stack_001",
        title="栈的基本概念",
        subject="数据结构",
        content="栈是一种后进先出的线性数据结构，核心操作包括 push、pop 和 peek。",
        tags=("栈", "线性表", "后进先出"),
    ),
    KnowledgeChunk(
        chunk_id="kb_stack_002",
        title="栈的代码实现",
        subject="数据结构",
        content="用 Python 列表可以快速实现栈，append 对应入栈，pop 对应出栈。",
        tags=("栈", "Python", "代码实践"),
    ),
    KnowledgeChunk(
        chunk_id="kb_queue_001",
        title="队列与栈的对比",
        subject="数据结构",
        content="队列是先进先出结构，栈是后进先出结构，二者常用于不同的任务调度场景。",
        tags=("队列", "栈", "对比"),
    ),
)


def _knowledge_file() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"


@lru_cache(maxsize=1)
def load_knowledge_base() -> tuple[KnowledgeChunk, ...]:
    import logging
    path = _knowledge_file()
    if not path.exists():
        logging.getLogger(__name__).error("知识库文件缺失: %s — RAG 检索将不可用", path)
        return DEFAULT_KNOWLEDGE_BASE
    rows = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        KnowledgeChunk(
            chunk_id=str(row["chunk_id"]),
            title=str(row["title"]),
            subject=str(row["subject"]),
            content=str(row["content"]),
            tags=tuple(str(tag) for tag in row.get("tags", [])),
        )
        for row in rows
    )


def _score_chunk(chunk: KnowledgeChunk, query: str, subject: Optional[str]) -> float:
    """TF-IDF-like scoring: term frequency in chunk, title boost, subject match, exact match."""
    import re
    normalized = re.sub(r'[，。、；：！？\s]+', ' ', query)
    terms = [term for term in normalized.split() if len(term) >= 2]

    score = 0.1  # base score

    # Subject match bonus
    if subject and subject in chunk.subject:
        score += 0.25

    # Title match (higher weight)
    title_matches = sum(1 for term in terms if term in chunk.title)
    if title_matches:
        score += min(0.3, title_matches * 0.15)

    # Content match
    content_matches = sum(1 for term in terms if term in chunk.content)
    if content_matches:
        score += min(0.25, content_matches * 0.08)

    # Tag match
    tag_text = " ".join(chunk.tags)
    tag_matches = sum(1 for term in terms if term in tag_text)
    if tag_matches:
        score += min(0.15, tag_matches * 0.05)

    # Exact phrase match (highest signal)
    if query and (query in chunk.title or query in chunk.content):
        score += 0.2

    return min(score, 0.99)


def _memory_search(query: str, subject: Optional[str], top_k: int) -> List[dict]:
    scored = sorted(
        ((_score_chunk(chunk, query, subject), chunk) for chunk in load_knowledge_base()),
        key=lambda item: item[0],
        reverse=True,
    )
    return [
        {
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "content": chunk.content,
            "subject": chunk.subject,
            "score": round(score, 2),
            "retrieval_engine": "memory_fallback",
            "tags": list(chunk.tags),
        }
        for score, chunk in scored[:top_k]
    ]


def _chunk_embedding_text(chunk: KnowledgeChunk) -> str:
    return f"{chunk.title} {chunk.content} {' '.join(chunk.tags)}"


def _chunk_business_id(chunk: KnowledgeChunk):
    return uuid5(NAMESPACE_URL, f"autolearning:knowledge:{chunk.chunk_id}")


def _sync_embedding_index(chunks: tuple[KnowledgeChunk, ...]) -> dict:
    try:
        from sqlalchemy import select

        from app.db.models import EmbeddingIndex
        from app.db.session import SessionLocal
    except Exception as exc:
        return {"synced": 0, "skipped": len(chunks), "error": str(exc)}

    settings = get_settings()
    embedding_status = embedding_service.get_embedding_status()
    synced = 0
    try:
        with SessionLocal() as db:
            for chunk in chunks:
                business_id = _chunk_business_id(chunk)
                existing = db.scalar(
                    select(EmbeddingIndex)
                    .where(
                        EmbeddingIndex.business_type == "knowledge_chunk",
                        EmbeddingIndex.business_id == business_id,
                        EmbeddingIndex.version_no == 1,
                    )
                    .limit(1)
                )
                if existing and existing.embedding_model == str(embedding_status["active_mode"]):
                    continue
                text_hash = hashlib.sha256(_chunk_embedding_text(chunk).encode("utf-8")).hexdigest()
                if existing:
                    existing.collection_name = settings.chroma_collection
                    existing.embedding_id = chunk.chunk_id
                    existing.text_hash = text_hash
                    existing.embedding_model = str(embedding_status["active_mode"])
                    existing.vector_status = "active"
                else:
                    db.add(
                        EmbeddingIndex(
                            business_type="knowledge_chunk",
                            business_id=business_id,
                            collection_name=settings.chroma_collection,
                            embedding_id=chunk.chunk_id,
                            text_hash=text_hash,
                            embedding_model=str(embedding_status["active_mode"]),
                            vector_status="active",
                            version_no=1,
                        )
                    )
                synced += 1
            db.commit()
        return {"synced": synced, "skipped": len(chunks) - synced}
    except Exception as exc:
        return {"synced": synced, "skipped": len(chunks) - synced, "error": str(exc)}


_chroma_collection_cache = None


def _get_chroma_collection():
    global _chroma_collection_cache
    if _chroma_collection_cache is not None:
        return _chroma_collection_cache

    settings = get_settings()
    if settings.rag_backend == "memory":
        return None
    try:
        import chromadb
    except ModuleNotFoundError:
        return None

    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    collection = client.get_or_create_collection(settings.chroma_collection)
    chunks = load_knowledge_base()
    existing_ids = set(collection.get().get("ids", []))
    missing = [chunk for chunk in chunks if chunk.chunk_id not in existing_ids]
    if missing:
        collection.add(
            ids=[chunk.chunk_id for chunk in missing],
            documents=[chunk.content for chunk in missing],
            embeddings=[embedding_service.embed_text(_chunk_embedding_text(chunk)) for chunk in missing],
            metadatas=[
                {
                    "title": chunk.title,
                    "subject": chunk.subject,
                    "tags": ",".join(chunk.tags),
                }
                for chunk in missing
            ],
        )
    _chroma_collection_cache = collection
    return collection


def _chroma_search(query: str, subject: Optional[str], top_k: int) -> Optional[List[dict]]:
    collection = _get_chroma_collection()
    if collection is None:
        return None

    # Skip vector search when using deterministic fallback embeddings —
    # they have no semantic meaning and produce random results.
    # Fall back to keyword-based memory search instead.
    embedding_status = embedding_service.get_embedding_status()
    if embedding_status.get("active_mode") == "deterministic_fallback":
        return None

    results = collection.query(query_embeddings=[embedding_service.embed_text(query)], n_results=top_k)
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0] or [0.0] * len(ids)

    output: List[dict] = []
    for chunk_id, content, metadata, distance in zip(ids, docs, metadatas, distances):
        score = round(max(0.0, 1.0 - float(distance)), 2)
        if subject:
            chunk_subject = metadata.get("subject", "")
            if chunk_subject == subject:
                score = min(1.0, score + 0.15)
            elif subject in chunk_subject or chunk_subject in subject:
                score = min(1.0, score + 0.08)
        output.append(
            {
                "chunk_id": chunk_id,
                "title": metadata.get("title", chunk_id),
                "content": content,
                "subject": metadata.get("subject"),
                "score": score,
                "retrieval_engine": "chroma",
                "tags": str(metadata.get("tags", "")).split(",") if metadata.get("tags") else [],
            }
        )
    output.sort(key=lambda x: x["score"], reverse=True)
    return output[:top_k]


def rebuild_knowledge_index(force: bool = False) -> dict:
    """Create or refresh the local Chroma collection from versioned JSON data."""
    global _chroma_collection_cache
    settings = get_settings()
    # Clear the knowledge base cache to reload from file
    load_knowledge_base.cache_clear()
    chunks = load_knowledge_base()
    embedding_status = embedding_service.get_embedding_status()
    if settings.rag_backend == "memory":
        return {
            "engine": "memory_fallback",
            "indexed_chunks": len(chunks),
            "embedding": embedding_status,
            "forced": force,
        }
    try:
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        if force:
            try:
                client.delete_collection(settings.chroma_collection)
            except Exception:
                pass
            _chroma_collection_cache = None
        collection = _get_chroma_collection()
        index_sync = _sync_embedding_index(chunks)
        return {
            "engine": "chroma",
            "collection": settings.chroma_collection,
            "indexed_chunks": collection.count() if collection else 0,
            "embedding_index": index_sync,
            "embedding": embedding_status,
            "forced": force,
        }
    except Exception as exc:
        _chroma_collection_cache = None
        raise RuntimeError(f"Chroma rebuild failed: {exc}") from exc


def knowledge_status() -> dict:
    chunks = load_knowledge_base()
    settings = get_settings()
    status = {
        "configured_backend": settings.rag_backend,
        "knowledge_file": str(_knowledge_file()),
        "source_chunks": len(chunks),
        "subjects": sorted({chunk.subject for chunk in chunks}),
        "embedding": embedding_service.get_embedding_status(),
    }
    try:
        collection = _get_chroma_collection()
        status["active_engine"] = "chroma" if collection else "unavailable"
        status["indexed_chunks"] = collection.count() if collection else 0
    except Exception as exc:
        status["active_engine"] = "unavailable"
        status["indexed_chunks"] = 0
        status["error"] = str(exc)
    return status


def _apply_profile_boost(results: List[dict], profile) -> List[dict]:
    """Boost RAG results that match the student's weak topics."""
    weak_topics = set(getattr(profile.knowledge_profile, "weak_topics", []) or [])
    if not weak_topics:
        return results

    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")
        tags = r.get("tags", [])
        tag_text = " ".join(tags) if isinstance(tags, list) else ""
        combined = f"{title} {content} {tag_text}"
        for topic in weak_topics:
            if topic and topic in combined:
                r["score"] = min(0.99, r.get("score", 0) + 0.3)
                break

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


_reranker_model = None


def _get_reranker():
    """Lazy-load cross-encoder reranker model."""
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model
    try:
        from sentence_transformers import CrossEncoder
        # Use a lightweight Chinese cross-encoder
        _reranker_model = CrossEncoder("BAAI/bge-reranker-base", max_length=512, device="cpu")
        logger.info("Cross-encoder reranker loaded")
    except Exception as exc:
        logger.warning("Reranker unavailable: %s", exc)
        _reranker_model = False
    return _reranker_model


def _rerank_results(query: str, results: List[dict], top_k: int) -> List[dict]:
    """Rerank results using cross-encoder model for better relevance."""
    if len(results) <= 1:
        return results

    reranker = _get_reranker()
    if reranker is False or reranker is None:
        return results[:top_k]

    try:
        # Build query-document pairs
        pairs = [(query, f"{r.get('title', '')} {r.get('content', '')[:300]}") for r in results]
        scores = reranker.predict(pairs)

        # Combine reranker scores with original scores
        for i, r in enumerate(results):
            original = r.get("score", 0)
            rerank_score = float(scores[i])
            # Weighted combination: 60% reranker + 40% original
            r["score"] = round(min(0.99, 0.4 * original + 0.6 * rerank_score), 2)
            r["retrieval_engine"] = r.get("retrieval_engine", "unknown") + "+rerank"

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    except Exception:
        logger.debug("Reranking failed, using original order", exc_info=True)
        return results[:top_k]


def _tokenize_chinese(text: str) -> List[str]:
    """Tokenize Chinese text using jieba, with fallback to character split."""
    try:
        import jieba
        tokens = list(jieba.cut(text))
        # Filter: min length 1 for Chinese chars, 2 for ASCII
        return [t.strip() for t in tokens if len(t.strip()) >= 1 and not t.strip().isascii() or len(t.strip()) >= 2]
    except ImportError:
        # Fallback: split on punctuation and spaces
        import re
        normalized = re.sub(r'[，。、；：！？\s\(\)（）\[\]【】{}]+', ' ', text)
        return [t for t in normalized.split() if len(t) >= 2]


def _bm25_search(query: str, subject: Optional[str], top_k: int) -> List[dict]:
    """BM25 keyword search over the knowledge base with Chinese tokenization."""
    import math

    chunks = load_knowledge_base()
    if not chunks:
        return []

    # Tokenize query with jieba
    query_terms = _tokenize_chinese(query)
    if not query_terms:
        return []

    # BM25 parameters
    k1, b = 1.5, 0.75
    avg_dl = sum(len(c.content) for c in chunks) / len(chunks)
    n_docs = len(chunks)

    # Tokenize all chunks and compute IDF
    chunk_tokens = []
    for c in chunks:
        text = f"{c.title} {c.content} {' '.join(c.tags)}"
        chunk_tokens.append(_tokenize_chinese(text))

    avg_dl = sum(len(t) for t in chunk_tokens) / len(chunk_tokens) if chunk_tokens else 1

    # Compute IDF for each query term
    idf = {}
    for term in query_terms:
        df = sum(1 for tokens in chunk_tokens if term in tokens or any(term in t for t in tokens))
        idf[term] = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)

    # Score each chunk
    scored = []
    for chunk, tokens in zip(chunks, chunk_tokens):
        dl = len(tokens)
        tf_sum = 0
        token_text = " ".join(tokens)
        for term in query_terms:
            # Count term occurrences in tokenized text
            tf = token_text.count(term) if len(term) > 1 else sum(1 for t in tokens if t == term)
            if tf > 0:
                tf_sum += idf[term] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))

        # Subject bonus
        if subject and subject in chunk.subject:
            tf_sum *= 1.3

        if tf_sum > 0:
            scored.append((tf_sum, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    max_score = scored[0][0] if scored else 1.0

    return [
        {
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "content": chunk.content,
            "subject": chunk.subject,
            "score": round(min(0.99, score / max_score * 0.95), 2),
            "retrieval_engine": "bm25",
            "tags": list(chunk.tags),
        }
        for score, chunk in scored[:top_k]
    ]


def _rrf_fusion(vector_results: List[dict], bm25_results: List[dict], top_k: int, k: int = 60) -> List[dict]:
    """Reciprocal Rank Fusion: combine vector and BM25 results."""
    rrf_scores: dict[str, float] = {}
    result_map: dict[str, dict] = {}

    for rank, r in enumerate(vector_results):
        cid = r["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (k + rank + 1)
        result_map[cid] = r

    for rank, r in enumerate(bm25_results):
        cid = r["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (k + rank + 1)
        if cid not in result_map:
            result_map[cid] = r

    # Sort by RRF score
    sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    results = []
    for cid in sorted_ids[:top_k]:
        r = result_map[cid].copy()
        r["score"] = round(min(0.99, rrf_scores[cid] * 10), 2)  # normalize to 0-1
        r["retrieval_engine"] = "hybrid_rrf"
        results.append(r)
    return results


def search_knowledge(query: str, subject: Optional[str] = None, top_k: int = 5, profile=None, user_id=None) -> List[dict]:
    """Search knowledge base with hybrid retrieval (vector + BM25 + RRF fusion)."""
    results: List[dict] = []

    # 1. Search user's personal knowledge base first (higher priority)
    if user_id:
        try:
            from app.services.document_ingestion import search_user_knowledge
            user_results = search_user_knowledge(user_id, query, top_k=top_k)
            if user_results:
                for r in user_results:
                    r["score"] = min(0.99, r.get("score", 0) + 0.1)  # boost user docs
                results.extend(user_results)
        except Exception:
            pass

    # 2. Hybrid search on system knowledge base
    remaining = top_k - len(results)
    if remaining > 0:
        if get_settings().rag_backend == "memory":
            system_results = _memory_search(query, subject, remaining)
        else:
            # Hybrid: vector + BM25 + RRF fusion
            vector_results = _chroma_search(query, subject, remaining * 2) or []
            bm25_results = _bm25_search(query, subject, remaining * 2)

            if vector_results and bm25_results:
                system_results = _rrf_fusion(vector_results, bm25_results, remaining)
            elif vector_results:
                system_results = vector_results[:remaining]
            elif bm25_results:
                system_results = bm25_results[:remaining]
            else:
                system_results = _memory_search(query, subject, remaining)
        results.extend(system_results)

    if profile is not None:
        results = _apply_profile_boost(results, profile)

    # Deduplicate
    seen: set = set()
    deduped: List[dict] = []
    for r in results:
        cid = r.get("chunk_id", "")
        if cid not in seen:
            seen.add(cid)
            deduped.append(r)

    # Rerank with cross-encoder for better relevance
    deduped = _rerank_results(query, deduped, top_k)
    return deduped


def search_knowledge_with_graph(query: str, subject: Optional[str] = None, top_k: int = 5, profile=None, user_id=None) -> List[dict]:
    """Search knowledge with graph-aware context expansion.

    After initial RAG retrieval, finds which knowledge graph nodes contain
    the matched chunks and adds sibling chunks from the same node for
    broader context.
    """
    initial = search_knowledge(query, subject, top_k, profile=profile, user_id=user_id)
    if not initial:
        return initial

    try:
        from app.services import graph_service
        graph = graph_service.get_full_graph()
    except Exception:
        return initial

    if not graph or not graph.get("nodes"):
        return initial

    # Build chunk_id -> node mapping
    initial_ids = {r["chunk_id"] for r in initial}
    chunk_to_node: dict[str, dict] = {}
    for node in graph["nodes"]:
        for cid in node.get("chunk_ids", []):
            chunk_to_node[cid] = node

    # Find sibling chunks from matched nodes
    expanded: List[dict] = []
    seen_node_ids: set[str] = set()
    for result in initial:
        node = chunk_to_node.get(result["chunk_id"])
        if not node or node["id"] in seen_node_ids:
            continue
        seen_node_ids.add(node["id"])
        for sibling_cid in node.get("chunk_ids", []):
            if sibling_cid not in initial_ids:
                # Look up the chunk content from the knowledge base
                chunks = load_knowledge_base()
                for chunk in chunks:
                    if chunk.chunk_id == sibling_cid:
                        expanded.append({
                            "chunk_id": sibling_cid,
                            "title": chunk.title,
                            "content": chunk.content,
                            "subject": chunk.subject,
                            "score": round(result["score"] * 0.7, 2),
                            "retrieval_engine": "graph_expand",
                            "tags": list(chunk.tags),
                        })
                        break

    # Merge, deduplicate, cap
    combined = initial + expanded
    seen: set[str] = set()
    deduped: List[dict] = []
    for item in combined:
        if item["chunk_id"] not in seen:
            seen.add(item["chunk_id"])
            deduped.append(item)
    deduped.sort(key=lambda x: x["score"], reverse=True)
    return deduped[:top_k * 2]
