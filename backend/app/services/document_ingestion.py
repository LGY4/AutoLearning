from __future__ import annotations
"""Document Ingestion Service — chunks documents, generates embeddings, stores in ChromaDB.

Supports both system knowledge base and user-uploaded documents.
User documents are stored with user_id metadata for scoped retrieval.
"""

import hashlib
import logging
import re
from typing import List, Optional
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.services import embedding_service

logger = logging.getLogger(__name__)

# Chunking parameters
MAX_CHUNK_SIZE = 500  # characters per chunk
MIN_CHUNK_SIZE = 50
OVERLAP_SIZE = 50  # character overlap between chunks


def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE, overlap: int = OVERLAP_SIZE) -> List[str]:
    """Split text into overlapping chunks by paragraphs, then by sentences if needed."""
    if not text or not text.strip():
        return []

    # First split by paragraphs
    paragraphs = re.split(r'\n\s*\n', text.strip())
    chunks: List[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) <= max_size:
            if len(para) >= MIN_CHUNK_SIZE:
                chunks.append(para)
            elif chunks:
                # Merge small paragraph with previous chunk
                if len(chunks[-1]) + len(para) + 1 <= max_size:
                    chunks[-1] = chunks[-1] + "\n" + para
                else:
                    chunks.append(para)
            else:
                chunks.append(para)
        else:
            # Split long paragraphs by sentences
            sentences = re.split(r'(?<=[。！？.!?\n])\s*', para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= max_size:
                    current = current + " " + sent if current else sent
                else:
                    if current:
                        chunks.append(current.strip())
                    current = sent
            if current and len(current) >= MIN_CHUNK_SIZE:
                chunks.append(current.strip())

    # Add overlap
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            overlapped.append(prev_tail + " " + chunks[i])
        chunks = overlapped

    return [c for c in chunks if c.strip()]


def ingest_document(
    user_id: UUID,
    title: str,
    content: str,
    subject: str = "通用",
    tags: Optional[List[str]] = None,
    source: str = "user_upload",
    deduplicate: bool = True,
) -> dict:
    """Chunk a document, generate embeddings, and store in ChromaDB.

    Returns:
        {"chunks_created": int, "collection": str, "chunk_ids": list}
    """
    settings = get_settings()

    # Deduplication: if a document with the same title exists, delete it first
    if deduplicate:
        try:
            existing = list_user_documents(user_id)
            if any(d["title"] == title for d in existing):
                logger.info("Document '%s' already exists for user %s, replacing", title, user_id)
                delete_user_document(user_id, title)
        except Exception:
            pass

    chunks = chunk_text(content)

    if not chunks:
        return {"chunks_created": 0, "collection": "", "chunk_ids": []}

    # Generate chunk IDs
    chunk_ids = [f"user_{user_id}_{uuid4().hex[:8]}" for _ in chunks]

    # Generate embeddings
    embeddings = []
    for chunk in chunks:
        embed_text = f"{title} {chunk} {' '.join(tags or [])}"
        embeddings.append(embedding_service.embed_text(embed_text))

    # Store in ChromaDB
    collection_name = f"user_{user_id}"
    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = client.get_or_create_collection(collection_name)

        metadatas = [
            {
                "title": title,
                "subject": subject,
                "tags": ",".join(tags or []),
                "source": source,
                "user_id": str(user_id),
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            for i in range(len(chunks))
        ]

        collection.add(
            ids=chunk_ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info("Ingested %d chunks for user %s, title='%s'", len(chunks), user_id, title)
        return {
            "chunks_created": len(chunks),
            "collection": collection_name,
            "chunk_ids": chunk_ids,
        }
    except Exception as exc:
        logger.error("Failed to ingest document: %s", exc)
        return {"chunks_created": 0, "collection": "", "chunk_ids": [], "error": str(exc)}


def search_user_knowledge(
    user_id: UUID,
    query: str,
    top_k: int = 5,
) -> Optional[List[dict]]:
    """Search a user's personal knowledge base."""
    settings = get_settings()
    collection_name = f"user_{user_id}"

    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return None

        if collection.count() == 0:
            return None

        # Skip if using fallback embeddings
        embedding_status = embedding_service.get_embedding_status()
        if embedding_status.get("active_mode") == "deterministic_fallback":
            return None

        query_embedding = embedding_service.embed_text(query)
        results = collection.query(query_embeddings=[query_embedding], n_results=min(top_k, collection.count()))

        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] or [0.0] * len(ids)

        output = []
        for chunk_id, content, metadata, distance in zip(ids, docs, metadatas, distances):
            score = round(max(0.0, 1.0 - float(distance)), 2)
            content_hash = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
            source = metadata.get("source", "user_upload")
            provenance = {
                "source_name": metadata.get("title", "") or "User uploaded document",
                "source_url": "",
                "source_type": "user_upload",
                "license": "user_provided",
                "version": "",
                "retrieved_at": "",
                "content_hash": content_hash,
                "authority_level": "user_provided",
                "review_status": "user_owned",
                "reviewer": "",
                "language": "",
                "audience": "",
                "difficulty": "",
            }
            output.append({
                "chunk_id": chunk_id,
                "title": metadata.get("title", ""),
                "content": content,
                "subject": metadata.get("subject", ""),
                "score": score,
                "retrieval_engine": "user_chroma",
                "tags": str(metadata.get("tags", "")).split(",") if metadata.get("tags") else [],
                "source": source,
                **provenance,
                "provenance": provenance,
            })

        output.sort(key=lambda x: x["score"], reverse=True)
        return output[:top_k]
    except Exception as exc:
        logger.debug("User knowledge search failed: %s", exc)
        return None


def list_user_documents(user_id: UUID) -> List[dict]:
    """List all documents in a user's knowledge base."""
    settings = get_settings()
    collection_name = f"user_{user_id}"

    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return []

        if collection.count() == 0:
            return []

        all_data = collection.get()
        ids = all_data.get("ids", [])
        metadatas = all_data.get("metadatas", [])

        # Group by title (each document produces multiple chunks)
        docs: dict[str, dict] = {}
        for chunk_id, meta in zip(ids, metadatas):
            title = meta.get("title", "未命名")
            if title not in docs:
                docs[title] = {
                    "title": title,
                    "subject": meta.get("subject", ""),
                    "source": meta.get("source", ""),
                    "chunk_count": 0,
                    "tags": str(meta.get("tags", "")).split(",") if meta.get("tags") else [],
                }
            docs[title]["chunk_count"] += 1

        return list(docs.values())
    except Exception:
        return []


def delete_user_document(user_id: UUID, title: str) -> bool:
    """Delete all chunks of a document from a user's knowledge base."""
    settings = get_settings()
    collection_name = f"user_{user_id}"

    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return False

        # Find chunks with matching title
        all_data = collection.get()
        ids_to_delete = []
        for chunk_id, meta in zip(all_data.get("ids", []), all_data.get("metadatas", [])):
            if meta.get("title") == title:
                ids_to_delete.append(chunk_id)

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            logger.info("Deleted %d chunks for title='%s' from user %s", len(ids_to_delete), title, user_id)
            return True
        return False
    except Exception:
        return False


def get_user_knowledge_stats(user_id: UUID) -> dict:
    """Get statistics about a user's knowledge base."""
    settings = get_settings()
    collection_name = f"user_{user_id}"

    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return {"total_chunks": 0, "documents": 0, "collection": collection_name}

        total = collection.count()
        docs = list_user_documents(user_id)
        return {
            "total_chunks": total,
            "documents": len(docs),
            "collection": collection_name,
        }
    except Exception:
        return {"total_chunks": 0, "documents": 0, "collection": collection_name}
