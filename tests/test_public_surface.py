from __future__ import annotations

import re
from pathlib import Path

from hbqrs import book_root

HOST_MARKERS = (
    r"Palimpsest",
    r"palimpsest",
    r"\bModel A\b",
    r"\bModel B\b",
    r"canon/manuscript state",
    r"decisions establish",
    r"Do not rewrite HBQ scores",
)

SCAN_DIRS = (
    "registry",
    "bundles",
    "schema",
    "prompts",
    "docs",
    "examples",
    "sources",
    "src",
    "README.md",
    "NOTICE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CITATION.cff",
    "manifest.json",
)


def test_public_text_has_no_host_product_language() -> None:
    root = book_root()
    hits: list[str] = []
    targets: list[Path] = []
    for name in SCAN_DIRS:
        path = root / name
        if path.is_file():
            targets.append(path)
        elif path.is_dir():
            targets.extend(item for item in path.rglob("*") if item.is_file())
    for path in targets:
        if path.suffix.lower() not in {".md", ".json", ".jsonl", ".yaml", ".yml", ".py", ".toml", ".cff", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in HOST_MARKERS:
            if re.search(needle, text):
                hits.append(f"{path.relative_to(root)}: {needle}")
    assert hits == []


def test_review_prompts_are_findings_only() -> None:
    review_dir = book_root() / "prompts" / "review"
    files = list(review_dir.glob("review*.md"))
    assert len(files) >= 16
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "Follow `prompts/review/_shared.md`" in text or path.name == "review.independent.md"
        assert "Do not rewrite HBQ scores" not in text
        assert "manuscript state" not in text


def test_open_review_schema_exists() -> None:
    schema = book_root() / "schema" / "open_review.schema.json"
    assert schema.is_file()
    assert "open review" in schema.read_text(encoding="utf-8").lower()
