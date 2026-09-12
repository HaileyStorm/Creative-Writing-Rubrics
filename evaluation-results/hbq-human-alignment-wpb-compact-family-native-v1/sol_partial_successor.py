"""Fresh 127-cell successor after immutable WPB admissions 0052 and 0068."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
PENDING = HERE / "sol_pending_continuation.py"
PENDING_SHA256 = "472f341be2a92cf36178d015957ab8fa44d7b2dcf0aa96422d12a183f0356d48"
PREFIX = ("wpb-pair-wpb-en-0052", "wpb-pair-wpb-en-0068")


def _load_pending() -> ModuleType:
    raw = PENDING.read_bytes()
    if __import__("hashlib").sha256(raw).hexdigest() != PENDING_SHA256:
        raise ValueError("pending continuation source drifted")
    module = ModuleType("_wpb_partial_successor_pending"); module.__file__ = str(PENDING)
    sys.modules[module.__name__] = module
    try: exec(compile(raw, str(PENDING), "exec"), module.__dict__)  # noqa: S102
    finally: sys.modules.pop(module.__name__, None)
    if PENDING.read_bytes() != raw: raise ValueError("pending continuation source changed during load")
    return module


def canonical(value: Any) -> bytes: return _load_pending().canonical(value)
def sha256(value: Any) -> str: return _load_pending().sha256(value)
def _read(path: Path, label: str): return _load_pending()._read(path, label)
def _write_new(path: Path, value: Any): return _load_pending()._write_new(path, value)
def _require(condition: bool, message: str) -> None:
    if not condition: raise ValueError(message)


def source_manifest() -> dict[str, Any]:
    pending = _load_pending(); own = Path(__file__).resolve().read_bytes()
    return {"format_version": 1, "kind": "wpb_sol_partial_successor_source_manifest_v1",
            "successor": {"path": str(Path(__file__).resolve()), "sha256": sha256(own)},
            "pending": {"path": str(PENDING), "sha256": PENDING_SHA256}, "pending_source_manifest": pending.source_manifest()}


def _filtered(resolution: dict[str, Any]) -> dict[str, Any]:
    rows = tuple(row for row in resolution["rows"] if row["cell_id"] not in PREFIX)
    _require(len(resolution["rows"]) == 128 and len(rows) == 127 and PREFIX[0] not in {row["cell_id"] for row in resolution["rows"]}
             and [row["cell_id"] for row in resolution["rows"] if row["cell_id"] == PREFIX[1]] == [PREFIX[1]], "frozen two-cell prefix differs")
    return {**resolution, "rows": rows, "payloads": {row["cell_id"]: resolution["payloads"][row["cell_id"]] for row in rows}}


def _configured_legacy() -> tuple[ModuleType, ModuleType]:
    pending = _load_pending(); legacy, strict = pending._configured_legacy(); prior = legacy._resolution
    def resolution(frozen: ModuleType, freeze_root: Path) -> dict[str, Any]: return _filtered(prior(frozen, freeze_root))
    legacy._resolution = resolution
    return legacy, strict


def _manifest_path(root: Path) -> Path: return root / "partial-successor-manifest.json"
def _batch(root: Path, number: int) -> Path: return root / "batches" / f"{number:04d}"
def _projection_path(batch: Path) -> Path: return batch / "partial-successor-projection.json"
def _binding_path(batch: Path) -> Path: return batch / "partial-successor-review-binding.json"


def _manifest(root: Path) -> tuple[dict[str, Any], str]:
    pending = _load_pending(); value, raw = pending._read(_manifest_path(root), "partial successor manifest")
    campaign, campaign_raw = pending._read(root / "campaign.json", "partial successor campaign")
    source = source_manifest()
    _require(value.get("format_version") == 1 and value.get("kind") == "wpb_sol_partial_successor_v1"
             and value.get("campaign") == {"path": str((root / "campaign.json").resolve()), "sha256": pending.sha256(campaign_raw)}
             and value.get("source_manifest") == source and value.get("source_manifest_sha256") == pending.sha256(source)
             and value.get("excluded_completed_cells") == list(PREFIX) and value.get("remaining_logical_cells") == 127
             and value.get("automatic_resend_authorized") is False and len(campaign.get("cells", [])) == 127, "partial successor manifest differs")
    return value, pending.sha256(raw)


def create_campaign(*, campaign_root: Path, partial_reconciliation_path: Path, expected_partial_reconciliation_sha256: str, **kwargs: Any) -> dict[str, Any]:
    pending = _load_pending(); root = Path(campaign_root).resolve(); _require(not root.exists(), "fresh partial successor root required")
    reconciliation, reconciliation_raw = pending._read(Path(partial_reconciliation_path), "partial reconciliation")
    inventory = reconciliation.get("immutable_inventory")
    _require(pending.sha256(reconciliation_raw) == expected_partial_reconciliation_sha256
             and reconciliation.get("kind") == "wpb_sol_partial_successor_reconciliation_v1"
             and reconciliation.get("completed_cells") == list(PREFIX) and reconciliation.get("remaining_logical_cells") == 127
             and reconciliation.get("automatic_resend_authorized") is False and isinstance(inventory, dict)
             and reconciliation.get("immutable_inventory_sha256") == pending.sha256(inventory)
             and isinstance(reconciliation.get("prior_reconciliation"), dict)
             and isinstance(reconciliation.get("settlement"), dict)
             and isinstance(reconciliation.get("0068_execution_receipt"), dict), "partial reconciliation differs")
    prior_root = Path(reconciliation.get("campaign_root", "")).resolve()
    _require(prior_root != root and prior_root.is_dir(), "partial reconciliation campaign root differs")
    for relative, digest in inventory.items():
        pending._exact(prior_root / relative.replace("/", "\\"), digest, "partial successor immutable evidence")
    for key in ("prior_reconciliation", "settlement", "0068_execution_receipt"):
        descriptor = reconciliation[key]
        _require(set(descriptor) == {"path", "sha256"}, "partial reconciliation descriptor differs")
        pending._exact(Path(descriptor["path"]), descriptor["sha256"], "partial reconciliation descriptor")
    source = source_manifest(); legacy, _strict = _configured_legacy(); captured: dict[str, Any] = {}; original = legacy._full_freeze
    def freeze(*args: Any, **inner: Any) -> dict[str, Any]:
        result = original(*args, **inner)
        if inner.get("replay_native") is True: captured["context"] = result
        return result
    legacy._full_freeze = freeze
    result = legacy.create_campaign(campaign_root=root, **kwargs)
    campaign, campaign_raw = pending._read(root / "campaign.json", "partial successor campaign"); context = captured.get("context")
    _require(isinstance(context, dict) and context["schedule_sha256"] == campaign["schedule_sha256"], "full selection verification is missing")
    manifest = {"format_version": 1, "kind": "wpb_sol_partial_successor_v1", "campaign": {"path": str((root / "campaign.json").resolve()), "sha256": pending.sha256(campaign_raw)},
                "partial_reconciliation": {"path": str(Path(partial_reconciliation_path).resolve()), "sha256": expected_partial_reconciliation_sha256},
                "source_manifest": source, "source_manifest_sha256": pending.sha256(source), "selection_context_sha256": pending.sha256(context),
                "excluded_completed_cells": list(PREFIX), "remaining_logical_cells": 127, "automatic_resend_authorized": False}
    raw = pending._write_new(_manifest_path(root), manifest)
    return {**result, "logical_cells": 127, "partial_successor_manifest_sha256": pending.sha256(raw), "provider_calls_made": 0, "process_launches": 0}


def prepare_next_batch(**kwargs: Any) -> dict[str, Any]:
    pending = _load_pending(); root = Path(kwargs["campaign_root"]).resolve(); manifest, manifest_sha = _manifest(root); legacy, strict = _configured_legacy()
    pending._install_frozen_verifier(legacy, source=manifest["source_manifest"]["pending_source_manifest"],
                                    selection_context_sha256=manifest["selection_context_sha256"])
    source = manifest["source_manifest"]
    supplied_factory = kwargs.pop("broker_factory", None)
    _require(supplied_factory is None or callable(supplied_factory), "partial successor broker factory differs")
    bridge = strict._load_bridge()
    factory = supplied_factory or bridge.broker_factory(source["pending_source_manifest"]["strict_source_manifest"]["broker_source_manifest"],
                                                        before_create=lambda: _require(source_manifest() == source, "partial successor source drifted"))
    result = legacy.prepare_next_batch(**(kwargs | {"broker_factory": factory})); batch = _batch(root, result["batch_number"]); plan, plan_raw = pending._read(batch / "plan.json", "partial plan")
    cells = plan["cell_ids"]; _require(not set(cells) & set(PREFIX), "completed prefix was prepared")
    schemas = [pending._read(batch / "execution" / cell / "response-schema.json", "schema")[0] for cell in cells]
    strict_raw = pending.canonical(strict.strict_native_schema(schemas[0]))
    pending._write_new(batch / "strict-native-schema.json", strict_raw)
    projection = {"format_version": 1, "kind": "wpb_sol_partial_successor_projection_v1", "manifest_sha256": manifest_sha,
                  "plan_sha256": pending.sha256(plan_raw), "batch_number": result["batch_number"], "cell_ids": cells,
                  "strict_schema_sha256": pending.sha256(strict_raw), "source_manifest_sha256": manifest["source_manifest_sha256"], "automatic_resend_authorized": False}
    raw = pending._write_new(_projection_path(batch), projection)
    return {**result, "partial_successor_projection_sha256": pending.sha256(raw), "provider_calls_made": 0, "process_launches": 0}


def review_material(*, campaign_root: Path, batch_number: int) -> dict[str, Any]:
    pending = _load_pending(); value, raw = pending._read(_projection_path(_batch(Path(campaign_root), batch_number)), "partial projection")
    return {"format_version": 1, "kind": "wpb_sol_partial_successor_review_v1", "decision": "approved_wpb_sol_partial_successor_dispatch",
            "projection_sha256": pending.sha256(raw), "batch_number": batch_number, "cell_ids": value["cell_ids"],
            "manifest_sha256": value["manifest_sha256"], "automatic_resend_authorized": False, "reviewed_at": None, "expires_at": None}


def _review(path: Path, expected_sha256: str, root: Path, number: int, *, require_unexpired: bool) -> str:
    pending = _load_pending(); value, raw = pending._read(path, "partial successor review"); expected = review_material(campaign_root=root, batch_number=number)
    _require(pending.sha256(raw) == expected_sha256 and set(value) == set(expected)
             and all(value[key] == item for key, item in expected.items() if key not in {"reviewed_at", "expires_at"})
             and pending._time(value["reviewed_at"], "reviewed_at") < pending._time(value["expires_at"], "expires_at"), "partial successor review differs")
    if require_unexpired: _require(__import__("datetime").datetime.now(__import__("datetime").timezone.utc) < pending._time(value["expires_at"], "expires_at"), "partial successor review expired")
    return pending.sha256(raw)


def _binding(root: Path, number: int, *, require_unexpired: bool) -> dict[str, Any]:
    pending = _load_pending(); value, _raw = pending._read(_binding_path(_batch(root, number)), "partial successor review binding")
    _require(value.get("projection_sha256") == pending.sha256((_projection_path(_batch(root, number))).read_bytes())
             and isinstance(value.get("review"), dict) and value.get("automatic_resend_authorized") is False, "partial successor binding differs")
    _review(Path(value["review"]["path"]), value["review"]["sha256"], root, number, require_unexpired=require_unexpired)
    return value


def _bind_review(root: Path, number: int, review_path: Path, expected_review_sha256: str) -> None:
    pending = _load_pending(); projection_raw = (_projection_path(_batch(root, number))).read_bytes()
    digest = _review(review_path, expected_review_sha256, root, number, require_unexpired=True)
    pending._write_new(_binding_path(_batch(root, number)), {"format_version": 1, "kind": "wpb_sol_partial_successor_review_binding_v1",
                        "projection_sha256": pending.sha256(projection_raw), "review": {"path": str(review_path.resolve()), "sha256": digest},
                        "automatic_resend_authorized": False})


def _safe_failure(error: BaseException) -> dict[str, Any]:
    trace = error.__traceback__
    while trace is not None and trace.tb_next is not None: trace = trace.tb_next
    return {"error_type": type(error).__name__, "source_function": trace.tb_frame.f_code.co_name if trace else None,
            "source_line": trace.tb_lineno if trace else None, "cause_type": type(error.__cause__).__name__ if error.__cause__ else None}


def dispatch_batch(*, successor_review_path: Path, expected_successor_review_sha256: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Delegate to the pinned strict lifecycle while preserving the first worker failure."""
    pending = _load_pending(); root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]
    manifest, _manifest_sha = _manifest(root); _bind_review(root, number, Path(successor_review_path), expected_successor_review_sha256)
    legacy, _strict = _configured_legacy(); lock = threading.Lock(); original_frozen = legacy._frozen
    pending._install_frozen_verifier(legacy, source=manifest["source_manifest"]["pending_source_manifest"],
                                    selection_context_sha256=manifest["selection_context_sha256"])
    source = manifest["source_manifest"]
    supplied_factory = kwargs.pop("broker_factory", None)
    _require(supplied_factory is None or callable(supplied_factory), "partial successor broker factory differs")
    bridge = _strict._load_bridge()
    factory = supplied_factory or bridge.broker_factory(source["pending_source_manifest"]["strict_source_manifest"]["broker_source_manifest"],
                                                        before_create=lambda: _require(source_manifest() == source, "partial successor source drifted"))
    frozen_runtime = legacy._frozen()
    resolution = legacy._resolution(frozen_runtime, Path(kwargs["freeze_root"]))
    _lifecycle, runtime, _rows = frozen_runtime._sol_runtime(resolution)
    base_call = kwargs.get("call_codex") or legacy._current_call_codex(runtime, receipt_root=_batch(root, number) / "sol-process-receipts")

    def guarded_call(**call_kwargs: Any) -> tuple[str, dict[str, Any]]:
        _binding(root, number, require_unexpired=True)
        _require(source_manifest() == source, "partial successor source drifted")
        before = call_kwargs.get("before_provider_attempt")
        _require(callable(before), "frozen Sol runtime omitted precontact gate")

        def guarded() -> None:
            _binding(root, number, require_unexpired=True)
            _require(source_manifest() == source, "partial successor source drifted")
            before()

        return base_call(**(call_kwargs | {"before_provider_attempt": guarded}))
    def frozen() -> ModuleType:
        module = original_frozen(); original_wave = module._fail_fast_wave
        def wave(*, rows: Any, output_root: Path, endpoint: str, run: Any) -> list[dict[str, Any]]:
            def observed(row: dict[str, Any]) -> dict[str, Any]:
                try: return run(row)
                except BaseException as error:
                    with lock:
                        failure = _batch(root, number) / "first-worker-failure.json"
                        if not failure.exists():
                            try: pending._write_new(failure, {"format_version": 1, "kind": "wpb_sol_partial_successor_first_worker_failure_v1",
                                                              "cell_id": row.get("cell_id"), "failure": _safe_failure(error),
                                                              "source_manifest_sha256": manifest["source_manifest_sha256"], "automatic_resend_authorized": False})
                            except FileExistsError: pass
                    raise
            return original_wave(rows=rows, output_root=output_root, endpoint=endpoint, run=observed)
        module._fail_fast_wave = wave; return module
    legacy._frozen = frozen
    return legacy.dispatch_batch(**(kwargs | {"broker_factory": factory, "call_codex": guarded_call}))


def settle_batch(**kwargs: Any) -> dict[str, Any]:
    root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]; manifest, _manifest_sha = _manifest(root); _binding(root, number, require_unexpired=False)
    pending = _load_pending(); legacy, _strict = _configured_legacy()
    pending._install_frozen_verifier(legacy, source=manifest["source_manifest"]["pending_source_manifest"],
                                    selection_context_sha256=manifest["selection_context_sha256"])
    return legacy.settle_batch(**kwargs)


def report(*, campaign_root: Path, partial_reconciliation_path: Path,
           expected_partial_reconciliation_sha256: str, **kwargs: Any) -> dict[str, Any]:
    """Join the two immutable admissions with 127 fully settled successor cells."""
    pending = _load_pending(); root = Path(campaign_root).resolve(); manifest, manifest_sha = _manifest(root)
    reconciliation, reconciliation_raw = pending._read(Path(partial_reconciliation_path), "partial reconciliation")
    inventory = reconciliation.get("immutable_inventory")
    _require(pending.sha256(reconciliation_raw) == expected_partial_reconciliation_sha256
             and reconciliation.get("format_version") == 1
             and reconciliation.get("kind") == "wpb_sol_partial_successor_reconciliation_v1"
             and reconciliation.get("completed_cells") == list(PREFIX)
             and reconciliation.get("remaining_logical_cells") == 127
             and reconciliation.get("automatic_resend_authorized") is False
             and reconciliation.get("source_sha256") == PENDING_SHA256
             and reconciliation.get("source_manifest_sha256") == pending.sha256(pending.source_manifest())
             and isinstance(inventory, dict)
             and reconciliation.get("immutable_inventory_sha256") == pending.sha256(inventory),
             "partial reconciliation differs")
    predecessor = Path(reconciliation.get("campaign_root", "")).resolve()
    _require(predecessor.is_dir() and predecessor != root, "partial reconciliation campaign root differs")
    for relative, digest in inventory.items():
        _require(isinstance(relative, str) and isinstance(digest, str), "partial reconciliation inventory is malformed")
        pending._exact(predecessor / relative.replace("/", "\\\\"), digest, "partial successor immutable evidence")
    for key in ("prior_reconciliation", "settlement", "0068_execution_receipt"):
        descriptor = reconciliation.get(key)
        _require(isinstance(descriptor, dict) and set(descriptor) == {"path", "sha256"},
                 "partial reconciliation descriptor differs")
        pending._exact(Path(descriptor["path"]), descriptor["sha256"], "partial reconciliation descriptor")

    prior = reconciliation["prior_reconciliation"]
    prior_value, _prior_raw = pending._read(Path(prior["path"]), "prior strict reconciliation")
    pending._reconciliation(Path(prior["path"]))
    strict_predecessor = Path(prior_value["campaign_root"]).resolve()
    pending._verify_predecessor(prior_value, strict_predecessor)
    strict = pending._load_strict(); full_legacy, _bridge = strict._configured_legacy()
    pending_source = manifest["source_manifest"]["pending_source_manifest"]
    pending._install_frozen_verifier(full_legacy, source=pending_source,
                                    selection_context_sha256=manifest["selection_context_sha256"])
    verifier_path = full_legacy._verifier_path(kwargs.get("freeze_verifier_path"))
    full_frozen = full_legacy._frozen(); full_resolution = full_legacy._resolution(full_frozen, Path(kwargs["freeze_root"]))
    _require(len(full_resolution["rows"]) == 129 and {row["cell_id"] for row in full_resolution["rows"]} >= set(PREFIX),
             "full WPB schedule differs")
    context = full_legacy._full_freeze(Path(kwargs["freeze_path"]), kwargs["expected_freeze_sha256"],
                                       kwargs["expected_freeze_verifier_sha256"], verifier_path=verifier_path,
                                       mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False), replay_native=True)
    _require(context["schedule_sha256"] == full_resolution["schedule_sha256"], "full selection schedule differs")

    legacy, _strict = _configured_legacy(); filtered = legacy._resolution(legacy._frozen(), Path(kwargs["freeze_root"]))
    _require(len(filtered["rows"]) == 127 and not ({row["cell_id"] for row in filtered["rows"]} & set(PREFIX)),
             "partial successor schedule differs")
    freeze_contract = legacy._freeze_contract(context, verifier_path=verifier_path,
                                               mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
    _campaign, campaign_sha = legacy._campaign(root, filtered, context, kwargs["expected_freeze_sha256"],
                                                kwargs["expected_freeze_verifier_sha256"], freeze_contract)
    numbers = tuple(range(1, 14))
    _require(tuple(legacy._batch_numbers(root)) == numbers and not (root / "stopped.json").exists(),
             "partial successor is incomplete or stopped")
    lifecycle, runtime, _rows = full_frozen._sol_runtime(full_resolution); v4 = lifecycle.sol_v4()
    by_id = {str(row["cell_id"]): row for row in full_resolution["rows"]}
    strict_plan, _strict_plan_raw = pending._read(strict_predecessor / "batches" / "0001" / "plan.json", "strict predecessor plan")
    partial_plan, _partial_plan_raw = pending._read(predecessor / "batches" / "0001" / "plan.json", "partial predecessor plan")
    settlement, settlement_raw = pending._read(Path(reconciliation["settlement"]["path"]), "partial predecessor settlement")
    _require(pending.sha256(settlement_raw) == reconciliation["settlement"]["sha256"]
             and settlement.get("status") == "terminal_or_ambiguous", "partial predecessor settlement differs")
    prior_cells = {str(item.get("cell_id")): item for item in settlement.get("cells", []) if isinstance(item, dict)}
    identities: set[tuple[str, str]] = set(); measurements: list[dict[str, Any]] = []; bindings: dict[str, dict[str, Any]] = {}

    def admit_preserved(cell_id: str) -> None:
        row = by_id.get(cell_id)
        admission_root, plan = ((strict_predecessor, strict_plan) if cell_id == PREFIX[0] else (predecessor, partial_plan))
        _require(row is not None and cell_id in plan.get("cell_ids", []), "partial predecessor cell differs")
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, admission_root / "batches" / "0001" / "execution" / cell_id,
                                                   plan["authorization_acknowledgement_sha256"])
        identity = admitted["identity"]
        key = (str(identity.get("thread_id")), str(identity.get("session_id"))) if isinstance(identity, dict) else ("", "")
        _require(all(key) and key not in identities, "duplicate or missing preserved native identity")
        identities.add(key)
        answer = full_frozen._valid_response(full_resolution["core"], admitted["answer"])
        if cell_id == PREFIX[1]:
            record = prior_cells.get(cell_id)
            _require(isinstance(record, dict) and record.get("state") == "completed"
                     and pending.sha256(admitted["receipt"]) == reconciliation["0068_execution_receipt"]["sha256"],
                     "0068 admission differs")
        measurements.append({"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                             "measurement_provenance": {"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                                        "parsed_response_sha256": full_frozen.sha256(answer)}, "response": answer})
        bindings[cell_id] = {"preserved_partial_reconciliation_sha256": expected_partial_reconciliation_sha256,
                             "execution_receipt_sha256": pending.sha256(admitted["receipt"]), "identity_sha256": pending.sha256(identity),
                             "effective_settings_sha256": full_frozen.sha256(admitted["settings"])}

    for cell_id in PREFIX:
        admit_preserved(cell_id)
    epochs: list[dict[str, Any]] = []
    for number in numbers:
        _binding(root, number, require_unexpired=False)
        plan, plan_sha = legacy._plan(root, number, campaign_sha, verifier_path=verifier_path,
                                      mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
        legacy._cheap_freeze(plan, Path(kwargs["freeze_path"]), kwargs["expected_freeze_sha256"],
                             kwargs["expected_freeze_verifier_sha256"], verifier_path=verifier_path,
                             mixed_v5_freeze=kwargs.get("mixed_v5_freeze", False))
        settled, settled_sha = legacy._settlement(root, number, campaign_sha)
        _require(settled.get("status") == "completed" and settled.get("plan_sha256") == plan_sha
                 and len(settled.get("cells", [])) == len(plan["cell_ids"]), "partial successor settlement is incomplete")
        rows = legacy._batch_rows(filtered, plan); legacy._verify_prepared_bindings(_batch(root, number), rows, plan)
        entries = lifecycle._output_inventory(_batch(root, number) / "execution", rows)
        settled_cells = {str(item.get("cell_id")): item for item in settled["cells"] if isinstance(item, dict)}
        for row in rows:
            cell_id = str(row["cell_id"]); record = settled_cells.get(cell_id)
            _require(isinstance(record, dict) and record.get("state") == "completed", "unsettled partial successor cell")
            admitted = lifecycle._admit_completed_cell(runtime, v4, row, entries[cell_id], plan["authorization_acknowledgement_sha256"])
            _require(admitted["route"] == plan["route"] and admitted["route_evidence"] == plan["route_evidence"], "partial successor route differs")
            identity = admitted["identity"]
            key = (str(identity.get("thread_id")), str(identity.get("session_id"))) if isinstance(identity, dict) else ("", "")
            _require(all(key) and key not in identities, "duplicate partial successor native identity")
            identities.add(key); answer = full_frozen._valid_response(full_resolution["core"], admitted["answer"])
            _require(record.get("execution_receipt_sha256") == pending.sha256(admitted["receipt"])
                     and record.get("raw_response_sha256") == pending.sha256(admitted["final"])
                     and record.get("identity_sha256") == pending.sha256(identity), "partial successor settlement binding drifted")
            measurements.append({"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                 "measurement_provenance": {"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                                            "parsed_response_sha256": full_frozen.sha256(answer)}, "response": answer})
            bindings[cell_id] = {"batch_number": number, "route_sha256": plan["route_sha256"],
                                 "route_evidence_sha256": plan["route_evidence_sha256"], "review_sha256": plan["review_sha256"],
                                 "execution_receipt_sha256": pending.sha256(admitted["receipt"]), "identity_sha256": pending.sha256(identity),
                                 "effective_settings_sha256": full_frozen.sha256(admitted["settings"]),
                                 "prepared_source_bindings_sha256": plan["prepared_source_bindings_sha256"]}
        epochs.append({"batch_number": number, "route_sha256": plan["route_sha256"], "route_evidence_sha256": plan["route_evidence_sha256"],
                       "review_sha256": plan["review_sha256"], "settlement_sha256": settled_sha})
    _require(len(measurements) == 129 and {item["cell_id"] for item in measurements} == set(by_id) and len(identities) == 129,
             "full 129-cell partial successor replay is incomplete")
    analysis = full_resolution["core"].analyze(Path(kwargs["freeze_root"]), measurements, context["selected_profile"])
    return {"format_version": 1, "kind": "wpb_sol_partial_successor_replayed_report_v1", "status": "complete_batched_sol_campaign",
            "authority": "development_screening_only", "confirmation": "closed", "measurement_count": 129,
            "preserved_completed_cells": list(PREFIX), "new_measurement_count": 127,
            "partial_successor_manifest_sha256": manifest_sha, "partial_reconciliation_sha256": expected_partial_reconciliation_sha256,
            "full_selection_verification": "native_replay", "route_epochs": epochs, "native_receipt_bindings": bindings, "analysis": analysis}
