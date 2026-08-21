"""Fresh-88 successor adapter: raw binary runs are the only admissible evidence."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence

from hbqrs.run_verify import verify_binary_run

HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "study-contract.json"
MATRIX_NAME = "fresh88-verifier-matrix.json"
RECEIPT_NAME = "fresh88-execution-receipt.json"
AUTHORITY_PIN = {"frozen_successor_sha256": "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7", "freeze_receipt_sha256": "eaab5d605a720c86f00e40635e59e9a43bb9c58998a70d9e5bca3907c008f1b0", "replay_status": "rejected"}
EXECUTION = {"artifact_id": "PER_CELL", "bundle_id": "prose.short_story", "batch_size": 32, "batch_attempts": 3,
             "strict_ai": False, "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "codex_bin": "codex"}
PROVIDER = {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}
_CANONICAL_BINDING_PATHS = {
    "registry": HERE.parents[1] / "registry" / "all_modules.json",
    "bundles": HERE.parents[1] / "bundles" / "all_bundles.json",
    "prompts": HERE.parents[1] / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md",
    "response_schema": HERE.parents[1] / "schema" / "hbq_judge_response.schema.json",
    "score_v1_schema": HERE.parents[1] / "schema" / "hbq_score_report.schema.json",
    "score_v2_schema": HERE.parents[1] / "schema" / "hbq_score_report.v2.schema.json",
    "verdict_schema": HERE.parents[1] / "schema" / "hbq_verdict.schema.json",
    "task_contract_schema": HERE.parents[1] / "schema" / "hbq_task_contract.schema.json",
}
_RUNTIME_FILES = (
    HERE / "study.py", HERE / "prepare_fresh.py", HERE / "run_fresh.py", HERE / "successor_gate.py",
    HERE.parents[1] / "src" / "hbqrs" / "__init__.py",
    HERE.parents[1] / "src" / "hbqrs" / "paths.py",
    HERE.parents[1] / "src" / "hbqrs" / "run_verify.py",
    HERE.parents[1] / "src" / "hbqrs" / "runner.py",
    HERE.parents[1] / "src" / "hbqrs" / "runner_v2.py",
    HERE.parents[1] / "src" / "hbqrs" / "core.py",
    HERE.parents[1] / "src" / "hbqrs" / "scoring_v2.py",
    HERE.parents[1] / "src" / "hbqrs" / "weights.py",
)

def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _binding(path: Path) -> dict[str, Any]:
    path = path.resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_path(path)}

def canonical_bindings() -> dict[str, Any]:
    bound = {key: _binding(path) for key, path in _CANONICAL_BINDING_PATHS.items()}
    prompt = bound.pop("prompts")
    return {**bound, "prompts": [prompt]}

def runtime_manifest() -> dict[str, Any]:
    files = {str(path.resolve()): _binding(path) for path in _RUNTIME_FILES}
    return {"files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}

def read_json(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict): raise ValueError(f"Expected object: {path}")
    return value

def atomic_immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered: raise ValueError(f"Immutable artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(rendered); out.flush(); os.fsync(out.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True); raise

def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if value.get("format_version") != 2 or value.get("study_id") != "hbq-human-alignment-v3-successor-v1": raise ValueError("Successor contract identity drifted")
    if value.get("verified54") != {"status": "DISABLED", "reason": "authoritative_replay_rejected"}: raise ValueError("Verified54 must remain disabled")
    if value.get("fresh88_authority") != AUTHORITY_PIN: raise ValueError("Fresh88 authority pin drifted")
    return value

CONTRACT = load_contract()

def load_authority(root: Path) -> dict[str, Any]:
    contract, receipt = root / "frozen-successor-contract.json", root / "freeze-receipt.json"
    if not contract.is_file() or not receipt.is_file() or sha256_path(contract) != AUTHORITY_PIN["frozen_successor_sha256"] or sha256_path(receipt) != AUTHORITY_PIN["freeze_receipt_sha256"]: raise ValueError("Authoritative fresh88 freeze bytes drifted")
    frozen = read_json(contract); fresh, binding = frozen.get("fresh_complement"), frozen.get("binding")
    ids = fresh.get("scheduled_item_ids") if isinstance(fresh, Mapping) else None
    if not isinstance(binding, Mapping) or binding.get("carried_replay_status") != "rejected" or not isinstance(ids, list) or len(ids) != 88 or len(set(ids)) != 88 or any(not isinstance(x, str) or not x for x in ids): raise ValueError("Authoritative fresh88 selection is invalid")
    return frozen

def _bound(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}: raise ValueError(f"{label} binding malformed")
    path = Path(str(value["path"])).resolve()
    if not path.is_file() or path.stat().st_size != value["bytes"] or sha256_path(path) != value["sha256"]: raise ValueError(f"{label} binding drifted")
    return dict(value)

def load_execution_contract(work: Path, authority_root: Path) -> dict[str, Any]:
    authority = load_authority(authority_root); plan = read_json(work / "fresh88-execution-contract.json")
    required = {"format_version", "study_id", "authority_contract_sha256", "origin", "phase", "base_frozen", "cells"}
    if set(plan) != required or plan["format_version"] != 1 or plan["study_id"] != CONTRACT["study_id"] or plan["authority_contract_sha256"] != AUTHORITY_PIN["frozen_successor_sha256"] or plan["origin"] != "fresh_full_successor" or plan["phase"] != "development": raise ValueError("Fresh run execution contract identity drifted")
    base = plan["base_frozen"]
    exact_base = {"registry", "bundles", "prompts", "response_schema", "score_v1_schema", "score_v2_schema", "verdict_schema", "task_contract_schema", "weight_profile", "execution", "provider", "runtime_manifest"}
    if set(base) != exact_base: raise ValueError("Fresh run base contract keys drifted")
    for key in exact_base:
        if key not in base: raise ValueError(f"Fresh run contract lacks {key}")
    bindings = canonical_bindings()
    for key, expected in bindings.items():
        if base.get(key) != expected: raise ValueError(f"Canonical {key} binding drifted")
    if base["runtime_manifest"] != runtime_manifest(): raise ValueError("Runtime source manifest drifted")
    if base["weight_profile"] is not None: raise ValueError("Fresh successor weight profile must be None")
    if not isinstance(base["prompts"], list) or not base["prompts"]: raise ValueError("Prompt bindings missing")
    for item in base["prompts"]: _bound(item, "prompt")
    if base["execution"] != EXECUTION or base["provider"] != PROVIDER: raise ValueError("Fresh successor runtime pin drifted")
    ids, cells = authority["fresh_complement"]["scheduled_item_ids"], plan["cells"]
    source_rows = {row.get("item_id"): row for row in authority.get("selection", {}).get("development", []) if isinstance(row, Mapping)}
    if not isinstance(cells, list) or len(cells) != 88: raise ValueError("Fresh run contract requires exactly 88 cells")
    for ordinal, (cell, item_id) in enumerate(zip(cells, ids), 1):
        if not isinstance(cell, Mapping) or set(cell) != {"item_id", "origin", "ordinal", "run_dir", "artifact", "contexts", "task_contract", "external_input"} or cell["item_id"] != item_id or cell["origin"] != "fresh_full_successor" or cell["ordinal"] != ordinal or not isinstance(cell["run_dir"], str) or Path(cell["run_dir"]).parts != ("runs", item_id): raise ValueError("Fresh run item/order/layout binding drifted")
        _bound(cell["artifact"], "artifact"); _bound(cell["task_contract"], "task contract")
        if not isinstance(cell["contexts"], list): raise ValueError("Context binding malformed")
        for item in cell["contexts"]: _bound(item, "context")
        external = cell["external_input"]
        source = source_rows.get(item_id, {}).get("external_input")
        expected = {"artifact": cell["artifact"]["sha256"], "contexts": [item["sha256"] for item in cell["contexts"]], "task_contract": cell["task_contract"]["sha256"]}
        if not isinstance(source, Mapping) or external != source or expected != {"artifact":source.get("source.md",{}).get("sha256"), "contexts":[source.get("prompt.md",{}).get("sha256")], "task_contract":source.get("task-contract.json",{}).get("sha256")}: raise ValueError("Cell external input authority binding drifted")
    return plan

def _metrics(run_dir: Path) -> dict[str, Any]:
    import math
    score = read_json(run_dir / "score.v2.json"); final = score.get("final_score")
    observed = final.get("observed") if isinstance(final, Mapping) else None
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(float(observed)): raise ValueError("Verified score lacks finite final_score.observed")
    return {"score": float(observed), "confidence": score.get("confidence", {"status": "UNAVAILABLE"}), "coverage": final.get("coverage", {"status": "UNAVAILABLE"}), "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}

def _under(root: Path, value: str) -> Path:
    relative = Path(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != value
        or len(relative.parts) != 2
        or relative.parts[0] != "runs"
        or not relative.parts[1]
    ):
        raise ValueError("Run directory layout is not canonical")
    resolved, base = (root / relative).resolve(), root.resolve()
    if resolved == base or base not in resolved.parents:
        raise ValueError("Run directory escapes artifact root")
    return resolved

def _verify_cell(cell: Mapping[str, Any], base: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    if base.get("execution", {}).get("artifact_id") == cell.get("item_id"):
        raise ValueError("Shared artifact identity is forbidden")
    frozen = dict(base); frozen.update({key: cell[key] for key in ("artifact", "contexts", "task_contract")})
    execution = dict(frozen["execution"]); execution["artifact_id"] = cell["item_id"]; frozen["execution"] = execution
    task = read_json(Path(cell["task_contract"]["path"]))
    if task.get("artifact_id") != cell["item_id"]: raise ValueError("Cell task does not bind item identity")
    run_dir = _under(artifact_root, str(cell["run_dir"]))
    result = verify_binary_run(run_dir, frozen)
    score_path = run_dir / "score.v2.json"
    if result.get("score_v2_sha256") != sha256_path(score_path): raise ValueError("Verified score descendant drifted")
    metrics = _metrics(run_dir)
    return {"run_dir": cell["run_dir"], "result": result, "metrics": metrics}

def freeze_execution_contract(work: Path, artifact_root: Path) -> dict[str, Any]:
    if (artifact_root / "runs").exists(): raise ValueError("Execution receipt must be frozen before raw runs exist")
    plan_hash = sha256_path(work / "fresh88-execution-contract.json")
    receipt = {"format_version": 1, "study_id": CONTRACT["study_id"], "execution_contract_sha256": plan_hash, "purpose": "pre_execution_raw_verifier_binding"}
    atomic_immutable_json(work / RECEIPT_NAME, receipt)
    if read_json(work / RECEIPT_NAME) != receipt: raise ValueError("Execution receipt reseal mismatch")
    return receipt

def verify_cells(cells: Sequence[Mapping[str, Any]], base: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    sessions: set[str] = set()
    run_dirs: set[str] = set()
    for cell in cells:
        run_dir = cell.get("run_dir")
        if not isinstance(run_dir, str) or run_dir in run_dirs: raise ValueError("Duplicate cell run directory")
        run_dirs.add(run_dir)
        verified = _verify_cell(cell, base, artifact_root)
        result, found = verified["result"], verified["result"].get("sessions")
        if not isinstance(found, list) or not found: raise ValueError("Verified run lacks session commitments")
        for session in found:
            digest = session.get("session_id_sha256") if isinstance(session, Mapping) else None
            if not isinstance(digest, str) or len(digest) != 64 or digest in sessions: raise ValueError("Fresh88 sessions must be study-wide unique")
            sessions.add(digest)
        records.append({"item_id": cell["item_id"], "origin": cell["origin"], "ordinal": cell["ordinal"], "run_dir": run_dir, "run_sha256": result["run_sha256"], "verifier": result, "metrics": verified["metrics"]})
    return {"records": records, "session_count": len(sessions)}

def verify_matrix(work: Path, authority_root: Path, artifact_root: Path) -> dict[str, Any]:
    plan = load_execution_contract(work, authority_root); receipt = read_json(work / RECEIPT_NAME)
    expected_receipt = {"format_version": 1, "study_id": CONTRACT["study_id"], "execution_contract_sha256": sha256_path(work / "fresh88-execution-contract.json"), "purpose": "pre_execution_raw_verifier_binding"}
    if receipt != expected_receipt: raise ValueError("Missing or invalid pre-execution receipt")
    verified = verify_cells(plan["cells"], plan["base_frozen"], artifact_root)
    expected = {_under(artifact_root, cell["run_dir"]) for cell in plan["cells"]}
    actual = {path for path in artifact_root.joinpath("runs").glob("*") if path.is_dir()} if (artifact_root / "runs").is_dir() else set()
    if actual != expected: raise ValueError("Raw run directory set has missing or extra cells")
    core = {"format_version": 1, "study_id": CONTRACT["study_id"], "execution_contract_sha256": receipt["execution_contract_sha256"], "execution_receipt_sha256": sha256_path(work / RECEIPT_NAME), **verified}
    matrix = {**core, "matrix_sha256": hashlib.sha256(canonical(core)).hexdigest()}; atomic_immutable_json(work / MATRIX_NAME, matrix)
    if read_json(work / MATRIX_NAME) != matrix: raise ValueError("Verifier matrix reseal mismatch")
    return matrix

def diagnostics(matrix: Mapping[str, Any]) -> dict[str, Any]:
    records = matrix.get("records")
    if not isinstance(records, list) or len(records) != 88: raise ValueError("Matrix lacks 88 verified records")
    scores = [r["metrics"]["score"] for r in records if isinstance(r.get("metrics", {}).get("score"), (int, float)) and not isinstance(r["metrics"]["score"], bool)]
    return {"score": {"mean": fmean(scores)} if scores else {"status": "UNAVAILABLE"}, "confidence": {"status": "DERIVED_FROM_VERIFIED_OUTPUTS"}, "order": {"method": "scheduled_ordinal_halves_v1", "records": 88}, "repeatability": {"status": "UNAVAILABLE", "reason": "one_verified_development_pass"}, "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}

def create_development_gate(work: Path, artifact_root: Path, authority_root: Path) -> dict[str, Any]:
    matrix = verify_matrix(work, authority_root, artifact_root)
    gate = {"format_version": 1, "study_id": CONTRACT["study_id"], "phase": "semantic_development_gate", "development_mode": "fresh_88", "matrix_sha256": matrix["matrix_sha256"], "execution_receipt_sha256": matrix["execution_receipt_sha256"], "diagnostics": diagnostics(matrix), "next_phase": "repeatability"}
    atomic_immutable_json(work / "semantic-development-gate.json", gate); return gate

def permit_phase(work: Path, phase: str, artifact_root: Path, authority_root: Path) -> dict[str, Any]:
    if phase in {"repeatability", "confirmatory"}: raise ValueError("Distinct raw-run contract is required for later successor phases")
    if phase != "development": raise ValueError("Unsupported successor phase")
    matrix = verify_matrix(work, authority_root, artifact_root); gate = read_json(work / "semantic-development-gate.json")
    expected_gate = {"format_version": 1, "study_id": CONTRACT["study_id"], "phase": "semantic_development_gate", "development_mode": "fresh_88", "matrix_sha256": matrix["matrix_sha256"], "execution_receipt_sha256": matrix["execution_receipt_sha256"], "diagnostics": diagnostics(matrix), "next_phase": "repeatability"}
    if gate != expected_gate: raise ValueError("Successor gate cannot be reused after raw evidence drift")
    return matrix
