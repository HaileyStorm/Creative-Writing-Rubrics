from __future__ import annotations

import asyncio
import functools
import hashlib
import importlib.util
import json
import multiprocessing
import os
import queue
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v1"
FREEZE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("_broader_exec_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def freeze_module():
    spec = importlib.util.spec_from_file_location("_broader_exec_freeze_test", FREEZE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def frozen_root(tmp_path: Path) -> Path:
    root = tmp_path / "frozen"
    freeze_module().freeze(output_root=root, normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    return root


def route(_queue: Path):
    return ({"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "grok_command": ["fixture"], "allowed_payload_classes": ["public_repo", "public_synthetic"], "timeout_seconds": 1.0}, {"fixture": "route"})


def runner(**kwargs):
    prompt, root, value = kwargs["prompt"], kwargs["output_dir"], kwargs["route"]
    token = hashlib.sha256(prompt + str(root).encode()).hexdigest()
    responses = root / "responses"
    responses.mkdir()
    (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
    kwargs["before_contact"]()
    scores = {key: 3.0 for key in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}
    envelope = {"requestId": "request-" + token, "sessionId": "session-" + token, "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": {"scores": scores, "evidence": {key: "fixture" for key in scores}, "coverage": {key: True for key in scores}}}
    response = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
    identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    settings = {"route_name": value["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False}
    return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": identity, "effective_settings": settings}


def gated_runner(counter, guard, entries, release, **kwargs):
    with guard:
        counter["active"] += 1
        counter["maximum"] = max(counter["maximum"], counter["active"])
    entries.put(kwargs["output_dir"].name)
    try:
        if not release.wait(30):
            raise TimeoutError("test gate release timed out")
        return runner(**kwargs)
    finally:
        with guard:
            counter["active"] -= 1


def direct_worker(common_args, cell_id, counter, guard, entries, release, outcomes):
    value = module()
    try:
        result = value.execute_one(**common_args, cell_id=cell_id, allow_remote=True, runner=functools.partial(gated_runner, counter, guard, entries, release))
        outcomes.put(("ok", result.get("cell_id")))
    except BaseException as error:
        outcomes.put(("error", type(error).__name__, str(error)))


def common(tmp_path: Path):
    return {"output_root": tmp_path / "roots", "frozen_root": frozen_root(tmp_path), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": route}


def test_prepare_admits_exact_five_manifest_frozen_root_and_writes_35_zero_call_cells(tmp_path: Path):
    value, args = module(), common(tmp_path)
    result = value.prepare_all(**args)
    assert result["logical_cells"] == 35 and result["effective_candidates"] == 5
    assert result["provider_calls_made"] == result["process_launches"] == 0
    schedule = json.loads((args["output_root"] / "schedule.json").read_bytes())
    assert schedule["schedule_sha256"] == value.SCHEDULE_SHA256 and len(schedule["cells"]) == 35
    assert all((args["output_root"] / cell / "prepared.json").exists() for cell in result["prepared_cells"])
    with pytest.raises(ValueError):
        value.prepare_all(**args)


def test_frozen_root_payload_manifest_reparse_and_confirmation_tampering_are_rejected(tmp_path: Path):
    value, root = module(), frozen_root(tmp_path)
    schedule = json.loads((root / "schedule.json").read_bytes())
    schedule["cells"][0]["payload_base64"] = schedule["cells"][1]["payload_base64"]
    (root / "schedule.json").write_bytes(value.canonical(schedule))
    with pytest.raises(ValueError, match="commitment"):
        value.admit_frozen_root(root)
    root = frozen_root(tmp_path / "extra")
    (root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        value.admit_frozen_root(root)
    root = frozen_root(tmp_path / "link")
    try:
        os.symlink(root / "schedule.json", root / "reparse.json")
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(ValueError, match="unsafe|inventory"):
        value.admit_frozen_root(root)
    args = common(tmp_path / "confirmation")
    value.prepare_all(**args)
    with pytest.raises(ValueError, match="confirmation"):
        value.execute_one(**args, cell_id="confirmation-forbidden", allow_remote=True, runner=runner)


def test_wave_enforces_at_most_ten_slots_and_replay_is_durable(tmp_path: Path):
    value, args = module(), common(tmp_path)
    value.prepare_all(**args)
    admitted = value.admit_frozen_root(args["frozen_root"])
    original_admit = value.admit_frozen_root
    value.admit_frozen_root = lambda _root: admitted
    lock = threading.Lock()
    active = maximum = 0
    def concurrent(**kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.01)
            return runner(**kwargs)
        finally:
            with lock:
                active -= 1
    try:
        rows = asyncio.run(value.execute_wave(**args, allow_remote=True, runner=concurrent))
        assert len(rows) == 35 and 1 <= maximum <= 10
        assert all(row["state"] == "provisional_scoring_received" for row in rows)
        collector = tmp_path / "collector.json"
        final = value.finalize_collector(output_root=args["output_root"], frozen_root=args["frozen_root"], collector_output=collector, authorization_acknowledgement_sha256=ACK)
        assert final["cells"] == 35
        replay = value.replay_collector(output_root=args["output_root"], frozen_root=args["frozen_root"], collector_path=collector)
        assert replay["equal_group_projection_ready"] is True
        tampered = json.loads(collector.read_bytes())
        tampered["cells"][0]["native_response_sha256"] = "0" * 64
        collector.write_bytes(value.canonical(tampered))
        with pytest.raises(ValueError, match="payload/response/settings"):
            value.replay_collector(output_root=args["output_root"], frozen_root=args["frozen_root"], collector_path=collector)
    finally:
        value.admit_frozen_root = original_admit


def test_direct_multiprocess_callers_share_exact_ten_slots_and_foreign_slot_fails_closed(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        counter, guard, release = manager.dict(active=0, maximum=0), manager.Lock(), manager.Event()
        entries, outcomes = context.Queue(), context.Queue()
        common_args = {key: item for key, item in args.items() if key != "route_provider"}
        common_args["route_provider"] = route
        workers = [context.Process(target=direct_worker, args=(common_args, cell_id, counter, guard, entries, release, outcomes)) for cell_id in prepared["prepared_cells"][:11]]
        for worker in workers:
            worker.start()
        try:
            entered = {entries.get(timeout=45) for _ in range(10)}
        except queue.Empty:
            for worker in workers:
                worker.join(10)
            reports = []
            while True:
                try:
                    reports.append(outcomes.get_nowait())
                except queue.Empty:
                    break
            pytest.fail(f"direct runner entries did not reach ten slots: {reports}")
        assert len(entered) == 10 and counter["maximum"] == 10
        with pytest.raises(queue.Empty):
            entries.get(timeout=0.5)
        release.set()
        for worker in workers:
            worker.join(60)
        assert all(worker.exitcode == 0 for worker in workers)
        assert sorted(outcomes.get(timeout=5) for _ in workers) == [("ok", cell_id) for cell_id in sorted(prepared["prepared_cells"][:11])]
        assert dict(counter) == {"active": 0, "maximum": 10}
    locks, root_hash = value._slot_root(args["output_root"])
    foreign = locks / "slot-0.lock"
    foreign.write_bytes(value.canonical({"format_version": 1, "study_id": "foreign", "kind": "global_broader_grok_execution_slot", "cell_id": "foreign", "slot": 0, "output_root_sha256": root_hash, "token": "0" * 32}))
    with pytest.raises(ValueError, match="foreign or malformed"):
        value._acquire_global_slot(args["output_root"], "foreign-test")


def test_slot_release_survives_concurrent_occupied_slot_scanning(tmp_path: Path):
    value, args = module(), common(tmp_path)
    value.prepare_all(**args)
    held = [value._acquire_global_slot(args["output_root"], f"held-{index}") for index in range(value.MAX_CONCURRENCY)]
    started, result = threading.Event(), []
    def scanner():
        started.set()
        try:
            slot, record = value._acquire_global_slot(args["output_root"], "scanner")
            result.append("acquired")
            value._release_global_slot(slot, record)
        except BaseException as error:
            result.append((type(error).__name__, str(error)))
    thread = threading.Thread(target=scanner)
    thread.start()
    assert started.wait(2)
    time.sleep(0.1)
    try:
        value._release_global_slot(*held[0])
        thread.join(10)
        assert not thread.is_alive() and result == ["acquired"]
    finally:
        for slot, record in held[1:]:
            value._release_global_slot(slot, record)


def test_ambiguous_claim_is_terminal_and_expired_lease_never_contacts_again(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    cell = prepared["prepared_cells"][0]
    calls = 0
    def ambiguous(**kwargs):
        nonlocal calls
        calls += 1
        kwargs["before_contact"]()
        raise RuntimeError("ambiguous")
    first = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=ambiguous)
    assert first["kind"] == "reconcile_required_after_process_launch" and calls == 1
    second = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=ambiguous)
    assert second["state"] == "terminal" and calls == 1
    other = prepared["prepared_cells"][1]
    claims = args["output_root"] / value.CLAIMS
    claims.mkdir(exist_ok=True)
    (claims / other).mkdir()
    (claims / other / "claim.json").write_bytes(value.canonical({"format_version": 1, "study_id": value.STUDY_ID, "kind": "exclusive_execution_claim", "cell_id": other, "acquired_at": time.time() - value.LEASE_SECONDS - 1, "lease_seconds": value.LEASE_SECONDS}))
    expired = value.execute_one(**args, cell_id=other, allow_remote=True, runner=ambiguous)
    assert expired["state"] == "reconcile_required" and calls == 1
    assert value.execute_one(**args, cell_id=other, allow_remote=True, runner=ambiguous)["state"] == "terminal"


def test_cli_and_no_runtime_optimizer_dependency(tmp_path: Path):
    value, args = module(), common(tmp_path)
    captured = {}
    def prepared(**kwargs):
        captured.update(kwargs)
        return {"format_version": 1, "study_id": value.STUDY_ID, "kind": "prepared_35_broader_grok_development_cells", "prepared_cells": [], "logical_cells": 35, "effective_candidates": 5, "provider_calls_made": 0, "process_launches": 0}
    value.prepare_all = prepared
    assert value.main(["--prepare-all", "--output-root", str(args["output_root"]), "--frozen-root", str(args["frozen_root"]), "--queue-root", str(args["queue_root"]), "--authorization-acknowledgement-sha256", ACK]) == 0
    assert captured["frozen_root"] == args["frozen_root"] and captured["queue_root"] == args["queue_root"]
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
