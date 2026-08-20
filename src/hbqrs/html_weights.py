"""Optional offline editor for strict bundle scoring-weight profiles."""

from __future__ import annotations

import html
import json
from typing import Any, Mapping, Sequence

from .weights import make_weight_profile


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")


def render_weight_configurator(
    modules: Sequence[dict[str, Any]],
    bundle: Mapping[str, Any],
    *,
    title: str = "HBQ-RS scoring weights",
) -> str:
    """Render a self-contained editor for every deterministic bundle weight layer."""

    profile = make_weight_profile(modules, bundle)
    esc = lambda value: html.escape(str(value), quote=True)
    module_titles = {str(item.get("module_id")): str(item.get("title", item.get("module_id"))) for item in modules}

    def inputs(collection: str, key_fields: tuple[str, ...], number_field: str) -> str:
        rows = []
        for index, record in enumerate(profile.get(collection, [])):
            identity = " / ".join(str(record[field]) for field in key_fields)
            module_id = record.get("module_id")
            label = module_titles.get(str(module_id), identity) if module_id else identity
            data = esc(json.dumps({field: record[field] for field in key_fields}, ensure_ascii=False))
            rows.append(
                f'<label class="weight-row" data-search="{esc((identity + " " + label).casefold())}">'
                f'<span><strong>{esc(label)}</strong><small>{esc(identity)}</small></span>'
                f'<input type="number" min="0" step="any" required data-collection="{collection}" '
                f'data-number-field="{number_field}" data-key="{data}" value="{esc(record[number_field])}"></label>'
            )
        return "".join(rows) or '<p class="muted">This bundle has no entries at this layer.</p>'

    sections = [
        ("Domains", "Relative inputs; downloaded profiles normalize the exact domain set to 100 points.", "domain_weights", ("domain_id",), "weight"),
        ("Components", "Weights of modules inside their bundle domains.", "component_weights", ("domain_id", "module_id"), "weight"),
        ("Groups", "Multipliers inherited by scored leaves below each group.", "group_weights", ("group_id",), "weight"),
        ("Questions", "Atomic scored-leaf weights. Supplemental and hard-gate-only leaves are excluded.", "question_weights", ("question_id",), "weight"),
        ("Penalty caps", "Maximum point deductions for penalty modules.", "penalty_caps", ("module_id",), "cap_points"),
    ]
    section_html = "".join(
        f'<details open><summary>{esc(heading)} <span class="count">{len(profile.get(collection, []))}</span></summary>'
        f'<p class="muted">{esc(description)}</p><div class="weights">{inputs(collection, keys, number)}</div></details>'
        for heading, description, collection, keys, number in sections
    )
    script = r"""
(() => {
  const $ = (id) => document.getElementById(id);
  const starter = JSON.parse($('hbqrs-weight-starter').textContent);
  const profile = () => {
    const result = {profile_version:1,profile_id:$('hbqrs-profile-id').value.trim(),bundle_id:starter.bundle_id};
    document.querySelectorAll('[data-collection]').forEach((input) => {
      const collection=input.dataset.collection; const item=JSON.parse(input.dataset.key);
      item[input.dataset.numberField]=Number(input.value); (result[collection] ||= []).push(item);
    });
    return result;
  };
  const validate = (value) => {
    if (!/^[a-z0-9_.-]+$/.test(value.profile_id)) return 'Profile ID must use lowercase letters, numbers, dot, underscore, or hyphen.';
    for (const [collection, rows] of Object.entries(value)) if (Array.isArray(rows)) for (const row of rows) for (const [key, number] of Object.entries(row)) if ((key==='weight'||key==='cap_points') && (!Number.isFinite(number)||number<0||(collection!=='domain_weights'&&collection!=='penalty_caps'&&number===0))) return `Invalid ${collection} value.`;
    if (value.domain_weights && value.domain_weights.reduce((sum,row)=>sum+row.weight,0)<=0) return 'Domain weights need a positive total.';
    return '';
  };
  const update = () => { const value=profile(); const error=validate(value); $('hbqrs-error').textContent=error; $('hbqrs-json').value=error?'':JSON.stringify(value,null,2)+'\n'; };
  const filter = () => { const query=$('hbqrs-search').value.trim().toLocaleLowerCase(); let shown=0; document.querySelectorAll('.weight-row').forEach((row)=>{row.hidden=!!query&&!row.dataset.search.includes(query);if(!row.hidden)shown+=1;});$('hbqrs-search-count').textContent=`${shown} weight${shown===1?'':'s'} shown.`; };
  document.querySelectorAll('input').forEach((input)=>input.addEventListener('input',()=>{update();filter();}));
  $('hbqrs-download').addEventListener('click',()=>{const value=profile();const error=validate(value);if(error){$('hbqrs-error').textContent=error;return;}const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'});const anchor=document.createElement('a');anchor.href=URL.createObjectURL(blob);anchor.download=`${value.profile_id}.json`;document.body.append(anchor);anchor.click();anchor.remove();URL.revokeObjectURL(anchor.href);});
  $('hbqrs-select').addEventListener('click',()=>{$('hbqrs-json').focus();$('hbqrs-json').select();}); update(); filter();
})();
"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>:root{{color-scheme:light dark;font:16px/1.5 system-ui,sans-serif}}body{{max-width:72rem;margin:auto;padding:1.25rem}}header,section,details{{border:1px solid #8886;border-radius:.75rem;padding:.8rem 1rem;margin:.8rem 0}}summary{{cursor:pointer;font-size:1.1rem;font-weight:750}}.count{{font-size:.8rem;opacity:.7}}.muted,small{{opacity:.75}}.weight-row{{display:grid;grid-template-columns:minmax(16rem,1fr) 8rem;gap:1rem;align-items:center;padding:.35rem;border-bottom:1px solid #8884}}.weight-row span,.weight-row small{{display:block}}input,textarea,button{{font:inherit}}input[type=number],input[type=text],input[type=search]{{box-sizing:border-box;width:100%;padding:.35rem}}textarea{{box-sizing:border-box;width:100%;min-height:12rem}}button{{padding:.5rem .7rem;margin:.35rem .35rem .35rem 0}}:focus-visible{{outline:3px solid #e39b18;outline-offset:2px}}.error{{color:#c23;font-weight:700}}@media(max-width:38rem){{.weight-row{{grid-template-columns:1fr}}}}</style></head><body>
<header><p>Optional local configurator</p><h1>{esc(title)}</h1><p>Bundle <code>{esc(profile['bundle_id'])}</code>. Edit every deterministic scoring layer or keep the shipped defaults. There are no chapter/scene/unit weights here; author goals remain in the separate task contract.</p></header>
<section><label for="hbqrs-profile-id">Profile ID<input id="hbqrs-profile-id" type="text" value="custom" pattern="[a-z0-9_.-]+"></label><label for="hbqrs-search">Search weights<input id="hbqrs-search" type="search" placeholder="ID or module title"></label><output id="hbqrs-search-count" class="muted" aria-live="polite"></output><p id="hbqrs-error" class="error" role="alert"></p></section>
{section_html}
<section><h2>Strict profile JSON</h2><textarea id="hbqrs-json" readonly></textarea><button id="hbqrs-download" type="button">Download profile JSON</button><button id="hbqrs-select" type="button">Select JSON for copying</button><p class="muted">Use with <code>--weight-profile</code>; long-form local diagnostics can use a separate <code>--local-weight-profile</code> bound to their local bundle.</p></section>
<script id="hbqrs-weight-starter" type="application/json">{_safe_json(profile)}</script><script>{script}</script></body></html>"""
