"""Prospective, source-only preparation of the full opened HANNA cohort."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY = "matched_hanna_open120_v1"
ARMS = ("hbq", "ttcw14", "holistic", "compact", "oregon")
ENDPOINTS = ("grok", "sol")
RUNTIME_SHA = "45c7ad4ea2eee0d8acecd877d8a1f9f27854c2d537b53fd9b27a0da7956cbb68"
SOURCE_PINS = {
    "authority": ("cwr-hanna-successor-fresh88-freeze-v4/frozen-successor-contract.json", "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7", 200207),
    "authority_receipt": ("cwr-hanna-successor-fresh88-freeze-v4/freeze-receipt.json", "eaab5d605a720c86f00e40635e59e9a43bb9c58998a70d9e5bca3907c008f1b0", 5646),
    "work": ("cwr-hanna-fresh88-sol-v1-20260821-w4/fresh88-execution-contract.json", "6b3bfcd2407442c9997631cd38d7df7e01bd5017782feb62ad360840399b1726", 142408),
    "work_receipt": ("cwr-hanna-fresh88-sol-v1-20260821-w4/fresh88-execution-receipt.json", "bdb84a8243822ba95b40e08dd99220d4afd3d7899f2a90ab7f90ce630d35f7c2", 229),
    "prior_exposure": ("cwr-multisample-repeatability-v1-20260821-44518ab/frozen-run-contract.json", "5fb06e5a4775ecfe1cee10132e52100733c7e765e8eae9865374bb23f1addddd", 123496),
}
VALIDATION_PIN = ("ca5adea2288d9c01ddf3aeb0c6239ac2c550d26095a2c66a928d90511f4afb16", 65224)
DEPENDENCY_PINS = {
    "hbq-matched-ttcw-20261004/prepare.py": "c56c99d69ffbe053886661132bf680d02a7729038477a79a5f3f79316c29e685",
    "hbq-matched-mfa-v1/prepare.py": "7924ad115282402cfeb35b310e050e1a6411d3d2ab7cb43877ca38b380f9cac2",
    "hbq-matched-ttcw-20261004/validate_response.py": "a41915877b6f7e21a05f0b34d3c31c788f7f23070ab674ecfc514d93391e270e",
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def checked(path, pin, size=None):
    raw = Path(path).read_bytes()
    require(digest(raw) == pin and (size is None or len(raw) == size), "Frozen source/code bytes differ: " + str(path))
    return raw


def project_json(raw, specification):
    """Decode only explicitly selected fields; skipped targets are never decoded."""
    text, decoder = raw.decode("utf-8"), json.JSONDecoder()

    def white(i):
        while i < len(text) and text[i].isspace():
            i += 1
        return i

    def skip(i):
        i = white(i)
        if text[i] == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == '"':
                    return i + 1
                else:
                    i += 1
        elif text[i] in "[{":
            close = "]" if text[i] == "[" else "}"
            i += 1
            while True:
                i = white(i)
                if text[i] == close:
                    return i + 1
                if text[i] in ",:":
                    i += 1
                else:
                    i = skip(i)
        else:
            end = i
            while end < len(text) and text[end] not in ",]} \r\n\t":
                end += 1
            return end
        raise ValueError("Unterminated source JSON")

    def parse(i, spec):
        i = white(i)
        if spec is True:
            return decoder.raw_decode(text, i)
        if isinstance(spec, list):
            require(text[i] == "[", "Expected source metadata array")
            result, i = [], white(i + 1)
            while text[i] != "]":
                value, i = parse(i, spec[0])
                result.append(value)
                i = white(i)
                if text[i] == ",":
                    i = white(i + 1)
                else:
                    require(text[i] == "]", "Invalid source array separator")
            return result, i + 1
        require(text[i] == "{", "Expected source metadata object")
        result, seen, i = {}, set(), white(i + 1)
        while text[i] != "}":
            key, i = decoder.raw_decode(text, i)
            require(isinstance(key, str) and key not in seen, "Duplicate source metadata key")
            seen.add(key)
            i = white(i)
            require(text[i] == ":", "Invalid source metadata separator")
            i = white(i + 1)
            if key in spec:
                result[key], i = parse(i, spec[key])
            else:
                i = skip(i)
            i = white(i)
            if text[i] == ",":
                i = white(i + 1)
            else:
                require(text[i] == "}", "Invalid source object separator")
        require(set(result) == set(spec), "Required source metadata absent")
        return result, i + 1

    value, end = parse(0, specification)
    require(white(end) == len(text), "Trailing source JSON")
    return value


ROW_FIELDS = {k: True for k in ("item_id", "story_id", "model", "prompt_group_id", "story_sha256", "prompt_sha256", "external_input")}
VALIDATION_FIELDS = {k: True for k in ("item_id", "story_id", "model", "prompt_group_id", "partition", "status", "story", "prompt", "annotation_count", "source_binding_sha256")}


def source_item(original_id, story_id, model, group, source, prompt, origin):
    source.decode("utf-8")
    prompt.decode("utf-8")
    require(bool(source.strip()) and bool(prompt.strip()), "Empty source or originating prompt")
    require(group == "prompt-" + digest(prompt)[:16], "Originating prompt group commitment differs")
    opaque = "artifact-" + digest(canonical([STUDY, original_id, digest(source)]))[:24]
    return {"id": opaque, "original_id": original_id, "native_story_id": story_id,
            "model_role": model, "role": "human_source" if model == "Human" else "generated",
            "group": group, "origin": origin, "raw": source, "prompt": prompt,
            "sha256": digest(source), "prompt_sha256": digest(prompt), "bytes": len(source)}


def load_sources(documents, validation_path, *, pins=SOURCE_PINS, validation_pin=VALIDATION_PIN):
    raw = {name: checked(documents / rel, sha, size) for name, (rel, sha, size) in pins.items()}
    development = project_json(raw["authority"], {"selection": {"development": [ROW_FIELDS]}})["selection"]["development"]
    work = project_json(raw["work"], {"cells": [dict.fromkeys(("item_id", "artifact", "contexts", "task_contract", "external_input"), True)]})["cells"]
    require(len(development) == len(work) == 88 and len({r["item_id"] for r in development}) == 88, "Full Fresh88 membership differs")
    by_id = {r["item_id"]: r for r in development}
    require(set(by_id) == {r["item_id"] for r in work} and len({r["item_id"] for r in work}) == 88, "Authority/work identity membership differs")
    items, physical_pins = [], []
    for cell in work:
        row = by_id[cell["item_id"]]
        require(cell["external_input"] == row["external_input"] and len(cell["contexts"]) == 1, "Authority/work source descriptors differ")
        parts = {}
        for name, pin in (("source.md", cell["artifact"]), ("prompt.md", cell["contexts"][0]), ("task-contract.json", cell["task_contract"])):
            expected = row["external_input"][name]
            require(pin["sha256"] == expected["sha256"] and pin["bytes"] == expected["bytes"], "Physical input descriptor differs")
            path = Path(pin["path"]).resolve()
            expected_root = (documents / "cwr-human-reference-v3-d9038f1/inputs/development" / row["item_id"]).resolve()
            require(path == expected_root / name, "Source locator differs from retained development root")
            parts[name] = checked(path, pin["sha256"], pin["bytes"])
            physical_pins.append({"path": str(path), "sha256": pin["sha256"], "bytes": pin["bytes"]})
        require(digest(parts["source.md"]) == row["story_sha256"] and digest(parts["prompt.md"]) == row["prompt_sha256"], "Original source/context hash differs")
        items.append(source_item(row["item_id"], row["story_id"], row["model"], row["prompt_group_id"], parts["source.md"], parts["prompt.md"], "fresh88_open_development"))
    validation_raw = checked(validation_path, *validation_pin)
    validation = project_json(validation_raw, {"selected_items": [VALIDATION_FIELDS]})["selected_items"]
    require(len(validation) == 32, "Full open validation membership differs")
    for row in validation:
        require(row["partition"] == "validation" and row["status"] == "open" and row["annotation_count"] == 3
                and row["model"] != "Human", "Only existing open validation units are admitted")
        require(row["item_id"] == "item-" + digest(row["story_id"].encode())[:16], "Validation original identity differs")
        binding = {k: row[k] for k in ("prompt_group_id", "story_id", "model", "prompt", "story")}
        require(digest(canonical(binding).rstrip(b"\n")) == row["source_binding_sha256"], "Validation source binding differs")
        items.append(source_item(row["item_id"], row["story_id"], row["model"], row["prompt_group_id"], row["story"].encode("utf-8"), row["prompt"].encode("utf-8"), "fresh96_open_validation"))
    validate_cohort(items)
    exposure = project_json(raw["prior_exposure"], {"samples": [{"inputs": {"source.md": True, "prompt.md": True}}]})["samples"]
    source_overlap = {r["inputs"]["source.md"]["sha256"] for r in exposure} & {i["sha256"] for i in items if i["origin"] == "fresh88_open_development"}
    context_overlap = {r["inputs"]["prompt.md"]["sha256"] for r in exposure} & {i["prompt_sha256"] for i in items if i["origin"] == "fresh88_open_development"}
    require(len(exposure) == len(source_overlap) == 11 and len(context_overlap) == 10, "Prior native source exposure commitments differ")
    commitments = {name: {"path": str(documents / rel), "sha256": sha, "bytes": size} for name, (rel, sha, size) in pins.items()}
    commitments["validation"] = {"path": str(validation_path.resolve()), "sha256": validation_pin[0], "bytes": validation_pin[1]}
    return items, {"source_commitments": commitments, "physical_input_commitments": physical_pins,
                   "prior_exposure": {"census_e_exact_source_matches": len(source_overlap), "census_e_prompt_hashes": len(context_overlap)}}


def validate_cohort(items):
    require(len(items) == len({i["id"] for i in items}) == len({i["native_story_id"] for i in items}) == 120, "Full120 source identity membership differs")
    require(Counter(i["role"] for i in items) == Counter(generated=112, human_source=8), "Source role geometry differs")
    dev = [i for i in items if i["origin"] == "fresh88_open_development"]
    val = [i for i in items if i["origin"] == "fresh96_open_validation"]
    require(len(dev) == 88 and len(val) == 32 and Counter(i["model_role"] for i in dev) == Counter({m: 8 for m in {i["model_role"] for i in dev}}), "Opened source cohort balance differs")
    dg, vg = {i["group"] for i in dev}, {i["group"] for i in val}
    require((len(dg), len(vg), len(dg & vg), len(dg | vg)) == (40, 16, 1, 55), "Source prompt-group geometry differs")
    require(not {i["group"] for i in dev if i["role"] == "generated"} & vg, "Generated-source group separation differs")


def select_sentinels(items):
    selected, groups, models = [], set(), set()
    strata = [("human_source", "fresh88_open_development", 1), ("generated", "fresh88_open_development", 3), ("generated", "fresh96_open_validation", 2)]
    for role, origin, count in strata:
        candidates = sorted((i for i in items if i["role"] == role and i["origin"] == origin),
                            key=lambda i: digest(canonical([STUDY, "sentinel_source_metadata_v1", i["group"], i["sha256"], i["prompt_sha256"], i["model_role"]])))
        chosen = 0
        for item in candidates:
            if item["group"] in groups or item["model_role"] in models:
                continue
            selected.append(item["id"])
            groups.add(item["group"])
            models.add(item["model_role"])
            chosen += 1
            if chosen == count:
                break
        require(chosen == count, "Six source-group/role sentinel strata unavailable")
    return sorted(selected)


def task_contract(artifact_id, prompt):
    return {"contract_version": 1, "contract_id": "origin_prompt_v1", "artifact_id": artifact_id,
            "context": {"artifact_kind": "prose_fiction", "declared_scope": "complete short prose fiction", "completion_status": "complete",
                        "background": ["The separately supplied context is the exact originating writing prompt."],
                        "constraints": ["Evaluate the supplied complete story as a response to the originating writing prompt. Visible local defects remain assessable."],
                        "audience": ["general fiction reader"]}, "preferences": [], "priorities": [],
            "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story meaningfully respond to the supplied originating writing prompt?", "weight": 2.0,
                                "source": {"kind": "driving_prompt", "reference": "Originating writing prompt", "exact_excerpt": prompt},
                                "applies_to": ["whole artifact"], "rationale": "Non-gating prompt-specific relevance signal."}], "binding_requirements": []}


def read_runtime(path):
    raw = checked(path, RUNTIME_SHA)
    source = json.loads(raw)
    rt = source["runtime"]
    require(rt["model"] == "gpt-6.1-sol" and rt["reasoning"] == "high" and rt["timeout_seconds"] == 900
            and rt["workers"] == rt["attempts_per_logical_sample"] == 1 and rt["automatic_retries"] == 0,
            "Registered secondary runtime differs")
    files = {"private/source-runtime-manifest.json": raw}
    names = ("implementation/core.py", "implementation/runner.py", "implementation/codex_receipts.py", "implementation/schema_subset.py", "implementation/secondary-helper.py", "inputs/all_modules.yaml", "inputs/all_bundles.yaml")
    for name in names:
        pin = source["artifacts"][name]
        files[name] = checked(path.parent / name, pin["sha256"], pin["bytes"])
    for name in ("core.py", "runner.py", "codex_receipts.py"):
        require((REPO / "src/hbqrs" / name).read_bytes() == files["implementation/" + name], "Current offline runtime differs from frozen source")
    external = source["external_pins"]
    checked(Path(external["cli_path_local_only"]), external["cli_sha256"], external["cli_bytes"])
    require(Path(external["secondary_helper_path_local_only"]).read_bytes() == files["implementation/secondary-helper.py"], "Secondary helper differs")
    return source, files, load_module("hanna_frozen_subset", path.parent / "implementation/schema_subset.py")


def build(items, provenance, runtime_path, ttcw_tests):
    validate_cohort(items)
    runtime_source, files, subset = read_runtime(runtime_path)
    for relative, sha in DEPENDENCY_PINS.items():
        raw = checked(HERE.parent / relative, sha)
        files["implementation/" + relative.split("/")[0] + "-" + Path(relative).name] = raw
    ttcw = load_module("hanna_ttcw_prepare", HERE.parent / "hbq-matched-ttcw-20261004/prepare.py")
    mfa = load_module("hanna_mfa_prepare", HERE.parent / "hbq-matched-mfa-v1/prepare.py")
    tests_raw = checked(ttcw_tests, ttcw.PINS["tests"][1])
    test_payload = canonical(ttcw.adapted_tests(json.loads(tests_raw))).decode("utf-8")
    files["sources/ttcw-tests.json"] = tests_raw
    files["sources/ttcw-adapted-tests.json"] = test_payload.encode("utf-8")
    files["implementation/validate_response.py"] = checked(HERE.parent / "hbq-matched-ttcw-20261004/validate_response.py", DEPENDENCY_PINS["hbq-matched-ttcw-20261004/validate_response.py"])
    files["implementation/prepare.py"] = (HERE / "prepare.py").read_bytes()
    files["REGISTRATION.md"] = (HERE / "REGISTRATION.md").read_bytes()
    for name, path in {"schema/hbq_task_contract.schema.json": REPO / "schema/hbq_task_contract.schema.json",
                       "schema/hbq_judge_response.schema.json": REPO / "schema/hbq_judge_response.schema.json",
                       "schema/hbq_verdict.schema.json": REPO / "schema/hbq_verdict.schema.json",
                       "schema/hbq_score_report.schema.json": REPO / "schema/hbq_score_report.schema.json",
                       "schema/hbq_score_report.v2.schema.json": REPO / "schema/hbq_score_report.v2.schema.json",
                       "prompts/BINARY_EVALUATION_PROMPT.md": REPO / "prompts/judge/BINARY_EVALUATION_PROMPT.md",
                       "implementation/scoring_v2.py": REPO / "src/hbqrs/scoring_v2.py",
                       "implementation/paths.py": REPO / "src/hbqrs/paths.py"}.items():
        files[name] = path.read_bytes()
    assets = {}
    for arm in ARMS[1:]:
        prompt = (ttcw.HERE / "arms" / (arm + ".prompt.md")).read_bytes()
        schema = (ttcw.HERE / "arms" / (arm + ".schema.json")).read_bytes()
        files["arms/" + arm + ".prompt.md"] = prompt
        files["arms/" + arm + ".original.schema.json"] = schema
        assets[arm] = (prompt.decode("utf-8"), json.loads(schema))
    files["arm-definitions.json"] = (ttcw.HERE / "arm-definitions.json").read_bytes()
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import core, runner
    from jsonschema import Draft202012Validator
    modules = core.load_modules(runtime_path.parent / "inputs/all_modules.yaml")
    bundle = core.resolve_bundle(core.load_bundles(runtime_path.parent / "inputs/all_bundles.yaml"), "prose.short_form")
    base = core.compile_bundle(modules, bundle)
    base_ids = [r["question"]["id"] for r in core.compiled_questions(base)]
    require(len(base_ids) == 170 and base["counts"] == {"domain_questions": 135, "hard_gates": 0, "penalty_questions": 18, "supplemental_questions": 17}, "Canonical short_form bank differs")
    files["compiled/canonical.json"] = canonical(base)
    sentinel_ids = select_sentinels(items)
    by_id, prepared = {i["id"]: i for i in items}, {}

    def artifact(name, raw):
        files[name] = raw
        return {"path": name, "sha256": digest(raw), "bytes": len(raw)}

    for item in items:
        ident = item["id"]
        task = task_contract(ident, item["prompt"].decode("utf-8"))
        Draft202012Validator(json.loads(files["schema/hbq_task_contract.schema.json"])).validate(task)
        compiled = core.compile_bundle(modules, bundle, task_contract=task)
        questions = core.compiled_questions(compiled)
        ids = [q["question"]["id"] for q in questions]
        require(len(ids) == 171 and [q for q in ids if q in base_ids] == base_ids and len(set(ids) - set(base_ids)) == 1
                and compiled["counts"]["hard_gates"] == 0, "Exact canonical plus nongating relevance bank differs")
        projection = runner._task_contract_judge_context(task)
        context = json.dumps(projection, ensure_ascii=False, indent=2).encode("utf-8")
        prepared[ident] = {"task": task, "questions": questions, "projection": projection,
            "task_contract": artifact("contracts/" + ident + ".json", canonical(task)),
            "compiled": artifact("compiled/" + ident + ".json", canonical(compiled)),
            "task_context": artifact("contexts/" + digest(context) + ".json", context),
            "originating_prompt": artifact("origin-prompts/" + ident + ".txt", item["prompt"]),
            "source": artifact("inputs/" + ident + ".txt", item["raw"])}
    units = [{"artifact_id": item["id"], "arm": arm, "repeat": repeat}
             for repeat in range(3) for item in items if repeat == 0 or item["id"] in sentinel_ids for arm in ARMS]
    units.sort(key=lambda u: (u["repeat"], digest(canonical([STUDY, "dispatch_v1", u]))))
    requests, ordinals = [], Counter()
    for unit in units:
        ident, arm = unit["artifact_id"], unit["arm"]
        item, entry = by_id[ident], prepared[ident]
        context = files[entry["task_context"]["path"]].decode("utf-8")
        original = item["prompt"].decode("utf-8")
        text = item["raw"].decode("utf-8")
        packets = [(n // 8 + 1, entry["questions"][n:n + 8], runner._batch_response_schema([q["question"]["id"] for q in entry["questions"][n:n + 8]])) for n in range(0, 171, 8)] if arm == "hbq" else [(1, [], assets[arm][1])]
        for batch, questions, schema in packets:
            retained = artifact("retained-schemas/" + digest(canonical(schema)) + ".json", canonical(schema))
            portable = mfa.portable_schema(schema)
            subset.validate_schema(portable)
            emitted = artifact("schemas/" + digest(canonical(portable)) + ".json", canonical(portable))
            if arm == "hbq":
                # The shared renderer trims artifact/context tails. Substitute exact bytes after rendering.
                marker = "FROZEN_LITERAL_" + digest(canonical([ident, batch]))
                require(marker not in text and marker not in original, "Literal rendering marker collides")
                prompt = runner._render_prompt(binary_prompt=files["prompts/BINARY_EVALUATION_PROMPT.md"].decode("utf-8"),
                    artifact={"name": "Story", "text": marker + "_STORY"}, contexts=[{"name": "Originating writing prompt", "text": marker + "_PROMPT"}],
                    bundle_id="prose.short_form", artifact_id=ident, questions=questions, task_contract_context=entry["projection"])
                require(prompt.count(marker + "_STORY") == prompt.count(marker + "_PROMPT") == 1, "Literal rendering markers differ")
                prompt = prompt.replace(marker + "_STORY", text).replace(marker + "_PROMPT", original)
            else:
                prompt = assets[arm][0] + "\n## Frozen common task context\n\n" + context
                prompt += "\n## Originating writing prompt\n\n" + original + "\n## Story\n\n" + text + "\n"
                if arm == "ttcw14":
                    prompt += "\n## Original questions and interpretive definitions\n\n" + test_payload
            require(context in prompt and original in prompt and text in prompt, "Exact source/common context absent from prompt")
            prompt_pin = artifact("prompts/" + digest(prompt.encode("utf-8")) + ".txt", prompt.encode("utf-8"))
            condition = {**unit, "form": "complete_short_prose_fiction", "bundle_id": "prose.short_form", "batch": batch,
                "question_ids": [q["question"]["id"] for q in questions],
                "sources": [{"id": ident, "input_path": entry["source"]["path"], "sha256": item["sha256"], "bytes": item["bytes"]}],
                "task_context": entry["task_context"], "originating_prompt": entry["originating_prompt"],
                "task_contract_path": entry["task_contract"]["path"], "task_contract_sha256": entry["task_contract"]["sha256"],
                "compiled_path": entry["compiled"]["path"], "compiled_sha256": entry["compiled"]["sha256"],
                "prompt_path": prompt_pin["path"], "prompt_sha256": prompt_pin["sha256"], "prompt_bytes": prompt_pin["bytes"],
                "schema_path": emitted["path"], "schema_sha256": emitted["sha256"], "schema_bytes": emitted["bytes"],
                "retained_schema_path": retained["path"], "retained_schema_sha256": retained["sha256"]}
            logical = digest(canonical(condition))
            endpoints = ENDPOINTS if int(logical[-1], 16) % 2 == 0 else ENDPOINTS[::-1]
            for endpoint in endpoints:
                ordinals[endpoint] += 1
                row = {**condition, "logical_sample_id": logical, "endpoint": endpoint, "endpoint_ordinal": ordinals[endpoint], "ordinal": len(requests) + 1}
                row["request_sha256"] = digest(canonical(row))
                requests.append(row)
    selection = [{k: i[k] for k in ("id", "original_id", "native_story_id", "model_role", "role", "group", "origin", "sha256", "prompt_sha256", "bytes")} for i in sorted(items, key=lambda i: i["id"])]
    files["private/source-provenance.json"] = canonical({**provenance, "items": selection, "sentinel_ids": sentinel_ids})
    counts = {"texts": 120, "generated": 112, "human_source": 8, "prompt_groups": 55, "development_validation_shared_groups": 1,
        "sentinels": 6, "cycles": 3, "story_passes_per_endpoint": 132, "canonical_leaves": 170, "dynamic_relevance_leaves": 1,
        "full_leaves_per_pass": 171, "packets_per_pass": 22, "packet_size": 8,
        "initial_requests_per_endpoint": 3120, "repeat_requests_per_endpoint": 312,
        "requests_per_endpoint": 3432, "requests_total": 6864,
        "by_arm_per_endpoint": {"hbq": 2904, "ttcw14": 132, "holistic": 132, "compact": 132, "oregon": 132},
        "initial_hbq_positions_per_endpoint": 20520, "all_hbq_positions_per_endpoint": 22572}
    require(len(requests) == 6864 and all(dict(Counter(r["arm"] for r in requests if r["endpoint"] == e)) == counts["by_arm_per_endpoint"] for e in ENDPOINTS), "Prospective matched geometry differs")
    manifest = {"schema_version": 1, "study_id": STUDY, "evidence_class": "already_open_uncertain_credential_human_reference_preparation",
        "execution_authority": False, "labels_read": False, "labels_released": False, "provider_calls_made": 0,
        "counts": counts, "requests": requests, "sentinel_ids": sentinel_ids, "source_membership_sha256": digest(canonical(selection)),
        "source_pins": provenance["source_commitments"], "generation_manifest_file_sha256": RUNTIME_SHA,
        "sentinel_policy": "source metadata hash; one Human-source, three Fresh88-generated, two validation-generated; six distinct prompt groups and model roles; no outcome values",
        "order_policy": "repeat phases0/1/2; salted unit dispatch shuffle; fixed canonical packet/question order; no causal question-order experiment",
        "prior_exposure": {"census_e_exact_source_matches": 11, "census_e_prompt_hashes": 10, "fresh88_generated_validation_group_overlap": 0,
                           "already_open_source": True, "certified_unused_confirmation": False, "historical_source_selection": "retained historical membership; not a newly outcome-blind source sample"},
        "human_gate": {"required_verified_terminal_requests": 6864, "requires_explicit_release": True, "release_granted": False,
                       "unattempted_blocks_release": True, "failed_and_unadmitted_never_votes": True},
        "runtime": {"sol": {"model": "gpt-6.1-sol", "reasoning": "high", "provider": "codex", "account_identity_sha256": runtime_source["runtime"]["account_identity_sha256"],
                            "secondary_home_sha256": runtime_source["runtime"]["codex_home_sha256"], "codex_receipt_policy": "codex_native_rollout_v1", "live_binding_required": True},
                    "grok": {"model": "grok-4.7", "reasoning": "high", "provider": "grok", "route": "grok-build-grok-4.7", "reviewed_gv5_exact_route_binding_required": True,
                             "zero_charge_required": True, "tools_allowed": False, "live_binding_required": True},
                    "timeout_seconds": 900, "workers_initially": 1, "batch_attempts": 1, "automatic_retries": 0,
                    "native_defaults": True, "temperature_seed_control_supported": False, "no_ambiguous_resend": True, "collection_adapter_required": True},
        "external_pins": runtime_source["external_pins"],
        "admission": {"implementation_path": "implementation/validate_response.py", "interface": "semantic_validate(arm,response,request,source_texts,subset,context,schema)",
                      "context_argument": "Exact decoded task_context plus newline plus exact decoded originating_prompt", "schema_argument": "Frozen portable request schema for every arm"},
        "scoring": {"contract": "strict full171 position import; exact per-source task/compiled contracts; no incomplete/unadmitted scalar",
                    "score_interface": "hbqrs.scoring_v2.score_bundle(admission_policy='strict_import_v1')",
                    "report_version": 2, "candidate": None,
                    "comparators": {"ttcw14": "assessed YES fraction with assessed/14 coverage; no partial full score", "holistic": "native overall1–7", "compact": "independent native overall1–5; dimension mean diagnostic only", "oregon": "exact six-trait sum6–36"},
                    "human_alignment_claim": False, "training": False, "optimization": False, "expert_generalization_claim": False},
        "disclosure": {"destinations": ["OpenAI ChatGPT subscription via designated secondary native Codex exec", "reviewed zero-charge Grok native route"],
                       "outbound": "Exact literal source story, exact originating prompt, identical pretty task context, arm instructions/rubric/questions and portable response schema",
                       "excluded": ["human ratings", "human targets", "generator/model roles", "original source identifiers", "historical quartiles/ranks"],
                       "transmission_prompt_bytes_total": sum(r["prompt_bytes"] for r in requests)},
        "artifacts": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}}
    manifest["manifest_content_sha256"] = digest(canonical(manifest))
    files["manifest.json"] = canonical(manifest)
    return manifest, files


def output_preflight(output, inputs):
    output = output.resolve()
    require(not output.exists(), "Output must be fresh and nonexistent, including dry-run")
    require(not output.is_relative_to(REPO) and not REPO.is_relative_to(output), "Private freeze must be outside repository")
    for path in inputs:
        path = path.resolve()
        require(not output.is_relative_to(path) and not path.is_relative_to(output), "Output overlaps retained input")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents-root", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--ttcw-tests", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    validation = HERE.parent / "hbq-human-alignment-hanna96-fresh-split-v1/manifest.json"
    protected = [args.runtime_manifest.parent, args.ttcw_tests, validation, args.documents_root / "cwr-human-reference-v3-d9038f1"]
    protected.extend((args.documents_root / rel).parent for rel, _sha, _size in SOURCE_PINS.values())
    output_preflight(args.output_root, protected)
    items, provenance = load_sources(args.documents_root, validation)
    manifest, files = build(items, provenance, args.runtime_manifest, args.ttcw_tests)
    if not args.dry_run:
        args.output_root.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            path = args.output_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
    print(json.dumps({"state": "dry_run_without_contact" if args.dry_run else "prepared_without_contact", "manifest_sha256": digest(files["manifest.json"]),
                      "counts": manifest["counts"], "source_membership_sha256": manifest["source_membership_sha256"],
                      "artifact_count": len(files), "execution_authority": False, "labels_read": False, "provider_calls_made": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
