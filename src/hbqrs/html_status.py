"""Optional self-contained progress page derived from persisted workflow state."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any

from .core import HBQError, load_data


def summarize_workflow_progress(output_dir: str | Path) -> dict[str, Any]:
    """Read only durable checkpoints and return a compact progress snapshot."""

    root = Path(output_dir).resolve()
    workflow_path = root / "workflow.json"
    if not workflow_path.is_file():
        raise HBQError(f"No long-form workflow found at {root}")
    workflow = load_data(workflow_path)
    if not isinstance(workflow, dict):
        raise HBQError("workflow.json must contain an object")
    plan_path = root / "plan.json"
    plan = load_data(plan_path) if plan_path.is_file() else None
    if plan is not None and not isinstance(plan, dict):
        raise HBQError("plan.json must contain an object")
    private = root / ".private"
    evaluations = private / "evaluations"
    scopes: list[dict[str, Any]] = []
    if evaluations.is_dir():
        for directory in sorted((item for item in evaluations.iterdir() if item.is_dir()), key=lambda item: item.name):
            response_count = len(list((directory / "responses").glob("batch-*.json")))
            score = load_data(directory / "score.json") if (directory / "score.json").is_file() else None
            run = load_data(directory / "run.json") if (directory / "run.json").is_file() else None
            configured_batches = None
            if isinstance(run, dict):
                configuration = run.get("configuration", {})
                question_ids = configuration.get("question_ids", []) if isinstance(configuration, dict) else []
                batch_size = configuration.get("batch_size") if isinstance(configuration, dict) else None
                if isinstance(question_ids, list) and isinstance(batch_size, int) and batch_size > 0:
                    configured_batches = (len(question_ids) + batch_size - 1) // batch_size
            scopes.append(
                {
                    "scope_id": directory.name,
                    "response_batches": response_count,
                    "expected_batches": configured_batches,
                    "complete": isinstance(score, dict),
                    "status": score.get("status") if isinstance(score, dict) else "RUNNING",
                }
            )
    expected_scopes = None
    if isinstance(plan, dict):
        sampling = plan.get("sampling_plan", {})
        unit_ids = sampling.get("unit_ids", []) if isinstance(sampling, dict) else []
        expected_scopes = 1 + len(unit_ids) if isinstance(unit_ids, list) else None
    report_complete = (root / "report.json").is_file()
    synthesis_complete = (private / "passes" / "synthesis" / "result.json").is_file()
    map_complete = (private / "passes" / "map" / "result.json").is_file()
    route_complete = (private / "passes" / "route" / "result.json").is_file()
    if report_complete:
        phase = "complete"
    elif synthesis_complete:
        phase = "rendering"
    elif scopes and expected_scopes is not None and sum(item["complete"] for item in scopes) >= expected_scopes:
        phase = "synthesis"
    elif map_complete:
        phase = "binary judging"
    elif route_complete:
        phase = "mapping"
    else:
        phase = "routing"
    return {
        "status_version": 1,
        "phase": phase,
        "complete": report_complete,
        "route_complete": route_complete,
        "map_complete": map_complete,
        "synthesis_complete": synthesis_complete,
        "completed_scopes": sum(bool(item["complete"]) for item in scopes),
        "expected_scopes": expected_scopes,
        "scopes": scopes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def render_workflow_status(
    progress: dict[str, Any], *, refresh_seconds: int | None = None
) -> str:
    """Render a static status page with an optional, pausable local refresh."""

    if refresh_seconds is not None and not 1 <= refresh_seconds <= 3600:
        raise ValueError("refresh_seconds must be between 1 and 3600")
    esc = lambda value: html.escape(str(value), quote=True)
    refresh_controls = ""
    if refresh_seconds:
        refresh_controls = f"""<p class="refresh-control"><label><input id="hbqrs-auto-refresh" type="checkbox" checked> Refresh this local status page every {refresh_seconds} seconds</label></p>
<p id="hbqrs-refresh-state" class="refresh-state" aria-live="polite">Automatic refresh is on.</p>
<noscript><p class="refresh-state">Automatic refresh needs scripting. Use your browser's refresh control to update this static page.</p></noscript>
<script>(function () {{
  const toggle = document.getElementById("hbqrs-auto-refresh");
  const state = document.getElementById("hbqrs-refresh-state");
  let timer;
  function update() {{
    window.clearTimeout(timer);
    if (toggle.checked) {{
      state.textContent = "Automatic refresh is on; this page will update in about {refresh_seconds} seconds.";
      timer = window.setTimeout(function () {{ window.location.reload(); }}, {refresh_seconds * 1000});
    }} else {{
      state.textContent = "Automatic refresh is paused. Use your browser's refresh control when you want an update.";
    }}
  }}
  toggle.addEventListener("change", update);
  update();
}}());</script>"""
    expected = progress.get("expected_scopes")
    scope_total = "not known yet" if expected is None else str(expected)
    updated_at = progress.get("updated_at")
    updated_markup = (
        f'<time datetime="{esc(updated_at)}">{esc(updated_at)}</time>'
        if updated_at
        else "not recorded"
    )
    rows = "".join(
        "<tr>"
        f"<th scope=\"row\">{esc(item.get('scope_id'))}</th>"
        f"<td>{esc(item.get('status'))}</td>"
        f"<td>{esc(item.get('response_batches'))} / {esc(item.get('expected_batches') or '?')}</td>"
        "</tr>"
        for item in progress.get("scopes", [])
    ) or '<tr><td colspan="3">No binary scope has started.</td></tr>'
    data = json.dumps(progress, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>HBQ-RS workflow status</title>
<style>:root{{color-scheme:light dark;font:16px/1.5 system-ui,sans-serif}}*,*::before,*::after{{box-sizing:border-box}}body{{max-width:58rem;margin:auto;padding:2rem}}header,section{{border:1px solid #8886;border-radius:1rem;padding:1rem 1.25rem;margin:1rem 0}}.phase{{font-size:1.5rem;font-weight:750}}p,time{{overflow-wrap:anywhere}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{text-align:left;padding:.55rem;border-bottom:1px solid #8885;overflow-wrap:anywhere}}th:nth-child(1){{width:38%}}th:nth-child(2){{width:25%}}small,.refresh-state{{opacity:.75}}.refresh-control input{{margin-right:.45rem}}input:focus-visible{{outline:3px solid #f59e0b;outline-offset:2px}}@media (max-width:40rem){{body{{width:100%;margin:0;padding:.75rem}}header,section{{width:100%;padding:.75rem}}th,td{{padding:.45rem .35rem;font-size:.9rem}}}}</style></head><body>
<header><p>HBQ-RS long-form workflow</p><div class="phase">{esc(progress.get('phase', 'unknown')).title()}</div><p>{esc(progress.get('completed_scopes', 0))} of {esc(scope_total)} whole/local scopes complete.</p><p>Last updated: {updated_markup}</p>{refresh_controls}</header>
<section><h1>Persisted progress</h1><table><thead><tr><th>Scope</th><th>Status</th><th>Response batches</th></tr></thead><tbody>{rows}</tbody></table><p><small>Derived from checkpoint files. Refreshing or closing this page never controls the run.</small></p></section>
<script type="application/json" id="hbqrs-status-data">{data}</script></body></html>"""
