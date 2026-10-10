"""Qualify explicitly selected cumulative Sol008 prefixes using pinned v1 guards.

Each operation gets an isolated engine. Its selection hook and source identity
are bound by this version's specification; immutable v1 files stay unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from types import ModuleType

SELF = Path(__file__).resolve()
SOURCE = SELF.read_bytes()
SOURCE_SHA256 = hashlib.sha256(SOURCE).hexdigest()
HERE = SELF.parent
REPO = HERE.parents[1]
TASK = "01a11270-c290-75c2-a441-1bc8ca2e34d6"
PROBE = REPO / ".artifacts-temp" / ("rollover-successor-" + TASK)
DEPENDENCY = HERE / "analysis_sol_live_prefix_v1.py"
DEPENDENCY_SHA256 = "eafff0aff8c64bcb7502d00fa3f6998d1abf0b1457445389240284187d69d835"
DEPENDENCY_BYTES = 41416
POLICY = "matched_ttcw_sol008_frozen_settled_prefix_v2"
NAMESPACE = "cwr-sol008-live-prefix-v2"
MAX_BYTES = 128 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def plain(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, "Canonical absolute path required")
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            require(not part.is_symlink() and not getattr(part.lstat(), "st_file_attributes", 0) & 0x400,
                    "Reparse ancestry refused")
    return path


def read(path):
    path = plain(path)
    before = path.stat()
    require(path.is_file() and before.st_size <= MAX_BYTES, "Bounded ordinary file required")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    after = path.stat()
    plain(path)
    require(len(raw) <= MAX_BYTES and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Input changed during read")
    return raw


def checked(path, digest, size=None):
    raw = read(path)
    require(sha(raw) == digest and (size is None or len(raw) == size), "Input commitment differs: " + Path(path).name)
    return raw


def dependency_commitment():
    return {"path": str(DEPENDENCY), "sha256": DEPENDENCY_SHA256, "bytes": DEPENDENCY_BYTES}


def selection_commitment(value):
    require(isinstance(value, dict) and set(value) == {"path", "sha256", "bytes", "actual_read_chunk"},
            "Explicit selection path/hash/size/actual-read commitment required")
    path = plain(Path(value["path"]))
    require(str(path) == value["path"] and path.parent == plain(PROBE) and path.suffix == ".json",
            "Selection must be a canonical owned PROBE child JSON file")
    require(isinstance(value["sha256"], str) and re.fullmatch("[0-9a-f]{64}", value["sha256"])
            and type(value["bytes"]) is int and 0 < value["bytes"] <= 1024 * 1024
            and isinstance(value["actual_read_chunk"], str)
            and re.fullmatch("[A-Za-z0-9_-]{1,128}", value["actual_read_chunk"]), "Selection commitment fields differ")
    return dict(value)


def validate_selection(engine, sources, commitment, *, as_of_utc, through, counts):
    require(type(through) is int and engine.FIRST <= through < engine.LAST,
            "Live cumulative selection must retain an original next-ready request")
    require(set(counts) == {"accepted", "semantic_rejected"} and all(type(value) is int and value >= 0 for value in counts.values())
            and sum(counts.values()) == through - engine.FIRST + 1, "Declared cumulative settlement geometry differs")
    raw = sources[engine.SELECTION]
    require(sha(raw) == commitment["sha256"] and len(raw) == commitment["bytes"], "Selection receipt commitment differs")
    boundary = json.loads(raw)
    require(raw == canonical(boundary), "Canonical immutable selection receipt required")
    require(boundary["schema_version"] == 2 and boundary["owner"] == TASK
            and boundary["state"] == "FROZEN_CUMULATIVE_SOL008_SELECTION_RELEASE_HELD"
            and all(boundary[key] is False for key in ("provider_contact", "target_release", "reservation_settlement", "scientific_admission_established")),
            "Versioned cumulative selection scope differs")
    frozen = boundary["frozen_settled_prefix"]
    retained = frozen["as_of_actual_read"]
    require(retained["status"] == "fulfilled" and retained["value"]["exit_code"] == 0
            and type(retained["value"]["exit_code"]) is int
            and retained["value"]["chunk_id"] == commitment["actual_read_chunk"], "Exact actual selection observation differs")
    observation = json.loads(retained["value"]["output"])
    ready = observation["ready"]
    require(all(type(frozen[key]) is int for key in ("original_first", "original_through", "as_of_ready", "settled", "accepted", "semantic_rejected"))
            and frozen["source"] == "sol008" and frozen["original_first"] == engine.FIRST
            and frozen["original_through"] == through and frozen["as_of_ready"] == through + 1
            and frozen["settled"] == sum(counts.values()) and frozen["accepted"] == counts["accepted"]
            and frozen["semantic_rejected"] == counts["semantic_rejected"], "Frozen original interval/counts differ")
    require(all(type(observation[key]) is int for key in ("settled", "accepted", "semantic_rejected", "unadmitted"))
            and type(ready["endpoint_ordinal"]) is int
            and observation["state"] == "waiting_for_goal_permit" and observation["terminal"] is None
            and observation["settled"] == frozen["settled"] and observation["accepted"] == frozen["accepted"]
            and observation["semantic_rejected"] == frozen["semantic_rejected"] and observation["unadmitted"] == 0
            and ready["schema_version"] == 1 and ready["state"] == "WAITING_FOR_NATIVE_ACTIVE_GOAL_PERMIT"
            and ready["endpoint_ordinal"] == through + 1 and ready["ready_utc"] == as_of_utc
            and observation["ready_sha256"] == sha(canonical(ready)) and ready["owner"] == TASK
            and ready["sample_created"] is False and ready["model_contact_started"] is False and ready["no_resend"] is True
            and ready["invocation_sha256"] == sha(sources[engine.LIFE / "invocation.json"])
            and ready["job_sha256"] == sha(sources[engine.OUT / "job.json"]), "Actual precontact as-of observation differs")
    engine.instant(as_of_utc)
    originals = json.loads(sources[engine.ORIGINAL])["requests"]
    next_rows = [row for row in originals if row["endpoint"] == "sol" and row["endpoint_ordinal"] == through + 1]
    require(len(next_rows) == 1 and all(ready[key] == next_rows[0][key] for key in ("logical_sample_id", "request_sha256")),
            "Original next-ready logical descriptor differs")
    require(boundary["source_pins"]["Sol008_job"] == sha(sources[engine.OUT / "job.json"])
            and boundary["source_pins"]["continue_sol.py"] == engine.CODE_PINS[HERE / "continue_sol.py"]
            and boundary["source_pins"]["src/hbqrs/codex_receipts.py"] == engine.CODE_PINS[REPO / "src/hbqrs/codex_receipts.py"],
            "Selection/native source join differs")


def bound_engine(commitment):
    commitment = selection_commitment(commitment)
    checked(SELF, SOURCE_SHA256, len(SOURCE))
    raw = checked(DEPENDENCY, DEPENDENCY_SHA256, DEPENDENCY_BYTES)
    engine = ModuleType("isolated_cumulative_prefix_engine")
    engine.__file__ = str(DEPENDENCY)
    exec(compile(raw, str(DEPENDENCY), "exec"), engine.__dict__)
    old_selection = engine.SELECTION
    engine.POLICY, engine.NAMESPACE = POLICY, NAMESPACE
    engine.SELF, engine.SELF_RAW, engine.SELF_SHA256 = SELF, SOURCE, SOURCE_SHA256
    engine.SELECTION = Path(commitment["path"])
    engine.METADATA_PINS = {path: pin for path, pin in engine.METADATA_PINS.items() if path != old_selection}
    engine.METADATA_PINS.update({engine.SELECTION: (commitment["sha256"], commitment["bytes"]),
                                 DEPENDENCY: (DEPENDENCY_SHA256, DEPENDENCY_BYTES), SELF: (SOURCE_SHA256, len(SOURCE))})
    engine.selection_check = lambda sources, **arguments: validate_selection(engine, sources, commitment, **arguments)
    legacy_validate = engine.validate_spec

    def validate(spec, snapshot, *, captured):
        validate_bindings(spec, commitment)
        return legacy_validate({**spec, "schema_version": 1}, snapshot, captured=captured)

    engine.validate_spec = validate
    return engine


def validate_bindings(spec, commitment=None):
    require(spec["schema_version"] == 2 and spec["policy"] == POLICY and spec["owner"] == TASK
            and spec["reader_sha256"] == SOURCE_SHA256 and spec["dependency_reader"] == dependency_commitment(),
            "Loaded v2 reader/v1 dependency contract differs")
    selected = selection_commitment(spec["selection_commitment"])
    require(commitment is None or selected == commitment, "CLI/specification selection commitments differ")
    require(spec["cumulative_prefix"] is True and spec["prior_prefix_additive_input"] is False,
            "Cumulative replacement provenance differs")
    checked(SELF, SOURCE_SHA256, len(SOURCE))
    checked(DEPENDENCY, DEPENDENCY_SHA256, DEPENDENCY_BYTES)
    return selected


def prepare_spec(*, selection_commitment, as_of_utc, through, expected_counts):
    engine = bound_engine(selection_commitment)
    spec = engine.prepare_spec(as_of_utc=as_of_utc, through=through, expected_counts=expected_counts)
    spec.update(schema_version=2, selection_commitment=dict(selection_commitment), dependency_reader=dependency_commitment(),
                cumulative_prefix=True, prior_prefix_additive_input=False)
    validate_bindings(spec)
    return spec


def capture_spec(template):
    engine = bound_engine(validate_bindings(template))
    result = engine.capture_spec(template)
    validate_bindings(result)
    return result


def replay_prefix(spec, *, specification_sha256):
    require(sha(canonical(spec)) == specification_sha256, "Canonical v2 specification commitment differs")
    commitment = validate_bindings(spec)
    engine = bound_engine(commitment)
    result = engine.replay_prefix(spec, specification_sha256=specification_sha256)
    result["report"].update(schema_version=2, dependency_reader=dependency_commitment(), selection_commitment=commitment,
                            cumulative_prefix=True, replacement_cache_required=True, prior_prefix_additive_input=False,
                            engine_contract_schema_version=1)
    result["metadata_commitments"] = {str(path): {"sha256": digest, "bytes": size} for path, (digest, size) in engine.METADATA_PINS.items()}
    result["runtime_commitments"] = {str(path): {"sha256": digest} for path, digest in engine.CODE_PINS.items()}
    validate_bindings(spec)
    return result


def write_output(result, output_dir, *, owned_output_root):
    root, output = plain(owned_output_root), plain(output_dir)
    require(root == plain(PROBE) and output != root and output.is_relative_to(root) and not output.exists(), "Fresh owned PROBE output required")
    report = result["report"]
    engine = bound_engine(report["selection_commitment"])
    require(report["reader_sha256"] == SOURCE_SHA256 and report["dependency_reader"] == dependency_commitment(), "Output reader provenance differs")
    sources = report["source_commitments"]
    require(all(not plain(Path(path)).is_relative_to(output) for path in sources)
            and all(not output.is_relative_to(source_root) for source_root in (engine.OUT, engine.LIFE, engine.GATES, engine.OBSERVATIONS, engine.MANIFEST.parent)),
            "Output overlaps retained source scope")

    def stable():
        for path, pin in sources.items():
            checked(Path(path), pin["sha256"], pin["bytes"])

    stable()
    payloads = {"report.json": canonical(report), "qualified-prefix-records.json": canonical(result["records"]),
                "normalized-predictions.json": canonical(result["predictions"]), "native-identities.json": canonical(result["identities"])}
    output.mkdir(parents=False, exist_ok=False)
    for name, raw in payloads.items():
        with engine.within(output, name).open("xb") as stream:
            stream.write(raw)
    stable()
    require(all(read(engine.within(output, name)) == raw for name, raw in payloads.items()), "Prefix payload readback differs")
    manifest = {key: value for key, value in report.items() if key != "source_commitments"}
    manifest.update(metadata_commitments=result["metadata_commitments"], runtime_commitments=result["runtime_commitments"],
                    files={name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in payloads.items()}, source_commitments=sources)
    stable()
    with engine.within(output, "manifest.json").open("xb") as stream:
        stream.write(canonical(manifest))
    require(read(engine.within(output, "manifest.json")) == canonical(manifest), "Prefix manifest readback differs")
    stable()
    return manifest


def main():
    require(not sys.flags.optimize, "Nonoptimized qualification required")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--selection-bytes", type=int, required=True)
    parser.add_argument("--selection-actual-read-chunk", required=True)
    parser.add_argument("--specification", type=Path, required=True)
    parser.add_argument("--specification-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--owned-output-root", type=Path, required=True)
    args = parser.parse_args()
    commitment = selection_commitment({"path": str(args.selection), "sha256": args.selection_sha256,
                                      "bytes": args.selection_bytes, "actual_read_chunk": args.selection_actual_read_chunk})
    raw = checked(args.specification, args.specification_sha256)
    spec = json.loads(raw)
    require(raw == canonical(spec), "Canonical explicit v2 specification required")
    validate_bindings(spec, commitment)
    result = replay_prefix(spec, specification_sha256=args.specification_sha256)
    require(read(args.specification) == raw, "Specification changed during replay")
    manifest = write_output(result, args.output_dir, owned_output_root=args.owned_output_root)
    require(read(args.specification) == raw, "Specification changed during output")
    print(json.dumps({"state": manifest["state"], "manifest_sha256": sha(canonical(manifest)), "reader_sha256": SOURCE_SHA256,
                      "dependency_reader_sha256": DEPENDENCY_SHA256, "specification_sha256": args.specification_sha256,
                      "selection_sha256": commitment["sha256"], "as_of_utc": manifest["as_of_utc"],
                      "qualified_settlements": manifest["qualified_settlements"], "qualified_accepted": manifest["qualified_accepted"],
                      "semantic_rejected": manifest["semantic_rejected"], "human_labels_opened": False, "provider_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
