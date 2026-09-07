from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_batched_execution.py"
SUPPORT = Path(__file__).with_name("test_hbq_human_alignment_wpb_compact_native_v1.py")
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
VERIFIER_SHA256 = "e" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context(value: Any) -> dict[str, Any]:
    resolution = value._frozen()._resolution(freeze_root=FREEZE_ROOT)
    return {
        "freeze_sha256": "f" * 64,
        "selection_frozen_at": "2026-09-07T00:00:00Z",
        "selected_profile": {"core": 1.0, "craft": 2.0, "form": 3.0},
        "schedule_sha256": resolution["schedule_sha256"],
        "source_bindings": {"synthetic_fixture": "preverified_producer_boundary"},
        "evidence_files": {"synthetic_fixture": "no_native_claim"},
        "native_measurement_count": 129,
    }


def _install_context(monkeypatch: pytest.MonkeyPatch, value: Any, context: dict[str, Any]) -> None:
    def verify(path: Path, expected: str, *, replay_native: bool) -> dict[str, Any]:
        assert path.name == "grok-selection-freeze.json" and expected == context["freeze_sha256"]
        return dict(context)
    monkeypatch.setattr(value, "_freeze_module", lambda expected: SimpleNamespace(verify_freeze=verify))


def _review(value: Any, path: Path, payload: dict[str, Any]) -> tuple[Path, str]:
    path.write_bytes(value.canonical(payload))
    return path, value.sha256(path.read_bytes())


def _route(route_support: Any, epoch: int) -> dict[str, Any]:
    route, _evidence = route_support.sol_route()
    route = {**route, "cost_evidence": dict(route["cost_evidence"])}
    now = datetime.now(timezone.utc)
    route["cost_evidence"].update({"checked_at": (now - timedelta(seconds=1)).isoformat(),
                                   "expires_at": (now + timedelta(minutes=30)).isoformat(),
                                   "evidence_hash": f"{epoch:064x}"})
    return route


def test_full_batched_aggregation_uses_real_frozen_sol_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(HELPER, "wpb_sol_batched_full_integration")
    support = load(SUPPORT, "wpb_sol_batched_full_integration_support")
    frozen = _context(value); _install_context(monkeypatch, value, frozen)
    campaign, queue = tmp_path / "external-campaign", tmp_path / "queue"; queue.mkdir()
    freeze_review, freeze_review_sha = _review(value, tmp_path / "freeze-review.json", {
        "format_version": 1, "kind": "wpb_grok_selection_freeze_independent_review",
        "freeze_sha256": frozen["freeze_sha256"], "freeze_verifier_sha256": VERIFIER_SHA256,
        "decision": "approved_wpb_grok_selection_freeze", "reviewed_at": "2026-09-07T00:00:00Z",
    })
    created = value.create_campaign(campaign_root=campaign, queue_root=queue, freeze_root=FREEZE_ROOT,
                                    freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                    expected_freeze_verifier_sha256=VERIFIER_SHA256, independent_review_path=freeze_review, expected_independent_review_sha256=freeze_review_sha)
    route_support = support.load(support.V12_TEST, "wpb_sol_batched_integration_route_support")
    resolution = value._frozen()._resolution(freeze_root=FREEZE_ROOT)
    contacts = support.Contacts()
    runner = support.sol_runner(value._frozen(), resolution["rows"], contacts)
    completed: set[str] = set()
    route_hashes: list[str] = []
    for epoch in range(1, 14):
        route = _route(route_support, epoch)
        pending = [str(row["cell_id"]) for row in resolution["rows"] if str(row["cell_id"]) not in completed]
        cell_ids = pending[:10]
        batch_review, batch_review_sha = _review(value, tmp_path / f"review-{epoch:04d}.json", {
            "format_version": 1, "kind": "approved_wpb_sol_batched_dispatch", "campaign_sha256": created["campaign_sha256"],
            "decision": "approved_wpb_sol_batched_dispatch", "batch_number": epoch, "cell_ids": cell_ids, "freeze_sha256": frozen["freeze_sha256"],
            "route_sha256": value.sha256(route), "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        prepared = value.prepare_next_batch(campaign_root=campaign, queue_root=queue, freeze_root=FREEZE_ROOT,
                                            freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                            expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                            review_path=batch_review, expected_review_sha256=batch_review_sha,
                                            authorization_acknowledgement_sha256="a" * 64,
                                            broker_factory=lambda _root, route=route: route_support.Broker(route))
        assert prepared["prepared_cells"] == cell_ids and len(cell_ids) == (9 if epoch == 13 else 10)
        outcomes = value.dispatch_batch(campaign_root=campaign, queue_root=queue, freeze_root=FREEZE_ROOT,
                                        freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                        expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                        batch_number=epoch, allow_remote=True,
                                        broker_factory=lambda _root, route=route: route_support.Broker(route), call_codex=runner)
        assert len(outcomes) == len(cell_ids)
        settled = value.settle_batch(campaign_root=campaign, freeze_root=FREEZE_ROOT,
                                     freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                     expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                     batch_number=epoch)
        assert settled["status"] == "completed" and settled["completed_cells"] == cell_ids
        completed.update(cell_ids); route_hashes.append(value.sha256(route))
    report = value.report(campaign_root=campaign, freeze_root=FREEZE_ROOT,
                          freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                          expected_freeze_verifier_sha256=VERIFIER_SHA256)
    assert len(completed) == len(contacts.calls) == len(set(contacts.calls)) == 129
    assert [len(json.loads((campaign / "batches" / f"{epoch:04d}" / "plan.json").read_bytes())["cell_ids"]) for epoch in range(1, 14)] == [10] * 12 + [9]
    assert len(set(route_hashes)) == len({epoch["route_sha256"] for epoch in report["route_epochs"]}) == 13
    assert report["measurement_count"] == len(report["native_receipt_bindings"]) == 129
    assert report["analysis"]["profile"]["multipliers"] == frozen["selected_profile"]
    final = campaign / "batches" / "0013"; missing = campaign / "batches" / "0013-missing"
    final.rename(missing)
    try:
        with pytest.raises(ValueError, match="batch directory is malformed"):
            value.report(campaign_root=campaign, freeze_root=FREEZE_ROOT,
                         freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                         expected_freeze_verifier_sha256=VERIFIER_SHA256)
    finally:
        missing.rename(final)
