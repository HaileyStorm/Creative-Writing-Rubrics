from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_parallel_execution_v1.py"
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load():
    spec = importlib.util.spec_from_file_location("parallel", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path, monkeypatch):
    module = load()
    paths = [
        tmp_path / name for name in ("plan", "original", "replacement", "queue", "old")
    ]
    for path in paths:
        path.mkdir()
    marker = paths[-1] / "requests/0829/handoff-stop.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "evidence_class": "intentional_precontact_parallel_handoff",
                "boundary_ordinal": 829,
                "expected_accepted_prefix_through": 828,
                "new_execution_concurrency": 10,
                "consumed_request": False,
                "resend_authority": False,
                "restart_old_collector": False,
            }
        )
    )
    identity = {"model": "gpt-5.6-sol"}
    route = {**identity, "codex_command": ["native"]}

    def request_payload(_plan, ordinal):
        prompt, schema = f"prompt-{ordinal}".encode(), b"{}"
        return (
            {
                "ordinal": ordinal,
                "batch_number": ordinal - 759,
                "prompt_sha256": sha(prompt),
                "schema_sha256": sha(schema),
            },
            prompt,
            schema,
        )

    def validate_native(_slot, request, _route, raw, _record):
        value = json.loads(raw)
        return {
            "thread_id": value.get("thread_id", f"thread-{request['ordinal']}"),
            "response_sha256": sha(raw),
            "verdicts": [],
        }

    def accepted(_helper, slot, _request, _manifest_sha, _identity, threads):
        terminal_path = slot / "terminal.json"
        if not terminal_path.exists():
            raise ValueError("ambiguous slot")
        terminal = json.loads(terminal_path.read_bytes())
        if terminal.get("state") != "accepted" or terminal["thread_id"] in threads:
            raise ValueError("retained terminal differs")
        threads.add(terminal["thread_id"])
        return {"thread_id": terminal["thread_id"], "verdicts": []}

    helper = SimpleNamespace(
        request_payload=request_payload,
        route_snapshot=lambda *_: dict(route),
        validate_native=validate_native,
    )
    old = SimpleNamespace(_accepted=accepted)
    for name in ("HELPER_PATH", "OLD_PATH"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        monkeypatch.setattr(module, name, path)
        monkeypatch.setattr(
            module,
            "HELPER_SHA" if name == "HELPER_PATH" else "OLD_SHA",
            sha(path.read_bytes()),
        )
    driver = tmp_path / "driver.py"
    driver.write_bytes(b"driver")
    monkeypatch.setattr(module, "__file__", str(driver))
    monkeypatch.setattr(module, "HANDOFF_SHA", sha(marker.read_bytes()))
    monkeypatch.setattr(module, "CAMPAIGN_ROOT", tmp_path / "parallel")
    monkeypatch.setattr(
        module, "_load", lambda path, *_: helper if path == module.HELPER_PATH else old
    )
    monkeypatch.setattr(
        module,
        "_prefix",
        lambda *_: {
            "through_ordinal": 828,
            "verdict_count": 6408,
            "thread_ids": ["prior"],
            "route_identity": identity,
        },
    )
    return SimpleNamespace(
        module=module,
        args=(*paths, marker),
        helper=helper,
        route=route,
        driver=driver,
        marker=marker,
        root=module.CAMPAIGN_ROOT,
    )


class Adapter:
    def __init__(
        self, *, barrier=None, fail=None, before_gate=None, stop=None, collision=False
    ):
        self.barrier = threading.Barrier(barrier) if barrier else None
        self.fail, self.before_gate, self.stop, self.collision = (
            fail,
            before_gate,
            stop,
            collision,
        )
        self.calls, self.active, self.maximum = [], 0, 0
        self.lock = threading.Lock()

    def call_codex(self, **kwargs):
        if self.before_gate:
            self.before_gate(kwargs)
        kwargs["before_provider_attempt"]()
        ordinal = int(kwargs["output_dir"].name)
        with self.lock:
            self.calls.append((ordinal, kwargs["batch_number"]))
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            if self.barrier:
                self.barrier.wait(timeout=10)
            if self.stop:
                self.stop.touch()
            if ordinal == self.fail:
                raise RuntimeError("synthetic failure")
            time.sleep(0.03)
            return json.dumps({"thread_id": "duplicate"} if self.collision else {}), {}
        finally:
            with self.lock:
                self.active -= 1


def test_ten_overlapping_calls_use_unique_frozen_ordinals(case):
    adapter = Adapter(barrier=10)
    result = case.module.collect(
        *case.args, through_ordinal=838, adapter_override=adapter
    )
    assert result["state"] == "collected"
    assert adapter.maximum == 10 and adapter.active == 0
    assert sorted(adapter.calls) == [
        (ordinal, ordinal - 759) for ordinal in range(829, 839)
    ]
    assert result["completed_ordinals"] == list(range(829, 839))


def test_failure_stops_replenishment_and_drains_calls(case):
    adapter = Adapter(barrier=10, fail=831)
    result = case.module.collect(
        *case.args, through_ordinal=848, adapter_override=adapter
    )
    assert result["state"] == "stopped_no_retry"
    assert len(adapter.calls) == 10 and adapter.active == 0
    assert result["failures"] == [{"ordinal": 831, "error_type": "RuntimeError"}]
    assert len(result["completed_ordinals"]) == 9
    retry = Adapter()
    with pytest.raises(ValueError):
        case.module.collect(*case.args, through_ordinal=848, adapter_override=retry)
    assert not retry.calls


@pytest.mark.parametrize("terminal", [None, {"state": "stopped_no_retry"}])
def test_later_failure_or_ambiguity_blocks_new_gap_before_contact(case, terminal):
    case.module.collect(*case.args, through_ordinal=829, adapter_override=Adapter())
    slot = case.root / "requests/0840"
    slot.mkdir()
    if terminal is not None:
        (slot / "terminal.json").write_text(json.dumps(terminal))
    adapter = Adapter()
    with pytest.raises(ValueError):
        case.module.collect(*case.args, through_ordinal=848, adapter_override=adapter)
    assert not adapter.calls and not (case.root / "requests/0830").exists()


@pytest.mark.parametrize("changed", ["driver", "helper", "route", "payload"])
def test_binding_drift_stops_before_contact(case, changed):
    def change(kwargs):
        if changed == "driver":
            case.driver.write_bytes(b"changed")
        elif changed == "helper":
            case.module.HELPER_PATH.write_bytes(b"changed")
        elif changed == "route":
            case.route["extra"] = True
        else:
            kwargs["response_schema"].write_bytes(b"changed")

    adapter = Adapter(before_gate=change)
    result = case.module.collect(
        *case.args, through_ordinal=829, adapter_override=adapter
    )
    assert result["state"] == "stopped_no_retry" and not adapter.calls


def test_thread_collision_is_retained_failure(case):
    adapter = Adapter(barrier=2, collision=True)
    result = case.module.collect(
        *case.args, through_ordinal=830, adapter_override=adapter
    )
    assert (
        result["state"] == "stopped_no_retry" and len(result["completed_ordinals"]) == 1
    )
    assert len(result["failures"]) == 1


def test_control_drains_and_resume_skips_accepted_slots(case, tmp_path):
    stop = tmp_path / "stop"
    adapter = Adapter(barrier=10, stop=stop)
    result = case.module.collect(
        *case.args, through_ordinal=848, adapter_override=adapter, stop_path=stop
    )
    assert result["state"] == "stopped_by_control" and adapter.active == 0
    assert result["completed_ordinals"] == list(range(829, 839))
    stop.unlink()
    resumed = Adapter(barrier=10)
    result = case.module.collect(
        *case.args, through_ordinal=848, adapter_override=resumed, stop_path=stop
    )
    assert result["state"] == "collected"
    assert [ordinal for ordinal, _ in sorted(resumed.calls)] == list(range(839, 849))


def test_handoff_extra_file_prevents_contact(case):
    (case.marker.parent / "start.json").write_text("{}")
    adapter = Adapter()
    with pytest.raises(ValueError, match="handoff slot contacted"):
        case.module.collect(*case.args, through_ordinal=829, adapter_override=adapter)
    assert not adapter.calls
