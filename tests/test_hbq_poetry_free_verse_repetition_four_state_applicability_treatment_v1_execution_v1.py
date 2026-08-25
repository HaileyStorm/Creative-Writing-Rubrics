from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from _hbq_s1_historical_runtime import install_historical_runtime
from hbqrs.paths import book_root

ROOT = (
    book_root()
    / "evaluation-results"
    / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v1"
)


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_execution_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return install_historical_runtime(module, source_commit=module.SOURCE_COMMIT)


@pytest.fixture
def private_root(tmp_path: Path, monkeypatch):
    value = study()
    root = tmp_path / "private"
    root.mkdir()
    states = (
        ("absence", "NOT_APPLICABLE"),
        ("accidental_inert_duplicate", "NO"),
        ("functional_recurrence", "YES"),
        ("incomplete_indicated_recurrence", "CANNOT_ASSESS"),
    )
    fixtures = [
        {
            "fixture_id": f"fixture-{index}",
            "state": state,
            "role": "target" if state == "accidental_inert_duplicate" else "control",
            "expected_verdict": verdict,
            "declared_scope": "complete poem" if state != "incomplete_indicated_recurrence" else "excerpt",
            "completion_status": "complete" if state != "incomplete_indicated_recurrence" else "excerpt",
            "contexts": [f"Synthetic context {index}."],
            "text": f"Synthetic quoted evidence {index}.",
        }
        for index, (state, verdict) in enumerate(states, start=1)
    ]
    controller = {
        "study_id": value.STUDY_ID,
        "format_version": 1,
        "visibility": "private_controller_only",
        "fixture_matrix": fixtures,
    }
    combinations = [(fixture, repeat) for fixture in fixtures for repeat in (1, 2, 3)]
    ledger = {
        "study_id": value.STUDY_ID,
        "format_version": 1,
        "visibility": "private_controller_only",
        "slot_mapping": [
            {
                "opaque_slot_id": f"s1fourstate-v1-slot-{index:02d}",
                "fixture_id": fixture["fixture_id"],
                "arm": "candidate",
                "repeat": repeat,
            }
            for index, (fixture, repeat) in enumerate(combinations, start=1)
        ],
    }
    (root / "private-controller.json").write_text(json.dumps(controller), encoding="utf-8")
    (root / "private-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (root / "verify_private_freeze.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    def frozen():
        return controller, ledger

    monkeypatch.setattr(value, "_private_freeze", frozen)
    monkeypatch.setattr(value._adapter(), "_private_freeze", frozen)
    monkeypatch.setattr(value._base(), "_private_freeze", frozen)
    value.set_private_root(root)
    return value, root / value.PRIVATE_EXECUTION_DIRECTORY


def find_leaf(node: object, leaf_id: str) -> dict[str, object] | None:
    if isinstance(node, dict):
        if node.get("id") == leaf_id:
            return node
        for child in node.values():
            found = find_leaf(child, leaf_id)
            if found is not None:
                return found
    if isinstance(node, list):
        for child in node:
            found = find_leaf(child, leaf_id)
            if found is not None:
                return found
    return None


def fake_render(command, **_kwargs):
    registry = Path(command[command.index("--registry") + 1])
    leaf = find_leaf(json.loads(registry.read_text(encoding="utf-8")), "form.poetry.free_verse.repetition")
    assert leaf is not None
    return SimpleNamespace(returncode=0, stdout=("frozen prompt\n" + str(leaf["text"]) + "\n").encode(), stderr=b"")


def test_exact_head_adapter_runtime_candidate_and_four_state_geometry_are_bound(private_root):
    value, _root = private_root
    report = value.validate_package()
    assert report["source_commit"] == value.SOURCE_COMMIT
    assert report["slots"] == 12 and report["provider_calls"] == 0
    assert report["normalization_events_required"] == 0
    assert value.contract()["candidate"]["text"] == value.CANDIDATE_TEXT
    assert value.contract()["promotion"] == "none"


def test_schedule_is_twelve_candidate_only_sol_high_singletons(private_root):
    value, root = private_root
    schedule = value.build_schedule()
    assert len(schedule) == len({slot["opaque_slot_id"] for slot in schedule}) == 12
    assert {slot["fixture_id"] for slot in schedule} == {f"fixture-{index}" for index in range(1, 5)}
    assert {slot["arm"] for slot in schedule} == {"candidate"}
    assert {slot["repeat"] for slot in schedule} == {1, 2, 3}
    assert all(slot["condition"]["batch_size"] == slot["condition"]["batch_attempts"] == 1 for slot in schedule)
    live = value.command_for(schedule[0], root, render=False)
    assert live[live.index("--model") + 1] == "gpt-5.6-sol"
    assert live[live.index("--reasoning") + 1] == "high"
    assert live[live.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"


def test_provider_free_dry_run_freezes_twelve_prompts_without_contact(private_root):
    value, root = private_root
    report = value.dry_run(root.parent, runner_call=fake_render)
    assert report["provider_calls"] == 0
    assert report["rendered_prompts"] == report["candidate_prompt_checks"] == 12
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert disclosure["planned_provider_sends"] == 12
    assert disclosure["semantic_retries"] == "forbidden"
    assert disclosure["resume"] == "forbidden"


def test_strict_grounding_accepts_only_verbatim_quotes_with_zero_normalization(private_root):
    value, _root = private_root
    slot = value.build_schedule()[0]
    quote = slot["artifact_text"]
    raw = {
        "verdicts": [{
            "question_id": "form.poetry.free_verse.repetition",
            "verdict": slot["expected_verdict"],
            "evidence": [{"kind": "exact_quote", "exact_quote": quote, "summary": None, "reference": "artifact"}],
        }]
    }
    assert value._validate_raw_grounding(slot, {"normalization_audit": []}, raw) == 1
    with pytest.raises(ValueError, match="Normalized"):
        value._validate_raw_grounding(slot, {"normalization_audit": [{"reason": "not_verbatim"}]}, raw)
    raw["verdicts"][0]["evidence"][0]["exact_quote"] = "not supplied"
    with pytest.raises(ValueError, match="verbatim"):
        value._validate_raw_grounding(slot, {"normalization_audit": []}, raw)
    raw["verdicts"][0]["evidence"][0] = {"kind": "summary", "exact_quote": None, "summary": "summary", "reference": "artifact"}
    with pytest.raises(ValueError, match="verbatim"):
        value._validate_raw_grounding(slot, {"normalization_audit": []}, raw)


def test_claim_boundary_rechecks_exact_head_before_writing(private_root, monkeypatch):
    value, root = private_root
    contacts = []
    monkeypatch.setattr(value, "_git", lambda *args: "0" * 40)
    monkeypatch.setattr(value._base(), "_four_state_original_claim_execution", lambda *args: contacts.append(True))
    with pytest.raises(ValueError, match="Exact source HEAD"):
        value._claim_execution(root, value.build_schedule())
    assert contacts == []


def test_execute_requires_both_authorities_before_contact(private_root):
    value, root = private_root
    contacts = []
    with pytest.raises(ValueError, match="allow-remote"):
        value.execute(root.parent, runner_call=lambda *args, **kwargs: contacts.append(True))
    with pytest.raises(ValueError, match="zero-incremental-charge"):
        value.execute(root.parent, allow_remote=True, runner_call=lambda *args, **kwargs: contacts.append(True))
    assert contacts == []


def test_public_package_has_no_private_fixture_prose_and_gate_never_promotes(private_root):
    value, _root = private_root
    public = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "run.py", "study.py", "study-contract.json"))
    assert "Amber dust settles" not in public
    assert "Inventory the latch" not in public
    assert "Hold the lantern low" not in public
    assert "Open the blue room" not in public
    assert value.contract()["gating"]["any_complete_valid_miss"] == "NO_GO_DSPY_ELIGIBLE_ONLY"
    assert value.contract()["gating"]["success_authorizes_only"] == "fresh_disjoint_holdout"


def test_cli_refuses_live_execution_without_both_authorities(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--execute", "--private-root", str(tmp_path)],
        cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "requires explicit authority" in result.stderr
