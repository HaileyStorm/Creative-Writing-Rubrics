"""Regression tests for the public Gray Blood projection contract."""

from __future__ import annotations

import importlib.util
import hashlib
import shutil
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "gray-blood-ch1-6"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_package_verifies() -> None:
    verifier = load_module("gray_public_verifier", ROOT / "verify_publication.py")
    assert verifier.check(ROOT) == []


def test_public_verdict_projection_has_no_evidence_or_execution_metadata() -> None:
    expected = {"bundle", "confidence", "question_id", "scope", "verdict"}
    records = [
        json.loads(line)
        for path in (ROOT / "verdicts").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 3214
    assert all(set(record) == expected for record in records)


def test_public_verdict_projection_discards_private_fields(tmp_path: Path) -> None:
    import json

    sanitizer = load_module("gray_public_sanitizer", ROOT / "sanitize_publication.py")
    raw = tmp_path / "private-verdicts.jsonl"
    raw.write_text(
        json.dumps(
            {
                "artifact_id": "private-artifact",
                "bundle_id": "prose.novel",
                "confidence": 0.98765,
                "evidence": [{"exact_quote": "private prose", "reference": "private path"}],
                "judge_id": "provider:model",
                "note": "private model note",
                "question_id": "core.example",
                "run_id": "private-run",
                "verdict": "YES",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert sanitizer.public_verdicts(raw, "whole_work", "prose.novel") == [
        {
            "bundle": "prose.novel",
            "confidence": 0.9877,
            "question_id": "core.example",
            "scope": "whole_work",
            "verdict": "YES",
        }
    ]


def refresh_public_integrity(root: Path, sanitizer, forbidden_terms: list[str] | None = None) -> None:
    audit = json.loads((root / "privacy-audit.json").read_text(encoding="utf-8"))
    refreshed = sanitizer.audit_tree(root, forbidden_terms=forbidden_terms)
    refreshed["unpublished_source_prose_ngram_hits"] = audit["unpublished_source_prose_ngram_hits"]
    if forbidden_terms is None:
        refreshed["explicit_private_term_hits"] = audit["explicit_private_term_hits"]
    sanitizer.write_json(root / "privacy-audit.json", refreshed)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sanitizer.files_for_audit(root)
    }
    sanitizer.write_json(root / "manifest.json", manifest)


@pytest.mark.parametrize(
    "forbidden_key",
    ["private_filename", "raw_prompt", "raw_response", "private_note", "brief_sha256"],
)
def test_verifier_rejects_private_keys_after_integrity_regeneration(
    tmp_path: Path, forbidden_key: str
) -> None:
    sanitizer = load_module("gray_public_sanitizer_for_keys", ROOT / "sanitize_publication.py")
    verifier = load_module("gray_public_verifier_for_keys", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    report_path = candidate / "reports" / "original.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report[forbidden_key] = "synthetic-private-value"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    refresh_public_integrity(candidate, sanitizer)
    assert any("forbidden public key" in failure for failure in verifier.check(candidate))


@pytest.mark.parametrize("overlap_length", [11, 25])
def test_verifier_rejects_source_overlap_after_integrity_regeneration(
    tmp_path: Path, overlap_length: int
) -> None:
    sanitizer = load_module("gray_public_sanitizer_for_ngram", ROOT / "sanitize_publication.py")
    verifier = load_module("gray_public_verifier_for_ngram", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    synthetic_private = tmp_path / "synthetic-private"
    artifact = synthetic_private / ".private" / "inputs" / "artifact.txt"
    artifact.parent.mkdir(parents=True)
    tokens = [f"syntheticword{index:02d}" for index in range(30)]
    artifact.write_text(" ".join(tokens), encoding="utf-8")
    overlap = candidate / "comparison.json"
    data = json.loads(overlap.read_text(encoding="utf-8"))
    data["synthetic_overlap_check"] = " ".join(tokens[:overlap_length])
    overlap.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    audit = sanitizer.audit_tree(candidate, synthetic_private, synthetic_private)
    sanitizer.write_json(candidate / "privacy-audit.json", audit)
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = {
        path.relative_to(candidate).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sanitizer.files_for_audit(candidate)
    }
    sanitizer.write_json(candidate / "manifest.json", manifest)
    assert any("source-prose overlap" in failure for failure in verifier.check(candidate))


def test_verifier_rejects_committed_private_literal_after_integrity_regeneration(tmp_path: Path) -> None:
    sanitizer = load_module("gray_public_sanitizer_for_literal", ROOT / "sanitize_publication.py")
    verifier = load_module("gray_public_verifier_for_literal", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    private_literal = "synthetic-private-input-name.txt"
    comparison = candidate / "comparison.json"
    data = json.loads(comparison.read_text(encoding="utf-8"))
    data["synthetic_label"] = private_literal
    comparison.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    refresh_public_integrity(candidate, sanitizer, [private_literal])
    assert any("committed private literal" in failure for failure in verifier.check(candidate))


@pytest.mark.parametrize("metadata_name", ["manifest.json", "privacy-audit.json"])
def test_verifier_rejects_private_metadata_keys_without_integrity_refresh(
    tmp_path: Path, metadata_name: str
) -> None:
    verifier = load_module("gray_public_verifier_for_metadata_key", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    path = candidate / metadata_name
    data = json.loads(path.read_text(encoding="utf-8"))
    data["private_filename"] = "synthetic-private-manuscript.txt"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert any("invalid metadata keys" in failure for failure in verifier.check(candidate))


@pytest.mark.parametrize(
    ("metadata_name", "path", "value"),
    [
        ("manifest.json", ("protocol", "comparison_scope"), "synthetic-private-manuscript.txt"),
        ("privacy-audit.json", ("ngram_normalization",), "synthetic-private-manuscript.txt"),
    ],
)
def test_verifier_rejects_private_metadata_values_without_integrity_refresh(
    tmp_path: Path, metadata_name: str, path: tuple[str, ...], value: str
) -> None:
    verifier = load_module("gray_public_verifier_for_metadata_value", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    destination = candidate / metadata_name
    data = json.loads(destination.read_text(encoding="utf-8"))
    cursor = data
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    destination.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert any("invalid manifest protocol values" in failure or "invalid privacy-audit normalization" in failure for failure in verifier.check(candidate))


def test_score_views_and_reader_summary_are_consistent() -> None:
    original = json.loads((ROOT / "reports" / "original.json").read_text(encoding="utf-8"))
    rewrite = json.loads((ROOT / "reports" / "rewrite.json").read_text(encoding="utf-8"))
    comparison = json.loads((ROOT / "comparison.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    protocol = manifest["protocol"]
    assert protocol["minimum_coverage"] == 0.8
    assert protocol["standard"] == {"id": "HBQ-RS", "version": "1.0.0"}
    assert protocol["bundle_versions"] == {"prose.chapter": 1, "prose.novel": 1}
    assert protocol["binary_judge"]["reasoning"] == "high"
    assert protocol["structured_judge"]["reasoning"] == "high"
    assert protocol["orientation_and_synthesis"]["reasoning"] == "high"
    assert "## Orientation" in readme
    assert "## Case study: five bounded moments" in readme
    assert "five permitted files" in readme
    assert "four bounded moments" not in readme
    assert "must not be read as causing the +7.89 whole-work difference" in readme
    assert "completion-only leaves are `NOT_APPLICABLE`" in readme
    assert "protocol, reasoning configuration, and accepted-verdict set differ" in readme
    for draft, report in (("original", original), ("rewrite", rewrite)):
        whole = report["whole_work"]["score"]["observed"]
        chapter_mean = report["wip_70_30"]["chapter_mean"]["observed"]
        composite = report["wip_70_30"]["score"]["observed"]
        assert abs(composite - (0.7 * whole + 0.3 * chapter_mean)) < 0.0002
        assert comparison["drafts"][draft]["whole_work"]["observed"] == whole
        assert comparison["drafts"][draft]["wip_70_30"]["observed"] == composite
        assert manifest["results"][draft]["whole_work_observed"] == whole
        assert manifest["results"][draft]["wip_70_30_observed"] == composite
        assert f"{whole:.2f}" in readme
        assert f"{composite:.2f}" in readme
    for old, new, delta in zip(
        original["whole_work"]["domains"],
        rewrite["whole_work"]["domains"],
        comparison["domain_differences_rewrite_minus_original"],
    ):
        assert delta["observed_difference"] == round(
            new["score"]["observed"] - old["score"]["observed"], 4
        )


def test_curated_excerpts_are_exactly_declared_and_bounded() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((ROOT / "excerpts" / "provenance.json").read_text(encoding="utf-8"))
    expected_files = [
        "excerpts/ch01-new-relationship.md",
        "excerpts/ch03-new-magic-cost.md",
        "excerpts/ch04-new-engraving.md",
        "excerpts/ch05-revision-pair.md",
        "excerpts/ch05-pro-illusion-consent.md",
    ]
    assert manifest["publication"]["manuscript_prose_included"] is True
    assert manifest["publication"]["curated_excerpt_files"] == expected_files
    assert manifest["publication"]["curated_excerpt_word_count"] == 1235
    assert manifest["publication"]["curated_excerpt_authorship"] == {
        "excerpts/ch01-new-relationship.md": "gpt-5.6-pro-rewrite",
        "excerpts/ch03-new-magic-cost.md": "gpt-5.6-pro-rewrite",
        "excerpts/ch04-new-engraving.md": "gpt-5.6-pro-rewrite",
        "excerpts/ch05-pro-illusion-consent.md": "gpt-5.6-pro-rewrite",
        "excerpts/ch05-revision-pair.md": "author-original-vs-gpt-5.6-pro-rewrite",
    }
    assert receipt["total_word_count"] == 1235
    assert receipt["authorization"] == (
        "The owner confirmed these exact five selections for public case-study use; "
        "no other Gray Blood manuscript prose is authorized here."
    )
    assert receipt["published_newline_projection"] == (
        "Source line endings are rendered as Markdown paragraph breaks; source character segments and excerpt hashes remain exact."
    )
    assert [entry["file"] for entry in receipt["curated_excerpts"]] == expected_files
    assert all(entry["word_count"] > 0 for entry in receipt["curated_excerpts"])
    assert "\n\n" in (ROOT / "excerpts" / "ch05-pro-illusion-consent.md").read_text(encoding="utf-8")
    assert [entry["authorship"] for entry in receipt["curated_excerpts"]] == [
        "gpt-5.6-pro-rewrite",
        "gpt-5.6-pro-rewrite",
        "gpt-5.6-pro-rewrite",
        "author-original-vs-gpt-5.6-pro-rewrite",
        "gpt-5.6-pro-rewrite",
    ]
    assert all(
        segment["authorship_role"] == "author-original" and segment["model"] is None
        or segment["authorship_role"] == "gpt-5.6-pro-rewrite" and segment["model"] == "gpt-5.6-pro"
        for entry in receipt["curated_excerpts"]
        for segment in entry["segments"]
    )


def test_excerpt_extractor_records_character_and_utf8_byte_boundaries() -> None:
    extractor = load_module("gray_excerpt_extractor", ROOT / "extract_excerpts.py")
    raw = "aé\r\nz".encode("utf-8")
    record, rendered = extractor.segment_record(raw, "fixture", "new", "chapter-01", 1, 4)
    assert rendered == "é\n\n"
    assert record["char_start"] == 1 and record["char_end"] == 4
    assert record["utf8_byte_start"] == 1 and record["utf8_byte_end"] == 5
    assert record["excerpt_sha256"] == hashlib.sha256("é\r\n".encode("utf-8")).hexdigest()
    assert "C:\\Users" not in (ROOT / "extract_excerpts.py").read_text(encoding="utf-8")


def test_targeted_excerpt_contract_is_dormant_and_small() -> None:
    contract = json.loads((ROOT / "targeted-evaluation-contract.json").read_text(encoding="utf-8"))
    ownership = json.loads((ROOT.parents[1] / "registry" / "criterion_ownership.json").read_text(encoding="utf-8"))
    assert contract["execution"]["status"] == "not_run"
    assert contract["execution"]["allow_remote_required"] is True
    assert "refusal as an execution outcome" in contract["execution"]["refusal_tracking"]
    assert len(contract["curated_excerpt_ids"]) == 5
    assert contract["curated_excerpt_authorship"] == {
        "gb-ch05-revision-pair-relationship-magic-v2": "author-original-vs-gpt-5.6-pro-rewrite",
        "gb-new-ch01-relationship-approach-v2": "gpt-5.6-pro-rewrite",
        "gb-new-ch03-magic-cost-v1": "gpt-5.6-pro-rewrite",
        "gb-new-ch04-engraving-v1": "gpt-5.6-pro-rewrite",
        "gb-new-ch05-illusion-consent-v1": "gpt-5.6-pro-rewrite",
    }
    assert sum(len(leaves) for leaves in contract["leaf_sets"].values()) == 16
    assert all(question_id in ownership for leaves in contract["leaf_sets"].values() for question_id in leaves)


def test_verifier_rejects_unapproved_excerpt_file_after_integrity_regeneration(tmp_path: Path) -> None:
    sanitizer = load_module("gray_public_sanitizer_for_extra_excerpt", ROOT / "sanitize_publication.py")
    verifier = load_module("gray_public_verifier_for_extra_excerpt", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (candidate / "excerpts" / "unapproved.md").write_text("unapproved manuscript text\n", encoding="utf-8")
    refresh_public_integrity(candidate, sanitizer)
    assert any("unexpected public package file" in failure for failure in verifier.check(candidate))


def test_verifier_rejects_private_path_in_excerpt_receipt(tmp_path: Path) -> None:
    sanitizer = load_module("gray_public_sanitizer_for_excerpt_path", ROOT / "sanitize_publication.py")
    verifier = load_module("gray_public_verifier_for_excerpt_path", ROOT / "verify_publication.py")
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    receipt_path = candidate / "excerpts" / "provenance.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["curated_excerpts"][0]["input_path"] = "C:\\private\\chapter-01.txt"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    refresh_public_integrity(candidate, sanitizer)
    assert any("forbidden public key" in failure for failure in verifier.check(candidate))


def test_public_package_is_lf_only_and_survives_git_lf_projection(tmp_path: Path) -> None:
    sanitizer = load_module("gray_public_sanitizer_for_lf", ROOT / "sanitize_publication.py")
    verifier = load_module("gray_public_verifier_for_lf", ROOT / "verify_publication.py")
    public_files = [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    assert all(b"\r" not in path.read_bytes() for path in public_files)
    candidate = tmp_path / "git-lf-projection"
    shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for path in sanitizer.files_for_audit(candidate):
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    assert verifier.check(candidate) == []
