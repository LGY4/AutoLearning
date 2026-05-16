from __future__ import annotations

from app.core.config import get_settings
from app.ops.bootstrap import wait_for_tcp
from app.tasks.celery_app import celery_app


def main() -> None:
    settings = get_settings()
    wait_for_tcp("PostgreSQL", settings.database_url)
    wait_for_tcp("Redis", settings.redis_url)
    celery_app.worker_main(["worker", "--loglevel=INFO", "--pool=solo"])


if __name__ == "__main__":
    main()
