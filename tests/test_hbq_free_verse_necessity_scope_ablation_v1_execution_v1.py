from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-free-verse-necessity-scope-ablation-v1-execution-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("necessity_scope_ablation_executor", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_payload(slot):
    quote = next(line for line in slot["artifact_text"].splitlines() if line.strip())
    return {"verdicts": [{"question_id": slot["leaf_id"], "verdict": "YES", "confidence": 0.75, "evidence": [{"kind": "exact_quote", "reference": slot["artifact_name"], "exact_quote": quote, "summary": None}], "note": "Public synthetic exact-quote check."}]}


def test_zero_call_contract_binds_reviewed_freeze_and_exact_schedule():
    study = load_study()
    report = study.validate_package()
    assert report["provider_calls"] == 0 and report["slots"] == 36
    assert report["prompt_aggregate_sha256"] == "27bf3b9ccb7700abf8b13fcb7d0d4ffb131e4324cbde209c44f1827da61ebd67"
    contract = study.contract()
    assert contract["execution"]["provider"] == "codex"
    assert contract["execution"]["model"] == "gpt-5.6-sol"
    assert contract["execution"]["reasoning"] == "high"
    assert contract["execution"]["paid_fallback"] == "forbidden"
    assert contract["execution"]["provider_calls_authorized_by_this_freeze"] is False
    schedule = study.build_schedule()
    assert len(schedule) == len({row["slot_id"] for row in schedule}) == 36
    assert {(row["case_id"], row["leaf_id"], row["repeat"]) for row in schedule} == {(case_id, leaf_id, repeat) for case_id in study.predecessor().EXPECTED for leaf_id in study.LEAVES for repeat in range(1, 4)}
    assert all(row["prompt"].count(row["leaf_id"]) >= 1 for row in schedule)
    assert all(next(leaf for leaf in study.LEAVES if leaf != row["leaf_id"]) not in row["prompt"] for row in schedule)


def test_reviewed_predecessor_bytes_and_schema_are_fail_closed(monkeypatch):
    study = load_study()
    study._verify_predecessor_bytes()
    assert study.sha256_bytes(study.predecessor().git_show_bytes("schema/hbq_judge_response.schema.json")) == study.contract()["validation"]["schema_git_show_sha256"]
    altered = deepcopy(study.contract())
    altered["execution"]["paid_fallback"] = "allowed"
    monkeypatch.setattr(study, "contract", lambda: altered)
    with pytest.raises(ValueError, match="Execution successor contract"):
        study.validate_package()


def test_prepare_is_external_private_and_writes_only_immutable_zero_call_artifacts(tmp_path):
    study = load_study()
    report = study.prepare(tmp_path)
    assert report["provider_calls"] == 0 and report["rendered_prompts"] == 36 and report["terminal_records"] == 0
    manifest = json.loads((tmp_path / "study-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["slots"]) == 36
    assert len(list((tmp_path / "rendered-prompts").glob("*.txt"))) == 36
    assert len(list((tmp_path / "inputs").glob("*.txt"))) == 36
    with pytest.raises(ValueError, match="outside"):
        study.prepare(study.REPOSITORY / "private-root-forbidden")


def test_claim_then_terminal_is_one_shot_and_schema_evidence_checked(tmp_path):
    study = load_study()
    study.prepare(tmp_path)
    slot = study.build_schedule()[0]
    claim = study.claim_slot(tmp_path, slot["slot_id"])
    assert claim["state"] == "claimed_before_contact" and claim["attempt"] == 1
    with pytest.raises(ValueError, match="retry/resume"):
        study.claim_slot(tmp_path, slot["slot_id"])
    terminal = study.record_terminal(tmp_path, slot["slot_id"], valid_payload(slot))
    assert terminal["state"] == "terminal_schema_and_evidence_valid"
    bad = valid_payload(slot)
    bad["verdicts"][0]["evidence"][0]["exact_quote"] = "not in the artifact"
    with pytest.raises(ValueError, match="artifact-grounded"):
        study.validate_response(slot, bad)
    with pytest.raises(ValueError, match="All claimed slots"):
        study.settle(tmp_path)


def test_provider_free_cli_has_no_remote_execution_surface():
    verified = subprocess.run([sys.executable, str(ROOT / "run.py"), "--verify"], text=True, capture_output=True, check=True)
    assert json.loads(verified.stdout)["provider_calls"] == 0
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "--execute" not in text
        assert "import requests" not in text and "from requests" not in text
        assert "subprocess.run" not in text
