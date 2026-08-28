#!/usr/bin/env python3
"""Revalidate completed `run_judge` artifacts for the matched calibration screen."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs import runner

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("grok_sol_current_matched_study", HERE / "study.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Calibration study helper is unavailable")
study = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = study
SPEC.loader.exec_module(study)

VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
RUN_CONFIGURATION_KEYS = {
    "artifact", "contexts", "task_contract", "task_contract_judge_context", "scope_compatibility", "weight_profile",
    "bundle_id", "bundle_version", "question_ids", "provider", "model", "endpoint", "api_key_env", "temperature",
    "allow_model_mismatch", "reasoning", "batch_size", "retry_policy", "retry_semantics", "evidence_normalization_policy",
    "validation_feedback_policy", "artifact_id", "judge_id", "strict_ai", "prompt_rendering_version", "prompts",
    "response_schema", "questions_sha256", "compiled_bundle_sha256",
}
V4_CHECKPOINT_KEYS = {
    "format_version", "batch", "retry_policy", "accepted_attempt", "question_ids", "prompt_sha256", "base_prompt_sha256",
    "effective_prompt_sha256", "validation_feedback_policy", "validation_feedback", "normalization_policy", "normalization_audit",
    "response_sha256", "response_artifact", "rejected_chain", "previous_checkpoint_sha256", "verdicts_sha256", "provider",
    "normalized_verdicts",
}
V4_RUN_MANIFEST_KEYS = {"format_version", "run_id", "created_at", "config_sha256", "remote", "configuration"}


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _compact(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: record.get(key) for key in ("name", "bytes", "sha256")}


def _runtime_compact(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"name": Path(str(record["relative_path"])).name, "bytes": record["bytes"], "sha256": record["sha256"]}


def _current_binding(relative_path: str) -> dict[str, Any]:
    path = study.BOOK / relative_path
    return study.binding(path)


def _check_snapshot(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshot, dict):
        raise ValueError("Frozen snapshot must be an object")
    study.validate_snapshot(snapshot)
    return {row["case_id"]: row for row in study.cases()}


def _bound_dispatch_file(root: Path, value: Any) -> Path:
    if not isinstance(value, Mapping) or set(value) != {"relative_path", "bytes", "sha256"}:
        raise ValueError("Dispatch binding artifact has an invalid shape")
    relative = value.get("relative_path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Dispatch binding artifact path is unsafe")
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError("Dispatch binding artifact escapes its prepared root") from exc
    if value.get("bytes") != resolved.stat().st_size or value.get("sha256") != study.sha(resolved):
        raise ValueError("Dispatch binding artifact bytes drifted")
    return resolved


def _validate_dispatch_binding(dispatch_binding_path: Path, frozen_path: Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    binding = read(dispatch_binding_path)
    required = {"format_version", "study_id", "status", "provider_calls", "frozen_inputs", "disclosure", "owner_acknowledgement", "zero_charge_proofs", "conditions_sha256", "evidence_class", "promotion", "trusted_launch_receipt"}
    if set(binding) != required or binding.get("format_version") != 1 or binding.get("study_id") != snapshot["study_id"] or binding.get("status") != "prepared_provisional_dispatch_disabled" or binding.get("provider_calls") != 0:
        raise ValueError("Dispatch binding identity or disabled status drifted")
    if binding.get("frozen_inputs") != {"bytes": frozen_path.stat().st_size, "sha256": study.sha(frozen_path)} or binding.get("conditions_sha256") != hashlib.sha256(study.canonical(snapshot["protocol"]["conditions"])).hexdigest():
        raise ValueError("Dispatch binding frozen input or condition binding drifted")
    if binding.get("evidence_class") != "DEVELOPMENT_SCREENING_FIXTURE" or binding.get("promotion") != {"eligible": False, "evidence_class": "NON_PROMOTABLE", "reason": "trusted_external_runner_launch_receipt_required"} or binding.get("trusted_launch_receipt") != {"status": "absent_nonpromotable", "receipt": None}:
        raise ValueError("Dispatch binding promotion or trusted-launch status drifted")
    root = dispatch_binding_path.parent
    disclosure = read(_bound_dispatch_file(root, binding["disclosure"]))
    acknowledgement = read(_bound_dispatch_file(root, binding["owner_acknowledgement"]))
    zero_charge = read(_bound_dispatch_file(root, binding["zero_charge_proofs"]))
    study._validate_owner_acknowledgement(acknowledgement, disclosure, dict(snapshot))
    study._validate_zero_charge_proofs(zero_charge, dict(snapshot))
    return binding


def _provider(condition_id: str) -> Mapping[str, Any]:
    matches = [row for row in study.contract()["conditions"] if row.get("condition_id") == condition_id]
    if len(matches) != 1:
        raise ValueError("Condition is absent from the frozen protocol")
    return matches[0]


@lru_cache(maxsize=None)
def _package_hashes(bundle_id: str, question_id: str) -> tuple[str, str]:
    modules = load_modules(registry_path())
    bundle = resolve_bundle(load_bundles(bundles_path()), bundle_id)
    compiled = compile_bundle(modules, bundle)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    rows = sorted(compiled_questions(compiled), key=lambda row: roles.get(str(row.get("role")), 99))
    selected = [row for row in rows if row["question"]["id"] == question_id]
    if len(selected) != 1:
        raise ValueError("Frozen leaf is not uniquely selectable from its declared bundle")
    return hashlib.sha256(runner._json_bytes(compiled)).hexdigest(), hashlib.sha256(runner._json_bytes(runner._question_payload(selected))).hexdigest()


@lru_cache(maxsize=None)
def _bundle_version(bundle_id: str) -> Any:
    return resolve_bundle(load_bundles(bundles_path()), bundle_id).get("version")


def _expected_configuration_keys(condition_id: str) -> set[str]:
    if condition_id == "sol":
        return RUN_CONFIGURATION_KEYS | {"codex_bin"}
    if condition_id == "grok":
        return RUN_CONFIGURATION_KEYS | {"grok_bin", "allow_unattested_reasoning"}
    raise ValueError("Condition is absent from the frozen protocol")


def _assert_configuration(case: Mapping[str, Any], condition_id: str, config: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    if set(config) != _expected_configuration_keys(condition_id):
        raise ValueError("run_judge configuration has an unexpected or missing execution-affecting key")
    expected = _provider(condition_id)
    commitment = snapshot["case_commitments"][case["case_id"]]
    required = {
        "task_contract": None,
        "task_contract_judge_context": None,
        "scope_compatibility": None,
        "weight_profile": None,
        "bundle_id": case["bundle_id"],
        "bundle_version": _bundle_version(str(case["bundle_id"])),
        "question_ids": [case["question_id"]],
        "provider": expected["provider"],
        "model": expected["model"],
        "endpoint": None,
        "api_key_env": None,
        "temperature": None,
        "allow_model_mismatch": None,
        "reasoning": expected["reasoning"],
        "batch_size": 1,
        "retry_policy": {"batch_attempts": snapshot["protocol"]["batch_attempts"]},
        "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY,
        "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY,
        "artifact_id": case["case_id"],
        "judge_id": f"{expected['provider']}:{expected['model']}",
        "strict_ai": False,
        "prompt_rendering_version": runner.PROMPT_RENDERING_VERSION,
    }
    if any(config.get(key) != value for key, value in required.items()):
        raise ValueError("run_judge configuration does not match the frozen condition/case")
    if condition_id == "sol" and config.get("codex_bin") != "codex":
        raise ValueError("Sol configuration has an unexpected Codex executable")
    if condition_id == "grok" and (config.get("grok_bin") != "grok" or config.get("allow_unattested_reasoning") is not True):
        raise ValueError("Grok configuration lacks its frozen executable or reasoning-attestation limitation")
    if _compact(config.get("artifact", {})) != commitment["artifact"] or [_compact(item) for item in config.get("contexts", [])] != [commitment["context"]]:
        raise ValueError("run_judge artifact/context bindings drifted")
    runtime = {item["relative_path"]: item for item in snapshot["runtime"]}
    if [_compact(item) for item in config.get("prompts", [])] != [_runtime_compact(runtime["prompts/judge/BINARY_EVALUATION_PROMPT.md"])] or _compact(config.get("response_schema", {})) != _runtime_compact(runtime["schema/hbq_judge_response.schema.json"]):
        raise ValueError("run_judge prompt/schema bindings drifted")
    compiled_sha, question_sha = _package_hashes(str(case["bundle_id"]), str(case["question_id"]))
    if config.get("compiled_bundle_sha256") != compiled_sha or config.get("questions_sha256") != question_sha:
        raise ValueError("run_judge compiled package/leaf binding drifted")


def _assert_matched_configuration(sol: Mapping[str, Any], grok: Mapping[str, Any]) -> None:
    sol_config, grok_config = sol.get("configuration"), grok.get("configuration")
    if not isinstance(sol_config, Mapping) or not isinstance(grok_config, Mapping):
        raise ValueError("Accepted Sol/Grok runs lack their bound configurations")
    sol_shared = {key: value for key, value in sol_config.items() if key not in {"provider", "model", "reasoning", "judge_id", "codex_bin"}}
    grok_shared = {key: value for key, value in grok_config.items() if key not in {"provider", "model", "reasoning", "judge_id", "grok_bin", "allow_unattested_reasoning"}}
    if sol_shared != grok_shared:
        raise ValueError("Sol/Grok run configurations are asymmetric outside the frozen judge identity fields")


def _assert_unique_schedule_identities(records: list[tuple[str, Mapping[str, Any]]]) -> None:
    run_ids: set[str] = set()
    grok_request_ids: set[str] = set()
    grok_session_ids: set[str] = set()
    for condition_id, result in records:
        run_id = result.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in run_ids:
            raise ValueError("Accepted schedule has duplicate or missing run_id")
        run_ids.add(run_id)
        if condition_id != "grok":
            continue
        receipt = result.get("provider_receipt")
        if not isinstance(receipt, Mapping):
            raise ValueError("Grok schedule entry lacks a provider receipt")
        for key, seen in (("request_id_sha256", grok_request_ids), ("session_id_sha256", grok_session_ids)):
            value = receipt.get(key)
            if not isinstance(value, str) or len(value) != 64 or value in seen:
                raise ValueError(f"Grok schedule has duplicate or missing {key}")
            seen.add(value)
    if len(run_ids) != 72 or len(grok_request_ids) != 36 or len(grok_session_ids) != 36:
        raise ValueError("Accepted schedule identity count does not match the frozen 72-run geometry")


def _run_manifest_identity(manifest: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    if set(manifest) != V4_RUN_MANIFEST_KEYS or manifest.get("format_version") != 4 or manifest.get("config_sha256") != hashlib.sha256(runner._json_bytes(config)).hexdigest() or manifest.get("remote") is not True:
        raise ValueError("run_judge manifest does not use the exact current V4 shape")
    run_id, created_at = manifest.get("run_id"), manifest.get("created_at")
    if not isinstance(run_id, str) or not run_id.strip() or not isinstance(created_at, str):
        raise ValueError("run_judge manifest lacks a bound run identity or timestamp")
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("run_judge manifest has an invalid creation timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("run_judge manifest timestamp must include an offset")
    return run_id


def _assert_verdict_identity(verdict: Mapping[str, Any], case: Mapping[str, Any], config: Mapping[str, Any], run_id: str) -> None:
    expected = {
        "question_id": case["question_id"],
        "artifact_id": case["case_id"],
        "bundle_id": case["bundle_id"],
        "judge_id": config["judge_id"],
        "run_id": run_id,
    }
    if any(verdict.get(key) != value for key, value in expected.items()) or config["judge_id"] != f"{config['provider']}:{config['model']}":
        raise ValueError("Normalized verdict identity is not bound to the manifest/configuration")


def _checkpoint_record(run: Path, case: Mapping[str, Any], condition_id: str) -> dict[str, Any]:
    path = run / "responses" / "batch-0001.json"
    record = read(path)
    keys = set(record)
    if keys != V4_CHECKPOINT_KEYS or record.get("format_version") != 4:
        raise ValueError("Response checkpoint must use the exact current V4 schema")
    condition = _provider(condition_id)
    expected_prompt = study.rendered_prompt(dict(case), dict(condition)).encode("utf-8")
    prompt_path = run / "responses" / "batch-0001.prompt.txt.gz"
    try:
        persisted_prompt = gzip.decompress(prompt_path.read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Response checkpoint prompt receipt is unreadable") from exc
    prompt_sha256 = hashlib.sha256(expected_prompt).hexdigest()
    if persisted_prompt != expected_prompt or any(record.get(key) != prompt_sha256 for key in ("prompt_sha256", "base_prompt_sha256", "effective_prompt_sha256")):
        raise ValueError("Response checkpoint prompt bytes or hash do not match the exact frozen rendering")
    if record.get("batch") != 1 or record.get("retry_policy") != {"batch_attempts": 1} or record.get("question_ids") != [case["question_id"]] or record.get("accepted_attempt") != 1 or record.get("rejected_chain") != {"count": 0, "head_sha256": None}:
        raise ValueError("Response checkpoint schedule binding drifted")
    if record.get("normalization_policy") != runner.EVIDENCE_NORMALIZATION_POLICY or record.get("validation_feedback_policy") != runner.VALIDATION_FEEDBACK_POLICY or record.get("validation_feedback") is not None:
        raise ValueError("Response checkpoint normalization policy drifted")
    receipt = record.get("response_artifact")
    expected_receipt_path = "responses/batch-0001.accepted-0001.message.txt"
    if not isinstance(receipt, Mapping) or receipt.get("path") != expected_receipt_path:
        raise ValueError("Response checkpoint accepted-response receipt is absent or misbound")
    response_path = run / expected_receipt_path
    if not response_path.is_file() or receipt.get("bytes") != response_path.stat().st_size or receipt.get("sha256") != study.sha(response_path) or record.get("response_sha256") != study.sha(response_path):
        raise ValueError("Response checkpoint accepted-response receipt drifted")
    provider = record.get("provider")
    if not isinstance(provider, Mapping):
        raise ValueError("Response checkpoint lacks provider evidence")
    if condition_id == "sol":
        reported = provider.get("reported")
        command = provider.get("command")
        if set(provider) != {"command", "reported"} or reported != {"model": condition["model"], "provider": "openai", "reasoning_effort": condition["reasoning"]} or not isinstance(command, list) or not command or command[0] != "codex":
            raise ValueError("Sol provider/model/reasoning receipt drifted")
    elif condition_id == "grok":
        required = {"cli_version", "requested", "reported", "session_id_sha256", "request_id_sha256", "reasoning_attested", "reasoning_attestation", "provider_artifacts"}
        if set(provider) != required or provider.get("requested") != {"model": condition["model"], "reasoning_effort": condition["reasoning"]} or provider.get("reported") != {"provider": "grok", "model": "grok-4.6-build"} or provider.get("reasoning_attested") is not False or provider.get("reasoning_attestation") != "not_reported_by_grok_build_cli":
            raise ValueError("Grok provider/model/reasoning receipt drifted")
        artifacts = provider.get("provider_artifacts")
        if not isinstance(artifacts, Mapping) or set(artifacts) != {"grok_envelope"}:
            raise ValueError("Grok provider receipt lacks its envelope artifact")
        envelope_artifact = artifacts["grok_envelope"]
        envelope_path = run / str(envelope_artifact.get("path")) if isinstance(envelope_artifact, Mapping) else None
        try:
            envelope = json.loads(envelope_path.read_text(encoding="utf-8")) if envelope_path is not None else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Grok provider envelope is unreadable") from exc
        if not isinstance(envelope, Mapping):
            raise ValueError("Grok provider envelope is malformed")
        for field, receipt_key in (("requestId", "request_id_sha256"), ("sessionId", "session_id_sha256")):
            value = envelope.get(field)
            if not isinstance(value, str) or provider.get(receipt_key) != hashlib.sha256(value.encode("utf-8")).hexdigest():
                raise ValueError("Grok provider receipt identities are not derived from its bound envelope")
    else:
        raise ValueError("Condition is absent from the frozen protocol")
    try:
        runner._validate_provider_artifacts(run, record)
    except runner.HBQError as exc:
        raise ValueError("Response checkpoint provider receipt is invalid") from exc
    return dict(provider)


def _run_path(work: Path, condition_id: str, case_id: str, repetition: int) -> Path:
    return work / "runs" / condition_id / case_id / f"run-{repetition:02d}"


def _run_evidence_bindings(work: Path, run: Path) -> list[dict[str, Any]]:
    if not run.is_dir():
        raise ValueError("Expected accepted run directory is missing")
    files = sorted(path for path in run.rglob("*") if path.is_file())
    if not files:
        raise ValueError("Accepted run contains no persisted evidence")
    return [
        {
            "relative_path": path.relative_to(work).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": study.sha(path),
        }
        for path in files
    ]


def _validate_run_tree(work: Path, cases: Mapping[str, Mapping[str, Any]]) -> None:
    runs = work / "runs"
    expected = {
        _run_path(work, condition_id, case_id, repetition).relative_to(work).as_posix()
        for condition_id in ("sol", "grok")
        for case_id in cases
        for repetition in range(1, 4)
    }
    actual = {
        path.relative_to(work).as_posix()
        for path in runs.glob("*/*/run-*")
        if path.is_dir()
    } if runs.is_dir() else set()
    if actual != expected:
        raise ValueError("Accepted runs do not exactly match the frozen condition/case/repetition schedule")
    allowed_prefixes = tuple(f"{path}/" for path in expected)
    unexpected = [
        path.relative_to(work).as_posix()
        for path in runs.rglob("*")
        if path.is_file() and not path.relative_to(work).as_posix().startswith(allowed_prefixes)
    ]
    if unexpected:
        raise ValueError("Run tree contains evidence outside the frozen schedule")


def _localize_evidence(case: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    quote = evidence.get("exact_quote")
    if quote is None:
        if not isinstance(evidence.get("summary"), str) or not evidence["summary"].strip():
            raise ValueError("A normalized evidence item is neither an exact quote nor a nonblank summary")
        return None
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError("An exact quote must be nonblank")
    reference = evidence.get("reference")
    sources = {"source.md": str(case["artifact"]), "context.md": str(case["context"])}
    if reference not in sources:
        raise ValueError("An exact quote must identify its frozen source or context reference")
    source = sources[str(reference)]
    offsets: list[int] = []
    offset = source.find(quote)
    while offset >= 0:
        offsets.append(offset)
        offset = source.find(quote, offset + 1)
    if len(offsets) != 1:
        raise ValueError("An exact quote must have one source-specific frozen offset")
    start = offsets[0]
    return {"reference": reference, "start_offset": start, "end_offset": start + len(quote), "exact_quote": quote}


def _run(work: Path, snapshot: Mapping[str, Any], case: Mapping[str, Any], condition_id: str, repetition: int) -> dict[str, Any]:
    run = _run_path(work, condition_id, str(case["case_id"]), repetition)
    evidence_bindings = _run_evidence_bindings(work, run)
    manifest = read(run / "run.json")
    config = manifest.get("configuration")
    if not isinstance(config, Mapping):
        raise ValueError("run_judge manifest is malformed or unbound")
    run_id = _run_manifest_identity(manifest, config)
    _assert_configuration(case, condition_id, config, snapshot)
    provider_receipt = _checkpoint_record(run, case, condition_id)
    verdicts, count, _ = runner._load_checkpoints(run, artifact_text=str(case["artifact"]), context_texts=[str(case["context"])], batch_attempts=int(snapshot["protocol"]["batch_attempts"]), normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    stored = runner._load_completed(run / "verdicts.jsonl")
    if count != 1 or verdicts != stored or len(verdicts) != 1:
        raise ValueError("run_judge checkpoints do not settle exactly one bound leaf")
    verdict = verdicts[0]
    if verdict.get("question_id") != case["question_id"] or verdict.get("verdict") not in VERDICTS:
        raise ValueError("run_judge verdict does not match the bound leaf")
    _assert_verdict_identity(verdict, case, config, run_id)
    localizations = []
    preserved_evidence = []
    for evidence in verdict.get("evidence", []):
        if not isinstance(evidence, Mapping):
            raise ValueError("run_judge normalized evidence is malformed")
        item = dict(evidence)
        preserved_evidence.append(item)
        localization = _localize_evidence(case, item)
        if localization is not None:
            localizations.append(localization)
    return {
        "verdict": str(verdict["verdict"]),
        "exact_quote_count": len(localizations),
        "evidence_localizations": localizations,
        "evidence": preserved_evidence,
        "input_evidence": evidence_bindings,
        "configuration": dict(config),
        "run_id": run_id,
        "provider_receipt": provider_receipt,
    }


def _rate(count: int, total: int) -> dict[str, int | float | None]:
    return {"count": count, "total": total, "rate": count / total if total else None}


def analyze(snapshot_path: Path, work: Path, dispatch_binding_path: Path, output: Path) -> dict[str, Any]:
    guarded = study.guard_external_roots(
        {"frozen": snapshot_path, "work": work, "dispatch_binding": dispatch_binding_path, "output": output},
        require_exists={"frozen", "work", "dispatch_binding"},
    )
    snapshot_path, work, dispatch_binding_path, output = (guarded["frozen"], guarded["work"], guarded["dispatch_binding"], guarded["output"])
    study.validate()
    snapshot = read(snapshot_path)
    cases = _check_snapshot(snapshot)
    dispatch_binding = _validate_dispatch_binding(dispatch_binding_path, snapshot_path, snapshot)
    if output.exists():
        raise ValueError("Refusing to overwrite a calibration analysis output")
    _validate_run_tree(work, cases)
    cross_judge_by_area: dict[str, Counter[str]] = defaultdict(Counter)
    judge_by_intent: dict[str, Counter[str]] = {"sol": Counter(), "grok": Counter()}
    judge_by_area: dict[str, dict[str, Counter[str]]] = {"sol": defaultdict(Counter), "grok": defaultdict(Counter)}
    repeats: dict[str, dict[str, list[str]]] = {condition: defaultdict(list) for condition in ("sol", "grok")}
    exact = joint_binary = binary_agree = quotes = joint_no = 0
    scope = Counter({"same_frozen_declared_scope": 0, "grok_broader": 0, "grok_narrower": 0, "unavailable_from_runner": 0})
    joint_no_declared_leaf = Counter({"joint_no_same_declared_leaf": 0, "not_joint_no": 0})
    disagreement_ledger: list[dict[str, Any]] = []
    analysis_inputs: list[dict[str, Any]] = []
    schedule_identities: list[tuple[str, Mapping[str, Any]]] = []
    for case_id, case in cases.items():
        for repetition in range(1, 4):
            sol = _run(work, snapshot, case, "sol", repetition)
            grok = _run(work, snapshot, case, "grok", repetition)
            schedule_identities.extend((("sol", sol), ("grok", grok)))
            _assert_matched_configuration(sol, grok)
            for condition_id, result in (("sol", sol), ("grok", grok)):
                run = _run_path(work, condition_id, case_id, repetition)
                analysis_inputs.append({
                    "condition_id": condition_id,
                    "case_id": case_id,
                    "repetition": repetition,
                    "run_path": run.relative_to(work).as_posix(),
                    "files": result.get("input_evidence", _run_evidence_bindings(work, run)),
                })
            repeats["sol"][case_id].append(sol["verdict"]); repeats["grok"][case_id].append(grok["verdict"])
            expected = str(study.contract()["design_intent_verdicts"][case["design_intent"]])
            for condition_id, result in (("sol", sol), ("grok", grok)):
                observed = result["verdict"]
                judge_by_intent[condition_id][f"{expected}->{observed}"] += 1
                judge_by_area[condition_id][str(case["area"])][f"{expected}->{observed}"] += 1
            cross_judge_by_area[str(case["area"])][f"{sol['verdict']}->{grok['verdict']}"] += 1
            exact += int(sol["verdict"] == grok["verdict"])
            if {sol["verdict"], grok["verdict"]}.issubset({"YES", "NO"}):
                joint_binary += 1; binary_agree += int(sol["verdict"] == grok["verdict"])
            quotes += sol["exact_quote_count"] + grok["exact_quote_count"]
            scope["same_frozen_declared_scope"] += 1; scope["unavailable_from_runner"] += 1
            if sol["verdict"] == grok["verdict"] == "NO":
                joint_no += 1; joint_no_declared_leaf["joint_no_same_declared_leaf"] += 1
            else:
                joint_no_declared_leaf["not_joint_no"] += 1
            disagreement_ledger.append({
                "case_id": case_id,
                "area": case["area"],
                "design_intent": case["design_intent"],
                "expected_verdict": expected,
                "repetition": repetition,
                "sol_verdict": sol["verdict"],
                "grok_verdict": grok["verdict"],
                "pair_exact": sol["verdict"] == grok["verdict"],
                "sol_matches_design_intent": sol["verdict"] == expected,
                "grok_matches_design_intent": grok["verdict"] == expected,
                "common_mode_wrong": sol["verdict"] == grok["verdict"] != expected,
                "sol_evidence": sol.get("evidence", []),
                "grok_evidence": grok.get("evidence", []),
                "sol_evidence_localizations": sol.get("evidence_localizations", []),
                "grok_evidence_localizations": grok.get("evidence_localizations", []),
            })
    _assert_unique_schedule_identities(schedule_identities)
    total = len(cases) * 3
    def repeatability(values: list[str]) -> dict[str, int | float]:
        modal = Counter(values).most_common(1)[0][1]
        return {"all_three_count": int(len(set(values)) == 1), "pairwise_agreement": sum(values[left] == values[right] for left in range(3) for right in range(left + 1, 3)) / 3, "modal_agreement": modal / 3}
    per_judge_design_intent = {
        condition: {
            "exact_agreement": _rate(sum(count for key, count in values.items() if key.split("->", 1)[0] == key.split("->", 1)[1]), total),
            "confusion": dict(sorted(values.items())),
            "confusion_by_area": {area: dict(sorted(counts.items())) for area, counts in sorted(judge_by_area[condition].items())},
        }
        for condition, values in judge_by_intent.items()
    }
    summary = {
        "format_version": 3, "study_id": snapshot["study_id"], "snapshot_sha256": study.sha(snapshot_path), "pair_count": total,
        "evidence_class": "DEVELOPMENT_SCREENING_FIXTURE",
        "promotion": {"eligible": False, "evidence_class": "NON_PROMOTABLE", "reason": "trusted_external_runner_launch_receipt_required"},
        "dispatch_binding_sha256": study.sha(dispatch_binding_path),
        "four_state": {"exact_agreement": _rate(exact, total), "cross_judge_confusion_by_area": {area: dict(sorted(values.items())) for area, values in sorted(cross_judge_by_area.items())}},
        "per_judge_design_intent": per_judge_design_intent,
        "case_disagreement_ledger": disagreement_ledger,
        "binary_joint_yes_no": _rate(binary_agree, joint_binary),
        "repeatability": {condition: {"all_three_rate": _rate(sum(repeatability(values)["all_three_count"] for values in cases_.values()), len(cases_)), "mean_pairwise_agreement": statistics.fmean(repeatability(values)["pairwise_agreement"] for values in cases_.values()), "mean_modal_agreement": statistics.fmean(repeatability(values)["modal_agreement"] for values in cases_.values())} for condition, cases_ in repeats.items()},
        "quote_grounding": {"exact_quote_count": quotes, "grounded_exact_quote_count": quotes, "rate": 1.0 if quotes else None},
        "latency": {"status": "unavailable_runner_does_not_persist_structured_elapsed_time"},
        "directional_deltas": {
            "scope": dict(scope),
            "joint_no_same_declared_leaf": {**dict(joint_no_declared_leaf), "joint_no_pair_count": joint_no},
            "materiality": {"status": "unavailable_runner_has_no_structured_materiality_evidence"},
        },
        "interpretation": "Development screen only; Sol remains canonical for scope, craft, penalty, and release decisions.",
    }
    output.mkdir(parents=True)
    input_manifest = {
        "format_version": 1,
        "study_id": snapshot["study_id"],
        "evidence_class": "DEVELOPMENT_SCREENING_FIXTURE",
        "promotion": {"eligible": False, "evidence_class": "NON_PROMOTABLE", "reason": "trusted_external_runner_launch_receipt_required"},
        "dispatch_binding": {"bytes": dispatch_binding_path.stat().st_size, "sha256": study.sha(dispatch_binding_path)},
        "frozen_inputs": {"bytes": snapshot_path.stat().st_size, "sha256": study.sha(snapshot_path)},
        "analysis_program": snapshot["analysis_program"],
        "accepted_runs": analysis_inputs,
    }
    (output / "analysis-input-manifest.json").write_bytes(study.canonical(input_manifest))
    (output / "summary.json").write_bytes(study.canonical(summary))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--dispatch-binding", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary = analyze(args.frozen.resolve(), args.work.resolve(), args.dispatch_binding.resolve(), args.output.resolve())
    print(json.dumps({"study_id": summary["study_id"], "pair_count": summary["pair_count"], "provider_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
