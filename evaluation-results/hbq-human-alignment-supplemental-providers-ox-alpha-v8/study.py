"""Outcome-blind preparation and evidence bindings for Ox Alpha v8."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from hbqrs import runner

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
V2_ROOT = HERE.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v2"
V7_ROOT = HERE.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v7"
FROZEN_NAME = "frozen-ox-alpha-v8-contract.json"
V2_FILES = {
    "study.py": "ce3719c554b3b990eb0a5c729146c14f918eeb125e3baaf2b574fe5191a5c3e6",
    "analyze_pilot.py": "1c086dddd34a410a138541fdfc617dcb108ed3abede97bc2591115fbdfd095b2",
    "prepare_pilot.py": "cdcbf11fd4beb2ccd5ddfea2c0f0670d08fd1ac197934ed0ddd2e4b9401cc686",
    "run_pilot.py": "7e3864db190f13066c6b100b7c78eba2dd3b772b71ec185e61d0718c9113f4c8",
    "README.md": "749ddfb96179fb7f8888c51275dcb9a14d4cb2f72b4d326c7650a4d6afec98af",
    "study-contract.json": "4a9b94fd5a4d3801fc3354d9d3f645c05266e65d29541cec519a358eeff81bb4",
}
V7_FILES = {
    "study.py": "f1ec8f19025d2096332889deaa70ce94caade1db8fe408692cab3f9281225604",
    "verify_transport_pilot.py": "1e2b77c008f8ebf285d85a0b536d3db48314ca5b4f9289457bf39761ddef3631",
    "run_transport_pilot.py": "5282eaa8d25cd13ce154adef57d9d445620b2eac9f3095e5c73fe7120f0a471e",
    "prepare_transport_successor.py": "ed2a044e02e8cf7455e8db16c2f8da937b0b7217c27acd688dfd3b6a854e0b3c",
    "README.md": "db2bc89adfe7939ae2621623f9e6994d85d3e3c95f685d42dbe110c70e811711",
    "study-contract.json": "f1c281008ce6b3258cfb45a6f6a0a2eabd048e0969695111beff4c375d0c9aaa",
}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


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


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _external_separate(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if any(_inside(path, REPO_ROOT) for path in resolved):
        raise ValueError("v8 work and evidence roots must remain outside the repository")
    if any(left == right or _inside(left, right) or _inside(right, left) for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("v8 work and evidence roots must be distinct and non-overlapping")


def _module(path: Path, name: str, aliases: Mapping[str, Any] | None = None) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load required predecessor module: {path}")
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules[spec.name] = module
    sys.modules.update(aliases or {})
    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


def _check_parent(root: Path, files: Mapping[str, str], label: str) -> None:
    if not root.is_dir():
        raise ValueError(f"Required {label} package is unavailable")
    for name, expected in files.items():
        if sha(root / name) != expected:
            raise ValueError(f"{label} parent file drifted: {name}")


def parent_v2() -> Any:
    _check_parent(V2_ROOT, V2_FILES, "v2")
    return _module(V2_ROOT / "study.py", "ox_alpha_v8_parent_v2")


def parent_v7() -> Any:
    _check_parent(V7_ROOT, V7_FILES, "v7")
    return _module(V7_ROOT / "study.py", "ox_alpha_v8_parent_v7")


def v7_verifier(v7: Any | None = None) -> Any:
    v7 = v7 or parent_v7()
    return _module(V7_ROOT / "verify_transport_pilot.py", "ox_alpha_v8_parent_v7_verify", {"study": v7})


def _tree(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError("v7 successful root is unavailable")
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _duration(run: Path, proof: Mapping[str, Any]) -> int:
    raw = proof.get("raw_evidence")
    events = raw.get("events") if isinstance(raw, Mapping) else None
    location = events.get("path") if isinstance(events, Mapping) else None
    if not isinstance(location, str):
        raise ValueError("v7 proof does not bind raw events")
    path = (run / location).resolve()
    if not _inside(path, run) or not path.is_file():
        raise ValueError("v7 raw events escape their run")
    records = [strict_json(line, label=str(path)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [record.get("data") for record in records if isinstance(record, Mapping) and record.get("event_type") == "http_attempt"]
    if len(attempts) != 1 or not isinstance(attempts[0], Mapping):
        raise ValueError("v7 raw evidence does not have exactly one HTTP attempt")
    started, finished = attempts[0].get("http_started_monotonic_ns"), attempts[0].get("http_finished_monotonic_ns")
    if type(started) is not int or type(finished) is not int or finished <= started:
        raise ValueError("v7 raw HTTP timing is malformed")
    return finished - started


def v7_completion(work: Path) -> dict[str, Any]:
    """Re-verify the successful, immutable cap-1 predecessor before v8 freezes."""
    _external_separate(work)
    v7, verifier = parent_v7(), v7_verifier()
    result = verifier.verify_pilot(work)
    if result.get("status") != "PASS" or result.get("cells") != 3 or (work / "pilot-uncertain.json").exists():
        raise ValueError("v7 root is not a completed non-uncertain cap-1 transport pass")
    frozen = v7.load_frozen(work)
    proofs = [verifier.verify_cell(work, frozen, cell) for cell in frozen["cells"]]
    identities = {key: [str(proof[key]) for proof in proofs] for key in ("session_id", "receipt_id", "logical_request_id")}
    if any(len(set(values)) != 3 or any(not value for value in values) for values in identities.values()):
        raise ValueError("v7 does not prove three distinct provider identities")
    durations = [_duration(work / "runs" / "pilot" / str(cell["cell_id"]), proof) for cell, proof in zip(frozen["cells"], proofs)]
    if any(duration >= 150_000_000_000 for duration in durations):
        raise ValueError("v7 raw HTTP latency is not below 150 seconds")
    return {
        "root": str(work.resolve()),
        "tree": _tree(work),
        "frozen_contract": fingerprint(work / v7.FROZEN_NAME),
        "verification": result,
        "cells": [{"cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_count": len(cell["question_ids"]), "raw_http_duration_ns": duration} for cell, duration in zip(frozen["cells"], durations)],
        "global_ids": identities,
        "request_schema": v7.CONTRACT["transport_pilot"]["required_request_schema"],
        "cap1": True,
        "no_recovery": True,
    }


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    required = {"format_version", "study_id", "status", "frozen_before_execution", "purpose", "parents", "provider", "selection", "questions", "runtime", "remote_disclosure", "zero_cost", "stop_conditions", "interpretation_limits"}
    if set(value) != required or value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v8" or value.get("status") != "preregistered_full_scoring_successor_unexecuted" or value.get("frozen_before_execution") is not True:
        raise ValueError("Ox v8 contract identity drifted")
    expected_runtime = {"batch_size": 4, "expected_batches_per_item": 45, "batch_attempts": 1, "workers": 1, "maximum_logical_requests": 135, "maximum_physical_http_attempts_per_logical_request": 1, "maximum_physical_http_attempts": 135, "retry_or_fallback": "forbidden", "execution_mode": "serial", "serial_rationale": value["runtime"].get("serial_rationale")}
    if value["runtime"] != expected_runtime or not isinstance(expected_runtime["serial_rationale"], str) or not expected_runtime["serial_rationale"]:
        raise ValueError("Ox v8 cap-1 full-run geometry drifted")
    if value["selection"].get("item_ids") != ["hanna-827", "hanna-957", "hanna-201"] or value["questions"].get("primary_leaf_count") != 179 or value["questions"].get("static_leaf_count") != 178 or value["questions"].get("dynamic_leaf_id") != "task.contract.hanna.prompt_response":
        raise ValueError("Ox v8 selection or 179-leaf geometry drifted")
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "evidence_status": "provisional_only"}
    zero_cost = {"catalog_binding": "No-purchase public-HANNA pilot. Stop before any paid route, new human work, or provider upgrade.", "no_purchase": True, "stop_on_charge_signal": True, "stop_on_http_402": True}
    if value["provider"] != provider or value["zero_cost"] != zero_cost:
        raise ValueError("Ox v8 provider or no-purchase policy drifted")
    return value


CONTRACT = load_contract()


def question_geometry(task_path: Path) -> dict[str, Any]:
    base = parent_v2().question_geometry(task_path)
    batches = [base["primary_question_ids"][start:start + 4] for start in range(0, len(base["primary_question_ids"]), 4)]
    if [len(batch) for batch in batches] != [4] * 44 + [3] or len(batches) != CONTRACT["runtime"]["expected_batches_per_item"]:
        raise ValueError("Ox v8 requires forty-four four-leaf batches and one three-leaf batch")
    return {**base, "primary_batches": batches}


def judge_assets() -> dict[str, Any]:
    return parent_v7().judge_assets()


def runtime_bindings() -> dict[str, Any]:
    launcher = runner.NOUS_LAUNCHER_PATH
    return {
        "study": fingerprint(Path(__file__)), "contract": fingerprint(CONTRACT_PATH), "runner": fingerprint(Path(runner.__file__)),
        "launcher": fingerprint(launcher), "bridge": fingerprint(launcher.parent / "nous_codex_bridge.py"),
        "preparer": fingerprint(HERE / "prepare_pilot.py"), "executor": fingerprint(HERE / "run_pilot.py"), "verifier": fingerprint(HERE / "analyze_pilot.py"),
    }


def _frozen_cells(fresh: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells = fresh.get("cells")
    if not isinstance(cells, list) or len(cells) != 3:
        raise ValueError("Fresh88 selected cells are malformed")
    result = []
    for number, source in enumerate(cells, 1):
        if not isinstance(source, Mapping):
            raise ValueError("Fresh88 selected cell is malformed")
        geometry, external = source.get("geometry"), source.get("external_input")
        if not isinstance(geometry, Mapping) or not isinstance(external, Mapping):
            raise ValueError("Fresh88 cell lacks geometry or input commitments")
        task_path = Path(str(source["task_contract"]["path"]))
        current = question_geometry(task_path)
        if current["primary_question_ids"] != geometry["primary_question_ids"] or current["static_question_ids"] != geometry["static_question_ids"]:
            raise ValueError("Fresh88 and v8 exact question geometry disagree")
        result.append({
            "cell_id": f"ox-alpha-v8-{number:02d}", "item_id": source["item_id"], "ordinal": source["ordinal"],
            "inputs": {"source.md": external["source.md"], "prompt.md": external["prompt.md"], "task-contract.json": external["task-contract.json"]},
            "paths": {"artifact": source["artifact"]["path"], "prompt": source["contexts"][0]["path"], "task_contract": source["task_contract"]["path"]},
            "primary_question_ids": current["primary_question_ids"], "primary_batches": current["primary_batches"], "static_question_ids": current["static_question_ids"], "task_contract_descendant": current["task_contract_descendant"],
            "gpt_reference": {"matrix_record": source["gpt_record"], "repair1_artifacts": source["repair1_artifacts"], "primary_score": source["gpt_record"]["metrics"]["score"], "static_ablation_score": source["gpt_static_ablation"]["final_score"]["observed"]},
        })
    return result


def _zero_cost_proof(path: Path) -> dict[str, Any]:
    return parent_v2()._zero_cost_proof(path)


def assert_fresh_at(proof: Mapping[str, Any], checked_at: str) -> None:
    parent_v2()._assert_fresh_at(proof, checked_at)


def freeze_work(fresh88_work: Path, authority: Path, repair1_artifacts: Path, proof_path: Path, v7_work: Path, work: Path) -> dict[str, Any]:
    _external_separate(fresh88_work, authority, repair1_artifacts, proof_path, v7_work, work)
    if work.exists() and any(work.iterdir()):
        raise ValueError("Ox v8 preparation requires an empty external work root")
    v2 = parent_v2()
    fresh = v2._fresh88_binding(fresh88_work, authority, repair1_artifacts)
    zero, checked_at = _zero_cost_proof(proof_path), datetime.now(timezone.utc).isoformat()
    assert_fresh_at(zero, checked_at)
    predecessor = v7_completion(v7_work)
    _external_separate(fresh88_work, authority, repair1_artifacts, proof_path, Path(str(zero["catalog"]["root"])), Path(str(zero["usage"]["root"])), v7_work, work)
    fresh = {"sources": {"work": str(fresh88_work.resolve()), "authority": str(authority.resolve()), "repair1_artifacts": str(repair1_artifacts.resolve())}, **fresh}
    frozen = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "study_contract": fingerprint(CONTRACT_PATH), "runtime": runtime_bindings(), "judge_assets": judge_assets(), "fresh88": fresh, "zero_cost_proof": {**zero, "freshness_checked_at": checked_at}, "v7_transport_success": predecessor, "cells": _frozen_cells(fresh)}
    if sum(len(cell["primary_batches"]) for cell in frozen["cells"]) != CONTRACT["runtime"]["maximum_logical_requests"]:
        raise ValueError("Ox v8 logical request geometry drifted")
    immutable_json(work / FROZEN_NAME, frozen)
    return frozen


def input_paths(cell: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    paths, inputs = cell.get("paths"), cell.get("inputs")
    if not isinstance(paths, Mapping) or not isinstance(inputs, Mapping):
        raise ValueError("Ox v8 cell lacks input commitments")
    artifact, prompt, task = (Path(str(paths[key])) for key in ("artifact", "prompt", "task_contract"))
    if [fingerprint(path) for path in (artifact, prompt, task)] != [inputs["source.md"], inputs["prompt.md"], inputs["task-contract.json"]]:
        raise ValueError("Ox v8 external inputs drifted")
    return artifact, prompt, task


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    required = {"format_version", "study_id", "frozen_before_execution", "study_contract", "runtime", "judge_assets", "fresh88", "zero_cost_proof", "v7_transport_success", "cells"}
    if set(value) != required or value.get("format_version") != 1 or value.get("study_id") != CONTRACT["study_id"] or value.get("frozen_before_execution") is not True or value.get("study_contract") != fingerprint(CONTRACT_PATH) or value.get("runtime") != runtime_bindings() or value.get("judge_assets") != judge_assets():
        raise ValueError("Ox v8 frozen contract binding drifted")
    proof = value.get("zero_cost_proof")
    if not isinstance(proof, Mapping) or not isinstance(proof.get("freshness_checked_at"), str):
        raise ValueError("Ox v8 frozen zero-cost proof is malformed")
    proof_path = Path(str(proof.get("path", "")))
    if proof != {**_zero_cost_proof(proof_path), "freshness_checked_at": proof["freshness_checked_at"]}:
        raise ValueError("Ox v8 current zero-cost proof drifted")
    assert_fresh_at(proof, proof["freshness_checked_at"])
    predecessor = value.get("v7_transport_success")
    if not isinstance(predecessor, Mapping) or predecessor != v7_completion(Path(str(predecessor.get("root", "")))):
        raise ValueError("Ox v8 v7 transport predecessor changed or is invalid")
    fresh = value.get("fresh88")
    if not isinstance(fresh, Mapping) or not isinstance(fresh.get("sources"), Mapping):
        raise ValueError("Ox v8 Fresh88 binding is malformed")
    sources = fresh["sources"]
    try:
        current_fresh = {"sources": {key: str(Path(str(sources[key])).resolve()) for key in ("work", "authority", "repair1_artifacts")}, **parent_v2()._fresh88_binding(Path(str(sources["work"])), Path(str(sources["authority"])), Path(str(sources["repair1_artifacts"])))}
    except (KeyError, TypeError) as exc:
        raise ValueError("Ox v8 Fresh88 source paths are malformed") from exc
    if fresh != current_fresh:
        raise ValueError("Ox v8 exact Fresh88 GPT references drifted")
    _external_separate(work, proof_path, Path(str(proof["catalog"]["root"])), Path(str(proof["usage"]["root"])), Path(str(predecessor["root"])), *(Path(str(sources[key])) for key in ("work", "authority", "repair1_artifacts")))
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 3:
        raise ValueError("Ox v8 frozen cells are malformed")
    if cells != _frozen_cells(fresh):
        raise ValueError("Ox v8 frozen cells do not exactly reconstruct from Fresh88")
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError("Ox v8 frozen cell is malformed")
        input_paths(cell)
        ids, batches = cell.get("primary_question_ids"), cell.get("primary_batches")
        if not isinstance(ids, list) or not isinstance(batches, list) or [item for batch in batches for item in batch] != ids or [len(batch) for batch in batches] != [4] * 44 + [3] or len(ids) != 179 or len(set(ids)) != 179:
            raise ValueError("Ox v8 frozen question geometry drifted")
    return value
