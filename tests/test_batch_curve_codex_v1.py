from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "batch-curve-codex-v1"


def _module():
    spec = importlib.util.spec_from_file_location("batch_curve_codex_v1", ROOT / "batch_curve_codex.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _local_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    if argv[:2] == ["git", "rev-parse"]:
        return subprocess.CompletedProcess(argv, 0, "d9042684fe262a0d2741e34974de311dc71b20e1\n", "")
    if argv[:2] == ["git", "status"]:
        return subprocess.CompletedProcess(argv, 0, "", "")
    if argv[:3] == ["git", "branch", "-r"]:
        return subprocess.CompletedProcess(argv, 0, "  origin/main\n", "")
    if argv[-1] == "--version":
        return subprocess.CompletedProcess(argv, 0, "codex 1.0.5\n", "")
    raise AssertionError(argv)


def test_contract_freezes_predecessors_exact_stack_and_39_cell_plan() -> None:
    module = _module()
    value = module.contract()
    assert len(module.plan()) == 39
    assert value["execution"]["strict_ai"] is True
    assert value["execution"]["batch_attempts"] == 3
    assert value["execution"]["checkpoint_format_version"] == 4
    assert value["recommendation"]["screening_recommendation"] is None
    for key in ("v2_contract", "v2_harness", "live_contract", "live_adapter"):
        assert len(value["parent"][key]["sha256"]) == 64
    assert value["execution"]["model"] == "gpt-5.6-sol"


def test_prompt_is_exact_strict_ai_prefix_binary_parity_and_contiguous_only() -> None:
    module = _module()
    ids = module.plan()[0]
    parent = json.loads((ROOT.parent / "batch-curve-v2" / "study-contract.json").read_text(encoding="utf-8"))
    batch = parent["runtime"]["frozen_question_ids"][:2]
    prompt, binding = module.effective_prompt(batch)
    assert prompt.startswith("# Strict AI-output evaluation prefix")
    assert "# Atomic binary evaluation prompt" in prompt
    assert binding["question_ids"] == batch
    assert binding["prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="contiguous"):
        module.effective_prompt([batch[0], parent["runtime"]["frozen_question_ids"][3]])
    assert ids["sequence"] == 1


def test_local_ordered_runner_persists_exact_first_and_all_in_one_prompts_with_zero_contexts(tmp_path: Path) -> None:
    module = _module()
    value, items = module.contract(), module._question_items(module.contract())
    parent = json.loads((ROOT.parent / "batch-curve-v2" / "study-contract.json").read_text(encoding="utf-8"))
    harness = module._v2_harness()
    inputs = value["frozen_inputs"]
    source = module._bound(inputs["source"]["path"], inputs["source"])
    prefix, binary = (module._bound(item["path"], item) for item in inputs["prompts"])
    calls = 0

    def fake_invoke(*, executable: str, model: str, reasoning: str, prompt: str, output_dir: Path, response_schema: Path, batch_number: int, attempt_number: int, timeout: float) -> tuple[str, dict]:
        nonlocal calls
        assert timeout == 600
        inspect.signature(__import__("hbqrs.runner", fromlist=["_call_codex"])._call_codex).bind(executable=executable, model=model, reasoning=reasoning, prompt=prompt, output_dir=output_dir, response_schema=response_schema, batch_number=batch_number, attempt_number=attempt_number, timeout=timeout)
        calls += 1
        ids = [item["question"]["id"] for item in items if item["question"]["id"] in prompt]
        return json.dumps({"verdicts": harness._fixture_verdicts(ids)}), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"fresh-{calls}"}}

    for size, expected_prompt in ((1, module.effective_prompt(parent["runtime"]["frozen_question_ids"][:1])[0]), (178, module.effective_prompt(parent["runtime"]["frozen_question_ids"])[0])):
        destination = tmp_path / str(size)
        module.run_ordered(output_dir=destination, source=source, registry=module._bound(inputs["registry"]["path"], inputs["registry"]), bundles=module._bound(inputs["bundles"]["path"], inputs["bundles"]), prefix=prefix, binary=binary, response_schema=module._bound(inputs["response_schema"]["path"], inputs["response_schema"]), question_items=items, batch_size=size, codex_bin="fake", timeout_seconds=600, invoke=fake_invoke)
        first = (destination / "responses" / "batch-0001.prompt.txt.gz").read_bytes()
        import gzip
        assert gzip.decompress(first).decode("utf-8") == expected_prompt
        assert module.verify_ordered(run_dir=destination, source=source, prefix=prefix, binary=binary, registry=module._bound(inputs["registry"]["path"], inputs["registry"]), bundles=module._bound(inputs["bundles"]["path"], inputs["bundles"]), score_v1_schema=module._bound(inputs["score_v1_schema"]["path"], inputs["score_v1_schema"]), score_v2_schema=module._bound(inputs["score_v2_schema"]["path"], inputs["score_v2_schema"]), question_items=items, batch_size=size, codex_bin="fake", timeout_seconds=600)["verdict_count"] == 178
    (tmp_path / "178" / "responses" / "attempt-started" / "batch-0001-attempt-0001.json").unlink()
    with pytest.raises(ValueError, match="attempt-started"):
        module.verify_ordered(run_dir=tmp_path / "178", source=source, prefix=prefix, binary=binary, registry=module._bound(inputs["registry"]["path"], inputs["registry"]), bundles=module._bound(inputs["bundles"]["path"], inputs["bundles"]), score_v1_schema=module._bound(inputs["score_v1_schema"]["path"], inputs["score_v1_schema"]), score_v2_schema=module._bound(inputs["score_v2_schema"]["path"], inputs["score_v2_schema"]), question_items=items, batch_size=178, codex_bin="fake", timeout_seconds=600)


def test_ordered_runner_resumes_after_a_persisted_rejection_without_resetting_feedback_budget(tmp_path: Path) -> None:
    module = _module(); value = module.contract(); inputs = value["frozen_inputs"]
    item = module._question_items(value)[:1]; source = module._bound(inputs["source"]["path"], inputs["source"])
    prefix, binary = (module._bound(entry["path"], entry) for entry in inputs["prompts"]); harness = module._v2_harness(); calls = 0
    def interrupted(**_kwargs: object) -> tuple[str, dict]:
        nonlocal calls; calls += 1
        if calls == 1: raise ValueError("first rejected")
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        module.run_ordered(output_dir=tmp_path / "run", source=source, registry=module._bound(inputs["registry"]["path"], inputs["registry"]), bundles=module._bound(inputs["bundles"]["path"], inputs["bundles"]), prefix=prefix, binary=binary, response_schema=module._bound(inputs["response_schema"]["path"], inputs["response_schema"]), question_items=item, batch_size=1, codex_bin="fake", timeout_seconds=600, invoke=interrupted)
    def accepted(**_kwargs: object) -> tuple[str, dict]:
        return json.dumps({"verdicts": harness._fixture_verdicts([item[0]["question"]["id"]])}), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "fresh-resume"}}
    module.run_ordered(output_dir=tmp_path / "run", source=source, registry=module._bound(inputs["registry"]["path"], inputs["registry"]), bundles=module._bound(inputs["bundles"]["path"], inputs["bundles"]), prefix=prefix, binary=binary, response_schema=module._bound(inputs["response_schema"]["path"], inputs["response_schema"]), question_items=item, batch_size=1, codex_bin="fake", timeout_seconds=600, invoke=accepted)
    rejected = tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    assert rejected.is_file() and (tmp_path / "run" / "responses" / "batch-0001.json").is_file()


def test_real_provider_failure_shape_hashes_rejected_session_and_stops_nonretryable(tmp_path: Path) -> None:
    module = _module(); value = module.contract(); inputs = value["frozen_inputs"]; item = module._question_items(value)[:1]; source = module._bound(inputs["source"]["path"], inputs["source"]); prefix, binary = (module._bound(entry["path"], entry) for entry in inputs["prompts"]); calls = 0
    def refused(**_kwargs: object) -> tuple[str, dict]:
        nonlocal calls; calls += 1
        from hbqrs import runner as shared
        raise shared._ProviderAttemptFailure("permanent", retryable=False, content="provider raw", provider_record={"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "raw-session"}})
    with pytest.raises(ValueError, match="exhausted"):
        module.run_ordered(output_dir=tmp_path / "run", source=source, registry=module._bound(inputs["registry"]["path"], inputs["registry"]), bundles=module._bound(inputs["bundles"]["path"], inputs["bundles"]), prefix=prefix, binary=binary, response_schema=module._bound(inputs["response_schema"]["path"], inputs["response_schema"]), question_items=item, batch_size=1, codex_bin="fake", timeout_seconds=600, invoke=refused)
    record = json.loads((tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").read_text(encoding="utf-8"))
    assert calls == 1 and record["retryable"] is False and record["provider_session_id_sha256"] == hashlib.sha256(b"raw-session").hexdigest() and "raw-session" not in json.dumps(record)
    assert {"format_version", "batch", "attempt", "sequence", "previous_rejected_sha256", "stage", "retry_policy", "prompt_sha256", "base_prompt_sha256", "effective_prompt_sha256", "validation_feedback_policy", "validation_feedback", "raw_content", "provider", "provider_session_id_sha256", "retryable", "error"} == set(record)


def test_signature_typeerror_is_local_nonretryable_and_restart_never_invokes(tmp_path: Path) -> None:
    module = _module(); value = module.contract(); inputs = value["frozen_inputs"]; item = module._question_items(value)[:1]; source = module._bound(inputs["source"]["path"], inputs["source"]); prefix, binary = (module._bound(entry["path"], entry) for entry in inputs["prompts"])
    common = {"output_dir": tmp_path / "run", "source": source, "registry": module._bound(inputs["registry"]["path"], inputs["registry"]), "bundles": module._bound(inputs["bundles"]["path"], inputs["bundles"]), "prefix": prefix, "binary": binary, "response_schema": module._bound(inputs["response_schema"]["path"], inputs["response_schema"]), "question_items": item, "batch_size": 1, "codex_bin": "fake", "timeout_seconds": 600}
    def wrong_signature(*, impossible: object) -> tuple[str, dict]:
        raise AssertionError(impossible)
    with pytest.raises(ValueError, match="nonretryable programmer"):
        module.run_ordered(**common, invoke=wrong_signature)
    record = json.loads((tmp_path / "run" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").read_text(encoding="utf-8"))
    assert record["stage"] == "local_invocation_error" and record["retryable"] is False and record["provider"] is None
    prompt = tmp_path / "run" / "responses" / "batch-0001.prompt.txt.gz"; before = prompt.read_bytes(); before_mtime = prompt.stat().st_mtime_ns
    with pytest.raises(ValueError, match="persisted nonretryable"):
        module.run_ordered(**common, invoke=lambda **_: pytest.fail("restart must not invoke"))
    assert prompt.read_bytes() == before and prompt.stat().st_mtime_ns == before_mtime


def test_prepare_requires_clean_pushed_commit_and_records_disclosure_before_any_run(tmp_path: Path) -> None:
    module = _module()
    work, private = tmp_path / "work", tmp_path / "private"
    receipt = module.prepare(work, private, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    assert (work / module.RECEIPT).is_file()
    assert receipt["pre_execution"] is True
    assert receipt["codex"]["version"] == "codex 1.0.5"
    assert receipt["outbound_disclosure"]["raw_evidence"].startswith("private")

    def dirty(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = _local_run(argv, **kwargs)
        if argv[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(argv, 0, " M source.md\n", "")
        return result

    with pytest.raises(ValueError, match="clean commit"):
        module.prepare(tmp_path / "other", private, subprocess_run=dirty, executable_resolver=lambda _: str(tmp_path / "codex.exe"))


def test_execution_persists_attempt_started_then_private_raw_indexes_without_a_recommendation(tmp_path: Path) -> None:
    module = _module()
    work, private = tmp_path / "work", tmp_path / "private"
    module.prepare(work, private, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    calls: list[Path] = []

    def fake_runner(**kwargs: object) -> dict[str, object]:
        assert kwargs["timeout_seconds"] == 600
        destination = Path(str(kwargs["output_dir"]))
        (destination / "responses" / "rejected" / "batch-0001").mkdir(parents=True, exist_ok=True)
        (destination / "run.json").write_text("{}\n", encoding="utf-8")
        (destination / "responses" / "rejected" / "batch-0001" / "attempt-0001.json").write_text("private raw rejected evidence\n", encoding="utf-8")
        calls.append(destination)
        return {}

    def fake_verifier(**kwargs: object) -> dict:
        assert kwargs["batch_size"] >= 1 and kwargs["question_items"] and kwargs["timeout_seconds"] == 600
        digest = hashlib.sha256(str(kwargs["run_dir"]).encode("utf-8")).hexdigest()
        return {"run_sha256": "a" * 64, "checkpoint_chain_head_sha256": "d" * 64, "sessions": [{"session_id_sha256": digest}], "rejected_attempt_count": 1}

    result = module.execute(work, private, runner=fake_runner, verifier=fake_verifier, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    assert result["completed_cells"] == 39 and result["screening_recommendation"] is None
    assert len(calls) == 39
    first = json.loads((work / "cells" / "cell-01.json").read_text(encoding="utf-8"))
    assert first["calls"][0] == {"event": "attempt_started", "attempt": 1}
    raw = first["calls"][1]["raw_evidence_index"]
    index = private / raw["relative_path"]
    assert index.stat().st_size == raw["bytes"]
    assert hashlib.sha256(index.read_bytes()).hexdigest() == raw["sha256"]
    public_cell = (work / "cells" / "cell-01.json").read_text(encoding="utf-8")
    assert "private raw rejected evidence" not in public_cell and str(private.resolve()) not in public_cell


def test_crash_after_durable_attempt_started_is_resumable_and_tampered_raw_index_fails_closed(tmp_path: Path) -> None:
    module = _module()
    work, private = tmp_path / "work", tmp_path / "private"
    module.prepare(work, private, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    original = module.plan
    module.plan = lambda: original()[:1]
    try:
        with pytest.raises(RuntimeError, match="interrupted"):
            module.execute(work, private, runner=lambda **_: (_ for _ in ()).throw(RuntimeError("interrupted")), verifier=lambda **_: {}, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
        cell = json.loads((work / "cells" / "cell-01.json").read_text(encoding="utf-8"))
        assert cell["status"] == "in_progress" and cell["calls"] == [{"event": "attempt_started", "attempt": 1}]

        def run_once(**kwargs: object) -> dict:
            destination = Path(str(kwargs["output_dir"])); destination.mkdir(parents=True, exist_ok=True); (destination / "run.json").write_text("{}", encoding="utf-8"); return {}
        verified = {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "checkpoint_chain_head_sha256": "d" * 64, "sessions": [], "rejected_attempt_count": 0}
        module.execute(work, private, runner=run_once, verifier=lambda **_: verified, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
        index = private / "evidence-index" / "cell-01.json"
        index.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="index drifted"):
            module._raw_index(private, "runs/cell-01")
    finally:
        module.plan = original


def test_execute_rejects_a_duplicate_session_across_two_cells(tmp_path: Path) -> None:
    module = _module(); work, private = tmp_path / "work", tmp_path / "private"
    module.prepare(work, private, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    original = module.plan; module.plan = lambda: original()[:2]
    try:
        def fake_runner(**kwargs: object) -> None:
            destination = Path(str(kwargs["output_dir"])); destination.mkdir(parents=True, exist_ok=True); (destination / "run.json").write_text("{}", encoding="utf-8")
        def duplicate(**_kwargs: object) -> dict:
            return {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "checkpoint_chain_head_sha256": "d" * 64, "verdict_count": 178, "rejected_attempt_count": 0, "sessions": [{"session_id_sha256": "e" * 64}]}
        with pytest.raises(ValueError, match="reused across cells"):
            module.execute(work, private, runner=fake_runner, verifier=duplicate, subprocess_run=_local_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    finally:
        module.plan = original
