from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile
import runpy
import shutil
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v4"
RESULTS = ROOT / "results"


def _json(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def _verifier():
    return SimpleNamespace(**runpy.run_path(str(RESULTS / "verify_results.py"), run_name="established_v4_publication_verifier"))


def _publication_fixture(tmp_path: Path) -> Path:
    study = tmp_path / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v4"
    shutil.copytree(ROOT, study, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT.parent / "source.md", study.parent / "source.md")
    return study / "results"


def test_publication_manifest_hashes_and_privacy_scan() -> None:
    manifest = _verifier().verify()
    assert len(manifest["files"]) == 6
    assert manifest["source_analysis_manifest"] == {"file_count": 31, "bytes": 5205, "sha256": "3267343f9f6653489eca29f45957335458fe304b45a6762695e28d7dd3c81c95"}
    assert manifest["files"]["agreement.svg"] == {"bytes": 1654, "sha256": "6d8a22b8dcb18366813a4a43074c6dd761ab27029ba8058a1271f670fed8ab41"}
    assert manifest["files"]["score-distributions.svg"] == {"bytes": 3607, "sha256": "f2f2d1b84c5b076478c6445b4d27880e7b28e9437fb362956c3b9a09b2599b2f"}


def test_verifier_rejects_an_unexpected_raw_private_artifact(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    (results / "response.json").write_text('{"private_path":"C:\\\\Users\\\\writer\\\\draft.txt"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected or missing entries"):
        _verifier().verify(results)


def test_verifier_privacy_scans_the_publication_manifest(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    manifest_path = results / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["private_path"] = "C:\\Users\\writer\\draft.txt"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest contains a private runtime field"):
        _verifier().verify(results)


def test_verifier_allows_only_regenerable_python_cache_entries(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    py_compile.compile(str(results / "verify_results.py"), doraise=True)
    _verifier().verify(results)
    cache = results / "__pycache__"
    assert list(cache.glob("verify_results.*.pyc"))
    (cache / "response.json").write_text('{"private":"raw provider output"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected or missing entries"):
        _verifier().verify(results)


def test_verifier_binds_publication_authorization_and_source_bytes(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    study = results.parent
    contract_path = study / "study-contract.json"
    manifest_path = results / "publication-manifest.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source"]["publication_authorized"] = False
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["protocol_contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not authorize"):
        _verifier().verify(results)
    contract["source"]["publication_authorized"] = True
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["protocol_contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (study.parent / "source.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the frozen contract"):
        _verifier().verify(results)


def test_published_metrics_match_the_completed_study() -> None:
    summary = _json("summary.json")
    hbq = summary["arms"]["hbq_short_story_batch32"]
    assert hbq["exact_all_run_agreement_rate"] == pytest.approx(0.9101123595505618)
    assert hbq["mean_modal_label_proportion"] == pytest.approx(0.9707865168539327)
    assert hbq["nominal_krippendorff_alpha"] == pytest.approx(0.8616957801335363)
    assert hbq["observed_score"]["mean"] == pytest.approx(90.6764)
    assert hbq["observed_score"]["sample_standard_deviation"] == pytest.approx(3.2755873877825366)
    assert hbq["observed_score"]["range"] == pytest.approx(8.2961)
    naplan = summary["arms"]["naplan_narrative_2022"]
    cambridge = summary["arms"]["cambridge_igcse_0500_p2_mj_2024"]
    oregon = summary["arms"]["oregon_narrative_2017"]
    assert naplan["total_score"]["values"] == [47] * 5 and naplan["retry_provenance"]["semantic_rejection_count"] == 3
    assert cambridge["total_score"]["values"] == [40, 40, 39, 40, 39]
    assert cambridge["criteria"]["content_and_structure"]["values"] == [16, 16, 15, 16, 15]
    assert oregon["total_score"]["values"] == [36] * 5 and oregon["retry_provenance"]["semantic_rejection_count"] == 3


def test_leaf_publication_is_complete_and_run_ids_are_not_published() -> None:
    leaves = _json("hbq-leaf-repeatability.json")["leaves"]
    assert len(leaves) == 178
    assert all(len(item["labels"]) == 5 for item in leaves)
    assert "session_id" not in json.dumps(_json("provenance.json"))
    assert "run_id" not in json.dumps(leaves)
