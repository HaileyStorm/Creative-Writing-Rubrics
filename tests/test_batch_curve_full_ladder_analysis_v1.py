from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evaluation-results/the-part-that-arrives-first-repeatability/batch-curve-full-ladder-analysis-v1/analyze.py"
CONTRACT = SCRIPT.parent / "analysis-contract.json"
SPEC = importlib.util.spec_from_file_location("full_ladder_analysis", SCRIPT)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ANALYSIS)

PARENT_PUBLIC = Path(r"C:\Users\Haile\Documents\cwr-batch-curve-codex-v1-20260821-ae23440-r1")
PARENT_PRIVATE = Path(r"C:\Users\Haile\Documents\cwr-batch-curve-codex-v1-20260821-ae23440-private-r1")
V3_PUBLIC = Path(r"C:\Users\Haile\Documents\cwr-batch-curve-v3-live-943282b-20260822")
V3_PRIVATE = Path(r"C:\Users\Haile\Documents\cwr-batch-curve-v3-private-943282b-20260822")
RUNTIME = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-batch-v3-943282b-clean")


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value), encoding="utf-8")


def record(path: Path) -> dict[str, object]:
    return {"relative_path": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_private_reference_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escaped"):
        ANALYSIS.bound_private(tmp_path, {"relative_path": "../escape", "bytes": 0, "sha256": "0" * 64})


def test_run_path_rejects_escape_after_valid_index(tmp_path: Path) -> None:
    index = tmp_path / "index.json"; write(index, {"run_path": "../escape", "files": [], "private_root_sha256": "a" * 64})
    with pytest.raises(ValueError, match="Run path escaped"):
        ANALYSIS.validate_private_index(tmp_path, {"raw_evidence_index": {**record(index), "private_root_sha256": "a" * 64}})


def test_contract_freezes_exact_runtime_and_v3_ranges() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["sizes"] == [1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, "all-in-one"]
    assert contract["recommendation"] is None
    assert set(contract["analysis_runtime"]["files"]) == {"hbqrs", "core", "paths", "runner", "scoring_v2", "weights", "registry", "bundles", "harness"}
    assert {key: list(value) for key, value in ANALYSIS.expected_v3_schedule().items()} == {36: list(range(32, 46)), 37: list(range(1, 7)), 38: list(range(1, 24)), 39: list(range(1, 5))}
    assert len(contract["parent_geometry"]["quota_rejections"]) == 3
    assert [item["batch"] for item in contract["parent_geometry"]["prefix_batches"]] == list(range(1, 32))


def test_runtime_drift_rejects_missing_or_replaced_file(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="Analysis runtime drifted"):
        ANALYSIS.validate_runtime(ROOT, tmp_path, contract)


def test_git_contract_drift_rejects() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8")); contract["v3_contract_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="V3 contract byte drifted"):
        ANALYSIS.validate_v3_bindings(ROOT, contract)


def test_duplicate_session_and_parent_overlap_reject() -> None:
    session = "a" * 64; seen: set[str] = set()
    ANALYSIS.collect_sessions({"sessions": [{"session_id_sha256": session}]}, seen, "first")
    with pytest.raises(ValueError, match="overlap or resend"):
        ANALYSIS.collect_sessions({"sessions": [{"session_id_sha256": session}]}, seen, "duplicate")
    with pytest.raises(ValueError, match="overlaps parent"):
        ANALYSIS.require_no_session_overlap({session}, {session})


def test_batch_geometry_and_private_index_member_drift_reject(tmp_path: Path) -> None:
    private = tmp_path / "private"; private.mkdir(); run = private / "runs/cell"; run.mkdir(parents=True)
    member = run / "verdicts.jsonl"; member.write_text("{}\n", encoding="utf-8")
    index = private / "index.json"; write(index, {"run_path": "runs/cell", "private_root_sha256": "b" * 64, "files": [{"path": "runs/cell/verdicts.jsonl", "bytes": member.stat().st_size, "sha256": ANALYSIS.sha(member)}]})
    accepted = {"raw_evidence_index": {**record(index), "private_root_sha256": "b" * 64}}
    ANALYSIS.validate_private_index(private, accepted)
    member.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="member drifted"):
        ANALYSIS.validate_private_index(private, accepted)


def test_parent_prefix_byte_mutation_and_session_overlap_reject() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(contract)); broken["parent_geometry"]["prefix_batches"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="prefix batch bytes drifted"):
        ANALYSIS.validate_parent_prefix_batches(PARENT_PRIVATE, broken, set())
    session = contract["parent_geometry"]["prefix_batches"][0]["session_id_sha256"]
    with pytest.raises(ValueError, match="overlap or resend"):
        ANALYSIS.validate_parent_prefix_batches(PARENT_PRIVATE, contract, {session})


def test_preloaded_wrong_hbqrs_module_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    monkeypatch.setitem(sys.modules, "hbqrs", SimpleNamespace(__file__=str(ROOT / "tests" / "conftest.py")))
    with pytest.raises(ValueError, match="Preloaded or wrong HBQRS module"):
        ANALYSIS.validate_executed_hbqrs(RUNTIME, contract)


def test_public_projection_rejects_private_paths_prompts_and_sessions() -> None:
    for forbidden in ({"sessions": []}, {"prompt_sha256": "a" * 64}, {"private_root_sha256": "a" * 64}, {"run_path": "runs/x"}):
        with pytest.raises(ValueError, match="leaked"):
            ANALYSIS.public_projection_is_safe(forbidden)
    ANALYSIS.public_projection_is_safe({"privacy": {"contains_private_evidence": False}})


def test_publication_writes_lf_json(tmp_path: Path) -> None:
    target = tmp_path / "result.json"; ANALYSIS.write(target, {"ok": True})
    assert target.read_bytes() == b'{\n  "ok": true\n}\n'


@pytest.mark.skipif(not all(path.is_dir() for path in (PARENT_PUBLIC, PARENT_PRIVATE, V3_PUBLIC, V3_PRIVATE, RUNTIME)), reason="sealed local evidence roots unavailable")
def test_real_deterministic_replay_and_public_manifest(tmp_path: Path) -> None:
    args = ["--repo-root", str(ROOT), "--runtime-root", str(RUNTIME), "--parent-public-root", str(PARENT_PUBLIC), "--parent-private-root", str(PARENT_PRIVATE), "--v3-public-root", str(V3_PUBLIC), "--v3-private-root", str(V3_PRIVATE)]
    first, second = tmp_path / "one", tmp_path / "two"
    for output in (first, second):
        subprocess.run([sys.executable, str(SCRIPT), *args, "--output-dir", str(output)], check=True, capture_output=True, text=True)
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert (first / "repeatability.json").read_bytes() == (second / "repeatability.json").read_bytes()
    summary = json.loads((first / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "completed_offline_full_ladder_no_recommendation"
    ANALYSIS.public_projection_is_safe(summary)
