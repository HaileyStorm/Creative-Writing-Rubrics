"""Provider-free QPC24 historical receipt, criterion-ID and state census."""
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
    spec = importlib.util.spec_from_file_location("qpc24_census_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common, selective = helper("common"), helper("selective")
Inputs, sha, canonical, digest, require, inside = (
    common.Inputs, common.sha, common.canonical, common.digest, common.require, common.inside)
project_json = selective.project_json
POLICY = "qpc24_historical_receipt_id_state_join_v1"
LEAF = {"question_id": True, "verdict": True}
CHAIN = {key: True for key in ("base_request_index", "slot_id", "claim_sha256", "terminal_sha256",
                              "call_receipt_sha256", "reported_identity_receipt_sha256", "response_sha256")}
NEW_CHAIN = {key: value for key, value in CHAIN.items() if key != "slot_id"}
SLOT = {key: True for key in ("base_request_index", "slot_id", "role", "repetition", "batch",
                             "question_count", "prompt_sha256", "source_sha256")}
VERDICTS = {"YES", "NO", "CANNOT_ASSESS", "NOT_APPLICABLE"}
LIMITS = [
    "Historical receipt metadata and raw response IDs/states only; quotations, evidence, prose and human ratings are not decoded.",
    "Reported sessions are not native-envelope or backend execution attestation; accepted chains do not establish physical contact cardinality.",
    "Prompt and source commitments are joined as retained metadata; original outbound prompt/source bytes are not independently reconstructed or opened.",
    "The inherited 170 evidence normalizations are a settlement declaration, not a replay of invalid_exact_quote_to_summary_v1 or current admission.",
    "Excluded incomplete passes remain nonvoting; incomplete-attempt absence declarations are historical and are not fresh native/process proofs.",
    "Only the finite seven-root QPC24 selection is covered; no full-book, multisample or complete census B inference is added.",
]


def reported(raw):
    # Discover field names while skipping their values, then decode only identity metadata.
    class Names(dict):
        def __init__(self):
            self.names = []

        def __contains__(self, key):
            self.names.append(key)
            return False

    names = Names()
    project_json(raw, {"reported": names})
    required = {"provider", "model", "reasoning_effort"}
    require(required <= set(names.names) <= required | {"session_id"}, "Reported identity field contract differs")
    return project_json(raw, {"reported": {key: True for key in names.names}})["reported"]


def run(recipe, source_root):
    require(recipe["policy"] == POLICY and recipe["helper_pins"] == {k: v[1] for k, v in HELPERS.items()},
            "Recipe policy or helper pins differ")
    reader, files = Inputs(Path(source_root)), {}
    for root in recipe["roots"]:
        require(reader.path(root["locator"]).is_dir(), "Missing QPC24 retained root")
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

    packages = recipe["packages"]
    v5 = packages["v5"]["root"]
    frozen = read(v5, "private-freeze.v1.json", {
        "v3_lineage": {"inherited_v2_complete_receipt_chains": [CHAIN], "semantic_direct_receipt_chains": [CHAIN],
                       "all_21_direct_receipt_chains": [CHAIN],
                       "orphan": {"accepted_b01_index": True, "excluded_whole_pass": True,
                                  "orphan_b02_claim_sha256": True, "orphan_b02_terminal_call_identity": True}},
        "selection": {"target_voting_calls": True, "target_voting_positions": True}})
    settlement = read(v5, "settlement.v1.json", {"private_freeze_sha256": True, "new_accepted_receipt_chains": [NEW_CHAIN]})
    final = read(v5, "settlement.v2.json", {"private_freeze_sha256": True, "settlement_v1_sha256": True,
                                           "archived_acceptance_chains": {"v2": True, "v3": True, "v5": True, "total": True},
                                           "archived_response_geometry": {"complete_passes": True, "verdict_positions": True},
                                           "valid_evidence_normalizations": {"total": True, "v5": True}})
    require(settlement["private_freeze_sha256"] == final["private_freeze_sha256"] == sha(raw(v5, "private-freeze.v1.json"))
            and final["settlement_v1_sha256"] == sha(raw(v5, "settlement.v1.json")), "Settlement freeze binding differs")
    rows = {"v2": frozen["v3_lineage"]["inherited_v2_complete_receipt_chains"],
            "v3": frozen["v3_lineage"]["semantic_direct_receipt_chains"],
            "v5": [{**r, "slot_id": f"public_control_story-r3-b{r['base_request_index'] - 120:02d}"}
                   for r in settlement["new_accepted_receipt_chains"]]}
    counts = {key: len(value) for key, value in rows.items()}
    require(counts == recipe["expected"]["chains_by_origin"]
            and final["archived_acceptance_chains"] == {**counts, "total": sum(counts.values())}, "Inherited receipt membership differs")
    require(frozen["selection"] == {"target_voting_calls": recipe["expected"]["requests"],
                                    "target_voting_positions": recipe["expected"]["positions"]}, "Frozen denominator differs")

    base = recipe["controller_root"]
    controller = read(base, "qpc24-private-controller.v1.json", {"roles": [{"role": True, "source_sha256": True}]})
    sources = {r["role"]: r["source_sha256"] for r in controller["roles"]}
    binding = read(base, "qpc24-private-binding.v1.json", {"controller_sha256": True, "prompt_records": [
        {key: True for key in ("role", "repetition", "batch", "question_count", "prompt_sha256")}]})
    require(binding["controller_sha256"] == sha(raw(base, "qpc24-private-controller.v1.json")), "Controller binding differs")
    prompts = binding["prompt_records"]
    slots, passes = {}, {}
    for origin, package in packages.items():
        approval = read(package["root"], package["approval"], {"private_freeze_sha256": True, "controller_binding_sha256": True})
        binding_path = "live-controller-binding.v1.json" if origin == "v5" else "live-controller-binding.v3.json"
        require(approval == {"private_freeze_sha256": sha(raw(package["root"], package["freeze"])),
                             "controller_binding_sha256": sha(raw(package["root"], binding_path))},
                "Historical approval freeze binding differs")
        selected = read(package["root"], package["freeze"], {"slots": [SLOT]})["slots"]
        slots[origin] = {r["base_request_index"]: r for r in selected}
        require(len(slots[origin]) == len(selected), "Duplicate frozen slot identity")
    observations, leaves, excluded, sessions = [], [], [], Counter()
    missing_sessions = 0

    def chain(origin, row, voting):
        nonlocal missing_sessions
        package, sid, index = packages[origin], row["slot_id"], row["base_request_index"]
        root, neutral = package["root"], package["neutral_root"]
        slot = slots[origin].get(index)
        require(slot is not None and slot["slot_id"] == sid and 1 <= index <= len(prompts), "Receipt has no matching frozen slot")
        prompt = prompts[index - 1]
        require(prompt == {k: slot[k] for k in prompt} and sources[slot["role"]] == slot["source_sha256"],
                "Frozen prompt or source commitment differs")
        paths = {"claim_sha256": f"scheduler-state/claims/{sid}.claim.v1.json",
                 "terminal_sha256": f"scheduler-state/terminals/{sid}.terminal.v1.json",
                 "call_receipt_sha256": f"scheduler-state/call-receipts/{sid}.v1.json",
                 "reported_identity_receipt_sha256": f"scheduler-state/reported-identity-receipts/{sid}.v1.json"}
        response_path = f"slot-{index:04d}/responses/batch-{index:04d}.attempt-0001.message.json"
        require(all(sha(raw(root, path)) == row[key] for key, path in paths.items())
                and sha(raw(neutral, response_path)) == row["response_sha256"], "Archived receipt commitment differs")
        claim = read(root, paths["claim_sha256"], {"slot_id": True, "base_request_index": True})
        terminal = read(root, paths["terminal_sha256"], {"slot_id": True, "status": True, "receipt_sha256": True})
        call = read(root, paths["call_receipt_sha256"], {key: True for key in (
            "slot_id", "claim_sha256", "approval_sha256", "prompt_sha256", "source_sha256",
            "response_sha256", "reported_identity_receipt_sha256")})
        identity = read(root, paths["reported_identity_receipt_sha256"], {"slot_id": True, "claim_sha256": True, "reported_sha256": True})
        identity_reported = reported(raw(root, paths["reported_identity_receipt_sha256"]))
        require(claim == {"slot_id": sid, "base_request_index": index}
                and terminal == {"slot_id": sid, "status": "accepted", "receipt_sha256": row["call_receipt_sha256"]}
                and call["slot_id"] == identity["slot_id"] == sid
                and call["claim_sha256"] == identity["claim_sha256"] == row["claim_sha256"]
                and call["approval_sha256"] == sha(raw(root, package["approval"]))
                and call["reported_identity_receipt_sha256"] == row["reported_identity_receipt_sha256"]
                and identity["reported_sha256"] == sha(canonical(identity_reported) + b"\n")
                and call["response_sha256"] == row["response_sha256"]
                and call["prompt_sha256"] == slot["prompt_sha256"] and call["source_sha256"] == slot["source_sha256"],
                "Receipt provenance binding differs")
        observation = {"slot_id_sha256": digest([origin, sid]), "origin": origin, "base_request_index": index,
                       "response_sha256": row["response_sha256"], "call_receipt_sha256": row["call_receipt_sha256"],
                       "prompt_sha256": slot["prompt_sha256"], "source_sha256": slot["source_sha256"],
                       "reported_provider": identity_reported["provider"], "reported_model": identity_reported["model"],
                       "reported_reasoning_effort": identity_reported["reasoning_effort"], "voting": voting}
        session = identity_reported.get("session_id")
        observation["reported_session_sha256"] = digest(session) if isinstance(session, str) and session.strip() else None
        if not voting:
            excluded.append(observation)
            return
        if observation["reported_session_sha256"]:
            sessions[observation["reported_session_sha256"]] += 1
        else:
            missing_sessions += 1
        response_rows = read(neutral, response_path, {"verdicts": [LEAF]})["verdicts"]
        require(len(response_rows) == slot["question_count"] and all(isinstance(v["question_id"], str)
                and v["verdict"] in VERDICTS for v in response_rows), "Response ID/state geometry differs")
        pass_key = (slot["role"], slot["repetition"])
        passes.setdefault(pass_key, []).append((slot["batch"], response_rows))
        observations.append(observation)
        for v in response_rows:
            leaves.append({"position_id_sha256": digest([*pass_key, v["question_id"]]),
                           "slot_id_sha256": observation["slot_id_sha256"], **v})

    for origin, members in rows.items():
        require([r["base_request_index"] for r in members] == recipe["membership"][origin], "Selected request membership differs")
        for row in members:
            chain(origin, row, True)
    extra = [r for r in frozen["v3_lineage"]["all_21_direct_receipt_chains"] if r["base_request_index"] not in recipe["membership"]["v3"]]
    require([r["base_request_index"] for r in extra] == recipe["excluded_indexes"], "Excluded receipt membership differs")
    for row in extra:
        chain("v3", row, False)
    orphan = frozen["v3_lineage"]["orphan"]
    orphan_raw = raw(packages["v3"]["root"], "scheduler-state/claims/public_control_story-r2-b02.claim.v1.json")
    require(sha(orphan_raw) == orphan["orphan_b02_claim_sha256"] and orphan["accepted_b01_index"] in recipe["excluded_indexes"]
            and orphan["orphan_b02_terminal_call_identity"] == "ABSENT", "Historical orphan commitment differs")
    for batches in passes.values():
        require([number for number, _ in batches] == list(range(1, recipe["expected"]["batches_per_pass"] + 1)), "Complete pass batch order differs")
        ids = [v["question_id"] for _, batch in batches for v in batch]
        require(len(ids) == len(set(ids)) == recipe["expected"]["positions_per_pass"]
                and sha(canonical(ids) + b"\n") == recipe["question_sequence_sha256"], "Complete pass criterion sequence differs")
    require(len(observations) == recipe["expected"]["requests"] and len(leaves) == recipe["expected"]["positions"]
            and len({v["position_id_sha256"] for v in leaves}) == len(leaves)
            and final["archived_response_geometry"] == {"complete_passes": len(passes), "verdict_positions": len(leaves)},
            "Qualified position or final geometry differs")
    artifacts = list(reader.artifacts.values())
    private = {"policy": POLICY, "requests": observations, "leaves": leaves, "excluded_requests": excluded,
               "historical_reserved_attempt": {"pass_id_sha256": digest(orphan["excluded_whole_pass"]),
                                               "claim_sha256": sha(orphan_raw), "terminal_status": "historically_declared_absent_not_replayed"},
               "artifact_index": artifacts}
    report = {"schema_version": 1, "policy": POLICY, "status": "historical_metadata_id_state_join",
              "observed": {"accepted_voting_chains": len(observations), "chains_by_origin": counts,
                           "complete_passes": len(passes), "qualified_leaf_positions": len(leaves),
                           "distinct_reported_sessions": len(sessions), "excluded_accepted_chains": len(excluded),
                           "historical_reserved_claims_hashed": 1,
                           "verified_artifacts": len(artifacts), "artifact_bytes": sum(r["source_bytes"] for r in artifacts),
                           "verdict_states": dict(sorted(Counter(r["verdict"] for r in leaves).items()))},
              "gaps": {"missing_reported_sessions": missing_sessions,
                       "duplicate_reported_session_request_positions": sum(n - 1 for n in sessions.values()),
                       "outbound_prompt_bytes_independently_verified": False,
                       "historical_incomplete_attempts_not_replayed": True},
              "inherited_declarations": {"evidence_normalizations": final["valid_evidence_normalizations"]},
              "historical_sequence_source_declared": recipe.get("sequence_source"),
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
