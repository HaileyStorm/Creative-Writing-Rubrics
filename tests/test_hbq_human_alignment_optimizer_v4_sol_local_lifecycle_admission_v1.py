from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1"
EXEC_PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3"
admit = load_module(PACKAGE / "admit.py", name="hanna_sol_lifecycle_admission_v1")
execution = load_module(EXEC_PACKAGE / "executor.py", name="hanna_sol_lifecycle_admission_exec_v3")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(tmp_path: Path) -> dict:
    roots = {"frozen_successor_path": Path.home() / "Documents" / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json", "hanna_csv_path": Path.home() / "Documents" / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv"}
    predecessor = execution._load_predecessor()
    return next(dict(row) for row in predecessor.derive_schedule(**roots)["mandatory_development"] if row["route_name"] == "sol_validation"), roots


def _seed_source(tmp_path: Path) -> tuple[Path, dict, dict]:
    row, roots = _row(tmp_path)
    source_root = tmp_path / "source"
    final = json.dumps({"scores": {name: 3 for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}, "evidence": {name: "fixture" for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}, "coverage": {name: True for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}}, separators=(",", ":"))
    events = b"".join(json.dumps(value, separators=(",", ":")).encode() + b"\n" for value in ({"type": "thread.started", "thread_id": "thread-1"}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": final}}, {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}))
    def invoke(**kwargs):
        kwargs["before_provider_attempt"](); responses = kwargs["output_dir"] / "responses"; responses.mkdir(exist_ok=True)
        message, event_path, stderr = responses / "batch-0001.attempt-0001.message.json", responses / "batch-0001.attempt-0001.events.jsonl", kwargs["output_dir"] / "raw-codex-stderr.bin"
        message.write_text(final, encoding="utf-8"); event_path.write_bytes(events); stderr.write_bytes(b"")
        return final, {"command": execution._expected_codex_command(kwargs["executable"], kwargs["output_dir"]), "reported": execution._strict_stderr_labels(b""), "provider_artifacts": {"codex_events": {"path": event_path.relative_to(kwargs["output_dir"]).as_posix(), "bytes": len(events), "sha256": execution._sha(events)}, "codex_stderr": {"path": stderr.name, "bytes": 0, "sha256": execution._sha(b"")}}}
    route = {"name": execution.SOL_ROUTE_NAME, "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True, "allowed_payload_classes": ["public_repo"], "codex_command": ["fixture"], "codex_command_identity": {"version": 1, "artifacts": []}, "cli_version_identity": {"version": 1, "artifacts": []}, "auth_status_identity": {"version": 1, "artifacts": []}, "codex_cli_version": "fixture", "command": ["python-fixture.exe", str(execution.CODEX_ADAPTER_PATH)], "command_identity": {"version": 1, "artifacts": []}, "cost_evidence": {"evidence_hash": "e" * 64, "checked_at": "2026-08-29T00:00:00Z", "expires_at": "2026-08-30T00:00:00Z"}, "auth_receipt_hash": "1" * 64, "timeout_seconds": 60}
    class Broker:
        def __init__(self, _root): pass
        def _load_registry_live(self): return {"version": 1, "routes": [route]}
        def _validate_route(self, *_args, **_kwargs): pass
    execution.prepare_only(output_root=source_root, cell_id=row["cell_id"], queue_root=tmp_path / "queue", broker_factory=Broker, authorization_acknowledgement_sha256="d" * 64, **roots)
    execution.execute_sol(output_root=source_root, cell_id=row["cell_id"], queue_root=tmp_path / "queue", broker_factory=Broker, call_codex=invoke, authorization_acknowledgement_sha256="d" * 64, allow_remote=True, **roots)
    return source_root, row, roots


def test_admission_replays_pinned_lifecycle_and_copies_exact_artifacts(tmp_path: Path) -> None:
    source, row, roots = _seed_source(tmp_path)
    source_inventory = admit._inventory(source / row["cell_id"])
    result = admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out", proof_path=tmp_path / "proof.json", cell_id=row["cell_id"], **roots)
    destination = Path(result["destination_root"])
    proof = json.loads((tmp_path / "proof.json").read_text(encoding="utf-8"))
    assert result["provider_calls_made"] == 0 and result["evidence_status"].endswith("unproven")
    assert admit._inventory(destination)["prompt-request.bin"] == source_inventory["prompt-request.bin"]
    assert admit._inventory(destination)["response-schema.json"] == source_inventory["response-schema.json"]
    assert admit._inventory(destination)["raw-codex-final-response.bin"] == source_inventory["raw-codex-final-response.bin"]
    assert admit._inventory(destination)["raw-codex-events.bin"] == source_inventory["raw-codex-events.bin"]
    assert admit._inventory(destination)["effective-settings.json"] == source_inventory["effective-settings.json"]
    assert proof["provider_attested"] is False and proof["deduplication_key"]["cell_id"] == row["cell_id"]
    assert admit._inventory(source / row["cell_id"]) == source_inventory


@pytest.mark.parametrize("mutator", ["identity", "tamper", "reparse", "partial"])
def test_admission_rejects_bad_or_unsafe_inputs(tmp_path: Path, mutator: str) -> None:
    source, row, roots = _seed_source(tmp_path)
    cell = source / row["cell_id"]
    if mutator == "identity":
        receipt = json.loads((cell / "execution-receipt.json").read_text(encoding="utf-8")); receipt["identity"]["session_id"] = "forged"; (cell / "execution-receipt.json").write_bytes(execution._canonical(receipt))
    elif mutator == "tamper":
        (cell / "raw-codex-final-response.bin").write_bytes(b"{}")
    elif mutator == "reparse":
        target = cell / "alias"
        try:
            target.symlink_to(cell / "prepared.json")
        except OSError:
            pytest.skip("symlink creation is unavailable on this Windows fixture host")
    else:
        (tmp_path / "out").mkdir()
    with pytest.raises(ValueError):
        admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out", proof_path=tmp_path / "proof.json", cell_id=row["cell_id"], **roots)


def test_admission_rejects_proof_collision_and_duplicate_prior_key(tmp_path: Path) -> None:
    source, row, roots = _seed_source(tmp_path)
    admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out", proof_path=tmp_path / "proof.json", cell_id=row["cell_id"], **roots)
    with pytest.raises(ValueError, match="existing output"):
        admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out2", proof_path=tmp_path / "proof.json", cell_id=row["cell_id"], **roots)
    with pytest.raises(ValueError, match="deduplication"):
        admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out3", proof_path=tmp_path / "proof3.json", cell_id=row["cell_id"], prior_proof_paths=[tmp_path / "proof.json"], **roots)
    (tmp_path / "skeletal-prior.json").write_bytes(admit._canonical({"study_id": admit.STUDY_ID, "kind": "sol_local_lifecycle_admission_proof"}))
    with pytest.raises(ValueError, match="prior proof"):
        admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out4", proof_path=tmp_path / "proof4.json", cell_id=row["cell_id"], prior_proof_paths=[tmp_path / "skeletal-prior.json"], **roots)


def test_prior_proof_rejects_self_consistent_rehashed_key_evasion(tmp_path: Path) -> None:
    source, row, roots = _seed_source(tmp_path)
    proof_path = tmp_path / "proof.json"
    first = admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out", proof_path=proof_path, cell_id=row["cell_id"], **roots)
    destination = Path(first["destination_root"])
    forged_key = {"cell_id": row["cell_id"], "contact_id": "forged-contact", "session_id": "forged-session", "request_sha256": "a" * 64, "final_response_sha256": "b" * 64}
    result_path = destination / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")); result["deduplication_key"] = forged_key
    result_path.write_bytes(admit._canonical(result))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["deduplication_key"] = forged_key
    proof["destination_result_sha256"] = _sha(result_path)
    proof["destination_inventory"] = admit._inventory(destination)
    proof_path.write_bytes(admit._canonical(proof))
    with pytest.raises(ValueError, match="deduplication key drifted"):
        admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out2", proof_path=tmp_path / "proof2.json", cell_id=row["cell_id"], prior_proof_paths=[proof_path], **roots)


def test_admission_rejects_changed_then_restored_source_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, row, roots = _seed_source(tmp_path)
    cell = source / row["cell_id"]
    before = admit._inventory(cell)
    original_copy = admit._copy_inventory
    def raced_copy(source_path: Path, destination: Path, inventory: dict) -> None:
        if source_path != cell:
            original_copy(source_path, destination, inventory)
            return
        prompt = source_path / "prompt-request.bin"
        original = prompt.read_bytes()
        prompt.write_bytes(b"changed-during-copy")
        try:
            original_copy(source_path, destination, inventory)
        finally:
            prompt.write_bytes(original)
    monkeypatch.setattr(admit, "_copy_inventory", raced_copy)
    with pytest.raises(ValueError, match="staged clone drifted"):
        admit.admit_local_lifecycle(source_execution_root=source, output_root=tmp_path / "out", proof_path=tmp_path / "proof.json", cell_id=row["cell_id"], **roots)
    assert admit._inventory(cell) == before
    assert not (tmp_path / "out").exists() and not (tmp_path / "proof.json").exists()


def test_cli_accepts_repeatable_prior_proofs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}
    def fake_admit(**kwargs):
        seen.update(kwargs)
        return {"accepted": True}
    monkeypatch.setattr(admit, "admit_local_lifecycle", fake_admit)
    assert admit.main(["--admit-local-lifecycle", "--source-execution-root", str(tmp_path / "source"), "--output-root", str(tmp_path / "out"), "--proof-path", str(tmp_path / "proof"), "--cell-id", "cell", "--frozen-successor-path", str(tmp_path / "frozen"), "--hanna-csv-path", str(tmp_path / "csv"), "--prior-proof", str(tmp_path / "one.json"), "--prior-proof", str(tmp_path / "two.json")]) == 0
    assert seen["prior_proof_paths"] == [tmp_path / "one.json", tmp_path / "two.json"]


def test_contract_and_pins_are_exact() -> None:
    assert _sha(EXEC_PACKAGE / "executor.py") == admit.EXEC_SHA256
    assert _sha(EXEC_PACKAGE / "study-contract.json") == admit.EXEC_CONTRACT_SHA256
    assert admit.contract()["admission"]["provider_attested"] is False
