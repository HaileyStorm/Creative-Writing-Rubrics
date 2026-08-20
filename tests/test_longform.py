from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hbqrs import HBQError
from hbqrs.longform import (
    build_route_sample,
    compute_hierarchical_score,
    complete_local_evaluation_plan,
    make_completion_contract,
    render_chapter_comparison_svg,
    resolve_local_bundle_plan,
    run_longform_workflow,
    segment_longform,
    validate_long_form_map,
    validate_route_selection,
    validate_task_contract,
)


TEXT = (
    "Prologue\r\n"
    "Rain silvered the empty platform.\r\n"
    "\r\n"
    "Chapter One\r\n"
    "Mara found the sealed letter and left it unopened.\r\n"
    "\r\n"
    "CHAPTER TWO: The Return\r\n"
    "At dawn, she opened it beside the river.\r\n"
)


def _catalog():
    modules = [
        {
            "module_id": "craft.synthetic",
            "title": "Synthetic craft",
            "description": "Test module.",
            "artifact_types": ["prose_fiction"],
            "valid_scopes": ["work"],
        }
    ]
    bundles = [
        {
            "bundle_id": "prose.synthetic",
            "title": "Synthetic prose",
            "description": "Test bundle.",
            "artifact_types": ["prose_fiction"],
            "valid_scopes": ["work"],
            "module_ids": ["craft.synthetic"],
        }
    ]
    return modules, bundles


def _contract(*, binding: bool = True):
    requirements = []
    if binding:
        requirements.append(
            {
                "requirement_id": "requirement.two_chapters",
                "atomic_question": "Does the work contain exactly two chapters?",
                "objective": True,
                "non_negotiable": True,
                "source": {
                    "kind": "explicit_user_requirement",
                    "reference": "driving-prompt:2",
                    "exact_excerpt": "Include exactly two chapters.",
                },
                "applies_to": ["work"],
                "verification": {"method": "numeric_limit", "expected": "exactly 2"},
            }
        )
    return {
        "contract_version": 1,
        "contract_id": "contract.synthetic",
        "artifact_id": "synthetic-story",
        "context": {
            "artifact_kind": "prose_fiction",
            "declared_scope": "work",
            "completion_status": "work_in_progress",
            "background": ["A synthetic mystery."],
            "constraints": [],
            "audience": ["adult"],
        },
        "preferences": [
            {
                "id": "preference.tension",
                "statement": "Prefer quiet tension.",
                "source": {
                    "kind": "user_preference",
                    "reference": "project-context:1",
                    "exact_excerpt": "Prefer quiet tension.",
                },
            }
        ],
        "priorities": [],
        "weighted_goals": [
            {
                "goal_id": "goal.clarity",
                "atomic_question": "Is the prose clear?",
                "weight": 2.0,
                "source": {
                    "kind": "driving_prompt",
                    "reference": "driving-prompt:1",
                    "exact_excerpt": "Keep the prose clear.",
                },
                "applies_to": ["work"],
                "rationale": "Clarity is an author priority, not an eligibility condition.",
            }
        ],
        "binding_requirements": requirements,
    }


def _route(segmentation, *, contract=None):
    unit_ids = [unit["unit_id"] for unit in segmentation["units"]]
    return {
        "route_version": 1,
        "artifact_profile": {
            "artifact_kind": "prose_fiction",
            "declared_scope": "work",
            "completion_status": "work_in_progress",
            "unit_count": segmentation["unit_count"],
            "source_sha256": segmentation["source_sha256"],
        },
        "selected_bundle_id": "prose.synthetic",
        "selected_module_ids": ["craft.synthetic"],
        "selection_reasons": [
            {"catalog_id": "prose.synthetic", "reason": "Matches long-form prose."},
            {"catalog_id": "craft.synthetic", "reason": "Covers the requested craft pass."},
        ],
        "sampling_plan": {
            "coverage_mode": "complete",
            "unit_ids": unit_ids,
            "strata": [{"name": "complete synthetic set", "unit_ids": unit_ids}],
            "global_map_required": True,
            "rationale": "The tiny synthetic work can be assessed in full.",
        },
        "task_contract": contract or _contract(binding=False),
    }


def _map(segmentation):
    units = []
    for unit in segmentation["units"]:
        units.append(
            {
                "unit_id": unit["unit_id"],
                "summary": f"Synthetic summary for {unit['heading'] or 'section'}.",
                "chronology": f"Position {unit['ordinal']}",
                "povs": ["Mara"],
                "characters": ["Mara"],
                "locations": ["platform" if unit["ordinal"] == 1 else "river"],
                "promises_opened": ["The sealed letter"] if unit["ordinal"] == 2 else [],
                "promises_advanced": [],
                "promises_resolved": ["The letter is opened"] if unit["ordinal"] == 3 else [],
                "motifs": ["water"],
                "ending_state": "The next unit remains possible.",
                "load_bearing": unit["ordinal"] in {2, 3},
            }
        )
    return {
        "map_version": 1,
        "artifact_id": segmentation["artifact_id"],
        "source_sha256": segmentation["source_sha256"],
        "orientation": {
            "premise": "Mara delays opening a letter that may change her course.",
            "evaluated_scope": "A prologue and two short synthetic chapters.",
            "cast": [{"name": "Mara", "role": "The viewpoint character and letter recipient."}],
        },
        "units": units,
        "work_state": {
            "chronology": ["Night at the platform", "Dawn at the river"],
            "central_arcs": ["Mara moves from avoidance to action."],
            "subplots": [],
            "promises": ["The letter's contents remain a forward promise."],
            "motifs": ["Water marks transitions."],
            "ending_state": "Mara has opened the letter; its contents remain unrevealed.",
        },
        "state_ledgers": [
            {
                "entity_type": "object",
                "entity": "sealed letter",
                "current_state": "open",
                "changes": [
                    {"unit_id": segmentation["units"][1]["unit_id"], "state": "sealed"},
                    {"unit_id": segmentation["units"][2]["unit_id"], "state": "open"},
                ],
            }
        ],
        "distant_links": [
            {
                "setup_unit_id": segmentation["units"][1]["unit_id"],
                "payoff_unit_id": segmentation["units"][2]["unit_id"],
                "description": "The sealed letter is opened.",
                "status": "paid_off",
            }
        ],
        "limitations": ["The synthetic work ends before the letter's contents are shown."],
    }


def _result(observed: float):
    return {
        "control_state": "VALID",
        "coverage": 1.0,
        "score": {"observed": observed, "lower": observed, "upper": observed},
        "domains": [
            {
                "domain_id": "craft",
                "title": "Craft",
                "coverage": 1.0,
                "score": {"observed": observed, "lower": observed, "upper": observed},
            }
        ],
    }


def test_segmentation_preserves_source_spans_hashes_and_stable_ids():
    first = segment_longform(TEXT, artifact_id="synthetic-story")
    second = segment_longform(TEXT, artifact_id="synthetic-story")

    assert first == second
    assert first["unit_count"] == 3
    assert [unit["heading"] for unit in first["units"]] == ["Prologue", "Chapter One", "CHAPTER TWO: The Return"]
    assert "".join(unit["text"] for unit in first["units"]) == TEXT
    assert first["units"][1]["span"]["start"] == TEXT.index("Chapter One")
    assert all(unit["unit_id"].endswith(unit["sha256"][:12]) for unit in first["units"])


def test_complete_local_plan_excludes_only_brief_nonprose_front_matter():
    title_text = "Synthetic Title\n\nChapter One\nA scene begins.\n\nChapter Two\nThe scene continues.\n"
    segmentation = segment_longform(title_text, artifact_id="synthetic-story")
    assert segmentation["units"][0]["kind"] == "front_matter"
    assert segmentation["units"][0]["local_evaluation"] == {
        "eligible": False,
        "reason": "brief_nonprose_front_matter",
    }
    assert all(unit["local_evaluation"]["eligible"] for unit in segmentation["units"][1:])
    plan = complete_local_evaluation_plan(_route(segmentation), segmentation)
    assert plan["sampling_plan"]["coverage_mode"] == "complete"
    assert plan["sampling_plan"]["unit_ids"] == [
        unit["unit_id"] for unit in segmentation["units"][1:]
    ]

    prose_front = segment_longform(
        "An untitled opening sentence.\n\nChapter One\nThe chapter continues.\n",
        artifact_id="synthetic-story",
    )
    assert prose_front["units"][0]["kind"] == "front_matter"
    assert prose_front["units"][0]["local_evaluation"]["eligible"] is True


def test_local_bundle_auto_selects_exact_chapter_scope_and_explicit_global_is_deep_mode():
    modules, bundles = _catalog()
    bundles.append(
        {
            "bundle_id": "prose.chapter",
            "title": "Synthetic chapter",
            "description": "Chapter-scoped diagnostics.",
            "artifact_types": ["prose_fiction"],
            "valid_scopes": ["chapter"],
            "module_ids": ["craft.synthetic"],
        }
    )
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    automatic = resolve_local_bundle_plan(
        bundles=bundles,
        global_bundle_id="prose.synthetic",
        artifact_kind="prose_fiction",
        segmentation=segmentation,
    )
    assert automatic == {
        "global_bundle_id": "prose.synthetic",
        "local_bundle_id": "prose.chapter",
        "local_bundle_mode": "scope_auto",
    }
    explicit = resolve_local_bundle_plan(
        bundles=bundles,
        global_bundle_id="prose.synthetic",
        artifact_kind="prose_fiction",
        segmentation=segmentation,
        explicit_local_bundle_id="prose.synthetic",
    )
    assert explicit["local_bundle_mode"] == "explicit_global_deep"


def test_local_bundle_auto_falls_back_safely_and_rejects_ambiguity():
    _modules, bundles = _catalog()
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    fallback = resolve_local_bundle_plan(
        bundles=bundles,
        global_bundle_id="prose.synthetic",
        artifact_kind="prose_fiction",
        segmentation=segmentation,
    )
    assert fallback["local_bundle_id"] == "prose.synthetic"
    assert fallback["local_bundle_mode"] == "global_fallback_no_scope_bundle"

    for suffix in ("a", "b"):
        bundles.append(
            {
                "bundle_id": f"prose.chapter_{suffix}",
                "title": suffix,
                "description": suffix,
                "artifact_types": ["prose_fiction"],
                "valid_scopes": ["chapter"],
                "module_ids": ["craft.synthetic"],
            }
        )
    with pytest.raises(HBQError, match="ambiguous"):
        resolve_local_bundle_plan(
            bundles=bundles,
            global_bundle_id="prose.synthetic",
            artifact_kind="prose_fiction",
            segmentation=segmentation,
        )


def test_route_sample_is_bounded_separated_and_span_auditable():
    sample = build_route_sample("0123456789" * 20, limit=30)
    assert sample["excerpt_char_count"] == 30
    assert [item["label"] for item in sample["excerpts"]] == ["start", "middle", "end"]
    assert sample["text"].count("<<<HBQ-RS ROUTE EXCERPT ") == 3
    assert sample["text"].count("<<<END HBQ-RS ROUTE EXCERPT>>>") == 3
    assert sample["excerpts"][0]["span"] == {"start": 0, "end": 10}
    assert sample["excerpts"][-1]["span"] == {"start": 190, "end": 200}


def test_completion_contract_distinguishes_wip_from_missing_supplied_evidence():
    wip = make_completion_contract("work_in_progress")
    assert wip["incomplete"] is True
    assert wip["completion_only_criterion_verdict"] == "NOT_APPLICABLE"
    assert wip["unavailable_supplied_evidence_verdict"] == "CANNOT_ASSESS"
    assert wip["applicable_binding_requirements"] == "evaluate"
    assert wip["applicable_weighted_goals"] == "score"
    assert make_completion_contract("complete")["completion_only_criterion_verdict"] == "EVALUATE"


def test_subjective_goals_are_weighted_and_cannot_be_binding_gates():
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    contract = _contract(binding=False)
    validated = validate_task_contract(
        contract,
        artifact_id="synthetic-story",
        unit_ids=[unit["unit_id"] for unit in segmentation["units"]],
    )
    assert validated["weighted_goals"][0]["weight"] == 2.0
    assert validated["binding_requirements"] == []

    subjective_gate = deepcopy(contract["weighted_goals"][0])
    subjective_gate = {
        "requirement_id": "requirement.tone",
        "atomic_question": "Is the tone dark?",
        "objective": True,
        "non_negotiable": True,
        "source": {
            "kind": "explicit_user_requirement",
            "reference": "driving-prompt:3",
            "exact_excerpt": "Make the tone dark.",
        },
        "applies_to": ["work"],
        "verification": {"method": "structural_constraint", "expected": "dark"},
    }
    contract["binding_requirements"] = [subjective_gate]
    with pytest.raises(HBQError, match="weighted_goal instead of a gate"):
        validate_task_contract(
            contract,
            artifact_id="synthetic-story",
            unit_ids=[unit["unit_id"] for unit in segmentation["units"]],
        )


def test_task_criteria_cannot_be_inferred_from_candidate_prose():
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    contract = _contract(binding=False)
    contract["weighted_goals"][0]["source"] = {
        "kind": "sample_text_inference",
        "reference": "candidate:sample",
        "exact_excerpt": "Rain silvered the empty platform.",
    }
    with pytest.raises(HBQError, match="strict schema"):
        validate_task_contract(
            contract,
            artifact_id="synthetic-story",
            unit_ids=[unit["unit_id"] for unit in segmentation["units"]],
        )


def test_route_is_constrained_to_catalog_and_sampling_inventory():
    modules, bundles = _catalog()
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    route = _route(segmentation)
    assert validate_route_selection(
        route, segmentation=segmentation, modules=modules, bundles=bundles
    )["selected_bundle_id"] == "prose.synthetic"
    with pytest.raises(HBQError, match="exceeding the declared limit"):
        validate_route_selection(
            route,
            segmentation=segmentation,
            modules=modules,
            bundles=bundles,
            local_sample_limit=2,
        )

    reduced = deepcopy(route)
    reduced["sampling_plan"]["coverage_mode"] = "sampled"
    reduced["sampling_plan"]["unit_ids"] = reduced["sampling_plan"]["unit_ids"][:1]
    reduced["sampling_plan"]["strata"] = [
        {"name": "reduced", "unit_ids": reduced["sampling_plan"]["unit_ids"]}
    ]
    with pytest.raises(HBQError, match="must cover every substantive unit in order"):
        validate_route_selection(
            reduced,
            segmentation=segmentation,
            modules=modules,
            bundles=bundles,
        )

    wrong_status = deepcopy(route)
    wrong_status["artifact_profile"]["completion_status"] = "complete"
    wrong_status["task_contract"]["context"]["completion_status"] = "complete"
    with pytest.raises(HBQError, match="does not match the declared artifact status"):
        validate_route_selection(
            wrong_status,
            segmentation=segmentation,
            modules=modules,
            bundles=bundles,
            expected_completion_status="work_in_progress",
        )

    route["selected_module_ids"] = ["craft.not_in_catalog"]
    with pytest.raises(HBQError, match="unknown modules"):
        validate_route_selection(route, segmentation=segmentation, modules=modules, bundles=bundles)


def test_automatic_route_cannot_promote_preference_text_to_a_binding_gate():
    modules, bundles = _catalog()
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    contract = _contract(binding=True)
    requirement = contract["binding_requirements"][0]
    requirement["source"]["exact_excerpt"] = "Prefer exactly two chapters."
    route = _route(segmentation, contract=contract)
    with pytest.raises(HBQError, match="Automatic route selection cannot create binding requirements"):
        validate_route_selection(
            route,
            segmentation=segmentation,
            modules=modules,
            bundles=bundles,
        )
    approved = validate_route_selection(
        route,
        segmentation=segmentation,
        modules=modules,
        bundles=bundles,
        binding_contract_approved=True,
    )
    assert approved["task_contract"]["binding_requirements"][0]["requirement_id"] == "requirement.two_chapters"


def test_long_form_map_requires_exact_ordered_units_and_known_references():
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    work_map = _map(segmentation)
    assert validate_long_form_map(work_map, segmentation=segmentation)["orientation"]["cast"][0]["name"] == "Mara"

    work_map["units"] = list(reversed(work_map["units"]))
    with pytest.raises(HBQError, match="exactly once and in order"):
        validate_long_form_map(work_map, segmentation=segmentation)


def test_complete_workflow_renders_explanatory_report_and_independent_scores():
    modules, bundles = _catalog()
    requests = []

    def select_route(request):
        requests.append(request)
        segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
        route = _route(segmentation)
        first_unit = route["sampling_plan"]["unit_ids"][0]
        route["sampling_plan"] = {
            "coverage_mode": "sampled",
            "unit_ids": [first_unit],
            "strata": [{"name": "model-proposed subset", "unit_ids": [first_unit]}],
            "global_map_required": True,
            "rationale": "The model proposed a subset, but default workflow coverage must override it.",
        }
        return route

    def build_map(request):
        return _map(
            {
                "artifact_id": request["artifact_id"],
                "source_sha256": request["source_sha256"],
                "units": request["units"],
            }
        )

    scores = iter([88.0, 81.0, 84.0, 92.0])

    def evaluate(request):
        if request["scope_kind"] == "local":
            assert request["source_text"]
        else:
            assert "source_text" not in request
            assert "".join(unit["text"] for unit in request["units"]) == TEXT
        return _result(next(scores))

    def synthesize(request):
        assert "source_text" not in request
        return {
            "findings": [
                {
                    "kind": "strength",
                    "finding": "The deferred letter creates a clear local promise.",
                    "why_it_matters": "The later opening demonstrates a traceable setup and payoff.",
                    "evidence_refs": [request["local_results"][1]["scope_id"], request["local_results"][2]["scope_id"]],
                    "criterion_ids": ["craft.synthetic.promise"],
                }
            ],
            "warnings": [],
        }

    output = run_longform_workflow(
        text=TEXT,
        artifact_id="synthetic-story",
        modules=modules,
        bundles=bundles,
        artifact_kind="prose_fiction",
        declared_scope="work",
        completion_status="work_in_progress",
        route_selector=select_route,
        map_builder=build_map,
        evaluator=evaluate,
        synthesizer=synthesize,
        driving_prompt="Keep the prose clear. Include exactly two chapters.",
        project_context="Prefer quiet tension.",
    )

    assert len(output["report"]["local_results"]) == 3
    assert output["report"]["hierarchical_score"] is None
    assert output["report"]["route"]["global_bundle_id"] == "prose.synthetic"
    assert output["report"]["route"]["local_bundle_id"] == "prose.synthetic"
    assert output["report"]["route"]["local_bundle_mode"] == "global_fallback_no_scope_bundle"
    assert output["report"]["route"]["local_coverage_mode"] == "complete"
    assert len(output["report"]["route"]["local_unit_ids"]) == 3
    assert [item["score"]["observed"] for item in output["report"]["local_results"]] == [81.0, 84.0, 92.0]
    assert "Control state" in output["markdown"]
    assert "Coverage" in output["markdown"]
    assert "Observed score" in output["markdown"]
    assert "Uncertainty bounds" in output["markdown"]
    assert "not a confidence interval" in output["markdown"]
    assert output["report"]["completion_contract"] == make_completion_contract("work_in_progress")
    assert "Work-in-progress rule" in output["markdown"]
    assert "Mara" in output["markdown"] and "viewpoint character" in output["markdown"]
    assert "81.0" in output["svg"] and "92.0" in output["svg"]
    assert "average" not in json.dumps(output["report"]).casefold()
    assert TEXT in requests[0]["sample_text"]
    assert "<<<HBQ-RS ROUTE EXCERPT " in requests[0]["sample_text"]


def test_hierarchical_weighted_mean_normalizes_custom_weights_and_bounds():
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    unit_ids = [unit["unit_id"] for unit in segmentation["units"][:2]]
    global_result = {
        "scope_id": "work",
        "label": "Whole work",
        **_result(80.0),
        "score": {"observed": 80.0, "lower": 70.0, "upper": 90.0},
    }
    local_results = [
        {
            "scope_id": unit_ids[0],
            "label": "One",
            **_result(60.0),
            "score": {"observed": 60.0, "lower": 50.0, "upper": 80.0},
        },
        {
            "scope_id": unit_ids[1],
            "label": "Two",
            **_result(100.0),
            "score": {"observed": 100.0, "lower": 90.0, "upper": 100.0},
        },
    ]
    hierarchy = compute_hierarchical_score(
        {
            "profile_version": 1,
            "profile_id": "balanced.custom",
            "global_weight": 1,
            "local_weight": 1,
            "local_reducer": "weighted_mean",
            "unfinished_unit_ids": [unit_ids[1]],
            "unfinished_unit_weight": 3,
            "prologue_epilogue_weight": 1,
        },
        global_result=global_result,
        local_results=local_results,
        unit_headings={unit_ids[0]: "Prologue", unit_ids[1]: "Chapter One"},
    )
    assert hierarchy is not None
    assert hierarchy["local_component"]["score"] == {
        "observed": 90.0,
        "lower": 80.0,
        "upper": 95.0,
    }
    assert hierarchy["score"] == {"observed": 85.0, "lower": 75.0, "upper": 92.5}
    assert hierarchy["global_component"]["effective_weight"] == 0.5
    assert [item["effective_weight"] for item in hierarchy["local_component"]["unit_weight_assignments"]] == [
        0.25,
        0.75,
    ]
    assert [item["weight_class"] for item in hierarchy["local_component"]["unit_weight_assignments"]] == [
        "prologue_epilogue",
        "unfinished",
    ]


def test_hierarchical_weakest_unit_preserves_its_interval():
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    unit_ids = [unit["unit_id"] for unit in segmentation["units"][:2]]
    local_results = [
        {
            "scope_id": unit_ids[0],
            "label": "One",
            **_result(62.0),
            "score": {"observed": 62.0, "lower": 50.0, "upper": 70.0},
        },
        {"scope_id": unit_ids[1], "label": "Two", **_result(91.0)},
    ]
    hierarchy = compute_hierarchical_score(
        {
            "profile_version": 1,
            "profile_id": "weakest.chapter",
            "global_weight": 0,
            "local_weight": 2,
            "local_reducer": "weakest_unit",
        },
        global_result=None,
        local_results=local_results,
    )
    assert hierarchy is not None
    assert hierarchy["score"] == {"observed": 62.0, "lower": 50.0, "upper": 70.0}
    assert hierarchy["local_component"]["selected_weakest_unit_id"] == unit_ids[0]
    assert hierarchy["global_component"]["score"] is None


@pytest.mark.parametrize(
    "profile,match",
    [
        (
            {
                "profile_version": 1,
                "profile_id": "bad.negative",
                "global_weight": -1,
                "local_weight": 1,
                "local_reducer": "weighted_mean",
            },
            "strict schema",
        ),
        (
            {
                "profile_version": 1,
                "profile_id": "bad.zero",
                "global_weight": 0,
                "local_weight": 0,
                "local_reducer": "weighted_mean",
            },
            "positive finite sum",
        ),
        (
            {
                "profile_version": 1,
                "profile_id": "bad.nan",
                "global_weight": float("nan"),
                "local_weight": 1,
                "local_reducer": "weighted_mean",
            },
            "finite nonnegative",
        ),
        (
            {
                "profile_version": 1,
                "profile_id": "bad.unit",
                "global_weight": 1,
                "local_weight": 1,
                "local_reducer": "weighted_mean",
                "unfinished_unit_ids": ["unit-9999-aaaaaaaaaaaa"],
                "unfinished_unit_weight": 0.5,
            },
            "unknown local units",
        ),
        (
            {
                "profile_version": 1,
                "profile_id": "bad.arbitrary",
                "global_weight": 1,
                "local_weight": 1,
                "local_reducer": "weighted_mean",
                "unit_weights": {"unit-9999-aaaaaaaaaaaa": 1},
            },
            "strict schema",
        ),
    ],
)
def test_hierarchical_profile_rejects_invalid_weights_and_unit_ids(profile, match):
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    unit_id = segmentation["units"][0]["unit_id"]
    with pytest.raises(HBQError, match=match):
        compute_hierarchical_score(
            profile,
            global_result={"scope_id": "work", "label": "Whole", **_result(80.0)},
            local_results=[{"scope_id": unit_id, "label": "One", **_result(70.0)}],
        )


def test_comparison_svg_shows_each_draft_without_computing_an_average():
    svg = render_chapter_comparison_svg(
        [
            {"name": "Draft A", "results": [{"label": "Chapter 1", **_result(78.0)}]},
            {"name": "Draft B", "results": [{"label": "Chapter 1", **_result(86.0)}]},
        ]
    )
    assert "Draft A" in svg and "Draft B" in svg
    assert ">78.0<" in svg and ">86.0<" in svg
    assert "Chapter 1" in svg


def test_strict_task_contract_schema_rejects_unknown_fields():
    segmentation = segment_longform(TEXT, artifact_id="synthetic-story")
    contract = _contract()
    contract["unexpected"] = True
    with pytest.raises(HBQError, match="strict schema"):
        validate_task_contract(
            contract,
            artifact_id="synthetic-story",
            unit_ids=[unit["unit_id"] for unit in segmentation["units"]],
        )
