"""Provider-free frozen-fit DEV comparison for Dryad full-HBQ analysis.

Native admission remains an upstream requirement: a reviewed fit hash binds
this module to prior evidence but cannot authenticate arbitrary native leaves.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence
import uuid


ROOT = Path(__file__).resolve().parent
PROTOCOL_PATH = ROOT / "protocol-v2.json"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
OPTIMIZER_PATH = ROOT / "optimizer.py"
OPTIMIZER_SHA256 = "6baeb9240c866b9d09ce3042b776836d2f309770fe8a6bc0abcf4b359bfe2c61"
ANALYSIS_MATH_PATH = ROOT / "analysis_math.py"
ANALYSIS_MATH_SHA256 = "237c6ff2fb9c343b7a7000fdbbe17ad76db29afde1164a4fa7f0affa0963b41f"
NATIVE_ADMISSION_PATH = ROOT / "native_admission.py"
NATIVE_ADMISSION_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
DEV_COUNT = 60
TRAIN_COUNT = 176
QUESTION_COUNT = 178
CANONICAL_VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _read(path: Path, expected: str, label: str) -> bytes:
    raw = path.read_bytes()
    if _sha(raw) != expected:
        raise ValueError(f"{label} hash drift")
    return raw


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_dev_{label}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def _capture(expected_comparison_sha256: str) -> tuple[dict[Path, bytes], dict[str, Any], ModuleType, ModuleType, ModuleType]:
    own_raw = _read(Path(__file__).resolve(), _hash(expected_comparison_sha256, "expected_comparison_sha256"), "Reviewed DEV comparison")
    protocol_raw = _read(PROTOCOL_PATH, PROTOCOL_SHA256, "Protocol")
    optimizer_raw = _read(OPTIMIZER_PATH, OPTIMIZER_SHA256, "Optimizer")
    math_raw = _read(ANALYSIS_MATH_PATH, ANALYSIS_MATH_SHA256, "Analysis math")
    native_raw = _read(NATIVE_ADMISSION_PATH, NATIVE_ADMISSION_SHA256, "Native admission")
    try:
        protocol = json.loads(protocol_raw)
    except json.JSONDecodeError as error:
        raise ValueError("Protocol is not JSON") from error
    return {Path(__file__).resolve(): own_raw, PROTOCOL_PATH: protocol_raw, OPTIMIZER_PATH: optimizer_raw,
            ANALYSIS_MATH_PATH: math_raw, NATIVE_ADMISSION_PATH: native_raw}, protocol, _load(OPTIMIZER_PATH, optimizer_raw, "optimizer"), _load(ANALYSIS_MATH_PATH, math_raw, "math"), _load(NATIVE_ADMISSION_PATH, native_raw, "native")


def _verify(captures: dict[Path, bytes], runtime: Any) -> None:
    if any(path.read_bytes() != raw for path, raw in captures.items()):
        raise ValueError("Pinned DEV comparison source changed during evaluation")
    verify = getattr(runtime, "verify", None)
    if not callable(verify):
        raise ValueError("Runtime lacks a pinned postcheck")
    verify()


def _runtime(runtime: Any, native: ModuleType) -> tuple[Any, str]:
    if runtime is None:
        return native.load_runtime(), "pinned_native_load_runtime"
    return runtime, "caller_supplied_test_runtime_no_authority"


def _questions(runtime: Any, optimizer: ModuleType) -> tuple[str, ...]:
    return optimizer._question_ids(runtime)


def _verdicts(rows: Sequence[dict[str, Any]], question_ids: tuple[str, ...]) -> dict[str, list[dict[str, str]]]:
    if not isinstance(rows, list) or len(rows) != DEV_COUNT:
        raise ValueError("DEV verdict_rows must contain exactly 60 stories")
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"opaque_story_id", "verdicts"}:
            raise ValueError("DEV verdict row must contain only opaque_story_id and verdicts")
        story, verdicts = row["opaque_story_id"], row["verdicts"]
        if type(story) is not str or not story or story in result or not isinstance(verdicts, list) or len(verdicts) != QUESTION_COUNT:
            raise ValueError("DEV verdict identity or inventory is invalid")
        checked: list[dict[str, str]] = []
        for question_id, verdict in zip(question_ids, verdicts):
            if not isinstance(verdict, dict) or set(verdict) != {"question_id", "verdict"} or verdict.get("question_id") != question_id or type(verdict.get("verdict")) is not str or verdict["verdict"] not in CANONICAL_VERDICTS:
                raise ValueError("DEV verdicts must exactly match ordered four-state outcomes")
            checked.append({"question_id": question_id, "verdict": verdict["verdict"]})
        result[story] = checked
    return result


def _fit(fit_raw: bytes, expected_fit_sha256: str, optimizer: ModuleType, analysis: ModuleType, runtime_source: str, protocol, captures) -> tuple[dict[str, Any], set[str]]:
    if not isinstance(fit_raw, bytes) or _sha(fit_raw) != _hash(expected_fit_sha256, "expected_fit_sha256"):
        raise ValueError("Frozen fit hash differs from the external review anchor")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Frozen fit has duplicate keys")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Frozen fit has a nonfinite constant")
    try:
        fit = json.loads(fit_raw, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError as error:
        raise ValueError("Frozen fit is not JSON") from error
    if not isinstance(fit, dict) or set(fit) != {"evidence_class", "identity", "input_commitments", "trial_count", "trial_records", "winner"}:
        raise ValueError("Frozen fit shape differs")
    expected_evidence = "development_fit_only" if runtime_source == "pinned_native_load_runtime" else "synthetic_fit_no_authority"
    identity = fit.get("identity")
    if fit.get("evidence_class") != expected_evidence or identity != optimizer._identity(protocol, captures, runtime_source):
        raise ValueError("Frozen fit identity or authority classification differs")
    commitments = fit.get("input_commitments")
    if not isinstance(commitments, dict) or set(commitments) != {"verdict_rows_sha256", "target_rows_sha256"}:
        raise ValueError("Frozen fit input commitments are missing")
    for value in commitments.values():
        _hash(value, "Frozen fit input commitment")
    records = fit.get("trial_records")
    if fit.get("trial_count") != 128 or not isinstance(records, list) or len(records) != 128:
        raise ValueError("Frozen fit does not contain exactly 128 trials")
    trial_ids = [record.get("trial_number") if isinstance(record, dict) else None for record in records]
    if trial_ids != list(range(128)) or any(type(number) is not int for number in trial_ids) or any(record.get("independent_recompute_match") is not True or record.get("state") == "failed" for record in records):
        raise ValueError("Frozen fit trial replay inventory differs")
    if records[0].get("multipliers") != [1.0] * len(optimizer.DOMAIN_ORDER):
        raise ValueError("Frozen fit trial zero is not the all-one baseline")
    train_ids: set[str] | None = None
    for record in records:
        if set(record) != {"trial_number", "multipliers", "profile", "profile_audit", "canonical_points_reproduced", "score_hashes", "score_rows_sha256", "analysis", "objective", "independent_recompute_match"}:
            raise ValueError("Frozen trial shape differs")
        vector = record["multipliers"]
        if not isinstance(vector, list) or len(vector) != 9 or any(type(value) not in (int, float) or value not in optimizer.MULTIPLIERS for value in vector):
            raise ValueError("Frozen trial multiplier geometry differs")
        if record["profile"] != optimizer._profile(tuple(vector)) or type(record["canonical_points_reproduced"]) is not bool or record["canonical_points_reproduced"] != (vector == [1.0] * 9):
            raise ValueError("Frozen trial profile differs")
        _hash(record["score_rows_sha256"], "Frozen trial score rows")
        score_hashes = record.get("score_hashes")
        analysis_result = record.get("analysis")
        if not isinstance(score_hashes, dict) or len(score_hashes) != TRAIN_COUNT or not isinstance(analysis_result, dict) or analysis_result.get("partition") != "TRAIN" or analysis_result.get("item_count") != TRAIN_COUNT or set(analysis_result.get("co_primary", {})) != set(analysis.CO_PRIMARY) or set(analysis_result.get("raw_axes", {})) != set(analysis.AXES):
            raise ValueError("Frozen fit trial lacks the complete TRAIN analysis")
        for metric in (*analysis_result["co_primary"].values(), *analysis_result["raw_axes"].values()):
            rho = metric.get("rho") if isinstance(metric, dict) else None
            if type(rho) not in (int, float) or not math.isfinite(rho) or not -1 <= rho <= 1:
                raise ValueError("Frozen trial correlation differs")
        objective = record["objective"]
        expected_objective = sum(analysis_result["co_primary"][name]["rho"] for name in analysis.CO_PRIMARY) / 2
        if type(objective) not in (int, float) or not math.isfinite(objective) or objective != expected_objective or analysis_result.get("protocol_sha256") != PROTOCOL_SHA256:
            raise ValueError("Frozen trial objective or protocol differs")
        if any(type(story) is not str or not story or _hash(value, "Frozen trial score") != value for story, value in score_hashes.items()):
            raise ValueError("Frozen fit score hashes are malformed")
        ids = set(score_hashes)
        if train_ids is None:
            train_ids = ids
        elif ids != train_ids:
            raise ValueError("Frozen fit trials do not share one TRAIN identity set")
    winner = fit.get("winner")
    if winner != optimizer._winner(records):
        raise ValueError("Frozen fit winner differs from the deterministic rule")
    return fit, train_ids or set()


def _scores(runtime: Any, modules: list[dict[str, Any]], bundle: dict[str, Any], verdicts: dict[str, list[dict[str, str]]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for story in sorted(verdicts):
        score = runtime.core.score_bundle(modules, bundle, verdicts[story], artifact_id=story, task_contract=None)
        observed, coverage = score.get("final_score", {}).get("observed"), score.get("coverage")
        if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed) or not 0 <= observed <= 100 or isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not math.isfinite(coverage) or coverage < 0.88:
            raise ValueError("DEV scoring produced an invalid observed score or coverage")
        rows.append({"opaque_story_id": story, "score": observed, "coverage": coverage})
        hashes[story] = _sha(_canonical(score))
    return rows, hashes


def evaluate_dev(verdict_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], fit_raw: bytes, *, expected_fit_sha256: str, expected_comparison_sha256: str, runtime: Any = None) -> dict[str, Any]:
    """Score the frozen DEV set under baseline and frozen TRAIN winner profiles."""
    captures, protocol, optimizer, analysis, native = _capture(expected_comparison_sha256)
    loaded_runtime, runtime_source = _runtime(runtime, native)
    verdict_input = target_input = None
    try:
        _verify(captures, loaded_runtime)
        fit, train_ids = _fit(fit_raw, expected_fit_sha256, optimizer, analysis, runtime_source, protocol, captures)
        question_ids = _questions(loaded_runtime, optimizer)
        verdicts = _verdicts(verdict_rows, question_ids)
        partition, targets = analysis._targets(target_rows)
        if partition != "DEV" or len(targets) != DEV_COUNT or set(verdicts) != {story for story, _ in targets} or set(verdicts).intersection(train_ids):
            raise ValueError("DEV inputs must be complete, matching, and disjoint from frozen TRAIN IDs")
        verdict_input = _canonical(sorted(verdict_rows, key=lambda row: row["opaque_story_id"]))
        target_input = _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"]))
        baseline_modules, baseline_bundle, baseline_audit = loaded_runtime.weights.materialize_weight_profile(loaded_runtime.modules, loaded_runtime.bundle, None)
        vector = tuple(fit["winner"]["multipliers"])
        candidate_profile = optimizer._profile(vector)
        if fit["winner"].get("profile") != candidate_profile:
            raise ValueError("Frozen winner profile differs from its multiplier vector")
        candidate_modules, candidate_bundle, candidate_audit = loaded_runtime.weights.materialize_weight_profile(loaded_runtime.modules, loaded_runtime.bundle, candidate_profile)
        baseline_scores, baseline_hashes = _scores(loaded_runtime, baseline_modules, baseline_bundle, verdicts)
        candidate_scores, candidate_hashes = _scores(loaded_runtime, candidate_modules, candidate_bundle, verdicts)
        comparison = analysis.compare_dev(baseline_scores, candidate_scores, target_rows)
        if _canonical(sorted(verdict_rows, key=lambda row: row["opaque_story_id"])) != verdict_input or _canonical(sorted(target_rows, key=lambda row: row["opaque_story_id"])) != target_input:
            raise ValueError("DEV inputs changed during comparison")
        evidence_class = "unadmitted_dev_comparison_only" if runtime_source == "pinned_native_load_runtime" else "synthetic_dev_comparison_no_authority"
        result = {
            "evidence_class": evidence_class,
            "native_admission_verified": False,
            "target_freeze_verified": False,
            "identity": {
                "comparison_sha256": _sha(captures[Path(__file__).resolve()]),
                "optimizer_sha256": OPTIMIZER_SHA256,
                "analysis_math_sha256": ANALYSIS_MATH_SHA256,
                "native_admission_sha256": NATIVE_ADMISSION_SHA256,
                "protocol_sha256": PROTOCOL_SHA256,
                "runtime_source": runtime_source,
                "runtime_pins": {"runtime_bindings": protocol["runtime_bindings"], "shared_runtime_bindings": protocol["shared_runtime_bindings"]},
                "frozen_fit_sha256": _sha(fit_raw),
            },
            "frozen_fit": {"sha256": _sha(fit_raw), "input_commitments": fit["input_commitments"]},
            "input_commitments": {"verdict_rows_sha256": _sha(verdict_input), "target_rows_sha256": _sha(target_input)},
            "comparison": comparison,
            "baseline_scores": baseline_scores,
            "candidate_scores": candidate_scores,
            "profile_audits": {"baseline": baseline_audit, "candidate": candidate_audit},
            "score_hashes": {"baseline": baseline_hashes, "candidate": candidate_hashes},
        }
        _verify(captures, loaded_runtime)
        return result
    except Exception as error:
        try:
            _verify(captures, loaded_runtime)
        except Exception as postcheck_error:
            error.add_note(f"Pinned source/runtime postcheck failed: {type(postcheck_error).__name__}")
        raise
