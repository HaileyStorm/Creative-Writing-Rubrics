from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_pass_admission.py"


def load():
    spec = importlib.util.spec_from_file_location("dryad_sol_admission_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(subject, tmp_path: Path, monkeypatch, *, loaded_batches: int = 23):
    plan_root, execution = tmp_path / "plan", tmp_path / "execution"
    plan_root.mkdir(); execution.mkdir()
    ids = [f"q-{number:03d}" for number in range(178)]
    story = b"A small frozen story."
    pass_id = "measurement/train/0001/dryad-000000000000000000000001"
    run_path = f"runs/{pass_id}"; run = execution / run_path; run.mkdir(parents=True)
    (plan_root / "inputs").mkdir(); (plan_root / "inputs/story.txt").write_bytes(story)
    passes = [{"pass_id": pass_id, "logical_sample_id": "measurement-train-0001", "opaque_story_id": "dryad-000000000000000000000001", "input_path": "inputs/story.txt", "run_path": run_path, "source_sha256": _sha(story), "source_bytes": len(story), "batch_size": 8, "batches": 23}]
    for number in range(2, 237):
        passes.append({"pass_id": f"other/{number}", "logical_sample_id": f"other-{number}", "input_path": "inputs/story.txt", "run_path": f"runs/other/{number}", "source_sha256": _sha(story), "source_bytes": len(story), "batch_size": 8, "batches": 23})
    requests = []
    for ordinal in range(1, 5429):
        batch = (ordinal - 1) % 23 + 1
        which_pass = passes[(ordinal - 1) // 23]["pass_id"]
        chunk = ids[(batch - 1) * 8:batch * 8] if which_pass == pass_id else []
        requests.append({"ordinal": ordinal, "pass_id": which_pass, "batch_number": batch, "question_ids": chunk, "prompt_path": f"prompts/request-{ordinal:04d}.txt", "prompt_sha256": "0" * 64, "prompt_bytes": 0, "schema_path": f"schemas/request-{ordinal:04d}.json", "schema_sha256": "0" * 64, "schema_bytes": 0})
    for request in requests[:23]:
        prompt = f"prompt-{request['batch_number']}".encode(); schema = f"schema-{request['batch_number']}".encode()
        for key, raw in (("prompt_path", prompt), ("schema_path", schema)):
            path = plan_root / request[key]; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            request[key.replace("path", "sha256")] = _sha(raw); request[key.replace("path", "bytes")] = len(raw)
    plan = {"passes": passes, "requests": requests, "runtime": {"question_ids": ids}}
    plan_raw = subject._canonical(plan); (plan_root / "plan.json").write_bytes(plan_raw)
    monkeypatch.setattr(subject, "PLAN_SHA256", _sha(plan_raw))
    bindings = {"driver": "d" * 64, "adapter": "a" * 64, "runner": "b" * 64, "v3": "c" * 64, "core": "e" * 64}
    auth = {"schema_version": 1, "account_class": "subscription", "provider": "openai_codex", "route": "codex-chatgpt-gpt-5.6-sol", "evidence_class": "chatgpt_subscription_auth_status_v1", "checked_at": "2026-09-06T00:00:00+00:00", "expires_at": "2026-09-06T01:00:00+00:00", "status_hash": "f" * 64, "audit": {}}
    cost = {"schema_version": 1, "account_class": "subscription", "provider": "openai_codex", "route": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "kind": "subscription_included", "allowance_state": "available", "checked_at": "2026-09-06T00:00:00+00:00", "expires_at": "2026-09-06T01:00:00+00:00", "audit": {}}
    route = {"zero_charge": True, "armed": True, "account_class": "subscription", "provider": "openai_codex", "model": "gpt-5.6-sol", "reasoning_effort": "high", "timeout_seconds": 900, "codex_command": ["codex"], "codex_command_identity": {"version": 1, "artifacts": [{"index": 0, "sha256": "1" * 64, "path_hash": "2" * 64}]}, "auth_receipt_hash": _sha(subject._canonical(auth)), "cost_evidence": {"evidence_hash": _sha(subject._canonical(cost)), "checked_at": cost["checked_at"], "expires_at": cost["expires_at"], "kind": cost["kind"], "allowance_state": cost["allowance_state"]}}
    route_sha = _sha(subject._canonical(route)); reviews = set()
    for cohort in range(1, 4):
        ordinals = list(range((cohort - 1) * 10 + 1, min(cohort * 10 + 1, 5429)))
        review = {"schema_version": 1, "decision": "approved_sol_cohort", "plan_sha256": subject.PLAN_SHA256, "cohort_number": cohort, "ordinals": ordinals, "source_bindings": bindings, "route_sha256": route_sha, "reviewed_at": "2026-09-06T00:00:00+00:00", "expires_at": "2026-09-06T02:00:00+00:00", "reviewer_task": "sol-review"}
        raw = subject._canonical(review); sha = _sha(raw); reviews.add(sha)
        path = execution / f"cohorts/{cohort:04d}/reviews/{sha}.json"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    weight = {"weights": "fixture"}
    config = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "artifact_id": "measurement-train-0001", "question_ids": ids, "batch_size": 8, "retry_policy": {"batch_attempts": 1}, "attempt_lifecycle_policy": "terminal_sidecar_v1", "weight_profile": weight, "codex_bin": "codex"}
    (run / "run.json").write_bytes(subject._canonical({"configuration": config}))
    verdicts = [{"question_id": item, "verdict": "YES"} for item in ids[:loaded_batches * 8] if item in ids]
    if loaded_batches == 23:
        verdicts = [{"question_id": item, "verdict": "YES"} for item in ids]
    (run / "responses/schemas").mkdir(parents=True)
    for request in requests[:23]:
        number = request["batch_number"]; final = f'{{"batch":{number}}}'.encode()
        events = (json.dumps({"type": "thread.started", "thread_id": f"thread-{number}"}) + "\n" + json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": final.decode()}}) + "\n").encode()
        stderr = b""; message = run / f"responses/batch-{number:04d}.attempt-0001.message.json"; message.write_bytes(final)
        event_path = run / f"responses/batch-{number:04d}.attempt-0001.events.jsonl"; event_path.write_bytes(events)
        stderr_path = run / f"responses/batch-{number:04d}.attempt-0001.stderr.bin"; stderr_path.write_bytes(stderr)
        prompt = (plan_root / request["prompt_path"]).read_bytes(); (run / f"responses/batch-{number:04d}.prompt.txt.gz").write_bytes(gzip.compress(prompt))
        (run / f"responses/schemas/batch-{number:04d}.json").write_bytes((plan_root / request["schema_path"]).read_bytes())
        cohort = (request["ordinal"] - 1) // 10 + 1; review_sha = next(value for value in reviews if (execution / f"cohorts/{cohort:04d}/reviews/{value}.json").exists())
        metadata = {"schema_version": 1, "plan_sha256": subject.PLAN_SHA256, "ordinal": request["ordinal"], "source_bindings": bindings, "cohort_number": cohort, "review_sha256": review_sha, "route_sha256": route_sha, "route_snapshot": route, "authorized_at": "2026-09-06T00:30:00+00:00", "auth_receipt": auth, "cost_receipt": cost}
        command = ["codex", "exec", "--output-schema", str(run / f"responses/schemas/batch-{number:04d}.json"), "--output-last-message", str(message), "--disable", "code_mode", "-"]
        descriptor = lambda path: {"path": path.relative_to(run).as_posix(), "bytes": len(path.read_bytes()), "sha256": _sha(path.read_bytes())}
        checkpoint = {"accepted_attempt": 1, "question_ids": request["question_ids"], "response_artifact": descriptor(message), "provider": {"command": command, "provider_artifacts": {"codex_events": descriptor(event_path), "codex_stderr": descriptor(stderr_path)}, "dryad_sol": metadata}}
        (run / f"responses/batch-{number:04d}.json").write_bytes(subject._canonical(checkpoint))
    score = {"final_score": {"observed": 50.0}, "coverage": .9, "weight_profile": weight}; (run / "score.json").write_bytes(subject._canonical(score))
    class Runner:
        _json_bytes = staticmethod(subject._canonical)
        _provider_artifact = staticmethod(lambda root, path: {"path": path.relative_to(root).as_posix(), "bytes": len(path.read_bytes()), "sha256": _sha(path.read_bytes())})
        @staticmethod
        def _load_checkpoints(*args, **kwargs): return verdicts, loaded_batches, "head"
    class Core:
        @staticmethod
        def score_bundle(*args, **kwargs): return {"final_score": {"observed": 50.0}, "coverage": .9}
    class V3:
        _expected_codex_command = staticmethod(lambda executable, root: [executable, "exec", "--output-schema", "old", "--output-last-message", "old", "-"])
        _load_parse_codex_events = staticmethod(lambda: lambda raw: {"thread_id": json.loads(raw.splitlines()[0])["thread_id"], "usage": {}})
        @staticmethod
        def _strict_stderr_labels(raw):
            if b"different" in raw: raise ValueError("conflicting stderr label")
            return {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}
        @staticmethod
        def _codex_event_projection(raw, parser):
            events = [json.loads(line) for line in raw.splitlines() if line]
            messages = [event["item"]["text"] for event in events if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"]
            if len(messages) != 1: raise ValueError("exactly one agent message")
            return {**parser(raw), "completed_agent_message_text": messages[0]}
    runtime = SimpleNamespace(runner=Runner, core=Core, weights=SimpleNamespace(materialize_weight_profile=lambda *args: (None, None, weight)), modules=[], bundle={})
    monkeypatch.setattr(subject, "_source_bindings", lambda value: (runtime, V3, None))
    return SimpleNamespace(plan_root=plan_root, execution=execution, run=run, pass_id=pass_id, bindings=bindings, reviews=reviews)


def _admit(subject, fixture, **kwargs):
    return subject.admit_pass(fixture.run, fixture.plan_root, fixture.pass_id, expected_plan_sha256=subject.PLAN_SHA256, expected_source_bindings=fixture.bindings, expected_reviews=fixture.reviews, **kwargs)


def test_round_trip_accepts_absent_stderr_labels_and_replays_score(tmp_path, monkeypatch):
    subject = load(); fixture = _fixture(subject, tmp_path, monkeypatch)
    result = _admit(subject, fixture)
    assert len(result["verdicts"]) == len(result["local_thread_ids"]) * 8 - 6
    assert result["score"] == 50.0 and result["coverage"] == .9
    assert result["requested_identity"]["native_endpoint_contact_cardinality"] == "unproven"


def test_utc_parser_accepts_collector_offsets_and_rejects_other_offsets():
    subject = load()
    assert subject._time("2026-09-06T00:30:00+00:00", "fixture").utcoffset().total_seconds() == 0
    assert subject._time("2026-09-06T00:30:00Z", "fixture").utcoffset().total_seconds() == 0
    with pytest.raises(ValueError): subject._time("2026-09-06T00:30:00-07:00", "fixture")
    with pytest.raises(ValueError): subject._time("2026-09-06T00:30:00", "fixture")


@pytest.mark.parametrize("kind", ["prompt", "ids", "labels", "events", "review", "route"])
def test_rejects_drift_in_retained_or_governing_evidence(tmp_path, monkeypatch, kind):
    subject = load(); fixture = _fixture(subject, tmp_path, monkeypatch)
    checkpoint = fixture.run / "responses/batch-0001.json"
    if kind == "prompt": (fixture.plan_root / "prompts/request-0001.txt").write_bytes(b"drift")
    elif kind == "ids":
        value = json.loads(checkpoint.read_text()); value["question_ids"] = ["wrong"]; checkpoint.write_bytes(subject._canonical(value))
    elif kind == "labels":
        path = fixture.run / "responses/batch-0001.attempt-0001.stderr.bin"; path.write_bytes(b"model: different\n")
        value = json.loads(checkpoint.read_text()); value["provider"]["provider_artifacts"]["codex_stderr"] = {"path": path.relative_to(fixture.run).as_posix(), "bytes": len(path.read_bytes()), "sha256": _sha(path.read_bytes())}; checkpoint.write_bytes(subject._canonical(value))
    elif kind == "events":
        path = fixture.run / "responses/batch-0001.attempt-0001.events.jsonl"; path.write_bytes(path.read_bytes() + b'{"type":"item.completed","item":{"type":"agent_message","text":"other"}}\n')
        value = json.loads(checkpoint.read_text()); value["provider"]["provider_artifacts"]["codex_events"] = {"path": path.relative_to(fixture.run).as_posix(), "bytes": len(path.read_bytes()), "sha256": _sha(path.read_bytes())}; checkpoint.write_bytes(subject._canonical(value))
    elif kind == "review":
        review = next((fixture.execution / "cohorts/0001/reviews").glob("*.json")); value = json.loads(review.read_text()); value["route_sha256"] = "0" * 64; review.write_bytes(subject._canonical(value))
    else:
        value = json.loads(checkpoint.read_text()); value["provider"]["dryad_sol"]["route_snapshot"]["armed"] = False; value["provider"]["dryad_sol"]["route_sha256"] = _sha(subject._canonical(value["provider"]["dryad_sol"]["route_snapshot"])); checkpoint.write_bytes(subject._canonical(value))
    with pytest.raises(ValueError): _admit(subject, fixture)


def test_partial_prefix_reports_no_score(tmp_path, monkeypatch):
    subject = load(); fixture = _fixture(subject, tmp_path, monkeypatch, loaded_batches=2)
    result = _admit(subject, fixture, expected_batches=2)
    assert len(result["verdicts"]) == 16 and result["score"] is None and result["coverage"] is None


def test_rejects_unbound_route_command_and_caller_event_parser(tmp_path, monkeypatch):
    subject = load(); fixture = _fixture(subject, tmp_path, monkeypatch)
    with pytest.raises(TypeError): _admit(subject, fixture, parse_events=lambda _: {"thread_id": "forged", "usage": {}})
    checkpoint = fixture.run / "responses/batch-0001.json"; value = json.loads(checkpoint.read_text())
    route = value["provider"]["dryad_sol"]["route_snapshot"]; route.pop("codex_command_identity")
    value["provider"]["dryad_sol"]["route_sha256"] = _sha(subject._canonical(route)); checkpoint.write_bytes(subject._canonical(value))
    with pytest.raises(ValueError, match="command identity"): _admit(subject, fixture)


def test_rejects_configured_executable_not_in_reviewed_route(tmp_path, monkeypatch):
    subject = load(); fixture = _fixture(subject, tmp_path, monkeypatch)
    path = fixture.run / "run.json"; value = json.loads(path.read_text()); value["configuration"]["codex_bin"] = "unreviewed-codex"; path.write_bytes(subject._canonical(value))
    with pytest.raises(ValueError, match="native command"): _admit(subject, fixture)


def test_campaign_composes_frozen_order_and_rejects_duplicate_threads(tmp_path, monkeypatch):
    subject = load(); plan_root, execution = tmp_path / "plan", tmp_path / "execution"; plan_root.mkdir(); execution.mkdir()
    passes = [{"pass_id": f"pass-{number}", "run_path": f"runs/{number}", "logical_sample_id": f"sample-{number}", "opaque_story_id": f"story-{number}", "partition": "TRAIN" if number < 176 else "DEV"} for number in range(236)]
    raw = subject._canonical({"passes": passes, "requests": [{}] * 5428}); (plan_root / "plan.json").write_bytes(raw); monkeypatch.setattr(subject, "PLAN_SHA256", _sha(raw))
    def fake(run, root, pass_id, **kwargs):
        number = int(pass_id.removeprefix("pass-")); return {"local_thread_ids": [f"thread-{number}-{batch}" for batch in range(23)], "verdicts": [{}] * 178, "score": 50.0, "coverage": .9}
    monkeypatch.setattr(subject, "admit_pass", fake)
    result = subject.admit_campaign(plan_root, execution, expected_plan_sha256=subject.PLAN_SHA256, expected_source_bindings={}, expected_reviews=set())
    assert len(result["endpoint_sol_rows"]) == 236 and result["logical_requests"] == 5428
    def duplicate(*args, **kwargs): return {"local_thread_ids": ["same"] * 23, "verdicts": [{}] * 178, "score": 50.0, "coverage": .9}
    monkeypatch.setattr(subject, "admit_pass", duplicate)
    with pytest.raises(ValueError, match="duplicates"): subject.admit_campaign(plan_root, execution, expected_plan_sha256=subject.PLAN_SHA256, expected_source_bindings={}, expected_reviews=set())
