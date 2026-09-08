"""Synthetic filesystem/semantic checks; no private judgments or provider calls."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/grok70_schema_recovery.py"


def load():
    spec = importlib.util.spec_from_file_location("grok70_recovery_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def semantic_fixture(*, question_ids=None, quote=None):
    ids = list(question_ids) if question_ids is not None else [f"synthetic-question-{number}" for number in range(8)]
    assert len(ids) == 8
    quote = "A" * 543 if quote is None else quote
    original = {"verdicts": [{"question_id": item, "verdict": "YES", "confidence": 0.5, "note": "Synthetic fixture.",
                               "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote[:1], "summary": None}]}
                              for item in ids]}
    original["verdicts"][3]["evidence"][0]["exact_quote"] = quote
    derivative = copy.deepcopy(original)
    derivative["verdicts"][3]["evidence"][0]["exact_quote"] = quote[:500]
    evidence_schema = {"type": "object", "additionalProperties": False,
                       "required": ["kind", "reference", "exact_quote", "summary"],
                       "properties": {"kind": {"enum": ["exact_quote", "summary"]}, "reference": {"type": "string"},
                                      "exact_quote": {"type": ["string", "null"], "maxLength": 500},
                                      "summary": {"type": ["string", "null"], "maxLength": 500}}}
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
              "required": ["verdicts"], "properties": {"verdicts": {"type": "array", "minItems": 8, "items": {
                  "type": "object", "additionalProperties": False,
                  "required": ["question_id", "verdict", "confidence", "evidence", "note"],
                  "properties": {"question_id": {"type": "string", "enum": ids}, "verdict": {"enum": ["YES", "NO"]},
                                 "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "note": {"type": "string"},
                                 "evidence": {"type": "array", "minItems": 1, "items": evidence_schema}}}}}}
    return original, derivative, schema, quote + "\n"


def session_bytes(original_raw):
    message = {"method": "session/update", "params": {"sessionId": "synthetic-session-70", "update": {
        "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": original_raw.decode("utf-8")}}}}
    return canonical(message) + b"\n"


def make_fixture(tmp_path, *, question_ids=None, response_schema=None, response_schema_raw=None):
    """Return synthetic adopted inputs; use internal reader with outcome_sha256.

    The public wrapper's fixed real outcome anchor is tested independently; it
    is never replaced or monkeypatched to make these synthetic files pass.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    proposal = tmp_path / "proposal"
    proposal.mkdir()
    original, derivative, schema, source = semantic_fixture(question_ids=question_ids)
    if response_schema is not None:
        schema = copy.deepcopy(response_schema)
    original_raw, derivative_raw, schema_raw, source_raw = canonical(original), canonical(derivative), canonical(schema), source.encode()
    if response_schema_raw is not None:
        assert isinstance(response_schema_raw, bytes)
        assert json.loads(response_schema_raw) == schema
        schema_raw = response_schema_raw
    updates_raw = session_bytes(original_raw)
    source_path, updates_path = tmp_path / "synthetic-story.txt", tmp_path / "updates.jsonl"
    source_path.write_bytes(source_raw); updates_path.write_bytes(updates_raw)
    source_binding = {"bytes": len(source_raw), "relative_path": "inputs/synthetic-story.txt", "sha256": sha(source_raw)}
    extraction = {"agent_message_count": 1, "container_bytes": len(updates_raw), "container_sha256": sha(updates_raw),
                  "extracted_bytes": len(original_raw), "original_agent_message_sha256": sha(original_raw),
                  "rule": "exactly_one_agent_message_chunk_utf8_text"}
    commitments = {
        "authority": {"admission_authority": False, "native_mutation_authority": False, "owner_adoption_required": True,
                      "provider_contact_authority": False, "resend_authority": False},
        "ceiling": {"native_cli_envelope_request_id_binding": "missing", "promotable_as_accepted_result": False,
                    "reason": "native CLI envelope was not retained after structured-output validation error"},
        "derivative_agent_message": {"bytes": len(derivative_raw), "semantic_delta_path": "verdicts[3].evidence[0].exact_quote",
                                     "sha256": sha(derivative_raw), "transformation": "first_500_unicode_codepoints_only"},
        "kind": "grok70_schema_recovery_proposal_commitments",
        "original_agent_message": {"bytes": len(original_raw), "extraction": extraction["rule"], "sha256": sha(original_raw),
                                   "source_updates_container_sha256": sha(updates_raw)},
        "response_schema": {"bytes": len(schema_raw), "sha256": sha(schema_raw)},
        "schema_validation": {"derivative_error_count": 0, "draft": "2020-12", "maximum_codepoints": 500,
                              "original_error_count": 1, "original_error_path": "verdicts[3].evidence[0].exact_quote",
                              "original_length_codepoints": 543}, "schema_version": 1,
        "source_substring_proof": {"derivative_quote_is_substring": True, "original_quote_is_substring": True,
                                   "source_relative_path": source_binding["relative_path"], "source_sha256": sha(source_raw)},
        "status": "proposal_only",
    }
    payloads = {"PROPOSAL.md": b"Synthetic quote-only recovery proposal; never provider or native authority.",
                "commitments.json": canonical(commitments), "original-agent-message.json": original_raw,
                "derivative-agent-message.json": derivative_raw, "response-schema.json": schema_raw}
    for name, raw in payloads.items(): (proposal / name).write_bytes(raw)
    file_hashes = {name: sha(raw) for name, raw in payloads.items()}
    checks = {"derivative_codepoints": 500, "derivative_schema_error_count": 0, "derivative_source_substring": True,
              "exact_semantic_delta_path": "verdicts[3].evidence[0].exact_quote", "first_500_codepoints_exact": True,
              "original_codepoints": 543, "original_schema_error_count": 1,
              "original_schema_error_path": "verdicts[3].evidence[0].exact_quote", "original_source_substring": True,
              "semantic_diff_count": 1}
    review = {"authority": {key: False for key in ("admission_authority", "execution_authority", "native_mutation_authority",
              "owner_adoption", "provider_contact_authority", "resend_authority", "study_admission")}, "checks": checks,
              "evidence_ceiling": {"native_cli_envelope_request_id_binding": "missing", "promotable_as_accepted_result": False,
                                   "recovery_class": "candidate_only"},
              "evidence_paths": {"source_input": str(source_path), "source_updates_container": str(updates_path)},
              "evidence_class": "independent_grok70_schema_recovery_candidate_review_v1", "extraction": extraction,
              "proposal_files": file_hashes, "schema_version": 1, "source_input": source_binding}
    review_path = tmp_path / "review.json"; review_path.write_bytes(canonical(review))
    adoption = {"decision": "adopt_exact_grok70_quote_repair", "implementation_admission_status": "pending_reviewed_integration",
                "independent_review": {"path": str(review_path), "sha256": sha(review_path.read_bytes())},
                "owner_decision": {"explicit": True, "recorded_at": "2026-09-08T00:00:00Z", "reference": "Synthetic owner decision"},
                "proposal_files_sha256": file_hashes, "proposal_root": str(proposal), "schema_version": 1,
                "scope": {"logical_request_ordinal": 70, "native_cli_envelope_request_id_binding": "missing",
                          "ordinary_native_admission": False, "original_preserved": True, "provider_contact_authority": False,
                          "resend_authority": False, "transformation": "verdicts[3].evidence[0].exact_quote first 500 unicode codepoints only",
                          "wpb_0843_adoption": False}}
    adoption_path = tmp_path / "adoption.json"; adoption_path.write_bytes(canonical(adoption))
    outcome = {"state": "ambiguous", "result": None, "failure": {"category": "validation_error",
               "code": "validation_structured_output_error", "provider_error_type": "GrokBuildValidationFailure"}}
    outcome_path = tmp_path / "outcome.json"; outcome_path.write_bytes(canonical(outcome))
    args = {"adoption_path": adoption_path, "expected_adoption_sha256": sha(adoption_path.read_bytes()), "review_path": review_path,
            "source_path": source_path, "updates_path": updates_path, "terminal_outcome_path": outcome_path}
    return SimpleNamespace(proposal_root=proposal, args=args, outcome_sha256=sha(outcome_path.read_bytes()),
                           original=original, derivative=derivative, schema=schema, source=source, adoption=adoption,
                           review=review, commitments=commitments)


def read_synthetic(subject, fixture):
    return subject._recover_judgment(fixture.proposal_root, **fixture.args, terminal_outcome_sha256=fixture.outcome_sha256)


def test_synthetic_adopted_reader_is_deterministic_and_preserves_original(tmp_path):
    subject = load(); fixture = make_fixture(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = read_synthetic(subject, fixture)
    assert result == read_synthetic(subject, fixture)
    assert result["judgment"] == fixture.derivative
    provenance = result["study_recovered_quote_repair"]
    assert provenance["logical_request_ordinal"] == 70 and provenance["native_admission"] is False
    assert provenance["native_cli_envelope_request_id_binding"] == "missing"
    assert provenance["provider_calls"] == 0 and provenance["resend_authority"] is False
    assert provenance["owner_adopted_at"] == "2026-09-08T00:00:00Z"
    assert provenance["checks"]["semantic_diff_count"] == 1
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}


def test_public_wrapper_keeps_fixed_terminal_binding_and_no_override(tmp_path):
    subject = load(); fixture = make_fixture(tmp_path)
    with pytest.raises(ValueError, match="terminal outcome bytes differ"):
        subject.recover_judgment(fixture.proposal_root, **fixture.args)
    with pytest.raises(TypeError):
        subject.recover_judgment(fixture.proposal_root, **fixture.args, terminal_outcome_sha256=fixture.outcome_sha256)


def test_fixture_binds_supplied_response_schema_through_the_full_chain(tmp_path):
    subject = load()
    _, _, schema, _ = semantic_fixture()
    schema["properties"]["verdicts"]["items"]["properties"]["confidence"]["minimum"] = 0.1
    fixture = make_fixture(tmp_path, response_schema=schema)
    result = read_synthetic(subject, fixture)
    assert result["study_recovered_quote_repair"]["response_schema_sha256"] == sha(canonical(schema))


def test_fixture_preserves_supplied_schema_bytes_and_rejects_mismatched_content(tmp_path):
    subject = load()
    _, _, schema, _ = semantic_fixture()
    raw = (json.dumps(schema, indent=2) + "\n").encode()
    fixture = make_fixture(tmp_path / "valid", response_schema=schema, response_schema_raw=raw)
    result = read_synthetic(subject, fixture)
    assert (fixture.proposal_root / "response-schema.json").read_bytes() == raw
    assert result["study_recovered_quote_repair"]["response_schema_sha256"] == sha(raw)
    with pytest.raises(AssertionError):
        make_fixture(tmp_path / "invalid", response_schema=schema, response_schema_raw=b"{}")


def test_unicode_codepoints_are_not_utf8_bytes():
    subject = load()
    original, derivative, schema, source = semantic_fixture(quote="🐦" * 500 + "Z" * 43)
    result = subject._semantic_proof(original, derivative, schema, source)
    assert result["derivative_codepoints"] == 500
    assert len(subject._quote(derivative).encode()) == 2000


@pytest.mark.parametrize("kind", ["other_verdict", "other_quote", "extra_field", "not_prefix", "wrong_length", "source",
                                  "original_zero_errors", "original_multiple_errors", "derivative_schema_error", "remote_ref"])
def test_rejects_unauthorized_semantic_and_schema_changes(kind):
    subject = load(); original, derivative, schema, source = semantic_fixture()
    if kind == "other_verdict": derivative["verdicts"][0]["verdict"] = "NO"
    elif kind == "other_quote": derivative["verdicts"][0]["evidence"][0]["exact_quote"] = "AA"
    elif kind == "extra_field": derivative["extra"] = True
    elif kind == "not_prefix": derivative["verdicts"][3]["evidence"][0]["exact_quote"] = "B" * 500
    elif kind == "wrong_length": derivative["verdicts"][3]["evidence"][0]["exact_quote"] = "A" * 499
    elif kind == "source": source = "unrelated"
    elif kind == "remote_ref": schema["$ref"] = "https://example.invalid/no-network"
    else:
        quote_schema = schema["properties"]["verdicts"]["items"]["properties"]["evidence"]["items"]["properties"]["exact_quote"]
        if kind == "original_zero_errors": quote_schema["maxLength"] = 600
        elif kind == "derivative_schema_error": quote_schema["maxLength"] = 499
        else:
            original["verdicts"][0]["confidence"] = 2
            derivative["verdicts"][0]["confidence"] = 2
    with pytest.raises(ValueError): subject._semantic_proof(original, derivative, schema, source)


@pytest.mark.parametrize("name", ["PROPOSAL.md", "commitments.json", "original-agent-message.json",
                                  "derivative-agent-message.json", "response-schema.json", "source_path", "updates_path", "review_path"])
def test_rejects_hash_drift_without_rebinding_authority(tmp_path, name):
    subject = load(); fixture = make_fixture(tmp_path)
    path = fixture.args[name] if name in fixture.args else fixture.proposal_root / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bytes differ"): read_synthetic(subject, fixture)


@pytest.mark.parametrize("kind", ["owner", "ordinal", "native", "resend", "scope_extra", "review_hash", "decision", "missing_field"])
def test_rejects_invalid_adoption_even_with_a_matching_external_digest(tmp_path, kind):
    subject = load(); fixture = make_fixture(tmp_path)
    value = fixture.adoption
    if kind == "owner": value["owner_decision"]["explicit"] = False
    elif kind == "ordinal": value["scope"]["logical_request_ordinal"] = [70, 71]
    elif kind == "native": value["scope"]["ordinary_native_admission"] = True
    elif kind == "resend": value["scope"]["resend_authority"] = True
    elif kind == "scope_extra": value["scope"]["also_ordinal"] = 71
    elif kind == "review_hash": value["independent_review"]["sha256"] = "0" * 64
    elif kind == "decision": value["decision"] = "proposed"
    else: value.pop("owner_decision")
    raw = canonical(value); fixture.args["adoption_path"].write_bytes(raw)
    fixture.args["expected_adoption_sha256"] = sha(raw)
    with pytest.raises(ValueError): read_synthetic(subject, fixture)


@pytest.mark.parametrize("kind", ["second_message", "different_session", "nontext", "blank_line", "duplicate_key"])
def test_session_extraction_rejects_ambiguity(kind):
    subject = load(); raw = session_bytes(b'{"synthetic":true}')
    event = json.loads(raw)
    if kind == "second_message": raw += raw
    elif kind == "different_session":
        event["params"]["sessionId"] = "another-session"
        event["params"]["update"]["sessionUpdate"] = "reasoning_chunk"
        raw += canonical(event) + b"\n"
    elif kind == "nontext":
        event["params"]["update"]["content"]["type"] = "image"
        raw = canonical(event) + b"\n"
    elif kind == "blank_line": raw += b"\n"
    else: raw = raw.replace(b'"type":"text"', b'"type":"text","type":"text"')
    with pytest.raises(ValueError): subject._extract_original(raw)


def test_commitments_cannot_weaken_the_adopted_rule(tmp_path):
    subject = load(); fixture = make_fixture(tmp_path)
    fixture.commitments["schema_validation"]["maximum_codepoints"] = 501
    with pytest.raises(ValueError, match="commitments differ"):
        subject._verify_commitments(fixture.commitments, canonical(fixture.original), canonical(fixture.derivative),
                                    canonical(fixture.schema), fixture.review["source_input"], fixture.review["extraction"])


def test_untrusted_adoption_hash_and_duplicate_json_are_rejected(tmp_path):
    subject = load(); fixture = make_fixture(tmp_path)
    fixture.args["expected_adoption_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Owner adoption bytes differ"): read_synthetic(subject, fixture)
    with pytest.raises(ValueError): subject._json(b'{"owner":true,"owner":false}', "Fixture")
    with pytest.raises(ValueError): subject._json(b'{"value":NaN}', "Fixture")
