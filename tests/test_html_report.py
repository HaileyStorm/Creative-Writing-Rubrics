from copy import deepcopy

import pytest

from hbqrs import book_root
from hbqrs.core import load_bundles
from hbqrs.html_report import render_html_report, render_html_scorecard


UNIT_ONE = "unit-0001-0123456789ab"
UNIT_TWO = "unit-0002-abcdef012345"
UNIT_THREE = "unit-0003-123456abcdef"


def _interval(observed: float, lower: float | None = None, upper: float | None = None):
    return {
        "observed": observed,
        "lower": observed - 1 if lower is None else lower,
        "upper": observed + 1 if upper is None else upper,
    }


def _result(scope_id: str, label: str, observed: float):
    return {
        "scope_id": scope_id,
        "label": label,
        "control_state": "VALID",
        "coverage": 0.95,
        "score": _interval(observed),
        "domains": [
            {
                "domain_id": "craft",
                "title": "Craft",
                "coverage": 0.9,
                "score": _interval(observed - 2),
            },
            {
                "domain_id": "continuity",
                "title": "Continuity",
                "coverage": 1.0,
                "score": _interval(observed + 1),
            },
        ],
    }


def _report(with_hierarchy: bool = True):
    global_result = _result("work", "Whole work", 81)
    local_results = [_result(UNIT_ONE, "Chapter One", 78), _result(UNIT_TWO, "Chapter Two", 84)]
    hierarchy = None
    if with_hierarchy:
        hierarchy = {
            "profile_version": 1,
            "profile_id": "wip-balanced",
            "method": "weighted_global_local",
            "local_reducer": "weighted_mean",
            "score": _interval(80),
            "global_component": {
                "score": _interval(81),
                "requested_weight": 2,
                "effective_weight": 2 / 3,
            },
            "local_component": {
                "score": _interval(79),
                "requested_weight": 1,
                "effective_weight": 1 / 3,
                "selected_weakest_unit_id": None,
                "unit_weight_assignments": [
                    {
                        "unit_id": UNIT_ONE,
                        "weight_class": "unfinished",
                        "class_modifier": 0.5,
                        "effective_weight": 1 / 3,
                    },
                    {
                        "unit_id": UNIT_TWO,
                        "weight_class": "ordinary",
                        "class_modifier": 1,
                        "effective_weight": 2 / 3,
                    },
                ],
            },
            "unit_weight_policy": {
                "ordinary_unit_weight": 1.0,
                "unfinished_unit_weight": 0.5,
                "unfinished_unit_ids": [UNIT_ONE],
                "prologue_epilogue_weight": 1.0,
                "prologue_epilogue_unit_ids": [],
                "overlap_precedence": "unfinished_before_prologue_epilogue",
            },
            "policy": "Existing intervals only; never replaces canonical results.",
        }
    return {
        "report_version": 1,
        "artifact": {"artifact_id": "sample", "source_sha256": "0" * 64, "unit_count": 2},
        "route": {
            "global_bundle_id": "prose.novel",
            "local_bundle_id": "prose.novel",
            "local_bundle_mode": "scope_auto",
            "module_ids": ["prose.scene_clarity"],
            "weighted_goal_count": 1,
            "binding_requirement_count": 0,
            "local_coverage_mode": "complete",
            "local_unit_ids": [UNIT_ONE, UNIT_TWO],
            "non_substantive_unit_ids": [],
        },
        "completion_contract": {
            "contract_version": 1,
            "completion_status": "work_in_progress",
            "incomplete": True,
            "completion_only_criterion_verdict": "NOT_APPLICABLE",
            "unavailable_supplied_evidence_verdict": "CANNOT_ASSESS",
            "assess_supplied_scope_craft": True,
            "assess_supplied_scope_continuity": True,
            "applicable_binding_requirements": "evaluate",
            "applicable_weighted_goals": "score",
        },
        "orientation": {
            "premise": "A concise, source-free reader orientation.",
            "evaluated_scope": "Two chapters of a work in progress.",
            "cast": [{"name": "Mara", "role": "Viewpoint character."}],
        },
        "global_result": global_result,
        "local_results": local_results,
        "hierarchical_score": hierarchy,
        "findings": [
            {
                "kind": "strength",
                "finding": "The throughline is clear.",
                "why_it_matters": "It supports reader orientation.",
                "evidence_refs": ["whole-work:craft"],
                "criterion_ids": ["prose.scene_clarity.001"],
            }
        ],
        "warnings": ["A limitation is recorded without manuscript quotation."],
    }


def test_full_renderer_is_deterministic_self_contained_and_semantic():
    report = _report()
    first = render_html_report(report)
    assert first == render_html_report(report)
    assert "<script src=" not in first
    assert "<link rel=" not in first
    assert "https://github.com/HaileyStorm/Creative-Writing-Rubrics" in first
    assert "fetch(" not in first
    assert "localStorage" not in first
    assert "sessionStorage" not in first
    assert "innerHTML" not in first
    assert "Custom-weighted composite" in first
    assert "Canonical whole-work score" in first
    assert "Whole-work domain breakdown" in first
    assert "Local trajectory" in first
    assert "Findings and evidence references" in first
    assert "for=\"hbqrs-global-weight\"" in first
    assert "aria-live=\"polite\"" in first
    assert "@media print" in first
    assert "Shared unfinished-unit modifier" in first
    assert "arbitrary per-chapter tuning" in first


def test_renderer_escapes_embedded_json_and_visible_text():
    report = _report()
    report["orientation"]["premise"] = "</script><img src=x onerror=alert(1)>"
    report["findings"][0]["finding"] = "<b>unsafe</b>"
    output = render_html_report(report, title="<unsafe title>")
    assert "<unsafe title>" not in output
    assert "&lt;unsafe title&gt;" in output
    assert "</script><img src=x" not in output
    assert "\\u003c/script\\u003e\\u003cimg" in output
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in output


def test_scorecard_is_static_scoped_and_shows_active_modifiers():
    card = render_html_scorecard(_report())
    assert "<script" not in card
    assert '<meta charset="utf-8">' in card
    assert ".hbqrs-scorecard" in card
    assert "Custom-weighted composite" in card
    assert "global effective weight 66.7%" in card
    assert "local reducer <code>weighted_mean</code>" in card
    assert "Active local-unit modifiers" in card
    assert UNIT_ONE in card
    assert "Support this project" in card
    assert "<details open>" in card
    assert "Whole-work domains (2)" in card
    assert "Local trajectory" in card


def test_scorecard_layouts_are_explicit_and_self_contained():
    report = _report()
    summary = render_html_scorecard(report, layout="summary")
    compact = render_html_scorecard(report, layout="compact")
    minimal = render_html_scorecard(report, layout="minimal")
    assert "Open full report" not in summary
    assert "Whole-work domains (2)" in summary
    assert "Whole-work domains (2)" not in compact
    assert "Whole-work control state" in compact
    assert "Whole-work control state" not in minimal


def test_scorecard_omits_custom_headline_without_profile():
    report = _report(with_hierarchy=False)
    card = render_html_scorecard(report)
    full = render_html_report(report)
    assert "Custom-weighted composite" not in card
    assert "Custom-weighted composite" not in full
    assert "Canonical whole-work score" in card
    assert "Canonical whole-work score" in full


def test_renderer_does_not_mutate_report():
    report = _report()
    before = deepcopy(report)
    render_html_report(report)
    render_html_scorecard(report)
    assert report == before


def _completion_contract(status: str) -> dict[str, object]:
    completion_only = {
        "complete": "EVALUATE",
        "work_in_progress": "NOT_APPLICABLE",
        "excerpt": "NOT_APPLICABLE",
        "unknown": "CANNOT_ASSESS",
    }[status]
    return {
        "contract_version": 1,
        "completion_status": status,
        "incomplete": status in {"work_in_progress", "excerpt"},
        "completion_only_criterion_verdict": completion_only,
        "unavailable_supplied_evidence_verdict": "CANNOT_ASSESS",
        "assess_supplied_scope_craft": True,
        "assess_supplied_scope_continuity": True,
        "applicable_binding_requirements": "evaluate",
        "applicable_weighted_goals": "score",
    }


def _matrix_report(
    *,
    local_count: int,
    null_scores: bool,
    control_state: str,
    completion_status: str,
    hierarchy: bool,
    modifiers: bool = False,
    bundle_id: str = "prose.novel",
) -> dict[str, object]:
    report = _report(with_hierarchy=False)
    unit_ids = [UNIT_ONE, UNIT_TWO, UNIT_THREE]
    labels = [
        "Prologue — an intentionally long unicode label: naïve café 🧭",
        "Chapter Two: a deliberately verbose local diagnostic label for wrapping",
        "Epilogue — 终章",
    ]
    locals_ = [_result(unit_id, label, 72 + index * 8) for index, (unit_id, label) in enumerate(zip(unit_ids[:local_count], labels))]
    report["route"]["global_bundle_id"] = bundle_id
    report["route"]["local_bundle_id"] = bundle_id
    report["route"]["local_unit_ids"] = [UNIT_ONE] if local_count == 0 else unit_ids[:local_count]
    report["local_results"] = locals_
    report["completion_contract"] = _completion_contract(completion_status)
    global_result = report["global_result"]
    global_result["control_state"] = control_state
    for result in locals_:
        result["control_state"] = control_state
    if null_scores:
        for result in [global_result, *locals_]:
            result["score"] = None
            for domain in result["domains"]:
                domain["score"] = None
    if hierarchy:
        assignments = []
        for index, result in enumerate(locals_):
            assignments.append(
                {
                    "unit_id": result["scope_id"],
                    "weight_class": "unfinished" if modifiers and index == 0 else "ordinary",
                    "class_modifier": 0.5 if modifiers and index == 0 else 1.0,
                    "effective_weight": 1 / len(locals_) if locals_ else 0.0,
                }
            )
        report["hierarchical_score"] = {
            "profile_version": 1,
            "profile_id": "matrix-profile",
            "method": "weighted_global_local",
            "local_reducer": "weakest_unit" if modifiers else "weighted_mean",
            "score": _interval(79),
            "global_component": {
                "score": None if null_scores else _interval(81),
                "requested_weight": 1.0,
                "effective_weight": 1.0 if not locals_ else 0.5,
            },
            "local_component": {
                "score": None if (null_scores or not locals_) else _interval(77),
                "requested_weight": 0.0 if not locals_ else 1.0,
                "effective_weight": 0.0 if not locals_ else 0.5,
                "selected_weakest_unit_id": locals_[0]["scope_id"] if modifiers and locals_ else None,
                "unit_weight_assignments": assignments,
            },
            "unit_weight_policy": {
                "ordinary_unit_weight": 1.0,
                "unfinished_unit_weight": 0.5 if modifiers else 1.0,
                "unfinished_unit_ids": [locals_[0]["scope_id"]] if modifiers and locals_ else [],
                "prologue_epilogue_weight": 1.0,
                "prologue_epilogue_unit_ids": [],
                "overlap_precedence": "unfinished_before_prologue_epilogue",
            },
            "policy": "Synthetic matrix profile over existing results only.",
        }
    return report


MATRIX_CASES = [
    pytest.param("summary", 0, False, "VALID", "complete", False, False, id="summary-canonical-zero-locals"),
    pytest.param("summary", 3, False, "VALID", "complete", False, False, id="summary-many-unicode-locals"),
    pytest.param("compact", 1, False, "UNRESOLVED", "work_in_progress", True, True, id="compact-custom-wip-modifier"),
    pytest.param("minimal", 3, False, "PROVISIONAL", "excerpt", True, False, id="minimal-custom-many-locals"),
    pytest.param("summary", 1, True, "INELIGIBLE", "unknown", False, False, id="summary-null-score-unknown"),
    pytest.param("compact", 3, True, "INVALID", "complete", True, True, id="compact-null-score-invalid"),
    pytest.param("minimal", 1, False, "VALID", "work_in_progress", False, False, id="minimal-canonical-wip"),
]


@pytest.mark.parametrize(
    ("layout", "local_count", "null_scores", "control_state", "completion_status", "hierarchy", "modifiers"),
    MATRIX_CASES,
)
def test_scorecard_feature_matrix(
    layout: str,
    local_count: int,
    null_scores: bool,
    control_state: str,
    completion_status: str,
    hierarchy: bool,
    modifiers: bool,
):
    card = render_html_scorecard(
        _matrix_report(
            local_count=local_count,
            null_scores=null_scores,
            control_state=control_state,
            completion_status=completion_status,
            hierarchy=hierarchy,
            modifiers=modifiers,
        ),
        layout=layout,
    )
    assert "Canonical whole-work score" in card
    assert "Creative-Writing-Rubrics" in card
    assert "Support this project" in card
    assert "<script" not in card
    assert "<link rel=" not in card
    assert "src=" not in card
    assert "fetch(" not in card
    assert "Open full report" not in card
    if hierarchy:
        assert "Custom-weighted composite" in card
    else:
        assert "Custom-weighted composite" not in card
    if null_scores:
        assert "Not observed" in card
        assert "Not available" in card
    if layout == "summary":
        assert "<details open>" in card
        assert "Whole-work domains" in card
        assert "Local trajectory" in card
    elif layout == "compact":
        assert "Whole-work control state" in card
        assert "Whole-work domains" not in card
    else:
        assert "Whole-work control state" not in card
        assert "Whole-work domains" not in card
    if layout != "minimal":
        assert control_state in card
        assert completion_status.replace("_", " ").title() in card or completion_status == "work_in_progress"
    if modifiers:
        assert "Active local-unit modifiers" in card
    if local_count == 3 and layout == "summary":
        assert "naïve café 🧭" in card


def test_compact_scorecard_smoke_matrix_for_every_catalog_bundle():
    bundles = load_bundles(book_root() / "bundles" / "all_bundles.json")
    assert len(bundles) == 85
    for bundle in bundles:
        card = render_html_scorecard(
            _matrix_report(
                local_count=1,
                null_scores=False,
                control_state="VALID",
                completion_status="work_in_progress",
                hierarchy=False,
                bundle_id=bundle["bundle_id"],
            ),
            layout="compact",
        )
        assert "Canonical whole-work score" in card
        assert "<script" not in card
