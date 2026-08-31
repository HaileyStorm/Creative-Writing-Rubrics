#!/usr/bin/env python3
"""One fresh, auditable replacement for V5's terminal cycle-two control."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STUDY_ID = "cwr-guided-revision-gain-v2-live-exec-v6-single-replacement"
V5_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v5" / "executor.py"
V5_SHA256 = "42ce0b571c638e9b7883af0706fdff023f6c8805c34a48220d366237dce862a9"
V5_ROOT = Path(r"C:\Users\Haile\Documents\cwr-revision-gain-v5-live-1e97a19-20260831a")
V4_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v4" / "executor.py"
V4_SHA256 = "1f962cd5cb731968e6baef37932c6aebb7c5667c99ea57a59cc7dc52f9f88250"
V4_ROOT = Path(r"C:\Users\Haile\Documents\cwr-revision-gain-v4-reconcile-1f57ad1-20260830a")
V4_INVENTORY_SHA256 = "d184f015ef98a59df777eaafbf62ad6f38ad51911654480d7077dd9af45a9773"
EVENT_ID = "revision-v2-c2-hanna-178-grok-4.6-generic_no_feedback"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
TERMINAL_FILES = frozenset({"adapter-control.json", "adapter-schema-binding.json", "adapter-stdout-binding.json", "adapter-stdout.raw", "governed-route-proof.json", "launch-intent.json", "live-admission.json", "outbound-payload.json", "payload.json", "prepared-cell.json", "terminal-outcome.json"})
TERMINAL_HASHES = {
    "adapter-control.json": "71cc111da620a75b01cd54dd13705ade7823ec75877000c4fe3ec2fc04dc5400",
    "adapter-schema-binding.json": "394d412340de6b2c25c2528fd2a81b88950b30f20fb89aaaf680b43373833a14",
    "adapter-stdout-binding.json": "e53ae5ceb617c134bb3e478cc3bf770cf643989a1eaee790cdf43a1490102851",
    "adapter-stdout.raw": "452f7d15d12301b86445a252edc397f67f87fef9434580f5c5b88e38979494a0",
    "governed-route-proof.json": "2414c2140e92c52e1759a4afefb98d6c29fac32888a70176d7e32607f0b1410a",
    "launch-intent.json": "77284463f63f83ade218572009252f3560b1a38e0bb51f58dc20ab2a0fddd65d",
    "live-admission.json": "fe9561f64ed3f22f4cc378b52e5e07dbc33f5a16174a5841f6e87e294d6fd73e",
    "outbound-payload.json": "9e6857534039d52e0be7f2f2185efb3cc52381177495a88e2f28259a24af0ab6",
    "payload.json": "203d16855646ba36db4def6a3937266f849fee66176a7bb8d1f7fbe387efdb2e",
    "prepared-cell.json": "d389f3876ec78ac77a32131a368f3a5252dcf90688829dfc5dff1e7e311258a3",
    "terminal-outcome.json": "23e631ec1c248f259b009b447bb300d7cc22eabc8c6c479904c7e6ae931b07a5",
}
PRELAUNCH_FILES = frozenset({"payload.json", "prepared-cell.json", "governed-route-proof.json", "outbound-payload.json", "adapter-schema-binding.json", "replacement-admission.json"})
SETTLED_FILES = PRELAUNCH_FILES | frozenset({"launch-intent.json", "launch-route-binding.json", "adapter-stdout.raw", "adapter-stdout-binding.json", "adapter-control.json", "replacement-authority.json"})
_SUBPROCESS_RUN = subprocess.run
_BASE_MODULE: Any | None = None


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain(path: Path) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError("V6 replacement path is reparsed")
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("V6 replacement artifact is not a plain file")
    with path.open("rb") as handle:
        raw = handle.read()
    if os.lstat(path).st_size != before.st_size:
        raise ValueError("V6 replacement artifact changed during read")
    return raw


def _json(path: Path, *, label: str) -> Any:
    raw = _plain(path)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"V6 {label} is not JSON") from error
    if canonical(value) + b"\n" != raw:
        raise ValueError(f"V6 {label} is not canonical")
    return value


def _directory(directory: Path, *, expected: set[str], label: str) -> None:
    info = os.lstat(directory)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0) & 0x400)
            or {path.name for path in directory.iterdir()} != expected):
        raise ValueError(f"V6 {label} inventory drifted")


def _replacement_inventory(root: Path, *, state: str) -> None:
    expected = PRELAUNCH_FILES if state == "prelaunch" else SETTLED_FILES
    _directory(root, expected=set(expected), label=f"replacement {state}")
    for name in expected:
        _plain(root / name)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")


def _write_raw(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _commit(root: Path, path: Path) -> dict[str, Any]:
    raw = _plain(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": _sha(raw)}


def _base():
    global _BASE_MODULE
    if _BASE_MODULE is not None:
        return _BASE_MODULE
    if _sha(_plain(V5_PATH)) != V5_SHA256:
        raise ValueError("V6 pinned V5 executor drifted")
    spec = importlib.util.spec_from_file_location("_v5_for_v6_replacement", V5_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _BASE_MODULE = module
    return _BASE_MODULE


def _terminal_root() -> Path:
    return V5_ROOT / "live-cells" / "revision_generation" / EVENT_ID


def verify_terminal() -> dict[str, Any]:
    root = _terminal_root()
    if not root.is_dir() or {p.name for p in root.iterdir()} != TERMINAL_FILES:
        raise ValueError("V6 original terminal inventory drifted")
    for name, expected in TERMINAL_HASHES.items():
        if _sha(_plain(root / name)) != expected:
            raise ValueError("V6 original terminal artifact drifted")
    control = json.loads(_plain(root / "adapter-control.json"))
    detail = control.get("control", {}).get("detail", "") if isinstance(control, Mapping) else ""
    if (control.get("control", {}).get("state") != "ambiguous" or "max turns reached" not in detail
            or '"text": ""' not in detail or '"sessionId"' not in detail or '"requestId"' not in detail):
        raise ValueError("V6 original terminal control is not the pinned empty Grok outcome")
    outcome = json.loads(_plain(root / "terminal-outcome.json"))
    if outcome != {"fresh_output_root_required": False, "no_resend": True, "state": "terminal_postlaunch_reconcile_required"}:
        raise ValueError("V6 original terminal outcome drifted")
    for path in V5_ROOT.rglob("*"):
        relative = path.relative_to(V5_ROOT)
        if EVENT_ID in relative.parts and root not in path.parents and path.resolve() != root.resolve():
            raise ValueError("V6 original event has an unauthenticated V5 artifact outside its terminal root")
        if path.name == f"{EVENT_ID}.md":
            raise ValueError("V6 original event has an unauthenticated V5 descendant")
    return {"root": str(root), "inventory": {name: _commit(root, root / name) for name in sorted(TERMINAL_FILES)}, "no_resend": True}


def contract() -> dict[str, Any]:
    expected = {"format_version": 1, "study_id": STUDY_ID, "base_commit": "1e97a192e2be50f02917604f7ae8ae247aaf5e06", "base_executor_sha256": V5_SHA256, "v5_root": str(V5_ROOT), "v4_import": {"source_run_root": str(V4_ROOT), "executor_sha256": V4_SHA256, "inventory_sha256": V4_INVENTORY_SHA256}, "original_event_id": EVENT_ID, "authorized_acknowledgement_sha256": ACK, "dispatch": "one_fresh_replacement_only_after_terminal_verification", "provider_calls_made_by_prepare": 0}
    raw = _plain(HERE / "study-contract.json")
    if canonical(expected) + b"\n" != raw:
        raise ValueError("V6 study contract drifted")
    if _sha(_plain(V4_PATH)) != V4_SHA256:
        raise ValueError("V6 pinned V4 executor drifted")
    _base()._validate_v4_import_root()
    return expected


def _safe_root(root: Path) -> Path:
    root = Path(os.path.abspath(root))
    for immutable in (V5_ROOT, _terminal_root()):
        try:
            if os.path.commonpath((os.path.normcase(str(root)), os.path.normcase(str(immutable)))) in {os.path.normcase(str(root)), os.path.normcase(str(immutable))}:
                raise ValueError("V6 replacement root overlaps immutable V5 evidence")
        except ValueError as error:
            if "overlaps" in str(error):
                raise
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        if not current.exists():
            break
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("V6 replacement root has unsafe ancestry")
    return root


def _disjoint(left: Path, right: Path, *, label: str) -> None:
    left, right = Path(os.path.abspath(left)), Path(os.path.abspath(right))
    try:
        common = os.path.commonpath((os.path.normcase(str(left)), os.path.normcase(str(right))))
    except ValueError as error:
        raise ValueError(f"V6 {label} roots are on different drives") from error
    if common in {os.path.normcase(str(left)), os.path.normcase(str(right))}:
        raise ValueError(f"V6 {label} roots overlap")


def _safe_target_root(run_root: Path, target_root: Path, source_root: Path) -> Path:
    target_root = _safe_root(Path(target_root))
    for other, label in ((run_root, "target/work"), (source_root, "target/source"), (V5_ROOT, "target/V5")):
        _disjoint(target_root, Path(other), label=label)
    return target_root


def _validate_run_inventory(run_root: Path, *, adopted: bool, replacement_state: str) -> None:
    expected = {"frozen-inputs.json", "frozen-cwr-question-payload.json", "imports", "carry-forward", "replacement-cells"}
    if adopted:
        expected |= {"adoptions", "descendants"}
    _directory(run_root, expected=expected, label="replacement run-root")
    for name in ("imports", "carry-forward", "replacement-cells"):
        info = os.lstat(run_root / name)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError("V6 replacement run-root has an unsafe directory")
    _plain(run_root / "frozen-inputs.json")
    _plain(run_root / "frozen-cwr-question-payload.json")
    replacements = run_root / "replacement-cells"
    _directory(replacements, expected={_replacement_id(run_root)}, label="replacement cell")
    _replacement_inventory(replacements / _replacement_id(run_root), state=replacement_state)
    if adopted:
        for directory, filename in (("adoptions", f"{EVENT_ID}.json"), ("descendants", f"{EVENT_ID}.md")):
            root = run_root / directory
            _directory(root, expected={filename}, label="replacement adopted")
            _plain(root / filename)


def _replacement_id(run_root: Path) -> str:
    return "replacement-" + _sha(canonical({"study_id": STUDY_ID, "run_root": str(Path(run_root).resolve()), "original_event_id": EVENT_ID}))[:24]


def _prior_native_ids() -> set[str]:
    ids: set[str] = set()
    for path in V5_ROOT.rglob("verified-receipt.json"):
        value = json.loads(_plain(path))
        native = value.get("native_receipt") if isinstance(value, Mapping) else None
        if isinstance(native, Mapping):
            for field in ("provider_request_id", "session_id"):
                identity = native.get(field)
                if isinstance(identity, str) and identity:
                    ids.add(identity)
    if len(ids) < 14:
        raise ValueError("V6 cannot establish all seven predecessor native identities")
    return ids


def _prepared_admission(base: Any, run_root: Path, root: Path, *, state: str) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    _replacement_inventory(root, state=state)
    admission = _json(root / "replacement-admission.json", label="replacement admission")
    prepared = _json(root / "prepared-cell.json", label="prepared cell")
    if not isinstance(admission, Mapping) or not isinstance(prepared, Mapping):
        raise ValueError("V6 replacement admission is malformed")
    schema = base._decorate_adapter_schema(base._REVISION_RESPONSE_SCHEMA)
    expected_schema = {"format_version": 1, "study_id": STUDY_ID, "kind": "adapter_schema_decoration", "underlying_pilot_response_schema": base._REVISION_RESPONSE_SCHEMA, "underlying_pilot_response_schema_sha256": _sha(canonical(base._REVISION_RESPONSE_SCHEMA)), "adapter_output_schema": schema, "adapter_output_schema_sha256": _sha(canonical(schema))}
    if (admission.get("prepared") != prepared or prepared.get("event_id") != EVENT_ID
            or prepared.get("work_root") != str(run_root.resolve()) or prepared.get("provider_model") != "grok-4.6"
            or prepared.get("reasoning") != "high" or prepared.get("tools_enabled") is not False
            or _plain(root / "payload.json") != _plain(_terminal_root() / "payload.json")
            or _json(root / "adapter-schema-binding.json", label="adapter schema") != expected_schema):
        raise ValueError("V6 replacement prepared payload or settings drifted")
    outbound_raw = _plain(root / "outbound-payload.json")
    outbound = _json(root / "outbound-payload.json", label="outbound payload")
    proof = _json(root / "governed-route-proof.json", label="governed route proof")
    expected_identity = {"study_id": STUDY_ID, "successor_event_id": _replacement_id(run_root), "logical_sample_id": _sha(canonical({"original_event_id": EVENT_ID, "original_payload_sha256": _sha(_plain(root / "payload.json"))}))}
    expected_admission = {"format_version": 1, "study_id": STUDY_ID, "kind": "single_replacement_prepared", "replacement_event_id": _replacement_id(run_root), "original_event_id": EVENT_ID, "original_terminal": verify_terminal(), "prepared": prepared, "route_evidence": _commit(run_root, root / "governed-route-proof.json"), "adapter_schema": _commit(run_root, root / "adapter-schema-binding.json"), "original_payload": _commit(V5_ROOT, _terminal_root() / "payload.json"), "original_outbound_payload": _commit(V5_ROOT, _terminal_root() / "outbound-payload.json"), "replacement_payload": _commit(run_root, root / "payload.json"), "outbound_payload": _commit(run_root, root / "outbound-payload.json"), "provider_calls_made": 0, "no_resend": True}
    if (not isinstance(outbound, Mapping) or outbound.get("identity") != expected_identity
            or canonical(outbound.get("pilot_payload")) + b"\n" != _plain(root / "payload.json")
            or admission != expected_admission or not isinstance(proof, Mapping)):
        raise ValueError("V6 replacement admission or outbound identity drifted")
    return dict(prepared), outbound_raw, dict(outbound), dict(proof)


def _pilot(base: Any):
    """Permit copied V5 authorities only after byte-for-byte source replay."""
    pilot = base._imported_sol_reader(base._pilot())
    reader = pilot._read_verified_receipt
    def carry_reader(path: Path, *, expected_event_id: str, expected_phase: str) -> dict[str, Any]:
        path = Path(path)
        if path.name == "replacement-authority.json":
            root = path.parent
            run_root = root.parent.parent
            _safe_root(run_root)
            _replacement_inventory(root, state="settled")
            prepared, outbound, _outbound, _proof = _prepared_admission(base, run_root, root, state="settled")
            value = _json(path, label="replacement authority")
            launch_raw = _plain(root / "launch-route-binding.json")
            launch = _json(root / "launch-route-binding.json", label="launch route binding")
            expected_launch = {"format_version": 1, "study_id": STUDY_ID, "kind": "launch_time_route_identity", "prepared": _commit(run_root, root / "prepared-cell.json"), "admission_sha256": _sha(_plain(root / "replacement-admission.json")), "route_evidence": _commit(run_root, root / "governed-route-proof.json"), "adapter_schema": _commit(run_root, root / "adapter-schema-binding.json"), "route": launch.get("route")}
            route = launch.get("route")
            if (launch != expected_launch or not isinstance(route, Mapping)
                    or set(route) != {"model", "reported_model", "reasoning_effort", "grok_command_identity", "subscription_receipt_hash"}
                    or route["model"] != "grok-4.6" or route["reported_model"] != "grok-4.6-build" or route["reasoning_effort"] != "high"):
                raise ValueError("V6 launch-time route identity drifted")
            stdout = _plain(root / "adapter-stdout.raw")
            control = base._adapter_envelope(stdout)
            if (canonical(control) + b"\n" != _plain(root / "adapter-control.json")
                    or _json(root / "adapter-stdout-binding.json", label="adapter stdout binding") != {"format_version": 1, "study_id": STUDY_ID, "kind": "exact_raw_adapter_stdout", "raw_stdout": _commit(run_root, root / "adapter-stdout.raw"), "control": _commit(run_root, root / "adapter-control.json")}):
                raise ValueError("V6 replacement stdout/control replay drifted")
            actual = base._receipt_from_control(pilot=pilot, root=root, prepared=prepared, route=route, control_raw=stdout, payload_override=outbound)
            expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "v6_wrapper_bound_native_replacement_authority", "original_event_id": EVENT_ID, "replacement_event_id": _replacement_id(run_root), "prepared": _commit(run_root, root / "prepared-cell.json"), "outbound_payload": _commit(run_root, root / "outbound-payload.json"), "launch_route": _commit(run_root, root / "launch-route-binding.json"), "actual_native_receipt": actual}
            if value != expected or expected_event_id != EVENT_ID or expected_phase != "revision_generation":
                raise ValueError("V6 replacement authority drifted")
            normalized = dict(actual)
            normalized["transmitted_payload_sha256"] = prepared["payload"]["sha256"]
            return pilot.validate_receipt(prepared_root=root, receipt=normalized, output_path=None)
        parts = path.parts
        if "carry-forward" not in parts:
            return reader(path, expected_event_id=expected_event_id, expected_phase=expected_phase)
        index = parts.index("carry-forward")
        suffix = parts[index + 1:]
        if len(suffix) != 3 or suffix[0] not in {"revision_generation", "cwr_feedback"} or suffix[2] != "verified-receipt.json":
            raise ValueError("V6 carry-forward receipt path is invalid")
        phase, event_id = suffix[0], suffix[1]
        if event_id != expected_event_id or phase != expected_phase:
            raise ValueError("V6 carry-forward receipt identity drifted")
        source = V5_ROOT / "live-cells" / phase / event_id / "verified-receipt.json"
        if _plain(path) != _plain(source):
            raise ValueError("V6 carry-forward receipt source drifted")
        return reader(source, expected_event_id=expected_event_id, expected_phase=expected_phase)
    pilot._read_verified_receipt = carry_reader
    return pilot


def _carry_records(base: Any, run_root: Path) -> list[dict[str, Any]]:
    """Copy the seven authenticated predecessors into a V6-local authority tree."""
    imports, _ = base.import_cycle_one(output_root=run_root)
    for event in base._pilot().revision_schedule():
        event_id = event["event_id"]
        if event_id == EVENT_ID or event["cycle"] != 2:
            continue
        source = V5_ROOT / "live-cells" / "revision_generation" / event_id
        target = run_root / "carry-forward" / "revision_generation" / event_id
        if target.exists():
            if {path.name for path in target.iterdir()} != {"prepared-cell.json", "payload.json", "launch-intent.json", "verified-receipt.json"}:
                raise ValueError("V6 carry-forward revision inventory drifted")
            for name in ("prepared-cell.json", "payload.json", "launch-intent.json", "verified-receipt.json"):
                if _plain(target / name) != _plain(source / name):
                    raise ValueError("V6 carry-forward revision source drifted")
        else:
            target.mkdir(parents=True)
            for name in ("prepared-cell.json", "payload.json", "launch-intent.json", "verified-receipt.json"):
                _write_raw(target / name, _plain(source / name))
        if event["guidance_arm"] == "cwr_guided":
            feedback_event = event["cwr_feedback_event_id"]
            feedback_source = V5_ROOT / "live-cells" / "cwr_feedback" / feedback_event
            feedback_target = run_root / "carry-forward" / "cwr_feedback" / feedback_event
            source_names = {artifact.name for artifact in feedback_source.iterdir()}
            if feedback_target.exists():
                if {artifact.name for artifact in feedback_target.iterdir()} != source_names:
                    raise ValueError("V6 carry-forward feedback inventory drifted")
                for name in source_names:
                    if _plain(feedback_target / name) != _plain(feedback_source / name):
                        raise ValueError("V6 carry-forward feedback source drifted")
            else:
                for artifact in feedback_source.iterdir():
                    _write_raw(feedback_target / artifact.name, _plain(artifact))
        descendant = V5_ROOT / "descendants" / f"{event_id}.md"
        carried_descendant = run_root / "carry-forward" / "descendants" / f"{event_id}.md"
        if carried_descendant.exists():
            if _plain(carried_descendant) != _plain(descendant):
                raise ValueError("V6 carry-forward descendant source drifted")
        else:
            _write_raw(carried_descendant, _plain(descendant))
    pilot = _pilot(base)
    records = list(imports)
    for event in pilot.revision_schedule():
        event_id = event["event_id"]
        if event_id == EVENT_ID or event["cycle"] != 2:
            continue
        source = pilot.contract()["sources"]["items"][event["source_item_id"]]
        target = run_root / "carry-forward" / "revision_generation" / event_id
        descendant = run_root / "carry-forward" / "descendants" / f"{event_id}.md"
        parent = next(row for row in records if row["event_id"] == event["parent_event_id"])
        feedback = None
        if event["guidance_arm"] == "cwr_guided":
            feedback_event = event["cwr_feedback_event_id"]
            feedback = {"event_id": feedback_event, "verified_receipt": _commit(run_root, run_root / "carry-forward" / "cwr_feedback" / feedback_event / "verified-receipt.json")}
        records.append({"event_id": event_id, "source": {"item_id": event["source_item_id"], "source.md": source["source.md"], "prompt.md": source["prompt.md"]}, "parent": {"event_id": event["parent_event_id"], "descendant": parent["descendant"]}, "descendant": _commit(run_root, descendant), "generator": {"model": "grok-4.6", "reasoning": "high", "tools_enabled": False}, "generator_receipt": _commit(run_root, target / "verified-receipt.json"), "cwr_feedback": feedback})
    if len(records) != 7:
        raise ValueError("V6 did not materialize exactly seven predecessor records")
    return records


def prepare_replacement(*, run_root: Path, source_root: Path, acknowledgement_sha256: str, queue_root: Path) -> dict[str, Any]:
    if acknowledgement_sha256 != ACK:
        raise ValueError("V6 acknowledgement is not authorized")
    verify_terminal()
    run_root = _safe_root(Path(run_root))
    source_root = _safe_root(Path(source_root))
    queue_root = _safe_root(Path(queue_root))
    for other, label in ((source_root, "work/source"), (queue_root, "work/queue"), (V5_ROOT, "work/V5")):
        _disjoint(run_root, other, label=label)
    if run_root.exists():
        raise ValueError("V6 replacement root must be fresh")
    base = _base()
    records = _carry_records(base, run_root)
    pilot = _pilot(base)
    replacement_id = _replacement_id(run_root)
    root = run_root / "replacement-cells" / replacement_id
    prepared = pilot.prepare_cell(work_root=run_root, prepared_root=root, phase="revision_generation", event_id=EVENT_ID, acknowledgement_sha256=ACK, source_root=source_root, revision_records=records)
    if _plain(root / "payload.json") != _plain(_terminal_root() / "payload.json"):
        raise ValueError("V6 replacement would not transmit byte-identical pilot payload")
    broker, route, proof = base._governed_route(pilot, queue_root=queue_root, phase="revision_generation", event_id=EVENT_ID)
    _write(root / "governed-route-proof.json", proof)
    original_outbound = json.loads(_plain(_terminal_root() / "outbound-payload.json"))
    outbound = {"format_version": 1, "kind": "versioned_successor_outbound_payload", "identity": {"study_id": STUDY_ID, "successor_event_id": replacement_id, "logical_sample_id": _sha(canonical({"original_event_id": EVENT_ID, "original_payload_sha256": _sha(_plain(root / "payload.json"))}))}, "pilot_payload": original_outbound["pilot_payload"]}
    if canonical(outbound["pilot_payload"]) + b"\n" != _plain(root / "payload.json"):
        raise ValueError("V6 replacement pilot payload drifted from original bytes")
    _write(root / "outbound-payload.json", outbound)
    schema = base._decorate_adapter_schema(base._REVISION_RESPONSE_SCHEMA)
    schema_binding = {"format_version": 1, "study_id": STUDY_ID, "kind": "adapter_schema_decoration", "underlying_pilot_response_schema": base._REVISION_RESPONSE_SCHEMA, "underlying_pilot_response_schema_sha256": _sha(canonical(base._REVISION_RESPONSE_SCHEMA)), "adapter_output_schema": schema, "adapter_output_schema_sha256": _sha(canonical(schema))}
    _write(root / "adapter-schema-binding.json", schema_binding)
    admission = {"format_version": 1, "study_id": STUDY_ID, "kind": "single_replacement_prepared", "replacement_event_id": replacement_id, "original_event_id": EVENT_ID, "original_terminal": verify_terminal(), "prepared": prepared, "route_evidence": _commit(run_root, root / "governed-route-proof.json"), "adapter_schema": _commit(run_root, root / "adapter-schema-binding.json"), "original_payload": _commit(V5_ROOT, _terminal_root() / "payload.json"), "original_outbound_payload": _commit(V5_ROOT, _terminal_root() / "outbound-payload.json"), "replacement_payload": _commit(run_root, root / "payload.json"), "outbound_payload": _commit(run_root, root / "outbound-payload.json"), "provider_calls_made": 0, "no_resend": True}
    _write(root / "replacement-admission.json", admission)
    return admission


def _replacement_root(run_root: Path) -> Path:
    root = Path(run_root) / "replacement-cells" / _replacement_id(Path(run_root))
    if not root.is_dir():
        raise ValueError("V6 replacement has not been prepared")
    return root


def execute_replacement(*, run_root: Path, allow_remote: bool) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("V6 requires explicit allow_remote=True")
    run_root = _safe_root(Path(run_root)); base = _base(); pilot = _pilot(base); root = _replacement_root(run_root)
    _validate_run_inventory(run_root, adopted=False, replacement_state="prelaunch")
    if (root / "launch-intent.json").exists() or (root / "terminal-outcome.json").exists() or (root / "replacement-authority.json").exists():
        raise ValueError("V6 replacement is one-shot and cannot resend")
    prepared, outbound_raw, _outbound, proof = _prepared_admission(base, run_root, root, state="prelaunch")
    admission_raw = _plain(root / "replacement-admission.json")
    schema = base._decorate_adapter_schema(base._REVISION_RESPONSE_SCHEMA)
    pilot._validate_current_prepared(prepared_root=root, prepared=prepared)
    queue_root = _safe_root(Path(proof["queue_root"]))
    _disjoint(run_root, queue_root, label="work/queue")
    broker, route, current = base._governed_route(pilot, queue_root=queue_root, phase="revision_generation", event_id=EVENT_ID)
    if any(proof.get(k) != current.get(k) for k in set(proof) - {"validated_at"}):
        raise ValueError("V6 governed route drifted")
    args = ["--grok-command-json", canonical(route["grok_command"]).decode(), "--model", route["model"], "--reported-model", route["reported_model"], "--reasoning-effort", route["reasoning_effort"], "--output-schema-json", canonical(schema).decode(), "--expected-command-identity-json", canonical(route["grok_command_identity"]).decode(), "--cli-version-command-json", canonical(route["cli_version_command"]).decode(), "--expected-cli-version-identity-json", canonical(route["cli_version_identity"]).decode(), "--expected-cli-version", route["grok_cli_version"], "--subscription-receipt-json", canonical(broker._load_json_artifact(route["subscription_receipt_hash"])).decode(), "--broker-root", str(broker.root), "--timeout-seconds", str(route["timeout_seconds"]), "--nonvisual-max-turns", str(route["nonvisual_max_turns"])]
    prior_ids = _prior_native_ids()
    verify_terminal(); contract()
    prepared, replay_outbound, _outbound, replay_proof = _prepared_admission(base, run_root, root, state="prelaunch")
    if replay_outbound != outbound_raw or replay_proof != proof:
        raise ValueError("V6 replacement admission changed before launch")
    launch_route = {"format_version": 1, "study_id": STUDY_ID, "kind": "launch_time_route_identity", "prepared": _commit(run_root, root / "prepared-cell.json"), "admission_sha256": _sha(admission_raw), "route_evidence": _commit(run_root, root / "governed-route-proof.json"), "adapter_schema": _commit(run_root, root / "adapter-schema-binding.json"), "route": {"model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"], "grok_command_identity": route["grok_command_identity"], "subscription_receipt_hash": route["subscription_receipt_hash"]}}
    _write(root / "launch-route-binding.json", launch_route)
    pilot.begin_one_launch(prepared_root=root)
    try:
        completed = _SUBPROCESS_RUN([*route["command"], *args], input=canonical({"prompt": outbound_raw.decode("utf-8")}), capture_output=True, check=False, timeout=int(route["timeout_seconds"]))
        _write_raw(root / "adapter-stdout.raw", completed.stdout)
        if completed.returncode != 0:
            raise ValueError("V6 replacement subprocess did not settle")
        state, _result = base._control_from_adapter(completed.stdout)
        _write(root / "adapter-control.json", base._adapter_envelope(completed.stdout))
        binding = {"format_version": 1, "study_id": STUDY_ID, "kind": "exact_raw_adapter_stdout", "raw_stdout": _commit(run_root, root / "adapter-stdout.raw"), "control": _commit(run_root, root / "adapter-control.json")}
        _write(root / "adapter-stdout-binding.json", binding)
        if state != "completed":
            raise ValueError("V6 replacement did not return a completed control")
        native = base._receipt_from_control(pilot=pilot, root=root, prepared=prepared, route=route, control_raw=completed.stdout, payload_override=outbound_raw)
        if native["provider_request_id"] in prior_ids or native["session_id"] in prior_ids or native["provider_request_id"] == native["session_id"]:
            raise ValueError("V6 replacement native request/session identity is not unique")
        authority = {"format_version": 1, "study_id": STUDY_ID, "kind": "v6_wrapper_bound_native_replacement_authority", "original_event_id": EVENT_ID, "replacement_event_id": _replacement_id(run_root), "prepared": _commit(run_root, root / "prepared-cell.json"), "outbound_payload": _commit(run_root, root / "outbound-payload.json"), "launch_route": _commit(run_root, root / "launch-route-binding.json"), "actual_native_receipt": native}
        _write(root / "replacement-authority.json", authority)
    except Exception as error:
        pilot.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)
        return {"study_id": STUDY_ID, "original_event_id": EVENT_ID, "state": "terminal_postlaunch_reconcile_required", "process_launches": 1, "provider_calls_made": "unproven", "no_resend": True, "error_type": type(error).__name__, "error": str(error)}
    return {"study_id": STUDY_ID, "original_event_id": EVENT_ID, "replacement_event_id": _replacement_id(run_root), "state": "settled", "process_launches": 1, "provider_calls_made": 1, "no_resend": True, "replacement_authority": _commit(run_root, root / "replacement-authority.json")}


def adopt_original_event(*, run_root: Path) -> dict[str, Any]:
    run_root = _safe_root(Path(run_root)); base = _base(); pilot = _pilot(base); root = _replacement_root(run_root)
    verify_terminal(); contract(); _validate_run_inventory(run_root, adopted=False, replacement_state="settled")
    if (root / "terminal-outcome.json").exists():
        raise ValueError("V6 cannot adopt an ambiguous replacement")
    verified = pilot._read_verified_receipt(root / "replacement-authority.json", expected_event_id=EVENT_ID, expected_phase="revision_generation")
    if verified.get("event_id") != EVENT_ID or verified.get("phase") != "revision_generation":
        raise ValueError("V6 replacement receipt identity drifted")
    descendant = run_root / "descendants" / f"{EVENT_ID}.md"
    _write_raw(descendant, verified["response"]["story"].encode("utf-8"))
    records = _carry_records(base, run_root)
    source = pilot.contract()["sources"]["items"]["hanna-178"]
    parent = next(row for row in records if row["event_id"] == "revision-v2-c1-hanna-178-grok-4.6-generic_no_feedback")
    record = {"event_id": EVENT_ID, "source": {"item_id": "hanna-178", "source.md": source["source.md"], "prompt.md": source["prompt.md"]}, "parent": {"event_id": parent["event_id"], "descendant": parent["descendant"]}, "descendant": _commit(run_root, descendant), "generator": {"model": "grok-4.6", "reasoning": "high", "tools_enabled": False}, "generator_receipt": _commit(run_root, root / "replacement-authority.json"), "cwr_feedback": None}
    pilot.validate_revision_lineage(work_root=run_root, records=[*records, record])
    authority = {"format_version": 1, "study_id": STUDY_ID, "kind": "adopted_original_event_after_single_fresh_replacement", "original_event_id": EVENT_ID, "replacement_event_id": _replacement_id(run_root), "original_terminal": verify_terminal(), "replacement_receipt": record["generator_receipt"], "record": record, "no_resend": True}
    _write(run_root / "adoptions" / f"{EVENT_ID}.json", authority)
    return record


def validate_full_lineage(*, run_root: Path) -> dict[str, Any]:
    run_root = _safe_root(Path(run_root)); verify_terminal(); contract(); _validate_run_inventory(run_root, adopted=True, replacement_state="settled"); base = _base(); pilot = _pilot(base); records = _carry_records(base, run_root)
    raw = _plain(Path(run_root) / "adoptions" / f"{EVENT_ID}.json")
    adoption = json.loads(raw)
    record = adoption.get("record")
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "adopted_original_event_after_single_fresh_replacement", "original_event_id": EVENT_ID, "replacement_event_id": _replacement_id(run_root), "original_terminal": verify_terminal(), "replacement_receipt": _commit(run_root, _replacement_root(run_root) / "replacement-authority.json"), "record": record, "no_resend": True}
    if canonical(adoption) + b"\n" != raw or adoption != expected or not isinstance(record, Mapping) or record.get("event_id") != EVENT_ID:
        raise ValueError("V6 adoption authority drifted")
    return pilot.validate_revision_lineage(work_root=Path(run_root), records=[*records, adoption["record"]])


def freeze_targets(*, run_root: Path, source_root: Path, target_root: Path) -> dict[str, Any]:
    run_root = _safe_root(Path(run_root)); source_root = _safe_root(Path(source_root)); target_root = _safe_target_root(run_root, Path(target_root), source_root)
    base = _base(); pilot = _pilot(base); validate_full_lineage(run_root=run_root)
    record = json.loads(_plain(run_root / "adoptions" / f"{EVENT_ID}.json"))["record"]
    return pilot.prepare_targets(work_root=run_root, target_root=target_root, source_root=source_root, revision_records=[*_carry_records(base, run_root), record])
