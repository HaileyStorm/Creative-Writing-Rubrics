from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-sentinel-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("nonpoetry_scope_sentinel_study", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return historical_runtime.install(module, source_commit="c4ba06453785bdb52bce374926b65d3cab542a9a")
    except historical_runtime.HistoricalRuntimeUnbound as exc:
        pytest.skip(f"historical runtime unbound: {exc}")


def test_frozen_s2_subset_has_exact_four_state_geometry_and_no_provider_mode():
    s = load_study()
    assert s.verify_package() == {
        "study_id": "hbq-nonpoetry-scope-sentinel-v1",
        "status": "frozen_development_only_nonpoetry_scope_sentinel",
        "provider_calls": 0,
        "artifacts": 20,
        "slots": 60,
        "staged_subset_of_s2": 300,
    }
    slots = s.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 60
    assert {slot["leaf_id"] for slot in slots} == set(s.LEAVES)
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["state"] for slot in slots} == set(s.STATES)
    assert {slot["expected_verdict"] for slot in slots} == s.VERDICTS
    assert s.load_contract()["portfolio_binding"]["additive_to_portfolio"] is False


def test_current_leaf_bytes_and_criterion_ownership_are_bound():
    s = load_study()
    assert s.source_leaf_hashes() == s.load_contract()["bindings"]["source_leaves"]
    assert s.source_leaf_records()["scope.passage.status"]["question_type"] == "diagnostic"
    assert s.source_leaf_records()["op.critique.single_unit_critique.no_whole_claims"]["text"].startswith("Does it avoid extrapolating")


def test_each_staged_leaf_is_hard_pinned_to_its_own_s2_scope_finding_record():
    s = load_study()
    portfolio = s.load_contract()["portfolio_binding"]
    rows = {row["finding_id"]: row for row in s.load_jsonl(s.REPOSITORY / portfolio["findings_path"])}
    assert [*portfolio["leaf_findings"]] == list(s.LEAVES)
    assert list(portfolio["leaf_findings"].values()) == portfolio["finding_ids"]
    for leaf, finding_id in portfolio["leaf_findings"].items():
        assert rows[finding_id]["kind"] == "scope_binding_review"
        assert rows[finding_id]["subjects"] == [leaf]


def test_state_invariant_uses_scope_not_quality_and_nonpoetry_artifacts_match_leaves():
    s = load_study()
    contract = s.load_contract()
    assert contract["state_invariant"] == s.STATE_INVARIANT
    assert contract["screen"] == s.SCREEN
    corpus = s.load_corpus()
    for artifact in corpus["artifacts"]:
        if artifact["state"] != "activation_mismatch":
            assert artifact["artifact_kind"] == s.LEAF_ARTIFACT_KINDS[artifact["leaf_id"]]
    assert {item["artifact_kind"] for item in corpus["artifacts"] if item["leaf_id"] == "data.eval.evaluation_determinism.rerun" and item["state"] != "activation_mismatch"} == {"evaluation_pipeline"}
    assert {item["artifact_kind"] for item in corpus["artifacts"] if item["leaf_id"] == "op.critique.single_unit_critique.no_whole_claims" and item["state"] != "activation_mismatch"} == {"critique_report"}
    assert {item["artifact_kind"] for item in corpus["artifacts"] if item["leaf_id"] == "scope.passage.status" and item["state"] != "activation_mismatch"} == {"scope_evaluation_record"}


def test_all_twenty_fixture_contracts_pin_completion_scope_and_private_oracle_ledger():
    s = load_study()
    corpus = s.load_corpus()["artifacts"]
    contexts = [s.task_context_for(artifact) for artifact in corpus]
    assert len(contexts) == 20
    assert {context["completion_status"] for context in contexts} == {"complete", "excerpt", "unknown"}
    assert len({item["fixture_id"] for item in s.FIXTURE_CONTRACTS.values()}) == 20
    for artifact, context in zip(corpus, contexts, strict=True):
        fixture = s.FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]
        assert fixture["scope_declaration"] == artifact["declared_scope"] == context["declared_scope"]
        assert fixture["oracle_verdict"] == s.STATE_VERDICTS[artifact["state"]]
        assert context["completion_status"] == fixture["completion_status"]
    scope_material = next(item for item in corpus if item["leaf_id"] == "scope.passage.status" and item["state"] == "material_failure")
    assert "EXCERPT" in scope_material["text"] and "whole-work completeness" in scope_material["contexts"][0]
    critique_unknown = next(item for item in corpus if item["leaf_id"] == "op.critique.single_unit_critique.no_whole_claims" and item["state"] == "missing_required_evidence")
    assert "whole-manuscript" not in critique_unknown["text"] and "unknown" in critique_unknown["contexts"][0]


def test_production_renderer_keeps_local_labels_and_state_ledger_out_of_prompts():
    s = load_study()
    rendered = s.render_all_provider_prompts()
    assert len(rendered) == 60
    slot = next(slot for slot in s.plan_slots() if slot["leaf_id"] == "scope.passage.status" and slot["state"] == "material_failure")
    prompt = rendered[slot["slot_id"]]
    assert "scope.passage.status" in prompt
    assert "excerpt from a novel" in prompt
    assert '"completion_status": "excerpt"' in prompt
    assert slot["slot_id"] not in prompt
    assert slot["state"] not in prompt
    assert "expected_verdict" not in prompt


def test_contract_and_corpus_drift_fail_closed(monkeypatch):
    s = load_study()
    original_contract = s.load_contract()
    altered_contract = deepcopy(original_contract)
    altered_contract["geometry"]["slots_exact"] = 59
    monkeypatch.setattr(s, "load_contract", lambda: altered_contract)
    with pytest.raises(ValueError, match="Study geometry drifted"):
        s.verify_package()
    altered_corpus = deepcopy(s.load_corpus())
    altered_corpus["artifacts"][0]["state"] = "other"
    with pytest.raises(ValueError, match="Artifact matrix drifted"):
        s.verify_corpus(altered_corpus)
    altered_contract = deepcopy(original_contract)
    altered_contract["portfolio_binding"]["leaf_findings"][s.LEAVES[0]] = altered_contract["portfolio_binding"]["finding_ids"][1]
    monkeypatch.setattr(s, "load_contract", lambda: altered_contract)
    with pytest.raises(ValueError, match="S2 portfolio boundary drifted"):
        s.verify_package()
    altered_contract = deepcopy(original_contract)
    altered_contract["screen"]["expected_labels_provider_facing"] = True
    monkeypatch.setattr(s, "load_contract", lambda: altered_contract)
    with pytest.raises(ValueError, match="Production screen binding drifted"):
        s.verify_package()
    altered_contract = deepcopy(original_contract)
    altered_contract["state_invariant"]["material_failure"]["rule"] = "changed"
    monkeypatch.setattr(s, "load_contract", lambda: altered_contract)
    with pytest.raises(ValueError, match="Scope invariant drifted"):
        s.verify_package()
    altered_fixture = deepcopy(s.FIXTURE_CONTRACTS)
    altered_fixture[(s.LEAVES[0], "localized_issue")]["completion_status"] = "excerpt"
    monkeypatch.setattr(s, "FIXTURE_CONTRACTS", altered_fixture)
    with pytest.raises(ValueError, match="Fixture completion-status regime drifted"):
        s.verify_corpus(s.load_corpus())


def test_historical_runtime_snapshot_rejects_a_mutated_declared_registry_file():
    s = load_study()
    path = s._historical_runtime_root / "registry" / "question_index.jsonl"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(ValueError, match="mutated"):
            s.sha256_file(path)
    finally:
        path.write_bytes(original)


def test_historical_runtime_rejects_an_unavailable_declared_digest_without_relabeling_bytes(tmp_path: Path):
    path = tmp_path / "runtime.txt"
    original = b"historical bytes\n"
    path.write_bytes(original)
    with pytest.raises(ValueError, match="binding is unavailable"):
        historical_runtime._normalize_declared_bytes(path, "0" * 64)
    assert path.read_bytes() == original


def test_historical_runtime_restores_declared_mixed_eol_bytes_only_when_the_exact_hash_matches(tmp_path: Path):
    path = tmp_path / "runtime.txt"
    frozen = b"one\r\ntwo\nthree\r\n"
    path.write_bytes(b"one\ntwo\nthree\n")
    historical_runtime._normalize_declared_bytes(
        path,
        historical_runtime.hashlib.sha256(frozen).hexdigest(),
        candidate_payloads=(frozen,),
    )
    assert path.read_bytes() == frozen


def test_provider_free_command_surface_and_public_privacy_boundary():
    s = load_study()
    dry = historical_runtime.run_cli(s, ROOT / "run.py", "--dry-run")
    rendered = historical_runtime.run_cli(s, ROOT / "run.py", "--render-plan")
    assert dry.returncode == rendered.returncode == 0
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    assert len(json.loads(rendered.stdout)["rendered_slots"]) == 60
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "api_key", "session_id")
    for path in ROOT.iterdir():
        if path.suffix in {".py", ".json", ".md"}:
            value = path.read_text(encoding="utf-8")
            assert all(fragment not in value for fragment in forbidden)
    source = (ROOT / "run.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "--execute" not in source
