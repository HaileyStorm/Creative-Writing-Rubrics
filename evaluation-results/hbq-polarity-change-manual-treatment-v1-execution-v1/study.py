"""Frozen, resumable direct execution for the P1 manual prompt treatment."""
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

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-polarity-change-manual-treatment-v1"
STUDY_ID = "hbq-polarity-change-manual-treatment-v1-execution-v1"
PREDECESSOR_COMMIT = "6366bb3"
PREDECESSOR_TREE = "1043f5196960e3e1fae15ddb4b53b1c2c3a3ba7e"
PREDECESSOR_FILES = {
    "README.md": "e74c58cf7595442d8fe7818288029d7863ff2088",
    "fixture-carriers.json": "6e57b6e81012ce0e0eec22c49430a2c94e8714f1",
    "public-synthetic-corpus.json": "a9feaa012f35d5a3f1d513e05cff60232bef45f0",
    "run.py": "38f38d8fa2f68d44a4563b4bf74af242487d7bfc",
    "sealed-holdout-contract.json": "2761fce81b7e74cb6f049079e8785f4cbada4ec7",
    "study-contract.json": "a0b7cdb7e2b40b844fca4ea94585391cbbc3003d",
    "study.py": "a2b061d2b38a43c02318e3f45441fb34490e93df",
}
VERDICTS = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})
REPETITIONS, SLOTS = 3, 57
BUNDLE_ID = "p1-manual-treatment-development"
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json",
    "bundles/all_bundles.json", "registry/question_index.jsonl", "src/hbqrs/runner.py", "src/hbqrs/cli.py",
)
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_prompt_bytes(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""):
        raise ValueError("Prompt contains a lone CR byte")
    return value.replace(b"\r\n", b"\n")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git binding lookup failed")
    return result.stdout.strip()


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


def _write_summary(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("p1_manual_treatment_predecessor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load frozen P1 manual-treatment predecessor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_package() -> dict[str, Any]:
    value = contract()
    expected_execution = {
        "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1,
        "batch_attempts": 3, "maximum_provider_sends": 171, "one_leaf_per_call": True, "attempt_lifecycle_policy": "terminal_sidecar_v1",
        "collision_resistant_judge_ids": True, "owner_attested_zero_incremental_charge_only": True,
        "paid_api_or_fallback_route": "forbidden",
    }
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1 or value.get("status") != "frozen_execution_successor_unexecuted":
        raise ValueError("Execution contract identity drifted")
    if value.get("predecessor") != {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": PREDECESSOR_FILES}:
        raise ValueError("Predecessor contract binding drifted")
    if value.get("execution") != expected_execution or value.get("geometry") != {"leaves": 11, "fixtures": 19, "repeats": 3, "slots": SLOTS}:
        raise ValueError("Execution geometry or route binding drifted")
    if value.get("prompt_commitment") != "canonical_utf8_lf_private_overlay_v1" or value.get("public_result_policy") != "aggregate_only_after_execution" or value.get("holdout") != "sealed_unopened_until_development_settlement" or value.get("promotion") != "none":
        raise ValueError("Execution contract surface drifted")
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-polarity-change-manual-treatment-v1") != PREDECESSOR_TREE:
        raise ValueError("Predecessor tree is unavailable")
    for path, blob in PREDECESSOR_FILES.items():
        target = f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-polarity-change-manual-treatment-v1/{path}"
        if _git("rev-parse", target) != blob or _git("hash-object", str(PREDECESSOR_ROOT / path)) != blob:
            raise ValueError("Current manual-treatment predecessor bytes differ from their pinned committed source")
    predecessor = _predecessor()
    predecessor.verify_package()
    if len(predecessor.LEAVES) != 11 or len(predecessor.plan_slots()) != SLOTS:
        raise ValueError("P1 manual-treatment predecessor geometry drifted")
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "predecessor": PREDECESSOR_COMMIT}


def _runtime_bindings() -> dict[str, Any]:
    return {"cwr_files": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}, "successor_files": {path: sha256_file(ROOT / path) for path in SUCCESSOR_FILES}}


def build_schedule() -> list[dict[str, Any]]:
    validate_package()
    predecessor = _predecessor()
    corpus = predecessor.load_corpus()
    predecessor.verify_corpus(corpus)
    fixtures = {str(item["case_id"]): dict(item) for item in corpus["fixtures"]}
    carriers = predecessor.load_carriers()["carriers"]
    rows: list[dict[str, Any]] = []
    case_ordinals = {str(fixture["case_id"]): index for index, fixture in enumerate(corpus["fixtures"], start=1)}
    for source in predecessor.plan_slots():
        fixture = fixtures[str(source["case_id"])]
        case_id = str(source["case_id"])
        ordinal = case_ordinals[case_id]
        fixture_hash = sha256_bytes(canonical_json(fixture))
        row = {**dict(source), "artifact_id": f"p1mt-a{ordinal:02d}-{fixture_hash[:16]}", "slot_id": f"p1mt-s{ordinal:02d}-r{source['repeat']}", "artifact_text": fixture["text"], "artifact_kind": fixture["artifact_kind"], "carrier": dict(carriers[case_id]), "artifact_sha256": sha256_bytes(str(fixture["text"]).encode("utf-8"))}
        row["judge_id"] = f"p1mt-j-{sha256_bytes(canonical_json({'slot': row['slot_id'], 'artifact': row['artifact_id'], 'leaf': row['leaf_id']}))[:24]}"
        rows.append(row)
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS:
        raise ValueError("Exact 57-slot schedule drifted")
    return rows


def _private_bundle() -> dict[str, Any]:
    predecessor = _predecessor()
    records = predecessor.source_leaf_records()
    modules = list(dict.fromkeys(records[leaf]["module_id"] for leaf in predecessor.LEAVES))
    return {
        "$schema": "../schema/hbq_bundle.schema.json", "standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1, "task_contract_domain_id": "p1mt-01",
        "title": "P1 manual-treatment diagnostic", "description": "Frozen singleton P1 manual-treatment execution bundle.", "artifact_types": ["synthetic_diagnostic"], "valid_scopes": ["excerpt", "passage", "scene", "work"], "profile": {}, "module_ids": modules,
        "domains": [{"domain_id": f"p1mt-{index:02d}", "title": leaf, "points": 1.0, "components": [{"module_id": records[leaf]["module_id"], "weight": 1.0, "include_question_ids": [leaf]}], "score_mode": "weighted_binary_mean"} for index, leaf in enumerate(predecessor.LEAVES, start=1)],
        "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": False, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
        "excerpt_and_incomplete_policy": {"flagged_excerpt": "Evaluate only declared synthetic evidence.", "unflagged_incomplete": "Do not infer missing material.", "visible_local_defects": "Evaluate supplied synthetic text only."},
        "judge_policy": {"artifact_assumed_ai_generated": True, "strict_but_fair": True, "no_glazing": True, "judge_execution_not_intent": True, "do_not_invent_defects": True, "avoid_length_and_ornament_bias": True, "brief_evidence_required": True, "private_chain_of_thought_not_requested": True, "verdict_states": sorted(VERDICTS), "pairwise_finalists": False}, "notes": [],
    }


def _task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    carrier = slot["carrier"]
    return {"contract_version": 1, "contract_id": f"p1mt-c-{sha256_bytes(str(slot['artifact_id']).encode('utf-8'))[:20]}", "artifact_id": slot["artifact_id"], "context": {"artifact_kind": slot["artifact_kind"], "declared_scope": carrier["declared_scope"], "completion_status": carrier["completion_status"], "background": ["Public synthetic development screen for manual prompt treatment."], "constraints": [f"relevant_evidence={carrier['relevant_evidence']}"], "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "p1mt-execution-v1-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen P1 manual-treatment singleton diagnostic bundle."}


def _overlay_files() -> dict[str, bytes]:
    predecessor = _predecessor()
    binary = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes()
    return {
        "prompts/judge/JUDGE_PREFIX.md": (REPOSITORY / "prompts/judge/JUDGE_PREFIX.md").read_bytes(),
        "prompts/judge/BINARY_EVALUATION_PROMPT.md": canonical_prompt_bytes(binary).rstrip(b"\n") + b"\n\n" + predecessor.TREATMENT_APPENDIX.encode("utf-8") + b"\n",
        "schema/hbq_judge_response.schema.json": (REPOSITORY / "schema/hbq_judge_response.schema.json").read_bytes(),
        "schema/hbq_task_contract.schema.json": (REPOSITORY / "schema/hbq_task_contract.schema.json").read_bytes(),
        "schema/hbq_verdict.schema.json": (REPOSITORY / "schema/hbq_verdict.schema.json").read_bytes(),
        "schema/hbq_diagnostic_report.schema.json": (REPOSITORY / "schema/hbq_diagnostic_report.schema.json").read_bytes(),
        "registry/all_modules.json": (REPOSITORY / "registry/all_modules.json").read_bytes(),
    }


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "artifact_id", "leaf_id", "repeat", "artifact_sha256")}


def _remote_disclosure() -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "destination": "Codex CLI -> authenticated OpenAI service", "material": "public synthetic fixtures and public prompt treatment only", "planned_slots": SLOTS, "paid_route": "forbidden", "holdout": "not present"}


def prepare(private_root: str | Path) -> dict[str, Any]:
    root = _external_root(private_root)
    schedule = build_schedule()
    for slot in schedule:
        _write_or_verify(root / "inputs" / f"{slot['artifact_id']}.txt", str(slot["artifact_text"]).encode("utf-8"))
        task = _task_contract(slot)
        _write_or_verify(root / "task-contracts" / f"{slot['artifact_id']}.json", canonical_json(task))
        _write_or_verify(root / "scope-overrides" / f"{slot['artifact_id']}.json", canonical_json(_scope_override(slot, task)))
    _write_or_verify(root / "runtime-p1mt-bundle.json", canonical_json([_private_bundle()]))
    for relative, value in _overlay_files().items():
        _write_or_verify(root / "runtime-book" / relative, value)
    disclosure = _remote_disclosure()
    _write_or_verify(root / "remote-disclosure.json", canonical_json(disclosure))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "private_overlay_sha256": {path: sha256_bytes(value) for path, value in _overlay_files().items()}, "remote_disclosure_sha256": sha256_bytes(canonical_json(disclosure)), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": schedule}))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def environment_for(private_root: str | Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["HBQRS_ROOT"] = str(_external_root(private_root) / "runtime-book")
    return environment


def _judge_id(slot: Mapping[str, Any]) -> str:
    return str(slot["judge_id"])


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, resume: bool = False) -> list[str]:
    root = _external_root(private_root)
    command = [sys.executable, "-m", "hbqrs", "--registry", str(REPOSITORY / "registry/all_modules.json"), "--bundles", str(root / "runtime-p1mt-bundle.json"), "judge", str(root / "inputs" / f"{slot['artifact_id']}.txt"), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai", "--batch-size", "1", "--batch-attempts", "3", "--attempt-lifecycle-policy", "terminal_sidecar_v1", "--artifact-id", slot["artifact_id"], "--judge-id", _judge_id(slot), "--task-contract", str(root / "task-contracts" / f"{slot['artifact_id']}.json"), "--scope-compatibility-override", str(root / "scope-overrides" / f"{slot['artifact_id']}.json"), "--question-id", slot["leaf_id"], "--output-dir", str(root / "runs" / slot["slot_id"])]
    if resume:
        command.append("--resume")
    return command


def _render_command(slot: Mapping[str, Any], root: Path, output: Path) -> list[str]:
    return [sys.executable, "-m", "hbqrs", "--registry", str(REPOSITORY / "registry/all_modules.json"), "--bundles", str(root / "runtime-p1mt-bundle.json"), "render-judge", "--bundle", BUNDLE_ID, "--artifact", str(root / "inputs" / f"{slot['artifact_id']}.txt"), "--artifact-id", slot["artifact_id"], "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--task-contract", str(root / "task-contracts" / f"{slot['artifact_id']}.json"), "--scope-compatibility-override", str(root / "scope-overrides" / f"{slot['artifact_id']}.json"), "--question-id", slot["leaf_id"], "--output", str(output)]


def _runtime_schedule(root: Path, schedule: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    rubric_sha = sha256_file(REPOSITORY / "registry/all_modules.json")
    for slot in schedule:
        prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        raw = prompt_path.read_bytes()
        canonical = canonical_prompt_bytes(raw)
        if raw != canonical:
            raise ValueError("Frozen rendered prompt is not canonical UTF-8 LF bytes")
        result = dict(slot)
        result["rendered_prompt_sha256"] = sha256_bytes(raw)
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": slot["leaf_id"], "judge_id": _judge_id(slot), "prompt_sha256": sha256_bytes(canonical), "canonical_prompt_sha256": sha256_bytes(canonical), "rubric_sha256": rubric_sha}
        result["condition"] = condition
        result["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=str(result["artifact_id"]), artifact_sha256=str(result["artifact_sha256"]), condition=condition, repetition=int(result["repeat"]), rubric_revision="1.2.0")
        resolved.append(result)
    return resolved


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    result = prepare(private_root)
    root = _external_root(private_root)
    environment = environment_for(root)
    for slot in build_schedule():
        command = [*command_for(slot, root, resume=(root / "runs" / slot["slot_id"] / "run.json").is_file()), "--dry-run"]
        completed = runner_call(command, text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(completed, "returncode", 1):
            raise RuntimeError(f"CWR dry run stopped at {slot['slot_id']}")
        prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        completed = runner_call(_render_command(slot, root, prompt_path), text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(completed, "returncode", 1) or not prompt_path.is_file():
            raise RuntimeError(f"CWR prompt render stopped at {slot['slot_id']}")
        prompt_path.write_bytes(canonical_prompt_bytes(prompt_path.read_bytes()))
    schedule = _runtime_schedule(root, build_schedule())
    hashes = {slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in schedule}
    preview = {"mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS, "first_command": command_for(schedule[0], root), "last_command": command_for(schedule[-1], root), "rendered_prompt_sha256s": hashes, "rendered_prompt_aggregate_sha256": sha256_bytes(canonical_json(hashes))}
    _write_summary(root / "runtime-schedule.json", {"format_version": 1, "slots": schedule, "rendered_prompt_aggregate_sha256": preview["rendered_prompt_aggregate_sha256"]})
    _write_summary(root / "dry-run.json", preview)
    _assert_no_provider_metadata_leakage(root, schedule)
    return {**result, **preview}


def _assert_no_provider_metadata_leakage(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    for slot in schedule:
        task = _task_contract(slot)
        provider_fields = canonical_json({"artifact_id": slot["artifact_id"], "judge_id": _judge_id(slot), "contract_id": task["contract_id"]}).decode("utf-8")
        prompt = (root / "rendered-prompts" / f"{slot['slot_id']}.txt").read_text(encoding="utf-8")
        forbidden = (str(slot["case_id"]), "expected_verdict", "sealed-holdout", "oracle")
        if any(token in provider_fields or token in prompt for token in forbidden):
            raise ValueError("Provider-facing prompt or metadata leaked a case, expected label, or private control token")


def _validate_runtime_bindings(root: Path) -> list[dict[str, Any]]:
    validate_package()
    manifest = _load_json(root / "study-manifest.json")
    if manifest.get("runtime_bindings") != _runtime_bindings() or manifest.get("private_overlay_sha256") != {path: sha256_bytes(value) for path, value in _overlay_files().items()} or manifest.get("remote_disclosure_sha256") != sha256_bytes(canonical_json(_remote_disclosure())):
        raise ValueError("CWR runtime or overlay binding drifted; prepare again")
    if (root / "remote-disclosure.json").read_bytes() != canonical_json(_remote_disclosure()):
        raise ValueError("Frozen remote disclosure drifted")
    for relative, expected in _overlay_files().items():
        if (root / "runtime-book" / relative).read_bytes() != expected:
            raise ValueError("Frozen private prompt overlay drifted")
    if (root / "runtime-p1mt-bundle.json").read_bytes() != canonical_json([_private_bundle()]):
        raise ValueError("Frozen private diagnostic bundle drifted")
    stored = _load_json(root / "runtime-schedule.json")
    expected = _runtime_schedule(root, build_schedule())
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected}))
    if stored.get("slots") != expected or stored.get("rendered_prompt_aggregate_sha256") != aggregate:
        raise ValueError("Prepared prompt schedule drifted; dry run again")
    return expected


def _fresh_execute_preflight(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    if not (root / "remote-disclosure.json").is_file() or (root / "remote-disclosure.json").read_bytes() != canonical_json(_remote_disclosure()):
        raise ValueError("Fresh execute requires the exact prepared remote disclosure")
    for slot in schedule:
        run_dir = root / "runs" / str(slot["slot_id"])
        if not (run_dir / "run.json").is_file():
            raise ValueError("Fresh execute requires a complete dry-run manifest for every slot")
        responses = run_dir / "responses"
        if responses.is_dir() and any(path.is_file() for path in responses.rglob("*")):
            raise ValueError("Fresh execute rejects a slot with prior provider attempts; use --resume")


def execute(private_root: str | Path, *, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    root = _external_root(private_root)
    schedule = _validate_runtime_bindings(root)
    if not resume:
        _fresh_execute_preflight(root, schedule)
    environment = environment_for(root)
    for slot in schedule:
        completed = runner_call([*command_for(slot, root, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(completed, "returncode", 1):
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}")
    return {"mode": "resume" if resume else "execute", "inspected_slots": SLOTS, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "billing": "owner_attested_subscription_zero_incremental_charge"}


def _input_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "name": path.name, "bytes": len(data), "sha256": sha256_bytes(data)}


def _verify_checkpoint_prompt(run_dir: Path, prompt_path: Path) -> dict[str, str]:
    checkpoint = run_dir / "responses" / "batch-0001.prompt.txt.gz"
    try:
        checkpoint_bytes = gzip.decompress(checkpoint.read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt is unavailable or malformed") from exc
    rendered = prompt_path.read_bytes()
    if rendered != canonical_prompt_bytes(rendered):
        raise ValueError("Frozen rendered prompt is not canonical UTF-8 LF bytes")
    if canonical_prompt_bytes(checkpoint_bytes) != rendered:
        raise ValueError("Checkpoint prompt differs from frozen rendered prompt beyond line endings")
    return {"checkpoint_prompt_sha256": sha256_bytes(checkpoint_bytes), "rendered_prompt_sha256": sha256_bytes(rendered), "canonical_prompt_sha256": sha256_bytes(rendered)}


def _validate_production_evidence(evidence: Any, *, artifact_text: str, question_id: str) -> None:
    if not isinstance(evidence, list):
        raise ValueError("Production normalized evidence is unavailable")
    runner._validate_typed_checkpoint_evidence(evidence, question_id=question_id)
    runner._validate_exact_quotes(evidence, artifact_text=artifact_text, context_texts=[], question_id=question_id)


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run_dir = root / "runs" / str(slot["slot_id"])
    manifest = _load_json(run_dir / "run.json")
    config = manifest.get("configuration")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "artifact_id": slot["artifact_id"], "judge_id": _judge_id(slot), "bundle_id": BUNDLE_ID, "question_ids": [slot["leaf_id"]]}
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping) or any(config.get(key) != value for key, value in expected.items()) or config.get("attempt_lifecycle_policy") != "terminal_sidecar_v1":
        raise ValueError("Production singleton run binding drifted")
    artifact_path = root / "inputs" / f"{slot['artifact_id']}.txt"
    task_contract_path = root / "task-contracts" / f"{slot['artifact_id']}.json"
    override_path = root / "scope-overrides" / f"{slot['artifact_id']}.json"
    expected_scope = {"mode": "reviewed_override", "path": str(override_path.resolve()), "name": override_path.name, "bytes": len(override_path.read_bytes()), "sha256": sha256_file(override_path), "format_version": 1, "decision_id": "p1mt-execution-v1-scope-compatibility", "reviewer": "hbqrs-reviewed-v1"}
    if config.get("artifact") != _input_record(artifact_path) or config.get("contexts") != [] or config.get("task_contract") != {**_input_record(task_contract_path), "contract_id": _task_contract(slot)["contract_id"]} or config.get("scope_compatibility") != expected_scope:
        raise ValueError("Production artifact, carrier, or task-contract binding drifted")
    if manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Run manifest configuration hash drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run_dir, config_sha256=str(manifest["config_sha256"]), batch_attempts=3, reconstruct=False, strict_v5=True, require_durable=True)
    prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    commitments = _verify_checkpoint_prompt(run_dir, prompt)
    if commitments["canonical_prompt_sha256"] != slot["condition"]["canonical_prompt_sha256"]:
        raise ValueError("Checkpoint prompt canonical hash differs from prepared schedule")
    overlay = root / "runtime-book"
    expected_prompt_hashes = [sha256_file(overlay / "prompts" / "judge" / name) for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")]
    actual_prompt_hashes = [item.get("sha256") for item in config.get("prompts", [])] if isinstance(config.get("prompts"), list) else []
    if actual_prompt_hashes != expected_prompt_hashes or config.get("response_schema", {}).get("sha256") != sha256_file(overlay / "schema" / "hbq_judge_response.schema.json"):
        raise ValueError("Manual prompt overlay or response schema binding drifted")
    verdicts, checkpoints, chain = runner._load_checkpoints(run_dir, artifact_text=str(slot["artifact_text"]), context_texts=[], batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]:
        raise ValueError("Run does not contain exactly one accepted selected leaf")
    verdict_run_id = verdicts[0].get("run_id")
    if not isinstance(verdict_run_id, str) or not verdict_run_id.strip() or verdict_run_id != manifest.get("run_id"):
        raise ValueError("Accepted verdict run identity differs from the run manifest")
    _validate_production_evidence(verdicts[0].get("evidence"), artifact_text=str(slot["artifact_text"]), question_id=str(slot["leaf_id"]))
    checkpoint = _load_json(run_dir / "responses" / "batch-0001.json")
    reported = checkpoint.get("provider", {}).get("reported", {})
    if not isinstance(reported, Mapping) or {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider/model/reasoning report drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session:
        raise ValueError("Provider session identity missing")
    if checkpoint.get("accepted_attempt") != len(runner._rejected_records(run_dir, 1)) + 1:
        raise ValueError("Retry did not replace one logical slot cumulatively")
    return {"slot_id": slot["slot_id"], "verdict": verdicts[0].get("verdict"), "expected": slot["expected_verdict"], "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "evidence": verdicts[0]["evidence"], "run_id": verdict_run_id, "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "prompt_commitment": commitments}


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    value = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": SLOTS, "failures": failures}
    _write_summary(root / "settlement.json", value)
    _write_summary(root / "public-aggregate.json", {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS})
    return value


def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    root = _external_root(private_root)
    try:
        schedule = _validate_runtime_bindings(root)
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "schedule", "reason": str(exc)}])
    records, failures = [], []
    for slot in schedule:
        try:
            record = verifier(root, slot)
            if record.get("slot_id") != slot["slot_id"] or record.get("verdict") not in VERDICTS:
                raise ValueError("Verifier slot identity or four-state verdict malformed")
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != SLOTS or len({row["slot_id"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), failures or [{"slot_id": "identity", "reason": "Duplicate logical slot"}])
    if len({row["run_id"] for row in records}) != SLOTS or len({row["session_id_sha256"] for row in records}) != SLOTS or len({row["checkpoint_chain_head_sha256"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Run, session, or checkpoint identity repeated"}])
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    state_counts: dict[str, Counter[str]] = {leaf: Counter() for leaf in _predecessor().LEAVES}
    slot_map = {slot["slot_id"]: slot for slot in schedule}
    for record in records:
        slot = slot_map[record["slot_id"]]
        cells[(str(slot["case_id"]), str(slot["leaf_id"]))].append(bool(record["correct"]))
        state_counts[str(slot["leaf_id"])][str(record["verdict"])] += 1
    states = {key: next(slot["expected_verdict"] for slot in schedule if (slot["case_id"], slot["leaf_id"]) == key) for key in cells}
    per_cell = {f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": states[key]} for index, (key, values) in enumerate(cells.items(), start=1)}
    decision = "MANUAL_TREATMENT_PASS" if len(per_cell) == 19 and all(value["passed"] for value in per_cell.values()) else "DIAGNOSTIC_FAIL"
    accuracy = {state: {"correct": sum(bool(row["correct"]) for row in records if row["expected"] == state), "denominator": sum(row["expected"] == state for row in records)} for state in sorted(VERDICTS)}
    counts = {leaf: {state: state_counts[leaf][state] for state in sorted(VERDICTS)} for leaf in state_counts}
    settlement = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "per_cell_three_of_three": per_cell, "canonical_four_state_counts": counts, "accuracy": accuracy, "promotion": "none", "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "cells": {"passed": sum(value["passed"] for value in per_cell.values()), "total": len(per_cell)}, "canonical_four_state_counts": counts, "accuracy": accuracy, "promotion": "none"}
    _write_summary(root / "settlement.json", settlement)
    _write_summary(root / "public-aggregate.json", public)
    return settlement


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    for name in ("prepare", "settle"):
        child = commands.add_parser(name)
        child.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    result = validate_package() if args.command == "verify" else prepare(args.private_root) if args.command == "prepare" else settle(args.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
