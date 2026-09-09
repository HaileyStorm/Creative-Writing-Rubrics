"""Synthetic contracts for the successor Sol composite replay adapter."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_composite_analysis_v5.py"
)
LEGACY_SOURCE = (
    ROOT
    / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_analysis_workflow.py"
)
SOL_ADMISSION_SOURCE = (
    ROOT
    / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_pass_admission.py"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()


def _module():
    spec = importlib.util.spec_from_file_location(
        "dryad_sol_composite_analysis_v5_test", SOURCE
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _hash_file(path: Path, raw: bytes) -> str:
    path.write_bytes(raw)
    return _sha(raw)


def _progress() -> dict[str, object]:
    return {
        "schema_version": 1,
        "evidence_class": "incomplete_collection_progress_snapshot",
        "sol": {
            "provisional_pass_number": 19,
            "provisional_pass_remains_unadmitted": True,
            "recovered_transport_ordinal": 221,
        },
        "full_study_admission": False,
        "alignment_result": None,
        "execution_authority": False,
    }


@pytest.fixture
def synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = _module()
    files = tmp_path / "files"
    files.mkdir()
    names = (
        "composite.py",
        "legacy.py",
        "sol.py",
        "comparison.py",
        "workflow.py",
        "plan.json",
        "public.json",
        "predecessor.json",
        "suffix-epoch.json",
        "suffix-source.py",
        "scoring.json",
        "v5-runtime.json",
        "fit.json",
        "train-freeze.json",
        "grok-dev-comparison.json",
        "grok-dev-freeze.json",
        "dev-targets.json",
        "progress.json",
        "amendment.json",
        "approval.json",
        "cutoff.json",
    )
    paths = {name: files / name for name in names}
    hashes = {name: _hash_file(path, b"{}") for name, path in paths.items()}
    hashes["progress.json"] = _hash_file(
        paths["progress.json"], _canonical(_progress())
    )
    hashes["fit.json"] = _hash_file(paths["fit.json"], _canonical({"fit": "synthetic"}))
    package = files / "package"
    package.mkdir()
    _hash_file(package / "candidate-manifest.json", b"{}")
    sol_root = files / "sol-root"
    sol_root.mkdir()
    native = files / "native"
    native.mkdir()
    bindings = files / "bindings"
    bindings.mkdir()
    events: list[str] = []
    parity = {
        "schema_version": 1,
        "evidence_class": "v1_v5_source_bound_scoring_parity",
    }
    parity_sha = _sha(subject._canonical(parity))
    expected_fit, expected_train, expected_admission = (
        hashes["fit.json"],
        hashes["train-freeze.json"],
        "a" * 64,
    )

    stored_comparison = _canonical(
        {"evidence_class": "baseline_source_verified_dev_comparison_unadmitted"}
    )
    freeze = {
        "schema_version": 1,
        "evidence_class": "composite_dev_outer_freeze_v5",
        "stage": "DEV",
        "provider_calls": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
        "sol_validation": False,
        "admission": {
            "counts": {
                "passes": 236,
                "logical": 5428,
                "native": 5427,
                "recovered": 1,
            },
            "recovered_ordinals": [70],
        },
        "admission_binding": {
            "canonical_composite_admission_sha256": expected_admission
        },
        "scoring": {"parity": parity, "commitment_sha256": parity_sha},
        "train": {"fit_sha256": expected_fit, "freeze_sha256": expected_train},
        "inner": {
            "sha256": _sha(stored_comparison),
            "evidence_class": "baseline_source_verified_dev_comparison_unadmitted",
        },
        "selection_frozen_at": "2026-09-09T00:00:00Z",
    }
    frozen = subject._canonical(freeze)
    hashes["grok-dev-comparison.json"] = _hash_file(
        paths["grok-dev-comparison.json"], stored_comparison
    )
    hashes["grok-dev-freeze.json"] = _hash_file(paths["grok-dev-freeze.json"], frozen)

    def composite_replay(*_args, **_kwargs):
        events.append("grok")
        return {
            "comparison_raw": stored_comparison,
            "freeze_raw": frozen,
            "freeze": freeze,
        }

    campaign = {
        "synthetic": "campaign",
        "complete": True,
        "transport_recovery": {"allowlist": {"ordinal": 221}},
    }
    legacy = SimpleNamespace(
        _canonical=subject._canonical,
        _load=lambda *_args: SimpleNamespace(
            PLAN_SHA256=hashes["plan.json"],
            admit_campaign=lambda *_a, **_k: campaign,
            _time=lambda value, _label: datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ),
        ),
        _amendment_context=lambda *_a, **_k: (
            {
                "manifest_sha256": "b" * 64,
                "manifest": {
                    "proposal_sha256": "c" * 64,
                    "approval_sha256": "d" * 64,
                    "approval_recorded_at": "2026-09-08T00:00:00Z",
                },
            },
            {},
        ),
        _transport_adoption_context=lambda **_k: {
            "helper": SimpleNamespace(admit_campaign=lambda *_a, **_k: campaign),
            "provenance": {"allowlist": {"ordinal": 221}},
            "captured": {},
        },
        _chronology=lambda *_a, **_k: {
            "checkpoint_count": 5428,
            "ordered_checkpoint_commitment": "e" * 64,
        },
        _sol_rows=lambda _workflow, checked, _partitions: (
            (
                {"DEV": [{"opaque_story_id": f"d{n}"} for n in range(60)]},
                {
                    "endpoint_sol_rows_sha256": "f" * 64,
                    "projected_rows_sha256": "0" * 64,
                },
            )
            if checked.get("complete") is True
            else (_ for _ in ()).throw(ValueError("complete Sol admission is required"))
        ),
    )
    workflow = SimpleNamespace(
        DEV_TARGETS_SHA256="1" * 64,
        _partition_ids=lambda *_a: (
            paths["public.json"],
            paths["public.json"].read_bytes(),
            {"TRAIN": {"t"}, "DEV": {"d"}},
        ),
        _targets=lambda *_a: (
            events.append("target")
            or (paths["dev-targets.json"], paths["dev-targets.json"].read_bytes(), [])
        ),
        _inner_commitments=lambda *_a: None,
    )
    comparison = SimpleNamespace(
        evaluate_dev=lambda *_a, **_k: (
            events.append("sol")
            or {"evidence_class": "baseline_source_verified_dev_comparison_unadmitted"}
        )
    )
    module_by_name = {
        "composite.py": SimpleNamespace(replay_composite_dev=composite_replay),
        "legacy.py": legacy,
        "comparison.py": comparison,
        "workflow.py": workflow,
    }
    monkeypatch.setattr(subject, "COMPOSITE_PATH", paths["composite.py"])
    monkeypatch.setattr(subject, "LEGACY_SOL_PATH", paths["legacy.py"])
    monkeypatch.setattr(subject, "SOL_ADMISSION_PATH", paths["sol.py"])
    monkeypatch.setattr(subject, "COMPARISON_PATH", paths["comparison.py"])
    monkeypatch.setattr(subject, "WORKFLOW_PATH", paths["workflow.py"])
    original_load = subject._load
    monkeypatch.setattr(
        subject,
        "_load",
        lambda path, raw, _label: module_by_name.get(
            path.name, original_load(path, raw, _label)
        ),
    )
    return SimpleNamespace(
        subject=subject,
        paths=paths,
        hashes=hashes,
        package=package,
        sol_root=sol_root,
        native=native,
        bindings=bindings,
        events=events,
        expected_fit=expected_fit,
        expected_train=expected_train,
        campaign=campaign,
        legacy=legacy,
    )


def test_actual_pinned_sol_admission_owns_time_parser():
    legacy = _module_from(LEGACY_SOURCE, "dryad_legacy_sol_time_contract")
    sol = _module_from(SOL_ADMISSION_SOURCE, "dryad_sol_admission_time_contract")
    assert "_time" not in vars(legacy)
    assert callable(sol._time)
    assert sol._time("2026-09-09T00:00:00Z", "synthetic") == datetime(
        2026, 9, 9, tzinfo=timezone.utc
    )


def test_rejects_future_selection_timestamp_from_sol_admission_parser(synthetic):
    synthetic.legacy._load = lambda *_args: SimpleNamespace(
        PLAN_SHA256=synthetic.hashes["plan.json"],
        admit_campaign=lambda *_a, **_k: synthetic.campaign,
        _time=lambda *_args: datetime(9999, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="in the future"):
        _run(synthetic)
    assert synthetic.events == ["grok"]


def _module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run(case, **changes):
    h, p = case.hashes, case.paths
    values = dict(  # noqa: C408 - keyword form keeps the public replay contract legible.
        plan_root=p["plan.json"].parent,
        public_inputs_path=p["public.json"],
        predecessor_path=p["predecessor.json"],
        suffix_root=p["suffix-epoch.json"].parent,
        scoring_manifest_path=p["scoring.json"],
        v5_runtime_manifest_path=p["v5-runtime.json"],
        v5_runtime_package_root=case.package,
        dev_targets_path=p["dev-targets.json"],
        fit_path=p["fit.json"],
        train_freeze_path=p["train-freeze.json"],
        grok_dev_comparison_path=p["grok-dev-comparison.json"],
        grok_dev_freeze_path=p["grok-dev-freeze.json"],
        sol_execution_root=case.sol_root,
        progress_snapshot_path=p["progress.json"],
        output_root=p["plan.json"].parent.parent / "sol-output",
        expected_plan_sha256=h["plan.json"],
        expected_public_inputs_sha256=h["public.json"],
        expected_predecessor_sha256=h["predecessor.json"],
        expected_suffix_epoch_sha256=h["suffix-epoch.json"],
        expected_suffix_source_sha256=h["suffix-source.py"],
        expected_composite_analysis_sha256=h["composite.py"],
        expected_composer_sha256="2" * 64,
        expected_workflow_sha256=h["workflow.py"],
        expected_comparison_sha256=h["comparison.py"],
        expected_scoring_runtime_loader_sha256="4" * 64,
        expected_v5_runtime_loader_sha256="5" * 64,
        expected_scoring_manifest_sha256=h["scoring.json"],
        expected_v5_runtime_manifest_sha256=h["v5-runtime.json"],
        expected_v5_runtime_package_manifest_sha256=_sha(
            (case.package / "candidate-manifest.json").read_bytes()
        ),
        expected_fit_sha256=case.expected_fit,
        expected_train_freeze_sha256=case.expected_train,
        expected_grok_dev_comparison_sha256=h["grok-dev-comparison.json"],
        expected_grok_dev_freeze_sha256=h["grok-dev-freeze.json"],
        approved_v4_routes={},
        approved_v5_routes={},
        expected_sol_analysis_sha256=_sha(SOURCE.read_bytes()),
        expected_legacy_sol_workflow_sha256=h["legacy.py"],
        expected_sol_admission_sha256=h["sol.py"],
        expected_sol_source_bindings={"source.py": "6" * 64},
        expected_sol_reviews={"7" * 64},
        expected_progress_snapshot_sha256=h["progress.json"],
        amendment_manifest_path=p["amendment.json"],
        cohort_bindings_root=case.bindings,
        approval_path=p["approval.json"],
        cutoff_path=p["cutoff.json"],
        native_root=case.native,
        transport_adoption_path=p["amendment.json"],
        expected_transport_adoption_sha256=h["amendment.json"],
        transport_incident_path=p["approval.json"],
        expected_recovered_interpreter_sha256="8" * 64,
    )
    values.update(changes)
    return case.subject.compare_composite_sol(**values)


def test_synthetic_replay_orders_composite_grok_before_target_and_separate_sol_scoring(
    synthetic,
):
    result = _run(synthetic)
    assert synthetic.events == ["grok", "target", "sol"]
    assert result["freeze"]["no_pooling"] is True
    assert (
        result["freeze"]["provider_calls"] == 0
        and result["freeze"]["execution_authority"] is False
    )
    assert result["freeze"]["full_study_admission"] is False
    assert result["freeze"]["current_sol_prefix"] == {
        "snapshot_sha256": synthetic.hashes["progress.json"],
        "provisional_pass_number": 19,
        "provisional_pass_remains_unadmitted": True,
        "recovered_transport_ordinal": 221,
    }
    assert (
        synthetic.paths["plan.json"].parent.parent
        / "sol-output"
        / "sol-composite-dev-freeze.json"
    ).is_file()


@pytest.mark.parametrize(
    "field, value",
    [
        ("provisional_pass_number", 18),
        ("provisional_pass_remains_unadmitted", False),
        ("recovered_transport_ordinal", 220),
    ],
)
def test_rejects_progress_that_relabels_unresolved_sol_prefix(synthetic, field, value):
    snapshot = _progress()
    snapshot["sol"][field] = value
    synthetic.paths["progress.json"].write_bytes(_canonical(snapshot))
    with pytest.raises(ValueError, match="unresolved gate"):
        _run(
            synthetic,
            expected_progress_snapshot_sha256=_sha(
                synthetic.paths["progress.json"].read_bytes()
            ),
        )


def test_rejects_existing_composite_freeze_byte_drift_without_sol_output(synthetic):
    path = synthetic.paths["grok-dev-freeze.json"]
    path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="bytes differ"):
        _run(synthetic, expected_grok_dev_freeze_sha256=_sha(path.read_bytes()))
    assert synthetic.events == ["grok"]
    assert not (synthetic.paths["plan.json"].parent.parent / "sol-output").exists()


def test_rejects_omitted_ordinal_221_transport_adoption_before_composite_replay(
    synthetic,
    monkeypatch,
):
    legacy = synthetic.subject._load(synthetic.paths["legacy.py"], b"{}", "legacy")
    monkeypatch.setattr(legacy, "_transport_adoption_context", lambda **_kwargs: None)
    with pytest.raises(ValueError, match="ordinal-221"):
        _run(
            synthetic,
            transport_adoption_path=None,
            expected_transport_adoption_sha256=None,
            transport_incident_path=None,
            expected_recovered_interpreter_sha256=None,
        )
    assert synthetic.events == []


def test_historical_provisional_snapshot_cannot_bypass_complete_sol_admission(
    synthetic,
):
    synthetic.campaign["complete"] = False
    with pytest.raises(ValueError, match="complete Sol admission"):
        _run(synthetic)
    assert synthetic.events == ["grok"]


def test_rejects_composite_freeze_without_v1_parity_commitment(synthetic, monkeypatch):
    original = synthetic.subject._replayed_composite_freeze
    monkeypatch.setattr(
        synthetic.subject,
        "_replayed_composite_freeze",
        lambda result, comparison, freeze, comparison_sha, freeze_sha, fit, train: (
            original(
                {
                    **result,
                    "freeze": {
                        **result["freeze"],
                        "scoring": {
                            "parity": {"evidence_class": "wrong"},
                            "commitment_sha256": "0" * 64,
                        },
                    },
                },
                comparison,
                freeze,
                comparison_sha,
                freeze_sha,
                fit,
                train,
            )
        ),
    )
    with pytest.raises(ValueError):
        _run(synthetic)


def test_rejects_input_drift_before_sol_scoring(synthetic, monkeypatch):
    original = synthetic.subject._sol_campaign

    def drift(*args, **kwargs):
        synthetic.paths["fit.json"].write_bytes(b"drift")
        return original(*args, **kwargs)

    monkeypatch.setattr(synthetic.subject, "_sol_campaign", drift)
    with pytest.raises(ValueError, match="hash drift"):
        _run(synthetic)
