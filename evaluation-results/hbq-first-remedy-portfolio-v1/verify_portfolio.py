from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
EXPECTED_PACKAGES = (("R0", 2, 0), ("L1", 1, 72), ("L2", 3, 216), ("P1", 11, 132), ("S1", 35, 420), ("S2", 25, 300))
EXPECTED_STATUS = "frozen_public_coverage_manifest_no_execution_authorized"
EXPECTED_CWR_PARENT = "910c0c48d11de15be6f20626140ac8fd2373d2b7"
CANONICAL_MANIFEST_SHA256 = "eebe2ac7a7b592459e5b084d8f6806a56ccd7a8c077e6508b34e0a0818111d32"
CANONICAL_PROJECTION_SHA256 = "32f0089449bca0f5482bbbda7d4926335d4cd895457523cdae247f6209a67256"
EXPECTED_COVERAGE = {
    "findings_exact": 77,
    "ordered_finding_ids_sha256": "6f0a92b49bdb1a34d6216f42da26087247ce0962782a809b9a414fae5ababda3",
    "unique_leaves_exact": 80,
    "leaf_memberships_exact": 81,
    "only_repeated_leaf": "penalty.purple_prose.fatigue",
    "only_repeated_leaf_memberships_exact": 2,
}
EXPECTED_BINDINGS = {
    "source_audit": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/leaf-audit.jsonl", "sha256": "dada4b53635ac4991b1fa59426c5100753026a5493b46022037b1d715fcff818"},
    "findings": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/findings.jsonl", "sha256": "06c08ef035a09288fa6710db51786ec1a73b71116ac9b23e4c2a09ece8fa14a1"},
    "triage": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/sol-triage.jsonl", "sha256": "f5427aead55b3a17fbe24917d56dba7a50efd8c4a6ce55602c6280b3ddee67e9"},
    "triage_summary": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/sol-triage-summary.json", "sha256": "c482a2d94d51d95bee62a2d2176c623f0b9064123a97d3ae2028c52178f80d19"},
    "r0_settled_figurative_result": {
        "path": "evaluation-results/hbq-figurative-scope-treatment-v1-execution-v1/public-result.json",
        "sha256": "1527cbf9299d9ca83c328101cd15e146e5f8e841c495d1b192a33f51e759534e",
        "decision": "NO_GO",
        "fatigue": {"baseline": [12, 12], "scope_rendering_only": [12, 12]},
        "relevant_calls_exact": 24,
        "interpretation": "development-level NO_CHANGE/watch only; it authorizes no overall treatment or rubric promotion",
    },
}
LEXICAL_CALLS_PER_FINDING = 12 * 2 * 3
FOUR_STATE_CALLS_PER_FINDING = 4 * 3


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_projection_sha256(manifest: dict) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_manifest(manifest: dict, repository_root: Path = REPOSITORY_ROOT) -> dict:
    require(manifest["format"] == "hbq-first-remedy-portfolio-v1", "Unexpected format")
    require(manifest["status"] == EXPECTED_STATUS, "Portfolio status drifted")
    require(manifest["cwr_parent"] == EXPECTED_CWR_PARENT, "CWR parent projection drifted")
    require(canonical_projection_sha256(manifest) == CANONICAL_PROJECTION_SHA256, "Canonical manifest projection drifted")
    require(manifest["coverage"] == EXPECTED_COVERAGE, "Coverage projection drifted")
    require(manifest["bindings"] == EXPECTED_BINDINGS, "Binding projection drifted")
    execution = manifest["execution"]
    require(execution == {
        "initial_calls_exact": 1140,
        "provider_calls_authorized_by_this_manifest": False,
        "one_leaf_per_request": True,
        "batch_size_exact": 1,
        "conditional_successors": "separate_frozen_affected_only_packages",
    }, "Execution contract drifted")

    packages = manifest["packages"]
    observed = tuple((item["package_id"], item["finding_count_exact"], item["initial_calls_exact"]) for item in packages)
    ids = [finding_id for package in packages for finding_id in package["finding_ids"]]
    require(all(len(item["finding_ids"]) == item["finding_count_exact"] for item in packages), "Package finding count drifted")
    for package in packages:
        if package["package_id"] == "R0":
            expected_calls = 0
        elif package["package_id"] in {"L1", "L2"}:
            expected_calls = package["finding_count_exact"] * LEXICAL_CALLS_PER_FINDING
        else:
            expected_calls = package["finding_count_exact"] * FOUR_STATE_CALLS_PER_FINDING
        require(package["initial_calls_exact"] == expected_calls, "Derived package call geometry drifted")
    require(observed == EXPECTED_PACKAGES, "Package partition or call geometry drifted")
    require(len(ids) == 77 and len(set(ids)) == 77, "Finding partition must contain 77 disjoint IDs")
    require(all(len(item) == 64 and all(character in "0123456789abcdef" for character in item) for item in ids), "Finding ID format drifted")
    ordered_id_hash = hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()
    require(ordered_id_hash == manifest["coverage"]["ordered_finding_ids_sha256"], "Exact finding-ID membership or order drifted")
    require(sum(item["initial_calls_exact"] for item in packages) == execution["initial_calls_exact"], "Initial call total drifted")

    for binding in EXPECTED_BINDINGS.values():
        path = repository_root / binding["path"]
        require(path.is_file(), f"Missing bound file: {binding['path']}")
        require(sha256_file(path) == binding["sha256"], f"Hash binding drifted: {binding['path']}")

    status = subprocess.run(["git", "-C", str(repository_root), "merge-base", "--is-ancestor", EXPECTED_CWR_PARENT, "HEAD"], capture_output=True, text=True)
    require(status.returncode == 0, "Pinned CWR parent is not an ancestor of HEAD")

    triage_summary = load_json(repository_root / manifest["bindings"]["triage_summary"]["path"])
    require(triage_summary["status_counts"] == {"false_positive": 396, "first_remedy_experiment": 77, "intentional_specialization": 276, "watch": 59}, "Triage status counts drifted")
    require(triage_summary["decision_counts"]["needs_empirical_test"] == 136, "Public triage collapse count drifted")
    require([item["sha256"] for item in triage_summary["source_part_commitments"]] == manifest["public_provenance"]["source_part_commitments_sha256"], "Source-part commitments drifted")

    finding_rows = {row["finding_id"]: row for row in load_jsonl(repository_root / manifest["bindings"]["findings"]["path"])}
    triage_rows = {row["finding_id"]: row for row in load_jsonl(repository_root / manifest["bindings"]["triage"]["path"])}
    require(set(ids).issubset(finding_rows), "Selected finding is absent from bound findings")
    require(all(triage_rows.get(finding_id, {}).get("decision") == "needs_empirical_test" for finding_id in ids), "Selected finding lacks public needs_empirical_test triage")

    memberships = [leaf for finding_id in ids for leaf in finding_rows[finding_id]["subjects"]]
    counts = Counter(memberships)
    coverage = EXPECTED_COVERAGE
    require(len(memberships) == coverage["leaf_memberships_exact"], "Leaf membership count drifted")
    require(len(counts) == coverage["unique_leaves_exact"], "Unique leaf count drifted")
    repeated = {leaf: count for leaf, count in counts.items() if count > 1}
    require(repeated == {coverage["only_repeated_leaf"]: coverage["only_repeated_leaf_memberships_exact"]}, "Repeated-leaf rule drifted")

    r0 = packages[0]
    r0_result = load_json(repository_root / manifest["bindings"]["r0_settled_figurative_result"]["path"])
    r0_binding = manifest["bindings"]["r0_settled_figurative_result"]
    require(r0["initial_calls_exact"] == 0 and r0_result["decision"] == r0_binding["decision"] == "NO_GO", "R0 settlement drifted")
    actual_fatigue = {arm: r0_result["arms"][arm]["fatigue"] for arm in r0_binding["fatigue"]}
    require(actual_fatigue == r0_binding["fatigue"], "R0 fatigue evidence drifted")
    require(sum(actual_fatigue[arm][1] for arm in actual_fatigue) == r0_binding["relevant_calls_exact"], "R0 relevant-call count drifted")
    require("no overall treatment or rubric promotion" in r0_binding["interpretation"], "R0 promotion limit drifted")

    return {"status": EXPECTED_STATUS, "findings": len(ids), "unique_leaves": len(counts), "initial_calls": execution["initial_calls_exact"], "provider_calls": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        parser.error("--check is required; this verifier has no execution mode")
    manifest_path = PACKAGE_ROOT / "manifest.json"
    require(sha256_file(manifest_path) == CANONICAL_MANIFEST_SHA256, "Canonical manifest bytes drifted")
    report = verify_manifest(load_json(manifest_path))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
