"""Provider-free retained Batch-3/5 LAMP request and leaf census."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return sha(canonical(value))


def retained_digest(value: object) -> str:
    return sha(canonical(value) + b"\n")


def inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


class Inputs:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.artifacts: dict[str, dict] = {}

    def path(self, locator: str) -> Path:
        path = (self.root / locator).resolve()
        require(inside(path, self.root) and path != self.root, "Source locator leaves retained LAMP root")
        return path

    def raw(self, locator: str, expected: str | None = None, size: int | None = None) -> bytes:
        path = self.path(locator)
        require(path.is_file(), f"Missing retained artifact: {locator}")
        require(path.stat().st_size <= 16 * 1024 * 1024, f"Oversized retained artifact: {locator}")
        raw = path.read_bytes()
        actual = sha(raw)
        require(expected is None or actual == expected, f"Source hash differs: {locator}")
        require(size is None or len(raw) == size, f"Source byte count differs: {locator}")
        receipt = {"source_locator": locator, "source_sha256": actual, "source_bytes": len(raw)}
        require(locator not in self.artifacts or self.artifacts[locator] == receipt,
                f"Artifact changed while reading: {locator}")
        self.artifacts[locator] = receipt
        return raw

    def read(self, locator: str, expected: str | None = None) -> dict:
        return json.loads(self.raw(locator, expected))


def validate_repeat_requests(main: dict, repeat: dict, main_sha: str, predictions_sha: str) -> None:
    require(repeat["main_plan_sha256"] == main_sha
            and repeat["blind_predictions_sha256"] == predictions_sha
            and repeat["exact_prompt_bytes_reused_from_main"] is True
            and repeat["repeat_identity_is_distinct_from_main"] is True,
            "Repeat parent or distinct-identity declaration differs")
    originals, identities = set(), set()
    for row in repeat["requests"]:
        original = row["original_ordinal"]
        require(isinstance(original, int) and 1 <= original <= len(main["requests"])
                and original not in originals, "Duplicate or absent repeat parent ordinal")
        originals.add(original)
        parent = main["requests"][original - 1]
        for key in ("sample_id", "source_sha256", "prompt_sha256", "schema_sha256", "question_ids",
                    "cohort", "group_id_local_only", "variant_id_local_only", "prompt_bytes", "schema_bytes"):
            require(row[key] == parent[key], f"Repeat parent {key} differs")
        identity = row["planned_repeat_id"]
        require(identity == f"batch35-repeat-1|main-ordinal-{original}" and identity not in identities,
                "Planned repeat identity differs or duplicates")
        identities.add(identity)
    require(repeat["logical_repeat_id_template"] == "batch35-repeat-1|{endpoint}|main-ordinal-{original_ordinal}",
            "Logical repeat identity template differs")


def wave_packets(inputs: Inputs, root: str, endpoint: str, starts: list[int], end: int,
                 manifest_sha: str, seen: set[int]) -> tuple[list[tuple[int, dict]], list[str], list[str]]:
    packets, wave_hashes, terminal_hashes = [], [], []
    for start in starts:
        base = f"{root}/waves/{endpoint}-wave-{start:04d}"
        result_raw = inputs.raw(base + ".result.json")
        result = json.loads(result_raw)
        intent = inputs.read(base + ".intent.json", result["intent_sha256"])
        numbers = list(range(start, min(start + 8, end + 1)))
        require(result["ordinals"] == numbers and [item["ordinal"] for item in result["terminals"]] == numbers
                and intent["endpoint"] == endpoint and intent["ordinals"] == numbers
                and intent["manifest_sha256"] == manifest_sha, "Wave intent/result binding differs")
        wave_hashes.append(sha(result_raw))
        for receipt in result["terminals"]:
            ordinal = receipt["ordinal"]
            require(ordinal not in seen, "Overlapping retained logical ordinal; replay is not another vote")
            seen.add(ordinal)
            require(isinstance(receipt["terminal_sha256"], str), "Missing terminal receipt is unresolved")
            packets.append((ordinal, dict(receipt, wave_result_sha256=sha(result_raw),
                                          wave_intent_sha256=result["intent_sha256"])))
            terminal_hashes.append(receipt["terminal_sha256"])
    return packets, wave_hashes, terminal_hashes


def native_sol(inputs: Inputs, base: str, evidence: dict, started: dict,
               accepted: bool) -> tuple[str, dict | None]:
    completion = inputs.read(base + "/process-completion.json", evidence["process_completion_sha256"])
    events_raw = inputs.raw(base + "/events.jsonl", completion["events_sha256"], completion["events_bytes"])
    events = [json.loads(line) for line in events_raw.splitlines() if line.strip()]
    threads = [event.get("thread_id") for event in events if event.get("type") == "thread.started"]
    require(len(threads) == 1 and isinstance(threads[0], str) and threads[0], "Native Sol thread missing or conflicting")
    require(started["model"] == "gpt-6-sol" and started["effort"] == "xhigh", "Retained Sol requested settings differ")
    if not accepted:
        require(evidence["state"] == "unknown_exit_requires_reconciliation"
                and evidence["native_thread_ids"] == threads, "Unadmitted native thread binding differs")
        return sha(threads[0].encode("utf-8")), None
    native = evidence["native_identity"]
    final_raw = inputs.raw(base + "/final.json", completion["final_sha256"], completion["final_bytes"])
    require(evidence["final_sha256"] == sha(final_raw) and completion["state"] == "exited"
            and completion["exit_code"] == 0 and native["thread_id"] == threads[0]
            and native["turn_completed"] is True and native["tool_events"] == 0
            and native["native_event_count"] == len(events), "Accepted Sol native identity/completion differs")
    require([event.get("type") for event in events] == ["thread.started", "turn.started", "item.completed", "turn.completed"],
            "Accepted Sol event order contains missing, foreign or tool events")
    item = events[2]["item"]
    require(item["type"] == "agent_message" and item["text"].rstrip("\r\n") == final_raw.decode("utf-8").rstrip("\r\n"),
            "Accepted Sol native final differs")
    return sha(threads[0].encode("utf-8")), json.loads(final_raw)


def project_packet(inputs: Inputs, scope: str, endpoint: str, root: str, row: dict,
                   receipt: dict, manifest: dict, manifest_sha: str, plan_sha: str,
                   repair: dict | None = None, repair_sha: str | None = None) -> dict:
    ordinal = row["ordinal"]
    base = f"{root}/{endpoint}/request-{ordinal:04d}"
    terminal = inputs.read(base + "/terminal.json", receipt["terminal_sha256"])
    start_raw = inputs.raw(base + "/attempt-start.json")
    started = json.loads(start_raw)
    require(started["ordinal"] == terminal["ordinal"] == ordinal and started["attempt_number"] == 1
            and started["manifest_sha256"] == manifest_sha and started["plan_sha256"] == plan_sha
            and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"]
            and started["session_id"] == terminal["session_id"], "Packet input/attempt/terminal binding differs")
    if endpoint == "sol":
        inputs.raw(base + "/prompt.txt", row["prompt_sha256"], row["prompt_bytes"])
        inputs.raw(base + "/schema.json", row["schema_sha256"], row["schema_bytes"])
    contact_path = inputs.path(base + "/contact-admission.json")
    contacted = contact_path.exists()
    if contacted:
        contact = inputs.read(base + "/contact-admission.json")
        require(contact["ordinal"] == ordinal and contact["session_id"] == started["session_id"]
                and contact["disclosure_sha256"] == manifest["disclosure_sha256"], "Contact admission binding differs")
        if endpoint == "grok":
            require(contact["route_sha256"] == manifest["grok_route_sha256"], "Contact route binding differs")
    evidence = terminal
    lineage = {"root_name": root, "manifest_sha256": manifest_sha,
               "terminal_sha256": receipt["terminal_sha256"], "attempt_start_sha256": sha(start_raw),
               "wave_result_sha256": receipt.get("wave_result_sha256"),
               "wave_intent_sha256": receipt.get("wave_intent_sha256"),
               "original_terminal_state": terminal["state"], "wave_terminal_state": receipt["state"],
               "contact_admission_exists": contacted}
    if contacted:
        lineage["contact_admission_sha256"] = inputs.artifacts[base + "/contact-admission.json"]["source_sha256"]
    if repair is not None:
        require(scope == "main" and endpoint == "sol" and repair["ordinal"] == ordinal
                and terminal["state"] == "unclassified_controller_exception" and receipt["state"] == "runner_exception"
                and repair["state"] == "accepted_reconciled" and repair["attempt_count"] == 1
                and repair["resend_count"] == 0 and repair["replacement"] is None
                and repair["manifest_sha256"] == manifest_sha
                and repair["terminal_sha256"] == receipt["terminal_sha256"]
                and repair["attempt_start_sha256"] == sha(start_raw), "Local repair predecessor binding differs")
        evidence = repair
        lineage["repair_sha256"] = repair_sha
    else:
        require(terminal["state"] == receipt["state"] and terminal["manifest_sha256"] == manifest_sha
                and terminal["plan_sha256"] == plan_sha, "Packet terminal state/condition differs")
    accepted = evidence["state"] in {"accepted", "accepted_reconciled"}
    require((accepted and contacted) or (not accepted and terminal["state"] in {
        "definitely_not_contacted", "unknown_exit_requires_reconciliation"}), "Unresolved packet disposition")
    native_hash, raw_response = None, None
    if endpoint == "sol":
        require(contacted, "Retained Sol packet lacks contact admission")
        native_hash, raw_response = native_sol(inputs, base, evidence, started, accepted)
        lineage["process_completion_sha256"] = evidence["process_completion_sha256"]
    else:
        outcome = inputs.read(base + "/broker-outcome.json", terminal["broker_outcome_sha256"])
        lineage["broker_outcome_sha256"] = terminal["broker_outcome_sha256"]
        if accepted:
            require(outcome["state"] == "completed" and outcome["failure"] is None, "Accepted Grok broker state differs")
            result = outcome["result"]
            runtime, native = result["runtime"], evidence["native_identity"]
            envelope = result["native_envelope_artifact"]
            require(envelope["sha256"] == evidence["native_envelope_sha256"] == runtime["envelope_hash"]
                    and native["session_id_hash"] == sha(started["session_id"].encode("utf-8"))
                    and runtime["session_id_hash"] == native["session_id_hash"]
                    and runtime["request_id_hash"] == native["request_id_hash"]
                    and runtime["observed_turns"] == native["observed_turns"]
                    and runtime["execution_contract"]["staged_prompt_sha256"] == row["prompt_sha256"]
                    and runtime["execution_contract"]["staged_prompt_byte_length"] == row["prompt_bytes"],
                    "Grok native envelope/identity/prompt binding differs")
            native_hash = native["request_id_hash"]
            raw_response = result["output"]
            lineage["native_envelope_sha256"] = envelope["sha256"]
            lineage["native_envelope_materialized_here"] = False
            lineage["retained_runtime_sha256"] = digest(runtime)
        else:
            require(not contacted and outcome["state"] == "definitely_not_contacted" and outcome["result"] is None,
                    "Definitely-not-contacted slot has conflicting contact/result")
    leaves = []
    if accepted:
        values = evidence["verdicts"]
        require([v["question_id"] for v in values] == row["question_ids"], "Accepted leaf order or coverage differs")
        native_values = raw_response["verdicts"]
        require([(v["question_id"], v["verdict"]) for v in native_values]
                == [(v["question_id"], v["verdict"]) for v in values], "Normalized leaves differ from retained native verdicts")
        if repair is not None:
            require(repair["events_sha256"] == inputs.artifacts[base + "/events.jsonl"]["source_sha256"]
                    and repair["repair_path"] == ["verdicts", 3, "evidence", 0, "exact_quote"], "Local repair source/path differs")
            derived = deepcopy(raw_response)
            quote = derived["verdicts"][3]["evidence"][0]["exact_quote"]
            require(isinstance(quote, str) and sha(quote.encode("utf-8")) == repair["prior_redundant_quote_sha256"],
                    "Local repair original quote commitment differs")
            derived["verdicts"][3]["evidence"][0]["exact_quote"] = None
            require(retained_digest(derived) == repair["derived_json_sha256"], "Local repair derived response hash differs")
            lineage["derived_json_sha256"] = repair["derived_json_sha256"]
        for position, value in enumerate(values):
            require(value["artifact_id"] == row["sample_id"] and value["bundle_id"] == "prose.short_form"
                    and value["verdict"] in VERDICTS, "Invalid normalized native leaf identity/value")
            leaves.append({"position": position, "question_id": value["question_id"], "verdict": value["verdict"],
                           "native_row_sha256": digest(native_values[position]), "normalized_row_sha256": digest(value)})
        lineage["normalized_verdicts_sha256"] = digest(values)
    slot = {"scope": scope, "endpoint": endpoint, "ordinal": ordinal, "sample_sha256": digest(row["sample_id"]),
            "group_sha256": digest(row["group_id_local_only"]), "source_sha256": row["source_sha256"],
            "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
            "planned_question_ids_sha256": digest(row["question_ids"]), "planned_question_count": len(row["question_ids"]),
            "client_session_sha256": sha(started["session_id"].encode("utf-8")), "native_identity_sha256": native_hash,
            "accepted": accepted, "disposition": evidence["state"], "no_resend": True,
            "leaves": leaves, "lineage": lineage, "lineage_sha256": digest(lineage)}
    if scope == "repeat":
        logical = f"batch35-repeat-1|{endpoint}|main-ordinal-{row['original_ordinal']}"
        slot.update(original_ordinal=row["original_ordinal"], planned_repeat_id=row["planned_repeat_id"], logical_repeat_id=logical)
        if accepted:
            identity = inputs.read(base + "/planned-repeat-identity.json")
            require(identity["endpoint"] == endpoint and identity["logical_repeat_id"] == logical
                    and identity["original_ordinal"] == row["original_ordinal"] and identity["repeat_ordinal"] == ordinal
                    and identity["plan_sha256"] == plan_sha and identity["terminal_sha256"] == receipt["terminal_sha256"],
                    "Repeat native receipt identity binding differs")
    return slot


def build_census(control_root: Path, descriptor: dict) -> tuple[dict, dict]:
    inputs = Inputs(control_root / descriptor["control_subdirectory"])
    data = {}
    for name, spec in descriptor["sources"].items():
        raw = inputs.raw(spec["path"], spec["sha256"])
        if spec.get("json", True):
            data[name] = json.loads(raw)
    main, repeat, prediction, readout, freeze = (data[k] for k in ("main_plan", "repeat_plan", "predictions", "repeat_readout", "source_freeze"))
    specs = descriptor["sources"]
    validate_repeat_requests(main, repeat, specs["main_plan"]["sha256"], specs["predictions"]["sha256"])
    require(main["source_freeze_sha256"] == repeat["source_freeze_sha256"] == specs["source_freeze"]["sha256"]
            and main["candidate_sha256"] == specs["candidate"]["sha256"]
            and repeat["repeatability_design_sha256"] == specs["repeat_design"]["sha256"]
            and prediction["plan_sha256"] == specs["main_plan"]["sha256"]
            and readout["plan_sha256"] == specs["repeat_plan"]["sha256"]
            and readout["blind_predictions_sha256"] == specs["predictions"]["sha256"]
            and readout["repeat_verdicts_are_not_extra_human_alignment_votes"] is True,
            "Retained source/plan/admission/repeat binding differs")
    source_variants = {}
    for group in freeze["selected"]:
        for variant in group["variants"]:
            key = variant["artifact_sha256"]
            require(key not in source_variants, "Ambiguous retained source identity")
            inputs.raw("lamp-holdout-source-r340/" + variant["artifact_path"], key, variant["artifact_bytes"])
            source_variants[key] = (group, variant)
    require(len(freeze["selected"]) == descriptor["expected"]["source_groups"]
            and len(source_variants) == descriptor["expected"]["source_variants"], "Retained source count differs")
    for scope, plan in (("main", main), ("repeat", repeat)):
        runner_pins = [value for key, value in plan["runtime_pins"].items()
                       if key.replace("\\", "/").endswith("/src/hbqrs/runner.py")]
        require(runner_pins == [descriptor["plan_runner_sha256"]], "Historical plan runner pin differs")
        require([r["ordinal"] for r in plan["requests"]] == list(range(1, len(plan["requests"]) + 1)), "Plan ordinal order differs")
        require(len(plan["requests"]) == descriptor["expected"][scope]["planned_requests_per_endpoint"], "Plan request count differs")
        planned = defaultdict(list)
        for row in plan["requests"]:
            require(len(row["question_ids"]) == len(set(row["question_ids"])), "Duplicate planned question")
            planned[row["sample_id"]].extend(row["question_ids"])
            plan_root = specs[scope + "_plan"]["path"].rsplit("/", 1)[0]
            inputs.raw(plan_root + "/" + row["prompt_path"], row["prompt_sha256"], row["prompt_bytes"])
            inputs.raw(plan_root + "/" + row["schema_path"], row["schema_sha256"], row["schema_bytes"])
        require(len(planned) == len(plan["passes"]) == descriptor["expected"][scope]["passes"], "Plan pass inventory differs")
        for passed in plan["passes"]:
            require(planned[passed["sample_id"]] == plan["question_ids"], "Planned leaf coverage/order differs")
            group, variant = source_variants[passed["source_sha256"]]
            require(passed["group_id_local_only"] == group["id"]
                    and passed["source_path_local_only"] == variant["artifact_path"]
                    and passed["instruction_sha256"] == group["instruction_sha256"], "Plan source/group/instruction identity differs")
            for row in (r for r in plan["requests"] if r["sample_id"] == passed["sample_id"]):
                require(row["source_sha256"] == passed["source_sha256"]
                        and row["group_id_local_only"] == passed["group_id_local_only"], "Request source/pass binding differs")
    slots, summaries, runtime_pins = [], {}, []
    all_clients, all_natives, accepted_natives, leaf_slots = set(), set(), set(), set()
    for scope, plan, admission in (("main", main, prediction["endpoint_receipts"]), ("repeat", repeat, readout["native_receipts"])):
        summaries[scope] = {}
        for endpoint in ("grok", "sol"):
            seen, hashes, terminal_hashes, lane_slots = set(), [], [], []
            lineage = descriptor["lineages"][scope][endpoint]
            actual_lineage = prediction["native_lineages"][endpoint] if scope == "main" else admission[endpoint]["lineage"]
            require([x["root_name"] for x in actual_lineage] == [x["root"] for x in lineage], "Retained lineage selection differs")
            previous = None
            for index, lane in enumerate(lineage):
                root, prefix = lane["root"], lane["source_prefix"]
                manifest, terminal, binding = (data[prefix + suffix] for suffix in ("_manifest", "_terminal", "_binding"))
                msha, tsha = (specs[prefix + suffix]["sha256"] for suffix in ("_manifest", "_terminal"))
                require(actual_lineage[index]["terminal_sha256"] == tsha
                        and terminal["manifest_sha256"] == msha and binding["manifest_sha256"] == msha
                        and manifest["confirmation_plan_sha256"] == specs[scope + "_plan"]["sha256"]
                        and manifest["selection_sha256"] == specs["candidate" if scope == "main" else "repeat_design"]["sha256"]
                        and manifest["disclosure_sha256"] == specs[scope + "_disclosure"]["sha256"], "Lineage condition/terminal binding differs")
                if previous is None:
                    require(binding["plan_sha256"] == specs[scope + "_plan"]["sha256"], "Wrapper plan binding differs")
                    stops = [item for item in terminal["endpoints"] if item["endpoint"] == endpoint]
                    require(len(stops) == 1, "Original endpoint stop receipt missing or duplicated")
                    stop = stops[0]
                    last = stop.get("wave_start", len(plan["requests"]) - 7)
                    require(lane["starts"] == list(range(1, last + 1, 8)), "Original lane stop boundary differs")
                else:
                    require(binding["previous_root_name"] == previous and binding["endpoint"] == endpoint
                            and terminal["endpoint"] == endpoint
                            and [w["wave_start"] for w in terminal["waves"]] == lane["starts"]
                            and binding["new_ordinals"] == list(range(lane["starts"][0], len(plan["requests"]) + 1)),
                            "Suffix boundary or predecessor binding differs")
                runtime_pins.append({"scope": scope, "endpoint": endpoint, "root_name": root,
                                     "manifest_sha256": msha, "runner_sha256": manifest["runner_sha256"],
                                     "native_helper_sha256": manifest["native_helper_sha256"]})
                packets, wave_hashes, thashes = wave_packets(inputs, root, endpoint, lane["starts"], len(plan["requests"]), msha, seen)
                hashes.extend(wave_hashes)
                terminal_hashes.extend(thashes)
                for ordinal, receipt in packets:
                    repair = data["repair"] if scope == "main" and endpoint == "sol" and ordinal == descriptor["repair_ordinal"] else None
                    slot = project_packet(inputs, scope, endpoint, root, plan["requests"][ordinal - 1], receipt,
                                          manifest, msha, specs[scope + "_plan"]["sha256"], repair,
                                          specs["repair"]["sha256"] if repair else None)
                    client, native = slot["client_session_sha256"], slot["native_identity_sha256"]
                    require(client not in all_clients, "Client session reused across logical requests")
                    all_clients.add(client)
                    if native is not None:
                        require(native not in all_natives, "Native identity reused across logical requests")
                        all_natives.add(native)
                        if slot["accepted"]:
                            accepted_natives.add(native)
                    for leaf in slot["leaves"]:
                        key = (scope, endpoint, slot["sample_sha256"], leaf["question_id"])
                        require(key not in leaf_slots, "Duplicate native leaf slot")
                        leaf_slots.add(key)
                    lane_slots.append(slot)
                previous = root
            expected_receipt = admission[endpoint]
            require(seen == set(range(1, len(plan["requests"]) + 1))
                    and hashes == expected_receipt["wave_result_hashes"]
                    and retained_digest(terminal_hashes) == expected_receipt["terminal_chain_sha256"], "Complete retained terminal/wave chain differs")
            require(expected_receipt["planned_ordinals" if scope == "main" else "planned"] == len(plan["requests"]),
                    "Retained declared request denominator differs")
            if scope == "main":
                repairs = [{"ordinal": s["ordinal"], "original_terminal_sha256": s["lineage"]["terminal_sha256"],
                            "repair_sha256": s["lineage"]["repair_sha256"]}
                           for s in lane_slots if "repair_sha256" in s["lineage"]]
                require(repairs == expected_receipt["local_reconciliations"], "Retained local-repair inventory differs")
            else:
                require(expected_receipt["unattempted"] == [], "Repeat endpoint retains unresolved unattempted slots")
            nonaccepted = [{"ordinal": s["ordinal"], "state": s["disposition"],
                            "terminal_sha256": s["lineage"]["terminal_sha256"],
                            "contact_admission_exists": s["lineage"]["contact_admission_exists"]}
                           for s in lane_slots if not s["accepted"]]
            require(nonaccepted == expected_receipt["nonaccepted"], "Unadmitted disposition inventory differs")
            accepted_count = sum(s["accepted"] for s in lane_slots)
            leaves = sum(len(s["leaves"]) for s in lane_slots)
            require(accepted_count == expected_receipt["accepted_count" if scope == "main" else "accepted"]
                    == descriptor["expected"][scope][endpoint]["accepted"]
                    and leaves == descriptor["expected"][scope][endpoint]["leaves"], "Accepted native/observed leaf denominator differs")
            summaries[scope][endpoint] = {"planned_requests": len(plan["requests"]), "client_sessions": len(lane_slots),
                "accepted_native_identities": accepted_count, "observed_native_leaves": leaves,
                "unadmitted_states": dict(Counter(s["disposition"] for s in lane_slots if not s["accepted"])),
                "retained_local_repairs": sum("repair_sha256" in s["lineage"] for s in lane_slots),
                "terminal_chain_sha256": retained_digest(terminal_hashes)}
            slots.extend(lane_slots)
    admitted, excluded = set(prediction["source_groups_admitted"]), set(prediction["source_groups_excluded"])
    groups = {group["id"] for group in freeze["selected"]}
    require(not admitted & excluded and admitted | excluded == groups
            and len(admitted) == descriptor["expected"]["admitted_groups"]
            and len(excluded) == descriptor["expected"]["excluded_groups"], "Source group admission partition differs")
    incomplete_groups = {s["group_sha256"] for s in slots if s["scope"] == "main" and not s["accepted"]}
    require(incomplete_groups <= {digest(g) for g in excluded}
            and len(incomplete_groups) == descriptor["expected"]["groups_with_unadmitted_requests"],
            "Native-gap source groups conflict with retained admission partition")
    require(len(all_clients) == descriptor["expected"]["client_sessions"]
            and len(accepted_natives) == descriptor["expected"]["accepted_native_identities"], "Combined client/native inventory differs")
    artifacts = sorted(inputs.artifacts.values(), key=lambda item: item["source_locator"])
    report = {"schema_version": 1, "status": "partial_census", "evidence_class": descriptor["scope"],
        "provider_calls_made": 0, "new_provider_votes": 0, "descriptor_sha256": digest(descriptor),
        "implementation_sha256": sha(Path(__file__).read_bytes()), "sources": list(specs.values()),
        "declared": {"source_groups": len(groups), "source_variants": len(source_variants),
                     "main": main["counts"], "repeat": repeat["counts"]},
        "observed": {"main": summaries["main"], "repeat": summaries["repeat"], "source_groups_admitted": len(admitted),
            "source_groups_excluded": len(excluded), "client_sessions": len(all_clients),
            "source_groups_with_unadmitted_requests": len(incomplete_groups),
            "excluded_groups_with_complete_request_leaves": len(excluded) - len(incomplete_groups),
            "accepted_native_identities": len(accepted_natives), "unadmitted_native_identities": len(all_natives - accepted_natives),
            "main_native_leaves": sum(v["observed_native_leaves"] for v in summaries["main"].values()),
            "repeat_native_leaves": sum(v["observed_native_leaves"] for v in summaries["repeat"].values()),
            "verified_artifact_count": len(artifacts), "verified_artifact_bytes": sum(a["source_bytes"] for a in artifacts)},
        "provenance": {"request_native_leaf_join_sha256": digest(slots), "verified_artifact_index_sha256": digest(artifacts),
            "plan_runtime_pins_sha256": {"main": digest(main["runtime_pins"]), "repeat": digest(repeat["runtime_pins"])},
            "plan_runner_sha256": descriptor["plan_runner_sha256"], "collection_runtime_pins": runtime_pins,
            "local_repair_sha256": specs["repair"]["sha256"],
            "local_repair_predecessor_terminal_sha256": data["repair"]["terminal_sha256"],
            "repeat_votes_are_extra_alignment_votes": False},
        "privacy": "Aggregates, hashes and allowlisted locators only; private slot ledger remains task-local.",
        "unresolved": descriptor["unresolved"]}
    ledger = {"schema_version": 1, "scope": descriptor["scope"], "private_task_local_only": True,
              "report_sha256": digest(report), "slots": slots, "artifacts": artifacts}
    return report, ledger


def output_preflight(output: Path, control_root: Path, descriptor: dict) -> None:
    require(not output.exists(), "Census output must be a fresh nonexistent directory")
    require(not inside(output, REPOSITORY), "Census output must remain outside the repository")
    retained = control_root / descriptor["control_subdirectory"]
    require(not inside(output, retained) and not inside(retained, output), "Output overlaps retained LAMP inputs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    descriptor = json.loads((HERE / "source-descriptor.json").read_bytes())
    try:
        output_preflight(args.output_root, args.control_root, descriptor)
        report, ledger = build_census(args.control_root, descriptor)
        if not args.dry_run:
            args.output_root.mkdir(parents=True, exist_ok=False)
            for name, value in (("census.json", report), ("private-slots.json", ledger)):
                with (args.output_root / name).open("xb") as stream:
                    stream.write(canonical(value) + b"\n")
        print(json.dumps({"dry_run": args.dry_run, "status": report["status"], "report_sha256": digest(report),
                          "private_ledger_sha256": digest(ledger), "observed": report["observed"]}, sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, f"Census C validation failed: {error}\n")


if __name__ == "__main__":
    main()
