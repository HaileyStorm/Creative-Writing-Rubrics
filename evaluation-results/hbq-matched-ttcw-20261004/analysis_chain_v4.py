"""Explicit frozen008 native execution analysis; metadata mode never opens jobs or labels.

All substitutions belong to private pinned predecessor instances. The original
full3108 gate, own returned lifecycles, scoring and historical recoveries remain.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
POLICY = "matched_ttcw_chain_analysis_v4"
PREDECESSOR_SHA = "c9faf4653cde6f5c272e4c0065270b73536e15dfe2c6e4f2c34a6d4c090bb088"
COLLECTOR_SHA = "c594953c0a9134c89ab60f28ae95143dcfef3d0594db0d7ae071184496d6ac20"
COLLECTOR_POLICY = "ttcw_untouched_suffix_execution_v4"
MANIFEST_SHA = "cce67e7abb0d44ffb4c9cfd972d112c5fd8712b1732fe0071cd5aaccaf9aaf4c"
IDENTITY_SOURCE_PINS = {
    "continue_manifest": "eb1373141a21060aafe9603ce262715ba1d3b0474e93f90dbd54def6b9b773ac",
    "continue_sol_chain": "b8818aed5a141891e168cbbb7192bba546d435e7877ed139ef8a9d50b029791d",
}
ATTESTATIONS = ("global_headroom_verified", "returned_allocation_verified", "current_route_verified", "outbound_disclosure_confirmed")
FLAGS = ("--execute-native", *("--owner-" + name.replace("_", "-") for name in ATTESTATIONS))
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)


def predecessor():
    import hashlib
    path = HERE / "analysis_chain_v3.py"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == PREDECESSOR_SHA, "Pinned v3 analysis differs")
    import importlib.util
    spec = importlib.util.spec_from_file_location("ttcw_analysis_v4_private_predecessor", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def derive(owner, name, pin, replacements, namespace):
    raw = (HERE / (owner.__name__.split(".")[-1] + ".py")).read_bytes() if owner.__name__ in IDENTITY_SOURCE_PINS else Path(owner.__file__).read_bytes()
    require(namespace["sha"](raw) == pin, "Pinned identity/lifecycle source differs")
    text = raw.decode("utf-8")
    function = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
    source = ast.get_source_segment(text, function)
    for old, new in replacements:
        require(source.count(old) == 1, "Pinned finite interface substitution differs")
        source = source.replace(old, new)
    scope = dict(vars(owner), **namespace)
    exec(compile(source, "explicit_ttcw_v4_private_" + name, "exec"), scope)
    return scope[name]


def optional(project, raw, keys):
    project(raw, {})
    result = {}
    for key in keys:
        try:
            result.update(project(raw, {key: True}))
        except ValueError as error:
            if str(error) != "Required source metadata absent":
                raise
    return result


def native_identity_metadata(raw, project):
    state = project(raw, {"state": True})["state"]
    result = {"state": state}
    if state == "completed":
        fields = ("subscription_receipt_hash", "requested_reasoning_effort", "command_identity", "cli_version", "request_id_hash")
        runtime = {}
        for key in fields:
            try:
                runtime.update(project(raw, {"result": {"runtime": {key: True}}})["result"]["runtime"])
            except ValueError as error:
                if str(error) != "Required source metadata absent":
                    raise
        result["result"] = {"runtime": runtime}
    return result


def execution_attestations(job):
    values = job.get("owner_attestations")
    require(isinstance(values, dict) and set(values) == set(ATTESTATIONS)
            and all(values[name] is True for name in ATTESTATIONS), "v4 requires all four actual execution attestations")
    return values


def runtime():
    prior = predecessor()
    chain, loaded = prior.runtime()
    project = loaded["project_json"]
    before, paths = dict(sys.modules), list(sys.path)
    try:
        native = prior.module("ttcw_analysis_v4_native", HERE / "collector_suffix_v4.py", COLLECTOR_SHA)
    finally:
        sys.path[:] = paths
        for name in set(sys.modules) - set(before):
            sys.modules.pop(name, None)
        sys.modules.update(before)
    loaded["suffix_v4"] = native

    def decode_prefix_record(name, raw, terminal_raw):
        if name == "native-result.json" and project(terminal_raw, {"state": True})["state"] not in {"accepted", "semantic_rejected"}:
            return native_identity_metadata(raw, project)
        return json.loads(raw)

    def failed_event_metadata(raw):
        return optional(project, raw, ("type", "thread_id", "turn_id"))

    scope = {"sha": prior.sha, "native_identity_metadata": lambda raw: native_identity_metadata(raw, project),
             "decode_prefix_record": decode_prefix_record, "failed_event_metadata": failed_event_metadata}
    original_replay = derive(chain, "replay_source", prior.OLD_SHA,
        [('native = json.loads((sample / "native-result.json").read_bytes())',
          'native = native_identity_metadata((sample / "native-result.json").read_bytes())')], scope)
    helper = loaded["continue_manifest"]
    helper.prefix_receipt = derive(helper, "prefix_receipt", IDENTITY_SOURCE_PINS["continue_manifest"],
        [('json.loads(retained[name]) for name in PREFIX_FILES[:5]',
          'decode_prefix_record(name, retained[name], retained["terminal.json"]) for name in PREFIX_FILES[:5]')], scope)
    helper = loaded["continue_sol_chain"]
    helper.failure_receipt = derive(helper, "failure_receipt", IDENTITY_SOURCE_PINS["continue_sol_chain"],
        [('event = json.loads(line)', 'event = failed_event_metadata(line)')], scope)

    def dispatch(specification, *args):
        policy = specification.get("collector_policy")
        if policy == COLLECTOR_POLICY:
            return replay_v4(specification, *args, prior=prior)
        if policy == prior.V3_POLICY:
            return prior.replay_v3(specification, *args)
        require(policy in (None, loaded["collector_v2"].POLICY), "Unknown source collector policy")
        return original_replay(specification, *args)

    chain.replay_source = dispatch
    original_lifecycle = prior.verify_lifecycle
    v4_lifecycle = derive(prior, "verify_lifecycle", PREDECESSOR_SHA,
        [('{"collector.py", "collector_v2.py", "collector_suffix_v3.py"}',
          '{"collector.py", "collector_v2.py", "collector_suffix_v3.py", "collector_suffix_v4.py"}'),
         ('str(Path(pins["launcher"]["path"]).resolve()), "--run"]',
          'str(Path(pins["launcher"]["path"]).resolve()), "--run", "--invocation-sha256", pins["invocation"]["sha256"]]')],
        {"sha": prior.sha, "V3_POLICY": COLLECTOR_POLICY})

    def verify_lifecycle(specification):
        if specification.get("collector_policy") != COLLECTOR_POLICY:
            return original_lifecycle(specification)
        job = json.loads(prior.checked(Path(specification["results_root"]) / "job.json", specification["job_sha256"]))
        execution_attestations(job)
        require(job["collector_policy"] == COLLECTOR_POLICY and job["collector_sha256"] == COLLECTOR_SHA, "v4 lifecycle job differs")
        proof, beginning, ending = v4_lifecycle(specification)
        pin = specification["lifecycle"]["invocation"]
        invocation = json.loads(prior.checked(pin["path"], pin["sha256"]))
        argv = invocation["argv"]
        require(all(argv.count(flag) == 1 for flag in FLAGS), "v4 native argv requires execute and all four owner flags")
        require(argv.count("--route-root") == 1
                and Path(argv[argv.index("--route-root") + 1]).resolve() == (native.TOOLS.parent / "state/model-work-queue-cwr-placeholder-r31").resolve(),
                "v4 owning route root differs")
        proof.update(collector_policy=COLLECTOR_POLICY, collector_sha256=COLLECTOR_SHA,
                     execution_attestations_verified=True, native_dispatcher_terminal_receipt=False)
        return proof, beginning, ending

    prior.verify_lifecycle = verify_lifecycle
    loaded["analysis_v3"] = prior
    return chain, loaded


def replay_v4(specification, base, base_raw, artifacts, helper, loaded, subset, index, *, prior):
    native = loaded["suffix_v4"]
    job = json.loads(prior.checked(Path(specification["results_root"]) / "job.json", specification["job_sha256"]))
    attestations = execution_attestations(job)
    # The replay body remains exact; only its private, explicit v4 interfaces change.
    proxy = SimpleNamespace(load_manifest=native.load_manifest, replay=native.replay,
        job_binding=lambda manifest, endpoint, workers, headroom, route: native.job_binding(
            manifest, endpoint, workers, headroom, route, owner_attestations=attestations),
        sample_path=native.base.sample_path, inputs=native.base.inputs, SETTLED=native.base.SETTLED)
    scope = dict(vars(prior), V3_POLICY=COLLECTOR_POLICY, V3_SHA=COLLECTOR_SHA)
    replay = FunctionType(prior.replay_v3.__code__, scope, "explicit_native_v4_replay")
    return replay(specification, base, base_raw, artifacts, helper, dict(loaded, suffix_v3=proxy), subset, index)


def build(config, environment=None):
    chain, loaded = runtime() if environment is None else environment
    report, joined, endpoints, manifest, loaded, chain = loaded["analysis_v3"].build(config, (chain, loaded))
    report.update(policy=POLICY, analysis_sha256=loaded["analysis_v3"].sha(Path(__file__).read_bytes()),
                  predecessor_analysis_sha256=PREDECESSOR_SHA, suffix_v4_collector_sha256=COLLECTOR_SHA,
                  failed_identity_projection_source_pins=IDENTITY_SOURCE_PINS)
    return report, joined, endpoints, manifest, loaded, chain


def release_labels(config, report, joined, endpoints, manifest, loaded, chain, labels, *, explicit_release=False):
    return loaded["analysis_v3"].release_labels(config, report, joined, endpoints, manifest, loaded, chain,
                                               labels, explicit_release=explicit_release)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    prior = predecessor()
    if args.metadata_only:
        require(args.config is args.config_sha256 is args.labels is None and not args.release_development_labels_postprediction,
                "Metadata-only cannot load config, jobs, attempts or labels")
        for name, pin in {"analysis_chain": prior.OLD_SHA, "collector_suffix_v3": prior.V3_SHA,
                          "collector_suffix_v4": COLLECTOR_SHA, **IDENTITY_SOURCE_PINS}.items():
            prior.checked(HERE / (name + ".py"), pin)
        prior.checked(prior.PROJECT_PATH, prior.PROJECT_SHA)
        print(json.dumps({"policy": POLICY, "state": "metadata_only_code_pins_verified", "planned_denominator": 3108,
            "original_stories": 36, "reserved_v4_prefix": 322, "planned_v4_suffix": 1232, "manifest_v4_sha256": MANIFEST_SHA,
            "collector_v4_sha256": COLLECTOR_SHA, "predecessor_analysis_sha256": PREDECESSOR_SHA,
            "analysis_sha256": prior.sha(Path(__file__).read_bytes()), "native_attempts_loaded": False,
            "source_data_loaded": False, "labels_opened": False, "provider_calls_made": 0}, sort_keys=True))
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
