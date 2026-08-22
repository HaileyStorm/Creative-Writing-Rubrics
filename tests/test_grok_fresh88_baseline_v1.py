from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-fresh88-baseline-v1"


def load():
    spec = importlib.util.spec_from_file_location("grok_fresh88_baseline_v1", ROOT / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


study = load()


def make_primary(tmp_path):
    output = tmp_path / "primary"
    output.mkdir()
    dimensions = {name: {"spearman": {"estimate": 0.1}} for name in study.RATING_DIMENSIONS}
    rows = []
    for ordinal in range(1, 89):
        rows.append({"item_id": f"hanna-{ordinal}", "story_id": str(ordinal), "execution_ordinal": ordinal, "selection_ordinal": ordinal, "source_model": "Model", "quartile": 1, "prompt_group_id": f"prompt-{ordinal // 2}", "story_sha256": f"story-{ordinal}", "prompt_sha256": f"prompt-hash-{ordinal}", "human_ratings": {name: [1, 2, 3] for name in study.RATING_DIMENSIONS}, "human_means": {name: 2.0 for name in study.RATING_DIMENSIONS}, "human_overall": 2.0, "hbq_full_observed_score": float(ordinal), "hbq_mapping": {name: {"score": 0.0, "coverage": 1.0, "unresolved": 0, "not_applicable": 0, "question_count": 1} for name in study.RATING_DIMENSIONS}, "evidence": {}})
    summary = {"format_version": 1, "study_id": study.PRIMARY_ID, "analysis_kind": "offline_primary_development_analysis", "evidence_binding": {"analysis_contract_sha256": "a" * 64}, "item_count": 88, "primary_generated_only": {"dimensions": dimensions}}
    (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (output / "items.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    manifest = {"format_version": 1, "study_id": study.PRIMARY_ID, "analysis_contract_sha256": "a" * 64, "summary_evidence_binding_sha256": hashlib.sha256(study.canonical(summary["evidence_binding"])).hexdigest(), "files": {name: study.file_binding(output / name) for name in ("summary.json", "items.jsonl")}}
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return output, rows


def test_contract_is_explicitly_analysis_only_and_not_a_relabeling_route():
    assert study.CONTRACT["status"] == "analysis_only_preregistered"
    assert study.CONTRACT["parents"]["grok_generation"]["study_id"] == "hbq-human-alignment-supplemental-providers-v1"
    assert "does not establish the Fresh88 baseline" in study.CONTRACT["parents"]["historical_verifier"]["role"]


def test_primary_schema_rejects_unbound_or_incomplete_parent(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    for name in ("summary.json", "items.jsonl", "manifest.json"):
        (primary / name).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="summary identity"):
        study.load_primary(primary)


def test_missing_primary_files_are_named(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    with pytest.raises(ValueError, match="summary.json"):
        study.load_primary(primary)


def test_cluster_bootstrap_is_prompt_group_seeded_and_descriptive():
    result = study.paired_cluster_bootstrap([("p-a", 1.0), ("p-a", 3.0), ("p-b", -1.0)])
    assert result["seed"] == 560820 + 901
    assert result["draws"] == 1000
    assert result["cluster"] == "prompt_group_id"
    assert result["item_count"] == 3
    assert result["estimate"] == pytest.approx(1.0)
    assert result["descriptive_only"] is True


def test_analysis_uses_primary_canonical_order_and_binds_both_parents(monkeypatch, tmp_path):
    primary, rows = make_primary(tmp_path)
    grok = tmp_path / "grok"; grok.mkdir()
    scores = {row["item_id"]: row["hbq_full_observed_score"] + 1 for row in reversed(rows)}
    runtime = {"analyzer": {"relative_path": "analyze.py", "bytes": 1, "sha256": "a" * 64}, "study": {"relative_path": "study.py", "bytes": 1, "sha256": "b" * 64}, "contract": {"relative_path": "study-contract.json", "bytes": 1, "sha256": "c" * 64}}
    reasoning = {"accepted_checkpoint_count": 528, "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli", "attestation_counts": {"not_reported_by_grok_build_cli": 528}}
    evidence = {"verification_manifest": {"bytes": 1, "sha256": "a" * 64}, "generic_verifier_v2": {"bytes": 1, "sha256": "c" * 64}, "provider_id": study.GROK_ID, "phase": "development", "item_count": 88, "receipt_session_count": 528, "receipt_chain_sha256": "d" * 64, "corpus_root_sha256": "e" * 64, "reasoning_provenance": reasoning}
    monkeypatch.setattr(study, "verify_grok_corpus", lambda root, manifest, loaded, **_: (scores, evidence))
    monkeypatch.setattr(study, "_require_committed_clean_runtime", lambda: runtime)
    output = tmp_path / "output"
    summary = study.analyze(primary, grok, tmp_path / "verifier", output)
    produced = [json.loads(line) for line in (output / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert [row["execution_ordinal"] for row in produced] == list(range(1, 89))
    assert all(row["grok_minus_fresh88"] == 1.0 for row in produced)
    assert summary["fresh88_primary_hanna_metrics"]["dimensions"] == list(study.RATING_DIMENSIONS)
    assert summary["grok_reasoning_provenance"] == reasoning
    assert manifest["parents"]["historical_grok"]["receipt_session_count"] == 528
    assert manifest["parents"]["fresh88_primary"]["identity"]["analysis_kind"] == "offline_primary_development_analysis"
    assert manifest["successor_runtime"] == runtime
    (output / "items.jsonl").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file bindings drifted"):
        study.verify_output(output, runtime)


def test_grok_verifier_rejects_id_mismatch_before_raw_run_verification(monkeypatch, tmp_path):
    primary, rows = make_primary(tmp_path)
    grok = tmp_path / "grok"; (grok / "invocations" / study.GROK_ID).mkdir(parents=True)
    (grok / "frozen-provider-contract.json").write_text(json.dumps({"study_id": "hbq-human-alignment-supplemental-providers-v1", "frozen_before_execution": True, "selection": {"partitions": {"development": [{"item_id": "wrong"}] * 88}}}), encoding="utf-8")
    (grok / "invocations" / study.GROK_ID / "development.json").write_text("{}", encoding="utf-8")
    (tmp_path / "verifier").mkdir()
    (tmp_path / "verifier" / "verification-manifest.json").write_text("{}", encoding="utf-8")
    fake = type("Verifier", (), {"verify_verification_manifest": staticmethod(lambda *_: {"corpus": {"provider_id": study.GROK_ID, "phase": "development", "run_count": 88, "checkpoint_count": 528, "receipt_chain_sha256": "a" * 64, "root_commitment": {"sha256": "b" * 64}}}), "load_frozen": staticmethod(lambda path: json.loads((path / "frozen-provider-contract.json").read_text(encoding="utf-8")))})()
    monkeypatch.setattr(study, "_load_generic", lambda *_: fake)
    with pytest.raises(ValueError, match="exact same 88 IDs"):
        study.verify_grok_corpus(grok, tmp_path / "verifier", rows)


def test_reasoning_provenance_requires_all_528_unattested_grok_receipts(tmp_path):
    work = tmp_path / "work"
    selected = []
    for ordinal in range(88):
        item_id = f"hanna-{ordinal}"
        selected.append({"item_id": item_id})
        responses = work / "runs" / study.GROK_ID / "development" / item_id / "run-01" / "responses"
        responses.mkdir(parents=True)
        for batch in range(1, 7):
            (responses / f"batch-{batch:04d}.json").write_text(json.dumps({"provider": {"reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli"}}), encoding="utf-8")
    result = study._grok_reasoning_provenance(work, selected)
    assert result["accepted_checkpoint_count"] == 528
    assert result["reasoning_attested"] is False
    assert result["attestation_counts"] == {"not_reported_by_grok_build_cli": 528}
    path = work / "runs" / study.GROK_ID / "development" / "hanna-0" / "run-01" / "responses" / "batch-0001.json"
    path.write_text(json.dumps({"provider": {"reasoning_attested": True, "reasoning_attestation": "not_reported_by_grok_build_cli"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="attestation provenance drifted"):
        study._grok_reasoning_provenance(work, selected)


def test_runtime_binding_tamper_is_rejected(monkeypatch, tmp_path):
    original = {name: path for name, path in study._runtime_paths().items()}
    monkeypatch.setattr(study, "_runtime_paths", lambda: original)
    class Result:
        returncode = 0
        def __init__(self, stdout=b""): self.stdout = stdout
    def command(args, **_kwargs):
        if args[-1].startswith("HEAD:"):
            relative = args[-1].split(":", 1)[1]
            for path in original.values():
                if study._relative_path(path) == relative:
                    return Result(path.read_bytes())
        return Result()
    monkeypatch.setattr(study.subprocess, "run", command)
    assert study._require_committed_clean_runtime()["study"]["sha256"] == study.sha256_path(original["study"])
    def tampered(args, **_kwargs):
        result = command(args, **_kwargs)
        if args[-1].startswith("HEAD:"):
            result.stdout += b"tamper"
        return result
    monkeypatch.setattr(study.subprocess, "run", tampered)
    with pytest.raises(ValueError, match="does not match"):
        study._require_committed_clean_runtime()


@pytest.mark.parametrize("pairs", [[], [("", 1.0)], [("p", True)], [("p", "1")]])
def test_cluster_bootstrap_rejects_malformed_pairs(pairs):
    with pytest.raises(ValueError):
        study.paired_cluster_bootstrap(pairs)


def test_contract_json_round_trips_without_hidden_mutation():
    assert json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8")) == study.CONTRACT


@pytest.mark.skipif(not all(os.environ.get(name) for name in ("CWR_FRESH88_PRIMARY_OUTPUT", "CWR_HISTORICAL_GROK_WORK", "CWR_GROK_VERIFIER_OUTPUT", "CWR_GROK_VERIFIER_CLEAN_REPO")), reason="explicit sealed-parent replay roots")
def test_real_sealed_parent_replay(monkeypatch):
    clean = Path(os.environ["CWR_GROK_VERIFIER_CLEAN_REPO"])
    verifier_path = clean / "evaluation-results" / "hbq-human-alignment-supplemental-providers-verifier-v2" / "analyze_study.py"
    monkeypatch.setattr(sys, "path", [str(clean / "src"), *sys.path])
    for name in [name for name in sys.modules if name == "hbqrs" or name.startswith("hbqrs.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    _, rows, _ = study.load_primary(Path(os.environ["CWR_FRESH88_PRIMARY_OUTPUT"]))
    scores, evidence = study.verify_grok_corpus(Path(os.environ["CWR_HISTORICAL_GROK_WORK"]), Path(os.environ["CWR_GROK_VERIFIER_OUTPUT"]), rows, generic_verifier_path=verifier_path)
    assert len(scores) == 88
    assert evidence["receipt_session_count"] == 528
    assert evidence["reasoning_provenance"]["attestation_counts"] == {"not_reported_by_grok_build_cli": 528}
