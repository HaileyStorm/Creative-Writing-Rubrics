"""One-time, separately evidenced replacement for the ambiguous original Sol 773."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

import jsonschema

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
ADAPTER_PATH = ROOT / "sol_existing_runtime.py"
ADMISSION_PATH = ROOT / "sol_pass_admission.py"
COLLECTOR_PATH = ROOT / "sol_measurement_execution.py"
TEST_PATH = REPOSITORY / "tests/test_dryad_sol773_replacement_execution.py"
ADAPTER_SHA256 = "da66787bf507bc330abea69c41065d18a355e96339e1e4d4b83055a0159f5087"
ADMISSION_SHA256 = "cd8364c18cbd8a07bc18a9b4d3d0bc1102518cfbed465b9c4f4586245b8eb65d"
COLLECTOR_SHA256 = "b2ed2aa567bbeab3a933a33cf35ccfad81cb2eb47ec0479a57e52962a3a34a40"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
PROMPT_SHA256 = "d3c8ffdfaaabf6cdfe55662da277c33d02aa1a04d68c8cb5cf9cbaa8b82c0c98"
PROMPT_BYTES = 7743
SCHEMA_SHA256 = "6828735e3fc6e2ef61807588f0c66e5e355ec543647cd1c5e4902053b3f2cec9"
SCHEMA_BYTES = 2542
ORDINAL = 773
BATCH = 14
MODEL = "gpt-5.6-sol"
REASONING = "high"
ROUTE_NAME = "codex-chatgpt-gpt-5.6-sol"
NAMESPACE = "sol773-replacement-execution-v1"
TIMEOUT = 300
PASS_ID = "baseline8-v1/train/0034/dryad-28525e90bcce269ace039aa7"
LOGICAL_SAMPLE_ID = "baseline8-v1-train-0034-dryad-28525e90bcce269ace039aa7"
SOURCE_SHA256 = "f5548847a5d566a17aeccb13a6fc8b1ebbc55e303cf54766b0de3ba2b6c80c7c"
SOURCE_BYTES = 793
QUESTION_IDS = [
    "craft.narrative.theme_and_subtext.emergence", "craft.narrative.theme_and_subtext.subtext",
    "craft.narrative.theme_and_subtext.development", "craft.narrative.theme_and_subtext.counterpoint",
    "craft.narrative.theme_and_subtext.integration", "craft.narrative.theme_and_subtext.no_moral",
    "craft.narrative.theme_and_subtext.open_questions", "core.emotional_and_intellectual_effect.intended_effect",
]
ANCESTOR = {
    "original_start_sha256": "92e959db6be2ad97df73fc1a14b110e361005dccff1f0953127b6c36e1c04a43",
    "prefix_reconciliation_sha256": "83e80e62f47f28a4aefef01f39c9455b16108029ab7e8395709b2f27c33ab6cd",
    "interruption_audit_sha256": "4953eb48496d9571ffae5309cb5e4eb33daecaa43a6c513a17e45c4eadffdb4c",
    "reboot_observation_sha256": "2e9f96d92c5fb213078464bbaad44e4916b102c191e87fbd7d294a65f7be641e",
    "pass34_head_sha256": "3593730d357bcc0ccc0bbd0d066a1de9cf445f5b103efe599fca9baf6cdba124",
}
_HEX = set("0123456789abcdef")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _time(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and value.endswith(("Z", "+00:00")), f"{label} differs")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _require(result.tzinfo is not None, f"{label} differs")
    return result.astimezone(timezone.utc)


def _load(path: Path, expected: str, label: str) -> ModuleType:
    _require(_sha(path.read_bytes()) == expected, f"Sol 773 {label} source differs")
    spec = importlib.util.spec_from_file_location(f"_dryad_sol773_{label}", path)
    _require(spec is not None and spec.loader is not None, f"Sol 773 {label} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bindings() -> dict[str, str]:
    return {"collector": _sha(COLLECTOR_PATH.read_bytes()), "adapter": _sha(ADAPTER_PATH.read_bytes()),
            "admission": _sha(ADMISSION_PATH.read_bytes())}


def _tree_sha(root: Path) -> str:
    _require(root.is_dir(), "Sol 773 native root differs")
    rows = [{"path": path.relative_to(root).as_posix(), "sha256": _sha(path.read_bytes())}
            for path in sorted(root.rglob("*")) if path.is_file()]
    return _sha(_canonical(rows))


def _read_exact(path: Path, expected_sha256: str, expected_bytes: int, label: str) -> bytes:
    raw = path.read_bytes()
    _require(_sha(raw) == expected_sha256 and len(raw) == expected_bytes, f"Sol 773 {label} differs")
    return raw


def _execution_binding(path: Path, manifest_raw: bytes, decision_raw: bytes, review_raw: bytes,
                       *, at: datetime | None = None) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes(); value = _json(raw, "Sol 773 execution binding")
    expected = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_binding_v1",
                "replacement_manifest_sha256": _sha(manifest_raw), "owner_decision_sha256": _sha(decision_raw),
                "independent_review_sha256": _sha(review_raw)}
    _require(set(value) == set(expected) | {"queue_root", "auth_receipt_path", "cost_receipt_path", "reviewed_at", "expires_at"}
             and all(value.get(key) == item for key, item in expected.items())
             and all(isinstance(value.get(key), str) and value[key] for key in ("queue_root", "auth_receipt_path", "cost_receipt_path")),
             "Sol 773 execution binding differs")
    reviewed, expires = (_time(value[key], f"Sol 773 execution binding {key}") for key in ("reviewed_at", "expires_at"))
    _require(reviewed < expires <= reviewed + timedelta(hours=2), "Sol 773 execution binding window differs")
    if at is not None:
        _require(reviewed <= at and at + timedelta(seconds=TIMEOUT) < expires,
                 "Sol 773 execution binding requires renewal")
    return raw, value


def _fresh_route(manifest: Mapping[str, Any], execution: Mapping[str, Any], now: datetime) -> tuple[dict[str, Any], bytes, bytes]:
    registry_raw = (Path(execution["queue_root"]) / "routes.json").read_bytes()
    registry = _json(registry_raw, "Sol 773 route registry")
    routes = registry.get("routes")
    _require(isinstance(routes, list), "Sol 773 route registry differs")
    route = next((item for item in routes if isinstance(item, Mapping) and item.get("name") == ROUTE_NAME), None)
    _require(isinstance(route, dict) and route.get("armed") is True
             and route.get("zero_charge") is True and route.get("health") == "healthy"
             and route.get("provider") == "openai_codex" and route.get("adapter") == "codex_exec"
             and route.get("destination") == "openai_codex_chatgpt_subscription"
             and route.get("account_class") == "subscription" and route.get("model") == MODEL
             and route.get("reasoning_effort") == REASONING and route.get("timeout_seconds") == 900,
             "Sol 773 live route differs")
    stable_keys = {"name", "provider", "adapter", "destination", "account_class", "model", "reasoning_effort", "timeout_seconds", "codex_command", "codex_command_identity"}
    _require(manifest["route_identity"] == {key: route[key] for key in stable_keys}, "Sol 773 immutable route identity differs")
    auth_raw = Path(execution["auth_receipt_path"]).read_bytes()
    cost_raw = Path(execution["cost_receipt_path"]).read_bytes()
    strict = _load(ADMISSION_PATH, ADMISSION_SHA256, "admission")
    auth, cost = strict._json(auth_raw, "Sol 773 auth receipt"), strict._json(cost_raw, "Sol 773 cost receipt")
    _require(strict._canonical(auth) == auth_raw and strict._canonical(cost) == cost_raw
             and route.get("auth_receipt_hash") == _sha(auth_raw)
             and isinstance(route.get("cost_evidence"), Mapping)
             and route["cost_evidence"].get("evidence_hash") == _sha(cost_raw), "Sol 773 receipt binding differs")
    auth_keys = {"schema_version", "account_class", "provider", "route", "evidence_class", "checked_at", "expires_at", "status_hash", "audit"}
    cost_keys = {"schema_version", "account_class", "provider", "route", "model", "kind", "allowance_state", "checked_at", "expires_at", "audit"}
    _require(set(auth) == auth_keys and set(cost) == cost_keys and auth.get("schema_version") == cost.get("schema_version") == 1
             and auth.get("account_class") == cost.get("account_class") == "subscription"
             and auth.get("provider") == cost.get("provider") == "openai_codex"
             and auth.get("route") == cost.get("route") == ROUTE_NAME
             and auth.get("evidence_class") == "chatgpt_subscription_auth_status_v1" and strict._hex(auth.get("status_hash"))
             and isinstance(auth.get("audit"), Mapping) and isinstance(cost.get("audit"), Mapping)
             and cost.get("model") == MODEL and cost.get("kind") == "subscription_included"
             and cost.get("allowance_state") == "available", "Sol 773 included allowance differs")
    _require(all(route["cost_evidence"].get(key) == cost.get(key) for key in ("checked_at", "expires_at", "kind", "allowance_state")),
             "Sol 773 cost receipt projection differs")
    executable = Path(route["codex_command"][0])
    _require(executable.is_file() and _sha(executable.read_bytes()) == route["codex_command_identity"]["artifacts"][0]["sha256"],
             "Sol 773 CLI differs")
    for receipt, label in ((auth, "auth"), (cost, "cost")):
        checked, expires = strict._time(receipt["checked_at"], label), strict._time(receipt["expires_at"], label)
        _require(checked <= now and now + timedelta(seconds=TIMEOUT) < expires, "Sol 773 receipt requires refresh")
    return route, auth_raw, cost_raw


def _manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes(); value = _json(raw, "Sol 773 replacement manifest")
    required = {"schema_version", "evidence_class", "namespace", "ordinal", "batch_number", "model", "reasoning",
                "ancestor", "plan", "prompt", "schema", "source", "question_ids", "native", "original_result_path", "replacement_root",
                "route_identity", "source_bindings", "executor_sha256"}
    _require(set(value) == required and value["schema_version"] == 1
             and value["evidence_class"] == "sol773_replacement_execution_v1" and value["namespace"] == NAMESPACE
             and value["ordinal"] == ORDINAL and value["batch_number"] == BATCH
             and value["model"] == MODEL and value["reasoning"] == REASONING and value["ancestor"] == ANCESTOR
             and value["executor_sha256"] == _sha(Path(__file__).read_bytes())
             and value["source_bindings"] == _bindings(), "Sol 773 immutable manifest differs")
    _require(value["question_ids"] == QUESTION_IDS, "Sol 773 question IDs differ")
    for key, expected_sha, expected_bytes in (("prompt", PROMPT_SHA256, PROMPT_BYTES), ("schema", SCHEMA_SHA256, SCHEMA_BYTES)):
        binding = value[key]
        _require(isinstance(binding, Mapping) and set(binding) == {"path", "sha256", "bytes"}
                 and binding["sha256"] == expected_sha and binding["bytes"] == expected_bytes, f"Sol 773 {key} binding differs")
    for key in ("plan", "source"):
        binding = value[key]
        _require(isinstance(binding, Mapping) and set(binding) == {"path", "sha256", "bytes"} and _hex(binding["sha256"])
                 and type(binding["bytes"]) is int and binding["bytes"] >= 0, f"Sol 773 {key} binding differs")
    _require(value["plan"]["sha256"] == PLAN_SHA256 and value["source"]["sha256"] == SOURCE_SHA256
             and value["source"]["bytes"] == SOURCE_BYTES and isinstance(value["native"], Mapping)
             and set(value["native"]) == {"root", "tree_sha256"} and _hex(value["native"]["tree_sha256"])
             and isinstance(value["original_result_path"], str) and isinstance(value["replacement_root"], str) and isinstance(value["route_identity"], Mapping)
             and set(value["route_identity"]) == {"name", "provider", "adapter", "destination", "account_class", "model", "reasoning_effort", "timeout_seconds", "codex_command", "codex_command_identity"}
             and value["route_identity"].get("name") == ROUTE_NAME and value["route_identity"].get("provider") == "openai_codex"
             and value["route_identity"].get("adapter") == "codex_exec" and value["route_identity"].get("destination") == "openai_codex_chatgpt_subscription"
             and value["route_identity"].get("account_class") == "subscription" and value["route_identity"].get("model") == MODEL
             and value["route_identity"].get("reasoning_effort") == REASONING and value["route_identity"].get("timeout_seconds") == 900,
             "Sol 773 replacement bindings differ")
    return raw, value


def _review(path: Path, manifest_raw: bytes) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes(); value = _json(raw, "Sol 773 independent review")
    expected = {"schema_version": 1, "decision": "approved", "replacement_manifest_sha256": _sha(manifest_raw),
                "executor_sha256": _sha(Path(__file__).read_bytes()), "test_source_sha256": _sha(TEST_PATH.read_bytes())}
    _require(set(value) == set(expected) | {"reference"} and all(value.get(key) == item for key, item in expected.items())
             and isinstance(value.get("reference"), str) and bool(value["reference"].strip()), "Sol 773 independent review differs")
    return raw, value


def _decision(path: Path, manifest_raw: bytes, review_raw: bytes) -> dict[str, Any]:
    value = _json(path.read_bytes(), "Sol 773 owner decision")
    expected = {"schema_version": 1, "decision": "approve_sol773_replacement_once",
                "replacement_manifest_sha256": _sha(manifest_raw), "independent_review_sha256": _sha(review_raw),
                "executor_sha256": _sha(Path(__file__).read_bytes())}
    _require(set(value) == set(expected) | {"reference", "recorded_at"}
             and all(value.get(key) == item for key, item in expected.items())
             and isinstance(value.get("reference"), str) and bool(value["reference"].strip()), "Sol 773 owner decision differs")
    _time(value["recorded_at"], "Sol 773 owner decision time")
    return value


def _frozen_payload(manifest: Mapping[str, Any]) -> tuple[bytes, bytes]:
    native = Path(manifest["native"]["root"])
    _require(_tree_sha(native) == manifest["native"]["tree_sha256"], "Sol 773 native evidence differs")
    _require(not Path(manifest["original_result_path"]).is_file(), "Sol 773 original result now exists; reconciliation is required")
    plan_path = Path(manifest["plan"]["path"])
    plan = _json(_read_exact(plan_path, manifest["plan"]["sha256"], manifest["plan"]["bytes"], "plan"), "Sol 773 plan")
    source = _read_exact(Path(manifest["source"]["path"]), manifest["source"]["sha256"], manifest["source"]["bytes"], "source")
    prompt = _read_exact(Path(manifest["prompt"]["path"]), PROMPT_SHA256, PROMPT_BYTES, "prompt")
    schema = _read_exact(Path(manifest["schema"]["path"]), SCHEMA_SHA256, SCHEMA_BYTES, "schema")
    request = next((item for item in plan.get("requests", []) if isinstance(item, Mapping) and item.get("ordinal") == ORDINAL), None)
    passed = next((item for item in plan.get("passes", []) if isinstance(item, Mapping) and item.get("pass_id") == PASS_ID), None)
    _require(isinstance(request, Mapping) and isinstance(passed, Mapping)
             and request.get("batch_number") == BATCH and request.get("pass_id") == PASS_ID
             and request.get("logical_sample_id") == LOGICAL_SAMPLE_ID and request.get("question_ids") == QUESTION_IDS
             and request.get("prompt_sha256") == manifest["prompt"]["sha256"] and request.get("prompt_bytes") == manifest["prompt"]["bytes"]
             and request.get("schema_sha256") == manifest["schema"]["sha256"] and request.get("schema_bytes") == manifest["schema"]["bytes"]
             and passed.get("logical_sample_id") == LOGICAL_SAMPLE_ID and passed.get("source_sha256") == SOURCE_SHA256
             and passed.get("source_bytes") == SOURCE_BYTES and passed.get("batch_size") == 8 and passed.get("batches") == 23
             and Path(manifest["source"]["path"]).resolve() == (plan_path.parent / passed.get("input_path", "")).resolve()
             and Path(manifest["prompt"]["path"]).resolve() == (plan_path.parent / request.get("prompt_path", "")).resolve()
             and Path(manifest["schema"]["path"]).resolve() == (plan_path.parent / request.get("schema_path", "")).resolve()
             and source, "Sol 773 frozen plan provenance differs")
    return prompt, schema


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _terminal(root: Path, state: str, start_raw: bytes, **extra: Any) -> dict[str, Any]:
    value = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_v1", "state": state,
             "start_sha256": _sha(start_raw), "original_ordinal": ORDINAL, "replacement_is_original": False,
             "full_study_admitted": False, **extra}
    _write_new(root / "replacement-terminal.json", _canonical(value))
    return value


def execute_replacement(manifest_path: Path, owner_decision_path: Path, independent_review_path: Path, execution_binding_path: Path, output_root: Path,
                        *, adapter: Any | None = None, now: Callable[[], datetime] | None = None) -> dict[str, Any]:
    """Perform one adapter call only after all immutable and fresh-contact checks pass."""
    manifest_raw, manifest = _manifest(Path(manifest_path))
    review_raw, _ = _review(Path(independent_review_path), manifest_raw)
    decision_raw = Path(owner_decision_path).read_bytes()
    _decision(Path(owner_decision_path), manifest_raw, review_raw)
    output_root = Path(output_root).resolve(); native = Path(manifest["native"]["root"]).resolve()
    _require(output_root == Path(manifest["replacement_root"]).resolve() and output_root.name == NAMESPACE
             and output_root != native and not output_root.is_relative_to(native),
             "Sol 773 replacement namespace differs")
    _require(not output_root.exists() or not any(output_root.iterdir()), "Sol 773 replacement evidence already exists")
    prompt, schema = _frozen_payload(manifest)
    now_value = (now or (lambda: datetime.now(timezone.utc)))()
    _require(now_value.tzinfo is not None, "Sol 773 clock differs")
    execution_raw, execution = _execution_binding(Path(execution_binding_path), manifest_raw, decision_raw, review_raw,
                                                   at=now_value.astimezone(timezone.utc))
    route, auth_raw, cost_raw = _fresh_route(manifest, execution, now_value.astimezone(timezone.utc))
    output_root.mkdir(parents=True, exist_ok=True)
    _write_new(output_root / "payload/request-0773.txt", prompt)
    _write_new(output_root / "payload/request-0773.json", schema)
    start = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_v1", "state": "replacement_started",
             "original_ordinal": ORDINAL, "replacement_is_original": False, "manifest_sha256": _sha(manifest_raw),
             "owner_decision_sha256": _sha(Path(owner_decision_path).read_bytes()), "review_sha256": _sha(review_raw),
             "payload": {"prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}}
    start_raw = _canonical(start); _write_new(output_root / "replacement-start.json", start_raw)
    snapshot_schema = output_root / "payload/request-0773.json"

    def before_contact() -> None:
        current_manifest_raw, current_manifest = _manifest(Path(manifest_path))
        current_review_raw, _ = _review(Path(independent_review_path), current_manifest_raw)
        fresh_prompt, fresh_schema = _frozen_payload(current_manifest)
        current = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
        current_execution_raw, current_execution = _execution_binding(Path(execution_binding_path), current_manifest_raw, decision_raw, current_review_raw,
                                                                       at=current)
        _require(current_manifest_raw == manifest_raw and current_manifest == manifest and current_review_raw == review_raw
                 and Path(owner_decision_path).read_bytes() == decision_raw, "Sol 773 reviewed binding changed")
        _decision(Path(owner_decision_path), current_manifest_raw, current_review_raw)
        fresh_route, fresh_auth, fresh_cost = _fresh_route(manifest, current_execution, current)
        _require(fresh_prompt == prompt and fresh_schema == schema
                 and snapshot_schema.read_bytes() == schema and (output_root / "replacement-start.json").read_bytes() == start_raw,
                 "Sol 773 pre-contact binding differs")
        _write_new(output_root / "runtime/route.json", _canonical(fresh_route))
        _write_new(output_root / "runtime/auth-receipt.json", fresh_auth)
        _write_new(output_root / "runtime/cost-receipt.json", fresh_cost)
        authorization = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_v1", "state": "replacement_authorized",
                         "start_sha256": _sha(start_raw), "execution_binding_sha256": _sha(current_execution_raw),
                         "authorized_at": current.isoformat(), "runtime": {"route_sha256": _sha(_canonical(fresh_route)),
                         "auth_receipt_sha256": _sha(fresh_auth), "cost_receipt_sha256": _sha(fresh_cost)}}
        _write_new(output_root / "replacement-authorization.json", _canonical(authorization))

    runtime = adapter or _load(ADAPTER_PATH, ADAPTER_SHA256, "adapter")
    try:
        content, record = runtime.call_codex(prompt=prompt.decode("utf-8"), output_dir=output_root, response_schema=snapshot_schema,
                                             executable=route["codex_command"][0], model=MODEL, reasoning=REASONING,
                                             batch_number=BATCH, timeout=TIMEOUT, attempt_number=1,
                                             before_provider_attempt=before_contact)
    except Exception as error:  # The marker permanently consumes the one permitted replacement attempt.
        return _terminal(output_root, "replacement_ambiguous_adapter_failure", start_raw, error_type=type(error).__name__)
    try:
        _require(isinstance(content, str) and isinstance(record, Mapping), "Sol 773 adapter result differs")
        response = _json(content.encode("utf-8"), "Sol 773 replacement response")
        jsonschema.validate(response, json.loads(schema.decode("utf-8")))
        verdicts = response.get("verdicts")
        _require(isinstance(verdicts, list) and [row.get("question_id") if isinstance(row, Mapping) else None for row in verdicts]
                 == manifest["question_ids"], "Sol 773 replacement response IDs differ")
    except Exception as error:
        return _terminal(output_root, "replacement_invalid_response", start_raw, error_type=type(error).__name__)
    _write_new(output_root / "replacement-response.json", content.encode("utf-8"))
    _write_new(output_root / "replacement-provider-record.json", _canonical(dict(record)))
    return _terminal(output_root, "replacement_accepted", start_raw, response_sha256=_sha(content.encode("utf-8")),
                     provider_record_sha256=_sha(_canonical(dict(record))), replacement_accepted=True)


def admit_replacement(manifest_path: Path, owner_decision_path: Path, independent_review_path: Path, execution_binding_path: Path, output_root: Path) -> dict[str, Any]:
    """Read a separately accepted replacement without promoting it to original or full-study evidence."""
    manifest_raw, manifest = _manifest(Path(manifest_path))
    review_raw, _ = _review(Path(independent_review_path), manifest_raw)
    decision_raw = Path(owner_decision_path).read_bytes()
    _decision(Path(owner_decision_path), manifest_raw, review_raw)
    _require(not Path(manifest["original_result_path"]).is_file(), "Sol 773 original result now exists; reconciliation is required")
    root = Path(output_root).resolve()
    native = Path(manifest["native"]["root"]).resolve()
    _require(root == Path(manifest["replacement_root"]).resolve() and root.name == NAMESPACE
             and root != native and not root.is_relative_to(native), "Sol 773 replacement namespace differs")
    prompt, schema = _frozen_payload(manifest)
    _require((root / "payload/request-0773.txt").read_bytes() == prompt
             and (root / "payload/request-0773.json").read_bytes() == schema,
             "Sol 773 replacement saved payload differs")
    start_raw = (root / "replacement-start.json").read_bytes()
    terminal_raw = (root / "replacement-terminal.json").read_bytes(); terminal = _json(terminal_raw, "Sol 773 replacement terminal")
    start = _json(start_raw, "Sol 773 replacement start")
    authorization_raw = (root / "replacement-authorization.json").read_bytes()
    authorization = _json(authorization_raw, "Sol 773 replacement authorization")
    authorized = _time(authorization.get("authorized_at"), "Sol 773 replacement authorization time")
    execution_raw, _ = _execution_binding(Path(execution_binding_path), manifest_raw, decision_raw, review_raw, at=authorized)
    expected_start = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_v1", "state": "replacement_started",
                      "original_ordinal": ORDINAL, "replacement_is_original": False, "manifest_sha256": _sha(manifest_raw),
                      "owner_decision_sha256": _sha(decision_raw), "review_sha256": _sha(review_raw),
                      "payload": {"prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}}
    route_raw = (root / "runtime/route.json").read_bytes()
    auth_raw = (root / "runtime/auth-receipt.json").read_bytes()
    cost_raw = (root / "runtime/cost-receipt.json").read_bytes()
    route = _json(route_raw, "Sol 773 replacement route")
    strict = _load(ADMISSION_PATH, ADMISSION_SHA256, "admission")
    _require(_canonical(route) == route_raw and strict._canonical(strict._json(auth_raw, "Sol 773 replacement auth")) == auth_raw
             and strict._canonical(strict._json(cost_raw, "Sol 773 replacement cost")) == cost_raw
             and all(key in route for key in manifest["route_identity"])
             and manifest["route_identity"] == {key: route[key] for key in manifest["route_identity"]}
             and route.get("armed") is True and route.get("zero_charge") is True and route.get("health") == "healthy"
             and route.get("auth_receipt_hash") == _sha(auth_raw) and route.get("cost_evidence", {}).get("evidence_hash") == _sha(cost_raw),
             "Sol 773 replacement runtime evidence differs")
    runtime = {"route_sha256": _sha(route_raw), "auth_receipt_sha256": _sha(auth_raw), "cost_receipt_sha256": _sha(cost_raw)}
    auth_snapshot = _json(auth_raw, "Sol 773 replacement auth")
    expected_authorization = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_v1", "state": "replacement_authorized",
                              "start_sha256": _sha(start_raw), "execution_binding_sha256": _sha(execution_raw),
                              "authorized_at": authorization.get("authorized_at"), "runtime": runtime}
    _require(start == expected_start and authorization == expected_authorization
             and _time(auth_snapshot["checked_at"], "Sol 773 replacement auth checked") <= authorized < _time(auth_snapshot["expires_at"], "Sol 773 replacement auth expiry")
             and terminal == {**terminal, "start_sha256": _sha(start_raw)}
             and terminal.get("state") == "replacement_accepted"
             and terminal.get("replacement_is_original") is False and terminal.get("full_study_admitted") is False,
             "Sol 773 replacement is not admissible")
    response_raw = (root / "replacement-response.json").read_bytes()
    record_raw = (root / "replacement-provider-record.json").read_bytes()
    _require((root / f"responses/batch-{BATCH:04d}.attempt-0001.message.json").read_bytes() == response_raw,
             "Sol 773 replacement native final message differs")
    _require(terminal.get("response_sha256") == _sha(response_raw)
             and terminal.get("provider_record_sha256") == _sha(record_raw), "Sol 773 replacement response differs")
    response = _json(response_raw, "Sol 773 replacement response")
    record = _json(record_raw, "Sol 773 replacement provider record")
    _require(_canonical(record) == record_raw, "Sol 773 replacement provider record differs")
    adapter = _load(ADAPTER_PATH, ADAPTER_SHA256, "adapter")
    v3 = adapter._base()
    runner = _load(COLLECTOR_PATH, COLLECTOR_SHA256, "collector")._private_runner()
    expected_command = list(v3._expected_codex_command(route["codex_command"][0], root))
    expected_command[expected_command.index("--output-schema") + 1] = str(root / "payload/request-0773.json")
    expected_command[expected_command.index("--output-last-message") + 1] = str(root / f"responses/batch-{BATCH:04d}.attempt-0001.message.json")
    expected_command[-1:-1] = ["--disable", "code_mode"]
    artifacts = record.get("provider_artifacts")
    _require(record.get("command") == expected_command and isinstance(artifacts, Mapping)
             and set(artifacts) == {"codex_events", "codex_stderr"}, "Sol 773 replacement native command differs")
    for descriptor in artifacts.values():
        _require(isinstance(descriptor, Mapping) and isinstance(descriptor.get("path"), str)
                 and runner._provider_artifact(root, root / descriptor["path"]) == dict(descriptor),
                 "Sol 773 replacement native artifact differs")
    stderr = (root / artifacts["codex_stderr"]["path"]).read_bytes()
    labels = v3._strict_stderr_labels(stderr)
    events = (root / artifacts["codex_events"]["path"]).read_bytes()
    projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
    _require(record.get("reported") == labels and projection.get("completed_agent_message_text", "").encode("utf-8") == response_raw
             and isinstance(projection.get("thread_id"), str) and projection["thread_id"]
             and isinstance(projection.get("usage"), dict), "Sol 773 replacement native event evidence differs")
    jsonschema.validate(response, json.loads(schema.decode("utf-8")))
    verdicts = response.get("verdicts")
    _require(isinstance(verdicts, list) and [row.get("question_id") if isinstance(row, Mapping) else None for row in verdicts]
             == manifest["question_ids"], "Sol 773 replacement response IDs differ")
    return {"evidence_class": "sol773_replacement_amended_descendant_v1", "original_ordinal": ORDINAL,
            "replacement_is_original": False, "full_study_admitted": False, "automatic_774_dispatch": False,
            "owner_decision_sha256": _sha(Path(owner_decision_path).read_bytes()), "review_sha256": _sha(review_raw),
            "manifest_sha256": _sha(manifest_raw), "response_sha256": _sha(response_raw), "verdicts": verdicts}
