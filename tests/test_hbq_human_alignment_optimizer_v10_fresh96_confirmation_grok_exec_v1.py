from __future__ import annotations

import base64
import builtins
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1"
EXECUTOR = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-exec-v1"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def freeze_module():
    return load(FREEZE / "study.py", "v10_future_freeze_test")


def executor_module():
    return load(EXECUTOR / "executor.py", "v10_future_exec_test")


def test_panel_and_analysis_are_frozen_before_private_root_admission() -> None:
    study = freeze_module()
    contract = study.contract()
    assert contract["panel"] == {"baseline_candidate_id": study.BASELINE, "child_candidate_id": study.CHILD}
    assert contract["analysis_rule"] == {
        "aggregation": "mean_of_16_prompt_group_maes",
        "comparison": "child20_minus_baseline",
        "direction": "negative_favors_child20",
        "endpoints": {"grok_primary": {"complete_cells": 64, "endpoint_pooling": "forbidden"}, "sol_later": {"complete_cells": 64, "endpoint_pooling": "forbidden"}},
        "missing_or_ambiguous_cell": "terminal_reconcile_only_no_projection_without_all_64_cells",
        "pairing": "same_item_each_candidate_exact_payload_unchanged_across_endpoints",
        "selection": "forbidden",
        "target_use": "local_projection_only",
    }
    validation = study._module(study.VALIDATION, study.VALIDATION_SHA256, "v10_validation")
    panel = study._panel(validation)
    assert [(row["candidate_id"], row["candidate_sha256"], row["instruction_sha256"], row["profile_sha256"]) for row in panel] == [
        (study.BASELINE, study.BASELINE_CANDIDATE_SHA256, study.BASELINE_INSTRUCTION_SHA256, study.BASELINE_PROFILE_SHA256),
        (study.CHILD, study.CHILD_CANDIDATE_SHA256, study.CHILD_INSTRUCTION_SHA256, study.CHILD_PROFILE_SHA256),
    ]
    assert study._qualification() == {"result_sha256": study.V9_SOL_VETO_SHA256, "study_id": "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-result-v1", "selection": "grok_qualification_then_sol_veto_only", "retained_candidate_id": study.CHILD}


def valid_frozen_schedule(study) -> dict:
    validation = study._module(study.VALIDATION, study.VALIDATION_SHA256, "v10_validation_schedule")
    panel = study._panel(validation)
    cells = []
    for number in range(32):
        item = {"item_id": f"item-{number:02d}", "prompt_group_id": f"group-{number // 2:02d}", "prompt": f"Prompt {number}", "story": f"Substantive story text for item {number}." * 8, "source_binding_sha256": "a" * 64, "target": {dimension: 2.0 for dimension in study.DIMENSIONS}}
        for candidate in panel:
            payload = study._payload(validation, item, candidate)
            target = {dimension: 2.0 for dimension in study.DIMENSIONS}
            cells.append({"cell_id": "v10-future-" + study.sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20], "ordinal": len(cells) + 1, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "partition": "future_confirmation", "prompt_group_id": item["prompt_group_id"], "item_id": item["item_id"], "source_binding_sha256": item["source_binding_sha256"], "target": target, "target_sha256": study.sha256(target), "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": study.sha256(payload), "endpoint_payload_sha256s": {"grok_primary": study.sha256(payload), "sol_later": study.sha256(payload)}})
    candidates = [{key: candidate[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "kind")} for candidate in panel]
    value = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "frozen_fresh96_future_confirmation_candidate_panel", "private_source": {"fresh96_manifest_sha256": study.MANIFEST_SHA256, "private_freeze_sha256": study.PRIVATE_FREEZE_SHA256, "hanna_csv_sha256": "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"}, "qualification": study._qualification(), "analysis_rule": study.contract()["analysis_rule"], "candidates": candidates, "cells": cells, "geometry": {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}, "authority": study.contract()["authority"]}
    value["schedule_sha256"] = study.sha256(value)
    return value


def test_coherent_panel_rehash_cannot_replace_a_candidate_profile() -> None:
    study = freeze_module()
    value = valid_frozen_schedule(study)
    study.validate(value)
    tampered = json.loads(study.canonical(value))
    row = next(row for row in tampered["cells"] if row["candidate_id"] == study.BASELINE)
    payload = json.loads(base64.b64decode(row["payload_base64"]))
    payload["profile"] = {"tampered": True}
    profile_sha = hashlib.sha256(json.dumps(payload["profile"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    for cell in tampered["cells"]:
        if cell["candidate_id"] == study.BASELINE:
            decoded = json.loads(base64.b64decode(cell["payload_base64"]))
            decoded["profile"] = {"tampered": True}
            changed = study.canonical(decoded)
            cell["payload_base64"], cell["payload_sha256"] = base64.b64encode(changed).decode(), study.sha256(changed)
            cell["candidate_profile_sha256"] = profile_sha
            cell["endpoint_payload_sha256s"] = {"grok_primary": study.sha256(changed), "sol_later": study.sha256(changed)}
    tampered["candidates"][0]["profile_sha256"] = profile_sha
    tampered.pop("schedule_sha256")
    tampered["schedule_sha256"] = study.sha256(tampered)
    with pytest.raises(ValueError, match="panel"):
        study.validate(tampered)


def schedule(study) -> dict:
    cells = []
    for number in range(32):
        for candidate in (study.BASELINE, study.CHILD):
            payload = study.canonical({"format_version": 1, "study_id": "public", "instruction": candidate, "profile": {}, "writing": {"prompt": f"Prompt {number}", "story": "Story text long enough to be substantive."}, "response_schema": {}})
            cells.append({"cell_id": f"cell-{candidate[-4:]}-{number:02d}", "candidate_id": candidate, "item_id": f"item-{number:02d}", "prompt_group_id": f"group-{number // 2:02d}", "partition": "future_confirmation", "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": study.sha256(payload), "endpoint_payload_sha256s": {"grok_primary": study.sha256(payload), "sol_later": study.sha256(payload)}, "target": {name: 2.0 for name in study.DIMENSIONS}, "target_sha256": study.sha256({name: 2.0 for name in study.DIMENSIONS})})
    value = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "frozen_fresh96_future_confirmation_candidate_panel", "analysis_rule": study.contract()["analysis_rule"], "candidates": [], "cells": cells, "geometry": {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}, "authority": study.contract()["authority"]}
    value["schedule_sha256"] = study.sha256(value)
    return value


class FakeFreeze:
    def __init__(self, value):
        self.value = value
        self.STUDY_ID = value["study_id"]

    def validate_frozen_root(self, _root):
        return self.value

    @staticmethod
    def strict(raw: bytes, label: str):
        return json.loads(raw.decode())

    @staticmethod
    def sha256(value):
        raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        return hashlib.sha256(raw).hexdigest()


def test_executor_admits_only_64_cell_cross_endpoint_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    study, executor = freeze_module(), executor_module()
    value = schedule(study)
    monkeypatch.setattr(executor, "freeze_module", lambda: FakeFreeze(value))
    frozen = executor.frozen_schedule(Path("unused"))
    assert frozen["study_id"] == executor.STUDY_ID
    assert executor.MAX_CONCURRENCY == 10
    assert frozen["geometry"] == {"candidates": 2, "confirmation_cells": 64, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}
    for row in frozen["cells"]:
        payload = base64.b64decode(row["payload_base64"])
        assert row["endpoint_payload_sha256s"]["grok_primary"] == row["endpoint_payload_sha256s"]["sol_later"] == hashlib.sha256(payload).hexdigest()
        assert "tools" not in json.loads(payload)
    value["cells"].pop()
    with pytest.raises(ValueError, match="identity"):
        executor.frozen_schedule(Path("unused"))


def test_remote_execution_requires_explicit_opt_in_before_loading_runner() -> None:
    executor = executor_module()
    with pytest.raises(ValueError, match="explicit allow_remote"):
        executor.execute_one(output_root=Path("out"), freeze_root=Path("freeze"), queue_root=Path("queue"), authorization_acknowledgement_sha256="a" * 64, cell_id="cell", allow_remote=False)


def test_no_runtime_optimizer_or_sol_execution_surface() -> None:
    sources = (FREEZE / "study.py").read_text(encoding="utf-8").casefold() + (EXECUTOR / "executor.py").read_text(encoding="utf-8").casefold()
    assert "import dspy" not in sources and "import optuna" not in sources
    assert "sol_later" in sources and "def execute_sol" not in sources


def test_modules_load_when_runtime_optimizer_imports_are_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}:
            raise AssertionError("runtime optimizer import attempted")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert freeze_module().STUDY_ID.endswith("candidates-v1")
    assert executor_module().STUDY_ID.endswith("grok-exec-v1")


class FakeCollectorBase:
    def __init__(self, schedule):
        self.schedule = schedule

    @staticmethod
    def canonical(value):
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

    def sha256(self, value):
        return hashlib.sha256(value if isinstance(value, bytes) else self.canonical(value)).hexdigest()

    @staticmethod
    def _safe(path):
        return Path(path)

    @staticmethod
    def stable(path):
        return Path(path).read_bytes()

    def strict(self, raw, _label):
        value = json.loads(raw)
        assert self.canonical(value) == raw
        return value

    @contextmanager
    def _bound_source(self, **_kwargs):
        class Lifecycle:
            @staticmethod
            def write_new(path, raw):
                Path(path).write_bytes(raw)
        class Parent:
            @staticmethod
            def _validate_route_evidence(route, evidence):
                assert route == {"provider": "xai"} and evidence == {"proof": "p"}
        yield Lifecycle(), object(), self.schedule, Parent(), object()

    @staticmethod
    def _validate_claims(_output, _cells):
        return None

    def _admit_cell(self, _lifecycle, _source, _output, row, _schedule, _ack):
        request = f"request-{row['cell_id']}".encode()
        response = self.canonical({"structuredOutput": {"scores": {name: 2.0 for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}, "evidence": {name: "specific text" for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}, "coverage": {name: True for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}}})
        identity = {"request_id": f"request-{row['cell_id']}", "session_id": f"session-{row['cell_id']}"}
        return request, response, identity, {"tools_enabled": False}, {"route": {"provider": "xai"}, "route_evidence": {"proof": "p"}}


def test_persisted_collector_and_replay_are_v10_measurement_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executor = executor_module()
    cells = []
    for number in range(64):
        payload = f"payload-{number}".encode()
        cells.append({"cell_id": f"cell-{number:02d}", "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": hashlib.sha256(payload).hexdigest()})
    schedule = {"schedule_sha256": "s" * 64, "cells": cells}
    base = FakeCollectorBase(schedule)
    monkeypatch.setattr(executor, "_configured_base", lambda: base)
    output = tmp_path / "output"; output.mkdir(); (output / ".claims").mkdir(); (output / "schedule.json").write_bytes(base.canonical(schedule))
    for row in cells:
        (output / row["cell_id"]).mkdir()
    collector = tmp_path / "collector.json"
    finalized = executor.finalize_collector(output_root=output, freeze_root=tmp_path / "freeze", collector_output=collector, authorization_acknowledgement_sha256="a" * 64)
    persisted = json.loads(collector.read_bytes())
    assert finalized["kind"] == persisted["kind"] == "complete_64_fresh96_future_confirmation_grok_receipts_cardinality_unproven"
    assert {row["effective_settings"]["tools_enabled"] for row in persisted["cells"]} == {False}
    replay = executor.replay_collector(output_root=output, freeze_root=tmp_path / "freeze", collector_path=collector)
    assert replay["authority"]["confirmation"] == {"status": "measurement_only", "cells": 64}
    persisted["kind"] = "complete_64_desc18_open_validation_grok_receipts_cardinality_unproven"
    collector.write_bytes(base.canonical(persisted))
    with pytest.raises(ValueError, match="collector drifted"):
        executor.replay_collector(output_root=output, freeze_root=tmp_path / "freeze", collector_path=collector)
