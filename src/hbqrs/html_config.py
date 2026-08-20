"""Offline setup-page renderer for HBQ-RS long-form workflows."""

from __future__ import annotations

from html import escape
import json
from typing import Any, Mapping, Sequence


def _text(value: Any) -> str:
    return escape(str(value), quote=True)


def _safe_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace(
        "<", "\\u003c"
    ).replace(">", "\\u003e").replace("&", "\\u0026")


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return sorted({item for item in value if isinstance(item, str) and item})


def _normalize_catalog(catalog: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Keep only the catalog fields required by the offline chooser."""

    if not isinstance(catalog, Mapping):
        raise ValueError("catalog must be a mapping with bundles and modules")

    def records(key: str, id_key: str) -> list[dict[str, Any]]:
        source = catalog.get(key, [])
        if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
            raise ValueError(f"catalog.{key} must be an array")
        cleaned: list[dict[str, Any]] = []
        for item in source:
            if not isinstance(item, Mapping) or not isinstance(item.get(id_key), str) or not item[id_key]:
                raise ValueError(f"catalog.{key} entries need a non-empty {id_key}")
            cleaned.append(
                {
                    id_key: item[id_key],
                    "title": item.get("title", item[id_key]) if isinstance(item.get("title", item[id_key]), str) else item[id_key],
                    "description": item.get("description", "") if isinstance(item.get("description", ""), str) else "",
                    "artifact_types": _strings(item.get("artifact_types")),
                    "valid_scopes": _strings(item.get("valid_scopes")),
                    "module_ids": _strings(item.get("module_ids")),
                }
            )
        return sorted(cleaned, key=lambda record: record[id_key])

    return {"bundles": records("bundles", "bundle_id"), "modules": records("modules", "module_id")}


def _css() -> str:
    return """
*{box-sizing:border-box}body{margin:0;background:#eef2f7;color:#172033;font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow-wrap:anywhere}main{max-width:70rem;margin:0 auto;padding:1.5rem}header,section{background:#fff;border:1px solid #cbd5e1;border-radius:12px;padding:1rem;margin:1rem 0;min-width:0}h1,h2,h3{margin:.1rem 0 .6rem}.muted{color:#526174}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(14rem,100%),1fr));gap:.75rem}.grid label{display:block;font-weight:650;min-width:0}input,select,textarea{font:inherit;max-width:100%;min-width:0;padding:.4rem;border:1px solid #64748b;border-radius:5px}select{width:100%}textarea{width:100%;min-height:7rem;white-space:pre;overflow:auto}fieldset{border:1px solid #cbd5e1;border-radius:8px;margin:.75rem 0;padding:.75rem;min-width:0}legend{font-weight:700}.choice{display:inline-flex;align-items:flex-start;gap:.3rem;margin-right:1rem;font-weight:600;max-width:100%}.choice input{max-width:none;flex:0 0 auto;margin-top:.25rem}button{font:inherit;font-weight:650;padding:.45rem .7rem;border:1px solid #176b87;background:#176b87;color:#fff;border-radius:5px;cursor:pointer}button:hover{background:#0f5068}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #f59e0b;outline-offset:2px}.actions{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:.75rem}.panel{background:#f7f9fc;border-left:4px solid #176b87;padding:.75rem;margin:.75rem 0}.module-tree{list-style:none;margin:.6rem 0;padding:0}.module-tree details{border:1px solid #cbd5e1;border-radius:6px;background:#f7f9fc;margin:.45rem 0;padding:.35rem .55rem}.module-tree summary{cursor:pointer;font-weight:700}.module-tree ul{list-style:none;margin:.45rem 0 0;padding-left:1rem}.module-tree li{margin:.3rem 0}.module-tree label{display:inline-flex;align-items:flex-start;gap:.35rem;max-width:100%}.module-tree input{max-width:none;margin-top:.2rem;flex:0 0 auto}.module-search-status{display:block;margin:.35rem 0}.error{color:#9f1239;font-weight:650}code{overflow-wrap:anywhere}@media (max-width:40rem){main{padding:.75rem}header,section{padding:.75rem}}@media print{body{background:#fff}main{max-width:none;padding:0}.screen-only,button{display:none!important}header,section{break-inside:avoid;border-color:#777}}
""".strip()


def _script() -> str:
    return r"""
(() => {
  'use strict';
  const catalog = JSON.parse(document.getElementById('hbqrs-catalog-data').textContent);
  const $ = (id) => document.getElementById(id);
  const choices = (id) => Array.from($(id).selectedOptions).map((item) => item.value);
  const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };
  const option = (value, label) => { const node = document.createElement('option'); node.value = value; node.textContent = label; return node; };
  const appendOptions = (id, values, fallback) => { const node = $(id); clear(node); const list = values.length ? values : [fallback]; list.forEach((value) => node.append(option(value, value))); if (list.includes(fallback)) node.value = fallback; };
  const selectedBundle = () => catalog.bundles.find((bundle) => bundle.bundle_id === $('hbqrs-bundle').value) || null;
  const updateModules = () => {
    const bundle = selectedBundle(); const list = $('hbqrs-modules'); clear(list);
    if (!bundle) { const item = document.createElement('li'); item.textContent = 'No catalog bundle is available.'; list.append(item); return; }
    const groups = new Map();
    [...bundle.module_ids].sort().forEach((id) => {
      const module = catalog.modules.find((entry) => entry.module_id === id); const groupId = id.split('.', 1)[0] || 'other';
      if (!groups.has(groupId)) groups.set(groupId, []); groups.get(groupId).push({id, module});
    });
    [...groups.entries()].forEach(([groupId, entries]) => {
      const group = document.createElement('li'); group.dataset.hbqrsModuleGroup = groupId;
      const details = document.createElement('details'); details.open = true;
      const summary = document.createElement('summary'); summary.textContent = `${groupId.replace(/_/g, ' ')} (${entries.length})`;
      const branch = document.createElement('ul'); branch.setAttribute('role', 'group');
      entries.forEach(({id, module}) => {
        const item = document.createElement('li'); item.dataset.hbqrsModuleRow = id;
        const label = document.createElement('label'); const input = document.createElement('input');
        input.type = 'checkbox'; input.name = 'frozen-module'; input.value = id; input.checked = true; input.addEventListener('change', render);
        const title = module ? module.title : id; const description = module && module.description ? ` — ${module.description}` : '';
        label.append(input, document.createTextNode(` ${title} (${id})${description}`)); item.append(label); branch.append(item);
      });
      details.append(summary, branch); group.append(details); list.append(group);
    });
    filterModules();
  };
  const filterModules = () => {
    const query = $('hbqrs-module-search').value.trim().toLocaleLowerCase(); let visible = 0;
    document.querySelectorAll('[data-hbqrs-module-row]').forEach((row) => { const matches = !query || row.textContent.toLocaleLowerCase().includes(query); row.hidden = !matches; if (matches) visible += 1; });
    document.querySelectorAll('[data-hbqrs-module-group]').forEach((group) => { group.hidden = !Array.from(group.querySelectorAll('[data-hbqrs-module-row]')).some((row) => !row.hidden); });
    $('hbqrs-module-search-status').textContent = `${visible} compatible module${visible === 1 ? '' : 's'} shown.`;
  };
  const updateBundleMode = () => { $('hbqrs-bundle-wrap').hidden = document.querySelector('input[name="bundle-mode"]:checked').value !== 'frozen'; };
  const updateCoverage = () => { $('hbqrs-sample-wrap').hidden = document.querySelector('input[name="coverage-mode"]:checked').value !== 'sampled'; };
  const number = (id) => Number($(id).value);
  const finitePositiveInteger = (value) => Number.isInteger(value) && value > 0;
  const headingPattern = /^(?:#{1,6}\s*)?(?:(?:chapter|chap\.?|part|book)\s+(?:[0-9]+|[ivxlcdm]+|[a-z]+)(?:\s*[:.\-—]\s*.+)?|(?:prologue|epilogue|interlude|afterword)(?:\s*[:.\-—]\s*.+)?)(?:\s*)$/i;
  const previewFile = async () => {
    const file = $('hbqrs-manuscript').files[0]; const select = $('hbqrs-unfinished-ordinal'); clear(select); select.append(option('', 'No unfinished unit selected'));
    if (!file) { $('hbqrs-file-status').textContent = 'No local file selected.'; return; }
    try {
      const text = await file.text(); const headingLines = text.split(/\r?\n/).map((line, index) => ({line, index})).filter((item) => headingPattern.test(item.line.trim()));
      const units = headingLines.length ? [...(headingLines[0].index > 0 ? ['Front matter'] : []), ...headingLines.map((item) => item.line)] : ['Whole supplied text'];
      units.forEach((heading, index) => select.append(option(String(index + 1), `Unit ${index + 1}: ${heading.replace(/^#+\s*/, '')}`)));
      $('hbqrs-file-status').textContent = `${units.length} deterministic-looking unit(s) previewed locally from ${file.name}. The text is not uploaded, stored, or included in the downloaded configuration.`;
    } catch (error) { $('hbqrs-file-status').textContent = 'The selected file could not be read locally.'; }
  };
  const profile = () => {
    if (!$('hbqrs-profile-enabled').checked) return null;
    const profileId = $('hbqrs-profile-id').value.trim() || 'workflow-profile';
    const value = {profile_version: 1, profile_id: profileId, global_weight: number('hbqrs-global-weight'), local_weight: number('hbqrs-local-weight'), local_reducer: $('hbqrs-local-reducer').value};
    if (number('hbqrs-prologue-epilogue-weight') !== 1) value.prologue_epilogue_weight = number('hbqrs-prologue-epilogue-weight');
    const ordinal = $('hbqrs-unfinished-ordinal').value;
    const binding = ordinal ? {unfinished_unit_ordinal: Number(ordinal), unfinished_unit_weight: number('hbqrs-unfinished-weight')} : null;
    return {profile: value, pending_ordinal_binding: binding};
  };
  const localInput = (id) => {
    const file = $(id).files[0];
    return {selected: Boolean(file), filename: file ? file.name : null, content_in_config: false};
  };
  const config = () => {
    const coverage = document.querySelector('input[name="coverage-mode"]:checked').value;
    const bundleMode = document.querySelector('input[name="bundle-mode"]:checked').value;
    const selectedModules = Array.from(document.querySelectorAll('input[name="frozen-module"]:checked')).map((node) => node.value);
    return {config_version: 1, route: {artifact_kind: $('hbqrs-artifact-kind').value, declared_scope: $('hbqrs-scope').value, completion_status: $('hbqrs-completion').value, bundle_mode: bundleMode, frozen_bundle_id: bundleMode === 'frozen' ? $('hbqrs-bundle').value : null, frozen_module_ids: bundleMode === 'frozen' ? selectedModules : []}, route_inputs: {artifact: localInput('hbqrs-manuscript'), originating_prompt: {filename: 'hbqrs-originating-prompt.txt', provided: Boolean($('hbqrs-originating-prompt').value.trim()), content_in_config: false}, judging_brief: {filename: 'hbqrs-judging-brief.txt', provided: Boolean($('hbqrs-judging-brief').value.trim()), content_in_config: false}}, local_evaluation: {coverage_mode: coverage, local_sample_limit: coverage === 'sampled' ? number('hbqrs-sample-limit') : null}, execution: {binary_workers: number('hbqrs-binary-workers'), provider: $('hbqrs-provider').value, model: $('hbqrs-model').value.trim(), base_url: $('hbqrs-base-url').value.trim(), openai_structured_outputs: $('hbqrs-structured').checked, structured_reasoning: $('hbqrs-structured-reasoning').value, judge_reasoning: $('hbqrs-judge-reasoning').value, plan_only: $('hbqrs-plan-only').checked}, outputs: {html_report: $('hbqrs-html-report').checked}, hierarchical_score: profile()};
  };
  const quote = (value) => JSON.stringify(String(value));
  const command = (value) => {
    const route = value.route; const execution = value.execution; const local = value.local_evaluation;
    const parts = ['cwr', 'longform', quote(value.route_inputs.artifact.filename || '<manuscript.txt>'), '--artifact-kind', quote(route.artifact_kind), '--scope', quote(route.declared_scope), route.completion_status === 'work_in_progress' ? '--wip' : '--completion-status', route.completion_status === 'work_in_progress' ? '' : route.completion_status, '--provider', execution.provider, '--model', quote(execution.model || '<model>'), '--output-dir', quote('cwr-output'), '--binary-workers', String(execution.binary_workers), '--structured-reasoning', execution.structured_reasoning, '--judge-reasoning', execution.judge_reasoning];
    if (execution.provider === 'openai' && execution.base_url) parts.push('--base-url', quote(execution.base_url));
    if (route.bundle_mode === 'frozen' && route.frozen_bundle_id) parts.push('--bundle', route.frozen_bundle_id);
    if (route.bundle_mode === 'frozen') route.frozen_module_ids.forEach((id) => parts.push('--module', id));
    if ($('hbqrs-judging-brief').value.trim()) parts.push('--brief', quote('hbqrs-judging-brief.txt'));
    if ($('hbqrs-originating-prompt').value.trim()) parts.push('--driving-prompt-file', quote('hbqrs-originating-prompt.txt'));
    if (local.coverage_mode === 'sampled') parts.push('--local-sample-limit', String(local.local_sample_limit));
    if (execution.openai_structured_outputs) parts.push('--openai-structured-outputs');
    if (value.outputs.html_report) parts.push('--html-report');
    if (value.hierarchical_score) parts.push('--hierarchical-score-profile', quote('profile.json'));
    if (execution.plan_only) parts.push('--plan-only');
    return parts.filter(Boolean).join(' ');
  };
  const validate = (value) => {
    const weights = value.hierarchical_score ? [value.hierarchical_score.profile.global_weight, value.hierarchical_score.profile.local_weight, value.hierarchical_score.profile.prologue_epilogue_weight ?? 1, value.hierarchical_score.pending_ordinal_binding?.unfinished_unit_weight ?? 1] : [];
    if (!finitePositiveInteger(value.execution.binary_workers)) return 'Binary workers must be a positive whole number.';
    if (value.route.bundle_mode === 'frozen' && !value.route.frozen_module_ids.length) return 'A frozen bundle needs at least one selected module.';
    if (value.local_evaluation.coverage_mode === 'sampled' && !finitePositiveInteger(value.local_evaluation.local_sample_limit)) return 'An explicit sampled run needs a positive local sample limit.';
    if (!value.execution.model) return 'Choose a model before exporting a command.';
    if (value.hierarchical_score && (!/^[a-z0-9_.-]+$/.test(value.hierarchical_score.profile.profile_id) || !weights.every((weight) => Number.isFinite(weight) && weight >= 0) || !(value.hierarchical_score.profile.global_weight + value.hierarchical_score.profile.local_weight > 0))) return 'Use a lowercase profile ID and finite non-negative profile weights with a positive global/local total.';
    return '';
  };
  const render = () => { const value = config(); const issue = validate(value); $('hbqrs-config-output').value = JSON.stringify(value, null, 2) + '\n'; $('hbqrs-command-output').value = command(value); $('hbqrs-status').textContent = issue || 'Configuration preview only. No command has run and no manuscript text leaves this page.'; $('hbqrs-status').className = issue ? 'error' : 'muted'; return issue ? null : value; };
  const downloadTextFile = (id, filename) => { const text = $(id).value; if (!text) { $('hbqrs-status').textContent = `Enter text before downloading ${filename}.`; $('hbqrs-status').className = 'error'; return; } const blob = new Blob([text], {type: 'text/plain;charset=utf-8'}); const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(blob); anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(anchor.href); };
  const download = () => { const value = render(); if (!value) return; const blob = new Blob([JSON.stringify(value, null, 2) + '\n'], {type: 'application/json'}); const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(blob); anchor.download = 'hbqrs-longform-config.json'; document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(anchor.href); };
  const initial = () => {
    const kinds = [...new Set(catalog.bundles.flatMap((bundle) => bundle.artifact_types))]; const scopes = [...new Set(catalog.bundles.flatMap((bundle) => bundle.valid_scopes))];
    appendOptions('hbqrs-artifact-kind', kinds.sort(), 'prose_fiction'); appendOptions('hbqrs-scope', scopes.sort(), 'manuscript');
    const bundle = $('hbqrs-bundle'); clear(bundle); catalog.bundles.forEach((item) => bundle.append(option(item.bundle_id, `${item.title} (${item.bundle_id})`))); updateModules(); updateBundleMode(); updateCoverage(); render();
  };
  document.querySelectorAll('input,select').forEach((node) => node.addEventListener('input', render));
  document.querySelectorAll('input[name="bundle-mode"]').forEach((node) => node.addEventListener('change', () => { updateBundleMode(); render(); }));
  document.querySelectorAll('input[name="coverage-mode"]').forEach((node) => node.addEventListener('change', () => { updateCoverage(); render(); }));
  $('hbqrs-bundle').addEventListener('change', () => { updateModules(); render(); }); $('hbqrs-module-search').addEventListener('input', filterModules); $('hbqrs-manuscript').addEventListener('change', async () => { await previewFile(); render(); }); $('hbqrs-originating-prompt').addEventListener('input', render); $('hbqrs-judging-brief').addEventListener('input', render); $('hbqrs-download').addEventListener('click', download); $('hbqrs-download-prompt').addEventListener('click', () => downloadTextFile('hbqrs-originating-prompt', 'hbqrs-originating-prompt.txt')); $('hbqrs-download-brief').addEventListener('click', () => downloadTextFile('hbqrs-judging-brief', 'hbqrs-judging-brief.txt')); $('hbqrs-select-command').addEventListener('click', () => { $('hbqrs-command-output').focus(); $('hbqrs-command-output').select(); });
  initial();
})();
""".strip()


def render_workflow_configurator(
    catalog: Mapping[str, Any], *, title: str = "HBQ-RS long-form workflow setup"
) -> str:
    """Render a self-contained local configuration page from a compact catalog.

    The page merely prepares downloadable configuration data and a command
    preview. Its optional file picker reads a user-selected file in-browser to
    offer a non-persistent heading/ordinal preview; it never transmits text.
    """

    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    clean_catalog = _normalize_catalog(catalog)
    document = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title><style>__CSS__</style></head><body><main>
<header><h1>__TITLE__</h1><p class="muted">Prepare an inspectable local workflow. This page does not run a judge, retain a draft, or send anything across the network.</p></header>
<section aria-labelledby="hbqrs-route-title"><h2 id="hbqrs-route-title">Artifact and route</h2><div class="grid"><label for="hbqrs-artifact-kind">Artifact kind<select id="hbqrs-artifact-kind"></select></label><label for="hbqrs-scope">Declared scope<select id="hbqrs-scope"></select></label><label for="hbqrs-completion">Completion status<select id="hbqrs-completion"><option value="work_in_progress">Work in progress</option><option value="complete">Complete</option><option value="excerpt">Excerpt</option><option value="unknown">Unknown</option></select></label></div><fieldset><legend>Bundle selection</legend><label class="choice"><input type="radio" name="bundle-mode" value="automatic" checked> Automatic route selection (LLM via the configured endpoint)</label><label class="choice"><input type="radio" name="bundle-mode" value="frozen"> Freeze this bundle</label><div id="hbqrs-bundle-wrap"><label for="hbqrs-bundle">Frozen bundle<select id="hbqrs-bundle"></select></label><h3>Confirm compatible modules</h3><p class="muted">Automatic routing remains a complete first-class route. It asks the configured model to choose from the local catalog, then the runner validates every ID and scope deterministically. In a frozen route, all modules from the selected compatible bundle start checked; clear one only for a deliberate controlled evaluation.</p><label for="hbqrs-module-search">Search this bundle's modules<input id="hbqrs-module-search" type="search" autocomplete="off" placeholder="Title, ID, or description"></label><output id="hbqrs-module-search-status" class="muted module-search-status" aria-live="polite"></output><ul id="hbqrs-modules" class="module-tree" aria-label="Compatible frozen-module checklist"></ul></div></fieldset></section>
<section aria-labelledby="hbqrs-inputs-title"><h2 id="hbqrs-inputs-title">Pre-run context</h2><p class="muted">When you run the generated command, automatic routing sends the declared bounded writing sample, optional originating prompt, and judging brief to the configured model. This static page itself only previews headings locally and never contacts the endpoint.</p><label for="hbqrs-manuscript">Local writing sample<input id="hbqrs-manuscript" type="file" accept="text/plain,.txt,.md"></label><p id="hbqrs-file-status" class="muted">No local file selected.</p><label for="hbqrs-originating-prompt">Optional originating prompt<textarea id="hbqrs-originating-prompt" placeholder="The prompt that originally drove this draft"></textarea></label><div class="actions"><button id="hbqrs-download-prompt" type="button">Download originating prompt as UTF-8 text</button></div><label for="hbqrs-judging-brief">Optional natural-language judging brief<textarea id="hbqrs-judging-brief" placeholder="What should this evaluation prioritize?"></textarea></label><div class="actions"><button id="hbqrs-download-brief" type="button">Download judging brief as UTF-8 text</button></div><p class="muted">Configuration records only whether these inputs exist and the proposed local filenames. Download the prompt or brief text files before running the generated command.</p></section>
<section aria-labelledby="hbqrs-local-title"><h2 id="hbqrs-local-title">Local coverage</h2><fieldset><legend>Coverage policy</legend><label class="choice"><input type="radio" name="coverage-mode" value="complete" checked> Complete: every substantive unit</label><label class="choice"><input type="radio" name="coverage-mode" value="sampled"> Explicit sampled limit</label><label id="hbqrs-sample-wrap" for="hbqrs-sample-limit">Sampled local-unit limit<input id="hbqrs-sample-limit" type="number" min="1" step="1" value="4"></label></fieldset><label for="hbqrs-binary-workers">Binary workers<input id="hbqrs-binary-workers" type="number" min="1" step="1" value="1"></label></section>
<section aria-labelledby="hbqrs-provider-title"><h2 id="hbqrs-provider-title">Judge connection</h2><div class="grid"><label for="hbqrs-provider">Provider<select id="hbqrs-provider"><option value="openai">OpenAI-compatible endpoint</option><option value="codex">Codex CLI</option></select></label><label for="hbqrs-model">Model<input id="hbqrs-model" required placeholder="model identifier"></label><label for="hbqrs-base-url">Base URL (OpenAI-compatible only)<input id="hbqrs-base-url" value="http://127.0.0.1:8000/v1"></label><label for="hbqrs-structured-reasoning">Structured-pass reasoning<select id="hbqrs-structured-reasoning"><option>low</option><option>medium</option><option selected>high</option><option>xhigh</option><option>max</option></select></label><label for="hbqrs-judge-reasoning">Binary-judge reasoning<select id="hbqrs-judge-reasoning"><option>low</option><option selected>medium</option><option>high</option><option>xhigh</option><option>max</option></select></label></div><label class="choice"><input id="hbqrs-structured" type="checkbox"> Request OpenAI Structured Outputs when the endpoint supports them</label><p class="muted">Credentials are intentionally not collected here. Configure the chosen provider outside this static page.</p></section>
<section aria-labelledby="hbqrs-profile-title"><h2 id="hbqrs-profile-title">Optional custom headline profile</h2><label class="choice"><input id="hbqrs-profile-enabled" type="checkbox"> Include a separate global-plus-local custom composite</label><div class="grid"><label for="hbqrs-profile-id">Profile ID<input id="hbqrs-profile-id" value="workflow-profile" pattern="[a-z0-9_.-]+"></label><label for="hbqrs-global-weight">Global requested weight<input id="hbqrs-global-weight" type="number" min="0" step="0.1" value="1"></label><label for="hbqrs-local-weight">Local requested weight<input id="hbqrs-local-weight" type="number" min="0" step="0.1" value="1"></label><label for="hbqrs-local-reducer">Local reducer<select id="hbqrs-local-reducer"><option value="weighted_mean">Weighted mean</option><option value="weakest_unit">Weakest unit</option></select></label><label for="hbqrs-unfinished-weight">Shared unfinished-unit modifier<input id="hbqrs-unfinished-weight" type="number" min="0" step="0.1" value="1"></label><label for="hbqrs-prologue-epilogue-weight">Shared prologue/epilogue modifier<input id="hbqrs-prologue-epilogue-weight" type="number" min="0" step="0.1" value="1"></label></div><label for="hbqrs-unfinished-ordinal">Unfinished unit ordinal<select id="hbqrs-unfinished-ordinal"><option value="">No unfinished unit selected</option></select></label><p class="muted">Ordinary units remain equal-weight. The optional ordinal is a pending local binding only: a runner must map it to the deterministic unit ID before making a strict profile.</p></section>
<section aria-labelledby="hbqrs-output-title"><h2 id="hbqrs-output-title">Outputs and plan-only review</h2><label class="choice"><input id="hbqrs-html-report" type="checkbox" checked> Write self-contained report and scorecard HTML</label><label class="choice"><input id="hbqrs-plan-only" type="checkbox" checked> Plan-only review first (render the command with <code>--plan-only</code>)</label></section>
<section aria-labelledby="hbqrs-export-title"><h2 id="hbqrs-export-title">Review and export</h2><p id="hbqrs-status" aria-live="polite" class="muted"></p><label for="hbqrs-config-output">Workflow configuration preview<textarea id="hbqrs-config-output" readonly></textarea></label><div class="actions"><button id="hbqrs-download" type="button">Download configuration JSON</button></div><label for="hbqrs-command-output">Copyable command preview<textarea id="hbqrs-command-output" readonly></textarea></label><div class="actions"><button id="hbqrs-select-command" type="button">Select command for copying</button></div><p class="muted">The command preview is not executed. If a profile uses an unfinished ordinal, bind it during workflow setup and write the resulting strict profile before running the shown profile flag.</p></section>
</main><script id="hbqrs-catalog-data" type="application/json">__CATALOG__</script><script>__SCRIPT__</script></body></html>"""
    replacements = {"__TITLE__": _text(title), "__CSS__": _css(), "__CATALOG__": _safe_json(clean_catalog), "__SCRIPT__": _script()}
    for marker, value in replacements.items():
        document = document.replace(marker, value)
    return document
