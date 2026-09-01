from __future__ import annotations

import ast
import base64
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-exec-v1"
DOCUMENTS = Path(r"C:\Users\Haile\Documents")
GROK_ROOT = DOCUMENTS / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a"
LIVE_SOL_ROOT = DOCUMENTS / "cwr-desc16-referent-evidence-sol-veto-exec-pending"


def module():
    spec = importlib.util.spec_from_file_location("_desc16_sol_veto", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def real_inputs() -> dict[str, Path]:
    return {
        "freeze_root": DOCUMENTS / "cwr-hanna-desc16-referent-evidence-freeze-commit-pending-20260901a",
        "development_freeze_root": DOCUMENTS / "cwr-hanna-broader-freeze-436da1e-20260831a",
        "normalized_root": DOCUMENTS / "cwr-hanna-nextwave-normalized-d5e95ba-20260831a",
        "materialization_root": DOCUMENTS / "cwr-hanna-v5-mixed-materialization-9bb20be-20260830a",
        "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
        "grok_execution_root": GROK_ROOT,
        "grok_collector_path": DOCUMENTS / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a.collector.json",
        "grok_result_path": DOCUMENTS / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a.optimizer-bdf96b8-v1.json",
    }


def fake_rows(value) -> tuple[dict, ...]:
    rows = []
    for candidate_index, candidate in enumerate(value.QUALIFIED_CHILDREN):
        for item_index in range(13):
            payload = value.canonical({"candidate": candidate, "item": item_index, "response_schema": {"type": "object"}})
            rows.append({
                "candidate_id": candidate,
                "cell_id": f"sol-{candidate_index}-{item_index}",
                "item_id": f"item-{item_index}",
                "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_parity": "observed_exact_grok_outbound_bytes",
                "payload_sha256": value.sha256(payload),
                "prompt_group_id": f"group-{min(item_index // 2, 6)}",
                "source_cell_id": f"grok-{candidate_index}-{item_index}",
                "story_id": f"item-{item_index}",
                "target": {dimension: 0.0 for dimension in value.DIMENSIONS},
            })
    return tuple(rows)


def test_package_freezes_only_optimizer_qualifiers_and_has_no_runtime_optimizer_imports():
    value = module()
    contract = value.validate_package()
    assert contract["geometry"] == {"development_groups": 7, "max_concurrency": 10, "sol_cells": 26}
    assert tuple(contract["qualified_children"]) == value.QUALIFIED_CHILDREN
    assert contract["authority"]["sol"] == "veto_only"
    assert contract["authority"]["confirmation"] == "unopened"
    assert contract["pinned_dependencies"]["frozen_parent_sol_result"]["equal_group_mae"] == pytest.approx(1.0101190476190476)
    tree = ast.parse((PACKAGE / "executor.py").read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not {"dspy", "optuna"} & imports


def test_real_optimizer_replay_builds_derived_26_byte_identical_sol_payloads():
    value = module()
    resolution = value._resolve(**real_inputs())
    rows = resolution["rows"]
    assert len(rows) == len(value.QUALIFIED_CHILDREN) * 13 == 26
    assert {row["candidate_id"] for row in rows} == set(value.QUALIFIED_CHILDREN)
    assert "broader-nextwave-23-missing_evidence_not_no-local-antecedent-only" not in {row["candidate_id"] for row in rows}
    assert resolution["qualification"]["frozen_before_sol"] is True
    assert tuple(resolution["qualification"]["qualifiers"]) == value.QUALIFIED_CHILDREN
    assert resolution["parent_sol_reference"]["candidate_id"] == "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
    for row in rows:
        raw = base64.b64decode(row["payload_base64"], validate=True)
        assert raw == (GROK_ROOT / row["source_cell_id"] / "outbound-payload.json").read_bytes()
        assert value.sha256(raw) == row["payload_sha256"]


def test_rows_reject_parent_or_outside_candidate_substitution(tmp_path: Path):
    value = module()
    rows = fake_rows(value)
    cells = []
    targets = {}
    for row in rows:
        source = dict(row)
        source.pop("source_cell_id")
        source.pop("story_id")
        source.pop("target")
        source.pop("payload_parity")
        cells.append(source)
        target = {dimension: 0.0 for dimension in value.DIMENSIONS}
        targets[row["item_id"]] = target
        cell = tmp_path / source["cell_id"]
        cell.mkdir()
        (cell / "outbound-payload.json").write_bytes(base64.b64decode(source["payload_base64"]))
    for item_index in range(13):
        payload = value.canonical({"candidate": value.PARENT_CANDIDATE_ID, "item": item_index, "response_schema": {"type": "object"}})
        cell_id = f"parent-{item_index}"
        cells.append({
            "candidate_id": value.PARENT_CANDIDATE_ID,
            "cell_id": cell_id,
            "item_id": f"item-{item_index}",
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "payload_sha256": value.sha256(payload),
            "prompt_group_id": f"group-{min(item_index // 2, 6)}",
        })
        cell = tmp_path / cell_id
        cell.mkdir()
        (cell / "outbound-payload.json").write_bytes(payload)
    rejected = "broader-nextwave-23-missing_evidence_not_no-local-antecedent-only"
    for item_index in range(13):
        payload = value.canonical({"candidate": rejected, "item": item_index, "response_schema": {"type": "object"}})
        cell_id = f"rejected-{item_index}"
        cells.append({
            "candidate_id": rejected,
            "cell_id": cell_id,
            "item_id": f"item-{item_index}",
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "payload_sha256": value.sha256(payload),
            "prompt_group_id": f"group-{min(item_index // 2, 6)}",
        })
        cell = tmp_path / cell_id
        cell.mkdir()
        (cell / "outbound-payload.json").write_bytes(payload)
    schedule = {
        "candidates": [{"candidate_id": candidate} for candidate in (value.PARENT_CANDIDATE_ID, *value.QUALIFIED_CHILDREN, rejected)],
        "cells": cells,
    }
    built = value._rows(schedule=schedule, targets=targets, grok_execution_root=tmp_path)
    assert len(built) == len(value.QUALIFIED_CHILDREN) * 13
    schedule["cells"][0]["candidate_id"] = value.PARENT_CANDIDATE_ID
    with pytest.raises(ValueError, match="geometry"):
        value._rows(schedule=schedule, targets=targets, grok_execution_root=tmp_path)


def test_prepare_is_zero_contact_and_writes_derived_fresh_cells(monkeypatch, tmp_path: Path):
    value = module()
    rows = fake_rows(value)
    resolution = {
        "rows": rows,
        "schedule": {"schedule_sha256": "s" * 64},
        "bindings": {
            "result_analyzer_commit": "a" * 40,
            "result_analyzer_sha256": "b" * 64,
            "result_analyzer_contract_sha256": "c" * 64,
            "grok_result_sha256": "d" * 64,
            "grok_result_internal_sha256": "e" * 64,
            "grok_execution_commit": "f" * 40,
            "grok_executor_sha256": "1" * 64,
            "grok_collector_sha256": "2" * 64,
            "hanna_csv_sha256": "3" * 64,
            "replay_input_commitments": {},
        },
    }
    launches = []

    class Base:
        canonical = staticmethod(value.canonical)

        @staticmethod
        def _route(_queue, _factory):
            return {"name": "route"}, {"route_name": "route"}, None

        @staticmethod
        def _prepared(row, payload, schema, target, route, evidence, acknowledgement):
            launches.append("prepare")
            return {
                "prepared.json": value.canonical({"cell": row, "route": route, "route_evidence": evidence}),
                "outbound-payload.json": payload,
                "response-schema.json": schema,
            }

        @staticmethod
        def _write_new(path, raw):
            path.write_bytes(raw)

    monkeypatch.setattr(value, "validate_package", dict)
    monkeypatch.setattr(value, "_resolve", lambda **_kwargs: resolution)
    monkeypatch.setattr(value, "_configured_base", lambda _resolution: Base())
    queue = tmp_path / "queue"
    queue.mkdir()
    sources = {}
    for name in (
        "freeze_root", "development_freeze_root", "normalized_root", "materialization_root",
        "frozen_successor_path", "hanna_csv_path", "grok_execution_root",
        "grok_collector_path", "grok_result_path",
    ):
        path = tmp_path / ("source-" + name)
        path.mkdir()
        sources[name] = path
    result = value.prepare_all(
        output_root=tmp_path / "output",
        queue_root=queue,
        authorization_acknowledgement_sha256="2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78",
        **sources,
    )
    assert result["cells"] == len(rows)
    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert result["max_concurrency"] == 10
    assert len(launches) == len(rows)
    with pytest.raises(ValueError, match="fresh output root"):
        value.prepare_all(
            output_root=tmp_path / "output",
            queue_root=queue,
            authorization_acknowledgement_sha256="2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78",
            **sources,
        )


def test_terminal_launch_evidence_refuses_a_second_cell_claim(tmp_path: Path):
    value = module()
    row = fake_rows(value)[0]
    root = tmp_path / row["cell_id"]
    root.mkdir()
    (root / "launch-intent.json").write_bytes(value.canonical({"cell_id": row["cell_id"]}))
    locks = tmp_path / "locks"
    locks.mkdir()
    with pytest.raises(ValueError, match="fresh root|no resend"):
        value._claim_cell(locks, SimpleNamespace(), root, row)
    assert not list(locks.iterdir())


def test_wave_uses_at_most_ten_codex_lanes(monkeypatch, tmp_path: Path):
    value = module()
    rows = fake_rows(value)
    current = peak = 0
    guard = threading.Lock()
    monkeypatch.setattr(value, "validate_package", dict)
    monkeypatch.setattr(value, "_resolve", lambda **_kwargs: {"rows": rows, "bindings": {}, "schedule": {}})
    class Base:
        @staticmethod
        def _inventory(_path, *, completed=False):
            assert completed is True

    monkeypatch.setattr(value, "_configured_base", lambda _resolution: Base())
    monkeypatch.setattr(value, "_prepared_inventory", lambda *_args: None)
    monkeypatch.setattr(value, "_terminal_state", lambda *_args: False)
    monkeypatch.setattr(value, "_locks", lambda _root: tmp_path / "locks")

    def run(**kwargs):
        nonlocal current, peak
        with guard:
            current += 1
            peak = max(peak, current)
        time.sleep(0.01)
        with guard:
            current -= 1
        return {"cell_id": kwargs["row"]["cell_id"]}

    locks = tmp_path / "locks"
    locks.mkdir()
    monkeypatch.setattr(value, "_execute_prepared", run)
    queue = tmp_path / "queue"
    queue.mkdir()
    sources = {}
    for name in (
        "freeze_root", "development_freeze_root", "normalized_root", "materialization_root",
        "frozen_successor_path", "hanna_csv_path", "grok_execution_root",
        "grok_collector_path", "grok_result_path",
    ):
        path = tmp_path / ("source-" + name)
        path.mkdir()
        sources[name] = path
    output = tmp_path / "output"
    output.mkdir()
    completed = value.execute_wave(
        output_root=output,
        queue_root=queue,
        authorization_acknowledgement_sha256="a" * 64,
        allow_remote=True,
        **sources,
    )
    assert len(completed) == len(rows)
    assert 1 < peak <= 10


def test_pinned_callback_creates_responses_before_revalidating_and_writes_one_launch_intent():
    value = module()
    base, _grok = value.sol_v4()._sources()
    v3_source = Path(base._load_v3().__file__).read_text(encoding="utf-8")
    callback_source = Path(base.__file__).read_text(encoding="utf-8")
    assert v3_source.index("message.parent.mkdir") < v3_source.index("before_provider_attempt()")
    assert "callback=True" in callback_source
    assert "if launches:" in callback_source
    assert "_write_new(root / \"launch-intent.json\"" in callback_source


def test_finalize_uses_completed_inventory_and_writes_replayable_collector(monkeypatch, tmp_path: Path):
    value = module()
    rows = fake_rows(value)
    parent = {
        "candidate_id": value.PARENT_CANDIDATE_ID,
        "equal_group_mae": value.PARENT_SOL_EQUAL_GROUP_MAE,
        "result_commit": value.PARENT_SOL_RESULT_COMMIT,
        "result_file_sha256": value.PARENT_SOL_RESULT_SHA256,
    }
    output = tmp_path / "output"
    output.mkdir()
    for row in rows:
        (output / row["cell_id"]).mkdir()
    inventory_modes = []

    class Base:
        @staticmethod
        def _inventory(_path, *, completed=False):
            inventory_modes.append(completed)

        @staticmethod
        def _write_new(path, raw):
            path.write_bytes(raw)

    def admitted(_base, _v4, row, _root, _ack):
        payload = base64.b64decode(row["payload_base64"])
        final = value.canonical({"cell": row["cell_id"]})
        identity = {
            "thread_id": "thread-" + row["cell_id"],
            "session_id": "session-" + row["cell_id"],
            "contact_id": "contact-" + row["cell_id"],
        }
        settings = {"tools_enabled": False}
        return {
            "route": {"name": "route"},
            "route_evidence": {"route_name": "route"},
            "payload": payload,
            "final": final,
            "receipt": {"cell": row["cell_id"]},
            "identity": identity,
            "identity_key": (identity["thread_id"], identity["session_id"], identity["contact_id"]),
            "settings": settings,
            "answer": {"scores": {dimension: 0.0 for dimension in value.DIMENSIONS}},
        }

    monkeypatch.setattr(value, "validate_package", dict)
    monkeypatch.setattr(value, "_resolve", lambda **_kwargs: {"rows": rows, "parent_sol_reference": parent})
    monkeypatch.setattr(value, "_configured_base", lambda _resolution: Base())
    monkeypatch.setattr(value, "sol_v4", lambda: SimpleNamespace())
    monkeypatch.setattr(value, "_admit_completed_cell", admitted)
    collector = tmp_path / "collector.json"
    result = value.finalize_collector(
        output_root=output,
        collector_output=collector,
        authorization_acknowledgement_sha256="a" * 64,
    )
    assert result["cells"] == result["process_launches"] == len(rows)
    assert inventory_modes == [True] * len(rows)
    persisted = value.strict(collector.read_bytes(), "collector")
    assert persisted["parent_sol_reference"] == parent


def test_live_codex_reported_shape_is_semantically_bound():
    value = module()
    projection = {"thread_id": "thread-1"}
    identity = {
        "provider": "openai_codex",
        "provider_reported_model": None,
        "reasoning_attested": False,
        "session_id": "local-codex-thread-session:thread-1",
    }
    settings = {
        "provider_attested": False,
        "local_effective_reasoning_effort": "high",
    }
    record = {
        "command": ["codex"],
        "provider_artifacts": {},
        "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": None},
    }
    assert value._validated_reported_record(
        record,
        identity=identity,
        settings=settings,
        projection=projection,
    ) == record["reported"]
    for field, forged in (
        ("model", "gpt-5.6-sol"),
        ("provider", "openai_codex"),
        ("reasoning_effort", "high"),
        ("session_id", "unrelated-session"),
    ):
        mutated = json.loads(json.dumps(record))
        mutated["reported"][field] = forged
        with pytest.raises(ValueError):
            value._validated_reported_record(
                mutated,
                identity=identity,
                settings=settings,
                projection=projection,
            )


def test_live_derived_cell_root_finalizes_and_replays_provider_free_without_mutation(tmp_path: Path):
    if not LIVE_SOL_ROOT.is_dir():
        pytest.skip("opt-in immutable live Sol evidence is unavailable")
    value = module()
    before = value._tree_commitment(LIVE_SOL_ROOT)
    collector = tmp_path / "collector.json"
    finalized = value.finalize_collector(
        output_root=LIVE_SOL_ROOT,
        collector_output=collector,
        authorization_acknowledgement_sha256="2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78",
        **real_inputs(),
    )
    assert finalized["cells"] == finalized["process_launches"] == len(value.QUALIFIED_CHILDREN) * 13
    assert finalized["provider_calls_made"] is None
    replayed = value.replay_collector(
        output_root=LIVE_SOL_ROOT,
        collector_path=collector,
        **real_inputs(),
    )
    assert replayed["cells"] == replayed["process_launches"] == len(value.QUALIFIED_CHILDREN) * 13
    assert replayed["native_endpoint_contact_cardinality"] == "unproven"
    assert value._tree_commitment(LIVE_SOL_ROOT) == before


def test_collector_replay_rejects_forged_response_even_with_matching_hash(monkeypatch, tmp_path: Path):
    value = module()
    rows = fake_rows(value)
    acknowledgement = "a" * 64

    def admitted(_base, _v4, row, _root, supplied_ack):
        assert supplied_ack == acknowledgement
        payload = base64.b64decode(row["payload_base64"])
        final = value.canonical({"cell": row["cell_id"]})
        identity = {
            "thread_id": "thread-" + row["cell_id"],
            "session_id": "session-" + row["cell_id"],
            "contact_id": "contact-" + row["cell_id"],
        }
        settings = {"tools_enabled": False, "model": "gpt-5.6-sol"}
        answer = {"scores": {dimension: 0.0 for dimension in value.DIMENSIONS}}
        return {
            "route": {"name": "route"},
            "route_evidence": {"route_name": "route"},
            "payload": payload,
            "final": final,
            "receipt": {"cell": row["cell_id"], "final_response_sha256": value.sha256(final)},
            "identity": identity,
            "identity_key": (identity["thread_id"], identity["session_id"], identity["contact_id"]),
            "settings": settings,
            "answer": answer,
        }

    monkeypatch.setattr(value, "validate_package", dict)
    parent = {
        "candidate_id": value.PARENT_CANDIDATE_ID,
        "equal_group_mae": value.PARENT_SOL_EQUAL_GROUP_MAE,
        "result_commit": value.PARENT_SOL_RESULT_COMMIT,
        "result_file_sha256": value.PARENT_SOL_RESULT_SHA256,
    }
    monkeypatch.setattr(value, "_resolve", lambda **_kwargs: {"rows": rows, "parent_sol_reference": parent})

    class Base:
        @staticmethod
        def _inventory(_path, *, completed=False):
            assert completed is True

    monkeypatch.setattr(value, "_configured_base", lambda _resolution: Base())
    monkeypatch.setattr(value, "sol_v4", lambda: SimpleNamespace())
    monkeypatch.setattr(value, "_admit_completed_cell", admitted)
    cells = []
    for row in rows:
        item = admitted(None, None, row, tmp_path, acknowledgement)
        cells.append({
            "cell_id": row["cell_id"],
            "source_cell_id": row["source_cell_id"],
            "candidate_id": row["candidate_id"],
            "payload_base64": base64.b64encode(item["payload"]).decode("ascii"),
            "payload_sha256": value.sha256(item["payload"]),
            "final_response_base64": base64.b64encode(item["final"]).decode("ascii"),
            "final_response_sha256": value.sha256(item["final"]),
            "receipt_sha256": value.sha256(item["receipt"]),
            "identity": item["identity"],
            "effective_settings": item["settings"],
            "effective_settings_sha256": value.sha256(item["settings"]),
            "human_score_projection": item["answer"],
        })
    collector = {
        "format_version": 1,
        "study_id": value.STUDY_ID,
        "kind": "complete_derived_desc16_sol_veto_receipts_cardinality_unproven",
        "authorization_acknowledgement_sha256": acknowledgement,
        "optimizer_result_file_sha256": value.RESULT_FILE_SHA256,
        "optimizer_result_internal_sha256": value.RESULT_INTERNAL_SHA256,
        "parent_sol_reference": parent,
        "qualified_children": list(value.QUALIFIED_CHILDREN),
        "route": {"name": "route"},
        "route_evidence": {"route_name": "route"},
        "cells": cells,
        "native_endpoint_contact_cardinality": "unproven",
        "provider_calls_made": None,
        "process_launches": len(rows),
    }
    path = tmp_path / "collector.json"
    output = tmp_path / "output"
    output.mkdir()
    for row in rows:
        (output / row["cell_id"]).mkdir()
    path.write_bytes(value.canonical(collector))
    replayed = value.replay_collector(output_root=output, collector_path=path)
    assert replayed["cells"] == replayed["process_launches"] == len(rows)
    collector["format_version"] = 2
    path.write_bytes(value.canonical(collector))
    with pytest.raises(ValueError, match="collector drifted"):
        value.replay_collector(output_root=output, collector_path=path)
    collector["format_version"] = 1
    forged = value.canonical({"forged": True})
    collector["cells"][0]["final_response_base64"] = base64.b64encode(forged).decode("ascii")
    collector["cells"][0]["final_response_sha256"] = value.sha256(forged)
    path.write_bytes(value.canonical(collector))
    with pytest.raises(ValueError, match="persisted Sol receipt"):
        value.replay_collector(output_root=output, collector_path=path)
