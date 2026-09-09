"""Synthetic composition tests for the v5 composite TRAIN/DEV adapter."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_composite_analysis_v5.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def composer_canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load():
    spec = importlib.util.spec_from_file_location("dryad_composite_analysis_v5_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = load()
    train_ids = {f"train-{index:03d}" for index in range(176)}
    dev_ids = {f"dev-{index:03d}" for index in range(60)}
    public = tmp_path / "public.json"
    public_raw = canonical({"TRAIN": [{"opaque_story_id": item} for item in sorted(train_ids)],
                            "DEV": [{"opaque_story_id": item} for item in sorted(dev_ids)]})
    public.write_bytes(public_raw)
    train_target = tmp_path / "train.json"
    dev_target = tmp_path / "dev.json"
    train_target.write_bytes(canonical([{"opaque_story_id": item, "partition": "TRAIN"} for item in sorted(train_ids)]))
    dev_target.write_bytes(canonical([{"opaque_story_id": item, "partition": "DEV"} for item in sorted(dev_ids)]))
    calls: list[str] = []
    state = {"complete": True, "fit_drift": False, "parity": "parity", "compare_error": None}
    rows = [{"opaque_story_id": item, "verdicts": [{"question_id": "q", "verdict": "YES"}]}
            for item in sorted(train_ids | dev_ids)]

    def admit_composite_baseline(**kwargs):
        calls.append("admit")
        if not state["complete"]:
            raise ValueError("incomplete composite admission")
        record = {"composer_source_sha256": kwargs["expected_composer_sha256"],
                  "counts": {"passes": 236, "logical": 5428, "native": 5427, "recovered": 1},
                  "recovered_ordinals": [70], "endpoint_grok_rows": rows, "provider_calls_made": 0,
                  "execution_authority": False, "promotion_authority": False, "confirmation_authority": False}
        return {"composite_admission": record, "composite_admission_sha256": digest(composer_canonical(record)),
                "provider_calls_made": 0, "execution_authority": False}

    def project(admission, partitions):
        found = {row["opaque_story_id"] for row in admission["endpoint_grok_rows"]}
        assert found == partitions["TRAIN"] | partitions["DEV"]
        projected = {name: sorted(({"opaque_story_id": row["opaque_story_id"], "verdicts": row["verdicts"]}
                                   for row in admission["endpoint_grok_rows"] if row["opaque_story_id"] in ids),
                                  key=lambda row: row["opaque_story_id"])
                     for name, ids in partitions.items()}
        return projected, {"projected": "synthetic"}

    def targets(path, _expected, partition, ids):
        calls.append("targets-" + partition)
        values = json.loads(Path(path).read_bytes())
        assert {item["opaque_story_id"] for item in values} == ids
        return Path(path), Path(path).read_bytes(), values

    def commitments(inner, verdicts, targets, _target_hash):
        expected = {"verdict_rows_sha256": digest(subject._canonical(verdicts)),
                    "target_rows_sha256": digest(subject._canonical(sorted(targets, key=lambda row: row["opaque_story_id"]))) }
        assert inner["input_commitments"] == expected

    pure = SimpleNamespace(_project_rows=project, _targets=targets, _inner_commitments=commitments,
                           TRAIN_TARGETS_SHA256="a" * 64, DEV_TARGETS_SHA256="b" * 64)

    def fit(verdicts, targets, **kwargs):
        calls.append("fit")
        assert len(verdicts) == len(targets) == 176 and kwargs["expected_optimizer_sha256"] == "3" * 64
        payload = {"verdict_rows_sha256": digest(subject._canonical(verdicts)),
                   "target_rows_sha256": digest(subject._canonical(sorted(targets, key=lambda row: row["opaque_story_id"]))) }
        if state["fit_drift"]:
            payload["verdict_rows_sha256"] = "0" * 64
        return {"evidence_class": "baseline_source_verified_fit_unadmitted", "input_commitments": payload,
                "trial_count": 128, "trial_records": [], "winner": {}}

    def compare(verdicts, targets, fit_raw, **kwargs):
        calls.append("compare")
        assert len(verdicts) == len(targets) == 60 and json.loads(fit_raw)["trial_count"] == 128
        if state["compare_error"]:
            raise state["compare_error"]
        return {"evidence_class": "baseline_source_verified_dev_comparison_unadmitted",
                "input_commitments": {"verdict_rows_sha256": digest(subject._canonical(verdicts)),
                                      "target_rows_sha256": digest(subject._canonical(sorted(targets, key=lambda row: row["opaque_story_id"])))}}

    def capture(**kwargs):
        engine = SimpleNamespace(fit_train=fit) if kwargs["engine_label"] == "Optimizer" else SimpleNamespace(evaluate_dev=compare)
        return {}, SimpleNamespace(admit_composite_baseline=admit_composite_baseline, _canonical=composer_canonical), pure, engine, SimpleNamespace(), SimpleNamespace()

    monkeypatch.setattr(subject, "_capture", capture)
    monkeypatch.setattr(subject, "_runtime_parity", lambda *_args, **_kwargs: ({"commitment_sha256": state["parity"], "parity": {}}, {}))
    return SimpleNamespace(subject=subject, tmp_path=tmp_path, public=public, train_target=train_target,
                           dev_target=dev_target, calls=calls, state=state)


def kwargs(case, *, comparison: bool = False) -> dict[str, object]:
    values: dict[str, object] = {
        "expected_plan_sha256": "1" * 64, "expected_public_inputs_sha256": digest(case.public.read_bytes()),
        "expected_predecessor_sha256": "2" * 64, "expected_suffix_epoch_sha256": "3" * 64,
        "expected_suffix_source_sha256": "4" * 64, "expected_analysis_sha256": digest(SOURCE.read_bytes()),
        "expected_composer_sha256": "5" * 64, "expected_workflow_sha256": "6" * 64,
        "expected_scoring_runtime_loader_sha256": "8" * 64,
        "expected_v5_runtime_loader_sha256": "9" * 64, "expected_scoring_manifest_sha256": "a" * 64,
        "expected_v5_runtime_manifest_sha256": "b" * 64, "expected_v5_runtime_package_manifest_sha256": "c" * 64,
        "approved_v4_routes": {}, "approved_v5_routes": {},
    }
    values["expected_comparison_sha256" if comparison else "expected_optimizer_sha256"] = "d" * 64 if comparison else "3" * 64
    return values


def fit(case, output: Path | None = None):
    return case.subject.fit_composite_train(
        case.tmp_path / "plan", case.public, case.tmp_path / "predecessor.json", case.tmp_path / "suffix",
        case.tmp_path / "v1.json", case.tmp_path / "v5.json", case.tmp_path / "package", case.train_target,
        output or case.tmp_path.parent / (case.tmp_path.name + "-train"), **kwargs(case),
    )


def compare(case, train: Path, output: Path | None = None, **override):
    values = kwargs(case, comparison=True)
    values.update(override)
    fit_path = train / "fit-unadmitted.json"
    freeze_path = train / "train-composite-freeze.json"
    expected_fit = values.pop("expected_fit_sha256", digest(fit_path.read_bytes()))
    expected_freeze = values.pop("expected_train_freeze_sha256", digest(freeze_path.read_bytes()))
    return case.subject.compare_composite_dev(
        case.tmp_path / "plan", case.public, case.tmp_path / "predecessor.json", case.tmp_path / "suffix",
        case.tmp_path / "v1.json", case.tmp_path / "v5.json", case.tmp_path / "package", case.dev_target,
        fit_path, freeze_path, output or case.tmp_path.parent / (case.tmp_path.name + "-dev"),
        expected_fit_sha256=expected_fit, expected_train_freeze_sha256=expected_freeze, **values,
    )


def test_incomplete_composite_admission_reads_no_targets(case) -> None:
    case.state["complete"] = False
    with pytest.raises(ValueError, match="incomplete composite admission"):
        fit(case)
    assert case.calls == ["admit"]


def test_train_projects_complete_composite_before_targets_and_binds_provenance(case) -> None:
    result = fit(case)
    freeze = result["freeze"]
    assert case.calls == ["admit", "targets-TRAIN", "fit"]
    assert freeze["admission_binding"]["canonical_composite_admission_sha256"] == digest(
        composer_canonical(freeze["admission"])
    )
    assert set(freeze["admission_binding"]["projected_rows_sha256"]) == {"TRAIN", "DEV"}
    assert freeze["scoring"]["commitment_sha256"] == "parity"
    assert set(result["artifacts"]) == {"fit-unadmitted.json", "train-composite-freeze.json"}


def test_train_rejects_inner_commitment_drift_without_output(case) -> None:
    case.state["fit_drift"] = True
    output = case.tmp_path.parent / (case.tmp_path.name + "-drift")
    with pytest.raises(AssertionError):
        fit(case, output)
    assert case.calls == ["admit", "targets-TRAIN", "fit"]
    assert not output.exists()


def test_dev_rechecks_admission_then_exact_train_bytes_before_dev_targets(case) -> None:
    train = case.tmp_path.parent / (case.tmp_path.name + "-train")
    fit(case, train)
    raw = (train / "train-composite-freeze.json").read_bytes()
    (train / "train-composite-freeze.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="Composite TRAIN freeze hash drift"):
        compare(case, train, expected_train_freeze_sha256=digest(raw))
    assert case.calls == ["admit", "targets-TRAIN", "fit", "admit"]


def test_dev_rejects_fit_byte_drift_before_reading_dev_targets(case) -> None:
    train = case.tmp_path.parent / (case.tmp_path.name + "-train")
    fit(case, train)
    raw = (train / "fit-unadmitted.json").read_bytes()
    (train / "fit-unadmitted.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="Frozen composite TRAIN fit hash drift"):
        compare(case, train, expected_fit_sha256=digest(raw))
    assert case.calls == ["admit", "targets-TRAIN", "fit", "admit"]


def test_dev_freeze_is_deterministically_bound_and_selects_only_after_compare(case, monkeypatch) -> None:
    train = case.tmp_path.parent / (case.tmp_path.name + "-train")
    fit(case, train)
    monkeypatch.setattr(case.subject, "datetime", SimpleNamespace(
        now=lambda zone: __import__("datetime").datetime(2026, 9, 9, 6, 1, 2, tzinfo=zone),
    ))
    result = compare(case, train)
    assert case.calls == ["admit", "targets-TRAIN", "fit", "admit", "targets-DEV", "compare"]
    assert result["freeze"]["selection_frozen_at"] == "2026-09-09T06:01:02Z"
    assert result["freeze"]["train"] == {"fit_sha256": digest((train / "fit-unadmitted.json").read_bytes()),
                                         "freeze_sha256": digest((train / "train-composite-freeze.json").read_bytes())}
    dev_freeze = case.tmp_path.parent / (case.tmp_path.name + "-dev") / "dev-composite-freeze.json"
    assert result["artifacts"]["dev-composite-freeze.json"] == digest(dev_freeze.read_bytes())
    assert dev_freeze.read_bytes() == canonical(json.loads(dev_freeze.read_bytes()))


def test_replay_reconstructs_existing_dev_bytes_without_writing_or_new_selection(case) -> None:
    train = case.tmp_path.parent / (case.tmp_path.name + "-train")
    fit(case, train)
    produced = case.tmp_path.parent / (case.tmp_path.name + "-dev")
    compare(case, train, produced)
    comparison = produced / "dev-comparison-unadmitted.json"
    freeze = produced / "dev-composite-freeze.json"
    values = kwargs(case, comparison=True)
    replay = case.subject.replay_composite_dev(
        case.tmp_path / "plan", case.public, case.tmp_path / "predecessor.json", case.tmp_path / "suffix",
        case.tmp_path / "v1.json", case.tmp_path / "v5.json", case.tmp_path / "package", case.dev_target,
        train / "fit-unadmitted.json", train / "train-composite-freeze.json", comparison, freeze,
        expected_fit_sha256=digest((train / "fit-unadmitted.json").read_bytes()),
        expected_train_freeze_sha256=digest((train / "train-composite-freeze.json").read_bytes()),
        expected_dev_comparison_sha256=digest(comparison.read_bytes()), expected_dev_freeze_sha256=digest(freeze.read_bytes()),
        **values,
    )
    assert replay["comparison_raw"] == comparison.read_bytes()
    assert replay["freeze_raw"] == freeze.read_bytes()
    assert case.calls == ["admit", "targets-TRAIN", "fit", "admit", "targets-DEV", "compare",
                          "admit", "targets-DEV", "compare"]


class _ParityCore:
    def score_bundle(self, modules, bundle, verdicts, **kwargs):
        return {"modules": modules, "bundle": bundle, "verdicts": verdicts, "contract": kwargs.get("task_contract")}


class _ParityWeights:
    def materialize_weight_profile(self, modules, bundle, profile):
        return modules, {**bundle, "profile": profile}, {"synthetic": True}


def parity_runtime(marker: str = "same"):
    questions = [{"question": {"id": f"q-{number:03d}"}} for number in range(178)]
    sources = {str(ROOT / name): "f" * 64 for name in ("src/hbqrs/core.py", "src/hbqrs/weights.py", "src/hbqrs/paths.py", "registry/all_modules.json", "bundles/all_bundles.json")}
    core = _ParityCore()
    if marker != "same":
        class DriftCore(_ParityCore):
            def score_bundle(self, modules, bundle, verdicts, **kwargs):
                value = super().score_bundle(modules, bundle, verdicts, **kwargs)
                if bundle.get("profile"):
                    value["drift"] = marker
                return value
        core = DriftCore()
    return SimpleNamespace(modules=[{"module_id": "m"}], bundle={"bundle_id": "prose.short_story", "domains": [{"domain_id": "task", "points": 100}]},
                           compiled={"bundle": "compiled"}, questions=questions, core=core, weights=_ParityWeights(),
                           provenance={"source_sha256": sources}, verify=lambda: None)


def test_scoring_parity_covers_four_state_hardgate_na_unknown_and_weights() -> None:
    subject = load()
    parity = subject._scoring_parity(parity_runtime(), parity_runtime())
    assert set(parity["case_score_sha256"]) == {"four_state", "not_applicable", "unknown", "weighted",
                                                   "hard_gate_yes", "hard_gate_no", "hard_gate_unknown"}
    assert parity["before_after_verified"] is True
    with pytest.raises(ValueError, match="weighted"):
        subject._scoring_parity(parity_runtime(), parity_runtime("drift"))


def test_scoring_parity_cases_execute_against_actual_hbq_scoring() -> None:
    subject = load()
    sys.path.insert(0, str(ROOT / "src"))
    from hbqrs import core, weights

    modules = core.load_modules(ROOT / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(ROOT / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    closure = ("src/hbqrs/core.py", "src/hbqrs/weights.py", "src/hbqrs/paths.py", "registry/all_modules.json", "bundles/all_bundles.json")
    sources = {str(ROOT / path): digest((ROOT / path).read_bytes()) for path in closure}
    runtime = SimpleNamespace(modules=modules, bundle=bundle, compiled=compiled, questions=questions,
                              core=core, weights=weights, provenance={"source_sha256": sources}, verify=lambda: None)
    parity = subject._scoring_parity(runtime, runtime)
    assert parity["case_score_sha256"]["hard_gate_yes"] != parity["case_score_sha256"]["hard_gate_no"]
    assert parity["case_score_sha256"]["hard_gate_no"] != parity["case_score_sha256"]["hard_gate_unknown"]
