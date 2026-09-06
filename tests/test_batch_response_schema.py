from __future__ import annotations

import json
from pathlib import Path

import pytest

from hbqrs import book_root, cli, runner
from hbqrs.core import HBQError


def test_batch_schema_binds_exact_ordered_ids_and_tail_minimum() -> None:
    schema = runner._batch_response_schema(["alpha", "beta", "gamma"])
    verdicts = schema["properties"]["verdicts"]
    assert verdicts["minItems"] == 3 and "maxItems" not in verdicts
    assert verdicts["items"]["properties"]["question_id"]["enum"] == ["alpha", "beta", "gamma"]
    assert runner._response_schema() != schema


@pytest.mark.parametrize("ids", ([], ["duplicate", "duplicate"]))
def test_batch_schema_rejects_empty_or_duplicate_ids(ids: list[str]) -> None:
    with pytest.raises(HBQError, match="question IDs"):
        runner._batch_response_schema(ids)


def test_cli_parses_opt_in_mode_and_keeps_default_absent(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("fixture", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(cli, "run_judge", lambda **kwargs: captured.update(kwargs) or {"status": "DRY_RUN"})
    assert cli.main(["judge", str(artifact), "--bundle", "prose.short_story", "--provider", "codex", "--model", "fixture", "--output-dir", str(tmp_path / "run"), "--dry-run", "--response-schema-mode", "batch_question_ids_v1"]) == 0
    assert captured["response_schema_mode"] == "batch_question_ids_v1"
    assert cli.main(["judge", str(artifact), "--bundle", "prose.short_story", "--provider", "codex", "--model", "fixture", "--output-dir", str(tmp_path / "run2"), "--dry-run"]) == 0
    assert captured["response_schema_mode"] is None


def test_unknown_mode_rejects_before_artifact_read(tmp_path) -> None:
    with pytest.raises(HBQError, match="Unknown response_schema_mode"):
        runner.run_judge(artifact_path=tmp_path / "missing.txt", bundle_id="prose.short_story", provider="codex", model="fixture", output_dir=tmp_path / "run", registry="registry/all_modules.json", bundles="bundles/all_bundles.json", response_schema_mode="unknown")


def _run_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, resume: bool = False):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    seen = []
    def fake_call(**kwargs):
        schema = json.loads(kwargs["response_schema"].read_text(encoding="utf-8"))
        seen.append(schema)
        ids = schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"]
        return json.dumps({"verdicts": [{"question_id": item, "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}], "note": "fixture"} for item in ids]}), {"model": "fixture"}
    monkeypatch.setattr(runner, "_call_openai", fake_call)
    result = runner.run_judge(artifact_path=artifact, bundle_id="prose.scene", provider="openai", model="fixture", output_dir=tmp_path / "run", registry=book_root() / "registry/all_modules.json", bundles=book_root() / "bundles/all_bundles.json", question_ids=["core.task_and_brief_fidelity.operation", "core.length_and_scope_fit.explicit"], batch_size=1, resume=resume, response_schema_mode="batch_question_ids_v1")
    return result, seen


def test_opt_in_delivers_exact_persisted_schema_and_rejects_tampered_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _run_opt_in(tmp_path, monkeypatch)
    assert result["status"] == "DIAGNOSTIC_SUBSET" and [schema["properties"]["verdicts"]["minItems"] for schema in seen] == [1, 1]
    schema = tmp_path / "run/responses/schemas/batch-0001.json"
    schema.write_text("{}", encoding="utf-8")
    with pytest.raises(HBQError, match="schema drift"):
        _run_opt_in(tmp_path, monkeypatch, resume=True)


def test_opt_in_rejects_extra_schema_inventory_and_mode_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_opt_in(tmp_path, monkeypatch)
    (tmp_path / "run/responses/schemas/extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(HBQError, match="inventory"):
        _run_opt_in(tmp_path, monkeypatch, resume=True)
    (tmp_path / "run/responses/schemas/extra.json").unlink()
    artifact = tmp_path / "artifact.txt"
    with pytest.raises(HBQError, match="settings changed"):
        runner.run_judge(artifact_path=artifact, bundle_id="prose.scene", provider="openai", model="fixture", output_dir=tmp_path / "run", registry=book_root() / "registry/all_modules.json", bundles=book_root() / "bundles/all_bundles.json", question_ids=["core.task_and_brief_fidelity.operation", "core.length_and_scope_fit.explicit"], batch_size=1, resume=True)


def test_offline_checkpoint_replay_rejects_opt_in_schema_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_opt_in(tmp_path, monkeypatch)
    (tmp_path / "run/responses/schemas/batch-0001.json").write_text("{}", encoding="utf-8")
    with pytest.raises(HBQError, match="schema"):
        runner._load_checkpoints(tmp_path / "run", artifact_text="A short test scene.", context_texts=[], batch_attempts=3)


def test_opt_in_missing_schema_recovery_requires_zero_execution_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    calls = []
    original_write = runner._atomic_write
    def interrupted_write(path, raw):
        if Path(path).as_posix().endswith("responses/schemas/batch-0002.json"):
            raise OSError("synthetic schema-publication interruption")
        return original_write(path, raw)
    monkeypatch.setattr(runner, "_atomic_write", interrupted_write)
    monkeypatch.setattr(runner, "_call_openai", lambda **_: calls.append("provider") or pytest.fail("must not contact provider"))
    with pytest.raises(OSError, match="publication interruption"):
        runner.run_judge(artifact_path=artifact, bundle_id="prose.scene", provider="openai", model="fixture", output_dir=tmp_path / "run", registry=book_root() / "registry/all_modules.json", bundles=book_root() / "bundles/all_bundles.json", question_ids=["core.task_and_brief_fidelity.operation", "core.length_and_scope_fit.explicit"], batch_size=1, response_schema_mode="batch_question_ids_v1")
    assert calls == []
    monkeypatch.setattr(runner, "_atomic_write", original_write)
    result, seen = _run_opt_in(tmp_path, monkeypatch, resume=True)
    run_root = tmp_path / "run"
    assert result["status"] == "DIAGNOSTIC_SUBSET" and len(seen) == 2
    assert (run_root / "responses/schemas/batch-0002.json").is_file()


def test_opt_in_missing_schema_after_response_evidence_rejects_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_opt_in(tmp_path, monkeypatch)
    (tmp_path / "run/responses/schemas/batch-0001.json").unlink()
    monkeypatch.setattr(runner, "_call_openai", lambda **_: pytest.fail("must not contact provider"))
    artifact = tmp_path / "artifact.txt"
    with pytest.raises(HBQError, match="schema"):
        runner.run_judge(artifact_path=artifact, bundle_id="prose.scene", provider="openai", model="fixture", output_dir=tmp_path / "run", registry=book_root() / "registry/all_modules.json", bundles=book_root() / "bundles/all_bundles.json", question_ids=["core.task_and_brief_fidelity.operation", "core.length_and_scope_fit.explicit"], batch_size=1, resume=True, response_schema_mode="batch_question_ids_v1")


def test_openai_request_body_binds_opt_in_schema_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = tmp_path / "schema.json"
    expected_schema = runner._batch_response_schema(["q-1"])
    schema.write_text(json.dumps(expected_schema), encoding="utf-8")
    bodies = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, *_): return b'{"model":"fixture","choices":[{"message":{"content":"{\\"verdicts\\":[]}"}}]}'
    class Opener:
        def open(self, request, timeout):
            bodies.append(json.loads(request.data))
            return Response()
    monkeypatch.setattr(runner, "build_opener", lambda *_: Opener())
    monkeypatch.setenv("HBQ_SCHEMA_TEST_KEY", "fixture")
    common = {"endpoint": "https://example.invalid/v1/chat/completions", "api_key_env": "HBQ_SCHEMA_TEST_KEY", "model": "fixture", "system_prompt": "system", "user_prompt": "user", "temperature": None, "allow_model_mismatch": False, "timeout": 1}
    runner._call_openai(response_schema=schema, **common)
    runner._call_openai(**common)
    assert bodies[0]["response_format"] == {"type": "json_schema", "json_schema": {"name": "hbq_batch_verdicts", "strict": True, "schema": expected_schema}}
    assert "response_format" not in bodies[1]


def test_opt_in_remote_disclosure_binds_mode_and_descriptors_only(tmp_path: Path, capsys) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("fixture", encoding="utf-8")
    common = {"artifact_path": artifact, "bundle_id": "prose.scene", "provider": "openai", "model": "fixture", "registry": book_root() / "registry/all_modules.json", "bundles": book_root() / "bundles/all_bundles.json", "question_ids": ["core.task_and_brief_fidelity.operation"], "base_url": "https://example.invalid/v1"}
    with pytest.raises(HBQError, match="off-machine"):
        runner.run_judge(output_dir=tmp_path / "opt-in", response_schema_mode="batch_question_ids_v1", **common)
    opt_in = capsys.readouterr().err
    assert '"response_schema_mode": "batch_question_ids_v1"' in opt_in and '"batch_response_schemas"' in opt_in and 'batch-0001.json' in opt_in
    with pytest.raises(HBQError, match="off-machine"):
        runner.run_judge(output_dir=tmp_path / "default", **common)
    legacy = capsys.readouterr().err
    assert "response_schema_mode" not in legacy and "batch_response_schemas" not in legacy


def test_post_provider_schema_tamper_prevents_accepted_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("A short test scene.", encoding="utf-8")
    def fake_call(**kwargs):
        schema_path = kwargs["response_schema"]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_path.write_text("{}", encoding="utf-8")
        question_id = schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"][0]
        return json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}], "note": "fixture"}]}), {"model": "fixture"}
    monkeypatch.setattr(runner, "_call_openai", fake_call)
    with pytest.raises(HBQError, match="schema drift"):
        runner.run_judge(artifact_path=artifact, bundle_id="prose.scene", provider="openai", model="fixture", output_dir=tmp_path / "run", registry=book_root() / "registry/all_modules.json", bundles=book_root() / "bundles/all_bundles.json", question_ids=["core.task_and_brief_fidelity.operation"], batch_size=1, response_schema_mode="batch_question_ids_v1")
    assert not (tmp_path / "run/responses/batch-0001.json").exists()
