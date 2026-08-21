"""External-only preparation and immutable-contract checks for HANNA v3."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
V2_STUDY = HERE.parent / "hbq-human-alignment-v2" / "study.py"
V2_ANALYZER = HERE.parent / "hbq-human-alignment-v2" / "analyze_study.py"
V2_CONTRACT = HERE.parent / "hbq-human-alignment-v2" / "study-contract.json"
PROTOCOL_FIELDS = (
    "study_id", "frozen_before_execution", "dataset", "selection", "provider",
    "runner", "repeatability", "metrics", "human_ratings_policy",
    "published_human_agreement_context",
)


def _load_v2() -> Any:
    spec = importlib.util.spec_from_file_location("hbq_hanna_v2_core", V2_STUDY)
    if spec is None or spec.loader is None:
        raise RuntimeError("HANNA v2 compatibility core is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_v2 = _load_v2()
CSV_NAME = _v2.CSV_NAME
LICENSE_NAME = _v2.LICENSE_NAME
RATING_DIMENSIONS = _v2.RATING_DIMENSIONS
PARTITIONS = _v2.PARTITIONS
HannaItem = _v2.HannaItem
canonical_json = _v2.canonical_json
sha256_bytes = _v2.sha256_bytes
sha256_text = _v2.sha256_text
sha256_path = _v2.sha256_path
write_json = _v2.write_json
fetch_or_verify_dataset = _v2.fetch_or_verify_dataset
load_hanna_items = _v2.load_hanna_items
privacy_forbidden_strings = _v2.privacy_forbidden_strings
select_partitions = _v2.select_partitions
mapping_sets = _v2.mapping_sets
make_task_contract = _v2.make_task_contract
compiled_question_ids = _v2.compiled_question_ids
assert_mapping_valid = _v2.assert_mapping_valid
fingerprint = _v2.fingerprint
alpha_nominal = _v2.alpha_nominal


def load_contract() -> dict[str, Any]:
    contract = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))
    supersedes = contract.get("supersedes")
    if (
        not isinstance(supersedes, Mapping)
        or supersedes.get("study_id") != "hbq-human-alignment-v2"
        or supersedes.get("study_contract_sha256") != sha256_path(V2_CONTRACT)
    ):
        raise ValueError("v3 supersedes reference does not bind the v2 contract")
    return contract


def protocol_projection(contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = load_contract() if contract is None else contract
    return {key: source[key] for key in PROTOCOL_FIELDS}


def protocol_sha256(contract: Mapping[str, Any] | None = None) -> str:
    return sha256_bytes(canonical_json(protocol_projection(contract)))


def package_paths() -> list[Path]:
    from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir

    return [
        registry_path(), bundles_path(),
        prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md",
        prompts_dir() / "judge" / "JUDGE_PREFIX.md",
        schema_dir() / "hbq_judge_response.schema.json",
        schema_dir() / "hbq_verdict.schema.json",
        schema_dir() / "hbq_task_contract.schema.json",
        schema_dir() / "hbq_score_report.schema.json",
        ROOT / "src" / "hbqrs" / "core.py",
        ROOT / "src" / "hbqrs" / "runner.py",
        ROOT / "src" / "hbqrs" / "weights.py",
        ROOT / "src" / "hbqrs" / "paths.py",
        ROOT / "src" / "hbqrs" / "__init__.py",
        V2_STUDY, V2_ANALYZER,
        HERE / "study.py", HERE / "prepare_hanna.py", HERE / "run_study.py",
        HERE / "analyze_study.py", HERE / "confirmation_gate.py",
        HERE / "study-contract.json", HERE / "README.md",
    ]


def _runtime_files() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for path in package_paths():
        key = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        if key in entries:
            raise ValueError(f"Duplicate frozen runtime key: {key}")
        entries[key] = fingerprint(path)
    return entries


def _runtime_sha256(files: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(files))


def prompt_partitions(items: Sequence[HannaItem], contract: Mapping[str, Any]) -> dict[str, list[str]]:
    prompts = {item.prompt_sha256 for item in items}
    if len(prompts) != contract["selection"]["prompt_groups"]:
        raise ValueError("Pinned HANNA data does not contain the contract prompt-group count")
    ordered = sorted(prompts)
    random = __import__("random").Random(f"{contract['selection']['seed']}:prompt-groups")
    random.shuffle(ordered)
    count = contract["selection"]["prompt_groups_per_partition"]
    result = {"development": ordered[:count], "confirmatory": ordered[count:]}
    if any(len(values) != count for values in result.values()) or set(result["development"]) & set(result["confirmatory"]):
        raise ValueError("Prompt partition must be exactly 48/48 and disjoint")
    return result


def validate_selection(selections: Mapping[str, Sequence[Mapping[str, Any]]], prompt_groups: Mapping[str, Sequence[str]], contract: Mapping[str, Any]) -> str:
    if set(selections) != set(PARTITIONS) or set(prompt_groups) != set(PARTITIONS):
        raise ValueError("Frozen selection partitions are incomplete")
    expected_prompt_count = contract["selection"]["prompt_groups_per_partition"]
    prompt_sets = {partition: set(prompt_groups[partition]) for partition in PARTITIONS}
    if any(len(values) != expected_prompt_count for values in prompt_sets.values()) or prompt_sets["development"] & prompt_sets["confirmatory"]:
        raise ValueError("Frozen prompt partition is not exactly 48/48 and disjoint")
    all_items: set[str] = set()
    for partition in PARTITIONS:
        rows = list(selections[partition])
        if len(rows) != 88:
            raise ValueError(f"Frozen {partition} selection must contain exactly 88 items")
        models = sorted({str(row.get("model", "")) for row in rows})
        if len(models) != contract["selection"]["models"] or any(not model for model in models):
            raise ValueError(f"Frozen {partition} selection does not cover the contract model count")
        for model in models:
            model_rows = [row for row in rows if row.get("model") == model]
            if len(model_rows) != 8 or {int(row.get("quartile", 0)) for row in model_rows} != {1, 2, 3, 4} or any(sum(row.get("quartile") == quartile for row in model_rows) != 2 for quartile in range(1, 5)):
                raise ValueError(f"Frozen {partition}/{model} selection is not 8 items across four balanced quartiles")
        for row in rows:
            item_id, prompt_sha = row.get("item_id"), row.get("prompt_sha256")
            if not isinstance(item_id, str) or not item_id or item_id in all_items or not isinstance(prompt_sha, str) or prompt_sha not in prompt_sets[partition] or row.get("prompt_group_id") != f"prompt-{prompt_sha[:16]}":
                raise ValueError(f"Frozen {partition} selection row is invalid or crosses its prompt partition")
            all_items.add(item_id)
    if len(all_items) != 176:
        raise ValueError("Frozen selection must contain exactly 176 distinct items")
    return sha256_bytes(canonical_json({"partitions": selections, "prompt_partitions": prompt_groups}))


def derived_repeatability_items(selections: Mapping[str, Sequence[Mapping[str, Any]]], contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    development = list(selections.get("development", []))
    if len(development) != 88:
        raise ValueError("Frozen development selection must contain exactly 88 items")
    models = sorted({str(row.get("model", "")) for row in development})
    if len(models) != contract["selection"]["models"] or any(not model for model in models):
        raise ValueError("Frozen development selection does not cover the contract model count")
    selected: list[dict[str, Any]] = []
    for model in models:
        candidates = [row for row in development if row.get("model") == model]
        choice = min(candidates, key=lambda row: sha256_text(f"{contract['repeatability']['seed']}:{model}:{row['item_id']}"))
        selected.append({"item_id": choice["item_id"], "model": model, "partition": "development"})
    if len(selected) != 11 or len({row["item_id"] for row in selected}) != 11:
        raise ValueError("Derived repeatability selection must contain exactly 11 unique items")
    return selected


def freeze_external_work(data_dir: Path, work_dir: Path, *, fetch: bool = False) -> dict[str, Any]:
    dataset_files = fetch_or_verify_dataset(data_dir, fetch=fetch)
    contract = load_contract()
    items = load_hanna_items(data_dir)
    selections = select_partitions(items, seed=contract["selection"]["seed"])
    groups = prompt_partitions(items, contract)
    assert_mapping_valid()
    if (work_dir / "frozen-run-contract.json").exists():
        raise ValueError("Refusing to overwrite existing frozen external contract")
    by_id = {item.item_id: item for item in items}
    for partition, rows in selections.items():
        for row in rows:
            item = by_id[row["item_id"]]
            folder = work_dir / "inputs" / partition / item.item_id
            folder.mkdir(parents=True, exist_ok=False)
            (folder / "source.md").write_text(item.story, encoding="utf-8", newline="\n")
            (folder / "prompt.md").write_text(item.prompt, encoding="utf-8", newline="\n")
            write_json(folder / "task-contract.json", make_task_contract(item))
            row["external_input"] = {
                name: fingerprint(folder / name)
                for name in ("source.md", "prompt.md", "task-contract.json")
            }
    selection_sha256 = validate_selection(selections, groups, contract)
    repeatability = derived_repeatability_items(selections, contract)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        commit = "UNAVAILABLE"
    runtime_files = _runtime_files()
    frozen = {
        "format_version": 3,
        "study_id": contract["study_id"],
        "frozen_before_execution": True,
        "study_contract_sha256": sha256_path(HERE / "study-contract.json"),
        "v2_contract_sha256": sha256_path(V2_CONTRACT),
        "protocol": protocol_projection(contract),
        "protocol_sha256": protocol_sha256(contract),
        "dataset": {**contract["dataset"], "verified_files": dataset_files},
        "selection": contract["selection"],
        "partitions": selections,
        "prompt_partitions": groups,
        "selection_sha256": selection_sha256,
        "repeatability": {**contract["repeatability"], "items": repeatability},
        "provider": contract["provider"],
        "runner": contract["runner"],
        "mapping_sets": mapping_sets(),
        "mapping_sets_sha256": sha256_bytes(canonical_json(mapping_sets())),
        "package_commit": commit,
        "runtime_files": runtime_files,
        "runtime_sha256": _runtime_sha256(runtime_files),
        "question_ids": compiled_question_ids(),
    }
    write_json(work_dir / "frozen-run-contract.json", frozen)
    return frozen


def validate_external_inputs(work_dir: Path, frozen: Mapping[str, Any]) -> None:
    for partition, rows in frozen["partitions"].items():
        for row in rows:
            folder = work_dir / "inputs" / partition / row["item_id"]
            for name in ("source.md", "prompt.md", "task-contract.json"):
                if row["external_input"].get(name) != fingerprint(folder / name):
                    raise ValueError(f"External input drifted: {partition}/{row['item_id']}/{name}")


def validate_dataset_binding(data_dir: Path, frozen: Mapping[str, Any]) -> None:
    observed = fetch_or_verify_dataset(data_dir)
    if frozen.get("dataset", {}).get("verified_files") != observed:
        raise ValueError("Supplied HANNA dataset files do not match the frozen verified metadata")


def validate_frozen_contract(work_dir: Path) -> dict[str, Any]:
    frozen = json.loads((work_dir / "frozen-run-contract.json").read_text(encoding="utf-8"))
    if frozen.get("format_version") != 3 or not frozen.get("frozen_before_execution"):
        raise ValueError("Run contract is not a v3 pre-execution freeze")
    contract = load_contract()
    expected_protocol = protocol_projection(contract)
    if frozen.get("study_id") != contract["study_id"]:
        raise ValueError("Frozen study identifier drifted")
    if frozen.get("study_contract_sha256") != sha256_path(HERE / "study-contract.json"):
        raise ValueError("Frozen study contract drifted")
    if frozen.get("v2_contract_sha256") != sha256_path(V2_CONTRACT):
        raise ValueError("Frozen v2 compatibility contract drifted")
    if frozen.get("protocol") != expected_protocol or frozen.get("protocol_sha256") != protocol_sha256(contract):
        raise ValueError("Frozen protocol projection drifted")
    for key in ("selection", "provider", "runner"):
        if frozen.get(key) != expected_protocol[key]:
            raise ValueError(f"Frozen {key} does not match the canonical v3 protocol")
    canonical_repeatability = expected_protocol["repeatability"]
    frozen_repeatability = frozen.get("repeatability")
    if not isinstance(frozen_repeatability, Mapping) or set(frozen_repeatability) != {*canonical_repeatability, "items"} or {key: frozen_repeatability.get(key) for key in canonical_repeatability if key != "items"} != {key: canonical_repeatability[key] for key in canonical_repeatability if key != "items"}:
        raise ValueError("Frozen repeatability settings do not match the canonical v3 protocol")
    if frozen_repeatability.get("items") != derived_repeatability_items(frozen.get("partitions", {}), contract):
        raise ValueError("Frozen repeatability items are not the deterministic 11-item derivation")
    if frozen.get("selection_sha256") != validate_selection(frozen.get("partitions", {}), frozen.get("prompt_partitions", {}), contract):
        raise ValueError("Frozen selection structure or hash drifted")
    verified_files = frozen.get("dataset", {}).get("verified_files")
    expected_hashes = {CSV_NAME: expected_protocol["dataset"]["csv_sha256"], LICENSE_NAME: expected_protocol["dataset"]["license_sha256"]}
    if not isinstance(verified_files, Mapping) or set(verified_files) != set(expected_hashes) or any(not isinstance(verified_files.get(name), Mapping) or verified_files[name].get("sha256") != expected_hashes[name] or not isinstance(verified_files[name].get("bytes"), int) or isinstance(verified_files[name].get("bytes"), bool) or verified_files[name]["bytes"] < 1 for name in expected_hashes) or {
        key: value for key, value in frozen.get("dataset", {}).items() if key != "verified_files"
    } != expected_protocol["dataset"]:
        raise ValueError("Frozen dataset provenance does not match the canonical v3 protocol")
    runtime_files = _runtime_files()
    if frozen.get("runtime_files") != runtime_files or frozen.get("runtime_sha256") != _runtime_sha256(runtime_files):
        raise ValueError("Frozen runtime files drifted")
    try:
        current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Cannot verify frozen package commit") from exc
    if frozen.get("package_commit") != current:
        raise ValueError("Frozen package commit drifted")
    if frozen.get("question_ids") != compiled_question_ids():
        raise ValueError("Compiled question sequence drifted")
    if frozen.get("mapping_sets") != mapping_sets() or frozen.get("mapping_sets_sha256") != sha256_bytes(canonical_json(mapping_sets())):
        raise ValueError("Frozen mapping set drifted")
    validate_external_inputs(work_dir, frozen)
    assert_mapping_valid(frozen["question_ids"])
    return frozen
