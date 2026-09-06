"""Governed execution of one reviewed Dryad qualification cohort."""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PLAN_SOURCE = ROOT / "campaign_plan.py"
LEDGER_SOURCE = ROOT / "cohort_ledger.py"
NATIVE_SOURCE = ROOT / "native_admission.py"
SOURCE_PINS = {
    PLAN_SOURCE: "46a98eb1134d308a96bd7a34aee4b92a26f2e85e92768305e813daa08cb7b655",
    LEDGER_SOURCE: "ec70e52eb99abdf21342a949a5a77f1a19f542ee585e198b5f8eb147e2594a3d",
    NATIVE_SOURCE: "11d7f8bec870a0945fe2eb169fa1580bc351b4e07eaa46b831c4e8703431d122",
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _hash(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _require(value: bool, message: str) -> None:
    if not value: raise ValueError(message)
def _canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _plain(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try: info = candidate.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400: raise ValueError("Path contains a link or reparse point")
    result = absolute.resolve()
    if directory is True: _require(result.is_dir(), "Expected directory")
    if directory is False: _require(result.is_file(), "Expected file")
    return result


def _relative(root: Path, name: str, *, directory: bool | None = None) -> Path:
    path = Path(name)
    _require(isinstance(name, str) and name and not path.is_absolute() and all(part not in (".", "..") for part in path.parts), "Relative path differs")
    result = _plain(root / path, directory=directory)
    _require(result.is_relative_to(root), "Relative path escapes root")
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, f"{label} has duplicate keys")
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f"{label} has a nonfinite constant")
    try: value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _load(path: Path, raw: bytes) -> ModuleType:
    name = "_dryad_execution_" + uuid.uuid4().hex
    module = ModuleType(name); module.__file__ = str(path); module.__package__ = ""; sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
        return module
    finally: sys.modules.pop(name, None)


def _sources() -> tuple[dict[Path, bytes], tuple[ModuleType, ModuleType, ModuleType]]:
    captured = {_plain(path, directory=False): path.read_bytes() for path in SOURCE_PINS}
    _require(all(_hash(captured[path]) == expected for path, expected in SOURCE_PINS.items()), "Execution source pin differs")
    own = _plain(Path(__file__), directory=False); captured[own] = own.read_bytes()
    return captured, tuple(_load(path, raw) for path, raw in captured.items() if path != own)  # type: ignore[return-value]


def _unchanged(captured: Mapping[Path, bytes]) -> None: _require(all(path.read_bytes() == raw for path, raw in captured.items()), "Execution source changed")


def _plan(plan_root: Path, expected: str) -> tuple[dict[str, Any], bytes]:
    raw = _relative(plan_root, "plan.json", directory=False).read_bytes(); _require(_hash(raw) == expected, "Plan anchor differs")
    plan = _json(raw, "Plan"); _require(len(plan.get("passes", [])) == 18 and len(plan.get("requests", [])) == 261, "Plan geometry differs")
    return plan, raw


def _groups(ledger: ModuleType, plan: Mapping[str, Any], number: int) -> tuple[int, ...]:
    groups = ledger.cohort_groups(plan); _require(type(number) is int and 1 <= number <= len(groups), "Cohort number differs")
    return groups[number - 1]


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _route_hash(route: Mapping[str, Any]) -> str: return _hash(_canonical(dict(route)))


def prepare_cohort(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int, route: Mapping[str, Any], *, expected_plan_sha256: str, expected_previous_settlement_sha256: str) -> dict[str, str]:
    """Provider-free creation of the exact prepared/route records for one cohort."""
    _require(_HASH.fullmatch(expected_plan_sha256) and _HASH.fullmatch(expected_previous_settlement_sha256), "Trusted anchors differ")
    captured, (plan_module, ledger, _) = _sources()
    public_inputs_path = _plain(public_inputs_path, directory=False); plan_root = _plain(plan_root, directory=True); execution_root = _plain(execution_root, directory=True)
    _require(not plan_root.is_relative_to(execution_root) and not execution_root.is_relative_to(plan_root), "Plan and execution roots must differ")
    _require(plan_module.verify(public_inputs_path, plan_root).get("plan.json") == expected_plan_sha256, "Plan verification differs")
    plan, raw = _plan(plan_root, expected_plan_sha256); ordinals = _groups(ledger, plan, cohort_number)
    _require(isinstance(route, Mapping) and _route_hash(route), "Route snapshot differs")
    prefix = execution_root / "cohorts" / f"{cohort_number:04d}"
    prepared = {"schema_version": 1, "cohort_number": cohort_number, "plan_sha256": expected_plan_sha256,
                "execution_source_sha256": _hash(captured[Path(__file__).resolve()]),
                "previous_settlement_sha256": expected_previous_settlement_sha256, "request_ordinals": list(ordinals), "route_sha256": _route_hash(route)}
    lock, token = _lock(execution_root)
    try:
        if cohort_number == 1:
            _require(not any(path != lock for path in execution_root.iterdir()), "Fresh first cohort requires an empty execution root")
            (execution_root / "cohorts").mkdir(); (execution_root / "contacts").mkdir()
        ledger.verify_prefix(execution_root, raw, expected_plan_sha256, expected_previous_settlement_sha256, cohort_number - 1)
        _write_new(prefix / "prepared.json", _canonical(prepared)); _write_new(prefix / "route.json", _canonical(dict(route)))
        _unchanged(captured)
    finally:
        if lock.is_file() and lock.read_bytes() == token: lock.unlink()


    return {"prepared_sha256": _hash((prefix / "prepared.json").read_bytes()), "route_sha256": _route_hash(route)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or execute one reviewed Dryad qualification cohort.")
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("prepare", "run"):
        command = actions.add_parser(name)
        command.add_argument("--public-inputs", type=Path, required=True)
        command.add_argument("--plan-root", type=Path, required=True)
        command.add_argument("--execution-root", type=Path, required=True)
        command.add_argument("--cohort", type=int, required=True)
        command.add_argument("--plan-sha256", required=True)
        command.add_argument("--previous-settlement-sha256", required=True)
        if name == "prepare":
            command.add_argument("--route-json", type=Path, required=True)
        else:
            command.add_argument("--queue-root", type=Path, required=True)
            command.add_argument("--prepared-sha256", required=True)
            command.add_argument("--review-sha256", required=True)
            command.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    common = dict(expected_plan_sha256=args.plan_sha256, expected_previous_settlement_sha256=args.previous_settlement_sha256)
    if args.action == "prepare":
        route = _json(_plain(args.route_json, directory=False).read_bytes(), "Route")
        result = prepare_cohort(args.public_inputs, args.plan_root, args.execution_root, args.cohort, route, **common)
    else:
        result = run_cohort(args.public_inputs, args.plan_root, args.execution_root, args.cohort, args.queue_root,
                            expected_prepared_sha256=args.prepared_sha256, expected_review_sha256=args.review_sha256,
                            expected_source_sha256=args.source_sha256, **common)
    print(_canonical(result).decode("utf-8"))
    return 0


def _review(path: Path, expected: str, prepared: str, ledger: ModuleType) -> dict[str, Any]:
    raw = path.read_bytes(); _require(_hash(raw) == expected, "Reviewed record hash differs")
    value = ledger._json_object(raw, "Review")
    value["_window"] = ledger._review_window(value, prepared, ledger.REVIEWER_TASK)
    return value


def _lock(root: Path) -> tuple[Path, bytes]:
    path = root / ".launch.lock"; token = uuid.uuid4().hex.encode("ascii")
    _write_new(path, token); return path, token


def _fresh_route(broker: Any, route: Mapping[str, Any]) -> None:
    live = broker._grok_native_route(route["name"])
    _require(isinstance(live, dict) and _canonical(live) == _canonical(dict(route)), "Broker route is no longer exact")


def run_cohort(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int, queue_root: Path, broker_factory: Any | None = None, *, expected_plan_sha256: str, expected_previous_settlement_sha256: str, expected_prepared_sha256: str, expected_review_sha256: str, expected_source_sha256: str) -> dict[str, Any]:
    """Execute only one externally reviewed cohort through the injected Broker transport."""
    _require(all(_HASH.fullmatch(value) for value in (expected_plan_sha256, expected_previous_settlement_sha256, expected_prepared_sha256, expected_review_sha256, expected_source_sha256)), "Trusted anchors differ")
    captured, (plan_module, ledger, native) = _sources(); own = _plain(Path(__file__), directory=False)
    _require(_hash(own.read_bytes()) == expected_source_sha256 and captured[own] == own.read_bytes(), "Reviewed execution source differs")
    public_inputs_path = _plain(public_inputs_path, directory=False); plan_root = _plain(plan_root, directory=True); execution_root = _plain(execution_root, directory=True)
    _require(not plan_root.is_relative_to(execution_root) and not execution_root.is_relative_to(plan_root), "Plan and execution roots must differ")
    lock, token = _lock(execution_root)
    try:
        _require(plan_module.verify(public_inputs_path, plan_root).get("plan.json") == expected_plan_sha256, "Plan verification differs")
        plan, raw = _plan(plan_root, expected_plan_sha256); ordinals = _groups(ledger, plan, cohort_number)
        prefix = execution_root / "cohorts" / f"{cohort_number:04d}"; prepared_path = _relative(execution_root, f"cohorts/{cohort_number:04d}/prepared.json", directory=False); prepared_raw = prepared_path.read_bytes()
        _require(_hash(prepared_raw) == expected_prepared_sha256, "Prepared record hash differs")
        prepared = _json(prepared_raw, "Prepared"); route_path = _relative(execution_root, f"cohorts/{cohort_number:04d}/route.json", directory=False); route_raw = route_path.read_bytes(); route = _json(route_raw, "Route")
        ledger._assert_schema(prepared, {"schema_version", "cohort_number", "plan_sha256", "previous_settlement_sha256", "request_ordinals", "route_sha256", "execution_source_sha256"}, "Prepared")
        _require(type(prepared["cohort_number"]) is int and prepared["cohort_number"] == cohort_number
                 and isinstance(prepared["request_ordinals"], list) and all(type(value) is int for value in prepared["request_ordinals"])
                 and prepared["request_ordinals"] == list(ordinals) and prepared["plan_sha256"] == expected_plan_sha256
                 and prepared["previous_settlement_sha256"] == expected_previous_settlement_sha256
                 and prepared["route_sha256"] == _route_hash(route) and prepared["execution_source_sha256"] == expected_source_sha256,
                 "Prepared cohort differs")
        review_path = _relative(execution_root, f"cohorts/{cohort_number:04d}/review.json", directory=False); review_raw = review_path.read_bytes(); review = _review(review_path, expected_review_sha256, expected_prepared_sha256, ledger)
        pending = frozenset({f"cohorts/{cohort_number:04d}/prepared.json", f"cohorts/{cohort_number:04d}/route.json", f"cohorts/{cohort_number:04d}/review.json"})
        prior = ledger.verify_prefix(execution_root, raw, expected_plan_sha256, expected_previous_settlement_sha256, cohort_number - 1, pending)
        _require(all(contact["execution_source_sha256"] == expected_source_sha256 for contact in prior["contacts"].values()), "Prior executor source differs")
        protected_ledger, protected_directories = ledger._ledger_snapshot(execution_root)
        def prefix_unchanged() -> None:
            _require(ledger._ledger_snapshot(execution_root) == (protected_ledger, protected_directories), "Settled prefix or contact inventory changed")
        if cohort_number > 1:
            previous_raw = _relative(execution_root, f"cohorts/{cohort_number - 1:04d}/settlement.json", directory=False).read_bytes()
            _require(_hash(previous_raw) == expected_previous_settlement_sha256, "Previous settlement changed")
            previous_time = ledger._parse_utc(ledger._json_object(previous_raw, "Previous settlement")["settled_at"], "Previous settlement time")
            _require(review["_window"][0] >= previous_time, "Review precedes previous settlement")
        def approval_unchanged() -> None:
            _require(prepared_path.read_bytes() == prepared_raw and route_path.read_bytes() == route_raw and review_path.read_bytes() == review_raw, "Approval record changed")
        _require(review["_window"][0] <= datetime.now(timezone.utc) <= review["_window"][1], "Review window expired")
        queue_root = _plain(queue_root, directory=True)
        for protected in (plan_root, execution_root, REPOSITORY):
            _require(not queue_root.is_relative_to(protected) and not protected.is_relative_to(queue_root), "Queue root overlaps study evidence")
        runtime = native.load_runtime(); runtime.verify()
        factory = broker_factory or (lambda root, cls: cls(root))
        _require(callable(factory), "Broker factory differs")
        broker = factory(queue_root, runtime.broker.Broker)
        _require(type(broker) is runtime.broker.Broker and _plain(broker.root, directory=True) == queue_root, "Broker type or root differs"); _fresh_route(broker, route)
        requests = {row["ordinal"]: row for row in plan["requests"]}; passes = {row["pass_id"]: row for row in plan["passes"]}; current = set(ordinals)
        payloads = {}
        for ordinal in ordinals:
            request = requests[ordinal]
            source = passes[request["pass_id"]]
            for relative, expected_hash, expected_bytes in (
                (request["prompt_path"], request["prompt_sha256"], request["prompt_bytes"]),
                (source["input_path"], source["source_sha256"], source["source_bytes"]),
                (request["schema_path"], request["schema_sha256"], request["schema_bytes"]),
            ):
                path = _relative(plan_root, relative, directory=False)
                contents = path.read_bytes()
                _require(_hash(contents) == expected_hash and len(contents) == expected_bytes, "Frozen payload commitment differs")
                payloads[path] = contents
        def payloads_unchanged() -> None:
            _require(all(_plain(path, directory=False).read_bytes() == contents for path, contents in payloads.items()), "Frozen payload changed")
        phase = {"value": "before_contact"}
        def check(context: Mapping[str, Any], *, inner: bool = False) -> None:
            batch = context["batch"]; output = Path(context["output_dir"]).resolve(); pass_id = next(key for key, value in passes.items() if (execution_root / value["run_path"]).resolve() == output)
            request = next(row for row in requests.values() if row["pass_id"] == pass_id and row["batch_number"] == batch["number"])
            if request["ordinal"] not in current: raise runtime.runner.RetryDisclosurePause("outside reviewed cohort")
            if not inner:
                phase["value"] = "before_contact"
            prompt = _relative(plan_root, request["prompt_path"], directory=False).read_bytes(); schema = runtime.runner._json_bytes(runtime.runner._response_schema())
            _require(_hash(prompt) == request["prompt_sha256"] and len(prompt) == request["prompt_bytes"]
                     and _hash(schema) == request["schema_sha256"] and len(schema) == request["schema_bytes"], "Planned payload differs")
            prompt_record, schema_record = context["prompt"], context["response_schema"]
            _require(isinstance(prompt_record, Mapping) and isinstance(schema_record, Mapping), "Runner context descriptors differ")
            _require(prompt_record.get("text", "").encode("utf-8") == prompt and prompt_record.get("sha256") == _hash(prompt) and prompt_record.get("bytes") == len(prompt), "Prompt binding differs")
            schema_text = schema_record.get("text")
            _require(isinstance(schema_text, str) and runtime.runner._json_bytes(json.loads(schema_text)) == schema and schema_record.get("sha256") == _hash(schema_text.encode()) and schema_record.get("bytes") == len(schema_text.encode()), "Schema binding differs")
            _require(context["batch"]["question_ids"] == request["question_ids"] and context["attempt"]["number"] == 1, "Attempt binding differs")
            prefix_unchanged(); payloads_unchanged(); approval_unchanged(); runtime.verify(); _fresh_route(broker, route); _unchanged(captured)
            now = datetime.now(timezone.utc); _require(review["_window"][0] <= now <= review["_window"][1], "Review window expired")
            if inner:
                contact = {"schema_version": 1, "cohort_number": cohort_number, "ordinal": request["ordinal"], "plan_sha256": expected_plan_sha256, "prepared_sha256": expected_prepared_sha256, "review_sha256": expected_review_sha256, "route_sha256": _route_hash(route), "prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"], "admitted_at": now.isoformat().replace("+00:00", "Z")}
                relative = f"contacts/request-{request['ordinal']:04d}.json"
                contact_raw = _canonical(contact)
                _write_new(execution_root / relative, contact_raw)
                protected_ledger[relative] = _hash(contact_raw)
                phase["value"] = "inner_admitted"
        def runtime_guard() -> None:
            prefix_unchanged(); payloads_unchanged(); approval_unchanged(); runtime.verify(); _fresh_route(broker, route); _unchanged(captured)
            if phase["value"] != "in_flight":
                _require(review["_window"][0] <= datetime.now(timezone.utc) <= review["_window"][1], "Review window expired")
            if phase["value"] == "inner_admitted":
                phase["value"] = "in_flight"
        transport = runtime.transport.bind_grok_broker_transport(broker=broker, route=route, before_contact=lambda context: check(context, inner=True), runtime_check=runtime_guard)
        # The adapter's runtime_check has no attempt context; outer check carries the exact request binding.
        for pass_id in dict.fromkeys(requests[number]["pass_id"] for number in ordinals):
            record = passes[pass_id]; source = _relative(plan_root, record["input_path"], directory=False); destination = _relative(execution_root, record["run_path"])
            try:
                runtime.runner.run_judge(artifact_path=source, bundle_id="prose.short_story", provider="grok", model="grok-4.6", output_dir=destination, registry=REPOSITORY / "registry/all_modules.json", bundles=REPOSITORY / "bundles/all_bundles.json", question_ids=plan["runtime"]["question_ids"], batch_size=record["batch_size"], batch_attempts=1, reasoning="high", allow_remote=True, resume=destination.exists(), timeout=route["timeout_seconds"], artifact_id=record["opaque_story_id"], judge_id="grok:grok-4.6", allow_unattested_reasoning=True, attempt_lifecycle_policy="terminal_sidecar_v1", before_provider_attempt=check, grok_transport=transport, grok_transport_sha256=runtime.transport_sha256)
            except runtime.runner.RetryDisclosurePause:
                pass
        evidence_before = ledger._regular_tree(execution_root, "Execution evidence")
        settlement_contacts = []
        checked_runs = {}
        prior_requests = {contact["request_id_hash"] for contact in prior["contacts"].values()}
        prior_sessions = {contact["session_id_hash"] for contact in prior["contacts"].values()}
        for ordinal in ordinals:
            request = requests[ordinal]; record = passes[request["pass_id"]]; run_root = _relative(execution_root, record["run_path"])
            if request["pass_id"] not in checked_runs:
                source_text = _relative(plan_root, record["input_path"], directory=False).read_bytes().decode("utf-8")
                accepted_count = max(requests[number]["batch_number"] for number in ordinals if requests[number]["pass_id"] == request["pass_id"])
                if accepted_count < (178 + record["batch_size"] - 1) // record["batch_size"]:
                    _relative(run_root, f"responses/batch-{accepted_count + 1:04d}.prompt.txt.gz", directory=False)
                checked_runs[request["pass_id"]] = native.admit_prefix(
                    run_root, source={"opaque_story_id": record["opaque_story_id"], "story_text": source_text,
                                      "artifact_path": str(_relative(plan_root, record["input_path"], directory=False))},
                    batch_size=record["batch_size"], expected_batches=accepted_count,
                    approved_routes={**prior["routes"], _route_hash(route): route}, runtime=runtime)
            checkpoint_path = _relative(run_root, f"responses/batch-{request['batch_number']:04d}.json", directory=False)
            checkpoint_raw = checkpoint_path.read_bytes(); checkpoint = _json(checkpoint_raw, "Checkpoint")
            receipt_path = _relative(run_root, f"responses/grok-broker/batch-{request['batch_number']:04d}-attempt-0001/receipt.json", directory=False)
            receipt_raw = receipt_path.read_bytes(); receipt = _json(receipt_raw, "Native receipt")
            identity = checked_runs[request["pass_id"]]["native_identities"][request["batch_number"] - 1]
            _require(receipt.get("route_sha256") == _route_hash(route) and checkpoint.get("provider", {}).get("evidence_sha256") == _hash(receipt_raw), "Native receipt/checkpoint differs")
            _require(identity["request_id_hash"] not in prior_requests and identity["session_id_hash"] not in prior_sessions, "Native identity is duplicated")
            prior_requests.add(identity["request_id_hash"])
            prior_sessions.add(identity["session_id_hash"])
            contact_raw = _relative(execution_root, f"contacts/request-{ordinal:04d}.json", directory=False).read_bytes()
            contact = ledger._json_object(contact_raw, "Contact")
            expected_contact = {"schema_version": 1, "cohort_number": cohort_number, "ordinal": ordinal,
                                "plan_sha256": expected_plan_sha256, "prepared_sha256": expected_prepared_sha256,
                                "review_sha256": expected_review_sha256, "route_sha256": _route_hash(route),
                                "prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"],
                                "admitted_at": contact.get("admitted_at")}
            _require(contact_raw == _canonical(expected_contact), "Prospective contact binding differs")
            admitted_at = ledger._parse_utc(contact["admitted_at"], "Contact admission")
            _require(review["_window"][0] <= admitted_at <= review["_window"][1], "Contact outside review window")
            settlement_contacts.append({"ordinal": ordinal, "contact_sha256": _hash(contact_raw), "checkpoint_sha256": _hash(checkpoint_raw), "request_id_hash": identity["request_id_hash"], "session_id_hash": identity["session_id_hash"]})
        settled_at = datetime.now(timezone.utc)
        for ordinal in ordinals:
            contact = ledger._json_object((execution_root / "contacts" / f"request-{ordinal:04d}.json").read_bytes(), "Contact")
            _require(ledger._parse_utc(contact["admitted_at"], "Contact admission") <= settled_at, "Settlement clock precedes contact")
        runtime_guard()
        _require(plan_module.verify(public_inputs_path, plan_root).get("plan.json") == expected_plan_sha256, "Plan changed during execution")
        pending_contacts = pending | frozenset(f"contacts/request-{ordinal:04d}.json" for ordinal in ordinals)
        _require(ledger.verify_prefix(execution_root, raw, expected_plan_sha256, expected_previous_settlement_sha256, cohort_number - 1, pending_contacts) == prior, "Prior ledger changed")
        _require(ledger._regular_tree(execution_root, "Execution evidence") == evidence_before, "Evidence changed before settlement")
        settlement = {"schema_version": 1, "cohort_number": cohort_number, "plan_sha256": expected_plan_sha256,
                      "prepared_sha256": expected_prepared_sha256, "review_sha256": expected_review_sha256,
                      "route_sha256": _route_hash(route), "previous_settlement_sha256": expected_previous_settlement_sha256,
                      "settled_at": settled_at.isoformat().replace("+00:00", "Z"), "contacts": settlement_contacts}
        settlement_path = prefix / "settlement.json"; _write_new(settlement_path, _canonical(settlement))
        settlement_hash = _hash(settlement_path.read_bytes())
        ledger.verify_prefix(execution_root, raw, expected_plan_sha256, settlement_hash, cohort_number)
        _unchanged(captured); return {"cohort_number": cohort_number, "ordinals": list(ordinals), "status": "settled", "settlement_sha256": settlement_hash, "execution_source_sha256": expected_source_sha256, "provider_calls": len(ordinals)}
    finally:
        if lock.is_file() and lock.read_bytes() == token: lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
