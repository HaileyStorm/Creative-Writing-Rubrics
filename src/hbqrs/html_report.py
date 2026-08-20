"""Offline HTML renderers for strict HBQ-RS long-form reports.

The rendered document is a view over a report JSON object.  Its browser-only
weighting editor creates an explicitly non-canonical profile preview; it never
writes back to the report or sends data anywhere.
"""

from __future__ import annotations

from html import escape
import json
from typing import Any, Mapping, Sequence

from .longform import _schema, _validate_schema


def _validate_report(report: Mapping[str, Any]) -> None:
    _validate_schema(report, _schema("hbq_long_form_workflow_report.schema.json"), "Long-form workflow report")


def _text(value: Any) -> str:
    return escape(str(value), quote=True)


def _score_text(score: Mapping[str, Any] | None) -> str:
    if not isinstance(score, Mapping):
        return "Not observed"
    return f"{float(score['observed']):.1f}"


def _bounds_text(score: Mapping[str, Any] | None) -> str:
    if not isinstance(score, Mapping):
        return "Not available"
    return f"{float(score['lower']):.1f}\u2013{float(score['upper']):.1f}"


def _result_score(result: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    return result.get("score") if isinstance(result, Mapping) else None


def _percent(value: Any) -> str:
    return f"{float(value):.1%}"


def _completion_label(report: Mapping[str, Any]) -> str:
    status = str(report["completion_contract"]["completion_status"])
    return "Work in progress" if status == "work_in_progress" else status.replace("_", " ").title()


def _safe_json(value: Mapping[str, Any]) -> str:
    """Serialize data for a script element without allowing tag termination."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace(
        "<", "\\u003c"
    ).replace(">", "\\u003e").replace("&", "\\u0026")


def _scorecard_css() -> str:
    return """
.hbqrs-scorecard{--hbq-ink:#172033;--hbq-muted:#546177;--hbq-line:#cad2de;--hbq-panel:#f7f9fc;--hbq-accent:#176b87;color:var(--hbq-ink);background:#fff;border:1px solid var(--hbq-line);border-radius:12px;padding:1rem;font:16px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:58rem}.hbqrs-scorecard *{box-sizing:border-box}.hbqrs-scorecard h2,.hbqrs-scorecard h3{margin:.1rem 0 .55rem}.hbqrs-scorecard p{margin:.35rem 0}.hbqrs-scorecard a{color:#0f607c;text-underline-offset:.15em}.hbqrs-scorecard__scores{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.75rem;margin:.75rem 0}.hbqrs-scorecard__score{background:var(--hbq-panel);border-left:4px solid var(--hbq-accent);padding:.7rem}.hbqrs-scorecard__value{font-size:1.55rem;font-weight:700}.hbqrs-scorecard dl{display:grid;grid-template-columns:max-content 1fr;gap:.25rem .75rem;margin:.75rem 0}.hbqrs-scorecard dt{font-weight:650}.hbqrs-scorecard dd{margin:0;color:var(--hbq-muted)}.hbqrs-scorecard ul{margin:.35rem 0;padding-left:1.25rem}.hbqrs-scorecard details{border-top:1px solid var(--hbq-line);margin-top:.65rem;padding-top:.55rem}.hbqrs-scorecard summary{cursor:pointer;font-weight:650}.hbqrs-scorecard summary:focus-visible{outline:3px solid #f59e0b;outline-offset:2px}.hbqrs-scorecard__note{color:var(--hbq-muted);font-size:.93rem}.hbqrs-scorecard__footer{border-top:1px solid var(--hbq-line);margin-top:.9rem!important;padding-top:.65rem}.hbqrs-scorecard__table{width:100%;border-collapse:collapse;margin:.5rem 0;font-size:.93rem}.hbqrs-scorecard__table th,.hbqrs-scorecard__table td{padding:.35rem;border-bottom:1px solid var(--hbq-line);text-align:left}.hbqrs-scorecard__table th[scope=row]{font-weight:650}@media (max-width:36rem){.hbqrs-scorecard{padding:.75rem}.hbqrs-scorecard__table{font-size:.82rem}.hbqrs-scorecard__table th,.hbqrs-scorecard__table td{padding:.25rem}}
""".strip()


def _hierarchy_card(hierarchy: Mapping[str, Any] | None) -> str:
    if not isinstance(hierarchy, Mapping):
        return ""
    global_component = hierarchy["global_component"]
    local_component = hierarchy["local_component"]
    assignments = local_component["unit_weight_assignments"]
    modifiers = [assignment for assignment in assignments if assignment["weight_class"] != "ordinary"]
    weights = ""
    if modifiers:
        items = "".join(
            "<li>{}: <code>{}</code>; modifier {}, effective {}</li>".format(
                _text(str(assignment["weight_class"]).replace("_", " ")),
                _text(assignment["unit_id"]),
                _text(f"{float(assignment['class_modifier']):.6g}"),
                _text(_percent(assignment["effective_weight"])),
            )
            for assignment in modifiers
        )
        weights = f"<p><strong>Active local-unit modifiers</strong></p><ul>{items}</ul>"
    weakest = local_component.get("selected_weakest_unit_id")
    weakest_text = (
        f" Weakest selected unit: <code>{_text(weakest)}</code>." if weakest is not None else ""
    )
    return """
<div class="hbqrs-scorecard__score" aria-label="Custom-weighted composite">
  <strong>Custom-weighted composite</strong>
  <div class="hbqrs-scorecard__value">{score}</div>
  <div>Bounds: {bounds}</div>
  <p class="hbqrs-scorecard__note">Profile <code>{profile}</code>; global effective weight {global_weight}, local effective weight {local_weight}; local reducer <code>{reducer}</code>.{weakest}</p>
  {weights}
</div>
""".format(
        score=_text(_score_text(hierarchy["score"])),
        bounds=_text(_bounds_text(hierarchy["score"])),
        profile=_text(hierarchy["profile_id"]),
        global_weight=_text(_percent(global_component["effective_weight"])),
        local_weight=_text(_percent(local_component["effective_weight"])),
        reducer=_text(hierarchy["local_reducer"]),
        weakest=weakest_text,
        weights=weights,
    )


CARD_LAYOUTS = ("summary", "compact", "minimal")


def _scorecard_markup(report: Mapping[str, Any], *, layout: str = "summary") -> str:
    if layout not in CARD_LAYOUTS:
        raise ValueError(f"layout must be one of: {', '.join(CARD_LAYOUTS)}")
    global_result = report["global_result"]
    local_results = report["local_results"]
    hierarchy = report["hierarchical_score"]
    domains = global_result["domains"] if isinstance(global_result, Mapping) else []
    domain_rows = "".join(
        "<li>{}: {} ({}, bounds {})</li>".format(
            _text(domain["title"]),
            _text(_score_text(domain["score"])),
            _text(_percent(domain["coverage"])),
            _text(_bounds_text(domain["score"])),
        )
        for domain in domains
    ) or "<li>No whole-work domain scores were observed.</li>"
    local_summary = "No local unit scores were observed."
    observed_local = [result for result in local_results if isinstance(result.get("score"), Mapping)]
    if observed_local:
        weakest = min(enumerate(observed_local), key=lambda pair: (pair[1]["score"]["observed"], pair[0]))[1]
        local_summary = "{} local units; lowest observed local score: {} ({}, bounds {}).".format(
            len(local_results),
            _score_text(weakest["score"]),
            _text(weakest["label"]),
            _bounds_text(weakest["score"]),
        )
    state = global_result["control_state"] if isinstance(global_result, Mapping) else "Not available"
    coverage = _percent(global_result["coverage"]) if isinstance(global_result, Mapping) else "Not available"
    details = "" if layout == "minimal" else """
  <dl>
    <dt>Completion</dt><dd>{completion}</dd>
    <dt>Whole-work control state</dt><dd>{state}</dd>
    <dt>Whole-work coverage</dt><dd>{coverage}</dd>
    <dt>Local coverage</dt><dd>{local_mode} across {local_count} unit(s)</dd>
  </dl>
""".format(
        completion=_text(_completion_label(report)),
        state=_text(state),
        coverage=_text(coverage),
        local_mode=_text(report["route"]["local_coverage_mode"]),
        local_count=len(local_results),
    )
    breakdown = "" if layout != "summary" else """
  <details open>
    <summary>Whole-work domains ({domain_count})</summary>
    <ul>{domains}</ul>
  </details>
  <details open>
    <summary>Local trajectory</summary>
    <p>{local_summary}</p>
  </details>
""".format(domain_count=len(domains), domains=domain_rows, local_summary=local_summary)
    return """
<section class="hbqrs-scorecard" aria-labelledby="hbqrs-scorecard-title">
  <h2 id="hbqrs-scorecard-title">HBQ-RS scorecard</h2>
  <div class="hbqrs-scorecard__scores">
    {hierarchy}
    <div class="hbqrs-scorecard__score" aria-label="Canonical whole-work score">
      <strong>Canonical whole-work score</strong>
      <div class="hbqrs-scorecard__value">{global_score}</div>
      <div>Bounds: {global_bounds}</div>
    </div>
  </div>
  {details}
  {breakdown}
  <p class="hbqrs-scorecard__note">The canonical whole-work result remains separate. A custom-weighted composite is a declared view over existing intervals, never a replacement for the underlying results or their control states.</p>
  <p class="hbqrs-scorecard__note hbqrs-scorecard__footer"><a href="https://github.com/HaileyStorm/Creative-Writing-Rubrics">Creative-Writing-Rubrics</a> · <a href="https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/main/docs/DONATIONS.md">Support this project</a></p>
</section>
""".format(
        hierarchy=_hierarchy_card(hierarchy),
        global_score=_text(_score_text(_result_score(global_result))),
        global_bounds=_text(_bounds_text(_result_score(global_result))),
        details=details,
        breakdown=breakdown,
    )


def render_html_scorecard(report: Mapping[str, Any], *, layout: str = "summary") -> str:
    """Render an embeddable no-script scorecard with scoped styling.

    The charset declaration also makes the fragment safe to open directly as
    a standalone ``.html`` file without changing how it embeds in a document.
    """

    _validate_report(report)
    return f'<meta charset="utf-8"><style>{_scorecard_css()}</style>\n{_scorecard_markup(report, layout=layout)}'


def _table_rows(results: Sequence[Mapping[str, Any]]) -> str:
    return "".join(
        "<tr><th scope=\"row\">{}</th><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            _text(result["label"]),
            _text(result["control_state"]),
            _text(_percent(result["coverage"])),
            _text(_score_text(result["score"])),
            _text(_bounds_text(result["score"])),
        )
        for result in results
    )


def _domain_rows(result: Mapping[str, Any] | None) -> str:
    if not isinstance(result, Mapping):
        return "<tr><td colspan=\"4\">No whole-work result was observed.</td></tr>"
    return "".join(
        "<tr><th scope=\"row\">{}</th><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            _text(domain["title"]),
            _text(_percent(domain["coverage"])),
            _text(_score_text(domain["score"])),
            _text(_bounds_text(domain["score"])),
        )
        for domain in result["domains"]
    ) or "<tr><td colspan=\"4\">No whole-work domain scores were observed.</td></tr>"


def _finding_markup(findings: Sequence[Mapping[str, Any]]) -> str:
    if not findings:
        return "<p>No synthesis findings were recorded.</p>"
    chunks: list[str] = []
    for finding in findings:
        evidence = ", ".join(f"<code>{_text(item)}</code>" for item in finding["evidence_refs"])
        criteria = ", ".join(f"<code>{_text(item)}</code>" for item in finding["criterion_ids"])
        chunks.append(
            "<article class=\"hbqrs-finding\"><h3>{}: {}</h3><p>{}</p>"
            "<p><strong>Evidence references:</strong> {}<br><strong>Criteria:</strong> {}</p></article>".format(
                _text(str(finding["kind"]).replace("_", " ").title()),
                _text(finding["finding"]),
                _text(finding["why_it_matters"]),
                evidence,
                criteria,
            )
        )
    return "\n".join(chunks)


def _warning_markup(warnings: Sequence[Any]) -> str:
    if not warnings:
        return "<p>No warnings were recorded.</p>"
    return "<ul>" + "".join(f"<li>{_text(warning)}</li>" for warning in warnings) + "</ul>"


def _document_css() -> str:
    return _scorecard_css() + """
body{margin:0;background:#eef2f7;color:#172033;font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:72rem;margin:0 auto;padding:1.5rem}.hbqrs-report-header{margin-bottom:1.25rem}.hbqrs-report-header h1{margin:.1rem 0}.hbqrs-report-header p{max-width:70ch;color:#546177}section{background:#fff;border:1px solid #cad2de;border-radius:12px;padding:1rem;margin:1rem 0}h2{margin-top:.1rem}h3{margin-bottom:.35rem}table{border-collapse:collapse;width:100%;overflow-wrap:anywhere}th,td{border-bottom:1px solid #cad2de;padding:.45rem;text-align:left;vertical-align:top}th{background:#f7f9fc}th[scope=row]{font-weight:650}caption{text-align:left;font-weight:700;margin:.3rem 0}.hbqrs-finding{border-left:4px solid #176b87;padding:.1rem .8rem;margin:.75rem 0;background:#f7f9fc}.hbqrs-editor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(14rem,1fr));gap:.75rem}.hbqrs-editor-grid label{display:block;font-weight:650}.hbqrs-editor-grid input,.hbqrs-editor-grid select{font:inherit;max-width:100%;padding:.35rem;border:1px solid #64748b;border-radius:5px}.hbqrs-editor-actions{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:.75rem}button{font:inherit;font-weight:650;padding:.45rem .7rem;border:1px solid #176b87;background:#176b87;color:#fff;border-radius:5px;cursor:pointer}button:hover{background:#0f5068}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #f59e0b;outline-offset:2px}.hbqrs-preview{margin-top:1rem;padding:.75rem;background:#f7f9fc;border-left:4px solid #176b87}.hbqrs-error{color:#9f1239;font-weight:650}.hbqrs-muted{color:#546177}.hbqrs-screen-only{display:block}@media (max-width:40rem){main{padding:.75rem}section{padding:.75rem;overflow-x:auto}}@media print{body{background:#fff}main{max-width:none;padding:0}section,.hbqrs-scorecard{border-color:#777;break-inside:avoid}.hbqrs-screen-only{display:none!important}button{display:none}}
"""


def _editor_script() -> str:
    """Return static JS. Dynamic report strings are only assigned with textContent."""

    return r"""
(() => {
  'use strict';
  const report = JSON.parse(document.getElementById('hbqrs-report-data').textContent);
  const global = report.global_result;
  const locals = report.local_results || [];
  const $ = (id) => document.getElementById(id);
  const interval = (result) => result && result.score && Number.isFinite(Number(result.score.observed)) ? result.score : null;
  const number = (id) => Number($(id).value);
  const validWeight = (value) => Number.isFinite(value) && value >= 0;
  const fmt = (value) => Number(value).toFixed(1);
  const pct = (value) => `${(Number(value) * 100).toFixed(1)}%`;
  const weighted = (items, weights) => {
    const total = weights.reduce((sum, value) => sum + value, 0);
    if (!(total > 0)) return null;
    return ['observed', 'lower', 'upper'].reduce((output, key) => {
      output[key] = items.reduce((sum, item, index) => sum + Number(item[key]) * weights[index], 0) / total;
      return output;
    }, {});
  };
  const write = (id, value) => { $(id).textContent = value; };
  const profile = () => {
    const selected = new Set(Array.from($('hbqrs-unfinished-units').selectedOptions).map((option) => option.value));
    const modifier = number('hbqrs-unfinished-modifier');
    const value = {
      profile_version: 1,
      profile_id: $('hbqrs-profile-id').value.trim() || 'browser-preview',
      global_weight: number('hbqrs-global-weight'),
      local_weight: number('hbqrs-local-weight'),
      local_reducer: $('hbqrs-local-reducer').value,
    };
    if (selected.size) { value.unfinished_unit_ids = Array.from(selected); value.unfinished_unit_weight = modifier; }
    if (number('hbqrs-prologue-epilogue-modifier') !== 1) value.prologue_epilogue_weight = number('hbqrs-prologue-epilogue-modifier');
    return value;
  };
  const update = () => {
    const value = profile();
    const values = [value.global_weight, value.local_weight, number('hbqrs-unfinished-modifier'), number('hbqrs-prologue-epilogue-modifier')];
    if (!/^[a-z0-9_.-]+$/.test(value.profile_id) || !values.every(validWeight) || !(value.global_weight + value.local_weight > 0)) {
      write('hbqrs-preview-status', 'Use a lowercase profile ID and finite, non-negative weights with a positive global/local total.');
      $('hbqrs-preview-status').className = 'hbqrs-error';
      write('hbqrs-preview-value', 'Not available');
      return null;
    }
    const globalScore = interval(global);
    if (value.global_weight > 0 && !globalScore) {
      write('hbqrs-preview-status', 'A positive global weight requires a whole-work score interval.');
      $('hbqrs-preview-status').className = 'hbqrs-error';
      write('hbqrs-preview-value', 'Not available');
      return null;
    }
    const selectedUnfinished = new Set(value.unfinished_unit_ids || []);
    const modifierFor = (result) => selectedUnfinished.has(result.scope_id) ? value.unfinished_unit_weight : /^(prologue|epilogue)\b/i.test(result.label) ? (value.prologue_epilogue_weight === undefined ? 1 : value.prologue_epilogue_weight) : 1;
    const positive = locals.map((result, index) => [result, modifierFor(result), index]).filter((entry) => entry[1] > 0);
    if (value.local_weight > 0 && (!positive.length || positive.some((entry) => !interval(entry[0])))) {
      write('hbqrs-preview-status', 'A positive local weight requires at least one positive-weight local score interval.');
      $('hbqrs-preview-status').className = 'hbqrs-error';
      write('hbqrs-preview-value', 'Not available');
      return null;
    }
    let localScore = null;
    let weakest = null;
    const normalized = positive.reduce((sum, entry) => sum + entry[1], 0);
    if (value.local_weight > 0) {
      if (value.local_reducer === 'weakest_unit') {
        const selected = positive.reduce((best, entry) => !best || Number(interval(entry[0]).observed) < Number(interval(best[0]).observed) ? entry : best, null);
        localScore = interval(selected[0]);
        weakest = selected[0].scope_id;
      } else {
        localScore = weighted(positive.map((entry) => interval(entry[0])), positive.map((entry) => entry[1]));
      }
    }
    const components = [];
    const componentWeights = [];
    if (value.global_weight > 0) { components.push(globalScore); componentWeights.push(value.global_weight); }
    if (value.local_weight > 0) { components.push(localScore); componentWeights.push(value.local_weight); }
    const score = weighted(components, componentWeights);
    const total = value.global_weight + value.local_weight;
    write('hbqrs-preview-value', `${fmt(score.observed)} (bounds ${fmt(score.lower)}–${fmt(score.upper)})`);
    write('hbqrs-preview-components', `Effective global ${pct(value.global_weight / total)}; effective local ${pct(value.local_weight / total)}; reducer ${value.local_reducer}${weakest ? `; weakest ${weakest}` : ''}.`);
    const selectedLabels = Array.from($('hbqrs-unfinished-units').selectedOptions).map((option) => option.textContent).join(', ');
    const prologue = value.prologue_epilogue_weight === undefined ? '' : ` Shared prologue/epilogue modifier ${value.prologue_epilogue_weight.toFixed(3)}.`;
    const effectiveWeight = (result) => normalized > 0 ? pct(modifierFor(result) / normalized) : '0.0%';
    write('hbqrs-preview-weights', `${selectedLabels ? `Shared unfinished-unit modifier ${value.unfinished_unit_weight.toFixed(3)} for ${selectedLabels}.` : 'All ordinary local units retain equal requested weight.'}${prologue} Effective local weights: ${locals.map((result) => `${result.label}: ${effectiveWeight(result)}`).join(' · ')}`);
    write('hbqrs-preview-status', 'Preview calculated from existing intervals only. It is not the canonical whole-work score.');
    $('hbqrs-preview-status').className = 'hbqrs-muted';
    return value;
  };
  const addUnfinishedChoices = () => {
    const holder = $('hbqrs-unfinished-units');
    locals.forEach((result) => {
      const option = document.createElement('option'); option.value = result.scope_id; option.textContent = result.label; holder.append(option);
    });
  };
  $('hbqrs-global-weight').addEventListener('input', update);
  $('hbqrs-local-weight').addEventListener('input', update);
  $('hbqrs-local-reducer').addEventListener('change', update);
  $('hbqrs-profile-id').addEventListener('input', update);
  $('hbqrs-unfinished-modifier').addEventListener('input', update);
  $('hbqrs-unfinished-units').addEventListener('change', update);
  $('hbqrs-prologue-epilogue-modifier').addEventListener('input', update);
  $('hbqrs-download-profile').addEventListener('click', () => {
    const value = update(); if (!value) return;
    const blob = new Blob([JSON.stringify(value, null, 2) + '\n'], {type: 'application/json'});
    const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(blob);
    anchor.download = `${value.profile_id}.json`; document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(anchor.href);
  });
  const embeds = JSON.parse(document.getElementById('hbqrs-embed-data').textContent);
  const updateEmbed = () => { $('hbqrs-embed-code').value = embeds[$('hbqrs-card-layout').value]; };
  $('hbqrs-card-layout').addEventListener('change', updateEmbed);
  $('hbqrs-select-embed').addEventListener('click', () => { $('hbqrs-embed-code').focus(); $('hbqrs-embed-code').select(); });
  updateEmbed();
  addUnfinishedChoices(); update();
})();
""".strip()


def render_html_report(
    report: Mapping[str, Any], *, title: str = "HBQ-RS long-form evaluation"
) -> str:
    """Render a self-contained, offline interactive HTML report.

    The browser editor is an optional preview/export aid.  It derives a strict
    hierarchical-profile JSON object from the report's existing intervals and
    leaves the supplied report untouched.
    """

    _validate_report(report)
    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    orientation = report["orientation"]
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title><style>__CSS__</style></head><body><main>
<header class="hbqrs-report-header"><h1>__TITLE__</h1><p>__PREMISE__</p><p><strong>Evaluated scope:</strong> __SCOPE__</p></header>
__SCORECARD__
<section aria-labelledby="hbqrs-domains-title"><h2 id="hbqrs-domains-title">Whole-work domain breakdown</h2>
<table><caption>Domain scores and uncertainty bounds</caption><thead><tr><th scope="col">Domain</th><th scope="col">Coverage</th><th scope="col">Observed</th><th scope="col">Bounds</th></tr></thead><tbody>__DOMAIN_ROWS__</tbody></table></section>
<section aria-labelledby="hbqrs-locals-title"><h2 id="hbqrs-locals-title">Local trajectory</h2>
<table><caption>Independent local diagnostics</caption><thead><tr><th scope="col">Unit</th><th scope="col">Control state</th><th scope="col">Coverage</th><th scope="col">Observed</th><th scope="col">Bounds</th></tr></thead><tbody>__LOCAL_ROWS__</tbody></table>
<p class="hbqrs-muted">Local diagnostics do not overwrite or average into the canonical whole-work score. They show where the profile is strong, weak, or uneven.</p></section>
<section aria-labelledby="hbqrs-findings-title"><h2 id="hbqrs-findings-title">Findings and evidence references</h2>__FINDINGS__</section>
<section aria-labelledby="hbqrs-warnings-title"><h2 id="hbqrs-warnings-title">Warnings</h2>__WARNINGS__</section>
<section class="hbqrs-screen-only" aria-labelledby="hbqrs-editor-title"><h2 id="hbqrs-editor-title">Custom composite preview</h2>
<p>Use this optional view to combine existing global and local intervals under an explicit profile. It does not change the report, its control states, or the canonical whole-work score.</p>
<div class="hbqrs-editor-grid"><label for="hbqrs-profile-id">Profile ID<input id="hbqrs-profile-id" value="browser-preview" pattern="[a-z0-9_.-]+"></label><label for="hbqrs-global-weight">Global requested weight<input id="hbqrs-global-weight" type="number" min="0" step="0.1" value="1"></label><label for="hbqrs-local-weight">Local requested weight<input id="hbqrs-local-weight" type="number" min="0" step="0.1" value="1"></label><label for="hbqrs-local-reducer">Local reducer<select id="hbqrs-local-reducer"><option value="weighted_mean">Weighted mean</option><option value="weakest_unit">Weakest unit</option></select></label></div>
<div class="hbqrs-editor-grid"><label for="hbqrs-unfinished-modifier">Shared unfinished-unit modifier<input id="hbqrs-unfinished-modifier" type="number" min="0" step="0.1" value="1"></label><label for="hbqrs-unfinished-units">Units carrying that modifier<select id="hbqrs-unfinished-units" multiple size="4" aria-describedby="hbqrs-unfinished-help"></select></label><label for="hbqrs-prologue-epilogue-modifier">Shared prologue/epilogue modifier<input id="hbqrs-prologue-epilogue-modifier" type="number" min="0" step="0.1" value="1"></label></div><p id="hbqrs-unfinished-help" class="hbqrs-muted">Ordinary local chapters stay equal-weight. Select only units that are genuinely unfinished, then apply one shared modifier. The prologue/epilogue modifier applies only to deterministically recognized headings. Neither control enables arbitrary per-chapter tuning.</p>
<div class="hbqrs-preview" aria-live="polite"><h3>Non-canonical preview</h3><p id="hbqrs-preview-value">Not calculated</p><p id="hbqrs-preview-components"></p><p id="hbqrs-preview-weights"></p><p id="hbqrs-preview-status" class="hbqrs-muted"></p></div><div class="hbqrs-editor-actions"><button id="hbqrs-download-profile" type="button">Download strict profile JSON</button></div>
<p class="hbqrs-muted">Formula: reduce selected local intervals by the chosen local reducer, then take the requested global/local weighted mean. Unit weights are normalized inside the local component. Zero-weight units are excluded; weakest-unit selection uses the lowest observed local score, breaking ties by source order.</p></section>
<section class="hbqrs-screen-only" aria-labelledby="hbqrs-embed-title"><h2 id="hbqrs-embed-title">Embeddable scorecard</h2><p>Choose a fixed layout, then copy the complete self-contained fragment. No remote asset loads when the card renders; its repository and support links open only when selected.</p><label for="hbqrs-card-layout">Card layout<select id="hbqrs-card-layout"><option value="summary">Summary: scores, domains, and local trajectory</option><option value="compact">Compact: scores, control, and coverage</option><option value="minimal">Minimal: scores and disclosed weights</option></select></label><label for="hbqrs-embed-code">Embed code<textarea id="hbqrs-embed-code" readonly rows="10"></textarea></label><div class="hbqrs-editor-actions"><button id="hbqrs-select-embed" type="button">Select embed code for copying</button></div></section>
</main><script id="hbqrs-report-data" type="application/json">__DATA__</script><script id="hbqrs-embed-data" type="application/json">__EMBEDS__</script><script>__SCRIPT__</script></body></html>"""
    embeds = {layout: render_html_scorecard(report, layout=layout) for layout in CARD_LAYOUTS}
    replacements = {
        "__TITLE__": _text(title),
        "__CSS__": _document_css(),
        "__PREMISE__": _text(orientation["premise"]),
        "__SCOPE__": _text(orientation["evaluated_scope"]),
        "__SCORECARD__": _scorecard_markup(report),
        "__DOMAIN_ROWS__": _domain_rows(report["global_result"]),
        "__LOCAL_ROWS__": _table_rows(report["local_results"]),
        "__FINDINGS__": _finding_markup(report["findings"]),
        "__WARNINGS__": _warning_markup(report["warnings"]),
        "__DATA__": _safe_json(report),
        "__EMBEDS__": _safe_json(embeds),
        "__SCRIPT__": _editor_script(),
    }
    for marker, replacement in replacements.items():
        document = document.replace(marker, replacement)
    return document
