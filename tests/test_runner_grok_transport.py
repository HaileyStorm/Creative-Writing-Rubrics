"""Local transport doubles only: no provider contact or host-gate authority."""

from copy import deepcopy
import hashlib
import json

import pytest

from hbqrs import HBQError, book_root, run_judge as public_run_judge
from hbqrs import runner


QUESTION = "core.task_and_brief_fidelity.operation"
BINDING = "a" * 64


def run(root, transport, *, public=False, **overrides):
    artifact = root / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    arguments = dict(
        artifact_path=artifact, bundle_id="prose.scene", provider="grok",
        model="grok-4.6", output_dir=root / "run",
        registry=book_root() / "registry/all_modules.json",
        bundles=book_root() / "bundles/all_bundles.json", question_ids=[QUESTION],
        allow_remote=True, allow_unattested_reasoning=True, batch_attempts=1,
        attempt_lifecycle_policy=runner.ATTEMPT_LIFECYCLE_POLICY,
        grok_transport=transport, grok_transport_sha256=BINDING,
    )
    arguments.update(overrides)
    return (public_run_judge if public else runner.run_judge)(**arguments)


def answer(context):
    return json.dumps({"verdicts": [{
        "question_id": item, "verdict": "YES", "confidence": 0.8,
        "evidence": [{"kind": "exact_quote", "reference": "line:1",
                      "exact_quote": "A short test scene.", "summary": None}],
        "note": "Local fixture.",
    } for item in context["batch"]["question_ids"]]}), {"model": "grok-4.6", "evidence_sha256": "f" * 64, "tool_free": True}


@pytest.fixture(autouse=True)
def no_cli(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("Injected transport reached legacy CLI")
    monkeypatch.setattr(runner, "_call_grok", forbidden)


@pytest.mark.parametrize("public", [False, True])
def test_exact_context_success_and_completed_resume(tmp_path, public):
    contexts = []
    events = []

    def before(context):
        events.append("before")
        contexts.append(deepcopy(context))
        context["prompt"]["text"] = "Mutation must not reach transport"

    def transport(context):
        events.append("transport")
        assert context == contexts[-1]
        start = tmp_path / "run/responses/attempt-lifecycle/batch-0001/attempt-0001.start.json"
        assert start.is_file()
        for field in ("prompt", "response_schema"):
            raw = context[field]["text"].encode("utf-8")
            assert len(raw) == context[field]["bytes"]
            assert hashlib.sha256(raw).hexdigest() == context[field]["sha256"]
        assert context["batch"] == {"number": 1, "question_ids": [QUESTION]}
        assert context["attempt"] == {"number": 1, "batch_attempts": 1}
        assert context["transport"]["declared_sha256"] == BINDING
        assert context["transport"]["timeout"] == 42
        return answer(context)

    result = run(tmp_path, transport, before_provider_attempt=before, timeout=42, public=public)
    assert result["verdicts"] == 1
    before_bytes = {p: p.read_bytes() for p in (tmp_path / "run").rglob("*") if p.is_file()}
    run(tmp_path, transport, before_provider_attempt=before, timeout=42, resume=True, public=public, grok_bin="unused-changed")
    assert events == ["before", "transport"]
    assert all(p.read_bytes() == raw for p, raw in before_bytes.items())
    if public:
        assert result["status"] == "DIAGNOSTIC_SUBSET"


@pytest.mark.parametrize("error", [OSError, HBQError, RuntimeError])
def test_exception_is_sanitized_terminal_and_never_resent(tmp_path, error):
    calls = []
    def transport(context):
        calls.append(context)
        raise error("DO_NOT_PERSIST_TRANSPORT_DETAIL")
    with pytest.raises(HBQError, match="not retryable") as caught:
        run(tmp_path, transport)
    assert "DO_NOT_PERSIST" not in str(caught.value)
    with pytest.raises(HBQError, match="terminal nonretryable"):
        run(tmp_path, transport, resume=True)
    assert len(calls) == 1
    assert all(b"DO_NOT_PERSIST" not in p.read_bytes() for p in (tmp_path / "run").rglob("*") if p.is_file())


@pytest.mark.parametrize("result", [None, ("{}",), (42, {}), ("{}", []), ("{}", {"bad": object()}), ("{}", {"bad": float("nan")})])
def test_malformed_transport_result_is_terminal(tmp_path, result):
    calls = []
    def transport(context):
        calls.append(context)
        return result
    with pytest.raises(HBQError, match="not retryable"):
        run(tmp_path, transport)
    with pytest.raises(HBQError, match="terminal nonretryable"):
        run(tmp_path, transport, resume=True)
    assert len(calls) == 1
    assert not (tmp_path / "run/responses/batch-0001.json").exists()


@pytest.mark.parametrize("overrides", [
    {"batch_attempts": 3}, {"attempt_lifecycle_policy": None},
    {"grok_transport_sha256": None}, {"grok_transport_sha256": "not-a-hash"},
    {"grok_transport_sha256": "A" * 64}, {"provider": "codex", "allow_unattested_reasoning": False},
    {"grok_transport": 42}, {"grok_transport": None},
])
def test_invalid_injection_contract_is_rejected_before_run(tmp_path, overrides):
    with pytest.raises(HBQError, match="grok_transport"):
        run(tmp_path, answer, **overrides)
    assert not (tmp_path / "run").exists()


def test_dry_run_and_precontact_pause_do_not_invoke_transport(tmp_path):
    def forbidden(context):
        pytest.fail("Unexpected transport call")
    assert run(tmp_path, forbidden, dry_run=True)["status"] == "DRY_RUN"

    def pause(context):
        raise runner.RetryDisclosurePause("local pause")
    with pytest.raises(runner.RetryDisclosurePause):
        run(tmp_path, forbidden, resume=True, before_provider_attempt=pause)
    assert not list((tmp_path / "run").rglob("*.start.json"))


@pytest.mark.parametrize("overrides", [{"grok_transport_sha256": "b" * 64}, {"timeout": 43}, {"grok_transport": None, "grok_transport_sha256": None}])
def test_resume_rejects_transport_identity_or_mode_drift(tmp_path, overrides):
    run(tmp_path, answer, dry_run=True)
    with pytest.raises(HBQError, match="Cannot resume"):
        run(tmp_path, answer, resume=True, **overrides)


def test_interrupted_transport_remains_ambiguous_on_resume(tmp_path):
    calls = []
    def interrupted(context):
        calls.append(context)
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, interrupted)
    with pytest.raises(HBQError, match="ambiguous"):
        run(tmp_path, interrupted, resume=True)
    assert len(calls) == 1


def test_invalid_model_output_exhausts_one_attempt_without_resend(tmp_path):
    calls = []
    def invalid(context):
        calls.append(context)
        return "not json", answer(context)[1]
    with pytest.raises(HBQError, match="exhausted 1"):
        run(tmp_path, invalid)
    with pytest.raises(HBQError, match="exhausted 1"):
        run(tmp_path, invalid, resume=True)
    assert len(calls) == 1


@pytest.mark.parametrize("metadata", [
    {"model": "wrong", "evidence_sha256": "f" * 64},
    {"model": "grok-4.6", "evidence_sha256": "raw data"},
    {"model": "grok-4.6", "evidence_sha256": "f" * 64, "secret": "DO_NOT_PERSIST"},
    {"model": "grok-4.6", "evidence_sha256": "f" * 64, "tool_free": 1},
    {"model": "grok-4.6", "evidence_sha256": "f" * 64, 1: "DO_NOT_PERSIST"},
])
def test_non_allowlisted_metadata_never_persists(tmp_path, metadata):
    with pytest.raises(HBQError, match="contact outcome unknown"):
        run(tmp_path, lambda context: (answer(context)[0], metadata))
    assert all(b"DO_NOT_PERSIST" not in p.read_bytes() for p in (tmp_path / "run").rglob("*") if p.is_file())


@pytest.mark.parametrize("allow_remote", [False, True])
def test_disclosure_exposes_injected_transport_binding(tmp_path, capsys, allow_remote):
    if allow_remote:
        result = run(tmp_path, answer, dry_run=True)
    else:
        with pytest.raises(HBQError, match="off-machine"):
            run(tmp_path, answer, allow_remote=False)
    disclosure = json.loads(capsys.readouterr().err)["disclosure"]
    assert disclosure["destination"] == "Injected reviewed-caller transport -> authenticated xAI service"
    assert disclosure["grok_transport"] == {
        "protocol": "injected_grok_attempt_v1", "declared_sha256": BINDING,
        "identity_evidence": "caller_declared_unverified", "timeout": 600.0,
    }
    if allow_remote:
        assert result["grok_transport"] == disclosure["grok_transport"]


@pytest.mark.parametrize("attested", [None, False, True])
def test_reasoning_policy_is_enforced(tmp_path, attested):
    def transport(context):
        content, metadata = answer(context)
        if attested is not None:
            metadata["reasoning_attested"] = attested
        return content, metadata
    if attested is True:
        assert run(tmp_path, transport, allow_unattested_reasoning=False)["verdicts"] == 1
    else:
        with pytest.raises(HBQError, match="contact outcome unknown"):
            run(tmp_path, transport, allow_unattested_reasoning=False)


@pytest.mark.parametrize("tool_free", [None, False])
def test_tool_free_assertion_is_required(tmp_path, tool_free):
    def transport(context):
        content, metadata = answer(context)
        metadata.pop("tool_free")
        if tool_free is not None:
            metadata["tool_free"] = tool_free
        return content, metadata
    with pytest.raises(HBQError, match="contact outcome unknown"):
        run(tmp_path, transport)
