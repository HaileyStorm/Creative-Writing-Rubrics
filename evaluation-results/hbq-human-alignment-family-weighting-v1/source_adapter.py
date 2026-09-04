"""Provider-free reconstruction boundary for the frozen TRAIN48 HBQ inputs."""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

FAMILIES = ("core", "craft", "form")
SPLIT_SHA256 = "6ffa942b595449f4118c2cd51f3a36716126612a7c10f4765953c17eb1efdbc2"
EXECUTION_FREEZE_SHA256 = "4005c941d202d1aebcc31df658093421d3677bf3033939ea5ef42e34248e9a69"
FRESH88_CONTRACT_SHA256 = "6b3bfcd2407442c9997631cd38d7df7e01bd5017782feb62ad360840399b1726"
HANNA_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
RATING_DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")

# The Fresh88 execution contract names paths that have since moved.  These are
# the immutable source copies whose fingerprints satisfy that contract.
HISTORICAL_RUNTIME = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-fresh88-parent-runtime-f3aed43")
HISTORICAL_INPUT_RUNTIME = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-multisample-runtime-9422eff")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"invalid {label}")
    return value


def _pinned_json(path: Path, expected: str, *, label: str) -> dict[str, Any]:
    if not path.is_file() or _sha256(path) != expected:
        raise ValueError(f"{label} SHA-256 pin drifted")
    return _json(path, label=label)


def _runtime_api(fresh: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    manifest = fresh.get("base_frozen", {}).get("runtime_manifest")
    files = manifest.get("files") if isinstance(manifest, Mapping) else None
    source_root = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-fresh-verify")
    if not isinstance(files, Mapping) or not files:
        raise ValueError("Fresh88 runtime manifest is absent")
    for original, binding in files.items():
        if not isinstance(original, str) or not isinstance(binding, Mapping):
            raise ValueError("Fresh88 runtime manifest is malformed")
        try:
            relative = Path(original).resolve().relative_to(source_root)
        except ValueError as exc:
            raise ValueError("Fresh88 runtime source escapes its canonical root") from exc
        candidate = HISTORICAL_RUNTIME / relative
        if set(binding) != {"bytes", "path", "sha256"} or not candidate.is_file() or candidate.stat().st_size != binding["bytes"] or _sha256(candidate) != binding["sha256"]:
            raise ValueError("Fresh88 historical runtime source binding drifted")
    runtime_src = (HISTORICAL_RUNTIME / "src").resolve()
    existing = sys.modules.get("hbqrs")
    if existing is not None:
        location = Path(str(getattr(existing, "__file__", ""))).resolve()
        if not location.is_relative_to(runtime_src):
            raise ValueError("non-historical HBQ runtime is already imported")
    if str(runtime_src) not in sys.path:
        sys.path.insert(0, str(runtime_src))
    core = importlib.import_module("hbqrs.core")
    weights = importlib.import_module("hbqrs.weights")
    verifier = importlib.import_module("hbqrs.run_verify")
    for module in (core, weights, verifier):
        if not Path(str(module.__file__)).resolve().is_relative_to(runtime_src):
            raise ValueError("historical HBQ runtime import drifted")
    return core, weights, verifier.verify_binary_run


def _historical_base(base: Mapping[str, Any]) -> dict[str, Any]:
    frozen = dict(base)
    for key, relative in (("registry", Path("registry") / "all_modules.json"), ("bundles", Path("bundles") / "all_bundles.json")):
        binding = frozen.get(key)
        candidate = HISTORICAL_INPUT_RUNTIME / relative
        if not isinstance(binding, Mapping) or not candidate.is_file() or candidate.stat().st_size != binding.get("bytes") or _sha256(candidate) != binding.get("sha256"):
            raise ValueError(f"Fresh88 historical {key} binding is unavailable")
        frozen[key] = {**binding, "path": str(candidate)}
    return frozen


def _train_rows(split: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = split.get("items")
    if not isinstance(rows, list):
        raise ValueError("split manifest lacks item rows")
    train = [row for row in rows if isinstance(row, Mapping) and row.get("partition") == "train"]
    result = [{"item_id": str(row.get("item_id", "")), "prompt_group_id": str(row.get("prompt_group_id", ""))} for row in train]
    if len(result) != 48 or len({(row["item_id"], row["prompt_group_id"]) for row in result}) != 48 or len({row["prompt_group_id"] for row in result}) != 24 or any(not row["item_id"].startswith("item-") or not row["prompt_group_id"].startswith("prompt-") for row in result):
        raise ValueError("frozen TRAIN split is not exactly 48 items / 24 prompt groups")
    return sorted(result, key=lambda row: (row["prompt_group_id"], row["item_id"]))


def _schedule_bindings(freeze: Mapping[str, Any], train: Sequence[Mapping[str, str]]) -> dict[str, list[dict[str, str]]]:
    scheduled = freeze.get("schedule")
    if not isinstance(scheduled, list):
        raise ValueError("execution freeze lacks schedule")
    train_by_id = {row["item_id"]: row for row in train}
    found: dict[str, list[dict[str, str]]] = {item_id: [] for item_id in train_by_id}
    for row in scheduled:
        if not isinstance(row, Mapping) or row.get("partition") != "train":
            continue
        item_id = row.get("item_id")
        if item_id not in found:
            continue
        expected = train_by_id[str(item_id)]
        required = ("cell_id", "candidate_id", "story_sha256", "prompt_sha256", "task_payload_sha256")
        if row.get("prompt_group_id") != expected["prompt_group_id"] or any(not isinstance(row.get(key), str) or not row[key] for key in required):
            raise ValueError("execution freeze TRAIN schedule binding is malformed")
        if expected["prompt_group_id"] != "prompt-" + str(row["prompt_sha256"])[:16]:
            raise ValueError("execution freeze prompt-group binding drifted")
        found[str(item_id)].append({key: str(row[key]) for key in (*required, "candidate_instruction_sha256", "candidate_profile_sha256")})
    if any(not rows for rows in found.values()):
        raise ValueError("execution freeze lacks a selected TRAIN item")
    for item_id, rows in found.items():
        if len({row["story_sha256"] for row in rows}) != 1 or len({row["prompt_sha256"] for row in rows}) != 1:
            raise ValueError(f"execution freeze has ambiguous source bindings for {item_id}")
        found[item_id] = sorted(rows, key=lambda row: (row["candidate_id"], row["cell_id"]))
    return found


def _human_items(hanna_csv: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if hanna_csv.name != "hanna_stories_annotations.csv" or not hanna_csv.is_file() or _sha256(hanna_csv) != HANNA_CSV_SHA256:
        raise ValueError("pinned HANNA CSV SHA-256 drifted")
    try:
        with hanna_csv.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("pinned HANNA CSV is unreadable") from exc
    required = {"Story ID", "Prompt", "Story", "Model", "Worker ID", "Assignment ID", *RATING_DIMENSIONS}
    if not rows or not required <= set(rows[0]):
        raise ValueError("pinned HANNA CSV headers drifted")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        story_id = str(row.get("Story ID", "")).strip()
        if not story_id:
            raise ValueError("HANNA CSV lacks a Story ID")
        grouped.setdefault(story_id, []).append(row)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for story_id, group in grouped.items():
        if len(group) != 3 or any(len({str(row.get(field, "")) for row in group}) != 1 or not str(group[0].get(field, "")).strip() for field in ("Prompt", "Story", "Model")):
            raise ValueError("HANNA CSV does not have three consistent ratings per story")
        means: dict[str, float] = {}
        for dimension in RATING_DIMENSIONS:
            try:
                values = [int(str(row[dimension])) for row in group]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("HANNA CSV rating is invalid") from exc
            if any(value not in range(1, 6) for value in values):
                raise ValueError("HANNA CSV rating is outside 1..5")
            means[dimension] = sum(values) / 3.0
        story_sha = hashlib.sha256(str(group[0]["Story"]).encode("utf-8")).hexdigest()
        prompt_sha = hashlib.sha256(str(group[0]["Prompt"]).encode("utf-8")).hexdigest()
        key = (story_sha, prompt_sha)
        if key in result:
            raise ValueError("HANNA CSV has duplicate story/prompt content")
        result[key] = {"item_id": f"hanna-{story_id}", "human_dimension_means": means, "human_overall": sum(means.values()) / len(means)}
    return result


def _sanitized_task_contract(task: Mapping[str, Any]) -> dict[str, Any]:
    contract_id = task.get("contract_id")
    goals = task.get("weighted_goals")
    requirements = task.get("binding_requirements")
    if contract_id != "hanna" or not isinstance(goals, list) or len(goals) != 1 or not isinstance(requirements, list) or requirements:
        raise ValueError("Fresh88 task contract semantics drifted")
    goal = goals[0]
    if not isinstance(goal, Mapping) or goal.get("goal_id") != "prompt_response" or not isinstance(goal.get("atomic_question"), str) or not isinstance(goal.get("source"), Mapping) or not str(goal["source"].get("reference", "")).strip():
        raise ValueError("Fresh88 dynamic task question is malformed")
    weight = goal.get("weight")
    if type(weight) not in {int, float} or not math.isfinite(float(weight)) or float(weight) <= 0:
        raise ValueError("Fresh88 dynamic task weight is malformed")
    return {"contract_id": "hanna", "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": goal["atomic_question"], "weight": float(weight), "source": {"reference": str(goal["source"]["reference"])}}], "binding_requirements": []}


def _sanitized_verdicts(verdicts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for verdict in verdicts:
        question_id, state = verdict.get("question_id"), verdict.get("verdict")
        if not isinstance(question_id, str) or not isinstance(state, str):
            raise ValueError("native verdict representation is malformed")
        evidence = verdict.get("evidence") or []
        if not isinstance(evidence, list):
            raise ValueError("native verdict evidence is malformed")
        confidence = verdict.get("confidence", 0.0)
        if type(confidence) not in {int, float} or not math.isfinite(float(confidence)):
            raise ValueError("native verdict confidence is malformed")
        safe = {"question_id": question_id, "verdict": state, "confidence": float(confidence), "evidence": [{"reference": "redacted preserved evidence"} for _ in evidence]}
        if state == "NOT_APPLICABLE":
            if not str(verdict.get("note", "")).strip():
                raise ValueError("NOT_APPLICABLE native verdict lacks its required note")
            safe["note"] = "redacted preserved activation note"
        result.append(safe)
    return result


def _compiled_shape(core: Any, modules: Sequence[dict[str, Any]], bundle: Mapping[str, Any], task: Mapping[str, Any], verdicts: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    compiled = core.compile_bundle(modules, dict(bundle), task_contract=task)
    questions = core.compiled_questions(compiled)
    qids = [str(record["question"]["id"]) for record in questions]
    verdict_ids = [str(verdict["question_id"]) for verdict in verdicts]
    if len(questions) != 179 or len(qids) != 179 or len(set(qids)) != 179 or len(verdict_ids) != 179 or len(set(verdict_ids)) != 179 or set(qids) != set(verdict_ids):
        raise ValueError("Fresh88 native run does not have the exact 179-question union")
    dynamic = [record for record in compiled["domain_questions"] if str(record["module_id"]).startswith("task.contract.")]
    static = [record for record in compiled["domain_questions"] if not str(record["module_id"]).startswith("task.contract.")]
    if len(compiled["domain_questions"]) != 144 or len(dynamic) != 1 or len(static) != 143 or dynamic[0]["question"]["id"] != "task.contract.hanna.prompt_response":
        raise ValueError("Fresh88 static/dynamic question composition drifted")
    return questions, static, compiled


def _component_families(weights: Any, modules: Sequence[dict[str, Any]], bundle: Mapping[str, Any], static: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    profile = weights.make_weight_profile(modules, bundle, profile_id="frozen-family-weighting-v1")
    components = profile.get("component_weights")
    if not isinstance(components, list) or len(components) != 20:
        raise ValueError("Fresh88 bundle does not have exactly 20 static components")
    result: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, Mapping):
            raise ValueError("Fresh88 component profile is malformed")
        module_id, domain_id, weight = component.get("module_id"), component.get("domain_id"), component.get("weight")
        family = str(module_id).split(".", 1)[0]
        if family not in FAMILIES or not isinstance(domain_id, str) or type(weight) not in {int, float} or not math.isfinite(float(weight)) or float(weight) <= 0:
            raise ValueError("Fresh88 component has an unknown or invalid static family")
        result.append({"domain_id": domain_id, "module_id": str(module_id), "family": family, "base_weight": float(weight)})
    static_modules = {str(record["module_id"]) for record in static}
    component_modules = {row["module_id"] for row in result}
    if component_modules != static_modules or Counter(row["family"] for row in result) != Counter({"core": 11, "craft": 8, "form": 1}):
        raise ValueError("Fresh88 static components have an unclassified family gap")
    return result


def _scoring_context(record: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Mapping[str, Any], Mapping[str, Any], list[dict[str, Any]], list[Mapping[str, Any]]]:
    scoring = record.get("scoring")
    if not isinstance(scoring, Mapping):
        raise ValueError("record lacks canonical scoring context")
    modules, bundle, task, verdicts, components = (scoring.get(key) for key in ("modules", "bundle", "task_contract", "verdicts", "static_components"))
    if not isinstance(modules, list) or not isinstance(bundle, Mapping) or not isinstance(task, Mapping) or not isinstance(verdicts, list) or not isinstance(components, list):
        raise ValueError("record scoring context is malformed")
    return modules, bundle, task, verdicts, components


def _materialized_profile(weights: Any, record: Mapping[str, Any], multipliers: Mapping[str, float]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    modules, bundle, _task, _verdicts, components = _scoring_context(record)
    profile = weights.make_weight_profile(modules, bundle, profile_id="frozen-family-weighting-v1")
    profile_components = profile.get("component_weights")
    if not isinstance(profile_components, list) or len(profile_components) != len(components):
        raise ValueError("record component profile drifted")
    expected = {(str(row["domain_id"]), str(row["module_id"])): row for row in components if isinstance(row, Mapping)}
    if len(expected) != 20:
        raise ValueError("record static component inventory drifted")
    for component in profile_components:
        key = (str(component.get("domain_id")), str(component.get("module_id")))
        item = expected.get(key)
        if item is None or component.get("weight") != item.get("base_weight") or item.get("family") not in FAMILIES:
            raise ValueError("record component-family binding drifted")
        component["weight"] = float(component["weight"]) * float(multipliers[str(item["family"])])
    transformed_modules, transformed_bundle, _audit = weights.materialize_weight_profile(modules, bundle, profile)
    return transformed_modules, transformed_bundle


def _score(core: Any, weights: Any, record: Mapping[str, Any], multipliers: Mapping[str, float]) -> float:
    _modules, _bundle, task, verdicts, _components = _scoring_context(record)
    transformed_modules, transformed_bundle = _materialized_profile(weights, record, multipliers)
    final = core.score_bundle(transformed_modules, transformed_bundle, verdicts, artifact_id=str(record["item_id"]), task_contract=task).get("final_score", {})
    observed = final.get("observed") if isinstance(final, Mapping) else None
    if type(observed) not in {int, float} or not math.isfinite(float(observed)):
        raise ValueError("canonical rescore lacks a finite observed final score")
    return float(observed)


def rescore(records: Sequence[Mapping[str, Any]], multipliers: Mapping[str, float]) -> dict[str, float]:
    """Re-score adapter records with complete family multipliers and no provider use."""
    if set(multipliers) != set(FAMILIES):
        raise ValueError("complete core/craft/form multiplier profile required")
    if any(type(multipliers[name]) not in {int, float} or not math.isfinite(float(multipliers[name])) or float(multipliers[name]) <= 0 for name in FAMILIES):
        raise ValueError("family multipliers must be finite positive numbers")
    if len(records) != 48 or len({str(record.get("item_id")) for record in records}) != 48 or len({str(record.get("prompt_group_id")) for record in records}) != 24:
        raise ValueError("exact TRAIN48/24 records required")
    if not records:
        return {}
    if any(record.get("historical_runtime") != str(HISTORICAL_RUNTIME) for record in records):
        raise ValueError("record historical runtime binding drifted")
    # `build_records` imports the verified runtime.  Refuse a deserialized record
    # in a fresh process rather than silently substituting an unbound runtime.
    loaded = sys.modules.get("hbqrs.core")
    loaded_weights = sys.modules.get("hbqrs.weights")
    if loaded is None or loaded_weights is None:
        raise ValueError("rescore requires records built in this verified process")
    core, weights = loaded, loaded_weights
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        modules, bundle, _task, _verdicts, components = _scoring_context(record)
        key = hashlib.sha256(
            json.dumps(
                {"modules": modules, "bundle": bundle, "static_components": components},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        groups.setdefault(key, []).append(record)
    scores: dict[str, float] = {}
    for records_with_profile in groups.values():
        transformed_modules, transformed_bundle = _materialized_profile(weights, records_with_profile[0], multipliers)
        for record in records_with_profile:
            _modules, _bundle, task, verdicts, _components = _scoring_context(record)
            final = core.score_bundle(transformed_modules, transformed_bundle, verdicts, artifact_id=str(record["item_id"]), task_contract=task).get("final_score", {})
            observed = final.get("observed") if isinstance(final, Mapping) else None
            if type(observed) not in {int, float} or not math.isfinite(float(observed)):
                raise ValueError("canonical rescore lacks a finite observed final score")
            scores[str(record["item_id"])] = float(observed)
    return scores


def build_records(*, split_manifest: Path, execution_freeze: Path, fresh88_contract: Path, raw_runs_root: Path, hanna_csv: Path) -> list[dict[str, Any]]:
    """Return only frozen TRAIN48 records reconstructed from verified native runs."""
    split = _pinned_json(Path(split_manifest), SPLIT_SHA256, label="split manifest")
    freeze = _pinned_json(Path(execution_freeze), EXECUTION_FREEZE_SHA256, label="execution freeze")
    fresh = _pinned_json(Path(fresh88_contract), FRESH88_CONTRACT_SHA256, label="Fresh88 execution contract")
    train = _train_rows(split)
    schedule = _schedule_bindings(freeze, train)
    core, weights, verify_binary_run = _runtime_api(fresh)
    base = fresh.get("base_frozen")
    cells = fresh.get("cells")
    if not isinstance(base, Mapping) or not isinstance(cells, list) or len(cells) != 88:
        raise ValueError("Fresh88 execution contract is incomplete")
    runs_root = Path(raw_runs_root) / "runs"
    if not runs_root.is_dir() or runs_root.is_symlink():
        raise ValueError("Fresh88 raw runs root is unavailable or aliased")
    resolved_runs = runs_root.resolve()
    human = _human_items(Path(hanna_csv))
    cells_by_source: dict[tuple[str, str], Mapping[str, Any]] = {}
    for cell in cells:
        if not isinstance(cell, Mapping) or not isinstance(cell.get("external_input"), Mapping):
            raise ValueError("Fresh88 cell is malformed")
        external = cell["external_input"]
        source, prompt = external.get("source.md"), external.get("prompt.md")
        if not isinstance(source, Mapping) or not isinstance(prompt, Mapping) or not isinstance(source.get("sha256"), str) or not isinstance(prompt.get("sha256"), str):
            raise ValueError("Fresh88 external input binding is malformed")
        key = (str(source["sha256"]), str(prompt["sha256"]))
        if key in cells_by_source:
            raise ValueError("Fresh88 execution contract has duplicate source/prompt cells")
        cells_by_source[key] = cell
    records: list[dict[str, Any]] = []
    for selected in train:
        frozen_schedule = schedule[selected["item_id"]]
        story_sha, prompt_sha = frozen_schedule[0]["story_sha256"], frozen_schedule[0]["prompt_sha256"]
        cell = cells_by_source.get((story_sha, prompt_sha))
        human_row = human.get((story_sha, prompt_sha))
        if cell is None or human_row is None or cell.get("item_id") != human_row["item_id"]:
            raise ValueError("TRAIN source binding does not join uniquely to Fresh88 and HANNA")
        run_dir = runs_root / str(cell.get("item_id"))
        if not run_dir.is_dir() or run_dir.is_symlink() or run_dir.resolve().parent != resolved_runs:
            raise ValueError("Fresh88 selected native run is missing or aliased")
        frozen = _historical_base(base)
        frozen.update({key: cell[key] for key in ("artifact", "contexts", "task_contract")})
        execution = dict(frozen["execution"])
        execution["artifact_id"] = cell["item_id"]
        frozen["execution"] = execution
        verified = verify_binary_run(run_dir, frozen)
        verdicts = core.load_verdicts(run_dir / "verdicts.jsonl")
        task = core.load_data(Path(str(cell["task_contract"]["path"])))
        if not isinstance(task, Mapping):
            raise ValueError("Fresh88 task contract is malformed")
        safe_task = _sanitized_task_contract(task)
        questions, static, _compiled = _compiled_shape(core, core.load_modules(frozen["registry"]["path"]), core.resolve_bundle(core.load_bundles(frozen["bundles"]["path"]), execution["bundle_id"]), safe_task, verdicts)
        modules = core.load_modules(frozen["registry"]["path"])
        bundle = core.resolve_bundle(core.load_bundles(frozen["bundles"]["path"]), execution["bundle_id"])
        components = _component_families(weights, modules, bundle, static)
        safe_verdicts = _sanitized_verdicts(verdicts)
        score_v2 = _json(run_dir / "score.v2.json", label="Fresh88 score.v2")
        final = score_v2.get("final_score")
        observed = final.get("observed") if isinstance(final, Mapping) else None
        if type(observed) not in {int, float} or not math.isfinite(float(observed)):
            raise ValueError("Fresh88 score.v2 lacks finite final_score.observed")
        record = {
            "item_id": human_row["item_id"],
            "prompt_group_id": selected["prompt_group_id"],
            "human_overall": human_row["human_overall"],
            "human_overall_proxy": human_row["human_overall"],
            "human_dimension_means": human_row["human_dimension_means"],
            "original_final_score": float(observed),
            "historical_runtime": str(HISTORICAL_RUNTIME),
            "commitments": {"split_item_id": selected["item_id"], "source": {"story_sha256": story_sha, "prompt_sha256": prompt_sha, "task_contract_sha256": cell["external_input"]["task-contract.json"]["sha256"]}, "payload": frozen_schedule, "native": verified},
            "missingness": {"verdict_state_counts": dict(sorted(Counter(str(verdict["verdict"]) for verdict in safe_verdicts).items())), "verdict_state_by_question": {str(verdict["question_id"]): str(verdict["verdict"]) for verdict in safe_verdicts}},
            "scoring": {"modules": modules, "bundle": bundle, "task_contract": safe_task, "verdicts": safe_verdicts, "static_components": components, "compiled_question_ids": [str(question["question"]["id"]) for question in questions]},
        }
        record["all_one_final_score"] = _score(core, weights, record, {family: 1.0 for family in FAMILIES})
        if record["all_one_final_score"] != record["original_final_score"]:
            raise ValueError(f"all-one historical final-score parity failed for {record['item_id']}")
        records.append(record)
    if len(records) != 48 or len({record["item_id"] for record in records}) != 48 or len({record["prompt_group_id"] for record in records}) != 24:
        raise ValueError("reconstruction did not yield exact TRAIN48/24 geometry")
    return sorted(records, key=lambda record: (str(record["prompt_group_id"]), str(record["item_id"])))


def verify_all_one(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Assert exact all-one parity using the canonical reconstructed scorer."""
    scores = rescore(records, {family: 1.0 for family in FAMILIES})
    mismatches = [str(record["item_id"]) for record in records if scores[str(record["item_id"])] != record.get("original_final_score") or record.get("all_one_final_score") != record.get("original_final_score")]
    return {"state": "all_one_parity_pass" if not mismatches else "all_one_parity_failed", "mismatch_count": len(mismatches), "mismatched_item_ids": mismatches}
