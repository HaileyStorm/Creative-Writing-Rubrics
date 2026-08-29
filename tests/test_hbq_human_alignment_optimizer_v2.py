from __future__ import annotations

import copy
import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v2"
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
analysis = load_module(PACKAGE / "analyze.py", name="hanna_optimizer_analyze_v2")


def _response(scores: dict[str, float]) -> dict:
    return {
        "scores": scores,
        "evidence": {dimension: "native evidence" for dimension in analysis.DIMENSIONS},
        "coverage": {dimension: True for dimension in analysis.DIMENSIONS},
    }


def _receipt(cell: dict, route: dict, native_bytes: bytes, response_id: str | None, request_id: str | None, session_id: str | None) -> dict:
    binding = {
        "format_version": 1,
        "study_id": analysis.STUDY_ID,
        "kind": "native_cell_receipt_claim",
        "cell_id": cell["cell_id"],
        "provider": cell["provider"],
        "model": cell["model"],
        "transport_identity": route["transport_identity"],
        "request_sha256": cell["task_payload_sha256"],
        "native_response_sha256": analysis.sha256_bytes(native_bytes),
        "status": "success",
        "physical_provider_contacts": 1,
        "native_response_id_sha256": analysis.sha256_bytes(response_id.encode("utf-8")) if response_id is not None else None,
        "native_request_id_sha256": analysis.sha256_bytes(request_id.encode("utf-8")) if request_id is not None else None,
        "native_session_id_sha256": analysis.sha256_bytes(session_id.encode("utf-8")) if session_id is not None else None,
    }
    return {**binding, "receipt_id": "native-receipt-" + analysis.sha256_bytes(analysis.canonical(binding))[:16]}


def _receipt_binding_verifier(event: dict) -> dict:
    receipt = json.loads(event["receipt_bytes"].decode("utf-8"))
    assert receipt["cell_id"] == event["cell"]["cell_id"]
    assert receipt["native_response_sha256"] == analysis.sha256_bytes(event["native_response_bytes"])
    return {
        "format_version": 1,
        "study_id": analysis.STUDY_ID,
        "gate_kind": "native_cell_receipt",
        "receipt_sha256": analysis.sha256_bytes(event["receipt_bytes"]),
        "native_response_sha256": analysis.sha256_bytes(event["native_response_bytes"]),
        "cell_id": event["cell"]["cell_id"],
        "provider": event["cell"]["provider"],
        "model": event["cell"]["model"],
        "transport_identity": event["route"]["transport_identity"],
        "verified": True,
        "binding_verifier_id": "test-supplied-receipt-binding-verifier",
        "binding_root_id": "test-supplied-receipt-root-label",
    }


def _refresh_cell_receipt(supplied: dict, cell: dict, route: dict) -> None:
    native_bytes = base64.b64decode(supplied["native_response_base64"], validate=True)
    native = json.loads(native_bytes.decode("utf-8"))
    if cell["provider"] == "openai":
        response_id, request_id, session_id = native["id"], None, None
    else:
        response_id, request_id, session_id = None, native["requestId"], native["sessionId"]
    supplied["native_receipt"] = _receipt(cell, route, native_bytes, response_id, request_id, session_id)


@pytest.fixture(scope="module")
def frozen_material() -> dict:
    study, harness, _freeze_module, freeze = analysis._validated_parent(**ROOTS)
    candidates = harness.enumerate_balanced_candidates()
    targets = analysis._human_targets(study=study, **ROOTS)
    candidate_index = {candidate["candidate_id"]: index for index, candidate in enumerate(candidates)}
    cells = []
    for cell in freeze["schedule"]:
        index = candidate_index[cell["candidate_id"]]
        target = targets[cell["item_id"]]
        if cell["model"] == "gpt-5.6-sol":
            scores = {dimension: min(5.0, target[dimension] + index * 0.03) for dimension in analysis.DIMENSIONS}
        else:
            scores = {dimension: max(0.0, 5.5 - target[dimension] - index * 0.01) for dimension in analysis.DIMENSIONS}
        response = _response(scores)
        if cell["provider"] == "openai":
            response_id = "response-" + cell["cell_id"]
            request_id = None
            session_id = None
            native = {
                "id": response_id,
                "model": "gpt-5.6-sol",
                "choices": [{"message": {"content": json.dumps(response, ensure_ascii=False)}}],
            }
        else:
            response_id = None
            request_id = "request-" + cell["cell_id"]
            session_id = "session-" + cell["cell_id"]
            native = {
                "modelUsage": {"grok-4.6-build": {}},
                "sessionId": session_id,
                "requestId": request_id,
                "stopReason": "end_turn",
                "num_turns": 1,
                "structuredOutput": response,
            }
        native_bytes = analysis.canonical(native)
        route = next(route for route in freeze["routes"] if route["model"] == cell["model"])
        cells.append({
            "cell_id": cell["cell_id"],
            "task_payload_sha256": cell["task_payload_sha256"],
            "native_response_base64": base64.b64encode(native_bytes).decode("ascii"),
            "native_receipt": _receipt(cell, route, native_bytes, response_id, request_id, session_id),
        })
    evidence = {
        "format_version": 1,
        "study_id": analysis.STUDY_ID,
        "kind": "exact_native_train_development_cell_evidence",
        "execution_freeze_sha256": analysis.sha256_bytes(analysis.canonical(freeze)),
        "cells": cells,
    }
    return {"study": study, "harness": harness, "freeze": freeze, "targets": targets, "candidates": candidates, "evidence": evidence}


def test_full_732_cell_recomputation_selects_only_sol_and_keeps_confirmation_unopened(tmp_path: Path, frozen_material: dict) -> None:
    evidence_path = tmp_path / "native.json"
    output_path = tmp_path / "analysis.json"
    evidence_path.write_bytes(analysis.canonical(frozen_material["evidence"]))
    result = analysis.analyze(native_evidence_path=evidence_path, output_path=output_path, receipt_binding_verifier=_receipt_binding_verifier, **ROOTS)

    assert result["evidence"]["native_cell_count"] == 732
    assert result["evidence"]["train_cell_count"] == 576
    assert result["evidence"]["development_cell_count"] == 156
    assert result["evidence"]["confirmation_cell_count"] == 0
    assert result["status"] == "supplied_receipt_metrics_nonempirical_confirmation_unopened"
    assert result["selection_preview"]["model"] == "gpt-5.6-sol"
    assert result["selection_preview"]["candidate_id"] == frozen_material["candidates"][0]["candidate_id"]
    assert result["selection_preview"]["empirical_authority"] == "none_unpinned_cryptographic_trust_root"
    assert result["providers"]["grok-4.6"]["role"] == "separate_descriptive_screen_guard_only"
    assert result["confirmation"] == {"status": "unopened", "item_count": 19, "group_count": 8, "accepted_evidence_cells": 0}
    assert len(result["providers"]["gpt-5.6-sol"]["candidate_metrics"]) == 6
    assert all(
        row["development"]["item_count"] == 13
        and row["development"]["prompt_group_count"] == 7
        and row["development"]["unit"] == "prompt_group_equal_weight"
        and "train" not in row
        for row in result["providers"]["gpt-5.6-sol"]["candidate_metrics"]
    )
    assert result["evidence"]["analyze_py_sha256"] == analysis.sha256_bytes((PACKAGE / "analyze.py").read_bytes())
    assert result["evidence"]["runtime_identity"] == analysis._runtime_identity()
    assert result["evidence"]["runtime_identity_sha256"] == analysis.sha256_bytes(analysis.canonical(analysis._runtime_identity()))
    published = output_path.read_text(encoding="utf-8")
    assert "session-cell-" not in published and "request-cell-" not in published and "native evidence" not in published
    with pytest.raises(ValueError, match="new file|overwrite"):
        analysis.analyze(native_evidence_path=evidence_path, output_path=output_path, receipt_binding_verifier=_receipt_binding_verifier, **ROOTS)


@pytest.mark.parametrize("mutation,match", [
    (lambda value: value.update({"macro_spearman": 1.0}), "fields"),
    (lambda value: value["cells"].pop(), "732"),
    (lambda value: value["cells"].__setitem__(0, {**value["cells"][0], "task_payload_sha256": "0" * 64}), "request binding"),
    (lambda value: value["cells"][0].pop("native_receipt"), "fields"),
])
def test_rejects_aggregate_incomplete_tampered_or_wrong_model_native_evidence(frozen_material: dict, mutation, match: str) -> None:
    evidence = copy.deepcopy(frozen_material["evidence"])
    mutation(evidence)
    with pytest.raises(ValueError, match=match):
        analysis._recompute(
            evidence=evidence,
            freeze=frozen_material["freeze"],
            targets=frozen_material["targets"],
            candidates=frozen_material["candidates"],
            receipt_binding_verifier=_receipt_binding_verifier,
        )


@pytest.mark.parametrize("model", ["gpt-5.6-sol", "grok-4.6"])
def test_reported_endpoint_fails_closed_when_any_candidate_dimension_is_constant(frozen_material: dict, model: str) -> None:
    evidence = copy.deepcopy(frozen_material["evidence"])
    first_candidate = frozen_material["candidates"][0]["candidate_id"]
    schedule = frozen_material["freeze"]["schedule"]
    for supplied, cell in zip(evidence["cells"], schedule, strict=True):
        if cell["model"] == model and cell["candidate_id"] == first_candidate and cell["partition"] == "development":
            native = json.loads(base64.b64decode(supplied["native_response_base64"]).decode("utf-8"))
            response = json.loads(native["choices"][0]["message"]["content"]) if model == "gpt-5.6-sol" else native["structuredOutput"]
            response["scores"]["Relevance"] = 1.0
            if model == "gpt-5.6-sol":
                native["choices"][0]["message"]["content"] = json.dumps(response)
            else:
                native["structuredOutput"] = response
            supplied["native_response_base64"] = base64.b64encode(analysis.canonical(native)).decode("ascii")
            route = next(route for route in frozen_material["freeze"]["routes"] if route["model"] == cell["model"])
            _refresh_cell_receipt(supplied, cell, route)
    with pytest.raises(ValueError, match="reported development endpoints require six defined"):
        analysis._recompute(evidence=evidence, freeze=frozen_material["freeze"], targets=frozen_material["targets"], candidates=frozen_material["candidates"], receipt_binding_verifier=_receipt_binding_verifier)


def test_uneven_prompt_groups_reverse_item_weighted_candidate_order() -> None:
    group_values = [1.0, 1.6, 2.2, 2.8, 3.4, 4.0, 4.6]
    group_sizes = [7, 1, 1, 1, 1, 1, 1]
    targets: dict[str, dict[str, float]] = {}
    rows_a, rows_b = [], []
    item_errors_a, item_errors_b = [], []
    for group_index, (human, size) in enumerate(zip(group_values, group_sizes, strict=True)):
        predicted_a = human + (0.5 if group_index == 0 else 0.0)
        predicted_b = human + (0.0 if group_index == 0 else 0.09)
        for item_index in range(size):
            item_id = f"item-{group_index}-{item_index}"
            group_id = f"group-{group_index}"
            targets[item_id] = {dimension: human for dimension in analysis.DIMENSIONS}
            base = {"item_id": item_id, "prompt_group_id": group_id, "coverage": {dimension: True for dimension in analysis.DIMENSIONS}}
            rows_a.append({**base, "scores": {dimension: predicted_a for dimension in analysis.DIMENSIONS}})
            rows_b.append({**base, "scores": {dimension: predicted_b for dimension in analysis.DIMENSIONS}})
            item_errors_a.append(abs(predicted_a - human))
            item_errors_b.append(abs(predicted_b - human))
    endpoint_a = analysis._candidate_endpoint(rows_a, targets, expected_items=13, expected_groups=7)
    endpoint_b = analysis._candidate_endpoint(rows_b, targets, expected_items=13, expected_groups=7)
    assert endpoint_a["macro_spearman"] == pytest.approx(1.0)
    assert endpoint_b["macro_spearman"] == pytest.approx(1.0)
    assert endpoint_a["mean_absolute_error"] < endpoint_b["mean_absolute_error"]
    assert sum(item_errors_a) / 13 > sum(item_errors_b) / 13
    assert analysis._selection_key({"candidate_id": "candidate-a", "development": endpoint_a}) < analysis._selection_key({"candidate_id": "candidate-b", "development": endpoint_b})


def test_receipt_bindings_reject_response_swap_misassociation_and_duplicate_contact(frozen_material: dict) -> None:
    material = frozen_material
    schedule = material["freeze"]["schedule"]

    response_swap = copy.deepcopy(material["evidence"])
    response_swap["cells"][0]["native_response_base64"], response_swap["cells"][2]["native_response_base64"] = response_swap["cells"][2]["native_response_base64"], response_swap["cells"][0]["native_response_base64"]
    with pytest.raises(ValueError, match="receipt binding"):
        analysis._recompute(evidence=response_swap, freeze=material["freeze"], targets=material["targets"], candidates=material["candidates"], receipt_binding_verifier=_receipt_binding_verifier)

    pair_swap = copy.deepcopy(material["evidence"])
    for field in ("native_response_base64", "native_receipt"):
        pair_swap["cells"][0][field], pair_swap["cells"][2][field] = pair_swap["cells"][2][field], pair_swap["cells"][0][field]
    with pytest.raises(ValueError, match="receipt binding"):
        analysis._recompute(evidence=pair_swap, freeze=material["freeze"], targets=material["targets"], candidates=material["candidates"], receipt_binding_verifier=_receipt_binding_verifier)

    duplicate = copy.deepcopy(material["evidence"])
    first_native = json.loads(base64.b64decode(duplicate["cells"][1]["native_response_base64"]).decode("utf-8"))
    second_native = json.loads(base64.b64decode(duplicate["cells"][3]["native_response_base64"]).decode("utf-8"))
    second_native["requestId"], second_native["sessionId"] = first_native["requestId"], first_native["sessionId"]
    duplicate["cells"][3]["native_response_base64"] = base64.b64encode(analysis.canonical(second_native)).decode("ascii")
    route = next(route for route in material["freeze"]["routes"] if route["model"] == schedule[3]["model"])
    _refresh_cell_receipt(duplicate["cells"][3], schedule[3], route)
    with pytest.raises(ValueError, match="contact identity is duplicated"):
        analysis._recompute(evidence=duplicate, freeze=material["freeze"], targets=material["targets"], candidates=material["candidates"], receipt_binding_verifier=_receipt_binding_verifier)


def test_wrong_native_model_and_rejecting_binding_verifier_are_rejected(frozen_material: dict) -> None:
    evidence = copy.deepcopy(frozen_material["evidence"])
    cell = frozen_material["freeze"]["schedule"][0]
    native = json.loads(base64.b64decode(evidence["cells"][0]["native_response_base64"]).decode("utf-8"))
    native["model"] = "gpt-5.6-terra"
    evidence["cells"][0]["native_response_base64"] = base64.b64encode(analysis.canonical(native)).decode("ascii")
    route = next(route for route in frozen_material["freeze"]["routes"] if route["model"] == cell["model"])
    _refresh_cell_receipt(evidence["cells"][0], cell, route)
    with pytest.raises(ValueError, match="model identity"):
        analysis._recompute(evidence=evidence, freeze=frozen_material["freeze"], targets=frozen_material["targets"], candidates=frozen_material["candidates"], receipt_binding_verifier=_receipt_binding_verifier)

    def rejecting_verifier(event: dict) -> dict:
        result = _receipt_binding_verifier(event)
        result["verified"] = False
        return result

    with pytest.raises(ValueError, match="verifier rejected"):
        analysis._recompute(evidence=frozen_material["evidence"], freeze=frozen_material["freeze"], targets=frozen_material["targets"], candidates=frozen_material["candidates"], receipt_binding_verifier=rejecting_verifier)


@pytest.mark.parametrize("mutation", [
    lambda value: value["geometry"]["partitions"]["development"].update({"groups": 8}),
    lambda value: value["endpoint"].update({"selection_preview_provider": "grok-4.6"}),
    lambda value: value["endpoint"].update({"tie_breakers": ["candidate_id:lexicographic"]}),
    lambda value: value["endpoint"].update({"grok_role": "selector"}),
    lambda value: value["confirmation"].update({"status": "opened"}),
    lambda value: value["confirmation"].update({"accepted_evidence_cells": 1}),
    lambda value: value["optimizer_interfaces"]["dspy"].update({"runtime_dependency": True}),
    lambda value: value["outputs"].update({"aggregate_only": False}),
    lambda value: value["outputs"]["provenance"].remove("analyze_py_sha256"),
    lambda value: value.update({"interpretation_limits": ["Metrics are empirical."]}),
])
def test_critical_contract_semantics_are_executable(mutation) -> None:
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    mutation(contract)
    with pytest.raises(ValueError, match="critical study contract semantics drifted"):
        analysis._validate_contract_semantics(contract)


def test_canonical_input_and_reparse_paths_are_required(tmp_path: Path, frozen_material: dict) -> None:
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(frozen_material["evidence"], indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        analysis.read_canonical_object(noncanonical)

    canonical = tmp_path / "canonical.json"
    canonical.write_bytes(analysis.canonical(frozen_material["evidence"]))
    linked = tmp_path / "linked.json"
    try:
        os.symlink(canonical, linked)
    except OSError:
        pytest.skip("file symlinks are unavailable on this host")
    with pytest.raises(ValueError, match="links or reparses"):
        analysis.read_canonical_object(linked)


def test_reparse_ancestor_and_output_parent_replacement_are_rejected(tmp_path: Path, monkeypatch) -> None:
    ancestor = tmp_path / "ancestor"
    ancestor.mkdir()
    source = ancestor / "source.json"
    source.write_bytes(analysis.canonical({"ok": True}))
    real_lstat = analysis.os.lstat

    def marked_lstat(path):
        value = real_lstat(path)
        if Path(path) == ancestor:
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            fields["st_file_attributes"] = fields.get("st_file_attributes", 0) | 0x400
            return SimpleNamespace(**fields)
        return value

    monkeypatch.setattr(analysis.os, "lstat", marked_lstat)
    with pytest.raises(ValueError, match="links or reparses"):
        analysis.read_canonical_object(source)
    monkeypatch.setattr(analysis.os, "lstat", real_lstat)

    output = tmp_path / "never.json"
    real_snapshot = analysis._ancestry_snapshot
    parent_calls = 0

    def drifting_snapshot(path):
        nonlocal parent_calls
        value = real_snapshot(path)
        if Path(path) == tmp_path:
            parent_calls += 1
            if parent_calls >= 2:
                return value + ((0, 0, 0, 0),)
        return value

    monkeypatch.setattr(analysis, "_ancestry_snapshot", drifting_snapshot)
    with pytest.raises(ValueError, match="output parent changed"):
        analysis._publish_no_overwrite(output, b"{}\n")
    assert not output.exists()
    assert not list(tmp_path.glob(".never.json.*.tmp"))

    post_link_output = tmp_path / "post-link-never.json"
    parent_calls = 0

    def post_link_drift(path):
        nonlocal parent_calls
        value = real_snapshot(path)
        if Path(path) == tmp_path:
            parent_calls += 1
            if parent_calls >= 3:
                return value + ((0, 0, 0, 0),)
        return value

    monkeypatch.setattr(analysis, "_ancestry_snapshot", post_link_drift)
    with pytest.raises(ValueError, match="changed during publication"):
        analysis._publish_no_overwrite(post_link_output, b"{\"post\":true}\n")
    assert not post_link_output.exists()
    assert not list(tmp_path.glob(".post-link-never.json.*.tmp"))


def test_runtime_has_no_dspy_or_optuna_dependency_and_tie_aware_spearman() -> None:
    source = (PACKAGE / "analyze.py").read_text(encoding="utf-8")
    assert "import dspy" not in source and "import optuna" not in source
    assert analysis.spearman([1, 1, 2, 3], [4, 4, 1, 0]) == pytest.approx(-1.0)
    assert analysis.spearman([1, 1, 1], [1, 2, 3]) is None
