from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-treatment-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("s1_free_verse_execution_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def find_leaf(node: object, leaf_id: str) -> dict[str, object] | None:
    if isinstance(node, dict):
        if node.get("id") == leaf_id:
            return node
        for value in node.values():
            found = find_leaf(value, leaf_id)
            if found is not None:
                return found
    if isinstance(node, list):
        for value in node:
            found = find_leaf(value, leaf_id)
            if found is not None:
                return found
    return None


@pytest.fixture
def private_controller(tmp_path: Path, monkeypatch):
    s = study()
    root = tmp_path / "private-controller"
    root.mkdir()
    fixtures = [
        {"fixture_id": f"fixture-{index}", "role": "target" if index == 1 else "control", "expected_verdict": verdict,
         "declared_scope": "excerpt", "completion_status": "excerpt", "contexts": [f"context-{index}"], "text": f"fixture text {index}"}
        for index, verdict in enumerate(("NO", "YES", "CANNOT_ASSESS", "NOT_APPLICABLE"), start=1)
    ]
    controller = {
        "study_id": "hbq-poetry-free-verse-repetition-treatment-v1", "format_version": 3,
        "visibility": "private_controller_only",
        "provider_execution": {"permitted_now": False, "provider_calls_made_exact": 0, "planned_calls_exact": 24,
                               "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high",
                               "zero_paid_route_required": True, "semantic_retries_permitted": False,
                               "one_leaf_per_request": True},
        "fixture_matrix": fixtures,
    }
    ledger = {"study_id": controller["study_id"], "format_version": 3, "visibility": "private_controller_only",
              "slot_mapping": [{"opaque_slot_id": f"opaque-{index:02d}", "fixture_id": fixture["fixture_id"], "arm": arm, "repeat": repeat}
                               for index, (fixture, arm, repeat) in enumerate(((fixture, arm, repeat) for fixture in fixtures for arm in ("current", "candidate") for repeat in (1, 2, 3)), start=1)]}
    controller_bytes, ledger_bytes = canonical(controller), canonical(ledger)
    (root / "private-controller.json").write_bytes(controller_bytes)
    (root / "private-ledger.json").write_bytes(ledger_bytes)
    verifier = root / "verify_private_freeze.py"
    verifier.write_text(
        "import json,sys\nrecords=json.load(open(sys.argv[2], encoding='utf-8'))\n"
        "assert len(records)==24\nassert all(set(r)=={'opaque_slot_id','terminal_lifecycle','accepted','verdict','receipt_sha256'} for r in records)\n"
        "print(json.dumps({'decision':'HOLDOUT_ELIGIBLE_ON_SUCCESS','candidate_target_matches':3,'candidate_control_matches':9,'current_target_matches':2}))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(s, "PRIVATE_CONTROLLER_ROOT", root)
    monkeypatch.setattr(s, "CONTROLLER_SHA256", hashlib.sha256(controller_bytes).hexdigest())
    monkeypatch.setattr(s, "LEDGER_SHA256", hashlib.sha256(ledger_bytes).hexdigest())
    monkeypatch.setattr(s, "VERIFIER_SHA256", hashlib.sha256(verifier.read_bytes()).hexdigest())
    return s, root / s.PRIVATE_EXECUTION_DIRECTORY


def fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        registry = Path(command[command.index("--registry") + 1])
        leaf = find_leaf(json.loads(registry.read_text(encoding="utf-8")), "form.poetry.free_verse.repetition")
        assert leaf is not None
        return SimpleNamespace(returncode=0, stdout=("frozen prompt\n" + str(leaf["text"]) + "\n").encode("utf-8"), stderr=b"")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def record(slot, *, correct=True):
    verdict = slot["expected_verdict"] if correct else "YES"
    return {"opaque_slot_id": slot["opaque_slot_id"], "terminal_lifecycle": "accepted_no_semantic_retry", "accepted": True,
            "verdict": verdict, "receipt_sha256": hashlib.sha256(str(slot["opaque_slot_id"]).encode("utf-8")).hexdigest()}


def test_exact_predecessor_private_r3_binding_and_24_slot_geometry(private_controller):
    s, _root = private_controller
    validated = s.validate_package()
    schedule = s.build_schedule()
    assert validated["slots"] == 24 and validated["provider_calls"] == 0
    assert len(schedule) == len({slot["opaque_slot_id"] for slot in schedule}) == 24
    assert {(slot["arm"], slot["repeat"]) for slot in schedule} == {(arm, repeat) for arm in ("current", "candidate") for repeat in (1, 2, 3)}


def test_v5_quota_reset_is_fresh_zero_byte_lineage_not_a_rubric_vote(private_controller):
    s, root = private_controller
    value = s.contract()["quota_reset_successor"]
    assert s.PRIVATE_EXECUTION_DIRECTORY.endswith("v5-quota-reset-successor-terminal-sidecar-v1")
    assert root.name == s.PRIVATE_EXECUTION_DIRECTORY
    assert value == {
        "version": 5, "successor_parent_head": "637c92befda031529041f61152e9460607349516",
        "private_execution_directory": s.PRIVATE_EXECUTION_DIRECTORY,
        "ancestor_private_execution_directory": s.V4_PRIVATE_EXECUTION_DIRECTORY,
        "ancestor_runtime_head": s.V4_RUNTIME_HEAD,
        "ancestor_terminal": {"classification": "provider_retryable_failure", "response_bytes": 0,
                              "rubric_sample_or_result": "none", "retry": False, "lineage_not_a_vote": True},
        "fresh_namespace_required": True,
        "runtime_callback_policy": "current_frozen_runtime_required_before_render_and_dispatch",
    }
    assert value["ancestor_private_execution_directory"] != value["private_execution_directory"]
    assert s.validate_package()["provider_calls"] == 0


def test_private_verifier_hash_binding_and_exact_five_key_terminal_record(private_controller):
    s, root = private_controller
    records = [record(slot) for slot in s.build_schedule()]
    assert s._derive_gate(root, records)["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    verifier = root.parent / "verify_private_freeze.py"
    verifier.write_text("raise SystemExit(0)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="verifier commitment"):
        s._private_freeze()


def test_private_root_must_be_explicit_and_disjoint_and_public_sources_contain_no_personal_path(private_controller):
    s, _root = private_controller
    with pytest.raises(ValueError, match="outside"):
        s.set_private_root(book_root())
    with pytest.raises(ValueError, match="disjoint"):
        s.set_private_root(book_root().parent)
    assert "C:\\Users\\" not in (ROOT / "study.py").read_text(encoding="utf-8")
    assert "C:\\Users\\" not in (ROOT / "study-contract.json").read_text(encoding="utf-8")


def test_dry_run_is_provider_free_and_pairwise_prompt_delta_is_only_candidate_wording(private_controller):
    s, root = private_controller
    result = s.dry_run(runner_call=fake_cwr)
    assert result["provider_calls"] == 0 and result["rendered_prompts"] == 24 and result["prompt_pair_checks"] == 12
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert disclosure["planned_provider_sends"] == 24
    assert disclosure["attempt_lifecycle_policy"] == "terminal_sidecar_v1"
    assert disclosure["paid_api_or_fallback_route"] == "forbidden"
    schedule = s.build_schedule()
    current = next(slot for slot in schedule if slot["arm"] == "current" and slot["repeat"] == 1)
    candidate = next(slot for slot in schedule if slot["fixture_id"] == current["fixture_id"] and slot["arm"] == "candidate" and slot["repeat"] == 1)
    assert s._artifact_path(root, current) == s._artifact_path(root, candidate)
    assert s._task_path(root, current) == s._task_path(root, candidate)
    assert "current" not in s._artifact_path(root, current).name and "candidate" not in s._task_path(root, candidate).name


def test_live_command_has_allow_remote_only_for_the_live_judge(private_controller):
    s, _root = private_controller
    slot = s.build_schedule()[0]
    rendered, live = s._command(slot, render=True), s._command(slot, render=False)
    assert "--allow-remote" not in rendered
    assert live[live.index("--allow-remote") - 1] == "terminal_sidecar_v1"


def test_inherited_codex_argv_disables_unbounded_connection_retries(private_controller, monkeypatch, tmp_path: Path):
    s, _root = private_controller
    seen = []

    def rejected(argv, **_kwargs):
        seen.append(argv)
        return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: configuration rejection")

    monkeypatch.setattr(s.runner.subprocess, "run", rejected)
    with pytest.raises(s.runner._ProviderAttemptFailure, match="configuration rejection"):
        s.runner._call_codex(
            executable="codex", model="gpt-5.6-sol", reasoning="high", prompt="synthetic",
            output_dir=tmp_path, response_schema=book_root() / "schema" / "hbq_judge_response.schema.json",
            batch_number=1, timeout=1.0,
        )
    argv = seen[0]
    index = argv.index("unbounded_connection_retries")
    assert argv[index - 1] == "--disable"


def test_missing_remote_flag_stops_before_provider_callback_or_run(private_controller, monkeypatch):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    slot = s.build_schedule()[0]
    callbacks = []
    monkeypatch.setattr(s.runner, "_call_codex", lambda *_args, **_kwargs: callbacks.append(True))
    with pytest.raises(s.runner.HBQError, match="pass --allow-remote"):
        s.runner.run_judge(
            artifact_path=s._artifact_path(root, slot), bundle_id=s.BUNDLE_ID, provider="codex", model="gpt-5.6-sol",
            output_dir=root / "runs" / str(slot["opaque_slot_id"]), registry=s._registry_path(root, slot["arm"]),
            bundles=root / "catalog" / "bundles.json", context_paths=s._context_paths(root, slot),
            task_contract_path=s._task_path(root, slot), scope_compatibility_override_path=s._override_path(root, slot),
            question_ids=[s.LEAF_ID], batch_size=1, batch_attempts=1, reasoning="high", strict_ai=True,
            artifact_id=slot["fixture_id"], attempt_lifecycle_policy=s.ATTEMPT_LIFECYCLE_POLICY,
        )
    assert callbacks == []
    assert not (root / "runs" / str(slot["opaque_slot_id"])).exists()


def test_execute_is_singleton_no_resume_and_requires_frozen_disclosure(private_controller):
    s, root = private_controller
    with pytest.raises(ValueError, match="requires"):
        s.execute(runner_call=fake_cwr)
    s.dry_run(runner_call=fake_cwr)
    seen = []

    def spy(command, **kwargs):
        seen.append(command)
        return fake_cwr(command, **kwargs)

    result = s.execute(acknowledged_zero_incremental_charge=True, runner_call=spy)
    assert result == {"study_id": s.STUDY_ID, "provider_calls": 24, "semantic_retries": 0, "resume": "forbidden"}
    provider_commands = [command for command in seen if "judge" in command]
    assert len(provider_commands) == 24
    assert all("--resume" not in command and command[command.index("--batch-attempts") + 1] == "1" for command in provider_commands)
    assert all(command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1" for command in provider_commands)
    assert (root / "receipts" / "zero-charge-acknowledgement.v1.json").is_file()
    assert len(list((root / "dispatches").glob("*.start.v1.json"))) == 24
    assert len(list((root / "dispatches").glob("*.settled.v1.json"))) == 24


def test_execute_rejects_generated_input_or_rendered_prompt_drift_before_contact(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    schedule = s.build_schedule()
    first = schedule[0]
    s._artifact_path(root, first).write_text("mutated after dry run", encoding="utf-8")
    seen = []
    with pytest.raises(ValueError, match="drifted"):
        s.execute(acknowledged_zero_incremental_charge=True, runner_call=lambda command, **kwargs: seen.append(command) or fake_cwr(command, **kwargs))
    assert seen == []


def test_execute_rejects_immediate_prerender_drift_before_dispatch(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    seen = []

    def changed_render(command, **_kwargs):
        seen.append(command)
        if "render-judge" in command:
            return SimpleNamespace(returncode=0, stdout=b"different prompt\n", stderr=b"")
        raise AssertionError("provider judge must not run after a prompt-drift detection")

    with pytest.raises(ValueError, match="Rendered provider prompt drifted"):
        s.execute(acknowledged_zero_incremental_charge=True, runner_call=changed_render)
    assert len(seen) == 1 and "render-judge" in seen[0]
    assert not (root / "dispatches").exists()


def test_execute_rechecks_frozen_runtime_after_render_before_provider_callback(private_controller, monkeypatch):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    original_bindings = s._runtime_bindings
    drift = {"active": False}

    def runtime_bindings():
        bindings = original_bindings()
        return {**bindings, "runtime_head": "0" * 64} if drift["active"] else bindings

    monkeypatch.setattr(s, "_runtime_bindings", runtime_bindings)
    calls = []

    def changes_runtime_after_render(command, **kwargs):
        calls.append(command)
        if "render-judge" in command:
            drift["active"] = True
            return fake_cwr(command, **kwargs)
        raise AssertionError("runtime drift must stop before a provider callback")

    with pytest.raises(ValueError, match="runtime manifest drifted before dispatch"):
        s.execute(acknowledged_zero_incremental_charge=True, runner_call=changes_runtime_after_render)
    assert len(calls) == 1 and "render-judge" in calls[0]
    assert not (root / "dispatches").exists()


def test_existing_atomic_claim_stops_contention_before_any_callback(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    s._claim_execution(root, s._runtime_schedule())
    callbacks = []
    with pytest.raises(ValueError, match="Execution claim already exists"):
        s.execute(acknowledged_zero_incremental_charge=True, runner_call=lambda *args, **kwargs: callbacks.append(args))
    assert callbacks == []


def test_claimed_root_rejects_prepare_and_dry_run_without_rewriting_manifest(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    manifest = (root / "study-manifest.json").read_bytes()
    s._claim_execution(root, s._runtime_schedule())
    with pytest.raises(ValueError, match="claimed root"):
        s.prepare()
    with pytest.raises(ValueError, match="claimed root"):
        s.dry_run(runner_call=lambda *_args, **_kwargs: pytest.fail("claimed dry run must not render"))
    assert (root / "study-manifest.json").read_bytes() == manifest


def test_later_slot_state_stops_before_claim_or_any_callback(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    later = s.build_schedule()[-1]
    (root / "dispatches").mkdir(parents=True)
    (root / "dispatches" / f"{later['opaque_slot_id']}.failure.v1.json").write_text("{}", encoding="utf-8")
    callbacks = []
    with pytest.raises(ValueError, match="fresh private root"):
        s.execute(acknowledged_zero_incremental_charge=True, runner_call=lambda *args, **kwargs: callbacks.append(args))
    assert callbacks == []
    assert not (root / s.EXECUTION_CLAIM_NAME).exists()


def test_precontact_nonzero_writes_hashed_definitely_not_contacted_failure_receipt(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)

    def precontact_failure(command, **kwargs):
        if "render-judge" in command:
            return fake_cwr(command, **kwargs)
        return SimpleNamespace(returncode=2, stdout="non-secret diagnostic", stderr="review the disclosure and pass --allow-remote")

    with pytest.raises(ValueError, match="definitely_not_contacted_precontact_remote_disclosure_gate"):
        s.execute(acknowledged_zero_incremental_charge=True, runner_call=precontact_failure)
    failure = next((root / "dispatches").glob("*.failure.v1.json"))
    receipt = json.loads(failure.read_text(encoding="utf-8"))
    assert receipt["contact_classification"] == "definitely_not_contacted_precontact_remote_disclosure_gate"
    assert receipt["run_directory_present"] is False
    assert receipt["stdout"]["sha256"] == hashlib.sha256(b"non-secret diagnostic").hexdigest()
    assert receipt["stderr"]["sha256"] == hashlib.sha256(b"review the disclosure and pass --allow-remote").hexdigest()
    assert not (root / "runs").exists()


def test_private_verifier_rejects_noncanonical_terminal_record_shape(private_controller):
    s, root = private_controller
    malformed = record(s.build_schedule()[0])
    malformed["unexpected"] = True
    with pytest.raises(ValueError, match="terminal-record verifier"):
        s._derive_gate(root, [malformed] * 24)


def test_settlement_is_write_once_and_public_result_is_aggregate_only(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    s._claim_execution(root, s._runtime_schedule())
    s._write_zero_charge_acknowledgement()
    result = s.settle(verifier=lambda _root, slot: record(slot))
    assert result["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    public = json.loads((root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    assert public == {"study_id": s.STUDY_ID, "decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "completed_slots": 24, "planned_slots": 24,
                      "aggregate": {"candidate_target_matches": 3, "candidate_control_matches": 9, "current_target_matches": 2}, "promotion": "none"}
    sidecar = json.loads((root / "terminal-sidecar.v1.json").read_text(encoding="utf-8"))
    assert sidecar["format"] == "terminal_sidecar_v1" and sidecar["promotion"] == "none"
    assert result["execution_claim_sha256"] == hashlib.sha256((root / s.EXECUTION_CLAIM_NAME).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="write-once"):
        s.settle(verifier=lambda _root, slot: record(slot))


def test_settlement_rejects_missing_or_drifted_execution_claim(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    s._write_zero_charge_acknowledgement()
    with pytest.raises(ValueError, match="Execution claim is unavailable or drifted"):
        s.settle(verifier=lambda _root, slot: record(slot))
    claim = s._claim_execution(root, s._runtime_schedule())
    claim.write_bytes(b"{}")
    with pytest.raises(ValueError, match="Execution claim is unavailable or drifted"):
        s.settle(verifier=lambda _root, slot: record(slot))


def test_cli_requires_private_root_and_never_offers_resume():
    completed = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], capture_output=True, text=True, check=False)
    assert completed.returncode == 2
    assert "--private-root" in completed.stderr
    assert "--resume" not in (ROOT / "run.py").read_text(encoding="utf-8")
