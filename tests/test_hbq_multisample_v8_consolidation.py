from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1" / "consolidate_v8.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("consolidate_v8_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def _bypass_repository_tree_scan(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    plain_tree = module._plain_tree
    repository_root = module.HERE.parent.parent.absolute()

    def fixture_plain_tree(root: Path, label: str) -> Path:
        if Path(root).absolute() == repository_root:
            return repository_root
        return plain_tree(root, label)

    monkeypatch.setattr(module, "_plain_tree", fixture_plain_tree)


def _reconstruction_fixture(
    module: ModuleType, tmp_path: Path, *, corrupt: bool = False
) -> tuple[Path, Path, dict[str, bytes]]:
    original_root = tmp_path / "original"
    historical_core_root = tmp_path / "historical-core"
    blobs: dict[str, bytes] = {}
    runtime_rows: list[dict[str, Any]] = []
    for relative, source in sorted(module.GIT_RUNTIME_SOURCES.items()):
        raw = f"fixture local blob {relative}\n".encode()
        blobs[source["oid"]] = raw
        value = module._reconstruction_bytes(raw, source["transform"])
        runtime_rows.append({"path": relative, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()})
    for relative, support in sorted(module.SUPPORT_FILES.items()):
        raw = (ROOT / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != support["sha256"]:
            raw = raw.replace(b"\r\n", b"\n")
        assert len(raw) == support["bytes"]
        assert hashlib.sha256(raw).hexdigest() == support["sha256"]
        blobs[support["oid"]] = raw
    core_path = historical_core_root / module.RETAINED_CORE_RELATIVE
    core_path.parent.mkdir(parents=True)
    core_path.write_bytes(b"retained historical core fixture\n")
    runtime_rows.append(
        {
            "path": module.RETAINED_CORE_RELATIVE,
            "bytes": core_path.stat().st_size,
            "sha256": _sha(core_path),
        }
    )
    runtime_rows.sort(key=lambda row: row["path"])
    if corrupt:
        runtime_rows[0] = {**runtime_rows[0], "sha256": "0" * 64}
    _write_json(
        original_root / "frozen-run-contract.json",
        {
            "runtime_files": runtime_rows,
            "runtime_sha256": hashlib.sha256(module._canonical(runtime_rows)).hexdigest(),
        },
    )
    return original_root, historical_core_root, blobs


def _event_fixture(module: ModuleType) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    arms = [
        {"arm_id": "hbq_short_story_batch32", "kind": "hbq", "native_scale": [0, 10]},
        *[
            {"arm_id": f"native-arm-{index}", "kind": "native", "native_scale": [0, 10]}
            for index in range(2, 7)
        ],
    ]
    samples = [
        {
            "item_id": item_id,
            "model": "fixture-model",
            "prompt_sha256": hashlib.sha256(item_id.encode()).hexdigest(),
            "human_overall": 3.0,
            "frozen_quality_band": "middle",
        }
        for item_id in ("item-01", "item-02", "item-03", "item-04", "item-05", "item-06", "hanna-523", "hanna-594", "hanna-731", "hanna-817", "hanna-907")
    ]
    schedule = [
        {"item_id": sample["item_id"], "arm_id": arms[(repetition - 1 + position) % len(arms)]["arm_id"], "repetition": repetition}
        for sample in samples
        for repetition in range(1, 6)
        for position in range(len(arms))
    ]
    events = [{"sequence": index, **event} for index, event in enumerate(schedule, 1)]
    assert len(events) == module.CELL_COUNT
    assert events[180] == module.MISSING_181
    return {
        "study_id": "consolidation-provider-free-fixture",
        "schedule": schedule,
        "samples": samples,
        "contract": {
            "arms": arms,
            "repetitions": 5,
            "primary_metrics": {"bootstrap": {"seed": 560820}},
        },
        "full_development_quality_cutpoints": {"fixture": True},
    }, events


def _binding(root: Path, event: dict[str, Any]) -> Path:
    filename = "run.json" if event["arm_id"] == "hbq_short_story_batch32" else "pass.json"
    return root / "runs" / event["item_id"] / event["arm_id"] / f"run-{event['repetition']:02d}" / filename


def _write_run(root: Path, event: dict[str, Any]) -> Path:
    path = _binding(root, event)
    _write_json(path, {"fixture_sequence": event["sequence"]})
    return path


def _completion(event: dict[str, Any], path: Path) -> dict[str, Any]:
    return {"event": "completed", **event, "run_binding_sha256": _sha(path)}


def _fake_analyzer(frozen: dict[str, Any], *, duplicate_sessions: bool = False) -> Any:
    def validate(original_root: Path, data_dir: Path) -> dict[str, Any]:
        assert (original_root / "inputs" / "immutable-input.txt").read_bytes() == b"original-input-bytes\n"
        assert data_dir.is_dir()
        return frozen

    def load_run(work: Any, sample: dict[str, Any], arm: dict[str, Any], repetition: int) -> tuple[float, list[str], list[str], None, None]:
        assert (work / "inputs" / "immutable-input.txt").read_bytes() == b"original-input-bytes\n"
        filename = "run.json" if arm["kind"] == "hbq" else "pass.json"
        binding = work / "runs" / sample["item_id"] / arm["arm_id"] / f"run-{repetition:02d}" / filename
        sequence = json.loads(binding.read_text(encoding="utf-8"))["fixture_sequence"]
        session = "duplicate-session" if duplicate_sessions else f"session-{sequence}"
        return float(sequence % 11), [session], [f"commitment-{sequence}"], None, None

    def numeric_metrics(values: list[float], scale: list[int]) -> dict[str, Any]:
        return {
            "values": values,
            "exact_all_repetition_agreement": True,
            "modal_proportion": 1.0,
            "pairwise_exact_agreement": 1.0,
            "normalized_sample_sd": 0.0,
            "normalized_mapd": 0.0,
            "normalized_range": 0.0,
        }

    return SimpleNamespace(
        validate=validate,
        _load_run=load_run,
        _numeric_metrics=numeric_metrics,
        _scale=lambda arm_id: [0, 10],
        _quality=lambda rows, repetitions: {"fixture": True},
        _bootstrap=lambda rows_by_arm, seed, draws: {"fixture": True},
        _derived_prompt_variant_cells=[],
        statistics=statistics,
    )


def _admission_stubs(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    roots: dict[str, Path],
    events: list[dict[str, Any]],
    state: dict[str, list[Any]],
    *,
    terminal_valid: bool,
    normalization_valid: bool,
) -> None:
    admission = {"sequence": 182, "settlement_sha256": "fixture-settlement"}

    class Guard:
        def _assert_no_unresolved_v8_state(self, v8: Any, work: Path) -> None:
            assert work == roots["v8"]
            state["terminal"].append("guard_clear")

        def preflight(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["guard_root"] == roots["guard"]
            assert kwargs["v8_runtime_root"] == roots["runtime"]
            state["terminal"].append("preflight")
            if terminal_valid:
                raise ValueError("V8 has no untouched sequence remaining")
            return {}

        def _guard_binding(self, guard_root: Path) -> dict[str, str]:
            assert guard_root == roots["guard"]
            state["terminal"].append("guard_binding")
            return {"v8_identity": "fixture-identity", "v8_prepared_runtime_projection": "pinned-fixture-runtime"}

        def _canonical_runtime(self, runtime: Path) -> tuple[Path, object]:
            assert runtime == roots["runtime"]
            state["terminal"].append("canonical_runtime")
            return runtime, runner

        def _v8_static_identity(self, v8: Any, runtime: Path, executor: object, work: Path) -> str:
            assert (v8, runtime, executor, work) == (state["v8"][0], roots["runtime"], runner, roots["v8"])
            state["terminal"].append("static_identity")
            return "fixture-identity"

        def _validate_guard_journal(self, guard_root: Path, accepted: list[dict[str, Any]], sentinel: dict[str, int]) -> set[int]:
            assert guard_root == roots["guard"] and accepted == events[181:] and sentinel == {"sequence": -1}
            state["terminal"].append("guard_journal")
            return {330}

        def _validate_claims(self, guard_root: Path, accepted: list[dict[str, Any]], sentinel: dict[str, int], completed: set[int]) -> None:
            assert guard_root == roots["guard"] and accepted == events[181:] and sentinel == {"sequence": -1} and completed == {330}
            state["terminal"].append("claims")

        def _recompute_contacts(self, v8: Any, work: Path, accepted: list[dict[str, Any]]) -> int:
            assert (v8, work, accepted) == (state["v8"][0], roots["v8"], events[181:])
            state["terminal"].append("contacts_recomputed")
            return 148

    class V8:
        JOURNAL = "execution-journal.jsonl"

        def _verify_prepared(self, original: Path, closed: Path, v7: Path, v8: Path) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, Any]]:
            assert (original, closed, v7, v8) == (roots["original"], roots["closed"], roots["v7"], roots["v8"])
            state["terminal"].append("verify_prepared")
            return {"runtime": "pinned-fixture-runtime"}, events[181:], admission

        def _accepted(self, work: Path, schedule: list[dict[str, Any]], received_admission: dict[str, Any]) -> list[dict[str, Any]]:
            assert work == roots["v8"] and schedule == events[181:] and received_admission == admission
            state["terminal"].append("accepted")
            return events[181:]

        def _validate_contact_sessions(self, original: Path, work: Path, received_admission: dict[str, Any], accepted: list[dict[str, Any]]) -> None:
            assert (original, work, received_admission, accepted) == (roots["original"], roots["v8"], admission, events[181:])
            state["terminal"].append("contacts")

    runner = object()
    guard, v8 = Guard(), V8()
    state["v8"].append(v8)

    def query_safe(runtime: Path, query_binding: Path) -> tuple[Any, Any]:
        assert runtime == roots["runtime"] and query_binding == roots["query"]
        state["query"].append((runtime, query_binding))
        return guard, v8

    def validate_normalization(received_runner: object, destination: Path, source: str) -> None:
        assert received_runner is runner
        item_id = destination.parents[1].name
        assert source == f"fixture-source-{item_id}\n"
        assert isinstance(json.loads((destination / "pass.json").read_text(encoding="utf-8"))["fixture_sequence"], int)
        state["phases"].append("native_normalization")
        state["normalizations"].append(destination)
        if not normalization_valid:
            raise ValueError("fixture normalization rejected raw run")

    monkeypatch.setattr(module, "_v8_runtime_dir", lambda runtime: runtime)
    monkeypatch.setattr(module, "_load_query_safe_v8", query_safe)
    monkeypatch.setattr(module, "_verify_missing181_receipt", lambda root, runtime: state["receipts"].append((root, runtime)))
    monkeypatch.setattr(module, "_load_frozen_successor_normalizer", lambda runtime: SimpleNamespace(_v1_runner=lambda: runner, _validate_normalization=validate_normalization))


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    duplicate_sessions: bool = False,
    terminal_valid: bool = True,
    normalization_valid: bool = True,
) -> tuple[ModuleType, dict[str, Path], list[dict[str, Any]], dict[int, str], dict[str, list[Any]]]:
    module = _module()
    _bypass_repository_tree_scan(module, monkeypatch)
    frozen, events = _event_fixture(module)
    roots = {name: tmp_path / name for name in ("original", "closed", "v4", "v6", "v7", "missing181", "v8", "guard", "query")}
    original, closed, v4, v6, v7, missing181, v8 = (roots[name] for name in ("original", "closed", "v4", "v6", "v7", "missing181", "v8"))
    original.mkdir(parents=True)
    (original / "inputs").mkdir()
    (original / "inputs" / "immutable-input.txt").write_bytes(b"original-input-bytes\n")
    for item_id in {event["item_id"] for event in events}:
        source_path = original / "inputs" / item_id / "source.md"
        source_path.parent.mkdir()
        source_path.write_text(f"fixture-source-{item_id}\n", encoding="utf-8", newline="\n")
    _write_json(original / "frozen-run-contract.json", frozen)

    bindings: dict[int, str] = {}
    for event in events[:76]:
        path = _write_run(original, event)
        bindings[event["sequence"]] = _sha(path)
    _write_jsonl(
        original / "schedule-journal.jsonl",
        [{"event": "planned", **event} for event in events]
        + [_completion(event, _binding(original, event)) for event in events[:76]],
    )

    for event in events[76:177]:
        path = _write_run(closed, event)
        bindings[event["sequence"]] = _sha(path)
    _write_jsonl(
        closed / "successor-schedule-journal.jsonl",
        [{"event": "planned", **event} for event in events[76:]]
        + [_completion(event, _binding(closed, event)) for event in events[76:177]],
    )

    event178 = events[177]
    binding178 = _write_run(v4, event178)
    bindings[178] = _sha(binding178)
    event179, event180 = events[178:180]
    for event in (event179, event180):
        path = _write_run(v6, event)
        bindings[event["sequence"]] = _sha(path)
    _write_jsonl(v6 / "schedule.jsonl", [event179, event180])
    _write_jsonl(
        v6 / "execution-journal.jsonl",
        [{"event": "admitted-prefix", "sequence": 178, "v4_root": str(v4), "v4_run_sha256": _sha(binding178)}]
        + [_completion(event, _binding(v6, event)) for event in (event179, event180)],
    )

    event181, event182 = events[180:182]
    path181 = _write_run(missing181, event181)
    bindings[181] = _sha(path181)
    _write_json(missing181 / "completion-binding.json", {"event": module.MISSING_181})
    _write_json(
        missing181 / "normal-receipt.json",
        {
            "event": module.MISSING_181,
            "binding_sha256": _sha(missing181 / "completion-binding.json"),
            "output": {"path": str(path181), "sha256": _sha(path181)},
        },
    )

    path182 = _write_run(v7, event182)
    bindings[182] = _sha(path182)
    _write_json(v7 / "v7-binding.json", {"roots": {"v6": str(v6)}})
    _write_jsonl(v7 / "schedule.jsonl", [event181, event182])
    _write_jsonl(v7 / "execution-journal.jsonl", [{"event": event} for event in ("admitted-prefix", "forensic-precontact", "attempt-intent")])

    for event in events[182:]:
        path = _write_run(v8, event)
        bindings[event["sequence"]] = _sha(path)
    _write_jsonl(v8 / "schedule.jsonl", events[181:])
    _write_jsonl(
        v8 / "execution-journal.jsonl",
        [
            {"event": "admitted-prefix", "sequence": 182, "settlement_sha256": "fixture-settlement"},
            {"event": "adopted-v7-output", "sequence": 182, "settlement_sha256": "fixture-settlement"},
        ]
        + [_completion(event, _binding(v8, event)) for event in events[182:]],
    )

    runtime = tmp_path / "runtime"
    runtime_analyzer = runtime / module.ANALYZER.relative_to(module.HERE.parent.parent)
    runtime_analyzer.parent.mkdir(parents=True)
    runtime_analyzer.write_bytes(module.ANALYZER.read_bytes())
    analysis_runtime = tmp_path / "analysis-runtime"
    analysis_runtime.mkdir()
    analysis_analyzer = analysis_runtime / module.ANALYZER.relative_to(module.HERE.parent.parent)
    analysis_analyzer.parent.mkdir(parents=True)
    analysis_analyzer.write_bytes(module.ANALYZER.read_bytes())
    _write_json(analysis_runtime / "reconstruction-provenance.json", {"fixture": True})
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    roots.update({"runtime": runtime, "analysis_runtime": analysis_runtime, "data": data_dir})
    for name in ("guard", "query"):
        roots[name].mkdir()
        (roots[name] / "immutable-binding.json").write_text("{}\n", encoding="utf-8", newline="\n")
    state: dict[str, list[Any]] = {"query": [], "terminal": [], "receipts": [], "normalizations": [], "v8": [], "analysis_runtime": [], "analysis_verifications": [], "phases": [], "read_order": []}
    def fake_analysis_verification(runtime_root: Path, original_root: Path) -> None:
        state["analysis_verifications"].append((runtime_root, original_root))
    def fake_analyzer(runtime_root: Path) -> Any:
        state["phases"].append("original_analyzer_import")
        state["analysis_runtime"].append(runtime_root)
        reader = _fake_analyzer(frozen, duplicate_sessions=duplicate_sessions)
        load_run = reader._load_run

        def tracked_load_run(work: Any, sample: dict[str, Any], arm: dict[str, Any], repetition: int) -> tuple[float, list[str], list[str], None, None]:
            state["read_order"].append(("original", sample["item_id"], arm["arm_id"], repetition))
            return load_run(work, sample, arm, repetition)

        reader._load_run = tracked_load_run
        return reader

    def fake_v8_reader(runtime_root: Path) -> Any:
        state["read_order"].append(("v8_reader_loaded",))
        reader = _fake_analyzer(frozen, duplicate_sessions=duplicate_sessions)
        load_run = reader._load_run

        def tracked_load_run(work: Any, sample: dict[str, Any], arm: dict[str, Any], repetition: int) -> tuple[float, list[str], list[str], None, None]:
            state["read_order"].append(("v8", sample["item_id"], arm["arm_id"], repetition))
            return load_run(work, sample, arm, repetition)

        reader._load_run = tracked_load_run
        return reader

    monkeypatch.setattr(module, "_verify_analysis_runtime", fake_analysis_verification)
    monkeypatch.setattr(module, "_load_frozen_analyzer", fake_analyzer)
    monkeypatch.setattr(module, "_load_v8_hbq_reader", fake_v8_reader)
    _admission_stubs(module, monkeypatch, roots, events, state, terminal_valid=terminal_valid, normalization_valid=normalization_valid)
    return module, roots, events, bindings, state


def _consolidate(module: ModuleType, roots: dict[str, Path], output: Path) -> dict[str, Any]:
    return module.consolidate(
        original_root=roots["original"],
        closed_successor_root=roots["closed"],
        v7_root=roots["v7"],
        missing181_root=roots["missing181"],
        v8_root=roots["v8"],
        guard_root=roots["guard"],
        query_binding_root=roots["query"],
        output_root=output,
        data_dir=roots["data"],
        analysis_runtime_root=roots["analysis_runtime"],
        runtime_root=roots["runtime"],
    )


def _retry_native_fixture(module: ModuleType, tmp_path: Path, *, sequence: int) -> tuple[dict[str, Any], dict[str, Any]]:
    original_root, v8_root, artifacts = tmp_path / "original", tmp_path / "v8", tmp_path / "artifacts"
    sample = {"item_id": "hanna-523"}
    arm = {"arm_id": "native-arm", "prompt": "arms/fixture.md", "schema": "schema.json"}
    event = {"sequence": sequence, "item_id": sample["item_id"], "arm_id": arm["arm_id"], "repetition": 1}
    source, prompt_context, base_prompt = "source\n", "prompt\n", "fixture base prompt\n"
    (original_root / "inputs" / sample["item_id"]).mkdir(parents=True)
    (original_root / "inputs" / sample["item_id"] / "source.md").write_text(source, encoding="utf-8", newline="\n")
    (original_root / "inputs" / sample["item_id"] / "prompt.md").write_text(prompt_context, encoding="utf-8", newline="\n")
    (artifacts / "arms").mkdir(parents=True)
    (artifacts / arm["prompt"]).write_text("fixture rubric\n", encoding="utf-8", newline="\n")
    schema = {"type": "object"}
    _write_json(artifacts / arm["schema"], schema)
    state: dict[str, Any] = {"feedback": {"reason": "quote fail"}}

    def structured(value: Any) -> bytes:
        return module._canonical(value)

    def write_pass(directory: Path, rendered_prompt: str, result: dict[str, Any], session: str) -> tuple[dict[str, Any], dict[str, Any]]:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "request.prompt.txt.gz").write_bytes(gzip.compress(rendered_prompt.encode("utf-8")))
        (directory / "response.schema.json").write_bytes(structured(schema))
        configuration = {
            "name": "hanna-523-native-arm-run-01",
            "provider": "codex",
            "model": "fixture-model",
            "reasoning": "fixture-reasoning",
            "prompt_sha256": hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest(),
            "schema_sha256": hashlib.sha256(structured(schema)).hexdigest(),
        }
        manifest = {"format_version": 1, "configuration": configuration, "config_sha256": hashlib.sha256(structured(configuration)).hexdigest()}
        response = {
            "format_version": 1,
            "content": json.dumps(result, sort_keys=True),
            "config_sha256": manifest["config_sha256"],
            "prompt_sha256": configuration["prompt_sha256"],
            "schema_sha256": configuration["schema_sha256"],
            "session": session,
        }
        response["content_sha256"] = hashlib.sha256(response["content"].encode("utf-8")).hexdigest()
        response["result_sha256"] = hashlib.sha256(structured(result)).hexdigest()
        _write_json(directory / "pass.json", manifest)
        _write_json(directory / "response.json", response)
        _write_json(directory / "result.json", result)
        return manifest, response

    output = tmp_path / "run"
    archive = output / "retry-attempts" / "attempt-0001"
    rejected_result, accepted_result = {"kind": "rejected"}, {"kind": "accepted"}
    _archive_manifest, rejected_response = write_pass(archive, base_prompt, rejected_result, "session-first")
    _write_json(
        output / "attempts" / "rejected-0001.json",
        {"format_version": 1, "reason": "quote fail", "response": rejected_response, "result": rejected_result},
    )
    retry_prompt = f"{base_prompt.rstrip()}\n\n<validation_feedback>{structured(state['feedback']).decode('utf-8')}</validation_feedback>\n"
    _accepted_manifest, _accepted_response = write_pass(output, retry_prompt, accepted_result, "session-second")
    first_message, second_message = output / "attempt-0001.message.json", output / "attempt-0002.message.json"
    _write_json(first_message, rejected_result)
    _write_json(second_message, accepted_result)

    disclosure_sha = "a" * 64
    _write_json(v8_root / "disclosure.json", {"profile": {"provider": "fixture"}})
    _write_json(v8_root / "retry-disclosure.json", {"provider_attempt_context": {"feedback": state["feedback"], "prompt": retry_prompt}})
    ack_path = v8_root / "retry-ack.json"
    _write_json(ack_path, {"ack": True})
    journal = [
        {"event": "attempt-intent", "sequence": sequence},
        {"event": "retry-disclosure-pause", "sequence": sequence, "retry_disclosure_sha256": disclosure_sha},
        {"event": "retry-intent", "sequence": sequence, "retry_disclosure_sha256": disclosure_sha, "retry_ack_sha256": _sha(ack_path)},
    ]

    def semantic(result: dict[str, Any], arm_id: str, received_source: str) -> None:
        assert arm_id == arm["arm_id"] and received_source == source
        if result == rejected_result:
            raise ValueError("quote fail")

    def project(result: dict[str, Any], received_source: str) -> None:
        assert received_source == source
        if result == rejected_result:
            raise ValueError("quote fail")

    analyzer = SimpleNamespace(
        HERE=artifacts,
        _json=lambda path: json.loads(Path(path).read_text(encoding="utf-8")),
        _structured_json_bytes=structured,
        _provider_response_schema=lambda value: value,
        Draft202012Validator=lambda value: SimpleNamespace(iter_errors=lambda result: []),
        _artifact_prompt=lambda _rubric, _source, _prompt: base_prompt,
        _parse_model_json=json.loads,
        _provider_ok=lambda response, provider: None,
        _validate_provider_artifacts=lambda directory, response: None,
        _session=lambda response: response["session"],
        _semantic_native=semantic,
        _native_score=lambda arm_id, result: 7.0,
        contract=lambda: {"provider": {"model": "fixture-model", "reasoning": "fixture-reasoning"}},
    )
    retry_helper = SimpleNamespace(
        _native_rejection_chain=lambda directory: {"chain": "fixture"},
        _native_retry_feedback=lambda chain: state["feedback"],
        _canonical=structured,
        _provider_identity=lambda frozen, profile: {"provider": "fixture"},
        _native_context=lambda **kwargs: {"feedback": kwargs["validation_feedback"], "prompt": kwargs["prompt"]},
        _semantic_native=lambda *args: pytest.fail("successor semantic native must not run"),
    )
    normalizer = SimpleNamespace(
        _project_result_quotes=project,
        _semantic_native=lambda *args: pytest.fail("successor semantic native must not run"),
    )
    v8 = SimpleNamespace(
        DISCLOSURE="disclosure.json",
        read_json=lambda path: json.loads(Path(path).read_text(encoding="utf-8")),
        _read_journal=lambda root: journal,
        _retry_pause_record=lambda root, pause, prior, received_event: None,
        _retry_disclosure_path=lambda root, digest: root / "retry-disclosure.json",
        _retry_ack_path=lambda root, digest: ack_path,
        _validate_retry_ack=lambda root, digest, path: None,
        _native_message_evidence=lambda directory, allow_missing: [(1, first_message), (2, second_message)],
        _physical_output_sessions=lambda directory, received_event: ["session-first", "session-second"],
        _recorded_provider_contacts=lambda root, received_event: 2,
        sha=_sha,
    )
    return {
        "analyzer": analyzer,
        "v8": v8,
        "retry_helper": retry_helper,
        "normalizer": normalizer,
        "v8_root": v8_root,
        "original_root": original_root,
        "frozen": {"provider": "fixture"},
        "event": event,
        "path": output / "pass.json",
        "sample": sample,
        "arm": arm,
        "repetition": 1,
    }, {"state": state, "archive": archive, "output": output}


@pytest.mark.parametrize("drifted", ["analyzer", "study"])
def test_load_v8_hbq_reader_rejects_drifted_bytes_before_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drifted: str) -> None:
    module = _module()
    runtime = tmp_path / "runtime"
    analyzer_path, study_path = runtime / module.V8_ANALYZER_RELATIVE, runtime / module.V8_STUDY_RELATIVE
    analyzer_path.parent.mkdir(parents=True)
    study_path.parent.mkdir(parents=True, exist_ok=True)
    (runtime / "src").mkdir()
    analyzer_bytes, study_bytes = b"expected analyzer\n", b"expected study\n"
    analyzer_path.write_bytes(b"drifted analyzer\n" if drifted == "analyzer" else analyzer_bytes)
    study_path.write_bytes(b"drifted study\n" if drifted == "study" else study_bytes)
    monkeypatch.setattr(module, "V8_ANALYZER_SHA256", hashlib.sha256(analyzer_bytes).hexdigest())
    monkeypatch.setattr(module, "V8_STUDY_SHA256", hashlib.sha256(study_bytes).hexdigest())

    with pytest.raises(ValueError, match="Frozen V8 HBQ reader bytes drifted from the admitted runtime"):
        module._load_v8_hbq_reader(runtime)


@pytest.mark.parametrize("sequence", [223, 244])
def test_load_retry_native_run_replays_two_persisted_attempts_without_successor_semantics(tmp_path: Path, sequence: int) -> None:
    module = _module()
    arguments, _fixture = _retry_native_fixture(module, tmp_path, sequence=sequence)

    score, sessions, commitments, provenance = module._load_retry_native_run(**arguments)

    assert score == 7.0
    assert sessions == ["session-first", "session-second"]
    assert len(commitments) == 4
    assert provenance == {
        "sequence": sequence,
        "item_id": "hanna-523",
        "arm_id": "native-arm",
        "repetition": 1,
        "original_semantic_rejection_reason": "quote fail",
        "successor_normalization_rejection_reason": "quote fail",
        "physical_messages": [
            {"attempt": 1, "path": str(arguments["path"].parent / "attempt-0001.message.json"), "sha256": _sha(arguments["path"].parent / "attempt-0001.message.json")},
            {"attempt": 2, "path": str(arguments["path"].parent / "attempt-0002.message.json"), "sha256": _sha(arguments["path"].parent / "attempt-0002.message.json")},
        ],
        "reported_sessions": sessions,
        "physical_messages_do_not_independently_attest_reported_sessions": True,
    }


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("feedback", "Retry-native reconstructed attempt-two context drifted from its retry disclosure"),
        ("rejection", "Retry-native successor normalization reason drifted"),
        ("archive", "Retry-native output lacks the immutable first-attempt archive"),
        ("schema", "Retry-native persisted prompt or projected schema drifted"),
    ],
)
def test_load_retry_native_run_rejects_altered_immutable_retry_evidence(tmp_path: Path, mutation: str, error: str) -> None:
    module = _module()
    arguments, paths = _retry_native_fixture(module, tmp_path, sequence=223)
    if mutation == "feedback":
        paths["state"]["feedback"] = {"reason": "tampered"}
    elif mutation == "rejection":
        rejected_path = paths["output"] / "attempts" / "rejected-0001.json"
        rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
        rejected["reason"] = "tampered"
        _write_json(rejected_path, rejected)
    elif mutation == "archive":
        paths["archive"].rename(paths["archive"].with_name("attempt-0001-moved"))
    elif mutation == "schema":
        (paths["output"] / "response.schema.json").write_bytes(b"{}")
    else:
        raise AssertionError(f"Unexpected fixture mutation: {mutation}")

    with pytest.raises(ValueError, match=error):
        module._load_retry_native_run(**arguments)


def test_reconstruct_original_analysis_runtime_materializes_exact_manifest_without_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    _bypass_repository_tree_scan(module, monkeypatch)
    original_root, historical_core_root, blobs = _reconstruction_fixture(module, tmp_path)

    output = tmp_path / "derived-analysis-runtime"
    result = module.reconstruct_original_analysis_runtime(
        output_root=output,
        original_root=original_root,
        historical_core_root=historical_core_root,
        git_blob_reader=blobs.__getitem__,
    )

    provenance = json.loads((output / "reconstruction-provenance.json").read_text(encoding="utf-8"))
    assert result["status"] == "derived_exact_manifest"
    assert result["file_count"] == 34
    assert result["support_file_count"] == len(module.SUPPORT_FILES)
    assert len(provenance["files"]) == 34
    assert provenance["not_a_single_historical_git_snapshot"] is True
    assert provenance["not_an_original_execution_root"] is True
    assert provenance["support_files_are_not_part_of_original_runtime_manifest"] is True
    retained = next(row for row in provenance["files"] if row["path"] == module.RETAINED_CORE_RELATIVE)
    assert retained["source_kind"] == "retained_historical_snapshot"
    assert all(_sha(output / row["path"]) == row["sha256"] for row in provenance["files"])
    assert {row["path"] for row in provenance["support_files"]} == set(module.SUPPORT_FILES)
    assert all(
        row["source_kind"] == "local_git_blob"
        and row["purpose"] == module.SUPPORT_FILES[row["path"]]["purpose"]
        and _sha(output / row["path"]) == row["sha256"]
        for row in provenance["support_files"]
    )


def test_reconstruct_original_analysis_runtime_rejects_one_byte_manifest_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    _bypass_repository_tree_scan(module, monkeypatch)
    original_root, historical_core_root, blobs = _reconstruction_fixture(module, tmp_path, corrupt=True)

    output = tmp_path / "rejected-analysis-runtime"
    with pytest.raises(ValueError, match="Reconstructed runtime bytes do not match the original frozen manifest"):
        module.reconstruct_original_analysis_runtime(
            output_root=output,
            original_root=original_root,
            historical_core_root=historical_core_root,
            git_blob_reader=blobs.__getitem__,
        )
    assert not output.exists()


def test_analysis_runtime_consumption_rejects_altered_support_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    _bypass_repository_tree_scan(module, monkeypatch)
    original_root, historical_core_root, blobs = _reconstruction_fixture(module, tmp_path)
    output = tmp_path / "derived-analysis-runtime"
    module.reconstruct_original_analysis_runtime(
        output_root=output,
        original_root=original_root,
        historical_core_root=historical_core_root,
        git_blob_reader=blobs.__getitem__,
    )
    module._verify_analysis_runtime(output, original_root)
    support_path = output / next(iter(sorted(module.SUPPORT_FILES)))
    support_path.write_bytes(support_path.read_bytes() + b"x")

    with pytest.raises(ValueError, match="Derived original analysis runtime support bytes drifted"):
        module._verify_analysis_runtime(output, original_root)


def test_derived_analyzer_selects_only_six_checkpoints_without_mutating_attempt_artifacts(tmp_path: Path) -> None:
    module = _module()
    analyzer_path = tmp_path / "analyze_study.py"
    original_source = module.ANALYZER.read_text(encoding="utf-8")
    analyzer_path.write_text(original_source, encoding="utf-8", newline="\n")
    responses = tmp_path / "responses"
    responses.mkdir()
    attempts: dict[Path, bytes] = {}
    for batch in range(1, 7):
        (responses / f"batch-{batch:04d}.json").write_text('{"checkpoint": true}\n', encoding="utf-8", newline="\n")
        attempt = responses / f"batch-{batch:04d}.attempt-0001.message.json"
        payload = f'{{"attempt": {batch}}}\n'.encode()
        attempt.write_bytes(payload)
        attempts[attempt] = payload

    derived_source = module._derived_analyzer_source(analyzer_path)

    assert derived_source == original_source.replace(
        module.LEGACY_ACCEPTED_CHECKPOINT_GLOB, module.EXACT_ACCEPTED_CHECKPOINT_GLOB
    ).replace(
        module.LEGACY_HBQ_MANIFEST_BINDING, module.DERIVED_HBQ_MANIFEST_BINDING
    ).replace(module.LEGACY_PROMPT_BINDING_BLOCK, module.DERIVED_PROMPT_BINDING_BLOCK)
    assert len(list(responses.glob("batch-*.json"))) == 12
    assert [path.name for path in sorted(responses.glob("batch-[0-9][0-9][0-9][0-9].json"))] == [
        f"batch-{batch:04d}.json" for batch in range(1, 7)
    ]
    assert {path: path.read_bytes() for path in attempts} == attempts
    assert all(path.exists() for path in attempts)


def test_derived_manifest_binding_accepts_only_versions_3_and_4_with_full_configuration_hash() -> None:
    module = _module()
    configuration = {
        "provider": "codex",
        "model": "fixture-model",
        "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": {"mode": "strict"},
        "validation_feedback_policy": {"enabled": True},
        "unrelated_frozen_setting": "must-remain-bound",
    }
    digest = hashlib.sha256(module._canonical(configuration)).hexdigest()

    def accepted(manifest: dict[str, Any], candidate: dict[str, Any]) -> bool:
        return manifest.get("format_version") in {3, 4} and manifest.get("config_sha256") == hashlib.sha256(module._canonical(candidate)).hexdigest()

    assert module.DERIVED_HBQ_MANIFEST_BINDING == (
        '        if manifest.get("format_version") not in {3, 4} or manifest.get("config_sha256") '
        '!= hashlib.sha256(_json_bytes(config)).hexdigest():\n'
        '            raise ValueError("HBQ manifest configuration binding is invalid")\n'
    )
    assert all(accepted({"format_version": version, "config_sha256": digest}, configuration) for version in (3, 4))
    assert not accepted({"config_sha256": digest}, configuration)
    assert not accepted({"format_version": 5, "config_sha256": digest}, configuration)
    assert not accepted({"format_version": 3, "config_sha256": "0" * 64}, configuration)

    for key, replacement in (
        ("retry_semantics", "other"),
        ("evidence_normalization_policy", {"mode": "other"}),
        ("validation_feedback_policy", {"enabled": False}),
        ("unrelated_frozen_setting", "drifted"),
    ):
        mutated = {**configuration, key: replacement}
        assert hashlib.sha256(module._canonical(mutated)).hexdigest() != digest
        assert not accepted({"format_version": 4, "config_sha256": digest}, mutated)


def test_derived_prompt_binding_allows_only_pinned_pairs_and_exact_schema() -> None:
    module = _module()
    expected_prompts = [
        {"name": "JUDGE_PREFIX.md", "bytes": 1200, "sha256": "crlf-prefix"},
        {"name": "BINARY_EVALUATION_PROMPT.md", "bytes": 1500, "sha256": "crlf-binary"},
    ]
    expected_schema = {"name": "hbq_judge_response.schema.json", "bytes": 10, "sha256": "schema"}
    sample = {"item_id": "hanna-523"}
    arm = {"arm_id": "hbq_short_story_batch32"}
    variants: list[dict[str, Any]] = []
    compact = lambda value: value
    frozen_input_compact = lambda value: value

    assert module.RETAINED_LF_PROMPT_BINDINGS == [
        {"name": "JUDGE_PREFIX.md", "bytes": 1184, "sha256": "ba48be75c55502d762f1029745b6a4b3b4d12674317f20906443467a00f8f3a5"},
        {"name": "BINARY_EVALUATION_PROMPT.md", "bytes": 1460, "sha256": "3dd432228d2ad747e9a3958320e1b7eccf725bbc985aec1cd74eeb865254bd1c"},
    ]
    assert module._derived_prompt_binding_is_accepted(
        {"prompts": expected_prompts, "response_schema": expected_schema},
        expected_prompts,
        expected_schema,
        compact,
        frozen_input_compact,
        sample,
        arm,
        1,
        variants,
    )
    assert variants == []

    retained = [dict(item) for item in module.RETAINED_LF_PROMPT_BINDINGS]
    assert module._derived_prompt_binding_is_accepted(
        {"prompts": retained, "response_schema": expected_schema},
        expected_prompts,
        expected_schema,
        compact,
        frozen_input_compact,
        sample,
        arm,
        1,
        variants,
    )
    assert variants == [{"item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "repetition": 1}]
    assert module._derived_prompt_binding_is_accepted(
        {"prompts": retained, "response_schema": expected_schema},
        expected_prompts,
        expected_schema,
        compact,
        frozen_input_compact,
        sample,
        arm,
        1,
        variants,
    )
    assert len(variants) == 1

    one_byte_drift = [dict(item) for item in retained]
    one_byte_drift[0]["bytes"] += 1
    assert not module._derived_prompt_binding_is_accepted(
        {"prompts": one_byte_drift, "response_schema": expected_schema},
        expected_prompts,
        expected_schema,
        compact,
        frozen_input_compact,
        sample,
        arm,
        2,
        variants,
    )
    assert not module._derived_prompt_binding_is_accepted(
        {"prompts": retained, "response_schema": {**expected_schema, "sha256": "schema-drift"}},
        expected_prompts,
        expected_schema,
        compact,
        frozen_input_compact,
        sample,
        arm,
        2,
        variants,
    )
    assert len(variants) == 1


def test_consolidate_rejects_analysis_runtime_gate_before_loading_analyzer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, roots, _, _, state = _fixture(tmp_path, monkeypatch)

    def reject_analysis_runtime(runtime_root: Path, original_root: Path) -> None:
        state["analysis_verifications"].append((runtime_root, original_root))
        raise ValueError("Derived original analysis runtime support bytes drifted: fixture")

    monkeypatch.setattr(module, "_verify_analysis_runtime", reject_analysis_runtime)
    with pytest.raises(ValueError, match="Derived original analysis runtime support bytes drifted"):
        _consolidate(module, roots, tmp_path / "rejected-analysis-runtime")
    assert state["analysis_verifications"] == [(roots["analysis_runtime"], roots["original"])]
    assert state["analysis_runtime"] == []


def test_consolidate_replays_cross_root_330_geometry_without_copying_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, roots, events, bindings, state = _fixture(tmp_path, monkeypatch)
    source_tree_hashes = {name: module._tree_hash(path) for name, path in roots.items() if name not in {"runtime", "data"}}

    result = _consolidate(module, roots, tmp_path / "derived")

    output = tmp_path / "derived"
    provenance = json.loads((output / "consolidation-provenance.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert result["status"] == "complete_330"
    assert result["geometry"] == {"expected_cells": 330, "observed_cells": 330, "unique_cell_identities": 330}
    assert result["source_kind_counts"] == {
        "original_1_76": 76,
        "closed_successor_77_177": 101,
        "adopted_v4_178": 1,
        "admitted_v6_179_180": 2,
        "missing181_detached_completion": 1,
        "adopted_v7_182": 1,
        "v8_accepted_183_330": 148,
    }
    assert [path.name for path in sorted(output.iterdir())] == ["consolidation-provenance.json", "manifest.json", "summary.json"]
    assert provenance["missing181_not_v8_acceptance"] is True
    assert provenance["terminal_admission"]["accepted_sequence_count"] == 149
    assert provenance["terminal_admission"]["adopted_sequence"] == 182
    assert provenance["analysis_runtime"]["root"] == str(roots["analysis_runtime"])
    assert provenance["original_analyzer"]["derived_analysis_compatibility"]["retained_lf_variant_cells"] == []
    hbq_quality = summary["arms"]["hbq_short_story_batch32"]["quality_sensitivity"]
    assert hbq_quality["status"] == "version_cohorted_not_pooled"
    assert {version: details["sample_count"] for version, details in hbq_quality["cohorts"].items()} == {
        "original_rubric_v1_0_0": 6,
        "v8_rubric_v1_2_1": 5,
    }
    assert [cell["sequence"] for cell in provenance["cells"]] == list(range(1, 331))
    assert {cell["sequence"]: cell["run_binding_sha256"] for cell in provenance["cells"]} == bindings
    assert {name: module._tree_hash(path) for name, path in roots.items() if name not in {"runtime", "data"}} == source_tree_hashes
    assert len(events) == 330
    assert state["query"] == [(roots["runtime"], roots["query"])]
    assert state["terminal"] == ["verify_prepared", "guard_clear", "accepted", "contacts", "preflight", "guard_binding", "canonical_runtime", "static_identity", "guard_journal", "claims", "contacts_recomputed"]
    assert state["receipts"] == [(roots["missing181"], roots["runtime"])]
    assert state["analysis_verifications"] == [(roots["analysis_runtime"], roots["original"])]
    assert state["analysis_runtime"] == [roots["analysis_runtime"]]
    native_events = [event for event in events if event["arm_id"] != "hbq_short_story_batch32"]
    assert len(state["normalizations"]) == len(native_events) == 275
    assert state["phases"] == ["native_normalization"] * len(native_events) + ["original_analyzer_import"]

    def source_root(event: dict[str, Any]) -> Path:
        sequence = event["sequence"]
        if sequence <= 76:
            return roots["original"]
        if sequence <= 177:
            return roots["closed"]
        if sequence == 178:
            return roots["v4"]
        if sequence <= 180:
            return roots["v6"]
        if sequence == 181:
            return roots["missing181"]
        if sequence == 182:
            return roots["v7"]
        return roots["v8"]

    assert {path / "pass.json" for path in state["normalizations"]} == {
        _binding(source_root(event), event) for event in native_events
    }
    v8_hbq_events = [
        event
        for event in events
        if event["arm_id"] == "hbq_short_story_batch32" and (event["sequence"] == 181 or event["sequence"] >= 183)
    ]
    assert len(v8_hbq_events) == 25
    assert {event["item_id"] for event in v8_hbq_events} == module.V8_HBQ_ITEM_IDS
    expected_original = [
        ("original", event["item_id"], event["arm_id"], event["repetition"])
        for event in events
        if event not in v8_hbq_events
    ]
    expected_v8 = [("v8", event["item_id"], event["arm_id"], event["repetition"]) for event in v8_hbq_events]
    assert state["read_order"] == [*expected_original, ("v8_reader_loaded",), *expected_v8]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("incomplete", "V8 journal is not a terminal 183-330 completion"),
        ("duplicate_adoption", "V8 does not retain the adopted V7 sequence 182 provenance"),
        ("relabel", "Original completion record relabels its frozen event"),
    ],
)
def test_consolidate_rejects_incomplete_duplicate_adoption_and_relabels_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, error: str
) -> None:
    module, roots, events, _, _ = _fixture(tmp_path, monkeypatch)
    if mutation == "incomplete":
        rows = module._jsonl(roots["v8"] / "execution-journal.jsonl")[:-1]
        _write_jsonl(roots["v8"] / "execution-journal.jsonl", rows)
    elif mutation == "duplicate_adoption":
        rows = module._jsonl(roots["v8"] / "execution-journal.jsonl")
        rows[1]["sequence"] = 181
        _write_jsonl(roots["v8"] / "execution-journal.jsonl", rows)
    else:
        rows = module._jsonl(roots["original"] / "schedule-journal.jsonl")
        rows[330]["item_id"] = "relabelled-item"
        _write_jsonl(roots["original"] / "schedule-journal.jsonl", rows)

    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match=error):
        _consolidate(module, roots, output)
    assert not output.exists()
    assert events[180] == module.MISSING_181


def test_consolidate_rejects_existing_output_and_cross_root_session_collision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, roots, _, _, _ = _fixture(tmp_path, monkeypatch)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="Refusing to merge"):
        _consolidate(module, roots, existing)

    collision_module, collision_roots, _, _, _ = _fixture(tmp_path / "collision", monkeypatch, duplicate_sessions=True)
    output = tmp_path / "collision-derived"
    with pytest.raises(ValueError, match="fresh-session requirement"):
        _consolidate(collision_module, collision_roots, output)
    assert not output.exists()


def test_consolidate_requires_pinned_terminal_admission_before_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, roots, _, _, state = _fixture(tmp_path, monkeypatch, terminal_valid=False)

    output = tmp_path / "terminal-rejected"
    with pytest.raises(ValueError, match="Query-safe guard unexpectedly found a nonterminal V8 event"):
        _consolidate(module, roots, output)
    assert state["terminal"] == ["verify_prepared", "guard_clear", "accepted", "contacts", "preflight"]
    assert state["normalizations"] == []
    assert not output.exists()


def test_consolidate_requires_raw_normalization_for_each_native_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, roots, _, _, state = _fixture(tmp_path, monkeypatch, normalization_valid=False)

    output = tmp_path / "normalization-rejected"
    with pytest.raises(ValueError, match="fixture normalization rejected raw run"):
        _consolidate(module, roots, output)
    assert len(state["normalizations"]) == 1
    assert not output.exists()
