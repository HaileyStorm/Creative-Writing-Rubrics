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


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-contextual-justification-treatment-v2-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("l2_contextual_treatment_v2_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return historical_runtime.install(module)


@pytest.fixture
def private_root():
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-contextual-v2-execution-v1-"))
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
        output.write_text(json.dumps({"verdicts": [{"question_id": question_id, "verdict": states[(len(contacts) - 1) % len(states)], "confidence": 0.8, "evidence": [evidence], "note": "test"}]}), encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "done", "stderr": "provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()
    return call


def test_frozen_package_binds_source_lifecycle_parent_runtime_leaves_and_pairs():
    value = study()
    assert value.validate_package() == {"study_id": value.STUDY_ID, "source_commit": value.SOURCE_COMMIT, "slots": 18, "provider_calls": 0, "image_slots": 0}
    assert value.contract()["parent_result"] == value.PARENT_RESULT
    assert value.contract()["pair_prompt_hashes"] == value.PAIR_PROMPT_HASHES
    assert value.contract()["compiled_leaf_hashes"] == value.COMPILED_LEAF_HASHES


def test_exact_text_only_schedule_is_blind_and_lifecycle_is_cached():
    value = study()
    slots = value.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 18
    assert len({slot["logical_sample_id"] for slot in slots}) == len({slot["run_id"] for slot in slots}) == 18
    assert [slot["slot_id"] for slot in slots] == [f"l2contextv2exec-v1-{number:03d}" for number in range(1, 19)]
    assert {slot["case_id"] for slot in slots} == set(value.PAIR_PROMPT_HASHES)
    assert {slot["leaf_id"] for slot in slots} == {value.LINE_BREAKS}
    assert all(slot["image_input"] is None and "--image" not in value.command_for(slot, Path(tempfile.gettempdir()), codex_binary="codex") for slot in slots)
    assert value._lifecycle() is value._lifecycle()
    rendered = "\n".join(slot["prompt"] for slot in slots).casefold()
    assert all(token not in rendered for token in ("expected-ledger", "baseline", "necessity", "holdout"))


def test_schedule_never_opens_expected_ledger(monkeypatch):
    value = study()
    source = value._source()
    monkeypatch.setattr(source, "load_ledger", lambda: (_ for _ in ()).throw(AssertionError("ledger opened")))
    value._schedule_template.cache_clear()
    assert len(value.build_schedule()) == 18


def test_provider_free_dry_run_has_schema_manifest_auth_disclosure_and_no_image(private_root):
    value = study()
    report = value.dry_run(private_root, auth_call=fake_auth)
    assert report["provider_calls"] == 0 and report["planned_slots"] == 18 and report["image_slots"] == 0
    assert (private_root / "study-manifest.json").is_file() and (private_root / "runtime-schedule.json").is_file()
    disclosure = json.loads((private_root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert len(disclosure["slots"]) == 18 and all(item["attachment"] is None for item in disclosure["slots"])
    assert not list((private_root / "inputs").glob("*.png"))
    assert len(value._validated_schedule(private_root)) == 18


def test_private_root_is_required_outside_checkout_before_contact(tmp_path):
    value = study()
    root = value.REPOSITORY / ".private-root-should-not-exist"
    contacts = []
    with pytest.raises(ValueError):
        value.execute(root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=lambda *args, **kwargs: contacts.append(True), auth_call=fake_auth)
    assert contacts == []


def test_execution_requires_both_cli_authorities_before_private_root_access(tmp_path):
    value = study()
    with pytest.raises(ValueError, match="explicit allow-remote"):
        value.execute(tmp_path)
    with pytest.raises(ValueError, match="explicit allow-remote"):
        value.execute(tmp_path, allow_remote=True)


def test_cli_requires_both_execute_authorities_without_contact(tmp_path):
    command = [sys.executable, str(ROOT / "run.py"), "--execute", "--private-root", str(tmp_path)]
    result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 2 and "requires explicit authority" in result.stderr
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run", "--private-root", str(tmp_path), "--allow-remote"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
    assert dry.returncode == 2 and "dry run accepts no remote acknowledgement" in dry.stderr


def test_warmed_runtime_drift_fails_before_auth_or_provider_contact(private_root, monkeypatch):
    value = study()
    value._lifecycle()
    value._source()
    value.build_schedule()
    drifted = dict(value.RUNTIME_BLOBS)
    drifted["src/hbqrs/runner.py"] = "0" * 40
    monkeypatch.setattr(value, "RUNTIME_BLOBS", drifted)
    contacts = []
    def trap(*args, **kwargs):
        contacts.append(True)
        raise AssertionError("drift reached contact")
    with pytest.raises(ValueError, match="contract|runtime"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=trap, auth_call=trap)
    assert contacts == []


def test_mutated_frozen_schema_fails_before_auth_or_provider_contact(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    schema = value._base_lifecycle()._frozen_schema_path(private_root)
    schema.write_bytes(schema.read_bytes() + b" ")
    contacts = []
    def trap(*args, **kwargs):
        contacts.append(True)
        raise AssertionError("schema drift reached contact")
    with pytest.raises(ValueError, match="frozen response schema"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=trap, auth_call=trap)
    assert contacts == []


def test_claim_contention_and_failed_contact_terminalize_without_retry(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    base = value._base_lifecycle()
    base._claim_execution(private_root, value.build_schedule())
    with pytest.raises(ValueError, match="claim already exists"):
        value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted([]), auth_call=fake_auth)
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-contextual-v2-terminal-"))
    try:
        value.dry_run(root, auth_call=fake_auth)
        contacts = []
        def failed(command, **kwargs):
            contacts.append(command)
            return type("R", (), {"returncode": 1, "stdout": "no", "stderr": "bad"})()
        with pytest.raises(RuntimeError, match="no resend"):
            value.execute(root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=failed, auth_call=fake_auth)
        terminals = [json.loads(base._sidecar_path(root, slot).read_text(encoding="utf-8")) for slot in value.build_schedule()]
        assert len(contacts) == 1 and terminals[0]["state"] == "ambiguous_contact"
        assert sum(item["state"] == "blocked_before_dispatch" for item in terminals[1:]) == 17
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_response_schema_and_normalization_handle_all_four_states_and_quote_repair():
    value = study()
    slot = value.build_schedule()[0]
    def payload(state, quote):
        return {"verdicts": [{"question_id": slot["leaf_id"], "verdict": state, "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "synthetic", "exact_quote": quote, "summary": None}], "note": "test"}]}
    for state in value.VERDICTS:
        result = value._validate_response(slot, payload(state, slot["artifact_text"].splitlines()[0]))
        assert result["verdict"]["verdict"] == state and result["normalization_audit"] == []
    demoted = value._validate_response(slot, payload("NOT_APPLICABLE", "not a verbatim quote"))
    assert demoted["normalization_audit"][0]["reason"] == "not_verbatim"
    with pytest.raises(ValueError, match="normalization"):
        value._validate_response(slot, payload("CANNOT_ASSESS", ""))


def test_full_histogram_external_boolean_settlement_and_aggregate_only_publication(private_root):
    value, slots = study(), study().build_schedule()
    states = tuple(value.VERDICTS)
    records = [record(slot, states[index % len(states)], [{"reason": "not_verbatim"}] if index == 0 else []) for index, slot in enumerate(slots)]
    settlement, public = value._aggregate_test_only(schedule=slots, records=records, scorer=lambda _slot, _record: True)
    assert settlement["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert settlement["aggregate_cells"] == {"zero_of_three": 0, "one_of_three": 0, "two_of_three": 0, "three_of_three": 6, "total": 6}
    assert settlement["normalization_events"] == 1 and "verdict_counts" not in public
    t06 = next(slot for slot in slots if slot["case_id"] == "t06")
    miss, _ = value._aggregate_test_only(schedule=slots, records=records, scorer=lambda slot, _record: slot["slot_id"] != t06["slot_id"])
    assert miss["decision"] == "NO_GO_DSPY_ELIGIBLE_ONLY"
    assert miss["aggregate_cells"] == {"zero_of_three": 0, "one_of_three": 0, "two_of_three": 1, "three_of_three": 5, "total": 6}
    with pytest.raises(ValueError, match="boolean"):
        value._aggregate_test_only(schedule=slots, records=records, scorer=lambda _slot, _record: 1)
    with pytest.raises(ValueError, match="unique singleton"):
        value._aggregate_test_only(schedule=slots, records=records[:-1], scorer=lambda _slot, _record: True)


def test_complete_execution_settles_claim_bound_aggregate_only_and_mutation_rejects(private_root):
    value = study()
    value.dry_run(private_root, auth_call=fake_auth)
    contacts = []
    assert value.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted(contacts), auth_call=fake_auth)["completed_slots"] == 18
    settlement = value.settle(private_root, scorer=lambda _slot, _record: True)
    public = json.loads((private_root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    marker = json.loads((private_root / "settlement-publication.v1.json").read_text(encoding="utf-8"))
    assert len(contacts) == 18 and settlement["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert settlement["execution_claim_sha256"] == public["execution_claim_sha256"]
    assert marker["public_sha256"] == value.sha256_file(private_root / "public-aggregate.v1.json")
    assert set(public).isdisjoint({"slots", "records", "verdict_counts", "expected_ledger", "normalization_audit", "artifact_text"})
    receipt = value._base_lifecycle()._attempt_dir(private_root, value.build_schedule()[0]) / "receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b" ")
    with pytest.raises(ValueError):
        value.settle(private_root, scorer=lambda _slot, _record: True)
