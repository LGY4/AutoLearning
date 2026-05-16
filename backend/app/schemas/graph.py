from __future__ import annotations
"""Knowledge graph schemas — unified format for GraphBuilderAgent output."""

from typing import Dict,  List,  Optional

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "published"
    REJECTED = "rejected"


class SourceRef(BaseModel):
    """Provenance tracking — where this node/edge came from."""
    type: str  # "outline" | "document" | "knowledge_base" | "search" | "llm_infer"
    ref: str  # file path, URL, chunk_id, or description
    confidence: float = 0.8


class GraphNode(BaseModel):
    id: str
    name: str
    level: int = 1
    subject: str = ""
    chunk_ids: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    description: str = ""
    # New fields
    related_chunks: List[str] = Field(default_factory=list)
    source_refs: List[SourceRef] = Field(default_factory=list)
    confidence: float = 0.8
    tags: List[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str = "prerequisite"  # "prerequisite" | "corequisite" | "related"
    confidence: float = 0.8
    source_refs: List[SourceRef] = Field(default_factory=list)


class GraphMetadata(BaseModel):
    course_id: str = ""
    course_name: str = ""
    version: int = 1
    generated_by: str = "graph_builder_agent"  # "graph_builder_agent" | "manual" | "import"
    review_status: ReviewStatus = ReviewStatus.DRAFT
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    source_summary: List[SourceRef] = Field(default_factory=list)
    confidence: float = 0.8
    node_count: int = 0
    edge_count: int = 0


class GraphData(BaseModel):
    """Unified knowledge graph schema."""
    metadata: GraphMetadata
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    learning_paths: Dict[str, List[str]] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class GraphBuildRequest(BaseModel):
    course_name: str
    course_id: str = ""
    outline: Optional[str] = None  # course outline text
    documents: List[str] = Field(default_factory=list)  # file paths or text content
    search_queries: List[str] = Field(default_factory=list)  # optional search topics
    existing_graph: Optional[GraphData] = None  # merge with existing
    max_nodes: int = 30
    version: int = 1


class GraphPublishRequest(BaseModel):
    graph_id: str
    course_id: str
    approved_by: str = "admin"
