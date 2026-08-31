"""Receipt-backed exploratory mixed-provenance shrinkage decisions."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

HERE = Path(__file__).resolve().parent
V2_PATH = HERE.parent / "hbq-human-alignment-optimizer-v2" / "analyze.py"
V2_SHA256 = "dc8479a962e4a0e2d0082a4619e0e52922d9d82663bd97bc6e17694781aef822"
_STUDY = _V2 = None
_FROZEN, _SOL = object(), object()


def _study():
    global _STUDY
    if _STUDY is None:
        spec = importlib.util.spec_from_file_location("_mixed_study", HERE / "study.py")
        if spec is None or spec.loader is None: raise ValueError("mixed evaluator cannot load study")
        _STUDY = importlib.util.module_from_spec(spec); sys.modules[spec.name] = _STUDY; spec.loader.exec_module(_STUDY)
    return _STUDY


def _v2():
    global _V2
    if _V2 is None:
        if hashlib.sha256(V2_PATH.read_bytes()).hexdigest() != V2_SHA256: raise ValueError("mixed evaluator pinned v2 analyzer drifted")
        spec = importlib.util.spec_from_file_location("_mixed_v2", V2_PATH)
        if spec is None or spec.loader is None: raise ValueError("mixed evaluator cannot load v2 analyzer")
        _V2 = importlib.util.module_from_spec(spec); sys.modules[spec.name] = _V2; spec.loader.exec_module(_V2)
    return _V2


def objective(deltas: Sequence[float], edit_mass: float) -> float:
    values = [float(value) for value in deltas]
    if not values or any(not math.isfinite(value) for value in values) or not math.isfinite(float(edit_mass)) or not 0 <= float(edit_mass) <= 1: raise ValueError("mixed evaluator objective inputs invalid")
    return .5 * fmean(values) + .25 * pstdev(values) + .02 * float(edit_mass)


def _decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str): raise ValueError(f"mixed evaluator {label} missing base64")
    try: raw = base64.b64decode(value, validate=True)
    except ValueError as error: raise ValueError(f"mixed evaluator {label} invalid base64") from error
    if base64.b64encode(raw).decode() != value: raise ValueError(f"mixed evaluator {label} noncanonical base64")
    return raw


def _targets(token: Any):
    _root, frozen, csv = token._inputs; v2 = _v2(); parent, _harness, _freeze, _execution = v2._validated_parent(frozen_successor_path=frozen, hanna_csv_path=csv)
    return v2._human_targets(study=parent, frozen_successor_path=frozen, hanna_csv_path=csv)


def _evidence(path: Path, study: Any, route: str, expected: int) -> list[Mapping[str, Any]]:
    raw = Path(path).read_bytes()
    try: value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("mixed evaluator native receipt set invalid JSON") from error
    if not isinstance(value, dict) or study.canonical(value) != raw or set(value) != {"format_version", "study_id", "kind", "route_name", "cells"} or value["format_version"] != 1 or value["study_id"] != study.STUDY_ID or value["kind"] != "complete_hanna_native_cell_receipts" or value["route_name"] != route or not isinstance(value["cells"], list) or len(value["cells"]) != expected: raise ValueError("mixed evaluator native receipt geometry drifted")
    return value["cells"]


def project_native(*, validated_schedule: Any, route_name: str, native_evidence_path: Path, schedule_value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    study = _study(); schedule, _candidates = study._validated_schedule(validated_schedule); source = schedule if schedule_value is None else schedule_value; expected = [row for row in source["cells"] if row["route_name"] == route_name]; count = 33 if route_name == "grok_primary" else 4
    if len(expected) != count: raise ValueError("mixed evaluator schedule route geometry drifted")
    index = {row["cell_id"]: row for row in expected}; targets = _targets(validated_schedule); contacts = set(); observed = []
    for supplied in _evidence(native_evidence_path, study, route_name, count):
        if not isinstance(supplied, Mapping) or set(supplied) != {"cell_id", "payload_base64", "payload_sha256", "native_response_base64", "native_response_sha256", "identity"}: raise ValueError("mixed evaluator native receipt fields drifted")
        cell = index.get(supplied["cell_id"]); payload = _decode(supplied["payload_base64"], "payload")
        if cell is None or payload != study.payload_bytes(cell) or supplied["payload_sha256"] != cell["payload_sha256"]: raise ValueError("mixed evaluator native payload binding drifted")
        native_bytes = _decode(supplied["native_response_base64"], "native response")
        if supplied["native_response_sha256"] != hashlib.sha256(native_bytes).hexdigest(): raise ValueError("mixed evaluator native response binding drifted")
        try: native = json.loads(native_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("mixed evaluator native response invalid JSON") from error
        identity = supplied["identity"]
        if not isinstance(native, Mapping) or not isinstance(identity, Mapping) or identity.get("tools_enabled") is not False: raise ValueError("mixed evaluator native identity/tools drifted")
        if route_name == "grok_primary":
            required = {"provider", "requested_model", "reported_model", "request_id", "session_id", "physical_provider_contacts", "tools_enabled"}
            if set(identity) != required or identity.get("provider") != "xai" or identity.get("requested_model") != "grok-4.6" or identity.get("reported_model") != "grok-4.6-build" or identity.get("physical_provider_contacts") != 1 or native.get("requestId") != identity.get("request_id") or native.get("sessionId") != identity.get("session_id"): raise ValueError("mixed evaluator Grok native identity drifted")
            contact = (identity["request_id"], identity["session_id"]); provider, model = "xai", "grok-4.6"
        else:
            required = {"provider", "requested_model", "reported_model", "response_id", "native_endpoint_contact_cardinality", "process_launches", "tools_enabled"}
            if set(identity) != required or identity.get("provider") != "openai_codex_local_lifecycle" or identity.get("requested_model") != "gpt-5.6-sol" or identity.get("reported_model") != "gpt-5.6-sol" or identity.get("native_endpoint_contact_cardinality") != "unproven" or identity.get("process_launches") != 1 or native.get("id") != identity.get("response_id") or native.get("model") != "gpt-5.6-sol": raise ValueError("mixed evaluator Sol lifecycle identity drifted")
            contact = (identity["response_id"], ""); provider, model = "openai", "gpt-5.6-sol"
        if not isinstance(contact[0], str) or not contact[0] or contact in contacts: raise ValueError("mixed evaluator native contact identity is duplicated")
        contacts.add(contact); scores, coverage, _receipt = _v2()._extract_native(native_bytes, provider=provider, model=model)
        target = targets.get(cell["item_id"])
        if target is None: raise ValueError("mixed evaluator target binding drifted")
        observed.append({"cell_id": cell["cell_id"], "candidate_id": cell["candidate_id"], "prompt_group_id": cell["prompt_group_id"], "mean_absolute_error": fmean(abs(scores[dimension] - target[dimension]) for dimension in _v2().DIMENSIONS), "coverage": coverage})
    if set(index) != {row["cell_id"] for row in observed}: raise ValueError("mixed evaluator native receipts partial or duplicate")
    return observed


def _matrix(schedule: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], route: str) -> dict[str, dict[str, float]]:
    cells = [row for row in schedule["cells"] if row["route_name"] == route]; expected, groups = (33, 3) if route == "grok_primary" else (4, 2)
    if len(cells) != expected or len(rows) != expected: raise ValueError("mixed evaluator metric geometry drifted")
    index = {row["cell_id"]: row for row in cells}; result = {}
    for row in rows:
        cell = index.get(row["cell_id"])
        if cell is None or row["candidate_id"] != cell["candidate_id"] or row["prompt_group_id"] != cell["prompt_group_id"]: raise ValueError("mixed evaluator projected metric binding drifted")
        if row["prompt_group_id"] in result.setdefault(row["candidate_id"], {}): raise ValueError("mixed evaluator projected metric duplicate")
        result[row["candidate_id"]][row["prompt_group_id"]] = float(row["mean_absolute_error"])
    if set(index) != {row["cell_id"] for row in rows} or any(len(value) != groups for value in result.values()): raise ValueError("mixed evaluator projected metrics incomplete")
    return result


def _decision(token: Any, evidence: Path) -> dict[str, Any]:
    study = _study(); schedule, candidates = study._validated_schedule(token); matrix = _matrix(schedule, project_native(validated_schedule=token, route_name="grok_primary", native_evidence_path=evidence), "grok_primary"); baseline = candidates[0]["candidate_id"]; groups = [row["prompt_group_id"] for row in schedule["groups"]]; masses = {row["candidate_id"]: 0. if row["candidate_id"] == baseline else study._edit_mass(candidates[0], row) for row in candidates}; scores = {baseline: {"deltas": [0.] * 3, "j": 0., "edit_mass": 0.}}
    for candidate in sorted(set(matrix) - {baseline}):
        values = [matrix[candidate][group] - matrix[baseline][group] for group in groups]; scores[candidate] = {"deltas": values, "j": objective(values, masses[candidate]), "edit_mass": masses[candidate]}
    overall = min(scores, key=lambda candidate: (scores[candidate]["j"], candidate)); folds = []
    for held in range(3):
        winner = min(scores, key=lambda candidate: (0. if candidate == baseline else objective([value for index, value in enumerate(scores[candidate]["deltas"]) if index != held], scores[candidate]["edit_mass"]), candidate)); folds.append({"held_out_prompt_group_id": groups[held], "winner_candidate_id": winner})
    selected = scores[overall]; wins = sum(row["winner_candidate_id"] == overall for row in folds); improved = sum(value < 0 for value in selected["deltas"]); worst = max(selected["deltas"]); passed = overall != baseline and selected["j"] < 0 and wins >= 2 and improved >= 2 and worst <= .1 + 1e-12
    result = {"format_version": 2, "study_id": study.STUDY_ID, "kind": "receipt_backed_exploratory_post_hoc_grok_decision", "grok_schedule_sha256": schedule["schedule_sha256"], "native_evidence_sha256": study.sha256(Path(evidence).read_bytes()), "selected_candidate_id": overall if passed else baseline, "provisional_candidate_id": overall, "action": "advance_to_sol" if passed else "baseline_stop", "scores": [{"candidate_id": key, **scores[key]} for key in sorted(scores)], "leave_one_group_out": folds, "gate": {"j_strictly_negative": selected["j"] < 0, "same_candidate_fold_wins": wins, "raw_groups_improved": improved, "maximum_group_worsening": worst, "maximum_allowed_group_worsening": .1, "passed": passed}, "optuna_role": "development_only_grid_reproduction_no_selection_authority", "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "claim": "EXPLORATORY_POST_HOC_DEVELOPMENT_ONLY; no general HANNA claim; NO-GO until independently replayed native evidence"}; result["decision_sha256"] = study.sha256(result); return result


@dataclass(frozen=True)
class FrozenGrokDecision:
    decision: Mapping[str, Any]; _bytes: bytes; _evidence: bytes; _schedule: Any; _token: object


def select_grok(*, validated_schedule: Any, native_evidence_path: Path) -> FrozenGrokDecision:
    study = _study(); value = _decision(validated_schedule, native_evidence_path); raw = study.canonical(value)
    return FrozenGrokDecision(json.loads(raw), raw, Path(native_evidence_path).read_bytes(), validated_schedule, _FROZEN)


def _validated_frozen(value: Any):
    study = _study()
    if not isinstance(value, FrozenGrokDecision) or value._token is not _FROZEN or study.canonical(dict(value.decision)) != value._bytes: raise ValueError("mixed evaluator requires analyzer-minted frozen Grok decision")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "evidence.json"
        path.write_bytes(value._evidence)
        result = _decision(value._schedule, path)
    if study.canonical(result) != value._bytes: raise ValueError("mixed evaluator frozen decision/evidence drifted")
    return value._schedule, result


@dataclass(frozen=True)
class ValidatedSolSchedule:
    value: Mapping[str, Any]; _bytes: bytes; _frozen: FrozenGrokDecision; _token: object


def _sol_value(frozen: FrozenGrokDecision) -> dict[str, Any]:
    study = _study(); token, decision = _validated_frozen(frozen); schedule, _candidates = study._validated_schedule(token); baseline = schedule["candidates"][0]["candidate_id"]
    if decision["action"] != "advance_to_sol": return {"format_version": 2, "study_id": study.STUDY_ID, "kind": "baseline_stop_no_sol_schedule", "grok_decision_sha256": study.sha256(frozen._bytes), "cells": [], "geometry": {"candidates": 0, "groups": 0, "sol_cells": 0}, "confirmation": {"status": "unopened", "cells": 0}}
    winner = decision["selected_candidate_id"]; source = {(row["item_id"], row["candidate_id"]): row for row in schedule["cells"]}; candidates = {row["candidate_id"]: row for row in schedule["candidates"]}; cells = []
    for group in schedule["groups"][:2]:
        for candidate_id in (baseline, winner):
            grok = source[(group["item_id"], candidate_id)]; candidate = candidates[candidate_id]; key = {"study_id": study.STUDY_ID, "route_name": "sol_validation", "item_id": group["item_id"], "candidate_id": candidate_id}
            cells.append({"ordinal": len(cells)+1, "cell_id": "mixed-shrinkage-cell-"+study.sha256(key)[:16], "route_name": "sol_validation", **group, "sample_id": candidate["sample_id"], "source_candidate_id": candidate["source_candidate_id"], "provenance_kind": candidate["provenance_kind"], "candidate_id": candidate_id, "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "payload_base64": grok["payload_base64"], "payload_sha256": grok["payload_sha256"]})
    value = {"format_version": 2, "study_id": study.STUDY_ID, "kind": "exploratory_frozen_winner_two_group_sol_schedule", "grok_decision_sha256": study.sha256(frozen._bytes), "selected_candidate_id": winner, "candidate_order": [baseline, winner], "groups": schedule["groups"][:2], "cells": cells, "geometry": {"candidates": 2, "groups": 2, "sol_cells": 4}, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}; value["schedule_sha256"] = study.sha256(value); return value


def build_sol_schedule(*, frozen: FrozenGrokDecision) -> ValidatedSolSchedule:
    study = _study(); value = _sol_value(frozen); raw = study.canonical(value); return ValidatedSolSchedule(json.loads(raw), raw, frozen, _SOL)


def validate_sol(*, frozen: FrozenGrokDecision, sol_schedule: ValidatedSolSchedule, native_evidence_path: Path) -> dict[str, Any]:
    study = _study(); token, decision = _validated_frozen(frozen)
    if not isinstance(sol_schedule, ValidatedSolSchedule) or sol_schedule._token is not _SOL or sol_schedule._frozen is not frozen or study.canonical(_sol_value(frozen)) != sol_schedule._bytes: raise ValueError("mixed evaluator Sol schedule binding drifted")
    schedule = json.loads(sol_schedule._bytes); baseline = study._validated_schedule(token)[0]["candidates"][0]["candidate_id"]
    evidence_sha = study.sha256(Path(native_evidence_path).read_bytes())
    if decision["action"] != "advance_to_sol":
        if schedule["cells"] or _evidence(native_evidence_path, study, "sol_validation", 0): raise ValueError("mixed evaluator baseline stop requires zero Sol cells")
        result = {"format_version": 2, "study_id": study.STUDY_ID, "kind": "receipt_backed_baseline_stop", "native_evidence_sha256": evidence_sha, "passed": False, "action": "baseline_stop", "selected_candidate_id": baseline, "confirmation": {"status": "unopened", "cells": 0}, "claim": "NO-GO"}
        result["decision_sha256"] = study.sha256(result)
        return result
    projected = project_native(validated_schedule=token, route_name="sol_validation", native_evidence_path=native_evidence_path, schedule_value=schedule)
    if {row["cell_id"] for row in projected} != {row["cell_id"] for row in schedule["cells"]}: raise ValueError("mixed evaluator Sol receipt schedule drifted")
    matrix = _matrix({"cells": schedule["cells"]}, projected, "sol_validation"); winner = decision["selected_candidate_id"]; groups = [row["prompt_group_id"] for row in schedule["groups"]]; deltas = [matrix[winner][group] - matrix[baseline][group] for group in groups]; passed = fmean(deltas) <= 1e-12 and max(deltas) <= .1 + 1e-12
    result = {"format_version": 2, "study_id": study.STUDY_ID, "kind": "receipt_backed_two_group_sol_nonreversal_decision", "native_evidence_sha256": evidence_sha, "selected_candidate_id": winner, "aggregate_delta": fmean(deltas), "group_deltas": deltas, "passed": passed, "action": "retain_candidate" if passed else "baseline_stop", "sol_cannot_substitute": True, "native_endpoint_contact_cardinality": "unproven", "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "claim": "EXPLORATORY_POST_HOC_DEVELOPMENT_ONLY; NO-GO until independently replayed native evidence"}
    result["decision_sha256"] = study.sha256(result)
    return result
