from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from tests import _historical_runtime_compat as historical_runtime
from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "batch-curve-live-v1"


def _raw_live():
    spec = importlib.util.spec_from_file_location("batch_curve_live_v1", ROOT / "batch_curve_live.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _live():
    module = _raw_live()
    parent_root = ROOT.parent / "batch-curve-v2"
    contract = json.loads((parent_root / "study-contract.json").read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("batch_curve_v2_compat", parent_root / "batch_curve_harness.py")
    assert spec and spec.loader
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    historical_runtime.allow_batch_curve_runner_drift(parent, contract)
    module._parent_harness = lambda: parent
    return module


def _contract() -> dict:
    return json.loads((ROOT / "execution-contract.json").read_text(encoding="utf-8"))


def _receipt(number: int) -> dict:
    return {
        "configured_provider_kind": "codex_cli",
        "runner_provider_argument": "codex",
        "reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"},
        "session_id": f"fake-fresh-session-{number}",
    }


TRANSPORT = {
    "mode": "test_callback_only",
    "identity": "pytest-fake-endpoint",
    "version": "1",
    "args_sha256": hashlib.sha256(b"no-args").hexdigest(),
}


def test_parent_projection_and_effective_prompt_bind_the_exact_frozen_subset() -> None:
    live, contract = _live(), _contract()
    with pytest.raises(ValueError, match="Frozen runner revision drifted"):
        _raw_live().validate_execution_contract(contract)
    live.validate_execution_contract(contract)
    planned = live.plans(contract)
    assert len(planned) == 39
    assert sum(1 for row in planned if row["size"] == "all-in-one") == 3
    prompt, binding = live.effective_prompt(["core.task_and_brief_fidelity.intervention", "core.task_and_brief_fidelity.completion_flag"], contract)
    assert "# Atomic binary evaluation prompt" in prompt
    assert "The Part That Arrives First" in prompt
    assert binding["question_ids"] == ["core.task_and_brief_fidelity.intervention", "core.task_and_brief_fidelity.completion_flag"]
    assert binding["effective_prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="canonical disk"):
        drifted = copy.deepcopy(contract)
        drifted["parent"]["contract_sha256"] = "0" * 64
        live.validate_execution_contract(drifted)
    for path, value in ((["study_id"], "other-study"), (["schedule", "cells"], 38)):
        drifted = copy.deepcopy(contract)
        target = drifted
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValueError, match="canonical disk|shape"):
            live.validate_execution_contract(drifted)
    with pytest.raises(ValueError, match="contiguous"):
        live.effective_prompt(["core.task_and_brief_fidelity.intervention", "core.length_and_scope_fit.form"], contract)


def test_fake_external_run_is_resumable_and_never_promotes_a_screen_to_a_recommendation(tmp_path: Path) -> None:
    live, contract = _live(), _contract()
    calls = 0

    def endpoint(_prompt: str, context: dict) -> dict:
        nonlocal calls
        calls += 1
        ids = context["prompt_binding"]["question_ids"]
        return {
            "verdicts": live._parent_harness()._fixture_verdicts(ids),
            "provider": _receipt(calls),
            "response_commitment_sha256": hashlib.sha256(f"unpersisted-{calls}".encode()).hexdigest(),
        }

    result = live.run_callback_mechanism(tmp_path, endpoint, TRANSPORT, contract)
    assert result["completed_cells"] == 39
    assert result["largest_completed_screening_size"] == 178
    assert result["recommendation"] is None and result["evidence_class"] == "transport_agnostic_callback_mechanism_not_live"
    assert len(result["position_metrics"]) == 39
    assert result["screening"]["24"]["confidence_diagnostics"]["mean_assessed_confidence"] == 1.0
    assert (tmp_path / "analysis.json").is_file()
    assert calls > 39
    assert live.run_callback_mechanism(tmp_path, lambda *_: pytest.fail("completed external work should resume without calls"), TRANSPORT, contract) == result
    all_in_one = json.loads((tmp_path / "cells" / "cell-13.json").read_text(encoding="utf-8"))
    assert all_in_one["plan"]["size"] == "all-in-one"
    assert len(all_in_one["calls"]) == 2 and len(all_in_one["calls"][1]["question_ids"]) == 178
    for path in tmp_path.rglob("*.json"):
        assert "unpersisted-" not in path.read_text(encoding="utf-8")


def test_rejected_fake_response_keeps_only_a_commitment_and_resumes_the_frozen_retry_budget(tmp_path: Path) -> None:
    live, contract = _live(), _contract()
    calls = 0

    def bad_endpoint(_prompt: str, context: dict) -> dict:
        nonlocal calls
        calls += 1
        return {
            "verdicts": [{"question_id": context["prompt_binding"]["question_ids"][0]}],
            "provider": _receipt(calls),
            "response_commitment_sha256": hashlib.sha256(f"raw-provider-body-{calls}".encode()).hexdigest(),
        }

    with pytest.raises(ValueError, match="exhausted"):
        live.run_callback_mechanism(tmp_path, bad_endpoint, TRANSPORT, contract)
    cell = json.loads((tmp_path / "cells" / "cell-01.json").read_text(encoding="utf-8"))
    assert len(cell["calls"]) == 6
    assert all(call["event"] == "rejected" and call["rejection"] == "endpoint_rejected_or_invalid" and "provider" in call for call in cell["calls"][1::2])
    serialized = json.dumps(cell)
    assert "raw-provider-body" not in serialized and "verdicts" not in serialized


def test_malformed_or_throwing_callbacks_consume_attempts_without_persisting_injected_secrets(tmp_path: Path) -> None:
    live, contract = _live(), _contract()
    calls = 0

    def unsafe_endpoint(_prompt: str, _context: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("NOUS_API_KEY=secret-should-never-persist")
        return {"verdicts": [], "provider": {**_receipt(calls), "api_key": "secret"}, "response_commitment_sha256": "0" * 64, "raw_response": "secret"}

    with pytest.raises(ValueError, match="exhausted"):
        live.run_callback_mechanism(tmp_path, unsafe_endpoint, TRANSPORT, contract)
    cell = json.loads((tmp_path / "cells" / "cell-01.json").read_text(encoding="utf-8"))
    assert [call["event"] for call in cell["calls"]] == ["attempt_started", "rejected"] * 3
    assert all(call["rejection"] == "transport_or_malformed_response" for call in cell["calls"][1::2])
    assert "secret" not in json.dumps(cell)


def test_receipt_allowlist_rejects_nested_and_top_level_injection(tmp_path: Path) -> None:
    live, contract = _live(), _contract()

    def endpoint(_prompt: str, context: dict) -> dict:
        return {
            "verdicts": live._parent_harness()._fixture_verdicts(context["prompt_binding"]["question_ids"]),
            "provider": {**_receipt(1), "raw_response": "forbidden"},
            "response_commitment_sha256": "0" * 64,
        }

    with pytest.raises(ValueError, match="exhausted"):
        live.run_callback_mechanism(tmp_path, endpoint, TRANSPORT, contract)
    assert "raw_response" not in (tmp_path / "cells" / "cell-01.json").read_text(encoding="utf-8")


def test_duplicate_session_across_semantic_rejections_fails_closed_and_is_retained(tmp_path: Path) -> None:
    live, contract = _live(), _contract()

    def endpoint(_prompt: str, context: dict) -> dict:
        return {
            "verdicts": [{"question_id": context["prompt_binding"]["question_ids"][0]}],
            "provider": _receipt(1),
            "response_commitment_sha256": "0" * 64,
        }

    with pytest.raises(ValueError, match="reused"):
        live.run_callback_mechanism(tmp_path, endpoint, TRANSPORT, contract)
    cell = json.loads((tmp_path / "cells" / "cell-01.json").read_text(encoding="utf-8"))
    rejected = cell["calls"][1::2]
    assert len(rejected) == 2 and all(call["rejection"] == "endpoint_rejected_or_invalid" and call["provider"]["session_id"] == "fake-fresh-session-1" for call in rejected)


def test_manifest_binds_callback_identity_and_adapter_runtime_bytes(tmp_path: Path) -> None:
    live, contract = _live(), _contract()
    manifest = live.prepare(tmp_path, TRANSPORT, contract)
    assert manifest["transport"] == TRANSPORT and len(manifest["adapter_sha256"]) == 64
    manifest["adapter_sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        live.analyze(tmp_path, contract)
