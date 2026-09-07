from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_measurement_execution.py"


@pytest.fixture
def case(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sol_collector_test", SOURCE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    plan_root, execution, queue = (tmp_path / name for name in ("plan", "execution", "queue"))
    plan_root.mkdir()
    queue.mkdir()
    (plan_root / "story.txt").write_bytes(b"Public synthetic story.")
    passes, requests = [], []
    for index in range(236):
        passed = {"pass_id": f"p{index}", "logical_sample_id": f"s{index}", "input_path": "story.txt",
                  "source_sha256": m.digest(b"Public synthetic story."), "run_path": f"runs/p{index}"}
        passes.append(passed)
        for batch in range(1, 24):
            prompt, schema = f"prompt-{batch}.txt", f"schema-{batch}.json"
            if index == 0:
                (plan_root / prompt).write_bytes(f"Exact prompt {batch}\r\n".encode())
                (plan_root / schema).write_bytes(b'{"type":"object"}')
            requests.append({"ordinal": len(requests) + 1, "pass_id": passed["pass_id"], "batch_number": batch,
                             "question_ids": [f"q{batch}"], "prompt_path": prompt, "schema_path": schema,
                             "prompt_sha256": m.digest(f"Exact prompt {batch}\r\n".encode()),
                             "prompt_bytes": len(f"Exact prompt {batch}\r\n".encode()),
                             "schema_sha256": m.digest(b'{"type":"object"}'),
                             "schema_bytes": len(b'{"type":"object"}')})
    plan = {"passes": passes, "requests": requests}
    monkeypatch.setattr(m, "_study", lambda root: plan)
    now = datetime.now(timezone.utc)
    auth = {"schema_version": 1, "status_hash": "a" * 64, "audit": {},
            "account_class": "subscription", "provider": "openai_codex", "route": "codex-chatgpt-gpt-5.6-sol",
            "evidence_class": "chatgpt_subscription_auth_status_v1", "checked_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat()}
    cost = {**auth, "kind": "subscription_included", "allowance_state": "available", "model": "gpt-5.6-sol"}
    for key in ("status_hash", "evidence_class"):
        del cost[key]
    auth_path, cost_path = tmp_path / "auth.json", tmp_path / "cost.json"
    auth_path.write_bytes(m.canonical(auth))
    cost_path.write_bytes(m.canonical(cost))
    exe = tmp_path / "synthetic.exe"
    exe.write_bytes(b"Not an executable; synthetic test only")
    route = {"name": auth["route"], "armed": True, "zero_charge": True, "health": "healthy",
             "account_class": "subscription", "model": "gpt-5.6-sol", "reasoning_effort": "high", "timeout_seconds": 900,
             "provider": "openai_codex", "adapter": "codex_exec", "destination": "openai_codex_chatgpt_subscription",
             "auth_receipt_hash": m.digest(auth_path.read_bytes()), "cost_evidence": {**cost, "evidence_hash": m.digest(cost_path.read_bytes())},
             "codex_command": [str(exe)], "codex_command_identity": {"artifacts": [{"sha256": m.digest(exe.read_bytes())}]}}
    (queue / "routes.json").write_bytes(m.canonical({"routes": [route]}))
    review = {"schema_version": 1, "decision": "approved_sol_cohort", "plan_sha256": m.PLAN_SHA256,
              "cohort_number": 1, "ordinals": list(range(1, 11)), "source_bindings": m.source_bindings(),
              "route_sha256": m.digest(m.canonical(route)), "reviewer_task": "synthetic-reviewer",
              "reviewed_at": now.isoformat(), "expires_at": (now + timedelta(hours=2)).isoformat()}
    review_path = tmp_path / "review.json"
    review_path.write_bytes(m.canonical(review))
    calls = []
    class Pause(Exception):
        pass
    runner = SimpleNamespace(RetryDisclosurePause=Pause)
    def judge(**kwargs):
        output = kwargs["output_dir"]
        (output / "responses").mkdir(parents=True, exist_ok=True)
        for request in requests[:23]:
            path = output / "responses" / f"batch-{request['batch_number']:04d}.json"
            if path.exists():
                continue
            context = {"output_dir": str(output), "batch": {"number": request["batch_number"]},
                       "prompt": {"text": (plan_root / request["prompt_path"]).read_bytes().decode()},
                       "response_schema": {"text": (plan_root / request["schema_path"]).read_bytes().decode()}}
            try:
                kwargs["before_provider_attempt"](context)
                content, record = runner._call_codex(prompt=context["prompt"]["text"], output_dir=output,
                    response_schema=plan_root / request["schema_path"], batch_number=request["batch_number"])
            except Pause:
                return {"status": "PAUSED"}
            path.write_bytes(m.canonical({"provider": record, "content": content}))
        return {"status": "COMPLETE"}
    runner.run_judge = judge
    def native(**kwargs):
        kwargs["before_provider_attempt"]()
        calls.append(kwargs)
        return "{}", {"reported": {"model": None}}
    real_runner = m._private_runner
    monkeypatch.setattr(m, "_private_runner", lambda: runner)
    monkeypatch.setattr(m, "_adapter", lambda: SimpleNamespace(call_codex=native))
    def run():
        return m.collect_cohort(plan_root, execution, review_path, expected_review_sha256=m.digest(review_path.read_bytes()),
            queue_root=queue, auth_receipt_path=auth_path, cost_receipt_path=cost_path)
    return SimpleNamespace(m=m, run=run, calls=calls, plan=plan_root, execution=execution, review=review,
                           review_path=review_path, queue=queue, route=route, data=plan, real_runner=real_runner,
                           auth_path=auth_path, cost_path=cost_path)


def test_collects_only_reviewed_ten_and_resume_does_not_resend(case):
    result = case.run()
    assert result["completed_ordinals"] == list(range(1, 11)) and result["status"] == "cohort_collected"
    assert len(case.calls) == 10 and result["full_study_admitted"] is False
    record = json.loads((case.execution / "runs/p0/responses/batch-0001.json").read_bytes())["provider"]["dryad_sol"]
    assert record["ordinal"] == 1 and record["auth_receipt"]["account_class"] == "subscription"
    assert case.run()["completed_ordinals"] == list(range(1, 11)) and len(case.calls) == 10
    assert not (case.execution / ".collect.lock").exists()


@pytest.mark.parametrize("change", ["payload", "route", "source"])
def test_drift_stops_before_native_call(case, change):
    if change == "payload":
        (case.plan / "prompt-1.txt").write_bytes(b"changed")
    elif change == "route":
        case.route["zero_charge"] = False
        (case.queue / "routes.json").write_bytes(case.m.canonical({"routes": [case.route]}))
    else:
        case.review["source_bindings"]["driver"] = "0" * 64
        case.review_path.write_bytes(case.m.canonical(case.review))
    with pytest.raises(ValueError):
        case.run()
    assert not case.calls


@pytest.mark.parametrize("change", ["missing_audit", "noncanonical", "offset_time", "cost_projection"])
def test_inadmissible_receipt_stops_before_contact(case, change):
    auth = json.loads(case.auth_path.read_bytes())
    if change == "missing_audit":
        del auth["audit"]
    elif change == "offset_time":
        auth["checked_at"] = datetime.now(timezone(timedelta(hours=1))).isoformat()
    elif change == "cost_projection":
        case.route["cost_evidence"]["kind"] = "different"
    raw = json.dumps(auth, indent=2).encode() if change == "noncanonical" else case.m.canonical(auth)
    case.auth_path.write_bytes(raw)
    case.route["auth_receipt_hash"] = case.m.digest(raw)
    (case.queue / "routes.json").write_bytes(case.m.canonical({"routes": [case.route]}))
    case.review["route_sha256"] = case.m.digest(case.m.canonical(case.route))
    case.review_path.write_bytes(case.m.canonical(case.review))
    with pytest.raises(ValueError, match="receipt"):
        case.run()
    assert not case.calls


def test_expired_window_pauses_without_contact(case):
    case.review["reviewed_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    case.review["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    case.review_path.write_bytes(case.m.canonical(case.review))
    assert case.run()["status"] == "paused" and not case.calls


def test_real_runner_checkpoint_flow_preserves_unattested_native_metadata(case, monkeypatch, tmp_path):
    runner = case.real_runner()
    root = case.m.REPOSITORY
    modules = runner.load_modules(root / "registry/all_modules.json")
    bundle = runner.resolve_bundle(runner.load_bundles(root / "bundles/all_bundles.json"), "prose.short_story")
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(runner.compiled_questions(runner.compile_bundle(modules, bundle)), key=lambda item: order[item["role"]])
    ids = [item["question"]["id"] for item in questions]
    probe = tmp_path / "schema-probe"
    with contextlib.redirect_stderr(io.StringIO()):
        runner.run_judge(artifact_path=case.plan / "story.txt", bundle_id="prose.short_story", provider="codex",
            model="gpt-5.6-sol", reasoning="high", output_dir=probe, registry=root / "registry/all_modules.json",
            bundles=root / "bundles/all_bundles.json", artifact_id="s0", judge_id="codex:gpt-5.6-sol",
            question_ids=ids, batch_size=8, batch_attempts=1, allow_remote=True, dry_run=True,
            attempt_lifecycle_policy="terminal_sidecar_v1", response_schema_mode="batch_question_ids_v1")
    binary = runner._read_text_record(root / "prompts/judge/BINARY_EVALUATION_PROMPT.md")["text"].strip()
    artifact = runner._read_text_record(case.plan / "story.txt")
    for index, request in enumerate(case.data["requests"][:23]):
        selected = questions[index * 8:(index + 1) * 8]
        request["question_ids"] = [item["question"]["id"] for item in selected]
        prompt = runner._render_prompt(binary_prompt=binary, artifact=artifact, contexts=[], bundle_id="prose.short_story",
            artifact_id="s0", questions=selected, provider="codex", model="gpt-5.6-sol").encode()
        schema = (probe / f"responses/schemas/batch-{index + 1:04d}.json").read_bytes()
        for field, raw in (("prompt", prompt), ("schema", schema)):
            (case.plan / request[f"{field}_path"]).write_bytes(raw)
            request[f"{field}_sha256"], request[f"{field}_bytes"] = case.m.digest(raw), len(raw)
    calls = []
    def native(**kwargs):
        kwargs["before_provider_attempt"]()
        schema = json.loads(kwargs["response_schema"].read_bytes())
        batch_ids = schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"]
        calls.append(batch_ids)
        content = json.dumps({"verdicts": [{"question_id": q, "verdict": "YES", "confidence": .8,
            "evidence": [{"kind": "exact_quote", "reference": "story", "exact_quote": "Public", "summary": None}],
            "note": "Synthetic integration fixture."} for q in batch_ids]})
        return content, {"reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}}
    monkeypatch.setattr(case.m, "_private_runner", lambda: runner)
    monkeypatch.setattr(case.m, "_adapter", lambda: SimpleNamespace(call_codex=native))
    result = case.run()
    assert result["completed_ordinals"] == list(range(1, 11)) and len(calls) == 10
    checkpoint = json.loads((case.execution / "runs/p0/responses/batch-0001.json").read_bytes())
    assert checkpoint["provider"]["reported"]["model"] is None
    assert checkpoint["provider"]["dryad_sol"]["ordinal"] == 1
    case.run()
    assert len(calls) == 10
