from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v1"
CANDIDATES = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-candidates-v1"
BROADER = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(name, None)
    return value


def module():
    return load(PACKAGE / "executor.py", "_desc13_lower_step_exec_test")


def candidate_study():
    return load(CANDIDATES / "study.py", "_desc13_lower_step_candidates_test")


def broader_study():
    return load(BROADER / "study.py", "_desc13_lower_step_broader_test")


def frozen_roots(tmp_path: Path) -> tuple[Path, Path]:
    candidate = tmp_path / "candidate-freeze"
    candidate_study().freeze(output_root=candidate)
    development = tmp_path / "development-freeze"
    broader_study().freeze(output_root=development, normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    return candidate, development


def route_provider(counter: dict[str, int] | None = None):
    route = {
        "name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec",
        "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True,
        "health": "healthy", "reasoning_effort": "high", "grok_command": ["fixture"],
        "allowed_payload_classes": ["public_repo", "public_synthetic"], "timeout_seconds": 1.0,
    }
    evidence = {"kind": "fixture-current-zero-charge-proof"}
    lock = threading.Lock()

    def provider(_queue: Path):
        if counter is not None:
            with lock:
                counter["active"] = counter.get("active", 0) + 1
                counter["maximum"] = max(counter.get("maximum", 0), counter["active"])
            time.sleep(0.003)
            with lock:
                counter["active"] -= 1
                counter["calls"] = counter.get("calls", 0) + 1
        return route, evidence

    return provider


def runner(value, *, fail_after_contact: bool = False, concurrency: dict[str, int] | None = None):
    calls = {"count": 0}
    guard = threading.Lock()

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        with guard:
            calls["count"] += 1
        if concurrency is not None:
            with guard:
                concurrency["active"] = concurrency.get("active", 0) + 1
                concurrency["maximum"] = max(concurrency.get("maximum", 0), concurrency["active"])
        try:
            schema = json.loads(schema_path.read_bytes())
            assert schema["required"] == ["scores", "evidence", "coverage"]
            responses = output_dir / "responses"
            responses.mkdir()
            before_contact()
            if fail_after_contact:
                raise RuntimeError("postlaunch")
            (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
            scores = {key: 3.0 for key in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}
            token = hashlib.sha256(prompt + str(output_dir).encode()).hexdigest()
            response = value.canonical({"requestId": "request-" + token, "sessionId": "session-" + token, "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": {"scores": scores, "evidence": {key: "fixture" for key in scores}, "coverage": {key: True for key in scores}}})
            (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
            settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}
            return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": "request-" + token, "session_id": "session-" + token, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": settings}
        finally:
            if concurrency is not None:
                with guard:
                    concurrency["active"] -= 1

    return run, calls


def common(tmp_path: Path):
    candidate, development = frozen_roots(tmp_path)
    return {"output_root": tmp_path / "output", "candidate_freeze_root": candidate, "development_freeze_root": development, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": route_provider()}


def _leaves(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, (*prefix, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, (*prefix, index))
    else:
        yield prefix, value


def _replace(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


def _different(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "-tampered"
    raise TypeError("unexpected contract leaf type")


def test_every_frozen_contract_leaf_is_exactly_enforced(monkeypatch: pytest.MonkeyPatch):
    value = module()
    expected = value._expected_contract()
    schedule = {"geometry": expected["geometry"], "candidate_freeze_manifest_sha256": value.CANDIDATE_MANIFEST_SHA256}
    value._validate_contract(schedule)
    for path, original in _leaves(expected):
        tampered = deepcopy(expected)
        _replace(tampered, path, _different(original))
        monkeypatch.setattr(value, "contract", lambda tampered=tampered: tampered)
        with pytest.raises(ValueError, match="contract"):
            value._validate_contract(schedule)


def test_prepare_materializes_exact_five_by_seven_scoring_payloads_without_contact(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 35
    assert prepared["effective_candidates"] == 5
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    schedule = json.loads((args["output_root"] / "schedule.json").read_bytes())
    rebuilt = value.build_schedule(candidate_freeze_root=args["candidate_freeze_root"], development_freeze_root=args["development_freeze_root"])
    assert schedule == rebuilt and schedule["geometry"]["grok_cells"] == 35
    assert {row["candidate_id"] for row in schedule["cells"]} == {row["candidate_id"] for row in schedule["candidates"]}
    assert {row["prompt_group_id"] for row in schedule["cells"]} == {row["prompt_group_id"] for row in schedule["groups"]}
    assert all((args["output_root"] / row["cell_id"] / "outbound-payload.json").read_bytes() == base64.b64decode(row["payload_base64"], validate=True) for row in schedule["cells"])
    assert "import dspy" not in (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import optuna" not in (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()


def test_wave_uses_one_serialized_route_load_and_never_exceeds_ten_native_lanes(tmp_path: Path):
    value, args = module(), common(tmp_path)
    value.prepare_all(**args)
    route_counter: dict[str, int] = {}
    concurrency: dict[str, int] = {}
    fake, calls = runner(value, concurrency=concurrency)
    rows = asyncio.run(value.execute_wave(**{**args, "route_provider": route_provider(route_counter)}, allow_remote=True, runner=fake))
    assert len(rows) == calls["count"] == 35
    assert 1 <= concurrency["maximum"] <= 10
    assert route_counter["maximum"] == 1 and route_counter["calls"] == 1
    collector = tmp_path / "collector.json"
    finalized = value.finalize_collector(**{key: item for key, item in args.items() if key not in {"queue_root", "route_provider"}}, collector_output=collector)
    assert finalized["cells"] == 35
    assert value.replay_collector(output_root=args["output_root"], candidate_freeze_root=args["candidate_freeze_root"], development_freeze_root=args["development_freeze_root"], collector_path=collector)["equal_group_projection_ready"] is True


def test_postlaunch_ambiguity_is_terminal_and_repeated_worker_is_idle(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    fake, calls = runner(value, fail_after_contact=True)
    cell = prepared["prepared_cells"][0]
    first = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=fake)
    assert first["kind"] == "reconcile_required_after_process_launch" and calls["count"] == 1
    second = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=fake)
    assert second["state"] == "terminal" and calls["count"] == 1


def test_callback_rejects_mutation_of_every_prepared_artifact_before_launch(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    root = args["output_root"] / prepared["prepared_cells"][0]
    artifacts = sorted(path.name for path in root.iterdir())
    assert artifacts == sorted(value.v3_runtime()._runtime().lifecycle().PREPARED)
    calls = 0
    for cell, artifact in zip(prepared["prepared_cells"][:len(artifacts)], artifacts, strict=True):
        def mutate_before_contact(*, output_dir: Path, before_contact, artifact=artifact, **_kwargs):
            nonlocal calls
            calls += 1
            (output_dir / "responses").mkdir()
            path = output_dir / artifact
            path.write_bytes(path.read_bytes() + b" ")
            before_contact()
            raise AssertionError("callback must reject mutation before contact")

        result = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=mutate_before_contact)
        assert result["kind"] == "definitely_not_contacted"
        assert result["provider_calls_made"] == result["process_launches"] == 0
        assert not (args["output_root"] / cell / "launch-intent.json").exists()
    assert calls == len(artifacts)


def test_callback_rejects_prepared_artifact_reparse_before_launch(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    cell = prepared["prepared_cells"][0]

    def reparse_before_contact(*, output_dir: Path, before_contact, **_kwargs):
        target = output_dir / "response-schema.json"
        staged = output_dir.parent / "response-schema.staged"
        target.replace(staged)
        try:
            os.symlink(staged, target)
        except OSError:
            pytest.skip("symlink privilege is unavailable")
        (output_dir / "responses").mkdir()
        before_contact()
        raise AssertionError("callback must reject reparse before contact")

    result = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=reparse_before_contact)
    assert result["kind"] == "definitely_not_contacted"
    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert not (args["output_root"] / cell / "launch-intent.json").exists()


def test_prepared_reparse_and_freeze_mutation_are_rejected_before_runner_contact(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    fake, calls = runner(value)
    cell = prepared["prepared_cells"][0]
    path = args["output_root"] / cell / "outbound-payload.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="prepared binding|pristine"):
        value.execute_one(**args, cell_id=cell, allow_remote=True, runner=fake)
    assert calls["count"] == 0
    rebuilt = value.build_schedule(candidate_freeze_root=args["candidate_freeze_root"], development_freeze_root=args["development_freeze_root"])
    manifest = json.loads((args["candidate_freeze_root"] / "manifest.json").read_bytes())
    manifest["manifest_sha256"] = "0" * 64
    (args["candidate_freeze_root"] / "manifest.json").write_bytes(value.canonical(manifest))
    with pytest.raises(ValueError, match="manifest|candidate"):
        value.build_schedule(candidate_freeze_root=args["candidate_freeze_root"], development_freeze_root=args["development_freeze_root"])
    assert rebuilt["geometry"]["grok_cells"] == 35
