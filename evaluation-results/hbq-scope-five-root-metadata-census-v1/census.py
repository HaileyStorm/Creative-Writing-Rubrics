"""Finite historical membership proof; sealed outputs remain hash-only."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "scope_five_root_frozen_metadata_v1"
READER = REPO / "evaluation-results/hbq-matched-hanna-20261004/prepare.py"
READER_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
_reader = None
CONDITION = ("leaf_id", "provider", "model", "reasoning", "strict_ai", "batch_size",
             "batch_attempts", "prompt_sha256", "rubric_sha256")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return sha(canonical(value))


def project(raw, specification):
    global _reader
    if _reader is None:
        require(sha(READER.read_bytes()) == READER_SHA, "Pinned lexical reader differs")
        spec = importlib.util.spec_from_file_location("five_root_lexical", READER)
        _reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_reader)
    return _reader.project_json(raw, specification)


def fields(names):
    return {name: True for name in names}


def projection(family, role, raw):
    if role == "terminal_opaque_membership":
        require(family == "clean", "Unsupported terminal metadata projection")
        return project(raw, [{"opaque_slot_id": True}])
    require(role in ("manifest", "runtime"), "Sealed artifacts have no decoding projection")
    common = ("logical_sample_id", "repeat")
    if family == "clean":
        require(role == "manifest", "Clean runtime mapping is not part of this proof")
        slot = fields((*common, "opaque_slot_id"))
    else:
        slot = fields((*common, "slot_id", "leaf_id"))
    if family in ("sentinel", "treatment"):
        slot.update(fields(("artifact_id", "artifact_sha256")))
    if family == "treatment":
        slot.update(fields(("source_slot_id", "arm", "judge_id")))
    if family in ("semantic", "disjoint"):
        slot["fixture_commitment_sha256"] = True
    if family == "disjoint":
        slot["arm"] = True
    if family != "treatment" or role == "runtime":
        condition = fields(CONDITION)
        if family != "sentinel":
            if family != "treatment":
                condition["question_sha256"] = True
            if role == "runtime":
                condition.update(fields(("questions_sha256", "compiled_bundle_sha256")))
        slot["condition"] = condition
    if role == "runtime":
        slot["rendered_prompt_sha256"] = True
        return project(raw, {"slots": [slot], "rendered_prompt_aggregate_sha256": True})
    root = {"study_id": True, "slots": [slot]}
    if family == "treatment":
        root.update(fields(("planned_new_calls", "reused_accepted_calls")))
    else:
        root["planned_slots"] = True
    return project(raw, root)


def membership(item, manifest, companion):
    family, geometry = item["id"], item["geometry"]
    rows = manifest["slots"]
    identity = "opaque_slot_id" if family == "clean" else "slot_id"
    require(len(rows) == geometry["planned_slots"] and len({r[identity] for r in rows}) == len(rows),
            "Duplicate or changed frozen slot membership")
    require(len({r["logical_sample_id"] for r in rows}) == len(rows) and
            all(type(r["repeat"]) is int and r["repeat"] > 0 for r in rows),
            "Frozen logical identity or repeat membership differs")
    planned = manifest["planned_new_calls"] if family == "treatment" else manifest["planned_slots"]
    require(planned == len(rows), "Declared and projected plan geometry differs")
    reused = manifest.get("reused_accepted_calls", 0)
    require(reused == geometry.get("reused_predecessor_declarations", 0), "Predecessor reuse declaration differs")
    slots, joins = [], {}
    if family == "clean":
        require([r[identity] for r in rows] == [r[identity] for r in companion],
                "Clean terminal opaque membership differs")
        slots = [{"manifest": row, "terminal_opaque_metadata": terminal}
                 for row, terminal in zip(rows, companion)]
        joins = {"terminal_opaque_ids_equal_in_order": True,
                 "runtime_logical_identity_join": "unresolved_not_inspected"}
        runtime = None
    else:
        runtime = companion["slots"]
        require(len(runtime) == len(rows) and len({r[identity] for r in runtime}) == len(runtime) and
                len({r["logical_sample_id"] for r in runtime}) == len(runtime), "Runtime slot identities differ")
        matched = [key for key in rows[0] if key not in ("logical_sample_id", "condition")]
        require(all([r[key] for r in rows] == [r[key] for r in runtime] for key in matched),
                "Ordered slot/leaf/repeat/artifact membership differs")
        mismatches = sum(a["logical_sample_id"] != b["logical_sample_id"] for a, b in zip(rows, runtime))
        require(mismatches == geometry["logical_id_mismatches"], "Dual frozen logical ID commitments differ")
        joins = {"ordered_membership_fields": matched, "ordered_membership_equal": True,
                 "manifest_logical_ids_sha256": digest([r["logical_sample_id"] for r in rows]),
                 "runtime_logical_ids_sha256": digest([r["logical_sample_id"] for r in runtime]),
                 "logical_id_mismatches": mismatches,
                 "logical_identity_equivalence": "unresolved_both_source_lists_preserved"}
        slots = [{"manifest": a, "runtime": b} for a, b in zip(rows, runtime)]
    leaf = lambda row: row.get("leaf_id", row.get("condition", {}).get("leaf_id"))
    require(all(isinstance(leaf(row), str) and leaf(row) for row in rows), "Frozen leaf identity absent")
    leaves = dict(sorted(Counter(leaf(row) for row in rows).items()))
    repeats = dict(sorted(Counter(str(row["repeat"]) for row in rows).items()))
    prompts = Counter(row["rendered_prompt_sha256"] for row in runtime) if runtime is not None else None
    observed = {"manifest_metadata_positions": len(rows), "planned_new_positions": planned,
                "leaf_membership": leaves, "repeat_membership": repeats,
                "reused_predecessor_declarations_excluded_from_new_positions": reused,
                "exact_reuse_binding": "unresolved_not_inspected" if reused else "not_declared",
                "companion_metadata_positions": len(runtime) if runtime is not None else len(companion),
                "distinct_runtime_prompt_commitments": len(prompts) if prompts is not None else None,
                "runtime_prompt_commitment_groups_with_repeats": sum(v > 1 for v in prompts.values()) if prompts else None,
                "joins": joins, "current_admission_verified": False, "native_request_run_ancestry": "unresolved",
                "physical_contact_cardinality": None}
    return slots, observed


def checked(path, pin):
    raw = path.read_bytes()
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Pinned source bytes differ")
    return raw


def census(documents_root, recipe, recipe_raw):
    require(recipe["policy"] == POLICY and {r["id"] for r in recipe["families"]} ==
            {"sentinel", "treatment", "semantic", "disjoint", "clean"} and len(recipe["families"]) == 5,
            "Finite recipe membership differs")
    summaries, slots, artifacts = [], [], []
    documents_root = Path(documents_root).resolve()
    for family in recipe["families"]:
        root = (documents_root / family["root_relative_to_documents"]).resolve()
        require(root.is_relative_to(documents_root), "Source locator escapes Documents")
        projections = {}
        for source in family["source_files"]:
            path = (root / source["locator"]).resolve()
            require(path.is_relative_to(root), "Source file escapes retained root")
            raw = checked(path, source)
            artifacts.append({"family": family["id"], "kind": source["role"],
                              "locator": source["locator"], "bytes": len(raw), "sha256": sha(raw)})
            if source["role"] != "sealed_hash_only":
                projections[source["role"]] = projection(family["id"], source["role"], raw)
        public = family["public_artifact"]
        public_path = (REPO / public["locator"]).resolve()
        require(public_path.is_relative_to(REPO), "Public locator escapes repository")
        checked(public_path, public)
        artifacts.append({"family": family["id"], "kind": "public_hash_only", **public})
        companion = projections["terminal_opaque_membership" if family["id"] == "clean" else "runtime"]
        selected, observed = membership(family, projections["manifest"], companion)
        slots.extend({"family": family["id"], **row} for row in selected)
        summaries.append({"family": family["id"], "source_root_locator": family["root_relative_to_documents"],
                          "source_pins": family["source_files"], "public_artifact": public,
                          "observed_metadata": observed})
    report = {"schema_version": 1, "policy": POLICY, "families": summaries,
              "implementation_sha256": sha(Path(__file__).read_bytes()), "recipe_sha256": sha(recipe_raw),
              "lexical_projection_reader_sha256": READER_SHA,
              "artifact_ledger_sha256": digest(artifacts), "private_metadata_ledger_sha256": digest(slots),
              "provider_calls": 0, "new_votes": 0, "scoring_performed": False, "human_labels_opened": False,
              "scope": "exact_five_retained_root_memberships_no_ancestor_or_contact_sum",
              "remaining_gaps": ["Projected positions are frozen membership metadata, not observed verdict leaves or native admission.",
                                 "Manifest/runtime logical IDs differ; both commitments remain unresolved and preserved.",
                                 "Treatment's six predecessor reuse declarations add no new positions; their exact bindings remain unresolved.",
                                 "Clean terminal opaque membership supplies no native/run ancestry or runtime logical-ID proof.",
                                 "Historical retries, failed attempts, duplicate output representations and physical contact cardinality are not audited.",
                                 "Settlements/public aggregates remain hash-only; no outcomes, expected states, judgments or grounding evidence are decoded."]}
    return report, slots, artifacts


def destination(path, documents_root, recipe):
    output = Path(path).resolve()
    require(not output.exists(), "Output must be a fresh immutable descendant")
    roots = [REPO, *(Path(documents_root).resolve() / f["root_relative_to_documents"] for f in recipe["families"])]
    require(all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output)
                for root in roots), "Output overlaps checkout or retained inputs")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--documents-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    recipe_raw = (HERE / "recipe.json").read_bytes()
    recipe = json.loads(recipe_raw)
    output = destination(args.output_root, args.documents_root, recipe)
    report, slots, artifacts = census(args.documents_root, recipe, recipe_raw)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in {"report.json": canonical(report), "private-metadata.json": canonical(slots),
                          "artifact-ledger.json": canonical(artifacts), "recipe.json": recipe_raw,
                          "census.py": Path(__file__).read_bytes(), "lexical-reader.py": READER.read_bytes()}.items():
            with (output / name).open("xb") as stream:
                stream.write(raw)
    print(json.dumps({"report_sha256": digest(report), "recipe_sha256": sha(recipe_raw),
                      "implementation_sha256": report["implementation_sha256"],
                      "artifact_ledger_sha256": report["artifact_ledger_sha256"],
                      "private_metadata_ledger_sha256": report["private_metadata_ledger_sha256"],
                      "families": [{"family": row["family"], "observed_metadata": row["observed_metadata"]}
                                   for row in report["families"]],
                      "provider_calls": 0, "new_votes": 0, "human_labels_opened": False,
                      "output_written": not args.dry_run}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
