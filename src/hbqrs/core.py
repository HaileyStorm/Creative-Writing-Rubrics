#!/usr/bin/env python3
"""Validate, compile, and score HBQ-RS creative-rubric bundles.

All scoring leaves are positive propositions: YES is a pass, NO is a failure,
NOT_APPLICABLE removes a leaf, and CANNOT_ASSESS preserves uncertainty.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import yaml

VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
SCORED_TYPES = {"scored", "subjective_threshold"}
QUESTION_TYPES = {"hard_gate", "scored", "subjective_threshold", "diagnostic"}


@dataclass(frozen=True)
class SelectedLeaf:
    """One selected question with its effective bundle-scoring metadata.

    Attributes:
        module_id: Owning rubric module.
        domain_id: Scored domain, penalty identifier, or supplemental role.
        question: Original question record.
        component_weight: Bundle component multiplier.
        group_weight: Product of ancestor-group weights.
        effective_weight: Leaf × component × ancestor weights.
        group_ids: Ordered ancestor group IDs.
        role: ``domain``, ``hard_gate``, ``penalty``, or ``supplemental``.
        cap_points: Penalty cap when role is ``penalty``.
    """

    module_id: str
    domain_id: str | None
    question: dict[str, Any]
    component_weight: float
    group_weight: float
    effective_weight: float
    group_ids: tuple[str, ...]
    role: str
    cap_points: float | None = None


class HBQError(ValueError):
    """Raised when a registry, bundle, or verdict set is invalid."""


def _read_jsonl(path: Path) -> list[Any]:
    """Read a JSON Lines file, ignoring blank lines."""

    values: list[Any] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise HBQError(f"Invalid JSONL in {path} at line {line_number}: {exc}") from exc
    return values


def load_data(path: str | Path) -> Any:
    """Load JSON, JSONL, YAML, or YML from ``path``."""

    source = Path(path)
    if not source.exists():
        raise HBQError(f"File does not exist: {source}")
    suffix = source.suffix.lower()
    if suffix == ".jsonl":
        return _read_jsonl(source)
    if suffix == ".json":
        return json.loads(source.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(source.read_text(encoding="utf-8"))
    raise HBQError(f"Unsupported file type for {source}; expected JSON, JSONL, YAML, or YML")


def write_data(path: str | Path | None, value: Any, *, fmt: str | None = None) -> None:
    """Write a value as JSON or YAML, or print it when no path is supplied."""

    target = Path(path) if path else None
    selected = (fmt or (target.suffix.lstrip(".") if target else "json")).lower()
    if selected in {"yaml", "yml"}:
        text = yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110)
    elif selected == "json":
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    else:
        raise HBQError(f"Unsupported output format: {selected}")
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _ensure_list(value: Any, label: str) -> list[dict[str, Any]]:
    """Normalize a loaded registry or bundle collection to a list of objects."""

    if isinstance(value, dict):
        if label == "modules" and "modules" in value:
            value = value["modules"]
        elif label == "bundles" and "bundles" in value:
            value = value["bundles"]
        else:
            value = [value]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise HBQError(f"Expected {label} to be an object or list of objects")
    return value


def load_modules(path: str | Path) -> list[dict[str, Any]]:
    """Load one or more HBQ-RS module records."""

    return _ensure_list(load_data(path), "modules")


def load_bundles(path: str | Path) -> list[dict[str, Any]]:
    """Load one or more HBQ-RS bundle records."""

    return _ensure_list(load_data(path), "bundles")


def walk_tree(
    nodes: Sequence[dict[str, Any]],
    *,
    group_ids: tuple[str, ...] = (),
    group_weight: float = 1.0,
) -> Iterable[tuple[dict[str, Any], tuple[str, ...], float]]:
    """Yield each question, ancestor IDs, and product of ancestor weights."""

    for node in nodes:
        node_type = node.get("type")
        if node_type == "question":
            yield node, group_ids, group_weight
        elif node_type == "group":
            weight = float(node.get("weight", 1.0))
            yield from walk_tree(
                node.get("children", []),
                group_ids=(*group_ids, str(node.get("id", ""))),
                group_weight=group_weight * weight,
            )
        else:
            raise HBQError(f"Unknown rubric-tree node type: {node_type!r}")


def select_leaves(module_record: dict[str, Any], component: Mapping[str, Any]) -> list[tuple[dict[str, Any], tuple[str, ...], float]]:
    """Select leaves from a module according to a bundle component's selectors."""

    exact = set(component.get("include_question_ids", []) or [])
    groups = set(component.get("include_group_ids", []) or [])
    selected: list[tuple[dict[str, Any], tuple[str, ...], float]] = []
    for leaf, ancestors, group_weight in walk_tree(module_record.get("tree", [])):
        if exact and leaf.get("id") not in exact:
            continue
        if groups and not groups.intersection(ancestors):
            continue
        selected.append((leaf, ancestors, group_weight))
    return selected


def index_modules(modules: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Create a unique module-ID index."""

    result: dict[str, dict[str, Any]] = {}
    for record in modules:
        module_id = record.get("module_id")
        if not isinstance(module_id, str) or not module_id:
            raise HBQError("Every module needs a non-empty module_id")
        if module_id in result:
            raise HBQError(f"Duplicate module_id: {module_id}")
        result[module_id] = record
    return result


def index_bundles(bundles: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Create a unique bundle-ID index."""

    result: dict[str, dict[str, Any]] = {}
    for record in bundles:
        bundle_id = record.get("bundle_id")
        if not isinstance(bundle_id, str) or not bundle_id:
            raise HBQError("Every bundle needs a non-empty bundle_id")
        if bundle_id in result:
            raise HBQError(f"Duplicate bundle_id: {bundle_id}")
        result[bundle_id] = record
    return result


def validate_registry(
    modules: Sequence[dict[str, Any]],
    bundles: Sequence[dict[str, Any]],
    *,
    module_schema: Mapping[str, Any] | None = None,
    bundle_schema: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return structural, ownership, selector, and optional schema errors."""

    errors: list[str] = []
    try:
        module_by_id = index_modules(modules)
    except HBQError as exc:
        errors.append(str(exc))
        module_by_id = {m.get("module_id", f"invalid:{i}"): m for i, m in enumerate(modules)}
    try:
        index_bundles(bundles)
    except HBQError as exc:
        errors.append(str(exc))

    question_ids: set[str] = set()
    criterion_owners: dict[str, tuple[str, str]] = {}
    for module_id, record in module_by_id.items():
        try:
            leaves = list(walk_tree(record.get("tree", [])))
        except HBQError as exc:
            errors.append(f"{module_id}: {exc}")
            continue
        if not leaves:
            errors.append(f"Module {module_id} contains no questions")
        for leaf, _, _ in leaves:
            qid = leaf.get("id")
            if not isinstance(qid, str) or not qid:
                errors.append(f"Module {module_id} has a question without an ID")
                continue
            if qid in question_ids:
                errors.append(f"Duplicate question ID: {qid}")
            question_ids.add(qid)
            if leaf.get("pass_answer") != "YES":
                errors.append(f"Question {qid} is not positive-oriented")
            if not str(leaf.get("text", "")).rstrip().endswith("?"):
                errors.append(f"Question {qid} is not phrased as a question")
            if leaf.get("question_type") not in QUESTION_TYPES:
                errors.append(f"Question {qid} has invalid question_type {leaf.get('question_type')!r}")
            try:
                if float(leaf.get("weight", 0)) <= 0:
                    errors.append(f"Question {qid} has non-positive weight")
            except (TypeError, ValueError):
                errors.append(f"Question {qid} has a nonnumeric weight")
            key = leaf.get("criterion_key")
            if not isinstance(key, str) or not key:
                errors.append(f"Question {qid} lacks criterion_key")
            elif key in criterion_owners and criterion_owners[key] != (module_id, qid):
                errors.append(
                    f"Criterion {key} has multiple owners: {criterion_owners[key]} and {(module_id, qid)}"
                )
            else:
                criterion_owners[key] = (module_id, qid)

    for bundle in bundles:
        bundle_id = bundle.get("bundle_id", "<missing>")
        domains = bundle.get("domains", [])
        try:
            total = sum(float(domain.get("points", 0)) for domain in domains)
            if not math.isclose(total, 100.0, abs_tol=1e-8):
                errors.append(f"Bundle {bundle_id} domain points sum to {total}, not 100")
        except (TypeError, ValueError):
            errors.append(f"Bundle {bundle_id} contains nonnumeric domain points")
        scored_question_owners: dict[str, str] = {}
        for domain in domains:
            domain_id = domain.get("domain_id", "<missing>")
            selected_count = 0
            for component in domain.get("components", []):
                module_id = component.get("module_id")
                if module_id not in module_by_id:
                    errors.append(f"Bundle {bundle_id} references missing module {module_id}")
                    continue
                leaves = select_leaves(module_by_id[module_id], component)
                if not leaves:
                    errors.append(
                        f"Bundle {bundle_id} domain {domain_id} component {module_id} selects no questions"
                    )
                selected_count += len(leaves)
                for leaf, _, _ in leaves:
                    qid = leaf["id"]
                    if qid in scored_question_owners:
                        errors.append(
                            f"Bundle {bundle_id} double-scores {qid} in "
                            f"{scored_question_owners[qid]} and {domain_id}"
                        )
                    else:
                        scored_question_owners[qid] = str(domain_id)
            if selected_count == 0:
                errors.append(f"Bundle {bundle_id} domain {domain_id} has no selected questions")
        for penalty in bundle.get("penalty_modules", []):
            module_id = penalty.get("module_id")
            if module_id not in module_by_id:
                errors.append(f"Bundle {bundle_id} references missing penalty module {module_id}")
            try:
                if float(penalty.get("cap_points", -1)) < 0:
                    errors.append(f"Bundle {bundle_id} has a negative penalty cap")
            except (TypeError, ValueError):
                errors.append(f"Bundle {bundle_id} has a nonnumeric penalty cap")

    if module_schema is not None or bundle_schema is not None:
        try:
            import jsonschema
        except ImportError:
            errors.append("jsonschema is unavailable; schema validation was requested")
        else:
            if module_schema is not None:
                validator = jsonschema.Draft202012Validator(module_schema)
                for record in modules:
                    for err in validator.iter_errors(record):
                        location = "/".join(str(p) for p in err.absolute_path)
                        errors.append(f"Schema module {record.get('module_id')}/{location}: {err.message}")
            if bundle_schema is not None:
                validator = jsonschema.Draft202012Validator(bundle_schema)
                for record in bundles:
                    for err in validator.iter_errors(record):
                        location = "/".join(str(p) for p in err.absolute_path)
                        errors.append(f"Schema bundle {record.get('bundle_id')}/{location}: {err.message}")
    return errors


def compile_bundle(
    modules: Sequence[dict[str, Any]],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """Compile a bundle to a flat, judge-ready question packet.

    Domain questions, hard gates, bounded penalty questions, and unscored overlay
    questions are separated.  The packet retains all original activation text,
    profile metadata, evidence requirements, and effective weights.
    """

    module_by_id = index_modules(modules)
    bundle_id = str(bundle.get("bundle_id"))
    domain_questions: list[dict[str, Any]] = []
    hard_gates: dict[str, dict[str, Any]] = {}
    supplemental: dict[str, dict[str, Any]] = {}
    used_module_ids: set[str] = set()
    scored_qids: dict[str, str] = {}

    for domain in bundle.get("domains", []):
        domain_id = str(domain["domain_id"])
        for component in domain.get("components", []):
            module_id = str(component["module_id"])
            if module_id not in module_by_id:
                raise HBQError(f"Bundle {bundle_id} references missing module {module_id}")
            used_module_ids.add(module_id)
            component_weight = float(component.get("weight", 1.0))
            leaves = select_leaves(module_by_id[module_id], component)
            if not leaves:
                raise HBQError(f"Component {module_id} in {bundle_id}/{domain_id} selects no questions")
            for leaf, ancestors, group_weight in leaves:
                qid = leaf["id"]
                qtype = leaf["question_type"]
                record = {
                    "module_id": module_id,
                    "domain_id": domain_id,
                    "domain_title": domain.get("title", domain_id),
                    "domain_points": float(domain.get("points", 0)),
                    "question": leaf,
                    "component_weight": component_weight,
                    "group_weight": group_weight,
                    "effective_weight": float(leaf["weight"]) * component_weight * group_weight,
                    "group_ids": list(ancestors),
                }
                if qtype == "hard_gate":
                    hard_gates.setdefault(qid, {**record, "role": "hard_gate"})
                elif qtype in SCORED_TYPES:
                    if qid in scored_qids:
                        raise HBQError(
                            f"Bundle {bundle_id} double-scores {qid} in {scored_qids[qid]} and {domain_id}"
                        )
                    scored_qids[qid] = domain_id
                    domain_questions.append({**record, "role": "domain"})
                else:
                    supplemental.setdefault(qid, {**record, "role": "supplemental"})

    penalty_groups: list[dict[str, Any]] = []
    penalty_module_ids: set[str] = set()
    for penalty in bundle.get("penalty_modules", []):
        module_id = str(penalty["module_id"])
        if module_id not in module_by_id:
            raise HBQError(f"Bundle {bundle_id} references missing penalty module {module_id}")
        penalty_module_ids.add(module_id)
        used_module_ids.add(module_id)
        questions: list[dict[str, Any]] = []
        for leaf, ancestors, group_weight in walk_tree(module_by_id[module_id].get("tree", [])):
            questions.append(
                {
                    "module_id": module_id,
                    "penalty_id": module_id,
                    "question": leaf,
                    "component_weight": 1.0,
                    "group_weight": group_weight,
                    "effective_weight": float(leaf["weight"]) * group_weight,
                    "group_ids": list(ancestors),
                    "role": "penalty",
                    "cap_points": float(penalty["cap_points"]),
                }
            )
        penalty_groups.append(
            {
                "module_id": module_id,
                "title": module_by_id[module_id].get("title", module_id),
                "cap_points": float(penalty["cap_points"]),
                "questions": questions,
            }
        )

    # Modules that are attached as overlays but own no bundle points remain
    # visible to the judge as supplemental diagnostics.  They never silently
    # acquire score weight.
    for module_id in bundle.get("module_ids", []):
        module_id = str(module_id)
        if module_id in used_module_ids or module_id in penalty_module_ids:
            continue
        if module_id not in module_by_id:
            raise HBQError(f"Bundle {bundle_id} lists missing module {module_id}")
        for leaf, ancestors, group_weight in walk_tree(module_by_id[module_id].get("tree", [])):
            qid = leaf["id"]
            record = {
                "module_id": module_id,
                "domain_id": None,
                "question": leaf,
                "component_weight": 1.0,
                "group_weight": group_weight,
                "effective_weight": float(leaf["weight"]) * group_weight,
                "group_ids": list(ancestors),
                "role": "hard_gate" if leaf["question_type"] == "hard_gate" else "supplemental",
            }
            if leaf["question_type"] == "hard_gate":
                hard_gates.setdefault(qid, record)
            else:
                supplemental.setdefault(qid, record)

    return {
        "standard": bundle.get("standard"),
        "bundle_id": bundle_id,
        "bundle_version": bundle.get("version"),
        "title": bundle.get("title"),
        "description": bundle.get("description"),
        "artifact_types": bundle.get("artifact_types", []),
        "valid_scopes": bundle.get("valid_scopes", []),
        "profile": bundle.get("profile", {}),
        "judge_policy": bundle.get("judge_policy", {}),
        "coverage_policy": bundle.get("coverage_policy", {}),
        "hard_gate_policy": bundle.get("hard_gate_policy", {}),
        "excerpt_and_incomplete_policy": bundle.get("excerpt_and_incomplete_policy", {}),
        "domains": bundle.get("domains", []),
        "domain_questions": domain_questions,
        "hard_gates": list(hard_gates.values()),
        "penalty_groups": penalty_groups,
        "supplemental_questions": list(supplemental.values()),
        "counts": {
            "domain_questions": len(domain_questions),
            "hard_gates": len(hard_gates),
            "penalty_questions": sum(len(group["questions"]) for group in penalty_groups),
            "supplemental_questions": len(supplemental),
        },
    }


def compiled_questions(compiled: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a compiled bundle into its ordered judge-question records."""

    rows: list[dict[str, Any]] = []
    for item in compiled.get("domain_questions", []):
        rows.append({**item, "role": "domain"})
    for item in compiled.get("hard_gates", []):
        rows.append({**item, "role": "hard_gate"})
    for group in compiled.get("penalty_groups", []):
        for item in group.get("questions", []):
            rows.append({**item, "role": "penalty", "penalty_module_id": group.get("module_id")})
    for item in compiled.get("supplemental_questions", []):
        rows.append({**item, "role": "supplemental"})
    return rows


def _normalize_verdict_records(value: Any) -> list[dict[str, Any]]:
    """Normalize a verdict collection to a list of objects."""

    if isinstance(value, dict):
        if "verdicts" in value:
            value = value["verdicts"]
        elif "question_id" in value:
            value = [value]
        else:
            # Convenience compact map: {question_id: "YES"}.
            compact: list[dict[str, Any]] = []
            for question_id, verdict in value.items():
                if isinstance(verdict, str):
                    compact.append({"question_id": question_id, "verdict": verdict})
                elif isinstance(verdict, dict):
                    compact.append({"question_id": question_id, **verdict})
                else:
                    raise HBQError(f"Unsupported compact verdict value for {question_id}")
            value = compact
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise HBQError("Verdicts must be a list, an object containing 'verdicts', or a compact question map")
    return value


def load_verdicts(path: str | Path) -> list[dict[str, Any]]:
    """Load verdict records from JSON, JSONL, or YAML."""

    return _normalize_verdict_records(load_data(path))


def _verdict_index(verdicts: Sequence[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Index verdicts by question and report duplicates or malformed records."""

    result: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for index, record in enumerate(verdicts):
        question_id = record.get("question_id")
        verdict = str(record.get("verdict", "")).upper()
        if not isinstance(question_id, str) or not question_id:
            issues.append(f"Verdict record {index} lacks question_id")
            continue
        if question_id in result:
            issues.append(f"Duplicate verdict for {question_id}; the first record was retained")
            continue
        if verdict not in VERDICTS:
            issues.append(f"Verdict for {question_id} has invalid state {verdict!r}")
            verdict = "CANNOT_ASSESS"
        normalized = dict(record)
        normalized["verdict"] = verdict
        result[question_id] = normalized
    return result, issues


def _get_verdict(
    question_record: Mapping[str, Any],
    verdict_by_id: Mapping[str, dict[str, Any]],
    issues: list[str],
) -> dict[str, Any]:
    """Return a verdict, treating omitted selected questions as unassessed."""

    question = question_record["question"]
    question_id = question["id"]
    verdict = dict(verdict_by_id.get(question_id, {}))
    if not verdict:
        verdict = {
            "question_id": question_id,
            "verdict": "CANNOT_ASSESS",
            "confidence": 0.0,
            "evidence": [],
            "note": "No verdict supplied.",
        }
        issues.append(f"Missing verdict for selected question {question_id}; treated as CANNOT_ASSESS")
    state = verdict["verdict"]
    evidence = verdict.get("evidence") or []
    policy = question.get("evidence_policy", {})
    required_refs = int(policy.get("minimum_references", 0)) if policy.get("required") else 0
    if state in {"YES", "NO"} and len(evidence) < required_refs:
        issues.append(
            f"Verdict {state} for {question_id} has {len(evidence)} evidence references; {required_refs} required"
        )
    if state == "NOT_APPLICABLE" and not str(verdict.get("note", "")).strip():
        issues.append(f"NOT_APPLICABLE verdict for {question_id} lacks an activation-condition reason")
    try:
        confidence = float(verdict.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
        issues.append(f"Verdict for {question_id} has nonnumeric confidence")
    if not 0.0 <= confidence <= 1.0:
        issues.append(f"Verdict for {question_id} has confidence outside 0..1")
        confidence = min(1.0, max(0.0, confidence))
    verdict["confidence"] = confidence
    return verdict


def _enforce_subjective_ladders(
    compiled: Mapping[str, Any],
    effective_states: MutableMapping[str, str],
    issues: list[str],
) -> None:
    """Fail-close inconsistent cumulative holistic threshold verdicts."""

    ladders: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for record in compiled["domain_questions"]:
        question = record["question"]
        if question.get("question_type") != "subjective_threshold":
            continue
        module_id = record["module_id"]
        qid = question["id"]
        suffix = qid.rsplit("threshold_", 1)[-1]
        try:
            order = int(suffix.split("_", 1)[0])
        except (ValueError, IndexError):
            order = len(ladders[module_id]) + 1
        ladders[module_id].append((qid, order))
    for module_id, values in ladders.items():
        prior_passed = True
        for qid, _ in sorted(values, key=lambda item: item[1]):
            state = effective_states[qid]
            if state == "YES" and not prior_passed:
                effective_states[qid] = "NO"
                issues.append(
                    f"Subjective ladder {module_id} had {qid}=YES after a lower threshold failed or was unassessed; normalized to NO"
                )
                state = "NO"
            prior_passed = prior_passed and state == "YES"


def _triplet(observed: float | None, lower: float | None, upper: float | None) -> dict[str, float | None]:
    """Round and return an observed/lower/upper score triplet."""

    def rounded(value: float | None) -> float | None:
        return None if value is None else round(float(value), 4)

    return {"observed": rounded(observed), "lower": rounded(lower), "upper": rounded(upper)}


def score_bundle(
    modules: Sequence[dict[str, Any]],
    bundle: dict[str, Any],
    verdicts: Sequence[dict[str, Any]],
    *,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Score verdicts under one bundle using HBQ-RS uncertainty rules."""

    compiled = compile_bundle(modules, bundle)
    verdict_by_id, issues = _verdict_index(verdicts)
    selected_ids = {
        record["question"]["id"]
        for record in compiled["domain_questions"] + compiled["hard_gates"] + compiled["supplemental_questions"]
    }
    selected_ids.update(
        record["question"]["id"]
        for group_record in compiled["penalty_groups"]
        for record in group_record["questions"]
    )
    for extra in sorted(set(verdict_by_id) - selected_ids):
        issues.append(f"Verdict supplied for question not selected by bundle: {extra}")

    all_selected_records: dict[str, dict[str, Any]] = {}
    for record in compiled["domain_questions"] + compiled["hard_gates"] + compiled["supplemental_questions"]:
        all_selected_records.setdefault(record["question"]["id"], record)
    for penalty_group in compiled["penalty_groups"]:
        for record in penalty_group["questions"]:
            all_selected_records.setdefault(record["question"]["id"], record)

    normalized_verdicts: dict[str, dict[str, Any]] = {}
    effective_states: dict[str, str] = {}
    for qid, record in all_selected_records.items():
        verdict = _get_verdict(record, verdict_by_id, issues)
        normalized_verdicts[qid] = verdict
        effective_states[qid] = verdict["verdict"]
    _enforce_subjective_ladders(compiled, effective_states, issues)

    # Hard gates are eligibility, never quality points.
    hard_gate_results: list[dict[str, Any]] = []
    hard_no = False
    hard_unknown = False
    for record in compiled["hard_gates"]:
        qid = record["question"]["id"]
        state = effective_states[qid]
        hard_gate_results.append(
            {
                "question_id": qid,
                "verdict": state,
                "module_id": record["module_id"],
                "evidence": normalized_verdicts[qid].get("evidence", []),
            }
        )
        if state == "NO":
            hard_no = True
        elif state == "CANNOT_ASSESS":
            hard_unknown = True
    hard_gate_status = "INVALID" if hard_no else "UNRESOLVED" if hard_unknown else "VALID"

    # Domain scoring.
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    domain_meta: dict[str, dict[str, Any]] = {}
    for domain in bundle.get("domains", []):
        domain_meta[str(domain["domain_id"])] = domain
    for record in compiled["domain_questions"]:
        by_domain[str(record["domain_id"])].append(record)

    domain_reports: list[dict[str, Any]] = []
    active_points = 0.0
    observed_points_base = 0.0
    observed_point_capacity = 0.0
    lower_points_base = 0.0
    upper_points_base = 0.0
    weighted_assessed_points = 0.0
    confidence_numerator = 0.0
    confidence_denominator = 0.0

    for domain_id, meta in domain_meta.items():
        points = float(meta["points"])
        passed = failed = unassessed = 0.0
        assessed_confidence = 0.0
        assessed_confidence_weight = 0.0
        question_reports: list[dict[str, Any]] = []
        for record in by_domain.get(domain_id, []):
            qid = record["question"]["id"]
            state = effective_states[qid]
            weight = float(record["effective_weight"])
            verdict = normalized_verdicts[qid]
            question_reports.append(
                {
                    "question_id": qid,
                    "module_id": record["module_id"],
                    "verdict": state,
                    "weight": round(weight, 6),
                    "confidence": verdict.get("confidence", 0.0),
                    "evidence": verdict.get("evidence", []),
                }
            )
            if state == "NOT_APPLICABLE":
                continue
            if state == "CANNOT_ASSESS":
                unassessed += weight
            elif state == "YES":
                passed += weight
                assessed_confidence += weight * float(verdict.get("confidence", 0.0))
                assessed_confidence_weight += weight
            elif state == "NO":
                failed += weight
                assessed_confidence += weight * float(verdict.get("confidence", 0.0))
                assessed_confidence_weight += weight
        assessed = passed + failed
        applicable = assessed + unassessed
        if applicable > 0:
            active_points += points
            lower = points * passed / applicable
            upper = points * (passed + unassessed) / applicable
            lower_points_base += lower
            upper_points_base += upper
            coverage = assessed / applicable
            weighted_assessed_points += points * coverage
        else:
            lower = upper = None
            coverage = None
        if assessed > 0:
            observed = points * passed / assessed
            observed_points_base += observed
            observed_point_capacity += points
        else:
            observed = None
        if assessed_confidence_weight > 0:
            domain_confidence = assessed_confidence / assessed_confidence_weight
            confidence_numerator += points * domain_confidence
            confidence_denominator += points
        else:
            domain_confidence = None
        domain_reports.append(
            {
                "domain_id": domain_id,
                "title": meta.get("title", domain_id),
                "nominal_points": points,
                "active": applicable > 0,
                "weights": {
                    "passed": round(passed, 6),
                    "failed": round(failed, 6),
                    "unassessed": round(unassessed, 6),
                    "applicable": round(applicable, 6),
                },
                "coverage": None if coverage is None else round(coverage, 4),
                "confidence": None if domain_confidence is None else round(domain_confidence, 4),
                "score": _triplet(observed, lower, upper),
                "questions": question_reports,
            }
        )

    # If an entire conditional domain is N/A, its points are proportionally
    # reallocated among active domains. This is essential for, e.g., a
    # single-stanza haiku under a bundle that also contains sequence criteria.
    normalization_factor = 100.0 / active_points if active_points > 0 else 0.0
    observed_factor = 100.0 / observed_point_capacity if observed_point_capacity > 0 else 0.0
    base_observed = observed_points_base * observed_factor if observed_point_capacity > 0 else None
    base_lower = lower_points_base * normalization_factor if active_points > 0 else None
    base_upper = upper_points_base * normalization_factor if active_points > 0 else None
    weighted_coverage = weighted_assessed_points / active_points if active_points > 0 else 0.0
    overall_confidence = confidence_numerator / confidence_denominator if confidence_denominator > 0 else 0.0

    penalty_reports: list[dict[str, Any]] = []
    penalty_observed_total = 0.0
    penalty_lower_total = 0.0
    penalty_upper_total = 0.0
    for group_record in compiled["penalty_groups"]:
        cap = float(group_record["cap_points"])
        passed = failed = unassessed = 0.0
        question_reports: list[dict[str, Any]] = []
        for record in group_record["questions"]:
            qid = record["question"]["id"]
            state = effective_states[qid]
            weight = float(record["effective_weight"])
            verdict = normalized_verdicts[qid]
            question_reports.append(
                {
                    "question_id": qid,
                    "verdict": state,
                    "weight": round(weight, 6),
                    "confidence": verdict.get("confidence", 0.0),
                    "evidence": verdict.get("evidence", []),
                }
            )
            if state == "NOT_APPLICABLE":
                continue
            if state == "CANNOT_ASSESS":
                unassessed += weight
            elif state == "YES":
                passed += weight
            elif state == "NO":
                failed += weight
        assessed = passed + failed
        applicable = assessed + unassessed
        observed = cap * failed / assessed if assessed > 0 else 0.0
        lower = cap * failed / applicable if applicable > 0 else 0.0
        upper = cap * (failed + unassessed) / applicable if applicable > 0 else 0.0
        coverage = assessed / applicable if applicable > 0 else 1.0
        penalty_observed_total += observed
        penalty_lower_total += lower
        penalty_upper_total += upper
        penalty_reports.append(
            {
                "module_id": group_record["module_id"],
                "title": group_record["title"],
                "cap_points": cap,
                "coverage": round(coverage, 4),
                "weights": {
                    "passed": round(passed, 6),
                    "failed": round(failed, 6),
                    "unassessed": round(unassessed, 6),
                    "applicable": round(applicable, 6),
                },
                "deduction": _triplet(observed, lower, upper),
                "questions": question_reports,
            }
        )

    final_observed = None if base_observed is None else max(0.0, base_observed - penalty_observed_total)
    final_lower = None if base_lower is None else max(0.0, base_lower - penalty_upper_total)
    final_upper = None if base_upper is None else max(0.0, base_upper - penalty_lower_total)
    minimum_coverage = float(bundle.get("coverage_policy", {}).get("minimum_weighted_coverage", 0.0))
    if hard_gate_status == "INVALID":
        status = "INELIGIBLE"
    elif hard_gate_status == "UNRESOLVED":
        status = "UNRESOLVED"
    elif weighted_coverage < minimum_coverage:
        status = str(bundle.get("coverage_policy", {}).get("below_threshold_status", "PROVISIONAL"))
    else:
        status = "SCORED"

    # Supplemental questions are reported but not forced into coverage or score.
    supplemental_results: list[dict[str, Any]] = []
    for record in compiled["supplemental_questions"]:
        qid = record["question"]["id"]
        supplemental_results.append(
            {
                "question_id": qid,
                "module_id": record["module_id"],
                "verdict": effective_states[qid],
                "confidence": normalized_verdicts[qid].get("confidence", 0.0),
                "evidence": normalized_verdicts[qid].get("evidence", []),
            }
        )

    artifact = artifact_id
    if artifact is None:
        artifact = next((str(v.get("artifact_id")) for v in verdicts if v.get("artifact_id")), "artifact")

    return {
        "$schema": "../schema/hbq_score_report.schema.json",
        "standard": bundle.get("standard"),
        "bundle_id": bundle.get("bundle_id"),
        "bundle_version": bundle.get("version"),
        "artifact_id": artifact,
        "status": status,
        "hard_gate_status": hard_gate_status,
        "hard_gates": hard_gate_results,
        "coverage": round(weighted_coverage, 4),
        "minimum_coverage": minimum_coverage,
        "confidence": round(overall_confidence, 4),
        "active_nominal_points": round(active_points, 4),
        "inactive_points_reallocated": round(max(0.0, 100.0 - active_points), 4),
        "base_score": _triplet(base_observed, base_lower, base_upper),
        "penalty_deduction": _triplet(
            penalty_observed_total,
            penalty_lower_total,
            penalty_upper_total,
        ),
        "final_score": _triplet(final_observed, final_lower, final_upper),
        "domains": domain_reports,
        "penalties": penalty_reports,
        "supplemental": supplemental_results,
        "issues": sorted(set(issues)),
    }


def resolve_bundle(bundles: Sequence[dict[str, Any]], bundle_id: str) -> dict[str, Any]:
    """Return a named bundle or raise with a useful message."""

    index = index_bundles(bundles)
    if bundle_id not in index:
        nearby = ", ".join(sorted(index)[:20])
        raise HBQError(f"Unknown bundle {bundle_id!r}. Available examples: {nearby}")
    return index[bundle_id]
