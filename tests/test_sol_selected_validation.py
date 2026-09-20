from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_selected_validation.py"
SOL_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-remaining-20260910-r3")
PUBLIC = Path(r"C:\Users\Haile\Documents\cwr-dryad-pilot-source-freeze-20260905-r1\public-inputs.json")
DEV_TARGETS = Path(r"C:\Users\Haile\Documents\cwr-dryad-analysis-targets-20260905-r2\dev-targets.json")
RECEIPT = SOL_ROOT / "selected100-complete-collection-replay.json"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def load() -> Any:
    spec = importlib.util.spec_from_file_location("selected_sol_validation_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(binding: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for partition in ("TRAIN", "DEV"):
        for number, story in enumerate(binding[partition]):
            pass_id = f"{partition.lower()}-{number:03d}"
            rows.append({
                "pass_id": pass_id,
                "original_opaque_story_id": story,
                "partition": partition,
                "canonical_verdicts": [
                    {"question_id": f"q-{index:03d}", "verdict": "YES"}
                    for index in range(178)
                ],
                "coverage": 0.86 if partition == "TRAIN" and number == 19 else 0.8648 if partition == "TRAIN" and number == 42 else 0.95,
                "score": 50.0,
                "request_commitments": [{"ordinal": number + 1, "path": f"sol/{partition}/{number}", "sha256": "a" * 64}],
                "evidence_classes": ["original_native_checkpoint"],
            })
    return rows


def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mutate_during_evaluate: bool = False) -> tuple[Any, dict[str, Any], dict[str, Any], list[str], Any]:
    subject = load()
    events: list[str] = []
    binding = {
        "schema_version": 1,
        "selected_schedule_sha256": subject.SELECTED_SCHEDULE_SHA256,
        "selected_schedule_source_sha256": subject.SELECTED_SCHEDULE_SOURCE_SHA256,
        "TRAIN": [f"train-{index:03d}" for index in range(70)],
        "DEV": [f"dev-{index:03d}" for index in range(30)],
    }
    fit = tmp_path / "fit.json"
    fit.write_bytes(b"fit-bytes\n")
    train_freeze = tmp_path / "train-freeze.json"
    train_freeze.write_bytes(canonical({"engine_binding": binding}))
    dev_comparison = tmp_path / "dev-comparison.json"
    dev_comparison.write_bytes(b"dev-comparison\n")
    dev_freeze = tmp_path / "dev-freeze.json"
    dev_freeze.write_bytes(canonical({
        "engine_binding": binding,
        "train": {"fit_sha256": digest(fit.read_bytes()), "freeze_sha256": digest(train_freeze.read_bytes())},
    }))
    scoring_manifest = tmp_path / "scoring.json"
    scoring_manifest.write_bytes(b"scoring\n")
    package_root = tmp_path / "package"
    package_root.mkdir()
    source = tmp_path / "captured-source.py"
    source.write_bytes(b"source\n")
    workflow = tmp_path / "workflow.py"
    workflow.write_bytes(b"workflow\n")
    pure = SimpleNamespace(DEV_TARGETS_SHA256=subject.DEV_TARGETS_SHA256)
    selected_targets = [{"opaque_story_id": story, "partition": "DEV"} for story in binding["DEV"]]

    def selected_target_projection(_pure: Any, path: Path, *_args: Any, **_kwargs: Any) -> tuple[Path, bytes, list[dict[str, Any]], dict[str, Any]]:
        return Path(path), Path(path).read_bytes(), selected_targets, {
            "original_target_sha256": subject.DEV_TARGETS_SHA256,
            "original_count": 60,
            "selected_target_sha256": "a" * 64,
            "selected_count": 30,
        }

    composite = SimpleNamespace(
        WORKFLOW_PATH=workflow,
        _load=lambda *_args: pure,
        _selected_targets=selected_target_projection,
    )

    class Engine:
        def validate_frozen_fit(self, *_args: Any, **_kwargs: Any) -> None:
            events.append("validate")

        def evaluate_dev(self, rows: list[dict[str, Any]], targets: list[dict[str, Any]], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("evaluate")
            assert len(rows) == 30
            assert len(targets) == 30
            if mutate_during_evaluate:
                source.write_bytes(b"drifted-source\n")
            return {"evidence_class": "selected100_amended_dev_comparison_unadmitted", "input_commitments": {"verdict_rows_sha256": "b" * 64, "target_rows_sha256": "c" * 64}}

    engine = Engine()
    sol_rows = _rows(binding)
    sol_result = {
        "provider_calls": 0,
        "full_study_admitted": False,
        "selected_requests": 2300,
        "canonical_verdicts": 17800,
        "endpoint_sol_rows": sol_rows,
        "qualification_failures": [
            {"pass_id": "train-019", "coverage": 0.86, "reason": "coverage_below_0.88"},
            {"pass_id": "train-042", "coverage": 0.8648, "reason": "coverage_below_0.88"},
        ],
        "unknown_exit_commitments": [{"ordinal": 4525, "process_success_proven": False}],
        "accepted_native_thread_ids": ["thread-1"],
    }

    class Grok:
        def replay_selected_successor_dev(self, **_kwargs: Any) -> dict[str, Any]:
            events.append("grok")
            return {"comparison_raw": dev_comparison.read_bytes(), "freeze_raw": dev_freeze.read_bytes(), "freeze": json.loads(dev_freeze.read_bytes())}

        def _capture(self, _pins: Mapping[str, Any]) -> tuple[Any, ...]:
            return ({source: source.read_bytes()}, None, None, None, None, composite, engine, None, None)

    class Sol:
        def replay_collected(self, **_kwargs: Any) -> dict[str, Any]:
            events.append("sol")
            return sol_result

    def load_pinned(path: Path, _expected: str, _label: str) -> Any:
        if path == subject.GROK_ANALYSIS_PATH:
            return Grok()
        if path == subject.SOL_REPLAY_PATH:
            return Sol()
        raise AssertionError(path)

    monkeypatch.setattr(subject, "_load_pinned", load_pinned)
    reader_inputs = {
        "plan_root": tmp_path / "plan",
        "predecessor_path": tmp_path / "predecessor.json",
        "old_suffix_root": tmp_path / "old",
        "recovery_root": tmp_path / "recovery",
        "successor_roots": [],
    }
    scoring_inputs = {
        "scoring_manifest_path": scoring_manifest,
        "expected_scoring_manifest_sha256": digest(scoring_manifest.read_bytes()),
        "v5_runtime_manifest_path": scoring_manifest,
        "v5_runtime_package_root": package_root,
    }
    source_pins = {"analysis": "0" * 64, "selected_engine": "1" * 64, "workflow": digest(workflow.read_bytes())}
    grok_kwargs = {
        "reader_inputs": reader_inputs,
        "public_inputs_path": PUBLIC,
        "expected_public_inputs_sha256": subject.PUBLIC_INPUTS_SHA256,
        "dev_targets_path": DEV_TARGETS,
        "fit_path": fit,
        "train_freeze_path": train_freeze,
        "dev_comparison_path": dev_comparison,
        "dev_freeze_path": dev_freeze,
        "expected_fit_sha256": digest(fit.read_bytes()),
        "expected_train_freeze_sha256": digest(train_freeze.read_bytes()),
        "expected_dev_comparison_sha256": digest(dev_comparison.read_bytes()),
        "expected_dev_freeze_sha256": digest(dev_freeze.read_bytes()),
        "source_pins": source_pins,
        "scoring_inputs": scoring_inputs,
    }
    sol_kwargs = {
        "campaign_root": SOL_ROOT,
        "expected_campaign_manifest_sha256": subject.SOL_CAMPAIGN_MANIFEST_SHA256,
        "expected_collection_result_sha256": subject.SOL_COLLECTION_RESULT_SHA256,
        "expected_composer_sha256": subject.SOL_REPLAY_SOURCE_SHA256,
    }
    return subject, grok_kwargs, sol_kwargs, events, sol_result


def output_path(tmp_path: Path) -> Path:
    return tmp_path.parent / f"{tmp_path.name}-selected-sol-output"


def test_stage_order_and_no_sol_fit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, grok_kwargs, sol_kwargs, events, _ = fixture(tmp_path, monkeypatch)
    result = subject.validate_selected_successor_sol(
        grok_replay_kwargs=grok_kwargs,
        sol_replay_kwargs=sol_kwargs,
        sol_replay_receipt_path=RECEIPT,
        output_root=output_path(tmp_path),
    )
    assert events == ["grok", "sol", "validate", "evaluate"]
    assert result["freeze"]["full_study_admitted"] is False
    assert (output_path(tmp_path) / "selected100-sol-validation-freeze-v1.json").is_file()


def test_preserves_selected_binding_failures_and_unknown_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, grok_kwargs, sol_kwargs, _events, sol_result = fixture(tmp_path, monkeypatch)
    result = subject.validate_selected_successor_sol(
        grok_replay_kwargs=grok_kwargs,
        sol_replay_kwargs=sol_kwargs,
        sol_replay_receipt_path=RECEIPT,
        output_root=output_path(tmp_path),
    )
    freeze = result["freeze"]
    assert freeze["sol_collection"]["qualification_failures"] == sol_result["qualification_failures"]
    assert freeze["sol_collection"]["unknown_exit_commitments"] == sol_result["unknown_exit_commitments"]
    assert freeze["grok_selection"]["engine_binding"] == json.loads(grok_kwargs["train_freeze_path"].read_bytes())["engine_binding"]


def test_mismatched_frozen_inputs_stop_before_sol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, grok_kwargs, sol_kwargs, events, _ = fixture(tmp_path, monkeypatch)
    mismatched = json.loads(grok_kwargs["dev_freeze_path"].read_bytes())
    mismatched["engine_binding"]["DEV"] = ["other"] * 30
    grok_kwargs["dev_freeze_path"].write_bytes(canonical(mismatched))
    grok_kwargs["expected_dev_freeze_sha256"] = digest(grok_kwargs["dev_freeze_path"].read_bytes())
    with pytest.raises(ValueError, match="binding"):
        subject.validate_selected_successor_sol(
            grok_replay_kwargs=grok_kwargs,
            sol_replay_kwargs=sol_kwargs,
            sol_replay_receipt_path=RECEIPT,
            output_root=output_path(tmp_path),
        )
    assert events == ["grok"]


def test_dev_coverage_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, grok_kwargs, sol_kwargs, _events, sol_result = fixture(tmp_path, monkeypatch)
    sol_result["endpoint_sol_rows"][70]["coverage"] = 0.5
    with pytest.raises(ValueError, match="coverage failure"):
        subject.validate_selected_successor_sol(
            grok_replay_kwargs=grok_kwargs,
            sol_replay_kwargs=sol_kwargs,
            sol_replay_receipt_path=RECEIPT,
            output_root=output_path(tmp_path),
        )


def test_output_must_be_fresh_and_external(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, grok_kwargs, sol_kwargs, _events, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="overlaps protected"):
        subject.validate_selected_successor_sol(
            grok_replay_kwargs=grok_kwargs,
            sol_replay_kwargs=sol_kwargs,
            sol_replay_receipt_path=RECEIPT,
            output_root=SOL_ROOT / "_new-validation-output",
        )
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="fresh"):
        subject.validate_selected_successor_sol(
            grok_replay_kwargs=grok_kwargs,
            sol_replay_kwargs=sol_kwargs,
            sol_replay_receipt_path=RECEIPT,
            output_root=existing,
        )


def test_captured_input_drift_publishes_no_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, grok_kwargs, sol_kwargs, _events, _ = fixture(tmp_path, monkeypatch, mutate_during_evaluate=True)
    output = output_path(tmp_path)
    with pytest.raises(ValueError, match="before publication"):
        subject.validate_selected_successor_sol(
            grok_replay_kwargs=grok_kwargs,
            sol_replay_kwargs=sol_kwargs,
            sol_replay_receipt_path=RECEIPT,
            output_root=output,
        )
    assert not output.exists()
