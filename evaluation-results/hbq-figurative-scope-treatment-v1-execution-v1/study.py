"""Frozen direct-execution successor for the public figurative DEV package."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id, private_projection, public_projection


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-figurative-scope-treatment-v1"
STUDY_ID = "hbq-figurative-scope-treatment-v1-execution-v1"
PREDECESSOR_COMMIT = "17b2881d6c695a432ed5a36b0a3cb75eae72a5b5"
PREDECESSOR_TREE = "486827c2f97587d7f802e7bb1ec6b8c2dd3a38f7"
PROMPT_REPAIR_PARENT = "fb77e8a61bff6b130147acd7a7c43ce20e88dd14"
CORPUS_NAME = "public-synthetic-prompt-scope-corpus.json"
CORPUS_SHA256 = "a2bea2ed937738e9d70d272f193852ad94c22b0d2611699ae221dcf21a33bb5d"
ARMS = ("baseline", "scope_rendering_only")
REPETITIONS = 3
EXPECTED_CELLS = 28
EXPECTED_REQUESTS = 168
LEAVES = {
    "core.freshness_and_non_genericness.no_default_metaphors",
    "penalty.purple_prose.proportion",
    "penalty.purple_prose.fatigue",
}
BUNDLE_ID = "prose.short_story"
RUNTIME_FILES = (
    "src/hbqrs/runner.py", "src/hbqrs/cli.py", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json", "bundles/all_bundles.json",
)
SUCCESSOR_RUNTIME_FILES = ("study.py", "run.py", "study-contract.json")
LEGACY_SETTLEMENT_BINDINGS = {
    "prompt_repair_parent": PROMPT_REPAIR_PARENT,
    "runtime_head": "89a00d6f6ad8faff53b73c5c6663accb87c8ca92",
    "cwr_files": {
        "bundles/all_bundles.json": "ca20defa2e3350f949dc9da5e69bb9061d5a0c2d6ddcd71bb9399262dad10f86",
        "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
        "registry/all_modules.json": "4da342cc24881c70be11e5e2cd92a7beccbeb024e5808a5c779935f29989a4ed",
        "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
        "src/hbqrs/cli.py": "1948ff57820e0fd4cf3f9ed214056cec22a86fb1946e3a7e1e7738a29de7898f",
        "src/hbqrs/runner.py": "e0189f621da8616ec52d831d24098b4f4c8aeb988f3075028726ccca5342cf35",
    },
    "successor_files": {
        "run.py": "ef3cda68cc26fbf2a5a284fc1077ff44a2481133574eb3ae39f86e92a732e4e2",
        "study-contract.json": "da739a33ae539a73e6909bfb982bac61165e8372b0fdf0a9e863656090a147d2",
        "study.py": "6aae3fdb377773b9b79cac097fb894a64d035dc7b9f3be210df724cc9556816d",
    },
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_prompt_bytes(value: bytes) -> bytes:
    """Canonicalize only universal-newline transport differences; preserve every other byte."""
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path.name}")
    return value


def contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, text=True, encoding="utf-8", capture_output=True, check=False
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _external_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return root
    raise ValueError("private_root must be outside the CWR repository")


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to overwrite frozen file: {path}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_summary(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def validate_package() -> dict[str, Any]:
    value = contract()
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1:
        raise ValueError("Study contract identity drifted")
    predecessor = value.get("predecessor")
    runtime = value.get("runtime")
    schedule = value.get("schedule")
    if predecessor != {
        "study_id": "hbq-figurative-scope-treatment-v1", "commit": PREDECESSOR_COMMIT,
        "tree": PREDECESSOR_TREE, "synthetic_corpus_sha256": CORPUS_SHA256,
    }:
        raise ValueError("Predecessor binding drifted")
    if runtime != {
        "prompt_repair_parent": PROMPT_REPAIR_PARENT, "prompt_rendering_version": 2,
        "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high",
        "batch_size": 1, "batch_attempts": 3, "one_leaf_per_call": True,
        "execute_requires_zero_incremental_charge_acknowledgement": True,
    }:
        raise ValueError("Runtime binding drifted")
    if schedule != {"cells": EXPECTED_CELLS, "arms": list(ARMS), "repetitions": REPETITIONS, "planned_requests": EXPECTED_REQUESTS}:
        raise ValueError("Schedule binding drifted")
    if sha256_file(PREDECESSOR_ROOT / CORPUS_NAME) != CORPUS_SHA256:
        raise ValueError("Published predecessor corpus bytes drifted")
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{PREDECESSOR_ROOT.relative_to(REPO_ROOT).as_posix()}") != PREDECESSOR_TREE:
        raise ValueError("Published predecessor tree binding drifted")
    _git("merge-base", "--is-ancestor", PROMPT_REPAIR_PARENT, "HEAD")
    return {"study_id": STUDY_ID, "planned_requests": EXPECTED_REQUESTS, "predecessor": PREDECESSOR_COMMIT, "prompt_repair_parent": PROMPT_REPAIR_PARENT}


def _corpus() -> list[dict[str, Any]]:
    corpus = load_json(PREDECESSOR_ROOT / CORPUS_NAME)
    records = corpus.get("records")
    if corpus.get("format_version") != 2 or not isinstance(records, list) or len(records) != 18:
        raise ValueError("Published predecessor corpus geometry drifted")
    cells = sum(len(item.get("target_verdicts", {})) for item in records if isinstance(item, Mapping))
    if cells != EXPECTED_CELLS:
        raise ValueError("Published predecessor cell geometry drifted")
    return [dict(item) for item in records]


def _task_contract(*, artifact_id: str, record: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "contract_id": f"fstexec-contract-{ordinal:03d}",
        "artifact_id": artifact_id,
        "context": {
            "artifact_kind": "prose_fiction",
            "declared_scope": record["declared_scope"],
            "completion_status": record["completion_status"],
            "background": [], "constraints": [], "audience": [],
        },
        "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": [],
    }


def _compatibility_override(*, artifact_id: str, task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "artifact_id": artifact_id,
        "bundle_id": BUNDLE_ID,
        "task_contract_sha256": sha256_bytes(canonical_json(task)),
        "contract_id": task["contract_id"],
        "artifact_kind": task["context"]["artifact_kind"],
        "declared_scope": task["context"]["declared_scope"],
        "compatibility_mode": "reviewed_override",
        "decision_id": "fstexec-reviewed-v1-scope-compatibility",
        "reviewer": "hbqrs-reviewed-v1",
        "reason": "Reviewed direct-v4 compatibility for the frozen figurative scope treatment.",
    }


def _condition(*, arm: str, task: Mapping[str, Any] | None) -> dict[str, Any]:
    prompt_spec = {
        "execution": "direct_v4_one_leaf", "arm": arm, "task_contract": task,
        "prompt_rendering_version": 2, "batch_size": 1,
    }
    return {
        "arm": arm,
        "prompt_sha256": sha256_bytes(canonical_json(prompt_spec)),
        "rubric_sha256": sha256_file(REPO_ROOT / "registry" / "all_modules.json"),
    }


def build_schedule() -> list[dict[str, Any]]:
    validate_package()
    schedule: list[dict[str, Any]] = []
    cell_ordinal = 0
    for record in _corpus():
        targets = record["target_verdicts"]
        if not isinstance(targets, Mapping) or not set(targets).issubset(LEAVES):
            raise ValueError("Published predecessor leaf mapping drifted")
        source = "\n".join(record["units"])
        for leaf_id, expected_verdict in sorted(targets.items()):
            cell_ordinal += 1
            artifact_id = f"asset-{cell_ordinal:03d}"
            artifact_sha256 = sha256_bytes(source.encode("utf-8"))
            task = _task_contract(artifact_id=artifact_id, record=record, ordinal=cell_ordinal)
            for arm in ARMS:
                effective_task = None if arm == "baseline" else task
                condition = _condition(arm=arm, task=effective_task)
                for repetition in range(1, REPETITIONS + 1):
                    slot_ordinal = len(schedule) + 1
                    schedule.append({
                        "slot_id": f"slot-{slot_ordinal:03d}", "study_id": STUDY_ID,
                        "artifact_id": artifact_id, "artifact_file": f"asset-{cell_ordinal:03d}.txt",
                        "artifact_text": source, "artifact_sha256": artifact_sha256,
                        "leaf_id": leaf_id, "arm": arm, "repetition": repetition,
                        "condition": condition,
                        "logical_sample_id": logical_sample_id(
                            study_id=STUDY_ID, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
                            condition=condition, repetition=repetition, rubric_revision="1.2.0",
                        ),
                        "task_contract": effective_task,
                        "compatibility_override": (
                            _compatibility_override(artifact_id=artifact_id, task=task) if effective_task is not None else None
                        ),
                        "oracle": {
                            "expected_verdict": expected_verdict,
                            "controller_scope_materiality": record["controller_scope_materiality"],
                            "source_case_id": record["case_id"], "source_kind": record["kind"],
                        },
                    })
    if cell_ordinal != EXPECTED_CELLS or len(schedule) != EXPECTED_REQUESTS:
        raise ValueError("Frozen schedule geometry drifted")
    return schedule


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "study_id", "artifact_id", "artifact_file", "artifact_sha256", "leaf_id", "arm", "repetition", "condition", "logical_sample_id")}


def _runtime_bindings() -> dict[str, Any]:
    return {
        "prompt_repair_parent": PROMPT_REPAIR_PARENT,
        "runtime_head": _git("rev-parse", "HEAD"),
        "cwr_files": {name: sha256_file(REPO_ROOT / name) for name in RUNTIME_FILES},
        "successor_files": {name: sha256_file(ROOT / name) for name in SUCCESSOR_RUNTIME_FILES},
    }


def _validate_runtime_bindings(root: Path) -> None:
    manifest = load_json(root / "study-manifest.json")
    if manifest.get("runtime_bindings") != _runtime_bindings():
        raise ValueError("CWR runtime, prompt, schema, or catalog binding drifted; rerun --dry-run")


def _settlement_binding_mode(root: Path) -> str:
    """Accept one named historical harness only for settlement, never for execution."""
    manifest = load_json(root / "study-manifest.json")
    bindings = manifest.get("runtime_bindings")
    if bindings == _runtime_bindings():
        return "current"
    if bindings == LEGACY_SETTLEMENT_BINDINGS:
        return "legacy_newline_compatibility_only"
    raise ValueError("CWR runtime, prompt, schema, or catalog binding drifted; rerun --dry-run")


def _v1_study() -> Any:
    spec = importlib.util.spec_from_file_location("fst_execution_predecessor", PREDECESSOR_ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load published v1 study")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _predecessor_rows() -> dict[tuple[str, str, str, int], dict[str, Any]]:
    module = _v1_study()
    rows = module.build_plan(module.load_json(CORPUS_NAME), module.load_json("study-contract.json"))
    result: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = (row["case_id"], row["leaf_id"], row["arm"], row["repeat"])
        result[key] = row
    if len(result) != EXPECTED_REQUESTS:
        raise ValueError("Published v1 response plan drifted")
    return result


def prepare(private_root: str | Path) -> dict[str, Any]:
    root = _external_root(private_root)
    schedule = build_schedule()
    runtime_bindings = _runtime_bindings()
    for slot in schedule:
        _write_or_verify(root / "inputs" / slot["artifact_file"], slot["artifact_text"].encode("utf-8"))
        if slot["task_contract"] is not None:
            ordinal = int(slot["artifact_id"].split("-")[1])
            _write_or_verify(root / "contracts" / f"contract-{ordinal:03d}.json", canonical_json(slot["task_contract"]))
            _write_or_verify(root / "compatibility" / f"compat-{ordinal:03d}.json", canonical_json(slot["compatibility_override"]))
    manifest = {
        "format_version": 2, "study_id": STUDY_ID, "runtime_bindings": runtime_bindings,
        "contract_sha256": sha256_file(ROOT / "study-contract.json"),
        "predecessor_corpus_sha256": CORPUS_SHA256,
        "planned_requests": EXPECTED_REQUESTS,
        "slots": [_public_slot(slot) for slot in schedule],
    }
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": schedule}))
    return {"private_root": str(root), "planned_requests": len(schedule), "provider_calls": 0}


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, resume: bool = False) -> list[str]:
    root = _external_root(private_root)
    command = [
        sys.executable, "-m", "hbqrs", "judge", str(root / "inputs" / slot["artifact_file"]), "--bundle", BUNDLE_ID,
        "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high",
        "--output-dir", str(root / "runs" / slot["slot_id"]), "--artifact-id", slot["artifact_id"],
        "--question-id", slot["leaf_id"], "--batch-size", "1", "--batch-attempts", "3",
    ]
    if slot["task_contract"] is not None:
        ordinal = int(str(slot["artifact_id"]).split("-")[1])
        command.extend([
            "--task-contract", str(root / "contracts" / f"contract-{ordinal:03d}.json"),
            "--scope-compatibility-override", str(root / "compatibility" / f"compat-{ordinal:03d}.json"),
        ])
    if resume:
        command.append("--resume")
    return command


def _render_command(slot: Mapping[str, Any], root: Path) -> list[str]:
    command = [
        sys.executable, "-m", "hbqrs", "render-judge", "--bundle", BUNDLE_ID,
        "--artifact", str(root / "inputs" / slot["artifact_file"]), "--artifact-id", slot["artifact_id"],
        "--provider", "codex", "--model", "gpt-5.6-sol", "--question-id", slot["leaf_id"],
    ]
    if slot["task_contract"] is not None:
        ordinal = int(str(slot["artifact_id"]).split("-")[1])
        command.extend([
            "--task-contract", str(root / "contracts" / f"contract-{ordinal:03d}.json"),
            "--scope-compatibility-override", str(root / "compatibility" / f"compat-{ordinal:03d}.json"),
        ])
    return command


def _runtime_schedule(root: Path, schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for slot in schedule:
        prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if not prompt_path.is_file():
            raise ValueError(f"Missing rendered prompt for {slot['slot_id']}")
        result = dict(slot)
        condition = {
            "arm": slot["arm"], "prompt_sha256": sha256_file(prompt_path),
            "rubric_sha256": sha256_file(REPO_ROOT / "registry" / "all_modules.json"),
        }
        result["condition"] = condition
        result["logical_sample_id"] = logical_sample_id(
            study_id=STUDY_ID, artifact_id=slot["artifact_id"], artifact_sha256=slot["artifact_sha256"],
            condition=condition, repetition=slot["repetition"], rubric_revision="1.2.0",
        )
        resolved.append(result)
    return resolved


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    result = prepare(private_root)
    root = _external_root(private_root)
    schedule = build_schedule()
    for slot in schedule:
        command = [*command_for(slot, root, resume=(root / "runs" / slot["slot_id"] / "run.json").is_file()), "--dry-run"]
        completed = runner_call(command, text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(completed, "returncode", 1) != 0:
            raise RuntimeError(f"CWR dry-run stopped at {slot['slot_id']}")
        prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = _render_command(slot, root)
        completed = runner_call(rendered, text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(completed, "returncode", 1) != 0:
            raise RuntimeError(f"CWR prompt rendering stopped at {slot['slot_id']}")
        prompt_path.write_bytes(str(getattr(completed, "stdout", "")).encode("utf-8"))
    resolved = _runtime_schedule(root, schedule)
    preview = {
        "mode": "dry_run", "provider_calls": 0, "planned_requests": len(schedule),
        "first_command": command_for(schedule[0], private_root),
        "last_command": command_for(schedule[-1], private_root),
        "runtime_bindings": _runtime_bindings(),
        "rendered_prompt_sha256s": {slot["slot_id"]: slot["condition"]["prompt_sha256"] for slot in resolved},
    }
    _write_summary(root / "runtime-schedule.json", canonical_json({"format_version": 1, "slots": resolved}))
    _write_summary(root / "dry-run.json", canonical_json(preview))
    return {**result, **preview}


def _run_counts(root: Path, slot: Mapping[str, Any]) -> dict[str, int]:
    run_dir = root / "runs" / str(slot["slot_id"])
    accepted = len(list((run_dir / "responses").glob("batch-[0-9][0-9][0-9][0-9].json")))
    rejected = sum(len(runner._rejected_records(run_dir, batch)) for batch in range(1, accepted + 2)) if run_dir.is_dir() else 0
    return {"accepted": accepted, "rejected": rejected}


def execute(private_root: str | Path, *, resume: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires an explicit zero-incremental-charge acknowledgement")
    root = _external_root(private_root)
    _validate_runtime_bindings(root)
    prepared = load_json(root / "runtime-schedule.json")
    if prepared.get("slots") != _runtime_schedule(root, build_schedule()):
        raise ValueError("Rendered prompt or runtime schedule binding drifted; rerun --dry-run")
    schedule = prepared["slots"]
    before = {slot["slot_id"]: _run_counts(root, slot) for slot in schedule}
    for slot in schedule:
        command = [*command_for(slot, root, resume=True), "--allow-remote"]
        completed = runner_call(command, text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(completed, "returncode", 1) != 0:
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}")
    after = {slot["slot_id"]: _run_counts(root, slot) for slot in schedule}
    accepted = sum(after[key]["accepted"] - before[key]["accepted"] for key in after)
    rejected = sum(after[key]["rejected"] - before[key]["rejected"] for key in after)
    return {"mode": "resume" if resume else "execute", "inspected_slots": len(schedule), "completed_slots": sum(count["accepted"] == 1 for count in after.values()), "accepted_provider_sends": accepted, "rejected_provider_sends": rejected}


def _gate_name(slot: Mapping[str, Any]) -> str | None:
    leaf = slot["leaf_id"]
    oracle = slot["oracle"]
    if oracle["source_kind"] == "control":
        return "control"
    if leaf == "core.freshness_and_non_genericness.no_default_metaphors":
        if oracle["source_case_id"] == "isolated-local-defect":
            return "isolated_yes_revision_note"
        if oracle["source_case_id"] == "recurring-scope-defect":
            return "recurring_no"
        return "stockness"
    if leaf == "penalty.purple_prose.proportion":
        return "proportion_material_load"
    if leaf == "penalty.purple_prose.fatigue":
        if oracle["source_case_id"] in {"incomplete-scope", "unknown-coverage"}:
            return "excerpt_cannot_assess"
        return "fatigue"
    raise ValueError("Unexpected frozen leaf")


def _verify_checkpoint_prompt(run_dir: Path, prompt_path: Path) -> dict[str, str]:
    checkpoint_prompt = run_dir / "responses" / "batch-0001.prompt.txt.gz"
    try:
        checkpoint_bytes = gzip.decompress(checkpoint_prompt.read_bytes())
        rendered_bytes = prompt_path.read_bytes()
        if canonical_prompt_bytes(checkpoint_bytes) != canonical_prompt_bytes(rendered_bytes):
            raise ValueError("CWR checkpoint prompt does not equal the frozen rendered prompt")
    except OSError as exc:
        raise ValueError("CWR checkpoint prompt is unavailable or malformed") from exc
    return {
        "checkpoint_prompt_sha256": sha256_bytes(checkpoint_bytes),
        "rendered_prompt_sha256": sha256_bytes(rendered_bytes),
        "canonical_prompt_sha256": sha256_bytes(canonical_prompt_bytes(checkpoint_bytes)),
    }


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run_dir = root / "runs" / slot["slot_id"]
    manifest_path = run_dir / "run.json"
    if not manifest_path.is_file():
        raise ValueError("missing CWR manifest")
    manifest = load_json(manifest_path)
    configuration = manifest.get("configuration")
    if manifest.get("format_version") != 4 or not isinstance(configuration, Mapping):
        raise ValueError("run is not a v4 CWR manifest")
    expected = {
        "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1,
        "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "question_ids": [slot["leaf_id"]],
    }
    if any(configuration.get(key) != value for key, value in expected.items()):
        raise ValueError("CWR runtime configuration drifted")
    artifact = configuration.get("artifact")
    if not isinstance(artifact, Mapping) or artifact.get("sha256") != slot["artifact_sha256"]:
        raise ValueError("CWR artifact binding drifted")
    if configuration.get("contexts") != []:
        raise ValueError("Execution successor permits no additional context")
    contract_path = root / "contracts" / f"contract-{int(str(slot['artifact_id']).split('-')[1]):03d}.json"
    expected_contract = slot["task_contract"]
    if expected_contract is None:
        if configuration.get("task_contract") is not None or configuration.get("scope_compatibility") is not None:
            raise ValueError("Baseline must not carry a task contract")
    else:
        contract_record = configuration.get("task_contract")
        if not isinstance(contract_record, Mapping) or contract_record.get("sha256") != sha256_file(contract_path):
            raise ValueError("Treatment task contract is not bound")
        override_path = root / "compatibility" / f"compat-{int(str(slot['artifact_id']).split('-')[1]):03d}.json"
        expected_scope = {
            "mode": "reviewed_override", "path": str(override_path.resolve()), "name": override_path.name,
            "bytes": len(override_path.read_bytes()), "sha256": sha256_file(override_path), "format_version": 1,
            "decision_id": slot["compatibility_override"]["decision_id"], "reviewer": slot["compatibility_override"]["reviewer"],
        }
        if configuration.get("scope_compatibility") != expected_scope:
            raise ValueError("Treatment reviewed override is not bound")
        expected_context = runner._task_contract_judge_context_record(
            runner._task_contract_judge_context(expected_contract)
        )
        if configuration.get("task_contract_judge_context") != expected_context:
            raise ValueError("Treatment model-facing task context is not bound")
    prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    if not prompt_path.is_file() or sha256_file(prompt_path) != slot["condition"]["prompt_sha256"]:
        raise ValueError("Actual rendered prompt binding drifted")
    prompt_commitments = _verify_checkpoint_prompt(run_dir, prompt_path)
    verdicts, checkpoints, chain_head = runner._load_checkpoints(
        run_dir, artifact_text=slot["artifact_text"], context_texts=[], batch_attempts=3,
        normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY,
    )
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]:
        raise ValueError("CWR checkpoint does not contain exactly the frozen leaf")
    if not isinstance(verdicts[0].get("run_id"), str) or not verdicts[0]["run_id"].strip():
        raise ValueError("CWR run identity is missing")
    checkpoint = load_json(run_dir / "responses" / "batch-0001.json")
    reported = checkpoint.get("provider", {}).get("reported", {}) if isinstance(checkpoint.get("provider"), Mapping) else {}
    expected_reported = {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}
    if not isinstance(reported, Mapping) or any(reported.get(key) != value for key, value in expected_reported.items()):
        raise ValueError("CWR provider, model, or reasoning binding drifted")
    session_id = reported.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("CWR provider session identity is missing")
    diagnostic = load_json(run_dir / "diagnostic.json")
    if diagnostic.get("status") != "DIAGNOSTIC_SUBSET" or diagnostic.get("selected_question_ids") != [slot["leaf_id"]]:
        raise ValueError("CWR single-leaf diagnostic binding drifted")
    return {
        "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"],
        "arm": slot["arm"], "gate": _gate_name(slot), "correct": verdicts[0].get("verdict") == slot["oracle"]["expected_verdict"],
        "verdict": verdicts[0].get("verdict"), "run_id": verdicts[0]["run_id"],
        "checkpoint_chain_head_sha256": chain_head, "session_id_sha256": sha256_bytes(session_id.encode("utf-8")),
        **prompt_commitments,
        "evidence": verdicts[0].get("evidence"), "note": verdicts[0].get("note"),
        "accepted_provider_call_count": 1,
        "rejected_retry_count": len(runner._rejected_records(run_dir, 1)),
        "batch_attempt_count": 1 + len(runner._rejected_records(run_dir, 1)),
        "normalization_events": checkpoint.get("normalization_audit", []),
    }


def _summarize(records: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """Apply the unchanged v1 gate membership independently to each paired arm."""
    groups: dict[str, dict[str, list[bool]]] = {arm: defaultdict(list) for arm in ARMS}
    for record in records:
        slot = record["slot"]
        oracle = slot["oracle"]
        arm = record["arm"]
        correct = bool(record["correct"])
        if slot["leaf_id"] == "core.freshness_and_non_genericness.no_default_metaphors":
            groups[arm]["stockness"].append(correct)
        if slot["leaf_id"] == "penalty.purple_prose.proportion":
            groups[arm]["proportion_material_load"].append(correct)
        if slot["leaf_id"] == "penalty.purple_prose.fatigue":
            groups[arm]["fatigue"].append(correct)
        if oracle["source_case_id"] == "isolated-local-defect":
            groups[arm]["isolated_yes_revision_note"].append(correct)
        if oracle["source_case_id"] == "recurring-scope-defect":
            groups[arm]["recurring_no"].append(correct)
        if oracle["source_case_id"] == "incomplete-scope":
            groups[arm]["excerpt_cannot_assess"].append(correct)
        groups[arm]["schema_evidence_provenance"].append(True)
        if oracle["source_kind"] == "control":
            groups[arm]["control"].append(correct)
    named = ("stockness", "proportion_material_load", "fatigue", "isolated_yes_revision_note", "recurring_no", "excerpt_cannot_assess", "schema_evidence_provenance")
    gates: dict[str, Any] = {}
    for arm in ARMS:
        gates[arm] = {name: {"correct": sum(groups[arm][name]), "denominator": len(groups[arm][name]), "passed": bool(groups[arm][name]) and all(groups[arm][name])} for name in named}
    baseline_controls = groups["baseline"].get("control", [])
    treatment_controls = groups["scope_rendering_only"].get("control", [])
    gates["scope_rendering_only"]["zero_control_regression"] = {
        "baseline_correct": sum(baseline_controls), "treatment_correct": sum(treatment_controls),
        "denominator": len(baseline_controls), "passed": bool(treatment_controls) and sum(treatment_controls) >= sum(baseline_controls),
    }
    treatment_passes = all(value["passed"] for value in gates["scope_rendering_only"].values())
    scope_sensitive = ("isolated_yes_revision_note", "recurring_no", "excerpt_cannot_assess")
    improves = [name for name in scope_sensitive if gates["scope_rendering_only"][name]["correct"] > gates["baseline"][name]["correct"]]
    return gates, "GO_TREATMENT" if treatment_passes and improves else "NO_EFFECT" if treatment_passes else "NO_GO"


def settle_incomplete(root: Path, slot_id: str, reason: str, completed: int) -> dict[str, Any]:
    result = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": EXPECTED_REQUESTS, "failures": [{"slot_id": slot_id, "reason": reason}]}
    _write_summary(root / "settlement.json", canonical_json(result))
    _write_summary(root / "public-aggregate.json", canonical_json({"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": EXPECTED_REQUESTS}))
    return result


def _v1_response_rows(schedule: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predecessor = _predecessor_rows()
    by_slot = {slot["slot_id"]: slot for slot in schedule}
    rows: list[dict[str, Any]] = []
    for record in records:
        slot = by_slot[record["slot_id"]]
        oracle = slot["oracle"]
        key = (oracle["source_case_id"], slot["leaf_id"], slot["arm"], slot["repetition"])
        expected = predecessor[key]
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("CWR evidence is missing")
        v1_evidence = _v1_exact_quote_subset(evidence)
        revision_note = record.get("note") if expected["case_id"] == "isolated-local-defect" else None
        if expected["case_id"] == "isolated-local-defect" and (not isinstance(revision_note, str) or not revision_note.strip()):
            raise ValueError("Isolated local defect requires a nonblank revision note")
        rows.append({
            **{key: expected[key] for key in ("request_id", "study_id", "partition", "arm", "case_id", "leaf_id", "repeat", "artifact_sha256", "controller_scope_materiality", "controller_scope_verdict")},
            "revision_note": revision_note, "verdict": record["verdict"], "evidence": v1_evidence,
            "provider_provenance": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "run_id": f"accepted-session-{record['session_id_sha256']}"},
        })
    return sorted(rows, key=lambda item: item["request_id"])


def _v1_exact_quote_subset(evidence: Any) -> list[dict[str, str]]:
    """The v1 adapter is lossy only for summary evidence; raw successor evidence stays private."""
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("CWR evidence is missing")
    result = [
        {"reference": item["reference"], "quote": item["exact_quote"]}
        for item in evidence
        if isinstance(item, Mapping) and isinstance(item.get("reference"), str) and item["reference"].strip()
        and isinstance(item.get("exact_quote"), str) and item["exact_quote"].strip()
    ]
    if not result:
        raise ValueError("Published v1 analyzer requires at least one grounded exact-quote evidence item")
    return result


def _published_v1_analysis(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path = root / "v1-response-rows.json"
    _write_summary(path, canonical_json(rows))
    completed = subprocess.run([sys.executable, "analyze.py", "--responses", str(path)], cwd=PREDECESSOR_ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or "Published v1 analyzer failed")
    result = json.loads(completed.stdout)
    if not isinstance(result, Mapping) or not isinstance(result.get("settlement"), Mapping):
        raise ValueError("Published v1 analyzer returned malformed output")
    return dict(result["settlement"])


def _arm_split(schedule: list[dict[str, Any]], records: list[dict[str, Any]], gates: Mapping[str, Any]) -> dict[str, Any]:
    by_slot = {slot["slot_id"]: slot for slot in schedule}
    memberships = {arm: sorted((by_slot[row["slot_id"]]["oracle"]["source_case_id"], by_slot[row["slot_id"]]["leaf_id"], by_slot[row["slot_id"]]["repetition"]) for row in records if row["arm"] == arm) for arm in ARMS}
    if memberships[ARMS[0]] != memberships[ARMS[1]]:
        raise ValueError("Arm split membership is not paired")
    return {arm: {"slots": len(memberships[arm]), "paired_membership_sha256": sha256_bytes(canonical_json(memberships[arm])), "gates": gates[arm]} for arm in ARMS}


def _decision_from_v1_gates(gates: Mapping[str, Any], published_v1: Mapping[str, Any]) -> str:
    """Promote only an unchanged-v1-valid response table with paired-arm evidence."""
    published_gates = published_v1.get("gates")
    expected_denominators = {
        "stockness": 72, "proportion_material_load": 72, "fatigue": 24,
        "isolated_yes_revision_note": 6, "recurring_no": 6,
        "excerpt_cannot_assess": 6, "schema_evidence_provenance": 168,
        "control_regression": 24,
    }
    if (
        published_v1.get("denominator") != EXPECTED_REQUESTS
        or not isinstance(published_gates, Mapping)
        or set(published_gates) != set(expected_denominators)
        or any(not isinstance(published_gates[name], Mapping) or published_gates[name].get("denominator") != denominator for name, denominator in expected_denominators.items())
    ):
        raise ValueError("Published v1 analyzer did not return its gates")
    schema_gate = published_gates["schema_evidence_provenance"]
    if schema_gate.get("passed") is not True or schema_gate.get("correct") != EXPECTED_REQUESTS:
        return "NO_GO"
    treatment = gates["scope_rendering_only"]
    if not all(item["passed"] for item in treatment.values()):
        return "NO_GO"
    scope_sensitive = ("isolated_yes_revision_note", "recurring_no", "excerpt_cannot_assess")
    if any(treatment[name]["correct"] > gates["baseline"][name]["correct"] for name in scope_sensitive):
        return "GO_TREATMENT"
    return "NO_EFFECT"


def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    root = _external_root(private_root)
    try:
        binding_mode = _settlement_binding_mode(root)
    except (OSError, ValueError) as exc:
        return settle_incomplete(root, "runtime", str(exc), 0)
    schedule_path = root / "runtime-schedule.json"
    if not schedule_path.is_file():
        result = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": 0, "planned_slots": EXPECTED_REQUESTS, "failures": [{"slot_id": "schedule", "reason": "Run --dry-run before settlement"}]}
        _write_summary(root / "settlement.json", canonical_json(result))
        _write_summary(root / "public-aggregate.json", canonical_json({"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False}))
        return result
    stored = load_json(schedule_path)
    schedule = stored.get("slots")
    try:
        expected_schedule = _runtime_schedule(root, build_schedule())
    except (OSError, ValueError) as exc:
        expected_schedule = None
        schedule_error = str(exc)
    else:
        schedule_error = "runtime schedule does not match this frozen package"
    if not isinstance(schedule, list) or schedule != expected_schedule:
        result = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": 0, "planned_slots": EXPECTED_REQUESTS, "failures": [{"slot_id": "schedule", "reason": schedule_error}]}
        _write_summary(root / "settlement.json", canonical_json(result))
        _write_summary(root / "public-aggregate.json", canonical_json({"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False}))
        return result
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for slot in schedule:
        try:
            record = verifier(root, slot)
            record["slot"] = slot
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": slot["slot_id"], "reason": str(exc)})
    if failures or len(records) != EXPECTED_REQUESTS:
        result = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": len(records), "planned_slots": EXPECTED_REQUESTS, "failures": failures}
        _write_summary(root / "settlement.json", canonical_json(result))
        _write_summary(root / "public-aggregate.json", canonical_json({"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": len(records), "planned_slots": EXPECTED_REQUESTS}))
        return result
    if len({record["session_id_sha256"] for record in records}) != EXPECTED_REQUESTS:
        return settle_incomplete(root, "identity", "CWR provider sessions are not unique across the schedule", len(records))
    if len({record["checkpoint_chain_head_sha256"] for record in records}) != EXPECTED_REQUESTS:
        return settle_incomplete(root, "identity", "CWR checkpoint chains are not unique across the schedule", len(records))
    gates, _unused_decision = _summarize(records)
    identity_rows = []
    by_slot = {slot["slot_id"]: slot for slot in schedule}
    for record in records:
        slot = by_slot[record["slot_id"]]
        identity_rows.append({
            "study_id": STUDY_ID, "artifact_id": slot["artifact_id"], "artifact_sha256": slot["artifact_sha256"],
            "condition": slot["condition"], "repetition": slot["repetition"], "rubric_revision": "1.2.0",
            "verified_run": {key: record[key] for key in ("accepted_provider_call_count", "rejected_retry_count", "batch_attempt_count")},
            "normalization_events": record["normalization_events"], "repair_attempts": [],
        })
    try:
        v1_rows = _v1_response_rows(schedule, records)
        published_v1 = _published_v1_analysis(root, v1_rows)
        arm_split = _arm_split(schedule, records, gates)
        decision = _decision_from_v1_gates(gates, published_v1)
    except (OSError, ValueError, runner.HBQError) as exc:
        return settle_incomplete(root, "v1", str(exc), len(records))
    settlement = {"study_id": STUDY_ID, "decision": decision, "runtime_binding_mode": binding_mode, "v1_evidence_projection": "exact_quote_subset_only; raw mixed evidence remains in private records", "completed_slots": len(records), "planned_slots": EXPECTED_REQUESTS, "gates": gates, "published_v1_analysis": published_v1, "arm_split": arm_split, "private_identity": private_projection(identity_rows, repetitions=REPETITIONS), "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "runtime_binding_mode": binding_mode, "completed_slots": len(records), "planned_slots": EXPECTED_REQUESTS, "gates": gates, "arm_split": arm_split, "published_v1_all_frozen_gates_pass": published_v1.get("all_frozen_gates_pass"), "aggregate_identity": public_projection(identity_rows, repetitions=REPETITIONS)}
    _write_summary(root / "settlement.json", canonical_json(settlement))
    _write_summary(root / "public-aggregate.json", canonical_json(public))
    return settlement


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("verify")
    for name in ("prepare", "settle"):
        child = subcommands.add_parser(name)
        child.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        print(json.dumps(validate_package(), sort_keys=True))
    elif args.command == "prepare":
        print(json.dumps(prepare(args.private_root), sort_keys=True))
    else:
        print(json.dumps(settle(args.private_root), sort_keys=True))


if __name__ == "__main__":
    main()
