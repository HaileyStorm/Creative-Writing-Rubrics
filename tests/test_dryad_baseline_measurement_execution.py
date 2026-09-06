from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "baseline_measurement_execution.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("dryad_baseline_measurement_execution", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    value = _load()
    plan_root, execution_root, queue_root = tmp_path / "plan", tmp_path / "execution", tmp_path / "queue"
    plan_root.mkdir()
    execution_root.mkdir()
    queue_root.mkdir()
    public_root = tmp_path / "public"
    public_root.mkdir()
    public_inputs = public_root / "public-inputs.json"
    runtime_manifest = tmp_path / "runtime.json"
    route_path = tmp_path / "route.json"
    public_inputs.write_bytes(b'{"evidence":"synthetic"}')
    runtime_manifest.write_bytes(b'{"runtime":"synthetic"}')
    route = {"name": "synthetic", "timeout_seconds": 1}
    route_path.write_bytes(_canonical(route))

    prompt, schema = b"synthetic prompt", b'{"type":"object"}'
    (plan_root / "prompts").mkdir()
    (plan_root / "schemas").mkdir()
    (plan_root / "inputs").mkdir()
    (plan_root / "prompts/shared.txt").write_bytes(prompt)
    (plan_root / "schemas/shared.json").write_bytes(schema)
    questions = [f"question-{number:03d}" for number in range(1, 179)]
    passes, requests = [], []
    for pass_number in range(1, 237):
        pass_id = f"pass-{pass_number:03d}"
        source = f"synthetic source {pass_number}".encode()
        input_path = f"inputs/{pass_id}.txt"
        (plan_root / input_path).write_bytes(source)
        passes.append({
            "pass_id": pass_id,
            "logical_sample_id": f"logical-{pass_number:03d}",
            "opaque_story_id": f"opaque-{pass_number:03d}",
            "input_path": input_path,
            "run_path": f"runs/{pass_id}",
            "source_sha256": _hash(source),
            "source_bytes": len(source),
        })
        for batch_number in range(1, 24):
            ordinal = (pass_number - 1) * 23 + batch_number
            question_ids = questions[(batch_number - 1) * 8:batch_number * 8]
            requests.append({
                "ordinal": ordinal,
                "pass_id": pass_id,
                "logical_sample_id": f"logical-{pass_number:03d}",
                "batch_number": batch_number,
                "question_ids": question_ids,
                "prompt_path": "prompts/shared.txt",
                "prompt_sha256": _hash(prompt),
                "prompt_bytes": len(prompt),
                "schema_path": "schemas/shared.json",
                "schema_sha256": _hash(schema),
                "schema_bytes": len(schema),
                "endpoint_user_payloads": {
                    "grok": {"sha256": _hash(prompt), "bytes": len(prompt)},
                    "sol": {"sha256": _hash(prompt), "bytes": len(prompt)},
                },
            })
    plan = {
        "public_inputs_sha256": _hash(public_inputs.read_bytes()),
        "passes": passes,
        "requests": requests,
        "runtime": {"question_ids": questions},
    }
    plan_raw = _canonical(plan)
    (plan_root / "plan.json").write_bytes(plan_raw)
    verified = {"plan.json": value.PLAN_SHA256}
    verified.update({f"synthetic/{number:05d}": _hash(str(number).encode()) for number in range(1, 11094)})
    assert len(verified) == 11094

    state: dict[str, Any] = {
        "full_verifications": 0,
        "ledger_prefix_calls": 0,
        "ledger_final_calls": 0,
        "native_calls": 0,
        "admission_calls": 0,
        "runtime_checks": 0,
        "stub_contacts": [],
        "pause_after": None,
        "advance_clock_on_pause": None,
        "prefix_drift": False,
        "drift_on_runner": False,
        "route_drift": False,
        "replace_lock_on_runner": False,
        "broker_constructions": 0,
        "runner_ordinals": list(range(5421, 5429)),
        "clock": datetime.now(timezone.utc),
    }
    source_path = Path(value.__file__).resolve()
    captured = {
        source_path: source_path.read_bytes(),
        value.TERMINAL_IDENTITIES: value.TERMINAL_IDENTITIES.read_bytes(),
    }
    initial_prior = {"contacts": {}, "routes": {}, "head": {"settlement_sha256": "0" * 64}}
    state["ledger_prior"] = initial_prior

    class RetryDisclosurePause(Exception):
        pass

    class FakeBroker:
        def __init__(self, root: Path) -> None:
            self.root = Path(root)
            state["broker_constructions"] += 1

        def _grok_native_route(self, name: str) -> dict[str, Any]:
            assert name == route["name"]
            return {**route, "timeout_seconds": 2} if state["route_drift"] else dict(route)

    class FakeTransport:
        def __init__(self, before_contact: Any, runtime_check: Any) -> None:
            self.before_contact = before_contact
            self.runtime_check = runtime_check

    class FakeRunner:
        def run_judge(self, **kwargs: Any) -> None:
            output = Path(kwargs["output_dir"])
            transport = kwargs["grok_transport"]
            selected = [item for item in requests if item["ordinal"] in state["runner_ordinals"]]
            for request in selected:
                contact = execution_root / "contacts" / f"request-{request['ordinal']:04d}.json"
                if contact.exists():
                    continue
                if state["drift_on_runner"]:
                    state["prefix_drift"] = True
                if state["replace_lock_on_runner"]:
                    (execution_root / ".launch.lock").write_bytes(b"different owner")
                context = {
                    "batch": {"number": request["batch_number"], "question_ids": request["question_ids"]},
                    "output_dir": str(output),
                    "prompt": {"text": prompt.decode(), "sha256": request["prompt_sha256"], "bytes": len(prompt)},
                    "response_schema": {"text": schema.decode(), "sha256": request["schema_sha256"], "bytes": len(schema)},
                    "attempt": {"number": 1},
                }
                kwargs["before_provider_attempt"](context)
                transport.before_contact(context)
                state["stub_contacts"].append(request["ordinal"])
                transport.runtime_check()
                response = output / "responses" / f"batch-{request['batch_number']:04d}.json"
                response.parent.mkdir(parents=True, exist_ok=True)
                response.write_bytes(_canonical({"ordinal": request["ordinal"], "synthetic": True}))
                if state["pause_after"] == len(state["stub_contacts"]):
                    state["pause_after"] = None
                    if state["advance_clock_on_pause"] is not None:
                        state["clock"] = state["advance_clock_on_pause"]
                    raise RetryDisclosurePause("synthetic pause")

    FakeRunner.RetryDisclosurePause = RetryDisclosurePause

    def full_verify(inputs: Path, root: Path) -> dict[str, str]:
        assert inputs == public_inputs and root == plan_root
        state["full_verifications"] += 1
        if state.get("inventory_drift"):
            return {**verified, "synthetic/00001": "0" * 64}
        return dict(verified)

    def cohort_groups(_: dict[str, Any]) -> list[tuple[int, ...]]:
        return [tuple(range(index, index + 10)) for index in range(1, 5421, 10)] + [tuple(range(5421, 5429))]

    def verify_prefix(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        state["ledger_prefix_calls"] += 1
        prior = state["ledger_prior"]
        return {**prior, "changed": True} if state["prefix_drift"] else prior

    def verify_ledger(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        state["ledger_final_calls"] += 1

    def load_runtime(path: Path, *, expected_manifest_sha256: str) -> Any:
        assert expected_manifest_sha256 == _hash(runtime_manifest.read_bytes())
        assert path in {runtime_manifest, value.ROOT / "baseline-runtime-v1.json"}
        return runtime

    def runtime_verify() -> None:
        state["runtime_checks"] += 1

    def bind_transport(*, broker: Any, route: dict[str, Any], before_contact: Any, runtime_check: Any) -> FakeTransport:
        assert isinstance(broker, FakeBroker) and route == route_snapshot
        return FakeTransport(before_contact, runtime_check)

    route_snapshot = dict(route)
    runtime = SimpleNamespace(
        verify=runtime_verify,
        broker=SimpleNamespace(Broker=FakeBroker),
        runner=FakeRunner(),
        transport=SimpleNamespace(bind_grok_broker_transport=bind_transport),
        transport_sha256=_hash(b"synthetic transport"),
    )

    def native_admit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        state["native_calls"] += 1
        return {"native_identities": [
            {"request_id_hash": _hash(f"request-{number}".encode()), "session_id_hash": _hash(f"session-{number}".encode())}
            for number in range(1, 24)
        ]}

    def trusted_identities(_: bytes) -> tuple[frozenset[str], frozenset[str]]:
        return frozenset(_hash(f"trusted-request-{number}".encode()) for number in range(33)), frozenset(
            _hash(f"trusted-session-{number}".encode()) for number in range(33)
        )

    def admit_baseline(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        state["admission_calls"] += 1
        return {
            "evidence_class": "complete_native_baseline_measurement_admission",
            "admitted_passes": 236,
            "logical_requests": 5428,
        }

    monkeypatch.setattr(value, "_sources", lambda: (
        captured,
        (
            SimpleNamespace(verify=full_verify),
            SimpleNamespace(cohort_groups=cohort_groups, verify_prefix=verify_prefix, verify_ledger=verify_ledger),
            SimpleNamespace(load_runtime=load_runtime),
            SimpleNamespace(admit_prefix=native_admit),
            SimpleNamespace(_trusted_identities=trusted_identities, admit_baseline=admit_baseline),
        ),
    ))
    monkeypatch.setattr(value, "_plan", lambda root, expected: (plan, plan_raw))

    class Clock(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            assert tz == timezone.utc
            return state["clock"]

    monkeypatch.setattr(value, "datetime", Clock)
    return SimpleNamespace(
        value=value,
        state=state,
        plan=plan,
        plan_root=plan_root,
        execution_root=execution_root,
        queue_root=queue_root,
        public_root=public_root,
        public_inputs=public_inputs,
        runtime_manifest=runtime_manifest,
        route_path=route_path,
        route=route,
        captured=captured,
        source_path=source_path,
        verified=verified,
    )


def _initialize(case: SimpleNamespace) -> dict[str, str]:
    value = case.value
    result = value.initialize(
        case.public_inputs,
        case.plan_root,
        case.execution_root,
        case.runtime_manifest,
        case.route_path,
        expected_plan_sha256=value.PLAN_SHA256,
        expected_runtime_manifest_sha256=_hash(case.runtime_manifest.read_bytes()),
        expected_route_sha256=value._route_hash(case.route),
    )
    case.initialization_source_sha256 = json.loads((case.execution_root / "initialization.json").read_text())["execution_source_sha256"]
    prior_settled_at = case.state["clock"] - timedelta(minutes=1)
    prior_raw = _canonical({"settled_at": prior_settled_at.isoformat().replace("+00:00", "Z")})
    case.previous_settlement_sha256 = _hash(prior_raw)
    prior_path = case.execution_root / "cohorts/0542/settlement.json"
    prior_path.parent.mkdir(parents=True)
    prior_path.write_bytes(prior_raw)
    case.state["ledger_prior"] = {
        "contacts": {},
        "routes": {},
        "head": {"settlement_sha256": case.previous_settlement_sha256},
    }
    return result


def _prepare(case: SimpleNamespace, cohort: int = 543, previous_settlement_sha256: str | None = None) -> dict[str, str]:
    value = case.value
    case.cohort = cohort
    previous_settlement_sha256 = previous_settlement_sha256 or (
        "0" * 64 if cohort == 1 else case.previous_settlement_sha256
    )
    return value.prepare_cohort(
        case.public_inputs,
        case.plan_root,
        case.execution_root,
        cohort,
        case.route,
        expected_plan_sha256=value.PLAN_SHA256,
        expected_initialization_sha256=case.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=previous_settlement_sha256,
    )


def _review(case: SimpleNamespace, *, start: datetime, end: datetime) -> str:
    value = case.value
    raw = value._canonical({
        "schema_version": 1,
        "reviewer_task": value.REVIEWER_TASK,
        "decision": "approved_cohort",
        "prepared_sha256": case.prepared["prepared_sha256"],
        "reviewed_at": start.isoformat().replace("+00:00", "Z"),
        "expires_at": end.isoformat().replace("+00:00", "Z"),
    })
    path = case.execution_root / "cohorts" / f"{case.cohort:04d}" / "review.json"
    path.write_bytes(raw)
    return _hash(raw)


def _run(
    case: SimpleNamespace,
    review_sha256: str,
    continuation_sha256: str | None = None,
    previous_settlement_sha256: str | None = None,
) -> dict[str, Any]:
    value = case.value
    previous_settlement_sha256 = previous_settlement_sha256 or (
        "0" * 64 if case.cohort == 1 else case.previous_settlement_sha256
    )
    return value.run_cohort(
        case.public_inputs,
        case.plan_root,
        case.execution_root,
        case.cohort,
        case.queue_root,
        broker_factory=lambda root, cls: cls(root),
        expected_plan_sha256=value.PLAN_SHA256,
        expected_initialization_sha256=case.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=previous_settlement_sha256,
        expected_prepared_sha256=case.prepared["prepared_sha256"],
        expected_review_sha256=review_sha256,
        expected_source_sha256=case.initialization_source_sha256,
        expected_continuation_sha256=continuation_sha256,
    )


def _write_continuation(
    case: SimpleNamespace,
    candidate: dict[str, Any],
    *,
    reviewed_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    now = reviewed_at or case.state["clock"]
    raw = case.value._canonical({
        **candidate,
        "reviewed_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (expires_at or now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    })
    root = case.execution_root / "cohorts" / f"{case.cohort:04d}" / "review-continuations"
    path = root / f"{len(list(root.glob('*.json'))) + 1:04d}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)
    return _hash(raw)


def test_initialize_binds_full_inventory_route_and_exclusive_record(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    record_path = case.execution_root / "initialization.json"
    record_raw = record_path.read_bytes()
    record = json.loads(record_raw)
    assert set(record) == {
        "schema_version", "evidence_class", "plan_sha256", "plan_inventory_sha256", "plan_files",
        "runtime_manifest_sha256", "route_sha256", "route_snapshot_sha256", "execution_source_sha256",
        "public_inputs_sha256",
    }
    assert record["plan_inventory_sha256"] == _hash(_canonical(case.verified))
    assert record["route_sha256"] == case.value._route_hash(case.route)
    assert record["plan_files"] == 11094 and case.state["full_verifications"] == 1
    assert not (case.execution_root / ".launch.lock").exists()
    with pytest.raises(ValueError, match="empty execution root"):
        _initialize(case)
    assert record_path.read_bytes() == record_raw
    assert not (case.execution_root / ".launch.lock").exists()


def test_preparation_uses_initialization_without_reverifying_full_plan(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    assert case.value._groups(case.value._sources()[1][1], case.plan, 1) == tuple(range(1, 11))
    assert case.value._groups(case.value._sources()[1][1], case.plan, 543) == tuple(range(5421, 5429))
    case.prepared = _prepare(case)
    prepared = json.loads((case.execution_root / "cohorts/0543/prepared.json").read_text())
    assert prepared["request_ordinals"] == list(range(5421, 5429))
    assert case.state["full_verifications"] == 1
    assert case.state["stub_contacts"] == [] and case.state["native_calls"] == 0

    for function in (case.value.prepare_cohort, case.value.prepare_continuation, case.value.run_cohort, case.value.finalize):
        parameter = inspect.signature(function).parameters["expected_initialization_sha256"]
        assert parameter.default is inspect.Parameter.empty


def test_expired_original_review_resumes_only_with_fresh_continuation_and_never_resends(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    first_now = case.state["clock"]
    review_sha256 = _review(case, start=first_now - timedelta(minutes=1), end=first_now + timedelta(minutes=1))
    case.state["pause_after"] = 3
    case.state["advance_clock_on_pause"] = first_now + timedelta(minutes=2)
    paused = _run(case, review_sha256)
    assert paused == {
        "cohort_number": 543,
        "completed_ordinals": [5421, 5422, 5423],
        "status": "paused_for_continuation_review",
        "provider_calls": 3,
    }
    first_contact = (case.execution_root / "contacts/request-5421.json").read_bytes()
    candidate = case.value.prepare_continuation(
        case.public_inputs,
        case.plan_root,
        case.execution_root,
        543,
        expected_plan_sha256=case.value.PLAN_SHA256,
        expected_initialization_sha256=case.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=case.previous_settlement_sha256,
        expected_prepared_sha256=case.prepared["prepared_sha256"],
        expected_review_sha256=review_sha256,
        expected_source_sha256=case.initialization_source_sha256,
    )
    continuation_sha256 = _write_continuation(case, candidate)
    settled = _run(case, review_sha256, continuation_sha256)
    assert settled["status"] == "settled" and settled["provider_calls"] == 5
    assert case.state["stub_contacts"] == list(range(5421, 5429))
    assert sorted(path.name for path in (case.execution_root / "contacts").glob("request-*.json")) == [
        f"request-{ordinal:04d}.json" for ordinal in range(5421, 5429)
    ]
    assert (case.execution_root / "contacts/request-5421.json").read_bytes() == first_contact
    assert candidate["completed_prefix"]["ordinals"] == [5421, 5422, 5423]


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("payload", "Baseline planned payload differs"),
        ("source", "Reviewed execution source differs"),
        ("route", "Broker route is no longer exact"),
        ("prefix", "Settled ledger prefix changed"),
    ],
)
def test_drift_blocks_before_synthetic_contact(case: SimpleNamespace, drift: str, message: str) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    if drift == "payload":
        (case.plan_root / "prompts/shared.txt").write_bytes(b"changed prompt")
    elif drift == "source":
        case.captured[case.source_path] = b"changed source pin"
    elif drift == "route":
        case.state["route_drift"] = True
    else:
        case.state["drift_on_runner"] = True
    with pytest.raises(ValueError, match=message):
        _run(case, review_sha256)
    assert case.state["stub_contacts"] == []
    assert not list((case.execution_root / "contacts").glob("request-*.json"))
    assert not (case.execution_root / ".launch.lock").exists()


def test_finalizer_requires_released_lock_and_matching_initial_inventory(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    lock = case.execution_root / ".launch.lock"
    lock.write_bytes(b"held")
    common = {
        "expected_plan_sha256": case.value.PLAN_SHA256,
        "expected_initialization_sha256": case.initialization["initialization_sha256"],
        "expected_final_settlement_sha256": "1" * 64,
        "expected_execution_source_sha256": case.initialization_source_sha256,
        "expected_runtime_manifest_sha256": _hash(case.runtime_manifest.read_bytes()),
        "expected_admission_sha256": "2" * 64,
    }
    with pytest.raises(ValueError, match="released execution lock"):
        case.value.finalize(case.public_inputs, case.plan_root, case.execution_root, case.runtime_manifest, **common)
    assert case.state["admission_calls"] == 0
    lock.unlink()
    case.state["inventory_drift"] = True
    with pytest.raises(ValueError, match="Final full plan inventory differs"):
        case.value.finalize(case.public_inputs, case.plan_root, case.execution_root, case.runtime_manifest, **common)
    assert case.state["admission_calls"] == 0
    case.state["inventory_drift"] = False
    result = case.value.finalize(case.public_inputs, case.plan_root, case.execution_root, case.runtime_manifest, **common)
    assert result["evidence_class"] == "complete_native_baseline_measurement_admission"
    assert result["admitted_passes"] == 236 and result["logical_requests"] == 5428
    assert case.state["full_verifications"] == 3
    assert case.state["ledger_final_calls"] == 1 and case.state["admission_calls"] == 1


def test_cohort_boundary_pauses_runner_after_ten_reviewed_contacts_and_settles(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.state["ledger_prior"] = {"contacts": {}, "routes": {}, "head": {"settlement_sha256": "0" * 64}}
    case.state["runner_ordinals"] = list(range(1, 24))
    case.prepared = _prepare(case, 1)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    settled = _run(case, review_sha256)
    assert settled["status"] == "settled" and settled["provider_calls"] == 10
    assert case.state["stub_contacts"] == list(range(1, 11))
    assert not (case.execution_root / "contacts/request-0011.json").exists()


def test_completed_unsettled_cohort_recovers_offline_without_a_broker_or_live_review(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1))
    first = _run(case, review_sha256)
    settlement = case.execution_root / "cohorts/0543/settlement.json"
    settlement.unlink()
    case.state["clock"] = now + timedelta(minutes=2)
    before = case.state["broker_constructions"]
    recovered = _run(case, review_sha256)
    assert first["status"] == recovered["status"] == "settled"
    assert recovered["provider_calls"] == 0
    assert case.state["broker_constructions"] == before
    assert case.state["stub_contacts"] == list(range(5421, 5429))


def test_cohort_two_backdated_review_fails_before_broker_or_contact(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    prior_settled_at = case.state["clock"]
    previous_raw = _canonical({"settled_at": prior_settled_at.isoformat().replace("+00:00", "Z")})
    previous_sha256 = _hash(previous_raw)
    previous_path = case.execution_root / "cohorts/0001/settlement.json"
    previous_path.parent.mkdir(parents=True)
    previous_path.write_bytes(previous_raw)
    case.state["ledger_prior"] = {
        "contacts": {},
        "routes": {},
        "head": {"settlement_sha256": previous_sha256},
    }
    case.prepared = _prepare(case, 2, previous_sha256)
    review_sha256 = _review(
        case,
        start=prior_settled_at - timedelta(minutes=1),
        end=prior_settled_at + timedelta(minutes=3),
    )
    brokers_before = case.state["broker_constructions"]
    with pytest.raises(ValueError, match="Review precedes previous settlement"):
        _run(case, review_sha256, previous_settlement_sha256=previous_sha256)
    assert case.state["broker_constructions"] == brokers_before
    assert case.state["stub_contacts"] == []


@pytest.mark.parametrize("backdate", ["initial", "current"])
def test_backdated_continuation_approval_fails_before_broker_or_contact(case: SimpleNamespace, backdate: str) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    case.state["pause_after"] = 3
    assert _run(case, review_sha256)["status"] == "paused_for_continuation_review"
    candidate = case.value.prepare_continuation(
        case.public_inputs, case.plan_root, case.execution_root, 543,
        expected_plan_sha256=case.value.PLAN_SHA256,
        expected_initialization_sha256=case.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=case.previous_settlement_sha256,
        expected_prepared_sha256=case.prepared["prepared_sha256"],
        expected_review_sha256=review_sha256,
        expected_source_sha256=case.initialization_source_sha256,
    )
    if backdate == "initial":
        continuation_sha256 = _write_continuation(
            case,
            candidate,
            reviewed_at=now - timedelta(minutes=2),
            expires_at=now + timedelta(minutes=3),
        )
    else:
        first_continuation = _write_continuation(case, candidate)
        case.state["pause_after"] = 5
        assert _run(case, review_sha256, first_continuation)["status"] == "paused_for_continuation_review"
        next_candidate = case.value.prepare_continuation(
            case.public_inputs, case.plan_root, case.execution_root, 543,
            expected_plan_sha256=case.value.PLAN_SHA256,
            expected_initialization_sha256=case.initialization["initialization_sha256"],
            expected_previous_settlement_sha256=case.previous_settlement_sha256,
            expected_prepared_sha256=case.prepared["prepared_sha256"],
            expected_review_sha256=review_sha256,
            expected_source_sha256=case.initialization_source_sha256,
        )
        continuation_sha256 = _write_continuation(
            case,
            next_candidate,
            reviewed_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=3),
        )
    brokers_before = case.state["broker_constructions"]
    contacts_before = list(case.state["stub_contacts"])
    with pytest.raises(ValueError):
        _run(case, review_sha256, continuation_sha256)
    assert case.state["broker_constructions"] == brokers_before
    assert case.state["stub_contacts"] == contacts_before


def test_completed_continuation_recovery_requires_its_expected_anchor(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    case.state["pause_after"] = 3
    assert _run(case, review_sha256)["status"] == "paused_for_continuation_review"
    candidate = case.value.prepare_continuation(
        case.public_inputs, case.plan_root, case.execution_root, 543,
        expected_plan_sha256=case.value.PLAN_SHA256,
        expected_initialization_sha256=case.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=case.previous_settlement_sha256,
        expected_prepared_sha256=case.prepared["prepared_sha256"],
        expected_review_sha256=review_sha256,
        expected_source_sha256=case.initialization_source_sha256,
    )
    continuation_sha256 = _write_continuation(case, candidate)
    assert _run(case, review_sha256, continuation_sha256)["status"] == "settled"
    settlement = case.execution_root / "cohorts/0543/settlement.json"
    settlement.unlink()
    case.state["clock"] = now + timedelta(minutes=20)
    brokers_before = case.state["broker_constructions"]
    for anchor in (None, "0" * 64):
        with pytest.raises(ValueError):
            _run(case, review_sha256, anchor)
        assert not settlement.exists()
    recovered = _run(case, review_sha256, continuation_sha256)
    assert recovered["status"] == "settled" and recovered["provider_calls"] == 0
    assert case.state["broker_constructions"] == brokers_before


def test_corrupt_completed_contact_blocks_recovery_before_settlement_persistence(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    assert _run(case, review_sha256)["status"] == "settled"
    settlement = case.execution_root / "cohorts/0543/settlement.json"
    settlement.unlink()
    contact = case.execution_root / "contacts/request-5421.json"
    corrupted = json.loads(contact.read_text())
    corrupted["review_sha256"] = "0" * 64
    contact.write_bytes(_canonical(corrupted))
    brokers_before = case.state["broker_constructions"]
    with pytest.raises(ValueError):
        _run(case, review_sha256)
    assert not settlement.exists()
    assert case.state["broker_constructions"] == brokers_before


@pytest.mark.parametrize("tamper", ["contact", "run_files", "native_identity"])
def test_continuation_candidate_must_replay_actual_prefix_before_any_new_contact(case: SimpleNamespace, tamper: str) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    case.state["pause_after"] = 3
    assert _run(case, review_sha256)["status"] == "paused_for_continuation_review"
    candidate = case.value.prepare_continuation(
        case.public_inputs, case.plan_root, case.execution_root, 543,
        expected_plan_sha256=case.value.PLAN_SHA256,
        expected_initialization_sha256=case.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=case.previous_settlement_sha256,
        expected_prepared_sha256=case.prepared["prepared_sha256"],
        expected_review_sha256=review_sha256,
        expected_source_sha256=case.initialization_source_sha256,
    )
    if tamper == "contact":
        candidate["completed_prefix"]["contacts"][0]["contact_sha256"] = "0" * 64
    elif tamper == "run_files":
        candidate["completed_prefix"]["run_files"] = {"runs/forged.json": "0" * 64}
        candidate["completed_prefix"]["run_tree_sha256"] = _hash(_canonical(candidate["completed_prefix"]["run_files"]))
    else:
        candidate["completed_prefix"]["contacts"][0]["request_id_hash"] = "0" * 64
    continuation_sha256 = _write_continuation(case, candidate)
    brokers_before = case.state["broker_constructions"]
    with pytest.raises(ValueError):
        _run(case, review_sha256, continuation_sha256)
    assert case.state["stub_contacts"] == [5421, 5422, 5423]
    assert case.state["broker_constructions"] == brokers_before


def test_continuation_preparation_requires_a_stable_execution_lock(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    case.state["pause_after"] = 3
    assert _run(case, review_sha256)["status"] == "paused_for_continuation_review"
    prefix = {
        path.relative_to(case.execution_root): path.read_bytes()
        for path in (case.execution_root / "contacts").glob("request-*.json")
    }
    lock = case.execution_root / ".launch.lock"
    lock.write_bytes(b"another owner")
    with pytest.raises(OSError):
        case.value.prepare_continuation(
            case.public_inputs, case.plan_root, case.execution_root, 543,
            expected_plan_sha256=case.value.PLAN_SHA256,
            expected_initialization_sha256=case.initialization["initialization_sha256"],
            expected_previous_settlement_sha256=case.previous_settlement_sha256,
            expected_prepared_sha256=case.prepared["prepared_sha256"],
            expected_review_sha256=review_sha256,
            expected_source_sha256=case.initialization_source_sha256,
        )
    assert {path.relative_to(case.execution_root): path.read_bytes()
            for path in (case.execution_root / "contacts").glob("request-*.json")} == prefix
    assert lock.read_bytes() == b"another owner"


def test_queue_inside_public_input_parent_and_replaced_lock_block_before_contact(case: SimpleNamespace) -> None:
    case.initialization = _initialize(case)
    case.prepared = _prepare(case)
    now = case.state["clock"]
    review_sha256 = _review(case, start=now - timedelta(minutes=1), end=now + timedelta(minutes=10))
    public_queue = case.public_root / "queue"
    public_queue.mkdir()
    brokers_before = case.state["broker_constructions"]
    for overlapping_queue in (public_queue, case.plan_root):
        with pytest.raises(ValueError, match="Queue root overlaps baseline evidence"):
            case.value.run_cohort(
                case.public_inputs, case.plan_root, case.execution_root, 543, overlapping_queue,
                broker_factory=lambda root, cls: cls(root),
                expected_plan_sha256=case.value.PLAN_SHA256,
                expected_initialization_sha256=case.initialization["initialization_sha256"],
                expected_previous_settlement_sha256=case.previous_settlement_sha256,
                expected_prepared_sha256=case.prepared["prepared_sha256"],
                expected_review_sha256=review_sha256,
                expected_source_sha256=case.initialization_source_sha256,
            )
    assert case.state["broker_constructions"] == brokers_before
    case.state["replace_lock_on_runner"] = True
    with pytest.raises(ValueError):
        _run(case, review_sha256)
    assert case.state["stub_contacts"] == []
    assert (case.execution_root / ".launch.lock").read_bytes() == b"different owner"
