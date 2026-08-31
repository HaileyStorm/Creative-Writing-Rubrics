from __future__ import annotations

import base64
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module():
    spec = importlib.util.spec_from_file_location("_broader_grok_result_test", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def extractor(raw: bytes, *, provider: str, model: str):
    assert provider == "xai" and model == "grok-4.6"
    value = json.loads(raw)
    return value["scores"], {dimension: True for dimension in DIMENSIONS}, {"reported_model": "grok-4.6-build"}


def fixture():
    candidates = ["normalized-nextwave-08-conservative-hybrid", "broader-nextwave-11-scope_materiality", "broader-nextwave-12-construct_framing", "broader-nextwave-13-missing_evidence_not_no", "broader-nextwave-14-human_reference_variant"]
    deltas = {candidates[0]: 1.0, candidates[1]: 0.25, candidates[2]: 0.5, candidates[3]: 0.75, candidates[4]: 0.6}
    cells, collector_cells, targets, groups = [], [], {}, []
    for group_index in range(7):
        item, group = f"item-{group_index}", f"group-{group_index}"
        targets[item] = {dimension: 2.0 for dimension in DIMENSIONS}
        groups.append({"item_id": item, "partition": "development", "prompt_group_id": group})
        for candidate in candidates:
            cell_id = f"cell-{group_index}-{candidates.index(candidate)}"
            payload = f"payload:{cell_id}".encode()
            request = f"request:{cell_id}".encode()
            response = json.dumps({"scores": {dimension: 2.0 + deltas[candidate] for dimension in DIMENSIONS}}).encode()
            row = {"cell_id": cell_id, "candidate_id": candidate, "item_id": item, "prompt_group_id": group, "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": module().sha256(payload)}
            cells.append(row)
            settings = {"route_name": "fixture"}
            collector_cells.append({"cell_id": cell_id, "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode(), "native_request_sha256": module().sha256(request), "native_response_base64": base64.b64encode(response).decode(), "native_response_sha256": module().sha256(response), "identity": {"request_id": f"request-{cell_id}", "session_id": f"session-{cell_id}"}, "effective_settings": settings, "effective_settings_sha256": module().sha256(settings)})
    value = module()
    schedule = {"study_id": value.FREEZE_ID, "schedule_sha256": value.SCHEDULE_SHA256, "cells": cells, "groups": groups}
    collector = {"format_version": 1, "study_id": value.V2_ID, "kind": "complete_35_broader_grok_receipts_cardinality_unproven", "schedule_sha256": value.SCHEDULE_SHA256, "authorization_acknowledgement_sha256": "a" * 64, "route": {"name": "fixture"}, "route_evidence": {"fixture": True}, "cells": collector_cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0}
    return schedule, collector, targets


def test_package_is_path_free_and_provider_free():
    value = module()
    assert value.validate_package()["study_id"] == value.STUDY_ID
    assert value.main([]) == 0
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source


def test_complete_native_fixture_recomputes_equal_group_metrics_and_deterministic_choice():
    value = module(); schedule, collector, targets = fixture()
    result = value._project(schedule, collector, targets, extractor)
    assert [row["candidate_id"] for row in result["metrics"]][0] == "broader-nextwave-11-scope_materiality"
    assert result["selection"]["tie_breakers"] == ["equal_group_mae:ascending", "candidate_id:lexicographic"]
    assert len(result["metrics"]) == 5 and all(row["cells"] == 7 for row in result["metrics"])
    assert len(result["parent_vs_descendant"]) == 4
    assert result["authority"]["selection"] == "grok_development_only"


def test_partial_payload_and_identity_adversaries_are_rejected():
    value = module(); schedule, collector, targets = fixture()
    partial = deepcopy(collector); partial["cells"].pop()
    with pytest.raises(ValueError, match="geometry|partial"):
        value._project(schedule, partial, targets, extractor)
    payload = deepcopy(collector); payload["cells"][0]["payload_base64"] = payload["cells"][1]["payload_base64"]
    with pytest.raises(ValueError, match="binding"):
        value._project(schedule, payload, targets, extractor)
    duplicate = deepcopy(collector); duplicate["cells"][1]["identity"] = deepcopy(duplicate["cells"][0]["identity"])
    with pytest.raises(ValueError, match="binding"):
        value._project(schedule, duplicate, targets, extractor)
    aggregate = deepcopy(collector); aggregate["caller_aggregate"] = {"mae": 0.0}
    with pytest.raises(ValueError, match="aggregate"):
        value._project(schedule, aggregate, targets, extractor)
