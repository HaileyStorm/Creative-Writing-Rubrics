"""Concrete, provenance-bound Codex executor for the frozen batch-curve screen.

The only public projection is commitments to an operator-selected private raw
evidence root. Execution remains explicit and receipt-gated.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping

PACKAGE_DIR = Path(__file__).resolve().parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from hbqrs import compile_bundle, load_bundles, load_modules
from hbqrs.paths import bundles_path, registry_path
from ordered_runner import _prompt as _ordered_prompt, run as run_ordered
from ordered_verify import verify as verify_ordered


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "codex-execution-contract.json"
RECEIPT = "preexecution-disclosure-receipt.json"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def _same(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(_same(value, right[key]) for key, value in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_json_bytes(value) + b"\n")
    temporary.replace(path)


def _bound(relative: str, binding: Mapping[str, Any]) -> Path:
    if set(binding) != {"path", "bytes", "sha256"} or binding.get("path") != relative:
        raise ValueError("Frozen binding shape drifted")
    path = (HERE / relative).resolve()
    if not path.is_file() or type(binding["bytes"]) is not int or type(binding["sha256"]) is not str:
        raise ValueError(f"Frozen binding is malformed: {relative}")
    if path.stat().st_size != binding["bytes"] or _sha256_path(path) != binding["sha256"]:
        raise ValueError(f"Frozen bytes drifted: {relative}")
    return path


def contract() -> dict[str, Any]:
    value = _read(CONTRACT_PATH)
    expected = {"format_version", "study_id", "status", "parent", "execution", "frozen_inputs", "privacy", "recommendation"}
    if set(value) != expected or value["format_version"] != 1 or value["study_id"] != "the-part-that-arrives-first-batch-curve-codex-v1":
        raise ValueError("Codex successor contract shape drifted")
    if value["status"] != "preregistered_concrete_codex_execution_no_empirical_results":
        raise ValueError("Codex successor is not an unexecuted preregistration")
    execution = value["execution"]
    if not isinstance(execution, dict) or execution.get("provider") != "codex" or execution.get("reported_provider") != "openai" or execution.get("model") != "gpt-5.6-sol" or execution.get("reasoning") != "high" or execution.get("strict_ai") is not True or execution.get("fresh_sessions") is not True or execution.get("batch_attempts") != 3 or execution.get("cells") != 39 or execution.get("question_count") != 178 or not isinstance(execution.get("codex_argv_template"), list):
        raise ValueError("Codex execution pins drifted")
    if value["recommendation"] != {"screening_recommendation": None, "above_24_requires": "deep exact-stack HANNA evidence"}:
        raise ValueError("Recommendation must remain disabled")
    for name, binding in value["parent"].items():
        if not isinstance(name, str) or not isinstance(binding, dict):
            raise ValueError("Predecessor bindings are malformed")
        _bound(str(binding.get("path")), binding)
    inputs = value["frozen_inputs"]
    for name in ("source", "registry", "bundles", "response_schema", "verdict_schema", "score_v1_schema", "score_v2_schema", "adapter", "ordered_runner", "ordered_verifier"):
        _bound(str(inputs[name].get("path")), inputs[name])
    for binding in [*inputs["prompts"], *inputs["runtime"]]:
        _bound(str(binding.get("path")), binding)
    return value


def _v2_harness() -> Any:
    path = HERE.parent / "batch-curve-v2" / "batch_curve_harness.py"
    spec = importlib.util.spec_from_file_location("batch_curve_codex_parent_v2", path)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v2 harness cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def plan() -> list[dict[str, Any]]:
    value = contract()
    parent = _read((HERE / value["parent"]["v2_contract"]["path"]).resolve())
    harness = _v2_harness()
    modules = load_modules(registry_path())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == parent["runtime"]["bundle_id"])
    compiled = compile_bundle(modules, bundle)
    if [item["question"]["id"] for item in harness.all_question_items(compiled)] != parent["runtime"]["frozen_question_ids"]:
        raise ValueError("Current registry no longer reconstructs the frozen v2 question order")
    blocks = parent.get("screening", {}).get("blocks")
    sizes = parent.get("batch_sizes")
    if not isinstance(blocks, list) or len(blocks) != 3 or not isinstance(sizes, list) or any(not isinstance(block, list) or len(block) != len(sizes) or set(block) != set(sizes) for block in blocks):
        raise ValueError("Frozen v2 schedule shape drifted")
    projection = harness.contract_projection_sha256(parent)
    rows = [{"event": "planned", "format_version": harness.JOURNAL_FORMAT, "sequence": sequence, "block": block, "within_block": within, "repetition": block, "size": size, "contract_projection_sha256": projection} for sequence, (block, within, size) in enumerate(((block, within, size) for block, schedule in enumerate(blocks, 1) for within, size in enumerate(schedule, 1)), 1)]
    if len(rows) != value["execution"]["cells"] or any(row["sequence"] != index for index, row in enumerate(rows, 1)):
        raise ValueError("Frozen 39-cell v2 schedule drifted")
    return rows


def effective_prompt(question_ids: list[str]) -> tuple[str, dict[str, Any]]:
    """Return the strict-AI prompt for one exact frozen batch partition."""
    value = contract()
    parent = _read((HERE / value["parent"]["v2_contract"]["path"]).resolve())
    frozen = parent["runtime"]["frozen_question_ids"]
    if not question_ids or any(type(item) is not str for item in question_ids):
        raise ValueError("Question batch is malformed")
    positions = [frozen.index(item) if item in frozen else -1 for item in question_ids]
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise ValueError("Question batch must be one contiguous v2 frozen partition")
    modules = load_modules(registry_path())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == parent["runtime"]["bundle_id"])
    compiled = compile_bundle(modules, bundle)
    items = {str(item["question"]["id"]): item for item in _v2_harness().all_question_items(compiled)}
    questions = [items[item] for item in question_ids]
    inputs = value["frozen_inputs"]
    prefix, binary = (_bound(item["path"], item).read_text(encoding="utf-8") for item in inputs["prompts"])
    source = _bound(inputs["source"]["path"], inputs["source"])
    prompt = _ordered_prompt(prefix=prefix, binary=binary, source=source, bundle_id=parent["runtime"]["bundle_id"], artifact_id="the-part-that-arrives-first", questions=questions)
    return prompt, {"question_ids": list(question_ids), "prompt_sha256": _sha256_bytes(prompt.encode("utf-8")), "prefix_sha256": inputs["prompts"][0]["sha256"], "binary_sha256": inputs["prompts"][1]["sha256"]}


def _git_state(run: Callable[..., Any] = subprocess.run) -> dict[str, str]:
    root = HERE.parents[2]
    def command(argv: list[str]) -> str:
        completed = run(argv, cwd=root, capture_output=True, text=True, check=False)
        if getattr(completed, "returncode", 1) != 0:
            raise ValueError("Cannot establish clean pushed package provenance")
        return str(getattr(completed, "stdout", "")).strip()
    head, dirty = command(["git", "rev-parse", "HEAD"]), command(["git", "status", "--porcelain"])
    remotes = command(["git", "branch", "-r", "--contains", head]).splitlines()
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head) or dirty or "origin/main" not in {item.strip() for item in remotes}:
        raise ValueError("Preparation requires a clean commit already pushed to origin/main")
    return {"commit": head, "remote": "origin/main"}


def _codex_runtime(executable: str, run: Callable[..., Any] = subprocess.run, resolve: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    resolved = resolve(executable)
    if not resolved:
        raise ValueError("Codex executable cannot be resolved")
    completed = run([resolved, "--version"], capture_output=True, text=True, check=False)
    version = str(getattr(completed, "stdout", "")).strip()
    if getattr(completed, "returncode", 1) != 0 or not version:
        raise ValueError("Codex version probe failed")
    return {"executable": str(Path(resolved).resolve()), "version": version}


def _receipt(value: Mapping[str, Any], private_root: Path, executable: str, run: Callable[..., Any], resolve: Callable[[str], str | None]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": value["study_id"],
        "contract_sha256": _sha256_path(CONTRACT_PATH),
        "git": _git_state(run),
        "codex": {**_codex_runtime(executable, run, resolve), "argv_template": value["execution"]["codex_argv_template"]},
        "private_evidence_root_sha256": _sha256_bytes(str(private_root.resolve()).encode("utf-8")),
        "outbound_disclosure": value["privacy"],
        "outbound_bindings": {"source": value["frozen_inputs"]["source"], "prompts": value["frozen_inputs"]["prompts"], "response_schema": value["frozen_inputs"]["response_schema"]},
        "pre_execution": True,
    }


def prepare(work_root: Path, private_evidence_root: Path, *, executable: str = "codex", subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    """Seal a local disclosure receipt before any provider call; this is offline."""
    value = contract()
    private_evidence_root.mkdir(parents=True, exist_ok=True)
    receipt = _receipt(value, private_evidence_root, executable, subprocess_run, executable_resolver)
    target = work_root / RECEIPT
    if target.exists() and not _same(_read(target), receipt):
        raise ValueError("Existing pre-execution receipt binds a different environment")
    _atomic_json(target, receipt)
    return receipt


def _raw_index(private_root: Path, relative_run: str) -> dict[str, Any]:
    run = private_root / relative_run
    files = [{"path": path.relative_to(private_root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256_path(path)} for path in sorted(run.rglob("*")) if path.is_file()]
    index = {"format_version": 1, "private_root_sha256": _sha256_bytes(str(private_root.resolve()).encode("utf-8")), "run_path": relative_run, "files": files}
    path = private_root / "evidence-index" / f"{Path(relative_run).name}.json"
    if path.exists() and _read(path) != index:
        raise ValueError("Immutable private raw-evidence index drifted")
    _atomic_json(path, index)
    return {"private_root_sha256": _sha256_bytes(str(private_root.resolve()).encode("utf-8")), "relative_path": path.relative_to(private_root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256_path(path)}


def _validate_roots(work_root: Path, private_root: Path) -> None:
    public, private = work_root.resolve(), private_root.resolve()
    if public == private or public in private.parents or private in public.parents:
        raise ValueError("Public work and private raw-evidence roots must be disjoint")


def _question_items(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    parent = _read((HERE / value["parent"]["v2_contract"]["path"]).resolve())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == parent["runtime"]["bundle_id"])
    return _v2_harness().all_question_items(compile_bundle(load_modules(registry_path()), bundle))


def _completed_cell(cell: Mapping[str, Any], row: Mapping[str, Any], private_root: Path, value: Mapping[str, Any], verifier: Callable[..., Any], codex_bin: str) -> dict[str, Any] | None:
    if set(cell) != {"format_version", "plan", "calls", "status"} or cell.get("format_version") != 1 or not _same(cell.get("plan"), row) or cell.get("status") != "completed" or not isinstance(cell.get("calls"), list) or len(cell["calls"]) != 2:
        return None
    accepted = cell["calls"][-1]; raw = accepted.get("raw_evidence_index") if isinstance(accepted, Mapping) else None
    if not isinstance(raw, Mapping) or set(raw) != {"private_root_sha256", "relative_path", "bytes", "sha256"} or raw["private_root_sha256"] != _sha256_bytes(str(private_root.resolve()).encode("utf-8")):
        return None
    index = private_root / raw["relative_path"]
    if not index.is_file() or index.stat().st_size != raw["bytes"] or _sha256_path(index) != raw["sha256"]:
        return None
    try:
        inputs = value["frozen_inputs"]; items = _question_items(value); size = 178 if row["size"] == "all-in-one" else int(row["size"])
        verified = verifier(run_dir=private_root / "runs" / f"cell-{int(row['sequence']):02d}", source=_bound(inputs["source"]["path"], inputs["source"]), prefix=_bound(inputs["prompts"][0]["path"], inputs["prompts"][0]), binary=_bound(inputs["prompts"][1]["path"], inputs["prompts"][1]), registry=_bound(inputs["registry"]["path"], inputs["registry"]), bundles=_bound(inputs["bundles"]["path"], inputs["bundles"]), score_v1_schema=_bound(inputs["score_v1_schema"]["path"], inputs["score_v1_schema"]), score_v2_schema=_bound(inputs["score_v2_schema"]["path"], inputs["score_v2_schema"]), question_items=items, batch_size=size, codex_bin=codex_bin)
    except Exception:
        return None
    raw_index = _read(index)
    run = private_root / f"runs/cell-{int(row['sequence']):02d}"
    expected_files = [{"path": path.relative_to(private_root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256_path(path)} for path in sorted(run.rglob("*")) if path.is_file()]
    if raw_index != {"format_version": 1, "private_root_sha256": raw["private_root_sha256"], "run_path": f"runs/cell-{int(row['sequence']):02d}", "files": expected_files}:
        return None
    expected_accepted = {"event": "accepted", "raw_evidence_index": dict(raw), **verified}
    return verified if _same(accepted, expected_accepted) else None


def execute(work_root: Path, private_evidence_root: Path, *, runner: Callable[..., Any] = run_ordered, verifier: Callable[..., Any] = verify_ordered, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    """Explicit live path. It reprobes the sealed environment before every send."""
    _validate_roots(work_root, private_evidence_root); value = contract(); receipt = _read(work_root / RECEIPT)
    live = _receipt(value, private_evidence_root, receipt.get("codex", {}).get("executable", "codex"), subprocess_run, executable_resolver)
    if not _same(receipt, live): raise ValueError("Live environment no longer exactly matches the pre-execution receipt")
    rows, items, completed, session_hashes = plan(), _question_items(value), 0, set(); inputs = value["frozen_inputs"]
    for row in rows:
        sequence = int(row["sequence"]); cell_path = work_root / "cells" / f"cell-{sequence:02d}.json"; cell = _read(cell_path) if cell_path.exists() else {"format_version": 1, "plan": row, "calls": [], "status": "pending"}
        if cell.get("status") == "completed":
            verified_existing = _completed_cell(cell, row, private_evidence_root, value, verifier, receipt["codex"]["executable"])
            if verified_existing is None: raise ValueError("Completed cell does not fully validate")
            for session in verified_existing["sessions"]:
                digest = session["session_id_sha256"]
                if digest in session_hashes: raise ValueError("Fresh provider session was reused across cells")
                session_hashes.add(digest)
            completed += 1; continue
        claim = work_root / "claims" / f"cell-{sequence:02d}.claim"; claim.parent.mkdir(parents=True, exist_ok=True)
        try: handle = claim.open("x", encoding="utf-8")
        except FileExistsError: raise ValueError("Cell is already claimed by another executor")
        try:
            with handle:
                handle.write(str(sequence))
                if not _same(cell.get("plan"), row) or cell.get("status") not in {"pending", "in_progress"}: raise ValueError("Cell checkpoint drifted")
                if not cell["calls"]: cell.update({"status": "in_progress", "calls": [{"event": "attempt_started", "attempt": 1}]}); _atomic_json(cell_path, cell)
                size = 178 if row["size"] == "all-in-one" else int(row["size"]); run_dir = private_evidence_root / "runs" / f"cell-{sequence:02d}"
                runner(output_dir=run_dir, source=_bound(inputs["source"]["path"], inputs["source"]), registry=_bound(inputs["registry"]["path"], inputs["registry"]), bundles=_bound(inputs["bundles"]["path"], inputs["bundles"]), prefix=_bound(inputs["prompts"][0]["path"], inputs["prompts"][0]), binary=_bound(inputs["prompts"][1]["path"], inputs["prompts"][1]), response_schema=_bound(inputs["response_schema"]["path"], inputs["response_schema"]), question_items=items, batch_size=size, codex_bin=receipt["codex"]["executable"])
                verified = verifier(run_dir=run_dir, source=_bound(inputs["source"]["path"], inputs["source"]), prefix=_bound(inputs["prompts"][0]["path"], inputs["prompts"][0]), binary=_bound(inputs["prompts"][1]["path"], inputs["prompts"][1]), registry=_bound(inputs["registry"]["path"], inputs["registry"]), bundles=_bound(inputs["bundles"]["path"], inputs["bundles"]), score_v1_schema=_bound(inputs["score_v1_schema"]["path"], inputs["score_v1_schema"]), score_v2_schema=_bound(inputs["score_v2_schema"]["path"], inputs["score_v2_schema"]), question_items=items, batch_size=size, codex_bin=receipt["codex"]["executable"])
                for session in verified["sessions"]:
                    digest = session["session_id_sha256"]
                    if digest in session_hashes: raise ValueError("Fresh provider session was reused across cells")
                    session_hashes.add(digest)
                raw = _raw_index(private_evidence_root, f"runs/cell-{sequence:02d}"); cell.update({"status": "completed", "calls": [{"event": "attempt_started", "attempt": 1}, {"event": "accepted", "raw_evidence_index": raw, **verified}]}); _atomic_json(cell_path, cell); completed += 1
        finally:
            claim.unlink(missing_ok=True)
    result = {"format_version": 1, "contract_sha256": _sha256_path(CONTRACT_PATH), "completed_cells": completed, "status": "incomplete_nonlive_analysis_pending", "screening_recommendation": None, "recommendation_reason": "No screening recommendation is ever produced here; above 24 additionally requires deep exact-stack HANNA evidence."}; _atomic_json(work_root / "analysis.json", result); return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan, prepare, or explicitly execute the Codex batch-curve successor.")
    parser.add_argument("command", choices=("plan", "prepare", "execute"))
    parser.add_argument("work_root", type=Path, nargs="?")
    parser.add_argument("private_evidence_root", type=Path, nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        print(json.dumps(plan(), indent=2))
        return
    if args.command == "execute":
        if not args.work_root or not args.private_evidence_root:
            raise SystemExit("execute requires WORK_ROOT PRIVATE_EVIDENCE_ROOT")
        print(json.dumps(execute(args.work_root, args.private_evidence_root), indent=2))
        return
    if not args.dry_run or args.work_root is None or args.private_evidence_root is None:
        raise SystemExit("prepare is local-only and requires --dry-run WORK_ROOT PRIVATE_EVIDENCE_ROOT")
    print(json.dumps(prepare(args.work_root, args.private_evidence_root), indent=2))


if __name__ == "__main__":
    main()
