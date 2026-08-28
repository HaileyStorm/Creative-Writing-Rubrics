from __future__ import annotations

import builtins
import copy
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v1"
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
study = load_module(PACKAGE / "study.py", name="hanna_optimizer_study_v1")
analysis = load_module(PACKAGE / "analyze.py", name="hanna_optimizer_analyze_v1", aliases={"study": study})
harness = load_module(PACKAGE / "offline_harness.py", name="hanna_optimizer_harness_v1", aliases={"study": study})
freeze = load_module(PACKAGE / "execution_freeze.py", name="hanna_optimizer_execution_freeze_v1", aliases={"study": study, "offline_harness": harness})
executor = load_module(PACKAGE / "executor.py", name="hanna_optimizer_executor_v1", aliases={"study": study, "offline_harness": harness, "execution_freeze": freeze})
OPENAI_ENDPOINT = "https://approved.example.invalid/v1/chat/completions"


def _trusted_gate_verifier(event: dict) -> dict:
    assert event["study_id"] == study.CONTRACT["study_id"]
    assert event["gate_kind"] in {"acknowledgement", "zero_charge_route_receipt"}
    assert event["gate_sha256"] == study.hashlib.sha256(event["gate_bytes"]).hexdigest()
    return {"format_version": 1, "study_id": study.CONTRACT["study_id"], "gate_kind": event["gate_kind"], "gate_sha256": event["gate_sha256"], "gate_bytes": len(event["gate_bytes"]), "trusted_verifier_id": "test-deployment-verifier", "trusted_root_id": "test-trusted-gate-root", "verified": True}


def _split() -> dict:
    return study.derive_split_manifest(**ROOTS)


def test_source_bound_map_and_group_disjoint_geometry() -> None:
    mapping = study.derive_eligible_map(**ROOTS)
    study.validate_eligible_map(mapping, **ROOTS)
    split = _split()
    study.validate_split_manifest(split, **ROOTS)
    assert len(mapping) == 80
    assert len({row["prompt_group_id"] for row in mapping}) == 39
    assert study.sha256(mapping) == study.CONTRACT["eligible_universe"]["item_group_map_sha256"]
    assert {name: sum(row["partition"] == name for row in split["items"]) for name in ("train", "development", "confirmation")} == {"train": 48, "development": 13, "confirmation": 19}
    groups = {name: {row["prompt_group_id"] for row in split["groups"] if row["partition"] == name} for name in ("train", "development", "confirmation")}
    assert not (groups["train"] & groups["development"] or groups["train"] & groups["confirmation"] or groups["development"] & groups["confirmation"])


def test_selection_scaffold_is_an_explicit_unimplemented_blocker() -> None:
    with pytest.raises(ValueError, match="unimplemented"):
        study.derive_selection_artifact({"forged": "freeze"}, [{"forged": "result"}], **ROOTS)
    with pytest.raises(ValueError, match="unimplemented"):
        study.validate_selection_artifact({"forged": "selection"}, {"forged": "freeze"}, **ROOTS)


def test_imported_aggregate_is_hard_rejected() -> None:
    with pytest.raises(ValueError, match="non-authoritative"):
        analysis.validate_aggregate({})


def test_optional_optimizer_config_has_no_runtime_backend_dependency(monkeypatch) -> None:
    original_import = builtins.__import__

    def deny_optional_backends(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}:
            raise AssertionError("optional optimizer backend imported at runtime")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_optional_backends)
    assert study.load_optimizer_config()["candidate_generator"]["runtime_dependency"] is False


@pytest.mark.parametrize("kind", ["file", "ancestor", "output"])
def test_synthetic_reparse_points_fail_before_read_or_write(tmp_path: Path, monkeypatch, kind: str) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    if kind == "ancestor":
        target = tmp_path / "ancestor"
        target.mkdir()
        source = target / "source.json"
        source.write_text("{}", encoding="utf-8")
    elif kind == "output":
        target = tmp_path / "output"
        target.mkdir()
    else:
        target = source
    target = Path(os.path.abspath(target))
    actual_lstat = study.os.lstat

    def synthetic_lstat(path, *args, **kwargs):
        metadata = actual_lstat(path, *args, **kwargs)
        if Path(os.path.abspath(path)) == target:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(study.os, "lstat", synthetic_lstat)
    with pytest.raises(ValueError, match="symlink or reparse"):
        if kind == "output":
            study.atomic_output_directory(target, {"result.json": "{}\n"})
        else:
            study.read_json(source)


def test_source_roots_are_explicit_and_rechecked_after_read(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    source = Path(os.path.abspath(source))
    actual_lstat = study.os.lstat
    seen = 0

    def swapped_lstat(path, *args, **kwargs):
        nonlocal seen
        metadata = actual_lstat(path, *args, **kwargs)
        if Path(os.path.abspath(path)) == source:
            seen += 1
            if seen > 1:
                return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(study.os, "lstat", swapped_lstat)
    with pytest.raises(ValueError, match="symlink or reparse"):
        study.read_json(source)
    assert "C:\\Users" not in inspect.getsource(study)


def test_real_symlink_ancestor_is_rejected_or_skipped_without_windows_privilege(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "source.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege is unavailable")
    with pytest.raises(ValueError, match="symlink or reparse"):
        study.read_json(link / "source.json")


def test_offline_harness_derives_six_balanced_canonical_candidates() -> None:
    assert len(harness.legal_factor_tuples()) == 36
    candidates = harness.enumerate_balanced_candidates()
    harness.validate_candidates(candidates)
    assert len(candidates) == 6
    assert len({candidate["candidate_id"] for candidate in candidates}) == 6
    for name, values in study.CONTRACT["candidate_space"]["controls"].items():
        counts = {value: sum(candidate["factors"][name] == value for candidate in candidates) for value in values}
        assert set(counts.values()) == {6 // len(values)}
    assert all(b'"demonstrations":0' in candidate["profile_bytes"] for candidate in candidates)
    assert all(candidate["instruction_bytes"] for candidate in candidates)


def test_offline_harness_ids_bind_exact_instruction_and_profile_bytes() -> None:
    candidate = harness.enumerate_balanced_candidates()[0]
    assert candidate["instruction_sha256"] == study.hashlib.sha256(candidate["instruction_bytes"]).hexdigest()
    assert candidate["profile_sha256"] == study.hashlib.sha256(candidate["profile_bytes"]).hexdigest()
    altered = copy.deepcopy(candidate)
    altered["instruction_bytes"] += b"drift"
    with pytest.raises(ValueError, match="frozen balanced derivation"):
        harness.validate_candidates([altered, *harness.enumerate_balanced_candidates()[1:]])
    assert harness.candidate_bytes_for_model(candidate, "gpt-5.6-sol") == harness.candidate_bytes_for_model(candidate, "grok-4.6")


def test_offline_harness_reuses_authoritative_split_and_has_no_caller_split_or_confirmation_surface() -> None:
    assert harness.validate_authoritative_split(**ROOTS) == study.sha256(_split())
    assert "split_manifest" not in inspect.signature(harness.validate_authoritative_split).parameters
    source = inspect.getsource(harness)
    assert "validate_score_manifest" not in source
    assert "select_sol_candidate" not in source
    assert "confirmation" not in inspect.signature(harness.validate_authoritative_split).parameters


def test_optional_adapters_do_not_import_until_called(monkeypatch) -> None:
    original_import = builtins.__import__

    def deny_optional_backends(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}:
            raise AssertionError("optional optimizer backend imported eagerly")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_optional_backends)
    assert harness.dspy_candidate_wording_adapter_contract()["selection_authority"] == "none"
    with pytest.raises((RuntimeError, AssertionError)):
        harness.optuna_explore_legal_tuples(n_trials=1)


def test_optional_optuna_explores_only_legal_tuples_when_installed() -> None:
    if importlib.util.find_spec("optuna") is None:
        pytest.skip("Optuna is not installed")
    trials = harness.optuna_explore_legal_tuples(n_trials=2)
    assert len(trials) == 2
    assert all(trial in harness.legal_factor_tuples() for trial in trials)


def test_execution_freeze_has_exact_732_cell_geometry_and_public_only_canaries() -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    freeze.validate_execution_freeze(manifest, **ROOTS)
    assert len(manifest["schedule"]) == 732
    assert len({row["cell_id"] for row in manifest["schedule"]}) == 732
    assert {row["partition"] for row in manifest["schedule"]} == {"train", "development"}
    assert len(manifest["canaries"]) == 2
    assert {row["model"] for row in manifest["canaries"]} == {"gpt-5.6-sol", "grok-4.6"}
    assert all(not row["metric_eligible"] and not row["selection_eligible"] for row in manifest["canaries"])
    assert {row["canary_id"] for row in manifest["canaries"]}.isdisjoint({row["cell_id"] for row in manifest["schedule"]})
    assert manifest["confirmation"] == {"status": "structurally_unreachable", "cells": 76}


def test_execution_freeze_rebuilds_identical_sol_and_grok_payload_bytes() -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in manifest["schedule"]:
        grouped.setdefault((row["item_id"], row["candidate_id"]), []).append(row)
    pair = next(rows for rows in grouped.values() if {row["model"] for row in rows} == {"gpt-5.6-sol", "grok-4.6"})
    payloads = [freeze.provider_ready_payload(freeze=manifest, cell_id=row["cell_id"], **ROOTS) for row in pair]
    assert payloads[0] == payloads[1]
    assert all(study.hashlib.sha256(payload).hexdigest() == row["task_payload_sha256"] for payload, row in zip(payloads, pair, strict=True))


def test_execution_freeze_rejects_tamper_reparse_and_any_result_acceptance(monkeypatch) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    altered = copy.deepcopy(manifest)
    altered["schedule"][0]["task_payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash drifted|source-bound"):
        freeze.validate_execution_freeze(altered, **ROOTS)
    disclosure = freeze.execution_disclosure(manifest, **ROOTS)
    assert disclosure["acknowledgement_preview"]["acknowledged"] is False
    assert disclosure["acknowledgement_preview"]["external_owner_attestation_required"] is True
    assert disclosure["future_native_receipt_contract"]["acceptance"] == "requires_exact_raw_wire_and_session_recomputation"
    assert not hasattr(freeze, "validate_result_receipt")
    assert all(route["paid_api"] is False and route["no_charge_proof_required_before_contact"] == "trusted_zero_charge_route_receipt" for route in manifest["routes"])
    altered_candidate = copy.deepcopy(manifest)
    altered_candidate["candidate_commitments"][0]["profile_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="candidate commitments"):
        freeze.validate_execution_freeze(altered_candidate, **ROOTS)
    target = Path(os.path.abspath(ROOTS["hanna_csv_path"]))
    actual_lstat = study.os.lstat

    def reparse_lstat(path, *args, **kwargs):
        metadata = actual_lstat(path, *args, **kwargs)
        if Path(os.path.abspath(path)) == target:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(study.os, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="cannot be read|symlink or reparse"):
        freeze.derive_execution_freeze(**ROOTS)


def test_readme_prepare_and_validate_commands_execute(tmp_path: Path) -> None:
    output = tmp_path / "prepared"
    prepare = [sys.executable, str(PACKAGE / "prepare.py"), "--frozen-successor-contract", str(ROOTS["frozen_successor_path"]), "--hanna-csv", str(ROOTS["hanna_csv_path"]), "--output-dir", str(output)]
    completed = subprocess.run(prepare, cwd=ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    validate = [sys.executable, str(PACKAGE / "validate.py"), "--frozen-successor-contract", str(ROOTS["frozen_successor_path"]), "--hanna-csv", str(ROOTS["hanna_csv_path"]), "--split-manifest", str(output / "split-manifest.json"), "--execution-freeze", str(output / "execution-freeze.json"), "--disclosure", str(output / "preflight-disclosure.json")]
    completed = subprocess.run(validate, cwd=ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr


def _external_execution_gates(tmp_path: Path, manifest: dict, cell: dict) -> tuple[Path, Path, dict]:
    route = freeze.ROUTES[cell["model"]]
    payload = freeze.provider_ready_payload(freeze=manifest, cell_id=cell["cell_id"], **ROOTS)
    disclosure = executor._disclosure(freeze=manifest, cell=cell, route=route, payload=payload, endpoint=OPENAI_ENDPOINT, grok_bin=None)
    acknowledgement = tmp_path / "external-acknowledgement.json"
    acknowledgement.write_bytes(study.canonical({
        "format_version": 1,
        "study_id": study.CONTRACT["study_id"],
        "kind": "local_first_remote_execution",
        "cell_id": cell["cell_id"],
        "disclosure_sha256": study.sha256(disclosure),
        "acknowledged": True,
        "attestor": "external-owner",
    }))
    receipt = tmp_path / "external-zero-charge-route-receipt.json"
    receipt.write_bytes(study.canonical({
        "format_version": 1,
        "study_id": study.CONTRACT["study_id"],
        "kind": "trusted_zero_charge_route_receipt",
        "cell_id": cell["cell_id"],
        "disclosure_sha256": study.sha256(disclosure),
        "provider": route["provider"],
        "model": route["model"],
        "transport_identity": route["transport_identity"],
        "reasoning_effort": route["reasoning_effort"],
        "paid_api": False,
        "no_financial_liability": True,
        "issuer": "trusted-external-route-authority",
    }))
    return acknowledgement, receipt, disclosure


def test_executor_prepares_one_frozen_cell_and_dispatches_once_only(tmp_path: Path, monkeypatch) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = manifest["schedule"][0]
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    output = tmp_path / "prepared"
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    prepared = executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    assert prepared["state"] == "prepared_not_dispatched"
    assert (output / cell["cell_id"] / "acknowledgement.json").read_bytes() == acknowledgement.read_bytes()
    with pytest.raises(ValueError, match="allow-remote"):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=False, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)

    response = {"scores": {dimension: 3 for dimension in freeze.DIMENSIONS}, "evidence": {dimension: "bound local evidence" for dimension in freeze.DIMENSIONS}, "coverage": {dimension: True for dimension in freeze.DIMENSIONS}}
    calls = 0

    def fake_dispatch(**kwargs):
        nonlocal calls
        kwargs["before_provider_attempt"]()
        calls += 1
        return json.dumps(response), {"native_session": "provider-session-1", "model": cell["model"]}

    monkeypatch.setattr(executor, "_dispatch_via_runner", fake_dispatch)
    first = executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    assert first == {"cell_id": cell["cell_id"], "state": "provider_returned_unpromotable", "provider_calls_made": 1, "resumed": False}
    settled = json.loads((output / cell["cell_id"] / "result" / "attempt-result.json").read_text(encoding="utf-8"))
    assert settled["route_evidence"] == {"evidence_class": "development_selector_candidate_not_promotable", "reasoning_attested": None, "reasoning_attestation": "not_applicable"}
    second = executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    assert second["resumed"] is True and second["provider_calls_made"] == 0
    assert calls == 1


def test_executor_rejects_forged_gate_or_orphaned_prepared_root(tmp_path: Path) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = manifest["schedule"][0]
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    forged = json.loads(receipt.read_text(encoding="utf-8"))
    forged["issuer"] = ""
    receipt.write_bytes(study.canonical(forged))
    with pytest.raises(ValueError, match="zero-charge"):
        executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=tmp_path / "forged", acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    with pytest.raises(ValueError, match="disjoint"):
        executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=tmp_path, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    output = tmp_path / "prepared"
    executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    (output / cell["cell_id"] / "orphan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown or missing"):
        executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)


def test_executor_has_no_confirmation_cell_surface_and_rechecks_reparse_gate(tmp_path: Path, monkeypatch) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = dict(manifest["schedule"][0])
    cell["partition"] = "confirmation"
    with pytest.raises(ValueError, match="confirmation"):
        executor._cell({"schedule": [cell]}, cell["cell_id"])
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, manifest["schedule"][0])
    actual_lstat = study.os.lstat
    target = Path(os.path.abspath(acknowledgement))

    def reparse_lstat(path, *args, **kwargs):
        metadata = actual_lstat(path, *args, **kwargs)
        if Path(os.path.abspath(path)) == target:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(study.os, "lstat", reparse_lstat)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    with pytest.raises(ValueError, match="symlink or reparse"):
        executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=manifest["schedule"][0]["cell_id"], output_root=tmp_path / "never", acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)


def test_executor_revalidates_frozen_effective_request_and_rejects_result_orphans(tmp_path: Path) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = manifest["schedule"][0]
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    output = tmp_path / "prepared"
    executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    with pytest.raises(ValueError, match="request, or route wrapper drifted"):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint="https://substituted.example.invalid/v1/chat/completions")
    persisted_acknowledgement = output / cell["cell_id"] / "acknowledgement.json"
    altered_gate = json.loads(persisted_acknowledgement.read_text(encoding="utf-8"))
    altered_gate["acknowledged"] = False
    persisted_acknowledgement.write_bytes(study.canonical(altered_gate))
    with pytest.raises(ValueError, match="external acknowledgement"):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    (output / cell["cell_id"] / "result").mkdir()
    (output / cell["cell_id"] / "result" / "attempt-result.json").write_bytes(study.canonical({"forged": True}))
    with pytest.raises(ValueError, match="orphan"):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)


def test_executor_preserves_runner_failure_and_never_resends(tmp_path: Path, monkeypatch) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = manifest["schedule"][0]
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    output = tmp_path / "prepared"
    executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)

    class NativeFailure(RuntimeError):
        retryable = True
        content = "exact native failure body"
        provider_record = {"native": "record"}

    monkeypatch.setattr(executor, "_dispatch_via_runner", lambda **_kwargs: (_ for _ in ()).throw(NativeFailure("provider transport failed")))
    with pytest.raises(NativeFailure):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    root = output / cell["cell_id"]
    assert (root / "result" / "provider-failure.json").is_file()
    assert (root / "result" / "provider-failure-content.txt").read_text(encoding="utf-8") == "exact native failure body"
    resumed = executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    assert resumed == {"cell_id": cell["cell_id"], "state": "contact_outcome_unresolved_no_resend", "provider_calls_made": 0, "resumed": True}


def test_executor_hook_rejects_post_snapshot_mutation_before_mocked_contact(tmp_path: Path, monkeypatch) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = manifest["schedule"][0]
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    output = tmp_path / "prepared"
    executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    contacts = 0

    def mutate_then_hook(**kwargs):
        nonlocal contacts
        disclosure = output / cell["cell_id"] / "disclosure.json"
        disclosure.write_bytes(disclosure.read_bytes() + b" ")
        kwargs["before_provider_attempt"]()
        contacts += 1
        raise AssertionError("provider mock must not be reached")

    monkeypatch.setattr(executor, "_dispatch_via_runner", mutate_then_hook)
    with pytest.raises(ValueError, match="changed after final pre-contact snapshot"):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    assert contacts == 0


def test_executor_rejects_result_namespace_insertion_race(tmp_path: Path) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    cell = manifest["schedule"][0]
    acknowledgement, receipt, _ = _external_execution_gates(tmp_path, manifest, cell)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    output = tmp_path / "prepared"
    executor.prepare_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], cell_id=cell["cell_id"], output_root=output, acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
    root = output / cell["cell_id"]
    (root / "result").mkdir()
    (root / "result" / "attempt-result.json").write_bytes(study.canonical({"forged": True}))
    with pytest.raises(ValueError, match="orphan provider evidence"):
        executor.dispatch_prepared_cell(freeze_path=freeze_path, frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"], output_root=output, cell_id=cell["cell_id"], allow_remote=True, trusted_gate_verifier=_trusted_gate_verifier, endpoint=OPENAI_ENDPOINT)
