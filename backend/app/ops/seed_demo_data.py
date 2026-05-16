from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings


def _data_file(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / name


def _seed_prompt_templates(db) -> int:
    from sqlalchemy import select
    from app.db.models import PromptTemplate
    created = 0
    prompt_rows = json.loads(_data_file("prompt_templates.json").read_text(encoding="utf-8"))
    for row in prompt_rows:
        exists = db.scalar(
            select(PromptTemplate.id)
            .where(PromptTemplate.name == row["name"], PromptTemplate.version == row["version"])
            .limit(1)
        )
        if exists is None:
            db.add(
                PromptTemplate(
                    name=row["name"],
                    agent_name=row["agent_name"],
                    version=row["version"],
                    template=row["template"],
                    variables={"items": row.get("variables", [])},
                    status="active",
                )
            )
            created += 1
    return created


def seed_demo_data(seed_vertical_loop: bool = False) -> dict:
    if get_settings().repository_backend != "postgres":
        return {"prompt_templates_created": 0, "seed_vertical_loop": seed_vertical_loop, "skipped": True}
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        prompt_items = _seed_prompt_templates(db)
        db.commit()
    return {
        "prompt_templates_created": prompt_items,
        "seed_vertical_loop": seed_vertical_loop,
    }


def main() -> None:
    result = seed_demo_data(seed_vertical_loop=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
