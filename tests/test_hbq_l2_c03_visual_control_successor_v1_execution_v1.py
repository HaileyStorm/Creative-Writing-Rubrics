from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root
from tests import _hbq_l2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-l2-c03-visual-control-successor-v1-execution-v1"


def raw_study():
    spec = importlib.util.spec_from_file_location("l2_c03_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def study():
    return historical_runtime.install(raw_study())


@pytest.fixture
def private_root():
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-c03-execution-v1-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    for name in tuple(os.environ):
        if "API_KEY" in name.upper() or name.upper().startswith("OPENAI_API_"):
            monkeypatch.delenv(name, raising=False)


def fake_auth(command, **kwargs):
    assert kwargs["timeout"] == 20
    if command[-1] == "--version":
        return type("R", (), {"returncode": 0, "stdout": "codex test", "stderr": ""})()
    return type("R", (), {"returncode": 0, "stdout": "ChatGPT subscription", "stderr": ""})()


def record(slot, verdict="YES"):
    return {
        "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"],
        "run_id": slot["run_id"], "verdict": verdict, "normalization_audit": [],
    }


def accepted(contacts, verdict="YES", quote=None):
    def call(command, **kwargs):
        contacts.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        assert output.parent.is_dir()
        question_id = next(line for line in kwargs["input"].splitlines() if '"question_id":' in line).split('"')[3]
        evidence = {"kind": "exact_quote", "reference": "synthetic", "exact_quote": quote, "summary": None} if quote is not None else {"kind": "summary", "reference": "synthetic", "exact_quote": None, "summary": "Grounded."}
        output.write_text(json.dumps({"verdicts": [{"question_id": question_id, "verdict": verdict, "confidence": 0.8, "evidence": [evidence], "note": "test"}]}), encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "done", "stderr": "provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()
    return call


def test_pinned_geometry_and_prompt_blindness():
    value = study()
    assert value.validate_package()["slots"] == 12
    slots = value.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 12
    assert len({(slot["case_id"], slot["leaf_id"]) for slot in slots}) == 4
    assert all(slot["image_input"] is not None for slot in slots)
    assert all("expected_verdict" not in slot["prompt"] and "expected-ledger" not in slot["prompt"] for slot in slots)
    assert {slot["case_id"] for slot in slots} == {"s01", "s02"}
    assert len({slot["logical_sample_id"] for slot in slots}) == len({slot["run_id"] for slot in slots}) == 12
    per_fixture = {slot["image_input"]["name"]: 0 for slot in slots}
    for slot in slots:
        per_fixture[slot["image_input"]["name"]] += 1
    assert per_fixture == {"asset-01.png": 6, "asset-02.png": 6}


def test_current_checkout_drift_remains_fail_closed():
    with pytest.raises(ValueError, match=r"Current runtime differs from pinned source bytes: src/hbqrs/runner\.py"):
        raw_study().validate_package()


def test_historical_replay_executes_exact_private_runner():
    value = study()
    runner = value._historical_runtime_modules["src/hbqrs/runner.py"]
    pinned = value._historical_runtime_paths["src/hbqrs/runner.py"].read_bytes()
    source = value._git_bytes("show", f"{value.SOURCE_COMMIT}:src/hbqrs/runner.py")
    assert pinned == source
    assert runner.__historical_source_sha256__ == value.sha256_bytes(source) == "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2"
    assert runner.__historical_dependency_blobs__ == {
        relative: value._git("rev-parse", f"{value.SOURCE_COMMIT}:{relative}")
        for relative in ("src/hbqrs/core.py", "src/hbqrs/paths.py", "src/hbqrs/weights.py")
    }
    assert value._source().production_runner is runner
    assert value._lifecycle()._import_production_runner() is runner
    assert sys.modules["hbqrs.runner"] is not runner


def test_schedule_never_opens_either_expected_ledger(monkeypatch):
    value = study()
    source = value._source()
    predecessor = source.predecessor()
    monkeypatch.setattr(source, "load_ledger", lambda: (_ for _ in ()).throw(AssertionError("C03 ledger opened")))
    monkeypatch.setattr(predecessor, "load_ledger", lambda: (_ for _ in ()).throw(AssertionError("predecessor ledger opened")))
    value._schedule_template.cache_clear()
    assert len(value.build_schedule()) == 12


def test_provider_free_dry_run_has_all_twelve_exact_pngs(private_root):
    value = study()
    report = value.dry_run(private_root, auth_call=fake_auth)
    assert report["provider_calls"] == 0 and report["planned_slots"] == 12 and report["visual_png_slots"] == 12
    disclosure = json.loads((private_root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert len(disclosure["slots"]) == 12
    assert all(item["attachment"]["mime_type"] == "image/png" for item in disclosure["slots"])
    assert sum("--image" in value.command_for(slot, private_root) for slot in value.build_schedule()) == 12


def test_complete_success_is_diagnosis_only_and_any_miss_is_no_go():
    value = study()
    slots = value.build_schedule()
    success, public = value._aggregate_test_only(schedule=slots, records=[record(slot) for slot in slots], scorer=lambda _slot, _record: True)
    assert success["decision"] == "FIXTURE_DIAGNOSIS_SUPPORTED"
    assert success["aggregate_cells"] == {"zero_of_three": 0, "one_of_three": 0, "two_of_three": 0, "three_of_three": 4, "total": 4}
    assert public["promotion"] == "none" and "verdict_counts" not in public
    miss, _ = value._aggregate_test_only(schedule=slots, records=[record(slot) for slot in slots], scorer=lambda slot, _record: slot["slot_id"] != slots[0]["slot_id"])
    assert miss["decision"] == "NO_GO" and miss["aggregate_cells"]["two_of_three"] == 1


def test_atomic_claim_blocks_reuse_before_any_contact(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    base = value._lifecycle()
    base._claim_execution(private_root, value.build_schedule())
    with pytest.raises(ValueError, match="claim already exists"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted([]), auth_call=fake_auth)
    assert not (private_root / "runs" / "l2c03exec-v1-001").exists()


@pytest.mark.parametrize("mode", ["nonzero", "missing_output"])
def test_failed_first_contact_terminalizes_remaining_slots_without_retry(private_root, mode):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    contacts = []
    def call(command, **kwargs):
        contacts.append((command, kwargs))
        if mode == "nonzero":
            return type("R", (), {"returncode": 1, "stdout": "no", "stderr": "bad"})()
        return type("R", (), {"returncode": 0, "stdout": "no file", "stderr": "provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()
    with pytest.raises(RuntimeError, match="no resend"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=call, auth_call=fake_auth)
    base = value._lifecycle()
    terminals = [json.loads(base._sidecar_path(private_root, slot).read_text(encoding="utf-8")) for slot in value.build_schedule()]
    assert len(contacts) == 1 and terminals[0]["state"] == "ambiguous_contact"
    assert sum(item["state"] == "blocked_before_dispatch" for item in terminals[1:]) == 11


def test_twelve_successful_contacts_then_claim_bound_aggregate_settlement(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    contacts = []
    assert value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted(contacts), auth_call=fake_auth)["completed_slots"] == 12
    assert len(contacts) == 12
    settlement = value.settle(private_root, scorer=lambda _slot, _record: True)
    public = json.loads((private_root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    marker = json.loads((private_root / "settlement-publication.v1.json").read_text(encoding="utf-8"))
    assert settlement["decision"] == "FIXTURE_DIAGNOSIS_SUPPORTED"
    assert settlement["execution_claim_sha256"] == public["execution_claim_sha256"]
    assert marker["public_sha256"] == value.sha256_file(private_root / "public-aggregate.v1.json")
    assert marker["settlement_sha256"] == value.sha256_file(private_root / "settlement.v1.json")
    assert set(public).isdisjoint({"slots", "records", "verdict_counts", "expected_ledger", "normalization_audit"})


@pytest.mark.parametrize("mutation", ["receipt", "response", "diagnostic"])
def test_mutated_attempt_evidence_rejects_settlement(private_root, mutation):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted([]), auth_call=fake_auth)
    base = value._lifecycle()
    slot = value.build_schedule()[0]
    if mutation == "receipt":
        path = base._attempt_dir(private_root, slot) / "receipt.json"
    elif mutation == "response":
        path = base._response_path(private_root, slot)
    else:
        path = base._attempt_dir(private_root, slot) / "local-output" / "stdout.txt"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        value.settle(private_root, scorer=lambda _slot, _record: True)


def test_canonical_quote_normalization_retains_demotes_and_rejects():
    value = study()
    base = value._lifecycle()
    slot = {"leaf_id": "form.visual.environment_or_location_illustration.perspective", "artifact_id": "public-synthetic-artifact", "bundle_id": "visual.environment", "run_id": "normalization-test", "artifact_text": "structural plane"}
    def payload(quote):
        return {"verdicts": [{"question_id": slot["leaf_id"], "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "synthetic", "exact_quote": quote, "summary": None}], "note": "test"}]}
    exact = base._validate_response(slot, payload("structural plane"))
    assert exact["verdict"]["evidence"][0] == {"reference": "synthetic", "exact_quote": "structural plane"} and exact["normalization_audit"] == []
    demoted = base._validate_response(slot, payload("not a verbatim quote"))
    assert demoted["verdict"]["evidence"][0] == {"reference": "synthetic", "summary": "not a verbatim quote"}
    malformed = payload("")
    with pytest.raises(ValueError, match="normalization"):
        base._validate_response(slot, malformed)


def test_prepared_publication_recovery_requires_claim(private_root):
    value = study()
    base = value._lifecycle()
    slots = value.build_schedule()
    settlement, public = value._aggregate_test_only(schedule=slots, records=[record(slot) for slot in slots], scorer=lambda _slot, _record: True)
    with pytest.raises(ValueError, match="immutable execution claim"):
        base._write_settlement(private_root, settlement, public)
    claim = base._claim_execution(private_root, slots)
    bound = value.sha256_bytes(value.canonical_json(claim))
    settlement["execution_claim_sha256"] = bound
    public["execution_claim_sha256"] = bound
    def interrupted(path, payload):
        if path.name == "public-aggregate.v1.json":
            raise RuntimeError("crash")
        base._write_or_verify(path, payload)
    with pytest.raises(RuntimeError, match="crash"):
        base._write_settlement(private_root, settlement, public, writer=interrupted)
    base._write_settlement(private_root, settlement, public)
    assert (private_root / "settlement-publication.v1.json").is_file()


def test_runtime_mutation_fails_before_production_import(monkeypatch):
    value = study()
    imported = []
    original_git = value._git
    monkeypatch.setattr(value, "_git", lambda *args: "0" * 40 if args[0] == "hash-object" and args[1] in value.RUNTIME_PATHS else original_git(*args))
    monkeypatch.setattr(value, "_exec_frozen_module", lambda *args: imported.append(args) or None)
    with pytest.raises(ValueError, match="Current runtime differs"):
        value._source()
    assert imported == []
