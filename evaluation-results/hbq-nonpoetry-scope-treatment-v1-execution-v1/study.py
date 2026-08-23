"""Frozen executor for the S2 public manual wording/evidence-scope treatment."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import core, runner
from hbqrs.study_identity import logical_sample_id

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-nonpoetry-scope-treatment-v1"
PREDECESSOR_COMMIT = "6366bb3901e900ff73ddf5f5981d617954ea4a28"
PREDECESSOR_TREE = "e41eca02e8a67adbae6c736edac842ad31231f2f"
STUDY_ID = "hbq-nonpoetry-scope-treatment-v1-execution-v1"
PREDECESSOR_EXECUTION_ID = "hbq-nonpoetry-scope-sentinel-v1-execution-v1"
PREDECESSOR_EXECUTION_COMMIT = "a7e23b3"
PREDECESSOR_EXECUTION_TREE = "6c04c0bf77da5733c5623bcbd02758ad90af2b5b"
PREDECESSOR_EXECUTION_FILES = {
    "README.md": "8c27bac287933c07d2d6b5306690dbd0abb08c3e",
    "run.py": "b66ec188da7f104d649ef3b0f8ba26ff602f2762",
    "study-contract.json": "bec87aa79839a737c9a3ff5df4aeb254797eb756",
    "study.py": "6d580d5c2f0fe3aa5bef4b3d49afb19ed299d228",
}
PREDECESSOR_TREATMENT_FILES = {
    "README.md": "1f873529d8d808d91813ed001f781d306814c8b4",
    "private-four-state-holdout-contract.json": "8197df47c3cab69523ab1cd5e26148412536019a",
    "run.py": "ccff7b2559b7cc7a352f950c12ae30a394ed713e",
    "study-contract.json": "eeb9b24186c8e5581cc475b04f2a69df5e09d465",
    "study.py": "09734a398eadd4f136686f3163817a5d39e70e9d",
    "verify_output.py": "28c8ec5bc4e68e3b404112b5ee9c5e08bf7d04af",
}
BUNDLE_ID = "s2-manual-treatment-development"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
NEW_SLOTS, REUSED_SLOTS, REPEATS, MAX_SENDS = 27, 6, 3, 81
RUNTIME_FILES = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json",
    "registry/question_index.jsonl", "registry/criterion_ownership.json", "bundles/all_bundles.json",
    "src/hbqrs/runner.py", "src/hbqrs/cli.py", "src/hbqrs/core.py",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "git binding lookup failed")
    return completed.stdout.strip()


def _external_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        return root
    raise ValueError("private_root must be outside the CWR checkout")


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate frozen private artifact: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_summary(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def _treatment() -> Any:
    spec = importlib.util.spec_from_file_location("s2_treatment_predecessor", PREDECESSOR_ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load frozen S2 treatment")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _predecessor_execution() -> Any:
    root = ROOT.parent / "hbq-nonpoetry-scope-sentinel-v1-execution-v1"
    spec = importlib.util.spec_from_file_location("s2_execution_predecessor", root / "study.py")
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load frozen S2 predecessor executor")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _predecessor_binding() -> None:
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-nonpoetry-scope-treatment-v1") != PREDECESSOR_TREE:
        raise ValueError("Frozen treatment tree binding drifted")
    if _git("rev-parse", f"{PREDECESSOR_EXECUTION_COMMIT}:evaluation-results/hbq-nonpoetry-scope-sentinel-v1-execution-v1") != PREDECESSOR_EXECUTION_TREE:
        raise ValueError("Frozen executed S2 predecessor tree binding drifted")
    _git("merge-base", "--is-ancestor", PREDECESSOR_COMMIT, "HEAD")
    _git("merge-base", "--is-ancestor", PREDECESSOR_EXECUTION_COMMIT, "HEAD")
    for name, blob in PREDECESSOR_TREATMENT_FILES.items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-nonpoetry-scope-treatment-v1/{name}") != blob or _git("hash-object", str(PREDECESSOR_ROOT / name)) != blob:
            raise ValueError(f"Frozen treatment file drifted: {name}")
    execution_root = ROOT.parent / PREDECESSOR_EXECUTION_ID
    for name, blob in PREDECESSOR_EXECUTION_FILES.items():
        if _git("rev-parse", f"{PREDECESSOR_EXECUTION_COMMIT}:evaluation-results/{PREDECESSOR_EXECUTION_ID}/{name}") != blob or _git("hash-object", str(execution_root / name)) != blob:
            raise ValueError(f"Frozen executed predecessor file drifted: {name}")


def _source_question(leaf_id: str, question: Mapping[str, Any]) -> dict[str, Any]:
    return {key: question[key] for key in ("id", "module_id", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity")}


def _canonical_prompt(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""):
        raise ValueError("Prompt contains a lone carriage return")
    return value.replace(b"\r\n", b"\n")


def _arm_registry_bytes(arm: str) -> bytes:
    if arm not in {"current_wording", "candidate_wording"}:
        raise ValueError("Unknown treatment arm")
    modules = json.loads((REPOSITORY / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    source = _treatment().source_status_leaf()
    candidate = dict(source)
    candidate["text"] = _treatment().STATUS_CANDIDATE
    target = candidate if arm == "candidate_wording" else source
    found = 0

    def replace(nodes: list[dict[str, Any]], module_id: str) -> None:
        nonlocal found
        for node in nodes:
            if node.get("id") == "scope.passage.status":
                projected = {key: (module_id if key == "module_id" else node.get(key)) for key in source}
                if projected != source:
                    raise ValueError("Source scope leaf drifted before arm overlay")
                node["text"] = target["text"]
                found += 1
            children = node.get("children")
            if isinstance(children, list):
                replace(children, module_id)

    for module in modules:
        tree = module.get("tree")
        if isinstance(tree, list):
            replace(tree, str(module.get("module_id")))
    if found != 1:
        raise ValueError("Arm overlay did not modify exactly one source leaf")
    result = canonical_json(modules)
    if arm == "current_wording" and json.loads(result.decode("utf-8")) != modules:
        raise ValueError("Current arm overlay serialization drifted")
    return result


def _arm_question_index_bytes(arm: str) -> bytes:
    source_rows = [json.loads(line) for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines() if line]
    source = _treatment().source_status_leaf()
    candidate = dict(source)
    candidate["text"] = _treatment().STATUS_CANDIDATE
    target = candidate if arm == "candidate_wording" else source
    found = 0
    rows: list[bytes] = []
    for row in source_rows:
        if row.get("id") == "scope.passage.status":
            if {key: row.get(key) for key in source} != source:
                raise ValueError("Source question-index leaf drifted before arm overlay")
            row["text"] = target["text"]
            found += 1
        rows.append(canonical_json(row))
    if found != 1:
        raise ValueError("Question-index overlay did not modify exactly one source leaf")
    return b"\n".join(rows) + b"\n"


def _private_bundle() -> list[dict[str, Any]]:
    treatment = _treatment()
    leaves = (
        "modifier.genre.hybrid_or_genre_blend.tone",
        "op.critique.single_unit_critique.no_whole_claims",
        "scope.passage.status",
    )
    records = {leaf: treatment.source_leaf(leaf) for leaf in leaves}
    components = [{"module_id": records[leaf]["module_id"], "weight": 1.0, "include_question_ids": [leaf]} for leaf in leaves]
    return [{"standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1, "title": "S2 manual-treatment singleton bundle", "module_ids": [item["module_id"] for item in records.values()], "task_contract_domain_id": "s2mt", "domains": [{"domain_id": "s2mt", "title": "S2 manual treatment", "points": 3.0, "components": components, "score_mode": "weighted_binary_mean"}], "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": False, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True}, "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True}}]


def _overlay_files() -> dict[str, bytes]:
    return {
        "prompts/judge/JUDGE_PREFIX.md": (REPOSITORY / "prompts" / "judge" / "JUDGE_PREFIX.md").read_bytes(),
        "prompts/judge/BINARY_EVALUATION_PROMPT.md": (REPOSITORY / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_bytes(),
        "schema/hbq_judge_response.schema.json": (REPOSITORY / "schema" / "hbq_judge_response.schema.json").read_bytes(),
        "schema/hbq_task_contract.schema.json": (REPOSITORY / "schema" / "hbq_task_contract.schema.json").read_bytes(),
        "schema/hbq_verdict.schema.json": (REPOSITORY / "schema" / "hbq_verdict.schema.json").read_bytes(),
        "schema/hbq_diagnostic_report.schema.json": (REPOSITORY / "schema" / "hbq_diagnostic_report.schema.json").read_bytes(),
        "registry/all_modules.json": _arm_registry_bytes("current_wording"),
    }


def build_schedule() -> list[dict[str, Any]]:
    _predecessor_binding()
    treatment = _treatment(); treatment.validate_package()
    schedule: list[dict[str, Any]] = []
    for item in treatment.build_plan():
        if "reuse" in item:
            continue
        artifact, _fixture = treatment._artifact(item["leaf_id"], item["state"])
        ordinal = len(schedule) + 1
        task = {
            "contract_version": 1, "contract_id": f"npsstexec-contract-{ordinal:02d}", "artifact_id": f"s2-treatment-{ordinal:02d}",
            "context": {"artifact_kind": artifact["artifact_kind"], "declared_scope": artifact["declared_scope"], "completion_status": ("excerpt" if any(token in artifact["declared_scope"] for token in ("excerpt", "fragment")) else "complete"), "background": ["Public synthetic S2 treatment execution."], "constraints": ["Use only supplied artifact and context."], "audience": ["development-only rubric validation"]},
            "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": [],
        }
        question = _source_question(item["leaf_id"], item["question"])
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": item["leaf_id"], "arm": item["arm"], "task_contract_sha256": sha256_bytes(canonical_json(task)), "prompt_sha256": sha256_bytes(canonical_json({"question": question, "artifact": artifact, "task": task})), "rubric_sha256": sha256_file(REPOSITORY / "registry" / "all_modules.json")}
        row = {
            "slot_id": f"npsstexec-v1-{ordinal:02d}", "source_slot_id": item["slot_id"], "study_id": STUDY_ID,
            "artifact_id": task["artifact_id"], "artifact_text": artifact["text"], "artifact_sha256": sha256_bytes(artifact["text"].encode("utf-8")),
            "contexts": artifact["contexts"], "leaf_id": item["leaf_id"], "question": question, "state": item["state"], "arm": item["arm"], "repeat": item["repeat"], "expected_verdict": item["expected_verdict"], "task_contract": task, "condition": condition,
        }
        row["judge_id"] = "s2mt-j-" + sha256_bytes(canonical_json({"slot": row["slot_id"], "artifact": row["artifact_id"], "leaf": row["leaf_id"], "arm": row["arm"]}))[:24]
        row["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=task["artifact_id"], artifact_sha256=sha256_bytes(artifact["text"].encode("utf-8")), condition=condition, repetition=item["repeat"], rubric_revision="1.2.0")
        schedule.append(row)
    if len(schedule) != NEW_SLOTS or len({row["slot_id"] for row in schedule}) != NEW_SLOTS:
        raise ValueError("New-slot schedule geometry drifted")
    if sum(row["leaf_id"] == "scope.passage.status" for row in schedule) != 18 or sum(row["leaf_id"] != "scope.passage.status" for row in schedule) != 9:
        raise ValueError("Treatment partition drifted")
    return schedule


def _runtime_bindings() -> dict[str, Any]:
    return {"frozen_treatment_commit": PREDECESSOR_COMMIT, "frozen_execution_commit": PREDECESSOR_EXECUTION_COMMIT, "cwr_files": {name: sha256_file(REPOSITORY / name) for name in RUNTIME_FILES}, "successor_files": {name: sha256_file(ROOT / name) for name in ("study.py", "run.py", "study-contract.json")}}


def validate_package() -> dict[str, Any]:
    _predecessor_binding()
    contract = _load_json(ROOT / "study-contract.json")
    expected = {"format_version": 1, "study_id": STUDY_ID, "status": "frozen_execution_successor_unexecuted", "predecessor": {"treatment": {"study_id": "hbq-nonpoetry-scope-treatment-v1", "commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": PREDECESSOR_TREATMENT_FILES}, "executed_baseline": {"study_id": PREDECESSOR_EXECUTION_ID, "commit": PREDECESSOR_EXECUTION_COMMIT, "tree": PREDECESSOR_EXECUTION_TREE, "files": PREDECESSOR_EXECUTION_FILES}}, "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "batch_attempts": 3, "maximum_provider_sends": MAX_SENDS, "new_provider_calls_exact": NEW_SLOTS, "reused_accepted_calls_exact": REUSED_SLOTS, "one_leaf_per_call": True, "attempt_lifecycle_policy": "terminal_sidecar_v1", "collision_resistant_judge_ids": True, "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden"}, "holdout": "sealed_and_unopened", "promotion": "none"}
    if contract != expected:
        raise ValueError("Execution contract drifted")
    schedule = build_schedule()
    return {"study_id": STUDY_ID, "new_provider_calls": len(schedule), "reused_accepted_calls": REUSED_SLOTS, "sealed_private_holdout": True}


def _paths(root: Path, slot: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    ordinal = str(slot["slot_id"])[-2:]
    return root / "inputs" / f"{ordinal}.txt", root / "contracts" / f"{ordinal}.json", root / "compatibility" / f"{ordinal}.json"


def _context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    ordinal = str(slot["slot_id"])[-2:]
    return [root / "contexts" / ordinal / f"context-{index:02d}.txt" for index, _ in enumerate(slot["contexts"], 1)]


def _override(slot: Mapping[str, Any]) -> dict[str, Any]:
    task = slot["task_contract"]
    return {"format_version": 1, "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "npsstexec-v1-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen S2 treatment execution."}


def _registry_path(root: Path, arm: str) -> Path:
    return root / "registry-overlays" / arm / "all_modules.json"


def _question_index_path(root: Path, arm: str) -> Path:
    return root / "registry-overlays" / arm / "question_index.jsonl"


def _bundle_path(root: Path) -> Path:
    return root / "runtime-s2mt-bundle.json"


def environment_for(private_root: str | Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["HBQRS_ROOT"] = str(_external_root(private_root) / "runtime-book")
    return environment


def prepare(private_root: str | Path) -> dict[str, Any]:
    root = _external_root(private_root); schedule = build_schedule()
    for arm in ("current_wording", "candidate_wording"):
        _write_or_verify(_registry_path(root, arm), _arm_registry_bytes(arm))
        _write_or_verify(_question_index_path(root, arm), _arm_question_index_bytes(arm))
    _write_or_verify(_bundle_path(root), canonical_json(_private_bundle()))
    for relative, value in _overlay_files().items():
        _write_or_verify(root / "runtime-book" / relative, value)
    for slot in schedule:
        artifact, task, override = _paths(root, slot)
        _write_or_verify(artifact, str(slot["artifact_text"]).encode("utf-8")); _write_or_verify(task, canonical_json(slot["task_contract"])); _write_or_verify(override, canonical_json(_override(slot)))
        for path, context in zip(_context_paths(root, slot), slot["contexts"], strict=True): _write_or_verify(path, str(context).encode("utf-8"))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "runtime_bindings": _runtime_bindings(), "contract_sha256": sha256_file(ROOT / "study-contract.json"), "private_overlay_sha256": {path: sha256_bytes(value) for path, value in _overlay_files().items()}, "registry_overlays_sha256": {arm: {"registry": sha256_file(_registry_path(root, arm)), "question_index": sha256_file(_question_index_path(root, arm))} for arm in ("current_wording", "candidate_wording")}, "private_bundle_sha256": sha256_file(_bundle_path(root)), "planned_new_calls": NEW_SLOTS, "reused_accepted_calls": REUSED_SLOTS, "slots": [{key: row[key] for key in ("slot_id", "source_slot_id", "artifact_id", "artifact_sha256", "leaf_id", "arm", "repeat", "expected_verdict", "judge_id", "logical_sample_id")} for row in schedule]}
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest)); _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": schedule}))
    return {"provider_calls": 0, "new_calls": NEW_SLOTS, "reused_calls": REUSED_SLOTS}


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, resume: bool = False) -> list[str]:
    root = _external_root(private_root); artifact, task, override = _paths(root, slot)
    command = [sys.executable, "-m", "hbqrs", "--registry", str(_registry_path(root, str(slot["arm"]))), "--bundles", str(_bundle_path(root)), "judge", str(artifact), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai", "--output-dir", str(root / "runs" / str(slot["slot_id"])), "--artifact-id", str(slot["artifact_id"]), "--judge-id", str(slot["judge_id"]), "--question-id", str(slot["leaf_id"]), "--batch-size", "1", "--batch-attempts", "3", "--attempt-lifecycle-policy", "terminal_sidecar_v1", "--task-contract", str(task), "--scope-compatibility-override", str(override)]
    for context in _context_paths(root, slot): command.extend(["--context", str(context)])
    if resume: command.append("--resume")
    return command


def _render_command(slot: Mapping[str, Any], root: Path, output: Path) -> list[str]:
    artifact, task, override = _paths(root, slot)
    command = [sys.executable, "-m", "hbqrs", "--registry", str(_registry_path(root, str(slot["arm"]))), "--bundles", str(_bundle_path(root)), "render-judge", "--bundle", BUNDLE_ID, "--artifact", str(artifact), "--artifact-id", str(slot["artifact_id"]), "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--question-id", str(slot["leaf_id"]), "--task-contract", str(task), "--scope-compatibility-override", str(override), "--output", str(output)]
    for context in _context_paths(root, slot): command.extend(["--context", str(context)])
    return command


def _runtime_schedule(root: Path, schedule: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for slot in schedule:
        prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if not prompt.is_file(): raise ValueError(f"Missing rendered prompt: {slot['slot_id']}")
        raw = prompt.read_bytes()
        if raw != _canonical_prompt(raw):
            raise ValueError("Frozen rendered prompt is not canonical UTF-8 LF bytes")
        row = dict(slot)
        condition = dict(row["condition"])
        condition.update({"judge_id": row["judge_id"], "registry_overlay_sha256": sha256_file(_registry_path(root, str(row["arm"]))), "question_index_overlay_sha256": sha256_file(_question_index_path(root, str(row["arm"]))), "bundle_sha256": sha256_file(_bundle_path(root)), "prompt_sha256": sha256_bytes(raw), "canonical_prompt_sha256": sha256_bytes(raw)})
        modules = core.load_modules(_registry_path(root, str(row["arm"])))
        bundle = core.load_bundles(_bundle_path(root))[0]
        compiled = core.compile_bundle(modules, bundle, task_contract=row["task_contract"])
        selected = [item for item in core.compiled_questions(compiled) if item["question"]["id"] == row["leaf_id"]]
        required_question = {key: value for key, value in row["question"].items() if key != "module_id"}
        if len(selected) != 1 or {key: selected[0]["question"].get(key) for key in required_question} != required_question:
            raise ValueError("Arm registry did not compile the exact scheduled leaf")
        condition["questions_sha256"] = sha256_bytes(runner._json_bytes(runner._question_payload(selected)))
        condition["compiled_bundle_sha256"] = sha256_bytes(runner._json_bytes(compiled))
        row["condition"] = condition
        row["rendered_prompt_sha256"] = sha256_bytes(raw)
        row["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=str(row["artifact_id"]), artifact_sha256=str(row["artifact_sha256"]), condition=condition, repetition=int(row["repeat"]), rubric_revision="1.2.0")
        rows.append(row)
    return rows


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    root = _external_root(private_root); prepare(root); schedule = build_schedule(); environment = environment_for(root)
    for slot in schedule:
        call = runner_call([*command_for(slot, root, resume=(root / "runs" / str(slot["slot_id"]) / "run.json").is_file()), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(call, "returncode", 1): raise RuntimeError(f"Provider-free dry-run failed: {slot['slot_id']}: {getattr(call, 'stderr', '')}")
        output = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = runner_call(_render_command(slot, root, output), text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(rendered, "returncode", 1) or not output.is_file(): raise RuntimeError(f"Prompt render failed: {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        output.write_bytes(_canonical_prompt(output.read_bytes()))
    resolved = _runtime_schedule(root, schedule); aggregate = sha256_bytes(canonical_json({row["slot_id"]: row["rendered_prompt_sha256"] for row in resolved}))
    _write_or_verify(root / "runtime-schedule.json", canonical_json({"format_version": 1, "slots": resolved, "rendered_prompt_aggregate_sha256": aggregate}))
    for slot in resolved:
        prompt = (root / "rendered-prompts" / f"{slot['slot_id']}.txt").read_text(encoding="utf-8")
        expected_text = str(slot["question"]["text"])
        if expected_text not in prompt:
            raise ValueError("Rendered prompt does not contain the exact arm wording")
        if any(token in prompt.casefold() for token in ("oracle", "expected_verdict", "sealed holdout", "source_slot_id")):
            raise ValueError("Rendered prompt leaked an oracle or label token")
    return {"mode": "dry_run", "provider_calls": 0, "new_slots": len(resolved), "rendered_prompt_aggregate_sha256": aggregate}


def _validate_runtime(root: Path) -> list[dict[str, Any]]:
    manifest = _load_json(root / "study-manifest.json")
    expected_overlays = {arm: {"registry": sha256_file(_registry_path(root, arm)), "question_index": sha256_file(_question_index_path(root, arm))} for arm in ("current_wording", "candidate_wording")}
    if manifest.get("runtime_bindings") != _runtime_bindings() or manifest.get("private_overlay_sha256") != {path: sha256_bytes(value) for path, value in _overlay_files().items()} or manifest.get("registry_overlays_sha256") != expected_overlays or manifest.get("private_bundle_sha256") != sha256_file(_bundle_path(root)):
        raise ValueError("Runtime overlay, bundle, or source bindings drifted; repeat dry-run")
    for relative, value in _overlay_files().items():
        if (root / "runtime-book" / relative).read_bytes() != value:
            raise ValueError("Private runtime prompt overlay drifted")
    if _bundle_path(root).read_bytes() != canonical_json(_private_bundle()):
        raise ValueError("Private three-leaf bundle drifted")
    stored = _load_json(root / "runtime-schedule.json"); expected = _runtime_schedule(root, build_schedule())
    aggregate = sha256_bytes(canonical_json({row["slot_id"]: row["rendered_prompt_sha256"] for row in expected}))
    if stored.get("slots") != expected or stored.get("rendered_prompt_aggregate_sha256") != aggregate: raise ValueError("Prepared schedule drifted; repeat dry-run")
    return expected


def _fresh_execute_preflight(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    for slot in schedule:
        run = root / "runs" / str(slot["slot_id"])
        if not (run / "run.json").is_file(): raise ValueError("Fresh execute requires completed dry-run manifests")
        responses = run / "responses"
        if responses.is_dir() and any(path.is_file() for path in responses.rglob("*")): raise ValueError("Fresh execute rejects prior provider attempts; use --resume")


def execute(private_root: str | Path, *, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge: raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    root = _external_root(private_root); schedule = _validate_runtime(root)
    if not resume: _fresh_execute_preflight(root, schedule)
    environment = environment_for(root)
    for slot in schedule:
        done = runner_call([*command_for(slot, root, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(done, "returncode", 1): raise RuntimeError(f"Execution stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
    return {"mode": "resume" if resume else "execute", "accepted_new_calls_expected": NEW_SLOTS, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}


def _input_record(path: Path) -> dict[str, Any]:
    value = path.read_bytes(); return {"path": str(path.resolve()), "name": path.name, "bytes": len(value), "sha256": sha256_bytes(value)}


def _canonical_prompt(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""): raise ValueError("Prompt contains lone carriage return")
    return value.replace(b"\r\n", b"\n")


def _verify_checkpoint_prompt(run: Path, prompt: Path) -> dict[str, str]:
    try: checkpoint = gzip.decompress((run / "responses" / "batch-0001.prompt.txt.gz").read_bytes())
    except (OSError, EOFError) as exc: raise ValueError("Checkpoint prompt unavailable") from exc
    rendered = prompt.read_bytes()
    if _canonical_prompt(checkpoint) != rendered: raise ValueError("Checkpoint prompt differs from frozen rendered prompt")
    return {"rendered_prompt_sha256": sha256_bytes(rendered), "checkpoint_prompt_sha256": sha256_bytes(checkpoint), "canonical_prompt_sha256": sha256_bytes(_canonical_prompt(checkpoint))}


def _verify_new_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"]); manifest = _load_json(run / "run.json"); config = manifest.get("configuration")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "artifact_id": slot["artifact_id"], "judge_id": slot["judge_id"], "bundle_id": BUNDLE_ID, "question_ids": [slot["leaf_id"]], "questions_sha256": slot["condition"]["questions_sha256"], "compiled_bundle_sha256": slot["condition"]["compiled_bundle_sha256"], "attempt_lifecycle_policy": "terminal_sidecar_v1"}
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping) or any(config.get(key) != value for key, value in expected.items()): raise ValueError("Production singleton run binding drifted")
    if manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)): raise ValueError("Run manifest configuration hash drifted")
    artifact, task, override = _paths(root, slot); contexts = _context_paths(root, slot); prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    if config.get("artifact") != _input_record(artifact) or config.get("contexts") != [_input_record(path) for path in contexts] or config.get("task_contract", {}).get("sha256") != sha256_file(task) or config.get("scope_compatibility", {}).get("sha256") != sha256_file(override): raise ValueError("Artifact/context/contract binding drifted")
    overlay = root / "runtime-book"
    expected_prompts = [sha256_file(overlay / "prompts" / "judge" / name) for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")]
    if [item.get("sha256") for item in config.get("prompts", [])] != expected_prompts or config.get("response_schema", {}).get("sha256") != sha256_file(overlay / "schema" / "hbq_judge_response.schema.json"):
        raise ValueError("Prompt/schema overlay binding drifted")
    commitment = _verify_checkpoint_prompt(run, prompt)
    if commitment["canonical_prompt_sha256"] != slot["condition"]["canonical_prompt_sha256"]:
        raise ValueError("Checkpoint prompt does not bind the frozen arm prompt")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=3, reconstruct=False, strict_v5=True, require_durable=True)
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=str(slot["artifact_text"]), context_texts=[path.read_text(encoding="utf-8") for path in contexts], batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]: raise ValueError("Checkpoint is not the frozen singleton leaf")
    if verdicts[0].get("run_id") != manifest.get("run_id") or verdicts[0].get("judge_id") != slot["judge_id"] or not isinstance(manifest.get("run_id"), str) or not manifest["run_id"].strip(): raise ValueError("Run identity drifted")
    runner._validate_typed_checkpoint_evidence(verdicts[0].get("evidence"), question_id=str(slot["leaf_id"])); runner._validate_exact_quotes(verdicts[0].get("evidence"), artifact_text=str(slot["artifact_text"]), context_texts=[path.read_text(encoding="utf-8") for path in contexts], question_id=str(slot["leaf_id"]))
    reported = _load_json(run / "responses" / "batch-0001.json").get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}: raise ValueError("Provider/model/reasoning binding drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session.strip(): raise ValueError("Provider session missing")
    diagnostic = _load_json(run / "diagnostic.json")
    if diagnostic.get("status") != "DIAGNOSTIC_SUBSET" or diagnostic.get("selected_question_ids") != [slot["leaf_id"]]: raise ValueError("Diagnostic singleton binding drifted")
    rejected = runner._rejected_records(run, 1)
    if _load_json(run / "responses" / "batch-0001.json").get("accepted_attempt") != len(rejected) + 1:
        raise ValueError("Cumulative singleton retry accounting drifted")
    return {"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdicts[0].get("verdict"), "expected": slot["expected_verdict"], "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "run_id": manifest["run_id"], "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "evidence": verdicts[0].get("evidence"), "accepted_provider_call_count": 1, "rejected_retry_count": len(rejected), "batch_attempt_count": 1 + len(rejected), **commitment}


def _reused_slots() -> list[dict[str, Any]]:
    treatment = _treatment(); treatment.validate_package()
    reused = []
    for item in treatment.build_plan():
        binding = item.get("reuse")
        if not isinstance(binding, Mapping):
            continue
        if item.get("leaf_id") != "scope.passage.status" or item.get("arm") != "current_wording" or item.get("state") not in {"material_failure", "activation_mismatch"}:
            raise ValueError("Treatment reuse plan contains an unauthorized condition")
        artifact, fixture_source = treatment._artifact(str(item["leaf_id"]), str(item["state"]))
        if fixture_source != "predecessor-public-fixture":
            raise ValueError("A corrected fixture cannot be reused")
        reused.append({"source_slot_id": binding["predecessor_slot_id"], "leaf_id": item["leaf_id"], "state": item["state"], "repeat": item["repeat"], "expected": item["expected_verdict"], "artifact_text": artifact["text"], "contexts": artifact["contexts"], "source_wording": treatment.source_status_leaf()["text"], "fixture_id": item["fixture_id"]})
    if len(reused) != REUSED_SLOTS or len({item["source_slot_id"] for item in reused}) != REUSED_SLOTS:
        raise ValueError("Reuse plan geometry drifted")
    return reused


def verify_reused_predecessor_calls(predecessor_root: str | Path) -> list[dict[str, Any]]:
    root = _external_root(predecessor_root); predecessor = _predecessor_execution()
    settlement = _load_json(root / "settlement.json")
    if settlement.get("study_id") != PREDECESSOR_EXECUTION_ID or settlement.get("decision") != "DIAGNOSTIC_FAIL": raise ValueError("Immutable predecessor settlement binding drifted")
    runtime_schedule = _load_json(root / "runtime-schedule.json")
    expected_schedule = predecessor._runtime_schedule(root, predecessor.build_schedule())
    if runtime_schedule.get("slots") != expected_schedule:
        raise ValueError("Immutable predecessor runtime schedule drifted")
    schedule = {row["slot_id"]: row for row in expected_schedule}
    verified = []
    for binding in _reused_slots():
        slot = schedule.get(binding["source_slot_id"])
        if not isinstance(slot, Mapping) or slot.get("leaf_id") != binding["leaf_id"] or slot.get("expected_verdict") != binding["expected"] or slot.get("repeat") != binding["repeat"] or slot.get("artifact_text") != binding["artifact_text"] or slot.get("contexts") != binding["contexts"]:
            raise ValueError(f"Immutable predecessor schedule drifted: {binding['source_slot_id']}")
        row = predecessor._verify_slot(root, slot)
        if row.get("accepted_provider_call_count") != 1 or row.get("rejected_retry_count") != 0 or not isinstance(row.get("run_id"), str) or not isinstance(row.get("session_id_sha256"), str) or not isinstance(row.get("checkpoint_chain_head_sha256"), str):
            raise ValueError(f"Immutable predecessor call is not accepted: {binding['source_slot_id']}")
        verified.append({"source_slot_id": binding["source_slot_id"], "leaf_id": binding["leaf_id"], "state": binding["state"], "repeat": binding["repeat"], "expected": binding["expected"], "verdict": row["verdict"], "correct": row.get("correct") is True, "fixture_id": binding["fixture_id"], "source_wording_sha256": sha256_bytes(str(binding["source_wording"]).encode("utf-8")), "run_id_sha256": sha256_bytes(row["run_id"].encode("utf-8")), "session_id_sha256": row["session_id_sha256"], "checkpoint_chain_head_sha256": row["checkpoint_chain_head_sha256"]})
    if len({row["session_id_sha256"] for row in verified}) != REUSED_SLOTS or len({row["checkpoint_chain_head_sha256"] for row in verified}) != REUSED_SLOTS: raise ValueError("Immutable predecessor identity collision")
    return verified


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    value = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_new_slots": completed, "planned_new_slots": NEW_SLOTS, "failures": failures}; _write_summary(root / "settlement.json", value); _write_summary(root / "public-aggregate.json", {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_new_slots": completed, "planned_new_slots": NEW_SLOTS}); return value


def settle(private_root: str | Path, predecessor_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_new_slot) -> dict[str, Any]:
    root = _external_root(private_root)
    try: schedule = _validate_runtime(root); reused = verify_reused_predecessor_calls(predecessor_root)
    except (OSError, ValueError) as exc: return _incomplete(root, 0, [{"slot_id": "binding", "reason": str(exc)}])
    records, failures = [], []
    for slot in schedule:
        try: records.append(verifier(root, slot))
        except (OSError, ValueError, runner.HBQError) as exc: failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != NEW_SLOTS: return _incomplete(root, len(records), failures)
    identities = [(row["logical_sample_id"], row["session_id_sha256"], row["checkpoint_chain_head_sha256"]) for row in records]
    if any(len({item[index] for item in identities}) != NEW_SLOTS for index in range(3)): return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Repeated logical/session/checkpoint identity"}])
    if {row["session_id_sha256"] for row in records} & {row["session_id_sha256"] for row in reused} or {row["checkpoint_chain_head_sha256"] for row in records} & {row["checkpoint_chain_head_sha256"] for row in reused}:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "New execution reused a historical session or checkpoint"}])
    cells: dict[tuple[str, str, str], list[bool]] = defaultdict(list)
    observed: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for record in records:
        slot = next(item for item in schedule if item["slot_id"] == record["slot_id"])
        cells[(str(slot["leaf_id"]), str(slot["state"]), str(slot["arm"]))].append(bool(record["correct"]))
        observed[(str(slot["leaf_id"]), str(slot["state"]), str(slot["arm"]))].append(str(record["verdict"]))
    for row in reused:
        key = ("scope.passage.status", str(row["state"]), "current_wording")
        cells[key].append(bool(row["correct"])); observed[key].append(str(row["verdict"]))
    per_cell = {"|".join(key): {"match": sum(values), "denominator": REPEATS, "passed": sum(values) == REPEATS, "observed_verdict_counts": dict(Counter(observed[key]))} for key, values in sorted(cells.items())}
    expected_cell_keys = {("scope.passage.status", state, arm) for state in ("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch") for arm in ("current_wording", "candidate_wording")} | {("modifier.genre.hybrid_or_genre_blend.tone", "localized_issue", "current_wording"), ("modifier.genre.hybrid_or_genre_blend.tone", "missing_required_evidence", "current_wording"), ("op.critique.single_unit_critique.no_whole_claims", "missing_required_evidence", "current_wording")}
    if set(cells) != expected_cell_keys or any(len(value) != REPEATS for value in cells.values()):
        return _incomplete(root, len(records), [{"slot_id": "cells", "reason": "Treatment cell geometry drifted"}])
    baseline_keys = [("scope.passage.status", state, "current_wording") for state in ("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch")]
    candidate_keys = [("scope.passage.status", state, "candidate_wording") for state in ("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch")]
    control_keys = [("modifier.genre.hybrid_or_genre_blend.tone", "localized_issue", "current_wording"), ("modifier.genre.hybrid_or_genre_blend.tone", "missing_required_evidence", "current_wording"), ("op.critique.single_unit_critique.no_whole_claims", "missing_required_evidence", "current_wording")]
    passed = {key: sum(cells[key]) == REPEATS for key in cells}
    candidate_all = all(passed[key] for key in candidate_keys)
    controls_all = all(passed[key] for key in control_keys)
    no_regression = all(passed[candidate] for baseline, candidate in zip(baseline_keys, candidate_keys, strict=True) if passed[baseline])
    improvements = [baseline for baseline, candidate in zip(baseline_keys, candidate_keys, strict=True) if not passed[baseline] and passed[candidate]]
    if candidate_all and controls_all and no_regression and improvements:
        decision = "GO_TREATMENT"
    elif candidate_all and controls_all and no_regression:
        decision = "NO_EFFECT"
    else:
        decision = "DIAGNOSTIC_FAIL"
    sections = {"baseline_four_passage_cells": {"passed": sum(passed[key] for key in baseline_keys), "total": 4, "cells": ["|".join(key) for key in baseline_keys]}, "candidate_four_passage_cells": {"passed": sum(passed[key] for key in candidate_keys), "total": 4, "cells": ["|".join(key) for key in candidate_keys]}, "corrected_nonpassage_controls": {"passed": sum(passed[key] for key in control_keys), "total": 3, "cells": ["|".join(key) for key in control_keys]}, "improved_baseline_failures": ["|".join(key) for key in improvements], "no_regression_of_baseline_passes": no_regression}
    settlement = {"study_id": STUDY_ID, "decision": decision, "completed_new_slots": NEW_SLOTS, "reused_immutable_predecessor_calls": reused, "per_cell_three_of_three": per_cell, "treatment_gate": sections, "promotion": "none_pending_independent_review_and_sealed_holdout" if decision == "GO_TREATMENT" else "none", "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_new_slots": NEW_SLOTS, "reused_accepted_calls": REUSED_SLOTS, "cells": sections, "material_failure_baseline_actual": {"expected": "NO", "observed": per_cell["scope.passage.status|material_failure|current_wording"]["observed_verdict_counts"]}, "activation_mismatch_baseline_actual": {"expected": "NOT_APPLICABLE", "observed": per_cell["scope.passage.status|activation_mismatch|current_wording"]["observed_verdict_counts"]}, "promotion": "none"}
    _write_summary(root / "settlement.json", settlement); _write_summary(root / "public-aggregate.json", public); return settlement


def main() -> None:
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest="command", required=True); commands.add_parser("verify")
    for name in ("prepare", "dry-run", "execute"):
        child = commands.add_parser(name); child.add_argument("--private-root", required=True, type=Path)
        if name == "execute":
            child.add_argument("--resume", action="store_true"); child.add_argument("--allow-remote", action="store_true"); child.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    settle_parser = commands.add_parser("settle"); settle_parser.add_argument("--private-root", required=True, type=Path); settle_parser.add_argument("--predecessor-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "verify": result = validate_package()
    elif args.command == "prepare": result = prepare(args.private_root)
    elif args.command == "dry-run": result = dry_run(args.private_root)
    elif args.command == "execute": result = execute(args.private_root, resume=args.resume, allow_remote=args.allow_remote, acknowledged_zero_incremental_charge=args.acknowledge_zero_incremental_charge)
    else: result = settle(args.private_root, args.predecessor_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
