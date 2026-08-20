"""Strict, auditable scoring-weight profile materialization.

Profiles alter only the static registry and bundle weights that already feed
deterministic HBQ-RS scoring. Dynamic task-contract goal weights remain owned
by the frozen task contract and are intentionally outside this API. Profiles
also have no unit, chapter, scene, or other per-segment weight concept.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator

from .core import HBQError, compile_bundle
from .paths import schema_dir


SCORING_ROLES = {"domain", "penalty"}
OVERRIDE_COLLECTIONS = (
    "domain_weights",
    "component_weights",
    "group_weights",
    "question_weights",
    "penalty_caps",
)


def _validate_profile_schema(profile: Any) -> dict[str, Any]:
    if isinstance(profile, Mapping):
        numeric_fields = {
            "domain_weights": "weight",
            "component_weights": "weight",
            "group_weights": "weight",
            "question_weights": "weight",
            "penalty_caps": "cap_points",
        }
        for collection, field in numeric_fields.items():
            records = profile.get(collection)
            if not isinstance(records, list):
                continue
            for index, record in enumerate(records):
                if not isinstance(record, Mapping) or field not in record:
                    continue
                try:
                    number = float(record[field])
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(number):
                    raise HBQError(f"Weight profile {collection}/{index}/{field} must be finite")
    schema_path = schema_dir() / "hbq_weight_profile.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(profile),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        raise HBQError(f"Weight profile violates its strict schema at {location}: {error.message}")
    return deepcopy(dict(profile))


def _finite_number(value: Any, *, label: str, positive: bool) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise HBQError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise HBQError(f"{label} must be finite")
    if positive and number <= 0:
        raise HBQError(f"{label} must be strictly positive")
    if not positive and number < 0:
        raise HBQError(f"{label} must be nonnegative")
    return number


def _require_unique_keys(
    records: Sequence[Mapping[str, Any]],
    *,
    fields: tuple[str, ...],
    label: str,
) -> None:
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        key = tuple(record[field] for field in fields)
        if key in seen:
            rendered = "/".join(str(part) for part in key)
            raise HBQError(f"Duplicate {label} override: {rendered}")
        seen.add(key)


def _walk_nodes(nodes: Sequence[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes:
        yield node
        if node.get("type") == "group":
            yield from _walk_nodes(node.get("children", []))


def _tree_catalog(
    modules: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, dict[str, Any]]]], dict[str, list[tuple[str, dict[str, Any]]]]]:
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    questions: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for module in modules:
        module_id = str(module.get("module_id", ""))
        for node in _walk_nodes(module.get("tree", [])):
            node_id = str(node.get("id", ""))
            target = groups if node.get("type") == "group" else questions
            target.setdefault(node_id, []).append((module_id, node))
    return groups, questions


def _unique_catalog_node(
    catalog: Mapping[str, list[tuple[str, dict[str, Any]]]],
    node_id: str,
    *,
    kind: str,
) -> tuple[str, dict[str, Any]]:
    matches = catalog.get(node_id, [])
    if not matches:
        raise HBQError(f"Unknown {kind}_id: {node_id}")
    if len(matches) != 1:
        raise HBQError(f"Ambiguous {kind}_id in registry: {node_id}")
    return matches[0]


def _bundle_catalog(
    bundle: Mapping[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    domains: dict[str, dict[str, Any]] = {}
    components: dict[tuple[str, str], dict[str, Any]] = {}
    for domain in bundle.get("domains", []):
        domain_id = str(domain.get("domain_id", ""))
        if domain_id in domains:
            raise HBQError(f"Duplicate domain_id in bundle: {domain_id}")
        domains[domain_id] = domain
        for component in domain.get("components", []):
            key = (domain_id, str(component.get("module_id", "")))
            if key in components:
                raise HBQError(f"Duplicate component in bundle: {domain_id}/{key[1]}")
            components[key] = component
    penalties: dict[str, dict[str, Any]] = {}
    for penalty in bundle.get("penalty_modules", []):
        module_id = str(penalty.get("module_id", ""))
        if module_id in penalties:
            raise HBQError(f"Duplicate penalty module in bundle: {module_id}")
        penalties[module_id] = penalty
    return domains, components, penalties


def _compiled_roles(compiled: Mapping[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    question_roles: dict[str, set[str]] = {}
    group_roles: dict[str, set[str]] = {}

    def add(record: Mapping[str, Any], role: str) -> None:
        question_id = str(record["question"]["id"])
        question_roles.setdefault(question_id, set()).add(role)
        for group_id in record.get("group_ids", []):
            group_roles.setdefault(str(group_id), set()).add(role)

    for key, role in (
        ("domain_questions", "domain"),
        ("hard_gates", "hard_gate"),
        ("supplemental_questions", "supplemental"),
    ):
        for record in compiled.get(key, []):
            add(record, role)
    for penalty in compiled.get("penalty_groups", []):
        for record in penalty.get("questions", []):
            add(record, "penalty")
    return question_roles, group_roles


def _require_scoring_role(
    roles: Mapping[str, set[str]],
    node_id: str,
    *,
    kind: str,
) -> None:
    selected_roles = roles.get(node_id)
    if selected_roles is None:
        raise HBQError(f"{kind.capitalize()} {node_id} is outside the selected bundle")
    if not selected_roles.intersection(SCORING_ROLES):
        role_list = ", ".join(sorted(selected_roles))
        raise HBQError(
            f"{kind.capitalize()} {node_id} has only {role_list} role(s) and its weight does not affect scoring"
        )


def make_weight_profile(
    modules: Sequence[dict[str, Any]],
    bundle: Mapping[str, Any],
    *,
    profile_id: str = "custom",
) -> dict[str, Any]:
    """Return a complete editable profile containing every effective scoring weight.

    The profile is intentionally bundle-bound and has no unit-level fields.  It
    can be edited as JSON/YAML, passed back to :func:`materialize_weight_profile`,
    or used as the data source for an optional local configurator.
    """

    compiled = compile_bundle(modules, dict(bundle))
    question_roles, group_roles = _compiled_roles(compiled)
    groups, questions = _tree_catalog(modules)
    domains, components, penalties = _bundle_catalog(bundle)
    profile: dict[str, Any] = {
        "profile_version": 1,
        "profile_id": profile_id,
        "bundle_id": str(bundle.get("bundle_id", "")),
        "domain_weights": [
            {"domain_id": domain_id, "weight": float(domain.get("points", 0))}
            for domain_id, domain in domains.items()
        ],
        "component_weights": [
            {
                "domain_id": domain_id,
                "module_id": module_id,
                "weight": float(component.get("weight", 1.0)),
            }
            for (domain_id, module_id), component in components.items()
        ],
        "group_weights": [],
        "question_weights": [],
        "penalty_caps": [
            {"module_id": module_id, "cap_points": float(penalty["cap_points"])}
            for module_id, penalty in penalties.items()
        ],
    }
    for group_id, roles in sorted(group_roles.items()):
        if not roles.intersection(SCORING_ROLES):
            continue
        _, group = _unique_catalog_node(groups, group_id, kind="group")
        profile["group_weights"].append(
            {"group_id": group_id, "weight": float(group.get("weight", 1.0))}
        )
    for question_id, roles in sorted(question_roles.items()):
        if not roles.intersection(SCORING_ROLES):
            continue
        _, question = _unique_catalog_node(questions, question_id, kind="question")
        profile["question_weights"].append(
            {"question_id": question_id, "weight": float(question.get("weight", 1.0))}
        )
    for collection in OVERRIDE_COLLECTIONS:
        if not profile.get(collection):
            profile.pop(collection, None)
    _validate_profile_schema(profile)
    return profile


def materialize_weight_profile(
    modules: Sequence[dict[str, Any]],
    bundle: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Return deep-copied modules/bundle with a validated profile applied.

    Domain weights are relative inputs and, when supplied, must cover the
    bundle's exact domain set; their effective points are normalized to 100.
    Component, group, and question weights must be positive. Penalty caps may
    be zero. Overrides that cannot affect deterministic scoring (supplemental
    or hard-gate-only leaves/groups) are rejected rather than silently kept.

    The returned audit record preserves requested values, prior values, and
    effective values. Task-contract goal weights are not materialized because
    the task contract remains their sole owner.
    """

    source_bundle = dict(bundle)
    compiled = compile_bundle(modules, source_bundle)
    question_roles, group_roles = _compiled_roles(compiled)
    source_groups, source_questions = _tree_catalog(modules)

    transformed_modules = deepcopy(list(modules))
    transformed_bundle = deepcopy(source_bundle)
    copied_groups, copied_questions = _tree_catalog(transformed_modules)
    domains, components, penalties = _bundle_catalog(transformed_bundle)
    bundle_id = str(transformed_bundle.get("bundle_id", ""))

    requested = None if profile is None else _validate_profile_schema(profile)
    audit: dict[str, Any] = {
        "materialization_version": 1,
        "profile_id": None if requested is None else requested["profile_id"],
        "bundle_id": bundle_id,
        "identity": requested is None
        or not any(requested.get(collection) for collection in OVERRIDE_COLLECTIONS),
        "task_contract_weight_policy": (
            "Task-contract weighted goals remain owned by the frozen task contract and are not overridden."
        ),
        "requested": requested,
        "effective": {
            "domain_weights": [],
            "component_weights": [],
            "group_weights": [],
            "question_weights": [],
            "penalty_caps": [],
        },
    }
    if requested is None:
        return transformed_modules, transformed_bundle, audit
    if requested.get("bundle_id") is not None and requested["bundle_id"] != bundle_id:
        raise HBQError(
            f"Weight profile is bound to bundle {requested['bundle_id']!r}, not {bundle_id!r}"
        )

    domain_overrides = requested.get("domain_weights", [])
    _require_unique_keys(domain_overrides, fields=("domain_id",), label="domain")
    if domain_overrides:
        supplied_ids = {str(record["domain_id"]) for record in domain_overrides}
        expected_ids = set(domains)
        if supplied_ids != expected_ids:
            missing = sorted(expected_ids - supplied_ids)
            unknown = sorted(supplied_ids - expected_ids)
            details: list[str] = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if unknown:
                details.append(f"unknown {', '.join(unknown)}")
            raise HBQError(
                "Domain weight overrides must cover the bundle's exact domain set: " + "; ".join(details)
            )
        relative = {
            str(record["domain_id"]): _finite_number(
                record["weight"],
                label=f"domain weight {record['domain_id']}",
                positive=False,
            )
            for record in domain_overrides
        }
        total = math.fsum(relative.values())
        if total <= 0:
            raise HBQError("Domain weights must have a positive total")
        ordered_domains = list(domains.items())
        anchor_id = next(domain_id for domain_id, _ in reversed(ordered_domains) if relative[domain_id] > 0)
        normalized = {
            domain_id: relative[domain_id] / total * 100.0
            for domain_id, _ in ordered_domains
            if domain_id != anchor_id
        }
        normalized[anchor_id] = 100.0 - sum(normalized.values())
        for domain_id, domain in ordered_domains:
            prior_points = float(domain.get("points", 0))
            effective_points = normalized[domain_id]
            domain["points"] = effective_points
            audit["effective"]["domain_weights"].append(
                {
                    "domain_id": domain_id,
                    "requested_weight": relative[domain_id],
                    "previous_points": prior_points,
                    "effective_points": effective_points,
                }
            )

    component_overrides = requested.get("component_weights", [])
    _require_unique_keys(
        component_overrides,
        fields=("domain_id", "module_id"),
        label="component",
    )
    for record in component_overrides:
        domain_id = str(record["domain_id"])
        module_id = str(record["module_id"])
        key = (domain_id, module_id)
        if key not in components:
            raise HBQError(f"Component {domain_id}/{module_id} is outside the selected bundle")
        weight = _finite_number(
            record["weight"],
            label=f"component weight {domain_id}/{module_id}",
            positive=True,
        )
        component = components[key]
        previous = float(component.get("weight", 1.0))
        component["weight"] = weight
        audit["effective"]["component_weights"].append(
            {
                "domain_id": domain_id,
                "module_id": module_id,
                "requested_weight": weight,
                "previous_weight": previous,
                "effective_weight": weight,
            }
        )

    group_overrides = requested.get("group_weights", [])
    _require_unique_keys(group_overrides, fields=("group_id",), label="group")
    for record in group_overrides:
        group_id = str(record["group_id"])
        _unique_catalog_node(source_groups, group_id, kind="group")
        _require_scoring_role(group_roles, group_id, kind="group")
        _, group = _unique_catalog_node(copied_groups, group_id, kind="group")
        weight = _finite_number(
            record["weight"],
            label=f"group weight {group_id}",
            positive=True,
        )
        previous = float(group.get("weight", 1.0))
        group["weight"] = weight
        audit["effective"]["group_weights"].append(
            {
                "group_id": group_id,
                "requested_weight": weight,
                "previous_weight": previous,
                "effective_weight": weight,
            }
        )

    question_overrides = requested.get("question_weights", [])
    _require_unique_keys(question_overrides, fields=("question_id",), label="question")
    for record in question_overrides:
        question_id = str(record["question_id"])
        _unique_catalog_node(source_questions, question_id, kind="question")
        _require_scoring_role(question_roles, question_id, kind="question")
        _, question = _unique_catalog_node(copied_questions, question_id, kind="question")
        weight = _finite_number(
            record["weight"],
            label=f"question weight {question_id}",
            positive=True,
        )
        previous = float(question.get("weight", 1.0))
        question["weight"] = weight
        audit["effective"]["question_weights"].append(
            {
                "question_id": question_id,
                "requested_weight": weight,
                "previous_weight": previous,
                "effective_weight": weight,
            }
        )

    penalty_overrides = requested.get("penalty_caps", [])
    _require_unique_keys(penalty_overrides, fields=("module_id",), label="penalty cap")
    for record in penalty_overrides:
        module_id = str(record["module_id"])
        if module_id not in penalties:
            raise HBQError(f"Penalty module {module_id} is outside the selected bundle")
        cap = _finite_number(
            record["cap_points"],
            label=f"penalty cap {module_id}",
            positive=False,
        )
        penalty = penalties[module_id]
        previous = float(penalty["cap_points"])
        penalty["cap_points"] = cap
        audit["effective"]["penalty_caps"].append(
            {
                "module_id": module_id,
                "requested_cap_points": cap,
                "previous_cap_points": previous,
                "effective_cap_points": cap,
            }
        )

    return transformed_modules, transformed_bundle, audit
