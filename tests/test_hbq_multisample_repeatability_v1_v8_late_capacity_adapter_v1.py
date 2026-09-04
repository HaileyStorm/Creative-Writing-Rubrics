from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PATH = (
    Path(__file__).parents[1]
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-v8-late-capacity-adapter-v1"
    / "adapter.py"
)


def _adapter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v8_late_capacity_adapter_test", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RetryPause(RuntimeError):
    pass


def _harness(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    drift: str | None = None,
    capacity_age: int = 1,
) -> tuple[dict[str, Any], dict[str, Path], dict[str, Any]]:
    roots = {
        name: tmp_path / name
        for name in ("binding", "source", "closed", "v7", "work", "runtime", "guard")
    }
    for root in roots.values():
        root.mkdir()
    (roots["source"] / "frozen-run-contract.json").write_text("{}\n", encoding="utf-8")
    acknowledgement = roots["work"] / "disclosure-acknowledgement.json"
    acknowledgement.write_text("{}\n", encoding="utf-8")
    capacity = tmp_path / "capacity.json"
    capacity.write_text(json.dumps({"age_seconds": capacity_age}) + "\n", encoding="utf-8")

    accepted_event = {
        "sequence": 182,
        "item_id": "item-182",
        "arm_id": "native",
        "repetition": 1,
        "payload": {"prompt_sha256": "1" * 64},
    }
    next_event = {
        "sequence": 183,
        "item_id": "item-183",
        "arm_id": "native",
        "repetition": 1,
        "payload": {"prompt_sha256": "2" * 64},
    }
    guard_event = dict(next_event)
    if drift == "event":
        guard_event["sequence"] = 184
    schedule = [accepted_event, next_event]
    binding = {"runtime": {"executor": "frozen-v8"}}
    state: dict[str, Any] = {
        "order": [],
        "claims": 0,
        "native_commands": 0,
        "provider_attempts": 0,
        "supplier_paths": [],
        "capacity_validations": 0,
        "contact_lengths": [],
        "accepted_calls": 0,
        "query_binding_calls": 0,
        "exact_load_calls": 0,
        "module_load_calls": 0,
        "preflight_age_seconds": 601,
    }

    class Guard:
        def _assert_no_unresolved_v8_state(self, _v8: Any, _work: Path) -> None:
            state["order"].append("unresolved")

        def dispatch_next(self, *, delegate: Any, **_kwargs: Any) -> Any:
            if state["claims"]:
                raise ValueError("existing guard claim blocks resend")
            state["claims"] += 1
            state["order"].append("claim")
            state["order"].append(f"guard-preflight-age:{state['preflight_age_seconds']}")
            result = delegate(dict(guard_event))
            postflight_rows = [dict(row) for row in result]
            if drift == "postflight":
                postflight_rows[-1]["sequence"] = 999
            contact(roots["source"], roots["work"], {"admission": "frozen"}, postflight_rows)
            return result

    guard = Guard()

    def validate_ack(_work: Path, _ack: Path) -> None:
        state["order"].append("ack")
        if drift == "ack":
            raise ValueError("disclosure acknowledgement drift")

    def verify_prepared(*_args: Any) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        state["order"].append("verify")
        if drift == "source":
            raise ValueError("source binding drift")
        return binding, schedule, {"admission": "frozen"}

    def accepted(*_args: Any) -> list[dict[str, Any]]:
        state["accepted_calls"] += 1
        state["order"].append("accepted")
        return [accepted_event]

    def contact(_source: Path, _work: Path, _admission: Any, rows: list[dict[str, Any]]) -> None:
        state["contact_lengths"].append(len(rows))
        state["order"].append("postflight" if len(rows) == 2 else "contact")
        if len(rows) == 2 and rows != [accepted_event, next_event]:
            raise ValueError("guard postflight session drift")

    def orphan(_work: Path, _remaining: list[dict[str, Any]]) -> None:
        state["order"].append("payload")
        if drift == "payload":
            raise ValueError("payload output drift")

    def runtime_projection(_frozen: Any) -> dict[str, str]:
        state["order"].append("runtime")
        return {"runtime": "drifted"} if drift == "runtime" else binding["runtime"]

    def validate_capacity(evidence: Path) -> None:
        state["capacity_validations"] += 1
        state["order"].append("capacity")
        if json.loads(evidence.read_text(encoding="utf-8"))["age_seconds"] > 600:
            raise ValueError("Capacity evidence is not current")

    def settle(
        runner: Any,
        frozen: Any,
        source: Path,
        work: Path,
        _schedule: Any,
        _admission: Any,
        prior: list[dict[str, Any]],
        event: dict[str, Any],
        evidence: Path,
        ack: Path,
        timeout: float,
        runtime: Any,
    ) -> list[dict[str, Any]]:
        assert runner == "frozen-successor-runner"
        assert frozen == {"source": "frozen"}
        assert source == roots["source"] and work == roots["work"]
        assert evidence == capacity and ack == acknowledgement and timeout == 7
        assert runtime == binding["runtime"]
        state["native_commands"] += 1
        state["order"].append("settle")
        validate_capacity(evidence)
        return [*prior, event]

    v8 = SimpleNamespace(
        DISCLOSURE_ACK="disclosure-acknowledgement.json",
        _external=lambda value: Path(value),
        _work_path=lambda work, *parts, **_kwargs: Path(work).joinpath(*parts),
        _validate_disclosure_ack=validate_ack,
        _require_clean_pushed=lambda: state["order"].append("clean"),
        _verify_prepared=verify_prepared,
        _accepted=accepted,
        _validate_contact_sessions=contact,
        _require_no_orphan_output_cells=orphan,
        _plain_path=lambda value: Path(value),
        read_json=lambda _path: {"source": "frozen"},
        _runtime_projection=runtime_projection,
        validate_capacity_evidence=validate_capacity,
        _settle_one=settle,
        _load_hbq_runner=lambda: SimpleNamespace(RetryDisclosurePause=_RetryPause),
    )

    exact = SimpleNamespace()

    def load_pinned_modules(_runtime: Path) -> tuple[Any, Any, Path, Path]:
        state["module_load_calls"] += 1
        state["order"].append("load-modules")
        return guard, v8, roots["runtime"], roots["runtime"] / "executor.py"

    exact._load_pinned_modules = load_pinned_modules
    exact._load_pinned_successor_runner = lambda *_args: (
        state["order"].append("runner") or "frozen-successor-runner"
    )
    exact.RetryPauseTerminal = RuntimeError

    query = SimpleNamespace()

    def query_binding(_binding: Path, _runtime: Path) -> None:
        state["query_binding_calls"] += 1
        state["order"].append("query-binding")

    def load_exact() -> Any:
        state["exact_load_calls"] += 1
        state["order"].append("load-exact")
        return exact

    query._binding = query_binding
    query.load_query_only_exact_one = load_exact
    monkeypatch.setattr(module, "_load_query_only", lambda: query)

    def supplier() -> Path:
        state["supplier_paths"].append(capacity)
        state["order"].append("supplier")
        return capacity

    kwargs = {
        "binding_root": roots["binding"],
        "source_root": roots["source"],
        "closed_root": roots["closed"],
        "v7_root": roots["v7"],
        "work_root": roots["work"],
        "guard_root": roots["guard"],
        "disclosure_ack": acknowledgement,
        "capacity_supplier": supplier,
        "allow_remote": True,
        "timeout": 7,
        "v8_runtime_root": roots["runtime"],
    }
    return state, roots, kwargs


def test_late_supplier_is_one_shot_after_final_verify_and_no_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _adapter()
    state, _roots, kwargs = _harness(module, tmp_path, monkeypatch)
    result = module.dispatch_one(**kwargs)
    assert result == [
        {
            "sequence": 182,
            "item_id": "item-182",
            "arm_id": "native",
            "repetition": 1,
            "payload": {"prompt_sha256": "1" * 64},
        },
        {
            "sequence": 183,
            "item_id": "item-183",
            "arm_id": "native",
            "repetition": 1,
            "payload": {"prompt_sha256": "2" * 64},
        },
    ]
    assert state["claims"] == state["native_commands"] == 1
    assert len(state["supplier_paths"]) == 1
    assert state["provider_attempts"] == 0
    assert state["contact_lengths"] == [1, 2]
    assert state["order"].count("postflight") == 1
    assert state["accepted_calls"] == 1
    assert state["query_binding_calls"] == 1
    assert state["exact_load_calls"] == 1
    assert state["module_load_calls"] == 1
    supplier = state["order"].index("supplier")
    settle = state["order"].index("settle")
    assert settle < state["order"].index("postflight")
    assert state["order"].index("accepted") < state["order"].index("runner") < supplier < settle
    assert state["order"][supplier + 1 : settle] == ["capacity"]
    with pytest.raises(ValueError, match="claim"):
        module.dispatch_one(**kwargs)
    assert state["claims"] == state["native_commands"] == 1
    assert len(state["supplier_paths"]) == 1
    assert state["capacity_validations"] == 2
    assert state["exact_load_calls"] == 2
    assert state["query_binding_calls"] == state["module_load_calls"] == 2


def test_guard_postflight_rejects_drift_without_resending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _adapter()
    state, _roots, kwargs = _harness(module, tmp_path, monkeypatch, drift="postflight")
    with pytest.raises(ValueError, match="guard postflight"):
        module.dispatch_one(**kwargs)
    assert state["claims"] == state["native_commands"] == 1
    assert len(state["supplier_paths"]) == 1
    assert state["contact_lengths"] == [1, 2]
    assert state["order"].index("settle") < state["order"].index("postflight")
    with pytest.raises(ValueError, match="claim"):
        module.dispatch_one(**kwargs)
    assert state["claims"] == state["native_commands"] == 1
    assert len(state["supplier_paths"]) == 1


@pytest.mark.parametrize(
    "capacity_age, expected",
    [(601, "reject"), (1, "pass")],
    ids=["preflight-over-600-stale-reject", "preflight-over-600-late-fresh-pass"],
)
def test_late_capacity_recheck_is_not_aged_preflight_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capacity_age: int,
    expected: str,
) -> None:
    module = _adapter()
    state, _roots, kwargs = _harness(
        module, tmp_path, monkeypatch, capacity_age=capacity_age
    )
    if expected == "reject":
        with pytest.raises(ValueError, match="current"):
            module.dispatch_one(**kwargs)
        assert state["preflight_age_seconds"] > 600
        assert state["claims"] == 1
        assert state["native_commands"] == 0
        assert len(state["supplier_paths"]) == 1
    else:
        assert module.dispatch_one(**kwargs)[-1]["sequence"] == 183
        assert state["preflight_age_seconds"] > 600
        assert state["claims"] == state["native_commands"] == 1
        assert len(state["supplier_paths"]) == 1
        assert state["capacity_validations"] == 2


@pytest.mark.parametrize(
    "drift",
    ["event", "source", "runtime", "ack", "payload"],
    ids=["event-drift", "source-drift", "runtime-drift", "ack-drift", "payload-drift"],
)
def test_final_verification_drift_blocks_supplier_and_native_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    module = _adapter()
    state, _roots, kwargs = _harness(module, tmp_path, monkeypatch, drift=drift)
    with pytest.raises(ValueError):
        module.dispatch_one(**kwargs)
    assert state["claims"] == 1
    assert state["native_commands"] == 0
    assert state["provider_attempts"] == 0
    assert state["supplier_paths"] == []
