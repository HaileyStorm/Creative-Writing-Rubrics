#!/usr/bin/env python3
"""Generate and verify the frozen HBQ-RS full-leaf structural audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
AUDIT_ID = "hbq-full-leaf-structural-audit-v1"
ROW_FORMAT = "hbq-full-leaf-structural-audit-row-v1"
FINDING_FORMAT = "hbq-full-leaf-structural-audit-finding-v1"
OUTPUTS = ("leaf-audit.jsonl", "findings.jsonl", "summary.json", "manifest.json")
ABSOLUTE_PRIVATE_PATH = re.compile(r"(?i)(?:[a-z]:[\\/](?:users|home)[\\/]|/(?:users|home)/)")
SENTINELS = {
    "core.freshness_and_non_genericness.no_default_metaphors": {
        "module_id": "core.freshness_and_non_genericness",
        "owner_domain": "freshness",
        "role": "stockness_owner",
    },
    "penalty.purple_prose.proportion": {
        "module_id": "penalty.purple_prose",
        "owner_domain": "penalty.purple_prose",
        "role": "density_owner",
    },
    "penalty.purple_prose.fatigue": {
        "module_id": "penalty.purple_prose",
        "owner_domain": "penalty.purple_prose",
        "role": "density_owner",
    },
}
NEGATIVE_SURFACE = re.compile(r"\b(?:avoid|without|no|not|never|lack|lacks|free of|rather than)\b", re.I)
WHOLE_SCOPE = re.compile(r"\b(?:whole|entire|opening|ending|manuscript|global)\b", re.I)
CUMULATIVE_SCOPE = re.compile(r"\b(?:across|cumulative|throughout|distribution|repeated|recurrence|vary|all)\b", re.I)
CROSS_UNIT_SCOPE = re.compile(r"\b(?:between|transition|neighboring|prior|surrounding|sequence|arc|payoff)\b", re.I)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_input_bytes(value: bytes) -> bytes:
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Frozen input is not UTF-8 text") from exc
    return value.replace(b"\r\n", b"\n")


def canonical_input_record(path: Path) -> dict[str, Any]:
    payload = canonical_input_bytes(path.read_bytes())
    return {"bytes": len(payload), "sha256": sha256_bytes(payload)}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes(path: Path, value: bytes, *, check: bool) -> None:
    if check:
        if not path.exists() or path.read_bytes() != value:
            raise ValueError(f"Generated output drift: {path.name}")
        return
    path.write_bytes(value)


def source_tree_digest(directory: Path) -> str:
    rows = []
    for path in sorted(directory.glob("*.yaml"), key=lambda item: item.name):
        record = canonical_input_record(path)
        rows.append({"path": path.relative_to(ROOT).as_posix(), **record})
    return sha256_bytes(canonical_json(rows))


def input_records(contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative in ("registry/all_modules.json", "bundles/all_bundles.json", "registry/source_inventory_map.json"):
        path = ROOT / relative
        result[relative] = {"path": relative, **canonical_input_record(path)}
    aggregate = source_tree_digest(ROOT / "registry/modules")
    result["registry/modules.aggregate"] = {
        "path": "registry/modules",
        "bytes": sum(canonical_input_record(path)["bytes"] for path in (ROOT / "registry/modules").glob("*.yaml")),
        "sha256": aggregate,
    }
    expected = contract["frozen_input_hashes"]
    for name, record in result.items():
        if expected.get(name) != record["sha256"]:
            raise ValueError(f"Frozen input hash mismatch for {name}")
    binding = contract["parent_binding"]
    revision = str(contract["parent_revision"])
    for relative, expected_blob in binding["git_blobs"].items():
        actual_blob = subprocess.check_output(["git", "rev-parse", f"{revision}:{relative}"], cwd=ROOT, text=True).strip()
        if actual_blob != expected_blob:
            raise ValueError(f"Pinned parent Git blob mismatch for {relative}")
    for relative in ("registry/all_modules.json", "bundles/all_bundles.json", "registry/source_inventory_map.json"):
        parent_payload = subprocess.check_output(["git", "show", f"{revision}:{relative}"], cwd=ROOT)
        if canonical_input_bytes(parent_payload) != canonical_input_bytes((ROOT / relative).read_bytes()):
            raise ValueError(f"Current input diverges from pinned parent content: {relative}")
    return result


def walk_tree(nodes: Iterable[Mapping[str, Any]], groups: tuple[str, ...] = ()) -> Iterable[tuple[Mapping[str, Any], tuple[str, ...]]]:
    for node in nodes:
        if node.get("type") == "question":
            yield node, groups
        elif node.get("type") == "group":
            yield from walk_tree(node.get("children", []), groups + (str(node["id"]),))
        else:
            raise ValueError(f"Unknown tree node type: {node.get('type')!r}")


def module_source_paths() -> dict[str, Path]:
    result: dict[str, Path] = {}
    expression = re.compile(r"^module_id:\s*(\S+)\s*$", re.M)
    for path in sorted((ROOT / "registry/modules").glob("*.yaml"), key=lambda item: item.name):
        match = expression.search(path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"Module source has no module_id: {path.name}")
        module_id = match.group(1)
        if module_id in result:
            raise ValueError(f"Duplicate module source: {module_id}")
        result[module_id] = path
    return result


def normalized_tokens(text: str, boilerplate: set[str]) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).lower()
    folded = "".join(character if character.isalnum() else " " for character in folded)
    return [token for token in folded.split() if token not in boilerplate]


def dice(left: set[str], right: set[str]) -> float:
    return (2.0 * len(left & right) / (len(left) + len(right))) if left or right else 0.0


def score_pair(left_tokens: set[str], right_tokens: set[str]) -> dict[str, Any]:
    shared = sorted(left_tokens & right_tokens)
    union = left_tokens | right_tokens
    containment = len(shared) / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
    return {
        "token_jaccard": round(len(shared) / len(union), 12) if union else 0.0,
        "shared_content_tokens": shared,
        "shorter_containment": round(containment, 12),
        "fourgram_dice": None,
    }


def scope_details(question: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    text = str(question["text"])
    rules = []
    if WHOLE_SCOPE.search(text):
        signal = "whole"
        rules.append("whole_scope_terms")
    elif CUMULATIVE_SCOPE.search(text):
        signal = "cumulative"
        rules.append("cumulative_scope_terms")
    elif CROSS_UNIT_SCOPE.search(text):
        signal = "cross_unit"
        rules.append("cross_unit_scope_terms")
    else:
        signal = "local"
        rules.append("no_nonlocal_scope_terms")
    current_artifact_zero_neighbors = evidence.get("current_artifact") is True and evidence.get("neighboring_units", 0) == 0
    flags = ["current_artifact_zero_neighbors"] if current_artifact_zero_neighbors else []
    return {
        "signal": signal,
        "specificity": "explicit" if signal != "local" else "local_or_unspecified",
        "rules": rules,
        "flags": flags,
    }


def first_remedy(selection: str, eligible: list[str]) -> dict[str, Any]:
    if selection not in {"none", "eligible_static_signal", "bound_empirical_signal"}:
        raise ValueError("Unknown first-remedy selection")
    return {"selection": selection, "selected": None, "eligible": eligible}


def candidate_finding(kind: str, subjects: list[str], rule: Mapping[str, Any], raw_scores: Mapping[str, Any], routing: Mapping[str, Any], remedy: Mapping[str, Any], interpretation: str) -> dict[str, Any]:
    canonical_subjects = sorted(subjects)
    identity = {"subjects": canonical_subjects, "rule": rule}
    return {
        "finding_id": sha256_bytes(canonical_json(identity)),
        "format": FINDING_FORMAT,
        "audit": AUDIT_ID,
        "kind": kind,
        "subjects": canonical_subjects,
        "rule": dict(rule),
        "raw_scores": dict(raw_scores),
        "routing_evidence": dict(routing),
        "first_remedy": dict(remedy),
        "interpretation": interpretation,
    }


def scan_findings(rows: list[dict[str, Any]], contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rules = contract["lexical_pair_rules"]
    boilerplate = set(rules["boilerplate_tokens"])
    jaccard_floor = float(rules["token_jaccard_minimum"])
    containment_floor = float(rules["shorter_containment_minimum"])
    shared_minimum = int(rules["shared_content_tokens_minimum"])
    delta = float(contract["threshold_sensitivity"]["delta"])
    findings: list[dict[str, Any]] = []
    sensitivity: dict[str, int] = {"jaccard_minus": 0, "jaccard_base": 0, "jaccard_plus": 0, "containment_minus": 0, "containment_base": 0, "containment_plus": 0}
    token_sets = [set(normalized_tokens(str(row["question"]["text"]), boilerplate)) for row in rows]
    inverted: dict[str, list[int]] = defaultdict(list)
    for index, tokens in enumerate(token_sets):
        for token in tokens:
            inverted[token].append(index)
    shared_counts: Counter[tuple[int, int]] = Counter()
    for indexes in inverted.values():
        for pair in combinations(indexes, 2):
            shared_counts[pair] += 1
    qualified_pairs = sorted(pair for pair, count in shared_counts.items() if count >= shared_minimum)
    for left_index, right_index in qualified_pairs:
        left, right = rows[left_index], rows[right_index]
        scores = score_pair(token_sets[left_index], token_sets[right_index])
        shared_count = len(scores["shared_content_tokens"])
        for label, threshold in (("jaccard_minus", jaccard_floor - delta), ("jaccard_base", jaccard_floor), ("jaccard_plus", jaccard_floor + delta)):
            if shared_count >= shared_minimum and scores["token_jaccard"] >= threshold:
                sensitivity[label] += 1
        for label, threshold in (("containment_minus", containment_floor - delta), ("containment_base", containment_floor), ("containment_plus", containment_floor + delta)):
            if shared_count >= shared_minimum and scores["shorter_containment"] >= threshold:
                sensitivity[label] += 1
        jaccard_pass = shared_count >= shared_minimum and scores["token_jaccard"] >= jaccard_floor
        containment_pass = shared_count >= shared_minimum and scores["shorter_containment"] >= containment_floor
        if not (jaccard_pass or containment_pass):
            continue
        routing = {
            "common_artifact_types": sorted(set(left["routing"]["artifact_types"]) & set(right["routing"]["artifact_types"])),
            "common_valid_scopes": sorted(set(left["routing"]["valid_scopes"]) & set(right["routing"]["valid_scopes"])),
            "common_selected_bundles": sorted(set(left["routing"]["selected_bundles"]) & set(right["routing"]["selected_bundles"])),
            "same_module": left["owner"]["module_id"] == right["owner"]["module_id"],
        }
        findings.append(candidate_finding(
            "lexical_overlap", [left["qid"], right["qid"]],
            {"matched": [name for name, passed in (("token_jaccard", jaccard_pass), ("shorter_containment", containment_pass)) if passed], "thresholds": {"token_jaccard_minimum": jaccard_floor, "shorter_containment_minimum": containment_floor, "shared_content_tokens_minimum": shared_minimum}},
            scores, routing, first_remedy("none", []),
            "Similarity is a complete-scan candidate signal only; it does not establish semantic duplication or authorize a remedy."
        ))
    for row in rows:
        scope = row["scope"]
        current_artifact_zero_neighbors = "current_artifact_zero_neighbors" in scope["flags"]
        if scope["signal"] in {"cross_unit", "cumulative", "whole"} and current_artifact_zero_neighbors:
            findings.append(candidate_finding(
                "scope_binding_review", [row["qid"]],
                {"scope_signal": scope["signal"], "evidence_flag": "current_artifact_zero_neighbors"},
                {"token_jaccard": None, "shared_content_tokens": [], "shorter_containment": None, "fourgram_dice": None},
                {"artifact_types": row["routing"]["artifact_types"], "valid_scopes": row["routing"]["valid_scopes"], "selected_bundles": row["routing"]["selected_bundles"]},
                first_remedy("eligible_static_signal", ["localized_vs_scope_conflict"]),
                "Neutral scope-binding review candidate only. The default evidence setting does not prove local-only evidence or a rubric defect; later review needs a declared scope and bound empirical evidence."
            ))
        negative_terms = sorted(set(match.group(0).lower() for match in NEGATIVE_SURFACE.finditer(row["question"]["text"])))
        if row["polarity"]["pass_answer"] == "YES" and negative_terms:
            findings.append(candidate_finding(
                "polarity_change", [row["qid"]],
                {"surface_construction": "negative_terms_with_positive_pass", "terms": negative_terms},
                {"token_jaccard": None, "shared_content_tokens": [], "shorter_containment": None, "fourgram_dice": None},
                {"artifact_types": row["routing"]["artifact_types"], "valid_scopes": row["routing"]["valid_scopes"], "selected_bundles": row["routing"]["selected_bundles"]},
                first_remedy("eligible_static_signal", ["polarity_change"]),
                "Surface polarity candidate only. The frozen canonical orientation remains positive YES; no wording change is selected."
            ))
    findings.sort(key=lambda value: (value["kind"], value["subjects"], value["finding_id"]))
    sensitivity["pair_scan_total"] = len(rows) * (len(rows) - 1) // 2
    sensitivity["pairs_with_minimum_shared_content_tokens"] = len(qualified_pairs)
    return findings, sensitivity


def construct_rows(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    modules = read_json(ROOT / "registry/all_modules.json")
    bundles = read_json(ROOT / "bundles/all_bundles.json")
    inventory = read_json(ROOT / "registry/source_inventory_map.json")
    expected = contract["expected_inventory"]
    if len(modules) != expected["module_count"] or len(bundles) != expected["bundle_count"]:
        raise ValueError("Frozen module or bundle count mismatch")
    source_paths = module_source_paths()
    inventory_by_module = {record["module_id"]: record for record in inventory}
    if len(inventory_by_module) != expected["source_inventory_module_count"] or sum(int(item["question_count"]) for item in inventory) != expected["source_inventory_leaf_count"]:
        raise ValueError("Frozen source-inventory count mismatch")
    selected_bundles: dict[str, list[str]] = defaultdict(list)
    for bundle in bundles:
        for module_id in bundle["module_ids"]:
            selected_bundles[module_id].append(bundle["bundle_id"])
    rows: list[dict[str, Any]] = []
    criterion_counts: Counter[str] = Counter()
    staging: list[tuple[Mapping[str, Any], Mapping[str, Any], tuple[str, ...]]] = []
    for module in modules:
        for leaf, groups in walk_tree(module["tree"]):
            criterion_counts[str(leaf["criterion_key"])] += 1
            staging.append((module, leaf, groups))
    for ordinal, (module, leaf, groups) in enumerate(sorted(staging, key=lambda value: str(value[1]["id"])), start=1):
        module_id = str(module["module_id"])
        source_path = source_paths.get(module_id)
        if source_path is None:
            raise ValueError(f"No source module path for {module_id}")
        policy = dict(leaf.get("evidence_policy") or {})
        default_scope = dict(module.get("default_evidence_scope") or {})
        source_entry = inventory_by_module.get(module_id)
        scope = scope_details(leaf, default_scope)
        evidence_flags = []
        if policy.get("required"):
            evidence_flags.append("evidence_required")
        if int(policy.get("minimum_references", 0)) >= 1:
            evidence_flags.append("minimum_reference_present")
        materiality_cues = sorted(set(match.group(0).lower() for match in re.finditer(r"\b(?:must|required|material|hard|critical)\b", str(leaf.get("text", "")), re.I)))
        row = {
            "format": ROW_FORMAT,
            "audit": AUDIT_ID,
            "ordinal": ordinal,
            "qid": str(leaf["id"]),
            "criterion_key": str(leaf["criterion_key"]),
            "owner": {"module_id": module_id, "version": module["version"], "path": source_path.relative_to(ROOT).as_posix(), "kind": module["kind"], "domains": list(module.get("owner_domains", []))},
            "provenance": {"module_sha256": canonical_input_record(source_path)["sha256"], "origin": module.get("origin"), "research_basis": list(module.get("research_basis", [])), "source_inventory_entry": source_entry},
            "routing": {"artifact_types": list(module.get("artifact_types", [])), "valid_scopes": list(module.get("valid_scopes", [])), "default_evidence_scope": default_scope, "selected_bundles": sorted(selected_bundles[module_id])},
            "question": {"text": leaf["text"], "type": leaf["question_type"], "weight": leaf["weight"], "groups": list(groups)},
            "ownership": {"criterion_key_equals_qid": leaf["criterion_key"] == leaf["id"], "criterion_key_unique": criterion_counts[str(leaf["criterion_key"])] == 1, "flags": []},
            "polarity": {"pass_answer": leaf["pass_answer"], "orientation": "positive_yes" if leaf["pass_answer"] == "YES" else "noncanonical", "surface_construction": "negative_surface" if NEGATIVE_SURFACE.search(str(leaf["text"])) else "affirmative_surface", "rules": ["pass_answer_must_be_yes", "surface_terms_are_candidate_only"]},
            "scope": scope,
            "evidence": {"required": bool(policy.get("required")), "minimum_references": int(policy.get("minimum_references", 0)), "reference_style": policy.get("reference_style"), "specificity": "minimum_reference_required" if int(policy.get("minimum_references", 0)) >= 1 else "not_declared", "flags": evidence_flags},
            "materiality": {"severity": leaf.get("severity"), "cues": materiality_cues, "specificity": "declared_material" if leaf.get("severity") == "material" else "other", "flags": ["material" if leaf.get("severity") == "material" else "nonmaterial"]},
            "finding_ids": [],
        }
        rows.append(row)
    if len(rows) != expected["leaf_count"]:
        raise ValueError("Frozen leaf count mismatch")
    if [row["qid"] for row in rows] != sorted(row["qid"] for row in rows):
        raise ValueError("Leaf rows are not sorted by qid")
    return rows


def jsonl_bytes(records: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(record) for record in records)


def _forbidden_field_present(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in forbidden or _forbidden_field_present(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(_forbidden_field_present(item, forbidden) for item in value)
    return False


def public_safe(paths: Iterable[Path], privacy: Mapping[str, Any] | None = None) -> None:
    policy = privacy or read_json(PACKAGE / "audit-contract.json")["privacy"]
    forbidden_substrings = tuple(str(value).lower() for value in policy["forbidden_substrings"])
    forbidden_regexes = tuple(re.compile(str(value)) for value in policy["forbidden_regexes"])
    forbidden_fields = {str(value).lower() for value in policy["forbidden_field_names"]}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if ABSOLUTE_PRIVATE_PATH.search(text):
            raise ValueError(f"Sensitive or private path marker in {path.name}")
        if any(marker in text.lower() for marker in forbidden_substrings):
            raise ValueError(f"Sensitive public-content marker in {path.name}")
        if any(expression.search(text) for expression in forbidden_regexes):
            raise ValueError(f"Sensitive credential pattern in {path.name}")
        if path.suffix == ".json":
            records = [read_json(path)]
        elif path.suffix == ".jsonl":
            records = [json.loads(line) for line in text.splitlines() if line]
        else:
            records = []
        if any(_forbidden_field_present(record, forbidden_fields) for record in records):
            raise ValueError(f"Forbidden private or provider field in {path.name}")


def validate_review_record(review: Mapping[str, Any], contract: Mapping[str, Any] | None = None) -> None:
    binding = contract or read_json(PACKAGE / "audit-contract.json")
    if review.get("audit") != AUDIT_ID:
        raise ValueError("Review record names the wrong audit")
    if review.get("audit_input_hashes") != binding["frozen_input_hashes"]:
        raise ValueError("Review record does not bind the exact frozen audit inputs")
    findings = {record["finding_id"] for record in (json.loads(line) for line in (PACKAGE / "findings.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    if review.get("finding_id") not in findings:
        raise ValueError("Review record does not reference a generated finding")
    evidence_hashes = review.get("evidence_hashes")
    if not isinstance(evidence_hashes, list):
        raise ValueError("Review evidence hashes must be a list")
    declared = {str(record["sha256"]) for record in binding["immutable_evidence_records"]}
    unresolved = set(evidence_hashes) - declared
    if unresolved:
        raise ValueError("Review evidence hashes do not resolve to declared immutable evidence records")
    if review.get("decision") == "propose_change" and not evidence_hashes:
        raise ValueError("A proposed change requires immutable evidence")


def build(contract: Mapping[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    inputs = input_records(contract)
    rows = construct_rows(contract)
    findings, sensitivity = scan_findings(rows, contract)
    finding_ids: dict[str, list[str]] = defaultdict(list)
    for finding in findings:
        for qid in finding["subjects"]:
            finding_ids[qid].append(finding["finding_id"])
    for row in rows:
        row["finding_ids"] = sorted(finding_ids[row["qid"]])
    sentinels = []
    by_qid = {row["qid"]: row for row in rows}
    for qid, expected in SENTINELS.items():
        row = by_qid.get(qid)
        if row is None or row["owner"]["module_id"] != expected["module_id"] or expected["owner_domain"] not in row["owner"]["domains"]:
            raise ValueError(f"Ownership sentinel failed for {qid}")
        sentinels.append({"qid": qid, **expected})
    summary = {
        "format": "hbq-full-leaf-structural-audit-summary-v1",
        "audit": AUDIT_ID,
        "status": contract["status"],
        "inputs": inputs,
        "counts": {"modules": len({row["owner"]["module_id"] for row in rows}), "leaves": len(rows), "findings": len(findings), "findings_by_kind": dict(sorted(Counter(finding["kind"] for finding in findings).items())), "source_inventory_modules": len({row["owner"]["module_id"] for row in rows if row["provenance"]["source_inventory_entry"] is not None}), "source_inventory_absent_modules": len({row["owner"]["module_id"] for row in rows if row["provenance"]["source_inventory_entry"] is None}), "source_inventory_leaves": sum(1 for row in rows if row["provenance"]["source_inventory_entry"] is not None), "source_inventory_absent_leaves": sum(1 for row in rows if row["provenance"]["source_inventory_entry"] is None)},
        "threshold_sensitivity": {"delta": contract["threshold_sensitivity"]["delta"], "pair_counts": sensitivity},
        "frozen_state": {"positive_yes_leaf_count": sum(row["polarity"]["pass_answer"] == "YES" for row in rows), "material_leaf_count": sum(row["materiality"]["severity"] == "material" for row in rows), "evidence_minimum_one_leaf_count": sum(row["evidence"]["minimum_references"] >= 1 for row in rows)},
        "sentinels": sentinels,
        "interpretation_limits": contract["interpretation_limits"],
    }
    outputs = {"leaf-audit.jsonl": jsonl_bytes(rows), "findings.jsonl": jsonl_bytes(findings), "summary.json": canonical_json(summary)}
    manifest_files = {name: {"bytes": len(value), "sha256": sha256_bytes(value)} for name, value in sorted(outputs.items())}
    for name in ("audit-contract.json", "leaf-audit.schema.json", "finding.schema.json", "sol-review.schema.json", "generate.py", "README.md"):
        path = PACKAGE / name
        manifest_files[name] = {"bytes": path.stat().st_size, "sha256": file_digest(path)}
    manifest = {"format": "hbq-full-leaf-structural-audit-manifest-v1", "audit": AUDIT_ID, "inputs": inputs, "files": dict(sorted(manifest_files.items()))}
    outputs["manifest.json"] = canonical_json(manifest)
    return outputs, summary


def run(check: bool) -> None:
    contract = read_json(PACKAGE / "audit-contract.json")
    outputs, _ = build(contract)
    for name, value in outputs.items():
        write_bytes(PACKAGE / name, value, check=check)
    public_safe((PACKAGE / name for name in ("README.md", *OUTPUTS)), contract["privacy"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail unless generated outputs match the frozen inputs")
    arguments = parser.parse_args()
    run(arguments.check)
