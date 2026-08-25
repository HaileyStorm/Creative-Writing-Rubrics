from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-semantic-boundary-successor-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_semantic_boundary_successor_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return historical_runtime.install(module, source_commit=module.SOURCE_HEAD)


def fixtures():
    return [
        {"fixture_id": "s2sb-f01", "artifact_kind": "visible_penalty", "declared_scope": "excerpt", "evaluation_record": "evaluation 1", "contexts": ["context 1"]},
        {"fixture_id": "s2sb-f02", "artifact_kind": "silent_evaluation", "declared_scope": "fragment", "evaluation_record": "evaluation 2", "contexts": ["context 2"]},
        {"fixture_id": "s2sb-f03", "artifact_kind": "no_evaluation", "declared_scope": "excerpt", "evaluation_record": "passage only", "contexts": ["context 3"]},
    ]


def test_public_contract_freezes_the_adjudicated_semantics_and_no_promotion():
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["source_cwr_head"] == "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
    assert contract["candidate"]["text"] == "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?"
    assert contract["semantic_decision"] == {
        "owner": "observable_anti_penalty_behavior_in_the_supplied_evaluation",
        "visible_whole_work_penalty": "NO",
        "supplied_evaluation_without_completeness_penalty": "YES",
        "no_evaluation_record": "CANNOT_ASSESS",
    }
    assert contract["geometry"] == {"fixtures_exact": 3, "repeats_exact": 2, "slots_exact": 6, "candidate_only": True, "one_leaf_per_request": True}
    assert contract["execution"]["batch_attempts"] == 1
    assert contract["execution"]["post_response_semantic_retries_permitted"] is False
    assert set(contract["promotion"].values()) == {"none"}


def test_exact_six_candidate_singleton_geometry_and_command_surface(tmp_path: Path, monkeypatch):
    s = study()
    rows = fixtures()
    monkeypatch.setattr(s, "validate_package", lambda: {"provider_calls": 0})
    monkeypatch.setattr(s, "_private_file", lambda name: {"fixtures": rows} if name == "fixtures.v2.json" else {})
    monkeypatch.setattr(s, "_controller_root", lambda: tmp_path)
    schedule = s.build_schedule()
    assert len(schedule) == len({row["slot_id"] for row in schedule}) == 6
    assert {row["fixture_id"] for row in schedule} == {"s2sb-f01", "s2sb-f02", "s2sb-f03"}
    assert {row["repeat"] for row in schedule} == {1, 2}
    assert {row["leaf_id"] for row in schedule} == {"scope.passage.status"}
    for row in schedule:
        command = s._command(row)
        assert command[command.index("--provider") + 1] == "codex"
        assert command[command.index("--model") + 1] == "gpt-5.6-sol"
        assert command[command.index("--reasoning") + 1] == "high"
        assert command[command.index("--batch-size") + 1] == "1"
        assert command[command.index("--batch-attempts") + 1] == "1"
        assert command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"
        assert command.count("--question-id") == 1
        assert "--allow-remote" not in command


def test_live_execution_is_fail_closed_without_both_explicit_gates():
    s = study()
    with pytest.raises(ValueError, match="zero-incremental-charge"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=False)
    with pytest.raises(ValueError, match="remote"):
        s.execute(allow_remote=False, acknowledged_zero_incremental_charge=True)


def test_live_execution_rejects_head_mismatch_before_claim_or_contact(tmp_path: Path, monkeypatch):
    s = study()
    monkeypatch.setattr(s, "_controller_root", lambda: tmp_path)
    monkeypatch.setattr(s, "_current_head", lambda: "f" * 40)
    monkeypatch.setattr(s, "_validated_runtime_schedule", lambda: pytest.fail("schedule must not load after HEAD mismatch"))
    calls = []

    def forbidden_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(ValueError, match="live HEAD differs"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=forbidden_runner)
    assert calls == []
    assert not (tmp_path / "execution-v4-6ae9ee0-head-gated" / "execution-claim.v1").exists()


def test_public_package_contains_no_fixture_or_expected_ledger_content():
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.suffix in {".md", ".json", ".py"}).casefold()
    assert "mira folds the harbor chart" not in serialized
    assert "reject it because the complete novel ending is absent" not in serialized
    assert "expected-ledger.v2.json" in serialized  # commitment name only
    assert "automatic_promotion\": false" in serialized


def test_execute_is_exactly_six_one_shot_contacts_and_never_promotes(tmp_path: Path, monkeypatch):
    s = study()
    rows = fixtures()
    monkeypatch.setattr(s, "validate_package", lambda: {"provider_calls": 0})
    monkeypatch.setattr(s, "_private_file", lambda name: {"fixtures": rows} if name == "fixtures.v2.json" else {})
    monkeypatch.setattr(s, "_controller_root", lambda: tmp_path)
    schedule = s.build_schedule()
    monkeypatch.setattr(s, "_validated_runtime_schedule", lambda: schedule)
    monkeypatch.setattr(s, "_command", lambda slot, **_kwargs: ["provider", slot["slot_id"]])
    (tmp_path / "execution-v4-6ae9ee0-head-gated").mkdir()
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_verifier(_root, slot):
        ordinal = len(calls)
        return {
            "slot_id": slot["slot_id"],
            "fixture_id": slot["fixture_id"],
            "repeat": slot["repeat"],
            "logical_sample_id": slot["logical_sample_id"],
            "verdict": "YES",
            "run_id": f"run-{ordinal}",
            "session_id_sha256": f"{ordinal:064x}",
            "checkpoint_chain_head_sha256": f"{ordinal + 100:064x}",
            "accepted_provider_call_count": 1,
            "rejected_retry_count": 0,
            "batch_attempt_count": 1,
        }

    result = s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner, verifier=fake_verifier)
    assert len(calls) == 6 and result["completed_slots"] == 6 and result["promotion"] == "none"
    assert json.loads((tmp_path / "execution-v4-6ae9ee0-head-gated" / "execution-terminal.v1.json").read_text(encoding="utf-8"))["phase"] == "all_processes_accepted"
    with pytest.raises(ValueError, match="already claimed"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner, verifier=fake_verifier)


def test_settlement_only_opens_confirmation_review_on_all_three_two_of_two_cells(tmp_path: Path, monkeypatch):
    s = study()
    rows = fixtures()
    monkeypatch.setattr(s, "validate_package", lambda: {"provider_calls": 0})
    monkeypatch.setattr(s, "_controller_root", lambda: tmp_path)
    monkeypatch.setattr(s, "_private_file", lambda name: {"fixtures": rows} if name == "fixtures.v2.json" else {"rows": [
        {"fixture_id": "s2sb-f01", "semantic_state": "visible_whole_work_penalty", "expected_verdict": "NO"},
        {"fixture_id": "s2sb-f02", "semantic_state": "supplied_evaluation_without_completeness_penalty", "expected_verdict": "YES"},
        {"fixture_id": "s2sb-f03", "semantic_state": "no_evaluation_record", "expected_verdict": "CANNOT_ASSESS"},
    ]})
    schedule = s.build_schedule()
    monkeypatch.setattr(s, "_validated_runtime_schedule", lambda: schedule)
    expected = {"s2sb-f01": "NO", "s2sb-f02": "YES", "s2sb-f03": "CANNOT_ASSESS"}
    root = tmp_path / "execution-v4-6ae9ee0-head-gated"
    root.mkdir()
    (root / "execution-terminal.v1.json").write_text(json.dumps({"phase": "all_processes_accepted", "completed_slots": 6}), encoding="utf-8")
    records = [{"slot_id": slot["slot_id"], "fixture_id": slot["fixture_id"], "repeat": slot["repeat"], "verdict": expected[slot["fixture_id"]]} for slot in schedule]
    (root / "raw-results.v1.json").write_text(json.dumps({"records": records}), encoding="utf-8")
    result = s.settle()
    assert result["decision"] == "FRESH_DISJOINT_CONFIRMATION_REVIEW_ELIGIBLE"
    assert result["promotion"] == "none"
    assert all(cell["two_of_two"] for cell in result["cells"].values())
