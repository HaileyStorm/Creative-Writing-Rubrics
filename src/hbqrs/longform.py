"""Deterministic, transport-neutral building blocks for long-form HBQ-RS runs.

The functions in this module do not contact a model provider.  Callers supply
small callbacks for route selection, map construction, atomic evaluation, and
optional synthesis.  Every callback result is validated locally before it can
advance the workflow.
"""

from __future__ import annotations

from copy import deepcopy
from html import escape
import hashlib
import json
import math
import re
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from .core import HBQError, index_bundles, index_modules, load_data
from .paths import schema_dir


RouteSelector = Callable[[Mapping[str, Any]], Mapping[str, Any]]
MapBuilder = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Evaluator = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Synthesizer = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_CHAPTER_HEADING = re.compile(
    r"^(?:#{1,6}\s*)?(?:"
    r"(?:chapter|chap\.?|part|book)\s+(?:[0-9]+|[ivxlcdm]+|[a-z]+)(?:\s*[:.\-\u2014]\s*.+)?"
    r"|(?:prologue|epilogue|interlude|afterword)(?:\s*[:.\-\u2014]\s*.+)?"
    r")(?:\s*)$",
    re.IGNORECASE,
)
_SECTION_BREAK = re.compile(r"^\s*(?:\*{3,}|-{3,}|_{3,}|#{3,})\s*$")
_GENERIC_GATE_TERMS = (
    "requested operation",
    "follow the brief",
    "task fidelity",
    "overall quality",
    "author's goals",
    "authors goals",
)
_SUBJECTIVE_GATE_TERMS = (
    "compelling",
    "effective",
    "evocative",
    "interesting",
    "beautiful",
    "satisfying",
    "voice",
    "tone",
    "style",
    "mood",
    "genre feel",
)
_COMPLETION_STATUSES = {"complete", "work_in_progress", "excerpt", "unknown"}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _schema(name: str) -> dict[str, Any]:
    value = load_data(schema_dir() / name)
    if not isinstance(value, dict):
        raise HBQError(f"Schema {name} is not a JSON object")
    return value


def _validate_schema(value: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: list(error.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = "/".join(str(item) for item in first.absolute_path) or "<root>"
    raise HBQError(f"{label} does not satisfy its strict schema at {location}: {first.message}")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _local_evaluation_metadata(kind: str, text: str) -> dict[str, Any]:
    visible_lines = [line.strip() for line in text.splitlines() if line.strip()]
    brief_nonprose_front_matter = (
        kind == "front_matter"
        and len(visible_lines) <= 4
        and sum(len(line) for line in visible_lines) <= 256
        and not re.search(r"[.!?]", text)
    )
    return {
        "eligible": not brief_nonprose_front_matter,
        "reason": "brief_nonprose_front_matter" if brief_nonprose_front_matter else "substantive_unit",
    }


def segment_longform(text: str, *, artifact_id: str = "artifact") -> dict[str, Any]:
    """Split source text into source-preserving deterministic units.

    Explicit chapter-like headings are preferred.  When none exist, section
    breaks delimit units; otherwise the complete source is one work unit.
    Character spans are zero-based half-open Python string offsets.  Joining
    every returned ``text`` field reproduces the input byte-for-byte after the
    caller's original decoding.
    """

    if not isinstance(text, str) or not text:
        raise HBQError("Long-form source text must be a non-empty string")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise HBQError("artifact_id must be a non-empty string")

    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    headings: dict[int, str] = {}
    offset = 0
    for line in lines:
        visible = line.rstrip("\r\n")
        if _CHAPTER_HEADING.fullmatch(visible.strip()):
            starts.append(offset)
            headings[offset] = visible.strip().lstrip("#").strip()
        offset += len(line)

    kinds: dict[int, str] = {}
    if starts:
        if starts[0] != 0:
            starts.insert(0, 0)
            kinds[0] = "front_matter"
        for start in headings:
            kinds[start] = "chapter"
    else:
        starts = [0]
        offset = 0
        for line in lines:
            end = offset + len(line)
            if _SECTION_BREAK.fullmatch(line.rstrip("\r\n")) and end < len(text):
                starts.append(end)
            offset = end
        starts = sorted(set(starts))
        for start in starts:
            kinds[start] = "section" if len(starts) > 1 else "work"

    units: list[dict[str, Any]] = []
    for ordinal, start in enumerate(starts, start=1):
        end = starts[ordinal] if ordinal < len(starts) else len(text)
        unit_text = text[start:end]
        digest = _sha256_text(unit_text)
        units.append(
            {
                "unit_id": f"unit-{ordinal:04d}-{digest[:12]}",
                "ordinal": ordinal,
                "kind": kinds[start],
                "heading": headings.get(start),
                "span": {"start": start, "end": end},
                "lines": {
                    "start": _line_number(text, start),
                    "end": _line_number(text, max(start, end - 1)),
                },
                "char_count": len(unit_text),
                "sha256": digest,
                "local_evaluation": _local_evaluation_metadata(kinds[start], unit_text),
                "text": unit_text,
            }
        )

    if not any(unit["local_evaluation"]["eligible"] for unit in units):
        for unit in units:
            unit["local_evaluation"] = {"eligible": True, "reason": "only_available_unit"}

    if "".join(unit["text"] for unit in units) != text:
        raise HBQError("Internal segmentation error: units do not reconstruct the source")
    return {
        "segmentation_version": 2,
        "artifact_id": artifact_id,
        "source_sha256": _sha256_text(text),
        "char_count": len(text),
        "unit_count": len(units),
        "units": units,
    }


def resolve_local_bundle_plan(
    *,
    bundles: Sequence[dict[str, Any]],
    global_bundle_id: str,
    artifact_kind: str,
    segmentation: Mapping[str, Any],
    explicit_local_bundle_id: str | None = None,
) -> dict[str, str]:
    """Resolve the local rubric without asking a model or reducing coverage.

    An explicit selection always wins.  Otherwise, chapter-only substantive
    units use the unique catalog bundle whose scope is exactly ``chapter``.
    Mixed or non-chapter segmentation, or the absence of such a bundle, safely
    falls back to the global rubric.  Multiple exact candidates are rejected
    because choosing among them would require an unstated policy.
    """

    bundle_index = index_bundles(bundles)
    if global_bundle_id not in bundle_index:
        raise HBQError(f"Unknown global bundle {global_bundle_id!r}")
    if explicit_local_bundle_id is not None:
        if explicit_local_bundle_id not in bundle_index:
            raise HBQError(f"Unknown local bundle {explicit_local_bundle_id!r}")
        return {
            "global_bundle_id": global_bundle_id,
            "local_bundle_id": explicit_local_bundle_id,
            "local_bundle_mode": (
                "explicit_global_deep"
                if explicit_local_bundle_id == global_bundle_id
                else "explicit"
            ),
        }

    eligible_units = [
        unit for unit in segmentation["units"] if unit["local_evaluation"]["eligible"]
    ]
    if not eligible_units or any(unit["kind"] != "chapter" for unit in eligible_units):
        return {
            "global_bundle_id": global_bundle_id,
            "local_bundle_id": global_bundle_id,
            "local_bundle_mode": "global_fallback_mixed_or_nonchapter",
        }

    candidates = sorted(
        bundle_id
        for bundle_id, bundle in bundle_index.items()
        if artifact_kind in bundle.get("artifact_types", [])
        and set(bundle.get("valid_scopes", [])) == {"chapter"}
    )
    if len(candidates) > 1:
        raise HBQError(
            "Automatic local-bundle selection is ambiguous for chapter scope: "
            + ", ".join(candidates)
        )
    if candidates:
        return {
            "global_bundle_id": global_bundle_id,
            "local_bundle_id": candidates[0],
            "local_bundle_mode": "scope_auto",
        }
    return {
        "global_bundle_id": global_bundle_id,
        "local_bundle_id": global_bundle_id,
        "local_bundle_mode": "global_fallback_no_scope_bundle",
    }


def catalog_snapshot(
    modules: Sequence[dict[str, Any]], bundles: Sequence[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Return a compact, deterministic catalog suitable for route selection."""

    module_by_id = index_modules(modules)
    bundle_by_id = index_bundles(bundles)
    return {
        "bundles": [
            {
                "bundle_id": bundle_id,
                "title": str(record.get("title", bundle_id)),
                "description": str(record.get("description", "")),
                "artifact_types": list(record.get("artifact_types", [])),
                "valid_scopes": list(record.get("valid_scopes", [])),
                "module_ids": list(record.get("module_ids", [])),
            }
            for bundle_id, record in sorted(bundle_by_id.items())
        ],
        "modules": [
            {
                "module_id": module_id,
                "title": str(record.get("title", module_id)),
                "description": str(record.get("description", "")),
                "artifact_types": list(record.get("artifact_types", [])),
                "valid_scopes": list(record.get("valid_scopes", [])),
            }
            for module_id, record in sorted(module_by_id.items())
        ],
    }


def make_completion_contract(completion_status: str) -> dict[str, Any]:
    """Return the deterministic evaluation policy for supplied completion state."""

    if completion_status not in _COMPLETION_STATUSES:
        raise HBQError(f"Unknown completion_status: {completion_status!r}")
    incomplete = completion_status in {"work_in_progress", "excerpt"}
    completion_only_verdict = (
        "NOT_APPLICABLE" if incomplete else "EVALUATE" if completion_status == "complete" else "CANNOT_ASSESS"
    )
    return {
        "contract_version": 1,
        "completion_status": completion_status,
        "incomplete": incomplete,
        "completion_only_criterion_verdict": completion_only_verdict,
        "unavailable_supplied_evidence_verdict": "CANNOT_ASSESS",
        "assess_supplied_scope_craft": True,
        "assess_supplied_scope_continuity": True,
        "applicable_binding_requirements": "evaluate",
        "applicable_weighted_goals": "score",
    }


def make_route_request(
    segmentation: Mapping[str, Any],
    modules: Sequence[dict[str, Any]],
    bundles: Sequence[dict[str, Any]],
    *,
    artifact_kind: str,
    declared_scope: str,
    completion_status: str,
    driving_prompt: str = "",
    project_context: str = "",
    sample_text: str = "",
    local_sample_limit: int | None = None,
    required_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Build the data passed to a route-selector callback.

    ``sample_text`` is caller-selected; the core never silently extracts or
    sends source text.  A remote adapter can therefore disclose the exact
    request before transport.
    """

    make_completion_contract(completion_status)
    if local_sample_limit is not None and local_sample_limit < 1:
        raise HBQError("Local sample limit must be positive")
    return {
        "request_version": 1,
        "artifact_profile": {
            "artifact_id": segmentation["artifact_id"],
            "artifact_kind": artifact_kind,
            "declared_scope": declared_scope,
            "completion_status": completion_status,
            "unit_count": segmentation["unit_count"],
            "source_sha256": segmentation["source_sha256"],
        },
        "unit_inventory": [
            {
                "unit_id": unit["unit_id"],
                "ordinal": unit["ordinal"],
                "kind": unit["kind"],
                "heading": unit["heading"],
                "char_count": unit["char_count"],
                "sha256": unit["sha256"],
                "local_evaluation": deepcopy(unit["local_evaluation"]),
            }
            for unit in segmentation["units"]
        ],
        "driving_prompt": driving_prompt,
        "project_context": project_context,
        "sample_text": sample_text,
        "local_sample_limit": local_sample_limit,
        "local_coverage_mode": "complete" if local_sample_limit is None else "sampled",
        "required_bundle_id": required_bundle_id,
        "catalog": catalog_snapshot(modules, bundles),
        "response_schema": _schema("hbq_route_selection.schema.json"),
        "task_contract_schema": _schema("hbq_task_contract.schema.json"),
    }


def _require_atomic(question: str, label: str) -> None:
    lowered = question.casefold()
    if question.count("?") != 1 or "\n" in question or ";" in question:
        raise HBQError(f"{label} must contain one atomic binary question")
    if "and/or" in lowered:
        raise HBQError(f"{label} uses an ambiguous conjunction; split it into atomic questions")


def validate_task_contract(
    contract: Mapping[str, Any],
    *,
    artifact_id: str,
    unit_ids: Sequence[str],
    work_scope_aliases: Sequence[str] = (),
    expected_completion_status: str | None = None,
) -> dict[str, Any]:
    """Validate a task contract and the non-schema gate-safety invariants."""

    value = deepcopy(dict(contract))
    _validate_schema(value, _schema("hbq_task_contract.schema.json"), "Task contract")
    if value["artifact_id"] != artifact_id:
        raise HBQError("Task contract artifact_id does not match the segmented artifact")
    if (
        expected_completion_status is not None
        and value["context"]["completion_status"] != expected_completion_status
    ):
        raise HBQError("Task contract completion_status does not match the declared artifact status")

    aliases = {alias for alias in work_scope_aliases if alias and alias != "work"}
    for collection in (value["weighted_goals"], value["binding_requirements"]):
        for item in collection:
            item["applies_to"] = list(
                dict.fromkeys("work" if scope in aliases else scope for scope in item["applies_to"])
            )

    allowed_scopes = {"work", *unit_ids}
    identifiers: set[str] = set()
    for collection, id_key in (
        (value["preferences"], "id"),
        (value["priorities"], "id"),
        (value["weighted_goals"], "goal_id"),
        (value["binding_requirements"], "requirement_id"),
    ):
        for item in collection:
            identifier = item[id_key]
            if identifier in identifiers:
                raise HBQError(f"Task contract identifier is not unique: {identifier}")
            identifiers.add(identifier)

    for goal in value["weighted_goals"]:
        _require_atomic(goal["atomic_question"], f"Weighted goal {goal['goal_id']}")
        unknown = set(goal["applies_to"]) - allowed_scopes
        if unknown:
            raise HBQError(f"Weighted goal {goal['goal_id']} references unknown scopes: {sorted(unknown)}")

    for requirement in value["binding_requirements"]:
        label = f"Binding requirement {requirement['requirement_id']}"
        question = requirement["atomic_question"]
        _require_atomic(question, label)
        lowered = question.casefold()
        if any(term in lowered for term in (*_GENERIC_GATE_TERMS, *_SUBJECTIVE_GATE_TERMS)):
            raise HBQError(
                f"{label} is generic or subjective; represent it as a weighted_goal instead of a gate"
            )
        unknown = set(requirement["applies_to"]) - allowed_scopes
        if unknown:
            raise HBQError(f"{label} references unknown scopes: {sorted(unknown)}")
    return value


def validate_route_selection(
    selection: Mapping[str, Any],
    *,
    segmentation: Mapping[str, Any],
    modules: Sequence[dict[str, Any]],
    bundles: Sequence[dict[str, Any]],
    local_sample_limit: int | None = None,
    binding_contract_approved: bool = False,
    expected_completion_status: str | None = None,
) -> dict[str, Any]:
    """Validate a model-selected route against the exact local catalog."""

    value = deepcopy(dict(selection))
    route_schema = _schema("hbq_route_selection.schema.json")
    _validate_schema(value, route_schema, "Route selection")

    module_by_id = index_modules(modules)
    bundle_by_id = index_bundles(bundles)
    bundle_id = value["selected_bundle_id"]
    if bundle_id not in bundle_by_id:
        raise HBQError(f"Route selected unknown bundle: {bundle_id}")
    bundle = bundle_by_id[bundle_id]
    selected_modules = value["selected_module_ids"]
    unknown_modules = set(selected_modules) - set(module_by_id)
    if unknown_modules:
        raise HBQError(f"Route selected unknown modules: {sorted(unknown_modules)}")
    outside_bundle = set(selected_modules) - set(bundle.get("module_ids", []))
    if outside_bundle:
        raise HBQError(f"Route selected modules not owned by {bundle_id}: {sorted(outside_bundle)}")

    profile = value["artifact_profile"]
    if expected_completion_status is not None and profile["completion_status"] != expected_completion_status:
        raise HBQError("Route completion_status does not match the declared artifact status")
    if profile["unit_count"] != segmentation["unit_count"]:
        raise HBQError("Route unit_count does not match deterministic segmentation")
    if profile["source_sha256"] != segmentation["source_sha256"]:
        raise HBQError("Route source_sha256 does not match deterministic segmentation")
    artifact_types = set(bundle.get("artifact_types", []))
    if artifact_types and profile["artifact_kind"] not in artifact_types:
        raise HBQError(f"Bundle {bundle_id} does not support artifact type {profile['artifact_kind']!r}")
    valid_scopes = set(bundle.get("valid_scopes", []))
    if valid_scopes and profile["declared_scope"] not in valid_scopes:
        raise HBQError(f"Bundle {bundle_id} does not support scope {profile['declared_scope']!r}")

    unit_ids = [unit["unit_id"] for unit in segmentation["units"]]
    eligible_unit_ids = [
        unit["unit_id"]
        for unit in segmentation["units"]
        if unit["local_evaluation"]["eligible"]
    ]
    local_unit_ids = value["sampling_plan"]["unit_ids"]
    coverage_mode = value["sampling_plan"]["coverage_mode"]
    if local_sample_limit is None:
        if local_unit_ids != eligible_unit_ids or coverage_mode != "complete":
            raise HBQError(
                "Without an explicit local sample limit, local evaluation must cover every substantive unit in order"
            )
    elif len(local_unit_ids) > local_sample_limit:
        raise HBQError(
            f"Sampling plan selected {len(local_unit_ids)} units, exceeding the declared limit of {local_sample_limit}"
        )
    expected_mode = "complete" if local_unit_ids == eligible_unit_ids else "sampled"
    if coverage_mode != expected_mode:
        raise HBQError(f"Local coverage mode must be {expected_mode!r} for the selected unit set")
    unknown_units = set(local_unit_ids) - set(unit_ids)
    if unknown_units:
        raise HBQError(f"Sampling plan references unknown units: {sorted(unknown_units)}")
    ineligible_units = set(local_unit_ids) - set(eligible_unit_ids)
    if ineligible_units:
        raise HBQError(
            f"Local evaluation plan includes non-substantive front matter: {sorted(ineligible_units)}"
        )
    unit_position = {unit_id: index for index, unit_id in enumerate(unit_ids)}
    if local_unit_ids != sorted(local_unit_ids, key=unit_position.__getitem__):
        raise HBQError("Local evaluation unit IDs must preserve deterministic source order")
    stratified: set[str] = set()
    for stratum in value["sampling_plan"]["strata"]:
        outside_sample = set(stratum["unit_ids"]) - set(local_unit_ids)
        if outside_sample:
            raise HBQError(f"Sampling stratum {stratum['name']!r} contains unselected units")
        stratified.update(stratum["unit_ids"])
    if stratified != set(local_unit_ids):
        raise HBQError("Every selected local unit must appear in at least one declared stratum")

    reason_ids = {reason["catalog_id"] for reason in value["selection_reasons"]}
    unknown_reason_ids = reason_ids - {bundle_id, *selected_modules}
    if unknown_reason_ids:
        raise HBQError(f"Route gives selection reasons for unselected catalog IDs: {sorted(unknown_reason_ids)}")
    if bundle_id not in reason_ids:
        raise HBQError(f"Route lacks a selection reason for bundle {bundle_id}")
    value["task_contract"] = validate_task_contract(
        value["task_contract"],
        artifact_id=segmentation["artifact_id"],
        unit_ids=unit_ids,
        work_scope_aliases=[profile["declared_scope"]],
        expected_completion_status=profile["completion_status"],
    )
    if value["task_contract"]["binding_requirements"] and not binding_contract_approved:
        raise HBQError(
            "Automatic route selection cannot create binding requirements; "
            "supply a validated, artifact-bound task contract override"
        )
    return value


def complete_local_evaluation_plan(
    selection: Mapping[str, Any], segmentation: Mapping[str, Any]
) -> dict[str, Any]:
    """Freeze complete ordered local coverage independently of model routing."""

    value = deepcopy(dict(selection))
    unit_ids = [
        unit["unit_id"]
        for unit in segmentation["units"]
        if unit["local_evaluation"]["eligible"]
    ]
    value["sampling_plan"] = {
        "coverage_mode": "complete",
        "unit_ids": unit_ids,
        "strata": [{"name": "complete local evaluation", "unit_ids": unit_ids}],
        "global_map_required": True,
        "rationale": (
            "Default complete coverage evaluates every substantive deterministic unit in source order; "
            "brief non-prose front matter remains included in the mandatory whole-work pass."
        ),
    }
    return value


def make_map_request(
    segmentation: Mapping[str, Any], route_selection: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the exact request expected by a map-builder callback."""

    return {
        "request_version": 1,
        "artifact_id": segmentation["artifact_id"],
        "source_sha256": segmentation["source_sha256"],
        "completion_status": route_selection["artifact_profile"]["completion_status"],
        "units": deepcopy(segmentation["units"]),
        "task_contract": deepcopy(route_selection["task_contract"]),
        "response_schema": _schema("hbq_long_form_map.schema.json"),
    }


def validate_long_form_map(
    work_map: Mapping[str, Any], *, segmentation: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a long-form map against its source identity and unit inventory."""

    value = deepcopy(dict(work_map))
    _validate_schema(value, _schema("hbq_long_form_map.schema.json"), "Long-form map")
    if value["artifact_id"] != segmentation["artifact_id"]:
        raise HBQError("Long-form map artifact_id does not match the segmented artifact")
    if value["source_sha256"] != segmentation["source_sha256"]:
        raise HBQError("Long-form map source_sha256 does not match the segmented artifact")

    expected_units = [unit["unit_id"] for unit in segmentation["units"]]
    mapped_units = [unit["unit_id"] for unit in value["units"]]
    if mapped_units != expected_units:
        raise HBQError("Long-form map must contain every deterministic unit exactly once and in order")
    known = set(expected_units)
    for ledger in value["state_ledgers"]:
        for change in ledger["changes"]:
            if change["unit_id"] not in known:
                raise HBQError(f"State ledger references unknown unit {change['unit_id']}")
    for link in value["distant_links"]:
        if link["setup_unit_id"] not in known or link["payoff_unit_id"] not in known:
            raise HBQError("Distant setup/payoff link references an unknown unit")
    return value


def _interval(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    keys = ("observed", "lower", "upper")
    if not all(isinstance(value.get(key), (int, float)) for key in keys):
        return None
    result = {key: round(float(value[key]), 4) for key in keys}
    if not 0 <= result["lower"] <= result["upper"] <= 100:
        raise HBQError("Score interval must stay within 0..100 and lower must not exceed upper")
    if not result["lower"] <= result["observed"] <= result["upper"]:
        raise HBQError("Observed score must fall inside its interval")
    return result


def normalize_score_result(
    score_report: Mapping[str, Any], *, scope_id: str, label: str
) -> dict[str, Any]:
    """Reduce a deterministic score report to the reader-facing report shape."""

    if "control_state" in score_report and "score" in score_report:
        result = deepcopy(dict(score_report))
        result["scope_id"] = scope_id
        result["label"] = label
        return result

    state = score_report.get("hard_gate_status", score_report.get("status"))
    if state not in {"VALID", "INVALID", "UNRESOLVED", "PROVISIONAL", "INELIGIBLE"}:
        raise HBQError(f"Score report has unsupported control state: {state!r}")
    coverage = score_report.get("coverage")
    if not isinstance(coverage, (int, float)) or not 0 <= float(coverage) <= 1:
        raise HBQError("Score report coverage must be a number from 0 to 1")

    domains: list[dict[str, Any]] = []
    for domain in score_report.get("domains", []):
        if not isinstance(domain, Mapping):
            raise HBQError("Score report domains must be objects")
        domain_coverage = domain.get("coverage", 0)
        if not isinstance(domain_coverage, (int, float)) or not 0 <= float(domain_coverage) <= 1:
            raise HBQError("Domain coverage must be a number from 0 to 1")
        domains.append(
            {
                "domain_id": str(domain.get("domain_id", "domain")),
                "title": str(domain.get("title", domain.get("domain_id", "Domain"))),
                "coverage": round(float(domain_coverage), 4),
                "score": _interval(domain.get("score")),
            }
        )
    return {
        "scope_id": scope_id,
        "label": label,
        "control_state": state,
        "coverage": round(float(coverage), 4),
        "score": _interval(score_report.get("final_score")),
        "domains": domains,
        "weight_profile": deepcopy(score_report.get("weight_profile")),
    }


def _finite_weight(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HBQError(f"{label} must be a finite nonnegative number")
    weight = float(value)
    if not math.isfinite(weight) or weight < 0:
        raise HBQError(f"{label} must be a finite nonnegative number")
    return weight


def _weighted_interval(
    intervals: Sequence[Mapping[str, float]], weights: Sequence[float]
) -> dict[str, float]:
    total = sum(weights)
    if not math.isfinite(total) or total <= 0:
        raise HBQError("Score weights must have a positive finite sum")
    normalized = [weight / total for weight in weights]
    return {
        key: round(
            sum(float(interval[key]) * weight for interval, weight in zip(intervals, normalized)),
            6,
        )
        for key in ("observed", "lower", "upper")
    }


def validate_hierarchical_score_profile(
    profile: Mapping[str, Any],
    *,
    unit_ids: Sequence[str],
    unit_headings: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Validate an explicit profile against the exact evaluated unit IDs."""

    if not isinstance(profile, Mapping):
        raise HBQError("Hierarchical score profile must be a JSON object")
    value = deepcopy(dict(profile))
    _validate_schema(
        value,
        _schema("hbq_hierarchical_score_profile.schema.json"),
        "Hierarchical score profile",
    )
    global_weight = _finite_weight(value["global_weight"], "global_weight")
    local_weight = _finite_weight(value["local_weight"], "local_weight")
    if not math.isfinite(global_weight + local_weight) or global_weight + local_weight <= 0:
        raise HBQError("global_weight and local_weight must have a positive finite sum")
    if len(unit_ids) != len(set(unit_ids)):
        raise HBQError("Hierarchical score unit IDs must be unique")
    unfinished_unit_ids = value.get("unfinished_unit_ids", [])
    unknown_ids = sorted(set(unfinished_unit_ids) - set(unit_ids))
    if unknown_ids:
        raise HBQError(
            "Hierarchical score profile references unknown local units: " + ", ".join(unknown_ids)
        )
    unfinished_weight = _finite_weight(
        value.get("unfinished_unit_weight", 1.0), "unfinished_unit_weight"
    )
    structural_weight = _finite_weight(
        value.get("prologue_epilogue_weight", 1.0), "prologue_epilogue_weight"
    )
    if "prologue_epilogue_weight" in value and unit_headings is None:
        raise HBQError("prologue_epilogue_weight requires deterministic unit headings")
    unfinished = set(unfinished_unit_ids)
    materialized = []
    for unit_id in unit_ids:
        heading = (unit_headings or {}).get(unit_id)
        is_structural = isinstance(heading, str) and heading.casefold().startswith(
            ("prologue", "epilogue")
        )
        materialized.append(
            unfinished_weight if unit_id in unfinished else structural_weight if is_structural else 1.0
        )
    if local_weight > 0 and sum(materialized) <= 0:
        raise HBQError("Positive local_weight requires at least one positive unit weight")
    return value


def compute_hierarchical_score(
    profile: Mapping[str, Any] | None,
    *,
    global_result: Mapping[str, Any] | None,
    local_results: Sequence[Mapping[str, Any]],
    unit_headings: Mapping[str, str | None] | None = None,
) -> dict[str, Any] | None:
    """Combine existing score intervals under an explicit deterministic profile.

    This reducer never changes the underlying results or their control states.
    Ordinary units have equal weight one.  Optional shared modifiers apply to
    explicitly declared unfinished units and deterministically recognized
    prologue/epilogue headings.  For ``weakest_unit``, zero-modifier units are
    excluded and positive modifier magnitudes do not change weakest selection.
    """

    if profile is None:
        return None
    local_ids = [str(result["scope_id"]) for result in local_results]
    value = validate_hierarchical_score_profile(
        profile, unit_ids=local_ids, unit_headings=unit_headings
    )
    global_weight = _finite_weight(value["global_weight"], "global_weight")
    local_weight = _finite_weight(value["local_weight"], "local_weight")
    top_total = global_weight + local_weight
    unfinished_unit_ids = set(value.get("unfinished_unit_ids", []))
    unfinished_weight = _finite_weight(
        value.get("unfinished_unit_weight", 1.0), "unfinished_unit_weight"
    )
    structural_weight = _finite_weight(
        value.get("prologue_epilogue_weight", 1.0), "prologue_epilogue_weight"
    )
    structural_unit_ids = {
        unit_id
        for unit_id in local_ids
        if isinstance((unit_headings or {}).get(unit_id), str)
        and str((unit_headings or {})[unit_id]).casefold().startswith(("prologue", "epilogue"))
    }
    weight_classes = [
        (
            "unfinished",
            unfinished_weight,
        )
        if unit_id in unfinished_unit_ids
        else ("prologue_epilogue", structural_weight)
        if unit_id in structural_unit_ids
        else ("ordinary", 1.0)
        for unit_id in local_ids
    ]
    materialized_weights = [modifier for _weight_class, modifier in weight_classes]
    unit_weight_total = sum(materialized_weights)
    if local_weight > 0 and (not math.isfinite(unit_weight_total) or unit_weight_total <= 0):
        raise HBQError("Positive local_weight requires at least one positive unit weight")
    effective_unit_weights = (
        [weight / unit_weight_total for weight in materialized_weights]
        if unit_weight_total > 0
        else [0.0 for _ in materialized_weights]
    )

    global_interval = _interval(global_result.get("score")) if global_result is not None else None
    if global_weight > 0 and global_interval is None:
        raise HBQError("Positive global_weight requires an observed global score interval")

    local_interval: dict[str, float] | None = None
    weakest_unit_id: str | None = None
    if local_weight > 0:
        positive = [
            (result, weight)
            for result, weight in zip(local_results, materialized_weights)
            if weight > 0
        ]
        intervals: list[dict[str, float]] = []
        for result, _weight in positive:
            interval = _interval(result.get("score"))
            if interval is None:
                raise HBQError(
                    f"Positive unit weight requires an observed score interval for {result['scope_id']}"
                )
            intervals.append(interval)
        if value["local_reducer"] == "weighted_mean":
            local_interval = _weighted_interval(
                intervals, [weight for _result, weight in positive]
            )
        else:
            weakest_index = min(
                range(len(positive)), key=lambda index: (intervals[index]["observed"], index)
            )
            weakest_unit_id = str(positive[weakest_index][0]["scope_id"])
            local_interval = deepcopy(intervals[weakest_index])

    top_intervals: list[Mapping[str, float]] = []
    top_weights: list[float] = []
    if global_weight > 0:
        assert global_interval is not None
        top_intervals.append(global_interval)
        top_weights.append(global_weight)
    if local_weight > 0:
        assert local_interval is not None
        top_intervals.append(local_interval)
        top_weights.append(local_weight)
    score = _weighted_interval(top_intervals, top_weights)
    return {
        "profile_version": value["profile_version"],
        "profile_id": value["profile_id"],
        "method": "weighted_global_local",
        "local_reducer": value["local_reducer"],
        "score": score,
        "global_component": {
            "score": global_interval,
            "requested_weight": global_weight,
            "effective_weight": round(global_weight / top_total, 12),
        },
        "local_component": {
            "score": local_interval,
            "requested_weight": local_weight,
            "effective_weight": round(local_weight / top_total, 12),
            "selected_weakest_unit_id": weakest_unit_id,
            "unit_weight_assignments": [
                {
                    "unit_id": unit_id,
                    "weight_class": weight_class,
                    "class_modifier": weight,
                    "effective_weight": round(effective, 12),
                }
                for unit_id, (weight_class, weight), effective in zip(
                    local_ids, weight_classes, effective_unit_weights
                )
            ],
        },
        "unit_weight_policy": {
            "ordinary_unit_weight": 1.0,
            "unfinished_unit_weight": unfinished_weight,
            "unfinished_unit_ids": sorted(unfinished_unit_ids),
            "prologue_epilogue_weight": structural_weight,
            "prologue_epilogue_unit_ids": [
                unit_id for unit_id in local_ids if unit_id in structural_unit_ids
            ],
            "overlap_precedence": "unfinished_before_prologue_epilogue",
        },
        "policy": (
            "Explicit deterministic profile over existing global and local score intervals; "
            "it does not replace control states, completion handling, or underlying results."
        ),
    }


def build_workflow_report(
    *,
    segmentation: Mapping[str, Any],
    route_selection: Mapping[str, Any],
    work_map: Mapping[str, Any],
    global_result: Mapping[str, Any] | None,
    local_results: Sequence[Mapping[str, Any]],
    global_bundle_id: str | None = None,
    local_bundle_id: str | None = None,
    local_bundle_mode: str = "global_fallback_mixed_or_nonchapter",
    hierarchical_score_profile: Mapping[str, Any] | None = None,
    findings: Sequence[Mapping[str, Any]] = (),
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble and strictly validate the deterministic workflow report."""

    local_unit_ids = list(route_selection["sampling_plan"]["unit_ids"])
    local_by_id = {result["scope_id"]: deepcopy(dict(result)) for result in local_results}
    if len(local_by_id) != len(local_results):
        raise HBQError("Local results contain duplicate scope IDs")
    if set(local_by_id) != set(local_unit_ids):
        raise HBQError("Local results must cover every selected local unit exactly once")

    global_bundle_id = global_bundle_id or route_selection["selected_bundle_id"]
    local_bundle_id = local_bundle_id or global_bundle_id
    ordered_local_results = [local_by_id[unit_id] for unit_id in local_unit_ids]
    report = {
        "report_version": 1,
        "artifact": {
            "artifact_id": segmentation["artifact_id"],
            "source_sha256": segmentation["source_sha256"],
            "unit_count": segmentation["unit_count"],
        },
        "route": {
            "global_bundle_id": global_bundle_id,
            "local_bundle_id": local_bundle_id,
            "local_bundle_mode": local_bundle_mode,
            "module_ids": list(route_selection["selected_module_ids"]),
            "weighted_goal_count": len(route_selection["task_contract"]["weighted_goals"]),
            "binding_requirement_count": len(route_selection["task_contract"]["binding_requirements"]),
            "local_coverage_mode": route_selection["sampling_plan"]["coverage_mode"],
            "local_unit_ids": local_unit_ids,
            "non_substantive_unit_ids": [
                unit["unit_id"]
                for unit in segmentation["units"]
                if not unit["local_evaluation"]["eligible"]
            ],
        },
        "completion_contract": make_completion_contract(
            route_selection["artifact_profile"]["completion_status"]
        ),
        "orientation": deepcopy(work_map["orientation"]),
        "global_result": deepcopy(dict(global_result)) if global_result is not None else None,
        "local_results": ordered_local_results,
        "hierarchical_score": compute_hierarchical_score(
            hierarchical_score_profile,
            global_result=global_result,
            local_results=ordered_local_results,
            unit_headings={unit["unit_id"]: unit["heading"] for unit in segmentation["units"]},
        ),
        "findings": [deepcopy(dict(finding)) for finding in findings],
        "warnings": list(warnings),
    }
    _validate_schema(
        report, _schema("hbq_long_form_workflow_report.schema.json"), "Long-form workflow report"
    )
    return report


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _observed_score_text(result: Mapping[str, Any]) -> str:
    score = result.get("score")
    if not isinstance(score, Mapping):
        return "Not observed"
    return f"{score['observed']:.1f}"


def _uncertainty_bounds_text(result: Mapping[str, Any]) -> str:
    score = result.get("score")
    if not isinstance(score, Mapping):
        return "Not available"
    return f"{score['lower']:.1f}\u2013{score['upper']:.1f}"


def render_workflow_markdown(report: Mapping[str, Any]) -> str:
    """Render base results plus any explicitly requested deterministic hierarchy."""

    _validate_schema(
        report, _schema("hbq_long_form_workflow_report.schema.json"), "Long-form workflow report"
    )
    orientation = report["orientation"]
    lines = [
        "# Long-form evaluation",
        "",
        str(orientation["premise"]),
        "",
        f"**Evaluated scope:** {orientation['evaluated_scope']}",
    ]
    if orientation["cast"]:
        lines.extend(
            [
                "",
                "## Reader orientation",
                "",
                *[f"- **{member['name']}:** {member['role']}" for member in orientation["cast"]],
            ]
        )
    lines.extend(
        [
            "",
            "## How to read the results",
            "",
            "- **Control state** reports only objective, explicit binding requirements and whether enough evidence exists to decide them. Author preferences and aesthetic goals are weighted criteria, not gates.",
            "- **Coverage** is the weighted share of applicable selected criteria that received a YES or NO verdict.",
            "- **Observed score** is the deterministic score from relevant criteria that received a YES or NO verdict.",
            "- **Uncertainty bounds** are the non-statistical lowest and highest scores still possible if unassessed relevant criteria later resolve as failures or passes. They are not a confidence interval.",
            "- Local unit scores are independent diagnostics. They remain separate unless an explicit hierarchical score profile is shown below.",
            (
                "- **Work-in-progress rule:** criteria that require an unavailable finished work are NOT_APPLICABLE, not failures. Craft, continuity, applicable explicit requirements, and weighted goals are still evaluated on the supplied scope."
                if report["completion_contract"]["incomplete"]
                else "- **Completion rule:** completion-dependent criteria are evaluated according to the declared completion status."
            ),
            "",
            "## Route",
            "",
            f"Whole-work bundle `{report['route']['global_bundle_id']}` with {len(report['route']['module_ids'])} selected modules, "
            f"{report['route']['weighted_goal_count']} weighted author goals, and "
            f"{report['route']['binding_requirement_count']} binding requirements.",
            f"Local bundle `{report['route']['local_bundle_id']}`; selection mode `{report['route']['local_bundle_mode']}`.",
            f"Declared completion status: `{report['completion_contract']['completion_status']}`.",
            (
                f"Local coverage is complete across all {len(report['route']['local_unit_ids'])} substantive deterministic units."
                if report["route"]["local_coverage_mode"] == "complete"
                else f"Local coverage is an explicitly bounded diagnostic sample of {len(report['route']['local_unit_ids'])} units."
            ),
        ]
    )
    if report["route"]["non_substantive_unit_ids"]:
        lines.append(
            f"{len(report['route']['non_substantive_unit_ids'])} brief non-prose front-matter unit(s) "
            "remain in the whole-work evaluation but are omitted from local diagnostics."
        )

    global_result = report["global_result"]
    if global_result is not None:
        lines.extend(
            [
                "",
                "## Whole-work result",
                "",
                "| Scope | Control state | Coverage | Observed score | Uncertainty bounds |",
                "|---|---:|---:|---:|---:|",
                f"| {_md(global_result['label'])} | {global_result['control_state']} | "
                f"{global_result['coverage']:.1%} | {_observed_score_text(global_result)} | "
                f"{_uncertainty_bounds_text(global_result)} |",
            ]
        )
        if global_result["domains"]:
            lines.extend(
                [
                    "",
                    "### Whole-work components",
                    "",
                    "| Component | Coverage | Observed score | Uncertainty bounds |",
                    "|---|---:|---:|---:|",
                ]
            )
            for domain in global_result["domains"]:
                lines.append(
                    f"| {_md(domain['title'])} | {domain['coverage']:.1%} | "
                    f"{_observed_score_text({'score': domain['score']})} | "
                    f"{_uncertainty_bounds_text({'score': domain['score']})} |"
                )

    if report["local_results"]:
        lines.extend(
            [
                "",
                "## Local units",
                "",
                "| Unit | Control state | Coverage | Observed score | Uncertainty bounds |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for result in report["local_results"]:
            lines.append(
                f"| {_md(result['label'])} | {result['control_state']} | "
                f"{result['coverage']:.1%} | {_observed_score_text(result)} | "
                f"{_uncertainty_bounds_text(result)} |"
            )

    hierarchical = report["hierarchical_score"]
    if hierarchical is not None:
        global_component = hierarchical["global_component"]
        local_component = hierarchical["local_component"]
        lines.extend(
            [
                "",
                "## Hierarchical score (explicit profile)",
                "",
                f"Profile `{hierarchical['profile_id']}` combines existing intervals only; it makes no model call and does not replace control states, completion handling, or the underlying whole-work and local results.",
                f"Local reducer: `{hierarchical['local_reducer']}`.",
                "",
                "| Result | Observed score | Uncertainty bounds |",
                "|---|---:|---:|",
                f"| Hierarchical score | {_observed_score_text({'score': hierarchical['score']})} | {_uncertainty_bounds_text({'score': hierarchical['score']})} |",
                "",
                "| Component | Requested weight | Effective weight | Observed score | Uncertainty bounds |",
                "|---|---:|---:|---:|---:|",
                f"| Whole work | {global_component['requested_weight']:.6g} | {global_component['effective_weight']:.1%} | {_observed_score_text(global_component)} | {_uncertainty_bounds_text(global_component)} |",
                f"| Local `{hierarchical['local_reducer']}` | {local_component['requested_weight']:.6g} | {local_component['effective_weight']:.1%} | {_observed_score_text(local_component)} | {_uncertainty_bounds_text(local_component)} |",
                "",
                "Ordinary units have equal weight 1. Shared unfinished and prologue/epilogue modifiers are normalized over the evaluated local units.",
                "",
                "| Unit ID | Weight class | Class modifier | Effective local weight |",
                "|---|---|---:|---:|",
            ]
        )
        for unit_weight in local_component["unit_weight_assignments"]:
            lines.append(
                f"| `{unit_weight['unit_id']}` | `{unit_weight['weight_class']}` | {unit_weight['class_modifier']:.6g} | {unit_weight['effective_weight']:.1%} |"
            )
        if local_component["selected_weakest_unit_id"] is not None:
            lines.extend(
                [
                    "",
                    f"Weakest-unit selection: `{local_component['selected_weakest_unit_id']}`. Positive class modifiers include a unit; their magnitude does not alter weakest-unit selection.",
                ]
            )

    if report["findings"]:
        lines.extend(["", "## Findings", ""])
        for finding in report["findings"]:
            references = ", ".join(f"`{_md(reference)}`" for reference in finding["evidence_refs"])
            criteria = ", ".join(f"`{_md(criterion)}`" for criterion in finding["criterion_ids"])
            lines.append(f"### {_md(finding['kind'].replace('_', ' ').title())}: {_md(finding['finding'])}")
            lines.append("")
            lines.append(str(finding["why_it_matters"]))
            if references:
                lines.append(f" Evidence: {references}.")
            if criteria:
                lines.append(f" Criteria: {criteria}.")
            lines.append("")
    if report["warnings"]:
        lines.extend(["## Limitations", "", *[f"- {warning}" for warning in report["warnings"]], ""])
    return "\n".join(lines).rstrip() + "\n"


def render_chapter_comparison_svg(
    series: Sequence[Mapping[str, Any]], *, title: str = "Chapter-by-chapter comparison", width: int = 960
) -> str:
    """Render grouped local-score bars; no cross-unit aggregate is computed."""

    if not series:
        raise HBQError("At least one score series is required")
    names: list[str] = []
    by_name: list[dict[str, Mapping[str, Any]]] = []
    labels: list[str] = []
    for item in series:
        name = str(item.get("name", "")).strip()
        results = item.get("results")
        if not name or not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            raise HBQError("Each chart series needs a name and a results array")
        names.append(name)
        indexed: dict[str, Mapping[str, Any]] = {}
        for result in results:
            if not isinstance(result, Mapping) or not isinstance(result.get("label"), str):
                raise HBQError("Each chart result needs a label")
            label = result["label"]
            if label in indexed:
                raise HBQError(f"Chart series {name!r} repeats label {label!r}")
            indexed[label] = result
            if label not in labels:
                labels.append(label)
        by_name.append(indexed)

    left = 180
    right = 70
    top = 72
    row_height = max(34, 22 * len(series) + 12)
    height = top + len(labels) * row_height + 72
    chart_width = width - left - right
    colors = ("#2563eb", "#d97706", "#059669", "#7c3aed", "#dc2626")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(title)}</title>',
        '<desc id="desc">Independent unit scores with uncertainty intervals. No chapter average is calculated.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="20" y="30" font-family="sans-serif" font-size="20" font-weight="700" fill="#111827">{escape(title)}</text>',
    ]
    legend_x = 20
    for index, name in enumerate(names):
        color = colors[index % len(colors)]
        parts.extend(
            [
                f'<rect x="{legend_x}" y="44" width="12" height="12" rx="2" fill="{color}"/>',
                f'<text x="{legend_x + 18}" y="55" font-family="sans-serif" font-size="12" fill="#374151">{escape(name)}</text>',
            ]
        )
        legend_x += 24 + len(name) * 8
    for tick in range(0, 101, 20):
        x = left + chart_width * tick / 100
        parts.extend(
            [
                f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 44}" stroke="#e5e7eb"/>',
                f'<text x="{x:.1f}" y="{height - 24}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#6b7280">{tick}</text>',
            ]
        )
    for row, label in enumerate(labels):
        y0 = top + row * row_height
        parts.append(
            f'<text x="{left - 12}" y="{y0 + row_height / 2:.1f}" text-anchor="end" dominant-baseline="middle" font-family="sans-serif" font-size="12" fill="#111827">{escape(label)}</text>'
        )
        for index, indexed in enumerate(by_name):
            result = indexed.get(label)
            if result is None or not isinstance(result.get("score"), Mapping):
                continue
            score = result["score"]
            observed = float(score["observed"])
            lower = float(score["lower"])
            upper = float(score["upper"])
            if not 0 <= lower <= observed <= upper <= 100:
                raise HBQError("Chart score intervals must satisfy 0 <= lower <= observed <= upper <= 100")
            bar_y = y0 + 6 + index * 22
            bar_width = chart_width * observed / 100
            lower_x = left + chart_width * lower / 100
            upper_x = left + chart_width * upper / 100
            color = colors[index % len(colors)]
            parts.extend(
                [
                    f'<rect x="{left}" y="{bar_y}" width="{bar_width:.1f}" height="14" rx="2" fill="{color}" opacity="0.82"/>',
                    f'<line x1="{lower_x:.1f}" y1="{bar_y + 7}" x2="{upper_x:.1f}" y2="{bar_y + 7}" stroke="#111827" stroke-width="1.5"/>',
                    f'<line x1="{lower_x:.1f}" y1="{bar_y + 3}" x2="{lower_x:.1f}" y2="{bar_y + 11}" stroke="#111827"/>',
                    f'<line x1="{upper_x:.1f}" y1="{bar_y + 3}" x2="{upper_x:.1f}" y2="{bar_y + 11}" stroke="#111827"/>',
                    f'<text x="{min(left + bar_width + 5, width - 38):.1f}" y="{bar_y + 11}" font-family="sans-serif" font-size="10" fill="#111827">{observed:.1f}</text>',
                ]
            )
    parts.append(
        f'<text x="{left}" y="{height - 6}" font-family="sans-serif" font-size="11" fill="#6b7280">Bars are independent local diagnostics; whiskers show non-statistical uncertainty bounds.</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_local_scores_svg(report: Mapping[str, Any], *, title: str = "Local score profile") -> str:
    """Render the local results from one validated workflow report."""

    _validate_schema(
        report, _schema("hbq_long_form_workflow_report.schema.json"), "Long-form workflow report"
    )
    return render_chapter_comparison_svg(
        [{"name": report["artifact"]["artifact_id"], "results": report["local_results"]}], title=title
    )


def build_route_sample(text: str, *, limit: int = 12000) -> dict[str, Any]:
    """Build a bounded, auditable start/middle/end routing sample.

    The excerpt budget counts only source characters.  Explicit JSON metadata
    separators prevent adjacent excerpts from being mistaken for contiguous
    source and bind every excerpt to its original half-open character span.
    """

    if not isinstance(text, str) or not text:
        raise HBQError("Route sample source must be a non-empty string")
    if limit < 1:
        raise HBQError("Route sample limit must be positive")

    if len(text) <= limit:
        spans = [("complete", 0, len(text))]
    else:
        sizes = [limit // 3, limit // 3, limit - 2 * (limit // 3)]
        candidates = [
            ("start", 0, sizes[0]),
            ("middle", max(0, (len(text) - sizes[1]) // 2), 0),
            ("end", max(0, len(text) - sizes[2]), 0),
        ]
        candidates[1] = (candidates[1][0], candidates[1][1], candidates[1][1] + sizes[1])
        candidates[2] = (candidates[2][0], candidates[2][1], len(text))
        # Very small budgets can create empty or overlapping candidates.  Keep
        # the first occurrence of each source character and preserve order.
        spans = []
        covered_end = -1
        for label, start, end in candidates:
            start = max(start, covered_end)
            if end > start:
                spans.append((label, start, end))
                covered_end = end

    excerpts: list[dict[str, Any]] = []
    rendered: list[str] = []
    for label, start, end in spans:
        excerpt = text[start:end]
        record = {
            "label": label,
            "span": {"start": start, "end": end},
            "char_count": len(excerpt),
            "sha256": _sha256_text(excerpt),
        }
        excerpts.append(record)
        rendered.append(
            f"<<<HBQ-RS ROUTE EXCERPT {json.dumps(record, sort_keys=True, separators=(',', ':'))}>>>\n"
        )
        rendered.append(excerpt)
        if not excerpt.endswith("\n"):
            rendered.append("\n")
        rendered.append("<<<END HBQ-RS ROUTE EXCERPT>>>\n")
    sample_text = "".join(rendered)
    return {
        "sample_version": 1,
        "source_sha256": _sha256_text(text),
        "excerpt_char_count": sum(item["char_count"] for item in excerpts),
        "rendered_char_count": len(sample_text),
        "sha256": _sha256_text(sample_text),
        "excerpts": excerpts,
        "text": sample_text,
    }


def _default_route_sample(text: str, limit: int = 12000) -> str:
    return build_route_sample(text, limit=limit)["text"]


def _validate_source_excerpts(
    contract: Mapping[str, Any], *, driving_prompt: str, project_context: str
) -> None:
    pools = {
        "driving_prompt": (driving_prompt,),
        "explicit_user_requirement": (driving_prompt, project_context),
        "formal_specification": (driving_prompt, project_context),
        "user_preference": (driving_prompt, project_context),
    }
    items = [
        *contract["preferences"],
        *contract["priorities"],
        *contract["weighted_goals"],
        *contract["binding_requirements"],
    ]
    for item in items:
        source = item["source"]
        excerpt = source["exact_excerpt"]
        if not any(excerpt in pool for pool in pools[source["kind"]]):
            raise HBQError(
                f"Task contract source excerpt {source['reference']!r} is not present in its declared input"
            )


def run_longform_workflow(
    *,
    text: str,
    artifact_id: str,
    modules: Sequence[dict[str, Any]],
    bundles: Sequence[dict[str, Any]],
    artifact_kind: str,
    declared_scope: str,
    completion_status: str,
    route_selector: RouteSelector,
    map_builder: MapBuilder,
    evaluator: Evaluator,
    synthesizer: Synthesizer | None = None,
    driving_prompt: str = "",
    project_context: str = "",
    sample_text: str | None = None,
    local_sample_limit: int | None = None,
    local_bundle_id: str | None = None,
    hierarchical_score_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the complete transport-neutral long-form workflow.

    Callback contracts:

    * ``route_selector(request)`` returns an HBQ route-selection object.
    * ``map_builder(request)`` returns an HBQ long-form map.
    * ``evaluator(request)`` receives ``scope_kind`` (``global`` or ``local``),
      route, map, and task contract.  Local requests include exact unit text;
      the global request includes the complete source as ordered units rather
      than one undifferentiated string.  It returns either an HBQ score report
      or the normalized ``result`` shape from the workflow schema.
    * ``synthesizer(request)`` optionally returns exactly ``findings`` and
      ``warnings`` arrays.  It receives no raw source text.

    Provider adapters remain responsible for disclosure, transport, retries,
    response-schema enforcement, and provenance.  This function validates each
    semantic boundary and never averages local scores.  Local evaluation covers
    every deterministic unit unless the caller explicitly supplies
    ``local_sample_limit``.
    """

    segmentation = segment_longform(text, artifact_id=artifact_id)
    routed_sample = sample_text if sample_text is not None else _default_route_sample(text)
    route_request = make_route_request(
        segmentation,
        modules,
        bundles,
        artifact_kind=artifact_kind,
        declared_scope=declared_scope,
        completion_status=completion_status,
        driving_prompt=driving_prompt,
        project_context=project_context,
        sample_text=routed_sample,
        local_sample_limit=local_sample_limit,
    )
    selected = route_selector(route_request)
    if not isinstance(selected, Mapping):
        raise HBQError("Route selector must return a JSON object")
    if local_sample_limit is None:
        selected = complete_local_evaluation_plan(selected, segmentation)
    route = validate_route_selection(
        selected,
        segmentation=segmentation,
        modules=modules,
        bundles=bundles,
        local_sample_limit=local_sample_limit,
        expected_completion_status=completion_status,
    )
    _validate_source_excerpts(
        route["task_contract"],
        driving_prompt=driving_prompt,
        project_context=project_context,
    )

    mapped = map_builder(make_map_request(segmentation, route))
    if not isinstance(mapped, Mapping):
        raise HBQError("Map builder must return a JSON object")
    work_map = validate_long_form_map(mapped, segmentation=segmentation)
    local_bundle_plan = resolve_local_bundle_plan(
        bundles=bundles,
        global_bundle_id=route["selected_bundle_id"],
        artifact_kind=artifact_kind,
        segmentation=segmentation,
        explicit_local_bundle_id=local_bundle_id,
    )
    bundle_index = index_bundles(bundles)
    local_bundle = bundle_index[local_bundle_plan["local_bundle_id"]]
    common = {
        "request_version": 1,
        "artifact_id": artifact_id,
        "task_contract": deepcopy(route["task_contract"]),
        "long_form_map": deepcopy(work_map),
    }

    global_raw = evaluator(
        {
            **common,
            "bundle_id": route["selected_bundle_id"],
            "module_ids": deepcopy(route["selected_module_ids"]),
            "scope_kind": "global",
            "scope_id": "work",
            "scope_label": "Whole work",
            "units": deepcopy(segmentation["units"]),
        }
    )
    if not isinstance(global_raw, Mapping):
        raise HBQError("Evaluator must return a JSON object for the whole-work pass")
    global_result = normalize_score_result(global_raw, scope_id="work", label="Whole work")

    unit_by_id = {unit["unit_id"]: unit for unit in segmentation["units"]}
    local_results: list[dict[str, Any]] = []
    for unit_id in route["sampling_plan"]["unit_ids"]:
        unit = unit_by_id[unit_id]
        label = unit["heading"] or f"Unit {unit['ordinal']}"
        local_raw = evaluator(
            {
                **common,
                "bundle_id": local_bundle_plan["local_bundle_id"],
                "module_ids": deepcopy(
                    route["selected_module_ids"]
                    if local_bundle_plan["local_bundle_id"] == route["selected_bundle_id"]
                    else local_bundle["module_ids"]
                ),
                "scope_kind": "local",
                "scope_id": unit_id,
                "scope_label": label,
                "source_text": unit["text"],
                "unit": deepcopy(unit),
            }
        )
        if not isinstance(local_raw, Mapping):
            raise HBQError(f"Evaluator must return a JSON object for {unit_id}")
        local_results.append(normalize_score_result(local_raw, scope_id=unit_id, label=label))

    findings: Sequence[Mapping[str, Any]] = ()
    warnings: list[str] = list(work_map["limitations"])
    if synthesizer is not None:
        synthesis = synthesizer(
            {
                "request_version": 1,
                "artifact_id": artifact_id,
                "route": deepcopy(route),
                "long_form_map": deepcopy(work_map),
                "global_result": deepcopy(global_result),
                "local_results": deepcopy(local_results),
            }
        )
        if not isinstance(synthesis, Mapping) or set(synthesis) != {"findings", "warnings"}:
            raise HBQError("Synthesizer must return exactly findings and warnings arrays")
        if not isinstance(synthesis["findings"], Sequence) or isinstance(synthesis["findings"], (str, bytes)):
            raise HBQError("Synthesizer findings must be an array")
        if not isinstance(synthesis["warnings"], Sequence) or isinstance(synthesis["warnings"], (str, bytes)):
            raise HBQError("Synthesizer warnings must be an array")
        findings = synthesis["findings"]
        warnings.extend(str(warning) for warning in synthesis["warnings"])

    report = build_workflow_report(
        segmentation=segmentation,
        route_selection=route,
        work_map=work_map,
        global_result=global_result,
        local_results=local_results,
        global_bundle_id=local_bundle_plan["global_bundle_id"],
        local_bundle_id=local_bundle_plan["local_bundle_id"],
        local_bundle_mode=local_bundle_plan["local_bundle_mode"],
        hierarchical_score_profile=hierarchical_score_profile,
        findings=findings,
        warnings=warnings,
    )
    return {
        "segmentation": segmentation,
        "route_selection": route,
        "local_bundle_plan": local_bundle_plan,
        "long_form_map": work_map,
        "report": report,
        "markdown": render_workflow_markdown(report),
        "svg": render_local_scores_svg(report),
    }
