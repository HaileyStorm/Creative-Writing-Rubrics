"""Provider-free census of pinned Dryad Sol accepted requests and native leaves."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
MAX_BYTES = 32 * 1024 * 1024
VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
REPLACEMENTS = {4295, 4297, 4298, 4299, 4300, 4301, 4302, 4303, 4304, 4305}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value: Any) -> str:
    return sha(canonical(value))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def unique(rows: list[dict], key: str, label: str) -> dict:
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"Duplicate {label}")
    return result


class Inputs:
    def __init__(self, control: Path, campaign: Path, descriptor: dict):
        self.roots = {"control": control.resolve(), "campaign": campaign.resolve(),
                      "repository": REPOSITORY}
        for name, relative in descriptor["peer_roots"].items():
            path = (campaign.resolve().parent / relative).resolve()
            require(inside(path, campaign.resolve().parent) and path != campaign.resolve().parent,
                    "Peer input root escapes its supplied parent")
            self.roots[name] = path
        self.artifacts: dict[str, dict] = {}

    def path(self, root: str, relative: str) -> Path:
        path = (self.roots[root] / relative).resolve()
        require(inside(path, self.roots[root]) and path != self.roots[root],
                "Retained input path escapes its named root")
        return path

    def locate(self, path: Path) -> str:
        path = path.resolve()
        candidates = [(name, root) for name, root in self.roots.items()
                      if name not in {"control", "repository"} and inside(path, root)]
        require(bool(candidates), "Response or receipt lies outside the allowlisted empirical roots")
        name, root = max(candidates, key=lambda item: len(item[1].parts))
        return name + "/" + path.relative_to(root).as_posix()

    def read(self, path: Path, label: str, expected: str | None = None,
             expected_bytes: int | None = None, locator: str | None = None) -> bytes:
        try:
            require(path.stat().st_size <= MAX_BYTES, f"Retained input exceeds size bound: {label}")
            raw = path.read_bytes()
        except OSError as error:
            raise ValueError(f"Missing or unreadable retained input: {label}") from error
        actual = sha(raw)
        require(expected is None or actual == expected, f"Retained input hash differs: {label}")
        require(expected_bytes is None or len(raw) == expected_bytes,
                f"Retained input byte count differs: {label}")
        locator = locator or self.locate(path)
        self.artifacts[locator] = {"source_locator": locator, "source_sha256": actual,
                                   "source_bytes": len(raw)}
        return raw

    def json(self, path: Path, label: str, **pins: Any) -> dict:
        try:
            value = json.loads(self.read(path, label, **pins))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Malformed retained JSON: {label}") from error
        require(isinstance(value, dict), f"Retained JSON is not an object: {label}")
        return value


def source_class(ordinal: int, unknown_exit: bool) -> str:
    if ordinal <= 772:
        return "original_native_checkpoint"
    if ordinal == 773:
        return "owner_authorized_773_replacement"
    if ordinal <= 828:
        return "post773_native_continuation"
    if ordinal <= 1342:
        return "unknown_exit_retained_message" if unknown_exit else "parallel_native_completion"
    if unknown_exit:
        return "completed_with_unknown_exit_retained_message"
    if ordinal in REPLACEMENTS:
        return "owner_authorized_transport_replacement"
    return "selected_native_completion"


def native_binding(inputs: Inputs, response: dict, path: Path, commitment: dict,
                   request: dict, recoveries: dict, replacement: dict) -> tuple[str, dict]:
    ordinal = commitment["ordinal"]
    lineage = {"response_sha256": commitment["sha256"],
               "response_locator_sha256": digest(inputs.locate(path)),
               "retained_commitment_sha256": digest(commitment)}
    if ordinal <= 772:
        require(type(response.get("accepted_attempt")) is int, "Original accepted attempt identity differs")
        for key in ("prompt_sha256", "base_prompt_sha256", "effective_prompt_sha256"):
            require(key not in response or response[key] == request["prompt_sha256"],
                    "Original response prompt binding differs")
        artifact = response["provider"]["provider_artifacts"]["codex_events"]
        event_path = (path.parent.parent / artifact["path"]).resolve()
        require(inside(event_path, path.parent.parent), "Original event path escapes its own run")
        raw = inputs.read(event_path, "original native events", artifact["sha256"], artifact["bytes"])
        require(len(raw) <= 16 * 1024 * 1024, "Original native events exceed size bound")
        starts, completions = [], 0
        for line in raw.splitlines():
            require(len(line) <= 8 * 1024 * 1024, "Original native event line exceeds size bound")
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") == "thread.started":
                starts.append(event.get("thread_id"))
            if event.get("type") == "turn.completed":
                completions += 1
        require(len(starts) == completions == 1, "Original native thread/completion cardinality differs")
        thread = starts[0]
        lineage.update(identity_source="pinned_own_events", native_events_sha256=sha(raw),
                       accepted_attempt=response.get("accepted_attempt"))
    elif ordinal in recoveries:
        recovery, receipt_sha = recoveries[ordinal]
        message = recovery["native_files"]["message"]
        require(Path(message["path"]).resolve() == path and message["sha256"] == commitment["sha256"]
                and recovery["derived_response_sha256"] == commitment["sha256"]
                and recovery["process_success_proven"] is False,
                "Reconciliation does not bind this retained response")
        thread = recovery["thread_id"]
        lineage.update(identity_source="reconciliation", reconciliation_sha256=receipt_sha,
                       recovery_record_sha256=digest(recovery))
    else:
        replaced = ordinal == 773
        terminal_path = path.parent / ("replacement-terminal.json" if replaced else "terminal.json")
        terminal = replacement if replaced else inputs.json(terminal_path, "accepted terminal")
        require(terminal.get("original_ordinal" if replaced else "ordinal") == ordinal
                and terminal.get("response_sha256") == commitment["sha256"],
                "Accepted terminal request/response binding differs")
        accepted_states = ({"replacement_accepted_under_owner_allowance_assumption"} if replaced
                           else {"accepted", "completed", "completed_with_unknown_exit"})
        require(terminal.get("state") in accepted_states,
                "Retained terminal is not an accepted completion")
        require((terminal["state"] == "completed_with_unknown_exit")
                == (commitment["process_success_proven"] is False),
                "Unknown-exit commitment conflicts with terminal")
        thread = terminal.get("thread_id")
        start_path = path.parent / ("replacement-start.json" if replaced else "start.json")
        start_raw = inputs.read(start_path, "accepted attempt start", terminal.get("start_sha256"))
        start = json.loads(start_raw)
        require(start.get("ordinal") == ordinal, "Attempt start ordinal differs")
        for provenance in (start, start.get("payload", {})):
            for key in ("prompt_sha256", "schema_sha256"):
                require(key not in provenance or provenance[key] == request[key], "Attempt start input pin differs")
        lineage.update(identity_source="replacement_terminal" if replaced else "ordinary_terminal",
                       terminal_sha256=inputs.artifacts[inputs.locate(terminal_path)]["source_sha256"],
                       retained_terminal_state=terminal["state"], attempt_start_sha256=sha(start_raw),
                       retained_attempt=start.get("attempt"), retained_logical_attempt=start.get("logical_attempt"),
                       identity_evidence=terminal.get("identity_evidence"),
                       provider_attested=terminal.get("provider_attested"))
    require(isinstance(thread, str) and bool(thread), "Accepted native thread identity is absent")
    return thread, lineage


def build_census(control_root: Path, sol_campaign_root: Path, descriptor: dict) -> tuple[dict, dict]:
    inputs = Inputs(control_root, sol_campaign_root, descriptor)
    data, sources = {}, []
    for name, spec in descriptor["inputs"].items():
        path = inputs.path(spec["root"], spec["path"])
        locator = spec["root"] + "/" + spec["path"]
        raw = inputs.read(path, name, spec["sha256"], locator=locator)
        if spec.get("kind") != "code_pin":
            data[name] = json.loads(raw)
        sources.append({"id": name, **inputs.artifacts[locator],
                        "disposition": "retained_code_not_executed" if spec.get("kind") == "code_pin"
                        else "verified_retained_input"})
    replay, manifest, schedule, plan = (data[name] for name in ("replay", "manifest", "schedule", "plan"))
    freeze = data["validation"]["freeze"]["sol_collection"]
    specs, expected = descriptor["inputs"], descriptor["expected"]
    for field, name in (("campaign_manifest_sha256", "manifest"), ("collection_result_sha256", "result")):
        require(replay[field] == freeze[field] == specs[name]["sha256"], "Collection source pin differs")
    require(freeze["replay_receipt_sha256"] == specs["replay"]["sha256"], "Validation replay receipt pin differs")
    require(replay["composer_sha256"] == descriptor["retained_replay_composer_sha256"]
            and freeze["composer_sha256"] == specs["validation_reader"]["sha256"],
            "Retained composer or later validation reader pin differs")
    require(replay["provider_calls"] == 0 and replay["full_study_admitted"] is False,
            "Retained replay evidence scope differs")
    require(replay["collection_result"] == data["result"] and data["result"]["state"] == "collected"
            and data["result"]["failures"] == [], "Retained collection is incomplete")
    require(Path(manifest["plan_root"]).resolve() == inputs.roots["plan"]
            and manifest["original_plan_sha256"] == schedule["original_plan_sha256"] == specs["plan"]["sha256"]
            and manifest["selected_schedule_sha256"] == specs["schedule"]["sha256"],
            "Original plan or selected schedule binding differs")
    require(Path(manifest["reconciliation_path"]).resolve() == inputs.path(
        specs["recovery_4486"]["root"], specs["recovery_4486"]["path"])
            and manifest["reconciliation_sha256"] == specs["recovery_4486"]["sha256"],
            "Campaign recovery receipt binding differs")
    for key in ("canonical_verdicts", "selected_requests", "accepted_native_thread_ids", "unknown_exit_commitments"):
        require(freeze[key] == replay[key], f"Validation retained collection field differs: {key}")
    accepted = replay["accepted_native_thread_ids"]
    require(len(accepted) == len(set(accepted)) == expected["requests"], "Accepted native identity inventory differs")
    require(replay["selected_requests"] == expected["requests"]
            and replay["canonical_verdicts"] == expected["leaves"], "Retained declared counts differ")
    requests = unique(plan["requests"], "ordinal", "original plan ordinal")
    passes = unique(plan["passes"], "pass_id", "original pass")
    selected = unique(schedule["selected_passes"], "pass_id", "selected pass")
    rows = replay["endpoint_sol_rows"]
    require(len(unique(rows, "pass_id", "retained pass")) == len(selected) == expected["passes"],
            "Selected retained pass inventory differs")
    require([row["pass_id"] for row in rows] == list(selected), "Selected retained pass order differs")
    recoveries = {}
    for name in ("recovery_1328", "recovery_4486"):
        for recovery in data[name]["recoveries"]:
            ordinal = recovery["ordinal"]
            require(ordinal not in recoveries, "Duplicate reconciliation ordinal")
            recoveries[ordinal] = (recovery, specs[name]["sha256"])
    require(len(recoveries) == expected["reconciliation"], "Reconciliation inventory differs")
    slots, seen_ordinals, seen_threads, committed_unknown = [], [], [], []
    for row in rows:
        pass_id = row["pass_id"]
        chosen, original = selected[pass_id], passes[pass_id]
        require(row["partition"] == chosen["partition"] == original["partition"]
                and chosen["logical_sample_id"] == original["logical_sample_id"],
                "Selected pass identity/partition differs")
        commitments = row["request_commitments"]
        ordinals = [item["ordinal"] for item in commitments]
        require(ordinals == chosen["request_ordinals"] and len(ordinals) == len(set(ordinals)),
                "Duplicate or reordered selected request ordinal")
        projected = [{"question_id": value["question_id"], "verdict": value["verdict"]}
                     for value in row["canonical_verdicts"]]
        question_order = [qid for ordinal in ordinals for qid in requests[ordinal]["question_ids"]]
        require([value["question_id"] for value in projected] == question_order == schedule["question_ids"]
                and len(question_order) == len(set(question_order)) == chosen["leaves"],
                "Missing, duplicate or reordered retained leaf")
        require(all(value["verdict"] in VERDICTS for value in projected), "Retained leaf verdict differs")
        source_path = inputs.path("plan", original["input_path"])
        inputs.read(source_path, "story source", original["source_sha256"], original["source_bytes"])
        offset = 0
        for packet_index, commitment in enumerate(commitments):
            ordinal = commitment["ordinal"]
            request = requests[ordinal]
            require(request["pass_id"] == pass_id and request["logical_sample_id"] == chosen["logical_sample_id"]
                    and request["batch_number"] == packet_index + 1, "Planned packet/pass binding differs")
            require(ordinal not in seen_ordinals, "Duplicate accepted request ordinal")
            seen_ordinals.append(ordinal)
            for kind in ("prompt", "schema"):
                inputs.read(inputs.path("plan", request[kind + "_path"]), f"packet {kind}",
                            request[kind + "_sha256"], request[kind + "_bytes"])
            response_path = Path(commitment["path"]).resolve()
            response = inputs.json(response_path, "retained packet response", expected=commitment["sha256"])
            raw_verdicts = response.get("normalized_verdicts" if ordinal <= 772 else "verdicts")
            require(isinstance(raw_verdicts, list), "Retained response verdicts are absent")
            verdicts = [{"question_id": value["question_id"], "verdict": value["verdict"]} for value in raw_verdicts]
            require([value["question_id"] for value in verdicts] == request["question_ids"]
                    and verdicts == projected[offset:offset + len(verdicts)],
                    "Raw packet and retained leaf rows differ")
            offset += len(verdicts)
            unknown = commitment["process_success_proven"] is False
            require(not unknown or commitment["completion_class"] == "completed_with_unknown_exit",
                    "Unknown-exit completion classification differs")
            require(commitment["source_class"] == source_class(ordinal, unknown), "Retained source lineage class differs")
            if unknown:
                committed_unknown.append(commitment)
            thread, lineage = native_binding(inputs, response, response_path, commitment, request,
                                             recoveries, data["replacement"])
            require(thread in accepted and thread not in seen_threads, "Wrong or duplicate accepted native thread")
            seen_threads.append(thread)
            slot_id = digest(["dryad", "sol", specs["plan"]["sha256"], ordinal, chosen["logical_sample_id"]])
            leaves = [{"question_id": value["question_id"], "packet_leaf_index": index + 1,
                       "leaf_slot_sha256": digest([slot_id, value["question_id"]]),
                       "native_verdict_sha256": digest(value)} for index, value in enumerate(verdicts)]
            slots.append({"cohort": "dryad", "endpoint": "sol", "ordinal": ordinal,
                          "slot_sha256": slot_id, "logical_sample_sha256": digest(chosen["logical_sample_id"]),
                          "pass_sha256": digest(pass_id), "partition": row["partition"],
                          "batch_number": request["batch_number"], "source_sha256": original["source_sha256"],
                          "prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"],
                          "question_ids_sha256": digest(request["question_ids"]), "question_count": len(leaves),
                          "native_thread_sha256": sha(thread.encode("utf-8")),
                          "normalized_native_verdicts_sha256": digest(verdicts), "leaves": leaves,
                          "disposition": "accepted_retained_native", "no_resend": True,
                          "source_class": commitment["source_class"],
                          "completion_class": commitment["completion_class"],
                          "process_success_proven": commitment["process_success_proven"],
                          "attempt_lineage": lineage, "attempt_lineage_sha256": digest(lineage)})
    require(seen_ordinals == schedule["selected_request_ordinals"] and len(seen_ordinals) == expected["requests"],
            "Selected accepted request inventory/order differs")
    require(set(seen_threads) == set(accepted), "Accepted native identity inventory is not fully joined")
    require(committed_unknown == replay["unknown_exit_commitments"]
            and len(committed_unknown) == expected["unknown_exit"], "Unknown-exit retained inventory differs")
    require(set(recoveries) <= set(seen_ordinals), "Reconciliation belongs to an unselected request")
    identity_sources = Counter(slot["attempt_lineage"]["identity_source"] for slot in slots)
    for actual, declared in (("pinned_own_events", "original_events"), ("replacement_terminal", "replacement"),
                             ("ordinary_terminal", "ordinary_terminal"), ("reconciliation", "reconciliation")):
        require(identity_sources[actual] == expected[declared], "Accepted native receipt source counts differ")
    leaf_count = sum(slot["question_count"] for slot in slots)
    require(leaf_count == expected["leaves"], "Observed native leaf count differs")
    a = data["census_a"]
    prior = a["totals"]["observed_ttcw_pron_dryad_native_verdict_rows"]
    require(prior == expected["census_a_observed_leaves"], "Census A observed denominator differs")
    a_sol = next(item for item in a["sources"] if item["id"] == "dryad-sol")
    require(a_sol["source_sha256"] == specs["validation"]["sha256"]
            and not a_sol["observed"].get("normalized_native_verdict_rows"), "Census A already counts these Sol rows")
    artifacts = sorted(inputs.artifacts.values(), key=lambda value: value["source_locator"])
    report = {"schema_version": 1, "status": "partial_census", "evidence_class": descriptor["scope"],
              "provider_calls_made": 0, "new_provider_votes": 0, "descriptor_sha256": digest(descriptor),
              "implementation_sha256": sha(Path(__file__).read_bytes()), "sources": sources,
              "declared": {"retained_sol_verdicts": replay["canonical_verdicts"],
                           "retained_sol_requests": replay["selected_requests"]},
              "observed": {"passes": len(rows), "accepted_request_native_joins": len(slots),
                           "unique_native_threads": len(seen_threads), "normalized_native_verdict_rows": leaf_count,
                           "unknown_exit_requests": len(committed_unknown), "identity_sources": dict(identity_sources),
                           "source_classes": dict(Counter(slot["source_class"] for slot in slots)),
                           "qualification_failures_retained": len(replay["qualification_failures"]),
                           "verified_artifact_count": len(artifacts),
                           "verified_artifact_bytes": sum(item["source_bytes"] for item in artifacts)},
              "totals": {"census_a_observed_verdict_rows": prior, "additional_observed_retained_sol_rows": leaf_count,
                         "observed_ttcw_pron_dryad_native_verdict_rows_after_join": prior + leaf_count,
                         "retained_declared_ttcw_pron_dryad_native_verdicts": a["totals"][
                             "retained_declared_ttcw_pron_dryad_native_verdicts"]},
              "provenance": {"retained_replay_composer_sha256": replay["composer_sha256"],
                             "later_validation_reader_sha256": freeze["composer_sha256"],
                             "question_payload_sha256": plan["runtime"]["question_payload_sha256"],
                             "compiled_bundle_sha256": plan["runtime"]["compiled_bundle_sha256"],
                             "native_request_join_sha256": digest(slots),
                             "verified_artifact_index_sha256": digest(artifacts)},
              "privacy": "Public report contains aggregates, hashes and named source locators only; private ledger remains task-local.",
              "unresolved": descriptor["unresolved"]}
    ledger = {"schema_version": 1, "scope": descriptor["scope"], "report_sha256": digest(report),
              "private_task_local_only": True, "slots": slots, "artifacts": artifacts}
    return report, ledger


def output_preflight(output: Path, inputs: Inputs) -> None:
    output = output.resolve()
    require(not output.exists(), "Census output must be a fresh nonexistent directory")
    require(not inside(output, REPOSITORY), "Census output must remain outside the repository")
    for name, root in inputs.roots.items():
        if name not in {"control", "repository"}:
            require(not inside(output, root) and not inside(root, output), "Census output overlaps retained evidence")
    protected = inputs.roots["control"] / "dryad-sol-validation-r28"
    require(not inside(output, protected) and not inside(protected, output), "Census output overlaps validation evidence")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--sol-campaign-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    descriptor = json.loads((HERE / "source-descriptor.json").read_bytes())
    try:
        output_preflight(args.output_root, Inputs(args.control_root, args.sol_campaign_root, descriptor))
        report, ledger = build_census(args.control_root, args.sol_campaign_root, descriptor)
        if not args.dry_run:
            args.output_root.mkdir(parents=True, exist_ok=False)
            for name, value in (("census.json", report), ("private-slots.json", ledger)):
                with (args.output_root / name).open("xb") as handle:
                    handle.write(canonical(value) + b"\n")
        print(json.dumps({"dry_run": args.dry_run, "report_sha256": digest(report),
                          "private_ledger_sha256": digest(ledger), "observed": report["observed"],
                          "totals": report["totals"], "status": report["status"]}, sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, f"Census B validation failed: {error}\n")


if __name__ == "__main__":
    main()
