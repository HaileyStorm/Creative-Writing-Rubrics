from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-confirmation-grok-exec-v1"
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("_confirmation_grok_exec_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def schedule():
    cells = []
    for candidate in ("baseline", "candidate08"):
        for number in range(19):
            payload = f"prompt-{candidate}-{number}".encode()
            cells.append({"cell_id": f"{candidate[:1]}{number:031x}", "candidate_id": candidate, "item_id": f"item-{number:02d}", "prompt_group_id": f"group-{number % 8}", "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": __import__("hashlib").sha256(payload).hexdigest(), "target": {"dimension": number}})
    value = {"study_id": "hbq-human-alignment-optimizer-v5-f20-confirmation-freeze-v1", "cells": cells, "groups": [{"partition": "confirmation", "prompt_group_id": f"group-{number}"} for number in range(8)], "geometry": {"candidates": 2, "confirmation_groups": 8, "confirmation_items": 19, "endpoint_neutral_logical_cells": 38}, "authority": {"confirmation": {"status": "opened_by_this_frozen_schedule", "cells": 38}}}
    value["schedule_sha256"] = __import__("hashlib").sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    return value


class FakeFreeze:
    def __init__(self, value):
        self.value = value

    def validate_frozen_root(self, _root):
        return self.value


class FakeRuntime:
    def __init__(self):
        self.guard = threading.Lock()
        self.active = self.maximum = 0

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


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class FakeSource:
    STUDY_ID = "source"

    def __init__(self):
        self.schedule = None

    def live(self):
        return self

    def _route(self, queue_root, route_provider):
        if route_provider is None:
            return {"provider": "xai"}, {"proof": "p"}
        return route_provider(Path(queue_root))

    def prepare_all(self, *, output_root, queue_root, authorization_acknowledgement_sha256, route_provider, **_kwargs):
        _live, value = self.schedule()
        root = Path(output_root)
        root.mkdir()
        (root / ".claims").mkdir()
        (root / "schedule.json").write_bytes(canonical(value))
        for row in value["cells"]:
            route, evidence = route_provider(queue_root)
            cell = root / row["cell_id"]
            cell.mkdir()
            (cell / "prepared.json").write_bytes(canonical({"route": route, "route_evidence": evidence}))
            (cell / "authorization-acknowledgement.json").write_bytes(canonical({"acknowledgement_sha256": authorization_acknowledgement_sha256}))
        return {"prepared_cells": [row["cell_id"] for row in value["cells"]], "provider_calls_made": 0, "process_launches": 0}

    def execute_one(self, *, output_root, cell_id, **_kwargs):
        time.sleep(0.005)
        root = Path(output_root) / cell_id
        request = f"request-{cell_id}".encode()
        response = canonical({"requestId": f"request-{cell_id}", "sessionId": f"session-{cell_id}"})
        receipt = {"request": base64.b64encode(request).decode(), "response": base64.b64encode(response).decode(), "identity": {"request_id": f"request-{cell_id}", "session_id": f"session-{cell_id}"}, "settings": {"tools_enabled": False}}
        (root / "receipt.json").write_bytes(canonical(receipt))
        return {"cell_id": cell_id, "state": "provisional_scoring_received", "provider_calls_made": None, "process_launches": 1}

    def payload(self, row):
        raw = base64.b64decode(row["payload_base64"])
        return raw, raw, b"{}"

    def admit(self, root, _row, _schedule, _raw, _prompt, _schema, _route, _evidence, _ack, _live):
        receipt = json.loads((Path(root) / "receipt.json").read_text())
        return base64.b64decode(receipt["request"]), base64.b64decode(receipt["response"]), receipt["identity"], receipt["settings"]

    def validate_frozen_route(self, route, evidence):
        assert route == {"provider": "xai"} and evidence == {"proof": "p"}

    def _validate_runner_result(self, value, _route, _payload):
        return value["native_request_bytes"], value["native_response_bytes"], dict(value["identity"]), value["effective_settings"]


def patch(monkeypatch, value):
    source, runtime = FakeSource(), FakeRuntime()
    item = module()
    monkeypatch.setattr(item, "freeze_module", lambda: FakeFreeze(value))
    monkeypatch.setattr(item, "SCHEDULE_SHA256", value["schedule_sha256"])
    monkeypatch.setattr(item, "_runtime", lambda: runtime)
    monkeypatch.setattr(item, "bound_lifecycle", lambda frozen_root: _bound(item, source, value, runtime))
    return item, source, runtime


class _bound:
    def __init__(self, item, source, value, runtime):
        self.item, self.source, self.value, self.runtime = item, source, value, runtime

    def __enter__(self):
        self.before_schedule, self.before_study = self.source.schedule, self.source.STUDY_ID
        self.source.schedule = lambda **_ignored: (self.source, self.value)
        self.source.STUDY_ID = self.item.STUDY_ID
        return self.source, self.source, self.value, self.runtime

    def __exit__(self, *_error):
        self.source.schedule, self.source.STUDY_ID = self.before_schedule, self.before_study


def args(tmp_path):
    return {"output_root": tmp_path / "output", "frozen_root": tmp_path / "frozen", "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}


def test_prepare_uses_exact_38_cell_freeze_with_no_provider_calls(monkeypatch, tmp_path):
    value, item, _source, _runtime = schedule(), *patch(monkeypatch, schedule())
    outcome = item.prepare_all(**args(tmp_path), route_provider=lambda _queue: ({"provider": "xai"}, {"proof": "p"}))
    assert outcome["logical_cells"] == 38 and len(outcome["prepared_cells"]) == 38
    assert item.admit_frozen_root(tmp_path / "frozen") == value


def test_wave_caps_at_ten_and_loads_external_route_once(monkeypatch, tmp_path):
    item, _source, runtime = patch(monkeypatch, schedule())
    calls = {"count": 0}
    def route(_queue):
        calls["count"] += 1
        return {"provider": "xai"}, {"proof": "p"}
    item.prepare_all(**args(tmp_path), route_provider=route)
    rows = asyncio.run(item.execute_wave(**args(tmp_path), allow_remote=True, route_provider=route))
    assert len(rows) == 38 and calls["count"] == 2 and runtime.maximum == 10


def test_duplicate_cell_is_blocked_and_collector_replay_rejects_tamper(monkeypatch, tmp_path):
    item, _source, _runtime = patch(monkeypatch, schedule())
    common = args(tmp_path)
    item.prepare_all(**common)
    cell = schedule()["cells"][0]["cell_id"]
    assert item.execute_one(**common, cell_id=cell, allow_remote=True)["state"] == "provisional_scoring_received"
    assert item.execute_one(**common, cell_id=cell, allow_remote=True)["state"] == "claimed"
    asyncio.run(item.execute_wave(**common, allow_remote=True))
    collector = tmp_path / "collector.json"
    outcome = item.finalize_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_output=collector, authorization_acknowledgement_sha256=ACK)
    assert outcome["cells"] == 38 and item.replay_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector)["cells"] == 38
    value = json.loads(collector.read_text())
    value["cells"][0]["payload_sha256"] = "0" * 64
    collector.write_bytes(canonical(value))
    with pytest.raises(ValueError, match="collector payload"):
        item.replay_collector(output_root=common["output_root"], frozen_root=common["frozen_root"], collector_path=collector)


def test_reuses_pinned_v3_threadsafe_ten_process_regression():
    source = (ROOT / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_exec_v3_threadsafe_route_load.py").read_text(encoding="utf-8")
    assert "test_eleven_direct_processes_share_exact_ten_v3_slots" in source
    assert "MAX_CONCURRENCY = 10" in (PACKAGE / "executor.py").read_text(encoding="utf-8")
