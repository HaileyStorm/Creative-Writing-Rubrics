"""Provider-free historical poetry r3 singleton ID/state and receipt census."""
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
    spec = importlib.util.spec_from_file_location("poetry_r3_census_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common, selective = helper("common"), helper("selective")
Inputs, sha, canonical, digest, require, inside = (
    common.Inputs, common.sha, common.canonical, common.digest, common.require, common.inside)
project_json = selective.project_json
POLICY = "poetry_v2_r3_historical_singleton_metadata_join_v1"
LEAF = {"question_id": True, "verdict": True}
SLOT = {key: True for key in ("slot_id", "case_id", "arm", "repeat", "fixture_sha256", "prompt_sha256")}
IDENTITY = {key: True for key in ("study_id", "slot_id", "attempt")}
RECEIPT = {key: True for key in ("route", "model", "reasoning", "prompt_sha256", "fixture_sha256")}
VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
LIMITS = [
    "Historical r3 metadata and singleton ID/state projections only; poem text, quotations, notes, human ratings and sealed candidate ledger are not decoded.",
    "Raw source, rendered prompt, message and terminal bytes are verified against the finite recipe; canonical payload hashes remain retained declarations because full payloads are not decoded.",
    "Terminal verdict and payload verdict are duplicate projections of one observation, counted once; original and r2 superseded ancestors add no votes.",
    "No thread/session/native identity or native envelope is retained by this controller receipt contract; 42 historical terminals are not 42 verified native calls or physical contacts.",
    "No historical fixture-grounding/schema replay, current admission, scoring, candidate decision or human-alignment inference is performed.",
    "Only the two declared r3 roots are covered; no complete census B closure is implied.",
    "A preparatory exploratory read exceeded the settlement metadata boundary; its aggregates were not used for cohort, recipe or acceptance. Regeneration keeps settlement hash-only.",
]


def run(recipe, source_root):
    require(recipe["policy"] == POLICY and recipe["helper_pins"] == {k: v[1] for k, v in HELPERS.items()},
            "Recipe policy or helper pins differ")
    reader, files = Inputs(Path(source_root)), {}
    for root in recipe["roots"]:
        require(reader.path(root["locator"]).is_dir(), "Missing poetry r3 retained root")
        for entry in root["files"]:
            locator = root["locator"] + "/" + entry["locator"]
            require(locator not in files, "Duplicate recipe artifact")
            files[locator] = reader.raw(locator, entry["sha256"], entry["bytes"])

    def raw(root, path):
        locator = root + "/" + path
        require(locator in files, "Join path is outside finite recipe")
        return files[locator]

    def read(root, path, spec):
        return project_json(raw(root, path), spec)

    root, neutral, expected = recipe["source_root"], recipe["neutral_root"], recipe["expected"]
    manifest = read(root, "controller-manifest.json", {
        "study_id": True, "contract_sha256": True, "slots": [SLOT], "prompt_aggregate_sha256": True})
    binding = read(root, "controller-binding.v1.json", {
        "study_id": True, "study_contract_sha256": True, "route": True, "model": True, "reasoning": True})
    plan = read(root, "settlement-plan.v1.json", {"study_id": True, "valid_terminals_required": True})
    study = manifest["study_id"]
    require(binding["study_id"] == plan["study_id"] == study
            and binding["study_contract_sha256"] == manifest["contract_sha256"]
            and plan["valid_terminals_required"] == expected["slots"],
            "Historical study or settlement binding differs")
    slots = manifest["slots"]
    require([s["slot_id"] for s in slots] == recipe["slot_ids"]
            and len(slots) == len(set(recipe["slot_ids"])) == expected["slots"], "Frozen slot membership differs")
    cases, arms = {s["case_id"] for s in slots}, {s["arm"] for s in slots}
    require(len(cases) == expected["fixtures"] and len(arms) == expected["arms"]
            and len(slots) == expected["fixtures"] * expected["arms"] * expected["repeats"]
            and {(s["case_id"], s["arm"], s["repeat"]) for s in slots}
            == {(case, arm, repeat) for case in cases for arm in arms for repeat in range(1, expected["repeats"] + 1)},
            "Fixture arm repeat geometry differs")
    require(digest({s["slot_id"]: s["prompt_sha256"] for s in slots}) == manifest["prompt_aggregate_sha256"],
            "Prompt aggregate commitment differs")
    fixture_sets = {case: {s["fixture_sha256"] for s in slots if s["case_id"] == case} for case in cases}
    prompt_sets = {(case, arm): {s["prompt_sha256"] for s in slots if s["case_id"] == case and s["arm"] == arm}
                   for case in cases for arm in arms}
    require(all(len(values) == 1 for values in [*fixture_sets.values(), *prompt_sets.values()])
            and len({s["fixture_sha256"] for s in slots}) == expected["fixtures"]
            and len({s["prompt_sha256"] for s in slots}) == expected["prompt_hashes"],
            "Fixture or repeated prompt identity differs")
    observations = []
    for slot in slots:
        sid = slot["slot_id"]
        source_raw = raw(root, f"inputs/{sid}.txt")
        prompt_raw = raw(root, f"rendered-prompts/{sid}.txt")
        require(sha(source_raw) == slot["fixture_sha256"] and sha(prompt_raw) == slot["prompt_sha256"],
                "Frozen source or prompt bytes differ")
        claim = read(root, f"claims/{sid}.json", {**IDENTITY, **RECEIPT, "state": True})
        terminal_raw = raw(root, f"terminals/{sid}.json")
        terminal = project_json(terminal_raw, {**IDENTITY, "state": True, "receipt": RECEIPT,
                                               "response_sha256": True, "payload": {"verdicts": [LEAF]}, "verdict": LEAF})
        identity = {"study_id": study, "slot_id": sid, "attempt": 1}
        receipt = {"route": binding["route"], "model": binding["model"], "reasoning": binding["reasoning"],
                   "prompt_sha256": slot["prompt_sha256"], "fixture_sha256": slot["fixture_sha256"]}
        require(claim == {**identity, **receipt, "state": "claimed_before_contact"}
                and {k: terminal[k] for k in IDENTITY} == identity and terminal["state"] == "terminal_valid"
                and terminal["receipt"] == receipt, "Claim or terminal receipt binding differs")
        message_raw = raw(neutral, sid + "/responses/batch-0001.attempt-0001.message.json")
        message = project_json(message_raw, {"verdicts": [LEAF]})
        leaves = terminal["payload"]["verdicts"]
        require(len(leaves) == 1 and message["verdicts"] == leaves and terminal["verdict"] == leaves[0]
                and leaves[0]["question_id"] == recipe["question_id"] and leaves[0]["verdict"] in VERDICTS,
                "Singleton or duplicate verdict projection differs")
        observations.append({"position_id_sha256": digest([sid, recipe["question_id"]]),
                             "case_id_sha256": digest(slot["case_id"]), "wording_arm_sha256": digest(slot["arm"]),
                             "repeat": slot["repeat"], **leaves[0], **receipt,
                             "claim_sha256": sha(raw(root, f"claims/{sid}.json")),
                             "terminal_sha256": sha(terminal_raw), "message_raw_sha256": sha(message_raw),
                             "declared_canonical_payload_sha256": terminal["response_sha256"],
                             "canonical_payload_hash_verified": False, "native_identity_status": "unavailable"})
    require(len({r["position_id_sha256"] for r in observations}) == len(observations), "Duplicate qualified observation")
    artifacts = list(reader.artifacts.values())
    private = {"policy": POLICY, "observations": observations, "artifact_index": artifacts,
               "excluded_superseded_ancestors": recipe["excluded_ancestors"]}
    report = {"schema_version": 1, "policy": POLICY, "status": "historical_metadata_id_state_join",
              "observed": {"historical_valid_terminal_observations": len(observations),
                           "singleton_leaf_positions": len(observations), "unique_criterion_ids": 1,
                           "fixtures": len(cases), "wording_arms": len(arms), "repeats_per_contract": expected["repeats"],
                           "distinct_fixture_hashes": len(fixture_sets), "distinct_prompt_hashes": expected["prompt_hashes"],
                           "duplicate_terminal_projections_not_added": len(observations),
                           "verified_artifacts": len(artifacts), "artifact_bytes": sum(r["source_bytes"] for r in artifacts),
                           "verdict_states": dict(sorted(Counter(r["verdict"] for r in observations).items()))},
              "gaps": {"native_identity_unavailable_observations": len(observations),
                       "canonical_payload_hashes_retained_declared_not_verified": len(observations)},
              "historical_study_source_declared": recipe["historical_study_source"],
              "limitations": LIMITS, "implementation_sha256": sha(Path(__file__).read_bytes()),
              "recipe_canonical_sha256": digest(recipe), "input_commitment_sha256": digest(artifacts),
              "private_ledger_sha256": sha(canonical(private) + b"\n"), "provider_calls_made": 0, "new_provider_votes": 0}
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
