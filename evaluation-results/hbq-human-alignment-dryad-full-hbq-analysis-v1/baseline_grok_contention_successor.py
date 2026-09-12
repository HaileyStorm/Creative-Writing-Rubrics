"""One prospective C97 frozen wave of at most ten slots, inert until activation exists."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import threading
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
LOADER = HERE / "baseline_grok_contention_candidate.py"
SNAPSHOT = HERE / "baseline_runtime_data_snapshot.py"
LOADER_SHA256 = "025d9f9bcd3c9034581b38aa93f86b86caf2a0541a5882c9d292115b93a90815"
SNAPSHOT_SHA256 = "eb068749b2483d4b8ca480e5e57865692b89518fe924848f57d324574d167b0c"
CANDIDATE_MANIFEST_SHA256 = "c97c18af74ebbaebb1919760274eae5bacf9877373c0d7a8e6a1bae25de104f0"
SNAPSHOT_HELPERS_SHA256 = "eb068749b2483d4b8ca480e5e57865692b89518fe924848f57d324574d167b0c"
WAVE_CAP = 10
LOGICAL_ORDINALS = [*range(1, 1611), *range(4049, 4739)]
_BATCH_VALIDATION_LOCK = threading.RLock()


def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _canon(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
def _need(value: bool, message: str) -> None:
    if not value: raise ValueError(message)
def _new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output: output.write(_canon(value))
def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try: raw = path.read_bytes(); value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object"); return value, raw
def _bound(value: Any, label: str) -> tuple[dict[str, Any], bytes]:
    _need(isinstance(value, Mapping) and set(value) == {"path", "sha256"} and isinstance(value["path"], str) and isinstance(value["sha256"], str), f"{label} descriptor differs")
    path = Path(value["path"]); raw = path.read_bytes(); _need(_sha(raw) == value["sha256"], f"{label} source drift"); return dict(value), raw
def _load(path: Path, expected: str, name: str) -> ModuleType:
    raw = path.read_bytes(); _need(_sha(raw) == expected, f"{name} source pin differs")
    spec = importlib.util.spec_from_file_location(name, path); _need(spec is not None and spec.loader is not None, f"{name} load differs")
    old_bytecode, previous_module = sys.dont_write_bytecode, sys.modules.get(name); sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_bytecode
        if previous_module is None: sys.modules.pop(name, None)
        else: sys.modules[name] = previous_module
    _need(path.read_bytes() == raw, f"{name} source changed"); return module


def _identities_unique(values: list[Mapping[str, Any]]) -> bool:
    request = [item.get("request_id_hash") for item in values]; session = [item.get("session_id_hash") for item in values]
    return all(isinstance(item, str) and len(item) == 64 for item in request + session) and len(request) == len(set(request)) and len(session) == len(set(session))


def _identities(value: Any, label: str) -> list[dict[str, Any]]:
    _need(isinstance(value, list) and all(isinstance(item, Mapping) for item in value), f"{label} identities differ")
    result = [dict(item) for item in value]; _need(_identities_unique(result), f"{label} identities differ"); return result


def _closed_prefix(value: Any, expected: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _descriptor, raw = _bound(value, "closed prefix"); _need(_sha(raw) == expected, "closed prefix differs")
    prefix = json.loads(raw); required = {"schema_version", "kind", "ancestry", "identity_commitments", "local_decisions", "current_prefix_inventory", "stop_proof", "owned_exit_proof", "completed_logical_ordinals", "remaining_ordinals", "provider_calls_made"}
    _need(isinstance(prefix, dict) and set(prefix) == required and prefix.get("schema_version") == 1 and prefix.get("kind") == "grok_c97_closed_prefix_descriptor" and prefix.get("provider_calls_made") == 0, "closed prefix differs")
    for name in ("ancestry", "identity_commitments", "local_decisions", "current_prefix_inventory", "stop_proof", "owned_exit_proof"):
        _bound(prefix[name], f"closed prefix {name}")
    commitments = json.loads(_bound(prefix["identity_commitments"], "closed prefix identity commitments")[1])
    local = json.loads(_bound(prefix["local_decisions"], "closed prefix local decisions")[1])
    current = json.loads(_bound(prefix["current_prefix_inventory"], "closed prefix current inventory")[1])
    _need(isinstance(commitments, Mapping) and commitments.get("kind") == "grok_c97_identity_commitments" and commitments.get("provider_calls_made") == 0, "closed prefix commitments differ")
    _need(isinstance(local, Mapping) and local.get("kind") == "grok_c97_local_decisions" and local.get("provider_calls_made") == 0 and "native_identities" not in local, "closed prefix local decisions differ")
    _need(isinstance(current, Mapping) and current.get("kind") == "grok_c97_current_prefix_inventory" and current.get("provider_calls_made") == 0 and isinstance(current.get("terminals"), list) and isinstance(current.get("replays"), list), "closed prefix inventory differs")
    committed = _identities(commitments.get("native_identities"), "closed prefix commitments")
    _need(len(committed) == 277, "closed prefix commitment count differs")
    current_identities = _identities(current.get("native_identities"), "closed prefix inventory")
    ordinals: list[int] = []; terminal_identities: list[dict[str, Any]] = []
    for item in current["terminals"]:
        _need(isinstance(item, Mapping) and set(item) == {"ordinal", "terminal", "native_identity"} and type(item["ordinal"]) is int, "closed prefix terminal differs")
        _terminal, terminal_raw = _bound(item["terminal"], "closed prefix terminal")
        actual = json.loads(terminal_raw); identity = item["native_identity"]
        _need(isinstance(actual, Mapping) and actual.get("ordinal") == item["ordinal"] and actual.get("native_identity") == identity and isinstance(identity, Mapping), "closed prefix terminal identity differs")
        ordinals.append(item["ordinal"]); terminal_identities.append(dict(identity))
    replay_ordinals: list[int] = []
    for item in current["replays"]:
        _need(isinstance(item, Mapping) and set(item) == {"ordinals", "receipt"} and isinstance(item["ordinals"], list) and all(type(ordinal) is int for ordinal in item["ordinals"]), "closed prefix replay differs")
        _receipt, receipt_raw = _bound(item["receipt"], "closed prefix replay receipt"); receipt = json.loads(receipt_raw)
        terminal_rows, receipt_identities = receipt.get("terminals") if isinstance(receipt, Mapping) else None, receipt.get("native_identities") if isinstance(receipt, Mapping) else None
        _need(isinstance(receipt, Mapping) and receipt.get("ordinals") == item["ordinals"] and isinstance(terminal_rows, list) and [row.get("ordinal") for row in terminal_rows if isinstance(row, Mapping)] == item["ordinals"] and isinstance(receipt_identities, list) and [row.get("native_identity") for row in terminal_rows if isinstance(row, Mapping)] == receipt_identities, "closed prefix replay receipt differs")
        replay_ordinals.extend(item["ordinals"])
    completed, remaining = prefix["completed_logical_ordinals"], prefix["remaining_ordinals"]
    _need(isinstance(completed, list) and isinstance(remaining, list) and completed + remaining == LOGICAL_ORDINALS and ordinals == current.get("completed_logical_ordinals") and ordinals == replay_ordinals and current_identities == terminal_identities and set(ordinals) <= set(completed) and _identities_unique([*committed, *current_identities]), "closed prefix boundary differs")
    return prefix, [*committed, *current_identities]


def _batch(value: Any, expected: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _descriptor, raw = _bound(value, "frozen batch"); _need(_sha(raw) == expected, "frozen batch differs")
    batch = json.loads(raw); required = {"schema_version", "kind", "parent", "ordinals", "requests", "provider_calls_made"}
    _need(isinstance(batch, dict) and set(batch) == required and batch.get("schema_version") == 1 and batch.get("kind") == "grok_c97_frozen_batch" and batch.get("provider_calls_made") == 0, "frozen batch differs")
    parent_binding = batch["parent"]
    _need(isinstance(parent_binding, Mapping) and set(parent_binding) == {"source", "epoch_root", "epoch_sha256", "plan_root"} and isinstance(parent_binding.get("epoch_root"), str) and isinstance(parent_binding.get("epoch_sha256"), str) and isinstance(parent_binding.get("plan_root"), str), "frozen batch parent differs")
    with _BATCH_VALIDATION_LOCK:
        parent_source, _parent_raw = _bound(parent_binding["source"], "frozen batch parent source")
        parent = _load(Path(parent_source["path"]), parent_source["sha256"], "frozen batch parent")
        epoch, _epoch_raw = parent._load_epoch(Path(parent_binding["epoch_root"]), parent_binding["epoch_sha256"])
        plan_root = Path(parent_binding["plan_root"]); _need(epoch.get("plan_root") == str(plan_root), "frozen batch plan root differs")
        plan, _plan_raw = parent._plan(plan_root, epoch["plan_sha256"]); requests, passes = parent._request_index(plan), parent._pass_index(plan)
        rows = batch["requests"]; _need(isinstance(rows, list) and 1 <= len(rows) <= WAVE_CAP and batch.get("ordinals") == [item.get("ordinal") for item in rows], "frozen batch geometry differs")
        for item in rows:
            _need(isinstance(item, Mapping) and set(item) == {"ordinal", "pass_id", "prompt", "prompt_sha256", "schema", "schema_sha256", "question_ids", "source"} and type(item["ordinal"]) is int and isinstance(item["prompt"], str) and _sha(item["prompt"].encode()) == item["prompt_sha256"] and isinstance(item["question_ids"], list) and isinstance(item["source"], Mapping), "frozen batch request differs")
            original = requests.get(item["ordinal"]); _need(isinstance(original, Mapping) and item["pass_id"] == original.get("pass_id"), "frozen batch ordinal differs")
            prompt, schema_path, question_ids = parent._request_payload(plan_root, original); source = parent._source_for_pass(plan_root, passes[item["pass_id"]])
            schema, schema_raw = _bound(item["schema"], "frozen batch schema")
            _need(prompt == item["prompt"] and schema["path"] == str(schema_path) and schema["sha256"] == item["schema_sha256"] and isinstance(json.loads(schema_raw), Mapping) and question_ids == item["question_ids"] and source == item["source"], "frozen batch provenance differs")
    return batch, [dict(item) for item in rows]


def _manifest(root: Path, expected: str) -> tuple[dict[str, Any], bytes]:
    value, raw = _json(root / "grok-c97-contention-successor-manifest.json", "C97 successor manifest")
    required = {"schema_version", "kind", "controller_sha256", "candidate_loader", "candidate", "closed_prefix", "frozen_batch", "runtime", "new_route", "new_gate", "standing_packet", "queue", "barrier_packet", "barrier_helper_sha256", "barrier_binding", "pending_ordinals", "wave_cap", "provider_calls_made", "execution_authority"}
    runtime = value.get("runtime")
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1 and value.get("kind") == "grok_c97_contention_successor" and value.get("controller_sha256") == _sha(Path(__file__).read_bytes()) and value.get("candidate_loader", {}).get("sha256") == LOADER_SHA256 and value.get("candidate", {}).get("manifest_sha256") == CANDIDATE_MANIFEST_SHA256 and isinstance(runtime, Mapping) and runtime.get("snapshot_loader", {}).get("sha256") == SNAPSHOT_HELPERS_SHA256 and runtime.get("snapshot_loader", {}).get("path") == str(SNAPSHOT) and runtime.get("epoch_sha256") == _sha(_canon(runtime.get("epoch"))) and value.get("barrier_helper_sha256") == "37451e3dfab9b6d6cf6f8282ff4d12f20ea18aac76397cd4e22b6558980c7024" and value.get("wave_cap") == WAVE_CAP and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False and isinstance(value.get("pending_ordinals"), list), "C97 successor manifest differs")
    return value, raw


def prepare_contention_successor(*, continuation_root: Path, bindings: Mapping[str, Any]) -> dict[str, Any]:
    """Create an inert manifest; activation and contact are separate operations."""
    root = Path(continuation_root).resolve(); _need(not root.exists() or (root.is_dir() and not any(root.iterdir())), "C97 successor root is not fresh")
    required = {"candidate_loader", "candidate", "closed_prefix", "frozen_batch", "runtime", "new_route", "new_gate", "standing_packet", "queue", "barrier_packet", "barrier_helper_sha256", "barrier_binding"}
    _need(set(bindings) == required, "C97 successor bindings differ")
    for name in required - {"candidate", "barrier_binding", "runtime", "queue", "barrier_helper_sha256"}: _bound(bindings[name], name)
    _need(bindings["barrier_helper_sha256"] == "37451e3dfab9b6d6cf6f8282ff4d12f20ea18aac76397cd4e22b6558980c7024", "C97 barrier helper differs")
    _need(isinstance(bindings["queue"], Mapping) and set(bindings["queue"]) == {"path", "root_hash", "path_sha256"} and isinstance(bindings["queue"].get("path"), str) and isinstance(bindings["queue"].get("root_hash"), str) and bindings["queue"].get("path_sha256") == _sha(str(Path(bindings["queue"]["path"]).resolve()).encode()), "C97 queue binding differs")
    runtime = bindings["runtime"]; _need(isinstance(runtime, Mapping) and set(runtime) == {"snapshot_loader", "snapshot_manifest", "epoch", "epoch_sha256"} and isinstance(runtime.get("epoch"), Mapping) and runtime.get("epoch_sha256") == _sha(_canon(runtime["epoch"])), "C97 runtime binding differs")
    loader, _loader_raw = _bound(runtime["snapshot_loader"], "runtime snapshot loader"); _need(loader["path"] == str(SNAPSHOT) and loader["sha256"] == SNAPSHOT_HELPERS_SHA256, "C97 runtime loader differs")
    _bound(runtime["snapshot_manifest"], "runtime snapshot manifest")
    loader = _load(Path(bindings["candidate_loader"]["path"]), bindings["candidate_loader"]["sha256"], "C97 candidate loader")
    _need(hasattr(loader, "verify_candidate") and isinstance(bindings["candidate"], Mapping), "C97 candidate loader differs")
    loader.verify_candidate(Path(bindings["candidate"]["root"]), bindings["candidate"]["manifest_sha256"])
    prefix, _identities = _closed_prefix(bindings["closed_prefix"], bindings["closed_prefix"]["sha256"]); batch, _rows = _batch(bindings["frozen_batch"], bindings["frozen_batch"]["sha256"])
    _need(batch["ordinals"] == prefix["remaining_ordinals"][:len(batch["ordinals"])], "C97 frozen batch order differs")
    value = {"schema_version": 1, "kind": "grok_c97_contention_successor", "controller_sha256": _sha(Path(__file__).read_bytes()), **dict(bindings), "pending_ordinals": list(prefix["remaining_ordinals"]), "wave_cap": WAVE_CAP, "provider_calls_made": 0, "execution_authority": False}
    _new(root / "grok-c97-contention-successor-manifest.json", value); return value


def _activation(path: Path, expected: str, manifest: Mapping[str, Any], manifest_raw: bytes) -> dict[str, Any]:
    value, raw = _json(path, "C97 activation packet"); required = {"schema_version", "kind", "controller_sha256", "manifest_sha256", "rotation_result", "bootstrap", "supervision", "barrier_helper", "authority", "provider_calls_made"}
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1 and value.get("kind") == "grok_c97_activation_packet" and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("manifest_sha256") == _sha(manifest_raw) and value.get("provider_calls_made") == 0, "C97 activation packet differs")
    for name in ("rotation_result", "bootstrap", "supervision", "barrier_helper", "authority"):
        descriptor, _raw = _bound(value[name], f"activation {name}")
        if name == "barrier_helper": _need(descriptor["sha256"] == manifest["barrier_helper_sha256"], "activation barrier helper differs")
    return value


def _authority(activation: Mapping[str, Any], manifest: Mapping[str, Any], manifest_raw: bytes) -> dict[str, Any]:
    _descriptor, raw = _bound(activation["authority"], "C97 authority")
    value = json.loads(raw); required = {"schema_version", "kind", "decision", "controller_sha256", "manifest_sha256", "route_sha256", "gate_sha256", "standing_packet_sha256", "reviewed_at", "expires_at", "provider_calls_made", "automatic_resend_authorized"}
    route, route_raw = _json(Path(manifest["new_route"]["path"]), "C97 new route")
    gate, gate_raw = _json(Path(manifest["new_gate"]["path"]), "C97 new gate")
    standing, standing_raw = _json(Path(manifest["standing_packet"]["path"]), "C97 standing packet")
    try:
        reviewed = datetime.fromisoformat(str(value.get("reviewed_at")).replace("Z", "+00:00")); expires = datetime.fromisoformat(str(value.get("expires_at")).replace("Z", "+00:00"))
    except ValueError as error: raise ValueError("C97 authority time differs") from error
    now = datetime.now(timezone.utc)
    _need(isinstance(value, Mapping) and set(value) == required and value.get("schema_version") == 1 and value.get("kind") == "grok_c97_wave_authority" and value.get("decision") == "approved_grok_c97_one_frozen_wave" and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("manifest_sha256") == _sha(manifest_raw) and value.get("route_sha256") == _sha(route_raw) == manifest["new_route"]["sha256"] and value.get("gate_sha256") == _sha(gate_raw) == manifest["new_gate"]["sha256"] and value.get("standing_packet_sha256") == _sha(standing_raw) == manifest["standing_packet"]["sha256"] and gate.get("state") == "healthy" and standing.get("allowance_state") == "available" and standing.get("zero_charge_only") is True and standing.get("automatic_resend") is False and value.get("provider_calls_made") == 0 and value.get("automatic_resend_authorized") is False and reviewed.tzinfo is not None and expires.tzinfo is not None and reviewed <= now < expires and expires - now >= timedelta(seconds=300) and isinstance(route.get("name"), str), "C97 authority differs")
    return value


def _state(root: Path, expected: str) -> dict[str, Any]:
    manifest, raw = _manifest(root, expected); loader = _load(Path(manifest["candidate_loader"]["path"]), manifest["candidate_loader"]["sha256"], "C97 candidate loader")
    candidate, candidate_record = loader.load_candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
    prefix, identities = _closed_prefix(manifest["closed_prefix"], manifest["closed_prefix"]["sha256"]); batch, rows = _batch(manifest["frozen_batch"], manifest["frozen_batch"]["sha256"])
    for name in ("new_route", "new_gate", "standing_packet", "barrier_packet"): _bound(manifest[name], name)
    _need(isinstance(manifest["queue"], Mapping) and set(manifest["queue"]) == {"path", "root_hash", "path_sha256"} and manifest["queue"].get("path_sha256") == _sha(str(Path(manifest["queue"]["path"]).resolve()).encode()), "C97 queue binding differs")
    snapshot = _load(Path(manifest["runtime"]["snapshot_loader"]["path"]), manifest["runtime"]["snapshot_loader"]["sha256"], "C97 runtime snapshot")
    runtime = snapshot.load_runtime_from_epoch(dict(manifest["runtime"]["epoch"]), snapshot_manifest_path=Path(manifest["runtime"]["snapshot_manifest"]["path"]), expected_snapshot_manifest_sha256=manifest["runtime"]["snapshot_manifest"]["sha256"])
    adapter = importlib.import_module(candidate.__package__ + ".adapters.grok_exec")
    _need(manifest["pending_ordinals"] == prefix["remaining_ordinals"] and manifest["pending_ordinals"][:len(batch["ordinals"])] == batch["ordinals"], "C97 pending batch differs")
    return {"manifest": manifest, "manifest_raw": raw, "candidate": candidate, "candidate_record": candidate_record, "prefix": prefix, "identities": identities, "rows": rows, "runtime": runtime, "adapter": adapter}


def _attempt(root: Path, ordinal: int) -> Path: return root / "attempts" / f"request-{ordinal:04d}" / "terminal.json"
def _start(root: Path, ordinal: int) -> Path: return root / "attempts" / f"request-{ordinal:04d}" / "attempt-start.json"
def _replay(root: Path, ordinal: int, size: int) -> Path: return root / "replays" / f"wave-{ordinal:04d}-slots-{size:02d}.json"


def _contact_state(outcome: Any, admitted: bool) -> str:
    state = outcome.get("state") if isinstance(outcome, Mapping) else None
    if state in {"completed", "definitely_not_contacted", "ambiguous"}:
        return state
    return "ambiguous" if admitted else "definitely_not_contacted"


def _semantic(*, candidate: Any, adapter: Any, broker: Any, runtime: Any, row: Mapping[str, Any], terminal: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], Mapping[str, Any]]:
    result = terminal.get("candidate_result"); _need(terminal.get("state") == "completed" and isinstance(result, Mapping), "C97 terminal differs")
    descriptor = result.get("native_envelope_artifact"); _need(isinstance(descriptor, Mapping), "C97 envelope differs")
    envelope = broker.read_grok_native_envelope(dict(descriptor)); _need(_sha(envelope) == descriptor.get("sha256") and len(envelope) == descriptor.get("byte_length"), "C97 envelope differs")
    route, session = terminal.get("review_route"), terminal.get("session_id"); _need(isinstance(route, Mapping) and isinstance(session, str) and _sha(_canon(dict(route))) == terminal.get("route_sha256"), "C97 route differs")
    schema = json.loads(Path(row["schema"]["path"]).read_bytes())
    parsed = broker._parse_grok_exec_envelope(_canon({"control": {"version": 1, "state": "completed"}, "result": dict(result)}), {**dict(route), "output_schema": schema, "nonvisual_max_turns": 1}, {"prompt": row["prompt"]}, expected_session_id=session)
    output, identity, _usage = adapter._parse_grok_envelope(envelope, model=route["model"], reported_model=route["reported_model"], session_id=session, schema=schema, max_turns=1, exact_turns=True)
    identity = dict(identity); source = row["source"]
    normalized = runtime.runner._normalize_batch(output, expected_ids=row["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=f"c97/{row['ordinal']}", artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
    _need(parsed.state == "completed" and parsed.result == result and identity == terminal.get("native_identity") and output == result.get("output") and normalized == terminal.get("verdicts"), "C97 semantic replay differs")
    return identity, normalized, descriptor


def dispatch_contention_wave(*, continuation_root: Path, expected_manifest_sha256: str, activation_packet_path: Path, expected_activation_packet_sha256: str) -> dict[str, Any]:
    """Run one pre-frozen C97 wave of one through ten slots after activation proof."""
    root = Path(continuation_root).resolve(); state = _state(root, expected_manifest_sha256); manifest, raw = state["manifest"], state["manifest_raw"]
    activation = _activation(Path(activation_packet_path), expected_activation_packet_sha256, manifest, raw)
    barrier = _load(Path(activation["barrier_helper"]["path"]), activation["barrier_helper"]["sha256"], "C97 barrier helper")
    binding = barrier.BarrierBinding.parse(dict(manifest["barrier_binding"])); identities = list(state["identities"]); lock, lease_lock, stop = threading.Lock(), threading.Lock(), threading.Event()
    with barrier.acquire(binding, "c97-controller", 30) as lease:
        def held() -> None:
            with lease_lock: lease.assert_held(binding, "c97-controller")
        held()
        runtime, candidate, adapter, rows = state["runtime"], state["candidate"], state["adapter"], state["rows"]
        _need(not (root / "wave-start.json").exists() and not (root / "completed.json").exists() and not (root / "replays").exists(), "C97 wave already started")
        _need(not any(_start(root, row["ordinal"]).exists() or _attempt(root, row["ordinal"]).exists() for row in rows), "C97 attempt already started")
        _new(root / "wave-start.json", {"schema_version": 1, "kind": "grok_c97_wave_start", "manifest_sha256": _sha(raw), "ordinals": [row["ordinal"] for row in rows], "activation_packet_sha256": expected_activation_packet_sha256, "provider_calls_made": 0})
        for row in rows:
            _new(_start(root, row["ordinal"]), {"schema_version": 1, "ordinal": row["ordinal"], "manifest_sha256": _sha(raw), "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"], "question_ids": row["question_ids"], "provider_calls_made": 0})
        brokers = {row["ordinal"]: candidate.Broker(Path(manifest["queue"]["path"])) for row in rows}
        outcomes: dict[int, dict[str, Any]] = {}
        def cell(row: Mapping[str, Any]) -> None:
            ordinal, broker, admitted, outcome, result, identity, session = row["ordinal"], brokers[row["ordinal"]], False, None, None, None, None
            try:
                def before_contact() -> None:
                    nonlocal admitted
                    held()
                    _need(not stop.is_set() and _sha(Path(__file__).read_bytes()) == manifest["controller_sha256"], "C97 controller changed before contact")
                    _need((root / "grok-c97-contention-successor-manifest.json").read_bytes() == raw, "C97 manifest changed before contact")
                    for name in ("new_route", "new_gate", "standing_packet", "barrier_packet"): _bound(manifest[name], f"C97 {name}")
                    _fresh_batch, fresh_rows = _batch(manifest["frozen_batch"], manifest["frozen_batch"]["sha256"])
                    _need(next((item for item in fresh_rows if item["ordinal"] == ordinal), None) == row, "C97 frozen request changed before contact")
                    _authority(activation, manifest, raw)
                    runtime.verify(); admitted = True
                session = str(uuid.uuid4()); schema = json.loads(Path(row["schema"]["path"]).read_bytes())
                route, _route_raw = _json(Path(manifest["new_route"]["path"]), "C97 new route")
                outcome = broker.run_grok_native_request(route["name"], {"prompt": row["prompt"]}, output_schema=schema, nonvisual_max_turns=1, session_id=session, expected_route_sha256=manifest["new_route"]["sha256"], before_contact=before_contact)
                result = outcome.get("result") if isinstance(outcome, Mapping) else None
                if not (isinstance(outcome, Mapping) and outcome.get("state") == "completed" and isinstance(result, Mapping) and admitted): raise ValueError("C97 outcome stopped")
                record = result.get("runtime"); _need(isinstance(record, Mapping), "C97 candidate runtime differs")
                identity = {key: record.get(key) for key in ("request_id_hash", "session_id_hash", "observed_turns")}
                _need(identity.get("observed_turns") == 1, "C97 identity differs")
                source = row["source"]; normalized = runtime.runner._normalize_batch(result.get("output"), expected_ids=row["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=f"c97/{ordinal}", artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
                with lock:
                    _need(_identities_unique([*identities, identity]), "C97 native identity collision"); identities.append(identity)
                terminal = {"schema_version": 1, "ordinal": ordinal, "state": "completed", "session_id": session, "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "route_sha256": manifest["new_route"]["sha256"], "review_route": route, "broker_outcome": outcome, "candidate_result": dict(result), "native_identity": identity, "verdicts": normalized}
            except Exception as error:  # noqa: BLE001 - each native outcome needs a no-resend terminal
                stop.set(); terminal = {"schema_version": 1, "ordinal": ordinal, "state": "definitely_not_contacted" if _contact_state(outcome, admitted) == "definitely_not_contacted" else "ambiguous", "session_id": session, "contact_admitted": admitted, "broker_contact_state": outcome.get("state") if isinstance(outcome, Mapping) else None, "broker_outcome": outcome, "error_type": type(error).__name__}
                if isinstance(result, Mapping): terminal["candidate_result"] = dict(result)
                if isinstance(identity, Mapping): terminal["native_identity"] = dict(identity)
            _new(_attempt(root, ordinal), terminal)
            with lock: outcomes[ordinal] = terminal
        with ThreadPoolExecutor(max_workers=len(rows)) as executor: list(executor.map(cell, rows))
        held()
        completed = [outcomes[row["ordinal"]] for row in rows if outcomes[row["ordinal"]].get("state") == "completed"]
        if len(completed) != len(rows):
            known_completed = sum(isinstance(item.get("broker_outcome"), Mapping) and item["broker_outcome"].get("state") == "completed" for item in outcomes.values())
            ambiguous = sorted(item["ordinal"] for item in outcomes.values() if _contact_state(item.get("broker_outcome"), bool(item.get("contact_admitted"))) == "ambiguous")
            return {"state": "stopped_no_retry", "provider_calls_made": known_completed if not ambiguous else None, "completed_provider_outcomes": known_completed, "ambiguous_contact_ordinals": ambiguous, "completed_ordinals": [item["ordinal"] for item in completed]}
        replayed = []
        for row, terminal in zip(rows, completed, strict=True):
            held(); identity, _normalized, descriptor = _semantic(candidate=candidate, adapter=adapter, broker=brokers[row["ordinal"]], runtime=runtime, row=row, terminal=terminal)
            replayed.append({"ordinal": row["ordinal"], "terminal_sha256": _sha(_attempt(root, row["ordinal"]).read_bytes()), "native_envelope_sha256": descriptor["sha256"], "native_identity": identity})
        runtime.verify(); held()
        replay_path = _replay(root, rows[0]["ordinal"], len(rows)); _new(replay_path, {"schema_version": 1, "kind": "grok_c97_replay", "manifest_sha256": _sha(raw), "wave_size": len(rows), "native_identity_count": len(replayed), "ordinals": [row["ordinal"] for row in rows], "terminals": replayed, "provider_calls_made": 0})
        _new(root / "completed.json", {"schema_version": 1, "kind": "grok_c97_completed_wave", "manifest_sha256": _sha(raw), "replay_sha256": _sha(replay_path.read_bytes()), "provider_calls_made": len(rows)})
    return {"state": "completed_replayed", "provider_calls_made": len(rows), "completed_ordinals": [row["ordinal"] for row in rows]}
