"""Copied authorities, independent repeats, sealed fields and immutable boundaries."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-revision-ledger-census-v1/census.py"
spec = importlib.util.spec_from_file_location("revision_census_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path):
    roots, wrappers = [], []
    specifications = {
        "receipt": {key: True for key in ("event_id", "phase", "provider_model", "reasoning",
                                         "frozen_manifest_sha256", "prepared_record_sha256", "response_sha256")},
        "prepared": {"event_id": True, "phase": True, "provider_model": True}, "failure": {"state": True},
        "link": {"source_receipt": {"sha256": True}},
    }
    specifications["receipt"]["local_lifecycle"] = {"thread_id_sha256": True}
    recipe = {"policy": census.POLICY, "helper_pins": {k: v[1] for k, v in census.HELPERS.items()},
              "roots": roots, "wrappers": wrappers, "specifications": specifications, "external_references": []}

    def add(root, name, value, selected=None):
        raw = json.dumps(value).encode()
        (tmp_path / root["locator"] / name).write_bytes(raw)
        item = {"locator": name, "sha256": census.sha(raw), "bytes": len(raw)}
        if selected:
            item["spec"] = selected
        root["files"].append(item)
        return item["sha256"]

    parent_sha = None
    for index in range(2):
        root = {"id": str(index), "locator": "root" + str(index), "files": [], "status": "historical_metadata_only"}
        (tmp_path / root["locator"]).mkdir()
        roots.append(root)
        prepared_sha = add(root, "prepared.json", {"event_id": "original", "wrapper_version": index,
                                                  "phase": "cwr_feedback", "provider_model": "sol"}, "prepared")
        value = {"event_id": "original", "phase": "cwr_feedback", "provider_model": "sol",
                 "reasoning": "high", "frozen_manifest_sha256": census.sha(b'context'),
                 "prepared_record_sha256": prepared_sha, "response_sha256": census.sha(b'answer'),
                 "local_lifecycle": {"thread_id_sha256": census.sha(b'one native observation')},
                 "response": {"overall": 77, "rationale": "SEALED PRIVATE PROSE"}}
        receipt_spec = "receipt"
        if index == 1:
            # A wrapper may omit condition fields while preserving a bound local preparation.
            value.pop("phase")
            value.pop("provider_model")
            specifications["receipt-with-bound-condition"] = {key: v for key, v in specifications["receipt"].items()
                                                               if key not in {"phase", "provider_model"}}
            receipt_spec = "receipt-with-bound-condition"
        receipt_sha = add(root, "receipt.json", value, receipt_spec)
        wrappers.append({"root_id": str(index), "locator": "receipt.json", "logical_id": "original", "role": "receipt",
                         "bindings": [{"field": "prepared_record_sha256", "locator": "prepared.json"}]})
        if index == 0:
            parent_sha = receipt_sha
            add(root, "failure.json", {"state": "terminal_postlaunch_reconcile_required"}, "failure")
            wrappers.append({"root_id": "0", "locator": "failure.json", "logical_id": "failed",
                             "role": "failed_reserved"})
        else:
            add(root, "link.json", {"source_receipt": {"sha256": parent_sha}, "response": "SEALED"}, "link")
            wrappers.append({"root_id": "1", "locator": "link.json", "logical_id": "original", "role": "source_link"})
            # Same answer from a planned independent native request remains a separate observation.
            value["event_id"] = "planned-repeat"
            value["phase"], value["provider_model"] = "cwr_feedback", "sol"
            value["local_lifecycle"]["thread_id_sha256"] = census.sha(b'independent native repeat')
            add(root, "repeat.json", value, "receipt")
            wrappers.append({"root_id": "1", "locator": "repeat.json", "logical_id": "planned-repeat", "role": "receipt"})
    return recipe


def test_copied_wrappers_deduplicate_native_response_without_merging_repeats(tmp_path):
    recipe = fixture(tmp_path)
    report, ledger = census.run(recipe, tmp_path)
    assert report["observed"]["receipt_wrappers"] == 4
    assert report["observed"]["distinct_native_response_metadata_joins"] == 2
    assert report["observed"]["repeated_native_response_wrappers"] == 2
    assert report["observed"]["failed_reserved_observations"] == 1
    assert report["observed"]["verified_metadata_hash_bindings"] == 2
    assert b'SEALED' not in census.canonical({"report": report, "ledger": ledger})
    assert report["new_provider_votes"] == report["provider_calls_made"] == 0
    output = census.destination(tmp_path / "fresh", tmp_path, recipe)
    assert not output.exists()
    with pytest.raises(ValueError, match="overlaps"):
        census.destination(tmp_path / "root0/new", tmp_path, recipe)


def test_changed_metadata_and_conflicting_native_response_fail_before_export(tmp_path):
    recipe = fixture(tmp_path)
    receipt = tmp_path / "root1/receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b' ')
    with pytest.raises(ValueError, match="Source hash differs"):
        census.run(recipe, tmp_path)
    # A freshly committed wrapper with a conflicting answer must also fail the join.
    value = json.loads(receipt.read_bytes())
    value["response_sha256"] = census.sha(b'different answer')
    raw = json.dumps(value).encode()
    receipt.write_bytes(raw)
    pin = next(row for row in recipe["roots"][1]["files"] if row["locator"] == "receipt.json")
    pin.update(sha256=census.sha(raw), bytes=len(raw))
    with pytest.raises(ValueError, match="conflicting response"):
        census.run(recipe, tmp_path)


def test_sealed_values_are_skipped_before_decode_and_forbidden_spec_is_rejected():
    # This invalid escape would fail ordinary JSON decoding; sealed content is never decoded.
    raw = br'{"kind":"metadata","response":{"rationale":"SEALED\q","overall":77}}'
    assert census.project_json(raw, {"kind": True}) == {"kind": "metadata"}
    with pytest.raises(ValueError, match="Outcome/prose"):
        census.safe_spec({"response": True})
