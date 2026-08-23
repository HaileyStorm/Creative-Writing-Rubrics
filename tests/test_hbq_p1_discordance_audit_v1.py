from __future__ import annotations

import gzip
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-p1-discordance-audit-v1"
PRIVATE_ADAPTER_ROOT = Path(r"C:\Users\Haile\Documents\cwr-p1-discordance-adapter-v2-20260823")


def study():
    spec = importlib.util.spec_from_file_location("p1_discordance_audit_v1", ROOT / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def private_adapter_modules():
    if str(PRIVATE_ADAPTER_ROOT) not in sys.path:
        sys.path.insert(0, str(PRIVATE_ADAPTER_ROOT))
    import adapter
    import freeze_contract
    return adapter, freeze_contract


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _source_root(s, root: Path) -> None:
    fixtures = []
    expected = {}
    slots = []
    for ordinal in range(1, 21):
        fixture = f"H{ordinal:02d}"
        leaf = "core.coherence_and_comprehensibility.referents"
        fixtures.append({"fixture_id": fixture, "leaf_id": leaf, "artifact_kind": "synthetic_diagnostic", "declared_scope": "excerpt", "completion_status": "complete", "text": f"fixture {fixture}"})
        expected[fixture] = "YES"
        for arm in s.ARMS:
            for repeat in range(1, 4):
                slot = {"slot_id": f"slot-{fixture}-{arm}-{repeat}", "fixture_id": fixture, "artifact_id": f"artifact-{fixture}", "leaf_id": leaf, "arm": arm, "repeat": repeat, "judge_id": f"judge-{fixture}-{arm}-{repeat}"}
                slots.append(slot)
                run = root / "runs" / slot["slot_id"]
                _write(run / "run.json", {"configuration": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "attempt_lifecycle_policy": "terminal_sidecar_v1", "artifact_id": slot["artifact_id"], "judge_id": slot["judge_id"], "question_ids": [leaf]}})
                verdict = "NO" if (fixture, arm, repeat) == ("H01", "CURRENT", 1) else "YES"
                (run / "verdicts.jsonl").write_text(json.dumps({"question_id": leaf, "verdict": verdict, "evidence": [{"reference": "artifact", "exact_quote": f"fixture {fixture}"}]}), encoding="utf-8")
                _write(run / "responses" / "batch-0001.json", {"provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"session-{slot['slot_id']}"}}})
                prompt = "common prompt\n" + ("\ncandidate appendix\n" if arm == "TREATMENT" else "")
                (run / "responses").mkdir(parents=True, exist_ok=True)
                (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt.encode("utf-8")))
                _write(run / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.start.json", {"attempt_number": 1})
                _write(run / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.settled.json", {"attempt": 1, "outcome": "accepted", "policy": "terminal_sidecar_v1", "state": "settled"})
    _write(root / "private-corpus.json", {"format_version": 1, "study_id": s.SOURCE_STUDY_ID, "fixtures": fixtures})
    _write(root / "sealed-expected-ledger.json", {"format_version": 1, "study_id": s.SOURCE_STUDY_ID, "expected": expected})
    _write(root / "runtime-schedule.json", {"slots": slots})
    for name in ("study-manifest.json", "settlement.json", "arm-contract.json", "runtime-bundle.json", "remote-disclosure.json"):
        _write(root / name, {"name": name})
    base, delta = b"common prompt", b"\n\ncandidate appendix"
    binary = root / "runtime-book"
    (binary / "current" / "prompts" / "judge").mkdir(parents=True)
    (binary / "treatment" / "prompts" / "judge").mkdir(parents=True)
    (binary / "current" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").write_bytes(base + b"\n")
    (binary / "treatment" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").write_bytes(base + delta + b"\n")
    s.SOURCE_PRIVATE_CORPUS_SHA256 = s.sha(root / "private-corpus.json")
    s.SOURCE_LEDGER_SHA256 = s.sha(root / "sealed-expected-ledger.json")
    s.CANDIDATE_APPENDIX_SHA256 = s.digest(delta.lstrip(b"\n"))
    s.APPENDIX_PROMPT_DELTA_SHA256 = s.digest(delta)


def _adapter_result(s, request, output, *, status="ACCEPTED", extra=None, contract_path=None, evidence_root=None, attempt_id="attempt-0001"):
    contract_sha = s.sha(contract_path) if contract_path else "a" * 64
    preflight_sha, contact_sha, external_sha, precontact_sha = "b" * 64, "c" * 64, "e" * 64, None
    if evidence_root is not None:
        review = evidence_root / request["review_id"] / "attempts" / attempt_id
        preflight = {"review_id": request["review_id"], "request_sha256": s.digest(s.canonical(request)), "contract_sha256": contract_sha}
        _write(review / "preflight.json", preflight)
        preflight_sha = s.sha(review / "preflight.json")
        if status == "PRECONTACT_FAILED_NO_MODEL_CONTACT":
            precontact = {"format_version": 1, "review_id": request["review_id"], "request_sha256": s.digest(s.canonical(request)), "status": status, "preflight_sha256": preflight_sha, "model_contact_processes_started": 0, "retries": "permitted_before_any_model_contact"}
            _write(review / "precontact-receipt.json", precontact)
            precontact_sha = s.sha(review / "precontact-receipt.json")
            contact_sha = None
            external = {"format_version": 1, "review_id": request["review_id"], "request_sha256": s.digest(s.canonical(request)), "preflight_sha256": preflight_sha, "precontact_sha256": precontact_sha, "status": status}
        else:
            contact = {"review_id": request["review_id"], "request_sha256": s.digest(s.canonical(request)), "retries": 0, "events_sha256": "9" * 64}
            _write(review / "contact.json", contact)
            contact_sha = s.sha(review / "contact.json")
            if status == "AMBIGUOUS_NO_RETRY":
                ambiguity = {"review_id": request["review_id"], "status": status, "contact_process_started": True}
                _write(review / "ambiguity-receipt.json", ambiguity)
            external = {"format_version": 1, "review_id": request["review_id"], "request_sha256": s.digest(s.canonical(request)), "preflight_sha256": preflight_sha, "contact_sha256": contact_sha, "status": status}
            if status == "ACCEPTED":
                external["events_sha256"] = "9" * 64
                external["output_sha256"] = s.digest(s.canonical(output))
                external["event_projection"] = {"thread_id_sha256": "f" * 64, "usage": {"input_tokens": 1}, "tool_items_observed": 0}
            else:
                external["ambiguity_sha256"] = s.sha(review / "ambiguity-receipt.json")
        _write(review / "external-evidence.json", external)
        external_sha = s.sha(review / "external-evidence.json")
    ambiguity_sha = None if status != "AMBIGUOUS_NO_RETRY" else (s.sha(evidence_root / request["review_id"] / "attempts" / attempt_id / "ambiguity-receipt.json") if evidence_root is not None else "d" * 64)
    value = {
        "envelope": s.ADAPTER_ENVELOPE,
        "status": status,
        "review_id": request["review_id"],
        "evidence_attempt_id": attempt_id,
        "request_sha256": s.digest(s.canonical(request)),
        "contact_process_started": status != "PRECONTACT_FAILED_NO_MODEL_CONTACT",
        "adapter_contract_sha256": contract_sha,
        "preflight_sha256": preflight_sha,
        "contact_sha256": contact_sha,
        "ambiguity_sha256": ambiguity_sha,
        "precontact_sha256": precontact_sha,
        "external_evidence_sha256": external_sha,
        "requested": {**s.REQUESTED_IDENTITY, "model_contact_processes": 1},
        "observed": {
            "authenticated_service": "authenticated_openai_codex_cli",
            "model": s.NOT_ATTESTED,
            "reasoning_effort": s.NOT_ATTESTED,
            "thread_id_sha256": "f" * 64,
            "model_contact_processes_started": 0 if status == "PRECONTACT_FAILED_NO_MODEL_CONTACT" else 1,
            "provider_http_attempts_observed": None,
        },
        "output": output,
    }
    if extra:
        value.update(extra)
    return value


def _adapter_roots(s, tmp_path: Path, packet: Path) -> tuple[Path, Path]:
    manifest = json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8"))
    state_id, mechanism_id = s._expected_review_ids(manifest)
    head = subprocess.run(["git", "-C", str(s.REPOSITORY), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    projection = {
        "format_version": 2,
        "study_id": s.STUDY_ID,
        "status": "ARMED",
        "model_contact_processes_started": 0,
        "execution_enabled": True,
        "maximum_model_contact_processes": 2,
        "audit_manifest_sha256": s.sha(packet / "audit-manifest.json"),
        "remote_disclosure_sha256": s.sha(packet / "remote-disclosure.json"),
        "expected_ledger_sent": False,
        "provider_http_attempts_observed": None,
    }
    contract = tmp_path / "adapter-contract.json"
    contract.write_text(json.dumps({
        "format_version": 1,
        "status": "FROZEN",
        "cwr_head": head,
        "study_sha256": s.sha(s.ROOT / "study.py"),
        "study_contract_sha256": s.sha(s.ROOT / "study-contract.json"),
        "private_namespace_sha256": "1" * 64,
        "packet_root": str(packet.resolve()),
        "packet_manifest_sha256": s.sha(packet / "audit-manifest.json"),
        "packet_disclosure_sha256": s.sha(packet / "remote-disclosure.json"),
        "packet_arming_receipt_projection_sha256": s.digest(s.canonical(projection)),
        "expected_review_ids": [state_id, mechanism_id],
        "codex_cli_version": "codex-cli 0.149.0",
        "direct_codex_binary_sha256": "2" * 64,
        "login_status": "Logged in using ChatGPT",
        "login_status_sha256": s.digest(b"Logged in using ChatGPT"),
    }, sort_keys=True), encoding="utf-8")
    evidence = tmp_path / "adapter-evidence"
    evidence.mkdir()
    return contract, evidence


def test_provider_free_contract_forbids_execution_and_dspy() -> None:
    s = study()
    assert s.validate_package()["model_contact_processes_started"] == 0
    value = s.contract()["review_plan"]
    assert value["provider_execution_enabled"] is False
    assert value["dspy_enabled"] is False
    assert value["maximum_model_contact_processes"] == 2 and value["retries"] == 0
    assert value["attempt_lifecycle_policy"] == "terminal_sidecar_v1"
    assert s.contract()["adapter_execution"] == {
        "result_envelope": s.ADAPTER_ENVELOPE,
        "adapter_statuses": ["ACCEPTED", "AMBIGUOUS_NO_RETRY", "PRECONTACT_FAILED_NO_MODEL_CONTACT"],
        "one_model_contact_process_per_callback": True,
        "requested_model_contact_processes": 2,
        "precontact_failure_is_recoverable": True,
        "stable_adapter_evidence_root_required": True,
        "contiguous_attempt_names_required": True,
        "request_binds_exact_review_id_and_arming_receipt": True,
        "started_process_counting": "callback_local_envelope_and_cumulative_study_result",
        "provider_http_attempts_observed": None,
        "model_and_reasoning_identity_evidence": "requested_only",
    }
    assert tuple(value["mechanism_classifications"]) == (
        "FIXTURE_OR_LEDGER_AMBIGUITY", "SAME_INPUT_VARIANCE", "EVIDENCE_OR_VALIDATOR_DEFECT", "APPENDIX_HARM", "SHARED_PROMPT_GAP",
    )


def test_arm_rejects_an_arbitrary_adapter_file(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    arbitrary = tmp_path / "adapter-contract.json"
    arbitrary.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen packet-specific"):
        s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=arbitrary)


def test_freeze_contract_uses_public_validator_and_real_attempt_local_preflight(tmp_path: Path, monkeypatch) -> None:
    s = study()
    adapter, freezer = private_adapter_modules()
    source, packet = tmp_path / "source", tmp_path / "fresh-successor-packet"
    _source_root(s, source)
    s.freeze(source, packet)
    contract = tmp_path / "adapter-contract.json"
    result = freezer.freeze_contract(packet, contract_path=contract)
    assert result == {"status": "FROZEN", "adapter_contract_sha256": s.sha(contract)}
    armed = s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=contract)
    monkeypatch.setattr(adapter, "CONTRACT_PATH", contract)
    manifest = json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8"))
    state_id, _ = s._expected_review_ids(manifest)
    plan = s._review_plan(packet, state_id)
    request = s._review_request(plan, arming_receipt_sha256=s.sha(packet / "arming-receipt.json"))
    wrong_id = dict(request)
    wrong_id["review_id"] = "outside-contract-state"
    with pytest.raises(RuntimeError, match="outside the frozen adapter contract"):
        adapter._preflight(wrong_id, adapter._contract(), tmp_path / "wrong-id-attempt")
    wrong_arming = dict(request)
    wrong_arming["arming_receipt_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="arming receipt"):
        adapter._preflight(wrong_arming, adapter._contract(), tmp_path / "wrong-arming-attempt")
    attempt_root = tmp_path / "adapter-evidence" / state_id / "attempts" / "attempt-0001"
    preflight, path = adapter._preflight(request, adapter._contract(), attempt_root)
    assert path == attempt_root / "preflight.json"
    assert preflight["review_id"] == state_id and preflight["contract_sha256"] == armed["adapter_contract_sha256"]
    assert {item.name for item in attempt_root.iterdir()} == {"preflight.json"}


def test_freeze_then_fake_sequential_execution_binds_state_before_mechanism_and_settles_aggregate_only(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    result = s.freeze(source, packet)
    contract, evidence_root = _adapter_roots(s, tmp_path, packet)
    assert result == {"status": "INCOMPLETE", "model_contact_processes_started": 0, "selected_fixture_count": 1, "frozen_reviews": 2}
    manifest = json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "INCOMPLETE" and manifest["maximum_model_contact_processes"] == 2
    assert all(len(row["source_slot_commitments"]) == 6 for row in manifest["candidates"])
    state = json.loads(next((packet / "review-plans").glob("*-state.json")).read_text(encoding="utf-8"))
    assert state["visibility"]["hidden"] == ["label", "verdicts", "arm", "appendix", "session"]
    assert "source_judgment" not in json.dumps(state["material"])
    mechanism = json.loads(next((packet / "review-plans").glob("*-mechanism.json")).read_text(encoding="utf-8"))
    assert len(mechanism["material"]["anonymized_receipts"]) == 6
    assert {row["variant"] for row in mechanism["material"]["anonymized_receipts"]} == {"variant-a", "variant-b"}
    assert tuple(mechanism["response_contract"]["classification"]) == s.MECHANISM_CLASSIFICATIONS
    public = (packet / "public-aggregate.json").read_text(encoding="utf-8")
    assert "H01" not in public and "H02" not in public and json.loads(public)["bound_receipts"] == 6
    disclosure = json.loads((packet / "remote-disclosure.json").read_text(encoding="utf-8"))
    assert disclosure["endpoint_profile"]["destination"] == "Codex CLI -> authenticated OpenAI service"
    assert disclosure["expected_ledger_sent"] is False and "sealed expected ledger" in disclosure["excluded_materials"]
    assert len(disclosure["candidate_transmissions"][0]["mechanism_review_transmission"]["anonymized_six_receipts"]) == 6
    assert s.dry_run(source, packet) == {"status": "INCOMPLETE", "model_contact_processes_started": 0, "drift": [], "mode": "dry_run"}
    calls = []

    def fake_runner(request):
        calls.append(request)
        if request["review_type"] == "state_review":
            return _adapter_result(s, request, {"judgment_state": "YES", "evidence": "fixture evidence"}, contract_path=contract, evidence_root=evidence_root)
        else:
            assert request["material"]["blinded_state_judgment"]["output"]["judgment_state"] == "YES"
            return _adapter_result(s, request, {"classification": "SAME_INPUT_VARIANCE", "evidence": "receipt evidence"}, contract_path=contract, evidence_root=evidence_root)

    with pytest.raises(ValueError, match="arming"):
        s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    armed = s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=contract)
    assert armed["status"] == "ARMED" and armed["model_contact_processes_started"] == 0
    executed = s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    assert executed["requested_model_contact_processes"] == 2
    assert executed["observed_model_contact_processes_started"] == 2
    assert executed["provider_http_attempts_observed"] is None
    assert [call["review_type"] for call in calls] == ["state_review", "mechanism_review"]
    assert all(call["model"]["enabled"] is True for call in calls)
    settled = s.settle(source, packet, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    assert settled["status"] == "SETTLED_AGGREGATE_ONLY" and settled["review_count"] == 2
    assert settled["mechanism_classifications"]["SAME_INPUT_VARIANCE"] == 1
    assert "H01" not in json.dumps(settled) and "H02" not in json.dumps(settled)
    successor = json.loads((packet / "public-aggregate.settled.v1.json").read_text(encoding="utf-8"))
    assert successor["status"] == "SETTLED_AGGREGATE_ONLY" and json.loads(public)["status"] == "INCOMPLETE"
    extra = packet / "review-runs" / executed["review_ids"][0] / "attempt-lifecycle" / "batch-0001" / "attempt-0002.settled.json"
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="run tree"):
        s._validate_review_receipt(packet, executed["review_ids"][0])
    assert s.settle(source, packet, adapter_contract_path=contract, adapter_evidence_root=evidence_root)["status"] == "INCOMPLETE"


def test_state_output_cannot_carry_provider_metadata_into_mechanism() -> None:
    s = study()
    request = {"review_id": "test-state", "review_type": "state_review"}
    with pytest.raises(ValueError, match="state review output"):
        s._validate_adapter_result(_adapter_result(s, request, {"judgment_state": "YES", "evidence": "quote", "session_id": "leak"}), request)
    with pytest.raises(ValueError, match="prohibited provider metadata"):
        s._validate_adapter_result(_adapter_result(s, request, {"judgment_state": "YES", "evidence": "session_id: leak"}), request)


def test_mechanism_adapter_output_requires_exact_keys_and_nonempty_string_evidence() -> None:
    s = study()
    request = {"review_id": "test-mechanism", "review_type": "mechanism_review"}
    with pytest.raises(ValueError, match="mechanism review taxonomy"):
        s._validate_adapter_result(_adapter_result(s, request, {"classification": "SAME_INPUT_VARIANCE", "evidence": 3}), request)
    with pytest.raises(ValueError, match="mechanism review taxonomy"):
        s._validate_adapter_result(_adapter_result(s, request, {"classification": "SAME_INPUT_VARIANCE", "evidence": "ok", "extra": True}), request)
    with pytest.raises(ValueError, match="runner envelope"):
        s._validate_adapter_result(_adapter_result(s, request, {"classification": "SAME_INPUT_VARIANCE", "evidence": "ok"}, extra={"unexpected": True}), request)


def test_ambiguous_adapter_result_freezes_terminal_receipt_and_blocks_later_callbacks(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    contract, evidence_root = _adapter_roots(s, tmp_path, packet)
    s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=contract)
    calls = []

    def ambiguous_runner(request):
        calls.append(request)
        return _adapter_result(s, request, None, status="AMBIGUOUS_NO_RETRY", contract_path=contract, evidence_root=evidence_root)

    with pytest.raises(ValueError, match="AMBIGUOUS_NO_RETRY"):
        s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=ambiguous_runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    assert len(calls) == 1
    terminal = json.loads((packet / "ambiguity-receipt.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "AMBIGUOUS_NO_RETRY" and terminal["retries"] == 0
    with pytest.raises(ValueError, match="terminal AMBIGUOUS_NO_RETRY"):
        s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=ambiguous_runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    assert len(calls) == 1


def test_success_namespace_rejects_extra_adapter_evidence_file(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    contract, evidence_root = _adapter_roots(s, tmp_path, packet)
    s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=contract)

    def runner(request):
        output = {"judgment_state": "YES", "evidence": "fixture evidence"} if request["review_type"] == "state_review" else {"classification": "SAME_INPUT_VARIANCE", "evidence": "receipt evidence"}
        return _adapter_result(s, request, output, contract_path=contract, evidence_root=evidence_root)

    executed = s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    evidence = packet / "review-runs" / executed["review_ids"][0] / "external-evidence.extra.json"
    evidence.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected top-level"):
        s._validate_review_receipt(packet, executed["review_ids"][0])


def test_stable_root_state_accepted_then_mechanism_precontact_then_mechanism_accepted(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    contract, evidence_root = _adapter_roots(s, tmp_path, packet)
    s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=contract)
    calls = []

    def first_runner(request):
        calls.append(request)
        if request["review_type"] == "state_review":
            return _adapter_result(s, request, {"judgment_state": "YES", "evidence": "fixture evidence"}, contract_path=contract, evidence_root=evidence_root)
        return _adapter_result(s, request, None, status="PRECONTACT_FAILED_NO_MODEL_CONTACT", contract_path=contract, evidence_root=evidence_root)

    first = s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=first_runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    assert first["status"] == "PRECONTACT_FAILED_NO_MODEL_CONTACT" and first["model_contact_processes_started"] == 1
    assert [call["review_type"] for call in calls] == ["state_review", "mechanism_review"]
    state_id, mechanism_id = s._expected_review_ids(json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8")))
    assert (packet / "review-runs" / state_id / "receipt.json").is_file()
    assert not (packet / "review-runs" / mechanism_id).exists()

    def accepted_runner(request):
        calls.append(request)
        assert request["review_type"] == "mechanism_review"
        return _adapter_result(s, request, {"classification": "SAME_INPUT_VARIANCE", "evidence": "receipt evidence"}, contract_path=contract, evidence_root=evidence_root, attempt_id="attempt-0002")

    second = s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted_runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    assert second["status"] == "EXECUTED_PENDING_SETTLEMENT" and second["observed_model_contact_processes_started"] == 2
    assert [call["review_type"] for call in calls] == ["state_review", "mechanism_review", "mechanism_review"]


def test_contract_and_private_evidence_hash_mutation_are_rejected(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    contract, evidence_root = _adapter_roots(s, tmp_path, packet)
    s.arm(source, packet, confirm_pre_execution_contract=True, adapter_contract_path=contract)

    def runner(request):
        output = {"judgment_state": "YES", "evidence": "fixture evidence"} if request["review_type"] == "state_review" else {"classification": "SAME_INPUT_VARIANCE", "evidence": "receipt evidence"}
        return _adapter_result(s, request, output, contract_path=contract, evidence_root=evidence_root)

    executed = s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)
    external_path = evidence_root / executed["review_ids"][0] / "attempts" / "attempt-0001" / "external-evidence.json"
    external = json.loads(external_path.read_text(encoding="utf-8"))
    external["output_sha256"] = "0" * 64
    external_path.write_text(json.dumps(external), encoding="utf-8")
    assert s.settle(source, packet, adapter_contract_path=contract, adapter_evidence_root=evidence_root)["status"] == "INCOMPLETE"
    contract.write_text('{"mutated":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="adapter contract file drifted"):
        s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=runner, adapter_contract_path=contract, adapter_evidence_root=evidence_root)


def test_review_namespace_rejects_an_unexpected_global_run_id(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    (packet / "review-runs" / "unexpected-review").mkdir(parents=True)
    manifest = json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="unexpected review-run"):
        s._validate_review_namespace(packet, manifest, require_all=False)


def test_any_source_or_packet_drift_is_incomplete(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    response = next((source / "runs").glob("*/responses/batch-0001.json"))
    response.write_text("{}", encoding="utf-8")
    result = s.verify(source, packet)
    assert result["status"] == "INCOMPLETE" and result["drift"]
