from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_recovery.py"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _load():
    spec = importlib.util.spec_from_file_location("dryad_baseline_recovery", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = _load()
    plan_root, origin, external = tmp_path / "plan", tmp_path / "origin", tmp_path / "external"
    plan_root.mkdir(); origin.mkdir(); external.mkdir()
    run = subject.RUN_PATH
    plan = {
        "requests": [{"ordinal": 51, "batch_number": 5, "pass_id": "baseline8-v1/train/0003/dryad-01525cd0c309707489824aa4", "schema_path": "schemas/request-0051.json", "schema_sha256": ""}],
        "passes": [{"run_path": run, "pass_id": "baseline8-v1/train/0003/dryad-01525cd0c309707489824aa4", "batch_size": 8}],
    }
    schema = b'{"synthetic":true}'
    plan["requests"][0]["schema_sha256"] = _sha(schema)
    (plan_root / "schemas").mkdir(); (plan_root / "schemas/request-0051.json").write_bytes(schema)
    plan_raw = _json(plan); (plan_root / "plan.json").write_bytes(plan_raw)
    monkeypatch.setattr(subject, "PLAN_SHA256", _sha(plan_raw)); monkeypatch.setattr(subject, "BATCH_SCHEMA_SHA256", _sha(schema))

    route = {"provider": "synthetic"}
    route_raw = _json(route)
    prepared = {"cohort_number": 6, "plan_sha256": subject.PLAN_SHA256, "previous_settlement_sha256": subject.LAST_SETTLEMENT_SHA256,
                "execution_source_sha256": subject.BASE_EXECUTION_SOURCE_SHA256, "request_ordinals": list(range(51, 61)),
                "route_sha256": _sha(route_raw)}
    prepared_raw = _json(prepared)
    review = {"decision": "approved_cohort", "prepared_sha256": _sha(prepared_raw)}
    review_raw = _json(review)
    for relative, raw in {"cohorts/0006/prepared.json": prepared_raw, "cohorts/0006/route.json": route_raw,
                          "cohorts/0006/review.json": review_raw, "keep.txt": b"original"}.items():
        target = origin / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    contact = {"ordinal": 51, "cohort_number": 6, "plan_sha256": subject.PLAN_SHA256, "schema_sha256": subject.BATCH_SCHEMA_SHA256,
               "prepared_sha256": _sha(prepared_raw), "route_sha256": _sha(route_raw), "review_sha256": _sha(review_raw)}
    target = origin / "contacts/request-0051.json"; target.parent.mkdir(); target.write_bytes(_json(contact))
    target = origin / f"{run}/verdicts.jsonl"; target.parent.mkdir(parents=True); target.write_bytes(b"old aggregate\n")
    target = origin / f"{run}/responses/schemas/batch-0005.json"; target.parent.mkdir(parents=True); target.write_bytes(schema)
    failed = {}
    for index, suffix in enumerate(subject.FAILURE_SUFFIXES):
        target = origin / run / suffix; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(f"failed-{index}".encode()); failed[suffix] = _sha(target.read_bytes())
    bindings = {}
    for relative in subject.INCIDENT_BINDINGS:
        raw = (origin / relative).read_bytes(); bindings[relative] = {"bytes": len(raw), "sha256": _sha(raw)}
    approval = {"logical_request_ordinal": 51, "maximum_new_provider_attempts": 1, "other_terminal_attempts_authorized": False,
                "preserve_original_failed_attempt": True, "preserve_settled_requests": 50,
                "requires_fresh_post_revocation_zero_charge_rearm": True, "requires_reviewed_implementation": True}
    incident = {"logical_request_ordinal": 51, "last_settled_request": 50, "last_settlement_sha256": subject.LAST_SETTLEMENT_SHA256,
                "automatic_resend_authorized": False, "artifact_bindings": bindings}
    approval_path, incident_path = external / "approval.json", external / "incident.json"
    approval_path.write_bytes(_json(approval)); incident_path.write_bytes(_json(incident))
    monkeypatch.setattr(subject, "APPROVAL_SHA256", _sha(approval_path.read_bytes())); monkeypatch.setattr(subject, "INCIDENT_SHA256", _sha(incident_path.read_bytes()))
    probe = {"excluded_failed_batch5_files": failed, "retained_frozen_batch5_schema_sha256": subject.BATCH_SCHEMA_SHA256,
             "original_unchanged_during_copy": True, "native_prefix": {"result": "PASS"}}
    probe_path = external / "probe.json"; probe_path.write_bytes(_json(probe))
    monkeypatch.setattr(subject, "PROBE_PATH", probe_path); monkeypatch.setattr(subject, "PROBE_SHA256", _sha(probe_path.read_bytes()))
    return subject, origin, plan_root, approval_path, incident_path, tmp_path / "recovery-manifest.json"


def _prepare(case):
    subject, origin, plan, approval, incident, manifest = case
    result = subject.prepare_projection(origin, origin.parent / "derivative", plan, approval, incident, manifest,
                                        expected_approval_sha256=subject.APPROVAL_SHA256, expected_incident_sha256=subject.INCIDENT_SHA256)
    return result, origin.parent / "derivative", manifest


def test_prepare_copies_original_with_exact_exclusions_and_retained_schema(recovery):
    subject, origin, plan_root, *_ = recovery
    result, derivative, manifest = _prepare(recovery)
    assert result["provider_calls_made"] == 0 and not (derivative / "contacts/request-0051.json").exists()
    assert not (derivative / "cohorts/0006/prepared.json").exists() and not (derivative / "cohorts/0006/route.json").exists()
    assert (derivative / "keep.txt").read_bytes() == b"original"
    assert (derivative / f"{subject.RUN_PATH}/responses/schemas/batch-0005.json").read_bytes() == (plan_root / "schemas/request-0051.json").read_bytes()
    assert (origin / "contacts/request-0051.json").exists()
    raw = manifest.read_bytes(); value = json.loads(raw)
    assert value["mutable_derivative_paths"] == [f"{subject.RUN_PATH}/verdicts.jsonl"]
    assert set(value["exact_excluded_paths"]) == {"contacts/request-0051.json", "cohorts/0006/prepared.json", "cohorts/0006/route.json", "cohorts/0006/review.json", *(f"{subject.RUN_PATH}/{item}" for item in subject.FAILURE_SUFFIXES)}
    assert subject.verify_projection(manifest, _sha(raw))["status"] == "verified"


@pytest.mark.parametrize("target", ["original", "copy", "approval", "manifest"])
def test_tampering_is_rejected(recovery, target: str):
    subject, origin, _, approval, _, manifest = recovery
    result, derivative, _ = _prepare(recovery)
    expected = result["manifest_sha256"]
    if target == "original":
        (origin / "keep.txt").write_bytes(b"changed")
    elif target == "copy":
        (derivative / "keep.txt").write_bytes(b"changed")
    elif target == "approval":
        approval.write_bytes(b"{}")
    else:
        manifest.write_bytes(b"{}")
    with pytest.raises(ValueError):
        subject.verify_projection(manifest, expected)


def test_existing_or_overlapping_derivative_is_refused(recovery):
    subject, origin, plan, approval, incident, manifest = recovery
    for derivative in (origin, origin.parent / "existing"):
        if derivative.name == "existing":
            derivative.mkdir()
        with pytest.raises(ValueError):
            subject.prepare_projection(origin, derivative, plan, approval, incident, manifest,
                                       expected_approval_sha256=subject.APPROVAL_SHA256, expected_incident_sha256=subject.INCIDENT_SHA256)


def test_noncanonical_manifest_locator_is_refused(recovery):
    subject, origin, plan, approval, incident, manifest = recovery
    with pytest.raises(ValueError, match="fixed external locator"):
        subject.prepare_projection(origin, origin.parent / "derivative", plan, approval, incident, manifest.parent / "other.json",
                                   expected_approval_sha256=subject.APPROVAL_SHA256, expected_incident_sha256=subject.INCIDENT_SHA256)


def test_progress_mode_allows_only_aggregate_mutation_among_copied_files(recovery):
    subject, _, _, _, _, manifest = recovery
    result, derivative, _ = _prepare(recovery)
    aggregate = derivative / subject.MUTABLE_AGGREGATE
    aggregate.write_bytes(b"extended aggregate\n")
    derivative.joinpath("contacts/request-0051.json").parent.mkdir(exist_ok=True)
    derivative.joinpath("contacts/request-0051.json").write_bytes(b"normal future output")
    with pytest.raises(ValueError):
        subject.verify_projection(manifest, result["manifest_sha256"])
    assert subject.verify_projection(manifest, result["manifest_sha256"], allow_progress=True)["added_derivative_files"] == 1
    (derivative / "keep.txt").write_bytes(b"forbidden")
    with pytest.raises(ValueError, match="checkpoint"):
        subject.verify_projection(manifest, result["manifest_sha256"], allow_progress=True)
