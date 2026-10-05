"""Finite provider-free poetry architecture historical metadata census."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
HELPERS = {
    "common": (HERE.parent / "hbq-evidence-census-pass-c-v1/census.py",
               "42415af5418ae32303bfa7933712b2ad398c0ed66df32a7553a9e3d55f5de49b"),
    "selective": (HERE.parent / "hbq-matched-hanna-20261004/prepare.py",
                  "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"),
}


def helper(name):
    path, pin = HELPERS[name]
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
        raise ValueError("Pinned census helper differs: " + name)
    spec = importlib.util.spec_from_file_location("architecture_census_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common, selective = helper("common"), helper("selective")
Inputs, sha, canonical, digest, require, inside = (
    common.Inputs, common.sha, common.canonical, common.digest, common.require, common.inside)
project_json = selective.project_json
POLICY = "poetry_architecture_historical_metadata_join_v1"
SLOT = {key: True for key in ("slot_id", "case_id", "leaf_id", "repeat", "prompt_sha256")}
LEAF = {"question_id": True, "verdict": True}
VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
LIMITS = [
    "Finite historical metadata, criterion IDs and verdict states only; prompt/source prose, poems, quotations, rationales, targets and oracle fields are not decoded.",
    "Settlement and static export files are hash-only. Predecessor roots add no observations or votes; no historical settlement/schema/evidence or modern admission is replayed.",
    "The ablation public opaque tree-commitment convention is unavailable; its local receipt joins are not attributed to the public aggregate by matching counts or folder names.",
    "DSPy public settlement/export hashes bind the private files, but the inherited 4 proposal/40 task categorization has no authoritative individual message/leaf map. Its 44 messages are not rubric votes.",
    "Native identities, backend execution, physical contact cardinality and retry cardinality remain unavailable; route/model declarations are not native attestation.",
    "Ablation source-input bytes are independently recipe-pinned; the retained slot manifests commit prompts rather than separate fixture hashes.",
]


def run(recipe, source_root):
    require(recipe["policy"] == POLICY and recipe["helper_pins"] == {k: v[1] for k, v in HELPERS.items()},
            "Recipe policy or helper pins differ")
    reader, public_reader, files = Inputs(Path(source_root)), Inputs(REPOSITORY), {}
    for root in recipe["roots"]:
        require(reader.path(root["locator"]).is_dir(), "Missing architecture retained root")
        for entry in root["files"]:
            locator = root["locator"] + "/" + entry["locator"]
            require(locator not in files, "Duplicate recipe artifact")
            files[locator] = reader.raw(locator, entry["sha256"], entry["bytes"])
    public_files = {entry["locator"]: public_reader.raw(entry["locator"], entry["sha256"], entry["bytes"])
                    for entry in recipe["public_artifacts"]}

    def raw(root, path):
        locator = root + "/" + path
        require(locator in files, "Join path is outside finite recipe")
        return files[locator]

    def read(root, path, spec):
        require(path not in recipe["hash_only"], "Hash-only source cannot be decoded")
        return project_json(raw(root, path), spec)

    ablation = recipe["ablation"]
    root, expected = ablation["root"], ablation["expected"]
    manifest = read(root, "controller-manifest.json", {"controller_id": True, "controller_contract_sha256": True,
        "executor_prompt_aggregate_sha256": True, "slots": [SLOT]})
    executor = read(root, "executor-dry/study-manifest.json", {"prompt_aggregate_sha256": True, "slots": [SLOT]})
    plan = read(root, "settlement-plan.v1.json", {"controller_id": True, "slots": True})
    slots = manifest["slots"]
    require(slots == executor["slots"] and [s["slot_id"] for s in slots] == plan["slots"] == ablation["slot_ids"]
            and len(slots) == len(set(ablation["slot_ids"])) == expected["slots"]
            and plan["controller_id"] == manifest["controller_id"], "Ablation frozen slot binding differs")
    cases, leaves = {s["case_id"] for s in slots}, set(expected["criterion_positions"])
    require(len(cases) == expected["cases"] and dict(Counter(s["leaf_id"] for s in slots)) == expected["criterion_positions"]
            and {(s["case_id"], s["leaf_id"], s["repeat"]) for s in slots}
            == {(case, leaf, repeat) for case in cases for leaf in leaves for repeat in range(1, expected["repeats"] + 1)},
            "Ablation singleton repeat geometry differs")
    require(digest({s["slot_id"]: s["prompt_sha256"] for s in slots})
            == manifest["executor_prompt_aggregate_sha256"] == executor["prompt_aggregate_sha256"],
            "Ablation prompt aggregate differs")
    observations = []
    for slot in slots:
        sid, base = slot["slot_id"], f"attempts/{slot['slot_id']}/attempt-01"
        prompt = raw(root, f"executor-dry/rendered-prompts/{sid}.txt")
        source = raw(root, f"executor-dry/inputs/{sid}.txt")
        require(sha(prompt) == slot["prompt_sha256"], "Ablation prompt bytes differ")
        claim_raw, terminal_raw = raw(root, f"claims/{sid}.json"), raw(root, f"terminals/{sid}.json")
        identity = {"controller_id": manifest["controller_id"], "slot_id": sid, "attempt": 1}
        claim = project_json(claim_raw, {key: True for key in (*identity, "state", "prompt_sha256")})
        require(claim == {**identity, "state": "claimed_before_contact", "prompt_sha256": slot["prompt_sha256"]},
                "Ablation claim binding differs")
        terminal = project_json(terminal_raw, {key: True for key in (*identity, "case_id", "leaf_id", "repeat",
            "attempt_path", "raw_path", "route_path", "dispatcher_sha256", "transport_marker", "disposition",
            "raw_sha256", "route_sha256", "prompt_sha256")} | {"verdict": LEAF})
        require({k: terminal[k] for k in identity} == identity
                and all(terminal[k] == slot[k] for k in ("case_id", "leaf_id", "repeat", "prompt_sha256"))
                and terminal["attempt_path"] == base and terminal["raw_path"] == base + "/raw-response.bin"
                and terminal["route_path"] == base + "/route-attestation.bin"
                and terminal["transport_marker"] == "exact_codex_adapter_v1"
                and terminal["disposition"] == "terminal_accepted", "Ablation terminal identity/disposition differs")
        response_raw, route_raw = raw(root, terminal["raw_path"]), raw(root, terminal["route_path"])
        message_raw = raw(root, f"adapter-attempts/{sid}/attempt-01/responses/batch-0001.attempt-0001.message.json")
        require(sha(response_raw) == terminal["raw_sha256"] and sha(route_raw) == terminal["route_sha256"]
                and message_raw == response_raw, "Ablation response or route commitment differs")
        route = project_json(route_raw, {"kind": True, "fallback_used": True, "prompt_sha256": True,
            "raw_response_sha256": True, "reported": {key: True for key in ("provider", "model", "reasoning_effort")}})
        require(route == {"kind": "codex_exact_transport_attestation_v1", "fallback_used": False,
                "prompt_sha256": slot["prompt_sha256"], "raw_response_sha256": sha(response_raw),
                "reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}},
                "Ablation retained route declaration differs")
        response = project_json(response_raw, {"verdicts": [LEAF]})["verdicts"]
        require(len(response) == 1 and response[0] == terminal["verdict"]
                and response[0]["question_id"] == slot["leaf_id"] and response[0]["verdict"] in VERDICTS,
                "Ablation singleton or duplicate verdict projection differs")
        observations.append({"position_id_sha256": digest([sid, slot["leaf_id"]]), "case_id_sha256": digest(slot["case_id"]),
            "repeat": slot["repeat"], **response[0], "claim_sha256": sha(claim_raw), "terminal_sha256": sha(terminal_raw),
            "prompt_sha256": sha(prompt), "source_raw_sha256": sha(source), "response_raw_sha256": sha(response_raw),
            "route_raw_sha256": sha(route_raw), "declared_dispatcher_sha256": terminal["dispatcher_sha256"],
            "disposition": terminal["disposition"], "public_aggregate_link": "unresolved_opaque_commitment_convention"})
    require(len({r["position_id_sha256"] for r in observations}) == len(observations), "Duplicate ablation observation")
    opaque = project_json(public_files[ablation["public_locator"]],
                          {"opaque_private_receipt_and_settlement_commitment_sha256": True})
    dspy = recipe["dspy"]
    public = project_json(public_files[dspy["public_locator"]], {
        "source_commitments": {"settlement_sha256": True, "static_export_sha256": True},
        "execution": {"proposal_responses": True, "task_responses": True}})
    require(public["source_commitments"] == {"settlement_sha256": sha(raw(dspy["root"], "dspy-compile-settlement.json")),
                                            "static_export_sha256": sha(raw(dspy["root"], "compiled-static-export.txt"))},
            "DSPy public/private source commitment differs")
    require(public["execution"] == {"proposal_responses": dspy["declared_proposal_responses"],
                                   "task_responses": dspy["declared_task_responses"]}
            and len(dspy["message_paths"]) == len(set(dspy["message_paths"])) == dspy["expected_retained_messages"]
            == sum(public["execution"].values()), "DSPy declared message geometry differs")
    messages = [{"message_locator_local_only": p, "raw_sha256": sha(raw(dspy["root"], p)),
                 "bytes": len(raw(dspy["root"], p)), "individual_role_and_leaf_mapping": "unavailable"}
                for p in dspy["message_paths"]]
    hashes = Counter(m["raw_sha256"] for m in messages)
    artifacts = [{"source_scope": "private", **a} for a in reader.artifacts.values()]
    artifacts.extend({"source_scope": "public_repository", **a} for a in public_reader.artifacts.values())
    private = {"policy": POLICY, "ablation_local_observations": observations, "dspy_messages_hashed_only": messages,
        "ablation_public_opaque_commitment_declared": opaque, "dspy_public_private_commitments_verified": public["source_commitments"],
        "excluded_ancestors": recipe["excluded_ancestors"], "artifact_index": artifacts}
    report = {"schema_version": 1, "policy": POLICY, "status": "historical_metadata_join_with_explicit_gaps",
        "observed": {"ablation_local": {"allocated_claims": len(observations), "historical_accepted_terminals": len(observations),
            "singleton_leaf_positions": len(observations), "criterion_positions": dict(Counter(r["question_id"] for r in observations)),
            "duplicate_response_projections_not_added": len(observations), "native_identity_unavailable_slots": len(observations),
            "public_aggregate_attributed_leaf_positions": 0, "verdict_states": dict(sorted(Counter(r["verdict"] for r in observations).items()))},
            "dspy": {"retained_messages_hashed_only": len(messages), "distinct_message_hashes": len(hashes),
                "repeated_content_message_positions": sum(n - 1 for n in hashes.values()),
                "public_private_settlement_export_link": "verified_exact_raw_hashes", "decoded_or_admitted_leaf_positions": 0},
            "verified_artifacts": len(artifacts), "artifact_bytes": sum(a["source_bytes"] for a in artifacts)},
        "inherited_declarations": {"dspy_message_categories": public["execution"]},
        "gaps": {"ablation_public_private_link": "unresolved_opaque_commitment_convention",
                 "dspy_individual_proposal_task_leaf_map": "unavailable", "native_identity_attestation": "unavailable",
                 "physical_contact_and_retry_cardinality": "unavailable"},
        "limitations": LIMITS, "implementation_sha256": sha(Path(__file__).read_bytes()), "recipe_canonical_sha256": digest(recipe),
        "input_commitment_sha256": digest(artifacts), "private_ledger_sha256": sha(canonical(private) + b"\n"),
        "provider_calls_made": 0, "new_provider_votes": 0}
    return report, private


def destination(output, source_root, recipe):
    output = Path(output).resolve()
    require(not output.exists() and not inside(output, REPOSITORY), "Output must be fresh and outside repository")
    require(all(not inside(output, Path(source_root) / r["locator"]) for r in recipe["roots"]), "Output overlaps retained input")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    recipe_raw = (HERE / "recipe.json").read_bytes()
    recipe = json.loads(recipe_raw)
    output = destination(args.output_root, args.source_root, recipe)
    report, private = run(recipe, args.source_root)
    report["recipe_file_sha256"] = sha(recipe_raw)
    report_raw = canonical(report) + b"\n"
    receipt = {key: report[key] for key in ("policy", "observed", "gaps", "implementation_sha256", "recipe_file_sha256",
                                          "recipe_canonical_sha256", "input_commitment_sha256", "private_ledger_sha256")}
    receipt.update(report_sha256=sha(report_raw), dry_run=args.dry_run, provider_calls_made=0, new_provider_votes=0)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        snapshots = {"census.py": Path(__file__).read_bytes(), "recipe.json": recipe_raw, "census.json": report_raw,
                     "private-ledger.json": canonical(private) + b"\n",
                     "invocation.json": canonical({"source_root_local_only": str(args.source_root.resolve()),
                                                    "output_root_local_only": str(output)}) + b"\n",
                     "terminal.json": canonical({**receipt, "state": "completed"}) + b"\n"}
        snapshots.update({name + ".py": path.read_bytes() for name, (path, _) in HELPERS.items()})
        for name, content in snapshots.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
