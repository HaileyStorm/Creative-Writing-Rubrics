"""Prospective 126-cell Sol successor with serialized frozen-core verifier loads."""
from __future__ import annotations

import hashlib
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
LEGACY = HERE / "sol_partial_successor.py"
LEGACY_SHA256 = "82f1b825f4d76d6d9bc98a80985ead2b90d66f6236a7a230eee971264f1d4075"
SERIALIZER = HERE / "sol_frozen_core_serialization.py"
SERIALIZER_SHA256 = "a5b805ccb85c6a5c59c67f85b97589f626504301864a13f99bd17579af4fa0ec"
PREFIX = ("wpb-pair-wpb-en-0052", "wpb-pair-wpb-en-0068", "wpb-pair-wpb-en-0015")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_exact(path: Path, expected: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    _require(bool(expected) and hashlib.sha256(raw).hexdigest() == expected, f"{name} source drifted")
    module = ModuleType(name); module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(name, None)
    _require(path.read_bytes() == raw, f"{name} source changed during load")
    return module


def _load_legacy() -> ModuleType:
    return _load_exact(LEGACY, LEGACY_SHA256, "_wpb_serialized126_legacy")


def _load_serializer() -> ModuleType:
    return _load_exact(SERIALIZER, SERIALIZER_SHA256, "_wpb_serialized126_serializer")


def canonical(value: Any) -> bytes:
    return _load_legacy().canonical(value)


def sha256(value: Any) -> str:
    return _load_legacy().sha256(value)


def _read(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    return _load_legacy()._read(path, label)


def _write_new(path: Path, value: Any) -> bytes:
    return _load_legacy()._write_new(path, value)


def source_manifest() -> dict[str, Any]:
    legacy, serializer = _load_legacy(), _load_serializer()
    return {
        "format_version": 1,
        "kind": "wpb_sol_serialized126_successor_source_manifest_v1",
        "successor": {"path": str(Path(__file__).resolve()), "sha256": _sha(Path(__file__).resolve())},
        "historical_partial_successor": {"path": str(LEGACY.resolve()), "sha256": LEGACY_SHA256,
                                          "source_manifest": legacy.source_manifest()},
        "frozen_core_serialization": {"path": str(SERIALIZER.resolve()), "sha256": SERIALIZER_SHA256,
                                       "source_manifest": serializer.source_manifest()},
    }


def _filtered(resolution: dict[str, Any]) -> dict[str, Any]:
    rows = tuple(row for row in resolution["rows"] if str(row["cell_id"]) not in PREFIX)
    ids = [str(row["cell_id"]) for row in resolution["rows"]]
    _require(len(resolution["rows"]) == 127 and len(rows) == 126 and ids.count(PREFIX[2]) == 1
             and not set(PREFIX[:2]) & set(ids), "frozen three-cell prefix differs")
    return {**resolution, "rows": rows, "payloads": {str(row["cell_id"]): resolution["payloads"][str(row["cell_id"])] for row in rows}}


def _configured_legacy(shared_state: dict[str, Any] | None = None) -> tuple[ModuleType, ModuleType, dict[str, Any]]:
    state = {} if shared_state is None else shared_state
    legacy_source = _load_legacy(); legacy, strict = legacy_source._configured_legacy()
    serializer = _load_serializer(); serializer.install_on_legacy(legacy, state)
    previous = legacy._resolution

    def resolution(frozen: ModuleType, freeze_root: Path) -> dict[str, Any]:
        return _filtered(previous(frozen, freeze_root))

    legacy._resolution = resolution
    return legacy, strict, state


def _manifest_path(root: Path) -> Path:
    return root / "serialized126-successor-manifest.json"


def _batch(root: Path, number: int) -> Path:
    return root / "batches" / f"{number:04d}"


def _projection_path(batch: Path) -> Path:
    return batch / "serialized126-projection.json"


def _binding_path(batch: Path) -> Path:
    return batch / "serialized126-review-binding.json"


def _manifest(root: Path) -> tuple[dict[str, Any], str]:
    value, raw = _read(_manifest_path(root), "serialized126 successor manifest")
    campaign, campaign_raw = _read(root / "campaign.json", "serialized126 campaign")
    source = source_manifest()
    _require(value.get("format_version") == 1 and value.get("kind") == "wpb_sol_serialized126_successor_v1"
             and value.get("campaign") == {"path": str((root / "campaign.json").resolve()), "sha256": sha256(campaign_raw)}
             and value.get("source_manifest") == source and value.get("source_manifest_sha256") == sha256(source)
             and value.get("completed_cells") == list(PREFIX) and value.get("remaining_logical_cells") == 126
             and value.get("automatic_resend_authorized") is False and len(campaign.get("cells", [])) == 126,
             "serialized126 successor manifest differs")
    return value, sha256(raw)


def _verify_reconciliation(path: Path, expected: str, root: Path) -> tuple[dict[str, Any], bytes]:
    value, raw = _read(path, "serialized126 reconciliation"); inventory = value.get("immutable_inventory")
    _require(sha256(raw) == expected and value.get("format_version") == 1
             and value.get("kind") == "wpb_sol_serialized126_successor_reconciliation_v1"
             and value.get("source_sha256") == LEGACY_SHA256 and value.get("source_manifest_sha256") == sha256(_load_legacy().source_manifest())
             and value.get("completed_cells") == list(PREFIX) and value.get("remaining_logical_cells") == 126
             and value.get("automatic_resend_authorized") is False and isinstance(inventory, dict)
             and value.get("immutable_inventory_sha256") == sha256(inventory), "serialized126 reconciliation differs")
    prior_root = Path(value.get("campaign_root", "")).resolve()
    _require(prior_root.is_dir() and prior_root != root, "serialized126 reconciliation campaign root differs")
    _require(_sha(prior_root / "campaign.json") == value.get("campaign_sha256"), "serialized126 reconciliation campaign differs")
    for relative, digest in inventory.items():
        _require(isinstance(relative, str) and isinstance(digest, str), "serialized126 inventory is malformed")
        _load_legacy()._load_pending()._exact(prior_root / relative.replace("/", "\\"), digest, "serialized126 immutable evidence")
    for key in ("serialization_helper", "prior_reconciliation", "settlement", "0015_execution_receipt", "0015_process_receipt"):
        descriptor = value.get(key)
        _require(isinstance(descriptor, dict) and set(descriptor) == {"path", "sha256"}, "serialized126 reconciliation descriptor differs")
        _load_legacy()._load_pending()._exact(Path(descriptor["path"]), descriptor["sha256"], "serialized126 reconciliation descriptor")
    _require(value["serialization_helper"] == {"path": str(SERIALIZER.resolve()), "sha256": SERIALIZER_SHA256},
             "serialized126 helper pin differs")
    return value, raw


def _source_guard(expected: dict[str, Any]) -> None:
    _require(source_manifest() == expected, "serialized126 source closure drifted")


def create_campaign(*, campaign_root: Path, reconciliation_path: Path, expected_reconciliation_sha256: str, **kwargs: Any) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); _require(not root.exists(), "fresh serialized126 root required")
    _reconciliation, _raw = _verify_reconciliation(Path(reconciliation_path), expected_reconciliation_sha256, root)
    source = source_manifest(); shared: dict[str, Any] = {}; legacy, _strict, _state = _configured_legacy(shared)
    captured: dict[str, Any] = {}; original = legacy._full_freeze

    def freeze(*args: Any, **inner: Any) -> dict[str, Any]:
        result = original(*args, **inner)
        if inner.get("replay_native") is True:
            captured["context"] = result
        return result

    legacy._full_freeze = freeze
    result = legacy.create_campaign(campaign_root=root, **kwargs)
    campaign, campaign_raw = _read(root / "campaign.json", "serialized126 campaign"); context = captured.get("context")
    _require(isinstance(context, dict) and context.get("schedule_sha256") == campaign.get("schedule_sha256"),
             "full selection verification is missing")
    _source_guard(source)
    manifest = {"format_version": 1, "kind": "wpb_sol_serialized126_successor_v1",
                "campaign": {"path": str((root / "campaign.json").resolve()), "sha256": sha256(campaign_raw)},
                "reconciliation": {"path": str(Path(reconciliation_path).resolve()), "sha256": expected_reconciliation_sha256},
                "source_manifest": source, "source_manifest_sha256": sha256(source), "selection_context_sha256": sha256(context),
                "completed_cells": list(PREFIX), "remaining_logical_cells": 126, "automatic_resend_authorized": False}
    raw = _write_new(_manifest_path(root), manifest)
    return {**result, "logical_cells": 126, "serialized126_successor_manifest_sha256": sha256(raw),
            "provider_calls_made": 0, "process_launches": 0}


def _historical(manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest["source_manifest"]["historical_partial_successor"]["source_manifest"]


def _install_frozen_verifier(legacy: ModuleType, manifest: dict[str, Any]) -> None:
    historical = _historical(manifest)
    _load_legacy()._load_pending()._install_frozen_verifier(
        legacy, source=historical["pending_source_manifest"], selection_context_sha256=manifest["selection_context_sha256"])


def _broker_factory(legacy: ModuleType, strict: ModuleType, manifest: dict[str, Any], supplied: Any) -> Any:
    _require(supplied is None or callable(supplied), "serialized126 broker factory differs")
    if supplied is not None:
        return supplied
    historical = _historical(manifest)
    bridge = strict._load_bridge()
    return bridge.broker_factory(historical["pending_source_manifest"]["strict_source_manifest"]["broker_source_manifest"],
                                 before_create=lambda: _source_guard(manifest["source_manifest"]))


def prepare_next_batch(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs["campaign_root"]).resolve(); manifest, manifest_sha = _manifest(root)
    legacy, strict, _state = _configured_legacy({})
    _install_frozen_verifier(legacy, manifest); factory = _broker_factory(legacy, strict, manifest, kwargs.pop("broker_factory", None))
    result = legacy.prepare_next_batch(**(kwargs | {"broker_factory": factory}))
    batch = _batch(root, result["batch_number"]); plan, plan_raw = _read(batch / "plan.json", "serialized126 plan")
    cells = plan.get("cell_ids"); _require(isinstance(cells, list) and not set(cells) & set(PREFIX), "completed prefix was prepared")
    schemas = [_read(batch / "execution" / cell / "response-schema.json", "serialized126 schema")[0] for cell in cells]
    strict_raw = canonical(strict.strict_native_schema(schemas[0])); _write_new(batch / "strict-native-schema.json", strict_raw)
    projection = {"format_version": 1, "kind": "wpb_sol_serialized126_successor_projection_v1",
                  "successor_manifest_sha256": manifest_sha, "plan_sha256": sha256(plan_raw), "batch_number": result["batch_number"],
                  "cell_ids": cells, "strict_schema_sha256": sha256(strict_raw),
                  "source_manifest_sha256": manifest["source_manifest_sha256"], "automatic_resend_authorized": False}
    raw = _write_new(_projection_path(batch), projection)
    return {**result, "serialized126_projection_sha256": sha256(raw), "provider_calls_made": 0, "process_launches": 0}


def review_material(*, campaign_root: Path, batch_number: int) -> dict[str, Any]:
    projection, raw = _read(_projection_path(_batch(Path(campaign_root).resolve(), batch_number)), "serialized126 projection")
    return {"format_version": 1, "kind": "wpb_sol_serialized126_successor_dispatch_review_v1",
            "decision": "approved_wpb_sol_serialized126_successor_dispatch", "projection_sha256": sha256(raw),
            "successor_manifest_sha256": projection["successor_manifest_sha256"], "batch_number": batch_number,
            "cell_ids": projection["cell_ids"], "strict_schema_sha256": projection["strict_schema_sha256"],
            "source_manifest_sha256": projection["source_manifest_sha256"], "reviewed_at": None, "expires_at": None}


def _review(path: Path, expected: str, root: Path, number: int, *, require_unexpired: bool) -> str:
    legacy = _load_legacy(); pending = legacy._load_pending(); value, raw = legacy._read(path, "serialized126 review"); required = review_material(campaign_root=root, batch_number=number)
    _require(sha256(raw) == expected and set(value) == set(required)
             and all(value[key] == item for key, item in required.items() if key not in {"reviewed_at", "expires_at"})
             and pending._time(value["reviewed_at"], "reviewed_at") < pending._time(value["expires_at"], "expires_at"),
             "serialized126 review differs")
    if require_unexpired:
        _require(__import__("datetime").datetime.now(__import__("datetime").timezone.utc) < pending._time(value["expires_at"], "expires_at"),
                 "serialized126 review expired")
    return sha256(raw)


def _bind_review(root: Path, number: int, review_path: Path, expected: str) -> None:
    projection_raw = _projection_path(_batch(root, number)).read_bytes(); digest = _review(review_path, expected, root, number, require_unexpired=True)
    _write_new(_binding_path(_batch(root, number)), {"format_version": 1, "kind": "wpb_sol_serialized126_successor_review_binding_v1",
               "projection_sha256": sha256(projection_raw), "review": {"path": str(review_path.resolve()), "sha256": digest},
               "automatic_resend_authorized": False})


def _binding(root: Path, number: int, *, require_unexpired: bool) -> dict[str, Any]:
    value, _raw = _read(_binding_path(_batch(root, number)), "serialized126 review binding")
    _require(value.get("projection_sha256") == sha256(_projection_path(_batch(root, number)).read_bytes())
             and isinstance(value.get("review"), dict) and value.get("automatic_resend_authorized") is False,
             "serialized126 review binding differs")
    _review(Path(value["review"]["path"]), value["review"]["sha256"], root, number, require_unexpired=require_unexpired)
    return value


def _safe_failure(error: BaseException) -> dict[str, Any]:
    trace = error.__traceback__
    while trace is not None and trace.tb_next is not None:
        trace = trace.tb_next
    return {"error_type": type(error).__name__, "source_function": trace.tb_frame.f_code.co_name if trace else None,
            "source_line": trace.tb_lineno if trace else None, "cause_type": type(error.__cause__).__name__ if error.__cause__ else None}


def dispatch_batch(*, successor_review_path: Path, expected_successor_review_sha256: str, **kwargs: Any) -> list[dict[str, Any]]:
    root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]; manifest, _manifest_sha = _manifest(root)
    legacy, strict, _state = _configured_legacy({}); _install_frozen_verifier(legacy, manifest)
    _bind_review(root, number, Path(successor_review_path), expected_successor_review_sha256)
    factory = _broker_factory(legacy, strict, manifest, kwargs.pop("broker_factory", None)); lock = threading.Lock(); original_frozen = legacy._frozen

    def frozen() -> ModuleType:
        module = original_frozen(); wave = module._fail_fast_wave
        def observed(*, rows: Any, output_root: Path, endpoint: str, run: Any) -> list[dict[str, Any]]:
            def guarded(row: dict[str, Any]) -> dict[str, Any]:
                try:
                    return run(row)
                except BaseException as error:
                    with lock:
                        path = _batch(root, number) / "serialized126-first-worker-failure.json"
                        if not path.exists():
                            _write_new(path, {"format_version": 1, "kind": "wpb_sol_serialized126_successor_first_worker_failure_v1",
                                               "cell_id": row.get("cell_id"), "failure": _safe_failure(error),
                                               "source_manifest_sha256": manifest["source_manifest_sha256"], "automatic_resend_authorized": False})
                    raise
            return wave(rows=rows, output_root=output_root, endpoint=endpoint, run=guarded)
        module._fail_fast_wave = observed
        return module

    legacy._frozen = frozen; base = kwargs.get("call_codex")
    def call(**call_kwargs: Any) -> tuple[str, dict[str, Any]]:
        _binding(root, number, require_unexpired=True); _source_guard(manifest["source_manifest"])
        before = call_kwargs.get("before_provider_attempt"); _require(callable(before), "frozen Sol runtime omitted precontact gate")
        def guarded() -> None:
            _binding(root, number, require_unexpired=True); _source_guard(manifest["source_manifest"]); before()
        target = base or legacy._current_call_codex(legacy._frozen()._sol_runtime(legacy._resolution(legacy._frozen(), Path(kwargs["freeze_root"])))[1], receipt_root=_batch(root, number) / "sol-process-receipts")
        return target(**(call_kwargs | {"before_provider_attempt": guarded}))
    return legacy.dispatch_batch(**(kwargs | {"broker_factory": factory, "call_codex": call}))


def settle_batch(**kwargs: Any) -> dict[str, Any]:
    root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]; manifest, _manifest_sha = _manifest(root); _binding(root, number, require_unexpired=False)
    legacy, _strict, _state = _configured_legacy({}); _install_frozen_verifier(legacy, manifest)
    return legacy.settle_batch(**kwargs)


def report(*, campaign_root: Path, reconciliation_path: Path, expected_reconciliation_sha256: str, **kwargs: Any) -> dict[str, Any]:
    """Join the three immutable admissions with 126 settled prospective cells."""
    root = Path(campaign_root).resolve(); manifest, manifest_sha = _manifest(root)
    reconciliation, _raw = _verify_reconciliation(Path(reconciliation_path), expected_reconciliation_sha256, root)
    old = _load_legacy(); pending = old._load_pending(); strict = pending._load_strict(); shared: dict[str, Any] = {}
    full_legacy, _bridge = strict._configured_legacy(); _load_serializer().install_on_legacy(full_legacy, shared)
    verifier_path = full_legacy._verifier_path(kwargs.get("freeze_verifier_path")); full_frozen = full_legacy._frozen()
    full = full_legacy._resolution(full_frozen, Path(kwargs["freeze_root"]))
    _require(len(full["rows"]) == 129 and {str(row["cell_id"]) for row in full["rows"]} >= set(PREFIX), "full WPB schedule differs")
    context = full_legacy._full_freeze(Path(kwargs["freeze_path"]), kwargs["expected_freeze_sha256"],
                                       kwargs["expected_freeze_verifier_sha256"], verifier_path=verifier_path,
                                       mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False), replay_native=True)
    _require(context["schedule_sha256"] == full["schedule_sha256"], "full selection schedule differs")
    legacy, _strict, _state = _configured_legacy(shared); _install_frozen_verifier(legacy, manifest)
    filtered = legacy._resolution(legacy._frozen(), Path(kwargs["freeze_root"]))
    _require(len(filtered["rows"]) == 126 and not set(PREFIX) & {str(row["cell_id"]) for row in filtered["rows"]},
             "serialized126 schedule differs")
    contract = legacy._freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
    _campaign, campaign_sha = legacy._campaign(root, filtered, context, kwargs["expected_freeze_sha256"],
                                                kwargs["expected_freeze_verifier_sha256"], contract)
    numbers = tuple(range(1, 14)); _require(tuple(legacy._batch_numbers(root)) == numbers and not (root / "stopped.json").exists(),
                                             "serialized126 successor is incomplete or stopped")
    prior_value, _prior_raw = pending._read(Path(reconciliation["prior_reconciliation"]["path"]), "partial predecessor reconciliation")
    strict_descriptor = prior_value.get("prior_reconciliation")
    _require(isinstance(strict_descriptor, dict) and set(strict_descriptor) == {"path", "sha256"}, "strict predecessor descriptor differs")
    pending._exact(Path(strict_descriptor["path"]), strict_descriptor["sha256"], "strict predecessor reconciliation")
    strict_value = pending._reconciliation(Path(strict_descriptor["path"])); strict_root = Path(strict_value["campaign_root"]).resolve()
    pending._verify_predecessor(strict_value, strict_root); partial_root = Path(prior_value["campaign_root"]).resolve()
    partial_inventory = prior_value.get("immutable_inventory")
    _require(prior_value.get("kind") == "wpb_sol_partial_successor_reconciliation_v1"
             and prior_value.get("completed_cells") == list(PREFIX[:2]) and prior_value.get("remaining_logical_cells") == 127
             and prior_value.get("automatic_resend_authorized") is False and isinstance(partial_inventory, dict)
             and prior_value.get("immutable_inventory_sha256") == pending.sha256(partial_inventory), "partial predecessor reconciliation differs")
    for relative, digest in partial_inventory.items():
        _require(isinstance(relative, str) and isinstance(digest, str), "partial predecessor inventory is malformed")
        pending._exact(partial_root / relative.replace("/", "\\"), digest, "partial predecessor immutable evidence")
    current_root = Path(reconciliation["campaign_root"]).resolve()
    lifecycle, runtime, _rows = full_frozen._sol_runtime(full); v4 = lifecycle.sol_v4(); by_id = {str(row["cell_id"]): row for row in full["rows"]}
    strict_plan, _ = pending._read(strict_root / "batches" / "0001" / "plan.json", "strict predecessor plan")
    partial_plan, _ = pending._read(partial_root / "batches" / "0001" / "plan.json", "partial predecessor plan")
    current_plan, _ = pending._read(current_root / "batches" / "0001" / "plan.json", "serialized126 predecessor plan")
    partial_settlement, _ = pending._read(Path(prior_value["settlement"]["path"]), "partial predecessor settlement")
    settlement, settlement_raw = pending._read(Path(reconciliation["settlement"]["path"]), "serialized126 predecessor settlement")
    _require(pending.sha256(settlement_raw) == reconciliation["settlement"]["sha256"] and settlement.get("status") == "terminal_or_ambiguous",
             "serialized126 predecessor settlement differs")
    partial_cells = {str(item.get("cell_id")): item for item in partial_settlement.get("cells", []) if isinstance(item, dict)}
    current_cells = {str(item.get("cell_id")): item for item in settlement.get("cells", []) if isinstance(item, dict)}
    identities: set[tuple[str, str]] = set(); measurements: list[dict[str, Any]] = []; bindings: dict[str, dict[str, Any]] = {}

    def admit(cell_id: str) -> None:
        plan, base = ((strict_plan, strict_root) if cell_id == PREFIX[0] else
                      (partial_plan, partial_root) if cell_id == PREFIX[1] else (current_plan, current_root))
        row = by_id.get(cell_id); _require(row is not None and cell_id in plan.get("cell_ids", []), "preserved prefix plan differs")
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, base / "batches" / "0001" / "execution" / cell_id,
                                                   plan["authorization_acknowledgement_sha256"])
        identity = admitted["identity"]; key = (str(identity.get("thread_id")), str(identity.get("session_id")))
        _require(all(key) and key not in identities, "duplicate preserved native identity"); identities.add(key)
        if cell_id == PREFIX[1]:
            _require(partial_cells.get(cell_id, {}).get("state") == "completed", "0068 settlement differs")
        if cell_id == PREFIX[2]:
            _require(current_cells.get(cell_id, {}).get("state") == "completed"
                     and pending.sha256(admitted["receipt"]) == reconciliation["0015_execution_receipt"]["sha256"], "0015 admission differs")
        answer = full_frozen._valid_response(full["core"], admitted["answer"])
        measurements.append({"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                             "measurement_provenance": {"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                                        "parsed_response_sha256": full_frozen.sha256(answer)}, "response": answer})
        bindings[cell_id] = {"preserved_serialized126_reconciliation_sha256": expected_reconciliation_sha256,
                             "execution_receipt_sha256": pending.sha256(admitted["receipt"]), "identity_sha256": pending.sha256(identity),
                             "effective_settings_sha256": full_frozen.sha256(admitted["settings"])}

    for cell_id in PREFIX:
        admit(cell_id)
    epochs: list[dict[str, Any]] = []
    for number in numbers:
        _binding(root, number, require_unexpired=False)
        plan, plan_sha = legacy._plan(root, number, campaign_sha, verifier_path=verifier_path, mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
        legacy._cheap_freeze(plan, Path(kwargs["freeze_path"]), kwargs["expected_freeze_sha256"], kwargs["expected_freeze_verifier_sha256"],
                             verifier_path=verifier_path, mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
        settled, settled_sha = legacy._settlement(root, number, campaign_sha)
        _require(settled.get("status") == "completed" and settled.get("plan_sha256") == plan_sha
                 and len(settled.get("cells", [])) == len(plan["cell_ids"]), "serialized126 settlement is incomplete")
        rows = legacy._batch_rows(filtered, plan); legacy._verify_prepared_bindings(_batch(root, number), rows, plan)
        entries = lifecycle._output_inventory(_batch(root, number) / "execution", rows)
        settled_cells = {str(item.get("cell_id")): item for item in settled["cells"] if isinstance(item, dict)}
        for row in rows:
            cell_id = str(row["cell_id"]); record = settled_cells.get(cell_id)
            _require(isinstance(record, dict) and record.get("state") == "completed", "unsettled serialized126 cell")
            admitted = lifecycle._admit_completed_cell(runtime, v4, row, entries[cell_id], plan["authorization_acknowledgement_sha256"])
            _require(admitted["route"] == plan["route"] and admitted["route_evidence"] == plan["route_evidence"], "serialized126 route differs")
            identity = admitted["identity"]; key = (str(identity.get("thread_id")), str(identity.get("session_id")))
            _require(all(key) and key not in identities, "duplicate serialized126 native identity"); identities.add(key)
            answer = full_frozen._valid_response(full["core"], admitted["answer"])
            _require(record.get("execution_receipt_sha256") == pending.sha256(admitted["receipt"])
                     and record.get("raw_response_sha256") == pending.sha256(admitted["final"])
                     and record.get("identity_sha256") == pending.sha256(identity), "serialized126 settlement binding drifted")
            measurements.append({"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                 "measurement_provenance": {"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                                            "parsed_response_sha256": full_frozen.sha256(answer)}, "response": answer})
            bindings[cell_id] = {"batch_number": number, "route_sha256": plan["route_sha256"], "route_evidence_sha256": plan["route_evidence_sha256"],
                                 "review_sha256": plan["review_sha256"], "execution_receipt_sha256": pending.sha256(admitted["receipt"]),
                                 "identity_sha256": pending.sha256(identity), "effective_settings_sha256": full_frozen.sha256(admitted["settings"]),
                                 "prepared_source_bindings_sha256": plan["prepared_source_bindings_sha256"]}
        epochs.append({"batch_number": number, "route_sha256": plan["route_sha256"], "route_evidence_sha256": plan["route_evidence_sha256"],
                       "review_sha256": plan["review_sha256"], "settlement_sha256": settled_sha})
    _require(len(measurements) == 129 and {item["cell_id"] for item in measurements} == set(by_id) and len(identities) == 129,
             "full 129-cell serialized126 replay is incomplete")
    analysis = full["core"].analyze(Path(kwargs["freeze_root"]), measurements, context["selected_profile"])
    return {"format_version": 1, "kind": "wpb_sol_serialized126_successor_replayed_report_v1", "status": "complete_batched_sol_campaign",
            "authority": "development_screening_only", "confirmation": "closed", "measurement_count": 129,
            "preserved_completed_cells": list(PREFIX), "new_measurement_count": 126, "successor_manifest_sha256": manifest_sha,
            "serialized126_reconciliation_sha256": expected_reconciliation_sha256, "full_selection_verification": "native_replay",
            "route_epochs": epochs, "native_receipt_bindings": bindings, "analysis": analysis}
