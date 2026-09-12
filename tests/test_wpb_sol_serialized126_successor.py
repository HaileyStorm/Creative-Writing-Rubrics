from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1"
SOURCE = DIRECTORY / "sol_serialized126_successor.py"
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-wpb-sol-serialized126-reconciliation-20260912-r1\reconciliation.json")
PENDING_TEST = ROOT / "tests/test_wpb_sol_pending_continuation.py"
SUPPORT = ROOT / "tests/test_hbq_human_alignment_wpb_compact_native_v1.py"


def load(path: Path = SOURCE, name: str = "wpb_serialized126_successor") -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_three_completed_cells_are_excluded_in_order_and_126_remain() -> None:
    value = load(); legacy, _strict, _state = value._configured_legacy({})
    ids = [row["cell_id"] for row in legacy._resolution(legacy._frozen(), FREEZE_ROOT)["rows"]]
    assert len(ids) == 126 and not set(ids) & set(value.PREFIX)
    old = value._load_legacy(); partial, _strict = old._configured_legacy()
    assert [row["cell_id"] for row in partial._resolution(partial._frozen(), FREEZE_ROOT)["rows"]].count(value.PREFIX[2]) == 1


def test_wrong_helper_or_legacy_pin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); monkeypatch.setattr(value, "SERIALIZER_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="serializer source drifted"):
        value._load_serializer()
    monkeypatch.setattr(value, "LEGACY_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="legacy source drifted"):
        value._load_legacy()


def test_reconciliation_binds_three_prefix_and_immutable_inventory() -> None:
    value = load(); raw = RECONCILIATION.read_bytes()
    reconciliation, checked = value._verify_reconciliation(RECONCILIATION, hashlib.sha256(raw).hexdigest(), Path("C:/fresh"))
    assert checked == raw and reconciliation["completed_cells"] == list(value.PREFIX)
    assert reconciliation["remaining_logical_cells"] == 126 and reconciliation["automatic_resend_authorized"] is False


def test_actual_legacy_factory_installs_one_serialized_core_loader() -> None:
    value = load(); state: dict[str, Any] = {}; legacy, _strict, returned = value._configured_legacy(state)
    adapter = value._load_serializer(); v5 = legacy._load_exact(adapter.V5, adapter.V5_SHA256, "wpb_serialized126_v5")
    selection = v5._pinned_selection(); helper = selection._module(selection.SCHEMA_RECOVERY_HELPER, "wpb_serialized126_schema")
    barrier = threading.Barrier(10); failures: list[BaseException] = []; successes: list[None] = []

    def worker() -> None:
        try:
            barrier.wait(); helper._load_frozen_core(); successes.append(None)
        except BaseException as error:  # noqa: BLE001 - worker exceptions are assertion evidence.
            failures.append(error)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert returned is state and "frozen_core_lock" in state and len(successes) == 10 and failures == []


def _load_module(path: Path, name: str) -> Any:
    return load(path, name)


def _support() -> tuple[Any, Any, Any]:
    partial_tests = _load_module(PENDING_TEST, "wpb_serialized126_pending_tests")
    support = _load_module(SUPPORT, "wpb_serialized126_support")
    return partial_tests, support, support.load(support.V12_TEST, "wpb_serialized126_route")


def _write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_synthetic_prepare_dispatch_failure_and_settle_bind_new_scope(tmp_path: Path) -> None:
    value = load(); partial_tests, _support_value, route_support = _support()
    verifier, verifier_sha, review, review_sha, context = partial_tests.fixture(value._load_legacy(), tmp_path)
    root, queue = tmp_path / "serialized126", tmp_path / "queue"; queue.mkdir()
    value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION,
                          expected_reconciliation_sha256=hashlib.sha256(RECONCILIATION.read_bytes()).hexdigest(),
                          queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                          expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                          independent_review_path=review, expected_independent_review_sha256=review_sha,
                          freeze_verifier_path=verifier)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc); route = route_support.sol_route()[0]
    route = {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                           "expires_at": (now + timedelta(minutes=30)).isoformat()}}
    cells = [item["cell_id"] for item in json.loads((root / "campaign.json").read_bytes())["cells"][:10]]
    legacy_review = tmp_path / "legacy-review.json"
    legacy_review_sha = _write(legacy_review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": hashlib.sha256((root / "campaign.json").read_bytes()).hexdigest(),
        "batch_number": 1, "cell_ids": cells, "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
        expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier,
        review_path=legacy_review, expected_review_sha256=legacy_review_sha, authorization_acknowledgement_sha256="a" * 64,
        broker_factory=lambda _queue: route_support.Broker(route))
    assert len(prepared["prepared_cells"]) == 10 and not set(prepared["prepared_cells"]) & set(value.PREFIX)
    material = value.review_material(campaign_root=root, batch_number=1)
    review_path = tmp_path / "serialized-review.json"; review_sha = _write(review_path, {**material,
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    with pytest.raises(ValueError):
        value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier,
            batch_number=1, allow_remote=True, successor_review_path=review_path, expected_successor_review_sha256=review_sha,
            broker_factory=lambda _queue: route_support.Broker(route), call_codex=lambda **_kwargs: (_ for _ in ()).throw(ValueError("synthetic")))
    failure = json.loads((root / "batches/0001/serialized126-first-worker-failure.json").read_bytes())
    assert failure["failure"]["error_type"] == "ValueError" and failure["automatic_resend_authorized"] is False


def test_full_synthetic_13_batch_joined_129_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); pending_tests, support, route_support = _support()
    verifier, verifier_sha, review, review_sha, context = pending_tests.fixture(value._load_legacy(), tmp_path)
    root, queue = tmp_path / "serialized126-success", tmp_path / "queue"; queue.mkdir()
    reconciliation_sha = hashlib.sha256(RECONCILIATION.read_bytes()).hexdigest()
    value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, expected_reconciliation_sha256=reconciliation_sha,
                          queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                          expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                          independent_review_path=review, expected_independent_review_sha256=review_sha, freeze_verifier_path=verifier)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc); route = route_support.sol_route()[0]
    route = {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                           "expires_at": (now + timedelta(minutes=30)).isoformat()}}
    original = subprocess.run

    def run(command: list[str], **arguments: Any) -> subprocess.CompletedProcess[bytes]:
        if "input" not in arguments:
            return original(command, **arguments)
        output = Path(command[command.index("--cd") + 1]); schema = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema.read_bytes())["required"] == ["A", "B", "observed_winner"]
        answer = support.answer(value._load_legacy()._load_pending()._load_strict()); final = json.dumps(answer, sort_keys=True, separators=(",", ":"))
        message = Path(command[command.index("--output-last-message") + 1]); message.parent.mkdir(parents=True, exist_ok=True); message.write_text(final, encoding="utf-8")
        events = b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in (
            {"type": "thread.started", "thread_id": f"serialized126-{output.name}"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": final}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ))
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    campaign_sha = hashlib.sha256((root / "campaign.json").read_bytes()).hexdigest()

    def prepare(number: int, cells: list[str]) -> list[str]:
        legacy_review = tmp_path / f"legacy-review-{number}.json"
        legacy_review_sha = _write(legacy_review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
            "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha, "batch_number": number,
            "cell_ids": cells, "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
            "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        result = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier,
            review_path=legacy_review, expected_review_sha256=legacy_review_sha, authorization_acknowledgement_sha256="a" * 64,
            broker_factory=lambda _queue: route_support.Broker(route))
        assert result["prepared_cells"] == cells
        return result["prepared_cells"]

    def dispatch_and_settle(number: int, cells: list[str]) -> None:
        material = value.review_material(campaign_root=root, batch_number=number); review_path = tmp_path / f"serialized-review-{number}.json"
        review_sha = _write(review_path, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                          "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        outcomes = value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier,
            batch_number=number, allow_remote=True, successor_review_path=review_path, expected_successor_review_sha256=review_sha,
            broker_factory=lambda _queue: route_support.Broker(route))
        settled = value.settle_batch(campaign_root=root, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
            freeze_verifier_path=verifier, batch_number=number)
        assert len(outcomes) == len(cells) and settled["status"] == "completed"

    cells = [item["cell_id"] for item in json.loads((root / "campaign.json").read_bytes())["cells"]]
    dispatch_and_settle(1, prepare(1, cells[:10]))
    for number in range(2, 14):
        dispatch_and_settle(number, prepare(number, cells[(number - 1) * 10:number * 10]))
    report = value.report(campaign_root=root, reconciliation_path=RECONCILIATION, expected_reconciliation_sha256=reconciliation_sha,
                          freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                          expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier)
    assert report["status"] == "complete_batched_sol_campaign" and report["measurement_count"] == 129
    assert report["new_measurement_count"] == 126 and report["preserved_completed_cells"] == list(value.PREFIX)
