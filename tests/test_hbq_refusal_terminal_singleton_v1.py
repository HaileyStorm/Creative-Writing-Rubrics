from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "evaluation-results" / "hbq-refusal-terminal-singleton-v1" / "study.py"
README = STUDY.parent / "README.md"


def _study():
    specification = importlib.util.spec_from_file_location("hbq_refusal_terminal_singleton_v1", STUDY)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


ARCHIVED_OLD_RUNTIME = (
    "Archived provider-free injected runner mechanics require the frozen fb77e8a runtime; "
    "current runner and rubric bindings have advanced."
)


def _synthetic_gate_slots(study):
    """Build path-free rows for testing the current terminal-count gate only."""
    slots = []
    for scenario_id in study.SCENARIO_IDS:
        expected = study.EXPECTED[scenario_id]
        slots.append(
            {
                "scenario_id": scenario_id,
                "expected_terminal_class": expected[0],
                "observed_terminal_class": expected[0],
                "maximum_attempts": study.MAXIMUM_ATTEMPTS,
                "attempt_started_count": expected[1],
                "injected_attempt_count": expected[2],
                "remote_provider_call_count": expected[3],
                "accepted_response_count": expected[4],
                "rejected_retry_count": expected[5],
                "ambiguous_attempt_count": expected[6],
                "accepted_response_sha256": "a" * 64 if expected[4] else None,
                "rejected_chain_head_sha256": "b" * 64 if expected[5] else None,
                "resume_action": expected[7],
                "settlement_status": expected[8],
            }
        )
    return slots


@pytest.mark.skip(reason=ARCHIVED_OLD_RUNTIME)
def test_matrix_runs_through_runner_artifacts_and_passes_exact_terminal_counts():
    study = _study()
    result = study.run_matrix()
    assert result["gate"] == study.PASS
    assert result["logical_sample_count"] == 6
    assert result["injected_attempt_count"] == 9
    assert result["remote_provider_call_count"] == 0
    for slot in result["slots"]:
        expected = study.EXPECTED[slot["scenario_id"]]
        actual = (
            slot["observed_terminal_class"], slot["attempt_started_count"], slot["injected_attempt_count"],
            slot["remote_provider_call_count"], slot["accepted_response_count"], slot["rejected_retry_count"],
            slot["ambiguous_attempt_count"], slot["resume_action"], slot["settlement_status"],
        )
        assert actual == expected
        if slot["accepted_response_count"]:
            assert len(slot["accepted_response_sha256"]) == 64
        if slot["rejected_retry_count"]:
            assert len(slot["rejected_chain_head_sha256"]) == 64


@pytest.mark.skip(reason=ARCHIVED_OLD_RUNTIME)
def test_refusal_is_classified_from_frozen_rejected_content_not_a_fixture_signal():
    study = _study()
    fixture = json.loads(study.FIXTURES_PATH.read_text(encoding="utf-8"))
    refusal = fixture["scenarios"][1]
    assert "synthetic_terminal_signal" not in json.dumps(refusal)
    slot = study.evaluate_scenario(refusal)
    assert slot["observed_terminal_class"] == "refusal_deflection_exhausted"
    assert slot["accepted_response_count"] == 0
    assert slot["rejected_retry_count"] == 2


@pytest.mark.skip(reason=ARCHIVED_OLD_RUNTIME)
def test_nonretryable_and_ambiguous_poison_continuations_are_not_invoked():
    study = _study()
    fixture = json.loads(study.FIXTURES_PATH.read_text(encoding="utf-8"))
    nonretryable = study.evaluate_scenario(fixture["scenarios"][4])
    ambiguous = study.evaluate_scenario(fixture["scenarios"][5])
    assert nonretryable["attempt_started_count"] == 1
    assert nonretryable["resume_action"] == "stop_no_retry"
    assert ambiguous["attempt_started_count"] == 1
    assert ambiguous["resume_action"] == "hold_no_auto_resend"


@pytest.mark.parametrize("field", ["accepted_response_count", "rejected_retry_count", "ambiguous_attempt_count"])
def test_count_mutations_cannot_pass(field: str):
    study = _study()
    slots = copy.deepcopy(_synthetic_gate_slots(study))
    slots[0][field] += 1
    assert study._gate(slots) == study.NO_GO


def test_missing_slot_is_incomplete_and_path_free_replay_is_deterministic():
    study = _study()
    first, second = _synthetic_gate_slots(study), _synthetic_gate_slots(study)
    assert first == second
    assert study._gate(first[:-1]) == study.INCOMPLETE
    serialized = json.dumps(first, sort_keys=True)
    assert str(ROOT) not in serialized
    assert study.ARTIFACT_TEXT not in serialized
    assert study.RAW_REFUSAL not in serialized


def test_current_checkout_fails_closed_against_frozen_runner_binding():
    study = _study()
    with pytest.raises(ValueError, match="Executing checkout input drifted: src/hbqrs/runner.py"):
        study.verify_bindings()


def test_public_contract_geometry_and_nonpromotion_remain_live():
    study = _study()
    contract = study.contract()
    fixtures = json.loads(study.FIXTURES_PATH.read_text(encoding="utf-8"))
    assert contract["base_revision"] == study.BASE_REVISION
    assert contract["rubric"]["leaf_id"] == study.QUESTION_ID
    assert contract["execution"]["provider_free"] is True
    assert contract["execution"]["remote_provider_call_count"] == 0
    assert contract["execution"]["logical_sample_count"] == 6
    assert contract["execution"]["scenario_ids"] == list(study.SCENARIO_IDS)
    assert contract["gate"]["automatic_promotion"] is False
    assert contract["gate"]["pass_effect"].endswith("only")
    assert fixtures["artifact"]["text"] == study.ARTIFACT_TEXT
    assert [item["scenario_id"] for item in fixtures["scenarios"]] == list(study.SCENARIO_IDS)
    assert str(ROOT) not in json.dumps(contract, sort_keys=True)
    assert str(ROOT) not in json.dumps(fixtures, sort_keys=True)


def test_readme_labels_historical_runner_and_current_refusal_semantics():
    readme = README.read_text(encoding="utf-8")
    assert "The injected nine-attempt matrix and `python study.py verify` command are" in readme
    assert "historical/frozen-checkout-only: run them only with the exact `fb77e8a`" in readme
    assert "unstructured refusal text in ordinary response content is a schema/quote" in readme
    assert "`model_refusal` is recognized only from the" in readme
    assert "provider's structured `message.refusal` field (under the opted-in refusal lifecycle" in readme
    assert "Current-runner tests own that distinction." in readme


def test_canonical_git_binding_rejects_a_different_executing_checkout(monkeypatch: pytest.MonkeyPatch):
    study = _study()
    monkeypatch.setattr(study, "_checkout_has_base_revision", lambda: False)
    with pytest.raises(ValueError, match="does not descend"):
        study.verify_bindings()


@pytest.mark.parametrize(
    ("section", "key", "replacement", "message"),
    [
        ("gate", "automatic_promotion", True, "gate contract"),
        ("execution", "maximum_attempts_per_logical_sample", 99, "execution geometry"),
        ("execution", "remote_provider_call_count", 1, "execution geometry"),
        ("execution", "injected_attempt_count", 8, "execution geometry"),
        ("gate", "pass", "PASS_SOMETHING_ELSE", "gate contract"),
        ("gate", "pass_effect", "automatic runtime promotion", "gate contract"),
    ],
)
def test_contract_fails_closed_on_execution_and_gate_mutations(
    monkeypatch: pytest.MonkeyPatch, section: str, key: str, replacement: object, message: str
):
    study = _study()
    read = study._read_object

    def mutated(path: Path):
        value = read(path)
        if path == study.CONTRACT_PATH:
            value = copy.deepcopy(value)
            value[section][key] = replacement
        return value

    monkeypatch.setattr(study, "_read_object", mutated)
    with pytest.raises(ValueError, match=message):
        study.contract()
