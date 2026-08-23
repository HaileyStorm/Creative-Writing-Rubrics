"""Durable direct-image execution and settlement for the frozen L2 screen."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-other-lexical-overlap-ownership-v1"
STUDY_ID = "hbq-other-lexical-overlap-ownership-v1-execution-v1"
PREDECESSOR_COMMIT = "5d31848c5065a5532183635eea9c5c4dea9224d8"
PREDECESSOR_TREE = "52ec76acb527edf0897b55acd91c8563eab5f2d3"
PREDECESSOR_FILES = {
    "public-synthetic-corpus.json": "13b797dfab46c9b93bf8f37712d391742e8250a1",
    "study-contract.json": "dd942f10df96d88d8d68e5bd9f3cbb53c33ee9c9",
    "study.py": "4f587568ea6ee6e0172b0581503dd3e3d13ecdb1",
    "assets/fixture-manifest.json": "23b2edd73082882435ca0b977a43c6c0cee8501d",
    "assets/generate_visual_fixtures.py": "f19288d3ec0361fca7211fe55b40b08dbe35ccfb",
}
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
REPETITIONS, SLOTS, MAX_SENDS = 3, 216, 648
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/question_index.jsonl",
    "registry/criterion_ownership.json", "src/hbqrs/runner.py",
)


class RetryableStructuredResponseError(ValueError):
    """A completed, fully bound call returned a definitively invalid response."""


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
        raise ValueError(f"Expected JSON object: {path.name}")
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
            raise ValueError(f"Refusing to mutate immutable private artifact: {path.name}")
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
    spec = importlib.util.spec_from_file_location("l2_execution_predecessor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Frozen L2 predecessor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_package() -> dict[str, Any]:
    value = contract()
    expected_execution = {
        "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1,
        "batch_attempts": 3, "retry_semantics": "cumulative_singleton_replacement_v1", "maximum_provider_sends": MAX_SENDS, "one_leaf_per_call": True,
        "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden",
    }
    expected_image = {
        "input_contract": "codex_exec_image_flag_exact_png_bytes", "text_substitution_forbidden": True,
        "fixture_manifest_sha256": "9c564392fa5a7d0661620adf9df4f00da8505bc8a9b1811535dd9efc4483d3e8",
        "generator_sha256": "1a818209743bddf324bccffcd6011a143600c688780596c44bab1f1591ab13c9",
    }
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1 or value.get("status") != "frozen_execution_successor_unexecuted":
        raise ValueError("Execution contract identity drifted")
    if value.get("predecessor") != {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": PREDECESSOR_FILES}:
        raise ValueError("Predecessor binding drifted")
    if value.get("execution") != expected_execution or value.get("geometry") != {"artifacts": 36, "leaves": 6, "repeats": 3, "slots": SLOTS, "visual_image_slots": 72}:
        raise ValueError("Execution route or geometry drifted")
    if value.get("image_delivery") != expected_image or value.get("prompt_commitment") != "canonical_utf8_lf_v1" or value.get("public_result_policy") != "aggregate_only_after_execution" or value.get("promotion") != "none":
        raise ValueError("Image, prompt, or public policy drifted")
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-other-lexical-overlap-ownership-v1") != PREDECESSOR_TREE:
        raise ValueError("Pinned L2 predecessor tree is unavailable")
    for name, blob in PREDECESSOR_FILES.items():
        path = PREDECESSOR_ROOT / name
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-other-lexical-overlap-ownership-v1/{name}") != blob or _git("hash-object", str(path)) != blob:
            raise ValueError("Current L2 predecessor differs from pinned bytes")
    predecessor = _predecessor()
    report = predecessor.verify_package()
    if report != {"study_id": "hbq-other-lexical-overlap-ownership-v1", "status": "frozen_development_only_current_wording_screen", "provider_calls": 0, "artifacts": 36, "slots": 216, "visual_png_inputs": 6}:
        raise ValueError("Frozen L2 predecessor report drifted")
    assets = predecessor.verify_assets(predecessor.load_contract())
    if len(assets) != 6 or sha256_file(PREDECESSOR_ROOT / "assets" / "fixture-manifest.json") != expected_image["fixture_manifest_sha256"] or sha256_file(PREDECESSOR_ROOT / "assets" / "generate_visual_fixtures.py") != expected_image["generator_sha256"]:
        raise ValueError("Frozen visual fixture provenance drifted")
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "predecessor": PREDECESSOR_COMMIT, "visual_image_slots": 72}


def _runtime_bindings() -> dict[str, Any]:
    return {
        "cwr_files": {name: sha256_file(REPOSITORY / name) for name in RUNTIME_PATHS},
        "successor_files": {name: sha256_file(ROOT / name) for name in SUCCESSOR_FILES},
    }


def _artifact_by_case() -> dict[str, dict[str, Any]]:
    predecessor = _predecessor()
    return {str(value["case_id"]): dict(value) for value in predecessor.materialize_artifacts()}


def _run_id(slot_id: str, logical_id: str) -> str:
    return "l2exec-" + slot_id + "-" + sha256_bytes(logical_id.encode("utf-8"))[:20]


@lru_cache(maxsize=1)
def _schedule_template() -> tuple[bytes, ...]:
    predecessor = _predecessor()
    artifacts = _artifact_by_case()
    source_records = predecessor.source_leaf_records()
    # The frozen planner rereads the index for every singleton. Cache only its
    # already-verified in-memory source record map; no frozen source is changed.
    predecessor.source_leaf_records = lambda: source_records
    rows: list[dict[str, Any]] = []
    for original in predecessor.plan_slots():
        artifact = artifacts[str(original["case_id"])]
        request = predecessor.provider_request(str(original["slot_id"]))
        prompt = canonical_prompt_bytes(str(request["prompt"]).encode("utf-8"))
        image = request["image_inputs"]
        if bool(artifact["image_fixture"]) != bool(image):
            raise ValueError("Visual attachment schedule drifted")
        if image and len(image) != 1:
            raise ValueError("Visual slot requires exactly one PNG attachment")
        artifact_id = "l2-artifact-" + sha256_bytes(str(original["case_id"]).encode("utf-8"))[:16]
        slot = {
            "slot_id": "l2exec-v1-" + str(original["slot_id"]), "case_id": original["case_id"],
            "artifact_id": artifact_id, "artifact_name": artifact["artifact_name"],
            "artifact_kind": artifact["artifact_type"], "artifact_text": artifact["text"],
            "artifact_sha256": sha256_bytes(str(artifact["text"]).encode("utf-8")), "leaf_id": original["leaf_id"],
            "repeat": original["repeat"], "expected_verdict": original["expected_verdict"], "block_id": artifact["block_id"],
            "completion_status": artifact["completion_status"], "prompt": prompt.decode("utf-8"),
            "prompt_sha256": sha256_bytes(prompt), "image_input": dict(image[0]) if image else None,
        }
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": slot["leaf_id"], "prompt_sha256": slot["prompt_sha256"], "rubric_sha256": sha256_file(REPOSITORY / "registry" / "all_modules.json")}
        slot["condition"] = condition
        slot["logical_sample_id"] = logical_sample_id(study_id=STUDY_ID, artifact_id=slot["artifact_id"], artifact_sha256=slot["artifact_sha256"], condition=condition, repetition=int(slot["repeat"]), rubric_revision="1.2.0")
        slot["run_id"] = _run_id(str(slot["slot_id"]), str(slot["logical_sample_id"]))
        rows.append(slot)
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS or len({row["run_id"] for row in rows}) != SLOTS or len({row["artifact_id"] for row in rows}) != 36 or len({(row["case_id"], row["artifact_id"]) for row in rows}) != 36 or sum(row["image_input"] is not None for row in rows) != 72:
        raise ValueError("Exact L2 execution schedule drifted")
    return tuple(canonical_json(row) for row in rows)


def build_schedule() -> list[dict[str, Any]]:
    validate_package()
    return [json.loads(value.decode("utf-8")) for value in _schedule_template()]


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "case_id", "artifact_id", "artifact_name", "artifact_kind", "artifact_sha256", "leaf_id", "repeat", "block_id", "completion_status", "prompt_sha256", "condition", "logical_sample_id", "run_id")}


def _private_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return dict(slot)


def _input_path(root: Path, slot: Mapping[str, Any]) -> Path:
    suffix = ".png" if slot["image_input"] else ".txt"
    return root / "inputs" / (str(slot["artifact_id"]) + suffix)


def _attachment_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"name": path.name, "bytes": len(data), "sha256": sha256_bytes(data), "mime_type": "image/png"}


def prepare(private_root: str | Path) -> dict[str, Any]:
    root = _external_root(private_root)
    schedule = build_schedule()
    predecessor = _predecessor()
    fixtures = predecessor.verified_assets()
    by_artifact: dict[str, Mapping[str, Any]] = {}
    for slot in schedule:
        destination = _input_path(root, slot)
        if slot["image_input"]:
            image = dict(slot["image_input"])
            fixture = fixtures.get(Path(str(image["path"])).stem)
            if fixture is None:
                raise ValueError("Image fixture lookup drifted")
            source = PREDECESSOR_ROOT / str(image["path"])
            _write_or_verify(destination, source.read_bytes())
            if _attachment_record(destination) != {"name": destination.name, "bytes": image["bytes"] if "bytes" in image else source.stat().st_size, "sha256": image["sha256"], "mime_type": "image/png"}:
                raise ValueError("Prepared PNG attachment bytes drifted")
        else:
            _write_or_verify(destination, str(slot["artifact_text"]).encode("utf-8"))
        _write_or_verify(root / "rendered-prompts" / (str(slot["slot_id"]) + ".txt"), canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")))
        prior = by_artifact.setdefault(str(slot["artifact_id"]), slot)
        if prior["case_id"] != slot["case_id"] or prior["artifact_sha256"] != slot["artifact_sha256"] or prior["image_input"] != slot["image_input"]:
            raise ValueError("Artifact identity is inconsistent across repeats")
    if len(by_artifact) != 36:
        raise ValueError("Execution must preserve exactly one artifact identity per case")
    manifest = {
        "format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"),
        "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule],
    }
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": [_private_slot(slot) for slot in schedule]}))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0, "visual_image_slots": 72}


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, attempt: int = 1) -> list[str]:
    root = _external_root(private_root)
    attempt_dir = _attempt_dir(root, slot, attempt)
    command = [
        "codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config",
        "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "code_mode_host", "--disable", "hooks",
        "--disable", "memories", "--disable", "plugins", "--disable", "multi_agent", "--disable", "apps",
        "--disable", "browser_use", "--disable", "computer_use", "--disable", "image_generation", "--disable", "view_image",
        "--disable", "workspace_dependencies", "--disable", "skill_search", "--disable", "tool_suggest",
        "-c", 'web_search="disabled"', "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
        "--model", "gpt-5.6-sol", "-c", 'model_reasoning_effort="high"', "--output-schema",
        str(REPOSITORY / "schema" / "hbq_judge_response.schema.json"), "--output-last-message",
        str(_response_path(root, slot, attempt)), "--cd", str(attempt_dir),
    ]
    if slot["image_input"]:
        command.extend(["--image", str(_input_path(root, slot))])
    command.append("-")
    return command


def dry_run(private_root: str | Path) -> dict[str, Any]:
    prepared = prepare(private_root)
    root = _external_root(private_root)
    schedule = build_schedule()
    for slot in schedule:
        prompt_path = root / "rendered-prompts" / (str(slot["slot_id"]) + ".txt")
        if prompt_path.read_bytes() != canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")):
            raise ValueError("Frozen prompt bytes drifted")
        if slot["image_input"]:
            attachment = _attachment_record(_input_path(root, slot))
            if attachment["sha256"] != slot["image_input"]["sha256"] or attachment["mime_type"] != "image/png":
                raise ValueError("Visual PNG attachment commitment drifted")
    hashes = {str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}
    aggregate = sha256_bytes(canonical_json(hashes))
    _write_summary(root / "runtime-schedule.json", {"format_version": 1, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": aggregate})
    report = {"mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS, "visual_image_slots": 72, "first_command": command_for(schedule[0], root), "last_command": command_for(schedule[-1], root), "rendered_prompt_aggregate_sha256": aggregate}
    _write_summary(root / "dry-run.json", report)
    return {**prepared, **report}


def render_plan(private_root: str | Path) -> dict[str, Any]:
    report = dry_run(private_root)
    root = _external_root(private_root)
    schedule = build_schedule()
    rendered = {str(slot["slot_id"]): {"prompt_sha256": slot["prompt_sha256"], "image_attachment": _attachment_record(_input_path(root, slot)) if slot["image_input"] else None} for slot in schedule}
    value = {"mode": "render_plan", "provider_calls": 0, "planned_slots": SLOTS, "rendered_slots": rendered}
    _write_summary(root / "render-plan.json", value)
    return {**report, **value}


def _validated_schedule(root: Path) -> list[dict[str, Any]]:
    validate_package()
    manifest = _load_json(root / "study-manifest.json")
    if manifest.get("runtime_bindings") != _runtime_bindings():
        raise ValueError("CWR runtime or successor bindings drifted; dry-run again")
    stored = _load_json(root / "runtime-schedule.json")
    expected = [_public_slot(slot) for slot in build_schedule()]
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["prompt_sha256"] for slot in expected}))
    if stored.get("slots") != expected or stored.get("rendered_prompt_aggregate_sha256") != aggregate:
        raise ValueError("Prepared execution schedule drifted; dry-run again")
    return build_schedule()


def _attempt_dir(root: Path, slot: Mapping[str, Any], attempt: int) -> Path:
    if attempt not in range(1, 4):
        raise ValueError("Attempt number is outside the frozen cumulative limit")
    return root / "runs" / str(slot["slot_id"]) / "attempts" / f"attempt-{attempt:02d}"


def _intent_path(root: Path, slot: Mapping[str, Any], attempt: int) -> Path:
    return _attempt_dir(root, slot, attempt) / "intent.json"


def _receipt_path(root: Path, slot: Mapping[str, Any], attempt: int) -> Path:
    return _attempt_dir(root, slot, attempt) / "receipt.json"


def _outcome_path(root: Path, slot: Mapping[str, Any], attempt: int) -> Path:
    return _attempt_dir(root, slot, attempt) / "outcome.json"


def _response_path(root: Path, slot: Mapping[str, Any], attempt: int) -> Path:
    return _attempt_dir(root, slot, attempt) / "responses" / "batch-0001.output.json"


def _reported_settings(stderr: Any) -> dict[str, str]:
    reported: dict[str, str] = {}
    labels = {"provider": "provider", "model": "model", "reasoning effort": "reasoning_effort"}
    for line in str(stderr).splitlines():
        if line.strip().casefold() == "user":
            break
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        key = labels.get(label.strip().casefold())
        if key:
            reported[key] = value.strip()
    return reported


def _attempt(root: Path, slot: Mapping[str, Any], attempt: int, runner_call: Callable[..., Any]) -> dict[str, Any] | None:
    attempt_dir = _attempt_dir(root, slot, attempt)
    response = _response_path(root, slot, attempt)
    if response.exists() or _receipt_path(root, slot, attempt).exists() or _outcome_path(root, slot, attempt).exists():
        raise ValueError("Existing response or receipt must be reconciled before dispatch")
    image_record = _attachment_record(_input_path(root, slot)) if slot["image_input"] else None
    if slot["image_input"] and (image_record is None or image_record["sha256"] != slot["image_input"]["sha256"]):
        raise ValueError("Refusing image dispatch with unbound PNG bytes")
    prompt = canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8"))
    intent = {
        "format_version": 1, "study_id": STUDY_ID, "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"],
        "run_id": slot["run_id"], "attempt": attempt, "attempt_id": f"{slot['run_id']}-attempt-{attempt:02d}", "command": command_for(slot, root, attempt=attempt), "prompt_sha256": sha256_bytes(prompt),
        "attachment": image_record, "maximum_attempts": 3, "state": "contact_started",
    }
    _write_or_verify(_intent_path(root, slot, attempt), canonical_json(intent))
    response.parent.mkdir(parents=True, exist_ok=True)
    done = runner_call(command_for(slot, root, attempt=attempt), input=str(slot["prompt"]), text=True, encoding="utf-8", capture_output=True, check=False)
    stdout = getattr(done, "stdout", "")
    stderr = getattr(done, "stderr", "")
    receipt = {
        "format_version": 1, "study_id": STUDY_ID, "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"],
        "run_id": slot["run_id"], "attempt": attempt, "attempt_id": intent["attempt_id"], "command_sha256": sha256_bytes(canonical_json(command_for(slot, root, attempt=attempt))),
        "returncode": getattr(done, "returncode", None), "stdout_sha256": sha256_bytes(str(stdout).encode("utf-8")),
        "stderr_sha256": sha256_bytes(str(stderr).encode("utf-8")), "reported": _reported_settings(stderr), "attachment": image_record,
    }
    _write_or_verify(_receipt_path(root, slot, attempt), canonical_json(receipt))
    if getattr(done, "returncode", 1) != 0 or not response.is_file():
        raise RuntimeError(f"Execution requires reconciliation at {slot['slot_id']} attempt {attempt}; it will not resend automatically")
    try:
        record = _verify_attempt(root, slot, attempt)
    except RetryableStructuredResponseError as exc:
        _write_or_verify(_outcome_path(root, slot, attempt), canonical_json({"format_version": 1, "study_id": STUDY_ID, "slot_id": slot["slot_id"], "attempt": attempt, "attempt_id": intent["attempt_id"], "state": "rejected", "reason": str(exc)}))
        return None
    _write_or_verify(_outcome_path(root, slot, attempt), canonical_json({"format_version": 1, "study_id": STUDY_ID, "slot_id": slot["slot_id"], "attempt": attempt, "attempt_id": intent["attempt_id"], "state": "accepted", "response_sha256": record["response_sha256"]}))
    return record


def execute(private_root: str | Path, *, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    root = _external_root(private_root)
    schedule = _validated_schedule(root)
    completed = 0
    sends = sum(_receipt_path(root, slot, attempt).is_file() for slot in schedule for attempt in range(1, 4))
    if sends > MAX_SENDS:
        raise ValueError("Existing provider receipts exceed the frozen cumulative send cap")
    for slot in schedule:
        accepted = _accepted_slot(root, slot)
        if accepted is not None:
            completed += 1
            continue
        attempt = _next_attempt(root, slot)
        while attempt <= 3:
            if sends >= MAX_SENDS:
                raise ValueError("Frozen cumulative provider send cap reached")
            result = _attempt(root, slot, attempt, runner_call)
            sends += 1
            if result is not None:
                completed += 1
                break
            attempt += 1
        else:
            raise ValueError(f"Slot {slot['slot_id']} exhausted its three cumulative attempts")
    return {"mode": "resume" if resume else "execute", "completed_slots": completed, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "billing": "owner_attested_subscription_zero_incremental_charge"}


def _validate_response(slot: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    errors = sorted(Draft202012Validator(_load_json(REPOSITORY / "schema" / "hbq_judge_response.schema.json")).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise ValueError("Response violates strict judge schema: " + errors[0].message)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("verdicts"), list) or len(payload["verdicts"]) != 1:
        raise ValueError("Response must contain exactly one singleton verdict")
    repair_audit: list[dict[str, Any]] = []
    normalized = runner._normalize_batch(payload, expected_ids=[str(slot["leaf_id"])], artifact_id=str(slot["artifact_id"]), bundle_id="l2-lexical-overlap-development", judge_id="codex:gpt-5.6-sol", run_id=str(slot["run_id"]), artifact_text=str(slot["artifact_text"]), context_texts=[], normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=repair_audit)
    if len(normalized) != 1 or normalized[0].get("question_id") != slot["leaf_id"] or normalized[0].get("run_id") != slot["run_id"]:
        raise ValueError("Normalized singleton identity drifted")
    runner._validate_typed_checkpoint_evidence(normalized[0].get("evidence"), question_id=str(slot["leaf_id"]))
    if not slot["image_input"]:
        runner._validate_exact_quotes(normalized[0]["evidence"], artifact_text=str(slot["artifact_text"]), context_texts=[], question_id=str(slot["leaf_id"]))
    return {"verdict": normalized[0], "normalization_audit": repair_audit}


def _verify_attempt(root: Path, slot: Mapping[str, Any], attempt: int) -> dict[str, Any]:
    intent, receipt = _load_json(_intent_path(root, slot, attempt)), _load_json(_receipt_path(root, slot, attempt))
    response = _response_path(root, slot, attempt)
    attempt_id = f"{slot['run_id']}-attempt-{attempt:02d}"
    if intent.get("state") != "contact_started" or intent.get("run_id") != slot["run_id"] or intent.get("attempt") != attempt or intent.get("attempt_id") != attempt_id or receipt.get("returncode") != 0 or receipt.get("attempt_id") != attempt_id or not response.is_file():
        raise ValueError("Attempt intent, receipt, or output is incomplete")
    if receipt.get("reported") != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Codex provider/model/reasoning report is absent or drifted")
    if intent.get("command") != command_for(slot, root, attempt=attempt) or receipt.get("command_sha256") != sha256_bytes(canonical_json(command_for(slot, root, attempt=attempt))):
        raise ValueError("Codex command binding drifted")
    prompt = root / "rendered-prompts" / (str(slot["slot_id"]) + ".txt")
    if prompt.read_bytes() != canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")) or intent.get("prompt_sha256") != slot["prompt_sha256"]:
        raise ValueError("Frozen prompt binding drifted")
    if slot["image_input"]:
        attachment = _attachment_record(_input_path(root, slot))
        if receipt.get("attachment") != attachment or intent.get("attachment") != attachment or attachment["sha256"] != slot["image_input"]["sha256"]:
            raise ValueError("Exact PNG attachment binding drifted")
    elif intent.get("attachment") is not None or receipt.get("attachment") is not None:
        raise ValueError("Text slot unexpectedly carries an attachment")
    try:
        payload = json.loads(response.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetryableStructuredResponseError("Structured Codex response is malformed") from exc
    try:
        validated = _validate_response(slot, payload)
    except (ValueError, runner.HBQError) as exc:
        raise RetryableStructuredResponseError("Structured Codex response is invalid") from exc
    verdict = validated["verdict"]
    return {"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdict["verdict"], "expected": slot["expected_verdict"], "correct": verdict["verdict"] == slot["expected_verdict"], "run_id": slot["run_id"], "attempt": attempt, "attempt_id": attempt_id, "response_sha256": sha256_file(response), "command_sha256": receipt["command_sha256"], "attachment_sha256": receipt["attachment"]["sha256"] if receipt.get("attachment") else None, "evidence": verdict["evidence"], "normalization_audit": validated["normalization_audit"]}


def _next_attempt(root: Path, slot: Mapping[str, Any]) -> int:
    for attempt in range(1, 4):
        intent, receipt, outcome = _intent_path(root, slot, attempt), _receipt_path(root, slot, attempt), _outcome_path(root, slot, attempt)
        if not intent.exists() and not receipt.exists() and not outcome.exists() and not _response_path(root, slot, attempt).exists():
            return attempt
        if not intent.exists() or not receipt.exists() or not outcome.exists():
            raise ValueError(f"Slot {slot['slot_id']} attempt {attempt} is ambiguous; reconcile before resume")
        state = _load_json(outcome).get("state")
        if state == "accepted":
            return attempt
        if state != "rejected":
            raise ValueError(f"Slot {slot['slot_id']} attempt {attempt} outcome is malformed")
    return 4


def _accepted_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any] | None:
    outcomes: list[tuple[int, str]] = []
    for attempt in range(1, 4):
        outcome = _outcome_path(root, slot, attempt)
        if not outcome.exists():
            continue
        value = _load_json(outcome)
        state = value.get("state")
        if state not in {"accepted", "rejected"}:
            raise ValueError("Attempt outcome is malformed")
        outcomes.append((attempt, state))
    accepted = [attempt for attempt, state in outcomes if state == "accepted"]
    if not accepted:
        return None
    if [attempt for attempt, _ in outcomes] != list(range(1, len(outcomes) + 1)) or len(accepted) != 1 or accepted[0] != outcomes[-1][0] or any(state != "rejected" for _, state in outcomes[:-1]):
        raise ValueError("Accepted logical slot has invalid attempt history")
    record = _verify_attempt(root, slot, accepted[0])
    record.update({"accepted_provider_call_count": sum(state == "accepted" for _, state in outcomes), "rejected_retry_count": sum(state == "rejected" for _, state in outcomes), "batch_attempt_count": len(outcomes)})
    return record


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    settlement = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": SLOTS, "failures": failures}
    _write_summary(root / "settlement.json", settlement)
    _write_summary(root / "public-aggregate.json", {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS})
    return settlement


def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    root = _external_root(private_root)
    try:
        schedule = _validated_schedule(root)
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "schedule", "reason": str(exc)}])
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for slot in schedule:
        try:
            record = _accepted_slot(root, slot) if verifier is None else verifier(root, slot)
            if record is None:
                raise ValueError("No accepted logical vote exists")
            if record.get("slot_id") != slot["slot_id"] or record.get("verdict") not in VERDICTS or record.get("run_id") != slot["run_id"]:
                raise ValueError("Verifier returned malformed singleton identity")
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != SLOTS or len({row["slot_id"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), failures or [{"slot_id": "identity", "reason": "duplicate logical slot"}])
    if len({row["logical_sample_id"] for row in records}) != SLOTS or len({row["run_id"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "logical or run identity repeated"}])
    visual = [row for row in records if next(item for item in schedule if item["slot_id"] == row["slot_id"])["image_input"]]
    if len(visual) != 72 or len({row["attachment_sha256"] for row in visual}) != 6 or any(row["attachment_sha256"] is None for row in visual):
        return _incomplete(root, len(records), [{"slot_id": "images", "reason": "visual attachment receipts are incomplete"}])
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    counts: dict[str, Counter[str]] = {leaf: Counter() for leaf in _predecessor().BLOCK_LEAVES.values() for leaf in leaf}
    by_slot = {str(slot["slot_id"]): slot for slot in schedule}
    for row in records:
        slot = by_slot[str(row["slot_id"])]
        cells[(str(slot["case_id"]), str(slot["leaf_id"]))].append(bool(row["correct"]))
        counts[str(slot["leaf_id"])][str(row["verdict"])] += 1
    states = {(str(slot["case_id"]), str(slot["leaf_id"])): str(slot["expected_verdict"]) for slot in schedule}
    per_cell = {f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": states[key]} for index, (key, values) in enumerate(cells.items(), start=1)}
    scored = [value for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE"]
    controls = [value for value in per_cell.values() if value["expected_state"] == "NOT_APPLICABLE"]
    decision = "PASS_NO_CHANGE" if all(value["passed"] for value in scored) else "DIAGNOSTIC_FAIL"
    accuracy = {state: {"correct": sum(row["correct"] for row in records if row["expected"] == state), "denominator": sum(row["expected"] == state for row in records)} for state in sorted(VERDICTS)}
    four_state = {leaf: {state: counts[leaf][state] for state in sorted(VERDICTS)} for leaf in sorted(counts)}
    settlement = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "per_cell_three_of_three": per_cell, "canonical_four_state_counts": four_state, "accuracy": accuracy, "visual_attachment_slots": 72, "promotion": "none", "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "scored_cells": {"passed": sum(value["passed"] for value in scored), "total": len(scored)}, "not_applicable_diagnostic_cells": {"matched": sum(value["passed"] for value in controls), "total": len(controls)}, "canonical_four_state_counts": four_state, "visual_attachment_slots": 72, "promotion": "none"}
    _write_summary(root / "settlement.json", settlement)
    _write_summary(root / "public-aggregate.json", public)
    return settlement


def main() -> None:
    import argparse

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
