from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AutoLearning"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = ""
    model_provider: str = "openai_compatible"
    database_url: str = "postgresql+psycopg://autolearning:autolearning@localhost:5432/autolearning"
    redis_url: str = "redis://localhost:6379/0"
    vector_store: str = "chroma"
    object_storage: str = "minio"
    repository_backend: str = "postgres"
    rag_backend: str = "chroma"
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "autolearning_knowledge"
    # LLM - OpenAI-compatible API (works with DeepSeek, OpenAI, Ollama, vLLM, etc.)
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_api_key: Optional[str] = None
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.4
    llm_timeout_seconds: int = 60
    # LangGraph runtime
    langgraph_max_workers: int = 1
    langgraph_timeout_seconds: int = 300
    # Embedding - local sentence-transformers (BGE-small-zh)
    embedding_provider: str = "local"
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_timeout_seconds: int = 30
    embedding_allow_fallback: bool = False
    embedding_dimension: int = 512
    # Spark (legacy, optional)
    spark_app_id: Optional[str] = None
    spark_api_key: Optional[str] = None
    spark_api_secret: Optional[str] = None
    spark_api_url: str = "wss://spark-api.xf-yun.com/x2"
    spark_model: str = "spark-x"
    spark_json_retries: int = 2
    # HuggingFace image generation
    hf_token: Optional[str] = None
    hf_endpoint: str = "https://api-inference.hf-mirror.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context: object) -> None:
        if not self.secret_key:
            if self.environment == "production":
                raise ValueError(
                    "SECRET_KEY must be set in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            # Deterministic dev key — stable across workers, safe to lose
            import hashlib
            self.secret_key = hashlib.sha256(b"autolearning-dev-secret-key").hexdigest()


@lru_cache
def get_settings() -> Settings:
    return Settings()
