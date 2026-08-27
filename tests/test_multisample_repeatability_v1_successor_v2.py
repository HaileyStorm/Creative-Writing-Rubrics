from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v2" / "run_successor.py"


def _module():
    spec = importlib.util.spec_from_file_location("multisample_successor_v2_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _event(item_id: str = "hanna-523") -> dict[str, object]:
    return {"sequence": 181, "item_id": item_id, "arm_id": "hbq_short_story_batch32", "repetition": 1}


def _frozen(item_id: str = "hanna-523") -> dict[str, object]:
    return {"contract": {"provider": {"model": "gpt-5.6-sol", "reasoning": "high"}, "arms": [{"arm_id": "hbq_short_story_batch32", "kind": "comparison", "bundle_id": "prose.short_story", "batch_size": 32, "batch_attempts": 3}]}}


def _profile() -> dict[str, object]:
    return {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "paid_api": False, "human_judgment": False}


def _cell(event: dict[str, object], *, hbq: bool = True) -> dict[str, object]:
    request = {"prompt_utf8": "complete rendered prompt", "response_schema_utf8": "{\"type\":\"object\"}"}
    payload: dict[str, object] = {"batch": 1, "request": request}
    if hbq:
        payload["question_ids"] = ["q-1"]
    payload["payload_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    artifacts = [{"role": "artifact"}, {"role": "originating_prompt"}]
    rubric = [{"role": "rubric"}]
    if hbq:
        artifacts.append({"role": "task_contract"})
        rubric.extend([{"role": "rubric_registry"}, {"role": "rubric_bundle"}, {"role": "judge_instruction"}])
    return {**event, "outbound_artifacts": artifacts, "payload": {"provider_payloads": [payload], "rubric": rubric}}


def _inputs(tmp_path: Path, item_id: str) -> tuple[Path, Path]:
    folder = tmp_path / "predecessor" / "inputs" / item_id
    folder.mkdir(parents=True)
    (folder / "source.md").write_text("source\n", encoding="utf-8")
    (folder / "prompt.md").write_text("prompt\n", encoding="utf-8")
    task = {
        "artifact_id": item_id,
        "contract_id": "hanna",
        "context": {"artifact_kind": "short prose fiction", "declared_scope": "complete short story"},
    }
    task_path = folder / "task-contract.json"
    task_path.write_bytes(_canonical(task))
    return folder.parents[1], task_path


def _override(path: Path, task_path: Path, *, item_id: str, bundle_id: str = "prose.short_story") -> Path:
    path.write_bytes(_canonical({
        "format_version": 1,
        "artifact_id": item_id,
        "bundle_id": bundle_id,
        "task_contract_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "contract_id": "hanna",
        "artifact_kind": "short prose fiction",
        "declared_scope": "complete short story",
        "compatibility_mode": "reviewed_override",
        "decision_id": f"review-{item_id}",
        "reviewer": "operator",
        "reason": "Reviewed complete short story scope.",
    }))
    return path


def _context(*, question_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
        "batch": {"number": 1, "question_ids": question_ids},
        "attempt": {"number": 1},
        "prompt": {"encoding": "utf-8", "text": "complete rendered prompt"},
        "response_schema": {"encoding": "utf-8", "text": "{\"type\":\"object\"}"},
    }


def test_direct_module_load_and_runtime_identity_bind_actual_helper_bytes() -> None:
    runner = _module()
    identity = runner.runtime_identity()
    assert identity["helper_id"] == runner.HELPER_ID
    assert identity["path"] == "run_successor.py"
    assert identity["bytes"] == RUNNER.stat().st_size
    assert identity["sha256"] == hashlib.sha256(RUNNER.read_bytes()).hexdigest()


def test_two_hbq_artifacts_receive_their_own_exact_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    captured: list[dict[str, object]] = []
    boundary: list[dict[str, object]] = []

    def fake_judge(**kwargs):
        captured.append(kwargs)
        kwargs["before_provider_attempt"](_context(question_ids=["q-1"]))

    monkeypatch.setattr(runner, "run_judge", fake_judge)
    for item_id in ("hanna-523", "hanna-52"):
        source, task = _inputs(tmp_path / item_id, item_id)
        event = _event(item_id)
        override = _override(tmp_path / f"{item_id}.json", task, item_id=item_id)
        runner.dispatch_event(event=event, frozen=_frozen(item_id), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: boundary.append(dict(commitments)))

    assert [call["scope_compatibility_override_path"] for call in captured] == [str((tmp_path / "hanna-523.json").absolute()), str((tmp_path / "hanna-52.json").absolute())]
    assert [value["dependencies"]["scope_compatibility_override"]["path"] for value in boundary] == [str((tmp_path / "hanna-523.json").absolute()), str((tmp_path / "hanna-52.json").absolute())]
    assert all(value["disclosed_cell_sha256"] == hashlib.sha256(_canonical(_cell(_event(item_id)))).hexdigest() for value, item_id in zip(boundary, ("hanna-523", "hanna-52")))


@pytest.mark.parametrize("mutate", ["missing", "wrong_bundle", "task_drift"])
def test_invalid_hbq_binding_fails_before_provider_or_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate: str) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")
    if mutate == "missing":
        override = None
    elif mutate == "wrong_bundle":
        override = _override(tmp_path / "wrong.json", task, item_id="hanna-523", bundle_id="prose.scene")
    else:
        task.write_bytes(task.read_bytes() + b" ")
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: pytest.fail("invalid binding reached provider route"))

    with pytest.raises(ValueError, match="override|Override"):
        runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: None)
    assert not (tmp_path / "work").exists()


def test_preflight_payload_mismatch_fails_at_the_provider_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")

    def fake_judge(**kwargs):
        with pytest.raises(ValueError, match="acknowledged preflight payload"):
            kwargs["before_provider_attempt"](_context(question_ids=["wrong-question"]))

    monkeypatch.setattr(runner, "run_judge", fake_judge)
    runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: None)


def test_incomplete_preflight_disclosure_is_rejected_before_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")
    disclosure = _cell(event)
    disclosure["outbound_artifacts"] = [{"role": "artifact"}]
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: pytest.fail("incomplete disclosure reached provider route"))

    with pytest.raises(ValueError, match="omits an outbound artifact"):
        runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=disclosure, disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: None)


def test_exact_five_field_profile_is_required_before_provider_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")
    profile = _profile()
    profile.pop("human_judgment")
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: pytest.fail("profile mismatch reached provider route"))

    with pytest.raises(ValueError, match="profile does not bind"):
        runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=profile, scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: None)


def test_native_adapter_invokes_the_bound_hook_before_each_physical_attempt(tmp_path: Path) -> None:
    runner = _module()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    frozen = {"contract": {"provider": {"model": "gpt-5.6-sol", "reasoning": "high"}, "arms": [{"arm_id": "compact_analytic", "kind": "native", "prompt": "native-prompt.md", "schema": "native-schema.json"}]}}
    source, _ = _inputs(tmp_path, "hanna-52")
    rubric_root = tmp_path / "hbq-multisample-repeatability-v1"
    rubric_root.mkdir()
    (rubric_root / "native-prompt.md").write_text("native rubric", encoding="utf-8")
    (rubric_root / "native-schema.json").write_text("{}", encoding="utf-8")
    order: list[str] = []

    class PredecessorRunner:
        HERE = tmp_path / "successor"

        @staticmethod
        def _artifact_prompt(*args):
            return "complete rendered prompt"

        @staticmethod
        def _provider_response_schema(value):
            return value

        @staticmethod
        def _structured_json_bytes(value):
            return b"{}"

        @staticmethod
        def _v1_runner():
            return object()

        @staticmethod
        def _next_codex_message_attempt(*args):
            return order.count("physical-contact") + 1

        @staticmethod
        def _run_structured_pass(**kwargs):
            order.append("physical-contact")
            kwargs["pass_dir"].mkdir(parents=True, exist_ok=True)
            (kwargs["pass_dir"] / "pass.json").write_text("{}", encoding="utf-8")
            (kwargs["pass_dir"] / "response.json").write_text("{}", encoding="utf-8")
            return {"attempt": order.count("physical-contact")}

        @staticmethod
        def _semantic_native(*args):
            if order.count("physical-contact") == 1:
                raise ValueError("first result rejected")

        @staticmethod
        def _reject_structured_checkpoint(output, **kwargs):
            (output / "response.json").unlink()
            attempts = output / "attempts"
            attempts.mkdir(exist_ok=True)
            (attempts / "rejected-0001.json").write_text(json.dumps({"reason": kwargs["reason"], "response": {"content": "rejected"}}), encoding="utf-8")

    disclosure = _cell(event, hbq=False)
    payload = disclosure["payload"]["provider_payloads"][0]
    payload["request"] = {"prompt_utf8": "complete rendered prompt", "response_schema_utf8": "{}"}
    payload["question_ids"] = []
    payload["payload_sha256"] = hashlib.sha256(_canonical({"batch": 1, "request": payload["request"], "question_ids": []})).hexdigest()

    def faithful_v7_hook(context):
        order.append("hook")
        assert isinstance(context["batch"]["question_ids"], list)
        if context["attempt"]["number"] == 2:
            assert context["prompt"]["sha256"] != context["prompt"]["base_prompt_sha256"]
            assert context["validation_feedback"]["rejected_checkpoint_sha256"] == context["rejected_chain"]["head_sha256"]
            assert context["rejected_chain"]["count"] == 1
            assert len(context["rejected_chain"]["records"]) == 1

    with pytest.raises(runner.NativeRetryDisclosurePause) as paused:
        runner.dispatch_event(event=event, frozen=frozen, predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=disclosure, disclosure_profile=_profile(), predecessor_runner=PredecessorRunner(), before_provider_attempt=faithful_v7_hook, provider_boundary_check=lambda context, commitments: None)
    assert paused.value.context["attempt"]["number"] == 2
    result = runner.dispatch_event(event=event, frozen=frozen, predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=disclosure, disclosure_profile=_profile(), predecessor_runner=PredecessorRunner(), before_provider_attempt=faithful_v7_hook, provider_boundary_check=lambda context, commitments: None)
    assert result == tmp_path / "work" / "runs" / "hanna-52" / "compact_analytic" / "run-01" / "pass.json"
    assert result.is_file()
    assert (result.parent / "retry-attempts" / "attempt-0001" / "pass.json").is_file()
    assert order == ["hook", "physical-contact", "hook", "hook", "physical-contact"]


def test_reparse_override_is_rejected_before_read_or_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")
    original = runner._is_reparse
    monkeypatch.setattr(runner, "_is_reparse", lambda path: path == override.absolute() or original(path))
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: pytest.fail("reparse override reached provider route"))

    with pytest.raises(ValueError, match="symlink/reparse"):
        runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: None)


def test_override_and_task_contract_are_read_once_per_validation_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")
    original = Path.read_bytes
    reads: dict[Path, int] = {}

    def tracked(path: Path) -> bytes:
        if path in {override, task}:
            reads[path] = reads.get(path, 0) + 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: kwargs["before_provider_attempt"](_context(question_ids=["q-1"])))
    runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: None, provider_boundary_check=lambda context, commitments: None)
    assert reads == {override: 2, task: 2}


def test_provider_boundary_recheck_rejects_dependency_drift_before_outer_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module()
    source, task = _inputs(tmp_path, "hanna-523")
    event = _event()
    override = _override(tmp_path / "override.json", task, item_id="hanna-523")
    outer_calls: list[object] = []

    def fake_judge(**kwargs):
        override.write_bytes(override.read_bytes() + b" ")
        kwargs["before_provider_attempt"](_context(question_ids=["q-1"]))

    monkeypatch.setattr(runner, "run_judge", fake_judge)
    with pytest.raises(ValueError, match="Provider-boundary dependency drifted"):
        runner.dispatch_event(event=event, frozen=_frozen(), predecessor_root=source, work=tmp_path / "work", timeout=30.0, disclosed_cell=_cell(event), disclosure_profile=_profile(), scope_compatibility_override_path=override, before_provider_attempt=lambda context: outer_calls.append(context), provider_boundary_check=lambda context, commitments: outer_calls.append(commitments))
    assert outer_calls == []
