from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v3-final-message"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module():
    spec = importlib.util.spec_from_file_location("_confirmation_sol_reconcile_v3", PACKAGE / "recover.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value; spec.loader.exec_module(value)
    return value


class Base:
    @staticmethod
    def _validate_answer(value): return value


def answer(*, covered: bool, score: float):
    return {"coverage": {key: covered for key in DIMENSIONS}, "evidence": {key: "fixture" for key in DIMENSIONS}, "scores": {key: score for key in DIMENSIONS}}


def write_turn(tmp_path: Path, *, interim=answer(covered=False, score=0), final=answer(covered=True, score=2), trailing=None):
    responses = tmp_path / "responses"; responses.mkdir()
    final_raw = json.dumps(final, sort_keys=True, separators=(",", ":")).encode("utf-8")
    records = [{"type": "thread.started"}, {"type": "turn.started"}, {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(interim, sort_keys=True, separators=(",", ":"))}}, {"type": "item.completed", "item": {"type": "agent_message", "text": final_raw.decode("utf-8")}}]
    if trailing is not None: records.append(trailing)
    records.append({"type": "turn.completed"})
    (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(b"".join(json.dumps(item, separators=(",", ":")).encode("utf-8") + b"\n" for item in records))
    (responses / "batch-0001.attempt-0001.message.json").write_bytes(final_raw)


def test_accepts_only_zero_coverage_interim_then_exact_final(tmp_path: Path):
    value = module(); write_turn(tmp_path)
    assert value._terminal_final(tmp_path, Base()) == answer(covered=True, score=2)


@pytest.mark.parametrize("interim,trailing,mutate", [
    (answer(covered=True, score=0), None, False),
    (answer(covered=False, score=0), {"type": "item.completed", "item": {"type": "tool_message", "text": "{}"}}, False),
    (answer(covered=False, score=0), None, True),
])
def test_rejects_authoritative_interim_extra_after_final_or_message_mismatch(tmp_path: Path, interim, trailing, mutate):
    value = module(); write_turn(tmp_path, interim=interim, trailing=trailing)
    if mutate:
        (tmp_path / "responses" / "batch-0001.attempt-0001.message.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        value._terminal_final(tmp_path, Base())


def test_public_result_rejects_group_redistribution_contact_escalation_and_paths(tmp_path: Path):
    value = module(); source = PACKAGE / "result.json"
    assert value.validate_public(source)["metrics"]["broader-nextwave-13-missing_evidence_not_no"] == 1.2439236111111112
    redistributed = json.loads(source.read_bytes())
    groups = redistributed["group_mae"]["candidate-102cc7f06c9a99a7"]
    groups["prompt-224828d8a6b2b338"] += 0.1; groups["prompt-3286f1e85780066d"] -= 0.1
    alterations = {
        "same_average_group_redistribution": redistributed,
        "contact_escalation": {**json.loads(source.read_bytes()), "native_endpoint_contact_cardinality": "exactly_38"},
        "generalization_overclaim": {**json.loads(source.read_bytes()), "generalization": "established"},
        "private_path": {**json.loads(source.read_bytes()), "source_path": "C:\\private\\output"},
        "overclaim": {**json.loads(source.read_bytes()), "authority": {"selection": "promoted"}},
    }
    for label, altered in alterations.items():
        path = tmp_path / f"{label}.json"; path.write_bytes(value.canonical(altered))
        with pytest.raises(ValueError, match="binding"):
            value.validate_public(path)


def test_replay_requires_byte_identical_public_result(monkeypatch, tmp_path: Path):
    value = module(); source = PACKAGE / "result.json"
    expected = value.validate_public(source)
    monkeypatch.setattr(value, "recover_and_project", lambda **_: expected)
    assert value.replay_public(output_root=tmp_path, frozen_root=tmp_path, authorization_acknowledgement_sha256="ack", result_path=source) == expected
    altered = dict(expected); altered["comparison"] = dict(expected["comparison"]); altered["comparison"]["descendant_minus_baseline"] = 0.0
    monkeypatch.setattr(value, "recover_and_project", lambda **_: altered)
    with pytest.raises(ValueError, match="exactly equal"):
        value.replay_public(output_root=tmp_path, frozen_root=tmp_path, authorization_acknowledgement_sha256="ack", result_path=source)


def test_study_contract_rejects_tampering_and_coherently_rehashed_result(tmp_path: Path):
    value = module(); source = PACKAGE / "study-contract.json"
    assert value.validate_study_contract()["public_result_sha256"]
    altered = json.loads(source.read_bytes()); altered["authority"]["promotion"] = "promoted"
    path = tmp_path / "contract.json"; path.write_bytes(value.canonical(altered))
    with pytest.raises(ValueError, match="contract binding"):
        value.validate_study_contract(path)
    result = json.loads((PACKAGE / "result.json").read_bytes())
    result["group_mae"]["candidate-102cc7f06c9a99a7"]["prompt-224828d8a6b2b338"] += 0.1
    result_path = tmp_path / "result.json"; result_path.write_bytes(value.canonical(result))
    coherent = json.loads(source.read_bytes()); coherent["public_result_sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    coherent_path = tmp_path / "coherent-contract.json"; coherent_path.write_bytes(value.canonical(coherent))
    with pytest.raises(ValueError, match="contract binding"):
        value.validate_study_contract(coherent_path, result_path)
