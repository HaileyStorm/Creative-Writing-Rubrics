from __future__ import annotations

import base64
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PARENT = "broader-nextwave-13-missing_evidence_not_no"
CANDIDATES = (PARENT, "broader-nextwave-15-construct_framing-speaker-attribution", "broader-nextwave-16-scope_materiality-temporal-causality", "broader-nextwave-17-scope_materiality-sustained-stakes", "broader-nextwave-18-construct_framing-referent-resolution")


def module():
    spec = importlib.util.spec_from_file_location("_desc13_lower_step_result_test", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def extractor(raw: bytes, *, provider: str, model: str):
    assert provider == "xai" and model == "grok-4.6"
    value = json.loads(raw)
    return value["scores"], {dimension: True for dimension in DIMENSIONS}, {"reported_model": "grok-4.6-build"}


def fixture():
    value = module(); deltas = {PARENT: 1.0, CANDIDATES[1]: 0.25, CANDIDATES[2]: 0.5, CANDIDATES[3]: 0.75, CANDIDATES[4]: 0.6}
    cells, receipt_cells, targets, groups = [], [], {}, []
    for group_index in range(7):
        item_id, group_id = f"item-{group_index}", f"group-{group_index}"
        targets[item_id] = {dimension: 2.0 for dimension in DIMENSIONS}
        groups.append({"item_id": item_id, "prompt_group_id": group_id})
        for candidate_index, candidate_id in enumerate(CANDIDATES):
            cell_id = f"cell-{group_index}-{candidate_index}"; payload = f"payload:{cell_id}".encode(); request = f"request:{cell_id}".encode()
            response = value.canonical({"scores": {dimension: 2.0 + deltas[candidate_id] for dimension in DIMENSIONS}})
            cell = {"cell_id": cell_id, "candidate_id": candidate_id, "item_id": item_id, "prompt_group_id": group_id, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": value.sha256(payload)}
            cells.append(cell)
            settings = {"requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False}
            receipt_cells.append({"cell_id": cell_id, "payload_base64": cell["payload_base64"], "payload_sha256": cell["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": value.sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": value.sha256(response), "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": f"request-{cell_id}", "session_id": f"session-{cell_id}", "tools_enabled": False}, "effective_settings": settings, "effective_settings_sha256": value.sha256(settings)})
    schedule = {"study_id": value.EXECUTOR_ID, "kind": value.SCHEDULE_KIND, "schedule_sha256": "s" * 64, "geometry": {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}, "cells": cells, "groups": groups}
    collector = {"format_version": 1, "study_id": value.EXECUTOR_ID, "kind": value.COLLECTOR_KIND, "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": "a" * 64, "route": {"name": "fixture"}, "route_evidence": {"fixture": True}, "cells": receipt_cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0}
    return schedule, collector, targets


def test_package_is_provider_free_and_has_no_runtime_optimizer_dependency():
    value = module()
    assert value.validate_package()["study_id"] == value.STUDY_ID
    assert value.main([]) == 0
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source


def test_contract_pins_every_executor_commitment_and_authority_field():
    value = module(); contract = value._contract()
    value._validate_contract(contract)
    changed_authority = deepcopy(contract); changed_authority["authority"]["promotion"] = "allowed"
    with pytest.raises(ValueError, match="contract"):
        value._validate_contract(changed_authority)
    changed_executor = deepcopy(contract); changed_executor["pinned_executor"]["executor_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contract"):
        value._validate_contract(changed_executor)


def test_complete_native_fixture_recomputes_equal_group_metrics_and_choice():
    value = module(); schedule, collector, targets = fixture()
    result = value._project(schedule, collector, targets, extractor)
    assert result["selection"]["candidate_id"] == CANDIDATES[1]
    assert result["selection"]["tie_breakers"] == ["equal_group_mae:ascending", "candidate_id:lexicographic"]
    assert len(result["metrics"]) == 5 and all(row["cells"] == 7 for row in result["metrics"])
    assert all(row["equal_group_mae"] == sum(row["group_mae"].values()) / row["cells"] for row in result["metrics"])
    assert len(result["parent_vs_descendant"]) == 4
    assert result["authority"]["selection"] == "grok_development_only"


def test_partial_aggregate_identity_and_native_binding_adversaries_are_rejected():
    value = module(); schedule, collector, targets = fixture()
    partial = deepcopy(collector); partial["cells"].pop()
    with pytest.raises(ValueError, match="geometry|partial"):
        value._project(schedule, partial, targets, extractor)
    aggregate = deepcopy(collector); aggregate["caller_aggregate"] = {"mae": 0.0}
    with pytest.raises(ValueError, match="aggregate"):
        value._project(schedule, aggregate, targets, extractor)
    duplicate = deepcopy(collector); duplicate["cells"][1]["identity"] = deepcopy(duplicate["cells"][0]["identity"])
    with pytest.raises(ValueError, match="binding"):
        value._project(schedule, duplicate, targets, extractor)
    settings = deepcopy(collector); settings["cells"][0]["effective_settings"]["tools_enabled"] = True
    with pytest.raises(ValueError, match="binding"):
        value._project(schedule, settings, targets, extractor)
    response = deepcopy(collector); response["cells"][0]["native_response_base64"] = base64.b64encode(b"{}").decode("ascii")
    response["cells"][0]["native_response_sha256"] = value.sha256(b"{}")
    with pytest.raises(ValueError, match="extraction"):
        value._project(schedule, response, targets, extractor)


def test_replay_rejects_collector_swap_after_executor_replay(tmp_path: Path, monkeypatch):
    value = module(); schedule, collector, targets = fixture(); collector_path = tmp_path / "collector.json"
    collector_path.write_bytes(value.canonical(collector))
    original = collector_path.read_bytes()

    class Executor:
        def replay_collector(self, **_kwargs):
            collector_path.write_bytes(value.canonical({**collector, "route_evidence": {"swapped": True}}))
            return {"cells": 35, "equal_group_projection_ready": True, "collector_sha256": value.sha256(original)}

    class V2:
        _extract_native = staticmethod(extractor)

    class V3:
        @staticmethod
        def v2_module():
            return V2()

    class Freeze:
        @staticmethod
        def _v3():
            return V3()

    monkeypatch.setattr(value, "_verify_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(value, "_load_executor", lambda _repo: Executor())
    monkeypatch.setattr(value, "_output_schedule", lambda *_args, **_kwargs: schedule)
    monkeypatch.setattr(value, "_load_freeze", lambda _repo: Freeze())
    monkeypatch.setattr(value, "_targets", lambda *_args, **_kwargs: targets)
    with pytest.raises(ValueError, match="collector changed"):
        value.replay(candidate_freeze_root=tmp_path, development_freeze_root=tmp_path, normalized_root=tmp_path, materialization_root=tmp_path, frozen_successor_path=collector_path, hanna_csv_path=collector_path, output_root=tmp_path, collector_path=collector_path)


def test_target_reconstruction_rejects_external_input_swap(tmp_path: Path):
    value = module(); frozen = tmp_path / "frozen"; normalized = tmp_path / "normalized"; materialization = tmp_path / "materialization"
    frozen.mkdir(); normalized.mkdir(); materialization.mkdir()
    successor = tmp_path / "successor.json"; successor.write_bytes(b"{}")
    csv = tmp_path / "hanna.csv"; csv.write_bytes(b"item")

    groups = [{"item_id": f"item-{index}", "prompt_group_id": f"group-{index}"} for index in range(7)]

    class V2:
        @staticmethod
        def _human_targets(**_kwargs):
            return {f"item-{index}": {dimension: 2.0 for dimension in DIMENSIONS} for index in range(7)}

    class V3:
        @staticmethod
        def _material(**_kwargs):
            return object(), object(), object(), object(), object()

        @staticmethod
        def v2_module():
            return V2()

    class Freeze:
        @staticmethod
        def validate_frozen_root(_path):
            return {"groups": groups, "schedule": "stable"}

        @staticmethod
        def build(**kwargs):
            kwargs["hanna_csv_path"].write_bytes(b"swapped")
            return {"groups": groups, "schedule": "stable"}

        @staticmethod
        def _v3():
            return V3()

    with pytest.raises(ValueError, match="external HANNA input changed"):
        value._targets(Freeze(), frozen_root=frozen, normalized_root=normalized, materialization_root=materialization, frozen_successor_path=successor, hanna_csv_path=csv)
