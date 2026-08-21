"""Provenance-bound callback mechanism for the frozen batch-curve v2 screen.

The endpoint is deliberately injected.  This module owns durable local evidence,
not credentials or a provider transport.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from hbqrs import compile_bundle, load_bundles, load_modules, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import _render_prompt


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "execution-contract.json"
CELL_FORMAT = 1


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_value(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _bound_file(relative: str) -> Path:
    path = (HERE / relative).resolve()
    if not path.is_file():
        raise ValueError(f"Bound artifact is missing: {relative}")
    return path


def _parent_harness() -> Any:
    path = HERE.parent / "batch-curve-v2" / "batch_curve_harness.py"
    spec = importlib.util.spec_from_file_location("batch_curve_live_parent_v2", path)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen parent harness cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _same(expected: Any, actual: Any) -> bool:
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return set(expected) == set(actual) and all(_same(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(_same(left, right) for left, right in zip(expected, actual, strict=True))
    return expected == actual


def _sha256(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _exact_parent(contract: Mapping[str, Any]) -> tuple[Any, Mapping[str, Any], list[dict[str, Any]], Mapping[str, Any]]:
    required = {"format_version", "study_id", "status", "parent", "prompt_binding", "schedule", "output_policy"}
    if set(contract) != required or contract.get("format_version") != 1 or contract.get("study_id") != "the-part-that-arrives-first-batch-curve-live-v1" or contract.get("status") != "transport_agnostic_callback_mechanism_not_live":
        raise ValueError("Live execution contract shape drifted")
    parent = contract["parent"]
    if not isinstance(parent, Mapping) or set(parent) != {"contract_path", "contract_sha256", "projection_path", "projection_sha256", "harness_path", "harness_sha256"}:
        raise ValueError("Live execution contract parent binding is incomplete")
    parent_contract_path = _bound_file(str(parent["contract_path"]))
    projection_path = _bound_file(str(parent["projection_path"]))
    harness_path = _bound_file(str(parent["harness_path"]))
    if not all(_sha256(parent.get(key)) for key in ("contract_sha256", "projection_sha256", "harness_sha256")):
        raise ValueError("Live execution contract has malformed parent hashes")
    if _sha256_bytes(parent_contract_path.read_bytes()) != parent["contract_sha256"] or _sha256_bytes(harness_path.read_bytes()) != parent["harness_sha256"]:
        raise ValueError("Frozen parent bytes drifted")
    if projection_path.read_text(encoding="ascii").strip() != parent["projection_sha256"]:
        raise ValueError("Frozen parent projection drifted")
    prompt = contract["prompt_binding"]
    if not isinstance(prompt, Mapping) or set(prompt) != {"binary_prompt_path", "binary_prompt_sha256", "source_path", "source_sha256", "effective_prompt"}:
        raise ValueError("Live prompt binding is incomplete")
    binary_path, source_path = _bound_file(str(prompt["binary_prompt_path"])), _bound_file(str(prompt["source_path"]))
    if _sha256_bytes(binary_path.read_bytes()) != prompt["binary_prompt_sha256"] or _sha256_bytes(source_path.read_bytes()) != prompt["source_sha256"]:
        raise ValueError("Frozen binary prefix or source bytes drifted")
    if prompt["effective_prompt"] != "runner_render_prompt_v1: frozen binary prefix plus frozen source and exact frozen question subset":
        raise ValueError("Effective prompt protocol drifted")
    if contract["schedule"] != {"cells": 39, "repetitions": 3, "all_in_one_question_count": 178, "source": "parent_fixed_three_block_rotation"}:
        raise ValueError("Fixed 39-cell schedule binding drifted")
    if contract["output_policy"] != {"external_root": "operator_selected", "resume": "per-cell atomic checkpoints", "raw_response_bodies": "prohibited", "credentials": "prohibited", "callback": "transport_boundary_only_no_concrete_provider_adapter_verified", "recommendation": "none_until_parent_deep_validation_accepts_an_exact_empirical_stack"}:
        raise ValueError("Live output policy drifted")
    harness = _parent_harness()
    parent_contract = _read_json(parent_contract_path)
    modules = load_modules(registry_path())
    bundle = next((item for item in load_bundles(bundles_path()) if item["bundle_id"] == parent_contract["runtime"]["bundle_id"]), None)
    if bundle is None:
        raise ValueError("Frozen parent bundle is unavailable")
    compiled = compile_bundle(modules, bundle)
    harness.validate_contract(parent_contract, compiled)
    items = harness.all_question_items(compiled)
    frozen_ids = parent_contract["runtime"]["frozen_question_ids"]
    if [item["question"]["id"] for item in items] != frozen_ids or len(items) != 178:
        raise ValueError("Compiled questions do not exactly reconstruct the frozen parent order")
    return harness, parent_contract, items, bundle


def validate_execution_contract(contract: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    disk = _read_json(CONTRACT_PATH)
    current = disk if contract is None else contract
    if not isinstance(current, Mapping):
        raise ValueError("Live execution contract must be an object")
    if not _same(current, disk):
        raise ValueError("Passed execution contract does not exactly match canonical disk contract")
    _exact_parent(current)
    return current


def plans(contract: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    current = validate_execution_contract(contract)
    harness, parent, _items, _bundle = _exact_parent(current)
    planned = harness.planned_events(parent)
    if len(planned) != 39 or planned[-1]["size"] != 48:
        raise ValueError("Parent schedule is not the frozen 39-cell rotation")
    return [dict(row) for row in planned]


def _question_batch(items: Sequence[Mapping[str, Any]], ids: Sequence[str]) -> list[Mapping[str, Any]]:
    by_id = {str(item["question"]["id"]): item for item in items}
    if len(by_id) != len(items) or any(question_id not in by_id for question_id in ids):
        raise ValueError("Frozen question batch cannot be reconstructed")
    return [by_id[question_id] for question_id in ids]


def _effective_prompt_bound(current: Mapping[str, Any], parent: Mapping[str, Any], items: Sequence[Mapping[str, Any]], question_ids: Sequence[str]) -> tuple[str, dict[str, Any]]:
    frozen_ids = parent["runtime"]["frozen_question_ids"]
    if not isinstance(question_ids, Sequence) or isinstance(question_ids, (str, bytes)) or not question_ids:
        raise ValueError("Question batch must be a nonempty ordered sequence")
    positions = [frozen_ids.index(question_id) if type(question_id) is str and question_id in frozen_ids else -1 for question_id in question_ids]
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise ValueError("Question batch must be one exact contiguous frozen-order partition")
    questions = _question_batch(items, question_ids)
    source_path = _bound_file(str(current["prompt_binding"]["source_path"]))
    binary_path = _bound_file(str(current["prompt_binding"]["binary_prompt_path"]))
    prompt = _render_prompt(
        binary_prompt=binary_path.read_text(encoding="utf-8"),
        artifact={"name": source_path.name, "text": source_path.read_text(encoding="utf-8")},
        contexts=[], bundle_id=parent["runtime"]["bundle_id"], artifact_id="the-part-that-arrives-first",
        questions=questions,
    )
    binding = {
        "binary_prompt_sha256": current["prompt_binding"]["binary_prompt_sha256"],
        "source_sha256": current["prompt_binding"]["source_sha256"],
        "parent_question_order_sha256": parent["runtime"]["question_id_sequence_sha256"],
        "question_ids": list(question_ids),
        "question_batch_sha256": _sha256_value(list(question_ids)),
        "effective_prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
    }
    return prompt, binding


def effective_prompt(question_ids: Sequence[str], contract: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    current = validate_execution_contract(contract)
    _harness, parent, items, _bundle = _exact_parent(current)
    return _effective_prompt_bound(current, parent, items, question_ids)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_json_bytes(value) + b"\n")
    temporary.replace(path)


def _transport(transport: Any) -> dict[str, str]:
    if not isinstance(transport, Mapping) or set(transport) != {"mode", "identity", "version", "args_sha256"}:
        raise ValueError("Transport identity must use the exact callback allowlist")
    projected = {key: transport[key] for key in ("mode", "identity", "version", "args_sha256")}
    if projected["mode"] != "test_callback_only" or not all(isinstance(projected[key], str) and projected[key] for key in ("identity", "version")) or not _sha256(projected["args_sha256"]):
        raise ValueError("No concrete provider transport is verified for this mechanism")
    return projected


def _manifest(contract: Mapping[str, Any], transport: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "execution_contract_disk_sha256": _sha256_bytes(CONTRACT_PATH.read_bytes()),
        "execution_contract_canonical_sha256": _sha256_value(contract),
        "parent_contract_sha256": contract["parent"]["contract_sha256"],
        "parent_projection_sha256": contract["parent"]["projection_sha256"],
        "parent_harness_sha256": contract["parent"]["harness_sha256"],
        "adapter_sha256": _sha256_bytes(Path(__file__).read_bytes()),
        "transport": _transport(transport),
        "cell_count": 39,
        "raw_response_bodies": "prohibited",
        "credentials": "prohibited",
    }


def prepare(work_root: Path, transport: Mapping[str, Any], contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    current = validate_execution_contract(contract)
    work_root.mkdir(parents=True, exist_ok=True)
    manifest_path = work_root / "manifest.json"
    expected = _manifest(current, transport)
    if manifest_path.exists():
        existing = _read_json(manifest_path)
        if not _same(expected, existing):
            raise ValueError("External work root belongs to a different execution contract")
    else:
        _atomic_json(manifest_path, expected)
    (work_root / "cells").mkdir(exist_ok=True)
    return expected


def _cell_path(work_root: Path, sequence: int) -> Path:
    return work_root / "cells" / f"cell-{sequence:02d}.json"


def _receipt(receipt: Any, parent: Mapping[str, Any], harness: Any) -> Mapping[str, Any]:
    expected = {"configured_provider_kind", "runner_provider_argument", "reported", "session_id"}
    if not isinstance(receipt, Mapping) or set(receipt) != expected:
        raise ValueError("Provider receipt contains unallowlisted fields")
    if not isinstance(receipt.get("reported"), Mapping) or set(receipt["reported"]) != {"provider", "model", "reasoning_effort"}:
        raise ValueError("Provider receipt reported identity contains unallowlisted fields")
    projected = {
        "configured_provider_kind": receipt["configured_provider_kind"],
        "runner_provider_argument": receipt["runner_provider_argument"],
        "reported": {
            "provider": receipt["reported"]["provider"], "model": receipt["reported"]["model"],
            "reasoning_effort": receipt["reported"]["reasoning_effort"],
        },
        "session_id": receipt["session_id"],
    }
    harness.verify_provider_receipt(projected, parent)
    return projected


def _new_cell(plan: Mapping[str, Any], previous_cell_sha256: str | None) -> dict[str, Any]:
    return {
        "format_version": CELL_FORMAT,
        "plan": dict(plan),
        "previous_cell_sha256": previous_cell_sha256,
        "calls": [],
        "status": "in_progress",
    }


def _validate_cell(
    cell: Mapping[str, Any], *, current: Mapping[str, Any], plan: Mapping[str, Any], parent: Mapping[str, Any], harness: Any,
    items: Sequence[Mapping[str, Any]], previous_cell_sha256: str | None, session_ids: set[str],
) -> list[dict[str, Any]]:
    expected_keys = {"format_version", "plan", "previous_cell_sha256", "calls", "status"}
    if cell.get("status") == "completed":
        expected_keys |= {"evaluation", "evaluation_sha256"}
    if set(cell) != expected_keys or cell.get("format_version") != CELL_FORMAT or not _same(cell.get("plan"), dict(plan)) or cell.get("previous_cell_sha256") != previous_cell_sha256 or cell.get("status") not in {"in_progress", "completed"} or not isinstance(cell.get("calls"), list):
        raise ValueError("Cell checkpoint shape or chain binding drifted")
    chunks = harness.partition_question_ids(parent["runtime"]["frozen_question_ids"], plan["size"])
    accepted: list[dict[str, Any]] = []
    cursor = 0
    source = _bound_file(str(current["prompt_binding"]["source_path"])).read_text(encoding="utf-8")
    for ordinal, ids in enumerate(chunks, 1):
        accepted_call: Mapping[str, Any] | None = None
        for attempt in range(1, parent["runtime"]["batch_attempts"] + 1):
            if cursor >= len(cell["calls"]):
                break
            started = cell["calls"][cursor]
            cursor += 1
            _prompt, binding = _effective_prompt_bound(current, parent, items, ids)
            started_expected = {"event": "attempt_started", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids, "prompt_binding": binding}
            if not isinstance(started, Mapping) or not _same(started, started_expected):
                raise ValueError("Cell lacks a persisted attempt-started checkpoint")
            if cursor >= len(cell["calls"]):
                if cell["status"] == "completed":
                    raise ValueError("Completed cell has an unterminated provider attempt")
                return accepted
            call = cell["calls"][cursor]
            cursor += 1
            common = {"batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids, "response_commitment_sha256": call.get("response_commitment_sha256") if isinstance(call, Mapping) else None}
            if not isinstance(call, Mapping) or not _sha256(common["response_commitment_sha256"]):
                raise ValueError("Attempt terminal record lacks a safe response commitment")
            if call.get("event") == "accepted":
                expected = {**common, "event": "accepted", "prompt_binding": binding, "provider": call.get("provider"), "verdicts": call.get("verdicts"), "verdicts_sha256": call.get("verdicts_sha256")}
                if set(call) != set(expected) or not _same(call, expected):
                    raise ValueError("Accepted attempt record shape drifted")
                receipt = _receipt(call["provider"], parent, harness)
                session = receipt["session_id"]
                if session in session_ids:
                    raise ValueError("Fresh provider session provenance was reused")
                session_ids.add(session)
                verdicts = harness._strict_fixture_verdicts(call["verdicts"], ids, artifact_text=source)
                if call["verdicts_sha256"] != _sha256_value(verdicts):
                    raise ValueError("Accepted parsed verdict hash drifted")
                accepted.extend(verdicts)
                accepted_call = call
                break
            if call.get("event") != "rejected":
                raise ValueError("Attempt terminal event is invalid")
            rejection = call.get("rejection")
            if rejection == "endpoint_rejected_or_invalid":
                expected = {**common, "event": "rejected", "prompt_binding": binding, "provider": call.get("provider"), "rejection": rejection}
                if set(call) != set(expected) or not _same(call, expected):
                    raise ValueError("Rejected provider attempt record shape drifted")
                receipt = _receipt(call["provider"], parent, harness)
                session = receipt["session_id"]
                if session in session_ids:
                    raise ValueError("Fresh provider session provenance was reused")
                session_ids.add(session)
                continue
            if rejection != "transport_or_malformed_response" or not _same(call, {**common, "event": "rejected", "rejection": rejection}):
                raise ValueError("Unsafe malformed-response record")
        if accepted_call is None and cursor == len(cell["calls"]):
            break
        if accepted_call is None:
            raise ValueError("A physical batch exhausted retries without acceptance")
    if cursor != len(cell["calls"]):
        raise ValueError("Cell has extra or interleaved physical calls")
    if cell["status"] == "completed":
        if len(accepted) != len(parent["runtime"]["frozen_question_ids"]):
            raise ValueError("Completed cell lacks the frozen full question sequence")
        evaluation = harness._canonical_evaluation(_study_modules(parent), _study_bundle(parent), accepted)
        if not _same(cell.get("evaluation"), evaluation) or cell.get("evaluation_sha256") != _sha256_value(evaluation):
            raise ValueError("Completed cell score provenance drifted")
    return accepted


def _study_modules(parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    return load_modules(registry_path())


def _study_bundle(parent: Mapping[str, Any]) -> Mapping[str, Any]:
    return next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == parent["runtime"]["bundle_id"])


def _confidence_rows(items: Sequence[Mapping[str, Any]], repetitions: Sequence[Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    weights = {str(item["question"]["id"]): float(item["effective_weight"]) for item in items}
    if len(weights) != len(items):
        raise ValueError("Frozen question weights are not unique")
    rows: list[dict[str, Any]] = []
    for verdicts in repetitions:
        for verdict in verdicts:
            label = verdict["verdict"]
            question_id = verdict["question_id"]
            rows.append({
                "question_id": question_id, "verdict": label, "assessed": label in {"YES", "NO"},
                "weight": weights[question_id], "confidence": verdict["confidence"],
                "canonical_leaf_score": 1.0 if label == "YES" else 0.0,
            })
    return rows


def _persist_analysis(work_root: Path, value: Mapping[str, Any]) -> None:
    path = work_root / "analysis.json"
    if path.exists() and _same(_read_json(path), value):
        return
    _atomic_json(path, value)


Endpoint = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def _prior_cells(work_root: Path, planned: Sequence[Mapping[str, Any]], current: Mapping[str, Any], parent: Mapping[str, Any], harness: Any, items: Sequence[Mapping[str, Any]]) -> tuple[dict[int, dict[str, Any]], set[str], str | None]:
    loaded: dict[int, dict[str, Any]] = {}
    sessions: set[str] = set()
    previous: str | None = None
    for plan in planned:
        path = _cell_path(work_root, int(plan["sequence"]))
        if not path.exists():
            if any(_cell_path(work_root, int(later["sequence"])).exists() for later in planned if later["sequence"] > plan["sequence"]):
                raise ValueError("External work root has a gap in its fixed schedule")
            break
        cell = _read_json(path)
        _validate_cell(cell, current=current, plan=plan, parent=parent, harness=harness, items=items, previous_cell_sha256=previous, session_ids=sessions)
        loaded[int(plan["sequence"])] = cell
        if cell["status"] != "completed":
            if any(_cell_path(work_root, int(later["sequence"])).exists() for later in planned if later["sequence"] > plan["sequence"]):
                raise ValueError("External work root continues after an incomplete cell")
            break
        previous = _sha256_bytes(path.read_bytes())
    return loaded, sessions, previous


def _response_or_raise(response: Any, parent: Mapping[str, Any], harness: Any) -> Mapping[str, Any]:
    if not isinstance(response, Mapping) or set(response) != {"verdicts", "provider", "response_commitment_sha256"}:
        raise ValueError("Endpoint response must omit raw bodies and contain only verdicts, provider receipt, and commitment")
    if not _sha256(response.get("response_commitment_sha256")):
        raise ValueError("Endpoint response commitment is malformed")
    return {"verdicts": response["verdicts"], "provider": _receipt(response["provider"], parent, harness), "response_commitment_sha256": response["response_commitment_sha256"]}


def run_callback_mechanism(work_root: Path, endpoint: Endpoint, transport: Mapping[str, Any], contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Exercise the non-live callback mechanism; no concrete provider is admitted."""
    current = validate_execution_contract(contract)
    prepare(work_root, transport, current)
    harness, parent, items, bundle = _exact_parent(current)
    planned = plans(current)
    loaded, sessions, previous = _prior_cells(work_root, planned, current, parent, harness, items)
    source = _bound_file(str(current["prompt_binding"]["source_path"])).read_text(encoding="utf-8")
    modules = _study_modules(parent)
    for plan in planned:
        sequence = int(plan["sequence"])
        cell = loaded.get(sequence)
        path = _cell_path(work_root, sequence)
        if cell is not None and cell["status"] == "completed":
            previous = _sha256_bytes(path.read_bytes())
            continue
        if cell is None:
            cell = _new_cell(plan, previous)
            _atomic_json(path, cell)
        chunks = harness.partition_question_ids(parent["runtime"]["frozen_question_ids"], plan["size"])
        all_verdicts: list[dict[str, Any]] = []
        for ordinal, ids in enumerate(chunks, 1):
            terminal = [call for call in cell["calls"] if call["event"] in {"accepted", "rejected"} and call["batch_ordinal"] == ordinal]
            started = [call for call in cell["calls"] if call["event"] == "attempt_started" and call["batch_ordinal"] == ordinal]
            if len(started) != len(terminal):
                if len(started) != len(terminal) + 1:
                    raise ValueError("Cell has an invalid attempt-started checkpoint sequence")
                interrupted = started[-1]
                cell["calls"].append({
                    "event": "rejected", "batch_ordinal": ordinal, "attempt": interrupted["attempt"], "question_ids": ids,
                    "response_commitment_sha256": _sha256_value({"kind": "interrupted_before_terminal_receipt", "sequence": sequence, "batch_ordinal": ordinal, "attempt": interrupted["attempt"]}),
                    "rejection": "transport_or_malformed_response",
                })
                _atomic_json(path, cell)
                return run_callback_mechanism(work_root, endpoint, transport, current)
            accepted = next((call for call in terminal if call["event"] == "accepted"), None)
            if accepted is not None:
                all_verdicts.extend(accepted["verdicts"])
                continue
            if len(terminal) >= parent["runtime"]["batch_attempts"]:
                raise ValueError("A resumed physical batch exhausted its frozen retry budget")
            prompt, binding = _effective_prompt_bound(current, parent, items, ids)
            attempt = len(terminal) + 1
            started = {"event": "attempt_started", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids, "prompt_binding": binding}
            cell["calls"].append(started)
            _atomic_json(path, cell)
            try:
                response = _response_or_raise(endpoint(prompt, {"plan": dict(plan), "batch_ordinal": ordinal, "attempt": attempt, "prompt_binding": binding}), parent, harness)
            except Exception:
                cell["calls"].append({
                    "event": "rejected", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids,
                    "response_commitment_sha256": _sha256_value({"kind": "transport_or_malformed_response", "sequence": sequence, "batch_ordinal": ordinal, "attempt": attempt}),
                    "rejection": "transport_or_malformed_response",
                })
                _atomic_json(path, cell)
                if attempt == parent["runtime"]["batch_attempts"]:
                    raise ValueError("Physical batch exhausted its frozen retry budget")
                return run_callback_mechanism(work_root, endpoint, transport, current)
            receipt = response["provider"]
            session = receipt["session_id"]
            if session in sessions:
                cell["calls"].append({
                    "event": "rejected", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids,
                    "prompt_binding": binding, "provider": dict(receipt),
                    "response_commitment_sha256": response["response_commitment_sha256"], "rejection": "endpoint_rejected_or_invalid",
                })
                _atomic_json(path, cell)
                raise ValueError("Endpoint reused a fresh-session identity")
            sessions.add(session)
            try:
                verdicts = harness._strict_fixture_verdicts(response["verdicts"], ids, artifact_text=source)
            except ValueError:
                cell["calls"].append({
                    "event": "rejected", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids,
                    "prompt_binding": binding, "provider": dict(receipt),
                    "response_commitment_sha256": response["response_commitment_sha256"], "rejection": "endpoint_rejected_or_invalid",
                })
                _atomic_json(path, cell)
                if attempt == parent["runtime"]["batch_attempts"]:
                    raise ValueError("Physical batch exhausted its frozen retry budget")
                return run_callback_mechanism(work_root, endpoint, transport, current)
            cell["calls"].append({
                "event": "accepted", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": ids,
                "prompt_binding": binding, "provider": dict(receipt),
                "response_commitment_sha256": response["response_commitment_sha256"],
                "verdicts": verdicts, "verdicts_sha256": _sha256_value(verdicts),
            })
            _atomic_json(path, cell)
            all_verdicts.extend(verdicts)
        if [row["question_id"] for row in all_verdicts] != parent["runtime"]["frozen_question_ids"]:
            raise ValueError("Cell accepted verdicts do not reconstruct the frozen full order")
        evaluation = harness._canonical_evaluation(modules, bundle, all_verdicts)
        cell.update({"status": "completed", "evaluation": evaluation, "evaluation_sha256": _sha256_value(evaluation)})
        _atomic_json(path, cell)
        previous = _sha256_bytes(path.read_bytes())
    return analyze(work_root, current)


def analyze(work_root: Path, contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Summarize completed cells without promoting screening evidence to a recommendation."""
    current = validate_execution_contract(contract)
    manifest = _read_json(work_root / "manifest.json")
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("transport"), Mapping):
        raise ValueError("External work manifest lacks transport identity")
    expected_manifest = _manifest(current, manifest["transport"])
    if not _same(manifest, expected_manifest):
        raise ValueError("External work manifest does not bind this execution contract")
    harness, parent, items, _bundle = _exact_parent(current)
    planned = plans(current)
    loaded, _sessions, _previous = _prior_cells(work_root, planned, current, parent, harness, items)
    by_size: dict[str, list[tuple[Mapping[str, Any], list[dict[str, Any]]]]] = {}
    for plan in planned:
        cell = loaded.get(int(plan["sequence"]))
        if cell is not None and cell["status"] == "completed":
            verdicts = [verdict for call in cell["calls"] if call["event"] == "accepted" for verdict in call["verdicts"]]
            by_size.setdefault(str(plan["size"]), []).append((cell["evaluation"], verdicts))
    complete_sizes = {
        size: evaluations for size, evaluations in by_size.items()
        if len(evaluations) == parent["screening"]["repetitions"]
    }
    largest_completed = max((harness.resolved_size("all-in-one" if size == "all-in-one" else int(size), parent["runtime"]["question_count"]) for size in complete_sizes), default=None)
    screening: dict[str, dict[str, Any]] = {}
    for size, evaluations in complete_sizes.items():
        verdict_repetitions = [verdicts for _evaluation, verdicts in evaluations]
        repetitions = [
            [{**verdict, "canonical_observed_score": evaluation["canonical_observed_score"], "strict_schema_conformant": True, "exact_quote_grounded": True} for verdict in verdicts]
            for evaluation, verdicts in evaluations
        ]
        metrics = harness.repeatability_metrics(repetitions)
        screening[size] = {
            "metrics": metrics,
            "confidence_diagnostics": harness.confidence_diagnostics(_confidence_rows(items, verdict_repetitions), expected_question_ids=parent["runtime"]["frozen_question_ids"]),
            "state": harness.screening_state(metrics, parent["decline_and_bracket"]["thresholds"]),
        }
    transitions = None
    if len(screening) == len(parent["batch_sizes"]):
        transitions = harness.bracket_transitions({size: screening[str(size)]["state"] for size in parent["batch_sizes"]})
    result = {
        "format_version": 1,
        "parent_contract_sha256": current["parent"]["contract_sha256"],
        "manifest_sha256": _sha256_bytes((work_root / "manifest.json").read_bytes()),
        "adapter_sha256": manifest["adapter_sha256"],
        "evidence_class": "transport_agnostic_callback_mechanism_not_live",
        "completed_cells": sum(len(rows) for rows in by_size.values()),
        "complete_screening_sizes": sorted(complete_sizes, key=lambda size: harness.resolved_size("all-in-one" if size == "all-in-one" else int(size), parent["runtime"]["question_count"])),
        "largest_completed_screening_size": largest_completed,
        "screening": screening,
        "bracket_transitions": transitions,
        "position_metrics": [
            {"sequence": plan["sequence"], "size": plan["size"], "rows": harness.position_rows(parent["runtime"]["frozen_question_ids"], block=plan["block"], within_block=plan["within_block"], size=plan["size"])}
            for plan in planned
            if (cell := loaded.get(int(plan["sequence"]))) is not None and cell["status"] == "completed"
        ],
        "recommendation": None,
        "recommendation_reason": "callback-only mechanism output is not live evidence or parent deep-validation evidence; no size is recommended",
    }
    _persist_analysis(work_root, result)
    return result
