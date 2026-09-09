"""Provider-free contracts for the one-time Sol 773 replacement executor."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol773_replacement_execution.py"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _module():
    spec = importlib.util.spec_from_file_location("dryad_sol773_replacement_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = _module()
    plan_root = tmp_path / "plan"; (plan_root / "prompts").mkdir(parents=True); (plan_root / "schemas").mkdir(); (plan_root / "inputs").mkdir()
    plan, source, prompt, schema = (plan_root / name for name in ("plan.json", "inputs/source.txt", "prompts/request-0773.txt", "schemas/request-0773.json"))
    source.write_bytes(b"synthetic immutable source")
    prompt_raw = b"Synthetic exact prompt\r\n" + b"x" * (7743 - len(b"Synthetic exact prompt\r\n"))
    schema_value = {"type": "object", "required": ["verdicts"], "additionalProperties": False,
                    "properties": {"verdicts": {"type": "array", "minItems": 8, "maxItems": 8,
                    "items": {"type": "object", "required": ["question_id", "verdict"], "additionalProperties": False,
                    "properties": {"question_id": {"type": "string"}, "verdict": {"type": "string"}}}}}}
    schema_raw = _canonical(schema_value) + b" " * (2542 - len(_canonical(schema_value)))
    prompt.write_bytes(prompt_raw); schema.write_bytes(schema_raw)
    plan_value = {"requests": [{"ordinal": subject.ORDINAL, "batch_number": subject.BATCH, "pass_id": subject.PASS_ID,
                                  "logical_sample_id": subject.LOGICAL_SAMPLE_ID, "question_ids": subject.QUESTION_IDS,
                                  "prompt_path": "prompts/request-0773.txt", "prompt_sha256": _sha(prompt_raw), "prompt_bytes": len(prompt_raw),
                                  "schema_path": "schemas/request-0773.json", "schema_sha256": _sha(schema_raw), "schema_bytes": len(schema_raw)}],
                  "passes": [{"pass_id": subject.PASS_ID, "logical_sample_id": subject.LOGICAL_SAMPLE_ID,
                              "input_path": "inputs/source.txt", "source_sha256": _sha(source.read_bytes()), "source_bytes": len(source.read_bytes()),
                              "batch_size": 8, "batches": 23}]}
    plan.write_bytes(subject._canonical(plan_value))
    monkeypatch.setattr(subject, "PLAN_SHA256", _sha(plan.read_bytes()))
    monkeypatch.setattr(subject, "PROMPT_SHA256", _sha(prompt_raw))
    monkeypatch.setattr(subject, "SCHEMA_SHA256", _sha(schema_raw))
    monkeypatch.setattr(subject, "SOURCE_SHA256", _sha(source.read_bytes()))
    monkeypatch.setattr(subject, "SOURCE_BYTES", len(source.read_bytes()))
    native = tmp_path / "original-native"; native.mkdir(); (native / "immutable.txt").write_bytes(b"preserved")
    cli = tmp_path / "synthetic-codex.exe"; cli.write_bytes(b"synthetic CLI only")
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    auth = {"schema_version": 1, "account_class": "subscription", "provider": "openai_codex", "route": subject.ROUTE_NAME,
            "evidence_class": "chatgpt_subscription_auth_status_v1", "checked_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(), "status_hash": "a" * 64, "audit": {}}
    cost = {"schema_version": 1, "account_class": "subscription", "provider": "openai_codex", "route": subject.ROUTE_NAME,
            "model": subject.MODEL, "kind": "subscription_included", "allowance_state": "available", "checked_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(), "audit": {}}
    auth_path, cost_path = tmp_path / "auth.json", tmp_path / "cost.json"
    auth_path.write_bytes(subject._canonical(auth)); cost_path.write_bytes(subject._canonical(cost))
    route = {"name": subject.ROUTE_NAME, "armed": True, "zero_charge": True, "health": "healthy", "provider": "openai_codex",
             "adapter": "codex_exec", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription",
             "model": subject.MODEL, "reasoning_effort": subject.REASONING, "timeout_seconds": 900,
             "auth_receipt_hash": _sha(auth_path.read_bytes()), "cost_evidence": {**cost, "evidence_hash": _sha(cost_path.read_bytes())},
             "codex_command": [str(cli)], "codex_command_identity": {"artifacts": [{"sha256": _sha(cli.read_bytes())}]}}
    queue = tmp_path / "queue"; queue.mkdir(); (queue / "routes.json").write_bytes(subject._canonical({"routes": [route]}))
    ids = subject.QUESTION_IDS
    output = tmp_path / "replacement-evidence" / subject.NAMESPACE
    manifest = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_v1", "namespace": subject.NAMESPACE,
                "ordinal": subject.ORDINAL, "batch_number": subject.BATCH, "model": subject.MODEL, "reasoning": subject.REASONING,
                "ancestor": copy.deepcopy(subject.ANCESTOR), "plan": {"path": str(plan), "sha256": _sha(plan.read_bytes()), "bytes": len(plan.read_bytes())},
                "prompt": {"path": str(prompt), "sha256": subject.PROMPT_SHA256, "bytes": len(prompt_raw)},
                "schema": {"path": str(schema), "sha256": subject.SCHEMA_SHA256, "bytes": len(schema_raw)},
                "source": {"path": str(source), "sha256": _sha(source.read_bytes()), "bytes": len(source.read_bytes())},
                "question_ids": ids, "native": {"root": str(native), "tree_sha256": subject._tree_sha(native)},
                "original_result_path": str(native / "runs/original-773-result.json"),
                "replacement_root": str(output),
                "route_identity": {key: route[key] for key in ("name", "provider", "adapter", "destination", "account_class", "model", "reasoning_effort", "timeout_seconds", "codex_command", "codex_command_identity")},
                "source_bindings": subject._bindings(), "executor_sha256": _sha(SOURCE.read_bytes())}
    manifest_path = tmp_path / "manifest.json"; manifest_path.write_bytes(subject._canonical(manifest))
    review = {"schema_version": 1, "decision": "approved", "replacement_manifest_sha256": _sha(manifest_path.read_bytes()),
              "executor_sha256": _sha(SOURCE.read_bytes()), "test_source_sha256": _sha(Path(__file__).read_bytes()), "reference": "synthetic review"}
    review_path = tmp_path / "review.json"; review_path.write_bytes(subject._canonical(review))
    decision = {"schema_version": 1, "decision": "approve_sol773_replacement_once", "replacement_manifest_sha256": _sha(manifest_path.read_bytes()),
                "independent_review_sha256": _sha(review_path.read_bytes()), "executor_sha256": _sha(SOURCE.read_bytes()),
                "reference": "synthetic owner decision", "recorded_at": now.isoformat()}
    decision_path = tmp_path / "decision.json"; decision_path.write_bytes(subject._canonical(decision))
    execution = {"schema_version": 1, "evidence_class": "sol773_replacement_execution_binding_v1",
                 "replacement_manifest_sha256": _sha(manifest_path.read_bytes()), "owner_decision_sha256": _sha(decision_path.read_bytes()),
                 "independent_review_sha256": _sha(review_path.read_bytes()), "queue_root": str(queue),
                 "auth_receipt_path": str(auth_path), "cost_receipt_path": str(cost_path), "reviewed_at": now.isoformat(),
                 "expires_at": (now + timedelta(hours=1)).isoformat()}
    execution_path = tmp_path / "execution-binding.json"; execution_path.write_bytes(subject._canonical(execution))
    response = {"verdicts": [{"question_id": item, "verdict": "YES"} for item in ids]}
    calls: list[dict[str, object]] = []
    v3 = subject._load(subject.ADAPTER_PATH, subject.ADAPTER_SHA256, "adapter")._base()

    class Adapter:
        def call_codex(self, *, executable, model, reasoning, prompt, output_dir, response_schema, batch_number, timeout,
                       attempt_number, before_provider_attempt):
            assert executable == route["codex_command"][0] and model == subject.MODEL and reasoning == subject.REASONING
            assert prompt.encode("utf-8") == prompt_raw and response_schema.read_bytes() == schema_raw
            assert (batch_number, timeout, attempt_number) == (subject.BATCH, subject.TIMEOUT, 1)
            before_provider_attempt(); calls.append({"executable": executable, "model": model, "reasoning": reasoning})
            content = json.dumps(response)
            responses = output_dir / "responses"; responses.mkdir(exist_ok=True)
            message = responses / f"batch-{batch_number:04d}.attempt-0001.message.json"; message.write_text(content, encoding="utf-8")
            events = responses / f"batch-{batch_number:04d}.attempt-0001.events.jsonl"
            event_rows = [{"type": "thread.started", "thread_id": "synthetic-thread"}, {"type": "turn.started"},
                          {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": content}},
                          {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0,
                           "cache_write_input_tokens": 0, "output_tokens": 4, "reasoning_output_tokens": 0}}]
            events.write_bytes(b"\n".join(json.dumps(item, separators=(",", ":")).encode() for item in event_rows) + b"\n")
            stderr = responses / f"batch-{batch_number:04d}.attempt-0001.stderr.bin"; stderr.write_bytes(b"")
            command = list(v3._expected_codex_command(executable, output_dir))
            command[command.index("--output-schema") + 1] = str(response_schema)
            command[command.index("--output-last-message") + 1] = str(message)
            command[-1:-1] = ["--disable", "code_mode"]
            descriptor = lambda path: {"path": path.relative_to(output_dir).as_posix(), "bytes": len(path.read_bytes()), "sha256": _sha(path.read_bytes())}
            return content, {"command": command, "reported": v3._strict_stderr_labels(b""),
                             "provider_artifacts": {"codex_events": descriptor(events), "codex_stderr": descriptor(stderr)}}

    def execute(output: Path, adapter: object | None = None, at: datetime | None = None, clock=None):
        return subject.execute_replacement(manifest_path, decision_path, review_path, execution_path, output,
                                           adapter=adapter or Adapter(), now=clock or (lambda: at or now))

    return SimpleNamespace(subject=subject, manifest=manifest, manifest_path=manifest_path, review_path=review_path,
                           decision_path=decision_path, native=native, source=source, prompt=prompt, schema=schema,
                           route=route, queue=queue, auth_path=auth_path, cost_path=cost_path, execution_path=execution_path,
                           ids=ids, response=response, calls=calls, execute=execute, output=output, now=now)


def test_constants_pin_the_real_773_payload_and_ancestry():
    subject = _module()
    assert (subject.ORDINAL, subject.BATCH, subject.PLAN_SHA256, subject.PROMPT_BYTES, subject.SCHEMA_BYTES) == (
        773, 14, "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f", 7743, 2542)
    assert subject.PROMPT_SHA256 == "d3c8ffdfaaabf6cdfe55662da277c33d02aa1a04d68c8cb5cf9cbaa8b82c0c98"
    assert subject.SCHEMA_SHA256 == "6828735e3fc6e2ef61807588f0c66e5e355ec543647cd1c5e4902053b3f2cec9"
    assert subject.ANCESTOR["original_start_sha256"] == "92e959db6be2ad97df73fc1a14b110e361005dccff1f0953127b6c36e1c04a43"
    assert subject.PASS_ID == "baseline8-v1/train/0034/dryad-28525e90bcce269ace039aa7"
    assert len(subject.QUESTION_IDS) == 8 and subject.QUESTION_IDS[0] == "craft.narrative.theme_and_subtext.emergence"


def test_delivers_exact_frozen_payload_once_and_marks_an_amended_descendant(case, tmp_path):
    result = case.execute(case.output)
    assert result["state"] == "replacement_accepted" and len(case.calls) == 1
    output = case.output
    assert (output / "payload/request-0773.txt").read_bytes() == case.prompt.read_bytes()
    assert (output / "payload/request-0773.json").read_bytes() == case.schema.read_bytes()
    assert json.loads((output / "replacement-authorization.json").read_bytes())["authorized_at"] == case.now.isoformat()
    admitted = case.subject.admit_replacement(case.manifest_path, case.decision_path, case.review_path, case.execution_path, output)
    assert admitted["evidence_class"] == "sol773_replacement_amended_descendant_v1"
    assert admitted["original_ordinal"] == 773 and admitted["replacement_is_original"] is False
    assert admitted["full_study_admitted"] is False and admitted["automatic_774_dispatch"] is False


@pytest.mark.parametrize("kind", ["missing_decision", "changed_decision", "changed_review", "payload", "source", "receipt", "ordinal"])
def test_precontact_failures_never_call_fake_adapter(case, tmp_path, kind):
    if kind == "missing_decision":
        case.decision_path.unlink()
    elif kind == "changed_decision":
        value = json.loads(case.decision_path.read_bytes()); value["executor_sha256"] = "0" * 64
        case.decision_path.write_bytes(case.subject._canonical(value))
    elif kind == "changed_review":
        value = json.loads(case.review_path.read_bytes()); value["decision"] = "pending"
        case.review_path.write_bytes(case.subject._canonical(value))
    elif kind == "payload":
        case.prompt.write_bytes(b"changed")
    elif kind == "source":
        case.source.write_bytes(b"changed")
    elif kind == "receipt":
        value = json.loads(case.cost_path.read_bytes()); value["allowance_state"] = "unavailable"
        case.cost_path.write_bytes(case.subject._canonical(value))
    else:
        value = json.loads(case.manifest_path.read_bytes()); value["ordinal"] = 774
        case.manifest_path.write_bytes(case.subject._canonical(value))
    with pytest.raises((FileNotFoundError, ValueError)):
        case.execute(case.output)
    assert not case.calls


@pytest.mark.parametrize("marker", ["replacement-start.json", "replacement-terminal.json"])
def test_existing_start_or_result_prevents_any_replacement_retry(case, marker):
    output = case.output; output.mkdir(parents=True); (output / marker).write_bytes(b"prior")
    with pytest.raises(ValueError, match="evidence already exists"):
        case.execute(output)
    assert not case.calls


def test_designated_root_prevents_a_second_parent_namespace(case, tmp_path):
    with pytest.raises(ValueError, match="namespace"):
        case.execute(tmp_path / "other-parent" / case.subject.NAMESPACE)
    assert not case.calls


def test_adapter_error_is_terminal_and_cannot_be_retried(case, tmp_path):
    class FailingAdapter:
        def call_codex(self, **kwargs):
            kwargs["before_provider_attempt"]()
            case.calls.append(kwargs)
            raise RuntimeError("synthetic crash")
    output = case.output
    result = case.execute(output, FailingAdapter())
    assert result["state"] == "replacement_ambiguous_adapter_failure" and len(case.calls) == 1
    with pytest.raises(ValueError, match="evidence already exists"):
        case.execute(output)
    assert len(case.calls) == 1


def test_native_tree_is_preserved_and_drift_rejects_before_contact(case, tmp_path):
    before = {path.relative_to(case.native): path.read_bytes() for path in case.native.rglob("*") if path.is_file()}
    case.native.joinpath("immutable.txt").write_bytes(b"drift")
    with pytest.raises(ValueError, match="native evidence"):
        case.execute(case.output)
    assert not case.calls
    case.native.joinpath("immutable.txt").write_bytes(before[Path("immutable.txt")])
    assert {path.relative_to(case.native): path.read_bytes() for path in case.native.rglob("*") if path.is_file()} == before


def test_fresh_receipt_renewal_needs_no_new_owner_decision(case):
    auth = json.loads(case.auth_path.read_bytes()); cost = json.loads(case.cost_path.read_bytes())
    renewed = case.now + timedelta(minutes=5)
    for receipt in (auth, cost):
        receipt["checked_at"] = renewed.isoformat(); receipt["expires_at"] = (renewed + timedelta(hours=1)).isoformat()
    case.auth_path.write_bytes(case.subject._canonical(auth)); case.cost_path.write_bytes(case.subject._canonical(cost))
    route = copy.deepcopy(case.route)
    route["auth_receipt_hash"] = _sha(case.auth_path.read_bytes())
    route["cost_evidence"] = {**cost, "evidence_hash": _sha(case.cost_path.read_bytes())}
    (case.queue / "routes.json").write_bytes(case.subject._canonical({"routes": [route]}))
    assert case.execute(case.output, at=renewed)["state"] == "replacement_accepted"
    assert len(case.calls) == 1


@pytest.mark.parametrize("kind", ["revoked", "changed_identity"])
def test_live_queue_drift_rejects_before_contact(case, kind):
    route = copy.deepcopy(case.route)
    if kind == "revoked":
        route["armed"] = False
    else:
        route["timeout_seconds"] = 901
    (case.queue / "routes.json").write_bytes(case.subject._canonical({"routes": [route]}))
    with pytest.raises(ValueError):
        case.execute(case.output)
    assert not case.calls


def test_execution_binding_expiry_rejects_before_contact(case):
    binding = json.loads(case.execution_path.read_bytes())
    binding["expires_at"] = (case.now - timedelta(seconds=1)).isoformat()
    case.execution_path.write_bytes(case.subject._canonical(binding))
    with pytest.raises(ValueError, match="binding"):
        case.execute(case.output)
    assert not case.calls


def test_slow_frozen_scan_resamples_before_contact_and_consumes_only_the_marker(case, monkeypatch):
    binding = json.loads(case.execution_path.read_bytes())
    binding["expires_at"] = (case.now + timedelta(seconds=400)).isoformat()
    case.execution_path.write_bytes(case.subject._canonical(binding))
    auth = json.loads(case.auth_path.read_bytes()); cost = json.loads(case.cost_path.read_bytes())
    for receipt in (auth, cost): receipt["expires_at"] = (case.now + timedelta(seconds=400)).isoformat()
    case.auth_path.write_bytes(case.subject._canonical(auth)); case.cost_path.write_bytes(case.subject._canonical(cost))
    route = copy.deepcopy(case.route); route["auth_receipt_hash"] = _sha(case.auth_path.read_bytes())
    route["cost_evidence"] = {**cost, "evidence_hash": _sha(case.cost_path.read_bytes())}
    (case.queue / "routes.json").write_bytes(case.subject._canonical({"routes": [route]}))
    clock = [case.now]; scans = [0]; original = case.subject._frozen_payload
    def slow(manifest):
        value = original(manifest); scans[0] += 1
        if scans[0] == 2: clock[0] += timedelta(seconds=120)
        return value
    monkeypatch.setattr(case.subject, "_frozen_payload", slow)
    result = case.execute(case.output, clock=lambda: clock[0])
    assert result["state"] == "replacement_ambiguous_adapter_failure" and not case.calls
    assert (case.output / "replacement-start.json").is_file()
    assert not (case.output / "replacement-authorization.json").exists()


@pytest.mark.parametrize("kind", ["terminal", "response", "runtime", "saved_prompt", "saved_schema", "native_message", "schema", "ids", "native", "original_result"])
def test_admission_rejects_tampering_schema_id_drift_and_late_original_result(case, tmp_path, kind):
    output = case.output
    case.execute(output)
    if kind == "terminal":
        value = json.loads((output / "replacement-terminal.json").read_bytes()); value["state"] = "replacement_invalid_response"
        (output / "replacement-terminal.json").write_bytes(case.subject._canonical(value))
    elif kind == "response":
        (output / "replacement-response.json").write_bytes(b"{}")
    elif kind == "runtime":
        (output / "runtime/route.json").write_bytes(b"{}")
    elif kind == "saved_prompt":
        (output / "payload/request-0773.txt").write_bytes(b"changed")
    elif kind == "saved_schema":
        (output / "payload/request-0773.json").write_bytes(b"{}")
    elif kind == "native_message":
        (output / "responses/batch-0014.attempt-0001.message.json").write_bytes(b"{}")
    elif kind == "schema":
        case.schema.write_bytes(b"{}")
    elif kind == "ids":
        value = json.loads((output / "replacement-response.json").read_bytes()); value["verdicts"][0]["question_id"] = "other"
        (output / "replacement-response.json").write_bytes(case.subject._canonical(value))
    elif kind == "native":
        (case.native / "immutable.txt").write_bytes(b"changed")
    else:
        Path(case.manifest["original_result_path"]).parent.mkdir(parents=True, exist_ok=True)
        Path(case.manifest["original_result_path"]).write_bytes(b"late original")
    with pytest.raises(ValueError):
        case.subject.admit_replacement(case.manifest_path, case.decision_path, case.review_path, case.execution_path, output)
