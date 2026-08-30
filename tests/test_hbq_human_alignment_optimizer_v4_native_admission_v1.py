from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-admission-v1"
admit = load_module(PACKAGE / "admit.py", name="hanna_v4_native_admission_v1")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
AUTH = "d" * 64


def route() -> dict:
    return {
        "name": "grok-build-grok-4.6", "model": "grok-4.6", "adapter": "grok_exec",
        "provider": "xai_grok_build", "destination": "xai_grok_build_subscription",
        "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy",
        "reasoning_effort": "high", "reported_model": "grok-4.6-build", "identity_evidence": "requested_only",
        "allowed_payload_classes": ["public_repo"], "grok_command": ["grok-fixture.exe"],
        "grok_command_identity": {"version": 1, "artifacts": [{"path": "grok-fixture.exe", "sha256": "b" * 64}]},
        "cli_version_identity": {"version": 1, "artifacts": [{"path": "grok-fixture.exe", "sha256": "b" * 64}]},
        "grok_cli_version": "grok fixture 1.0", "cost_evidence": {"evidence_hash": "a" * 64},
        "subscription_receipt_hash": "c" * 64, "timeout_seconds": 60,
    }


class Broker:
    def __init__(self, _root: Path):
        self.candidate = route()

    def _load_registry_live(self):
        return {"version": 1, "routes": [self.candidate]}

    def _validate_route(self, *_args, **_kwargs):
        return None


def broker(_path: Path) -> Broker:
    return Broker(_path)


@pytest.fixture(scope="module")
def execution():
    return admit._load_pinned()[1]


@pytest.fixture(scope="module")
def predecessor():
    return admit._load_pinned()[0]


@pytest.fixture(scope="module")
def grok_row(predecessor):
    schedule = predecessor.derive_schedule(**ROOTS)
    return next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary")


def completed_source(execution, grok_row: dict, tmp_path: Path) -> Path:
    source = tmp_path / "exec-source"
    execution.prepare_only(output_root=source, cell_id=grok_row["cell_id"], queue_root=tmp_path / "queue",
                           frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"],
                           authorization_acknowledgement_sha256=AUTH, broker_factory=broker)

    def fake_call(**kwargs):
        kwargs["before_provider_attempt"]()
        root = kwargs["output_dir"]
        responses = root / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8")
        envelope = execution._canonical({
            "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1,
            "sessionId": "session-1", "requestId": "request-1", "structuredOutput": {"ok": True},
        })
        envelope_path = responses / "batch-0001.attempt-0001.grok.envelope.json"
        envelope_path.write_bytes(envelope)
        return "{}", {
            "cli_version": "grok fixture 1.0", "requested": {"model": "grok-4.6", "reasoning_effort": "high"},
            "reported": {"provider": "grok", "model": "grok-4.6-build"},
            "session_id_sha256": execution._sha(b"session-1"), "request_id_sha256": execution._sha(b"request-1"),
            "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli",
            "provider_artifacts": {"grok_envelope": {"path": envelope_path.relative_to(root).as_posix(),
                                                         "bytes": len(envelope), "sha256": execution._sha(envelope)}},
        }

    result = execution.execute_grok(output_root=source, cell_id=grok_row["cell_id"], queue_root=tmp_path / "queue",
                                    frozen_successor_path=ROOTS["frozen_successor_path"], hanna_csv_path=ROOTS["hanna_csv_path"],
                                    authorization_acknowledgement_sha256=AUTH, allow_remote=True,
                                    broker_factory=broker, call_grok=fake_call)
    assert result["native_contact_proven"] is True
    return source


def admit_one(execution, grok_row: dict, tmp_path: Path):
    source = completed_source(execution, grok_row, tmp_path)
    output = tmp_path / "admitted"
    proof = tmp_path / "admission-proof.json"
    source_before = admit._tree_inventory(source / grok_row["cell_id"])
    result = admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                        cell_id=grok_row["cell_id"], **ROOTS)
    return source, output, proof, source_before, result


def test_contract_and_pins_are_exact_and_no_dspy_optuna_runtime_imports() -> None:
    assert admit.contract()["native_exec"]["executor_sha256"] == "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
    assert admit._sha(admit._stable_bytes(admit.EXEC_PATH)) == admit.EXEC_SHA256
    names = {node.names[0].name.split(".")[0] for node in ast.walk(ast.parse((PACKAGE / "admit.py").read_text(encoding="utf-8")))
             if isinstance(node, ast.Import)}
    names |= {node.module.split(".")[0] for node in ast.walk(ast.parse((PACKAGE / "admit.py").read_text(encoding="utf-8")))
              if isinstance(node, ast.ImportFrom) and node.module}
    assert {"dspy", "optuna"}.isdisjoint(names)


def test_admission_uses_internal_exec_verifier_preserves_source_and_creates_exact_settled_shape(execution, predecessor, grok_row, tmp_path: Path, monkeypatch) -> None:
    called = []
    original = predecessor._validate_persisted_result
    monkeypatch.setattr(predecessor, "_validate_persisted_result", lambda *args, **kwargs: (called.append(kwargs["inventory_state"]), original(*args, **kwargs))[1])
    original_loader = admit._load_pinned
    monkeypatch.setattr(admit, "_load_pinned", lambda: (predecessor, execution))
    source, output, proof, source_before, result = admit_one(execution, grok_row, tmp_path)
    assert result["provider_calls_made"] == 0
    destination = output / grok_row["cell_id"]
    assert {path.name for path in destination.iterdir()} == admit.DESTINATION_FILES
    assert called == ["native_returned_unprojected", "native_returned_unprojected"]
    assert admit._tree_inventory(source / grok_row["cell_id"]) == source_before
    proof_value = json.loads(proof.read_text(encoding="utf-8"))
    assert proof_value["source_exec_executor_sha256"] == admit.EXEC_SHA256
    assert proof_value["destination_inventory"]["native-request.bin"]["sha256"] == grok_row["task_payload_sha256"]
    assert admit._load_pinned is not original_loader


def test_existing_destination_or_proof_is_never_resumed_or_overwritten(execution, grok_row, tmp_path: Path) -> None:
    source, output, proof, _before, _result = admit_one(execution, grok_row, tmp_path)
    original = proof.read_bytes()
    with pytest.raises(ValueError, match="refuses existing"):
        admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                   cell_id=grok_row["cell_id"], **ROOTS)
    assert proof.read_bytes() == original


@pytest.mark.parametrize("mutation", ["relabel", "response", "orphan"])
def test_source_relabel_mutation_and_orphan_are_rejected(execution, grok_row, tmp_path: Path, mutation: str) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    cell = source / grok_row["cell_id"]
    if mutation == "relabel":
        receipt = json.loads((cell / "execution-receipt.json").read_text(encoding="utf-8"))
        receipt["cell_id"] = "v4-cell-relabelled"
        (cell / "execution-receipt.json").write_bytes(execution._canonical(receipt))
    elif mutation == "response":
        (cell / "raw-grok-envelope.bin").write_bytes(b"{}")
    else:
        (cell / "orphan.bin").write_bytes(b"orphan")
    with pytest.raises(ValueError):
        admit.admit_completed_grok(source_execution_root=source, output_root=tmp_path / f"out-{mutation}",
                                   proof_path=tmp_path / f"proof-{mutation}.json", cell_id=grok_row["cell_id"],
                                   **ROOTS)


def test_exact_source_clone_is_same_evidence_and_proof_binds_deduplication_key(execution, grok_row, tmp_path: Path) -> None:
    import shutil
    source = completed_source(execution, grok_row, tmp_path)
    clone = tmp_path / "exact-clone"
    shutil.copytree(source, clone)
    first = admit.admit_completed_grok(source_execution_root=source, output_root=tmp_path / "first",
                                       proof_path=tmp_path / "first-proof.json", cell_id=grok_row["cell_id"], **ROOTS)
    second = admit.admit_completed_grok(source_execution_root=clone, output_root=tmp_path / "second",
                                        proof_path=tmp_path / "second-proof.json", cell_id=grok_row["cell_id"], **ROOTS)
    first_key = json.loads(Path(first["proof_path"]).read_text(encoding="utf-8"))["deduplication_key"]
    second_key = json.loads(Path(second["proof_path"]).read_text(encoding="utf-8"))["deduplication_key"]
    assert first_key == second_key


def test_overlapping_paths_reject_before_touching_source(execution, grok_row, tmp_path: Path) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    before = admit._tree_inventory(source / grok_row["cell_id"])
    with pytest.raises(ValueError, match="must not overlap"):
        admit.admit_completed_grok(source_execution_root=source, output_root=source / "forbidden-output",
                                   proof_path=tmp_path / "proof.json", cell_id=grok_row["cell_id"], **ROOTS)
    with pytest.raises(ValueError, match="must not overlap"):
        admit.admit_completed_grok(source_execution_root=source, output_root=tmp_path / "output",
                                   proof_path=source / "forbidden-proof.json", cell_id=grok_row["cell_id"], **ROOTS)
    assert admit._tree_inventory(source / grok_row["cell_id"]) == before


def test_historical_admission_never_consults_live_broker_or_queue(execution, predecessor, grok_row, tmp_path: Path, monkeypatch) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    monkeypatch.setattr(execution, "validate_live_grok_route", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("live route consulted")))
    monkeypatch.setattr(admit, "_load_pinned", lambda: (predecessor, execution))
    result = admit.admit_completed_grok(source_execution_root=source, output_root=tmp_path / "out",
                                        proof_path=tmp_path / "proof.json", cell_id=grok_row["cell_id"], **ROOTS)
    assert result["accepted"] is True and result["provider_calls_made"] == 0


def test_contract_bytes_mutation_is_rejected(monkeypatch) -> None:
    original = admit._stable_bytes
    def mutated(path: Path) -> bytes:
        raw = original(path)
        return raw + b" " if Path(path) == admit.CONTRACT_PATH else raw
    monkeypatch.setattr(admit, "_stable_bytes", mutated)
    with pytest.raises(ValueError, match="contract identity drifted"):
        admit.contract()


def test_verified_loader_compiles_the_exact_verified_buffers(monkeypatch) -> None:
    original_read = admit._stable_bytes
    observed = []
    def observe(path: Path) -> bytes:
        raw = original_read(path)
        if Path(path) in {admit.EXEC_PATH, admit.PREDECESSOR_PATH}:
            observed.append((Path(path), raw))
        return raw
    original_load = admit._load_verified_buffer
    def load(path: Path, raw: bytes, name: str):
        assert any(candidate == path and candidate_raw == raw for candidate, candidate_raw in observed)
        return original_load(path, raw, name)
    monkeypatch.setattr(admit, "_stable_bytes", observe)
    monkeypatch.setattr(admit, "_load_verified_buffer", load)
    predecessor, execution = admit._load_pinned()
    assert predecessor.STUDY_ID.endswith("subscription-v1") and execution.STUDY_ID.endswith("exec-v1")


def test_staging_failure_leaves_no_destination_or_proof(execution, grok_row, tmp_path: Path, monkeypatch) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    original = admit._new_file
    calls = []
    def fail_after_two(path: Path, value: bytes) -> None:
        calls.append(path)
        if len(calls) == 3:
            raise RuntimeError("fixture staging failure")
        original(path, value)
    monkeypatch.setattr(admit, "_new_file", fail_after_two)
    output, proof = tmp_path / "out", tmp_path / "proof.json"
    with pytest.raises(RuntimeError, match="staging failure"):
        admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                   cell_id=grok_row["cell_id"], **ROOTS)
    assert not output.exists() and not proof.exists()
    assert not list(tmp_path.glob(".*.admission-stage-*"))


def test_proof_publication_race_never_replaces_concurrent_proof(execution, grok_row, tmp_path: Path, monkeypatch) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    output, proof = tmp_path / "out", tmp_path / "proof.json"
    original = admit._new_file
    def race(path: Path, value: bytes) -> None:
        if path == proof:
            proof.write_bytes(b"concurrent-proof")
        original(path, value)
    monkeypatch.setattr(admit, "_new_file", race)
    with pytest.raises(RuntimeError, match="requires reconciliation"):
        admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                   cell_id=grok_row["cell_id"], **ROOTS)
    assert proof.read_bytes() == b"concurrent-proof" and (output / grok_row["cell_id"]).exists()


def test_changed_published_destination_is_left_for_reconciliation(execution, grok_row, tmp_path: Path, monkeypatch) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    output, proof = tmp_path / "out", tmp_path / "proof.json"
    original = admit._new_file
    def race(path: Path, value: bytes) -> None:
        if path == proof:
            (output / grok_row["cell_id"] / "native-response.bin").write_bytes(b"concurrent-change")
            proof.write_bytes(b"concurrent-proof")
        original(path, value)
    monkeypatch.setattr(admit, "_new_file", race)
    with pytest.raises(RuntimeError, match="requires reconciliation"):
        admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                   cell_id=grok_row["cell_id"], **ROOTS)
    assert (output / grok_row["cell_id"] / "native-response.bin").read_bytes() == b"concurrent-change"
    assert proof.read_bytes() == b"concurrent-proof"


def test_prepublication_concurrent_destination_file_is_preserved_for_reconciliation(execution, grok_row, tmp_path: Path, monkeypatch) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    output, proof = tmp_path / "out", tmp_path / "proof.json"
    original = admit._new_file
    destination = output / grok_row["cell_id"]
    def race(path: Path, value: bytes) -> None:
        if path == destination / "native-response.bin":
            (destination / "concurrent.bin").write_bytes(b"concurrent-prepublication")
        original(path, value)
    monkeypatch.setattr(admit, "_new_file", race)
    with pytest.raises(RuntimeError, match="requires reconciliation"):
        admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                   cell_id=grok_row["cell_id"], **ROOTS)
    assert (destination / "concurrent.bin").read_bytes() == b"concurrent-prepublication"
    assert not proof.exists() and not list(tmp_path.glob(".*.admission-stage-*"))


def test_output_root_reservation_never_replaces_an_empty_racer(execution, grok_row, tmp_path: Path, monkeypatch) -> None:
    source = completed_source(execution, grok_row, tmp_path)
    output, proof = tmp_path / "out", tmp_path / "proof.json"
    original = admit._plain_inventory
    raced = False
    def reserve_race(root: Path, expected=None):
        nonlocal raced
        value = original(root, expected)
        if not raced and root.parent.name.startswith(".out.admission-stage-"):
            output.mkdir()
            raced = True
        return value
    monkeypatch.setattr(admit, "_plain_inventory", reserve_race)
    with pytest.raises(FileExistsError):
        admit.admit_completed_grok(source_execution_root=source, output_root=output, proof_path=proof,
                                   cell_id=grok_row["cell_id"], **ROOTS)
    assert output.exists() and not list(output.iterdir()) and not proof.exists()
    assert not list(tmp_path.glob(".*.admission-stage-*"))


def test_publication_does_not_use_replace() -> None:
    assert "os.replace" not in (PACKAGE / "admit.py").read_text(encoding="utf-8")
