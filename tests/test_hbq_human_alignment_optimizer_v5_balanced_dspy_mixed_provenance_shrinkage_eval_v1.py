from __future__ import annotations

import base64
import builtins
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from _scoped_module_loader import load_module

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-shrinkage-eval-v1"
MATERIAL = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
analyze = load_module(PACKAGE / "analyze.py", name="mixed_receipt_analyze")
study = analyze._study()


@pytest.fixture(scope="module")
def schedule():
    return study.prepare_grok_schedule(materialization_root=MATERIAL, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def _evidence(token, cells, route: str, *, winner: str | None = None):
    targets = analyze._targets(token); baseline = token.value["candidates"][0]["candidate_id"]; rows = []
    for ordinal, cell in enumerate(cells):
        delta = .6 if cell["candidate_id"] == baseline else .2 if cell["candidate_id"] == winner else .9
        answer = {"scores": {dimension: max(0., min(5., targets[cell["item_id"]][dimension] + delta)) for dimension in analyze._v2().DIMENSIONS}, "evidence": {dimension: "fixture" for dimension in analyze._v2().DIMENSIONS}, "coverage": {dimension: True for dimension in analyze._v2().DIMENSIONS}}
        if route == "grok_primary":
            request, session = f"request-{ordinal}", f"session-{ordinal}"
            native = {"modelUsage": {"grok-4.6-build": {}}, "requestId": request, "sessionId": session, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": answer}
            identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": request, "session_id": session, "physical_provider_contacts": 1, "tools_enabled": False}
        else:
            response = f"response-{ordinal}"
            native = {"id": response, "model": "gpt-5.6-sol", "choices": [{"message": {"content": __import__("json").dumps(answer)}}]}
            identity = {"provider": "openai_codex_local_lifecycle", "requested_model": "gpt-5.6-sol", "reported_model": "gpt-5.6-sol", "response_id": response, "native_endpoint_contact_cardinality": "unproven", "process_launches": 1, "tools_enabled": False}
        raw = study.canonical(native); rows.append({"cell_id": cell["cell_id"], "payload_base64": cell["payload_base64"], "payload_sha256": cell["payload_sha256"], "native_response_base64": base64.b64encode(raw).decode(), "native_response_sha256": hashlib.sha256(raw).hexdigest(), "identity": identity})
    return {"format_version": 1, "study_id": study.STUDY_ID, "kind": "complete_hanna_native_cell_receipts", "route_name": route, "cells": rows}


def _write(tmp_path: Path, name: str, value: dict) -> Path:
    path = tmp_path / name; path.write_bytes(study.canonical(value)); return path


def test_materialized_source_replays_and_sol_carries_full_candidate_identity(schedule, tmp_path):
    value = schedule.value
    assert value["materialization"]["materialization_file_sha256"] == study.MATERIALIZATION_FILE_SHA256
    assert value["materialization"]["mixed_composition_file_sha256"] == study.MIXED_COMPOSITION_FILE_SHA256
    assert value["geometry"] == {"candidates": 11, "groups": 3, "grok_cells": 33, "sol_cells": 0}
    assert [row["provenance_kind"] for row in value["candidates"][1:]].count("reconciled_v3_terminal_descendant_under_unknown_native_contact") == 9
    evidence = _write(tmp_path, "grok.json", _evidence(schedule, value["cells"], "grok_primary", winner=value["candidates"][1]["candidate_id"]))
    frozen = analyze.select_grok(validated_schedule=schedule, native_evidence_path=evidence); sol = analyze.build_sol_schedule(frozen=frozen)
    assert sol.value["geometry"] == {"candidates": 2, "groups": 2, "sol_cells": 4}
    required = {"source_candidate_id", "provenance_kind", "candidate_sha256", "candidate_instruction_sha256", "candidate_profile_sha256", "payload_base64", "payload_sha256"}
    assert all(required <= set(row) for row in sol.value["cells"])
    grok = {(row["item_id"], row["candidate_id"]): row for row in value["cells"]}
    assert all(study.payload_bytes(row) == study.payload_bytes(grok[(row["item_id"], row["candidate_id"])]) for row in sol.value["cells"])


def test_replay_self_hash_provenance_and_materialization_tamper_reject(schedule, tmp_path):
    forged = json.loads(study.canonical(schedule.value)); forged["candidates"][-1]["provenance_kind"] = "recovered_native_descendant"; body = {key: value for key, value in forged.items() if key != "schedule_sha256"}; forged["schedule_sha256"] = study.sha256(body)
    bad = study.ValidatedSchedule(forged, study.canonical(forged), schedule._candidate_bytes, schedule._inputs, study._TOKEN)
    with pytest.raises(ValueError, match="replay drifted"):
        study._validated_schedule(bad)
    copied = tmp_path / "material"; shutil.copytree(MATERIAL, copied); raw = bytearray((copied / "mixed-composition.json").read_bytes()); raw[-2] ^= 1; (copied / "mixed-composition.json").write_bytes(raw)
    with pytest.raises(ValueError, match="composition hash drifted"):
        study.prepare_grok_schedule(materialization_root=copied, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def test_receipt_backed_grok_and_sol_projection(schedule, tmp_path):
    winner = schedule.value["candidates"][1]["candidate_id"]
    grok = _write(tmp_path, "grok.json", _evidence(schedule, schedule.value["cells"], "grok_primary", winner=winner))
    frozen = analyze.select_grok(validated_schedule=schedule, native_evidence_path=grok)
    assert frozen.decision["selected_candidate_id"] == winner and frozen.decision["gate"]["passed"] is True
    sol = analyze.build_sol_schedule(frozen=frozen); sol_receipts = _write(tmp_path, "sol.json", _evidence(schedule, sol.value["cells"], "sol_validation", winner=winner))
    result = analyze.validate_sol(frozen=frozen, sol_schedule=sol, native_evidence_path=sol_receipts)
    assert result["passed"] is True and result["native_endpoint_contact_cardinality"] == "unproven"
    assert result["native_evidence_sha256"] == study.sha256(sol_receipts.read_bytes())
    assert result["decision_sha256"] == study.sha256({key: value for key, value in result.items() if key != "decision_sha256"})
    altered = _evidence(schedule, sol.value["cells"], "sol_validation", winner=winner); native = json.loads(base64.b64decode(altered["cells"][0]["native_response_base64"])); response = json.loads(native["choices"][0]["message"]["content"]); response["scores"]["Relevance"] = min(5., response["scores"]["Relevance"] + .01); native["choices"][0]["message"]["content"] = json.dumps(response); altered["cells"][0]["native_response_base64"] = base64.b64encode(study.canonical(native)).decode()
    altered["cells"][0]["native_response_sha256"] = hashlib.sha256(base64.b64decode(altered["cells"][0]["native_response_base64"])).hexdigest()
    changed = analyze.validate_sol(frozen=frozen, sol_schedule=sol, native_evidence_path=_write(tmp_path, "sol-changed.json", altered))
    assert changed["native_evidence_sha256"] != result["native_evidence_sha256"] and changed["decision_sha256"] != result["decision_sha256"]
    tampered = _evidence(schedule, sol.value["cells"], "sol_validation", winner=winner); tampered["cells"][1] = copy.deepcopy(tampered["cells"][0])
    with pytest.raises(ValueError, match="identity is duplicated"):
        analyze.validate_sol(frozen=frozen, sol_schedule=sol, native_evidence_path=_write(tmp_path, "sol-tampered.json", tampered))


@pytest.mark.parametrize("mutation,match", [
    (lambda value: value["cells"].pop(), "geometry"),
    (lambda value: value["cells"].__setitem__(1, copy.deepcopy(value["cells"][0])), "identity is duplicated"),
    (lambda value: value["cells"][0]["identity"].update({"requested_model": "wrong"}), "identity"),
    (lambda value: value["cells"][0].update({"payload_sha256": "0" * 64}), "payload binding"),
])
def test_fabricated_aggregate_and_native_tampering_are_rejected(schedule, tmp_path, mutation, match):
    with pytest.raises(TypeError): analyze.select_grok(validated_schedule=schedule, projected_group_metrics=[])
    evidence = _evidence(schedule, schedule.value["cells"], "grok_primary", winner=schedule.value["candidates"][1]["candidate_id"]); mutation(evidence)
    with pytest.raises(ValueError, match=match): analyze.select_grok(validated_schedule=schedule, native_evidence_path=_write(tmp_path, "bad.json", evidence))


def test_runtime_never_imports_dspy_or_optuna_and_confirmation_stays_unopened(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}: raise AssertionError("optimizer imported at runtime")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    load_module(PACKAGE / "study.py", name="mixed_runtime_study")
    load_module(PACKAGE / "analyze.py", name="mixed_runtime_analyze")
