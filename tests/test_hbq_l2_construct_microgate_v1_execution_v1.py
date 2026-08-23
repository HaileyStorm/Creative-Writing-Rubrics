from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root
from hbqrs import runner as production_runner


ROOT = book_root() / "evaluation-results" / "hbq-l2-construct-microgate-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("l2_construct_microgate_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record(slot, *, verdict: str | None = None):
    return {
        "slot_id": slot["slot_id"],
        "logical_sample_id": slot["logical_sample_id"],
        "run_id": slot["run_id"],
        "verdict": verdict or "YES",
        "response_sha256": "a" * 64,
        "attachment_sha256": slot["image_input"]["sha256"] if slot["image_input"] else None,
        "normalization_audit": [],
    }


def _fake_auth(command, **kwargs):
    assert kwargs["timeout"] == 20
    assert "OPENAI_API_KEY" not in kwargs["env"]
    if command[-1] == "--version":
        return type("Result", (), {"returncode": 0, "stdout": "codex-cli test", "stderr": ""})()
    assert command[-2:] == ["login", "status"]
    return type("Result", (), {"returncode": 0, "stdout": "Logged in using ChatGPT", "stderr": ""})()


@pytest.fixture
def private_root() -> Path:
    """The executor must reject test roots nested inside the public checkout."""
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-microgate-exec-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(autouse=True)
def no_api_credential_environment(monkeypatch: pytest.MonkeyPatch):
    for name in tuple(os.environ):
        if "API_KEY" in name.upper() or name.upper().startswith("OPENAI_API_"):
            monkeypatch.delenv(name, raising=False)


def test_exact_freeze_geometry_and_expected_ledger_exclusion():
    s = study()
    assert s.validate_package() == {
        "study_id": s.STUDY_ID, "slots": 24, "provider_calls": 0,
        "predecessor": s.PREDECESSOR_COMMIT, "visual_png_slots": 6,
        "expected_ledger_opened": False,
    }
    schedule = s.build_schedule()
    assert len(schedule) == len({slot["slot_id"] for slot in schedule}) == 24
    assert len({(slot["case_id"], slot["leaf_id"]) for slot in schedule}) == 8
    assert sum(slot["image_input"] is not None for slot in schedule) == 6
    assert not any("expected_verdict" in json.dumps(slot) for slot in schedule)
    assert all(slot["condition"]["attempt_lifecycle_policy"] == "terminal_sidecar_v1" for slot in schedule)


def test_all_24_frozen_prompts_match_production_compiled_bytes_and_aggregate():
    s = study()
    predecessor = s._predecessor()
    records = predecessor.compiled_leaf_records()
    artifacts = s._artifact_by_case()
    schedule = s.build_schedule()
    for slot in schedule:
        artifact = artifacts[slot["case_id"]]
        expected = production_runner._render_prompt(
            binary_prompt=s._frozen_binary_prompt(),
            artifact={"name": artifact["artifact_name"], "text": artifact["text"]},
            contexts=[],
            bundle_id=artifact["bundle_id"],
            artifact_id="public-synthetic-artifact",
            questions=[records[slot["leaf_id"]]],
            task_contract_context=predecessor.task_context_for(artifact),
        )
        assert slot["prompt"].encode("utf-8") == expected.encode("utf-8")
    hashes = {slot["slot_id"]: s.sha256_bytes(slot["prompt"].encode("utf-8")) for slot in schedule}
    assert s.sha256_bytes(s.canonical_json(hashes)) == "92c146ef3d047b4edd5448fca787cc430f024a114bdb0a1d68f224088bffce7f"


def test_dry_run_freezes_exact_png_attachment_no_image_control_and_disclosure(private_root: Path):
    s = study()
    report = s.dry_run(private_root, auth_call=_fake_auth)
    assert report["provider_calls"] == 0 and report["visual_png_slots"] == 6
    schedule = s.build_schedule()
    image_slot = next(slot for slot in schedule if slot["image_input"])
    image_path = Path(s.command_for(image_slot, private_root)[s.command_for(image_slot, private_root).index("--image") + 1])
    assert image_path.stat().st_size == 129853
    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    c04 = next(slot for slot in schedule if slot["case_id"] == "c04")
    assert "--image" not in s.command_for(c04, private_root)
    disclosure = json.loads((private_root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert len(disclosure["slots"]) == 24
    assert "expected" not in json.dumps(disclosure).casefold()
    assert disclosure["terminal_sidecar_format_version"] == 5
    auth = json.loads((private_root / "receipts" / "subscription-authentication.v1.json").read_text(encoding="utf-8"))
    assert auth["authentication"] == "chatgpt_subscription"
    assert len(auth["binary_sha256"]) == len(auth["version_stdout_sha256"]) == len(auth["login_status_stdout_sha256"]) == 64


def test_execute_requires_dual_gate_and_never_offers_resume(private_root: Path):
    s = study()
    s.dry_run(private_root, auth_call=_fake_auth)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(private_root)
    assert "resume" not in (ROOT / "run.py").read_text(encoding="utf-8")


def test_aggregate_only_write_once_settlement_and_gate_precedence(private_root: Path):
    s = study()
    s.dry_run(private_root, auth_call=_fake_auth)
    schedule = s.build_schedule()
    scores = {slot["slot_id"]: True for slot in schedule}
    result = s.settle(private_root, verifier=lambda _root, slot: _record(slot), scorer=lambda slot, _record: scores[slot["slot_id"]])
    assert result["decision"] == "FIXTURE_DRIVEN_CLOSE_NO_CHANGE"
    public = json.loads((private_root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    assert set(public) == {"study_id", "decision", "completed_slots", "planned_slots", "aggregate_cells", "visual_attachment_slots", "promotion"}
    assert public["aggregate_cells"] == {"zero_of_three": 0, "one_of_three": 0, "two_of_three": 0, "three_of_three": 8, "total": 8}
    with pytest.raises(ValueError, match="frozen aggregate-only"):
        s.settle(private_root, verifier=lambda _root, slot: _record(slot), scorer=lambda _slot, _record: True)

    variance_root = private_root / "variance"
    s.dry_run(variance_root, auth_call=_fake_auth)
    first_cell = [(slot["slot_id"], slot["case_id"], slot["leaf_id"]) for slot in schedule][:3]
    variance_scores = {slot["slot_id"]: True for slot in schedule}
    variance_scores[first_cell[0][0]] = False
    assert s.settle(variance_root, verifier=lambda _root, slot: _record(slot), scorer=lambda slot, _record: variance_scores[slot["slot_id"]])["decision"] == "VARIANCE_NO_GO"


def test_clean_zero_of_three_is_only_leaf_specific_treatment_design_eligibility(private_root: Path):
    s = study()
    s.dry_run(private_root, auth_call=_fake_auth)
    schedule = s.build_schedule()
    cell = {(slot["case_id"], slot["leaf_id"]) for slot in schedule}
    target = next(iter(cell))
    scores = {slot["slot_id"]: (slot["case_id"], slot["leaf_id"]) != target for slot in schedule}
    result = s.settle(private_root, verifier=lambda _root, slot: _record(slot), scorer=lambda slot, _record: scores[slot["slot_id"]])
    assert result["decision"] == "LEAF_SPECIFIC_TREATMENT_DESIGN_ELIGIBLE"
    assert result["promotion"] == "none"


def test_subscription_auth_rejects_api_environment(monkeypatch: pytest.MonkeyPatch):
    s = study()
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    with pytest.raises(ValueError, match="billing credential environment"):
        s.subscription_authentication(runner_call=_fake_auth)


def test_semantic_input_binding_uses_exact_freeze_blob_not_mutable_head(monkeypatch: pytest.MonkeyPatch):
    s = study()
    original = s._git_bytes

    def altered(*args):
        if args[-1].endswith("registry/question_index.jsonl"):
            return b"{not json}"
        return original(*args)

    monkeypatch.setattr(s, "_git_bytes", altered)
    with pytest.raises(Exception):
        s._frozen_leaf_records.cache_clear()
        s.validate_package()


def test_c03_logical_artifact_hash_binds_png_bytes_and_one_contact_timeout_terminalizes_all(private_root: Path):
    s = study()
    s.dry_run(private_root, auth_call=_fake_auth)
    schedule = s.build_schedule()
    c03 = next(slot for slot in schedule if slot["case_id"] == "c03")
    assert c03["artifact_sha256"] == s._artifact_sha256(c03["artifact_text"], c03["image_input"])
    assert c03["artifact_sha256"] != s.sha256_bytes(c03["artifact_text"].encode("utf-8"))
    command = s.command_for(c03, private_root)
    assert command[command.index("--disable") + 1] == "shell_tool"
    assert command[command.index("unbounded_connection_retries") - 1] == "--disable"
    assert "unbounded_connection_retries=false" not in command
    contacts = []

    def timed_out(command, **kwargs):
        contacts.append((command, kwargs))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(RuntimeError, match="no resend"):
        s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=timed_out, auth_call=_fake_auth)
    assert len(contacts) == 1 and contacts[0][1]["timeout"] == 120
    assert "OPENAI_API_KEY" not in contacts[0][1]["env"]
    terminal = [json.loads(s._sidecar_path(private_root, slot).read_text(encoding="utf-8")) for slot in schedule]
    assert len(terminal) == 24
    assert terminal[0]["state"] == "ambiguous_contact"
    assert all(value["format_version"] == 5 and value["maximum_physical_attempts"] == 1 for value in terminal)
    assert all(value["state"] == "blocked_before_dispatch" for value in terminal[1:])


def test_partial_nonzero_contact_terminalizes_every_remaining_slot_without_retry(private_root: Path):
    s = study()
    s.dry_run(private_root, auth_call=_fake_auth)
    schedule = s.build_schedule()
    contacts = []

    def partial(command, **kwargs):
        contacts.append((command, kwargs))
        return type("Result", (), {"returncode": 1, "stdout": "partial", "stderr": "transport interrupted"})()

    with pytest.raises(RuntimeError, match="no resend"):
        s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=partial, auth_call=_fake_auth)
    assert len(contacts) == 1
    terminal = [json.loads(s._sidecar_path(private_root, slot).read_text(encoding="utf-8")) for slot in schedule]
    assert terminal[0]["state"] == "ambiguous_contact"
    assert all(value["state"] == "blocked_before_dispatch" for value in terminal[1:])
    with pytest.raises(ValueError, match="one physical attempt"):
        s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=partial, auth_call=_fake_auth)


def test_successful_mocked_24_contact_path_uses_attested_binary_and_terminal_sidecars(private_root: Path):
    s = study()
    s.dry_run(private_root, auth_call=_fake_auth)
    contacts = []

    def accepted(command, **kwargs):
        contacts.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        question_id = next(line for line in kwargs["input"].splitlines() if '"question_id":' in line).split('"')[3]
        output.write_text(json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "summary", "reference": "supplied synthetic artifact", "exact_quote": None, "summary": "Grounded assessment of the supplied artifact."}], "note": "Synthetic test response."}]}), encoding="utf-8")
        return type("Result", (), {"returncode": 0, "stdout": "completed", "stderr": "provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()

    result = s.execute(private_root, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=accepted, auth_call=_fake_auth)
    assert result["completed_slots"] == 24 and len(contacts) == 24
    authentication = json.loads((private_root / "receipts" / "subscription-authentication.v1.json").read_text(encoding="utf-8"))
    assert all(call[0][0] == authentication["binary_path"] for call in contacts)
    assert len({id(call[1]["env"]) for call in contacts}) == 1
    command = contacts[0][0]
    for feature in ("unbounded_connection_retries", "browser_use_external", "tool_call_mcp_elicitation", "auth_elicitation"):
        assert command[command.index(feature) - 1] == "--disable"
    assert command[command.index('approval_policy="never"') - 1] == "-c"
    assert command[command.index("mcp_servers={}") - 1] == "-c"
    schedule = s.build_schedule()
    terminal = [json.loads(s._sidecar_path(private_root, slot).read_text(encoding="utf-8")) for slot in schedule]
    assert len(terminal) == 24 and all(value["state"] == "accepted" for value in terminal)
    receipts = [json.loads((s._attempt_dir(private_root, slot) / "receipt.json").read_text(encoding="utf-8")) for slot in schedule]
    assert all(value["reported"] == {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"} for value in receipts)
    assert all(value["environment_value_sha256"] == authentication["environment_value_sha256"] for value in receipts)
