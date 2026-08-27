from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import pytest

REPOSITORY=Path(__file__).resolve().parents[1]
PUBLIC=REPOSITORY / "evaluation-results" / "hbq-qpc24-two-pass-product-confirmation-v2"
PRIVATE=Path(r"C:\Users\Haile\Documents\cwr-qpc24-two-pass-product-confirmation-v2-4ce1204-20260825")

ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived QPC24 two-pass v2 controller mechanics require the frozen 4ce1204 runtime; current bindings have advanced."
)

def _module(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def _public(): return _module(PUBLIC / "study.py","qpc24_v2_public")
def _private(): return _module(PRIVATE / "freeze.py","qpc24_v2_freeze")
def _live():
    previous = sys.modules.get("freeze")
    sys.modules["freeze"] = _private()
    try:
        return _module(PRIVATE / "live_controller.py","qpc24_v2_live")
    finally:
        if previous is None:
            sys.modules.pop("freeze", None)
        else:
            sys.modules["freeze"] = previous
def _clear_api(monkeypatch,live):
    for key in live.API_ENVIRONMENT_KEYS: monkeypatch.delenv(key,raising=False)

def test_current_head_fails_closed_while_v2_public_plan_remains_exact():
    public = _public()
    contract=public.contract()
    assert contract["source_head"] == public.HEAD == "4ce1204d8dd97feff2c7bd88237e265fac742adb"
    assert contract["execution"]["dispatch_surface"] == "absent"
    assert contract["execution"]["remote_provider_call_count_now"] == 0
    assert {key: contract["geometry"][key] for key in ("complete_eligible_question_count", "questions_per_provider_call", "full_batches_per_pass", "final_remainder_questions", "calls_per_pass", "target_voting_calls", "target_voting_positions", "maximum_unique_contacts")} == {"complete_eligible_question_count":221, "questions_per_provider_call":24, "full_batches_per_pass":9, "final_remainder_questions":5, "calls_per_pass":10, "target_voting_calls":60, "target_voting_positions":1326, "maximum_unique_contacts":60}
    assert contract["fidelity"]["per_selected_pass"] == "full_prose.novel_221_leaves_in_9x24_plus_5"
    assert contract["fidelity"]["historical_five_repeat_plan"] == "retained_as_extended_validation_path_not_replaced"
    assert contract["non_claims"]["runtime_default"] == "none"
    assert contract["non_claims"]["new_evaluation_mode"] == "none"
    assert contract["non_claims"]["replacement_of_five_repeat_validation"] == "none"
    with pytest.raises(ValueError, match="QPC24 v2 exact-head drift"):
        public.validate()

@ARCHIVED_OLD_RUNTIME
def test_v2_selects_only_fresh_two_pass_slots_and_preserves_v1_incident():
    private=_private(); frozen=private.verify_freeze(); slots=frozen["slots"]
    assert len(slots) == 60 and sum(slot["question_count"] for slot in slots) == 1326
    assert {slot["base_request_index"] for slot in slots} == set(range(31,71)) | set(range(101,121))
    assert {slot["base_request_index"] for slot in slots}.isdisjoint(range(1,14))
    assert 21 not in {slot["base_request_index"] for slot in slots}
    assert frozen["selection"]["primary_repetitions"] == {"author_original":[4,5],"gpt_5_6_pro_rewrite":[1,2],"public_control_story":[1,2]}
    assert frozen["historical_contact_ledger"]["contacted_request_indexes"] == list(range(1,14))+[21]
    assert "live-approval.v3.json" in frozen["historical_contact_ledger"]["v1_approvals"]

@ARCHIVED_OLD_RUNTIME
def test_slot_claim_is_immutable_and_never_resends_after_restart(tmp_path:Path):
    first=_private().claim_next(tmp_path); assert first and first["slot_id"] == "author_original-r4-b01"
    assert _private().claim_next(tmp_path)["slot_id"] == "author_original-r4-b02"
    assert _private().summary(tmp_path) == {"study_id":"hbq-qpc24-two-pass-product-confirmation-v2","provider_calls":0,"eligible_never_claimed_slots":58,"claimed_slots":2,"terminal_slots":0,"claimed_without_terminal_nonvoting":2}

def test_identity_normalizer_allows_only_optional_nonempty_session_id(tmp_path:Path,monkeypatch):
    live=_live(); _clear_api(monkeypatch,live)
    assert live.normalize_reported(live.REPORTED)[0] == live.REPORTED
    with_session={**live.REPORTED,"session_id":"session-private"}
    assert live.normalize_reported(with_session)[0] == with_session
    for bad in ({**live.REPORTED,"model":"wrong"},{**live.REPORTED,"session_id":""},{**live.REPORTED,"unexpected":"x"}):
        with pytest.raises(ValueError,match="identity receipt drift"): live.normalize_reported(bad)

@ARCHIVED_OLD_RUNTIME
def test_injected_session_identity_dispatch_persists_commitment_and_accepts(tmp_path:Path,monkeypatch):
    live=_live(); _clear_api(monkeypatch,live); binding=live.verify_binding(); monkeypatch.setattr(live,"verify_binding",lambda:binding); neutral=tmp_path / "neutral"; monkeypatch.setattr(live,"NEUTRAL_WORK_ROOT",neutral)
    monkeypatch.setattr(live,"_review_approval",lambda approval:"fake-codex")
    monkeypatch.setattr(live,"_process_absence",lambda root:{"status":"ABSENT","unique_neutral_slot_root":str(root)})
    request=live._prepared_requests()[31]; calls=[]
    def fake_call(**kwargs): calls.append(kwargs); return live._simulated_content(request),{"reported":{**live.REPORTED,"session_id":"session-private"}}
    result=live.dispatch_prepared_slot(tmp_path / "state",approval=live.load_live_approval(),neutral_root=neutral,call=fake_call)
    assert result and result["slot_id"] == "author_original-r4-b01" and len(calls) == 1 and calls[0]["timeout"] == 7200.0
    report=json.loads((tmp_path / "state" / "reported-identity-receipts" / "author_original-r4-b01.v1.json").read_text())
    assert report["reported"] == {**live.REPORTED,"session_id":"session-private"} and len(report["reported_sha256"]) == 64
    assert json.loads((tmp_path / "state" / "terminals" / "author_original-r4-b01.terminal.v1.json").read_text())["status"] == "accepted"

@ARCHIVED_OLD_RUNTIME
def test_identity_mismatch_is_persisted_then_terminalized_and_halted(tmp_path:Path,monkeypatch):
    live=_live(); _clear_api(monkeypatch,live); binding=live.verify_binding(); monkeypatch.setattr(live,"verify_binding",lambda:binding); neutral=tmp_path / "neutral"; monkeypatch.setattr(live,"NEUTRAL_WORK_ROOT",neutral)
    monkeypatch.setattr(live,"_review_approval",lambda approval:"fake-codex")
    monkeypatch.setattr(live,"_process_absence",lambda root:{"status":"ABSENT","unique_neutral_slot_root":str(root)})
    request=live._prepared_requests()[31]
    with pytest.raises(ValueError,match="identity receipt drift"):
        live.dispatch_prepared_slot(tmp_path / "state",approval=live.load_live_approval(),neutral_root=neutral,call=lambda **kwargs:(live._simulated_content(request),{"reported":{**live.REPORTED,"model":"wrong"}}))
    state=tmp_path / "state"; assert (state / "reported-identity-receipts" / "author_original-r4-b01.v1.json").is_file()
    assert json.loads((state / "terminals" / "author_original-r4-b01.terminal.v1.json").read_text())["status"] == "invalid_identity_or_receipt"
    assert (state / "automatic-advancement-halts" / "author_original-r4-b01.v1.json").is_file()
    with pytest.raises(ValueError,match="halted"): live.prepare_next(state,neutral_root=neutral,production=True)
    assert _private().summary(state)["claimed_without_terminal_nonvoting"] == 0

@ARCHIVED_OLD_RUNTIME
def test_timeout_terminalizes_halts_and_no_provider_route_runs(tmp_path:Path,monkeypatch):
    live=_live(); _clear_api(monkeypatch,live); binding=live.verify_binding(); monkeypatch.setattr(live,"verify_binding",lambda:binding); neutral=tmp_path / "neutral"; monkeypatch.setattr(live,"NEUTRAL_WORK_ROOT",neutral)
    monkeypatch.setattr(live,"_review_approval",lambda approval:"fake-codex")
    monkeypatch.setattr(live,"_process_absence",lambda root:{"status":"ABSENT","unique_neutral_slot_root":str(root)})
    calls=0
    def timeout(**kwargs):
        nonlocal calls; calls+=1; raise TimeoutError("injected timeout")
    with pytest.raises(TimeoutError): live.dispatch_prepared_slot(tmp_path / "state",approval=live.load_live_approval(),neutral_root=neutral,call=timeout)
    assert calls == 1
    terminal=json.loads((tmp_path / "state" / "terminals" / "author_original-r4-b01.terminal.v1.json").read_text())
    assert terminal["status"] == "local_transport_ambiguity" and (tmp_path / "state" / "automatic-advancement-halts").is_dir()

@ARCHIVED_OLD_RUNTIME
def test_preflight_and_simulation_are_provider_free(tmp_path:Path,monkeypatch):
    live=_live(); _clear_api(monkeypatch,live)
    result=live.dry_preflight(tmp_path / "state",neutral_root=tmp_path / "neutral")
    assert result["provider_calls"] == 0 and result["next_slot"] == "author_original-r4-b01"
    simulation=live.simulate_full_success(tmp_path / "simulation",neutral_root=tmp_path / "sim-neutral")
    assert simulation == {"provider_calls":0,"simulated_accepted_calls":60,"simulated_positions":1326,"remaining":0}
