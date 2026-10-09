"""Offline qualification of an explicitly frozen settled Sol008 prefix.

Preparation reads metadata only. Capture and replay read only named prefix paths;
neither operation enumerates the live results tree or releases its reservation.
The caller owns prospective selection, output ownership and later disjoint joins.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import uuid

SELF = Path(__file__).resolve()
SELF_RAW = SELF.read_bytes()
SELF_SHA256 = hashlib.sha256(SELF_RAW).hexdigest()
HERE = SELF.parent
REPO = HERE.parents[1]
TASK = "01a11270-c290-75c2-a441-1bc8ca2e34d6"
PROBE = REPO / ".artifacts-temp" / ("rollover-successor-" + TASK)
BASE = Path("C:/Users/Haile/Documents/cwr-resume-control-20260919-r1/successor-program-20261004/ttcw-phase1")
OWN = BASE / ("owner-successor-" + TASK)
OUT = OWN / "ttcw-sol-successor-008"
LIFE = OWN / "ttcw-successor-008-lifecycle/sol"
GATES = PROBE / "ttcw-sol-goal-gates-105-008"
OBSERVATIONS = PROBE / "ttcw-goal-observations-105-008"
MANIFEST = BASE / "frozen-sol-suffix-003/manifest.json"
ORIGINAL = MANIFEST.parent / "lineage/parent-manifest.json"
CATALOG = OWN / "sol-tool-catalog-probe-003/selected-model-catalog.json"
PATCH = OWN / "ttcw-sol-tools-preparation-061-v2/proposed_native_call.py"
LAUNCHER = PROBE / "launch_ttcw_sol_supervised_105_008.py"
CLI = Path("C:/Users/Haile/AppData/Roaming/npm/codex.exe")
SUBSET = Path("C:/Users/Haile/.codex/tools/model_work_queue/adapters/json_schema_subset.py")
SELECTION = PROBE / "sol008-prefix-admission-review-118.json"
POLICY = "matched_ttcw_sol008_frozen_settled_prefix_v1"
NAMESPACE = "cwr-sol008-live-prefix-v1"
MAX_BYTES = 128 * 1024 * 1024
FIRST, LAST, DENOMINATOR = 955, 1554, 3108
FILES = ("condition.json", "terminal.json", "native-result.json", "native-identity.json",
         "attempt-started.json", "schema.json", "response.json", "acceptance.json")
CODE_PINS = {
    HERE / "continue_sol.py": "09ce5e25dfa9998ce4af8307858dfd9ed29906ba6bd1c61ec1f831833f55c4eb",
    HERE / "analysis_chain.py": "96de810dc955c5aac086990aa052b1980079fa67b7a825062045a2dc9805a229",
    HERE / "analysis.py": "c843cb8bfb54a3cc27955c911c1a8e5aa053d6a2f25a9f4dd3b67479fa22ae19",
    HERE / "validate_response.py": "a41915877b6f7e21a05f0b34d3c31c788f7f23070ab674ecfc514d93391e270e",
    REPO / "src/hbqrs/codex_receipts.py": "5d1c7af681e881a77201dee7cece4a14fa11cadc86d119714766492e547e1116",
    SUBSET: "d8389463bc7b2c3b8f172890f5ab6c3f5b5a7c77263d040e25ebd5be9eadad1c",
    PATCH: "befe441219c1c7dcdb8a14950f8b8b08335851226af04151562c23a2bdb7a1dd",
    LAUNCHER: "ac78f2165303532e6e3d3026c066d7118cd4c0a2485dca872c57290e8321848e",
}
METADATA_PINS = {
    OUT / "job.json": ("2a026e6308da31023f39ae1cf1770382e4ccbd0c8d5b31a0b16da39f999fc894", 30028),
    LIFE / "invocation.json": ("fba2121d03fcac56a481a07ffcee40ecd6020d51aa34d9e886fd2bba2973eb6c", 28848),
    OWN / "allocation-consumed-ttcw-sol-008.json": ("5cf423b4667757448358d01b5b3077e1e772b0cbaf8badd99faf83a26bfc479d", 976),
    LIFE / "launch-contract.json": ("bbc274ba3d081cca7f1e84044a59b672d3baa7974453ae5310183749748c3fea", 28336),
    LIFE / "child-started.json": ("371cb0d80047f2a00bc8c067bebfa841b4bd82bec8b39abc13eca896d3506660", 186),
    LIFE / "parent-started.json": ("6ce5a6fbf03fa50ad16d506b4051b7b0860ec7f78324c2e231ba838f6385268d", 150),
    LIFE / "native-handle.json": ("ab693d672dcaec26863926c0561afa9f82fe5551bf262a76b3a75e97637887d3", 206),
    LIFE / "composition.json": ("ee0b7028909b29affbc9c55d7da0c6dccc9a377c36a8ed4c137df3dd06aa228a", 334),
    MANIFEST: ("edab05ee97aa0f670a2aff05d6457934d017431bd37e2e8b4b5d808358c1d401", 2832790),
    ORIGINAL: ("b1868f8b6dee6daba3125b73628e6276b34f7049fad049f17262cbe3c859b7b7", 4481093),
    CATALOG: ("4b7945891e62ce62dd98be5e428161ebb34732d1338cffd2b5ee28b2bde16cf5", 66309),
    OWN / "sol-tool-catalog-probe-003/receipt.json": ("b3b505b5a76db9cebca16adfdbc9d2447849aa71034c2c02005d78eabf634c3c", 3056),
    PROBE / "ttcw008-tool-disable-boundary-105.json": ("f17d70ca12e3a290d3561736d27d337dfab185e8c5f009476455f1e9037c7841", 3445),
    SELECTION: ("ce8d34c14eebe280fdfcc8eb9234830851c1a97c570ba9c8fb7649b120d47c3a", 4044),
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def instant(value):
    require(isinstance(value, str), "Timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Timezone-aware timestamp required")
    return result.astimezone(timezone.utc)


def plain(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, "Canonical absolute path required")
    for component in (path, *path.parents):
        if component.exists() or component.is_symlink():
            require(not component.is_symlink()
                    and not getattr(component.lstat(), "st_file_attributes", 0) & 0x400,
                    "Reparse ancestry refused")
    return path


def within(root, name):
    root = plain(root)
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and not any(part in {".", ".."} for part in name.replace("\\", "/").split("/"))
            and ":" not in name, "Relative artifact path required")
    path = plain(root / name)
    require(path != root and path.is_relative_to(root), "Artifact escapes declared root")
    return path


def read(path):
    path = plain(path)
    before = path.stat()
    require(path.is_file() and before.st_size <= MAX_BYTES, "Bounded regular file required")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    after = path.stat()
    plain(path)
    require(len(raw) <= MAX_BYTES and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Artifact changed during read")
    return raw


def checked(path, digest, size=None):
    raw = read(path)
    require(sha(raw) == digest and (size is None or len(raw) == size), "Artifact commitment differs: " + Path(path).name)
    return raw


def reader_pin():
    require(checked(SELF, SELF_SHA256, len(SELF_RAW)) == SELF_RAW, "Loaded reader source changed")
    return SELF_SHA256


class Snapshot:
    def __init__(self):
        self.raw = {}

    def get(self, path, pin=None):
        path = plain(path)
        raw = read(path) if pin is None else checked(path, pin["sha256"], pin["bytes"])
        require(path not in self.raw or self.raw[path] == raw, "Repeated artifact read changed")
        self.raw[path] = raw
        return raw

    def stable(self):
        require(all(read(path) == raw for path, raw in self.raw.items()), "Consumed artifact changed during qualification")

    def commitments(self):
        return {str(path): {"sha256": sha(raw), "bytes": len(raw)} for path, raw in sorted(self.raw.items())}


def selected(raw, path, names, scope):
    tree = ast.parse(raw)
    body = []
    for name in names:
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        require(len(nodes) == 1, "Exact reusable function required")
        body.extend(nodes)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *body], type_ignores=[])), str(path), "exec"), scope)
    return scope


def loaded(raw, path):
    module = ModuleType("frozen_prefix_" + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def metadata(snapshot):
    sources = {path: snapshot.get(path, {"sha256": digest, "bytes": size})
               for path, (digest, size) in METADATA_PINS.items()}
    job = json.loads(sources[OUT / "job.json"])
    iv = json.loads(sources[LIFE / "invocation.json"])
    contract = iv["contract"]
    consumed = json.loads(sources[OWN / "allocation-consumed-ttcw-sol-008.json"])
    require(sha(canonical(contract)) == iv["launch_contract_sha256"]
            and sources[LIFE / "launch-contract.json"] == canonical(contract), "Invocation contract differs")
    require(iv["allocation_consumption_sha256"] == sha(canonical(consumed))
            and consumed["launch_contract_sha256"] == iv["launch_contract_sha256"], "Allocation consumption differs")
    require(contract["owner"] == consumed["owner"] == TASK
            and contract["workers"] == consumed["workers"] == 1
            and contract["ordinals"] == [FIRST, LAST] and contract["requests"] == LAST - FIRST + 1
            and contract["all_model_tool_definitions"] == 0 and contract["automatic_retries"] == 0
            and contract["no_resend"] is True and consumed["no_resend"] is True
            and consumed["reserved_total"] == 10 and consumed["retained_ambiguous_total"] == 9
            and consumed["unknown_reservations_released"] is False, "Exact owned reservation controls differ")
    require(contract["output"] == str(OUT) and contract["lifecycle"] == str(LIFE)
            and contract["goal_gate_root"] == str(GATES) and contract["cwd"] == str(REPO)
            and iv["allocation_consumption_path"] == str(OWN / "allocation-consumed-ttcw-sol-008.json")
            and consumed["invocation_path"] == str(LIFE / "invocation.json"), "Invocation path binding differs")
    require(contract["model"] == job["model"] == "gpt-6.1-sol"
            and contract["effort"] == job["reasoning"] == "high" and contract["timeout_seconds"] == 300
            and job["endpoint"] == "sol" and job["automatic_retries"] == 0 and job["zero_charge_only"] is True,
            "Frozen model/account collection controls differ")
    successor = job["successor_continuation"]
    expected = {"owner": TASK, "native_invocation_sha256": sha(sources[LIFE / "invocation.json"]),
                "allocation_consumption_sha256": iv["allocation_consumption_sha256"],
                "launch_contract_sha256": iv["launch_contract_sha256"], "all_model_tool_definitions": 0,
                "global_allocation_consumed": True, "automatic_retries": 0, "no_resend": True,
                "untouched_first": FIRST, "untouched_last": LAST, "original_endpoint_denominator": LAST,
                "source_manifest_sha256": sha(sources[MANIFEST]), "runtime_timeout_seconds": 300,
                "goal_gate_policy": "native_ACTIVE_per_exact_request_before_sample"}
    require(all(successor.get(key) == value for key, value in expected.items()), "Exact successor startup join differs")
    require(job["manifest_sha256"] == sha(sources[MANIFEST]), "Job manifest differs")
    parent, handle, child = (json.loads(sources[LIFE / name]) for name in
                             ("parent-started.json", "native-handle.json", "child-started.json"))
    require(all(item["invocation_sha256"] == expected["native_invocation_sha256"] for item in (parent, handle, child))
            and handle["parent_pid"] == parent["pid"] and child["parent_pid"] == handle["pid"]
            and handle["owned_handle"] is True and handle["detached"] is False and child["no_resend"] is True
            and instant(contract["created_utc"]) <= instant(parent["started_utc"])
            <= instant(handle["started_utc"]) <= instant(child["started_utc"]), "Owned startup process identity differs")
    require(contract["child_argv"] == [str(REPO / ".venv/Scripts/python.exe"), "-B", str(LAUNCHER), "--run", contract["nonce"]],
            "Owned child argv differs")
    composition = json.loads(sources[LIFE / "composition.json"])
    require(composition["adapter_sha256"] == successor["adapter_sha256"]
            and composition["source_sha256"] == job["collector_sha256"]
            and composition["tool_definitions"] == 0 and composition["untouched_requests"] == LAST - FIRST + 1
            and composition["dispatch_authority_created"] is False
            and composition["sites"] == {"entry": 1, "rows": 1, "output": 1, "job": 1, "call": 1, "sample_gate": 1, "subset": 1},
            "Reviewed startup composition differs")
    control = contract["native_tool_control"]
    require(control["model_catalog_path"] == str(CATALOG) and control["model_catalog_sha256"] == sha(sources[CATALOG])
            and control["qualification_receipt_sha256"] == sha(sources[OWN / "sol-tool-catalog-probe-003/receipt.json"])
            and control["all_model_tool_definitions"] == 0, "Startup probe/catalog binding differs")
    catalog = json.loads(sources[CATALOG])["models"]
    require(len(catalog) == 1 and catalog[0]["slug"] == "gpt-6.1-sol" and catalog[0]["tool_mode"] == "direct"
            and catalog[0]["apply_patch_tool_type"] is None and catalog[0]["experimental_supported_tools"] == [],
            "Disabled-tool catalog differs")
    fixture = json.loads(sources[OWN / "sol-tool-catalog-probe-003/receipt.json"])
    require(fixture["local_fixture_serialization_only"] is True and fixture["request_count"] == 1
            and fixture["requests"][0]["tool_count"] == 0 and fixture["requests"][0]["recursive_descriptor_count"] == 0
            and fixture["model_catalog_binding"]["derived_one_model_catalog_sha256"] == sha(sources[CATALOG]),
            "Retained local startup fixture differs")
    return sources, job, iv, child


def descriptor_rows(sources, through):
    require(type(through) is int and FIRST <= through <= LAST, "Explicit bounded original prefix required")
    base, source = json.loads(sources[ORIGINAL]), json.loads(sources[MANIFEST])
    require(base.get("labels_read") is False and source.get("labels_read") is False,
            "Label-free frozen manifests required")
    require(len(base["requests"]) == DENOMINATOR and len({(r["endpoint"], r["logical_sample_id"]) for r in base["requests"]}) == DENOMINATOR,
            "Distinct original denominator differs")
    for endpoint in ("sol", "grok"):
        require([r["endpoint_ordinal"] for r in base["requests"] if r["endpoint"] == endpoint] == list(range(1, LAST + 1)),
                "Original endpoint order differs")
    originals = [row for row in base["requests"] if row["endpoint"] == "sol"]
    source_rows = [row for row in source["requests"] if row["endpoint"] == "sol"]
    require(source_rows == originals[source["continuation"]["reserved_through_endpoint_ordinal"]:],
            "Source reorders or substitutes original suffix")
    rows = originals[FIRST - 1:through]
    require(all(sha(canonical({k: v for k, v in row.items() if k != "request_sha256"})) == row["request_sha256"] for row in rows),
            "Frozen request commitment differs")
    return base, source, rows


def selection_check(sources, *, as_of_utc, through, counts):
    boundary = json.loads(sources[SELECTION])
    frozen = boundary["frozen_initial_prefix"]
    retained = frozen["as_of_actual_read"]
    require(boundary["owner"] == TASK and boundary["schema_version"] == 1
            and boundary["state"] == "SOURCE_REVIEW_LIVE_PREFIX_REQUIRES_VERSIONED_QUALIFICATION_READER"
            and boundary["provider_contact"] is False and boundary["target_release"] is False
            and boundary["reservation_settlement"] is False and boundary["scientific_admission_established"] is False,
            "Immutable prospective selection receipt differs")
    require(retained["status"] == "fulfilled" and retained["value"]["exit_code"] == 0
            and retained["value"]["chunk_id"] == "633291", "Retained actual as-of metadata read differs")
    observation = json.loads(retained["value"]["output"])
    ready = observation["ready"]
    require(frozen["source"] == "sol008" and frozen["original_first"] == FIRST
            and frozen["original_through"] == through and frozen["as_of_ready"] == through + 1
            and frozen["settled"] == sum(counts.values()) and frozen["accepted"] == counts["accepted"]
            and frozen["semantic_rejected"] == counts["semantic_rejected"], "Frozen as-of original prefix/counts differ")
    require(observation["state"] == "waiting_for_goal_permit" and observation["terminal"] is None
            and observation["settled"] == frozen["settled"] and observation["accepted"] == frozen["accepted"]
            and observation["semantic_rejected"] == frozen["semantic_rejected"] and observation["unadmitted"] == 0
            and ready["endpoint_ordinal"] == through + 1 and ready["ready_utc"] == as_of_utc
            and observation["ready_sha256"] == sha(canonical(ready))
            and ready["owner"] == TASK and ready["sample_created"] is False and ready["model_contact_started"] is False
            and ready["invocation_sha256"] == sha(sources[LIFE / "invocation.json"])
            and ready["job_sha256"] == sha(sources[OUT / "job.json"]), "Actual initial as-of observation differs")
    require(boundary["source_pins"]["Sol008_job"] == sha(sources[OUT / "job.json"])
            and boundary["source_pins"]["continue_sol.py"] == CODE_PINS[HERE / "continue_sol.py"]
            and boundary["source_pins"]["src/hbqrs/codex_receipts.py"] == CODE_PINS[REPO / "src/hbqrs/codex_receipts.py"],
            "Prospective selection/native source join differs")


def prepare_spec(*, as_of_utc, through=1184, expected_counts=None):
    """Return a metadata-only template; it grants no contact or qualification."""
    instant(as_of_utc)
    snapshot = Snapshot()
    sources, _, _, _ = metadata(snapshot)
    _, _, rows = descriptor_rows(sources, through)
    counts = {"accepted": 229, "semantic_rejected": 1} if expected_counts is None else expected_counts
    require(set(counts) == {"accepted", "semantic_rejected"} and all(type(v) is int and v >= 0 for v in counts.values())
            and sum(counts.values()) == len(rows), "Declared settled count differs")
    selection_check(sources, as_of_utc=as_of_utc, through=through, counts=counts)
    snapshot.stable()
    return {"schema_version": 1, "policy": POLICY, "state": "METADATA_PREPARED_CAPTURE_REQUIRED", "owner": TASK,
            "reader_sha256": reader_pin(), "as_of_utc": as_of_utc,
            "selection": "Every exact original Sol008 position from first through boundary; independent of outcomes",
            "first_original_endpoint_ordinal": FIRST, "through_original_endpoint_ordinal": through,
            "last_reserved_original_endpoint_ordinal": LAST, "original_denominator": DENOMINATOR,
            "expected_counts": counts, "metadata_commitments": snapshot.commitments(),
            "samples": [{"prefix_position": index, "original_endpoint_ordinal": row["endpoint_ordinal"],
                         "original_request_ordinal": row["ordinal"], "logical_sample_id": row["logical_sample_id"],
                         "request_sha256": row["request_sha256"]} for index, row in enumerate(rows, 1)],
            "prior_native_identities": [], "sample_bodies_read": 0, "human_labels_opened": False, "provider_calls": 0}


def validate_spec(spec, snapshot, *, captured):
    require(spec["schema_version"] == 1 and spec["policy"] == POLICY and spec["owner"] == TASK
            and spec["reader_sha256"] == reader_pin()
            and spec["state"] == ("FROZEN_SETTLED_PREFIX" if captured else "METADATA_PREPARED_CAPTURE_REQUIRED")
            and spec["first_original_endpoint_ordinal"] == FIRST and spec["last_reserved_original_endpoint_ordinal"] == LAST
            and spec["original_denominator"] == DENOMINATOR and spec["human_labels_opened"] is False and spec["provider_calls"] == 0,
            "Versioned explicit prefix descriptor differs")
    as_of = instant(spec["as_of_utc"])
    sources, job, iv, child = metadata(snapshot)
    require(spec["metadata_commitments"] == snapshot.commitments(), "Frozen metadata inventory differs")
    base, source, rows = descriptor_rows(sources, spec["through_original_endpoint_ordinal"])
    require(len(spec["samples"]) == len(rows), "Frozen prefix count differs")
    for index, (pin, row) in enumerate(zip(spec["samples"], rows), 1):
        require(all(pin[key] == value for key, value in {"prefix_position": index, "original_endpoint_ordinal": row["endpoint_ordinal"],
                    "original_request_ordinal": row["ordinal"], "logical_sample_id": row["logical_sample_id"],
                    "request_sha256": row["request_sha256"]}.items()), "Original position or logical descriptor differs")
    counts = spec["expected_counts"]
    require(set(counts) == {"accepted", "semantic_rejected"} and all(type(v) is int and v >= 0 for v in counts.values())
            and sum(counts.values()) == len(rows), "Prospective counts differ")
    selection_check(sources, as_of_utc=spec["as_of_utc"], through=spec["through_original_endpoint_ordinal"], counts=counts)
    require(instant(child["started_utc"]) <= as_of, "As-of predates owned startup")
    return sources, job, iv, child, base, source, rows


def sample_capture(snapshot, row):
    sample = within(OUT, f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}")
    raw = {name: snapshot.get(within(sample, name)) for name in FILES}
    native = json.loads(raw["native-result.json"])
    require(set(native["provider_artifacts"]) == {"codex_events", "codex_message", "codex_rollout", "codex_receipt"},
            "Native artifact inventory differs")
    for item in native["provider_artifacts"].values():
        require(item["path"] not in raw, "Native artifact aliases sample control file")
        raw[item["path"]] = snapshot.get(within(sample, item["path"]), item)
    sponsorship = {}
    for role, root, suffix in (("ready", GATES, "ready"), ("permit", GATES, "permit"), ("observation", OBSERVATIONS, "observation")):
        path = within(root, f"{row['endpoint_ordinal']:04d}-{suffix}.json")
        sponsorship[role] = snapshot.get(path)
    return sample, raw, sponsorship


def capture_spec(template):
    """Freeze explicit per-attempt commitments, without admitting responses."""
    snapshot = Snapshot()
    *_, rows = validate_spec(template, snapshot, captured=False)
    spec = json.loads(canonical(template))
    for pin, row in zip(spec["samples"], rows):
        _, raw, sponsorship = sample_capture(snapshot, row)
        require(json.loads(raw["terminal.json"])["state"] in {"accepted", "semantic_rejected"}, "Unsettled explicit prefix; no resend")
        pin["files"] = {name: {"sha256": sha(value), "bytes": len(value)} for name, value in sorted(raw.items())}
        pin["sponsorship"] = {role: {"sha256": sha(value), "bytes": len(value)} for role, value in sponsorship.items()}
    snapshot.stable()
    spec.update(state="FROZEN_SETTLED_PREFIX", captured_utc=datetime.now(timezone.utc).isoformat(),
                sample_bodies_read=len(rows), capture_is_admission=False)
    return spec


def sponsorship_check(row, raw, sponsorship, *, iv_sha, job_sha, child_started, as_of):
    ready, permit, observation = (json.loads(sponsorship[key]) for key in ("ready", "permit", "observation"))
    require(all(value == canonical(json.loads(value)) for value in sponsorship.values()), "Canonical immutable Goal sponsorship required")
    require(ready["schema_version"] == 1 and ready["state"] == "WAITING_FOR_NATIVE_ACTIVE_GOAL_PERMIT"
            and ready["owner"] == permit["owner"] == permit["goal_thread_id"] == TASK
            and permit["goal_status"] == "active" and permit["goal_source"] == "actual native tools.get_goal"
            and ready["sample_created"] is False and ready["model_contact_started"] is False
            and ready["no_resend"] is True, "Actual native Goal sponsorship differs")
    require(ready["invocation_sha256"] == permit["invocation_sha256"] == iv_sha
            and ready["job_sha256"] == job_sha and permit["ready_sha256"] == sha(sponsorship["ready"])
            and all(ready[key] == permit[key] == row[key] for key in ("endpoint_ordinal", "logical_sample_id", "request_sha256")),
            "Exact per-request Goal join differs")
    require(set(observation) == {"schema_version", "owner", "native_goal", "permit", "ready_metadata", "ready_sha256"}
            and observation["schema_version"] == 1 and observation["owner"] == TASK and observation["permit"] == permit
            and observation["ready_metadata"] == ready and observation["ready_sha256"] == sha(sponsorship["ready"]),
            "Rich Goal observation envelope differs")
    goal = observation["native_goal"]["goal"]
    require(goal["threadId"] == TASK and goal["status"] == "active" and goal["updatedAt"] == permit["goal_updated_at"]
            and goal["tokensUsed"] == permit["goal_tokens_used"], "Rich native Goal identity differs")
    started = json.loads(raw["attempt-started.json"])
    rt, pt, st = instant(ready["ready_utc"]), instant(permit["observed_utc"]), instant(started["time"])
    require(child_started <= rt <= pt <= st <= as_of and (st - pt).total_seconds() <= 120,
            "Attempt outside ready/Goal/permit chronology or lease")
    return st


def own_turn_as_of(raw, *, started, as_of):
    rows = [json.loads(line) for line in raw.splitlines()]
    starts = [r for r in rows if r.get("type") == "event_msg" and r.get("payload", {}).get("type") == "task_started"]
    ends = [r for r in rows if r.get("type") == "event_msg" and r.get("payload", {}).get("type") == "task_complete"]
    require(len(starts) == len(ends) == 1 and started <= instant(starts[0]["timestamp"])
            <= instant(ends[0]["timestamp"]) <= as_of, "Own native completion outside frozen as-of prefix")


def add_identities(identities, thread, turn):
    for kind, value in (("sol_thread", thread), ("sol_turn", turn)):
        require(isinstance(value, str) and str(uuid.UUID(value)) == value, "Typed native UUID required")
        item = (kind, sha(value.encode()))
        require(item not in identities, "Duplicate native identity; disjoint merge required")
        identities.add(item)


def prior_identities(rows):
    require(isinstance(rows, list), "Explicit typed prior identities required")
    result = set()
    for item in rows:
        require(isinstance(item, list) and len(item) == 2 and item[0] in {"sol_thread", "sol_turn"}
                and isinstance(item[1], str) and len(item[1]) == 64 and all(c in "0123456789abcdef" for c in item[1]),
                "Typed prior identity commitment differs")
        require(tuple(item) not in result, "Duplicate prior identity")
        result.add(tuple(item))
    return result


def runtime(snapshot):
    sources = {path: snapshot.get(path, {"sha256": digest, "bytes": path.stat().st_size}) for path, digest in CODE_PINS.items()}
    native_path = REPO / "src/hbqrs/codex_receipts.py"
    native = loaded(sources[native_path], native_path)
    subset = loaded(sources[SUBSET], SUBSET)
    validator = loaded(sources[HERE / "validate_response.py"], HERE / "validate_response.py")
    common = {"Path": Path, "json": json, "require": require,
              "prepare": SimpleNamespace(digest=sha, canonical=canonical, checked=checked)}
    assignments = [node.value for node in ast.parse(sources[HERE / "continue_sol.py"]).body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FILES" for target in node.targets)]
    require(len(assignments) == 1 and ast.literal_eval(assignments[0]) == FILES, "Pinned native prefix file inventory differs")
    validate = selected(sources[HERE / "analysis.py"], HERE / "analysis.py", ["validate_continuation"], dict(common))["validate_continuation"]
    prefix = selected(sources[HERE / "continue_sol.py"], HERE / "continue_sol.py", ["prefix_receipt"],
                      {"Path": Path, "json": json, "FILES": FILES, "codex_receipts": native,
                       "checked": checked, "within": within, "digest": sha})["prefix_receipt"]
    semantics = selected(sources[HERE / "analysis_chain.py"], HERE / "analysis_chain.py", ["replay_semantics"], dict(common))["replay_semantics"]
    tools = selected(sources[LAUNCHER], LAUNCHER, ["tools"], {"json": json, "adapter": SimpleNamespace(TOOL_PROFILE=CATALOG)})["tools"]
    call = next(n for n in ast.parse(sources[PATCH]).body if isinstance(n, ast.FunctionDef) and n.name == "_call_codex")
    expressions = [n.value for n in call.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "arguments" for t in n.targets)]
    require(len(expressions) == 1, "Exact frozen native argv factory required")

    def command(sample):
        args = eval(compile(ast.Expression(expressions[0]), str(PATCH), "eval"), {"__builtins__": {"str": str}},
                    {"model": "gpt-6.1-sol", "reasoning": "high", "response_schema": sample / "schema.json",
                     "message_path": sample / "responses/batch-0001.attempt-0001.message.json", "output_dir": sample})
        args[-1:-1] = tools()
        args.remove("--ephemeral")
        args.insert(1, "--json")
        return [str(CLI), *args[:-1], "<prompt-via-stdin>"]

    return validate, prefix, semantics, subset, validator, command


def replay_prefix(spec, *, specification_sha256):
    """Qualify only the frozen prefix; return predictions with all release gates held."""
    require(sha(canonical(spec)) == specification_sha256, "Explicit canonical frozen specification commitment required")
    snapshot = Snapshot()
    sources, job, iv, child, base, source, rows = validate_spec(spec, snapshot, captured=True)
    snapshot.get(SELF, {"sha256": reader_pin(), "bytes": len(SELF_RAW)})
    validate, prefix, semantics, subset, validator, command = runtime(snapshot)
    validate(source, base, "sol", base_raw=sources[ORIGINAL], derived_root=MANIFEST.parent)
    require(job["validator_sha256"] == CODE_PINS[HERE / "validate_response.py"]
            and source["implementation"]["semantic_validator_sha256"] == job["validator_sha256"]
            and source["implementation"]["schema_subset_sha256"] == CODE_PINS[SUBSET]
            and job["receipt_reader_sha256"] == CODE_PINS[REPO / "src/hbqrs/codex_receipts.py"], "Frozen validator/native implementation join differs")
    artifacts = {}
    required = {"context.txt"}
    for row in rows:
        required.update([row["prompt_path"], row["schema_path"], *(item["input_path"] for item in row["sources"])])
    for name in sorted(required):
        artifacts[name] = snapshot.get(within(MANIFEST.parent, name), source["artifacts"][name])
    identities = prior_identities(spec["prior_native_identities"])
    previous = set(identities)
    records, predictions, states = [], [], Counter()
    as_of = instant(spec["as_of_utc"])
    for pin, row in zip(spec["samples"], rows):
        sample, raw, sponsorship = sample_capture(snapshot, row)
        require(pin["files"] == {name: {"sha256": sha(value), "bytes": len(value)} for name, value in sorted(raw.items())}
                and pin["sponsorship"] == {role: {"sha256": sha(value), "bytes": len(value)} for role, value in sponsorship.items()},
                "Frozen prefix artifact inventory/commitment differs")
        for path_key, digest_key, size_key in (("prompt_path", "prompt_sha256", "prompt_bytes"), ("schema_path", "schema_sha256", "schema_bytes")):
            require(sha(artifacts[row[path_key]]) == row[digest_key] and len(artifacts[row[path_key]]) == row[size_key], "Frozen prompt/schema differs")
        require(all(sha(artifacts[item["input_path"]]) == item["sha256"] for item in row["sources"]), "Frozen source differs")
        started = sponsorship_check(row, raw, sponsorship, iv_sha=sha(sources[LIFE / "invocation.json"]),
                                    job_sha=sha(sources[OUT / "job.json"]), child_started=instant(child["started_utc"]), as_of=as_of)
        native = json.loads(raw["native-result.json"])
        require(native["command"] == command(sample), "Exact all-tools-disabled native startup command differs")
        own_turn_as_of(raw[native["provider_artifacts"]["codex_rollout"]["path"]], started=started, as_of=as_of)
        receipt, thread, turn = prefix(OUT, row, artifacts, job)
        add_identities(identities, thread, turn)
        answer = semantics(row, sample, artifacts, subset, validator)
        state = json.loads(raw["terminal.json"])["state"]
        require((answer is not None) == (state == "accepted"), "Frozen semantic state differs")
        states[state] += 1
        for name, item in receipt["artifacts"].items():
            require(pin["files"].get(name) == item, "Replayed native/sample capture differs")
        vote = None if answer is None else {"request": row, "response": answer["response"], "abstention": answer["abstention"]}
        record = {"request": row, "state": state, "accepted": vote, "prefix_position": pin["prefix_position"],
                  "original_endpoint_ordinal": row["endpoint_ordinal"], "original_request_ordinal": row["ordinal"],
                  "source_index_namespace": NAMESPACE, "source_index": 0,
                  "terminal_sha256": receipt["terminal_sha256"], "native_evidence_verified": True,
                  "terminal_evidence_verified": True, "goal_sponsorship_verified": True,
                  "qualified_startup_command_verified": True, "started_time": json.loads(raw["attempt-started.json"])["time"],
                  "native_identities": [["sol_thread", sha(thread.encode())], ["sol_turn", sha(turn.encode())]],
                  "qualification": {"native_receipt": receipt, "sponsorship": pin["sponsorship"]},
                  "evidence_sha256": sha(canonical({"native_receipt": receipt, "sponsorship": pin["sponsorship"]}))}
        records.append({"identity": ["sol", row["logical_sample_id"]], "record": record})
        if vote is not None:
            predictions.append({"logical_sample_id": row["logical_sample_id"], "vote": vote})
    require(dict(states) == {key: value for key, value in spec["expected_counts"].items() if value}, "Prospective accepted/rejected counts differ")
    snapshot.stable()
    report = {"schema_version": 1, "policy": POLICY, "state": "QUALIFIED_FROZEN_SETTLED_PREFIX_RELEASE_HELD",
              "owner": TASK, "reader_sha256": reader_pin(), "specification_sha256": specification_sha256,
              "as_of_utc": spec["as_of_utc"], "source_index_namespace": NAMESPACE, "original_denominator": DENOMINATOR,
              "first_original_endpoint_ordinal": FIRST, "through_original_endpoint_ordinal": rows[-1]["endpoint_ordinal"],
              "qualified_settlements": len(rows), "qualified_accepted": states["accepted"], "semantic_rejected": states["semantic_rejected"],
              "remaining_original_positions_unrepresented": DENOMINATOR - len(rows),
              "reserved_suffix_unresolved": LAST - rows[-1]["endpoint_ordinal"], "sample_bodies_read": len(rows),
              "human_labels_opened": False, "provider_calls": 0, "reservation_released": False,
              "outer_return_required_for_this_prefix": False, "outer_native_termination_proven": False,
              "remote_or_billing_quiescence_proven": False, "production_wire_catalog_attested": False,
              "tool_proof_level": "Exact startup command/catalog and historical native local fixture; zero observed per-attempt tools",
              "full_label_release_gate_passed": False, "full_coverage_established": False, "full_goal_complete": False,
              "disjoint_merge_required": True, "sources_mixed": False, "promotion_established": False,
              "cross_source_native_identity_disjointness_proven": False,
              "original_endpoint_positions": [row["endpoint_ordinal"] for row in rows],
              "original_request_positions": [row["ordinal"] for row in rows],
              "source_commitments": snapshot.commitments()}
    return {"report": report, "records": records, "predictions": {"sol": predictions, "grok": []},
            "identities": [list(item) for item in sorted(identities - previous)]}


def write_output(result, output_dir, *, owned_output_root):
    output_dir, root = plain(output_dir), plain(owned_output_root)
    require(output_dir != root and output_dir.is_relative_to(root) and not output_dir.exists(), "Fresh caller-owned output directory required")
    inputs = [plain(Path(path)) for path in result["report"]["source_commitments"]]
    require(all(not path.is_relative_to(output_dir) and output_dir != path for path in inputs)
            and all(not output_dir.is_relative_to(source_root) for source_root in (OUT, LIFE, GATES, OBSERVATIONS, MANIFEST.parent)),
            "Output overlaps retained source scope")
    for path, pin in result["report"]["source_commitments"].items():
        checked(Path(path), pin["sha256"], pin["bytes"])
    payloads = {"report.json": canonical(result["report"]), "qualified-prefix-records.json": canonical(result["records"]),
                "normalized-predictions.json": canonical(result["predictions"]), "native-identities.json": canonical(result["identities"])}
    output_dir.mkdir(parents=False, exist_ok=False)
    for name, raw in payloads.items():
        with within(output_dir, name).open("xb") as handle:
            handle.write(raw)
    manifest = {"schema_version": 1, "policy": POLICY, "state": result["report"]["state"],
                "owner": TASK, "source_index_namespace": NAMESPACE,
                "specification_sha256": result["report"]["specification_sha256"],
                "reader_sha256": result["report"]["reader_sha256"], "as_of_utc": result["report"]["as_of_utc"],
                "original_endpoint_positions": result["report"]["original_endpoint_positions"],
                "original_request_positions": result["report"]["original_request_positions"],
                "qualified_settlements": result["report"]["qualified_settlements"],
                "qualified_accepted": result["report"]["qualified_accepted"],
                "semantic_rejected": result["report"]["semantic_rejected"],
                "remaining_original_positions_unrepresented": result["report"]["remaining_original_positions_unrepresented"],
                "original_denominator": DENOMINATOR,
                "first_original_endpoint_ordinal": result["report"]["first_original_endpoint_ordinal"],
                "through_original_endpoint_ordinal": result["report"]["through_original_endpoint_ordinal"],
                "metadata_commitments": {str(path): {"sha256": digest, "bytes": size} for path, (digest, size) in METADATA_PINS.items()},
                "runtime_commitments": {str(path): {"sha256": digest} for path, digest in CODE_PINS.items()},
                "files": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in payloads.items()},
                "human_labels_opened": False, "provider_calls": 0, "full_label_release_gate_passed": False,
                "reservation_released": False, "outer_native_termination_proven": False,
                "remote_or_billing_quiescence_proven": False, "production_wire_catalog_attested": False,
                "full_coverage_established": False, "full_goal_complete": False, "promotion_established": False,
                "cross_source_native_identity_disjointness_proven": False,
                "sources_mixed": False, "disjoint_merge_required": True}
    with within(output_dir, "manifest.json").open("xb") as handle:
        handle.write(canonical(manifest))
    require(all(read(within(output_dir, name)) == raw for name, raw in payloads.items())
            and read(within(output_dir, "manifest.json")) == canonical(manifest), "Created output readback differs")
    for path, pin in result["report"]["source_commitments"].items():
        checked(Path(path), pin["sha256"], pin["bytes"])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specification", type=Path, required=True)
    parser.add_argument("--specification-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--owned-output-root", type=Path, required=True)
    args = parser.parse_args()
    raw = checked(args.specification, args.specification_sha256)
    spec = json.loads(raw)
    require(raw == canonical(spec), "Canonical frozen specification bytes required")
    result = replay_prefix(spec, specification_sha256=args.specification_sha256)
    require(read(args.specification) == raw, "Specification changed during replay")
    manifest = write_output(result, args.output_dir, owned_output_root=args.owned_output_root)
    print(json.dumps({"state": manifest["state"], "manifest_sha256": sha(canonical(manifest)),
                      "reader_sha256": manifest["reader_sha256"], "specification_sha256": manifest["specification_sha256"],
                      "as_of_utc": manifest["as_of_utc"],
                      "qualified_settlements": result["report"]["qualified_settlements"],
                      "qualified_accepted": result["report"]["qualified_accepted"],
                      "semantic_rejected": result["report"]["semantic_rejected"], "human_labels_opened": False, "provider_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
