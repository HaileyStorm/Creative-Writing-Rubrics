from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import hashlib
import gzip
import importlib
import io
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-multisample-repeatability-v1"
REPOSITORY = book_root().resolve()

# Git's canonical-LF archive is the retained successor representation for two
# Windows-byte-bound import files.  The frozen study mapping remains untouched.
IMPORT_RUNTIME_SUCCESSOR_SEALS = {
    "70b4cd16bd536f2f6ddb8e066f801090a037a39605652b14d6c7f6ff312446cb": {
        "raw_bytes": 45951,
        "canonical_lf_bytes": 45093,
        "canonical_lf_sha256": "0518be16a4528b893de6af61300ecea58dc56d6b7944b5ae5fd3a3214a3794ef",
    },
    "dedadb6d9f8e3cf700c16012b29e1a590a2b1175c8ead0cf17c44aa6417b8266": {
        "raw_bytes": 1419,
        "canonical_lf_bytes": 1367,
        "canonical_lf_sha256": "69bc5a8260ec5d5f95b80868469610d4dc1b8bcb3d58ce5f7e4c40f77b6e3fb7",
    },
}


def _install_import_runtime_successor_seals(study: ModuleType) -> None:
    def pinned_paths() -> list[Path]:
        paths = [study.ROOT / relative for relative in study.STUDY_IMPORT_RUNTIME_SHA256]
        for path, expected in zip(paths, study.STUDY_IMPORT_RUNTIME_SHA256.values()):
            if not path.is_file():
                raise ValueError("Pinned study-import runtime closure drifted")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() == expected:
                continue
            seal = IMPORT_RUNTIME_SUCCESSOR_SEALS.get(expected)
            canonical_lf = payload.replace(b"\r\n", b"\n")
            if not isinstance(seal, dict) or seal.get("canonical_lf_bytes") != len(canonical_lf) or seal.get("canonical_lf_sha256") != hashlib.sha256(canonical_lf).hexdigest():
                raise ValueError("Pinned study-import runtime closure drifted")
        return paths

    study._pinned_study_import_runtime_paths = pinned_paths


class HistoricalMultiSampleRuntime:
    """Materialize the frozen study control with its separately pinned HBQ runtime."""

    CONTROL_COMMIT = "df084e488168e3cd3103cccd7e747b63676b4b7e"
    RUNTIME_COMMIT = "a09be09869e2a0843f3c448fd0f25c10f963ff85"
    PACKAGE_NAME = "multisample_v1_historical_hbqrs"

    def __init__(self) -> None:
        self._runtime: SimpleNamespace | None = None
        self._modules: dict[str, ModuleType] = {}

    @staticmethod
    def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(["git", "-C", str(REPOSITORY), *args], capture_output=True, check=False)

    @classmethod
    def _safe_extract(cls, archive: bytes, destination: Path) -> None:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as contents:
            root = destination.resolve()
            for member in contents.getmembers():
                target = (destination / member.name).resolve()
                if member.issym() or member.islnk() or not target.is_relative_to(root) or not (member.isdir() or member.isfile()):
                    raise ValueError("Historical multisample archive is unsafe")
            contents.extractall(destination, filter="data")

    def _archive(self, destination: Path, commit: str, *paths: str) -> None:
        result = self._git("archive", "--format=tar", commit, *paths)
        if result.returncode:
            raise ValueError("Pinned multisample control/runtime commit is unavailable")
        self._safe_extract(result.stdout, destination)

    def _restore_raw_runtime_bytes(self, destination: Path) -> None:
        listed = self._git("ls-tree", "-r", "--name-only", self.RUNTIME_COMMIT, "--", "src/hbqrs")
        if listed.returncode:
            raise ValueError("Pinned multisample runtime listing is unavailable")
        for value in listed.stdout.decode("utf-8").splitlines():
            relative = Path(value)
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Pinned multisample runtime path is unsafe")
            payload = self._git("show", f"{self.RUNTIME_COMMIT}:{relative.as_posix()}")
            if payload.returncode:
                raise ValueError("Pinned multisample runtime asset is unavailable")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload.stdout)

    def runtime(self) -> SimpleNamespace:
        if self._runtime is not None:
            return self._runtime
        for commit in (self.CONTROL_COMMIT, self.RUNTIME_COMMIT):
            if self._git("cat-file", "-e", f"{commit}^{{commit}}").returncode:
                raise ValueError("Pinned multisample control/runtime commit is unavailable")
        lease = tempfile.TemporaryDirectory(prefix="cwr-multisample-v1-historical-runtime-")
        snapshot = Path(lease.name) / "repository"
        try:
            self._archive(
                snapshot,
                self.CONTROL_COMMIT,
                "evaluation-results/hbq-multisample-repeatability-v1",
                "evaluation-results/hbq-human-alignment-v3",
                "evaluation-results/hbq-human-alignment-v2",
                "evaluation-results/the-part-that-arrives-first-repeatability",
                "registry",
                "bundles",
                "prompts",
                "schema",
            )
            self._archive(snapshot, self.RUNTIME_COMMIT, "src/hbqrs")
            self._restore_raw_runtime_bytes(snapshot)
            package_root = snapshot / "src" / "hbqrs"
            spec = importlib.util.spec_from_file_location(
                self.PACKAGE_NAME,
                package_root / "__init__.py",
                submodule_search_locations=[str(package_root)],
            )
            assert spec and spec.loader
            package = importlib.util.module_from_spec(spec)
            sys.modules[self.PACKAGE_NAME] = package
            spec.loader.exec_module(package)
            paths = importlib.import_module(f"{self.PACKAGE_NAME}.paths")
            paths.book_root = lambda: snapshot
            self._runtime = SimpleNamespace(
                lease=lease,
                root=snapshot,
                package=package,
                core=importlib.import_module(f"{self.PACKAGE_NAME}.core"),
                paths=paths,
                runner=importlib.import_module(f"{self.PACKAGE_NAME}.runner"),
                structured=importlib.import_module(f"{self.PACKAGE_NAME}.longform_runner"),
            )
            return self._runtime
        except Exception:
            lease.cleanup()
            raise

    @contextmanager
    def aliases(self):
        historical = self.runtime()
        aliases = {
            "hbqrs": historical.package,
            "hbqrs.core": historical.core,
            "hbqrs.paths": historical.paths,
            "hbqrs.runner": historical.runner,
            "hbqrs.longform_runner": historical.structured,
        }
        if "study" in self._modules:
            aliases["study"] = self._modules["study"]
        prior = {name: sys.modules.get(name) for name in aliases}
        sys.modules.update(aliases)
        try:
            yield
        finally:
            for name, value in prior.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value

    def module(self, name: str) -> ModuleType:
        if name in self._modules:
            return self._modules[name]
        root = self.runtime().root / ROOT.relative_to(REPOSITORY)
        spec = importlib.util.spec_from_file_location(f"multisample_v1_historical_{name}", root / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        if name == "study":
            self._modules[name] = module
        try:
            with self.aliases():
                spec.loader.exec_module(module)
                if name == "study":
                    _install_import_runtime_successor_seals(module)
        except Exception:
            self._modules.pop(name, None)
            raise
        self._modules[name] = module
        return module

    def hanna(self) -> ModuleType:
        study = self.module("study")
        with self.aliases():
            return study.hanna()


_HISTORICAL = HistoricalMultiSampleRuntime()


def _historical_runtime() -> SimpleNamespace:
    return _HISTORICAL.runtime()


def _module(name: str):
    if name != "study" and "study" not in sys.modules:
        _module("study")
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _complete_hbq_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, retry_first: bool = False):
    historical = _historical_runtime()
    study = _HISTORICAL.module("study")
    analysis = _HISTORICAL.module("analyze_study")
    hanna = _HISTORICAL.hanna()
    source_text, prompt_text = "A short test scene.", "Write a tense short scene."
    item = hanna.HannaItem("fixture-story", "1", "fixture-model", prompt_text, source_text, {key: (3, 3, 3) for key in hanna.RATING_DIMENSIONS})
    task = hanna.make_task_contract(item)
    folder = tmp_path / "work" / "inputs" / item.item_id
    folder.mkdir(parents=True)
    (folder / "source.md").write_text(source_text, encoding="utf-8")
    (folder / "prompt.md").write_text(prompt_text, encoding="utf-8")
    study.write_json(folder / "task-contract.json", task)
    study.write_json(folder / "human-ratings.json", {"human_overall": item.human_overall, "human_means": item.human_means, "ratings": {key: list(value) for key, value in item.ratings.items()}})
    arm = next(value for value in analysis.contract()["arms"] if value["kind"] == "hbq")
    question_ids = study.question_sequence(task)
    calls = 0

    def fake_codex(**kwargs):
        nonlocal calls
        calls += 1
        batch = calls - 2 if retry_first and calls > 1 else calls - 1
        ids = ["unexpected.question"] if retry_first and calls == 1 else question_ids[batch * arm["batch_size"]:(batch + 1) * arm["batch_size"]]
        content = json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}], "note": "Grounded fixture verdict."} for question_id in ids]})
        return content, {"reported": {"provider": "openai", "model": analysis.contract()["provider"]["model"], "reasoning_effort": analysis.contract()["provider"]["reasoning"], "session_id": f"fixture-session-{calls}"}}

    monkeypatch.setattr(historical.runner, "_call_codex", fake_codex)
    output = tmp_path / "work" / "runs" / item.item_id / arm["arm_id"] / "run-01"
    historical.runner.run_judge(artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"], task_contract_path=folder / "task-contract.json", artifact_id=item.item_id, bundle_id=arm["bundle_id"], provider="codex", model=analysis.contract()["provider"]["model"], reasoning=analysis.contract()["provider"]["reasoning"], output_dir=output, registry=study.registry_path(), bundles=study.bundles_path(), batch_size=arm["batch_size"], batch_attempts=arm["batch_attempts"], allow_remote=True, strict_ai=True)
    sample = {"item_id": item.item_id, "question_count": len(question_ids), "question_id_sequence_sha256": hashlib.sha256(study.canonical(question_ids)).hexdigest(), "inputs": {name: study.fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json", "human-ratings.json")}}
    return analysis, sample, arm, tmp_path / "work", output, calls


def test_contract_freezes_six_arms_and_exact_hanna_repeatability_shape() -> None:
    study = _module("study")
    value = study.contract()
    assert value["repetitions"] == 5
    assert value["arms"][0]["question_count"] == 179  # HANNA's frozen prompt-response goal is additive.
    assert [arm["arm_id"] for arm in value["arms"]] == [
        "hbq_short_story_batch32", "naplan_narrative_2022", "cambridge_igcse_0500_p2_mj_2024",
        "oregon_narrative_2017", "compact_analytic", "holistic_anchored",
    ]
    assert value["quality_sensitivity"]["primary"].startswith("continuous tie-aware Spearman")
    assert value["primary_metrics"]["bootstrap"] == {"seed": 560820, "draws": 10000, "unit": "prompt cluster", "comparison": "paired arm deltas on the same frozen sample and repetition"}


def test_runtime_provenance_pins_the_exhaustive_lazy_study_import_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "study", raising=False)
    historical = _historical_runtime()
    study = _HISTORICAL.module("study")
    assert "study" not in sys.modules
    expected = {"src/hbqrs/__init__.py", "src/hbqrs/core.py", "src/hbqrs/paths.py"}
    assert set(study.STUDY_IMPORT_RUNTIME_SHA256) == expected
    assert {path.relative_to(study.ROOT).as_posix() for path in study._pinned_study_import_runtime_paths()} == expected
    audit = """import importlib.util, json, sys
from pathlib import Path
target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target.parent))
spec = importlib.util.spec_from_file_location('multisample_import_audit', target)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
root = Path(sys.argv[2]).resolve()
print(json.dumps({name: Path(value.__file__).resolve().relative_to(root).as_posix() for name, value in sorted(sys.modules.items()) if name == 'hbqrs' or name.startswith('hbqrs.') and getattr(value, '__file__', None)}, sort_keys=True))
"""
    environment = {**os.environ, "PYTHONPATH": str(historical.root / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
    completed = subprocess.run([sys.executable, "-c", audit, str(study.HERE / "study.py"), str(study.ROOT)], cwd=study.ROOT, env=environment, check=True, capture_output=True, text=True)
    assert json.loads(completed.stdout) == {"hbqrs": "src/hbqrs/__init__.py", "hbqrs.core": "src/hbqrs/core.py", "hbqrs.paths": "src/hbqrs/paths.py"}
    monkeypatch.setitem(study.STUDY_IMPORT_RUNTIME_SHA256, "src/hbqrs/core.py", "0" * 64)
    with pytest.raises(ValueError, match="study-import runtime closure drifted"):
        study._pinned_study_import_runtime_paths()


def test_schedule_is_complete_balanced_and_deterministic() -> None:
    study = _module("study")
    arms = [arm["arm_id"] for arm in study.contract()["arms"]]
    first = study.frozen_schedule([f"hanna-{index}" for index in range(11)], arms, 5)
    second = study.frozen_schedule([f"hanna-{index}" for index in reversed(range(11))], arms, 5)
    assert first == second
    assert len(first) == 11 * 5 * 6
    assert {(row["item_id"], row["repetition"], row["arm_id"]) for row in first} == {(f"hanna-{sample}", repetition, arm) for sample in range(11) for repetition in range(1, 6) for arm in arms}
    for arm in arms:
        positions = [row["position"] for row in first if row["arm_id"] == arm]
        counts = [positions.count(position) for position in range(1, 7)]
        assert max(counts) - min(counts) <= 1


def test_tie_aware_rank_metrics_and_constant_kendall_are_explicit() -> None:
    analysis = _module("analyze_study")
    assert analysis.spearman([1, 1, 2, 3], [4, 4, 1, 0]) == pytest.approx(-1.0)
    assert analysis.kendall_w([[1, 1, 1], [2, 2, 2]]) is None
    assert analysis.kendall_w([[1, 2, 3], [1, 2, 3], [1, 2, 3]]) == pytest.approx(1.0)


def test_numeric_metrics_are_scale_normalized_without_cross_scale_totals() -> None:
    analysis = _module("analyze_study")
    compact = analysis._numeric_metrics([1, 2, 3, 4, 5], (1, 5))
    hbq = analysis._numeric_metrics([0, 25, 50, 75, 100], (0, 100))
    assert compact["normalized_range"] == hbq["normalized_range"] == 1.0
    assert compact["normalized_mapd"] == pytest.approx(hbq["normalized_mapd"])
    assert compact["native_range"] == 4
    assert hbq["native_range"] == 100


def test_paired_bootstrap_is_seeded_and_preserves_direction() -> None:
    analysis = _module("analyze_study")
    rows = {
        "a": [{"item_id": f"i{i}", "prompt_sha256": "shared" if i < 2 else f"p{i}", "normalized_sample_sd": 0.1, "normalized_mapd": 0.1, "normalized_range": 0.1, "pairwise_exact_agreement": 1.0} for i in range(11)],
        "b": [{"item_id": f"i{i}", "prompt_sha256": "shared" if i < 2 else f"p{i}", "normalized_sample_sd": 0.2, "normalized_mapd": 0.2, "normalized_range": 0.2, "pairwise_exact_agreement": 0.5} for i in range(11)],
    }
    first = analysis._bootstrap(rows, seed=560820, draws=100)
    assert first == analysis._bootstrap(rows, seed=560820, draws=100)
    values = {row["metric"]: row["estimate"] for row in first["a__minus__b"]}
    assert values["normalized_sample_sd"] == pytest.approx(-0.1)
    assert values["pairwise_exact_agreement"] == pytest.approx(0.5)
    assert {row["prompt_cluster_count"] for row in first["a__minus__b"]} == {10}
    assert {row["estimand"] for row in first["a__minus__b"]} == {"equal_sample_mean_paired_delta"}


def test_cluster_bootstrap_resamples_whole_clusters_without_reweighting_the_equal_sample_estimand() -> None:
    analysis = _module("analyze_study")
    rows = {
        "a": [
            {"item_id": "a", "prompt_sha256": "shared", "normalized_sample_sd": 0.0, "normalized_mapd": 0.0, "normalized_range": 0.0, "pairwise_exact_agreement": 0.0},
            {"item_id": "b", "prompt_sha256": "shared", "normalized_sample_sd": 0.0, "normalized_mapd": 0.0, "normalized_range": 0.0, "pairwise_exact_agreement": 0.0},
            {"item_id": "c", "prompt_sha256": "other", "normalized_sample_sd": 1.0, "normalized_mapd": 1.0, "normalized_range": 1.0, "pairwise_exact_agreement": 1.0},
        ],
        "b": [
            {"item_id": "a", "prompt_sha256": "shared", "normalized_sample_sd": 1.0, "normalized_mapd": 1.0, "normalized_range": 1.0, "pairwise_exact_agreement": 1.0},
            {"item_id": "b", "prompt_sha256": "shared", "normalized_sample_sd": 1.0, "normalized_mapd": 1.0, "normalized_range": 1.0, "pairwise_exact_agreement": 1.0},
            {"item_id": "c", "prompt_sha256": "other", "normalized_sample_sd": 0.0, "normalized_mapd": 0.0, "normalized_range": 0.0, "pairwise_exact_agreement": 0.0},
        ],
    }
    first = analysis._bootstrap(rows, seed=560820, draws=100)
    for row in first["a__minus__b"]:
        assert row["estimate"] == pytest.approx(-1 / 3)


def test_quality_summary_keeps_thin_bands_descriptive_and_rank_outputs_defined() -> None:
    analysis = _module("analyze_study")
    rows = [
        {"human_overall": float(index), "frozen_quality_band": 1 if index < 3 else 4, "values": [float(index)] * 5, "normalized_values": [index / 10] * 5, "mean_normalized_score": index / 10}
        for index in range(1, 7)
    ]
    value = analysis._quality(rows, 5)
    assert value["continuous_tie_aware_spearman_of_repeat_mean_vs_human"] == pytest.approx(1.0)
    assert value["per_repeat_spearman_vs_human"] == pytest.approx([1.0] * 5)
    assert value["high_minus_low_normalized_gap"] == pytest.approx(0.3)
    assert value["bands"]["1"]["sample_count"] == 2
    assert value["bands"]["2"]["sample_count"] == 0
    assert value["kendall_w_across_repetitions"] == pytest.approx(1.0)


def test_coarse_arms_require_grounded_quotes() -> None:
    runner = _module("run_study")
    source = "The exact line appears here."
    good = {"score": 4, "evidence": [{"quote": "exact line", "explanation": "grounded"}]}
    runner._semantic_native(good, "holistic_anchored", source)
    with pytest.raises(ValueError, match="exact substring"):
        runner._semantic_native({"score": 4, "evidence": [{"quote": "invented", "explanation": "wrong"}]}, "holistic_anchored", source)


def test_native_remote_gate_and_outbound_disclosure_are_exact(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _module("run_study")
    arm = next(value for value in runner.contract()["arms"] if value["arm_id"] == "holistic_anchored")
    folder = tmp_path / "inputs" / "story"
    folder.mkdir(parents=True)
    source, prompt = "A story.", "An originating prompt."
    (folder / "source.md").write_text(source, encoding="utf-8")
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")
    event = {"sequence": 1, "item_id": "story", "arm_id": arm["arm_id"], "repetition": 1}
    disclosure = runner._outbound_disclosure(tmp_path, event, arm)
    assert disclosure["files"] == [
        {"role": "story", "path": "inputs/story/source.md", "bytes": len(source.encode()), "sha256": hashlib.sha256(source.encode()).hexdigest()},
        {"role": "originating_prompt", "path": "inputs/story/prompt.md", "bytes": len(prompt.encode()), "sha256": hashlib.sha256(prompt.encode()).hexdigest()},
        {"role": "scoring_instructions", "path": (runner.HERE / arm["prompt"]).relative_to(runner.HERE).as_posix(), "bytes": (runner.HERE / arm["prompt"]).stat().st_size, "sha256": hashlib.sha256((runner.HERE / arm["prompt"]).read_bytes()).hexdigest()},
    ]
    assert disclosure["rendered_prompt"]["sha256"] == hashlib.sha256(runner._artifact_prompt((runner.HERE / arm["prompt"]).read_text(encoding="utf-8"), source, prompt).encode("utf-8")).hexdigest()
    provider_schema = runner._structured_json_bytes(runner._provider_response_schema(runner._json(runner.HERE / arm["schema"])))
    assert disclosure["provider_response_schema"] == {"path": "runs/story/holistic_anchored/run-01/response.schema.json", "bytes": len(provider_schema), "sha256": hashlib.sha256(provider_schema).hexdigest()}
    frozen = {"contract": {"arms": [arm], "provider": runner.contract()["provider"]}}
    with pytest.raises(ValueError, match="--allow-remote"):
        runner._run(event, frozen, tmp_path, 1.0, allow_remote=False)
    assert capsys.readouterr().out == ""


def test_hbq_path_receives_the_existing_runner_remote_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")
    arm = next(value for value in runner.contract()["arms"] if value["kind"] == "hbq")
    folder = tmp_path / "inputs" / "story"
    folder.mkdir(parents=True)
    (folder / "source.md").write_text("A story.", encoding="utf-8")
    (folder / "prompt.md").write_text("A prompt.", encoding="utf-8")
    (folder / "task-contract.json").write_text("{}", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: captured.update(kwargs))
    event = {"sequence": 1, "item_id": "story", "arm_id": arm["arm_id"], "repetition": 1}
    frozen = {"contract": {"arms": [arm], "provider": runner.contract()["provider"]}}
    assert runner._run(event, frozen, tmp_path, 1.0, allow_remote=False) == tmp_path / "runs" / "story" / arm["arm_id"] / "run-01" / "run.json"
    assert captured["allow_remote"] is False


def test_native_total_score_field_is_used_for_all_three_established_arms() -> None:
    analysis = _module("analyze_study")
    for arm in ("naplan_narrative_2022", "cambridge_igcse_0500_p2_mj_2024", "oregon_narrative_2017"):
        assert analysis._native_score(arm, {"total_score": 17}) == 17
        with pytest.raises(KeyError):
            analysis._native_score(arm, {"total": 17})


def test_journal_recovers_only_an_exact_plan_prefix(tmp_path: Path) -> None:
    study = _module("study")
    runner = _module("run_study")
    frozen = {"schedule": study.frozen_schedule(["one"], [arm["arm_id"] for arm in study.contract()["arms"]], 5)}
    plans = runner._plans(frozen)
    journal = tmp_path / runner.JOURNAL
    journal.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in plans[:3]) + "\n", encoding="utf-8")
    path, completed = runner._prepare_journal(tmp_path, frozen)
    assert completed == 0
    assert runner._read_journal(path) == plans
    journal.write_text(json.dumps({**plans[0], "item_id": "tampered"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-prefix"):
        runner._prepare_journal(tmp_path, frozen)


def test_journal_recovers_only_a_torn_unterminated_tail_and_reseals_the_valid_prefix(tmp_path: Path) -> None:
    study = _module("study")
    runner = _module("run_study")
    frozen = {"schedule": study.frozen_schedule(["one"], [arm["arm_id"] for arm in study.contract()["arms"]], 5)}
    plans = runner._plans(frozen)
    journal = tmp_path / runner.JOURNAL
    runner._append(journal, plans[0])
    with journal.open("ab") as handle:
        handle.write(b'{"event":"planned"')
    path, completed = runner._prepare_journal(tmp_path, frozen)
    assert completed == 0
    assert runner._read_journal(path) == plans


@pytest.mark.parametrize("tail", [b"\n", b" \t\n", b"\n\n"])
def test_journal_rejects_blank_or_whitespace_newline_terminated_records(tail: bytes, tmp_path: Path) -> None:
    study = _module("study")
    runner = _module("run_study")
    analysis = _module("analyze_study")
    frozen = {"schedule": study.frozen_schedule(["one"], [arm["arm_id"] for arm in study.contract()["arms"]], 5)}
    plans = runner._plans(frozen)
    journal = tmp_path / runner.JOURNAL
    journal.write_bytes(json.dumps(plans[0], sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" + tail)
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        runner._read_journal(journal)
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        runner._prepare_journal(tmp_path, frozen)
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        analysis._journal(tmp_path, {"schedule": [], "contract": {"arms": []}})


def test_journal_rejects_missing_or_extra_completed_run_bindings_before_resume(tmp_path: Path) -> None:
    study = _module("study")
    runner = _module("run_study")
    frozen = {"schedule": study.frozen_schedule(["one"], [arm["arm_id"] for arm in study.contract()["arms"]], 5)}
    plans = runner._plans(frozen)
    journal = tmp_path / runner.JOURNAL
    journal.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in plans) + "\n", encoding="utf-8")
    missing = {**plans[0], "event": "completed", "run_binding_sha256": "0" * 64}
    journal.write_text(journal.read_text(encoding="utf-8") + json.dumps(missing, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="existing final run manifest"):
        runner._prepare_journal(tmp_path, frozen)
    bindings = []
    for plan in plans:
        binding = runner._binding_path(tmp_path, plan)
        binding.parent.mkdir(parents=True, exist_ok=True)
        binding.write_text(json.dumps({"sequence": plan["sequence"]}), encoding="utf-8")
        bindings.append({**plan, "event": "completed", "run_binding_sha256": runner.sha(binding)})
    journal.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in [*plans, *bindings, bindings[-1]]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="extra completion"):
        runner._prepare_journal(tmp_path, frozen)


def test_sample_bindings_rederive_parent_fields_quality_band_and_input_fingerprints(tmp_path: Path) -> None:
    study = _module("study")
    folder = tmp_path / "inputs" / "story"
    folder.mkdir(parents=True)
    source, prompt = "A source.", "A prompt."
    (folder / "source.md").write_text(source, encoding="utf-8")
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")
    study.write_json(folder / "task-contract.json", {"fixture": True})
    hanna = study.hanna()
    item = hanna.HannaItem("story", "1", "model", prompt, source, {key: (3, 3, 3) for key in hanna.RATING_DIMENSIONS})
    study.write_json(folder / "human-ratings.json", study._authoritative_rating(item))
    parent_row = {"item_id": "story", "model": "model", "story_id": "1", "quartile": 2, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "story_sha256": hashlib.sha256(source.encode()).hexdigest(), "prompt_group_id": "prompt-fixture", "selected_rank": 1}
    sample = {"item_id": "story", "model": "model", "story_id": "1", "development_quartile": 2, "prompt_sha256": parent_row["prompt_sha256"], "story_sha256": parent_row["story_sha256"], "human_overall": 3.0, "parent_development_row": parent_row, "parent_development_row_sha256": hashlib.sha256(study.canonical(parent_row)).hexdigest(), "inputs": {name: study.fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json", "human-ratings.json")}, "frozen_quality_band": 3}
    cutpoints = {"q1_upper": 1.0, "q2_upper": 2.0, "q3_upper": 3.0}
    study._validate_sample_binding(tmp_path, sample, {"partitions": {"development": [parent_row]}}, cutpoints, item)
    with pytest.raises(ValueError, match="quality band"):
        study._validate_sample_binding(tmp_path, {**sample, "frozen_quality_band": 4}, {"partitions": {"development": [parent_row]}}, cutpoints, item)
    with pytest.raises(ValueError, match="monotonic"):
        study._quality_band(3.0, {"q1_upper": 3.0, "q2_upper": 2.0, "q3_upper": 4.0})
    values = [float(index) for index in range(88)]
    cutpoints = study._quality_cutpoints(values)
    assert {**cutpoints, "q2_upper": 99.0} != study._quality_cutpoints(values)


def test_analyzer_loads_a_complete_accepted_hbq_run_without_helper_mocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis, sample, arm, work, output, calls = _complete_hbq_run(tmp_path, monkeypatch)
    score, sessions, commitments, verdicts, metadata = analysis._load_run(work, sample, arm, 1)
    assert calls == 6
    assert score == pytest.approx(100.0)
    assert len(sessions) == len(commitments) == 6
    assert len(verdicts) == len(metadata) == sample["question_count"] == 179
    assert len(list((output / "responses").glob("batch-*.json"))) == 6


def test_analyzer_replays_a_real_hbq_retry_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis, sample, arm, work, output, calls = _complete_hbq_run(tmp_path, monkeypatch, retry_first=True)
    score, sessions, commitments, verdicts, _ = analysis._load_run(work, sample, arm, 1)
    rejected = output / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    checkpoint = json.loads((output / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    assert calls == 7
    assert score == pytest.approx(100.0)
    assert len(verdicts) == 179
    assert rejected.is_file()
    assert checkpoint["accepted_attempt"] == 2
    assert len(sessions) == len(commitments) == 7


def test_rejected_hbq_attempt_artifact_semantics_and_session_availability_are_revalidated(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    path = tmp_path / "run"
    rejected = path / "responses" / "rejected" / "batch-0001"
    rejected.mkdir(parents=True)
    record_path = rejected / "attempt-0001.json"
    record_path.write_text(json.dumps({"stage": "model_output", "raw_content": {"text": "{}"}}), encoding="utf-8")
    sessions, commitments = analysis._validate_hbq_rejected_attempts(
        path,
        {"artifact_id": "story", "bundle_id": "prose.short_story", "judge_id": "judge"},
        {"run_id": "run"},
        [{"question_ids": ["q"]}],
        "source text",
        "prompt text",
        3,
    )
    assert sessions == [None]
    assert commitments == [hashlib.sha256(record_path.read_bytes()).hexdigest()]
    record_path.write_text(json.dumps({"stage": "model_output", "raw_content": {"text": "{}"}, "provider": {"provider_artifacts": {"bad": {"path": "missing.txt"}}}}), encoding="utf-8")
    with pytest.raises(Exception, match="artifact"):
        analysis._validate_hbq_rejected_attempts(path, {"artifact_id": "story", "bundle_id": "prose.short_story", "judge_id": "judge"}, {"run_id": "run"}, [{"question_ids": ["q"]}], "source text", "prompt text", 3)


def test_native_artifact_matrix_binds_rendered_prompt_result_and_session_availability(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    arm = next(item for item in analysis.contract()["arms"] if item["arm_id"] == "holistic_anchored")
    sample = {"item_id": "story"}
    inputs = tmp_path / "inputs" / "story"
    inputs.mkdir(parents=True)
    source, prompt = "A grounded exact quote. Another exact quote.", "Write a story."
    (inputs / "source.md").write_text(source, encoding="utf-8")
    (inputs / "prompt.md").write_text(prompt, encoding="utf-8")
    result = {
        "method": "holistic_anchored_v1", "score": 4, "rationale": "Coherent.",
        "strengths": ["Voice", "Image"], "limitations": ["Pacing"],
        "evidence": [{"quote": "grounded exact quote", "explanation": "Grounded."}, {"quote": "Another exact quote", "explanation": "Also grounded."}],
    }
    schema = analysis._json(analysis.HERE / arm["schema"])
    rendered = analysis._artifact_prompt((analysis.HERE / arm["prompt"]).read_text(encoding="utf-8"), source, prompt)
    configuration = {
        "name": "story-holistic_anchored-run-01", "provider": "codex", "model": analysis.contract()["provider"]["model"],
        "reasoning": analysis.contract()["provider"]["reasoning"], "prompt_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(analysis._structured_json_bytes(schema)).hexdigest(),
    }
    manifest = {"format_version": 1, "configuration": configuration, "config_sha256": hashlib.sha256(analysis._structured_json_bytes(configuration)).hexdigest()}
    content = json.dumps(result, sort_keys=True)
    response = {
        "format_version": 1, "config_sha256": manifest["config_sha256"], "prompt_sha256": configuration["prompt_sha256"],
        "schema_sha256": configuration["schema_sha256"], "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "result_sha256": hashlib.sha256(analysis._structured_json_bytes(result)).hexdigest(), "provider": {},
    }
    run = tmp_path / "run"
    run.mkdir()
    (run / "request.prompt.txt.gz").write_bytes(gzip.compress(rendered.encode("utf-8"), mtime=0))
    (run / "response.schema.json").write_bytes(analysis._structured_json_bytes(analysis._provider_response_schema(schema)))
    assert analysis._validate_native_binding(run, tmp_path, sample, arm, 1, result, response, manifest) is None
    (run / "request.prompt.txt.gz").write_bytes(gzip.compress(b"tampered", mtime=0))
    with pytest.raises(ValueError, match="persisted prompt"):
        analysis._validate_native_binding(run, tmp_path, sample, arm, 1, result, response, manifest)
    (run / "request.prompt.txt.gz").write_bytes(gzip.compress(rendered.encode("utf-8"), mtime=0))
    (run / "response.schema.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="projected response schema"):
        analysis._validate_native_binding(run, tmp_path, sample, arm, 1, result, response, manifest)
    (run / "response.schema.json").write_bytes(analysis._structured_json_bytes(analysis._provider_response_schema(schema)))
    response["result_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="binding"):
        analysis._validate_native_binding(run, tmp_path, sample, arm, 1, result, response, manifest)


def test_native_semantic_rejection_writer_retries_and_analyzer_replays_actual_nested_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hbqrs import longform_runner

    runner = _module("run_study")
    analysis = _module("analyze_study")
    arm = next(value for value in runner.contract()["arms"] if value["arm_id"] == "holistic_anchored")
    folder = tmp_path / "inputs" / "story"
    folder.mkdir(parents=True)
    source, prompt = "A grounded exact quote. Another exact quote.", "Write a story."
    (folder / "source.md").write_text(source, encoding="utf-8")
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")
    event = {"sequence": 1, "item_id": "story", "arm_id": arm["arm_id"], "repetition": 1}
    invalid = {"method": "holistic_anchored_v1", "score": 4, "rationale": "Coherent.", "strengths": ["Voice", "Image"], "limitations": ["Pacing"], "evidence": [{"quote": "invented first", "explanation": "Ungrounded."}, {"quote": "invented second", "explanation": "Also ungrounded."}]}
    accepted = {**invalid, "evidence": [{"quote": "grounded exact quote", "explanation": "Grounded."}, {"quote": "Another exact quote", "explanation": "Also grounded."}]}
    calls = 0

    def fake_codex(**kwargs):
        nonlocal calls
        calls += 1
        result = invalid if calls == 1 else accepted
        return json.dumps(result, sort_keys=True), {"reported": {"provider": "openai", "model": runner.contract()["provider"]["model"], "reasoning_effort": runner.contract()["provider"]["reasoning"], "session_id": f"native-session-{calls}"}}

    monkeypatch.setattr(longform_runner, "_call_codex", fake_codex)
    frozen = {"contract": {"arms": [arm], "provider": runner.contract()["provider"]}}
    binding = runner._run(event, frozen, tmp_path, 1.0, allow_remote=True)
    path = binding.parent
    rejected = json.loads((path / "attempts" / "rejected-0001.json").read_text(encoding="utf-8"))
    assert calls == 2
    assert set(rejected) == {"format_version", "reason", "response", "result"}
    manifest = json.loads(binding.read_text(encoding="utf-8"))
    sample = {"item_id": "story"}
    sessions, commitments = analysis._validate_native_attempts(path, tmp_path, sample, arm, 1, manifest)
    assert sessions == ["native-session-1"]
    assert commitments == [hashlib.sha256((path / "attempts" / "rejected-0001.json").read_bytes()).hexdigest()]


def test_confidence_diagnostics_separate_proxy_prior_roles_and_canonical_score() -> None:
    analysis = _module("analyze_study")
    metadata = [
        {"question_id": "domain", "role": "domain", "effective_weight": 2.0},
        {"question_id": "penalty", "role": "penalty", "effective_weight": 1.0},
        {"question_id": "gate", "role": "hard_gate", "effective_weight": 1.0},
    ]
    verdicts = []
    for repetition in range(5):
        verdicts.append([
            {"question_id": "domain", "verdict": "YES", "confidence": 0.9},
            {"question_id": "penalty", "verdict": "YES" if repetition < 3 else "NO", "confidence": 0.6},
            {"question_id": "gate", "verdict": "N/A", "confidence": 0.8},
        ])
    value = analysis._leaf_metrics(verdicts, metadata)
    diagnostic = value["confidence_diagnostics"]
    assert diagnostic["stable_and_flipped"]["stable"]["leaf_count"] == 2
    assert diagnostic["stable_and_flipped"]["flipped"]["leaf_count"] == 1
    assert diagnostic["roles"]["penalty"]["leaf_count"] == 1
    assert diagnostic["roles"]["hard_gate"]["leaf_count"] == 1
    assert diagnostic["historical_prior"]["status"] == "unavailable"
    assert diagnostic["effective_confidence_mass_is_not_coverage"] is True
    assert diagnostic["canonical_score_and_coverage_unchanged"] is True
    assert diagnostic["target"] == "repeat_consensus_proxy_not_human_truth"


def test_full_analysis_emits_prompt_cluster_and_confidence_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _module("analyze_study")
    arms = analysis.contract()["arms"]
    samples = [{"item_id": f"i{i}", "model": f"m{i}", "prompt_sha256": "shared" if i < 2 else f"p{i}", "human_overall": float(i), "frozen_quality_band": 1 if i < 3 else 4} for i in range(11)]
    frozen = {"study_id": "hbq-multisample-repeatability-v1", "study_contract_sha256": "c" * 64, "runtime_sha256": "r" * 64, "contract": {"arms": arms, "repetitions": 5, "primary_metrics": {"bootstrap": {"seed": 560820}}}, "samples": samples, "full_development_quality_cutpoints": {"method": "fixture"}}
    monkeypatch.setattr(analysis, "validate", lambda work, data_dir: frozen)
    monkeypatch.setattr(analysis, "_journal", lambda work, value: None)
    monkeypatch.setattr(analysis, "sha", lambda path: "f" * 64)
    counter = 0
    def fake_load(work, sample, arm, repetition):
        nonlocal counter
        counter += 1
        sessions = [f"session-{counter}"]
        score = float(int(sample["item_id"][1:]) + repetition)
        if arm["kind"] == "hbq":
            verdict = [{"question_id": "q", "verdict": "YES", "confidence": 0.8}]
            metadata = [{"question_id": "q", "role": "domain", "effective_weight": 1.0}]
            return score, sessions, [f"commitment-{counter}"], verdict, metadata
        return score, sessions, [f"commitment-{counter}"], None, None
    monkeypatch.setattr(analysis, "_load_run", fake_load)
    output = tmp_path / "analysis"
    analysis.analyze(tmp_path / "work", output, tmp_path / "data")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["prompt_cluster_count"] == 10
    assert summary["paired_prompt_cluster_bootstrap"]["cluster_count"] == 10
    assert summary["paired_prompt_cluster_bootstrap"]["estimand"] == "equal_sample_mean_paired_delta"
    assert summary["canonical_scores_and_coverage_are_not_confidence_weighted"] is True
    assert summary["fresh_session_commitment"]["status"] == "verified_unique"
    hbq = summary["arms"]["hbq_short_story_batch32"]
    assert len(hbq["quality_sensitivity"]["per_repeat_spearman_vs_human"]) == 5
    assert hbq["leaf_repeatability"]["confidence_macro"]["repeat_consensus_is_not_truth"] is True
