from pathlib import Path

from validate_knowledge_base import validate_knowledge_base


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "backend/app/main.py",
    "backend/app/api/v1/router.py",
    "backend/app/core/enums.py",
    "backend/app/schemas/profile.py",
    "backend/app/db/base.py",
    "backend/app/db/models.py",
    "backend/app/repositories/vertical_loop_repository.py",
    "backend/app/workflows/learning_graph.py",
    "backend/app/services/rag_service.py",
    "backend/app/services/knowledge_governance_service.py",
    "backend/app/services/embedding_service.py",
    "backend/app/services/model_gateway.py",
    "backend/app/tasks/celery_app.py",
    "backend/app/ops/start_api.py",
    "backend/app/ops/start_worker.py",
    "backend/app/ops/seed_demo_data.py",
    "backend/app/ops/import_knowledge_base.py",
    "backend/app/ops/check_spark.py",
    "backend/app/api/v1/system.py",
    "backend/app/data/knowledge_base.json",
    "backend/app/data/system_kb_schema.json",
    "backend/app/data/system_kb_manifest.json",
    "backend/app/data/prompt_templates.json",
    "frontend/src/components/resource/ResourceRenderer.tsx",
    "backend/alembic.ini",
    "backend/alembic/versions/20260430_0001_baseline.py",
    "backend/app/db/schema.sql",
    "frontend/src/types/baseline.ts",
    "frontend/src/App.tsx",
    "frontend/src/pages/SystemKnowledgePage.tsx",
    "frontend/src/hooks/useAuth.ts",
    "frontend/src/hooks/useRecordLearning.ts",
    "frontend/src/components/chat/ChatPanel.tsx",
    "frontend/tests/e2e/product.spec.ts",
    "infra/docker-compose.yml",
    "docs/DEVELOPMENT.md",
    "docs/FLOW_STAGE_VERIFICATION.md",
    "scripts/verify_runtime.py",
    "scripts/validate_knowledge_base.py",
    "scripts/compose_integration.py",
    "scripts/compose_integration.cmd",
    "scripts/docker_up.cmd",
    "scripts/docker_verify.cmd",
    "scripts/spark_smoke.cmd",
]

REQUIRED_TOKENS = {
    "backend/app/core/enums.py": [
        "document",
        "mindmap",
        "quiz",
        "reading",
        "video",
        "animation",
        "code_case",
        "profile_agent",
        "path_agent",
        "document_agent",
        "quiz_agent",
        "mindmap_agent",
        "video_agent",
        "code_agent",
        "quality_agent",
        "recommendation_agent",
        "tutor_agent",
        "pending",
        "running",
        "success",
        "failed",
        "retrying",
        "cancelled",
        "timeout",
    ],
    "backend/app/api/v1/router.py": ["/auth", "/learning", "/profiles", "/learning-paths", "/resources", "/agent-workflows"],
    "backend/app/api/v1/agent_workflows.py": ["/events", "StreamingResponse"],
    "backend/app/api/v1/resources.py": ["/generate-async", "/tasks/{celery_task_id}"],
    "backend/app/api/v1/knowledge.py": ["/status", "/rebuild", "/search", "/governance", "/chunks", "/validate"],
    "backend/app/workflows/learning_graph.py": ["StateGraph", "START", "END", "build_learning_graph"],
    "backend/app/repositories/vertical_loop_repository.py": ["PostgresVerticalLoopRepository", "AutoSwitchRepository", "SessionLocal"],
    "backend/app/services/rag_service.py": ["PersistentClient", "memory_fallback", "chroma", "EmbeddingIndex", "knowledge_base.json", "embedding_service"],
    "backend/app/services/knowledge_governance_service.py": ["validate_knowledge_base", "governance_report", "chunk_summaries", "content_hash", "allowed_review_statuses"],
    "backend/app/data/system_kb_schema.json": ["$defs", "chunk", "manifest", "content_hash"],
    "backend/app/data/system_kb_manifest.json": ["allowed_sources", "default_chunk_metadata", "required_chunk_fields"],
    "scripts/validate_knowledge_base.py": ["validate_knowledge_base", "Knowledge base governance validation passed"],
    "backend/app/services/embedding_service.py": ["EMBEDDING_API_URL", "deterministic_fallback", "embed_text"],
    "backend/app/services/model_gateway.py": ["websocket", "_call_spark", "hmac-sha256", "generate_json", "ValidationError"],
    "backend/app/ops/start_api.py": ["bootstrap_application", "uvicorn.run"],
    "backend/app/ops/start_worker.py": ["worker_main", "wait_for_tcp"],
    "backend/app/ops/seed_demo_data.py": ["prompt_templates.json", "seed_demo_data"],
    "backend/app/ops/check_spark.py": ["--call", "get_model_status"],
    "infra/docker-compose.yml": ["healthcheck", "service_healthy", "python -m app.ops.start_api", "python -m app.ops.start_worker"],
    "frontend/vite.config.ts": ["VITE_API_PROXY_TARGET"],
    "backend/app/schemas/profile.py": [
        "BasicInfo",
        "KnowledgeProfile",
        "LearningGoalProfile",
        "LearningPreference",
        "LearningBehavior",
        "CognitiveProfile",
        "DynamicUpdate",
    ],
    "frontend/src/types/baseline.ts": ["ResourceType", "AgentName", "AgentTaskStatus", "StudentProfile"],
    "frontend/src/App.tsx": ["AuthModal", "Sidebar", "LearningPage", "ModelConfigModal", "SystemKnowledgePage", "/knowledge"],
    "frontend/src/pages/SystemKnowledgePage.tsx": ["/knowledge/governance", "/knowledge/chunks", "/knowledge/search", "/knowledge/validate"],
    "frontend/src/hooks/useAuth.ts": ["/auth/me"],
    "frontend/src/hooks/useRecordLearning.ts": ["/learning-records"],
    "frontend/src/components/chat/ChatPanel.tsx": ["/learning/start-stream"],
    "frontend/tests/e2e/product.spec.ts": ["/learning/start", "learning-start-panel", "resource-gear", "数字人老师", "新创画像"],
    "frontend/package.json": ["@playwright/test", "test:e2e"],
    "frontend/playwright.config.ts": ["Desktop Chrome", "Pixel 7"],
    "backend/app/db/schema.sql": [
        "app_user",
        "student_profile",
        "student_profile_history",
        "learning_resource",
        "learning_path",
        "learning_path_node",
        "agent_workflow",
        "agent_task",
        "agent_event_log",
        "recommendation_record",
        "learning_record",
        "embedding_index",
        "prompt_template",
        "audit_log",
    ],
    ".env.example": [
        "DATABASE_URL",
        "REDIS_URL",
        "MODEL_PROVIDER",
        "SPARK_APP_ID",
        "SPARK_API_KEY",
        "SPARK_API_SECRET",
        "REPOSITORY_BACKEND",
        "RAG_BACKEND",
        "CHROMA_PERSIST_DIR",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_API_URL",
        "EMBEDDING_ALLOW_FALLBACK",
    ],
    "docs/FLOW_STAGE_VERIFICATION.md": [
        "FLOW_STAGE_VERIFICATION_VERSION=2026-04-30",
        "repository_backend=postgres",
        "knowledge_engine=chroma",
        "20260430_0001",
        "9 passed",
    ],
}

SECRET_PLACEHOLDER_KEYS = ["SPARK_APP_ID", "SPARK_API_KEY", "SPARK_API_SECRET"]


def main() -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")

    failures: list[str] = []
    for path, tokens in REQUIRED_TOKENS.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                failures.append(f"{path} missing token {token!r}")

    if failures:
        raise SystemExit("\n".join(failures))

    forbidden_hits: list[str] = []
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for line in env_example:
        for key in SECRET_PLACEHOLDER_KEYS:
            if line.startswith(f"{key}=") and line.split("=", 1)[1].strip():
                forbidden_hits.append(f".env.example has non-empty {key}")

    if forbidden_hits:
        raise SystemExit("\n".join(forbidden_hits))

    knowledge_failures = validate_knowledge_base()
    if knowledge_failures:
        raise SystemExit("\n".join(knowledge_failures))

    print("Baseline validation passed.")


if __name__ == "__main__":
    main()
