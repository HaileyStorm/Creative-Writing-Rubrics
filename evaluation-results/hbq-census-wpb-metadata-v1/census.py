"""Finite, hash-bound WPB metadata census without admission or scoring replay."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "wpb_completed_historical_metadata_census_v1"
V2_PATH = REPO / "evaluation-results/hbq-census-pass-b-dispositions-v1/registry_v2.py"
V2_SHA = "311d8f79f667cb4730af5045e1b2e936b7fb8c53a12fed3d9649beb9d8879940"
PREFIX_ROOTS = ("cwr-wpb-sol-strict-schema-validation-20260910-r1",
                "cwr-wpb-sol-pending-validation-20260912-r1",
                "cwr-wpb-sol-partial-validation-20260912-r1",
                "cwr-wpb-sol-serialized126-validation-20260912-r1")
CAMPAIGN = "cwr-wpb-sol-import-serialized-validation-20260912-r1"
IDENTITY_FIELDS = {key: True for key in (
    "contact_id", "effective_model", "native_endpoint_contact_cardinality", "provider",
    "provider_reported_model", "reasoning_attested", "requested_model", "requested_reasoning_effort",
    "route_name", "session_id", "thread_id", "transport_identity")}
RECEIPT_FIELDS = {key: True for key in (
    "request_sha256", "final_response_sha256", "effective_settings_sha256", "internal_retry_cardinality",
    "native_endpoint_contact_cardinality", "process_launches", "provider_calls_made")}
RECEIPT_FIELDS.update(cell={"cell_id": True, "payload_sha256": True}, identity=IDENTITY_FIELDS)
PREFIX_BINDING = {key: True for key in (
    "preserved_import_serialized_reconciliation_sha256", "execution_receipt_sha256",
    "identity_sha256", "effective_settings_sha256")}
SUCCESSOR_BINDING = {key: True for key in (
    "batch_number", "route_sha256", "route_evidence_sha256", "review_sha256",
    "execution_receipt_sha256", "identity_sha256", "effective_settings_sha256",
    "prepared_source_bindings_sha256")}


def common():
    if hashlib.sha256(V2_PATH.read_bytes()).hexdigest() != V2_SHA:
        raise ValueError("Pinned metadata projection utility differs")
    spec = importlib.util.spec_from_file_location("wpb_metadata_pinned_v2", V2_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = module.SELECTIVE.read_bytes()
    module.require(module.sha(raw) == module.SELECTIVE_SHA, "Lexical reader pin differs")
    tree = ast.parse(raw)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and
                node.name in {"require", "project_json"}]
    module.require(len(selected) == 2, "Lexical reader functions differ")
    namespace = {"json": json}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(module.SELECTIVE), "exec"), namespace)
    module.project = namespace["project_json"]
    return module


def source_path(pin, roots):
    root = roots[pin["root"]].resolve()
    locator = pin["locator"]
    path = (root / locator).resolve()
    if not isinstance(locator, str) or "\\" in locator or Path(locator).is_absolute() or not path.is_relative_to(root):
        raise ValueError("Source locator escapes its declared root")
    return path


def checked(pin, roots):
    raw = source_path(pin, roots).read_bytes()
    if len(raw) != pin["bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Frozen source commitment differs")
    return raw


def output_preflight(output, pins, roots):
    output = output.resolve()
    if output.exists() or output.is_relative_to(REPO) or any(
            output == source_path(pin, roots) or
            source_path(pin, roots).is_relative_to(output) for pin in pins):
        raise ValueError("Fresh output outside repository and retained source directories required")
    return output


def run(recipe, roots):
    v2 = common()
    require, project = v2.require, v2.project
    require(recipe["policy"] == POLICY and recipe["schema_version"] == 1, "Wrong census policy")
    sources = {pin["id"]: pin for pin in recipe["sources"]}
    require(len(sources) == len(recipe["sources"]) and
            len({(p["root"], p["locator"]) for p in sources.values()}) == len(sources),
            "Duplicate frozen source descriptor")
    raw = {name: checked(pin, roots) for name, pin in sources.items()}
    prefix = project(raw["manifest"], {"completed_cells": True})["completed_cells"]
    require(len(prefix) == len(set(prefix)) == 4, "Frozen preserved measurement membership differs")
    bindings = project(raw["final-report"], {"native_receipt_bindings": True})["native_receipt_bindings"]
    rows = [{"cell_id": cell_id, "receipt": "receipt-" + cell_id, "preserved": cell_id in prefix}
            for cell_id in sorted(bindings)]
    ids = [row["cell_id"] for row in rows]
    require(len(ids) == len(set(ids)) == 129 and {r["cell_id"] for r in rows if r["preserved"]} == set(prefix),
            "Finite measurement membership differs")
    report_fields = {key: True for key in (
        "format_version", "kind", "status", "authority", "confirmation", "measurement_count",
        "preserved_completed_cells", "new_measurement_count", "successor_manifest_sha256",
        "import_serialized_reconciliation_sha256")}
    report_fields.update(route_epochs=[{key: True for key in (
        "batch_number", "route_sha256", "route_evidence_sha256", "review_sha256", "settlement_sha256")}],
        native_receipt_bindings={row["cell_id"]: PREFIX_BINDING if row["preserved"] else SUCCESSOR_BINDING for row in rows})
    report = project(raw["final-report"], report_fields)
    require(bindings == report["native_receipt_bindings"], "Unexpected fields in historical native metadata binding")
    for row in rows:
        cell_id = row["cell_id"]
        require(cell_id.startswith("wpb-pair-wpb-en-") and cell_id[len("wpb-pair-wpb-en-"):].isdigit(),
                "Unsafe logical receipt locator")
        binding = bindings[cell_id]
        base = PREFIX_ROOTS[prefix.index(cell_id)] if row["preserved"] else CAMPAIGN
        number = 1 if row["preserved"] else binding["batch_number"]
        require(type(number) is int and 1 <= number <= 13, "Unsafe receipt batch locator")
        locator = base + "/batches/" + format(number, "04d") + "/execution/" + cell_id + "/execution-receipt.json"
        path = source_path({"root": "documents", "locator": locator}, roots)
        pin = {"id": row["receipt"], "root": "documents", "locator": locator,
               "sha256": binding["execution_receipt_sha256"], "bytes": path.stat().st_size}
        require((pin["root"], pin["locator"]) not in {(p["root"], p["locator"]) for p in sources.values()},
                "Duplicate report-driven receipt descriptor")
        raw[row["receipt"]] = checked(pin, roots)
        sources[row["receipt"]] = pin
    require(report["status"] == "complete_batched_sol_campaign" and report["format_version"] == 1 and
            report["kind"] == "wpb_sol_import_serialized_successor_replayed_report_v1" and
            report["authority"] == "development_screening_only" and report["confirmation"] == "closed" and
            report["measurement_count"] == 129 and report["new_measurement_count"] == 125 and
            report["preserved_completed_cells"] == prefix and
            report["successor_manifest_sha256"] == sources["manifest"]["sha256"] and
            report["import_serialized_reconciliation_sha256"] == sources["reconciliation"]["sha256"],
            "Saved report identity/source binding differs")
    completion = project(raw["completion"], {key: True for key in (
        "state", "report_sha256", "provider_calls_made", "frozen_grok_choice_refitted", "confirmation")})
    require(completion == {"state": "full_129_cell_report_completed", "report_sha256": sources["final-report"]["sha256"],
        "provider_calls_made": 0, "frozen_grok_choice_refitted": False, "confirmation": "closed"},
        "Saved report completion differs")
    provenance = project(raw["public-provenance"], {"source_artifacts": {
        "wpb_final_report": {"sha256": True, "measurement_count": True, "new_measurement_count": True},
        "wpb_final_completion": {"sha256": True}}, "report_generation": {"provider_calls_made": True}})
    require(provenance == {"source_artifacts": {"wpb_final_report": {
        "sha256": sources["final-report"]["sha256"], "measurement_count": 129, "new_measurement_count": 125},
        "wpb_final_completion": {"sha256": sources["completion"]["sha256"]}},
        "report_generation": {"provider_calls_made": 0}}, "Public/private report commitments differ")
    manifest = project(raw["manifest"], {"kind": True, "completed_cells": True,
        "remaining_logical_cells": True, "automatic_resend_authorized": True, "campaign": {"sha256": True}})
    require(manifest == {"kind": "wpb_sol_import_serialized_successor_v1", "completed_cells": prefix,
        "remaining_logical_cells": 125, "automatic_resend_authorized": False,
        "campaign": {"sha256": sources["campaign"]["sha256"]}}, "Successor manifest membership differs")
    campaign = project(raw["campaign"], {"cells": [{"cell_id": True, "payload_sha256": True}]})["cells"]
    require(len(campaign) == 125 and len({c["cell_id"] for c in campaign}) == 125 and
            {c["cell_id"] for c in campaign} == set(ids) - set(prefix), "Successor campaign membership differs")
    campaign_by_id = {cell["cell_id"]: cell for cell in campaign}
    epochs = {epoch["batch_number"]: epoch for epoch in report["route_epochs"]}
    require(len(epochs) == len(report["route_epochs"]) == 13 and set(epochs) == set(range(1, 14)),
            "Saved batch epoch membership differs")
    settled = {}
    settlement_memberships = []
    for entry in recipe["settlements"]:
        number = entry["batch_number"]
        require(sources[entry["source"]]["sha256"] == epochs[number]["settlement_sha256"],
                "Saved epoch settlement commitment differs")
        value = project(raw[entry["source"]], {"status": True, "cells": [{key: True for key in (
            "cell_id", "state", "execution_receipt_sha256", "identity_sha256", "raw_response_sha256")}]})
        cells = value["cells"]
        require(value["status"] == "completed" and len(cells) == (10 if number < 13 else 5) and
                len({c["cell_id"] for c in cells}) == len(cells), "Completed settlement membership differs")
        for cell in cells:
            require(cell["state"] == "completed" and cell["cell_id"] not in settled, "Duplicate or unsettled successor cell")
            settled[cell["cell_id"]] = (number, cell)
        settlement_memberships.append({"source": entry["source"], "batch_number": number,
            "cell_ids": [cell["cell_id"] for cell in cells]})
    require(set(settled) == set(ids) - set(prefix) and
            sorted(e["batch_number"] for e in recipe["settlements"]) == list(range(1, 14)),
            "Finite successor settlement coverage differs")
    measurements = []
    for row in rows:
        cell_id = row["cell_id"]
        receipt = project(raw[row["receipt"]], RECEIPT_FIELDS)
        binding = report["native_receipt_bindings"][cell_id]
        identity = receipt["identity"]
        identity_sha = v2.sha(v2.canonical(identity))
        require(sources[row["receipt"]]["sha256"] == binding["execution_receipt_sha256"] and
                identity_sha == binding["identity_sha256"] and
                receipt["effective_settings_sha256"] == binding["effective_settings_sha256"] and
                receipt["cell"]["cell_id"] == cell_id and receipt["request_sha256"] == receipt["cell"]["payload_sha256"],
                "Completed receipt/report metadata join differs")
        require(identity["requested_model"] == "gpt-5.6-sol" and identity["requested_reasoning_effort"] == "high" and
                identity["reasoning_attested"] is False and receipt["process_launches"] == 1 and
                receipt["internal_retry_cardinality"] == receipt["native_endpoint_contact_cardinality"] == "unproven" and
                receipt["provider_calls_made"] is None, "Historical requested-only receipt scope differs")
        require(isinstance(identity["thread_id"], str) and bool(identity["thread_id"]) and
                isinstance(identity["session_id"], str) and bool(identity["session_id"]), "Native identity metadata absent")
        if row["preserved"]:
            require(binding["preserved_import_serialized_reconciliation_sha256"] == sources["reconciliation"]["sha256"],
                    "Preserved measurement reconciliation differs")
        else:
            number, settlement = settled[cell_id]
            require(binding["batch_number"] == number and
                    all(binding[key] == epochs[number][key] for key in ("route_sha256", "route_evidence_sha256", "review_sha256")) and
                    settlement["execution_receipt_sha256"] == binding["execution_receipt_sha256"] and
                    settlement["identity_sha256"] == identity_sha and
                    settlement["raw_response_sha256"] == receipt["final_response_sha256"] and
                    campaign_by_id[cell_id]["payload_sha256"] == receipt["request_sha256"],
                    "Campaign/settlement/receipt metadata join differs")
        measurements.append({"cell_id": cell_id, "receipt_source": row["receipt"], "preserved": row["preserved"],
            "identity_sha256": identity_sha, "request_sha256": receipt["request_sha256"],
            "payload_sha256": receipt["cell"]["payload_sha256"], "execution_receipt_sha256": binding["execution_receipt_sha256"],
            "effective_settings_sha256": binding["effective_settings_sha256"],
            "native_thread_session_sha256": v2.sha(v2.canonical([identity["thread_id"], identity["session_id"]])),
            "requested_model": identity["requested_model"], "requested_reasoning_effort": identity["requested_reasoning_effort"],
            "reasoning_attested": identity["reasoning_attested"]})
    for key in ("identity_sha256", "request_sha256", "payload_sha256", "native_thread_session_sha256"):
        require(len({row[key] for row in measurements}) == 129, "Duplicate completed measurement metadata identity")
    chain_names = ("reconciliation-strict", "reconciliation-partial", "reconciliation-serialized126", "reconciliation")
    strict = project(raw[chain_names[0]], {"campaign_root": True, "remaining_logical_cells": True,
        "completed_cell_ids": True, "automatic_resend": True, "batch_restart_authorized": True,
        "complete_batch_admitted": True, "provider_calls_during_reconciliation": True,
        "settlement_sha256": True, "protected_completed_identity": IDENTITY_FIELDS})
    require(Path(strict["campaign_root"]).resolve() == (roots["documents"] / PREFIX_ROOTS[0]).resolve() and
        strict["remaining_logical_cells"] == 128 and strict["completed_cell_ids"] == prefix[:1] and
        strict["automatic_resend"] is False and strict["batch_restart_authorized"] is False and
        strict["complete_batch_admitted"] is False and strict["provider_calls_during_reconciliation"] == 0 and
        strict["settlement_sha256"] == sources["ancestor-1"]["sha256"] and
        v2.sha(v2.canonical(strict["protected_completed_identity"])) == bindings[prefix[0]]["identity_sha256"],
        "Historical strict reconciliation identity/status join differs")
    for index in range(1, 4):
        count = index + 1
        descriptor_fields = {"path": True, "sha256": True}
        fields = {"campaign_root": True, "completed_cells": True, "remaining_logical_cells": True,
            "automatic_resend_authorized": True, "prior_reconciliation": descriptor_fields, "settlement": descriptor_fields}
        receipt_key = prefix[index].rsplit("-", 1)[-1] + "_execution_receipt"
        if index >= 2:
            fields[receipt_key] = descriptor_fields
        value = project(raw[chain_names[index]], fields)
        require(value["completed_cells"] == prefix[:count] and value["remaining_logical_cells"] == 129 - count and
                value["automatic_resend_authorized"] is False and
                Path(value["campaign_root"]).resolve() == (roots["documents"] / PREFIX_ROOTS[index]).resolve(),
                "Historical reconciliation prefix/root differs")
        for key, target in (("prior_reconciliation", chain_names[index - 1]), ("settlement", "ancestor-" + str(count))):
            require(value[key]["sha256"] == sources[target]["sha256"] and
                    Path(value[key]["path"]).resolve() == source_path(sources[target], roots),
                    "Historical reconciliation predecessor/settlement join differs")
        if index >= 2:
            target = sources["receipt-" + prefix[index]]
            require(value[receipt_key]["sha256"] == target["sha256"] and
                    Path(value[receipt_key]["path"]).resolve() == source_path(target, roots),
                    "Historical preserved receipt descriptor differs")
    occurrences = []
    for entry in recipe["ancestor_settlements"]:
        value = project(raw[entry["source"]], {"status": True, "cells": [{"cell_id": True, "state": True}]})
        require(value["status"] == "terminal_or_ambiguous" and len(value["cells"]) == 10 and
                Counter(cell["state"] for cell in value["cells"]) == {"completed": 1, "terminal_or_ambiguous": 9},
                "Ancestor generic status membership differs")
        require(entry["namespace"] in PREFIX_ROOTS and [cell["cell_id"] for cell in value["cells"]
            if cell["state"] == "completed"] == [prefix[PREFIX_ROOTS.index(entry["namespace"])]],
            "Ancestor completed identity differs from preserved measurement")
        for ordinal, cell in enumerate(value["cells"], 1):
            occurrences.append({"namespace": entry["namespace"], "ordinal": ordinal, **cell})
    frequency = Counter(row["cell_id"] for row in occurrences)
    terminal_ids = {row["cell_id"] for row in occurrences if row["state"] == "terminal_or_ambiguous"}
    observed = {"completed_measurements": len(measurements), "preserved_measurements": 4,
        "successor_measurements": 125, "completed_settlements": 13, "distinct_identity_commitments": 129,
        "distinct_request_commitments": 129, "distinct_payload_commitments": 129,
        "ancestor_status_occurrences": len(occurrences), "ancestor_distinct_logical_ids": len(frequency),
        "ancestor_recurring_logical_ids": sum(n > 1 for n in frequency.values()),
        "ancestor_terminal_or_ambiguous_occurrences": sum(row["state"] == "terminal_or_ambiguous" for row in occurrences),
        "ancestor_terminal_or_ambiguous_distinct_logical_ids": len(terminal_ids)}
    require(observed == recipe["expected_counts"] and len({e["namespace"] for e in recipe["ancestor_settlements"]}) == 4,
            "Frozen expected metadata counts differ")
    source_descriptor = list(sources.values())
    require(len(source_descriptor) == 158, "Finite source descriptor size differs")
    private = {"policy": POLICY, "artifact_ledger": source_descriptor, "measurements": measurements,
               "settlement_memberships": settlement_memberships, "ancestor_status_occurrences": occurrences}
    public = {"schema_version": 1, "policy": POLICY, "observed": observed,
        "source_descriptor_sha256": v2.sha(v2.canonical(source_descriptor)),
        "input_commitment_sha256": v2.sha(v2.canonical(source_descriptor)), "committed_files": len(source_descriptor),
        "static_source_descriptor_sha256": v2.sha(v2.canonical(recipe["sources"])),
        "measurement_commitment_sha256": v2.sha(v2.canonical(measurements)),
        "ancestor_occurrence_commitment_sha256": v2.sha(v2.canonical(occurrences)),
        "public_source_binding": {key: sources[key] for key in ("public-provenance", "public-aggregate", "final-report", "completion")},
        "lexical_reader_sha256": v2.SELECTIVE_SHA, "projection_utility_sha256": V2_SHA,
        "provider_calls_made": 0, "new_provider_votes": 0, "human_labels_opened": False,
        "native_admission": "not_replayed", "scoring": "not_replayed", "observed_leaf_coverage": "not_established",
        "physical_contact_cardinality": None, "internal_retry_cardinality": None,
        "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "reasoning_attested": False,
        "limitations": ["Historical completed metadata only; no new observations or votes and no quality or human validation claim.",
            "Generic ancestor states are namespaced occurrences, not failed contacts, extra votes or physical retries.",
            "Requested model and effort are historical declarations; provider-side reasoning and physical cardinality remain unproven.",
            "Targets, prose, prepared payloads, human_score_projection, sessions, raw responses and analysis outcomes are not decoded."]}
    return public, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("documents-root", "control-root", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    v2 = common()
    roots = {"repository": REPO, "documents": args.documents_root.resolve(),
             "control": args.control_root.resolve()}
    recipe_raw = (HERE / "recipe.json").read_bytes()
    recipe = json.loads(recipe_raw)
    output = output_preflight(args.output_root, recipe["sources"], roots)
    v2.require(all(not output.is_relative_to((roots["documents"] / locator).resolve()) for locator in
                   (CAMPAIGN, *PREFIX_ROOTS)), "Output overlaps retained campaign root")
    report_pin = next(pin for pin in recipe["sources"] if pin["id"] == "final-report")
    v2.require(not output.is_relative_to(source_path(report_pin, roots).parent), "Output overlaps retained final report directory")
    implementation_raw = Path(__file__).read_bytes()
    report, private = run(recipe, roots)
    report.update(recipe_file_sha256=v2.sha(recipe_raw), implementation_sha256=v2.sha(implementation_raw),
                  private_ledger_sha256=v2.sha(v2.canonical(private)))
    report_raw = v2.canonical(report)
    receipt = {"policy": POLICY, "report_sha256": v2.sha(report_raw),
               "recipe_file_sha256": v2.sha(recipe_raw), "implementation_sha256": v2.sha(implementation_raw),
               "private_ledger_sha256": report["private_ledger_sha256"], "observed": report["observed"],
               "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": args.dry_run}
    for pin in private["artifact_ledger"]:
        checked(pin, roots)
    v2.require((HERE / "recipe.json").read_bytes() == recipe_raw and
               Path(__file__).read_bytes() == implementation_raw and
               v2.sha(V2_PATH.read_bytes()) == V2_SHA and
               v2.sha(v2.SELECTIVE.read_bytes()) == v2.SELECTIVE_SHA, "Census source changed during execution")
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        artifacts = {"report.json": report_raw, "private-ledger.json": v2.canonical(private),
                     "recipe.json": recipe_raw, "census.py": implementation_raw}
        for name, content in artifacts.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
        with (output / "terminal.json").open("xb") as stream:
            stream.write(v2.canonical({**receipt, "state": "completed"}))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
