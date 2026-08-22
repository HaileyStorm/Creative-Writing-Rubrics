from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v2"


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules.update(aliases or {})
    try: spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None: sys.modules.pop(key, None)
            else: sys.modules[key] = value
    return module


study = load("ox_alpha_v2_study", "study.py")
analysis = load("ox_alpha_v2_analysis", "analyze_pilot.py", {"study": study})
pilot = load("ox_alpha_v2_pilot", "run_pilot.py", {"study": study})


def task(item_id: str = "item") -> dict:
    return {"contract_version": 1, "contract_id": "hanna", "artifact_id": item_id, "context": {"artifact_kind": "story", "declared_scope": "complete", "completion_status": "complete", "background": ["prompt"], "constraints": ["respond"], "audience": ["reader"]}, "preferences": [], "priorities": [], "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story meaningfully respond to the prompt?", "weight": 2.0, "source": {"kind": "driving_prompt", "reference": "prompt", "exact_excerpt": "prompt"}, "applies_to": ["whole artifact"], "rationale": "signal"}], "binding_requirements": []}


def test_contract_preserves_v1_failure_and_freezes_179_18_36_geometry():
    assert study.CONTRACT["supersedes"]["status"] == "preserved_unexecuted_protocol_failure"
    assert study.CONTRACT["supersedes"]["contract_sha256"] == study.sha(study.V1_ROOT / "study-contract.json")
    assert study.CONTRACT["selection"]["item_ids"] == ["hanna-827", "hanna-957", "hanna-201"]
    assert study.CONTRACT["runtime"]["maximum_logical_requests"] == 18
    assert study.CONTRACT["runtime"]["maximum_physical_http_attempts"] == 36


def test_real_compiler_fixture_has_exact_179_and_final_19_batch(tmp_path):
    path = tmp_path / "task.json"; path.write_text(json.dumps(task()), encoding="utf-8")
    geometry = study.question_geometry(path)
    assert len(geometry["static_question_ids"]) == 178
    assert len(geometry["primary_question_ids"]) == 179
    assert [len(batch) for batch in geometry["primary_batches"]] == [32, 32, 32, 32, 32, 19]
    assert set(geometry["primary_question_ids"]) == set(geometry["static_question_ids"]) | {"task.contract.hanna.prompt_response"}
    assert geometry["task_contract_descendant"]["weighted_goals"] == []


def test_static_ablation_rejects_prefix_and_duplicate_json(tmp_path):
    path = tmp_path / "task.json"; path.write_text(json.dumps(task()), encoding="utf-8")
    geometry = study.question_geometry(path)
    rows = [{"question_id": item} for item in geometry["primary_question_ids"]]
    with pytest.raises(ValueError, match="exactly the 179"):
        study.static_ablation(rows[:178], task(), "item")
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        study.strict_json('{"x": 1, "x": 2}', label="fixture")


def test_load_rechecks_cost_freshness_and_fresh88_bindings(monkeypatch, tmp_path):
    checked: list[str] = []
    monkeypatch.setattr(study, "_assert_fresh_at", lambda _proof, when: checked.append(when))
    monkeypatch.setattr(study, "_zero_cost_proof", lambda path: {"path": str(path), "fingerprint": {"name": path.name, "bytes": 1, "sha256": "a" * 64}, "catalog": {"root": str(tmp_path / "catalog"), "sealed_at": "2026-08-21T00:00:00+00:00"}, "usage": {"root": str(tmp_path / "usage"), "sealed_at": "2026-08-21T00:00:00+00:00"}})
    for name in ("catalog", "usage", "fresh", "authority", "repair", "work"):
        (tmp_path / name).mkdir()
    proof = tmp_path / "proof.json"; proof.write_text("{}", encoding="utf-8")
    cells = []
    for number, item_id in enumerate(study.CONTRACT["selection"]["item_ids"], 1):
        path = tmp_path / f"{item_id}.task.json"; path.write_text(json.dumps(task(item_id)), encoding="utf-8")
        artifact, prompt = tmp_path / f"{item_id}.source.md", tmp_path / f"{item_id}.prompt.md"; artifact.write_text("story", encoding="utf-8"); prompt.write_text("prompt", encoding="utf-8")
        geo = study.question_geometry(path)
        cells.append({"cell_id": f"ox-alpha-v2-{number:02d}", "item_id": item_id, "paths": {"artifact": str(artifact), "prompt": str(prompt), "task_contract": str(path)}, "inputs": {"source.md": study.fingerprint(artifact), "prompt.md": study.fingerprint(prompt), "task-contract.json": study.fingerprint(path)}, "primary_question_ids": geo["primary_question_ids"], "primary_batches": geo["primary_batches"], "static_question_ids": geo["static_question_ids"], "task_contract_descendant": geo["task_contract_descendant"]})
    bindings = {key: {"path": "x", "bytes": 1, "sha256": "a" * 64} for key in ("execution_contract", "execution_receipt", "verifier_matrix", "semantic_gate")}
    fresh = {"sources": {"work": str(tmp_path / "fresh"), "authority": str(tmp_path / "authority"), "repair1_artifacts": str(tmp_path / "repair")}, **bindings}
    monkeypatch.setattr(study, "_fresh88_binding", lambda *_: bindings)
    monkeypatch.setattr(study, "_frozen_cells", lambda _: cells)
    monkeypatch.setattr(study, "_runtime_bindings", lambda: {})
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path / "managed-repository")
    payload = {"format_version": 2, "study_id": study.CONTRACT["study_id"], "frozen_before_execution": True, "study_contract": study.fingerprint(study.CONTRACT_PATH), "runtime": {}, "fresh88": fresh, "zero_cost_proof": {**study._zero_cost_proof(proof), "freshness_checked_at": "2026-08-21T00:00:00+00:00"}, "cells": cells}
    (tmp_path / "work" / study.FROZEN_NAME).write_text(json.dumps(payload), encoding="utf-8")
    loaded = study.load_frozen(tmp_path / "work")
    assert loaded["study_id"] == study.CONTRACT["study_id"] and checked
    payload["cells"][0]["primary_batches"][-1] = payload["cells"][0]["primary_batches"][-1][:-1]
    (tmp_path / "work" / study.FROZEN_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="question geometry"):
        study.load_frozen(tmp_path / "work")


def test_public_output_disjointness_fails_before_verification(monkeypatch, tmp_path):
    work, output = tmp_path / "work", tmp_path / "work" / "published"; work.mkdir()
    frozen = {"zero_cost_proof": {"path": str(tmp_path / "proof.json"), "catalog": {"root": str(tmp_path / "catalog")}, "usage": {"root": str(tmp_path / "usage")}}, "fresh88": {"sources": {"work": str(tmp_path / "fresh"), "authority": str(tmp_path / "authority"), "repair1_artifacts": str(tmp_path / "repair")}}, "cells": []}
    monkeypatch.setattr(analysis, "load_frozen", lambda _: frozen)
    monkeypatch.setattr(analysis, "verify_evidence", lambda *_: (_ for _ in ()).throw(AssertionError("must not verify")))
    with pytest.raises(ValueError, match="disjoint"):
        analysis.analyze(work, output)
    assert not output.exists()


def test_executor_verifies_each_cell_before_any_later_provider_call(monkeypatch, tmp_path):
    cells = [{"cell_id": "ox-alpha-v2-01", "item_id": "one", "primary_question_ids": ["q"]}, {"cell_id": "ox-alpha-v2-02", "item_id": "two", "primary_question_ids": ["q"]}]
    frozen = {"cells": cells, "zero_cost_proof": {"catalog": {"sealed_at": "2026-08-21T00:00:00+00:00"}, "usage": {"sealed_at": "2026-08-21T00:00:00+00:00"}}}
    source, prompt, contract = tmp_path / "source.md", tmp_path / "prompt.md", tmp_path / "task.json"
    source.write_text("story", encoding="utf-8"); prompt.write_text("prompt", encoding="utf-8"); contract.write_text(json.dumps(task("one")), encoding="utf-8")
    (tmp_path / study.FROZEN_NAME).write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen)
    monkeypatch.setattr(pilot, "_assert_fresh_at", lambda *_: None)
    monkeypatch.setattr(pilot, "input_paths", lambda _: (source, prompt, contract))
    monkeypatch.setattr(pilot, "run_judge", lambda **kwargs: (calls.append(kwargs["artifact_id"]), Path(kwargs["output_dir"]).mkdir(parents=True)))
    monkeypatch.setattr(analysis, "verify_run", lambda *_: (_ for _ in ()).throw(ValueError("recovered retry")))
    prior = sys.modules.get("analyze_pilot"); sys.modules["analyze_pilot"] = analysis
    try:
        with pytest.raises(ValueError, match="recovered retry"):
            pilot.execute(tmp_path)
    finally:
        if prior is None: sys.modules.pop("analyze_pilot", None)
        else: sys.modules["analyze_pilot"] = prior
    assert calls == ["one"]
    assert json.loads(next((tmp_path / "pilot-journal").glob("*.json")).read_text())['status'] == "failed"


def test_executor_stale_proof_fails_before_claim_or_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(pilot, "load_frozen", lambda _: {"cells": [], "zero_cost_proof": {}})
    monkeypatch.setattr(pilot, "_assert_fresh_at", lambda *_: (_ for _ in ()).throw(ValueError("not fresh")))
    with pytest.raises(ValueError, match="not fresh"):
        pilot.execute(tmp_path)
    assert not (tmp_path / "pilot-invocation.json").exists()
    assert not (tmp_path / "pilot-execution-claim.json").exists()


def test_verify_run_reconstructs_a_full_accepted_179_leaf_run(monkeypatch, tmp_path):
    from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
    from hbqrs.runner import _json_bytes
    from hbqrs.scoring_v2 import score_bundle as score_bundle_v2
    artifact, prompt, task_path = tmp_path / "source.md", tmp_path / "prompt.md", tmp_path / "task.json"
    artifact.write_text("A complete short story.", encoding="utf-8"); prompt.write_text("prompt", encoding="utf-8"); task_path.write_text(json.dumps(task("item")), encoding="utf-8")
    geometry = study.question_geometry(task_path)
    cell = {"cell_id": "ox-alpha-v2-01", "item_id": "item", "paths": {"artifact": str(artifact), "prompt": str(prompt), "task_contract": str(task_path)}, "inputs": {"source.md": study.fingerprint(artifact), "prompt.md": study.fingerprint(prompt), "task-contract.json": study.fingerprint(task_path)}, "primary_question_ids": geometry["primary_question_ids"], "primary_batches": geometry["primary_batches"], "static_question_ids": geometry["static_question_ids"], "task_contract_descendant": geometry["task_contract_descendant"]}
    verdicts = [{"artifact_id": "item", "bundle_id": "prose.short_story", "confidence": 0.9, "evidence": [{"reference": "source.md", "summary": "present"}], "judge_id": "nous:stealth/ox-alpha", "note": "", "question_id": item, "run_id": "test", "verdict": "YES"} for item in cell["primary_question_ids"]]
    run = tmp_path / "runs" / cell["cell_id"]; responses = run / "responses"; responses.mkdir(parents=True)
    (run / "verdicts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in verdicts), encoding="utf-8")
    modules, bundle = load_modules(book_root() / "registry" / "all_modules.json"), resolve_bundle(load_bundles(book_root() / "bundles" / "all_bundles.json"), "prose.short_story")
    primary = score_bundle(modules, bundle, verdicts, artifact_id="item", task_contract=task("item")); primary_v2 = score_bundle_v2(modules, bundle, verdicts, artifact_id="item", task_contract=task("item"))
    (run / "score.json").write_text(json.dumps(primary), encoding="utf-8"); (run / "score.v2.json").write_text(json.dumps(primary_v2), encoding="utf-8")
    config = {"bundle_id": "prose.short_story", "question_ids": cell["primary_question_ids"], "provider": "nous", "model": "stealth/ox-alpha", "reasoning": "max", "batch_size": 32, "retry_policy": {"batch_attempts": 1}, "artifact_id": "item", "strict_ai": False, "allow_unattested_reasoning": True, "nous_transport_policy": analysis.NOUS_TRANSPORT_POLICY, "nous_model_policy": {"requested_model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "required_reasoning_effort": "max"}, "artifact": cell["inputs"]["source.md"], "contexts": [cell["inputs"]["prompt.md"]], "task_contract": cell["inputs"]["task-contract.json"]}
    (run / "run.json").write_text(json.dumps({"format_version": 3, "configuration": config, "config_sha256": __import__("hashlib").sha256(_json_bytes(config)).hexdigest()}), encoding="utf-8")
    previous = None
    for number, ids in enumerate(cell["primary_batches"], 1):
        accepted = responses / f"accepted-{number}.json"; accepted.write_text("{}", encoding="utf-8")
        checkpoint = {"format_version": 4, "batch": number, "question_ids": ids, "previous_checkpoint_sha256": previous, "retry_policy": {"batch_attempts": 1}, "accepted_attempt": 1, "recovered_from_rejected": None, "rejected_chain": {"count": 0, "head_sha256": None}, "response_artifact": {"path": f"responses/{accepted.name}"}, "provider": {"physical_http_attempt_count": 1}}
        checkpoint_path = responses / f"batch-{number:04d}.json"; checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8"); previous = study.sha(checkpoint_path)
    monkeypatch.setattr(analysis, "_receipt", lambda _run, checkpoint: f"receipt-{checkpoint['batch']}")
    monkeypatch.setattr(analysis, "_load_checkpoints", lambda *_args, **_kwargs: (verdicts, 6, {}))
    proof = analysis.verify_run(tmp_path, {}, cell)
    assert proof["receipt_count"] == 6 and proof["primary_score"] == primary_v2["final_score"]["observed"]


@pytest.mark.skipif(not os.environ.get("CWR_OX_V2_REAL_FRESH88_ROOT"), reason="explicit local Fresh88 integration probe")
def test_optional_real_fresh88_integration_probe():
    fresh = Path(os.environ["CWR_OX_V2_REAL_FRESH88_ROOT"])
    authority = Path(os.environ["CWR_OX_V2_REAL_AUTHORITY_ROOT"])
    repair = Path(os.environ["CWR_OX_V2_REAL_REPAIR_ROOT"])
    binding = study._fresh88_binding(fresh, authority, repair)
    assert [cell["item_id"] for cell in binding["cells"]] == study.CONTRACT["selection"]["item_ids"]
