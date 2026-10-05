"""Named P4 v6 continuation: exact no-contact recovery, then untouched slots."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid

HERE = Path(__file__).resolve().parent
POLICY = "p4_grok_longform_v6_continuation_once_v1"
MANIFEST_SHA = "d0cb6589924a4900b123206f40595035a6d792c623bac1c8303de9d95bac1ac4"
COLLECTOR_SHA = "0425421d9cdcbcc706c69e5eae16724079ddd05d0d670962707105724721525f"
PROFILE_SHA = "b012b3a3e0a7dd3929cc1b7f541a3af53c188e2f1aaf4f18c7897d5a4307d366"
V6_PINS = {
    "derived.py": "04b9a590c00d27a1528e40b2b30ddee91a2439b4256dd19beb88a5d726e338dd",
    "adapters/grok_exec.py": "3e2fd8c4dbe4aa606f4a7891efb9451086a00e1cf9ec860a36e265729a4b2f50",
    "arm.py": "b337cc9cc1011389ef78e2ae44df6524c11321c6f3e6803bd9dada62b25aa65a",
}
PREFIX_PINS = {
    "job": "9d9a0a6d7c17e73c652c65b841175450ad55499f06c35941134530e19410c7d8",
    "accepted_terminal": "ef7c4aec9c446cb8067d16018d90b19566128e87870f9aa745528c8302b81be9",
    "negative_terminal": "216167ed1bc472cf925b6e32616c145d2fbc3574bef6cab8d80a067a0c66abd7",
    "negative_native": "8c4f6c92bbb86514e73531af7eb2a8b9f265d0ac9715668cd191943d520d794f",
}
V6_ROOT = HERE.parent / "hbq-grok-longform-transport-v6"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def predecessor():
    import hashlib
    path = HERE / "collector.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != COLLECTOR_SHA:
        raise ValueError("Frozen P4 collector differs")
    module = load("cwr_p4_v6_private_predecessor", path)
    return module


c = predecessor()
canonical, digest, require = c.canonical, c.digest, c.require


def profile(tools):
    for name, sha in V6_PINS.items():
        require(digest((V6_ROOT / name).read_bytes()) == sha, "V6 entry/loader source differs")
    sys.path.insert(0, str(tools.resolve()))
    derived = load("cwr_p4_v6_profile", V6_ROOT / "derived.py")
    commitment = derived.profile_commitment()
    require(commitment["profile_sha256"] == PROFILE_SHA, "V6 execution profile differs")
    return derived, commitment


def python_runtime():
    executable = Path(sys.executable).resolve()
    return {"version": sys.version, "cache_tag": sys.implementation.cache_tag,
            "executable_path_local_only": str(executable), "executable_sha256": digest(executable.read_bytes())}


def strict_native_answer(sample, row, binding, prompt, schema, receipts):
    require(row["endpoint"] == "grok", "V6 continuation is Grok only")
    native = json.loads((sample / "native-result.json").read_bytes())
    require(native["state"] == "completed", "Own native completion missing; no resend")
    identity = json.loads((sample / "native-identity.json").read_bytes())
    started = json.loads((sample / "attempt-started.json").read_bytes())
    session = identity["session_id"]
    if binding.get("policy") == POLICY:
        require(session != binding["source_prefix"][0]["native_thread_id"], "Original native vote must not be duplicated")
    require(str(uuid.UUID(session)) == session and started["session_id"] == session
            and identity["logical_sample_id"] == row["logical_sample_id"]
            and started["manifest_sha256"] == binding["manifest_sha256"]
            and started["logical_sample_id"] == row["logical_sample_id"]
            and started["prompt_sha256"] == row["prompt_sha256"]
            and started["schema_sha256"] == row["schema_sha256"]
            and started["job_sha256"] == digest((sample.parent / "job.json").read_bytes())
            and started["attempt"] == 1 and started["no_resend"] is True,
            "Own started/session/prompt/schema/job binding differs")
    require(datetime.fromisoformat(started["time"]).utcoffset() is not None, "Contact time lacks timezone")
    if binding.get("policy") == POLICY:
        derived, commitment = profile(Path(binding["tools_root_local_only"]))
        require(binding["v6_execution_profile"] == commitment and binding["v6_entry_sha256s"] == V6_PINS,
                "V6 job profile differs")
        module = derived.load_broker()
        require(native["result"]["runtime"]["adapter_version"] == 6
                and native["result"]["runtime"]["execution_contract"]["nonvisual_transport_contract"] == derived.CONTRACT,
                "Own native receipt is not exact v6")
    else:
        from model_work_queue import broker as module
        require(binding["collector_sha256"] == COLLECTOR_SHA
                and native["result"]["runtime"]["adapter_version"] == 5, "Original v5 receipt differs")
    raw_envelope = (sample / "native-envelope.json").read_bytes()

    class OwnEnvelope(module.Broker):
        def read_grok_native_envelope(self, descriptor):
            require(descriptor["sha256"] == digest(raw_envelope)
                    and descriptor["byte_length"] == len(raw_envelope), "Retained native envelope differs")
            return raw_envelope

    route = {**binding["route"], "output_schema": json.loads(schema)}
    control = {"control": {"version": 1, "state": "completed"}, "result": native["result"]}
    parser = OwnEnvelope(sample.parent)
    parsed = parser._parse_grok_exec_envelope(module._canonical(control), route,
        {"prompt": prompt.decode("utf-8")}, expected_session_id=session)
    require(parsed.state == "completed", "Full own native transport receipt rejected; no resend")
    return native["result"]["output"], session, True


c.native_answer = strict_native_answer


def verify_negative(sample, row, binding, *, pins=PREFIX_PINS):
    require(digest((sample / "terminal.json").read_bytes()) == pins["negative_terminal"]
            and digest((sample / "native-result.json").read_bytes()) == pins["negative_native"],
            "Exact positive no-contact evidence differs")
    terminal = json.loads((sample / "terminal.json").read_bytes())
    native = json.loads((sample / "native-result.json").read_bytes())
    require(terminal["state"] == native["state"] == "definitely_not_contacted"
            and native["result"] is None and terminal["no_resend"] is True
            and terminal["logical_sample_id"] == row["logical_sample_id"]
            and terminal["manifest_sha256"] == binding["manifest_sha256"]
            and terminal["job_sha256"] == pins["job"]
            and terminal.get("attempt_id") is None and terminal.get("native_thread_id") is None,
            "Negative contact disposition conflicts")
    failure = native["failure"]
    require(failure["category"] == "gate_error" and failure["code"] == "nonvisual_prompt_too_large"
            and failure["provider"] == "xai_grok_build" and failure["account_class"] == "subscription"
            and failure["status"] is None and failure["provider_error_type"] is None,
            "No-contact failure mechanism differs")
    require(all(not (sample / name).exists() for name in
                ["attempt-started.json", "native-envelope.json", "response.json"]),
            "Contact/completion evidence prohibits recovery")
    return {"logical_sample_id": row["logical_sample_id"], "endpoint_ordinal": row["endpoint_ordinal"],
            "original_terminal_sha256": pins["negative_terminal"], "native_result_sha256": pins["negative_native"],
            "disposition": "positive_no_contact_size_gate", "same_logical_slot": True, "new_vote": False}


def source_prefix(source, manifest, root, subset, validator, receipts, tools, *, pins=PREFIX_PINS):
    raw = (source / "job.json").read_bytes()
    require(digest(raw) == pins["job"], "Original job pin differs")
    binding = json.loads(raw)
    require(binding == c.job_binding(manifest, root, MANIFEST_SHA, "grok", tools,
        binding["route"], COLLECTOR_SHA, binding["payload_classification"]), "Original source job differs")
    require((source / "frozen-manifest.json").read_bytes() == (root / "manifest.json").read_bytes(),
            "Original source raw manifest differs")
    rows = [r for r in manifest["requests"] if r["endpoint"] == "grok"]
    samples = [c.sample_path(source, row) for row in rows]
    require([i + 1 for i, sample in enumerate(samples) if sample.exists()] == [1, 2],
            "Original prefix changed or an untouched slot is occupied")
    require({p.name for p in source.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-[0-9a-f]{12}", p.name)}
            == {p.name for p in samples[:2]}, "Unknown source attempt directory")
    accepted, _ = c.replay(samples[0], rows[0], manifest, binding, root, receipts, subset, validator)
    require(accepted["state"] == "accepted"
            and digest((samples[0] / "terminal.json").read_bytes()) == pins["accepted_terminal"],
            "Original completed slot 1 differs")
    c.replay(samples[1], rows[1], manifest, binding, root, receipts, subset, validator)
    negative = verify_negative(samples[1], rows[1], binding, pins=pins)
    return [{"endpoint_ordinal": 1, "logical_sample_id": rows[0]["logical_sample_id"],
             "disposition": "accepted_retained_original", "terminal_sha256": pins["accepted_terminal"],
             "native_thread_id": accepted["native_thread_id"], "new_vote": False}, negative]


def build_plan(manifest_path, source, tools):
    derived, commitment = profile(tools)
    manifest, root, subset, validator, receipts = c.load_manifest(manifest_path, MANIFEST_SHA, COLLECTOR_SHA, tools)
    prefix = source_prefix(source, manifest, root, subset, validator, receipts, tools)
    rows = [row for row in manifest["requests"] if row["endpoint"] == "grok"]
    require(len(rows) == 232 and [r["endpoint_ordinal"] for r in rows] == list(range(1, 233)), "Full P4 denominator differs")
    plan = {"schema_version": 1, "policy": POLICY, "execution_authority": False,
        "source_manifest_path_local_only": str(manifest_path.resolve()), "source_manifest_sha256": MANIFEST_SHA,
        "source_results_local_only": str(source.resolve()), "source_job_sha256": PREFIX_PINS["job"],
        "tools_root_local_only": str(tools.resolve()), "collector_sha256": digest(Path(__file__).read_bytes()),
        "predecessor_collector_sha256": COLLECTOR_SHA, "v6_entry_sha256s": V6_PINS,
        "v6_execution_profile": commitment, "python_runtime": python_runtime(), "source_prefix": prefix, "requests": rows[1:],
        "counts": {"full_endpoint_planned": 232, "full_matched_planned": 464, "accepted_original_retained": 1,
                   "positive_no_contact_recovery": 1, "untouched": 230, "continuation_requests": 231},
        "timeout_seconds": 900, "workers": 1, "automatic_retries": 0,
        "original_manifest_artifacts_commitment_sha256": digest(canonical(manifest["artifacts"])),
        "diagnostic_scalar_eligible": False, "model_read_whole_body_proven": False,
        "raw_own_history_exported_or_independently_recomputed": False}
    plan["content_sha256"] = digest(canonical(plan))
    return plan, manifest, root, subset, validator, receipts


def safe_output(output, protected, *, existing=False):
    output = output.resolve()
    repo = c.p.REPO.resolve()
    require(not output.is_relative_to(repo) and not repo.is_relative_to(output), "Private output overlaps repository")
    for path in protected:
        path = path.resolve()
        require(not output.is_relative_to(path) and not path.is_relative_to(output), "Output overlaps retained input")
    if not existing: require(not output.exists(), "Output must be fresh and nonexistent")


def job_binding(plan, plan_sha, manifest, root, route, tools):
    derived, commitment = profile(tools)
    require(route["nonvisual_transport_contract"] == derived.CONTRACT_NAME
            and derived.CONTRACT_NAME in route["capabilities"] and route["nonvisual_max_turns"] == 1
            and route["timeout_seconds"] == 900 and route["zero_charge"] is True,
            "Exact armed v6 geometry differs")
    command = route["command"]
    require(Path(command[0]).resolve() == Path(sys.executable).resolve()
            and plan["python_runtime"] == python_runtime(), "V6 interpreter must match frozen AST execution profile")
    require(Path(command[1]).resolve() == (V6_ROOT / "adapters/grok_exec.py").resolve()
            and command[-2:] == ["--tools-root", str(tools.resolve())], "V6 adapter entry/tools binding differs")
    old = c.job_binding(manifest, root, MANIFEST_SHA, "grok", tools, route,
                        digest(Path(__file__).read_bytes()), "public_synthetic")
    old.update(policy=POLICY, continuation_plan_sha256=plan_sha,
        predecessor_collector_sha256=COLLECTOR_SHA, source_prefix=plan["source_prefix"],
        source_job_sha256=plan["source_job_sha256"], tools_root_local_only=str(tools.resolve()),
        v6_execution_profile=commitment, v6_entry_sha256s=V6_PINS, python_runtime=python_runtime(), planned=232,
        continuation_requests=231, raw_own_history_exported_or_independently_recomputed=False)
    return old


def inventory(output, plan, manifest, binding, root, receipts, subset, validator):
    pending, states, identities = [], ["accepted_retained_original"], {plan["source_prefix"][0]["native_thread_id"]}
    for row in plan["requests"]:
        sample = c.sample_path(output, row)
        if not sample.exists(): pending.append(row); continue
        terminal, _ = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
        states.append(terminal["state"])
        if terminal.get("native_thread_id"):
            require(terminal["native_thread_id"] not in identities, "Duplicate own native identity across prefix/continuation")
            identities.add(terminal["native_thread_id"])
    require(not c.sample_path(output, next(r for r in manifest["requests"] if r["endpoint"] == "grok")).exists(),
            "Original completed slot 1 must never be recreated")
    if output.exists():
        expected = {c.sample_path(output, row).name for row in plan["requests"]}
        require(all(p.name in expected for p in output.iterdir() if p.is_dir()
                    and re.fullmatch(r"\d{4}-[0-9a-f]{12}", p.name)), "Unknown occupied continuation slot")
    return pending, states


def execute(output, pending, manifest, binding, root, receipts, subset, validator, broker, *, limit=None):
    for row in pending[:limit]:
        if (output / "STOP").exists(): c.t.note_stop(output); return 3
        if not c.grok_contact_allowed(binding["route"]): return 3
        state = c.collect_one(row, manifest, binding, root, output, subset, validator, receipts, broker=broker)
        print(json.dumps({"ordinal": row["endpoint_ordinal"], "state": state, "contract": row["contract"]}), flush=True)
        if state not in c.SETTLED: return 3
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-results", type=Path)
    parser.add_argument("--plan-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    if args.dry_run and not args.prepare: args.validate_only = True
    require(args.limit is None or args.limit > 0, "Limit must be positive")
    if args.prepare:
        require(all([args.manifest, args.source_results, args.plan_dir]), "Preparation needs manifest/source-results/plan-dir")
        plan, _, root, _, _, _ = build_plan(args.manifest, args.source_results, args.tools_root)
        safe_output(args.plan_dir, [root, args.source_results])
        raw = canonical(plan)
        dry_run = args.dry_run or args.validate_only
        if not dry_run:
            args.plan_dir.mkdir(parents=True, exist_ok=False)
            c.write_bytes(args.plan_dir / "plan.json", raw)
            c.write_bytes(args.plan_dir / "source-manifest.json", args.manifest.read_bytes())
            c.write_bytes(args.plan_dir / "source-job.json", (args.source_results / "job.json").read_bytes())
        print(json.dumps({"state": "provider_free_prepared", "dry_run": dry_run,
            "plan_sha256": digest(raw), "content_sha256": plan["content_sha256"], "counts": plan["counts"],
            "profile_sha256": PROFILE_SHA, "provider_calls": 0})); return 0
    require(all([args.plan, args.plan_sha256, args.results_dir]), "Collection needs pinned plan/results-dir")
    raw = args.plan.read_bytes(); require(digest(raw) == args.plan_sha256, "Frozen continuation plan pin differs")
    saved = json.loads(raw)
    plan, manifest, root, subset, validator, receipts = build_plan(Path(saved["source_manifest_path_local_only"]),
        Path(saved["source_results_local_only"]), args.tools_root)
    require(saved == plan and (args.plan.parent / "source-manifest.json").read_bytes() == (root / "manifest.json").read_bytes()
            and digest((args.plan.parent / "source-job.json").read_bytes()) == PREFIX_PINS["job"], "Frozen continuation lineage differs")
    output = args.results_dir.resolve()
    safe_output(output, [root, Path(plan["source_results_local_only"]), args.plan.parent], existing=output.exists())
    if args.route_root is None:
        require(args.validate_only and not output.exists(), "Execution requires an exact armed v6 route")
        print(json.dumps({"state": "provider_free_validated_route_pending", "planned": 232,
                          "accepted_original_retained": 1, "pending": 231, "provider_calls": 0})); return 0
    require(args.route_sha256 is not None, "Route pin required")
    route = next(r for r in json.loads((args.route_root / "routes.json").read_bytes())["routes"] if r["name"] == "grok-build-grok-4.7")
    require(digest(canonical(route).rstrip(b"\n")) == args.route_sha256, "Exact v6 route pin differs")
    binding = job_binding(plan, args.plan_sha256, manifest, root, route, args.tools_root)
    derived, _ = profile(args.tools_root)
    broker = derived.load_broker().Broker(args.route_root.resolve())
    broker._validate_route(route, verify_command_identity=True, validate_current_evidence=True)
    if output.exists():
        require(json.loads((output / "job.json").read_bytes()) == binding
                and (output / "frozen-manifest.json").read_bytes() == (root / "manifest.json").read_bytes()
                and (output / "continuation-plan.json").read_bytes() == raw, "Existing job/raw inputs differ")
    pending, states = inventory(output, plan, manifest, binding, root, receipts, subset, validator)
    if args.validate_only:
        print(json.dumps({"state": "provider_free_validated", "planned": 232, "pending": len(pending),
            "terminal_states": dict(Counter(states)), "provider_calls": 0, "profile_sha256": PROFILE_SHA})); return 0
    require(all(s in c.SETTLED or s == "accepted_retained_original" for s in states), "Occupied native failure stops; no resend")
    require(c.grok_contact_allowed(route), "Route expiry/campaign cutoff prevents new contact")
    if (output / "STOP").exists(): c.t.note_stop(output); return 3
    if not pending: return 0
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False); c.record(output / "job.json", binding)
        c.write_bytes(output / "frozen-manifest.json", (root / "manifest.json").read_bytes())
        c.write_bytes(output / "continuation-plan.json", raw)
    return execute(output, pending, manifest, binding, root, receipts, subset, validator, broker, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
