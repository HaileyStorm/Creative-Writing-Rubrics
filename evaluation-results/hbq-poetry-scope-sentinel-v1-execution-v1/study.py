"""Frozen zero-paid executor for the public S1 poetry scope sentinel."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-poetry-scope-sentinel-v1"
STUDY_ID = "hbq-poetry-scope-sentinel-v1-execution-v1"
PREDECESSOR_COMMIT = "67bbf999719a7aa62036edcb1e0a7104a43f17bf"
PREDECESSOR_TREE = "2f2c466691d06c0a0e137a94805d1ba4ed8227b2"
LEAVES = (
    "form.poetry.general_poetry.ending",
    "form.poetry.elegy.movement",
    "form.poetry.free_verse.repetition",
    "form.poetry.haiku_in_english.sequence_scope",
    "form.poetry.pantoum.recontext",
)
MODULES = {
    "form.poetry.general_poetry.ending": "form.poetry.general_poetry",
    "form.poetry.elegy.movement": "form.poetry.elegy",
    "form.poetry.free_verse.repetition": "form.poetry.free_verse",
    "form.poetry.haiku_in_english.sequence_scope": "form.poetry.haiku_in_english",
    "form.poetry.pantoum.recontext": "form.poetry.pantoum",
}
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
REPETITIONS, SLOTS, MAX_SENDS = 3, 60, 180
BUNDLE_ID = "diagnostic.poetry_scope_sentinel"
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json",
    "registry/question_index.jsonl", "registry/criterion_ownership.json", "bundles/all_bundles.json",
    "src/hbqrs/runner.py", "src/hbqrs/cli.py",
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
        raise ValueError("Prompt contains a lone carriage return")
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
    spec = importlib.util.spec_from_file_location("s1_execution_predecessor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load frozen S1 predecessor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _predecessor_bindings() -> dict[str, str]:
    return {
        "public-synthetic-corpus.json": "1909dddfe0c465641c8e8d774145e788a22738bc",
        "study-contract.json": "94ca9ccdfc87cfa2bd98c36fce902727548c1d0a",
        "study.py": "8de27b9a5aa90bb100ae4b2c784e6b95f59ec961",
    }


def validate_package() -> dict[str, Any]:
    value = contract()
    expected_execution = {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "batch_attempts": 3, "maximum_provider_sends": MAX_SENDS, "one_leaf_per_call": True, "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden"}
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1 or value.get("status") != "frozen_execution_successor_unexecuted":
        raise ValueError("Execution contract identity drifted")
    if value.get("predecessor") != {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": _predecessor_bindings()} or value.get("execution") != expected_execution:
        raise ValueError("Execution predecessor or route binding drifted")
    if value.get("geometry") != {"artifacts": 20, "leaves": 5, "repeats": 3, "slots": SLOTS} or value.get("public_result_policy") != "aggregate_only_after_execution" or value.get("promotion") != "none":
        raise ValueError("Execution geometry or public boundary drifted")
    path = "evaluation-results/hbq-poetry-scope-sentinel-v1"
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}") != PREDECESSOR_TREE:
        raise ValueError("Predecessor tree is unavailable")
    for name, blob in _predecessor_bindings().items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}/{name}") != blob or _git("hash-object", str(PREDECESSOR_ROOT / name)) != blob:
            raise ValueError("Current predecessor bytes differ from exact historical source")
    predecessor = _predecessor()
    predecessor.verify_package()
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "predecessor": PREDECESSOR_COMMIT}


def _bundle() -> list[dict[str, Any]]:
    components = [{"module_id": module, "weight": 1.0, "include_question_ids": [leaf]} for leaf, module in MODULES.items()]
    return [{"standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1, "title": "Frozen S1 singleton diagnostic", "module_ids": list(MODULES.values()), "task_contract_domain_id": "s1", "domains": [{"domain_id": "s1", "title": "S1 poetry scope sentinel", "points": 100.0, "components": components, "score_mode": "weighted_binary_mean"}], "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True}, "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True}}]


def _task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"pssexec-contract-{slot['artifact_id']}", "artifact_id": slot["artifact_id"], "context": {"artifact_kind": slot["artifact_kind"], "declared_scope": slot["declared_scope"], "completion_status": slot["completion_status"], "background": ["Public synthetic development screen for declared poetic scope only."], "constraints": ["Use only supplied artifact and contexts."], "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "pssexec-v1-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen S1 poetry diagnostic bundle."}


def build_schedule() -> list[dict[str, Any]]:
    validate_package()
    predecessor = _predecessor(); corpus = predecessor.load_corpus(); predecessor.verify_corpus(corpus)
    schedule: list[dict[str, Any]] = []
    for ordinal, artifact in enumerate(corpus["artifacts"], start=1):
        carrier = predecessor.FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]
        for repeat in range(1, REPETITIONS + 1):
            slot = {"slot_id": f"pssexec-v1-{ordinal:02d}-r{repeat}", "artifact_id": f"synthetic-{ordinal:02d}", "artifact_file": f"synthetic-{ordinal:02d}.txt", "leaf_id": artifact["leaf_id"], "repeat": repeat, "expected_verdict": predecessor.STATE_VERDICTS[artifact["state"]], "artifact_text": artifact["text"], "contexts": artifact["contexts"], "artifact_kind": artifact["artifact_kind"], "declared_scope": artifact["declared_scope"], "completion_status": carrier["completion_status"], "artifact_sha256": predecessor.artifact_sha256(artifact)}
            task = _task_contract(slot); slot["task_contract"] = task; slot["scope_override"] = _scope_override(slot, task)
            condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": slot["leaf_id"], "task_contract_sha256": sha256_bytes(canonical_json(task)), "prompt_sha256": "0" * 64, "rubric_sha256": sha256_file(REPOSITORY / "registry" / "all_modules.json")}
            slot["condition"] = condition
            slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=slot["artifact_id"], artifact_sha256=slot["artifact_sha256"], condition=condition, repetition=repeat, rubric_revision="1.2.0")
            schedule.append(slot)
    if len(schedule) != SLOTS or len({row["slot_id"] for row in schedule}) != SLOTS or {row["leaf_id"] for row in schedule} != set(LEAVES):
        raise ValueError("Exact S1 schedule drifted")
    return schedule


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "artifact_id", "artifact_file", "leaf_id", "repeat", "artifact_sha256", "condition", "logical_sample_id")}


def _runtime_bindings() -> dict[str, Any]:
    return {"runtime_head": _git("rev-parse", "HEAD"), "cwr_files": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}, "successor_files": {path: sha256_file(ROOT / path) for path in SUCCESSOR_FILES}}


def _paths(root: Path, slot: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    stem = str(slot["artifact_id"])
    return root / "inputs" / str(slot["artifact_file"]), root / "contracts" / f"{stem}.json", root / "overrides" / f"{stem}.json"


def prepare(private_root: str | Path) -> dict[str, Any]:
    root = _external_root(private_root); schedule = build_schedule()
    _write_or_verify(root / "catalog" / "bundles.json", canonical_json(_bundle()))
    for slot in schedule:
        artifact, task, override = _paths(root, slot)
        _write_or_verify(artifact, slot["artifact_text"].encode("utf-8")); _write_or_verify(task, canonical_json(slot["task_contract"])); _write_or_verify(override, canonical_json(slot["scope_override"]))
        for index, text in enumerate(slot["contexts"], start=1):
            _write_or_verify(root / "contexts" / str(slot["artifact_id"]) / f"context-{index:02d}.txt", text.encode("utf-8"))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest)); _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": schedule}))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    return sorted((root / "contexts" / str(slot["artifact_id"])).glob("context-*.txt"))


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, resume: bool = False) -> list[str]:
    root = _external_root(private_root); artifact, task, override = _paths(root, slot)
    command = [sys.executable, "-m", "hbqrs", "--bundles", str(root / "catalog" / "bundles.json"), "judge", str(artifact), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai", "--batch-size", "1", "--batch-attempts", "3", "--artifact-id", str(slot["artifact_id"]), "--question-id", str(slot["leaf_id"]), "--task-contract", str(task), "--scope-compatibility-override", str(override), "--output-dir", str(root / "runs" / str(slot["slot_id"]))]
    for context in _context_paths(root, slot): command.extend(["--context", str(context)])
    if resume: command.append("--resume")
    return command


def _render_command(slot: Mapping[str, Any], root: Path) -> list[str]:
    artifact, task, override = _paths(root, slot)
    command = [sys.executable, "-m", "hbqrs", "--bundles", str(root / "catalog" / "bundles.json"), "render-judge", "--artifact", str(artifact), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["artifact_id"]), "--question-id", str(slot["leaf_id"]), "--task-contract", str(task), "--scope-compatibility-override", str(override)]
    for context in _context_paths(root, slot): command.extend(["--context", str(context)])
    return command


def _runtime_schedule(root: Path, schedule: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for source in schedule:
        prompt = root / "rendered-prompts" / f"{source['slot_id']}.txt"
        if not prompt.is_file():
            raise ValueError(f"Missing rendered prompt: {source['slot_id']}")
        slot = dict(source); prompt_hash = sha256_file(prompt)
        slot["rendered_prompt_sha256"] = prompt_hash
        condition = dict(slot["condition"]); condition["prompt_sha256"] = prompt_hash
        slot["condition"] = condition
        slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=slot["artifact_id"], artifact_sha256=slot["artifact_sha256"], condition=condition, repetition=slot["repeat"], rubric_revision="1.2.0")
        resolved.append(slot)
    return resolved


def _rendered_prompt_bytes(value: Any) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if not isinstance(value, bytes):
        raise ValueError("CWR render returned no prompt bytes")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        text = value.decode("cp1252")
    return text.encode("utf-8")


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    prepared = prepare(private_root); root = _external_root(private_root)
    for slot in build_schedule():
        command = [*command_for(slot, root, resume=(root / "runs" / slot["slot_id"] / "run.json").is_file()), "--dry-run"]
        done = runner_call(command, text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"CWR dry run stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
        rendered = runner_call(_render_command(slot, root), text=False, capture_output=True, check=False)
        if getattr(rendered, "returncode", 1):
            raise RuntimeError(f"CWR prompt render stopped at {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        _write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", canonical_prompt_bytes(_rendered_prompt_bytes(getattr(rendered, "stdout", None))))
    schedule = _runtime_schedule(root, build_schedule())
    hashes = {slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in schedule}
    aggregate = sha256_bytes(canonical_json(hashes))
    _write_summary(root / "runtime-schedule.json", {"format_version": 1, "slots": schedule, "rendered_prompt_aggregate_sha256": aggregate})
    preview = {"mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS, "first_command": command_for(schedule[0], root), "last_command": command_for(schedule[-1], root), "rendered_prompt_sha256s": hashes, "rendered_prompt_aggregate_sha256": aggregate}
    _write_summary(root / "dry-run.json", preview)
    return {**prepared, **preview}


def _validate_runtime_bindings(root: Path) -> list[dict[str, Any]]:
    manifest = _load_json(root / "study-manifest.json")
    if manifest.get("runtime_bindings") != _runtime_bindings():
        raise ValueError("CWR runtime/schema/runner binding drifted; dry-run again")
    stored = _load_json(root / "runtime-schedule.json")
    expected = _runtime_schedule(root, build_schedule())
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected}))
    if stored.get("slots") != expected or stored.get("rendered_prompt_aggregate_sha256") != aggregate:
        raise ValueError("Prepared prompt schedule drifted; dry-run again")
    return expected


def _fresh_execute_preflight(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    for slot in schedule:
        run = root / "runs" / str(slot["slot_id"])
        if not (run / "run.json").is_file():
            raise ValueError("Fresh execute requires complete dry-run manifests")
        responses = run / "responses"
        if responses.is_dir() and any(path.is_file() for path in responses.rglob("*")):
            raise ValueError("Fresh execute rejects prior provider attempts; use --resume")


def execute(private_root: str | Path, *, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    root = _external_root(private_root); schedule = _validate_runtime_bindings(root)
    if not resume:
        _fresh_execute_preflight(root, schedule)
    for slot in schedule:
        done = runner_call([*command_for(slot, root, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
    return {"mode": "resume" if resume else "execute", "inspected_slots": SLOTS, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "billing": "owner_attested_subscription_zero_incremental_charge"}


def _input_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "name": path.name, "bytes": len(data), "sha256": sha256_bytes(data)}


def _verify_checkpoint_prompt(run: Path, prompt: Path) -> dict[str, str]:
    checkpoint = run / "responses" / "batch-0001.prompt.txt.gz"
    try:
        raw = gzip.decompress(checkpoint.read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt is unavailable or malformed") from exc
    rendered = prompt.read_bytes()
    if canonical_prompt_bytes(raw) != rendered:
        raise ValueError("Checkpoint prompt differs from frozen rendered prompt beyond CRLF-to-LF transport")
    return {"rendered_prompt_sha256": sha256_bytes(rendered), "checkpoint_prompt_sha256": sha256_bytes(raw), "canonical_prompt_sha256": sha256_bytes(canonical_prompt_bytes(raw))}


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"]); manifest = _load_json(run / "run.json"); config = manifest.get("configuration")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "question_ids": [slot["leaf_id"]]}
    if manifest.get("format_version") != 4 or not isinstance(config, Mapping) or any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Production singleton run binding drifted")
    if manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Run manifest configuration hash drifted")
    artifact, task, override = _paths(root, slot); contexts = _context_paths(root, slot); prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    if sha256_file(prompt) != slot["rendered_prompt_sha256"] or config.get("artifact") != _input_record(artifact) or config.get("contexts") != [_input_record(path) for path in contexts]:
        raise ValueError("Artifact, context, or prompt binding drifted")
    if config.get("task_contract", {}).get("sha256") != sha256_file(task) or config.get("scope_compatibility", {}).get("sha256") != sha256_file(override):
        raise ValueError("Task contract or scope override binding drifted")
    expected_prompts = [sha256_file(REPOSITORY / "prompts" / "judge" / name) for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")]
    actual_prompts = [item.get("sha256") for item in config.get("prompts", [])] if isinstance(config.get("prompts"), list) else []
    if actual_prompts != expected_prompts or config.get("response_schema", {}).get("sha256") != sha256_file(REPOSITORY / "schema" / "hbq_judge_response.schema.json"):
        raise ValueError("Strict prompt or schema binding drifted")
    commitment = _verify_checkpoint_prompt(run, prompt)
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=str(slot["artifact_text"]), context_texts=[path.read_text(encoding="utf-8") for path in contexts], batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]:
        raise ValueError("Checkpoint does not contain exactly the frozen leaf")
    manifest_run_id, verdict_run_id = manifest.get("run_id"), verdicts[0].get("run_id")
    if not isinstance(manifest_run_id, str) or not manifest_run_id.strip() or not isinstance(verdict_run_id, str) or not verdict_run_id.strip() or verdict_run_id != manifest_run_id:
        raise ValueError("Accepted checkpoint run identity does not match its manifest")
    runner._validate_typed_checkpoint_evidence(verdicts[0].get("evidence"), question_id=str(slot["leaf_id"]))
    runner._validate_exact_quotes(verdicts[0].get("evidence"), artifact_text=str(slot["artifact_text"]), context_texts=[path.read_text(encoding="utf-8") for path in contexts], question_id=str(slot["leaf_id"]))
    checkpoint = _load_json(run / "responses" / "batch-0001.json"); reported = checkpoint.get("provider", {}).get("reported", {}) if isinstance(checkpoint.get("provider"), Mapping) else {}
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider, model, or reasoning binding drifted")
    session = reported.get("session_id"); diagnostic = _load_json(run / "diagnostic.json")
    if not isinstance(session, str) or not session.strip() or diagnostic.get("status") != "DIAGNOSTIC_SUBSET" or diagnostic.get("selected_question_ids") != [slot["leaf_id"]]:
        raise ValueError("Provider identity or diagnostic singleton binding drifted")
    return {"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdicts[0].get("verdict"), "expected": slot["expected_verdict"], "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "run_id": verdicts[0].get("run_id"), "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "evidence": verdicts[0].get("evidence"), "accepted_provider_call_count": 1, "rejected_retry_count": len(runner._rejected_records(run, 1)), "batch_attempt_count": 1 + len(runner._rejected_records(run, 1)), **commitment}


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    result = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": SLOTS, "failures": failures}
    _write_summary(root / "settlement.json", result)
    _write_summary(root / "public-aggregate.json", {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS})
    return result


def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    root = _external_root(private_root)
    try:
        schedule = _validate_runtime_bindings(root)
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "runtime", "reason": str(exc)}])
    records: list[dict[str, Any]] = []; failures: list[dict[str, str]] = []
    for slot in schedule:
        try:
            records.append(verifier(root, slot))
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != SLOTS:
        return _incomplete(root, len(records), failures)
    if len({row["logical_sample_id"] for row in records}) != SLOTS or len({row["session_id_sha256"] for row in records}) != SLOTS or len({row["checkpoint_chain_head_sha256"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Repeated logical, session, or checkpoint identity"}])
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list); counts = {leaf: Counter() for leaf in LEAVES}
    by_id = {item["slot_id"]: item for item in schedule}
    for row in records:
        slot = by_id[row["slot_id"]]; cells[(str(slot["artifact_id"]), str(slot["leaf_id"]))].append(bool(row["correct"])); counts[str(slot["leaf_id"])][str(row["verdict"])] += 1
    per_cell = {f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": by_id[next(row["slot_id"] for row in records if (by_id[row["slot_id"]]["artifact_id"], by_id[row["slot_id"]]["leaf_id"]) == cell)]["expected_verdict"]} for index, (cell, values) in enumerate(cells.items(), start=1)}
    scored = [value for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE"]; na = [value for value in per_cell.values() if value["expected_state"] == "NOT_APPLICABLE"]
    decision = "PASS_NO_CHANGE" if all(value["passed"] for value in scored) else "DIAGNOSTIC_FAIL"
    four = {leaf: {state: counts[leaf][state] for state in sorted(VERDICTS)} for leaf in LEAVES}
    settlement = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "per_cell_three_of_three": per_cell, "canonical_four_state_counts": four, "promotion": "none", "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "scored_cells": {"passed": sum(item["passed"] for item in scored), "total": len(scored)}, "not_applicable_diagnostic_cells": {"matched": sum(item["passed"] for item in na), "total": len(na)}, "canonical_four_state_counts": four, "promotion": "none"}
    _write_summary(root / "settlement.json", settlement); _write_summary(root / "public-aggregate.json", public)
    return settlement


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest="command", required=True); commands.add_parser("verify")
    for name in ("prepare", "settle"):
        child = commands.add_parser(name); child.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    result = validate_package() if args.command == "verify" else prepare(args.private_root) if args.command == "prepare" else settle(args.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
