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


def test_status_html_is_self_contained_pausable_and_escapes_values():
    html = render_workflow_status(
        {
            "phase": "binary <judge>",
            "completed_scopes": 1,
            "expected_scopes": 2,
            "updated_at": "2026-08-20T12:34:56+00:00",
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
    assert '<meta http-equiv="refresh"' not in html
    assert 'id="hbqrs-auto-refresh"' in html
    assert 'type="checkbox" checked' in html
    assert "Automatic refresh is paused." in html
    assert "window.location.reload()" in html
    assert "<noscript>" in html
    assert '<time datetime="2026-08-20T12:34:56+00:00">' in html
    assert "Last updated:" in html
    assert "*,*::before,*::after{box-sizing:border-box}" in html
    assert "table{width:100%;border-collapse:collapse;table-layout:fixed}" in html
    assert "overflow-wrap:anywhere" in html
    assert "@media (max-width:40rem){body{width:100%;margin:0;padding:.75rem}" in html
    assert "&lt;unit&gt;" in html
    assert "binary <judge>" not in html
    assert "fetch(" not in html
    assert "<script src=" not in html


def test_status_html_is_static_without_watch_refresh():
    html = render_workflow_status({"phase": "routing", "scopes": []})
    assert "hbqrs-auto-refresh" not in html
    assert "window.location.reload()" not in html
    assert "Last updated: not recorded" in html


def test_status_rejects_missing_workflow_and_bad_refresh(tmp_path: Path):
    with pytest.raises(HBQError, match="No long-form workflow"):
        summarize_workflow_progress(tmp_path)
    with pytest.raises(ValueError, match="refresh_seconds"):
        render_workflow_status({}, refresh_seconds=0)
