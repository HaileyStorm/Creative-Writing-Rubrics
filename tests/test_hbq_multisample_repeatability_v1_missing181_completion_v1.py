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


def _callback(
    module: ModuleType,
    calls: list[dict[str, Any]],
    order: list[str],
    *,
    endpoint: str | None = None,
):
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
        runner = module._load_runtime(RUNTIME)[1]._load_successor_runner()
        output = work / "runs" / "hanna-523" / "hbq_short_story_batch32" / "run-01"
        output.mkdir(parents=True)
        question_ids = [item for payload in payloads for item in payload["question_ids"]]
        hbq_runner = module._load_runtime(RUNTIME)[1]._load_hbq_runner()
        schema_path = output / "response.schema.json"
        run_id = "missing181-provider-free-fixture"
        configuration = {
            "question_ids": question_ids,
            "batch_size": 32,
            "retry_policy": {"batch_attempts": 3},
            "retry_semantics": "cumulative_batch_attempts_v1",
        }
        config_sha256 = hashlib.sha256(module.canonical(configuration)).hexdigest()

        def observed_boundary(
            context: dict[str, Any], commitments: dict[str, Any]
        ) -> None:
            provider_boundary_check(context, commitments)
            order.append("boundary")

        def observed_before(context: dict[str, Any]) -> None:
            before_provider_attempt(context)
            order.append(f"before-{context['batch']['number']}")

        def fake_run_judge(**kwargs: Any) -> None:
            assert kwargs["provider"] == "codex"
            assert "endpoint" not in kwargs
            assert kwargs["batch_attempts"] == 3
            assert kwargs["batch_size"] == 32
            assert kwargs["before_provider_attempt"] is not None
            order.append("manifest")
            (output / "run.json").write_bytes(
                module.canonical(
                    {
                        "format_version": 4,
                        "run_id": run_id,
                        "config_sha256": config_sha256,
                        "remote": True,
                        "configuration": configuration,
                    }
                )
                + b"\n"
            )
            schema_path.write_bytes(
                hbq_runner._json_bytes(hbq_runner._response_schema())
            )
            if schema_path.read_text(encoding="utf-8") != payloads[0]["request"]["response_schema_utf8"]:
                raise AssertionError("frozen schema bytes differ from the actual runner schema")

            for payload in payloads:
                request = payload["request"]
                prompt = request["prompt_utf8"]
                context = hbq_runner._before_provider_attempt_context(
                    destination=output,
                    schema_path=schema_path,
                    run_id=run_id,
                    config_sha256=config_sha256,
                    provider=kwargs["provider"],
                    model=kwargs["model"],
                    reasoning=kwargs["reasoning"],
                    endpoint=endpoint,
                    batch_number=payload["batch"],
                    question_ids=payload["question_ids"],
                    attempt_number=1,
                    batch_attempts=kwargs["batch_attempts"],
                    base_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    effective_prompt=prompt,
                    feedback_policy=None,
                    feedback=None,
                    rejected_chain={
                        "format_version": 1,
                        "count": 0,
                        "head_sha256": "0" * 64,
                        "records": [],
                    },
                )
                # The actual helper binds these callbacks before invoking run_judge.
                kwargs["before_provider_attempt"](context)

        runner.run_judge = fake_run_judge
        runner.dispatch_event(
            event=event,
            frozen=frozen,
            predecessor_root=predecessor_root,
            work=work,
            timeout=timeout,
            disclosed_cell=disclosed_cell,
            disclosure_profile=disclosure_profile,
            scope_compatibility_override_path=scope_compatibility_override_path,
            predecessor_runner=predecessor_runner,
            before_provider_attempt=observed_before,
            provider_boundary_check=observed_boundary,
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
    assert order == [
        "callback",
        "manifest",
        "boundary",
        "before-1",
        "boundary",
        "before-2",
        "boundary",
        "before-3",
        "boundary",
        "before-4",
        "boundary",
        "before-5",
        "boundary",
        "before-6",
        "output",
    ]
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
def test_actual_successor_rejects_non_null_endpoint_before_provider_attempt(
    tmp_path: Path,
) -> None:
    module = _module()
    _, controller = _prepared(module, tmp_path)
    capacity = _capacity(module, tmp_path / "capacity.json")
    source_before = (SOURCE / "frozen-run-contract.json").read_bytes()
    calls: list[dict[str, Any]] = []
    order: list[str] = []
    with pytest.raises(ValueError, match="Provider boundary context drifted"):
        module.dispatch_missing181(
            controller_root=controller,
            live_capacity_evidence=capacity,
            allow_remote=True,
            callback=_callback(
                module,
                calls,
                order,
                endpoint="https://unexpected.invalid",
            ),
        )
    assert len(calls) == 1
    assert order == ["callback", "manifest"]
    assert (controller / module.CLAIM).is_file()
    assert not (controller / module.RECEIPT).exists()
    output = controller / "runs" / "hanna-523" / "hbq_short_story_batch32" / "run-01"
    assert (output / "run.json").is_file()
    assert not (output / "verdicts.jsonl").exists()
    assert (SOURCE / "frozen-run-contract.json").read_bytes() == source_before


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
    source_before = (SOURCE / "frozen-run-contract.json").read_bytes()
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
    assert (SOURCE / "frozen-run-contract.json").read_bytes() == source_before
