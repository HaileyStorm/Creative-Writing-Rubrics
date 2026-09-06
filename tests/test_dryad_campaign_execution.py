from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "campaign_execution.py"
BROKER_TEST = ROOT / "tests" / "test_grok_broker_transport.py"
PUBLIC_INPUTS = Path.home() / "Documents/cwr-dryad-pilot-source-freeze-20260905-r1/public-inputs.json"
PLAN_ROOT = Path.home() / "Documents/cwr-dryad-qualification-v2-plan-20260906-r1"
GENESIS = "0" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def subject() -> Any:
    return load(SOURCE, "dryad_campaign_execution")


@pytest.fixture
def broker_case(monkeypatch: pytest.MonkeyPatch):
    shared = load(BROKER_TEST, "dryad_broker_transport_fixture")
    generator = shared.fixture.__wrapped__(monkeypatch)
    case, route = next(generator)
    try:
        first = json.loads((PLAN_ROOT / "plan.json").read_bytes())["passes"][0]
        quote = (PLAN_ROOT / first["input_path"]).read_text(encoding="utf-8").splitlines()[0][:48]
        fake = case.fake.read_text(encoding="utf-8")
        assert '"fixture-request"' in fake and '"A short test scene."' in fake
        fake = fake.replace('"A short test scene."', json.dumps(quote)).replace('"fixture-request"', '"fixture-" + session')
        case.fake.write_text(fake, encoding="utf-8")
        route = case.route("hbq", timeout_seconds=30)
        case.write_route(route)
        assert case.broker.root.resolve().is_relative_to(Path(case.temp.name).resolve())
        assert case.broker.grok_host_gate_path.resolve().is_relative_to(Path(case.temp.name).resolve())
        yield case, route
    finally:
        try:
            next(generator)
        except StopIteration:
            pass


def broker_factory(case: Any):
    def factory(root: Path, cls: Any) -> Any:
        assert Path(root).resolve() == case.broker.root.resolve()
        return cls(root, grok_host_gate_path=case.broker.grok_host_gate_path)
    return factory


def review(value: Any, execution_root: Path, cohort: int, prepared_sha256: str, *, expired: bool = False, now: datetime | None = None, duration_minutes: int = 10) -> str:
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(minutes=16) if expired else now
    end = now - timedelta(seconds=1) if expired else now + timedelta(minutes=duration_minutes)
    raw = value._canonical({
        "schema_version": 1,
        "reviewer_task": value._sources()[1][1].REVIEWER_TASK,
        "decision": "approved_cohort",
        "prepared_sha256": prepared_sha256,
        "reviewed_at": start.isoformat().replace("+00:00", "Z"),
        "expires_at": end.isoformat().replace("+00:00", "Z"),
    })
    path = execution_root / "cohorts" / f"{cohort:04d}" / "review.json"
    path.write_bytes(raw)
    return digest(raw)


def prepare(value: Any, execution_root: Path, cohort: int, route: dict[str, Any], previous: str) -> tuple[str, str]:
    result = value.prepare_cohort(PUBLIC_INPUTS, PLAN_ROOT, execution_root, cohort, route, expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()), expected_previous_settlement_sha256=previous)
    return result["prepared_sha256"], result["route_sha256"]


def run(value: Any, case: Any, execution_root: Path, cohort: int, previous: str, prepared: str, reviewed: str, continuation: str | None = None) -> dict[str, Any]:
    return value.run_cohort(
        PUBLIC_INPUTS, PLAN_ROOT, execution_root, cohort, case.broker.root,
        broker_factory=broker_factory(case), expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()),
        expected_previous_settlement_sha256=previous, expected_prepared_sha256=prepared,
        expected_review_sha256=reviewed, expected_source_sha256=digest(SOURCE.read_bytes()), expected_continuation_sha256=continuation,
    )


def pause_before_batch(value: Any, monkeypatch: pytest.MonkeyPatch, execution_root: Path, batch_number: int, invoke):
    original_sources = value._sources
    def interrupted_sources():
        captured, modules = original_sources()
        native = modules[2]
        original_loader = native.load_runtime
        def loader():
            runtime = original_loader()
            original_run = runtime.runner.run_judge
            def wrapped_run(**kwargs):
                original_hook = kwargs["before_provider_attempt"]
                def hook(context):
                    if context["batch"]["number"] == batch_number:
                        raise runtime.runner.RetryDisclosurePause("test continuation pause before attempt start")
                    original_hook(context)
                kwargs["before_provider_attempt"] = hook
                return original_run(**kwargs)
            runtime.runner.run_judge = wrapped_run
            return runtime
        native.load_runtime = loader
        return captured, modules
    monkeypatch.setattr(value, "_sources", interrupted_sources)
    try:
        return invoke()
    finally:
        monkeypatch.setattr(value, "_sources", original_sources)


def write_continuation(value: Any, execution_root: Path, cohort: int, previous: str, prepared: str, reviewed: str, *, now: datetime | None = None) -> tuple[str, dict[str, Any]]:
    proposal = value.prepare_continuation(PUBLIC_INPUTS, PLAN_ROOT, execution_root, cohort,
                                          expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()),
                                          expected_previous_settlement_sha256=previous, expected_prepared_sha256=prepared,
                                          expected_review_sha256=reviewed, expected_source_sha256=digest(SOURCE.read_bytes()))
    now = now or datetime.now(timezone.utc)
    record = {**proposal, "reviewed_at": now.isoformat().replace("+00:00", "Z"), "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")}
    directory = execution_root / f"cohorts/{cohort:04d}/review-continuations"
    directory.mkdir(exist_ok=True)
    path = directory / f"{len(list(directory.glob('*.json'))) + 1:04d}.json"
    path.write_bytes(value._canonical(record))
    return digest(path.read_bytes()), proposal


def admitted_prefix_verdicts(value: Any, execution_root: Path, route: dict[str, Any], expected_batches: int) -> list[dict[str, Any]]:
    plan = json.loads((PLAN_ROOT / "plan.json").read_bytes())
    record = plan["passes"][0]
    native = value._sources()[1][2]
    runtime = native.load_runtime()
    admitted = native.admit_prefix(execution_root / record["run_path"], source={
        "opaque_story_id": record["opaque_story_id"],
        "story_text": (PLAN_ROOT / record["input_path"]).read_text(encoding="utf-8"),
        "artifact_path": str(PLAN_ROOT / record["input_path"]),
    }, batch_size=record["batch_size"], expected_batches=expected_batches,
                                  approved_routes={digest(value._canonical(route)): route}, runtime=runtime)
    return admitted["verdicts"]


def test_two_reviewed_cohorts_settle_once_with_temp_fake_broker(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]]):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    first_prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    first_review = review(value, execution_root, 1, first_prepared)
    first = run(value, case, execution_root, 1, GENESIS, first_prepared, first_review)
    assert first["status"] == "settled" and len(first["ordinals"]) == 10
    assert sorted((execution_root / "contacts").glob("request-*.json"))
    assert len(list((execution_root / "contacts").glob("request-*.json"))) == 10
    assert not (execution_root / "contacts" / "request-0011.json").exists()
    assert not list(execution_root.rglob("batch-0011/attempt-0001.start.json"))
    with pytest.raises(ValueError, match="inventory|settled|prefix|Prepared"):
        run(value, case, execution_root, 1, GENESIS, first_prepared, first_review)

    second_prepared, _ = prepare(value, execution_root, 2, route, first["settlement_sha256"])
    second_review = review(value, execution_root, 2, second_prepared)
    second = run(value, case, execution_root, 2, first["settlement_sha256"], second_prepared, second_review)
    assert second["status"] == "settled" and len(second["ordinals"]) == 10
    contacts = list((execution_root / "contacts").glob("request-*.json"))
    assert len(contacts) == 20
    request_hashes = [
        item["request_id_hash"]
        for number in (1, 2)
        for item in json.loads((execution_root / "cohorts" / f"{number:04d}" / "settlement.json").read_bytes())["contacts"]
    ]
    assert len(request_hashes) == len(set(request_hashes)) == 20


def test_expired_prefix_renews_once_and_settles_without_resending(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared)
    original_sources = value._sources

    def interrupted_sources():
        captured, modules = original_sources()
        native = modules[2]
        original_loader = native.load_runtime
        def loader():
            runtime = original_loader()
            original_run = runtime.runner.run_judge
            def wrapped_run(**kwargs):
                original_hook = kwargs["before_provider_attempt"]
                def hook(context):
                    if context["batch"]["number"] == 5:
                        raise runtime.runner.RetryDisclosurePause("review expired before attempt start")
                    original_hook(context)
                kwargs["before_provider_attempt"] = hook
                return original_run(**kwargs)
            runtime.runner.run_judge = wrapped_run
            return runtime
        native.load_runtime = loader
        return captured, modules

    monkeypatch.setattr(value, "_sources", interrupted_sources)
    paused = run(value, case, execution_root, 1, GENESIS, prepared, reviewed)
    assert paused["status"] == "paused_for_continuation_review" and paused["provider_calls"] == 4
    assert len(list((execution_root / "contacts").glob("request-*.json"))) == 4
    assert not list(execution_root.rglob("batch-0005/attempt-0001.start.json"))
    monkeypatch.setattr(value, "_sources", original_sources)
    proposal = value.prepare_continuation(PUBLIC_INPUTS, PLAN_ROOT, execution_root, 1,
                                          expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()),
                                          expected_previous_settlement_sha256=GENESIS, expected_prepared_sha256=prepared,
                                          expected_review_sha256=reviewed, expected_source_sha256=digest(SOURCE.read_bytes()))
    now = datetime.now(timezone.utc)
    renewed = {**proposal, "reviewed_at": now.isoformat().replace("+00:00", "Z"), "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")}
    continuation_path = execution_root / "cohorts/0001/review-continuations/0001.json"
    continuation_path.parent.mkdir()
    continuation_path.write_bytes(value._canonical(renewed))
    continuation = digest(continuation_path.read_bytes())
    protected = next(execution_root.rglob("run.json"))
    protected_raw = protected.read_bytes()
    protected.write_bytes(b"tampered prefix")
    with pytest.raises(ValueError, match="Continuation run prefix"):
        run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation)
    assert len(list(execution_root.rglob("native-envelope.json"))) == 4
    protected.write_bytes(protected_raw)
    settled = run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation)
    assert settled["status"] == "settled" and settled["provider_calls"] == 6
    assert len(list((execution_root / "contacts").glob("request-*.json"))) == 10
    contact_hashes = [digest((execution_root / "contacts" / f"request-{number:04d}.json").read_bytes()) for number in range(1, 5)]
    assert contact_hashes == [entry["contact_sha256"] for entry in proposal["completed_prefix"]["contacts"]]


def test_two_renewals_require_strictly_advancing_prefixes(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared)
    first = pause_before_batch(value, monkeypatch, execution_root, 5, lambda: run(value, case, execution_root, 1, GENESIS, prepared, reviewed))
    assert first["completed_ordinals"] == [1, 2, 3, 4]
    continuation_one, proposal_one = write_continuation(value, execution_root, 1, GENESIS, prepared, reviewed)
    second = pause_before_batch(value, monkeypatch, execution_root, 7, lambda: run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation_one))
    assert second["completed_ordinals"] == [1, 2, 3, 4, 5, 6]
    continuation_two, proposal_two = write_continuation(value, execution_root, 1, GENESIS, prepared, reviewed)
    assert proposal_one["completed_prefix"]["ordinals"] == [1, 2, 3, 4]
    assert proposal_two["completed_prefix"]["ordinals"] == [1, 2, 3, 4, 5, 6]
    settled = run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation_two)
    assert settled["status"] == "settled" and settled["provider_calls"] == 4
    chain = json.loads((execution_root / "cohorts/0001/settlement.json").read_bytes())["authorization_chain"]
    assert [entry["ordinals"] for entry in chain] == [[1, 2, 3, 4], [5, 6], [7, 8, 9, 10]]


def test_cohort_two_renewal_uses_local_prefix_ordinals(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    first_prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    first_review = review(value, execution_root, 1, first_prepared)
    first = run(value, case, execution_root, 1, GENESIS, first_prepared, first_review)
    second_prepared, _ = prepare(value, execution_root, 2, route, first["settlement_sha256"])
    second_review = review(value, execution_root, 2, second_prepared)
    paused = pause_before_batch(value, monkeypatch, execution_root, 15, lambda: run(value, case, execution_root, 2, first["settlement_sha256"], second_prepared, second_review))
    assert paused["completed_ordinals"] == [11, 12, 13, 14]
    continuation, proposal = write_continuation(value, execution_root, 2, first["settlement_sha256"], second_prepared, second_review)
    assert proposal["completed_prefix"]["ordinals"] == [11, 12, 13, 14]
    settled = run(value, case, execution_root, 2, first["settlement_sha256"], second_prepared, second_review, continuation)
    assert settled["status"] == "settled" and settled["provider_calls"] == 6


def test_cohort_two_renewal_replays_prior_route_and_contacts_new_route(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, first_route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    first_prepared, _ = prepare(value, execution_root, 1, first_route, GENESIS)
    first_review = review(value, execution_root, 1, first_prepared)
    first = run(value, case, execution_root, 1, GENESIS, first_prepared, first_review)
    case.fake.write_text(case.fake.read_text(encoding="utf-8").replace('if scenario == "hbq":', 'if scenario in {"hbq", "hbq-2"}:'), encoding="utf-8")
    second_route = case.route("hbq-2", timeout_seconds=30)
    case.write_route(second_route)
    second_prepared, _ = prepare(value, execution_root, 2, second_route, first["settlement_sha256"])
    second_review = review(value, execution_root, 2, second_prepared)
    paused = pause_before_batch(value, monkeypatch, execution_root, 15, lambda: run(value, case, execution_root, 2, first["settlement_sha256"], second_prepared, second_review))
    assert paused["completed_ordinals"] == [11, 12, 13, 14]
    continuation, _ = write_continuation(value, execution_root, 2, first["settlement_sha256"], second_prepared, second_review)
    settled = run(value, case, execution_root, 2, first["settlement_sha256"], second_prepared, second_review, continuation)
    assert settled["status"] == "settled" and settled["provider_calls"] == 6


def test_original_receipt_tamper_after_first_resumed_call_blocks_next_contact(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared)
    pause_before_batch(value, monkeypatch, execution_root, 5, lambda: run(value, case, execution_root, 1, GENESIS, prepared, reviewed))
    continuation, _ = write_continuation(value, execution_root, 1, GENESIS, prepared, reviewed)
    original_sources = value._sources
    protected = next(execution_root.rglob("batch-0001-attempt-0001/receipt.json"))
    def tampering_sources():
        captured, modules = original_sources()
        native = modules[2]
        original_loader = native.load_runtime
        def loader():
            runtime = original_loader()
            original_run = runtime.runner.run_judge
            def wrapped_run(**kwargs):
                original_hook = kwargs["before_provider_attempt"]
                def hook(context):
                    if context["batch"]["number"] == 6:
                        protected.write_bytes(b"tampered old receipt")
                    original_hook(context)
                kwargs["before_provider_attempt"] = hook
                return original_run(**kwargs)
            runtime.runner.run_judge = wrapped_run
            return runtime
        native.load_runtime = loader
        return captured, modules
    monkeypatch.setattr(value, "_sources", tampering_sources)
    with pytest.raises(ValueError, match="Continuation run prefix changed"):
        run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation)
    assert len(list(execution_root.rglob("native-envelope.json"))) == 5
    assert not list(execution_root.rglob("batch-0006/attempt-0001.start.json"))


def test_expired_original_review_can_settle_under_fresh_continuation_window(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    origin = datetime(2026, 9, 6, tzinfo=timezone.utc)
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared, now=origin, duration_minutes=15)
    class Clock:
        instant = origin + timedelta(minutes=1)
        @classmethod
        def now(cls, tz=None):
            return cls.instant if tz is not None else cls.instant.replace(tzinfo=None)
    monkeypatch.setattr(value, "datetime", Clock)
    paused = pause_before_batch(value, monkeypatch, execution_root, 5, lambda: run(value, case, execution_root, 1, GENESIS, prepared, reviewed))
    assert paused["completed_ordinals"] == [1, 2, 3, 4]
    continuation, _ = write_continuation(value, execution_root, 1, GENESIS, prepared, reviewed, now=origin + timedelta(minutes=16))
    Clock.instant = origin + timedelta(minutes=17)
    settled = run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation)
    assert settled["status"] == "settled" and settled["provider_calls"] == 6


def test_continuation_rejects_omitted_prefix_file_before_resumed_contact(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared)
    pause_before_batch(value, monkeypatch, execution_root, 5, lambda: run(value, case, execution_root, 1, GENESIS, prepared, reviewed))
    _, proposal = write_continuation(value, execution_root, 1, GENESIS, prepared, reviewed)
    path = execution_root / "cohorts/0001/review-continuations/0001.json"
    record = json.loads(path.read_bytes())
    removed = next(name for name in record["completed_prefix"]["run_files"] if name.endswith("receipt.json"))
    record["completed_prefix"]["run_files"].pop(removed)
    record["completed_prefix"]["run_tree_sha256"] = digest(value._canonical(record["completed_prefix"]["run_files"]))
    path.write_bytes(value._canonical(record))
    continuation = digest(path.read_bytes())
    with pytest.raises(ValueError, match="Continuation.*prefix"):
        run(value, case, execution_root, 1, GENESIS, prepared, reviewed, continuation)
    assert len(list(execution_root.rglob("native-envelope.json"))) == 4
    assert proposal["completed_prefix"]["run_files"][removed]


def test_continuation_preparation_rejects_wrong_previous_settlement_before_contact(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared)
    pause_before_batch(value, monkeypatch, execution_root, 5, lambda: run(value, case, execution_root, 1, GENESIS, prepared, reviewed))
    with pytest.raises(ValueError, match="Previous settlement|Prepared cohort"):
        value.prepare_continuation(PUBLIC_INPUTS, PLAN_ROOT, execution_root, 1,
                                   expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()),
                                   expected_previous_settlement_sha256="f" * 64, expected_prepared_sha256=prepared,
                                   expected_review_sha256=reviewed, expected_source_sha256=digest(SOURCE.read_bytes()))
    assert len(list(execution_root.rglob("native-envelope.json"))) == 4


def test_interrupted_and_uninterrupted_prefixes_have_identical_native_verdicts(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    value = subject()
    case, route = broker_case
    direct_root = tmp_path / "direct"
    direct_root.mkdir()
    direct_prepared, _ = prepare(value, direct_root, 1, route, GENESIS)
    direct_review = review(value, direct_root, 1, direct_prepared)
    assert run(value, case, direct_root, 1, GENESIS, direct_prepared, direct_review)["status"] == "settled"
    resumed_root = tmp_path / "resumed"
    resumed_root.mkdir()
    resumed_prepared, _ = prepare(value, resumed_root, 1, route, GENESIS)
    resumed_review = review(value, resumed_root, 1, resumed_prepared)
    paused = pause_before_batch(value, monkeypatch, resumed_root, 5, lambda: run(value, case, resumed_root, 1, GENESIS, resumed_prepared, resumed_review))
    assert paused["completed_ordinals"] == [1, 2, 3, 4]
    continuation, _ = write_continuation(value, resumed_root, 1, GENESIS, resumed_prepared, resumed_review)
    assert run(value, case, resumed_root, 1, GENESIS, resumed_prepared, resumed_review, continuation)["status"] == "settled"
    assert admitted_prefix_verdicts(value, direct_root, route, 10) == admitted_prefix_verdicts(value, resumed_root, route, 10)


@pytest.mark.parametrize("fault", ["orphan", "contact_mutation"])
def test_ledger_change_between_contacts_stops_before_second_attempt(tmp_path, broker_case, monkeypatch, fault):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared)
    original_sources = value._sources
    def sources():
        captured, modules = original_sources()
        native = modules[2]
        original_loader = native.load_runtime
        def loader():
            runtime = original_loader()
            original_run = runtime.runner.run_judge
            def wrapped_run(**kwargs):
                original_hook = kwargs["before_provider_attempt"]
                def hook(context):
                    if context["batch"]["number"] == 2:
                        path = execution_root / "contacts" / ("orphan.json" if fault == "orphan" else "request-0001.json")
                        path.write_bytes(b"{}")
                    original_hook(context)
                kwargs["before_provider_attempt"] = hook
                return original_run(**kwargs)
            runtime.runner.run_judge = wrapped_run
            return runtime
        native.load_runtime = loader
        return captured, modules
    monkeypatch.setattr(value, "_sources", sources)
    with pytest.raises(ValueError, match="inventory changed"):
        run(value, case, execution_root, 1, GENESIS, prepared, reviewed)
    assert len(list(execution_root.rglob("native-envelope.json"))) == 1
    assert not list(execution_root.rglob("batch-0002/attempt-0001.start.json"))
    assert not (execution_root / "cohorts/0001/settlement.json").exists()


@pytest.mark.parametrize("mutation", ("expired", "prepared", "review", "source"))
def test_invalid_approval_or_source_rejects_before_fake_contact(tmp_path: Path, broker_case: tuple[Any, dict[str, Any]], mutation: str):
    value = subject()
    case, route = broker_case
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    prepared, _ = prepare(value, execution_root, 1, route, GENESIS)
    reviewed = review(value, execution_root, 1, prepared, expired=mutation == "expired")
    if mutation == "prepared":
        prepared = "0" * 64
    if mutation == "review":
        reviewed = "0" * 64
    source = digest(SOURCE.read_bytes()) if mutation != "source" else "0" * 64
    with pytest.raises((TypeError, ValueError), match="source|Prepared|Review|window|hash|authorization"):
        value.run_cohort(
            PUBLIC_INPUTS, PLAN_ROOT, execution_root, 1, case.broker.root, broker_factory=broker_factory(case),
            expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()), expected_previous_settlement_sha256=GENESIS,
            expected_prepared_sha256=prepared, expected_review_sha256=reviewed, expected_source_sha256=source,
        )
    assert not list((execution_root / "contacts").glob("request-*.json"))
    assert not list(execution_root.rglob("*.start.json"))
