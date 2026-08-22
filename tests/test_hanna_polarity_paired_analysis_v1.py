from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-hanna-polarity-paired-analysis-v1"


def load():
    spec = importlib.util.spec_from_file_location("hanna_polarity_paired_analysis_v1", ROOT / "analyze.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(question_id: str, verdict: str, confidence: float = 0.9) -> dict[str, object]:
    return {"question_id": question_id, "verdict": verdict, "confidence": confidence}


def test_checked_in_aggregate_matches_sealed_report_shape() -> None:
    summary = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "results" / "manifest.json").read_text(encoding="utf-8"))
    rendered = (ROOT / "results" / "summary.json").read_bytes()
    assert summary["reconstruction"] == {"cell_count": 12, "canonical_verdict_count": 1236}
    assert summary["focal_batch1"]["disagreement"] == {
        "any_matched_polarity_disagreement_leaf_count": 7,
        "any_six_observation_instability_leaf_count": 9,
        "focal_leaf_count": 27,
        "matched_pair_disagreement_count": 8,
        "matched_pair_count": 81,
    }
    assert summary["mean_absolute_dimension_error"]["primary_endpoint_aligned"] == pytest.approx({"positive": 0.24444444444444446, "paired": 0.26296296296296295, "negative": 0.2814814814814815})
    assert summary["mean_absolute_dimension_error"]["sensitivity_divide_by_max"] == pytest.approx({"positive": 0.27777777777777773, "paired": 0.2962962962962963, "negative": 0.3148148148148148})
    assert manifest["files"]["summary.json"] == {"bytes": len(rendered), "sha256": hashlib.sha256(rendered).hexdigest()}
    for name in ("analyze.py", "study-contract.json"):
        source = ROOT / name
        assert manifest["analysis"][name] == {"bytes": source.stat().st_size, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    text = (ROOT / "results" / "summary.json").read_text(encoding="utf-8")
    assert "C:\\Users\\" not in text and "You 've been best friends" not in text


def test_bound_rejects_tampered_input(tmp_path: Path) -> None:
    module = load()
    path = tmp_path / "input.json"
    path.write_text("sealed", encoding="utf-8")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert module.bound(path, expected)["sha256"] == expected
    path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Bound input drifted"):
        module.bound(path, expected)


def test_stage_binding_rejects_tampered_raw_evidence(tmp_path: Path) -> None:
    module = load()
    work, private = tmp_path / "work", tmp_path / "private"
    work.mkdir(); private.mkdir()
    plan, evidence, raw = work / "pilot-contract.json", work / "stage1-evidence.json", private / "stage1-raw-evidence.json"
    for path, content in ((plan, "plan"), (evidence, "evidence"), (raw, "raw")):
        path.write_text(content, encoding="utf-8")
    expected = {"plan": hashlib.sha256(plan.read_bytes()).hexdigest(), "evidence": hashlib.sha256(evidence.read_bytes()).hexdigest(), "raw": hashlib.sha256(raw.read_bytes()).hexdigest()}
    assert module.bind_stage("stage1", work, private, expected)["raw"]["sha256"] == expected["raw"]
    raw.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Bound input drifted"):
        module.bind_stage("stage1", work, private, expected)


def test_hanna_normalization_is_zero_to_five_and_parent_bound(tmp_path: Path) -> None:
    module = load()
    story, prompt = "story", "prompt"
    csv_path = tmp_path / "hanna.csv"
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("Story ID", "Story", "Prompt", *dimensions))
        writer.writeheader()
        for value in (1, 3, 5):
            writer.writerow({"Story ID": "225", "Story": story, "Prompt": prompt, **{dimension: value for dimension in dimensions}})
    plan = {"parent": {"parent_cell": {"artifact": {"sha256": hashlib.sha256(story.encode()).hexdigest()}, "contexts": [{"sha256": hashlib.sha256(prompt.encode()).hexdigest()}]}}}
    assert module.hanna_means(csv_path, plan) == {
        "primary_endpoint_aligned": {dimension: 0.5 for dimension in dimensions},
        "sensitivity_divide_by_max": {dimension: 0.6 for dimension in dimensions},
    }
    plan["parent"]["parent_cell"]["artifact"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sealed pilot parent"):
        module.hanna_means(csv_path, plan)


def test_hanna_requires_every_rating_row_to_match_parent_text(tmp_path: Path) -> None:
    module = load()
    csv_path = tmp_path / "hanna.csv"
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("Story ID", "Story", "Prompt", *dimensions))
        writer.writeheader()
        writer.writerow({"Story ID": "225", "Story": "story", "Prompt": "prompt", **{dimension: 3 for dimension in dimensions}})
        writer.writerow({"Story ID": "225", "Story": "different", "Prompt": "prompt", **{dimension: 3 for dimension in dimensions}})
        writer.writerow({"Story ID": "225", "Story": "story", "Prompt": "prompt", **{dimension: 3 for dimension in dimensions}})
    plan = {"parent": {"parent_cell": {"artifact": {"sha256": hashlib.sha256(b"story").hexdigest()}, "contexts": [{"sha256": hashlib.sha256(b"prompt").hexdigest()}]}}}
    with pytest.raises(ValueError, match="sealed pilot parent"):
        module.hanna_means(csv_path, plan)


def test_hanna_rejects_out_of_range_rating(tmp_path: Path) -> None:
    module = load()
    csv_path = tmp_path / "hanna.csv"
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("Story ID", "Story", "Prompt", *dimensions))
        writer.writeheader()
        for rating in (1, 3, 6):
            writer.writerow({"Story ID": "225", "Story": "story", "Prompt": "prompt", **{dimension: rating for dimension in dimensions}})
    plan = {"parent": {"parent_cell": {"artifact": {"sha256": hashlib.sha256(b"story").hexdigest()}, "contexts": [{"sha256": hashlib.sha256(b"prompt").hexdigest()}]}}}
    with pytest.raises(ValueError, match="rating is malformed"):
        module.hanna_means(csv_path, plan)


def test_focal_disagreement_separates_polarity_from_repeat_instability() -> None:
    module = load()
    ids = [f"q-{index}" for index in range(27)]
    cells: dict[str, list[dict[str, object]]] = {}
    for condition in module.FOCAL:
        for repetition in (1, 2, 3):
            cells[f"{condition}:{repetition}"] = [row(identifier, "YES") for identifier in ids]
    for index in range(7):
        cells[f"{module.FOCAL[1]}:{index % 3 + 1}"][index]["verdict"] = "NO"
    cells[f"{module.FOCAL[0]}:3"][7]["verdict"] = "NO"
    cells[f"{module.FOCAL[1]}:3"][7]["verdict"] = "NO"
    result = module.focal_disagreement(cells)
    assert result == {"focal_leaf_count": 27, "any_matched_polarity_disagreement_leaf_count": 7, "matched_pair_disagreement_count": 7, "matched_pair_count": 81, "any_six_observation_instability_leaf_count": 8}
