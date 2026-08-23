"""Zero-paid, private-controller executor for the final S2 manual A/B study."""
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
STUDY_ID = "hbq-nonpoetry-scope-final-manual-v1-execution-v1"
PREDECESSOR_ID = "hbq-nonpoetry-scope-final-manual-v1"
PREDECESSOR_COMMIT = "09b403a6673645fa99efffebfbf24af7a986d190"
PREDECESSOR_TREE = "4d39e445262c20fadb9a6b4374a21e49f4db465d"
PREDECESSOR_FILES = {
    "README.md": "7e82e16972f478d2b6fbcba373f943cbe5a8d585",
    "run.py": "b2e3b058f5e95b76a325bd00589f70b61ea21d78",
    "study-contract.json": "a5c5d438f1492c57a8a2030fff2ad03bf0df1cb3",
    "study.py": "0b32bd3147acc825612aeaaf4d7d76d70bac265f",
}
PRIVATE_CONTROLLER_ROOT: Path | None = None
PRIVATE_EXECUTION_DIRECTORY = "execution-v4-stable-portable-terminal-v1"
PRIVATE_CONTRACT_NAME = "controller-contract.v1.json"
PRIVATE_CONTROLLER_SHA256 = "b6f12ade4ee05e4507080d4fc9e6d93b5ff99b2295bfa8d599d613b4e05b75eb"
LEAF_ID = "scope.passage.status"
ARMS = ("baseline", "candidate")
REPEATS = (1, 2, 3)
SLOTS, MAX_SENDS = 24, 72
ATTEMPT_LIFECYCLE_POLICY = "terminal_sidecar_v1"
BUNDLE_ID = "diagnostic.nonpoetry_scope_final_manual"
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json",
    "registry/question_index.jsonl", "registry/criterion_ownership.json", "src/hbqrs/runner.py",
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


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate frozen private artifact: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_provider_free_manifest(path: Path, value: bytes) -> None:
    if not path.exists() or path.read_bytes() == value:
        _write_or_verify(path, value)
        return
    root = _execution_root()
    responses = root / "runs"
    receipt = root / "receipts" / "provider-free-dry-run.v1.json"
    if (responses.is_dir() and any(item.is_file() for item in responses.rglob("responses/*"))) or not receipt.is_file() or _load_json(receipt).get("provider_calls") != 0:
        raise ValueError("Prepared manifest drift requires a fresh private execution root")
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
        raise ValueError("A private controller root must be supplied explicitly")
    return PRIVATE_CONTROLLER_ROOT


def _private_contract_path() -> Path:
    return _controller_root() / PRIVATE_CONTRACT_NAME


def _execution_root() -> Path:
    return _controller_root() / PRIVATE_EXECUTION_DIRECTORY


def _private_contract() -> dict[str, Any]:
    path = _private_contract_path()
    if not path.is_file() or sha256_file(path) != PRIVATE_CONTROLLER_SHA256:
        raise ValueError("Exact private controller contract is unavailable or drifted")
    value = _load_json(path)
    expected_execution = {"provider_calls_made_exact": 0, "future_calls_exact": SLOTS, "one_leaf_per_request": True}
    if value.get("study_id") != PREDECESSOR_ID or value.get("status") != "presealed_private_controller_contract" or value.get("execution") != expected_execution:
        raise ValueError("Private controller execution boundary drifted")
    fixtures, questions = value.get("fixtures"), value.get("questions")
    if not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(questions, Mapping) or set(questions) != set(ARMS):
        raise ValueError("Private controller matrix drifted")
    if any(not isinstance(row, Mapping) or not isinstance(row.get("fixture_id"), str) or not isinstance(row.get("text"), str) or not isinstance(row.get("contexts"), list) for row in fixtures):
        raise ValueError("Private fixture shape drifted")
    if any(not isinstance(questions[arm], Mapping) or questions[arm].get("id") != LEAF_ID for arm in ARMS):
        raise ValueError("Private question leaf drifted")
    return value


def validate_package() -> dict[str, Any]:
    value = contract()
    execution = {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "batch_attempts": 3, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "maximum_provider_sends": MAX_SENDS, "one_leaf_per_call": True, "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden"}
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1 or value.get("status") != "frozen_execution_successor_unexecuted":
        raise ValueError("Execution contract identity drifted")
    private_controller = {"contract_filename": PRIVATE_CONTRACT_NAME, "contract_sha256": PRIVATE_CONTROLLER_SHA256}
    if value.get("predecessor") != {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": PREDECESSOR_FILES} or value.get("private_controller") != private_controller:
        raise ValueError("Execution predecessor or private controller binding drifted")
    if value.get("execution") != execution or value.get("geometry") != {"fixtures": 4, "arms": list(ARMS), "repeats": 3, "slots": SLOTS}:
        raise ValueError("Execution route or geometry drifted")
    if value.get("public_result_policy") != "aggregate_only_after_execution" or value.get("promotion") != "none" or value.get("success_action") != "HOLDOUT_ELIGIBLE_ON_SUCCESS" or value.get("failure_action") != "NO_GO_DSPY_ELIGIBLE_ONLY":
        raise ValueError("Execution public boundary drifted")
    path = f"evaluation-results/{PREDECESSOR_ID}"
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}") != PREDECESSOR_TREE:
        raise ValueError("Predecessor tree is unavailable")
    for name, blob in PREDECESSOR_FILES.items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}/{name}") != blob:
            raise ValueError("Predecessor file binding drifted")
    controller = _private_contract()
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "private_controller_sha256": sha256_file(_private_contract_path()), "fixture_count": len(controller["fixtures"])}


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


def _arm_registry(controller: Mapping[str, Any], arm: str) -> list[dict[str, Any]]:
    modules = json.loads((REPOSITORY / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    if not isinstance(modules, list):
        raise ValueError("Canonical module registry is unavailable")
    source = next((module for module in modules if module.get("module_id") == "scope.passage"), None)
    if not isinstance(source, dict):
        raise ValueError("Canonical S2 module is unavailable")
    copied = json.loads(json.dumps(source, ensure_ascii=False))
    leaf = _find_leaf(copied)
    question = controller["questions"][arm]
    if leaf is None or any(leaf.get(key) != value for key, value in question.items() if key not in {"module_id", "text"}):
        raise ValueError("Private controller question fields do not match canonical leaf")
    leaf["text"] = question["text"]
    return [copied]


def _bundle() -> list[dict[str, Any]]:
    return [{"standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1, "title": "Final S2 manual singleton diagnostic", "module_ids": ["scope.passage"], "task_contract_domain_id": "s2", "domains": [{"domain_id": "s2", "title": "Final scope wording A/B", "points": 100.0, "components": [{"module_id": "scope.passage", "weight": 1.0, "include_question_ids": [LEAF_ID]}], "score_mode": "weighted_binary_mean"}], "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True}, "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True}}]


def build_schedule() -> list[dict[str, Any]]:
    controller = _private_contract()
    rubric_sha256 = sha256_file(REPOSITORY / "registry" / "all_modules.json")
    schedule: list[dict[str, Any]] = []
    for index, fixture in enumerate(controller["fixtures"], start=1):
        for arm in ARMS:
            for repeat in REPEATS:
                artifact_sha256 = sha256_bytes(fixture["text"].encode("utf-8"))
                condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": LEAF_ID, "arm": arm, "question_sha256": sha256_bytes(canonical_json(controller["questions"][arm])), "prompt_sha256": "0" * 64, "rubric_sha256": rubric_sha256}
                fixture_id = str(fixture["fixture_id"])
                slot = {"slot_id": f"s2fmexec-v1-f{index}-{arm}-r{repeat}", "fixture_id": fixture_id, "fixture_commitment_sha256": sha256_bytes(canonical_json(fixture)), "arm": arm, "repeat": repeat, "leaf_id": LEAF_ID, "artifact_text": fixture["text"], "contexts": fixture["contexts"], "expected_verdict": controller["expected_oracles"][fixture["state"]], "artifact_kind": fixture["artifact_kind"], "declared_scope": fixture["declared_scope"], "condition": condition}
                slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=fixture_id, artifact_sha256=artifact_sha256, condition=condition, repetition=repeat, rubric_revision="1.2.0")
                schedule.append(slot)
    if len(schedule) != SLOTS or len({slot["slot_id"] for slot in schedule}) != SLOTS or {slot["leaf_id"] for slot in schedule} != {LEAF_ID}:
        raise ValueError("Exact final-manual schedule drifted")
    return schedule


def _task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    completion_status = "excerpt" if "excerpt" in str(slot["declared_scope"]).casefold() else "unknown"
    return {"contract_version": 1, "contract_id": f"s2fmexec-{slot['fixture_id']}", "artifact_id": slot["fixture_id"], "context": {"artifact_kind": slot["artifact_kind"], "declared_scope": slot["declared_scope"], "completion_status": completion_status, "background": ["Private synthetic development screen."], "constraints": ["Use only supplied artifact and contexts."], "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "s2fmexec-v1-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for the frozen final S2 singleton diagnostic."}


def _slot_paths(root: Path, slot: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    stem = str(slot["fixture_id"])
    return root / "inputs" / f"{stem}.txt", root / "contracts" / f"{stem}.json", root / "overrides" / f"{stem}.json"


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "fixture_commitment_sha256", "arm", "repeat", "leaf_id", "condition", "logical_sample_id")}


def _runtime_bindings() -> dict[str, Any]:
    return {"runtime_head": _git("rev-parse", "HEAD"), "cwr_files": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}, "successor_files": {path: sha256_file(ROOT / path) for path in SUCCESSOR_FILES}, "private_controller_sha256": sha256_file(_private_contract_path())}


def _study_manifest(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}


def prepare() -> dict[str, Any]:
    validate_package()
    root, schedule = _execution_root(), build_schedule()
    _write_or_verify(root / "catalog" / "bundles.json", canonical_json(_bundle()))
    for arm in ARMS:
        _write_or_verify(root / "catalog" / f"{arm}-registry.json", canonical_json(_arm_registry(_private_contract(), arm)))
    for slot in schedule:
        artifact, task_path, override = _slot_paths(root, slot)
        task = _task_contract(slot)
        _write_or_verify(artifact, str(slot["artifact_text"]).encode("utf-8"))
        _write_or_verify(task_path, canonical_json(task))
        _write_or_verify(override, canonical_json(_scope_override(slot, task)))
        for index, context in enumerate(slot["contexts"], start=1):
            _write_or_verify(root / "contexts" / str(slot["fixture_id"]) / f"context-{index:02d}.txt", str(context).encode("utf-8"))
    _write_provider_free_manifest(root / "study-manifest.json", canonical_json(_study_manifest(schedule)))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": schedule}))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    return sorted((root / "contexts" / str(slot["fixture_id"])).glob("context-*.txt"))


def _command(slot: Mapping[str, Any], *, render: bool = False, resume: bool = False) -> list[str]:
    root = _execution_root()
    artifact, task, override = _slot_paths(root, slot)
    command = [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / f"{slot['arm']}-registry.json"), "--bundles", str(root / "catalog" / "bundles.json"), "render-judge" if render else "judge"]
    if render:
        command.extend(["--artifact", str(artifact)])
    else:
        command.extend([str(artifact), "--output-dir", str(root / "runs" / str(slot["slot_id"])), "--reasoning", "high", "--batch-size", "1", "--batch-attempts", "3", "--attempt-lifecycle-policy", ATTEMPT_LIFECYCLE_POLICY])
    command.extend(["--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["fixture_id"]), "--question-id", LEAF_ID, "--task-contract", str(task), "--scope-compatibility-override", str(override)])
    for context in _context_paths(root, slot):
        command.extend(["--context", str(context)])
    if resume and not render:
        command.append("--resume")
    return command


def _rendered_prompt_bytes(value: Any) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8").encode("utf-8")
        except UnicodeDecodeError:
            return value.decode("cp1252").encode("utf-8")
    raise ValueError("CWR render returned no prompt bytes")


def _runtime_schedule(root: Path, schedule: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for source in schedule:
        prompt = root / "rendered-prompts" / f"{source['slot_id']}.txt"
        if not prompt.is_file():
            raise ValueError(f"Missing rendered prompt: {source['slot_id']}")
        slot = dict(source)
        prompt_sha256 = sha256_file(prompt)
        slot["rendered_prompt_sha256"] = prompt_sha256
        condition = dict(slot["condition"])
        condition["prompt_sha256"] = prompt_sha256
        slot["condition"] = condition
        slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=slot["fixture_id"], artifact_sha256=sha256_bytes(str(slot["artifact_text"]).encode("utf-8")), condition=condition, repetition=slot["repeat"], rubric_revision="1.2.0")
        resolved.append(slot)
    return resolved


def _assert_pairwise_prompt_deltas(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    questions = _private_contract()["questions"]
    by_pair = {(str(slot["fixture_id"]), int(slot["repeat"]), str(slot["arm"])): slot for slot in schedule}
    for fixture_id, repeat in sorted({(fixture_id, repeat) for fixture_id, repeat, _arm in by_pair}):
        baseline = by_pair[(fixture_id, repeat, "baseline")]
        candidate = by_pair[(fixture_id, repeat, "candidate")]
        baseline_prompt = (root / "rendered-prompts" / f"{baseline['slot_id']}.txt").read_text(encoding="utf-8")
        candidate_prompt = (root / "rendered-prompts" / f"{candidate['slot_id']}.txt").read_text(encoding="utf-8")
        expected = baseline_prompt.replace(str(questions["baseline"]["text"]), str(questions["candidate"]["text"]))
        if expected != candidate_prompt:
            raise ValueError("A/B rendered prompts differ beyond the frozen candidate question wording")


def dry_run(*, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    prepared = prepare()
    root = _execution_root()
    for slot in build_schedule():
        done = runner_call([*_command(slot, resume=(root / "runs" / slot["slot_id"] / "run.json").is_file()), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(done, "returncode", 1):
            raise RuntimeError(f"CWR dry run stopped at {slot['slot_id']}: {getattr(done, 'stderr', '')}")
        rendered = runner_call(_command(slot, render=True), text=False, capture_output=True, check=False)
        if getattr(rendered, "returncode", 1):
            raise RuntimeError(f"CWR prompt render stopped at {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        _write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", canonical_prompt_bytes(_rendered_prompt_bytes(getattr(rendered, "stdout", None))))
    _assert_pairwise_prompt_deltas(root, build_schedule())
    schedule = _runtime_schedule(root, build_schedule())
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in schedule}))
    _write_or_verify(root / "runtime-schedule.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": schedule, "rendered_prompt_aggregate_sha256": aggregate}))
    _write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(_disclosure_receipt(schedule)))
    receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_dry_run", "provider_calls": 0, "slots": SLOTS, "rendered_prompt_aggregate_sha256": aggregate, "private_controller_sha256": sha256_file(_private_contract_path())}
    _write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json(receipt))
    return {**prepared, "rendered_prompt_aggregate_sha256": aggregate, "provider_calls": 0}


def _validated_runtime_schedule() -> list[dict[str, Any]]:
    root = _execution_root()
    stored = _load_json(root / "runtime-schedule.json")
    prepared = build_schedule()
    if _load_json(root / "study-manifest.json") != _study_manifest(prepared):
        raise ValueError("Prepared manifest or runtime binding drifted; dry-run again")
    expected = _runtime_schedule(root, prepared)
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected}))
    if stored.get("study_id") != STUDY_ID or stored.get("provider_calls") != 0 or stored.get("slots") != expected or stored.get("rendered_prompt_aggregate_sha256") != aggregate:
        raise ValueError("Prepared prompt schedule drifted; dry-run again")
    return expected


def _write_zero_charge_acknowledgement() -> None:
    root = _execution_root()
    acknowledgement = _zero_charge_receipt()
    _write_or_verify(root / "receipts" / "zero-charge-acknowledgement.v1.json", canonical_json(acknowledgement))


def _disclosure_receipt(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    root = _execution_root()
    disclosures = []
    for slot in schedule:
        artifact, task, override = _slot_paths(root, slot)
        disclosures.append({"slot_id": slot["slot_id"], "arm": slot["arm"], "repeat": slot["repeat"], "artifact": _input_record(artifact), "contexts": [_input_record(path) for path in _context_paths(root, slot)], "task_contract_sha256": sha256_file(task), "scope_compatibility_sha256": sha256_file(override), "registry_sha256": sha256_file(root / "catalog" / f"{slot['arm']}-registry.json"), "rendered_prompt_sha256": slot["rendered_prompt_sha256"]})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "preexecution_disclosure", "remote_destination": "Codex gpt-5.6-sol", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "slots": disclosures, "one_leaf_per_call": True, "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "promotion": "none"}


def _zero_charge_receipt() -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "owner_zero_incremental_charge_acknowledgement", "route": "codex", "paid_api_or_fallback_route": "forbidden", "acknowledged": True, "maximum_provider_sends": MAX_SENDS}


def execute(*, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    validate_package()
    schedule = _validated_runtime_schedule()
    disclosure = _execution_root() / "receipts" / "preexecution-disclosure.v1.json"
    if not disclosure.is_file() or _load_json(disclosure) != _disclosure_receipt(schedule):
        raise ValueError("Exact frozen preexecution disclosure is unavailable or drifted")
    _write_zero_charge_acknowledgement()
    if not resume:
        for slot in schedule:
            responses = _execution_root() / "runs" / str(slot["slot_id"]) / "responses"
            if responses.is_dir() and any(path.is_file() for path in responses.rglob("*")):
                raise ValueError("Fresh execute rejects prior provider attempts; use --resume")
    for slot in schedule:
        done = runner_call([*_command(slot, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False)
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
    run = root / "runs" / str(slot["slot_id"])
    manifest = _load_json(run / "run.json")
    config = manifest.get("configuration")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY, "artifact_id": slot["fixture_id"], "bundle_id": BUNDLE_ID, "question_ids": [LEAF_ID]}
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping) or any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Production singleton run binding drifted")
    if manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Run manifest configuration hash drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=3, reconstruct=False, strict_v5=True, require_durable=True)
    artifact, task, override = _slot_paths(root, slot)
    contexts = _context_paths(root, slot)
    prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    registry = root / "catalog" / f"{slot['arm']}-registry.json"
    if config.get("registry") != _input_record(registry) or config.get("artifact") != _input_record(artifact) or config.get("contexts") != [_input_record(path) for path in contexts] or sha256_file(prompt) != slot["rendered_prompt_sha256"]:
        raise ValueError("Registry, artifact, context, or prompt binding drifted")
    if config.get("task_contract", {}).get("sha256") != sha256_file(task) or config.get("scope_compatibility", {}).get("sha256") != sha256_file(override):
        raise ValueError("Task contract or scope override binding drifted")
    commitment = _verify_checkpoint_prompt(run, prompt)
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=str(slot["artifact_text"]), context_texts=[path.read_text(encoding="utf-8") for path in contexts], batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != LEAF_ID:
        raise ValueError("Checkpoint does not contain exactly the frozen leaf")
    reported = _load_json(run / "responses" / "batch-0001.json").get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider, model, or reasoning binding drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session.strip() or verdicts[0].get("run_id") != manifest.get("run_id"):
        raise ValueError("Accepted checkpoint run identity does not match its manifest")
    retries = len(runner._rejected_records(run, 1))
    if retries + 1 > 3:
        raise ValueError("Slot exceeded maximum cumulative attempts")
    return {"slot_id": slot["slot_id"], "arm": slot["arm"], "fixture_id": slot["fixture_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdicts[0].get("verdict"), "expected": slot["expected_verdict"], "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "run_id": verdicts[0].get("run_id"), "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "accepted_provider_call_count": 1, "rejected_retry_count": retries, "batch_attempt_count": retries + 1, **commitment}


def _write_terminal_sidecar(root: Path, settlement: Mapping[str, Any], public: Mapping[str, Any]) -> None:
    settlement_path = root / "settlement.v1.json"
    public_path = root / "public-aggregate.v1.json"
    sidecar = {"format": "terminal_sidecar_v1", "study_id": STUDY_ID, "decision": settlement["decision"], "completed_slots": settlement["completed_slots"], "planned_slots": settlement["planned_slots"], "promotion": "none", "settlement_sha256": sha256_file(settlement_path), "public_aggregate_sha256": sha256_file(public_path)}
    _write_or_verify(root / "terminal-sidecar.v1.json", canonical_json(sidecar))


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    result = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": SLOTS, "failures": failures, "promotion": "none"}
    public = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS, "promotion": "none"}
    _write_or_verify(root / "settlement.v1.json", canonical_json(result))
    _write_or_verify(root / "public-aggregate.v1.json", canonical_json(public))
    _write_terminal_sidecar(root, result, public)
    return result


def settle(*, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    root = _execution_root()
    try:
        validate_package()
        schedule = _validated_runtime_schedule()
        disclosure = root / "receipts" / "preexecution-disclosure.v1.json"
        acknowledgement = root / "receipts" / "zero-charge-acknowledgement.v1.json"
        if _load_json(disclosure) != _disclosure_receipt(schedule) or _load_json(acknowledgement) != _zero_charge_receipt():
            raise ValueError("Execution disclosure or zero-charge acknowledgement drifted")
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "runtime", "reason": str(exc)}])
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for slot in schedule:
        try:
            records.append(verifier(root, slot))
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != SLOTS:
        return _incomplete(root, len(records), failures)
    if len({row["logical_sample_id"] for row in records}) != SLOTS or len({row["session_id_sha256"] for row in records}) != SLOTS or len({row["checkpoint_chain_head_sha256"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Repeated logical, session, or checkpoint identity"}])
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for record in records:
        cells[(str(record["fixture_id"]), str(record["arm"]))].append(bool(record["correct"]))
    if len(cells) != 8 or any(len(values) != 3 for values in cells.values()):
        return _incomplete(root, len(records), [{"slot_id": "geometry", "reason": "Expected eight three-repeat private cells"}])
    fixture_ids = {str(slot["fixture_id"]) for slot in schedule}
    candidate_all = all(all(cells[(fixture_id, "candidate")]) for fixture_id in fixture_ids)
    expected_by_cell = {(str(slot["fixture_id"]), str(slot["arm"])): str(slot["expected_verdict"]) for slot in schedule}
    material_failure_candidate_no = all(all(cells[(fixture_id, "candidate")]) for fixture_id in fixture_ids if expected_by_cell[(fixture_id, "candidate")] == "NO")
    missing_evidence_candidate_cannot_assess = all(all(cells[(fixture_id, "candidate")]) for fixture_id in fixture_ids if expected_by_cell[(fixture_id, "candidate")] == "CANNOT_ASSESS")
    localized_or_inactive = [slot for slot in schedule if slot["expected_verdict"] in {"YES", "NOT_APPLICABLE"}]
    by_slot = {row["slot_id"]: row for row in records}
    no_regression = all(by_slot[slot["slot_id"]]["correct"] for slot in localized_or_inactive)
    passed = candidate_all and material_failure_candidate_no and missing_evidence_candidate_cannot_assess and no_regression
    decision = "HOLDOUT_ELIGIBLE_ON_SUCCESS" if passed else "NO_GO_DSPY_ELIGIBLE_ONLY"
    private = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "candidate_all_four_cells_3_of_3": candidate_all, "material_failure_candidate_no_3_of_3": material_failure_candidate_no, "missing_required_evidence_candidate_cannot_assess_3_of_3": missing_evidence_candidate_cannot_assess, "no_localized_or_inactive_regression": no_regression, "promotion": "none", "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "aggregate_cells": {"candidate_passed": sum(all(cells[(fixture_id, "candidate")]) for fixture_id in {slot["fixture_id"] for slot in schedule}), "total": 4}, "promotion": "none"}
    _write_or_verify(root / "settlement.v1.json", canonical_json(private))
    _write_or_verify(root / "public-aggregate.v1.json", canonical_json(public))
    _write_terminal_sidecar(root, private, public)
    return private
