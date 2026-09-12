"""Source-bound recovery for an interrupted, unlaunched WPB pending batch."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
PENDING = HERE / "sol_pending_continuation.py"
PENDING_SHA256 = "472f341be2a92cf36178d015957ab8fa44d7b2dcf0aa96422d12a183f0356d48"
PREPARED_FILES = frozenset({
    "authorization-acknowledgement.json", "disclosure.json", "outbound-payload.json", "prepared.json",
    "response-schema.json", "target-vector.json", "zero-charge-route-proof.json",
})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _exact(path: Path, expected: str, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"missing {label}") from error
    _require(_sha256(raw) == expected, f"{label} drifted")
    return raw


def _load_pending() -> ModuleType:
    raw = _exact(PENDING, PENDING_SHA256, "pending continuation source")
    module = ModuleType("_wpb_pending_unlaunched_source")
    module.__file__ = str(PENDING)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(PENDING), "exec"), module.__dict__)  # noqa: S102 - bytes are pinned.
    finally:
        sys.modules.pop(module.__name__, None)
    _exact(PENDING, PENDING_SHA256, "pending continuation source")
    return module


def _descriptor(path: Path, expected: str, label: str) -> dict[str, str]:
    resolved = path.resolve()
    _exact(resolved, expected, label)
    return {"path": str(resolved), "sha256": expected}


def _own_descriptor() -> dict[str, str]:
    raw = Path(__file__).resolve().read_bytes()
    return {"path": str(Path(__file__).resolve()), "sha256": _sha256(raw)}


def _unlaunched(batch: Path, cells: list[str], *, launched_cell: str | None = None) -> None:
    _require(not (batch / "settlement.json").exists() and not (batch / "local-dispatch-failure.json").exists(),
             "batch has terminal or local failure evidence")
    _require(not (batch / "sol-process-receipts").exists(), "batch has process evidence")
    _require(launched_cell is not None or not (batch / "locks").exists(), "batch has an earlier launch claim")
    execution = batch / "execution"
    try:
        entries = {entry.name: entry for entry in execution.iterdir()}
    except OSError as error:
        raise ValueError("prepared execution inventory is unavailable") from error
    _require(set(entries) == set(cells), "prepared execution inventory differs")
    forbidden = {"launch-intent.json", "execution-receipt.json", "codex-record.json", "effective-settings.json",
                 "raw-codex-events.bin", "raw-codex-final-response.bin", "raw-codex-stderr.bin", "responses"}
    for cell in cells:
        root = entries[cell]
        has_intent = launched_cell is not None and (root / "launch-intent.json").exists()
        has_response_dir = launched_cell is not None and (root / "responses").is_dir()
        expected = PREPARED_FILES | ({"launch-intent.json"} if has_intent else set()) | ({"responses"} if has_response_dir else set())
        _require(root.is_dir() and {entry.name for entry in root.iterdir()} == expected,
                 "prepared cell is no longer unlaunched")
        _require(not has_response_dir or not any((root / "responses").iterdir()), "prepared cell has response evidence")
        allowed = ({"launch-intent.json", "responses"} if launched_cell is not None else set())
        _require(not any((root / name).exists() for name in forbidden - allowed), "prepared cell has launch evidence")


def _precontact_target(batch: Path, cell_id: str) -> None:
    root = batch / "execution" / cell_id
    _require(root.is_dir(), "pre-contact cell is unavailable")
    names = {entry.name for entry in root.iterdir()}
    allowed = PREPARED_FILES | {"launch-intent.json", "responses"}
    _require(PREPARED_FILES <= names <= allowed and (root / "responses").is_dir()
             and not any((root / "responses").iterdir()), "pre-contact cell has prior response evidence")
    forbidden = {"execution-receipt.json", "codex-record.json", "effective-settings.json", "raw-codex-events.bin",
                 "raw-codex-final-response.bin", "raw-codex-stderr.bin"}
    _require(not any((root / name).exists() for name in forbidden), "pre-contact cell has terminal evidence")


def _previous_invocation(pending: ModuleType, path: Path, expected_sha256: str, *, root: Path, number: int,
                         review_path: Path, review_sha256: str) -> dict[str, str]:
    value, raw = pending._read(path, "prior interrupted invocation")
    _require(_sha256(raw) == expected_sha256 and value.get("source_sha256") == PENDING_SHA256
             and value.get("automatic_resend") is False and isinstance(value.get("kwargs"), dict),
             "prior interrupted invocation differs")
    kwargs = value["kwargs"]
    expected = {"campaign_root": str(root), "batch_number": number, "continuation_review_path": str(review_path),
                "expected_continuation_review_sha256": review_sha256, "allow_remote": True}
    _require(all(kwargs.get(key) == item for key, item in expected.items()), "prior invocation binding differs")
    return {"path": str(path.resolve()), "sha256": expected_sha256}


def _unlaunched_reconciliation(pending: ModuleType, path: Path, expected_sha256: str, *, root: Path, number: int,
                               manifest: dict[str, Any], manifest_sha256: str, plan: dict[str, Any], plan_sha256: str,
                               projection_sha256: str, binding_sha256: str, review_sha256: str) -> tuple[dict[str, Any], dict[str, str]]:
    value, raw = pending._read(path, "unlaunched restart reconciliation")
    inventory = value.get("immutable_inventory")
    _require(_sha256(raw) == expected_sha256 and value.get("kind") == "wpb_unlaunched_batch_restart_reconciliation"
             and value.get("schema_version") == 1 and value.get("automatic_resend_authorized") is False
             and value.get("resume_scope") == "only_same_ten_prepared_cells_after_independent_prelaunch_and_quiescence_review"
             and value.get("campaign_root") == str(root) and value.get("campaign_sha256") == manifest["campaign"]["sha256"]
             and value.get("pending_manifest_sha256") == manifest_sha256 and value.get("source_sha256") == PENDING_SHA256
             and value.get("source_manifest_sha256") == manifest["source_manifest_sha256"] and value.get("batch_number") == number
             and value.get("cell_ids") == plan.get("cell_ids") and value.get("completed_predecessor_excluded") == pending.ADMITTED_CELL
             and value.get("projection_sha256") == projection_sha256 and value.get("continuation_review_sha256") == review_sha256
             and value.get("existing_review_binding_sha256") == binding_sha256 and value.get("launch_intents") == 0
             and value.get("process_receipts") == 0 and value.get("execution_receipts") == 0
             and value.get("prepared_only_cells") == len(plan["cell_ids"]) and isinstance(inventory, dict)
             and value.get("immutable_inventory_sha256") == pending.sha256(inventory), "unlaunched restart reconciliation differs")
    for relative, digest in inventory.items():
        _require(isinstance(relative, str) and isinstance(digest, str), "unlaunched inventory is malformed")
        _exact(root / relative.replace("/", "\\"), digest, "unlaunched immutable evidence")
    supervisor = value.get("supervisor_invocation")
    observation = value.get("process_observation")
    _require(isinstance(supervisor, dict) and isinstance(observation, dict)
             and set(supervisor) == {"path", "sha256"} and set(observation) == {"path", "sha256"},
             "unlaunched reconciliation provenance is malformed")
    _exact(Path(supervisor["path"]), supervisor["sha256"], "prior supervisor invocation")
    _exact(Path(observation["path"]), observation["sha256"], "process observation")
    return value, {"path": str(path.resolve()), "sha256": expected_sha256}


def _outer_operation(pending: ModuleType, path: Path, expected_sha256: str, *, reconciliation: dict[str, str],
                     invocation: dict[str, str], manifest: dict[str, Any], manifest_sha256: str,
                     plan: dict[str, Any], plan_sha256: str, projection_sha256: str, review: dict[str, str]) -> dict[str, str]:
    value, raw = pending._read(path, "reviewed unlaunched resume operation")
    expected = {"format_version": 1, "kind": "wpb_sol_pending_unlaunched_resume_operation_v1",
                "companion": _own_descriptor(), "unlaunched_reconciliation": reconciliation,
                "prior_invocation": invocation, "pending_source": _descriptor(PENDING, PENDING_SHA256, "pending continuation source"),
                "pending_manifest": {"path": str((Path(manifest["campaign"]["path"]).parent / "pending-continuation-manifest.json").resolve()),
                                     "sha256": manifest_sha256}, "campaign": manifest["campaign"],
                "source_manifest_sha256": manifest["source_manifest_sha256"],
                "plan": {"path": str((Path(manifest["campaign"]["path"]).parent / "batches/0001/plan.json").resolve()), "sha256": plan_sha256},
                "projection_sha256": projection_sha256, "review": review, "cell_ids": plan["cell_ids"],
                "automatic_resend_authorized": False}
    _require(_sha256(raw) == expected_sha256 and value == expected, "reviewed unlaunched resume operation differs")
    return {"path": str(path.resolve()), "sha256": expected_sha256}


def _preflight(*, campaign_root: Path, batch_number: int, continuation_review_path: Path,
               expected_continuation_review_sha256: str, prior_invocation_path: Path,
               expected_prior_invocation_sha256: str, unlaunched_reconciliation_path: Path,
               expected_unlaunched_reconciliation_sha256: str, outer_operation_path: Path,
               expected_outer_operation_sha256: str, fresh_route_guard: Any, launched_cell: str | None = None) -> dict[str, Any]:
    _require(callable(fresh_route_guard), "fresh route guard is required")
    pending = _load_pending()
    root, number = Path(campaign_root).resolve(), batch_number
    manifest, manifest_sha256 = pending._manifest(root)
    _require(number == 1, "unlaunched resume only admits the interrupted first batch")
    batch = pending._batch(root, number)
    binding, projection = pending._binding(root, number, require_unexpired=True)
    review = binding["review"]
    review_path = Path(continuation_review_path).resolve()
    _require(review == {"path": str(review_path), "sha256": expected_continuation_review_sha256},
             "previous continuation review differs")
    pending._review(review_path, expected_continuation_review_sha256, root, number, require_unexpired=True)
    plan, plan_raw = pending._read(batch / "plan.json", "prepared pending plan")
    cells = plan.get("cell_ids")
    _require(isinstance(cells, list) and len(cells) == 10 and pending.ADMITTED_CELL not in cells,
             "unlaunched batch cells differ")
    _require(launched_cell is None or launched_cell in cells, "pre-contact cell is absent from the resumed batch")
    _unlaunched(batch, cells, launched_cell=launched_cell)
    binding_raw = _exact(batch / "pending-continuation-review-binding.json", pending.sha256(pending.canonical(binding)),
                         "existing continuation review binding")
    invocation = _previous_invocation(pending, Path(prior_invocation_path), expected_prior_invocation_sha256,
                                      root=root, number=number, review_path=review_path,
                                      review_sha256=expected_continuation_review_sha256)
    projection_path = batch / "strict-schema-projection.json"
    reconciliation_value, reconciliation = _unlaunched_reconciliation(
        pending, Path(unlaunched_reconciliation_path), expected_unlaunched_reconciliation_sha256, root=root, number=number,
        manifest=manifest, manifest_sha256=manifest_sha256, plan=plan, plan_sha256=pending.sha256(plan_raw),
        projection_sha256=pending.sha256(projection), binding_sha256=_sha256(binding_raw), review_sha256=expected_continuation_review_sha256,
    )
    operation = _outer_operation(pending, Path(outer_operation_path), expected_outer_operation_sha256,
                                 reconciliation=reconciliation, invocation=invocation, manifest=manifest,
                                 manifest_sha256=manifest_sha256, plan=plan, plan_sha256=pending.sha256(plan_raw),
                                 projection_sha256=pending.sha256(projection), review=review)
    route = fresh_route_guard()
    expected_route = {"route_sha256": plan.get("route_sha256"), "route_evidence_sha256": plan.get("route_evidence_sha256")}
    _require(route == expected_route, "fresh route differs")
    return {"format_version": 1, "kind": "wpb_sol_pending_unlaunched_resume_v1", "mode": "root_review_required_no_dispatch",
            "companion": _own_descriptor(), "pending_source": _descriptor(PENDING, PENDING_SHA256, "pending continuation source"),
            "prior_invocation": invocation, "unlaunched_reconciliation": reconciliation,
            "outer_operation": operation,
            "process_observation": reconciliation_value["process_observation"],
            "pending_manifest": {"path": str((root / "pending-continuation-manifest.json").resolve()), "sha256": manifest_sha256},
            "plan": {"path": str((batch / "plan.json").resolve()), "sha256": pending.sha256(plan_raw)},
            "projection": {"path": str(projection_path.resolve()), "sha256": pending.sha256(projection)}, "review": review,
            "prepared_cells": cells, "automatic_resend_authorized": False, "provider_calls_made": 0, "process_launches": 0}


def _precontact(*, descriptor: dict[str, Any], kwargs: dict[str, Any], cell_id: str) -> None:
    pending = _load_pending()
    root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]
    batch = pending._batch(root, number)
    _require(cell_id in descriptor["prepared_cells"], "pre-contact cell is absent from the reviewed operation")
    manifest, manifest_sha256 = pending._manifest(root)
    binding, projection = pending._binding(root, number, require_unexpired=True)
    review_path = Path(kwargs["continuation_review_path"]).resolve()
    review_sha256 = kwargs["expected_continuation_review_sha256"]
    _require(binding["review"] == {"path": str(review_path), "sha256": review_sha256}, "pre-contact review differs")
    pending._review(review_path, review_sha256, root, number, require_unexpired=True)
    plan, plan_raw = pending._read(batch / "plan.json", "prepared pending plan")
    _require(plan.get("cell_ids") == descriptor["prepared_cells"] and pending.sha256(plan_raw) == descriptor["plan"]["sha256"]
             and pending.sha256(projection) == descriptor["projection"]["sha256"], "pre-contact plan or projection differs")
    reconciliation = descriptor["unlaunched_reconciliation"]
    invocation = descriptor["prior_invocation"]
    _exact(Path(reconciliation["path"]), reconciliation["sha256"], "unlaunched restart reconciliation")
    _previous_invocation(pending, Path(invocation["path"]), invocation["sha256"], root=root, number=number,
                         review_path=review_path, review_sha256=review_sha256)
    _outer_operation(pending, Path(kwargs["outer_operation_path"]), kwargs["expected_outer_operation_sha256"],
                     reconciliation=reconciliation, invocation=invocation, manifest=manifest, manifest_sha256=manifest_sha256,
                     plan=plan, plan_sha256=pending.sha256(plan_raw), projection_sha256=pending.sha256(projection), review=binding["review"])
    _precontact_target(batch, cell_id)
    route = kwargs["fresh_route_guard"]()
    expected_route = {"route_sha256": plan.get("route_sha256"), "route_evidence_sha256": plan.get("route_evidence_sha256")}
    _require(route == expected_route, "fresh route differs")


def prepare_unlaunched_resume(**kwargs: Any) -> dict[str, Any]:
    """Validate admission and return a precontact guard without dispatching."""
    descriptor = _preflight(**kwargs)

    def before_provider_attempt() -> None:
        _preflight(**kwargs)

    return {**descriptor, "before_provider_attempt": before_provider_attempt}


def dispatch_unlaunched_resume(*, dispatch_kwargs: dict[str, Any], call_codex: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Reuse the exact binding and delegate one unlaunched batch through the pinned dispatcher."""
    descriptor = _preflight(**kwargs)
    pending = _load_pending()
    root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]
    review_path = Path(kwargs["continuation_review_path"]).resolve()
    review_sha256 = kwargs["expected_continuation_review_sha256"]
    _require(dispatch_kwargs.get("campaign_root") == root and dispatch_kwargs.get("batch_number") == number
             and Path(dispatch_kwargs.get("continuation_review_path")).resolve() == review_path
             and dispatch_kwargs.get("expected_continuation_review_sha256") == review_sha256
             and dispatch_kwargs.get("allow_remote") is True, "dispatch arguments differ from reviewed operation")
    original_bind, original_configure = pending._bind_review, pending._configured_legacy
    precontact_cells: set[str] = set()

    def reuse_binding(binding_root: Path, binding_number: int, binding_review_path: Path, binding_review_sha256: str) -> None:
        _require(Path(binding_root).resolve() == root and binding_number == number
                 and Path(binding_review_path).resolve() == review_path and binding_review_sha256 == review_sha256,
                 "dispatch binding arguments differ")
        _preflight(**kwargs)
        pending._binding(root, number, require_unexpired=True)

    def configure_legacy() -> tuple[ModuleType, ModuleType]:
        legacy, strict = original_configure()
        original_current = legacy._current_call_codex

        def current_call(runtime: ModuleType, *, receipt_root: Path) -> Any:
            return wrap_call(original_current(runtime, receipt_root=receipt_root))

        legacy._current_call_codex = current_call
        return legacy, strict

    def wrap_call(base: Any) -> Any:
        _require(callable(base), "native call callback is unavailable")

        def guarded_call(**call_kwargs: Any) -> tuple[str, dict[str, Any]]:
            before = call_kwargs.get("before_provider_attempt")
            output = Path(call_kwargs.get("output_dir"))
            _require(callable(before) and output.name in descriptor["prepared_cells"], "native pre-contact callback differs")

            def outer_before() -> None:
                _require(output.name not in precontact_cells, "pre-contact callback repeated for one cell")
                precontact_cells.add(output.name)
                _precontact(descriptor=descriptor, kwargs=kwargs, cell_id=output.name)
                before()

            return base(**(call_kwargs | {"before_provider_attempt": outer_before}))

        return guarded_call

    pending._bind_review = reuse_binding
    pending._configured_legacy = configure_legacy
    try:
        outer_call = wrap_call(call_codex) if call_codex is not None else None
        outcomes = pending.dispatch_batch(**(dispatch_kwargs | ({"call_codex": outer_call} if outer_call is not None else {})))
    finally:
        pending._configured_legacy = original_configure
        pending._bind_review = original_bind
    return {**descriptor, "mode": "dispatch_completed", "outcomes": outcomes,
            "process_launches": len(outcomes), "provider_calls_made": None,
            "provider_contact_cardinality": "unknown"}
