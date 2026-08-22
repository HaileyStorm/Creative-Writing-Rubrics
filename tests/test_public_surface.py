from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tarfile
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


def test_lazy_public_exports_preserve_attribute_and_from_import_semantics() -> None:
    import hbqrs

    assert hbqrs.__all__ == ["__version__", *hbqrs._EXPORTS]
    for name in hbqrs.__all__:
        assert getattr(hbqrs, name) is not None
        namespace: dict[str, object] = {}
        exec(f"from hbqrs import {name}", namespace)
        assert namespace[name] is getattr(hbqrs, name)


def test_multisample_study_fresh_import_has_minimal_hbqrs_closure() -> None:
    study = book_root() / "evaluation-results" / "hbq-multisample-repeatability-v1" / "study.py"
    code = """\
import importlib.util
import json
import sys
spec = importlib.util.spec_from_file_location("multisample_study_probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(sorted(name for name in sys.modules if name == "hbqrs" or name.startswith("hbqrs."))))
"""
    env = os.environ.copy()
    source = str(book_root() / "src")
    env["PYTHONPATH"] = source + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run([sys.executable, "-c", code, str(study)], check=True, capture_output=True, text=True, env=env)

    assert json.loads(result.stdout) == ["hbqrs", "hbqrs.core", "hbqrs.paths"]


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


def test_published_long_form_evaluation_is_complete_and_sanitized() -> None:
    root = book_root() / "evaluation-results" / "gray-blood-ch1-6"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evaluation_id"] == "gray-blood-chapters-1-6-current-comparison-v2"
    assert manifest["publication"] == {
        "curated_excerpt_authorship": {
            "excerpts/ch01-new-relationship.md": "gpt-5.6-pro-rewrite",
            "excerpts/ch03-new-magic-cost.md": "gpt-5.6-pro-rewrite",
            "excerpts/ch04-new-engraving.md": "gpt-5.6-pro-rewrite",
            "excerpts/ch05-pro-illusion-consent.md": "gpt-5.6-pro-rewrite",
            "excerpts/ch05-revision-pair.md": "author-original-vs-gpt-5.6-pro-rewrite",
        },
        "curated_excerpt_files": [
            "excerpts/ch01-new-relationship.md",
            "excerpts/ch03-new-magic-cost.md",
            "excerpts/ch04-new-engraving.md",
            "excerpts/ch05-revision-pair.md",
            "excerpts/ch05-pro-illusion-consent.md",
        ],
        "curated_excerpt_word_count": 1235,
        "evidence_text_included": False,
        "execution_metadata_included": False,
        "manuscript_prose_included": True,
        "published_verdicts": 3214,
    }
    assert manifest["protocol"] == {
        "binary_judge": {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"},
        "bundle_versions": {"prose.chapter": 1, "prose.novel": 1},
        "chapter_bundle": "prose.chapter",
        "chapter_count_per_draft": 6,
        "chapter_verdicts_per_draft": 1368,
        "comparison_scope": "complete current six-chapter WIP protocol; not a sampled-to-full comparison",
        "global_bundle": "prose.novel",
        "minimum_coverage": 0.8,
        "orientation_and_synthesis": {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"},
        "standard": {"id": "HBQ-RS", "version": "1.0.0"},
        "structured_judge": {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"},
        "whole_work_verdicts_per_draft": 239,
    }
    assert set(manifest["results"]) == {"original", "rewrite"}

    # The package-owned verifier is the single privacy and integrity authority:
    # source-prose overlap, committed private literals, files, hashes, LF bytes,
    # metadata shape, and projection fields must all agree together.
    completed = subprocess.run(
        [sys.executable, str(root / "verify_publication.py"), str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Gray Blood public package verification passed." in completed.stdout


def test_built_distributions_include_the_intended_public_surface(tmp_path: Path) -> None:
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
    assert "hbqrs/book/schema/hbq_batch.schema.json" in names
    assert any(name.startswith("hbqrs/book/sources/") for name in names)
    assert "Requires-Dist: jsonschema>=4.0" in metadata
    assert not any("evaluation-results/" in name for name in names)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "hatchling",
            "build",
            "--target",
            "sdist",
            "--directory",
            str(tmp_path),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    sdist = next(tmp_path.glob("creative_writing_rubrics-*.tar.gz"))
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = set(archive.getnames())
    assert any("/evaluation-results/gray-blood-ch1-6/manifest.json" in name for name in sdist_names)
    assert not any("/evaluation-results/gray-blood-original-ch1-7/" in name for name in sdist_names)
