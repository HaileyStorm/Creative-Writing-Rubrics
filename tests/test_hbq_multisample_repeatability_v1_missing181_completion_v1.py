from __future__ import annotations

import hashlib
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-missing181-completion-v1"
)
EXECUTOR = PACKAGE / "executor.py"
SOURCE = Path(
    r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab"
)
SETTLEMENT = (
    ROOT
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v7"
    / "forensic-sequence-181-settlement.json"
)
RUNTIME = Path(
    r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-v8-runtime-e50dd50\evaluation-results\hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8"
)

AVAILABLE = EXECUTOR.is_file() and SOURCE.is_dir() and SETTLEMENT.is_file() and RUNTIME.is_dir()


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("missing181_completion_test", EXECUTOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capacity(module: ModuleType, path: Path, *, age_seconds: int = 0) -> Path:
    observed = datetime.now(UTC) - timedelta(seconds=age_seconds)
    payload = {
        "kind": "external_current_capacity_evidence_v2",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "assertion": "capacity_available",
        "attestation": "local_host_observation_only",
        "observed_at": observed.isoformat(),
        "observation": {
            "surface": "native_codex_quota_surface",
            "reference": "provider-free test fixture",
        },
    }
    path.write_bytes(module.canonical(payload) + b"\n")
    return path


def _prepared(module: ModuleType, tmp_path: Path) -> tuple[dict[str, Any], Path]:
    controller = tmp_path / "controller"
    binding = module.prepare_completion(
        original_root=SOURCE,
        v7_settlement=SETTLEMENT,
        controller_root=controller,
        v8_runtime_root=RUNTIME,
    )
    module.write_disclosure_ack(
        controller_root=controller,
        acknowledgement=module._expected_ack(binding),
    )
    return binding, controller


def _callback(module: ModuleType, calls: list[dict[str, Any]], order: list[str]):
    def dispatch_event(
        *,
        event: dict[str, Any],
        frozen: dict[str, Any],
        predecessor_root: Path,
        work: Path,
        timeout: float,
        disclosed_cell: dict[str, Any],
        disclosure_profile: dict[str, Any],
        scope_compatibility_override_path: Path,
        predecessor_runner: Any,
        before_provider_attempt: Any,
        provider_boundary_check: Any,
    ) -> Path:
        calls.append(
            {
                "event": event,
                "frozen": frozen,
                "predecessor_root": predecessor_root,
                "work": work,
                "timeout": timeout,
                "disclosed_cell": disclosed_cell,
                "disclosure_profile": disclosure_profile,
                "scope_compatibility_override_path": scope_compatibility_override_path,
                "predecessor_runner": predecessor_runner,
                "before_provider_attempt": before_provider_attempt,
                "provider_boundary_check": provider_boundary_check,
            }
        )
        order.append("callback")
        payloads = disclosed_cell["payload"]["provider_payloads"]
        for payload in payloads:
            request = payload["request"]
            prompt = request["prompt_utf8"]
            schema = request["response_schema_utf8"]
            before_provider_attempt(
                {
                    "provider": {
                        key: disclosure_profile[key]
                        for key in ("provider", "model", "reasoning")
                    },
                    "batch": {
                        "number": payload["batch"],
                        "question_ids": payload["question_ids"],
                    },
                    "attempt": {"number": 1, "batch_attempts": 3},
                    "prompt": {
                        "encoding": "utf-8",
                        "text": prompt,
                        "bytes": len(prompt.encode()),
                        "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    },
                    "response_schema": {
                        "encoding": "utf-8",
                        "text": schema,
                        "bytes": len(schema.encode()),
                        "sha256": hashlib.sha256(schema.encode()).hexdigest(),
                    },
                }
            )
            order.append(f"before-{payload['batch']}")

        runner = module._load_runtime(RUNTIME)[1]._load_successor_runner()
        provider = disclosure_profile
        task_path = SOURCE / "inputs" / "hanna-523" / "task-contract.json"
        override_path = scope_compatibility_override_path
        commitments = {
            "provider": {key: provider[key] for key in ("provider", "model", "reasoning")},
            "disclosure_profile": dict(provider),
            "disclosed_cell_sha256": hashlib.sha256(
                module.canonical(disclosed_cell)
            ).hexdigest(),
            "disclosure_profile_sha256": hashlib.sha256(
                module.canonical(provider)
            ).hexdigest(),
            "helper": runner.runtime_identity(),
            "dependencies": {
                "scope_compatibility_override": {
                    "path": str(override_path.absolute()),
                    "bytes": override_path.stat().st_size,
                    "sha256": module.sha(override_path),
                },
                "task_contract": {
                    "path": str(task_path.absolute()),
                    "bytes": task_path.stat().st_size,
                    "sha256": module.sha(task_path),
                },
            },
        }
        provider_boundary_check(
            {
                "provider": {
                    key: provider[key] for key in ("provider", "model", "reasoning")
                }
            },
            commitments,
        )
        order.append("boundary")

        output = work / "runs" / "hanna-523" / "hbq_short_story_batch32" / "run-01"
        output.mkdir(parents=True)
        question_ids = [item for payload in payloads for item in payload["question_ids"]]
        (output / "run.json").write_bytes(
            module.canonical(
                {
                    "configuration": {
                        "question_ids": question_ids,
                        "batch_size": 32,
                        "retry_policy": {"batch_attempts": 3},
                        "retry_semantics": "cumulative_batch_attempts_v1",
                    }
                }
            )
            + b"\n"
        )
        (output / "verdicts.jsonl").write_bytes(
            b"".join(module.canonical({"question_id": item}) + b"\n" for item in question_ids)
        )
        responses = output / "responses"
        responses.mkdir()
        for number, payload in enumerate(payloads, 1):
            ids = payload["question_ids"]
            (responses / f"batch-{number:04d}.json").write_bytes(
                module.canonical(
                    {
                        "batch": number,
                        "accepted_attempt": 1,
                        "question_ids": ids,
                        "normalized_verdicts": [{"question_id": item} for item in ids],
                        "session_id": f"accepted-session-{number}",
                    }
                )
                + b"\n"
            )
            (responses / f"batch-{number:04d}.attempt-0001.message.json").write_bytes(
                module.canonical({"session_id": f"message-session-{number}"}) + b"\n"
            )
        order.append("output")
        return output / "run.json"

    return dispatch_event


@pytest.mark.skipif(not AVAILABLE, reason="host-local frozen CWR evidence is unavailable")
def test_prepare_binds_exact_181_source_settlement_disclosure_override_and_179_questions(
    tmp_path: Path,
) -> None:
    module = _module()
    binding, controller = _prepared(module, tmp_path)
    assert binding["event"] == module.EVENT == {
        "sequence": 181,
        "item_id": "hanna-523",
        "arm_id": "hbq_short_story_batch32",
        "repetition": 1,
    }
    assert binding["v7_zero_contact_settlement"] == {
        "path": str(SETTLEMENT.absolute()),
        "sha256": module.sha(SETTLEMENT),
        "evidence_class": "local_task_history_projection_and_immutable_local_files",
        "not_provider_attestation": True,
    }
    assert binding["source"]["root"] == str(SOURCE.absolute())
    assert binding["runtime"]["executor_sha256"] == module.EXPECTED_V8_EXECUTOR_SHA256
    assert len(binding["question_ids"]) == 179
    assert len(binding["question_ids"]) == len(set(binding["question_ids"]))
    disclosure = module._json(controller / module.DISCLOSURE)
    assert disclosure["sequence"] == 181
    assert disclosure["item_id"] == "hanna-523"
    assert len(disclosure["payload"]["provider_payloads"]) == 6
    v8 = module._load_runtime(RUNTIME)[1]
    assert [item["artifact_id"] for item in v8._scope_override_records(
        SOURCE, [module.EVENT], v8.read_json(SOURCE / "frozen-run-contract.json")
    )] == ["hanna-523"]
    override = next((controller / module.OVERRIDES).iterdir())
    assert module.sha(override) == binding["scope_compatibility_override"]["sha256"]
    assert not (controller / module.CLAIM).exists()


@pytest.mark.skipif(not AVAILABLE, reason="host-local frozen CWR evidence is unavailable")
def test_dispatch_uses_frozen_dispatch_event_signature_and_persists_normal_receipt(
    tmp_path: Path,
) -> None:
    module = _module()
    binding, controller = _prepared(module, tmp_path)
    capacity = _capacity(module, tmp_path / "capacity.json")
    calls: list[dict[str, Any]] = []
    order: list[str] = []
    receipt_path = module.dispatch_missing181(
        controller_root=controller,
        live_capacity_evidence=capacity,
        allow_remote=True,
        callback=_callback(module, calls, order),
    )
    assert len(calls) == 1
    assert set(calls[0]) == {
        "event", "frozen", "predecessor_root", "work", "timeout", "disclosed_cell",
        "disclosure_profile", "scope_compatibility_override_path", "predecessor_runner",
        "before_provider_attempt", "provider_boundary_check",
    }
    assert calls[0]["event"] == module.EVENT
    assert calls[0]["predecessor_root"] == SOURCE.absolute()
    assert calls[0]["work"] == controller.absolute()
    assert order == ["callback", "before-1", "before-2", "before-3", "before-4", "before-5", "before-6", "boundary", "output"]
    assert receipt_path == controller / module.RECEIPT
    receipt = module._json(receipt_path)
    assert receipt["status"] == "NORMAL_RECEIPT_WITH_PERSISTED_EVIDENCE"
    assert receipt["event"] == module.EVENT
    assert receipt["output"]["persisted_batches"] == 6
    assert receipt["output"]["persisted_attempts"] == 6
    assert receipt["output"]["persisted_session_bearing_records"] == 6
    assert receipt["output"]["question_ids_sha256"] == binding["question_ids_sha256"]
    assert (controller / module.CLAIM).is_file()


@pytest.mark.skipif(not AVAILABLE, reason="host-local frozen CWR evidence is unavailable")
def test_default_off_and_stale_capacity_fail_before_claim_or_callback(tmp_path: Path) -> None:
    module = _module()
    _, controller = _prepared(module, tmp_path)
    capacity = _capacity(module, tmp_path / "stale-capacity.json", age_seconds=601)
    calls: list[dict[str, Any]] = []
    callback = _callback(module, calls, [])
    with pytest.raises(ValueError, match="explicitly authorized"):
        module.dispatch_missing181(
            controller_root=controller,
            live_capacity_evidence=capacity,
            callback=callback,
        )
    with pytest.raises(ValueError, match="not current"):
        module.dispatch_missing181(
            controller_root=controller,
            live_capacity_evidence=capacity,
            allow_remote=True,
            callback=callback,
        )
    assert calls == []
    assert not (controller / module.CLAIM).exists()
    assert not (controller / module.RECEIPT).exists()
    assert not (controller / "runs").exists()


@pytest.mark.skipif(not AVAILABLE, reason="host-local frozen CWR evidence is unavailable")
def test_exclusive_claim_and_normal_receipt_make_a_second_dispatch_impossible(
    tmp_path: Path,
) -> None:
    module = _module()
    _, controller = _prepared(module, tmp_path)
    capacity = _capacity(module, tmp_path / "capacity.json")
    calls: list[dict[str, Any]] = []
    module.dispatch_missing181(
        controller_root=controller,
        live_capacity_evidence=capacity,
        allow_remote=True,
        callback=_callback(module, calls, []),
    )
    claim_before = (controller / module.CLAIM).read_bytes()
    receipt_before = (controller / module.RECEIPT).read_bytes()
    with pytest.raises(ValueError, match="blocks resend"):
        module.dispatch_missing181(
            controller_root=controller,
            live_capacity_evidence=capacity,
            allow_remote=True,
            callback=lambda **_kwargs: pytest.fail("second dispatch reached callback"),
        )
    assert (controller / module.CLAIM).read_bytes() == claim_before
    assert (controller / module.RECEIPT).read_bytes() == receipt_before
