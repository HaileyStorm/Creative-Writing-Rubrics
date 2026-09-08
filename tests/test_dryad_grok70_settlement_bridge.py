"""Provider-free composition of adopted Grok70 recovery and the real ledger."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_dryad_baseline_measurement_execution import (
    ROOT,
    _canonical,
    _hash,
    _prepare,
    _prepare_genesis_actual_ledger,
    _review,
    _run,
    _write_continuation,
)
from test_dryad_baseline_measurement_execution import (
    actual_ledger_case as actual_ledger_case,  # noqa: PLC0414 - register the shared pytest fixture.
)
from test_dryad_baseline_measurement_execution import (
    case as case,  # noqa: PLC0414 - register the dependency of actual_ledger_case.
)
from test_dryad_baseline_recovered_study import load, materialize


def test_real_recovered70_settles_and_renewal_prepares71(
    actual_ledger_case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    c = actual_ledger_case
    execution = c.value
    support = load(ROOT / "tests/test_dryad_baseline_recovered_study.py", "grok70_bridge_support")
    recovered_root = tmp_path / "recovery"
    recovered_root.mkdir()
    recovered = support.case.__wrapped__(recovered_root, monkeypatch)
    core = recovered.operational_core
    repository = Path(core.__file__).resolve().parents[2]
    revisions = subprocess.run(
        ["git", "-C", str(repository), "rev-list", "--reverse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()

    def git_bytes(revision: str, relative: str) -> bytes:
        return subprocess.run(
            ["git", "-C", str(repository), "show", f"{revision}:{relative}"],
            check=True, capture_output=True,
        ).stdout

    manifests = [{"revision": revision, "files": {
        relative: _hash(git_bytes(revision, relative)) for relative in core._OPERATIONAL_FILES
    }} for revision in revisions]
    source_copy = repository / execution.EXECUTION_SOURCE_RELATIVE
    captured, modules = execution._sources()
    ledger = modules[1]
    _, core_raw = ledger._core()
    monkeypatch.setattr(ledger, "_core", lambda: (core, core_raw))
    captured.pop(c.source_path)
    monkeypatch.setattr(execution, "__file__", str(source_copy))

    def source_epoch(epoch: int) -> None:
        raw = git_bytes(revisions[epoch], execution.EXECUTION_SOURCE_RELATIVE)
        source_copy.write_bytes(raw)
        captured[source_copy] = raw

    source_epoch(0)
    runtime = modules[2].load_runtime(
        c.runtime_manifest, expected_manifest_sha256=_hash(c.runtime_manifest.read_bytes()))
    fake_runner = runtime.runner
    native_admit = modules[3].admit_prefix

    # The general fixture hashes only batch numbers; this adapter binds each
    # synthetic native identity to its actual plan ordinal and run path.
    def unique_native(run_root: Path, **kwargs):
        admitted = native_admit(run_root, **kwargs)
        run_path = Path(run_root).relative_to(c.execution_root).as_posix()
        record = next(row for row in c.plan["passes"] if row["run_path"] == run_path)
        requests = [row for row in c.plan["requests"] if row["pass_id"] == record["pass_id"]
                    and row["batch_number"] <= kwargs["expected_batches"]]
        admitted["native_identities"] = [{
            "request_id_hash": _hash(f"request:{row['ordinal']}:{run_path}".encode()),
            "session_id_hash": _hash(f"session:{row['ordinal']}:{run_path}".encode()),
        } for row in requests]
        return admitted

    monkeypatch.setattr(modules[3], "admit_prefix", unique_native)
    c.state["clock"] = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)
    now = c.state["clock"]
    c.route.update({"subscription_receipt_hash": "a" * 64, "cost_evidence": {
        "allowance_state": "available", "checked_at": now.isoformat(),
        "evidence_hash": "b" * 64, "expires_at": (now + timedelta(hours=3)).isoformat(),
        "kind": "subscription_included", "version": 1,
    }})
    c.route_path.write_bytes(_canonical(c.route))
    monkeypatch.setattr(runtime.transport, "bind_grok_broker_transport", lambda **kwargs: SimpleNamespace(
        before_contact=kwargs["before_contact"], runtime_check=kwargs["runtime_check"]))

    target = c.plan["passes"][3]
    old_pass_id = target["pass_id"]
    source_raw = recovered.source["story_text"].encode()
    target.update(pass_id=recovered.subject.TARGET_PASS_ID,
                  logical_sample_id=recovered.subject.LOGICAL_SAMPLE_ID,
                  opaque_story_id=recovered.subject.STORY_ID,
                  source_sha256=_hash(source_raw), source_bytes=len(source_raw))
    (c.plan_root / target["input_path"]).write_bytes(source_raw)
    for request in c.plan["requests"]:
        if request["pass_id"] == old_pass_id:
            request.update(pass_id=target["pass_id"], logical_sample_id=target["logical_sample_id"])
    request70 = c.plan["requests"][69]
    request70["question_ids"] = [item["question"]["id"] for item in recovered.runtime.questions[:8]]
    schema70 = (recovered.original / "responses/schemas/batch-0001.json").read_bytes()
    (c.plan_root / "schemas/recovered70.json").write_bytes(schema70)
    request70.update(schema_path="schemas/recovered70.json", schema_sha256=_hash(schema70), schema_bytes=len(schema70))
    plan_raw = _canonical(c.plan)
    (c.plan_root / "plan.json").write_bytes(plan_raw)
    monkeypatch.setattr(execution, "_plan", lambda *_: (c.plan, plan_raw))

    _prepare_genesis_actual_ledger(c)
    def renewal(number: int, previous: str, old_epoch: int, new_epoch: int) -> str:
        prefix, _ = execution._execution_snapshot(c.execution_root)
        aggregates = {}
        for record in c.plan["passes"]:
            relative = f"{record['run_path']}/verdicts.jsonl"
            if relative in prefix:
                raw = (c.execution_root / relative).read_bytes()
                aggregates[relative] = {"derivation": "runner_normalized_verdicts_v1",
                    "sha256": _hash(raw), "bytes": len(raw), "verdict_count": len(raw.splitlines())}
        value = {
            "schema_version": 1, "evidence_class": "independently_reviewed_operational_renewal",
            "reviewer_task": execution.REVIEWER_TASK, "decision": "approved_operational_renewal",
            "original_initialization_sha256": c.initialization["initialization_sha256"],
            "previous_renewal_sha256": previous, "settled_cohort_number": number,
            "settled_head_settlement_sha256": c.previous_settlement_sha256,
            "preserved_prefix": {"immutable_files": {
                path: sha for path, sha in prefix.items() if path not in aggregates},
                "derived_aggregate_prefixes": aggregates},
            "next_cohort_number": number + 1, "remaining_ordinals": list(range(number * 10 + 1, 5429)),
            "old_route": dict(c.route), "new_route": dict(c.route),
            "old_route_sha256": execution._route_hash(c.route), "new_route_sha256": execution._route_hash(c.route),
            "old_receipt_sha256": "a" * 64, "new_receipt_sha256": "a" * 64,
            "old_operational_source_manifest": manifests[old_epoch],
            "new_operational_source_manifest": manifests[new_epoch],
            "reviewed_at": c.state["clock"].isoformat(),
        }
        path = c.execution_root / f"cohorts/{number:04d}/operational-renewals/0001.json"
        execution._write_new(path, _canonical(value))
        return _hash(path.read_bytes())

    for number in range(1, 7):
        if number != 1:
            c.prepared = _prepare(c, number, c.previous_settlement_sha256)
        c.state["runner_ordinals"] = list(range(number * 10 - 9, number * 10 + 1))
        review_sha = _review(c, start=now, end=now + timedelta(minutes=9))
        settled = _run(c, review_sha)
        assert settled["status"] == "settled"
        c.previous_settlement_sha256 = settled["settlement_sha256"]

    contact51_before = (c.execution_root / "contacts/request-0051.json").read_bytes()
    renewal6 = renewal(6, "0" * 64, 0, 1)
    source_epoch(1)
    c.initialization_source_sha256 = manifests[1]["files"][execution.EXECUTION_SOURCE_RELATIVE]
    c.prepared = _prepare(c, 7, c.previous_settlement_sha256, renewal6)
    review7 = _review(c, start=now, end=now + timedelta(minutes=9))
    c.state["runner_ordinals"] = list(range(61, 70))
    c.state["pause_after"] = 68
    assert _run(c, review7, operational_renewal_sha256=renewal6)["completed_ordinals"] == list(range(61, 69))
    source_epoch(2)
    c.state["clock"] = now + timedelta(minutes=10)
    amendment7 = execution.prepare_partial_source_amendment(
        c.public_inputs, c.plan_root, c.execution_root, 7,
        expected_plan_sha256=execution.PLAN_SHA256,
        expected_initialization_sha256=c.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=c.previous_settlement_sha256,
        expected_prepared_sha256=c.prepared["prepared_sha256"], expected_review_sha256=review7,
        expected_source_sha256=c.initialization_source_sha256,
        expected_operational_renewal_sha256=renewal6)
    assert amendment7["schema_version"] == 4
    assert amendment7["completed_prefix"]["ordinals"] == list(range(61, 69))
    amendment7_sha = _write_continuation(c, amendment7)
    c.initialization_source_sha256 = manifests[2]["files"][execution.EXECUTION_SOURCE_RELATIVE]
    c.state["pause_after"] = 69
    paused = _run(c, review7, continuation_sha256=amendment7_sha, operational_renewal_sha256=renewal6)
    assert paused["completed_ordinals"] == list(range(61, 70))
    assert c.state["stub_contacts"] == list(range(1, 70))

    contact70 = json.loads((c.execution_root / "contacts/request-0069.json").read_bytes())
    request70 = c.plan["requests"][69]
    contact70.update(ordinal=70, prompt_sha256=request70["prompt_sha256"], schema_sha256=request70["schema_sha256"])
    contact_path = c.execution_root / "contacts/request-0070.json"
    execution._write_new(contact_path, _canonical(contact70))
    original = c.execution_root / target["run_path"]
    original.parent.mkdir(parents=True, exist_ok=True)
    artifact_path = c.plan_root / target["input_path"]

    def original_plan_bound_failure(_context):
        recovered.calls.append("plan-bound-synthetic-failure")
        raise RuntimeError("Synthetic terminal schema failure; no external contact")

    # The executor supplies the frozen plan input path. Build this failed origin
    # with that path from inception; do not rewrite a run's source configuration.
    with pytest.raises(recovered.runtime.core.HBQError):
        recovered.runtime.runner.run_judge(**{**recovered.options, "artifact_path": str(artifact_path),
            "output_dir": original}, grok_transport=original_plan_bound_failure)
    outcome = original / "responses/grok-broker/batch-0001-attempt-0001/outcome.json"
    outcome.parent.mkdir(parents=True, exist_ok=True)
    outcome.write_bytes(recovered.adopted.args["terminal_outcome_path"].read_bytes())
    recovered.original = original
    recovered.source = {**recovered.source, "artifact_path": str(artifact_path)}
    recovered.original_inventory = recovered.subject._inventory(original)
    recovered.amendment["original_run_tree_sha256"] = _hash(_canonical(recovered.original_inventory))
    recovered.kwargs["source"] = recovered.source
    recovered.kwargs.update(contact_path=contact_path, expected_contact_sha256=_hash(contact_path.read_bytes()))
    recovered.amendment["study_recovery_summary"]["contact_sha256"] = _hash(contact_path.read_bytes())
    source_copy.write_bytes(source_copy.read_bytes() + b"\n# synthetic study recovery reader epoch\n")
    for args in (["add", execution.EXECUTION_SOURCE_RELATIVE], ["commit", "-m", "synthetic study reader epoch"]):
        subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True)
    recovered_manifest = core.current_operational_source_manifest()
    revisions.append(recovered_manifest["revision"])
    manifests.append(recovered_manifest)
    source_epoch(3)
    recovered.amendment["recovery_operational_source_manifest"] = manifests[3]
    recovered.amendment_path.write_bytes(_canonical(recovered.amendment))
    recovered.kwargs["expected_amendment_sha256"] = _hash(recovered.amendment_path.read_bytes())
    materialize(recovered)
    binding = recovered.result["expected_study_recovery"]
    assert binding["recovery_operational_source_manifest"] == manifests[3]
    assert recovered.subject._inventory(original) == recovered.original_inventory
    assert not (original / "responses/batch-0001.json").exists()
    original_before = recovered.subject._inventory(original)
    native_prefix = {path: raw for path in c.execution_root.rglob("*") if path.is_file()
                     for raw in [path.read_bytes()]}

    # Native predecessors use the fixture replay; the recovered pass goes through
    # the actual helper and runner checkpoint parser, with its external descendant.
    real_runner = recovered.runtime.runner

    class CompositeRunner:
        def __getattr__(self, name):
            return getattr(real_runner, name)

        def _load_checkpoints(self, run_root, **kwargs):
            if Path(run_root) == recovered.descendant:
                return real_runner._load_checkpoints(run_root, **kwargs)
            return fake_runner._load_checkpoints(run_root, **kwargs)

        def run_judge(self, **kwargs):
            pytest.fail("A fully contacted cohort must settle without launching a runner")

    for name, value in vars(recovered.runtime).items():
        if name != "runner":
            setattr(runtime, name, value)
    runtime.runner = CompositeRunner()
    captured[execution.RECOVERED_STUDY_SOURCE] = execution.RECOVERED_STUDY_SOURCE.read_bytes()
    original_load = execution._load
    monkeypatch.setattr(execution, "_load", lambda path, raw, prefix: recovered.subject
                        if Path(path) == execution.RECOVERED_STUDY_SOURCE else original_load(path, raw, prefix))
    monkeypatch.setattr(execution, "STUDY_RECOVERY_ADOPTION_SHA256", binding["adoption_sha256"])
    c.state["clock"] = now + timedelta(minutes=62)
    study_args = {"study_recovery_manifest_path": recovered.descendant / "recovered-study.json",
                  "expected_study_recovery_manifest_sha256": recovered.result["manifest_sha256"]}
    before_brokers = c.state["broker_constructions"]
    settled = execution.run_cohort(
        c.public_inputs, c.plan_root, c.execution_root, 7, c.queue_root,
        expected_plan_sha256=execution.PLAN_SHA256,
        expected_initialization_sha256=c.initialization["initialization_sha256"],
        expected_previous_settlement_sha256=c.previous_settlement_sha256,
        expected_prepared_sha256=c.prepared["prepared_sha256"], expected_review_sha256=review7,
        expected_source_sha256=manifests[3]["files"][execution.EXECUTION_SOURCE_RELATIVE],
        expected_operational_renewal_sha256=renewal6, expected_continuation_sha256=amendment7_sha, **study_args)
    assert settled["status"] == "settled" and settled["provider_calls"] == 0
    assert c.state["broker_constructions"] == before_brokers
    c.previous_settlement_sha256 = settled["settlement_sha256"]
    settlement7 = json.loads((c.execution_root / "cohorts/0007/settlement.json").read_bytes())
    assert settlement7["schema_version"] == 4
    assert [item["ordinals"] for item in settlement7["authorization_chain"]] == [list(range(61, 69)), [69, 70]]
    assert [item["execution_source_sha256"] for item in settlement7["authorization_chain"]] == [
        manifests[epoch]["files"][execution.EXECUTION_SOURCE_RELATIVE] for epoch in (1, 2)]
    assert settlement7["contacts"][-1] == binding["summary"]
    assert not {"request_id_hash", "session_id_hash", "checkpoint_sha256"} & set(settlement7["contacts"][-1])
    assert sum(item.get("evidence_kind") == "study_recovered" for item in settlement7["contacts"]) == 1
    assert recovered.subject._inventory(original) == original_before
    assert all(path.read_bytes() == raw for path, raw in native_prefix.items())

    common = {"expected_route_sha256": c.initialization["route_sha256"],
              "expected_execution_source_sha256": json.loads((c.execution_root / "initialization.json").read_bytes())["execution_source_sha256"],
              "expected_reviewer_task": execution.REVIEWER_TASK, "expected_study_recovery": binding}
    verified = ledger.verify_prefix(c.execution_root, c.public_inputs.read_bytes(), plan_raw,
        execution.PLAN_SHA256, c.previous_settlement_sha256, 7, **common)
    assert (verified["native_contact_count"], verified["study_recovered_contact_count"]) == (69, 1)
    assert verified["study_recovered_ordinals"] == [70]
    assert verified["contacts"][70]["execution_source_sha256"] == manifests[2]["files"][execution.EXECUTION_SOURCE_RELATIVE]
    assert verified["contacts"][51]["execution_source_sha256"] == manifests[0]["files"][execution.EXECUTION_SOURCE_RELATIVE]
    assert verified["contacts"][68]["execution_source_sha256"] == manifests[1]["files"][execution.EXECUTION_SOURCE_RELATIVE]
    assert verified["contacts"][69]["execution_source_sha256"] == manifests[2]["files"][execution.EXECUTION_SOURCE_RELATIVE]
    assert (c.execution_root / "contacts/request-0051.json").read_bytes() == contact51_before

    def prepare8(renewal_sha):
        return execution.prepare_cohort(c.public_inputs, c.plan_root, c.execution_root, 8, c.route,
            expected_plan_sha256=execution.PLAN_SHA256,
            expected_initialization_sha256=c.initialization["initialization_sha256"],
            expected_previous_settlement_sha256=c.previous_settlement_sha256,
            expected_operational_renewal_sha256=renewal_sha, **study_args)

    with pytest.raises(ValueError, match="operational renewal before cohort 8"):
        prepare8(renewal6)
    assert not (c.execution_root / "cohorts/0008").exists()
    renewal7 = renewal(7, renewal6, 2, 3)
    prepared8 = prepare8(renewal7)
    value8 = json.loads((c.execution_root / "cohorts/0008/prepared.json").read_bytes())
    assert prepared8["prepared_sha256"] == _hash(_canonical(value8))
    assert value8["request_ordinals"] == list(range(71, 81))
    renewal_value = json.loads((c.execution_root / "cohorts/0007/operational-renewals/0001.json").read_bytes())
    assert renewal_value["next_cohort_number"] == 8
    assert renewal_value["remaining_ordinals"] == list(range(71, 5429))

    class BrokerBoundaryReached(Exception):
        pass

    broker_boundary = []

    def stop_at_broker(root, _broker_class):
        assert root == c.queue_root
        broker_boundary.append(71)
        raise BrokerBoundaryReached("Synthetic zero-contact broker boundary")

    c.cohort, c.prepared = 8, prepared8
    review8 = _review(c, start=c.state["clock"], end=c.state["clock"] + timedelta(minutes=9))
    with pytest.raises(BrokerBoundaryReached):
        execution.run_cohort(c.public_inputs, c.plan_root, c.execution_root, 8, c.queue_root,
            broker_factory=stop_at_broker, expected_plan_sha256=execution.PLAN_SHA256,
            expected_initialization_sha256=c.initialization["initialization_sha256"],
            expected_previous_settlement_sha256=c.previous_settlement_sha256,
            expected_prepared_sha256=prepared8["prepared_sha256"], expected_review_sha256=review8,
            expected_source_sha256=manifests[3]["files"][execution.EXECUTION_SOURCE_RELATIVE],
            expected_operational_renewal_sha256=renewal7, **study_args)
    assert broker_boundary == [71]
    assert c.state["broker_constructions"] == before_brokers
    assert c.state["stub_contacts"] == list(range(1, 70))
    assert not (c.execution_root / "contacts/request-0071.json").exists()
    assert recovered.subject._inventory(original) == original_before
    assert recovered.calls == ["original-synthetic-failure", "plan-bound-synthetic-failure"]
