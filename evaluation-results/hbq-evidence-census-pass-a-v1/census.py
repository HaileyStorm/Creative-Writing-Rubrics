"""Provider-free, metadata-only projection of explicitly retained census A inputs."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ACCEPTED_STATES = {"accepted", "accepted_native_retry", "accepted_native_session_local_recovery",
                   "accepted_local_projection"}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def at(value: Any, path: str, default: Any = None) -> Any:
    for part in path.split(".") if path else []:
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def counts(value: dict, names: tuple[str, ...]) -> dict:
    return {name: value[name] for name in names
            if type(value.get(name)) is int and value[name] >= 0}


def pin(value: Any) -> str | None:
    if isinstance(value, str) and len(value) == 64:
        try:
            int(value, 16)
            return value.lower()
        except ValueError:
            pass
    return None


def native_identity(record: dict) -> str | None:
    native = record.get("native_identity", record)
    request = native.get("request_id_hash", native.get("request_id_sha256"))
    session = native.get("session_id_hash", native.get("session_id_sha256",
                         native.get("thread_id")))
    if request or session:
        return digest({"request": request, "session": session})
    return None


def plan_projection(data: dict, source: dict, slots: list) -> dict:
    passes, requests = data.get("passes", []), data.get("requests", [])
    result = {"declared": counts(data.get("counts", {}), (
        "stories", "logical_requests_per_endpoint", "criterion_verdicts_per_endpoint",
        "questions_per_story")), "observed": {"passes": len(passes),
        "requests": len(requests), "packet_question_memberships": sum(
            len(row.get("question_ids", [])) for row in requests)},
        "pins": {"question_payload_sha256": pin(at(data, "runtime.question_payload_sha256")),
                 "compiled_bundle_sha256": pin(at(data, "runtime.compiled_bundle_sha256")),
                 "context_sha256": pin(at(data, "context.sha256")),
                 "response_schema_sha256": pin(at(data, "response_schema.sha256"))}}
    for row in requests:
        slots.append({"source_id": source["id"], "kind": "planned_packet",
                      "ordinal": row.get("ordinal"),
                      "planned_slot_sha256": digest([source["cohort"], row.get("logical_sample_id"),
                                                     row.get("pass_id"), row.get("ordinal")]),
                      "logical_sample_sha256": digest(row.get("logical_sample_id")),
                      "pass_sha256": digest(row.get("pass_id")),
                      "prompt_sha256": pin(row.get("prompt_sha256")),
                      "schema_sha256": pin(row.get("schema_sha256")),
                      "question_ids_sha256": digest(row.get("question_ids", [])),
                      "question_count": len(row.get("question_ids", []))})
    return result


def replay_projection(data: dict, source: dict, plan: dict | None, slots: list) -> dict:
    records = list(data.get("records", []))
    for key in ("original_accepted_records", "second_attempt_records", "local_native_session_records"):
        records.extend(data.get(key, []))
    grouped: dict[Any, list] = {}
    for row in records:
        grouped.setdefault(row.get("ordinal"), []).append(row)
    planned = {row["ordinal"]: row for row in (plan or {}).get("requests", [])}
    nonresponses = {row["ordinal"]: row for row in data.get("declared_nonresponses", [])}
    unresolved = set(data.get("unresolved_ordinals", []))
    unique_native = set()
    state_counts: Counter = Counter()
    native_verdicts = 0
    conflicts = []
    for ordinal in sorted(set(planned) | set(grouped) | unresolved | set(nonresponses)):
        rows = grouped.get(ordinal, [])
        identities = {native_identity(row) for row in rows} - {None}
        unique_native.update(identities)
        accepted = [row for row in rows if row.get("state") in ACCEPTED_STATES]
        commitments = {(native_identity(row), row.get("normalized_verdicts_sha256"))
                       for row in accepted}
        disposition = "accepted" if accepted else "missing"
        if any(row.get("state") in {"accepted_native_session_local_recovery", "accepted_local_projection"}
               for row in accepted):
            disposition = "repaired"
        elif any(row.get("state") == "accepted_native_retry" for row in accepted):
            disposition = "accepted_retry"
        if len(commitments) > 1:
            disposition = "unresolved_identity_conflict"
            conflicts.append(ordinal)
        elif ordinal in nonresponses:
            disposition = "declared_nonresponse"
        elif ordinal in unresolved:
            disposition = "unresolved_reserved"
        if disposition in {"accepted", "accepted_retry", "repaired"}:
            native_verdicts += accepted[0].get("verdict_count", accepted[0].get("normalized_verdict_count", 0))
        state_counts[disposition] += 1
        request = planned.get(ordinal, {})
        slots.append({"source_id": source["id"], "kind": "native_packet",
                      "ordinal": ordinal, "endpoint": source["endpoint"],
                      "slot_sha256": digest([source["cohort"], source["endpoint"],
                                             request.get("logical_sample_id"), ordinal]),
                      "native_identity_sha256": sorted(identities), "disposition": disposition,
                      "record_count": len(rows), "replayed_duplicate_records": max(0, len(accepted) - len(commitments)),
                      "no_resend": disposition in {"unresolved_reserved", "declared_nonresponse", "unresolved_identity_conflict"},
                      "missing_question_count": nonresponses.get(ordinal, {}).get("missing_verdict_count", 0),
                      "normalized_verdicts_sha256": sorted({p for row in rows
                          if (p := pin(row.get("normalized_verdicts_sha256")))})})
    verdict_rows = data.get("score_ready_verdict_rows", [])
    result = {"declared": counts(data, ("accepted_count", "accepted_verdict_count", "logical_packet_count",
        "logical_request_count", "planned_verdict_count", "missing_verdict_count",
        "physical_contacted_attempt_count", "contact_admission_count")),
        "observed": {"raw_packet_records": len(records), "unique_native_identities": len(unique_native),
                     "slot_dispositions": dict(state_counts), "accepted_packet_verdicts": native_verdicts,
                     "retained_record_states": dict(Counter(row.get("state", "absent") for row in records)),
                     "normalized_native_verdict_rows": sum(len(row.get("verdicts", [])) for row in verdict_rows)},
        "pins": {"plan_sha256": pin(data.get("plan_sha256")),
                 "score_ready_verdict_rows_sha256": pin(data.get("score_ready_verdict_rows_sha256"))},
        "unresolved": ["Physical contacts and complete attempt/recovery lineage are not independently joined."]}
    if plan is None:
        result["unresolved"].append("Retained plan absent; no planned-slot completeness claim.")
    if conflicts:
        result["unresolved"].append("Multiple accepted identity/output commitments in a logical slot.")
    return result


def dryad_projection(data: dict, source: dict, slots: list) -> dict:
    if source["endpoint"] == "sol":
        collection = at(data, "freeze.sol_collection", {})
        for thread in collection.get("accepted_native_thread_ids", []):
            slots.append({"source_id": source["id"], "kind": "native_identity",
                          "native_identity_sha256": digest({"thread": thread})})
        return {"declared": counts(collection, ("canonical_verdicts", "selected_requests")),
                "observed": {"accepted_native_thread_ids": len(collection.get("accepted_native_thread_ids", [])),
                             "unique_native_thread_ids": len(set(collection.get("accepted_native_thread_ids", []))),
                             "unknown_exit_commitments": len(collection.get("unknown_exit_commitments", []))},
                "unresolved": ["Sol verdict rows and planned-request/attempt joins are absent from this projection."]}
    collection = at(data, "freeze.admission.record.collection_record", {})
    for field, disposition in (("native_identities", "accepted"),
                               ("historical_excluded_native_identities", "historical_excluded")):
        for row in collection.get(field, []):
            slots.append({"source_id": source["id"], "kind": "native_identity",
                          "native_identity_sha256": native_identity(row), "disposition": disposition})
    rows = collection.get("normalized_verdict_rows", [])
    return {"declared": counts(collection.get("counts", {}), ("criterion_verdicts", "logical_requests",
              "native_requests", "stories", "local_recovered_requests", "parallel_local_recovered_requests")),
            "observed": {"normalized_native_verdict_rows": len(rows),
                         "native_identities": len(collection.get("native_identities", [])),
                         "historical_excluded_native_identities": len(collection.get("historical_excluded_native_identities", [])),
                         "story_pass_pairs": len({digest([r.get("opaque_story_id"), r.get("pass_id")]) for r in rows})},
            "unresolved": ["Native identity-to-packet/leaf and complete recovery chain joins remain unresolved.",
                           "Historical prefixes are ancestors of the consolidated bank, not additional votes."]}


def lamp_projection(data: dict, source: dict, slots: list) -> dict:
    kind = source["kind"]
    if kind == "lamp_source":
        selected = data.get("selected", [])
        return {"declared": counts(data, ("triplets", "paragraph_variants")),
                "observed": {"selected_groups": len(selected), "selected_variants": sum(
                    len(row.get("variants", [])) for row in selected)},
                "unresolved": ["Rights/form, work/author overlap and source-to-pass joins remain unresolved."]}
    passes = data.get("passes", [])
    for row in passes:
        slots.append({"source_id": source["id"], "kind": "planned_pass",
                      "slot_sha256": digest([source["id"], row.get("sample_id")]),
                      "sample_sha256": digest(row.get("sample_id")),
                      "group_sha256": digest(row.get("group_id_local_only")),
                      "variant_sha256": digest(row.get("variant_id_local_only")),
                      "repeat_index": row.get("repeat_index_local_only"),
                      "source_sha256": pin(row.get("source_sha256"))})
    receipts = data.get("native_receipts", data.get("endpoint_receipts", {}))
    projected = {}
    for endpoint, receipt in receipts.items():
        projected[endpoint] = {"declared": counts(receipt, ("accepted", "planned", "accepted_count",
            "planned_ordinals", "attempted_ordinals")), "observed": {name: len(receipt[name])
            for name in ("nonaccepted", "unattempted", "ambiguous_ordinals", "declared_missing",
                         "local_reconciliations") if isinstance(receipt.get(name), list)}}
        for field in ("nonaccepted", "ambiguous_ordinals", "declared_missing"):
            for row in receipt.get(field, []):
                ordinal = row.get("ordinal") if isinstance(row, dict) else row
                slots.append({"source_id": source["id"], "kind": "reserved_missing_packet",
                              "endpoint": endpoint, "ordinal": ordinal,
                              "slot_sha256": digest([source["id"], endpoint, ordinal]),
                              "disposition": "unresolved_reserved", "no_resend": True})
    return {"observed": {"planned_pass_rows": len(passes),
                         "planned_endpoint_pass_sets": len(passes) * len(receipts)}, "endpoint_receipts": projected,
            "unresolved": ["Native packets/leaves, same-contract repeat, repaired and ambiguous attempt joins remain unresolved.",
                           "Scores and preference labels are not read or exported; pass rows do not prove accepted votes."]}


def build_census(control_root: Path, descriptor: dict) -> tuple[dict, list]:
    if not control_root.is_dir():
        raise FileNotFoundError("Retained control root is unavailable")
    sources, slots, loaded = [], [], {}
    for source in descriptor["sources"]:
        relative = Path(source["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Descriptor source must be relative to control root")
        path = (control_root / relative).resolve()
        if not path.is_relative_to(control_root.resolve()):
            raise ValueError("Descriptor source escapes control root")
        report = {"id": source["id"], "cohort": source["cohort"], "kind": source["kind"],
                  "source_locator": source["path"], "disposition": "absent"}
        if not path.is_file():
            report["unresolved"] = ["Allowlisted retained source is absent; no zero-count inference."]
            sources.append(report)
            continue
        payload = path.read_bytes()
        report.update(source_bytes=len(payload), source_sha256=hashlib.sha256(payload).hexdigest())
        if source["kind"] == "code_pin":
            report["disposition"] = "retained_code_not_executed"
            sources.append(report)
            continue
        try:
            data = json.loads(payload.decode("utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
        except (ValueError, UnicodeError):
            report["disposition"] = "unreadable"
            report["unresolved"] = ["Retained source is not a readable JSON object."]
            sources.append(report)
            continue
        loaded[source["id"]] = data
        report["disposition"] = "projected_partial"
        if source["kind"] == "plan":
            report.update(plan_projection(data, source, slots))
        elif source["kind"] == "replay":
            report.update(replay_projection(data, source, loaded.get(source["plan_id"]), slots))
            expected_pin = next((r.get("source_sha256") for r in sources if r["id"] == source["plan_id"]), None)
            report["plan_pin_matches_retained_bytes"] = expected_pin is not None and expected_pin == data.get("plan_sha256")
            if not report["plan_pin_matches_retained_bytes"]:
                report["unresolved"].append("Plan pin absent or mismatched; ordinal joins are provisional.")
        elif source["kind"] == "dryad":
            report.update(dryad_projection(data, source, slots))
        elif source["kind"].startswith("lamp_"):
            report.update(lamp_projection(data, source, slots))
        elif source["kind"] == "derived_prediction":
            report["declared_native_counts"] = counts(data.get("native_verdict_count_by_endpoint", {}), ("grok", "sol"))
            report["new_native_votes"] = 0
            report["unresolved"] = ["Derived predictions, including CANNOT_ASSESS fill, are not native votes."]
        sources.append(report)
    observed = sum(s.get("observed", {}).get("normalized_native_verdict_rows", 0) for s in sources)
    declared = sum(s.get("declared", {}).get("accepted_verdict_count",
                   s.get("declared", {}).get("criterion_verdicts", s.get("declared", {}).get("canonical_verdicts", 0)))
                   for s in sources if s["kind"] in {"replay", "dryad"})
    lamp_sources = [s for s in sources if s["kind"] == "lamp_source"]
    report = {"schema_version": 1, "evidence_class": "local_retained_metadata_projection",
              "status": "partial_census", "provider_calls_made": 0,
              "descriptor_sha256": digest(descriptor), "sources": sources,
              "totals": {"observed_ttcw_pron_dryad_native_verdict_rows": observed,
                         "retained_declared_ttcw_pron_dryad_native_verdicts": declared,
                         "observed_lamp_source_groups": sum(s.get("observed", {}).get("selected_groups", 0) for s in lamp_sources),
                         "observed_lamp_source_variants": sum(s.get("observed", {}).get("selected_variants", 0) for s in lamp_sources),
                         "observed_lamp_pass_rows": sum(s.get("observed", {}).get("planned_pass_rows", 0) for s in sources),
                         "observed_lamp_planned_endpoint_pass_sets": sum(
                             s.get("observed", {}).get("planned_endpoint_pass_sets", 0) for s in sources)},
              "unresolved": descriptor["remaining_joins"],
              "privacy": "Private metadata export; opaque identity hashes do not authorize publication."}
    return report, slots


def write_census(control_root: Path, output_root: Path, descriptor: dict) -> dict:
    control_root = control_root.resolve()
    output_root = output_root.resolve()
    if output_root == control_root or control_root.is_relative_to(output_root):
        raise ValueError("Output root must not contain the evidence root")
    if output_root.exists():
        raise FileExistsError("Output root must be a fresh immutable descendant")
    report, slots = build_census(control_root, descriptor)
    output_root.mkdir(parents=True, exist_ok=False)
    for name, value in (("census.json", report), ("private-slots.json", slots)):
        with (output_root / name).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    descriptor = json.loads((HERE / "source-descriptor.json").read_text(encoding="utf-8"))
    result = write_census(args.control_root, args.output_root, descriptor)
    print(json.dumps({"status": result["status"], "totals": result["totals"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
