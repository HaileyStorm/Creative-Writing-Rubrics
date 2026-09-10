"""Provider-free split-root recovery analysis guards."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_recovery_analysis.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def load():
    spec = importlib.util.spec_from_file_location("dryad_grok_recovery_analysis_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identities(count: int = 2299) -> list[dict[str, str]]:
    return [{"request_id_hash": digest(f"request-{number}".encode()),
             "session_id_hash": digest(f"session-{number}".encode())} for number in range(count)]


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = load()
    train_ids = [f"train-{number:03d}" for number in range(70)]
    dev_ids = [f"dev-{number:03d}" for number in range(30)]
    ordinals = [*range(1, 1611), *range(4049, 4739)]
    rows = []
    for number, story in enumerate(train_ids + dev_ids):
        start = number * 23 if number < 70 else 1610 + (number - 70) * 23
        rows.append({"pass_id": "pass-" + story, "partition": "TRAIN" if number < 70 else "DEV",
                     "opaque_story_id": story, "ordinals": ordinals[start:start + 23], "source": {"sha256": "a" * 64, "bytes": 1},
                     "score": 50.0, "coverage": .9, "provenance": "v4_recovered70_old_v5_replacement88" if number == 3 else "recovery",
                     "verdict_rows": [{"question_id": f"q-{item:03d}", "verdict": "YES"} for item in range(178)]})
    collection = {"schema_version": 1, "evidence_class": "selected100_grok_collection_replay_only",
                  "counts": subject.EXPECTED_COUNTS, "recovered_ordinals": [70], "coverage_failures": [],
                  "full_study_admitted": False, "provider_calls_made": 0,
                  "input_commitments": {"reader_sha256": "a" * 64, "recovery_controller_sha256": "c" * 64,
                                        "recovery_manifest_sha256": "d" * 64, "plan_sha256": "e" * 64,
                                        "predecessor_sha256": "f" * 64, "old_suffix_epoch_sha256": "1" * 64,
                                        "suffix_helper_sha256": "2" * 64, "composite_helper_sha256": "0" * 64,
                                        "selected_schedule_sha256": "s" * 64,
                                        "selected_schedule_source_sha256": "t" * 64}, "rows": rows,
                  "native_identities": identities()}
    reader = SimpleNamespace(RECOVERY_SHA256="c" * 64, _canonical=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
                             _sha=digest, source_for_ordinal=lambda ordinal: "recovery" if ordinal == 88 else "original")
    collection["native_identity_commitment_sha256"] = digest(reader._canonical(collection["native_identities"]))
    calls: list[str] = []
    reader.read_selected_collection = lambda **_kwargs: (calls.append("admit") or collection)
    composite = SimpleNamespace(_identity_sets=lambda rows, req, ses: (
        (_ for _ in ()).throw(ValueError("identity collision")) if len({row["request_id_hash"] for row in rows}) != len(rows) else None))
    analysis = SimpleNamespace()
    engine = SimpleNamespace()
    monkeypatch.setattr(subject, "_capture", lambda _pins: ({}, reader, composite, analysis, engine))
    selection = {"schedule": {"sha256": "s" * 64}, "source": {"sha256": "t" * 64},
                 "verified": {"selected_train_ids": ["pass-" + value for value in train_ids],
                              "selected_dev_ids": ["pass-" + value for value in dev_ids],
                              "selected_request_ordinals": ordinals,
                              "question_ids": [f"q-{item:03d}" for item in range(178)]}}
    monkeypatch.setattr(subject, "_selection", lambda *_args, **_kwargs: (selection, {}, {"requests": set(), "sessions": set()}))
    pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    pins.update({"analysis": digest(SOURCE.read_bytes()), "reader": "a" * 64, "recovery_controller": "c" * 64})
    inputs = {"plan_root": tmp_path, "predecessor_path": tmp_path / "predecessor", "old_suffix_root": tmp_path,
              "recovery_root": tmp_path, "expected_plan_sha256": "e" * 64, "expected_predecessor_sha256": "f" * 64,
              "expected_old_epoch_sha256": "1" * 64, "expected_suffix_source_sha256": "2" * 64,
              "expected_recovery_manifest_sha256": "d" * 64, "expected_public_inputs_sha256": "i" * 64,
              "approved_v4_routes": {}, "approved_v5_routes": {}}
    return SimpleNamespace(subject=subject, tmp_path=tmp_path, pins=pins, inputs=inputs, collection=collection,
                           reader=reader, analysis=analysis, engine=engine, calls=calls)


def admit(case):
    return case.subject.admit_selected_baseline(reader_inputs=case.inputs, source_pins=case.pins)


@pytest.mark.parametrize("fault", ["coverage", "identity", "schedule", "source", "criterion", "recovered"])
def test_admission_rejects_invalid_collection_before_targets(case, fault: str) -> None:
    if fault == "coverage":
        case.collection["rows"][0]["coverage"] = .87
    elif fault == "identity":
        case.collection["native_identities"][-1] = case.collection["native_identities"][0]
        case.collection["native_identity_commitment_sha256"] = digest(case.reader._canonical(case.collection["native_identities"]))
    elif fault == "schedule":
        case.collection["rows"][0]["ordinals"][0] = 2
    elif fault == "criterion":
        case.collection["rows"][0]["verdict_rows"].reverse()
    elif fault == "recovered":
        case.collection["recovered_ordinals"] = [88]
    else:
        case.collection["input_commitments"]["reader_sha256"] = "z" * 64
    with pytest.raises(ValueError):
        admit(case)
    assert case.calls == ["admit"]


def test_admission_marks_only_selected_baseline_after_all_inherited_gates(case) -> None:
    result = admit(case)
    assert result.record["selected_baseline_admitted"] is True
    assert result.record["original_full_study_admitted"] is False
    assert result.record["collection_record"] == case.collection
    assert result.record["selection"]["request_ordinals"] == [*range(1, 1611), *range(4049, 4739)]


def setup_stages(case, monkeypatch: pytest.MonkeyPatch, admission):
    subject, calls = case.subject, case.calls
    public = case.tmp_path / "public.json"
    public.write_bytes(canonical({"TRAIN": [{"opaque_story_id": f"train-{number:03d}"} for number in range(176)],
                                  "DEV": [{"opaque_story_id": f"dev-{number:03d}"} for number in range(60)]}))
    train_target, dev_target = case.tmp_path / "train.json", case.tmp_path / "dev.json"
    train_target.write_bytes(canonical([{"opaque_story_id": f"train-{number:03d}"} for number in range(70)]))
    dev_target.write_bytes(canonical([{"opaque_story_id": f"dev-{number:03d}"} for number in range(30)]))
    train_rows = [{"opaque_story_id": f"train-{number:03d}", "verdicts": []} for number in range(70)]
    dev_rows = [{"opaque_story_id": f"dev-{number:03d}", "verdicts": []} for number in range(30)]
    projection = {"selected_schedule_sha256": "s" * 64, "projected_rows_sha256": {"TRAIN": digest(canonical(train_rows)), "DEV": digest(canonical(dev_rows))}}
    binding = {"schema_version": 1, "TRAIN": [row["opaque_story_id"] for row in train_rows], "DEV": [row["opaque_story_id"] for row in dev_rows],
               "selected_schedule_sha256": "s" * 64, "selected_schedule_source_sha256": "t" * 64}
    def partitions(_path, _expected, _view):
        return public, public.read_bytes(), {"TRAIN": set(binding["TRAIN"]), "DEV": set(binding["DEV"])}
    def targets(_pure, path, _expected, partition, _ids, _public):
        calls.append("targets-" + partition)
        values = json.loads(Path(path).read_bytes())
        return Path(path), Path(path).read_bytes(), values, {"original_target_sha256": "a" * 64, "original_count": 176 if partition == "TRAIN" else 60,
                                                              "selected_target_sha256": digest(canonical(values)), "selected_count": len(values)}
    def write(output, artifacts):
        output.mkdir()
        for name, raw in artifacts.items():
            (output / name).write_bytes(raw)
        return {name: digest(raw) for name, raw in artifacts.items()}
    analysis = SimpleNamespace(_partitions=partitions, _project_rows=lambda *_args: ({"TRAIN": train_rows, "DEV": dev_rows}, projection),
                               _engine_binding=lambda *_args: binding, _selected_targets=targets,
                               _write=write,
                               _output_preflight=lambda output, *_args: output, WORKFLOW_PATH=Path("workflow"))
    state = {"preflight_error": None}
    def fit(rows, targets, **_kwargs):
        calls.append("fit")
        return {"evidence_class": "selected100_amended_fit_unadmitted", "input_commitments": {"verdict_rows_sha256": digest(canonical(rows)), "target_rows_sha256": digest(canonical(targets))}}
    def preflight(*_args, **_kwargs):
        calls.append("preflight")
        if state["preflight_error"]:
            raise state["preflight_error"]
    def compare(rows, targets, _fit, **_kwargs):
        calls.append("compare")
        return {"evidence_class": "selected100_amended_dev_comparison_unadmitted", "input_commitments": {"verdict_rows_sha256": digest(canonical(rows)), "target_rows_sha256": digest(canonical(targets))}}
    engine = SimpleNamespace(fit_train=fit, validate_frozen_fit=preflight, evaluate_dev=compare)
    pure = SimpleNamespace(TRAIN_TARGETS_SHA256="a" * 64, DEV_TARGETS_SHA256="b" * 64, _inner_commitments=lambda *_args: None)
    composite = SimpleNamespace(_identity_sets=lambda rows, req, ses: (
        (_ for _ in ()).throw(ValueError("identity collision")) if len({row["request_id_hash"] for row in rows}) != len(rows) else None))
    monkeypatch.setattr(subject, "_capture", lambda _pins: ({}, case.reader, composite, analysis, engine))
    monkeypatch.setattr(subject, "_runtime", lambda *_args, **_kwargs: {"commitment_sha256": "k" * 64})
    monkeypatch.setattr(subject, "_load", lambda _path, _raw, label: pure if label == "workflow" else analysis)
    monkeypatch.setattr(subject, "_read", lambda path, expected, _label: (Path(path), Path(path).read_bytes()) if Path(path).exists() else (Path(path), b"source"))
    return public, train_target, dev_target, state, {"scoring_manifest_path": public, "v5_runtime_manifest_path": public,
                                                       "v5_runtime_package_root": case.tmp_path, "expected_scoring_manifest_sha256": "a" * 64,
                                                       "expected_v5_runtime_manifest_sha256": "b" * 64, "expected_v5_runtime_package_manifest_sha256": "c" * 64}


def test_train_dev_and_replay_use_full_freeze_binding_before_dev_targets(case, monkeypatch: pytest.MonkeyPatch) -> None:
    admission = admit(case)
    public, train_target, dev_target, state, scoring = setup_stages(case, monkeypatch, admission)
    case.inputs["expected_public_inputs_sha256"] = digest(public.read_bytes())
    train = case.tmp_path / "train-output"
    case.subject.fit_selected_train(reader_inputs=case.inputs, public_inputs_path=public,
        expected_public_inputs_sha256=digest(public.read_bytes()), train_targets_path=train_target, output_root=train,
        source_pins=case.pins, scoring_inputs=scoring)
    fit_path, freeze_path = train / "selected100-grok-recovery-fit-v1.json", train / "selected100-grok-recovery-train-freeze-v1.json"
    stored_train = json.loads(freeze_path.read_bytes())
    assert stored_train["admission"]["record"] == admission.record
    assert digest(canonical(stored_train["admission"]["record"])) == stored_train["admission"]["sha256"]
    bad_freeze = case.tmp_path / "hash-correct-wrong-train-freeze.json"
    stored_train["target_projection"]["original_target_sha256"] = "0" * 64
    bad_freeze.write_bytes(canonical(stored_train))
    with pytest.raises(ValueError, match="target projection"):
        case.subject.compare_selected_dev(reader_inputs=case.inputs, public_inputs_path=public,
            expected_public_inputs_sha256=digest(public.read_bytes()), dev_targets_path=dev_target, fit_path=fit_path,
            train_freeze_path=bad_freeze, output_root=case.tmp_path / "bad-dev-output", expected_fit_sha256=digest(fit_path.read_bytes()),
            expected_train_freeze_sha256=digest(bad_freeze.read_bytes()), source_pins=case.pins, scoring_inputs=scoring)
    assert "targets-DEV" not in case.calls
    state["preflight_error"] = ValueError("semantic fit rejection")
    with pytest.raises(ValueError, match="semantic"):
        case.subject.compare_selected_dev(reader_inputs=case.inputs, public_inputs_path=public,
            expected_public_inputs_sha256=digest(public.read_bytes()), dev_targets_path=dev_target, fit_path=fit_path,
            train_freeze_path=freeze_path, output_root=case.tmp_path / "dev-output", expected_fit_sha256=digest(fit_path.read_bytes()),
            expected_train_freeze_sha256=digest(freeze_path.read_bytes()), source_pins=case.pins, scoring_inputs=scoring)
    assert "targets-DEV" not in case.calls
    state["preflight_error"] = None
    dev = case.tmp_path / "dev-output"
    compared = case.subject.compare_selected_dev(reader_inputs=case.inputs, public_inputs_path=public,
        expected_public_inputs_sha256=digest(public.read_bytes()), dev_targets_path=dev_target, fit_path=fit_path,
        train_freeze_path=freeze_path, output_root=dev, expected_fit_sha256=digest(fit_path.read_bytes()),
        expected_train_freeze_sha256=digest(freeze_path.read_bytes()), source_pins=case.pins, scoring_inputs=scoring)
    comparison_path = dev / "selected100-grok-recovery-dev-comparison-v1.json"
    dev_freeze_path = dev / "selected100-grok-recovery-dev-freeze-v1.json"
    replay = case.subject.replay_selected_dev(reader_inputs=case.inputs, public_inputs_path=public,
        expected_public_inputs_sha256=digest(public.read_bytes()), dev_targets_path=dev_target, fit_path=fit_path,
        train_freeze_path=freeze_path, dev_comparison_path=comparison_path, dev_freeze_path=dev_freeze_path,
        expected_fit_sha256=digest(fit_path.read_bytes()), expected_train_freeze_sha256=digest(freeze_path.read_bytes()),
        expected_dev_comparison_sha256=digest(comparison_path.read_bytes()), expected_dev_freeze_sha256=digest(dev_freeze_path.read_bytes()),
        source_pins=case.pins, scoring_inputs=scoring)
    assert replay["comparison_raw"] == comparison_path.read_bytes()
    assert replay["freeze_raw"] == dev_freeze_path.read_bytes()
    assert compared["freeze"]["selection_frozen_at"] == replay["freeze"]["selection_frozen_at"]
