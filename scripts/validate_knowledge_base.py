from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.knowledge_governance_service import validate_knowledge_base


def main() -> None:
    failures = validate_knowledge_base()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Knowledge base governance validation passed.")


if __name__ == "__main__":
    main()
