from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

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


def test_strict_judge_response_schema_is_public() -> None:
    path = book_root() / "schema" / "hbq_judge_response.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    verdict = schema["properties"]["verdicts"]["items"]
    assert verdict["additionalProperties"] is False
    assert verdict["properties"]["evidence"]["items"]["additionalProperties"] is False


def test_built_wheel_includes_provenance_and_validation_runtime(tmp_path: Path) -> None:
    root = book_root()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
            str(root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("creative_writing_rubrics-*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")

    assert "hbqrs/book/manifest.json" in names
    assert "hbqrs/book/schema/hbq_judge_response.schema.json" in names
    assert any(name.startswith("hbqrs/book/sources/") for name in names)
    assert "Requires-Dist: jsonschema>=4.0" in metadata
