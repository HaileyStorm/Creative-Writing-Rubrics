from __future__ import annotations

import importlib.util
import json
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

SUPPORT_PATH = Path(__file__).with_name("test_hbq_human_alignment_wpb_compact_native_v1.py")
_spec = importlib.util.spec_from_file_location("wpb_native_batch_support", SUPPORT_PATH)
assert _spec and _spec.loader
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)


def campaign_args(args: dict[str, Any], *, queue: bool = False) -> dict[str, Any]:
    result = {"campaign_root": args["output_root"], "freeze_root": args["freeze_root"], "authorization_acknowledgement_sha256": args["authorization_acknowledgement_sha256"]}
    if queue:
        result["queue_root"] = args["queue_root"]
    return result


def prepare(value: Any, args: dict[str, Any]) -> dict[str, Any]:
    return value.prepare_next_batch(**campaign_args(args, queue=True), grok_route_provider=args["grok_route_provider"])


def execute(value: Any, args: dict[str, Any], batch: dict[str, Any], contacts: Any, **runner_options: Any) -> list[dict[str, Any]]:
    rows = value._resolution(freeze_root=support.FREEZE)["rows"]
    return value.execute_batch(**campaign_args(args, queue=True), batch_number=batch["batch_number"], allow_remote=True,
                               grok_broker_factory=args["grok_broker_factory"],
                               grok_runner_factory=lambda _error: support.grok_runner(value, rows, contacts, **runner_options))


@pytest.fixture(scope="module")
def completed_campaign(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    value = support.executor()
    args = support.common(value, tmp_path_factory.mktemp("wpb-batch-campaign"), "grok")
    created = value.create_campaign(**campaign_args(args))
    contacts = support.Contacts()
    batches, settlements, roots = [], [], {}
    for _ in range(13):
        batch = prepare(value, args)
        outcomes = execute(value, args, batch, contacts)
        assert len(outcomes) == len(batch["prepared_cells"])
        settlement = value.settle_batch(**campaign_args(args), batch_number=batch["batch_number"])
        assert settlement["completed_cells"] == batch["prepared_cells"]
        assert not settlement["consumed_cells"] and not settlement["eligible_successors"]
        batches.append(batch)
        settlements.append(settlement)
        for cell in batch["prepared_cells"]:
            roots[cell] = value._batch_root(args["output_root"], batch["batch_number"]) / "execution" / cell
    report = value.report(endpoint="grok", output_root=args["output_root"], freeze_root=support.FREEZE,
                          authorization_acknowledgement_sha256=support.ACK, profile=support.profile())
    return {"value": value, "args": args, "created": created, "contacts": contacts, "batches": batches,
            "settlements": settlements, "roots": roots, "report": report}


def test_all_129_cells_complete_once_across_renewed_batches(completed_campaign: dict[str, Any]) -> None:
    c = completed_campaign
    assert c["created"]["logical_cells"] == 129 and c["created"]["provider_calls_made"] == 0
    assert [len(batch["prepared_cells"]) for batch in c["batches"]] == [10] * 12 + [9]
    assert len(c["contacts"].calls) == len(set(c["contacts"].calls)) == 129
    assert c["contacts"].maximum <= 10
    assert c["report"]["measurement_count"] == 129
    assert c["report"]["native_endpoint_contact_cardinality"] == "unproven"
    assert c["report"]["analysis"]["mae"] == "not_applicable_pairwise_preference_target"
    assert len({binding["route_evidence_sha256"] for binding in c["report"]["native_receipt_bindings"].values()}) == 13
    with pytest.raises(ValueError, match="eligible"):
        prepare(c["value"], c["args"])


def test_campaign_report_rejects_native_and_chain_mutations(completed_campaign: dict[str, Any]) -> None:
    c = completed_campaign
    value, args = c["value"], c["args"]
    root = next(iter(c["roots"].values()))
    batch = value._batch_root(args["output_root"], 1)
    artifacts = [root / name for name in ("native-response.bin", "runtime-identity.json", "execution-receipt.json", "authorization-acknowledgement.json", "prepared.json", "outbound-payload.json")]
    artifacts += [batch / "plan.json", batch / "settlement.json"]
    for path in artifacts:
        original = path.read_bytes()
        path.write_bytes(b"{}\n")
        try:
            with pytest.raises((KeyError, TypeError, ValueError)):
                value.report(endpoint="grok", output_root=args["output_root"], freeze_root=support.FREEZE,
                             authorization_acknowledgement_sha256=support.ACK, profile=support.profile())
        finally:
            path.write_bytes(original)


def test_invalid_proof_and_active_batch_fail_before_successor_work(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    valid_provider = args["grok_route_provider"]

    def expired(queue_root: Path):
        route, evidence = valid_provider(queue_root)
        route["cost_evidence"]["expires_at"] = "2000-01-01T00:00:00+00:00"
        return route, evidence

    with pytest.raises(ValueError):
        value.prepare_next_batch(**campaign_args(args, queue=True), grok_route_provider=expired)
    assert not (args["output_root"] / "batches").exists()
    batch = prepare(value, args)
    batch_root = value._batch_root(args["output_root"], batch["batch_number"])
    marker = batch_root / "execution-active.json"
    marker.write_text("{}\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="active"):
            prepare(value, args)
        with pytest.raises(ValueError, match="active"):
            value.settle_batch(**campaign_args(args), batch_number=batch["batch_number"])
    finally:
        marker.unlink()
    settlement = value.settle_batch(**campaign_args(args), batch_number=batch["batch_number"])
    assert settlement["eligible_successors"] == batch["prepared_cells"]
    assert not settlement["completed_cells"] and not settlement["consumed_cells"]
    with pytest.raises(ValueError, match="partial"):
        value.report(endpoint="grok", output_root=args["output_root"], freeze_root=support.FREEZE,
                     authorization_acknowledgement_sha256=support.ACK, profile=support.profile())
    successor = prepare(value, args)
    assert successor["prepared_cells"] == batch["prepared_cells"]
    assert successor["batch_number"] == 2


def test_claim_without_launch_is_consumed_and_claim_drift_blocks_renewal(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    batch = prepare(value, args)
    execution = value._batch_root(args["output_root"], 1) / "execution"
    first = batch["prepared_cells"][0]
    resolution = value._resolution(freeze_root=support.FREEZE)
    with value._grok_bound(resolution) as (_lifecycle, runtime, _v9, _v11, _v13, _v15):
        assert runtime._claim(execution, first) == "claimed_now"
    assert not (execution / first / "launch-intent.json").exists()
    settlement = value.settle_batch(**campaign_args(args), batch_number=1)
    assert settlement["consumed_cells"] == [first]
    assert first not in settlement["eligible_successors"]
    claim = execution / ".claims" / first / "claim.json"
    original = claim.read_bytes()
    for replacement in (b"{}\n", None):
        if replacement is None:
            claim.unlink()
        else:
            claim.write_bytes(replacement)
        try:
            with pytest.raises((OSError, TypeError, ValueError)):
                prepare(value, args)
        finally:
            claim.write_bytes(original)
    successor = prepare(value, args)
    assert first not in successor["prepared_cells"]
    assert len(successor["prepared_cells"]) == 10


def test_setup_failure_does_not_strand_execution_marker(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    batch = prepare(value, args)

    def broken_factory(_error_type: type[Exception]):
        raise RuntimeError("fixture setup failure")

    with pytest.raises(RuntimeError, match="setup failure"):
        value.execute_batch(**campaign_args(args, queue=True), batch_number=1, allow_remote=True,
                            grok_broker_factory=args["grok_broker_factory"], grok_runner_factory=broken_factory)
    assert not (value._batch_root(args["output_root"], 1) / "execution-active.json").exists()
    settlement = value.settle_batch(**campaign_args(args), batch_number=1)
    assert settlement["eligible_successors"] == batch["prepared_cells"]


def test_one_native_batch_admits_receipts_and_refuses_resend(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    batch = prepare(value, args)
    contacts = support.Contacts()
    outcomes = execute(value, args, batch, contacts)
    assert len(outcomes) == len(contacts.calls) == 10
    settlement = value.settle_batch(**campaign_args(args), batch_number=1)
    assert settlement["completed_cells"] == batch["prepared_cells"]
    assert not settlement["consumed_cells"] and not settlement["eligible_successors"]
    with pytest.raises(ValueError):
        execute(value, args, batch, contacts)
    assert len(contacts.calls) == 10
    with pytest.raises(ValueError, match="partial"):
        value.report(endpoint="grok", output_root=args["output_root"], freeze_root=support.FREEZE,
                     authorization_acknowledgement_sha256=support.ACK, profile=support.profile())


def test_default_shared_request_path_preserves_raw_bytes_and_uses_one_gate(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    batch = prepare(value, args)
    batch_root = value._batch_root(args["output_root"], 1)
    plan = json.loads((batch_root / "plan.json").read_bytes())
    route = plan["route"]
    blobs: dict[str, bytes] = {}
    sessions: list[str] = []
    adapter_bytes = lambda obj: json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    def factory(queue_root: Path, broker_type: type[Any], _error_type: type[Exception]) -> Any:
        broker = broker_type(queue_root, grok_host_gate_path=tmp_path / "temporary-shared-gate.sqlite3")
        broker.init()

        def request(route_name, payload, *, output_schema, nonvisual_max_turns, session_id, before_contact, expected_route_sha256):
            assert route_name == route["name"] and expected_route_sha256 == value.sha256(adapter_bytes(route))
            assert nonvisual_max_turns == 1 and set(payload) == {"prompt"}
            before_contact()
            sessions.append(session_id)
            result = support.answer(value)
            envelope = support.native_envelope(result, session_id, f"request-{session_id}")
            raw = b" \n" + json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            digest = value.sha256(raw)
            blobs[digest] = raw
            prompt = payload["prompt"].encode("utf-8")
            return {"state": "completed", "failure": None,
                    "result": support.shared_result(value, prompt, output_schema, route, raw)}

        broker.run_grok_native_request = request
        broker.run_grok_native_contact = lambda *_args, **_kwargs: pytest.fail("shared request was guarded a second time")
        broker.read_grok_native_envelope = lambda descriptor: blobs[descriptor["sha256"]]
        return broker

    outcomes = value.execute_batch(**campaign_args(args, queue=True), batch_number=1, allow_remote=True, grok_broker_factory=factory)
    assert len(outcomes) == len(sessions) == len(set(sessions)) == 10
    settlement = value.settle_batch(**campaign_args(args), batch_number=1)
    assert settlement["completed_cells"] == batch["prepared_cells"]
    for cell_id in batch["prepared_cells"]:
        cell = batch_root / "execution" / cell_id
        raw = (cell / "native-response.bin").read_bytes()
        assert raw.startswith(b" \n") and raw == blobs[value.sha256(raw)]
        assert value._shared_result_path(cell).is_file()


def test_shared_schema_accepts_exact_frozen_wpb_contract(tmp_path: Path) -> None:
    value = support.executor()
    core = value._resolution(freeze_root=support.FREEZE)["core"]
    broker, _error_type = value._grok_broker(tmp_path / "queue", lambda root, cls, _error: cls(root, grok_host_gate_path=tmp_path / "host.sqlite3"))
    actual, raw = broker._freeze_grok_output_schema(core.RESPONSE_SCHEMA)
    assert actual == core.RESPONSE_SCHEMA
    assert json.loads(raw) == core.RESPONSE_SCHEMA


def test_batch_slots_do_not_read_another_workers_unfinished_file(tmp_path: Path) -> None:
    value = support.executor()
    resolution = value._resolution(freeze_root=support.FREEZE)
    rows = tuple(resolution["rows"][:10])
    execution = tmp_path / "execution"
    execution.mkdir()
    barrier = threading.Barrier(10)
    with value._grok_bound(resolution) as (_lifecycle, base, _v9, _v11, _v13, _v15):
        original_write = base._write_slot

        def unfinished_write(path: Path, record: dict[str, Any]) -> None:
            with path.open("xb") as handle:
                barrier.wait(timeout=20)
                handle.write(base.canonical(record))

        base._write_slot = unfinished_write
        runtime = value._batch_slot_runtime(base, execution, rows)
        try:
            with ThreadPoolExecutor(max_workers=10) as pool:
                acquired = list(pool.map(lambda row: runtime._acquire_global_slot(execution, row["cell_id"]), rows))
            assert len({path for path, _record in acquired}) == 10
            assert {record["slot"] for _path, record in acquired} == set(range(10))
        finally:
            base._write_slot = original_write
        occupied, record = acquired[0]
        original = occupied.read_bytes()
        with pytest.raises(FileExistsError):
            runtime._acquire_global_slot(execution, rows[0]["cell_id"])
        assert occupied.read_bytes() == original
        for path, record in acquired:
            runtime._release_global_slot(path, record)


def test_missing_or_changed_shared_proof_is_consumed_before_settlement(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    batch = prepare(value, args)
    contacts = support.Contacts()
    execute(value, args, batch, contacts)
    execution = value._batch_root(args["output_root"], 1) / "execution"
    missing, changed = batch["prepared_cells"][:2]
    value._shared_result_path(execution / missing).unlink()
    proof_path = value._shared_result_path(execution / changed)
    proof = json.loads(proof_path.read_bytes())
    proof["runtime"]["execution_contract"]["staged_prompt_sha256"] = "0" * 64
    proof_path.write_bytes(value.canonical(proof))
    settlement = value.settle_batch(**campaign_args(args), batch_number=1)
    assert set(settlement["consumed_cells"]) == {missing, changed}
    assert len(settlement["completed_cells"]) == 8 and not settlement["eligible_successors"]
    assert len(contacts.calls) == 10
    with pytest.raises(ValueError):
        execute(value, args, batch, contacts)


def test_batch_cannot_rebind_its_authorization_away_from_campaign(tmp_path: Path) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    prepare(value, args)
    batch = value._batch_root(args["output_root"], 1)
    plan_path, ack_path = batch / "plan.json", batch / "batch-acknowledgement.json"
    plan, ack = json.loads(plan_path.read_bytes()), json.loads(ack_path.read_bytes())
    plan["authorization_acknowledgement_sha256"] = ack["authorization_acknowledgement_sha256"] = "b" * 64
    ack_path.write_bytes(value.canonical(ack))
    plan["batch_acknowledgement_sha256"] = value.sha256(ack_path.read_bytes())
    plan_path.write_bytes(value.canonical(plan))
    with pytest.raises(ValueError):
        value._batch_plan(args["output_root"], 1, value.sha256((args["output_root"] / "campaign.json").read_bytes()))
    assert not (batch / "execution-active.json").exists()
    assert not (batch / "execution" / ".claims").exists()


def test_live_route_uses_current_pinned_broker_not_historical_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = support.executor()
    broker = object()
    calls = []

    def native_validate(root, *, broker_factory):
        assert root == tmp_path and broker_factory(root) is broker
        calls.append(root)
        return {"name": "fixture"}, {"proof": "fixture"}

    monkeypatch.setattr(value, "_grok_broker", lambda root, factory: (broker, RuntimeError))
    lifecycle = SimpleNamespace(live=lambda: SimpleNamespace(_native_exec=lambda: SimpleNamespace(validate_live_grok_route=native_validate)))
    assert value._grok_live_route(lifecycle, tmp_path) == ({"name": "fixture"}, {"proof": "fixture"})
    assert calls == [tmp_path]


def test_default_batch_preparation_uses_reviewed_live_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = support.executor()
    args = support.common(value, tmp_path, "grok")
    value.create_campaign(**campaign_args(args))
    calls = []

    def live(_lifecycle, root):
        calls.append(root)
        return args["grok_route_provider"](root)

    monkeypatch.setattr(value, "_grok_live_route", live)
    batch = value.prepare_next_batch(**campaign_args(args, queue=True))
    assert len(batch["prepared_cells"]) == 10 and calls == [args["queue_root"]]
