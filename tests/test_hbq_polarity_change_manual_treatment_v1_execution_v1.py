from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-polarity-change-manual-treatment-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("p1_manual_treatment_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"manual treatment prompt\r\n")
    elif "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _prepared(s, root: Path):
    s.dry_run(root, runner_call=_fake_cwr)
    return json.loads((root / "runtime-schedule.json").read_text(encoding="utf-8"))["slots"]


@pytest.fixture
def private_root():
    with tempfile.TemporaryDirectory(prefix="hbq-p1mt-exec-") as directory:
        yield Path(directory)


def _record(slot: dict[str, object]) -> dict[str, object]:
    return {
        "slot_id": slot["slot_id"], "verdict": slot["expected_verdict"], "expected": slot["expected_verdict"], "correct": True,
        "evidence": [{"reference": "artifact", "exact_quote": str(slot["artifact_text"])[:20]}],
        "run_id": f"run-{slot['slot_id']}", "session_id_sha256": hashlib.sha256(str(slot["slot_id"]).encode()).hexdigest(),
        "checkpoint_chain_head_sha256": hashlib.sha256(("chain-" + str(slot["slot_id"])).encode()).hexdigest(),
    }


def test_package_binds_pushed_manual_treatment_predecessor_and_exact_57_slots():
    s = study()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "slots": 57, "provider_calls": 0, "predecessor": "6366bb3"}
    slots = s.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 57
    assert len({slot["leaf_id"] for slot in slots}) == 11
    assert {slot["expected_verdict"] for slot in slots} == {"YES", "NO", "NOT_APPLICABLE"}
    assert s.contract()["execution"]["maximum_provider_sends"] == 171


def test_dry_run_freezes_private_overlay_carriers_and_canonical_prompts(private_root: Path):
    s = study()
    report = s.dry_run(private_root, runner_call=_fake_cwr)
    schedule = json.loads((private_root / "runtime-schedule.json").read_text(encoding="utf-8"))["slots"]
    assert report["provider_calls"] == 0 and len(schedule) == 57
    assert (private_root / "runtime-book" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8").endswith(s._predecessor().TREATMENT_APPENDIX + "\n")
    assert (private_root / "task-contracts" / schedule[0]["artifact_id"]).with_suffix(".json").is_file()
    assert (private_root / "remote-disclosure.json").is_file()
    assert (private_root / "rendered-prompts" / schedule[0]["slot_id"]).with_suffix(".txt").read_bytes() == b"manual treatment prompt\n"


def test_singleton_commands_have_unique_judge_ids_and_execute_requires_dual_acknowledgement(private_root: Path):
    s = study()
    slots = _prepared(s, private_root)
    commands = [s.command_for(slot, private_root) for slot in slots]
    judge_ids = {command[command.index("--judge-id") + 1] for command in commands}
    assert len(judge_ids) == 57
    assert all("--allow-remote" not in command and command[command.index("--batch-size") + 1] == "1" and command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1" for command in commands)
    assert all("-yes" not in judge_id and "-no" not in judge_id and "-na" not in judge_id for judge_id in judge_ids)
    assert s.environment_for(private_root)["HBQRS_ROOT"] == str(private_root / "runtime-book")
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(private_root, runner_call=_fake_cwr)
    assert s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)["mode"] == "execute"


def test_terminal_sidecar_unresolved_start_blocks_resume(tmp_path: Path):
    s = study()
    output = tmp_path / "terminal-sidecar"
    output.mkdir()
    config_sha256 = "a" * 64
    s.runner._write_attempt_start(output_dir=output, config_sha256=config_sha256, batch_number=1, attempt_number=1, base_prompt_sha256="b" * 64, effective_prompt_sha256="c" * 64, batch_attempts=3)
    with pytest.raises(s.runner.HBQError, match="ambiguous"):
        s.runner._validate_or_reconstruct_attempt_lifecycle(output, config_sha256=config_sha256, batch_attempts=3, reconstruct=False, strict_v5=True)


def test_tampered_disclosure_blocks_fresh_execution_and_resume(private_root: Path):
    s = study()
    _prepared(s, private_root)
    (private_root / "remote-disclosure.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="disclosure"):
        s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)
    with pytest.raises(ValueError, match="disclosure"):
        s.execute(private_root, resume=True, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)


def test_settlement_requires_all_19_cells_three_of_three_and_unique_receipts(private_root: Path):
    s = study()
    slots = _prepared(s, private_root)
    settled = s.settle(private_root, verifier=lambda _root, slot: _record(slot))
    assert settled["decision"] == "MANUAL_TREATMENT_PASS"
    assert len(settled["per_cell_three_of_three"]) == 19
    other = private_root / "missing"
    _prepared(s, other)
    incomplete = s.settle(other, verifier=lambda _root, slot: (_ for _ in ()).throw(ValueError("missing run")) if slot["slot_id"] == slots[0]["slot_id"] else _record(slot))
    assert incomplete["decision"] == "INCOMPLETE" and incomplete["completed_slots"] == 56


def test_public_package_is_code_only_and_does_not_contain_private_holdout_or_response_data():
    s = study()
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    assert files == {"run.py", "study-contract.json", "study.py"}
    for path in (ROOT / name for name in files):
        text = path.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in text and "Gray Blood" not in text and "raw_response" not in text
    assert "sealed-holdout" not in " ".join(files)
