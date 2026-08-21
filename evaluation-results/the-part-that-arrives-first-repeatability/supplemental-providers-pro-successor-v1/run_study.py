#!/usr/bin/env python3
"""Run the hash-bound Nous Pro successor after validating Flash's failed execution."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "study-contract.json"
JOURNAL_NAME = "schedule-journal.jsonl"
EXPECTED_SCHEDULE = {
    "kind": "five_block_near_latin",
    "execution": "serial_in_listed_order",
    "blocks": [["hbq", "naplan", "cambridge", "oregon"], ["naplan", "cambridge", "oregon", "hbq"], ["cambridge", "oregon", "hbq", "naplan"], ["oregon", "hbq", "naplan", "cambridge"], ["hbq", "naplan", "cambridge", "oregon"]],
    "maximum_position_imbalance": 1,
}


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


CONTRACT = read(CONTRACT_PATH)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _v3():
    path = HERE.parent / "supplemental-providers-v3" / "run_study.py"
    spec = importlib.util.spec_from_file_location("pro_successor_v3_runner", path)
    if spec is None or spec.loader is None:
        raise ValueError("Supplemental-provider v3 runner is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _implementation_paths() -> dict[str, Path]:
    return {"runner": HERE / "run_study.py", "analyzer": HERE / "analyze_study.py"}


def _planned(provider_id: str) -> list[dict[str, Any]]:
    contract_hash = sha(CONTRACT_PATH)
    return [
        {
            "format_version": 1,
            "event": "planned",
            "provider_id": provider_id,
            "sequence": (block - 1) * 4 + position,
            "block": block,
            "position": position,
            "method_id": method,
            "run_id": f"run-{block:02d}",
            "protocol_contract_sha256": contract_hash,
            "successor_v3_contract_sha256": CONTRACT["successor_of"]["study_contract_sha256"],
            "schedule_sha256": canonical(CONTRACT["schedule"]),
            "parity_sha256": canonical(CONTRACT["parity"]),
            "flash_trigger_sha256": canonical(CONTRACT["flash_execution_trigger"]),
        }
        for block, methods in enumerate(CONTRACT["schedule"]["blocks"], 1)
        for position, method in enumerate(methods, 1)
    ]


def schedule_events() -> list[dict[str, Any]]:
    return _planned(CONTRACT["provider"]["provider_id"])


def _append(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("Journal write was partial")
        os.fsync(fd)
    finally:
        os.close(fd)


def _journal(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Journal contains a non-object event")
    return rows


def _binding(work: Path, method_id: str, run_id: str) -> Path:
    return work / "providers" / CONTRACT["provider"]["provider_id"] / method_id / run_id / ("run.json" if method_id == "hbq" else "pass.json")


def _prepare_journal(work: Path) -> tuple[Path, int]:
    path = work / "providers" / CONTRACT["provider"]["provider_id"] / JOURNAL_NAME
    plans, rows = schedule_events(), _journal(path)
    if not rows:
        for event in plans:
            _append(path, event)
        return path, 0
    planned_count = min(len(rows), len(plans))
    if rows[:planned_count] != plans[:planned_count]:
        raise ValueError("Journal planned events do not bind to the frozen successor protocol")
    if len(rows) < len(plans):
        for event in plans[len(rows):]:
            _append(path, event)
        return path, 0
    completions = rows[len(plans):]
    if len(completions) > len(plans):
        raise ValueError("Journal has too many completion events")
    for expected, actual in zip(plans, completions):
        binding = _binding(work, expected["method_id"], expected["run_id"])
        fields = {key: value for key, value in expected.items() if key != "event"}
        if actual.get("event") != "completed" or {key: actual.get(key) for key in fields} != fields or not binding.is_file() or actual.get("run_binding_sha256") != sha(binding):
            raise ValueError("Journal completion is missing, reordered, or no longer binds its manifest")
    return path, len(completions)


def validate_flash_trigger(flash_work: Path) -> None:
    trigger = CONTRACT["flash_execution_trigger"]
    journal = flash_work / trigger["journal_path"]
    if not journal.is_file() or sha(journal) != trigger["journal_sha256"]:
        raise ValueError("Flash trigger journal does not match the frozen failed execution")
    rows = _journal(journal)
    if len(rows) != trigger["planned_event_count"] + trigger["completed_event_count"]:
        raise ValueError("Flash trigger completion count drifted")
    plans, completions = rows[: trigger["planned_event_count"]], rows[trigger["planned_event_count"] :]
    if [row.get("event") for row in plans] != ["planned"] * len(plans) or [row.get("sequence") for row in plans] != list(range(1, 21)):
        raise ValueError("Flash trigger schedule is malformed")
    if len(completions) != 1 or completions[0].get("event") != "completed" or completions[0].get("provider_id") != trigger["provider_id"] or completions[0].get("method_id") != "hbq" or completions[0].get("run_id") != "run-01" or completions[0].get("run_binding_sha256") != trigger["completed_hbq_run_binding_sha256"]:
        raise ValueError("Flash trigger does not prove the lone completed HBQ slot")
    hbq = trigger["completed_hbq_manifest"]
    hbq_path = flash_work / hbq["path"]
    if not hbq_path.is_file() or hbq_path.stat().st_size != hbq["bytes"] or sha(hbq_path) != hbq["sha256"] or hbq["sha256"] != trigger["completed_hbq_run_binding_sha256"]:
        raise ValueError("Flash completed HBQ manifest does not match the frozen trigger")
    manifest = trigger["naplan_pass_manifest"]
    manifest_path = flash_work / manifest["path"]
    if not manifest_path.is_file() or manifest_path.stat().st_size != manifest["bytes"] or sha(manifest_path) != manifest["sha256"]:
        raise ValueError("Flash trigger NAPLAN pass manifest does not match the frozen failed execution")
    if any((flash_work / path).exists() for path in trigger["required_absent_paths"]):
        raise ValueError("Flash trigger unexpectedly contains an accepted NAPLAN result")
    for expected in trigger["semantic_rejections"]:
        path = flash_work / expected["path"]
        if not path.is_file() or path.stat().st_size != expected["bytes"] or sha(path) != expected["sha256"]:
            raise ValueError("Flash semantic-rejection artifact does not match the frozen trigger")
        record = read(path)
        if record.get("reason") != expected["reason"]:
            raise ValueError("Flash semantic-rejection reason does not match the frozen trigger")


def preflight(flash_work: Path) -> tuple[dict[str, Any], Path]:
    v3 = _v3()
    v3.preflight()
    provider = CONTRACT.get("provider", {})
    expected_provider = ("nous_pro_max", "nous", "deepseek/deepseek-v4-pro-0813", "max", True, ["deepseek/deepseek-v4-pro-0813", "deepseek/deepseek-v4-pro-20260813"], "deepseek/deepseek-v4-pro-20260813", True, True, True)
    observed_provider = (provider.get("provider_id"), provider.get("provider"), provider.get("model"), provider.get("reasoning"), provider.get("allow_unattested_reasoning"), provider.get("reported_models"), provider.get("provider_canonical_model"), provider.get("provisional_reasoning"), provider.get("no_purchase"), provider.get("stop_on_http_402"))
    if CONTRACT.get("format_version") != 1 or CONTRACT.get("frozen_before_execution") is not True or CONTRACT.get("repetitions") != 5 or observed_provider != expected_provider or CONTRACT.get("schedule") != EXPECTED_SCHEDULE or CONTRACT["schedule"]["blocks"] != v3.CONTRACT["schedule"]["blocks"]:
        raise ValueError("Nous Pro successor protocol drifted")
    successor = CONTRACT["successor_of"]
    if sha(HERE.parent / "supplemental-providers-v3" / "study-contract.json") != successor["study_contract_sha256"] or sha(HERE.parent / "supplemental-providers-v3" / "run_study.py") != successor["runner_sha256"] or sha(HERE.parent / "supplemental-providers-v3" / "analyze_study.py") != successor["analyzer_sha256"]:
        raise ValueError("Successor no longer binds the immutable v3 implementation")
    for name, path in _implementation_paths().items():
        if CONTRACT["implementation_hashes"].get(name) != sha(path):
            raise ValueError("Successor implementation hash drifted")
    parity = CONTRACT["parity"]
    source = (HERE / parity["source"]["path"]).resolve()
    if not source.is_file() or source.stat().st_size != parity["source"]["bytes"] or sha(source) != parity["source"]["sha256"] or parity["hbq"] != {key: v3.CONTRACT["hbq"][key] for key in parity["hbq"]} or parity["native_runtime"] != v3.CONTRACT["native_runtime"]:
        raise ValueError("Successor source or HBQ/native parity drifted")
    v3_methods = {item["method_id"]: item for item in v3.CONTRACT["methods"]}
    if [item["method_id"] for item in parity["methods"]] != [item["method_id"] for item in v3.CONTRACT["methods"]]:
        raise ValueError("Successor method order drifted")
    for method in parity["methods"]:
        parent = v3_methods[method["method_id"]]
        if method["kind"] != parent["kind"] or method["reference_arm"] != parent["reference_arm"]:
            raise ValueError("Successor method parity drifted")
        for key in ("prompt", "schema"):
            if key in method and method[key] != parent[key]:
                raise ValueError("Successor native asset path drifted")
        for key in ("prompt", "schema"):
            if key in method and sha((HERE / method[key]).resolve()) != method[f"{key}_sha256"]:
                raise ValueError("Successor native asset hash drifted")
    validate_flash_trigger(flash_work)
    return CONTRACT, source


def execute(work: Path, flash_work: Path, timeout: float) -> None:
    preflight(flash_work)
    work.mkdir(parents=True, exist_ok=True)
    journal, completed = _prepare_journal(work)
    v3 = _v3()
    provider = CONTRACT["provider"]
    for event in schedule_events()[completed:]:
        try:
            v3._run(event, provider, work, timeout)
        except Exception as exc:
            if "402" in str(exc):
                raise RuntimeError("Nous Pro returned HTTP 402; successor stops without purchase or retry") from exc
            raise
        binding = _binding(work, event["method_id"], event["run_id"])
        _append(journal, {**event, "event": "completed", "run_binding_sha256": sha(binding)})
        print(json.dumps({"provider": provider["provider_id"], "sequence": event["sequence"], "method": event["method_id"]}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--flash-work-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    execute(args.work_dir.resolve(), args.flash_work_dir.resolve(), args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
