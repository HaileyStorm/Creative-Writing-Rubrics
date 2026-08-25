from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from _hbq_s1_historical_runtime import install_historical_runtime
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v4"
CANDIDATE_TEXT = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))["candidate"]["text"]


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v4_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return install_historical_runtime(module, source_commit=module.SOURCE_COMMIT)


@pytest.fixture
def private_root(tmp_path: Path, monkeypatch):
    value = study()
    states = (
        ("no-recurrence", "NOT_APPLICABLE", "a-91f6c3b82d70"), ("copy-echo", "NO", "a-b07d5e2c9418"),
        ("turning-refrain", "YES", "a-4d8b2e610ac7"), ("omitted-return", "CANNOT_ASSESS", "a-62e9a4d70bc1"),
    )
    controller = {"study_id": value.STUDY_ID, "format_version": 4, "visibility": "private_controller_only", "fixture_matrix": [
        {"fixture_id": f"test-{name}", "state": name, "role": "target" if verdict == "NO" else "control", "expected_verdict": verdict,
         "declared_scope": "complete poem" if verdict != "CANNOT_ASSESS" else "excerpt", "completion_status": "complete" if verdict != "CANNOT_ASSESS" else "excerpt",
         "contexts": [f"Context {index}."], "text": f"Quoteable v4 evidence {index}."}
        for index, (name, verdict, _artifact) in enumerate(states, start=1)
    ]}
    ledger = {"study_id": value.STUDY_ID, "format_version": 4, "visibility": "private_controller_only", "slot_mapping": [
        {"opaque_slot_id": f"q-{index + 512:012x}", "fixture_id": f"test-{row[0]}", "opaque_artifact_id": row[2], "arm": "candidate", "repeat": repeat}
        for index, (row, repeat) in enumerate(((row, repeat) for row in states for repeat in (1, 2, 3)), start=1)
    ]}
    del tmp_path
    root = Path(tempfile.mkdtemp(prefix="hbq-s1-v4-"))
    (root / "private-controller.json").write_text(json.dumps(controller), encoding="utf-8")
    (root / "private-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (root / "verify_private_freeze.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(value, "_private_freeze", lambda: (controller, ledger))
    value.set_private_root(root)
    try:
        yield value, root / value.PRIVATE_EXECUTION_DIRECTORY
    finally:
        shutil.rmtree(root, ignore_errors=True)


def fake_render(command, **kwargs):
    artifact_id = command[command.index("--artifact-id") + 1]
    runtime = Path(kwargs["env"]["HBQRS_ROOT"])
    prompt = (runtime / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout=f"Artifact ID: {artifact_id}\n{prompt}\n{CANDIDATE_TEXT}\n".encode(), stderr=b"")


def payload(quote="Quoteable v4 evidence 1."):
    return {"verdicts": [{"question_id": "form.poetry.free_verse.repetition", "verdict": "NOT_APPLICABLE", "confidence": 0.9,
        "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote, "summary": None}], "note": "Grounded."}]}


def test_historical_overlay_contains_the_full_nested_adapter_chain():
    value = study()
    root = value._historical_runtime_root / "evaluation-results"
    names = [
        "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1",
        *[f"hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v{version}" for version in range(1, 5)],
    ]
    assert all((root / name / "study.py").is_file() for name in names)
    assert value._configure().ROOT == value.ROOT
    value.assert_historical_runtime()


def test_v4_separates_v2_snapshot_from_current_no_result(private_root):
    value, _root = private_root
    report = value.validate_package()
    assert report["slots"] == 12 and report["provider_calls"] == 0
    contract = value.contract()
    snapshot = contract["v2_historical_preexecution_snapshot"]
    outcome = contract["v2_current_outcome_binding"]
    assert snapshot["provider_calls_at_snapshot"] == 0 and snapshot["execution_claim_at_snapshot"] == "none"
    assert outcome["formal_result"] == "NO_RESULT" and outcome["strict_evidence_gate"] == {"matched": 10, "total": 12, "summary_items": 2}


def test_exact_quote_protocol_replaces_summary_evidence(private_root):
    value, _root = private_root
    schema = json.loads(value.SCHEMA_SOURCE.read_text(encoding="utf-8"))
    validate(payload(), schema)
    invalid = payload(); invalid["verdicts"][0]["evidence"][0]["summary"] = "not allowed"
    with pytest.raises(ValidationError):
        validate(invalid, schema)


def test_v4_schedule_is_fresh_and_provider_opaque(private_root):
    value, root = private_root
    schedule = value.build_schedule()
    assert len(schedule) == 12 and len({slot["fixture_id"] for slot in schedule}) == 4
    assert all(value._v3()._v2().OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule)
    command = value.command_for(schedule[0], root, render=False)
    assert command[command.index("--artifact-id") + 1] == schedule[0]["fixture_id"]
    assert schedule[0]["private_fixture_id"] not in command


def test_provider_free_dry_run_writes_v4_protocol_receipt(private_root):
    value, root = private_root
    report = value.dry_run(root.parent, runner_call=fake_render)
    assert report["provider_calls"] == 0 and report["rendered_prompts"] == 12
    protocol = json.loads((root / "receipts" / "evidence-protocol-scan.v4.json").read_text(encoding="utf-8"))
    assert protocol["format_version"] == 4 and protocol["generic_summary_instruction_hits"] == 0
    assert not (root / "receipts" / "evidence-protocol-scan.v3.json").exists()


def test_protocol_scan_rejects_reintroduced_generic_summary_instruction(private_root):
    value, _root = private_root
    value._v3()._write_runtime_book()
    schedule = value.build_schedule()
    exact = value.PROMPT_SOURCE.read_bytes() + b"\n" + CANDIDATE_TEXT.encode()
    prompts = {slot["opaque_slot_id"]: exact for slot in schedule}
    assert value._v3()._protocol_prompt_scan(schedule, prompts)["format_version"] == 4
    prompts[schedule[0]["opaque_slot_id"]] += b"\nuse `summary` for an evidence description"
    with pytest.raises(ValueError, match="replace"):
        value._v3()._protocol_prompt_scan(schedule, prompts)


def test_claim_requires_freeze_receipts_before_contact(private_root, monkeypatch):
    value, root = private_root
    contacts = []
    monkeypatch.setattr(value._v3()._base(), "_four_state_original_claim_execution", lambda *args: contacts.append(True))
    with pytest.raises(ValueError, match="privacy receipt"):
        value._v3()._claim_execution(root, value.build_schedule())
    assert contacts == []


def test_execute_requires_both_authorities_before_contact(private_root):
    value, root = private_root
    with pytest.raises(ValueError, match="allow-remote"):
        value.execute(root.parent)
    with pytest.raises(ValueError, match="zero-incremental-charge"):
        value.execute(root.parent, allow_remote=True)


def test_public_package_excludes_private_v4_prose(private_root):
    value, _root = private_root
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    assert "Mica rain taps" not in public and "Stack the yellow plates" not in public
    assert value.contract()["promotion"] == "none"


def test_cli_refuses_live_execution_without_both_authorities(tmp_path: Path):
    result = subprocess.run([sys.executable, str(ROOT / "run.py"), "--execute", "--private-root", str(tmp_path)], cwd=ROOT,
        text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 2 and "requires explicit authority" in result.stderr
