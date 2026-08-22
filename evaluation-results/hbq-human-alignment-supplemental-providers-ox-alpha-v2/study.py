"""Fresh88-bound, no-provider preparation and local verification helpers for Ox v2."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.scoring_v2 import score_bundle as score_bundle_v2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CODE_ROOT = REPO_ROOT
CONTRACT_PATH = HERE / "study-contract.json"
V1_ROOT = HERE.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v1"
FROZEN_NAME = "frozen-ox-alpha-v2-contract.json"


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON object key: {key}")
        value[key] = item
    return value


def strict_json(text: str, *, label: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {label}") from exc


def read_json(path: Path) -> dict[str, Any]:
    value = strict_json(path.read_text(encoding="utf-8"), label=str(path))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Required file is unavailable: {path}")
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _external_separate(*paths: Path) -> None:
    resolved = [item.resolve() for item in paths]
    if any(_inside(item, REPO_ROOT) for item in resolved):
        raise ValueError("Fresh88/work/proof roots must remain outside the repository")
    if any(left == right or _inside(left, right) or _inside(right, left) for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("Fresh88/work/proof roots must be distinct and non-overlapping")


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered); output.flush(); os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def _module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load required validator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    required = {"format_version", "study_id", "status", "frozen_before_execution", "supersedes", "provider", "selection", "questions", "runtime", "fresh88", "remote_disclosure", "zero_cost", "stop_conditions", "interpretation_limits"}
    if set(value) != required or value["format_version"] != 2 or value["study_id"] != "hbq-human-alignment-supplemental-providers-ox-alpha-v2" or value["status"] != "preregistered_successor_unexecuted" or value["frozen_before_execution"] is not True:
        raise ValueError("Ox v2 contract identity drifted")
    if value["supersedes"] != {"study_id": "hbq-human-alignment-supplemental-providers-ox-alpha-v1", "contract_sha256": sha(V1_ROOT / "study-contract.json"), "status": "preserved_unexecuted_protocol_failure", "reason": "v1 bound the obsolete canonical-v3 178-item reference and therefore cannot answer the Fresh88 179-item comparison."}:
        raise ValueError("Ox v1 preservation/failure binding drifted")
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reported_models": ["stealth/ox-alpha"], "reasoning": "max", "allow_unattested_reasoning": True, "provisional_reasoning": True, "maximum_workers": 1, "evidence_status": "provisional_only"}
    if value["provider"] != provider or value["selection"]["item_ids"] != ["hanna-827", "hanna-957", "hanna-201"]:
        raise ValueError("Ox v2 provider or outcome-blind selection drifted")
    runtime = value["runtime"]
    expected = {"batch_size": 32, "expected_batches_per_item": 6, "batch_attempts": 1, "workers": 1, "maximum_logical_requests": 18, "maximum_physical_http_attempts_per_logical_request": 2, "maximum_physical_http_attempts": 36, "retry_or_fallback": "forbidden"}
    if runtime != expected or value["questions"].get("primary_leaf_count") != 179 or value["questions"].get("static_leaf_count") != 178 or value["questions"].get("dynamic_leaf_id") != "task.contract.hanna.prompt_response":
        raise ValueError("Ox v2 179-leaf geometry drifted")
    if value["zero_cost"].get("no_purchase") is not True:
        raise ValueError("Ox v2 zero-cost policy drifted")
    return value


CONTRACT = load_contract()


def _base() -> Any:
    return _module(V1_ROOT / "study.py", "ox_alpha_v1_preserved_validator")


def _binding_matches(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) not in ({"path", "bytes", "sha256"}, {"name", "bytes", "sha256"}):
        return False
    path_key = "path" if "path" in value else "name"
    return type(value.get("bytes")) is int and isinstance(value.get("sha256"), str) and len(value["sha256"]) == 64 and bool(value.get(path_key))


def _static_ids() -> list[str]:
    bundle = resolve_bundle(load_bundles(bundles_path()), CONTRACT["questions"]["bundle_id"])
    compiled = compile_bundle(load_modules(registry_path()), bundle)
    ids = _ordered_ids(compiled)
    if len(ids) != 178 or len(set(ids)) != 178 or CONTRACT["questions"]["dynamic_leaf_id"] in ids:
        raise ValueError("Static 178-leaf bundle geometry drifted")
    return ids


def _ordered_ids(compiled: Mapping[str, Any]) -> list[str]:
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    return [str(item["question"]["id"]) for item in sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))]


def _task_descendant(task: Mapping[str, Any]) -> dict[str, Any]:
    descendant = deepcopy(dict(task))
    goals = descendant.get("weighted_goals")
    if not isinstance(goals, list):
        raise ValueError("HANNA task contract lacks weighted goals")
    target = CONTRACT["questions"]["dynamic_leaf_id"].rsplit(".", 1)[-1]
    retained = [goal for goal in goals if isinstance(goal, Mapping) and goal.get("goal_id") != target]
    if len(retained) != len(goals) - 1:
        raise ValueError("Task-contract descendant must remove exactly the dynamic prompt-response goal")
    descendant["weighted_goals"] = retained
    return descendant


def question_geometry(task_path: Path) -> dict[str, Any]:
    task = read_json(task_path)
    static = _static_ids()
    bundle = resolve_bundle(load_bundles(bundles_path()), CONTRACT["questions"]["bundle_id"])
    primary = _ordered_ids(compile_bundle(load_modules(registry_path()), bundle, task_contract=task))
    ablated = _ordered_ids(compile_bundle(load_modules(registry_path()), bundle, task_contract=_task_descendant(task)))
    expected_dynamic = CONTRACT["questions"]["dynamic_leaf_id"]
    if len(primary) != 179 or set(primary) != set(static) | {expected_dynamic} or len(ablated) != 178 or set(ablated) != set(static):
        raise ValueError("Fresh88 HANNA task-contract question geometry drifted")
    batches = [primary[index:index + CONTRACT["runtime"]["batch_size"]] for index in range(0, len(primary), CONTRACT["runtime"]["batch_size"])]
    if [len(batch) for batch in batches] != [32, 32, 32, 32, 32, 19] or any(len(set(batch)) != len(batch) for batch in batches):
        raise ValueError("Ox v2 requires five 32-ID batches and one final 19-ID batch")
    return {"static_question_ids": static, "primary_question_ids": primary, "primary_batches": batches, "ablated_question_ids": ablated, "task_contract_descendant": _task_descendant(task)}


def _fresh88_binding(work: Path, authority: Path, artifacts: Path) -> dict[str, Any]:
    pin = CONTRACT["fresh88"]
    if sha(authority / "frozen-successor-contract.json") != pin["authority_contract_sha256"] or sha(authority / "freeze-receipt.json") != pin["authority_receipt_sha256"]:
        raise ValueError("Fresh88 v4 authority bytes drifted")
    execution_path, receipt_path, matrix_path = (work / name for name in ("fresh88-execution-contract.json", "fresh88-execution-receipt.json", "fresh88-verifier-matrix.json"))
    execution, receipt, matrix = read_json(execution_path), read_json(receipt_path), read_json(matrix_path)
    if execution.get("study_id") != pin["study_id"] or execution.get("phase") != pin["phase"] or execution.get("authority_contract_sha256") != pin["authority_contract_sha256"]:
        raise ValueError("Fresh88 execution contract identity drifted")
    base = execution.get("base_frozen")
    if not isinstance(base, Mapping):
        raise ValueError("Fresh88 execution contract lacks its frozen base")
    for path, key in ((registry_path(), "registry"), (bundles_path(), "bundles")):
        expected = base.get(key)
        if not isinstance(expected, Mapping) or sha(path) != expected.get("sha256"):
            raise ValueError(f"Fresh88 {key} binding no longer matches the local static-ablation scorer")
    runtime_files = base.get("runtime_manifest", {}).get("files") if isinstance(base.get("runtime_manifest"), Mapping) else None
    required_runtime = {name: fingerprint(CODE_ROOT / "src" / "hbqrs" / name) for name in ("core.py", "scoring_v2.py")}
    if not isinstance(runtime_files, Mapping) or any(sum(1 for path, binding in runtime_files.items() if Path(str(path)).name == name and isinstance(binding, Mapping) and binding.get("bytes") == current["bytes"] and binding.get("sha256") == current["sha256"]) != 1 for name, current in required_runtime.items()):
        raise ValueError("Fresh88 static-ablation scoring runtime no longer matches its sealed verifier")
    if receipt.get("execution_contract_sha256") != sha(execution_path) or matrix.get("execution_contract_sha256") != sha(execution_path) or matrix.get("execution_receipt_sha256") != sha(receipt_path):
        raise ValueError("Fresh88 verifier matrix is not bound to its execution contract/receipt")
    matrix_core = {key: value for key, value in matrix.items() if key != "matrix_sha256"}
    if matrix.get("matrix_sha256") != hashlib.sha256(canonical(matrix_core)).hexdigest():
        raise ValueError("Fresh88 verifier matrix hash drifted")
    gate = read_json(work / "semantic-development-gate.json")
    if gate.get("matrix_sha256") != matrix.get("matrix_sha256") or gate.get("study_id") != pin["study_id"] or gate.get("phase") != "semantic_development_gate":
        raise ValueError("Fresh88 semantic development gate is not bound to its verifier matrix")
    cells = {str(cell.get("item_id")): cell for cell in execution.get("cells", []) if isinstance(cell, Mapping)}
    records = {str(record.get("item_id")): record for record in matrix.get("records", []) if isinstance(record, Mapping)}
    selected: list[dict[str, Any]] = []
    for item_id in CONTRACT["selection"]["item_ids"]:
        cell, record = cells.get(item_id), records.get(item_id)
        if not isinstance(cell, Mapping) or not isinstance(record, Mapping):
            raise ValueError(f"Fresh88 has no selected public HANNA cell: {item_id}")
        if record.get("run_dir") != cell.get("run_dir"):
            raise ValueError("Fresh88 matrix/execution run binding drifted")
        run = artifacts / str(cell["run_dir"])
        verifier = record.get("verifier")
        commitments = verifier.get("commitments") if isinstance(verifier, Mapping) else None
        verdict_binding = commitments.get("verdicts") if isinstance(commitments, Mapping) else None
        if not isinstance(verdict_binding, Mapping) or sha(run / "run.json") != record.get("run_sha256") or sha(run / "score.v2.json") != verifier.get("score_v2_sha256") or fingerprint(run / "verdicts.jsonl") != {"name": "verdicts.jsonl", "bytes": verdict_binding.get("bytes"), "sha256": verdict_binding.get("sha256")}:
            raise ValueError("Fresh88 repair1 artifacts do not match the sealed selected verifier record")
        task_path = Path(str(cell["task_contract"]["path"]))
        geometry = question_geometry(task_path)
        score_v2_path = run / "score.v2.json"
        verdict_path = artifacts / str(cell["run_dir"]) / "verdicts.jsonl"
        verdicts = [strict_json(line, label=f"{verdict_path}:{number}") for number, line in enumerate(verdict_path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
        gpt_primary = score_bundle_v2(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), CONTRACT["questions"]["bundle_id"]), verdicts, artifact_id=item_id, task_contract=read_json(task_path))
        stored_primary = read_json(score_v2_path)
        if _finite_score(gpt_primary, "Fresh88 reconstructed score") != _finite_score(stored_primary, "Fresh88 score.v2") or _finite_score(stored_primary, "Fresh88 score.v2") != _finite_score(record.get("metrics", {}).get("score") if isinstance(record.get("metrics"), Mapping) else None, "Fresh88 matrix score"):
            raise ValueError("Fresh88 GPT matrix score is not reconstructed from its sealed score.v2/verdicts")
        gpt_static = static_ablation(verdicts, read_json(task_path), item_id)
        selected.append({"item_id": item_id, "ordinal": cell["ordinal"], "artifact": dict(cell["artifact"]), "contexts": [dict(item) for item in cell["contexts"]], "task_contract": dict(cell["task_contract"]), "external_input": dict(cell["external_input"]), "run_dir": cell["run_dir"], "repair1_artifacts": {"run": fingerprint(run / "run.json"), "score_v2": fingerprint(run / "score.v2.json"), "verdicts": fingerprint(run / "verdicts.jsonl")}, "gpt_record": dict(record), "gpt_static_ablation": gpt_static, "geometry": geometry})
    return {"execution_contract": fingerprint(work / "fresh88-execution-contract.json"), "execution_receipt": fingerprint(work / "fresh88-execution-receipt.json"), "verifier_matrix": fingerprint(work / "fresh88-verifier-matrix.json"), "semantic_gate": fingerprint(work / "semantic-development-gate.json"), "repair1_artifacts_root": str(artifacts.resolve()), "matrix_sha256": matrix["matrix_sha256"], "cells": selected}


def _zero_cost_proof(path: Path) -> dict[str, Any]:
    return _base()._zero_cost_proof(path)


def _assert_fresh_at(proof: Mapping[str, Any], checked_at: str) -> None:
    _base()._assert_fresh_at(proof, checked_at)


def _finite_score(value: Any, label: str) -> float:
    if isinstance(value, Mapping):
        value = value.get("final_score", {}).get("observed") if isinstance(value.get("final_score"), Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _runtime_bindings() -> dict[str, Any]:
    from hbqrs import runner
    launcher = runner.NOUS_LAUNCHER_PATH
    return {"study": fingerprint(Path(__file__)), "contract": fingerprint(CONTRACT_PATH), "runner": fingerprint(Path(runner.__file__)), "launcher": fingerprint(launcher), "bridge": fingerprint(launcher.parent / "nous_codex_bridge.py")}


def _frozen_cells(fresh: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells = fresh.get("cells")
    if not isinstance(cells, list) or len(cells) != 3:
        raise ValueError("Fresh88 selected-cell binding is malformed")
    result: list[dict[str, Any]] = []
    for number, cell in enumerate(cells, 1):
        if not isinstance(cell, Mapping): raise ValueError("Fresh88 selected cell is malformed")
        geometry, external = cell.get("geometry"), cell.get("external_input")
        if not isinstance(geometry, Mapping) or not isinstance(external, Mapping): raise ValueError("Fresh88 selected cell lacks geometry/input bindings")
        result.append({"cell_id": f"ox-alpha-v2-{number:02d}", "item_id": cell["item_id"], "ordinal": cell["ordinal"], "inputs": {"source.md": external["source.md"], "prompt.md": external["prompt.md"], "task-contract.json": external["task-contract.json"]}, "paths": {"artifact": cell["artifact"]["path"], "prompt": cell["contexts"][0]["path"], "task_contract": cell["task_contract"]["path"]}, "primary_question_ids": geometry["primary_question_ids"], "primary_batches": geometry["primary_batches"], "static_question_ids": geometry["static_question_ids"], "task_contract_descendant": geometry["task_contract_descendant"], "gpt_reference": {"matrix_record": cell["gpt_record"], "repair1_artifacts": cell["repair1_artifacts"], "primary_score": cell["gpt_record"]["metrics"]["score"], "static_ablation_score": cell["gpt_static_ablation"]["final_score"]["observed"]}})
    return result


def freeze_work(fresh88_work: Path, authority: Path, repair1_artifacts: Path, proof: Path, work: Path) -> dict[str, Any]:
    _external_separate(fresh88_work, authority, repair1_artifacts, proof, work)
    if work.exists() and any(work.iterdir()):
        raise ValueError("Ox v2 preparation requires an empty external work root")
    fresh = _fresh88_binding(fresh88_work, authority, repair1_artifacts)
    zero = _zero_cost_proof(proof)
    checked_at = datetime.now(timezone.utc).isoformat()
    _assert_fresh_at(zero, checked_at)
    _external_separate(fresh88_work, authority, repair1_artifacts, proof, Path(str(zero["catalog"]["root"])), Path(str(zero["usage"]["root"])), work)
    fresh = {"sources": {"work": str(fresh88_work.resolve()), "authority": str(authority.resolve()), "repair1_artifacts": str(repair1_artifacts.resolve())}, **fresh}
    frozen = {"format_version": 2, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "study_contract": fingerprint(CONTRACT_PATH), "runtime": _runtime_bindings(), "fresh88": fresh, "zero_cost_proof": {**zero, "freshness_checked_at": checked_at}, "cells": _frozen_cells(fresh)}
    if sum((len(cell["primary_question_ids"]) + 31) // 32 for cell in frozen["cells"]) != CONTRACT["runtime"]["maximum_logical_requests"]:
        raise ValueError("Ox v2 logical request geometry drifted")
    immutable_json(work / FROZEN_NAME, frozen)
    return frozen


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    if value.get("study_id") != CONTRACT["study_id"] or value.get("frozen_before_execution") is not True or value.get("study_contract") != fingerprint(CONTRACT_PATH) or value.get("runtime") != _runtime_bindings() or len(value.get("cells", [])) != 3:
        raise ValueError("Ox v2 frozen contract drifted")
    fresh = value.get("fresh88")
    proof = value.get("zero_cost_proof")
    sources = fresh.get("sources") if isinstance(fresh, Mapping) else None
    if not isinstance(fresh, Mapping) or not isinstance(sources, Mapping) or not isinstance(proof, Mapping) or not all(isinstance(sources.get(key), str) and sources[key] for key in ("work", "authority", "repair1_artifacts")) or not all(_binding_matches(fresh.get(key)) for key in ("execution_contract", "execution_receipt", "verifier_matrix", "semantic_gate")):
        raise ValueError("Ox v2 Fresh88 binding is malformed")
    current_proof = _zero_cost_proof(Path(str(proof.get("path", ""))))
    if proof != {**current_proof, "freshness_checked_at": proof.get("freshness_checked_at")}:
        raise ValueError("Ox v2 sealed zero-cost proof drifted")
    _assert_fresh_at(current_proof, str(proof.get("freshness_checked_at", "")))
    fresh_work, authority, artifacts = (Path(str(sources[key])) for key in ("work", "authority", "repair1_artifacts"))
    _external_separate(fresh_work, authority, artifacts, Path(str(proof.get("path", ""))), Path(str(current_proof["catalog"]["root"])), Path(str(current_proof["usage"]["root"])), work)
    current_fresh = {"sources": {"work": str(fresh_work.resolve()), "authority": str(authority.resolve()), "repair1_artifacts": str(artifacts.resolve())}, **_fresh88_binding(fresh_work, authority, artifacts)}
    if fresh != current_fresh:
        raise ValueError("Ox v2 Fresh88 authority, matrix, gate, or repair1 binding drifted")
    if value.get("cells") != _frozen_cells(current_fresh):
        raise ValueError("Ox v2 frozen cells are not the exact current Fresh88 binding")
    for cell, item_id in zip(value["cells"], CONTRACT["selection"]["item_ids"]):
        if not isinstance(cell, Mapping) or cell.get("item_id") != item_id:
            raise ValueError("Ox v2 frozen cell question geometry drifted")
        artifact, prompt, task = input_paths(cell)
        geometry = question_geometry(task)
        if (cell.get("primary_question_ids") != geometry["primary_question_ids"] or cell.get("primary_batches") != geometry["primary_batches"] or cell.get("static_question_ids") != geometry["static_question_ids"] or cell.get("task_contract_descendant") != geometry["task_contract_descendant"] or len(set(cell["primary_question_ids"])) != 179 or len(set(cell["static_question_ids"])) != 178 or set(cell["primary_question_ids"]) != set(cell["static_question_ids"]) | {CONTRACT["questions"]["dynamic_leaf_id"]}):
            raise ValueError("Ox v2 frozen cell question geometry drifted")
    return value


def input_paths(cell: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    paths = cell.get("paths")
    if not isinstance(paths, Mapping):
        raise ValueError("Ox v2 cell lacks source bindings")
    artifact, prompt, task = (Path(str(paths.get(key))).resolve() for key in ("artifact", "prompt", "task_contract"))
    expected = cell.get("inputs")
    if not isinstance(expected, Mapping) or {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)} != expected:
        raise ValueError("Ox v2 frozen public input bytes drifted")
    if read_json(task).get("artifact_id") != cell.get("item_id"):
        raise ValueError("Ox v2 task contract does not bind its judged artifact identity")
    return artifact, prompt, task


def static_ablation(verdicts: list[dict[str, Any]], task_contract: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    ids = _static_ids()
    by_id = {str(row.get("question_id")): row for row in verdicts if isinstance(row, Mapping)}
    if set(by_id) != set(ids) | {CONTRACT["questions"]["dynamic_leaf_id"]}:
        raise ValueError("Static ablation requires exactly the 179 primary verdict IDs; never slice positional prefixes")
    bundle = resolve_bundle(load_bundles(bundles_path()), CONTRACT["questions"]["bundle_id"])
    return score_bundle_v2(load_modules(registry_path()), bundle, [by_id[item] for item in ids], artifact_id=artifact_id, task_contract=_task_descendant(task_contract))
