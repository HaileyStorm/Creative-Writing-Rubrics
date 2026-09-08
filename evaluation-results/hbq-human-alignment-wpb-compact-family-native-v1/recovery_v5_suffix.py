"""Side-by-side, v5-only admission for the untouched WPB 0918 suffix."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HELPER_PATH = Path(__file__).resolve()
HERE = HELPER_PATH.parent
FROZEN_RECOVERY = HERE / "recovery.py"
FROZEN_RECOVERY_SHA256 = "3bd13df9f27f71563e3a0bf444b22e5bdc3741ca5b3ef278a2254227a155f5ec"
CANONICAL_BROKER = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\broker.py")
CANONICAL_ADAPTER = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\adapters\grok_exec.py")
FIRST_V5_CELL = "wpb-pair-wpb-en-0918"
V5_COUNT = 27
_HEX = set("0123456789abcdef")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO UTC timestamp") from error
    _require(parsed.tzinfo is not None, f"{label} must include UTC offset")
    return parsed.astimezone(timezone.utc)


def _frozen() -> ModuleType:
    raw = FROZEN_RECOVERY.read_bytes()
    _require(_hash(raw) == FROZEN_RECOVERY_SHA256, "frozen recovery source drifted")
    spec = importlib.util.spec_from_file_location("wpb_v5_frozen_recovery", FROZEN_RECOVERY)
    _require(spec is not None and spec.loader is not None, "cannot load frozen recovery")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(FROZEN_RECOVERY.read_bytes() == raw, "frozen recovery changed during load")
    return module


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not UTF-8 JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def _suffix(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells = plan.get("cells")
    _require(isinstance(cells, list) and len(cells) == 40, "recovery plan geometry drifted")
    values = [dict(item) for item in cells if isinstance(item, Mapping)]
    _require(len(values) == 40 and len({item.get("cell_id") for item in values}) == 40, "recovery plan cells are malformed")
    start = next((index for index, item in enumerate(values) if item.get("cell_id") == FIRST_V5_CELL), None)
    _require(start is not None, "0918 is absent from the frozen plan")
    suffix = values[start:]
    _require(len(suffix) == V5_COUNT and all(item.get("kind") == "unstarted" for item in suffix), "v5 suffix is not exactly 0918 plus 26 untouched cells")
    return suffix


def _source_descriptor(value: Any, label: str, *, forbidden: Path | None = None) -> dict[str, str]:
    _require(isinstance(value, Mapping), f"{label} descriptor is malformed")
    path, digest = value.get("path"), value.get("sha256")
    _require(isinstance(path, str) and isinstance(digest, str), f"{label} descriptor is malformed")
    resolved = Path(path).resolve()
    _require(resolved.is_file() and _hash(resolved.read_bytes()) == _hex(digest, f"{label} hash"), f"{label} source drifted")
    _require(forbidden is None or resolved != forbidden.resolve(), f"{label} must not use the canonical shared source")
    return {"path": str(resolved), "sha256": digest}


def _candidate(candidate: Mapping[str, Any], frozen: ModuleType) -> dict[str, Any]:
    package = candidate.get("package_manifest")
    _require(isinstance(package, Mapping), "candidate manifest is malformed")
    manifest_descriptor = _source_descriptor(package, "candidate manifest")
    manifest_path = Path(manifest_descriptor["path"])
    manifest, _raw = _json(manifest_path, "candidate manifest")
    files = manifest.get("files")
    # The exact manifest hash is independently reviewed; its revision is not the adapter transport version.
    _require(isinstance(manifest.get("schema_version"), int) and not isinstance(manifest.get("schema_version"), bool) and manifest["schema_version"] > 0
             and manifest.get("kind") == "complete_candidate_runtime_probe_set"
             and manifest.get("explicit_exclusion") == ["candidate-manifest.json"] and isinstance(files, list), "candidate manifest shape drifted")
    root = manifest_path.parent.resolve()
    members: dict[str, str] = {}
    for item in files:
        _require(isinstance(item, Mapping) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str), "candidate manifest member is malformed")
        member = (root / item["path"]).resolve()
        _require(member.is_relative_to(root) and member.is_file() and _hash(member.read_bytes()) == _hex(item["sha256"], "candidate member hash"), "candidate manifest member drifted")
        _require(item["path"] not in members, "candidate manifest has duplicate member")
        members[item["path"]] = item["sha256"]
    broker = _source_descriptor(candidate.get("broker"), "candidate broker", forbidden=CANONICAL_BROKER)
    adapter = _source_descriptor(candidate.get("adapter"), "candidate adapter", forbidden=CANONICAL_ADAPTER)
    _require(broker == {"path": str((root / "model_work_queue/broker.py").resolve()), "sha256": members.get("model_work_queue/broker.py")}
             and adapter == {"path": str((root / "model_work_queue/adapters/grok_exec.py").resolve()), "sha256": members.get("model_work_queue/adapters/grok_exec.py")}, "candidate sources are not manifest members")
    queue = Path(str(candidate.get("isolated_queue_root", ""))).resolve()
    _require(queue.is_dir() and queue != Path(frozen.QUEUE_ROOT).resolve(), "candidate must use an isolated queue")
    return {"package_manifest": manifest_descriptor, "broker": broker, "adapter": adapter, "isolated_queue_root": str(queue)}


def _disjoint(left: Path, right: Path) -> None:
    _require(not left.is_relative_to(right) and not right.is_relative_to(left), "v5 suffix root must be disjoint from the old recovery root")


def _old_0918(*, frozen: ModuleType, plan: Mapping[str, Any], root: Path, review: Mapping[str, Any], suffix: list[dict[str, Any]]) -> None:
    cell = root / "cells" / FIRST_V5_CELL
    binding = review.get("0918_original")
    _require(isinstance(binding, Mapping) and binding.get("cell_id") == FIRST_V5_CELL, "0918 original evidence binding is absent")
    descriptors = {name: _source_descriptor(binding.get(name), f"0918 {name}") for name in ("attempt", "outcome", "request", "prepared")}
    _require(descriptors == {name: {"path": str((cell / f"{name}.json").resolve()), "sha256": _hash((cell / f"{name}.json").read_bytes())} for name in descriptors}, "0918 original evidence path drifted")
    outcome, _outcome_raw = _json(cell / "outcome.json", "0918 original outcome")
    prepared, _prepared_raw = _json(cell / "prepared.json", "0918 original prepared")
    row, payload = _payload(frozen, plan, FIRST_V5_CELL)
    _require(outcome.get("state") == "definitely_not_contacted" and outcome.get("result") is None
             and prepared == {"cell_id": FIRST_V5_CELL, "kind": "unstarted", "payload_sha256": row["payload_sha256"]}
             and _json(cell / "request.json", "0918 original request")[0] == {"prompt": payload.decode("utf-8")}, "0918 original DNC or payload binding drifted")
    for item in suffix[1:]:
        later = root / "cells" / item["cell_id"]
        _require(not any((later / name).exists() for name in ("attempt.json", "outcome.json", "admission.json")), "later v5 suffix cell was touched in the old recovery root")


def _authority(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, reviewed_path: Path | str,
               expected_review_sha256: str, candidate: Mapping[str, Any], require_live: bool) -> tuple[dict[str, Any], dict[str, Any], ModuleType, list[dict[str, Any]]]:
    frozen = _frozen()
    root = Path(recovery_root).resolve()
    target = Path(suffix_root).resolve()
    _disjoint(root, target)
    plan = frozen._read_plan(root, _hex(expected_plan_sha256, "expected recovery plan hash"))
    frozen._verify_origin(plan)
    suffix = _suffix(plan)
    review, raw = _json(Path(reviewed_path).resolve(), "v5 suffix review")
    _require(_hash(raw) == _hex(expected_review_sha256, "expected v5 suffix review hash"), "v5 suffix review hash drifted")
    route, gate = review.get("route"), review.get("gate")
    _require(review.get("decision") == "approved_wpb_v5_side_by_side_suffix" and review.get("recovery_plan_sha256") == expected_plan_sha256
             and review.get("suffix_root") == str(target) and review.get("cell_ids") == [item["cell_id"] for item in suffix] and review.get("0918_precontact_derivative") is True
             and isinstance(route, Mapping) and review.get("route_sha256") == _hash(dict(route))
             and isinstance(gate, Mapping) and review.get("gate_sha256") == _hash(dict(gate)), "v5 review scope, route, or gate drifted")
    _require(route.get("timeout_seconds") == 300 and route.get("max_concurrency") == 1 and route.get("nonvisual_max_turns") == 1, "v5 route must remain 300/1/1")
    helper = {"path": str(HELPER_PATH), "sha256": _hash(HELPER_PATH.read_bytes())}
    _require(review.get("helper") == helper, "v5 helper source binding drifted")
    _old_0918(frozen=frozen, plan=plan, root=root, review=review, suffix=suffix)
    bound = _candidate(candidate, frozen)
    _require(review.get("candidate") == bound, "v5 candidate binding drifted")
    reviewed = _timestamp(review.get("reviewed_at"), "v5 review reviewed_at")
    expires = _timestamp(review.get("expires_at"), "v5 review expires_at")
    if require_live:
        now = datetime.now(timezone.utc)
        _require(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "v5 review does not cover the route timeout")
    return plan, {"route": dict(route), "gate": dict(gate), "candidate": bound, "review": {"path": str(Path(reviewed_path).resolve()), "sha256": expected_review_sha256}, "helper": helper}, frozen, suffix


def verify_authority(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, reviewed_path: Path | str,
                     expected_review_sha256: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Validate side-package authority without loading a broker or contacting a provider."""
    _plan, authority, _frozen_module, suffix = _authority(recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
                                                            reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
                                                            candidate=candidate, require_live=False)
    return {"cell_ids": [item["cell_id"] for item in suffix], "provider_calls_made": 0, "native_admission_permitted": False,
            "candidate": authority["candidate"]}


def _payload(frozen: ModuleType, plan: Mapping[str, Any], cell_id: str) -> tuple[dict[str, Any], bytes]:
    legacy = frozen._load_legacy()
    resolution, rows = frozen._rows(legacy, Path(plan["freeze_root"]))
    item = rows.get(cell_id)
    _require(isinstance(item, Mapping) and resolution.get("schedule_sha256") == plan.get("schedule_sha256"), "v5 payload or schedule drifted")
    payload = resolution["payloads"][cell_id]
    _require(frozen.sha256(payload) == item.get("payload_sha256"), "v5 payload bytes drifted")
    return dict(item), payload


def _candidate_broker(frozen: ModuleType, candidate: Mapping[str, Any]) -> type[Any]:
    _module, broker_type = frozen._load_broker(Path(str(candidate["broker"]["path"])))
    _require(callable(getattr(broker_type, "run_grok_native_request", None)) and callable(getattr(broker_type, "read_grok_native_envelope", None))
             and callable(getattr(broker_type, "_parse_grok_exec_envelope", None)), "candidate broker surface drifted")
    return broker_type


def _observe_gate(broker: Any, route: Mapping[str, Any], gate: Mapping[str, Any], *, initial: bool) -> dict[str, Any]:
    path, expected = gate.get("path"), gate.get("row")
    _require(isinstance(path, str) and isinstance(expected, Mapping), "v5 reviewed gate is malformed")
    gate_path = Path(path).resolve()
    _require(gate_path == Path(broker.grok_host_gate_path).resolve() and gate_path.is_file(), "v5 reviewed gate path drifted")
    uri = f"file:{gate_path.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT contract_hash,max_concurrency,state,detail,updated_at,source_evidence_hash FROM grok_host_gates WHERE provider=? AND account_class=?", (route.get("provider"), route.get("account_class"))).fetchone()
            _require(row is not None and dict(row) == dict(expected), "v5 reviewed gate row drifted")
            if initial:
                active = db.execute("SELECT COUNT(*) FROM grok_host_slots WHERE provider=? AND account_class=?", (route.get("provider"), route.get("account_class"))).fetchone()[0]
                _require(active == 0, "v5 host gate has an active slot")
    except sqlite3.Error as error:
        raise ValueError("v5 reviewed gate is unavailable") from error
    return {"path": str(gate_path), "row": dict(expected)}


def _attempt(*, cell_id: str, plan_sha256: str, review_sha256: str, item: Mapping[str, Any], payload: bytes,
             schema: Mapping[str, Any], authority: Mapping[str, Any], session_id: str, gate_observation: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "cell_id": cell_id, "plan_sha256": plan_sha256, "review_sha256": review_sha256,
            "payload_sha256": item["payload_sha256"], "schema_sha256": _hash(dict(schema)), "route_sha256": _hash(authority["route"]),
            "gate_sha256": _hash(authority["gate"]), "gate_observation_sha256": _hash(dict(gate_observation)), "candidate": authority["candidate"], "review": authority["review"], "helper": authority["helper"], "session_id": session_id,
            "session_id_hash": _hash(session_id.encode("utf-8")), "route_name": authority["route"].get("name"),
            "requested_model": authority["route"].get("model"), "requested_reasoning_effort": authority["route"].get("reasoning_effort"),
            "request_sha256": _hash({"prompt": payload.decode("utf-8")})}


def _guard_inflight(*, recovery_root: Path | str, expected_plan_sha256: str, cell_id: str, reviewed_path: Path | str,
                    expected_review_sha256: str, candidate: Mapping[str, Any], suffix_root: Path, attempt: Mapping[str, Any],
                    gate_observation: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], ModuleType]:
    plan, authority, frozen, suffix = _authority(recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
                                                  reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
                                                  candidate=candidate, require_live=True)
    _require(cell_id in {item["cell_id"] for item in suffix}, "cell is not in v5 suffix")
    _require((suffix_root / "cells" / cell_id / "v5-attempt.json").is_file() and not (suffix_root / "cells" / cell_id / "outcome.json").exists(), "v5 in-flight attempt is not exclusive")
    row, payload = _payload(frozen, plan, cell_id)
    schema = frozen._frozen_schema(plan)
    expected = _attempt(cell_id=cell_id, plan_sha256=expected_plan_sha256, review_sha256=expected_review_sha256, item=row,
                        payload=payload, schema=schema, authority=authority, session_id=str(attempt.get("session_id", "")), gate_observation=gate_observation)
    _require(dict(attempt) == expected, "v5 in-flight attempt binding drifted")
    return plan, authority, frozen


def dispatch(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str,
             reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Make one reviewed v5 request; every broker outcome permanently consumes its suffix cell."""
    source, target = Path(recovery_root).resolve(), Path(suffix_root).resolve()
    _require(source != target, "v5 suffix evidence must not write the old recovery root")
    plan, authority, frozen, suffix = _authority(recovery_root=source, suffix_root=target, expected_plan_sha256=expected_plan_sha256,
                                                  reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
                                                  candidate=candidate, require_live=True)
    cell_ids = [item["cell_id"] for item in suffix]
    _require(cell_id in cell_ids, "cell is not in v5 suffix")
    cell = target / "cells" / cell_id
    _require(not (cell / "v5-attempt.json").exists() and not (cell / "outcome.json").exists() and not (cell / "v5-admission.json").exists(), "v5 cell is already consumed; no resend")
    for prior in cell_ids[:cell_ids.index(cell_id)]:
        _verify_admission(recovery_root=source, suffix_root=target, expected_plan_sha256=expected_plan_sha256, cell_id=prior,
                          reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256, candidate=candidate)
    row, payload = _payload(frozen, plan, cell_id)
    schema = frozen._frozen_schema(plan)
    _require(isinstance(authority["route"].get("name"), str) and authority["route"]["name"], "v5 route has no name")
    broker_type = _candidate_broker(frozen, authority["candidate"])
    broker = broker_type(Path(authority["candidate"]["isolated_queue_root"]))
    gate_observation = _observe_gate(broker, authority["route"], authority["gate"], initial=True)
    session_id = str(uuid.uuid4())
    attempt = _attempt(cell_id=cell_id, plan_sha256=expected_plan_sha256, review_sha256=expected_review_sha256, item=row,
                       payload=payload, schema=schema, authority=authority, session_id=session_id, gate_observation=gate_observation)
    frozen._write_new(cell / "v5-attempt.json", attempt)
    frozen._write_new(cell / "route.json", authority["route"])
    frozen._write_new(cell / "gate.json", authority["gate"])
    frozen._write_new(cell / "gate-observation-initial.json", gate_observation)
    frozen._write_new(cell / "request.json", {"prompt": payload.decode("utf-8")})
    frozen._write_new(cell / "response-schema.json", schema)
    def before_contact() -> None:
        _guard_inflight(recovery_root=source, expected_plan_sha256=expected_plan_sha256, cell_id=cell_id,
                        reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256, candidate=candidate,
                        suffix_root=target, attempt=attempt, gate_observation=gate_observation)
        observed = _observe_gate(broker, authority["route"], authority["gate"], initial=False)
        _require(observed == gate_observation, "v5 reviewed gate row drifted")
        frozen._write_new(cell / "gate-observation-before-contact.json", observed)

    outcome = broker.run_grok_native_request(str(authority["route"]["name"]), {"prompt": payload.decode("utf-8")}, output_schema=schema,
                                              nonvisual_max_turns=1, session_id=session_id, before_contact=before_contact,
                                              expected_route_sha256=_hash(authority["route"]))
    _require(isinstance(outcome, Mapping) and set(outcome) == {"state", "result", "failure"}, "candidate broker outcome is malformed")
    frozen._write_new(cell / "outcome.json", dict(outcome))
    if outcome["state"] != "completed" or outcome["failure"] is not None or not isinstance(outcome["result"], Mapping):
        return {"cell_id": cell_id, "status": "terminal_no_resend", "outcome_sha256": _hash(dict(outcome)),
                "provider_calls_made": 0 if outcome["state"] == "definitely_not_contacted" else 1}
    result = dict(outcome["result"])
    descriptor = result.get("native_envelope_artifact")
    _require(isinstance(descriptor, Mapping), "completed candidate result lacks envelope descriptor")
    envelope = broker.read_grok_native_envelope(dict(descriptor))
    _require(isinstance(envelope, bytes), "candidate broker returned a non-byte envelope")
    frozen._write_new(cell / "result.json", result)
    with (cell / "native-envelope.json").open("xb") as handle:
        handle.write(envelope)
    return {"cell_id": cell_id, "status": "completed_pending_v5_admission", "result_sha256": _hash(result),
            "envelope_sha256": _hash(envelope), "provider_calls_made": 1}


def _validate_provider_evidence(*, frozen: ModuleType, plan: Mapping[str, Any], cell: Path, attempt: Mapping[str, Any],
                                result: Mapping[str, Any], envelope_raw: bytes, authority: Mapping[str, Any]) -> tuple[str, str]:
    route, _route_raw = _json(cell / "route.json", "v5 route")
    gate, _gate_raw = _json(cell / "gate.json", "v5 gate")
    request, _request_raw = _json(cell / "request.json", "v5 request")
    schema, schema_raw = _json(cell / "response-schema.json", "v5 response schema")
    _require(route == authority["route"] and gate == authority["gate"] and _hash(route) == attempt.get("route_sha256")
             and _hash(gate) == attempt.get("gate_sha256") and schema_raw == _canonical(schema)
             and _hash(schema_raw) == attempt.get("schema_sha256") and schema == frozen._frozen_schema(plan), "v5 route, gate, or schema commitment drifted")
    row, payload = _payload(frozen, plan, cell.name)
    _require(attempt.get("payload_sha256") == row["payload_sha256"] and request == {"prompt": payload.decode("utf-8")}
             and attempt.get("request_sha256") == _hash(request), "v5 request payload drifted")
    _require(attempt.get("candidate") == authority["candidate"], "v5 candidate source commitment drifted")
    broker_type = _candidate_broker(frozen, authority["candidate"])
    broker = broker_type(Path(authority["candidate"]["isolated_queue_root"]))
    descriptor = result.get("native_envelope_artifact")
    _require(isinstance(descriptor, Mapping) and broker.read_grok_native_envelope(dict(descriptor)) == envelope_raw, "retained native envelope bytes differ from the candidate artifact")
    effective_route = {**route, "output_schema": schema, "output_schema_artifact_hash": _hash(schema_raw), "nonvisual_max_turns": 1}
    projection = _canonical({"control": {"version": 1, "state": "completed"}, "result": dict(result)})
    parsed = broker._parse_grok_exec_envelope(projection, effective_route, request, expected_session_id=str(attempt["session_id"]))
    _require(getattr(parsed, "state", None) == "completed" and getattr(parsed, "result", None) == result, "candidate Grok envelope replay failed")
    try:
        envelope = json.loads(envelope_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("v5 native envelope is not JSON") from error
    _require(isinstance(envelope, Mapping) and envelope.get("structuredOutput") == result.get("output"), "v5 envelope output binding drifted")
    request_id, session_id = envelope.get("requestId"), envelope.get("sessionId")
    _require(isinstance(request_id, str) and request_id and isinstance(session_id, str) and session_id
             and session_id == attempt["session_id"], "v5 envelope identity binding drifted")
    return request_id, session_id


def _admission_evidence(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str,
                        reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], ModuleType, Path, dict[str, Any], dict[str, Any], bytes, str, str, str]:
    plan, authority, frozen, suffix = _authority(recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
                                                  reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
                                                  candidate=candidate, require_live=False)
    _require(cell_id in {item["cell_id"] for item in suffix}, "cell is not in v5 suffix")
    cell = Path(suffix_root).resolve() / "cells" / cell_id
    _require(all((cell / name).is_file() for name in ("v5-attempt.json", "outcome.json", "result.json", "native-envelope.json", "route.json", "gate.json", "gate-observation-initial.json", "gate-observation-before-contact.json", "request.json", "response-schema.json")), "v5 raw evidence is missing")
    attempt, _attempt_raw = _json(cell / "v5-attempt.json", "v5 attempt")
    outcome, _outcome_raw = _json(cell / "outcome.json", "v5 outcome")
    result, result_raw = _json(cell / "result.json", "v5 native result")
    observed, _observed_raw = _json(cell / "gate-observation-initial.json", "v5 initial gate observation")
    callback_observed, _callback_raw = _json(cell / "gate-observation-before-contact.json", "v5 callback gate observation")
    envelope_raw = (cell / "native-envelope.json").read_bytes()
    _require(outcome.get("state") == "completed" and outcome.get("failure") is None and outcome.get("result") == result, "v5 cell has no completed native result")
    row, payload = _payload(frozen, plan, cell_id)
    expected_attempt = _attempt(cell_id=cell_id, plan_sha256=expected_plan_sha256, review_sha256=expected_review_sha256, item=row,
                                payload=payload, schema=frozen._frozen_schema(plan), authority=authority, session_id=str(attempt.get("session_id", "")), gate_observation=observed)
    _require(attempt == expected_attempt, "v5 attempt binding drifted")
    _require(callback_observed == observed, "v5 callback gate observation drifted")
    request_id, session_id = _validate_provider_evidence(frozen=frozen, plan=plan, cell=cell, attempt=attempt, result=result,
                                                          envelope_raw=envelope_raw, authority=authority)
    descriptor, runtime = result.get("native_envelope_artifact"), result.get("runtime")
    _require(set(result) == {"schema_version", "request_hash", "output", "output_hash", "runtime", "native_envelope_artifact"}
             and result.get("schema_version") == 2 and isinstance(descriptor, Mapping)
             and descriptor == {"schema_version": 1, "sha256": _hash(envelope_raw), "byte_length": len(envelope_raw)}
             and result.get("request_hash") == _hash({"prompt": payload.decode("utf-8")}) and result.get("output_hash") == _hash(result.get("output"))
             and isinstance(runtime, Mapping), "v5 result payload binding drifted")
    execution = runtime.get("execution_contract")
    _require(runtime.get("adapter_version") == 5 and runtime.get("identity_evidence") == "requested_only"
             and runtime.get("execution_policy") == "bounded_nonvisual_deny_wins_attested" and runtime.get("reasoning_attested") is False
             and isinstance(runtime.get("tool_policy_attestation_hash"), str) and len(runtime["tool_policy_attestation_hash"]) == 64
             and isinstance(execution, Mapping) and execution.get("tools") == "deny_wins_none_attested" and execution.get("max_turns") == 1
             and execution.get("output_schema_hash") == attempt["schema_sha256"] and execution.get("staged_prompt_sha256") == row["payload_sha256"]
             and execution.get("staged_prompt_byte_length") == len(payload) and isinstance(execution.get("nonvisual_transport_contract"), Mapping)
             and execution.get("nonvisual_transport_contract_sha256") == _hash(dict(execution["nonvisual_transport_contract"]))
             and runtime.get("session_id_hash") == attempt["session_id_hash"] and runtime.get("envelope_hash") == _hash(envelope_raw),
             "v5 result lacks adapter-v5 deny-wins attestation")
    if isinstance(attempt.get("requested_model"), str):
        _require(runtime.get("requested_model") == attempt["requested_model"], "v5 result model drifted")
    if isinstance(attempt.get("requested_reasoning_effort"), str):
        _require(runtime.get("requested_reasoning_effort") == attempt["requested_reasoning_effort"], "v5 result reasoning drifted")
    _require(runtime.get("request_id_hash") == _hash(request_id.encode("utf-8")) and runtime.get("session_id_hash") == _hash(session_id.encode("utf-8")), "v5 runtime identity drifted")
    return plan, authority, frozen, cell, result, dict(runtime), envelope_raw, request_id, session_id, _hash(result_raw)


def _prefix_identities(frozen: ModuleType, plan: Mapping[str, Any], recovery_root: Path) -> tuple[set[str], set[str], set[str]]:
    cells = [dict(item) for item in plan.get("cells", []) if isinstance(item, Mapping)]
    first = next((index for index, item in enumerate(cells) if item.get("cell_id") == FIRST_V5_CELL), None)
    _require(first == 13 and cells[1].get("cell_id") == "wpb-pair-wpb-en-0843", "v5 predecessor geometry drifted")
    admitted = [frozen._verify_admission(plan, recovery_root, item) for item in cells[:first] if item.get("cell_id") != "wpb-pair-wpb-en-0843"]
    _require(len(admitted) == 12, "v5 must reserve exactly the twelve native-v4 predecessors")
    identities = {item.get("identity_sha256") for item in admitted}
    requests = {item.get("request_id_sha256") for item in admitted}
    sessions = {item.get("session_id_sha256") for item in admitted}
    _require(all(isinstance(item, str) and len(item) == 64 for item in identities | requests | sessions)
             and len(identities) == len(requests) == len(sessions) == 12, "native-v4 predecessor identity inventory drifted")
    return set(identities), set(requests), set(sessions)


def _admission(*, plan: Mapping[str, Any], frozen: ModuleType, recovery_root: Path, cell: Path, result: Mapping[str, Any], runtime: Mapping[str, Any],
               envelope_raw: bytes, request_id: str, session_id: str, result_sha256: str, expected_plan_sha256: str,
               expected_review_sha256: str) -> dict[str, Any]:
    row, _payload_value = _payload(frozen, plan, cell.name)
    identity, request_hash, session_hash = _hash({"request_id": request_id, "session_id": session_id}), _hash(request_id.encode("utf-8")), _hash(session_id.encode("utf-8"))
    prefix_identities, prefix_requests, prefix_sessions = _prefix_identities(frozen, plan, recovery_root)
    _require(identity not in set(plan["origin"]["reserved_identity_hashes"]) and identity not in prefix_identities
             and request_hash not in set(plan["origin"].get("reserved_request_id_hashes", []))
             and request_hash not in prefix_requests and session_hash not in set(plan["origin"].get("reserved_session_id_hashes", []))
             and session_hash not in prefix_sessions, "v5 identity overlaps original or native-v4 evidence")
    for path in (cell.parent.parent / "cells").glob("*/v5-admission.json"):
        if path.parent == cell:
            continue
        prior, _raw = _json(path, "prior v5 admission")
        _require(prior.get("identity_sha256") != identity and prior.get("request_id_sha256") != request_hash and prior.get("session_id_sha256") != session_hash, "v5 identity overlaps another suffix cell")
    legacy = frozen._load_legacy()
    resolution, _rows = frozen._rows(legacy, Path(plan["freeze_root"]))
    answer = legacy._valid_response(resolution["core"], result["output"])
    return {"format_version": 1, "cell_id": cell.name, "plan_sha256": expected_plan_sha256, "review_sha256": expected_review_sha256,
            "result_sha256": result_sha256, "envelope_sha256": _hash(envelope_raw), "identity_sha256": identity,
            "request_id_sha256": request_hash, "session_id_sha256": session_hash, "payload_sha256": row["payload_sha256"],
            "adapter_version": 5, "tool_policy_attestation_hash": runtime["tool_policy_attestation_hash"], "response": answer}


def _verify_admission(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str,
                      reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    cell = Path(suffix_root).resolve() / "cells" / cell_id
    _require((cell / "v5-attempt.json").is_file(), "v5 raw evidence is missing")
    attempt, _attempt_raw = _json(cell / "v5-attempt.json", "v5 attempt")
    review = attempt.get("review")
    _require(isinstance(review, Mapping) and isinstance(review.get("path"), str) and isinstance(review.get("sha256"), str), "v5 recorded review binding is malformed")
    data = _admission_evidence(recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
                               cell_id=cell_id, reviewed_path=review["path"], expected_review_sha256=review["sha256"], candidate=candidate)
    plan, _authority_value, frozen, cell, result, runtime, envelope_raw, request_id, session_id, result_sha256 = data
    admission, _raw = _json(cell / "v5-admission.json", "v5 admission")
    _require(admission == _admission(plan=plan, frozen=frozen, recovery_root=Path(recovery_root).resolve(), cell=cell, result=result, runtime=runtime, envelope_raw=envelope_raw,
                                     request_id=request_id, session_id=session_id, result_sha256=result_sha256,
                                     expected_plan_sha256=expected_plan_sha256, expected_review_sha256=review["sha256"]), "v5 admission commitment drifted")
    return admission


def admit(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str,
          reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Admit one completed v5 suffix result after replaying all retained evidence."""
    target = Path(suffix_root).resolve()
    _require(Path(recovery_root).resolve() != target, "v5 suffix evidence must not write the old recovery root")
    plan, _authority_value, frozen, suffix = _authority(recovery_root=recovery_root, suffix_root=target, expected_plan_sha256=expected_plan_sha256,
                                                  reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
                                                  candidate=candidate, require_live=False)
    cell_ids = [item["cell_id"] for item in suffix]
    _require(cell_id in cell_ids, "cell is not in v5 suffix")
    cell = target / "cells" / cell_id
    _require(not (cell / "v5-admission.json").exists(), "v5 cell already admitted")
    for prior in cell_ids[:cell_ids.index(cell_id)]:
        _verify_admission(recovery_root=recovery_root, suffix_root=target, expected_plan_sha256=expected_plan_sha256, cell_id=prior,
                          reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256, candidate=candidate)
    data = _admission_evidence(recovery_root=recovery_root, suffix_root=target, expected_plan_sha256=expected_plan_sha256,
                               cell_id=cell_id, reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256, candidate=candidate)
    plan, _authority_value, frozen, evidence_cell, result, runtime, envelope_raw, request_id, session_id, result_sha256 = data
    admission = _admission(plan=plan, frozen=frozen, recovery_root=Path(recovery_root).resolve(), cell=evidence_cell, result=result, runtime=runtime, envelope_raw=envelope_raw,
                           request_id=request_id, session_id=session_id, result_sha256=result_sha256,
                           expected_plan_sha256=expected_plan_sha256, expected_review_sha256=expected_review_sha256)
    raw = frozen._write_new(cell / "v5-admission.json", admission)
    return {"cell_id": cell_id, "admission_sha256": _hash(raw), "status": "admitted", "provider_calls_made": 0}
