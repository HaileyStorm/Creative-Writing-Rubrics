from __future__ import annotations

import builtins
import json
import os
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-v1"
executor = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_v1")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}


@pytest.fixture(scope="module")
def schedule_and_v3():
    v3 = executor._load_v3()
    return executor.derive_schedule(**ROOTS), v3


@pytest.fixture(autouse=True)
def trusted_private_seams(monkeypatch):
    monkeypatch.setattr(executor, "_load_pinned_gate_verifier", lambda: lambda _event: {"accepted": True})
    def receipt(event):
        evidence = event.get("identity", {})
        if evidence.get("route_name") == executor.SOL_ROUTE["route_name"]:
            return {
                "accepted": True,
                "attested_contact_id": evidence["contact_id"],
                "attested_session_id": evidence["session_id"],
                "attestation_scope": "local_codex_contact_and_session_binding_not_provider_model_attestation",
            }
        return {"accepted": True}
    monkeypatch.setattr(executor, "_load_pinned_native_request_verifier", lambda: receipt)


def response(scores: dict[str, float] | None = None) -> dict:
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    return {
        "scores": scores or {name: 3.0 for name in dimensions},
        "evidence": {name: "observed" for name in dimensions},
        "coverage": {name: True for name in dimensions},
    }


def identity(row: dict, index: int) -> dict:
    route = row["route"]
    return {
        "provider": route["provider"],
        "route_name": route["route_name"],
        "requested_model": route["requested_model"],
        "requested_reasoning_effort": route["requested_reasoning_effort"],
        "effective_model": route["effective_model"],
        "provider_reported_model": route["provider_reported_model"],
        "identity_evidence": route["identity_evidence"],
        "reasoning_attested": False,
        "transport_identity": route["transport_identity"],
        "contact_id": f"contact-{index}",
        "session_id": f"session-{index}",
    }


def settings(row: dict) -> dict:
    route = row["route"]
    return {
        "route_name": route["route_name"],
        "effective_model": route["effective_model"],
        "requested_reasoning_effort": route["requested_reasoning_effort"],
        "tools_enabled": False,
        "web_search_enabled": False,
        "subagents_enabled": False,
        "output_schema_sha256": row["response_schema_sha256"],
        "provider_attested": False,
        "source": "grok_cli_invocation_and_envelope_v1" if row["route_name"] == "grok_primary" else "codex_cli_local_events_and_invocation_v1",
    }


def native_response(row: dict, index: int, scores: dict[str, float] | None = None) -> bytes:
    output = response(scores)
    if row["route_name"] == "grok_primary":
        return executor.canonical({
            "modelUsage": {"grok-4.6-build": {}},
            "stopReason": "end_turn",
            "num_turns": 1,
            "sessionId": f"session-{index}",
            "requestId": f"contact-{index}",
            "structuredOutput": output,
        })
    return executor.canonical(output)


def gate_files(tmp_path: Path, schedule: dict, row: dict, payload: bytes) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    disclosure = executor._disclosure(row=row, schedule=schedule, payload=payload)
    common = {
        "format_version": 1,
        "study_id": executor.STUDY_ID,
        "cell_id": row["cell_id"],
        "disclosure_sha256": executor.digest(disclosure),
        "acknowledged": True,
        "attestor": "provider-free-test",
    }
    acknowledgement = tmp_path / "acknowledgement.json"
    proof = tmp_path / "zero-charge-route-proof.json"
    acknowledgement.write_bytes(executor.canonical({**common, "kind": "acknowledgement"}))
    proof.write_bytes(executor.canonical({
        **common,
        "kind": "zero_charge_route_proof",
        "route_descriptor_sha256": executor.digest(row["route"]),
        "account_class": "subscription",
        "zero_charge_only": True,
        "paid_fallback_forbidden": True,
        "api_fallback_forbidden": True,
    }))
    return acknowledgement, proof


def use_frozen_schedule(monkeypatch, schedule: dict, v3, *, fake_payload: bool = False) -> None:
    monkeypatch.setattr(executor, "derive_schedule", lambda **_roots: schedule)
    monkeypatch.setattr(executor, "_load_v3", lambda: v3)
    if fake_payload:
        monkeypatch.setattr(
            executor,
            "_payload",
            lambda _v3, row, **_roots: executor.canonical({
                "format_version": 1,
                "study_id": executor.STUDY_ID,
                "fixture_item": row["item_id"],
                "fixture_candidate": row["candidate_id"],
            }),
        )


def prepare(tmp_path: Path, schedule: dict, v3, row: dict) -> None:
    payload = executor._payload(v3, row, **ROOTS)
    acknowledgement, proof = gate_files(tmp_path / "gates" / row["cell_id"], schedule, row, payload)
    executor.prepare_cell(
        **ROOTS,
        cell_id=row["cell_id"],
        output_root=tmp_path / "native",
        acknowledgement_path=acknowledgement,
        route_proof_path=proof,
    )


def test_frozen_geometry_exact_cross_route_bytes_and_confirmation_unopened(schedule_and_v3) -> None:
    schedule, v3 = schedule_and_v3
    mandatory = schedule["mandatory_development"]
    training = schedule["optional_training_pool"]["cells"]
    assert len(mandatory) == 100
    assert sum(row["route_name"] == "grok_primary" for row in mandatory) == 65
    assert sum(row["route_name"] == "sol_validation" for row in mandatory) == 35
    assert len(training) == 360 and schedule["optional_training_pool"]["status"].endswith("not_runtime_dispatchable")
    assert schedule["confirmation"] == {"status": "unopened", "scheduled_cells": 0}
    grok = {(row["item_id"], row["candidate_id"]): row for row in mandatory if row["route_name"] == "grok_primary"}
    sol = next(row for row in mandatory if row["route_name"] == "sol_validation")
    left, right = grok[(sol["item_id"], sol["candidate_id"])], sol
    assert executor._payload(v3, left, **ROOTS) == executor._payload(v3, right, **ROOTS)
    with pytest.raises(ValueError, match="training is optional and confirmation is unopened"):
        executor._cell(schedule, training[0]["cell_id"])
    with pytest.raises(ValueError, match="confirmation"):
        executor._cell(schedule, "confirmation-never-scheduled")


def test_route_relabel_and_tool_mutation_are_rejected(schedule_and_v3) -> None:
    schedule, _v3 = schedule_and_v3
    grok = next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary")
    sol = next(row for row in schedule["mandatory_development"] if row["route_name"] == "sol_validation")
    wrong = identity(sol, 1)
    wrong["provider"] = "openai"
    wrong["provider_reported_model"] = "gpt-5.6-sol"
    with pytest.raises(ValueError, match="relabelled"):
        executor._validate_identity(wrong, sol)
    wrong_grok = identity(grok, 2)
    wrong_grok["provider_reported_model"] = "grok-4.6"
    with pytest.raises(ValueError, match="relabelled"):
        executor._validate_identity(wrong_grok, grok)
    changed = settings(sol)
    changed["tools_enabled"] = True
    with pytest.raises(ValueError, match="effective settings drifted"):
        executor._validate_effective_settings(changed, sol)


def test_one_cell_per_route_contact_counters_and_no_resend(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    use_frozen_schedule(monkeypatch, schedule, v3)
    rows = [
        next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary"),
        next(row for row in schedule["mandatory_development"] if row["route_name"] == "sol_validation"),
    ]
    for row in rows:
        prepare(tmp_path, schedule, v3, row)
    calls: list[str] = []

    def runner(row, payload, before_contact):
        calls.append(row["cell_id"])
        before_contact()
        index = len(calls)
        return {
            "request_bytes": b"native-request:" + payload,
            "response_bytes": native_response(row, index),
            "identity": identity(row, index),
            "effective_settings": settings(row),
        }

    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: runner)
    for row in rows:
        first = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id=row["cell_id"], allow_remote=True)
        second = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id=row["cell_id"], allow_remote=True)
        assert first["state"] == "native_returned_unprojected" and first["provider_calls_made"] == 1
        assert second["provider_calls_made"] == 0 and second["resumed"] is True
    assert calls == [row["cell_id"] for row in rows]


def test_confirmation_fails_before_contact_and_ambiguous_contact_never_resends(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    use_frozen_schedule(monkeypatch, schedule, v3)
    row = schedule["mandatory_development"][0]
    prepare(tmp_path, schedule, v3, row)
    calls = []

    def runner(_row, _payload, before_contact):
        calls.append("contact")
        before_contact()
        raise TimeoutError("ambiguous after launch")

    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: runner)
    first = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id=row["cell_id"], allow_remote=True)
    second = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id=row["cell_id"], allow_remote=True)
    assert first["state"] == "reconcile_required" and second["provider_calls_made"] == 0
    assert calls == ["contact"]
    with pytest.raises(ValueError, match="confirmation"):
        executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id="confirmation-never-scheduled", allow_remote=True)
    assert calls == ["contact"]


def test_orphan_contact_artifact_and_malformed_resume_fail_closed(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    use_frozen_schedule(monkeypatch, schedule, v3)
    first, second = schedule["mandatory_development"][:2]
    prepare(tmp_path, schedule, v3, first)
    (tmp_path / "native" / first["cell_id"] / "native-response.bin").write_bytes(b"orphan")
    calls = []
    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: calls.append("runner"))
    with pytest.raises(ValueError, match="orphan or partial contact artifacts"):
        executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id=first["cell_id"], allow_remote=True)
    assert calls == []

    prepare(tmp_path, schedule, v3, second)
    root = tmp_path / "native" / second["cell_id"]
    prepared = executor._read_canonical(root / "prepared.json", label="prepared")
    intent_value = executor._expected_intent(second, prepared)
    (root / "intent.json").write_bytes(executor.canonical(intent_value))
    malformed = {
        "format_version": 1,
        "study_id": executor.STUDY_ID,
        "kind": "native_subscription_cell_result",
        "state": "completed",
        "cell_id": second["cell_id"],
        "intent_sha256": executor.digest(intent_value),
        "error_type": "TimeoutError",
        "provider_calls_made": 1,
    }
    (root / "result.json").write_bytes(executor.canonical(malformed))
    with pytest.raises(ValueError, match="malformed reconciliation result"):
        executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "native", cell_id=second["cell_id"], allow_remote=True)
    assert calls == []


def test_reparse_ancestor_is_rejected_when_supported(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    use_frozen_schedule(monkeypatch, schedule, v3)
    row = schedule["mandatory_development"][0]
    prepare(tmp_path, schedule, v3, row)
    linked = tmp_path / "linked-native"
    try:
        os.symlink(tmp_path / "native", linked, target_is_directory=True)
    except OSError as error:
        if os.name == "nt" and getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise
    with pytest.raises(ValueError, match="reparse point is forbidden"):
        executor._verify_root(**ROOTS, output_root=linked, cell_id=row["cell_id"], allow_contact_files=False)


def test_contract_bytes_and_full_semantics_are_immutable(tmp_path: Path, monkeypatch) -> None:
    original = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    mutated = dict(original)
    mutated["result_authority"] = "empirical"
    path = tmp_path / "mutated-contract.json"
    path.write_bytes(executor.canonical(mutated))
    monkeypatch.setattr(executor, "CONTRACT_PATH", path)
    with pytest.raises(ValueError, match="contract bytes drifted"):
        executor.contract()


def test_grok_id_swap_and_sol_receipt_denial_are_rejected(schedule_and_v3, monkeypatch) -> None:
    schedule, _v3 = schedule_and_v3
    grok = next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary")
    grok_identity = identity(grok, 1)
    swapped = executor.canonical({
        "modelUsage": {"grok-4.6-build": {}},
        "stopReason": "end_turn",
        "num_turns": 1,
        "sessionId": "different-session",
        "requestId": "different-contact",
        "structuredOutput": response(),
    })
    with pytest.raises(ValueError, match="contact/session identity is misassociated"):
        executor._extract_native(swapped, row=grok, identity=grok_identity)

    sol = next(row for row in schedule["mandatory_development"] if row["route_name"] == "sol_validation")
    sol_identity = identity(sol, 2)
    monkeypatch.setattr(executor, "_load_pinned_native_request_verifier", lambda: lambda _event: {"accepted": True})
    with pytest.raises(ValueError, match="Sol local contact/session receipt"):
        executor._verify_native_request_receipt(row=sol, identity=sol_identity, event={"identity": sol_identity})


def test_projection_uses_all_persisted_cells_then_rejects_duplicate_and_misassociation(
    schedule_and_v3, tmp_path: Path, monkeypatch
) -> None:
    schedule, v3 = schedule_and_v3
    use_frozen_schedule(monkeypatch, schedule, v3, fake_payload=True)
    targets = executor._targets(v3=v3, schedule=schedule, **ROOTS)
    contacts = []

    def runner(row, payload, before_contact):
        index = len(contacts) + 1
        contacts.append(row["cell_id"])
        before_contact()
        return {
            "request_bytes": b"native-request:" + payload,
            "response_bytes": native_response(row, index, targets[row["item_id"]]),
            "identity": identity(row, index),
            "effective_settings": settings(row),
        }

    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: runner)
    for row in schedule["mandatory_development"]:
        prepare(tmp_path, schedule, v3, row)
        outcome = executor.dispatch_prepared_cell(
            **ROOTS, output_root=tmp_path / "native", cell_id=row["cell_id"], allow_remote=True
        )
        assert outcome["state"] == "native_returned_unprojected"
    assert len(contacts) == 100
    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: (_ for _ in ()).throw(AssertionError("projection contacted provider")))
    projected = executor.project_mandatory_cells(**ROOTS, output_root=tmp_path / "native")
    assert projected["completed_cells"] == 100
    assert projected["confirmation"] == {"status": "unopened", "scheduled_cells": 0}
    assert projected["optional_training_pool"]["scheduled_cells"] == 0
    assert projected["empirical_authority"].startswith("development_evidence_only")

    first, second = schedule["mandatory_development"][:2]
    first_result = executor._read_canonical(tmp_path / "native" / first["cell_id"] / "result.json", label="first")
    second_path = tmp_path / "native" / second["cell_id"] / "result.json"
    second_result = executor._read_canonical(second_path, label="second")
    duplicate = dict(second_result["identity"])
    duplicate["contact_id"] = first_result["identity"]["contact_id"]
    duplicate["session_id"] = first_result["identity"]["session_id"]
    second_result["identity"] = duplicate
    second_result["identity_sha256"] = executor.digest(duplicate)
    second_path.write_bytes(executor.canonical(second_result))
    with pytest.raises(ValueError, match="duplicated"):
        executor.project_mandatory_cells(**ROOTS, output_root=tmp_path / "native")

    grok = first
    bad_envelope = executor.canonical({
        "modelUsage": {"grok-4.6": {}},
        "stopReason": "end_turn",
        "num_turns": 1,
        "sessionId": "session",
        "requestId": "request",
        "structuredOutput": response(),
    })
    with pytest.raises(ValueError):
        executor._extract_native(bad_envelope, row=grok, identity=identity(grok, 999))
    sol = next(row for row in schedule["mandatory_development"] if row["route_name"] == "sol_validation")
    with pytest.raises(ValueError, match="structured response schema drifted"):
        executor._extract_native(executor.canonical({"output": response()}), row=sol, identity=identity(sol, 1000))


def test_runtime_has_no_dspy_or_optuna_dependency(monkeypatch) -> None:
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("optimizer import is forbidden at runtime")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8")
    assert "import dspy" not in source and "import optuna" not in source
    assert executor._load_pinned_runner.__name__ == "_load_pinned_runner"
