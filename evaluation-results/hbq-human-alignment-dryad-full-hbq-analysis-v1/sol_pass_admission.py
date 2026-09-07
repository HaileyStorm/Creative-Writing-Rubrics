"""Read-only admission of one collected Sol fixed-batch pass."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PROTOCOL = ROOT / "protocol-v2.json"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
_HEX = set("0123456789abcdef")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _time(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and value.endswith(("Z", "+00:00")), f"{label} differs")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _require(result.tzinfo is not None, f"{label} differs")
    return result.astimezone(timezone.utc)


def _relative(root: Path, name: str) -> Path:
    path = root / name
    _require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), "Required evidence path differs")
    return path


def _source_bindings(expected: Mapping[str, str]) -> tuple[Any, Any, Any]:
    _require(set(expected) == {"driver", "adapter", "runner", "v3", "core"} and all(_hex(value) for value in expected.values()), "Sol source bindings differ")
    protocol_raw = PROTOCOL.read_bytes()
    _require(_sha(protocol_raw) == PROTOCOL_SHA256, "Protocol source differs")
    bindings = _json(protocol_raw, "Protocol").get("runtime_bindings")
    _require(isinstance(bindings, dict) and all(_hex(value) and _sha((REPOSITORY / path).read_bytes()) == value for path, value in bindings.items()), "Inherited runtime bindings differ")
    _require(expected["runner"] == bindings.get("src/hbqrs/runner.py") and expected["core"] == bindings.get("src/hbqrs/core.py"), "Sol runner/core bindings differ")
    spec = importlib.util.spec_from_file_location("_dryad_sol_admission_runtime", ROOT / "sol_existing_runtime.py")
    _require(spec is not None and spec.loader is not None, "Sol runtime cannot load")
    sol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sol)
    _require(expected["driver"] == _sha((ROOT / "sol_measurement_execution.py").read_bytes()) and expected["adapter"] == _sha((ROOT / "sol_existing_runtime.py").read_bytes()) and expected["v3"] == sol.BASE_SHA256, "Sol driver or adapter binding differs")
    inserted = str(REPOSITORY / "src") not in sys.path
    if inserted:
        sys.path.insert(0, str(REPOSITORY / "src"))
    try:
        from hbqrs import core, runner, weights
    finally:
        if inserted:
            sys.path.remove(str(REPOSITORY / "src"))
    modules = core.load_modules(REPOSITORY / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story")
    return SimpleNamespace(core=core, runner=runner, weights=weights, modules=modules, bundle=bundle), sol._base(), sol


def _route(metadata: Mapping[str, Any], authorized: datetime) -> None:
    required = {"schema_version", "plan_sha256", "ordinal", "source_bindings", "cohort_number", "review_sha256", "route_sha256", "route_snapshot", "authorized_at", "auth_receipt", "cost_receipt"}
    _require(set(metadata) == required and metadata["schema_version"] == 1 and metadata["plan_sha256"] == PLAN_SHA256 and _hex(metadata["review_sha256"]) and _hex(metadata["route_sha256"]), "Sol checkpoint metadata differs")
    route = metadata["route_snapshot"]
    _require(isinstance(route, Mapping) and _sha(_canonical(route)) == metadata["route_sha256"] and route.get("zero_charge") is True and route.get("armed") is True and route.get("account_class") == "subscription" and route.get("provider") == "openai_codex" and route.get("model") == "gpt-5.6-sol" and route.get("reasoning_effort") == "high" and route.get("timeout_seconds") == 900, "Sol route differs")
    command, identity = route.get("codex_command"), route.get("codex_command_identity")
    _require(isinstance(command, list) and command and all(isinstance(value, str) and value for value in command) and isinstance(identity, Mapping) and set(identity) == {"version", "artifacts"} and identity.get("version") == 1 and isinstance(identity.get("artifacts"), list) and identity["artifacts"] and all(isinstance(item, Mapping) and set(item) == {"index", "sha256", "path_hash"} and type(item["index"]) is int and 0 <= item["index"] < len(command) and _hex(item["sha256"]) and _hex(item["path_hash"]) for item in identity["artifacts"]), "Sol route command identity differs")
    auth, cost = metadata["auth_receipt"], metadata["cost_receipt"]
    auth_keys = {"schema_version", "account_class", "provider", "route", "evidence_class", "checked_at", "expires_at", "status_hash", "audit"}
    cost_keys = {"schema_version", "account_class", "provider", "route", "model", "kind", "allowance_state", "checked_at", "expires_at", "audit"}
    _require(isinstance(auth, Mapping) and set(auth) == auth_keys and auth.get("schema_version") == 1 and auth.get("account_class") == "subscription" and auth.get("provider") == "openai_codex" and auth.get("route") == "codex-chatgpt-gpt-5.6-sol" and auth.get("evidence_class") == "chatgpt_subscription_auth_status_v1" and _hex(auth.get("status_hash")) and isinstance(auth.get("audit"), Mapping), "Sol auth receipt differs")
    _require(isinstance(cost, Mapping) and set(cost) == cost_keys and cost.get("schema_version") == 1 and cost.get("account_class") == "subscription" and cost.get("provider") == "openai_codex" and cost.get("route") == "codex-chatgpt-gpt-5.6-sol" and cost.get("model") == "gpt-5.6-sol" and cost.get("kind") == "subscription_included" and cost.get("allowance_state") == "available" and isinstance(cost.get("audit"), Mapping), "Sol cost receipt differs")
    evidence = route.get("cost_evidence")
    _require(route.get("auth_receipt_hash") == _sha(_canonical(auth)) and isinstance(evidence, Mapping) and evidence.get("evidence_hash") == _sha(_canonical(cost)) and all(evidence.get(key) == cost.get(key) for key in ("checked_at", "expires_at", "kind", "allowance_state")), "Sol route receipt binding differs")
    for receipt, label in ((auth, "auth"), (cost, "cost")):
        start, end = _time(receipt["checked_at"], label), _time(receipt["expires_at"], label)
        _require(start <= authorized < end, "Sol receipt window differs")


def admit_pass(run_root: Path, plan_root: Path, pass_id: str, *, expected_plan_sha256: str, expected_source_bindings: Mapping[str, str], expected_reviews: set[str], expected_batches: int | None = None) -> dict[str, Any]:
    """Replay a collected prefix; a partial prefix cannot establish a score."""
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_hex(value) for value in expected_reviews), "Trusted Sol admission anchors differ")
    runtime, v3, _ = _source_bindings(expected_source_bindings)
    plan_raw = _relative(Path(plan_root), "plan.json").read_bytes()
    _require(_sha(plan_raw) == expected_plan_sha256, "Frozen plan differs")
    plan = _json(plan_raw, "Plan")
    passes, requests = plan.get("passes"), plan.get("requests")
    _require(isinstance(passes, list) and isinstance(requests, list) and len(passes) == 236 and len(requests) == 5428, "Plan geometry differs")
    record = next((item for item in passes if isinstance(item, dict) and item.get("pass_id") == pass_id), None)
    _require(record is not None and record.get("batch_size") == 8 and record.get("batches") == 23, "Planned Sol pass differs")
    planned = [item for item in requests if isinstance(item, dict) and item.get("pass_id") == pass_id]
    ids = plan.get("runtime", {}).get("question_ids") if isinstance(plan.get("runtime"), dict) else None
    _require(len(planned) == 23 and isinstance(ids, list) and len(ids) == len(set(ids)) == 178 and [item.get("batch_number") for item in planned] == list(range(1, 24)) and [question for item in planned for question in item.get("question_ids", [])] == ids, "Planned Sol batches differ")
    root = Path(run_root).resolve(); _require(root.is_dir(), "Sol run root differs")
    execution = root
    for _ in Path(record["run_path"]).parts: execution = execution.parent
    _require((execution / record["run_path"]).resolve() == root, "Sol execution root differs")
    source = _relative(Path(plan_root), record["input_path"]).read_bytes()
    _require(_sha(source) == record.get("source_sha256") and len(source) == record.get("source_bytes"), "Sol source differs")
    text = source.decode("utf-8")
    manifest = _json(_relative(root, "run.json").read_bytes(), "Sol run")
    config = manifest.get("configuration")
    _, _, weight_audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, None)
    _require(isinstance(config, Mapping) and config.get("provider") == "codex" and config.get("model") == "gpt-5.6-sol" and config.get("reasoning") == "high" and config.get("artifact_id") == record.get("logical_sample_id") and config.get("question_ids") == ids and config.get("batch_size") == 8 and config.get("retry_policy") == {"batch_attempts": 1} and config.get("attempt_lifecycle_policy") == "terminal_sidecar_v1" and config.get("weight_profile") == weight_audit, "Sol run configuration differs")
    count = 23 if expected_batches is None else expected_batches
    _require(type(count) is int and 1 <= count <= 23, "Sol expected batch prefix differs")
    verdicts, checkpoint_count, head = runtime.runner._load_checkpoints(root, artifact_text=text, context_texts=[], batch_attempts=1)
    _require(checkpoint_count == count and len(verdicts) == sum(len(item["question_ids"]) for item in planned[:count]), "Sol checkpoint prefix differs")
    threads: list[str] = []
    for request in planned[:count]:
        number = request["batch_number"]
        checkpoint = _json(_relative(root, f"responses/batch-{number:04d}.json").read_bytes(), "Sol checkpoint")
        _require(checkpoint.get("accepted_attempt") == 1 and checkpoint.get("question_ids") == request["question_ids"], "Sol checkpoint request differs")
        prompt, schema = _relative(Path(plan_root), request["prompt_path"]).read_bytes(), _relative(Path(plan_root), request["schema_path"]).read_bytes()
        _require(gzip.decompress(_relative(root, f"responses/batch-{number:04d}.prompt.txt.gz").read_bytes()) == prompt and _sha(prompt) == request["prompt_sha256"] and len(prompt) == request["prompt_bytes"] and _relative(root, f"responses/schemas/batch-{number:04d}.json").read_bytes() == schema and _sha(schema) == request["schema_sha256"] and len(schema) == request["schema_bytes"], "Sol retained prompt or schema differs")
        provider = checkpoint.get("provider"); metadata = provider.get("dryad_sol") if isinstance(provider, Mapping) else None
        _require(isinstance(metadata, Mapping) and metadata.get("ordinal") == request["ordinal"] and metadata.get("source_bindings") == dict(expected_source_bindings), "Sol provider binding differs")
        authorized = _time(metadata.get("authorized_at"), "Sol authorization")
        _route(metadata, authorized)
        cohort = metadata.get("cohort_number"); start = ((request["ordinal"] - 1) // 10) * 10 + 1
        _require(type(cohort) is int and cohort == (request["ordinal"] - 1) // 10 + 1 and metadata["review_sha256"] in expected_reviews, "Sol cohort binding differs")
        review_raw = _relative(execution, f"cohorts/{cohort:04d}/reviews/{metadata['review_sha256']}.json").read_bytes(); review = _json(review_raw, "Sol review")
        _require(_sha(review_raw) == metadata["review_sha256"] and set(review) == {"schema_version", "decision", "plan_sha256", "cohort_number", "ordinals", "source_bindings", "route_sha256", "reviewed_at", "expires_at", "reviewer_task"} and review.get("schema_version") == 1 and review.get("decision") == "approved_sol_cohort" and review.get("plan_sha256") == PLAN_SHA256 and review.get("cohort_number") == cohort and review.get("ordinals") == list(range(start, min(start + 10, 5429))) and review.get("source_bindings") == dict(expected_source_bindings) and review.get("route_sha256") == metadata["route_sha256"] and isinstance(review.get("reviewer_task"), str) and review["reviewer_task"], "Sol review differs")
        reviewed, expires = _time(review["reviewed_at"], "Sol review"), _time(review["expires_at"], "Sol review")
        _require(reviewed <= authorized <= expires <= reviewed + timedelta(hours=2), "Sol review window differs")
        artifacts = provider.get("provider_artifacts") if isinstance(provider, Mapping) else None
        _require(isinstance(artifacts, Mapping) and set(artifacts) == {"codex_events", "codex_stderr"}, "Sol provider artifacts differ")
        command = list(v3._expected_codex_command(config.get("codex_bin", "codex"), root))
        command[command.index("--output-schema") + 1] = str(root / f"responses/schemas/batch-{number:04d}.json")
        command[command.index("--output-last-message") + 1] = str(root / f"responses/batch-{number:04d}.attempt-0001.message.json")
        command[-1:-1] = ["--disable", "code_mode"]
        _require(config.get("codex_bin") == metadata["route_snapshot"]["codex_command"][0] == provider.get("command", [None])[0] and provider.get("command") == command, "Sol native command differs")
        for descriptor in artifacts.values():
            path = _relative(root, descriptor.get("path")); _require(runtime.runner._provider_artifact(root, path) == dict(descriptor), "Sol provider artifact hash differs")
        stderr = _relative(root, artifacts["codex_stderr"]["path"]).read_bytes(); v3._strict_stderr_labels(stderr)
        events = _relative(root, artifacts["codex_events"]["path"]).read_bytes(); projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        final = _relative(root, checkpoint["response_artifact"]["path"]).read_bytes()
        _require(projection.get("completed_agent_message_text", "").encode("utf-8") == final and isinstance(projection.get("thread_id"), str) and projection["thread_id"] and isinstance(projection.get("usage"), dict), "Sol native event projection differs")
        threads.append(projection["thread_id"])
    _require(len(threads) == len(set(threads)), "Duplicate local Sol thread identity")
    result: dict[str, Any] = {"verdicts": [{"question_id": item["question_id"], "verdict": item["verdict"]} for item in verdicts], "checkpoint_head_sha256": head, "local_thread_ids": threads, "requested_identity": {"model": "gpt-5.6-sol", "reasoning": "high", "identity_evidence": "requested_only", "native_endpoint_contact_cardinality": "unproven"}, "score": None, "coverage": None}
    if count == 23:
        score = runtime.core.score_bundle(runtime.modules, runtime.bundle, verdicts, artifact_id=record["logical_sample_id"], task_contract=None)
        score["weight_profile"] = weight_audit
        _require(_relative(root, "score.json").read_bytes() == runtime.runner._json_bytes(score), "Sol score replay differs")
        observed, coverage = score["final_score"]["observed"], score["coverage"]
        _require(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100 and type(coverage) in (int, float) and math.isfinite(coverage) and coverage >= .88, "Sol score or coverage differs")
        result.update(score=observed, coverage=coverage)
    return result


def admit_campaign(plan_root: Path, execution_root: Path, *, expected_plan_sha256: str, expected_source_bindings: Mapping[str, str], expected_reviews: set[str]) -> dict[str, Any]:
    """Compose only complete admitted passes; partial results have no campaign meaning."""
    plan_raw = _relative(Path(plan_root), "plan.json").read_bytes()
    _require(expected_plan_sha256 == PLAN_SHA256 and _sha(plan_raw) == expected_plan_sha256, "Frozen campaign plan differs")
    plan = _json(plan_raw, "Plan")
    passes, requests = plan.get("passes"), plan.get("requests")
    _require(isinstance(passes, list) and len(passes) == 236 and isinstance(requests, list) and len(requests) == 5428, "Campaign plan geometry differs")
    _require([item.get("partition") if isinstance(item, Mapping) else None for item in passes] == ["TRAIN"] * 176 + ["DEV"] * 60, "Campaign frozen source order differs")
    threads: set[str] = set(); rows: list[dict[str, Any]] = []
    for record in passes:
        _require(isinstance(record, Mapping) and isinstance(record.get("pass_id"), str) and isinstance(record.get("run_path"), str), "Campaign pass differs")
        admitted = admit_pass(Path(execution_root) / record["run_path"], Path(plan_root), record["pass_id"], expected_plan_sha256=expected_plan_sha256, expected_source_bindings=expected_source_bindings, expected_reviews=expected_reviews)
        local = admitted.get("local_thread_ids")
        _require(isinstance(local, list) and len(local) == len(set(local)) == 23 and all(isinstance(value, str) and value and value not in threads for value in local) and isinstance(admitted.get("verdicts"), list) and len(admitted["verdicts"]) == 178 and type(admitted.get("score")) in (int, float) and type(admitted.get("coverage")) in (int, float), "Campaign pass is incomplete or duplicates a local thread")
        threads.update(local)
        rows.append({key: record[key] for key in ("pass_id", "logical_sample_id", "opaque_story_id", "partition")} | {key: admitted[key] for key in ("verdicts", "score", "coverage")})
    _require(len(rows) == 236 and len(threads) == 5428, "Campaign local thread cardinality differs")
    return {"evidence_class": "complete_sol_local_lifecycle_campaign_admission", "execution_authority": False, "provider_calls": 0, "admitted_passes": 236, "logical_requests": 5428, "endpoint_sol_rows": rows, "identity_ceiling": {"identity_evidence": "requested_only", "native_endpoint_contact_cardinality": "unproven", "provider_attested": False}}
