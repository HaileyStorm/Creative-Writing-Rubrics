from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-text-holdout-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("l2_text_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def private_root():
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-text-execution-v1-"))
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


def record(slot, verdict="YES", audit=None):
    return {"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "run_id": slot["run_id"], "verdict": verdict, "normalization_audit": [] if audit is None else audit}


def accepted(contacts, states=None, quote=None):
    states = states or ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]
    def call(command, **kwargs):
        contacts.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        question_id = next(line for line in kwargs["input"].splitlines() if '"question_id":' in line).split('"')[3]
        evidence = {"kind": "exact_quote", "reference": "synthetic", "exact_quote": quote, "summary": None} if quote is not None else {"kind": "summary", "reference": "synthetic", "exact_quote": None, "summary": "Grounded."}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"verdicts": [{"question_id": question_id, "verdict": states[len(contacts) % len(states)], "confidence": 0.8, "evidence": [evidence], "note": "test"}]}), encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "done", "stderr": "provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()
    return call


def test_exact_text_only_schedule_and_prompt_blindness():
    value = study()
    assert value.validate_package()["slots"] == 24
    slots = value.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 24
    assert len({slot["logical_sample_id"] for slot in slots}) == 24
    assert len({slot["run_id"] for slot in slots}) == 24
    assert len({(slot["case_id"], slot["leaf_id"]) for slot in slots}) == 8
    assert {slot["case_id"] for slot in slots} == {"t01", "t02", "t03", "t04"}
    command_root = Path(tempfile.gettempdir()) / "cwr-l2-text-command-test"
    assert all(slot["image_input"] is None and "--image" not in value.command_for(slot, command_root, codex_binary="codex") for slot in slots)
    assert all("expected_verdict" not in slot["prompt"] and "expected-ledger" not in slot["prompt"] and "holdout" not in slot["prompt"] for slot in slots)
    candidate = [slot for slot in slots if slot["leaf_id"] == value.LINE_BREAKS]
    control = [slot for slot in slots if slot["leaf_id"] == value.NECESSITY]
    assert len(candidate) == len(control) == 12 and all(slot["artifact_text"] for slot in slots)


def test_schedule_never_opens_expected_ledger(monkeypatch):
    value = study()
    source = value._source()
    monkeypatch.setattr(source, "load_ledger", lambda: (_ for _ in ()).throw(AssertionError("ledger opened")))
    value._schedule_template.cache_clear()
    assert len(value.build_schedule()) == 24


def test_compiled_leaf_drift_fails_before_prompt_rendering(monkeypatch):
    value = study()
    source = value._source()
    records = source.compiled_leaf_records()
    altered = {leaf_id: source.deepcopy(record) for leaf_id, record in records.items()}
    altered[value.LINE_BREAKS]["question"]["text"] += " drift"
    rendered = []
    monkeypatch.setattr(source, "compiled_leaf_records", lambda: altered)
    monkeypatch.setattr(source.production_runner, "_render_prompt", lambda **_kwargs: rendered.append(True) or "unexpected")
    value._schedule_template.cache_clear()
    with pytest.raises(ValueError, match="compiled leaf provenance"):
        value.build_schedule()
    assert rendered == []


def test_provider_free_dry_run_writes_only_text_inputs(private_root):
    value = study()
    report = value.dry_run(private_root, auth_call=fake_auth)
    assert report["provider_calls"] == 0 and report["planned_slots"] == 24 and report["image_slots"] == 0
    disclosure = json.loads((private_root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert len(disclosure["slots"]) == 24 and all(item["attachment"] is None for item in disclosure["slots"])
    assert not list((private_root / "inputs").glob("*.png"))
    assert all("--image" not in value.command_for(slot, private_root) for slot in value.build_schedule())


def test_mixed_state_success_and_cannot_assess_mismatch_are_scorer_only():
    value, slots = study(), study().build_schedule()
    states = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")
    records = [record(slot, states[index % len(states)]) for index, slot in enumerate(slots)]
    settlement, public = value._aggregate_test_only(schedule=slots, records=records, scorer=lambda _slot, _record: True)
    assert settlement["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS" and public["promotion"] == "none"
    cannot = next(slot for slot, item in zip(slots, records) if item["verdict"] == "CANNOT_ASSESS")
    miss, _ = value._aggregate_test_only(schedule=slots, records=records, scorer=lambda slot, _record: slot["slot_id"] != cannot["slot_id"])
    assert miss["decision"] == "NO_GO" and miss["aggregate_cells"]["two_of_three"] == 1


@pytest.mark.parametrize("leaf_id", ["form.poetry.free_verse.line_breaks", "form.poetry.free_verse.necessity"])
def test_any_candidate_or_control_miss_is_no_go(leaf_id):
    value, slots = study(), study().build_schedule()
    target = next(slot for slot in slots if slot["leaf_id"] == leaf_id)
    result, _ = value._aggregate_test_only(schedule=slots, records=[record(slot) for slot in slots], scorer=lambda slot, _record: slot["slot_id"] != target["slot_id"])
    assert result["decision"] == "NO_GO"


def test_claim_contention_blocks_before_contact(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    value._lifecycle()._claim_execution(private_root, value.build_schedule())
    with pytest.raises(ValueError, match="claim already exists"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted([]), auth_call=fake_auth)


@pytest.mark.parametrize("mode", ["nonzero", "missing_output"])
def test_failure_blocks_remaining_without_retry(private_root, mode):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    contacts = []
    def call(command, **kwargs):
        contacts.append((command, kwargs))
        if mode == "nonzero":
            return type("R", (), {"returncode": 1, "stdout": "no", "stderr": "bad"})()
        return type("R", (), {"returncode": 0, "stdout": "no", "stderr": "provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()
    with pytest.raises(RuntimeError, match="no resend"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=call, auth_call=fake_auth)
    base = value._lifecycle()
    terminals = [json.loads(base._sidecar_path(private_root, slot).read_text(encoding="utf-8")) for slot in value.build_schedule()]
    assert len(contacts) == 1 and terminals[0]["state"] == "ambiguous_contact"
    assert sum(item["state"] == "blocked_before_dispatch" for item in terminals[1:]) == 23


def test_complete_contacts_settle_claim_bound_aggregate_only(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    contacts = []
    assert value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted(contacts), auth_call=fake_auth)["completed_slots"] == 24
    settlement = value.settle(private_root, scorer=lambda _slot, _record: True)
    public = json.loads((private_root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    marker = json.loads((private_root / "settlement-publication.v1.json").read_text(encoding="utf-8"))
    assert len(contacts) == 24 and settlement["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert settlement["execution_claim_sha256"] == public["execution_claim_sha256"]
    assert marker["public_sha256"] == value.sha256_file(private_root / "public-aggregate.v1.json")
    assert set(public).isdisjoint({"slots", "records", "verdict_counts", "expected_ledger", "normalization_audit", "artifact_text"})


def test_canonical_quote_normalization_and_public_aggregate_count():
    value = study()
    slot = value.build_schedule()[0]
    def payload(quote):
        return {"verdicts": [{"question_id": slot["leaf_id"], "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "synthetic", "exact_quote": quote, "summary": None}], "note": "test"}]}
    exact = value._validate_response(slot, payload(slot["artifact_text"].splitlines()[0]))
    assert exact["normalization_audit"] == []
    demoted = value._validate_response(slot, payload("not a verbatim quote"))
    assert demoted["normalization_audit"][0]["reason"] == "not_verbatim"
    records = [record(item, audit=demoted["normalization_audit"] if item["slot_id"] == slot["slot_id"] else []) for item in value.build_schedule()]
    _, public = value._aggregate_test_only(schedule=value.build_schedule(), records=records, scorer=lambda _slot, _record: True)
    assert public["normalization_events"] == 1
    with pytest.raises(ValueError, match="normalization"):
        value._validate_response(slot, payload(""))


@pytest.mark.parametrize("kind", ["source", "lineage", "runtime"])
def test_source_lineage_and_runtime_drift_fail_before_import(monkeypatch, kind):
    value, imported = study(), []
    original = value._git
    if kind == "source":
        target = str(value.SOURCE_ROOT / "study.py")
    elif kind == "lineage":
        target = str(value.ROOT.parent / "hbq-l2-construct-microgate-v2" / "study.py")
    else:
        target = "src/hbqrs/runner.py"
    def drift(*args):
        if args[0] == "hash-object" and args[1] == target:
            return "0" * 40
        return original(*args)
    monkeypatch.setattr(value, "_git", drift)
    monkeypatch.setattr(value, "_exec_frozen_module", lambda *args: imported.append(args) or None)
    value._source.cache_clear()
    with pytest.raises(ValueError):
        value._source()
    assert imported == []


def test_mutation_rejects_settlement_and_interrupted_publication_recovers(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted([]), auth_call=fake_auth)
    base, slot = value._lifecycle(), value.build_schedule()[0]
    receipt = base._attempt_dir(private_root, slot) / "receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b" ")
    with pytest.raises(ValueError):
        value.settle(private_root, scorer=lambda _slot, _record: True)
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-text-publication-v1-"))
    try:
        slots = value.build_schedule()
        claim = base._claim_execution(root, slots)
        settlement, public = value._aggregate_test_only(schedule=slots, records=[record(item) for item in slots], scorer=lambda _slot, _record: True)
        bound = value.sha256_bytes(value.canonical_json(claim))
        settlement["execution_claim_sha256"] = public["execution_claim_sha256"] = bound
        def interrupted(path, payload):
            if path.name == "public-aggregate.v1.json":
                raise RuntimeError("crash")
            base._write_or_verify(path, payload)
        with pytest.raises(RuntimeError, match="crash"):
            base._write_settlement(root, settlement, public, writer=interrupted)
        base._write_settlement(root, settlement, public)
        assert (root / "settlement-publication.v1.json").is_file()
    finally:
        shutil.rmtree(root, ignore_errors=True)
