from __future__ import annotations

import asyncio
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
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-grok-exec-v1"
ACK = "a" * 64


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def module():
    spec = importlib.util.spec_from_file_location("_hanna96_validation_grok_exec_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def schedule():
    cells = []
    for candidate in ("baseline", "descendant13"):
        for number in range(32):
            payload = f"prompt-{candidate}-{number}".encode()
            target = {"dimension": float(number)}
            cells.append({"cell_id": f"{candidate[:1]}{number:031x}", "candidate_id": candidate, "item_id": f"item-{number:02d}", "prompt_group_id": f"group-{number // 2:02d}", "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": hashlib.sha256(payload).hexdigest(), "source_binding_sha256": hashlib.sha256(f"source-{number}".encode()).hexdigest(), "target": target, "target_sha256": hashlib.sha256(canonical(target)).hexdigest()})
    value = {"format_version": 1, "study_id": "hbq-human-alignment-hanna96-validation-freeze-v1", "cells": cells, "geometry": {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}, "authority": {"endpoint_pooling": "forbidden", "generalization": "none", "process_launches": 0, "promotion": "none", "provider_calls_made": 0, "runtime": "none", "selection": "none"}}
    value["schedule_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


class FakeFreeze:
    def __init__(self, value):
        self.value = value

    def validate_frozen_root(self, _root):
        return self.value


class FakeSource:
    STUDY_ID = "source"

    def __init__(self):
        self.schedule = None

    def live(self):
        return self

    def _route(self, _queue_root, provider):
        return provider(Path("queue")) if provider else ({"provider": "xai", "model": "grok-4.6-build", "tools": False}, {"proof": "p"})

    def prepare_all(self, *, output_root, authorization_acknowledgement_sha256, route_provider, **_kwargs):
        _live, value = self.schedule()
        root = Path(output_root)
        root.mkdir()
        (root / ".claims").mkdir()
        (root / "schedule.json").write_bytes(canonical(value))
        for row in value["cells"]:
            route, evidence = route_provider(Path("queue"))
            cell = root / row["cell_id"]
            cell.mkdir()
            (cell / "prepared.json").write_bytes(canonical({"route": route, "route_evidence": evidence}))
            (cell / "authorization-acknowledgement.json").write_bytes(canonical({"acknowledgement_sha256": authorization_acknowledgement_sha256}))
        return {"prepared_cells": [row["cell_id"] for row in value["cells"]], "provider_calls_made": 0, "process_launches": 0}

    def execute_one(self, *, output_root, cell_id, **_kwargs):
        time.sleep(0.002)
        root = Path(output_root) / cell_id
        request = f"request-{cell_id}".encode()
        dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
        response = canonical({"requestId": f"request-{cell_id}", "sessionId": f"session-{cell_id}", "structuredOutput": {"scores": {dimension: 3 for dimension in dimensions}, "evidence": {dimension: "e" for dimension in dimensions}, "coverage": {dimension: True for dimension in dimensions}}})
        receipt = {"request": base64.b64encode(request).decode(), "response": base64.b64encode(response).decode(), "identity": {"request_id": f"request-{cell_id}", "session_id": f"session-{cell_id}"}, "settings": {"tools_enabled": False, "model": "grok-4.6-build"}}
        (root / "receipt.json").write_bytes(canonical(receipt))
        return {"cell_id": cell_id, "state": "provisional_scoring_received", "provider_calls_made": None, "process_launches": 1}

    def payload(self, row):
        raw = base64.b64decode(row["payload_base64"])
        return raw, raw, b"{}"

    def admit(self, root, _row, _schedule, _raw, _prompt, _schema, _route, _evidence, _ack, _live):
        receipt = json.loads((Path(root) / "receipt.json").read_text())
        return base64.b64decode(receipt["request"]), base64.b64decode(receipt["response"]), receipt["identity"], receipt["settings"]

    def validate_frozen_route(self, route, evidence):
        assert route["provider"] == "xai" and route["model"] == "grok-4.6-build" and route["tools"] is False and evidence == {"proof": "p"}

    def _validate_runner_result(self, value, _route, _payload):
        return value["native_request_bytes"], value["native_response_bytes"], dict(value["identity"]), value["effective_settings"]


class FakeRuntime:
    def __init__(self, source):
        self.source, self.guard, self.active, self.maximum = source, threading.Lock(), 0, 0

    def lifecycle(self):
        return self.source

    def _acquire_global_slot(self, _root, _cell):
        with self.guard:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        return Path("slot"), {"slot": 1}

    def _release_global_slot(self, _slot, _record):
        with self.guard:
            self.active -= 1

    def _claim(self, output_root, cell_id):
        claim = Path(output_root) / ".claims" / cell_id
        try:
            claim.mkdir()
        except FileExistsError:
            return "claimed"
        (claim / "claim.json").write_bytes(canonical({"cell_id": cell_id}))
        return "claimed_now"


def patch(monkeypatch, value):
    item, source = module(), FakeSource()
    runtime = FakeRuntime(source)
    monkeypatch.setattr(item, "freeze_module", lambda: FakeFreeze(value))
    monkeypatch.setattr(item, "SCHEDULE_SHA256", value["schedule_sha256"])
    monkeypatch.setattr(item, "_runtime", lambda: runtime)
    return item, runtime


def args(tmp_path):
    return {"output_root": tmp_path / "output", "frozen_root": tmp_path / "frozen", "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}


def test_prepare_uses_all_64_endpoint_neutral_cells_without_contact(monkeypatch, tmp_path):
    value = schedule()
    item, _runtime = patch(monkeypatch, value)
    route_calls = {"count": 0}

    def route(_queue):
        route_calls["count"] += 1
        return {"provider": "xai", "model": "grok-4.6-build", "tools": False}, {"proof": "p"}

    outcome = item.prepare_all(**args(tmp_path), route_provider=route)
    assert outcome["logical_cells"] == 64 and len(outcome["prepared_cells"]) == 64
    assert outcome["provider_calls_made"] == 0 and outcome["process_launches"] == 0 and route_calls["count"] == 1
    assert item.admit_frozen_root(tmp_path / "frozen") == value


def test_actual_fresh96_freeze_rebuilds_and_admits_without_provider_contact(tmp_path):
    item = module()
    frozen = tmp_path / "frozen"
    schedule = item.freeze_module().freeze(frozen)
    assert schedule["schedule_sha256"] == item.SCHEDULE_SHA256
    assert item.admit_frozen_root(frozen)["geometry"]["endpoint_neutral_logical_cells"] == 64


def test_wave_caps_at_ten_and_replay_rejects_payload_tamper(monkeypatch, tmp_path):
    value = schedule()
    item, runtime = patch(monkeypatch, value)
    common = args(tmp_path)
    route = lambda _queue: ({"provider": "xai", "model": "grok-4.6-build", "tools": False}, {"proof": "p"})
    item.prepare_all(**common, route_provider=route)
    rows = asyncio.run(item.execute_wave(**common, allow_remote=True, route_provider=route))
    assert len(rows) == 64 and runtime.maximum == 10
    collector = tmp_path / "collector.json"
    assert item.finalize_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_output=collector, authorization_acknowledgement_sha256=ACK)["cells"] == 64
    assert item.replay_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector)["cells"] == 64
    value = json.loads(collector.read_text())
    value["cells"][0]["source_binding_sha256"] = "0" * 64
    collector.write_bytes(canonical(value))
    with pytest.raises(ValueError, match="collector payload"):
        item.replay_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector)


def test_projection_replays_exact_per_cell_scores_and_rejects_aggregate_tamper(monkeypatch, tmp_path):
    value = schedule()
    item, _runtime = patch(monkeypatch, value)
    common = args(tmp_path)
    route = lambda _queue: ({"provider": "xai", "model": "grok-4.6-build", "tools": False}, {"proof": "p"})
    item.prepare_all(**common, route_provider=route)
    asyncio.run(item.execute_wave(**common, allow_remote=True, route_provider=route))
    collector = tmp_path / "collector.json"
    item.finalize_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_output=collector, authorization_acknowledgement_sha256=ACK)
    projection = tmp_path / "grok.json"
    outcome = item.write_projection(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector, projection_output=projection)
    assert outcome["cells"] == 64 and item.replay_projection(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector, projection_path=projection)["endpoint"] == "grok-4.6"
    value = json.loads(projection.read_text())
    value["projections"] = [{"endpoint": "grok-4.6", "aggregate": 1}]
    projection.write_bytes(canonical(value))
    with pytest.raises(ValueError, match="endpoint projection set drifted"):
        item.replay_projection(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector, projection_path=projection)


def test_contract_keeps_exact_grok_route_and_no_fallback_or_resend():
    contract = json.loads((PACKAGE / "study-contract.json").read_text())
    assert contract["endpoint"] == {"max_concurrency": 10, "model": "grok-4.6-build", "provider": "xai", "reported_model": "grok-4.6-build", "tools": "disabled"}
    assert contract["lifecycle"] == {"fallback": "forbidden", "resend": "forbidden", "terminal_ambiguity": "reconcile_required", "transport": "pinned_confirmed_grok_lifecycle"}
