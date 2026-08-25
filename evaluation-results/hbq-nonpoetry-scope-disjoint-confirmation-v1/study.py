"""Fresh six-call S2 disjoint confirmation executor."""
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
STUDY_ID = "hbq-nonpoetry-scope-disjoint-confirmation-v1"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
LEAF_ID = "scope.passage.status"
CANDIDATE_TEXT = "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?"
BUNDLE_ID = "diagnostic.nonpoetry_scope_disjoint_confirmation"
ATTEMPT_LIFECYCLE_POLICY = "terminal_sidecar_v1"
REPEATS = (1, 2)
SLOTS = 6
PRIVATE_CONTROLLER_NAME = "controller-contract.v2.json"
PRIVATE_CONTROLLER_SHA256 = "fc62d1afd0f1357c05d28686df9310f3369d41b85548f966eefc2b0a1628abfc"
PRIVATE_FILES = {
    "fixtures.v2.json": "d357443c92566f337add1f7d473e9a761d01746da0d080b42bec601c9d87f1c6",
    "expected-ledger.v1.json": "7db4b63d6b282f22229acb813f5656951aca3fc1d88c6fd40841dce62617b23e",
}
FIXTURE_DIGESTS = (
    "862b222dcedcdb90df8687be1449486a177a74fc51b41b6815c17ba822239de2",
    "26ea348ee7a00cfe2becbd40b7db94c4ad1e4639992583380768737fd57d8cfe",
    "4c0dbf620db427d99da303409c3157f3abc4572c231f6cd47c9c3f2562954610",
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
LEAF_FIELDS = ("id", "module_id", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")
PRIVATE_ROOT: Path | None = None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def write_once(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Frozen artifact drifted: {path}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def current_head() -> str:
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.strip() or "CWR HEAD is unavailable")
    return done.stdout.strip()


def assert_exact_head() -> None:
    if current_head() != SOURCE_HEAD:
        raise ValueError("CWR live HEAD differs from the frozen execution source head")


def set_private_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Private root must be outside the CWR checkout")
    global PRIVATE_ROOT
    PRIVATE_ROOT = root
    return root


def controller_root() -> Path:
    if PRIVATE_ROOT is None:
        raise ValueError("An explicit external private root is required")
    return PRIVATE_ROOT


def execution_root() -> Path:
    return controller_root() / "execution-v3-6ae9ee0"


def private_file(name: str, *, load: bool = True) -> dict[str, Any] | None:
    path = controller_root() / name
    if name not in PRIVATE_FILES or not path.is_file() or sha256_file(path) != PRIVATE_FILES[name]:
        raise ValueError(f"Frozen private file is unavailable or drifted: {name}")
    return load_json(path) if load else None


def source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == LEAF_ID:
            return {key: row[key] for key in LEAF_FIELDS}
    raise ValueError("Canonical S2 leaf is unavailable")


def candidate_leaf() -> dict[str, Any]:
    value = source_leaf()
    value["text"] = CANDIDATE_TEXT
    return value


def find_leaf(node: Any) -> dict[str, Any] | None:
    if isinstance(node, dict):
        if node.get("id") == LEAF_ID:
            return node
        for value in node.values():
            found = find_leaf(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_leaf(value)
            if found is not None:
                return found
    return None


def candidate_registry() -> list[dict[str, Any]]:
    modules = json.loads((REPOSITORY / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    source = next((row for row in modules if row.get("module_id") == "scope.passage"), None)
    if not isinstance(source, dict):
        raise ValueError("Canonical scope.passage module is unavailable")
    copied = json.loads(json.dumps(source, ensure_ascii=False))
    leaf = find_leaf(copied)
    if leaf is None:
        raise ValueError("Canonical scope.passage.status leaf is unavailable")
    leaf["text"] = CANDIDATE_TEXT
    return [copied]


def bundle() -> list[dict[str, Any]]:
    return [{"standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1, "title": "S2 fresh disjoint confirmation", "module_ids": ["scope.passage"], "task_contract_domain_id": "s2", "domains": [{"domain_id": "s2", "title": "Fresh passage-status confirmation", "points": 100.0, "components": [{"module_id": "scope.passage", "weight": 1.0, "include_question_ids": [LEAF_ID]}], "score_mode": "weighted_binary_mean"}], "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True}, "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True}}]


def expected_contract() -> dict[str, Any]:
    source = source_leaf()
    candidate = candidate_leaf()
    owner = load_json(REPOSITORY / "registry" / "criterion_ownership.json")[LEAF_ID]
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_fresh_disjoint_confirmation",
        "development_only": True,
        "source_cwr_head": SOURCE_HEAD,
        "candidate": {"leaf_id": LEAF_ID, "text": CANDIDATE_TEXT, "source_leaf_sha256": sha256_bytes(canonical_json(source)), "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)), "owner": owner, "unchanged_fields": {key: source[key] for key in LEAF_FIELDS if key != "text"}},
        "freshness": {"prior_fixture_identity_reuse": False, "prior_carrier_prose_reuse": False, "prior_record_template_reuse": False, "prior_answer_key_language_reuse": False},
        "geometry": {"fresh_fixtures": 3, "candidate_only": True, "repeats_per_fixture": 2, "slots": SLOTS, "one_leaf_per_call": True},
        "execution": {"freeze_provider_calls": 0, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "batch_attempts": 1, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "semantic_retry": "forbidden", "normalization": "forbidden", "maximum_provider_sends": SLOTS, "paid_or_fallback_route": "forbidden", "live_head_must_equal_source_head_before_claim": True},
        "private_controller": {"filename": PRIVATE_CONTROLLER_NAME, "sha256": PRIVATE_CONTROLLER_SHA256, "bound_files": PRIVATE_FILES, "fixture_digests": list(FIXTURE_DIGESTS)},
        "gate": {"required": "six_of_six_exact_first_attempt_raw_verdicts", "success_action": "INDEPENDENT_WORDING_ONLY_PROMOTION_REVIEW_ELIGIBLE", "failure_action": "NO_GO", "automatic_promotion": False},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "owner", "split", "weight", "applicability", "evidence_policy")},
        "runtime_bindings": RUNTIME_BINDINGS,
    }


def validate_package() -> dict[str, Any]:
    assert_exact_head()
    for relative, expected in RUNTIME_BINDINGS.items():
        if sha256_file(REPOSITORY / relative) != expected:
            raise ValueError(f"Runtime binding drifted: {relative}")
    if load_json(ROOT / "study-contract.json") != expected_contract():
        raise ValueError("Public confirmation contract drifted")
    controller_path = controller_root() / PRIVATE_CONTROLLER_NAME
    if not controller_path.is_file() or sha256_file(controller_path) != PRIVATE_CONTROLLER_SHA256:
        raise ValueError("Private confirmation controller is unavailable or drifted")
    controller = load_json(controller_path)
    if controller.get("study_id") != STUDY_ID or controller.get("source_cwr_head") != SOURCE_HEAD or controller.get("bound_files") != PRIVATE_FILES or controller.get("fixture_digests") != list(FIXTURE_DIGESTS):
        raise ValueError("Private controller identity or binding drifted")
    if controller.get("future_execution", {}).get("calls_during_freeze") != 0 or controller.get("future_execution", {}).get("normalization") != "forbidden":
        raise ValueError("Private execution boundary drifted")
    fixtures = private_file("fixtures.v2.json")
    assert fixtures is not None
    rows = fixtures.get("fixtures")
    if not isinstance(rows, list) or len(rows) != 3 or [sha256_bytes(canonical_json(row)) for row in rows] != list(FIXTURE_DIGESTS):
        raise ValueError("Fresh fixture geometry or commitments drifted")
    forbidden = {"target_verdict", "boundary_case", "basis", "expected", "oracle", "answer"}
    if any(not isinstance(row, dict) or forbidden.intersection(row) for row in rows):
        raise ValueError("Answer-key content leaked into fixture records")
    private_file("expected-ledger.v1.json", load=False)
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "labels_loaded": False, "exact_head": SOURCE_HEAD}


def build_schedule() -> list[dict[str, Any]]:
    validate_package()
    fixtures = private_file("fixtures.v2.json")
    assert fixtures is not None
    schedule: list[dict[str, Any]] = []
    question_hash = sha256_bytes(canonical_json(candidate_leaf()))
    for fixture in fixtures["fixtures"]:
        artifact_text = str(fixture["carrier_text"])
        if fixture.get("evaluation_record") is not None:
            artifact_text += "\n\n" + str(fixture["evaluation_record"])
        artifact_hash = sha256_bytes(artifact_text.encode("utf-8"))
        for repeat in REPEATS:
            condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID, "question_sha256": question_hash, "prompt_sha256": "0" * 64, "rubric_sha256": RUNTIME_BINDINGS["registry/all_modules.json"]}
            fixture_id = str(fixture["fixture_id"])
            slot = {"slot_id": f"s2dc-v1-{fixture_id}-r{repeat}", "fixture_id": fixture_id, "fixture_digest": sha256_bytes(canonical_json(fixture)), "repeat": repeat, "leaf_id": LEAF_ID, "artifact_text": artifact_text, "contexts": list(fixture["contexts"]), "artifact_kind": fixture["artifact_kind"], "declared_scope": fixture["declared_scope"], "condition": condition}
            slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=fixture_id, artifact_sha256=artifact_hash, condition=condition, repetition=repeat, rubric_revision="1.2.0")
            schedule.append(slot)
    if len(schedule) != SLOTS or len({row["slot_id"] for row in schedule}) != SLOTS or len({row["logical_sample_id"] for row in schedule}) != SLOTS:
        raise ValueError("Six-call schedule geometry drifted")
    return schedule


def slot_paths(root: Path, slot: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    fixture_id = str(slot["fixture_id"])
    return root / "inputs" / f"{fixture_id}.txt", root / "contracts" / f"{fixture_id}.json", root / "overrides" / f"{fixture_id}.json"


def context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    return sorted((root / "contexts" / str(slot["fixture_id"])).glob("context-*.txt"))


def task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"s2dc-{slot['fixture_id']}", "artifact_id": slot["fixture_id"], "context": {"artifact_kind": slot["artifact_kind"], "declared_scope": slot["declared_scope"], "completion_status": "excerpt", "background": ["Fresh disjoint passage-status confirmation."], "constraints": ["Use only this packet."], "audience": ["rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "s2dc-v1-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed passage-scope compatibility for this fresh singleton confirmation."}


def prepare() -> dict[str, Any]:
    schedule = build_schedule()
    root = execution_root()
    write_once(root / "catalog" / "candidate-registry.json", canonical_json(candidate_registry()))
    write_once(root / "catalog" / "bundles.json", canonical_json(bundle()))
    for slot in schedule:
        artifact, task_path, override_path = slot_paths(root, slot)
        task = task_contract(slot)
        write_once(artifact, str(slot["artifact_text"]).encode("utf-8"))
        write_once(task_path, canonical_json(task))
        write_once(override_path, canonical_json(scope_override(slot, task)))
        for index, context in enumerate(slot["contexts"], start=1):
            write_once(root / "contexts" / str(slot["fixture_id"]) / f"context-{index:02d}.txt", str(context).encode("utf-8"))
    public_slots = [{key: row[key] for key in ("slot_id", "fixture_digest", "repeat", "leaf_id", "logical_sample_id", "condition")} for row in schedule]
    write_once(root / "study-manifest.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "source_head": SOURCE_HEAD, "slots": public_slots, "runtime_bindings": RUNTIME_BINDINGS, "provider_calls": 0}))
    write_once(root / "private-schedule.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "slots": schedule}))
    return {"execution_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def command(slot: Mapping[str, Any], *, render: bool = False, resume: bool = False) -> list[str]:
    root = execution_root()
    artifact, task, override = slot_paths(root, slot)
    value = [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "candidate-registry.json"), "--bundles", str(root / "catalog" / "bundles.json"), "render-judge" if render else "judge"]
    if render:
        value.extend(["--artifact", str(artifact)])
    else:
        value.extend([str(artifact), "--output-dir", str(root / "runs" / str(slot["slot_id"])), "--reasoning", "high", "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", ATTEMPT_LIFECYCLE_POLICY])
    value.extend(["--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["fixture_id"]), "--question-id", LEAF_ID, "--task-contract", str(task), "--scope-compatibility-override", str(override)])
    for context in context_paths(root, slot):
        value.extend(["--context", str(context)])
    if resume and not render:
        value.append("--resume")
    return value


def prompt_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        try:
            raw = value.decode("utf-8").encode("utf-8")
        except UnicodeDecodeError:
            raw = value.decode("cp1252").encode("utf-8")
    else:
        raw = str(value).encode("utf-8")
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError("Rendered prompt contains a lone carriage return")
    return raw.replace(b"\r\n", b"\n")


def input_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "name": path.name, "bytes": len(raw), "sha256": sha256_bytes(raw)}


def resolved_schedule() -> list[dict[str, Any]]:
    root = execution_root()
    result: list[dict[str, Any]] = []
    for source in build_schedule():
        prompt = root / "rendered-prompts" / f"{source['slot_id']}.txt"
        manifest = load_json(root / "runs" / str(source["slot_id"]) / "run.json")
        config = manifest.get("configuration")
        if not prompt.is_file() or manifest.get("format_version") != 5 or not isinstance(config, Mapping):
            raise ValueError("Provider-free dry binding is incomplete")
        compiled = config.get("compiled_bundle_sha256")
        questions = config.get("questions_sha256")
        if not isinstance(compiled, str) or len(compiled) != 64 or not isinstance(questions, str) or len(questions) != 64:
            raise ValueError("Provider-free compiled identity is unavailable")
        slot = dict(source)
        slot["rendered_prompt_sha256"] = sha256_file(prompt)
        slot["compiled_bundle_sha256"] = compiled
        slot["questions_sha256"] = questions
        condition = dict(slot["condition"])
        condition.update({"prompt_sha256": slot["rendered_prompt_sha256"], "compiled_bundle_sha256": compiled, "questions_sha256": questions})
        slot["condition"] = condition
        slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=str(slot["fixture_id"]), artifact_sha256=sha256_bytes(str(slot["artifact_text"]).encode("utf-8")), condition=condition, repetition=int(slot["repeat"]), rubric_revision="1.2.0")
        result.append(slot)
    return result


def disclosure(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    root = execution_root()
    slots = []
    for slot in schedule:
        artifact, task, override = slot_paths(root, slot)
        slots.append({"slot_id": slot["slot_id"], "repeat": slot["repeat"], "artifact": input_record(artifact), "contexts": [input_record(path) for path in context_paths(root, slot)], "task_contract_sha256": sha256_file(task), "scope_compatibility_sha256": sha256_file(override), "registry_sha256": sha256_file(root / "catalog" / "candidate-registry.json"), "rendered_prompt_sha256": slot["rendered_prompt_sha256"]})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "preexecution_disclosure", "remote_destination": "Codex gpt-5.6-sol", "model": "gpt-5.6-sol", "reasoning": "high", "slots": slots, "one_leaf_per_call": True, "maximum_provider_sends": SLOTS, "batch_attempts": 1, "normalization": "forbidden", "promotion": "none"}


def dry_run(*, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    prepared = prepare()
    root = execution_root()
    for slot in build_schedule():
        run_manifest = root / "runs" / str(slot["slot_id"]) / "run.json"
        done = runner_call([*command(slot, resume=run_manifest.is_file()), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"Dry-run stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
        rendered = runner_call(command(slot, render=True), text=False, capture_output=True, check=False)
        if getattr(rendered, "returncode", 1):
            raise RuntimeError(f"Prompt render stopped at {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        write_once(root / "rendered-prompts" / f"{slot['slot_id']}.txt", prompt_bytes(getattr(rendered, "stdout", b"")))
    schedule = resolved_schedule()
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): slot["rendered_prompt_sha256"] for slot in schedule}))
    write_once(root / "runtime-schedule.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": schedule, "rendered_prompt_aggregate_sha256": aggregate}))
    write_once(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(disclosure(schedule)))
    write_once(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_dry_run", "provider_calls": 0, "slots": SLOTS, "rendered_prompt_aggregate_sha256": aggregate, "controller_sha256": PRIVATE_CONTROLLER_SHA256}))
    return {**prepared, "rendered_prompt_aggregate_sha256": aggregate}


def validated_runtime_schedule() -> list[dict[str, Any]]:
    assert_exact_head()
    root = execution_root()
    expected = resolved_schedule()
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): slot["rendered_prompt_sha256"] for slot in expected}))
    if load_json(root / "runtime-schedule.json") != {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": expected, "rendered_prompt_aggregate_sha256": aggregate}:
        raise ValueError("Runtime schedule drifted")
    if load_json(root / "receipts" / "preexecution-disclosure.v1.json") != disclosure(expected):
        raise ValueError("Preexecution disclosure drifted")
    return expected


def verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"])
    manifest = load_json(run / "run.json")
    config = manifest.get("configuration")
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping):
        raise ValueError("Production run manifest is invalid")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 1}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "question_ids": [LEAF_ID], "compiled_bundle_sha256": slot["compiled_bundle_sha256"], "questions_sha256": slot["questions_sha256"]}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Production run configuration drifted")
    artifact, task_path, override_path = slot_paths(root, slot)
    contexts = context_paths(root, slot)
    prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    if config.get("artifact") != input_record(artifact) or config.get("contexts") != [input_record(path) for path in contexts]:
        raise ValueError("Production artifact or context binding drifted")
    if config.get("task_contract", {}).get("sha256") != sha256_file(task_path) or config.get("scope_compatibility", {}).get("sha256") != sha256_file(override_path):
        raise ValueError("Production task or scope binding drifted")
    checkpoint_prompt = gzip.decompress((run / "responses" / "batch-0001.prompt.txt.gz").read_bytes())
    if prompt_bytes(checkpoint_prompt) != prompt.read_bytes() or sha256_file(prompt) != slot["rendered_prompt_sha256"]:
        raise ValueError("Checkpoint prompt differs from the frozen rendered prompt")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=1, reconstruct=False, strict_v5=True, require_durable=True)
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[path.read_text(encoding="utf-8") for path in contexts], batch_attempts=1, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != LEAF_ID:
        raise ValueError("Accepted checkpoint does not contain exactly the frozen leaf")
    response = load_json(run / "responses" / "batch-0001.json")
    if response.get("accepted_attempt") != 1 or response.get("normalization_audit") != [] or response.get("rejected_chain", {}).get("count") != 0:
        raise ValueError("First-attempt, no-retry, no-normalization rule failed")
    raw_message = load_json(run / "responses" / "batch-0001.accepted-0001.message.txt")
    raw_verdicts = raw_message.get("verdicts")
    if not isinstance(raw_verdicts, list) or len(raw_verdicts) != 1 or raw_verdicts[0].get("question_id") != LEAF_ID or raw_verdicts[0].get("verdict") != verdicts[0].get("verdict"):
        raise ValueError("Raw accepted verdict does not match the settled checkpoint")
    if runner._rejected_records(run, 1):
        raise ValueError("Rejected retry record is forbidden")
    reported = response.get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider identity drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session.strip():
        raise ValueError("Provider session is unavailable")
    return {"slot_id": slot["slot_id"], "fixture_id": slot["fixture_id"], "repeat": slot["repeat"], "logical_sample_id": slot["logical_sample_id"], "raw_verdict": raw_verdicts[0]["verdict"], "run_id": verdicts[0]["run_id"], "session_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_sha256": chain, "accepted_attempt": 1, "normalization_events": 0, "rejected_retries": 0}


def execute(*, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = verify_slot) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit remote and zero-incremental-charge acknowledgement")
    assert_exact_head()
    schedule = validated_runtime_schedule()
    root = execution_root()
    claim = root / "execution-claim.v1"
    try:
        claim.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError("Execution root is already claimed; retry is forbidden") from exc
    write_once(claim / "claim.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "kind": "one_shot_claim", "maximum_provider_sends": SLOTS, "retry": "forbidden", "normalization": "forbidden"}))
    write_once(root / "receipts" / "zero-charge-acknowledgement.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "route": "codex", "acknowledged": True, "maximum_provider_sends": SLOTS, "paid_or_fallback_route": "forbidden"}))
    records: list[dict[str, Any]] = []
    sessions: set[str] = set()
    chains: set[str] = set()
    for slot in schedule:
        done = runner_call([*command(slot, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            terminal = {"format_version": 1, "study_id": STUDY_ID, "phase": "terminal_nonzero", "slot_id": slot["slot_id"], "completed_slots": len(records), "later_slots_started": False, "returncode": int(getattr(done, "returncode", 1)), "retry": "forbidden"}
            write_once(root / "execution-terminal.v1.json", canonical_json(terminal))
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}")
        record = verifier(root, slot)
        if record["session_sha256"] in sessions or record["checkpoint_chain_sha256"] in chains:
            raise ValueError("Provider session or checkpoint chain was reused")
        sessions.add(record["session_sha256"])
        chains.add(record["checkpoint_chain_sha256"])
        records.append(record)
    write_once(root / "raw-results.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "records": records, "promotion": "none"}))
    write_once(root / "execution-terminal.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "phase": "all_six_accepted", "completed_slots": SLOTS, "normalization_events": 0, "rejected_retries": 0, "promotion": "none"}))
    return {"mode": "execute", "completed_slots": SLOTS, "normalization_events": 0, "rejected_retries": 0, "promotion": "none"}


def settle() -> dict[str, Any]:
    root = execution_root()
    schedule = validated_runtime_schedule()
    terminal = load_json(root / "execution-terminal.v1.json")
    raw = load_json(root / "raw-results.v1.json")
    if terminal.get("phase") != "all_six_accepted" or terminal.get("completed_slots") != SLOTS or terminal.get("normalization_events") != 0 or terminal.get("rejected_retries") != 0:
        raise ValueError("Exact confirmation execution is incomplete or invalid")
    records = raw.get("records")
    if not isinstance(records, list) or len(records) != SLOTS or {row.get("slot_id") for row in records} != {row["slot_id"] for row in schedule}:
        raise ValueError("Raw result geometry drifted")
    ledger = private_file("expected-ledger.v1.json")
    assert ledger is not None
    entries = ledger.get("entries")
    if not isinstance(entries, list) or len(entries) != 3:
        raise ValueError("Private answer-key geometry drifted")
    expected = {row["fixture_id"]: row for row in entries}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["fixture_id"])].append(record)
    cells: dict[str, dict[str, Any]] = {}
    success = True
    for fixture_id in sorted(grouped):
        observed = [str(row["raw_verdict"]) for row in sorted(grouped[fixture_id], key=lambda item: int(item["repeat"]))]
        target = str(expected[fixture_id]["target_verdict"])
        matched = observed == [target, target]
        success = success and matched
        cells[str(expected[fixture_id]["boundary_case"])] = {"target": target, "observed": observed, "two_of_two": matched}
    decision = "INDEPENDENT_WORDING_ONLY_PROMOTION_REVIEW_ELIGIBLE" if success else "NO_GO"
    result = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "cells": cells, "promotion": "none", "automatic_promotion": False}
    write_once(root / "settlement.v1.json", canonical_json(result))
    return result
