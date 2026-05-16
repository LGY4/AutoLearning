from __future__ import annotations

import json

from app.services import rag_service


def import_knowledge_base(force: bool = False) -> dict:
    return rag_service.rebuild_knowledge_index(force=force)


def main() -> None:
    result = import_knowledge_base(force=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
