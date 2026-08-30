from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import ModuleType

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-manifest-v1"
ADMISSION = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1"
manifest = load_module(PACKAGE / "generate.py", name="hanna_sol_lifecycle_manifest_v1")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proof(cell_id: str, ordinal: int, *, contact_id: str | None = None) -> dict:
    return {
        "cell_id": cell_id,
        "source_receipt_sha256": f"{ordinal:064x}",
        "destination_result_sha256": f"{ordinal + 100:064x}",
        "deduplication_key": {
            "cell_id": cell_id,
            "contact_id": contact_id or f"contact-{ordinal}",
            "session_id": f"session-{ordinal}",
            "request_sha256": f"{ordinal + 200:064x}",
            "final_response_sha256": f"{ordinal + 300:064x}",
        },
    }


def _fake_admission() -> ModuleType:
    module = ModuleType("fake_admission")
    module._stable_bytes = lambda path: Path(path).read_bytes()
    module._plain_ancestry = lambda *_args, **_kwargs: None
    module._load_execution = lambda: object()
    def validate(path: Path, **_kwargs) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    module._validate_prior_proof = validate
    def new_file(path: Path, raw: bytes) -> None:
        Path(path).write_bytes(raw)
    module._new_file = new_file
    module.contract = lambda: {"study_id": "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1"}
    return module


def _seed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, frozenset[str]]:
    cells = frozenset(f"v4-cell-{index:016x}" for index in range(manifest.EXPECTED_PROOF_COUNT))
    proofs = tmp_path / "proofs"; proofs.mkdir()
    for ordinal, cell_id in enumerate(sorted(cells)):
        (proofs / f"{ordinal:02}.json").write_bytes(manifest._canonical(_proof(cell_id, ordinal)))
    monkeypatch.setattr(manifest, "_load_admission", _fake_admission)
    monkeypatch.setattr(manifest, "_expected_cells", lambda *_args: cells)
    return proofs, cells


def test_manifest_pins_and_contract_are_exact() -> None:
    assert _sha(ADMISSION / "admit.py") == manifest.ADMISSION_SHA256
    assert _sha(ADMISSION / "study-contract.json") == manifest.ADMISSION_CONTRACT_SHA256
    assert manifest.TERMINAL_CELLS == {"v4-cell-2eb4f20b3db15aac", "v4-cell-2333370999fb84f3"}
    assert "aggregate" not in inspect.signature(manifest.build_manifest).parameters


def test_manifest_projects_only_authenticated_ids_hashes_and_ceiling(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proofs, cells = _seed(monkeypatch, tmp_path)
    result = manifest.build_manifest(proof_root=proofs, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "csv")
    assert set(result) == manifest.RESULT_FIELDS
    assert {entry["cell_id"] for entry in result["cells"]} == cells
    assert result["counts"] == {"admitted_original_sol_cells": 33, "provider_calls_made": 0}
    assert result["ceiling"]["native_endpoint_contact_cardinality"] == "unproven"
    assert "proofs" not in manifest._canonical(result).decode("utf-8")
    assert all(set(entry) == manifest.CELL_FIELDS for entry in result["cells"])


def test_manifest_rejects_partial_swapped_and_reused_proofs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proofs, cells = _seed(monkeypatch, tmp_path)
    (proofs / "32.json").unlink()
    with pytest.raises(ValueError, match="exactly 33"):
        manifest.build_manifest(proof_root=proofs, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "csv")
    (proofs / "32.json").write_bytes(manifest._canonical(_proof("v4-cell-not-original", 32, contact_id="contact-0")))
    with pytest.raises(ValueError, match="partial, swapped, terminal, or duplicated"):
        manifest.build_manifest(proof_root=proofs, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "csv")
    (proofs / "32.json").write_bytes(manifest._canonical(_proof(sorted(cells)[-1], 32, contact_id="contact-0")))
    with pytest.raises(ValueError, match="contact_id is reused"):
        manifest.build_manifest(proof_root=proofs, frozen_successor_path=tmp_path / "frozen", hanna_csv_path=tmp_path / "csv")


def test_live_full_replay_when_all_33_proofs_are_present() -> None:
    proof_root = Path.home() / "Documents" / "cwr-hanna-v4-sol-local-lifecycle-admissions-e5c50b1" / "proofs"
    if not proof_root.exists() or len(list(proof_root.glob("*.json"))) != manifest.EXPECTED_PROOF_COUNT:
        pytest.skip("live admission proof set is not complete")
    result = manifest.build_manifest(
        proof_root=proof_root,
        frozen_successor_path=Path.home() / "Documents" / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        hanna_csv_path=Path.home() / "Documents" / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
    )
    assert result["counts"]["admitted_original_sol_cells"] == 33
    committed = PACKAGE / "result.json"
    assert committed.read_bytes() == manifest._canonical(result)
    assert hashlib.sha256(committed.read_bytes()).hexdigest() == (
        "70f096138ee218c4410fc3ba469d087647d717a56eb28f731c5de15dff4a9c19"
    )
