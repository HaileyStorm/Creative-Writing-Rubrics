"""Fresh strict-schema continuation for the 128 WPB cells left after batch 01."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STRICT = HERE / "sol_strict_schema_successor.py"
STRICT_SHA256 = "2627a161c2bb4aa8f40b1201366359ed25b033587294acc3607e25fd0d38a1be"
RECONCILIATION_SHA256 = "6e1efc368e8ebfa56037754386cef3eb25a4efb251185ae7ca6d32844670fa06"
BASE_CAMPAIGN_SHA256 = "de7cdfc40a8748e9a168a9065f318c5342ee4476ea034ae72b45c67dae3b359a"
ADMITTED_CELL = "wpb-pair-wpb-en-0052"
MAX_BATCH_SIZE = 10
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    _require(isinstance(value, dict) and raw == canonical(value), f"noncanonical {label}")
    return value, raw


def _write_new(path: Path, value: Mapping[str, Any] | bytes) -> bytes:
    raw = value if isinstance(value, bytes) else canonical(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return raw


def _exact(path: Path, expected: str, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"missing {label}") from error
    _require(sha256(raw) == expected, f"{label} source drifted")
    return raw


def _time(value: Any, label: str) -> datetime:
    _require(type(value) is str and value.endswith("Z"), f"{label} must be UTC Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error


def _load_strict() -> ModuleType:
    raw = _exact(STRICT, STRICT_SHA256, "strict-schema predecessor")
    module = ModuleType("_wpb_pending_strict_predecessor")
    module.__file__ = str(STRICT)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(STRICT), "exec"), module.__dict__)  # noqa: S102 - predecessor bytes are pinned.
    finally:
        sys.modules.pop(module.__name__, None)
    _exact(STRICT, STRICT_SHA256, "strict-schema predecessor")
    return module


def source_manifest() -> dict[str, Any]:
    strict = _load_strict()
    own = Path(__file__).resolve().read_bytes()
    return {"format_version": 1, "kind": "wpb_sol_pending_continuation_source_manifest_v1",
            "continuation": {"path": str(Path(__file__).resolve()), "sha256": sha256(own)},
            "strict_predecessor": {"path": str(STRICT.resolve()), "sha256": STRICT_SHA256},
            "strict_source_manifest": strict.source_manifest()}


def _reconciliation(path: Path) -> dict[str, Any]:
    value, raw = _read(path, "strict batch-01 reconciliation")
    _require(sha256(raw) == RECONCILIATION_SHA256 and value.get("campaign_sha256") == BASE_CAMPAIGN_SHA256
             and value.get("completed_cell_ids") == [ADMITTED_CELL] and value.get("remaining_logical_cells") == 128
             and value.get("automatic_resend") is False and value.get("batch_restart_authorized") is False
             and value.get("root_cause") == "unproven", "strict batch-01 reconciliation differs")
    return value


def _manifest_path(root: Path) -> Path:
    return root / "pending-continuation-manifest.json"


def _batch(root: Path, number: int) -> Path:
    _require(type(number) is int and number > 0, "batch number is invalid")
    return root / "batches" / f"{number:04d}"


def _projection_path(batch: Path) -> Path:
    return batch / "strict-schema-projection.json"


def _binding_path(batch: Path) -> Path:
    return batch / "pending-continuation-review-binding.json"


def _strict_path(batch: Path) -> Path:
    return batch / "strict-native-schema.json"


def _filtered_resolution(resolution: Mapping[str, Any]) -> dict[str, Any]:
    rows = tuple(row for row in resolution["rows"] if str(row["cell_id"]) != ADMITTED_CELL)
    _require(len(resolution["rows"]) == 129 and len(rows) == 128, "frozen WPB schedule differs")
    payloads = {str(row["cell_id"]): resolution["payloads"][str(row["cell_id"])] for row in rows}
    return {**resolution, "rows": rows, "payloads": payloads}


def _configured_legacy() -> tuple[ModuleType, ModuleType]:
    """Use the pinned strict runtime while making 0052 unavailable to every lifecycle stage."""
    strict = _load_strict()
    legacy, _bridge = strict._configured_legacy()
    original_resolution = legacy._resolution

    def resolution(frozen: ModuleType, freeze_root: Path) -> dict[str, Any]:
        return _filtered_resolution(original_resolution(frozen, freeze_root))

    legacy._resolution = resolution
    return legacy, strict


def _source_guard(expected: Mapping[str, Any]) -> None:
    _require(source_manifest() == expected, "pending continuation source closure drifted")


def _manifest(root: Path) -> tuple[dict[str, Any], str]:
    value, raw = _read(_manifest_path(root), "pending continuation manifest")
    campaign, campaign_raw = _read(root / "campaign.json", "pending continuation campaign")
    expected_source = source_manifest()
    _require(value.get("format_version") == 1 and value.get("kind") == "wpb_sol_pending_continuation_campaign_v1"
             and value.get("campaign") == {"path": str((root / "campaign.json").resolve()), "sha256": sha256(campaign_raw)}
             and value.get("source_manifest") == expected_source and value.get("source_manifest_sha256") == sha256(expected_source)
             and value.get("admitted_predecessor_cell") == ADMITTED_CELL and value.get("remaining_logical_cells") == 128
             and value.get("automatic_resend_authorized") is False and value.get("schedule_sha256") == campaign.get("schedule_sha256")
             and isinstance(value.get("selection_context_sha256"), str) and _HASH.fullmatch(value["selection_context_sha256"])
             and value.get("full_selection_verification") == "frozen_verifier_required_on_every_lifecycle_stage"
             and isinstance(value.get("reconciliation"), Mapping) and value["reconciliation"].get("sha256") == RECONCILIATION_SHA256,
             "pending continuation manifest differs")
    ids = [str(cell.get("cell_id")) for cell in campaign.get("cells", [])]
    _require(len(ids) == 128 and ADMITTED_CELL not in ids and len(set(ids)) == 128, "pending continuation schedule differs")
    return value, sha256(raw)


def create_campaign(*, campaign_root: Path, reconciliation_path: Path, **kwargs: Any) -> dict[str, Any]:
    """Create the fresh 128-cell root after an explicit full selection verification."""
    root, source = Path(campaign_root).resolve(), source_manifest()
    _require(not root.exists(), "fresh pending continuation root required")
    reconciliation = _reconciliation(Path(reconciliation_path))
    legacy, _strict = _configured_legacy()
    original_freeze, captured = legacy._full_freeze, {}

    def record_freeze(*args: Any, **inner: Any) -> dict[str, Any]:
        value = original_freeze(*args, **inner)
        if inner.get("replay_native") is True:
            captured["context"] = value
        return value

    legacy._full_freeze = record_freeze
    result = legacy.create_campaign(campaign_root=root, **kwargs)
    campaign, campaign_raw = _read(root / "campaign.json", "pending continuation campaign")
    context = captured.get("context")
    _require(isinstance(context, Mapping), "full selection verification was not recorded")
    _require(context["schedule_sha256"] == campaign["schedule_sha256"], "full selection schedule differs")
    _source_guard(source)
    manifest = {"format_version": 1, "kind": "wpb_sol_pending_continuation_campaign_v1",
                "campaign": {"path": str((root / "campaign.json").resolve()), "sha256": sha256(campaign_raw)},
                "reconciliation": {"path": str(Path(reconciliation_path).resolve()), "sha256": RECONCILIATION_SHA256,
                                   "immutable_inventory_sha256": reconciliation["immutable_evidence_inventory_sha256"]},
                "source_manifest": source, "source_manifest_sha256": sha256(source),
                "selection_context_sha256": sha256(context),
                "full_selection_verification": "frozen_verifier_required_on_every_lifecycle_stage", "admitted_predecessor_cell": ADMITTED_CELL,
                "remaining_logical_cells": 128, "schedule_sha256": campaign["schedule_sha256"],
                "automatic_resend_authorized": False}
    raw = _write_new(_manifest_path(root), manifest)
    return {**result, "logical_cells": 128, "pending_continuation_manifest_sha256": sha256(raw),
            "full_selection_verification": "native_replay", "provider_calls_made": 0, "process_launches": 0}


def _projection(root: Path, number: int) -> tuple[dict[str, Any], str]:
    batch = _batch(root, number)
    value, raw = _read(_projection_path(batch), "strict schema projection")
    manifest, manifest_sha = _manifest(root)
    plan, plan_raw = _read(batch / "plan.json", "pending continuation batch plan")
    strict, strict_raw = _read(_strict_path(batch), "strict native schema")
    cells = plan.get("cell_ids")
    _require(isinstance(cells, list) and 1 <= len(cells) <= MAX_BATCH_SIZE and all(isinstance(cell, str) for cell in cells),
             "pending continuation plan cells differ")
    schemas: dict[str, str] = {}
    for cell_id in cells:
        schema, schema_raw = _read(batch / "execution" / cell_id / "response-schema.json", "prepared evaluation schema")
        strict_predecessor = _load_strict()
        _require(strict == strict_predecessor.strict_native_schema(schema), "strict native schema differs")
        schemas[cell_id] = sha256(schema_raw)
    expected = {"format_version": 1, "kind": "wpb_sol_pending_continuation_strict_schema_projection_v1",
                "pending_continuation_manifest_sha256": manifest_sha, "legacy_plan_sha256": sha256(plan_raw),
                "batch_number": number, "cell_ids": cells, "evaluation_schema_sha256s": schemas,
                "strict_native_schema_sha256": sha256(strict_raw), "actual_commands": value.get("actual_commands"),
                "actual_command_sha256s": value.get("actual_command_sha256s"),
                "source_manifest_sha256": manifest["source_manifest_sha256"]}
    _require(value == expected and isinstance(value["actual_commands"], Mapping)
             and set(value["actual_commands"]) == set(cells)
             and value["actual_command_sha256s"] == {key: sha256(command) for key, command in value["actual_commands"].items()},
             "strict schema projection differs")
    return value, sha256(raw)


def _install_frozen_verifier(legacy: ModuleType, *, source: Mapping[str, Any], selection_context_sha256: str) -> None:
    original = legacy._full_freeze

    def verified(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _source_guard(source)
        value = original(*args, **kwargs)
        _require(sha256(value) == selection_context_sha256, "frozen selection context differs")
        _source_guard(source)
        return value

    legacy._full_freeze = verified


def prepare_next_batch(**kwargs: Any) -> dict[str, Any]:
    """Prepare at most ten never-contacted cells and persist the exact strict command projection."""
    root, source = Path(kwargs["campaign_root"]).resolve(), source_manifest()
    manifest, manifest_sha = _manifest(root)
    legacy, strict = _configured_legacy()
    _install_frozen_verifier(legacy, source=source, selection_context_sha256=manifest["selection_context_sha256"])
    supplied_factory = kwargs.pop("broker_factory", None)
    _require(supplied_factory is None or callable(supplied_factory), "pending continuation broker factory differs")
    bridge = strict._load_bridge()
    factory = supplied_factory or bridge.broker_factory(source["strict_source_manifest"]["broker_source_manifest"],
                                                        before_create=lambda: _source_guard(source))
    result = legacy.prepare_next_batch(**(kwargs | {"broker_factory": factory}))
    batch = _batch(root, result["batch_number"])
    plan, plan_raw = _read(batch / "plan.json", "pending continuation batch plan")
    cells = plan["cell_ids"]
    schemas = [_read(batch / "execution" / cell_id / "response-schema.json", "prepared evaluation schema")[0] for cell_id in cells]
    _require(all(schema == schemas[0] for schema in schemas), "per-cell evaluation schema differs")
    strict_raw = canonical(strict.strict_native_schema(schemas[0]))
    _write_new(_strict_path(batch), strict_raw)
    frozen = legacy._frozen()
    resolution = legacy._resolution(frozen, Path(kwargs["freeze_root"]))
    _lifecycle, runtime, _rows = frozen._sol_runtime(resolution)
    executable = plan["route"]["codex_command"][0]
    commands = {cell_id: runtime._load_v3()._expected_codex_command(executable, batch / "execution" / cell_id) for cell_id in cells}
    _source_guard(source)
    projection = {"format_version": 1, "kind": "wpb_sol_pending_continuation_strict_schema_projection_v1",
                  "pending_continuation_manifest_sha256": manifest_sha, "legacy_plan_sha256": sha256(plan_raw),
                  "batch_number": result["batch_number"], "cell_ids": cells,
                  "evaluation_schema_sha256s": {cell_id: sha256((batch / "execution" / cell_id / "response-schema.json").read_bytes()) for cell_id in cells},
                  "strict_native_schema_sha256": sha256(strict_raw), "actual_commands": commands,
                  "actual_command_sha256s": {cell_id: sha256(command) for cell_id, command in commands.items()},
                  "source_manifest_sha256": manifest["source_manifest_sha256"]}
    raw = _write_new(_projection_path(batch), projection)
    return {**result, "strict_schema_projection_sha256": sha256(raw), "provider_calls_made": 0, "process_launches": 0}


def review_material(*, campaign_root: Path, batch_number: int) -> dict[str, Any]:
    projection, projection_sha = _projection(Path(campaign_root).resolve(), batch_number)
    return {"format_version": 1, "kind": "wpb_sol_pending_continuation_dispatch_review_v1",
            "decision": "approved_wpb_sol_pending_continuation_dispatch", "projection_sha256": projection_sha,
            "pending_continuation_manifest_sha256": projection["pending_continuation_manifest_sha256"],
            "legacy_plan_sha256": projection["legacy_plan_sha256"], "batch_number": batch_number,
            "cell_ids": projection["cell_ids"], "strict_native_schema_sha256": projection["strict_native_schema_sha256"],
            "actual_command_sha256s": projection["actual_command_sha256s"],
            "source_manifest_sha256": projection["source_manifest_sha256"], "reviewed_at": None, "expires_at": None}


def _review(path: Path, expected_sha256: str, root: Path, number: int, *, require_unexpired: bool) -> str:
    _require(isinstance(expected_sha256, str) and _HASH.fullmatch(expected_sha256) is not None, "continuation review anchor is invalid")
    value, raw = _read(path, "pending continuation independent review")
    expected = review_material(campaign_root=root, batch_number=number)
    _require(sha256(raw) == expected_sha256 and set(value) == set(expected)
             and all(value[key] == item for key, item in expected.items() if key not in {"reviewed_at", "expires_at"})
             and _time(value["reviewed_at"], "continuation review reviewed_at") < _time(value["expires_at"], "continuation review expires_at"),
             "pending continuation independent review differs")
    if require_unexpired:
        _require(datetime.now(timezone.utc) < _time(value["expires_at"], "continuation review expires_at"),
                 "pending continuation independent review has expired")
    return sha256(raw)


def _bind_review(root: Path, number: int, review_path: Path, review_sha256: str) -> None:
    projection, projection_sha = _projection(root, number)
    digest = _review(review_path, review_sha256, root, number, require_unexpired=True)
    value = {"format_version": 1, "kind": "wpb_sol_pending_continuation_review_binding_v1",
             "projection_sha256": projection_sha, "review": {"path": str(Path(review_path).resolve()), "sha256": digest},
             "source_manifest_sha256": projection["source_manifest_sha256"], "automatic_resend_authorized": False}
    _write_new(_binding_path(_batch(root, number)), value)


def _binding(root: Path, number: int, *, require_unexpired: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    projection, projection_sha = _projection(root, number)
    value, _raw = _read(_binding_path(_batch(root, number)), "pending continuation review binding")
    expected = {"format_version": 1, "kind": "wpb_sol_pending_continuation_review_binding_v1",
                "projection_sha256": projection_sha, "review": value.get("review"),
                "source_manifest_sha256": projection["source_manifest_sha256"], "automatic_resend_authorized": False}
    _require(value == expected and isinstance(value["review"], Mapping) and isinstance(value["review"].get("path"), str)
             and isinstance(value["review"].get("sha256"), str), "pending continuation review binding differs")
    _review(Path(value["review"]["path"]), value["review"]["sha256"], root, number, require_unexpired=require_unexpired)
    return value, projection


def _safe_failure(error: BaseException) -> dict[str, Any]:
    trace = error.__traceback__
    while trace is not None and trace.tb_next is not None:
        trace = trace.tb_next
    frame = trace.tb_frame if trace is not None else None
    return {"error_type": type(error).__name__, "source_function": frame.f_code.co_name if frame else None,
            "source_line": trace.tb_lineno if trace else None, "cause_type": type(error.__cause__).__name__ if error.__cause__ else None}


def dispatch_batch(*, continuation_review_path: Path, expected_continuation_review_sha256: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Dispatch through the frozen V3 lifecycle after full verification, source, review, route, and command checks."""
    root, number, source = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"], source_manifest()
    legacy, strict = _configured_legacy()
    manifest, _manifest_sha = _manifest(root)
    _install_frozen_verifier(legacy, source=source, selection_context_sha256=manifest["selection_context_sha256"])
    supplied_factory = kwargs.pop("broker_factory", None)
    _require(supplied_factory is None or callable(supplied_factory), "pending continuation broker factory differs")
    bridge = strict._load_bridge()
    factory = supplied_factory or bridge.broker_factory(source["strict_source_manifest"]["broker_source_manifest"],
                                                        before_create=lambda: _source_guard(source))
    def run_dispatch() -> list[dict[str, Any]]:
        _bind_review(root, number, Path(continuation_review_path), expected_continuation_review_sha256)
        frozen = legacy._frozen()
        resolution = legacy._resolution(frozen, Path(kwargs["freeze_root"]))
        _lifecycle, runtime, _rows = frozen._sol_runtime(resolution)
        base_call = kwargs.get("call_codex") or legacy._current_call_codex(runtime, receipt_root=_batch(root, number) / "sol-process-receipts")

        def strict_call(**call_kwargs: Any) -> tuple[str, dict[str, Any]]:
            _binding(root, number, require_unexpired=True)
            _source_guard(source)
            _bound, projection = _binding(root, number, require_unexpired=True)
            output_root = Path(call_kwargs["output_dir"])
            cell_id = output_root.name
            actual = runtime._load_v3()._expected_codex_command(call_kwargs["executable"], output_root)
            _require(actual == projection["actual_commands"].get(cell_id), "pending continuation command drifted before contact")
            before = call_kwargs.get("before_provider_attempt")
            _require(callable(before), "frozen Sol runtime omitted precontact gate")

            def guarded() -> None:
                _binding(root, number, require_unexpired=True)
                _source_guard(source)
                before()

            return base_call(**(call_kwargs | {"before_provider_attempt": guarded}))

        return legacy.dispatch_batch(**(kwargs | {"broker_factory": factory, "call_codex": strict_call}))

    try:
        return run_dispatch()
    except (OSError, TypeError, ValueError) as error:
        batch = _batch(root, number)
        if not (batch / "local-dispatch-failure.json").exists():
            _write_new(batch / "local-dispatch-failure.json", {"format_version": 1, "kind": "wpb_sol_pending_continuation_local_failure_v1",
                       "failure": _safe_failure(error), "launch_intent_exists": any((batch / "execution").glob("*/launch-intent.json")),
                       "process_receipt_exists": any((batch / "sol-process-receipts").glob("*.json")) if (batch / "sol-process-receipts").exists() else False,
                       "automatic_resend_authorized": False})
        raise


def settle_batch(**kwargs: Any) -> dict[str, Any]:
    root, number, source = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"], source_manifest()
    manifest, _manifest_sha = _manifest(root)
    legacy, _strict = _configured_legacy()
    _install_frozen_verifier(legacy, source=source, selection_context_sha256=manifest["selection_context_sha256"])
    _binding(root, number, require_unexpired=False)
    return legacy.settle_batch(**kwargs)


def _verify_predecessor(reconciliation: Mapping[str, Any], predecessor_root: Path) -> None:
    inventory = reconciliation.get("immutable_evidence_inventory")
    _require(isinstance(inventory, Mapping) and sha256(inventory) == reconciliation.get("immutable_evidence_inventory_sha256"),
             "predecessor immutable inventory differs")
    for relative, expected in inventory.items():
        _require(isinstance(relative, str) and isinstance(expected, str) and _HASH.fullmatch(expected) is not None,
                 "predecessor immutable inventory is malformed")
        _exact(predecessor_root / relative.replace("/", "\\"), expected, "predecessor immutable evidence")
    _require(reconciliation.get("completed_cell_ids") == [ADMITTED_CELL]
             and reconciliation.get("original_settlement_status_preserved") == "terminal_or_ambiguous", "predecessor admission differs")


def report(*, campaign_root: Path, predecessor_root: Path, reconciliation_path: Path, **kwargs: Any) -> dict[str, Any]:
    """Replay the immutable 0052 admission and all 128 new admissions through the frozen core."""
    root, source = Path(campaign_root).resolve(), source_manifest()
    manifest, manifest_sha = _manifest(root)
    reconciliation = _reconciliation(Path(reconciliation_path))
    predecessor = Path(predecessor_root).resolve()
    _verify_predecessor(reconciliation, predecessor)
    legacy, _strict = _configured_legacy()
    _install_frozen_verifier(legacy, source=source, selection_context_sha256=manifest["selection_context_sha256"])
    verifier_path = legacy._verifier_path(kwargs.get("freeze_verifier_path"))
    frozen = legacy._frozen()
    full_resolution = frozen._resolution(freeze_root=Path(kwargs["freeze_root"]))
    filtered = _filtered_resolution(full_resolution)
    context = legacy._full_freeze(Path(kwargs["freeze_path"]), kwargs["expected_freeze_sha256"],
                                  kwargs["expected_freeze_verifier_sha256"], verifier_path=verifier_path,
                                  mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False), replay_native=True)
    _require(context["schedule_sha256"] == full_resolution["schedule_sha256"], "full selection schedule differs")
    _source_guard(source)
    freeze_contract = legacy._freeze_contract(context, verifier_path=verifier_path,
                                               mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
    _campaign, campaign_sha256 = legacy._campaign(root, filtered, context, kwargs["expected_freeze_sha256"],
                                                   kwargs["expected_freeze_verifier_sha256"], freeze_contract)
    numbers = tuple(range(1, 14))
    _require(tuple(legacy._batch_numbers(root)) == numbers and not (root / "stopped.json").exists(),
             "pending continuation is incomplete or stopped")
    lifecycle, runtime, _rows = frozen._sol_runtime(filtered)
    v4 = lifecycle.sol_v4()
    by_id = {str(row["cell_id"]): row for row in full_resolution["rows"]}
    identities: set[tuple[str, str]] = set()
    measurements: list[dict[str, Any]] = []
    bindings: dict[str, dict[str, Any]] = {}

    old_plan, _old_plan_raw = _read(predecessor / "batches" / "0001" / "plan.json", "predecessor plan")
    old_row = by_id.get(ADMITTED_CELL)
    _require(old_row is not None and ADMITTED_CELL in old_plan.get("cell_ids", []), "predecessor completed cell differs")
    old_entry = predecessor / "batches" / "0001" / "execution" / ADMITTED_CELL
    old = lifecycle._admit_completed_cell(runtime, v4, old_row, old_entry, old_plan["authorization_acknowledgement_sha256"])
    old_identity = old["identity"]
    old_key = (str(old_identity.get("thread_id")), str(old_identity.get("session_id"))) if isinstance(old_identity, Mapping) else ("", "")
    _require(all(old_key), "predecessor native identity is missing")
    identities.add(old_key)
    old_answer = frozen._valid_response(full_resolution["core"], old["answer"])
    measurements.append({"endpoint": "sol", "cell_id": ADMITTED_CELL, "payload_sha256": old_row["payload_sha256"],
                         "measurement_provenance": {"endpoint": "sol", "cell_id": ADMITTED_CELL, "payload_sha256": old_row["payload_sha256"],
                                                    "parsed_response_sha256": frozen.sha256(old_answer)}, "response": old_answer})
    bindings[ADMITTED_CELL] = {"predecessor_reconciliation_sha256": RECONCILIATION_SHA256,
                               "execution_receipt_sha256": sha256(old["receipt"]), "identity_sha256": sha256(old_identity),
                               "effective_settings_sha256": frozen.sha256(old["settings"])}
    epochs: list[dict[str, Any]] = []
    for number in numbers:
        _binding(root, number, require_unexpired=False)
        plan, plan_sha = legacy._plan(root, number, campaign_sha256, verifier_path=verifier_path,
                                      mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
        legacy._cheap_freeze(plan, Path(kwargs["freeze_path"]), kwargs["expected_freeze_sha256"],
                             kwargs["expected_freeze_verifier_sha256"], verifier_path=verifier_path,
                             mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
        settlement, settlement_sha = legacy._settlement(root, number, campaign_sha256)
        _require(settlement.get("status") == "completed" and settlement.get("plan_sha256") == plan_sha
                 and len(settlement.get("cells", [])) == len(plan["cell_ids"]), "pending continuation settlement is incomplete")
        rows = legacy._batch_rows(filtered, plan)
        legacy._verify_prepared_bindings(_batch(root, number), rows, plan)
        entries = lifecycle._output_inventory(_batch(root, number) / "execution", rows)
        settled = {str(cell.get("cell_id")): cell for cell in settlement["cells"] if isinstance(cell, Mapping)}
        for row in rows:
            cell_id = str(row["cell_id"])
            record = settled.get(cell_id)
            _require(isinstance(record, Mapping) and record.get("state") == "completed", "unsettled continuation cell")
            admitted = lifecycle._admit_completed_cell(runtime, v4, row, entries[cell_id], plan["authorization_acknowledgement_sha256"])
            _require(admitted["route"] == plan["route"] and admitted["route_evidence"] == plan["route_evidence"], "admitted continuation route differs")
            identity = admitted["identity"]
            key = (str(identity.get("thread_id")), str(identity.get("session_id"))) if isinstance(identity, Mapping) else ("", "")
            _require(all(key) and key not in identities, "duplicate continuation native identity")
            identities.add(key)
            answer = frozen._valid_response(full_resolution["core"], admitted["answer"])
            _require(record.get("execution_receipt_sha256") == sha256(admitted["receipt"])
                     and record.get("raw_response_sha256") == sha256(admitted["final"])
                     and record.get("identity_sha256") == sha256(identity), "continuation settlement receipt binding drifted")
            measurements.append({"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                 "measurement_provenance": {"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                                            "parsed_response_sha256": frozen.sha256(answer)}, "response": answer})
            bindings[cell_id] = {"batch_number": number, "route_sha256": plan["route_sha256"],
                                 "route_evidence_sha256": plan["route_evidence_sha256"], "review_sha256": plan["review_sha256"],
                                 "execution_receipt_sha256": sha256(admitted["receipt"]), "identity_sha256": sha256(identity),
                                 "effective_settings_sha256": frozen.sha256(admitted["settings"]),
                                 "prepared_source_bindings_sha256": plan["prepared_source_bindings_sha256"]}
        epochs.append({"batch_number": number, "route_sha256": plan["route_sha256"],
                       "route_evidence_sha256": plan["route_evidence_sha256"], "review_sha256": plan["review_sha256"],
                       "settlement_sha256": settlement_sha})
    _require(len(measurements) == 129 and {item["cell_id"] for item in measurements} == set(by_id) and len(identities) == 129,
             "full 129-cell continuation replay is incomplete")
    analysis = full_resolution["core"].analyze(Path(kwargs["freeze_root"]), measurements, context["selected_profile"])
    return {"format_version": 1, "kind": "wpb_sol_pending_continuation_replayed_report_v1", "status": "complete_batched_sol_campaign",
            "authority": "development_screening_only", "confirmation": "closed", "measurement_count": 129,
            "admitted_predecessor_cell": ADMITTED_CELL, "new_measurement_count": 128,
            "pending_continuation_manifest_sha256": manifest_sha, "reconciliation_sha256": RECONCILIATION_SHA256,
            "full_selection_verification": "native_replay", "route_epochs": epochs,
            "native_receipt_bindings": bindings, "analysis": analysis}
