"""Read a verified qualified cache and compose its saved lifecycle release bridge.

The four saved profiles have fixed code and configuration commitments. No
producer is rerun. This adapter does not authorize label access or qualify
missing, historical, or live observations; the full frozen release gates apply.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import stat
import sys
from types import FunctionType, ModuleType

import analysis_release_measurements_v1 as previous

POLICY = "matched_ttcw_qualified_cache_release_v2"
NAMESPACE = "cwr-qualified-cache-v2"
SPECIFICATIONS_SHA = "0c3cd2e981e4e62120d5c0a533d5e0140b1442c9600d7688f0f086e3428f5d67"
PREVIOUS_SHA = "753315251d8038809bd09fb9922e5649ae1aa017c16a635f65368cb6f48981f6"
PROFILES = {
    "saved_owned_sol_004_strict_v1": ("ttcw004_historical_lifecycle_091.py", "05be8c1981b30d0aec3b7983e4692c7447f958a390368bea133765cf7008cc22", 3, 669, 714, 45),
    "saved_owned_sol_005_strict_v1": ("ttcw005_saved_lifecycle_095.py", "ca429f130959c1fcdedf519e83f10382683d3666f66e5286f7bc02aee362a684", 5, 715, 777, 63),
    "saved_owned_sol_006_strict_v1": ("ttcw006_saved_lifecycle_096.py", "441c5e5cff4b714a838deecfdc7781de7099cf14321e63705fd518f8656f8a2d", 3, 778, 786, 8),
    "saved_owned_sol_007_strict_v1": ("ttcw007_saved_lifecycle_104.py", "0438aa359b9caa4401bbe43af619dd0e1f34c6d23f90e76c5b949540eebea205", 5, 787, 954, 168),
}
DESCRIPTOR_FIELDS = ("id", "index", "endpoint", "namespace", "local_source_index",
                     "first_original_endpoint_ordinal", "last_original_endpoint_ordinal",
                     "producer_sha256", "driver_sha256", "report_path", "report_sha256",
                     "saved_lifecycle_exit_code")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def checked(path, digest, size=None):
    """Read only ordinary pinned evidence, refusing link/reparse ancestry."""
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        info = entry.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Linked evidence path refused")
    require(path.is_file(), "Ordinary evidence file required")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, "Pinned evidence differs")
    require(size is None or len(raw) == size, "Evidence size differs")
    return raw


def object_at(pin):
    return json.loads(checked(pin["path"], pin["sha256"], pin.get("bytes")))


def registered_specifications(path):
    document = json.loads(checked(path, SPECIFICATIONS_SHA))
    require(document["source_index_namespace"] == NAMESPACE
            and document["original_denominator"] == 3108
            and document["label_release_authorized"] is False,
            "Prepared source registry differs")
    sources = document["sources"]
    require(len(sources) == len(PROFILES), "Saved source registry incomplete")
    for index, source in enumerate(sources):
        name, pin, exit_code, first, last, count = PROFILES[source["proof_profile"]]
        require(source["index"] == index and type(source["index"]) is int
                and source["namespace"] == NAMESPACE and source["endpoint"] == "sol"
                and source["local_source_index"] == 0
                and source["represented_original_range"] == [first, last]
                and source["scheduled_original_range"] == [first, 1554]
                and source["saved_lifecycle_exit_code"] == exit_code
                and source["qualified_settlements"] == count
                and Path(source["lifecycle_verifier"]["path"]).name == name
                and source["lifecycle_verifier"]["sha256"] == pin,
                "Registered saved source differs")
    return document


def decode_join(rows, endpoint_rows):
    """Convert serialized identities and endpoints without changing membership."""
    require(isinstance(rows, list) and set(endpoint_rows) == {"sol", "grok"},
            "Qualified cache shape differs")
    joined = {}
    for item in rows:
        pair = item["identity"]
        require(isinstance(pair, list) and len(pair) == 2
                and pair[0] in endpoint_rows and isinstance(pair[1], str),
                "Invalid cached identity")
        identity = tuple(pair)
        record = item["record"]
        request = record["request"]
        require(identity not in joined
                and identity == (request["endpoint"], request["logical_sample_id"]),
                "Duplicate or substituted cached identity")
        joined[identity] = record
    endpoints = {"sol": {}, "grok": {}}
    for endpoint, votes in endpoint_rows.items():
        require(isinstance(votes, list), "Serialized endpoint list required")
        for vote in votes:
            request = vote["request"]
            identity = request["logical_sample_id"]
            require(request["endpoint"] == endpoint and identity not in endpoints[endpoint],
                    "Duplicate or foreign endpoint vote")
            record = joined.get((endpoint, identity))
            require(record is not None and record["state"] == "accepted"
                    and record["accepted"] == vote, "Endpoint vote differs from cached admission")
            endpoints[endpoint][identity] = vote
    expected = {endpoint: {identity: record["accepted"]
                for (ep, identity), record in joined.items()
                if ep == endpoint and record["state"] == "accepted"}
                for endpoint in endpoints}
    require(endpoints == expected, "Accepted cache membership differs")
    return joined, endpoints


def build(source_specifications, environment=None):
    """Load the retained cache without calling owning replay readers or labels."""
    checked(previous.__file__, PREVIOUS_SHA)
    document = registered_specifications(source_specifications)
    manifest_pin = document["cache_manifest"]
    cache = object_at(manifest_pin)
    require(cache["state"] == "PASS_CACHED_JOIN_RELEASE_HELD"
            and cache["human_labels_opened"] is False and cache["live008_read"] is False
            and cache["provider_calls"] == 0, "Cached evidence scope differs")
    root = Path(manifest_pin["path"]).absolute().parent
    payloads = {}
    for name, pin in cache["files"].items():
        require(Path(name).name == name and name not in {".", ".."}, "Cache payload containment")
        payloads[name] = checked(root / name, pin["sha256"], pin["bytes"])
    for pin in cache["source_commitments"].values():
        checked(pin["path"], pin["sha256"], pin["bytes"])
    report = object_at(document["cache_report"])
    require(payloads["report.json"] == checked(document["cache_report"]["path"], document["cache_report"]["sha256"])
            and report["source_commitments"] == cache["source_commitments"]
            and report["source_index_namespace"] == NAMESPACE
            and report["original_denominator"] == 3108, "Cache report differs")
    acceptance = object_at(document["cache_acceptance"])
    require(acceptance["state"] == "PASS_ACTUAL_CACHED_JOIN_OUTPUT"
            and acceptance["manifest_sha256"] == manifest_pin["sha256"]
            and acceptance["namespace"] == NAMESPACE
            and acceptance["original_requests"] == 3108
            and acceptance["qualified_accepted"] == report["qualified_accepted"]
            and acceptance["human_labels_opened"] is False
            and acceptance["endpoint_membership_matches_qualified_join"] is True,
            "Independent cache acceptance differs")
    require(report["sources"] == [{field: source[field] for field in DESCRIPTOR_FIELDS}
                                  for source in document["sources"]], "Cache source descriptors differ")
    joined, endpoints = decode_join(json.loads(payloads["joined-records.json"]),
                                    json.loads(payloads["qualified-endpoints.json"]))
    manifest = object_at(cache["source_commitments"]["frozen_original"])
    chain, loaded = previous.boundary.runtime() if environment is None else environment
    originals = chain.planned_rows(manifest)
    require(joined.keys() == originals.keys() and len(originals) == 3108
            and all(record["request"] == originals[identity] for identity, record in joined.items()),
            "Cached ledger differs from original3108 requests")
    for identity, record in joined.items():
        if record["state"] != "accepted":
            require(record.get("accepted") is None, "Unaccepted cache record supplies a vote")
            continue
        index = record.get("source_index")
        require(type(index) is int and 0 <= index < len(document["sources"]), "Cached source index invalid")
        source = document["sources"][index]
        require(source["endpoint"] == identity[0]
                and source["first_original_endpoint_ordinal"] <= record["request"]["endpoint_ordinal"]
                <= source["last_original_endpoint_ordinal"]
                and record.get("source_index_namespace") == NAMESPACE
                and record.get("source_id") == source["id"]
                and record.get("local_source_index") == source["local_source_index"]
                and record.get("goal_sponsorship_verified") is True
                and all(record.get(field) is True for field in
                        ("terminal_evidence_verified", "native_evidence_verified", "qualified_startup_command_verified")),
                "Cached qualification binding differs")
    config = {**copy.deepcopy(document), "source_specifications_path": str(Path(source_specifications).absolute())}
    metadata = {**report, "release_bridge_policy": POLICY, "release_bridge_implemented": True,
                "label_release_authorized_by_adapter": False, "saved_inspections_performed": 0}
    return config, metadata, joined, endpoints, manifest, loaded, chain


def saved_lifecycle(specification, registered):
    """Verify one exact saved return; never replay or admit literary samples."""
    require(not sys.flags.optimize, "Saved profiles require nonoptimized verification")
    require(specification == registered, "Saved source specification substituted")
    profile = specification["proof_profile"]
    name, digest, exit_code, first, last, count = PROFILES[profile]
    path = Path(specification["lifecycle_verifier"]["path"])
    require(path.name == name and specification["lifecycle_verifier"]["sha256"] == digest,
            "Unregistered saved verifier")
    raw = checked(path, digest)
    module = ModuleType("cwr_private_" + profile)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    inspected = module.inspect_saved_lifecycle()
    pins = specification["lifecycle"]
    manifest = json.loads(checked(specification["manifest_path"], specification["manifest_sha256"]))
    job = json.loads(checked(Path(specification["results_root"]) / "job.json", specification["job_sha256"]))
    object_at(pins["invocation"])
    started, outer = object_at(pins["run_started"]), object_at(pins["outer_terminal"])
    return verify_saved_return(specification, inspected, manifest, job, started, outer)


def verify_saved_return(specification, inspected, manifest, job, started, outer):
    """Check a registered inspector's result; this pure check admits no votes."""
    profile = specification["proof_profile"]
    _, _, exit_code, first, _, count = PROFILES[profile]
    pins = specification["lifecycle"]
    require(inspected["state"] == "VERIFIED_OWNED_LOCAL_RETURN_REPLAY_REQUIRED"
            and inspected["source_lifecycle_verified"] is True
            and type(inspected["exit_code"]) is int and inspected["exit_code"] == exit_code
            and inspected["original_denominator"] == 3108
            and type(inspected["sample_bodies_read"]) is type(inspected["accepted_votes_admitted"]) is int
            and inspected["sample_bodies_read"] == inspected["accepted_votes_admitted"] == 0
            and all(inspected[field] is False for field in
                    ("labels_opened", "remote_or_billing_quiescence_proven", "full_label_release_gate_passed")),
            "Saved inspector does not establish this local return")
    require(inspected["invocation_sha256"] == pins["invocation"]["sha256"]
            and inspected["outer_terminal_sha256"] == pins["outer_terminal"]["sha256"]
            and inspected["manifest_sha256"] == specification["manifest_sha256"],
            "Saved proof and configured lifecycle differ")
    expected_rows = [row for row in manifest["requests"]
                     if row["endpoint"] == "sol" and first <= row["endpoint_ordinal"] <= 1554]
    require(inspected["rows"] == expected_rows
            and [row["endpoint_ordinal"] for row in expected_rows] == list(range(first, 1555)),
            "Saved proof original suffix differs")
    require(job["endpoint"] == "sol" and job["manifest_sha256"] == specification["manifest_sha256"],
            "Saved owning job differs")
    require(type(outer["exit_code"]) is int and outer["exit_code"] == exit_code
            and outer["native_exit_confirmed"] is True and outer["no_resend"] is True
            and outer["invocation_sha256"] == pins["invocation"]["sha256"]
            and outer["terminal_counts"] == inspected["declared_terminal_counts"]
            and type(outer["terminal_counts"]["accepted"]) is int
            and outer["terminal_counts"]["accepted"] == count, "Saved outer return differs")
    def timestamp(value):
        instant = datetime.fromisoformat(value)
        require(instant.tzinfo is not None, "Saved return timestamp has no timezone")
        return instant
    beginning, ending = timestamp(started["started_utc"]), timestamp(outer["completed_utc"])
    require(beginning <= ending and beginning == timestamp(specification["recorded_beginning"])
            and ending == timestamp(specification["recorded_ending"]), "Saved return chronology differs")
    return {"endpoint": "sol", "job_sha256": specification["job_sha256"],
            "invocation_sha256": pins["invocation"]["sha256"],
            "outer_terminal_sha256": pins["outer_terminal"]["sha256"], "exit_code": exit_code,
            "saved_profile": profile, "local_dispatch_return_only": True,
            "physical_remote_settlement_proven": False}, beginning, ending


def release_labels(config, report, joined, endpoints, manifest, loaded, chain, labels, *, explicit_release=False):
    require(explicit_release is True, "Explicit authorized postprediction label release required")
    checked(previous.__file__, PREVIOUS_SHA)
    chain.label_release_gate(joined)
    saved = [source for source in config["sources"] if source.get("proof_profile") is not None]
    require(all(source["proof_profile"] in PROFILES for source in saved), "Unknown saved lifecycle profile")
    registry = {}
    if saved:
        document = registered_specifications(config["source_specifications_path"])
        registry = {source["proof_profile"]: source for source in document["sources"]}
        require(all(source == registry[source["proof_profile"]] for source in saved),
                "Configured saved source differs from registered evidence")
    prior = loaded["analysis_v3"]
    historical = prior.release_labels.__globals__["verify_lifecycle"]

    def verify(specification):
        profile = specification.get("proof_profile")
        if profile is None:
            return historical(specification)
        require(profile in registry, "Unregistered saved lifecycle profile")
        return saved_lifecycle(specification, registry[profile])

    private = ModuleType(prior.__name__)
    private.__dict__.update(vars(prior))
    private.release_labels = FunctionType(prior.release_labels.__code__,
        {**prior.release_labels.__globals__, "verify_lifecycle": verify}, prior.release_labels.__name__)
    result = previous.release_labels(config, report, joined, endpoints, manifest,
        {**loaded, "analysis_v3": private}, chain, labels, explicit_release=True)
    result["qualified_cache_release_bridge"] = {"policy": POLICY,
        "registered_saved_profiles": sorted(registry), "frozen_release_code_preserved": True,
        "arbitrary_exit5_allowed": False, "release_authority_established": False,
        "promotion_established": False}
    return result
