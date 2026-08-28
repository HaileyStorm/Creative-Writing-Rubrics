from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v1"
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
ENDPOINT = "https://approved.example.invalid/v1/chat/completions"
study = load_module(PACKAGE / "study.py", name="hanna_launcher_study_v1")
harness = load_module(PACKAGE / "offline_harness.py", name="hanna_launcher_harness_v1", aliases={"study": study})
freeze = load_module(PACKAGE / "execution_freeze.py", name="hanna_launcher_freeze_v1", aliases={"study": study, "offline_harness": harness})
executor = load_module(PACKAGE / "executor.py", name="hanna_launcher_executor_v1", aliases={"study": study, "offline_harness": harness, "execution_freeze": freeze})
launch = load_module(PACKAGE / "launch.py", name="hanna_launcher_v1", aliases={"study": study, "execution_freeze": freeze, "executor": executor})


def _simulated_trusted_root_verifier(event: dict) -> dict:
    if event.get("kind") == "trusted_route_availability":
        route = event["route"]
        return {"format_version": 1, "study_id": study.CONTRACT["study_id"], "kind": "trusted_route_availability", "provider": route["provider"], "model": route["model"], "reasoning_effort": route["reasoning_effort"], "paid_api": False, "request_sha256": event["request_sha256"], "endpoint": event["endpoint"], "executable": event["executable"], "authorization_proved": True, "zero_spend_proved": True, "trusted_root_id": "simulated-test-root", "verified": True}
    return {"format_version": 1, "study_id": study.CONTRACT["study_id"], "gate_kind": event["gate_kind"], "gate_sha256": event["gate_sha256"], "gate_bytes": len(event["gate_bytes"]), "trusted_verifier_id": "test-gate-verifier", "trusted_root_id": "test-deployment-root", "verified": True}


def _gates(tmp_path: Path, preview: dict) -> tuple[Path, Path]:
    cell, route = preview["cell"], preview["remote_destination"]
    acknowledgement = tmp_path / "acknowledgement.json"
    acknowledgement.write_bytes(study.canonical({"format_version": 1, "study_id": study.CONTRACT["study_id"], "kind": "local_first_remote_execution", "cell_id": cell["cell_id"], "disclosure_sha256": study.sha256(preview), "acknowledged": True, "attestor": "external-owner"}))
    receipt = tmp_path / "zero-charge.json"
    receipt.write_bytes(study.canonical({"format_version": 1, "study_id": study.CONTRACT["study_id"], "kind": "trusted_zero_charge_route_receipt", "cell_id": cell["cell_id"], "disclosure_sha256": study.sha256(preview), "provider": route["provider"], "model": route["model"], "transport_identity": route["transport_identity"], "reasoning_effort": route["reasoning_effort"], "paid_api": False, "no_financial_liability": True, "issuer": "trusted-route-authority"}))
    return acknowledgement, receipt


def test_four_mapped_engineering_anchor_ids_have_exact_provider_free_previews(tmp_path: Path) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    anchors = ("cell-3e8c1dc67f188f1a", "cell-5a1ce279279efa23", "cell-baeda94393c31c8c", "cell-400612d81c34ae0b")
    by_id = {cell["cell_id"]: cell for cell in manifest["schedule"]}
    assert set(anchors).issubset(by_id)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    previews = [launch.preview_cell_disclosure(freeze_path=freeze_path, cell_id=cell_id, endpoint=ENDPOINT if by_id[cell_id]["provider"] == "openai" else None, grok_bin=None if by_id[cell_id]["provider"] == "openai" else Path(sys.executable), **ROOTS) for cell_id in anchors]
    assert {preview["cell"]["partition"] for preview in previews} == {"train", "development"}
    assert {preview["cell"]["provider"] for preview in previews} == {"openai", "xai"}
    assert all(preview["outbound_wrapper"]["system_instruction"] == executor.SYSTEM_INSTRUCTION for preview in previews)
    assert all(preview["artifacts_leaving_machine"]["provider_ready_task"]["sha256"] == preview["cell"]["task_payload_sha256"] for preview in previews)


def test_preflight_persists_exact_nonpromotable_preview_and_rejects_gate_failures(tmp_path: Path) -> None:
    manifest = freeze.derive_execution_freeze(**ROOTS)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(study.canonical(manifest))
    cell_id = manifest["schedule"][0]["cell_id"]
    preview = launch.preview_cell_disclosure(freeze_path=freeze_path, cell_id=cell_id, endpoint=ENDPOINT, **ROOTS)
    acknowledgement, receipt = _gates(tmp_path, preview)
    result = launch.preview_preflight_cell(freeze_path=freeze_path, cell_id=cell_id, attempt_root=tmp_path / "attempt", acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_root_verifier=_simulated_trusted_root_verifier, endpoint=ENDPOINT, **ROOTS)
    assert result["provider_calls_made"] == 0 and result["promotable"] is False and result["selector_eligible"] is False
    assert result["disclosure"] == preview
    assert result["transport_evidence_class"] == "development_transport_evidence_only"
    with pytest.raises(ValueError, match="execution cell is unknown"):
        launch.preview_cell_disclosure(freeze_path=freeze_path, cell_id="canary-0000000000000000", endpoint=ENDPOINT, **ROOTS)

    def no_zero_spend(event: dict) -> dict:
        value = _simulated_trusted_root_verifier(event)
        if event.get("kind") == "trusted_route_availability":
            value["zero_spend_proved"] = False
        return value

    with pytest.raises(ValueError, match="zero-spend availability is unproved"):
        launch.preview_preflight_cell(freeze_path=freeze_path, cell_id=manifest["schedule"][2]["cell_id"], attempt_root=tmp_path / "failed", acknowledgement_path=acknowledgement, zero_charge_route_receipt_path=receipt, trusted_root_verifier=no_zero_spend, endpoint=ENDPOINT, **ROOTS)
    with pytest.raises(ValueError, match="OpenAI-compatible endpoint is required before preparation"):
        launch.preview_cell_disclosure(freeze_path=freeze_path, cell_id=cell_id, **ROOTS)
