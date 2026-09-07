"""Collect frozen Sol batches through the existing runner and CLI lifecycle."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
TIMEOUT = 300
FILES = {
    "driver": Path(__file__).resolve(),
    "adapter": ROOT / "sol_existing_runtime.py",
    "runner": REPOSITORY / "src/hbqrs/runner.py",
    "core": REPOSITORY / "src/hbqrs/core.py",
    "v3": ROOT.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/executor.py",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_bindings() -> dict[str, str]:
    return {key: digest(path.read_bytes()) for key, path in FILES.items()}


def _study(plan_root: Path) -> dict[str, Any]:
    raw = (plan_root / "plan.json").read_bytes()
    require(digest(raw) == PLAN_SHA256, "Sol frozen plan differs")
    protocol_raw = (ROOT / "protocol-v2.json").read_bytes()
    require(digest(protocol_raw) == PROTOCOL_SHA256, "Sol frozen protocol differs")
    for relative, expected in json.loads(protocol_raw)["runtime_bindings"].items():
        require(digest((REPOSITORY / relative).read_bytes()) == expected, "Sol study source differs")
    return json.loads(raw)


def _ordinals(cohort: int) -> list[int]:
    require(type(cohort) is int and 1 <= cohort <= 543, "Sol cohort differs")
    return list(range((cohort - 1) * 10 + 1, min(cohort * 10 + 1, 5429)))


def review_candidate(plan_root: Path, cohort: int, route_path: Path) -> dict[str, Any]:
    _study(plan_root)
    route = read(route_path)
    return {"schema_version": 1, "decision": "approved_sol_cohort", "plan_sha256": PLAN_SHA256,
            "cohort_number": cohort, "ordinals": _ordinals(cohort), "source_bindings": source_bindings(),
            "route_sha256": digest(canonical(route))}


def _private_runner() -> ModuleType:
    import hbqrs  # noqa: F401 - establishes the package for relative imports.

    name = f"hbqrs._dryad_sol_{uuid.uuid4().hex}"
    module = ModuleType(name)
    module.__file__, module.__package__ = str(FILES["runner"]), "hbqrs"
    sys.modules[name] = module
    try:
        exec(compile(FILES["runner"].read_bytes(), str(FILES["runner"]), "exec"), module.__dict__)  # noqa: S102 - current hash-bound local runner.
    finally:
        sys.modules.pop(name, None)
    return module


def _adapter() -> Any:
    spec = importlib.util.spec_from_file_location("_dryad_sol_existing", FILES["adapter"])
    require(spec is not None and spec.loader is not None, "Sol adapter cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_cohort(
    plan_root: Path, execution_root: Path, review_path: Path, *, expected_review_sha256: str,
    queue_root: Path, auth_receipt_path: Path, cost_receipt_path: Path,
) -> dict[str, Any]:
    plan_root, execution_root = plan_root.resolve(), execution_root.resolve()
    plan = _study(plan_root)
    raw = review_path.read_bytes()
    require(digest(raw) == expected_review_sha256, "Sol review anchor differs")
    review = json.loads(raw)
    expected_keys = {"schema_version", "decision", "plan_sha256", "cohort_number", "ordinals",
                     "source_bindings", "route_sha256", "reviewed_at", "expires_at", "reviewer_task"}
    require(set(review) == expected_keys and review["schema_version"] == 1
            and review["decision"] == "approved_sol_cohort" and review["plan_sha256"] == PLAN_SHA256
            and isinstance(review["reviewer_task"], str) and bool(review["reviewer_task"]), "Sol review differs")
    cohort = review["cohort_number"]
    ordinals = _ordinals(cohort)
    require(review["ordinals"] == ordinals and review["source_bindings"] == source_bindings(), "Sol reviewed scope differs")
    start, end = (datetime.fromisoformat(review[key].replace("Z", "+00:00")) for key in ("reviewed_at", "expires_at"))
    require(start.utcoffset() == end.utcoffset() == timedelta(0) and start < end <= start + timedelta(hours=2),
            "Sol review window differs")
    requests = {row["ordinal"]: row for row in plan["requests"]}
    passes = {row["pass_id"]: row for row in plan["passes"]}
    require(list(requests) == list(range(1, 5429)) and len(passes) == 236, "Sol plan geometry differs")
    for ordinal in range(1, ordinals[0]):
        request = requests[ordinal]
        prior = execution_root / passes[request["pass_id"]]["run_path"] / "responses" / f"batch-{request['batch_number']:04d}.json"
        require(prior.is_file(), "Sol collection cannot skip earlier batches")
    execution_root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex.encode()
    lock = execution_root / ".collect.lock"
    with lock.open("xb") as output:
        output.write(token)
    try:
        directory = execution_root / "cohorts" / f"{cohort:04d}"
        reviews = directory / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        retained = reviews / f"{expected_review_sha256}.json"
        if retained.exists():
            require(retained.read_bytes() == raw, "Sol retained review differs")
        else:
            with retained.open("xb") as output:
                output.write(raw)
        runner, adapter = _private_runner(), _adapter()
        selected = {ordinal: requests[ordinal] for ordinal in ordinals}
        active: dict[str, Any] = {}
        def authorize() -> None:
            now = datetime.now(timezone.utc)
            if not start <= now or now + timedelta(seconds=TIMEOUT) >= end:
                raise runner.RetryDisclosurePause("Sol review window requires renewal")
            require(source_bindings() == review["source_bindings"] and retained.read_bytes() == raw,
                    "Sol source or review changed")
            route = next(row for row in read(queue_root / "routes.json")["routes"] if row["name"] == "codex-chatgpt-gpt-5.6-sol")
            require(digest(canonical(route)) == review["route_sha256"] and route["armed"] is True
                    and route["zero_charge"] is True and route["health"] == "healthy"
                    and route["provider"] == "openai_codex" and route["adapter"] == "codex_exec"
                    and route["destination"] == "openai_codex_chatgpt_subscription"
                    and route["account_class"] == "subscription" and route["model"] == "gpt-5.6-sol"
                    and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900, "Sol current route differs")
            auth_raw, cost_raw = auth_receipt_path.read_bytes(), cost_receipt_path.read_bytes()
            require(digest(auth_raw) == route["auth_receipt_hash"]
                    and digest(cost_raw) == route["cost_evidence"]["evidence_hash"], "Sol receipt binding differs")
            auth, cost = json.loads(auth_raw), json.loads(cost_raw)
            auth_keys = {"schema_version", "account_class", "provider", "route", "evidence_class",
                         "checked_at", "expires_at", "status_hash", "audit"}
            cost_keys = {"schema_version", "account_class", "provider", "route", "model", "kind",
                         "allowance_state", "checked_at", "expires_at", "audit"}
            require(set(auth) == auth_keys and set(cost) == cost_keys
                    and auth["schema_version"] == cost["schema_version"] == 1
                    and isinstance(auth["audit"], dict) and isinstance(cost["audit"], dict)
                    and isinstance(auth["status_hash"], str) and len(auth["status_hash"]) == 64
                    and set(auth["status_hash"]) <= set("0123456789abcdef")
                    and canonical(auth) == auth_raw and canonical(cost) == cost_raw,
                    "Sol receipt replay contract differs")
            require(all(route["cost_evidence"].get(key) == cost[key]
                        for key in ("checked_at", "expires_at", "kind", "allowance_state")),
                    "Sol cost receipt projection differs")
            require(auth["account_class"] == cost["account_class"] == "subscription"
                    and auth["provider"] == cost["provider"] == "openai_codex"
                    and auth["route"] == cost["route"] == route["name"]
                    and auth["evidence_class"] == "chatgpt_subscription_auth_status_v1"
                    and cost["kind"] == "subscription_included" and cost["allowance_state"] == "available"
                    and cost["model"] == "gpt-5.6-sol", "Sol included subscription evidence differs")
            for receipt in (auth, cost, route["cost_evidence"]):
                require(all(isinstance(receipt[key], str) and receipt[key].endswith(("Z", "+00:00"))
                            for key in ("checked_at", "expires_at")), "Sol receipt UTC time differs")
                checked = datetime.fromisoformat(receipt["checked_at"].replace("Z", "+00:00"))
                expires = datetime.fromisoformat(receipt["expires_at"].replace("Z", "+00:00"))
                if not checked <= now or now + timedelta(seconds=TIMEOUT) >= expires:
                    raise runner.RetryDisclosurePause("Sol subscription evidence requires refresh")
            executable = Path(route["codex_command"][0])
            require(digest(executable.read_bytes()) == route["codex_command_identity"]["artifacts"][0]["sha256"],
                    "Sol CLI executable changed")
            active["evidence"] = {"schema_version": 1, "plan_sha256": PLAN_SHA256,
                "ordinal": active["request"]["ordinal"], "source_bindings": review["source_bindings"],
                "cohort_number": cohort, "review_sha256": expected_review_sha256,
                "route_sha256": review["route_sha256"], "route_snapshot": route,
                "authorized_at": now.isoformat(), "auth_receipt": auth, "cost_receipt": cost}

        def before(context: dict[str, Any]) -> None:
            output = Path(context["output_dir"]).resolve()
            request = next((row for row in selected.values() if row["batch_number"] == context["batch"]["number"]
                            and execution_root / passes[row["pass_id"]]["run_path"] == output), None)
            if request is None:
                raise runner.RetryDisclosurePause("Sol reviewed cohort boundary")
            for field, context_key in (("prompt", "prompt"), ("schema", "response_schema")):
                expected = (plan_root / request[f"{field}_path"]).read_bytes()
                require(digest(expected) == request[f"{field}_sha256"] and len(expected) == request[f"{field}_bytes"]
                        and context[context_key]["text"].encode("utf-8") == expected, "Sol frozen payload differs")
            active["request"] = request
            authorize()

        def invoke(**kwargs: Any) -> tuple[str, dict[str, Any]]:
            original_gate = kwargs.get("before_provider_attempt")
            def gate() -> None:
                if original_gate is not None:
                    original_gate()
                authorize()
            content, record = adapter.call_codex(**{**kwargs, "before_provider_attempt": gate})
            return content, {**record, "dryad_sol": dict(active["evidence"])}

        runner._call_codex = invoke
        results = []
        for pass_id in dict.fromkeys(requests[ordinal]["pass_id"] for ordinal in ordinals):
            passed = passes[pass_id]
            artifact = plan_root / passed["input_path"]
            require(digest(artifact.read_bytes()) == passed["source_sha256"], "Sol story source differs")
            output = execution_root / passed["run_path"]
            route = next(row for row in read(queue_root / "routes.json")["routes"] if row["name"] == "codex-chatgpt-gpt-5.6-sol")
            with (directory / f"runner-{uuid.uuid4().hex}.log").open("x", encoding="utf-8") as log, contextlib.redirect_stderr(log):
                try:
                    result = runner.run_judge(artifact_path=artifact, bundle_id="prose.short_story", provider="codex",
                        model="gpt-5.6-sol", reasoning="high", output_dir=output,
                        registry=REPOSITORY / "registry/all_modules.json", bundles=REPOSITORY / "bundles/all_bundles.json",
                        question_ids=[q for row in requests.values() if row["pass_id"] == pass_id for q in row["question_ids"]],
                        batch_size=8, batch_attempts=1, allow_remote=True, resume=(output / "run.json").exists(),
                        artifact_id=passed["logical_sample_id"], judge_id="codex:gpt-5.6-sol", timeout=TIMEOUT,
                        codex_bin=route["codex_command"][0], attempt_lifecycle_policy="terminal_sidecar_v1",
                        response_schema_mode="batch_question_ids_v1", before_provider_attempt=before)
                except runner.RetryDisclosurePause:
                    result = {"status": "PAUSED"}
            results.append({"pass_id": pass_id, "status": result["status"]})
        completed = [ordinal for ordinal in ordinals if (
            execution_root / passes[requests[ordinal]["pass_id"]]["run_path"] / "responses"
            / f"batch-{requests[ordinal]['batch_number']:04d}.json").is_file()]
        return {"cohort_number": cohort, "completed_ordinals": completed, "passes": results,
                "status": "cohort_collected" if completed == ordinals else "paused",
                "full_study_admitted": False}
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
