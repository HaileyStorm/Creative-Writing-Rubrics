from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v11-train-sol-exec-v1"
GROK_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-v11-train-grok-dc7b59a-20260904-r1")
V9_SOL_ROOT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-sol-veto-926f8f1-20260901a")
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
GROK_ACK = "035a88b2e2aef5bc2ae1cab50e70cc3a09c42fc4112321e40760bc29042ab1e2"
ACK = "a" * 64


def module():
    if not GROK_ROOT.is_dir():
        pytest.skip("frozen V11 Grok receipt root is not available")
    spec = importlib.util.spec_from_file_location("v11_train_sol_exec", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def source_args() -> dict[str, Path | str]:
    return {
        "grok_root": GROK_ROOT,
        "grok_acknowledgement": GROK_ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
    }


def _route_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    proofs = list(V9_SOL_ROOT.rglob("zero-charge-route-proof.json"))
    if not proofs:
        pytest.skip("pinned V9 Sol route fixture is not available")
    proof = json.loads(proofs[0].read_text(encoding="utf-8"))
    route = copy.deepcopy(proof["route"])
    evidence = copy.deepcopy(proof["route_evidence"])
    now = datetime.now(timezone.utc)
    route["cost_evidence"]["checked_at"] = (now - timedelta(minutes=1)).isoformat()
    route["cost_evidence"]["expires_at"] = (now + timedelta(minutes=10)).isoformat()
    evidence["cost_evidence_checked_at"] = route["cost_evidence"]["checked_at"]
    evidence["cost_evidence_expires_at"] = route["cost_evidence"]["expires_at"]
    evidence["route_sha256"] = _sha(route)
    return route, evidence


def _sha(value: bytes | Any) -> str:
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


class _FakeBroker:
    def __init__(self, route: dict[str, Any]) -> None:
        self.route = route

    def _load_registry_live(self) -> dict[str, Any]:
        return {"version": 1, "routes": [self.route]}

    def _validate_route(self, candidate: dict[str, Any], *, verify_command_identity: bool, validate_current_evidence: bool) -> None:
        assert candidate == self.route
        assert verify_command_identity is True and validate_current_evidence is True


def broker_factory(route: dict[str, Any]):
    return lambda _root: _FakeBroker(route)


def _call_args(mod, tmp_path: Path, *, route: dict[str, Any] | None = None) -> dict[str, Any]:
    route = route or _route_fixture()[0]
    return {
        **source_args(),
        "output_root": tmp_path / "sol-output",
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
        "broker_factory": broker_factory(route),
    }


def _answer(mod, *, index: int) -> dict[str, Any]:
    score = float(1 + index % 4)
    return {
        "scores": {name: score for name in mod.DIMS},
        "evidence": {name: f"The submitted story grounds the {name} judgment." for name in mod.DIMS},
        "coverage": {name: (name != "Complexity") for name in mod.DIMS},
    }


def fake_codex(mod, calls: list[str], callback_snapshots: list[set[str]]):
    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        token = root.name
        index = int(token[-1], 16) % 8
        responses = root / "responses"
        responses.mkdir(exist_ok=True)
        callback_snapshots.append({path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()})
        kwargs["before_provider_attempt"]()
        answer = _answer(mod, index=index)
        final = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        events = b"".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
            for event in (
                {"type": "thread.started", "thread_id": f"fixture-thread-{token}"},
                {"type": "turn.started"},
                {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}},
                {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
                {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}},
            )
        )
        events_path = responses / "batch-0001.attempt-0001.events.jsonl"
        message_path = responses / "batch-0001.attempt-0001.message.json"
        stderr_path = root / "raw-codex-stderr.bin"
        events_path.write_bytes(events)
        message_path.write_text(final, encoding="utf-8")
        stderr_path.write_bytes(b"")
        calls.append(token)
        v3_spec = importlib.util.spec_from_file_location(
            "v11_native_codex_fixture", ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
        )
        assert v3_spec and v3_spec.loader
        v3 = importlib.util.module_from_spec(v3_spec)
        v3_spec.loader.exec_module(v3)
        command = v3._expected_codex_command(kwargs["executable"], root)
        return final, {
            "command": command,
            "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{token}"},
            "provider_artifacts": {
                "codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": mod.sha256(events)},
                "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": mod.sha256(b"")},
            },
        }

    return invoke


def _report_args(common: dict[str, Any]) -> dict[str, Any]:
    return {key: common[key] for key in (*source_args(), "output_root", "authorization_acknowledgement_sha256")}


def test_contract_and_grok_rows_preserve_exact_eight_payloads_without_targets() -> None:
    mod = module()
    contract = mod.validate_package()
    assert contract["geometry"] == {"candidates": 2, "groups": 4, "items": 4, "max_concurrency": 8, "sol_cells": 8}
    assert mod.SOURCE_SHA256 == "af2d326934f51ddb83b6449a760295f46921c87189c653558de37930af018f11"
    assert mod.GROK_RESULT_SHA256 == "6366de64754c365c4d91a9117d8c174f771ad50062ef342f11996cddfa78c58e"
    resolution = mod._resolution(**source_args())
    rows = resolution["rows"]
    source_cells = {row["cell_id"]: row for row in resolution["schedule"]["cells"]}
    grok_cells = {row["cell_id"]: row for row in resolution["grok_result"]["cells"]}
    assert len(rows) == len(source_cells) == len(grok_cells) == 8
    assert {row["candidate_id"] for row in rows} == {mod.BASELINE, mod.CHILD20}
    assert {row["partition"] for row in rows} == {"train"}
    for row in rows:
        source = source_cells[row["source_cell_id"]]
        assert base64.b64decode(row["payload_base64"], validate=True) == base64.b64decode(source["payload_base64"], validate=True)
        native_request = (GROK_ROOT / row["source_cell_id"] / "native-request.bin").read_bytes()
        assert row["payload_sha256"] == source["payload_sha256"]
        assert json.loads(native_request)["prompt"].encode("utf-8") == base64.b64decode(row["payload_base64"], validate=True)
        assert _sha(native_request) == grok_cells[row["source_cell_id"]]["native_request_sha256"]
        prompt = json.loads(base64.b64decode(row["payload_base64"]))
        assert "target" not in prompt


def test_prepare_all_uses_real_lower_lifecycle_and_makes_zero_contacts(tmp_path: Path) -> None:
    mod = module()
    common = _call_args(mod, tmp_path)
    queue = common["queue_root"]
    queue.mkdir()
    result = mod.prepare_all(**common)
    assert result == {"study_id": mod.STUDY_ID, "state": "prepared_exact_8_matched_sol_train_cells", "cells": 8, "groups": 4, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": 8}
    assert {path.name for path in common["output_root"].iterdir()} == {row["cell_id"] for row in mod._resolution(**source_args())["rows"]}
    for root in common["output_root"].iterdir():
        prepared = json.loads((root / "prepared.json").read_text(encoding="utf-8"))
        assert prepared["source"]["sol_role"] == "matched_measurement_only_after_grok_gate"
        assert prepared["source"]["endpoint_pooling"] == "forbidden"
        assert prepared["source"]["promotion"] == "none"


def test_execute_wave_persists_eight_receipts_metrics_and_never_resends_or_mutates(tmp_path: Path) -> None:
    mod = module()
    route, _evidence = _route_fixture()
    common = _call_args(mod, tmp_path, route=route)
    common["queue_root"].mkdir()
    mod.prepare_all(**common)
    calls: list[str] = []
    callback_snapshots: list[set[str]] = []
    results = mod.execute_wave(**common, allow_remote=True, call_codex=fake_codex(mod, calls, callback_snapshots))
    assert len(results) == len(calls) == len(callback_snapshots) == 8
    assert all(not any(path.startswith("responses/") for path in snapshot) for snapshot in callback_snapshots)
    assert all(result["state"] == "local_codex_lifecycle_received_native_contact_unproven" for result in results), results
    report = mod.report(**_report_args(common))
    assert report["endpoint"] == "sol_later" and report["partition"] == "train"
    assert len(report["cells"]) == report["unique_thread_ids"] == report["unique_session_ids"] == 8
    assert all(type(cell["scores"][name]) is float for cell in report["cells"] for name in mod.DIMS)
    assert any(cell["coverage"]["Complexity"] is False for cell in report["cells"])
    assert report["authority"] == {"confirmation": "none", "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"}
    expected_mae: dict[str, float] = {}
    for row in mod._resolution(**source_args())["rows"]:
        receipt = json.loads((common["output_root"] / row["cell_id"] / "execution-receipt.json").read_text(encoding="utf-8"))
        projection = receipt["human_score_projection"]
        assert all(type(projection["scores"][name]) in {int, float} for name in mod.DIMS)
        assert all(type(projection["coverage"][name]) is bool for name in mod.DIMS)
        expected_mae[row["cell_id"]] = sum(abs(float(projection["scores"][name]) - row["target"][name]) for name in mod.DIMS) / len(mod.DIMS)
    assert {cell["cell_id"]: cell["mae"] for cell in report["cells"]} == expected_mae
    before = {path.relative_to(common["output_root"]).as_posix(): _sha(path.read_bytes()) for path in common["output_root"].rglob("*") if path.is_file()}
    call_count_before = len(calls)

    def must_not_run(**_kwargs: Any):
        raise AssertionError("rerun invoked fake Codex")

    with pytest.raises(ValueError, match="root inventory|terminal evidence|no resend"):
        mod.execute_wave(**common, allow_remote=True, call_codex=must_not_run)
    after = {path.relative_to(common["output_root"]).as_posix(): _sha(path.read_bytes()) for path in common["output_root"].rglob("*") if path.is_file()}
    assert after == before and len(calls) == call_count_before

    original_runtime = mod._runtime
    for identity_field in ("thread_id", "session_id"):
        count = 0
        first_identity_value: str | None = None

        def collided_runtime(resolution, *, _field=identity_field):
            nonlocal count, first_identity_value
            lifecycle, runtime = original_runtime(resolution)
            original_admit = lifecycle._admit_completed_cell

            def admit(*args: Any, **kwargs: Any):
                nonlocal count, first_identity_value
                result = original_admit(*args, **kwargs)
                count += 1
                identity = dict(result["identity"])
                if count == 1:
                    first_identity_value = identity[_field]
                if count == 2:
                    identity[_field] = first_identity_value
                    result = dict(result)
                    result["identity"] = identity
                return result

            lifecycle._admit_completed_cell = admit
            return lifecycle, runtime

        mod._runtime = collided_runtime
        try:
            with pytest.raises(ValueError, match="duplicate or invalid Sol identity"):
                mod.report(**_report_args(common))
        finally:
            mod._runtime = original_runtime

    count = 0

    def mixed_runtime(resolution):
        nonlocal count
        lifecycle, runtime = original_runtime(resolution)
        original_admit = lifecycle._admit_completed_cell

        def admit(*args: Any, **kwargs: Any):
            nonlocal count
            result = original_admit(*args, **kwargs)
            count += 1
            if count == 2:
                result = dict(result)
                mixed = dict(result["route"])
                mixed["name"] = "mixed-route"
                result["route"] = mixed
            return result

        lifecycle._admit_completed_cell = admit
        return lifecycle, runtime

    mod._runtime = mixed_runtime
    try:
        with pytest.raises(ValueError, match="mixed Sol route or evidence"):
            mod.report(**_report_args(common))
    finally:
        mod._runtime = original_runtime


def test_grok_qualification_failure_fails_before_route_or_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = module()
    route_calls: list[str] = []
    contact_calls: list[str] = []
    monkeypatch.setattr(mod, "_resolution", lambda **_kwargs: (_ for _ in ()).throw(ValueError("Grok result does not open matched Sol-8 measurement")))

    def no_route(_root: Path):
        route_calls.append("route")
        raise AssertionError("route was consulted after failed Grok qualification")

    def no_contact(**_kwargs: Any):
        contact_calls.append("contact")
        raise AssertionError("Codex was contacted after failed Grok qualification")

    queue = tmp_path / "queue"
    queue.mkdir()
    args = {
        **source_args(),
        "output_root": tmp_path / "output",
        "queue_root": queue,
        "authorization_acknowledgement_sha256": ACK,
        "broker_factory": no_route,
    }
    with pytest.raises(ValueError, match="Grok result does not open matched Sol-8 measurement"):
        mod.prepare_all(**args)
    assert not args["output_root"].exists() and route_calls == contact_calls == []
    with pytest.raises(ValueError, match="Grok result does not open matched Sol-8 measurement"):
        mod.execute_one(**args, cell_id="unknown", allow_remote=True, call_codex=no_contact)
    assert route_calls == contact_calls == []
