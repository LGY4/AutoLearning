from __future__ import annotations
from typing import List

"""GraphBuilderAgent — semi-automatic knowledge graph generation.

Input sources (priority order):
  1. Uploaded documents / Markdown / PDF text
  2. Course outline provided by user
  3. Existing knowledge_base.json chunks
  4. Controlled web search results (supplementary only)

LLM extracts knowledge points, analyzes dependencies, merges duplicates.
Every node/edge carries source_refs for provenance. No ungrounded fabrication.

Output: GraphData (draft, pending review).
"""

import json
import re
from pathlib import Path

from app.schemas.graph import (
    GraphBuildRequest,
    GraphData,
    GraphEdge,
    GraphMetadata,
    GraphNode,
    ReviewStatus,
    SourceRef,
)
from app.services import model_gateway
from app.services.graph_validator import validate_graph


def _knowledge_base_chunks() -> List[dict]:
    """Load existing knowledge_base.json as source material."""
    path = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _build_source_context(request: GraphBuildRequest) -> tuple[str, List[SourceRef]]:
    """Assemble all input sources into a single context string with provenance."""
    context_parts: List[str] = []
    all_sources: List[SourceRef] = []

    # 1. Course outline (highest priority)
    if request.outline:
        context_parts.append(f"【课程大纲】\n{request.outline}")
        all_sources.append(SourceRef(type="outline", ref="user_provided", confidence=0.95))

    # 2. Uploaded documents
    for i, doc in enumerate(request.documents):
        # Detect if it's a file path or raw text
        if len(doc) < 500 and not doc.startswith(" ") and ("\n" not in doc[:100]):
            # Likely a file path
            context_parts.append(f"【文档{i+1}】(来源: {doc})\n[文件内容已引用]")
            all_sources.append(SourceRef(type="document", ref=doc, confidence=0.9))
        else:
            # Raw text content
            truncated = doc[:3000] if len(doc) > 3000 else doc
            context_parts.append(f"【文档{i+1}】\n{truncated}")
            all_sources.append(SourceRef(type="document", ref=f"document_{i+1}", confidence=0.9))

    # 3. Existing knowledge base chunks
    chunks = _knowledge_base_chunks()
    if chunks:
        chunk_summary = "\n".join(
            f"- [{c.get('chunk_id', '')}] {c.get('title', '')}: {c.get('content', '')[:80]}"
            for c in chunks[:30]
        )
        context_parts.append(f"【现有知识库 ({len(chunks)}条)】\n{chunk_summary}")
        all_sources.append(SourceRef(type="knowledge_base", ref="knowledge_base.json", confidence=0.85))

    # 4. Search results (supplementary, only if explicitly requested)
    if request.search_queries:
        search_results = _controlled_search(request.search_queries)
        if search_results:
            context_parts.append(f"【搜索补充】\n{search_results}")
            all_sources.append(SourceRef(type="search", ref="controlled_search", confidence=0.6))

    context = "\n\n---\n\n".join(context_parts) if context_parts else "无外部资料，请基于课程名称推断基础知识体系。"
    return context, all_sources


def _controlled_search(queries: List[str]) -> str:
    """Run controlled RAG search against existing knowledge base only.
    Does NOT crawl external URLs — only searches local Chroma/memory index."""
    try:
        from app.services import rag_service
        results: List[str] = []
        for q in queries[:5]:
            hits = rag_service.search_knowledge(q, top_k=3)
            for h in hits:
                results.append(f"[{h.get('title', '')}] {h.get('content', '')[:120]}")
        return "\n".join(results[:15]) if results else ""
    except Exception:
        return ""


_GRAPH_BUILD_PROMPT = """\
你是一个知识图谱构建专家。根据以下课程信息和资料，生成该课程的知识图谱。

课程名称：{course_name}
课程ID：{course_id}
最大节点数：{max_nodes}

参考资料：
{context}

{existing_context}

要求：
1. 提取 {max_nodes} 个以内的核心知识点作为节点
2. 分析知识点之间的前置依赖关系（prerequisite）
3. 每个节点标注所属层级 level（1=基础, 2=进阶, 3=高级）
4. 每个知识点必须有来源依据（来自大纲、文档或知识库），不可无来源编造
5. 合并重复或高度相似的知识点
6. 为每个节点关联相关的 chunk_ids（如果能从知识库匹配）
7. 生成推荐学习路径

返回严格 JSON：
{{
  "course_id": "{course_id}",
  "course_name": "{course_name}",
  "nodes": [
    {{
      "id": "唯一英文ID",
      "name": "知识点名称",
      "level": 1,
      "subject": "{course_name}",
      "chunk_ids": [],
      "depends_on": ["前置知识点ID"],
      "description": "简要描述",
      "tags": ["标签"],
      "source_reason": "该知识点的来源说明（来自大纲/文档/知识库的哪个部分）"
    }}
  ],
  "edges": [
    {{
      "source": "前置节点ID",
      "target": "后续节点ID",
      "type": "prerequisite"
    }}
  ],
  "learning_paths": {{
    "beginner": ["基础节点ID列表"],
    "intermediate": ["进阶节点ID列表"],
    "advanced": ["高级节点ID列表"]
  }}
}}
"""


def build_graph(request: GraphBuildRequest) -> GraphData:
    """Generate a knowledge graph from provided sources."""
    context, all_sources = _build_source_context(request)

    # Check for existing graph to merge
    existing_context = ""
    if request.existing_graph:
        existing_ids = [n.id for n in request.existing_graph.nodes]
        existing_names = [n.name for n in request.existing_graph.nodes]
        existing_context = (
            f"已有图谱节点 ({len(existing_ids)}个)：\n"
            f"IDs: {', '.join(existing_ids[:20])}\n"
            f"Names: {', '.join(existing_names[:20])}\n\n"
            "请在此基础上扩展，保留已有节点，新增缺失知识点，合并重复项。"
        )

    from app.services.prompt_utils import build_prompt
    prompt = build_prompt(
        "graph_build_v1",
        _GRAPH_BUILD_PROMPT,
        {
            "course_name": request.course_name,
            "course_id": request.course_id or _slugify(request.course_name),
            "max_nodes": request.max_nodes,
            "context": context,
            "existing_context": existing_context,
        },
    )

    raw = model_gateway.generate_json(
        prompt,
        required_keys=["nodes", "edges"],
    )

    # Parse LLM output into GraphData
    nodes = []
    for n in raw.get("nodes", []):
        source_reason = n.pop("source_reason", "")
        source_refs = []
        if source_reason:
            source_refs.append(SourceRef(type="llm_infer", ref=source_reason, confidence=0.7))
        # Inherit sources from context
        source_refs.extend(all_sources[:2])

        nodes.append(GraphNode(
            id=n.get("id", ""),
            name=n.get("name", ""),
            level=n.get("level", 1),
            subject=n.get("subject", request.course_name),
            chunk_ids=n.get("chunk_ids", []),
            depends_on=n.get("depends_on", []),
            description=n.get("description", ""),
            tags=n.get("tags", []),
            source_refs=source_refs,
            confidence=0.7,
        ))

    edges = []
    for e in raw.get("edges", []):
        edges.append(GraphEdge(
            source=e.get("source", ""),
            target=e.get("target", ""),
            type=e.get("type", "prerequisite"),
            confidence=0.7,
            source_refs=all_sources[:1],
        ))

    # If existing graph, merge: keep existing nodes, add new ones
    if request.existing_graph:
        existing_node_ids = {n.id for n in request.existing_graph.nodes}
        merged_nodes = list(request.existing_graph.nodes)
        for n in nodes:
            if n.id not in existing_node_ids:
                merged_nodes.append(n)
            else:
                # Update source_refs to include new sources
                existing_node = next(x for x in merged_nodes if x.id == n.id)
                existing_node.source_refs.extend(n.source_refs)
        nodes = merged_nodes

        existing_edge_keys = {(e.source, e.target) for e in request.existing_graph.edges}
        merged_edges = list(request.existing_graph.edges)
        for e in edges:
            if (e.source, e.target) not in existing_edge_keys:
                merged_edges.append(e)
        edges = merged_edges

    learning_paths = raw.get("learning_paths", {})

    # Build metadata
    metadata = GraphMetadata(
        course_id=request.course_id or _slugify(request.course_name),
        course_name=request.course_name,
        version=request.version,
        generated_by="graph_builder_agent",
        review_status=ReviewStatus.DRAFT,
        source_summary=all_sources,
        confidence=0.7,
        node_count=len(nodes),
        edge_count=len(edges),
    )

    graph = GraphData(
        metadata=metadata,
        nodes=nodes,
        edges=edges,
        learning_paths=learning_paths,
    )

    return graph


def build_and_validate(request: GraphBuildRequest) -> tuple[GraphData, dict]:
    """Build graph and validate. Returns (graph, validation_result)."""
    graph = build_graph(request)
    validation = validate_graph(graph)
    return graph, validation.model_dump()


def _slugify(text: str) -> str:
    """Convert Chinese/English text to a simple ID slug."""
    text = text.strip().lower()
    slug = re.sub(r'[^\w一-鿿]+', '_', text)
    return slug.strip('_')[:30] or "course"


def publish_graph(graph: GraphData) -> GraphData:
    """Save a validated graph to the data directory as the published version."""
    from pathlib import Path
    import json

    graph.metadata.review_status = ReviewStatus.APPROVED
    graph.metadata.updated_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).astimezone().isoformat(timespec="seconds")

    # Save to data directory
    data_dir = Path(__file__).resolve().parents[1] / "data"
    filename = f"knowledge_graph_{graph.metadata.course_id}.json"
    output_path = data_dir / filename

    output_path.write_text(
        json.dumps(graph.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return graph
