from __future__ import annotations

from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-sol-replacement-schedule-v1"
schedule = load_module(PACKAGE / "schedule.py", name="hanna_v4_sol_replacement_schedule_v1")


def test_two_terminal_roots_produce_two_distinct_same_item_replacements() -> None:
    rows = schedule.derive_replacements()
    assert [row["replacement_for_terminal_cell_id"] for row in rows] == ["v4-cell-2eb4f20b3db15aac", "v4-cell-2333370999fb84f3"]
    assert {row["cell_id"] for row in rows} == {"v4-sol-replacement-25aec056875cb72c", "v4-sol-replacement-af46262aed40d89e"}
    assert {row["item_id"] for row in rows} == {"item-25d5a1163ca56b27"}
    assert {row["original_item_id"] for row in rows} == {"item-028fc3ac6963b50f"}
    assert all(row["item_id"] > row["original_item_id"] and row["selection_rule"].startswith("lexicographically_next_unused") for row in rows)
    assert {row["candidate_id"] for row in rows} == {"candidate-2b57cd5298e5bbc6", "candidate-52d1be4bc34e0018"}
    assert {row["prompt_group_id"] for row in rows} == {"prompt-132112dd8eeb2d4d"}
    assert {row["parent_cell_id"] for row in rows} == {"v3-cell-0dfba6025e79e719", "v3-cell-3a7ad97cb6fcb7f8"}
    assert all(row["task_payload_sha256"] != schedule._json(schedule.TERMINALS[row["replacement_for_terminal_cell_id"]]["root"] / "prepared.json", "prepared")["request_sha256"] for row in rows)


def test_terminal_inventory_drift_is_rejected(monkeypatch, tmp_path: Path) -> None:
    terminal = schedule.TERMINALS["v4-cell-2eb4f20b3db15aac"]
    copied = tmp_path / "terminal"; copied.mkdir()
    monkeypatch.setitem(terminal, "root", copied)
    with pytest.raises(ValueError, match="inventory/hash drifted"):
        schedule.derive_replacements()
