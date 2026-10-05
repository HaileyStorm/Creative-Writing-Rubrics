"""One-worker native collection of the frozen development-only MFA canary."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import prepare

POLICY = "mfa_native_once_v1"
SETTLED = {"accepted", "semantic_rejected"}
CUTOFF = datetime(2026, 10, 16, 5, 40, tzinfo=timezone.utc)


def grok_contact_allowed(at_time=None):
    return (at_time or datetime.now(timezone.utc)) + timedelta(seconds=900) < CUTOFF


def require(condition, message):
    prepare.require(condition, message)


def record(path, value):
    prepare.extract.write_new(path, prepare.canonical(value))


def within(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "Evidence path escapes its own directory")
    return path


def pinned(root, relative, metadata):
    raw = within(root, relative).read_bytes()
    require(prepare.sha(raw) == metadata["sha256"] and len(raw) == metadata["bytes"], "Frozen artifact differs")
    return raw


def load_manifest(path, expected_sha, tools):
    root = path.resolve().parent
    raw = path.read_bytes()
    require(prepare.sha(raw) == expected_sha, "Exact manifest pin differs")
    manifest = json.loads(raw)
    require(prepare.sha(prepare.canonical({k: v for k, v in manifest.items() if k != "manifest_content_sha256"}))
            == manifest["manifest_content_sha256"], "Manifest content commitment differs")
    require(manifest["state"] == "frozen_development_canary" and manifest["labels_read"] is False,
            "Only frozen outcome-blind development preparation is eligible")
    require(manifest["runtime"]["timeout_seconds"] == 900 and manifest["runtime"]["batch_attempts"] == 1
            and manifest["runtime"]["automatic_retries"] == 0, "Registered one-attempt timeout contract differs")
    for relative, meta in manifest["artifacts"].items():
        pinned(root, relative, meta)
    selection = json.loads(pinned(root, "selection.json", manifest["artifacts"]["selection.json"]))
    require(selection["partition"] == "development" and len(selection["selected_targets"]) == 2
            and all(u["partition"] == "development" for u in selection["evaluation_units"])
            and selection["selection_sha256"] == manifest["selection_sha256"], "Development selection binding differs")
    require(manifest["extraction_sha256"] is not None, "Exact extraction receipt is absent")
    checks = [(HERE / "validate_response.py", "implementation/validate_response.py"),
              (HERE / "prepare.py", "implementation/prepare.py"),
              (HERE / "extract.py", "implementation/extract.py"),
              (REPO / "src/hbqrs/runner.py", "implementation/runner.py"),
              (REPO / "src/hbqrs/codex_receipts.py", "implementation/codex_receipts.py"),
              (tools / "model_work_queue/adapters/json_schema_subset.py", "implementation/schema_subset.py"),
              (tools / "model_work_queue/adapters/grok_exec.py", "implementation/grok_exec.py"),
              (Path(manifest["external_pins"]["secondary_helper_path_local_only"]), "implementation/secondary-helper.py")]
    for current, retained in checks:
        require(prepare.sha(current.read_bytes()) == manifest["artifacts"][retained]["sha256"], "Frozen runtime implementation differs")
    require(prepare.sha(Path(manifest["external_pins"]["cli_path_local_only"]).read_bytes())
            == manifest["external_pins"]["cli_sha256"], "Frozen native CLI differs")
    subset = prepare.load_module("mfa_collection_schema_subset", tools / "model_work_queue/adapters/json_schema_subset.py")
    validator = prepare.load_module("mfa_collection_validator", HERE / "validate_response.py")
    for endpoint in prepare.ENDPOINTS:
        rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
        require(rows and [r["endpoint_ordinal"] for r in rows] == list(range(1, len(rows) + 1))
                and len({r["logical_sample_id"] for r in rows}) == len(rows), "Endpoint identities are absent or duplicated")
        for row in rows:
            require(prepare.sha(prepare.canonical({k: v for k, v in row.items() if k != "request_sha256"}))
                    == row["request_sha256"] and row["partition"] == "development", "Request commitment differs")
            for kind in ("prompt", "schema"):
                raw_item = pinned(root, row[kind + "_path"], manifest["artifacts"][row[kind + "_path"]])
                require(prepare.sha(raw_item) == row[kind + "_sha256"] and len(raw_item) == row[kind + "_bytes"], "Request bytes differ")
            subset.validate_schema(json.loads(raw_item))
            require(row["context_sha256"] == manifest["artifacts"]["context.txt"]["sha256"], "Context binding differs")
            for source in row["sources"]:
                raw_source = pinned(root, source["input_path"], manifest["artifacts"][source["input_path"]])
                require(prepare.sha(raw_source) == source["sha256"] and len(raw_source) == source["bytes"], "Source binding differs")
            if "task_contract_path" in row:
                require(manifest["artifacts"][row["task_contract_path"]]["sha256"] == row["task_contract_sha256"], "Task contract differs")
    return manifest, root, subset, validator


def secondary_binding(manifest, helper, account=None):
    env = helper.collection_environment()
    home = Path(env.get("CODEX_HOME", "")).resolve()
    runtime = manifest["runtime"]["sol"]
    require(home == helper.COLLECTION_HOME.resolve() and home.name == "cwr-sol-secondary"
            and home.parent.name == "collection-accounts" and prepare.sha(str(home).encode()) == runtime["secondary_home_sha256"]
            and helper.CLI.resolve() == Path(manifest["external_pins"]["cli_path_local_only"]).resolve(), "Secondary account home/CLI differs")
    require(not any(env.get(k) for k in ("CODEX_SQLITE_HOME", "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")), "Alternate auth/state override present")
    if account is not None:
        identity = prepare.sha(prepare.canonical({"type": account.get("account_type"), "email": account.get("email", "").lower()}))
        require(account.get("account_type") == "chatgpt" and account.get("probe_exit_confirmed") is True
                and identity == runtime["account_identity_sha256"] == prepare.SECONDARY_ACCOUNT_SHA256, "Secondary native account unavailable")
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
    context = pinned(root, "context.txt", manifest["artifacts"]["context.txt"]).decode("utf-8")
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
    compact = lambda value: prepare.canonical(value).rstrip(b"\n")
    require(envelope["sessionId"] == session and runtime["session_id_hash"] == prepare.sha(session.encode())
            and runtime["requested_model"] == binding["runtime"]["model"]
            and runtime["requested_reasoning_effort"] == binding["runtime"]["reasoning"]
            and runtime["reported_model"] == binding["route"]["reported_model"]
            and result["request_hash"] == prepare.sha(compact({"prompt": prompt.decode("utf-8")}))
            and runtime["execution_contract"]["output_schema_hash"] == prepare.sha(compact(json.loads(schema)))
            and result["output_hash"] == prepare.sha(compact(result["output"]))
            and result["native_envelope_artifact"]["sha256"] == prepare.sha(raw)
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
        require(terminal["state"] in {"unadmitted_no_resend", "ambiguous", "definitely_not_contacted"}, "Unknown terminal disposition")
        for relative, meta in terminal["retained_artifacts"].items():
            pinned(sample, relative, meta)
        return terminal, None
    for name, expected in terminal["artifact_sha256s"].items():
        require(prepare.sha(within(sample, name).read_bytes()) == expected, "Settled evidence differs")
    started = json.loads((sample / "attempt-started.json").read_bytes())
    require(started["manifest_sha256"] == binding["manifest_sha256"] and started["logical_sample_id"] == row["logical_sample_id"]
            and started["attempt"] == 1 and started["no_resend"] is True
            and started["job_sha256"] == prepare.sha((sample.parent / "job.json").read_bytes())
            and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"], "Attempt-start receipt differs")
    if row["endpoint"] == "sol":
        account_raw = (sample.parent / "account-binding.json").read_bytes()
        require(prepare.sha(account_raw) == started["account_binding_sha256"]
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
    prepare.extract.write_new(sample / "prompt.txt", prompt)
    prepare.extract.write_new(sample / "schema.json", schema)
    session = str(uuid.uuid4()) if row["endpoint"] == "grok" else None
    record(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]})
    terminal = {"manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"], "no_resend": True, "accepted": False}
    def before():
        require(not (output / "STOP").exists(), "Stop observed before contact")
        require(row["endpoint"] != "grok" or grok_contact_allowed(), "Campaign deadline prevents native contact")
        record(sample / "attempt-started.json", {"time": datetime.now(timezone.utc).isoformat(), "attempt": 1,
            "manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"],
            "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
            "job_sha256": prepare.sha((output / "job.json").read_bytes()), "session_id": session, "no_resend": True,
            "account_binding_sha256": prepare.sha((output / "account-binding.json").read_bytes()) if row["endpoint"] == "sol" else None})
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
            prepare.extract.write_new(sample / "native-envelope.json", broker.read_grok_native_envelope(native["result"]["native_envelope_artifact"]))
        answer = validate_native(sample, row, binding, prompt, schema, receipts)
        if row["endpoint"] == "sol":
            require(answer == json.loads(content), "Returned JSON differs from retained native final")
        record(sample / "response.json", answer)
        acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
        record(sample / "acceptance.json", acceptance)
        terminal.update(state="accepted" if acceptance["accepted"] else "semantic_rejected", accepted=acceptance["accepted"], abstention=acceptance["abstention"])
        terminal["artifact_sha256s"] = {p.name: prepare.sha(p.read_bytes()) for p in sample.iterdir() if p.is_file()}
    except BaseException as error:
        terminal.setdefault("state", "unadmitted_no_resend")
        terminal["error_class"] = type(error).__name__
        if hasattr(error, "provider_record"):
            terminal["provider_record"] = error.provider_record
        terminal["retained_artifacts"] = {p.relative_to(sample).as_posix(): {"sha256": prepare.sha(p.read_bytes()), "bytes": p.stat().st_size}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--extraction-receipt", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--endpoint", choices=prepare.ENDPOINTS, required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--payload-classification", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    require(args.limit is None or args.limit > 0, "Limit must be positive")
    manifest, root, subset, validator = load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    selection = json.loads((root / "selection.json").read_bytes())
    _, extraction_sha = prepare.read_extraction(args.extraction_receipt.resolve().parent, selection)
    require(extraction_sha == manifest["extraction_sha256"] and prepare.sha(args.extraction_receipt.read_bytes()) == extraction_sha,
            "Exact extraction receipt differs")
    output = args.results_dir.resolve()
    require(not output.is_relative_to(REPO) and not REPO.is_relative_to(output) and not output.is_relative_to(root) and not root.is_relative_to(output), "Results must be private and separate from frozen input")
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import codex_receipts
    binding = {"manifest_sha256": args.manifest_sha256, "extraction_sha256": manifest["extraction_sha256"], "endpoint": args.endpoint,
        "runtime": manifest["runtime"][args.endpoint], "timeout_seconds": 900, "workers": 1, "automatic_retries": 0,
        "policy": POLICY, "collector_sha256": prepare.sha(Path(__file__).read_bytes()), "payload_classification": args.payload_classification,
        "implementation": manifest["implementation"], "artifacts_commitment_sha256": prepare.sha(prepare.canonical(manifest["artifacts"])),
        "account_probe_sha256": prepare.sha((args.tools_root / "adaptive_settings/account_probe.py").read_bytes()),
        "broker_sha256": prepare.sha((args.tools_root / "model_work_queue/broker.py").read_bytes()),
        "provider_contact_cardinality_proven": False, "cost_token_cache_attestation": False}
    if args.endpoint == "grok":
        require(args.route_root is not None and args.route_sha256 is not None, "Grok requires reviewed exact route pin")
        routes = json.loads((args.route_root / "routes.json").read_bytes())["routes"]
        route = next(r for r in routes if r["name"] == manifest["runtime"]["grok"]["route"])
        require(prepare.sha(prepare.canonical(route).rstrip(b"\n")) == args.route_sha256
                and route["model"] == binding["runtime"]["model"] and route["reasoning_effort"] == "high"
                and route["timeout_seconds"] == 900 and args.payload_classification in route["allowed_payload_classes"], "Reviewed Grok route/settings/disclosure differs")
        binding.update(route=route, route_sha256=args.route_sha256, campaign_deadline=CUTOFF.isoformat(), deadline_margin_seconds=900)
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
        helper = prepare.load_module("mfa_secondary_helper", Path(manifest["external_pins"]["secondary_helper_path_local_only"]))
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
