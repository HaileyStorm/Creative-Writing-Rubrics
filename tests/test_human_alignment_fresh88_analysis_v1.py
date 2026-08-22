from __future__ import annotations

import importlib.util
import json
import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-v3-fresh88-analysis-v1"
sys.path.insert(0, str(PACKAGE))
spec = importlib.util.spec_from_file_location("fresh88_analysis_v1", PACKAGE / "analyze.py")
assert spec and spec.loader
analysis = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = analysis
spec.loader.exec_module(analysis)


def _plan() -> dict:
    return {
        "cells": [
            {"item_id": "hanna-1", "origin": "fresh_full_successor", "ordinal": 1, "run_dir": "runs/hanna-1"},
            {"item_id": "hanna-2", "origin": "fresh_full_successor", "ordinal": 2, "run_dir": "runs/hanna-2"},
        ]
    }


def _verified() -> list[dict]:
    return [
        {"item_id": "hanna-1", "metrics": {"score": 10.0, "confidence": {"status": "UNAVAILABLE"}, "coverage": {"status": "UNAVAILABLE"}, "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}, "result": {"run_sha256": "a" * 64, "sessions": [{"session_id_sha256": "b" * 64}]}},
        {"item_id": "hanna-2", "metrics": {"score": 20.0, "confidence": {"status": "UNAVAILABLE"}, "coverage": {"status": "UNAVAILABLE"}, "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}, "result": {"run_sha256": "c" * 64, "sessions": [{"session_id_sha256": "d" * 64}]}},
    ]


def _bound(plan: dict, verified: list[dict]) -> dict:
    records = []
    for cell, row in zip(plan["cells"], verified):
        records.append({"item_id": cell["item_id"], "origin": cell["origin"], "ordinal": cell["ordinal"], "run_dir": cell["run_dir"], "run_sha256": row["result"]["run_sha256"], "verifier": row["result"], "metrics": row["metrics"]})
    receipt = {"format_version": 1, "study_id": analysis.CONTRACT["predecessor"]["study_id"], "execution_contract_sha256": analysis.CONTRACT["predecessor"]["execution_contract_sha256"], "purpose": "pre_execution_raw_verifier_binding"}
    core = {"format_version": 1, "study_id": analysis.CONTRACT["predecessor"]["study_id"], "execution_contract_sha256": receipt["execution_contract_sha256"], "execution_receipt_sha256": analysis.CONTRACT["predecessor"]["execution_receipt_sha256"], "records": records, "session_count": 2}
    matrix = {**core, "matrix_sha256": analysis.sha256_canonical(core)}
    diagnostics = {"score": {"mean": 15.0}, "confidence": {"status": "DERIVED_FROM_VERIFIED_OUTPUTS"}, "order": {"method": "scheduled_ordinal_halves_v1", "records": 88}, "repeatability": {"status": "UNAVAILABLE", "reason": "one_verified_development_pass"}, "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}
    gate = {"format_version": 1, "study_id": analysis.CONTRACT["predecessor"]["study_id"], "phase": "semantic_development_gate", "development_mode": "fresh_88", "matrix_sha256": matrix["matrix_sha256"], "execution_receipt_sha256": matrix["execution_receipt_sha256"], "diagnostics": diagnostics, "next_phase": "repeatability"}
    return {"receipt": receipt, "matrix": matrix, "gate": gate}


def test_contract_freezes_analysis_only_public_output_shape() -> None:
    assert analysis.CONTRACT["analysis_only"] is True
    assert analysis.CONTRACT["outputs"] == ["summary.json", "items.jsonl", "manifest.json"]
    assert analysis.CONTRACT["predecessor"]["study_id"] == "hbq-human-alignment-v3-successor-v1"


def test_matrix_and_gate_reconstruct_and_reject_session_reuse() -> None:
    plan, verified = _plan(), _verified()
    matrix = analysis._verify_matrix_gate(plan, _bound(plan, verified), verified)
    assert matrix["matrix_sha256"] == _bound(plan, verified)["matrix"]["matrix_sha256"]
    duplicate = _verified()
    duplicate[1]["result"]["sessions"][0]["session_id_sha256"] = duplicate[0]["result"]["sessions"][0]["session_id_sha256"]
    with pytest.raises(ValueError, match="globally unique"):
        analysis._verify_matrix_gate(plan, _bound(plan, duplicate), duplicate)


def test_matrix_and_gate_reject_tampered_sealed_gate() -> None:
    plan, verified = _plan(), _verified()
    bound = _bound(plan, verified)
    bound["gate"]["next_phase"] = "forged"
    with pytest.raises(ValueError, match="semantic development gate"):
        analysis._verify_matrix_gate(plan, bound, verified)


def test_authority_execution_order_rejects_reordered_cells() -> None:
    frozen = {"fresh_complement": {"scheduled_item_ids": ["hanna-1", "hanna-2"]}}
    plan = _plan()
    assert analysis._assert_scheduled_cell_order(frozen, plan) == ["hanna-1", "hanna-2"]
    plan["cells"].reverse()
    with pytest.raises(ValueError, match="scheduled order"):
        analysis._assert_scheduled_cell_order(frozen, plan)


def test_public_output_is_atomic_and_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "output"
    analysis.atomic_output_directory(output, {"summary.json": "{}\n", "items.jsonl": "", "manifest.json": "{}\n"})
    assert sorted(path.name for path in output.iterdir()) == ["items.jsonl", "manifest.json", "summary.json"]
    with pytest.raises(ValueError, match="Refusing"):
        analysis.atomic_output_directory(output, {"summary.json": "{}\n"})


def test_output_must_be_disjoint_from_private_roots(tmp_path: Path) -> None:
    private = tmp_path / "private"; private.mkdir()
    with pytest.raises(ValueError, match="disjoint"):
        analysis.ensure_output_disjoint(private / "output", [private])
    with pytest.raises(ValueError, match="disjoint"):
        analysis.ensure_output_disjoint(tmp_path, [private])


def test_public_safety_rejects_private_story_or_provider_text(tmp_path: Path) -> None:
    class Item:
        story = "private prose"; prompt = "private prompt"
    class Metrics:
        @staticmethod
        def privacy_forbidden_strings(_: Path) -> list[str]: return ["worker-secret"]
    selection = [{"item_id": "hanna-1"}]
    with pytest.raises(ValueError, match="would disclose"):
        analysis._public_safe({"summary.json": "private prose"}, tmp_path, Metrics(), [tmp_path / "evidence"], selection, {"hanna-1": Item()})
    with pytest.raises(ValueError, match="would disclose"):
        analysis._public_safe({"summary.json": "provider"}, tmp_path, Metrics(), [tmp_path / "evidence"], selection, {"hanna-1": Item()})


def test_real_fresh88_bindings_optionally_load() -> None:
    roots = [
        Path("C:/Users/Haile/Documents/cwr-hanna-fresh88-sol-v1-20260821-w4"),
        Path("C:/Users/Haile/Documents/cwr-hanna-successor-fresh88-freeze-v4"),
        Path("C:/Users/Haile/Documents/cwr-hanna-fresh88-sol-v1-20260821-w4-repair1-artifacts"),
        Path("C:/Users/Haile/Documents/Creative-Writing-Rubrics-fresh88-parent-runtime-f3aed43"),
    ]
    if not all(path.is_dir() for path in roots):
        pytest.skip("requires the explicitly mounted Fresh88 authority, evidence, and historical runtime roots")
    _, _, plan, _ = analysis._load_inputs(*roots)
    assert plan["study_id"] == analysis.CONTRACT["predecessor"]["study_id"]
    assert len(plan["cells"]) == 88


def test_analyze_integration_uses_frozen_dataset_names_and_utf8_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Item:
        def __init__(self, item_id: str, model: str) -> None:
            self.item_id, self.model = item_id, model
            self.story, self.prompt = f"story {item_id}", f"prompt {item_id}"
            self.story_sha256 = hashlib.sha256(self.story.encode()).hexdigest()
            self.prompt_sha256 = hashlib.sha256(self.prompt.encode()).hexdigest()
            self.human_means = {name: 3.0 for name in FakeMetrics.RATING_DIMENSIONS}
            self.human_overall = 3.0
            self.ratings = {name: (3, 3, 3) for name in FakeMetrics.RATING_DIMENSIONS}
            self.story_id = item_id.removeprefix("hanna-")

    class FakeMetrics:
        RATING_DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
        @staticmethod
        def fetch_or_verify_dataset(_: Path) -> dict:
            return {analysis.CONTRACT["dataset"]["csv_name"]: {"sha256": analysis.CONTRACT["dataset"]["csv_sha256"], "bytes": 101}, analysis.CONTRACT["dataset"]["license_name"]: {"sha256": analysis.CONTRACT["dataset"]["license_sha256"], "bytes": 7}}
        @staticmethod
        def mapping_sets() -> dict:
            return {name: [f"question.{index}"] for index, name in enumerate(FakeMetrics.RATING_DIMENSIONS)}
        @staticmethod
        def load_hanna_items(_: Path) -> list[Item]: return items
        @staticmethod
        def record_for(item: Item, selected: dict, verdicts: list[dict], score: dict, source: str, prompt: str, mappings: dict) -> dict:
            assert verdicts[0]["rationale"] == "replacement: \ufffd"
            assert source == item.story and prompt == item.prompt
            return {"item_id": item.item_id, "story_id": item.story_id, "source_model": item.model, "quartile": selected["quartile"], "prompt_group_id": selected["prompt_group_id"], "story_sha256": item.story_sha256, "prompt_sha256": item.prompt_sha256, "human_ratings": item.ratings, "human_means": item.human_means, "human_overall": item.human_overall, "hbq_full_observed_score": score["final_score"]["observed"], "hbq_mapping": {name: {"score": 0.5, "coverage": 1.0, "unresolved": 0, "not_applicable": 0, "question_count": 1} for name in mappings}, "evidence": {"total": 1}}
        @staticmethod
        def dimension_analysis(rows: list[dict], dimension: str, seed: int) -> dict: return {"item_count": len(rows), "dimension": dimension, "seed": seed}
        @staticmethod
        def macro_cluster_bootstrap(rows: list[dict], seed: int) -> dict: return {"item_count": len(rows), "seed": seed, "draws": 1000, "cluster": "prompt_group_id"}
        @staticmethod
        def ordinal_agreement(rows: list[Item]) -> dict: return {name: {"item_count": len(rows)} for name in FakeMetrics.RATING_DIMENSIONS}
        @staticmethod
        def source_model_strata(rows: list[dict]) -> dict: return {"all": {"item_count": len(rows)}}
        @staticmethod
        def privacy_forbidden_strings(_: Path) -> list[str]: return []

    runtime, artifacts, work, authority, data, output = (tmp_path / name for name in ("runtime", "artifacts", "work", "authority", "data", "output"))
    (runtime / "src" / "hbqrs").mkdir(parents=True)
    (runtime / "src" / "hbqrs" / "run_verify.py").write_text("import hashlib\ndef verify_binary_run(run, frozen):\n item=frozen['execution']['artifact_id']; return {'run_sha256': hashlib.sha256(item.encode()).hexdigest(), 'sessions': [{'session_id_sha256': hashlib.sha256(('session:'+item).encode()).hexdigest()}]}\n", encoding="utf-8")
    artifacts.joinpath("runs").mkdir(parents=True)
    work.mkdir(); authority.mkdir(); data.mkdir()
    items = [Item(f"hanna-{number}", "Human" if number <= 8 else "Model") for number in range(1, 89)]
    selection, cells = [], []
    for ordinal, item in enumerate(items, 1):
        selection.append({"item_id": item.item_id, "model": item.model, "quartile": 1, "prompt_group_id": f"group-{ordinal}", "story_sha256": item.story_sha256, "prompt_sha256": item.prompt_sha256})
        run = artifacts / "runs" / item.item_id; run.mkdir()
        (run / "score.v2.json").write_text(json.dumps({"final_score": {"observed": float(ordinal), "coverage": {"rate": 1.0}}, "confidence": {"mean": 0.8}}), encoding="utf-8")
        (run / "verdicts.jsonl").write_text(json.dumps({"question_id": "question.0", "verdict": "YES", "rationale": "replacement: \ufffd"}, ensure_ascii=False) + "\n", encoding="utf-8")
        cells.append({"item_id": item.item_id, "origin": "fresh_full_successor", "ordinal": ordinal, "run_dir": f"runs/{item.item_id}", "artifact": {}, "contexts": [], "task_contract": {}, "external_input": {"source.md": {"sha256": item.story_sha256}, "prompt.md": {"sha256": item.prompt_sha256}}})
    frozen = {"selection": {"development": selection}, "fresh_complement": {"item_ids": [item.item_id for item in sorted(items, key=lambda item: item.item_id)], "scheduled_item_ids": [item.item_id for item in items]}}
    plan = {"base_frozen": {"execution": {}}, "cells": cells}
    gate_path = work / "semantic-development-gate.json"; gate_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(analysis, "_load_inputs", lambda *_: (frozen, {"runtime_source_manifest_sha256": analysis.CONTRACT["predecessor"]["runtime_source_manifest_sha256"]}, plan, {"receipt": {}, "matrix": {}, "gate": {}}))
    monkeypatch.setattr(analysis, "_load_historical_metrics", lambda _: FakeMetrics())
    monkeypatch.setattr(analysis, "_analysis_bindings", lambda _: (analysis.CONTRACT["analysis"], "e" * 64))
    monkeypatch.setattr(analysis, "_verify_matrix_gate", lambda *_: {"matrix_sha256": "m" * 64})
    analysis.analyze(data, work, authority, artifacts, runtime, output)
    published = [json.loads(line) for line in (output / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(published) == 88 and published[0]["item_id"] == "hanna-1" and published[-1]["item_id"] == "hanna-9"
    assert published[0]["execution_ordinal"] == 1 and "\ufffd" not in (output / "items.jsonl").read_text(encoding="utf-8")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["analysis"] == analysis.CONTRACT["analysis"]
    assert summary["evidence_binding"]["analysis_source_manifest_sha256"] == "e" * 64
