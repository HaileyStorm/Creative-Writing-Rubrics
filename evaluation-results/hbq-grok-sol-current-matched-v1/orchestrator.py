#!/usr/bin/env python3
"""Provider-free preflight and strict native-evidence validation for Grok/Sol."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
BOOK = HERE.parents[1]
sys.path.insert(0, str(BOOK / "src"))

SHA256 = hashlib.sha256


def _load_module(name: str, filename: str) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen Grok/Sol study")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


study = _load_module("hbq_grok_sol_current_matched_study", "study.py")
analyze = _load_module("hbq_grok_sol_current_matched_analyze", "analyze_study.py")
trusted_launcher = _load_module("hbq_grok_sol_current_matched_launcher", "trusted_launcher.py")


def _sha_bytes(value: bytes) -> str:
    return SHA256(value).hexdigest()


def _is_reparse(path: Path) -> bool:
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        attributes = 0
    return path.is_symlink() or bool(attributes & 0x400)


def _guard_path(path: Path, *, exists: bool = True) -> Path:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and _is_reparse(current):
            raise RuntimeError(f"Reparse point is not allowed: {current}")
    if exists and not absolute.exists():
        raise RuntimeError(f"Required path is missing: {absolute}")
    return absolute.resolve(strict=False)


def _read(path: Path) -> bytes:
    guarded = _guard_path(path)
    value = guarded.read_bytes()
    if _guard_path(path) != guarded:
        raise RuntimeError("Path changed while being read")
    return value


def _load_object(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read(path)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path.name}")
    return value, raw


def _cell(condition_id: str, case_id: str, repetition: int) -> tuple[dict[str, Any], dict[str, Any]]:
    conditions = {row["condition_id"]: row for row in study.contract()["conditions"]}
    cases = {row["case_id"]: row for row in study.cases()}
    if condition_id not in conditions or case_id not in cases or repetition not in range(1, 4):
        raise RuntimeError("Cell is absent from the exact 12x3 Sol/Grok schedule")
    return conditions[condition_id], cases[case_id]


def _validated_disclosure(prepared_binding_path: Path, frozen_path: Path, snapshot: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use the analyzer's sole strict binding authority before any preflight/result use."""
    try:
        binding = analyze._validate_dispatch_binding(prepared_binding_path, frozen_path, snapshot)
        disclosure_path = analyze._bound_dispatch_file(prepared_binding_path.parent, binding["disclosure"])
        disclosure = analyze.read(disclosure_path)
    except ValueError as exc:
        raise RuntimeError("Prepared dispatch binding is not admissible") from exc
    if disclosure != study.dispatch_disclosure(dict(snapshot)):
        raise RuntimeError("Prepared disclosure is no longer the exact frozen disclosure")
    return binding, disclosure


def _schedule_entry(disclosure: Mapping[str, Any], condition_id: str, case_id: str, repetition: int) -> Mapping[str, Any]:
    found = [row for row in disclosure.get("entries", []) if isinstance(row, dict) and (row.get("condition_id"), row.get("case_id"), row.get("repetition")) == (condition_id, case_id, repetition)]
    if len(found) != 1:
        raise RuntimeError("Disclosure lacks exactly one schedule entry for this cell")
    return found[0]


def _assert_full_matched_task_identity(disclosure: Mapping[str, Any]) -> None:
    conditions = {row["condition_id"]: row for row in study.contract()["conditions"]}
    for case in study.cases():
        sol = study.rendered_prompt(case, conditions["sol"]).encode("utf-8")
        grok = study.rendered_prompt(case, conditions["grok"]).encode("utf-8")
        if sol != grok:
            raise RuntimeError("Matched-input invariant failed: Sol and Grok task bytes differ")
        for repetition in range(1, 4):
            for condition_id in ("sol", "grok"):
                commitment = _schedule_entry(disclosure, condition_id, case["case_id"], repetition).get("rendered_prompt")
                if not isinstance(commitment, dict) or commitment.get("bytes") != len(sol) or commitment.get("sha256") != _sha_bytes(sol):
                    raise RuntimeError("Disclosure does not bind every matched task byte sequence")


def inspect_cell(
    *, frozen_path: Path, prepared_binding_path: Path, trusted_receipt_path: Path,
    condition_id: str, case_id: str, repetition: int,
) -> dict[str, Any]:
    """Validate the exact public payload without trusting or contacting a provider."""
    condition, case = _cell(condition_id, case_id, repetition)
    frozen_path, prepared_binding_path, trusted_receipt_path = (_guard_path(path) for path in (frozen_path, prepared_binding_path, trusted_receipt_path))
    frozen_bytes = _read(frozen_path)
    try:
        frozen = json.loads(frozen_bytes)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Frozen snapshot is invalid JSON") from exc
    study.validate_snapshot(frozen)
    prepared_bytes = _read(prepared_binding_path)
    _, disclosure = _validated_disclosure(prepared_binding_path, frozen_path, frozen)
    receipt, receipt_bytes = _load_object(trusted_receipt_path)
    # A local file is inspectable evidence only; it does not establish trust.
    if receipt.get("study_id") != study.EXPECTED_STUDY_ID:
        raise RuntimeError("Receipt does not identify the frozen study")
    _assert_full_matched_task_identity(disclosure)
    schedule = _schedule_entry(disclosure, condition_id, case_id, repetition)
    prompt = study.rendered_prompt(case, condition).encode("utf-8")
    if schedule.get("rendered_prompt", {}).get("sha256") != _sha_bytes(prompt) or schedule.get("rendered_prompt", {}).get("bytes") != len(prompt):
        raise RuntimeError("Disclosure prompt commitment drifted")
    return {"status": "preflight_only_no_dispatch", "provider_calls": 0, "cell": {"condition_id": condition_id, "case_id": case_id, "repetition": repetition},
            "frozen_sha256": _sha_bytes(frozen_bytes), "prepared_binding_sha256": _sha_bytes(prepared_bytes), "receipt_sha256": _sha_bytes(receipt_bytes),
            "launcher_identity": trusted_launcher.identity(), "task_sha256": _sha_bytes(prompt)}


def execute_cell(
    *, frozen_path: Path, prepared_binding_path: Path, trusted_receipt_path: Path, work_root: Path,
    condition_id: str, case_id: str, repetition: int, allow_remote: bool,
) -> dict[str, Any]:
    """Fail closed until an independently trusted execution successor exists."""
    if allow_remote is not True:
        raise RuntimeError("Remote dispatch requires an explicit allow_remote=True")
    preflight = inspect_cell(frozen_path=frozen_path, prepared_binding_path=prepared_binding_path, trusted_receipt_path=trusted_receipt_path, condition_id=condition_id, case_id=case_id, repetition=repetition)
    trusted_launcher.verify_external_launch(preflight)
    raise AssertionError("A trusted launcher must not return without a separately reviewed dispatch implementation")


def validate_completed_cell(
    *, frozen_path: Path, prepared_binding_path: Path, work_root: Path, condition_id: str, case_id: str, repetition: int,
) -> dict[str, Any]:
    """Strictly validate a native runner V4 cell; no test callback can manufacture acceptance."""
    _, case = _cell(condition_id, case_id, repetition)
    frozen_path, prepared_binding_path, work_root = (_guard_path(path) for path in (frozen_path, prepared_binding_path, work_root))
    snapshot, _ = _load_object(frozen_path)
    study.validate_snapshot(snapshot)
    _validated_disclosure(prepared_binding_path, frozen_path, snapshot)
    result = analyze._run(work_root, snapshot, case, condition_id, repetition)
    return {"status": "native_v4_evidence_validated_nonpromotable", "provider_calls": 0, "cell": {"condition_id": condition_id, "case_id": case_id, "repetition": repetition},
            "run_id": result["run_id"], "provider_receipt": result["provider_receipt"], "native_evidence": result["input_evidence"], "launcher_identity": trusted_launcher.identity()}


def recover_cell(*, work_root: Path, condition_id: str, case_id: str, repetition: int) -> dict[str, Any]:
    """Classify an interrupted cell without ever resending it."""
    _cell(condition_id, case_id, repetition)
    work_root = _guard_path(work_root)
    run = work_root / "runs" / condition_id / case_id / f"run-{repetition:02d}"
    intent = run / "attempt-intent.json"
    if not intent.exists():
        return {"status": "no_durable_intent_no_dispatch", "provider_calls": 0}
    _read(intent)
    native = run / "responses" / "batch-0001.accepted-0001.message.txt"
    if not native.exists():
        return {"status": "precontact_or_unresolved_no_resend", "provider_calls": 0}
    return {"status": "native_evidence_present_operator_validation_required_no_resend", "provider_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="One-cell Grok/Sol preflight; this host has no trusted remote-launch authority.")
    parser.add_argument("command", choices=("inspect", "execute", "recover"))
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--prepared-binding", type=Path, required=True)
    parser.add_argument("--trusted-receipt", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--case", dest="case_id", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    if args.command == "recover":
        print(json.dumps(recover_cell(work_root=args.work_root, condition_id=args.condition, case_id=args.case_id, repetition=args.repetition), sort_keys=True))
        return 0
    operation = execute_cell if args.command == "execute" else inspect_cell
    result = operation(frozen_path=args.frozen, prepared_binding_path=args.prepared_binding, trusted_receipt_path=args.trusted_receipt,
                       work_root=args.work_root, condition_id=args.condition, case_id=args.case_id, repetition=args.repetition,
                       allow_remote=args.allow_remote) if args.command == "execute" else operation(frozen_path=args.frozen, prepared_binding_path=args.prepared_binding, trusted_receipt_path=args.trusted_receipt,
                       condition_id=args.condition, case_id=args.case_id, repetition=args.repetition)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
