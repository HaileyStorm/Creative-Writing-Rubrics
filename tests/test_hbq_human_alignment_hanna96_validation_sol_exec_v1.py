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
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-sol-exec-v1"
FREEZE = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
ANALYZER = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-analysis-v1" / "analyze.py"
ACK = "a" * 64
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module():
    spec = importlib.util.spec_from_file_location("_fresh96_sol_exec", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def schedule(value):
    cells = []
    for index in range(32):
        item = f"item-{index:02d}"
        for candidate in (value.BASELINE, value.DESCENDANT):
            payload = value.canonical({"study_id": value.FREEZE_ID, "candidate_id": candidate, "item_id": item, "response_schema": {"type": "object"}})
            target = {dimension: 2.0 for dimension in DIMENSIONS}
            cells.append({"cell_id": f"neutral-{candidate[-4:]}-{item}", "candidate_id": candidate, "prompt_group_id": f"group-{index // 2:02d}", "item_id": item,
                          "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": hashlib.sha256(payload).hexdigest(),
                          "source_binding_sha256": f"{index + 1:064x}", "target": target, "target_sha256": value.sha256(target)})
    result = {"study_id": value.FREEZE_ID, "geometry": {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}, "source": {"fresh96_manifest_sha256": "f" * 64}, "cells": cells}
    result["schedule_sha256"] = value.sha256(result)
    return result


class FakeBase:
    def __init__(self, counter=None):
        self.route_calls = 0
        self.counter = counter

    def _route(self, _queue, _factory):
        self.route_calls += 1
        return {"name": "fixture", "destination": "fixture", "codex_command": ["fixture"]}, {"fixture": True}, None

    @staticmethod
    def canonical(value):
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    @staticmethod
    def _write_new(path, raw):
        path.write_bytes(raw)

    def _prepared(self, row, payload, schema, target, route, evidence, acknowledgement):
        disclosure = {"cell": row["cell_id"]}
        target_file = {"hanna_csv_sha256": "old", "target": target}
        prepared = {"source": {}, "target_vector_sha256": "old"}
        return {"outbound-payload.json": payload, "response-schema.json": schema, "target-vector.json": self.canonical(target_file), "disclosure.json": self.canonical(disclosure),
                "authorization-acknowledgement.json": self.canonical({"ack": acknowledgement}), "zero-charge-route-proof.json": self.canonical({"route": route}), "prepared.json": self.canonical(prepared)}

    def execute_one(self, **kwargs):
        if self.counter:
            with self.counter["lock"]:
                self.counter["active"] += 1
                self.counter["maximum"] = max(self.counter["maximum"], self.counter["active"])
            time.sleep(0.01)
            with self.counter["lock"]:
                self.counter["active"] -= 1
        return {"cell_id": kwargs["cell_id"], "state": "fixture"}


def resolved(value):
    source = schedule(value)
    return {"schedule": source, "schedule_file_sha256": value.sha256(value.canonical(source)), "schedule_sha256": source["schedule_sha256"], "rows": value._rows(source)}


def configure(value, monkeypatch, *, counter=None):
    result = resolved(value)
    base = FakeBase(counter)
    monkeypatch.setattr(value, "_resolve", lambda *, frozen_root: result)
    monkeypatch.setattr(value, "_configured_base", lambda _resolution: base)
    return result, base


def test_rows_preserve_all_64_endpoint_neutral_payload_bytes():
    value = module()
    source = schedule(value)
    rows = value._rows(source)
    assert len(rows) == 64
    assert len({row["item_id"] for row in rows}) == 32
    assert len({row["prompt_group_id"] for row in rows}) == 16
    original = {cell["cell_id"]: cell for cell in source["cells"]}
    assert all(base64.b64decode(row["payload_base64"]) == base64.b64decode(original[row["source_cell_id"]]["payload_base64"]) for row in rows)


def test_rows_reject_tampered_payload_or_pairing():
    value = module()
    source = schedule(value)
    source["cells"][0]["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="payload"):
        value._rows(source)
    source = schedule(value)
    source["cells"][0]["candidate_id"] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        value._rows(source)


def test_prepare_has_zero_contact_and_writes_exact_payloads(tmp_path, monkeypatch):
    value = module()
    result, base = configure(value, monkeypatch)
    frozen, queue, output = tmp_path / "frozen", tmp_path / "queue", tmp_path / "output"
    frozen.mkdir(); queue.mkdir()
    actual = value.prepare_all(output_root=output, frozen_root=frozen, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    assert actual["cells"] == 64 and actual["provider_calls_made"] == 0 and actual["process_launches"] == 0
    assert base.route_calls == 1
    for row in result["rows"]:
        assert (output / row["cell_id"] / "outbound-payload.json").read_bytes() == base64.b64decode(row["payload_base64"])


def test_wave_has_two_lanes_and_rejects_terminal_resend(tmp_path, monkeypatch):
    value = module()
    counter = {"active": 0, "maximum": 0, "lock": threading.Lock()}
    result, _base = configure(value, monkeypatch, counter=counter)
    frozen, queue, output = tmp_path / "frozen", tmp_path / "queue", tmp_path / "output"
    frozen.mkdir(); queue.mkdir()
    value.prepare_all(output_root=output, frozen_root=frozen, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    values = value.execute_wave(output_root=output, frozen_root=frozen, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)
    assert len(values) == 64 and counter["maximum"] == 2
    root = output / result["rows"][0]["cell_id"]
    (root / "launch-intent.json").write_text("{}", encoding="utf-8")
    locks = value._locks(output)
    try:
        with pytest.raises(ValueError, match="no resend"):
            value._claim(locks, root, result["rows"][0]["cell_id"])
    finally:
        if locks.exists():
            for child in locks.iterdir(): child.unlink()
            locks.rmdir()


def test_reconcile_reports_ambiguity_without_requeue(tmp_path, monkeypatch):
    value = module()
    result, _base = configure(value, monkeypatch)
    frozen, output = tmp_path / "frozen", tmp_path / "output"
    frozen.mkdir(); output.mkdir()
    cell = output / result["rows"][0]["cell_id"]; cell.mkdir()
    (cell / "result.json").write_bytes(value.canonical({"kind": "reconcile_required_after_process_launch"}))
    state = value.reconcile_all(output_root=output, frozen_root=frozen, authorization_acknowledgement_sha256=ACK)
    assert state["state"] == "reconcile_required" and state["provider_calls_made"] == 0 and state["action"] == "no_requeue_or_resend"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_projection_writer_replays_sealed_freeze_and_analyzer_schema(tmp_path, monkeypatch):
    value = module()
    freeze, analyzer = load(FREEZE, "fresh96_freeze_for_sol"), load(ANALYZER, "fresh96_analyzer_for_sol")
    frozen, execution, published = tmp_path / "frozen", tmp_path / "execution", tmp_path / "published"
    freeze.freeze(frozen); execution.mkdir(); published.mkdir()
    resolution = value._resolve(frozen_root=frozen)

    class ProjectionBase:
        @staticmethod
        def stable(path): return Path(path).read_bytes()
        @staticmethod
        def _json(path, _label): return json.loads(Path(path).read_text(encoding="utf-8"))
        @staticmethod
        def _canonical_json(path, _label):
            raw = Path(path).read_bytes(); parsed = json.loads(raw)
            assert raw == value.canonical(parsed)
            return parsed
        @staticmethod
        def _inventory(root, *, completed):
            assert completed and {path.name for path in root.iterdir()} == {"authorization-acknowledgement.json", "disclosure.json", "execution-receipt.json", "outbound-payload.json", "prepared.json", "raw-codex-final-response.bin", "response-schema.json", "target-vector.json", "zero-charge-route-proof.json"}
        @staticmethod
        def _validate_answer(answer):
            assert set(answer) == {"scores", "evidence", "coverage"}
            return answer
        @staticmethod
        def _prepared(row, payload, schema, target, route, evidence, acknowledgement):
            target_file = {"target": target, "source_binding_sha256": row["source_binding_sha256"]}
            prepared = {"route_evidence": evidence, "cell": row, "task_payload_sha256": value.sha256(payload), "response_schema_sha256": value.sha256(schema)}
            return {"outbound-payload.json": payload, "response-schema.json": schema, "target-vector.json": value.canonical(target_file), "disclosure.json": value.canonical({"cell_id": row["cell_id"]}), "authorization-acknowledgement.json": value.canonical({"acknowledgement_sha256": acknowledgement}), "zero-charge-route-proof.json": value.canonical({"route": route}), "prepared.json": value.canonical(prepared)}

    base = ProjectionBase()
    monkeypatch.setattr(value, "_configured_base", lambda _resolution: base)
    route, evidence = {"name": "fixture"}, {"fixture": True}
    for index, row in enumerate(resolution["rows"]):
        root = execution / row["cell_id"]; root.mkdir()
        payload = base64.b64decode(row["payload_base64"])
        schema = value.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in base._prepared(row, payload, schema, row["target"], route, evidence, ACK).items():
            (root / name).write_bytes(raw)
        answer = {"scores": row["target"], "evidence": {dimension: "fixture" for dimension in DIMENSIONS}, "coverage": {dimension: True for dimension in DIMENSIONS}}
        (root / "raw-codex-final-response.bin").write_bytes(value.canonical(answer))
        identity = {"thread_id": f"thread-{index}", "session_id": f"session-{index}", "contact_id": f"contact-{index}", "effective_model": "gpt-5.6-sol", "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high"}
        receipt = {"cell": row, "study_id": value.STUDY_ID, "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "request_sha256": value.sha256(payload), "response_schema_sha256": value.sha256(schema), "human_score_projection": answer, "identity": identity}
        (root / "execution-receipt.json").write_bytes(value.canonical(receipt))
    path = published / "sol.json"
    written = value.write_projection_set(projection_output=path, output_root=execution, frozen_root=frozen, authorization_acknowledgement_sha256=ACK)
    assert written["schedule_sha256"] == freeze.build()["schedule_sha256"] == "639c34bb1d07266759280249b6b74a51c05d51f60ed27eb3aed0b2ea6c3bfee2"
    assert [row["cell_id"] for row in written["projections"]] == sorted(row["cell_id"] for row in freeze.build()["cells"])
    assert value.replay_projection_set(projection_path=path, output_root=execution, frozen_root=frozen, authorization_acknowledgement_sha256=ACK) == written
    analyzer.EXPECTED_EXECUTOR_BINDINGS["gpt-5.6-sol"] = written["executor_binding"]
    grok = dict(written); grok["endpoint"] = "grok-4.6"; grok["executor_binding"] = analyzer.EXPECTED_EXECUTOR_BINDINGS["grok-4.6"]; grok["projections"] = [{**row, "endpoint": "grok-4.6"} for row in written["projections"]]; grok.pop("projection_set_sha256"); grok["projection_set_sha256"] = analyzer.sha256(grok)
    (published / "grok.json").write_bytes(analyzer.canonical(grok))
    assert analyzer.analyze_frozen_roots(frozen, published)["endpoint_metrics"][0]["endpoint"] == "gpt-5.6-sol"
    path.write_bytes(value.canonical({**written, "endpoint": "wrong"}))
    with pytest.raises(ValueError, match="differs"):
        value.replay_projection_set(projection_path=path, output_root=execution, frozen_root=frozen, authorization_acknowledgement_sha256=ACK)


def test_runtime_has_no_dspy_or_optuna_and_contract_is_exact():
    value = module()
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert value.validate_package()["pinned_dependencies"]["fresh96_freeze_study_sha256"] == value.FREEZE_SHA256
