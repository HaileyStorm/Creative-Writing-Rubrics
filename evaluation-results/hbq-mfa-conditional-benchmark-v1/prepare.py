"""Freeze requests for the conditional MFA benchmark; preparation never authorizes execution."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY = "mfa_conditional_outcome_blind_benchmark_v1"
ENDPOINTS = ("grok", "sol")
ARMS = ("hbq", "holistic", "compact", "pairwise")
CANARY = HERE.parent / "hbq-matched-mfa-v1"
CANARY_PREPARE_SHA = "7924ad115282402cfeb35b310e050e1a6411d3d2ab7cb43877ca38b380f9cac2"
CANARY_EXTRACT_SHA = "e6da4d37b88053226928feecb9080013ded2a47f2d7d3b3980ce434f69ba0915"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract = load_module("mfa_conditional_extract", HERE / "extract.py")
canonical, sha, require = extract.canonical, extract.sha, extract.require


def canary_helpers():
    extract.checked(CANARY / "prepare.py", CANARY_PREPARE_SHA)
    extract.checked(CANARY / "extract.py", CANARY_EXTRACT_SHA)
    return load_module("mfa_conditional_canary_helpers", CANARY / "prepare.py")


def request_units(selection):
    units = []
    for repeat in (0, 1, 2):
        for text in selection["texts"]:
            if repeat == 0 or text["id"] in selection["bank_sentinel_ids"]:
                for arm in ARMS[:-1]:
                    units.append({"arm": arm, "repeat": repeat, "artifact_id": text["id"]})
        for pair in selection["pairs"]:
            if repeat == 0 or pair["pair_id"] in selection["pair_sentinel_ids"]:
                for orientation in ("AB", "BA"):
                    units.append({"arm": "pairwise", "repeat": repeat, "artifact_id": pair["pair_id"],
                                  "pair_id": pair["pair_id"], "orientation": orientation})
    return sorted(units, key=lambda u: (u["repeat"], sha(canonical([STUDY, u]))))


def read_extraction(root, selection):
    raw = extract.within(root, "extraction.json").read_bytes()
    receipt = json.loads(raw)
    policy, _ = extract.profile()
    require(receipt["policy"] == STUDY and receipt["selection_sha256"] == selection["selection_sha256"]
            and receipt["source_pins"] == policy["source_pins"] and receipt["labels_released"] is False,
            "Conditional extraction binding differs")
    for name, pin in receipt["artifacts"].items():
        value = extract.checked(extract.within(root, name), pin["sha256"])
        require(len(value) == pin["bytes"], "Extraction artifact length differs")
    require(extract.within(root, "selection.json").read_bytes() == canonical(selection)
            and extract.within(root, "implementation/extract.py").read_bytes() == (HERE / "extract.py").read_bytes(),
            "Extraction selection or implementation differs")
    texts = {}
    for item in selection["texts"]:
        value = extract.checked(extract.within(root, "inputs/" + item["sha256"] + ".txt"), item["sha256"])
        require(len(value) == item["bytes"], "Extracted candidate length differs")
        texts[item["id"]] = value
    return texts, sha(raw)


def build(selection, metadata_files, secondary_helper, cli, tools_root, *, texts=None, extraction_sha=None):
    policy, policy_raw = extract.profile()
    helper = canary_helpers()
    require(selection["policy"] == STUDY and selection["partition"] == "confirmation"
            and selection["primary_repeat"] == 0 and len(selection["planned_ballots"]) == 3276,
            "Only the pinned conditional cohort is supported")
    paths = {"registry/all_modules.yaml": REPO / "registry/all_modules.yaml",
             "bundles/all_bundles.yaml": REPO / "bundles/all_bundles.yaml",
             "prompts/BINARY_EVALUATION_PROMPT.md": REPO / "prompts/judge/BINARY_EVALUATION_PROMPT.md",
             "implementation/schema_subset.py": tools_root / "model_work_queue/adapters/json_schema_subset.py",
             "implementation/grok_exec.py": tools_root / "model_work_queue/adapters/grok_exec.py",
             "implementation/secondary-helper.py": secondary_helper,
             "implementation/prepare.py": HERE / "prepare.py", "implementation/extract.py": HERE / "extract.py",
             "implementation/canary-prepare.py": CANARY / "prepare.py",
             "implementation/canary-extract.py": CANARY / "extract.py",
             "implementation/selective-reader.py": HERE.parent / "hbq-matched-hanna-20261004/prepare.py",
             "implementation/validate_response.py": CANARY / "validate_response.py",
             "candidate-mechanism-profile.json": CANARY / "ladder-candidate-profile.json"}
    for name in ("core", "runner", "scoring_v2", "codex_receipts", "ladder_uncertainty", "decision_readiness"):
        paths["implementation/" + name + ".py"] = REPO / "src/hbqrs" / (name + ".py")
    for name in ("hbq_task_contract", "hbq_judge_response", "hbq_verdict"):
        paths["schema/" + name + ".schema.json"] = REPO / "schema" / (name + ".schema.json")
    for arm in ARMS[1:]:
        paths[f"arms/{arm}.prompt.md"] = CANARY / f"arms/{arm}.prompt.md"
        paths[f"arms/{arm}.schema.json"] = CANARY / f"arms/{arm}.schema.json"
    files = {name: path.read_bytes() for name, path in paths.items()}
    files["membership-profile.json"] = policy_raw
    mechanism = json.loads(files["candidate-mechanism-profile.json"])
    # The prospective mechanism pins are checked before importing any scoring module.
    for relative, digest in mechanism["source_files_sha256"].items():
        extract.checked(REPO / relative, digest)
    settings = helper.helper_settings(files["implementation/secondary-helper.py"])
    require(settings["CLI"] == cli.resolve(), "CLI differs from secondary helper")
    subset = load_module("mfa_conditional_schema_subset", paths["implementation/schema_subset.py"])
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import core, runner
    from jsonschema import Draft202012Validator
    modules = core.load_modules(paths["registry/all_modules.yaml"])
    bundle = core.resolve_bundle(core.load_bundles(paths["bundles/all_bundles.yaml"]), "prose.short_form")
    compiled = core.compile_bundle(modules, bundle)
    questions = core.compiled_questions(compiled)
    require(len(questions) == 170 and len({q["question"]["id"] for q in questions}) == 170
            and compiled["counts"] == {"domain_questions": 135, "hard_gates": 0,
                                       "penalty_questions": 18, "supplemental_questions": 17},
            "Canonical short-form bank differs")
    files["compiled.json"] = canonical(compiled)
    files["selection.json"] = canonical(selection)
    files["context.txt"] = helper.CONTEXT.encode("utf-8")
    for name, raw in metadata_files.items():
        if name not in ("private-metadata.json", "private-membership.json", "membership-profile.json"):
            files["metadata-commitments/" + name] = raw
    schemas = {arm: json.loads(files[f"arms/{arm}.schema.json"]) for arm in ARMS[1:]}
    for schema in schemas.values():
        subset.validate_schema(schema)
    task_schema = json.loads(files["schema/hbq_task_contract.schema.json"])
    by_id = {t["id"]: t for t in selection["texts"]}
    pair_by_id = {p["pair_id"]: p for p in selection["pairs"]}
    if texts is not None:
        require(set(texts) == set(by_id) and all(sha(raw) == by_id[key]["sha256"]
                and len(raw) == by_id[key]["bytes"] for key, raw in texts.items()), "Extracted input inventory differs")
    requests, ordinal = [], Counter()
    common_projection = None
    for unit in request_units(selection):
        arm = unit["arm"]
        if arm == "pairwise":
            pair = pair_by_id[unit["pair_id"]]
            ids = ["mfa-" + h for h in pair["excerpt_hashes"]]
            if unit["orientation"] == "BA":
                ids.reverse()
            sources = [{**by_id[i], "input_path": "inputs/" + by_id[i]["sha256"] + ".txt", "side": side}
                       for i, side in zip(ids, "AB")]
            task = helper.contract(unit["pair_id"])
            packets = [(1, [], schemas[arm])]
        else:
            artifact_id = unit["artifact_id"]
            sources = [{**by_id[artifact_id], "input_path": "inputs/" + by_id[artifact_id]["sha256"] + ".txt"}]
            task = helper.contract(artifact_id)
            require(core.compile_bundle(modules, bundle, task_contract=task)["counts"] == compiled["counts"],
                    "Task contract changes canonical bank")
            packets = [(n // 8 + 1, questions[n:n + 8], runner._batch_response_schema(
                [q["question"]["id"] for q in questions[n:n + 8]])) for n in range(0, 170, 8)] if arm == "hbq" else [(1, [], schemas[arm])]
        Draft202012Validator(task_schema).validate(task)
        task_path = f"contracts/{unit['artifact_id']}.json"
        files[task_path] = canonical(task)
        projection = runner._task_contract_judge_context(task)
        rendered_context = json.dumps(projection, ensure_ascii=False, indent=2).encode("utf-8")
        if common_projection is None:
            common_projection = rendered_context
        require(rendered_context == common_projection, "Cross-arm task-context projections differ")
        files["task-context.txt"] = rendered_context
        files["evidence-context.txt"] = rendered_context + b"\n" + files["context.txt"]
        for batch, packet, schema in packets:
            retained_raw = canonical(schema)
            retained_sha = sha(retained_raw)
            files["retained-schemas/" + retained_sha + ".json"] = retained_raw
            portable = helper.portable_schema(schema)
            schema_raw = canonical(portable)
            subset.validate_schema(portable)
            schema_path = "schemas/" + sha(schema_raw) + ".json"
            files[schema_path] = schema_raw
            condition = {**unit, "batch": batch, "question_ids": [q["question"]["id"] for q in packet],
                         "sources": sources, "bundle_id": "prose.short_form", "task": "quality",
                         "partition": "confirmation", "primary": unit["repeat"] == 0,
                         "schema_path": schema_path, "schema_sha256": sha(schema_raw), "schema_bytes": len(schema_raw),
                         "retained_schema_sha256": retained_sha, "task_contract_path": task_path,
                         "task_contract_sha256": sha(files[task_path]), "context_path": "evidence-context.txt",
                         "context_sha256": sha(files["evidence-context.txt"]),
                         "task_context_path": "task-context.txt", "task_context_sha256": sha(rendered_context)}
            if texts is not None:
                if arm == "hbq":
                    prompt = runner._render_prompt(binary_prompt=files["prompts/BINARY_EVALUATION_PROMPT.md"].decode("utf-8"),
                        artifact={"name": "Excerpt", "text": texts[unit["artifact_id"]].decode("utf-8")},
                        contexts=[{"name": "Quality excerpt scope", "text": helper.CONTEXT}], bundle_id="prose.short_form",
                        artifact_id=unit["artifact_id"], questions=packet, task_contract_context=projection)
                else:
                    prompt = files[f"arms/{arm}.prompt.md"].decode("utf-8") + "\n## Task contract context\n\n" + rendered_context.decode("utf-8")
                    prompt += "\n## Common excerpt context\n\n" + helper.CONTEXT
                    for source in sources:
                        prompt += "\n## Excerpt" + (" " + source["side"] if arm == "pairwise" else "") + "\n\n" + texts[source["id"]].decode("utf-8") + "\n"
                require(rendered_context.decode("utf-8") in prompt and helper.CONTEXT in prompt,
                        "Declared exact task/context bytes absent from outbound prompt")
                prompt_raw = prompt.encode("utf-8")
                prompt_path = "prompts/" + sha(prompt_raw) + ".txt"
                files[prompt_path] = prompt_raw
                condition.update(prompt_path=prompt_path, prompt_sha256=sha(prompt_raw), prompt_bytes=len(prompt_raw))
            logical_id = sha(canonical(condition))
            endpoints = ENDPOINTS if int(logical_id[-1], 16) % 2 == 0 else ENDPOINTS[::-1]
            for endpoint in endpoints:
                ordinal[endpoint] += 1
                request = {**condition, "logical_sample_id": logical_id, "endpoint": endpoint,
                           "endpoint_ordinal": ordinal[endpoint], "ordinal": len(requests) + 1}
                request["request_sha256"] = sha(canonical(request))
                requests.append(request)
    if texts is not None:
        files.update({"inputs/" + by_id[key]["sha256"] + ".txt": raw for key, raw in texts.items()})
    counts = {**extract.summary(selection), "canonical_leaves": 170, "canonical_packets": 22, "packet_size": 8,
              "requests_total": len(requests), "requests_per_endpoint": dict(ordinal), "bank_sentinels": 2,
              "pair_sentinels": 2, "primary_repeat": 0, "diagnostic_repeats": [1, 2],
              "by_arm_per_endpoint": dict(Counter(r["arm"] for r in requests if r["endpoint"] == "sol")),
              "initial_requests_per_endpoint": sum(r["endpoint"] == "sol" and r["repeat"] == 0 for r in requests),
              "diagnostic_requests_per_endpoint": sum(r["endpoint"] == "sol" and r["repeat"] > 0 for r in requests)}
    require(len(requests) == policy["expected"]["requests_total"]
            and set(ordinal.values()) == {policy["expected"]["requests_per_endpoint"]}, "Request geometry differs")
    manifest = {"schema_version": 1, "study_id": STUDY,
        "state": "frozen_conditional_benchmark_preparation" if texts is not None else "metadata_only_prospective_plan",
        "execution_authority": False, "execution_disabled": True,
        "collector_binding": {"status": "UNIMPLEMENTED", "reason": "Canary development policy/cohort guards are not this benchmark contract",
            "next_scope": "separate source-bound collector for this manifest, 5170/endpoint, exact task/context and strict admission"},
        "labels_read": False, "provider_calls_made": 0, "counts": counts, "selection_sha256": selection["selection_sha256"],
        "source_pins": policy["source_pins"], "membership_profile_sha256": sha(policy_raw),
        "candidate_mechanism_profile_sha256": policy["candidate_profile_sha256"], "extraction_sha256": extraction_sha,
        "requests": requests, "context": {"path": "evidence-context.txt", "sha256": sha(files["evidence-context.txt"])},
        "outbound_payload": "Exact selected candidate excerpts, shared excerpt scope, pretty task projection and arm rubric; no Preference, win, Reason, original reference, panel, condition, rater or writer identities",
        "implementation": {"prepare_sha256": sha(files["implementation/prepare.py"]),
                           "extract_sha256": sha(files["implementation/extract.py"]),
                           "semantic_validator_sha256": sha(files["implementation/validate_response.py"])},
        "runtime": {"sol": {"model": "gpt-6.1-sol", "reasoning": "high", "provider": "codex",
                            "account_identity_sha256": helper.SECONDARY_ACCOUNT_SHA256,
                            "secondary_home_sha256": sha(str(settings["COLLECTION_HOME"]).encode()),
                            "account": "designated secondary subscription; native identity unverified", "codex_receipt_policy": "codex_native_rollout_v1"},
                    "grok": {"model": "grok-4.7", "reasoning": "high", "provider": "grok",
                             "reviewed_runtime_route_binding_required": True},
                    "batch_attempts": 1, "workers_initially": 1, "automatic_retries": 0, "timeout_seconds": 900,
                    "strict_ai_prefix": False, "sampler": "native defaults; unsupported temperature/seed",
                    "native_execution_verified": False},
        "external_pins": {"secondary_helper_sha256": sha(files["implementation/secondary-helper.py"]),
                          "secondary_helper_path_local_only": str(secondary_helper.resolve()),
                          "cli_sha256": sha(cli.read_bytes()), "cli_path_local_only": str(cli.resolve())},
        "scoring": {"baseline": "historical_v1 after strict_import_v1 admission",
                    "candidate": "uncertainty_preserving_ladder_v1 projected from same admitted raw bank",
                    "candidate_promoted": False, "full_bank_required": True, "human_alignment_claim": False,
                    "fine_model_variant": "UNKNOWN", "unused_data_certified": "UNKNOWN", "fresh_confirmation_claim": False},
        "artifacts": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}}
    manifest["manifest_content_sha256"] = sha(canonical(manifest))
    return manifest, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("metadata-root", "partition-root", "audit-root", "secondary-helper", "codex-cli", "tools-root", "output-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--extraction-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    require(not args.dry_run or args.extraction_root is None, "Dry-run must not read extracted prose")
    selection, input_files = extract.load_inputs(args.metadata_root, args.partition_root, args.audit_root)
    inputs = [args.metadata_root, args.partition_root, args.audit_root, args.secondary_helper, args.codex_cli, args.tools_root]
    if args.extraction_root:
        inputs.append(args.extraction_root)
    output = extract.private_output(args.output_root, inputs)
    texts, extraction_sha = read_extraction(args.extraction_root, selection) if args.extraction_root else (None, None)
    require(args.dry_run or texts is not None, "Actual text freeze requires reviewed extraction")
    manifest, files = build(selection, input_files, args.secondary_helper, args.codex_cli, args.tools_root,
                            texts=texts, extraction_sha=extraction_sha)
    raw = canonical(manifest)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in files.items():
            extract.write_new(output / name, value)
        extract.write_new(output / "manifest.json", raw)
    print(json.dumps({"dry_run": args.dry_run, "counts": manifest["counts"], "manifest_sha256": sha(raw),
                      "source_prose_read": texts is not None, "labels_read": False, "provider_calls": 0,
                      "execution_disabled": True, "membership_profile_sha256": manifest["membership_profile_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
