from __future__ import annotations

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
        {"arm_id": "hbq_short_story_batch32", "kind": "native", "native_scale": [0, 10]},
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
        for item_id in ("item-01", "item-02", "item-03", "item-04", "item-05", "item-06", "hanna-523", "item-08", "item-09", "item-10", "item-11")
    ]
    schedule = [
        {"item_id": sample["item_id"], "arm_id": arm["arm_id"], "repetition": repetition}
        for sample in samples
        for arm in arms
        for repetition in range(1, 6)
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
    return root / "runs" / event["item_id"] / event["arm_id"] / f"run-{event['repetition']:02d}" / "pass.json"


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
        binding = work / "runs" / sample["item_id"] / arm["arm_id"] / f"run-{repetition:02d}" / "pass.json"
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
    state: dict[str, list[Any]] = {"query": [], "terminal": [], "receipts": [], "normalizations": [], "v8": [], "analysis_runtime": []}
    def fake_analyzer(runtime_root: Path) -> Any:
        state["analysis_runtime"].append(runtime_root)
        return _fake_analyzer(frozen, duplicate_sessions=duplicate_sessions)
    monkeypatch.setattr(module, "_load_frozen_analyzer", fake_analyzer)
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
    assert len(provenance["files"]) == 34
    assert provenance["not_a_single_historical_git_snapshot"] is True
    assert provenance["not_an_original_execution_root"] is True
    retained = next(row for row in provenance["files"] if row["path"] == module.RETAINED_CORE_RELATIVE)
    assert retained["source_kind"] == "retained_historical_snapshot"
    assert all(_sha(output / row["path"]) == row["sha256"] for row in provenance["files"])


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


def test_consolidate_replays_cross_root_330_geometry_without_copying_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, roots, events, bindings, state = _fixture(tmp_path, monkeypatch)
    source_tree_hashes = {name: module._tree_hash(path) for name, path in roots.items() if name not in {"runtime", "data"}}

    result = _consolidate(module, roots, tmp_path / "derived")

    output = tmp_path / "derived"
    provenance = json.loads((output / "consolidation-provenance.json").read_text(encoding="utf-8"))
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
    assert [cell["sequence"] for cell in provenance["cells"]] == list(range(1, 331))
    assert {cell["sequence"]: cell["run_binding_sha256"] for cell in provenance["cells"]} == bindings
    assert {name: module._tree_hash(path) for name, path in roots.items() if name not in {"runtime", "data"}} == source_tree_hashes
    assert len(events) == 330
    assert state["query"] == [(roots["runtime"], roots["query"])]
    assert state["terminal"] == ["verify_prepared", "guard_clear", "accepted", "contacts", "preflight", "guard_binding", "canonical_runtime", "static_identity", "guard_journal", "claims", "contacts_recomputed"]
    assert state["receipts"] == [(roots["missing181"], roots["runtime"])]
    assert state["analysis_runtime"] == [roots["analysis_runtime"]]
    assert len(state["normalizations"]) == 330
    assert {path / "pass.json" for path in state["normalizations"]} == {
        _binding(roots["original"], event) for event in events[:76]
    } | {
        _binding(roots["closed"], event) for event in events[76:177]
    } | {
        _binding(roots["v4"], events[177]),
        _binding(roots["v6"], events[178]),
        _binding(roots["v6"], events[179]),
        _binding(roots["missing181"], events[180]),
        _binding(roots["v7"], events[181]),
    } | {
        _binding(roots["v8"], event) for event in events[182:]
    }


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
