from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-full-leaf-structural-audit-v1"


def _module():
    spec = importlib.util.spec_from_file_location("full_leaf_structural_audit_v1", ROOT / "generate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ingest_module():
    spec = importlib.util.spec_from_file_location("full_leaf_structural_audit_ingest_v1", ROOT / "ingest.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _jsonl(name: str):
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines() if line]


def test_regeneration_is_exact_and_manifest_binds_every_nonmanifest_package_file():
    module = _module()
    module.run(check=True)
    manifest = _json("manifest.json")
    assert set(manifest["files"]) == {
        "README.md",
        "audit-contract.json",
        "finding.schema.json",
        "findings.jsonl",
        "generate.py",
        "ingest.py",
        "leaf-audit.jsonl",
        "leaf-audit.schema.json",
        "sol-review.schema.json",
        "sol-triage.jsonl",
        "sol-triage-summary.json",
        "summary.json",
    }
    for name, record in manifest["files"].items():
        payload = (ROOT / name).read_bytes()
        assert record == {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def test_leaf_inventory_is_exact_sorted_and_parity_matches_the_frozen_registry():
    leaves = _jsonl("leaf-audit.jsonl")
    registry = _json("../../registry/all_modules.json")
    expected = []

    def walk(nodes):
        for node in nodes:
            if node["type"] == "question":
                expected.append((node["id"], node["criterion_key"]))
            else:
                walk(node["children"])

    for record in registry:
        walk(record["tree"])
    assert len(leaves) == 2145
    assert [(row["ordinal"], row["qid"]) for row in leaves] == list(enumerate(sorted(row["qid"] for row in leaves), start=1))
    assert [(row["qid"], row["criterion_key"]) for row in leaves] == sorted(expected)
    assert all(row["format"] == "hbq-full-leaf-structural-audit-row-v1" for row in leaves)
    assert all(row["ownership"]["criterion_key_unique"] for row in leaves)
    assert all(row["provenance"]["source_inventory_entry"] is None or row["provenance"]["source_inventory_entry"]["module_id"] == row["owner"]["module_id"] for row in leaves)


def test_findings_use_stable_canonical_ids_and_never_select_a_remedy():
    module = _module()
    findings = _jsonl("findings.jsonl")
    allowed = {"none", "eligible_static_signal", "bound_empirical_signal"}
    assert {finding["kind"] for finding in findings} == {"lexical_overlap", "scope_binding_review", "polarity_change"}
    for finding in findings:
        identity = {"subjects": sorted(finding["subjects"]), "rule": finding["rule"]}
        assert finding["finding_id"] == module.sha256_bytes(module.canonical_json(identity))
        assert finding["first_remedy"]["selection"] in allowed
        assert finding["first_remedy"]["selected"] is None
    assert all(finding["kind"] != "lexical_overlap" or finding["first_remedy"]["selection"] == "none" for finding in findings)


def test_generated_rows_and_findings_conform_to_their_public_schemas():
    module = _module()
    contract = _json("audit-contract.json")
    leaf_validator = Draft202012Validator(_json("leaf-audit.schema.json"))
    finding_validator = Draft202012Validator(_json("finding.schema.json"))
    sol_validator = Draft202012Validator(_json("sol-review.schema.json"))
    for row in _jsonl("leaf-audit.jsonl"):
        assert not list(leaf_validator.iter_errors(row))
    for finding in _jsonl("findings.jsonl"):
        assert not list(finding_validator.iter_errors(finding))
    review = {
        "audit": "hbq-full-leaf-structural-audit-v1", "finding_id": _jsonl("findings.jsonl")[0]["finding_id"], "reviewer": "Sol", "decision": "needs_empirical_test",
        "audit_input_hashes": contract["frozen_input_hashes"], "evidence_hashes": [], "evidence_scope": "sealed development study", "rationale": "No immutable empirical evidence is declared in this static package."
    }
    assert not list(sol_validator.iter_errors(review))
    module.validate_review_record(review, contract)
    degenerate_leaf = deepcopy(_jsonl("leaf-audit.jsonl")[0]); degenerate_leaf["owner"].pop("module_id")
    assert list(leaf_validator.iter_errors(degenerate_leaf))
    degenerate_finding = deepcopy(_jsonl("findings.jsonl")[0]); degenerate_finding["first_remedy"]["selection"] = "automatic"
    assert list(finding_validator.iter_errors(degenerate_finding))
    degenerate_review = deepcopy(review); degenerate_review["reviewer"] = " "
    assert list(sol_validator.iter_errors(degenerate_review))
    degenerate_review = deepcopy(review); degenerate_review["audit_input_hashes"].pop("registry/modules.aggregate")
    assert list(sol_validator.iter_errors(degenerate_review))
    empty_inventory = deepcopy(_jsonl("leaf-audit.jsonl")[0]); empty_inventory["provenance"]["source_inventory_entry"] = {}
    assert list(leaf_validator.iter_errors(empty_inventory))
    unknown_finding = deepcopy(review); unknown_finding["finding_id"] = "0" * 64
    with pytest.raises(ValueError, match="generated finding"):
        module.validate_review_record(unknown_finding, contract)
    unbound_proposal = deepcopy(review); unbound_proposal["decision"] = "propose_change"; unbound_proposal["evidence_hashes"] = ["a" * 64]
    assert not list(sol_validator.iter_errors(unbound_proposal))
    with pytest.raises(ValueError, match="declared immutable"):
        module.validate_review_record(unbound_proposal, contract)


def test_bound_sol_triage_is_complete_ordered_schema_valid_and_does_not_authorize_a_repair():
    module = _module()
    ingest = _ingest_module()
    contract = _json("audit-contract.json")
    findings = _jsonl("findings.jsonl")
    triage = _jsonl("sol-triage.jsonl")
    summary = _json("sol-triage-summary.json")
    validator = Draft202012Validator(_json("sol-review.schema.json"))
    assert len(triage) == len(findings) == 808
    assert [record["finding_id"] for record in triage] == [record["finding_id"] for record in findings]
    assert all(not list(validator.iter_errors(record)) for record in triage)
    assert all(record["reviewer"] == "GPT-5.6 Sol semantic triage" for record in triage)
    assert all(record["audit_input_hashes"] == contract["frozen_input_hashes"] for record in triage)
    assert all(record["evidence_hashes"] == [] for record in triage)
    assert all(record["decision"] != "propose_change" for record in triage)
    for record in triage:
        module.validate_review_record(record, contract)
    assert summary["status_counts"] == {"false_positive": 396, "first_remedy_experiment": 77, "intentional_specialization": 276, "watch": 59}
    assert summary["decision_counts"] == {"needs_empirical_test": 136, "no_change": 276, "propose_change": 0, "reject_candidate": 396}
    assert summary["input_commit"] == "59249fccadb256e00e9f70a064c65903f1f26e6e"
    assert summary["review_identity"] == contract["bound_semantic_triage"]["public_binding"]["review_identity"]
    assert summary["decision_binding"] == contract["bound_semantic_triage"]["decision_binding"]
    assert summary["bindings"]["audit_input_hashes"] == contract["frozen_input_hashes"]
    assert [item["record_count"] for item in summary["source_part_commitments"]] == [135, 135, 135, 135, 135, 133]
    assert all(len(item["sha256"]) == 64 for item in summary["source_part_commitments"])
    ingest.validate_published()


def test_no_source_triage_check_rejects_any_semantic_or_summary_binding_mutation():
    ingest = _ingest_module()
    contract = _json("audit-contract.json")
    triage = _jsonl("sol-triage.jsonl")
    summary = _json("sol-triage-summary.json")
    triage_bytes = (ROOT / "sol-triage.jsonl").read_bytes()
    summary_bytes = (ROOT / "sol-triage-summary.json").read_bytes()
    for field, replacement in (("rationale", "A changed rationale."), ("decision", "no_change"), ("evidence_scope", "findings-1-134")):
        changed = deepcopy(triage)
        changed[0][field] = replacement
        payload = b"".join(ingest.canonical_json(record) for record in changed)
        with pytest.raises(ValueError, match="record SHA-256 mismatch"):
            ingest.validate_published_bytes(payload, summary_bytes, contract)
    changed_summary = deepcopy(summary)
    changed_summary["review_identity"]["model"] = "unbound"
    with pytest.raises(ValueError, match="summary SHA-256 mismatch"):
        ingest.validate_published_bytes(triage_bytes, ingest.canonical_json(changed_summary), contract)
    changed_summary = deepcopy(summary)
    changed_summary["bindings"]["audit_input_hashes"]["registry/all_modules.json"] = "0" * 64
    with pytest.raises(ValueError, match="summary SHA-256 mismatch"):
        ingest.validate_published_bytes(triage_bytes, ingest.canonical_json(changed_summary), contract)
    changed_summary = deepcopy(summary)
    changed_summary["source_part_commitments"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="summary SHA-256 mismatch"):
        ingest.validate_published_bytes(triage_bytes, ingest.canonical_json(changed_summary), contract)


def test_frozen_hashes_are_lf_canonical_but_reject_content_drift_and_source_inventory_absence_is_explicit(tmp_path: Path):
    module = _module()
    contract = _json("audit-contract.json")
    assert contract["parent_revision"] == "8970e0903cbec50cf62dbbc9e22b1cb7988c988b"
    assert contract["input_canonicalization"] == "utf8_lf_replace_crlf"
    module.input_records(contract)
    assert module.canonical_input_bytes(b"one\r\ntwo\n") == b"one\ntwo\n"
    lf = tmp_path / "input-lf.json"; crlf = tmp_path / "input-crlf.json"; changed_bytes = tmp_path / "input-changed.json"
    lf.write_bytes(b'{"value":1}\n'); crlf.write_bytes(b'{"value":1}\r\n'); changed_bytes.write_bytes(b'{"value":2}\r\n')
    assert module.canonical_input_record(lf) == module.canonical_input_record(crlf)
    assert module.canonical_input_record(lf) != module.canonical_input_record(changed_bytes)
    changed = deepcopy(contract)
    changed["frozen_input_hashes"]["registry/all_modules.json"] = "0" * 64
    with pytest.raises(ValueError, match="Frozen input hash mismatch"):
        module.input_records(changed)
    summary = _json("summary.json")
    assert summary["counts"]["source_inventory_modules"] == 203
    assert summary["counts"]["source_inventory_absent_modules"] == 75
    assert summary["counts"]["source_inventory_leaves"] == 1594
    assert summary["counts"]["source_inventory_absent_leaves"] == 551


def test_owner_sentinels_preserve_stockness_and_density_boundaries():
    leaves = {row["qid"]: row for row in _jsonl("leaf-audit.jsonl")}
    assert leaves["core.freshness_and_non_genericness.no_default_metaphors"]["owner"]["module_id"] == "core.freshness_and_non_genericness"
    assert leaves["core.freshness_and_non_genericness.no_default_metaphors"]["owner"]["domains"] == ["freshness"]
    for qid in ("penalty.purple_prose.proportion", "penalty.purple_prose.fatigue"):
        assert leaves[qid]["owner"]["module_id"] == "penalty.purple_prose"
        assert leaves[qid]["owner"]["domains"] == ["penalty.purple_prose"]


def test_public_safety_rejects_paths_private_tokens_and_provider_fields(tmp_path: Path):
    module = _module()
    for name, content in (("windows.md", "C:\\Users\\someone\\private.txt\n"), ("unix.md", "/home/someone/private.txt\n"), ("token.md", "NOUS_API_KEY=value\n"), ("credential.md", "sk-abcdefghijklmnop\n"), ("private.md", "Palimpsest\n")):
        public = tmp_path / name
        public.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            module.public_safe([public])
    provider = tmp_path / "provider.json"
    provider.write_text('{"api_key":"x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Forbidden"):
        module.public_safe([provider])
    provider.write_text('{"provider_output":"x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Forbidden"):
        module.public_safe([provider])
