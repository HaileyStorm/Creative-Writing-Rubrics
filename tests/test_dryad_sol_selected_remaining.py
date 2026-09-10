from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "sol_selected_remaining_execution.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("test_selected_remaining", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconciliation_requires_exact_reviewed_prefix_contract() -> None:
    value = load()
    path = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-completed-message-recovery-4486-4492-20260910-r1\reconciliation.json")
    reconciliation, completed, recovered = value._reconciliation(path, "8a0860386ee148d22cf09c85b07fabf54b58a6c762ada72b166e932e1628c317")

    assert reconciliation["recognized_logical_requests"] == 2068
    assert len(completed) == 204 and list(recovered) == list(value.RETAINED_UNKNOWN)


def test_reconciliation_hash_drift_rejects_before_collection() -> None:
    value = load()
    path = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-completed-message-recovery-4486-4492-20260910-r1\reconciliation.json")
    with pytest.raises(ValueError, match="reconciliation differs"):
        value._reconciliation(path, "0" * 64)


def test_precontact_recovery_binds_the_immutable_r2_inventory() -> None:
    value = load()
    recovery = value._precontact_failure()

    assert len(recovery["files"]) == 78
    assert recovery["provider_contacts"] == 0
    assert recovery["model_request_resend"] is False


def test_frozen_completion_validator_is_owned_by_selected_collector() -> None:
    recovery = load()
    selected_spec = importlib.util.spec_from_file_location("test_frozen_selected", ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "sol_selected_successor_execution.py")
    assert selected_spec and selected_spec.loader
    selected = importlib.util.module_from_spec(selected_spec); selected_spec.loader.exec_module(selected)

    assert not hasattr(recovery, "_validated_completion")
    assert callable(selected._validated_completion)


def test_unknown_exit_facade_recognizes_only_validator_approved_valueerror(tmp_path: Path) -> None:
    value = load(); slot = tmp_path / "request"; (slot / "native-output").mkdir(parents=True)
    (slot / "route.json").write_text("{}", encoding="utf-8"); (slot / "source-bindings.json").write_text("{}", encoding="utf-8")
    seen: dict[str, Any] = {}

    class FailingRuntime:
        @staticmethod
        def call_codex(**kwargs: Any) -> tuple[str, dict[str, Any]]:
            seen.update(kwargs)
            raise ValueError("unknown exit")

    validator = SimpleNamespace(validate_completed_unknown_exit=lambda **_kwargs: ("retained", "thread-1", {"completion_class": "completed_with_unknown_exit", "process_success_proven": False}))
    runtime = value.CompletionAwareRuntime(FailingRuntime(), object(), validator)
    content, record = runtime.call_codex(output_dir=slot / "native-output", request={"ordinal": 1})

    assert content == "retained" and record["completion_class"] == "completed_with_unknown_exit"
    assert "request" not in seen


def test_unknown_exit_facade_propagates_when_validator_rejects(tmp_path: Path) -> None:
    value = load(); slot = tmp_path / "request"; (slot / "native-output").mkdir(parents=True)
    (slot / "route.json").write_text("{}", encoding="utf-8"); (slot / "source-bindings.json").write_text("{}", encoding="utf-8")

    class FailingRuntime:
        @staticmethod
        def call_codex(**_kwargs: Any) -> tuple[str, dict[str, Any]]:
            raise ValueError("unknown exit")

    validator = SimpleNamespace(validate_completed_unknown_exit=lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid retained completion")))
    runtime = value.CompletionAwareRuntime(FailingRuntime(), object(), validator)
    with pytest.raises(ValueError, match="invalid retained completion"):
        runtime.call_codex(output_dir=slot / "native-output", request={"ordinal": 1})


def test_facade_does_not_forward_request_to_the_real_frozen_invoker_signature(tmp_path: Path) -> None:
    value = load()
    runtime_spec = importlib.util.spec_from_file_location("test_frozen_runtime", value.RUNTIME)
    assert runtime_spec and runtime_spec.loader
    frozen = importlib.util.module_from_spec(runtime_spec); runtime_spec.loader.exec_module(frozen)
    signature = inspect.signature(frozen._base()._load_call_codex())
    seen: dict[str, Any] = {}

    class StrictChild:
        @staticmethod
        def call_codex(**kwargs: Any) -> tuple[str, dict[str, Any]]:
            signature.bind(**kwargs)
            seen.update(kwargs)
            return "ordinary", {"completion_class": "completed", "native_thread_id": "thread-1"}

    facade = value.CompletionAwareRuntime(StrictChild(), frozen, object())
    content, _record = facade.call_codex(executable="fixture", model="gpt-5.6-sol", reasoning="high", prompt="{}",
                                         output_dir=tmp_path, response_schema=tmp_path / "schema.json", batch_number=1,
                                         timeout=300, attempt_number=1, before_provider_attempt=lambda: None,
                                         capture_jsonl_events=True, request={"ordinal": 1})

    assert content == "ordinary" and "request" not in seen


def test_incomplete_resume_is_never_resubmitted(tmp_path: Path) -> None:
    value = load(); root = tmp_path / "campaign"; slot = root / "requests" / "4507"; slot.mkdir(parents=True)
    (slot / "terminal.json").write_text(json.dumps({"state": "stopped_no_retry"}), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete remaining slot"):
        value._validate_existing(root, {"ordinal": 4507}, set(), old=object(), runtime=object(), validator=object(), manifest_sha256="m")


def test_dispatch_counts_only_newly_accepted_remaining_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); monkeypatch.setattr(value, "REMAINING", (4507, 4508))
    root, parent_root, plan = tmp_path / "campaign", tmp_path / "parent", tmp_path / "plan"
    root.mkdir(); parent_root.mkdir(); plan.mkdir(); (plan / "plan.json").write_bytes(b"plan")
    (parent_root / "campaign-manifest.json").write_bytes(b"parent-manifest"); (parent_root / "collection-result.json").write_bytes(b"parent-result")
    descriptor = b'{"selected_request_ordinals":[]}'
    (root / "selected-schedule.json").write_bytes(descriptor); (parent_root / "selected-schedule.json").write_bytes(descriptor)

    class Helper:
        @staticmethod
        def route_snapshot(_queue: Path, _identity: dict[str, Any]) -> dict[str, Any]:
            return {"codex_command": ["fixture-codex"]}

        @staticmethod
        def request_payload(_plan: Path, ordinal: int) -> tuple[dict[str, Any], bytes, bytes]:
            prompt = f"prompt-{ordinal}".encode(); schema = b'{"type":"object"}'
            return {"ordinal": ordinal, "batch_number": ordinal - 4506, "question_ids": [],
                    "prompt_sha256": value._sha(prompt), "schema_sha256": value._sha(schema)}, prompt, schema

    parallel = SimpleNamespace(HELPER_PATH=Path("helper"), HELPER_SHA="helper", _load=lambda *_args: Helper)
    old = SimpleNamespace(PARALLEL=Path("parallel"), PARALLEL_SHA256="parallel", _load=lambda *_args: parallel,
                          _validated_completion=lambda slot, request, _runtime: (json.loads((slot / "provider-record.json").read_text(encoding="utf-8"))["native_thread_id"],
                                                                                   json.loads((slot / "provider-record.json").read_text(encoding="utf-8"))))
    parent = SimpleNamespace(OLD=Path("old"), OLD_SHA256="old", _load=lambda *_args: old)

    class Runtime:
        @staticmethod
        def call_codex(**kwargs: Any) -> tuple[str, dict[str, Any]]:
            kwargs["before_provider_attempt"]()
            ordinal = 4506 + kwargs["batch_number"]
            return "{}", {"completion_class": "completed", "native_thread_id": f"new-{ordinal}"}

    controller_hash = value._sha(Path(value.__file__).read_bytes())
    manifest = {"driver_sha256": value.PARENT_SHA256, "actual_controller_sha256": controller_hash,
                "completion_validator_sha256": value._sha(value.COMPLETION.read_bytes()), "frozen_runtime_sha256": value.RUNTIME_SHA256,
                "remaining_original_ordinals": [4507, 4508],
                "counts": {"recognized_prefix": 2068, "recognized_unknown_exit": 7, "remaining_requests": 2, "selected_collection": 2300, "lanes": 10},
                "full_study_admitted": False, "parent_campaign_root": str(parent_root), "reconciliation_path": str(tmp_path / "reconciliation.json"),
                "reconciliation_sha256": value._sha(b"reconciliation"), "parent_manifest_sha256": value._sha(b"parent-manifest"),
                "parent_collection_result_sha256": value._sha(b"parent-result"), "selected_schedule_sha256": value._sha(descriptor),
                "recognized_prefix_thread_ids_sha256": value._sha(value._canonical(["prefix"])), "plan_root": str(plan),
                "original_plan_sha256": value._sha(b"plan"), "old_route_identity": {}, "attempt_policy": {"cumulative_attempts": 1, "resend": False},
                "precontact_recovery_path": str(tmp_path / "precontact.json"), "precontact_recovery_sha256": value._sha(b"precontact"),
                "precontact_recovery_inventory_sha256": value._sha(value._canonical({})), "prior_precontact_failure_root": str(value.R2_ROOT),
                "prior_precontact_failure_manifest_sha256": value.R2_MANIFEST_SHA256, "prior_precontact_failure_result_sha256": value.R2_RESULT_SHA256}
    (root / "campaign-manifest.json").write_bytes(value._canonical(manifest)); (tmp_path / "reconciliation.json").write_bytes(b"reconciliation"); (tmp_path / "precontact.json").write_bytes(b"precontact")
    monkeypatch.setattr(value, "_parent_context", lambda **_kwargs: (parent, Runtime(), object(), {}, {}, {"prefix"}))
    monkeypatch.setattr(value, "_precontact_failure", lambda *_args: {"files": {}})

    result = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=Runtime())

    assert result["state"] == "collected"
    assert result["accepted_new"] == 2 and result["recognized_logical_requests"] == 2070
    assert result["full_study_admitted"] is False
