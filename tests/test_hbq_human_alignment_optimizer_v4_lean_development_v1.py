from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-lean-development-v1"
optimizer = load_module(PACKAGE / "optimizer.py", name="hanna_v4_lean_development_v1")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
REAL_SOL_CELL_ROOT = DOCUMENTS / "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-c3e02c02a94115ae" / "v4-cell-c3e02c02a94115ae"


@pytest.fixture(scope="module")
def frozen():
    native = optimizer._load_native()
    schedule = optimizer.freeze_lean_schedule(**ROOTS)
    return schedule, native


def _identity(row: dict, index: int) -> dict:
    route = row["route"]
    grok = row["route_name"] == "grok_primary"
    result = {
        "provider": route["provider"],
        "route_name": route["route_name"],
        "requested_model": route["requested_model"],
        "requested_reasoning_effort": route["requested_reasoning_effort"],
        "effective_model": route["effective_model"],
        "provider_reported_model": route["provider_reported_model"],
        "identity_evidence": route["identity_evidence"],
        "reasoning_attested": False,
        "transport_identity": route["transport_identity"],
        "contact_id": f"request-{index}" if grok else f"unproven-native-endpoint-contact-for-local-thread:fixture-{index}",
        "session_id": f"session-{index}" if grok else f"local-codex-thread-session:fixture-{index}",
    }
    if not grok:
        result["identity_evidence"] = "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested"
        result["transport_identity"] = "codex_chatgpt_subscription_exec_tool_free_v3"
    return result


def _response(row: dict, identity: dict, targets: dict[str, dict[str, float]]) -> bytes:
    scores = dict(targets[row["item_id"]])
    structured = {
        "scores": scores,
        "evidence": {name: "persisted fixture observation" for name in optimizer.DIMENSIONS},
        "coverage": {name: True for name in optimizer.DIMENSIONS},
    }
    if row["route_name"] == "sol_validation":
        return optimizer.canonical(structured)
    return optimizer.canonical({
        "modelUsage": {"grok-4.6-build": {}},
        "stopReason": "end_turn",
        "num_turns": 1,
        "sessionId": identity["session_id"],
        "requestId": identity["contact_id"],
        "structuredOutput": structured,
    })


def _evidence(tmp_path: Path, schedule: dict, native, *, stage: str = "training", rows=None) -> Path:
    rows = list(rows or optimizer._expected_rows(schedule, stage))
    targets = optimizer._targets(native, rows, **ROOTS)
    v3 = native._load_v3()
    cells = []
    for index, row in enumerate(rows):
        cells.append({
            "cell_id": row["cell_id"],
            "evidence_kind": "admitted_grok" if row["route_name"] == "grok_primary" else "sol_exec_v3",
            "execution_root": str(tmp_path / f"root-{index}"),
            "proof_path": str(tmp_path / f"proof-{index}.json") if row["route_name"] == "grok_primary" else None,
            "queue_root": None if row["route_name"] == "grok_primary" else str(tmp_path / "queue"),
        })
    value = {
        "format_version": 1,
        "study_id": optimizer.STUDY_ID,
        "kind": "verified_persisted_native_cells",
        "schedule_sha256": schedule["schedule_sha256"],
        "stage": stage,
        "cells": cells,
    }
    path = tmp_path / f"{stage}-evidence.json"
    path.write_bytes(optimizer.canonical(value))
    return path


def _fixture_verifier(native, schedule, *, stage="training", rows=None):
    expected = list(rows or optimizer._expected_rows(schedule, stage))
    targets = optimizer._targets(native, expected, **ROOTS)
    v3 = native._load_v3()
    by_cell = {row["cell_id"]: (index, row) for index, row in enumerate(expected)}

    def verify(reference, row, *, frozen_successor_path, hanna_csv_path):
        index, expected_row = by_cell[reference["cell_id"]]
        assert expected_row == row
        payload = native._payload(v3, row, **ROOTS)
        request = json.loads(payload.decode("utf-8"))["components"]["task_payload"].encode("utf-8")
        identity = _identity(row, index)
        return request, _response(row, identity, targets), identity
    return verify


def _verified(event: dict) -> dict:
    suffix = event["cell"]["cell_id"].encode("utf-8")
    return {
        **event["expected"],
        "prepared_sha256": hashlib.sha256(b"prepared-" + suffix).hexdigest(),
        "intent_sha256": hashlib.sha256(b"intent-" + suffix).hexdigest(),
        "result_sha256": hashlib.sha256(b"result-" + suffix).hexdigest(),
    }


def test_freezes_lean_geometry_and_endpoint_disjointness(frozen) -> None:
    schedule, _native = frozen
    assert schedule["geometry"] == {
        "training": {"grok_cells": 25, "sol_cells": 10, "items": 5, "prompt_groups": 5},
        "grok_development": {"cells": 65, "items": 13, "prompt_groups": 7},
        "sol_validation_after_freeze": {"cells": 7, "items": 7, "prompt_groups": 7},
        "confirmation": {"cells": 0, "status": "unopened"},
    }
    partitions = schedule["partitions"]
    train = [*partitions["training"]["grok"], *partitions["training"]["sol_sprinkled"]]
    development = [*partitions["grok_development"], *partitions["sol_validation_templates"]]
    assert not ({row["item_id"] for row in train} & {row["item_id"] for row in development})
    assert not ({row["prompt_group_id"] for row in train} & {row["prompt_group_id"] for row in development})
    assert partitions["confirmation"] == {"status": "unopened", "cells": []}
    assert len(schedule["candidate_ids"]) == 5
    prepared = optimizer.prepare_training_collection(**ROOTS)
    assert prepared["provider_calls_made"] == 0
    assert prepared["dispatch_authority"] == "none_governed_runner_or_adapter_required"
    assert [cell["cell_id"] for cell in prepared["cells"]] == [row["cell_id"] for row in train]


def test_provider_preflight_fails_closed_and_makes_zero_calls(frozen) -> None:
    schedule, _native = frozen
    with pytest.raises(ValueError, match="no enabled live provider route inspector"):
        optimizer.preflight_live_execution(**ROOTS)
    inspected = []

    def inspector(route: dict) -> dict:
        inspected.append(route["route_name"])
        return {
            "accepted": True,
            "route_sha256": optimizer.sha256(route),
            "provider_calls_made": 0,
        }

    result = optimizer.preflight_live_execution(**ROOTS, route_inspector=inspector)
    assert set(inspected) == {"grok-build-grok-4.6", "codex-chatgpt-gpt-5.6-sol"}
    assert result["schedule_sha256"] == schedule["schedule_sha256"]
    assert result["provider_calls_made"] == 0 and result["dispatch_authority"] == "none_preflight_only"


def test_real_optuna_search_uses_only_verified_training_and_opens_seven_sol_rows(
    frozen, tmp_path: Path, monkeypatch
) -> None:
    schedule, native = frozen
    evidence = _evidence(tmp_path, schedule, native)
    with pytest.raises(ValueError, match="admitted Grok proof"):
        optimizer.optimize_training_evidence(**ROOTS, training_evidence_path=evidence)
    monkeypatch.setattr(optimizer, "_verify_persisted_cell", _fixture_verifier(native, schedule))
    result = optimizer.optimize_training_evidence(
        **ROOTS, training_evidence_path=evidence, seed=17
    )
    assert result["optimizer"] == "optuna.GridSampler@4.9.0"
    assert result["training_evidence_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert result["frozen_candidate_id"] in schedule["candidate_ids"]
    assert result["confirmation"] == {"status": "unopened", "cells": 0}
    grok_gate = {
        "schedule_sha256": schedule["schedule_sha256"], "frozen_candidate_id": result["frozen_candidate_id"],
        "status": "validated_no_substitution",
    }
    monkeypatch.setattr(optimizer, "validate_grok_development", lambda **_kwargs: grok_gate)
    rows = optimizer.sol_validation_rows(
        schedule, result, **ROOTS, training_evidence_path=evidence, seed=17,
        grok_development_result=grok_gate, grok_development_evidence_path=tmp_path / "grok-development.json",
        minimum_macro_spearman=0.0,
    )
    assert len(rows) == 7 and {row["candidate_id"] for row in rows} == {result["frozen_candidate_id"]}
    grok = {
        (row["item_id"], row["candidate_id"]): row
        for row in schedule["partitions"]["grok_development"]
    }
    for row in rows:
        matched = grok[(row["item_id"], row["candidate_id"])]
        assert all(row[field] == matched[field] for field in optimizer.PROMPT_FIELDS)


def test_rejects_aggregates_synthetic_shapes_and_partition_relabelling(
    frozen, tmp_path: Path, monkeypatch
) -> None:
    schedule, native = frozen
    evidence = _evidence(tmp_path, schedule, native)
    monkeypatch.setattr(optimizer, "_verify_persisted_cell", _fixture_verifier(native, schedule))
    value = json.loads(evidence.read_text(encoding="utf-8"))
    value["cells"][0] = {"aggregate": {"macro_spearman": 1.0}}
    evidence.write_bytes(optimizer.canonical(value))
    with pytest.raises(ValueError, match="caller aggregates, raw bytes, or synthetic results"):
        optimizer.optimize_training_evidence(**ROOTS, training_evidence_path=evidence)
    evidence = _evidence(tmp_path, schedule, native)
    value = json.loads(evidence.read_text(encoding="utf-8"))
    value["cells"][0]["cell_id"] = schedule["partitions"]["grok_development"][0]["cell_id"]
    evidence.write_bytes(optimizer.canonical(value))
    with pytest.raises(ValueError, match="cell order or partition binding"):
        optimizer.optimize_training_evidence(**ROOTS, training_evidence_path=evidence)


def test_sol_exec_v3_identity_is_local_lifecycle_only(frozen) -> None:
    schedule, _native = frozen
    row = schedule["partitions"]["training"]["sol_sprinkled"][0]
    identity = _identity(row, 7)
    assert optimizer._validate_sol_v3_identity(identity, row) == identity
    relabelled = dict(identity)
    relabelled["transport_identity"] = row["route"]["transport_identity"]
    with pytest.raises(ValueError, match="Sol exec-v3 local-lifecycle identity"):
        optimizer._validate_sol_v3_identity(relabelled, row)


@pytest.mark.skipif(not REAL_SOL_CELL_ROOT.is_dir(), reason="current local Sol exec-v3 receipt fixture is unavailable")
def test_real_sol_exec_v3_receipt_identity_canary() -> None:
    native = optimizer._load_native()
    schedule = native.derive_schedule(**ROOTS)
    row = native._cell(schedule, "v4-cell-c3e02c02a94115ae")
    receipt = json.loads((REAL_SOL_CELL_ROOT / "execution-receipt.json").read_text(encoding="utf-8"))
    assert optimizer._validate_sol_v3_identity(receipt["identity"], row) == receipt["identity"]
    assert receipt["native_contact_proven"] is False
    assert receipt["native_endpoint_contact_cardinality"] == "unproven"


def test_dspy_331_program_produces_versioned_descendant_without_authority(frozen, monkeypatch) -> None:
    _schedule, native = frozen
    v3 = native._load_v3()
    parent = v3.candidate_pack()[0]
    program = optimizer.build_dspy_descendant_program()
    proposed_instruction = parent["instruction_bytes"] + b"\nLean DSPy development descendant."
    proposed_profile = optimizer.canonical({"proposal": "training-only fixture"})
    calls = []

    def fake_predict(**inputs):
        calls.append(inputs)
        return SimpleNamespace(
            descendant_instruction_base64=base64.b64encode(proposed_instruction).decode("ascii"),
            descendant_profile_base64=base64.b64encode(proposed_profile).decode("ascii"),
        )

    program.predict = fake_predict
    training_result = {"result_sha256": "a" * 64}
    diagnostics = {"training_result_sha256": "a" * 64}
    context = {
        "parent": parent, "training_result": training_result,
        "training_result_bytes": optimizer.canonical(training_result),
        "training_diagnostics": diagnostics,
        "training_diagnostics_bytes": optimizer.canonical(diagnostics),
        "training_diagnostics_sha256": optimizer.sha256_bytes(optimizer.canonical(diagnostics)),
    }
    monkeypatch.setattr(optimizer, "dspy_training_context", lambda **_kwargs: context)
    result = program(
        frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"],
        training_evidence_path=Path("fixture-evidence.json"),
    )
    assert len(calls) == 1 and result["predictor_invoked"] is True
    lineage = result["lineage"]
    assert lineage["dspy_program"] == "Predict(LeanDescendantSignature)@3.3.1"
    assert lineage["runtime_authority"] == "none"
    assert lineage["confirmation_authority"] == "none"
    assert base64.b64decode(result["descendant_instruction_base64"]) != parent["instruction_bytes"]
    assert base64.b64decode(result["descendant_profile_base64"]) == proposed_profile
    assert base64.b64decode(calls[0]["training_result_base64"]) == context["training_result_bytes"]
    assert base64.b64decode(calls[0]["training_diagnostics_base64"]) == context["training_diagnostics_bytes"]
