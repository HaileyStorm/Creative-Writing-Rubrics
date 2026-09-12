from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_pending_continuation.py"
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_pending_unlaunched_resume.py"
SUPPORT = ROOT / "tests/test_wpb_sol_pending_continuation.py"
ROUTE_SUPPORT = ROOT / "tests/test_hbq_human_alignment_wpb_compact_native_v1.py"
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-wpb-sol-strict-batch01-reconciliation-20260910-r1/reconciliation.json")


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest(path) for path in sorted(root.rglob("*")) if path.is_file()}


def setup(value: Any, tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    support = load(SUPPORT, "wpb_unlaunched_resume_support")
    pending = load(PENDING, "wpb_unlaunched_resume_pending")
    verifier, verifier_sha, review, review_sha, context = support.fixture(pending, tmp_path)
    root, queue = tmp_path / "continuation", tmp_path / "queue"
    queue.mkdir()
    pending.create_campaign(campaign_root=root, reconciliation_path=RECONCILIATION, queue_root=queue, freeze_root=FREEZE_ROOT,
                            freeze_path=tmp_path / "freeze.json", expected_freeze_sha256=context["freeze_sha256"],
                            expected_freeze_verifier_sha256=verifier_sha, independent_review_path=review,
                            expected_independent_review_sha256=review_sha, freeze_verifier_path=verifier)
    route_source = load(ROUTE_SUPPORT, "wpb_unlaunched_resume_routes")
    routes = route_source.load(route_source.V12_TEST, "wpb_unlaunched_resume_route")
    route = routes.sol_route()[0]
    now = datetime.now(timezone.utc)
    route = {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                           "expires_at": (now + timedelta(minutes=30)).isoformat()}}
    campaign_sha = digest(root / "campaign.json")
    cells = [cell["cell_id"] for cell in json.loads((root / "campaign.json").read_bytes())["cells"][:10]]
    review_path = tmp_path / "legacy-review.json"
    review_sha256 = support.write(review_path, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha, "batch_number": 1, "cell_ids": cells,
        "freeze_sha256": context["freeze_sha256"], "route_sha256": pending.sha256(route),
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    pending.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "freeze.json",
        expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
        freeze_verifier_path=verifier, review_path=review_path, expected_review_sha256=review_sha256,
        authorization_acknowledgement_sha256="a" * 64, broker_factory=lambda _queue: routes.Broker(route))
    material = pending.review_material(campaign_root=root, batch_number=1)
    continuation_review = tmp_path / "continuation-review.json"
    continuation_review_sha = support.write(continuation_review, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    pending._bind_review(root, 1, continuation_review, continuation_review_sha)
    binding_path = root / "batches/0001/pending-continuation-review-binding.json"
    invocation = tmp_path / "prior-invocation.json"
    invocation_sha = support.write(invocation, {"automatic_resend": False, "source_sha256": value.PENDING_SHA256,
        "kwargs": {"allow_remote": True, "batch_number": 1, "campaign_root": str(root),
                   "continuation_review_path": str(continuation_review.resolve()),
                   "expected_continuation_review_sha256": continuation_review_sha}})
    observation = tmp_path / "process-observation.json"
    observation_sha = support.write(observation, {"observation": "external audit; no liveness inference"})
    reconciliation = tmp_path / "unlaunched-reconciliation.json"
    record = {"schema_version": 1, "kind": "wpb_unlaunched_batch_restart_reconciliation", "automatic_resend_authorized": False,
              "resume_scope": "only_same_ten_prepared_cells_after_independent_prelaunch_and_quiescence_review", "campaign_root": str(root),
              "campaign_sha256": campaign_sha, "pending_manifest_sha256": digest(root / "pending-continuation-manifest.json"),
              "source_sha256": value.PENDING_SHA256, "source_manifest_sha256": pending.sha256(pending.source_manifest()),
              "batch_number": 1, "cell_ids": cells, "completed_predecessor_excluded": pending.ADMITTED_CELL,
              "projection_sha256": digest(root / "batches/0001/strict-schema-projection.json"),
              "continuation_review_sha256": continuation_review_sha, "existing_review_binding_sha256": digest(binding_path),
              "launch_intents": 0, "process_receipts": 0, "execution_receipts": 0, "prepared_only_cells": 10,
              "supervisor_invocation": {"path": str(invocation.resolve()), "sha256": invocation_sha},
              "process_observation": {"path": str(observation.resolve()), "sha256": observation_sha}}
    record["immutable_inventory"] = inventory(root)
    record["immutable_inventory_sha256"] = pending.sha256(record["immutable_inventory"])
    reconciliation_sha = support.write(reconciliation, record)
    manifest, manifest_sha = pending._manifest(root)
    operation = tmp_path / "outer-operation.json"
    operation_sha = support.write(operation, {"format_version": 1, "kind": "wpb_sol_pending_unlaunched_resume_operation_v1",
        "companion": value._own_descriptor(), "unlaunched_reconciliation": {"path": str(reconciliation.resolve()), "sha256": reconciliation_sha},
        "prior_invocation": {"path": str(invocation.resolve()), "sha256": invocation_sha},
        "pending_source": value._descriptor(PENDING, value.PENDING_SHA256, "pending continuation source"),
        "pending_manifest": {"path": str((root / "pending-continuation-manifest.json").resolve()), "sha256": manifest_sha},
        "campaign": manifest["campaign"], "source_manifest_sha256": manifest["source_manifest_sha256"],
        "plan": {"path": str((root / "batches/0001/plan.json").resolve()), "sha256": digest(root / "batches/0001/plan.json")},
        "projection_sha256": digest(root / "batches/0001/strict-schema-projection.json"),
        "review": {"path": str(continuation_review.resolve()), "sha256": continuation_review_sha}, "cell_ids": cells,
        "automatic_resend_authorized": False})
    kwargs = {"campaign_root": root, "batch_number": 1, "continuation_review_path": continuation_review,
              "expected_continuation_review_sha256": continuation_review_sha, "prior_invocation_path": invocation,
              "expected_prior_invocation_sha256": invocation_sha, "unlaunched_reconciliation_path": reconciliation,
              "expected_unlaunched_reconciliation_sha256": reconciliation_sha, "outer_operation_path": operation,
              "expected_outer_operation_sha256": operation_sha,
              "fresh_route_guard": lambda: {"route_sha256": json.loads((root / "batches/0001/plan.json").read_bytes())["route_sha256"],
                                               "route_evidence_sha256": json.loads((root / "batches/0001/plan.json").read_bytes())["route_evidence_sha256"]}}
    dispatch_kwargs = {"campaign_root": root, "queue_root": queue, "freeze_root": FREEZE_ROOT,
                       "freeze_path": tmp_path / "freeze.json", "expected_freeze_sha256": context["freeze_sha256"],
                       "expected_freeze_verifier_sha256": verifier_sha, "freeze_verifier_path": verifier, "batch_number": 1,
                       "allow_remote": True, "continuation_review_path": continuation_review,
                       "expected_continuation_review_sha256": continuation_review_sha,
                       "broker_factory": lambda _queue: routes.Broker(route)}
    return kwargs, {"root": root, "binding": binding_path, "cells": cells, "dispatch_kwargs": dispatch_kwargs, "support": support}


def test_exact_binding_admits_read_only_resume_and_rechecks_before_contact(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_unlaunched_resume_success")
    kwargs, paths = setup(value, tmp_path)
    before = inventory(paths["root"])
    result = value.prepare_unlaunched_resume(**kwargs)
    result["before_provider_attempt"]()
    assert result["mode"] == "root_review_required_no_dispatch"
    assert result["prepared_cells"] == paths["cells"]
    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert result["companion"]["sha256"] == digest(SOURCE)
    assert result["pending_source"]["sha256"] == value.PENDING_SHA256
    assert result["prior_invocation"]["sha256"] == kwargs["expected_prior_invocation_sha256"]
    assert result["unlaunched_reconciliation"]["sha256"] == kwargs["expected_unlaunched_reconciliation_sha256"]
    assert inventory(paths["root"]) == before


def test_binding_drift_and_any_launch_artifact_refuse_resume(tmp_path: Path) -> None:
    value = load(SOURCE, "wpb_unlaunched_resume_refusal")
    kwargs, paths = setup(value, tmp_path)
    original = paths["binding"].read_bytes()
    paths["binding"].write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="binding"):
        value.prepare_unlaunched_resume(**kwargs)
    paths["binding"].write_bytes(original)
    (paths["root"] / "batches/0001/execution" / paths["cells"][0] / "launch-intent.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="unlaunched|launch evidence"):
        value.prepare_unlaunched_resume(**kwargs)


def test_dispatch_reuses_existing_binding_and_preserves_native_precontact_path(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(SOURCE, "wpb_unlaunched_resume_dispatch")
    kwargs, paths = setup(value, tmp_path)
    route_source = load(ROUTE_SUPPORT, "wpb_unlaunched_resume_dispatch_route")
    pending = load(PENDING, "wpb_unlaunched_resume_dispatch_pending")
    original_run, binding = subprocess.run, paths["binding"].read_bytes()
    callback_commands: list[list[str]] = []
    route_checks: list[None] = []
    original_guard = kwargs["fresh_route_guard"]
    operation_lock = threading.Lock()
    operation_leader: list[str] = []
    leader_started = threading.Event()

    def fresh_route() -> dict[str, str]:
        route_checks.append(None)
        return original_guard()

    def run(command: list[str], **arguments: Any) -> subprocess.CompletedProcess[bytes]:
        if "input" not in arguments:
            return original_run(command, **arguments)
        callback_commands.append(command)
        output = Path(command[command.index("--cd") + 1])
        if operation_leader and output.name == operation_leader[0]:
            leader_started.set()
        schema = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema.read_bytes())["required"] == ["A", "B", "observed_winner"]
        final = json.dumps(route_source.answer(pending._load_strict()), sort_keys=True, separators=(",", ":"))
        message = Path(command[command.index("--output-last-message") + 1])
        message.parent.mkdir(parents=True, exist_ok=True)
        message.write_text(final, encoding="utf-8")
        events = b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in (
            {"type": "thread.started", "thread_id": f"unlaunched-{output.name}"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": final}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ))
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr=b"")

    kwargs["fresh_route_guard"] = fresh_route
    original_precontact = value._precontact

    def staggered_precontact(**arguments: Any) -> None:
        with operation_lock:
            if not operation_leader:
                operation_leader.append(arguments["cell_id"])
            leader = operation_leader[0]
        if arguments["cell_id"] != leader:
            receipt = paths["root"] / "batches/0001/execution" / leader / "execution-receipt.json"
            assert leader_started.wait(timeout=10.0), "leader synthetic cell did not reach its native callback"
            deadline = time.monotonic() + 10.0
            while not receipt.is_file() and time.monotonic() < deadline:
                time.sleep(0.005)
            assert receipt.is_file(), "leader synthetic cell did not complete before staggered pre-contact"
        original_precontact(**arguments)

    monkeypatch.setattr(value, "_precontact", staggered_precontact)
    monkeypatch.setattr(subprocess, "run", run)
    result = value.dispatch_unlaunched_resume(dispatch_kwargs=paths["dispatch_kwargs"], **kwargs)
    assert len(result["outcomes"]) == len(paths["cells"]) == len(callback_commands)
    assert result["mode"] == "dispatch_completed" and result["process_launches"] == len(paths["cells"])
    assert result["provider_calls_made"] is None and result["provider_contact_cardinality"] == "unknown"
    assert paths["binding"].read_bytes() == binding
    assert len(route_checks) >= len(paths["cells"]) + 2
    with pytest.raises(ValueError, match="unlaunched|launch evidence|process evidence"):
        value.dispatch_unlaunched_resume(dispatch_kwargs=paths["dispatch_kwargs"], **kwargs)
