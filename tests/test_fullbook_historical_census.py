"""Historical joins retain scope identity and fail on changed evidence or leaves."""
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-fullbook-historical-census-v1/census.py"
spec = importlib.util.spec_from_file_location("fullbook_census_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path):
    recipe = {"policy": census.POLICY, "helper_pins": {k: v[1] for k, v in census.HELPERS.items()},
              "freeze_root": "freeze", "roots": [], "executions": [], "expected": {"requests": 2, "positions": 4}}

    def add(root, path, value):
        raw = value if isinstance(value, bytes) else census.canonical(value) + b"\n"
        target = tmp_path / root["locator"] / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        row = {"locator": path, "sha256": census.sha(raw), "bytes": len(raw)}
        root["files"].append(row)
        return row

    parents = {}
    for number in range(2):
        root = {"locator": "execution" + str(number), "files": []}
        recipe["roots"].append(root)
        aid = "artifact" + str(number)
        parents[aid] = str(tmp_path / root["locator"])
        add(root, "plan.json", {"route": {"sampling_plan": {"unit_ids": []}}})
        recipe["executions"].append({"artifact_id": aid, "root": root["locator"],
                                     "scopes": [{"id": "global", "positions": 2, "batches": 1, "bundle_id": "prose.novel"}]})
        prefix = ".private/evaluations/global/"
        add(root, prefix + "run.json", {"run_id": "run" + str(number), "config_sha256": census.sha(b'config'),
                                        "configuration": {"question_ids": ["a", "b"], "batch_size": 2, "bundle_id": "prose.novel"}})
        leaves = [{"question_id": "a", "verdict": "YES"}, {"question_id": "b", "verdict": "CANNOT_ASSESS"}]
        verdict_raw = b''.join(census.canonical(v) + b'\n' for v in leaves)
        verdict_pin = add(root, prefix + "verdicts.jsonl", verdict_raw)
        add(root, prefix + "response.schema.json", b'{"type":"object"}')
        # Invalid JSON escapes demonstrate that response prose is hashed, never decoded.
        response = br'{"verdicts":[{"note":"SEALED\q"}]}'
        response_pin = add(root, prefix + "responses/batch-0001.accepted-0001.message.txt", response)
        add(root, prefix + "responses/batch-0001.attempt-0001.message.json", response)
        prompt = b'SEALED CREATIVE PAYLOAD'
        add(root, prefix + "responses/batch-0001.prompt.txt.gz", gzip.compress(prompt))
        checkpoint = {"batch": 1, "accepted_attempt": 1, "question_ids": ["a", "b"],
                      "prompt_sha256": census.sha(prompt), "base_prompt_sha256": census.sha(prompt),
                      "effective_prompt_sha256": census.sha(prompt), "response_sha256": response_pin["sha256"],
                      "previous_checkpoint_sha256": None, "verdicts_sha256": verdict_pin["sha256"],
                      "response_artifact": {**response_pin, "path": response_pin["locator"][len(prefix):]},
                      "rejected_chain": {"count": 0, "head_sha256": None}, "normalized_verdicts": leaves,
                      "provider": {"reported": {"provider": "openai", "model": "historical-sol", "reasoning_effort": "high",
                                                "session_id": "same-reported-session"}},
                      "private_note": "SEALED RATIONALE"}
        checkpoint["response_artifact"].pop("locator")
        cp_pin = add(root, prefix + "responses/batch-0001.json", checkpoint)
        stem = prefix + "responses/attempt-lifecycle/batch-0001/attempt-0001"
        start = {"attempt": 1, "batch": 1, "base_prompt_sha256": census.sha(prompt),
                 "effective_prompt_sha256": census.sha(prompt), "config_sha256": census.sha(b'config'),
                 "policy": "terminal_sidecar_v1", "state": "started"}
        start_pin = add(root, stem + ".start.json", start)
        add(root, stem + ".settled.json", {"attempt": 1, "batch": 1, "policy": "terminal_sidecar_v1", "state": "settled",
                                          "outcome": "accepted", "start_sha256": start_pin["sha256"],
                                          "evidence": {"kind": "accepted_checkpoint", "path": "responses/batch-0001.json",
                                                       "sha256": cp_pin["sha256"]}})
    freeze = {"locator": "freeze", "files": []}
    recipe["roots"].append(freeze)
    plan_pin = add(freeze, "plan.json", {"parent_roots": parents})
    add(freeze, "freeze-manifest.json", {"files": {"plan.json": {k: plan_pin[k] for k in ("sha256", "bytes")}}})
    return recipe


def test_scope_qualified_positions_privacy_session_gap_and_fresh_output(tmp_path):
    recipe = fixture(tmp_path)
    report, ledger = census.run(recipe, tmp_path)
    assert report["observed"]["accepted_request_chains"] == 2
    assert report["observed"]["ordered_leaf_positions"] == 4
    assert len({v["position_id_sha256"] for v in ledger["leaves"]}) == 4
    assert report["gaps"]["duplicate_reported_session_request_positions"] == 1
    assert b'SEALED' not in census.canonical({"report": report, "ledger": ledger})
    assert report["provider_calls_made"] == report["new_provider_votes"] == 0
    output = census.destination(tmp_path / "fresh", tmp_path, recipe)
    assert not output.exists()
    with pytest.raises(ValueError, match="overlaps"):
        census.destination(tmp_path / "execution0/new", tmp_path, recipe)


def test_changed_commitment_and_recommitted_duplicate_leaf_fail(tmp_path):
    recipe = fixture(tmp_path)
    root = recipe["roots"][0]
    path = ".private/evaluations/global/responses/batch-0001.json"
    target = tmp_path / root["locator"] / path
    original = target.read_bytes()
    target.write_bytes(original + b' ')
    with pytest.raises(ValueError, match="Source hash differs"):
        census.run(recipe, tmp_path)
    value = json.loads(original)
    value["normalized_verdicts"][1]["question_id"] = "a"
    raw = census.canonical(value) + b'\n'
    target.write_bytes(raw)
    pin = next(r for r in root["files"] if r["locator"] == path)
    pin.update(sha256=census.sha(raw), bytes=len(raw))
    with pytest.raises(ValueError, match="Checkpoint leaf identities"):
        census.run(recipe, tmp_path)
