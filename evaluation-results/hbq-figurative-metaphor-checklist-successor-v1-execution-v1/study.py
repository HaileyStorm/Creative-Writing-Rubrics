"""Exact, one-attempt Phase A executor for the figurative checklist successor."""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from functools import cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ID = "hbq-figurative-metaphor-checklist-successor-v1"
PREDECESSOR_COMMIT = "a02418f"
PREDECESSOR_TREE = "9ca4cc8fc859a41467b575e5cfb8b96593df57c7"
PREDECESSOR_FILES = {
    "README.md": "f2471ada406e4fc1c40d020fbb9334578224b9ff",
    "expected-verdict-ledger.json": "0b2ab72897039f309fb1f6ed56a32791ffaf3e50",
    "public-synthetic-corpus.json": "b0bf722785b9624a3fedd5b97905a4b303e43231",
    "real-holdout-commitment.json": "c5e432ef80bf4ff45471fb8205db081fa83f57cc",
    "run.py": "a69eb0bc0657d5341618b078baa2980a1941422a",
    "study-contract.json": "86845a5c5392d7c38070c4d6a0e92c82846f2361",
    "study.py": "f0d92426008673d0e4b3f774af45bcf2c9d4bd51",
}
STUDY_ID = "hbq-figurative-metaphor-checklist-successor-v1-execution-v1"
PRIVATE_EXECUTION_DIRECTORY = "phase-a-execution-v1"
TARGET = "penalty.purple_prose.metaphor"
CONTROLS = ("core.freshness_and_non_genericness.no_default_metaphors", "penalty.purple_prose.proportion")
LEAVES, REPEATS, SLOTS = (TARGET, *CONTROLS), (1, 2, 3), 72
BUNDLE_ID = "figurative-metaphor-checklist-successor-phase-a"
ATTEMPT_LIFECYCLE_POLICY = "terminal_sidecar_v1"
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json",
    "registry/question_index.jsonl", "registry/criterion_ownership.json",
    "src/hbqrs/runner.py", "src/hbqrs/cli.py",
)
SUCCESSOR_FILES = ("README.md", "study.py", "run.py", "study-contract.json")


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
    done = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.strip() or "git binding lookup failed")
    return done.stdout.strip()


def _git_bytes(path: str) -> bytes:
    done = subprocess.run(["git", "show", path], cwd=REPOSITORY, capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.decode("utf-8", "replace").strip() or "frozen source unavailable")
    return done.stdout


def _frozen_json(name: str) -> dict[str, Any]:
    value = json.loads(_git_bytes(f"{PREDECESSOR_COMMIT}:evaluation-results/{PREDECESSOR_ID}/{name}").decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Frozen {name} is not an object")
    return value


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _external_root(value: str | Path) -> Path:
    root, repository = Path(value).resolve(), REPOSITORY.resolve()
    try:
        root.relative_to(repository)
    except ValueError:
        pass
    else:
        raise ValueError("private_root must be outside the CWR checkout")
    try:
        repository.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("private_root must be disjoint from the CWR checkout")
    return root


def _root(value: str | Path) -> Path:
    return _external_root(value) / PRIVATE_EXECUTION_DIRECTORY


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
    if path.exists():
        raise ValueError(f"Refusing to replace terminal result: {path.name}")
    _write_or_verify(path, canonical_json(value))


def validate_package() -> dict[str, Any]:
    expected_execution = {
        "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_call": True,
        "batch_size": 1, "batch_attempts": 1, "physical_attempts_per_slot": 1,
        "retry_or_resume": "forbidden", "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY,
        "run_manifest_format_version": 5, "maximum_provider_sends": 72,
        "zero_incremental_charge_only": True, "paid_fallback": "forbidden",
    }
    expected_privacy = {
        "runtime_private_root": "explicit_external_disjoint_portable",
        "provider_input": "public_synthetic_fixture_text_current_production_prompt_one_leaf_and_declared_task_context_only",
        "excluded_from_provider": ["expected labels", "semantic construction", "reviewer rationale", "case labels", "Phase B checklist", "real holdout"],
        "result": "aggregate_only", "real_holdout": "closed",
    }
    expected_stops = {
        "controls": "24_of_24_each", "current_target_sufficient": "24_of_24_CURRENT_TARGET_SUFFICIENT",
        "mixed_target_cell": "CURRENT_TARGET_UNSTABLE_NO_GO",
        "phase_b_eligible": "at_least_2_all_wrong_stable_target_cells_with_distinct_wording_across_at_least_2_stockness_load_strata",
        "otherwise": "STABLE_MISS_EVIDENCE_INSUFFICIENT_NO_GO", "phase_b": "disabled_no_holdout_opened",
    }
    value = contract()
    predecessor = {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": PREDECESSOR_FILES}
    if value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("status") != "frozen_phase_a_executor_unexecuted" or value.get("predecessor") != predecessor:
        raise ValueError("Execution successor identity or predecessor binding drifted")
    if value.get("execution") != expected_execution or value.get("privacy") != expected_privacy or value.get("phase_a_stops") != expected_stops or value.get("promotion") != "none":
        raise ValueError("Execution, privacy, Phase A stop, or promotion contract drifted")
    if value.get("runtime_bindings") != {"freeze": "exact_runtime_and_successor_file_sha256s_before_dry_run_and_settlement", "prompt": "exact_checkpoint_equals_rendered_prompt_after_crlf_to_lf_only"}:
        raise ValueError("Runtime binding contract drifted")
    if value.get("phase_a") != {"fixtures": 8, "leaves": list(LEAVES), "repeats": 3, "slots": 72, "prompt": "current_production_prompt_only"}:
        raise ValueError("Phase A geometry drifted")
    prefix = f"{PREDECESSOR_COMMIT}:evaluation-results/{PREDECESSOR_ID}"
    if _git("rev-parse", prefix) != PREDECESSOR_TREE:
        raise ValueError("Frozen predecessor tree is unavailable")
    for name, blob in PREDECESSOR_FILES.items():
        if _git("rev-parse", f"{prefix}/{name}") != blob:
            raise ValueError(f"Frozen predecessor file drifted: {name}")
    if len(build_schedule()) != SLOTS:
        raise ValueError("Phase A schedule drifted")
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "phase_b_enabled": False, "real_holdout_opened": False}


@cache
def _leaf_records() -> dict[str, dict[str, Any]]:
    rows = {}
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item.get("id") in LEAVES:
            rows[item["id"]] = item
    if set(rows) != set(LEAVES):
        raise ValueError("Current production leaf records are unavailable")
    return rows


def build_schedule() -> list[dict[str, Any]]:
    corpus, ledger = _frozen_json("public-synthetic-corpus.json"), _frozen_json("expected-verdict-ledger.json")
    expected = ledger.get("expected_verdicts")
    if not isinstance(corpus.get("fixtures"), list) or len(corpus["fixtures"]) != 8 or not isinstance(expected, Mapping):
        raise ValueError("Frozen source geometry drifted")
    rows: list[dict[str, Any]] = []
    for fixture_index, fixture in enumerate(corpus["fixtures"], start=1):
        case_id, text, construction = fixture.get("case_id"), fixture.get("text"), fixture.get("semantic_construction")
        if not isinstance(case_id, str) or not isinstance(text, str) or not isinstance(construction, Mapping) or not isinstance(expected.get(case_id), Mapping):
            raise ValueError("Frozen fixture shape drifted")
        figures = construction.get("figures")
        probe = next((item for item in figures if isinstance(item, Mapping) and item.get("role") == "separate_probe"), None) if isinstance(figures, list) else None
        if not isinstance(probe, Mapping) or not isinstance(probe.get("source_domain"), str):
            raise ValueError("Frozen stockness/load strata drifted")
        artifact_id = f"fmcs-phase-a-artifact-{fixture_index:02d}"
        for leaf_id in LEAVES:
            verdict = expected[case_id].get(leaf_id)
            if verdict not in {"YES", "NO"}:
                raise ValueError("Frozen expected verdict drifted")
            for repeat in REPEATS:
                rows.append({
                    "slot_id": f"fmcs-phase-a-f{fixture_index:02d}-{leaf_id.rsplit('.', 1)[-1]}-r{repeat}",
                    "artifact_id": artifact_id, "case_id": case_id, "leaf_id": leaf_id, "repeat": repeat,
                    "artifact_text": text, "artifact_sha256": sha256_bytes(text.encode("utf-8")), "expected_verdict": verdict,
                    "stratum": {"stockness_probe": probe["source_domain"], "figurative_load": len(figures)},
                })
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS:
        raise ValueError("Exact 72-slot Phase A schedule drifted")
    return rows


def _bundle() -> list[dict[str, Any]]:
    records = _leaf_records()
    modules = list(dict.fromkeys(records[leaf]["module_id"] for leaf in LEAVES))
    return [{
        "standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1,
        "title": "Figurative checklist Phase A singleton diagnostic", "module_ids": modules,
        "task_contract_domain_id": "figurative-1",
        "domains": [{"domain_id": f"figurative-{index}", "title": leaf, "points": 1.0,
                     "components": [{"module_id": records[leaf]["module_id"], "weight": 1.0, "include_question_ids": [leaf]}],
                     "score_mode": "weighted_binary_mean"} for index, leaf in enumerate(LEAVES, start=1)],
        "penalty_modules": [],
        "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
    }]


def _task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"fmcs-phase-a-{slot['artifact_id']}", "artifact_id": slot["artifact_id"], "context": {"artifact_kind": "prose.short_story", "declared_scope": "complete supplied passage", "completion_status": "complete", "background": ["Public synthetic figurative-development screen."], "constraints": ["Use only supplied artifact."], "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "fmcs-phase-a-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen public synthetic Phase A diagnostic."}


def _paths(root: Path, slot: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    stem = str(slot["artifact_id"])
    return root / "inputs" / f"{stem}.txt", root / "contracts" / f"{stem}.json", root / "overrides" / f"{stem}.json"


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "artifact_id", "leaf_id", "repeat", "artifact_sha256", "stratum")}


def _runtime_bindings() -> dict[str, Any]:
    return {"cwr_head": _git("rev-parse", "HEAD"), "cwr_files": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}, "successor_files": {path: sha256_file(ROOT / path) for path in SUCCESSOR_FILES}}


def _manifest(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validate_package()
    root, schedule = _root(private_root), build_schedule()
    _write_or_verify(root / "catalog" / "registry.json", (REPOSITORY / "registry" / "all_modules.json").read_bytes())
    _write_or_verify(root / "catalog" / "bundles.json", canonical_json(_bundle()))
    for slot in schedule:
        artifact, task_path, override_path = _paths(root, slot)
        task = _task_contract(slot)
        _write_or_verify(artifact, str(slot["artifact_text"]).encode("utf-8"))
        _write_or_verify(task_path, canonical_json(task))
        _write_or_verify(override_path, canonical_json(_scope_override(slot, task)))
    _write_or_verify(root / "study-manifest.v1.json", canonical_json(_manifest(schedule)))
    _write_or_verify(root / "private-schedule.v1.json", canonical_json({"format_version": 1, "slots": schedule}))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, output_root: str = "runs", allow_remote: bool = False) -> list[str]:
    root = _root(private_root)
    artifact, task, override = _paths(root, slot)
    command = [
        sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "registry.json"),
        "--bundles", str(root / "catalog" / "bundles.json"), "judge", str(artifact),
        "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai",
        "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", ATTEMPT_LIFECYCLE_POLICY,
        "--artifact-id", str(slot["artifact_id"]), "--question-id", str(slot["leaf_id"]),
        "--task-contract", str(task), "--scope-compatibility-override", str(override),
        "--output-dir", str(root / output_root / str(slot["slot_id"])),
    ]
    if allow_remote:
        command.append("--allow-remote")
    return command


def _render_command(slot: Mapping[str, Any], root: Path, output: Path) -> list[str]:
    artifact, task, override = _paths(root, slot)
    return [
        sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "registry.json"),
        "--bundles", str(root / "catalog" / "bundles.json"), "render-judge", "--artifact", str(artifact),
        "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai",
        "--artifact-id", str(slot["artifact_id"]), "--question-id", str(slot["leaf_id"]),
        "--task-contract", str(task), "--scope-compatibility-override", str(override), "--output", str(output),
    ]


def _runtime_schedule(root: Path, schedule: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    resolved = []
    for source in schedule:
        prompt = root / "rendered-prompts" / f"{source['slot_id']}.txt"
        if not prompt.is_file():
            raise ValueError(f"Missing rendered prompt: {source['slot_id']}")
        raw = prompt.read_bytes()
        if raw != canonical_prompt_bytes(raw):
            raise ValueError("Rendered prompt is not canonical UTF-8 LF bytes")
        dry_manifest = _load_json(root / "dry-runs" / str(source["slot_id"]) / "run.json")
        dry_config = dry_manifest.get("configuration")
        compiled_bundle_sha256 = dry_config.get("compiled_bundle_sha256") if isinstance(dry_config, Mapping) else None
        if dry_manifest.get("format_version") != 5 or not isinstance(compiled_bundle_sha256, str) or len(compiled_bundle_sha256) != 64:
            raise ValueError("Dry-run manifest does not bind the compiled production bundle")
        slot = dict(source)
        condition = {
            "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True,
            "batch_size": 1, "batch_attempts": 1, "leaf_id": slot["leaf_id"],
            "prompt_sha256": sha256_bytes(raw), "registry_sha256": sha256_file(root / "catalog" / "registry.json"),
            "rubric_sha256": sha256_file(root / "catalog" / "registry.json"),
        }
        slot["condition"] = condition
        slot["compiled_bundle_sha256"] = compiled_bundle_sha256
        slot["rendered_prompt_sha256"] = condition["prompt_sha256"]
        slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=str(slot["artifact_id"]), artifact_sha256=str(slot["artifact_sha256"]), condition=condition, repetition=int(slot["repeat"]), rubric_revision="1.2.0")
        resolved.append(slot)
    return resolved


def _input_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "name": path.name, "bytes": len(data), "sha256": sha256_bytes(data)}


def _disclosure(schedule: Sequence[Mapping[str, Any]], root: Path) -> dict[str, Any]:
    slots = []
    for slot in schedule:
        artifact, task, override = _paths(root, slot)
        slots.append({"slot_id": slot["slot_id"], "artifact": _input_record(artifact), "task_contract_sha256": sha256_file(task), "scope_compatibility_sha256": sha256_file(override), "rendered_prompt_sha256": slot["rendered_prompt_sha256"]})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "preexecution_disclosure", "provider_calls": 0, "remote_destination": "Codex gpt-5.6-sol", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_call": True, "physical_attempts_per_slot": 1, "retry_or_resume": "forbidden", "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "zero_incremental_charge_only": True, "paid_fallback": "forbidden", "slots": slots}


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    prepared, root, schedule = prepare(private_root), _root(private_root), build_schedule()
    for slot in schedule:
        done = runner_call([*command_for(slot, private_root, output_root="dry-runs"), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"CWR dry run stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
        prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = runner_call(_render_command(slot, root, prompt_path), text=False, capture_output=True, check=False)
        if getattr(rendered, "returncode", 1):
            raise RuntimeError(f"CWR render stopped at {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        canonical_prompt = canonical_prompt_bytes(prompt_path.read_bytes())
        temporary = prompt_path.with_name(prompt_path.name + ".tmp")
        temporary.write_bytes(canonical_prompt)
        temporary.replace(prompt_path)
    runtime = _runtime_schedule(root, schedule)
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in runtime}))
    _write_or_verify(root / "runtime-schedule.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": runtime, "rendered_prompt_aggregate_sha256": aggregate}))
    _write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(_disclosure(runtime, root)))
    _write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "planned_slots": SLOTS, "phase_b_enabled": False, "real_holdout_opened": False, "rendered_prompt_aggregate_sha256": aggregate}))
    return {**prepared, "provider_calls": 0, "rendered_prompt_aggregate_sha256": aggregate, "rendered_prompts": SLOTS}


def _validated_runtime_schedule(private_root: str | Path) -> list[dict[str, Any]]:
    root = _root(private_root)
    validate_package()
    if _load_json(root / "study-manifest.v1.json") != _manifest(build_schedule()):
        raise ValueError("Prepared runtime/successor binding drifted; use a fresh dry run")
    expected = _runtime_schedule(root, build_schedule())
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected}))
    stored = _load_json(root / "runtime-schedule.v1.json")
    if stored != {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": expected, "rendered_prompt_aggregate_sha256": aggregate}:
        raise ValueError("Prepared current-production prompt schedule drifted; use a fresh dry run")
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != _disclosure(expected, root):
        raise ValueError("Exact preexecution disclosure drifted")
    return expected


def _zero_charge_receipt() -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "owner_zero_incremental_charge_acknowledgement", "route": "codex", "paid_fallback": "forbidden", "acknowledged": True, "maximum_provider_sends": SLOTS}


def execute(private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires --allow-remote and zero-incremental-charge acknowledgement")
    root, schedule = _root(private_root), _validated_runtime_schedule(private_root)
    terminal_paths = ("phase-a-settlement.v1.json", "public-aggregate.v1.json", "terminal-sidecar.v5.json")
    if any((root / name).exists() for name in terminal_paths):
        raise ValueError("Phase A execution is forbidden after any terminal settlement artifact")
    runs_root = root / "runs"
    if runs_root.exists() and any(runs_root.iterdir()):
        raise ValueError("One-attempt Phase A execution rejects pre-existing run directories; no retry or resume exists")
    for slot in schedule:
        run = root / "runs" / str(slot["slot_id"])
        if run.exists():
            raise ValueError("One-attempt Phase A execution rejects pre-existing run directories; no retry or resume exists")
    _write_or_verify(root / "receipts" / "zero-charge-acknowledgement.v1.json", canonical_json(_zero_charge_receipt()))
    for slot in schedule:
        done = runner_call(command_for(slot, private_root, allow_remote=True), text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}; do not retry or resume this successor")
    return {"mode": "execute", "executed_slots": SLOTS, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "billing": "owner_attested_zero_incremental_charge"}


def _verify_checkpoint_prompt(run: Path, prompt: Path) -> dict[str, str]:
    try:
        checkpoint = gzip.decompress((run / "responses" / "batch-0001.prompt.txt.gz").read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt is unavailable or malformed") from exc
    rendered = prompt.read_bytes()
    if rendered != canonical_prompt_bytes(rendered):
        raise ValueError("Prepared rendered prompt is not canonical UTF-8 LF bytes")
    if canonical_prompt_bytes(checkpoint) != rendered:
        raise ValueError("Checkpoint prompt differs from the exact rendered current-production prompt")
    return {"checkpoint_prompt_sha256": sha256_bytes(checkpoint), "rendered_prompt_sha256": sha256_bytes(rendered), "canonical_prompt_sha256": sha256_bytes(rendered)}


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"])
    manifest = _load_json(run / "run.json")
    config = manifest.get("configuration")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 1}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "question_ids": [slot["leaf_id"]]}
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping) or any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Production singleton run configuration drifted")
    if manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Run manifest configuration hash drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=1, reconstruct=False, strict_v5=True, require_durable=True)
    artifact, task, override = _paths(root, slot)
    prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    if config.get("compiled_bundle_sha256") != slot["compiled_bundle_sha256"] or config.get("artifact") != _input_record(artifact) or config.get("contexts") != []:
        raise ValueError("Compiled bundle, artifact, or context binding drifted")
    if config.get("task_contract", {}).get("sha256") != sha256_file(task) or config.get("scope_compatibility", {}).get("sha256") != sha256_file(override):
        raise ValueError("Task contract or scope override binding drifted")
    commitments = _verify_checkpoint_prompt(run, prompt)
    if commitments["canonical_prompt_sha256"] != slot["rendered_prompt_sha256"]:
        raise ValueError("Checkpoint prompt hash differs from the frozen runtime schedule")
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=str(slot["artifact_text"]), context_texts=[], batch_attempts=1, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]:
        raise ValueError("Run does not contain exactly one accepted selected leaf")
    checkpoint = _load_json(run / "responses" / "batch-0001.json")
    reported = checkpoint.get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider/model/reasoning receipt drifted")
    session, verdict_run = reported.get("session_id"), verdicts[0].get("run_id")
    if not isinstance(session, str) or not session.strip() or verdict_run != manifest.get("run_id"):
        raise ValueError("Provider response or accepted run identity drifted")
    evidence = verdicts[0].get("evidence")
    runner._validate_typed_checkpoint_evidence(evidence, question_id=str(slot["leaf_id"]))
    runner._validate_exact_quotes(evidence, artifact_text=str(slot["artifact_text"]), context_texts=[], question_id=str(slot["leaf_id"]))
    if runner._rejected_records(run, 1) or checkpoint.get("accepted_attempt") != 1:
        raise ValueError("One-attempt Phase A slot has a rejected or non-first attempt")
    return {"slot_id": slot["slot_id"], "verdict": verdicts[0].get("verdict"), "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "prompt_commitments": commitments}


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": SLOTS, "failures": failures, "phase_b_enabled": False, "real_holdout_opened": False, "promotion": "none"}
    _write_summary(root / "phase-a-settlement.v1.json", settlement)
    _write_summary(root / "public-aggregate.v1.json", {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS, "promotion": "none"})
    _write_terminal(root, settlement)
    return settlement


def _write_terminal(root: Path, settlement: Mapping[str, Any]) -> None:
    _write_summary(root / "terminal-sidecar.v5.json", {"format": "terminal_sidecar_v1", "format_version": 5, "study_id": STUDY_ID, "decision": settlement["decision"], "completed_slots": settlement["completed_slots"], "planned_slots": SLOTS, "settlement_sha256": sha256_file(root / "phase-a-settlement.v1.json"), "phase_b_enabled": False, "real_holdout_opened": False, "promotion": "none"})


def settle(private_root: str | Path) -> dict[str, Any]:
    root = _root(private_root)
    try:
        schedule = _validated_runtime_schedule(private_root)
        if _load_json(root / "receipts" / "zero-charge-acknowledgement.v1.json") != _zero_charge_receipt():
            raise ValueError("Zero-charge acknowledgement is unavailable or drifted")
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "runtime", "reason": str(exc)}])
    records, failures = [], []
    for slot in schedule:
        try:
            records.append(_verify_slot(root, slot))
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != SLOTS or len({record["slot_id"] for record in records}) != SLOTS:
        return _incomplete(root, len(records), failures or [{"slot_id": "identity", "reason": "Duplicate slot receipt"}])
    if len({record["session_id_sha256"] for record in records}) != SLOTS or len({record["checkpoint_chain_head_sha256"] for record in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Repeated provider-session or checkpoint-chain receipt"}])
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    by_slot = {record["slot_id"]: record for record in records}
    for slot in schedule:
        cells[(str(slot["artifact_id"]), str(slot["leaf_id"]))].append(bool(by_slot[slot["slot_id"]]["correct"]))
    if len(cells) != 24 or any(len(values) != 3 for values in cells.values()):
        return _incomplete(root, len(records), [{"slot_id": "geometry", "reason": "Expected 24 three-repeat Phase A cells"}])
    controls = {leaf: sum(sum(cells[(str(slot["artifact_id"]), leaf)]) for slot in schedule if slot["leaf_id"] == leaf and slot["repeat"] == 1) for leaf in CONTROLS}
    target_cells = {artifact: cells[(artifact, TARGET)] for artifact in {str(slot["artifact_id"]) for slot in schedule}}
    target_correct = sum(sum(values) for values in target_cells.values())
    mixed = [artifact for artifact, values in target_cells.items() if any(values) and not all(values)]
    misses = [artifact for artifact, values in target_cells.items() if not any(values)]
    target_slots = {str(slot["artifact_id"]): slot for slot in schedule if slot["leaf_id"] == TARGET}
    wording, strata = {target_slots[item]["artifact_sha256"] for item in misses}, {canonical_json(target_slots[item]["stratum"]) for item in misses}
    if any(value != 24 for value in controls.values()):
        decision = "FIXTURE_OR_OWNERSHIP_INVALID_NO_GO"
    elif target_correct == 24:
        decision = "CURRENT_TARGET_SUFFICIENT"
    elif mixed:
        decision = "CURRENT_TARGET_UNSTABLE_NO_GO"
    elif len(misses) >= 2 and len(wording) >= 2 and len(strata) >= 2:
        decision = "PHASE_B_ELIGIBLE_BUT_DISABLED"
    else:
        decision = "STABLE_MISS_EVIDENCE_INSUFFICIENT_NO_GO"
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "controls": {leaf: {"correct": controls[leaf], "total": 24, "passed": controls[leaf] == 24} for leaf in CONTROLS}, "target": {"correct": target_correct, "total": 24, "mixed_cells": len(mixed), "stable_all_wrong_cells": len(misses), "distinct_wording": len(wording), "distinct_stockness_load_strata": len(strata)}, "phase_b_enabled": False, "real_holdout_opened": False, "promotion": "none"}
    _write_summary(root / "phase-a-settlement.v1.json", settlement)
    _write_summary(root / "public-aggregate.v1.json", {key: value for key, value in settlement.items() if key not in {"format_version"}})
    _write_terminal(root, settlement)
    return settlement
