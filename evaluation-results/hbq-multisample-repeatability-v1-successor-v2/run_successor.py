"""Dispatch one V7 cell only after its complete preflight projection is bound."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import RetryDisclosurePause, run_judge


HELPER_ID = "hbq-multisample-repeatability-v1-successor-v2-dispatch-helper"
_OVERRIDE_KEYS = {
    "format_version",
    "artifact_id",
    "bundle_id",
    "task_contract_sha256",
    "contract_id",
    "artifact_kind",
    "declared_scope",
    "compatibility_mode",
    "decision_id",
    "reviewer",
    "reason",
}


class NativeRetryDisclosurePause(RetryDisclosurePause):
    """A semantic native rejection has a durable changed payload but no second contact."""

    def __init__(self, context: Mapping[str, Any]) -> None:
        super().__init__("Native semantic retry disclosure and acknowledgement are required before another provider contact")
        self.context = dict(context)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _plain_file(path: Path) -> Path:
    absolute = Path(path).absolute()
    probe = absolute
    while True:
        if _is_reparse(probe):
            raise ValueError(f"Scope compatibility dependency contains a symlink/reparse point: {probe}")
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    try:
        if not stat.S_ISREG(absolute.lstat().st_mode):
            raise ValueError(f"Scope compatibility dependency is not a regular file: {absolute}")
    except FileNotFoundError as exc:
        raise ValueError(f"Scope compatibility dependency is missing: {absolute}") from exc
    return absolute


def _read_once(path: Path) -> tuple[Path, bytes, str]:
    plain = _plain_file(path)
    try:
        raw = plain.read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read scope compatibility dependency: {plain}") from exc
    return plain, raw, hashlib.sha256(raw).hexdigest()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def runtime_identity() -> dict[str, Any]:
    path, raw, digest = _read_once(Path(__file__))
    return {"helper_id": HELPER_ID, "path": path.name, "bytes": len(raw), "sha256": digest}


def _arm(frozen: Mapping[str, Any], event: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = frozen.get("contract")
    arms = contract.get("arms") if isinstance(contract, Mapping) else None
    matches = [arm for arm in arms or [] if isinstance(arm, Mapping) and arm.get("arm_id") == event.get("arm_id")]
    if len(matches) != 1:
        raise ValueError("Frozen contract does not select exactly one arm")
    return matches[0]


def _provider_identity(frozen: Mapping[str, Any], disclosure_profile: Mapping[str, Any]) -> dict[str, str]:
    contract = frozen.get("contract")
    provider = contract.get("provider") if isinstance(contract, Mapping) else None
    if not isinstance(provider, Mapping):
        raise ValueError("Frozen contract has no provider identity")
    expected = {"provider": "codex", "model": provider.get("model"), "reasoning": provider.get("reasoning")}
    if not all(isinstance(value, str) and value.strip() for value in expected.values()):
        raise ValueError("Frozen provider identity is malformed")
    expected_profile = {**expected, "paid_api": False, "human_judgment": False}
    if dict(disclosure_profile) != expected_profile:
        raise ValueError("Preflight disclosure profile does not bind the frozen provider identity")
    return expected


def _validate_disclosed_cell(
    disclosed_cell: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    hbq: bool,
) -> list[dict[str, Any]]:
    if any(disclosed_cell.get(key) != event.get(key) for key in ("sequence", "item_id", "arm_id", "repetition")):
        raise ValueError("Preflight disclosure cell does not bind this event")
    artifacts = disclosed_cell.get("outbound_artifacts")
    payload = disclosed_cell.get("payload")
    if not isinstance(artifacts, list) or not isinstance(payload, Mapping):
        raise ValueError("Preflight disclosure cell is incomplete")
    roles = {item.get("role") for item in artifacts if isinstance(item, Mapping)}
    required_roles = {"artifact", "originating_prompt"} | ({"task_contract"} if hbq else set())
    if not required_roles <= roles:
        raise ValueError("Preflight disclosure omits an outbound artifact")
    rubric = payload.get("rubric")
    payloads = payload.get("provider_payloads")
    if not isinstance(rubric, list) or not isinstance(payloads, list) or not payloads:
        raise ValueError("Preflight disclosure omits rubric or provider payloads")
    if hbq and not {"rubric_registry", "rubric_bundle", "judge_instruction"} <= {item.get("role") for item in rubric if isinstance(item, Mapping)}:
        raise ValueError("Preflight disclosure omits HBQ instructions or rubric bindings")
    checked: list[dict[str, Any]] = []
    for item in payloads:
        if not isinstance(item, Mapping) or not isinstance(item.get("batch"), int) or item["batch"] < 1:
            raise ValueError("Preflight provider payload is malformed")
        request = item.get("request")
        if not isinstance(request, Mapping) or not all(isinstance(request.get(key), str) for key in ("prompt_utf8", "response_schema_utf8")):
            raise ValueError("Preflight provider payload omits prompt or response schema")
        projected = {"batch": item["batch"], "request": dict(request)}
        if "question_ids" in item:
            if not isinstance(item["question_ids"], list) or not all(isinstance(value, str) for value in item["question_ids"]):
                raise ValueError("Preflight provider payload question IDs are malformed")
            projected["question_ids"] = item["question_ids"]
        if item.get("payload_sha256") != hashlib.sha256(_canonical(projected)).hexdigest():
            raise ValueError("Preflight provider payload binding drifted")
        checked.append(dict(item))
    if len({item["batch"] for item in checked}) != len(checked):
        raise ValueError("Preflight provider payload batches are not unique")
    return checked


def _validate_override(path: Path | None, *, event: Mapping[str, Any], arm: Mapping[str, Any], task_contract_path: Path) -> dict[str, Any]:
    if path is None:
        raise ValueError("HBQ dispatch requires an exact reviewed scope compatibility override")
    override_path, override_raw, override_sha256 = _read_once(Path(path))
    task_path, task_raw, task_sha256 = _read_once(task_contract_path)
    override = _json_object(override_raw, "Scope compatibility override")
    task_contract = _json_object(task_raw, "HBQ task contract")
    if set(override) != _OVERRIDE_KEYS:
        raise ValueError("Scope compatibility override must use the exact v1 schema")
    expected = {
        "format_version": 1,
        "artifact_id": event.get("item_id"),
        "bundle_id": arm.get("bundle_id"),
        "task_contract_sha256": task_sha256,
        "contract_id": task_contract.get("contract_id"),
        "artifact_kind": task_contract.get("context", {}).get("artifact_kind") if isinstance(task_contract.get("context"), Mapping) else None,
        "declared_scope": task_contract.get("context", {}).get("declared_scope") if isinstance(task_contract.get("context"), Mapping) else None,
        "compatibility_mode": "reviewed_override",
    }
    if any(override.get(key) != value for key, value in expected.items()):
        raise ValueError("Scope compatibility override does not bind this artifact, contract, and bundle")
    if not all(isinstance(override.get(key), str) and override[key].strip() for key in ("decision_id", "reviewer", "reason")):
        raise ValueError("Scope compatibility override requires a nonblank decision, reviewer, and reason")
    return {
        "mode": "reviewed_override",
        "path": str(override_path),
        "name": override_path.name,
        "bytes": len(override_raw),
        "sha256": override_sha256,
        "task_contract": {"path": str(task_path), "bytes": len(task_raw), "sha256": task_sha256},
        "format_version": 1,
        "decision_id": override["decision_id"],
        "reviewer": override["reviewer"],
    }


def _bound_before_provider_attempt(
    *,
    payloads: list[dict[str, Any]],
    provider: Mapping[str, str],
    before_provider_attempt: Callable[[Mapping[str, Any]], None],
    provider_boundary_check: Callable[[Mapping[str, Any], Mapping[str, Any]], None],
    commitments: Mapping[str, Any],
) -> Callable[[Mapping[str, Any]], None]:
    def checked(context: Mapping[str, Any]) -> None:
        attempt = context.get("attempt")
        if not isinstance(attempt, Mapping) or not isinstance(attempt.get("number"), int) or attempt["number"] < 1:
            raise ValueError("Provider attempt context is malformed")
        if attempt["number"] == 1:
            batch = context.get("batch")
            prompt = context.get("prompt")
            schema = context.get("response_schema")
            reported = context.get("provider")
            if not all(isinstance(value, Mapping) for value in (batch, prompt, schema, reported)):
                raise ValueError("Provider attempt lacks preflight-bindable fields")
            selected = [payload for payload in payloads if payload["batch"] == batch.get("number")]
            if len(selected) != 1:
                raise ValueError("Provider attempt batch was not preflight-disclosed")
            request = selected[0]["request"]
            if (
                any(reported.get(key) != value for key, value in provider.items())
                or prompt.get("encoding") != "utf-8"
                or schema.get("encoding") != "utf-8"
                or prompt.get("text") != request["prompt_utf8"]
                or schema.get("text") != request["response_schema_utf8"]
                or batch.get("question_ids") != selected[0].get("question_ids")
            ):
                raise ValueError("Provider attempt does not exactly match the acknowledged preflight payload")
        dependencies = commitments.get("dependencies")
        if isinstance(dependencies, Mapping):
            for dependency in dependencies.values():
                if not isinstance(dependency, Mapping) or not isinstance(dependency.get("path"), str):
                    raise ValueError("Provider-boundary dependency commitment is malformed")
                _, raw, digest = _read_once(Path(dependency["path"]))
                if dependency.get("bytes") != len(raw) or dependency.get("sha256") != digest:
                    raise ValueError("Provider-boundary dependency drifted after preflight validation")
        provider_boundary_check(context, commitments)
        before_provider_attempt(context)

    return checked


def _output_path(work: Path, event: Mapping[str, Any]) -> Path:
    suffix = "run.json" if event.get("arm_id") == "hbq_short_story_batch32" else "pass.json"
    return Path(work) / "runs" / str(event["item_id"]) / str(event["arm_id"]) / f"run-{int(event['repetition']):02d}" / suffix


def _native_context(
    *,
    event: Mapping[str, Any],
    provider: Mapping[str, str],
    attempt: int,
    prompt: str,
    schema: bytes,
    output: Path,
    validation_feedback: Mapping[str, Any] | None = None,
    rejected_chain: Mapping[str, Any] | None = None,
    base_prompt: str | None = None,
) -> dict[str, Any]:
    prompt_bytes = prompt.encode("utf-8")
    base_prompt_bytes = (base_prompt if base_prompt is not None else prompt).encode("utf-8")
    return {
        "format_version": 1,
        "run": {"name": f"{event['item_id']}-{event['arm_id']}-run-{int(event['repetition']):02d}"},
        "provider": dict(provider),
        "batch": {"number": 1, "question_ids": []},
        "attempt": {"number": attempt},
        "prompt": {
            "encoding": "utf-8",
            "text": prompt,
            "bytes": len(prompt_bytes),
            "sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "base_prompt_sha256": hashlib.sha256(base_prompt_bytes).hexdigest(),
        },
        "response_schema": {
            "encoding": "utf-8",
            "text": schema.decode("utf-8"),
            "bytes": len(schema),
            "sha256": hashlib.sha256(schema).hexdigest(),
        },
        "validation_feedback_policy": "native_semantic_rejection_v1" if validation_feedback is not None else None,
        "validation_feedback": dict(validation_feedback) if validation_feedback is not None else None,
        "rejected_chain": dict(rejected_chain) if rejected_chain is not None else {"count": 0, "head_sha256": "0" * 64, "records": []},
        "output_dir": str(output),
    }


def _native_rejection_chain(output: Path) -> dict[str, Any]:
    root = output / "attempts"
    paths = sorted(root.glob("rejected-*.json")) if root.is_dir() else []
    if not paths:
        raise ValueError("Native semantic rejection lacks a durable rejected checkpoint")
    records = []
    for path in paths:
        _, raw, digest = _read_once(path)
        record = _json_object(raw, "Native rejected checkpoint")
        if not isinstance(record.get("reason"), str) or not isinstance(record.get("response"), Mapping):
            raise ValueError("Native rejected checkpoint is incomplete")
        records.append({"path": path.name, "sha256": digest, "reason": record["reason"]})
    return {"format_version": 1, "count": len(records), "records": records, "head_sha256": records[-1]["sha256"]}


def _native_retry_feedback(rejected_chain: Mapping[str, Any]) -> dict[str, Any]:
    records = rejected_chain.get("records")
    if not isinstance(records, list) or not records or not isinstance(records[-1], Mapping):
        raise ValueError("Native rejected-chain feedback is unavailable")
    feedback = {
        "format_version": 1,
        "kind": "native_semantic_rejection",
        "rejected_checkpoint_sha256": records[-1].get("sha256"),
        "reason": records[-1].get("reason"),
    }
    if not isinstance(feedback["rejected_checkpoint_sha256"], str) or not isinstance(feedback["reason"], str):
        raise ValueError("Native rejected-chain feedback is malformed")
    feedback["sha256"] = hashlib.sha256(_canonical(feedback)).hexdigest()
    return feedback


def _archive_native_base_pass(output: Path) -> None:
    archive = output / "retry-attempts" / "attempt-0001"
    archive.mkdir(parents=True, exist_ok=True)
    for name in ("pass.json", "response.schema.json", "request.prompt.txt.gz"):
        source = output / name
        destination = archive / name
        if source.is_file():
            if destination.exists():
                raise ValueError("Native base-pass archive already exists")
            os.replace(source, destination)


def _promote_native_retry(retry_output: Path, output: Path) -> None:
    if not (retry_output / "pass.json").is_file() or not (retry_output / "response.json").is_file():
        raise ValueError("Accepted native retry lacks its structured-pass evidence")
    for source in retry_output.iterdir():
        if not source.is_file():
            continue
        destination = output / source.name
        if destination.exists():
            raise ValueError("Native retry promotion would overwrite existing evidence")
        os.replace(source, destination)


def _dispatch_native(
    *,
    predecessor_runner: Any,
    event: Mapping[str, Any],
    frozen: Mapping[str, Any],
    predecessor_root: Path,
    work: Path,
    timeout: float,
    provider: Mapping[str, str],
    before_provider_attempt: Callable[[Mapping[str, Any]], None],
) -> Path:
    arm = _arm(frozen, event)
    source_path = Path(predecessor_root) / "inputs" / str(event["item_id"]) / "source.md"
    prompt_path = Path(predecessor_root) / "inputs" / str(event["item_id"]) / "prompt.md"
    rubric_path = Path(predecessor_runner.HERE).parent / "hbq-multisample-repeatability-v1" / str(arm["prompt"])
    schema_path = Path(predecessor_runner.HERE).parent / "hbq-multisample-repeatability-v1" / str(arm["schema"])
    _, source_raw, _ = _read_once(source_path)
    _, prompt_raw, _ = _read_once(prompt_path)
    _, rubric_raw, _ = _read_once(rubric_path)
    _, schema_raw, _ = _read_once(schema_path)
    try:
        source_text = source_raw.decode("utf-8")
        prompt_text = prompt_raw.decode("utf-8")
        rubric_text = rubric_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Native dispatch dependency is not UTF-8") from exc
    schema = _json_object(schema_raw, "Native response schema")
    rendered = predecessor_runner._artifact_prompt(rubric_text, source_text, prompt_text)
    provider_schema = predecessor_runner._structured_json_bytes(predecessor_runner._provider_response_schema(schema))
    output = _output_path(work, event).parent
    semantic_runner = predecessor_runner._v1_runner()
    while True:
        attempts = output / "attempts"
        recorded = len(list(attempts.glob("rejected-*.json"))) + len(list(attempts.glob("failed-*.json"))) + 1 if attempts.is_dir() else 1
        attempt = max(recorded, predecessor_runner._next_codex_message_attempt(output, 1))
        if not (output / "response.json").is_file() and attempt > 3:
            raise ValueError(f"{arm['arm_id']} exhausted the frozen three-attempt limit")
        retrying = attempt > 1
        if retrying:
            if attempt != 2:
                raise ValueError("Native retry cap reached; operator settlement is required before another contact")
            rejected_chain = _native_rejection_chain(output)
            feedback = _native_retry_feedback(rejected_chain)
            effective_prompt = f"{rendered.rstrip()}\n\n<validation_feedback>{_canonical(feedback).decode('utf-8')}</validation_feedback>\n"
            retry_context = _native_context(
                event=event,
                provider=provider,
                attempt=attempt,
                prompt=effective_prompt,
                schema=provider_schema,
                output=output,
                validation_feedback=feedback,
                rejected_chain=rejected_chain,
                base_prompt=rendered,
            )
            before_provider_attempt(retry_context)
            pass_dir = output / "retry-attempts" / f"attempt-{attempt:04d}"
        else:
            effective_prompt = rendered
            pass_dir = output
        if not (output / "response.json").is_file():
            if not retrying:
                before_provider_attempt(_native_context(event=event, provider=provider, attempt=attempt, prompt=rendered, schema=provider_schema, output=output))
        result = predecessor_runner._run_structured_pass(
            name=f"{event['item_id']}-{event['arm_id']}-run-{int(event['repetition']):02d}",
            prompt=effective_prompt,
            schema=schema,
            pass_dir=pass_dir,
            provider="codex",
            model=provider["model"],
            endpoint=None,
            api_key_env="OPENAI_API_KEY",
            temperature=None,
            allow_model_mismatch=False,
            reasoning=provider["reasoning"],
            codex_bin="codex",
            timeout=timeout,
            resume=(pass_dir / "pass.json").is_file(),
            openai_structured_outputs=False,
        )
        try:
            predecessor_runner._semantic_native(semantic_runner, result, str(arm["arm_id"]), source_text, pass_dir)
            if retrying:
                _promote_native_retry(pass_dir, output)
            return output / "pass.json"
        except ValueError as exc:
            if (pass_dir / "normalization-audit.json").is_file():
                raise
            if (pass_dir / "response.json").is_file():
                predecessor_runner._reject_structured_checkpoint(pass_dir, reason=str(exc))
            if (pass_dir / "result.json").is_file():
                (pass_dir / "result.json").unlink()
            if retrying:
                raise ValueError("Native retry was rejected; operator settlement is required before another contact")
            _archive_native_base_pass(output)
            rejected_chain = _native_rejection_chain(output)
            feedback = _native_retry_feedback(rejected_chain)
            retry_prompt = f"{rendered.rstrip()}\n\n<validation_feedback>{_canonical(feedback).decode('utf-8')}</validation_feedback>\n"
            retry_context = _native_context(
                event=event,
                provider=provider,
                attempt=attempt + 1,
                prompt=retry_prompt,
                schema=provider_schema,
                output=output,
                validation_feedback=feedback,
                rejected_chain=rejected_chain,
                base_prompt=rendered,
            )
            before_provider_attempt(retry_context)
            raise NativeRetryDisclosurePause(retry_context)


def dispatch_event(
    *,
    event: Mapping[str, Any],
    frozen: Mapping[str, Any],
    predecessor_root: Path,
    work: Path,
    timeout: float,
    disclosed_cell: Mapping[str, Any],
    disclosure_profile: Mapping[str, Any],
    scope_compatibility_override_path: Path | None = None,
    predecessor_runner: Any | None = None,
    before_provider_attempt: Callable[[Mapping[str, Any]], None] | None = None,
    provider_boundary_check: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None = None,
) -> Path:
    """Dispatch one already-acknowledged cell; no schedule or output recovery lives here."""

    if before_provider_attempt is None or provider_boundary_check is None:
        raise ValueError("A pre-contact acknowledgement hook is required")
    arm = _arm(frozen, event)
    hbq = arm.get("kind") != "native"
    provider = _provider_identity(frozen, disclosure_profile)
    payloads = _validate_disclosed_cell(disclosed_cell, event, hbq=hbq)
    commitments: dict[str, Any] = {
        "format_version": 1,
        "helper": runtime_identity(),
        "provider": dict(provider),
        "disclosure_profile": dict(disclosure_profile),
        "disclosed_cell_sha256": hashlib.sha256(_canonical(disclosed_cell)).hexdigest(),
        "disclosure_profile_sha256": hashlib.sha256(_canonical(disclosure_profile)).hexdigest(),
    }
    if not hbq:
        if predecessor_runner is None:
            raise ValueError("Native dispatch requires the immutable predecessor runner")
        bound_hook = _bound_before_provider_attempt(payloads=payloads, provider=provider, before_provider_attempt=before_provider_attempt, provider_boundary_check=provider_boundary_check, commitments=commitments)
        return _dispatch_native(predecessor_runner=predecessor_runner, event=event, frozen=frozen, predecessor_root=predecessor_root, work=work, timeout=timeout, provider=provider, before_provider_attempt=bound_hook)
    folder = Path(predecessor_root) / "inputs" / str(event["item_id"])
    override = _validate_override(
        scope_compatibility_override_path,
        event=event,
        arm=arm,
        task_contract_path=folder / "task-contract.json",
    )
    commitments["dependencies"] = {
        "scope_compatibility_override": {key: override[key] for key in ("path", "bytes", "sha256")},
        "task_contract": dict(override["task_contract"]),
    }
    bound_hook = _bound_before_provider_attempt(payloads=payloads, provider=provider, before_provider_attempt=before_provider_attempt, provider_boundary_check=provider_boundary_check, commitments=commitments)
    output = _output_path(work, event)
    run_judge(
        artifact_path=folder / "source.md",
        context_paths=[folder / "prompt.md"],
        task_contract_path=folder / "task-contract.json",
        artifact_id=str(event["item_id"]),
        bundle_id=str(arm["bundle_id"]),
        provider=provider["provider"],
        model=provider["model"],
        reasoning=provider["reasoning"],
        output_dir=output.parent,
        registry=registry_path(),
        bundles=bundles_path(),
        batch_size=arm["batch_size"],
        batch_attempts=arm["batch_attempts"],
        allow_remote=True,
        resume=output.is_file(),
        timeout=timeout,
        strict_ai=True,
        scope_compatibility_override_path=override["path"],
        before_provider_attempt=bound_hook,
    )
    return output
