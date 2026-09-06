"""Frozen TRAIN-only domain-weight fitting for Dryad full-HBQ analysis.

This module accepts already admitted verdicts and already prepared targets.  It
does not load targets, contact a provider, judge prose, fit DEV, or promote a
profile into runtime use.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence
import uuid

import optuna


ANALYSIS_ROOT = Path(__file__).resolve().parent
ROOT = ANALYSIS_ROOT.parents[1]
PROTOCOL_PATH = ANALYSIS_ROOT / "protocol-v2.json"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
ANALYSIS_MATH_PATH = ANALYSIS_ROOT / "analysis_math.py"
ANALYSIS_MATH_SHA256 = "237c6ff2fb9c343b7a7000fdbbe17ad76db29afde1164a4fa7f0affa0963b41f"
NATIVE_ADMISSION_PATH = ANALYSIS_ROOT / "native_admission.py"
NATIVE_ADMISSION_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
DOMAIN_ORDER = ("task", "character", "movement", "language", "setting", "effect", "fresh", "mechanics", "holistic")
CANONICAL_POINTS = (8, 15, 19, 16, 9, 10, 10, 5, 8)
MULTIPLIERS = (0.5, 1.0, 2.0)
TRAIN_COUNT = 176
QUESTION_COUNT = 178
CANONICAL_VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}


class OptimizationAborted(RuntimeError):
    """A failed trial stops this fixed fitting campaign without replacement."""

    def __init__(self, message: str, attempted_trials: Sequence[dict[str, Any]]) -> None:
        super().__init__(message)
        self.attempted_trials = list(attempted_trials)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _read_pinned(path: Path, expected: str, label: str) -> bytes:
    raw = path.read_bytes()
    if _sha(raw) != expected:
        raise ValueError(f"{label} hash drift")
    return raw


def _load_raw_module(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_optimizer_{label}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def _capture() -> tuple[dict[str, bytes], dict[str, Any], ModuleType, ModuleType]:
    protocol_raw = _read_pinned(PROTOCOL_PATH, PROTOCOL_SHA256, "Protocol")
    try:
        protocol = json.loads(protocol_raw)
    except json.JSONDecodeError as error:
        raise ValueError("Protocol is not JSON") from error
    if protocol.get("optimization", {}).get("domain_order") != list(DOMAIN_ORDER) or protocol["optimization"].get("canonical_points") != list(CANONICAL_POINTS) or protocol["optimization"].get("multipliers") != list(MULTIPLIERS):
        raise ValueError("Frozen optimization geometry drift")
    if protocol["optimization"].get("trials_total_including_baseline") != 128 or protocol["optimization"].get("seed") != 20260905 or protocol["optimization"].get("parallel_jobs") != 1:
        raise ValueError("Frozen Optuna schedule drift")
    if protocol["optimization"].get("sampler_settings") != {"n_startup_trials": 10, "n_ei_candidates": 24, "multivariate": False, "group": False, "constant_liar": False}:
        raise ValueError("Frozen sampler settings drift")
    math_raw = _read_pinned(ANALYSIS_MATH_PATH, ANALYSIS_MATH_SHA256, "Analysis math")
    native_raw = _read_pinned(NATIVE_ADMISSION_PATH, NATIVE_ADMISSION_SHA256, "Native admission")
    return {PROTOCOL_PATH: protocol_raw, ANALYSIS_MATH_PATH: math_raw, NATIVE_ADMISSION_PATH: native_raw}, protocol, _load_raw_module(ANALYSIS_MATH_PATH, math_raw, "math"), _load_raw_module(NATIVE_ADMISSION_PATH, native_raw, "native")


def _assert_unchanged(captures: dict[Path, bytes], runtime: Any) -> None:
    if any(path.read_bytes() != raw for path, raw in captures.items()):
        raise ValueError("Pinned optimizer source changed during fitting")
    verify = getattr(runtime, "verify", None)
    if not callable(verify):
        raise ValueError("Runtime lacks a pinned postcheck")
    verify()


def _runtime(runtime: Any, native: ModuleType) -> tuple[Any, str]:
    if runtime is None:
        return native.load_runtime(), "pinned_native_load_runtime"
    return runtime, "caller_supplied_test_runtime_no_authority"


def _question_ids(runtime: Any) -> tuple[str, ...]:
    questions = getattr(runtime, "questions", None)
    if not isinstance(questions, list) or len(questions) != QUESTION_COUNT:
        raise ValueError("Runtime does not expose the frozen 178-question inventory")
    try:
        ids = tuple(question["question"]["id"] for question in questions)
    except (KeyError, TypeError) as error:
        raise ValueError("Runtime question inventory is malformed") from error
    if any(type(question_id) is not str or not question_id for question_id in ids) or len(set(ids)) != QUESTION_COUNT:
        raise ValueError("Runtime question inventory is not unique")
    if getattr(runtime, "core", None) is None or getattr(runtime.core, "VERDICTS", None) != CANONICAL_VERDICTS:
        raise ValueError("Runtime canonical verdict states drift")
    if getattr(runtime, "bundle", {}).get("bundle_id") != "prose.short_story":
        raise ValueError("Runtime bundle drift")
    domains = tuple((domain.get("domain_id"), domain.get("points")) for domain in runtime.bundle.get("domains", []))
    if tuple(domain_id for domain_id, _ in domains) != DOMAIN_ORDER or tuple(float(points) for _, points in domains) != tuple(float(point) for point in CANONICAL_POINTS):
        raise ValueError("Runtime domain geometry drift")
    return ids


def _verdict_rows(rows: Sequence[dict[str, Any]], question_ids: tuple[str, ...]) -> dict[str, list[dict[str, str]]]:
    if not isinstance(rows, list) or len(rows) != TRAIN_COUNT:
        raise ValueError("verdict_rows must contain exactly 176 TRAIN stories")
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"opaque_story_id", "verdicts"}:
            raise ValueError("Each verdict row must contain only opaque_story_id and verdicts")
        story, verdicts = row["opaque_story_id"], row["verdicts"]
        if type(story) is not str or not story or story in result or not isinstance(verdicts, list) or len(verdicts) != QUESTION_COUNT:
            raise ValueError("Verdict story identity or inventory is invalid")
        checked: list[dict[str, str]] = []
        for expected, verdict in zip(question_ids, verdicts):
            if not isinstance(verdict, dict) or set(verdict) != {"question_id", "verdict"} or verdict.get("question_id") != expected or type(verdict.get("verdict")) is not str or verdict["verdict"] not in CANONICAL_VERDICTS:
                raise ValueError("Verdicts must exactly match ordered four-state native outcomes")
            checked.append({"question_id": expected, "verdict": verdict["verdict"]})
        result[story] = checked
    return result


def _profile(vector: tuple[float, ...]) -> dict[str, Any]:
    suffix = "-".join(str(value).replace(".", "p") for value in vector)
    return {
        "profile_version": 1,
        "profile_id": f"dryad-train-{suffix}",
        "bundle_id": "prose.short_story",
        "domain_weights": [
            {"domain_id": domain_id, "weight": point * multiplier}
            for domain_id, point, multiplier in zip(DOMAIN_ORDER, CANONICAL_POINTS, vector)
        ],
    }


def _score_trial(runtime: Any, analysis: ModuleType, verdicts: dict[str, list[dict[str, str]]], target_rows: list[dict[str, Any]], vector: tuple[float, ...], trial_number: int) -> dict[str, Any]:
    profile = _profile(vector)
    modules, bundle, audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, profile)
    expected_points = tuple(float(point) for point in CANONICAL_POINTS)
    effective_points = tuple(float(domain["points"]) for domain in bundle["domains"])
    canonical_equivalent = vector == (1.0,) * len(DOMAIN_ORDER) and effective_points == expected_points
    if tuple(domain["domain_id"] for domain in bundle["domains"]) != DOMAIN_ORDER:
        raise ValueError("Materialized domain order drift")
    scores: list[dict[str, Any]] = []
    score_hashes: dict[str, str] = {}
    for story in sorted(verdicts):
        score = runtime.core.score_bundle(modules, bundle, verdicts[story], artifact_id=story, task_contract=None)
        observed, coverage = score.get("final_score", {}).get("observed"), score.get("coverage")
        if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed) or not 0 <= observed <= 100 or isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not math.isfinite(coverage) or coverage < 0.88:
            raise ValueError(f"Trial {trial_number} produced an invalid native score")
        scores.append({"opaque_story_id": story, "score": observed, "coverage": coverage})
        score_hashes[story] = _sha(_canonical(score))
    analysis_result = analysis.analyze_scores(scores, target_rows)
    primary = analysis_result["co_primary"]
    objective = (primary["novelty"]["rho"] + primary["usefulness"]["rho"]) / 2
    if not math.isfinite(objective):
        raise ValueError(f"Trial {trial_number} has an undefined objective")
    return {
        "trial_number": trial_number,
        "multipliers": list(vector),
        "profile": profile,
        "profile_audit": audit,
        "canonical_points_reproduced": canonical_equivalent,
        "score_hashes": score_hashes,
        "score_rows_sha256": _sha(_canonical(scores)),
        "analysis": analysis_result,
        "objective": objective,
    }


def _winner(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def key(record: dict[str, Any]) -> tuple[float, float, tuple[float, ...], int]:
        vector = tuple(record["multipliers"])
        return (-record["objective"], sum(abs(math.log2(value)) for value in vector), vector, record["trial_number"])
    return min(records, key=key)


def _identity(protocol: dict[str, Any], captures: dict[Path, bytes], runtime_source: str) -> dict[str, Any]:
    return {
        "evidence_class": "development_fit_only" if runtime_source == "pinned_native_load_runtime" else "synthetic_fit_no_authority",
        "optimizer_sha256": _sha(captures[Path(__file__).resolve()]),
        "protocol_sha256": PROTOCOL_SHA256,
        "analysis_math": {"path": ANALYSIS_MATH_PATH.relative_to(ROOT).as_posix(), "sha256": _sha(captures[ANALYSIS_MATH_PATH])},
        "native_admission": {"path": NATIVE_ADMISSION_PATH.relative_to(ROOT).as_posix(), "sha256": _sha(captures[NATIVE_ADMISSION_PATH])},
        "runtime_source": runtime_source,
        "runtime_pins": {"runtime_bindings": protocol["runtime_bindings"], "shared_runtime_bindings": protocol["shared_runtime_bindings"]},
    }


def fit_train(verdict_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], *, expected_optimizer_sha256: str, runtime: Any = None) -> dict[str, Any]:
    """Fit exactly 128 TRAIN-only profiles from frozen four-state verdict rows."""
    own_path = Path(__file__).resolve()
    own_raw = _read_pinned(own_path, expected_optimizer_sha256, "Reviewed optimizer")
    captures, protocol, analysis, native = _capture()
    captures[own_path] = own_raw
    if optuna.__version__ != protocol["optimization"]["optuna_version"]:
        raise ValueError("Optuna version differs from the frozen protocol")
    loaded_runtime, runtime_source = _runtime(runtime, native)
    records: list[dict[str, Any]] = []
    try:
        _assert_unchanged(captures, loaded_runtime)
        question_ids = _question_ids(loaded_runtime)
        verdicts = _verdict_rows(verdict_rows, question_ids)
        partition, targets = analysis._targets(target_rows)
        if partition != "TRAIN" or len(targets) != TRAIN_COUNT or set(verdicts) != {story for story, _ in targets}:
            raise ValueError("Fitting requires exactly matching unique TRAIN verdicts and targets")
        target_raw = _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"]))
        verdict_raw = _canonical([{ "opaque_story_id": story, "verdicts": verdicts[story]} for story in sorted(verdicts)])
        sampler = optuna.samplers.TPESampler(seed=20260905, n_startup_trials=10, n_ei_candidates=24, multivariate=False, group=False, constant_liar=False)
        study = optuna.create_study(direction="maximize", sampler=sampler)
        baseline = {domain: 1.0 for domain in DOMAIN_ORDER}
        study.enqueue_trial(baseline, skip_if_exists=False)

        def objective(trial: optuna.Trial) -> float:
            vector = []
            try:
                for domain in DOMAIN_ORDER:
                    vector.append(float(trial.suggest_categorical(domain, MULTIPLIERS)))
                record = _score_trial(loaded_runtime, analysis, verdicts, target_rows, tuple(vector), trial.number)
            except Exception as error:
                records.append({"trial_number": trial.number, "multipliers": list(vector), "state": "failed", "error": f"{type(error).__name__}: {error}"})
                raise
            records.append(record)
            return record["objective"]

        prior_verbosity = optuna.logging.get_verbosity()
        try:
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            study.optimize(objective, n_trials=128, n_jobs=1, catch=())
        except Exception as error:
            raise OptimizationAborted("Frozen TRAIN optimization aborted; no replacement trial was run", records) from error
        finally:
            optuna.logging.set_verbosity(prior_verbosity)
        if len(records) != 128 or records[0]["trial_number"] != 0 or records[0]["multipliers"] != [1.0] * len(DOMAIN_ORDER) or any(record.get("state") == "failed" for record in records):
            raise OptimizationAborted("Frozen TRAIN trial inventory drift", records)
        stored = {trial.number: trial.value for trial in study.trials}
        if len(stored) != 128 or any(stored.get(record["trial_number"]) != record["objective"] for record in records):
            raise OptimizationAborted("Optuna trial records differ from the frozen arithmetic", records)
        for record in records:
            replayed = _score_trial(loaded_runtime, analysis, verdicts, target_rows, tuple(record["multipliers"]), record["trial_number"])
            if _canonical(replayed) != _canonical(record):
                raise OptimizationAborted("Independent frozen-leaf trial recomputation differs", records)
            record["independent_recompute_match"] = True
        winner = _winner(records)
        if _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"])) != target_raw:
            raise OptimizationAborted("Frozen targets changed during fitting", records)
        identity = _identity(protocol, captures, runtime_source)
        result = {"evidence_class": identity["evidence_class"], "identity": identity,
                  "input_commitments": {"verdict_rows_sha256": _sha(verdict_raw), "target_rows_sha256": _sha(target_raw)},
                  "trial_count": len(records), "trial_records": records, "winner": winner}
        _assert_unchanged(captures, loaded_runtime)
        return result
    except Exception as error:
        failure = error if isinstance(error, OptimizationAborted) or not records else OptimizationAborted("Frozen TRAIN fitting or replay failed", records)
        try:
            _assert_unchanged(captures, loaded_runtime)
        except Exception as postcheck_error:
            failure.postcheck_failure = type(postcheck_error).__name__
            failure.add_note("Pinned source/runtime postcheck also failed")
        if failure is error:
            raise
        raise failure from error
