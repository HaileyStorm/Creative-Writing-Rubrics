"""Synthetic adopted recovery with real runner loading and isolated fake CLI."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs import core, runner, weights
from hbqrs import grok_broker_transport_v2 as transport_module

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_recovered_study.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path, monkeypatch):
    subject = load(SOURCE, "recovered_study_test")
    reader_support = load(ROOT / "tests/test_dryad_grok70_schema_recovery.py", "recovery_reader_support")
    source_support = load(ROOT / "tests/test_cohort_ledger_core.py", "recovery_source_support")
    operational_core, _, _ = source_support.operational_core(tmp_path)
    actual_reader = subject._module("grok70_schema_recovery")
    modules = core.load_modules(ROOT / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(ROOT / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    question_ids = [item["question"]["id"] for item in questions[:8]]
    response_schema = runner._batch_response_schema(question_ids)
    adopted = reader_support.make_fixture(tmp_path / "adopted", question_ids=question_ids,
        response_schema=response_schema, response_schema_raw=runner._json_bytes(response_schema))

    # The public reader hard-pins the real terminal outcome. Only this test-local
    # dependency calls its real internal verifier with the synthetic outcome pin;
    # no reader, normalizer, source-manifest or native parser validation is stubbed.
    def synthetic_recovery(inputs):
        kwargs = {key: Path(value) if key != "expected_adoption_sha256" else value
                  for key, value in inputs.items()}
        return actual_reader._recover_judgment(**kwargs, terminal_outcome_sha256=adopted.outcome_sha256)

    module_loader = subject._module

    def dependencies(name):
        if name == "baseline_measurement_ledger":
            return SimpleNamespace(current_operational_source_manifest=operational_core.current_operational_source_manifest,
                                   _core=lambda: (operational_core, Path(operational_core.__file__).read_bytes()))
        return module_loader(name)

    monkeypatch.setattr(subject, "_recovery", synthetic_recovery)
    monkeypatch.setattr(subject, "_module", dependencies)
    native_checks = []
    runtime = SimpleNamespace(runner=runner, core=core, weights=weights, modules=modules,
        bundle=bundle, compiled=compiled, questions=questions, transport=transport_module,
        transport_sha256=subject.digest(Path(transport_module.__file__).read_bytes()),
        response_schema_mode="batch_question_ids_v1", verify=lambda: native_checks.append("runtime_checked"))
    original, descendant = tmp_path / "original-failed-run", tmp_path / "study-descendant"
    source = {"opaque_story_id": subject.LOGICAL_SAMPLE_ID, "source_opaque_story_id": subject.STORY_ID, "story_text": adopted.source,
              "artifact_path": str(adopted.args["source_path"])}
    options = {"artifact_path": source["artifact_path"], "bundle_id": "prose.short_story", "provider": "grok", "model": "grok-4.6",
        "output_dir": original, "registry": ROOT / "registry/all_modules.json", "bundles": ROOT / "bundles/all_bundles.json",
        "batch_size": 8, "batch_attempts": 1, "reasoning": "high", "allow_remote": True, "allow_unattested_reasoning": True,
        "timeout": 120, "artifact_id": subject.LOGICAL_SAMPLE_ID, "judge_id": "grok:grok-4.6",
        "attempt_lifecycle_policy": runner.ATTEMPT_LIFECYCLE_POLICY,
        "grok_transport_sha256": runtime.transport_sha256, "response_schema_mode": "batch_question_ids_v1"}
    calls = []

    def original_failure(context):
        assert context["batch"]["number"] == 1
        calls.append("original-synthetic-failure")
        raise RuntimeError("Synthetic terminal schema failure; no external contact")

    with pytest.raises(core.HBQError):
        runner.run_judge(**options, grok_transport=original_failure)
    outcome = original / "responses/grok-broker/batch-0001-attempt-0001/outcome.json"
    outcome.parent.mkdir(parents=True, exist_ok=True)
    outcome.write_bytes(adopted.args["terminal_outcome_path"].read_bytes())
    contact_path = tmp_path / "original-contact70.json"
    contact_path.write_bytes(subject.canonical({"ordinal": 70, "cohort_number": 7,
        "review_sha256": "a" * 64, "admitted_at": "2026-09-07T23:00:00Z"}))
    original_inventory = subject._inventory(original)
    recovery = actual_reader._recover_judgment(adopted.proposal_root, **adopted.args,
        terminal_outcome_sha256=adopted.outcome_sha256)
    summary = {"ordinal": 70, "evidence_kind": "study_recovered", "contact_sha256": subject.digest(contact_path.read_bytes()),
        "adoption_sha256": adopted.args["expected_adoption_sha256"],
        "derivative_sha256": recovery["study_recovered_quote_repair"]["derivative_sha256"],
        "study_accepted_at": "2026-09-08T00:01:00Z"}
    amendment = {"schema_version": 1, "decision": "approved_study_recovery_materialization",
        "reviewer_task": "independent-synthetic-reviewer", "original_run_tree_sha256": subject.digest(subject.canonical(original_inventory)),
        "materializer_sha256": subject.digest(SOURCE.read_bytes()),
        "recovery_operational_source_manifest": operational_core.current_operational_source_manifest(),
        "study_recovery_summary": summary}
    amendment_path = tmp_path / "reviewed-amendment.json"
    amendment_path.write_bytes(subject.canonical(amendment))
    kwargs = {"proposal_root": adopted.proposal_root, **adopted.args, "amendment_path": amendment_path,
        "expected_amendment_sha256": subject.digest(amendment_path.read_bytes()), "contact_path": contact_path,
        "expected_contact_sha256": summary["contact_sha256"], "source": source, "runtime": runtime}
    return SimpleNamespace(subject=subject, adopted=adopted, original=original, descendant=descendant,
        kwargs=kwargs, original_inventory=original_inventory, source=source, runtime=runtime, calls=calls,
        options=options, tmp_path=tmp_path, amendment=amendment, amendment_path=amendment_path,
        operational_core=operational_core)


def materialize(case):
    result = case.subject.materialize_recovered_run(case.original, case.descendant, **case.kwargs)
    case.result = result
    case.anchors = {"expected_recovered_manifest_sha256": result["manifest_sha256"],
        "expected_adoption_sha256": case.kwargs["expected_adoption_sha256"],
        "expected_amendment_sha256": case.kwargs["expected_amendment_sha256"]}
    return result


def test_materialization_is_idempotent_and_real_runner_loads_study_checkpoint(case):
    result = materialize(case)
    before = case.subject._inventory(case.descendant)
    assert case.subject.materialize_recovered_run(case.original, case.descendant, **case.kwargs) == result
    assert case.subject._inventory(case.descendant) == before
    verdicts, count, head = runner._load_checkpoints(case.descendant, artifact_text=case.source["story_text"],
        context_texts=[], batch_attempts=1)
    assert len(verdicts) == 8 and count == 1 and head == result["checkpoint_head_sha256"]
    checkpoint = json.loads((case.descendant / "responses/batch-0001.json").read_bytes())
    assert set(checkpoint["provider"]) == {"study_recovered_quote_repair"}
    assert not (case.descendant / "responses/grok-broker").exists()
    assert not (case.descendant / "responses/rejected").exists()
    assert case.subject._inventory(case.original) == case.original_inventory
    assert case.calls == ["original-synthetic-failure"]
    checked = case.subject.load_recovered_study(case.descendant, source=case.source, runtime=case.runtime, **case.anchors)
    assert checked["expected_study_recovery"] == result["expected_study_recovery"]
    assert checked["target_pass_id"] == case.subject.TARGET_PASS_ID
    assert set(checked["expected_study_recovery"]["summary"]) == case.subject.SUMMARY_FIELDS | {"amendment_sha256"}
    replay = case.subject.admit_prefix(case.descendant, source=case.source, runtime=case.runtime,
        batch_size=8, expected_batches=1, approved_routes={}, **case.anchors)
    assert replay["accepted_count"] == 8 and replay["native_identities"] == []
    assert replay["study_recovered"] == [result["expected_study_recovery"]["summary"]]
    with pytest.raises((ValueError, FileNotFoundError)):
        case.subject._native.admit_prefix(case.descendant, source=case.source, runtime=case.runtime,
            batch_size=8, expected_batches=1, approved_routes={})


def test_resume_denied_gate_reaches_original71_without_contacting70(case):
    materialize(case)
    attempted, contacts = [], []

    def before_contact(context):
        attempted.append(69 + context["batch"]["number"])
        assert context["batch"]["number"] == 2
        raise runner.RetryDisclosurePause("Synthetic host gate denied before contact")

    def forbidden(context):
        contacts.append(context)
        pytest.fail("Denied gate must prevent provider contact")

    with pytest.raises(runner.RetryDisclosurePause):
        runner.run_judge(**{**case.options, "output_dir": case.descendant}, resume=True,
            before_provider_attempt=before_contact, grok_transport=forbidden)
    assert attempted == [71] and contacts == []
    assert case.subject._inventory(case.original) == case.original_inventory
    assert not (case.descendant / "responses/batch-0002.json").exists()
    assert not (case.descendant / "responses/attempt-lifecycle/batch-0002").exists()


@pytest.fixture
def native_suffix(case, monkeypatch):
    shared_root = Path.home() / ".codex/tools/model_work_queue"
    require_fixture = shared_root / "test_grok_adapter.py"
    assert require_fixture.is_file(), "The isolated installed fake CLI fixture is required"
    monkeypatch.syspath_prepend(str(shared_root.parent))
    shared = importlib.import_module("model_work_queue.test_grok_adapter")
    assert Path(shared.__file__).resolve() == require_fixture.resolve()
    fixture = shared.GrokAdapterTests()
    fixture.setUp()
    try:
        assert fixture.broker.root.resolve().is_relative_to(Path(fixture.temp.name).resolve())
        assert fixture.broker.grok_host_gate_path.resolve().is_relative_to(Path(fixture.temp.name).resolve())
        script = shared.FAKE
        addition = '''
if scenario == "hbq":
    questions = json.loads(prompt.rsplit("```json\\n", 1)[1].split("\\n```", 1)[0])
    output = {"verdicts": [{"question_id": q["question_id"], "verdict": "YES", "confidence": 0.5,
        "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": "A", "summary": None}],
        "note": "Synthetic native suffix fixture."} for q in questions]}
'''
        assert script.count("payload = {") == 1
        script = script.replace("payload = {", addition + "\npayload = {")
        script = script.replace('"fixture-request"', '"fixture-" + session')
        fixture.fake.write_text(script, encoding="utf-8")
        route = fixture.route("hbq", timeout_seconds=120)
        assert route["grok_command"] == [sys.executable, str(fixture.fake), "hbq"]
        fixture.write_route(route)
        case.runtime.broker = SimpleNamespace(Broker=shared.Broker)
        case.runtime.adapter = shared.grok_exec
        admitted = []

        def admission(context):
            assert context["batch"]["number"] >= 2
            admitted.append(69 + context["batch"]["number"])

        transport = transport_module.bind_grok_broker_transport(broker=fixture.broker, route=route,
            before_contact=admission, runtime_check=case.runtime.verify)
        yield SimpleNamespace(fixture=fixture, route=route, transport=transport, admitted=admitted)
    finally:
        fixture.tearDown()


def test_native_suffix_replay_excludes70_and_preserves_canonical_scoring(case, native_suffix):
    materialize(case)
    result = runner.run_judge(**{**case.options, "output_dir": case.descendant},
        resume=True, grok_transport=native_suffix.transport)
    assert result["verdicts"] == 178
    assert native_suffix.admitted == list(range(71, 93))
    routes = {case.subject.digest(case.subject.canonical(native_suffix.route)): native_suffix.route}
    replay = case.subject.admit_pass(case.descendant, source=case.source, batch_size=8,
        approved_routes=routes, runtime=case.runtime, **case.anchors)
    assert len(replay["verdicts"]) == 178 and len(replay["native_identities"]) == 22
    assert replay["study_recovered_ordinals"] == [70]
    assert replay["study_recovered"] == [case.result["expected_study_recovery"]["summary"]]
    verdicts, _, _ = runner._load_checkpoints(case.descendant, artifact_text=case.source["story_text"],
        context_texts=[], batch_attempts=1)
    score = core.score_bundle(case.runtime.modules, case.runtime.bundle, verdicts,
        artifact_id=case.source["opaque_story_id"], task_contract=None)
    assert replay["score"] == score["final_score"]["observed"] and replay["coverage"] == score["coverage"]
    assert case.subject._inventory(case.original) == case.original_inventory
    before = case.subject._inventory(case.descendant)
    assert case.subject.materialize_recovered_run(case.original, case.descendant, **case.kwargs) == case.result
    assert case.subject._inventory(case.descendant) == before


def test_real_isolated_host_gate_denial_prevents_suffix_adapter_launch(case, native_suffix, monkeypatch):
    materialize(case)
    original_checkpoint = (case.descendant / "responses/batch-0001.json").read_bytes()
    attempted, launches = [], []
    fixture, route = native_suffix.fixture, native_suffix.route

    def revoke(context):
        attempted.append(69 + context["batch"]["number"])
        fixture.broker._revoke_grok_host_gate(route, "Synthetic gate denial during reviewed admission")

    def forbidden(*args, **kwargs):
        launches.append(True)
        pytest.fail("Revoked isolated host gate reached fake provider")

    transport = transport_module.bind_grok_broker_transport(broker=fixture.broker, route=route,
        before_contact=revoke, runtime_check=case.runtime.verify)
    monkeypatch.setattr(fixture.broker, "_run_grok_exec", forbidden)
    with pytest.raises(core.HBQError, match="not retryable"):
        runner.run_judge(**{**case.options, "output_dir": case.descendant}, resume=True, grok_transport=transport)
    with pytest.raises(core.HBQError, match="terminal nonretryable"):
        runner.run_judge(**{**case.options, "output_dir": case.descendant}, resume=True, grok_transport=transport)
    assert attempted == [71] and launches == []
    assert (case.descendant / "responses/batch-0001.json").read_bytes() == original_checkpoint
    assert case.subject._inventory(case.original) == case.original_inventory


def test_reader_source_drift_is_rejected_before_execution(tmp_path, monkeypatch):
    subject = load(SOURCE, "recovered_reader_pin_test")
    (tmp_path / "grok70_schema_recovery.py").write_text("raise AssertionError('must not execute')", encoding="utf-8")
    monkeypatch.setattr(subject, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Recovery reader source differs"):
        subject._module("grok70_schema_recovery")


def test_real_failed_run_metadata_preserves_execution_and_source_identity():
    subject = load(SOURCE, "recovered_real_identity_test")
    path = Path.home() / "Documents/cwr-dryad-grok51-recovery-20260907-r1/native/runs" / subject.TARGET_PASS_ID / "run.json"
    if not path.is_file():
        pytest.skip("Read-only real metadata fixture is unavailable on this host")
    before = path.read_bytes()
    run = json.loads(before)
    source = {"opaque_story_id": subject.LOGICAL_SAMPLE_ID, "source_opaque_story_id": subject.STORY_ID}
    assert subject._run_identity(run, source, runner)["artifact_id"] == subject.LOGICAL_SAMPLE_ID
    with pytest.raises(ValueError, match="run identity"):
        subject._run_identity(run, {**source, "opaque_story_id": subject.STORY_ID}, runner)
    assert path.read_bytes() == before


@pytest.mark.parametrize("fault", ["original", "adoption", "amendment", "checkpoint", "wrong_anchor"])
def test_replay_rejects_changed_evidence_without_provider_contact(case, fault):
    materialize(case)
    if fault == "original":
        target = case.original / "responses/attempt-lifecycle/batch-0001/attempt-0001.settled.json"
    elif fault == "adoption":
        target = case.adopted.args["adoption_path"]
    elif fault == "amendment":
        target = case.amendment_path
    elif fault == "checkpoint":
        target = case.descendant / "responses/batch-0001.json"
    else:
        target = None
        case.anchors["expected_amendment_sha256"] = "0" * 64
    if target is not None:
        target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError):
        case.subject.load_recovered_study(case.descendant, source=case.source, runtime=case.runtime, **case.anchors)
    assert case.calls == ["original-synthetic-failure"]


def test_materialization_rejects_unapproved_contact_without_writing_descendant(case):
    path = case.kwargs["contact_path"]
    contact = json.loads(path.read_bytes())
    contact["ordinal"] = 71
    path.write_bytes(case.subject.canonical(contact))
    case.kwargs["expected_contact_sha256"] = case.subject.digest(path.read_bytes())
    with pytest.raises(ValueError, match="request 70"):
        case.subject.materialize_recovered_run(case.original, case.descendant, **case.kwargs)
    assert not case.descendant.exists()
    assert case.subject._inventory(case.original) == case.original_inventory
