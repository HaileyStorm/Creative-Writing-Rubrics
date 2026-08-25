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
    / "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1"
)


def study():
    spec = importlib.util.spec_from_file_location("s1_clean_na_execution_test", ROOT / "study.py")
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
    fixture = {
        "fixture_id": "synthetic-clean-na",
        "role": "control",
        "expected_verdict": "NOT_APPLICABLE",
        "declared_scope": "complete free-verse poem",
        "completion_status": "complete",
        "contexts": ["Complete free-verse poem."],
        "text": "Synthetic private fixture.",
    }
    controller = {
        "study_id": value.STUDY_ID,
        "format_version": 1,
        "visibility": "private_controller_only",
        "fixture_matrix": [fixture],
    }
    ledger = {
        "study_id": value.STUDY_ID,
        "format_version": 1,
        "visibility": "private_controller_only",
        "slot_mapping": [
            {
                "opaque_slot_id": f"s1cleanna-v1-slot-{repeat:02d}",
                "fixture_id": fixture["fixture_id"],
                "arm": "candidate",
                "repeat": repeat,
            }
            for repeat in (1, 2, 3)
        ],
    }
    (root / "private-controller.json").write_text(json.dumps(controller), encoding="utf-8")
    (root / "private-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (root / "verify_private_freeze.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    def frozen():
        return controller, ledger

    monkeypatch.setattr(value, "_private_freeze", frozen)
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


def record(slot, verdict="NOT_APPLICABLE"):
    return {
        "opaque_slot_id": slot["opaque_slot_id"],
        "terminal_lifecycle": "accepted_no_semantic_retry",
        "accepted": True,
        "verdict": verdict,
        "receipt_sha256": "0" * 64,
    }


def test_exact_head_template_result_runtime_and_candidate_are_bound(private_root):
    value, _root = private_root
    report = value.validate_package()
    assert report == {
        "study_id": value.STUDY_ID,
        "source_commit": value.SOURCE_COMMIT,
        "slots": 3,
        "provider_calls": 0,
        "success_authorizes_only": "fresh_disjoint_holdout",
    }
    assert value.contract()["candidate"]["prompt_delta"] == "none_from_predecessor_candidate"
    assert value.contract()["promotion"] == "none"


def test_schedule_is_candidate_only_singleton_three_repeat_and_blind(private_root):
    value, root = private_root
    schedule = value.build_schedule()
    assert len(schedule) == len({slot["opaque_slot_id"] for slot in schedule}) == 3
    assert {slot["arm"] for slot in schedule} == {"candidate"}
    assert {slot["repeat"] for slot in schedule} == {1, 2, 3}
    assert {slot["condition"]["batch_size"] for slot in schedule} == {1}
    assert {slot["condition"]["batch_attempts"] for slot in schedule} == {1}
    live = value.command_for(schedule[0], root, render=False)
    assert live[live.index("--batch-size") + 1] == "1"
    assert live[live.index("--batch-attempts") + 1] == "1"
    assert live[live.index("--reasoning") + 1] == "high"
    assert live[live.index("--model") + 1] == "gpt-5.6-sol"


def test_provider_free_dry_run_freezes_three_prompts_without_contact(private_root):
    value, root = private_root
    report = value.dry_run(root.parent, runner_call=fake_render)
    assert report["provider_calls"] == 0
    assert report["rendered_prompts"] == 3
    assert report["candidate_prompt_checks"] == 3
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert disclosure["planned_provider_sends"] == 3
    assert disclosure["semantic_retries"] == "forbidden"
    assert disclosure["paid_api_or_fallback_route"] == "forbidden"


def test_execute_requires_both_explicit_authorities_before_contact(private_root):
    value, root = private_root
    contacts = []
    with pytest.raises(ValueError, match="allow-remote"):
        value.execute(root.parent, runner_call=lambda *args, **kwargs: contacts.append(True))
    with pytest.raises(ValueError, match="zero-incremental-charge"):
        value.execute(root.parent, allow_remote=True, runner_call=lambda *args, **kwargs: contacts.append(True))
    assert contacts == []


def test_private_root_is_disjoint_and_public_files_contain_no_personal_path(private_root):
    value, _root = private_root
    assert value._historical_original_repository == book_root().resolve()
    with pytest.raises(ValueError, match="outside"):
        value.set_private_root(book_root())
    with pytest.raises(ValueError, match="disjoint"):
        value.set_private_root(book_root().parent)
    for name in ("README.md", "run.py", "study.py", "study-contract.json"):
        assert "C:\\Users\\" not in (ROOT / name).read_text(encoding="utf-8")


def test_private_gate_requires_three_of_three_and_never_promotes(private_root, monkeypatch):
    value, _root = private_root
    monkeypatch.setattr(value._base(), "_write_or_verify", lambda path, data: path.write_bytes(data))

    def assess(records):
        matches = sum(item["verdict"] == "NOT_APPLICABLE" for item in records)
        return {
            "study_id": value.STUDY_ID,
            "decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS" if matches == 3 else "NO_GO",
            "clean_na_matches": matches,
            "required": 3,
            "promotion": "none",
        }

    monkeypatch.setattr(value, "_derive_gate", lambda _root, records: assess(records))
    slots = value.build_schedule()
    assert assess([record(slot) for slot in slots])["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    miss = [record(slot) for slot in slots]
    miss[0]["verdict"] = "NO"
    assert assess(miss)["decision"] == "NO_GO"
    assert value.contract()["gating"]["success_authorizes_only"] == "fresh_disjoint_holdout"


def test_cli_refuses_live_execution_without_both_authorities(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--execute", "--private-root", str(tmp_path)],
        cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "requires explicit authority" in result.stderr
