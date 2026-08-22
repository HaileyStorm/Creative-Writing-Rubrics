from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-confidence-diagnostics-v1"
sys.path.insert(0, str(PACKAGE))
spec = importlib.util.spec_from_file_location("confidence_diagnostics_v1", PACKAGE / "study.py")
assert spec and spec.loader
study = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = study
spec.loader.exec_module(study)


def _seal(directory: Path, payload: dict) -> None:
    directory.mkdir()
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    (directory / "confidence-input.json").write_bytes(raw)
    manifest = {"format_version": 1, "kind": payload["kind"], "files": {"confidence-input.json": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}}
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _fingerprint(model: str) -> dict[str, str]:
    return {
        "provider": "test", "model": model, "reasoning_effort": "high",
        "prompt_sha256": "a" * 64, "schema_sha256": "b" * 64,
        "compiled_bundle_sha256": "c" * 64, "questions_sha256": "d" * 64,
        "runtime_sha256": "e" * 64, "corpus_sha256": "f" * 64, "selection_sha256": "0" * 64,
    }


def _authority() -> dict:
    return {"parent_manifest": {"bytes": 42, "sha256": "a" * 64}}


def _condition() -> dict:
    return {"phase": "development", "arm_id": "hbq", "bundle_id": "prose.short_story", "batch_size": 32, "polarity": "as_frozen", "task_contract_sha256": "b" * 64, "weight_profile_sha256": "c" * 64}


def _repeat_payload() -> dict:
    fingerprint = _fingerprint("model-a"); fingerprint.pop("reasoning_effort"); fingerprint["requested_reasoning_effort"] = "high"; fingerprint["reasoning_attestation"] = "provider_attested"
    return {"format_version": 1, "kind": "repeatability_confidence_evidence", "models": [{"model_fingerprint": fingerprint, "condition": _condition(), "authority": _authority(), "records": [
        {"item_id": "opaque-1", "question_id": "q-1", "role": "domain", "effective_weight": 1.0, "responses": [{"verdict": "YES", "confidence": 0.95}, {"verdict": "YES", "confidence": 0.9}, {"verdict": "YES", "confidence": 0.9}]},
        {"item_id": "opaque-1", "question_id": "q-2", "role": "penalty", "effective_weight": 2.0, "responses": [{"verdict": "NO", "confidence": 0.3}, {"verdict": "YES", "confidence": 0.4}, {"verdict": "NO", "confidence": 0.3}]}
    ]}]}


def _fresh_payload() -> dict:
    records = []
    for index in range(88):
        human = float((index % 5) + 1)
        records.append({"item_id": f"opaque-{index}", "source_model": "Human" if index < 8 else "Generated", "score": float(index), "hanna_overall": human, "hanna_dimensions": {name: human for name in study.FRESH_DIMENSIONS}, "mapped_scores": {name: index % 3 / 2 for name in study.FRESH_DIMENSIONS}, "mapped_confidences": {name: 0.5 + (index % 5) / 10 for name in study.FRESH_DIMENSIONS}, "verdicts": [{"verdict": "YES" if index % 2 else "NO", "confidence": 0.5 + (index % 5) / 10, "effective_weight": 1.0, "role": "domain"}, {"verdict": "NOT_APPLICABLE", "confidence": 0.9, "effective_weight": 0.5, "role": "hard_gate"}]})
    digest = hashlib.sha256(study.canonical([{"item_id": item["item_id"], "source_model": item["source_model"], "hanna_overall": item["hanna_overall"], "hanna_dimensions": item["hanna_dimensions"]} for item in records])).hexdigest()
    def model(name: str) -> dict:
        fingerprint = _fingerprint(name); fingerprint.pop("reasoning_effort"); fingerprint["requested_reasoning_effort"] = "high"; fingerprint["reasoning_attestation"] = "provider_attested"
        return {"model_fingerprint": fingerprint, "condition": _condition(), "authority": _authority(), "selection_digest": digest, "records": records}
    return {"format_version": 1, "kind": "fresh88_confidence_evidence", "models": [model("fresh"), model("grok")]}


def test_repeat_diagnostics_keep_proxy_and_canonical_boundaries(tmp_path: Path) -> None:
    repeat = tmp_path / "repeat"; _seal(repeat, _repeat_payload())
    summary = study.analyze(repeat, None, tmp_path / "output")
    model = next(iter(summary["repeatability"].values()))
    assert model["repeat_consensus_proxy_not_human_truth"] is True
    assert model["stable_vs_flip"]["stable_leaf_count"] == 1
    assert model["stable_vs_flip"]["flipped_leaf_count"] == 1
    assert model["leave_one_out_eligible_response_count"] == 4
    assert model["leave_one_out_tied_excluded_response_count"] == 2
    assert model["leave_one_out_repeat_consensus_proxy_calibration"]["brier"] is not None
    assert model["equal_budget_resampling"]["status"] == "observed_repeat_bootstrap_only"
    assert model["role_stratified_noncanonical_diagnostics"]["domain"]["effective_confidence_mass_is_not_coverage"] is True
    assert "opaque-1" not in (tmp_path / "output" / "summary.json").read_text(encoding="utf-8")


def test_fresh88_separates_fingerprints_and_refuses_brier_claims(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"; _seal(fresh, _fresh_payload())
    summary = study.analyze(None, fresh, tmp_path / "output")
    assert len(summary["fresh88"]) == 2
    for result in summary["fresh88"].values():
        assert result["item_count"] == 88
        association = result["confidence_vs_hanna_rank_association"]
        assert association["brier_ece_reliability_bins"] == "not_emitted_without_binary_human_leaf_truth"
        assert result["primary_generated80"]["item_count"] == 80
        assert result["secondary_all88"]["dimensions"]["Relevance"]["not_leaf_truth_or_calibration"] is True
    assert "opaque-0" not in (tmp_path / "output" / "summary.json").read_text(encoding="utf-8")


def test_output_is_deterministic_for_same_sealed_inputs(tmp_path: Path) -> None:
    repeat = tmp_path / "repeat"; fresh = tmp_path / "fresh"
    _seal(repeat, _repeat_payload()); _seal(fresh, _fresh_payload())
    study.analyze(repeat, fresh, tmp_path / "output-a")
    study.analyze(repeat, fresh, tmp_path / "output-b")
    for name in ("summary.json", "manifest.json"):
        assert (tmp_path / "output-a" / name).read_bytes() == (tmp_path / "output-b" / name).read_bytes()


def test_sealed_input_and_output_tampering_fail_closed(tmp_path: Path) -> None:
    repeat = tmp_path / "repeat"; _seal(repeat, _repeat_payload())
    (repeat / "confidence-input.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        study.analyze(repeat, None, tmp_path / "output")
    repeat = tmp_path / "repeat2"; _seal(repeat, _repeat_payload())
    output = tmp_path / "existing"; output.mkdir()
    with pytest.raises(ValueError, match="Refusing"):
        study.analyze(repeat, None, output)


def test_output_verifier_rejects_private_key_and_invalid_primary_shape(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"; _seal(fresh, _fresh_payload())
    study.analyze(None, fresh, tmp_path / "output")
    summary_path = tmp_path / "output" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["evidence"]["fresh88"]["input"]["item_id"] = "leak"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    manifest_path = tmp_path / "output" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["summary.json"] = {"bytes": summary_path.stat().st_size, "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="raw/private"):
        study.verify_output(tmp_path / "output")
    bad = _fresh_payload(); bad["models"][0]["records"][8]["source_model"] = "Human"
    fresh = tmp_path / "fresh2"; _seal(fresh, bad)
    with pytest.raises(ValueError, match="generated-only"):
        study.analyze(None, fresh, tmp_path / "output2")


def test_rejects_private_fields_and_nonrectangular_repeat_matrix(tmp_path: Path) -> None:
    payload = _repeat_payload()
    payload["models"][0]["records"][0]["prose"] = "forbidden"
    repeat = tmp_path / "repeat"; _seal(repeat, payload)
    with pytest.raises(ValueError, match="unsupported"):
        study.analyze(repeat, None, tmp_path / "output")
    payload = _repeat_payload()
    payload["models"][0]["records"][1]["responses"].pop()
    repeat = tmp_path / "repeat2"; _seal(repeat, payload)
    with pytest.raises(ValueError, match="rectangular"):
        study.analyze(repeat, None, tmp_path / "output2")


def test_rejects_incomplete_fingerprint_and_missing_dimension_mapping(tmp_path: Path) -> None:
    payload = _fresh_payload()
    payload["models"][0]["model_fingerprint"].pop("runtime_sha256")
    fresh = tmp_path / "fresh"; _seal(fresh, payload)
    with pytest.raises(ValueError, match="complete"):
        study.analyze(None, fresh, tmp_path / "output")
    payload = _fresh_payload()
    payload["models"][0]["records"][0]["mapped_confidences"].pop("Surprise")
    fresh = tmp_path / "fresh2"; _seal(fresh, payload)
    with pytest.raises(ValueError, match="mapped HBQ"):
        study.analyze(None, fresh, tmp_path / "output2")


def test_rejects_selection_parity_and_reasoning_attestation_drift(tmp_path: Path) -> None:
    payload = _fresh_payload()
    payload["models"][1]["selection_digest"] = "a" * 64
    fresh = tmp_path / "fresh"; _seal(fresh, payload)
    with pytest.raises(ValueError, match="selection/source/HANNA"):
        study.analyze(None, fresh, tmp_path / "output")
    payload = _fresh_payload()
    payload["models"][1]["model_fingerprint"]["reasoning_attestation"] = "forged"
    fresh = tmp_path / "fresh2"; _seal(fresh, payload)
    with pytest.raises(ValueError, match="attestation"):
        study.analyze(None, fresh, tmp_path / "output2")
    payload = _fresh_payload()
    payload["models"][1]["condition"]["task_contract_sha256"] = "d" * 64
    fresh = tmp_path / "fresh3"; _seal(fresh, payload)
    with pytest.raises(ValueError, match="task-contract digest"):
        study.analyze(None, fresh, tmp_path / "output3")
