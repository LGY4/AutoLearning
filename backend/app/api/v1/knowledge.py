from __future__ import annotations

from typing import List,  Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.enums import UserRole
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.graph import GraphBuildRequest, GraphData, GraphPublishRequest, ReviewStatus
from app.services import graph_builder_agent, graph_diff, graph_service, graph_validator, rag_service
from app.services.file_parser import parse_uploaded_file
from app.repositories.graph_repository import graph_repository


class KnowledgeSearchRequest(BaseModel):
    query: str
    subject: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=10)


class KnowledgeRebuildRequest(BaseModel):
    force: bool = False


router = APIRouter()


def _require_admin(current_user: UserDTO) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="管理员权限不足")


@router.post("/search", response_model=ApiResponse[dict])
def search(payload: KnowledgeSearchRequest) -> ApiResponse[dict]:
    return success(
        {
            "query": payload.query,
            "subject": payload.subject,
            "results": rag_service.search_knowledge(payload.query, payload.subject, payload.top_k),
        }
    )


@router.get("/search", response_model=ApiResponse[dict])
def search_get(q: str, subject: Optional[str] = None, top_k: int = 5) -> ApiResponse[dict]:
    return success(
        {
            "query": q,
            "subject": subject,
            "results": rag_service.search_knowledge(q, subject, top_k),
        }
    )


@router.get("/status", response_model=ApiResponse[dict])
def status() -> ApiResponse[dict]:
    return success(rag_service.knowledge_status())


# ── User Knowledge Base ─────────────────────────────────────────────

@router.post("/upload", response_model=ApiResponse[dict])
async def upload_to_knowledge_base(
    title: str,
    file: UploadFile = File(...),
    subject: str = "通用",
    tags: Optional[str] = None,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Upload a document to the user's personal knowledge base.

    The document is chunked, embedded, and stored in ChromaDB for RAG retrieval.
    """
    from app.services.document_ingestion import ingest_document
    from app.services.file_parser import parse_uploaded_file

    content = await file.read()
    parsed = parse_uploaded_file(file.filename, content)
    if not parsed.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    result = ingest_document(
        user_id=current_user.id,
        title=title or file.filename or "未命名文档",
        content=parsed,
        subject=subject,
        tags=tag_list,
        source="user_upload",
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    return success(result)


@router.get("/my-documents", response_model=ApiResponse[list])
def list_my_documents(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[list]:
    """List all documents in the user's personal knowledge base."""
    from app.services.document_ingestion import list_user_documents
    return success(list_user_documents(current_user.id))


@router.delete("/my-documents/{title}", response_model=ApiResponse[dict])
def delete_my_document(title: str, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Delete a document from the user's personal knowledge base."""
    from app.services.document_ingestion import delete_user_document
    deleted = delete_user_document(current_user.id, title)
    return success({"deleted": deleted, "title": title})


@router.get("/my-stats", response_model=ApiResponse[dict])
def my_knowledge_stats(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Get statistics about the user's personal knowledge base."""
    from app.services.document_ingestion import get_user_knowledge_stats
    return success(get_user_knowledge_stats(current_user.id))


@router.post("/rebuild", response_model=ApiResponse[dict])
def rebuild(payload: KnowledgeRebuildRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _require_admin(current_user)
    return success(rag_service.rebuild_knowledge_index(force=payload.force))


# ── Knowledge Graph endpoints ─────────────────────────────────────────────


@router.get("/graph", response_model=ApiResponse[dict])
def get_graph() -> ApiResponse[dict]:
    """Return the full knowledge graph with enriched node data."""
    return success(graph_service.get_full_graph())


@router.get("/graph/node/{node_id}", response_model=ApiResponse[dict])
def get_graph_node(node_id: str) -> ApiResponse[dict]:
    node = graph_service.get_node_with_context(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return success(node)


@router.get("/graph/prerequisites/{node_id}", response_model=ApiResponse[list])
def get_prerequisites(node_id: str) -> ApiResponse[list]:
    return success(graph_service.get_prerequisites(node_id))


@router.get("/graph/path/{level}", response_model=ApiResponse[list])
def get_learning_path(level: str) -> ApiResponse[list]:
    return success(graph_service.get_learning_path(level))


@router.get("/graph/topology", response_model=ApiResponse[list])
def get_topology() -> ApiResponse[list]:
    return success(graph_service.topological_sort())


@router.get("/graph/with-path", response_model=ApiResponse[dict])
def get_graph_with_path(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Return the knowledge graph enriched with the user's current learning path status."""
    graph = graph_service.get_full_graph()

    from app.repositories.vertical_loop_repository import repository
    path = repository.get_path(current_user.id)

    # Build a map from knowledge_point name -> path node status
    path_status_map: dict[str, dict] = {}
    path_info = None
    if path:
        path_info = {
            "path_id": str(path.path_id),
            "title": path.title,
            "goal": path.goal,
            "status": path.status,
            "completed_count": sum(1 for n in path.nodes if n.status.value == "completed"),
            "total_count": len(path.nodes),
        }
        for node in path.nodes:
            path_status_map[node.knowledge_point] = {
                "node_id": str(node.node_id),
                "order": node.order,
                "status": node.status.value,
                "estimated_minutes": node.estimated_minutes,
            }

    # Enrich graph nodes with path_status
    nodes = graph.get("nodes", [])
    for n in nodes:
        n["path_status"] = path_status_map.get(n["name"])

    return success({"graph": graph, "path": path_info})


# ── Graph Builder endpoints (with DB persistence) ────────────────────────


@router.post("/graphs/build", response_model=ApiResponse[dict])
def build_graph(payload: GraphBuildRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Build a knowledge graph from provided sources. Returns draft + validation."""
    _require_admin(current_user)
    graph, validation = graph_builder_agent.build_and_validate(payload)

    graph_id = f"{graph.metadata.course_id}_v{graph.metadata.version}"
    graph_repository.save_graph(graph, graph_id)

    return success({
        "graph_id": graph_id,
        "graph": graph.model_dump(mode="json"),
        "validation": validation,
    })


@router.post("/graphs/upload-build", response_model=ApiResponse[dict])
async def upload_and_build(
    course_name: str = "",
    course_id: str = "",
    max_nodes: int = 30,
    files: List[UploadFile] = File(...),
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Upload PDF/Markdown/text files and build a graph from their content."""
    _require_admin(current_user)
    import asyncio

    documents: List[str] = []
    for f in files:
        content = await f.read()
        try:
            text = parse_uploaded_file(f.filename or "unknown", content)
            documents.append(text)
        except Exception as e:
            documents.append(f"[解析失败: {f.filename} — {e}]")

    request = GraphBuildRequest(
        course_name=course_name,
        course_id=course_id,
        documents=documents,
        max_nodes=max_nodes,
    )
    # Run blocking LLM call in thread pool to avoid blocking the event loop
    graph, validation = await asyncio.to_thread(graph_builder_agent.build_and_validate, request)

    graph_id = f"{graph.metadata.course_id}_v{graph.metadata.version}"
    graph_repository.save_graph(graph, graph_id)

    return success({
        "graph_id": graph_id,
        "graph": graph.model_dump(mode="json"),
        "validation": validation,
        "files_parsed": [f.filename for f in files],
    })


@router.post("/graphs/validate", response_model=ApiResponse[dict])
def validate_graph_endpoint(payload: GraphData) -> ApiResponse[dict]:
    """Validate a graph without saving."""
    result = graph_validator.validate_graph(payload)
    return success(result.model_dump())


@router.post("/graphs/publish", response_model=ApiResponse[dict])
def publish_graph(payload: GraphPublishRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Publish a draft graph. Requires prior validation."""
    graph = graph_repository.get_graph(payload.graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Draft graph '{payload.graph_id}' not found")

    validation = graph_validator.validate_graph(graph)
    if not validation.valid:
        return success({
            "error": "Graph has validation errors, cannot publish",
            "validation": validation.model_dump(),
        })

    # Check if there's an existing published graph for this course — diff first
    existing_published = graph_repository.get_published_graph(payload.course_id)
    diff_result = None
    if existing_published:
        diff_result = graph_diff.diff_graphs(existing_published, graph)

    # Mark as published and save to file + DB
    graph.metadata.review_status = ReviewStatus.APPROVED
    published = graph_builder_agent.publish_graph(graph)
    graph_repository.save_graph(graph, payload.graph_id)
    graph_repository.update_status(payload.graph_id, "published")

    # Reload graph_service cache
    graph_service.load_graph.cache_clear()

    return success({
        "status": "published",
        "graph": published.model_dump(mode="json"),
        "diff": diff_result,
    })


@router.get("/graphs", response_model=ApiResponse[list])
def list_graphs(course_id: Optional[str] = None, status: Optional[str] = None) -> ApiResponse[list]:
    """List all graphs with optional filters."""
    return success(graph_repository.list_graphs(course_id=course_id, status=status))


@router.get("/graphs/{graph_id}", response_model=ApiResponse[dict])
def get_graph_by_id(graph_id: str) -> ApiResponse[dict]:
    """Get a specific graph by ID."""
    graph = graph_repository.get_graph(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found")
    return success(graph.model_dump(mode="json"))


@router.delete("/graphs/{graph_id}", response_model=ApiResponse[dict])
def delete_graph(graph_id: str, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Delete a draft graph."""
    _require_admin(current_user)
    deleted = graph_repository.delete_graph(graph_id)
    return success({"deleted": deleted, "graph_id": graph_id})


@router.post("/graphs/diff", response_model=ApiResponse[dict])
def diff_graphs_endpoint(payload: dict) -> ApiResponse[dict]:
    """Compare two graphs. Body: {old_graph_id, new_graph_id} or {old_graph, new_graph}."""
    old_id = payload.get("old_graph_id")
    new_id = payload.get("new_graph_id")

    if old_id and new_id:
        old_graph = graph_repository.get_graph(old_id)
        new_graph = graph_repository.get_graph(new_id)
        if not old_graph:
            raise HTTPException(status_code=404, detail=f"Graph '{old_id}' not found")
        if not new_graph:
            raise HTTPException(status_code=404, detail=f"Graph '{new_id}' not found")
    else:
        # Accept inline graph data
        old_data = payload.get("old_graph")
        new_data = payload.get("new_graph")
        if not old_data or not new_data:
            return success({"error": "Provide old_graph_id/new_graph_id or old_graph/new_graph"})
        old_graph = GraphData.model_validate(old_data)
        new_graph = GraphData.model_validate(new_data)

    diff_result = graph_diff.diff_graphs(old_graph, new_graph)
    return success(diff_result)
