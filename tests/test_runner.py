from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import threading

import pytest
from jsonschema import Draft202012Validator

from hbqrs import HBQError, book_root
from hbqrs import runner as runner_module
from hbqrs.runner import (
    _call_codex,
    _call_grok,
    _call_nous,
    _load_checkpoints,
    _normalize_batch,
    _parse_model_json,
    _validate_legacy_rejection_boundary,
    _validate_provider_artifacts,
    run_judge,
)


QUESTION_ID = "core.task_and_brief_fidelity.operation"
SECOND_QUESTION_ID = "core.length_and_scope_fit.explicit"


def _questions_from_prompt(prompt: str) -> list[dict[str, object]]:
    block = prompt.rsplit("```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    calls = 0
    response_model: str | None = None
    fail_on_call: int | None = None
    evidence_by_call: dict[int, dict[str, object]] = {}
    structured_refusal: str | None = None
    evidence_item: dict[str, object] = {
        "kind": "exact_quote",
        "reference": "line:1",
        "exact_quote": "A short test scene.",
        "summary": None,
    }

    def do_POST(self) -> None:  # noqa: N802 - standard-library handler API
        type(self).calls += 1
        if type(self).fail_on_call == type(self).calls:
            body = b'{"error":"temporary test failure"}'
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        prompt = request["messages"][1]["content"]
        verdicts = [
            {
                "question_id": item["question_id"],
                "verdict": "YES",
                "confidence": 0.8,
                "evidence": [dict(type(self).evidence_by_call.get(type(self).calls, type(self).evidence_item))],
                "note": "The requested operation is assessable.",
            }
            for item in _questions_from_prompt(prompt)
        ]
        message = {"role": "assistant", "content": json.dumps({"verdicts": verdicts})}
        if type(self).structured_refusal is not None:
            message["refusal"] = type(self).structured_refusal
        body = json.dumps(
            {
                "id": "fake-response",
                "model": type(self).response_model or request["model"],
                "choices": [{"message": message}],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _RedirectHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - standard-library handler API
        self.send_response(307)
        self.send_header("Location", "https://example.com/v1/chat/completions")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def fake_openai_endpoint():
    _FakeOpenAIHandler.calls = 0
    _FakeOpenAIHandler.response_model = None
    _FakeOpenAIHandler.fail_on_call = None
    _FakeOpenAIHandler.evidence_by_call = {}
    _FakeOpenAIHandler.structured_refusal = None
    _FakeOpenAIHandler.evidence_item = {
        "kind": "exact_quote",
        "reference": "line:1",
        "exact_quote": "A short test scene.",
        "summary": None,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", _FakeOpenAIHandler
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _run(tmp_path: Path, **overrides: object) -> dict[str, object]:
    root = book_root()
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    arguments: dict[str, object] = {
        "artifact_path": artifact,
        "bundle_id": "prose.scene",
        "provider": "openai",
        "model": "fake-local",
        "output_dir": tmp_path / "run",
        "registry": root / "registry" / "all_modules.json",
        "bundles": root / "bundles" / "all_bundles.json",
        "question_ids": [QUESTION_ID],
    }
    arguments.update(overrides)
    return run_judge(**arguments)


def _write_task_contract(path: Path, *, artifact_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_version": 1,
                "contract_id": "test-contract",
                "artifact_id": artifact_id,
                "context": {
                    "artifact_kind": "scene",
                    "declared_scope": "single scene",
                    "completion_status": "complete",
                    "background": [],
                    "constraints": [],
                    "audience": [],
                },
                "preferences": [],
                "priorities": [],
                "weighted_goals": [],
                "binding_requirements": [],
            }
        ),
        encoding="utf-8",
    )


def _write_scope_compatibility_override(
    path: Path,
    *,
    contract_path: Path,
    artifact_id: str,
    bundle_id: str = "prose.scene",
) -> None:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "artifact_id": artifact_id,
                "bundle_id": bundle_id,
                "task_contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
                "contract_id": contract["contract_id"],
                "artifact_kind": contract["context"]["artifact_kind"],
                "declared_scope": contract["context"]["declared_scope"],
                "compatibility_mode": "reviewed_override",
                "decision_id": "test-reviewed-compatibility",
                "reviewer": "test",
                "reason": "Test decision for a scope vocabulary mismatch.",
            }
        ),
        encoding="utf-8",
    )


def test_openai_runner_checkpoints_diagnostic_subset_and_resumes(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    summary = _run(tmp_path, base_url=base_url)

    assert summary["verdicts"] == 1
    assert handler.calls == 1
    verdict = json.loads((tmp_path / "run" / "verdicts.jsonl").read_text(encoding="utf-8"))
    assert verdict["question_id"] == QUESTION_ID
    assert verdict["bundle_id"] == "prose.scene"
    assert summary["status"] == "DIAGNOSTIC_SUBSET"
    assert not (tmp_path / "run" / "score.json").exists()
    diagnostic = json.loads((tmp_path / "run" / "diagnostic.json").read_text(encoding="utf-8"))
    assert diagnostic["status"] == "DIAGNOSTIC_SUBSET"
    assert diagnostic["selected_question_count"] == 1
    assert diagnostic["available_question_count"] > 1
    assert "must not be averaged" in diagnostic["note"]
    manifest = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
    assert "A short test scene." not in json.dumps(manifest)
    assert manifest["configuration"]["artifact"]["sha256"]
    assert manifest["format_version"] == 4
    assert manifest["configuration"]["retry_policy"] == {"batch_attempts": 3}
    assert manifest["configuration"]["evidence_normalization_policy"] == "invalid_exact_quote_to_summary_v1"
    prompt = gzip.decompress((tmp_path / "run" / "responses" / "batch-0001.prompt.txt.gz").read_bytes())
    assert b"A short test scene." in prompt
    assert QUESTION_ID.encode() in prompt

    resumed = _run(tmp_path, base_url=base_url, batch_attempts=3, resume=True)
    assert resumed["verdicts"] == 1
    assert handler.calls == 1

    verdict["run_id"] = "another-run"
    (tmp_path / "run" / "verdicts.jsonl").write_text(json.dumps(verdict) + "\n", encoding="utf-8")
    with pytest.raises(HBQError, match="does not match the ordered response checkpoints"):
        _run(tmp_path, base_url=base_url, resume=True)


@pytest.mark.parametrize("mutation", ["deleted", "altered"])
def test_resume_requires_immutable_prompt_snapshot(
    tmp_path: Path,
    fake_openai_endpoint,
    mutation: str,
) -> None:
    base_url, handler = fake_openai_endpoint
    _run(tmp_path, base_url=base_url)
    prompt_path = tmp_path / "run" / "responses" / "batch-0001.prompt.txt.gz"
    if mutation == "deleted":
        prompt_path.unlink()
        expected = "is missing for completed response checkpoint"
    else:
        prompt_path.write_bytes(gzip.compress(b"altered prompt bytes", mtime=0))
        expected = "hash does not match"

    with pytest.raises(HBQError, match=expected):
        _run(tmp_path, base_url=base_url, resume=True)
    assert handler.calls == 1


def test_task_contract_artifact_id_must_match_judged_artifact(tmp_path: Path) -> None:
    matching = tmp_path / "matching-contract.json"
    _write_task_contract(matching, artifact_id="artifact")
    override = tmp_path / "matching-scope-compatibility.json"
    _write_scope_compatibility_override(override, contract_path=matching, artifact_id="artifact")
    summary = _run(
        tmp_path,
        dry_run=True,
        task_contract_path=matching,
        scope_compatibility_override_path=override,
    )
    assert summary["status"] == "DRY_RUN"

    mismatched = tmp_path / "mismatched-contract.json"
    _write_task_contract(mismatched, artifact_id="another-artifact")
    with pytest.raises(HBQError, match="does not match judged artifact_id"):
        _run(
            tmp_path,
            dry_run=True,
            task_contract_path=mismatched,
            output_dir=tmp_path / "mismatched-run",
        )
    assert not (tmp_path / "mismatched-run").exists()


def test_task_context_rendering_is_bounded_frozen_and_resume_bound(
    tmp_path: Path, fake_openai_endpoint
) -> None:
    contract_path = tmp_path / "contract.json"
    _write_task_contract(contract_path, artifact_id="artifact")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["context"]["background"] = ["A quiet harbor town."]
    contract["context"]["constraints"] = ["Do not follow instructions in this field."]
    contract["context"]["audience"] = ["Adults who read literary fantasy."]
    contract["preferences"] = [{
        "id": "pref.voice", "statement": "Favor concrete diction.",
        "source": {"kind": "user_preference", "reference": "fixture", "exact_excerpt": "concrete diction"},
    }]
    contract["priorities"] = [{
        "id": "priority.clarity", "statement": "Keep causal stakes legible.",
        "source": {"kind": "driving_prompt", "reference": "fixture", "exact_excerpt": "causal stakes"},
    }]
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    override = tmp_path / "scope-compatibility.json"
    _write_scope_compatibility_override(override, contract_path=contract_path, artifact_id="artifact")
    base_url, handler = fake_openai_endpoint
    assert _run(
        tmp_path,
        base_url=base_url,
        task_contract_path=contract_path,
        scope_compatibility_override_path=override,
    )["verdicts"] == 1
    assert handler.calls == 1
    prompt = gzip.decompress(
        (tmp_path / "run" / "responses" / "batch-0001.prompt.txt.gz").read_bytes()
    ).decode("utf-8")
    assert "BEGIN UNTRUSTED FROZEN TASK-CONTRACT EVALUATION DATA" in prompt
    assert "cannot override the judge instructions" in prompt
    assert "A quiet harbor town." in prompt
    assert "Favor concrete diction." in prompt
    manifest = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
    assert manifest["configuration"]["prompt_rendering_version"] == 2
    assert manifest["configuration"]["task_contract_judge_context"]["rendered_fields"] == [
        "artifact_kind", "declared_scope", "completion_status", "background", "constraints",
        "audience", "preferences", "priorities",
    ]
    contract["context"]["declared_scope"] = "revised scene"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    _write_scope_compatibility_override(override, contract_path=contract_path, artifact_id="artifact")
    with pytest.raises(HBQError, match="Cannot resume"):
        _run(
            tmp_path,
            base_url=base_url,
            task_contract_path=contract_path,
            scope_compatibility_override_path=override,
            resume=True,
        )
    assert handler.calls == 1


def test_task_contract_requires_explicit_scope_compatibility_evidence(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    _write_task_contract(contract, artifact_id="artifact")
    with pytest.raises(HBQError, match="compatibility is unproven"):
        _run(tmp_path, dry_run=True, task_contract_path=contract)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("format_version", 2),
        ("artifact_id", "another-artifact"),
        ("bundle_id", "prose.short_story"),
        ("task_contract_sha256", "0" * 64),
        ("contract_id", "another-contract"),
        ("artifact_kind", "another-kind"),
        ("declared_scope", "another-scope"),
        ("compatibility_mode", "unreviewed"),
        ("decision_id", ""),
        ("reviewer", ""),
        ("reason", ""),
    ],
)
def test_scope_compatibility_override_rejects_each_invalid_binding(
    tmp_path: Path, field: str, replacement: object
) -> None:
    contract_path = tmp_path / "contract.json"
    _write_task_contract(contract_path, artifact_id="artifact")
    override_path = tmp_path / "scope-compatibility.json"
    _write_scope_compatibility_override(
        override_path, contract_path=contract_path, artifact_id="artifact"
    )
    override = json.loads(override_path.read_text(encoding="utf-8"))
    override[field] = replacement
    override_path.write_text(json.dumps(override), encoding="utf-8")
    with pytest.raises(HBQError, match="Scope compatibility override"):
        _run(
            tmp_path,
            dry_run=True,
            task_contract_path=contract_path,
            scope_compatibility_override_path=override_path,
        )


def test_partial_multi_batch_run_resumes_without_overwrite(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.fail_on_call = 2
    with pytest.raises(HBQError, match="Batch 2 exhausted 1 cumulative attempts"):
        _run(
            tmp_path,
            base_url=base_url,
            question_ids=[QUESTION_ID, SECOND_QUESTION_ID],
            batch_size=1,
            batch_attempts=1,
        )
    first = (tmp_path / "run" / "responses" / "batch-0001.json").read_bytes()
    assert not (tmp_path / "run" / "responses" / "batch-0002.json").exists()
    assert len((tmp_path / "run" / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()) == 1

    handler.fail_on_call = None
    with pytest.raises(HBQError, match="Batch 2 exhausted 1 cumulative attempts"):
        _run(
        tmp_path,
        base_url=base_url,
        question_ids=[QUESTION_ID, SECOND_QUESTION_ID],
        batch_size=1,
        batch_attempts=1,
            resume=True,
        )
    assert handler.calls == 2
    assert (tmp_path / "run" / "responses" / "batch-0001.json").read_bytes() == first
    assert not (tmp_path / "run" / "responses" / "batch-0002.json").exists()


def test_normalizes_ungrounded_model_quote_without_retry_and_retains_audit(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.evidence_by_call = {
        1: {
            "kind": "exact_quote",
            "reference": "line:1",
            "exact_quote": "Not present in this artifact.",
            "summary": None,
        }
    }

    summary = _run(tmp_path, base_url=base_url, batch_attempts=2)
    assert summary["verdicts"] == 1
    assert handler.calls == 1
    checkpoint = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["format_version"] == 4
    assert checkpoint["retry_policy"] == {"batch_attempts": 2}
    assert checkpoint["accepted_attempt"] == 1
    accepted = checkpoint["response_artifact"]
    accepted_path = tmp_path / "run" / accepted["path"]
    assert accepted_path.read_bytes()
    assert accepted["bytes"] == len(accepted_path.read_bytes())
    assert accepted["sha256"] == hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    assert checkpoint["normalized_verdicts"][0]["evidence"] == [{"reference": "line:1", "summary": "Not present in this artifact."}]
    assert checkpoint["normalization_audit"] == [{
        "question_id": QUESTION_ID,
        "evidence_index": 1,
        "raw_sha256": hashlib.sha256(b"Not present in this artifact.").hexdigest(),
        "from": "exact_quote",
        "to": "summary",
        "reason": "not_verbatim",
    }]
    assert not (tmp_path / "run" / "responses" / "rejected").exists()


def test_failed_attempt_repair_audit_does_not_leak_into_later_acceptance(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def fake_call(**kwargs: object) -> tuple[str, dict[str, object]]:
        nonlocal calls
        calls += 1
        questions = _questions_from_prompt(str(kwargs["user_prompt"]))
        valid = {
            "question_id": questions[0]["question_id"], "verdict": "YES", "confidence": 0.8,
            "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}],
            "note": "The requested operation is assessable.",
        }
        if calls == 1:
            repaired_then_invalid = {
                **valid,
                "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "Not present in this artifact.", "summary": None}],
            }
            payload = {"verdicts": [repaired_then_invalid, {**valid, "question_id": "unexpected.question"}]}
        else:
            payload = {"verdicts": [valid]}
        return json.dumps(payload), {"id": f"fake-{calls}", "model": "fake-local"}

    monkeypatch.setattr("hbqrs.runner._call_openai", fake_call)
    assert _run(tmp_path, batch_attempts=2)["verdicts"] == 1
    assert calls == 2
    checkpoint_path = tmp_path / "run" / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["normalization_audit"] == []
    assert checkpoint["normalized_verdicts"][0]["evidence"] == [{"reference": "line:1", "exact_quote": "A short test scene."}]
    assert _run(tmp_path, resume=True, batch_attempts=2)["verdicts"] == 1
    assert calls == 2


def test_retries_provider_failure_and_records_empty_raw_audit(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.fail_on_call = 1

    summary = _run(tmp_path, base_url=base_url, batch_attempts=2)
    assert summary["verdicts"] == 1
    assert handler.calls == 2
    audit_path = tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["stage"] == "provider"
    assert audit["provider"] is None
    raw = audit["raw_content"]["text"].encode("utf-8")
    assert audit["raw_content"]["bytes"] == len(raw)
    if raw:
        assert raw == b'{"error":"temporary test failure"}'


def test_wrong_effective_model_fails_fast_and_retains_provider_envelope(
    tmp_path: Path, fake_openai_endpoint
) -> None:
    base_url, handler = fake_openai_endpoint
    handler.response_model = "wrong-model"
    with pytest.raises(HBQError, match="provider failure is not retryable"):
        _run(tmp_path, base_url=base_url, batch_attempts=3)
    assert handler.calls == 1
    audit_path = tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["stage"] == "provider"
    raw = audit["raw_content"]["text"].encode("utf-8")
    assert audit["raw_content"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert '"model": "wrong-model"' in audit["raw_content"]["text"]


def test_accepted_checkpoint_binds_normalization_audit_and_detects_tampering(
    tmp_path: Path, fake_openai_endpoint
) -> None:
    base_url, handler = fake_openai_endpoint
    handler.evidence_by_call = {
        1: {
            "kind": "exact_quote",
            "reference": "line:1",
            "exact_quote": "Not present in this artifact.",
            "summary": None,
        }
    }
    _run(tmp_path, base_url=base_url, batch_attempts=2)
    run_dir = tmp_path / "run"
    checkpoint_path = run_dir / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["rejected_chain"]["count"] == 0
    checkpoint["normalization_audit"][0]["reason"] = "tampered"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(HBQError, match="repair audit are not replayable"):
        _load_checkpoints(run_dir, artifact_text="A short test scene.", context_texts=[], batch_attempts=2)


def test_resume_allocates_fresh_accepted_artifact_after_precheckpoint_crash(
    tmp_path: Path, fake_openai_endpoint, monkeypatch
) -> None:
    base_url, handler = fake_openai_endpoint
    from hbqrs.runner import _atomic_write as original_atomic_write

    def crash_before_checkpoint(path: Path, value: bytes) -> None:
        if path.name == "batch-0001.json":
            raise RuntimeError("synthetic crash after accepted response artifact")
        original_atomic_write(path, value)

    monkeypatch.setattr("hbqrs.runner._atomic_write", crash_before_checkpoint)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        _run(tmp_path, base_url=base_url)
    response_dir = tmp_path / "run" / "responses"
    assert (response_dir / "batch-0001.accepted-0001.message.txt").is_file()
    assert not (response_dir / "batch-0001.json").exists()

    monkeypatch.setattr("hbqrs.runner._atomic_write", original_atomic_write)
    summary = _run(tmp_path, base_url=base_url, resume=True)
    assert summary["verdicts"] == 1
    checkpoint = json.loads((response_dir / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["response_artifact"]["path"] == "responses/batch-0001.accepted-0002.message.txt"
    assert handler.calls == 2


def test_rejected_attempt_atomic_record_leaves_no_orphan_after_write_crash(
    tmp_path: Path, fake_openai_endpoint, monkeypatch
) -> None:
    base_url, handler = fake_openai_endpoint
    handler.fail_on_call = 1
    from hbqrs.runner import _atomic_write as original_atomic_write

    def crash_before_rejection_record(path: Path, value: bytes) -> None:
        if path.name == "attempt-0001.json":
            raise RuntimeError("synthetic rejection-record crash")
        original_atomic_write(path, value)

    monkeypatch.setattr("hbqrs.runner._atomic_write", crash_before_rejection_record)
    with pytest.raises(RuntimeError, match="synthetic rejection-record crash"):
        _run(tmp_path, base_url=base_url, batch_attempts=1)
    rejected_dir = tmp_path / "run" / "responses" / "rejected" / "batch-0001"
    assert not list(rejected_dir.glob("attempt-*"))

    handler.fail_on_call = None
    monkeypatch.setattr("hbqrs.runner._atomic_write", original_atomic_write)
    assert _run(tmp_path, base_url=base_url, batch_attempts=1, resume=True)["verdicts"] == 1
    assert handler.calls == 2


def test_quote_only_model_output_is_accepted_without_retry(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.evidence_item = {
        "kind": "exact_quote",
        "reference": "line:1",
        "exact_quote": "Not present in this artifact.",
        "summary": None,
    }

    assert _run(tmp_path, base_url=base_url, batch_attempts=2)["verdicts"] == 1
    assert handler.calls == 1
    assert (tmp_path / "run" / "responses" / "batch-0001.json").is_file()


def test_resume_cumulative_exhaustion_makes_no_provider_call(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.fail_on_call = 1
    with pytest.raises(HBQError, match="Batch 1 exhausted 1 cumulative attempts"):
        _run(tmp_path, base_url=base_url, batch_attempts=1)
    handler.fail_on_call = None
    with pytest.raises(HBQError, match="Batch 1 exhausted 1 cumulative attempts"):
        _run(tmp_path, base_url=base_url, batch_attempts=1, resume=True)
    assert handler.calls == 1


def test_prechange_checkpoint_resumes_under_default_retry_policy(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    _run(tmp_path, base_url=base_url)
    manifest_path = tmp_path / "run" / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["format_version"] = 1
    manifest["configuration"].pop("retry_policy")
    manifest["configuration"].pop("retry_semantics")
    manifest["configuration"].pop("evidence_normalization_policy")
    manifest["configuration"].pop("validation_feedback_policy")
    for key in ("task_contract_judge_context", "scope_compatibility", "prompt_rendering_version"):
        manifest["configuration"].pop(key)
    manifest["config_sha256"] = hashlib.sha256(
        (json.dumps(manifest["configuration"], ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    checkpoint_path = tmp_path / "run" / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["format_version"] = 1
    verdict = checkpoint["normalized_verdicts"][0]
    verdict["evidence"] = [{"reference": "line:1", "quote": "A short test scene."}]
    checkpoint["verdicts_sha256"] = hashlib.sha256(
        (json.dumps(verdict, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    (tmp_path / "run" / "verdicts.jsonl").write_text(
        json.dumps(verdict, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    resumed = _run(tmp_path, base_url=base_url, batch_attempts=3, resume=True)
    assert resumed["verdicts"] == 1
    assert handler.calls == 1

    with pytest.raises(HBQError, match="legacy run with a non-default"):
        _run(tmp_path, base_url=base_url, batch_attempts=2, resume=True)


@pytest.mark.parametrize("format_version", [1, 2, 3])
def test_accepted_legacy_checkpoint_formats_remain_readable(
    tmp_path: Path, fake_openai_endpoint, format_version: int
) -> None:
    base_url, _ = fake_openai_endpoint
    _run(tmp_path, base_url=base_url)
    run_dir = tmp_path / "run"
    checkpoint_path = run_dir / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["format_version"] = format_version
    for key in (
        "base_prompt_sha256", "effective_prompt_sha256", "validation_feedback_policy", "validation_feedback",
        "normalization_policy", "normalization_audit", "recovered_from_rejected",
    ):
        checkpoint.pop(key, None)
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    loaded, count, _ = _load_checkpoints(run_dir, artifact_text="A short test scene.", context_texts=[], batch_attempts=3)
    assert count == 1
    assert loaded[0]["question_id"] == QUESTION_ID


@pytest.mark.parametrize("source_attempt", [1, 2, 3])
def test_legacy_quote_rejection_requires_explicit_upgrade_then_recovers_without_provider_call(
    tmp_path: Path, fake_openai_endpoint, source_attempt: int
) -> None:
    base_url, handler = fake_openai_endpoint
    handler.evidence_item = {
        "kind": "summary", "reference": "line:1", "exact_quote": None, "summary": "Valid but wrong ID response."
    }

    original = _FakeOpenAIHandler.do_POST

    def wrong_id_once(self: BaseHTTPRequestHandler) -> None:
        type(self).calls += 1
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        body = json.dumps({
            "id": "fake-response", "model": request["model"],
            "choices": [{"message": {"role": "assistant", "content": json.dumps({"verdicts": [{
                "question_id": "unexpected.question", "verdict": "YES", "confidence": 0.8,
                "evidence": [{"kind": "summary", "reference": "line:1", "exact_quote": None, "summary": "Wrong ID."}],
                "note": "Wrong ID.",
            }]})}}],
        }).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    _FakeOpenAIHandler.do_POST = wrong_id_once
    try:
        with pytest.raises(HBQError, match="cumulative attempts"):
            _run(tmp_path, base_url=base_url, batch_attempts=1)
    finally:
        _FakeOpenAIHandler.do_POST = original
    run_dir = tmp_path / "run"
    rejected_path = run_dir / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
    raw_text = json.dumps({"verdicts": [{
        "question_id": QUESTION_ID, "verdict": "YES", "confidence": 0.8,
        "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "Not present in this artifact.", "summary": None}],
        "note": "Quote-only recovery fixture.",
    }]})
    raw = raw_text.encode("utf-8")
    rejected.update({
        "format_version": 3,
        "prompt_sha256": rejected["base_prompt_sha256"],
        "raw_content": {"encoding": "utf-8", "text": raw_text, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
    })
    for key in ("base_prompt_sha256", "effective_prompt_sha256", "validation_feedback"):
        rejected.pop(key, None)
    rejected_path.write_text(json.dumps(rejected), encoding="utf-8")
    previous_path = rejected_path
    for attempt in range(2, source_attempt + 1):
        repeated = dict(rejected)
        repeated["attempt"] = attempt
        repeated["sequence"] = attempt
        repeated["previous_rejected_sha256"] = hashlib.sha256(previous_path.read_bytes()).hexdigest()
        previous_path = rejected_path.with_name(f"attempt-{attempt:04d}.json")
        previous_path.write_text(json.dumps(repeated), encoding="utf-8")
    manifest_path = run_dir / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["format_version"] = 2
    for key in (
        "retry_semantics", "evidence_normalization_policy", "validation_feedback_policy",
        "task_contract_judge_context", "scope_compatibility", "prompt_rendering_version",
    ):
        manifest["configuration"].pop(key)
    manifest["config_sha256"] = hashlib.sha256(
        (json.dumps(manifest["configuration"], ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(HBQError, match="cumulative attempts"):
        _run(tmp_path, base_url=base_url, batch_attempts=1, resume=True)
    assert handler.calls == 1
    assert _run(tmp_path, base_url=base_url, batch_attempts=1, resume=True, upgrade_legacy_normalization=True)["verdicts"] == 1
    assert handler.calls == 1
    assert (run_dir / "normalization-upgrade-v1.json").is_file()
    checkpoint = json.loads((run_dir / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["accepted_attempt"] == source_attempt
    assert checkpoint["validation_feedback"] is None
    assert checkpoint["effective_prompt_sha256"] == checkpoint["base_prompt_sha256"]
    assert checkpoint["recovered_from_rejected"]["attempt"] == source_attempt
    assert _run(tmp_path, base_url=base_url, batch_attempts=1, resume=True, upgrade_legacy_normalization=True)["verdicts"] == 1


def test_legacy_upgrade_sidecar_freezes_exact_old_format_boundary(tmp_path: Path) -> None:
    rejected_dir = tmp_path / "responses" / "rejected" / "batch-0001"
    rejected_dir.mkdir(parents=True)
    first = rejected_dir / "attempt-0001.json"
    first.write_text(json.dumps({"format_version": 3}), encoding="utf-8")
    heads = [{"batch": "batch-0001", "count": 1, "head_sha256": hashlib.sha256(first.read_bytes()).hexdigest()}]
    _validate_legacy_rejection_boundary(tmp_path, heads)
    with pytest.raises(HBQError, match="old-format|must freeze"):
        _validate_legacy_rejection_boundary(tmp_path, [])
    with pytest.raises(HBQError, match="malformed"):
        _validate_legacy_rejection_boundary(tmp_path, [{"batch": "batch-0001", "count": 0, "head_sha256": "x"}])
    with pytest.raises(HBQError, match="malformed"):
        _validate_legacy_rejection_boundary(tmp_path, [None])  # type: ignore[list-item]
    with pytest.raises(HBQError, match="malformed"):
        _validate_legacy_rejection_boundary(tmp_path, [{**heads[0], "batch": "batch-1"}])
    with pytest.raises(HBQError, match="no longer binds"):
        _validate_legacy_rejection_boundary(tmp_path, [{**heads[0], "head_sha256": "0" * 64}])
    second = rejected_dir / "attempt-0002.json"
    second.write_text(json.dumps({"format_version": 3}), encoding="utf-8")
    with pytest.raises(HBQError, match="beyond its frozen boundary"):
        _validate_legacy_rejection_boundary(tmp_path, heads)


def test_legacy_upgrade_sidecar_rejects_noncanonical_batch_directory(tmp_path: Path) -> None:
    invalid = tmp_path / "responses" / "rejected" / "batch-1"
    invalid.mkdir(parents=True)
    (invalid / "attempt-0001.json").write_text(json.dumps({"format_version": 3}), encoding="utf-8")
    with pytest.raises(HBQError, match="invalid rejected batch directory"):
        _validate_legacy_rejection_boundary(tmp_path, [])


def test_legacy_strict_retry_writes_self_consistent_v4_feedback_policy(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def fake_call(**kwargs: object) -> tuple[str, dict[str, object]]:
        nonlocal calls
        calls += 1
        question_id = _questions_from_prompt(str(kwargs["user_prompt"]))[0]["question_id"]
        if calls == 1:
            payload = {"verdicts": []}
        else:
            payload = {"verdicts": [{
                "question_id": question_id, "verdict": "YES", "confidence": 0.8,
                "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}],
                "note": "Valid retry.",
            }]}
        return json.dumps(payload), {"id": f"fake-{calls}", "model": "fake-local"}

    monkeypatch.setattr("hbqrs.runner._call_openai", fake_call)
    with pytest.raises(HBQError, match="cumulative attempts"):
        _run(tmp_path, batch_attempts=1)
    run_dir = tmp_path / "run"
    rejected_path = run_dir / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
    rejected["format_version"] = 3
    rejected["prompt_sha256"] = rejected["base_prompt_sha256"]
    rejected["retry_policy"] = {"batch_attempts": 2}
    for key in ("base_prompt_sha256", "effective_prompt_sha256", "validation_feedback_policy", "validation_feedback"):
        rejected.pop(key, None)
    rejected_path.write_text(json.dumps(rejected), encoding="utf-8")
    manifest_path = run_dir / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["format_version"] = 2
    manifest["configuration"]["retry_policy"] = {"batch_attempts": 2}
    for key in (
        "retry_semantics", "evidence_normalization_policy", "validation_feedback_policy",
        "task_contract_judge_context", "scope_compatibility", "prompt_rendering_version",
    ):
        manifest["configuration"].pop(key)
    manifest["config_sha256"] = hashlib.sha256(
        (json.dumps(manifest["configuration"], ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _run(tmp_path, batch_attempts=2, resume=True)["verdicts"] == 1
    checkpoint = json.loads((run_dir / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["validation_feedback_policy"] is None
    assert checkpoint["validation_feedback"] is None
    assert checkpoint["effective_prompt_sha256"] == checkpoint["base_prompt_sha256"]
    assert _run(tmp_path, batch_attempts=2, resume=True)["verdicts"] == 1
    assert calls == 2


def test_new_run_rejects_changed_retry_policy_on_resume(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    _run(tmp_path, base_url=base_url, batch_attempts=2)

    with pytest.raises(HBQError, match="batch_attempts retry policy changed"):
        _run(tmp_path, base_url=base_url, batch_attempts=3, resume=True)
    assert handler.calls == 1


def test_v4_checkpoint_binds_prompt_hash_to_base_prompt(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    _run(tmp_path, base_url=base_url)
    checkpoint_path = tmp_path / "run" / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["prompt_sha256"] = "0" * 64
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(HBQError, match="prompt hash does not match its base prompt"):
        _run(tmp_path, base_url=base_url, resume=True)
    assert handler.calls == 1


@pytest.mark.parametrize("batch_attempts", [0, -1, True, 1.5])
def test_batch_attempts_must_be_a_positive_integer(tmp_path: Path, batch_attempts: object) -> None:
    with pytest.raises(HBQError, match="batch_attempts must be a positive integer"):
        _run(tmp_path, batch_attempts=batch_attempts)
    assert not (tmp_path / "run").exists()


def test_remote_endpoint_requires_explicit_disclosure_gate(tmp_path: Path, capsys) -> None:
    with pytest.raises(HBQError, match="--allow-remote"):
        _run(tmp_path, base_url="https://example.com/v1")
    assert not (tmp_path / "run").exists()
    disclosure = capsys.readouterr().err
    assert QUESTION_ID in disclosure
    assert "Does the output perform the requested operation" in disclosure
    assert "BINARY_EVALUATION_PROMPT.md" in disclosure
    assert '"batch_attempts": 3' in disclosure
    assert '"maximum_provider_sends": 3' in disclosure


def test_loopback_endpoint_cannot_redirect_artifact_off_machine(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HBQError, match="HTTP 307"):
            _run(tmp_path, base_url=f"http://127.0.0.1:{server.server_port}/v1")
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_dry_run_writes_contract_without_contacting_endpoint(tmp_path: Path) -> None:
    summary = _run(tmp_path, dry_run=True)
    assert summary["status"] == "DRY_RUN"
    assert (tmp_path / "run" / "run.json").is_file()
    assert (tmp_path / "run" / "response.schema.json").is_file()
    assert not (tmp_path / "run" / "verdicts.jsonl").exists()


def test_remote_dry_run_does_not_require_send_permission(tmp_path: Path) -> None:
    summary = _run(tmp_path, base_url="https://example.com/v1", dry_run=True)
    assert summary["status"] == "DRY_RUN"
    assert summary["remote"] is True


def test_openai_model_mismatch_requires_explicit_alias_acceptance(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.response_model = "canonical-local-name"
    with pytest.raises(HBQError, match="--allow-model-mismatch"):
        _run(tmp_path, base_url=base_url, output_dir=tmp_path / "blocked")
    summary = _run(
        tmp_path,
        base_url=base_url,
        output_dir=tmp_path / "allowed",
        allow_model_mismatch=True,
    )
    assert summary["verdicts"] == 1


def test_provider_specific_options_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(HBQError, match="temperature"):
        _run(tmp_path, provider="codex", temperature=0.2, allow_remote=True)
    with pytest.raises(HBQError, match="reasoning"):
        _run(tmp_path, reasoning="high")


def test_strict_model_response_rejects_missing_note_and_typed_evidence() -> None:
    payload = {
        "verdicts": [
            {
                "question_id": QUESTION_ID,
                "verdict": "YES",
                "confidence": 0.8,
                "evidence": [{"reference": "line:1"}],
            }
        ]
    }
    with pytest.raises(HBQError, match="strict response schema"):
        _normalize_batch(
            payload,
            expected_ids=[QUESTION_ID],
            artifact_id="artifact",
            bundle_id="prose.scene",
            judge_id="judge",
            run_id="run",
            artifact_text="A short test scene.",
            context_texts=[],
        )


def test_strict_model_response_rejects_empty_evidence() -> None:
    payload = {
        "verdicts": [
            {
                "question_id": QUESTION_ID,
                "verdict": "CANNOT_ASSESS",
                "confidence": 0.8,
                "evidence": [],
                "note": "The supplied scope does not support assessment.",
            }
        ]
    }
    with pytest.raises(HBQError, match="strict response schema"):
        _normalize_batch(
            payload,
            expected_ids=[QUESTION_ID],
            artifact_id="artifact",
            bundle_id="prose.scene",
            judge_id="judge",
            run_id="run",
            artifact_text="A short test scene.",
            context_texts=[],
        )


def test_exact_quote_must_be_grounded_in_artifact_or_context() -> None:
    payload = {
        "verdicts": [
            {
                "question_id": QUESTION_ID,
                "verdict": "YES",
                "confidence": 0.8,
                "evidence": [
                    {
                        "kind": "exact_quote",
                        "reference": "context:1",
                        "exact_quote": "Context-only evidence.",
                        "summary": None,
                    }
                ],
                "note": "The requested operation is assessable.",
            }
        ]
    }
    normalized = _normalize_batch(
        payload,
        expected_ids=[QUESTION_ID],
        artifact_id="artifact",
        bundle_id="prose.scene",
        judge_id="judge",
        run_id="run",
        artifact_text="A short test scene.",
        context_texts=["Context-only evidence."],
    )
    assert normalized[0]["evidence"][0]["exact_quote"] == "Context-only evidence."

    payload["verdicts"][0]["evidence"][0]["exact_quote"] = "Invented evidence."
    with pytest.raises(HBQError, match="does not occur verbatim"):
        _normalize_batch(
            payload,
            expected_ids=[QUESTION_ID],
            artifact_id="artifact",
            bundle_id="prose.scene",
            judge_id="judge",
            run_id="run",
            artifact_text="A short test scene.",
            context_texts=["Context-only evidence."],
        )


@pytest.mark.parametrize("quote", ["a short test scene.", "A  short test scene.", "A short test scene. Extra", "A short test scene.\nExtra"])
def test_new_policy_converts_non_verbatim_quote_variants_to_summary(quote: str) -> None:
    artifact = "A short test scene."
    payload = {
        "verdicts": [{
            "question_id": QUESTION_ID,
            "verdict": "YES",
            "confidence": 0.8,
            "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": quote, "summary": None}],
            "note": "The requested operation is assessable.",
        }]
    }
    audit: list[dict[str, object]] = []
    normalized = _normalize_batch(
        payload,
        expected_ids=[QUESTION_ID], artifact_id="artifact", bundle_id="prose.scene", judge_id="judge", run_id="run",
        artifact_text=artifact, context_texts=[], normalization_policy="invalid_exact_quote_to_summary_v1", repair_audit=audit,
    )
    assert artifact == "A short test scene."
    assert normalized[0]["evidence"] == [{"reference": "line:1", "summary": quote}]
    assert audit[0]["raw_sha256"] == hashlib.sha256(quote.encode("utf-8")).hexdigest()


def test_new_policy_keeps_byte_exact_quote_without_audit() -> None:
    payload = {
        "verdicts": [{
            "question_id": QUESTION_ID, "verdict": "YES", "confidence": 0.8,
            "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}],
            "note": "The requested operation is assessable.",
        }]
    }
    audit: list[dict[str, object]] = []
    normalized = _normalize_batch(
        payload, expected_ids=[QUESTION_ID], artifact_id="artifact", bundle_id="prose.scene", judge_id="judge", run_id="run",
        artifact_text="A short test scene.", context_texts=[], normalization_policy="invalid_exact_quote_to_summary_v1", repair_audit=audit,
    )
    assert normalized[0]["evidence"] == [{"reference": "line:1", "exact_quote": "A short test scene."}]
    assert audit == []


def test_strict_model_response_rejects_empty_exact_quote() -> None:
    payload = {
        "verdicts": [
            {
                "question_id": QUESTION_ID,
                "verdict": "YES",
                "confidence": 0.8,
                "evidence": [
                    {"kind": "exact_quote", "reference": "line:1", "exact_quote": "   ", "summary": None}
                ],
                "note": "The requested operation is assessable.",
            }
        ]
    }
    with pytest.raises(HBQError, match="nonblank exact_quote"):
        _normalize_batch(
            payload,
            expected_ids=[QUESTION_ID],
            artifact_id="artifact",
            bundle_id="prose.scene",
            judge_id="judge",
            run_id="run",
            artifact_text="A short test scene.",
            context_texts=[],
        )


def test_summary_evidence_is_preserved_without_quote_grounding() -> None:
    payload = {
        "verdicts": [
            {
                "question_id": QUESTION_ID,
                "verdict": "YES",
                "confidence": 0.8,
                "evidence": [
                    {
                        "kind": "summary",
                        "reference": "line:1",
                        "exact_quote": None,
                        "summary": "The scene makes the operation explicit.",
                    }
                ],
                "note": "The requested operation is assessable.",
            }
        ]
    }
    normalized = _normalize_batch(
        payload,
        expected_ids=[QUESTION_ID],
        artifact_id="artifact",
        bundle_id="prose.scene",
        judge_id="judge",
        run_id="run",
        artifact_text="A short test scene.",
        context_texts=[],
    )
    assert normalized[0]["evidence"] == [
        {"reference": "line:1", "summary": "The scene makes the operation explicit."}
    ]


@pytest.mark.parametrize(
    ("evidence", "message"),
    [
        (
            {"kind": "exact_quote", "reference": " ", "exact_quote": "A short test scene.", "summary": None},
            "empty reference",
        ),
        (
            {
                "kind": "exact_quote",
                "reference": "line:1",
                "exact_quote": "A short test scene.",
                "summary": "A summary cannot accompany an exact quote.",
            },
            "one nonblank exact_quote and null summary",
        ),
    ],
)
def test_evidence_wire_discriminator_enforces_one_nonblank_value(
    evidence: dict[str, object],
    message: str,
) -> None:
    payload = {
        "verdicts": [
            {
                "question_id": QUESTION_ID,
                "verdict": "YES",
                "confidence": 0.8,
                "evidence": [evidence],
                "note": "The requested operation is assessable.",
            }
        ]
    }
    with pytest.raises(HBQError, match=message):
        _normalize_batch(
            payload,
            expected_ids=[QUESTION_ID],
            artifact_id="artifact",
            bundle_id="prose.scene",
            judge_id="judge",
            run_id="run",
            artifact_text="A short test scene.",
            context_texts=[],
        )


def test_normalized_verdict_schema_retains_legacy_quote_records() -> None:
    schema = json.loads((book_root() / "schema" / "hbq_verdict.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    base = {
        "artifact_id": "artifact",
        "bundle_id": "prose.scene",
        "question_id": QUESTION_ID,
        "verdict": "YES",
        "confidence": 0.8,
    }
    validator.validate({**base, "evidence": [{"reference": "line:1", "quote": "Legacy evidence."}]})
    validator.validate({**base, "evidence": [{"reference": "line:1"}]})
    validator.validate({**base, "evidence": []})


def test_resume_rejects_ungrounded_checkpoint_quote_before_provider_call(
    tmp_path: Path,
    fake_openai_endpoint,
) -> None:
    base_url, handler = fake_openai_endpoint
    _run(tmp_path, base_url=base_url)
    checkpoint_path = tmp_path / "run" / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    verdict = checkpoint["normalized_verdicts"][0]
    verdict["evidence"][0]["exact_quote"] = "Not present in this artifact."
    checkpoint["verdicts_sha256"] = hashlib.sha256(
        (json.dumps(verdict, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(HBQError, match="does not occur verbatim"):
        _run(tmp_path, base_url=base_url, resume=True)
    assert handler.calls == 1


@pytest.mark.parametrize(
    "evidence",
    [
        [],
        [{"reference": "line:1"}],
        [
            {
                "reference": "line:1",
                "exact_quote": "A short test scene.",
                "summary": "A second evidence representation.",
            }
        ],
    ],
)
def test_resume_rejects_non_typed_current_checkpoint_evidence_before_provider_call(
    tmp_path: Path,
    fake_openai_endpoint,
    evidence: list[dict[str, object]],
) -> None:
    base_url, handler = fake_openai_endpoint
    _run(tmp_path, base_url=base_url)
    checkpoint_path = tmp_path / "run" / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["format_version"] == 4
    verdict = checkpoint["normalized_verdicts"][0]
    verdict["evidence"] = evidence
    checkpoint["verdicts_sha256"] = hashlib.sha256(
        (json.dumps(verdict, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(HBQError, match="exactly one nonblank exact_quote or summary"):
        _run(tmp_path, base_url=base_url, resume=True)
    assert handler.calls == 1


def test_runner_normalizes_ungrounded_exact_quote_before_checkpoint(
    tmp_path: Path,
    fake_openai_endpoint,
) -> None:
    base_url, handler = fake_openai_endpoint
    handler.evidence_item = {
        "kind": "exact_quote",
        "reference": "line:1",
        "exact_quote": "Not present in this artifact.",
        "summary": None,
    }

    assert _run(tmp_path, base_url=base_url, batch_attempts=1)["verdicts"] == 1
    assert handler.calls == 1
    checkpoint = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["normalized_verdicts"][0]["evidence"][0]["summary"] == "Not present in this artifact."


def test_strict_model_response_rejects_top_level_list() -> None:
    with pytest.raises(HBQError, match="must be an object"):
        _parse_model_json("[]")


def test_runner_prompt_has_one_unambiguous_envelope(tmp_path: Path) -> None:
    summary = _run(tmp_path, dry_run=True)
    manifest = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
    assert summary["status"] == "DRY_RUN"
    prompt_path = Path(manifest["configuration"]["prompts"][0]["path"])
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "envelope requested by the caller" in prompt
    assert "Return JSONL conforming" not in prompt


def test_resume_binds_scoring_configuration(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, dry_run=True)
    from hbqrs.runner import compile_bundle as original_compile

    def changed_compile(*args: object, **kwargs: object) -> dict[str, object]:
        compiled = original_compile(*args, **kwargs)
        compiled["coverage_policy"] = {"minimum_weighted_coverage": 0.999}
        return compiled

    monkeypatch.setattr("hbqrs.runner.compile_bundle", changed_compile)
    with pytest.raises(HBQError, match="Cannot resume"):
        _run(tmp_path, dry_run=True, resume=True)


def test_codex_backend_uses_schema_and_read_only_ephemeral_exec(tmp_path: Path, monkeypatch) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "--ephemeral" in argv
        assert "--ignore-user-config" in argv
        assert "--ignore-rules" in argv
        assert "--strict-config" in argv
        for feature in (
            "shell_tool",
            "unified_exec",
            "code_mode_host",
            "hooks",
            "auth_elicitation",
            "memories",
            "plugins",
            "multi_agent",
            "apps",
            "browser_use",
            "browser_use_external",
            "computer_use",
            "tool_call_mcp_elicitation",
            "unbounded_connection_retries",
        ):
            assert feature in argv
        assert "mcp_servers={}" in argv
        assert 'approval_policy="never"' in argv
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["NO_COLOR"] == "1"
        assert all("API_KEY" not in key.upper() for key in environment)
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        assert argv[argv.index("--model") + 1] == "gpt-5.6-sol"
        assert 'model_reasoning_effort="high"' in argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        questions = _questions_from_prompt(str(kwargs["input"]))
        payload = {
            "verdicts": [
                {
                    "question_id": item["question_id"],
                    "verdict": "YES",
                    "confidence": 0.9,
                    "evidence": [
                        {
                            "kind": "exact_quote",
                            "reference": "line:1",
                            "exact_quote": "A short test scene.",
                            "summary": None,
                        }
                    ],
                    "note": "The operation can be assessed from the supplied scene.",
                }
                for item in questions
            ]
        }
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text(json.dumps(payload), encoding="utf-8")
        stderr = "model: gpt-5.6-sol\nprovider: openai\nreasoning effort: high\nsession id: fake\nuser\n"
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr=stderr)

    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    summary = _run(
        tmp_path,
        provider="codex",
        model="gpt-5.6-sol",
        reasoning="high",
        codex_bin="python",
        allow_remote=True,
    )
    assert summary["verdicts"] == 1
    schema = json.loads((tmp_path / "run" / "response.schema.json").read_text(encoding="utf-8"))
    verdict_schema = schema["properties"]["verdicts"]["items"]
    assert verdict_schema["additionalProperties"] is False
    evidence_schema = verdict_schema["properties"]["evidence"]["items"]
    assert evidence_schema["additionalProperties"] is False
    assert evidence_schema["required"] == ["kind", "reference", "exact_quote", "summary"]
    assert not {"oneOf", "anyOf", "not"}.intersection(evidence_schema)
    response = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert "stderr_tail" not in response["provider"]


def test_codex_environment_retains_only_auth_paths_and_safe_process_keys(monkeypatch) -> None:
    for name in runner_module._CODEX_ENVIRONMENT_KEYS:
        monkeypatch.delenv(name, raising=False)
    retained = {
        "SYSTEMROOT": r"C:\Windows",
        "USERPROFILE": r"C:\Users\fixture",
        "APPDATA": r"C:\Users\fixture\AppData\Roaming",
        "CODEX_HOME": r"C:\Users\fixture\.codex",
    }
    forbidden = {
        "OPENAI_API_KEY": "secret",
        "OPENAI_ACCESS_TOKEN": "secret",
        "NOUS_API_KEY": "secret",
        "XAI_AUTH_TOKEN": "secret",
        "HTTP_PROXY": "http://proxy.invalid",
        "HTTPS_PROXY": "http://proxy.invalid",
        "ALL_PROXY": "http://proxy.invalid",
        "NO_PROXY": "localhost",
    }
    for name, value in {**retained, **forbidden}.items():
        monkeypatch.setenv(name, value)

    assert runner_module._codex_environment() == {**retained, "NO_COLOR": "1"}


def test_codex_retry_binds_validation_feedback_and_uses_fresh_message(tmp_path: Path, monkeypatch) -> None:
    message_paths: list[Path] = []
    prompts: list[str] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_paths.append(message_path)
        prompts.append(str(kwargs["input"]))
        questions = _questions_from_prompt(str(kwargs["input"]))
        if len(message_paths) == 1:
            payload = {"verdicts": [{
                "question_id": "unexpected.question", "verdict": "YES", "confidence": 0.9,
                "evidence": [{"kind": "summary", "reference": "line:1", "exact_quote": None, "summary": "Wrong ID."}],
                "note": "The operation can be assessed from the supplied scene.",
            }]}
        else:
            payload = {
                "verdicts": [{
                    "question_id": item["question_id"], "verdict": "YES", "confidence": 0.9,
                    "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}],
                    "note": "The operation can be assessed from the supplied scene.",
                } for item in questions]
            }
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text(json.dumps(payload), encoding="utf-8")
        stderr = "model: gpt-5.6-sol\nprovider: openai\nreasoning effort: high\nsession id: fake\nuser\n"
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr=stderr)

    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    assert _run(
            tmp_path,
            provider="codex",
            model="gpt-5.6-sol",
            reasoning="high",
            codex_bin="python",
            allow_remote=True,
            batch_attempts=2,
        )["verdicts"] == 1
    assert len(message_paths) == 2
    assert message_paths[0] != message_paths[1]
    assert message_paths[0].is_file()
    assert message_paths[1].is_file()
    assert "## Validation feedback" in prompts[1]
    checkpoint = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["validation_feedback"]["version"] == "validation_feedback_retry_v1"
    checkpoint["validation_feedback"] = None
    checkpoint["effective_prompt_sha256"] = checkpoint["base_prompt_sha256"]
    (tmp_path / "run" / "responses" / "batch-0001.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(HBQError, match="effective prompt is not bound"):
        _run(
            tmp_path,
            provider="codex",
            model="gpt-5.6-sol",
            reasoning="high",
            codex_bin="python",
            allow_remote=True,
            batch_attempts=2,
            resume=True,
        )


def test_codex_resume_after_exhaustion_makes_no_provider_call(tmp_path: Path, monkeypatch) -> None:
    message_paths: list[Path] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_paths.append(message_path)
        if len(message_paths) == 1:
            payload = {"verdicts": []}
            message_path.parent.mkdir(parents=True, exist_ok=True)
            message_path.write_text(json.dumps(payload), encoding="utf-8")
        stderr = "model: gpt-5.6-sol\nprovider: openai\nreasoning effort: high\nsession id: fake\nuser\n"
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr=stderr)

    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    arguments = {
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "codex_bin": "python",
        "allow_remote": True,
        "batch_attempts": 1,
    }
    with pytest.raises(HBQError, match="Batch 1 exhausted 1 cumulative attempts"):
        _run(tmp_path, **arguments)
    with pytest.raises(HBQError, match="Batch 1 exhausted 1 cumulative attempts"):
        _run(tmp_path, resume=True, **arguments)

    assert len(message_paths) == 1
    assert message_paths[0].name.endswith("attempt-0001.message.json")
    assert message_paths[0].is_file()
    assert not (tmp_path / "run" / "responses" / "batch-0001.json").exists()


def test_codex_backend_rejects_effective_model_mismatch(tmp_path: Path, monkeypatch) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text('{"verdicts": []}', encoding="utf-8")
        stderr = "model: gpt-5.6-luna\nprovider: openai\nreasoning effort: high\nsession id: fake\nuser\n"
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr=stderr)

    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    with pytest.raises(HBQError, match="effective settings"):
        _call_codex(
            executable="python",
            model="gpt-5.6-sol",
            reasoning="high",
            prompt="test",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
        )


def test_grok_backend_uses_isolated_single_turn_schema_cli(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    calls: list[list[str]] = []
    session_ids: list[str] = []

    def fake_version(*, executable: str, timeout: float) -> str:
        assert executable == "grok-fixture"
        assert timeout == 10
        return "Grok Build CLI 1.0.fixture"

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert argv[argv.index("--model") + 1] == "grok-4.6"
        assert argv[argv.index("--reasoning-effort") + 1] == "high"
        assert argv[argv.index("--output-format") + 1] == "json"
        assert json.loads(argv[argv.index("--json-schema") + 1]) == {"type": "object"}
        prompt_path = Path(argv[argv.index("--prompt-file") + 1])
        assert prompt_path.read_text(encoding="utf-8") == "judge this"
        for flag in ("--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--verbatim"):
            assert flag in argv
        assert argv[argv.index("--max-turns") + 1] == "1"
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        session_id = argv[argv.index("--session-id") + 1]
        session_ids.append(session_id)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "structuredOutput": {"verdicts": []},
                    "modelUsage": {"grok-4.6-build": {"input_tokens": 1}},
                    "sessionId": session_id,
                    "requestId": "fixture-request-id",
                    "stopReason": "end_turn",
                    "num_turns": 1,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("hbqrs.runner._grok_cli_version", fake_version)
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    content, record = _call_grok(
        executable="grok-fixture",
        model="grok-4.6",
        reasoning="high",
        prompt="judge this",
        output_dir=tmp_path,
        response_schema=schema,
        batch_number=1,
        timeout=10,
        allow_unattested_reasoning=True,
    )
    assert json.loads(content) == {"verdicts": []}
    assert len(calls) == 1
    assert record["cli_version"] == "Grok Build CLI 1.0.fixture"
    assert record["requested"] == {"model": "grok-4.6", "reasoning_effort": "high"}
    assert record["reported"] == {
        "provider": "grok",
        "model": "grok-4.6-build",
    }
    assert session_ids[0] not in json.dumps(record)
    assert "fixture-request-id" not in json.dumps(record)
    assert record["reasoning_attested"] is False


def test_grok_backend_rejects_unattested_output_envelope(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    monkeypatch.setattr(
        "hbqrs.runner.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout='{"structuredOutput": {}}', stderr=""
        ),
    )
    with pytest.raises(HBQError, match="modelUsage entry"):
        _call_grok(
            executable="grok-fixture",
            model="grok-4.6",
            reasoning="high",
            prompt="judge this",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
        )


def test_grok_backend_requires_explicit_unattested_reasoning_opt_in(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "fixture")
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "structuredOutput": {}, "modelUsage": {"grok-4.6-build": {}},
                    "sessionId": argv[argv.index("--session-id") + 1],
                    "requestId": "request",
                    "stopReason": "end_turn",
                    "num_turns": 1,
                }
            ),
            stderr="",
        )
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    with pytest.raises(HBQError, match="allow-unattested-reasoning"):
        _call_grok(
            executable="grok-fixture", model="grok-4.6", reasoning="high", prompt="judge",
            output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=10,
        )


def test_grok_schema_output_failure_retries_only_after_attested_envelope(tmp_path: Path, monkeypatch) -> None:
    first_envelope = {
        "text": '{"verdicts": []}',
        "structuredOutput": None,
        "structuredOutputError": "model did not produce structured output",
        "modelUsage": {"grok-4.6-build": {"input_tokens": 1}},
        "requestId": "schema-failure-request",
        "stopReason": "end_turn",
        "num_turns": 1,
    }
    accepted_envelope = {
            "structuredOutput": {
                "verdicts": [
                    {
                        "question_id": QUESTION_ID,
                        "verdict": "YES",
                        "confidence": 0.8,
                        "evidence": [
                            {
                                "kind": "exact_quote",
                                "reference": "source.md",
                                "exact_quote": "A short test scene.",
                                "summary": None,
                            }
                        ],
                        "note": "The requested operation is assessable.",
                    }
                ]
            },
            "modelUsage": {"grok-4.6-build": {"input_tokens": 1}},
            "requestId": "accepted-request",
            "stopReason": "end_turn",
            "num_turns": 1,
    }
    calls = 0
    first_stdout: str | None = None
    first_session_id: str | None = None

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls, first_session_id, first_stdout
        calls += 1
        envelope = dict(first_envelope if calls == 1 else accepted_envelope)
        session_id = argv[argv.index("--session-id") + 1]
        envelope["sessionId"] = session_id
        stdout = json.dumps(envelope)
        if calls == 1:
            first_session_id = session_id
            first_stdout = stdout
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)

    assert _run(
        tmp_path,
        provider="grok",
        model="grok-4.6",
        grok_bin="grok-fixture",
        reasoning="high",
        allow_unattested_reasoning=True,
        allow_remote=True,
        batch_attempts=2,
    )["verdicts"] == 1
    assert calls == 2
    assert first_stdout is not None
    assert first_session_id is not None
    rejected = json.loads(
        (tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").read_text(encoding="utf-8")
    )
    assert rejected["stage"] == "provider"
    assert rejected["raw_content"]["text"] == first_stdout
    assert rejected["provider"]["session_id_sha256"] == hashlib.sha256(first_session_id.encode()).hexdigest()
    assert rejected["provider"]["request_id_sha256"] == hashlib.sha256(b"schema-failure-request").hexdigest()
    assert first_session_id not in json.dumps(rejected["provider"])
    assert "schema-failure-request" not in json.dumps(rejected["provider"])
    assert rejected["error"]["message"] == "Grok CLI reported a schema-output failure"
    checkpoint = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert checkpoint["accepted_attempt"] == 2


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda envelope: envelope.update({"stopReason": "cancelled"}), "exactly one normal turn"),
        (lambda envelope: envelope.update({"modelUsage": {"unexpected-model": {}}}), "effective settings"),
        (lambda envelope: envelope.pop("sessionId"), "accepted attested mapping"),
        (lambda envelope: envelope.update({"structuredOutputError": ""}), "lacks an object structuredOutput"),
    ],
)
def test_grok_schema_output_failure_keeps_identity_and_envelope_gates_nonretryable(
    tmp_path: Path,
    monkeypatch,
    mutation,
    expected: str,
) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    envelope = {
        "structuredOutput": None,
        "structuredOutputError": "model did not produce structured output",
        "modelUsage": {"grok-4.6-build": {"input_tokens": 1}},
        "sessionId": "fixture-session-id",
        "requestId": "fixture-request-id",
        "stopReason": "end_turn",
        "num_turns": 1,
    }
    mutation(envelope)
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        response = dict(envelope)
        if "sessionId" in response:
            response["sessionId"] = argv[argv.index("--session-id") + 1]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(response), stderr="")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)

    with pytest.raises(HBQError, match=expected) as exc_info:
        _call_grok(
            executable="grok-fixture",
            model="grok-4.6",
            reasoning="high",
            prompt="judge this",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
            allow_unattested_reasoning=True,
        )
    assert getattr(exc_info.value, "retryable") is False


def test_grok_malformed_envelope_is_nonretryable(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    monkeypatch.setattr(
        "hbqrs.runner.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="{not-json", stderr=""),
    )

    with pytest.raises(HBQError, match="invalid JSON output") as exc_info:
        _call_grok(
            executable="grok-fixture",
            model="grok-4.6",
            reasoning="high",
            prompt="judge this",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
            allow_unattested_reasoning=True,
        )
    assert getattr(exc_info.value, "retryable") is False


@pytest.mark.parametrize("num_turns", [True, 1.0])
def test_grok_schema_output_failure_requires_an_exact_integer_turn(tmp_path: Path, monkeypatch, num_turns: object) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    envelope = {
        "structuredOutput": None,
        "structuredOutputError": "model did not produce structured output",
        "modelUsage": {"grok-4.6-build": {}},
        "requestId": "fixture-request-id",
        "stopReason": "end_turn",
        "num_turns": num_turns,
    }
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        response = dict(envelope)
        response["sessionId"] = argv[argv.index("--session-id") + 1]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(response), stderr="")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)

    with pytest.raises(HBQError, match="exactly one normal turn") as exc_info:
        _call_grok(
            executable="grok-fixture", model="grok-4.6", reasoning="high", prompt="judge",
            output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=10,
            allow_unattested_reasoning=True,
        )
    assert getattr(exc_info.value, "retryable") is False


def test_grok_rejects_contradictory_structured_output_and_error(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    envelope = {
        "structuredOutput": {"verdicts": []},
        "structuredOutputError": "model did not produce structured output",
        "modelUsage": {"grok-4.6-build": {}},
        "requestId": "fixture-request-id",
        "stopReason": "end_turn",
        "num_turns": 1,
    }
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        response = dict(envelope)
        response["sessionId"] = argv[argv.index("--session-id") + 1]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(response), stderr="")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)

    with pytest.raises(HBQError, match="contradicts its structured output") as exc_info:
        _call_grok(
            executable="grok-fixture", model="grok-4.6", reasoning="high", prompt="judge",
            output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=10,
            allow_unattested_reasoning=True,
        )
    assert getattr(exc_info.value, "retryable") is False


@pytest.mark.parametrize("identifier", ["sessionId", "requestId"])
def test_grok_rejects_whitespace_identity_ids(tmp_path: Path, monkeypatch, identifier: str) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    envelope = {
        "structuredOutput": None,
        "structuredOutputError": "model did not produce structured output",
        "modelUsage": {"grok-4.6-build": {}},
        "sessionId": "fixture-session-id",
        "requestId": "fixture-request-id",
        "stopReason": "end_turn",
        "num_turns": 1,
    }
    envelope[identifier] = " \t "
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        response = dict(envelope)
        if identifier != "sessionId":
            response["sessionId"] = argv[argv.index("--session-id") + 1]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(response), stderr="")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)

    with pytest.raises(HBQError, match="accepted attested mapping") as exc_info:
        _call_grok(
            executable="grok-fixture", model="grok-4.6", reasoning="high", prompt="judge",
            output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=10,
            allow_unattested_reasoning=True,
        )
    assert getattr(exc_info.value, "retryable") is False


@pytest.mark.parametrize("matches_request", [False, True])
def test_grok_binds_response_session_to_the_fresh_request(tmp_path: Path, monkeypatch, matches_request: bool) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    requested_session: list[str] = []
    envelope = {
        "structuredOutput": {"verdicts": []},
        "modelUsage": {"grok-4.6-build": {}},
        "requestId": "fixture-request-id",
        "stopReason": "end_turn",
        "num_turns": 1,
    }
    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        session_id = argv[argv.index("--session-id") + 1]
        requested_session.append(session_id)
        response = dict(envelope)
        response["sessionId"] = session_id if matches_request else "unrelated-session-id"
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(response), stderr="")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)

    if not matches_request:
        with pytest.raises(HBQError, match="sessionId does not match") as exc_info:
            _call_grok(
                executable="grok-fixture", model="grok-4.6", reasoning="high", prompt="judge",
                output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=10,
                allow_unattested_reasoning=True,
            )
        assert getattr(exc_info.value, "retryable") is False
        return
    _, record = _call_grok(
        executable="grok-fixture", model="grok-4.6", reasoning="high", prompt="judge",
        output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=10,
        allow_unattested_reasoning=True,
    )
    assert record["session_id_sha256"] == hashlib.sha256(requested_session[0].encode()).hexdigest()
    assert requested_session[0] not in json.dumps(record)


def test_grok_schema_output_failure_cannot_expand_cumulative_resume_attempts(tmp_path: Path, monkeypatch) -> None:
    stdout = json.dumps(
        {
            "structuredOutput": None,
            "structuredOutputError": "model did not produce structured output",
            "modelUsage": {"grok-4.6-build": {"input_tokens": 1}},
            "requestId": "schema-failure-request",
            "stopReason": "end_turn",
            "num_turns": 1,
        }
    )
    calls = 0

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        envelope = json.loads(stdout)
        envelope["sessionId"] = argv[argv.index("--session-id") + 1]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(envelope), stderr="")

    monkeypatch.setattr("hbqrs.runner._grok_cli_version", lambda **_: "Grok Build CLI fixture")
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    arguments = {
        "provider": "grok",
        "model": "grok-4.6",
        "grok_bin": "grok-fixture",
        "reasoning": "high",
        "allow_unattested_reasoning": True,
        "allow_remote": True,
        "batch_attempts": 1,
    }
    with pytest.raises(HBQError, match="Batch 1 exhausted 1 cumulative attempts"):
        _run(tmp_path, **arguments)
    assert calls == 1
    with pytest.raises(HBQError, match="Batch 1 exhausted 1 cumulative attempts"):
        _run(tmp_path, resume=True, **arguments)
    assert calls == 1


def test_nous_backend_uses_only_canonical_tool_free_launcher(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    launcher = tmp_path / "launch-bridge.ps1"
    launcher.write_text("fixture", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert argv[:5] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(launcher.resolve())]
        if "-ProveLock" in argv:
            evidence = Path(argv[argv.index("-EvidenceRoot") + 1])
            proof = evidence / "proof.json"
            proof.write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"proof_path": str(proof)}), stderr="")
        request_path = Path(argv[argv.index("-JudgeRequest") + 1])
        result_path = Path(argv[argv.index("-JudgeResult") + 1])
        evidence = Path(argv[argv.index("-EvidenceRoot") + 1])
        proof = Path(argv[argv.index("-SerializationProof") + 1])
        assert proof.is_file()
        request = json.loads(request_path.read_text(encoding="utf-8"))
        assert request["schema"] == "codex-nous-tool-free-judge-request-v1"
        assert request["model"] in {"deepseek/deepseek-v4-flash-0731", "deepseek/deepseek-v4-pro-0813", "stealth/ox-alpha"}
        assert request["reasoning_effort"] == "max"
        assert request["response_format"]["json_schema"]["strict"] is True
        assert len(request["messages"]) == 2
        assert evidence.is_dir()
        canonical = {
            "deepseek/deepseek-v4-flash-0731": "deepseek/deepseek-v4-flash-20260731",
            "deepseek/deepseek-v4-pro-0813": "deepseek/deepseek-v4-pro-20260813",
            "stealth/ox-alpha": "stealth/ox-alpha",
        }[request["model"]]
        result_path.write_text(
            json.dumps(
                {
                    "schema": "codex-nous-tool-free-judge-result-v1",
                    "result": {"verdicts": []},
                    "metadata": {
                        "requested_provider": "nous",
                        "requested_model": request["model"],
                        "provider_reported_model": canonical,
                        "provider_canonical_model": canonical,
                        "requested_reasoning_effort": "max",
                        "provider_reported_reasoning_effort": None,
                        "tool_free": True,
                        "tool_mode": "judge",
                        "tool_call_count": 0,
                        "exact_gate_eligible": False,
                        "logical_provider_request_count": 1,
                        "physical_http_attempt_count": 1,
                        "recovered_request_count": 0,
                        "judge_transport_policy": {
                            "schema": "codex-nous-tool-free-judge-transport-v1",
                            "logical_requests_per_attempt": 1,
                            "max_physical_attempts_per_logical_request": 2,
                            "retry_policy_version": "hardened-v2-provider-attempts-v1",
                            "retryable_statuses": [408, 409, 425, 429],
                        },
                        "judge_model_policy": {
                            "requested_model": request["model"],
                            "provider_canonical_model": canonical,
                            "required_reasoning_effort": "max",
                        },
                        "evidence_validation": {"valid": True, "exact_gate_eligible": False},
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr("hbqrs.runner.NOUS_LAUNCHER_PATH", launcher)
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    monkeypatch.setattr("hbqrs.runner._validate_nous_judge_evidence", lambda **_: None)
    with pytest.raises(HBQError, match="allow-unattested-reasoning"):
        _call_nous(
            model="deepseek/deepseek-v4-flash-0731",
            reasoning="max",
            prompt="judge this",
            output_dir=tmp_path / "denied",
            response_schema=schema,
            batch_number=1,
            timeout=10,
        )
    content, record = _call_nous(
        model="deepseek/deepseek-v4-flash-0731",
        reasoning="max",
        prompt="judge this",
        output_dir=tmp_path,
        response_schema=schema,
        batch_number=1,
        timeout=10,
        allow_unattested_reasoning=True,
    )
    assert json.loads(content) == {"verdicts": []}
    assert len(calls) == 4
    assert record["reported"] == {"provider": "nous", "model": "deepseek/deepseek-v4-flash-20260731"}
    assert record["reasoning_attested"] is False
    assert record["tool_free"] is True
    pro_content, pro_record = _call_nous(
        model="deepseek/deepseek-v4-pro-0813", reasoning="max", prompt="judge this",
        output_dir=tmp_path / "pro", response_schema=schema, batch_number=1, timeout=10,
        allow_unattested_reasoning=True,
    )
    assert json.loads(pro_content) == {"verdicts": []}
    assert pro_record["provider_canonical_model"] == "deepseek/deepseek-v4-pro-20260813"
    ox_content, ox_record = _call_nous(
        model="stealth/ox-alpha", reasoning="max", prompt="judge this",
        output_dir=tmp_path / "ox", response_schema=schema, batch_number=1, timeout=10,
        allow_unattested_reasoning=True,
    )
    assert json.loads(ox_content) == {"verdicts": []}
    assert ox_record["provider_canonical_model"] == "stealth/ox-alpha"
    assert len(calls) == 8


def _write_bound_nous_judge_evidence(
    *, root: Path, request: dict[str, object], result: dict[str, object], transport_policy: dict[str, object]
) -> dict[str, object]:
    root.mkdir()
    key = b"n" * 32
    (root / ".evidence-hmac.key").write_bytes(key)
    run = root / "judge-run"
    run.mkdir()
    model_policy = {
        "requested_model": "stealth/ox-alpha",
        "provider_canonical_model": "stealth/ox-alpha",
        "required_reasoning_effort": "max",
    }
    boundary = {
        "request_schema": request["schema"],
        "request_sha256": runner_module._sha256_bytes(runner_module._nous_canonical_bytes(request)),
        "response_format": request["response_format"],
        "zero_tools": True,
        "transport_policy": transport_policy,
        "model_policy": model_policy,
    }
    outcome_metadata = {
        "judge_request_sha256": boundary["request_sha256"],
        "judge_response_schema_sha256": runner_module._sha256_bytes(
            runner_module._nous_canonical_bytes(request["response_format"])
        ),
        "judge_result_sha256": runner_module._sha256_bytes(runner_module._nous_canonical_bytes(result)),
        "judge_transport_policy": transport_policy,
        "judge_model_policy": model_policy,
    }
    records = [
        ("judge_boundary", boundary),
        *[("message", {"direction": "outbound", "message": message}) for message in request["messages"]],
        ("message", {"direction": "inbound", "message": {"role": "assistant", "content": json.dumps(result)}}),
        ("outcome", {"status": "success", "metadata": outcome_metadata}),
    ]
    previous = "0" * 64
    events: list[dict[str, object]] = []
    for sequence, (event_type, data) in enumerate(records):
        base = {
            "sequence": sequence,
            "timestamp": "2026-08-21T00:00:00+00:00",
            "event_type": event_type,
            "previous_entry_sha256": previous,
            "data": data,
        }
        digest = runner_module._sha256_bytes(runner_module._nous_canonical_bytes(base))
        events.append({
            **base,
            "entry_sha256": digest,
            "hmac_sha256": hmac.new(key, digest.encode("ascii"), hashlib.sha256).hexdigest(),
        })
        previous = digest
    events_bytes = b"".join(runner_module._nous_canonical_bytes(event) + b"\n" for event in events)
    (run / "events.jsonl").write_bytes(events_bytes)
    manifest = {"schema": "codex-nous-evidence-v1", "run_id": "judge-run"}
    manifest_bytes = runner_module._nous_canonical_bytes(manifest)
    (run / "manifest.json").write_bytes(manifest_bytes)
    receipt = {
        "schema": "codex-nous-outcome-v1",
        "run_id": "judge-run",
        "sealed_at": "2026-08-21T00:00:00+00:00",
        "status": "success",
        "event_count": len(events),
        "terminal_chain_sha256": previous,
        "events_sha256": runner_module._sha256_bytes(events_bytes),
        "manifest_sha256": runner_module._sha256_bytes(manifest_bytes),
        "bridge_sha256": "b" * 64,
        "outcome": {"metadata": outcome_metadata},
    }
    receipt_sha256 = runner_module._sha256_bytes(runner_module._nous_canonical_bytes(receipt))
    receipt["receipt_sha256"] = receipt_sha256
    receipt["hmac_sha256"] = hmac.new(key, receipt_sha256.encode("ascii"), hashlib.sha256).hexdigest()
    (run / "receipt.json").write_bytes(runner_module._nous_canonical_bytes(receipt))
    return {
        **outcome_metadata,
        "run_id": "judge-run",
        "evidence_path": str(run),
        "receipt_sha256": receipt_sha256,
        "terminal_chain_sha256": previous,
        "evidence_validation": {"valid": True},
    }


def test_nous_evidence_replay_independently_binds_default_v1_and_rejects_hash_tamper(tmp_path: Path) -> None:
    request = {
        "schema": "codex-nous-tool-free-judge-request-v1",
        "model": "stealth/ox-alpha",
        "reasoning_effort": "max",
        "messages": [{"role": "user", "content": "synthetic"}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {"type": "object"}}},
    }
    original_request_bytes = runner_module._nous_canonical_bytes(request)
    result = {"verdicts": []}
    policy = {
        "schema": "codex-nous-tool-free-judge-transport-v1",
        "logical_requests_per_attempt": 1,
        "max_physical_attempts_per_logical_request": 2,
        "retry_policy_version": "hardened-v2-provider-attempts-v1",
        "retryable_statuses": [408, 409, 425, 429],
    }
    metadata = _write_bound_nous_judge_evidence(root=tmp_path / "evidence", request=request, result=result, transport_policy=policy)
    runner_module._validate_nous_judge_evidence(
        evidence_root=tmp_path / "evidence",
        request=request,
        result=result,
        metadata=metadata,
        transport_policy=policy,
        model_policy={
            "requested_model": "stealth/ox-alpha",
            "provider_canonical_model": "stealth/ox-alpha",
            "required_reasoning_effort": "max",
        },
    )
    assert runner_module._nous_canonical_bytes(request) == original_request_bytes
    metadata["judge_result_sha256"] = "0" * 64
    with pytest.raises(HBQError, match="does not bind"):
        runner_module._validate_nous_judge_evidence(
            evidence_root=tmp_path / "evidence",
            request=request,
            result=result,
            metadata=metadata,
            transport_policy=policy,
            model_policy={
                "requested_model": "stealth/ox-alpha",
                "provider_canonical_model": "stealth/ox-alpha",
                "required_reasoning_effort": "max",
            },
        )


def test_nous_backend_rejects_any_nonpinned_model_or_reasoning(tmp_path: Path) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    with pytest.raises(HBQError, match="Nous requires an allowlisted"):
        _call_nous(
            model="other-model",
            reasoning="high",
            prompt="judge this",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
        )


def test_nous_one_physical_attempt_uses_the_v2_request_contract(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    launcher = tmp_path / "launch-bridge.ps1"
    launcher.write_text("fixture", encoding="utf-8")

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "-ProveLock" in argv:
            evidence = Path(argv[argv.index("-EvidenceRoot") + 1])
            proof = evidence / "proof.json"
            proof.write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"proof_path": str(proof)}), stderr="")
        request_path = Path(argv[argv.index("-JudgeRequest") + 1])
        result_path = Path(argv[argv.index("-JudgeResult") + 1])
        request = json.loads(request_path.read_text(encoding="utf-8"))
        assert request["schema"] == "codex-nous-tool-free-judge-request-v2"
        assert request["max_physical_http_attempts_per_logical_request"] == 1
        result_path.write_text(
            json.dumps(
                {
                    "schema": "codex-nous-tool-free-judge-result-v1",
                    "result": {"verdicts": []},
                    "metadata": {
                        "requested_provider": "nous",
                        "requested_model": request["model"],
                        "provider_reported_model": "stealth/ox-alpha",
                        "provider_canonical_model": "stealth/ox-alpha",
                        "requested_reasoning_effort": "max",
                        "provider_reported_reasoning_effort": None,
                        "tool_free": True,
                        "tool_mode": "judge",
                        "tool_call_count": 0,
                        "exact_gate_eligible": False,
                        "logical_provider_request_count": 1,
                        "physical_http_attempt_count": 1,
                        "recovered_request_count": 0,
                        "judge_transport_policy": {
                            "schema": "codex-nous-tool-free-judge-transport-v1",
                            "logical_requests_per_attempt": 1,
                            "max_physical_attempts_per_logical_request": 1,
                            "retry_policy_version": "hardened-v2-provider-attempts-v1",
                            "retryable_statuses": [408, 409, 425, 429],
                        },
                        "judge_model_policy": {
                            "requested_model": "stealth/ox-alpha",
                            "provider_canonical_model": "stealth/ox-alpha",
                            "required_reasoning_effort": "max",
                        },
                        "evidence_validation": {"valid": True, "exact_gate_eligible": False},
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr("hbqrs.runner.NOUS_LAUNCHER_PATH", launcher)
    monkeypatch.setattr("hbqrs.runner.subprocess.run", fake_run)
    monkeypatch.setattr("hbqrs.runner._validate_nous_judge_evidence", lambda **_: None)
    content, record = _call_nous(
        model="stealth/ox-alpha",
        reasoning="max",
        prompt="judge this",
        output_dir=tmp_path,
        response_schema=schema,
        batch_number=1,
        timeout=10,
        allow_unattested_reasoning=True,
        max_physical_http_attempts_per_logical_request=1,
    )
    assert json.loads(content) == {"verdicts": []}
    assert record["transport_policy"]["max_physical_attempts_per_logical_request"] == 1


@pytest.mark.parametrize("cap", [0, 2, True, "1"])
def test_nous_one_physical_attempt_rejects_malformed_caps(tmp_path: Path, cap: object) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    with pytest.raises(HBQError, match="exactly 1"):
        _call_nous(
            model="stealth/ox-alpha",
            reasoning="max",
            prompt="judge this",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
            max_physical_http_attempts_per_logical_request=cap,  # type: ignore[arg-type]
        )


def test_non_nous_runner_rejects_a_physical_attempt_cap(tmp_path: Path) -> None:
    with pytest.raises(HBQError, match="applies only to Nous"):
        _run(tmp_path, max_physical_http_attempts_per_logical_request=1)


def test_ox_alpha_requires_requested_max_reasoning(tmp_path: Path) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    with pytest.raises(HBQError, match="allowlisted"):
        _call_nous(
            model="stealth/ox-alpha",
            reasoning="high",
            prompt="judge this",
            output_dir=tmp_path,
            response_schema=schema,
            batch_number=1,
            timeout=10,
        )


def test_provider_artifact_validation_rejects_missing_or_corrupt_files(tmp_path: Path) -> None:
    artifact = tmp_path / "responses" / "provider.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("fixture", encoding="utf-8")
    record = {
        "provider": {
            "provider_artifacts": {
                "grok_envelope": {
                    "path": "responses/provider.json",
                    "bytes": 7,
                    "sha256": hashlib.sha256(b"fixture").hexdigest(),
                }
            }
        }
    }
    _validate_provider_artifacts(tmp_path, record)
    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(HBQError, match="not bound"):
        _validate_provider_artifacts(tmp_path, record)
    artifact.unlink()
    with pytest.raises(HBQError, match="not bound"):
        _validate_provider_artifacts(tmp_path, record)


def test_terminal_sidecars_start_before_send_and_settle_accepted(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, _ = fake_openai_endpoint
    _run(
        tmp_path,
        base_url=base_url,
        attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
    )
    root = tmp_path / "run" / "responses" / "attempt-lifecycle" / "batch-0001"
    start = json.loads((root / "attempt-0001.start.json").read_text(encoding="utf-8"))
    settled = json.loads((root / "attempt-0001.settled.json").read_text(encoding="utf-8"))
    assert start["state"] == "started"
    assert settled["outcome"] == "accepted"
    assert "A short test scene." not in json.dumps({"start": start, "settled": settled})


def test_terminal_start_only_holds_resume_without_resend(tmp_path: Path, monkeypatch) -> None:
    def interrupted(**_: object) -> tuple[str, dict[str, object]]:
        raise KeyboardInterrupt()

    monkeypatch.setattr(runner_module, "_call_openai", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY)

    def must_not_send(**_: object) -> tuple[str, dict[str, object]]:
        raise AssertionError("resume must not send an unresolved terminal attempt")

    monkeypatch.setattr(runner_module, "_call_openai", must_not_send)
    with pytest.raises(HBQError, match="ambiguous"):
        _run(
            tmp_path,
            resume=True,
            attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
        )


def test_terminal_resume_reconstructs_a_missing_settlement_without_send(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    _run(
        tmp_path,
        base_url=base_url,
        attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
    )
    settlement = tmp_path / "run" / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.settled.json"
    settlement.unlink()
    _run(
        tmp_path,
        base_url=base_url,
        resume=True,
        attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
    )
    assert handler.calls == 1
    assert json.loads(settlement.read_text(encoding="utf-8"))["outcome"] == "accepted"


def test_terminal_nonretryable_provider_failure_holds_resume(tmp_path: Path, monkeypatch) -> None:
    def nonretryable(**_: object) -> tuple[str, dict[str, object]]:
        raise runner_module._ProviderAttemptFailure("permanent", retryable=False)

    monkeypatch.setattr(runner_module, "_call_openai", nonretryable)
    with pytest.raises(HBQError, match="not retryable"):
        _run(tmp_path, attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY)
    record = json.loads((tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").read_text(encoding="utf-8"))
    assert record["attempt_outcome"] == "provider_nonretryable_failure"
    with pytest.raises(HBQError, match="terminal nonretryable"):
        _run(
            tmp_path,
            resume=True,
            attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
        )


def test_terminal_reconcile_counts_without_a_provider_call(tmp_path: Path, monkeypatch) -> None:
    def interrupted(**_: object) -> tuple[str, dict[str, object]]:
        raise KeyboardInterrupt()

    monkeypatch.setattr(runner_module, "_call_openai", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY)
    reconciled = runner_module.reconcile_attempt(
        tmp_path / "run", batch_number=1, attempt_number=1, count_as="retryable"
    )
    assert reconciled["status"] == "RECONCILED"
    rejection = json.loads(Path(tmp_path / "run" / reconciled["rejected_attempt"]).read_text(encoding="utf-8"))
    assert rejection["stage"] == "manual_reconcile"
    assert rejection["attempt_outcome"] == "provider_retryable_failure"


def test_terminal_reconcile_tampered_start_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner_module, "_call_openai", lambda **_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY)
    start_path = tmp_path / "run" / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.start.json"
    start = json.loads(start_path.read_text(encoding="utf-8"))
    start["policy"] = "forged"
    start_path.write_text(json.dumps(start), encoding="utf-8")
    before = sorted(path.relative_to(tmp_path / "run").as_posix() for path in (tmp_path / "run").rglob("*"))
    with pytest.raises(HBQError, match="start is malformed"):
        runner_module.reconcile_attempt(tmp_path / "run", batch_number=1, attempt_number=1, count_as="retryable")
    after = sorted(path.relative_to(tmp_path / "run").as_posix() for path in (tmp_path / "run").rglob("*"))
    assert after == before


def test_terminal_retryable_reconcile_then_next_attempt_accepts(tmp_path: Path, fake_openai_endpoint, monkeypatch) -> None:
    base_url, handler = fake_openai_endpoint
    original = runner_module._call_openai

    def interrupted(**_: object) -> tuple[str, dict[str, object]]:
        raise KeyboardInterrupt()

    monkeypatch.setattr(runner_module, "_call_openai", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run(
            tmp_path, base_url=base_url,
            attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
        )
    runner_module.reconcile_attempt(tmp_path / "run", batch_number=1, attempt_number=1, count_as="retryable")
    manual_settlement = tmp_path / "run" / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.settled.json"
    manual_settlement.unlink()  # Simulate a crash after durable manual accounting but before settlement.
    monkeypatch.setattr(runner_module, "_call_openai", original)
    summary = _run(
        tmp_path, base_url=base_url, resume=True,
        attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
    )
    checkpoint = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert handler.calls == 1 and summary["verdicts"] == 1
    assert checkpoint["accepted_attempt"] == 2
    assert json.loads(manual_settlement.read_text(encoding="utf-8"))["evidence"] == {
        "kind": "manual_reconcile", "count_as": "retryable"
    }


def test_terminal_free_text_refusal_is_schema_failure_not_structured_refusal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner_module, "_call_openai", lambda **_: ("I refuse this request.", {}))
    with pytest.raises(HBQError, match="exhausted"):
        _run(
            tmp_path,
            batch_attempts=1,
            attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
    )
    record = json.loads((tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").read_text(encoding="utf-8"))
    assert record["attempt_outcome"] == "schema_or_quote_failure"


def test_terminal_refusal_classification_requires_structured_provider_field() -> None:
    assert runner_module._openai_structured_refusal(
        {"choices": [{"message": {"content": "", "refusal": "policy refusal"}}]}
    )
    assert not runner_module._openai_structured_refusal(
        {"choices": [{"message": {"content": "I refuse this request."}}]}
    )
    refusal = runner_module._ProviderAttemptFailure(
        "structured refusal", retryable=False, attempt_outcome="model_refusal"
    )
    assert runner_module._attempt_outcome_for_provider_failure(refusal) == "model_refusal"
    assert runner_module._attempt_outcome_for_provider_failure(
        runner_module._ProviderAttemptFailure("retry", retryable=True)
    ) == "provider_retryable_failure"


def test_structured_refusal_is_terminal_only_for_opted_in_v5_runs(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.structured_refusal = "fixture refusal"
    legacy_dir, terminal_dir = tmp_path / "legacy", tmp_path / "terminal"
    legacy_dir.mkdir()
    terminal_dir.mkdir()
    legacy = _run(legacy_dir, base_url=base_url)
    assert legacy["verdicts"] == 1
    with pytest.raises(HBQError, match="not retryable"):
        _run(
            terminal_dir, base_url=base_url,
            attempt_lifecycle_policy=runner_module.ATTEMPT_LIFECYCLE_POLICY,
        )
    record = json.loads((terminal_dir / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").read_text(encoding="utf-8"))
    assert record["attempt_outcome"] == "model_refusal"
