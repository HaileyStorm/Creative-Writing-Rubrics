from copy import deepcopy

import pytest

from hbqrs.html_config import render_workflow_configurator


def _catalog():
    return {
        "bundles": [
            {
                "bundle_id": "prose.novel",
                "title": "Novel prose",
                "description": "A catalog-safe bundle description.",
                "artifact_types": ["prose_fiction"],
                "valid_scopes": ["manuscript", "chapter"],
                "module_ids": ["prose.scene_clarity", "prose.continuity"],
            }
        ],
        "modules": [
            {
                "module_id": "prose.scene_clarity",
                "title": "Scene clarity",
                "description": "Readable scene construction.",
                "artifact_types": ["prose_fiction"],
                "valid_scopes": ["manuscript", "chapter"],
            },
            {
                "module_id": "prose.continuity",
                "title": "Continuity",
                "description": "State remains legible.",
                "artifact_types": ["prose_fiction"],
                "valid_scopes": ["manuscript", "chapter"],
            },
        ],
    }


def test_configurator_is_deterministic_offline_and_self_contained():
    catalog = _catalog()
    first = render_workflow_configurator(catalog)
    assert first == render_workflow_configurator(catalog)
    assert "<script src=" not in first
    assert "<link rel=" not in first
    assert "https://" not in first
    assert "fetch(" not in first
    assert "XMLHttpRequest" not in first
    assert "localStorage" not in first
    assert "sessionStorage" not in first
    assert "innerHTML" not in first
    assert "eval(" not in first
    assert "file.text()" in first
    assert "No command has run" in first


def test_configurator_exposes_requested_controls_and_command_preview():
    output = render_workflow_configurator(_catalog())
    for text in (
        "Work in progress",
        "Automatic route selection",
        "Freeze this bundle",
        "Complete: every substantive unit",
        "Explicit sampled limit",
        "Binary workers",
        "OpenAI-compatible endpoint",
        "Base URL",
        "Structured-pass reasoning",
        "Binary-judge reasoning",
        "Shared unfinished-unit modifier",
        "Shared prologue/epilogue modifier",
        "Write self-contained report and scorecard HTML",
        "Download configuration JSON",
        "Copyable command preview",
        "--local-sample-limit",
        "--html-report",
        "--wip",
    ):
        assert text in output
    assert "Per-unit local weights" not in output
    assert "individual chapter weight" not in output
    assert "api-key" not in output.casefold()
    assert "password" not in output.casefold()


def test_configurator_frozen_module_checkboxes_flow_into_config_and_command_preview():
    output = render_workflow_configurator(_catalog())
    assert "Confirm compatible modules" in output
    assert "Automatic routing remains a complete first-class route." in output
    assert "Search this bundle's modules" in output
    assert 'type="search"' in output
    assert "module-tree" in output
    assert "dataset.hbqrsModuleGroup" in output
    assert "document.createElement('details')" in output
    assert "document.createElement('summary')" in output
    assert "filterModules" in output
    assert "compatible module" in output
    assert "input.name = 'frozen-module'" in output
    assert "input.checked = true" in output
    assert "frozen_module_ids" in output
    assert "querySelectorAll('input[name=\"frozen-module\"]:checked')" in output
    assert "--module" in output
    assert "A frozen bundle needs at least one selected module." in output


def test_configurator_keeps_prerun_inputs_local_and_exposes_plan_only_command_preview():
    output = render_workflow_configurator(_catalog())
    for text in (
        "Pre-run context",
        "Local writing sample",
        "Optional originating prompt",
        "Optional natural-language judging brief",
        "Download originating prompt as UTF-8 text",
        "Download judging brief as UTF-8 text",
        "--driving-prompt-file",
        "--brief",
        "content_in_config: false",
        "Plan-only review first",
        "--plan-only",
        "plan_only",
        "downloadTextFile",
    ):
        assert text in output
    assert "route_sample_text" not in output
    assert "parts.push('--brief', quote('hbqrs-judging-brief.txt'))" in output
    assert "parts.push('--plan-only')" in output
    assert "originating_prompt_text" not in output
    assert "judging_brief_text" not in output
    assert "file.text()" in output  # Existing local-only manuscript preview remains browser-side.


def test_configurator_escapes_catalog_and_embedded_json():
    catalog = _catalog()
    catalog["bundles"][0]["title"] = "</script><img src=x onerror=alert(1)>"
    catalog["modules"][0]["title"] = "<b>unsafe</b>"
    output = render_workflow_configurator(catalog, title="<unsafe title>")
    assert "<unsafe title>" not in output
    assert "&lt;unsafe title&gt;" in output
    assert "</script><img src=x" not in output
    assert "\\u003c/script\\u003e\\u003cimg" in output
    assert "document.createElement('option')" in output
    assert "textContent = label" in output


def test_configurator_does_not_mutate_catalog_and_rejects_bad_shapes():
    catalog = _catalog()
    before = deepcopy(catalog)
    render_workflow_configurator(catalog)
    assert catalog == before
    with pytest.raises(ValueError, match="catalog"):
        render_workflow_configurator({"bundles": "wrong", "modules": []})
