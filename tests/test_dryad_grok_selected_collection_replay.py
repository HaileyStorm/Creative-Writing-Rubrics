from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "baseline_grok_selected_collection_replay.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("dryad_grok_selected_collection_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identity(number: int) -> dict[str, str]:
    return {"request_id_hash": sha(f"request-{number}".encode()), "session_id_hash": sha(f"session-{number}".encode())}


def test_source_boundaries_keep_old_unknown_88_out_of_the_collection() -> None:
    value = load()
    expected = {
        80: "original_v4_prefix", 81: "old_v5", 87: "old_v5", 88: "recovery", 89: "old_v5", 91: "old_v5",
        92: "recovery", 1610: "recovery", 4049: "recovery",
    }
    assert {ordinal: value.source_for_ordinal(ordinal) for ordinal in expected} == expected
    assert 88 not in value.OLD_V5_ORDINALS
    for ordinal in (0, 1611, 4048, 4739):
        with pytest.raises(ValueError, match="outside"):
            value.source_for_ordinal(ordinal)


def test_identity_and_verdict_guards_reject_missing_or_duplicate_inputs() -> None:
    value = load()
    with pytest.raises(ValueError, match="identity"):
        value._unique([{"request_id_hash": "a" * 64}])
    assert value._identity({**identity(2), "observed_turns": 1}, "v4") == identity(2)
    with pytest.raises(ValueError, match="identity"):
        value._identity({**identity(3), "observed_turns": 0}, "v4")
    with pytest.raises(ValueError, match="duplicate"):
        value._unique([identity(1), identity(1)])
    questions = [f"q-{item}" for item in range(value.QUESTION_COUNT)]
    with pytest.raises(ValueError, match="verdict count"):
        value._verdicts([], questions, "fixture")
    bad = [{"question_id": question} for question in questions]
    bad[-1]["question_id"] = "wrong"
    with pytest.raises(ValueError, match="criterion order"):
        value._verdicts(bad, questions, "fixture")


def test_low_coverage_is_reported_without_filtering() -> None:
    value = load()
    questions = [f"q-{item}" for item in range(value.QUESTION_COUNT)]
    verdicts = [{"question_id": question, "verdict": "YES"} for question in questions]
    runtime = SimpleNamespace(core=SimpleNamespace(score_bundle=lambda *_args, **_kwargs: {
        "final_score": {"observed": 40}, "coverage": 0.5,
    }), modules={}, bundle={})
    record = {"pass_id": "pass", "partition": "TRAIN", "opaque_story_id": "opaque", "source_sha256": "b" * 64,
              "source_bytes": 1}
    row = value._record(record=record, ordinals=list(range(1, 24)), verdicts=verdicts, runtime=runtime,
                        provenance="fixture", replay_input_commitments={"fixture": "a" * 64})
    assert row["coverage"] == 0.5 and row["verdicts_sha256"] == sha(value._canonical(verdicts))
    assert row["verdict_rows"] == verdicts and row["source"] == {"sha256": "b" * 64, "bytes": 1}


def test_recovery_reader_requires_every_new_ordinal_and_preserves_controller_checks(tmp_path: Path) -> None:
    value = load()
    manifest = {"controller_sha256": sha(value.RECOVERY.read_bytes()), "parent_source": {"sha256": "a" * 64},
                "inner_epoch": {"sha256": "b" * 64}}
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "recovery-manifest.json").write_bytes(raw)
    parent = object()
    recovery = SimpleNamespace(
        _load_parent=lambda _hash: parent,
        _inner=lambda *_args: ({"plan_sha256": "c" * 64}, b"epoch", tmp_path, {}),
        _source_guard=lambda *_args: None,
        _validated_replay_chain=lambda *_args: (set(value.NEW_ORDINALS) - {88}, []),
    )
    with pytest.raises(ValueError, match="require replay"):
        value._load_recovery(tmp_path, recovery, manifest["controller_sha256"], sha(raw))


def test_historical_prefix_schema_smoke_is_optional_when_evidence_is_not_installed() -> None:
    value = load()
    suffix = value._module(value.SUFFIX, value.SUFFIX_SHA256, "actual suffix helper")
    old_root = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-selected100-v5-20260910-r1\epoch")
    if not old_root.is_dir():
        pytest.skip("historical selected100 evidence is not installed")
    epoch_hash = sha((old_root / "suffix-epoch.json").read_bytes())
    epoch, _raw = suffix._load_epoch(old_root, epoch_hash)
    plan_root, old_execution_root, prefix_root, requests = suffix._epoch_integrity(old_root, epoch)
    manifest, review = suffix._old_prefix(old_execution_root=old_execution_root, old_prefix_run_root=prefix_root,
                                          manifest_path=Path(epoch["old_prefix_manifest"]["path"]),
                                          expected_manifest_sha256=epoch["old_prefix_manifest"]["sha256"],
                                          review_path=Path(epoch["old_prefix_review"]["path"]),
                                          expected_review_sha256=epoch["old_prefix_review"]["sha256"])
    assert plan_root.is_dir() and requests[80]["ordinal"] == 80 and requests[92]["ordinal"] == 92
    assert manifest["counts"]["native_contacts"] == 79 and manifest["counts"]["study_recovered_ordinals"] == [70]
    assert review["provider_calls"] == 0
    assert {"root", "epoch_sha256", "epoch", "runtime", "plan_root", "passed", "row", "approved_v5_routes"} <= set(
        inspect.signature(suffix._replay_suffix_terminal).parameters
    )
    assert {"root", "epoch_sha256", "review", "wave_ordinals"} <= set(inspect.signature(suffix._prepare_wave_cell).parameters)


def test_full_synthetic_orchestration_routes_cross_root_collection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    value = load()
    questions = [f"q-{item:03d}" for item in range(value.QUESTION_COUNT)]
    calls: list[tuple[int, Path]] = []
    old_root, new_root, plan_root = tmp_path / "old", tmp_path / "new", tmp_path / "plan"
    old_root.mkdir(); new_root.mkdir(); plan_root.mkdir()

    def source_record(number: int) -> dict[str, Any]:
        return {"pass_id": f"pass-{number:03d}", "partition": "TRAIN" if number < 70 else "DEV",
                "opaque_story_id": f"story-{number:03d}", "source_sha256": sha(f"source-{number}".encode()), "source_bytes": number}

    passes = [source_record(number) for number in range(value.STORY_COUNT)]
    requests: list[dict[str, Any]] = []
    for number, record in enumerate(passes):
        start = number * 23 + 1 if number < 70 else 4049 + (number - 70) * 23
        for batch in range(23):
            requests.append({"ordinal": start + batch, "pass_id": record["pass_id"], "question_ids": questions[batch * 8:(batch + 1) * 8]})
    selected_ordinals = [row["ordinal"] for row in requests]

    runtime = SimpleNamespace(
        core=SimpleNamespace(score_bundle=lambda *_args, **_kwargs: {"final_score": {"observed": 50}, "coverage": 0.5}),
        modules={}, bundle={}, transport_sha256="t" * 64,
    )

    def attempt_path(root: Path, ordinal: int, name: str) -> Path:
        path = root / name
        if not path.exists():
            path.write_bytes(f"{root.name}-{name}".encode())
        return path

    def replay_terminal(*, root: Path, row: Mapping[str, Any], **_kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        ordinal = row["ordinal"]
        calls.append((ordinal, root))
        return ([{"question_id": question, "verdict": "YES"} for question in row["question_ids"]], identity(ordinal))

    suffix = SimpleNamespace(__file__="synthetic-suffix", _runtime_from_epoch=lambda _epoch: runtime,
                             _replay_suffix_terminal=replay_terminal, _attempt_path=attempt_path)
    old_passes = [{"pass_id": record["pass_id"], "run_root": str(old_root / record["pass_id"])} for record in passes[:3]]
    context = SimpleNamespace(
        suffix=suffix, old_runtime=runtime, old_passes=old_passes,
        epoch={"selected_request_ordinals": selected_ordinals, "selected_schedule": {"sha256": "s" * 64},
               "selected_schedule_source": {"sha256": "u" * 64}, "recovered_study_source": {"path": "recovered", "sha256": "r" * 64},
               "old_prefix_run_root": str(old_root / "prefix"), "recovered_study_manifest": {"sha256": "m" * 64},
               "recovery_adoption_sha256": "a" * 64, "recovery_amendment_sha256": "z" * 64},
    )

    def old_admit(_context: Any, *, pass_record: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any]:
        return {"verdicts": [{"question_id": question, "verdict": "YES"} for question in questions],
                "native_identities": [{**identity(ordinal), "observed_turns": 1} for ordinal in range(
                    passes.index(pass_record) * 23 + 1, passes.index(pass_record) * 23 + 24)],
                "run_manifest_sha256": "d" * 64, "checkpoint_head_sha256": "e" * 64}

    class Recovered:
        @staticmethod
        def admit_prefix(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"verdicts": [{"question_id": question, "verdict": "YES"} for question in questions[:88]],
                    "native_identities": [identity(ordinal) for ordinal in range(71, 81)],
                    "run_manifest_sha256": "f" * 64, "checkpoint_head_sha256": "g" * 64,
                    "recovered_manifest_sha256": "m" * 64}

    composite = SimpleNamespace(
        _predecessor=lambda *_args: (b"predecessor", {}), _actual_replay_context=lambda **_kwargs: context,
        _plan=lambda *_args: ({"requests": requests, "passes": passes}, b"plan", passes,
                               {record["pass_id"]: record for record in passes}, questions),
        _actual_old_admit=old_admit, _load_module=lambda *_args: Recovered(),
        _measurement_source=lambda *_args: {"opaque_story_id": "story-003", "story_text": "", "artifact_path": ""},
    )
    recovery = SimpleNamespace()
    modules = {value.COMPOSITE: composite, value.SUFFIX: suffix, value.RECOVERY: recovery}
    monkeypatch.setattr(value, "_module", lambda path, *_args: modules[path])
    monkeypatch.setattr(value, "_load_recovery", lambda *_args: (
        {"inner_epoch": {"sha256": "n" * 64}}, b"manifest", suffix, {"plan_sha256": "p" * 64},
        set(value.NEW_ORDINALS), [identity(ordinal) for ordinal in value.NEW_ORDINALS],
    ))
    result = value.read_selected_collection(
        plan_root=plan_root, predecessor_path=tmp_path / "predecessor", old_suffix_root=old_root, recovery_root=new_root,
        expected_plan_sha256="p" * 64, expected_predecessor_sha256="x" * 64, expected_old_epoch_sha256="o" * 64,
        expected_suffix_source_sha256=value.SUFFIX_SHA256, expected_recovery_controller_sha256=value.RECOVERY_SHA256,
        expected_recovery_manifest_sha256="h" * 64, approved_v4_routes={}, approved_v5_routes={},
    )
    assert result["counts"] == {"stories": 100, "logical_requests": 2300, "native_requests": 2299,
                                "study_recovered_requests": 1, "criterion_verdicts": 17800}
    assert len(result["rows"]) == 100 and result["coverage_failures"] == [row["pass_id"] for row in result["rows"]]
    assert result["full_study_admitted"] is False and result["provider_calls_made"] == 0
    roots = dict(calls)
    assert roots[81] == old_root and roots[88] == new_root and roots[92] == new_root
    assert roots[1610] == new_root and roots[4049] == new_root and roots[4738] == new_root
    assert result["rows"][0]["verdict_rows"][0] == {"question_id": questions[0], "verdict": "YES"}
    assert result["rows"][0]["source"] == {"sha256": passes[0]["source_sha256"], "bytes": 0}
    assert result["input_commitments"]["predecessor_sha256"] == "x" * 64


def test_hash_guard_detects_source_drift_before_reading() -> None:
    value = load()
    with pytest.raises(ValueError, match="drifted"):
        value._read(SOURCE, "0" * 64, "collection source")
