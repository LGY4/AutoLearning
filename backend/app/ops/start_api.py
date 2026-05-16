from __future__ import annotations

import json
import socket

import uvicorn

from app.core.config import get_settings
from app.ops.bootstrap import bootstrap_application


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main() -> None:
    result = bootstrap_application(seed_vertical_loop=False)
    print(json.dumps({"bootstrap": result}, ensure_ascii=False), flush=True)
    settings = get_settings()

    port = settings.port
    if port == 0:
        port = _find_free_port()

    # Print the resolved port so frontend / scripts can discover it
    print(json.dumps({"port": port, "host": settings.host}, ensure_ascii=False), flush=True)

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=port,
        reload=False,
        proxy_headers=settings.environment != "production",
    )


if __name__ == "__main__":
    main()
