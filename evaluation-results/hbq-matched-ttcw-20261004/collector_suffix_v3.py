"""Explicit native-once execution descendant for the untouched 007 TTCW suffix."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from threading import Event
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOLS = Path(r"C:\Users\Haile\.codex\tools")
POLICY = "ttcw_untouched_suffix_execution_v3"
MANIFEST_SHA = "7da4c9202c97fa972fc53447e8046c6f56ab5db2f0be75ffb28951095a8e642f"
SOURCE_DRIVER_SHA = "1302142a497d49e8ee6436704c24e61f881f8fdc933882e41941513fc451b6b9"
ROUTE_SHA = "4b4de96df75260b99ea4bb7c05fe7925b22c6a6a898cea404d0bb447b41d54b7"
CUTOFF = datetime(2026, 10, 16, 5, 40, tzinfo=timezone.utc)
MARGIN = timedelta(seconds=960)
SETTLED = {"accepted", "semantic_rejected"}
FAILED = {"ambiguous", "definitely_not_contacted", "unavailable", "unadmitted_no_resend"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


require(sha((HERE / "collector_v2.py").read_bytes()) == SOURCE_DRIVER_SHA, "Frozen v2 utility source differs")
source_driver = load_module("ttcw_suffix_v3_frozen_utilities", HERE / "collector_v2.py")
canonical, pinned, record = source_driver.canonical, source_driver.read_pinned, source_driver.write_new


def reviewed_route(root, expected):
    require(expected == ROUTE_SHA, "Explicit reviewed execution route SHA required")
    route = next(r for r in json.loads((root / "routes.json").read_bytes())["routes"]
                 if r["name"] == "grok-build-grok-4.7")
    require(sha(canonical(route)) == expected and route["model"] == "grok-4.7"
            and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900
            and route["nonvisual_max_turns"] == 1 and route["max_concurrency"] == 10
            and route["nonvisual_transport_contract"] == "grok_nonvisual_history_v5"
            and route["armed"] is True and route["trusted"] is True and route["zero_charge"] is True
            and "public_repo" in route["allowed_payload_classes"], "Execution route controls changed")
    return route


def guard(binding, output, halt, route_root=None, now=None):
    require(not halt.is_set() and not (output / "STOP").exists(), "STOP/failure prevents dispatch or contact")
    deadline = CUTOFF
    if binding["endpoint"] == "grok":
        route = reviewed_route(route_root, binding["route_sha256"])
        deadline = min(deadline, datetime.fromisoformat(route["cost_evidence"]["expires_at"]))
    require((now or datetime.now(timezone.utc)) + MARGIN < deadline, "Route/campaign margin prevents dispatch or contact")


def load_manifest(path, expected, endpoint):
    raw = path.read_bytes()
    require(expected == MANIFEST_SHA == sha(raw), "Explicit frozen 007 manifest SHA differs")
    manifest, root = json.loads(raw), path.resolve().parent
    require(sha(canonical({k: v for k, v in manifest.items() if k != "manifest_content_sha256"}) + b"\n")
            == manifest["manifest_content_sha256"], "Manifest content differs")
    require(manifest["collection_policy"] == {"name": "semantic_reject_continue_v2", "collector_sha256": SOURCE_DRIVER_SHA}
            and manifest["continuation"]["reserved_through_endpoint_ordinal"] == 279
            and manifest["executor_contract"]["execution_route_sha256"] == ROUTE_SHA
            and manifest["executor_contract"]["expiry_margin_seconds"] == 960, "007 preparation provenance differs")
    for name, pin in manifest["artifacts"].items():
        require(len(pinned(root, name, pin["sha256"])) == pin["bytes"], "Frozen artifact size differs")
    parent = json.loads(pinned(root, "lineage/parent-manifest.json", manifest["continuation"]["parent_manifest_sha256"]))
    original = [r for r in parent["requests"] if r["endpoint"] == "grok"]
    require(manifest["requests"] == original[279:] and len(original) == 1554
            and [r["endpoint_ordinal"] for r in manifest["requests"]] == list(range(280, 1555))
            and parent["counts"]["requests_total"] == 3108, "Scientific suffix or original denominator differs")
    rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
    require(rows and len({r["logical_sample_id"] for r in rows}) == len(rows), "Frozen 007 has no unique requests for selected endpoint")
    sys.path.insert(0, str(TOOLS))
    from model_work_queue.adapters import json_schema_subset as subset
    require(sha(Path(subset.__file__).read_bytes()) == manifest["implementation"]["schema_subset_sha256"]
            and sha((HERE / "validate_response.py").read_bytes()) == manifest["implementation"]["semantic_validator_sha256"],
            "Frozen admission implementation differs")
    validator = load_module("ttcw_suffix_v3_semantic_validator", HERE / "validate_response.py")
    for row in rows:
        require(sha(canonical({k: v for k, v in row.items() if k != "request_sha256"}) + b"\n") == row["request_sha256"],
                "Request descriptor differs")
        for kind in ("prompt", "schema"):
            require(len(pinned(root, row[kind + "_path"], row[kind + "_sha256"])) == row[kind + "_bytes"], "Request payload differs")
        subset.validate_schema(json.loads(pinned(root, row["schema_path"], row["schema_sha256"])))
        for item in row["sources"]:
            pinned(root, item["input_path"], item["sha256"])
    return manifest, root, rows, subset, validator


def job_binding(manifest, endpoint, workers, headroom, route=None, helper=None):
    require(1 <= workers <= headroom <= 10, "Workers exceed owner-declared project endpoint headroom <=10")
    require(endpoint in {"sol", "grok"}, "Unknown endpoint")
    binding = {"collector_policy": POLICY, "collector_sha256": sha(Path(__file__).read_bytes()),
        "source_collection_policy": manifest["collection_policy"], "manifest_sha256": MANIFEST_SHA,
        "source_manifest_sha256": manifest["continuation"]["source_manifest_sha256"],
        "source_inventory_sha256": manifest["continuation"]["prefix_jobs"][-1]["source_inventory_sha256"],
        "scientific_artifact_inventory_sha256": sha(canonical(manifest["artifacts"])),
        "validator_sha256": manifest["implementation"]["semantic_validator_sha256"],
        "schema_subset_sha256": manifest["implementation"]["schema_subset_sha256"],
        "broker_sha256": sha((TOOLS / "model_work_queue/broker.py").read_bytes()),
        "account_probe_sha256": sha((TOOLS / "adaptive_settings/account_probe.py").read_bytes()),
        "endpoint": endpoint, "workers": workers, "owner_declared_endpoint_headroom": headroom,
        "project_endpoint_cap": 10, "project_headroom_natively_verified": False,
        "timeout_seconds": 900, "automatic_retries": 0, "native_max_turns": 1,
        "cutoff": CUTOFF.isoformat(), "deadline_margin_seconds": 960, "zero_charge_only": True,
        "payload_classification": "public_repo", "original_requests_per_endpoint": 1554,
        "original_requests_total": 3108, "reserved_through_endpoint_ordinal": 279,
        "preparation_execution_enabled": False, "execution_authority": "explicit owning-controller invocation of this versioned descendant",
        "outbound": "Frozen TTCW story/context pairs, canonical rubric or comparator prompts and schemas; human targets excluded",
        "human_labels_read": False, "unused_or_promotion_authority": False}
    if endpoint == "grok":
        require(route is not None and sha(canonical(route)) == ROUTE_SHA, "Exact route absent")
        binding.update(route=route, route_sha256=ROUTE_SHA,
            source_route_sha256=manifest["executor_contract"]["source_route_sha256"], model=route["model"],
            reasoning=route["reasoning_effort"], destination=route["destination"])
    else:
        require(helper is not None, "Secondary subscription helper required")
        binding.update(model="gpt-6.1-sol", reasoning="high", helper_sha256=sha(helper.read_bytes()),
            runner_sha256=sha((REPO / "src/hbqrs/runner.py").read_bytes()),
            receipt_reader_sha256=sha((REPO / "src/hbqrs/codex_receipts.py").read_bytes()),
            destination="OpenAI ChatGPT subscription via isolated native Codex exec")
    return binding


def inputs(root, row):
    prompt = pinned(root, row["prompt_path"], row["prompt_sha256"])
    schema = pinned(root, row["schema_path"], row["schema_sha256"])
    texts = {s["id"]: pinned(root, s["input_path"], s["sha256"]).decode("utf-8") for s in row["sources"]}
    return prompt, schema, texts, (root / "context.txt").read_text(encoding="utf-8")


def sample_path(output, row):
    return output / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"


def validate_native(sample, row, binding, prompt, schema, receipts):
    native = json.loads((sample / "native-result.json").read_bytes())
    if row["endpoint"] == "sol":
        message = native["provider_artifacts"]["codex_message"]["path"]
        final = pinned(sample, message, native["provider_artifacts"]["codex_message"]["sha256"])
        receipts.verify(sample, native, prompt=prompt.decode("utf-8"), model=binding["model"],
                        reasoning=binding["reasoning"], final_raw=final)
        return json.loads(final)
    require(native["state"] == "completed", "Native Grok attempt did not complete")
    result = native["result"]
    runtime = result["runtime"]
    envelope_raw = (sample / "native-envelope.json").read_bytes()
    envelope = json.loads(envelope_raw)
    session = json.loads((sample / "native-identity.json").read_bytes())["session_id"]
    require(envelope["sessionId"] == session and runtime["session_id_hash"] == sha(session.encode())
            and runtime["requested_model"] == binding["model"] and runtime["requested_reasoning_effort"] == binding["reasoning"]
            and runtime["reported_model"] == binding["route"]["reported_model"]
            and result["request_hash"] == sha(canonical({"prompt": prompt.decode("utf-8")}))
            and runtime["execution_contract"]["output_schema_hash"] == sha(canonical(json.loads(schema)))
            and result["output_hash"] == sha(canonical(result["output"]))
            and result["native_envelope_artifact"]["sha256"] == sha(envelope_raw)
            and result["native_envelope_artifact"]["byte_length"] == len(envelope_raw)
            and envelope["structuredOutput"] == result["output"], "Own native envelope/request/schema/identity differs")
    for key, route_key in (("subscription_receipt_hash", "subscription_receipt_hash"),
                           ("command_identity", "grok_command_identity"), ("cli_version", "grok_cli_version")):
        require(runtime[key] == binding["route"][route_key], "Own native runtime differs from job route")
    return result["output"]


def replay(sample, row, binding, root, subset, validator, receipts=None):
    require((sample / "terminal.json").is_file(), "Occupied unresolved sample; no resend")
    require(json.loads((sample.parent / "job.json").read_bytes()) == binding, "Exact execution job differs")
    terminal = json.loads((sample / "terminal.json").read_bytes())
    require(terminal["no_resend"] is True and terminal["logical_sample_id"] == row["logical_sample_id"]
            and terminal["manifest_sha256"] == binding["manifest_sha256"]
            and terminal["job_sha256"] == sha((sample.parent / "job.json").read_bytes())
            and json.loads((sample / "condition.json").read_bytes()) == row, "Retained sample binding differs")
    for name, pin in terminal["retained_artifacts"].items():
        require(len(pinned(sample, name, pin["sha256"])) == pin["bytes"], "Retained evidence size differs")
    if terminal["state"] not in SETTLED:
        require(terminal["state"] in FAILED and terminal["accepted"] is False, "Unknown terminal disposition")
        return terminal, None
    require(not terminal.get("retention_errors"), "Settled evidence is unavailable")
    prompt, schema, texts, context = inputs(root, row)
    start = json.loads((sample / "attempt-started.json").read_bytes())
    require(start["no_resend"] is True and start["job_sha256"] == terminal["job_sha256"]
            and start["logical_sample_id"] == row["logical_sample_id"] and start["attempt"] == 1
            and start["prompt_sha256"] == row["prompt_sha256"] and start["schema_sha256"] == row["schema_sha256"]
            and (sample / "prompt.txt").read_bytes() == prompt and (sample / "schema.json").read_bytes() == schema,
            "Own contact receipt differs")
    answer = validate_native(sample, row, binding, prompt, schema, receipts)
    require(answer == json.loads((sample / "response.json").read_bytes()), "Derived answer differs")
    acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
    require(acceptance == json.loads((sample / "acceptance.json").read_bytes())
            and acceptance["accepted"] == terminal["accepted"] == (terminal["state"] == "accepted"), "Admission replay differs")
    return terminal, answer if acceptance["accepted"] else None


def collect_one(row, binding, root, output, subset, validator, halt, route_root=None,
                broker=None, helper=None, call_codex=None, receipts=None):
    sample = sample_path(output, row)
    sample.mkdir(exist_ok=False)
    record(sample / "condition.json", row)
    terminal = {"manifest_sha256": binding["manifest_sha256"], "logical_sample_id": row["logical_sample_id"],
                "job_sha256": sha((output / "job.json").read_bytes()), "no_resend": True, "accepted": False}
    try:
        prompt, schema, texts, context = inputs(root, row)
        (sample / "prompt.txt").write_bytes(prompt)
        (sample / "schema.json").write_bytes(schema)
        session = str(uuid.uuid4()) if row["endpoint"] == "grok" else None
        record(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]})

        def before():
            guard(binding, output, halt, route_root)
            record(sample / "attempt-started.json", {"state": "before_contact", "time": datetime.now(timezone.utc).isoformat(),
                "attempt": 1, "session_id": session, "logical_sample_id": row["logical_sample_id"],
                "manifest_sha256": binding["manifest_sha256"], "job_sha256": terminal["job_sha256"], "no_resend": True,
                "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
                "account_binding_sha256": sha((output / "account-binding.json").read_bytes()) if row["endpoint"] == "sol" else None})

        if row["endpoint"] == "grok":
            native = broker.run_grok_native_request(binding["route"]["name"], {"prompt": prompt.decode("utf-8")},
                output_schema=json.loads(schema), nonvisual_max_turns=1, session_id=session, before_contact=before,
                expected_route_sha256=binding["route_sha256"])
            record(sample / "native-result.json", native)
            if native["state"] != "completed":
                terminal["state"] = native["state"] if native["state"] in FAILED else "unadmitted_no_resend"
                terminal["native_state"] = native["state"]
                raise RuntimeError("Native attempt did not complete")
            (sample / "native-envelope.json").write_bytes(broker.read_grok_native_envelope(native["result"]["native_envelope_artifact"]))
        else:
            content, native = call_codex(executable=str(helper.CLI), model=binding["model"], reasoning=binding["reasoning"],
                prompt=prompt.decode("utf-8"), output_dir=sample, response_schema=sample / "schema.json", batch_number=1,
                timeout=900, before_provider_attempt=before, codex_receipt_policy="codex_native_rollout_v1")
            record(sample / "native-result.json", native)
        answer = validate_native(sample, row, binding, prompt, schema, receipts)
        if row["endpoint"] == "sol":
            require(answer == json.loads(content), "Returned answer differs from retained own final")
        record(sample / "response.json", answer)
        acceptance = validator.semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=json.loads(schema))
        record(sample / "acceptance.json", acceptance)
        terminal.update(state="accepted" if acceptance["accepted"] else "semantic_rejected",
                        accepted=acceptance["accepted"], abstention=acceptance["abstention"])
        terminal["retained_artifacts"] = {p.relative_to(sample).as_posix(): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                                          for p in sample.rglob("*") if p.is_file()}
    except Exception as error:
        halt.set()
        if terminal.get("state") in SETTLED or "state" not in terminal:
            terminal.update(state="unadmitted_no_resend", accepted=False)
        terminal["error_class"] = type(error).__name__
        if hasattr(error, "provider_record"):
            record(sample / "native-failure.json", error.provider_record)
        retained, unavailable = {}, []
        for path in sample.rglob("*"):
            if path.is_file():
                try:
                    raw = path.read_bytes()
                    retained[path.relative_to(sample).as_posix()] = {"sha256": sha(raw), "bytes": len(raw)}
                except OSError:
                    unavailable.append(path.relative_to(sample).as_posix())
        terminal.update(retained_artifacts=retained, retention_errors=unavailable)
    record(sample / "terminal.json", terminal)
    return terminal["state"]


def dispatch(rows, output, workers, worker, allowed):
    """Keep no queued backlog; failure/STOP closes admission while started work drains."""
    require(1 <= workers <= 10, "Invalid endpoint concurrency")
    halt, iterator, results, exhausted = Event(), iter(rows), [], False

    def admit():
        try:
            require(not halt.is_set() and not (output / "STOP").exists(), "Dispatch stopped")
            allowed(halt)
            return True
        except Exception:
            halt.set()
            return False

    def run(row):
        try:
            state = worker(row, halt)
        except BaseException:
            halt.set()
            raise
        if state not in SETTLED:
            halt.set()
        return state

    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        while active or not exhausted:
            while not exhausted and len(active) < workers and admit():
                row = next(iterator, None)
                if row is None:
                    exhausted = True
                    break
                active[pool.submit(run, row)] = row
            if halt.is_set():
                exhausted = True
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                row = active.pop(future)
                try:
                    state = future.result()
                except BaseException:
                    state = "unresolved_retained_attempt"
                    halt.set()
                entry = {"ordinal": row["endpoint_ordinal"], "state": state}
                results.append(entry)
                print(json.dumps(entry), flush=True)
    if (output / "STOP").exists():
        halt.set()
    return results, halt.is_set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--endpoint", required=True, choices=("sol", "grok"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--endpoint-headroom", required=True, type=int)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--secondary-helper", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    require(args.limit is None or args.limit > 0, "Positive explicit limit required")
    output = args.results_dir.resolve()
    require(not output.exists(), "Fresh results required; occupied attempts never resumed or resent")
    for protected in (REPO, args.manifest.resolve().parent):
        require(not output.is_relative_to(protected) and not protected.is_relative_to(output), "Results overlap repository/frozen input")
    manifest, root, rows, subset, validator = load_manifest(args.manifest, args.manifest_sha256, args.endpoint)
    route = None
    if args.endpoint == "grok":
        require(args.route_root is not None, "Explicit route root required")
        route = reviewed_route(args.route_root.resolve(), args.route_sha256)
    binding = job_binding(manifest, args.endpoint, args.workers, args.endpoint_headroom, route, args.secondary_helper)
    halt = Event()
    guard(binding, output, halt, args.route_root)
    if args.validate_only:
        print(json.dumps({"state": "validated_without_contact", "policy": POLICY, "manifest_sha256": MANIFEST_SHA,
            "job_binding_sha256": sha(canonical(binding)), "requests": len(rows), "original_requests_total": 3108,
            "reserved_through": 279, "workers": args.workers, "owner_declared_headroom": args.endpoint_headroom,
            "provider_calls": 0, "account_probe_performed": False, "outputs_written": False,
            "native_execution_verified": False}, sort_keys=True))
        return 0
    sys.path.insert(0, str(TOOLS))
    sys.path.insert(0, str(REPO / "src"))
    broker = helper = receipts = call_codex = None
    if args.endpoint == "grok":
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    else:
        helper = load_module("ttcw_suffix_v3_secondary_helper", args.secondary_helper.resolve())
        environment = helper.collection_environment()
        home = Path(environment.get("CODEX_HOME", "")).resolve()
        require(home == helper.COLLECTION_HOME.resolve() and home.name == "cwr-sol-secondary"
                and home.parent.name == "collection-accounts"
                and not any(environment.get(key) for key in ("CODEX_SQLITE_HOME", "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")),
                "Isolated secondary subscription environment differs")
        os.environ.clear()
        os.environ.update(environment)
        from adaptive_settings.account_probe import probe
        from hbqrs import runner, codex_receipts
        account = probe(helper.CLI)
        require(account.get("account_type") == "chatgpt" and account.get("email", "").lower() == "hailey2collet@gmail.com"
                and account.get("probe_exit_confirmed"), "Designated secondary subscription is unavailable")
        binding.update(cli_sha256=sha(Path(helper.CLI).read_bytes()), receipt_reader_sha256=codex_receipts.binding()["reader_sha256"],
            secondary_home_sha256=sha(str(home).encode()),
            account_identity_sha256=sha(canonical({"type": account["account_type"], "email": account["email"].lower()})))
        receipts, call_codex = codex_receipts, runner._call_codex
    guard(binding, output, halt, args.route_root)
    output.mkdir(parents=True, exist_ok=False)
    record(output / "job.json", binding)
    if args.endpoint == "sol":
        record(output / "account-binding.json", {"account_identity_sha256": binding["account_identity_sha256"],
            "helper_sha256": binding["helper_sha256"], "cli_sha256": binding["cli_sha256"], "secondary_subscription_verified": True})
    selected = rows if args.limit is None else rows[:args.limit]
    _, stopped = dispatch(selected, output, args.workers,
        lambda row, signal: collect_one(row, binding, root, output, subset, validator, signal, args.route_root,
                                       broker, helper, call_codex, receipts),
        lambda signal: guard(binding, output, signal, args.route_root))
    return 3 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
