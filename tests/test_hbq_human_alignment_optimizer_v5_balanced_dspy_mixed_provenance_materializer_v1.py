from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1"
QUEUE = Path(r"C:\Users\Haile\.codex\state\model-work-queue")
PREPARATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-v4-ccbb5b2-r4shrink-replacement-20260830b\r4shrink-replacement-20260830b-sample-01\dspy-input-preparation.json")
PARTIAL = Path(r"C:\Users\Haile\Documents\cwr-hanna-v3-reconcile-result-20260830b\partial-manifest.json")


def _module():
    path = PACKAGE / "materialize.py"
    spec = importlib.util.spec_from_file_location("_hanna_mixed_materializer_v1", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_exact_completed_queue_result_materializes_one_distinct_tenth_descendant(tmp_path: Path) -> None:
    module = _module()
    for source in (QUEUE / "queue.sqlite3", PREPARATION, PARTIAL):
        assert source.exists(), f"missing frozen provider-free source: {source}"

    output = tmp_path / "materialized"
    result = module.materialize(
        queue_root=QUEUE,
        dspy_input_preparation=PREPARATION,
        partial_nine_manifest=PARTIAL,
        output_root=output,
    )

    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert result["candidate_id"] == "candidate-625dac0d1e79f79c"
    assert result["candidate_sha256"] == "625dac0d1e79f79c544c4e6ec66af442499cae553e0179ea934906eee3533113"
    assert _sha((output / "queue-result.json").read_bytes()) == module.RESULT_SHA256
    assert _sha((output / "queue-request.json").read_bytes()) == module.REQUEST_SHA256
    assert _sha((output / "queue-task-metadata.json").read_bytes()) == module.TASK_METADATA_SHA256
    assert _sha((output / "queue-registry.json").read_bytes()) == module.REGISTRY_SHA256
    assert _sha((output / "queue-disclosure.json").read_bytes()) == module.DISCLOSURE_SHA256
    assert _sha((output / "dspy-input-preparation.json").read_bytes()) == module.PREPARATION_SHA256
    assert _sha((output / "partial-nine-manifest.json").read_bytes()) == module.PARTIAL_MANIFEST_FILE_SHA256
    assert _sha((output / "recommendation.bin").read_bytes()) == module.RECOMMENDATION_SHA256
    assert _sha((output / "parent-instruction.bin").read_bytes()) == module.PARENT_INSTRUCTION_SHA256
    assert _sha((output / "parent-profile.bin").read_bytes()) == module.PARENT_PROFILE_SHA256
    assert _sha((output / "descendant-instruction.bin").read_bytes()) == module.DESCENDANT_INSTRUCTION_SHA256
    assert _sha((output / "descendant-profile.json").read_bytes()) == "a3c67e96891ddb41a5cd69eda5308652410b9ab6ac946f03848108cdf14d3185"

    recommendation = (output / "recommendation.bin").read_bytes()
    parent = (output / "parent-instruction.bin").read_bytes()
    assert (output / "descendant-instruction.bin").read_bytes() == parent + b"\n" + recommendation + b"\n"
    profile = json.loads((output / "descendant-profile.json").read_bytes())
    assert profile["instruction_sha256"] == module.DESCENDANT_INSTRUCTION_SHA256
    assert profile["lineage"] == {
        "derivation": "parent_instruction_lf_recommendation_lf",
        "parent_instruction_sha256": module.PARENT_INSTRUCTION_SHA256,
        "parent_profile_sha256": module.PARENT_PROFILE_SHA256,
        "provider_output_unchanged": False,
        "queue_item_id": module.ITEM_ID,
        "queue_output_sha256": module.OUTPUT_SHA256,
        "queue_result_sha256": module.RESULT_SHA256,
        "recommendation_sha256": module.RECOMMENDATION_SHA256,
    }

    receipt = json.loads((output / "queue-receipt.json").read_bytes())
    assert receipt["evidence_class"] == "completed_queue_adapter_result_with_one_completed_attempt"
    assert receipt["endpoint_contact_evidence"] == {
        "native_contact_proven": False,
        "native_endpoint_contact_cardinality": "unknown_not_inferred_from_queue_attempt",
        "reasoning_attested": False,
        "source_model": "grok-4.6",
        "source_provider_attempts": 1,
        "source_route": "grok-build-grok-4.6",
    }
    assert receipt["sqlite"]["work_item"]["disclosure_hash"] == module.DISCLOSURE_SHA256
    assert receipt["sqlite"]["work_item"]["idempotency_key"] == module.IDEMPOTENCY_KEY
    assert receipt["sqlite"]["attempts"] == [{
        "detail": None, "finished_at": "2026-08-30T21:35:07+00:00", "id": 78,
        "item_id": module.ITEM_ID, "late_detail": None, "late_result_hash": None,
        "lease_token": "b7b8fac091d34befac8d932acd5e96cd", "outcome": "completed",
        "result_hash": module.RESULT_SHA256, "route_model": "grok-4.6",
        "route_name": "grok-build-grok-4.6", "started_at": "2026-08-30T21:33:44+00:00",
    }]
    composition_raw = (output / "mixed-composition.json").read_bytes()
    composition = json.loads(composition_raw)
    body = dict(composition); manifest_sha = body.pop("manifest_sha256")
    assert manifest_sha == _sha(module.canonical(body))
    assert composition["composition"] == {"candidate_count": 10, "exploratory_post_hoc_materializations": 1, "reconciled_v3_terminal_descendants": 9}
    assert composition["authority"] == module.AUTHORITY
    assert len(composition["candidates"]) == len({row["candidate_id"] for row in composition["candidates"]}) == 10
    kinds = [row["provenance"]["kind"] for row in composition["candidates"]]
    assert kinds.count("reconciled_v3_terminal_descendant_under_unknown_native_contact") == 9
    assert kinds.count("EXPLORATORY_POST_HOC_MATERIALIZATION") == 1
    assert "native_grok_descendant" not in composition_raw.decode("utf-8")
    assert all(row["provenance"]["source_terminal"]["provider_calls_made"] is None for row in composition["candidates"][:9])
    assert all(row["provenance"]["source_terminal"]["native_endpoint_contact_cardinality"] == "unknown" for row in composition["candidates"][:9])
    tenth = composition["candidates"][-1]
    assert tenth["candidate_id"] != module.PARENT_CANDIDATE_ID
    assert base64.b64decode(tenth["instruction_base64"], validate=True) == (output / "descendant-instruction.bin").read_bytes()
    assert tenth["provenance"]["provider_output_unchanged"] is False
    assert tenth["provenance"]["source_provider_attempts"] == 1
    assert tenth["provenance"]["reasoning_attested"] is False
    assert tenth["provenance"]["not_a_recovered_replacement_or_native_descendant"] is True
    assert json.loads((output / "descendant.json").read_bytes())["authority"] == module.AUTHORITY

    with pytest.raises(ValueError, match="fresh output"):
        module.materialize(queue_root=QUEUE, dspy_input_preparation=PREPARATION, partial_nine_manifest=PARTIAL, output_root=output)


def test_strict_transport_and_frozen_identity_mutations_fail_closed() -> None:
    module = _module()
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e309}', b'{"x":-1e309}'):
        with pytest.raises(ValueError, match="strict UTF-8 JSON"):
            module.strict_json(raw, label="adversarial")

    result_raw = (QUEUE / "artifacts" / module.RESULT_SHA256[:2] / module.RESULT_SHA256[2:]).read_bytes()
    registry_raw = (QUEUE / "artifacts" / module.REGISTRY_SHA256[:2] / module.REGISTRY_SHA256[2:]).read_bytes()
    result = module.strict_json(result_raw, label="result")
    registry = module.strict_json(registry_raw, label="registry")
    wrong_output = copy.deepcopy(result)
    wrong_output["result"]["output"]["recommendations"][0] += " changed"
    with pytest.raises(ValueError, match="output commitment"):
        module._validate_result(wrong_output, registry)
    wrong_command = copy.deepcopy(result)
    wrong_command["result"]["runtime"]["command_identity_hash"] = "0" * 64
    with pytest.raises(ValueError, match="command identity"):
        module._validate_result(wrong_command, registry)


def test_frozen_parent_or_partial_manifest_tamper_cannot_create_output(tmp_path: Path) -> None:
    module = _module()
    bad_preparation = tmp_path / "bad-preparation.json"
    bad_preparation.write_bytes(PREPARATION.read_bytes()[:-2] + b" \n")
    output = tmp_path / "bad-output"
    with pytest.raises(ValueError, match="source hash drifted"):
        module.materialize(queue_root=QUEUE, dspy_input_preparation=bad_preparation, partial_nine_manifest=PARTIAL, output_root=output)
    assert not output.exists()

    bad_partial = tmp_path / "bad-partial.json"
    bad_partial.write_bytes(PARTIAL.read_bytes()[:-2] + b" \n")
    with pytest.raises(ValueError, match="source hash drifted"):
        module.materialize(queue_root=QUEUE, dspy_input_preparation=PREPARATION, partial_nine_manifest=bad_partial, output_root=output)
    assert not output.exists()


def test_queue_lifecycle_mutations_fail_closed() -> None:
    module = _module()
    receipt = module._queue_receipt(QUEUE)
    work = copy.deepcopy([receipt["sqlite"]["work_item"]])
    attempts = copy.deepcopy(receipt["sqlite"]["attempts"])
    deliveries = copy.deepcopy(receipt["sqlite"]["deliveries"])
    for row, key, replacement in (
        (work[0], "idempotency_key", "different"),
        (work[0], "disclosure_hash", "0" * 64),
        (work[0], "updated_at", "2026-08-30T21:35:08+00:00"),
        (attempts[0], "lease_token", "0" * 32),
        (attempts[0], "started_at", "2026-08-30T21:33:45+00:00"),
        (deliveries[0], "attempts", 2),
        (deliveries[0], "updated_at", "2026-08-30T21:35:08+00:00"),
    ):
        mutated_work, mutated_attempts, mutated_deliveries = copy.deepcopy(work), copy.deepcopy(attempts), copy.deepcopy(deliveries)
        target = mutated_work[0] if row is work[0] else mutated_attempts[0] if row is attempts[0] else mutated_deliveries[0]
        target[key] = replacement
        with pytest.raises(ValueError, match="queue completion receipt"):
            module._validate_queue_rows(mutated_work, mutated_attempts, mutated_deliveries)


def test_sqlite_snapshot_rejects_controlled_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    attacker = tmp_path / "attacker.sqlite3"
    attacker.write_bytes((QUEUE / "queue.sqlite3").read_bytes())
    actual_connect = sqlite3.connect

    def redirect(_database: str, *args: object, **kwargs: object) -> sqlite3.Connection:
        return actual_connect(attacker.resolve().as_uri() + "?mode=ro", uri=True)

    monkeypatch.setattr(module.sqlite3, "connect", redirect)
    with pytest.raises(ValueError, match="snapshot was redirected"):
        module._queue_receipt(QUEUE)


def test_output_creation_rejects_preexisting_artifact_and_identity_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    root = tmp_path / "output"
    identity, parent_identity = module._create_output_root(root)
    module._write_artifact(root, identity, parent_identity, "one.json", b"{}\n")
    with pytest.raises(ValueError, match="could not create artifact"):
        module._write_artifact(root, identity, parent_identity, "one.json", b"{}\n")
    monkeypatch.setattr(module, "_directory_identity", lambda _stat: (0, 0, 0))
    with pytest.raises(ValueError, match="output root identity changed"):
        module._write_artifact(root, identity, parent_identity, "two.json", b"{}\n")


def test_output_parent_swap_rejects_write(tmp_path: Path) -> None:
    module = _module()
    parent = tmp_path / "parent"
    parent.mkdir()
    root = parent / "output"
    identity, parent_identity = module._create_output_root(root)
    parent.replace(tmp_path / "replaced-parent")
    parent.mkdir()
    with pytest.raises(ValueError, match="output root identity changed"):
        module._write_artifact(root, identity, parent_identity, "after-swap.json", b"{}\n")


def test_package_has_no_provider_or_evaluator_surface() -> None:
    source = (PACKAGE / "materialize.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "requests" not in source
    assert "socket" not in source
    assert "execute-wave" not in source
    contract = json.loads((PACKAGE / "study-contract.json").read_bytes())
    assert contract["authority"] == _module().AUTHORITY
    assert contract["authority"]["local_only"] is True
    assert contract["authority"]["endpoint_contact_evidence"]["native_contact_proven"] is False
