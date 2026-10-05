"""Provider-free figurative-scope v3 historical request and singleton state census."""
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
    spec = importlib.util.spec_from_file_location("figurative_census_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common, selective = helper("common"), helper("selective")
Inputs, sha, canonical, digest, require, inside = (
    common.Inputs, common.sha, common.canonical, common.digest, common.require, common.inside)
project_json = selective.project_json
POLICY = "figurative_scope_v3_historical_singleton_metadata_join_v1"
CONDITION = {key: True for key in ("arm", "prompt_sha256", "rubric_sha256")}
SLOT = {key: True for key in ("slot_id", "study_id", "artifact_id", "artifact_file", "artifact_sha256",
                             "leaf_id", "arm", "repetition", "logical_sample_id")}
SLOT["condition"] = CONDITION
LEAF = {"question_id": True, "verdict": True}
VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
HASH_ONLY = ["public-aggregate.json", "settlement.json", "private-schedule.json", "v1-response-rows.json"]
LIMITS = [
    "Only the finite v3 historical metadata, criterion IDs and verdict states are decoded; source/prompt prose, quotations, notes, targets and oracle values remain unopened.",
    "Aggregate, settlement, private schedule and inherited response rows are hash-only; original and v2 ancestors add no observations.",
    "Accepted, attempt and normalized checkpoint representations count once per qualified logical observation; no physical-contact cardinality is inferred.",
    "Reported provider sessions are declarations, not native-envelope, account or backend execution proof; historical code bindings are not current-code equivalence.",
    "Canonical full payload, verdict and configuration hashes remain declared where verification would require excluded fields. Stored portable schema bytes are pinned independently of the declared original schema.",
    "Only the historical universal-newline prompt projection is checked; no current schema/admission, evidence grounding, scoring or human-alignment replay is performed.",
]


def newline_bytes(raw):
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def run(recipe, source_root):
    require(recipe["policy"] == POLICY and recipe["helper_pins"] == {k: v[1] for k, v in HELPERS.items()}
            and recipe["hash_only"] == HASH_ONLY and recipe["historical_prompt_projection"] == "universal_newlines_only_v1",
            "Recipe policy or helper pins differ")
    reader, files = Inputs(Path(source_root)), {}
    for root in recipe["roots"]:
        require(reader.path(root["locator"]).is_dir(), "Missing figurative v3 retained root")
        for entry in root["files"]:
            locator = root["locator"] + "/" + entry["locator"]
            require(locator not in files, "Duplicate recipe artifact")
            files[locator] = reader.raw(locator, entry["sha256"], entry["bytes"])
    root = recipe["source_root"]

    def raw(path):
        locator = root + "/" + path
        require(locator in files, "Join path is outside finite recipe")
        return files[locator]

    def read(path, spec):
        require(path not in HASH_ONLY, "Hash-only source cannot be decoded")
        return project_json(raw(path), spec)

    manifest = read("study-manifest.json", {"study_id": True, "planned_requests": True,
                    "runtime_bindings": True, "contract_sha256": True, "slots": [SLOT]})
    runtime = read("runtime-schedule.json", {"slots": [SLOT]})["slots"]
    preview = read("dry-run.json", {"mode": True, "provider_calls": True, "planned_requests": True,
                                  "rendered_prompt_sha256s": True, "runtime_bindings": True})
    expected = recipe["expected"]
    require(manifest["runtime_bindings"] == preview["runtime_bindings"] == recipe["historical_runtime_bindings"]
            and manifest["contract_sha256"] == recipe["historical_contract_sha256"]
            and manifest["planned_requests"] == preview["planned_requests"] == expected["slots"]
            and preview["mode"] == "dry_run" and preview["provider_calls"] == 0,
            "Historical runtime or preparation binding differs")
    prepared = manifest["slots"]
    require([s["slot_id"] for s in prepared] == [s["slot_id"] for s in runtime] == recipe["slot_ids"]
            and len(runtime) == len(set(recipe["slot_ids"])) == expected["slots"]
            and len({s["logical_sample_id"] for s in runtime}) == len(runtime), "Slot or logical membership differs")
    require(all({k: s[k] for k in SLOT if k not in {"condition", "logical_sample_id"}}
                == {k: p[k] for k in SLOT if k not in {"condition", "logical_sample_id"}} for s, p in zip(runtime, prepared)),
            "Prepared/runtime source or scope differs")
    require(dict(Counter(s["arm"] for s in runtime)) == expected["arms"]
            and dict(Counter(str(s["repetition"]) for s in runtime)) == expected["repetitions"]
            and dict(Counter(s["leaf_id"] for s in runtime)) == expected["criterion_positions"]
            and preview["rendered_prompt_sha256s"] == {s["slot_id"]: s["condition"]["prompt_sha256"] for s in runtime},
            "Frozen arm/repetition/criterion geometry differs")
    cells = Counter((s["artifact_id"], s["leaf_id"], s["arm"], s["repetition"]) for s in runtime)
    require(all(count == 1 for count in cells.values()) and all(s["study_id"] == manifest["study_id"] for s in runtime),
            "Duplicate qualified cell or study identity")
    observations, sessions, runs = [], Counter(), Counter()
    missing_sessions, newline_projections = 0, 0
    historical = recipe["historical_runtime_bindings"]["cwr_files"]
    for slot, original in zip(runtime, prepared):
        sid, leaf_id = slot["slot_id"], slot["leaf_id"]
        prefix = f"runs/{sid}/"
        source_raw = raw("inputs/" + slot["artifact_file"])
        rendered = raw(f"rendered-prompts/{sid}.txt")
        condition = slot["condition"]
        require(sha(source_raw) == slot["artifact_sha256"] and sha(rendered) == condition["prompt_sha256"]
                and condition["arm"] == slot["arm"] and condition["rubric_sha256"] == historical["registry/all_modules.json"],
                "Source, rendered prompt or rubric binding differs")
        record = read(prefix + "run.json", {"format_version": True, "run_id": True, "config_sha256": True,
            "configuration": {key: True for key in ("provider", "model", "reasoning", "batch_size", "artifact_id", "bundle_id",
                "question_ids", "contexts", "artifact", "response_schema", "prompts", "task_contract", "scope_compatibility",
                "task_contract_judge_context", "compiled_bundle_sha256", "questions_sha256")}})
        cfg = record["configuration"]
        require(record["format_version"] == 4 and isinstance(record["run_id"], str) and record["run_id"].strip()
                and all(cfg[k] == v for k, v in {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high",
                    "batch_size": 1, "artifact_id": slot["artifact_id"], "bundle_id": "prose.short_story",
                    "question_ids": [leaf_id], "contexts": []}.items())
                and cfg["artifact"]["sha256"] == sha(source_raw) and cfg["artifact"]["bytes"] == len(source_raw)
                and cfg["response_schema"]["sha256"] == historical["schema/hbq_judge_response.schema.json"]
                and [p["sha256"] for p in cfg["prompts"]] == [historical["prompts/judge/BINARY_EVALUATION_PROMPT.md"]],
                "Run source/runtime/schema declaration differs")
        if slot["arm"] == "baseline":
            require(all(cfg[k] is None for k in ("task_contract", "scope_compatibility", "task_contract_judge_context")),
                    "Baseline carries undeclared context")
        else:
            for field, directory in (("task_contract", "contracts"), ("scope_compatibility", "compatibility")):
                item = cfg[field]
                require(isinstance(item, dict), "Treatment context commitment absent")
                context_raw = raw(directory + "/" + item["name"])
                require(item["sha256"] == sha(context_raw) and item["bytes"] == len(context_raw), "Treatment context binding differs")
            require(cfg["scope_compatibility"]["mode"] == "reviewed_override"
                    and cfg["task_contract_judge_context"]["model_facing"] is True, "Treatment context mode differs")
        cp_raw = raw(prefix + "responses/batch-0001.json")
        cp = project_json(cp_raw, {key: True for key in ("batch", "accepted_attempt", "question_ids", "previous_checkpoint_sha256",
            "prompt_sha256", "base_prompt_sha256", "effective_prompt_sha256", "response_sha256", "verdicts_sha256")}
            | {"response_artifact": {"path": True, "sha256": True, "bytes": True},
               "rejected_chain": {"count": True, "head_sha256": True},
               "normalized_verdicts": [{**LEAF, "run_id": True}],
               "provider": {"reported": {key: True for key in ("provider", "model", "reasoning_effort", "session_id")}}})
        accepted_path = "responses/batch-0001.accepted-0001.message.txt"
        accepted = raw(prefix + accepted_path)
        attempt = raw(prefix + "responses/batch-0001.attempt-0001.message.json")
        require(cp["batch"] == cp["accepted_attempt"] == 1 and cp["question_ids"] == [leaf_id]
                and cp["previous_checkpoint_sha256"] is None and cp["rejected_chain"] == {"count": 0, "head_sha256": None}
                and cp["response_artifact"] == {"path": accepted_path, "sha256": sha(accepted), "bytes": len(accepted)}
                and attempt == accepted, "Checkpoint response or accepted-attempt binding differs")
        prompt = gzip.decompress(raw(prefix + "responses/batch-0001.prompt.txt.gz"))
        require(cp["prompt_sha256"] == cp["base_prompt_sha256"] == cp["effective_prompt_sha256"] == sha(prompt)
                and newline_bytes(prompt) == newline_bytes(rendered), "Checkpoint prompt binding differs")
        newline_projections += prompt != rendered
        response = project_json(accepted, {"verdicts": [LEAF]})["verdicts"]
        normalized = cp["normalized_verdicts"]
        require(len(response) == len(normalized) == 1 and response[0]["question_id"] == leaf_id
                and response[0]["verdict"] in VERDICTS and normalized == [{**response[0], "run_id": record["run_id"]}],
                "Singleton checkpoint ID/state or run binding differs")
        diagnostic = read(prefix + "diagnostic.json", {"status": True, "selected_question_ids": True,
                                                     "artifact_id": True, "bundle_id": True})
        require(diagnostic == {"status": "DIAGNOSTIC_SUBSET", "selected_question_ids": [leaf_id],
                               "artifact_id": slot["artifact_id"], "bundle_id": "prose.short_story"}, "Diagnostic scope binding differs")
        reported = cp["provider"]["reported"]
        require(all(reported[k] == v for k, v in {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}.items()),
                "Reported provider/model declaration differs")
        session = reported["session_id"]
        session_hash = sha(session.encode("utf-8")) if isinstance(session, str) and session.strip() else None
        if session_hash:
            sessions[session_hash] += 1
        else:
            missing_sessions += 1
        runs[record["run_id"]] += 1
        observations.append({"position_id_sha256": digest([slot["logical_sample_id"], leaf_id]),
            "logical_sample_id_sha256": digest(slot["logical_sample_id"]), "prepared_logical_sample_id_sha256": digest(original["logical_sample_id"]),
            "artifact_id_sha256": digest(slot["artifact_id"]), "artifact_sha256": slot["artifact_sha256"],
            "arm": slot["arm"], "repetition": slot["repetition"], **response[0], "condition": condition,
            "prepared_condition_sha256": digest(original["condition"]), "run_id_sha256": digest(record["run_id"]),
            "reported_session_sha256": session_hash, "checkpoint_sha256": sha(cp_raw), "accepted_message_sha256": sha(accepted),
            "checkpoint_prompt_sha256": sha(prompt), "canonical_newline_prompt_sha256": sha(newline_bytes(prompt)),
            "portable_schema_raw_sha256": sha(raw(prefix + "response.schema.json")),
            "declared_source_schema_sha256": cfg["response_schema"]["sha256"],
            "declared_config_sha256": record["config_sha256"], "declared_full_payload_sha256": cp["response_sha256"],
            "declared_full_verdicts_sha256": cp["verdicts_sha256"], "canonical_full_hashes_verified": False,
            "compiled_bundle_sha256": cfg["compiled_bundle_sha256"], "questions_sha256": cfg["questions_sha256"],
            "task_context_commitment_sha256": digest({k: cfg[k] for k in ("task_contract", "scope_compatibility", "task_contract_judge_context")})})
    require(len({r["position_id_sha256"] for r in observations}) == len(observations), "Duplicate qualified observation")
    artifacts = list(reader.artifacts.values())
    private = {"policy": POLICY, "observations": observations, "artifact_index": artifacts,
               "historical_runtime_bindings": recipe["historical_runtime_bindings"], "excluded_ancestors": recipe["excluded_ancestors"]}
    report = {"schema_version": 1, "policy": POLICY, "status": "historical_metadata_id_state_join",
        "observed": {"accepted_checkpoint_observations": len(observations), "singleton_leaf_positions": len(observations),
            "arms": dict(Counter(r["arm"] for r in observations)), "repetitions": dict(Counter(str(r["repetition"]) for r in observations)),
            "criterion_positions": dict(Counter(r["question_id"] for r in observations)), "distinct_reported_sessions": len(sessions),
            "distinct_run_ids": len(runs), "duplicate_checkpoint_representations_not_added": len(observations),
            "historical_newline_prompt_projections": newline_projections,
            "prepared_runtime_condition_differences": sum(p["condition"] != s["condition"] for p, s in zip(prepared, runtime)),
            "verified_artifacts": len(artifacts), "artifact_bytes": sum(a["source_bytes"] for a in artifacts),
            "verdict_states": dict(sorted(Counter(r["verdict"] for r in observations).items()))},
        "gaps": {"missing_reported_sessions": missing_sessions, "duplicate_reported_session_positions": sum(n - 1 for n in sessions.values()),
                 "duplicate_run_positions": sum(n - 1 for n in runs.values()), "native_identity_attestation_available": False,
                 "canonical_full_hash_verification_unavailable_observations": len(observations)},
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
