"""Freeze and validate the provider-side projection of an existing HANNA v3 run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PHASES = ("development", "repeatability", "confirmatory")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if value.get("format_version") != 1 or value.get("frozen_before_execution") is not True:
        raise ValueError("Supplemental HANNA contract is not a pre-execution v1 freeze")
    providers = value.get("providers")
    if not isinstance(providers, list) or [item.get("provider_id") for item in providers] != ["grok_4_6_high", "nous_flash_max", "nous_pro_max"]:
        raise ValueError("Supplemental provider roster drifted")
    if value.get("phase_order") != ["development", "immutable_analysis_and_promotion", "repeatability", "confirmatory"]:
        raise ValueError("Supplemental phase order drifted")
    return value


CONTRACT = load_contract()


def primary_root() -> Path:
    return (HERE / CONTRACT["gpt_primary"]["study_path"]).resolve()


def provider(provider_id: str) -> dict[str, Any]:
    found = [item for item in CONTRACT["providers"] if item["provider_id"] == provider_id]
    if len(found) != 1:
        raise ValueError(f"Unknown frozen provider: {provider_id}")
    return found[0]


def _fingerprint(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _load_primary_study() -> Any:
    path = primary_root() / "study.py"
    spec = importlib.util.spec_from_file_location("supplemental_hanna_v3_study", path)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen GPT HANNA study helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_hashes(frozen: Mapping[str, Any]) -> dict[str, str]:
    files = frozen.get("runtime_files")
    if not isinstance(files, Mapping):
        raise ValueError("Primary frozen runtime file inventory is missing")
    result: dict[str, str] = {}
    for name in CONTRACT["gpt_primary"]["runtime_files_required"]:
        record = files.get(name)
        if not isinstance(record, Mapping) or not isinstance(record.get("sha256"), str):
            raise ValueError(f"Primary frozen runtime does not bind {name}")
        result[name] = str(record["sha256"])
    if result != CONTRACT["gpt_primary"]["required_runtime_hashes"]:
        raise ValueError("Primary frozen runtime hashes do not match the exact GPT v3 binding")
    return result


def _validate_primary_frozen(gpt_work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    primary = CONTRACT["gpt_primary"]
    if sha(primary_root() / "study-contract.json") != primary["study_contract_sha256"]:
        raise ValueError("Committed GPT study contract does not match supplemental binding")
    for filename, key in (("study.py", "study_sha256"), ("analyze_study.py", "analyzer_sha256"), ("run_study.py", "runner_sha256")):
        if sha(primary_root() / filename) != primary[key]:
            raise ValueError(f"Committed GPT {filename} does not match supplemental binding")
    frozen_path = gpt_work / "frozen-run-contract.json"
    frozen = read_json(frozen_path)
    if frozen.get("study_id") != primary["study_id"] or frozen.get("study_contract_sha256") != primary["study_contract_sha256"]:
        raise ValueError("External GPT frozen contract does not bind the exact primary study")
    if len(frozen.get("partitions", {}).get("development", [])) != primary["development_items"] or len(frozen.get("partitions", {}).get("confirmatory", [])) != primary["confirmatory_items"]:
        raise ValueError("External GPT selection count differs from the primary protocol")
    repeatability = frozen.get("repeatability", {})
    if len(repeatability.get("items", [])) != primary["repeatability_items"] or repeatability.get("repetitions") != primary["repeatability_repetitions"]:
        raise ValueError("External GPT repeatability schedule differs from the primary protocol")
    runner = frozen.get("runner", {})
    if runner.get("batch_size") != primary["batch_size"] or runner.get("batch_attempts") != primary["batch_attempts"] or runner.get("maximum_workers") != 4:
        raise ValueError("External GPT runner schedule differs from the primary protocol")
    study = _load_primary_study()
    if frozen.get("question_ids") != study.compiled_question_ids():
        raise ValueError("Frozen GPT question sequence no longer compiles exactly")
    if frozen.get("runtime_sha256") != study._runtime_sha256(frozen.get("runtime_files", {})):
        raise ValueError("External GPT frozen runtime inventory is not self-consistent")
    return frozen, {"frozen_contract": _fingerprint(frozen_path), "runtime_hashes": _runtime_hashes(frozen)}


def _input_commitments(gpt_work: Path, frozen: Mapping[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for partition in ("development", "confirmatory"):
        part: dict[str, dict[str, Any]] = {}
        for row in frozen["partitions"][partition]:
            item = str(row["item_id"])
            expected = row.get("external_input")
            if not isinstance(expected, Mapping) or set(expected) != {"source.md", "prompt.md", "task-contract.json"}:
                raise ValueError(f"Primary input commitment malformed: {partition}/{item}")
            folder = gpt_work / "inputs" / partition / item
            observed = {name: _fingerprint(folder / name) for name in expected}
            if observed != expected:
                raise ValueError(f"Primary input bytes drifted: {partition}/{item}")
            part[item] = observed
        result[partition] = part
    return result


def _rating_metadata(data: Path, primary_frozen: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Commit public HANNA labels without carrying any source prose into this study."""
    PRIMARY = _load_primary_study()
    PRIMARY.validate_dataset_binding(data, primary_frozen)
    by_id = {item.item_id: item for item in PRIMARY.load_hanna_items(data)}
    output: dict[str, dict[str, Any]] = {}
    for partition in ("development", "confirmatory"):
        for row in primary_frozen["partitions"][partition]:
            item = by_id.get(row["item_id"])
            if item is None or item.model != row["model"] or item.story_sha256 != row["story_sha256"] or item.prompt_sha256 != row["prompt_sha256"]:
                raise ValueError("Pinned HANNA metadata does not match the primary frozen selection")
            output[str(item.item_id)] = {
                "story_id": item.story_id,
                "model": item.model,
                "story_sha256": item.story_sha256,
                "prompt_sha256": item.prompt_sha256,
                "ratings_sha256": hashlib.sha256(canonical(item.ratings)).hexdigest(),
            }
    if len(output) != 176:
        raise ValueError("Pinned HANNA metadata does not cover the full primary selection")
    return output


def freeze_provider_work(gpt_work: Path, data: Path, work: Path) -> dict[str, Any]:
    if (work / "frozen-provider-contract.json").exists():
        raise ValueError("Refusing to overwrite a frozen supplemental work contract")
    frozen, bindings = _validate_primary_frozen(gpt_work)
    inputs = _input_commitments(gpt_work, frozen)
    metadata = _rating_metadata(data, frozen)
    selection = {key: frozen[key] for key in ("selection", "partitions", "prompt_partitions", "selection_sha256", "repeatability", "question_ids", "mapping_sets", "mapping_sets_sha256")}
    value = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "frozen_before_execution": True,
        "supplemental_contract_sha256": sha(CONTRACT_PATH),
        "primary_work_dir": str(gpt_work.resolve()),
        "primary_frozen": bindings["frozen_contract"],
        "primary_runtime_hashes": bindings["runtime_hashes"],
        "primary_runtime_files": frozen["runtime_files"],
        "primary_protocol": {key: frozen[key] for key in ("study_id", "study_contract_sha256", "runtime_sha256", "package_commit", "dataset", "protocol", "provider", "runner")},
        "selection": selection,
        "input_commitments": inputs,
        "rating_metadata": metadata,
        "providers": CONTRACT["providers"],
        "phase_order": CONTRACT["phase_order"],
        "nous_promotion": CONTRACT["nous_promotion"],
    }
    write_json(work / "frozen-provider-contract.json", value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    frozen = read_json(work / "frozen-provider-contract.json")
    if frozen.get("format_version") != 1 or frozen.get("study_id") != CONTRACT["study_id"] or frozen.get("supplemental_contract_sha256") != sha(CONTRACT_PATH):
        raise ValueError("Supplemental frozen contract does not bind this protocol")
    if frozen.get("providers") != CONTRACT["providers"] or frozen.get("phase_order") != CONTRACT["phase_order"] or frozen.get("nous_promotion") != CONTRACT["nous_promotion"]:
        raise ValueError("Supplemental frozen provider policy drifted")
    primary = frozen.get("primary_work_dir")
    if not isinstance(primary, str) or not primary:
        raise ValueError("Supplemental work contract lacks its primary source")
    primary_work = Path(primary)
    primary_frozen, bindings = _validate_primary_frozen(primary_work)
    if frozen.get("primary_frozen") != bindings["frozen_contract"] or frozen.get("primary_runtime_hashes") != bindings["runtime_hashes"] or frozen.get("primary_runtime_files") != primary_frozen.get("runtime_files"):
        raise ValueError("Supplemental work contract no longer binds the exact primary freeze/runtime")
    expected_selection = {key: primary_frozen[key] for key in ("selection", "partitions", "prompt_partitions", "selection_sha256", "repeatability", "question_ids", "mapping_sets", "mapping_sets_sha256")}
    if frozen.get("selection") != expected_selection or frozen.get("primary_protocol", {}).get("runtime_sha256") != primary_frozen.get("runtime_sha256"):
        raise ValueError("Supplemental selection does not exactly reuse the primary protocol")
    if frozen.get("input_commitments") != _input_commitments(primary_work, primary_frozen):
        raise ValueError("Supplemental input bytes no longer exactly match the primary work")
    if not isinstance(frozen.get("rating_metadata"), Mapping) or len(frozen["rating_metadata"]) != 176:
        raise ValueError("Supplemental work contract lacks the complete frozen HANNA rating metadata")
    return frozen


def validate_dataset_and_metadata(data: Path, frozen: Mapping[str, Any]) -> None:
    """Reopen the pinned dataset and reject any label/model/source metadata drift."""
    primary_frozen = read_json(Path(frozen["primary_work_dir"]) / "frozen-run-contract.json")
    PRIMARY = _load_primary_study()
    PRIMARY.validate_dataset_binding(data, primary_frozen)
    observed = _rating_metadata(data, primary_frozen)
    if observed != frozen["rating_metadata"]:
        raise ValueError("HANNA rating/model metadata does not match the frozen supplemental projection")


def phase_rows(frozen: Mapping[str, Any], phase: str) -> list[dict[str, Any]]:
    if phase not in PHASES:
        raise ValueError("Unknown supplemental phase")
    selection = frozen["selection"]
    if phase == "repeatability":
        rows = [{"kind": phase, "repetition": number, **row} for row in selection["repeatability"]["items"] for number in range(1, selection["repeatability"]["repetitions"] + 1)]
    else:
        rows = [{"kind": phase, "repetition": 1, **row} for row in selection["partitions"][phase]]
    random.Random(selection["selection"]["seed"]).shuffle(rows)
    return rows


def primary_input(frozen: Mapping[str, Any], phase: str, item_id: str) -> tuple[Path, dict[str, Any]]:
    partition = "development" if phase in {"development", "repeatability"} else "confirmatory"
    row = next((row for row in frozen["selection"]["partitions"][partition] if row["item_id"] == item_id), None)
    if row is None:
        raise ValueError("Supplemental job has no primary selection row")
    folder = Path(frozen["primary_work_dir"]) / "inputs" / partition / item_id
    expected = frozen["input_commitments"][partition][item_id]
    observed = {name: _fingerprint(folder / name) for name in expected}
    if observed != expected:
        raise ValueError("Supplemental job input bytes differ from its primary source")
    return folder, row
