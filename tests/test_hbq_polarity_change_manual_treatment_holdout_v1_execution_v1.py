from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-polarity-change-manual-treatment-holdout-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("p1_ab_holdout_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_cwr(command, **kwargs):
    if "render-judge" in command:
        output = Path(command[command.index("--output") + 1])
        root = Path(kwargs["env"]["HBQRS_ROOT"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes((root / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_bytes())
    elif "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.fixture
def private_root():
    with tempfile.TemporaryDirectory(prefix="hbq-p1ab-") as directory:
        yield Path(directory)


def _synthetic_private_corpus(s, root: Path):
    fixtures = [{"fixture_id": row["fixture_id"], "leaf_id": row["leaf_id"], "artifact_kind": "synthetic_diagnostic", "declared_scope": "excerpt", "completion_status": "complete", "text": "test-private-fixture-" + row["fixture_id"]} for row in s.fixture_spec()]
    (root / "private-corpus.json").write_text(json.dumps({"format_version": 1, "study_id": s.STUDY_ID, "privacy": "fixture_text_and_leaf_mapping_only_no_labels_or_arms", "authorship": "post-development independent authored holdout without private-response access", "fixtures": fixtures}, sort_keys=True), encoding="utf-8")
    s.PRIVATE_CORPUS_SHA256 = s.sha(root / "private-corpus.json")
    s.validate_package = lambda: {"study_id": s.STUDY_ID, "provider_calls": 0, "slots": 120, "sealed_ledger_unopened": True}


def test_provider_free_freeze_has_exact_geometry_and_no_oracle_material():
    s = study()
    assert s.validate_package()["slots"] == 120
    rows = s.fixture_spec()
    assert len(rows) == 20 and len({row["leaf_id"] for row in rows}) == 12
    assert {row["fixture_id"] for row in rows} == {f"H{i:02d}" for i in range(1, 21)}
    assert all(set(row) == {"fixture_id", "leaf_id"} for row in rows)
    assert s.CANDIDATE_APPENDIX_SHA256 == "00ce0c5f1063c1fb36cc663bd2c522ce5eda254ee8f9079ec21774277e0d3722"


def test_same_fixture_schedule_and_dry_run_prove_only_exact_appendix_diff(private_root: Path):
    s = study()
    _synthetic_private_corpus(s, private_root)
    report = s.dry_run(private_root, runner_call=_fake_cwr)
    assert report == {"mode": "dry_run", "provider_calls": 0, "slots": 120, "expected_ledger_opened": False}
    slots = s.schedule(private_root)
    for fixture in s.fixture_spec():
        subset = [slot for slot in slots if slot["fixture_id"] == fixture["fixture_id"]]
        assert len(subset) == 6
        assert len({slot["artifact_id"] for slot in subset}) == 1
        assert {(slot["arm"], slot["repeat"]) for slot in subset} == {(arm, repeat) for arm in s.ARMS for repeat in range(1, 4)}
    corpus = json.loads((private_root / "private-corpus.json").read_text(encoding="utf-8"))
    assert all("expected" not in row and "arm" not in row for row in corpus["fixtures"])
    assert not (private_root / "sealed-expected-ledger.json").exists()
    assert "sealed-expected-ledger.json" not in s.prepare.__code__.co_consts
    assert "sealed-expected-ledger.json" not in s.dry_run.__code__.co_consts


def test_execute_requires_explicit_zero_paid_acknowledgement_and_never_opens_ledger(private_root: Path):
    s = study()
    _synthetic_private_corpus(s, private_root)
    s.dry_run(private_root, runner_call=_fake_cwr)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(private_root, runner_call=_fake_cwr)
    result = s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)
    assert result["expected_ledger_opened"] is False and result["slots"] == 120


def test_terminal_sidecar_unresolved_start_is_ambiguous_stop():
    s = study()
    with tempfile.TemporaryDirectory(prefix="p1ab-sidecar-") as directory:
        output = Path(directory)
        s.runner._write_attempt_start(output_dir=output, config_sha256="a" * 64, batch_number=1, attempt_number=1, base_prompt_sha256="b" * 64, effective_prompt_sha256="c" * 64, batch_attempts=3)
        with pytest.raises(s.runner.HBQError, match="ambiguous"):
            s.runner._validate_or_reconstruct_attempt_lifecycle(output, config_sha256="a" * 64, batch_attempts=3, reconstruct=False, strict_v5=True)


def test_settlement_is_the_only_ledger_reader_and_enforces_corrected_go_gate(private_root: Path):
    s = study()
    _synthetic_private_corpus(s, private_root)
    s.dry_run(private_root, runner_call=_fake_cwr)
    expected = {row["fixture_id"]: "YES" for row in s.fixture_spec()}
    (private_root / "sealed-expected-ledger.json").write_text(json.dumps({"format_version": 1, "study_id": s.STUDY_ID, "expected": expected}, sort_keys=True), encoding="utf-8")
    s.SEALED_EXPECTED_LEDGER_SHA256 = s.sha(private_root / "sealed-expected-ledger.json")
    synthetic_failures = {row["fixture_id"] for row in s.fixture_spec()[:2]} | {row["fixture_id"] for row in s.fixture_spec()[8:10]}

    def verifier(_root, slot):
        passed = not (slot["arm"] == "CURRENT" and slot["fixture_id"] in synthetic_failures)
        return {"slot_id": slot["slot_id"], "verdict": expected[slot["fixture_id"]] if passed else "NO", "run_id": "run-" + slot["slot_id"], "session_id_sha256": slot["slot_id"], "checkpoint_chain_head_sha256": "chain-" + slot["slot_id"]}

    settled = s.settle(private_root, verifier=verifier)
    assert settled["decision"] == "GO_PROMOTION"
    assert settled["gates"]["treatment_target_48_of_48"]
    assert settled["gates"]["treatment_60_of_60"]
    assert settled["gates"]["both_controls_24_of_24"]
    assert settled["gates"]["target_improvements"] == 4
    assert settled["gates"]["stable_defect_in_both_families"]
    assert settled["candidate_appendix_sha256"] == s.CANDIDATE_APPENDIX_SHA256
    assert settled["promotion_scope"] == "exact_candidate_appendix_only"
    assert "sealed-expected-ledger.json" in s.settle.__code__.co_consts
