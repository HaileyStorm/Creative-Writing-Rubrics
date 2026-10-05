"""Provider-free historical full-book request, leaf and reported-session census."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
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
    spec = importlib.util.spec_from_file_location("fullbook_census_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common, selective = helper("common"), helper("selective")
Inputs, sha, digest, canonical, require, inside = (
    common.Inputs, common.sha, common.digest, common.canonical, common.require, common.inside)
project_json = selective.project_json
POLICY = "fullbook_historical_request_leaf_reported_session_join_v1"
VERDICTS = {"YES", "NO", "CANNOT_ASSESS", "NOT_APPLICABLE"}
LEAF = {"question_id": True, "verdict": True}
RUN = {"run_id": True, "config_sha256": True,
       "configuration": {"question_ids": True, "batch_size": True, "bundle_id": True}}
CHECKPOINT = {key: True for key in (
    "batch", "accepted_attempt", "question_ids", "prompt_sha256", "base_prompt_sha256",
    "effective_prompt_sha256", "response_sha256", "previous_checkpoint_sha256", "verdicts_sha256")}
CHECKPOINT.update(response_artifact={"path": True, "sha256": True, "bytes": True},
                  rejected_chain={"count": True, "head_sha256": True}, normalized_verdicts=[LEAF],
                  provider={"reported": {key: True for key in ("provider", "model", "reasoning_effort", "session_id")}})
START = {key: True for key in ("attempt", "batch", "base_prompt_sha256", "effective_prompt_sha256",
                             "config_sha256", "policy", "state")}
SETTLED = {key: True for key in ("attempt", "batch", "start_sha256", "policy", "state", "outcome")}
SETTLED["evidence"] = {"kind": True, "path": True, "sha256": True}
LIMITS = [
    "Historical accepted checkpoints and terminal sidecars only; reported sessions are not native-envelope or backend execution attestation.",
    "No creative payload or response prose decoding, human targets, historical scoring or modern semantic admission replay.",
    "Accepted logical request counts do not establish physical contact cardinality; rejected predecessor evidence is not replayed.",
    "V8 synthesis and V9 reconstruction add no binary observations; source identities remain immutable and scope-qualified.",
    "Only three declared roots and their finite recipe paths are covered; this is not complete census B closure.",
]


def run(recipe, source_root):
    require(recipe["policy"] == POLICY, "Recipe policy differs")
    require(recipe["helper_pins"] == {k: v[1] for k, v in HELPERS.items()}, "Recipe helper pins differ")
    reader = Inputs(Path(source_root))
    raw_files = {}
    for root in recipe["roots"]:
        require(reader.path(root["locator"]).is_dir(), "Missing full-book root")
        for entry in root["files"]:
            locator = root["locator"] + "/" + entry["locator"]
            require(locator not in raw_files, "Duplicate recipe artifact")
            raw_files[locator] = reader.raw(locator, entry["sha256"], entry["bytes"])

    def raw(root, path):
        locator = root + "/" + path
        require(locator in raw_files, "Join path is outside finite recipe")
        return raw_files[locator]

    freeze_root = recipe["freeze_root"]
    plan = project_json(raw(freeze_root, "plan.json"), {"parent_roots": True})
    freeze = project_json(raw(freeze_root, "freeze-manifest.json"),
                          {"files": {"plan.json": {"sha256": True, "bytes": True}}})
    require(freeze["files"]["plan.json"] == {"sha256": sha(raw(freeze_root, "plan.json")),
                                             "bytes": len(raw(freeze_root, "plan.json"))}, "V9 plan commitment differs")
    require(set(plan["parent_roots"]) == {r["artifact_id"] for r in recipe["executions"]}, "V9 parent inventory differs")
    slots, leaves, scopes, sessions = [], [], [], Counter()
    missing_sessions, rejected_predecessors = 0, 0
    for execution in recipe["executions"]:
        root = execution["root"]
        require(Path(plan["parent_roots"][execution["artifact_id"]]).resolve() == reader.path(root), "V9 execution root differs")
        parent = project_json(raw(root, "plan.json"), {"route": {"sampling_plan": {"unit_ids": True}}})
        require([s["id"] for s in execution["scopes"]] == ["global", *parent["route"]["sampling_plan"]["unit_ids"]],
                "Declared scope order differs")
        for scope in execution["scopes"]:
            prefix = ".private/evaluations/" + scope["id"] + "/"
            manifest = project_json(raw(root, prefix + "run.json"), RUN)
            cfg = manifest["configuration"]
            ids, batch_size = cfg["question_ids"], cfg["batch_size"]
            require(len(ids) == scope["positions"] and len(ids) == len(set(ids))
                    and cfg["bundle_id"] == scope["bundle_id"] and type(batch_size) is int and batch_size > 0,
                    "Scope question identity or geometry differs")
            total_batches = (len(ids) + batch_size - 1) // batch_size
            require(total_batches == scope["batches"], "Scope batch geometry differs")
            joined, previous = [], None
            for number in range(1, total_batches + 1):
                checkpoint_path = prefix + f"responses/batch-{number:04d}.json"
                checkpoint_raw = raw(root, checkpoint_path)
                cp = project_json(checkpoint_raw, CHECKPOINT)
                expected = ids[(number - 1) * batch_size:number * batch_size]
                require(cp["batch"] == number and cp["question_ids"] == expected
                        and cp["previous_checkpoint_sha256"] == previous, "Checkpoint order or chain differs")
                require([v["question_id"] for v in cp["normalized_verdicts"]] == expected
                        and all(v["verdict"] in VERDICTS for v in cp["normalized_verdicts"]), "Checkpoint leaf identities or states differ")
                attempt = cp["accepted_attempt"]
                require(type(attempt) is int and attempt > 0, "Accepted attempt identity differs")
                stem = prefix + f"responses/attempt-lifecycle/batch-{number:04d}/attempt-{attempt:04d}"
                start_raw = raw(root, stem + ".start.json")
                start, settled = project_json(start_raw, START), project_json(raw(root, stem + ".settled.json"), SETTLED)
                require(start["policy"] == settled["policy"] == "terminal_sidecar_v1"
                        and start["state"] == "started" and settled["state"] == "settled"
                        and settled["outcome"] == "accepted" and start["attempt"] == settled["attempt"] == attempt
                        and start["batch"] == settled["batch"] == number
                        and start["config_sha256"] == manifest["config_sha256"]
                        and settled["start_sha256"] == sha(start_raw), "Accepted lifecycle binding differs")
                require(settled["evidence"] == {"kind": "accepted_checkpoint", "path": checkpoint_path[len(prefix):],
                                                "sha256": sha(checkpoint_raw)}, "Settlement checkpoint binding differs")
                prompt = gzip.decompress(raw(root, prefix + f"responses/batch-{number:04d}.prompt.txt.gz"))
                require(sha(prompt) == cp["prompt_sha256"] == cp["base_prompt_sha256"] == start["base_prompt_sha256"]
                        and cp["effective_prompt_sha256"] == start["effective_prompt_sha256"], "Request prompt commitment differs")
                artifact = cp["response_artifact"]
                response = raw(root, prefix + artifact["path"])
                require(sha(response) == artifact["sha256"] == cp["response_sha256"]
                        and len(response) == artifact["bytes"], "Accepted response commitment differs")
                attempt_response = raw(root, prefix + f"responses/batch-{number:04d}.attempt-{attempt:04d}.message.json")
                require(attempt_response == response, "Original attempt and accepted response bytes differ")
                reported = cp["provider"]["reported"]
                session = reported["session_id"]
                if isinstance(session, str) and session.strip():
                    sessions[digest(session)] += 1
                else:
                    missing_sessions += 1
                rejected_predecessors += cp["rejected_chain"]["count"]
                slot_id = digest([execution["artifact_id"], scope["id"], number])
                slots.append({"slot_id_sha256": slot_id, "scope_id_sha256": digest([root, scope["id"]]),
                              "batch": number, "accepted_attempt": attempt, "checkpoint_sha256": sha(checkpoint_raw),
                              "response_sha256": sha(response), "prompt_sha256": sha(prompt),
                              "retained_response_schema_sha256": sha(raw(root, prefix + "response.schema.json")),
                              "reported_session_sha256": digest(session) if isinstance(session, str) and session.strip() else None,
                              "reported_provider": reported["provider"], "reported_model": reported["model"],
                              "reported_reasoning_effort": reported["reasoning_effort"]})
                for v in cp["normalized_verdicts"]:
                    leaves.append({"slot_id_sha256": slot_id, "position_id_sha256": digest([root, scope["id"], v["question_id"]]),
                                   "question_id": v["question_id"], "verdict": v["verdict"]})
                joined.extend(cp["normalized_verdicts"])
                previous = sha(checkpoint_raw)
            verdict_raw = raw(root, prefix + "verdicts.jsonl")
            retained = [project_json(line, LEAF) for line in verdict_raw.splitlines() if line.strip()]
            require(retained == joined and sha(verdict_raw) == cp["verdicts_sha256"], "Retained leaf order, states or final commitment differs")
            scopes.append({"scope_id_sha256": digest([root, scope["id"]]), "bundle_id": cfg["bundle_id"],
                           "positions": len(joined), "accepted_requests": total_batches})
    require(len(slots) == recipe["expected"]["requests"] and len(leaves) == recipe["expected"]["positions"], "Full-book census denominator differs")
    require(len({v["position_id_sha256"] for v in leaves}) == len(leaves), "Duplicate qualified leaf position")
    gaps = {"missing_reported_sessions": missing_sessions,
            "duplicate_reported_session_request_positions": sum(n - 1 for n in sessions.values()),
            "declared_rejected_predecessors_not_replayed": rejected_predecessors}
    artifact_index = list(reader.artifacts.values())
    private = {"policy": POLICY, "requests": slots, "leaves": leaves, "artifact_index": artifact_index}
    report = {"schema_version": 1, "policy": POLICY, "status": "historical_metadata_join",
              "observed": {"execution_roots": len(recipe["executions"]), "scopes": len(scopes),
                           "accepted_request_chains": len(slots), "ordered_leaf_positions": len(leaves),
                           "distinct_reported_sessions": len(sessions), "verified_artifacts": len(artifact_index),
                           "artifact_bytes": sum(v["source_bytes"] for v in artifact_index),
                           "verdict_states": dict(sorted(Counter(v["verdict"] for v in leaves).items()))},
              "scopes": scopes, "gaps": gaps, "limitations": LIMITS,
              "recipe_canonical_sha256": digest(recipe), "implementation_sha256": sha(Path(__file__).read_bytes()),
              "input_commitment_sha256": digest(artifact_index), "private_ledger_sha256": sha(canonical(private) + b"\n"),
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
        files = {"census.py": Path(__file__).read_bytes(), "recipe.json": recipe_raw, "census.json": report_raw,
                 "private-ledger.json": canonical(private) + b"\n",
                 "invocation.json": canonical({"source_root_local_only": str(args.source_root.resolve()),
                                                "output_root_local_only": str(output)}) + b"\n",
                 "terminal.json": canonical({**receipt, "state": "completed"}) + b"\n"}
        files.update({name + ".py": path.read_bytes() for name, (path, _) in HELPERS.items()})
        for name, content in files.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
