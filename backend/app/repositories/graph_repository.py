from __future__ import annotations
"""Graph repository — in-memory + SQL persistence for knowledge graphs."""

from typing import Dict,  List,  Optional

from datetime import datetime, timezone
from typing import Dict,  List,  Protocol
from uuid import UUID

from sqlalchemy import desc, select

from app.db.models import KnowledgeGraphModel
from app.db.session import SessionLocal
from app.schemas.graph import GraphData, ReviewStatus


class GraphRepository(Protocol):
    def save_graph(self, graph: GraphData, graph_id: str) -> str: ...
    def get_graph(self, graph_id: str) -> Optional[GraphData]: ...
    def list_graphs(self, course_id: Optional[str] = None, status: Optional[str] = None) -> List[dict]: ...
    def get_published_graph(self, course_id: str) -> Optional[GraphData]: ...
    def delete_graph(self, graph_id: str) -> bool: ...
    def update_status(self, graph_id: str, status: str) -> bool: ...


# ── In-Memory ─────────────────────────────────────────────────────────────

class InMemoryGraphRepository:
    def __init__(self) -> None:
        self._store: Dict[str, GraphData] = {}

    def save_graph(self, graph: GraphData, graph_id: str) -> str:
        self._store[graph_id] = graph
        return graph_id

    def get_graph(self, graph_id: str) -> Optional[GraphData]:
        return self._store.get(graph_id)

    def list_graphs(self, course_id: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
        results = []
        for gid, g in self._store.items():
            if course_id and g.metadata.course_id != course_id:
                continue
            if status and g.metadata.review_status.value != status:
                continue
            results.append({
                "graph_id": gid,
                "course_id": g.metadata.course_id,
                "course_name": g.metadata.course_name,
                "version": g.metadata.version,
                "review_status": g.metadata.review_status.value,
                "node_count": g.metadata.node_count,
                "edge_count": g.metadata.edge_count,
                "confidence": g.metadata.confidence,
                "generated_by": g.metadata.generated_by,
                "created_at": g.metadata.created_at,
                "updated_at": g.metadata.updated_at,
            })
        return results

    def get_published_graph(self, course_id: str) -> Optional[GraphData]:
        for g in self._store.values():
            if g.metadata.course_id == course_id and g.metadata.review_status == ReviewStatus.APPROVED:
                return g
        return None

    def delete_graph(self, graph_id: str) -> bool:
        return self._store.pop(graph_id, None) is not None

    def update_status(self, graph_id: str, status: str) -> bool:
        g = self._store.get(graph_id)
        if not g:
            return False
        g.metadata.review_status = ReviewStatus(status)
        g.metadata.updated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return True


# ── PostgreSQL ────────────────────────────────────────────────────────────

class PostgresGraphRepository:
    def save_graph(self, graph: GraphData, graph_id: str) -> str:
        with SessionLocal() as db:
            existing = db.scalar(
                select(KnowledgeGraphModel).where(KnowledgeGraphModel.graph_id == graph_id).limit(1)
            )
            if existing:
                existing.graph_json = graph.model_dump(mode="json")
                existing.node_count = graph.metadata.node_count
                existing.edge_count = graph.metadata.edge_count
                existing.confidence = graph.metadata.confidence
                existing.review_status = graph.metadata.review_status.value
                existing.course_name = graph.metadata.course_name
                existing.version = graph.metadata.version
                existing.generated_by = graph.metadata.generated_by
            else:
                db.add(KnowledgeGraphModel(
                    graph_id=graph_id,
                    course_id=graph.metadata.course_id,
                    course_name=graph.metadata.course_name,
                    version=graph.metadata.version,
                    review_status=graph.metadata.review_status.value,
                    graph_json=graph.model_dump(mode="json"),
                    node_count=graph.metadata.node_count,
                    edge_count=graph.metadata.edge_count,
                    confidence=graph.metadata.confidence,
                    generated_by=graph.metadata.generated_by,
                ))
            db.commit()
        return graph_id

    def get_graph(self, graph_id: str) -> Optional[GraphData]:
        with SessionLocal() as db:
            row = db.scalar(
                select(KnowledgeGraphModel).where(KnowledgeGraphModel.graph_id == graph_id).limit(1)
            )
            if not row:
                return None
            return GraphData.model_validate(row.graph_json)

    def list_graphs(self, course_id: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
        with SessionLocal() as db:
            stmt = select(KnowledgeGraphModel)
            if course_id:
                stmt = stmt.where(KnowledgeGraphModel.course_id == course_id)
            if status:
                stmt = stmt.where(KnowledgeGraphModel.review_status == status)
            stmt = stmt.order_by(desc(KnowledgeGraphModel.created_at)).limit(200)
            rows = db.scalars(stmt).all()
            return [
                {
                    "graph_id": r.graph_id,
                    "course_id": r.course_id,
                    "course_name": r.course_name,
                    "version": r.version,
                    "review_status": r.review_status,
                    "node_count": r.node_count,
                    "edge_count": r.edge_count,
                    "confidence": float(r.confidence) if r.confidence else None,
                    "generated_by": r.generated_by,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]

    def get_published_graph(self, course_id: str) -> Optional[GraphData]:
        with SessionLocal() as db:
            row = db.scalar(
                select(KnowledgeGraphModel)
                .where(
                    KnowledgeGraphModel.course_id == course_id,
                    KnowledgeGraphModel.review_status == "published",
                )
                .order_by(desc(KnowledgeGraphModel.version))
                .limit(1)
            )
            if not row:
                return None
            return GraphData.model_validate(row.graph_json)

    def delete_graph(self, graph_id: str) -> bool:
        with SessionLocal() as db:
            row = db.scalar(
                select(KnowledgeGraphModel).where(KnowledgeGraphModel.graph_id == graph_id).limit(1)
            )
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True

    def update_status(self, graph_id: str, status: str) -> bool:
        with SessionLocal() as db:
            row = db.scalar(
                select(KnowledgeGraphModel).where(KnowledgeGraphModel.graph_id == graph_id).limit(1)
            )
            if not row:
                return False
            row.review_status = status
            if status == "published":
                row.published_at = datetime.now(timezone.utc)
            db.commit()
            return True


# ── Auto-Switch ───────────────────────────────────────────────────────────

class AutoSwitchGraphRepository:
    def __init__(self) -> None:
        from app.core.config import get_settings
        backend = get_settings().repository_backend
        self.delegate: GraphRepository = (
            InMemoryGraphRepository() if backend == "memory" else PostgresGraphRepository()
        )

    def __getattr__(self, name):
        return getattr(self.delegate, name)


graph_repository: GraphRepository = AutoSwitchGraphRepository()
