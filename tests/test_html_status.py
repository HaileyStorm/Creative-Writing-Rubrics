from pathlib import Path

import pytest

from hbqrs.core import HBQError
from hbqrs.html_status import render_workflow_status, summarize_workflow_progress


def test_status_summary_reads_only_persisted_checkpoints(tmp_path: Path):
    (tmp_path / "workflow.json").write_text('{"configuration": {}}', encoding="utf-8")
    (tmp_path / "plan.json").write_text(
        '{"sampling_plan": {"unit_ids": ["u1", "u2"]}}', encoding="utf-8"
    )
    route = tmp_path / ".private" / "passes" / "route"
    route.mkdir(parents=True)
    (route / "result.json").write_text("{}", encoding="utf-8")
    progress = summarize_workflow_progress(tmp_path)
    assert progress["phase"] == "mapping"
    assert progress["expected_scopes"] == 3
    assert progress["completed_scopes"] == 0


def test_status_html_is_self_contained_and_escapes_values():
    html = render_workflow_status(
        {
            "phase": "binary <judge>",
            "completed_scopes": 1,
            "expected_scopes": 2,
            "scopes": [
                {
                    "scope_id": "<unit>",
                    "status": "RUNNING",
                    "response_batches": 2,
                    "expected_batches": 4,
                }
            ],
        },
        refresh_seconds=3,
    )
    assert '<meta http-equiv="refresh" content="3">' in html
    assert "&lt;unit&gt;" in html
    assert "binary <judge>" not in html
    assert "fetch(" not in html
    assert "<script src=" not in html


def test_status_rejects_missing_workflow_and_bad_refresh(tmp_path: Path):
    with pytest.raises(HBQError, match="No long-form workflow"):
        summarize_workflow_progress(tmp_path)
    with pytest.raises(ValueError, match="refresh_seconds"):
        render_workflow_status({}, refresh_seconds=0)
