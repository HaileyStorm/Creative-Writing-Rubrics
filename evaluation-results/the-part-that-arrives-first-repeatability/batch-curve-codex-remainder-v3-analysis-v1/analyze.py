"""Publish sanitized aggregates from the frozen V3 batch-curve evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
V3_CONTRACT = Path("evaluation-results/the-part-that-arrives-first-repeatability/batch-curve-codex-remainder-v3/study-contract.json")
REPAIRED_FILES = ("repeatability.json", "summary.json", "runtime-bindings.json", "tamper-tests.json")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def git_blob(repo_root: Path, head: str, relative: Path) -> bytes:
    result = subprocess.run(["git", "-C", str(repo_root), "show", f"{head}:{relative.as_posix()}"], check=False, capture_output=True)
    if result.returncode:
        raise ValueError(f"Frozen Git blob unavailable: {relative.as_posix()}")
    return result.stdout


def validate_git_binding(repo_root: Path, head: str, base: Path, item: Mapping[str, Any]) -> None:
    path = (base / str(item["path"])).resolve()
    try:
        relative = path.relative_to(repo_root.resolve())
    except ValueError as error:
        raise ValueError("Binding escaped the repository") from error
    blob = git_blob(repo_root, head, relative)
    require(len(blob) == item["bytes"] and sha256_bytes(blob) == item["sha256"], f"Frozen Git binding drifted: {relative}")


def validate_contract_bindings(repo_root: Path, head: str, contract: Mapping[str, Any]) -> None:
    base = repo_root / V3_CONTRACT.parent
    for section in ("lineage", "current_stack"):
        for item in contract[section].values():
            validate_git_binding(repo_root, head, base, item)


def validate_private_link(private_root: Path, record: Mapping[str, Any]) -> Path:
    relative = Path(str(record.get("private_path", record.get("relative_path", ""))))
    require(not relative.is_absolute() and ".." not in relative.parts, "Private reference escaped its root")
    path = private_root / relative
    require(path.is_file(), "Committed private evidence is missing")
    expected_bytes = record.get("private_bytes", record.get("bytes"))
    expected_sha256 = record.get("private_sha256", record.get("sha256"))
    require(path.stat().st_size == expected_bytes and sha256_file(path) == expected_sha256, "Public-to-private commitment drifted")
    return path


def validate_run_scores(private_root: Path, accepted: Mapping[str, Any]) -> None:
    index = validate_private_link(private_root, accepted["raw_evidence_index"])
    run_relative = Path(str(read_json(index)["run_path"]))
    require(not run_relative.is_absolute() and ".." not in run_relative.parts, "Run path escaped its root")
    run = (private_root / run_relative).resolve()
    try:
        run.relative_to(private_root.resolve())
    except ValueError as error:
        raise ValueError("Run path escaped its root") from error
    expected = {"run_sha256": "run.json", "score_sha256": "score.json", "score_v2_sha256": "score.v2.json"}
    for field, name in expected.items():
        path = run / name
        require(path.is_file() and accepted[field] == sha256_file(path), f"Public {field} drifted")


def leaf_grounded(leaf: Mapping[str, Any]) -> bool:
    return any("exact_quote" in item for item in leaf.get("evidence", []))


def validate_execution(public_root: Path, private_root: Path, contract: Mapping[str, Any], inherited_failed_preflights: int) -> dict[str, Any]:
    receipt_path, terminal_path = public_root / "preexecution-disclosure-receipt.json", public_root / "analysis.json"
    receipt, terminal = read_json(receipt_path), read_json(terminal_path)
    require(receipt["study_id"] == contract["study_id"] == terminal["study_id"], "Study identity drifted")
    require(receipt["git"]["head"] == contract["execution_data_head"], "Execution data head drifted")
    for field, expected in contract["expected_terminal"].items():
        require(terminal[field] == expected, f"Terminal {field} drifted")
    require(terminal["screening_recommendation"] is None, "Terminal recommendation must remain absent")
    preflights = sorted(public_root.glob("preflights/epoch-*/refresh-*.json"))
    require(len(preflights) == 6, "Expected six successful V3 preflights")
    for path in preflights:
        record = read_json(path)
        require(record["status"] == "accepted", "Preflight was not accepted")
        validate_private_link(private_root, record)
    cells = sorted((public_root / "cells").glob("cell-*.json"))
    require(len(cells) == 47, "Expected exactly 47 completed V3 cells")
    for path in cells:
        cell = read_json(path)
        require(cell["status"] == "completed" and len(cell["calls"]) == 2, "Cell attempt accounting drifted")
        validate_run_scores(private_root, cell["calls"][1])
    return {"execution_data_head": receipt["git"]["head"], "receipt_sha256": sha256_file(receipt_path), "terminal_analysis_sha256": sha256_file(terminal_path), "scored_units": len(cells), "successful_preflights": len(preflights), "inherited_failed_preflights": inherited_failed_preflights}


def validate_repaired_root(root: Path, contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str], int]:
    manifest = read_json(root / "manifest.json")
    repaired = contract["repaired_settlement"]
    require(sha256_file(root / "manifest.json") == repaired["manifest_sha256"], "Repaired manifest drifted")
    require(manifest["format_version"] == repaired["format_version"] and manifest["analysis_script_sha256"] == repaired["analysis_script_sha256"], "Repaired manifest identity drifted")
    listed = {item["path"]: item for item in manifest["files"]}
    require(len(listed) == len(manifest["files"]) and set(listed) == set(repaired["members"]), "Repaired manifest membership drifted")
    analyzer = root / "analyze.py"
    require(analyzer.is_file() and sha256_file(analyzer) == repaired["analysis_script_sha256"], "Repaired analyzer bytes drifted")
    for name in repaired["members"]:
        path = root / name
        require(path.is_file() and listed[name]["bytes"] == path.stat().st_size and listed[name]["sha256"] == sha256_file(path), f"Repaired settlement drifted: {name}")
    summary, repeatability, tamper = read_json(root / "summary.json"), read_json(root / "repeatability.json"), read_json(root / "tamper-tests.json")
    require(summary["repeatability"] == repeatability and summary["screening_recommendation"] is None, "Repaired result consistency drifted")
    require(set(tamper) == set(repaired["required_tamper_gates"]) and all(tamper.values()), "Repaired tamper gates are incomplete or false")
    inherited_failed = summary["evidence"]["preflight_commitments"]["inherited_failed"]
    require(inherited_failed == contract["expected_inherited_failed_preflights"], "Repaired inherited preflight accounting drifted")
    for size, expected in contract["expected_quote_grounding_rates"].items():
        require(repeatability[size]["metrics"]["exact_quote_grounding_rate"] == expected, f"Quote grounding drifted: {size}")
    return repeatability, {name: listed[name]["sha256"] for name in REPAIRED_FILES}, inherited_failed


def validate_repaired_runtime(repo_root: Path, head: str, repaired_root: Path, contract: Mapping[str, Any]) -> None:
    runtime = read_json(repaired_root / "runtime-bindings.json")
    for name in ("registry", "bundles"):
        item = runtime[name]
        blob = git_blob(repo_root, head, Path(item["path"]))
        require(len(blob) == item["bytes"] and sha256_bytes(blob) == item["sha256"], f"Executed {name} Git bytes drifted")
    expected_modules = contract["required_runtime"]["modules"]
    require(runtime["executed_hbqrs_modules"] == expected_modules, "Executed HBQ runtime module set drifted")
    for module in expected_modules:
        blob = git_blob(repo_root, head, Path(module["path"]))
        require(sha256_bytes(blob) == module["sha256"], f"Executed runtime Git bytes drifted: {module['path']}")
    harness = contract["required_runtime"]["harness"]
    require(sha256_bytes(git_blob(repo_root, head, Path(harness["path"]))) == harness["sha256"], "Executed harness Git bytes drifted")


def publication(repeatability: Mapping[str, Any], execution: Mapping[str, Any], repaired_files: Mapping[str, str], contract: Mapping[str, Any], analysis_contract_sha256: str) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": contract["study_id"],
        "status": "completed_offline_settlement_no_recommendation",
        "execution": dict(execution),
        "analysis_contract_sha256": analysis_contract_sha256,
        "repaired_settlement": {"input_manifest_sha256": contract["repaired_settlement"]["manifest_sha256"], "result_file_sha256": dict(repaired_files)},
        "previous_debug_settlement": contract["previous_debug_settlement"],
        "repeatability": repeatability,
        "screening_recommendation": None,
        "interpretation": "The completed third repetitions cover only batch sizes 4, 8, 32, and 48. This reports deterministic within-condition repeatability, not validity, calibration, human preference, or a production-size recommendation.",
        "privacy": {"contains_private_evidence": False, "contains_prompts": False, "contains_sessions": False},
    }


def publish(output_dir: Path, result: Mapping[str, Any]) -> None:
    require(not output_dir.exists(), "Output directory must be fresh")
    output_dir.mkdir(parents=True)
    write_json(output_dir / "summary.json", result)
    write_json(output_dir / "repeatability.json", result["repeatability"])
    provenance = {"format_version": 1, "execution_data_head": result["execution"]["execution_data_head"], "execution_commitments": {key: value for key, value in result["execution"].items() if key.endswith("sha256") or key.endswith("units") or key.endswith("preflights")}, "analysis_contract_sha256": result["analysis_contract_sha256"], "repaired_input_manifest_sha256": result["repaired_settlement"]["input_manifest_sha256"], "repaired_result_file_sha256": result["repaired_settlement"]["result_file_sha256"], "previous_debug_settlement": result["previous_debug_settlement"], "privacy": result["privacy"]}
    write_json(output_dir / "provenance.json", provenance)
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in sorted(output_dir.glob("*.json"))]
    write_json(output_dir / "manifest.json", {"format_version": 1, "analysis_script_sha256": sha256_file(Path(__file__)), "files": files})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--execution-public-root", type=Path, required=True)
    parser.add_argument("--execution-private-root", type=Path, required=True)
    parser.add_argument("--repaired-settlement-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    contract_path = HERE / "analysis-contract.json"
    contract = read_json(contract_path)
    v3_contract = json.loads(git_blob(args.repo_root, contract["execution_data_head"], V3_CONTRACT))
    require(v3_contract["study_id"] == contract["study_id"], "V3 contract study identity drifted")
    validate_contract_bindings(args.repo_root, contract["execution_data_head"], v3_contract)
    repeatability, repaired_files, inherited_failed = validate_repaired_root(args.repaired_settlement_root, contract)
    execution = validate_execution(args.execution_public_root, args.execution_private_root, contract, inherited_failed)
    validate_repaired_runtime(args.repo_root, contract["execution_data_head"], args.repaired_settlement_root, contract)
    publish(args.output_dir, publication(repeatability, execution, repaired_files, contract, sha256_file(contract_path)))


if __name__ == "__main__":
    main()
