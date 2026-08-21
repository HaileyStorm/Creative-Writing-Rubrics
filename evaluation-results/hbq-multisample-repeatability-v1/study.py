"""Freeze and validate the external-only HANNA multi-sample study inputs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hbqrs.core import (
    compile_bundle,
    compiled_questions,
    load_bundles,
    load_modules,
    resolve_bundle,
)
from hbqrs.paths import bundles_path, registry_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
HANNA = HERE.parent / "hbq-human-alignment-v3"
ESTABLISHED = HERE.parent / "the-part-that-arrives-first-repeatability" / "established-v4"
CONTRACT = HERE / "study-contract.json"
STUDY_IMPORT_RUNTIME_SHA256 = {
    "src/hbqrs/__init__.py": "f1e320efdb4c0deecf65101e91ed0a9afff3e37eb516ad70b41abbf8fe8fb4f8",
    "src/hbqrs/core.py": "70b4cd16bd536f2f6ddb8e066f801090a037a39605652b14d6c7f6ff312446cb",
    "src/hbqrs/paths.py": "dedadb6d9f8e3cf700c16012b29e1a590a2b1175c8ead0cf17c44aa6417b8266",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    try:
        label = path.relative_to(ROOT).as_posix()
    except ValueError:
        label = path.name
    return {"path": label, "bytes": path.stat().st_size, "sha256": sha(path)}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def _quality_band(value: float, cutpoints: Mapping[str, Any]) -> int:
    boundaries = [cutpoints.get(key) for key in ("q1_upper", "q2_upper", "q3_upper")]
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or any(not isinstance(boundary, (int, float)) or isinstance(boundary, bool) for boundary in boundaries)
        or boundaries != sorted(boundaries)
    ):
        raise ValueError("Frozen full-development quality cutpoints must be numeric and monotonic")
    return 1 + sum(value > boundary for boundary in boundaries)


def _quality_cutpoints(values: list[float]) -> dict[str, Any]:
    if len(values) != 88 or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values) or values != sorted(values):
        raise ValueError("Frozen full-development quality values must be 88 sorted numeric human-overall values")
    return {"method": "frozen full-development empirical quartiles", "item_count": len(values), "human_overall_values_sha256": hashlib.sha256(canonical(values)).hexdigest(), "q1_upper": values[21], "q2_upper": values[43], "q3_upper": values[65]}


def _parent_row(sample: Mapping[str, Any], parent: Mapping[str, Any]) -> Mapping[str, Any]:
    development = parent.get("partitions", {}).get("development") if isinstance(parent.get("partitions"), Mapping) else None
    if not isinstance(development, list):
        raise ValueError("Frozen HANNA parent development rows are unavailable")
    matched = [row for row in development if isinstance(row, Mapping) and row.get("item_id") == sample.get("item_id")]
    if len(matched) != 1:
        raise ValueError(f"Frozen sample does not bind exactly one HANNA parent development row: {sample.get('item_id')}")
    return matched[0]


def _authoritative_rating(item: Any) -> dict[str, Any]:
    return {"human_overall": item.human_overall, "human_means": item.human_means, "ratings": {key: list(values) for key, values in item.ratings.items()}}


def _validate_sample_binding(work_dir: Path, sample: Mapping[str, Any], parent: Mapping[str, Any], cutpoints: Mapping[str, Any], item: Any) -> None:
    parent_row = _parent_row(sample, parent)
    if sample.get("parent_development_row") != parent_row or sample.get("parent_development_row_sha256") != hashlib.sha256(canonical(parent_row)).hexdigest():
        raise ValueError(f"Frozen sample parent-row binding drifted: {sample.get('item_id')}")
    parent_fields = ("item_id", "model", "story_id", "prompt_sha256", "story_sha256")
    if any(sample.get(field) != parent_row.get(field) for field in parent_fields) or sample.get("development_quartile") != parent_row.get("quartile"):
        raise ValueError(f"Frozen sample does not reproduce its exact HANNA parent row: {sample.get('item_id')}")
    inputs = sample.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError(f"Frozen sample input fingerprints are missing: {sample.get('item_id')}")
    folder = work_dir / "inputs" / str(sample["item_id"])
    expected_inputs = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json", "human-ratings.json")}
    if inputs != expected_inputs:
        raise ValueError(f"Frozen external input drifted: {sample.get('item_id')}")
    if inputs["source.md"].get("sha256") != sample.get("story_sha256") or inputs["prompt.md"].get("sha256") != sample.get("prompt_sha256"):
        raise ValueError(f"Frozen source or originating-prompt fingerprint does not bind its HANNA parent row: {sample.get('item_id')}")
    rating = json.loads((folder / "human-ratings.json").read_text(encoding="utf-8"))
    authoritative = _authoritative_rating(item)
    if rating != authoritative or sample.get("human_overall") != authoritative["human_overall"]:
        raise ValueError(f"Frozen sample human ratings do not match the authoritative HANNA raw data: {sample.get('item_id')}")
    if sample.get("frozen_quality_band") != _quality_band(authoritative["human_overall"], cutpoints):
        raise ValueError(f"Frozen sample quality band is not deterministically re-derived: {sample.get('item_id')}")


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load frozen helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def hanna() -> Any:
    return _module("hbq_multisample_hanna_v3", HANNA / "study.py")


def contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("study_id") != "hbq-multisample-repeatability-v1" or value.get("repetitions") != 5:
        raise ValueError("Study contract identity or repetition count drifted")
    if [item["arm_id"] for item in value.get("arms", [])] != ["hbq_short_story_batch32", "naplan_narrative_2022", "cambridge_igcse_0500_p2_mj_2024", "oregon_narrative_2017", "compact_analytic", "holistic_anchored"]:
        raise ValueError("The frozen six-arm protocol drifted")
    return value


def _pinned_study_import_runtime_paths() -> list[Path]:
    paths = [ROOT / relative for relative in STUDY_IMPORT_RUNTIME_SHA256]
    if any(not path.is_file() or sha(path) != expected for path, expected in zip(paths, STUDY_IMPORT_RUNTIME_SHA256.values())):
        raise ValueError("Pinned study-import runtime closure drifted")
    return paths


def pinned_paths() -> list[Path]:
    c = contract()
    paths = [CONTRACT, HERE / "study.py", HERE / "prepare_study.py", HERE / "run_study.py", HERE / "analyze_study.py", HANNA / "study.py", HANNA / "study-contract.json", HANNA / "run_study.py", HANNA / "analyze_study.py", ESTABLISHED / "run_study.py", ESTABLISHED / "analyze_study.py", ESTABLISHED / "study-contract.json"]
    for arm in c["arms"]:
        if arm["kind"] == "native":
            paths.extend([HERE / arm["prompt"], HERE / arm["schema"]])
    from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir
    paths.extend([registry_path(), bundles_path(), prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md", prompts_dir() / "judge" / "JUDGE_PREFIX.md", schema_dir() / "hbq_judge_response.schema.json", schema_dir() / "hbq_score_report.schema.json", ROOT / "src" / "hbqrs" / "runner.py", ROOT / "src" / "hbqrs" / "longform_runner.py", ROOT / "src" / "hbqrs" / "weights.py", *_pinned_study_import_runtime_paths()])
    return paths


def frozen_schedule(sample_ids: list[str], arms: list[str], repetitions: int) -> list[dict[str, Any]]:
    if len(arms) != 6 or repetitions != 5:
        raise ValueError("Balanced schedule requires six arms and five repetitions")
    events: list[dict[str, Any]] = []
    for sample_index, item_id in enumerate(sorted(sample_ids)):
        for repetition in range(1, repetitions + 1):
            offset = (sample_index + repetition - 1) % len(arms)
            order = arms[offset:] + arms[:offset]
            for position, arm_id in enumerate(order, 1):
                events.append({"item_id": item_id, "repetition": repetition, "arm_id": arm_id, "position": position})
    positions = {arm: [event["position"] for event in events if event["arm_id"] == arm] for arm in arms}
    if max(max(values.count(position) for position in range(1, 7)) - min(values.count(position) for position in range(1, 7)) for values in positions.values()) > 1:
        raise ValueError("Near-Latin schedule position imbalance exceeds one")
    return events


def question_sequence(task: Mapping[str, Any], bundle_id: str = "prose.short_story") -> list[str]:
    bundle = resolve_bundle(load_bundles(bundles_path()), bundle_id)
    compiled = compile_bundle(load_modules(registry_path()), bundle, task_contract=task)
    records = sorted(compiled_questions(compiled), key=lambda item: {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}.get(str(item.get("role")), 99))
    return [str(item["question"]["id"]) for item in records]


def freeze(data_dir: Path, work_dir: Path, *, fetch: bool = False) -> dict[str, Any]:
    if (work_dir / "frozen-run-contract.json").exists():
        raise ValueError("Refusing to overwrite an existing frozen external contract")
    c, h = contract(), hanna()
    dataset = h.fetch_or_verify_dataset(data_dir, fetch=fetch)
    items = {item.item_id: item for item in h.load_hanna_items(data_dir)}
    parent_contract = h.load_contract()
    selected = h.select_partitions(list(items.values()), seed=parent_contract["selection"]["seed"])
    prompt_groups = h.prompt_partitions(list(items.values()), parent_contract)
    selection_sha256 = h.validate_selection(selected, prompt_groups, parent_contract)
    repeat = h.derived_repeatability_items(selected, parent_contract)
    if len(repeat) != 11 or len({row["model"] for row in repeat}) != 11:
        raise ValueError("HANNA v3 selection is not the exact 11-model repeatability slice")
    sample_rows: list[dict[str, Any]] = []
    for selected_row in repeat:
        item = items[selected_row["item_id"]]
        parent = next(row for row in selected["development"] if row["item_id"] == item.item_id)
        folder = work_dir / "inputs" / item.item_id
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "source.md").write_text(item.story, encoding="utf-8", newline="\n")
        (folder / "prompt.md").write_text(item.prompt, encoding="utf-8", newline="\n")
        task = h.make_task_contract(item)
        write_json(folder / "task-contract.json", task)
        question_ids = question_sequence(task)
        if len(question_ids) != 179:
            raise ValueError("HANNA task contract must compile to the frozen 179-question sequence")
        write_json(folder / "human-ratings.json", _authoritative_rating(item))
        inputs = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json", "human-ratings.json")}
        if inputs["source.md"]["sha256"] != parent["story_sha256"] or inputs["prompt.md"]["sha256"] != parent["prompt_sha256"]:
            raise ValueError(f"Prepared source or originating prompt does not match HANNA parent fingerprints: {item.item_id}")
        sample_rows.append({"item_id": item.item_id, "model": item.model, "story_id": item.story_id, "development_quartile": parent["quartile"], "prompt_sha256": item.prompt_sha256, "story_sha256": item.story_sha256, "human_overall": item.human_overall, "parent_development_row": parent, "parent_development_row_sha256": hashlib.sha256(canonical(parent)).hexdigest(), "question_count": len(question_ids), "question_id_sequence_sha256": hashlib.sha256(canonical(question_ids)).hexdigest(), "inputs": inputs})
    sample_rows.sort(key=lambda row: row["model"])
    if len({row["prompt_sha256"] for row in sample_rows}) != 10:
        raise ValueError("HANNA repeatability slice must retain its exact 10 prompt clusters")
    development_quality = sorted(items[row["item_id"]].human_overall for row in selected["development"])
    cutpoints = _quality_cutpoints(development_quality)
    for row in sample_rows:
        row["frozen_quality_band"] = _quality_band(row["human_overall"], cutpoints)
    arms = [arm["arm_id"] for arm in c["arms"]]
    schedule = frozen_schedule([row["item_id"] for row in sample_rows], arms, c["repetitions"])
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        commit = "UNAVAILABLE"
    runtime = [fingerprint(path) for path in pinned_paths()]
    question_lineage = [{"item_id": row["item_id"], "question_count": row["question_count"], "question_id_sequence_sha256": row["question_id_sequence_sha256"]} for row in sample_rows]
    parent = {
        "contract": parent_contract,
        "partitions": selected,
        "prompt_partitions": prompt_groups,
        "selection_sha256": selection_sha256,
        "repeatability_items": repeat,
    }
    frozen = {"format_version": 1, "study_id": c["study_id"], "frozen_before_execution": True, "study_contract_sha256": sha(CONTRACT), "contract": c, "hanna_v3_contract_sha256": sha(HANNA / "study-contract.json"), "hanna_v3_parent": parent, "hanna_v3_parent_selection_sha256": selection_sha256, "hanna_v3_repeatability_selection_sha256": hashlib.sha256(canonical(repeat)).hexdigest(), "dataset": {**c["dataset"], "verified_files": dataset}, "samples": sample_rows, "question_sequence_lineage": question_lineage, "question_sequence_lineage_sha256": hashlib.sha256(canonical(question_lineage)).hexdigest(), "full_development_human_overall": development_quality, "full_development_quality_cutpoints": cutpoints, "schedule": schedule, "schedule_sha256": hashlib.sha256(canonical(schedule)).hexdigest(), "package_commit": commit, "runtime_files": runtime, "runtime_sha256": hashlib.sha256(canonical(runtime)).hexdigest()}
    write_json(work_dir / "frozen-run-contract.json", frozen)
    return frozen


def validate(work_dir: Path, data_dir: Path) -> dict[str, Any]:
    path = work_dir / "frozen-run-contract.json"
    frozen = json.loads(path.read_text(encoding="utf-8"))
    c = contract()
    if frozen.get("format_version") != 1 or frozen.get("study_id") != c["study_id"] or not frozen.get("frozen_before_execution") or frozen.get("study_contract_sha256") != sha(CONTRACT):
        raise ValueError("Frozen study contract is absent, malformed, or drifted")
    if frozen.get("contract") != c or frozen.get("hanna_v3_contract_sha256") != sha(HANNA / "study-contract.json"):
        raise ValueError("Frozen protocol or HANNA v3 selection provenance drifted")
    h = hanna()
    observed_dataset = h.fetch_or_verify_dataset(data_dir)
    if frozen.get("dataset", {}).get("verified_files") != observed_dataset:
        raise ValueError("Authoritative HANNA dataset files do not match the frozen dataset commitment")
    raw_items = {item.item_id: item for item in h.load_hanna_items(data_dir)}
    raw_selected = h.select_partitions(list(raw_items.values()), seed=h.load_contract()["selection"]["seed"])
    raw_prompt_partitions = h.prompt_partitions(list(raw_items.values()), h.load_contract())
    parent = frozen.get("hanna_v3_parent")
    if not isinstance(parent, Mapping) or parent.get("contract") != h.load_contract():
        raise ValueError("Frozen HANNA parent contract provenance drifted")
    try:
        parent_selection_sha256 = h.validate_selection(parent["partitions"], parent["prompt_partitions"], parent["contract"])
        parent_repeatability = h.derived_repeatability_items(parent["partitions"], parent["contract"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Frozen HANNA parent partitions or prompt partitions are invalid") from exc
    if parent["partitions"] != raw_selected or parent["prompt_partitions"] != raw_prompt_partitions:
        raise ValueError("Frozen HANNA parent selection does not re-derive from the authoritative raw dataset")
    if (
        parent.get("selection_sha256") != parent_selection_sha256
        or frozen.get("hanna_v3_parent_selection_sha256") != parent_selection_sha256
        or parent.get("repeatability_items") != parent_repeatability
        or frozen.get("hanna_v3_repeatability_selection_sha256") != hashlib.sha256(canonical(parent_repeatability)).hexdigest()
    ):
        raise ValueError("Frozen HANNA parent selection or repeatability derivation drifted")
    samples = frozen.get("samples")
    if not isinstance(samples, list) or len(samples) != 11 or len({row.get("model") for row in samples}) != 11:
        raise ValueError("Frozen sample selection is not the required 11-model slice")
    if len({row.get("prompt_sha256") for row in samples}) != 10:
        raise ValueError("Frozen sample selection does not preserve the exact 10 prompt clusters")
    repeat = [{"item_id": row["item_id"], "model": row["model"], "partition": "development"} for row in samples]
    if repeat != parent_repeatability:
        raise ValueError("Frozen multi-sample rows are not the exact HANNA repeatability derivation")
    question_lineage = []
    for row in samples:
        task = json.loads((work_dir / "inputs" / row["item_id"] / "task-contract.json").read_text(encoding="utf-8"))
        ids = question_sequence(task)
        expected = {"item_id": row["item_id"], "question_count": len(ids), "question_id_sequence_sha256": hashlib.sha256(canonical(ids)).hexdigest()}
        if len(ids) != 179 or any(row.get(key) != value for key, value in expected.items() if key != "item_id"):
            raise ValueError(f"Frozen 179-question sequence drifted: {row['item_id']}")
        question_lineage.append(expected)
    if frozen.get("question_sequence_lineage") != question_lineage or frozen.get("question_sequence_lineage_sha256") != hashlib.sha256(canonical(question_lineage)).hexdigest():
        raise ValueError("Frozen question-sequence lineage drifted")
    quality_values = sorted(raw_items[row["item_id"]].human_overall for row in raw_selected["development"])
    if frozen.get("full_development_human_overall") != quality_values:
        raise ValueError("Frozen full-development human-overall values do not re-derive from the authoritative raw dataset")
    cutpoints = frozen.get("full_development_quality_cutpoints")
    if not isinstance(quality_values, list) or not isinstance(cutpoints, Mapping) or cutpoints != _quality_cutpoints(quality_values):
        raise ValueError("Frozen full-development quality cutpoints are missing, malformed, or not deterministically re-derived")
    _quality_band(0.0, cutpoints)
    expected_schedule = frozen_schedule([row["item_id"] for row in samples], [arm["arm_id"] for arm in c["arms"]], c["repetitions"])
    if frozen.get("schedule") != expected_schedule or frozen.get("schedule_sha256") != hashlib.sha256(canonical(expected_schedule)).hexdigest():
        raise ValueError("Frozen balanced schedule drifted")
    runtime = [fingerprint(path) for path in pinned_paths()]
    if frozen.get("runtime_files") != runtime or frozen.get("runtime_sha256") != hashlib.sha256(canonical(runtime)).hexdigest():
        raise ValueError("Pinned helper, prompt, schema, or runtime bytes drifted")
    for row in samples:
        item = raw_items.get(str(row.get("item_id")))
        if item is None:
            raise ValueError(f"Frozen sample is absent from the authoritative HANNA raw dataset: {row.get('item_id')}")
        _validate_sample_binding(work_dir, row, parent, cutpoints, item)
    return frozen
