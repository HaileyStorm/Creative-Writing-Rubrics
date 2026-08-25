from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as historical_runtime

ROOT = book_root() / "evaluation-results" / "hbq-figurative-dspy-boundary-search-successor-v1"


def study():
    spec = importlib.util.spec_from_file_location("figurative_dspy_boundary_search", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return historical_runtime.install(module, source_commit="6ae9ee0db17dda61bb9adc00a60bcd8072969d5d")


@pytest.fixture
def private_root():
    root = Path(tempfile.mkdtemp(prefix="hbq-figurative-dspy-boundary-"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def seed_ledger(root: Path, s) -> None:
    labels = {
        "tr-k4": "YES", "tr-q7": "NO", "tr-r2": "YES", "tr-v9": "NO",
        "tr-b5": "YES", "tr-n1": "NO", "tr-f8": "YES", "tr-h3": "NO",
        "tr-m6": "YES", "tr-p0": "YES", "tr-c4": "YES", "tr-x2": "NO",
        "dv-l3": "YES", "dv-t6": "NO", "dv-a9": "YES", "dv-e1": "YES",
        "dv-g7": "YES", "dv-w5": "NO",
    }
    (root / s.EXPECTED_LEDGER).write_text(json.dumps({"labels": labels}), encoding="utf-8")


def fake_provider_free_runner(command, **_kwargs):
    if "render-judge" in command:
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("production prompt", encoding="utf-8")
    return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()


def stub_materialization(monkeypatch, s):
    def prepare(root, _slots):
        path = root / s.PRIVATE_DIRECTORY
        path.mkdir(parents=True, exist_ok=True)
        return path

    def bindings(_root, slots):
        return {
            "study_contract_sha256": "1" * 64, "study_code_sha256": "2" * 64, "run_code_sha256": "3" * 64,
            "candidate_appendices_sha256": "4" * 64, "public_corpus_sha256": "5" * 64, "private_expected_ledger_sha256": "6" * 64,
            "schedule_sha256": "7" * 64, "provider_materials_sha256": "8" * 64, "provider_material_hashes": {},
            "rendered_prompts_sha256": "9" * 64, "rendered_prompt_hashes": {}, "provider_commands_sha256": "a" * 64, "provider_commands": {slot["slot_id"]: [] for slot in slots},
        }

    monkeypatch.setattr(s, "prepare_execution", prepare)
    monkeypatch.setattr(s, "_freeze_bindings", bindings)


def test_static_four_candidate_geometry_and_ownership_boundaries():
    s = study()
    assert s.validate_package() == {
        "study_id": s.STUDY_ID,
        "candidates": 4,
        "train_slots": 48,
        "selected_dev_slots": 24,
        "materialized_dev_slots": 48,
        "provider_calls": 0,
        "promotion": "none",
    }
    assert len(s.build_train_schedule()) == 48
    assert len(s.build_reserved_dev_schedule()) == 24
    assert {row["candidate_id"] for row in s.build_train_schedule()} == {"appendix-a", "appendix-b", "appendix-c", "appendix-d"}
    assert all(row["leaf_id"] == s.TARGET for row in s.build_train_schedule())


def test_prompt_has_no_expected_label_or_private_ledger_material():
    s = study()
    prompt = s.render_train_prompt(s.build_train_schedule()[0]).casefold()
    assert "expected" not in prompt
    assert "ledger" not in prompt
    assert "appendix-a" not in prompt
    assert s.STRICT_EVIDENCE.casefold() in prompt


def test_negative_fixtures_do_not_state_the_oracle_or_missing_hinge():
    s = study()
    labels = {"tr-q7", "tr-v9", "tr-n1", "tr-h3", "tr-x2", "dv-t6", "dv-w5"}
    text = "\n".join(case["text"] for case in s.corpus() if case["case_id"] in labels).casefold()
    for forbidden in ("no relation", "no explanation", "no second use", "without any change", "incompatible", " yet "):
        assert forbidden not in text


def test_supported_train_double_meaning_is_labelled_yes_only_in_the_private_ledger(private_root):
    s = study()
    seed_ledger(private_root, s)
    ledger = json.loads((private_root / s.EXPECTED_LEDGER).read_text(encoding="utf-8"))["labels"]
    assert ledger["tr-p0"] == "YES"
    case = next(item for item in s.corpus() if item["case_id"] == "tr-p0")
    assert set(case) == {"case_id", "split", "boundary_type", "text"}


def test_dry_run_is_provider_free_and_binds_train_before_reserved_dev(private_root, monkeypatch):
    s = study()
    seed_ledger(private_root, s)
    monkeypatch.setattr(s, "_require_exact_head", lambda: None)
    stub_materialization(monkeypatch, s)
    report = s.dry_run(private_root, runner_call=fake_provider_free_runner)
    assert report["provider_calls"] == 0
    frozen = json.loads((private_root / s.PRIVATE_DIRECTORY / "frozen-dry-run.v1.json").read_text(encoding="utf-8"))
    assert frozen["train_slots"] == 48 and frozen["selected_dev_slots"] == 24
    assert frozen["materialized_potential_dev_slots"] == 48
    assert frozen["stage_order"] == "all_train_before_any_dev"
    assert len(frozen["review_bindings"]["provider_commands"]) == 96
    assert all(slot["stage"] == "train" for slot in frozen["train_schedule"])
    assert all(slot["stage"] == "dev" for slot in frozen["all_potential_dev_schedule"])


def test_private_ledger_is_required_and_must_not_select_candidates(private_root, monkeypatch):
    s = study()
    monkeypatch.setattr(s, "_require_exact_head", lambda: None)
    stub_materialization(monkeypatch, s)
    with pytest.raises(FileNotFoundError):
        s.dry_run(private_root, runner_call=fake_provider_free_runner)
    seed_ledger(private_root, s)
    data = json.loads((private_root / s.EXPECTED_LEDGER).read_text(encoding="utf-8"))
    data["candidate"] = "appendix-a"
    (private_root / s.EXPECTED_LEDGER).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate selection"):
        s.dry_run(private_root, runner_call=fake_provider_free_runner)


def test_deterministic_top_two_prefers_exact_then_boundary_floor_then_id(private_root):
    s = study()
    seed_ledger(private_root, s)
    labels = json.loads((private_root / s.EXPECTED_LEDGER).read_text(encoding="utf-8"))["labels"]
    records = []
    for candidate in s.candidates():
        for slot in s.build_train_schedule():
            if slot["candidate_id"] != candidate["candidate_id"]:
                continue
            verdict = labels[slot["case_id"]]
            if candidate["candidate_id"] == "appendix-c" and slot["case_id"] in {"tr-k4", "tr-q7"}:
                verdict = "NO" if verdict == "YES" else "YES"
            if candidate["candidate_id"] == "appendix-d" and slot["case_id"] in {"tr-k4", "tr-r2"}:
                verdict = "NO" if verdict == "YES" else "YES"
            records.append({"slot_id": slot["slot_id"], "candidate_id": slot["candidate_id"], "case_id": slot["case_id"], "verdict": verdict})
    ranked = s.rank_train_records(records, private_root)
    assert [row["candidate_id"] for row in ranked[:2]] == ["appendix-a", "appendix-b"]
    assert len(s.build_selected_dev_schedule(["appendix-a", "appendix-b"])) == 24


def test_sealed_execution_requires_review_before_any_dispatch(private_root, monkeypatch):
    s = study()
    seed_ledger(private_root, s)
    monkeypatch.setattr(s, "_require_exact_head", lambda: None)
    stub_materialization(monkeypatch, s)
    s.dry_run(private_root, runner_call=fake_provider_free_runner)
    dispatched = []
    with pytest.raises(FileNotFoundError):
        s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=lambda *args, **kwargs: dispatched.append(args))
    assert dispatched == []


def test_go_record_must_bind_exact_dry_manifest_and_provider_visible_hashes(private_root, monkeypatch):
    s = study()
    seed_ledger(private_root, s)
    monkeypatch.setattr(s, "_require_exact_head", lambda: None)
    stub_materialization(monkeypatch, s)
    s.dry_run(private_root, runner_call=fake_provider_free_runner)
    dry_path = private_root / s.PRIVATE_DIRECTORY / "frozen-dry-run.v1.json"
    dry = json.loads(dry_path.read_text(encoding="utf-8"))
    review = {"study_id": s.STUDY_ID, "source_head": s.SOURCE_HEAD, "decision": "GO", "bindings": {"dry_manifest_sha256": "0" * 64, **dry["review_bindings"]}}
    (private_root / s.REVIEW_RECORD).write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="exact dry manifest"):
        s._require_review(private_root, dry)


def test_execution_command_is_exact_sol_high_singleton_and_one_attempt(private_root):
    s = study()
    slot = s.build_train_schedule()[0]
    s.prepare_execution(private_root, [slot])
    command = s.command_for(slot, private_root, allow_remote=True)
    assert command[command.index("--provider") + 1] == "codex"
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert command[command.index("--reasoning") + 1] == "high"
    assert command[command.index("--batch-size") + 1] == "1"
    assert command[command.index("--batch-attempts") + 1] == "1"
    assert "--resume" not in command and command[-1] == "--allow-remote"
