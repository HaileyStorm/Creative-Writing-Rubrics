"""Offline contract tests for the separate Ox polarity live boundary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-ox-alpha-polarity-batch-successor-v1"
V8_FAILURE = Path(os.environ.get("HBQ_OX_ALPHA_V8_ROOT", str(Path.home() / "Documents" / "cwr-ox-alpha-v8-full-scoring-20260821-73308d2"))) / "runs" / "ox-alpha-v8-01"
V9_ROOT = Path(os.environ.get("HBQ_OX_ALPHA_V9_ROOT", str(Path.home() / "Documents" / "cwr-ox-alpha-v9-scoring-20260822-db87d90")))


def load(name: str, file: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / file); assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules[spec.name] = module; sys.modules.update(aliases or {})
    try: spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None: sys.modules.pop(key, None)
            else: sys.modules[key] = value
    return module


study = load("ox_successor_live_study", "study.py")
live = load("ox_successor_live", "live.py", {"study": study})


def input_root(tmp_path: Path, row: dict[str, object]) -> tuple[dict[str, object], dict[str, str]]:
    artifact, prompt, contract = (tmp_path / "artifact.txt", tmp_path / "prompt.txt", tmp_path / "contract.json")
    artifact.write_text("artifact", encoding="utf-8"); prompt.write_text("prompt", encoding="utf-8")
    contract.write_text("{}", encoding="utf-8")
    inputs = {str(row["story_id"]): {"artifact": str(artifact), "prompt": str(prompt), "task_contract": str(contract), "frozen_inputs": {"source.md": live.fingerprint(artifact), "prompt.md": live.fingerprint(prompt), "task-contract.json": live.fingerprint(contract)}}}
    for polarity in ("positive", "negative_failure"):
        path = tmp_path / "projections" / f"{polarity}.registry.json"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}", encoding="utf-8")
    return {"schedule": [row]}, inputs[str(row["story_id"])]


def install_inputs(work: Path, inputs: dict[str, str]) -> None:
    live._immutable(work / "private-inputs.json", {next(iter(study.STORIES)): inputs})


def fake_frozen(row: dict[str, object]) -> dict[str, object]:
    return {"study_id": study.HERE.name, "schedule": [row]}


def test_exact_30_call_schedule_maps_to_cap_one_requests_without_counterpart_co_batching(tmp_path):
    rows = study.schedule()
    assert len(rows) == 30
    assert all(len(row["question_ids"]) in {1, 4} for row in rows)
    for row in rows:
        opposite = "negative_failure" if row["polarity"] == "positive" else "positive"
        assert not any(other["polarity"] == opposite and other["call_id"] == row["call_id"] for other in rows)
    row = next(item for item in rows if item["condition_id"] == "negative_failure_batch4")
    frozen, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    binding = live._binding(tmp_path, row)
    assert binding["provider"]["max_physical_http_attempts_per_logical_request"] == 1
    assert binding["question_ids"] == list(study.QUESTION_IDS)
    assert frozen["schedule"][0]["polarity"] == "negative_failure"


def test_private_projection_changes_exactly_the_four_reviewed_question_texts(tmp_path):
    projected = json.loads(live._projection(tmp_path, "negative_failure").read_text(encoding="utf-8"))
    original = json.loads((book_root() / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    def collect(value, output):
        if isinstance(value, dict):
            if value.get("type") == "question": output[value.get("id")] = value.get("text")
            for child in value.values(): collect(child, output)
        elif isinstance(value, list):
            for child in value: collect(child, output)
    before, after = {}, {}; collect(original, before); collect(projected, after)
    changed = {key for key in before if before[key] != after.get(key)}
    assert changed == set(study.QUESTION_IDS)
    assert {key: after[key] for key in study.QUESTION_IDS} == study.reviewed_pairs()


def test_all_30_real_inputs_compile_to_runner_order_without_provider_contact(tmp_path):
    frozen_path = V9_ROOT / "frozen-ox-alpha-v9-contract.json"
    if not frozen_path.is_file(): pytest.skip("set HBQ_OX_ALPHA_V9_ROOT to a sealed v9 root")
    inputs = live._inputs(json.loads(frozen_path.read_text(encoding="utf-8")))
    seen = []
    for row in study.schedule():
        registry = live._projection(tmp_path, row["polarity"])
        effective = live._effective_question_ids(row, inputs[row["story_id"]], registry)
        assert set(effective) == set(row["question_ids"])
        assert len(effective) == len(row["question_ids"])
        seen.append((row["call_id"], tuple(effective)))
    assert len(seen) == 30
    assert sum(len(ids) == 1 for _, ids in seen) == 24
    assert sum(len(ids) == 4 for _, ids in seen) == 6


def test_malformed_or_non524_failure_quarantines_and_is_never_resent(monkeypatch, tmp_path):
    row = study.schedule()[0]; _, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    monkeypatch.setattr(live, "load_frozen", lambda _: fake_frozen(row))
    monkeypatch.setattr(live, "_assert_fresh_zero_cost", lambda _: None)
    monkeypatch.setattr(live, "_claim", lambda _: tmp_path / "test-claim")
    monkeypatch.setattr(live, "_effective_question_ids", lambda row, *_: list(row["question_ids"]))
    calls: list[str] = []
    def fail(**kwargs):
        calls.append(str(kwargs["output_dir"])); raise RuntimeError("HTTP 500 malformed provider failure")
    monkeypatch.setattr(live, "run_judge", fail)
    assert live.execute(tmp_path) == 1
    assert live.execute(tmp_path) == 0
    history = live._histories(tmp_path)[row["call_id"]]
    assert len(calls) == len(history) == 1
    assert history[0]["status"] == "quarantined"


def test_verified_524_can_retry_with_same_hashes_and_distinct_attempt_identity(monkeypatch, tmp_path):
    row = study.schedule()[0]; _, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    monkeypatch.setattr(live, "load_frozen", lambda _: fake_frozen(row))
    monkeypatch.setattr(live, "_assert_fresh_zero_cost", lambda _: None)
    monkeypatch.setattr(live, "_claim", lambda _: tmp_path / "test-claim")
    monkeypatch.setattr(live, "_effective_question_ids", lambda row, *_: list(row["question_ids"]))
    binding = live._binding(tmp_path, row)
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    live._append(tmp_path, {"kind": "intent", "call_id": row["call_id"], "attempt": 1, "at": old, "binding": binding})
    live._append(tmp_path, {"kind": "result", "call_id": row["call_id"], "attempt": 1, "binding": binding, "result": {"status": "eligible_524", "at": old, "static_binding": binding["static_sha256"], "prompt": {"bytes": 1, "sha256": "a" * 64}, "request": {"bytes": 1, "sha256": "b" * 64}, "failed_identities": {"session_id": "failed-session", "logical_request_id": "failed-logical", "receipt_sha256": "c" * 64, "serialization_proof_sha256": "d" * 64}}})
    def succeed(**kwargs):
        destination = Path(kwargs["output_dir"]); destination.mkdir(parents=True)
        (destination / "verdicts.jsonl").write_text(json.dumps({"question_id": row["question_ids"][0], "verdict": "YES", "confidence": 0.9}) + "\n", encoding="utf-8")
        return {"run_id": "new-run"}
    monkeypatch.setattr(live, "run_judge", succeed)
    monkeypatch.setattr(live, "_accepted", lambda *_: {"status": "accepted", "static_binding": binding["static_sha256"], "prompt": {"bytes": 1, "sha256": "a" * 64}, "request": {"bytes": 1, "sha256": "b" * 64}, "accepted_identities": {"receipt_id": "accepted-receipt", "session_id": "accepted-session", "logical_request_id": "accepted-logical"}, "records": []})
    assert live.execute(tmp_path) == 1
    history = live._histories(tmp_path)[row["call_id"]]
    assert [item["status"] for item in history] == ["eligible_524", "accepted"]
    assert history[0]["static_binding"] == history[1]["static_binding"]
    assert history[0]["failed_identities"]["logical_request_id"] != history[1]["accepted_identities"]["logical_request_id"]


def test_524_with_inbound_or_result_bearing_evidence_cannot_be_promoted(tmp_path):
    attempt = tmp_path / "attempt"; evidence = attempt / "x.nous.evidence"; evidence.mkdir(parents=True)
    (evidence / "events.jsonl").write_text("\n".join(json.dumps(item) for item in [
        {"event_type": "http_attempt", "data": {"status": 524}},
        {"event_type": "message", "data": {"direction": "inbound"}},
    ]) + "\n", encoding="utf-8")
    assert live._v9_error_status(RuntimeError("HTTP 524")) == "candidate_524"
    with pytest.raises(ValueError): live._eligible_524(attempt)
    (evidence / "events.jsonl").write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 524}}) + "\n", encoding="utf-8")
    (attempt / "response.nous.result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError): live._eligible_524(attempt)


def test_eligible_524_replays_the_real_sealed_v9_lineage_when_available():
    if not V8_FAILURE.is_dir(): pytest.skip("sealed v8 failure root unavailable")
    result = live._eligible_524(V8_FAILURE)
    assert result["status"] == "eligible_524"
    assert result["failed_identities"]["logical_request_id"]


@pytest.mark.parametrize("error", [RuntimeError("HTTP 402"), RuntimeError("charge signal")])
def test_charge_signals_create_global_stop_and_stop_future_execution(monkeypatch, tmp_path, error):
    row = study.schedule()[0]; _, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    monkeypatch.setattr(live, "load_frozen", lambda _: {"study_id": study.HERE.name, "schedule": study.schedule()})
    monkeypatch.setattr(live, "_assert_fresh_zero_cost", lambda _: None)
    monkeypatch.setattr(live, "_claim", lambda _: tmp_path / "test-claim")
    monkeypatch.setattr(live, "_effective_question_ids", lambda row, *_: list(row["question_ids"]))
    monkeypatch.setattr(live, "run_judge", lambda **_: (_ for _ in ()).throw(error))
    assert live.execute(tmp_path) == 1
    assert list((tmp_path / "pauses").glob("*-global-stop.json"))
    with pytest.raises(ValueError, match="Global stop"):
        live.execute(tmp_path)


def test_o_excl_claim_rejects_a_second_executor(tmp_path):
    live._immutable(tmp_path / live.FROZEN_NAME, {"test": True})
    first = live._claim(tmp_path)
    assert first.is_file()
    with pytest.raises(ValueError, match="O_EXCL"):
        live._claim(tmp_path)


def test_provider_identity_cannot_cross_from_failed_to_accepted():
    histories = {"call": [
        {"status": "eligible_524", "failed_identities": {"session_id": "same", "logical_request_id": "same-logical", "receipt_sha256": "a", "serialization_proof_sha256": "b"}},
        {"status": "accepted", "accepted_identities": {"receipt_id": "r", "session_id": "same", "logical_request_id": "new-logical"}},
    ]}
    with pytest.raises(ValueError, match="collides"):
        live._assert_identities(histories)


def test_six_first_attempt_eligible_524s_write_a_global_pause(monkeypatch, tmp_path):
    row = study.schedule()[0]; _, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    schedule = [{**row, "call_id": f"call-{number}"} for number in range(6)]
    monkeypatch.setattr(live, "load_frozen", lambda _: {"study_id": study.HERE.name, "schedule": schedule})
    monkeypatch.setattr(live, "_assert_fresh_zero_cost", lambda _: None)
    monkeypatch.setattr(live, "_claim", lambda _: tmp_path / "test-claim")
    monkeypatch.setattr(live, "_effective_question_ids", lambda row, *_: list(row["question_ids"]))
    monkeypatch.setattr(live, "run_judge", lambda **_: (_ for _ in ()).throw(RuntimeError("HTTP 524")))
    counter = iter(range(6))
    def eligible(_):
        number = next(counter)
        return {"status": "eligible_524", "prompt": {"bytes": 1, "sha256": "a" * 64}, "request": {"bytes": 1, "sha256": "b" * 64}, "failed_identities": {"session_id": f"s{number}", "logical_request_id": f"l{number}", "receipt_sha256": f"{number:064x}", "serialization_proof_sha256": f"{number+6:064x}"}}
    monkeypatch.setattr(live, "_eligible_524", eligible)
    assert live.execute(tmp_path) == 6
    assert list((tmp_path / "pauses").glob("*-six-eligible-524.json"))


def test_partial_screen_exposes_progress_but_cannot_settle(monkeypatch, tmp_path):
    row = study.schedule()[0]; _, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    live._immutable(tmp_path / live.FROZEN_NAME, {"test": True})
    monkeypatch.setattr(live, "load_frozen", lambda _: {"study_id": study.HERE.name, "schedule": study.schedule()})
    binding = live._binding(tmp_path, row)
    live._append(tmp_path, {"kind": "intent", "call_id": row["call_id"], "attempt": 1, "at": "2026-08-22T00:00:00+00:00", "binding": binding})
    live._append(tmp_path, {"kind": "result", "call_id": row["call_id"], "attempt": 1, "binding": binding, "result": {"status": "accepted", "static_binding": binding["static_sha256"], "accepted_identities": {"receipt_id": "r", "session_id": "s", "logical_request_id": "l"}, "records": [{"status": "accepted", "story_id": row["story_id"], "condition_id": row["condition_id"], "polarity": row["polarity"], "question_id": row["question_ids"][0], "verdict": "YES", "confidence": 0.8}]}})
    payload = live.progress(tmp_path)
    assert payload["kind"] == "successor_progress_snapshot"
    assert payload["production_recommendation"] is None
    with pytest.raises(ValueError, match="Cannot settle"):
        live.settle(tmp_path)
    assert not (tmp_path / "settlement.json").exists()


def test_global_stop_can_seal_a_stopped_settlement_with_unsent_count(monkeypatch, tmp_path):
    row = study.schedule()[0]; _, inputs = input_root(tmp_path, row); install_inputs(tmp_path, inputs)
    live._immutable(tmp_path / live.FROZEN_NAME, {"test": True})
    monkeypatch.setattr(live, "load_frozen", lambda _: {"study_id": study.HERE.name, "schedule": study.schedule()})
    binding = live._binding(tmp_path, row)
    live._append(tmp_path, {"kind": "intent", "call_id": row["call_id"], "attempt": 1, "at": "2026-08-22T00:00:00+00:00", "binding": binding})
    live._append(tmp_path, {"kind": "result", "call_id": row["call_id"], "attempt": 1, "binding": binding, "result": {"status": "global_stop", "static_binding": binding["static_sha256"]}})
    payload = live.settle(tmp_path)
    assert payload["status"] == "stopped"
    assert payload["unsent_calls_after_global_stop"] == 29
    assert payload["confirmation_available"] is False
