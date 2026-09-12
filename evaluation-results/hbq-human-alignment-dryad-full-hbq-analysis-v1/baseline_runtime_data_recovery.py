"""Offline native recovery after historical runtime data moved to snapshots."""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
PARTIAL = HERE / "baseline_grok_standing_v6_partial_successor.py"
PARTIAL_SHA = "d2b669a5a06d8d72edd65159894069805e6c5b31d22f08df1b9e2ad3b0ce3a70"
ACCEPTED_DESCENDANTS = [266, *range(272, 279)]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path, expected: str) -> ModuleType:
    raw = path.read_bytes()
    need(sha(raw) == expected, "recovery source pin differs")
    module = ModuleType("_data_recovery_" + path.stem)
    module.__file__ = str(path.resolve())
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(module.__name__, None)
    need(path.read_bytes() == raw, "recovery source changed during load")
    return module


def read(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    need(sha(raw) == expected, "recovery evidence pin differs")
    value = json.loads(raw)
    need(isinstance(value, dict), "recovery evidence object required")
    return value


def build_context(*, continuation_root: Path, expected_manifest_sha256: str,
                  snapshot_manifest_path: Path, expected_snapshot_manifest_sha256: str,
                  expected_loader_sha256: str, expected_prefix_adapter_sha256: str) -> Any:
    partial = load(PARTIAL, PARTIAL_SHA)
    manifest, manifest_raw = partial._manifest(continuation_root, expected_manifest_sha256)
    base = partial._base()
    candidate, _ = base._candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
    e33 = base._load(base.E33, base.E33_SHA, "historical local controller")
    descriptor = manifest["prefix"]["descriptor"]
    local_manifest, _ = e33._manifest(Path(descriptor["root"]), descriptor["manifest_sha256"])
    _, parent, _, _, plan_root, requests, old_partial = e33._source_guard(local_manifest)
    epoch, _ = parent._load_epoch(Path(local_manifest["successor_root"]), local_manifest["inner_epoch"]["sha256"])
    loader = load(HERE / "baseline_runtime_data_snapshot.py", expected_loader_sha256)
    runtime = loader.load_runtime_from_epoch(epoch, snapshot_manifest_path=snapshot_manifest_path,
                                            expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256)
    adapter = load(HERE / "baseline_runtime_data_prefix.py", expected_prefix_adapter_sha256)
    prefix = adapter.verify_local_continuation_with_runtime(
        continuation_root=Path(descriptor["root"]), expected_manifest_sha256=descriptor["manifest_sha256"],
        expected_controller_sha256=descriptor["controller_sha256"], runtime=runtime)
    need(prefix["source"] == manifest["prefix"]["source"] and prefix["protected_paths"] == manifest["prefix"]["protected_paths"],
         "recovery prefix ownership changed")
    identities = list(e33._identity(old_partial["all_protected_native_identities"]))
    need(len(identities) == 259, "recovery protected prefix count differs")
    peers = partial._partial(Path(manifest["partial_reconciliation"]["path"]), manifest["partial_reconciliation"]["sha256"])
    need(manifest["terminal_source_roots"] == partial._source_roots(peers), "recovery peer roots differ")
    replayed, _ = partial._replayed(continuation_root, manifest, manifest_raw)
    need(sorted(replayed) == ACCEPTED_DESCENDANTS, "recovery descendant boundary differs")
    broker = candidate.Broker(Path(manifest["queue"]["path"]))
    passes = parent._pass_index(parent._plan(plan_root, epoch["plan_sha256"])[0])
    records = []
    terminals = [(item["ordinal"], Path(item["terminal"]["path"])) for item in peers["native_peers"]]
    terminals.extend((ordinal, partial._attempt_path(continuation_root, ordinal, "terminal.json")) for ordinal in ACCEPTED_DESCENDANTS)
    for ordinal, path in sorted(terminals):
        terminal_raw = path.read_bytes()
        terminal = json.loads(terminal_raw)
        identity, verdicts, envelope = base._semantic_replay_terminal(
            candidate=candidate, broker=broker, terminal=terminal, terminal_path=path, parent=parent,
            runtime=runtime, plan_root=plan_root, passes=passes, requests=requests)
        need(partial._identity_is_new(identity, identities), "recovery prior native identity collision")
        identities.append(identity)
        records.append({"ordinal": ordinal, "terminal": {"path": str(path), "sha256": sha(terminal_raw)},
                        "native_identity": identity, "verdicts": verdicts, "envelope": envelope})
    need(len(identities) == 276, "recovery prior native count differs")
    runtime.verify()
    return SimpleNamespace(partial=partial, base=base, candidate=candidate, broker=broker, parent=parent,
                           runtime=runtime, manifest=manifest, manifest_raw=manifest_raw, root=continuation_root,
                           plan_root=plan_root, passes=passes, requests=requests, identities=identities,
                           prefix=prefix, records=records, snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
                           loader_sha256=expected_loader_sha256, prefix_adapter_sha256=expected_prefix_adapter_sha256)


def recover_279(*, context: Any, expected_terminal_sha256: str, review_path: Path,
                expected_review_sha256: str) -> dict[str, Any]:
    """Reparse the retained native envelope; the original terminal stays ambiguous."""
    context.runtime.verify()
    need(len(context.identities) == 276, "279 recovery prior boundary differs")
    path = context.partial._attempt_path(context.root, 279, "terminal.json")
    terminal = read(path, expected_terminal_sha256)
    outcome = terminal.get("broker_outcome")
    result = terminal.get("candidate_result")
    need(terminal.get("ordinal") == 279 and terminal.get("state") == "ambiguous"
         and terminal.get("error_type") == "ValueError"
         and terminal.get("error_source") == "dispatch_standing_v6_wave:cell"
         and "before_contact_error" not in terminal and isinstance(outcome, Mapping)
         and outcome.get("state") == "completed" and isinstance(result, Mapping)
         and outcome.get("result") == result, "279 completed outcome is not recoverable")
    start_path = context.partial._attempt_path(context.root, 279, "attempt-start.json")
    start = read(start_path, terminal["attempt_start_sha256"])
    authorization_path = context.root / "controller-authorizations/request-0279.json"
    authorization_raw = authorization_path.read_bytes()
    authorization = json.loads(authorization_raw)
    review = read(review_path, expected_review_sha256)
    manifest_sha = sha(context.manifest_raw)
    need(authorization == {
        "candidate_manifest_sha256": context.manifest["candidate"]["manifest_sha256"],
        "gate_sha256": review.get("gate_sha256"), "manifest_sha256": manifest_sha,
        "operational_wave_cap": 1, "ordinal": 279, "review_sha256": expected_review_sha256,
        "route_sha256": review.get("route_sha256")}, "279 authorization binding differs")
    need(review.get("controller_sha256") == PARTIAL_SHA and review.get("manifest_sha256") == manifest_sha
         and review.get("first_ordinal") == 279 and review.get("operational_wave_cap") == 1
         and review.get("decision") == "approved_dryad_grok_standing_v6_partial_successor_wave"
         and review.get("candidate_manifest_sha256") == context.manifest["candidate"]["manifest_sha256"],
         "279 historical review differs")
    row = context.requests[279]
    source = context.parent._source_for_pass(context.plan_root, context.passes[row["pass_id"]])
    prompt, schema_path, ids = context.parent._request_payload(context.plan_root, row)
    schema = json.loads(schema_path.read_bytes())
    need(start.get("ordinal") == 279 and start.get("wave") == {"ordinals": [279], "size": 1, "slot": 0, "start": 279}
         and start.get("prompt_sha256") == row["prompt_sha256"] and start.get("schema_sha256") == row["schema_sha256"]
         and start.get("question_ids") == ids == row["question_ids"] and start.get("source_sha256") == source["sha256"]
         and start.get("route_sha256") == review.get("route_sha256") and start.get("gate_sha256") == review.get("gate_sha256")
         and start.get("candidate_manifest_sha256") == context.manifest["candidate"]["manifest_sha256"],
         "279 original request binding differs")
    route, session_id = review.get("route"), terminal.get("session_id")
    need(isinstance(route, Mapping) and isinstance(session_id, str)
         and context.base._sha(context.base._canon(dict(route))) == review.get("route_sha256"), "279 route differs")
    envelope_descriptor = result.get("native_envelope_artifact")
    need(isinstance(envelope_descriptor, Mapping), "279 envelope descriptor missing")
    envelope = context.broker.read_grok_native_envelope(dict(envelope_descriptor))
    need(sha(envelope) == envelope_descriptor.get("sha256") and len(envelope) == envelope_descriptor.get("byte_length"),
         "279 native envelope differs")
    parsed = context.broker._parse_grok_exec_envelope(
        context.base._canon({"control": {"version": 1, "state": "completed"}, "result": dict(result)}),
        {**dict(route), "output_schema": schema, "nonvisual_max_turns": 1}, {"prompt": prompt}, expected_session_id=session_id)
    adapter = importlib.import_module(context.candidate.__package__ + ".adapters.grok_exec")
    output, raw_identity, _usage = adapter._parse_grok_envelope(
        envelope, model=route["model"], reported_model=route["reported_model"], session_id=session_id,
        schema=schema, max_turns=1, exact_turns=True)
    identity = context.base._native_identity(raw_identity, "279 recovered native identity")
    need(parsed.state == "completed" and parsed.result == result and output == result.get("output")
         and identity == terminal.get("native_identity") and context.partial._identity_is_new(identity, context.identities),
         "279 native result or identity differs")
    verdicts = context.runtime.runner._normalize_batch(
        output, expected_ids=ids, artifact_id=source["opaque_story_id"], bundle_id="prose.short_story",
        judge_id="grok:grok-4.6", run_id="standing-v6/279", artifact_text=source["story_text"], context_texts=[],
        normalization_policy=context.runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
    need(len(verdicts) == 8 and [item["question_id"] for item in verdicts] == ids, "279 verdict coverage differs")
    context.runtime.verify()
    need(sha(path.read_bytes()) == expected_terminal_sha256, "279 source changed during recovery")
    return {"schema_version": 1, "evidence_class": "native_envelope_recovery_after_runtime_data_drift_v1",
            "ordinal": 279, "state": "verified_pending_independent_adoption", "original_terminal_state": "ambiguous",
            "original_terminal": {"path": str(path), "sha256": expected_terminal_sha256},
            "attempt_start": {"path": str(start_path), "sha256": terminal["attempt_start_sha256"]},
            "authorization": {"path": str(authorization_path), "sha256": sha(authorization_raw)},
            "historical_review": {"path": str(review_path), "sha256": expected_review_sha256},
            "native_envelope": dict(envelope_descriptor), "native_identity": identity, "question_ids": ids, "verdicts": verdicts,
            "prior_native_count": len(context.identities), "prior_logical_count": 278,
            "after_adoption_native_count": 277, "after_adoption_logical_count": 279,
            "local_recovery_ordinals": [70, 254], "native_identity_unique": True,
            "runtime_provenance": context.runtime.provenance, "snapshot_manifest_sha256": context.snapshot_manifest_sha256,
            "loader_sha256": context.loader_sha256, "prefix_adapter_sha256": context.prefix_adapter_sha256,
            "recovery_source_sha256": sha(Path(__file__).read_bytes()), "source_controller_sha256": PARTIAL_SHA,
            "provider_calls_made": 0, "original_completed_provider_contacts": 1,
            "automatic_resend_authorized": False, "original_evidence_modified": False}
