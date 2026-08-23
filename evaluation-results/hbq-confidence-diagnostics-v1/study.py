"""Sealed-evidence confidence diagnostics; deliberately separate from canonical HBQ scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "study-contract.json"
STATES = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
ASSESSED = {"YES", "NO"}
FRESH_DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
RESAMPLING_SEED = 560820 + 1201
RESAMPLING_DRAWS = 1000
FINGERPRINT_REQUIRED = {
    "provider", "model", "requested_reasoning_effort", "reasoning_attestation", "prompt_sha256",
    "schema_sha256", "compiled_bundle_sha256", "questions_sha256", "runtime_sha256",
    "corpus_sha256", "selection_sha256",
}
FRESH_FINGERPRINT_REQUIRED = FINGERPRINT_REQUIRED | {"accepted_artifacts_sha256"}
CONDITION_FIELDS = {"phase", "arm_id", "bundle_id", "batch_size", "polarity", "task_contract_sha256", "weight_profile_sha256"}
FRESH_CONDITION_FIELDS = CONDITION_FIELDS | {"accepted_artifacts_sha256"}
REASONING_ATTESTATIONS = {"provider_attested", "not_reported_by_grok_build_cli"}
REPEAT_EVIDENCE_KINDS = {"repeatability_confidence_evidence", "repeatability_confidence_evidence_partial_v1"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha(path)}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _finite(value: Any, label: str, *, lower: float | None = None, upper: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (lower is not None and result < lower) or (upper is not None and result > upper):
        raise ValueError(f"{label} is out of range")
    return result


def _contract() -> dict[str, Any]:
    value = _read_object(CONTRACT_PATH)
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-confidence-diagnostics-v1" or value.get("status") != "analysis_only_preregistered":
        raise ValueError("Confidence diagnostics contract identity drifted")
    return value


CONTRACT = _contract()


def _fingerprint(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != FINGERPRINT_REQUIRED or any(not isinstance(key, str) or not isinstance(item, str) or not item for key, item in value.items()):
        raise ValueError("Model fingerprint must be complete, safe, and string-valued")
    if value["reasoning_attestation"] not in REASONING_ATTESTATIONS:
        raise ValueError("Model fingerprint reasoning attestation is unsupported")
    return dict(sorted(value.items()))


def _fresh_fingerprint(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or not FINGERPRINT_REQUIRED <= set(value) or not set(value) <= FRESH_FINGERPRINT_REQUIRED:
        raise ValueError("Model fingerprint must be complete, safe, and string-valued")
    if "accepted_artifacts_sha256" not in value:
        raise ValueError("Fresh88 model fingerprint must include its accepted-artifact digest")
    base = _fingerprint({key: value[key] for key in FINGERPRINT_REQUIRED})
    digest = value["accepted_artifacts_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("Fresh88 accepted-artifact digest is malformed")
    return {**base, "accepted_artifacts_sha256": digest}


def _fingerprint_key(value: Mapping[str, str]) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _partial_shared_condition_key(model: Mapping[str, Any]) -> str:
    fingerprint, condition = model["model_fingerprint"], model["condition"]
    return hashlib.sha256(canonical({
        "model_fingerprint": {key: value for key, value in fingerprint.items() if key != "selection_sha256"},
        "condition": {key: value for key, value in condition.items() if key != "task_contract_sha256"},
    })).hexdigest()


def _authority(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("Evidence authority must be a nonempty manifest-binding map")
    parsed: dict[str, dict[str, Any]] = {}
    for name, item in value.items():
        expected_fields = {"item_count", "sha256"} if name == "accepted_artifacts" else {"bytes", "sha256"}
        if not isinstance(name, str) or not name or not isinstance(item, Mapping) or set(item) != expected_fields:
            raise ValueError("Evidence authority binding is malformed")
        size_key = "item_count" if name == "accepted_artifacts" else "bytes"
        size = item[size_key]
        digest = item["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Evidence authority binding is malformed")
        parsed[name] = {size_key: size, "sha256": digest}
    return dict(sorted(parsed.items()))


def _condition(value: Any, *, allowed_fields: set[str] = CONDITION_FIELDS) -> dict[str, str | int]:
    if not isinstance(value, Mapping) or not value or not set(value) <= allowed_fields:
        raise ValueError("Exact condition fields are malformed")
    parsed: dict[str, str | int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or (not isinstance(item, str) and not isinstance(item, int)) or isinstance(item, bool) or (isinstance(item, str) and not item):
            raise ValueError("Exact condition fields are malformed")
        parsed[key] = item
    return dict(sorted(parsed.items()))


def _sealed_input(directory: Path, expected_kind: str | set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = directory.resolve()
    input_path, manifest_path = directory / "confidence-input.json", directory / "manifest.json"
    if not directory.is_dir() or not input_path.is_file() or not manifest_path.is_file():
        raise ValueError("Sealed confidence evidence requires confidence-input.json and manifest.json")
    manifest, payload = _read_object(manifest_path), _read_object(input_path)
    expected_kinds = {expected_kind} if isinstance(expected_kind, str) else expected_kind
    if not expected_kinds or not all(isinstance(kind, str) for kind in expected_kinds):
        raise ValueError("Sealed confidence evidence requires a nonempty kind allowlist")
    if set(manifest) != {"format_version", "kind", "files"} or manifest.get("format_version") != 1 or manifest.get("kind") not in expected_kinds or manifest.get("files") != {"confidence-input.json": binding(input_path)}:
        raise ValueError("Sealed confidence evidence manifest does not bind exactly its input bytes")
    expected_fields = {"format_version", "kind", "models"}
    partial_counts: dict[str, int] | None = None
    if payload.get("kind") == "repeatability_confidence_evidence_partial_v1":
        expected_fields.add("partial_exclusions")
        expected_fields.add("partial_shared_condition_sha256")
        exclusions = payload.get("partial_exclusions")
        shared_condition = payload.get("partial_shared_condition_sha256")
        if not isinstance(shared_condition, str) or len(shared_condition) != 64 or any(character not in "0123456789abcdef" for character in shared_condition):
            raise ValueError("Partial repeat evidence shared condition is malformed")
        if not isinstance(exclusions, list) or any(not isinstance(row, Mapping) or set(row) != {"item_id", "reason"} or not isinstance(row["item_id"], str) or not row["item_id"] or row["reason"] not in {"missing_repetition", "duplicate_repetition", "condition_or_score_drift", "different_shared_condition"} for row in exclusions):
            raise ValueError("Partial repeat evidence exclusions are malformed")
        partial_counts = dict(sorted(Counter(str(row["reason"]) for row in exclusions).items()))
    if set(payload) != expected_fields or payload.get("format_version") != 1 or payload.get("kind") not in expected_kinds or payload.get("kind") != manifest.get("kind"):
        raise ValueError("Sealed confidence evidence kind drifted")
    receipt = {"input": binding(input_path), "manifest": binding(manifest_path), "kind": payload["kind"]}
    if partial_counts is not None:
        receipt["partial_exclusion_counts"] = partial_counts
        receipt["partial_shared_condition_sha256"] = payload["partial_shared_condition_sha256"]
    return payload, receipt


def _rank(values: Sequence[float]) -> list[float]:
    ordered, result, start = sorted(enumerate(values), key=lambda pair: pair[1]), [0.0] * len(values), 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + 1 + end) / 2
        for index, _ in ordered[start:end]:
            result[index] = rank
        start = end
    return result


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    denominator = sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    return None if denominator == 0 else sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right)) / math.sqrt(denominator)


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _modal(values: Sequence[str]) -> tuple[str | None, float]:
    counts = Counter(values)
    maximum = max(counts.values())
    labels = sorted(label for label, count in counts.items() if count == maximum)
    return (labels[0] if len(labels) == 1 else None), maximum / len(values)


def _bins(predictions: Sequence[tuple[float, int]]) -> tuple[list[dict[str, Any]], float | None]:
    if not predictions:
        return [], None
    rows: list[dict[str, Any]] = []
    weighted_error = 0.0
    for index in range(10):
        lower, upper = index / 10, (index + 1) / 10
        bucket = [(confidence, outcome) for confidence, outcome in predictions if lower <= confidence <= upper and (index == 9 or confidence < upper)]
        if not bucket:
            continue
        mean_confidence = statistics.fmean(value[0] for value in bucket)
        consensus = statistics.fmean(value[1] for value in bucket)
        weighted_error += len(bucket) * abs(mean_confidence - consensus)
        rows.append({"lower": lower, "upper": upper, "count": len(bucket), "mean_raw_confidence": mean_confidence, "repeat_consensus_proxy_agreement": consensus})
    return rows, weighted_error / len(predictions)


def _repeat_records(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Repeat input requires nonempty models")
    result: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, Mapping) or set(model) != {"model_fingerprint", "condition", "authority", "records"}:
            raise ValueError("Repeat model has an unsupported field")
        fingerprint = _fingerprint(model["model_fingerprint"])
        condition = _condition(model["condition"])
        authority = _authority(model["authority"])
        key = _fingerprint_key(fingerprint)
        records = model["records"]
        if key in result or not isinstance(records, list) or not records:
            raise ValueError("Repeat model fingerprint or records are invalid")
        parsed: list[dict[str, Any]] = []
        identities: set[tuple[str, str]] = set()
        repeat_count: int | None = None
        for record in records:
            if not isinstance(record, Mapping) or set(record) != {"item_id", "question_id", "role", "effective_weight", "responses"}:
                raise ValueError("Repeat record has an unsupported field")
            item_id, question_id, role = record["item_id"], record["question_id"], record["role"]
            if not all(isinstance(value, str) and value for value in (item_id, question_id, role)) or (item_id, question_id) in identities:
                raise ValueError("Repeat record identity is invalid or duplicated")
            identities.add((item_id, question_id))
            weight = _finite(record["effective_weight"], "Repeat effective weight", lower=0)
            responses = record["responses"]
            if not isinstance(responses, list) or len(responses) < 2:
                raise ValueError("Repeat record requires at least two responses")
            if repeat_count is None:
                repeat_count = len(responses)
            elif repeat_count != len(responses):
                raise ValueError("Repeat records must form a rectangular response matrix")
            checked = []
            for response in responses:
                if not isinstance(response, Mapping) or set(response) != {"verdict", "confidence"} or response["verdict"] not in STATES:
                    raise ValueError("Repeat response is malformed")
                checked.append({"verdict": response["verdict"], "confidence": _finite(response["confidence"], "Repeat confidence", lower=0, upper=1)})
            parsed.append({"item_id": item_id, "question_id": question_id, "role": role, "effective_weight": weight, "responses": checked})
        result[key] = {"model_fingerprint": fingerprint, "condition": condition, "authority": authority, "records": parsed}
    return result


def _repeat_resampling(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(records)
    repetitions = len(records[0]["responses"])
    if not count or repetitions < 2:
        return {"status": "unavailable_not_identifiable"}
    generator = random.Random(f"{RESAMPLING_SEED}:{count}:{repetitions}")
    uniform_accuracy, uniform_decided, targeted_accuracy, targeted_decided = [], [], [], []
    for _ in range(RESAMPLING_DRAWS):
        initial = [record["responses"][generator.randrange(repetitions)] for record in records]
        modalities = [_modal([response["verdict"] for response in record["responses"]])[0] for record in records]
        uniform_extra = [record["responses"][generator.randrange(repetitions)] for record in records]
        uniform_outcomes = [(_modal([first["verdict"], second["verdict"]])[0], modal) for first, second, modal in zip(initial, uniform_extra, modalities)]
        uniform_valid = [int(decision == modal) for decision, modal in uniform_outcomes if decision is not None and modal is not None]
        uniform_accuracy.append(statistics.fmean(uniform_valid) if uniform_valid else None)
        uniform_decided.append(len(uniform_valid) / count)
        raw_weights = [max(0.001, 1 - response["confidence"]) for response in initial]
        total = sum(raw_weights)
        allocations = [0] * count
        for _ in range(count):
            threshold, cumulative = generator.random() * total, 0.0
            for index, value in enumerate(raw_weights):
                cumulative += value
                if cumulative >= threshold:
                    allocations[index] += 1
                    break
        matches = []
        for record, first, modal, allocation in zip(records, initial, modalities, allocations):
            labels = [first["verdict"]] + [record["responses"][generator.randrange(repetitions)]["verdict"] for _ in range(allocation)]
            decision = _modal(labels)[0]
            if decision is not None and modal is not None:
                matches.append(int(decision == modal))
        targeted_accuracy.append(statistics.fmean(matches) if matches else None)
        targeted_decided.append(len(matches) / count)
    usable_uniform = [value for value in uniform_accuracy if value is not None]
    usable_targeted = [value for value in targeted_accuracy if value is not None]
    return {"status": "observed_repeat_bootstrap_only", "seed": RESAMPLING_SEED, "draws": RESAMPLING_DRAWS, "total_response_draws_per_simulation": 2 * count, "initial_response_draws": count, "additional_response_draws": count, "tie_rule": "A tied sampled decision or tied full-repeat proxy abstains and is excluded from proxy-accuracy denominators.", "strategies": {"uniform_one_extra_per_leaf": {"mean_proxy_accuracy_on_decided": statistics.fmean(usable_uniform) if usable_uniform else None, "mean_decided_leaf_fraction": statistics.fmean(uniform_decided)}, "low_initial_confidence_reallocation": {"mean_proxy_accuracy_on_decided": statistics.fmean(usable_targeted) if usable_targeted else None, "mean_decided_leaf_fraction": statistics.fmean(targeted_decided), "minus_uniform_proxy_accuracy": statistics.fmean(usable_targeted) - statistics.fmean(usable_uniform) if usable_uniform and usable_targeted else None}}, "interpretation": "A bootstrap of finite observed response distributions under equal total response draws; it does not establish prospective live-call benefit."}


def _repeat_model(model: Mapping[str, Any]) -> dict[str, Any]:
    records = model["records"]
    predictions: list[tuple[float, int]] = []
    per_leaf, stable_confidences, flip_confidences = [], [], []
    by_role: dict[str, list[dict[str, Any]]] = {}
    leave_one_out_tied = 0
    for record in records:
        responses, weight = record["responses"], record["effective_weight"]
        labels = [response["verdict"] for response in responses]
        _, modal_proportion = _modal(labels)
        confidences = [response["confidence"] for response in responses]
        for index, (label, confidence) in enumerate(zip(labels, confidences)):
            leave_out = labels[:index] + labels[index + 1:]
            consensus, _ = _modal(leave_out)
            if consensus is None:
                leave_one_out_tied += 1
            else:
                predictions.append((confidence, int(label == consensus)))
        stable = len(set(labels)) == 1
        (stable_confidences if stable else flip_confidences).append(statistics.fmean(confidences))
        per_leaf.append({"stable": stable, "modal_proportion": modal_proportion, "pairwise_agreement": sum(left == right for index, left in enumerate(labels) for right in labels[index + 1:]) / math.comb(len(labels), 2), "mean_confidence": statistics.fmean(confidences)})
        by_role.setdefault(record["role"], []).extend([{**response, "effective_weight": weight} for response in responses])
    reliability, ece = _bins(predictions)
    def role_summary(values: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        assessed = [value for value in values if value["verdict"] in ASSESSED]
        weight = sum(value["effective_weight"] for value in assessed)
        confidence_mass = sum(value["confidence"] * value["effective_weight"] for value in assessed)
        return {"assessed_response_count": len(assessed), "unweighted_yes_rate": statistics.fmean(int(value["verdict"] == "YES") for value in assessed) if assessed else None, "effective_weighted_yes_rate": sum(value["effective_weight"] * int(value["verdict"] == "YES") for value in assessed) / weight if weight else None, "confidence_weighted_yes_rate": sum(value["confidence"] * value["effective_weight"] * int(value["verdict"] == "YES") for value in assessed) / confidence_mass if confidence_mass else None, "effective_confidence_mass": confidence_mass / weight if weight else None, "effective_confidence_mass_is_not_coverage": True}
    return {"model_fingerprint": model["model_fingerprint"], "condition": model["condition"], "authority": model["authority"], "record_count": len(records), "total_response_count": sum(len(record["responses"]) for record in records), "leave_one_out_eligible_response_count": len(predictions), "leave_one_out_tied_excluded_response_count": leave_one_out_tied, "repetitions": len(records[0]["responses"]), "repeat_consensus_proxy_not_human_truth": True, "stable_vs_flip": {"stable_leaf_count": sum(row["stable"] for row in per_leaf), "flipped_leaf_count": sum(not row["stable"] for row in per_leaf), "stable_mean_raw_confidence": statistics.fmean(stable_confidences) if stable_confidences else None, "flipped_mean_raw_confidence": statistics.fmean(flip_confidences) if flip_confidences else None, "mean_pairwise_repeat_agreement": statistics.fmean(row["pairwise_agreement"] for row in per_leaf), "mean_modal_proportion": statistics.fmean(row["modal_proportion"] for row in per_leaf)}, "leave_one_out_repeat_consensus_proxy_calibration": {"brier": statistics.fmean((confidence - outcome) ** 2 for confidence, outcome in predictions) if predictions else None, "ece": ece, "reliability_bins": reliability, "tie_rule": "Exclude a response when the other repetitions have no unique modal verdict."}, "role_stratified_noncanonical_diagnostics": {role: role_summary(values) for role, values in sorted(by_role.items())}, "equal_budget_resampling": _repeat_resampling(records)}


def _partial_repeat_aggregate(models: Sequence[Mapping[str, Any]], shared_condition_sha256: str) -> dict[str, Any]:
    if len(models) < 3:
        raise ValueError("Partial aggregate requires at least three complete stories")
    pooled = [record for model in models for record in model["records"]]
    derived = _repeat_model({"model_fingerprint": models[0]["model_fingerprint"], "condition": models[0]["condition"], "authority": models[0]["authority"], "records": pooled})
    return {
        "story_count": len(models),
        "aggregation": "Pooled leaves from complete stories sharing the exact model/prompt/schema/runtime condition; task and artifact bindings remain story-specific.",
        "shared_condition_sha256": shared_condition_sha256,
        **{key: value for key, value in derived.items() if key not in {"model_fingerprint", "condition", "authority"}},
    }


def _fresh_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Fresh88 input requires nonempty models")
    parsed_models = []
    fingerprints: set[str] = set()
    for model in models:
        if not isinstance(model, Mapping) or set(model) != {"model_fingerprint", "condition", "authority", "selection_digest", "records"}:
            raise ValueError("Fresh88 model has an unsupported field")
        fingerprint = _fresh_fingerprint(model["model_fingerprint"])
        condition = _condition(model["condition"], allowed_fields=FRESH_CONDITION_FIELDS)
        authority = _authority(model["authority"])
        accepted = authority.get("accepted_artifacts")
        accepted_digest = fingerprint["accepted_artifacts_sha256"]
        if condition.get("accepted_artifacts_sha256") != accepted_digest or not isinstance(accepted, Mapping) or accepted.get("sha256") != accepted_digest or accepted.get("item_count") != 88:
            raise ValueError("Fresh88 accepted-artifact digest binding drifted")
        key = _fingerprint_key(fingerprint)
        records = model["records"]
        if key in fingerprints or not isinstance(records, list) or len(records) != 88:
            raise ValueError("Fresh88 requires 88 records per separate model fingerprint")
        fingerprints.add(key)
        rows, ids = [], set()
        for record in records:
            required = {"item_id", "source_model", "score", "hanna_overall", "hanna_dimensions", "mapped_scores", "mapped_confidences", "verdicts"}
            if not isinstance(record, Mapping) or set(record) != required or not isinstance(record["item_id"], str) or not record["item_id"] or record["item_id"] in ids or not isinstance(record["source_model"], str) or not record["source_model"]:
                raise ValueError("Fresh88 record identity or fields are invalid")
            ids.add(record["item_id"])
            dimensions = record["hanna_dimensions"]
            if not isinstance(dimensions, Mapping) or set(dimensions) != set(FRESH_DIMENSIONS):
                raise ValueError("Fresh88 record must retain exactly the six HANNA dimensions")
            mapped_scores, mapped_confidences = record["mapped_scores"], record["mapped_confidences"]
            if not isinstance(mapped_scores, Mapping) or set(mapped_scores) != set(FRESH_DIMENSIONS) or not isinstance(mapped_confidences, Mapping) or set(mapped_confidences) != set(FRESH_DIMENSIONS):
                raise ValueError("Fresh88 record must retain exact mapped HBQ scores and confidence mass for every HANNA dimension")
            verdicts = record["verdicts"]
            if not isinstance(verdicts, list) or not verdicts:
                raise ValueError("Fresh88 record requires verdict metadata")
            checked = []
            for verdict in verdicts:
                if not isinstance(verdict, Mapping) or set(verdict) != {"verdict", "confidence", "effective_weight", "role"} or verdict["verdict"] not in STATES or not isinstance(verdict["role"], str) or not verdict["role"]:
                    raise ValueError("Fresh88 verdict metadata is malformed")
                checked.append({"verdict": verdict["verdict"], "confidence": _finite(verdict["confidence"], "Fresh88 confidence", lower=0, upper=1), "effective_weight": _finite(verdict["effective_weight"], "Fresh88 effective weight", lower=0), "role": verdict["role"]})
            rows.append({"item_id": record["item_id"], "source_model": record["source_model"], "score": _finite(record["score"], "Fresh88 score"), "hanna_overall": _finite(record["hanna_overall"], "HANNA overall"), "hanna_dimensions": {name: _finite(dimensions[name], f"HANNA {name}") for name in FRESH_DIMENSIONS}, "mapped_scores": {name: _finite(mapped_scores[name], f"Mapped HBQ {name}", lower=0, upper=1) if mapped_scores[name] is not None else None for name in FRESH_DIMENSIONS}, "mapped_confidences": {name: _finite(mapped_confidences[name], f"Mapped confidence {name}", lower=0, upper=1) if mapped_confidences[name] is not None else None for name in FRESH_DIMENSIONS}, "verdicts": checked})
        if sum(row["source_model"] != "Human" for row in rows) != 80:
            raise ValueError("Fresh88 input must retain the frozen generated-only primary count of 80")
        digest = hashlib.sha256(canonical([{"item_id": row["item_id"], "source_model": row["source_model"], "hanna_overall": row["hanna_overall"], "hanna_dimensions": row["hanna_dimensions"]} for row in rows])).hexdigest()
        if model["selection_digest"] != digest:
            raise ValueError("Fresh88 model selection/source/HANNA digest drifted")
        parsed_models.append({"model_fingerprint": fingerprint, "condition": condition, "authority": authority, "selection_digest": digest, "records": rows})
    if len({model["selection_digest"] for model in parsed_models}) != 1:
        raise ValueError("Fresh88 models do not share exact ordered selection/source/HANNA parity")
    if len({str(model["condition"]["task_contract_sha256"]) for model in parsed_models}) != 1:
        raise ValueError("Fresh88 models do not share the exact ordered 88-item task-contract digest")
    return parsed_models


def _fresh_model(model: Mapping[str, Any]) -> dict[str, Any]:
    rows = model["records"]
    mean_confidence = []
    by_role: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        verdicts = row["verdicts"]
        row["mean_confidence"] = statistics.fmean(verdict["confidence"] for verdict in verdicts)
        mean_confidence.append(row["mean_confidence"])
        for verdict in verdicts:
            by_role.setdefault(verdict["role"], []).append(verdict)
    def agreement(subset: Sequence[Mapping[str, Any]], dimension: str | None) -> dict[str, Any]:
        eligible = [row for row in subset if dimension is None or (row["mapped_scores"][dimension] is not None and row["mapped_confidences"][dimension] is not None)]
        score_values = [row["mapped_scores"][dimension] if dimension is not None else row["score"] for row in eligible]
        confidence_values = [row["mapped_confidences"][dimension] if dimension is not None else row["mean_confidence"] for row in eligible]
        human = [row["hanna_dimensions"][dimension] if dimension is not None else row["hanna_overall"] for row in eligible]
        score_rank, human_rank = _rank(score_values), _rank(human)
        error = [abs(left - right) / (len(eligible) - 1) for left, right in zip(score_rank, human_rank)] if len(eligible) > 1 else []
        return {"eligible_item_count": len(eligible), "mapped_hbq_vs_hanna_spearman": _spearman(score_values, human), "confidence_vs_rank_agreement_spearman": _spearman(confidence_values, [-value for value in error]), "confidence_vs_abs_rank_error_spearman": _spearman(confidence_values, error), "mean_abs_rank_error": statistics.fmean(error) if error else None, "not_leaf_truth_or_calibration": True}
    def role_summary(values: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        assessed = [value for value in values if value["verdict"] in ASSESSED]
        total = sum(value["effective_weight"] for value in assessed)
        confidence = sum(value["confidence"] * value["effective_weight"] for value in assessed)
        return {"assessed_response_count": len(assessed), "effective_weighted_yes_rate": sum(value["effective_weight"] * int(value["verdict"] == "YES") for value in assessed) / total if total else None, "confidence_weighted_yes_rate": sum(value["confidence"] * value["effective_weight"] * int(value["verdict"] == "YES") for value in assessed) / confidence if confidence else None, "effective_confidence_mass": confidence / total if total else None, "effective_confidence_mass_is_not_coverage": True}
    def section(subset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {"item_count": len(subset), "overall": agreement(subset, None), "dimensions": {name: agreement(subset, name) for name in FRESH_DIMENSIONS}}
    return {"model_fingerprint": model["model_fingerprint"], "condition": model["condition"], "authority": model["authority"], "selection_digest": model["selection_digest"], "item_count": len(rows), "primary_generated80": section([row for row in rows if row["source_model"] != "Human"]), "secondary_all88": section(rows), "role_stratified_noncanonical_diagnostics": {role: role_summary(values) for role, values in sorted(by_role.items())}, "confidence_vs_hanna_rank_association": {"status": "descriptive_not_leaf_calibration", "brier_ece_reliability_bins": "not_emitted_without_binary_human_leaf_truth"}}


def _atomic_output(output: Path, files: Mapping[str, bytes]) -> None:
    if output.exists():
        raise ValueError("Refusing to merge confidence diagnostics into an existing output")
    output.mkdir(parents=True)
    for name, content in files.items():
        (output / name).write_bytes(content)


def _disjoint(output: Path, roots: Sequence[Path]) -> None:
    resolved = output.resolve()
    for root in roots:
        candidate = root.resolve()
        if resolved == candidate or candidate in resolved.parents or resolved in candidate.parents:
            raise ValueError("Confidence output must be disjoint from every evidence root")


def analyze(repeat_dir: Path | None, fresh88_dir: Path | None, output: Path) -> dict[str, Any]:
    if repeat_dir is None and fresh88_dir is None:
        raise ValueError("At least one sealed confidence evidence directory is required")
    roots = [root for root in (repeat_dir, fresh88_dir) if root is not None]
    _disjoint(output, roots)
    evidence: dict[str, Any] = {}
    repeat_result, fresh_result, partial_repeat_aggregate = None, None, None
    if repeat_dir is not None:
        payload, receipt = _sealed_input(repeat_dir, REPEAT_EVIDENCE_KINDS)
        models = _repeat_records(payload)
        if payload["kind"] == "repeatability_confidence_evidence_partial_v1":
            if any(len({record["item_id"] for record in model["records"]}) != 1 for model in models.values()):
                raise ValueError("Partial repeat evidence requires exactly one complete story per model group")
            covered = {record["item_id"] for model in models.values() for record in model["records"]}
            excluded = [row["item_id"] for row in payload["partial_exclusions"]]
            if len(covered) < 3 or len(excluded) != len(set(excluded)) or covered & set(excluded) or len(covered) + len(excluded) != 11:
                raise ValueError("Partial repeat evidence does not account exactly for the frozen 11-story schedule")
            shared_conditions = {_partial_shared_condition_key(model) for model in models.values()}
            if shared_conditions != {payload["partial_shared_condition_sha256"]}:
                raise ValueError("Partial repeat evidence does not share its declared full model/prompt/schema/runtime condition")
        repeat_result = {key: _repeat_model(model) for key, model in sorted(models.items())}
        if payload["kind"] == "repeatability_confidence_evidence_partial_v1":
            partial_repeat_aggregate = _partial_repeat_aggregate([model for _, model in sorted(models.items())], payload["partial_shared_condition_sha256"])
        evidence["repeatability"] = receipt
    if fresh88_dir is not None:
        payload, receipt = _sealed_input(fresh88_dir, "fresh88_confidence_evidence")
        fresh_result = {_fingerprint_key(model["model_fingerprint"]): _fresh_model(model) for model in _fresh_records(payload)}
        evidence["fresh88"] = receipt
    summary = {"format_version": 1, "study_id": CONTRACT["study_id"], "analysis_only": True, "canonical_hbq_unchanged": True, "confidence_status": "diagnostic_only", "evidence": evidence, "repeatability": repeat_result, "partial_repeatability_aggregate": partial_repeat_aggregate, "fresh88": fresh_result, "limits": CONTRACT["limits"], "privacy": "Aggregate-only output: no item IDs, prose, prompts, raw verdicts, sessions, request IDs, or provider response text."}
    body = canonical(summary) + b"\n"
    manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "files": {"summary.json": {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}}}
    rendered = {"summary.json": body, "manifest.json": canonical(manifest) + b"\n"}
    forbidden = ('"item_id"', "source.md", "prompt.md", '"session_id"', '"request_id"')
    if any(token in rendered["summary.json"].decode("utf-8") for token in forbidden):
        raise ValueError("Confidence aggregate output would expose raw/private material")
    _atomic_output(output, rendered)
    verify_output(output)
    return summary


def verify_output(output: Path) -> dict[str, Any]:
    output = output.resolve()
    summary_path, manifest_path = output / "summary.json", output / "manifest.json"
    if not summary_path.is_file() or not manifest_path.is_file():
        raise ValueError("Confidence output requires summary.json and manifest.json")
    summary, manifest = _read_object(summary_path), _read_object(manifest_path)
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "files": {"summary.json": binding(summary_path)}}
    if manifest != expected:
        raise ValueError("Confidence output manifest does not bind exactly its aggregate summary")
    required = {"format_version", "study_id", "analysis_only", "canonical_hbq_unchanged", "confidence_status", "evidence", "repeatability", "partial_repeatability_aggregate", "fresh88", "limits", "privacy"}
    if set(summary) != required or summary["format_version"] != 1 or summary["study_id"] != CONTRACT["study_id"] or summary["analysis_only"] is not True or summary["canonical_hbq_unchanged"] is not True or summary["confidence_status"] != "diagnostic_only":
        raise ValueError("Confidence output identity or noncanonical boundary drifted")
    def reject_raw(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, Mapping):
            forbidden = {"item_id", "question_id", "verdict", "source", "prompt", "session_id", "request_id", "response"}
            if path != ():
                forbidden.add("evidence")
            if set(value) & forbidden:
                raise ValueError("Confidence output exposes raw/private record material")
            for key, child in value.items():
                reject_raw(child, path + (str(key),))
        elif isinstance(value, list):
            for child in value:
                reject_raw(child, path)
    reject_raw(summary)
    repeat_receipt = summary["evidence"].get("repeatability")
    aggregate = summary["partial_repeatability_aggregate"]
    if isinstance(repeat_receipt, Mapping) and repeat_receipt.get("kind") == "repeatability_confidence_evidence_partial_v1":
        if not isinstance(aggregate, Mapping) or aggregate.get("story_count") != len(summary["repeatability"] or {}) or aggregate.get("shared_condition_sha256") != repeat_receipt.get("partial_shared_condition_sha256"):
            raise ValueError("Partial repeat aggregate is missing its shared-condition binding")
        if aggregate.get("record_count") != sum(model["record_count"] for model in (summary["repeatability"] or {}).values()) or aggregate.get("total_response_count") != sum(model["total_response_count"] for model in (summary["repeatability"] or {}).values()):
            raise ValueError("Partial repeat aggregate arithmetic drifted")
    elif aggregate is not None:
        raise ValueError("Non-partial evidence must not emit a partial repeat aggregate")
    if summary["fresh88"] is not None:
        for model in summary["fresh88"].values():
            if model["primary_generated80"]["item_count"] != 80 or model["secondary_all88"]["item_count"] != 88 or model["confidence_vs_hanna_rank_association"]["brier_ece_reliability_bins"] != "not_emitted_without_binary_human_leaf_truth":
                raise ValueError("Fresh88 output lacks its required primary/secondary or calibration boundary")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze sealed HBQ confidence metadata without provider contact.")
    parser.add_argument("--repeat-evidence-dir", type=Path)
    parser.add_argument("--fresh88-evidence-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.repeat_evidence_dir.resolve() if args.repeat_evidence_dir else None, args.fresh88_evidence_dir.resolve() if args.fresh88_evidence_dir else None, args.output_dir.resolve())
    return 0
