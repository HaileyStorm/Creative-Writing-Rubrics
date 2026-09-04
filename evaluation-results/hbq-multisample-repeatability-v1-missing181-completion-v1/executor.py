"""Default-off, one-shot completion for the V7-settled missing seq181 cell."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
import types
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-multisample-repeatability-v1-missing181-completion-v1"
STATUS = "PREPARED_DEFAULT_OFF"
EVENT = {"sequence": 181, "item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "repetition": 1}
SETTLEMENT_SHA256 = "258ccbda1fdf619bffb8728dc55f17c47f5658028100a9b8b41e19d7812a2b52"
EXPECTED_V8_EXECUTOR_SHA256 = "515ea015074883be64b64ec63b832c00c8452e65cd1786dd9ba81dc23b92b2d6"
EXPECTED_GUARD_SHA256 = "fb20800c50dd374d35a6314b2c7889bc1e523cb3ab4346d13f2d27dbaa92b4c8"
EXPECTED_GUARD_STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1"
EXPECTED_SOURCE_CONTRACT_SHA256 = "5fb06e5a4775ecfe1cee10132e52100733c7e765e8eae9865374bb23f1addddd"
EXPECTED_QUESTION_IDS_SHA256 = "4c4789fc9ab1ddb3ca7893d98867e69b866cd292de73f6fb4b987cf9a8326ebd"
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
GUARD_PATH = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1" / "guard.py"
BINDING, DISCLOSURE, ACKNOWLEDGEMENT, LOCK, CLAIM, RECEIPT, OVERRIDES = ("completion-binding.json", "preflight-disclosure.json", "disclosure-acknowledgement.json", "completion.lock", "exclusive-dispatch-claim.json", "normal-receipt.json", "scope-compatibility-overrides")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _is_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _plain(path: Path, *, missing_leaf: bool = False) -> Path:
    candidate = Path(path).absolute()
    for part in [*reversed(candidate.parents), candidate]:
        if not part.exists():
            if missing_leaf and part == candidate:
                continue
            raise ValueError(f"Required path is missing: {part}")
        if _is_reparse(part):
            raise ValueError(f"Reparse points are forbidden: {part}")
    return candidate


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_plain(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical(dict(value)) + b"\n"
    try:
        with _plain(path, missing_leaf=True).open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Immutable evidence already exists: {path}") from exc


def _write_override(path: Path, value: Mapping[str, Any]) -> None:
    """Match the pinned V8 scope-override byte commitment exactly."""
    payload = (json.dumps(dict(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    try:
        with _plain(path, missing_leaf=True).open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Immutable override already exists: {path}") from exc


@contextmanager
def _lock(root: Path):
    path = _plain(root / LOCK)
    if not path.is_file() or path.stat().st_size != 1:
        raise ValueError("Completion lock is malformed")
    with path.open("r+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_guard() -> Any:
    if sha(GUARD_PATH) != EXPECTED_GUARD_SHA256:
        raise ValueError("Pinned V8 guard SHA-256 drifted")
    module = types.ModuleType("missing181_pinned_v8_guard")
    module.__file__ = str(_plain(GUARD_PATH))
    exec(compile(GUARD_PATH.read_bytes(), str(GUARD_PATH), "exec"), module.__dict__)  # noqa: S102
    if module.STUDY_ID != EXPECTED_GUARD_STUDY_ID:
        raise ValueError("Pinned V8 guard study identity drifted")
    return module


def _load_runtime(v8_runtime_root: Path) -> tuple[Any, Any, Path, Path]:
    guard = _load_guard()
    runtime, executor = guard._canonical_runtime(Path(v8_runtime_root))
    if sha(executor) != EXPECTED_V8_EXECUTOR_SHA256:
        raise ValueError("Pinned frozen V8 executor SHA-256 drifted")
    return guard, guard._load_v8(executor), runtime, executor


def _load_pinned_runner(v8: Any, binding: Mapping[str, Any]) -> Any:
    projection = binding.get("source", {}).get("runtime_projection")
    if not isinstance(projection, Mapping):
        raise TypeError("Frozen source runtime projection is malformed")
    _assert_frozen_hbq_imports(v8, projection)
    files = projection.get("files") if isinstance(projection, Mapping) else None
    relative = v8.SUCCESSOR_RUNNER.relative_to(v8.REPO).as_posix()
    expected = [item for item in files or [] if isinstance(item, Mapping) and item.get("path") == relative]
    if len(expected) != 1 or v8._runtime_file(v8.SUCCESSOR_RUNNER, require_tracked=False) != expected[0]:
        raise ValueError("Pinned successor runner runtime projection drifted")
    runner = v8._load_successor_runner()
    identity = runner.runtime_identity()
    if not isinstance(identity, Mapping) or identity.get("path") != v8.SUCCESSOR_RUNNER.name or identity.get("bytes") != expected[0].get("bytes") or identity.get("sha256") != expected[0].get("sha256") or not callable(getattr(runner, "dispatch_event", None)):
        raise ValueError("Loaded successor runner identity drifted")
    return runner


def _source_provider_policy(frozen: Mapping[str, Any], profile: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = frozen.get("contract")
    provider = contract.get("provider") if isinstance(contract, Mapping) else None
    if not isinstance(provider, Mapping) or _provider_identity(provider) != _provider_identity(profile):
        raise ValueError("Original frozen provider identity does not match the pinned V8 profile")
    required = {"kind": "codex_cli", "fresh_sessions": True, "tools": "disabled", "seed_control": "unsupported", "temperature_control": "unsupported"}
    if any(provider.get(key) != value for key, value in required.items()):
        raise ValueError("Original frozen provider policy is not the required local Codex policy")
    return provider


def _assert_frozen_hbq_imports(v8: Any, projection: Mapping[str, Any]) -> None:
    """Reject ambient HBQ modules; this controller never substitutes a checkout import."""
    source_root = _plain(v8.REPO / "src")
    package_root = _plain(source_root / "hbqrs")
    for name, module in tuple(sys.modules.items()):
        if name == "hbqrs" or name.startswith("hbqrs."):
            location = getattr(module, "__file__", None)
            if not isinstance(location, str) or package_root not in _plain(Path(location)).parents:
                raise ValueError("An ambient hbqrs import blocks use of the frozen V8 runtime")
    spec = importlib.util.find_spec("hbqrs")
    if spec is None or not isinstance(spec.origin, str) or _plain(Path(spec.origin)) != package_root / "__init__.py":
        raise ValueError("PYTHONPATH does not resolve hbqrs from the frozen V8 runtime")
    files = projection.get("files") if isinstance(projection, Mapping) else None
    for relative in ("src/hbqrs/__init__.py", "src/hbqrs/core.py", "src/hbqrs/paths.py", "src/hbqrs/runner.py"):
        expected = [row for row in files or [] if isinstance(row, Mapping) and row.get("path") == relative]
        path = _plain(v8.REPO / relative)
        if len(expected) != 1 or expected[0].get("bytes") != path.stat().st_size or expected[0].get("sha256") != sha(path):
            raise ValueError("Frozen HBQ import dependency does not match the source runtime projection")
    v8._load_hbq_runner()
    for module_name, relative in {"hbqrs": "src/hbqrs/__init__.py", "hbqrs.core": "src/hbqrs/core.py", "hbqrs.paths": "src/hbqrs/paths.py", "hbqrs.runner": "src/hbqrs/runner.py"}.items():
        module = sys.modules.get(module_name)
        location = getattr(module, "__file__", None)
        if not isinstance(location, str) or _plain(Path(location)) != _plain(v8.REPO / relative):
            raise ValueError("Invoked HBQ module did not load from the frozen V8 runtime")


def _validate_original_binding(source: Path, frozen: Mapping[str, Any]) -> None:
    if sha(source / "frozen-run-contract.json") != EXPECTED_SOURCE_CONTRACT_SHA256:
        raise ValueError("Original frozen contract is not the exact seq181 source binding")
    samples = frozen.get("samples")
    matches = [row for row in samples or [] if isinstance(row, Mapping) and row.get("item_id") == EVENT["item_id"]]
    if len(matches) != 1:
        raise ValueError("Original frozen contract does not contain exactly one hanna-523 sample")
    sample = matches[0]
    if sample.get("question_count") != 179 or sample.get("question_id_sequence_sha256") != EXPECTED_QUESTION_IDS_SHA256:
        raise ValueError("Original hanna-523 question-sequence binding drifted")
    inputs = sample.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {"source.md", "prompt.md", "task-contract.json", "human-ratings.json"}:
        raise ValueError("Original hanna-523 declared inputs are malformed")
    folder = source / "inputs" / EVENT["item_id"]
    for name, record in inputs.items():
        if not isinstance(record, Mapping) or record.get("path") != name or not isinstance(record.get("bytes"), int) or not isinstance(record.get("sha256"), str):
            raise ValueError("Original hanna-523 declared input record is malformed")
        path = _plain(folder / name)
        if not path.is_file() or path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
            raise ValueError("Original hanna-523 declared input bytes drifted")
    schedule = frozen.get("schedule")
    if not isinstance(schedule, list) or len(schedule) <= 180 or schedule[180] != {"item_id": EVENT["item_id"], "arm_id": EVENT["arm_id"], "repetition": EVENT["repetition"], "position": 1}:
        raise ValueError("Original frozen schedule index 180 is not logical seq181")
    lineage = frozen.get("question_sequence_lineage")
    rows = [row for row in lineage or [] if isinstance(row, Mapping) and row.get("item_id") == EVENT["item_id"]]
    if rows != [{"item_id": EVENT["item_id"], "question_count": 179, "question_id_sequence_sha256": EXPECTED_QUESTION_IDS_SHA256}]:
        raise ValueError("Original frozen question lineage does not uniquely bind hanna-523")


def _event_and_questions(v8: Any, source: Path, frozen: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    disclosure = v8._event_disclosure(source, EVENT, frozen)
    overrides = v8._scope_override_records(source, [dict(EVENT)], frozen)
    payloads = disclosure.get("payload", {}).get("provider_payloads") if isinstance(disclosure.get("payload"), Mapping) else None
    if not isinstance(payloads, list) or len(payloads) != 6:
        raise ValueError("Missing181 disclosure does not bind six batch32 payloads")
    question_ids: list[str] = []
    for number, payload in enumerate(payloads, 1):
        ids = payload.get("question_ids") if isinstance(payload, Mapping) else None
        if payload.get("batch") != number or not isinstance(ids, list) or not 1 <= len(ids) <= 32 or not all(isinstance(item, str) and item for item in ids):
            raise ValueError("Missing181 disclosed HBQ batches are malformed")
        question_ids.extend(ids)
    if len(question_ids) != 179 or len(question_ids) != len(set(question_ids)) or hashlib.sha256(canonical(question_ids)).hexdigest() != EXPECTED_QUESTION_IDS_SHA256:
        raise ValueError("Missing181 does not bind the frozen 179-question sequence")
    if len(overrides) != 1 or overrides[0].get("artifact_id") != EVENT["item_id"] or overrides[0].get("arm_id") != EVENT["arm_id"]:
        raise ValueError("Missing181 exact cohort compatibility override is unavailable")
    return disclosure, overrides, question_ids


def _settlement(path: Path) -> dict[str, Any]:
    settlement = _json(path)
    row = settlement.get("settled_sequence")
    if sha(path) != SETTLEMENT_SHA256 or settlement.get("kind") != "v6_sequence_181_precontact_settlement" or settlement.get("study_id") != "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v7" or settlement.get("not_provider_attestation") is not True or not isinstance(row, Mapping) or any(row.get(key) != value for key, value in EVENT.items()) or row.get("provider_contacts") != 0:
        raise ValueError("V7 forensic settlement is not the exact immutable zero-contact seq181 evidence")
    return settlement


def _expected_ack(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "disclosure_sha256": binding["disclosure_sha256"], "acknowledged": True}


def _provider_identity(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {key: profile[key] for key in ("provider", "model", "reasoning")}


def _binding(root: Path) -> dict[str, Any]:
    root = _plain(root)
    allowed = {BINDING, DISCLOSURE, LOCK, OVERRIDES, ACKNOWLEDGEMENT, CLAIM, RECEIPT, "runs"}
    entries = {item.name for item in root.iterdir()}
    if not {BINDING, DISCLOSURE, LOCK, OVERRIDES}.issubset(entries) or entries - allowed:
        raise ValueError("Controller root has unexpected or missing entries")
    value = _json(root / BINDING)
    if value.get("study_id") != STUDY_ID or value.get("status") != STATUS or value.get("event") != EVENT or value.get("controller_root") != str(root) or sha(root / DISCLOSURE) != value.get("disclosure_sha256"):
        raise ValueError("Completion binding or disclosure drifted")
    return value


def _precontact(root: Path, binding: Mapping[str, Any], evidence: Path) -> tuple[Any, Any, Path, dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    historical = binding.get("v7_zero_contact_settlement")
    if not isinstance(historical, Mapping) or historical.get("sha256") != SETTLEMENT_SHA256:
        raise ValueError("Missing181 historical settlement binding drifted")
    _settlement(Path(str(historical.get("path", ""))))
    _guard, v8, runtime, executor = _load_runtime(Path(str(binding["runtime"]["root"])))
    if str(runtime) != binding["runtime"].get("root") or str(executor) != binding["runtime"].get("executor") or sha(executor) != binding["runtime"].get("executor_sha256") or v8.contract().get("study_id") != binding["runtime"].get("study_id"):
        raise ValueError("Frozen V8 runtime identity drifted")
    source = v8._external(Path(str(binding["source"]["root"])))
    if sha(source / "frozen-run-contract.json") != EXPECTED_SOURCE_CONTRACT_SHA256 or binding["source"].get("frozen_contract_sha256") != EXPECTED_SOURCE_CONTRACT_SHA256:
        raise ValueError("Original frozen source contract drifted")
    frozen = v8.read_json(source / "frozen-run-contract.json")
    _validate_original_binding(source, frozen)
    if v8._runtime_projection(frozen) != binding["source"].get("runtime_projection"):
        raise ValueError("Original source frozen runtime no longer matches the pinned V8 runtime")
    if v8.contract().get("provider") != binding.get("profile") or binding["profile"].get("paid_api") is not False or binding["profile"].get("human_judgment") is not False:
        raise ValueError("Pinned source or runtime provider profile drifted")
    source_policy = _source_provider_policy(frozen, binding["profile"])
    if hashlib.sha256(canonical(source_policy)).hexdigest() != binding["source"].get("provider_policy_sha256"):
        raise ValueError("Original frozen provider policy drifted")
    _assert_frozen_hbq_imports(v8, binding["source"]["runtime_projection"])
    disclosure, overrides, question_ids = _event_and_questions(v8, source, frozen)
    if question_ids != binding.get("question_ids") or hashlib.sha256(canonical(question_ids)).hexdigest() != binding.get("question_ids_sha256"):
        raise ValueError("Frozen 179-question identity binding drifted")
    if disclosure != _json(root / DISCLOSURE) or sha(root / DISCLOSURE) != binding["disclosure_sha256"]:
        raise ValueError("Acknowledged missing181 disclosure drifted")
    override = overrides[0]
    override_path = root / OVERRIDES / Path(str(override["path"])).name
    if _json(override_path) != override["schema"] or sha(override_path) != override["sha256"]:
        raise ValueError("Missing181 scope override drifted")
    if _json(root / ACKNOWLEDGEMENT) != _expected_ack(binding):
        raise ValueError("Missing181 acknowledgement does not bind the exact disclosure")
    receipt = v8.validate_capacity_evidence(v8._external(Path(evidence)))
    return v8, frozen, source, disclosure, override, question_ids, receipt


def prepare_completion(*, original_root: Path, v7_settlement: Path, controller_root: Path, v8_runtime_root: Path) -> dict[str, Any]:
    """Create one fresh provider-free controller and its immutable precontact evidence."""
    _guard, v8, runtime, executor = _load_runtime(v8_runtime_root)
    source = v8._external(Path(original_root))
    settlement = _settlement(_plain(Path(v7_settlement)))
    root = v8._external(Path(controller_root), allow_missing_leaf=True)
    if root.exists() or not root.parent.is_dir():
        raise ValueError("Controller root must be a fresh child of an existing external directory")
    if source == root or source in root.parents or root in source.parents or runtime == root or runtime in root.parents or root in runtime.parents:
        raise ValueError("Source, output/controller, and frozen runtime roots must be disjoint")
    frozen_path = source / "frozen-run-contract.json"
    frozen = v8.read_json(frozen_path)
    _validate_original_binding(source, frozen)
    runtime_projection = v8._runtime_projection(frozen)
    profile = v8.contract().get("provider")
    if not isinstance(profile, Mapping) or profile.get("paid_api") is not False or profile.get("human_judgment") is not False:
        raise TypeError("Pinned V8 provider profile is malformed")
    source_policy = _source_provider_policy(frozen, profile)
    _assert_frozen_hbq_imports(v8, runtime_projection)
    disclosure, overrides, question_ids = _event_and_questions(v8, source, frozen)
    os.mkdir(root)
    override_dir = root / OVERRIDES
    os.mkdir(override_dir)
    override = overrides[0]
    _write_override(override_dir / Path(str(override["path"])).name, override["schema"])
    _write_immutable(root / DISCLOSURE, disclosure)
    binding = {"format_version": 1, "study_id": STUDY_ID, "status": STATUS, "event": dict(EVENT), "controller_root": str(root), "source": {"root": str(source), "frozen_contract_sha256": EXPECTED_SOURCE_CONTRACT_SHA256, "runtime_projection": runtime_projection, "provider_policy_sha256": hashlib.sha256(canonical(source_policy)).hexdigest()}, "v7_zero_contact_settlement": {"path": str(_plain(Path(v7_settlement))), "sha256": SETTLEMENT_SHA256, "evidence_class": settlement["evidence_class"], "not_provider_attestation": True}, "runtime": {"root": str(runtime), "executor": str(executor), "executor_sha256": sha(executor), "study_id": v8.contract()["study_id"]}, "profile": dict(profile), "disclosure_sha256": sha(root / DISCLOSURE), "scope_compatibility_override": {"path": f"{OVERRIDES}/{Path(str(override['path'])).name}", "sha256": override["sha256"]}, "question_ids": question_ids, "question_ids_sha256": EXPECTED_QUESTION_IDS_SHA256, "provider_calls": 0}
    _write_immutable(root / BINDING, binding)
    with (root / LOCK).open("xb") as handle:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    return binding


def write_disclosure_ack(*, controller_root: Path, acknowledgement: Mapping[str, Any]) -> None:
    """Persist only the exact acknowledgement for this immutable disclosure."""
    root = _plain(Path(controller_root))
    with _lock(root):
        binding = _binding(root)
        if CLAIM in {item.name for item in root.iterdir()} or RECEIPT in {item.name for item in root.iterdir()}:
            raise ValueError("A claimed or completed controller cannot accept an acknowledgement")
        if dict(acknowledgement) != _expected_ack(binding):
            raise ValueError("Acknowledgement must exactly bind the prepared missing181 disclosure")
        _write_immutable(root / ACKNOWLEDGEMENT, acknowledgement)


def _claim(root: Path, binding: Mapping[str, Any], capacity: Mapping[str, Any]) -> None:
    _write_immutable(
        root / CLAIM,
        {
            "format_version": 1,
            "study_id": STUDY_ID,
            "event": dict(EVENT),
            "binding_sha256": sha(root / BINDING),
            "capacity_evidence_sha256": sha(Path(str(capacity["_path"]))),
            "capacity_observed_at": capacity["observed_at"],
            "claim_policy": "one dispatch only; retain this claim after every outcome",
        },
    )


def _validate_attempt(
    *,
    root: Path,
    binding: Mapping[str, Any],
    evidence: Path,
    context: Mapping[str, Any],
    runner: Any,
    disclosed_cell: Mapping[str, Any],
    profile: Mapping[str, Any],
    seen_batches: set[int],
) -> None:
    """The hook is immediately before each provider attempt, so it rechecks every binding."""
    attempt = context.get("attempt")
    batch = context.get("batch")
    provider = context.get("provider")
    prompt = context.get("prompt")
    schema = context.get("response_schema")
    if not all(isinstance(value, Mapping) for value in (attempt, batch, provider, prompt, schema)):
        raise ValueError("Runner omitted the per-attempt provider-boundary context")
    if attempt.get("number") != 1 or attempt.get("batch_attempts") != 3:
        raise ValueError("A retry would be a new provider attempt; this one-shot controller refuses resend")
    number = batch.get("number")
    if not isinstance(number, int) or not 1 <= number <= 6 or number in seen_batches or number != len(seen_batches) + 1:
        raise ValueError("HBQ provider batches must remain one fresh ordered sequence")
    v8, frozen, source, disclosure, override, _question_ids, _capacity = _precontact(root, binding, evidence)
    if profile != binding.get("profile") or disclosed_cell != disclosure:
        raise ValueError("Runner disclosure profile or cell changed after the exclusive claim")
    expected_payloads = disclosure["payload"]["provider_payloads"]
    expected = expected_payloads[number - 1]
    request = expected.get("request")
    if (
        not isinstance(request, Mapping)
        or provider != _provider_identity(binding["profile"])
        or batch.get("question_ids") != expected.get("question_ids")
        or prompt.get("encoding") != "utf-8"
        or schema.get("encoding") != "utf-8"
        or prompt.get("text") != request.get("prompt_utf8")
        or schema.get("text") != request.get("response_schema_utf8")
        or prompt.get("bytes") != len(str(request.get("prompt_utf8")).encode("utf-8"))
        or schema.get("bytes") != len(str(request.get("response_schema_utf8")).encode("utf-8"))
        or prompt.get("sha256") != hashlib.sha256(str(request.get("prompt_utf8")).encode("utf-8")).hexdigest()
        or schema.get("sha256") != hashlib.sha256(str(request.get("response_schema_utf8")).encode("utf-8")).hexdigest()
    ):
        raise ValueError("Per-attempt payload differs from the immutable reviewed disclosure")
    if v8._scope_override_records(source, [dict(EVENT)], frozen)[0] != override:
        raise ValueError("Scope-compatibility binding drifted before provider attempt")
    if not callable(getattr(runner, "runtime_identity", None)):
        raise TypeError("Pinned successor runner no longer exposes a runtime identity")
    seen_batches.add(number)


def _validate_provider_boundary(
    *,
    binding: Mapping[str, Any],
    disclosed_cell: Mapping[str, Any],
    profile: Mapping[str, Any],
    runner: Any,
    context: Mapping[str, Any],
    commitments: Mapping[str, Any],
) -> None:
    if context.get("provider") != _provider_identity(profile):
        raise ValueError("Provider boundary context drifted")
    expected = {
        "provider": _provider_identity(profile),
        "disclosure_profile": dict(profile),
        "disclosed_cell_sha256": hashlib.sha256(canonical(disclosed_cell)).hexdigest(),
        "disclosure_profile_sha256": hashlib.sha256(canonical(profile)).hexdigest(),
        "helper": runner.runtime_identity(),
    }
    if any(commitments.get(key) != value for key, value in expected.items()):
        raise ValueError("Provider-boundary commitments do not match the pinned controller")
    dependencies = commitments.get("dependencies")
    if not isinstance(dependencies, Mapping) or not isinstance(dependencies.get("scope_compatibility_override"), Mapping) or not isinstance(dependencies.get("task_contract"), Mapping):
        raise TypeError("HBQ provider boundary is missing its exact dependency commitments")
    override = dependencies["scope_compatibility_override"]
    task = dependencies["task_contract"]
    override_path = Path(str(binding["controller_root"])) / str(binding["scope_compatibility_override"]["path"])
    task_path = Path(str(binding["source"]["root"])) / "inputs" / EVENT["item_id"] / "task-contract.json"
    if override != {"path": str(override_path), "bytes": override_path.stat().st_size, "sha256": binding["scope_compatibility_override"]["sha256"]} or task != {"path": str(task_path), "bytes": task_path.stat().st_size, "sha256": sha(task_path)}:
        raise ValueError("Provider-boundary dependency paths or bytes drifted")


def _completed_output(v8: Any, root: Path, question_ids: list[str]) -> dict[str, Any]:
    target = v8._output_path(root, EVENT)
    output = _plain(target.parent)
    if target != output / "run.json" or not target.is_file():
        raise ValueError("Runner did not persist the exact isolated missing181 run.json")
    run = v8.read_json(target)
    configuration = run.get("configuration")
    if not isinstance(configuration, Mapping) or configuration.get("question_ids") != question_ids or configuration.get("batch_size") != 32 or configuration.get("retry_policy") != {"batch_attempts": 3} or configuration.get("retry_semantics") != "cumulative_batch_attempts_v1":
        raise ValueError("Persisted run configuration does not bind native batch32/three-attempt geometry")
    verdict_path = output / "verdicts.jsonl"
    raw = _plain(verdict_path).read_bytes()
    rows = []
    try:
        for line in raw.decode("utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise TypeError("verdict row is not an object")
            rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Persisted verdict bytes are not valid UTF-8 JSONL") from exc
    if [row.get("question_id") for row in rows] != question_ids:
        raise ValueError("Persisted verdict IDs do not exactly equal the frozen 179-question sequence")
    responses = output / "responses"
    accepted = sorted(responses.glob("batch-????.json"))
    if [path.name for path in accepted] != [f"batch-{number:04d}.json" for number in range(1, 7)]:
        raise ValueError("Persisted accepted batches are not the exact six batch32 checkpoints")
    attempts = 0
    normalized: list[str] = []
    for number, path in enumerate(accepted, 1):
        record = v8.read_json(path)
        attempt = record.get("accepted_attempt")
        ids = record.get("question_ids")
        verdicts = record.get("normalized_verdicts")
        expected = question_ids[(number - 1) * 32 : number * 32]
        if record.get("batch") != number or not isinstance(attempt, int) or not 1 <= attempt <= 3 or ids != expected or not isinstance(verdicts, list) or [item.get("question_id") if isinstance(item, Mapping) else None for item in verdicts] != expected:
            raise ValueError("Persisted batch attempts or normalized verdicts drifted")
        attempts += attempt
        normalized.extend(expected)
    if normalized != question_ids:
        raise ValueError("Accepted batch records do not reconstruct the frozen question sequence")
    sessions = v8._physical_output_sessions(output, EVENT)
    if len(sessions) != attempts or len(sessions) != len(set(sessions)):
        raise ValueError("Persisted attempt/session evidence is not an exact one-to-one topology")
    return {
        "path": str(target),
        "sha256": sha(target),
        "verdicts_jsonl_sha256": hashlib.sha256(raw).hexdigest(),
        "question_ids_sha256": hashlib.sha256(canonical(question_ids)).hexdigest(),
        "persisted_batches": 6,
        "persisted_attempts": attempts,
        "persisted_session_bearing_records": len(sessions),
        "session_ids_sha256": hashlib.sha256(canonical(sorted(sessions))).hexdigest(),
        "endpoint_attestation": "not independently proven; these are persisted runner/provider-session records",
    }


def dispatch_missing181(*, controller_root: Path, live_capacity_evidence: Path, allow_remote: bool = False, callback: Callable[..., Path] | None = None) -> Path:
    """Dispatch the one acknowledged cell once; any failure retains the exclusive claim."""
    if allow_remote is not True:
        raise ValueError("Missing181 remote dispatch is disabled unless explicitly authorized")
    root = _plain(Path(controller_root))
    with _lock(root):
        binding = _binding(root)
        entries = {item.name for item in root.iterdir()}
        if CLAIM in entries or RECEIPT in entries or "runs" in entries:
            raise ValueError("An existing claim, receipt, or output blocks resend or adoption")
        v8, frozen, source, disclosure, override, question_ids, capacity = _precontact(root, binding, Path(live_capacity_evidence))
        capacity = {**capacity, "_path": str(Path(live_capacity_evidence).absolute())}
        _claim(root, binding, capacity)
        runner = _load_pinned_runner(v8, binding)
        profile = binding["profile"]
        override_path = root / OVERRIDES / Path(str(override["path"])).name
        seen_batches: set[int] = set()

        def before_provider_attempt(context: Mapping[str, Any]) -> None:
            _validate_attempt(root=root, binding=binding, evidence=Path(live_capacity_evidence), context=context, runner=runner, disclosed_cell=disclosure, profile=profile, seen_batches=seen_batches)

        def provider_boundary_check(context: Mapping[str, Any], commitments: Mapping[str, Any]) -> None:
            _validate_provider_boundary(binding=binding, disclosed_cell=disclosure, profile=profile, runner=runner, context=context, commitments=commitments)

        dispatch = callback or runner.dispatch_event
        output = Path(dispatch(event=dict(EVENT), frozen=frozen, predecessor_root=source, work=root, timeout=3600.0, disclosed_cell=disclosure, disclosure_profile=profile, scope_compatibility_override_path=override_path, predecessor_runner=None, before_provider_attempt=before_provider_attempt, provider_boundary_check=provider_boundary_check))
        expected = v8._output_path(root, EVENT)
        if _plain(output) != expected:
            raise ValueError("Dispatcher returned a path other than the exact missing181 output")
        output_record = _completed_output(v8, root, question_ids)
        if seen_batches != set(range(1, 7)):
            raise ValueError("The dispatch did not expose all six bound provider-attempt callbacks")
        receipt = {"format_version": 1, "study_id": STUDY_ID, "status": "NORMAL_RECEIPT_WITH_PERSISTED_EVIDENCE", "event": dict(EVENT), "binding_sha256": sha(root / BINDING), "output": output_record, "attestation_limit": "Persisted attempts and unique session-bearing records are locally validated evidence, not independent provider endpoint contact proof."}
        _write_immutable(root / RECEIPT, receipt)
        return root / RECEIPT
