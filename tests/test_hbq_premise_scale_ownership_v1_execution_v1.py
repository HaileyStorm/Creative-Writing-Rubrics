from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-premise-scale-ownership-v1-execution-v1"


ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived P1 premise-scale execution mechanics require the frozen runtime bindings; current bindings have advanced."
)


def study():
    spec = importlib.util.spec_from_file_location("premise_scale_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        leaf = command[command.index("--question-id") + 1]
        artifact = command[command.index("--artifact-id") + 1]
        return SimpleNamespace(returncode=0, stdout=f"ordinary prompt for {artifact} / {leaf}", stderr="")
    if "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _prepared(s, root: Path):
    s.dry_run(root, runner_call=_fake_cwr)
    return json.loads((root / "runtime-schedule.json").read_text(encoding="utf-8"))["slots"]


def _record(s, slot: dict[str, object]) -> dict[str, object]:
    case = s._case_for(slot)
    quote = case["sections"]["premise"][:30]
    return {
        "slot_id": slot["slot_id"], "verdict": slot["expected_verdict"], "expected": slot["expected_verdict"],
        "correct": True, "evidence": [{"reference": "premise", "exact_quote": quote}],
        "run_id": f"run-{slot['slot_id']}", "session_id_sha256": f"{int(str(slot['slot_id'])[-3:]):064x}",
        "checkpoint_chain_head_sha256": f"{int(str(slot['slot_id'])[-3:]) + 1000:064x}",
    }


def test_current_checkout_fails_closed_and_execution_geometry_remains_exact():
    s = study()
    with pytest.raises(ValueError, match="Current production runtime binding drifted"):
        s.validate_package()
    predecessor = s._predecessor()
    corpus = predecessor.load_corpus()
    predecessor.verify_corpus(corpus)
    slots = predecessor.plan_slots()
    assert s.contract()["status"] == "frozen_execution_successor_unexecuted"
    assert s.contract()["execution"]["route"] == "codex"
    assert s.contract()["execution"]["model"] == "gpt-5.6-sol"
    assert s.contract()["execution"]["reasoning"] == "high"
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 72
    assert {slot["leaf_id"] for slot in slots} == set(predecessor.LEAVES)
    assert {slot["expected_verdict"] for slot in slots} == predecessor.VERDICTS
    assert len(corpus["artifacts"]) == 12
    assert len({item["pair_id"] for item in corpus["artifacts"]}) == 6
    assert s.contract()["predecessor"]["commit"] == "95a86b8353b4d27c85914d4258e4da33d080f9d7"


@ARCHIVED_OLD_RUNTIME
def test_dry_run_has_no_provider_calls_and_prepares_exact_prompt_commitments(tmp_path: Path):
    s = study()
    report = s.dry_run(tmp_path, runner_call=_fake_cwr)
    stored = json.loads((tmp_path / "runtime-schedule.json").read_text(encoding="utf-8"))
    assert report["provider_calls"] == 0
    assert len(report["rendered_prompt_sha256s"]) == 72
    assert stored["rendered_prompt_aggregate_sha256"] == report["rendered_prompt_aggregate_sha256"]
    assert "--provider" in report["first_command"] and report["first_command"][report["first_command"].index("--provider") + 1] == "codex"
    assert report["first_command"][report["first_command"].index("--batch-size") + 1] == "1"
    assert "--strict-ai" in report["first_command"]
    assert not (ROOT / "public-synthetic-corpus.json").exists()
    with pytest.raises(ValueError, match="outside"):
        s.prepare(s.REPOSITORY)


@ARCHIVED_OLD_RUNTIME
def test_provider_command_and_private_schedule_do_not_disclose_oracle_case_or_pair_metadata(tmp_path: Path):
    s = study()
    slots = _prepared(s, tmp_path)
    command = s.command_for(slots[0], tmp_path)
    private = (tmp_path / "private-schedule.json").read_text(encoding="utf-8")
    assert "expected_verdict" in private and "pair_id" in private and "case_id" in private
    joined = " ".join(command)
    # The local output directory names the slot for resumability; the provider-facing
    # prompt does not receive CLI bookkeeping or any oracle ledger field.
    prompt = (tmp_path / "rendered-prompts" / f"{slots[0]['slot_id']}.txt").read_text(encoding="utf-8")
    for forbidden in (slots[0]["case_id"], slots[0]["pair_id"], "expected_verdict", "oracle"):
        assert forbidden not in joined
        assert forbidden not in prompt
    assert "--question-id" in command and command[command.index("--question-id") + 1] == slots[0]["leaf_id"]
    assert "--allow-remote" not in command
    assert "--resume" not in command
    assert "--resume" in s.command_for(slots[0], tmp_path, resume=True)


@ARCHIVED_OLD_RUNTIME
def test_execute_requires_both_acknowledgement_and_prepared_bindings(tmp_path: Path):
    s = study()
    _prepared(s, tmp_path)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(tmp_path, runner_call=_fake_cwr)
    result = s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)
    assert result["route"] == "codex" and result["billing"] == "owner_attested_subscription_zero_incremental_charge"
    stored = json.loads((tmp_path / "runtime-schedule.json").read_text(encoding="utf-8"))
    stored["slots"][0]["rendered_prompt_sha256"] = "0" * 64
    (tmp_path / "runtime-schedule.json").write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(ValueError, match="schedule"):
        s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)


@ARCHIVED_OLD_RUNTIME
def test_settlement_requires_all_slots_and_reports_no_change_or_incomplete(tmp_path: Path):
    s = study()
    _prepared(s, tmp_path)
    result = s.settle(tmp_path, verifier=lambda _root, slot: _record(s, slot))
    assert result["decision"] == "PASS_NO_CHANGE"
    assert len(result["per_cell_three_of_three"]) == 24
    assert result["promotion"] == "none"
    public = json.loads((tmp_path / "public-aggregate.json").read_text(encoding="utf-8"))
    assert public["decision"] == "PASS_NO_CHANGE"
    assert public["scored_cells"] == {"passed": 20, "total": 20}
    assert public["not_applicable_diagnostic_cells"] == {"matched": 4, "total": 4}
    assert all(set(counts) == s.VERDICTS for counts in public["canonical_four_state_counts"].values())

    other = tmp_path.parent / "missing"
    _prepared(s, other)
    incomplete = s.settle(other, verifier=lambda _root, slot: (_ for _ in ()).throw(ValueError("missing run")) if slot["slot_id"] == "psoexec-v1-001" else _record(s, slot))
    assert incomplete["decision"] == "INCOMPLETE"
    assert incomplete["completed_slots"] == 71


@ARCHIVED_OLD_RUNTIME
def test_mutated_schedule_and_duplicate_identity_fail_closed(tmp_path: Path):
    s = study()
    slots = _prepared(s, tmp_path)
    manifest = json.loads((tmp_path / "study-manifest.json").read_text(encoding="utf-8"))
    manifest["runtime_bindings"]["cwr_files"]["src/hbqrs/runner.py"] = "0" * 64
    (tmp_path / "study-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert s.settle(tmp_path, verifier=lambda _root, slot: _record(s, slot))["decision"] == "INCOMPLETE"

    other = tmp_path.parent / "duplicate"
    _prepared(s, other)
    def duplicate(_root, slot):
        row = _record(s, slot)
        row["session_id_sha256"] = "a" * 64
        return row
    assert s.settle(other, verifier=duplicate)["decision"] == "INCOMPLETE"


def test_public_package_is_code_and_contract_only_and_does_not_expose_the_sealed_holdout():
    forbidden = ("C:\\Users\\", "Gray Blood", "Tears of Steel", "Spring", "raw_response", "api_key")
    files = [path for path in ROOT.iterdir() if path.is_file()]
    assert {path.name for path in files} == {"README.md", "run.py", "study-contract.json", "study.py"}
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(value in text for value in forbidden)
    assert "--execute" in (ROOT / "run.py").read_text(encoding="utf-8")


def test_production_compact_evidence_accepts_exact_summary_and_mixed_with_context_grounding():
    s = study()
    artifact = "artifact premise"
    contexts = ["contextual proof"]
    s._validate_production_evidence([{"reference": "artifact", "exact_quote": "artifact premise"}], artifact_text=artifact, context_texts=contexts, question_id=s.LEAVES[0])
    s._validate_production_evidence([{"reference": "context", "summary": "a grounded summary"}], artifact_text=artifact, context_texts=contexts, question_id=s.LEAVES[0])
    s._validate_production_evidence([{"reference": "artifact", "exact_quote": "artifact premise"}, {"reference": "context", "summary": "contextual summary"}], artifact_text=artifact, context_texts=contexts, question_id=s.LEAVES[0])
    with pytest.raises(Exception, match="quote"):
        s._validate_production_evidence([{"reference": "context", "exact_quote": "not supplied"}], artifact_text=artifact, context_texts=contexts, question_id=s.LEAVES[0])


@ARCHIVED_OLD_RUNTIME
def test_not_applicable_is_reported_but_not_a_pass_gate_and_overlap_is_a_diagnostic_outcome(tmp_path: Path):
    s = study()
    _prepared(s, tmp_path)
    def not_applicable_miss(_root, slot):
        row = _record(s, slot)
        if row["expected"] == "NOT_APPLICABLE":
            row["verdict"] = "YES"
            row["correct"] = False
        return row
    settled = s.settle(tmp_path, verifier=not_applicable_miss)
    assert settled["decision"] == "PASS_NO_CHANGE"
    assert settled["accuracy"]["not_applicable_unscored"]["correct"] < settled["accuracy"]["not_applicable_unscored"]["denominator"]
    assert "section_span_overlap" in settled["cross_leaf_evidence_section_span_overlap"]


@ARCHIVED_OLD_RUNTIME
def test_fresh_execute_requires_clean_dry_run_manifests_and_resume_allows_partial_attempts(tmp_path: Path):
    s = study()
    slots = _prepared(s, tmp_path)
    assert s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)["mode"] == "execute"
    response = tmp_path / "runs" / slots[0]["slot_id"] / "responses"
    response.mkdir(parents=True, exist_ok=True)
    (response / "batch-0001.attempt-01.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="prior provider attempts"):
        s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)
    assert s.execute(tmp_path, resume=True, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)["mode"] == "resume"


@ARCHIVED_OLD_RUNTIME
def test_overlap_uses_real_section_intervals_and_clarification_requires_case_level_repeats(tmp_path: Path):
    s = study()
    schedule = _prepared(s, tmp_path)
    by_slot = {slot["slot_id"]: slot for slot in schedule}
    pair = [slot for slot in schedule if slot["case_id"] == "mismatched-form-isolated" and slot["repeat"] == 1]
    rows = [_record(s, slot) for slot in pair]
    rows[0]["evidence"] = [{"reference": "different", "exact_quote": by_slot[rows[0]["slot_id"]]["artifact_text"][:20]}]
    rows[1]["evidence"] = [{"reference": "other", "summary": "summary only"}]
    overlap = s._overlap(rows, schedule)
    assert overlap["same_reference_overlap"] == 0
    assert overlap["section_span_overlap"] == 0
    assert overlap["exact_quote_overlap"] == 0

    records = [_record(s, slot) for slot in schedule]
    candidates = [slot for slot in schedule if slot["leaf_id"] == s.LEAVES[0] and slot["expected_verdict"] == "YES"]
    # One miss per carrier must not count as a two-of-three case-level repetition.
    for slot in candidates[:2]:
        row = next(item for item in records if item["slot_id"] == slot["slot_id"])
        row["verdict"], row["correct"] = "NO", False
    eligibility = s._clarification_eligibility(records, schedule, s._overlap(records, schedule))
    assert eligibility["eligible"] is False
