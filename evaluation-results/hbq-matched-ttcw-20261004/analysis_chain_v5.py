"""Frozen009 analysis descendant; metadata mode opens only pinned code.

Historical admissions and full3108 label gates remain on isolated predecessors.
The009 receipt proves joined local dispatch, not independent inflight measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
POLICY = "matched_ttcw_chain_analysis_v5"
PREDECESSOR_SHA = "c8f6aad7b238950495204bd6389b89507bf101dfd3d480c14518be564e7106be"
COLLECTOR_SHA = "c4d9cc6a6ec3744d1af9c844a2e4841eda648bcf856e1a8bd0c29c7f5840bc2f"
COLLECTOR_POLICY = "ttcw_untouched_suffix_execution_v5"
MANIFEST_SHA = "b3ae25cbd36674bdffdedf4c4cf58a2e51be109b86f183b72b3b490d70dd0137"
CONTENT_SHA = "6b1965790c11b13c98c9b743c2c97dc544e944930d177b9fa10c91cdc58e71ac"
OWNER = "01a10839-a735-7bf2-a05a-68afadb52755"
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)


def predecessor():
    path = HERE / "analysis_chain_v4.py"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == PREDECESSOR_SHA, "Pinned v4 analysis differs")
    spec = importlib.util.spec_from_file_location("ttcw_analysis_v5_private_predecessor", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def outer_before_reads(specification, prior):
    pin = specification.get("lifecycle", {}).get("outer_terminal")
    require(pin is not None, "Own true outer required before attempt reads")
    outer = json.loads(prior.checked(pin["path"], pin["sha256"]))
    invocation = specification["lifecycle"]["invocation"]["sha256"]
    require(outer.get("exit_code") in (0, 3) and outer.get("no_resend") is True
            and outer.get("invocation_sha256") == invocation
            and outer.get("native_exit_confirmed", True) is True, "Own true outer return unproved")


def dispatch_receipt(specification, job, prior):
    pin = specification["lifecycle"].get("dispatch_terminal")
    path = Path(specification["results_root"]) / "dispatch-terminal.json"
    require(pin is not None and Path(pin["path"]).resolve() == path.resolve(), "Own dispatcher receipt pin required")
    value = json.loads(prior.checked(path, pin["sha256"]))
    require(value["policy"] == COLLECTOR_POLICY and value["job_sha256"] == specification["job_sha256"]
            and value["owner_lifecycle_invocation_sha256"] == job["owner_lifecycle_invocation_sha256"]
            and value["workers"] == job["workers"] and value["inflight_at_terminal"] == 0
            and value["automatic_retries"] == 0 and value["human_release_eligible"] is False
            and isinstance(value["stopped"], bool), "Own joined dispatcher binding differs")
    states = value["states"]
    require(all(isinstance(r["ordinal"], int) and 338 <= r["ordinal"] <= 1554 for r in states)
            and len({r["ordinal"] for r in states}) == len(states), "Dispatcher has foreign/duplicate original positions")
    return value


def runtime():
    previous = predecessor()
    chain, loaded = previous.runtime()
    prior = loaded["analysis_v3"]
    before, paths = dict(sys.modules), list(sys.path)
    try:
        native = prior.module("ttcw_analysis_v5_native", HERE / "collector_suffix_v5.py", COLLECTOR_SHA)
    finally:
        sys.path[:] = paths
        for name in set(sys.modules) - set(before):
            sys.modules.pop(name, None)
        sys.modules.update(before)
    loaded["suffix_v5"] = native
    old_replay, old_lifecycle = chain.replay_source, prior.verify_lifecycle
    lifecycle = previous.derive(prior, "verify_lifecycle", previous.PREDECESSOR_SHA,
        [('{"collector.py", "collector_v2.py", "collector_suffix_v3.py"}',
          '{"collector_suffix_v5.py"}'),
         ('and arg("--endpoint") == job["endpoint"] == specification["endpoint"]',
          'and "--endpoint" not in argv and job["endpoint"] == specification["endpoint"] == "grok"'),
         ('str(Path(pins["launcher"]["path"]).resolve()), "--run"]',
          'str(Path(pins["launcher"]["path"]).resolve()), "--run", "--invocation-sha256", pins["invocation"]["sha256"]]')],
        {"sha": prior.sha, "V3_POLICY": COLLECTOR_POLICY})

    def verify_lifecycle(specification):
        outer_before_reads(specification, prior)
        if specification.get("collector_policy") != COLLECTOR_POLICY:
            return old_lifecycle(specification)
        pins = specification["lifecycle"]
        job = json.loads(prior.checked(Path(specification["results_root"]) / "job.json", specification["job_sha256"]))
        attestations = previous.execution_attestations(job)
        require(job["collector_policy"] == COLLECTOR_POLICY and job["collector_sha256"] == COLLECTOR_SHA
                and job["manifest_sha256"] == specification["manifest_sha256"] == MANIFEST_SHA
                and job["owner_lifecycle_invocation_sha256"] == pins["invocation"]["sha256"]
                and job["own_lifecycle_binding_verified"] is True, "v5 actual own job binding differs")
        proof, beginning, ending = lifecycle(specification)
        invocation = json.loads(prior.checked(pins["invocation"]["path"], pins["invocation"]["sha256"]))
        argv = invocation["argv"]
        require(invocation["owner"] == OWNER and invocation["owner_attestations"] == attestations
                and all(argv.count(flag) == 1 for flag in previous.FLAGS), "v5 actual owner execution differs")
        def path_arg(name):
            require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv), "Missing/duplicate v5 path argument")
            return Path(argv[argv.index(name) + 1]).resolve()
        own = Path(pins["invocation"]["path"]).resolve().parent
        require(path_arg("--owner-lifecycle-root") == own == Path(job["owner_lifecycle_root"]).resolve()
                and path_arg("--route-root") == (native.TOOLS.parent / "state/model-work-queue-cwr-placeholder-r31").resolve(),
                "v5 own lifecycle/route path differs")
        for name in ("handle", "native_handle"):
            receipt = json.loads(prior.checked(pins[name]["path"], pins[name]["sha256"]))
            require("process_creation_utc" in receipt
                    and receipt["creation_time_basis"] == "Windows GetProcessTimes on owned Popen handle",
                    "v5 owned process creation proof required")
        dispatch_receipt(specification, job, prior)
        proof.update(collector_policy=COLLECTOR_POLICY, collector_sha256=COLLECTOR_SHA,
            execution_attestations_verified=True, native_dispatcher_terminal_receipt=True,
            code_backed_joined_local_drain=True, inflight_zero_natively_measured=False,
            dispatch_terminal_sha256=pins["dispatch_terminal"]["sha256"])
        return proof, beginning, ending

    def dispatch(specification, *args):
        verify_lifecycle(specification)
        if specification.get("collector_policy") == COLLECTOR_POLICY:
            return replay_v5(specification, *args, prior=prior, previous=previous)
        return old_replay(specification, *args)

    prior.verify_lifecycle = verify_lifecycle
    chain.replay_source = dispatch
    loaded["analysis_v4"] = previous
    return chain, loaded


def replay_v5(specification, base, base_raw, artifacts, helper, loaded, subset, index, *, prior, previous):
    native = loaded["suffix_v5"]
    job = json.loads(prior.checked(Path(specification["results_root"]) / "job.json", specification["job_sha256"]))
    attestations = previous.execution_attestations(job)
    invocation_sha = specification["lifecycle"]["invocation"]["sha256"]
    def binding(manifest, endpoint, workers, headroom, route):
        require(endpoint == "grok", "009 has no Sol execution rows")
        return native.job_binding(manifest, workers, headroom, route, attestations, invocation_sha)
    proxy = SimpleNamespace(load_manifest=native.load_manifest, replay=native.replay, job_binding=binding,
        sample_path=native.native.sample_path, inputs=native.native.inputs, SETTLED=native.native.SETTLED)
    scope = dict(vars(prior), V3_POLICY=COLLECTOR_POLICY, V3_SHA=COLLECTOR_SHA)
    replay = FunctionType(prior.replay_v3.__code__, scope, "explicit_native_v5_replay")
    result = replay(specification, base, base_raw, artifacts, helper, dict(loaded, suffix_v3=proxy), subset, index)
    dispatch = dispatch_receipt(specification, job, prior)
    observed = {r["request"]["endpoint_ordinal"]: r["state"] for r in result[1].values()}
    require(observed == {r["ordinal"]: r["state"] for r in dispatch["states"]}, "Dispatcher/replayed attempt dispositions differ")
    return result


def build(config, environment=None):
    chain, loaded = runtime() if environment is None else environment
    prior = loaded["analysis_v3"]
    for specification in config["sources"]:
        prior.verify_lifecycle(specification)
    report, joined, endpoints, manifest, loaded, chain = loaded["analysis_v4"].build(config, (chain, loaded))
    report.update(policy=POLICY, analysis_sha256=prior.sha(Path(__file__).read_bytes()),
        predecessor_analysis_sha256=PREDECESSOR_SHA, suffix_v5_collector_sha256=COLLECTOR_SHA,
        suffix_v5_manifest_sha256=MANIFEST_SHA, suffix_v5_content_sha256=CONTENT_SHA,
        returned_sources_verified_before_attempt_reads=True)
    return report, joined, endpoints, manifest, loaded, chain


def release_labels(config, report, joined, endpoints, manifest, loaded, chain, labels, *, explicit_release=False):
    require(explicit_release, "Explicit postprediction human-label release required")
    chain.label_release_gate(joined)
    require(all(record["state"] not in {"definitely_not_contacted", "unavailable"} for record in joined.values()),
            "Precontact missing positions keep human labels closed")
    own_indices = {index for index, source in enumerate(config["sources"])
                   if source.get("collector_policy") == COLLECTOR_POLICY}
    require(all(record.get("started_time") is not None for record in joined.values()
                if record["source_index"] in own_indices), "009 unstarted positions keep human labels closed")
    return loaded["analysis_v4"].release_labels(config, report, joined, endpoints, manifest, loaded, chain,
                                              labels, explicit_release=explicit_release)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    previous = predecessor()
    prior = previous.predecessor()
    if args.metadata_only:
        require(args.config is args.config_sha256 is args.labels is None and not args.release_development_labels_postprediction,
                "Metadata-only cannot load config, jobs, attempts or labels")
        for name, pin in {"analysis_chain_v3": previous.PREDECESSOR_SHA, "analysis_chain": prior.OLD_SHA,
            "collector_suffix_v3": prior.V3_SHA, "collector_suffix_v4": previous.COLLECTOR_SHA,
            "collector_suffix_v5": COLLECTOR_SHA, **previous.IDENTITY_SOURCE_PINS}.items():
            prior.checked(HERE / (name + ".py"), pin)
        prior.checked(prior.PROJECT_PATH, prior.PROJECT_SHA)
        print(json.dumps({"policy": POLICY, "state": "metadata_only_code_pins_verified", "planned_denominator": 3108,
            "original_stories": 36, "reserved_v5_prefix": 337, "planned_v5_suffix": 1217,
            "manifest_v5_sha256": MANIFEST_SHA, "content_v5_sha256": CONTENT_SHA, "collector_v5_sha256": COLLECTOR_SHA,
            "predecessor_analysis_sha256": PREDECESSOR_SHA, "analysis_sha256": prior.sha(Path(__file__).read_bytes()),
            "native_attempts_loaded": False, "source_data_loaded": False, "labels_opened": False,
            "native_execution_verified": False, "provider_calls_made": 0}, sort_keys=True))
        return 0
    require(args.config is not None and args.config_sha256 is not None, "Pinned config required")
    require(args.release_development_labels_postprediction == (args.labels is not None), "Labels require explicit release")
    config = json.loads(prior.checked(args.config, args.config_sha256))
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
