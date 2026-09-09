from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_batched_execution.py"
SUPPORT = Path(__file__).with_name("test_hbq_human_alignment_wpb_compact_native_v1.py")
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
VERIFIER_SHA256 = "e" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subject() -> Any:
    return load(SOURCE, "wpb_sol_batched_execution_test")


def support() -> Any:
    return load(SUPPORT, "wpb_sol_batched_execution_support")


def context(value: Any) -> dict[str, Any]:
    resolution = value._frozen()._resolution(freeze_root=FREEZE_ROOT)
    return {
        "freeze_sha256": "f" * 64,
        "selection_frozen_at": "2026-09-07T00:00:00Z",
        "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
        "schedule_sha256": resolution["schedule_sha256"],
        "source_bindings": {"fixture": "synthetic_only"},
        "evidence_files": {"fixture": "synthetic_only"},
        "native_measurement_count": 129,
    }


def install_freeze(monkeypatch: pytest.MonkeyPatch, value: Any, frozen: dict[str, Any]) -> None:
    def verify(path: Path, expected: str, *, replay_native: bool) -> dict[str, Any]:
        assert path.name == "grok-selection-freeze.json" and expected == frozen["freeze_sha256"]
        return dict(frozen)
    monkeypatch.setattr(value, "_freeze_module", lambda _path, _expected: SimpleNamespace(verify_freeze=verify))


def mixed_context(value: Any) -> dict[str, Any]:
    return {
        "freeze_sha256": "f" * 64,
        "selection_frozen_at": "2026-09-07T00:00:00Z",
        "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
        "schedule_sha256": value._frozen()._resolution(freeze_root=FREEZE_ROOT)["schedule_sha256"],
        "source_bindings": {"fixture": "mixed-synthetic-only"},
        value.MIXED_V5_SELECTION_CONTEXT: {
            "legacy_measurement_count": 89, "v4_native_measurement_count": 12, "v5_native_measurement_count": 27,
            "local_session_schema_recovered_measurement_count": 1, "native_measurement_count": 128,
            "measurement_count": 129, "v4_cell_ids": [f"v4-{number}" for number in range(12)],
            "v5_cell_ids": [f"v5-{number}" for number in range(27)], "recovered_cell_id": "wpb-pair-wpb-en-0843",
            "authority": "development_only_no_runtime_or_confirmation_authority", "release_or_promotion_authority": "none",
        },
    }


def mixed_verifier(tmp_path: Path, frozen: dict[str, Any]) -> tuple[Path, str]:
    path = tmp_path / "reviewed-mixed-verifier.py"
    path.write_text(
        "def verify_freeze_context(freeze_path, expected_sha256, replay_native=True):\n"
        f"    return {frozen!r}\n",
        encoding="utf-8",
    )
    return path, __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def review(value: Any, root: Path, *, campaign_sha256: str, batch_number: int, cell_ids: list[str],
           freeze_sha256: str, route_sha256: str, freeze_contract: dict[str, Any] | None = None) -> tuple[Path, str]:
    now = datetime.now(timezone.utc)
    path = root / f"review-{batch_number:04d}.json"
    record = {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch", "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": campaign_sha256,
              "batch_number": batch_number, "cell_ids": cell_ids, "freeze_sha256": freeze_sha256,
              "route_sha256": route_sha256, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "expires_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), **(freeze_contract or {})}
    path.write_bytes(value.canonical(record))
    return path, value.sha256(path.read_bytes())


def fresh_route(route: dict[str, Any]) -> dict[str, Any]:
    route = {**route, "cost_evidence": dict(route["cost_evidence"])}
    route["cost_evidence"]["expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    return route


def freeze_review(value: Any, root: Path, freeze_sha256: str, freeze_contract: dict[str, Any] | None = None,
                  freeze_verifier_sha256: str = VERIFIER_SHA256) -> tuple[Path, str]:
    path = root / "freeze-review.json"
    path.write_bytes(value.canonical({"format_version": 1, "kind": "wpb_grok_selection_freeze_independent_review",
                                       "freeze_sha256": freeze_sha256, "freeze_verifier_sha256": freeze_verifier_sha256,
                                       "decision": "approved_wpb_grok_selection_freeze", "reviewed_at": "2026-09-07T00:00:00Z",
                                       **(freeze_contract or {})}))
    return path, value.sha256(path.read_bytes())


def test_preparation_is_lazy_bounded_and_replays_freeze_before_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, helpers = subject(), support(); frozen = context(value); install_freeze(monkeypatch, value, frozen)
    root, queue = tmp_path / "external-campaign", tmp_path / "queue"; queue.mkdir()
    freeze_approval, freeze_approval_sha = freeze_review(value, tmp_path, frozen["freeze_sha256"])
    created = value.create_campaign(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                    freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                    expected_freeze_verifier_sha256=VERIFIER_SHA256, independent_review_path=freeze_approval, expected_independent_review_sha256=freeze_approval_sha)
    route, _evidence = helpers.load(helpers.V12_TEST, "wpb_sol_batched_route_support").sol_route(); route = fresh_route(route)
    ids = [row["cell_id"] for row in value._frozen()._resolution(freeze_root=FREEZE_ROOT)["rows"][:10]]
    approved, approval_sha = review(value, tmp_path, campaign_sha256=created["campaign_sha256"], batch_number=1, cell_ids=ids,
                                    freeze_sha256=frozen["freeze_sha256"], route_sha256=value.sha256(route))
    result = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                      freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                      expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                      review_path=approved, expected_review_sha256=approval_sha, authorization_acknowledgement_sha256="a" * 64,
                                      broker_factory=lambda _root: helpers.load(helpers.V12_TEST, "wpb_sol_batched_broker_support").Broker(route))
    assert result["prepared_cells"] == ids and result["provider_calls_made"] == result["process_launches"] == 0
    assert not (root / "batches/0002").exists()
    binding = root / "batches/0001/prepared-source-bindings.json"
    binding_value = __import__("json").loads(binding.read_bytes())
    assert binding.is_file() and len(binding_value["prepared_sha256s"]) == 10
    assert binding_value["freeze_verifier_sha256"] == VERIFIER_SHA256
    campaign = __import__("json").loads((root / "campaign.json").read_bytes())
    plan = __import__("json").loads((root / "batches/0001/plan.json").read_bytes())
    assert "freeze_verifier_path" not in campaign and "freeze_verifier_path" not in plan


def test_expiring_route_cannot_create_a_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, helpers = subject(), support(); frozen = context(value); install_freeze(monkeypatch, value, frozen)
    root, queue = tmp_path / "external-campaign", tmp_path / "queue"; queue.mkdir()
    freeze_approval, freeze_approval_sha = freeze_review(value, tmp_path, frozen["freeze_sha256"])
    created = value.create_campaign(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                    freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                    expected_freeze_verifier_sha256=VERIFIER_SHA256, independent_review_path=freeze_approval, expected_independent_review_sha256=freeze_approval_sha)
    route, _evidence = helpers.load(helpers.V12_TEST, "wpb_sol_batched_expiry_route_support").sol_route()
    ids = [row["cell_id"] for row in value._frozen()._resolution(freeze_root=FREEZE_ROOT)["rows"][:10]]
    approved, approval_sha = review(value, tmp_path, campaign_sha256=created["campaign_sha256"], batch_number=1, cell_ids=ids,
                                    freeze_sha256=frozen["freeze_sha256"], route_sha256=value.sha256(route))
    with pytest.raises(ValueError, match="900-second"):
        value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                 freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                 expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                 review_path=approved, expected_review_sha256=approval_sha, authorization_acknowledgement_sha256="a" * 64,
                                 broker_factory=lambda _root: helpers.load(helpers.V12_TEST, "wpb_sol_batched_expiry_broker_support").Broker(route))
    assert not (root / "batches").exists()


@pytest.mark.parametrize(
    ("stderr", "error"),
    [
        (b"", None),
        (b"ERROR: native fixture failure\n", "contains an error marker"),
        (b"model: another-model\n", "identity label conflicts"),
        (b"\xff", "not valid UTF-8"),
    ],
)
def test_private_wpb_wrapper_captures_completed_process_before_stderr_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes,
    error: str | None,
) -> None:
    value = subject()
    runtime = value._frozen()._sol_runtime(value._frozen()._resolution(freeze_root=FREEZE_ROOT))[1]
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        message = Path(command[command.index("--output-last-message") + 1])
        message.parent.mkdir(parents=True, exist_ok=True)
        message.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b'{"type":"thread.started","thread_id":"fixture"}\n',
            stderr=stderr,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    receipt_root = tmp_path / "process-capture"
    invoke = value._current_call_codex(runtime, receipt_root=receipt_root)
    root, schema, gated = tmp_path / "cell", tmp_path / "schema.json", []
    root.mkdir()
    schema.write_text("{}", encoding="utf-8")

    if error is None:
        content, record = invoke(
            executable="fixture-codex",
            model="gpt-5.6-sol",
            reasoning="high",
            prompt="{}",
            output_dir=root,
            response_schema=schema,
            batch_number=1,
            timeout=1,
            before_provider_attempt=lambda: gated.append(True),
            capture_jsonl_events=True,
        )
        assert content == "{}"
        assert calls[0] == [*record["command"][:-1], "-"]
        assert record["command"][record["command"].index("--output-last-message") + 1] == str(
            root / "responses/batch-0001.attempt-0001.message.json"
        )
    else:
        with pytest.raises(ValueError, match=error):
            invoke(
                executable="fixture-codex",
                model="gpt-5.6-sol",
                reasoning="high",
                prompt="{}",
                output_dir=root,
                response_schema=schema,
                batch_number=1,
                timeout=1,
                before_provider_attempt=lambda: gated.append(True),
                capture_jsonl_events=True,
            )

    receipt = json.loads((receipt_root / "cell.json").read_bytes())
    message = root / "responses/batch-0001.attempt-0001.message.json"
    assert receipt["state"] == "completed" and receipt["exit_code"] == 0
    assert receipt["final_message"] == {
        "exists": True,
        "bytes": len(message.read_bytes()),
        "sha256": hashlib.sha256(message.read_bytes()).hexdigest(),
    }
    assert gated == [True] and calls[0][-1] == "-"
    assert calls[0][calls[0].index("code_mode") - 1:calls[0].index("code_mode") + 1] == ["--disable", "code_mode"]
    assert calls[0][calls[0].index("--output-last-message") + 1] == str(message)
    assert (root / "raw-codex-stderr.bin").is_file() and (root / "responses/batch-0001.attempt-0001.events.jsonl").is_file()


def test_persisted_review_companion_rejects_expiry_without_rewriting_history(tmp_path: Path) -> None:
    value = subject()
    plan = {"campaign_sha256": "c" * 64, "batch_number": 1, "cell_ids": ["cell-1"],
            "freeze_sha256": "f" * 64, "route_sha256": "r" * 64}
    review_path = tmp_path / "independent-review.json"
    review_path.write_bytes(value.canonical({
        "format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": plan["campaign_sha256"],
        "batch_number": plan["batch_number"], "cell_ids": plan["cell_ids"], "freeze_sha256": plan["freeze_sha256"],
        "route_sha256": plan["route_sha256"], "reviewed_at": "2026-09-07T00:00:00Z", "expires_at": "2026-09-07T00:01:00Z",
    }))
    plan["review_sha256"] = value.sha256(review_path.read_bytes())
    value._review_companion(tmp_path, plan, require_unexpired=False)
    with pytest.raises(ValueError, match="has expired"):
        value._review_companion(tmp_path, plan, require_unexpired=True)


def test_freeze_review_binds_the_exact_verifier_source(tmp_path: Path) -> None:
    value = subject()
    path = tmp_path / "freeze-review.json"
    path.write_bytes(value.canonical({
        "format_version": 1, "kind": "wpb_grok_selection_freeze_independent_review",
        "freeze_sha256": "f" * 64, "freeze_verifier_sha256": "0" * 64,
        "decision": "approved_wpb_grok_selection_freeze", "reviewed_at": "2026-09-07T00:00:00Z",
    }))
    with pytest.raises(ValueError, match="independent review differs"):
        value._freeze_review(path, value.sha256(path.read_bytes()), "f" * 64, VERIFIER_SHA256)


def test_batched_synthetic_fixture_uses_frozen_parser_and_closes_before_all_epochs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, helpers = subject(), support(); frozen = context(value); install_freeze(monkeypatch, value, frozen)
    root, queue = tmp_path / "external-campaign", tmp_path / "queue"; queue.mkdir()
    freeze_approval, freeze_approval_sha = freeze_review(value, tmp_path, frozen["freeze_sha256"])
    created = value.create_campaign(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                    freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                    expected_freeze_verifier_sha256=VERIFIER_SHA256, independent_review_path=freeze_approval, expected_independent_review_sha256=freeze_approval_sha)
    route_support = helpers.load(helpers.V12_TEST, "wpb_sol_batched_full_route_support")
    route, _evidence = route_support.sol_route(); route = fresh_route(route)
    factory = lambda _root: route_support.Broker(route)
    resolution = value._frozen()._resolution(freeze_root=FREEZE_ROOT)
    contacts = helpers.Contacts()
    runner = helpers.sol_runner(value._frozen(), resolution["rows"], contacts)
    for number in (1,):
        ids = [row["cell_id"] for row in resolution["rows"][:10]]
        approved, approval_sha = review(value, tmp_path, campaign_sha256=created["campaign_sha256"], batch_number=number, cell_ids=ids,
                                        freeze_sha256=frozen["freeze_sha256"], route_sha256=value.sha256(route))
        prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                            freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                            expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                            review_path=approved, expected_review_sha256=approval_sha, authorization_acknowledgement_sha256="a" * 64,
                                            broker_factory=factory)
        assert prepared["prepared_cells"] == ids
        outcomes = value.dispatch_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                        freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                        expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                        batch_number=number, allow_remote=True, broker_factory=factory, call_codex=runner)
        assert len(outcomes) == len(ids)
        settled = value.settle_batch(campaign_root=root, freeze_root=FREEZE_ROOT,
                                     freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                     expected_freeze_verifier_sha256=VERIFIER_SHA256,
                                     batch_number=number)
        assert settled["status"] == "completed" and settled["completed_cells"] == ids
    report = value.report(campaign_root=root, freeze_root=FREEZE_ROOT,
                          freeze_path=tmp_path / "grok-selection-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"], expected_freeze_verifier_sha256=VERIFIER_SHA256)
    assert report == {"status": "closed_incomplete", "authority": "development_screening_only", "completed_batches": 1, "metrics": None}
    assert len(contacts.calls) == len(set(contacts.calls)) == 10


def test_mixed_freeze_binds_reviewed_verifier_and_source_context_through_prepare(tmp_path: Path) -> None:
    value, helpers = subject(), support()
    frozen = mixed_context(value); verifier, verifier_sha256 = mixed_verifier(tmp_path, frozen)
    contract = value._freeze_contract(frozen, verifier_path=verifier.resolve(), mixed_v5_freeze=True)
    freeze_review_contract = contract | value._campaign_freeze_binding(frozen, mixed_v5_freeze=True)
    review_contract = {"freeze_verifier_sha256": verifier_sha256, **freeze_review_contract}
    root, queue = tmp_path / "external-campaign", tmp_path / "queue"; queue.mkdir()
    approval, approval_sha = freeze_review(value, tmp_path, frozen["freeze_sha256"], freeze_review_contract, verifier_sha256)
    created = value.create_campaign(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                    freeze_path=tmp_path / "mixed-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                    expected_freeze_verifier_sha256=verifier_sha256, independent_review_path=approval,
                                    expected_independent_review_sha256=approval_sha, freeze_verifier_path=verifier,
                                    mixed_v5_freeze=True)
    campaign = __import__("json").loads((root / "campaign.json").read_bytes())
    assert {key: campaign[key] for key in review_contract} == review_contract
    route, _evidence = helpers.load(helpers.V12_TEST, "wpb_sol_batched_mixed_route_support").sol_route(); route = fresh_route(route)
    ids = [row["cell_id"] for row in value._frozen()._resolution(freeze_root=FREEZE_ROOT)["rows"][:10]]
    dispatch_review, dispatch_review_sha = review(value, tmp_path, campaign_sha256=created["campaign_sha256"],
                                                   batch_number=1, cell_ids=ids, freeze_sha256=frozen["freeze_sha256"],
                                                   route_sha256=value.sha256(route), freeze_contract=review_contract)
    prepared = value.prepare_next_batch(campaign_root=root, queue_root=queue, freeze_root=FREEZE_ROOT,
                                        freeze_path=tmp_path / "mixed-freeze.json", expected_freeze_sha256=frozen["freeze_sha256"],
                                        expected_freeze_verifier_sha256=verifier_sha256, review_path=dispatch_review,
                                        expected_review_sha256=dispatch_review_sha, authorization_acknowledgement_sha256="a" * 64,
                                        broker_factory=lambda _root: helpers.load(helpers.V12_TEST, "wpb_sol_batched_mixed_broker_support").Broker(route),
                                        freeze_verifier_path=verifier, mixed_v5_freeze=True)
    plan = __import__("json").loads((root / "batches/0001/plan.json").read_bytes())
    bindings = __import__("json").loads((root / "batches/0001/prepared-source-bindings.json").read_bytes())
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    assert {key: plan[key] for key in review_contract} == review_contract
    assert {key: bindings[key] for key in review_contract} == review_contract
    assert "freeze_evidence_files_sha256" not in plan


@pytest.mark.parametrize(("field", "replacement"), [
    ("native_measurement_count", 129),
    ("measurement_count", 128),
    ("recovered_cell_id", ""),
])
def test_mixed_freeze_rejects_incorrect_geometry_before_campaign(field: str, replacement: Any, tmp_path: Path) -> None:
    value = subject(); frozen = mixed_context(value)
    frozen[value.MIXED_V5_SELECTION_CONTEXT][field] = replacement
    verifier, verifier_sha256 = mixed_verifier(tmp_path, frozen)
    with pytest.raises(ValueError, match="mixed v5 selection geometry differs"):
        value._full_freeze(tmp_path / "mixed-freeze.json", frozen["freeze_sha256"], verifier_sha256,
                           verifier_path=verifier.resolve(), mixed_v5_freeze=True, replay_native=False)


def test_mixed_freeze_rejects_verifier_hash_drift(tmp_path: Path) -> None:
    value = subject(); frozen = mixed_context(value); verifier, _verifier_sha256 = mixed_verifier(tmp_path, frozen)
    with pytest.raises(ValueError, match="source drifted"):
        value._full_freeze(tmp_path / "mixed-freeze.json", frozen["freeze_sha256"], "0" * 64,
                           verifier_path=verifier.resolve(), mixed_v5_freeze=True, replay_native=False)
