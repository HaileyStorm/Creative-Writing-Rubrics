from __future__ import annotations

from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1"
MANIFEST = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-reconcile-v1-52dc2157-e0b5c104\reconciliation-manifest.json")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
R4_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-heldout-exec-045ac9ba-de7fce66-r4")
COLLECTION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-heldout-exec-045ac9ba-de7fce66-r4-collection.json")
ADOPTION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-heldout-exec-045ac9ba-de7fce66-r4-adoption.json")
verifier = load_module(PACKAGE / "verifier.py", name="hanna_v4_heldout_verify")
analyze = load_module(PACKAGE / "analyze.py", name="hanna_v4_heldout_analyze_verify")


def common() -> dict:
    return {"collection_evidence_path": COLLECTION, "collection_root": R4_ROOT, "r4_adoption_path": ADOPTION, "reconciliation_manifest_path": MANIFEST, "frozen_successor_path": FROZEN, "hanna_csv_path": CSV}


@pytest.fixture(scope="module")
def frozen_schedule():
    return verifier.schedule(reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def test_grok_phase_does_not_open_sol_roots_and_phase_two_does(frozen_schedule, monkeypatch):
    sol_names = {row["cell_id"] for row in frozen_schedule["cells"] if row["route_name"] == "sol_validation"}
    opened: list[Path] = []
    original = verifier.stable_bytes
    def guarded(path: Path) -> bytes:
        path = Path(path)
        if path.is_relative_to(R4_ROOT) and path.relative_to(R4_ROOT).parts[0] in sol_names:
            opened.append(path); raise AssertionError("Grok phase opened a Sol root")
        return original(path)
    monkeypatch.setattr(verifier, "stable_bytes", guarded)
    phase = verifier.verify_grok_phase(**common())
    assert not opened and len(phase.projection["observations"]) == 44
    selection = verifier.select_grok(phase.projection)
    arbitrary = dict(selection)
    arbitrary["selected_candidate_id"] = analyze.BASELINE_ID
    with pytest.raises(ValueError, match="frozen Grok selection"):
        verifier.verify_sol_phase(grok_phase=phase, frozen_selection=arbitrary, collection_evidence_path=COLLECTION, collection_root=R4_ROOT, reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    assert not opened
    with pytest.raises(AssertionError, match="Sol root"):
        verifier.verify_sol_phase(grok_phase=phase, frozen_selection=selection, collection_evidence_path=COLLECTION, collection_root=R4_ROOT, reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def test_mutated_frozen_selection_is_rejected_before_sol_roots_open(monkeypatch):
    frozen = analyze.freeze_grok_selection(**common())
    frozen.selection["selected_candidate_id"] = analyze.BASELINE_ID
    opened: list[Path] = []
    original = frozen.verifier.stable_bytes

    def guarded(path: Path) -> bytes:
        path = Path(path)
        if path.is_relative_to(R4_ROOT) and path.relative_to(R4_ROOT).parts[0].startswith("heldout-cell-"):
            opened.append(path)
            raise AssertionError("Sol evidence opened")
        return original(path)

    monkeypatch.setattr(frozen.verifier, "stable_bytes", guarded)
    with pytest.raises(ValueError, match="mutated or substituted"):
        analyze.validate_sol_nonreversal(
            frozen=frozen,
            collection_evidence_path=COLLECTION,
            collection_root=R4_ROOT,
            reconciliation_manifest_path=MANIFEST,
            frozen_successor_path=FROZEN,
            hanna_csv_path=CSV,
        )
    assert not opened


def test_public_result_starts_from_evidence_and_reports_reversal():
    value = analyze.verify_and_analyze(**common())
    assert value["grok_selection"]["strict_grok_improvement"] is True
    assert value["result"]["gain_observed"] is False
    assert value["result"]["sol_validation"]["sol_evidence_ceiling"].endswith("unproven")


def test_self_hashed_synthetic_projection_is_not_an_evidence_api():
    with pytest.raises(ValueError, match="caller-created"):
        analyze.validate_sol_nonreversal(frozen={}, collection_evidence_path=COLLECTION, collection_root=R4_ROOT, reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    assert not hasattr(analyze, "analyze_projection")


def test_adapter_control_replay_rejects_request_output_and_identity_tampering(frozen_schedule):
    row = next(row for row in frozen_schedule["cells"] if row["route_name"] == "grok_primary")
    root = R4_ROOT / row["cell_id"]
    payload = verifier.stable_bytes(root / "payload.bin")
    prepared = verifier.object_at(root / "prepared.json", "prepared")
    evidence = verifier.object_at(root / "zero-charge-route-proof.json", "route proof")["route_evidence"]
    control = verifier.object_at(root / "adapter-control-envelope.json", "control")
    native = verifier.load(verifier.NATIVE_PATH, verifier.NATIVE_SHA256, "fixture_native")
    assert verifier._control(verifier.stable_bytes(root / "adapter-stdout.bin"), payload=payload, route=prepared["route"], evidence=evidence, native=native)[1] == control["result"]["output"]["scores"]
    control["result"]["output"]["scores"]["Relevance"] = 4.0
    with pytest.raises(ValueError, match="output hash"):
        verifier._control(verifier.adapter_canonical(control), payload=payload, route=prepared["route"], evidence=evidence, native=native)


def test_r4_adoption_requires_exact_immutable_manifest_and_copied_grok_trees(frozen_schedule, tmp_path: Path):
    adoption = verifier._adoption(ADOPTION, R4_ROOT, frozen_schedule)
    assert len(adoption["copied_grok_cells"]) == 44
    altered = tmp_path / "adoption.json"
    altered.write_bytes(verifier.stable_bytes(ADOPTION).replace(b'"provider_calls_made":0', b'"provider_calls_made":1', 1))
    with pytest.raises(ValueError, match="hash drifted"):
        verifier._adoption(altered, R4_ROOT, frozen_schedule)


def test_adoption_inventory_digest_binds_names_sizes_and_bytes(frozen_schedule, tmp_path: Path):
    adoption = verifier._adoption(ADOPTION, R4_ROOT, frozen_schedule)
    copied = adoption["copied_grok_cells"][0]
    source, replica = R4_ROOT / copied["cell_id"], tmp_path / copied["cell_id"]
    replica.mkdir()
    for entry in source.iterdir():
        (replica / entry.name).write_bytes(verifier.stable_bytes(entry))
    assert verifier._inventory_digest(replica) == copied["r4_inventory_sha256"]
    (replica / "payload.bin").write_bytes(b"tampered")
    assert verifier._inventory_digest(replica) != copied["r4_inventory_sha256"]
