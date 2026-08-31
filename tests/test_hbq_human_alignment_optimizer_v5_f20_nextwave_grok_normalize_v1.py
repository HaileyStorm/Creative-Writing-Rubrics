from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-normalize-v1"
TERMINAL = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-grok-544af81-20260831a")


def _module():
    spec = importlib.util.spec_from_file_location("_nextwave_normalize_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def test_exact_terminal_wave_normalizes_ten_and_reparses(tmp_path: Path):
    module = _module(); output = tmp_path / "normalized"
    result = module.normalize_all(source_root=TERMINAL, output_root=output)
    assert result["normalized_candidates"] == 10 and result["provider_calls_made"] == result["process_launches"] == 0
    assert module.verify_all(source_root=TERMINAL, output_root=output) == result
    manifest = json.loads((output / "source-manifest.json").read_bytes())
    assert manifest["source_commit"] == module.SOURCE_COMMIT and manifest["source_tree_sha256"] == module.SOURCE_TREE_SHA256
    records = [json.loads(path.read_bytes()) for path in sorted(output.glob("nextwave-*.json"))]
    assert len(records) == 10 and len({row["source"]["request_id"] for row in records}) == len({row["source"]["session_id"] for row in records}) == 10
    assert len({row["normalized"]["instruction_sha256"] for row in records}) == 10
    for row in records:
        assert row["normalization"]["applied_factor_keys"] == list(module.EXPECTED_FACTORS)
        assert row["normalized"]["profile"]["version"] == module.NORMALIZED_VERSION
        assert row["normalized"]["profile"]["instruction_sha256"] == row["normalized"]["instruction_sha256"]
        assert row["authority"] == {"judging": "none", "selection": "none", "promotion": "none", "runtime": "none", "confirmation": "unopened"}
    assert any(row["normalization"]["ignored_extra_factor_keys"] for row in records)


def test_missing_invalid_parent_identical_and_duplicate_suggestions_reject():
    module = _module(); source = module._load_source(); row, parents = source._catalog(Path(json.loads((TERMINAL / "catalog.json").read_bytes())["source_root"]))
    first = row[0]; root = TERMINAL / first["cell_id"]
    envelope, suggestion = module._raw_suggestion((root / "responses" / "batch-0001.attempt-0001.grok.envelope.json").read_bytes())
    parent_instruction, parent_profile = (root / "parent-instruction.bin").read_bytes(), (root / "parent-profile.json").read_bytes()
    broken = json.loads(json.dumps(suggestion)); del broken["profile"]["factors"][module.EXPECTED_FACTORS[0]]
    with pytest.raises(ValueError, match="missing or invalid"): module._normalize(parent_instruction, parent_profile, broken, source)
    broken = json.loads(json.dumps(suggestion)); broken["profile"]["factors"][module.EXPECTED_FACTORS[0]] = 1
    with pytest.raises(ValueError, match="missing or invalid"): module._normalize(parent_instruction, parent_profile, broken, source)
    parent = json.loads(parent_profile); identical = {"instruction": parent_instruction.decode(), "change_summary": "same", "profile": {"factors": parent["factors"]}}
    with pytest.raises(ValueError, match="parent-identical"): module._normalize(parent_instruction, parent_profile, identical, source)
    assert envelope["structuredOutput"] == suggestion
    altered = dict(envelope); altered["structuredOutput"] = {"instruction": "different", "profile": {}, "change_summary": "different"}
    with pytest.raises(ValueError, match="structuredOutput"):
        module._raw_suggestion(module.compact(altered))
    with pytest.raises(ValueError, match="duplicate identity or instruction"):
        module._unique([{ "request_id": "r1", "session_id": "s1", "raw": {"instruction": "same"}}, {"request_id": "r2", "session_id": "s2", "raw": {"instruction": "same"}}])


def test_source_and_output_tamper_unexpected_and_disjoint_reject(tmp_path: Path):
    module = _module(); source_copy = tmp_path / "terminal-copy"; shutil.copytree(TERMINAL, source_copy)
    with pytest.raises(ValueError, match="disjoint"):
        module.normalize_all(source_root=source_copy, output_root=source_copy / "output")
    (source_copy / "unexpected.bin").write_bytes(b"x")
    with pytest.raises(ValueError, match="inventory|evidence"):
        module.normalize_all(source_root=source_copy, output_root=tmp_path / "out")
    output = tmp_path / "good"; module.normalize_all(source_root=TERMINAL, output_root=output)
    record = next(output.glob("nextwave-*.json")); record.write_bytes(record.read_bytes() + b" ")
    with pytest.raises(ValueError, match="reparse"):
        module.verify_all(source_root=TERMINAL, output_root=output)
    (output / "unexpected.bin").write_bytes(b"x")
    with pytest.raises(ValueError, match="inventory"):
        module.verify_all(source_root=TERMINAL, output_root=output)


def test_no_runtime_optimizer_dependency():
    text = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in text and "import optuna" not in text
