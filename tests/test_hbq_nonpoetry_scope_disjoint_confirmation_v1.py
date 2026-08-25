from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-disjoint-confirmation-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_disjoint_confirmation_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return historical_runtime.install(module, source_commit=module.SOURCE_HEAD)


def fixture_rows():
    return [
        {"fixture_id": "s2dc-kestrel", "artifact_kind": "sheet", "declared_scope": "selected scene", "carrier_text": "new carrier a", "evaluation_record": "new response a", "contexts": ["new context a"]},
        {"fixture_id": "s2dc-lantern", "artifact_kind": "log", "declared_scope": "extract", "carrier_text": "new carrier b", "evaluation_record": "new response b", "contexts": ["new context b"]},
        {"fixture_id": "s2dc-tern", "artifact_kind": "packet", "declared_scope": "excerpt", "carrier_text": "new carrier c", "evaluation_record": None, "contexts": ["new context c"]},
    ]


def configured(tmp_path: Path, monkeypatch):
    s = study()
    rows = fixture_rows()
    monkeypatch.setattr(s, "validate_package", lambda: {"provider_calls": 0})
    monkeypatch.setattr(s, "private_file", lambda name, **_kwargs: {"fixtures": rows} if name == "fixtures.v2.json" else {})
    monkeypatch.setattr(s, "controller_root", lambda: tmp_path)
    return s, s.build_schedule()


def test_contract_freezes_fresh_candidate_only_no_retry_no_normalization_gate():
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["source_cwr_head"] == "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
    assert contract["freshness"] == {"prior_fixture_identity_reuse": False, "prior_carrier_prose_reuse": False, "prior_record_template_reuse": False, "prior_answer_key_language_reuse": False}
    assert contract["geometry"] == {"fresh_fixtures": 3, "candidate_only": True, "repeats_per_fixture": 2, "slots": 6, "one_leaf_per_call": True}
    assert contract["execution"]["batch_attempts"] == 1
    assert contract["execution"]["semantic_retry"] == contract["execution"]["normalization"] == "forbidden"
    assert contract["gate"]["success_action"] == "INDEPENDENT_WORDING_ONLY_PROMOTION_REVIEW_ELIGIBLE"
    assert contract["gate"]["automatic_promotion"] is False
    assert set(contract["promotion"].values()) == {"none"}


def test_exact_six_singleton_command_geometry(tmp_path: Path, monkeypatch):
    s, schedule = configured(tmp_path, monkeypatch)
    assert len(schedule) == len({row["slot_id"] for row in schedule}) == len({row["logical_sample_id"] for row in schedule}) == 6
    assert {row["fixture_id"] for row in schedule} == {"s2dc-kestrel", "s2dc-lantern", "s2dc-tern"}
    assert {row["repeat"] for row in schedule} == {1, 2}
    for row in schedule:
        command = s.command(row)
        assert command[command.index("--provider") + 1] == "codex"
        assert command[command.index("--model") + 1] == "gpt-5.6-sol"
        assert command[command.index("--reasoning") + 1] == "high"
        assert command[command.index("--batch-attempts") + 1] == "1"
        assert command.count("--question-id") == 1
        assert "--allow-remote" not in command


def test_live_execution_rejects_head_mismatch_before_claim_or_contact(tmp_path: Path, monkeypatch):
    s = study()
    monkeypatch.setattr(s, "controller_root", lambda: tmp_path)
    monkeypatch.setattr(s, "current_head", lambda: "f" * 40)
    monkeypatch.setattr(s, "validated_runtime_schedule", lambda: pytest.fail("must not load schedule"))
    calls = []
    with pytest.raises(ValueError, match="live HEAD differs"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=lambda *args, **kwargs: calls.append((args, kwargs)))
    assert calls == [] and not (tmp_path / "execution-v3-6ae9ee0" / "execution-claim.v1").exists()


def test_prompt_bytes_canonicalizes_windows_transport_and_newlines():
    s = study()
    assert s.prompt_bytes(b"antecedent of \x91it\x92\r\n") == "antecedent of ‘it’\n".encode("utf-8")
    assert s.prompt_bytes("‘it’\r\n") == "‘it’\n".encode("utf-8")
    with pytest.raises(ValueError, match="lone carriage return"):
        s.prompt_bytes(b"left\rright")


def test_execute_is_six_one_shot_contacts_with_no_promotion(tmp_path: Path, monkeypatch):
    s, schedule = configured(tmp_path, monkeypatch)
    monkeypatch.setattr(s, "assert_exact_head", lambda: None)
    monkeypatch.setattr(s, "validated_runtime_schedule", lambda: schedule)
    monkeypatch.setattr(s, "command", lambda slot, **_kwargs: ["provider", slot["slot_id"]])
    (tmp_path / "execution-v3-6ae9ee0").mkdir()
    calls = []
    def fake_runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    def verifier(_root, slot):
        ordinal = len(calls)
        return {"slot_id": slot["slot_id"], "fixture_id": slot["fixture_id"], "repeat": slot["repeat"], "logical_sample_id": slot["logical_sample_id"], "raw_verdict": "YES", "run_id": f"run-{ordinal}", "session_sha256": f"{ordinal:064x}", "checkpoint_chain_sha256": f"{ordinal + 20:064x}", "accepted_attempt": 1, "normalization_events": 0, "rejected_retries": 0}
    result = s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner, verifier=verifier)
    assert len(calls) == 6 and result == {"mode": "execute", "completed_slots": 6, "normalization_events": 0, "rejected_retries": 0, "promotion": "none"}
    with pytest.raises(ValueError, match="already claimed"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner, verifier=verifier)


def test_settlement_opens_review_only_on_six_exact_matches(tmp_path: Path, monkeypatch):
    s, schedule = configured(tmp_path, monkeypatch)
    monkeypatch.setattr(s, "assert_exact_head", lambda: None)
    monkeypatch.setattr(s, "validated_runtime_schedule", lambda: schedule)
    answer_rows = [
        {"fixture_id": "s2dc-kestrel", "boundary_case": "full_manuscript_bar_applied", "target_verdict": "NO"},
        {"fixture_id": "s2dc-lantern", "boundary_case": "local_review_complete_no_full_manuscript_bar", "target_verdict": "YES"},
        {"fixture_id": "s2dc-tern", "boundary_case": "evaluator_response_missing", "target_verdict": "CANNOT_ASSESS"},
    ]
    monkeypatch.setattr(s, "private_file", lambda name, **_kwargs: {"entries": answer_rows} if name == "expected-ledger.v1.json" else {"fixtures": fixture_rows()})
    root = tmp_path / "execution-v3-6ae9ee0"
    root.mkdir()
    (root / "execution-terminal.v1.json").write_text(json.dumps({"phase": "all_six_accepted", "completed_slots": 6, "normalization_events": 0, "rejected_retries": 0}), encoding="utf-8")
    expected = {row["fixture_id"]: row["target_verdict"] for row in answer_rows}
    records = [{"slot_id": slot["slot_id"], "fixture_id": slot["fixture_id"], "repeat": slot["repeat"], "raw_verdict": expected[slot["fixture_id"]]} for slot in schedule]
    (root / "raw-results.v1.json").write_text(json.dumps({"records": records}), encoding="utf-8")
    result = s.settle()
    assert result["decision"] == "INDEPENDENT_WORDING_ONLY_PROMOTION_REVIEW_ELIGIBLE"
    assert result["promotion"] == "none" and result["automatic_promotion"] is False


def test_public_package_contains_no_private_carrier_or_answer_key_text():
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.suffix in {".md", ".json", ".py"}).casefold()
    for forbidden in ("irena chalked", "jules counted", "snowmelt threaded", "feedback sheet uses absence"):
        assert forbidden not in public
