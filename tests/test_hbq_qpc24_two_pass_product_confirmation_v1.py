from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]
PUBLIC = REPOSITORY / "evaluation-results" / "hbq-qpc24-two-pass-product-confirmation-v1"
PRIVATE = Path(r"C:\Users\Haile\Documents\cwr-qpc24-two-pass-product-confirmation-v1-4ce1204-20260825")


ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived QPC24 two-pass v1 controller mechanics require the frozen 4ce1204 runtime; current bindings have advanced."
)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public():
    return _module(PUBLIC / "study.py", "qpc24_two_pass_public")


def _private():
    return _module(PRIVATE / "freeze.py", "qpc24_two_pass_private")


def _live():
    if str(PRIVATE) not in sys.path:
        sys.path.insert(0, str(PRIVATE))
    return _module(PRIVATE / "live_controller.py", "qpc24_two_pass_live_controller")


def _driver():
    if str(PRIVATE) not in sys.path:
        sys.path.insert(0, str(PRIVATE))
    return _module(PRIVATE / "live_driver.py", "qpc24_two_pass_live_driver")


def _clear_api_environment(monkeypatch: pytest.MonkeyPatch, live) -> None:
    for name in live.API_ENVIRONMENT_KEYS:
        monkeypatch.delenv(name, raising=False)


def test_current_head_fails_closed_while_public_plan_geometry_remains_exact() -> None:
    public = _public()
    contract = public.contract()
    assert contract["source_head"] == public.HEAD == "4ce1204d8dd97feff2c7bd88237e265fac742adb"
    assert contract["execution"]["provider_free_now"] is True
    assert contract["execution"]["remote_provider_call_count_now"] == 0
    assert contract["execution"]["dispatch_surface"] == "absent"
    assert contract["execution"]["future_execution"] == "requires_independent_review"
    geometry = contract["geometry"]
    assert geometry["artifact_roles"] == list(public.ROLE_ORDER)
    assert geometry["complete_eligible_question_count"] == 221
    assert geometry["questions_per_provider_call"] == 24
    assert geometry["full_batches_per_pass"] == 9
    assert geometry["final_remainder_questions"] == 5
    assert geometry["calls_per_pass"] == 10
    assert geometry["target_voting_calls"] == 60
    assert geometry["target_voting_positions"] == 1326
    assert geometry["maximum_unique_contacts"] == 90
    assert geometry["target_voting_calls"] // geometry["calls_per_pass"] == 6
    assert contract["fidelity"]["per_selected_pass"] == "full_prose.novel_221_leaves_in_9x24_plus_5"
    assert contract["fidelity"]["two_pass_effect"] == "reduces_repeatability_evidence_only"
    assert contract["fidelity"]["historical_five_repeat_plan"] == "retained_as_extended_validation_path_not_replaced"
    assert contract["non_claims"]["runtime_default"] == "none"
    assert contract["non_claims"]["new_evaluation_mode"] == "none"
    assert contract["non_claims"]["replacement_of_five_repeat_validation"] == "none"
    assert public.verify_question_geometry() == 221
    with pytest.raises(ValueError, match="QPC24 two-pass freeze requires exact source HEAD 4ce1204"):
        public.verify_exact_head_and_bindings()


@ARCHIVED_OLD_RUNTIME
def test_private_selection_is_untouched_and_has_complete_pass_geometry() -> None:
    private = _private()
    freeze = private.verify_freeze()
    slots = freeze["slots"]
    primary = [slot for slot in slots if slot["kind"] == "primary"]
    reserve = [slot for slot in slots if slot["kind"] == "reserve"]
    assert len(primary) == 60
    assert len(reserve) == 30
    assert sum(slot["question_count"] for slot in primary) == 1326
    assert {slot["base_request_index"] for slot in slots}.isdisjoint(range(1, 14))
    assert {slot["base_request_index"] for slot in slots} == set(range(21, 81)) | set(range(101, 131))
    for role, repetitions in private.PRIMARY_REPETITIONS.items():
        assert sorted({slot["repetition"] for slot in primary if slot["role"] == role}) == list(repetitions)
        assert [slot["question_count"] for slot in primary if slot["role"] == role and slot["repetition"] == repetitions[0]] == [24] * 9 + [5]
        assert len([slot for slot in primary if slot["role"] == role]) == 20
        assert len([slot for slot in reserve if slot["role"] == role]) == 10
    assert private.RESERVE_REPETITIONS == {"author_original": 5, "gpt_5_6_pro_rewrite": 3, "public_control_story": 3}
    assert freeze["historical_contact_ledger"]["contacted_request_indexes"] == list(range(1, 14))
    assert freeze["fidelity"]["runtime_or_default_change"] == "none"


@ARCHIVED_OLD_RUNTIME
def test_claim_without_terminal_is_consumed_after_restart(tmp_path: Path) -> None:
    private = _private()
    first = private.claim_next(tmp_path)
    assert first is not None
    assert first["slot_id"] not in {slot["slot_id"] for slot in private.eligible_slots(tmp_path)}
    restarted = _private()
    second = restarted.claim_next(tmp_path)
    assert second is not None and second["slot_id"] != first["slot_id"]
    state = restarted.summary(tmp_path)
    assert state["claimed_slots"] == 2
    assert state["terminal_slots"] == 0
    assert state["claimed_without_terminal_nonvoting"] == 2


@ARCHIVED_OLD_RUNTIME
def test_claim_is_exclusive_and_terminalized_slots_stay_consumed(tmp_path: Path) -> None:
    private = _private()
    first = private.claim_next(tmp_path)
    assert first is not None
    claim_path = tmp_path / "claims" / f"{first['slot_id']}.claim.v1.json"
    with pytest.raises(FileExistsError):
        with claim_path.open("xb") as handle:
            handle.write(b"duplicate")
    with pytest.raises(ValueError, match="receipt"):
        private.terminalize_slot(tmp_path, first["slot_id"], "accepted", "C" * 64)
    private.terminalize_slot(tmp_path, first["slot_id"], "accepted", "c" * 64)
    assert first["slot_id"] not in {slot["slot_id"] for slot in private.eligible_slots(tmp_path)}
    with pytest.raises(ValueError, match="Immutable artifact drift"):
        private.immutable_create(claim_path, {"different": True})


@ARCHIVED_OLD_RUNTIME
def test_reserves_only_replace_one_whole_pass_for_local_transport_ambiguity(tmp_path: Path) -> None:
    private = _private()
    first = private.claim_next(tmp_path)
    assert first is not None and first["slot_id"].startswith("author_original-r3-b")
    private.terminalize_slot(tmp_path, first["slot_id"], "local_transport_ambiguity", "a" * 64)
    activation = private.activate_reserve(tmp_path, "author_original", "author_original-r3", first["slot_id"])
    assert activation["reserve_pass"] == "author_original-r5"
    disqualification = json.loads((tmp_path / "pass-disqualifications" / "author_original-r3.v1.json").read_text(encoding="utf-8"))
    assert len(disqualification["slot_ids"]) == 10
    assert disqualification["decision"] == "WHOLE_PASS_NONVOTING_AFTER_LOCAL_TRANSPORT_AMBIGUITY"
    assert ("author_original", 3) not in private.active_passes(tmp_path)
    assert ("author_original", 5) in private.active_passes(tmp_path)
    assert all(not slot["slot_id"].startswith("author_original-r3-") for slot in private.eligible_slots(tmp_path))
    with pytest.raises(ValueError, match="Only one reserve"):
        private.activate_reserve(tmp_path, "author_original", "author_original-r4", first["slot_id"])


@ARCHIVED_OLD_RUNTIME
def test_substantive_terminal_cannot_activate_reserve(tmp_path: Path) -> None:
    private = _private()
    first = private.claim_next(tmp_path)
    assert first is not None
    private.terminalize_slot(tmp_path, first["slot_id"], "substantive_miss", "b" * 64)
    with pytest.raises(ValueError, match="local transport ambiguity"):
        private.activate_reserve(tmp_path, "author_original", "author_original-r3", first["slot_id"])


@ARCHIVED_OLD_RUNTIME
@pytest.mark.parametrize(
    ("role", "replaced_pass", "reserve_pass"),
    [
        ("author_original", "author_original-r3", "author_original-r5"),
        ("gpt_5_6_pro_rewrite", "gpt_5_6_pro_rewrite-r1", "gpt_5_6_pro_rewrite-r3"),
        ("public_control_story", "public_control_story-r1", "public_control_story-r3"),
    ],
)
def test_each_preregistered_reserve_replaces_only_its_whole_pass(tmp_path: Path, role: str, replaced_pass: str, reserve_pass: str) -> None:
    private = _private()
    target = next(slot for slot in private.eligible_slots(tmp_path) if slot["slot_id"].startswith(replaced_pass + "-b"))
    claimed = None
    while claimed != target["slot_id"]:
        claimed_slot = private.claim_next(tmp_path)
        assert claimed_slot is not None
        claimed = claimed_slot["slot_id"]
    private.terminalize_slot(tmp_path, claimed, "local_transport_ambiguity", "d" * 64)
    private.activate_reserve(tmp_path, role, replaced_pass, claimed)
    remaining = private.eligible_slots(tmp_path)
    assert all(not slot["slot_id"].startswith(replaced_pass + "-b") for slot in remaining)
    assert any(slot["slot_id"].startswith(reserve_pass + "-b") for slot in remaining)


def test_public_projection_has_no_private_root_or_label_data_and_private_freeze_has_no_execution_cli() -> None:
    public_text = "\n".join(path.read_bytes().decode("utf-8", errors="replace") for path in PUBLIC.rglob("*") if path.is_file())
    assert all(path not in public_text for path in (str(PRIVATE), r"C:\Users\Haile\Documents\cwr-qpc24-exact-head-controller-4ce1204-20260825", r"C:\Users\Haile\Documents\cwr-qpc24-live-v4-4ce1204-20260825", r"C:\Users\Haile\Documents\cwr-qpc24-live-v5-execution-4ce1204-20260825"))
    assert all(token not in public_text for token in ('"expected_labels"', '"expected_state"', '"source_path"', '"prompt_sha256"', '"session_id"', '"request_id"'))
    assert all(token not in public_text for token in ('"YES"', '"NO"', '"CANNOT_ASSESS"', '"NOT_APPLICABLE"'))
    private = _private()
    source = inspect.getsource(private)
    assert "def base_executor" not in source
    assert "execute_codex" not in source
    assert "_call_codex" not in source
    assert "subprocess" not in source
    assert "requests." not in source
    assert json.loads((PUBLIC / "study-contract.json").read_text(encoding="utf-8"))["execution"]["dispatch_surface"] == "absent"


@ARCHIVED_OLD_RUNTIME
def test_live_dry_preflight_uses_neutral_root_and_never_contacts_a_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    monkeypatch.setattr(live, "_runner", lambda: (_ for _ in ()).throw(AssertionError("provider path invoked")))
    result = live.dry_preflight(tmp_path / "state", neutral_root=tmp_path / "neutral")
    assert result["provider_calls"] == 0
    assert result["next_slot"] == "author_original-r3-b01"
    assert result["timeout_seconds"] == 7200.0
    assert not (tmp_path / "neutral" / ".git").exists()


@ARCHIVED_OLD_RUNTIME
def test_live_preclaim_rejects_prompt_drift_without_consuming_a_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    private = _private()
    original = live._prepared_requests()
    changed = {index: dict(request) for index, request in original.items()}
    changed[21]["prompt"] = changed[21]["prompt"] + " drift"
    monkeypatch.setattr(live, "_prepared_requests", lambda: changed)
    with pytest.raises(ValueError, match="prompt or input hash drift"):
        live.prepare_next(tmp_path / "state", neutral_root=tmp_path / "neutral")
    assert private.summary(tmp_path / "state")["claimed_slots"] == 0


@ARCHIVED_OLD_RUNTIME
def test_live_wrong_identity_is_rejected_and_simulated_full_run_is_provider_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    prepared = live.prepare_next(tmp_path / "identity-state", neutral_root=tmp_path / "neutral")
    assert prepared is not None
    with pytest.raises(ValueError, match="identity receipt drift"):
        live.validate_envelope(prepared, {"reported": {**live.REPORTED, "model": "wrong"}, "content": "{}"})
    result = live.simulate_full_success(tmp_path / "simulation-state", neutral_root=tmp_path / "simulation-neutral")
    assert result == {"provider_calls": 0, "simulated_accepted_calls": 60, "simulated_positions": 1326, "remaining": 0}


@ARCHIVED_OLD_RUNTIME
def test_live_api_environment_is_rejected_before_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    with pytest.raises(ValueError, match="API environment"):
        live.prepare_next(tmp_path / "state", neutral_root=tmp_path / "neutral")
    assert _private().summary(tmp_path / "state")["claimed_slots"] == 0


def test_live_process_absence_scan_ignores_its_own_probe_process(tmp_path: Path) -> None:
    live = _live()
    root = tmp_path / "never-used-slot-root"
    root.mkdir()
    proof = live._process_absence(root)
    assert proof["status"] == "ABSENT"
    assert proof["unique_neutral_slot_root"] == str(root)
    assert len(proof["scanner_sha256"]) == 64


@ARCHIVED_OLD_RUNTIME
def test_immutable_live_approval_binds_exact_route_and_rejects_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    approval = live.verify_live_approval()
    assert approval["maximum_unique_contacts"] == 60
    assert approval["requested"] == live.REQUESTED
    assert approval["timeout_seconds"] == 7200.0
    successor = live.verify_live_approval_v3()
    assert successor["execution_status"] == "AUTHORIZED_ZERO_PAID_GPT_5_6_CORE_WORK"
    drift = dict(approval)
    drift["controller_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Immutable live approval"):
        live._review_approval(drift)
    driver = _driver()
    preflight = driver.preflight(tmp_path / "driver-state")
    assert preflight["execution_status"] == "AUTHORIZED_ZERO_PAID_GPT_5_6_CORE_WORK"
    assert preflight["launch"] == "PREFLIGHT_COMPLETE_NO_PROVIDER_CONTACT"


@ARCHIVED_OLD_RUNTIME
def test_injected_accepted_dispatch_writes_receipt_without_provider_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    live.verify_binding()
    neutral = tmp_path / "neutral"
    monkeypatch.setattr(live, "NEUTRAL_WORK_ROOT", neutral)
    monkeypatch.setattr(live, "_review_approval", lambda approval: ("fake-codex", "f" * 64))
    monkeypatch.setattr(live, "_process_absence", lambda slot_root: {"status": "ABSENT", "method": "windows_command_line_scan", "unique_neutral_slot_root": str(slot_root), "scanner_sha256": "e" * 64})
    request = live._prepared_requests()[21]
    calls: list[dict] = []
    def fake_call(**kwargs):
        calls.append(kwargs)
        return live._simulated_content(request), {"reported": live.REPORTED}
    result = live.dispatch_prepared_slot(tmp_path / "state", approval=live.verify_live_approval_v3(), neutral_root=neutral, call=fake_call)
    assert result is not None and result["slot_id"] == "author_original-r3-b01"
    assert len(calls) == 1 and calls[0]["timeout"] == 7200.0
    assert (tmp_path / "state" / "call-receipts" / "author_original-r3-b01.v1.json").is_file()
    terminal = json.loads((tmp_path / "state" / "terminals" / "author_original-r3-b01.terminal.v1.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "accepted"


@ARCHIVED_OLD_RUNTIME
def test_injected_timeout_halts_without_duplicate_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live()
    _clear_api_environment(monkeypatch, live)
    live.verify_binding()
    neutral = tmp_path / "neutral"
    monkeypatch.setattr(live, "NEUTRAL_WORK_ROOT", neutral)
    monkeypatch.setattr(live, "_review_approval", lambda approval: ("fake-codex", "f" * 64))
    monkeypatch.setattr(live, "_process_absence", lambda slot_root: {"status": "ABSENT", "method": "windows_command_line_scan", "unique_neutral_slot_root": str(slot_root), "scanner_sha256": "e" * 64})
    calls = 0
    def timeout_call(**kwargs):
        nonlocal calls
        calls += 1
        raise live._runner()._ProviderAttemptFailure("injected timeout", retryable=True)
    with pytest.raises(Exception, match="injected timeout"):
        live.dispatch_prepared_slot(tmp_path / "state", approval=live.verify_live_approval_v3(), neutral_root=neutral, call=timeout_call)
    assert calls == 1
    with pytest.raises(ValueError, match="halted"):
        live.prepare_next(tmp_path / "state", neutral_root=neutral, production=True)
    assert _private().summary(tmp_path / "state")["claimed_slots"] == 1
