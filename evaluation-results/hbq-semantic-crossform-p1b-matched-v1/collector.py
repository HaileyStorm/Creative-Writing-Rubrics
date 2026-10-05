"""One-worker descriptive P1b native collection; no oracle or label promotion.

Lifecycle predecessor: MFA collector a4a7073ff5d24875fcc1d866b727792ebdafa4ad70df327691a72e17cbcacc94.
The frozen predecessor remains active and is never imported or edited here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import hashlib
import importlib.util
from collections import Counter, defaultdict
import os
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

POLICY = "p1b_descriptive_native_once_v1"
ENDPOINTS = ("grok", "sol")
SECONDARY_ACCOUNT_SHA256 = "a283be8dc909b7f172c1a348c38883deb00394b66de29023cbe45de4bbc37d3d"
FORMS = {"short_narrative": ("prose.short_story", 178, 23), "novel_work_segment": ("prose.short_form", 170, 22), "poem": ("poetry.free_verse", 89, 12)}
ARM_COUNTS = {"hbq": 640, "holistic": 32, "compact": 32, "pairwise": 48, "ttcw14": 16, "oregon": 16, "poemetric": 8}
SETTLED = {"accepted", "semantic_rejected"}
TERMINAL_STATES = SETTLED | {"unadmitted_no_resend", "ambiguous", "definitely_not_contacted", "unavailable"}
CUTOFF = datetime(2026, 10, 16, 5, 40, tzinfo=timezone.utc)


def grok_contact_allowed(at_time=None):
    return (at_time or datetime.now(timezone.utc)) + timedelta(seconds=900) < CUTOFF


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def record(path, value):
    write_bytes(path, canonical(value))


def within(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "Evidence path escapes its own directory")
    return path


def pinned(root, relative, metadata):
    raw = within(root, relative).read_bytes()
    require(digest(raw) == metadata["sha256"] and len(raw) == metadata["bytes"], "Frozen artifact differs")
    return raw


def source_settings(manifest, root):
    raw = pinned(root, "private/source-generation-manifest.json", manifest["artifacts"]["private/source-generation-manifest.json"])
    require(digest(raw) == manifest["generation_manifest_file_sha256"], "Generation source manifest differs")
    source = json.loads(raw)
    require(digest(canonical({k: v for k, v in source.items() if k != "manifest_content_sha256"})) == source["manifest_content_sha256"], "Generation content commitment differs")
    runtime = source["runtime"]
    require(runtime["model"] == "gpt-6.1-sol" and runtime["reasoning"] == "high"
            and runtime["receipt_policy"] == "codex_native_rollout_v1" and runtime["account_identity_sha256"] == SECONDARY_ACCOUNT_SHA256,
            "Frozen source secondary runtime differs")
    pins = source["external_pins"]
    require(Path(pins["tools_root_local_only"]).resolve().name == "tools", "Source tools root differs")
    helper_raw = Path(pins["secondary_helper_path_local_only"]).read_bytes()
    require(digest(helper_raw) == source["artifacts"]["implementation/secondary-helper.py"]["sha256"], "Frozen secondary helper differs")
    cli_raw = Path(pins["cli_path_local_only"]).read_bytes()
    require(digest(cli_raw) == pins["cli_sha256"] and len(cli_raw) == pins["cli_bytes"], "Frozen native CLI differs")
    home = Path(pins["collection_home_path_local_only"]).resolve()
    require(home.name == "cwr-sol-secondary" and home.parent.name == "collection-accounts"
            and digest(str(home).encode()) == runtime["codex_home_sha256"], "Frozen designated home differs")
    return source


def validate_geometry(manifest, root):
    from hbqrs import core
    bank_ids = {}
    for form, (bundle, leaves, packets) in FORMS.items():
        compiled = json.loads(pinned(root, "compiled/" + bundle + ".json", manifest["artifacts"]["compiled/" + bundle + ".json"]))
        bank_ids[form] = [q["question"]["id"] for q in core.compiled_questions(compiled)]
        require(len(bank_ids[form]) == leaves and len(set(bank_ids[form])) == leaves, "Canonical form bank differs")
    for endpoint in ENDPOINTS:
        rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
        require(len(rows) == 792 and Counter(r["arm"] for r in rows) == Counter(ARM_COUNTS)
                and [r["endpoint_ordinal"] for r in rows] == list(range(1, 793))
                and len({r["logical_sample_id"] for r in rows}) == len(rows), "Complete endpoint geometry differs")
        banks = defaultdict(list)
        for row in rows:
            require(row["form"] in FORMS and row["bundle_id"] == FORMS[row["form"]][0], "Form dispatch differs")
            require(row["repeat"] in (0, 1, 2), "Repeat cycle differs")
            if row["arm"] == "hbq":
                banks[(row["artifact_id"], row["repeat"], row["form"])].append(row)
        for (_, _, form), group in banks.items():
            group.sort(key=lambda r: r["batch"])
            require([r["batch"] for r in group] == list(range(1, FORMS[form][2] + 1))
                    and [q for r in group for q in r["question_ids"]] == bank_ids[form], "Incomplete or reordered native form bank")


def load_manifest(path, expected_sha, tools):
    root = path.resolve().parent
    raw = path.read_bytes()
    require(digest(raw) == expected_sha, "Exact manifest pin differs")
    manifest = json.loads(raw)
    require(manifest["study_id"] == "descriptive_synthetic_matched_crossform_v1"
            and manifest["evidence_class"] == "descriptive_ai_synthetic_stimuli"
            and manifest["candidate"] is None and manifest["oracle_accepted"] is False
            and manifest["fixed_synthetic_labels"] is False and manifest["execution_authority"] is False,
            "Only frozen descriptive synthetic preparation is eligible")
    require(manifest["runtime"]["timeout_seconds"] == 900 and manifest["runtime"]["automatic_retries"] == 0,
            "Registered one-attempt timeout contract differs")
    for relative, meta in manifest["artifacts"].items():
        pinned(root, relative, meta)
    source = source_settings(manifest, root)
    require(tools.resolve() == Path(source["external_pins"]["tools_root_local_only"]).resolve(), "Frozen tools root differs")
    checks = [(HERE / "prepare.py", "implementation/prepare.py"),
              (REPO / "src/hbqrs/core.py", "implementation/core.py"),
              (REPO / "src/hbqrs/runner.py", "implementation/runner.py"),
              (REPO / "src/hbqrs/codex_receipts.py", "implementation/codex_receipts.py"),
              (tools / "model_work_queue/adapters/json_schema_subset.py", "implementation/schema_subset.py"),
              (HERE / "arms/validate_response.py", "implementation/validate_response.py")]
    for current, retained in checks:
        require(digest(current.read_bytes()) == manifest["artifacts"][retained]["sha256"], "Frozen runtime implementation differs")
    require(digest((tools / "adaptive_settings/account_probe.py").read_bytes()) == source["external_pins"]["account_probe_sha256"], "Frozen account probe differs")
    subset = load_module("p1b_collection_schema_subset", root / "implementation/schema_subset.py")
    validator = load_module("p1b_collection_validator", root / "implementation/validate_response.py")
    sys.path.insert(0, str(REPO / "src"))
    validate_geometry(manifest, root)
    for row in manifest["requests"]:
        require(digest(canonical({k: v for k, v in row.items() if k != "request_sha256"})) == row["request_sha256"], "Request commitment differs")
        condition = {k: v for k, v in row.items() if k not in ("request_sha256", "logical_sample_id", "endpoint", "endpoint_ordinal", "ordinal")}
        require(digest(canonical(condition)) == row["logical_sample_id"], "Logical sample condition differs")
        for kind in ("prompt", "schema"):
            raw_item = pinned(root, row[kind + "_path"], manifest["artifacts"][row[kind + "_path"]])
            require(digest(raw_item) == row[kind + "_sha256"] and len(raw_item) == row[kind + "_bytes"], "Request bytes differ")
        subset.validate_schema(json.loads(raw_item))
        for source_item in row["sources"]:
            raw_source = pinned(root, source_item["input_path"], manifest["artifacts"][source_item["input_path"]])
            require(digest(raw_source) == source_item["sha256"] and len(raw_source) == source_item["bytes"], "Source binding differs")
        for field in ("task_context", "shared_work_context"):
            meta = row[field]
            require(pinned(root, meta["path"], manifest["artifacts"][meta["path"]]) == pinned(root, meta["path"], meta), "Context binding differs")
        require(row["compiled_sha256"] == manifest["artifacts"]["compiled/" + row["bundle_id"] + ".json"]["sha256"], "Compiled bank binding differs")
        contracts = row["task_contracts"]
        require([t["artifact_id"] for t in contracts] == [s["id"] for s in row["sources"]], "Task/source identity differs")
        for task in contracts:
            require(manifest["artifacts"][task["path"]]["sha256"] == task["sha256"], "Task contract binding differs")
            contract = json.loads(pinned(root, task["path"], manifest["artifacts"][task["path"]]))
            expected = {"short_narrative": ("prose_fiction", "story", "complete"), "novel_work_segment": ("prose_fiction", "passage", "excerpt"), "poem": ("poetry", "poem", "complete")}[row["form"]]
            require(contract["artifact_id"] == task["artifact_id"] and tuple(contract["context"][k] for k in ("artifact_kind", "declared_scope", "completion_status")) == expected
                    and all(contract[k] == [] for k in ("weighted_goals", "binding_requirements", "preferences", "priorities")), "Form task applicability differs")
    return manifest, root, subset, validator


def secondary_binding(source, helper, account=None):
    env = helper.collection_environment()
    home = Path(env.get("CODEX_HOME", "")).resolve()
    runtime = source["runtime"]
    require(home == helper.COLLECTION_HOME.resolve() and home.name == "cwr-sol-secondary"
            and home.parent.name == "collection-accounts" and digest(str(home).encode()) == runtime["codex_home_sha256"]
            and home == Path(source["external_pins"]["collection_home_path_local_only"]).resolve()
            and helper.CLI.resolve() == Path(source["external_pins"]["cli_path_local_only"]).resolve(), "Secondary account home/CLI differs")
    require(not any(env.get(k) for k in ("CODEX_SQLITE_HOME", "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")), "Alternate auth/state override present")
    if account is not None:
        identity = digest(canonical({"type": account.get("account_type"), "email": account.get("email", "").lower()}))
        require(account.get("account_type") == "chatgpt" and account.get("probe_exit_confirmed") is True
                and identity == runtime["account_identity_sha256"] == SECONDARY_ACCOUNT_SHA256, "Secondary native account unavailable")
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
    context = pinned(root, row["task_context"]["path"], row["task_context"]).decode("utf-8") + "\n" + pinned(root, row["shared_work_context"]["path"], row["shared_work_context"]).decode("utf-8")
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
    require(envelope["sessionId"] == session and runtime["session_id_hash"] == digest(session.encode())
            and runtime["requested_model"] == binding["runtime"]["model"]
            and runtime["requested_reasoning_effort"] == binding["runtime"]["reasoning"]
            and runtime["reported_model"] == binding["route"]["reported_model"]
            and result["request_hash"] == digest(compact({"prompt": prompt.decode("utf-8")}))
            and runtime["execution_contract"]["output_schema_hash"] == digest(compact(json.loads(schema)))
            and result["output_hash"] == digest(compact(result["output"]))
            and result["native_envelope_artifact"]["sha256"] == digest(raw)
            and result["native_envelope_artifact"]["byte_length"] == len(raw)
            and envelope["structuredOutput"] == result["output"], "Native Grok identity/request/schema/output binding differs")
    return result["output"]


def replay(sample, row, manifest, binding, root, receipts, subset, validator):
    require((sample / "terminal.json").is_file(), "Started slot is unresolved; no resend")
    terminal = json.loads((sample / "terminal.json").read_bytes())
    require(terminal.get("no_resend") is True and terminal.get("manifest_sha256") == binding["manifest_sha256"]
            and terminal.get("logical_sample_id") == row["logical_sample_id"], "Attempt binding differs; no resend")
    require(json.loads((sample / "condition.json").read_bytes()) == row, "Attempt condition differs")
    if terminal["state"] not in SETTLED:
        require(terminal["state"] in TERMINAL_STATES, "Unknown terminal disposition")
        for relative, meta in terminal["retained_artifacts"].items():
            pinned(sample, relative, meta)
        return terminal, None
    for name, expected in terminal["artifact_sha256s"].items():
        require(digest(within(sample, name).read_bytes()) == expected, "Settled evidence differs")
    started = json.loads((sample / "attempt-started.json").read_bytes())
    require(started["manifest_sha256"] == binding["manifest_sha256"] and started["logical_sample_id"] == row["logical_sample_id"]
            and started["attempt"] == 1 and started["no_resend"] is True
            and started["job_sha256"] == digest((sample.parent / "job.json").read_bytes())
            and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"], "Attempt-start receipt differs")
    if row["endpoint"] == "sol":
        account_raw = (sample.parent / "account-binding.json").read_bytes()
        require(digest(account_raw) == started["account_binding_sha256"]
                and json.loads(account_raw) == account_receipt(binding), "Secondary account receipt differs")
    prompt, schema, texts, context = inputs(root, manifest, row)
    require((sample / "prompt.txt").read_bytes() == prompt and (sample / "schema.json").read_bytes() == schema, "Own prompt/schema differs")
    answer = validate_native(sample, row, binding, prompt, schema, receipts)
    require(answer == json.loads((sample / "response.json").read_bytes()), "Derived answer differs from native final")
    acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
    require(acceptance == json.loads((sample / "acceptance.json").read_bytes())
            and acceptance["accepted"] == terminal["accepted"] == (terminal["state"] == "accepted"), "Admission replay differs")
    return terminal, answer if acceptance["accepted"] else None


def note_stop(output):
    if not (output / "stop-observed.json").exists():
        record(output / "stop-observed.json", {"time": datetime.now(timezone.utc).isoformat(),
               "behavior": "prevent new contact; current bounded call settles", "cooperative_cancellation_claimed": False})


def collect_one(row, manifest, binding, root, output, subset, validator, receipts, helper=None, call_codex=None, broker=None):
    sample = sample_path(output, row)
    sample.mkdir(exist_ok=False)
    record(sample / "condition.json", row)
    prompt, schema, texts, context = inputs(root, manifest, row)
    write_bytes(sample / "prompt.txt", prompt)
    write_bytes(sample / "schema.json", schema)
    session = str(uuid.uuid4()) if row["endpoint"] == "grok" else None
    record(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]})
    terminal = {"manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"], "no_resend": True, "accepted": False}
    def before():
        require(not (output / "STOP").exists(), "Stop observed before contact")
        require(row["endpoint"] != "grok" or grok_contact_allowed(), "Campaign deadline prevents native contact")
        record(sample / "attempt-started.json", {"time": datetime.now(timezone.utc).isoformat(), "attempt": 1,
            "manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"],
            "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
            "job_sha256": digest((output / "job.json").read_bytes()), "session_id": session, "no_resend": True,
            "account_binding_sha256": digest((output / "account-binding.json").read_bytes()) if row["endpoint"] == "sol" else None})
    try:
        if row["endpoint"] == "sol":
            content, native = call_codex(executable=str(helper.CLI), model=binding["runtime"]["model"], reasoning=binding["runtime"]["reasoning"],
                prompt=prompt.decode("utf-8"), output_dir=sample, response_schema=sample / "schema.json", batch_number=1,
                timeout=manifest["runtime"]["timeout_seconds"], before_provider_attempt=before, codex_receipt_policy="codex_native_rollout_v1")
            record(sample / "native-result.json", native)
        else:
            native = broker.run_grok_native_request(binding["route"]["name"], {"prompt": prompt.decode("utf-8")},
                output_schema=json.loads(schema), nonvisual_max_turns=1, session_id=session, before_contact=before,
                expected_route_sha256=binding["route_sha256"])
            record(sample / "native-result.json", native)
            if native["state"] != "completed":
                terminal["state"] = native["state"]
                raise RuntimeError("Native attempt did not complete")
            write_bytes(sample / "native-envelope.json", broker.read_grok_native_envelope(native["result"]["native_envelope_artifact"]))
        answer = validate_native(sample, row, binding, prompt, schema, receipts)
        if row["endpoint"] == "sol":
            require(answer == json.loads(content), "Returned JSON differs from retained native final")
        record(sample / "response.json", answer)
        acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
        record(sample / "acceptance.json", acceptance)
        terminal.update(state="accepted" if acceptance["accepted"] else "semantic_rejected", accepted=acceptance["accepted"], abstention=acceptance["abstention"])
        terminal["artifact_sha256s"] = {p.name: digest(p.read_bytes()) for p in sample.iterdir() if p.is_file()}
    except BaseException as error:
        terminal.setdefault("state", "unadmitted_no_resend")
        terminal["error_class"] = type(error).__name__
        if hasattr(error, "provider_record"):
            terminal["provider_record"] = error.provider_record
        terminal["retained_artifacts"] = {p.relative_to(sample).as_posix(): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                                          for p in sample.rglob("*") if p.is_file()}
        record(sample / "terminal.json", terminal)
        if (output / "STOP").exists():
            note_stop(output)
        if not isinstance(error, Exception):
            raise
        return terminal["state"]
    record(sample / "terminal.json", terminal)
    if (output / "STOP").exists():
        note_stop(output)
    return terminal["state"]


def job_binding(manifest, root, manifest_sha, endpoint, tools, route=None, payload_classification="public_synthetic"):
    require(endpoint in ENDPOINTS and payload_classification == "public_synthetic", "Collection destination scope differs")
    source = source_settings(manifest, root)
    runtime = dict(manifest["runtime"][endpoint])
    if endpoint == "sol":
        runtime.update(secondary_home_sha256=source["runtime"]["codex_home_sha256"], codex_receipt_policy="codex_native_rollout_v1")
    require(runtime["model"] == ("gpt-6.1-sol" if endpoint == "sol" else "grok-4.7") and runtime["reasoning"] == "high", "Registered endpoint settings differ")
    binding = {"manifest_sha256": manifest_sha, "generation_manifest_sha256": manifest["generation_manifest_file_sha256"], "endpoint": endpoint,
        "runtime": runtime, "timeout_seconds": 900, "workers": 1, "automatic_retries": 0,
        "policy": POLICY, "collector_sha256": digest(Path(__file__).read_bytes()), "payload_classification": payload_classification,
        "preparation_execution_authority": manifest["execution_authority"],
        "artifacts_commitment_sha256": digest(canonical(manifest["artifacts"])),
        "source_helper_sha256": source["artifacts"]["implementation/secondary-helper.py"]["sha256"],
        "cli_sha256": source["external_pins"]["cli_sha256"],
        "runner_sha256": manifest["artifacts"]["implementation/runner.py"]["sha256"],
        "receipt_reader_sha256": manifest["artifacts"]["implementation/codex_receipts.py"]["sha256"],
        "admission_sha256": manifest["artifacts"]["implementation/validate_response.py"]["sha256"],
        "grok_adapter_sha256": digest((tools / "model_work_queue/adapters/grok_exec.py").read_bytes()),
        "account_probe_sha256": digest((tools / "adaptive_settings/account_probe.py").read_bytes()),
        "broker_sha256": digest((tools / "model_work_queue/broker.py").read_bytes()),
        "provider_contact_cardinality_proven": False, "cost_token_cache_attestation": False}
    if endpoint == "grok":
        require(route is not None and route["name"] == "grok-build-grok-4.7" and route["model"] == runtime["model"]
                and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900
                and payload_classification in route["allowed_payload_classes"], "Reviewed Grok route/settings/disclosure differs")
        binding.update(route=route, route_sha256=digest(canonical(route).rstrip(b"\n")),
                       campaign_deadline=CUTOFF.isoformat(), deadline_margin_seconds=900)
    return binding


def verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools):
    binding = json.loads((output / "job.json").read_bytes())
    require(binding == job_binding(manifest, root, manifest_sha, endpoint, tools, binding.get("route")), "Job binding differs")
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--endpoint", choices=ENDPOINTS, required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--payload-classification", choices=["public_synthetic"], default="public_synthetic")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    require(args.limit is None or args.limit > 0, "Limit must be positive")
    manifest, root, subset, validator = load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    source = source_settings(manifest, root)
    output = args.results_dir.resolve()
    require(not output.is_relative_to(REPO) and not REPO.is_relative_to(output) and not output.is_relative_to(root) and not root.is_relative_to(output), "Results must be private and separate from frozen input")
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import codex_receipts
    route = None
    if args.endpoint == "grok":
        require(args.route_root is not None and args.route_sha256 is not None, "Grok requires reviewed exact route pin")
        routes = json.loads((args.route_root / "routes.json").read_bytes())["routes"]
        route = next(r for r in routes if r["name"] == "grok-build-grok-4.7")
        require(digest(canonical(route).rstrip(b"\n")) == args.route_sha256, "Reviewed route pin differs")
    binding = job_binding(manifest, root, args.manifest_sha256, args.endpoint, args.tools_root, route, args.payload_classification)
    rows = [r for r in manifest["requests"] if r["endpoint"] == args.endpoint]
    if output.exists():
        require((output / "job.json").is_file() and json.loads((output / "job.json").read_bytes()) == binding, "Job binding differs")
    pending, states = [], []
    for row in rows:
        sample = sample_path(output, row)
        if sample.exists():
            terminal, _ = replay(sample, row, manifest, binding, root, codex_receipts, subset, validator)
            states.append(terminal["state"])
        else:
            pending.append(row)
    if args.validate_only:
        print(json.dumps({"state": "provider_free_validated", "manifest_sha256": args.manifest_sha256, "endpoint": args.endpoint,
                          "planned": len(rows), "untouched": len(pending), "settled": len(states), "provider_calls": 0}))
        return 0
    if any(state not in SETTLED for state in states):
        raise ValueError("Unadmitted slot requires explicit reconciliation; no resend")
    if (output / "STOP").exists():
        note_stop(output)
        return 3
    if not pending:
        return 0
    helper = call_codex = broker = None
    if args.endpoint == "sol":
        helper = load_module("p1b_secondary_helper", Path(source["external_pins"]["secondary_helper_path_local_only"]))
        env = secondary_binding(source, helper)
        os.environ.clear()
        os.environ.update(env)
        sys.path.insert(0, str(args.tools_root))
        from adaptive_settings.account_probe import probe
        from hbqrs import runner
        secondary_binding(source, helper, probe(helper.CLI))
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
            require(json.loads((output / "account-binding.json").read_bytes()) == receipt, "Retained account receipt differs")
        else:
            record(output / "account-binding.json", receipt)
    for row in pending[:args.limit]:
        if args.endpoint == "grok" and not grok_contact_allowed():
            print(json.dumps({"state": "campaign_deadline_prevents_new_contact", "untouched_ordinal": row["endpoint_ordinal"]}), flush=True)
            return 3
        if (output / "STOP").exists():
            note_stop(output)
            return 3
        state = collect_one(row, manifest, binding, root, output, subset, validator, codex_receipts, helper, call_codex, broker)
        print(json.dumps({"ordinal": row["endpoint_ordinal"], "state": state}), flush=True)
        if state not in SETTLED:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
