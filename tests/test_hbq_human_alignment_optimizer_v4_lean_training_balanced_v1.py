from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-lean-training-balanced-v1" / "verifier.py"


def _load():
    spec = importlib.util.spec_from_file_location("balanced_training", VERIFIER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(*, group: int, candidate: int, route_name: str, cell_id: str, item_prefix: str = "train") -> dict:
    return {
        "cell_id": cell_id, "route_name": route_name, "item_id": f"{item_prefix}-item-{group}",
        "prompt_group_id": f"{item_prefix}-group-{group}", "candidate_id": f"candidate-{candidate}",
        "route": {"route_name": route_name},
    }


def _base(balanced):
    grok = [_row(group=group, candidate=candidate, route_name="grok_primary", cell_id=(balanced.FAILED_CELL_ID if (group, candidate) == (0, 2) else f"grok-{group}-{candidate}")) for group in range(5) for candidate in range(5)]
    sol = [_row(group=group, candidate=candidate, route_name="sol_validation", cell_id=f"sol-{group}-{candidate}") for group in range(2) for candidate in range(5)]
    development = [_row(group=group, candidate=candidate, route_name="grok_primary", cell_id=f"dev-{group}-{candidate}", item_prefix="dev") for group in range(7) for candidate in range(5)]
    optimizer = SimpleNamespace(_targets=lambda _native, rows, **_kwargs: {row["item_id"]: {"quality": 1.0} for row in rows})
    schedule = {"schedule_sha256": "schedule-sha", "candidate_ids": [f"candidate-{candidate}" for candidate in range(5)], "partitions": {"grok_development": development, "sol_validation_templates": []}}
    def cell(_collector, _optimizer, _native, _v1, _v3, _root, row, _schedule, **_kwargs):
        return {**row, "scores": {"quality": 1.0}, "coverage": {"quality": True}, "request_bytes": 7,
                "identity": {"provider": row["route_name"], "contact_id": row["cell_id"], "session_id": row["cell_id"]}}
    return SimpleNamespace(
        COLLECTOR_PATH=Path("hbq-human-alignment-optimizer-v4-lean-training-exec-v1/executor.py"),
        _dependencies=lambda: (object(), optimizer, object(), object(), object()),
        _rows=lambda _optimizer, _frozen, _hanna: (schedule, [*grok, *sol]),
        _cell=cell,
    )


def _terminal(root: Path, balanced) -> Path:
    root.mkdir(); (root / "responses").mkdir(); (root / "sidecar.bin").write_bytes(b"preserved")
    (root / "result.json").write_bytes(balanced.canonical({
        "format_version": 1, "study_id": "hbq-human-alignment-optimizer-v4-lean-training-exec-v1",
        "kind": "reconcile_required_after_process_launch", "cell_id": balanced.FAILED_CELL_ID,
        "error_type": "_ProviderAttemptFailure", "provider_calls_made": 1, "process_launches": 1,
    }))
    return root


def _pin_fixture_terminal(monkeypatch, balanced, terminal: Path) -> None:
    monkeypatch.setattr(balanced, "FAILED_TERMINAL_INVENTORY_SHA256", balanced.sha256_bytes(balanced.canonical(balanced._snapshot(terminal))))
    monkeypatch.setattr(balanced, "FAILED_TERMINAL_RESULT_SHA256", balanced.sha256_bytes(balanced._stable_bytes(terminal / "result.json")))


def test_replays_only_complete_groups_and_preserves_terminal_inventory(monkeypatch, tmp_path: Path):
    balanced = _load(); monkeypatch.setattr(balanced, "_base", lambda: _base(balanced))
    base = balanced._base()
    _schedule, rows, excluded, _failed = balanced._balanced_rows(base, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    references = [{"cell_id": row["cell_id"], "execution_root": str(tmp_path / row["cell_id"])} for row in rows]
    terminal = _terminal(tmp_path / "failed", balanced); _pin_fixture_terminal(monkeypatch, balanced, terminal)
    manifest = balanced.prepare_balanced_manifest(references=references, failed_terminal_root=terminal, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    evidence = tmp_path / "balanced.json"; evidence.write_bytes(balanced.canonical(manifest))
    projection = balanced.verify_balanced_training_receipts(collection_evidence_path=evidence, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    assert len(excluded) == 5
    assert projection["geometry"] == {"grok_prompt_groups": 4, "grok_candidates_per_group": 5, "grok_cells": 20, "sol_cells": 10, "total_cells": 30}
    assert projection["provider_calls_made"] == 0
    assert len(projection["observations"]) == 30
    assert len(projection["human_targets"]) == 5


def test_rejects_incomplete_group_and_changed_terminal(monkeypatch, tmp_path: Path):
    balanced = _load(); monkeypatch.setattr(balanced, "_base", lambda: _base(balanced))
    base = balanced._base()
    _schedule, rows, _excluded, _failed = balanced._balanced_rows(base, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    terminal = _terminal(tmp_path / "failed", balanced)
    _pin_fixture_terminal(monkeypatch, balanced, terminal)
    references = [{"cell_id": row["cell_id"], "execution_root": str(tmp_path / row["cell_id"])} for row in rows]
    with pytest.raises(ValueError, match="exactly the ordered"):
        balanced.prepare_balanced_manifest(references=references[:-1], failed_terminal_root=terminal, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    manifest = balanced.prepare_balanced_manifest(references=references, failed_terminal_root=terminal, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    evidence = tmp_path / "balanced.json"; evidence.write_bytes(balanced.canonical(manifest))
    (terminal / "sidecar.bin").write_bytes(b"changed")
    with pytest.raises(ValueError, match="does not match the pinned source"):
        balanced.verify_balanced_training_receipts(collection_evidence_path=evidence, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")


def test_rejects_a_forged_minimal_terminal_even_with_canonical_result(monkeypatch, tmp_path: Path):
    balanced = _load(); monkeypatch.setattr(balanced, "_base", lambda: _base(balanced))
    base = balanced._base()
    _schedule, rows, _excluded, _failed = balanced._balanced_rows(base, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")
    preserved = _terminal(tmp_path / "preserved", balanced); _pin_fixture_terminal(monkeypatch, balanced, preserved)
    forged = tmp_path / "forged"; forged.mkdir()
    (forged / "result.json").write_bytes((preserved / "result.json").read_bytes())
    references = [{"cell_id": row["cell_id"], "execution_root": str(tmp_path / row["cell_id"])} for row in rows]
    with pytest.raises(ValueError, match="does not match the pinned source"):
        balanced.prepare_balanced_manifest(references=references, failed_terminal_root=forged, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "hanna")


def test_pins_the_existing_collector_replayer_source():
    balanced = _load()
    assert balanced.sha256_bytes(balanced._stable_bytes(balanced.BASE_PATH)) == balanced.BASE_SHA256
