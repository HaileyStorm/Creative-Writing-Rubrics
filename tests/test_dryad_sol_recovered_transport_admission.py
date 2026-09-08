from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
from test_dryad_sol_pass_admission import _fixture, _sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_recovered_transport_admission.py"


def load():
    spec = importlib.util.spec_from_file_location("sol_recovered_admission_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def events(final='{"fixture":true}'):
    return [
        {"type": "thread.started", "thread_id": "synthetic-thread"},
        {"type": "turn.started"},
        {"type": "error", "message": "synthetic recovered transport"},
        {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0,
                                             "cache_write_input_tokens": 0, "output_tokens": 4,
                                             "reasoning_output_tokens": 0}},
    ]


def encode(value):
    return b"\n".join(json.dumps(item, separators=(",", ":")).encode() for item in value) + b"\n"


def pin_events(subject, monkeypatch, value):
    raw = encode(value)
    pins = dict(subject.ALLOWLIST)
    pins.update(events_bytes=len(raw), events_sha256=_sha(raw),
                error_message_bytes=len(value[2]["message"].encode()),
                error_message_sha256=_sha(value[2]["message"].encode()),
                final_message_sha256=_sha(value[3]["item"]["text"].encode()))
    monkeypatch.setattr(subject, "ALLOWLIST", pins)
    return raw


def repin_raw(subject, monkeypatch, raw):
    monkeypatch.setattr(subject, "ALLOWLIST", {**subject.ALLOWLIST, "events_bytes": len(raw), "events_sha256": _sha(raw)})


def test_exact_grammar_uses_unchanged_projection_and_strict_still_rejects(monkeypatch):
    subject = load()
    raw = pin_events(subject, monkeypatch, events())
    spec = importlib.util.spec_from_file_location("sol_projection_test", subject.ROOT / "sol_existing_runtime.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    v3 = adapter._base()
    assert v3._codex_event_projection(raw, subject._parse_exact_events) == {
        "schema_version": 1, "thread_id": "synthetic-thread", "usage": events()[-1]["usage"],
        "completed_agent_message_text": '{"fixture":true}',
    }
    with pytest.raises(ValueError, match="error"):
        v3._codex_event_projection(raw, v3._load_parse_codex_events())


@pytest.mark.parametrize("kind", ["raw_hash", "raw_length", "duplicate_key", "nested_duplicate", "keyset",
                                  "thread_type", "item_id", "item_type", "item_text", "usage_type", "usage_keys",
                                  "usage_bool", "usage_negative", "order", "extra_error", "unknown", "failed",
                                  "unfinished_item", "post_terminal", "blank_line", "non_object", "invalid_utf8",
                                  "error_message", "error_type", "missing_terminal", "extra_turn", "final_output"])
def test_rejects_event_drift_at_hash_and_grammar_boundaries(monkeypatch, kind):
    subject = load()
    value = events()
    raw = pin_events(subject, monkeypatch, value)
    if kind == "raw_hash": raw = raw.replace(b"synthetic-thread", b"synthetic-threaz")
    elif kind == "raw_length": raw += b"\n"
    elif kind == "duplicate_key": raw = raw.replace(b'"type":"error"', b'"type":"error","type":"error"')
    elif kind == "nested_duplicate": raw = raw.replace(b'"output_tokens":4', b'"output_tokens":4,"output_tokens":4')
    elif kind == "blank_line": raw += b"\n"
    elif kind == "invalid_utf8": raw = raw.replace(b"synthetic-thread", b"\xff")
    else:
        if kind == "keyset": value[2]["extra"] = 1
        elif kind == "thread_type": value[0]["thread_id"] = 7
        elif kind == "item_id": value[3]["item"]["id"] = ""
        elif kind == "item_type": value[3]["item"]["type"] = "reasoning"
        elif kind == "item_text": value[3]["item"]["text"] = 8
        elif kind == "usage_type": value[4]["usage"] = []
        elif kind == "usage_keys": value[4]["usage"]["extra"] = 0
        elif kind == "usage_bool": value[4]["usage"]["output_tokens"] = True
        elif kind == "usage_negative": value[4]["usage"]["output_tokens"] = -1
        elif kind == "order": value[1], value[2] = value[2], value[1]
        elif kind == "extra_error": value.insert(3, copy.deepcopy(value[2]))
        elif kind == "unknown": value[2]["type"] = "transport.recovered"
        elif kind == "failed": value[2]["type"] = "turn.failed"
        elif kind == "unfinished_item": value[3]["type"] = "item.started"
        elif kind == "post_terminal": value.append({"type": "turn.started"})
        elif kind == "non_object": value[2] = []
        elif kind == "error_message": value[2]["message"] += "!"
        elif kind == "error_type": value[2]["message"] = 39
        elif kind == "missing_terminal": value.pop()
        elif kind == "extra_turn": value[2] = {"type": "turn.started"}
        elif kind == "final_output": value[3]["item"]["text"] = "changed"
        raw = encode(value)
    # Grammar tests deliberately rebind only the outer fixture digest so they
    # exercise structural checks, while production pins remain immutable.
    if kind not in {"raw_hash", "raw_length"}: repin_raw(subject, monkeypatch, raw)
    with pytest.raises(ValueError): subject._parse_exact_events(raw)


def target_fixture(subject, tmp_path, monkeypatch):
    # Reuse the predecessor's synthetic runner/score boundary, retaining the real
    # route, review, prompt, schema, event grammar and new sidecar checks below.
    fixture = _fixture(subject, tmp_path, monkeypatch)
    runtime, v3, _ = subject._source_bindings(fixture.bindings)
    plan = json.loads((fixture.plan_root / "plan.json").read_bytes())
    plan["passes"][0], plan["passes"][9] = plan["passes"][9], plan["passes"][0]
    for request in plan["requests"][:23]: request["ordinal"] += 207
    for request in plan["requests"][207:230]: request["ordinal"] -= 207
    plan_raw = subject._canonical(plan)
    (fixture.plan_root / "plan.json").write_bytes(plan_raw)
    monkeypatch.setattr(subject, "PLAN_SHA256", _sha(plan_raw))
    monkeypatch.setattr(subject._base, "PLAN_SHA256", _sha(plan_raw))
    fixture.reviews.clear()
    for number in range(1, 24):
        path = fixture.run / f"responses/batch-{number:04d}.json"
        checkpoint = json.loads(path.read_bytes())
        metadata = checkpoint["provider"]["dryad_sol"]
        metadata["ordinal"] += 207
        metadata["plan_sha256"] = subject.PLAN_SHA256
        cohort = (metadata["ordinal"] - 1) // 10 + 1
        metadata["cohort_number"] = cohort
        review = {"schema_version": 1, "decision": "approved_sol_cohort", "plan_sha256": subject.PLAN_SHA256,
                  "cohort_number": cohort, "ordinals": list(range((cohort - 1) * 10 + 1, cohort * 10 + 1)),
                  "source_bindings": fixture.bindings, "route_sha256": metadata["route_sha256"],
                  "reviewed_at": "2026-09-06T00:00:00Z", "expires_at": "2026-09-06T02:00:00Z", "reviewer_task": "fixture"}
        review_raw = subject._canonical(review)
        sha = _sha(review_raw)
        review_path = fixture.execution / f"cohorts/{cohort:04d}/reviews/{sha}.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_bytes(review_raw)
        fixture.reviews.add(sha)
        metadata["review_sha256"] = sha
        final = (fixture.run / checkpoint["response_artifact"]["path"]).read_bytes()
        event_value = events(final.decode())
        event_value[0]["thread_id"] = f"synthetic-thread-{number}"
        if number == 14: event_raw = pin_events(subject, monkeypatch, event_value)
        else: event_raw = encode(event_value[:2] + event_value[3:])
        event_path = fixture.run / checkpoint["provider"]["provider_artifacts"]["codex_events"]["path"]
        event_path.write_bytes(event_raw)
        checkpoint["provider"]["provider_artifacts"]["codex_events"] = runtime.runner._provider_artifact(fixture.run, event_path)
        checkpoint["provider"]["reported"] = {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}
        path.write_bytes(subject._canonical(checkpoint))
    spec = importlib.util.spec_from_file_location("fixture_real_parser", subject.SHARED_PARSER_PATH)
    parser_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser_module)
    v3._load_parse_codex_events = staticmethod(lambda: parser_module._parse_events)
    checkpoint_path = fixture.run / "responses/batch-0014.json"
    pins = {**subject.ALLOWLIST, "checkpoint_sha256": _sha(checkpoint_path.read_bytes()),
            "stderr_bytes": 0, "stderr_sha256": _sha(b"")}
    monkeypatch.setattr(subject, "ALLOWLIST", pins)
    run_path = fixture.run / "run.json"
    manifest = json.loads(run_path.read_bytes())
    manifest["config_sha256"] = _sha(subject._canonical(manifest["configuration"]))
    run_path.write_bytes(subject._canonical(manifest))
    request = plan["requests"][13]
    start = {"format_version": 1, "policy": "terminal_sidecar_v1", "state": "started",
             "config_sha256": manifest["config_sha256"], "batch": 14, "attempt": 1,
             "base_prompt_sha256": request["prompt_sha256"], "effective_prompt_sha256": request["prompt_sha256"],
             "retry_policy": {"batch_attempts": 1}}
    lifecycle = fixture.run / "responses/attempt-lifecycle/batch-0014"
    lifecycle.mkdir(parents=True)
    start_raw = subject._canonical(start)
    (lifecycle / "attempt-0001.start.json").write_bytes(start_raw)
    settlement = {"format_version": 1, "policy": "terminal_sidecar_v1", "state": "settled", "start_sha256": _sha(start_raw),
                  "batch": 14, "attempt": 1, "outcome": "accepted",
                  "evidence": {"kind": "accepted_checkpoint", "path": "responses/batch-0014.json", "sha256": pins["checkpoint_sha256"]}}
    settled_raw = subject._canonical(settlement)
    (lifecycle / "attempt-0001.settled.json").write_bytes(settled_raw)
    monkeypatch.setattr(subject, "ALLOWLIST", {**subject.ALLOWLIST, "attempt_start_sha256": _sha(start_raw),
                                               "attempt_settled_sha256": _sha(settled_raw)})
    fixture.incident = tmp_path / "incident.json"
    fixture.incident.write_bytes(b'{"synthetic":true}')
    monkeypatch.setattr(subject, "INCIDENT_SHA256", _sha(fixture.incident.read_bytes()))
    fixture.proposal = tmp_path / "proposal.md"
    fixture.proposal.write_bytes(b"Synthetic proposal only.")
    monkeypatch.setattr(subject, "PROPOSAL_SHA256", _sha(fixture.proposal.read_bytes()))
    return fixture


def anchors(subject, fixture):
    return {"expected_plan_sha256": subject.PLAN_SHA256, "expected_source_bindings": fixture.bindings,
            "expected_reviews": fixture.reviews}


def candidate(subject, fixture):
    return subject.verify_candidate(fixture.run, fixture.plan_root, fixture.pass_id, **anchors(subject, fixture),
                                    incident_path=fixture.incident, proposal_path=fixture.proposal)


def adoption_record(subject, fixture, report):
    test_sha = _sha(Path(__file__).read_bytes())
    sources = subject._verify_sources()
    value = {"schema_version": 1, "decision": "adopt_" + subject.RECOVERY_CLASS,
             "owner_decision": {"explicit": True, "recorded_at": "2026-09-08T00:00:00Z", "reference": "synthetic owner"},
             "proposal_sha256": subject.PROPOSAL_SHA256, "incident_sha256": subject.INCIDENT_SHA256,
             **sources, "allowlist": dict(subject.ALLOWLIST), "candidate_verification_sha256": _sha(subject._canonical(report)),
             "independent_review": {"decision": "approved", "reference": "synthetic independent review",
                                    "interpreter_sha256": sources["interpreter_sha256"], "test_source_sha256": test_sha},
             "tests": {"test_source_sha256": test_sha, "result": "passed", "command": "synthetic pytest", "passed": 1}}
    fixture.adoption = fixture.incident.parent / "adoption.json"
    fixture.adoption.write_bytes(subject._canonical(value))
    return value


def adopted(subject, fixture):
    return subject.admit_pass(fixture.run, fixture.plan_root, fixture.pass_id, **anchors(subject, fixture),
                              adoption_path=fixture.adoption, expected_adoption_sha256=_sha(fixture.adoption.read_bytes()),
                              incident_path=fixture.incident)


@pytest.fixture(scope="module")
def _shared_target(tmp_path_factory):
    subject = load()
    patch = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("sol-recovered-synthetic")
    fixture = target_fixture(subject, root, patch)
    baseline = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    yield subject, fixture, root, baseline, set(fixture.reviews)
    patch.undo()


@pytest.fixture
def replay_case(_shared_target):
    subject, fixture, root, baseline, reviews = _shared_target
    yield subject, fixture
    # These are exclusively pytest-created synthetic files. Restore only deltas
    # so each rejection case starts from the same fully checked pass fixture.
    for path in root.rglob("*"):
        if path.is_file() and path not in baseline:
            path.resolve().relative_to(root.resolve())
            path.unlink()
    for path, raw in baseline.items():
        if not path.is_file() or path.read_bytes() != raw:
            path.write_bytes(raw)
    fixture.reviews.clear()
    fixture.reviews.update(reviews)


def test_candidate_is_deterministic_and_non_admitting_then_explicit_adoption_replays(replay_case):
    subject, fixture = replay_case
    report = candidate(subject, fixture)
    assert report == candidate(subject, fixture)
    assert report["study_admission"] is report["execution_authority"] is False
    assert report["provider_calls"] == 0 and report["recovered_ordinals"] == [221]
    assert report["replayed_batches"] == 23 and report["parity"]["score"] is True
    assert "verdicts" not in report and "score" not in report and "local_thread_ids" not in report
    assert report["observed_external_launch_count"] is report["observed_process_exit_code"] is None
    adoption_record(subject, fixture, report)
    result = adopted(subject, fixture)
    assert len(result["verdicts"]) == 178 and result["score"] == 50.0
    assert result["transport_recovery"]["candidate_verification_sha256"] == _sha(subject._canonical(report))
    assert result["transport_recovery"]["allowlist"]["ordinal"] == 221


@pytest.mark.parametrize("kind", ["ordinal", "batch", "second_attempt", "second_launch", "settlement_exit",
                                  "checkpoint", "stderr", "reported_identity", "final", "usage", "thread",
                                  "other_error", "prompt", "schema", "expired_route", "expired_review", "score"])
def test_replay_rejects_record_and_original_authority_drift(replay_case, kind):
    subject, fixture = replay_case
    checkpoint_path = fixture.run / "responses/batch-0014.json"
    checkpoint = json.loads(checkpoint_path.read_bytes())
    lifecycle = fixture.run / "responses/attempt-lifecycle/batch-0014"
    if kind in {"ordinal", "batch"}:
        request = {"ordinal": 222 if kind == "ordinal" else 221, "batch_number": 15 if kind == "batch" else 14}
        with pytest.raises(ValueError, match="ordinal or batch"):
            subject._target_evidence(fixture.run, request, checkpoint, {}, b"", b"", None)
        return
    if kind == "second_attempt":
        checkpoint["accepted_attempt"] = 2
        checkpoint_path.write_bytes(subject._canonical(checkpoint))
    elif kind == "second_launch":
        (lifecycle / "attempt-0002.start.json").write_bytes((lifecycle / "attempt-0001.start.json").read_bytes())
    elif kind == "settlement_exit":
        path = lifecycle / "attempt-0001.settled.json"
        value = json.loads(path.read_bytes()); value["exit_code"] = 1
        path.write_bytes(subject._canonical(value))
    elif kind == "checkpoint": checkpoint_path.write_bytes(checkpoint_path.read_bytes() + b" ")
    elif kind == "stderr": (fixture.run / checkpoint["provider"]["provider_artifacts"]["codex_stderr"]["path"]).write_bytes(b"drift")
    elif kind == "reported_identity":
        checkpoint["provider"]["reported"]["model"] = "other"
        checkpoint_path.write_bytes(subject._canonical(checkpoint))
    elif kind == "final": (fixture.run / checkpoint["response_artifact"]["path"]).write_bytes(b"changed")
    elif kind in {"usage", "thread", "other_error"}:
        number = 1 if kind == "other_error" else 14
        path = fixture.run / f"responses/batch-{number:04d}.attempt-0001.events.jsonl"
        value = [json.loads(line) for line in path.read_bytes().splitlines()]
        if kind == "usage": value[-1]["usage"]["output_tokens"] += 1
        elif kind == "thread": value[0]["thread_id"] += "drift"
        else: value.insert(2, {"type": "error", "message": "unapproved transport error"})
        path.write_bytes(encode(value))
        cp = fixture.run / f"responses/batch-{number:04d}.json"
        value = json.loads(cp.read_bytes())
        value["provider"]["provider_artifacts"]["codex_events"] = {
            "path": path.relative_to(fixture.run).as_posix(), "bytes": len(path.read_bytes()), "sha256": _sha(path.read_bytes())}
        cp.write_bytes(subject._canonical(value))
    elif kind == "prompt": (fixture.plan_root / "prompts/request-0001.txt").write_bytes(b"drift")
    elif kind == "schema": (fixture.run / "responses/schemas/batch-0001.json").write_bytes(b"drift")
    elif kind in {"expired_route", "expired_review"}:
        path = fixture.run / "responses/batch-0001.json"
        value = json.loads(path.read_bytes())
        metadata = value["provider"]["dryad_sol"]
        if kind == "expired_route": metadata["authorized_at"] = "2026-09-06T01:30:00Z"
        else:
            review_path = fixture.execution / f"cohorts/{metadata['cohort_number']:04d}/reviews/{metadata['review_sha256']}.json"
            review = json.loads(review_path.read_bytes())
            review["expires_at"] = "2026-09-06T00:20:00Z"
            raw = subject._canonical(review); sha = _sha(raw)
            review_path.with_name(sha + ".json").write_bytes(raw)
            metadata["review_sha256"] = sha; fixture.reviews.add(sha)
        path.write_bytes(subject._canonical(value))
    elif kind == "score": (fixture.run / "score.json").write_bytes(b"{}")
    with pytest.raises(ValueError): candidate(subject, fixture)


@pytest.mark.parametrize("kind", ["hash", "owner", "proposal", "incident", "interpreter", "strict", "executor", "parser",
                                  "allowlist", "review", "tests", "candidate", "extra_key", "duplicate_key"])
def test_adoption_rejects_drift(replay_case, kind):
    subject, fixture = replay_case
    value = adoption_record(subject, fixture, candidate(subject, fixture))
    if kind == "hash":
        with pytest.raises(ValueError, match="adoption bytes"):
            subject.verify_adoption(fixture.adoption, expected_adoption_sha256="0" * 64, incident_path=fixture.incident)
        return
    if kind == "owner": value["owner_decision"]["explicit"] = False
    elif kind in {"proposal", "incident", "interpreter", "executor"}: value[kind + "_sha256"] = "0" * 64
    elif kind == "strict": value["strict_admission_sha256"] = "0" * 64
    elif kind == "parser": value["shared_parser_sha256"] = "0" * 64
    elif kind == "allowlist": value["allowlist"]["ordinal"] = 222
    elif kind == "review": value["independent_review"]["decision"] = "pending"
    elif kind == "tests": value["tests"]["test_source_sha256"] = "0" * 64
    elif kind == "candidate": value["candidate_verification_sha256"] = "0" * 64
    elif kind == "extra_key": value["execution_authority"] = True
    raw = subject._canonical(value)
    if kind == "duplicate_key": raw = raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1')
    fixture.adoption.write_bytes(raw)
    with pytest.raises(ValueError): adopted(subject, fixture)


def test_missing_adoption_fails_before_any_replay(tmp_path):
    subject = load()
    kwargs = {"expected_plan_sha256": subject.PLAN_SHA256, "expected_source_bindings": {}, "expected_reviews": set()}
    with pytest.raises(TypeError): subject.admit_pass(tmp_path, tmp_path, "missing", **kwargs)
    with pytest.raises(TypeError): subject.admit_campaign(tmp_path, tmp_path, **kwargs)
    with pytest.raises(TypeError): subject.verify_candidate(tmp_path, tmp_path, "missing", **kwargs, parse_events=lambda _: {})
    with pytest.raises(ValueError, match="adoption hash"):
        subject.admit_pass(tmp_path, tmp_path, "missing", **kwargs, adoption_path=tmp_path / "absent",
                           expected_adoption_sha256="bad", incident_path=tmp_path / "absent")


@pytest.mark.parametrize("attribute", ["STRICT_PATH", "EXECUTOR_PATH", "SHARED_PARSER_PATH"])
def test_installed_or_frozen_source_drift_is_rejected(tmp_path, monkeypatch, attribute):
    subject = load()
    path = tmp_path / "drift.py"; path.write_bytes(b"# source drift")
    monkeypatch.setattr(subject, attribute, path)
    with pytest.raises(ValueError, match="source binding"): subject._verify_sources()


def test_ordinary_pass_delegates_to_strict_with_identical_data(tmp_path, monkeypatch):
    subject = load()
    # Exercise the internal dispatch after the separately tested adoption gate.
    fixture = _fixture(subject._base, tmp_path, monkeypatch)
    monkeypatch.setattr(subject, "PLAN_SHA256", subject._base.PLAN_SHA256)
    strict = subject._base.admit_pass(fixture.run, fixture.plan_root, fixture.pass_id, **anchors(subject, fixture))
    result = subject._admit_with_adoption(fixture.run, fixture.plan_root, fixture.pass_id,
                                          **anchors(subject, fixture), adoption={})
    assert result == strict and "transport_recovery" not in result


def test_campaign_preserves_strict_rows_and_requires_one_separate_recovery(tmp_path, monkeypatch):
    subject = load()
    passes = [{"pass_id": f"pass-{number}", "run_path": f"runs/{number}", "logical_sample_id": f"sample-{number}",
               "opaque_story_id": f"story-{number}", "partition": "TRAIN" if number < 176 else "DEV"}
              for number in range(236)]
    raw = subject._canonical({"passes": passes, "requests": [{}] * 5428})
    (tmp_path / "plan.json").write_bytes(raw)
    monkeypatch.setattr(subject, "PLAN_SHA256", _sha(raw))
    monkeypatch.setattr(subject._base, "PLAN_SHA256", _sha(raw))
    envelope = {"allowlist": dict(subject.ALLOWLIST)}
    recover_at = {9}
    def strict_pass(run, plan, pass_id, **kwargs):
        return {"local_thread_ids": [f"{pass_id}-{batch}" for batch in range(23)],
                "verdicts": [{}] * 178, "score": 50.0, "coverage": .9}
    def descendant_pass(run, plan, pass_id, **kwargs):
        result = strict_pass(run, plan, pass_id)
        if int(pass_id.removeprefix("pass-")) in recover_at: result["transport_recovery"] = envelope
        return result
    monkeypatch.setattr(subject._base, "admit_pass", strict_pass)
    monkeypatch.setattr(subject, "_admit_with_adoption", descendant_pass)
    monkeypatch.setattr(subject, "verify_adoption", lambda *args, **kwargs: envelope)
    kwargs = {"expected_plan_sha256": subject.PLAN_SHA256, "expected_source_bindings": {}, "expected_reviews": set()}
    strict = subject._base.admit_campaign(tmp_path, tmp_path, **kwargs)
    extra = {"adoption_path": tmp_path, "expected_adoption_sha256": "0" * 64, "incident_path": tmp_path}
    assert subject.admit_campaign(tmp_path, tmp_path, **kwargs, **extra) == {**strict, "transport_recovery": envelope}
    for wrong in (set(), {9, 10}):
        recover_at.clear(); recover_at.update(wrong)
        with pytest.raises(ValueError, match="exactly one ordinal"):
            subject.admit_campaign(tmp_path, tmp_path, **kwargs, **extra)
