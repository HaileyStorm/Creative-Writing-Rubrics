"""Six-call provider-free S2 semantic-boundary successor."""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-nonpoetry-scope-semantic-boundary-successor-v1"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
LEAF_ID = "scope.passage.status"
CANDIDATE_TEXT = "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?"
REPEATS = (1, 2)
SLOTS = 6
MAX_SENDS = 6
BUNDLE_ID = "diagnostic.nonpoetry_scope_semantic_boundary_successor"
ATTEMPT_LIFECYCLE_POLICY = "terminal_sidecar_v1"
PRIVATE_CONTROLLER_NAME = "controller-contract.v2.json"
PRIVATE_CONTROLLER_SHA256 = "afdbe646de835e03ade54c59bf0a1c1de65a6afb21a1c09682738c9a724bd2a2"
PRIVATE_FILES = {
    "fixtures.v2.json": "2916447fdd475bdd2991aef18f1a42256e410729856aedad4a70d89057676b95",
    "expected-ledger.v2.json": "e61aef1567f324dd01e019a2d9e2901347f1bcd3955d7492a243baecf41913f2",
}
FIXTURE_COMMITMENTS = (
    "e7637d2bb30e23a4e586c7643d5d000d5cbd23283cbc1f2ef6f02a8a942e5d91",
    "9aab160981ab982d31521673c8f392cb297b9082c9d0444374172a695538811b",
    "54ec35abfd259706775930ec69115f8b42bdc7cf7978397959ba47f52cc04e4e",
)
RUNTIME_BINDINGS = {
    "registry/question_index.jsonl": "d89706f0d32b4b8f5393a81d2d2382d58890452a55e0549c5bac77dd2497892a",
    "registry/criterion_ownership.json": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876",
    "registry/all_modules.json": "b8c453f7eb86889f2e76b593eb44a6660f9f7cd695dbd6ac3d13b23d3635102b",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
    "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
}
PRESERVED_FIELDS = (
    "id", "module_id", "criterion_key", "text", "pass_answer", "weight",
    "question_type", "severity", "applies_when", "evidence_policy",
)
PRIVATE_CONTROLLER_ROOT: Path | None = None


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


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate frozen artifact: {path}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _current_head() -> str:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "CWR HEAD is unavailable")
    return completed.stdout.strip()


def _assert_source_head() -> None:
    if _current_head() != SOURCE_HEAD:
        raise ValueError("CWR live HEAD differs from the frozen execution source head")


def set_private_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    repository = REPOSITORY.resolve()
    try:
        root.relative_to(repository)
    except ValueError:
        pass
    else:
        raise ValueError("private root must remain outside the CWR checkout")
    global PRIVATE_CONTROLLER_ROOT
    PRIVATE_CONTROLLER_ROOT = root
    return root


def _controller_root() -> Path:
    if PRIVATE_CONTROLLER_ROOT is None:
        raise ValueError("An explicit external private root is required")
    return PRIVATE_CONTROLLER_ROOT


def _execution_root() -> Path:
    return _controller_root() / "execution-v4-6ae9ee0-head-gated"


def _private_file(name: str) -> dict[str, Any]:
    path = _controller_root() / name
    if name not in PRIVATE_FILES or not path.is_file() or sha256_file(path) != PRIVATE_FILES[name]:
        raise ValueError(f"Frozen private file is unavailable or drifted: {name}")
    return _load_json(path)


def _source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == LEAF_ID:
            return {key: row[key] for key in PRESERVED_FIELDS}
    raise ValueError("Canonical S2 leaf is unavailable")


def _candidate_leaf() -> dict[str, Any]:
    leaf = _source_leaf()
    leaf["text"] = CANDIDATE_TEXT
    return leaf


def _find_leaf(node: Any) -> dict[str, Any] | None:
    if isinstance(node, dict):
        if node.get("id") == LEAF_ID:
            return node
        for value in node.values():
            found = _find_leaf(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_leaf(value)
            if found is not None:
                return found
    return None


def _candidate_registry() -> list[dict[str, Any]]:
    modules = json.loads((REPOSITORY / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    module = next((row for row in modules if row.get("module_id") == "scope.passage"), None)
    if not isinstance(module, dict):
        raise ValueError("Canonical scope.passage module is unavailable")
    copied = json.loads(json.dumps(module, ensure_ascii=False))
    leaf = _find_leaf(copied)
    if leaf is None:
        raise ValueError("Canonical scope.passage.status leaf is unavailable")
    leaf["text"] = CANDIDATE_TEXT
    return [copied]


def _bundle() -> list[dict[str, Any]]:
    return [{
        "standard": {"id": "HBQ-RS", "version": "1.2.0"},
        "bundle_id": BUNDLE_ID,
        "version": 1,
        "title": "S2 passage-status semantic boundary successor",
        "module_ids": ["scope.passage"],
        "task_contract_domain_id": "s2",
        "domains": [{"domain_id": "s2", "title": "Passage-status boundary", "points": 100.0, "components": [{"module_id": "scope.passage", "weight": 1.0, "include_question_ids": [LEAF_ID]}], "score_mode": "weighted_binary_mean"}],
        "penalty_modules": [],
        "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
    }]


def validate_package() -> dict[str, Any]:
    _assert_source_head()
    frozen = subprocess.run(["git", "rev-parse", SOURCE_HEAD], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if frozen.returncode or frozen.stdout.strip() != SOURCE_HEAD:
        raise ValueError("CWR exact-head provenance is unavailable")
    for relative, expected in RUNTIME_BINDINGS.items():
        if sha256_file(REPOSITORY / relative) != expected:
            raise ValueError(f"Runtime binding drifted: {relative}")
    ownership = _load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    if ownership.get(LEAF_ID) != {"module_id": "scope.passage", "question_id": LEAF_ID}:
        raise ValueError("Canonical S2 ownership drifted")
    source = _source_leaf()
    candidate = _candidate_leaf()
    contract = _load_json(ROOT / "study-contract.json")
    expected_contract = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_semantic_boundary_successor",
        "development_only": True,
        "source_cwr_head": SOURCE_HEAD,
        "candidate": {"leaf_id": LEAF_ID, "text": CANDIDATE_TEXT, "source_leaf_sha256": sha256_bytes(canonical_json(source)), "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)), "owner": ownership[LEAF_ID], "preserved_fields": {key: source[key] for key in PRESERVED_FIELDS if key != "text"}},
        "semantic_decision": {"owner": "observable_anti_penalty_behavior_in_the_supplied_evaluation", "visible_whole_work_penalty": "NO", "supplied_evaluation_without_completeness_penalty": "YES", "no_evaluation_record": "CANNOT_ASSESS"},
        "geometry": {"fixtures_exact": 3, "repeats_exact": 2, "slots_exact": SLOTS, "candidate_only": True, "one_leaf_per_request": True},
        "execution": {"permitted_now": False, "provider_calls_made_now_exact": 0, "future_route": "codex", "future_model": "gpt-5.6-sol", "future_reasoning": "high", "batch_size": 1, "batch_attempts": 1, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "maximum_provider_sends": MAX_SENDS, "post_response_semantic_retries_permitted": False, "paid_or_fallback_route": "forbidden"},
        "private_controller": {"contract_filename": PRIVATE_CONTROLLER_NAME, "contract_sha256": PRIVATE_CONTROLLER_SHA256, "file_bindings": PRIVATE_FILES, "fixture_commitments_sha256": list(FIXTURE_COMMITMENTS)},
        "gate": {"requires": "all_three_cells_2_of_2_first_attempt_exact", "success_action": "FRESH_DISJOINT_CONFIRMATION_REVIEW_ELIGIBLE", "failure_action": "NO_GO", "automatic_promotion": False},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "owner", "split", "weight", "applicability", "evidence_policy")},
        "runtime_bindings": RUNTIME_BINDINGS,
    }
    if contract != expected_contract:
        raise ValueError("Public study contract drifted")
    controller_path = _controller_root() / PRIVATE_CONTROLLER_NAME
    if not controller_path.is_file() or sha256_file(controller_path) != PRIVATE_CONTROLLER_SHA256:
        raise ValueError("Private controller contract is unavailable or drifted")
    controller = _load_json(controller_path)
    if controller.get("study_id") != STUDY_ID or controller.get("source_cwr_head") != SOURCE_HEAD or controller.get("file_bindings") != PRIVATE_FILES or controller.get("fixture_commitments_sha256") != list(FIXTURE_COMMITMENTS):
        raise ValueError("Private controller identity or binding drifted")
    if controller.get("provider_execution", {}).get("provider_calls_made_exact") != 0 or controller.get("provider_execution", {}).get("planned_slots_exact") != SLOTS:
        raise ValueError("Private controller execution boundary drifted")
    fixtures = _private_file("fixtures.v2.json").get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 3:
        raise ValueError("Private fixture geometry drifted")
    if [sha256_bytes(canonical_json(row)) for row in fixtures] != list(FIXTURE_COMMITMENTS):
        raise ValueError("Private fixture commitment drifted")
    forbidden = {"expected", "expected_verdict", "semantic_state", "oracle", "rationale"}
    if any(not isinstance(row, dict) or forbidden.intersection(row) for row in fixtures):
        raise ValueError("Expected labels leaked into private fixture records")
    return {"study_id": STUDY_ID, "planned_slots": SLOTS, "provider_calls": 0, "candidate_only": True, "labels_loaded": False}


def build_schedule() -> list[dict[str, Any]]:
    validate_package()
    fixtures = _private_file("fixtures.v2.json")["fixtures"]
    question_hash = sha256_bytes(canonical_json(_candidate_leaf()))
    rubric_hash = RUNTIME_BINDINGS["registry/all_modules.json"]
    schedule: list[dict[str, Any]] = []
    for fixture in fixtures:
        artifact_text = str(fixture["evaluation_record"])
        artifact_hash = sha256_bytes(artifact_text.encode("utf-8"))
        for repeat in REPEATS:
            condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID, "arm": "candidate", "question_sha256": question_hash, "prompt_sha256": "0" * 64, "rubric_sha256": rubric_hash}
            fixture_id = str(fixture["fixture_id"])
            slot = {"slot_id": f"s2sb-v1-{fixture_id}-r{repeat}", "fixture_id": fixture_id, "fixture_commitment_sha256": sha256_bytes(canonical_json(fixture)), "repeat": repeat, "leaf_id": LEAF_ID, "artifact_text": artifact_text, "contexts": list(fixture["contexts"]), "artifact_kind": fixture["artifact_kind"], "declared_scope": fixture["declared_scope"], "condition": condition}
            slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=fixture_id, artifact_sha256=artifact_hash, condition=condition, repetition=repeat, rubric_revision="1.2.0")
            schedule.append(slot)
    if len(schedule) != SLOTS or len({row["slot_id"] for row in schedule}) != SLOTS or {row["leaf_id"] for row in schedule} != {LEAF_ID}:
        raise ValueError("Exact six-call geometry drifted")
    return schedule


def _slot_paths(root: Path, slot: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    fixture = str(slot["fixture_id"])
    return root / "inputs" / f"{fixture}.txt", root / "contracts" / f"{fixture}.json", root / "overrides" / f"{fixture}.json"


def _context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    return sorted((root / "contexts" / str(slot["fixture_id"])).glob("context-*.txt"))


def _task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"s2sb-{slot['fixture_id']}", "artifact_id": slot["fixture_id"], "context": {"artifact_kind": slot["artifact_kind"], "declared_scope": slot["declared_scope"], "completion_status": "excerpt", "background": ["Development-only S2 semantic-boundary check."], "constraints": ["Use only the supplied artifact and context."], "audience": ["rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "s2sb-v1-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen S2 semantic-boundary singleton successor."}


def prepare() -> dict[str, Any]:
    schedule = build_schedule()
    root = _execution_root()
    _write_or_verify(root / "catalog" / "candidate-registry.json", canonical_json(_candidate_registry()))
    _write_or_verify(root / "catalog" / "bundles.json", canonical_json(_bundle()))
    for slot in schedule:
        artifact, task_path, override_path = _slot_paths(root, slot)
        task = _task_contract(slot)
        _write_or_verify(artifact, str(slot["artifact_text"]).encode("utf-8"))
        _write_or_verify(task_path, canonical_json(task))
        _write_or_verify(override_path, canonical_json(_scope_override(slot, task)))
        for index, context in enumerate(slot["contexts"], start=1):
            _write_or_verify(root / "contexts" / str(slot["fixture_id"]) / f"context-{index:02d}.txt", str(context).encode("utf-8"))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "source_cwr_head": SOURCE_HEAD, "planned_slots": SLOTS, "private_controller_sha256": PRIVATE_CONTROLLER_SHA256, "runtime_bindings": RUNTIME_BINDINGS, "slots": [{key: row[key] for key in ("slot_id", "fixture_commitment_sha256", "repeat", "leaf_id", "logical_sample_id", "condition")} for row in schedule]}
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "slots": schedule}))
    return {"execution_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _command(slot: Mapping[str, Any], *, render: bool = False, resume: bool = False) -> list[str]:
    root = _execution_root()
    artifact, task, override = _slot_paths(root, slot)
    command = [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "candidate-registry.json"), "--bundles", str(root / "catalog" / "bundles.json"), "render-judge" if render else "judge"]
    if render:
        command.extend(["--artifact", str(artifact)])
    else:
        command.extend([str(artifact), "--output-dir", str(root / "runs" / str(slot["slot_id"])), "--reasoning", "high", "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", ATTEMPT_LIFECYCLE_POLICY])
    command.extend(["--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["fixture_id"]), "--question-id", LEAF_ID, "--task-contract", str(task), "--scope-compatibility-override", str(override)])
    for context in _context_paths(root, slot):
        command.extend(["--context", str(context)])
    if resume and not render:
        command.append("--resume")
    return command


def _prompt_bytes(value: Any) -> bytes:
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError("Rendered prompt contains a lone carriage return")
    return raw.replace(b"\r\n", b"\n")


def _input_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "name": path.name, "bytes": len(raw), "sha256": sha256_bytes(raw)}


def _resolved_runtime_schedule() -> list[dict[str, Any]]:
    root = _execution_root()
    resolved: list[dict[str, Any]] = []
    for source in build_schedule():
        prompt = root / "rendered-prompts" / f"{source['slot_id']}.txt"
        dry_manifest = _load_json(root / "runs" / str(source["slot_id"]) / "run.json")
        config = dry_manifest.get("configuration")
        if not prompt.is_file() or dry_manifest.get("format_version") != 5 or not isinstance(config, Mapping):
            raise ValueError(f"Provider-free dry-run binding is incomplete: {source['slot_id']}")
        compiled = config.get("compiled_bundle_sha256")
        questions = config.get("questions_sha256")
        if not isinstance(compiled, str) or len(compiled) != 64 or not isinstance(questions, str) or len(questions) != 64:
            raise ValueError("Provider-free dry-run lacks compiled bundle/question identity")
        slot = dict(source)
        slot["rendered_prompt_sha256"] = sha256_file(prompt)
        slot["compiled_bundle_sha256"] = compiled
        slot["questions_sha256"] = questions
        condition = dict(slot["condition"])
        condition.update({"prompt_sha256": slot["rendered_prompt_sha256"], "compiled_bundle_sha256": compiled, "questions_sha256": questions})
        slot["condition"] = condition
        slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=str(slot["fixture_id"]), artifact_sha256=sha256_bytes(str(slot["artifact_text"]).encode("utf-8")), condition=condition, repetition=int(slot["repeat"]), rubric_revision="1.2.0")
        resolved.append(slot)
    return resolved


def _disclosure(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    root = _execution_root()
    rows = []
    for slot in schedule:
        artifact, task, override = _slot_paths(root, slot)
        rows.append({"slot_id": slot["slot_id"], "repeat": slot["repeat"], "artifact": _input_record(artifact), "contexts": [_input_record(path) for path in _context_paths(root, slot)], "task_contract_sha256": sha256_file(task), "scope_compatibility_sha256": sha256_file(override), "registry_sha256": sha256_file(root / "catalog" / "candidate-registry.json"), "rendered_prompt_sha256": slot["rendered_prompt_sha256"]})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "preexecution_disclosure", "remote_destination": "Codex gpt-5.6-sol", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "slots": rows, "one_leaf_per_call": True, "maximum_provider_sends": MAX_SENDS, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "promotion": "none"}


def dry_run(*, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    prepared = prepare()
    root = _execution_root()
    for slot in build_schedule():
        run_manifest = root / "runs" / str(slot["slot_id"]) / "run.json"
        done = runner_call([*_command(slot, resume=run_manifest.is_file()), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"CWR dry-run stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
        rendered = runner_call(_command(slot, render=True), text=False, capture_output=True, check=False)
        if getattr(rendered, "returncode", 1):
            raise RuntimeError(f"CWR prompt render stopped at {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        _write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", _prompt_bytes(getattr(rendered, "stdout", b"")))
    schedule = _resolved_runtime_schedule()
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): slot["rendered_prompt_sha256"] for slot in schedule}))
    _write_or_verify(root / "runtime-schedule.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": schedule, "rendered_prompt_aggregate_sha256": aggregate}))
    _write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(_disclosure(schedule)))
    receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_dry_run", "provider_calls": 0, "slots": SLOTS, "rendered_prompt_aggregate_sha256": aggregate, "private_controller_sha256": PRIVATE_CONTROLLER_SHA256}
    _write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json(receipt))
    return {**prepared, "rendered_prompt_aggregate_sha256": aggregate, "provider_calls": 0}


def _validated_runtime_schedule() -> list[dict[str, Any]]:
    root = _execution_root()
    stored = _load_json(root / "runtime-schedule.json")
    expected = _resolved_runtime_schedule()
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): slot["rendered_prompt_sha256"] for slot in expected}))
    if stored != {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": expected, "rendered_prompt_aggregate_sha256": aggregate}:
        raise ValueError("Prepared runtime schedule drifted")
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != _disclosure(expected):
        raise ValueError("Preexecution disclosure is unavailable or drifted")
    return expected


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"])
    manifest = _load_json(run / "run.json")
    config = manifest.get("configuration")
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping):
        raise ValueError("Production singleton manifest is invalid")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 1}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "question_ids": [LEAF_ID], "compiled_bundle_sha256": slot["compiled_bundle_sha256"], "questions_sha256": slot["questions_sha256"]}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Production singleton configuration drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=1, reconstruct=False, strict_v5=True, require_durable=True)
    artifact, _task, _override = _slot_paths(root, slot)
    contexts = _context_paths(root, slot)
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[path.read_text(encoding="utf-8") for path in contexts], batch_attempts=1, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != LEAF_ID:
        raise ValueError("Accepted checkpoint does not contain exactly the frozen leaf")
    if runner._rejected_records(run, 1):
        raise ValueError("One-shot slot contains a rejected semantic retry")
    reported = _load_json(run / "responses" / "batch-0001.json").get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider, model, or reasoning binding drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session.strip():
        raise ValueError("Provider session identity is unavailable")
    return {"slot_id": slot["slot_id"], "fixture_id": slot["fixture_id"], "repeat": slot["repeat"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdicts[0]["verdict"], "run_id": verdicts[0]["run_id"], "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "accepted_provider_call_count": 1, "rejected_retry_count": 0, "batch_attempt_count": 1}


def execute(*, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit remote and zero-incremental-charge acknowledgement")
    _assert_source_head()
    schedule = _validated_runtime_schedule()
    root = _execution_root()
    claim = root / "execution-claim.v1"
    try:
        claim.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError("Execution root is already claimed; semantic retries are forbidden") from exc
    claim_value = {"format_version": 1, "study_id": STUDY_ID, "kind": "atomic_one_shot_execution_claim", "retry": "forbidden", "maximum_provider_sends": MAX_SENDS}
    _write_or_verify(claim / "claim.json", canonical_json(claim_value))
    acknowledgement = {"format_version": 1, "study_id": STUDY_ID, "kind": "owner_zero_incremental_charge_acknowledgement", "route": "codex", "paid_api_or_fallback_route": "forbidden", "acknowledged": True, "maximum_provider_sends": MAX_SENDS}
    _write_or_verify(root / "receipts" / "zero-charge-acknowledgement.v1.json", canonical_json(acknowledgement))
    records: list[dict[str, Any]] = []
    sessions: set[str] = set()
    chains: set[str] = set()
    for slot in schedule:
        done = runner_call([*_command(slot, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            terminal = {"format_version": 1, "study_id": STUDY_ID, "phase": "terminal_nonzero", "slot_id": slot["slot_id"], "completed_slots": len(records), "later_slots_started": False, "returncode": int(getattr(done, "returncode", 1)), "stderr_sha256": sha256_bytes(str(getattr(done, "stderr", "")).encode("utf-8")), "retry": "forbidden"}
            _write_or_verify(root / "execution-terminal.v1.json", canonical_json(terminal))
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}")
        record = verifier(root, slot)
        if record["session_id_sha256"] in sessions or record["checkpoint_chain_head_sha256"] in chains:
            raise ValueError("Duplicate provider session or checkpoint chain")
        sessions.add(record["session_id_sha256"])
        chains.add(record["checkpoint_chain_head_sha256"])
        records.append(record)
    _write_or_verify(root / "raw-results.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "records": records, "promotion": "none"}))
    terminal = {"format_version": 1, "study_id": STUDY_ID, "phase": "all_processes_accepted", "completed_slots": SLOTS, "retry": "forbidden", "promotion": "none"}
    _write_or_verify(root / "execution-terminal.v1.json", canonical_json(terminal))
    return {"mode": "execute", "completed_slots": SLOTS, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "promotion": "none"}


def settle() -> dict[str, Any]:
    root = _execution_root()
    schedule = _validated_runtime_schedule()
    terminal = _load_json(root / "execution-terminal.v1.json")
    raw = _load_json(root / "raw-results.v1.json")
    if terminal.get("phase") != "all_processes_accepted" or terminal.get("completed_slots") != SLOTS:
        raise ValueError("Exact six-call execution has not completed")
    records = raw.get("records")
    if not isinstance(records, list) or len(records) != SLOTS or {row.get("slot_id") for row in records} != {row["slot_id"] for row in schedule}:
        raise ValueError("Raw execution record geometry drifted")
    ledger_rows = _private_file("expected-ledger.v2.json").get("rows")
    if not isinstance(ledger_rows, list) or len(ledger_rows) != 3:
        raise ValueError("Expected ledger geometry drifted")
    expected = {row["fixture_id"]: row for row in ledger_rows}
    cells: dict[str, dict[str, Any]] = {}
    all_match = True
    by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_fixture[str(row["fixture_id"])].append(row)
    for fixture_id in sorted(by_fixture):
        observed = [str(row["verdict"]) for row in sorted(by_fixture[fixture_id], key=lambda item: int(item["repeat"]))]
        expected_verdict = str(expected[fixture_id]["expected_verdict"])
        matched = observed == [expected_verdict, expected_verdict]
        all_match = all_match and matched
        cells[str(expected[fixture_id]["semantic_state"])] = {"expected": expected_verdict, "observed": observed, "two_of_two": matched}
    decision = "FRESH_DISJOINT_CONFIRMATION_REVIEW_ELIGIBLE" if all_match else "NO_GO"
    result = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "cells": cells, "promotion": "none", "next_action": "independent_review_then_fresh_disjoint_confirmation_only" if all_match else "manual_diagnosis"}
    _write_or_verify(root / "settlement.v1.json", canonical_json(result))
    return result
