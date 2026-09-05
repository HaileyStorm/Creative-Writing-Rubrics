"""Public execution coverage for v2 score descendants over frozen v1 runs."""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hbqrs import run_judge
from hbqrs.cli import main

QUESTION_ID = "test.quality.present"


class _FakeProviderHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self) -> None:
        type(self).calls += 1
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        questions = json.loads(request["messages"][1]["content"].rsplit("```json\n", 1)[1].split("\n```", 1)[0])
        payload = {
            "id": "public-v2-test-response",
            "model": request["model"],
            "choices": [{"message": {"role": "assistant", "content": json.dumps({"verdicts": [
                {
                    "question_id": item["question_id"],
                    "verdict": "YES",
                    "confidence": 0.8,
                    "evidence": [{
                        "kind": "exact_quote",
                        "reference": "artifact:1",
                        "exact_quote": "A short test scene.",
                        "summary": None,
                    }],
                    "note": "The single test criterion is assessable.",
                }
                for item in questions
            ]})}}],
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> tuple[str, type[_FakeProviderHandler]]:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _FakeProviderHandler.calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", _FakeProviderHandler
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _write_single_question_catalog(tmp_path: Path) -> tuple[Path, Path]:
    registry = tmp_path / "registry.json"
    bundles = tmp_path / "bundles.json"
    registry.write_text(
        json.dumps([{
            "module_id": "test.quality",
            "title": "Test quality",
            "kind": "domain",
            "tree": [{
                "id": QUESTION_ID,
                "type": "question",
                "criterion_key": QUESTION_ID,
                "text": "Is the test scene present?",
                "pass_answer": "YES",
                "weight": 1.0,
                "question_type": "scored",
                "severity": "minor",
                "applies_when": "Always for this test catalog.",
                "evidence_policy": {"required": True, "minimum_references": 1},
            }],
        }]),
        encoding="utf-8",
    )
    bundles.write_text(
        json.dumps([{
            "bundle_id": "test.public-v2",
            "title": "Public v2 test",
            "domains": [{
                "domain_id": "quality",
                "title": "Quality",
                "points": 100,
                "components": [{"module_id": "test.quality"}],
            }],
            "module_ids": ["test.quality"],
        }]),
        encoding="utf-8",
    )
    return registry, bundles


def _run_arguments(tmp_path: Path, base_url: str) -> dict[str, object]:
    registry, bundles = _write_single_question_catalog(tmp_path)
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    return {
        "artifact_path": artifact,
        "bundle_id": "test.public-v2",
        "provider": "openai",
        "model": "fake-local",
        "output_dir": tmp_path / "run",
        "registry": registry,
        "bundles": bundles,
        "base_url": base_url,
        "batch_attempts": 1,
    }


def _assert_v2_preserves_single_question_parent(run_dir: Path) -> bytes:
    parent_bytes = (run_dir / "score.json").read_bytes()
    parent = json.loads(parent_bytes)
    descendant = json.loads((run_dir / "score.v2.json").read_text(encoding="utf-8"))
    assert parent["bundle_id"] == descendant["bundle_id"] == "test.public-v2"
    assert len(parent["domains"]) == 1
    assert len(parent["domains"][0]["questions"]) == 1
    assert descendant["parent_score_sha256"] == hashlib.sha256(parent_bytes).hexdigest()
    for key in ("$schema", "report_version", "confidence_diagnostics", "parent_score_sha256"):
        descendant.pop(key, None)
    parent.pop("$schema", None)
    assert descendant == parent
    return parent_bytes


def test_public_api_creates_resumable_v2_descendant_without_changing_v1_parent(
    tmp_path: Path, fake_provider: tuple[str, type[_FakeProviderHandler]]
) -> None:
    base_url, handler = fake_provider
    arguments = _run_arguments(tmp_path, base_url)

    first = run_judge(**arguments)
    assert first["verdicts"] == 1
    assert first["score_report_version"] == 2
    parent_bytes = _assert_v2_preserves_single_question_parent(Path(arguments["output_dir"]))
    descendant_bytes = (Path(arguments["output_dir"]) / "score.v2.json").read_bytes()

    resumed = run_judge(**arguments, resume=True)
    assert resumed == first
    assert handler.calls == 1
    assert (Path(arguments["output_dir"]) / "score.json").read_bytes() == parent_bytes
    assert (Path(arguments["output_dir"]) / "score.v2.json").read_bytes() == descendant_bytes


def test_cli_creates_and_resumes_the_public_v2_descendant(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, fake_provider: tuple[str, type[_FakeProviderHandler]]
) -> None:
    base_url, handler = fake_provider
    registry, bundles = _write_single_question_catalog(tmp_path)
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    run_dir = tmp_path / "cli-run"
    argv = [
        "--registry", str(registry), "--bundles", str(bundles), "judge", str(artifact),
        "--bundle", "test.public-v2", "--provider", "openai", "--model", "fake-local",
        "--output-dir", str(run_dir), "--base-url", base_url, "--batch-attempts", "1",
    ]

    assert main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["score_report_version"] == 2
    parent_bytes = _assert_v2_preserves_single_question_parent(run_dir)

    assert main([*argv, "--resume"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed == first
    assert handler.calls == 1
    assert (run_dir / "score.json").read_bytes() == parent_bytes
