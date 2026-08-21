from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hbqrs.paths import book_root
from hbqrs.runner import _render_prompt


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v1"


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules.update(aliases or {})
    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


study = load("ox_alpha_study", "study.py")
analysis = load("ox_alpha_analysis", "analyze_pilot.py", {"study": study})
pilot = load("ox_alpha_pilot", "run_pilot.py", {"study": study, "analyze_pilot": analysis})


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _primary(tmp_path: Path) -> tuple[Path, Path, Path, list[dict]]:
    primary, public = tmp_path / "primary", tmp_path / "gpt-public"
    rows: list[dict] = []
    for number in range(1, 89):
        digest = f"{number:064x}"
        item = f"item-{number}"
        folder = primary / "inputs" / "development" / item
        folder.mkdir(parents=True)
        (folder / "source.md").write_text(f"public story {number}", encoding="utf-8")
        (folder / "prompt.md").write_text(f"public prompt {number}", encoding="utf-8")
        _write(folder / "task-contract.json", {"contract_id": "hanna", "artifact_id": item})
        rows.append({"item_id": item, "model": "M", "story_sha256": digest * 64, "prompt_sha256": ("z" if number == 1 else "y") * 64, "external_input": {name: study.fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}})
    _write(primary / "frozen-run-contract.json", {"study_id": "hbq-human-alignment-v3", "study_contract_sha256": "d" * 64, "runtime_sha256": "e" * 64, "package_commit": "f" * 40, "frozen_before_execution": True, "partitions": {"development": rows}, "question_ids": [f"q-{number}" for number in range(178)], "runtime_files": {"src/hbqrs/core.py": {"name": "core.py", "bytes": 1, "sha256": "a" * 64}, "prompts/judge/BINARY_EVALUATION_PROMPT.md": {"name": "BINARY_EVALUATION_PROMPT.md", "bytes": 1, "sha256": "b" * 64}, "schema/hbq_judge_response.schema.json": {"name": "hbq_judge_response.schema.json", "bytes": 1, "sha256": "c" * 64}}, "selection": {"seed": 77}})
    public.mkdir()
    items = public / "items.jsonl"
    items.write_text("".join(json.dumps({"item_id": row["item_id"], "story_id": f"story-{number}", "source_model": row["model"], "quartile": 1, "prompt_group_id": f"group-{number}", "story_sha256": row["story_sha256"], "prompt_sha256": row["prompt_sha256"], "human_ratings": {}, "human_means": {}, "human_overall": 0, "hbq_full_observed_score": number, "hbq_mapping": {}, "evidence": {}}) + "\n" for number, row in enumerate(rows, 1)), encoding="utf-8")
    canonical = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": "development", "study_contract_sha256": "d" * 64, "runtime_sha256": "e" * 64, "package_commit": "f" * 40}
    _write(public / "summary.json", {**canonical, "item_count": 88})
    _write(public / "manifest.json", {**canonical, "files": {path.name: {"bytes": path.stat().st_size, "sha256": study.sha(path)} for path in (public / "items.jsonl", public / "summary.json")}})
    catalog, usage = tmp_path / "zero-cost-catalog", tmp_path / "zero-cost-usage"
    catalog.mkdir(); usage.mkdir()
    sealed_at = datetime.now(timezone.utc).isoformat()
    _write(catalog / "manifest.json", {"schema": "codex-nous-evidence-v1", "mode": "catalog", "requested_provider": "nous", "requested_model": "deepseek/deepseek-v4-flash-0731", "requested_reasoning_effort": "max"})
    _write(catalog / "receipt.json", {"schema": "codex-nous-outcome-v1", "status": "success", "sealed_at": sealed_at, "receipt_sha256": "c" * 64})
    (catalog / "events.jsonl").write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 200, "response_body": {"data": [{"id": "stealth/ox-alpha", "canonical_slug": "stealth/ox-alpha", "pricing": {"prompt": "0.0000000000", "completion": "0.0000000000"}}]}}}) + "\n", encoding="utf-8")
    _write(usage / "manifest.json", {"schema": "codex-nous-evidence-v1", "mode": "judge", "requested_provider": "nous", "requested_model": "stealth/ox-alpha", "requested_reasoning_effort": "max"})
    _write(usage / "receipt.json", {"schema": "codex-nous-outcome-v1", "status": "success", "sealed_at": sealed_at, "receipt_sha256": "u" * 64})
    (usage / "events.jsonl").write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 200, "response_body": {"model": "stealth/ox-alpha", "usage": {"cost": 0, "cost_details": {"upstream_inference_completions_cost": 0, "upstream_inference_cost": 0, "upstream_inference_prompt_cost": 0}}}}}) + "\n", encoding="utf-8")
    proof = tmp_path / "zero-cost-proof.json"
    _write(proof, {"schema": "codex-nous-ox-alpha-zero-cost-proof-v3", "catalog_evidence_root": str(catalog), "usage_evidence_root": str(usage)})
    return primary, public, proof, rows


def _use_fixture_primary(monkeypatch):
    monkeypatch.setattr(study, "_canonical_primary", lambda path: study.read_json(path / "frozen-run-contract.json"))
    monkeypatch.setattr(study, "_validate_bridge_evidence", lambda root: {"valid": True, "receipt_sha256": study.read_json(root / "receipt.json")["receipt_sha256"]})


def test_contract_declares_zero_paid_eighteen_request_provisional_geometry():
    assert study.CONTRACT["provider"]["model"] == "stealth/ox-alpha"
    assert study.CONTRACT["runtime"]["maximum_logical_requests"] == 18
    assert study.CONTRACT["runtime"]["workers"] == 1
    assert study.CONTRACT["zero_cost"]["no_purchase"] is True
    assert "Missing provider max attestation" in " ".join(study.CONTRACT["interpretation_limits"])


def test_freeze_is_outcome_blind_and_rejects_primary_or_gpt_hash_drift(tmp_path, monkeypatch):
    primary, public, proof, rows = _primary(tmp_path)
    _use_fixture_primary(monkeypatch)
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path / "managed-repo")
    monkeypatch.setattr(study, "runtime_bindings", lambda: {"runner": {"name": "runner", "bytes": 1, "sha256": "r"}})
    frozen = study.freeze_work(primary, public, proof, tmp_path / "work")
    assert [cell["item_id"] for cell in frozen["cells"]] == [rows[0]["item_id"], rows[1]["item_id"], rows[2]["item_id"]]
    assert "hbq_full_observed_score" not in json.dumps(frozen)
    assert study.load_frozen(tmp_path / "work") == frozen
    (public / "items.jsonl").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="GPT paired reference"):
        study.load_frozen(tmp_path / "work")


@pytest.mark.parametrize("payload", ['{"study_id":"one","study_id":"two"}', '{"item_id":"one","item_id":"two"}'])
def test_strict_json_rejects_duplicate_study_and_item_keys(payload):
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        study.strict_json(payload, label="fixture")


def test_strict_json_rejects_duplicate_verdict_key():
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        study.strict_json('{"verdicts":[{"question_id":"q","verdict":"NO","verdict":"YES"}]}', label="provider-response")


def test_freeze_rejects_duplicate_gpt_item_and_noncanonical_phase(tmp_path, monkeypatch):
    primary, public, proof, _ = _primary(tmp_path)
    _use_fixture_primary(monkeypatch)
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path / "managed-repo")
    monkeypatch.setattr(study, "runtime_bindings", lambda: {})
    rows = (public / "items.jsonl").read_text(encoding="utf-8").splitlines()
    (public / "items.jsonl").write_text(rows[0] + "\n" + rows[0] + "\n", encoding="utf-8")
    manifest = study.read_json(public / "manifest.json")
    manifest["files"]["items.jsonl"] = {"bytes": (public / "items.jsonl").stat().st_size, "sha256": study.sha(public / "items.jsonl")}
    _write(public / "manifest.json", manifest)
    with pytest.raises(ValueError, match="duplicate item_id"):
        study.freeze_work(primary, public, proof, tmp_path / "work")
    primary, public, proof, _ = _primary(tmp_path / "third")
    _write(public / "summary.json", {"study_id": "hbq-human-alignment-v3", "phase": "confirmatory", "study_contract_sha256": "d" * 64, "runtime_sha256": "e" * 64})
    with pytest.raises(ValueError, match="canonical primary development"):
        study.freeze_work(primary, public, proof, tmp_path / "third-work")


def test_freeze_rejects_repo_or_overlapping_private_roots(tmp_path, monkeypatch):
    primary, public, proof, _ = _primary(tmp_path)
    _use_fixture_primary(monkeypatch)
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path / "managed-repo")
    monkeypatch.setattr(study, "runtime_bindings", lambda: {})
    with pytest.raises(ValueError, match="distinct and non-overlapping"):
        study.freeze_work(primary, public, proof, primary)
    with pytest.raises(ValueError, match="outside the repository"):
        study.freeze_work(study.REPO_ROOT, public, proof, tmp_path / "work")
    nested_usage = primary / "nested-usage"; nested_usage.mkdir()
    with pytest.raises(ValueError, match="distinct and non-overlapping"):
        study._external_separate(primary, public, proof, nested_usage, tmp_path / "other-work")


def test_zero_cost_proof_rejects_charge_or_unsealed_evidence(tmp_path, monkeypatch):
    _, _, proof, _ = _primary(tmp_path)
    _use_fixture_primary(monkeypatch)
    value = study.read_json(proof)
    events = Path(value["usage_evidence_root"]) / "events.jsonl"
    event = study.strict_json(events.read_text(encoding="utf-8"), label="fixture")
    event["data"]["response_body"]["usage"]["cost"] = 1
    events.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cost"):
        study._zero_cost_proof(proof)


def test_receipt_requires_unattested_provisional_evidence_under_the_same_root(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "_validate_provider_artifacts", lambda *_: None)
    root = "responses/batch-0001.attempt-0001.nous.evidence"
    events = tmp_path / root / "events.jsonl"; events.parent.mkdir(parents=True)
    (tmp_path / "responses").mkdir(exist_ok=True); (tmp_path / "responses" / "accepted.json").write_text('{"verdicts":[]}', encoding="utf-8")
    events.write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 200, "response_body": {"choices": [{"message": {"content": "{\"verdicts\":[]}"}}]}}}) + "\n", encoding="utf-8")
    record = {"response_artifact": {"path": "responses/accepted.json"}, "provider": {"requested": {"model": "stealth/ox-alpha", "reasoning_effort": "max"}, "reported": {"provider": "nous", "model": "stealth/ox-alpha"}, "provider_canonical_model": "stealth/ox-alpha", "reasoning_attested": False, "reasoning_attestation": "provider_did_not_report_reasoning_effort", "tool_free": True, "exact_gate_eligible": False, "transport_policy": analysis.NOUS_TRANSPORT_POLICY, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0, "evidence_sha256": "a" * 64, "serialization_proof_sha256": "b" * 64, "provider_artifacts": {"judge_request": {}, "judge_result": {}, "serialization_proof": {"path": root + "/proof.json"}, "evidence_tree": {"path": root}}}}
    assert analysis._receipt(tmp_path, record).startswith("nous:")
    record["provider"]["provider_artifacts"]["serialization_proof"]["path"] = "responses/proof.json"
    with pytest.raises(ValueError, match="EvidenceRoot"):
        analysis._receipt(tmp_path, record)


def test_receipt_rejects_recovered_or_non_2xx_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "_validate_provider_artifacts", lambda *_: None)
    root = "responses/batch-0001.attempt-0001.nous.evidence"; events = tmp_path / root / "events.jsonl"; events.parent.mkdir(parents=True)
    (tmp_path / "responses").mkdir(exist_ok=True); (tmp_path / "responses" / "accepted.json").write_text('{"verdicts":[]}', encoding="utf-8")
    events.write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 524, "response_body": {"choices": [{"message": {"content": "{\"verdicts\":[]}"}}]}}}) + "\n", encoding="utf-8")
    provider = {"requested": {"model": "stealth/ox-alpha", "reasoning_effort": "max"}, "reported": {"provider": "nous", "model": "stealth/ox-alpha"}, "provider_canonical_model": "stealth/ox-alpha", "reasoning_attested": False, "reasoning_attestation": "provider_did_not_report_reasoning_effort", "tool_free": True, "exact_gate_eligible": False, "transport_policy": analysis.NOUS_TRANSPORT_POLICY, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0, "evidence_sha256": "a" * 64, "serialization_proof_sha256": "b" * 64, "provider_artifacts": {"judge_request": {}, "judge_result": {}, "serialization_proof": {"path": root + "/proof.json"}, "evidence_tree": {"path": root}}}
    with pytest.raises(ValueError, match="non-2xx"):
        analysis._receipt(tmp_path, {"response_artifact": {"path": "responses/accepted.json"}, "provider": provider})
    events.write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 200, "response_body": {"choices": [{"message": {"content": "{\"verdicts\":[]}"}}]}}}) + "\n", encoding="utf-8")
    provider["recovered_request_count"] = 1
    with pytest.raises(ValueError, match="one-request"):
        analysis._receipt(tmp_path, {"response_artifact": {"path": "responses/accepted.json"}, "provider": provider})


def test_receipt_rejects_duplicate_key_in_raw_sealed_provider_message(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "_validate_provider_artifacts", lambda *_: None)
    root = "responses/batch-0001.attempt-0001.nous.evidence"
    events = tmp_path / root / "events.jsonl"; events.parent.mkdir(parents=True)
    (tmp_path / "responses").mkdir(exist_ok=True)
    (tmp_path / "responses" / "accepted.json").write_text('{"verdicts":[]}', encoding="utf-8")
    raw = '{"verdicts":[],"verdicts":[]}'
    events.write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 200, "response_body": {"choices": [{"message": {"content": raw}}]}}}) + "\n", encoding="utf-8")
    provider = {"requested": {"model": "stealth/ox-alpha", "reasoning_effort": "max"}, "reported": {"provider": "nous", "model": "stealth/ox-alpha"}, "provider_canonical_model": "stealth/ox-alpha", "reasoning_attested": False, "reasoning_attestation": "provider_did_not_report_reasoning_effort", "tool_free": True, "exact_gate_eligible": False, "transport_policy": analysis.NOUS_TRANSPORT_POLICY, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0, "evidence_sha256": "a" * 64, "serialization_proof_sha256": "b" * 64, "provider_artifacts": {"judge_request": {}, "judge_result": {}, "serialization_proof": {"path": root + "/proof.json"}, "evidence_tree": {"path": root}}}
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        analysis._receipt(tmp_path, {"response_artifact": {"path": "responses/accepted.json"}, "provider": provider})


def test_pilot_is_serial_one_attempt_and_stops_after_first_failure(tmp_path, monkeypatch):
    frozen = {"cells": [{"cell_id": "ox-alpha-01", "item_id": "one", "question_ids": ["q"]}, {"cell_id": "ox-alpha-02", "item_id": "two", "question_ids": ["q"]}], "provider": study.CONTRACT["provider"], "zero_cost_proof": {"catalog": {"sealed_at": "2026-08-21T00:00:00+00:00"}, "usage": {"sealed_at": "2026-08-21T00:00:00+00:00"}}}
    _write(tmp_path / "frozen-ox-alpha-contract.json", {})
    folder = tmp_path / "inputs"; folder.mkdir()
    for name in ("source.md", "prompt.md", "task-contract.json"):
        (folder / name).write_text("{}" if name.endswith("json") else "text", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen)
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    monkeypatch.setattr(pilot, "input_folder", lambda *_: folder)
    monkeypatch.setattr(pilot, "_verify_cell", lambda _work, _frozen, cell: {"cell": cell["cell_id"]})
    monkeypatch.setattr(pilot, "_assert_fresh_at", lambda *_: None)
    def fail_second(**kwargs):
        calls.append(kwargs["artifact_id"])
        Path(kwargs["output_dir"]).mkdir(parents=True)
        (Path(kwargs["output_dir"]) / "run.json").write_text("{}", encoding="utf-8")
        if kwargs["artifact_id"] == "two":
            raise RuntimeError("HTTP 402")
    monkeypatch.setattr(pilot, "run_judge", fail_second)
    with pytest.raises(RuntimeError, match="402"):
        pilot.execute(tmp_path)
    assert calls == ["one", "two"]
    records = pilot._records(tmp_path)
    assert [record["status"] for record in records] == ["completed", "failed"]
    with pytest.raises(ValueError, match="immutable evidence"):
        pilot.execute(tmp_path)


def test_pilot_rechecks_zero_cost_freshness_before_claim_or_provider_call(tmp_path, monkeypatch):
    frozen = {"cells": [], "zero_cost_proof": {"catalog": {"sealed_at": "2000-01-01T00:00:00+00:00"}, "usage": {"sealed_at": "2000-01-01T00:00:00+00:00"}}}
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen)
    with pytest.raises(ValueError, match="not fresh at preparation"):
        pilot.execute(tmp_path)
    assert not (tmp_path / "pilot-invocation.json").exists()
    assert not (tmp_path / "pilot-execution-claim.json").exists()


def test_public_analyzer_does_not_emit_paths_or_prose(tmp_path, monkeypatch):
    work, public = tmp_path / "private-work", tmp_path / "gpt-public"
    work.mkdir(); public.mkdir()
    frozen = {"primary_work_dir": str(work), "gpt_reference": {"output": str(public)}, "cells": [{"cell_id": "ox-alpha-01", "item_id": "one", "source_model": "M", "story_sha256": "a" * 64, "prompt_sha256": "b" * 64}]}
    (work / "runs" / "ox-alpha-01").mkdir(parents=True)
    _write(work / "runs" / "ox-alpha-01" / "score.json", {"final_score": {"observed": 3.0}})
    monkeypatch.setattr(analysis, "load_frozen", lambda _: frozen)
    monkeypatch.setattr(analysis, "verify_evidence", lambda *_: [{"cell_id": "ox-alpha-01", "item_id": "one", "receipt_count": 6, "physical_http_attempt_count": 6}])
    monkeypatch.setattr(analysis, "_gpt_pairs", lambda *_: {"one": {"hbq_full_observed_score": 2.0}})
    analysis.analyze(work, tmp_path / "published")
    text = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "published").iterdir())
    assert str(work) not in text and "source.md" not in text and "prompt.md" not in text


def test_ox_prompt_explicitly_names_verdict_fields_and_allowed_values():
    prompt = _render_prompt(binary_prompt="judge", artifact={"name": "source.md", "text": "text"}, contexts=[], bundle_id="prose.short_story", artifact_id="one", questions=[{"question": {"id": "q"}}], provider="nous", model="stealth/ox-alpha")
    assert "exactly these keys: `question_id`, `verdict`, `confidence`, `evidence`, and `note`" in prompt
    assert "`YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS`" in prompt
