"""Offline, provenance-bound full-ladder batch-curve settlement; no provider client exists here."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
V3_CONTRACT = Path("evaluation-results/the-part-that-arrives-first-repeatability/batch-curve-codex-remainder-v3/study-contract.json")
PARENT_CONTRACT = Path("evaluation-results/the-part-that-arrives-first-repeatability/batch-curve-codex-v1/codex-execution-contract.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def safe_relative(value: object, label: str) -> Path:
    relative = Path(str(value))
    require(not relative.is_absolute() and ".." not in relative.parts, f"{label} escaped its root")
    return relative


def root_commitment(root: Path) -> str:
    members = [
        {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]
    return hashlib.sha256(json.dumps(members, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def blob(repo: Path, head: str, relative: Path) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{head}:{relative.as_posix()}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"Frozen Git blob unavailable: {relative}")
    return result.stdout


def validate_binding_group(repo: Path, head: str, bindings: Mapping[str, Mapping[str, Any]], prefix: str, base: Path = Path(".")) -> None:
    for name, item in bindings.items():
        relative = (base / str(item["path"])).resolve().relative_to(repo.resolve()); value = blob(repo, head, relative)
        require(len(value) == item["bytes"] and hashlib.sha256(value).hexdigest() == item["sha256"], f"Frozen binding drifted: {prefix}.{name}")


def validate_runtime(repo: Path, runtime: Path, contract: Mapping[str, Any]) -> None:
    binding = contract["analysis_runtime"]; head = binding["git_head"]
    validate_binding_group(repo, head, binding["files"], "analysis_runtime", repo)
    for name, item in binding["files"].items():
        path = runtime / item["path"]
        require(path.is_file() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], f"Analysis runtime drifted: {name}")


def validate_parent_bindings(repo: Path, contract: Mapping[str, Any]) -> None:
    parent = json.loads(blob(repo, contract["parent_execution_head"], PARENT_CONTRACT))
    base = repo / PARENT_CONTRACT.parent
    # The historical contract is itself receipt-bound. Its registry assertions were
    # already stale at that recorded head, so this settlement does not relabel them
    # as an exact execution stack; the exact scorer stack is analysis_runtime.
    validate_binding_group(repo, contract["parent_execution_head"], {"source": parent["frozen_inputs"]["source"], "response_schema": parent["frozen_inputs"]["response_schema"]}, "parent.receipt_inputs", base)


def validate_v3_bindings(repo: Path, contract: Mapping[str, Any]) -> Mapping[str, Any]:
    head = contract["v3_execution_head"]; value = blob(repo, head, V3_CONTRACT)
    require(hashlib.sha256(value).hexdigest() == contract["v3_contract_sha256"], "V3 contract byte drifted")
    v3 = json.loads(value)
    base = repo / V3_CONTRACT.parent
    validate_binding_group(repo, head, v3["lineage"], "v3.lineage", base)
    validate_binding_group(repo, head, v3["current_stack"], "v3.current_stack", base)
    return v3


def bound_private(root: Path, record: Mapping[str, Any]) -> Path:
    relative = safe_relative(record.get("relative_path", record.get("private_path", "")), "Private reference")
    path = (root / relative).resolve()
    require(path.is_file() and path.is_relative_to(root.resolve()), "Private evidence is missing or escaped")
    expected_bytes, expected_sha = record.get("bytes", record.get("private_bytes")), record.get("sha256", record.get("private_sha256"))
    require(path.stat().st_size == expected_bytes and sha(path) == expected_sha, "Private commitment drifted")
    return path


def validate_private_index(private: Path, accepted: Mapping[str, Any]) -> tuple[Path, Mapping[str, Any]]:
    index_path = bound_private(private, accepted["raw_evidence_index"]); index = read(index_path)
    require(index["private_root_sha256"] == accepted["raw_evidence_index"]["private_root_sha256"], "Private root commitment drifted")
    run_path = safe_relative(index["run_path"], "Run path"); members = index["files"]
    require(isinstance(members, list) and members, "Private evidence index is empty")
    seen: set[str] = set()
    for item in members:
        relative = safe_relative(item["path"], "Indexed private file"); key = relative.as_posix()
        require(key not in seen, "Private evidence index duplicated a file"); seen.add(key)
        path = (private / relative).resolve()
        require(path.is_file() and path.is_relative_to(private.resolve()), "Private evidence member missing or escaped")
        require(path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], "Private evidence member drifted")
    run = (private / run_path).resolve()
    require(run.is_dir() and run.is_relative_to(private.resolve()), "Run is missing or escaped")
    return run, index


def bound_run(private: Path, accepted: Mapping[str, Any]) -> Path:
    run, _ = validate_private_index(private, accepted)
    for field, name in {"run_sha256": "run.json", "score_sha256": "score.json", "score_v2_sha256": "score.v2.json"}.items():
        require((run / name).is_file() and accepted[field] == sha(run / name), f"Run commitment drifted: {field}")
    return run


def collect_sessions(accepted: Mapping[str, Any], seen: set[str], label: str) -> None:
    sessions = accepted.get("sessions"); require(isinstance(sessions, list) and sessions, f"Missing accepted sessions: {label}")
    for item in sessions:
        value = item.get("session_id_sha256")
        require(is_sha(value), f"Malformed session commitment: {label}")
        require(value not in seen, f"Session overlap or resend: {label}"); seen.add(value)


def register_session(value: object, seen: set[str], label: str) -> None:
    require(is_sha(value), f"Malformed session commitment: {label}")
    require(value not in seen, f"Session overlap or resend: {label}"); seen.add(value)


def require_no_session_overlap(parent_sessions: set[str], recovery_sessions: set[str]) -> None:
    require(not parent_sessions.intersection(recovery_sessions), "V3 session overlaps parent evidence")


def validate_parent_rejections(private: Path, contract: Mapping[str, Any], seen: set[str]) -> None:
    expected = contract["parent_geometry"]["quota_rejections"]
    require(len(expected) == 3, "Parent quota-rejection geometry drifted")
    previous: str | None = None
    for item in expected:
        path = private / safe_relative(item["path"], "Parent rejection")
        require(path.is_file() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], "Parent quota rejection drifted")
        value = read(path)
        require(value["attempt"] == item["attempt"] and value["stage"] == "provider_transport" and value["retryable"] is True, "Parent rejection semantics drifted")
        require(value["previous_rejected_sha256"] == previous, "Parent rejection chain drifted")
        register_session(value["provider_session_id_sha256"], seen, "parent rejection")
        previous = item["sha256"]


def validate_parent_prefix_batches(private: Path, contract: Mapping[str, Any], seen: set[str]) -> list[list[dict[str, Any]]]:
    expected = contract["parent_geometry"]["prefix_batches"]
    require([item["batch"] for item in expected] == list(range(1, 32)), "Parent prefix batch geometry drifted")
    runs: list[list[dict[str, Any]]] = []
    for item in expected:
        batch = item["batch"]
        path = private / "runs/cell-36/responses" / f"batch-{batch:04d}.json"
        require(path.is_file() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], "Parent prefix batch bytes drifted")
        value = read(path)
        require(value["batch"] == batch and value["accepted_attempt"] == 1, "Parent prefix acceptance drifted")
        require(value["rejected_chain"] == {"count": 0, "head_sha256": None}, "Parent prefix retry semantics drifted")
        reported = value["provider"]["reported"]
        require(reported["provider"] == "openai" and reported["model"] == "gpt-5.6-sol" and reported["reasoning_effort"] == "high", "Parent prefix provider semantics drifted")
        session = hashlib.sha256(reported["session_id"].encode("utf-8")).hexdigest()
        require(session == item["session_id_sha256"], "Parent prefix session commitment drifted")
        register_session(session, seen, "parent prefix")
        response = value["response_artifact"]
        response_path = (private / "runs/cell-36" / safe_relative(response["path"], "Parent prefix response")).resolve()
        require(response_path.is_file() and response_path.is_relative_to(private.resolve()), "Parent prefix response escaped or missing")
        require(response_path.stat().st_size == response["bytes"] and sha(response_path) == response["sha256"] == value["response_sha256"], "Parent prefix response drifted")
        verdicts, ids = value["normalized_verdicts"], value["question_ids"]
        require(len(verdicts) == 4 and [row["question_id"] for row in verdicts] == ids and len(set(ids)) == 4, "Parent prefix verdict semantics drifted")
        runs.append(verdicts)
    require(len({row["question_id"] for run in runs for row in run}) == 124, "Parent prefix question overlap drifted")
    return runs


def parent_rows(repo: Path, public: Path, private: Path, contract: Mapping[str, Any]) -> tuple[dict[tuple[int | str, int], list[dict[str, Any]]], set[str], list[list[dict[str, Any]]]]:
    receipt = read(public / "preexecution-disclosure-receipt.json"); geometry = contract["parent_geometry"]
    require(sha(public / "preexecution-disclosure-receipt.json") == geometry["receipt_sha256"], "Parent receipt drifted")
    require(root_commitment(public) == geometry["public_root_sha256"], "Parent public root drifted")
    require(receipt["git"]["commit"] == contract["parent_execution_head"], "Parent execution head drifted")
    parent_contract = blob(repo, contract["parent_execution_head"], PARENT_CONTRACT)
    require(hashlib.sha256(parent_contract).hexdigest() == receipt["contract_sha256"], "Parent execution contract drifted")
    require(receipt["private_evidence_root_sha256"] == geometry["private_root_sha256"], "Parent private-root commitment drifted")
    cells = sorted((public / "cells").glob("cell-*.json")); require(len(cells) == geometry["public_cell_count"], "Parent public-cell geometry drifted")
    completed = [path for path in cells if read(path).get("status") == "completed"]
    require(len(completed) == contract["expected_parent_cells"] and len(cells) - len(completed) == 1, "Parent completed-cell geometry drifted")
    rows: dict[tuple[int | str, int], list[dict[str, Any]]] = {}; sessions: set[str] = set()
    for path in completed:
        cell = read(path); plan, calls = cell["plan"], cell["calls"]
        require(len(calls) == 2 and calls[0]["event"] == "attempt_started" and calls[1]["event"] == "accepted", "Parent accepted-attempt geometry drifted")
        accepted = calls[1]; require(accepted.get("rejected_attempt_count") == 0, "Unexpected parent accepted retry")
        collect_sessions(accepted, sessions, path.name); run = bound_run(private, accepted); verdicts = lines(run / "verdicts.jsonl")
        require(len(verdicts) == 178 and len({row["question_id"] for row in verdicts}) == 178, "Parent verdict sequence drifted")
        key = (plan["size"], plan["repetition"]); require(key not in rows, "Parent cell key duplicated"); rows[key] = verdicts
    prefix = validate_parent_prefix_batches(private, contract, sessions)
    validate_parent_rejections(private, contract, sessions)
    return rows, sessions, prefix


def expected_v3_schedule() -> dict[int, range]:
    return {36: range(32, 46), 37: range(1, 7), 38: range(1, 24), 39: range(1, 5)}


def v3_rows(repo: Path, public: Path, private: Path, prefix: list[list[dict[str, Any]]], contract: Mapping[str, Any], parent_sessions: set[str]) -> dict[tuple[int | str, int], list[dict[str, Any]]]:
    receipt, terminal = read(public / "preexecution-disclosure-receipt.json"), read(public / "analysis.json"); geometry = contract["v3_geometry"]
    require(sha(public / "preexecution-disclosure-receipt.json") == geometry["receipt_sha256"] and sha(public / "analysis.json") == geometry["terminal_sha256"], "V3 public receipt or terminal drifted")
    require(root_commitment(public) == geometry["public_root_sha256"], "V3 public root drifted")
    contract_sha = contract["v3_contract_sha256"]
    require(receipt["contract_sha256"] == contract_sha and terminal["contract_sha256"] == contract_sha, "V3 contract receipt drifted")
    require(receipt["git"]["head"] == contract["v3_execution_head"] and terminal["completed_units"] == contract["expected_v3_cells"], "V3 terminal identity drifted")
    require(receipt["private_evidence_root_sha256"] == geometry["private_root_sha256"], "V3 private-root commitment drifted")
    cells = sorted((public / "cells").glob("cell-*.json")); require(len(cells) == contract["expected_v3_cells"], "V3 cell count drifted")
    expected = expected_v3_schedule(); received: dict[int, set[int]] = {cell: set() for cell in expected}; grouped: dict[int, list[tuple[int, list[dict[str, Any]]]]] = {}; v3_sessions: set[str] = set()
    for path in cells:
        cell = read(path); plan, calls = cell["plan"], cell["calls"]; parent_cell, batch = plan["parent_cell"], plan["batch"]
        require(parent_cell in expected and batch in expected[parent_cell] and batch not in received[parent_cell], "V3 batch schedule drifted"); received[parent_cell].add(batch)
        require(cell["status"] == "completed" and len(calls) == 2 and calls[0]["event"] == "attempt_started" and calls[1]["event"] == "accepted", "V3 accepted-attempt geometry drifted")
        accepted = calls[1]; collect_sessions(accepted, v3_sessions, path.name); run = bound_run(private, accepted); verdicts = lines(run / "verdicts.jsonl")
        require([row["question_id"] for row in verdicts] == plan["question_ids"], "V3 verdict order drifted"); grouped.setdefault(parent_cell, []).append((batch, verdicts))
    require(received == {cell: set(ranges) for cell, ranges in expected.items()}, "V3 schedule ranges drifted")
    require_no_session_overlap(parent_sessions, v3_sessions)
    rows: dict[tuple[int | str, int], list[dict[str, Any]]] = {(4, 3): [item for run in [*prefix, *(verdicts for _, verdicts in sorted(grouped[36]))] for item in run]}
    for parent_cell, size in ((37, 32), (38, 8), (39, 48)):
        rows[(size, 3)] = [item for _, run in sorted(grouped[parent_cell]) for item in run]
    for key, run in rows.items():
        require(len(run) == 178 and len({item["question_id"] for item in run}) == 178, f"V3 reconstructed repetition drifted: {key}")
    return rows


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate_executed_hbqrs(runtime: Path, contract: Mapping[str, Any]) -> None:
    names = {"hbqrs": "hbqrs", "core": "hbqrs.core", "paths": "hbqrs.paths", "runner": "hbqrs.runner", "scoring_v2": "hbqrs.scoring_v2", "weights": "hbqrs.weights"}
    for key, module_name in names.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        item = contract["analysis_runtime"]["files"][key]
        path = Path(str(getattr(module, "__file__", ""))).resolve()
        expected = (runtime / item["path"]).resolve()
        require(path == expected and path.is_file() and sha(path) == item["sha256"], f"Preloaded or wrong HBQRS module: {module_name}")


def analyze(rows: Mapping[tuple[int | str, int], list[dict[str, Any]]], runtime: Path, contract: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sys.path.insert(0, str(runtime / "src"))
    from hbqrs import core, load_bundles, load_modules
    validate_executed_hbqrs(runtime, contract)
    harness = load_module(runtime / contract["analysis_runtime"]["files"]["harness"]["path"], "full_ladder_harness")
    modules = load_modules(runtime / "registry/all_modules.json")
    bundle = next(item for item in load_bundles(runtime / "bundles/all_bundles.json") if item["bundle_id"] == "prose.short_story")
    output: dict[str, Any] = {}; states: dict[int | str, str] = {}
    for size in contract["sizes"]:
        runs = [rows[(size, repetition)] for repetition in (1, 2, 3)]; ids = [item["question_id"] for item in runs[0]]
        require(len(ids) == 178 and len(set(ids)) == 178 and all([item["question_id"] for item in run] == ids for run in runs), f"Full ladder sequence drifted: {size}")
        reports = [core.score_bundle(modules, bundle, run, artifact_id="the-part-that-arrives-first") for run in runs]
        scores, coverage = [report["base_score"]["observed"] for report in reports], [report["coverage"] for report in reports]
        metric_runs = [[{**item, "canonical_observed_score": score, "strict_schema_conformant": True, "exact_quote_grounded": any("exact_quote" in evidence for evidence in item.get("evidence", []))} for item in run] for score, run in zip(scores, runs, strict=True)]
        metrics = harness.repeatability_metrics(metric_runs); metrics["canonical_coverage"] = coverage; metrics["mean_canonical_coverage"] = sum(coverage) / 3
        state = harness.screening_state(metrics, contract["thresholds"]); output[str(size)] = {"scores": scores, "metrics": metrics, "screening_state": state}; states[size] = state
    return output, harness.bracket_transitions(states)


def write(path: Path, value: Any) -> None:
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def public_projection_is_safe(value: Mapping[str, Any]) -> None:
    forbidden = {"raw_evidence_index", "run_path", "sessions", "session_id_sha256", "prompt", "prompt_sha256", "private_root_sha256"}
    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            require(not forbidden.intersection(item), "Public projection leaked private evidence")
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True); parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--parent-public-root", type=Path, required=True); parser.add_argument("--parent-private-root", type=Path, required=True)
    parser.add_argument("--v3-public-root", type=Path, required=True); parser.add_argument("--v3-private-root", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv); require(not args.output_dir.exists(), "Output directory must be fresh")
    contract_path = HERE / "analysis-contract.json"; contract = read(contract_path)
    validate_parent_bindings(args.repo_root, contract); validate_v3_bindings(args.repo_root, contract); validate_runtime(args.repo_root, args.runtime_root, contract)
    rows, parent_sessions, prefix = parent_rows(args.repo_root, args.parent_public_root, args.parent_private_root, contract)
    rows.update(v3_rows(args.repo_root, args.v3_public_root, args.v3_private_root, prefix, contract, parent_sessions))
    require(set(rows) == {(size, repetition) for size in contract["sizes"] for repetition in (1, 2, 3)}, "Full ladder is incomplete")
    results, transitions = analyze(rows, args.runtime_root, contract); args.output_dir.mkdir(parents=True)
    summary = {"format_version": 2, "study_id": contract["study_id"], "status": "completed_offline_full_ladder_no_recommendation", "analysis_contract_sha256": sha(contract_path), "parent_execution_head": contract["parent_execution_head"], "v3_execution_head": contract["v3_execution_head"], "completed_sizes": contract["sizes"], "repeatability": results, "transitions": transitions, "screening_recommendation": None, "privacy": {"contains_private_evidence": False, "contains_prompts": False, "contains_sessions": False}}
    public_projection_is_safe(summary); write(args.output_dir / "repeatability.json", results); write(args.output_dir / "summary.json", summary)
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(args.output_dir.glob("*.json"))]
    manifest = {"format_version": 2, "analysis_script_sha256": sha(Path(__file__)), "analysis_contract_sha256": sha(contract_path), "files": files}
    public_projection_is_safe(manifest); write(args.output_dir / "manifest.json", manifest)


if __name__ == "__main__":
    main()
