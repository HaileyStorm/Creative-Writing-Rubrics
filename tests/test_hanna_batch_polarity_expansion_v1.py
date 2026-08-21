from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-hanna-batch-polarity-expansion-v1"


def _load(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification); sys.modules[specification.name] = module
    specification.loader.exec_module(module); return module


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _binding(study, path: Path):
    return study.fingerprint(path)


def _sources(study, tmp_path: Path):
    sources = {}
    for story in study.STORIES:
        source, prompt = tmp_path / f"{story}.md", tmp_path / f"{story}.prompt.md"
        source.write_text(f"Source for {story}.", encoding="utf-8"); prompt.write_text(f"Prompt for {story}.", encoding="utf-8")
        sources[story] = {"item_id": story, "artifact": _binding(study, source), "contexts": [_binding(study, prompt)], "task_contract": _binding(study, prompt)}
    return sources


def _prepared(study, tmp_path, monkeypatch):
    sources = _sources(study, tmp_path)
    mapped = study.pilot().focal_question_ids()[0]
    reused = {f"{condition}:{repetition}": [{"question_id": mapped, "verdict": "YES", "confidence": 0.8}] for condition in study.CONDITIONS for repetition in (1, 2, 3)}
    reuse = {"pilot_plan": _binding(study, study.CONTRACT_PATH), "pilot_stage3_raw_evidence": _binding(study, study.CONTRACT_PATH), "verified_cell_count": 12, "verdict_count": 12, "reused_calls": 198, "session_commitments": [_digest(f"reused-{index}") for index in range(198)], "verified": reused, "source_cell": sources["hanna-225"]}
    parent = {"runtime": {"root": "fixture", "files": {}, "sha256": _digest("runtime")}, "parent_work": _binding(study, study.CONTRACT_PATH), "parent_matrix": _binding(study, study.CONTRACT_PATH), "parent_gate": _binding(study, study.CONTRACT_PATH), "stories": {story: {"cell": sources[story], "verified_run": {}} for story in study.NEW_STORIES}}
    authority = tmp_path / "repeatability-authority.json"
    authority.write_text(json.dumps({"format_version": 1, "status": "frozen_before_expansion_execution", "ordered_story_ids": [f"hanna-{index}" for index in range(1, 14)], "first_eleven_story_ids": [f"hanna-{index}" for index in range(1, 12)]}), encoding="utf-8")
    monkeypatch.setattr(study, "_pilot_binding", lambda *_: reuse)
    monkeypatch.setattr(study, "_fresh_parent_inputs", lambda *_: parent)
    work = tmp_path / "work"
    private = tmp_path / "private"
    study.prepare(tmp_path / "pilot", tmp_path / "pilot-private", tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "parent-authority", tmp_path / "parent-runtime", authority, work, private)
    return work, private, study.load_plan(work), reused


def _rows(study, plan):
    rows = []
    for number, cell in enumerate((cell for cell in plan["cells"] if cell["source"] == "new_provider_evidence"), 1):
        calls = []
        for call_number, question_ids in enumerate(study._chunks(cell["question_ids"], study._condition(cell["condition_id"])["batch_size"]), 1):
            verdicts = [{"question_id": question_id, "verdict": "NO" if study.pilot().question_polarity(cell["condition_id"], question_id) == "negative_failure_condition" else "YES", "confidence": 0.9} for question_id in question_ids]
            response = json.dumps(verdicts, sort_keys=True)
            prompt = study.rendered_prompt(plan, cell, question_ids)
            calls.append({"question_ids": question_ids, "session_id_sha256": _digest(f"{number}-{call_number}"), "prompt": prompt, "prompt_sha256": _digest(prompt), "response": response, "response_sha256": _digest(response), "verdicts": verdicts})
        rows.append({"story_id": cell["story_id"], "condition_id": cell["condition_id"], "repetition": cell["repetition"], "calls": calls})
    return rows


def test_contract_freezes_exact_geometry_latin_rows_and_twelfth_selector():
    study = _load("hanna_expansion_geometry", "study.py")
    contract, cells = study.load_contract(), study.planned_cells()
    assert contract["geometry"] == {"calls_per_story": 198, "reused_calls": 198, "new_provider_calls": 594, "combined_session_commitments": 792}
    assert len(cells) == 48 and sum(cell["new_calls"] for cell in cells) == 594
    assert [cell["latin_row"] for cell in cells if cell["story_id"] == "hanna-225" and cell["within_repetition"] == 1] == ["L0", "L1", "L2"]
    assert [cell["latin_row"] for cell in cells if cell["story_id"] == "hanna-178" and cell["within_repetition"] == 1] == ["L1", "L2", "L3"]
    assert [cell["latin_row"] for cell in cells if cell["story_id"] == "hanna-817" and cell["within_repetition"] == 1] == ["L2", "L3", "L0"]
    assert [cell["latin_row"] for cell in cells if cell["story_id"] == "hanna-382" and cell["within_repetition"] == 1] == ["L3", "L0", "L1"]


def test_prepare_binds_sources_and_rejects_plan_tampering(tmp_path, monkeypatch):
    study = _load("hanna_expansion_prepare", "study.py")
    work, _, plan, _ = _prepared(study, tmp_path, monkeypatch)
    assert plan["twelfth_story"]["twelfth_story_id"] == "hanna-12"
    assert plan["execution"]["attempts_per_new_call"] == 1
    path = work / study.PLAN_NAME; tampered = json.loads(path.read_text(encoding="utf-8")); tampered["cells"][12]["latin_row"] = "L0"; path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="geometry"):
        study.load_plan(work)
    tampered["cells"] = plan["cells"]
    tampered["twelfth_story"]["twelfth_story_id"] = "hanna-13"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="twelfth-story"):
        study.load_plan(work)
    authority = tmp_path / "duplicate-authority.json"
    authority.write_text(json.dumps({"format_version": 1, "status": "frozen_before_expansion_execution", "ordered_story_ids": ["hanna-1"] * 12, "first_eleven_story_ids": [f"hanna-{index}" for index in range(1, 12)]}), encoding="utf-8")
    with pytest.raises(ValueError, match="ordered frozen prefix"):
        study._frozen_twelfth(authority)
    same_root = tmp_path / "same-root"
    with pytest.raises(ValueError, match="public work and private roots must be disjoint"):
        study.prepare(tmp_path / "pilot", tmp_path / "pilot-private", tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "parent-authority", tmp_path / "parent-runtime", authority, same_root, same_root)


def test_verify_and_metrics_cover_all_594_new_sessions_and_keep_labels_offline(tmp_path, monkeypatch):
    study = _load("hanna_expansion_metrics", "study.py")
    work, _, plan, reused = _prepared(study, tmp_path, monkeypatch)
    fast_questions = {question_id: f"Question {question_id}" for question_id in study.pilot()._full_question_ids()}
    monkeypatch.setattr(study.pilot(), "_question_texts", lambda: fast_questions)
    monkeypatch.setattr(study.pilot(), "question_polarity", lambda *_: "positive")
    rows = _rows(study, plan)
    verified = study.verify_evidence(plan, rows)
    assert set(verified) == set(study.STORIES)
    assert sum(len(call["calls"]) for call in rows) == 594
    result = study.metrics(plan, rows)
    assert result["recommendation"] is None and result["promotion"] == "forbidden"
    assert result["cross_story"]["exploratory_alignment"]["status"] == "unavailable_without_offline_published_labels"
    label_source = tmp_path / "published-source.csv"; label_source.write_text("published HANNA ratings", encoding="utf-8")
    labels = tmp_path / "offline-labels.json"
    labels.write_text(json.dumps({"format_version": 1, "status": "offline_published_hanna_only", "source": "HANNA published ratings", "source_fingerprint": _binding(study, label_source), "labels": {story: float(index) for index, story in enumerate(study.STORIES)}}), encoding="utf-8")
    aligned = study.metrics(plan, rows, published_hanna_labels=labels)
    assert aligned["cross_story"]["exploratory_alignment"]["global_positive_batch32"]["status"] == "exploratory_four_story_offline_published_labels"
    invalid = json.loads(labels.read_text(encoding="utf-8")); invalid["labels"][study.STORIES[0]] = float("nan"); labels.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="label record"):
        study.metrics(plan, rows, published_hanna_labels=labels)


def test_executor_is_prepare_dry_run_only_and_study_has_no_provider_transport():
    tree = ast.parse((ROOT / "study.py").read_text(encoding="utf-8"))
    imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imports & {"requests", "httpx", "urllib", "socket", "subprocess"}
    executor = (ROOT / "run_expansion.py").read_text(encoding="utf-8")
    assert 'mode.add_argument("--execute"' not in executor
    assert "callback: Callable" in executor and "started_without_terminal" in executor and "provider_or_response_failure" in executor


def test_executor_attempt_records_are_one_shot_and_restart_requires_a_bound_terminal(tmp_path):
    executor = _load("hanna_expansion_executor", "run_expansion.py")
    item = {"sequence": 1, "story_id": "hanna-178", "condition_id": "single_positive_batch1", "repetition": 1, "latin_row": "L1", "call_in_cell": 1, "question_ids": ["q"], "prompt": "{}", "prompt_sha256": _digest("{}")}
    root, started, terminal = executor._attempt_paths(tmp_path, 1)
    executor._immutable(started, executor._start(item))
    response = json.dumps([{"question_id": "q", "verdict": "YES", "confidence": 0.8}]); receipt = {"provider": "openai", "model": executor.MODEL, "reasoning_effort": executor.REASONING, "session_id": "session"}; session = _digest("session")
    executor._immutable(terminal, {"format_version": 1, "status": "succeeded", "sequence": 1, "session_id_sha256": session, "receipt": receipt, "response": response, "response_sha256": _digest(response), "verdicts": json.loads(response)})
    replayed = executor._validate_existing(item, started, terminal, set())
    assert replayed["session_id_sha256"] == session
    bad = json.loads(terminal.read_text(encoding="utf-8")); bad["response_sha256"] = _digest("tampered"); terminal.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RuntimeError, match="existing terminal is invalid"):
        executor._validate_existing(item, started, terminal, set())
    with pytest.raises(RuntimeError, match="bound schema"):
        executor._terminal(item, {"receipt": receipt, "response": "[]"}, set())
    with pytest.raises(RuntimeError, match="required Codex route"):
        executor._terminal(item, {"receipt": {**receipt, "reasoning_effort": "low"}, "response": response}, set())
    duplicate = '[{"question_id":"wrong","question_id":"q","verdict":"NO","verdict":"YES","confidence":0.8}]'
    with pytest.raises(ValueError, match="duplicate object keys"):
        executor.study.validate_response(["q"], duplicate)
    with pytest.raises(RuntimeError, match="bound schema"):
        executor._terminal(item, {"receipt": receipt, "response": duplicate}, set())


def test_persisted_reused_matrix_is_a_198_session_hard_gate(tmp_path, monkeypatch):
    study = _load("hanna_expansion_reused_matrix", "study.py")
    work, private, plan, _ = _prepared(study, tmp_path, monkeypatch)
    matrix_path = private / study.REUSED_MATRIX_NAME
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert matrix["session_count"] == 198 and len(matrix["session_commitments"]) == 198 and len(matrix["cells"]) == 12
    matrix["session_commitments"][1] = matrix["session_commitments"][0]
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    with pytest.raises(ValueError, match="persisted reused-matrix binding"):
        study.load_plan(work)


def test_executor_rejects_private_root_substitution_and_freezes_duplicate_response(tmp_path, monkeypatch):
    study = _load("hanna_expansion_private_root", "study.py")
    work, private, _, _ = _prepared(study, tmp_path, monkeypatch)
    executor = _load("hanna_expansion_private_root_executor", "run_expansion.py")
    monkeypatch.setattr(executor, "schedule", lambda _plan: [])
    with pytest.raises(RuntimeError, match="does not match"):
        executor.prepare_execution(work, tmp_path / "substituted-private")
    item = {"sequence": 1, "story_id": "hanna-178", "condition_id": "single_positive_batch1", "repetition": 1, "latin_row": "L1", "call_in_cell": 1, "question_ids": ["q"], "prompt": "{}", "prompt_sha256": _digest("{}")}
    receipt = {"provider": "openai", "model": executor.MODEL, "reasoning_effort": executor.REASONING, "session_id": "duplicate-session"}
    monkeypatch.setattr(executor, "prepare_execution", lambda *_args, **_kwargs: {"status": "prepared_no_provider_contact"})
    monkeypatch.setattr(executor, "schedule", lambda _plan: [item])
    duplicate = '[{"question_id":"wrong","question_id":"q","verdict":"NO","verdict":"YES","confidence":0.8}]'
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute(work, private, lambda _item: {"receipt": receipt, "response": duplicate})
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "provider_or_response_failure"
