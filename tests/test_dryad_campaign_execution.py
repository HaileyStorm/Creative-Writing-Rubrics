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
PLAN_ROOT = Path.home() / "Documents/cwr-dryad-qualification-plan-20260905-r3"
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


def review(value: Any, execution_root: Path, cohort: int, prepared_sha256: str, *, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=16) if expired else now
    end = now - timedelta(seconds=1) if expired else now + timedelta(minutes=10)
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


def run(value: Any, case: Any, execution_root: Path, cohort: int, previous: str, prepared: str, reviewed: str) -> dict[str, Any]:
    return value.run_cohort(
        PUBLIC_INPUTS, PLAN_ROOT, execution_root, cohort, case.broker.root,
        broker_factory=broker_factory(case), expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()),
        expected_previous_settlement_sha256=previous, expected_prepared_sha256=prepared,
        expected_review_sha256=reviewed, expected_source_sha256=digest(SOURCE.read_bytes()),
    )


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
    with pytest.raises((TypeError, ValueError), match="source|Prepared|Review|window|hash"):
        value.run_cohort(
            PUBLIC_INPUTS, PLAN_ROOT, execution_root, 1, case.broker.root, broker_factory=broker_factory(case),
            expected_plan_sha256=digest((PLAN_ROOT / "plan.json").read_bytes()), expected_previous_settlement_sha256=GENESIS,
            expected_prepared_sha256=prepared, expected_review_sha256=reviewed, expected_source_sha256=source,
        )
    assert not list((execution_root / "contacts").glob("request-*.json"))
    assert not list(execution_root.rglob("*.start.json"))
