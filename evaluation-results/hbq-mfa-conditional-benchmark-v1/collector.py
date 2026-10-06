"""Named native execution descendant of the outcome-blind conditional benchmark."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
from threading import Event
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "mfa_conditional_native_once_v1"
SETTLED = {"accepted", "semantic_rejected"}
FAILED = {"unadmitted_no_resend", "ambiguous", "definitely_not_contacted", "unavailable"}
ROUTE_SHA = "4b4de96df75260b99ea4bb7c05fe7925b22c6a6a898cea404d0bb447b41d54b7"
CUTOFF = datetime(2026, 10, 16, 5, 40, tzinfo=timezone.utc)
MARGIN = 960
PREPARE_SHA = "b9e657dfd28fc6b05a30eecb2c2ab8a927d470f2c36441c8493f24bf838de8b6"
EXTRACT_SHA = "b0244c81bfa320798142336b8df2a81f834669f8baf31538f4024729c1e42039"
PROFILE_SHA = "50dbd17f6b9215c92e8a10fc93ff9a325f409bb9a063ddea0493862fa496054f"
VALIDATOR_SHA = "cfc30b376a25bb13ac3824da201ae066daffd2aad8006aa6404a53dbfa310470"
NATIVE_FOUNDATION_SHA = "a4a7073ff5d24875fcc1d866b727792ebdafa4ad70df327691a72e17cbcacc94"


def digest(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


for name, pin in (("prepare.py", PREPARE_SHA), ("extract.py", EXTRACT_SHA), ("membership-profile.json", PROFILE_SHA)):
    require(digest((HERE / name).read_bytes()) == pin, "Reviewed preparation bytes differ")
prepare = load_module("mfa_conditional_collection_prepare", HERE / "prepare.py")
canonical, sha = prepare.canonical, prepare.sha


def record(path, value):
    prepare.extract.write_new(path, canonical(value))


def within(root, relative):
    return prepare.extract.within(root, relative)


def pinned(root, relative, metadata):
    raw = within(root, relative).read_bytes()
    require(sha(raw) == metadata["sha256"] and len(raw) == metadata["bytes"], "Frozen artifact differs")
    return raw


def validate_row(root, manifest, row, subset, cache):
    require(sha(canonical({k: v for k, v in row.items() if k != "request_sha256"})) == row["request_sha256"]
            and row["partition"] == "confirmation" and row["bundle_id"] == "prose.short_form"
            and row["task"] == "quality" and row["primary"] == (row["repeat"] == 0), "Request commitment differs")
    for kind in ("prompt", "schema"):
        raw = cache[row[kind + "_path"]]
        require(sha(raw) == row[kind + "_sha256"] and len(raw) == row[kind + "_bytes"], "Request bytes differ")
    if row["schema_path"] not in subset["checked"]:
        subset["module"].validate_schema(json.loads(cache[row["schema_path"]]))
        subset["checked"].add(row["schema_path"])
    context, task_context = cache[row["context_path"]], cache[row["task_context_path"]]
    require(row["context_path"] == "evidence-context.txt" and row["task_context_path"] == "task-context.txt"
            and sha(context) == row["context_sha256"] and sha(task_context) == row["task_context_sha256"]
            and context == task_context + b"\n" + cache["context.txt"]
            and task_context in cache[row["prompt_path"]] and cache["context.txt"] in cache[row["prompt_path"]],
            "Exact declared task/context bytes differ or are absent from prompt")
    require(sha(cache[row["task_contract_path"]]) == row["task_contract_sha256"], "Task contract differs")
    for source in row["sources"]:
        value = cache[source["input_path"]]
        require(sha(value) == source["sha256"] and len(value) == source["bytes"], "Committed candidate differs")


def load_manifest(path, expected_sha, tools, extraction_receipt):
    root, raw = path.resolve().parent, path.read_bytes()
    require(sha(raw) == expected_sha, "Exact manifest pin differs")
    manifest = json.loads(raw)
    require(sha(canonical({k: v for k, v in manifest.items() if k != "manifest_content_sha256"}))
            == manifest["manifest_content_sha256"], "Manifest content commitment differs")
    require(manifest["study_id"] == prepare.STUDY and manifest["state"] == "frozen_conditional_benchmark_preparation"
            and manifest["execution_disabled"] is True and manifest["execution_authority"] is False
            and manifest["labels_read"] is False, "Only immutable conditional preparation is supported")
    require(manifest["runtime"]["timeout_seconds"] == 900 and manifest["runtime"]["batch_attempts"] == 1
            and manifest["runtime"]["automatic_retries"] == 0, "One-attempt runtime differs")
    cache = {name: pinned(root, name, meta) for name, meta in manifest["artifacts"].items()}
    require(sha(cache["membership-profile.json"]) == PROFILE_SHA == manifest["membership_profile_sha256"], "Membership profile differs")
    selection = json.loads(cache["selection.json"])
    require(selection["selection_sha256"] == manifest["selection_sha256"]
            and sha(canonical({k: v for k, v in selection.items() if k != "selection_sha256"})) == manifest["selection_sha256"],
            "Selection commitment differs")
    counts = prepare.extract.summary(selection)
    require(all(counts[k] == v for k, v in {"targets": 30, "fine_targets": 18, "unique_texts": 199,
        "pairs": 145, "evaluation_units": 289, "metadata_rows": 3276, "lay_only_pairs": 1}.items())
        and len({b["ballot_id"] for b in selection["planned_ballots"]}) == 3276
        and all(b["source_field"] == "Preference" for b in selection["planned_ballots"]), "Cohort membership differs")
    require(selection["partition"] == "confirmation" and all(u["partition"] == "confirmation" for u in selection["evaluation_units"]),
            "Cohort partition differs")
    require(extraction_receipt.name == "extraction.json" and sha(extraction_receipt.read_bytes()) == manifest["extraction_sha256"],
            "Exact extraction receipt differs")
    _, extraction_sha = prepare.read_extraction(extraction_receipt.resolve().parent, selection)
    require(extraction_sha == manifest["extraction_sha256"], "Extraction binding differs")
    current = {"implementation/prepare.py": HERE / "prepare.py", "implementation/extract.py": HERE / "extract.py",
               "membership-profile.json": HERE / "membership-profile.json",
               "implementation/validate_response.py": prepare.CANARY / "validate_response.py",
               "implementation/schema_subset.py": tools / "model_work_queue/adapters/json_schema_subset.py",
               "implementation/grok_exec.py": tools / "model_work_queue/adapters/grok_exec.py",
               "implementation/secondary-helper.py": Path(manifest["external_pins"]["secondary_helper_path_local_only"])}
    for name in ("runner", "codex_receipts", "core", "scoring_v2", "ladder_uncertainty", "decision_readiness"):
        current["implementation/" + name + ".py"] = REPO / "src/hbqrs" / (name + ".py")
    for retained, local in current.items():
        require(local.read_bytes() == cache[retained], "Frozen runtime implementation differs")
    require(sha(cache["implementation/validate_response.py"]) == VALIDATOR_SHA
            and sha((prepare.CANARY / "collector.py").read_bytes()) == NATIVE_FOUNDATION_SHA
            and sha(Path(manifest["external_pins"]["cli_path_local_only"]).read_bytes()) == manifest["external_pins"]["cli_sha256"],
            "Native/admission foundation or CLI differs")
    settings = prepare.canary_helpers().helper_settings(cache["implementation/secondary-helper.py"])
    require(settings["CLI"] == Path(manifest["external_pins"]["cli_path_local_only"]).resolve()
            and sha(str(settings["COLLECTION_HOME"]).encode()) == manifest["runtime"]["sol"]["secondary_home_sha256"],
            "Secondary home/CLI static binding differs")
    subset = prepare.load_module("conditional_collection_subset", root / "implementation/schema_subset.py")
    validator = prepare.load_module("conditional_collection_validator", root / "implementation/validate_response.py")
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import core
    questions = core.compiled_questions(json.loads(cache["compiled.json"]))
    question_ids = [q["question"]["id"] for q in questions]
    require(len(question_ids) == len(set(question_ids)) == 170, "Full canonical bank commitment differs")
    schema_state = {"module": subset, "checked": set()}
    by_endpoint = {}
    for endpoint in prepare.ENDPOINTS:
        rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
        require(len(rows) == 5170 and [r["endpoint_ordinal"] for r in rows] == list(range(1, 5171))
                and len({r["logical_sample_id"] for r in rows}) == 5170, "Endpoint denominator/identity differs")
        for row in rows:
            validate_row(root, manifest, row, schema_state, cache)
            require(row["question_ids"] == (question_ids[(row["batch"] - 1) * 8:row["batch"] * 8]
                    if row["arm"] == "hbq" else []), "Exact canonical packet question membership differs")
        expected = {(u["arm"], u["artifact_id"], u["repeat"], u.get("orientation"), batch)
                    for u in prepare.request_units(selection) for batch in (range(1, 23) if u["arm"] == "hbq" else (1,))}
        actual = {(r["arm"], r["artifact_id"], r["repeat"], r.get("orientation"), r["batch"]) for r in rows}
        require(actual == expected and len(actual) == len(rows), "Registered initial/repeat packet membership differs")
        by_endpoint[endpoint] = {r["logical_sample_id"]: r for r in rows}
    require(set(by_endpoint["sol"]) == set(by_endpoint["grok"]), "Matched endpoint logical identities differ")
    return manifest, root, subset, validator


def reviewed_route(route_root, expected_sha, classification):
    require(expected_sha == ROUTE_SHA, "This execution descendant requires its explicit reviewed renewal route")
    route = next(r for r in json.loads((route_root / "routes.json").read_bytes())["routes"] if r["name"] == "grok-build-grok-4.7")
    require(sha(canonical(route).rstrip(b"\n")) == expected_sha and route["model"] == "grok-4.7"
            and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900
            and route["max_concurrency"] == 10 and route["nonvisual_max_turns"] == 1
            and classification in route["allowed_payload_classes"] and route["armed"] is True
            and route["trusted"] is True and route["zero_charge"] is True, "Reviewed route controls differ")
    return route


def contact_allowed(binding, now=None):
    if binding["endpoint"] != "grok":
        return True
    expiry = datetime.fromisoformat(binding["route"]["cost_evidence"]["expires_at"])
    return (now or datetime.now(timezone.utc)) + timedelta(seconds=MARGIN) < min(CUTOFF, expiry)


def job_binding(manifest, manifest_sha, endpoint, tools, *, workers, headroom, classification, route=None):
    require(1 <= workers <= headroom <= 10, "Workers must fit owner-declared shared endpoint headroom <=10")
    require(classification == "public_repo", "Declared payload is pre-existing public source-reference excerpts, not synthetic")
    binding = {"policy": POLICY, "collector_sha256": sha(Path(__file__).read_bytes()), "manifest_sha256": manifest_sha,
        "preparation_execution_disabled": True, "execution_descendant_selected_by": "explicit owning-controller collect invocation",
        "endpoint": endpoint, "runtime": manifest["runtime"][endpoint], "extraction_sha256": manifest["extraction_sha256"],
        "selection_sha256": manifest["selection_sha256"], "membership_profile_sha256": manifest["membership_profile_sha256"],
        "candidate_mechanism_profile_sha256": manifest["candidate_mechanism_profile_sha256"],
        "implementation": manifest["implementation"], "artifacts_commitment_sha256": sha(canonical(manifest["artifacts"])),
        "workers": workers, "owner_declared_endpoint_headroom": headroom, "shared_project_endpoint_cap": 10,
        "project_concurrency_independently_verified": False, "timeout_seconds": 900, "automatic_retries": 0,
        "payload_classification": classification, "outbound_payload": manifest["outbound_payload"],
        "account_probe_sha256": sha((tools / "adaptive_settings/account_probe.py").read_bytes()),
        "broker_sha256": sha((tools / "model_work_queue/broker.py").read_bytes()),
        "native_foundation_sha256": NATIVE_FOUNDATION_SHA, "semantic_validator_sha256": VALIDATOR_SHA,
        "human_label_release_authority": False, "unused_data_certified": "UNKNOWN", "candidate_promoted": False,
        "planned_per_endpoint": 5170, "planned_total": 10340, "provider_contact_cardinality_proven": False,
        "cost_token_cache_attestation": False}
    if endpoint == "grok":
        require(route is not None and sha(canonical(route).rstrip(b"\n")) == ROUTE_SHA, "Exact execution route absent")
        binding.update(route=route, route_sha256=ROUTE_SHA, campaign_deadline=CUTOFF.isoformat(), deadline_margin_seconds=MARGIN)
    return binding


def verify_job_binding(output, expected):
    require(json.loads((output / "job.json").read_bytes()) == expected, "Immutable job binding differs")
    return expected


def secondary_binding(manifest, helper, account=None):
    env = helper.collection_environment()
    home = Path(env.get("CODEX_HOME", "")).resolve()
    runtime = manifest["runtime"]["sol"]
    require(home == helper.COLLECTION_HOME.resolve() and home.name == "cwr-sol-secondary"
            and home.parent.name == "collection-accounts" and sha(str(home).encode()) == runtime["secondary_home_sha256"]
            and helper.CLI.resolve() == Path(manifest["external_pins"]["cli_path_local_only"]).resolve(), "Secondary home/CLI differs")
    require(not any(env.get(k) for k in ("CODEX_SQLITE_HOME", "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")), "Alternate auth/state override")
    if account is not None:
        identity = sha(canonical({"type": account.get("account_type"), "email": account.get("email", "").lower()}))
        require(account.get("account_type") == "chatgpt" and account.get("probe_exit_confirmed") is True
                and identity == runtime["account_identity_sha256"] == prepare.canary_helpers().SECONDARY_ACCOUNT_SHA256,
                "Secondary native account unavailable")
    return env


def sample_path(output, row):
    return output / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"


def account_receipt(binding):
    return {"account_identity_sha256": binding["runtime"]["account_identity_sha256"],
            "secondary_home_sha256": binding["runtime"]["secondary_home_sha256"],
            "probe_exit_confirmed": True, "account_probe_sha256": binding["account_probe_sha256"]}


def inputs(root, manifest, row):
    prompt = pinned(root, row["prompt_path"], manifest["artifacts"][row["prompt_path"]])
    schema = pinned(root, row["schema_path"], manifest["artifacts"][row["schema_path"]])
    texts = {s["id"]: pinned(root, s["input_path"], manifest["artifacts"][s["input_path"]]).decode("utf-8") for s in row["sources"]}
    context = pinned(root, row["context_path"], manifest["artifacts"][row["context_path"]]).decode("utf-8")
    return prompt, schema, texts, context


def validate_native(sample, row, binding, prompt, schema, receipts):
    native = json.loads((sample / "native-result.json").read_bytes())
    if row["endpoint"] == "sol":
        final_raw = within(sample, native["provider_artifacts"]["codex_message"]["path"]).read_bytes()
        receipts.verify(sample, native, prompt=prompt.decode("utf-8"), model=binding["runtime"]["model"],
                        reasoning=binding["runtime"]["reasoning"], final_raw=final_raw)
        return json.loads(final_raw)
    require(native["state"] == "completed", "Native Grok attempt has no completion")
    raw = (sample / "native-envelope.json").read_bytes()
    envelope, result = json.loads(raw), native["result"]
    runtime = result["runtime"]
    session = json.loads((sample / "native-identity.json").read_bytes())["session_id"]
    compact = lambda value: canonical(value).rstrip(b"\n")
    require(envelope["sessionId"] == session and runtime["session_id_hash"] == sha(session.encode())
            and runtime["requested_model"] == binding["runtime"]["model"]
            and runtime["requested_reasoning_effort"] == binding["runtime"]["reasoning"]
            and runtime["reported_model"] == binding["route"]["reported_model"]
            and result["request_hash"] == sha(compact({"prompt": prompt.decode("utf-8")}))
            and runtime["execution_contract"]["output_schema_hash"] == sha(compact(json.loads(schema)))
            and result["output_hash"] == sha(compact(result["output"]))
            and result["native_envelope_artifact"]["sha256"] == sha(raw)
            and result["native_envelope_artifact"]["byte_length"] == len(raw)
            and envelope["structuredOutput"] == result["output"], "Native Grok identity/request/schema/output differs")
    return result["output"]


def replay(sample, row, manifest, binding, root, receipts, subset, validator):
    require((sample / "terminal.json").is_file(), "Started slot unresolved; no resend")
    terminal = json.loads((sample / "terminal.json").read_bytes())
    require(terminal.get("no_resend") is True and terminal.get("manifest_sha256") == binding["manifest_sha256"]
            and terminal.get("logical_sample_id") == row["logical_sample_id"]
            and json.loads((sample / "condition.json").read_bytes()) == row, "Attempt binding differs; no resend")
    started_path = sample / "attempt-started.json"
    if started_path.exists():
        started = json.loads(started_path.read_bytes())
        require(started["manifest_sha256"] == binding["manifest_sha256"] and started["logical_sample_id"] == row["logical_sample_id"]
                and started["attempt"] == 1 and started["no_resend"] is True
                and started["job_sha256"] == sha((sample.parent / "job.json").read_bytes())
                and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"], "Attempt-start receipt differs")
        if row["endpoint"] == "sol":
            account_raw = (sample.parent / "account-binding.json").read_bytes()
            require(sha(account_raw) == started["account_binding_sha256"] and json.loads(account_raw) == account_receipt(binding),
                    "Secondary account receipt differs")
    if terminal["state"] not in SETTLED:
        require(terminal["state"] in FAILED and terminal["accepted"] is False, "Unknown terminal disposition")
        for name, meta in terminal["retained_artifacts"].items():
            pinned(sample, name, meta)
        return terminal, None
    require(started_path.exists(), "Admitted sample has no own start receipt")
    for name, expected in terminal["artifact_sha256s"].items():
        require(sha(within(sample, name).read_bytes()) == expected, "Settled evidence differs")
    prompt, schema, texts, context = inputs(root, manifest, row)
    require((sample / "prompt.txt").read_bytes() == prompt and (sample / "schema.json").read_bytes() == schema, "Own prompt/schema differs")
    answer = validate_native(sample, row, binding, prompt, schema, receipts)
    require(answer == json.loads((sample / "response.json").read_bytes()), "Derived answer differs from native final")
    acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
    require(acceptance == json.loads((sample / "acceptance.json").read_bytes())
            and acceptance["accepted"] == terminal["accepted"] == (terminal["state"] == "accepted"), "Admission replay differs")
    return terminal, answer if acceptance["accepted"] else None


def collect_one(row, manifest, binding, root, output, subset, validator, receipts, halt,
                helper=None, call_codex=None, broker=None):
    sample = sample_path(output, row)
    sample.mkdir(exist_ok=False)
    record(sample / "condition.json", row)
    terminal = {"manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"],
                "no_resend": True, "accepted": False}
    try:
        prompt, schema, texts, context = inputs(root, manifest, row)
        prepare.extract.write_new(sample / "prompt.txt", prompt)
        prepare.extract.write_new(sample / "schema.json", schema)
        session = str(uuid.uuid4()) if row["endpoint"] == "grok" else None
        record(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]})

        def before():
            require(not halt.is_set() and not (output / "STOP").exists(), "Stop/failure prevents new contact")
            require(contact_allowed(binding), "Route expiry/campaign deadline prevents contact")
            record(sample / "attempt-started.json", {"time": datetime.now(timezone.utc).isoformat(), "attempt": 1,
                "manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"],
                "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
                "job_sha256": sha((output / "job.json").read_bytes()), "session_id": session, "no_resend": True,
                "account_binding_sha256": sha((output / "account-binding.json").read_bytes()) if row["endpoint"] == "sol" else None})

        if row["endpoint"] == "sol":
            content, native = call_codex(executable=str(helper.CLI), model=binding["runtime"]["model"],
                reasoning=binding["runtime"]["reasoning"], prompt=prompt.decode("utf-8"), output_dir=sample,
                response_schema=sample / "schema.json", batch_number=1, timeout=900,
                before_provider_attempt=before, codex_receipt_policy="codex_native_rollout_v1")
            record(sample / "native-result.json", native)
        else:
            native = broker.run_grok_native_request(binding["route"]["name"], {"prompt": prompt.decode("utf-8")},
                output_schema=json.loads(schema), nonvisual_max_turns=1, session_id=session, before_contact=before,
                expected_route_sha256=binding["route_sha256"])
            record(sample / "native-result.json", native)
            if native["state"] != "completed":
                terminal["native_state"] = native["state"]
                terminal["state"] = native["state"] if native["state"] in FAILED else "unadmitted_no_resend"
                raise RuntimeError("Native attempt did not complete")
            prepare.extract.write_new(sample / "native-envelope.json", broker.read_grok_native_envelope(native["result"]["native_envelope_artifact"]))
        answer = validate_native(sample, row, binding, prompt, schema, receipts)
        if row["endpoint"] == "sol":
            require(answer == json.loads(content), "Returned JSON differs from retained native final")
        record(sample / "response.json", answer)
        acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
        record(sample / "acceptance.json", acceptance)
        terminal.update(state="accepted" if acceptance["accepted"] else "semantic_rejected",
                        accepted=acceptance["accepted"], abstention=acceptance["abstention"])
        terminal["artifact_sha256s"] = {p.relative_to(sample).as_posix(): sha(p.read_bytes()) for p in sample.rglob("*") if p.is_file()}
    except BaseException as error:
        halt.set()
        if terminal.get("state") in SETTLED or "state" not in terminal:
            terminal.update(state="unadmitted_no_resend", accepted=False)
        terminal["error_class"] = type(error).__name__
        if hasattr(error, "provider_record"):
            terminal["provider_record"] = error.provider_record
        terminal.pop("artifact_sha256s", None)
        retained, unavailable = {}, []
        for path in sample.rglob("*"):
            if path.is_file():
                try:
                    value = path.read_bytes()
                    retained[path.relative_to(sample).as_posix()] = {"sha256": sha(value), "bytes": len(value)}
                except OSError:
                    unavailable.append(path.relative_to(sample).as_posix())
        terminal.update(retained_artifacts=retained, retention_errors=unavailable)
        record(sample / "terminal.json", terminal)
        if not isinstance(error, Exception):
            raise
        return terminal["state"]
    record(sample / "terminal.json", terminal)
    return terminal["state"]


def dispatch(rows, output, workers, worker, allowed=lambda: True):
    """No queued backlog: stop new admission and drain already-started calls."""
    halt, iterator, states, stopped = Event(), iter(rows), [], False

    def run(row):
        try:
            state = worker(row, halt)
        except BaseException:
            halt.set()
            raise
        if state not in SETTLED:
            halt.set()
        return state

    with ThreadPoolExecutor(max_workers=workers) as executor:
        active = {}
        while active or not stopped:
            if halt.is_set() or (output / "STOP").exists() or not allowed():
                halt.set()
                stopped = True
            while not stopped and len(active) < workers:
                if halt.is_set() or (output / "STOP").exists() or not allowed():
                    halt.set()
                    stopped = True
                    break
                row = next(iterator, None)
                if row is None:
                    stopped = True
                    break
                active[executor.submit(run, row)] = row
            if not active:
                break
            complete, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in complete:
                row = active.pop(future)
                try:
                    state = future.result()
                except BaseException:
                    state = "unresolved_retained_attempt"
                    halt.set()
                states.append({"ordinal": row["endpoint_ordinal"], "state": state})
                print(json.dumps(states[-1]), flush=True)
    if (output / "STOP").exists():
        halt.set()
    return states, halt.is_set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "extraction-receipt", "results-dir", "tools-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--endpoint", choices=prepare.ENDPOINTS, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--endpoint-headroom", type=int, required=True)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--payload-classification", choices=("public_repo",), required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    require(args.limit is None or args.limit > 0, "Limit must be positive")
    manifest, root, subset, validator = load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve(), args.extraction_receipt)
    output = args.results_dir.resolve()
    for protected in (REPO, root, args.extraction_receipt.resolve().parent):
        require(not output.is_relative_to(protected) and not protected.is_relative_to(output), "Results overlap repository/frozen input")
    route = None
    if args.endpoint == "grok":
        require(args.route_root is not None and args.route_sha256 is not None, "Reviewed exact route required")
        route = reviewed_route(args.route_root, args.route_sha256, args.payload_classification)
    binding = job_binding(manifest, args.manifest_sha256, args.endpoint, args.tools_root, workers=args.workers,
                          headroom=args.endpoint_headroom, classification=args.payload_classification, route=route)
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import codex_receipts
    rows = [r for r in manifest["requests"] if r["endpoint"] == args.endpoint]
    if output.exists():
        verify_job_binding(output, binding)
    pending, states = [], []
    for row in rows:
        sample = sample_path(output, row)
        if sample.exists():
            terminal, _ = replay(sample, row, manifest, binding, root, codex_receipts, subset, validator)
            states.append(terminal["state"])
        else:
            pending.append(row)
    if args.validate_only:
        print(json.dumps({"state": "provider_free_validated", "policy": POLICY, "manifest_sha256": args.manifest_sha256,
            "endpoint": args.endpoint, "planned": len(rows), "planned_total": 10340, "untouched": len(pending),
            "occupied": len(states), "workers": args.workers, "owner_declared_endpoint_headroom": args.endpoint_headroom,
            "job_binding_sha256": sha(canonical(binding)), "provider_calls": 0, "account_probe_performed": False,
            "labels_read": False, "native_execution_verified": False, "results_written": False}, sort_keys=True))
        return 0
    require(all(state in SETTLED for state in states), "Failed/ambiguous occupied slot; no resend or automatic continuation")
    if (output / "STOP").exists() or not contact_allowed(binding):
        return 3
    if not pending:
        return 0
    helper = call_codex = broker = None
    if args.endpoint == "sol":
        helper = prepare.load_module("conditional_secondary_helper", Path(manifest["external_pins"]["secondary_helper_path_local_only"]))
        env = secondary_binding(manifest, helper)
        os.environ.clear()
        os.environ.update(env)
        sys.path.insert(0, str(args.tools_root))
        from adaptive_settings.account_probe import probe
        from hbqrs import runner
        secondary_binding(manifest, helper, probe(helper.CLI))
        call_codex = runner._call_codex
    else:
        sys.path.insert(0, str(args.tools_root))
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        record(output / "job.json", binding)
    if args.endpoint == "sol":
        receipt = account_receipt(binding)
        if (output / "account-binding.json").exists():
            require(json.loads((output / "account-binding.json").read_bytes()) == receipt, "Account receipt differs")
        else:
            record(output / "account-binding.json", receipt)
    worker = lambda row, halt: collect_one(row, manifest, binding, root, output, subset, validator,
                                          codex_receipts, halt, helper, call_codex, broker)
    _, failed = dispatch(pending[:args.limit], output, args.workers, worker, lambda: contact_allowed(binding))
    return 3 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
