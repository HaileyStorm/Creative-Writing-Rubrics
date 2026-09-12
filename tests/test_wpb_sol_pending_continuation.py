from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_pending_continuation.py"
SUPPORT = ROOT / "tests/test_hbq_human_alignment_wpb_compact_native_v1.py"
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-wpb-sol-strict-batch01-reconciliation-20260910-r1/reconciliation.json")


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(value: Any, tmp_path: Path, *, mixed_v5: bool = False) -> tuple[Path, str, Path, str, dict[str, Any]]:
    resolution = value._configured_legacy()[0]._frozen()._resolution(freeze_root=FREEZE_ROOT)
    freeze = tmp_path / "freeze.json"
    freeze.write_bytes(b"fixture-freeze\n")
    context = {"freeze_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(), "selection_frozen_at": "2026-09-07T00:00:00Z",
               "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
               "schedule_sha256": resolution["schedule_sha256"], "source_bindings": {"fixture": "continuation"}}
    if mixed_v5:
        context["mixed_v5_selection_context"] = {"fixture": "mixed-v5"}
    else:
        context.update({"evidence_files": {"fixture": "continuation"}, "native_measurement_count": 129})
    verifier = tmp_path / "fixture-verifier.py"
    replay_log = tmp_path / "replay-native.jsonl"
    profile = tmp_path / "selected-profile.json"
    write(profile, context["selected_profile"])
    method = "verify_freeze_context" if mixed_v5 else "verify_freeze"
    validator = "\ndef validate_mixed_context(context):\n    return context\n" if mixed_v5 else ""
    verifier.write_text("import hashlib\nimport json\nfrom pathlib import Path\n\nREPLAY_LOG = Path(" + repr(str(replay_log)) + ")\n"
                        "PROFILE = Path(" + repr(str(profile)) + ")\nCONTEXT = " + repr(context) + "\n\ndef " + method + "(_path, _expected, *, replay_native):\n"
                        "    with REPLAY_LOG.open('a', encoding='ascii') as handle:\n"
                        "        handle.write(str(replay_native) + '\\n')\n"
                        "    if hashlib.sha256(Path(_path).read_bytes()).hexdigest() != _expected:\n"
                        "        raise ValueError('fixture freeze drifted')\n"
                        "    return {**CONTEXT, 'selected_profile': json.loads(PROFILE.read_text(encoding='utf-8'))}" + validator + "\n", encoding="utf-8")
    verifier_sha = hashlib.sha256(verifier.read_bytes()).hexdigest()
    review_value = {"format_version": 1, "kind": "wpb_grok_selection_freeze_independent_review",
                    "decision": "approved_wpb_grok_selection_freeze", "freeze_sha256": context["freeze_sha256"],
                    "freeze_verifier_sha256": verifier_sha, "reviewed_at": "2026-09-07T00:00:00Z"}
    if mixed_v5:
        review_value.update({"freeze_verifier_path": str(verifier.resolve()), "freeze_context_kind": "mixed_v5",
                             "mixed_v5_selection_context_sha256": value.sha256(context["mixed_v5_selection_context"]),
                             "freeze_source_bindings_sha256": value.sha256(context["source_bindings"])})
    review = tmp_path / "freeze-review.json"
    review_sha = write(review, review_value)
    return verifier, verifier_sha, review, review_sha, context


def test_fresh_campaign_excludes_only_admitted_prefix_and_requires_full_replay(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_pending_continuation_create")
    verifier, verifier_sha, review, review_sha, context = fixture(value, tmp_path)
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    created = value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue,
                                    freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                                    expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                                    independent_review_path=review, expected_independent_review_sha256=review_sha,
                                    freeze_verifier_path=verifier)
    campaign = json.loads((root / "campaign.json").read_bytes())
    ids = [cell["cell_id"] for cell in campaign["cells"]]
    assert created["logical_cells"] == len(ids) == 128
    assert "wpb-pair-wpb-en-0052" not in ids
    manifest = json.loads((root / "pending-continuation-manifest.json").read_bytes())
    assert created["full_selection_verification"] == "native_replay"
    assert manifest["full_selection_verification"] == "frozen_verifier_required_on_every_lifecycle_stage"
    assert manifest["selection_context_sha256"] == value.sha256(context)
    assert not (root / "full-selection-verification-receipt.json").exists()


def test_mixed_v5_freeze_uses_the_real_six_field_context_shape(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_pending_continuation_mixed_v5")
    verifier, verifier_sha, review, review_sha, context = fixture(value, tmp_path, mixed_v5=True)
    assert set(context) == {"freeze_sha256", "selection_frozen_at", "selected_profile", "schedule_sha256",
                            "source_bindings", "mixed_v5_selection_context"}
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    created = value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue,
                                    freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                                    expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                                    independent_review_path=review, expected_independent_review_sha256=review_sha,
                                    freeze_verifier_path=verifier, mixed_v5_freeze=True)
    campaign = json.loads((root / "campaign.json").read_bytes())
    assert created["logical_cells"] == 128
    assert campaign["freeze_context_kind"] == "mixed_v5"
    assert campaign["mixed_v5_selection_context_sha256"] == value.sha256(context["mixed_v5_selection_context"])


def test_prepare_is_bounded_and_full_replay_verifier_drift_prevents_route_contact(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_pending_continuation_prepare")
    verifier, verifier_sha, review, review_sha, context = fixture(value, tmp_path)
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue, freeze_root=FREEZE_ROOT,
                          freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                          expected_freeze_verifier_sha256=verifier_sha, independent_review_path=review,
                          expected_independent_review_sha256=review_sha, freeze_verifier_path=verifier)
    support = load(SUPPORT, "wpb_pending_continuation_route")
    route = support.load(support.V12_TEST, "wpb_pending_continuation_route_support").sol_route()[0]
    now = datetime.now(timezone.utc)
    route = {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                           "expires_at": (now + timedelta(minutes=30)).isoformat()}}
    campaign_sha = hashlib.sha256((root / "campaign.json").read_bytes()).hexdigest()
    ids = [cell["cell_id"] for cell in json.loads((root / "campaign.json").read_bytes())["cells"][:10]]
    dispatch_review = tmp_path / "dispatch-review.json"
    dispatch_review_sha = write(dispatch_review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha, "batch_number": 1, "cell_ids": ids,
        "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
        freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
        expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier, review_path=dispatch_review,
        expected_review_sha256=dispatch_review_sha, authorization_acknowledgement_sha256="a" * 64,
        broker_factory=lambda _queue: support.load(support.V12_TEST, "wpb_pending_continuation_broker").Broker(route))
    assert len(prepared["prepared_cells"]) == 10
    projection = json.loads((root / "batches/0001/strict-schema-projection.json").read_bytes())
    assert set(projection["actual_commands"]) == set(prepared["prepared_cells"])
    assert (tmp_path / "replay-native.jsonl").read_text(encoding="ascii").splitlines() == ["True", "False"]
    (tmp_path / "freeze.json").write_bytes(b"drifted-freeze\n")
    with pytest.raises(ValueError, match="freeze"):
        value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
            freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
            expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier, review_path=dispatch_review,
            expected_review_sha256=dispatch_review_sha, authorization_acknowledgement_sha256="a" * 64,
            broker_factory=lambda _queue: support.load(support.V12_TEST, "wpb_pending_continuation_broker_2").Broker(route))


def test_default_v3_process_path_uses_strict_schema_and_settles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(SOURCE, "wpb_pending_continuation_dispatch")
    verifier, verifier_sha, review, review_sha, context = fixture(value, tmp_path)
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue, freeze_root=FREEZE_ROOT,
                          freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                          expected_freeze_verifier_sha256=verifier_sha, independent_review_path=review,
                          expected_independent_review_sha256=review_sha, freeze_verifier_path=verifier)
    support = load(SUPPORT, "wpb_pending_continuation_dispatch_support")
    route_support = support.load(support.V12_TEST, "wpb_pending_continuation_dispatch_route")
    now = datetime.now(timezone.utc)
    route = route_support.sol_route()[0]
    route = {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                           "expires_at": (now + timedelta(minutes=30)).isoformat()}}
    campaign_sha = hashlib.sha256((root / "campaign.json").read_bytes()).hexdigest()
    ids = [cell["cell_id"] for cell in json.loads((root / "campaign.json").read_bytes())["cells"][:10]]
    legacy_review = tmp_path / "legacy-review.json"
    legacy_review_sha = write(legacy_review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha, "batch_number": 1, "cell_ids": ids,
        "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
        freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
        expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier, review_path=legacy_review,
        expected_review_sha256=legacy_review_sha, authorization_acknowledgement_sha256="a" * 64,
        broker_factory=lambda _queue: route_support.Broker(route))
    material = value.review_material(campaign_root=root, batch_number=1)
    continuation_review = tmp_path / "continuation-review.json"
    continuation_review_sha = write(continuation_review, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    original = subprocess.run

    def run(command: list[str], **arguments: Any) -> subprocess.CompletedProcess[bytes]:
        if "input" not in arguments:
            return original(command, **arguments)
        output = Path(command[command.index("--cd") + 1])
        schema = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema.read_bytes())["required"] == ["A", "B", "observed_winner"]
        answer = support.answer(value._load_strict())
        final = json.dumps(answer, sort_keys=True, separators=(",", ":"))
        message = Path(command[command.index("--output-last-message") + 1])
        message.parent.mkdir(parents=True, exist_ok=True)
        message.write_text(final, encoding="utf-8")
        events = b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in (
            {"type": "thread.started", "thread_id": f"continuation-{output.name}"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": final}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ))
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    outcomes = value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
        expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
        freeze_verifier_path=verifier, batch_number=1, allow_remote=True, continuation_review_path=continuation_review,
        expected_continuation_review_sha256=continuation_review_sha, broker_factory=lambda _queue: route_support.Broker(route))
    settled = value.settle_batch(campaign_root=root, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
        expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
        freeze_verifier_path=verifier, batch_number=1)
    assert len(outcomes) == len(prepared["prepared_cells"]) == 10
    assert settled["status"] == "completed"
    for number in range(2, 14):
        start = (number - 1) * 10
        batch_ids = [cell["cell_id"] for cell in json.loads((root / "campaign.json").read_bytes())["cells"][start:start + 10]]
        legacy_review = tmp_path / f"legacy-review-{number}.json"
        legacy_review_sha = write(legacy_review, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
            "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha, "batch_number": number,
            "cell_ids": batch_ids, "freeze_sha256": context["freeze_sha256"], "route_sha256": value.sha256(route),
            "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
            freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
            expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier, review_path=legacy_review,
            expected_review_sha256=legacy_review_sha, authorization_acknowledgement_sha256="a" * 64,
            broker_factory=lambda _queue: route_support.Broker(route))
        assert prepared["batch_number"] == number and prepared["prepared_cells"] == batch_ids
        material = value.review_material(campaign_root=root, batch_number=number)
        continuation_review = tmp_path / f"continuation-review-{number}.json"
        continuation_review_sha = write(continuation_review, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        outcomes = value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
            freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
            expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier, batch_number=number, allow_remote=True,
            continuation_review_path=continuation_review, expected_continuation_review_sha256=continuation_review_sha,
            broker_factory=lambda _queue: route_support.Broker(route))
        settled = value.settle_batch(campaign_root=root, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
            expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
            freeze_verifier_path=verifier, batch_number=number)
        assert len(outcomes) == len(batch_ids) and settled["status"] == "completed"
    predecessor_root = Path(json.loads(RECONCILIATION.read_bytes())["campaign_root"])
    report = value.report(campaign_root=root, predecessor_root=predecessor_root, reconciliation_path=RECONCILIATION,
                          freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                          expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                          freeze_verifier_path=verifier)
    assert report["status"] == "complete_batched_sol_campaign"
    assert report["measurement_count"] == 129 and report["new_measurement_count"] == 128
    write(tmp_path / "selected-profile.json", {"core": 2.0, "craft": 1.0, "form": 1.0})
    with pytest.raises(ValueError, match="frozen selection context differs"):
        value.report(campaign_root=root, predecessor_root=predecessor_root, reconciliation_path=RECONCILIATION,
                     freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                     expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                     freeze_verifier_path=verifier)


def test_precontact_failure_records_bounded_diagnostics_without_launch(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_pending_continuation_failure")
    verifier, verifier_sha, review, review_sha, context = fixture(value, tmp_path)
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue, freeze_root=FREEZE_ROOT,
                          freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                          expected_freeze_verifier_sha256=verifier_sha, independent_review_path=review,
                          expected_independent_review_sha256=review_sha, freeze_verifier_path=verifier)
    continuation_review = tmp_path / "continuation-review.json"
    continuation_review_sha = write(continuation_review, {})
    with pytest.raises(ValueError, match="strict schema projection"):
        value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                             freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                             expected_freeze_verifier_sha256=verifier_sha, freeze_verifier_path=verifier, batch_number=1,
                             allow_remote=True, continuation_review_path=continuation_review,
                             expected_continuation_review_sha256=continuation_review_sha, broker_factory=lambda _queue: None)
    diagnostic = json.loads((root / "batches/0001/local-dispatch-failure.json").read_bytes())
    assert diagnostic["launch_intent_exists"] is False and diagnostic["process_receipt_exists"] is False
    assert diagnostic["automatic_resend_authorized"] is False
    assert diagnostic["failure"]["error_type"] == "ValueError"
    assert set(diagnostic["failure"]) == {"error_type", "source_function", "source_line", "cause_type"}


def test_report_rejects_a_different_valid_selection_context_before_score_analysis(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_pending_continuation_report_context")
    verifier, verifier_sha, review, review_sha, context = fixture(value, tmp_path)
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    value.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue, freeze_root=FREEZE_ROOT,
                          freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                          expected_freeze_verifier_sha256=verifier_sha, independent_review_path=review,
                          expected_independent_review_sha256=review_sha, freeze_verifier_path=verifier)
    write(tmp_path / "selected-profile.json", {"core": 2.0, "craft": 1.0, "form": 1.0})
    predecessor_root = Path(json.loads(RECONCILIATION.read_bytes())["campaign_root"])
    with pytest.raises(ValueError, match="frozen selection context differs"):
        value.report(campaign_root=root, predecessor_root=predecessor_root, reconciliation_path=RECONCILIATION,
                     freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
                     expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                     freeze_verifier_path=verifier)
