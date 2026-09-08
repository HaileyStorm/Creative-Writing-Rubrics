from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/schema_recovery.py"
FREEZE_SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/grok_selection_freeze.py"
LOCAL_PROPOSAL = Path(r"C:\Users\Haile\Documents\cwr-wpb-0843-schema-recovery-proposal-20260907-r1")
LOCAL_SOURCE_CELL = Path(r"C:\Users\Haile\Documents\cwr-wpb-grok-recovery-20260907-r3\cells\wpb-pair-wpb-en-0843")


def load():
    spec = importlib.util.spec_from_file_location("wpb_schema_recovery", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_freeze():
    spec = importlib.util.spec_from_file_location("wpb_grok_selection_freeze_materializer_test", FREEZE_SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def synthetic_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = load()
    families = ("core", "craft", "form")
    schema = {
        "type": "object",
        "required": ["A", "B"],
        "additionalProperties": False,
        "properties": {"A": {"$ref": "#/definitions/side"}, "B": {"$ref": "#/definitions/side"}, "observed_winner": {"enum": ["A", "B", "TIE"]}},
        "definitions": {"side": {"type": "object", "required": ["scores", "coverage", "evidence"], "additionalProperties": False, "properties": {
            "scores": {"type": "object", "required": list(families), "additionalProperties": False, "properties": {family: {"type": "integer", "minimum": 1, "maximum": 5} for family in families}},
            "coverage": {"type": "object", "required": list(families), "additionalProperties": False, "properties": {family: {"enum": ["assessed", "limited", "not_assessable"]} for family in families}},
            "evidence": {"type": "object", "required": list(families), "additionalProperties": False, "properties": {family: {"type": "string", "minLength": 1, "maxLength": 180} for family in families}},
        }}},
    }
    original = {
        "A": {"scores": {"core": 4, "craft": 3, "form": 2}, "coverage": {"core": "assessed", "craft": "assessed", "form": "assessed"}, "evidence": {"core": "a" * 182, "craft": "a craft note", "form": "a form note"}},
        "B": {"scores": {"core": 5, "craft": 4, "form": 3}, "coverage": {"core": "assessed", "craft": "assessed", "form": "assessed"}, "evidence": {"core": "b core note", "craft": "b" * 183, "form": "b form note"}},
        "observed_winner": "B",
    }
    projected = copy.deepcopy(original)
    projected["A"]["evidence"]["core"] = projected["A"]["evidence"]["core"][:180]
    projected["B"]["evidence"]["craft"] = projected["B"]["evidence"]["craft"][:180]
    proposal, source = tmp_path / "proposal", tmp_path / "source"
    original_raw = write_json(proposal / "original-agent-message.json", original)
    projected_raw = write_json(proposal / "projected-agent-message.json", projected)
    schema_raw = write_json(proposal / "response-schema.json", schema)
    write_json(source / "response-schema.json", schema)
    outcome = {
        "failure": {"account_class": "subscription", "category": "validation_error", "code": "validation_structured_output_error", "detail": "Grok reported a structured-output validation failure", "incident_key": value.INCIDENT_KEY, "provider": "xai_grok_build", "provider_error_type": "GrokBuildValidationFailure", "revocation": "host_revoked_and_local_projected", "route_epoch_hash": "413e2c03957c934e06c06d32a6779349e127b25115fb00fbd65c4df1ea3582d7", "schema_version": 1, "status": None},
        "result": None,
        "state": "ambiguous",
    }
    attempt = {"cell_id": value.CELL_ID, "schema_sha256": value.sha256(schema_raw), "session_id_hash": "fc8b280d0d33e520f656dad0c0a674bf0cb6a4ca05ce313a10ce3caaee9c3ac7"}
    outcome_raw, attempt_raw = write_json(source / "outcome.json", outcome), write_json(source / "attempt.json", attempt)
    write_json(source / "prepared.json", {"cell_id": value.CELL_ID, "kind": "unstarted", "payload_sha256": "a" * 64})
    monkeypatch.setattr(value, "ORIGINAL_MESSAGE_SHA256", value.sha256(original_raw))
    monkeypatch.setattr(value, "PROJECTED_MESSAGE_SHA256", value.sha256(projected_raw))
    monkeypatch.setattr(value, "ORIGINAL_MESSAGE_BYTES", len(original_raw))
    monkeypatch.setattr(value, "PROJECTED_MESSAGE_BYTES", len(projected_raw))
    monkeypatch.setattr(value, "SCHEMA_SHA256", value.sha256(schema_raw))
    monkeypatch.setattr(value, "OUTCOME_SHA256", value.sha256(outcome_raw))
    monkeypatch.setattr(value, "ATTEMPT_SHA256", value.sha256(attempt_raw))
    return value, proposal, source


def owner_adoption(value, candidate: dict) -> dict:
    return {
        "format_version": 1, "kind": "wpb0843_schema_projection_owner_adoption", "cell_id": value.CELL_ID,
        "decision": "owner_adopts_local_session_schema_projection_only", "decision_at_utc": "2026-09-07T16:42:00Z",
        "adoption_candidate_sha256": value.sha256(candidate), "bindings": candidate["bindings"], "scope": "no_new_0843_provider_attempt",
        "native_cli_envelope_or_request_id_limitation": "accepted_no_cli_envelope_or_request_id_binding",
        "authorizes_new_0843_provider_attempt": False, "authorizes_native_admission": False, "authorizes_result_promotion": False,
    }


def test_synthetic_candidate_enforces_schema_core_and_exact_two_field_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, proposal, source = synthetic_roots(tmp_path, monkeypatch)
    verified = value.verify_candidate(proposal_root=proposal, source_cell_root=source)
    monkeypatch.setattr(value, "VERIFIED_CANDIDATE_SHA256", value.sha256(verified))
    candidate = value.prepare_adoption_candidate(verified=verified)
    assert verified["message"]["frozen_core"] == {"commit": value.CORE_COMMIT, "sha256": value.CORE_SHA256, "response_valid": True}
    assert verified["message"]["full_field_diff"] == [
        {"path": "A.evidence.core", "original_characters": 182, "projected_characters": 180, "operation": "prefix_truncate_to_schema_max_length"},
        {"path": "B.evidence.craft", "original_characters": 183, "projected_characters": 180, "operation": "prefix_truncate_to_schema_max_length"},
    ]
    assert candidate["status"] == "awaiting_new_explicit_owner_adoption"


def test_synthetic_candidate_rejects_any_change_outside_the_two_exact_prefix_truncations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, proposal, source = synthetic_roots(tmp_path, monkeypatch)
    projected_path = proposal / "projected-agent-message.json"
    projected = json.loads(projected_path.read_text(encoding="utf-8"))
    projected["A"]["scores"]["core"] = 5
    projected_path.write_text(json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="projected agent message (byte length|hash) drifted"):
        value.verify_candidate(proposal_root=proposal, source_cell_root=source)


def test_synthetic_adoption_rejects_prior_rearm_or_any_authority_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, proposal, source = synthetic_roots(tmp_path, monkeypatch)
    verified = value.verify_candidate(proposal_root=proposal, source_cell_root=source)
    monkeypatch.setattr(value, "VERIFIED_CANDIDATE_SHA256", value.sha256(verified))
    candidate = value.prepare_adoption_candidate(verified=verified)
    stale = owner_adoption(value, candidate)
    stale["decision_at_utc"] = "2026-09-07T16:41:54Z"
    with pytest.raises(ValueError, match="post-incident"):
        value.validate_adoption(adoption=stale, candidate=candidate)
    expanded = owner_adoption(value, candidate)
    expanded["authorizes_native_admission"] = True
    with pytest.raises(ValueError, match="local-session recovery ceiling"):
        value.validate_adoption(adoption=expanded, candidate=candidate)
    old_rearm = copy.deepcopy(candidate)
    old_rearm["bindings"]["outcome_sha256"] = "699fbb473ee3b781607a12af388b57538f2ca973c60abb775ed56adfeed08cfd"
    invalid = owner_adoption(value, old_rearm)
    with pytest.raises(ValueError, match="candidate"):
        value.validate_adoption(adoption=invalid, candidate=old_rearm)


def test_materializer_and_marker_retain_the_local_session_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, proposal, source = synthetic_roots(tmp_path, monkeypatch)
    verified = value.verify_candidate(proposal_root=proposal, source_cell_root=source)
    monkeypatch.setattr(value, "VERIFIED_CANDIDATE_SHA256", value.sha256(verified))
    candidate = value.prepare_adoption_candidate(verified=verified)
    adoption_path = tmp_path / "adoption.json"
    adoption_raw = write_json(adoption_path, owner_adoption(value, candidate))
    materialized = value.materialize_adopted_projection(
        adoption_path=adoption_path, expected_adoption_sha256=value.sha256(adoption_raw),
        proposal_root=proposal, source_cell_root=source, expected_payload_sha256="a" * 64,
    )
    core = value._load_frozen_core()
    assert materialized["measurement"]["measurement_provenance"] == {
        "endpoint": "grok", "cell_id": value.CELL_ID, "payload_sha256": "a" * 64,
        "parsed_response_sha256": value.sha256(core.canonical(materialized["measurement"]["response"])),
    }
    assert materialized["provenance"]["classification"] == "local_session_schema_recovered"
    assert materialized["marker"]["native_admission_permitted"] is False
    marker_path = tmp_path / "marker.json"
    marker_raw = write_json(marker_path, materialized["marker"])
    assert value.verify_adopted_projection_marker(
        marker_path=marker_path, expected_marker_sha256=value.sha256(marker_raw),
        adoption_path=adoption_path, expected_adoption_sha256=value.sha256(adoption_raw),
        proposal_root=proposal, source_cell_root=source, expected_payload_sha256="a" * 64,
    ) == materialized


def test_materializer_measurement_passes_the_freeze_validator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, proposal, source = synthetic_roots(tmp_path, monkeypatch)
    verified = value.verify_candidate(proposal_root=proposal, source_cell_root=source)
    monkeypatch.setattr(value, "VERIFIED_CANDIDATE_SHA256", value.sha256(verified))
    adoption_path = tmp_path / "adoption.json"
    adoption_raw = write_json(adoption_path, owner_adoption(value, value.prepare_adoption_candidate(verified=verified)))
    materialized = value.materialize_adopted_projection(
        adoption_path=adoption_path, expected_adoption_sha256=value.sha256(adoption_raw),
        proposal_root=proposal, source_cell_root=source, expected_payload_sha256="a" * 64,
    )
    freeze, core = load_freeze(), value._load_frozen_core()
    identifiers = [f"cell-{number:03d}" for number in range(128)] + [value.CELL_ID]
    payloads = {cell_id: ("a" * 64 if cell_id == value.CELL_ID else f"{number:064x}")
                for number, cell_id in enumerate(identifiers)}
    response = materialized["measurement"]["response"]
    measurements = [
        (materialized["measurement"] if cell_id == value.CELL_ID else {
            "endpoint": "grok", "cell_id": cell_id, "payload_sha256": payloads[cell_id],
            "measurement_provenance": {
                "endpoint": "grok", "cell_id": cell_id, "payload_sha256": payloads[cell_id],
                "parsed_response_sha256": value.sha256(core.canonical(response)),
            },
            "response": response,
        })
        for cell_id in identifiers
    ]
    rows = {cell_id: {"payload_sha256": payloads[cell_id]} for cell_id in identifiers}

    def analyze(_root, items, _profile):
        by_cell = {item["cell_id"]: item for item in items}
        ordered = [{key: by_cell[cell_id][key] for key in ("endpoint", "cell_id", "payload_sha256", "measurement_provenance")}
                   for cell_id in sorted(by_cell)]
        return {"native_admission": "not_claimed", "mae": "not_applicable_pairwise_preference_target",
                "ordered_measurement_commitment_sha256": core.sha256(ordered)}

    monkeypatch.setattr(core, "analyze", analyze)
    assert freeze._validate_measurements(core, tmp_path, "s" * 64, rows, measurements)[-1] == materialized["measurement"]


@pytest.mark.skipif(not LOCAL_PROPOSAL.is_dir() or not LOCAL_SOURCE_CELL.is_dir(), reason="local 0843 evidence roots are not available")
def test_real_local_evidence_is_read_only_and_matches_production_pins() -> None:
    value = load()
    proposal_before, source_before = snapshot(LOCAL_PROPOSAL), snapshot(LOCAL_SOURCE_CELL)
    verified = value.verify_candidate(proposal_root=LOCAL_PROPOSAL, source_cell_root=LOCAL_SOURCE_CELL)
    assert value.sha256(verified) == value.VERIFIED_CANDIDATE_SHA256
    assert proposal_before == snapshot(LOCAL_PROPOSAL)
    assert source_before == snapshot(LOCAL_SOURCE_CELL)
