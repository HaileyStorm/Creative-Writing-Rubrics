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
    / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2"
)


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v2_test", ROOT / "study.py")
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
        ("private-absence", "absence", "NOT_APPLICABLE", "a-000000000001"),
        ("private-inert", "accidental_inert_duplicate", "NO", "a-000000000002"),
        ("private-functional", "functional_recurrence", "YES", "a-000000000003"),
        ("private-incomplete", "incomplete_indicated_recurrence", "CANNOT_ASSESS", "a-000000000004"),
    )
    fixtures = [
        {
            "fixture_id": fixture_id,
            "state": state,
            "role": "target" if verdict == "NO" else "control",
            "expected_verdict": verdict,
            "declared_scope": "complete poem" if verdict != "CANNOT_ASSESS" else "excerpt",
            "completion_status": "complete" if verdict != "CANNOT_ASSESS" else "excerpt",
            "contexts": [f"Synthetic context {index}."],
            "text": f"Synthetic quoted evidence {index}.",
        }
        for index, (fixture_id, state, verdict, _artifact_id) in enumerate(states, start=1)
    ]
    controller = {
        "study_id": value.STUDY_ID,
        "format_version": 2,
        "visibility": "private_controller_only",
        "fixture_matrix": fixtures,
    }
    combinations = [(row, repeat) for row in states for repeat in (1, 2, 3)]
    ledger = {
        "study_id": value.STUDY_ID,
        "format_version": 2,
        "visibility": "private_controller_only",
        "slot_mapping": [
            {
                "opaque_slot_id": f"q-{index:012x}",
                "fixture_id": row[0],
                "opaque_artifact_id": row[3],
                "arm": "candidate",
                "repeat": repeat,
            }
            for index, (row, repeat) in enumerate(combinations, start=1)
        ],
    }
    (root / "private-controller.json").write_text(json.dumps(controller), encoding="utf-8")
    (root / "private-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (root / "verify_private_freeze.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    def frozen():
        return controller, ledger

    monkeypatch.setattr(value, "_private_freeze", frozen)
    monkeypatch.setattr(value._v1(), "_private_freeze", frozen)
    monkeypatch.setattr(value._v1()._adapter(), "_private_freeze", frozen)
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
    artifact_id = command[command.index("--artifact-id") + 1]
    leaf = find_leaf(json.loads(registry.read_text(encoding="utf-8")), "form.poetry.free_verse.repetition")
    assert leaf is not None
    prompt = f"Artifact ID: {artifact_id}\nfrozen prompt\n{leaf['text']}\n"
    return SimpleNamespace(returncode=0, stdout=prompt.encode(), stderr=b"")


def test_v2_binds_stale_zero_call_v1_and_fresh_private_commitments(private_root):
    value, _root = private_root
    report = value.validate_package()
    assert report["slots"] == 12 and report["provider_calls"] == 0
    assert report["provider_artifacts"] == 4 and report["semantic_identifier_hits_allowed"] == 0
    predecessor = value.contract()["v1_provider_free_predecessor"]
    assert predecessor["provider_calls"] == 0
    assert predecessor["execution_claim"] == "none"
    assert predecessor["disposition"] == "stale_semantic_identifier_leak_not_reusable"


def test_schedule_translates_private_semantics_to_opaque_provider_identifiers(private_root):
    value, root = private_root
    schedule = value.build_schedule()
    assert len(schedule) == 12
    assert len({slot["fixture_id"] for slot in schedule}) == 4
    assert all(value.OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule)
    assert all(value.OPAQUE_SLOT.fullmatch(slot["opaque_slot_id"]) for slot in schedule)
    assert all(slot["private_fixture_id"] != slot["fixture_id"] for slot in schedule)
    live = value.command_for(schedule[0], root, render=False)
    assert live[live.index("--artifact-id") + 1] == schedule[0]["fixture_id"]
    assert schedule[0]["private_fixture_id"] not in live
    assert schedule[0]["opaque_slot_id"] not in live


def test_prompt_scan_accepts_public_labels_but_rejects_private_semantics_and_oracles(private_root):
    value, _root = private_root
    schedule = value.build_schedule()
    prompts = {
        slot["opaque_slot_id"]: f"Artifact ID: {slot['fixture_id']}\n{value.CANDIDATE_TEXT}".encode()
        for slot in schedule
    }
    receipt = value._prompt_scan(schedule, prompts)
    assert receipt["semantic_identifier_hits"] == receipt["oracle_binding_hits"] == 0
    assert receipt["private_slot_identifier_hits"] == receipt["provider_artifact_mismatches"] == 0
    first = schedule[0]
    prompts[first["opaque_slot_id"]] += f"\n{first['private_fixture_id']}".encode()
    with pytest.raises(ValueError, match="leakage"):
        value._prompt_scan(schedule, prompts)
    prompts[first["opaque_slot_id"]] = f"Artifact ID: {first['fixture_id']}\nexpected_verdict: NO\n{value.CANDIDATE_TEXT}".encode()
    with pytest.raises(ValueError, match="leakage"):
        value._prompt_scan(schedule, prompts)


def test_provider_free_dry_run_writes_zero_hit_privacy_receipt(private_root):
    value, root = private_root
    report = value.dry_run(root.parent, runner_call=fake_render)
    assert report["provider_calls"] == 0
    assert report["rendered_prompts"] == report["candidate_prompt_checks"] == 12
    privacy = json.loads((root / "receipts" / "provider-prompt-privacy-scan.v2.json").read_text(encoding="utf-8"))
    assert privacy["prompts_scanned"] == 12 and privacy["provider_artifacts"] == 4
    assert privacy["semantic_identifier_hits"] == privacy["oracle_binding_hits"] == 0
    assert privacy["private_slot_identifier_hits"] == privacy["provider_artifact_mismatches"] == 0


def test_claim_requires_exact_privacy_receipt_and_exact_head(private_root, monkeypatch):
    value, root = private_root
    contacts = []
    monkeypatch.setattr(value._base(), "_four_state_original_claim_execution", lambda *args: contacts.append(True))
    with pytest.raises(ValueError, match="privacy receipt"):
        value._claim_execution(root, value.build_schedule())
    monkeypatch.setattr(value._v1(), "_git", lambda *args: "0" * 40)
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


def test_public_package_has_no_private_fixture_prose_or_mapping(private_root):
    value, _root = private_root
    public = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "run.py", "study.py", "study-contract.json"))
    assert "Amber dust settles" not in public
    assert "Inventory the latch" not in public
    assert "Hold the lantern low" not in public
    assert "Open the blue room" not in public
    assert "s1-four-state-private-absence" not in public
    assert value.contract()["identifier_boundary"]["prompt_privacy_receipt"] == "required_before_claim"


def test_cli_refuses_live_execution_without_both_authorities(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--execute", "--private-root", str(tmp_path)],
        cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "requires explicit authority" in result.stderr
