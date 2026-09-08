from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_measurement_ledger.py"
PUBLIC_INPUTS = Path.home() / "Documents/cwr-dryad-pilot-source-freeze-20260905-r1/public-inputs.json"
PREPARED = Path.home() / "Documents/cwr-dryad-baseline8-plan-20260906-r1/plan.json"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"


def load():
    spec = importlib.util.spec_from_file_location("dryad_baseline_measurement_ledger", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepared_baseline_plan_binds_fixed_operational_geometry() -> None:
    subject = load()
    raw = PREPARED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PLAN_SHA256
    plan = json.loads(raw)
    core, _ = subject._core()
    geometry = subject._geometry(PUBLIC_INPUTS.read_bytes(), raw, PLAN_SHA256, core)
    groups = subject.cohort_groups(plan)
    assert plan["dispatch_batch_size"] == 8 and plan["empirical_batch_cap"] is None
    assert plan["execution_authority"] is False and plan["native_admission"] is False
    assert len(geometry.passes) == 236 and len(geometry.requests) == 5428
    assert len(groups) == 543 and [len(group) for group in groups] == [10] * 542 + [8]
    assert tuple(ordinal for group in groups for ordinal in group) == tuple(range(1, 5429))


def test_wrapper_rejects_malformed_or_short_baseline_geometry() -> None:
    subject = load()
    with pytest.raises(ValueError, match="geometry"):
        subject.cohort_groups({"requests": []})


def test_wrapper_rejects_reparse_sources_before_hash_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    original_lstat = Path.lstat

    def reparse(path: Path):
        info = original_lstat(path)
        if path == subject.PLAN_SOURCE:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="link or reparse"):
        subject._source(subject.PLAN_SOURCE, subject.PLAN_SOURCE_SHA256, "Baseline planner")

    link = tmp_path / "planner-link.py"
    try:
        link.symlink_to(subject.PLAN_SOURCE)
    except OSError:
        return
    monkeypatch.setattr(Path, "lstat", original_lstat)
    with pytest.raises(ValueError, match="link or reparse"):
        subject._source(link, subject.PLAN_SOURCE_SHA256, "Baseline planner")


def test_wrapper_validates_schema3_renewal_candidate_with_pinned_core(monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    core, _ = subject._core()
    plan_sha256, route_sha256, prepared_sha256 = "a" * 64, "b" * 64, "c" * 64
    source_sha256, review_sha256, continuation_sha256 = "d" * 64, "e" * 64, "f" * 64
    passes = {"pass-1": {"pass_id": "pass-1", "logical_sample_id": "sample-1", "source_sha256": "1" * 64}}
    requests = {
        ordinal: {"ordinal": ordinal, "pass_id": "pass-1", "prompt_sha256": f"{ordinal:064x}", "schema_sha256": "2" * 64}
        for ordinal in (1, 2)
    }
    geometry = core.LedgerGeometry(plan_sha256, requests, passes, ((1, 2),))
    monkeypatch.setattr(subject, "_geometry", lambda *_: geometry)
    renewal_start = datetime(2026, 9, 6, 0, 11, tzinfo=timezone.utc)
    continuation = {
        "sha256": continuation_sha256,
        "source_sha256": source_sha256,
        "version": 2,
        "start": renewal_start,
        "end": renewal_start + timedelta(minutes=10),
        "value": {"completed_prefix": {"ordinals": [], "contacts": [], "run_files": {},
                                        "run_tree_sha256": hashlib.sha256(b"{}").hexdigest()}},
    }
    contacts: dict[int, bytes] = {}
    settlement_contacts = []
    for ordinal in (1, 2):
        raw = json.dumps({
            "schema_version": 1, "cohort_number": 1, "ordinal": ordinal, "plan_sha256": plan_sha256,
            "prepared_sha256": prepared_sha256, "review_sha256": continuation_sha256, "route_sha256": route_sha256,
            "prompt_sha256": requests[ordinal]["prompt_sha256"], "schema_sha256": "2" * 64,
            "admitted_at": (renewal_start + timedelta(minutes=ordinal)).isoformat().replace("+00:00", "Z"),
        }, sort_keys=True, separators=(",", ":")).encode()
        contacts[ordinal] = raw
        settlement_contacts.append({"ordinal": ordinal, "contact_sha256": hashlib.sha256(raw).hexdigest(),
                                    "checkpoint_sha256": f"{ordinal + 20:064x}",
                                    "request_id_hash": f"{ordinal + 30:064x}",
                                    "session_id_hash": f"{ordinal + 40:064x}"})
    settlement = {
        "schema_version": 3, "cohort_number": 1, "plan_sha256": plan_sha256,
        "prepared_sha256": prepared_sha256, "review_sha256": review_sha256, "route_sha256": route_sha256,
        "previous_settlement_sha256": "0" * 64,
        "settled_at": (renewal_start + timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),
        "contacts": settlement_contacts,
        "authorization_chain": [
            {"authorization_sha256": review_sha256, "execution_source_sha256": source_sha256, "ordinals": []},
            {"authorization_sha256": continuation_sha256, "execution_source_sha256": source_sha256, "ordinals": [1, 2]},
        ],
    }
    kwargs = {
        "cohort_number": 1, "ordinals": (1, 2), "prepared_sha256": prepared_sha256,
        "review_sha256": review_sha256, "route_sha256": route_sha256,
        "previous_settlement_sha256": "0" * 64,
        "review_start": datetime(2026, 9, 6, tzinfo=timezone.utc),
        "review_end": datetime(2026, 9, 6, 0, 10, tzinfo=timezone.utc),
        "continuations": [continuation], "settlement": settlement, "contact_records": contacts,
        "expected_execution_source_sha256": source_sha256,
    }
    verified, authorizations = subject.validate_candidate_cohort(b"synthetic", b"synthetic", plan_sha256, **kwargs)
    assert set(verified) == {1, 2} and set(authorizations) == {review_sha256, continuation_sha256}

    for field, replacement in (
        ("schema_version", 2),
        ("cohort_number", 2),
        ("ordinal", 3),
        ("prompt_sha256", "0" * 64),
        ("schema_sha256", "0" * 64),
    ):
        malformed = json.loads(contacts[1])
        malformed[field] = replacement
        malformed_raw = json.dumps(malformed, sort_keys=True, separators=(",", ":")).encode()
        bad_contacts = {**contacts, 1: malformed_raw}
        bad_settlement = {**settlement, "contacts": [dict(item) for item in settlement_contacts]}
        bad_settlement["contacts"][0]["contact_sha256"] = hashlib.sha256(malformed_raw).hexdigest()
        with pytest.raises(ValueError):
            subject.validate_candidate_cohort(b"synthetic", b"synthetic", plan_sha256,
                                             **{**kwargs, "settlement": bad_settlement, "contact_records": bad_contacts})


def test_wrapper_reads_renewal_epochs_through_its_pinned_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core_tests = ROOT / "tests" / "test_cohort_ledger_core.py"
    spec = importlib.util.spec_from_file_location("renewal_core_test_support", core_tests)
    assert spec and spec.loader
    support = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = support
    try:
        spec.loader.exec_module(support)
        fixture = support.operational_renewal_ledger(tmp_path)
    finally:
        sys.modules.pop(spec.name, None)

    subject = load()
    fake_core_path = fixture["core"].__file__
    monkeypatch.setattr(subject, "CORE", Path(fake_core_path))
    monkeypatch.setattr(subject, "CORE_SHA256", hashlib.sha256(Path(fake_core_path).read_bytes()).hexdigest())
    monkeypatch.setattr(subject, "_geometry", lambda *_: fixture["geometry"])
    original_core = subject._core

    def pinned_core():
        loaded, raw = original_core()
        loaded.HISTORICAL_OPERATIONAL_REVISION = fixture["core"].HISTORICAL_OPERATIONAL_REVISION
        return loaded, raw

    monkeypatch.setattr(subject, "_core", pinned_core)
    kwargs = {
        "expected_route_sha256": support.sha(fixture["routes"][0]),
        "expected_execution_source_sha256": fixture["sources"][0],
        "expected_reviewer_task": fixture["reviewer"],
    }
    verified = subject.verify_prefix(
        fixture["root"], b"synthetic-public-inputs", b"synthetic-plan", "a" * 64, fixture["head"], 3, **kwargs,
    )
    assert [item["sha256"] for item in verified["renewals"]] == list(fixture["renewals"])
    assert verified["epochs"][3]["operational_renewal_sha256"] == fixture["renewals"][1]

    with pytest.raises(ValueError):
        subject.verify_prefix(
            fixture["root"], b"synthetic-public-inputs", b"synthetic-plan", "a" * 64, fixture["head"], 3,
            **{**kwargs, "expected_route_sha256": "0" * 64},
        )


def test_partial_candidate_builder_validates_unused_continuation_and_current_committed_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("partial_core_test_support", ROOT / "tests/test_cohort_ledger_core.py")
    assert spec and spec.loader
    support = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = support
    try:
        spec.loader.exec_module(support)
        subject = load()
        original_core = subject._core

        def build(state):
            core_path = Path(state["core"].__file__)
            monkeypatch.setattr(subject, "CORE", core_path)
            monkeypatch.setattr(subject, "CORE_SHA256", support.sha(core_path.read_bytes()))
            monkeypatch.setattr(subject, "_geometry", lambda *_: state["geometry"])

            def pinned_core():
                core, raw = original_core()
                core.HISTORICAL_OPERATIONAL_REVISION = state["core"].HISTORICAL_OPERATIONAL_REVISION
                return core, raw

            monkeypatch.setattr(subject, "_core", pinned_core)
            pending = frozenset({"cohorts/0002/prepared.json", "cohorts/0002/review.json", "cohorts/0002/route.json",
                                 "cohorts/0002/review-continuations/0001.json", "contacts/request-0002.json"})
            with pytest.raises(ValueError, match="current|Latest operational"):
                subject.verify_prefix(state["root"], b"synthetic-inputs", b"synthetic-plan", "a" * 64,
                                      state["first"], 1, expected_route_sha256=support.sha(state["routes"][0]),
                                      expected_execution_source_sha256=state["sources"][0],
                                      expected_reviewer_task=state["reviewer"], allowed_pending_paths=pending)
            return subject.prepare_partial_source_amendment_candidate(
                state["root"], b"synthetic-inputs", b"synthetic-plan", expected_plan_sha256="a" * 64,
                expected_initialization_sha256=support.sha(state["initialization"]),
                expected_previous_settlement_sha256=state["first"], cohort_number=2,
                expected_prepared_sha256=support.sha(state["prepared_raw"]),
                expected_review_sha256=support.sha(state["review_raw"]),
                expected_operational_renewal_sha256=state["renewal_one"],
                expected_route_sha256=support.sha(state["routes"][1]),
                expected_execution_source_sha256=state["sources"][1],
                expected_prior_authorization_sha256=support.sha(state["unused_raw"]),
                completed_prefix=state["prefix"], expected_reviewer_task=state["reviewer"])

        support.partial_source_amendment_ledger(tmp_path, candidate_builder=build, late_renewal=True)
    finally:
        sys.modules.pop(spec.name, None)


def test_wrapper_requires_external_study_recovery_binding_for_mixed_settlement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("study_core_test_support", ROOT / "tests/test_cohort_ledger_core.py")
    assert spec and spec.loader
    support = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = support
    try:
        spec.loader.exec_module(support)
        state = support.study_recovery_ledger(tmp_path)
    finally:
        sys.modules.pop(spec.name, None)
    subject = load()
    core_path = Path(state["core"].__file__)
    monkeypatch.setattr(subject, "CORE", core_path)
    monkeypatch.setattr(subject, "CORE_SHA256", support.sha(core_path.read_bytes()))
    monkeypatch.setattr(subject, "_geometry", lambda *_: state["geometry"])
    original_core = subject._core

    def pinned_core():
        core, raw = original_core()
        core.HISTORICAL_OPERATIONAL_REVISION = state["core"].HISTORICAL_OPERATIONAL_REVISION
        return core, raw

    monkeypatch.setattr(subject, "_core", pinned_core)
    contacts, _ = subject.validate_candidate_cohort(b"synthetic-inputs", b"synthetic-plan", "a" * 64, **state["candidate"])
    assert sum("request_id_hash" in contact for contact in contacts.values()) == 9
    common = {"expected_route_sha256": support.sha(state["routes"][0]),
              "expected_execution_source_sha256": state["sources"][0], "expected_reviewer_task": state["reviewer"],
              "expected_study_recovery": state["binding"]}
    subject.verify_prefix(state["root"], b"synthetic-inputs", b"synthetic-plan", "a" * 64, state["head"], 6,
                          allowed_pending_paths=state["pending"], **common)
    head = support.sha(support.write(state["root"], "cohorts/0007/settlement.json", state["candidate"]["settlement"]))
    verified = subject.verify_prefix(state["root"], b"synthetic-inputs", b"synthetic-plan", "a" * 64, head, 7, **common)
    assert (verified["native_contact_count"], verified["study_recovered_contact_count"]) == (69, 1)
    with pytest.raises(ValueError, match="Study recovered settlement"):
        subject.verify_prefix(state["root"], b"synthetic-inputs", b"synthetic-plan", "a" * 64, head, 7,
                              **{**common, "expected_study_recovery": None})
