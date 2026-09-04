"""Matched TRAIN-only HANNA elicitation experiment: direct scores versus thresholds."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v15-rank-discrimination-v1"
CONTRACT_PATH = HERE / "experiment-contract.json"
V13 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-v1/study.py"
V13_SHA256 = "f2b5a4c178cf2a7919b5dfd8c5ddde7bf5c1e0e9aa81a2f2f4d0bdd9b97c8261"
V13_COMMIT = "9c76e81"
DIRECT, THRESHOLDS = "direct_integer", "ordinal_thresholds"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
THRESHOLD_KEYS = ("at_least_2", "at_least_3", "at_least_4", "at_least_5")

# Faithful paraphrases (not verbatim) of HANNA Appendix A, Table 7, levels 1-5.
ANCHORS = {
    "Relevance": ["unrelated", "weakly related", "rough prompt match", "match with one or two minor deviations", "exact prompt match"],
    "Coherence": ["nonsensical, unstable, or without a comprehensible plot", "mostly nonsensical", "mostly sensible with inconsistencies", "one or two small inconsistencies", "sensible throughout"],
    "Empathy": ["apathetic", "slight emotional connection", "identifiable emotions", "emotional involvement with minor obstacles", "complete emotional involvement"],
    "Surprise": ["ending obvious initially or nonsensical", "ending predictable early", "ending predictable halfway", "ending surprising but difficult to foresee", "ending surprising yet credibly foreshadowed"],
    "Engagement": ["boring", "one or two interesting elements", "mildly interesting", "nearly sustains interest to the end", "makes the reader want a sequel"],
    "Complexity": ["minimal setting with one or two characters or concepts", "simple plot or setting", "at least one development feature", "at least two development features", "at least three development features"],
}
COMPLEXITY_FEATURES = (
    "sophisticated concepts",
    "realistic characters",
    "intricate plotting",
    "background history or circumstances",
    "precise description",
)
HANNA_TABLE7_URL = "https://arxiv.org/html/2208.11646v2#A1.T7"
SHARED_INSTRUCTION = (
    "Assess this writing reference-free using the six HANNA criteria and the supplied "
    "level anchors. Apply the anchors to the writing itself; do not infer a human target. "
    "Empathy means understanding emotions, not agreement. Surprise concerns the ending. "
    "For Complexity, development features include sophisticated concepts, realistic characters, "
    "intricate plotting, background history or circumstances, and precise description. "
    "If the story ends mid-sentence, assess it as ending before that unfinished sentence. "
    "Prompt irrelevance affects Relevance only. Provide concise evidence for every criterion "
    "and set coverage truthfully."
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def load(path: Path, commit: str, digest: str, name: str) -> ModuleType:
    raw = Path(path).read_bytes()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{Path(path).relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned dependency cannot load")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if Path(path).read_bytes() != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def contract() -> dict[str, Any]:
    value = strict(CONTRACT_PATH.read_bytes(), "experiment contract")
    if value.get("study_id") != STUDY_ID or value.get("geometry") != {"conditions": 2, "grok_cells": 96, "groups": 24, "items": 48, "max_concurrency": 10, "sol_cells": 0}:
        raise ValueError("experiment contract drifted")
    return value


def _direct_schema() -> dict[str, Any]:
    return {"format_version": 1, "type": "object", "additionalProperties": False, "required": ["scores", "evidence", "coverage"], "properties": {"scores": {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "integer", "minimum": 1, "maximum": 5} for dimension in DIMS}}, "evidence": {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "string", "minLength": 1} for dimension in DIMS}}, "coverage": {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "boolean"} for dimension in DIMS}}}}


def _threshold_schema() -> dict[str, Any]:
    bits = {key: {"type": "boolean"} for key in THRESHOLD_KEYS}
    return {"format_version": 1, "type": "object", "additionalProperties": False, "required": ["thresholds", "evidence", "coverage"], "properties": {"thresholds": {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "object", "additionalProperties": False, "required": list(THRESHOLD_KEYS), "properties": bits} for dimension in DIMS}}, "evidence": {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "string", "minLength": 1} for dimension in DIMS}}, "coverage": {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "boolean"} for dimension in DIMS}}}}


def _train48_items(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> list[dict[str, Any]]:
    v13 = load(V13, V13_COMMIT, V13_SHA256, "_v15_v13_items")
    v11 = v13.load(v13.V11, v13.V11_COMMIT, v13.V11_SHA256, "_v15_v11_items")
    rows = [*v11.source_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract)), *v13.source_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))]
    if len(rows) != 48 or len({row["item_id"] for row in rows}) != 48 or len({row["prompt_group_id"] for row in rows}) != 24 or any(row.get("partition") != "train" or set(row.get("target", {})) != set(DIMS) for row in rows):
        raise ValueError("V15 TRAIN48 source union drifted")
    return sorted((dict(row) for row in rows), key=lambda row: (str(row["prompt_group_id"]), str(row["item_id"])))


def _shared_anchor_payload() -> tuple[str, dict[str, Any]]:
    return SHARED_INSTRUCTION, {
        "instruction_sha256": sha256(SHARED_INSTRUCTION.encode("utf-8")),
        "table": "HANNA Appendix A Table 7",
        "table_url": HANNA_TABLE7_URL,
        "paraphrase_only": True,
    }


def _condition(condition: str, anchors: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if condition == DIRECT:
        form, schema = {"kind": DIRECT, "instruction": "Return one integer score from 1 through 5 for each dimension."}, _direct_schema()
    elif condition == THRESHOLDS:
        form, schema = {"kind": THRESHOLDS, "instruction": "For each dimension, answer the four cumulative binary questions: score at least 2, 3, 4, and 5."}, _threshold_schema()
    else:
        raise ValueError("unknown V15 condition")
    profile = {"format_version": 1, "shared_hanna_criterion_anchors": dict(anchors), "complexity_development_features": list(COMPLEXITY_FEATURES), "condition": form, "reference_free": True, "prompt_irrelevance_affects": "Relevance_only", "cut_mid_sentence_policy": "assess_as_ending_before_the_unfinished_sentence"}
    return profile, schema


def _payload(*, instruction: str, anchors: Mapping[str, Any], condition: str, item: Mapping[str, Any]) -> bytes:
    profile, schema = _condition(condition, anchors)
    value = {"format_version": 1, "study_id": STUDY_ID, "instruction": instruction, "profile": profile, "writing": {"prompt": item["prompt"], "story": item["story"]}, "response_schema": schema}
    if set(value) != {"format_version", "study_id", "instruction", "profile", "writing", "response_schema"} or set(value["writing"]) != {"prompt", "story"} or "target" in value or "target" in value["writing"]:
        raise ValueError("target leaked into outbound payload")
    return canonical(value)


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    contract_value = contract()
    instruction, anchor_source = _shared_anchor_payload()
    items = _train48_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    cells: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        ordered = (DIRECT, THRESHOLDS) if index % 2 == 0 else (THRESHOLDS, DIRECT)
        for condition in ordered:
            profile, _schema = _condition(condition, ANCHORS)
            payload = _payload(instruction=instruction, anchors=ANCHORS, condition=condition, item=item)
            candidate = {"candidate_id": condition, "instruction_sha256": sha256(instruction.encode("utf-8")), "profile_sha256": sha256(profile), "candidate_sha256": sha256({"candidate_id": condition, "instruction_sha256": sha256(instruction.encode("utf-8")), "profile_sha256": sha256(profile)})}
            cells.append({"cell_id": "v15-train-" + sha256({"condition": condition, "item": item["item_id"]})[:20], "ordinal": len(cells) + 1, "condition": condition, **candidate, "item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": "train", "source_binding_sha256": item["source_binding_sha256"], "target": item["target"], "target_sha256": sha256(item["target"]), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    orders = Counter(cells[index]["condition"] for index in range(0, len(cells), 2))
    if len(cells) != 96 or len({row["cell_id"] for row in cells}) != 96 or len({row["item_id"] for row in cells}) != 48 or len({row["prompt_group_id"] for row in cells}) != 24 or orders != Counter({DIRECT: 24, THRESHOLDS: 24}):
        raise ValueError("V15 matched schedule geometry or condition order drifted")
    value: dict[str, Any] = {"format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "grok_primary", "conditions": [DIRECT, THRESHOLDS], "groups": [{"prompt_group_id": group, "partition": "train"} for group in sorted({item["prompt_group_id"] for item in items})], "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"], "anchor_source": anchor_source, "source": {"v13_study_sha256": V13_SHA256}}
    value["schedule_sha256"] = sha256(value)
    return value


def _project_thresholds(value: Mapping[str, Any]) -> int:
    if set(value) != set(THRESHOLD_KEYS) or any(type(value[key]) is not bool for key in THRESHOLD_KEYS):
        raise ValueError("threshold bits are malformed")
    bits = [value[key] for key in THRESHOLD_KEYS]
    if any(right and not left for left, right in pairwise(bits)):
        raise ValueError("threshold bits are nonmonotonic")
    return 1 + sum(bits)


def _validate_answer(condition: str, answer: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, bool], dict[str, Any]]:
    evidence, coverage = answer.get("evidence"), answer.get("coverage")
    if not isinstance(evidence, Mapping) or not isinstance(coverage, Mapping) or set(evidence) != set(DIMS) or set(coverage) != set(DIMS) or any(not isinstance(evidence[name], str) or not evidence[name] or type(coverage[name]) is not bool for name in DIMS):
        raise ValueError("answer evidence or coverage is malformed")
    if condition == DIRECT:
        scores = answer.get("scores")
        if set(answer) != {"scores", "evidence", "coverage"} or not isinstance(scores, Mapping) or set(scores) != set(DIMS) or any(type(scores[name]) is not int or not 1 <= scores[name] <= 5 for name in DIMS):
            raise ValueError("direct 1-5 answer is malformed")
        return {name: float(scores[name]) for name in DIMS}, dict(coverage), {"raw_scores": dict(scores)}
    thresholds = answer.get("thresholds")
    if set(answer) != {"thresholds", "evidence", "coverage"} or not isinstance(thresholds, Mapping) or set(thresholds) != set(DIMS):
        raise ValueError("threshold answer is malformed")
    raw = {name: dict(thresholds[name]) for name in DIMS if isinstance(thresholds[name], Mapping)}
    if set(raw) != set(DIMS):
        raise ValueError("threshold dimension bits are malformed")
    return {name: float(_project_thresholds(raw[name])) for name in DIMS}, dict(coverage), {"raw_threshold_bits": raw}


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    v13 = load(V13, V13_COMMIT, V13_SHA256, "_v15_bound_v13")
    v11 = v13.load(v13.V11, v13.V11_COMMIT, v13.V11_SHA256, "_v15_bound_v11")
    cells = schedule_value.get("cells")
    if not isinstance(cells, list) or len(cells) != 96:
        raise ValueError("V15 schedule payload geometry drifted")
    payloads: set[bytes] = set()
    for row in cells:
        if not isinstance(row, Mapping) or not isinstance(row.get("payload_base64"), str) or not isinstance(row.get("payload_sha256"), str):
            raise TypeError("V15 schedule payload binding drifted")
        raw = base64.b64decode(row["payload_base64"], validate=True)
        if sha256(raw) != row["payload_sha256"]:
            raise ValueError("V15 schedule payload hash drifted")
        payloads.add(raw)
    if len(payloads) != len(cells):
        raise ValueError("V15 schedule payload uniqueness drifted")
    with v11.bound(schedule_value=schedule_value) as (lifecycle, runtime, v9):
        original_study, original_precontact = lifecycle.STUDY_ID, v9._validate_precontact_payload

        def exact_precontact(payload: bytes) -> None:
            if type(payload) is not bytes or payload not in payloads:
                raise ValueError("outbound payload is not an exact frozen V15 payload")

        lifecycle.STUDY_ID, v9._validate_precontact_payload = STUDY_ID, exact_precontact
        try:
            yield lifecycle, runtime, v9, v11, v13
        finally:
            lifecycle.STUDY_ID, v9._validate_precontact_payload = original_study, original_precontact


def _response(helper: Any, raw: bytes, route: Mapping[str, Any], condition: str) -> tuple[dict[str, Any], dict[str, float], dict[str, bool], dict[str, Any]]:
    envelope = helper.strict(raw, "native response", canonical_required=False)
    reported = route.get("reported_model")
    structured = envelope.get("structuredOutput")
    if (set(envelope) != helper.RESPONSE_FIELDS or envelope.get("stopReason") != "end_turn" or envelope.get("num_turns") != 1
            or not isinstance(envelope.get("requestId"), str) or not envelope["requestId"] or not isinstance(envelope.get("sessionId"), str)
            or not envelope["sessionId"] or not isinstance(reported, str) or not isinstance(envelope.get("text"), str)
            or not isinstance(structured, Mapping) or helper.strict(envelope["text"].encode("utf-8"), "native response text", canonical_required=False) != structured):
        raise ValueError("native response identity or structured output drifted")
    usage = envelope.get("usage")
    usage_keys = {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens"}
    if (not isinstance(usage, Mapping) or set(usage) != usage_keys or any(type(usage[key]) is not int or usage[key] < 0 for key in usage_keys)
            or usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0 or usage["total_tokens"] < max(usage["input_tokens"], usage["output_tokens"])):
        raise ValueError("native response usage telemetry drifted")
    model_usage = envelope.get("modelUsage")
    model_keys = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"}
    if (not isinstance(model_usage, Mapping) or set(model_usage) != {reported} or not isinstance(model_usage[reported], Mapping)
            or set(model_usage[reported]) != model_keys or model_usage[reported].get("modelCalls") != 1):
        raise ValueError("native response model usage drifted")
    model = model_usage[reported]
    if any(type(model[key]) is not int or model[key] < 0 for key in model_keys - {"costUSD"}) or model["inputTokens"] <= 0 or model["outputTokens"] <= 0:
        raise ValueError("native response model call telemetry drifted")
    cost, ticks = helper._nonnegative_number(envelope.get("total_cost_usd"), "cost"), envelope.get("total_cost_usd_ticks")
    if (type(ticks) is not int or ticks < 0 or ticks != round(cost * 10_000_000_000)
            or not math.isclose(helper._nonnegative_number(model["costUSD"], "model cost"), cost, rel_tol=0, abs_tol=1e-12)
            or not isinstance(envelope.get("thought"), str)):
        raise ValueError("native response cost or thought telemetry drifted")
    scores, coverage, raw_form = _validate_answer(condition, structured)
    return dict(envelope), scores, coverage, raw_form


def _prepare(*, value: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    with bound(schedule_value=value) as (lifecycle, runtime, v9, _v11, _v13):
        result = lifecycle.prepare_all(output_root=output_root, queue_root=queue_root, authorization_acknowledgement_sha256=acknowledgement, route_provider=v9._validated_route(v9.parent_stack(), runtime, queue_root, route_provider), normalized_root=output_root.parent / ".v15-normalized", materialization_root=output_root.parent / ".v15-materialization", frozen_successor_path=output_root.parent / ".v15-successor.json", hanna_csv_path=output_root.parent / ".v15-source.csv")
    prepared = result.get("prepared_cells", [])
    if len(prepared) != 96 or set(prepared) != {row["cell_id"] for row in value["cells"]} or (output_root / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare the exact V15 96-cell schedule")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 96, "provider_calls_made": 0, "process_launches": 0}


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    return _prepare(value=schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract), output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=route_provider)


def _execute(*, value: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
    row = next((dict(item) for item in value["cells"] if item["cell_id"] == cell_id), None)
    if row is None:
        raise ValueError("unknown V15 cell")
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11, v13):
        reconcile = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v15_response_helper")
        helper = reconcile.helper(); parent = v9.parent_stack()
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)
        def checked(raw: bytes, route: Mapping[str, Any]) -> Any:
            return _response(helper, raw, route, row["condition"])
        return v11._execute_bound(value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=lambda _helper, raw, route: checked(raw, route)), response_helper=helper, selected=selected, output_root=output_root, queue_root=queue_root, authorization_acknowledgement_sha256=acknowledgement, cell_id=cell_id, route_provider=v9._validated_route(parent, runtime, queue_root, route_provider))


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    return _execute(value=schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract), output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=route_provider, runner=runner)


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11, v13):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v15_wave_helper").helper()
        parent = v9.parent_stack()
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)

        async def launch() -> list[dict[str, Any]]:
            route, evidence = v9._validated_route(parent, runtime, Path(queue_root), route_provider)(Path(queue_root))
            gate = asyncio.Semaphore(10)

            async def one(row: Mapping[str, Any]) -> dict[str, Any]:
                def parse(_helper: Any, raw: bytes, receipt_route: Mapping[str, Any], *, condition: str = str(row["condition"])) -> Any:
                    return _response(helper, raw, receipt_route, condition)

                async with gate:
                    return await asyncio.to_thread(
                        v11._execute_bound,
                        value=value,
                        lifecycle=lifecycle,
                        runtime=runtime,
                        v9=v9,
                        reconciler=SimpleNamespace(_response=parse),
                        response_helper=helper,
                        selected=selected,
                        output_root=Path(output_root),
                        queue_root=Path(queue_root),
                        authorization_acknowledgement_sha256=authorization_acknowledgement_sha256,
                        cell_id=str(row["cell_id"]),
                        route_provider=lambda _ignored: (route, evidence),
                    )

            outcomes = await asyncio.gather(*(one(row) for row in value["cells"]), return_exceptions=True)
            failure = next((outcome for outcome in outcomes if isinstance(outcome, BaseException)), None)
            if failure is not None:
                raise failure
            return [outcome for outcome in outcomes if isinstance(outcome, dict)]

        return asyncio.run(launch())


def _mean(values: Sequence[float]) -> float:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("finite numeric values required")
    return sum(values) / len(values)


def _rank(values: Sequence[float]) -> list[float]:
    ordered, ranks = sorted(range(len(values)), key=lambda index: values[index]), [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        for index in ordered[start:end]:
            ranks[index] = (start + 1 + end) / 2
        start = end
    return ranks


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("paired rank values required")
    a, b = _rank(left), _rank(right); mean_a, mean_b = _mean(a), _mean(b)
    variance_a, variance_b = sum((value - mean_a) ** 2 for value in a), sum((value - mean_b) ** 2 for value in b)
    if variance_a == 0 or variance_b == 0:
        return None
    return sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True)) / math.sqrt(variance_a * variance_b)


def _rank_metrics(cells: Sequence[Mapping[str, Any]], groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    items = sorted(cells, key=lambda cell: str(cell["item_id"])); item, group = {}, {}
    for dimension in DIMS:
        item[dimension] = _spearman([float(cell["scores"][dimension]) for cell in items], [float(cell["target"][dimension]) for cell in items])
        grouped = [groups[name] for name in sorted(groups)]
        group[dimension] = _spearman([_mean([float(cell["scores"][dimension]) for cell in rows]) for rows in grouped], [_mean([float(cell["target"][dimension]) for cell in rows]) for rows in grouped])
    return {"item_48": item, "item_48_macro": None if any(value is None for value in item.values()) else _mean([float(value) for value in item.values()]), "group_mean_24": group}


def _pair_accuracy(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dimension in DIMS:
        correct = reversed_pairs = model_ties = eligible = 0
        ordered = sorted(cells, key=lambda cell: str(cell["item_id"]))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                delta = float(left["target"][dimension]) - float(right["target"][dimension])
                if delta == 0:
                    continue
                eligible += 1; predicted = float(left["scores"][dimension]) - float(right["scores"][dimension])
                if predicted == 0: model_ties += 1
                elif predicted * delta > 0: correct += 1
                else: reversed_pairs += 1
        result[dimension] = {"unequal_human_pairs": eligible, "correct_pairs": correct, "reversed_pairs": reversed_pairs, "model_tied_pairs": model_ties, "pair_accuracy": None if not eligible else correct / eligible}
    return result


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract); roots = Path(output_root); expected = {row["cell_id"] for row in value["cells"]}
    if not roots.is_dir() or {path.name for path in roots.iterdir()} != {"schedule.json", ".claims", *expected} or (roots / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("incomplete or ambiguous V15 receipt inventory")
    cells: list[dict[str, Any]] = []; invalid: list[dict[str, str]] = []; threads: set[str] = set(); sessions: set[str] = set()
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {DIRECT: defaultdict(list), THRESHOLDS: defaultdict(list)}
    with bound(schedule_value=value) as (lifecycle, _runtime, v9, _v11, v13):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v15_report_helper").helper(); source = lifecycle.live(); parent = v9.parent_stack(); v9._validate_claims(roots, expected)
        frozen_route: Mapping[str, Any] | None = None; frozen_evidence: Mapping[str, Any] | None = None
        for row in value["cells"]:
            root = roots / row["cell_id"]
            try:
                stored = v9.strict(v9.stable(root / "prepared.json"), "prepared")
                acknowledgement = v9.strict(v9.stable(root / "authorization-acknowledgement.json"), "acknowledgement")
                if acknowledgement.get("acknowledgement_sha256") != authorization_acknowledgement_sha256:
                    raise ValueError("receipt acknowledgement drifted")
                route, evidence = stored.get("route"), stored.get("route_evidence")
                if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
                    raise TypeError("receipt route evidence is malformed")
                if frozen_route is None:
                    frozen_route, frozen_evidence = route, evidence
                elif route != frozen_route or evidence != frozen_evidence:
                    raise ValueError("mixed receipt route or evidence")
                raw, prompt, schema = lifecycle.payload(row); _request, response, identity, settings = lifecycle.admit(root, row, value, raw, prompt, schema, route, evidence, authorization_acknowledgement_sha256, source)
                _envelope, scores, coverage, raw_form = _response(helper, response, route, row["condition"])
                thread, session = identity.get("request_id"), identity.get("session_id")
                if not isinstance(thread, str) or not thread or not isinstance(session, str) or not session or thread in threads or session in sessions:
                    raise ValueError("duplicate or missing native identity")
                threads.add(thread); sessions.add(session)
                cell = {"cell_id": row["cell_id"], "condition": row["condition"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "payload_sha256": row["payload_sha256"], "native_response_sha256": sha256(response), "effective_settings_sha256": sha256(settings), "scores": scores, "coverage": coverage, "target": dict(row["target"]), **raw_form}
                cell["per_item_mae"] = _mean([abs(scores[name] - float(row["target"][name])) for name in DIMS]); cells.append(cell); grouped[row["condition"]][row["prompt_group_id"]].append(cell)
            except (TypeError, ValueError) as error:
                invalid.append({"cell_id": str(row["cell_id"]), "condition": str(row["condition"]), "reason": str(error)})
    if invalid:
        return {"format_version": 1, "study_id": STUDY_ID, "status": "invalid_or_incomplete_no_full_panel_claim", "invalid_count": len(invalid), "invalid_cells": invalid, "valid_cell_count": len(cells)}
    if frozen_route is None or frozen_evidence is None:
        raise ValueError("missing V15 common route evidence")
    lifecycle.validate_frozen_route(frozen_route, frozen_evidence)
    parent._validate_route_evidence(frozen_route, frozen_evidence)
    if len(cells) != 96 or len(threads) != 96 or len(sessions) != 96:
        raise ValueError("V15 complete receipt geometry drifted")
    metrics: dict[str, Any] = {}; ranks: dict[str, Any] = {}; occupancy: dict[str, Any] = {}; coverage_counts: dict[str, Any] = {}
    groups = sorted({row["prompt_group_id"] for row in value["cells"]})
    expected_items = {
        condition: {
            group: {row["item_id"] for row in value["cells"] if row["condition"] == condition and row["prompt_group_id"] == group}
            for group in groups
        }
        for condition in (DIRECT, THRESHOLDS)
    }
    if expected_items[DIRECT] != expected_items[THRESHOLDS] or any(not item_ids for item_ids in expected_items[DIRECT].values()):
        raise ValueError("V15 schedule does not preserve matched per-group item identities")
    for condition in (DIRECT, THRESHOLDS):
        by_group = grouped[condition]
        if set(by_group) != set(groups) or any(
            {cell["item_id"] for cell in by_group[group]} != expected_items[condition][group]
            or len(by_group[group]) != len(expected_items[condition][group])
            for group in groups
        ):
            raise ValueError("V15 condition does not retain the scheduled per-group items")
        rows = [cell for group in groups for cell in by_group[group]]
        group_mae = {group: _mean([cell["per_item_mae"] for cell in by_group[group]]) for group in groups}
        fixed = {group: _mean([_mean([abs(3.0 - float(cell["target"][name])) for name in DIMS]) for cell in by_group[group]]) for group in groups}
        metrics[condition] = {"per_group_mean_item_mae": group_mae, "equal_group_mean_item_mae": _mean(list(group_mae.values())), "fixed_three_equal_group_mae": _mean(list(fixed.values())), "item_count": 48, "group_count": 24, "pair_accuracy": _pair_accuracy(rows)}
        ranks[condition] = _rank_metrics(rows, by_group)
        occupancy[condition] = {dimension: dict(sorted(Counter(int(cell["scores"][dimension]) for cell in rows).items())) for dimension in DIMS}
        coverage_counts[condition] = {dimension: {"true": sum(cell["coverage"][dimension] for cell in rows), "false": sum(not cell["coverage"][dimension] for cell in rows)} for dimension in DIMS}
    return {"format_version": 1, "study_id": STUDY_ID, "kind": contract()["kind"], "status": "complete_matched_96_cells", "endpoint": "grok_primary", "cells": cells, "metrics": metrics, "rank_metrics": ranks, "score_occupancy": occupancy, "coverage_counts": coverage_counts, "invalid_count": 0, "unique_request_ids": len(threads), "unique_session_ids": len(sessions), "authority": contract()["authority"], "interpretation": "TRAIN_only_development_measurement; no_selection_promotion_confirmation_or_endpoint_pooling"}
