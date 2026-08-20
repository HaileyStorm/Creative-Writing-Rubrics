from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import json
from pathlib import Path
import subprocess
import threading

import pytest

from hbqrs import HBQError, book_root
from hbqrs.runner import _call_codex, _normalize_batch, _parse_model_json, run_judge


QUESTION_ID = "core.task_and_brief_fidelity.operation"
SECOND_QUESTION_ID = "core.length_and_scope_fit.explicit"


def _questions_from_prompt(prompt: str) -> list[dict[str, object]]:
    block = prompt.rsplit("```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    calls = 0
    response_model: str | None = None
    fail_on_call: int | None = None

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
                "evidence": [{"reference": "line:1", "quote": "A short test scene."}],
                "note": "The requested operation is assessable.",
            }
            for item in _questions_from_prompt(prompt)
        ]
        body = json.dumps(
            {
                "id": "fake-response",
                "model": type(self).response_model or request["model"],
                "choices": [{"message": {"role": "assistant", "content": json.dumps({"verdicts": verdicts})}}],
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
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def fake_openai_endpoint():
    _FakeOpenAIHandler.calls = 0
    _FakeOpenAIHandler.response_model = None
    _FakeOpenAIHandler.fail_on_call = None
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


def test_openai_runner_checkpoints_scores_and_resumes(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    summary = _run(tmp_path, base_url=base_url)

    assert summary["verdicts"] == 1
    assert handler.calls == 1
    verdict = json.loads((tmp_path / "run" / "verdicts.jsonl").read_text(encoding="utf-8"))
    assert verdict["question_id"] == QUESTION_ID
    assert verdict["bundle_id"] == "prose.scene"
    assert (tmp_path / "run" / "score.json").is_file()
    manifest = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
    assert "A short test scene." not in json.dumps(manifest)
    assert manifest["configuration"]["artifact"]["sha256"]
    prompt = gzip.decompress((tmp_path / "run" / "responses" / "batch-0001.prompt.txt.gz").read_bytes())
    assert b"A short test scene." in prompt
    assert QUESTION_ID.encode() in prompt

    resumed = _run(tmp_path, base_url=base_url, resume=True)
    assert resumed["verdicts"] == 1
    assert handler.calls == 1

    verdict["run_id"] = "another-run"
    (tmp_path / "run" / "verdicts.jsonl").write_text(json.dumps(verdict) + "\n", encoding="utf-8")
    with pytest.raises(HBQError, match="does not match the ordered response checkpoints"):
        _run(tmp_path, base_url=base_url, resume=True)


def test_partial_multi_batch_run_resumes_without_overwrite(tmp_path: Path, fake_openai_endpoint) -> None:
    base_url, handler = fake_openai_endpoint
    handler.fail_on_call = 2
    with pytest.raises(HBQError, match="HTTP 500"):
        _run(
            tmp_path,
            base_url=base_url,
            question_ids=[QUESTION_ID, SECOND_QUESTION_ID],
            batch_size=1,
        )
    first = (tmp_path / "run" / "responses" / "batch-0001.json").read_bytes()
    assert not (tmp_path / "run" / "responses" / "batch-0002.json").exists()
    assert len((tmp_path / "run" / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()) == 1

    handler.fail_on_call = None
    summary = _run(
        tmp_path,
        base_url=base_url,
        question_ids=[QUESTION_ID, SECOND_QUESTION_ID],
        batch_size=1,
        resume=True,
    )
    assert summary["verdicts"] == 2
    assert handler.calls == 3
    assert (tmp_path / "run" / "responses" / "batch-0001.json").read_bytes() == first
    assert (tmp_path / "run" / "responses" / "batch-0002.json").is_file()


def test_remote_endpoint_requires_explicit_disclosure_gate(tmp_path: Path, capsys) -> None:
    with pytest.raises(HBQError, match="--allow-remote"):
        _run(tmp_path, base_url="https://example.com/v1")
    assert not (tmp_path / "run").exists()
    disclosure = capsys.readouterr().err
    assert QUESTION_ID in disclosure
    assert "Does the output perform the requested operation" in disclosure
    assert "BINARY_EVALUATION_PROMPT.md" in disclosure


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


def test_strict_model_response_rejects_missing_note_and_quote() -> None:
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
        )


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
        for feature in ("shell_tool", "multi_agent", "apps", "browser_use", "computer_use"):
            assert feature in argv
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
                    "evidence": [{"reference": "line:1", "quote": "A short test scene."}],
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
    assert verdict_schema["properties"]["evidence"]["items"]["additionalProperties"] is False
    response = json.loads((tmp_path / "run" / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert "stderr_tail" not in response["provider"]


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
