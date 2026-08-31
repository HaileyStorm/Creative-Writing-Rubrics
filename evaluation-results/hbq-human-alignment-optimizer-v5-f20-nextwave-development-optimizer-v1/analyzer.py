from __future__ import annotations

"""Development-only Optuna/DSPy analysis over the frozen 33-cell Grok score."""

import argparse
import hashlib
import itertools
import json
import math
import os
import re
import stat
import sys
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCORER = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1" / "executor.py"
NORMALIZER = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-normalize-v1" / "executor.py"
NORMALIZER_CONTRACT = NORMALIZER.parent / "study-contract.json"
LIVE_EXEC = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1" / "executor.py"
LIVE_CONTRACT = LIVE_EXEC.parent / "study-contract.json"
GENERATION_EXEC = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-exec-v1" / "executor.py"
MATERIALIZER = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1" / "materialize.py"
EVALUATOR_STUDY = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-shrinkage-eval-v1" / "study.py"
EVALUATOR_ANALYZE = EVALUATOR_STUDY.parent / "analyze.py"
NATIVE_EXEC = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
GENERATION_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-grok-544af81-20260831a")
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-development-optimizer-v1"
BASELINE = "candidate-102cc7f06c9a99a7"
WINNER = "normalized-nextwave-08-conservative-hybrid"
SEED = 202608311
OPTUNA_VERSION = "4.9.0"
DSPY_VERSION = "3.3.1"

EXPECTED = {
    "collector_sha256": "d2f4c329fb05f31a27578483548855cfb7ab77c26ee75bbb44367019a2e8fe99",
    "schedule_sha256": "eb54e261111719716d056f6b5024b668894f0e49899b84351e2dbfe20e47b2cc",
    "scorer_executor_sha256": "c1641089073c07d5906d31685101dedbd5cdc936568baeb039a612f85b0f7539",
    "normalized_source_manifest_sha256": "7eba326fca7f6621edbc9a809d9305b580f6487fc6ba4de4c9f3e9d9c88a5a36",
    "winner_artifact_sha256": "48055e2ab5d7c2b347aecf0895b46b8e468c2de2af06b25db3215fd3a0af158c",
    "frozen_successor_sha256": "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7",
    "hanna_csv_sha256": "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b",
    "admitted_source_snapshot_sha256": "e85a341f8fa8da3d8e55d602d7bade5af1abbab331bacd2eb1cc04d341897e20",
}

WORST_WEIGHTS = (0.0, 0.1, 0.25)
LOO_WEIGHTS = (0.0, 0.1, 0.25)
NEXT_STEP_FRACTIONS = (0.05, 0.10)
STEP_RISK_SCALE = 0.05


@dataclass(frozen=True)
class FileAdmission:
    path: Path
    raw: bytes
    identity: tuple[int, int, int, int]


@dataclass(frozen=True)
class DirectoryAdmission:
    path: Path
    identity: tuple[int, int, int, int]
    relative_files: tuple[str, ...]


class SourceSnapshot:
    def __init__(self, files: dict[Path, FileAdmission], directories: dict[Path, DirectoryAdmission]):
        self._files = files
        self._directories = directories

    def bytes(self, path: Path) -> bytes:
        key = _absolute(path)
        admitted = self._files.get(key)
        if admitted is None:
            raise ValueError(f"source was not admitted: {path.name}")
        return admitted.raw

    def files_under(self, path: Path) -> tuple[Path, ...]:
        root = _absolute(path)
        admitted = self._directories.get(root)
        if admitted is None:
            raise ValueError(f"source directory was not admitted: {path.name}")
        return tuple(root / relative for relative in admitted.relative_files)

    def verify_unchanged(self) -> None:
        for root, admitted in self._directories.items():
            _assert_plain(root, directory=True)
            if _identity(root.stat()) != admitted.identity:
                raise ValueError(f"admitted source directory identity changed: {root.name}")
            current = _directory_files(root)[0]
            if current != admitted.relative_files:
                raise ValueError(f"admitted source directory inventory changed: {root.name}")
        for path, admitted in self._files.items():
            _assert_plain(path, directory=False)
            before = path.stat()
            raw = path.read_bytes()
            after = path.stat()
            if _identity(before) != admitted.identity or _identity(after) != admitted.identity or raw != admitted.raw:
                raise ValueError(f"admitted source identity or bytes changed: {path.name}")

    def commitment(
        self, *, roots: Mapping[str, Path], files: Mapping[str, Path]
    ) -> str:
        manifest: dict[str, Any] = {"format_version": 1, "roots": {}, "files": {}}
        for label, supplied_root in sorted(roots.items()):
            root = _absolute(supplied_root)
            admitted = self._directories.get(root)
            if admitted is None:
                raise ValueError("snapshot commitment root was not admitted")
            manifest["roots"][label] = [
                {
                    "path": relative,
                    "bytes": len(self.bytes(root / relative)),
                    "sha256": sha256(self.bytes(root / relative)),
                }
                for relative in admitted.relative_files
            ]
        for label, path in sorted(files.items()):
            raw = self.bytes(path)
            manifest["files"][label] = {"bytes": len(raw), "sha256": sha256(raw)}
        assert_public(manifest)
        return sha256(manifest)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (int(value.st_dev), int(value.st_ino), int(value.st_size), int(value.st_mtime_ns))


def _is_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError as error:
        raise ValueError(f"cannot inspect source ancestry: {path}") from error
    attributes = int(getattr(value, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    junction = bool(getattr(os.path, "isjunction", lambda _value: False)(path))
    return path.is_symlink() or junction or bool(attributes & reparse_flag)


def _assert_plain(path: Path, *, directory: bool) -> None:
    current = _absolute(path)
    if not current.exists() or (not current.is_dir() if directory else not current.is_file()):
        raise ValueError(f"required source path is absent or wrong kind: {path.name}")
    while True:
        if _is_reparse(current):
            raise ValueError(f"source path ancestry contains a reparse point: {current.name}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def _admit_file(path: Path) -> FileAdmission:
    path = _absolute(path)
    _assert_plain(path, directory=False)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if _identity(before) != _identity(after):
        raise ValueError(f"source changed while admitted: {path.name}")
    return FileAdmission(path=path, raw=raw, identity=_identity(after))


def _admit_directory(path: Path) -> tuple[DirectoryAdmission, list[Path]]:
    root = _absolute(path)
    _assert_plain(root, directory=True)
    before = root.stat()
    relative, entries = _directory_files(root)
    after = root.stat()
    if _identity(before) != _identity(after):
        raise ValueError(f"source directory changed while admitted: {root.name}")
    return DirectoryAdmission(root, _identity(after), relative), entries


def _directory_files(root: Path) -> tuple[tuple[str, ...], list[Path]]:
    entries: list[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        for candidate in current.iterdir():
            if candidate.is_dir():
                _assert_plain(candidate, directory=True)
                pending.append(candidate)
            elif candidate.is_file():
                _assert_plain(candidate, directory=False)
                entries.append(candidate)
            else:
                raise ValueError(f"unsupported source entry kind: {candidate.name}")
    entries.sort(key=lambda value: value.relative_to(root).as_posix())
    relative = tuple(candidate.relative_to(root).as_posix() for candidate in entries)
    return relative, entries


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256(value: bytes | Mapping[str, Any] | list[Any]) -> str:
    raw = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(raw).hexdigest()


def stable(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required plain file is absent: {path.name}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"source changed while reading: {path.name}")
    return raw


def admit_sources(
    *,
    collector_path: Path,
    score_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
) -> SourceSnapshot:
    files: dict[Path, FileAdmission] = {}
    directories: dict[Path, DirectoryAdmission] = {}
    for root in (score_root, normalized_root, materialization_root, GENERATION_ROOT):
        directory, members = _admit_directory(root)
        directories[directory.path] = directory
        for member in members:
            admission = _admit_file(member)
            files[admission.path] = admission
    for path in (
        collector_path, frozen_successor_path, hanna_csv_path, SCORER,
        NORMALIZER, NORMALIZER_CONTRACT, LIVE_EXEC, LIVE_CONTRACT,
        GENERATION_EXEC, MATERIALIZER, EVALUATOR_STUDY, EVALUATOR_ANALYZE, NATIVE_EXEC,
    ):
        admission = _admit_file(path)
        if admission.path in files:
            raise ValueError("source admission paths overlap")
        files[admission.path] = admission
    snapshot = SourceSnapshot(files, directories)
    if sha256(snapshot.bytes(collector_path)) != EXPECTED["collector_sha256"]:
        raise ValueError("frozen scorer collector drifted")
    if sha256(snapshot.bytes(score_root / "schedule.json")) != EXPECTED["schedule_sha256"]:
        raise ValueError("frozen scorer schedule drifted")
    if sha256(snapshot.bytes(normalized_root / "source-manifest.json")) != EXPECTED["normalized_source_manifest_sha256"]:
        raise ValueError("normalized source manifest drifted")
    if sha256(snapshot.bytes(normalized_root / "nextwave-08-conservative-hybrid.json")) != EXPECTED["winner_artifact_sha256"]:
        raise ValueError("candidate 08 artifact drifted")
    if sha256(snapshot.bytes(frozen_successor_path)) != EXPECTED["frozen_successor_sha256"]:
        raise ValueError("frozen successor contract drifted")
    if sha256(snapshot.bytes(hanna_csv_path)) != EXPECTED["hanna_csv_sha256"]:
        raise ValueError("HANNA CSV drifted")
    if sha256(snapshot.bytes(SCORER)) != EXPECTED["scorer_executor_sha256"]:
        raise ValueError("frozen scorer executor drifted")
    snapshot.verify_unchanged()
    return snapshot


def strict(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"{label} is not canonical JSON")
    return value


def json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def parse_no_duplicates(raw: bytes, label: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"{label} contains a duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=hook)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def assert_public(value: Any) -> None:
    private = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\|/users/|/home/|haile)")
    if isinstance(value, str):
        if private.search(value):
            raise ValueError("durable optimizer artifact leaks a private path or identity")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            assert_public(key)
            assert_public(item)
    elif isinstance(value, list):
        for item in value:
            assert_public(item)


def expected_contract() -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "source": {
            "scorer_commit": "6cfd64e8db03b06c70d39d79ca4aac24ba498232",
            "scorer_executor_sha256": EXPECTED["scorer_executor_sha256"],
            "collector_sha256": EXPECTED["collector_sha256"],
            "schedule_file_sha256": EXPECTED["schedule_sha256"],
            "recomputed_projection_sha256": "7c15ad195738d481d9bf5261e123df66369df627ac179014a8ca48200a2d6b30",
            "normalized_source_manifest_sha256": EXPECTED["normalized_source_manifest_sha256"],
            "frozen_successor_sha256": EXPECTED["frozen_successor_sha256"],
            "hanna_csv_sha256": EXPECTED["hanna_csv_sha256"],
            "admitted_source_snapshot_sha256": EXPECTED["admitted_source_snapshot_sha256"],
        },
        "geometry": {
            "endpoint": "grok-4.6-build",
            "candidates": 11,
            "development_prompt_groups": 3,
            "cells": 33,
            "confirmation_cells": 0,
        },
        "development": {
            "optuna": {
                "version": OPTUNA_VERSION,
                "sampler": "GridSampler",
                "seed": SEED,
                "trials": 198,
                "objective": "equal_group_mae_plus_low_weight_worst_group_leave_one_group_out_and_step_planning_penalties",
            },
            "dspy": {
                "version": DSPY_VERSION,
                "purpose": "example_and_signature_training_view_only",
                "lm_calls": 0,
                "predict_calls": 0,
            },
        },
        "authority": {
            "selection": "development_only_provisional",
            "confirmation": {"status": "unopened", "cells": 0},
            "sol_validation": "not_yet_run_for_candidate08",
            "general_hanna": "none",
            "promotion": "none",
            "runtime": "none",
        },
        "prohibitions": [
            "no provider or queue contact",
            "no held-out or confirmation targets",
            "no runtime DSPy or Optuna dependency",
            "no Sol generalization promotion or endpoint pooling claim",
        ],
    }


def load_contract() -> tuple[dict[str, Any], str]:
    raw = stable(HERE / "study-contract.json")
    value = parse_no_duplicates(raw, "study contract")
    if raw != canonical(value) + b"\n" or value != expected_contract():
        raise ValueError("study contract bytes or fields drifted")
    assert_public(value)
    return value, sha256(raw)


def validate_result_bytes(raw: bytes, expected: Mapping[str, Any]) -> dict[str, Any]:
    value = parse_no_duplicates(raw, "optimizer result")
    assert_public(value)
    if raw != canonical(value) + b"\n":
        raise ValueError("optimizer result is not exact canonical UTF-8 plus one LF")
    if value != expected:
        raise ValueError("optimizer result differs from recomputed evidence")
    internal = dict(value)
    digest = internal.pop("result_sha256", None)
    if digest != sha256(internal):
        raise ValueError("optimizer result internal hash drifted")
    return value


def _load_scorer(snapshot: SourceSnapshot) -> Any:
    module = types.ModuleType("_hanna_nextwave_scorer_for_dev_optimizer")
    module.__file__ = str(SCORER)
    sys.modules[module.__name__] = module
    exec(compile(snapshot.bytes(SCORER), str(SCORER), "exec"), module.__dict__)

    def admitted_load(path: Path, digest: str, name: str) -> Any:
        raw = snapshot.bytes(path)
        if module.sha256(raw) != digest:
            raise ValueError("pinned admitted dependency drifted")
        dependency = types.ModuleType(name)
        dependency.__file__ = str(path)
        sys.modules[name] = dependency
        try:
            exec(compile(raw, str(path), "exec"), dependency.__dict__)
        finally:
            sys.modules.pop(name, None)
        for stable_name in ("stable", "_stable"):
            if stable_name in dependency.__dict__:
                dependency.__dict__[stable_name] = snapshot.bytes
        if "_load" in dependency.__dict__:
            dependency.__dict__["_load"] = admitted_load
        return dependency

    module.stable = snapshot.bytes
    module.load = admitted_load
    return module


def recompute_projection(
    *,
    snapshot: SourceSnapshot,
    collector_path: Path,
    score_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
) -> dict[str, Any]:
    snapshot.verify_unchanged()
    scorer = _load_scorer(snapshot)
    value = scorer.descriptive_project(
        collector_path=collector_path,
        output_root=score_root,
        normalized_root=normalized_root,
        materialization_root=materialization_root,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    if (
        value.get("result_sha256") != "7c15ad195738d481d9bf5261e123df66369df627ac179014a8ca48200a2d6b30"
        or value.get("authority", {}).get("confirmation") != {"status": "unopened", "cells": 0}
        or len(value.get("metrics", [])) != 11
    ):
        raise ValueError("recomputed descriptive projection drifted")
    snapshot.verify_unchanged()
    return value


def diagnostics(metric: Mapping[str, Any]) -> dict[str, float]:
    groups = metric.get("group_mae")
    if not isinstance(groups, Mapping) or len(groups) != 3:
        raise ValueError("candidate group geometry drifted")
    values = [float(groups[key]) for key in sorted(groups)]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("candidate MAE is invalid")
    mean = sum(values) / 3
    reported = float(metric.get("equal_group_mae"))
    if not math.isclose(mean, reported, rel_tol=0, abs_tol=1e-12):
        raise ValueError("equal-group MAE does not recompute")
    loo_means = [(sum(values) - value) / 2 for value in values]
    return {
        "equal_group_mae": mean,
        "worst_group_mae": max(values),
        "worst_group_excess": max(values) - mean,
        "loo_instability": max(abs(value - mean) for value in loo_means),
    }


def regularized_score(diag: Mapping[str, float], *, worst_weight: float, loo_weight: float, next_step_fraction: float) -> float:
    robustness = diag["worst_group_excess"] + diag["loo_instability"]
    return (
        diag["equal_group_mae"]
        + worst_weight * diag["worst_group_excess"]
        + loo_weight * diag["loo_instability"]
        + STEP_RISK_SCALE * next_step_fraction * robustness
    )


def verify_optuna_trial_records(
    records: list[Mapping[str, Any]], by_candidate: Mapping[str, Mapping[str, float]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_ids = sorted(by_candidate)
    expected = set(itertools.product(candidate_ids, WORST_WEIGHTS, LOO_WEIGHTS, NEXT_STEP_FRACTIONS))
    verified: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float, float]] = set()
    for supplied in records:
        if set(supplied) != {"number", "params", "value"} or type(supplied.get("number")) is not int:
            raise ValueError("Optuna trial record fields drifted")
        params = supplied.get("params")
        value = supplied.get("value")
        if not isinstance(params, Mapping) or set(params) != {
            "candidate_id", "worst_group_weight", "loo_weight", "next_step_fraction"
        }:
            raise ValueError("Optuna trial params drifted")
        if type(params["candidate_id"]) is not str or any(
            type(params[key]) is not float for key in ("worst_group_weight", "loo_weight", "next_step_fraction")
        ):
            raise ValueError("Optuna trial param types drifted")
        key = (
            params["candidate_id"],
            params["worst_group_weight"],
            params["loo_weight"],
            params["next_step_fraction"],
        )
        if key not in expected or key in seen:
            raise ValueError("Optuna trial grid tuple is missing, duplicated, or fabricated")
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("Optuna trial value is invalid")
        recomputed = regularized_score(
            by_candidate[key[0]],
            worst_weight=key[1],
            loo_weight=key[2],
            next_step_fraction=key[3],
        )
        if not math.isclose(value, recomputed, rel_tol=0, abs_tol=1e-15):
            raise ValueError("Optuna trial value does not independently recompute")
        seen.add(key)
        verified.append({"number": supplied["number"], "params": dict(params), "value": value})
    if seen != expected or len(verified) != 198:
        raise ValueError("Optuna exact 198-tuple grid is incomplete")

    setting_winners: list[dict[str, Any]] = []
    grouped: dict[tuple[float, float, float], list[dict[str, Any]]] = {}
    for record in verified:
        params = record["params"]
        setting = (params["worst_group_weight"], params["loo_weight"], params["next_step_fraction"])
        grouped.setdefault(setting, []).append(record)
    expected_settings = set(itertools.product(WORST_WEIGHTS, LOO_WEIGHTS, NEXT_STEP_FRACTIONS))
    if set(grouped) != expected_settings or any(len(group) != 11 for group in grouped.values()):
        raise ValueError("Optuna verified trials do not form 18 complete settings")
    for setting in sorted(grouped):
        ranked = sorted(grouped[setting], key=lambda record: (record["value"], record["params"]["candidate_id"]))
        setting_winners.append(
            {
                "worst_group_weight": setting[0],
                "loo_weight": setting[1],
                "next_step_fraction": setting[2],
                "winner": ranked[0]["params"]["candidate_id"],
                "winner_score": ranked[0]["value"],
                "runner_up": ranked[1]["params"]["candidate_id"],
                "margin": ranked[1]["value"] - ranked[0]["value"],
            }
        )
    return verified, setting_winners


def run_optuna(metrics: list[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        import optuna  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("development analysis requires Optuna 4.9.0") from error
    if optuna.__version__ != OPTUNA_VERSION:
        raise ValueError("Optuna version drifted")
    candidate_ids = sorted(str(metric["candidate_id"]) for metric in metrics)
    by_candidate = {str(metric["candidate_id"]): diagnostics(metric) for metric in metrics}
    if len(candidate_ids) != 11 or set(candidate_ids) != set(by_candidate):
        raise ValueError("candidate geometry drifted")
    grid = {
        "candidate_id": candidate_ids,
        "worst_group_weight": list(WORST_WEIGHTS),
        "loo_weight": list(LOO_WEIGHTS),
        "next_step_fraction": list(NEXT_STEP_FRACTIONS),
    }
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.GridSampler(grid, seed=SEED)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    def objective(trial: Any) -> float:
        candidate_id = trial.suggest_categorical("candidate_id", candidate_ids)
        worst_weight = trial.suggest_categorical("worst_group_weight", list(WORST_WEIGHTS))
        loo_weight = trial.suggest_categorical("loo_weight", list(LOO_WEIGHTS))
        next_step_fraction = trial.suggest_categorical("next_step_fraction", list(NEXT_STEP_FRACTIONS))
        return regularized_score(
            by_candidate[candidate_id],
            worst_weight=float(worst_weight),
            loo_weight=float(loo_weight),
            next_step_fraction=float(next_step_fraction),
        )

    expected_trials = math.prod(len(values) for values in grid.values())
    study.optimize(objective, n_trials=expected_trials)
    if len(study.trials) != expected_trials or any(trial.state.name != "COMPLETE" for trial in study.trials):
        raise ValueError("Optuna grid did not complete exactly")
    records = [
        {"number": trial.number, "params": dict(trial.params), "value": trial.value}
        for trial in study.trials
    ]
    verified, setting_winners = verify_optuna_trial_records(records, by_candidate)
    winner_counts = {candidate_id: 0 for candidate_id in candidate_ids}
    for setting in setting_winners:
        winner_counts[setting["winner"]] += 1
    if winner_counts.get(WINNER) != len(setting_winners):
        raise ValueError("candidate 08 is not stable across the frozen low-penalty grid")
    baseline = by_candidate[BASELINE]["equal_group_mae"]
    winner = by_candidate[WINNER]["equal_group_mae"]
    high_penalty = sorted(
        (
            regularized_score(
                by_candidate[candidate_id],
                worst_weight=1.0,
                loo_weight=1.0,
                next_step_fraction=0.05,
            ),
            candidate_id,
        )
        for candidate_id in candidate_ids
    )
    return {
        "optimizer": f"optuna.GridSampler@{OPTUNA_VERSION}",
        "seed": SEED,
        "completed_trials": expected_trials,
        "verified_unique_grid_tuples": len(verified),
        "verified_trial_tuple_chain_sha256": sha256(
            [
                [
                    record["params"]["candidate_id"],
                    record["params"]["worst_group_weight"],
                    record["params"]["loo_weight"],
                    record["params"]["next_step_fraction"],
                    record["value"],
                ]
                for record in sorted(verified, key=lambda item: item["number"])
            ]
        ),
        "parameter_grid": grid,
        "objective": "equal_group_mae + worst_weight*worst_group_excess + loo_weight*loo_instability + 0.05*next_step_fraction*(worst_group_excess+loo_instability)",
        "next_step_term_is_planning_prior_not_empirical_outcome": True,
        "best_trial": {
            "number": study.best_trial.number,
            "value": study.best_value,
            "params": study.best_params,
        },
        "setting_count": len(setting_winners),
        "candidate08_wins": winner_counts[WINNER],
        "candidate08_min_margin": min(item["margin"] for item in setting_winners),
        "winner_counts": {key: value for key, value in winner_counts.items() if value},
        "outside_grid_sensitivity": {
            "worst_group_weight": 1.0,
            "loo_weight": 1.0,
            "next_step_fraction": 0.05,
            "winner": high_penalty[0][1],
            "candidate08_rank": next(index for index, item in enumerate(high_penalty, start=1) if item[1] == WINNER),
            "interpretation": "Strong robustness penalties can reverse the development ranking; candidate08 preference is limited to the frozen low-penalty grid.",
        },
        "unregularized": {
            "winner": WINNER,
            "winner_equal_group_mae": winner,
            "baseline_equal_group_mae": baseline,
            "absolute_mae_reduction": baseline - winner,
            "relative_mae_reduction": (baseline - winner) / baseline,
        },
        "candidate_diagnostics": {key: by_candidate[key] for key in candidate_ids},
    }


def _candidate_materials(
    *, snapshot: SourceSnapshot, normalized_root: Path, materialization_root: Path, expected_ids: set[str]
) -> dict[str, dict[str, Any]]:
    instruction = snapshot.bytes(materialization_root / "parent-instruction.bin")
    profile_raw = snapshot.bytes(materialization_root / "parent-profile.bin")
    if sha256(instruction) != "f318da394124d72dea4e9fb896d0345c6c5136d4839feae2cff1e389ea642de1":
        raise ValueError("baseline instruction drifted")
    if sha256(profile_raw) != "3d90b5bdd1b1cd1673cc45b834485754eb0ee01f89e2c3c7ddf5d31e7d24c74f":
        raise ValueError("baseline profile drifted")
    profile = strict(profile_raw, "baseline profile")
    materials: dict[str, dict[str, Any]] = {
        BASELINE: {"instruction": instruction.decode(), "profile": profile}
    }
    candidate_paths = [
        path for path in snapshot.files_under(normalized_root)
        if path.parent == _absolute(normalized_root) and path.name.startswith("nextwave-") and path.suffix == ".json"
    ]
    for path in candidate_paths:
        value = json_object(snapshot.bytes(path), path.name)
        source_cell = value.get("source_cell")
        normalized = value.get("normalized")
        if not isinstance(source_cell, Mapping) or not isinstance(normalized, Mapping):
            raise ValueError("normalized candidate structure drifted")
        candidate_id = "normalized-" + str(source_cell.get("cell_id"))
        candidate_instruction = normalized.get("instruction")
        candidate_profile = normalized.get("profile")
        if not isinstance(candidate_instruction, str) or not isinstance(candidate_profile, Mapping):
            raise ValueError("normalized prompt/profile is absent")
        if sha256(candidate_instruction.encode()) != normalized.get("instruction_sha256"):
            raise ValueError("normalized instruction hash drifted")
        if sha256(candidate_profile) != normalized.get("profile_sha256"):
            raise ValueError("normalized profile hash drifted")
        materials[candidate_id] = {"instruction": candidate_instruction, "profile": dict(candidate_profile)}
    if set(materials) != expected_ids:
        raise ValueError("DSPy candidate materials do not match scorer candidates")
    return materials


def build_dspy_training_view(
    *,
    metrics: list[Mapping[str, Any]],
    optimization: Mapping[str, Any],
    snapshot: SourceSnapshot,
    normalized_root: Path,
    materialization_root: Path,
) -> dict[str, Any]:
    try:
        import dspy  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("development analysis requires DSPy 3.3.1") from error
    if dspy.__version__ != DSPY_VERSION:
        raise ValueError("DSPy version drifted")

    class CandidateEvidenceSignature(dspy.Signature):
        """Represent frozen candidate evidence for development-only prompt-profile iteration."""

        candidate_id: str = dspy.InputField()
        instruction: str = dspy.InputField()
        profile_json: str = dspy.InputField()
        group_mae_json: str = dspy.InputField()
        equal_group_mae: float = dspy.OutputField()
        regularized_mae: float = dspy.OutputField()

    class NextPromptProfileSignature(dspy.Signature):
        """Propose one versioned small-step descendant; confirmation and promotion remain closed."""

        parent_candidate_id: str = dspy.InputField()
        parent_instruction: str = dspy.InputField()
        parent_profile_json: str = dspy.InputField()
        optimizer_diagnostics_json: str = dspy.InputField()
        requested_step_fraction: float = dspy.InputField()
        descendant_instruction: str = dspy.OutputField()
        descendant_profile_json: str = dspy.OutputField()
        change_summary: str = dspy.OutputField()

    metric_by_id = {str(metric["candidate_id"]): metric for metric in metrics}
    materials = _candidate_materials(
        snapshot=snapshot,
        normalized_root=normalized_root,
        materialization_root=materialization_root,
        expected_ids=set(metric_by_id),
    )
    examples = []
    selected = optimization["best_trial"]["params"]
    for candidate_id in sorted(metric_by_id):
        metric = metric_by_id[candidate_id]
        material = materials[candidate_id]
        score = regularized_score(
            diagnostics(metric),
            worst_weight=float(selected["worst_group_weight"]),
            loo_weight=float(selected["loo_weight"]),
            next_step_fraction=float(selected["next_step_fraction"]),
        )
        example = dspy.Example(
            candidate_id=candidate_id,
            instruction=material["instruction"],
            profile_json=canonical(material["profile"]).decode(),
            group_mae_json=canonical(metric["group_mae"]).decode(),
            equal_group_mae=float(metric["equal_group_mae"]),
            regularized_mae=score,
        ).with_inputs("candidate_id", "instruction", "profile_json", "group_mae_json")
        if set(example.inputs().toDict()) != {"candidate_id", "instruction", "profile_json", "group_mae_json"}:
            raise ValueError("DSPy evidence inputs drifted")
        if set(example.labels().toDict()) != {"equal_group_mae", "regularized_mae"}:
            raise ValueError("DSPy evidence labels drifted")
        examples.append(example)
    parent = materials[WINNER]
    next_input = dspy.Example(
        parent_candidate_id=WINNER,
        parent_instruction=parent["instruction"],
        parent_profile_json=canonical(parent["profile"]).decode(),
        optimizer_diagnostics_json=canonical(
            {
                "candidate": optimization["candidate_diagnostics"][WINNER],
                "candidate08_wins": optimization["candidate08_wins"],
                "setting_count": optimization["setting_count"],
            }
        ).decode(),
        requested_step_fraction=0.05,
    ).with_inputs(
        "parent_candidate_id",
        "parent_instruction",
        "parent_profile_json",
        "optimizer_diagnostics_json",
        "requested_step_fraction",
    )
    if next_input.labels().toDict():
        raise ValueError("next-step DSPy view must not fabricate a descendant label")
    evidence_digests = [sha256(example.toDict()) for example in examples]
    return {
        "library": f"dspy@{DSPY_VERSION}",
        "evidence_signature": CandidateEvidenceSignature.__name__,
        "next_candidate_signature": NextPromptProfileSignature.__name__,
        "evidence_examples": len(examples),
        "evidence_example_chain_sha256": sha256(evidence_digests),
        "next_input_sha256": sha256(next_input.toDict()),
        "next_parent": WINNER,
        "requested_step_fraction": 0.05,
        "lm_calls": 0,
        "predict_calls": 0,
        "descendant_generated": False,
        "note": "DSPy objects validate the frozen training view only; no LM or optimizer proposal was invoked.",
    }


def analyze(
    *,
    collector_path: Path,
    score_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
    between_phases: Callable[[SourceSnapshot], None] | None = None,
) -> dict[str, Any]:
    snapshot = admit_sources(
        collector_path=collector_path,
        score_root=score_root,
        normalized_root=normalized_root,
        materialization_root=materialization_root,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    snapshot_sha256 = snapshot.commitment(
        roots={
            "score_execution": score_root,
            "normalized_candidates": normalized_root,
            "materialization": materialization_root,
            "generation_lineage": GENERATION_ROOT,
        },
        files={
            "collector": collector_path,
            "frozen_successor": frozen_successor_path,
            "hanna_csv": hanna_csv_path,
            "scorer_executor": SCORER,
            "normalizer_executor": NORMALIZER,
            "normalizer_contract": NORMALIZER_CONTRACT,
            "live_executor": LIVE_EXEC,
            "live_contract": LIVE_CONTRACT,
            "generation_executor": GENERATION_EXEC,
            "materializer": MATERIALIZER,
            "evaluator_study": EVALUATOR_STUDY,
            "evaluator_analyze": EVALUATOR_ANALYZE,
            "native_executor": NATIVE_EXEC,
        },
    )
    if snapshot_sha256 != EXPECTED["admitted_source_snapshot_sha256"]:
        raise ValueError("admitted source snapshot commitment drifted")
    projection = recompute_projection(
        snapshot=snapshot,
        collector_path=collector_path,
        score_root=score_root,
        normalized_root=normalized_root,
        materialization_root=materialization_root,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    if between_phases is not None:
        between_phases(snapshot)
    snapshot.verify_unchanged()
    metrics = projection["metrics"]
    optimization = run_optuna(metrics)
    snapshot.verify_unchanged()
    dspy_view = build_dspy_training_view(
        metrics=metrics,
        optimization=optimization,
        snapshot=snapshot,
        normalized_root=normalized_root,
        materialization_root=materialization_root,
    )
    snapshot.verify_unchanged()
    _contract, contract_file_sha256 = load_contract()
    result: dict[str, Any] = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "development_only_regularized_nextwave_analysis",
        "source": {
            "scorer_commit": "6cfd64e8db03b06c70d39d79ca4aac24ba498232",
            "scorer_executor_sha256": EXPECTED["scorer_executor_sha256"],
            "collector_sha256": EXPECTED["collector_sha256"],
            "schedule_file_sha256": EXPECTED["schedule_sha256"],
            "recomputed_projection_sha256": projection["result_sha256"],
            "normalized_source_manifest_sha256": EXPECTED["normalized_source_manifest_sha256"],
            "winner_artifact_sha256": EXPECTED["winner_artifact_sha256"],
            "frozen_successor_sha256": EXPECTED["frozen_successor_sha256"],
            "hanna_csv_sha256": EXPECTED["hanna_csv_sha256"],
            "study_contract_file_sha256": contract_file_sha256,
            "admitted_source_snapshot_sha256": snapshot_sha256,
        },
        "geometry": {
            "endpoint": "grok-4.6-build",
            "candidates": 11,
            "development_prompt_groups": 3,
            "cells": 33,
            "confirmation_cells": 0,
        },
        "optimizer": optimization,
        "dspy_training_view": dspy_view,
        "finding": {
            "candidate08_remains_preferred_across_low_penalty_grid": True,
            "candidate_id": WINNER,
            "settings_won": optimization["candidate08_wins"],
            "settings_tested": optimization["setting_count"],
            "development_only_grok_equal_group_mae": optimization["unregularized"]["winner_equal_group_mae"],
            "baseline_equal_group_mae": optimization["unregularized"]["baseline_equal_group_mae"],
            "absolute_mae_reduction": optimization["unregularized"]["absolute_mae_reduction"],
            "relative_mae_reduction": optimization["unregularized"]["relative_mae_reduction"],
        },
        "next_geometry": {
            "immediate_sol_checkpoint": {
                "candidates": [BASELINE, WINNER],
                "same_frozen_development_groups": 3,
                "sol_cells": 6,
                "payload_rule": "candidate prompt/profile and item payload bytes unchanged from the Grok score",
                "purpose": "directional endpoint validation only; no pooling or general claim",
            },
            "broader_grok_iteration_after_checkpoint": {
                "candidate08_control": 1,
                "small_step_descendants": 4,
                "requested_step_fraction": 0.05,
                "frozen_development_prompt_groups": 7,
                "one_prechosen_item_per_group": True,
                "grok_cells": 35,
                "confirmation_cells": 0,
            },
            "sprinkled_sol_after_broader_grok_screen": {
                "candidates": [BASELINE, WINNER, "broader_grok_development_winner"],
                "frozen_development_prompt_groups": 7,
                "sol_cells": 21,
                "substitution": "forbidden",
            },
        },
        "authority": {
            "selection": "development_only_provisional",
            "confirmation": {"status": "unopened", "cells": 0},
            "sol_validation": "not_yet_run_for_candidate08",
            "general_hanna": "none",
            "promotion": "none",
            "runtime": "none",
            "native_endpoint_contact_cardinality": "unproven",
        },
        "claim": "Empirical only for the frozen 33-cell Grok development projection; Optuna regularization and DSPy data preparation add no held-out, Sol, general, promotion, or runtime authority.",
    }
    assert_public(result)
    result["result_sha256"] = sha256(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector", type=Path, required=True)
    parser.add_argument("--score-root", type=Path, required=True)
    parser.add_argument("--normalized-root", type=Path, required=True)
    parser.add_argument("--materialization-root", type=Path, required=True)
    parser.add_argument("--frozen-successor", type=Path, required=True)
    parser.add_argument("--hanna-csv", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(
        collector_path=args.collector,
        score_root=args.score_root,
        normalized_root=args.normalized_root,
        materialization_root=args.materialization_root,
        frozen_successor_path=args.frozen_successor,
        hanna_csv_path=args.hanna_csv,
    )
    print(canonical(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
