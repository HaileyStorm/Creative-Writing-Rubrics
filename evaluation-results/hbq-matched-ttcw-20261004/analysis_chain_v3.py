"""Versioned TTCW chain adapter; no collection or implicit human-label release.

The predecessor config is retained. A v3 source explicitly adds collector_policy
and, for label release, every source supplies lifecycle pins named invocation,
outer_terminal, run_started, native_handle, handle, and launcher. Each pin is
{path, sha256}. Metadata-only checks code pins without loading a config or data.
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
POLICY = "matched_ttcw_chain_analysis_v3"
OLD_SHA = "96de810dc955c5aac086990aa052b1980079fa67b7a825062045a2dc9805a229"
V3_SHA = "bfa5f34895d1eaa76ed6d1f5aca39f2b76919c2fb97780e5ed3531d7814599be"
V3_POLICY = "ttcw_untouched_suffix_execution_v3"
PROJECT_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
PROJECT_PATH = HERE.parent / "hbq-matched-hanna-20261004/prepare.py"
DENOMINATOR = 3108


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, expected):
    raw = Path(path).read_bytes()
    require(sha(raw) == expected, "Pinned artifact differs")
    return raw


def module(name, path, expected):
    checked(path, expected)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def lexical_projector():
    tree = ast.parse(checked(PROJECT_PATH, PROJECT_SHA))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "project_json"]
    require(len(selected) == 1, "Pinned lexical projector absent")
    namespace = {"json": json, "require": require}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(PROJECT_PATH), "exec"), namespace)
    return namespace["project_json"]


def retained_request_identity(raw, project):
    try:
        projected = project(raw, {"result": {"runtime": {"request_id_hash": True}}})
    except ValueError as error:
        if str(error) not in {"Required source metadata absent", "Expected source metadata object"}:
            raise
        project(raw, {})
        return None
    value = projected["result"]["runtime"]["request_id_hash"]
    require(value is None or isinstance(value, str), "Native request identity has an invalid type")
    return value or None


def runtime():
    # Overrides live only on this private predecessor instance.
    chain = module("ttcw_chain_v3_predecessor", HERE / "analysis_chain.py", OLD_SHA)
    loaded = chain.modules()
    loaded["project_json"] = lexical_projector()
    before = dict(sys.modules)
    try:
        loaded["suffix_v3"] = module("ttcw_chain_v3_native", HERE / "collector_suffix_v3.py", V3_SHA)
    finally:
        for name in set(sys.modules) - set(before):
            sys.modules.pop(name, None)
        for name, value in before.items():
            sys.modules[name] = value
    predecessor = chain.replay_source

    def dispatch(specification, *args):
        declared = specification.get("collector_policy")
        if declared == V3_POLICY:
            return replay_v3(specification, *args)
        require(declared in (None, loaded["collector_v2"].POLICY), "Unknown source collector policy")
        return predecessor(specification, *args)

    chain.replay_source = dispatch
    return chain, loaded


def replay_v3(specification, base, base_raw, artifacts, helper, loaded, subset, index):
    v3, old, prepare = loaded["suffix_v3"], loaded["analysis"], loaded["prepare"]
    require(specification["endpoint"] == "grok", "007 v3 source is Grok only")
    path, results = Path(specification["manifest_path"]), Path(specification["results_root"])
    raw = checked(path, specification["manifest_sha256"])
    source, root, rows, own_subset, validator = v3.load_manifest(path, specification["manifest_sha256"], "grok")
    old.validate_continuation(source, base, "grok", base_raw=base_raw, derived_root=root)
    through = source["continuation"]["reserved_through_endpoint_ordinal"]
    require(rows == [r for r in base["requests"] if r["endpoint"] == "grok"][through:],
            "v3 narrows/reorders original suffix")
    job_raw = checked(results / "job.json", specification["job_sha256"])
    job = json.loads(job_raw)
    require(job["collector_policy"] == V3_POLICY and job["collector_sha256"] == V3_SHA,
            "Explicit v3 collector job differs")
    expected = v3.job_binding(source, "grok", job["workers"], job["owner_declared_endpoint_headroom"], job["route"])
    require(job == expected, "v3 execution descendant binding differs")
    allowed = {v3.sample_path(results, row).name: row for row in rows}
    samples = sorted(p for p in results.iterdir() if p.is_dir() and re.match(r"\d{4}-", p.name))
    require(all(p.name in allowed for p in samples), "Attempt outside own original suffix")
    records, identities = {}, []
    for sample in samples:
        row = allowed[sample.name]
        rec = {"request": row, "state": "in_progress_or_unresolved", "accepted": None,
               "terminal_sha256": None, "source_index": index, "native_evidence_verified": False}
        if (sample / "terminal.json").is_file():
            terminal_raw = (sample / "terminal.json").read_bytes()
            terminal, answer = v3.replay(sample, row, job, root, own_subset, validator)
            require((sample / "terminal.json").read_bytes() == terminal_raw, "Terminal changed during replay")
            rec.update(state=terminal["state"], terminal_sha256=sha(terminal_raw),
                       evidence_sha256=sha(prepare.canonical({"terminal_sha256": sha(terminal_raw),
                           "retained_artifacts": terminal["retained_artifacts"],
                           "retention_errors": terminal.get("retention_errors", [])})),
                       retention_error_count=len(terminal.get("retention_errors", [])),
                       terminal_evidence_verified=not terminal.get("retention_errors"))
            if terminal["state"] in v3.SETTLED:
                rec["native_evidence_verified"] = True
                if answer is not None:
                    _, _, texts, context = v3.inputs(root, row)
                    rec["accepted"] = {"request": row, "response": answer,
                        "abstention": json.loads((sample / "acceptance.json").read_bytes())["abstention"],
                        "source_text": texts[row["sources"][0]["id"]], "context_text": context}
            identity_path, start_path = sample / "native-identity.json", sample / "attempt-started.json"
            identity = json.loads(identity_path.read_bytes()) if identity_path.is_file() else None
            started = json.loads(start_path.read_bytes()) if start_path.is_file() else None
            if identity is not None:
                session = identity["session_id"]
                require(str(uuid.UUID(session)) == session and identity["logical_sample_id"] == row["logical_sample_id"],
                        "Own reserved native identity differs")
                identities.append(("grok_session", sha(session.encode())))
            if started is not None:
                require(identity is not None and started["session_id"] == identity["session_id"]
                        and started["logical_sample_id"] == row["logical_sample_id"]
                        and started["job_sha256"] == specification["job_sha256"] and started["no_resend"] is True
                        and started["state"] == "before_contact" and started["attempt"] == 1
                        and started["manifest_sha256"] == specification["manifest_sha256"]
                        and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"],
                        "Own started native identity differs")
                rec["started_time"] = started["time"]
            if terminal["state"] in v3.SETTLED:
                require(identity is not None and started is not None, "Strict completion has no own started identity")
            native_path = sample / "native-result.json"
            if native_path.is_file():
                require("native-result.json" in terminal["retained_artifacts"], "Native result has no original terminal commitment")
                request_hash = retained_request_identity(native_path.read_bytes(), loaded["project_json"])
                if request_hash:
                    identities.append(("grok_request", request_hash))
        records[("grok", row["logical_sample_id"])] = rec
    require(len(set(identities)) == len(identities), "Duplicate native session/request within v3 source")
    return source, records, identities, {"endpoint": "grok", "manifest_sha256": sha(raw),
        "job_sha256": sha(job_raw), "collector_sha256": job["collector_sha256"], "collector_policy": V3_POLICY,
        "attempts": len(records), "states": dict(Counter(r["state"] for r in records.values())),
        "native_evidence_unverified": sum(not r["native_evidence_verified"] for r in records.values())}


def build(config, environment=None):
    chain, loaded = runtime() if environment is None else environment
    report, joined, endpoints, manifest, loaded = chain.build(config, loaded)
    report.update(policy=POLICY, analysis_sha256=sha(Path(__file__).read_bytes()),
                  predecessor_chain_sha256=OLD_SHA, suffix_v3_collector_sha256=V3_SHA,
                  own_lifecycles_verified=False, strict_original_admission_of_qualified_recoveries=False)
    return report, joined, endpoints, manifest, loaded, chain


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None, "Lifecycle timestamp has no timezone")
    return parsed


def verify_lifecycle(specification):
    pins = specification.get("lifecycle", {})
    require(all(name in pins for name in ("invocation", "outer_terminal", "run_started", "native_handle", "handle", "launcher")),
            "All-own lifecycle pins required before labels")
    def read(name):
        pin = pins[name]
        return json.loads(checked(pin["path"], pin["sha256"]))
    # A missing true outer is a stop, never a reason to infer return from handles.
    outer = read("outer_terminal")
    invocation = read("invocation")
    require(outer.get("exit_code") in (0, 3) and outer.get("no_resend") is True
            and outer.get("invocation_sha256") == pins["invocation"]["sha256"]
            and outer.get("native_exit_confirmed", True) is True, "Own true outer return unproved")
    checked(pins["launcher"]["path"], pins["launcher"]["sha256"])
    require(invocation.get("launcher_sha256") == pins["launcher"]["sha256"], "Own launcher binding differs")
    started, native, wrapper = read("run_started"), read("native_handle"), read("handle")
    argv = invocation["argv"]
    require(isinstance(argv, list) and "--validate-only" not in argv and native["argv"] == started["argv"] == argv
            and started["invocation_sha256"] == pins["invocation"]["sha256"]
            and started["launcher_sha256"] == pins["launcher"]["sha256"]
            and started["no_resend"] is native["no_resend"] is True,
            "Own native invocation/run-start binding differs")
    job = json.loads(checked(Path(specification["results_root"]) / "job.json", specification["job_sha256"]))
    candidates = [Path(arg) for arg in argv if Path(arg).name in {"collector.py", "collector_v2.py", "collector_suffix_v3.py"}]
    require(len(candidates) == 1, "Own collector argv missing/duplicated")
    checked(candidates[0], job["collector_sha256"])
    def arg(name):
        require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv), "Own invocation argument missing/duplicated")
        return argv[argv.index(name) + 1]
    require(Path(arg("--manifest")).resolve() == Path(specification["manifest_path"]).resolve()
            and Path(arg("--results-dir")).resolve() == Path(specification["results_root"]).resolve()
            and arg("--endpoint") == job["endpoint"] == specification["endpoint"]
            and job["manifest_sha256"] == specification["manifest_sha256"]
            and Path(wrapper["native_job"]).resolve() == Path(specification["results_root"]).resolve() / "job.json"
            and Path(wrapper["lifecycle"]).resolve() == Path(pins["outer_terminal"]["path"]).resolve().parent
            and wrapper["cwd"] == native["cwd"] and wrapper["pid"] != native["pid"], "Own lifecycle/job identity differs")
    if "workers" in job:
        require(int(arg("--workers")) == job["workers"] == wrapper["workers"], "Own worker allocation differs")
    if job.get("collector_policy") == V3_POLICY:
        require(arg("--manifest-sha256") == specification["manifest_sha256"]
                and int(arg("--endpoint-headroom")) == job["owner_declared_endpoint_headroom"]
                and arg("--route-sha256") == job["route_sha256"]
                and invocation["collector_sha256"] == job["collector_sha256"]
                and invocation["manifest_sha256"] == job["manifest_sha256"]
                and invocation["route_sha256"] == job["route_sha256"]
                and invocation["workers"] == job["workers"]
                and invocation["no_resend"] is wrapper["no_resend"] is True
                and outer.get("native_exit_confirmed") is True, "v3 execution argv differs")
        require(wrapper["argv"] == [str(HERE.parents[1] / ".venv/Scripts/python.exe"), "-B",
                    str(Path(pins["launcher"]["path"]).resolve()), "--run"]
                and Path(wrapper["cwd"]).resolve() == HERE.parents[1].resolve(), "v3 owning wrapper differs")
    beginning, running, ending = map(timestamp, (invocation["time"], started["time"], outer["time"]))
    require(beginning <= running <= ending, "Own lifecycle chronology differs")
    for receipt, lower, upper in ((wrapper, beginning, running), (native, running, ending)):
        if "process_creation_utc" in receipt:
            require(lower <= timestamp(receipt["process_creation_utc"]) <= upper
                    and receipt["creation_time_basis"] == "Windows GetProcessTimes on owned Popen handle",
                    "Own process creation chronology differs")
    return {"endpoint": job["endpoint"], "job_sha256": specification["job_sha256"],
        "invocation_sha256": pins["invocation"]["sha256"], "outer_terminal_sha256": pins["outer_terminal"]["sha256"],
        "exit_code": outer["exit_code"], "local_dispatch_return_only": True,
        "physical_remote_settlement_proven": False}, running, ending


def release_labels(config, report, joined, endpoints, manifest, loaded, chain, labels, *, explicit_release=False):
    require(explicit_release, "Explicit postprediction human-label release required")
    chain.label_release_gate(joined)
    for record in joined.values():
        require(record.get("terminal_evidence_verified", True), "Unverified retained terminal evidence keeps labels closed")
        if record["state"] in {"accepted", "semantic_rejected", "completed_schema_rejected"}:
            require(record.get("native_evidence_verified", True), "Unverified completed native evidence keeps labels closed")
        else:
            require(record["accepted"] is None, "Terminal missing observation cannot supply an accepted vote")
    lifecycles = []
    for index, specification in enumerate(config["sources"]):
        proof, beginning, ending = verify_lifecycle(specification)
        for record in joined.values():
            if record["source_index"] != index:
                continue
            row = record["request"]
            sample = Path(specification["results_root"]) / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
            start_path = sample / "attempt-started.json"
            if record["state"] in {"accepted", "semantic_rejected", "completed_schema_rejected"}:
                require(start_path.is_file(), "Completed observation has no own start")
            if start_path.is_file():
                started = json.loads(start_path.read_bytes())
                require(beginning <= timestamp(started["time"]) <= ending, "Attempt outside own returned lifecycle")
        lifecycles.append(proof)
    require({p["endpoint"] for p in lifecycles} == {"sol", "grok"}, "Both own endpoint lifecycles required")
    result = chain.release_labels(report, joined, endpoints, manifest, loaded, labels)
    result.update(own_lifecycles_verified=True, own_lifecycles=lifecycles)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    if args.metadata_only:
        require(args.config is None and args.config_sha256 is None and args.labels is None
                and not args.release_development_labels_postprediction, "Metadata-only cannot load config/data/labels")
        checked(HERE / "analysis_chain.py", OLD_SHA)
        checked(HERE / "collector_suffix_v3.py", V3_SHA)
        checked(PROJECT_PATH, PROJECT_SHA)
        print(json.dumps({"policy": POLICY, "state": "metadata_only_code_pins_verified", "planned_denominator": DENOMINATOR,
            "reserved_v3_prefix": 279, "planned_v3_suffix": 1275, "predecessor_sha256": OLD_SHA,
            "collector_v3_sha256": V3_SHA, "lexical_projector_sha256": PROJECT_SHA, "analysis_sha256": sha(Path(__file__).read_bytes()),
            "source_data_loaded": False, "native_attempts_loaded": False, "labels_opened": False, "provider_calls_made": 0}))
        return 0
    require(args.config is not None and args.config_sha256 is not None, "Pinned config required")
    require(args.release_development_labels_postprediction == (args.labels is not None), "Labels require explicit release")
    config = json.loads(checked(args.config, args.config_sha256))
    report, joined, endpoints, manifest, loaded, chain = build(config)
    if args.release_development_labels_postprediction:
        report = release_labels(config, report, joined, endpoints, manifest, loaded, chain, args.labels, explicit_release=True)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"policy": POLICY, "state": "blocked", "error_class": type(error).__name__,
                          "labels_opened": False, "provider_calls_made": 0}))
        raise SystemExit(3)
