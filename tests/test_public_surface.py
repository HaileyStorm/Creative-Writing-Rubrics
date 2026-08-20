from __future__ import annotations

import hashlib
import json
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
    assert manifest["accepted_binary_verdicts"] == 778
    assert manifest["publication"] == {
        "private_prose_included": False,
        "evidence_quotes_included": False,
        "local_paths_included": False,
        "scores_and_verdict_states_complete": True,
    }

    public_files = [path for path in root.rglob("*") if path.is_file()]
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
    for marker in (
        "C:\\Users",
        "\\Downloads\\",
        "Gray_Blood_NOTES.txt",
        "Gray Blood 11-25-23.txt",
        "Gray Blood (new) Ch1-6.txt",
        '"quote"',
        '"run_id"',
        '"session_id"',
    ):
        assert marker not in public_text
    assert re.search(r"(?i)\b[a-z]:\\", public_text) is None
    assert re.search(r"(?:/home/|/Users/)", public_text) is None

    audit = json.loads((root / "privacy-audit.json").read_text(encoding="utf-8"))
    assert not any(audit["forbidden_pattern_hits"].values())
    assert not any(count for row in audit["exact_source_prose_ngram_hits"].values() for count in row.values())
    audited_files = [path for path in public_files if path.name != "privacy-audit.json"]
    digest = hashlib.sha256()
    for path in sorted(audited_files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    assert len(audited_files) == audit["audited_file_count"]
    assert sum(path.stat().st_size for path in audited_files) == audit["audited_total_bytes"]
    assert digest.hexdigest() == audit["audited_tree_sha256"]

    verdict_schema = json.loads((book_root() / "schema" / "hbq_verdict.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(verdict_schema)
    verdict_count = 0
    for path in root.rglob("*-verdicts.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            validator.validate(json.loads(line))
            verdict_count += 1
    assert verdict_count == 778

    published_hash_bindings = 0
    for path in root.rglob("*-provenance.json"):
        provenance = json.loads(path.read_text(encoding="utf-8"))
        if "published_verdicts_sha256" not in provenance:
            continue
        verdict_path = path.with_name(path.name.replace("-provenance.json", "-verdicts.jsonl"))
        assert provenance["published_verdicts_sha256"] == hashlib.sha256(verdict_path.read_bytes()).hexdigest()
        for batch in provenance["batches"]:
            assert "private_unsanitized_batch_verdicts_sha256" in batch
            assert "verdicts_sha256" not in batch
        published_hash_bindings += 1
    assert published_hash_bindings == 14


def test_published_full_original_extension_is_complete_and_sanitized() -> None:
    root = book_root() / "evaluation-results" / "gray-blood-original-ch1-7"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["accepted_binary_verdicts"] == 249
    assert manifest["whole"]["verdict_count"] == 221
    assert manifest["chapter_7"]["verdict_count"] == 28
    assert manifest["publication"] == {
        "private_prose_included": False,
        "evidence_quotes_included": False,
        "local_paths_included": False,
        "scores_and_verdict_states_complete": True,
    }

    public_files = [path for path in root.rglob("*") if path.is_file()]
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
    assert re.search(r"(?i)\b[a-z]:\\", public_text) is None
    assert re.search(r"(?:/home/|/Users/)", public_text) is None
    for marker in ('Gray Blood 11-25-23.txt', 'Gray_Blood_NOTES.txt', '"quote"', '"run_id"', '"session_id"'):
        assert marker not in public_text

    audit = json.loads((root / "privacy-audit.json").read_text(encoding="utf-8"))
    assert not any(audit["forbidden_pattern_hits"].values())
    assert not any(count for row in audit["exact_source_prose_ngram_hits"].values() for count in row.values())
    audited_files = [path for path in public_files if path.name != "privacy-audit.json"]
    digest = hashlib.sha256()
    for path in sorted(audited_files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    assert len(audited_files) == audit["audited_file_count"]
    assert sum(path.stat().st_size for path in audited_files) == audit["audited_total_bytes"]
    assert digest.hexdigest() == audit["audited_tree_sha256"]

    verdict_schema = json.loads((book_root() / "schema" / "hbq_verdict.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(verdict_schema)
    verdict_count = 0
    for path in root.rglob("*-verdicts.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            validator.validate(json.loads(line))
            verdict_count += 1
    assert verdict_count == 249

    provenance_count = 0
    for path in root.rglob("*-provenance.json"):
        provenance = json.loads(path.read_text(encoding="utf-8"))
        verdict_path = path.with_name(path.name.replace("-provenance.json", "-verdicts.jsonl"))
        assert provenance["published_verdicts_sha256"] == hashlib.sha256(verdict_path.read_bytes()).hexdigest()
        for batch in provenance["batches"]:
            assert "private_unsanitized_batch_verdicts_sha256" in batch
            assert "verdicts_sha256" not in batch
        provenance_count += 1
    assert provenance_count == 2


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
    assert any("/evaluation-results/gray-blood-original-ch1-7/manifest.json" in name for name in sdist_names)
