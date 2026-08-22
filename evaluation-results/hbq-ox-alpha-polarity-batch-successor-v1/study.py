"""Offline contract, schedule, normalization, and diagnostics for the Ox screen."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any

from hbqrs import runner
from hbqrs.paths import book_root

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PAIRS_PATH = ROOT / "evaluation-results" / "hbq-hanna-batch-polarity-pilot-v1" / "polarity-pairs.json"
POSITIVE_SOURCE_PATH = book_root() / "registry" / "all_modules.json"
V9_FROZEN_NAME = "frozen-ox-alpha-v9-contract.json"
STORIES = ("hanna-827", "hanna-957", "hanna-201")
QUESTION_IDS = (
    "core.task_and_brief_fidelity.operation",
    "form.prose.short_story.unity",
    "craft.narrative.plot_and_causality.causal_chain",
    "core.freshness_and_non_genericness.unpredictable_specificity",
)
CONDITIONS = (
    {"id": "positive_batch1", "polarity": "positive", "batch_size": 1},
    {"id": "negative_failure_batch1", "polarity": "negative_failure", "batch_size": 1},
    {"id": "positive_batch4", "polarity": "positive", "batch_size": 4},
    {"id": "negative_failure_batch4", "polarity": "negative_failure", "batch_size": 4},
)
PARENT = {"study_id": "hbq-human-alignment-supplemental-providers-ox-alpha-v9", "use": "provenance_and_source_selection_only", "provider_results_reused": False}
AVAILABILITY = {"eligible_524_attempt_ceiling": 5, "pause_after_consecutive_eligible_524": 6, "same_unit_cooldown_minutes": 15, "after_three_consecutive_minutes": 30, "stop_on_http_402_or_charge_signal": True}
LIMITS = ["No provider call, human judging, or paid route is performed by this package.", "Negative responses are canonicalized before comparison.", "This screen cannot change production polarity or select a production ensemble."]
CONFIRMATION_GATE = {"accepted_records": 48, "matched_story_leaf_blocks": 12, "zero_terminal_attrition": True}
REVERSE = {"YES": "NO", "NO": "YES", "NOT_APPLICABLE": "NOT_APPLICABLE", "CANNOT_ASSESS": "CANNOT_ASSESS"}
STATES = frozenset(REVERSE)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_path(path)}


def read_json(path: Path) -> dict[str, Any]:
    def unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
        pairs: dict[str, Any] = {}
        for key, value in items:
            if key in pairs:
                raise ValueError(f"Duplicate JSON key: {key}")
            pairs[key] = value
        return pairs
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def load_contract() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    required = {"format_version", "study_id", "status", "frozen_before_execution", "parent", "stories", "question_ids", "conditions", "geometry", "quote_policy", "availability", "analysis", "confirmation_gate", "limits"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != HERE.name:
        raise ValueError("Successor contract identity drifted")
    if contract["status"] != "preregistered_development_screen_unexecuted" or contract["frozen_before_execution"] is not True:
        raise ValueError("Successor must remain preregistered")
    if contract["parent"] != PARENT or tuple(contract["stories"]) != STORIES or tuple(contract["question_ids"]) != QUESTION_IDS or contract["conditions"] != list(CONDITIONS):
        raise ValueError("Successor selection drifted")
    if contract["geometry"] != {"screen_provider_calls": 30, "confirmation_provider_calls": 30, "maximum_planned_provider_calls": 60}:
        raise ValueError("Successor call geometry drifted")
    if contract["quote_policy"] != {"normalization": "invalid_exact_quote_to_summary_v1", "repair_calls_in_primary_metrics": False}:
        raise ValueError("Successor quote policy drifted")
    if contract["availability"] != AVAILABILITY or contract["limits"] != LIMITS:
        raise ValueError("Successor availability or limits drifted")
    if contract["analysis"] != {"paired_mean": "diagnostic_only_when_both_canonical_verdicts_are_scoreable", "production_recommendation": "forbidden", "confirmation": "optional_balanced_second_screen_only_after_first_stage_gate"}:
        raise ValueError("Successor analysis policy drifted")
    if contract["confirmation_gate"] != CONFIRMATION_GATE:
        raise ValueError("Successor confirmation gate drifted")
    return contract


def reviewed_pairs() -> dict[str, str]:
    raw = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    pairs = {item["question_id"]: item["failure_question"] for item in raw if isinstance(item, dict) and set(item) == {"question_id", "failure_question"}}
    if len(pairs) != len(raw) or set(QUESTION_IDS) - set(pairs):
        raise ValueError("Reviewed polarity source does not cover the frozen leaves")
    return {question_id: pairs[question_id] for question_id in QUESTION_IDS}


def _question_texts() -> dict[str, str]:
    modules = json.loads(POSITIVE_SOURCE_PATH.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "question" and isinstance(value.get("id"), str) and isinstance(value.get("text"), str):
                found[value["id"]] = value["text"]
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(modules)
    if set(QUESTION_IDS) - set(found):
        raise ValueError("Registry no longer contains selected leaves")
    return {question_id: found[question_id] for question_id in QUESTION_IDS}


def positive_wording_source() -> dict[str, Any]:
    questions = _question_texts()
    return {
        "registry": fingerprint(POSITIVE_SOURCE_PATH),
        "question_text_sha256": {question_id: hashlib.sha256(questions[question_id].encode("utf-8")).hexdigest() for question_id in QUESTION_IDS},
    }


def source_v9_provenance(v9_root: Path) -> dict[str, Any]:
    frozen = read_json(v9_root / V9_FROZEN_NAME)
    units = frozen.get("units")
    if frozen.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v9" or not isinstance(units, list):
        raise ValueError("v9 source is not the frozen Ox successor")
    present: dict[str, set[str]] = defaultdict(set)
    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("v9 unit is malformed")
        story_id = unit.get("item_id")
        ids = unit.get("question_ids")
        if isinstance(story_id, str) and isinstance(ids, list):
            present[story_id].update(item for item in ids if isinstance(item, str))
    if any(set(QUESTION_IDS) - present[story_id] for story_id in STORIES):
        raise ValueError("v9 does not contain every selected leaf for every frozen story")
    return {"frozen_contract": fingerprint(v9_root / V9_FROZEN_NAME), "stories": list(STORIES), "question_ids": list(QUESTION_IDS)}


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"Immutable artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered); output.flush(); os.fsync(output.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def freeze_plan(v9_root: Path, output: Path) -> dict[str, Any]:
    """Seal a no-provider execution plan without retaining story text or source paths."""
    contract = load_contract()
    value = {
        "format_version": 1,
        "study_id": contract["study_id"],
        "frozen_before_execution": True,
        "contract": fingerprint(CONTRACT_PATH),
        "positive_wording_source": positive_wording_source(),
        "reviewed_polarity_source": fingerprint(PAIRS_PATH),
        "v9_source": source_v9_provenance(v9_root),
        "schedule": schedule(),
        "schedule_sha256": hashlib.sha256(canonical(schedule())).hexdigest(),
        "provider_calls_this_screen": 30,
        "optional_confirmation_provider_calls": 30,
        "remote_calls": "forbidden_by_this_package",
    }
    immutable_json(output, value)
    return value


def confirmation_available(first_screen_analysis: Mapping[str, Any]) -> bool:
    gate = load_contract()["confirmation_gate"]
    attrition = first_screen_analysis.get("attrition")
    return (first_screen_analysis.get("accepted_records") == gate["accepted_records"]
            and first_screen_analysis.get("matched_story_leaf_blocks") == gate["matched_story_leaf_blocks"]
            and isinstance(attrition, Mapping)
            and all(attrition.get(status) == 0 for status in ("eligible_524", "quarantined", "global_stop")))


def schedule(screen: int = 1, *, first_screen_analysis: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    if screen not in (1, 2):
        raise ValueError("Only the primary screen and optional balanced confirmation are defined")
    if screen == 2 and (first_screen_analysis is None or not confirmation_available(first_screen_analysis)):
        raise ValueError("Balanced confirmation is unavailable before the frozen first-stage gate passes")
    rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        for story_id in STORIES:
            size = condition["batch_size"]
            for offset in range(0, len(QUESTION_IDS), size):
                ids = list(QUESTION_IDS[offset:offset + size])
                rows.append({"screen": screen, "call_id": f"s{screen}-{condition['id']}-{story_id}-{offset // size + 1}", "story_id": story_id, "condition_id": condition["id"], "polarity": condition["polarity"], "question_ids": ids})
    if len(rows) != 30 or len({row["call_id"] for row in rows}) != 30:
        raise ValueError("Successor schedule geometry drifted")
    return rows


def request_questions(row: Mapping[str, Any]) -> list[dict[str, str]]:
    if row.get("polarity") not in {"positive", "negative_failure"} or not isinstance(row.get("question_ids"), list):
        raise ValueError("Malformed scheduled row")
    positive, negative = _question_texts(), reviewed_pairs()
    source = positive if row["polarity"] == "positive" else negative
    return [{"question_id": question_id, "question": source[question_id]} for question_id in row["question_ids"]]


def canonicalize_verdict(verdict: str, polarity: str) -> str:
    if verdict not in STATES or polarity not in {"positive", "negative_failure"}:
        raise ValueError("Unknown verdict or polarity")
    return verdict if polarity == "positive" else REVERSE[verdict]


def normalize_evidence(evidence: Sequence[Mapping[str, Any]], *, question_id: str, artifact_text: str, context_texts: Sequence[str] = ()) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    audit: list[dict[str, Any]] = []
    normalized = runner._normalize_evidence(evidence, question_id=question_id, artifact_text=artifact_text, context_texts=context_texts, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
    return normalized, audit


def availability_outcome(*, http_status: int | None = None, charge_signal: bool = False) -> str:
    if charge_signal or http_status == 402:
        return "global_stop"
    return "eligible_524" if http_status == 524 else "quarantined"


def availability_policy(consecutive_eligible_524: int, *, eligible_524_for_unit: int = 0) -> dict[str, Any]:
    if (not isinstance(consecutive_eligible_524, int) or consecutive_eligible_524 < 0
            or not isinstance(eligible_524_for_unit, int) or not 0 <= eligible_524_for_unit <= AVAILABILITY["eligible_524_attempt_ceiling"]):
        raise ValueError("Malformed eligible-524 count")
    availability = load_contract()["availability"]
    if consecutive_eligible_524 >= availability["pause_after_consecutive_eligible_524"]:
        return {"state": "paused", "minutes": None}
    if eligible_524_for_unit == availability["eligible_524_attempt_ceiling"]:
        return {"state": "unit_retry_exhausted", "minutes": None}
    return {"state": "cooldown", "minutes": availability["after_three_consecutive_minutes"] if consecutive_eligible_524 >= 3 else availability["same_unit_cooldown_minutes"]}


def analyze(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize complete pairs only; a paired mean remains a diagnostic, never output policy."""
    canonical_rows: list[dict[str, Any]] = []
    attrition = {"eligible_524": 0, "quarantined": 0, "global_stop": 0, "normalized_evidence": 0}
    for row in records:
        status = row.get("status", "accepted")
        if status != "accepted":
            if status not in {"eligible_524", "quarantined", "global_stop"}: raise ValueError("Unknown result status")
            attrition[status] += 1; continue
        needed = {"story_id", "condition_id", "polarity", "question_id", "verdict", "confidence"}
        if (not needed <= set(row) or row["story_id"] not in STORIES or row["question_id"] not in QUESTION_IDS
                or row["condition_id"] not in {item["id"] for item in CONDITIONS}
                or isinstance(row["confidence"], bool) or not isinstance(row["confidence"], (int, float))
                or not math.isfinite(float(row["confidence"])) or not 0 <= float(row["confidence"]) <= 1
                or "normalized_evidence" in row and not isinstance(row["normalized_evidence"], bool)):
            raise ValueError("Malformed accepted result")
        canonical_rows.append({**row, "canonical_verdict": canonicalize_verdict(str(row["verdict"]), str(row["polarity"]))})
        attrition["normalized_evidence"] += int(bool(row.get("normalized_evidence")))
    identities = [(row["story_id"], row["condition_id"], row["question_id"]) for row in canonical_rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate accepted result")
    by_block: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in canonical_rows:
        expected_polarity = next(item["polarity"] for item in CONDITIONS if item["id"] == row["condition_id"])
        if row["polarity"] != expected_polarity:
            raise ValueError("Condition and polarity mismatch")
        by_block[(str(row["story_id"]), str(row["question_id"]))][str(row["condition_id"])] = row
    complete_blocks = [values for values in by_block.values() if set(values) == {item["id"] for item in CONDITIONS}]
    scoreable_blocks = [values for values in complete_blocks if all(row["canonical_verdict"] in {"YES", "NO"} for row in values.values())]
    pairs, disagreements, means = 0, 0, []
    condition_yes: dict[str, list[float]] = defaultdict(list)
    interactions: list[float] = []
    for values in complete_blocks:
        for positive_key, negative_key in (("positive_batch1", "negative_failure_batch1"), ("positive_batch4", "negative_failure_batch4")):
            positive, negative = values[positive_key], values[negative_key]
            pairs += 1
            disagreements += int(positive["canonical_verdict"] != negative["canonical_verdict"])
            if {positive["canonical_verdict"], negative["canonical_verdict"]} <= {"YES", "NO"}:
                means.append(((positive["canonical_verdict"] == "YES") + (negative["canonical_verdict"] == "YES")) / 2)
    for values in scoreable_blocks:
        binary = {key: float(row["canonical_verdict"] == "YES") for key, row in values.items()}
        for key, value in binary.items(): condition_yes[key].append(value)
        interactions.append((binary["positive_batch1"] - binary["negative_failure_batch1"])
                            - (binary["positive_batch4"] - binary["negative_failure_batch4"]))
    rates = {condition["id"]: (statistics.mean(condition_yes[condition["id"]]) if condition_yes[condition["id"]] else None) for condition in CONDITIONS}
    return {
        "accepted_records": len(canonical_rows), "coverage": len(canonical_rows) / 48, "matched_story_leaf_blocks": len(complete_blocks), "scoreable_matched_story_leaf_blocks": len(scoreable_blocks),
        "polarity_pairs": pairs, "canonical_polarity_disagreement_rate": None if not pairs else disagreements / pairs,
        "batch_effect": {"batch1_yes_rate": statistics.mean(value for key, value in rates.items() if key.endswith("batch1") and value is not None) if any(key.endswith("batch1") and value is not None for key, value in rates.items()) else None, "batch4_yes_rate": statistics.mean(value for key, value in rates.items() if key.endswith("batch4") and value is not None) if any(key.endswith("batch4") and value is not None for key, value in rates.items()) else None},
        "polarity_effect": {"positive_yes_rate": statistics.mean(value for key, value in rates.items() if key.startswith("positive_") and value is not None) if any(key.startswith("positive_") and value is not None for key, value in rates.items()) else None, "negative_failure_yes_rate": statistics.mean(value for key, value in rates.items() if key.startswith("negative_failure_") and value is not None) if any(key.startswith("negative_failure_") and value is not None for key, value in rates.items()) else None},
        "batch_polarity_interaction": statistics.mean(interactions) if interactions else None,
        "confidence": None if not canonical_rows else statistics.mean(float(row["confidence"]) for row in canonical_rows),
        "attrition": attrition, "quote_normalization_rate": None if not canonical_rows else attrition["normalized_evidence"] / len(canonical_rows), "paired_mean_diagnostic": None if not means else statistics.mean(means),
        "production_recommendation": None,
    }
