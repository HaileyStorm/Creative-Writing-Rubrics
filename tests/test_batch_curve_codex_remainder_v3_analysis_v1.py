from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evaluation-results/the-part-that-arrives-first-repeatability/batch-curve-codex-remainder-v3-analysis-v1/analyze.py"
SPEC = importlib.util.spec_from_file_location("batch_curve_v3_analysis_v1", SCRIPT)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_quote_grounding_is_per_leaf() -> None:
    assert ANALYSIS.leaf_grounded({"evidence": [{"exact_quote": "x"}]})
    assert not ANALYSIS.leaf_grounded({"evidence": [{"summary": "x"}]})


def test_analysis_has_no_provider_or_recommendation_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "requests" not in source and "http" not in source
    assert '"screening_recommendation": None' in source


def test_private_preflight_drift_is_rejected(tmp_path: Path) -> None:
    private = tmp_path / "private"; private.mkdir()
    payload = private / "preflight.json"; payload.write_bytes(b"{}")
    record = {"private_path": "preflight.json", "private_bytes": 2, "private_sha256": digest(b"{}")}
    assert ANALYSIS.validate_private_link(private, record) == payload
    with pytest.raises(ValueError, match="commitment drifted"):
        ANALYSIS.validate_private_link(private, {**record, "private_sha256": "0" * 64})


def test_run_score_drift_is_rejected(tmp_path: Path) -> None:
    private = tmp_path / "private"; run = private / "runs/cell"; run.mkdir(parents=True)
    for name in ("run.json", "score.json", "score.v2.json"):
        (run / name).write_bytes(b"{}")
    index = private / "index.json"; write_json(index, {"run_path": "runs/cell"})
    accepted = {"raw_evidence_index": {"private_path": "index.json", "private_bytes": index.stat().st_size, "private_sha256": ANALYSIS.sha256_file(index)}, "run_sha256": ANALYSIS.sha256_file(run / "run.json"), "score_sha256": ANALYSIS.sha256_file(run / "score.json"), "score_v2_sha256": ANALYSIS.sha256_file(run / "score.v2.json")}
    ANALYSIS.validate_run_scores(private, accepted)
    with pytest.raises(ValueError, match="score_sha256 drifted"):
        ANALYSIS.validate_run_scores(private, {**accepted, "score_sha256": "0" * 64})


def test_runtime_git_byte_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"; repo.mkdir(); (repo / "bound.json").write_bytes(b"clean")
    item = {"path": "bound.json", "bytes": 5, "sha256": digest(b"clean")}
    monkeypatch.setattr(ANALYSIS, "git_blob", lambda *_: b"altered")
    with pytest.raises(ValueError, match="Frozen Git binding drifted"):
        ANALYSIS.validate_git_binding(repo, "943282b", repo, item)


def test_publication_is_deterministic_and_private_free(tmp_path: Path) -> None:
    contract = json.loads((SCRIPT.parent / "analysis-contract.json").read_text(encoding="utf-8"))
    repeatability = {"4": {"metrics": {"exact_quote_grounding_rate": contract["expected_quote_grounding_rates"]["4"]}, "scores": [1, 2, 3]}}
    execution = {"execution_data_head": contract["execution_data_head"], "receipt_sha256": "a" * 64, "terminal_analysis_sha256": "b" * 64, "scored_units": 47, "successful_preflights": 6, "inherited_failed_preflights": 1}
    result = ANALYSIS.publication(repeatability, execution, {"summary.json": "c" * 64}, contract, "d" * 64)
    first, second = tmp_path / "one", tmp_path / "two"; ANALYSIS.publish(first, result); ANALYSIS.publish(second, result)
    assert {path.name: ANALYSIS.sha256_file(path) for path in first.glob("*.json")} == {path.name: ANALYSIS.sha256_file(path) for path in second.glob("*.json")}
    assert result["screening_recommendation"] is None and all(not value for value in result["privacy"].values())
    published = json.loads((first / "summary.json").read_text(encoding="utf-8"))
    assert published["analysis_contract_sha256"] == "d" * 64
    assert published["repaired_settlement"]["input_manifest_sha256"] == contract["repaired_settlement"]["manifest_sha256"]
    assert "private_root" not in published["execution"]
    assert "private_path" not in published["execution"]
    assert "prompt" not in published["execution"]
    assert "sessions" not in published["execution"]


def repaired_fixture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "repaired"; root.mkdir(parents=True)
    contract = json.loads((SCRIPT.parent / "analysis-contract.json").read_text(encoding="utf-8"))
    analyzer = root / "analyze.py"; analyzer.write_bytes(b"frozen analyzer\n")
    contract["repaired_settlement"]["analysis_script_sha256"] = ANALYSIS.sha256_file(analyzer)
    repeatability = {size: {"metrics": {"exact_quote_grounding_rate": rate}} for size, rate in contract["expected_quote_grounding_rates"].items()}
    write_json(root / "repeatability.json", repeatability)
    write_json(root / "summary.json", {"repeatability": repeatability, "screening_recommendation": None, "evidence": {"preflight_commitments": {"inherited_failed": 1}}})
    write_json(root / "runtime-bindings.json", {})
    write_json(root / "tamper-tests.json", {name: True for name in contract["repaired_settlement"]["required_tamper_gates"]})
    write_json(root / "unit-validation.json", {})
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": ANALYSIS.sha256_file(path)} for path in sorted(root.glob("*.json"))]
    write_json(root / "manifest.json", {"format_version": 2, "analysis_script_sha256": contract["repaired_settlement"]["analysis_script_sha256"], "files": files})
    contract["repaired_settlement"]["manifest_sha256"] = ANALYSIS.sha256_file(root / "manifest.json")
    return root, contract


def test_repaired_result_quote_grounding_contract(tmp_path: Path) -> None:
    root, contract = repaired_fixture(tmp_path)
    validated, _, inherited = ANALYSIS.validate_repaired_root(root, contract)
    assert inherited == 1
    assert validated["48"]["metrics"]["exact_quote_grounding_rate"] == contract["expected_quote_grounding_rates"]["48"]


def test_coherent_metric_and_manifest_rewrite_is_rejected(tmp_path: Path) -> None:
    root, contract = repaired_fixture(tmp_path)
    repeatability = json.loads((root / "repeatability.json").read_text(encoding="utf-8"))
    repeatability["4"]["metrics"]["exact_quote_grounding_rate"] = 0.0
    write_json(root / "repeatability.json", repeatability)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8")); summary["repeatability"] = repeatability; write_json(root / "summary.json", summary)
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": ANALYSIS.sha256_file(path)} for path in sorted(root.glob("*.json")) if path.name != "manifest.json"]
    write_json(root / "manifest.json", {"format_version": 2, "analysis_script_sha256": contract["repaired_settlement"]["analysis_script_sha256"], "files": files})
    with pytest.raises(ValueError, match="manifest drifted"):
        ANALYSIS.validate_repaired_root(root, contract)


def test_empty_or_false_tamper_gates_are_rejected(tmp_path: Path) -> None:
    root, contract = repaired_fixture(tmp_path)
    write_json(root / "tamper-tests.json", {})
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": ANALYSIS.sha256_file(path)} for path in sorted(root.glob("*.json")) if path.name != "manifest.json"]
    write_json(root / "manifest.json", {"format_version": 2, "analysis_script_sha256": contract["repaired_settlement"]["analysis_script_sha256"], "files": files})
    contract["repaired_settlement"]["manifest_sha256"] = ANALYSIS.sha256_file(root / "manifest.json")
    with pytest.raises(ValueError, match="tamper gates"):
        ANALYSIS.validate_repaired_root(root, contract)


def test_missing_or_mutated_unit_validation_is_rejected(tmp_path: Path) -> None:
    root, contract = repaired_fixture(tmp_path)
    (root / "unit-validation.json").unlink()
    with pytest.raises(ValueError, match="unit-validation.json"):
        ANALYSIS.validate_repaired_root(root, contract)
    root, contract = repaired_fixture(tmp_path / "mutated")
    write_json(root / "unit-validation.json", {"changed": True})
    with pytest.raises(ValueError, match="unit-validation.json"):
        ANALYSIS.validate_repaired_root(root, contract)


def test_missing_or_altered_repaired_analyzer_is_rejected(tmp_path: Path) -> None:
    root, contract = repaired_fixture(tmp_path)
    (root / "analyze.py").unlink()
    with pytest.raises(ValueError, match="analyzer bytes drifted"):
        ANALYSIS.validate_repaired_root(root, contract)
    root, contract = repaired_fixture(tmp_path / "altered")
    (root / "analyze.py").write_bytes(b"different analyzer\n")
    with pytest.raises(ValueError, match="analyzer bytes drifted"):
        ANALYSIS.validate_repaired_root(root, contract)


def test_missing_runtime_module_or_harness_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = json.loads((SCRIPT.parent / "analysis-contract.json").read_text(encoding="utf-8"))
    repaired = tmp_path / "repaired"; repaired.mkdir()
    write_json(repaired / "runtime-bindings.json", {"registry": {"path": "registry/all_modules.json", "bytes": 0, "sha256": digest(b"")}, "bundles": {"path": "bundles/all_bundles.json", "bytes": 0, "sha256": digest(b"")}, "executed_hbqrs_modules": []})
    monkeypatch.setattr(ANALYSIS, "git_blob", lambda *_: b"")
    with pytest.raises(ValueError, match="module set drifted"):
        ANALYSIS.validate_repaired_runtime(tmp_path, "943282b", repaired, contract)
    runtime = json.loads((repaired / "runtime-bindings.json").read_text(encoding="utf-8"))
    contract["required_runtime"]["modules"] = [{**module, "sha256": digest(b"")} for module in contract["required_runtime"]["modules"]]
    contract["required_runtime"]["harness"]["sha256"] = "a" * 64
    runtime["executed_hbqrs_modules"] = contract["required_runtime"]["modules"]
    write_json(repaired / "runtime-bindings.json", runtime)
    with pytest.raises(ValueError, match="harness Git bytes drifted"):
        ANALYSIS.validate_repaired_runtime(tmp_path, "943282b", repaired, contract)


def test_escaped_run_path_is_rejected(tmp_path: Path) -> None:
    private = tmp_path / "private"; private.mkdir(); index = private / "index.json"
    write_json(index, {"run_path": "../outside"})
    accepted = {"raw_evidence_index": {"private_path": "index.json", "private_bytes": index.stat().st_size, "private_sha256": ANALYSIS.sha256_file(index)}}
    with pytest.raises(ValueError, match="Run path escaped"):
        ANALYSIS.validate_run_scores(private, accepted)
