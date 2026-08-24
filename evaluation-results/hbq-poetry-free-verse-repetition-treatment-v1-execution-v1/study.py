"""Private, zero-paid executor for the frozen S1 free-verse wording screen."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-treatment-v1-execution-v1"
EXECUTION_SUCCESSOR_VERSION = 5
SUCCESSOR_PARENT_HEAD = "637c92befda031529041f61152e9460607349516"
PREDECESSOR_ID = "hbq-poetry-free-verse-repetition-treatment-v1"
PREDECESSOR_COMMIT = "76023dff13558f024fefb38cbd59ab45ae8682ec"
PREDECESSOR_TREE = "9afcd4eada8c61034f784e128c6030740eccf951"
PREDECESSOR_FILES = {
    "README.md": "43a1f108ed7b180385bdcec87629c4af590ce3a3",
    "run.py": "fd09cc3a85b6cd50f5c34425cab4ba79a5d8ec42",
    "study-contract.json": "365400285799e3d6e4e918eed6cb56f4d5fe86f6",
    "study.py": "478f00e00ec5619002de81c268d06ecb8b2baf2b",
}
PRIVATE_CONTROLLER_ROOT: Path | None = None
CONTROLLER_NAME = "private-controller.json"
LEDGER_NAME = "private-ledger.json"
VERIFIER_NAME = "verify_private_freeze.py"
CONTROLLER_SHA256 = "7a75a6dd30e028bcfa398b7104bed34d32ea71efb491310eb87d3a50700dd5b9"
LEDGER_SHA256 = "9a3455fee1466d4cdc7461ab33c6b4014a4ad112b0e9f8293d3cf63615f52fbc"
VERIFIER_SHA256 = "6f70bbd01101d27b432b87421563a063bdee658f73700fabf4591b09e66a5c23"
# Earlier private execution roots are immutable terminal provenance. This v5
# root is deliberately fresh after v4's zero-byte retryable provider failure.
PRIVATE_EXECUTION_DIRECTORY = "execution-v5-quota-reset-successor-terminal-sidecar-v1"
V4_PRIVATE_EXECUTION_DIRECTORY = "execution-v4-bounded-connection-retries-terminal-sidecar-v1"
V4_RUNTIME_HEAD = "8b18f2847cf0b1e95a5603ffbf6d8f30a31981c5"
EXECUTION_CLAIM_NAME = "execution-claim.v1.json"
LEAF_ID = "form.poetry.free_verse.repetition"
ARMS = ("current", "candidate")
REPEATS = (1, 2, 3)
SLOTS = 24
ATTEMPT_LIFECYCLE_POLICY = "terminal_sidecar_v1"
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_treatment"
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "registry/all_modules.json",
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "src/hbqrs/runner.py",
)
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object at {path.name}")
    return value


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "Git binding lookup failed")
    return completed.stdout.strip()


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate frozen private artifact: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_prepared_manifest(path: Path, value: bytes) -> None:
    if not path.exists() or path.read_bytes() == value:
        _write_or_verify(path, value)
        return
    runs = _execution_root() / "runs"
    if runs.is_dir() and any(item.is_file() for item in runs.rglob("*")):
        raise ValueError("Prepared-manifest drift requires a fresh private root")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def set_private_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    repository = REPOSITORY.resolve()
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
    global PRIVATE_CONTROLLER_ROOT
    PRIVATE_CONTROLLER_ROOT = root
    return root


def _controller_root() -> Path:
    if PRIVATE_CONTROLLER_ROOT is None:
        raise ValueError("An explicit private_root is required")
    return PRIVATE_CONTROLLER_ROOT


def _execution_root() -> Path:
    return _controller_root() / PRIVATE_EXECUTION_DIRECTORY


def _private_paths() -> tuple[Path, Path, Path]:
    root = _controller_root()
    return root / CONTROLLER_NAME, root / LEDGER_NAME, root / VERIFIER_NAME


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    controller_path, ledger_path, verifier_path = _private_paths()
    if not controller_path.is_file() or not ledger_path.is_file() or not verifier_path.is_file():
        raise ValueError("Exact private r3 controller, ledger, or verifier is unavailable")
    if (sha256_file(controller_path) != CONTROLLER_SHA256 or sha256_file(ledger_path) != LEDGER_SHA256
            or sha256_file(verifier_path) != VERIFIER_SHA256):
        raise ValueError("Private r3 controller, ledger, or verifier commitment drifted")
    controller, ledger = _load_json(controller_path), _load_json(ledger_path)
    expected_execution = {
        "permitted_now": False, "provider_calls_made_exact": 0, "planned_calls_exact": 24,
        "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high",
        "zero_paid_route_required": True, "semantic_retries_permitted": False,
        "one_leaf_per_request": True,
    }
    fixtures = controller.get("fixture_matrix")
    slots = ledger.get("slot_mapping")
    if controller.get("study_id") != PREDECESSOR_ID or controller.get("format_version") != 3 or controller.get("visibility") != "private_controller_only" or controller.get("provider_execution") != expected_execution:
        raise ValueError("Private r3 controller boundary drifted")
    if not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(slots, list) or len(slots) != SLOTS:
        raise ValueError("Private r3 geometry drifted")
    if [item.get("role") for item in fixtures].count("target") != 1 or [item.get("role") for item in fixtures].count("control") != 3:
        raise ValueError("Private r3 target/control composition drifted")
    fixture_ids = {item.get("fixture_id") for item in fixtures}
    expected = {(fixture_id, arm, repeat) for fixture_id in fixture_ids for arm in ARMS for repeat in REPEATS}
    actual = {(item.get("fixture_id"), item.get("arm"), item.get("repeat")) for item in slots}
    if len(fixture_ids) != 4 or actual != expected or len({item.get("opaque_slot_id") for item in slots}) != SLOTS:
        raise ValueError("Private r3 slot mapping drifted")
    return controller, ledger


def _source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == LEAF_ID:
            return row
    raise ValueError("Canonical free-verse leaf is unavailable")


def _predecessor_contract() -> dict[str, Any]:
    raw = _git("show", f"{PREDECESSOR_COMMIT}:evaluation-results/{PREDECESSOR_ID}/study-contract.json")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Frozen predecessor contract is malformed")
    return value


def _questions() -> dict[str, dict[str, Any]]:
    frozen = _predecessor_contract()
    source = _source_leaf()
    candidate = frozen.get("candidate")
    if not isinstance(candidate, Mapping) or not isinstance(candidate.get("text"), str):
        raise ValueError("Frozen candidate wording is unavailable")
    preserved = candidate.get("preserved_fields")
    if not isinstance(preserved, Mapping) or any(source.get(key) != value for key, value in preserved.items()):
        raise ValueError("Canonical free-verse leaf fields drifted")
    if sha256_bytes(canonical_json({key: source[key] for key in (*preserved, "text")})) != candidate.get("source_leaf_sha256"):
        raise ValueError("Canonical free-verse leaf digest drifted")
    current = {key: source[key] for key in (*preserved, "text")}
    treatment = dict(current)
    treatment["text"] = str(candidate["text"])
    if sha256_bytes(canonical_json(treatment)) != candidate.get("candidate_leaf_sha256"):
        raise ValueError("Frozen candidate leaf digest drifted")
    return {"current": current, "candidate": treatment}


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


def _registry(arm: str) -> list[dict[str, Any]]:
    if arm not in ARMS:
        raise ValueError("Unknown private arm")
    modules = json.loads((REPOSITORY / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    source = next((item for item in modules if item.get("module_id") == "form.poetry.free_verse"), None)
    if not isinstance(source, dict):
        raise ValueError("Canonical free-verse module is unavailable")
    copied = deepcopy(source)
    leaf = _find_leaf(copied)
    question = _questions()[arm]
    if leaf is None or any(leaf.get(key) != value for key, value in question.items() if key != "text" and key in leaf):
        raise ValueError("Candidate treatment changed more than the leaf wording")
    leaf["text"] = question["text"]
    return [copied]


def _bundle() -> list[dict[str, Any]]:
    return [{
        "standard": {"id": "HBQ-RS", "version": "1.2.0"},
        "bundle_id": BUNDLE_ID, "version": 1,
        "title": "Free-verse repetition singleton diagnostic",
        "module_ids": ["form.poetry.free_verse"], "task_contract_domain_id": "s1",
        "domains": [{"domain_id": "s1", "title": "Free-verse repetition A/B", "points": 100.0,
                     "components": [{"module_id": "form.poetry.free_verse", "weight": 1.0, "include_question_ids": [LEAF_ID]}],
                     "score_mode": "weighted_binary_mean"}],
        "penalty_modules": [],
        "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
    }]


def _fixture_token(fixture_id: str) -> str:
    return sha256_bytes(fixture_id.encode("utf-8"))[:16]


def _task_contract(fixture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": 1, "contract_id": f"s1fvr-{_fixture_token(str(fixture['fixture_id']))}",
        "artifact_id": str(fixture["fixture_id"]),
        "context": {"artifact_kind": "poetry_excerpt", "declared_scope": fixture["declared_scope"],
                    "completion_status": fixture["completion_status"], "background": ["Private synthetic development screen."],
                    "constraints": ["Use only supplied artifact and contexts."], "audience": ["development-only rubric validation"]},
        "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": [],
    }


def build_schedule() -> list[dict[str, Any]]:
    controller, ledger = _private_freeze()
    fixtures = {str(item["fixture_id"]): item for item in controller["fixture_matrix"]}
    questions = _questions()
    rubric_sha256 = sha256_file(REPOSITORY / "registry" / "all_modules.json")
    schedule: list[dict[str, Any]] = []
    for mapping in sorted(ledger["slot_mapping"], key=lambda item: str(item["opaque_slot_id"])):
        arm, fixture_id, repeat = str(mapping["arm"]), str(mapping["fixture_id"]), int(mapping["repeat"])
        fixture = fixtures[fixture_id]
        question = questions[arm]
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True,
                     "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID,
                     "question_sha256": sha256_bytes(canonical_json(question)), "prompt_sha256": "0" * 64,
                     "rubric_sha256": rubric_sha256}
        schedule.append({
            "opaque_slot_id": str(mapping["opaque_slot_id"]), "arm": arm, "fixture_id": fixture_id, "repeat": repeat,
            "artifact_text": str(fixture["text"]), "contexts": list(fixture["contexts"]),
            "expected_verdict": str(fixture["expected_verdict"]), "role": str(fixture["role"]),
            "condition": condition,
            "logical_sample_id": logical_sample_id(study_id=STUDY_ID, artifact_id=fixture_id,
                artifact_sha256=sha256_bytes(str(fixture["text"]).encode("utf-8")), condition=condition,
                repetition=repeat, rubric_revision="1.2.0"),
        })
    if len(schedule) != SLOTS or len({slot["opaque_slot_id"] for slot in schedule}) != SLOTS:
        raise ValueError("Execution schedule geometry drifted")
    return schedule


def _artifact_path(root: Path, slot: Mapping[str, Any]) -> Path:
    return root / "inputs" / f"artifact-{_fixture_token(str(slot['fixture_id']))}.txt"


def _task_path(root: Path, slot: Mapping[str, Any]) -> Path:
    return root / "contracts" / f"task-{_fixture_token(str(slot['fixture_id']))}.json"


def _override_path(root: Path, slot: Mapping[str, Any]) -> Path:
    return root / "overrides" / f"scope-{_fixture_token(str(slot['fixture_id']))}.json"


def _scope_override(fixture: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": str(fixture["fixture_id"]), "bundle_id": BUNDLE_ID,
            "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"],
            "artifact_kind": "poetry_excerpt", "declared_scope": fixture["declared_scope"],
            "compatibility_mode": "reviewed_override", "decision_id": "s1fvr-execution-v1-scope-compatibility",
            "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen S1 singleton diagnostic."}


def _context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    return sorted((root / "contexts" / _fixture_token(str(slot["fixture_id"]))).glob("context-*.txt"))


def _registry_path(root: Path, arm: str) -> Path:
    return root / "catalog" / ("registry-a.json" if arm == "current" else "registry-b.json")


def _runtime_bindings() -> dict[str, Any]:
    return {"runtime_head": _git("rev-parse", "HEAD"), "cwr_files": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS},
            "successor_files": {path: sha256_file(ROOT / path) for path in SUCCESSOR_FILES},
            "controller_sha256": sha256_file(_private_paths()[0]), "ledger_sha256": sha256_file(_private_paths()[1]),
            "verifier_sha256": sha256_file(_private_paths()[2])}


def _generated_input_bindings(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    paths = {
        "catalog/bundles.json": root / "catalog" / "bundles.json",
        "catalog/registry-a.json": _registry_path(root, "current"),
        "catalog/registry-b.json": _registry_path(root, "candidate"),
        "private-schedule.json": root / "private-schedule.json",
    }
    for slot in schedule:
        token = _fixture_token(str(slot["fixture_id"]))
        paths[f"inputs/artifact-{token}.txt"] = _artifact_path(root, slot)
        paths[f"contracts/task-{token}.json"] = _task_path(root, slot)
        paths[f"overrides/scope-{token}.json"] = _override_path(root, slot)
        for path in _context_paths(root, slot):
            paths[path.relative_to(root).as_posix()] = path
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("Generated execution input is unavailable")
    return {name: sha256_file(path) for name, path in sorted(paths.items())}


def _manifest(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    slots = [{key: slot[key] for key in ("opaque_slot_id", "repeat", "condition", "logical_sample_id")} for slot in schedule]
    return {"format_version": 1, "study_id": STUDY_ID, "execution_successor_version": EXECUTION_SUCCESSOR_VERSION,
            "contract_sha256": sha256_file(ROOT / "study-contract.json"),
            "runtime_bindings": _runtime_bindings(), "generated_input_bindings": _generated_input_bindings(_execution_root(), schedule),
            "planned_slots": SLOTS, "slots": slots}


def validate_package() -> dict[str, Any]:
    value = contract()
    expected_execution = {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_call": True,
        "batch_size": 1, "batch_attempts": 1, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY,
        "allow_remote_at_live_dispatch": True,
        "maximum_provider_sends": SLOTS, "semantic_retries": "forbidden", "resume": "forbidden",
        "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden"}
    expected_quota_reset = {
        "version": EXECUTION_SUCCESSOR_VERSION, "successor_parent_head": SUCCESSOR_PARENT_HEAD,
        "private_execution_directory": PRIVATE_EXECUTION_DIRECTORY,
        "ancestor_private_execution_directory": V4_PRIVATE_EXECUTION_DIRECTORY,
        "ancestor_runtime_head": V4_RUNTIME_HEAD,
        "ancestor_terminal": {"classification": "provider_retryable_failure", "response_bytes": 0,
                              "rubric_sample_or_result": "none", "retry": False, "lineage_not_a_vote": True},
        "fresh_namespace_required": True,
        "runtime_callback_policy": "current_frozen_runtime_required_before_render_and_dispatch",
    }
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1 or value.get("status") != "frozen_quota_reset_successor_unexecuted":
        raise ValueError("Execution contract identity drifted")
    if value.get("predecessor") != {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": PREDECESSOR_FILES} or value.get("execution") != expected_execution:
        raise ValueError("Execution predecessor or route drifted")
    if value.get("quota_reset_successor") != expected_quota_reset:
        raise ValueError("Quota-reset successor lineage drifted")
    if value.get("geometry") != {"fixtures": 4, "arms": list(ARMS), "repeats": 3, "slots": SLOTS, "same_fixture_ab": True} or value.get("prompt_delta") != "candidate_leaf_text_only":
        raise ValueError("Execution geometry or prompt-delta boundary drifted")
    if value.get("public_result_policy") != "aggregate_only_after_execution" or value.get("promotion") != "none" or value.get("success_action") != "HOLDOUT_ELIGIBLE_ON_SUCCESS" or value.get("failure_action") != "NO_GO":
        raise ValueError("Execution result boundary drifted")
    path = f"evaluation-results/{PREDECESSOR_ID}"
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}") != PREDECESSOR_TREE:
        raise ValueError("Frozen predecessor tree is unavailable")
    for name, blob in PREDECESSOR_FILES.items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}/{name}") != blob:
            raise ValueError("Frozen predecessor file binding drifted")
    _private_freeze()
    _questions()
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": SLOTS, "private_r3_bound": True}


def prepare() -> dict[str, Any]:
    validate_package()
    root, schedule = _execution_root(), build_schedule()
    if _claim_path(root).exists():
        raise ValueError("Preparation cannot rewrite a claimed root")
    _write_or_verify(root / "catalog" / "bundles.json", canonical_json(_bundle()))
    _write_or_verify(_registry_path(root, "current"), canonical_json(_registry("current")))
    _write_or_verify(_registry_path(root, "candidate"), canonical_json(_registry("candidate")))
    controller, _ledger = _private_freeze()
    fixtures = {str(item["fixture_id"]): item for item in controller["fixture_matrix"]}
    for fixture_id, fixture in fixtures.items():
        slot = next(item for item in schedule if item["fixture_id"] == fixture_id)
        _write_or_verify(_artifact_path(root, slot), str(fixture["text"]).encode("utf-8"))
        task = _task_contract(fixture)
        _write_or_verify(_task_path(root, slot), canonical_json(task))
        _write_or_verify(_override_path(root, slot), canonical_json(_scope_override(fixture, task)))
        for index, context in enumerate(fixture["contexts"], start=1):
            _write_or_verify(root / "contexts" / _fixture_token(fixture_id) / f"context-{index:02d}.txt", str(context).encode("utf-8"))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": schedule}))
    _write_prepared_manifest(root / "study-manifest.json", canonical_json(_manifest(schedule)))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _command(slot: Mapping[str, Any], *, render: bool) -> list[str]:
    root = _execution_root()
    command = [sys.executable, "-m", "hbqrs", "--registry", str(_registry_path(root, str(slot["arm"]))), "--bundles", str(root / "catalog" / "bundles.json"), "render-judge" if render else "judge"]
    artifact = _artifact_path(root, slot)
    if render:
        command.extend(["--artifact", str(artifact)])
    else:
        command.extend([str(artifact), "--output-dir", str(root / "runs" / str(slot["opaque_slot_id"])), "--reasoning", "high", "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", ATTEMPT_LIFECYCLE_POLICY, "--allow-remote"])
    command.extend(["--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["fixture_id"]), "--question-id", LEAF_ID, "--task-contract", str(_task_path(root, slot)), "--scope-compatibility-override", str(_override_path(root, slot))])
    for context in _context_paths(root, slot):
        command.extend(["--context", str(context)])
    return command


def _stdout_bytes(result: Any) -> bytes:
    value = result.stdout
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise ValueError("render-judge produced no prompt bytes")


def _canonical_prompt(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""):
        raise ValueError("Rendered prompt has a lone carriage return")
    return value.replace(b"\r\n", b"\n")


def _run_render(slot: Mapping[str, Any], runner_call: Callable[..., Any]) -> bytes:
    result = runner_call(_command(slot, render=True), cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("render-judge failed for a frozen private slot")
    return _canonical_prompt(_stdout_bytes(result))


def _verify_prompt_pairs(root: Path, schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> None:
    questions = _questions()
    for fixture_id in {str(slot["fixture_id"]) for slot in schedule}:
        for repeat in REPEATS:
            current = next(slot for slot in schedule if slot["fixture_id"] == fixture_id and slot["arm"] == "current" and slot["repeat"] == repeat)
            candidate = next(slot for slot in schedule if slot["fixture_id"] == fixture_id and slot["arm"] == "candidate" and slot["repeat"] == repeat)
            expected = prompts[str(current["opaque_slot_id"])].replace(questions["current"]["text"].encode("utf-8"), questions["candidate"]["text"].encode("utf-8"))
            if expected == prompts[str(current["opaque_slot_id"])] or expected != prompts[str(candidate["opaque_slot_id"])]:
                raise ValueError("Rendered A/B prompts differ by more than the frozen candidate wording")


def _disclosure(schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "execution_successor_version": EXECUTION_SUCCESSOR_VERSION,
            "route": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
            "planned_provider_sends": SLOTS, "one_leaf_per_call": True, "batch_attempts": 1,
            "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "semantic_retries": "forbidden", "resume": "forbidden",
            "paid_api_or_fallback_route": "forbidden", "slots": [{"opaque_slot_id": slot["opaque_slot_id"], "rendered_prompt_sha256": sha256_bytes(prompts[str(slot["opaque_slot_id"])])} for slot in schedule]}


def dry_run(*, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    prepared = prepare()
    root, schedule = _execution_root(), build_schedule()
    prompts: dict[str, bytes] = {}
    for slot in schedule:
        rendered = _run_render(slot, runner_call)
        prompts[str(slot["opaque_slot_id"])] = rendered
        _write_or_verify(root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt", rendered)
    _verify_prompt_pairs(root, schedule, prompts)
    disclosure = _disclosure(schedule, prompts)
    _write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(disclosure))
    _write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "prompt_pair_checks": 12, "disclosure_sha256": sha256_bytes(canonical_json(disclosure))}))
    return {**prepared, "rendered_prompts": SLOTS, "provider_calls": 0, "prompt_pair_checks": 12}


def _runtime_schedule() -> list[dict[str, Any]]:
    root = _execution_root()
    if not (root / "study-manifest.json").is_file() or not (root / "private-schedule.json").is_file():
        raise ValueError("Execution requires a frozen provider-free dry run and disclosure")
    manifest = _load_json(root / "study-manifest.json")
    schedule_file = _load_json(root / "private-schedule.json")
    schedule = schedule_file.get("slots")
    if not isinstance(schedule, list) or manifest != _manifest(schedule):
        raise ValueError("Frozen private runtime manifest drifted")
    return schedule


def _assert_frozen_runtime(schedule: Sequence[Mapping[str, Any]]) -> None:
    """Reject a checkout or callback drift before a provider-capable command."""
    root = _execution_root()
    if _load_json(root / "study-manifest.json") != _manifest(schedule):
        raise ValueError("Frozen private runtime manifest drifted before dispatch")


def _execution_claim(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    manifest = root / "study-manifest.json"
    disclosure = root / "receipts" / "preexecution-disclosure.v1.json"
    if not manifest.is_file() or not disclosure.is_file():
        raise ValueError("Execution claim requires a frozen manifest and disclosure")
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "execution_successor_version": EXECUTION_SUCCESSOR_VERSION,
        "state": "claimed_before_execution",
        "planned_slots": SLOTS,
        "opaque_slot_ids_sha256": sha256_bytes(canonical_json([slot["opaque_slot_id"] for slot in schedule])),
        "manifest_sha256": sha256_file(manifest),
        "disclosure_sha256": sha256_file(disclosure),
    }


def _claim_path(root: Path) -> Path:
    return root / EXECUTION_CLAIM_NAME


def _assert_fresh_slot_paths(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    stale: list[str] = []
    for slot in schedule:
        slot_id = str(slot["opaque_slot_id"])
        paths = (
            root / "runs" / slot_id,
            root / "dispatches" / f"{slot_id}.start.v1.json",
            root / "dispatches" / f"{slot_id}.settled.v1.json",
            root / "dispatches" / f"{slot_id}.failure.v1.json",
        )
        stale.extend(str(path.relative_to(root)) for path in paths if path.exists())
    if stale:
        raise ValueError(f"Execution requires a fresh private root; existing slot state: {', '.join(stale)}")


def _claim_execution(root: Path, schedule: Sequence[Mapping[str, Any]]) -> Path:
    expected = canonical_json(_execution_claim(root, schedule))
    path = _claim_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as error:
        raise ValueError("Execution claim already exists; retry or resume is forbidden") from error
    try:
        offset = 0
        while offset < len(expected):
            written = os.write(descriptor, expected[offset:])
            if written <= 0:
                raise OSError("Unable to write the complete execution claim")
            offset += written
    finally:
        os.close(descriptor)
    return path


def _require_execution_claim(root: Path, schedule: Sequence[Mapping[str, Any]]) -> Path:
    path = _claim_path(root)
    expected = canonical_json(_execution_claim(root, schedule))
    if not path.is_file() or path.read_bytes() != expected:
        raise ValueError("Execution claim is unavailable or drifted")
    return path


def _zero_charge_receipt() -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "acknowledged": True, "route": "codex_gpt-5.6-sol_high",
            "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden", "maximum_provider_sends": SLOTS}


def _write_zero_charge_acknowledgement() -> None:
    _write_or_verify(_execution_root() / "receipts" / "zero-charge-acknowledgement.v1.json", canonical_json(_zero_charge_receipt()))


def _dispatch_start(root: Path, slot: Mapping[str, Any]) -> Path:
    path = root / "dispatches" / f"{slot['opaque_slot_id']}.start.v1.json"
    _write_or_verify(path, canonical_json({"format_version": 1, "study_id": STUDY_ID,
        "opaque_slot_id": slot["opaque_slot_id"], "state": "started_before_provider_dispatch",
        "route": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
        "batch_attempts": 1, "semantic_retries": "forbidden", "resume": "forbidden"}))
    return path


def _dispatch_settlement(root: Path, slot: Mapping[str, Any], start: Path) -> None:
    _write_or_verify(root / "dispatches" / f"{slot['opaque_slot_id']}.settled.v1.json", canonical_json({
        "format_version": 1, "study_id": STUDY_ID, "opaque_slot_id": slot["opaque_slot_id"],
        "state": "runner_command_returned_zero", "start_sha256": sha256_file(start),
    }))


def _result_bytes(result: Any, field: str) -> bytes:
    value = getattr(result, field, b"")
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if value is None:
        return b""
    raise ValueError(f"Runner {field} is not text or bytes")


def _dispatch_failure(root: Path, slot: Mapping[str, Any], start: Path, result: Any) -> dict[str, Any]:
    output = root / "runs" / str(slot["opaque_slot_id"])
    stdout, stderr = _result_bytes(result, "stdout"), _result_bytes(result, "stderr")
    definitely_not_contacted = not output.exists() and b"pass --allow-remote" in stderr
    record = {
        "format_version": 1, "study_id": STUDY_ID, "opaque_slot_id": slot["opaque_slot_id"],
        "state": "runner_command_returned_nonzero", "start_sha256": sha256_file(start),
        "returncode": result.returncode,
        "stdout": {"bytes": len(stdout), "sha256": sha256_bytes(stdout)},
        "stderr": {"bytes": len(stderr), "sha256": sha256_bytes(stderr)},
        "run_directory_present": output.exists(),
        "contact_classification": (
            "definitely_not_contacted_precontact_remote_disclosure_gate"
            if definitely_not_contacted else "ambiguous_provider_contact"
        ),
    }
    _write_or_verify(root / "dispatches" / f"{slot['opaque_slot_id']}.failure.v1.json", canonical_json(record))
    return record


def execute(*, acknowledged_zero_incremental_charge: bool = False,
            runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit zero-incremental-charge acknowledgement")
    root, schedule = _execution_root(), _runtime_schedule()
    receipt = root / "receipts" / "preexecution-disclosure.v1.json"
    dry = root / "receipts" / "provider-free-dry-run.v1.json"
    if not receipt.is_file() or not dry.is_file():
        raise ValueError("Execution requires a frozen provider-free dry run and disclosure")
    prompts = {str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes() for slot in schedule}
    if _load_json(receipt) != _disclosure(schedule, prompts):
        raise ValueError("Preexecution disclosure drifted")
    if (root / "settlement.v1.json").exists() or (root / "terminal-sidecar.v1.json").exists():
        raise ValueError("Execution cannot follow a terminal settlement")
    _assert_fresh_slot_paths(root, schedule)
    _claim_execution(root, schedule)
    _write_zero_charge_acknowledgement()
    for slot in schedule:
        output = root / "runs" / str(slot["opaque_slot_id"])
        dispatch = root / "dispatches" / f"{slot['opaque_slot_id']}.start.v1.json"
        if output.exists() or dispatch.exists():
            raise ValueError("Resume or a second physical attempt is forbidden")
        _assert_frozen_runtime(schedule)
        rendered = _run_render(slot, runner_call)
        frozen_prompt = root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt"
        if not frozen_prompt.is_file() or frozen_prompt.read_bytes() != rendered:
            raise ValueError("Rendered provider prompt drifted after the provider-free freeze")
        _assert_frozen_runtime(schedule)
        start = _dispatch_start(root, slot)
        result = runner_call(_command(slot, render=False), cwd=REPOSITORY, capture_output=True, text=True, check=False)
        if result.returncode:
            failure = _dispatch_failure(root, slot, start, result)
            raise ValueError(f"Singleton execution stopped ({failure['contact_classification']}); do not retry or resume this frozen screen")
        _dispatch_settlement(root, slot, start)
    return {"study_id": STUDY_ID, "provider_calls": SLOTS, "semantic_retries": 0, "resume": "forbidden"}


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["opaque_slot_id"])
    start = root / "dispatches" / f"{slot['opaque_slot_id']}.start.v1.json"
    settled = root / "dispatches" / f"{slot['opaque_slot_id']}.settled.v1.json"
    if not start.is_file() or not settled.is_file() or _load_json(settled) != {"format_version": 1, "study_id": STUDY_ID, "opaque_slot_id": slot["opaque_slot_id"], "state": "runner_command_returned_zero", "start_sha256": sha256_file(start)}:
        raise ValueError("Outer one-shot dispatch receipt is unavailable or drifted")
    manifest = _load_json(run / "run.json")
    config = manifest.get("configuration")
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping):
        raise ValueError("Terminal-sidecar v1 run manifest is unavailable")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1,
                "retry_policy": {"batch_attempts": 1}, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY,
                "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "question_ids": [LEAF_ID]}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Singleton run configuration drifted")
    config_sha = str(manifest.get("config_sha256"))
    if config_sha != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Run configuration digest drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=config_sha, batch_attempts=1, reconstruct=False, strict_v5=True, require_durable=True)
    verdicts, checkpoints, _chain = runner._load_checkpoints(run, artifact_text=str(slot["artifact_text"]), context_texts=[path.read_text(encoding="utf-8") for path in _context_paths(root, slot)], batch_attempts=1, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != LEAF_ID:
        raise ValueError("Terminal singleton checkpoint is incomplete")
    checkpoint = run / "responses" / "batch-0001.json"
    rejected = runner._rejected_records(run, 1)
    if rejected or _load_json(checkpoint).get("accepted_attempt") != 1:
        raise ValueError("A semantic retry or non-first accepted attempt is forbidden")
    reported = _load_json(checkpoint).get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider/model/reasoning receipt drifted")
    return {"opaque_slot_id": slot["opaque_slot_id"], "terminal_lifecycle": "accepted_no_semantic_retry", "accepted": True,
            "verdict": verdicts[0].get("verdict"), "receipt_sha256": sha256_file(checkpoint)}


def _derive_gate(root: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    record_path = root / "terminal-slot-records.v1.json"
    _write_or_verify(record_path, canonical_json(list(records)))
    verifier = _private_paths()[2]
    result = subprocess.run([sys.executable, str(verifier), "--assess-records", str(record_path)], cwd=_controller_root(), text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Private r3 terminal-record verifier rejected settlement evidence")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("decision") not in {"HOLDOUT_ELIGIBLE_ON_SUCCESS", "NO_GO_DSPY_ELIGIBLE_ONLY"}:
        raise ValueError("Private r3 verifier returned an invalid gate")
    return value


def _write_terminal(root: Path, settlement: Mapping[str, Any], public: Mapping[str, Any]) -> None:
    settlement_path, public_path = root / "settlement.v1.json", root / "public-aggregate.v1.json"
    _write_or_verify(settlement_path, canonical_json(settlement))
    _write_or_verify(public_path, canonical_json(public))
    sidecar = {"format": ATTEMPT_LIFECYCLE_POLICY, "study_id": STUDY_ID, "decision": settlement["decision"],
               "completed_slots": SLOTS, "planned_slots": SLOTS, "promotion": "none",
               "settlement_sha256": sha256_file(settlement_path), "public_aggregate_sha256": sha256_file(public_path)}
    _write_or_verify(root / "terminal-sidecar.v1.json", canonical_json(sidecar))


def settle(*, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    validate_package()
    root, schedule = _execution_root(), _runtime_schedule()
    if _load_json(root / "receipts" / "zero-charge-acknowledgement.v1.json") != _zero_charge_receipt():
        raise ValueError("Zero-charge acknowledgement is unavailable or drifted")
    prompts = {str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes() for slot in schedule}
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != _disclosure(schedule, prompts):
        raise ValueError("Preexecution disclosure is unavailable or drifted")
    claim = _require_execution_claim(root, schedule)
    if (root / "settlement.v1.json").exists() or (root / "public-aggregate.v1.json").exists():
        raise ValueError("Original settlement is write-once")
    records = [verifier(root, slot) for slot in schedule]
    gate = _derive_gate(root, records)
    decision = "HOLDOUT_ELIGIBLE_ON_SUCCESS" if gate["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS" else "NO_GO"
    settlement = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS,
                  "candidate_target_matches": gate["candidate_target_matches"], "candidate_control_matches": gate["candidate_control_matches"],
                  "current_target_matches": gate["current_target_matches"], "promotion": "none", "records": records,
                  "execution_claim_sha256": sha256_file(claim)}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS,
              "aggregate": {"candidate_target_matches": gate["candidate_target_matches"], "candidate_control_matches": gate["candidate_control_matches"], "current_target_matches": gate["current_target_matches"]}, "promotion": "none"}
    _write_terminal(root, settlement, public)
    return settlement
