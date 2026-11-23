"""Provider-free metadata census of the two historical V14 TRAIN endpoints.

Use a private, digest-bound recipe and a fresh output under the control root.
Targets, score projections, prompts, responses, events and command containers
are never decoded. This counts receipt metadata, not admitted votes or contacts.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_v14_train_receipt_metadata_v1"
PROJECTOR = REPO / "evaluation-results/hbq-matched-hanna-20261004/prepare.py"
PROJECTOR_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
CELL = {k: True for k in ("cell_id", "candidate_id", "item_id", "prompt_group_id", "partition", "payload_sha256")}
SCHEDULE = {k: True for k in ("format_version", "study_id", "kind", "endpoint", "schedule_sha256")}
SCHEDULE.update(geometry={k: True for k in ("candidates", "grok_cells", "groups", "items", "max_concurrency", "sol_cells")},
                groups=[{k: True for k in ("prompt_group_id", "partition")}],
                cells=[{**CELL, **{k: True for k in ("ordinal", "candidate_sha256", "candidate_instruction_sha256",
                      "candidate_profile_sha256", "source_binding_sha256")},
                      "endpoint_payload_sha256s": {"grok_primary": True, "sol_later": True}}])
IDENTITY = {
    "grok": {k: True for k in ("provider", "requested_model", "reported_model", "request_id", "session_id",
                               "tools_enabled", "native_endpoint_contact_cardinality")},
    "sol": {k: True for k in ("contact_id", "effective_model", "native_endpoint_contact_cardinality", "provider",
              "provider_reported_model", "reasoning_attested", "requested_model", "requested_reasoning_effort",
              "route_name", "session_id", "thread_id", "transport_identity")}}
SETTINGS = {k: True for k in ("requested_model", "requested_reasoning_effort", "tools_enabled",
                             "web_search_enabled", "subagents_enabled", "route_name")}
PREPARED = {k: True for k in ("format_version", "kind", "study_id", "authorization_sha256", "disclosure_sha256",
                            "response_schema_sha256", "route_proof_sha256", "process_launches", "provider_calls_made", "tools_enabled")}
RECEIPT = {k: True for k in ("format_version", "kind", "study_id", "effective_settings_sha256", "launch_intent_sha256",
                           "process_launches", "provider_calls_made", "native_endpoint_contact_cardinality")}
FILES = ("prepared.json", "execution-receipt.json", "effective-settings.json", "launch-intent.json", "response-schema.json")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()


def projector():
    raw = PROJECTOR.read_bytes()
    require(sha(raw) == PROJECTOR_SHA, "Lexical projector differs")
    namespace = {"__file__": str(PROJECTOR), "__name__": "v14_census_metadata_projector"}
    exec(compile(raw, str(PROJECTOR), "exec"), namespace)
    return namespace["project_json"]


def path_for(pin, roots):
    root = roots[pin["root"]]
    locator = Path(pin["locator"])
    require(not locator.is_absolute(), "Relative pin locator required")
    path = (root / locator).resolve()
    require(path.is_relative_to(root), "Source leaves declared root")
    return path


def checked(pin, roots):
    raw = path_for(pin, roots).read_bytes()
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Frozen source bytes differ")
    return raw


def schemas(endpoint):
    cell = dict(CELL)
    if endpoint == "sol":
        cell.update(source_cell_id=True, payload_parity=True)
    prepared = {**PREPARED, "cell": cell}
    receipt = {**RECEIPT, "cell": cell, "identity": IDENTITY[endpoint]}
    settings = dict(SETTINGS)
    if endpoint == "grok":
        prepared.update(schedule_sha256=True, outbound_payload_sha256=True, prompt_request_sha256=True)
        receipt.update(**{k: True for k in ("identity_sha256", "prepared_sha256", "payload_sha256", "native_request_sha256",
                       "native_response_sha256", "runner_prompt_artifact_sha256")})
        settings.update(reported_model=True, reasoning_attested=True)
    else:
        prepared.update(task_payload_sha256=True, source={k: True for k in (
            "expansion_study_sha256", "expansion_schedule_sha256", "recovered_descendant_sha256", "sol_role",
            "endpoint_pooling", "selection", "promotion", "generalization")})
        receipt.update(**{k: True for k in ("request_sha256", "response_schema_sha256", "final_response_sha256",
                       "raw_events_sha256", "raw_stderr_sha256", "internal_retry_cardinality")})
        settings.update(local_effective_model=True, local_effective_reasoning_effort=True, provider_attested=True)
    return prepared, receipt, settings


def cell_id(candidate, item):
    return "v14-expansion-" + sha(canonical({"candidate": candidate, "item": item}))[:20]


def sol_id(source):
    return "v14-expansion-sol-" + sha(canonical({"source_cell_id": source}))[:20]


def run(recipe, roots):
    require(recipe["policy"] == POLICY and set(recipe["endpoints"]) == {"grok", "sol"}, "Recipe endpoint contract differs")
    project = projector()
    for pin in recipe["sources"].values():
        checked(pin, roots)
    schedule = project(checked(recipe["sources"]["schedule"], roots), SCHEDULE)
    require(schedule["schedule_sha256"] == recipe["semantic_schedule_sha256"], "Declared semantic schedule differs")
    require(schedule["geometry"] == {"candidates": 2, "grok_cells": 88, "groups": 22, "items": 44,
                                     "max_concurrency": 10, "sol_cells": 0}, "Schedule geometry differs")
    require(schedule["endpoint"] == "grok_primary" and
            schedule["study_id"] == recipe["endpoints"]["grok"]["study_id"], "Schedule endpoint/study differs")
    cells = schedule["cells"]
    require(len(cells) == 88 and len({c["cell_id"] for c in cells}) == 88 and
            len({c["ordinal"] for c in cells}) == 88 and all(c["partition"] == "train" for c in cells),
            "Schedule cell membership differs")
    groups = {g["prompt_group_id"] for g in schedule["groups"]}
    require(len(schedule["groups"]) == len(groups) == 22 and all(g["partition"] == "train" for g in schedule["groups"]),
            "Schedule group membership differs")
    candidates = sorted({c["candidate_id"] for c in cells})
    item_sets = [{c["item_id"] for c in cells if c["candidate_id"] == k} for k in candidates]
    require(len(candidates) == 2 and item_sets[0] == item_sets[1] and len(item_sets[0]) == 44 and
            {c["prompt_group_id"] for c in cells} == groups and
            all(c["cell_id"] == cell_id(c["candidate_id"], c["item_id"]) and
                c["endpoint_payload_sha256s"] == {"grok_primary": c["payload_sha256"], "sol_later": c["payload_sha256"]}
                for c in cells), "Schedule item identity differs")
    rows, identity_sets, source_ledger = [], {}, []
    for endpoint, binding in sorted(recipe["endpoints"].items()):
        root = path_for(binding["root"], roots)
        require(root.is_dir(), "Endpoint root missing")
        planned = {c["cell_id"] if endpoint == "grok" else sol_id(c["cell_id"]) for c in cells}
        actual = {p.name for p in root.iterdir() if p.is_dir() and p.name != ".claims"}
        require(actual == planned and set(binding["cells"]) == planned, "Finite endpoint directory membership differs")
        identity_sets[endpoint] = set()
        p_spec, r_spec, s_spec = schemas(endpoint)
        for source in sorted(cells, key=lambda c: c["ordinal"]):
            name = source["cell_id"] if endpoint == "grok" else sol_id(source["cell_id"])
            pins = binding["cells"][name]
            require(set(pins) == set(FILES), "Finite cell file roles differ")
            raw = {}
            for filename, pin in pins.items():
                require(path_for(pin, roots) == (root / name / filename).resolve(), "Cell pin path differs")
                raw[filename] = checked(pin, roots)
                source_ledger.append(pin)
            # Launch intent and schema are opaque commitments; all prose containers remain skipped.
            prepared = project(raw["prepared.json"], p_spec)
            receipt = project(raw["execution-receipt.json"], r_spec)
            settings = project(raw["effective-settings.json"], s_spec)
            expected = {key: source[key] for key in CELL}
            expected["cell_id"] = name
            if endpoint == "sol":
                expected.update(source_cell_id=source["cell_id"], payload_parity="v14_expansion_grok_schedule_exact_payload_bytes")
            require(prepared["cell"] == receipt["cell"] == expected, "Preparation/receipt cell membership differs")
            require(prepared["study_id"] == receipt["study_id"] == binding["study_id"] and
                    prepared["process_launches"] == prepared["provider_calls_made"] == 0 and
                    receipt["process_launches"] == 1, "Preparation/execution metadata differs")
            require(receipt["effective_settings_sha256"] == pins["effective-settings.json"]["sha256"] and
                    receipt["launch_intent_sha256"] == pins["launch-intent.json"]["sha256"] and
                    prepared["response_schema_sha256"] == pins["response-schema.json"]["sha256"] == recipe["response_schema_sha256"],
                    "Receipt settings/launch/schema binding differs")
            if endpoint == "grok":
                require(prepared["schedule_sha256"] == schedule["schedule_sha256"] and
                        prepared["outbound_payload_sha256"] == source["payload_sha256"] and
                        receipt["prepared_sha256"] == pins["prepared.json"]["sha256"] and
                        receipt["payload_sha256"] == source["payload_sha256"] and
                        receipt["identity_sha256"] == sha(canonical(receipt["identity"])), "Grok receipt binding differs")
                keys = ("request_id", "session_id")
            else:
                require(prepared["source"]["expansion_schedule_sha256"] == schedule["schedule_sha256"] and
                        prepared["source"]["expansion_study_sha256"] == recipe["sources"]["grok_code"]["sha256"] and
                        receipt["response_schema_sha256"] == pins["response-schema.json"]["sha256"] and
                        prepared["task_payload_sha256"] == receipt["request_sha256"] == source["payload_sha256"],
                        "Sol source schedule binding differs")
                keys = ("thread_id", "session_id")
            identity = tuple(receipt["identity"][key] for key in keys)
            require(all(isinstance(v, str) and v for v in identity) and identity not in identity_sets[endpoint],
                    "Duplicate or missing endpoint identity")
            identity_sets[endpoint].add(identity)
            control_checks = {
                "requested_model": receipt["identity"]["requested_model"] == settings["requested_model"],
                "prepared_tools": prepared["tools_enabled"] == settings["tools_enabled"],
            }
            if endpoint == "grok":
                control_checks.update(reported_model=receipt["identity"]["reported_model"] == settings["reported_model"],
                                      identity_tools=receipt["identity"]["tools_enabled"] == settings["tools_enabled"])
            else:
                control_checks.update(requested_effort=receipt["identity"]["requested_reasoning_effort"] == settings["requested_reasoning_effort"],
                                      effective_model=receipt["identity"]["effective_model"] == settings["local_effective_model"])
            mismatches = sorted(key for key, consistent in control_checks.items() if not consistent)
            rows.append({"endpoint": endpoint, "source_cell_id": source["cell_id"], "cell_id": name,
                         "disposition": "receipt_backed_metadata_control_mismatch" if mismatches else "receipt_backed_metadata_only",
                         "control_metadata_mismatches": mismatches, "prepared": prepared,
                         "receipt": receipt, "settings": settings, "pins": pins})
        require(all(len({v[i] for v in identity_sets[endpoint]}) == 88 for i in (0, 1)), "Endpoint identity reuse differs")
    source_ledger.extend(recipe["sources"].values())
    counts = {endpoint: {"planned_cells": 88, "receipt_backed_metadata_cells": 88, "distinct_identity_pairs": len(identities),
                        "candidate_cells": dict(Counter(row["prepared"]["cell"]["candidate_id"] for row in rows if row["endpoint"] == endpoint)),
                        "control_metadata_mismatch_cells": sum(bool(row["control_metadata_mismatches"]) for row in rows if row["endpoint"] == endpoint),
                        "settings_tool_flags": dict(Counter(str(row["settings"]["tools_enabled"]) for row in rows if row["endpoint"] == endpoint)),
                        "receipt_provider_call_declarations": dict(Counter(str(row["receipt"]["provider_calls_made"]) for row in rows if row["endpoint"] == endpoint))}
              for endpoint, identities in identity_sets.items()}
    report = {"policy": POLICY, "status": "completed_metadata_only_census", "partition": "train",
              "items": 44, "groups": 22, "candidates": 2, "planned_cells": 176, "endpoints": counts,
              "source_pins": recipe["sources"], "semantic_schedule_sha256": schedule["schedule_sha256"],
              "semantic_schedule_hash_recomputed": False, "source_commitments_checked": len(source_ledger),
              "input_commitment_sha256": sha(canonical(source_ledger)), "provider_calls": 0, "new_votes": 0,
              "native_admission_replays": 0, "semantic_admission_replays": 0, "scoring_calls": 0, "compiler_calls": 0,
              "tools_off_eligible_records": 0, "capacity_released": 0, "physical_contact_cardinality": None,
              "labels_opened": False, "score_projections_opened": False, "confirmation_opened": False,
              "candidate_promoted": False, "full_goal_complete": False,
              "limitations": ["Receipt-backed metadata membership only; not current native/semantic admission or leaf/score validation.",
                 "Declared request/session uniqueness does not prove physical contacts, provider attestation or billing quiescence.",
                 "Schedule hash is joined as declared; excluded targets and payloads prevent independent semantic-hash recomputation.",
                 "Historical tool flags confer no current tools-disabled qualification or capacity release.",
                 "TRAIN items overlap prior candidates/expansions; endpoint rows are not additional unique human references.",
                 "Published terminal-inventory/report serialization is not reconstructed; no prior aggregate metric is recomputed."]}
    return report, {"policy": POLICY, "rows": rows, "artifact_ledger": source_ledger}


def recheck_snapshot(recipe, roots):
    for pin in recipe["sources"].values():
        checked(pin, roots)
    for binding in recipe["endpoints"].values():
        root = path_for(binding["root"], roots)
        require({p.name for p in root.iterdir() if p.is_dir() and p.name != ".claims"} == set(binding["cells"]),
                "Endpoint directory snapshot changed")
        for pins in binding["cells"].values():
            for pin in pins.values():
                checked(pin, roots)
    require(sha(PROJECTOR.read_bytes()) == PROJECTOR_SHA, "Projector snapshot changed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("documents-root", "control-root", "recipe", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--recipe-sha256", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    implementation_raw = Path(__file__).read_bytes()
    roots = {"repository": REPO, "documents": args.documents_root.resolve(), "control": args.control_root.resolve()}
    raw = args.recipe.read_bytes()
    require(sha(raw) == args.recipe_sha256, "Recipe digest differs")
    recipe = json.loads(raw)
    output = args.output_root.resolve()
    require(not output.exists() and output.is_relative_to(roots["control"]) and not output.is_relative_to(REPO),
            "Fresh private output under control root required")
    source_paths = [path_for(p, roots) for p in recipe["sources"].values()]
    source_paths += [path_for(e["root"], roots) for e in recipe["endpoints"].values()]
    require(all(not output.is_relative_to(p if p.is_dir() else p.parent) and not p.is_relative_to(output) for p in source_paths)
            and not args.recipe.resolve().is_relative_to(output), "Output overlaps frozen source")
    report, private = run(recipe, roots)
    recheck_snapshot(recipe, roots)
    require(args.recipe.read_bytes() == raw and Path(__file__).read_bytes() == implementation_raw,
            "Recipe/implementation snapshot changed")
    require(not output.exists() and output == args.output_root.absolute(), "Fresh plain output ancestry required")
    private_raw = canonical(private)
    report.update(implementation_sha256=sha(implementation_raw), recipe_sha256=sha(raw), private_ledger_sha256=sha(private_raw))
    report_raw = canonical(report)
    receipt = {"policy": POLICY, "state": "verified" if args.dry_run else "completed", "output_written": not args.dry_run,
               "report_sha256": sha(report_raw), "private_ledger_sha256": sha(private_raw),
               "implementation_sha256": report["implementation_sha256"], "recipe_sha256": sha(raw),
               "planned_cells": 176, "provider_calls": 0, "new_votes": 0}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in (("report.json", report_raw), ("private-metadata-ledger.json", private_raw),
                            ("recipe.json", raw), ("census_train_v14_metadata.py", implementation_raw),
                            ("terminal.json", canonical(receipt))):
            with (output / name).open("xb") as stream:
                stream.write(value)
    print(json.dumps(receipt, sort_keys=True))
    return receipt


if __name__ == "__main__":
    main()
