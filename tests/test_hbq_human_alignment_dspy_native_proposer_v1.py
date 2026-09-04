from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dspy-native-proposer-v1"
V11_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v11_child20_train_screen_v1.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proposer():
    return _load(PACKAGE / "proposer.py", "native_dspy_proposer")


@pytest.fixture(scope="module")
def v11_train(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    fixture = _load(V11_TEST, "v11_train_fixture")
    study = fixture.module()
    root = tmp_path_factory.mktemp("native-dspy-v11") / "grok-train"
    common = {
        "output_root": root,
        "queue_root": root.parent / "queue",
        "authorization_acknowledgement_sha256": "a" * 64,
        "split_manifest": fixture.SPLIT,
        "hanna_csv": fixture.CSV,
        "successor_contract": fixture.CONTRACT,
        "route_provider": fixture.route_provider(),
    }
    prepared = study.prepare_all(**common)
    contacts: list[str] = []
    executed = study.execute_eight(**common, allow_remote=True, runner=fixture.native_runner(study, contacts))
    report = study.report(**{name: value for name, value in common.items() if name not in {"queue_root", "route_provider"}})
    assert prepared["logical_cells"] == len(executed) == len(contacts) == 8
    assert report["partition"] == "train" and report.get("confirmation") is None
    return {"root": root, "ack": common["authorization_acknowledgement_sha256"], "split": fixture.SPLIT, "csv": fixture.CSV, "contract": fixture.CONTRACT, "report": report}


def _route(_queue: Path):
    route = {
        "name": "grok-build-grok-4.6",
        "provider": "xai_grok_build",
        "model": "grok-4.6",
        "adapter": "grok_exec",
        "destination": "xai_grok_build_subscription",
    }
    evidence = {"route_name": route["name"], "route_sha256": "e" * 64}
    return SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), route, evidence


def _common(v11_train: dict[str, object], output_root: Path) -> dict[str, object]:
    queue_root = output_root.parent / "queue"
    queue_root.mkdir()
    return {
        "output_root": output_root,
        "v11_grok_root": v11_train["root"],
        "v11_acknowledgement_sha256": v11_train["ack"],
        "split_manifest": v11_train["split"],
        "hanna_csv": v11_train["csv"],
        "successor_contract": v11_train["contract"],
        "queue_root": queue_root,
    }


@pytest.mark.parametrize("live_turns", [4, 1, 3, 5])
def test_shared_live_route_is_copied_to_one_turn_without_mutation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, live_turns: int):
    value = proposer()
    adapter = tmp_path / "grok-adapter.py"
    capture = tmp_path / "capture.py"
    adapter.write_text("adapter", encoding="utf-8")
    capture.write_text("capture", encoding="utf-8")
    grok = SimpleNamespace(
        GROK_ADAPTER_PATH=adapter,
        GROK_ADAPTER_SHA256=value.sha256(adapter.read_bytes()),
        CAPTURE_WRAPPER_PATH=capture,
        CAPTURE_WRAPPER_SHA256=value.sha256(capture.read_bytes()),
    )
    live_route = {
        "name": "grok-build-grok-4.6",
        "provider": "xai_grok_build",
        "model": "grok-4.6",
        "adapter": "grok_exec",
        "destination": "xai_grok_build_subscription",
        "nonvisual_max_turns": live_turns,
        "command": ["fixture", str(adapter)],
    }
    evidence = {"route_name": live_route["name"], "route_sha256": "e" * 64}
    native = SimpleNamespace(
        validate_live_grok_route=lambda _queue: (live_route, evidence),
        _load_broker_class=lambda: lambda _queue: "broker",
    )
    loaded = iter((grok, SimpleNamespace(), native))
    monkeypatch.setattr(value, "_load", lambda *_args: next(loaded))
    if live_turns != 4:
        with pytest.raises(ValueError, match="shared route"):
            value._route(tmp_path / "queue")
        assert live_route["nonvisual_max_turns"] == live_turns
        return
    _grok, _heldout, broker, effective, returned_evidence = value._route(tmp_path / "queue")
    assert broker == "broker" and returned_evidence is evidence
    assert live_route["nonvisual_max_turns"] == 4
    assert effective == {**live_route, "nonvisual_max_turns": 1}


def test_train_diagnostics_reject_development_or_confirmation_rows(monkeypatch: pytest.MonkeyPatch, v11_train: dict[str, object]):
    value = proposer()
    original_load = value._load

    def reject(report: dict[str, object]) -> None:
        def fake_load(path: Path, expected_sha256: str, name: str):
            if Path(path) == value.V11_TRAIN:
                return SimpleNamespace(report=lambda **_kwargs: report)
            return original_load(path, expected_sha256, name)

        monkeypatch.setattr(value, "_load", fake_load)
        with pytest.raises(ValueError, match="TRAIN|train|confirmation|development"):
            value._training_report(
                v11_grok_root=v11_train["root"],
                v11_acknowledgement_sha256=v11_train["ack"],
                split_manifest=v11_train["split"],
                hanna_csv=v11_train["csv"],
                successor_contract=v11_train["contract"],
            )

    development = json.loads(json.dumps(v11_train["report"]))
    development["cells"][0]["partition"] = "development"
    reject(development)
    confirmation = json.loads(json.dumps(v11_train["report"]))
    confirmation["confirmation"] = {"status": "opened", "cells": 1}
    reject(confirmation)


def test_real_dspy_capture_freezes_train_payload_and_tamper_blocks_offline_replay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, v11_train: dict[str, object]):
    value = proposer()
    monkeypatch.setattr(value, "_route", _route)
    common = _common(v11_train, tmp_path / "prepared")
    prepared = value.prepare_one(**common)
    root = common["output_root"]
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    request = json.loads((root / "dspy-request.json").read_bytes())
    payload = (root / "prompt-request.bin").read_bytes()
    diagnostics, teaching_input = value._diagnostics(v11_train["report"])
    assert request["model"] == "grok-4.6" and request.get("tools") in (None, [])
    assert payload == value.canonical(request)
    assert diagnostics["train_partition"] == teaching_input["partition"] == "train"
    assert len(teaching_input["examples"]) == 4
    assert all(set(row) == {"cell_id", "prompt_group_id", "scores", "target", "errors"} for row in teaching_input["examples"])
    assert value.verify_prepared(**{name: item for name, item in common.items() if name != "queue_root"})["provider_calls_made"] == 0
    request = json.loads((root / "dspy-request.json").read_bytes())
    request["messages"].append({"role": "user", "content": "forged request"})
    payload = value.canonical(request)
    disclosure = json.loads((root / "disclosure.json").read_bytes())
    disclosure["payload"] = {"bytes": len(payload), "sha256": value.sha256(payload), "text": payload.decode("utf-8")}
    stored = json.loads((root / "prepared.json").read_bytes())
    stored["dspy_request_sha256"] = stored["payload_sha256"] = value.sha256(payload)
    stored["disclosure_sha256"] = value.sha256(value.canonical(disclosure))
    (root / "dspy-request.json").write_bytes(payload)
    (root / "prompt-request.bin").write_bytes(payload)
    (root / "disclosure.json").write_bytes(value.canonical(disclosure))
    (root / "prepared.json").write_bytes(value.canonical(stored))
    with pytest.raises(ValueError):
        value.verify_prepared(**{name: item for name, item in common.items() if name != "queue_root"})
    acknowledgement = {
        "format_version": 1,
        "study_id": value.STUDY_ID,
        "kind": "authorization_acknowledgement_reference",
        "cell_id": value.STUDY_ID,
        "disclosure_sha256": value.sha256(value.canonical(disclosure)),
        "acknowledgement_sha256": "a" * 64,
    }
    acknowledgement_path = tmp_path / "acknowledgement.json"
    acknowledgement_path.write_bytes(value.canonical(acknowledgement))
    value.bind_authorization(output_root=root, acknowledgement_path=acknowledgement_path)
    routes: list[str] = []
    monkeypatch.setattr(value, "_route", lambda _queue: routes.append("route"))
    with pytest.raises(ValueError):
        value.execute_one(allow_remote=True, **common)
    assert routes == []
    assert {path.name for path in root.iterdir()} == value.BOUND_FILES


def test_one_fake_native_command_replays_bytes_parses_and_validates_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, v11_train: dict[str, object]):
    value = proposer()
    common = _common(v11_train, tmp_path / "prepared")
    calls: list[bytes] = []
    route = _route(common["queue_root"])[3]
    evidence = _route(common["queue_root"])[4]

    def invoke(_grok, _broker, received_route, payload: bytes, schema: dict[str, object], capture: Path):
        assert received_route == route
        assert schema == json.loads(value._schema().decode("utf-8"))
        calls.append(payload)
        output = {"completion": "[[ ## descendant_instruction ## ]]\nRequire each score to name a concrete supporting passage from the submitted story.\n\n[[ ## completed ## ]]"}
        runtime = {
            "requested_model": "grok-4.6",
            "reported_model": "grok-4.6-build",
            "requested_reasoning_effort": "high",
            "nonvisual_max_turns": 1,
            "observed_turns": 1,
        }
        control = {"control": {"version": 1, "state": "completed"}, "result": {"output": output, "output_hash": value.sha256(value.canonical(output)), "runtime": runtime}}
        raw = value.canonical(control)
        capture.write_bytes(raw)
        return SimpleNamespace(state="completed", detail=None), raw

    heldout = SimpleNamespace(_grok_invoke=invoke)
    monkeypatch.setattr(value, "_route", lambda _queue: (SimpleNamespace(), heldout, SimpleNamespace(), route, evidence))
    value.prepare_one(**common)
    root = common["output_root"]
    disclosure = json.loads((root / "disclosure.json").read_bytes())
    acknowledgement = {
        "format_version": 1,
        "study_id": value.STUDY_ID,
        "kind": "authorization_acknowledgement_reference",
        "cell_id": value.STUDY_ID,
        "disclosure_sha256": value.sha256(value.canonical(disclosure)),
        "acknowledgement_sha256": "b" * 64,
    }
    acknowledgement_path = tmp_path / "acknowledgement.json"
    acknowledgement_path.write_bytes(value.canonical(acknowledgement))
    value.bind_authorization(output_root=root, acknowledgement_path=acknowledgement_path)
    result = value.execute_one(allow_remote=True, **common)
    assert result.get("state") == "native_descendant_received", result
    assert calls == [(root / "prompt-request.bin").read_bytes()]
    receipt = json.loads((root / "execution-receipt.json").read_bytes())
    descendant = json.loads((root / "result.json").read_bytes())["descendant"]
    assert receipt["native_endpoint_contact_cardinality"] == "unproven"
    assert base64.b64decode(descendant["profile_base64"], validate=True) == value._parent()["profile_bytes"]
    with pytest.raises(ValueError, match="cannot resend"):
        value.execute_one(allow_remote=True, **common)
    assert len(calls) == 1
