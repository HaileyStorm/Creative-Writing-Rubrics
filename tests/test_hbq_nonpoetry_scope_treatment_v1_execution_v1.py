from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-treatment-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_treatment_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return historical_runtime.install(module, source_commit="6366bb3901e900ff73ddf5f5981d617954ea4a28")
    except historical_runtime.HistoricalRuntimeUnbound as exc:
        pytest.skip(f"historical runtime unbound: {exc}")


def _record(slot: dict[str, object], *, correct: bool = True) -> dict[str, object]:
    verdict = str(slot["expected_verdict"]) if correct else "YES"
    return {
        "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"],
        "verdict": verdict, "expected": slot["expected_verdict"], "correct": correct,
        "run_id": f"run-{slot['slot_id']}",
        "session_id_sha256": hashlib.sha256(("session-" + str(slot["slot_id"])).encode()).hexdigest(),
        "checkpoint_chain_head_sha256": hashlib.sha256(("chain-" + str(slot["slot_id"])).encode()).hexdigest(),
        "evidence": [], "accepted_provider_call_count": 1, "rejected_retry_count": 0, "batch_attempt_count": 1,
    }


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    return tmp_path / "s2-execution"


def test_package_full_binds_both_predecessors_and_exact_geometry():
    s = study()
    assert s.REPOSITORY != book_root()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "new_provider_calls": 27, "reused_accepted_calls": 6, "sealed_private_holdout": True}
    schedule = s.build_schedule()
    assert len(schedule) == len({row["slot_id"] for row in schedule}) == 27
    assert len({row["judge_id"] for row in schedule}) == 27
    assert sum(row["leaf_id"] == "scope.passage.status" for row in schedule) == 18
    assert sum(row["leaf_id"] != "scope.passage.status" for row in schedule) == 9
    assert s.contract()["predecessor"]["executed_baseline"]["commit"] == "a7e23b3"


def test_real_provider_free_dry_run_renders_exact_arm_wording_and_no_oracle_labels(private_root: Path):
    s = study()
    report = s.dry_run(private_root)
    runtime = json.loads((private_root / "runtime-schedule.json").read_text(encoding="utf-8"))
    assert report["provider_calls"] == 0 and len(runtime["slots"]) == 27
    assert (private_root / "runtime-s2mt-bundle.json").is_file()
    assert (private_root / "registry-overlays" / "current_wording" / "all_modules.json").is_file()
    assert (private_root / "registry-overlays" / "candidate_wording" / "all_modules.json").is_file()
    for slot in runtime["slots"]:
        prompt = (private_root / "rendered-prompts" / f"{slot['slot_id']}.txt").read_text(encoding="utf-8")
        assert slot["question"]["text"] in prompt
        assert "oracle" not in prompt.casefold()
        assert "expected_verdict" not in prompt.casefold()
        assert "sealed holdout" not in prompt.casefold()
        command = s.command_for(slot, private_root)
        assert command[command.index("--registry") + 1].endswith(f"registry-overlays\\{slot['arm']}\\all_modules.json")
        assert command[command.index("--bundles") + 1].endswith("runtime-s2mt-bundle.json")
        assert command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"
        assert command[command.index("--judge-id") + 1] == slot["judge_id"]


def test_execution_requires_dual_acknowledgement_and_uses_terminal_sidecars(private_root: Path):
    s = study()
    s.prepare(private_root)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(private_root)
    root = private_root / "sidecar"
    root.mkdir()
    s.runner._write_attempt_start(output_dir=root, config_sha256="a" * 64, batch_number=1, attempt_number=1, base_prompt_sha256="b" * 64, effective_prompt_sha256="c" * 64, batch_attempts=3)
    with pytest.raises(s.runner.HBQError, match="ambiguous"):
        s.runner._validate_or_reconstruct_attempt_lifecycle(root, config_sha256="a" * 64, batch_attempts=3, reconstruct=False, strict_v5=True)


def test_reuse_is_exact_immutable_baseline_and_preserves_observed_failure(monkeypatch, private_root: Path):
    s = study()
    s.prepare(private_root)
    immutable = []
    for index, row in enumerate(s._reused_slots(), 1):
        verdict = "NOT_APPLICABLE" if row["state"] == "activation_mismatch" else "YES"
        immutable.append({"source_slot_id": row["source_slot_id"], "leaf_id": row["leaf_id"], "state": row["state"], "repeat": row["repeat"], "expected": row["expected"], "verdict": verdict, "correct": verdict == row["expected"], "fixture_id": row["fixture_id"], "source_wording_sha256": hashlib.sha256(str(row["source_wording"]).encode()).hexdigest(), "run_id_sha256": hashlib.sha256(("run-" + str(index)).encode()).hexdigest(), "session_id_sha256": f"{index:064x}", "checkpoint_chain_head_sha256": f"{100 + index:064x}"})
    monkeypatch.setattr(s, "verify_reused_predecessor_calls", lambda _root: immutable)
    monkeypatch.setattr(s, "_validate_runtime", lambda _root: s.build_schedule())
    result = s.settle(private_root, private_root / "immutable", verifier=lambda _root, slot: _record(slot))
    assert result["decision"] == "GO_TREATMENT"
    assert result["per_cell_three_of_three"]["scope.passage.status|material_failure|current_wording"]["observed_verdict_counts"] == {"YES": 3}
    assert result["per_cell_three_of_three"]["scope.passage.status|activation_mismatch|current_wording"]["observed_verdict_counts"] == {"NOT_APPLICABLE": 3}
    assert result["treatment_gate"]["improved_baseline_failures"] == ["scope.passage.status|material_failure|current_wording"]


def test_runtime_binding_fails_closed_on_overlay_tamper(private_root: Path):
    s = study()
    s.prepare(private_root)
    (private_root / "registry-overlays" / "candidate_wording" / "all_modules.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="overlay"):
        s._validate_runtime(private_root)


def test_public_package_contains_no_private_holdout_or_response_material():
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    assert files == {"run.py", "study-contract.json", "study.py"}
    for path in (ROOT / name for name in files):
        text = path.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in text and "Gray Blood" not in text and "raw_response" not in text
