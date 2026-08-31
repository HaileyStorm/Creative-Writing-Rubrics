from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-exec-v1"
ACK = "a" * 64
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module():
    spec = importlib.util.spec_from_file_location("_confirmation_sol_exec", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def schedule(value):
    groups = [f"group-{index}" for index in range(8)]
    cells = []
    for item_index in range(19):
        item = f"item-{item_index:02d}"
        group = groups[item_index % len(groups)]
        for candidate in (value.BASELINE, value.SELECTED):
            payload = value.canonical({"study_id": value.FREEZE_ID, "item_id": item, "candidate_id": candidate, "response_schema": {"type": "object", "properties": {"scores": {"type": "object"}}}})
            cells.append({"cell_id": f"neutral-{candidate[-4:]}-{item}", "candidate_id": candidate, "partition": "confirmation", "prompt_group_id": group, "item_id": item, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": hashlib.sha256(payload).hexdigest(), "response_schema_sha256": hashlib.sha256(value.canonical({"type": "object", "properties": {"scores": {"type": "object"}}})).hexdigest(), "target": {dimension: 2.0 for dimension in DIMENSIONS}})
    result = {"study_id": value.FREEZE_ID, "candidate_selection": {"control_candidate_id": value.BASELINE, "selected_candidate_id": value.SELECTED}, "cells": cells, "geometry": {"candidates": 2, "confirmation_items": 19, "confirmation_groups": 8, "endpoint_neutral_logical_cells": 38}}
    result["schedule_sha256"] = value.SCHEDULE_SHA256
    return result


class FakeBase:
    def __init__(self, counter=None):
        self.route_calls = 0
        self.counter = counter

    def _route(self, _queue, _factory):
        self.route_calls += 1
        return {"name": "fixture"}, {"fixture": True}, None

    @staticmethod
    def _prepared(row, payload, schema, target, route, evidence, acknowledgement):
        return {"prepared.json": json.dumps({"cell": row, "payload_sha256": hashlib.sha256(payload).hexdigest(), "schema_sha256": hashlib.sha256(schema).hexdigest(), "target": target, "route": route, "evidence": evidence, "ack": acknowledgement}, sort_keys=True).encode("utf-8")}

    @staticmethod
    def _write_new(path, raw):
        path.write_bytes(raw)

    @staticmethod
    def canonical(value):
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    def execute_one(self, **kwargs):
        if self.counter is not None:
            with self.counter["lock"]:
                self.counter["active"] += 1
                self.counter["maximum"] = max(self.counter["maximum"], self.counter["active"])
            time.sleep(0.01)
            with self.counter["lock"]:
                self.counter["active"] -= 1
        return {"cell_id": kwargs["cell_id"], "state": "fixture"}


def resolution(value):
    source = schedule(value)
    return {"schedule": source, "schedule_sha256": value.sha256(value.canonical(source)), "rows": value._rows(source)}


def configure_fixture(value, monkeypatch, *, counter=None):
    resolved = resolution(value)
    base = FakeBase(counter)
    monkeypatch.setattr(value, "_resolve", lambda *, frozen_root: resolved)
    monkeypatch.setattr(value, "_configured_base", lambda _resolution: base)
    return resolved, base


def test_frozen_schedule_has_exact_38_paired_bytes_and_eight_groups():
    value = module()
    source = schedule(value)
    rows = value._rows(source)
    assert len(rows) == 38
    assert {row["candidate_id"] for row in rows} == {value.BASELINE, value.SELECTED}
    assert len({row["item_id"] for row in rows}) == 19
    assert len({row["prompt_group_id"] for row in rows}) == 8
    by_source = {cell["cell_id"]: cell for cell in source["cells"]}
    assert all(base64.b64decode(row["payload_base64"]) == base64.b64decode(by_source[row["source_cell_id"]]["payload_base64"]) for row in rows)


def test_tampered_payload_and_partition_are_rejected():
    value = module()
    source = schedule(value)
    source["cells"][0]["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="payload"):
        value._rows(source)
    source = schedule(value)
    source["cells"][0]["prompt_group_id"] = "group-extra"
    with pytest.raises(ValueError, match="partition"):
        value._rows(source)


def test_prepare_is_zero_contact_and_loads_route_once(tmp_path, monkeypatch):
    value = module()
    _resolved, base = configure_fixture(value, monkeypatch)
    frozen, queue, output = tmp_path / "frozen", tmp_path / "queue", tmp_path / "output"
    frozen.mkdir(); queue.mkdir()
    result = value.prepare_all(output_root=output, frozen_root=frozen, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    assert result == {"study_id": value.STUDY_ID, "cells": 38, "confirmation_items": 19, "confirmation_groups": 8, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "max_concurrency": 2, "authority": "confirmation_measurement_only"}
    assert base.route_calls == 1
    assert len(list(output.iterdir())) == 38


def test_route_loading_is_serialized():
    value = module()
    state = {"active": 0, "maximum": 0, "calls": 0}
    guard, barrier = threading.Lock(), threading.Barrier(3)

    def route():
        with guard:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            state["calls"] += 1
        time.sleep(0.02)
        with guard:
            state["active"] -= 1
        return "route"

    workers = [threading.Thread(target=lambda: (barrier.wait(), value._locked_route(route)), daemon=True) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(2)
    assert not any(worker.is_alive() for worker in workers)
    assert state == {"active": 0, "maximum": 1, "calls": 2}


def test_wave_uses_two_lanes_and_duplicate_claim_is_blocked(tmp_path, monkeypatch):
    value = module()
    counter = {"active": 0, "maximum": 0, "lock": threading.Lock()}
    _resolved, _base = configure_fixture(value, monkeypatch, counter=counter)
    frozen, queue, output = tmp_path / "frozen", tmp_path / "queue", tmp_path / "output"
    frozen.mkdir(); queue.mkdir()
    value.prepare_all(output_root=output, frozen_root=frozen, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    locks = value._locks(output)
    claim = value._claim_cell(locks, output / "confirmation-sol-neutral-0000-item-00", "same-cell")
    try:
        with pytest.raises(TimeoutError):
            original = value.WAIT_SECONDS
            value.WAIT_SECONDS = 0.02
            try:
                value._claim_cell(locks, output / "confirmation-sol-neutral-0000-item-00", "same-cell")
            finally:
                value.WAIT_SECONDS = original
    finally:
        value._release(claim)
    results = value.execute_wave(output_root=output, frozen_root=frozen, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)
    assert len(results) == 38 and counter["maximum"] == 2


def test_runtime_has_no_dspy_or_optuna_and_pins_the_committed_freeze():
    value = module()
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert value.validate_package()["pinned_dependencies"]["confirmation_freeze"]["schedule_sha256"] == value.SCHEDULE_SHA256
    freeze, _v4 = value._sources()
    assert freeze.STUDY_ID == value.FREEZE_ID
