from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from _hbq_s1_historical_runtime import install_historical_runtime
from hbqrs.paths import book_root

ROOT = (
    book_root()
    / "evaluation-results"
    / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v3"
)
CANDIDATE_TEXT = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))["candidate"]["text"]


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v3_test", ROOT / "study.py")
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
        ("fresh-zero", "absence", "NOT_APPLICABLE", "a-100000000001"),
        ("fresh-copy", "accidental_inert_duplicate", "NO", "a-100000000002"),
        ("fresh-change", "functional_recurrence", "YES", "a-100000000003"),
        ("fresh-omitted", "incomplete_indicated_recurrence", "CANNOT_ASSESS", "a-100000000004"),
    )
    fixtures = [
        {
            "fixture_id": fixture_id,
            "state": state,
            "role": "target" if verdict == "NO" else "control",
            "expected_verdict": verdict,
            "declared_scope": "complete poem" if verdict != "CANNOT_ASSESS" else "excerpt",
            "completion_status": "complete" if verdict != "CANNOT_ASSESS" else "excerpt",
            "contexts": [f"Fresh context {index}."],
            "text": f"Fresh quoteable evidence {index}.",
        }
        for index, (fixture_id, state, verdict, _artifact_id) in enumerate(states, start=1)
    ]
    controller = {
        "study_id": value.STUDY_ID,
        "format_version": 3,
        "visibility": "private_controller_only",
        "fixture_matrix": fixtures,
    }
    combinations = [(row, repeat) for row in states for repeat in (1, 2, 3)]
    ledger = {
        "study_id": value.STUDY_ID,
        "format_version": 3,
        "visibility": "private_controller_only",
        "slot_mapping": [
            {
                "opaque_slot_id": f"q-{index + 256:012x}",
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
    monkeypatch.setattr(value._v2(), "_private_freeze", frozen)
    monkeypatch.setattr(value._v2()._v1(), "_private_freeze", frozen)
    monkeypatch.setattr(value._v2()._v1()._adapter(), "_private_freeze", frozen)
    monkeypatch.setattr(value._base(), "_private_freeze", frozen)
    value.set_private_root(root)
    return value, root / value.PRIVATE_EXECUTION_DIRECTORY


def fake_render(command, **kwargs):
    artifact_id = command[command.index("--artifact-id") + 1]
    runtime = Path(kwargs["env"]["HBQRS_ROOT"])
    prompt = (runtime / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8")
    text = f"Artifact ID: {artifact_id}\n{prompt}\n{CANDIDATE_TEXT}\n"
    return SimpleNamespace(returncode=0, stdout=text.encode(), stderr=b"")


def valid_payload(quote="Fresh quoteable evidence 1."):
    return {
        "verdicts": [{
            "question_id": "form.poetry.free_verse.repetition",
            "verdict": "NOT_APPLICABLE",
            "confidence": 0.9,
            "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote, "summary": None}],
            "note": "Grounded.",
        }]
    }


def test_v3_binds_immutable_zero_call_v2_and_fresh_private_freeze(private_root):
    value, _root = private_root
    report = value.validate_package()
    assert report["slots"] == 12 and report["provider_calls"] == 0
    assert report["summary_evidence_available"] is False
    predecessor = value.contract()["v2_provider_free_predecessor"]
    assert predecessor["provider_calls"] == 0 and predecessor["execution_claim"] == "none"
    assert predecessor["disposition"] == "immutable_provider_free_evidence_protocol_successor"


def test_prompt_replaces_generic_evidence_instruction_without_contradiction(private_root):
    value, _root = private_root
    value._validate_protocol_sources()
    prompt = value.PROMPT_SOURCE.read_text(encoding="utf-8")
    assert "`kind` set exactly to `exact_quote`" in prompt
    assert "`summary` set to JSON `null`" in prompt
    assert "set `kind` to `exact_quote` or `summary`" not in prompt
    assert "use `summary` for an evidence description" not in prompt


def test_schema_makes_summary_unavailable_and_rejects_empty_or_summary_evidence(private_root):
    value, _root = private_root
    schema = json.loads(value.SCHEMA_SOURCE.read_text(encoding="utf-8"))
    validate(valid_payload(), schema)
    summary = valid_payload()
    summary["verdicts"][0]["evidence"][0] = {
        "kind": "summary", "reference": "artifact", "exact_quote": None, "summary": "description"
    }
    with pytest.raises(ValidationError):
        validate(summary, schema)
    empty = valid_payload("")
    with pytest.raises(ValidationError):
        validate(empty, schema)
    nonnull_summary = valid_payload()
    nonnull_summary["verdicts"][0]["evidence"][0]["summary"] = "not allowed"
    with pytest.raises(ValidationError):
        validate(nonnull_summary, schema)


def test_v3_schedule_uses_fresh_opaque_provider_identifiers(private_root):
    value, root = private_root
    schedule = value.build_schedule()
    assert len(schedule) == 12 and len({slot["fixture_id"] for slot in schedule}) == 4
    assert all(value._v2().OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule)
    live = value.command_for(schedule[0], root, render=False)
    assert live[live.index("--artifact-id") + 1] == schedule[0]["fixture_id"]
    assert schedule[0]["private_fixture_id"] not in live


def test_provider_free_dry_run_freezes_exact_quote_runtime_and_receipts(private_root):
    value, root = private_root
    report = value.dry_run(root.parent, runner_call=fake_render)
    assert report["provider_calls"] == 0
    assert report["rendered_prompts"] == report["candidate_prompt_checks"] == 12
    protocol = json.loads((root / "receipts" / "evidence-protocol-scan.v3.json").read_text(encoding="utf-8"))
    assert protocol["exact_quote_instruction_matches"] == 12
    assert protocol["generic_summary_instruction_hits"] == 0
    assert protocol["summary_evidence_available"] is False
    frozen_schema = json.loads((root / "runtime-book-v3" / "schema" / "hbq_judge_response.schema.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        validate({"verdicts": [{**valid_payload()["verdicts"][0], "evidence": [{"kind": "summary", "reference": "x", "exact_quote": None, "summary": "x"}]}]}, frozen_schema)


def test_protocol_scan_rejects_reintroduced_generic_summary_instruction(private_root):
    value, _root = private_root
    value._write_runtime_book()
    schedule = value.build_schedule()
    exact = value.PROMPT_SOURCE.read_bytes() + b"\n" + value._v2().CANDIDATE_TEXT.encode()
    prompts = {slot["opaque_slot_id"]: exact for slot in schedule}
    assert value._protocol_prompt_scan(schedule, prompts)["summary_evidence_available"] is False
    prompts[schedule[0]["opaque_slot_id"]] += b"\nuse `summary` for an evidence description"
    with pytest.raises(ValueError, match="replace"):
        value._protocol_prompt_scan(schedule, prompts)


def test_claim_requires_privacy_and_protocol_receipts_before_contact(private_root, monkeypatch):
    value, root = private_root
    contacts = []
    monkeypatch.setattr(value._base(), "_four_state_original_claim_execution", lambda *args: contacts.append(True))
    with pytest.raises(ValueError, match="privacy receipt"):
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


def test_public_package_contains_no_fresh_private_prose(private_root):
    value, _root = private_root
    names = ("README.md", "run.py", "study.py", "study-contract.json", "exact-quote-binary-prompt.md", "exact-quote-response.schema.json")
    public = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in names)
    assert "Copper pollen drifts" not in public
    assert "Count the green crate" not in public
    assert "Keep the window open" not in public
    assert "Turn toward the red field" not in public
    assert value.contract()["promotion"] == "none"


def test_cli_refuses_live_execution_without_both_authorities(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--execute", "--private-root", str(tmp_path)],
        cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "requires explicit authority" in result.stderr
