from __future__ import annotations

from pathlib import Path

from app.repositories import SqliteRepository

SEED_VISIBILITY = {
    "account-policy.md": "public",
    "orders-delivery.md": "public",
    "refund-policy.md": "internal",
    "escalation-sop.md": "internal",
    "incident-response.md": "admin",
}


def seed_documents(repository: SqliteRepository, seed_dir: Path) -> None:
    if repository.document_count() > 0 or not seed_dir.exists():
        return
    for path in sorted(seed_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        title = _title(content, path.stem)
        repository.insert_document(
            title=title,
            content=content,
            visibility=SEED_VISIBILITY.get(path.name, "internal"),
            created_by="system",
        )


def _title(content: str, fallback: str) -> str:
    first_line = content.splitlines()[0].strip()
    return first_line.removeprefix("# ").strip() or fallback
