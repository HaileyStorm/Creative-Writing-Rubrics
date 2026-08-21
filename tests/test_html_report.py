from copy import deepcopy

import pytest

from hbqrs import HBQError, book_root
from hbqrs.core import load_bundles
from hbqrs.html_report import CARD_LAYOUTS, render_html_report, render_html_scorecard


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


def _confidence_diagnostics():
    aggregate = {
        "question_count": 1,
        "applicable_count": 1,
        "assessed_count": 1,
        "applicable_effective_weight": 1.0,
        "assessed_effective_weight": 1.0,
        "assessed_raw_confidence_weighted_mean": 0.8,
        "assessed_raw_confidence_weighted_median": 0.8,
        "assessed_effective_weight_threshold_shares": {"gte_0_5": 1.0, "gte_0_75": 1.0, "gte_0_9": 0.0},
        "effective_confidence_mass": {"value": 0.8, "is_coverage": False},
    }
    return {
        "diagnostic_version": 1,
        "status": "DESCRIPTIVE_UNCALIBRATED",
        "disclosure": "Raw evaluator confidence is secondary to canonical scoring.",
        "roles": {role: deepcopy(aggregate) for role in ("domain", "hard_gate", "penalty", "supplemental")},
        "calibration": {
            "status": "UNAVAILABLE",
            "exact_fingerprint": None,
            "reason": "A single score has no polarity comparison, repeat judgments, or outcome history; no calibration inference is made.",
        },
    }


def _report(with_hierarchy: bool = True):
    global_result = _result("work", "Whole work", 81)
    global_result["confidence_diagnostics"] = _confidence_diagnostics()
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
                "trimmed_tail": None,
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
    assert "Custom-weighted composite · noncanonical" in first
    assert "Canonical whole-work score" in first
    assert "Secondary confidence diagnostics (uncalibrated)" in first
    assert "Threshold shares are assessed-effective-weight shares" in first
    assert "Whole-work domain breakdown" in first
    assert "Local trajectory" in first
    assert "Findings and evidence references" in first
    assert "for=\"hbqrs-global-weight\"" in first
    assert "aria-live=\"polite\"" in first
    assert "@media print" in first
    assert "Shared unfinished-unit modifier" in first
    assert "arbitrary per-chapter tuning" in first


def test_confidence_diagnostics_render_unassessed_ratios_as_not_observed():
    report = _report()
    aggregate = report["global_result"]["confidence_diagnostics"]["roles"]["penalty"]
    aggregate["assessed_count"] = 0
    aggregate["assessed_effective_weight"] = 0.0
    aggregate["assessed_raw_confidence_weighted_mean"] = None
    aggregate["assessed_raw_confidence_weighted_median"] = None
    aggregate["assessed_effective_weight_threshold_shares"] = {
        "gte_0_5": None,
        "gte_0_75": None,
        "gte_0_9": None,
    }
    aggregate["effective_confidence_mass"]["value"] = None

    card = render_html_scorecard(report)
    assert "lower weighted median Not observed" in card
    assert "assessed-effective-weight share at 75% Not observed" in card
    assert "mass Not observed" in card


def test_confidence_diagnostic_calibration_reason_remains_html_escaped():
    report = _report()
    report["global_result"]["confidence_diagnostics"]["calibration"]["reason"] = (
        '<img src="https://example.invalid/track.png">'
    )

    card = render_html_scorecard(report)

    assert "<img" not in card
    assert "&lt;img src=&quot;https://example.invalid/track.png&quot;&gt;" in card


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
    assert "Custom-weighted composite · noncanonical" in card
    assert "global 66.7%" in card
    assert "<code>weighted_mean</code>" in card
    assert "Active local-unit modifiers" in card
    assert "Chapter One" in card
    assert UNIT_ONE not in card
    assert "Support this project" in card
    assert "<details open>" in card
    assert "Whole-work domains (2)" in card
    assert "Local trajectory" in card
    assert "Format: Prose" in card
    assert "Bundle: prose.novel" in card
    assert 'id="hbqrs-scorecard-title"' not in card
    assert "hbqrs-scorecard__hero-value" in card


def test_scorecard_layouts_are_explicit_and_self_contained():
    report = _report()
    summary = render_html_scorecard(report, layout="summary")
    compact = render_html_scorecard(report, layout="compact")
    minimal = render_html_scorecard(report, layout="minimal")
    assert "Open full report" not in summary
    assert "Whole-work domains (2)" in summary
    assert "Whole-work domains (2)" not in compact
    assert "Control: VALID" in compact
    assert "Control: VALID" in minimal
    assert "Format: Prose" in minimal
    assert "Evaluated scope" not in minimal
    assert "Work in progress" in minimal
    assert "VALID" in minimal


@pytest.mark.parametrize("layout", CARD_LAYOUTS)
def test_scorecard_card_hierarchy_chips_and_accessible_visible_fallbacks(layout: str):
    card = render_html_scorecard(_report(), layout=layout)

    assert '<header class="hbqrs-scorecard__header">' in card
    assert 'class="hbqrs-scorecard__hero" aria-label="Canonical whole-work score"' in card
    assert card.index('class="hbqrs-scorecard__hero"') < card.index('class="hbqrs-scorecard__custom"')
    for text in (
        "Control: VALID",
        "Work in progress",
        "Coverage: 95.0%",
        "Format: Prose",
        "Scope: Two chapters of a work in progress.",
        "Bundle: prose.novel",
        "Source: sample",
        "Observed 81.0 · bounds 80.0–82.0",
        "Coverage 95.0%",
    ):
        assert text in card
    assert 'role="img" aria-label="Canonical whole-work score:' in card
    assert 'role="progressbar" aria-label="Whole-work coverage"' in card
    assert 'id="' not in card


def test_scorecard_card_styles_cover_mobile_print_dark_and_forced_colors():
    card = render_html_scorecard(_report())

    for token in (
        ".hbqrs-scorecard__hero-value",
        ".hbqrs-scorecard__interval-track",
        ".hbqrs-scorecard__coverage-fill",
        "@media (max-width:24.5rem)",
        "@media (prefers-color-scheme:dark)",
        "@media (forced-colors:active)",
        "@page{size:auto;margin:.4in}",
        "break-inside:avoid-page",
    ):
        assert token in card
    assert "@page{size:letter" not in card
    assert "@page{size:a4" not in card.casefold()
    assert "hbqrs-scorecard__table" not in card


def _relative_luminance(hex_color: str) -> float:
    values = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    return sum(component * coefficient for component, coefficient in zip(linear, (0.2126, 0.7152, 0.0722)))


def _contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_scorecard_focus_and_link_tokens_meet_contrast_targets():
    card = render_html_scorecard(_report())

    for token in ("--hbq-focus:#9a3412", "--hbq-accent-strong:#084d63", "--hbq-focus:#ffcf70"):
        assert token in card
    assert _contrast_ratio("#9a3412", "#ffffff") >= 4.5
    assert _contrast_ratio("#9a3412", "#f5f8fb") >= 4.5
    assert _contrast_ratio("#084d63", "#ffffff") >= 4.5
    assert _contrast_ratio("#084d63", "#f5f8fb") >= 4.5
    assert _contrast_ratio("#ffcf70", "#101923") >= 3.0
    assert _contrast_ratio("#b8ecfa", "#101923") >= 4.5


def test_scorecard_omits_custom_headline_without_profile():
    report = _report(with_hierarchy=False)
    card = render_html_scorecard(report)
    full = render_html_report(report)
    assert "Custom-weighted composite · noncanonical" not in card
    assert "Custom-weighted composite · noncanonical" not in full
    assert "Canonical whole-work score" in card
    assert "Canonical whole-work score" in full


def test_renderer_does_not_mutate_report():
    report = _report()
    before = deepcopy(report)
    render_html_report(report)
    render_html_scorecard(report)
    assert report == before


def test_scorecards_can_be_combined_without_duplicate_title_ids():
    cards = "\n".join(render_html_scorecard(_report(), layout=layout) for layout in CARD_LAYOUTS)
    assert "hbqrs-scorecard-title" not in cards
    assert cards.count('<h2 class="hbqrs-scorecard__title">Scorecard</h2>') == len(CARD_LAYOUTS)


def test_scorecard_uses_labels_for_modifier_and_weakest_unit_disclosures():
    report = _matrix_report(
        local_count=1,
        null_scores=False,
        control_state="VALID",
        completion_status="work_in_progress",
        hierarchy=True,
        modifiers=True,
    )
    card = render_html_scorecard(report)
    assert "Prologue — an intentionally long unicode label" in card
    assert UNIT_ONE not in card


def test_scorecard_discloses_tail_trim_with_labels_and_counts():
    report = _matrix_report(
        local_count=3,
        null_scores=False,
        control_state="VALID",
        completion_status="work_in_progress",
        hierarchy=True,
        modifiers=False,
    )
    hierarchy = report["hierarchical_score"]
    hierarchy["local_reducer"] = "trim_one_per_tail"
    hierarchy["score"] = _interval(80.5)
    hierarchy["local_component"]["score"] = _interval(80)
    hierarchy["local_component"]["trimmed_tail"] = {
        "eligible_unit_count": 3,
        "retained_unit_count": 1,
        "tie_rule": "lowest observed: earliest source-order tie; highest observed: latest source-order tie",
        "excluded_units": [
            {
                "unit_id": UNIT_ONE,
                "role": "lowest_tail",
                "weight_class": "ordinary",
                "source_index": 0,
                "reason": "lowest observed score; earliest source-order tie",
            },
            {
                "unit_id": UNIT_THREE,
                "role": "highest_tail",
                "weight_class": "ordinary",
                "source_index": 2,
                "reason": "highest observed score; latest source-order tie",
            },
        ],
    }
    assignments = hierarchy["local_component"]["unit_weight_assignments"]
    assignments[0]["effective_weight"] = 0.0
    assignments[1]["effective_weight"] = 1.0
    assignments[2]["effective_weight"] = 0.0

    card = render_html_scorecard(report)

    assert "Tail trim: 3 eligible, 1 retained" in card
    assert "Prologue — an intentionally long unicode label" in card
    assert "Epilogue — 终章" in card
    assert UNIT_ONE not in card and UNIT_THREE not in card


@pytest.mark.parametrize("reducer, weakest, trimmed_tail", [
    ("weighted_mean", UNIT_ONE, None),
    ("weakest_unit", None, None),
    ("trim_one_per_tail", None, None),
])
def test_scorecard_rejects_incoherent_reducer_metadata(reducer, weakest, trimmed_tail):
    report = _report()
    hierarchy = report["hierarchical_score"]
    hierarchy["local_reducer"] = reducer
    hierarchy["local_component"]["selected_weakest_unit_id"] = weakest
    hierarchy["local_component"]["trimmed_tail"] = trimmed_tail

    with pytest.raises(HBQError, match="strict schema"):
        render_html_scorecard(report)


def test_scorecard_zero_local_coverage_is_not_described_as_complete():
    card = render_html_scorecard(
        _matrix_report(
            local_count=0,
            null_scores=False,
            control_state="VALID",
            completion_status="complete",
            hierarchy=False,
        )
    )
    assert "No local units or scores were observed." in card
    assert "complete across 0" not in card


@pytest.mark.parametrize("layout", CARD_LAYOUTS)
def test_scorecard_handles_a_schema_valid_null_whole_work_result(layout: str):
    report = _report(with_hierarchy=False)
    report["global_result"] = None
    card = render_html_scorecard(report, layout=layout)
    assert "Canonical whole-work score" in card
    assert "Not observed" in card
    if layout == "minimal":
        assert "Not available" in card


@pytest.mark.parametrize("bundle_id", ("prose.novel", "poetry.collection", "drama.scene", "game.quest"))
def test_scorecard_identifies_bundle_and_format_for_each_supported_format(bundle_id: str):
    report = _matrix_report(
        local_count=1,
        null_scores=False,
        control_state="VALID",
        completion_status="complete",
        hierarchy=False,
        bundle_id=bundle_id,
    )
    format_name = bundle_id.split(".", 1)[0].title()
    for layout in CARD_LAYOUTS:
        card = render_html_scorecard(report, layout=layout)
        assert f"Format: {format_name}" in card
        assert f"Bundle: {bundle_id}" in card
        assert "Scope: Two chapters of a work in progress." in card


def test_report_print_styles_keep_header_with_following_content_and_dark_errors_legible():
    report = render_html_report(_report())
    assert '<div class="hbqrs-report-intro"><header class="hbqrs-report-header">' in report
    assert ".hbqrs-report-intro{break-inside:avoid-page;page-break-inside:avoid}" in report
    assert ".hbqrs-scorecard{border-color:#777;break-before:avoid-page;page-break-before:avoid}" in report
    assert '<section class="hbqrs-warnings" aria-labelledby="hbqrs-warnings-title">' in report
    assert ".hbqrs-warnings{break-inside:avoid-page;page-break-inside:avoid}" in report
    assert "section,.hbqrs-scorecard{border-color:#777;break-inside:avoid}" not in report
    assert "@media (prefers-color-scheme:dark){.hbqrs-error{color:#ffb4ab}}" in report


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
    if hierarchy and not null_scores:
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
                "trimmed_tail": None,
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
    if hierarchy and not null_scores:
        assert "Custom-weighted composite · noncanonical" in card
    else:
        assert "Custom-weighted composite · noncanonical" not in card
    if null_scores:
        assert "Not observed" in card
        assert "Not available" in card
    if layout == "summary":
        assert "<details open>" in card
        assert "Whole-work domains" in card
        assert "Local trajectory" in card
    elif layout == "compact":
        assert f"Control: {control_state}" in card
        assert "Whole-work domains" not in card
    else:
        assert f"Control: {control_state}" in card
        assert "Whole-work domains" not in card
    if layout != "minimal":
        assert control_state in card
        assert completion_status.replace("_", " ").title() in card or completion_status == "work_in_progress"
    if modifiers and not null_scores:
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
