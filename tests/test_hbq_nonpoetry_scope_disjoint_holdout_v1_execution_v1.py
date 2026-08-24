from __future__ import annotations

import hashlib
import gzip
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-disjoint-holdout-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_disjoint_execution_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def private_controller(tmp_path: Path, monkeypatch):
    s = study()
    root = tmp_path / "private-controller"
    root.mkdir()
    source = next(json.loads(line) for line in (book_root() / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(line)["id"] == s.LEAF_ID)
    states = ("localized_issue", "localized_issue", "material_failure", "material_failure", "missing_required_evidence", "missing_required_evidence", "activation_mismatch", "activation_mismatch")
    verdicts = {"localized_issue": "YES", "material_failure": "NO", "missing_required_evidence": "CANNOT_ASSESS", "activation_mismatch": "NOT_APPLICABLE"}
    fixtures = [{"fixture_id": f"s2dh-f{i:02d}", "artifact_kind": "memo" if i < 7 else "inventory", "declared_scope": "excerpt" if i < 7 else "metadata", "structure_id": f"structure-{i}", "subject_key": f"subject-{i}", "source_id": f"pg-{i}" if i < 7 else None, "source_excerpt": f"public excerpt {i}" if i < 7 else None, "evaluation_record": f"evaluation record {i}", "contexts": [f"context {i}"]} for i in range(1, 9)]
    ledger = [{"fixture_id": row["fixture_id"], "state": state, "expected_verdict": verdicts[state], "gate_role": "target" if state in {"material_failure", "missing_required_evidence"} else "control", "rationale": "sealed"} for row, state in zip(fixtures, states, strict=True)]
    sources = [{"source_id": f"pg-{i}", "title": f"title-{i}", "author": f"author-{i}", "original_publication_year": 1800 + i, "landing_url": f"https://www.gutenberg.org/ebooks/{i}", "content_url": f"https://www.gutenberg.org/cache/epub/{i}/x.html", "content_locator": {"line_start": i}, "copyright_status": "Public domain in the USA.", "excerpt": f"public excerpt {i}", "excerpt_sha256": hashlib.sha256(f"public excerpt {i}".encode()).hexdigest()} for i in range(1, 7)]
    file_hashes = {
        "fixtures.v1.json": _write_json(root / "fixtures.v1.json", {"fixtures": fixtures}),
        "expected-ledger.v1.json": _write_json(root / "expected-ledger.v1.json", {"rows": ledger}),
        "source-manifest.v1.json": _write_json(root / "source-manifest.v1.json", {"sources": sources}),
        "private-schedule.v1.json": _write_json(root / "private-schedule.v1.json", {"slots_exact": 48}),
    }
    controller = {"format_version": 1, "study_id": s.PREDECESSOR_ID, "status": "frozen_private_provider_free_holdout", "provider_execution": {"permitted_now": False, "provider_calls_made_exact": 0, "future_route": "codex", "future_model": "gpt-5.6-sol", "future_reasoning": "high", "planned_slots_exact": 48, "one_leaf_per_request": True, "post_response_retries_permitted": False, "paid_or_fallback_route": "forbidden"}, "questions": {"leaf_id": s.LEAF_ID, "baseline_text": source["text"], "candidate_text": "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?", "arm_delta": "p4_question_text_only"}, "file_bindings": file_hashes, "fixture_commitments_sha256": [hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for row in fixtures], "source_record_commitments_sha256": [hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for row in sources]}
    controller_hash = _write_json(root / "controller-contract.v1.json", controller)
    monkeypatch.setattr(s, "PRIVATE_FILES", file_hashes)
    monkeypatch.setattr(s, "PRIVATE_CONTROLLER_SHA256", controller_hash)
    monkeypatch.setattr(s, "PRIVATE_EXECUTION_DIRECTORY", "execution-test-v1")
    monkeypatch.setattr(s, "PRIVATE_CONTROLLER_ROOT", root.resolve())
    public_contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    public_contract["private_controller"]["contract_sha256"] = controller_hash
    monkeypatch.setattr(s, "contract", lambda: public_contract)
    return s, root / s.PRIVATE_EXECUTION_DIRECTORY


def fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        registry = Path(command[command.index("--registry") + 1])
        modules = json.loads(registry.read_text(encoding="utf-8"))
        def find(value):
            if isinstance(value, dict):
                if value.get("id") == "scope.passage.status": return value
                return next((found for child in value.values() if (found := find(child))), None)
            if isinstance(value, list): return next((found for child in value if (found := find(child))), None)
            return None
        return SimpleNamespace(returncode=0, stdout=("prefix\r\n" + find(modules)["text"] + "\r\n").encode(), stderr=b"")
    if "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        registry = Path(command[command.index("--registry") + 1]).read_bytes()
        config = {"compiled_bundle_sha256": hashlib.sha256(registry).hexdigest(), "questions_sha256": hashlib.sha256(registry + b"questions").hexdigest()}
        (output / "run.json").write_text(json.dumps({"format_version": 5, "configuration": config}), encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def record(slot, verdict):
    ordinal = int(hashlib.sha256(slot["slot_id"].encode()).hexdigest()[:12], 16)
    return {"slot_id": slot["slot_id"], "arm": slot["arm"], "fixture_id": slot["fixture_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdict, "run_id": f"run-{ordinal}", "session_id_sha256": f"{ordinal:064x}", "checkpoint_chain_head_sha256": f"{ordinal + 1:064x}", "accepted_provider_call_count": 1, "rejected_retry_count": 0, "batch_attempt_count": 1}


def test_exact_48_singleton_geometry_and_command_surface(private_controller):
    s, _ = private_controller
    schedule = s.build_schedule()
    assert len(schedule) == len({row["slot_id"] for row in schedule}) == 48
    assert sum(row["arm"] == "baseline" for row in schedule) == 24
    assert sum(row["arm"] == "candidate" for row in schedule) == 24
    assert len({row["fixture_id"] for row in schedule}) == 8
    for row in schedule:
        command = s._command(row)
        assert command[command.index("--provider") + 1] == "codex"
        assert command[command.index("--model") + 1] == "gpt-5.6-sol"
        assert command[command.index("--reasoning") + 1] == "high"
        assert command[command.index("--batch-size") + 1] == "1"
        assert command[command.index("--batch-attempts") + 1] == "1"
        assert command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"
        assert command.count("--question-id") == 1 and "--allow-remote" not in command
    runner_source = (book_root() / "src" / "hbqrs" / "runner.py").read_text(encoding="utf-8")
    assert '"--disable",\n        "unbounded_connection_retries"' in runner_source
    assert 'approval_policy="never"' in runner_source


def test_prepare_dry_and_live_do_not_open_sealed_ledger(private_controller, monkeypatch):
    s, root = private_controller
    original = s._private_file
    def guarded(name):
        if name == "expected-ledger.v1.json": raise AssertionError("labels opened early")
        return original(name)
    monkeypatch.setattr(s, "_private_file", guarded)
    s.dry_run(runner_call=fake_cwr)
    calls = []
    def live(command, **kwargs): calls.append(command); return fake_cwr(command, **kwargs)
    result = s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=live, verifier=lambda _root, slot: record(slot, "YES"))
    assert result["inspected_slots"] == 48 and len(calls) == 48
    assert all("--allow-remote" in command and "--resume" in command for command in calls)
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    forbidden = ("expected", "state", "gate_role", "rationale", "title", "author", "ebook", "locator", "copyright")
    serialized = json.dumps(disclosure).casefold()
    assert not any(token in serialized for token in forbidden)


def test_pairwise_prompts_differ_only_in_p4_wording(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    questions = s._questions()
    for fixture in {row["fixture_id"] for row in s.build_schedule()}:
        for repeat in s.REPEATS:
            baseline = root / "rendered-prompts" / f"s2dhexec-v1-{fixture}-baseline-r{repeat}.txt"
            candidate = root / "rendered-prompts" / f"s2dhexec-v1-{fixture}-candidate-r{repeat}.txt"
            assert b"\r" not in baseline.read_bytes() + candidate.read_bytes()
            assert baseline.read_text(encoding="utf-8").replace(questions["baseline"]["text"], questions["candidate"]["text"]) == candidate.read_text(encoding="utf-8")


def test_format5_receipt_binds_compiled_identity_without_registry_field(private_controller, monkeypatch):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    slot = s._validated_runtime_schedule()[0]
    artifact, task, override = s._slot_paths(root, slot)
    contexts = s._context_paths(root, slot)
    config = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 1}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": s.ATTEMPT_LIFECYCLE_POLICY, "artifact_id": slot["fixture_id"], "bundle_id": s.BUNDLE_ID, "question_ids": [s.LEAF_ID], "compiled_bundle_sha256": slot["compiled_bundle_sha256"], "questions_sha256": slot["questions_sha256"], "artifact": s._input_record(artifact), "contexts": [s._input_record(path) for path in contexts], "task_contract": {"sha256": s.sha256_file(task)}, "scope_compatibility": {"sha256": s.sha256_file(override)}}
    assert "registry" not in config
    run_id = "20260823T000000Z-" + s.runner._sha256_bytes(s.runner._json_bytes(config))[:10]
    run = root / "runs" / slot["slot_id"]
    (run / "responses").mkdir(parents=True, exist_ok=True)
    (run / "run.json").write_text(json.dumps({"format_version": 5, "run_id": run_id, "configuration": config, "config_sha256": s.runner._sha256_bytes(s.runner._json_bytes(config))}), encoding="utf-8")
    prompt = (root / "rendered-prompts" / f"{slot['slot_id']}.txt").read_bytes()
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt))
    (run / "responses" / "batch-0001.json").write_text(json.dumps({"provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "session-format5"}}}), encoding="utf-8")
    monkeypatch.setattr(s.runner, "_validate_or_reconstruct_attempt_lifecycle", lambda *args, **kwargs: None)
    monkeypatch.setattr(s.runner, "_load_checkpoints", lambda *args, **kwargs: ([{"question_id": s.LEAF_ID, "verdict": "YES", "run_id": run_id}], 1, "a" * 64))
    monkeypatch.setattr(s.runner, "_rejected_records", lambda *args, **kwargs: [])
    record_value = s._verify_slot(root, slot)
    assert record_value["accepted_provider_call_count"] == 1 and record_value["rejected_retry_count"] == 0


def test_nonzero_terminalizes_and_stops_later_slots(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    calls = []
    def fail(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7, stdout="", stderr="ambiguous transport")
    with pytest.raises(RuntimeError):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fail)
    assert len(calls) == 1
    terminal = json.loads((root / "execution-terminal.v1.json").read_text(encoding="utf-8"))
    assert terminal["phase"] == "terminal_nonzero" and terminal["later_slots_started"] is False
    second_calls = []
    def forbidden_second(command, **kwargs): second_calls.append(command); return fake_cwr(command, **kwargs)
    with pytest.raises(ValueError, match="already claimed"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=forbidden_second)
    assert second_calls == []
    claim = json.loads((root / "execution-claim.v1" / "claim.json").read_text(encoding="utf-8"))
    assert claim["retention"] == "preserve_on_crash_terminal_and_settlement"


def test_invalid_or_duplicate_accepted_receipt_stops_later_slots(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    calls = []
    def live(command, **kwargs): calls.append(command); return fake_cwr(command, **kwargs)
    with pytest.raises(RuntimeError, match="receipt rejected"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=live, verifier=lambda _root, _slot: {})
    assert len(calls) == 1
    terminal = json.loads((root / "execution-terminal.v1.json").read_text(encoding="utf-8"))
    assert terminal["phase"] == "terminal_invalid_receipt" and terminal["later_slots_started"] is False


@pytest.mark.parametrize("case,expected_calls", [("retry", 1), ("duplicate_session", 2)])
def test_retry_or_duplicate_session_terminalizes(private_controller, case, expected_calls):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    calls = []
    def live(command, **kwargs): calls.append(command); return fake_cwr(command, **kwargs)
    def invalid(_root, slot):
        value = record(slot, "YES")
        if case == "retry":
            value["rejected_retry_count"] = 1
        else:
            value["session_id_sha256"] = "f" * 64
        return value
    with pytest.raises(RuntimeError, match="receipt rejected"):
        s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=live, verifier=invalid)
    assert len(calls) == expected_calls
    assert json.loads((root / "execution-terminal.v1.json").read_text(encoding="utf-8"))["phase"] == "terminal_invalid_receipt"


def test_settlement_uses_sealed_labels_and_emits_aggregate_only(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr, verifier=lambda _root, slot: record(slot, "YES"))
    ledger = {row["fixture_id"]: row for row in s._private_file("expected-ledger.v1.json")["rows"]}
    result = s.settle(verifier=lambda _root, slot: record(slot, ledger[slot["fixture_id"]]["expected_verdict"] if slot["arm"] == "candidate" or ledger[slot["fixture_id"]]["gate_role"] == "control" else "YES"))
    assert result["decision"] == "PROMOTION_REVIEW_ELIGIBLE"
    public = json.loads((root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    assert public["decision"] == "PROMOTION_REVIEW_ELIGIBLE" and public["promotion"] == "none"
    assert "records" not in public and "fixture" not in json.dumps(public).casefold()
    assert public["execution_claim_sha256"] == s.sha256_bytes(s.canonical_json(s._execution_claim_payload()))


def test_settlement_requires_the_exact_atomic_execution_claim(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    result = s.settle(verifier=lambda _root, slot: record(slot, "YES"))
    assert result["decision"] == "INCOMPLETE"
    assert "execution claim" in result["failures"][0]["reason"]
    assert not (root / "execution-claim.v1").exists()


@pytest.mark.parametrize("scenario,expected_decision", [("no_effect", "NO_EFFECT"), ("candidate_mismatch", "NO_GO")])
def test_settlement_receipt_matrix_covers_no_effect_and_no_go(private_controller, scenario, expected_decision):
    s, _root = private_controller
    s.dry_run(runner_call=fake_cwr)
    s.execute(allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr, verifier=lambda _root, slot: record(slot, "YES"))
    ledger = {row["fixture_id"]: row for row in s._private_file("expected-ledger.v1.json")["rows"]}
    def verdict(slot):
        value = ledger[slot["fixture_id"]]["expected_verdict"]
        if scenario == "candidate_mismatch" and slot["arm"] == "candidate" and slot["fixture_id"] == "s2dh-f03":
            return "YES"
        return value
    result = s.settle(verifier=lambda _root, slot: record(slot, verdict(slot)))
    assert result["decision"] == expected_decision


def test_cli_requires_explicit_root_and_live_acknowledgements():
    done = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], capture_output=True, text=True, check=False)
    assert done.returncode == 2 and "--private-root" in done.stderr
    source = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "--allow-remote" in source and "--acknowledge-zero-incremental-charge" in source and "--resume" not in source
