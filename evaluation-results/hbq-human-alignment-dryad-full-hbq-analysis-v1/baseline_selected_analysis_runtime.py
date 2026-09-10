"""Selected 70-TRAIN/30-DEV adapter over the separately pinned frozen engines."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
PROTOCOL_PATH = ROOT / "protocol-v2.json"
OPTIMIZER_PATH = ROOT / "optimizer.py"
ANALYSIS_MATH_PATH = ROOT / "analysis_math.py"
COMPARISON_PATH = ROOT / "dev_comparison.py"
NATIVE_ADMISSION_PATH = ROOT / "native_admission.py"

PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
OPTIMIZER_SHA256 = "304020d4c7d40b1ca09be88d1eafbcc6b392c05717dda184f12faf845000a378"
ANALYSIS_MATH_SHA256 = "237c6ff2fb9c343b7a7000fdbbe17ad76db29afde1164a4fa7f0affa0963b41f"
COMPARISON_SHA256 = "98639fc917e51809cfc60b6f553f3ad9623df9f1b24c524bf44c817b87991291"
NATIVE_ADMISSION_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
BASELINE_RUNTIME_SOURCE = "source_verified_baseline_runtime"
TRAIN_COUNT = 70
DEV_COUNT = 30
QUESTION_COUNT = 178
TRIAL_COUNT = 128
_HASH_CHARACTERS = frozenset("0123456789abcdef")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in _HASH_CHARACTERS for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _read(path: Path, expected: str, label: str) -> bytes:
    raw = path.read_bytes()
    if _sha(raw) != _digest(expected, label + " hash"):
        raise ValueError(f"{label} hash drift")
    return raw


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_selected100_{label}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact locally pinned source only.
    return module


def _strict_json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"{label} has duplicate keys")
            value[key] = item
        return value

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error


def _selection(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "selected_schedule_sha256", "selected_schedule_source_sha256", "TRAIN", "DEV",
    } or value.get("schema_version") != 1:
        raise ValueError("Selected identity binding schema differs")
    selected = {
        "schema_version": 1,
        "selected_schedule_sha256": _digest(value.get("selected_schedule_sha256"), "Selected schedule"),
        "selected_schedule_source_sha256": _digest(value.get("selected_schedule_source_sha256"), "Selected schedule source"),
    }
    for partition, count in (("TRAIN", TRAIN_COUNT), ("DEV", DEV_COUNT)):
        rows = value.get(partition)
        if not isinstance(rows, list) or len(rows) != count or rows != sorted(rows):
            raise ValueError(f"Selected {partition} identity inventory differs")
        if any(type(item) is not str or not item for item in rows) or len(set(rows)) != count:
            raise ValueError(f"Selected {partition} identity inventory differs")
        selected[partition] = list(rows)
    if set(selected["TRAIN"]) & set(selected["DEV"]):
        raise ValueError("Selected TRAIN and DEV identities overlap")
    return selected


def _capture(expected_successor_sha256: str) -> tuple[dict[Path, bytes], dict[str, Any], ModuleType, ModuleType, ModuleType, ModuleType]:
    own_path = Path(__file__).resolve()
    captures = {
        own_path: _read(own_path, expected_successor_sha256, "Selected adapter"),
        PROTOCOL_PATH: _read(PROTOCOL_PATH, PROTOCOL_SHA256, "Protocol"),
        OPTIMIZER_PATH: _read(OPTIMIZER_PATH, OPTIMIZER_SHA256, "Optimizer"),
        ANALYSIS_MATH_PATH: _read(ANALYSIS_MATH_PATH, ANALYSIS_MATH_SHA256, "Analysis math"),
        COMPARISON_PATH: _read(COMPARISON_PATH, COMPARISON_SHA256, "DEV comparison"),
        NATIVE_ADMISSION_PATH: _read(NATIVE_ADMISSION_PATH, NATIVE_ADMISSION_SHA256, "Native admission"),
    }
    protocol = _strict_json(captures[PROTOCOL_PATH], "Protocol")
    if not isinstance(protocol, dict):
        raise ValueError("Protocol schema differs")  # noqa: TRY004 - malformed pinned protocol is a contract error.
    optimizer = _load(OPTIMIZER_PATH, captures[OPTIMIZER_PATH], "optimizer")
    analysis = _load(ANALYSIS_MATH_PATH, captures[ANALYSIS_MATH_PATH], "analysis_math")
    comparison = _load(COMPARISON_PATH, captures[COMPARISON_PATH], "dev_comparison")
    native = _load(NATIVE_ADMISSION_PATH, captures[NATIVE_ADMISSION_PATH], "native_admission")
    if (optimizer.PROTOCOL_SHA256 != PROTOCOL_SHA256 or optimizer.ANALYSIS_MATH_SHA256 != ANALYSIS_MATH_SHA256
            or comparison.OPTIMIZER_SHA256 != OPTIMIZER_SHA256 or comparison.ANALYSIS_MATH_SHA256 != ANALYSIS_MATH_SHA256
            or analysis.PROTOCOL_SHA256 != PROTOCOL_SHA256):
        raise ValueError("Frozen engine source pins differ")
    return captures, protocol, optimizer, analysis, comparison, native


def _override(analysis: ModuleType, optimizer: ModuleType, comparison: ModuleType) -> list[dict[str, Any]]:
    changes = (
        (analysis, "DEV_COUNT", 60, DEV_COUNT, "analysis_math.py", "analysis_math._bootstrap"),
        (optimizer, "TRAIN_COUNT", 176, TRAIN_COUNT, "optimizer.py", "optimizer train verdict and replay helpers"),
        (comparison, "DEV_COUNT", 60, DEV_COUNT, "dev_comparison.py", "dev_comparison._verdicts"),
    )
    records: list[dict[str, Any]] = []
    for module, name, original, replacement, source, consumer in changes:
        if getattr(module, name, None) != original:
            raise ValueError(f"Frozen {source} {name} differs before selected override")
        setattr(module, name, replacement)
        records.append({"source": source, "consumer": consumer, "global": name,
                        "original": original, "replacement": replacement})
    return records


def _postcheck(captures: Mapping[Path, bytes], runtime: Any) -> None:
    if any(path.read_bytes() != raw for path, raw in captures.items()):
        raise ValueError("Pinned selected-analysis source changed during execution")
    verify = getattr(runtime, "verify", None)
    if not callable(verify):
        raise ValueError("Runtime lacks a pinned postcheck")  # noqa: TRY004 - missing runtime capability is a contract error.
    verify()


def _runtime(optimizer: ModuleType, native: ModuleType, runtime: Any, *, baseline_manifest_path: Path | str | None,
             baseline_manifest_sha256: str | None) -> tuple[Any, str, dict[str, Any] | None, dict[Path, bytes]]:
    return optimizer._runtime(runtime, native, baseline_manifest_path=baseline_manifest_path,
                              baseline_manifest_sha256=baseline_manifest_sha256)


def _target_rows(analysis: ModuleType, rows: Sequence[dict[str, Any]], partition: str,
                 selected_ids: set[str]) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(rows, list) or len(rows) != len(selected_ids):
        raise ValueError(f"Selected {partition} target count differs")
    result: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    axes = set(analysis.AXES)
    primary = set(analysis.CO_PRIMARY)
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"opaque_story_id", "partition", "rating_count", "axis_means", "indices"}:
            raise ValueError("Selected target schema differs")
        story, current_partition, rating_count = row["opaque_story_id"], row["partition"], row["rating_count"]
        if (type(story) is not str or not story or story in seen or current_partition != partition
                or type(rating_count) is not int or rating_count < 1):
            raise ValueError("Selected target identity or partition differs")
        axis_means, indices = row["axis_means"], row["indices"]
        if not isinstance(axis_means, dict) or set(axis_means) != axes or not isinstance(indices, dict) or set(indices) != primary:
            raise ValueError("Selected target dimensions differ")
        values = {name: analysis._fraction(axis_means[name], f"axis_means.{name}") for name in analysis.AXES}
        values.update({name: analysis._fraction(indices[name], f"indices.{name}") for name in analysis.CO_PRIMARY})
        if any(not 1 <= item <= 9 for item in values.values()):
            raise ValueError("Selected target value is outside the source rating scale")
        seen.add(story)
        result.append((story, values))
    if seen != selected_ids:
        raise ValueError(f"Selected {partition} target IDs differ from the identity binding")
    return sorted(result)


def _analysis(analysis: ModuleType, partition: str, score_rows: list[dict[str, Any]],
              targets: list[tuple[str, dict[str, Any]]]) -> tuple[dict[str, Any], list[tuple[str, Any, dict[str, Any]]]]:
    scores = analysis._scores(score_rows)
    if set(scores) != {story for story, _ in targets}:
        raise ValueError("Selected score and target IDs differ")
    aligned = [(story, scores[story], values) for story, values in targets]
    result = analysis._analysis(partition, aligned)
    result["protocol_predecessor_sha256"] = PROTOCOL_SHA256
    return result, aligned


def _identity(stage: str, captures: Mapping[Path, bytes], runtime_source: str,
              runtime_binding: dict[str, Any] | None, selection: Mapping[str, Any],
              overrides: list[dict[str, Any]]) -> dict[str, Any]:
    if runtime_source == BASELINE_RUNTIME_SOURCE:
        if runtime_binding is None:
            raise ValueError("Source-verified runtime binding is missing")
        runtime_pins: Any = runtime_binding
    else:
        if runtime_binding is not None:
            raise ValueError("Only source-verified runtime may carry a runtime binding")
        runtime_pins = {"runtime_bindings": _strict_json(captures[PROTOCOL_PATH], "Protocol")["runtime_bindings"],
                        "shared_runtime_bindings": _strict_json(captures[PROTOCOL_PATH], "Protocol")["shared_runtime_bindings"]}
    return {
        "adapter_sha256": _sha(captures[Path(__file__).resolve()]),
        "stage": stage,
        "sources": {
            "adapter_sha256": _sha(captures[Path(__file__).resolve()]),
            "optimizer_sha256": OPTIMIZER_SHA256,
            "analysis_math_sha256": ANALYSIS_MATH_SHA256,
            "dev_comparison_sha256": COMPARISON_SHA256,
            "native_admission_sha256": NATIVE_ADMISSION_SHA256,
        },
        "protocol_predecessor": {"sha256": PROTOCOL_SHA256, "role": "frozen_predecessor_math_contract_only"},
        "runtime_source": runtime_source,
        "runtime_pins": runtime_pins,
        "selection_binding": dict(selection),
        "selected_count": TRAIN_COUNT if stage == "fit" else DEV_COUNT,
        "overrides": overrides,
    }


def _evidence_class(stage: str, runtime_source: str) -> str:
    if runtime_source == "caller_supplied_test_runtime_no_authority":
        return f"selected100_synthetic_{stage}_no_authority"
    return "selected100_amended_fit_unadmitted" if stage == "fit" else "selected100_amended_dev_comparison_unadmitted"


def _train_trial(optimizer: ModuleType, analysis: ModuleType, runtime: Any,
                 verdicts: Mapping[str, list[dict[str, str]]], targets: list[tuple[str, dict[str, Any]]],
                 vector: tuple[float, ...], trial_number: int) -> dict[str, Any]:
    profile = optimizer._profile(vector)
    modules, bundle, audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, profile)
    expected_points = tuple(float(point) for point in optimizer.CANONICAL_POINTS)
    effective_points = tuple(float(domain["points"]) for domain in bundle["domains"])
    if tuple(domain.get("domain_id") for domain in bundle.get("domains", [])) != optimizer.DOMAIN_ORDER:
        raise ValueError("Materialized domain order drift")
    scores: list[dict[str, Any]] = []
    score_hashes: dict[str, str] = {}
    for story in sorted(verdicts):
        score = runtime.core.score_bundle(modules, bundle, verdicts[story], artifact_id=story, task_contract=None)
        observed, coverage = score.get("final_score", {}).get("observed"), score.get("coverage")
        if (isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed)
                or not 0 <= observed <= 100 or isinstance(coverage, bool) or not isinstance(coverage, (int, float))
                or not math.isfinite(coverage) or coverage < 0.88):
            raise ValueError(f"Trial {trial_number} produced an invalid native score")
        scores.append({"opaque_story_id": story, "score": observed, "coverage": coverage})
        score_hashes[story] = _sha(_canonical(score))
    analysis_result, _ = _analysis(analysis, "TRAIN", scores, targets)
    primary = analysis_result["co_primary"]
    objective = sum(primary[name]["rho"] for name in analysis.CO_PRIMARY) / len(analysis.CO_PRIMARY)
    if not math.isfinite(objective):
        raise ValueError(f"Trial {trial_number} has an undefined objective")
    return {
        "trial_number": trial_number,
        "multipliers": list(vector),
        "profile": profile,
        "profile_audit": audit,
        "canonical_points_reproduced": vector == (1.0,) * len(optimizer.DOMAIN_ORDER) and effective_points == expected_points,
        "score_hashes": score_hashes,
        "score_rows_sha256": _sha(_canonical(scores)),
        "analysis": analysis_result,
        "objective": objective,
    }


def fit_train(verdict_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], *,
              selection_binding: Mapping[str, Any], expected_successor_sha256: str, runtime: Any = None,
              baseline_manifest_path: Path | str | None = None,
              baseline_manifest_sha256: str | None = None) -> dict[str, Any]:
    """Run the fixed 128-trial, selected-70 TRAIN fit without provider authority."""
    selection = _selection(selection_binding)
    captures, protocol, optimizer, analysis, comparison, native = _capture(expected_successor_sha256)
    overrides = _override(analysis, optimizer, comparison)
    if (protocol.get("optimization", {}).get("trials_total_including_baseline") != TRIAL_COUNT
            or protocol["optimization"].get("seed") != 20260905
            or protocol["optimization"].get("parallel_jobs") != 1
            or protocol["optimization"].get("sampler_settings") != {
                "n_startup_trials": 10, "n_ei_candidates": 24, "multivariate": False, "group": False,
                "constant_liar": False,
            } or optimizer.optuna.__version__ != protocol["optimization"].get("optuna_version")):
        raise ValueError("Frozen optimization settings drift")
    loaded_runtime, runtime_source, runtime_binding, runtime_captures = _runtime(
        optimizer, native, runtime, baseline_manifest_path=baseline_manifest_path,
        baseline_manifest_sha256=baseline_manifest_sha256)
    captures.update(runtime_captures)
    records: list[dict[str, Any]] = []
    try:
        _postcheck(captures, loaded_runtime)
        question_ids = optimizer._question_ids(loaded_runtime)
        verdicts = optimizer._verdict_rows(verdict_rows, question_ids)
        targets = _target_rows(analysis, target_rows, "TRAIN", set(selection["TRAIN"]))
        if set(verdicts) != set(selection["TRAIN"]):
            raise ValueError("Selected TRAIN verdict IDs differ from the identity binding")
        verdict_raw = _canonical(sorted(verdict_rows, key=lambda row: row["opaque_story_id"]))
        target_raw = _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"]))
        sampler = optimizer.optuna.samplers.TPESampler(
            seed=20260905, n_startup_trials=10, n_ei_candidates=24, multivariate=False, group=False,
            constant_liar=False)
        study = optimizer.optuna.create_study(direction="maximize", sampler=sampler)
        study.enqueue_trial({domain: 1.0 for domain in optimizer.DOMAIN_ORDER}, skip_if_exists=False)

        def objective(trial: Any) -> float:
            vector: list[float] = []
            try:
                for domain in optimizer.DOMAIN_ORDER:
                    vector.append(float(trial.suggest_categorical(domain, optimizer.MULTIPLIERS)))
                record = _train_trial(optimizer, analysis, loaded_runtime, verdicts, targets, tuple(vector), trial.number)
            except Exception as error:
                records.append({"trial_number": trial.number, "multipliers": vector, "state": "failed",
                                "error": f"{type(error).__name__}: {error}"})
                raise
            records.append(record)
            return record["objective"]

        verbosity = optimizer.optuna.logging.get_verbosity()
        try:
            optimizer.optuna.logging.set_verbosity(optimizer.optuna.logging.WARNING)
            study.optimize(objective, n_trials=TRIAL_COUNT, n_jobs=1, catch=())
        except Exception as error:
            raise optimizer.OptimizationAborted("Selected100 TRAIN optimization aborted; no replacement trial was run", records) from error
        finally:
            optimizer.optuna.logging.set_verbosity(verbosity)
        if (len(records) != TRIAL_COUNT or records[0].get("trial_number") != 0
                or records[0].get("multipliers") != [1.0] * len(optimizer.DOMAIN_ORDER)
                or any(record.get("state") == "failed" for record in records)):
            raise optimizer.OptimizationAborted("Selected100 TRAIN trial inventory drift", records)
        stored = {trial.number: trial.value for trial in study.trials}
        if len(stored) != TRIAL_COUNT or any(stored.get(record["trial_number"]) != record["objective"] for record in records):
            raise optimizer.OptimizationAborted("Selected100 Optuna trial records differ", records)
        for record in records:
            replay = _train_trial(optimizer, analysis, loaded_runtime, verdicts, targets,
                                  tuple(record["multipliers"]), record["trial_number"])
            if _canonical(replay) != _canonical(record):
                raise optimizer.OptimizationAborted("Selected100 independent trial recomputation differs", records)
            record["independent_recompute_match"] = True
        winner = optimizer._winner(records)
        if (_canonical(sorted(verdict_rows, key=lambda row: row["opaque_story_id"])) != verdict_raw
                or _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"])) != target_raw):
            raise optimizer.OptimizationAborted("Selected100 TRAIN inputs changed during fitting", records)
        identity = _identity("fit", captures, runtime_source, runtime_binding, selection, overrides)
        result = {
            "evidence_class": _evidence_class("fit", runtime_source),
            "identity": identity,
            "input_commitments": {"verdict_rows_sha256": _sha(verdict_raw), "target_rows_sha256": _sha(target_raw)},
            "trial_count": len(records),
            "trial_records": records,
            "winner": winner,
        }
        _postcheck(captures, loaded_runtime)
        return result
    except Exception as error:
        failure = error if isinstance(error, optimizer.OptimizationAborted) or not records else optimizer.OptimizationAborted(
            "Selected100 TRAIN fitting or replay failed", records)
        try:
            _postcheck(captures, loaded_runtime)
        except Exception as postcheck_error:  # noqa: BLE001 - retain the fitting error and its attempted records.
            failure.add_note(f"Pinned source/runtime postcheck failed: {type(postcheck_error).__name__}")
        if failure is error:
            raise
        raise failure from error


def _fit(fit_raw: bytes, expected_fit_sha256: str, optimizer: ModuleType, analysis: ModuleType,
         expected_identity: Mapping[str, Any], selected_train: set[str], runtime_source: str) -> dict[str, Any]:
    if not isinstance(fit_raw, bytes) or _sha(fit_raw) != _digest(expected_fit_sha256, "Expected fit"):
        raise ValueError("Frozen selected100 fit hash differs from the external review anchor")
    fit = _strict_json(fit_raw, "Frozen selected100 fit")
    if not isinstance(fit, dict) or set(fit) != {
        "evidence_class", "identity", "input_commitments", "trial_count", "trial_records", "winner",
    }:
        raise ValueError("Frozen selected100 fit shape differs")
    if (fit["evidence_class"] != _evidence_class("fit", runtime_source)
            or fit["identity"] != dict(expected_identity)):
        raise ValueError("Frozen selected100 fit identity or authority classification differs")
    commitments = fit.get("input_commitments")
    if not isinstance(commitments, dict) or set(commitments) != {"verdict_rows_sha256", "target_rows_sha256"}:
        raise ValueError("Frozen selected100 fit input commitments differ")
    for value in commitments.values():
        _digest(value, "Frozen selected100 fit input commitment")
    records = fit.get("trial_records")
    if fit.get("trial_count") != TRIAL_COUNT or not isinstance(records, list) or len(records) != TRIAL_COUNT:
        raise ValueError("Frozen selected100 fit does not contain exactly 128 trials")
    if [record.get("trial_number") if isinstance(record, dict) else None for record in records] != list(range(TRIAL_COUNT)):
        raise ValueError("Frozen selected100 fit trial inventory differs")
    if records[0].get("multipliers") != [1.0] * len(optimizer.DOMAIN_ORDER):
        raise ValueError("Frozen selected100 fit trial zero is not the all-one baseline")
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "trial_number", "multipliers", "profile", "profile_audit", "canonical_points_reproduced",
            "score_hashes", "score_rows_sha256", "analysis", "objective", "independent_recompute_match",
        } or record["independent_recompute_match"] is not True:
            raise ValueError("Frozen selected100 trial replay record differs")
        vector = record["multipliers"]
        if (not isinstance(vector, list) or len(vector) != len(optimizer.DOMAIN_ORDER)
                or any(type(item) not in (int, float) or item not in optimizer.MULTIPLIERS for item in vector)
                or record["profile"] != optimizer._profile(tuple(vector))
                or record["canonical_points_reproduced"] is not (vector == [1.0] * len(optimizer.DOMAIN_ORDER))):
            raise ValueError("Frozen selected100 trial profile differs")
        score_hashes, summary = record.get("score_hashes"), record.get("analysis")
        if (not isinstance(score_hashes, dict) or set(score_hashes) != selected_train
                or not isinstance(summary, dict) or summary.get("partition") != "TRAIN"
                or summary.get("item_count") != TRAIN_COUNT or summary.get("protocol_predecessor_sha256") != PROTOCOL_SHA256
                or set(summary.get("co_primary", {})) != set(analysis.CO_PRIMARY)
                or set(summary.get("raw_axes", {})) != set(analysis.AXES)):
            raise ValueError("Frozen selected100 trial analysis differs")
        _digest(record.get("score_rows_sha256"), "Frozen selected100 trial score rows")
        if any(type(story) is not str or not story or _digest(value, "Frozen selected100 score hash") != value
               for story, value in score_hashes.items()):
            raise ValueError("Frozen selected100 trial score hashes differ")
        for metric in (*summary["co_primary"].values(), *summary["raw_axes"].values()):
            rho = metric.get("rho") if isinstance(metric, dict) else None
            if type(rho) not in (int, float) or not math.isfinite(rho) or not -1 <= rho <= 1:
                raise ValueError("Frozen selected100 trial correlation differs")
        expected_objective = sum(summary["co_primary"][name]["rho"] for name in analysis.CO_PRIMARY) / len(analysis.CO_PRIMARY)
        if type(record["objective"]) not in (int, float) or not math.isfinite(record["objective"]) or record["objective"] != expected_objective:
            raise ValueError("Frozen selected100 trial objective differs")
    if fit.get("winner") != optimizer._winner(records):
        raise ValueError("Frozen selected100 fit winner differs")
    return fit


def _comparison(analysis: ModuleType, baseline_scores: list[dict[str, Any]], candidate_scores: list[dict[str, Any]],
                targets: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    baseline_analysis, baseline = _analysis(analysis, "DEV", baseline_scores, targets)
    candidate_analysis, candidate = _analysis(analysis, "DEV", candidate_scores, targets)
    if len(baseline) != DEV_COUNT or [row[0] for row in baseline] != [row[0] for row in candidate]:
        raise ValueError("Selected DEV comparison requires matching 30-story score vectors")
    deltas = {
        name: candidate_analysis["co_primary"][name]["rho"] - baseline_analysis["co_primary"][name]["rho"]
        for name in analysis.CO_PRIMARY
    }
    mean_delta = sum(deltas.values()) / len(deltas)
    dev_rule = all(value >= 0 for value in deltas.values()) and mean_delta > 0
    bootstrap = analysis._bootstrap(baseline, candidate)
    bootstrap["gain_gate_passed"] = (
        dev_rule and bootstrap["undefined_replicates"] == 0
        and bootstrap["lower_bound_mean_co_primary_delta"] is not None
        and bootstrap["lower_bound_mean_co_primary_delta"] > 0
    )
    return {
        "baseline": baseline_analysis,
        "candidate": candidate_analysis,
        "co_primary_deltas": deltas,
        "mean_co_primary_delta": mean_delta,
        "dev_rule_passed": dev_rule,
        "bootstrap": bootstrap,
        "candidate_retained": dev_rule and bootstrap["gain_gate_passed"],
        "protocol_predecessor_sha256": PROTOCOL_SHA256,
    }


def validate_frozen_fit(fit_raw: bytes, *, expected_fit_sha256: str, selection_binding: Mapping[str, Any],
                        expected_successor_sha256: str, runtime: Any = None,
                        baseline_manifest_path: Path | str | None = None,
                        baseline_manifest_sha256: str | None = None) -> None:
    """Validate the complete frozen TRAIN fit before the caller opens DEV targets."""
    selection = _selection(selection_binding)
    captures, _protocol, optimizer, analysis, comparison, native = _capture(expected_successor_sha256)
    overrides = _override(analysis, optimizer, comparison)
    loaded_runtime, runtime_source, runtime_binding, runtime_captures = _runtime(
        optimizer, native, runtime, baseline_manifest_path=baseline_manifest_path,
        baseline_manifest_sha256=baseline_manifest_sha256)
    captures.update(runtime_captures)
    try:
        _postcheck(captures, loaded_runtime)
        identity = _identity("fit", captures, runtime_source, runtime_binding, selection, overrides)
        _fit(fit_raw, expected_fit_sha256, optimizer, analysis, identity, set(selection["TRAIN"]), runtime_source)
        _postcheck(captures, loaded_runtime)
    except Exception as error:
        try:
            _postcheck(captures, loaded_runtime)
        except Exception as postcheck_error:  # noqa: BLE001 - retain the fit validation error.
            error.add_note(f"Pinned source/runtime postcheck failed: {type(postcheck_error).__name__}")
        raise


def evaluate_dev(verdict_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], fit_raw: bytes, *,
                 expected_fit_sha256: str, selection_binding: Mapping[str, Any], expected_successor_sha256: str,
                 runtime: Any = None, baseline_manifest_path: Path | str | None = None,
                 baseline_manifest_sha256: str | None = None) -> dict[str, Any]:
    """Score the selected DEV set against the frozen selected100 TRAIN winner."""
    selection = _selection(selection_binding)
    captures, _protocol, optimizer, analysis, comparison, native = _capture(expected_successor_sha256)
    overrides = _override(analysis, optimizer, comparison)
    loaded_runtime, runtime_source, runtime_binding, runtime_captures = _runtime(
        optimizer, native, runtime, baseline_manifest_path=baseline_manifest_path,
        baseline_manifest_sha256=baseline_manifest_sha256)
    captures.update(runtime_captures)
    try:
        _postcheck(captures, loaded_runtime)
        identity = _identity("fit", captures, runtime_source, runtime_binding, selection, overrides)
        fit = _fit(fit_raw, expected_fit_sha256, optimizer, analysis, identity, set(selection["TRAIN"]), runtime_source)
        question_ids = optimizer._question_ids(loaded_runtime)
        verdicts = comparison._verdicts(verdict_rows, question_ids)
        targets = _target_rows(analysis, target_rows, "DEV", set(selection["DEV"]))
        if set(verdicts) != set(selection["DEV"]):
            raise ValueError("Selected DEV verdict IDs differ from the identity binding")
        if set(verdicts) & set(selection["TRAIN"]):
            raise ValueError("Selected DEV verdict IDs overlap selected TRAIN")
        verdict_raw = _canonical(sorted(verdict_rows, key=lambda row: row["opaque_story_id"]))
        target_raw = _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"]))
        baseline_modules, baseline_bundle, baseline_audit = loaded_runtime.weights.materialize_weight_profile(
            loaded_runtime.modules, loaded_runtime.bundle, None)
        vector = tuple(fit["winner"]["multipliers"])
        profile = optimizer._profile(vector)
        if fit["winner"].get("profile") != profile:
            raise ValueError("Frozen selected100 winner profile differs")
        candidate_modules, candidate_bundle, candidate_audit = loaded_runtime.weights.materialize_weight_profile(
            loaded_runtime.modules, loaded_runtime.bundle, profile)
        baseline_scores, baseline_hashes = comparison._scores(loaded_runtime, baseline_modules, baseline_bundle, verdicts)
        candidate_scores, candidate_hashes = comparison._scores(loaded_runtime, candidate_modules, candidate_bundle, verdicts)
        result = {
            "evidence_class": _evidence_class("dev_comparison", runtime_source),
            "native_admission_verified": False,
            "target_freeze_verified": False,
            "identity": _identity("dev_comparison", captures, runtime_source, runtime_binding, selection, overrides),
            "frozen_fit": {"sha256": _sha(fit_raw), "input_commitments": fit["input_commitments"]},
            "input_commitments": {"verdict_rows_sha256": _sha(verdict_raw), "target_rows_sha256": _sha(target_raw)},
            "comparison": _comparison(analysis, baseline_scores, candidate_scores, targets),
            "baseline_scores": baseline_scores,
            "candidate_scores": candidate_scores,
            "profile_audits": {"baseline": baseline_audit, "candidate": candidate_audit},
            "score_hashes": {"baseline": baseline_hashes, "candidate": candidate_hashes},
        }
        if (_canonical(sorted(verdict_rows, key=lambda row: row["opaque_story_id"])) != verdict_raw
                or _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"])) != target_raw):
            raise ValueError("Selected DEV inputs changed during comparison")
        _postcheck(captures, loaded_runtime)
        return result
    except Exception as error:
        try:
            _postcheck(captures, loaded_runtime)
        except Exception as postcheck_error:  # noqa: BLE001 - retain the comparison failure.
            error.add_note(f"Pinned source/runtime postcheck failed: {type(postcheck_error).__name__}")
        raise
