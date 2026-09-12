from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_partial_successor.py"
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-wpb-sol-partial-successor-reconciliation-20260912-r1\reconciliation.json")
PENDING_TEST = ROOT / "tests/test_wpb_sol_pending_continuation.py"
SUPPORT = ROOT / "tests/test_hbq_human_alignment_wpb_compact_native_v1.py"


def load():
    return load_module(SOURCE, "wpb_partial_successor")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_two_prefix_cells_are_excluded_in_order_and_127_remain() -> None:
    value = load(); legacy, _strict = value._configured_legacy()
    resolution = legacy._resolution(legacy._frozen(), FREEZE_ROOT)
    ids = [row["cell_id"] for row in resolution["rows"]]
    assert len(ids) == 127 and not (set(ids) & set(value.PREFIX))
    pending, _strict = value._load_pending()._configured_legacy()
    prior = pending._resolution(pending._frozen(), FREEZE_ROOT)
    assert value.PREFIX[0] not in {row["cell_id"] for row in prior["rows"]}
    assert [row["cell_id"] for row in prior["rows"] if row["cell_id"] == value.PREFIX[1]] == [value.PREFIX[1]]


def test_source_drift_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    monkeypatch.setattr(value, "PENDING_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="source drifted"):
        value._load_pending()


def _support() -> tuple[Any, Any, Any]:
    pending_tests = load_module(PENDING_TEST, "wpb_partial_successor_pending_tests")
    support = load_module(SUPPORT, "wpb_partial_successor_support")
    return pending_tests, support, support.load(support.V12_TEST, "wpb_partial_successor_route")


def _write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def _campaign(value: Any, tmp_path: Path) -> tuple[Path, Path, dict[str, Any], Any, Any, Any]:
    pending_tests, support, route_support = _support()
    verifier, verifier_sha, review, review_sha, context = pending_tests.fixture(value, tmp_path)
    root, queue = tmp_path / "partial", tmp_path / "queue"; queue.mkdir()
    value.create_campaign(campaign_root=root, partial_reconciliation_path=RECONCILIATION,
                          expected_partial_reconciliation_sha256=__import__("hashlib").sha256(RECONCILIATION.read_bytes()).hexdigest(),
                          queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                          expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                          independent_review_path=review, expected_independent_review_sha256=review_sha,
                          freeze_verifier_path=verifier)
    return root, queue, context, verifier, support, route_support


def _prepared(value: Any, tmp_path: Path) -> tuple[dict[str, Any], Path, Path, dict[str, Any], Any, Any, Any, dict[str, Any]]:
    root, queue, context, verifier, support, route_support = _campaign(value, tmp_path)
    now = datetime.now(timezone.utc); route = route_support.sol_route()[0]
    route = {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                           "expires_at": (now + timedelta(minutes=30)).isoformat()}}
    cells = [item["cell_id"] for item in json.loads((root / "campaign.json").read_bytes())["cells"][:10]]
    legacy_review = tmp_path / "legacy-review.json"
    legacy_review_sha = _write(legacy_review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": __import__("hashlib").sha256((root / "campaign.json").read_bytes()).hexdigest(),
        "batch_number": 1, "cell_ids": cells, "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
        expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=__import__("hashlib").sha256(verifier.read_bytes()).hexdigest(),
        freeze_verifier_path=verifier, review_path=legacy_review, expected_review_sha256=legacy_review_sha,
        authorization_acknowledgement_sha256="a" * 64, broker_factory=lambda _queue: route_support.Broker(route))
    return prepared, root, queue, context, verifier, support, route_support, route


def test_synthetic_preparation_preserves_127_scope(tmp_path: Path) -> None:
    value = load(); prepared, root, _queue, _context, _verifier, _support_value, _route_support, _route = _prepared(value, tmp_path)
    assert len(prepared["prepared_cells"]) == 10
    assert not set(prepared["prepared_cells"]) & set(value.PREFIX)
    assert (root / "batches/0001/strict-native-schema.json").is_file()


def test_first_worker_failure_is_captured_once(tmp_path: Path) -> None:
    value = load(); _prepared_value, root, queue, context, verifier, _support_value, route_support, route = _prepared(value, tmp_path)
    material = value.review_material(campaign_root=root, batch_number=1); now = datetime.now(timezone.utc)
    review = tmp_path / "partial-review.json"; review_sha = _write(review, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    with pytest.raises(ValueError):
        value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=__import__("hashlib").sha256(verifier.read_bytes()).hexdigest(),
            freeze_verifier_path=verifier, batch_number=1, allow_remote=True, successor_review_path=review,
            expected_successor_review_sha256=review_sha, broker_factory=lambda _queue: route_support.Broker(route),
            call_codex=lambda **_kwargs: (_ for _ in ()).throw(ValueError("synthetic failure")))
    failure = json.loads((root / "batches/0001/first-worker-failure.json").read_bytes())
    assert failure["failure"]["error_type"] == "ValueError" and failure["automatic_resend_authorized"] is False


def test_full_synthetic_13_batch_joined_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    prepared, root, queue, context, verifier, support, route_support, route = _prepared(value, tmp_path)
    now = datetime.now(timezone.utc)
    verifier_sha = __import__("hashlib").sha256(verifier.read_bytes()).hexdigest()
    original = subprocess.run

    def run(command: list[str], **arguments: Any) -> subprocess.CompletedProcess[bytes]:
        if "input" not in arguments:
            return original(command, **arguments)
        output = Path(command[command.index("--cd") + 1])
        schema = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema.read_bytes())["required"] == ["A", "B", "observed_winner"]
        answer = support.answer(value._load_pending()._load_strict())
        final = json.dumps(answer, sort_keys=True, separators=(",", ":"))
        message = Path(command[command.index("--output-last-message") + 1])
        message.parent.mkdir(parents=True, exist_ok=True)
        message.write_text(final, encoding="utf-8")
        events = b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in (
            {"type": "thread.started", "thread_id": f"partial-{output.name}"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": final}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ))
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    campaign_sha = __import__("hashlib").sha256((root / "campaign.json").read_bytes()).hexdigest()

    def dispatch_and_settle(number: int, prepared_cells: list[str]) -> None:
        material = value.review_material(campaign_root=root, batch_number=number)
        review = tmp_path / f"partial-review-{number}.json"
        review_sha = _write(review, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        outcomes = value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
            freeze_verifier_path=verifier, batch_number=number, allow_remote=True, successor_review_path=review,
            expected_successor_review_sha256=review_sha, broker_factory=lambda _queue: route_support.Broker(route))
        settled = value.settle_batch(campaign_root=root, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
            freeze_verifier_path=verifier, batch_number=number)
        assert len(outcomes) == len(prepared_cells) and settled["status"] == "completed"

    dispatch_and_settle(1, prepared["prepared_cells"])
    cells = [item["cell_id"] for item in json.loads((root / "campaign.json").read_bytes())["cells"]]
    for number in range(2, 14):
        batch_cells = cells[(number - 1) * 10:number * 10]
        review = tmp_path / f"legacy-review-{number}.json"
        review_sha = _write(review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
            "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha, "batch_number": number,
            "cell_ids": batch_cells, "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
            "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        next_batch = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
            freeze_verifier_path=verifier, review_path=review, expected_review_sha256=review_sha,
            authorization_acknowledgement_sha256="a" * 64, broker_factory=lambda _queue: route_support.Broker(route))
        assert next_batch["prepared_cells"] == batch_cells
        dispatch_and_settle(number, batch_cells)
    report = value.report(campaign_root=root, partial_reconciliation_path=RECONCILIATION,
        expected_partial_reconciliation_sha256=__import__("hashlib").sha256(RECONCILIATION.read_bytes()).hexdigest(),
        freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
        expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier)
    assert report["status"] == "complete_batched_sol_campaign"
    assert report["measurement_count"] == 129 and report["new_measurement_count"] == 127
    assert report["preserved_completed_cells"] == list(value.PREFIX)
