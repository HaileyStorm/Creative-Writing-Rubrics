"""Provider-free contracts for direct post-773 Sol continuation dispatch."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_continuation_execution_v1.py"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _module():
    spec = importlib.util.spec_from_file_location("sol_continuation_execution_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = _module()
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import hashlib, json\n"
        "def predecessor(plan, original, replacement):\n"
        " return {'plan_sha256':'a'*64,'through_ordinal':773,'verdict_count':5986,'thread_ids':['prefix-thread'],'commitments':{'prefix':'p'},'route_identity':{'name':'codex-chatgpt-gpt-5.6-sol','provider':'openai_codex','adapter':'codex_exec','destination':'openai_codex_chatgpt_subscription','account_class':'subscription','model':'gpt-5.6-sol','reasoning_effort':'high','timeout_seconds':900}}\n"
        "def request_payload(plan, ordinal):\n"
        " prompt=('prompt-%04d\\r\\n' % ordinal).encode(); schema=b'{\\\"type\\\":\\\"object\\\"}'\n"
        " return {'ordinal':ordinal,'batch_number':ordinal-759,'prompt_sha256':hashlib.sha256(prompt).hexdigest(),'prompt_bytes':len(prompt),'schema_sha256':hashlib.sha256(schema).hexdigest(),'schema_bytes':len(schema)},prompt,schema\n"
        "def adapter(): raise AssertionError('override required')\n"
        "def route_snapshot(queue, expected):\n"
        " return {**expected,'codex_command':['synthetic-codex'],'codex_command_identity':{'artifacts':[{'sha256':'a'*64}]}}\n"
        "def validate_native(output, request, route, response, record):\n"
        " return {'verdicts':[{'question_id':'q'}],'thread_id':'thread-%d' % request['ordinal'],'usage':{},'response_sha256':hashlib.sha256(response).hexdigest()}\n",
        encoding="utf-8")
    monkeypatch.setattr(subject, "HELPER_PATH", helper)
    sandbox_root = tmp_path / "cwr-dryad-sol-post773-continuation-20260909-r1"
    monkeypatch.setattr(subject, "EXPECTED_CAMPAIGN_ROOT", sandbox_root)
    monkeypatch.setattr(subject, "CAMPAIGN_ROOT", sandbox_root)
    plan, original, replacement, queue = (tmp_path / name for name in ("plan", "original", "replacement", "queue"))
    for path in (plan, original, replacement, queue): path.mkdir()
    calls = []
    class Adapter:
        def call_codex(self, **kwargs):
            kwargs["before_provider_attempt"]()
            calls.append(kwargs)
            return '{"verdicts":[]}', {"synthetic": True}
    return subject, plan, original, replacement, queue, Adapter(), calls


def test_dispatches_774_with_exact_payload_and_its_frozen_batch(case):
    subject, plan, original, replacement, queue, adapter, calls = case
    result = subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=adapter)
    assert result["state"] == "collected" and result["completed_ordinals"] == [774]
    assert len(calls) == 1 and calls[0]["batch_number"] == 15
    root = subject.CAMPAIGN_ROOT / "requests/0774"
    assert calls[0]["prompt"].encode() == (root / "payload/request-0774.txt").read_bytes()
    assert calls[0]["response_schema"].read_bytes() == (root / "payload/request-0774.json").read_bytes()
    authorization = json.loads((root / "authorization.json").read_bytes())
    assert authorization["route_sha256"] == _sha((root / "route.json").read_bytes())
    assert __import__("datetime").datetime.fromisoformat(authorization["authorized_at"]).tzinfo is not None


def test_never_dispatches_prefix_and_restart_does_not_resend(case):
    subject, plan, original, replacement, queue, adapter, calls = case
    subject.collect(plan, original, replacement, queue, through_ordinal=775, adapter_override=adapter)
    assert [call["batch_number"] for call in calls] == [15, 16]
    subject.collect(plan, original, replacement, queue, through_ordinal=775, adapter_override=adapter)
    assert len(calls) == 2


def test_failure_is_terminal_and_restart_refuses_ambiguous_slot(case):
    subject, plan, original, replacement, queue, _adapter, calls = case
    class Failing:
        def call_codex(self, **kwargs):
            kwargs["before_provider_attempt"](); calls.append(kwargs); raise RuntimeError("synthetic")
    result = subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=Failing())
    assert result["state"] == "stopped_no_retry" and len(calls) == 1
    with pytest.raises(ValueError, match="terminal"):
        subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=Failing())


def test_existing_campaign_lock_is_not_reclaimed(case):
    subject, plan, original, replacement, queue, adapter, calls = case
    subject.CAMPAIGN_ROOT.mkdir(); (subject.CAMPAIGN_ROOT / ".collect.lock").write_bytes(b"other")
    with pytest.raises(ValueError, match="lock"):
        subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=adapter)
    assert not calls


@pytest.mark.parametrize("artifact", ["start.json", "authorization.json"])
def test_restart_rejects_tampered_start_or_authorization(case, artifact):
    subject, plan, original, replacement, queue, adapter, _calls = case
    subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=adapter)
    path = subject.CAMPAIGN_ROOT / "requests/0774" / artifact
    path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=adapter)


def test_existing_later_slot_without_774_is_an_ordinal_gap(case):
    subject, plan, original, replacement, queue, adapter, calls = case
    (subject.CAMPAIGN_ROOT / "requests/0775").mkdir(parents=True)
    with pytest.raises(ValueError, match="ordinal gap"):
        subject.collect(plan, original, replacement, queue, through_ordinal=775, adapter_override=adapter)
    assert not calls


@pytest.mark.parametrize("kind", ["prefix", "route", "source", "ordinal_gap"])
def test_prefix_route_source_and_ordinal_drift_stop_before_adapter(case, monkeypatch, kind):
    subject, plan, original, replacement, queue, adapter, calls = case
    if kind == "prefix":
        raw = subject.HELPER_PATH.read_text(encoding="utf-8").replace("5986", "1")
        subject.HELPER_PATH.write_text(raw, encoding="utf-8")
    elif kind == "route":
        raw = subject.HELPER_PATH.read_text(encoding="utf-8").replace("return {**expected", "return {**expected, 'model':'other'")
        subject.HELPER_PATH.write_text(raw, encoding="utf-8")
    elif kind == "source":
        monkeypatch.setattr(subject, "HELPER_PATH", subject.HELPER_PATH.with_name("missing.py"))
    else:
        raw = subject.HELPER_PATH.read_text(encoding="utf-8").replace("'ordinal':ordinal", "'ordinal':ordinal+1")
        subject.HELPER_PATH.write_text(raw, encoding="utf-8")
    with pytest.raises((FileNotFoundError, ValueError)):
        subject.collect(plan, original, replacement, queue, through_ordinal=774, adapter_override=adapter)
    assert not calls
