"""Versioned exact selector-ID admission; historical core selection is unchanged."""
from __future__ import annotations

from typing import Any, Mapping, Sequence
from . import core

HISTORICAL = 'historical_permissive_v1'
EXACT = 'exact_selector_ids_v1'
COVERAGE = 'exact_selector_coverage_v2'
POLICIES = (HISTORICAL, EXACT, COVERAGE)


def resolve_selector_policy(requested: str | None, prior_configuration: Mapping[str, Any] | None = None) -> tuple[str, bool]:
    """Resolve new admission or preserve an existing configuration's policy.

    The boolean says whether to serialize the policy field. Missing historical
    fields stay missing; null/unknown fields are never historical aliases.
    """
    if requested is not None and (not isinstance(requested, str) or requested not in POLICIES):
        raise core.HBQError('Unsupported selector policy')
    if prior_configuration is None:
        return requested or EXACT, True
    if not isinstance(prior_configuration, Mapping):
        raise core.HBQError('Cannot resume: selector configuration is malformed')
    recorded = 'selector_policy' in prior_configuration
    policy = prior_configuration.get('selector_policy', HISTORICAL)
    if not isinstance(policy, str) or policy not in POLICIES:
        raise core.HBQError('Cannot resume: unsupported selector policy')
    if requested is not None and requested != policy:
        raise core.HBQError('Cannot resume: selector policy changed')
    return policy, recorded


def _bundle_errors(module_by_id: Mapping[str, Any], bundle: Mapping[str, Any], *, require_coverage: bool = False) -> list[str]:
    errors = []
    for domain in bundle.get('domains', []):
        for component in domain.get('components', []):
            module_id = component.get('module_id')
            label = f"Bundle {bundle.get('bundle_id')} domain {domain.get('domain_id')} component {module_id}"
            if module_id not in module_by_id:
                errors.append(f'{label}: missing module')
                continue
            module = module_by_id[module_id]
            try:
                leaves = list(core.walk_tree(module.get('tree', [])))
            except core.HBQError as exc:
                errors.append(f'{label}: {exc}')
                continue
            question_ids = {leaf.get('id') for leaf, _, _ in leaves if isinstance(leaf.get('id'), str)}
            group_ids: set[str] = set()
            def collect_groups(nodes):
                for node in nodes:
                    if node.get('type') == 'group':
                        if isinstance(node.get('id'), str):
                            group_ids.add(node['id'])
                        collect_groups(node.get('children', []))
            collect_groups(module.get('tree', []))
            for field, known in (('include_question_ids', question_ids), ('include_group_ids', group_ids)):
                if field not in component:
                    continue
                values = component[field]
                if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                    errors.append(f'{label}: {field} must be an array of non-empty exact ID strings')
                    continue
                # Membership is checked against the whole owning module BEFORE
                # intersection. Repeated IDs preserve historical set semantics;
                # absent/empty arrays preserve the historical unrestricted filter.
                missing = set(values) - known
                if missing:
                    errors.append(f"{label}: unknown {field}: {', '.join(sorted(missing))}")
            explicit = component.get('include_question_ids')
            groups = component.get('include_group_ids')
            if (require_coverage and isinstance(explicit, list) and explicit
                    and all(isinstance(qid, str) and qid for qid in explicit)
                    and set(explicit) <= question_ids and isinstance(groups, list) and groups
                    and all(isinstance(gid, str) and gid for gid in groups)
                    and set(groups) <= group_ids):
                selected = {leaf['id'] for leaf, _, _ in core.select_leaves(module, component)}
                filtered = set(explicit) - selected
                if filtered:
                    errors.append(f"{label}: explicit questions excluded by group filter: {', '.join(sorted(filtered))}")
    return errors


def selector_integrity_errors(modules: Sequence[dict[str, Any]], bundles: Sequence[Mapping[str, Any]], *,
                              require_coverage: bool = False) -> list[str]:
    try:
        module_by_id = core.index_modules(modules)
    except core.HBQError as exc:
        return [f'Exact selector admission requires a unique module index: {exc}']
    return [error for bundle in bundles for error in _bundle_errors(module_by_id, bundle, require_coverage=require_coverage)]


def admit_bundle_selectors(modules: Sequence[dict[str, Any]], bundle: Mapping[str, Any], policy: str) -> None:
    if policy not in POLICIES:
        raise core.HBQError('Unsupported selector policy')
    if policy in (EXACT, COVERAGE):
        errors = selector_integrity_errors(modules, [bundle], require_coverage=policy == COVERAGE)
        if errors:
            raise core.HBQError('; '.join(errors))


def compile_bundle_strict(modules: Sequence[dict[str, Any]], bundle: dict[str, Any], *,
                          task_contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Explicit strict API. The deterministic core packet format is unchanged."""
    admit_bundle_selectors(modules, bundle, EXACT)
    return core.compile_bundle(modules, bundle, task_contract=task_contract)
