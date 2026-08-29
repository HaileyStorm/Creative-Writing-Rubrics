#!/usr/bin/env python3
"""One-cell executor for the frozen HANNA v3 Grok-primary/Sol-gate schedule.

This module deliberately owns no provider policy or optimizer.  It only turns an
already-derived v3 row into immutable request/evidence files and projects settled
native responses through the pinned v2 endpoint implementation.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v3" / "study.py"
STUDY_ID = "hbq-human-alignment-optimizer-v3-executor-v1"
CELL_FIELDS = (
    "cell_id", "item_id", "candidate_id", "partition", "prompt_group_id",
    "provider", "model", "configured_reasoning_effort", "transport_identity",
    "task_payload_sha256", "candidate_instruction_sha256", "candidate_profile_sha256",
    "response_schema_sha256", "prompt_sha256", "story_sha256",
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical(value))


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(f"HANNA v3 executor refuses to overwrite {path.name}") from error


def _read_canonical(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA v3 executor {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != payload:
        raise ValueError(f"HANNA v3 executor {label} is noncanonical")
    return value


def _load_v3() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_hanna_v3_executor_parent", V3_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA v3 study is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.contract()
    return module


def _all_mandatory(schedule: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [*schedule["grok_primary"], *schedule["sol_validation"]]
    if len(rows) != 460 or any(row["partition"] not in {"train", "development"} for row in rows):
        raise ValueError("HANNA v3 executor rejects schedule geometry or confirmation rows")
    if len({row["cell_id"] for row in rows}) != len(rows):
        raise ValueError("HANNA v3 executor schedule cell IDs are duplicated")
    return rows


def _cell(schedule: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    rows = [row for row in _all_mandatory(schedule) if row["cell_id"] == cell_id]
    if len(rows) != 1:
        raise ValueError("HANNA v3 executor accepts only mandatory train/development cells; confirmation is unopened")
    return dict(rows[0])


def _payload(v3: ModuleType, row: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> bytes:
    _study, _harness, _freeze, _split, candidates = v3._material(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    candidate = next((item for item in candidates if item["candidate_id"] == row["candidate_id"]), None)
    if candidate is None:
        raise ValueError("HANNA v3 executor candidate binding drifted")
    freeze_module = v3.v2_module().parent_modules()[2]
    source = freeze_module._source_material(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    ).get(row["item_id"])
    if not isinstance(source, Mapping):
        raise ValueError("HANNA v3 executor source item is absent")
    task = freeze_module._payload_bytes(item=source, candidate=candidate)
    components = {
        "task_payload": task.decode("utf-8"),
        "candidate_instruction": candidate["instruction_bytes"].decode("utf-8"),
        "candidate_profile": candidate["profile_bytes"].decode("utf-8"),
        "response_schema": freeze_module.response_schema_bytes().decode("utf-8"),
        "prompt": source["prompt"],
        "story": source["story"],
    }
    expected = (
        row["task_payload_sha256"], row["candidate_instruction_sha256"], row["candidate_profile_sha256"],
        row["response_schema_sha256"], row["prompt_sha256"], row["story_sha256"],
    )
    actual = tuple(digest_bytes(components[name].encode("utf-8")) for name in components)
    if actual != expected:
        raise ValueError("HANNA v3 executor exact payload component binding drifted")
    return canonical({"format_version": 1, "study_id": STUDY_ID, "components": components})


def _route_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    reported_model = "grok-4.6-build" if row["provider"] == "xai" else row["model"]
    return {
        "requested": {
            "provider": row["provider"], "model": row["model"],
            "reasoning_effort": row["configured_reasoning_effort"],
            "transport_identity": row["transport_identity"],
        },
        "reported_expectation": {
            "provider": "grok" if row["provider"] == "xai" else "openai",
            "model": reported_model,
            "reasoning_attested": False if row["provider"] == "xai" else None,
        },
    }


def _load_pinned_gate_verifier() -> Callable[[dict[str, Any]], Any]:
    """Private trust seam; a caller cannot supply its own gate authority."""
    raise ValueError("HANNA v3 executor has no enabled trusted gate verifier")


def _gate(path: Path, *, kind: str, cell: Mapping[str, Any], disclosure_sha256: str) -> dict[str, Any]:
    value = _read_canonical(path, label=kind)
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "kind": kind, "cell_id": cell["cell_id"],
        "disclosure_sha256": disclosure_sha256,
    }
    if any(value.get(name) != expected[name] for name in expected) or value.get("acknowledged") is not True:
        raise ValueError(f"HANNA v3 executor {kind} gate is invalid")
    outcome = _load_pinned_gate_verifier()({"gate_kind": kind, "gate": value, "cell": dict(cell)})
    if outcome is not True and outcome != {"accepted": True}:
        raise ValueError(f"HANNA v3 executor {kind} gate is not trusted")
    return value


def _disclosure(*, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "pre_contact_local_first_disclosure",
        "cell": {name: row[name] for name in CELL_FIELDS}, "schedule_sha256": schedule["schedule_sha256"],
        "route_identity": _route_identity(row),
        "artifacts_leaving_machine": {"outbound_payload": {"bytes": len(payload), "sha256": digest_bytes(payload), "text": payload.decode("utf-8")}},
        "provider_calls_made": 0,
    }


def _prepared(*, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, disclosure: Mapping[str, Any], acknowledgement: Mapping[str, Any], proof: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "prepared_schedule_cell", "cell": {name: row[name] for name in CELL_FIELDS},
        "schedule_sha256": schedule["schedule_sha256"], "outbound_payload_sha256": digest_bytes(payload), "disclosure_sha256": digest(disclosure),
        "acknowledgement_sha256": digest(acknowledgement), "route_proof_sha256": digest(proof), "provider_calls_made": 0,
    }


def _reject_reparse(path: Path) -> None:
    if path.is_symlink() or os.path.islink(path):
        raise ValueError("HANNA v3 executor reparsed prepared roots are rejected")


def _verify_prepared_root(*, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, cell_id: str, allow_contact_files: bool) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    v3 = _load_v3()
    schedule = v3.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    row = _cell(schedule, cell_id)
    root = Path(output_root) / cell_id
    _reject_reparse(root)
    payload = _payload(v3, row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    disclosure = _disclosure(row=row, schedule=schedule, payload=payload)
    acknowledgement = _gate(root / "acknowledgement.json", kind="acknowledgement", cell=row, disclosure_sha256=digest(disclosure))
    proof = _gate(root / "zero-charge-route-proof.json", kind="zero_charge_route_proof", cell=row, disclosure_sha256=digest(disclosure))
    expected = _prepared(row=row, schedule=schedule, payload=payload, disclosure=disclosure, acknowledgement=acknowledgement, proof=proof)
    if (root / "outbound-payload.json").read_bytes() != payload or _read_canonical(root / "disclosure.json", label="disclosure") != disclosure or _read_canonical(root / "prepared.json", label="prepared manifest") != expected:
        raise ValueError("HANNA v3 executor prepared root binding drifted")
    allowed = {"outbound-payload.json", "disclosure.json", "acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"}
    if allow_contact_files:
        allowed.update({"intent.json", "native-request.bin", "native-response.bin", "result.json"})
    children = {child.name for child in root.iterdir()}
    if not children <= allowed or any((root / name).is_symlink() for name in children):
        raise ValueError("HANNA v3 executor prepared root inventory drifted")
    return row, expected, payload


def prepare_cell(*, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, output_root: Path,
                 acknowledgement_path: Path, route_proof_path: Path) -> dict[str, Any]:
    """Prepare exactly one schedule-owned cell.  This function has no runner/contact path."""
    v3 = _load_v3()
    schedule = v3.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    row = _cell(schedule, cell_id)
    payload = _payload(v3, row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    root = Path(output_root) / cell_id
    if root.exists():
        _verify_prepared_root(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), cell_id=cell_id, allow_contact_files=False)
        return {"cell_id": cell_id, "provider_calls_made": 0, "prepared": True, "resumed": True}
    disclosure = _disclosure(row=row, schedule=schedule, payload=payload)
    disclosure_sha = digest(disclosure)
    acknowledgement = _gate(Path(acknowledgement_path), kind="acknowledgement", cell=row, disclosure_sha256=disclosure_sha)
    proof = _gate(Path(route_proof_path), kind="zero_charge_route_proof", cell=row, disclosure_sha256=disclosure_sha)
    root.mkdir(parents=True, exist_ok=False)
    _write_new(root / "outbound-payload.json", payload)
    _write_new(root / "disclosure.json", canonical(disclosure))
    _write_new(root / "acknowledgement.json", canonical(acknowledgement))
    _write_new(root / "zero-charge-route-proof.json", canonical(proof))
    prepared = _prepared(row=row, schedule=schedule, payload=payload, disclosure=disclosure, acknowledgement=acknowledgement, proof=proof)
    _write_new(root / "prepared.json", canonical(prepared))
    return {"cell_id": cell_id, "provider_calls_made": 0, "prepared": True, "resumed": False}


def _load_pinned_runner() -> Callable[[Mapping[str, Any], bytes, Callable[[], None]], Mapping[str, Any]]:
    """Private production seam; integration tests replace this loader, never a public runner argument."""
    raise ValueError("HANNA v3 executor has no enabled native runner in this package")


def _load_pinned_native_request_verifier() -> Callable[[dict[str, Any]], Any]:
    """Private evidence seam for proving a raw native request represents frozen bytes."""
    raise ValueError("HANNA v3 executor has no enabled native-request verifier")


def _settled(root: Path) -> dict[str, Any] | None:
    result_path = root / "result.json"
    if not result_path.exists():
        return None
    return _read_canonical(result_path, label="attempt result")


def dispatch_prepared_cell(*, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, cell_id: str, allow_remote: bool) -> dict[str, Any]:
    """Perform at most one native call after an exclusive intent; unresolved outcomes never resend."""
    root = Path(output_root) / cell_id
    if allow_remote is not True:
        return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
    row, prepared, payload = _verify_prepared_root(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), cell_id=cell_id, allow_contact_files=True,
    )
    prior = _settled(root)
    if prior is not None:
        return {"cell_id": cell_id, "state": prior["state"], "provider_calls_made": 0, "resumed": True}
    if (root / "intent.json").exists():
        raise ValueError("HANNA v3 executor prior contact intent is unresolved; explicit reconciliation is required")
    intent = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_native_contact", "cell_id": cell_id,
        "prepared_sha256": digest(prepared), "provider_calls_made_before_intent": 0,
    }
    try:
        runner = _load_pinned_runner()
    except BaseException:
        return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
    contacted = False
    def before_native_contact() -> None:
        nonlocal contacted
        if contacted:
            raise ValueError("HANNA v3 executor runner signalled contact twice")
        try:
            _write_new(root / "intent.json", canonical(intent))
        except ValueError as error:
            raise ValueError("HANNA v3 executor prior contact intent is unresolved; explicit reconciliation is required") from error
        contacted = True
    try:
        native = runner(row, payload, before_native_contact)
        if not contacted:
            return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
        if not isinstance(native, Mapping):
            raise ValueError("native runner result is invalid")
        request = native.get("request_bytes")
        response = native.get("response_bytes")
        identity = native.get("identity")
        if not isinstance(request, bytes) or not isinstance(response, bytes) or not isinstance(identity, Mapping):
            raise ValueError("native runner must return raw request/response bytes and identity")
        expected = row
        required_identity = {"provider", "requested_model", "reported_model", "transport_identity", "native_response_id", "native_request_id", "native_session_id"}
        if set(identity) != required_identity or identity["provider"] != expected["provider"] or identity["requested_model"] != expected["model"] or identity["transport_identity"] != expected["transport_identity"]:
            raise ValueError("native identity does not bind the prepared route")
        if expected["provider"] == "xai" and identity["reported_model"] != "grok-4.6-build":
            raise ValueError("Grok reported model identity drifted")
        if expected["provider"] == "openai" and identity["reported_model"] != expected["model"]:
            raise ValueError("Sol reported model identity drifted")
        if any(not isinstance(identity[key], str) or not identity[key] for key in ("native_response_id", "native_request_id", "native_session_id")):
            raise ValueError("native contact identity is incomplete")
        _write_new(root / "native-request.bin", request)
        _write_new(root / "native-response.bin", response)
        result = {
            "format_version": 1, "study_id": STUDY_ID, "kind": "native_cell_result", "state": "native_returned_unprojected",
            "cell_id": cell_id, "intent_sha256": digest(intent), "native_request_sha256": digest_bytes(request), "native_response_sha256": digest_bytes(response),
            "identity": dict(identity), "identity_sha256": digest(dict(identity)), "provider_calls_made": 1,
        }
    except BaseException as error:
        if not contacted:
            return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
        result = {
            "format_version": 1, "study_id": STUDY_ID, "kind": "native_cell_result", "state": "reconcile_required",
            "cell_id": cell_id, "intent_sha256": digest(intent), "error_type": type(error).__name__, "provider_calls_made": 1,
        }
    _write_new(root / "result.json", canonical(result))
    return {"cell_id": cell_id, "state": result["state"], "provider_calls_made": 1, "resumed": False}


def _scheduled_targets(*, v3: ModuleType, rows: Sequence[Mapping[str, Any]], frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, dict[str, float]]:
    """Read human ratings only for v3's 61 train/development item IDs."""
    parent_study = v3.v2_module().parent_modules()[0]
    eligible = parent_study.derive_eligible_map(Path(frozen_successor_path), Path(hanna_csv_path))
    wanted_ids = {row["item_id"] for row in rows}
    selected = {row["item_id"]: row for row in eligible if row["item_id"] in wanted_ids}
    if len(wanted_ids) != 13 or set(selected) != wanted_ids:
        raise ValueError("HANNA v3 scheduled target IDs drifted")
    by_story = {row["story_id"]: row["item_id"] for row in selected.values()}
    ratings: dict[str, list[Mapping[str, str]]] = {item_id: [] for item_id in wanted_ids}
    with Path(hanna_csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            item_id = by_story.get(source.get("Story ID", ""))
            if item_id is not None:
                ratings[item_id].append(source)
    dimensions = v3.v2_module().DIMENSIONS
    targets: dict[str, dict[str, float]] = {}
    for item_id, item in selected.items():
        source_rows = ratings[item_id]
        if len(source_rows) != 3 or any(row.get("Model") != item["source_model"] for row in source_rows):
            raise ValueError("HANNA v3 scheduled target rows drifted")
        targets[item_id] = {dimension: statistics.fmean(float(row[dimension]) for row in source_rows) for dimension in dimensions}
    return targets


def project_mandatory_cells(*, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path) -> dict[str, Any]:
    """Recompute Grok selection and Sol validation from persisted native response bytes only."""
    v3 = _load_v3()
    schedule = v3.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    mandatory_rows = _all_mandatory(schedule)
    rows = [row for row in mandatory_rows if row["partition"] == "development"]
    if len(rows) != 100 or sum(row["model"] == "grok-4.6" for row in rows) != 65 or sum(row["model"] == "gpt-5.6-sol" for row in rows) != 35:
        raise ValueError("HANNA v3 executor development projection geometry drifted")
    v2 = v3.v2_module()
    targets = _scheduled_targets(v3=v3, rows=rows, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    observations: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str, str]] = set()
    for row in rows:
        root = Path(output_root) / row["cell_id"]
        verified_row, prepared, outbound_payload = _verify_prepared_root(
            frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), cell_id=row["cell_id"], allow_contact_files=True,
        )
        if verified_row != row:
            raise ValueError("HANNA v3 projected schedule row drifted")
        intent = _read_canonical(root / "intent.json", label="contact intent")
        if intent != {
            "format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_native_contact", "cell_id": row["cell_id"],
            "prepared_sha256": digest(prepared), "provider_calls_made_before_intent": 0,
        }:
            raise ValueError("HANNA v3 native intent binding drifted")
        result = _read_canonical(root / "result.json", label="native result")
        required_result = {"format_version", "study_id", "kind", "state", "cell_id", "intent_sha256", "native_request_sha256", "native_response_sha256", "identity", "identity_sha256", "provider_calls_made"}
        if set(result) != required_result or result["format_version"] != 1 or result["study_id"] != STUDY_ID or result["kind"] != "native_cell_result" or result["state"] != "native_returned_unprojected" or result["cell_id"] != row["cell_id"] or result["intent_sha256"] != digest(intent) or result["provider_calls_made"] != 1:
            raise ValueError("HANNA v3 projection requires every mandatory settled native cell")
        request = (root / "native-request.bin").read_bytes()
        response = (root / "native-response.bin").read_bytes()
        if digest_bytes(request) != result.get("native_request_sha256") or digest_bytes(response) != result.get("native_response_sha256"):
            raise ValueError("HANNA v3 native request/response bytes drifted")
        request_gate = _load_pinned_native_request_verifier()({"cell": dict(row), "prepared": prepared, "outbound_payload": outbound_payload, "native_request_bytes": request})
        if request_gate is not True and request_gate != {"accepted": True}:
            raise ValueError("HANNA v3 native request is not bound to frozen outbound payload")
        identity = result.get("identity")
        if not isinstance(identity, Mapping) or digest(dict(identity)) != result.get("identity_sha256"):
            raise ValueError("HANNA v3 native identity binding drifted")
        contact = (str(identity.get("provider")), str(identity.get("native_response_id")), str(identity.get("native_request_id")), str(identity.get("native_session_id")))
        if contact in identities:
            raise ValueError("HANNA v3 native contact identity is duplicated")
        identities.add(contact)
        scores, coverage, reported = v2._extract_native(response, provider=row["provider"], model=row["model"])
        if reported["reported_model"] != identity["reported_model"]:
            raise ValueError("HANNA v3 persisted native response/model identity is misassociated")
        if row["provider"] == "xai" and (reported["native_request_id_sha256"] != digest_bytes(str(identity["native_request_id"]).encode("utf-8")) or reported["native_session_id_sha256"] != digest_bytes(str(identity["native_session_id"]).encode("utf-8"))):
            raise ValueError("HANNA v3 persisted Grok contact identity is misassociated")
        if row["provider"] == "openai" and reported["native_response_id_sha256"] != digest_bytes(str(identity["native_response_id"]).encode("utf-8")):
            raise ValueError("HANNA v3 persisted Sol contact identity is misassociated")
        observations.append({**row, "scores": scores, "coverage": coverage})
    def metrics(route: str, expected_items: int, expected_groups: int) -> list[dict[str, Any]]:
        result = []
        for candidate in schedule["candidate_ids"]:
            subset = [row for row in observations if row["model"] == route and row["candidate_id"] == candidate and row["partition"] == "development"]
            result.append({"candidate_id": candidate, "candidate_sha256": next(item["candidate_sha256"] for item in v3.candidate_pack() if item["candidate_id"] == candidate), "development": v2._candidate_endpoint(subset, targets, expected_items=expected_items, expected_groups=expected_groups)})
        return result
    grok = metrics("grok-4.6", 13, 7)
    frozen = v3.freeze_grok_selection(grok, schedule=schedule)
    sol = metrics("gpt-5.6-sol", 7, 7)
    validation = v3.validate_sol_generalization(frozen, grok, sol, schedule=schedule)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "independent_native_cell_projection", "grok_selection": frozen, "sol_validation": validation, "confirmation": {"status": "unopened", "scheduled_cells": 0}, "empirical_authority": "none_until_native_request_verifier_and_provider_receipt_trust_are_independently_accepted"}
