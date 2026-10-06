"""Named original/suffix native replay; metadata mode reads code pins only.

Historical scoring, exact Preference decoding and conditional inference remain
the pinned predecessor's methods. Every supplied source must own a returned
lifecycle; a later suffix never turns a reserved failed observation into a vote.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "conditional_native_chain_analysis_v2"
ORIGINAL_POLICY = "mfa_conditional_native_once_v1"
ORIGINAL_SHA = "da9215976126058e9a16eff12c9dabc3bf1ccdb44228bdf875a1107d3d059513"
ANALYSIS_SHA = "f6675511ac92c575c93d7d7611a1e81685bcd104261e82e2b115cbc6aec99299"
MANIFEST_SHA = "95e1008505a7e4b7294f505bbfae02a6e99c5dd6d30c9d98aa80b52079b6b409"
SUFFIX_POLICY = "conditional_mfa_untouched_grok_suffix_execution_v3"
SUFFIX_SHA = "93cf40e6b46adb5c92f6e7f801555282c8ca235f745688dca2728b11e7d46a79"
SUFFIX_MANIFEST_SHA = "4f452fd8c48106ed1663aa665d0cbff145a297e39c4516029eed3b85c6a34d23"
SUFFIX_CONTENT_SHA = "b5f335d5e9cc7b8d81608bae6d893e66b49434219c96911e8267ec95be5ff153"
PROGRAM = Path.home() / "Documents/cwr-resume-control-20260919-r1/successor-program-20261004"
SUFFIX_PATH = PROGRAM / "mfa-confirmation/continue_conditional_untouched_suffix_v3_001.py"
PROJECT_PATH = HERE.parent / "hbq-matched-hanna-20261004/prepare.py"
PROJECT_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
LAUNCHERS = {
    (ORIGINAL_POLICY, "grok"): (PROGRAM / "mfa-confirmation/launch_conditional_benchmark_grok_001.py",
        "6f860982302d1cdf0c9deb920fb52cb0349f2a4fe444a3f2024a088630fd9726"),
    (SUFFIX_POLICY, "grok"): (PROGRAM / "mfa-confirmation/launch_conditional_untouched_suffix_v3_002.py",
        "836eb4f74b57d3b8392be62ab874b53256737c26ef22e823b4de7c5d2a62df6c"),
    (ORIGINAL_POLICY, "sol"): (PROGRAM / "mfa-confirmation/launch_conditional_sol_after_lamp_001.py",
        "e112cea9246c3917c1a12f85f9d99d13efa412250ad7ff6b2eb5407bebdb49f7"),
}
LIFECYCLE_NAMES = ("outer_terminal", "invocation", "launcher", "run_started", "native_handle", "handle")
OWNER = "01a10839-a735-7bf2-a05a-68afadb52755"
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, pin):
    raw = Path(path).read_bytes()
    require(sha(raw) == pin, "Exact retained source differs")
    return raw


def module(name, path, pin):
    checked(path, pin)
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def predecessor():
    return module("conditional_v2_private_analysis", HERE / "analysis.py", ANALYSIS_SHA)


def lexical_reader():
    tree = ast.parse(checked(PROJECT_PATH, PROJECT_SHA))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "project_json"]
    require(len(nodes) == 1, "Pinned lexical reader differs")
    scope = {"json": json, "require": require}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "conditional_identity_metadata", "exec"), scope)
    return scope["project_json"]


def runtime():
    old = predecessor()
    before, paths = dict(sys.modules), list(sys.path)
    try:
        collector, loaded = old.collector_runtime()
        suffix = module("conditional_v2_private_suffix", SUFFIX_PATH, SUFFIX_SHA)
    finally:
        sys.path[:] = paths
        for name in set(sys.modules) - set(before):
            sys.modules.pop(name, None)
        sys.modules.update(before)
    return old, collector, suffix, loaded, lexical_reader()


def argument(argv, name):
    require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv), "Own argv argument missing/duplicated")
    return argv[argv.index(name) + 1]


def timestamp(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "Own lifecycle chronology lacks timezone")
    return result


def verify_lifecycle(source, job):
    policy, endpoint = source["collector_policy"], source["endpoint"]
    require((policy, endpoint) in LAUNCHERS, "Unpinned owning launcher contract")
    guarded_sol = policy == ORIGINAL_POLICY and endpoint == "sol"
    pins = source["lifecycle"]
    names = (*LIFECYCLE_NAMES, "collector_run_started") if guarded_sol else LIFECYCLE_NAMES
    require(set(pins) == set(names), "All named own lifecycle pins required")
    read = lambda name: json.loads(checked(pins[name]["path"], pins[name]["sha256"]))
    outer = read("outer_terminal")
    require(outer.get("exit_code") in (0, 3) and outer.get("no_resend") is True
            and outer.get("invocation_sha256") == pins["invocation"]["sha256"], "Exact owning return required")
    launcher, pin = LAUNCHERS[(policy, endpoint)]
    require(Path(pins["launcher"]["path"]).resolve() == launcher.resolve()
            and pins["launcher"]["sha256"] == pin, "Named owning launcher differs")
    checked(launcher, pin)
    inv, started, native, handle = (read(n) for n in ("invocation", "run_started", "native_handle", "handle"))
    argv = inv["argv"]
    native_argv = inv["native_argv"] if guarded_sol else argv
    require(inv["owner"] == OWNER and inv["launcher_sha256"] == started["launcher_sha256"] == pin
            and inv["collector_sha256"] == job["collector_sha256"]
            and inv["manifest_sha256"] == job["manifest_sha256"] == source["manifest_sha256"]
            and started["invocation_sha256"] == pins["invocation"]["sha256"]
            and started["argv"] == native["argv"] == native_argv
            and started["no_resend"] is native["no_resend"] is inv["no_resend"] is True,
            "Own invocation/native/run-start binding differs")
    collector = HERE / "collector.py" if policy == ORIGINAL_POLICY else SUFFIX_PATH
    require((argv[:1] == [str(collector)] if guarded_sol else
                argv[:3] == [str(REPO / ".venv/Scripts/python.exe"), "-B", str(collector)])
            and "--validate-only" not in argv and argument(argv, "--manifest-sha256") == source["manifest_sha256"]
            and Path(argument(argv, "--manifest")).resolve() == Path(source["manifest_path"]).resolve()
            and Path(argument(argv, "--results-dir")).resolve() == Path(source["results_root"]).resolve()
            and int(argument(argv, "--workers")) == job["workers"] == inv["workers"] == handle["workers"]
            and int(argument(argv, "--endpoint-headroom")) == job["owner_declared_endpoint_headroom"]
            and Path(handle["native_job"]).resolve() == Path(source["results_root"]).resolve() / "job.json"
            and Path(handle["lifecycle"]).resolve() == Path(pins["outer_terminal"]["path"]).resolve().parent
            and Path(native["cwd"]).resolve() == Path(handle["cwd"]).resolve() == REPO.resolve()
            and native["pid"] != handle["pid"], "Owning argv/job/handle differs")
    require(handle["argv"] == [str(REPO / ".venv/Scripts/python.exe"), "-B", str(launcher), "--run"],
            "Exact supported owning --run wrapper differs")
    if guarded_sol:
        require(argument(argv, "--endpoint") == job["endpoint"] == "sol"
                and argument(argv, "--payload-classification") == job["payload_classification"] == "public_repo"
                and inv["extraction_sha256"] == job["extraction_sha256"]
                and job["workers"] == 2 and outer.get("native_exit_confirmed") is True
                and inv["policy"] == "conditional_sol2_after_exact_lamp_disk_gap_terminal_join_v1"
                and native_argv == [str(REPO / ".venv/Scripts/python.exe"), "-B", str(launcher), "--native-run"]
                and set(inv["owner_attestations"]) == {"global_headroom_verified", "lamp_sol2_released", "outbound_disclosure_acknowledged"}
                and all(v is True for v in inv["owner_attestations"].values())
                and inv["runtime_augmentation"] == {"policy": "conditional_sol_disk_stop_before_contact_v1",
                    "guard_source_sha256": pin, "min_launch_free_bytes": 1073741824, "min_contact_free_bytes": 268435456,
                    "original_callback_preserved": True, "original_collector_job_and_admission_unchanged": True},
                "Exact named Sol guarded native-child contract differs")
        require(started["source_release_sha256"] == sha((json.dumps(inv["source_release"], sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()),
                "Own guarded Sol source-release commitment differs")
    elif policy == ORIGINAL_POLICY:
        require(argument(argv, "--endpoint") == endpoint == job["endpoint"]
                and argument(argv, "--payload-classification") == job["payload_classification"] == "public_repo"
                and inv["extraction_sha256"] == job["extraction_sha256"]
                and outer.get("native_dispatch_started") is True
                and all(inv.get(k) is True for k in ("owner_global_headroom_verified", "owner_current_route_verified",
                                                      "owner_outbound_disclosure_confirmed")),
                "Original actual-wait lifecycle contract differs")
    else:
        require(endpoint == job["endpoint"] == "grok" and job["workers"] == 2
                and job["persistence_guard_policy"] == "conditional_contact_time_minimum_free_disk_v1"
                and job["minimum_free_disk_bytes"] == 268435456 and inv["minimum_launch_free_disk_bytes"] == 1073741824
                and job["owner_lifecycle_invocation_sha256"] == pins["invocation"]["sha256"]
                and Path(job["owner_lifecycle_root"]).resolve() == Path(pins["outer_terminal"]["path"]).resolve().parent
                and argument(argv, "--owner-lifecycle-root") == job["owner_lifecycle_root"]
                and argument(argv, "--stop-path") == job["external_stop_path"]
                and outer.get("native_exit_confirmed") is True
                and set(inv["owner_attestations"]) == {"global_headroom_verified", "current_route_verified",
                    "mfa85_grok2_released", "outbound_disclosure_acknowledged"}
                and all(v is True for v in inv["owner_attestations"].values())
                and all(argv.count(flag) == 1 for flag in ("--execute-native", "--owner-global-headroom-verified",
                                                            "--owner-current-route-verified")),
                "Suffix requires actual execution and all owning attestations")
    if endpoint == "grok":
        require(argument(argv, "--route-sha256") == job["route_sha256"] == inv["route_sha256"], "Own route pin differs")
        require(Path(argument(argv, "--route-root")).resolve()
                == (Path.home() / ".codex/state/model-work-queue-cwr-placeholder-r31").resolve(), "Own route root differs")
    beginning, running, ending = map(timestamp, (inv["time"], started["time"], outer["time"]))
    require(beginning <= running <= ending, "Own returned chronology differs")
    if policy == SUFFIX_POLICY or guarded_sol:
        for receipt, lower, upper in ((handle, beginning, running), (native, running, ending)):
            require(receipt.get("creation_time_basis") == "Windows GetProcessTimes on owned Popen handle"
                    and lower <= timestamp(receipt["process_creation_utc"]) <= upper, "Own native creation receipt differs")
    if guarded_sol:
        collector_started = read("collector_run_started")
        require(collector_started["invocation_sha256"] == pins["invocation"]["sha256"]
                and collector_started["argv"] == argv and collector_started["no_resend"] is True
                and collector_started["runtime_augmentation"] == inv["runtime_augmentation"]["policy"]
                and timestamp(native["process_creation_utc"]) <= timestamp(collector_started["time"]) <= ending,
                "Own guarded Sol collector start differs")
        running = timestamp(collector_started["time"])
    return {"verified": True, "endpoint": endpoint, "collector_policy": policy, "job_sha256": source["job_sha256"],
        "lifecycle_pins": pins, "owning_wrapper_raw_invocation_argument": False,
        "return_basis": "pinned owning child wait and joined dispatcher",
        "native_exit_confirmed": outer.get("native_exit_confirmed"),
        "runtime_augmentation": inv.get("runtime_augmentation"),
        "persistence_guard_policy": job.get("persistence_guard_policy"), "minimum_free_disk_bytes": job.get("minimum_free_disk_bytes"),
        "minimum_launch_free_disk_bytes": inv.get("minimum_launch_free_disk_bytes"), "physical_remote_settlement_proven": False}, running, ending


def optional(project, raw, fields):
    project(raw, {})
    values = {}
    for name in fields:
        try:
            values.update(project(raw, {name: True}))
        except ValueError as error:
            if str(error) != "Required source metadata absent":
                raise
    return values


def native_ids(sample, row, terminal, c, project):
    ids = []
    path = sample / "native-identity.json"
    if path.is_file():
        value = project(path.read_bytes(), {"logical_sample_id": True, "session_id": True})
        require(value["logical_sample_id"] == row["logical_sample_id"], "Reserved native logical identity differs")
        session = value["session_id"]
        if row["endpoint"] == "sol":
            require(session is None, "Historical Sol native identity must be a null placeholder")
        else:
            require(row["endpoint"] == "grok" and str(uuid.UUID(session)) == session, "Reserved native session differs")
            ids.append(("grok_session", sha(session.encode())))
    path = sample / "native-result.json"
    if row["endpoint"] == "grok" and path.is_file():
        try:
            value = project(path.read_bytes(), {"result": {"runtime": {"request_id_hash": True}}})
            identity = value["result"]["runtime"]["request_id_hash"]
            require(identity is None or isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{64}", identity), "Native request ID differs")
            if identity:
                ids.append(("grok_request", identity))
        except ValueError as error:
            if str(error) not in {"Required source metadata absent", "Expected source metadata object"}:
                raise
    if row["endpoint"] == "sol":
        threads = set()
        for events in sample.glob("responses/*.events.jsonl"):
            for line in events.read_bytes().splitlines():
                if line.strip():
                    value = optional(project, line, ("type", "thread_id", "turn_id"))
                    if value.get("thread_id"):
                        threads.add(value["thread_id"])
        if terminal["state"] in c.SETTLED:
            value = project(path.read_bytes(), {"provider_artifacts": {"codex_receipt": True}, "reported": {"session_id": True}})
            receipt = value["provider_artifacts"]["codex_receipt"]
            identity = project(c.pinned(sample, receipt["path"], receipt), {"thread_id": True, "turn_id": True})
            require(identity["thread_id"] == value["reported"]["session_id"] and bool(identity["turn_id"]), "Own native receipt identity differs")
            threads.add(identity["thread_id"])
        require(len(threads) <= 1, "Foreign native thread in own attempt")
        for thread in threads:
            require(str(uuid.UUID(thread)) == thread, "Native thread ID differs")
            ids.append(("sol_thread", sha(thread.encode())))
    require(terminal["state"] not in c.SETTLED or bool(ids), "Completed observation lacks own native identity")
    return ids


def merge(joined, records, seen, entry, answer, identities):
    key = (entry["endpoint"], entry["logical_sample_id"])
    require(key not in joined, "Original logical observation occupied twice")
    require(len(set(identities)) == len(identities) and not seen.intersection(identities), "Native identity reused across logical observations")
    require(answer is None or entry["state"] == "accepted" and entry["original_strict_native_verified"] is True,
            "Rejected or failed response cannot supply a vote")
    seen.update(identities)
    joined[key] = entry
    if answer is not None:
        records.append({"request": entry["request"], "response": answer, "replay": dict(entry)})


def label_gate(ledger, proofs, explicit_release):
    require(explicit_release is True and len(ledger) == 10340
            and len({(e["endpoint"], e["logical_sample_id"]) for e in ledger}) == 10340
            and Counter(e["endpoint"] for e in ledger) == {"sol": 5170, "grok": 5170}
            and all(e.get("terminal_verified") is True and e["state"] not in {"untouched", "started_unresolved"}
                    and (e["state"] not in {"accepted", "semantic_rejected"} or e["original_strict_native_verified"] is True) for e in ledger)
            and bool(proofs) and {p["endpoint"] for p in proofs} == {"sol", "grok"}
            and all(p["verified"] is True for p in proofs), "Explicit release and every owning return/all10340 terminals required")


def build(config, environment=None):
    old, c, suffix, loaded, project = runtime() if environment is None else environment
    tools = Path(config["tools_root"])
    path = Path(config["manifest_path"])
    require(config["manifest_sha256"] == MANIFEST_SHA, "Original scientific manifest required")
    checked(path, MANIFEST_SHA)
    extraction = Path(config["extraction_receipt"])
    checked(extraction, config["extraction_sha256"])
    manifest, root, subset, validator = c.load_manifest(path, MANIFEST_SHA, tools, extraction)
    planned = {(r["endpoint"], r["logical_sample_id"]): r for r in manifest["requests"]}
    require(len(planned) == 10340 and Counter(r["endpoint"] for r in planned.values()) == {"sol": 5170, "grok": 5170}, "Full scientific denominator differs")
    joined, records, seen, proofs = {}, [], set(), []
    outputs = set()
    for index, source in enumerate(config["sources"]):
        policy, endpoint = source["collector_policy"], source["endpoint"]
        require(policy in {ORIGINAL_POLICY, SUFFIX_POLICY} and endpoint in {"sol", "grok"}, "Unknown native source policy")
        output = Path(source["results_root"])
        require(output.resolve() not in outputs, "Source result root duplicated")
        outputs.add(output.resolve())
        job = json.loads(checked(output / "job.json", source["job_sha256"]))
        proof, beginning, ending = verify_lifecycle(source, job)
        if policy == ORIGINAL_POLICY:
            require(Path(source["manifest_path"]).resolve() == path.resolve() and source["manifest_sha256"] == MANIFEST_SHA
                    and job["policy"] == policy and job["collector_sha256"] == ORIGINAL_SHA, "Original source contract differs")
            expected = c.job_binding(manifest, MANIFEST_SHA, endpoint, tools, workers=job["workers"],
                headroom=job["owner_declared_endpoint_headroom"], classification="public_repo", route=job.get("route"))
            c.verify_job_binding(output, expected)
            own, own_root, own_subset, own_validator = manifest, root, subset, validator
            rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
        else:
            require(endpoint == "grok" and source["manifest_sha256"] == SUFFIX_MANIFEST_SHA
                    and job["policy"] == SUFFIX_POLICY and job["collector_sha256"] == SUFFIX_SHA, "Explicit suffix contract differs")
            own, own_root, rows, lineage, own_subset, own_validator = suffix.load_manifest(Path(source["manifest_path"]), SUFFIX_MANIFEST_SHA)
            require(rows == [r for r in manifest["requests"] if r["endpoint"] == "grok"][68:], "Suffix scientific requests differ")
            expected = suffix.job_binding(own, lineage, job["route"], job["owner_declared_endpoint_headroom"],
                Path(job["external_stop_path"]), Path(job["owner_lifecycle_root"]))
            expected["owner_lifecycle_invocation_sha256"] = source["lifecycle"]["invocation"]["sha256"]
            require(job == expected, "Exact suffix owning job differs")
        proofs.append(proof)
        allowed = {c.sample_path(output, row).name: row for row in rows}
        samples = sorted(p for p in output.iterdir() if p.is_dir() and re.match(r"\d{4}-", p.name))
        require(all(p.name in allowed for p in samples), "Occupied attempt outside own scientific membership")
        for sample in samples:
            row = allowed[sample.name]
            require(planned[(endpoint, row["logical_sample_id"])] == row, "Own original descriptor differs")
            entry = {"endpoint": endpoint, "logical_sample_id": row["logical_sample_id"], "request_sha256": row["request_sha256"],
                "request": row, "state": "started_unresolved", "source_index": index, "original_strict_native_verified": False}
            answer, identities = None, []
            if (sample / "terminal.json").is_file():
                raw = (sample / "terminal.json").read_bytes()
                if policy == ORIGINAL_POLICY:
                    terminal, answer = c.replay(sample, row, own, job, own_root, loaded["receipts"], own_subset, own_validator)
                else:
                    terminal, answer = suffix.replay(sample, row, own, job, own_root, own_subset, own_validator)
                require((sample / "terminal.json").read_bytes() == raw and not terminal.get("retention_errors"), "Terminal/evidence changed or unavailable")
                entry.update(state=terminal["state"], terminal_sha256=sha(raw), terminal_verified=True,
                    original_strict_native_verified=terminal["state"] in c.SETTLED)
                identities = native_ids(sample, row, terminal, c, project)
                entry["native_identity_commitments"] = [list(i) for i in identities]
                identity_paths = [sample / "native-identity.json", sample / "native-result.json",
                                  *sample.glob("responses/*.events.jsonl")]
                entry["native_identity_metadata_artifacts"] = {p.relative_to(sample).as_posix(): sha(p.read_bytes())
                    for p in identity_paths if p.is_file()}
            if (sample / "attempt-started.json").is_file():
                start = project((sample / "attempt-started.json").read_bytes(), {"time": True, "logical_sample_id": True,
                    "job_sha256": True, "manifest_sha256": True, "prompt_sha256": True, "schema_sha256": True, "attempt": True, "no_resend": True})
                require(start["logical_sample_id"] == row["logical_sample_id"] and start["job_sha256"] == source["job_sha256"]
                        and start["manifest_sha256"] == source["manifest_sha256"] and start["prompt_sha256"] == row["prompt_sha256"]
                        and start["schema_sha256"] == row["schema_sha256"] and start["attempt"] == 1 and start["no_resend"] is True
                        and beginning <= timestamp(start["time"]) <= ending, "Own attempt outside returned native lifecycle")
            else:
                require(entry["state"] not in c.SETTLED, "Completed observation lacks own start")
            merge(joined, records, seen, entry, answer, identities)
    ledger = [joined.get(k, {"endpoint": r["endpoint"], "logical_sample_id": r["logical_sample_id"],
        "request_sha256": r["request_sha256"], "state": "untouched", "original_strict_native_verified": False}) for k, r in planned.items()]
    selection = json.loads(c.pinned(root, "selection.json", manifest["artifacts"]["selection.json"]))
    core = loaded["core"]
    loaded["modules"] = core.load_modules(root / "registry/all_modules.yaml")
    loaded["bundle"] = next(b for b in core.load_bundles(root / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
    profiles, decisions = old.predictions(c, manifest, selection, records, loaded, root)
    report = {"policy": POLICY, "analysis_sha256": sha(Path(__file__).read_bytes()), "predecessor_analysis_sha256": ANALYSIS_SHA,
        "manifest_sha256": MANIFEST_SHA, "suffix_collector_sha256": SUFFIX_SHA, "planned_requests": 10340,
        "planned_ballots": 3276, "accepted_requests": len(records), "terminal_states": dict(Counter(e["endpoint"] + ":" + e["state"] for e in ledger)),
        "own_lifecycles": proofs, "diagnostics": old.diagnostics(profiles, decisions), "labels_opened": False,
        "provider_calls": 0, "new_votes": 0, "candidate_promoted": False, "fresh_confirmation_claim": False,
        "human_alignment_claim": False, "physical_contact_cardinality_proven": False, "qualified_recovery_admitted": False}
    return report, ledger, profiles, decisions, selection, (old, c, manifest, root, loaded)


def release_labels(report, ledger, decisions, selection, environment, source_root, *, explicit_release=False):
    label_gate(ledger, report["own_lifecycles"], explicit_release)
    old, c, _, _, _ = environment
    # The predecessor's gate is also preserved after every individual source gate.
    outers = {e: {"verified": all(p["verified"] is True for p in report["own_lifecycles"] if p["endpoint"] == e),
        "source_lifecycles": [p for p in report["own_lifecycles"] if p["endpoint"] == e]} for e in ("sol", "grok")}
    ballots = old.released_ballots(c, selection, source_root, ledger, outers, True)
    inference = [old.stratum_inference(ballots, decisions, endpoint, panel, condition, old.profile())
        for endpoint in ("sol", "grok") for panel in ("expert", "lay") for condition in ("fewshot", "finetuned", "POOLED")]
    guards = []
    for endpoint in ("sol", "grok"):
        for panel in ("expert", "lay"):
            rows = [r for r in inference if r["endpoint"] == endpoint and r["panel"] == panel]
            field = "expert_numeric_guard" if panel == "expert" else "lay_noninferiority_numeric_guard"
            guards.append({"endpoint": endpoint, "panel": panel, "all_reference_conditions_and_pooled_numeric_guard":
                len(rows) == 3 and all(r[field] for r in rows), "unused_confirmation_eligibility_verified": False, "promotion_authority": False})
    report.update(labels_opened=True, inference=inference, conditional_numeric_guards=guards,
        reuse_limits="Crossed writer/rater labels do not establish independent humans; leaveouts are sensitivity points.")
    return ballots


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--release-conditional-labels-postprediction", action="store_true")
    parser.add_argument("--sealed-source-root", type=Path)
    args = parser.parse_args(argv)
    if args.metadata_only:
        require(args.config is args.config_sha256 is args.output_root is args.sealed_source_root is None
                and not args.release_conditional_labels_postprediction, "Metadata-only cannot touch source/results/labels")
        old = predecessor()
        old.profile()
        for path, pin in [(HERE / "collector.py", ORIGINAL_SHA), (SUFFIX_PATH, SUFFIX_SHA),
                          (PROJECT_PATH, PROJECT_SHA), *LAUNCHERS.values()]:
            checked(path, pin)
        print(json.dumps({"policy": POLICY, "state": "metadata_only_code_pins_verified", "analysis_sha256": sha(Path(__file__).read_bytes()),
            "predecessor_analysis_sha256": ANALYSIS_SHA, "planned_requests": 10340, "planned_per_endpoint": 5170,
            "original_unique_texts": 199, "reserved_grok_prefix": 68, "untouched_grok_suffix": 5102,
            "manifest_sha256": MANIFEST_SHA, "suffix_manifest_sha256": SUFFIX_MANIFEST_SHA,
            "suffix_manifest_content_sha256": SUFFIX_CONTENT_SHA, "suffix_collector_sha256": SUFFIX_SHA,
            "source_data_loaded": False, "attempts_loaded": False, "labels_opened": False, "provider_calls": 0,
            "runtime_native_and_human_results_verified": False, "original_sol_guarded_launcher_sha256": LAUNCHERS[(ORIGINAL_POLICY, "sol")][1]}, sort_keys=True))
        return 0
    require(args.config is not None and args.config_sha256 is not None, "Pinned chain config required")
    require(bool(args.sealed_source_root) == args.release_conditional_labels_postprediction, "Labels require explicit release")
    config = json.loads(checked(args.config, args.config_sha256))
    report, ledger, profiles, decisions, selection, environment = build(config)
    ballots = []
    if args.release_conditional_labels_postprediction:
        ballots = release_labels(report, ledger, decisions, selection, environment, args.sealed_source_root, explicit_release=True)
    if args.output_root:
        old, c, _, root, _ = environment
        protected = [root, Path(config["extraction_receipt"]).parent, *(Path(s["results_root"]) for s in config["sources"])]
        if args.sealed_source_root:
            protected.append(args.sealed_source_root)
        output = c.prepare.extract.private_output(args.output_root, protected)
        files = {"implementation/analysis_chain_v2.py": Path(__file__).read_bytes(), "config.json": checked(args.config, args.config_sha256),
            "report.json": old.canonical(report), "private-ledger.json": old.canonical({"original_requests": ledger,
                "profiles": [{"identity": list(k), **v} for k, v in profiles.items()],
                "pair_decisions": [{"identity": list(k), "decision": v} for k, v in decisions.items()], "released_ballots": ballots})}
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            c.prepare.extract.write_new(output / name, raw)
        c.prepare.extract.write_new(output / "receipt.json", old.canonical({"policy": POLICY, "config_sha256": args.config_sha256,
            "artifacts": {n: {"sha256": sha(raw), "bytes": len(raw)} for n, raw in files.items()},
            "new_votes": 0, "provider_calls": 0, "labels_opened": report["labels_opened"]}))
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"policy": POLICY, "state": "blocked", "error_class": type(error).__name__, "provider_calls": 0}))
        raise SystemExit(3)
