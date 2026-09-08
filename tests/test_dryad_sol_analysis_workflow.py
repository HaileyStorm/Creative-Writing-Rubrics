"""Synthetic contract tests for the provider-free original-sequence Sol workflow."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_analysis_workflow.py"
RECOVERED_SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_recovered_transport_admission.py"
RECOVERED_INTERPRETER_SHA256 = "f13452e7ff878f2368f64159060362f6ecf6320e74e45a9e7d7f93362b964930"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _module():
    spec = importlib.util.spec_from_file_location("dryad_sol_analysis_workflow_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _recovered_module():
    assert _sha(RECOVERED_SOURCE.read_bytes()) == RECOVERED_INTERPRETER_SHA256
    spec = importlib.util.spec_from_file_location("dryad_sol_recovered_transport_test", RECOVERED_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _utc(value: object, _label: str) -> datetime:
    if type(value) is not str:
        raise ValueError("timestamp differs")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp is not UTC")
    return parsed


@pytest.fixture
def synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Full-shaped synthetic records; these tests make no empirical claim."""
    subject = _module()
    root = tmp_path / "inputs"
    root.mkdir()
    public = root / "public.json"
    train_ids = {f"train-{number:03d}" for number in range(176)}
    dev_ids = {f"dev-{number:03d}" for number in range(60)}
    public_raw = _canonical({"TRAIN": [{"opaque_story_id": item} for item in sorted(train_ids)],
                             "DEV": [{"opaque_story_id": item} for item in sorted(dev_ids)]})
    public.write_bytes(public_raw)
    target = root / "target-freeze.json"; target.write_bytes(b"target")
    train_target = root / "train-targets.json"; train_target.write_bytes(b"train")
    dev_target = root / "dev-targets.json"; dev_target.write_bytes(b"dev")
    fit = root / "fit.json"; fit_raw = _canonical({"fit": "synthetic"}); fit.write_bytes(fit_raw)
    train_freeze = root / "train-freeze.json"; train_raw = _canonical({"train": "synthetic"}); train_freeze.write_bytes(train_raw)
    runtime = root / "runtime.json"; runtime.write_bytes(b"runtime")
    plan_root = root / "plan"; plan_root.mkdir()
    requests = [{"ordinal": number, "pass_id": f"pass-{(number - 1) // 23:03d}", "batch_number": (number - 1) % 23 + 1}
                for number in range(1, 5429)]
    passes = [{"pass_id": f"pass-{number:03d}", "run_path": f"runs/{number:03d}"} for number in range(236)]
    plan_raw = _canonical({"passes": passes, "requests": requests}); (plan_root / "plan.json").write_bytes(plan_raw)
    grok_execution = root / "grok"; grok_execution.mkdir()
    sol_execution = root / "sol"; sol_execution.mkdir()
    rows = [{"opaque_story_id": item, "verdicts": [{"question_id": "q", "verdict": "YES"}]}
            for item in sorted(train_ids | dev_ids)]
    admission = {
        "schema_version": 2, "evidence_class": "complete_native_baseline_measurement_admission",
        "execution_authority": False, "provider_calls": 0, "admitted_passes": 236,
        "logical_requests": 5428, "admission_sha256": "a" * 64, "plan_sha256": "b" * 64,
        "initialization_sha256": "c" * 64, "runtime_manifest_sha256": _sha(runtime.read_bytes()),
        "original_initialization": {"execution_source_sha256": "d" * 64, "route_sha256": "e" * 64},
        "reviewer_task": "synthetic-reviewer", "endpoint_grok_rows": rows,
        "immutable_provenance": {"ledger_head": {"settlement_sha256": "f" * 64}},
    }
    partitions = {"TRAIN": train_ids, "DEV": dev_ids}

    def project(value, verified):
        source_rows = value["endpoint_grok_rows"]
        projected = {name: [] for name in verified}
        for row in source_rows:
            story = row["opaque_story_id"]
            for name, identifiers in verified.items():
                if story in identifiers:
                    projected[name].append({"opaque_story_id": story, "verdicts": row["verdicts"]})
                    break
            else:
                raise ValueError("outside partition")
        if {row["opaque_story_id"] for row in projected["TRAIN"]} != verified["TRAIN"] or {row["opaque_story_id"] for row in projected["DEV"]} != verified["DEV"]:
            raise ValueError("not exhaustive")
        for partition_rows in projected.values():
            partition_rows.sort(key=lambda row: row["opaque_story_id"])
        return projected, {"admission_sha256": _sha(_canonical(value)), "endpoint_grok_rows_sha256": _sha(_canonical(source_rows)), "projected_rows_sha256": {name: _sha(_canonical(rows)) for name, rows in projected.items()}}

    def commitments(result, projected, targets, _target_hash):
        assert result["input_commitments"] == {"verdict_rows_sha256": _sha(_canonical(projected)), "target_rows_sha256": _sha(_canonical(sorted(targets, key=lambda row: row["opaque_story_id"])))}

    def compare(verdicts, targets, _fit_raw, **_kwargs):
        return {"evidence_class": "baseline_source_verified_dev_comparison_unadmitted",
                "input_commitments": {"verdict_rows_sha256": _sha(_canonical(verdicts)), "target_rows_sha256": _sha(_canonical(sorted(targets, key=lambda row: row["opaque_story_id"])))} }

    fit_value = compare(project(admission, partitions)[0]["TRAIN"], [{"opaque_story_id": item, "partition": "TRAIN"} for item in sorted(train_ids)], b"")
    fit_value["evidence_class"] = "baseline_source_verified_fit_unadmitted"
    fit_raw = _canonical(fit_value); fit.write_bytes(fit_raw)
    baseline_source = root / "baseline-source.py"; baseline_source.write_bytes(b"source")
    baseline = SimpleNamespace(
        RECOVERY_MANIFEST="recovery-manifest.json", COMPARISON_PATH=Path("comparison.py"), SOURCE_PATH=baseline_source,
        TRAIN_TARGETS_SHA256="0" * 64, DEV_TARGETS_SHA256="1" * 64,
        _canonical=_canonical, _json=lambda raw, _label: json.loads(raw), _capture=lambda *_args: ({baseline_source: b"source"}, SimpleNamespace(), SimpleNamespace(evaluate_dev=compare), None),
        _recovery_context=lambda *_args, **_kwargs: None,
        _output_preflight=lambda path, *_args: Path(path),
        _target_freeze=lambda path: (Path(path), Path(path).read_bytes(), {"target": "synthetic"}),
        _admit=lambda *_args, **_kwargs: copy.deepcopy(admission),
        _partition_ids=lambda path: (Path(path), Path(path).read_bytes(), partitions),
        _project_rows=project,
        _train_freeze=lambda path, _sha_value, _fit_raw, _binding, *_args: (Path(path), Path(path).read_bytes(), {"train": "synthetic"}),
        _targets=lambda path, _sha_value, partition, identifiers: (Path(path), Path(path).read_bytes(), [{"opaque_story_id": item, "partition": partition} for item in sorted(identifiers)]),
        _unchanged=lambda _captured: None, _inner_commitments=commitments,
        _outer_freeze=lambda *_args: {},
        _write=lambda path, artifacts: _write(path, artifacts),
    )
    campaign = {"evidence_class": "complete_sol_local_lifecycle_campaign_admission", "execution_authority": False,
                "provider_calls": 0, "admitted_passes": 236, "logical_requests": 5428,
                "endpoint_sol_rows": copy.deepcopy(rows),
                "identity_ceiling": {"identity_evidence": "requested_only", "native_endpoint_contact_cardinality": "unproven", "provider_attested": False}}
    sol = SimpleNamespace(PLAN_SHA256=_sha(plan_raw), _time=_utc,
                          admit_campaign=lambda *_args, **_kwargs: copy.deepcopy(campaign),
                          _json=lambda raw, label: subject._json(raw, label))
    transport_source = root / "sol_recovered_transport_admission.py"; transport_source.write_bytes(b"transport")
    adoption = root / "transport-adoption.json"; adoption.write_bytes(b"adoption")
    incident = root / "transport-incident.json"; incident.write_bytes(b"incident")
    allowlist = copy.deepcopy(_recovered_module().ALLOWLIST)
    transport_recovery = {
        "schema_version": 1, "evidence_class": "recovered_transport_exact_ordinal_221_v1",
        "adoption_sha256": _sha(adoption.read_bytes()), "proposal_sha256": "7" * 64,
        "incident_sha256": _sha(incident.read_bytes()), "interpreter_sha256": _sha(transport_source.read_bytes()),
        "strict_admission_sha256": _sha(b"sol"), "executor_sha256": "8" * 64,
        "shared_parser_sha256": "9" * 64, "allowlist": allowlist,
        "candidate_verification_sha256": "a" * 64, "execution_authority": False,
        "provider_calls": 0, "internal_retry_cardinality": "unproven",
        "native_endpoint_contact_cardinality": "unproven", "identity_evidence": "requested_only",
        "provider_attested": False, "observed_external_launch_count": None,
        "observed_process_exit_code": None, "independent_process_exit_receipt": False,
    }

    def verify_adoption(path, *, expected_adoption_sha256, incident_path):
        if _sha(Path(path).read_bytes()) != expected_adoption_sha256:
            raise ValueError("Recovery adoption bytes differ")
        if _sha(Path(incident_path).read_bytes()) != transport_recovery["incident_sha256"]:
            raise ValueError("Recovery incident differs")
        return copy.deepcopy(transport_recovery)

    def admit_recovered_campaign(*_args, **kwargs):
        verified = verify_adoption(
            kwargs["adoption_path"], expected_adoption_sha256=kwargs["expected_adoption_sha256"],
            incident_path=kwargs["incident_path"],
        )
        return {**copy.deepcopy(campaign), "transport_recovery": verified}

    transport = SimpleNamespace(
        ALLOWLIST=copy.deepcopy(allowlist), verify_adoption=verify_adoption,
        admit_campaign=admit_recovered_campaign,
    )
    comparison_raw = _canonical(compare(project({"endpoint_grok_rows": rows}, partitions)[0]["DEV"], [{"opaque_story_id": item, "partition": "DEV"} for item in sorted(dev_ids)], fit_raw))
    workflow_sha = _sha(b"baseline")
    freeze = {
        "schema_version": 1, "evidence_class": "admitted_dev_outer_freeze", "stage": "DEV",
        "workflow": {"sha256": workflow_sha}, "runtime_manifest": {"sha256": _sha(runtime.read_bytes())},
        "sources": {"admission_sha256": "a" * 64, "comparison_sha256": "b" * 64, "target_freeze_sha256": "c" * 64},
        "target": {"partition": "DEV", "sha256": "1" * 64, "bytes": 3},
        "target_freeze": {"target": "synthetic"}, "public_partitions": {name: sorted(value) for name, value in partitions.items()},
        "admission": admission, "admission_binding": project(admission, partitions)[1],
        "inner": {"sha256": _sha(comparison_raw), "evidence_class": "baseline_source_verified_dev_comparison_unadmitted"},
        "source_provenance": {}, "train_freeze": {"sha256": _sha(train_raw), "fit_sha256": _sha(fit_raw)},
        "selection_frozen_at": "2026-09-07T00:00:00Z",
    }

    def outer(*_args):
        return {key: copy.deepcopy(value) for key, value in freeze.items() if key not in {"train_freeze", "selection_frozen_at"}}
    baseline._outer_freeze = outer
    freeze_raw = _canonical(freeze); grok_freeze = root / "grok-dev-freeze.json"; grok_freeze.write_bytes(freeze_raw)
    grok_comparison = root / "grok-comparison.json"; grok_comparison.write_bytes(comparison_raw)
    def loader(path, raw, _label):
        if Path(path).name == "baseline_analysis_workflow.py":
            return baseline
        if Path(path).name == "sol_recovered_transport_admission.py":
            return transport
        return sol
    monkeypatch.setattr(subject, "_load", loader)
    monkeypatch.setattr(subject, "BASELINE_WORKFLOW_PATH", root / "baseline_analysis_workflow.py")
    monkeypatch.setattr(subject, "SOL_ADMISSION_PATH", root / "sol_pass_admission.py")
    monkeypatch.setattr(subject, "RECOVERED_SOL_ADMISSION_PATH", transport_source)
    (root / "baseline_analysis_workflow.py").write_bytes(b"baseline")
    (root / "sol_pass_admission.py").write_bytes(b"sol")
    monkeypatch.setattr(subject, "_capture_sol_sources", lambda *_args: {})
    monkeypatch.setattr(subject, "_chronology", lambda *_args: {"checkpoint_count": 5428, "first_authorized_at": "2026-09-07T00:00:00Z", "last_authorized_at": "2026-09-07T01:00:00Z", "ordered_checkpoint_commitment": "0" * 64})
    return SimpleNamespace(subject=subject, root=root, public=public, plan=plan_root, grok_execution=grok_execution,
                           sol_execution=sol_execution, runtime=runtime, target=target, train_target=train_target,
                           dev_target=dev_target, fit=fit, train_freeze=train_freeze, grok_comparison=grok_comparison,
                           grok_freeze=grok_freeze, freeze=freeze, baseline=baseline, campaign=campaign,
                           grok_admission=admission, transport_source=transport_source, adoption=adoption,
                           incident=incident, transport_recovery=transport_recovery, transport=transport)


def _write(path: Path, artifacts: dict[str, bytes]) -> dict[str, str]:
    path.mkdir()
    for name, raw in artifacts.items(): (path / name).write_bytes(raw)
    return {name: _sha(raw) for name, raw in artifacts.items()}


def _run(case, output: Path | None = None, **kwargs):
    return case.subject.compare_original_sequence_sol(
        case.public, case.plan, case.grok_execution, case.sol_execution, case.runtime, case.target,
        case.train_target, case.dev_target, case.fit, case.train_freeze, case.grok_comparison,
        case.grok_freeze, output or (case.root / "external-output"),
        expected_grok_dev_freeze_sha256=_sha(case.grok_freeze.read_bytes()),
        expected_wrapper_sha256=_sha(SOURCE.read_bytes()), expected_sol_admission_sha256=_sha((case.root / "sol_pass_admission.py").read_bytes()),
        expected_sol_source_bindings={"source.py": "a" * 64}, expected_sol_reviews={"b" * 64}, **kwargs,
    )


def _transport_options(case) -> dict[str, object]:
    return {
        "transport_adoption_path": case.adoption,
        "expected_transport_adoption_sha256": _sha(case.adoption.read_bytes()),
        "transport_incident_path": case.incident,
        "expected_recovered_interpreter_sha256": _sha(case.transport_source.read_bytes()),
    }


def test_full_shaped_provider_free_composition_is_original_sequence_only(synthetic):
    result = _run(synthetic)
    assert result["freeze"]["evidence_class"] == "original_sequence_sol_dev_outer_freeze"
    assert result["freeze"]["provider_calls"] == 0 and result["freeze"]["execution_authority"] is False
    assert result["freeze"]["sol_comparison_completed"] is True
    assert result["freeze"]["workflow"] == {"sha256": _sha(SOURCE.read_bytes())}
    assert result["freeze"]["sol_admission"]["chronology"]["checkpoint_count"] == 5428
    assert set(result["freeze"]["sol_admission"]["row_binding"]) == {"endpoint_sol_rows_sha256", "projected_rows_sha256"}
    assert "transport_recovery" not in result["freeze"]["sol_admission"]
    assert (synthetic.root / "external-output" / "sol-dev-comparison-unadmitted.json").is_file()


@pytest.mark.parametrize("missing", [
    "transport_adoption_path", "expected_transport_adoption_sha256",
    "transport_incident_path", "expected_recovered_interpreter_sha256",
])
def test_rejects_partial_recovered_transport_adoption_before_replay(synthetic, monkeypatch, missing):
    monkeypatch.setattr(
        synthetic.baseline, "_output_preflight",
        lambda *_args: (_ for _ in ()).throw(AssertionError("replay should not begin")),
    )
    options = _transport_options(synthetic)
    options.pop(missing)
    with pytest.raises(ValueError, match="arguments must be supplied together"):
        _run(synthetic, **options)


@pytest.mark.parametrize("kind", ["interpreter", "adoption", "incident", "strict_source"])
def test_rejects_recovered_transport_hash_or_source_drift(synthetic, kind):
    options = _transport_options(synthetic)
    if kind == "interpreter":
        options["expected_recovered_interpreter_sha256"] = "0" * 64
    elif kind == "adoption":
        options["expected_transport_adoption_sha256"] = "0" * 64
    elif kind == "incident":
        synthetic.incident.write_bytes(b"changed")
    else:
        synthetic.transport_recovery["strict_admission_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        _run(synthetic, **options)


@pytest.mark.parametrize("fault", ["omitted", "mismatched"])
def test_rejects_missing_or_mismatched_recovered_transport_campaign_provenance(synthetic, monkeypatch, fault):
    def malformed_campaign(*_args, **_kwargs):
        result = copy.deepcopy(synthetic.campaign)
        if fault == "mismatched":
            result["transport_recovery"] = {**synthetic.transport_recovery, "adoption_sha256": "0" * 64}
        return result

    monkeypatch.setattr(synthetic.transport, "admit_campaign", malformed_campaign)
    with pytest.raises(ValueError, match="campaign provenance"):
        _run(synthetic, **_transport_options(synthetic))


def test_recovered_transport_opt_in_carries_ordinal_221_without_changing_comparison(synthetic):
    pinned_interpreter = _recovered_module()
    strict = _run(synthetic, synthetic.root / "strict-output")
    recovered = _run(synthetic, synthetic.root / "recovered-output", **_transport_options(synthetic))
    provenance = recovered["freeze"]["sol_admission"]["transport_recovery"]
    assert provenance == synthetic.transport_recovery
    assert provenance["allowlist"] == pinned_interpreter.ALLOWLIST
    assert provenance["allowlist"]["ordinal"] == 221
    assert provenance["internal_retry_cardinality"] == "unproven"
    assert provenance["native_endpoint_contact_cardinality"] == "unproven"
    assert recovered["freeze"]["inner"] == strict["freeze"]["inner"]
    assert recovered["artifacts"]["sol-dev-comparison-unadmitted.json"] == strict["artifacts"]["sol-dev-comparison-unadmitted.json"]


@pytest.mark.parametrize("stamp", [None, "2026-09-07T00:00:00-07:00", "9999-01-01T00:00:00Z"])
def test_rejects_missing_nonutc_or_future_grok_selection_time(synthetic, stamp):
    frozen = copy.deepcopy(synthetic.freeze)
    frozen["selection_frozen_at"] = stamp
    with pytest.raises(ValueError):
        synthetic.subject._dev_freeze(_canonical(frozen), SimpleNamespace(_time=_utc))


@pytest.mark.parametrize("campaign_fault", ["missing_rows", "partial_admission"])
def test_rejects_incomplete_sol_campaign(synthetic, monkeypatch, campaign_fault):
    if campaign_fault == "missing_rows":
        synthetic.campaign["endpoint_sol_rows"].pop()
    else:
        synthetic.campaign["admitted_passes"] = 235
    sol = synthetic.subject._load(synthetic.root / "sol_pass_admission.py", b"sol", "sol")
    monkeypatch.setattr(sol, "admit_campaign", lambda *_args, **_kwargs: copy.deepcopy(synthetic.campaign))
    with pytest.raises(ValueError): _run(synthetic)


def test_rejects_changed_grok_comparison_bytes(synthetic):
    synthetic.grok_comparison.write_bytes(b"{}")
    synthetic.freeze["inner"]["sha256"] = _sha(b"{}")
    synthetic.grok_freeze.write_bytes(_canonical(synthetic.freeze))
    with pytest.raises(ValueError, match="comparison bytes"): _run(synthetic)


def test_rejects_altered_frozen_fit_and_incomplete_grok_admission(synthetic):
    synthetic.fit.write_bytes(b"{}")
    synthetic.freeze["train_freeze"]["fit_sha256"] = _sha(b"{}")
    synthetic.grok_freeze.write_bytes(_canonical(synthetic.freeze))
    with pytest.raises(ValueError, match="TRAIN fit"): _run(synthetic)
    synthetic.fit.write_bytes(_canonical({"evidence_class": "baseline_source_verified_fit_unadmitted", "input_commitments": {}}))
    synthetic.grok_admission["endpoint_grok_rows"].pop()
    synthetic.freeze["train_freeze"]["fit_sha256"] = _sha(synthetic.fit.read_bytes())
    synthetic.grok_freeze.write_bytes(_canonical(synthetic.freeze))
    with pytest.raises(ValueError): _run(synthetic)


def test_output_overlap_is_rejected_before_admission(synthetic, monkeypatch):
    monkeypatch.setattr(synthetic.baseline, "_output_preflight", lambda *_args: (_ for _ in ()).throw(ValueError("fresh external")))
    with pytest.raises(ValueError, match="fresh external"): _run(synthetic, synthetic.root / "inside")


def test_rejects_plan_input_drift_during_sol_admission(synthetic, monkeypatch):
    def unchanged(captured):
        if any(path.read_bytes() != raw for path, raw in captured.items()):
            raise ValueError("input changed")
    synthetic.baseline._unchanged = unchanged
    sol = synthetic.subject._load(synthetic.root / "sol_pass_admission.py", b"sol", "sol")
    def mutate(*_args, **_kwargs):
        (synthetic.plan / "plan.json").write_bytes(b"drift")
        return copy.deepcopy(synthetic.campaign)
    monkeypatch.setattr(sol, "admit_campaign", mutate)
    with pytest.raises(ValueError, match="input changed"): _run(synthetic)


def test_chronology_requires_all_ordinals_and_authorization_after_or_at_boundary(tmp_path, monkeypatch):
    subject = _module(); plan = tmp_path / "plan"; plan.mkdir(); execution = tmp_path / "execution"; execution.mkdir()
    requests = [{"ordinal": number, "pass_id": "pass-000", "batch_number": number} for number in range(1, 5429)]
    (plan / "plan.json").write_bytes(_canonical({"passes": [{"pass_id": "pass-000", "run_path": "run"}] + [{"pass_id": f"pass-{number:03d}", "run_path": f"run-{number}"} for number in range(1, 236)], "requests": requests}))
    raw_by_path = {}
    for request in requests:
        path = execution / "run" / "responses" / f"batch-{request['batch_number']:04d}.json"
        raw_by_path[path] = _canonical({"provider": {"dryad_sol": {"ordinal": request["ordinal"], "authorized_at": "2026-09-07T00:00:00Z"}}})
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda path: raw_by_path[path] if path in raw_by_path else original(path))
    sol = SimpleNamespace(PLAN_SHA256=_sha((plan / "plan.json").read_bytes()), _json=subject._json, _time=_utc)
    evidence = subject._chronology(sol, plan, execution, datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert evidence["checkpoint_count"] == 5428
    first = execution / "run" / "responses" / "batch-0001.json"
    raw_by_path[first] = _canonical({"provider": {"dryad_sol": {"ordinal": 1, "authorized_at": "2026-09-06T23:59:59Z"}}})
    with pytest.raises(ValueError, match="precedes"): subject._chronology(sol, plan, execution, datetime(2026, 9, 7, tzinfo=timezone.utc))
    raw_by_path[first] = _canonical({"provider": {"dryad_sol": {"ordinal": 9, "authorized_at": "2026-09-07T00:00:00Z"}}})
    with pytest.raises(ValueError, match="ordinal"): subject._chronology(sol, plan, execution, datetime(2026, 9, 7, tzinfo=timezone.utc))


def test_amended_comparison_uses_shared_replay_and_labels_bound_provenance(synthetic, monkeypatch):
    manifest = {
        "approval_sha256": "a" * 64, "proposal_sha256": "b" * 64, "cutoff_sha256": "c" * 64,
        "approval_recorded_at": "2026-09-07T14:37:32.080521+00:00",
        "source_bindings": {"amendment_guard_sha256": "d" * 64},
    }
    amendment = {
        "manifest": manifest, "manifest_sha256": "e" * 64, "bindings_root": synthetic.root / "bindings",
        "captured": {}, "prefix_ordinal": 120,
        "approval_recorded_at": datetime(2026, 9, 7, 14, 37, 32, 80521, tzinfo=timezone.utc),
    }
    monkeypatch.setattr(synthetic.subject, "_amendment_context", lambda *_args, **_kwargs: (amendment, {}))
    monkeypatch.setattr(synthetic.subject, "_chronology", lambda *_args: {
        "checkpoint_count": 5428, "first_authorized_at": "2026-09-06T00:00:00Z",
        "last_authorized_at": "2026-09-07T01:00:00Z", "ordered_checkpoint_commitment": "0" * 64})
    result = synthetic.subject.compare_amended_sequence_sol(
        synthetic.public, synthetic.plan, synthetic.grok_execution, synthetic.sol_execution, synthetic.runtime,
        synthetic.target, synthetic.train_target, synthetic.dev_target, synthetic.fit, synthetic.train_freeze,
        synthetic.grok_comparison, synthetic.grok_freeze, synthetic.root / "amended-output",
        expected_grok_dev_freeze_sha256=_sha(synthetic.grok_freeze.read_bytes()),
        expected_wrapper_sha256=_sha(SOURCE.read_bytes()),
        expected_sol_admission_sha256=_sha((synthetic.root / "sol_pass_admission.py").read_bytes()),
        expected_sol_source_bindings={"source.py": "a" * 64}, expected_sol_reviews={"b" * 64},
        amendment_manifest_path=synthetic.root / "unused-manifest.json", cohort_bindings_root=synthetic.root / "bindings",
        approval_path=synthetic.root / "unused-approval.json", cutoff_path=synthetic.root / "unused-cutoff.json",
        native_root=synthetic.sol_execution)
    assert result["freeze"]["evidence_class"] == "sequencing_amended_after_partial_sol_observation"
    assert result["freeze"]["sequencing_amendment"]["manifest_sha256"] == "e" * 64
    assert result["freeze"]["sequencing_amendment"]["deviation_label"] == "sequencing_amended_after_partial_sol_observation"
    assert result["freeze"]["sequencing_amendment"]["approval_recorded_at"] == "2026-09-07T14:37:32.080521+00:00"
