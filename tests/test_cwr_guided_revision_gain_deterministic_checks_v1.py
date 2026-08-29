from __future__ import annotations

import hashlib
import io
import importlib.util
import json
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v1"


def _checks():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_deterministic_checks_v1", ROOT / "deterministic_checks.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_byte_exact_counts_hashes_and_canonical_output_are_stable() -> None:
    checks = _checks()
    source = "One line.\r\n\r\nSecond line!"
    descendant = "One line.\n\nSecond line!\nThird?"
    first = checks.analyze_revision(source, descendant)
    second = checks.analyze_revision(source, descendant)
    assert first == second
    assert first["input_hashes"]["source_sha256"] == hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert first["exact_text_counts"]["source"] == {"bytes": len(source.encode("utf-8")), "characters": len(source), "words": 4, "paragraphs": 2, "sentence_units": 2}
    assert first["exact_text_counts"]["descendant_minus_source"] == {"bytes": 5, "characters": 5, "words": 1, "paragraphs": 0, "sentence_units": 1}
    assert checks.canonical_json(first) == json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert first["interpretation"]["quality_or_gain_verdict"] == "not_available"
    assert first["runtime_provenance"]["python_version"]
    assert first["runtime_provenance"]["unicodedata_version"]


def test_repetition_and_mechanics_are_explicit_proxies_not_quality_scores() -> None:
    checks = _checks()
    result = checks.analyze_revision("A plain line.\n", "A plain line.\nA plain line.\nA plain line.\n\n\n((  \n")
    mechanics = result["mechanics_counts"]["descendant"]
    repetition = result["repetition_proxies"]["descendant"]
    assert repetition["n_gram_size"] == 3
    assert repetition["duplicate_line_occurrences"] == 2
    assert mechanics["unbalanced_common_delimiters"]["parentheses"] == 2
    assert mechanics["repeated_whitespace_runs"] >= 2
    assert "quality" not in result["mechanics_counts"]["definition"].casefold()
    assert result["collateral_damage_review"]["has_flags"] is True


def test_whole_prompt_overlap_is_descriptive_and_never_parses_compound_constraints() -> None:
    checks = _checks()
    prompt = 'Write a story. Avoid dragons but include "red lantern". Should not mention robots. Must not use the phrase: "blue moon". Do not use the phrase: "silver key".'
    result = checks.analyze_revision("source", "The red lantern glowed.", originating_prompt=prompt)
    overlap = result["originating_prompt_lexical_overlap"]
    assert overlap["provided"] is True
    assert {"red", "lantern"} <= set(overlap["matching_descendant_tokens"])
    assert overlap["prompt_bytes"] == len(prompt.encode("utf-8"))
    assert overlap["prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert "does not parse constraints" in overlap["definition"]
    assert not {key for key in overlap if "constraint" in key or "prohibited" in key or "required" in key}
    assert not {flag["flag_id"] for flag in result["collateral_damage_review"]["flags"] if "prompt" in flag["flag_id"]}
    casefolded = checks.analyze_revision("source", "STRASSE", originating_prompt="Straße")["originating_prompt_lexical_overlap"]
    assert casefolded["matching_descendant_tokens"] == ["strasse"]
    assert "casefolded" in casefolded["definition"]
    no_prompt = checks.analyze_revision("source", "descendant")["originating_prompt_lexical_overlap"]
    assert no_prompt == {"provided": False, "prompt_bytes": None, "prompt_sha256": None, "unique_prompt_token_count": None, "matching_descendant_token_count": None, "matching_descendant_token_fraction": None}


def test_unicode_nfc_comparison_preserves_raw_hashes_and_source_relative_deltas() -> None:
    checks = _checks()
    prompt = "Include caf\u00e9. Do not mention na\u00efve."
    source = "A na\u00efve narrator visits the caf\u00e9."
    descendant = "A nai\u0308ve narrator visits the cafe\u0301."
    result = checks.analyze_revision(source, descendant, originating_prompt=prompt)
    overlap = result["originating_prompt_lexical_overlap"]
    assert overlap["matching_descendant_tokens"] == ["caf\u00e9", "na\u00efve"]
    assert result["input_hashes"]["descendant_sha256"] == hashlib.sha256(descendant.encode("utf-8")).hexdigest()
    mechanics = checks.analyze_revision("Unclosed (", "Unclosed (")
    assert "unbalanced_delimiter_count_increased" not in {flag["flag_id"] for flag in mechanics["collateral_damage_review"]["flags"]}
    normalized_lines = checks.analyze_revision("caf\u00e9\ncafe\u0301\n", "unchanged")
    assert normalized_lines["repetition_proxies"]["source"]["duplicate_line_occurrences"] == 1


def test_voice_style_proxies_and_collateral_flags_remain_nonsemantic() -> None:
    checks = _checks()
    result = checks.analyze_revision("I walk. We wait.", '"I wait," we said. We wait.')
    proxy = result["voice_style_proxies"]
    assert proxy["source"]["sentence_length_distribution"]["word_length_histogram"] == {"2": 2}
    assert proxy["descendant"]["dialogue_character_ratio"] > 0
    assert proxy["descendant"]["first_person_marker_rate"] > 0
    assert proxy["descendant"]["type_token_ratio"] > 0
    assert "non-semantic" in proxy["definition"].casefold()
    assert "never a quality or revision-gain verdict" in result["collateral_damage_review"]["interpretation"]
    mixed = checks.analyze_revision('"“nested”"', '"“nested”"')["voice_style_proxies"]["source"]
    assert mixed["dialogue_character_ratio"] == 0.8
    assert mixed["dialogue_character_ratio"] <= 1.0


def test_cli_uses_raw_file_hashes_refuses_overwrite_and_rejects_non_utf8(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    checks = _checks()
    source = tmp_path / "source.md"
    descendant = tmp_path / "descendant.md"
    prompt = tmp_path / "prompt.md"
    output = tmp_path / "checks.json"
    source.write_bytes("caf\u00e9 source bytes\r\n".encode("utf-8"))
    descendant.write_bytes(b"descendant bytes\n")
    prompt.write_bytes("Include caf\u00e9.\n".encode("utf-8"))
    assert checks.main(["--source", str(source), "--descendant", str(descendant), "--originating-prompt", str(prompt), "--output", str(output)]) == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["input_hashes"]["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert checks.main(["--source", str(source), "--descendant", str(descendant), "--output", str(output)]) == 2
    assert "Refusing to overwrite" in capsys.readouterr().err
    assert checks.main(["--source", str(source), "--descendant", str(source), "--output", str(tmp_path / "missing" / "checks.json")]) == 2
    assert "output parent must already exist" in capsys.readouterr().err
    binary_stdout = io.BytesIO()
    monkeypatch.setattr(checks.sys, "stdout", type("BinaryStdout", (), {"buffer": binary_stdout})())
    assert checks.main(["--source", str(source), "--descendant", str(source), "--originating-prompt", str(prompt)]) == 0
    stdout_payload = binary_stdout.getvalue()
    assert stdout_payload.endswith(b"\n")
    assert b"source" in stdout_payload
    assert b"caf\xc3\xa9" in stdout_payload
    assert stdout_payload == checks.canonical_json(json.loads(stdout_payload)) + b"\n"
    descendant.write_bytes(b"\xff")
    assert checks.main(["--source", str(source), "--descendant", str(descendant)]) == 2
    monkeypatch.undo()
    assert "not UTF-8" in capsys.readouterr().err


def test_cli_leaves_no_published_output_after_temporary_file_fsync_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    checks = _checks()
    source = tmp_path / "source.md"
    descendant = tmp_path / "descendant.md"
    output = tmp_path / "checks.json"
    source.write_text("source", encoding="utf-8")
    descendant.write_text("descendant", encoding="utf-8")
    monkeypatch.setattr(checks.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("simulated fsync failure")))
    assert checks.main(["--source", str(source), "--descendant", str(descendant), "--output", str(output)]) == 2
    assert not output.exists()
    assert "Could not publish" in capsys.readouterr().err


def test_collateral_thresholds_are_fixed_and_never_emit_gain_verdict() -> None:
    checks = _checks()
    source = "Token token token. Token token token. Token token token."
    descendant = "Token token token. Token token token. Token token token."
    result = checks.analyze_revision(source, descendant)
    assert result["collateral_damage_review"]["thresholds"] == checks.COLLATERAL_DAMAGE_THRESHOLDS
    assert {flag["flag_id"] for flag in result["collateral_damage_review"]["flags"]} == set()
    assert "gain" in result["collateral_damage_review"]["interpretation"]
