"""Settled chains reserve all outcomes with each actual source-job binding."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import continue_chain as chain
import continue_manifest
from prepare import canonical, digest
from test_continue_manifest import frozen, settled_sample, write


def pin_native(sample, route):
    native = json.loads((sample / "native-result.json").read_bytes())
    if native["state"] == "completed":
        runtime = native["result"]["runtime"]
        runtime["subscription_receipt_hash"] = route["subscription_receipt_hash"]
        runtime["request_id_hash"] = digest(sample.name.encode())
        write(sample / "native-result.json", native)
        terminal = json.loads((sample / "terminal.json").read_bytes())
        terminal["native_result_sha256"] = digest((sample / "native-result.json").read_bytes())
        write(sample / "terminal.json", terminal)


@pytest.fixture
def source_chain(frozen, tmp_path):
    path, results, original, artifacts, grok = frozen
    validator_sha = digest((chain.HERE / "validate_response.py").read_bytes())
    original["implementation"] = {"semantic_validator_sha256": validator_sha}
    original.pop("manifest_content_sha256")
    original["manifest_content_sha256"] = digest(canonical(original))
    raw_original = write(path, original)
    job = json.loads((results / "job.json").read_bytes())
    job.update(manifest_sha256=digest(raw_original), zero_charge_only=True, automatic_retries=0,
               collector_sha256=digest((chain.HERE / "collector.py").read_bytes()), validator_sha256=validator_sha)
    job["route"].update(model=job["model"], zero_charge=True, subscription_receipt_hash="300-route-receipt")
    job["route_sha256"] = digest(canonical(job["route"])[:-1])
    write(results / "job.json", job)
    for row in grok[:6]:
        pin_native(results / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}", job["route"])
    descendant, derived_artifacts = continue_manifest.build(path, results)
    derived = tmp_path / "derived"
    derived.mkdir()
    for name, raw in derived_artifacts.items():
        target = derived / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    second = tmp_path / "second-results"
    second.mkdir()
    second_job = deepcopy(job)
    second_job["manifest_sha256"] = digest(derived_artifacts["manifest.json"])
    second_job["route"].update(timeout_seconds=900, subscription_receipt_hash="900-route-receipt")
    second_job["route_sha256"] = digest(canonical(second_job["route"])[:-1])
    write(second / "job.json", second_job)
    settled_sample(second, grok[6], artifacts, accepted=True)
    sample = second / f"0007-{grok[6]['logical_sample_id'][:12]}"
    pin_native(sample, second_job["route"])
    terminal = json.loads((sample / "terminal.json").read_bytes())
    terminal.update(state="semantic_rejected", accepted=False)
    terminal["acceptance_sha256"] = digest(write(sample / "acceptance.json", {"accepted": False, "abstention": False, "errors": ["Synthetic invalid evidence."]}))
    write(sample / "terminal.json", terminal)
    return path, [(path, results), (derived / "manifest.json", second)], original, artifacts, grok


def test_chain_preserves_original_artifacts_and_untouched_suffix(source_chain):
    path, jobs, original, source_artifacts, grok = source_chain
    before = deepcopy(original)
    manifest, artifacts = chain.build(path, jobs)
    assert manifest["requests"] == grok[7:]
    assert manifest["requests"][0]["endpoint_ordinal"] == 8
    assert manifest["counts"]["reserved_prefix_requests"] == 7
    assert manifest["historical_registration"]["counts"] == original["counts"]
    assert [item["runtime_timeout_seconds"] for item in manifest["continuation"]["prefix_jobs"]] == [300, 900]
    receipts = manifest["continuation"]["prefix_receipts"]
    assert [receipt["terminal_state"] for receipt in receipts] == ["accepted"] * 5 + ["ambiguous", "semantic_rejected"]
    assert [receipt["source_job_index"] for receipt in receipts] == [0] * 6 + [1]
    assert all(receipt["no_resend"] for receipt in receipts)
    assert manifest["collection_policy"]["name"] == "semantic_reject_continue_v2"
    assert artifacts["lineage/parent-manifest.json"] == path.read_bytes()
    assert set(artifacts) == {*source_artifacts, "lineage/parent-manifest.json", "manifest.json"}
    assert all(artifacts[name] == raw for name, raw in source_artifacts.items())
    assert original == before


def test_semantic_rejection_never_changes_suffix_selection_or_becomes_a_vote(source_chain):
    path, jobs, _, _, grok = source_chain
    first, _ = chain.build(path, jobs)
    sample = jobs[1][1] / f"0007-{grok[6]['logical_sample_id'][:12]}"
    receipt = json.loads((sample / "terminal.json").read_bytes())
    receipt.update(state="accepted", accepted=True)
    receipt["acceptance_sha256"] = digest(write(sample / "acceptance.json", {"accepted": True, "abstention": False, "errors": []}))
    write(sample / "terminal.json", receipt)
    second, _ = chain.build(path, jobs)
    assert first["requests"] == second["requests"]
    assert first["continuation"]["prefix_receipts"][-1]["terminal_state"] == "semantic_rejected"
    assert second["continuation"]["prefix_receipts"][-1]["terminal_state"] == "accepted"


@pytest.mark.parametrize("damage", ["missing", "duplicate_job", "noncontiguous", "wrong_job", "wrong_native"])
def test_invalid_prefix_or_bindings_block_continuation(source_chain, damage):
    path, jobs, _, _, grok = source_chain
    sample = jobs[1][1] / f"0007-{grok[6]['logical_sample_id'][:12]}"
    if damage == "missing":
        (sample / "terminal.json").unlink()
    elif damage == "duplicate_job":
        jobs.append(jobs[1])
    elif damage == "noncontiguous":
        first = jobs[0][1] / f"0001-{grok[0]['logical_sample_id'][:12]}"
        first.rename(first.with_name("preserved-missing-slot"))
    elif damage == "wrong_job":
        (jobs[1][1] / "job.json").write_bytes((jobs[0][1] / "job.json").read_bytes())
    else:
        native = json.loads((sample / "native-result.json").read_bytes())
        native["result"]["runtime"]["subscription_receipt_hash"] = "300-route-receipt"
        write(sample / "native-result.json", native)
        terminal = json.loads((sample / "terminal.json").read_bytes())
        terminal["native_result_sha256"] = digest((sample / "native-result.json").read_bytes())
        write(sample / "terminal.json", terminal)
    with pytest.raises((ValueError, FileNotFoundError)):
        chain.build(path, jobs)


def test_duplicate_native_request_identity_blocks_chain(source_chain):
    path, jobs, _, _, grok = source_chain
    source = jobs[0][1] / f"0001-{grok[0]['logical_sample_id'][:12]}"
    target = jobs[1][1] / f"0007-{grok[6]['logical_sample_id'][:12]}"
    identity = json.loads((source / "native-result.json").read_bytes())["result"]["runtime"]["request_id_hash"]
    native = json.loads((target / "native-result.json").read_bytes())
    native["result"]["runtime"]["request_id_hash"] = identity
    write(target / "native-result.json", native)
    terminal = json.loads((target / "terminal.json").read_bytes())
    terminal["native_result_sha256"] = digest((target / "native-result.json").read_bytes())
    write(target / "terminal.json", terminal)
    with pytest.raises(ValueError, match="Duplicate native request"):
        chain.build(path, jobs)


def test_changed_source_job_descriptor_is_not_reused(source_chain):
    path, jobs, _, _, _ = source_chain
    source, results = jobs[1]
    manifest = json.loads(source.read_bytes())
    row = manifest["requests"][0]
    row["repeat"] = 0
    row["question_ids"] = ["changed-question"]
    row.pop("request_sha256")
    row["request_sha256"] = digest(canonical(row))
    manifest.pop("manifest_content_sha256")
    manifest["manifest_content_sha256"] = digest(canonical(manifest))
    raw = write(source, manifest)
    job = json.loads((results / "job.json").read_bytes())
    job["manifest_sha256"] = digest(raw)
    write(results / "job.json", job)
    with pytest.raises(ValueError, match="changes original descriptor"):
        chain.build(path, jobs)
