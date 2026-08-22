from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-verifier-v2"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verifier = load("supplemental_hanna_verifier_v2", "analyze_study.py")


def _historical_subset(tmp_path: Path) -> Path:
    configured = os.environ.get("CWR_HISTORICAL_GROK_WORK")
    if not configured:
        pytest.skip("set CWR_HISTORICAL_GROK_WORK to run historical Grok integration checks")
    historical_work = Path(configured)
    if not historical_work.is_dir():
        pytest.skip("CWR_HISTORICAL_GROK_WORK is not an available historical Grok work root")
    work = tmp_path / "work"
    (work / "invocations" / "grok_4_6_high").mkdir(parents=True)
    shutil.copyfile(historical_work / "frozen-provider-contract.json", work / "frozen-provider-contract.json")
    shutil.copyfile(historical_work / "invocations" / "grok_4_6_high" / "development.json", work / "invocations" / "grok_4_6_high" / "development.json")
    return work


def _historical_work() -> Path:
    configured = os.environ.get("CWR_HISTORICAL_GROK_WORK")
    if not configured:
        pytest.skip("set CWR_HISTORICAL_GROK_WORK to run historical Grok integration checks")
    historical_work = Path(configured)
    if not historical_work.is_dir():
        pytest.skip("CWR_HISTORICAL_GROK_WORK is not an available historical Grok work root")
    return historical_work


def test_historical_generation_accepts_the_pinned_invocation_without_current_runner_bytes(tmp_path):
    runtime = verifier._generation_runtime(_historical_subset(tmp_path), "grok_4_6_high", "development")
    assert runtime["components"]["runner"]["sha256"] == "ef87816de970738a44d16fbbd105f2309cb0e3750557502a2f68ee7f7b71d95c"
    assert runtime["components"]["runner"]["sha256"] != hashlib.sha256((book_root() / "src" / "hbqrs" / "runner.py").read_bytes()).hexdigest()


def test_complete_historical_corpus_does_not_read_the_checkout_binary_prompt(monkeypatch):
    original_frozen_text = verifier._frozen_text
    monkeypatch.setattr(verifier, "_frozen_text", lambda path: pytest.fail("historical binary prompt must not be read from the checkout") if path.name == "BINARY_EVALUATION_PROMPT.md" else original_frozen_text(path))
    corpus = verifier.verify_corpus(_historical_work(), "grok_4_6_high", "development")
    assert (corpus["run_count"], corpus["checkpoint_count"]) == (88, 528)


def test_historical_generation_rejects_current_runner_substitution(tmp_path):
    work = _historical_subset(tmp_path)
    invocation_path = work / "invocations" / "grok_4_6_high" / "development.json"
    record = json.loads(invocation_path.read_text(encoding="utf-8"))
    current = book_root() / "src" / "hbqrs" / "runner.py"
    record["runner"] = {"path": str(current), "bytes": current.stat().st_size, "sha256": hashlib.sha256(current.read_bytes()).hexdigest()}
    invocation_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="Historical invocation"):
        verifier._generation_runtime(work, "grok_4_6_high", "development")


def test_historical_component_paths_are_relocation_safe_but_not_lookalikes():
    generation = verifier._contract()["historical_generation"]
    expected = generation["invocations"]["grok_4_6_high/development"]["components"]["runner"]
    binding = {"path": r"D:\different-clone\src\hbqrs\runner.py", "bytes": expected["bytes"], "sha256": expected["sha256"]}
    assert verifier._historical_component({"runner": binding}, "runner", expected, generation["package_commit"]) == expected
    for path in (r"D:\different-clone\src\hbqrs-lookalike\runner.py", r"D:\different-clone\src\hbqrs\runner.py.bak"):
        with pytest.raises(ValueError, match="component binding drifted"):
            verifier._historical_component({"runner": {**binding, "path": path}}, "runner", expected, generation["package_commit"])


def test_pre_manifest_verifier_drift_requires_a_committed_runtime(monkeypatch, tmp_path):
    drifted = tmp_path / "analyze_study.py"
    drifted.write_bytes(verifier.VERIFIER_RUNTIME_PATH.read_bytes() + b"\n# drift\n")
    monkeypatch.setattr(verifier, "VERIFIER_RUNTIME_PATH", drifted)
    with pytest.raises(ValueError, match="Runtime path is outside the repository"):
        verifier._require_committed_verifier_runtime()


def test_verification_manifest_rejects_v2_runtime_drift(monkeypatch, tmp_path):
    corpus = {"generation_runtime": {}, "provider_id": "grok_4_6_high", "phase": "development", "run_count": 88, "checkpoint_count": 528, "receipt_chain_sha256": "a" * 64, "root_commitment": {}}
    monkeypatch.setattr(verifier, "_require_committed_verifier_runtime", lambda: None)
    monkeypatch.setattr(verifier, "verify_corpus", lambda *_: corpus)
    output = tmp_path / "output"
    verifier.write_verification_manifest(tmp_path, "grok_4_6_high", "development", output)
    drifted = tmp_path / "verifier.py"
    drifted.write_bytes(verifier.VERIFIER_RUNTIME_PATH.read_bytes() + b"\n# drift\n")
    monkeypatch.setattr(verifier, "VERIFIER_RUNTIME_PATH", drifted)
    with pytest.raises(ValueError, match="Runtime path is outside the repository"):
        verifier.verify_verification_manifest(tmp_path, "grok_4_6_high", "development", output)


def test_verification_manifest_rejects_later_dependency_binding_drift(monkeypatch, tmp_path):
    corpus = {"generation_runtime": {}, "provider_id": "grok_4_6_high", "phase": "development", "run_count": 88, "checkpoint_count": 528, "receipt_chain_sha256": "a" * 64, "root_commitment": {}}
    monkeypatch.setattr(verifier, "_require_committed_verifier_runtime", lambda: None)
    monkeypatch.setattr(verifier, "verify_corpus", lambda *_: corpus)
    dependencies = dict(verifier.VERIFIER_DEPENDENCY_PATHS)
    dependencies["hbqrs_runner"] = Path(__file__).resolve()
    monkeypatch.setattr(verifier, "VERIFIER_DEPENDENCY_PATHS", dependencies)
    output = tmp_path / "output"
    verifier.write_verification_manifest(tmp_path, "grok_4_6_high", "development", output)
    dependencies["hbqrs_runner"] = verifier.VERIFIER_RUNTIME_PATH
    with pytest.raises(ValueError, match="exact generation and verifier runtimes"):
        verifier.verify_verification_manifest(tmp_path, "grok_4_6_high", "development", output)


def _fake_frozen() -> dict:
    return {"selection": {"partitions": {"development": [{"item_id": f"item-{number}"} for number in range(88)]}}}


def _prepare_fake_corpus(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "work"
    root = work / "runs" / "grok_4_6_high" / "development"
    monkeypatch.setattr(verifier, "_generation_runtime", lambda *_: {})
    monkeypatch.setattr(verifier, "load_frozen", lambda *_: _fake_frozen())
    monkeypatch.setattr(verifier, "verify_run", lambda *_: ([{}], {}, [str(_[4]["item_id"])]) if len(_) > 4 else ([{}], {}, ["receipt"]))
    monkeypatch.setattr(verifier.GENERATION_ANALYSIS, "_checkpoint_files", lambda *_: [Path("one"), Path("two"), Path("three"), Path("four"), Path("five"), Path("six")])
    return work, root


def test_verify_corpus_rejects_empty_missing_and_extra_runs(monkeypatch, tmp_path):
    work, root = _prepare_fake_corpus(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="missing, extra, or mislocated"):
        verifier.verify_corpus(work, "grok_4_6_high", "development")
    for number in range(87):
        path = root / f"item-{number}" / "run-01"
        path.mkdir(parents=True)
        (path / "run.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="missing, extra, or mislocated"):
        verifier.verify_corpus(work, "grok_4_6_high", "development")
    final = root / "item-87" / "run-01"
    final.mkdir(parents=True)
    (final / "run.json").write_text("{}", encoding="utf-8")
    extra = root / "extra" / "run-01"
    extra.mkdir(parents=True)
    (extra / "run.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="missing, extra, or mislocated"):
        verifier.verify_corpus(work, "grok_4_6_high", "development")


def test_verify_run_preserves_mixed_newline_inputs_and_rejects_prompt_tampering(monkeypatch, tmp_path):
    work = tmp_path / "work"
    folder = tmp_path / "inputs" / "development" / "dev-0"
    folder.mkdir(parents=True)
    source_path, context_path = folder / "source.md", folder / "prompt.md"
    source_path.write_bytes(b"First line\r\nSecond line\n")
    context_path.write_bytes(b"Context one\nContext two\r\n")
    contract_path = folder / "task-contract.json"
    contract_path.write_bytes(b"{}\n")

    def bound(path: Path) -> dict[str, object]:
        data = path.read_bytes()
        return {"name": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    source, context = (path.read_bytes().decode("utf-8-sig") for path in (source_path, context_path))
    binary, binary_binding = verifier._historical_binary_prompt()
    binary_record = {"name": Path(binary_binding["relative_path"]).name, "bytes": binary_binding["bytes"], "sha256": binary_binding["sha256"]}
    rows = [{"role": "hard_gate", "question": {"id": "q-1"}}]
    default_weight, compiled = {"profile": "test"}, {"compiled": "test"}
    schema = {"name": "hbq_judge_response.schema.json", "bytes": 2, "sha256": "f" * 64}
    item = verifier.provider("grok_4_6_high")
    config = {"artifact": bound(source_path), "contexts": [bound(context_path)], "task_contract": {**bound(contract_path), "contract_id": "hanna"}, "bundle_id": "prose.short_story", "question_ids": ["q-1"], "provider": item["provider"], "model": item["model"], "reasoning": item["reasoning"], "batch_size": 32, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "evidence_normalization_policy": verifier.EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": verifier.VALIDATION_FEEDBACK_POLICY, "artifact_id": "dev-0", "judge_id": f"{item['provider']}:{item['model']}", "strict_ai": False, "allow_unattested_reasoning": True, "prompts": [binary_record], "response_schema": schema, "weight_profile": default_weight, "questions_sha256": hashlib.sha256(verifier._json_bytes(verifier._question_payload(rows))).hexdigest(), "compiled_bundle_sha256": hashlib.sha256(verifier._json_bytes(compiled)).hexdigest()}
    run = work / "runs" / "grok_4_6_high" / "development" / "dev-0" / "run-01"
    (run / "responses").mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"format_version": 3, "configuration": config, "config_sha256": hashlib.sha256(verifier._json_bytes(config)).hexdigest()}), encoding="utf-8")
    expected_prompt = verifier._render_prompt(binary_prompt=binary, artifact={"name": "source.md", "text": source}, contexts=[{"name": "prompt.md", "text": context}], bundle_id="prose.short_story", artifact_id="dev-0", questions=rows).encode("utf-8")
    clean_checkout_prompt = verifier._render_prompt(binary_prompt=binary.replace("\r\n", "\n"), artifact={"name": "source.md", "text": source}, contexts=[{"name": "prompt.md", "text": context}], bundle_id="prose.short_story", artifact_id="dev-0", questions=rows).encode("utf-8")
    assert clean_checkout_prompt != expected_prompt
    checkpoint = {"format_version": 4, "batch": 1, "question_ids": ["q-1"], "previous_checkpoint_sha256": None, "base_prompt_sha256": hashlib.sha256(expected_prompt).hexdigest(), "prompt_sha256": hashlib.sha256(expected_prompt).hexdigest(), "retry_policy": {"batch_attempts": 3}}
    checkpoint_path = run / "responses" / "batch-0001.json"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    checkpoint_path.with_suffix(".prompt.txt.gz").write_bytes(gzip.compress(expected_prompt))
    stored = [{"question_id": "q-1"}]
    (run / "verdicts.jsonl").write_text(json.dumps(stored[0]) + "\n", encoding="utf-8")
    (run / "score.json").write_text(json.dumps({"weight_profile": default_weight}), encoding="utf-8")
    frozen = {"input_commitments": {"development": {"dev-0": {"source.md": bound(source_path), "prompt.md": bound(context_path), "task-contract.json": bound(contract_path)}}, "confirmatory": {}}, "primary_runtime_files": {"prompts/judge/BINARY_EVALUATION_PROMPT.md": binary_record, "schema/hbq_judge_response.schema.json": schema}}
    seen_inputs: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(verifier, "primary_input", lambda *_: (folder, {"item_id": "dev-0"}))
    monkeypatch.setattr(verifier.GENERATION_ANALYSIS, "_expected_rows", lambda _: ({}, {}, rows, ["q-1"], default_weight))
    monkeypatch.setattr(verifier, "compile_bundle", lambda *_args, **_kwargs: compiled)
    original_frozen_text = verifier._frozen_text
    monkeypatch.setattr(verifier, "_frozen_text", lambda path: pytest.fail("historical binary prompt must not be read from the checkout") if path.name == "BINARY_EVALUATION_PROMPT.md" else original_frozen_text(path))
    monkeypatch.setattr(verifier, "receipt", lambda *_: "receipt")
    monkeypatch.setattr(verifier, "_load_checkpoints", lambda *_args, **kwargs: (seen_inputs.append((kwargs["artifact_text"], kwargs["context_texts"])) or stored, 1, None))
    monkeypatch.setattr(verifier, "score_bundle", lambda *_args, **_kwargs: {})

    assert verifier.verify_run(work, frozen, "grok_4_6_high", "development", {"item_id": "dev-0"}, 1)[0] == stored
    assert seen_inputs == [(source, [context])]
    checkpoint_path.with_suffix(".prompt.txt.gz").write_bytes(gzip.compress(expected_prompt + b"tampered"))
    with pytest.raises(ValueError, match="exact primary rendered batch bytes"):
        verifier.verify_run(work, frozen, "grok_4_6_high", "development", {"item_id": "dev-0"}, 1)


def test_historical_binary_prompt_payload_rejects_tampering(monkeypatch):
    contract = deepcopy(verifier._contract())
    contract["historical_generation"]["inputs"]["binary_prompt"]["base64_chunks"] = ["AA=="]
    monkeypatch.setattr(verifier, "_contract", lambda: contract)
    with pytest.raises(ValueError, match="payload hash drifted"):
        verifier._historical_binary_prompt()
