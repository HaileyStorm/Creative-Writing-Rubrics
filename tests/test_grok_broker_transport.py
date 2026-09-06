"""Optional installed-broker integration, isolated SQLite gates and fake CLI only.

These tests prove local wiring, not provider contact or an empirical batch cap.
"""

import hashlib
import importlib
import json
from pathlib import Path
import sys

import pytest

from hbqrs import HBQError, book_root, run_judge
from hbqrs import runner
from hbqrs.grok_broker_transport import bind_grok_broker_transport


SHARED = Path.home() / ".codex/tools/model_work_queue"
PINS = {
    "broker.py": "8869b4500760ede3b6b8c199c349b081cd5bd51bdd03e426b679f4dca705d367",
    "adapters/grok_exec.py": "f870671d90fde2670dd62c155488b004cee9d900b4f5185921b26323034a75f7",
    "adapters/json_schema_subset.py": "9b593fbc7f45b9fd965b567e3153b34fd8efd842248f6c5bb10821c643592c95",
    "test_grok_adapter.py": "653c403e98aae388bdc8f05c0c76b50e525ce02c03aaa6b54f317ec49102c9b5",
    "image_canary.py": "17104449da596b2be542d7670f6dee5034a13b78b13f16732da63c852f5e4998",
    "grok_usage_evidence.py": "dc5e00849699858445d966783bfa2b2afc5255b896f41544196ac023c82be99f",
}
ADAPTER_SOURCE = Path(__file__).resolve().parents[1] / "src/hbqrs/grok_broker_transport.py"
HBQ_FAKE = '''
if scenario == "hbq":
    questions = json.loads(prompt.rsplit("```json\\n", 1)[1].split("\\n```", 1)[0])
    output = {"verdicts": [{"question_id": q["question_id"], "verdict": "YES", "confidence": 0.8,
        "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}],
        "note": "Local wiring fixture."} for q in questions]}
'''


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def check_shared():
    for relative, expected in PINS.items():
        assert digest((SHARED / relative).read_bytes()) == expected, relative


@pytest.fixture
def fixture(monkeypatch):
    if not (SHARED / "test_grok_adapter.py").is_file():
        pytest.skip("Optional host-installed broker is unavailable; no native proof")
    check_shared()
    monkeypatch.syspath_prepend(str(SHARED.parent))
    shared_tests = importlib.import_module("model_work_queue.test_grok_adapter")
    assert Path(shared_tests.__file__).resolve() == (SHARED / "test_grok_adapter.py").resolve()
    case = shared_tests.GrokAdapterTests()
    case.setUp()
    try:
        assert case.broker.grok_host_gate_path.resolve().is_relative_to(Path(case.temp.name).resolve())
        assert case.broker.root.resolve().is_relative_to(Path(case.temp.name).resolve())
        fake = shared_tests.FAKE
        assert fake.count("payload = {") == 1
        case.fake.write_text(fake.replace("payload = {", HBQ_FAKE + "\npayload = {"), encoding="utf-8")
        route = case.route("hbq", timeout_seconds=30)
        assert route["grok_command"] == [sys.executable, str(case.fake), "hbq"]
        case.write_route(route)
        yield case, route
    finally:
        case.tearDown()


def execute(tmp_path, transport, **overrides):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    options = dict(
        artifact_path=artifact, bundle_id="prose.short_story", provider="grok", model="grok-4.6",
        output_dir=tmp_path / "run", registry=book_root() / "registry/all_modules.json",
        bundles=book_root() / "bundles/all_bundles.json", batch_size=178, batch_attempts=1,
        reasoning="high", allow_remote=True, allow_unattested_reasoning=True, timeout=30,
        attempt_lifecycle_policy=runner.ATTEMPT_LIFECYCLE_POLICY,
        grok_transport=transport, grok_transport_sha256=digest(ADAPTER_SOURCE.read_bytes()),
    )
    options.update(overrides)
    return run_judge(**options)


def bind(case, route, admission):
    return bind_grok_broker_transport(
        broker=case.broker, route=route, before_contact=admission, runtime_check=check_shared,
    )


@pytest.mark.parametrize("artifact_name", ["receipt", "outcome", "envelope", "request", "context"])
def test_full_hbq_local_chain_and_evidence_replay(tmp_path, fixture, monkeypatch, artifact_name):
    case, route = fixture
    events = []
    def admission(context):
        assert case.broker._grok_host_slot_count(route) == 1
        assert context["batch"]["question_ids"]
        events.append("admission")
    transport = bind(case, route, admission)
    def forbidden(**kwargs):
        pytest.fail("Legacy Grok CLI was reached")
    monkeypatch.setattr(runner, "_call_grok", forbidden)
    result = execute(tmp_path, transport)
    assert result["verdicts"] == 178
    assert result["score_report_version"] == 2
    assert events == ["admission"]
    assert case.broker._grok_host_slot_count(route) == 0
    checkpoint = json.loads((tmp_path / "run/responses/batch-0001.json").read_bytes())
    metadata = checkpoint["provider"]
    assert metadata["tool_free"] is True
    assert metadata["reasoning_attested"] is False
    assert metadata["evidence_sha256"] == metadata["provider_artifacts"]["receipt"]["sha256"]
    execute(tmp_path, transport, resume=True)
    assert events == ["admission"]
    evidence = tmp_path / "run" / metadata["provider_artifacts"][artifact_name]["path"]
    evidence.write_bytes(evidence.read_bytes() + b" ")
    with pytest.raises(HBQError, match="artifact"):
        execute(tmp_path, transport, resume=True)
    assert events == ["admission"]


def test_gate_revoked_inside_admission_prevents_launch_and_resend(tmp_path, fixture, monkeypatch):
    case, route = fixture
    events = []
    def admission(context):
        events.append("admission")
        case.broker._revoke_grok_host_gate(route, "fixture revocation during admission")
    transport = bind(case, route, admission)
    def forbidden(*args, **kwargs):
        pytest.fail("Revoked gate reached adapter")
    monkeypatch.setattr(case.broker, "_run_grok_exec", forbidden)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    with pytest.raises(HBQError, match="terminal nonretryable"):
        execute(tmp_path, transport, resume=True)
    assert events == ["admission"]
    assert case.broker._grok_host_slot_count(route) == 0


def test_route_drift_fails_before_admission_or_launch(tmp_path, fixture, monkeypatch):
    case, route = fixture
    def forbidden(*args, **kwargs):
        pytest.fail("Route drift reached admission or adapter")
    transport = bind(case, route, forbidden)
    changed = {**route, "priority": route["priority"] + 1}
    registry = json.loads((case.root / "routes.json").read_bytes())
    registry["routes"] = [changed]
    case.broker._write_json_atomic(case.root / "routes.json", registry)
    monkeypatch.setattr(case.broker, "_run_grok_exec", forbidden)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    outcomes = list((tmp_path / "run").rglob("outcome.json"))
    assert len(outcomes) == 1
    outcome = json.loads(outcomes[0].read_bytes())
    assert outcome["state"] == "definitely_not_contacted"
    assert outcome["failure"]["code"] == "expected_route_pin_mismatch"
    assert case.broker._grok_host_slot_count(route) == 0


def test_structured_billing_failure_is_preserved_safely_and_not_resent(tmp_path, fixture):
    case, _ = fixture
    route = case.route("structured_402", timeout_seconds=30)
    case.write_route(route)
    contacts = []
    transport = bind(case, route, lambda context: contacts.append(context))
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    outcome = json.loads(next((tmp_path / "run").rglob("outcome.json")).read_bytes())
    assert outcome["failure"]["status"] == 402
    assert outcome["failure"]["code"] == "usage_balance_exhausted"
    with pytest.raises(HBQError, match="terminal nonretryable"):
        execute(tmp_path, transport, resume=True)
    assert len(contacts) == 1
    assert case.broker._grok_host_slot_count(route) == 0
    assert all(b"authorization=must-not-persist" not in p.read_bytes() for p in (tmp_path / "run").rglob("*") if p.is_file())


def test_runtime_check_failure_never_reaches_native_request(tmp_path, fixture, monkeypatch):
    case, route = fixture
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid runtime reached native request")
    monkeypatch.setattr(case.broker, "run_grok_native_request", forbidden)
    def invalid_runtime():
        raise ValueError("DO_NOT_PERSIST_RUNTIME_DETAIL")
    transport = bind_grok_broker_transport(broker=case.broker, route=route, before_contact=forbidden, runtime_check=invalid_runtime)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    assert all(b"DO_NOT_PERSIST" not in p.read_bytes() for p in (tmp_path / "run").rglob("*") if p.is_file())


def test_same_adapter_attempt_directory_cannot_be_reused(tmp_path, fixture):
    case, route = fixture
    contexts = []
    transport = bind(case, route, lambda context: contexts.append(context))
    execute(tmp_path, transport)
    with pytest.raises(HBQError, match="refusing resend"):
        transport(contexts[0])
    assert len(contexts) == 1


def test_failed_broker_evidence_is_bound_to_rejection(tmp_path, fixture):
    case, route = fixture
    contacts = []
    def admission(context):
        contacts.append(context)
        raise RuntimeError("Private admission detail must not persist")
    transport = bind(case, route, admission)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    rejected = json.loads(next((tmp_path / "run/responses/rejected").rglob("attempt-*.json")).read_bytes())
    descriptor = rejected["provider"]["provider_artifacts"]["outcome"]
    outcome_path = tmp_path / "run" / descriptor["path"]
    assert digest(outcome_path.read_bytes()) == descriptor["sha256"]
    outcome_path.write_bytes(outcome_path.read_bytes() + b" ")
    with pytest.raises(HBQError, match="artifact"):
        execute(tmp_path, transport, resume=True)
    assert len(contacts) == 1


def test_evidence_mutation_during_normalization_blocks_checkpoint(tmp_path, fixture, monkeypatch):
    case, route = fixture
    transport = bind(case, route, lambda context: None)
    original = runner._normalize_batch
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt = next((tmp_path / "run/responses/grok-broker").rglob("receipt.json"))
        receipt.write_bytes(receipt.read_bytes() + b" ")
        return result
    monkeypatch.setattr(runner, "_normalize_batch", mutate)
    with pytest.raises(HBQError, match="artifact"):
        execute(tmp_path, transport)
    assert not (tmp_path / "run/responses/batch-0001.json").exists()
    assert not (tmp_path / "run/score.json").exists()


def test_runtime_change_inside_admission_blocks_launch(tmp_path, fixture, monkeypatch):
    case, route = fixture
    admitted = []
    def runtime_check():
        check_shared()
        if admitted:
            raise RuntimeError("runtime changed")
    def forbidden(*args, **kwargs):
        pytest.fail("Stale runtime reached adapter")
    monkeypatch.setattr(case.broker, "_run_grok_exec", forbidden)
    transport = bind_grok_broker_transport(
        broker=case.broker, route=route, before_contact=lambda context: admitted.append(context), runtime_check=runtime_check,
    )
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    assert len(admitted) == 1
    assert case.broker._grok_host_slot_count(route) == 0


def test_postcontact_failure_preserves_and_binds_raw_envelope(tmp_path, fixture):
    case, route = fixture
    checks = []
    def runtime_check():
        check_shared()
        checks.append(True)
        if len(checks) == 4:
            raise RuntimeError("post-contact runtime drift")
    transport = bind_grok_broker_transport(
        broker=case.broker, route=route, before_contact=lambda context: None, runtime_check=runtime_check,
    )
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, transport)
    assert len(checks) == 4
    rejected = json.loads(next((tmp_path / "run/responses/rejected").rglob("attempt-*.json")).read_bytes())
    descriptor = rejected["provider"]["provider_artifacts"]["envelope"]
    raw_path = tmp_path / "run" / descriptor["path"]
    assert digest(raw_path.read_bytes()) == descriptor["sha256"]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    with pytest.raises(HBQError, match="artifact"):
        execute(tmp_path, transport, resume=True)
    assert len(checks) == 4
