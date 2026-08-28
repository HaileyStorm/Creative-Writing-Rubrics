#!/usr/bin/env python3
"""Provider-free freezer, disclosure builder, and validator for revision-gain v1."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.runner import _question_payload

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
INITIAL_ACKNOWLEDGEMENT = "acknowledgement.json"
ENDPOINT_ACKNOWLEDGEMENT = "endpoint-acknowledgement.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _reject_reparse_ancestors(path: Path) -> None:
    candidate = path.absolute()
    while True:
        try:
            attributes = getattr(candidate.stat(), "st_file_attributes", 0)
        except OSError:
            attributes = 0
        if candidate.is_symlink() or attributes & 0x400:
            raise ValueError(f"Reparse point is not allowed in immutable artifact path: {candidate}")
        parent = candidate.parent
        if parent == candidate:
            return
        candidate = parent


def _read_bytes(path: Path, *, label: str) -> bytes:
    _reject_reparse_ancestors(path)
    if not path.is_file():
        raise ValueError(f"Missing immutable {label}: {path}")
    return path.read_bytes()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_bytes(path, label=label).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Immutable {label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"Immutable {label} is not an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(_read_bytes(path, label="artifact")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    _reject_reparse_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def write_jsonl(path: Path, records: list[Mapping[str, Any]]) -> None:
    _reject_reparse_ancestors(path)
    if path.exists():
        raise ValueError(f"Refusing to overwrite immutable lineage manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(canonical(dict(record)) + b"\n" for record in records))


def _write_immutable_bytes(path: Path, payload: bytes, *, label: str) -> None:
    _reject_reparse_ancestors(path)
    if path.exists():
        raise ValueError(f"Refusing to overwrite immutable {label}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse_ancestors(path)
    path.write_bytes(payload)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _read_bytes(path, label="lineage manifest")
    if not raw:
        raise ValueError("Immutable lineage manifest is missing or empty")
    try:
        records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Immutable lineage manifest is not JSONL") from error
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Immutable lineage manifest record is not an object")
    return records


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _artifact(root: Path, commitment: Mapping[str, Any], *, field: str) -> str:
    relative = commitment.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise ValueError(f"Lineage {field} path is unsafe")
    path = root.joinpath(*Path(relative).parts)
    payload = _read_bytes(path, label=f"lineage {field} artifact")
    if commitment.get("bytes") != len(payload) or commitment.get("sha256") != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"Lineage {field} artifact binding drifted")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Lineage {field} artifact is not UTF-8 text") from error


def _committed_bytes(root: Path, commitment: Any, *, field: str) -> bytes:
    if not isinstance(commitment, Mapping) or set(commitment) != {"path", "bytes", "sha256"}:
        raise ValueError(f"Provider receipt {field} commitment drifted")
    relative = commitment["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise ValueError(f"Provider receipt {field} path is unsafe")
    payload = _read_bytes(root.joinpath(*Path(relative).parts), label=f"provider receipt {field}")
    if commitment["bytes"] != len(payload) or commitment["sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"Provider receipt {field} commitment drifted")
    return payload


def _canonical_receipt_object(root: Path, commitment: Any, *, field: str) -> dict[str, Any]:
    payload = _committed_bytes(root, commitment, field=field)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Provider receipt {field} is not canonical JSON") from error
    if not isinstance(value, dict) or canonical(value) != payload:
        raise ValueError(f"Provider receipt {field} is not a canonical JSON object")
    return value


def fingerprint(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read_bytes(path, label=f"external input {label}")
    return {"path": label, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def _binding(path: Path, expected: Mapping[str, Any]) -> None:
    payload = _read_bytes(path, label="frozen asset")
    if len(payload) != expected.get("bytes") or hashlib.sha256(payload).hexdigest() != expected.get("sha256"):
        raise ValueError(f"Frozen asset binding drifted: {path.as_posix()}")


def _asset_binding(value: Mapping[str, Any]) -> None:
    path = HERE / str(value.get("path", ""))
    _binding(path, value)


def _committed_asset(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return one validated tracked asset commitment without widening its path."""
    _asset_binding(value)
    return {"path": value["path"], "bytes": value["bytes"], "sha256": value["sha256"]}


def _validate_feedback_schema(asset: Mapping[str, Any]) -> None:
    schema = _read_json(HERE / asset["path"], label="CWR feedback schema")
    findings = schema.get("properties", {}).get("findings") if isinstance(schema.get("properties"), Mapping) else None
    item = findings.get("items") if isinstance(findings, Mapping) else None
    fields = item.get("properties") if isinstance(item, Mapping) else None
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or schema.get("required") != ["findings"]
        or not isinstance(schema.get("properties"), Mapping)
        or set(schema["properties"]) != {"findings"}
        or not isinstance(findings, Mapping)
        or findings.get("type") != "array"
        or findings.get("maxItems") != 3
        or not isinstance(item, Mapping)
        or item.get("type") != "object"
        or item.get("additionalProperties") is not False
        or item.get("required") != ["location", "observation", "repair_target"]
        or not isinstance(fields, Mapping)
        or set(fields) != {"location", "observation", "repair_target"}
        or any(not isinstance(fields[name], Mapping) or fields[name].get("type") != "string" or fields[name].get("minLength") != 1 for name in fields)
        or _has_binary_verdict_field(schema)
    ):
        raise ValueError("Revision-gain feedback schema must define exact findings rather than binary verdicts")


def _has_binary_verdict_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in {"verdict", "binary", "pass_answer"} or _has_binary_verdict_field(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_has_binary_verdict_field(item) for item in value)
    return False


def _cwr_runtime_composition(value: Mapping[str, Any]) -> dict[str, Any]:
    """Compile the pinned short-story bundle into the exact feedback question payload."""
    runtime = value["cwr_runtime"]
    files = runtime["files"]
    for relative, expected in files.items():
        _binding(REPOSITORY / str(relative), expected)
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundles = load_bundles(REPOSITORY / "bundles" / "all_bundles.json")
    bundle = resolve_bundle(bundles, runtime["bundle_id"])
    compiled = compile_bundle(modules, bundle)
    questions = _question_payload(compiled_questions(compiled))
    if len(questions) != 178:
        raise ValueError("CWR feedback composition requires exactly 178 short-story questions")
    bundle_bytes, compiled_bytes, question_bytes = canonical(bundle), canonical(compiled), canonical(questions)
    return {
        "runtime_files": [
            {"path": relative, **dict(files[relative])}
            for relative in sorted(files)
        ],
        "bundle": {
            "bundle_id": runtime["bundle_id"],
            "bytes": len(bundle_bytes),
            "sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        },
        "compiled_bundle": {
            "bytes": len(compiled_bytes),
            "sha256": hashlib.sha256(compiled_bytes).hexdigest(),
        },
        "ordered_question_payload": {
            "count": len(questions),
            "bytes": len(question_bytes),
            "sha256": hashlib.sha256(question_bytes).hexdigest(),
        },
        "questions": questions,
    }


def _input_ids(value: Mapping[str, Any]) -> list[str]:
    inputs = value["source_population"].get("input_commitments")
    if not isinstance(inputs, Mapping):
        raise ValueError("Revision-gain input commitments are missing")
    return sorted(str(item_id) for item_id in inputs)


def contract() -> dict[str, Any]:
    value = _read_json(CONTRACT_PATH, label="study contract")
    source = value.get("source_population")
    cycles = value.get("cycles")
    generation = value.get("generation")
    endpoint = value.get("endpoint_evaluation")
    routes = value.get("provider_routes")
    if value.get("format_version") != 2 or value.get("study_id") != "cwr-guided-revision-gain-v1" or value.get("frozen_before_execution") is not True:
        raise ValueError("Revision-gain contract identity drifted")
    if not all(isinstance(part, Mapping) for part in (source, cycles, generation, endpoint, routes)):
        raise ValueError("Revision-gain contract sections are missing")
    eligible = _input_ids(value)
    pilot, held = source.get("pilot_item_ids"), source.get("held_back_item_ids")
    if not isinstance(pilot, list) or not isinstance(held, list) or sorted(eligible)[:6] != pilot or sorted(eligible)[6:] != held:
        raise ValueError("Revision-gain source selection is not the frozen lexical six-plus-four split")
    if len(eligible) != 10 or set(pilot) & set(held) or set(pilot) | set(held) != set(eligible):
        raise ValueError("Revision-gain source population is not the exact ten generated HANNA items")
    if not isinstance(source.get("parent_frozen_run_contract_sha256"), str) or len(source["parent_frozen_run_contract_sha256"]) != 64:
        raise ValueError("Revision-gain parent contract binding drifted")
    if cycles.get("second_cycle_item_ids") != pilot[:2] or cycles.get("adaptive_extension") or cycles.get("best_of_n"):
        raise ValueError("Revision-gain cycle policy drifted")
    if routes != {
        "grok-4.6-high": {"destination": "xai_grok_build_subscription", "model": "grok-4.6", "reasoning": "high", "paid_api": False},
        "gpt-5.6-sol-high": {"destination": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "paid_api": False},
        "deepseek-v4-flash-max": {"destination": "nous", "model": "deepseek/deepseek-v4-flash-0731", "reasoning": "max", "paid_api": False},
        "gpt-5.6-luna-xhigh": {"destination": "codex", "model": "gpt-5.6-luna", "reasoning": "xhigh", "paid_api": False},
    }:
        raise ValueError("Revision-gain provider route identity or zero-spend policy drifted")
    route_values = generation.get("generator_routes")
    if not isinstance(route_values, list) or [route.get("generator_id") for route in route_values if isinstance(route, Mapping)] != ["grok-4.6", "gpt-5.6-sol", "deepseek-v4-flash", "gpt-5.6-luna"]:
        raise ValueError("Revision-gain generator routes drifted")
    if [item.get("arm_id") for item in generation.get("guidance_arms", []) if isinstance(item, Mapping)] != ["cwr_guided", "generic_no_feedback"]:
        raise ValueError("Revision-gain guidance arms drifted")
    _asset_binding(generation["instruction_asset"])
    feedback_instrument = generation.get("feedback_instrument")
    if not isinstance(feedback_instrument, Mapping) or set(feedback_instrument) != {"prompt", "schema"}:
        raise ValueError("Revision-gain feedback instrument binding drifted")
    for asset in feedback_instrument.values():
        if not isinstance(asset, Mapping):
            raise ValueError("Revision-gain feedback instrument asset drifted")
        _asset_binding(asset)
    _validate_feedback_schema(feedback_instrument["schema"])
    instructions = _read_json(HERE / generation["instruction_asset"]["path"], label="revision instruction asset")
    feedback_packet = instructions.get("cwr_feedback_packet")
    if set(instructions) != {"format_version", "cwr_feedback_packet", "neutral_base_revision_instruction", "arm_difference"} or instructions.get("format_version") != 1 or not isinstance(feedback_packet, Mapping) or feedback_packet.get("maximum_findings") != 3 or feedback_packet.get("maximum_words") != 360 or feedback_packet.get("required_fields_per_finding") != ["location", "observation", "repair_target"] or not isinstance(feedback_packet.get("instruction"), str) or not feedback_packet["instruction"] or not isinstance(instructions["neutral_base_revision_instruction"], str) or not instructions["neutral_base_revision_instruction"] or instructions["arm_difference"] != {
        "cwr_guided": "Append the frozen CWR feedback packet after the identical neutral base revision instruction.",
        "generic_no_feedback": "Do not append a feedback packet after the identical neutral base revision instruction.",
    }:
        raise ValueError("Revision-gain arms must share one neutral base instruction")
    runtime = value.get("cwr_runtime", {}).get("files") if isinstance(value.get("cwr_runtime"), Mapping) else None
    if not isinstance(runtime, Mapping) or len(runtime) != 7:
        raise ValueError("Revision-gain CWR runtime binding drifted")
    for relative, expected in runtime.items():
        _binding(REPOSITORY / str(relative), expected)
    if endpoint.get("non_cwr_primary") is not True or endpoint.get("judges") != ["gpt-5.6-sol-high", "grok-4.6-high"] or endpoint.get("judging_protocol") != {"blind": True, "stateless": True, "identical_prompt_per_measure_across_judges": True}:
        raise ValueError("Revision-gain endpoint role drifted")
    measures = endpoint.get("measures")
    if not isinstance(measures, list) or [measure.get("measure_id") for measure in measures if isinstance(measure, Mapping)] != ["holistic_anchored", "compact_analytic"]:
        raise ValueError("Revision-gain endpoint measures drifted")
    for measure in measures:
        if measure.get("scalar_field") != "overall" or not isinstance(measure.get("minimum"), int) or not isinstance(measure.get("maximum"), int) or measure["minimum"] >= measure["maximum"]:
            raise ValueError("Revision-gain endpoint scalar binding drifted")
        _asset_binding(measure["prompt"])
        _asset_binding(measure["schema"])
    geometry = value.get("execution_geometry")
    if geometry != {"revision_descendants": 48, "source_baselines": 6, "endpoint_judges": 2, "endpoint_measures": 2, "endpoint_provider_calls": 216, "formula": "(48 descendants + 6 baselines) x 2 judges x 2 measures"}:
        raise ValueError("Revision-gain fixed execution geometry drifted")
    disclosure = value.get("remote_disclosure")
    expected_phase_payloads = {
        "cwr_feedback": ["one immutable source or parent descendant", "frozen CWR feedback instruction", "pinned CWR runtime"],
        "revision_generation": ["one immutable source or parent descendant", "one identical neutral base revision instruction", "frozen CWR feedback only for guided cells"],
        "blind_endpoint_judgment": ["one blinded target artifact", "one frozen endpoint prompt", "one frozen response schema"],
    }
    if not isinstance(disclosure, Mapping) or disclosure.get("phase_call_counts") != {"cwr_feedback": 24, "revision_generation": 48, "blind_endpoint_judgment": 216} or disclosure.get("payload_composition") != expected_phase_payloads:
        raise ValueError("Revision-gain phase disclosure geometry drifted")
    reporting = value.get("reporting")
    if not isinstance(reporting, Mapping) or reporting.get("raw_scale_pooling") is not False or reporting.get("equal_weight_unit") != "source_generator_cycle_within_each_judge_measure_scale" or reporting.get("summaries") != ["mean guided-minus-control by judge x measure x scale", "positive-zero-negative directional consistency by judge x measure x scale", "raw paired rows retained; this small development pilot does not estimate an uncertainty interval"] or reporting.get("cycle2_label") != "cumulative_from_cycle1_parent" or reporting.get("secondary_endpoint_delta") != "cycle2 child-minus-cycle1-parent by guidance arm x judge x measure x scale":
        raise ValueError("Revision-gain reporting contract drifted")
    if value.get("execution_status") != {"cwr_feedback": "composition_ready_provider_free", "promotion_requires": ["exact_cwr_composition_manifest", "owner_bound_disclosure_acknowledgement", "provider_native_transport_receipt"]}:
        raise ValueError("Revision-gain execution status contract drifted")
    return value


def _revision_event_id(cycle: int, item_id: str, generator_id: str, guidance_arm: str) -> str:
    return f"revision-v1-c{cycle}-{item_id}-{generator_id}-{guidance_arm}"


def revision_schedule(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else dict(value)
    source, cycles, generation = value["source_population"], value["cycles"], value["generation"]
    arms = [item["arm_id"] for item in generation["guidance_arms"]]
    events: list[dict[str, Any]] = []
    for cycle, item_ids in ((1, source["pilot_item_ids"]), (2, cycles["second_cycle_item_ids"])):
        for item_id in item_ids:
            for route in generation["generator_routes"]:
                if item_id not in route.get("item_ids", source["pilot_item_ids"]) or cycle not in route["cycles"]:
                    continue
                for guidance_arm in arms:
                    event_id = _revision_event_id(cycle, item_id, route["generator_id"], guidance_arm)
                    event = {
                        "event_id": event_id,
                        "cycle": cycle,
                        "source_item_id": item_id,
                        "generator_id": route["generator_id"],
                        "generator_tier": route["tier"],
                        "generator_route_id": route["route_id"],
                        "cwr_feedback_route_id": route["cwr_feedback_route_id"],
                        "guidance_arm": guidance_arm,
                    }
                    if cycle == 2:
                        event["parent_event_id"] = _revision_event_id(1, item_id, route["generator_id"], guidance_arm)
                    events.append(event)
    if len(events) != 48 or len({event["event_id"] for event in events}) != 48:
        raise ValueError("Revision-gain schedule must contain exactly 48 unique predeclared cells")
    known = {event["event_id"] for event in events}
    if any(event.get("parent_event_id") not in known for event in events if event["cycle"] == 2):
        raise ValueError("Revision-gain second-cycle parent binding drifted")
    return events


def _targets(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    baselines = [{"target_event_id": f"baseline-v1-{item_id}", "target_kind": "baseline", "source_item_id": item_id} for item_id in value["source_population"]["pilot_item_ids"]]
    descendants = [{"target_event_id": event["event_id"], "target_kind": "descendant", "source_item_id": event["source_item_id"], "revision": event} for event in revision_schedule(value)]
    targets = baselines + descendants
    ordered = sorted(targets, key=lambda target: hashlib.sha256(f"{value['endpoint_evaluation']['endpoint_order']['seed']}:{target['target_event_id']}".encode("utf-8")).hexdigest())
    for index, target in enumerate(ordered, 1):
        target["blind_target_id"] = f"blind-target-{index:03d}"
    return ordered


def endpoint_schedule(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else dict(value)
    conditions = [(judge, measure["measure_id"]) for judge in value["endpoint_evaluation"]["judges"] for measure in value["endpoint_evaluation"]["measures"]]
    events: list[dict[str, Any]] = []
    for index, target in enumerate(_targets(value)):
        for judge, measure_id in conditions[index % len(conditions):] + conditions[:index % len(conditions)]:
            events.append({"blind_target_id": target["blind_target_id"], "endpoint_event_id": f"endpoint-v1-{target['blind_target_id']}-{judge}-{measure_id}", "judge_route_id": judge, "measure_id": measure_id})
    for index, event in enumerate(events, 1):
        event["dispatch_order"] = index
    if len(events) != 216 or len({event["endpoint_event_id"] for event in events}) != 216:
        raise ValueError("Revision-gain endpoint schedule must contain exactly 216 calls")
    if {event["blind_target_id"] for event in events} != {target["blind_target_id"] for target in _targets(value)}:
        raise ValueError("Revision-gain endpoint blinding schedule drifted")
    return events


def _expected_input(item_id: str, name: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = value["source_population"]["input_commitments"][item_id].get(name)
    if not isinstance(expected, Mapping):
        raise ValueError("Revision-gain input commitment is malformed")
    return expected


def freeze_inputs(source_root: Path, work_root: Path) -> dict[str, Any]:
    """Freeze exact external HANNA fingerprints without copying source prose."""
    value = contract()
    target = work_root / "frozen-inputs.json"
    if target.exists():
        raise ValueError("Refusing to overwrite frozen revision-gain inputs")
    inputs: list[dict[str, Any]] = []
    for item_id in _input_ids(value):
        relative = Path("inputs") / item_id
        source = fingerprint(source_root / relative / "source.md", label=(relative / "source.md").as_posix())
        prompt = fingerprint(source_root / relative / "prompt.md", label=(relative / "prompt.md").as_posix())
        for name, actual in (("source.md", source), ("prompt.md", prompt)):
            expected = _expected_input(item_id, name, value)
            if {key: actual[key] for key in ("bytes", "sha256")} != dict(expected):
                raise ValueError(f"Frozen HANNA {name} binding drifted: {item_id}")
        inputs.append({"item_id": item_id, "source": source, "prompt": prompt})
    revisions = revision_schedule(value)
    endpoints = endpoint_schedule(value)
    frozen = {
        "study_id": value["study_id"],
        "study_contract_sha256": sha256(CONTRACT_PATH),
        "parent_frozen_run_contract_sha256": value["source_population"]["parent_frozen_run_contract_sha256"],
        "source_root_not_persisted": True,
        "source_material_copied": False,
        "inputs": inputs,
        "revision_schedule": revisions,
        "revision_schedule_sha256": hashlib.sha256(canonical(revisions)).hexdigest(),
        "endpoint_schedule": endpoints,
        "endpoint_schedule_sha256": hashlib.sha256(canonical(endpoints)).hexdigest(),
    }
    write_json(target, frozen)
    return frozen


def validate_frozen_inputs(work_root: Path) -> dict[str, Any]:
    value = contract()
    path = work_root / "frozen-inputs.json"
    if not path.is_file():
        raise ValueError("Frozen revision-gain inputs are missing")
    frozen = _read_json(path, label="frozen inputs")
    required = {"study_id", "study_contract_sha256", "parent_frozen_run_contract_sha256", "source_root_not_persisted", "source_material_copied", "inputs", "revision_schedule", "revision_schedule_sha256", "endpoint_schedule", "endpoint_schedule_sha256"}
    if set(frozen) != required or frozen.get("study_id") != value["study_id"] or frozen.get("study_contract_sha256") != sha256(CONTRACT_PATH) or frozen.get("parent_frozen_run_contract_sha256") != value["source_population"]["parent_frozen_run_contract_sha256"]:
        raise ValueError("Frozen revision-gain contract binding drifted")
    if frozen.get("source_root_not_persisted") is not True or frozen.get("source_material_copied") is not False:
        raise ValueError("Frozen revision-gain source privacy policy drifted")
    inputs = frozen.get("inputs")
    if not isinstance(inputs, list) or [row.get("item_id") for row in inputs if isinstance(row, Mapping)] != _input_ids(value):
        raise ValueError("Frozen revision-gain input IDs drifted")
    for row in inputs:
        item_id = row.get("item_id") if isinstance(row, Mapping) else None
        if not isinstance(row, Mapping) or set(row) != {"item_id", "source", "prompt"} or not isinstance(item_id, str):
            raise ValueError("Frozen revision-gain input row schema drifted")
        for file_name, key in (("source.md", "source"), ("prompt.md", "prompt")):
            actual = row.get(key)
            expected = _expected_input(item_id, file_name, value)
            if not isinstance(actual, Mapping) or set(actual) != {"path", "bytes", "sha256"} or actual.get("path") != f"inputs/{item_id}/{file_name}" or {name: actual.get(name) for name in ("bytes", "sha256")} != expected:
                raise ValueError("Frozen revision-gain input fingerprint drifted")
    revisions, endpoints = revision_schedule(value), endpoint_schedule(value)
    if frozen.get("revision_schedule") != revisions or frozen.get("revision_schedule_sha256") != hashlib.sha256(canonical(revisions)).hexdigest():
        raise ValueError("Frozen revision-gain revision schedule drifted")
    if frozen.get("endpoint_schedule") != endpoints or frozen.get("endpoint_schedule_sha256") != hashlib.sha256(canonical(endpoints)).hexdigest():
        raise ValueError("Frozen revision-gain endpoint schedule drifted")
    return frozen


def disclosure_preview(work_root: Path) -> dict[str, Any]:
    """Build an exact no-prose preview for a later, separately authorized run."""
    frozen = validate_frozen_inputs(work_root)
    value = contract()
    route_ids = {route["route_id"] for route in value["generation"]["generator_routes"]} | {route["cwr_feedback_route_id"] for route in value["generation"]["generator_routes"]} | set(value["endpoint_evaluation"]["judges"])
    roles = {
        "cwr_feedback": sorted({route["cwr_feedback_route_id"] for route in value["generation"]["generator_routes"]}),
        "revision_generation": sorted({route["route_id"] for route in value["generation"]["generator_routes"]}),
        "blind_endpoint_judgment": value["endpoint_evaluation"]["judges"],
    }
    return {
        "study_id": value["study_id"],
        "provider_calls_made": 0,
        "contract_sha256": sha256(CONTRACT_PATH),
        "parent_frozen_run_contract_sha256": frozen["parent_frozen_run_contract_sha256"],
        "destinations": {route_id: value["provider_routes"][route_id] for route_id in sorted(route_ids)},
        "role_routes": roles,
        "phases": {
            role: {"call_count": value["remote_disclosure"]["phase_call_counts"][role], "payload_composition": value["remote_disclosure"]["payload_composition"][role]}
            for role in value["remote_disclosure"]["destination_roles"]
        },
        "input_commitments": frozen["inputs"],
        "instruction_asset": value["generation"]["instruction_asset"],
        "cwr_runtime": value["cwr_runtime"],
        "endpoint_measures": value["endpoint_evaluation"]["measures"],
        "revision_schedule_sha256": frozen["revision_schedule_sha256"],
        "endpoint_schedule_sha256": frozen["endpoint_schedule_sha256"],
        "acknowledgement_required": True,
    }


def write_disclosure_preview(work_root: Path) -> dict[str, Any]:
    preview = disclosure_preview(work_root)
    preview_path = work_root / "disclosure-preview.json"
    hash_path = work_root / "disclosure-preview.canonical.sha256"
    if preview_path.exists() or hash_path.exists():
        raise ValueError("Refusing to overwrite immutable disclosure preview")
    write_json(preview_path, preview)
    _write_immutable_bytes(hash_path, (hashlib.sha256(canonical(preview)).hexdigest() + "\n").encode("ascii"), label="disclosure hash")
    return preview


def validate_disclosure_acknowledgement(work_root: Path, acknowledgement_path: Path) -> dict[str, Any]:
    preview = disclosure_preview(work_root)
    preview_path = work_root / "disclosure-preview.json"
    hash_path = work_root / "disclosure-preview.canonical.sha256"
    preview_sha = hashlib.sha256(canonical(preview)).hexdigest()
    if _read_json(preview_path, label="disclosure preview") != preview or _read_bytes(hash_path, label="disclosure hash").decode("ascii") != preview_sha + "\n":
        raise ValueError("Revision-gain disclosure preview binding drifted")
    if not acknowledgement_path.is_file():
        raise ValueError("Revision-gain disclosure acknowledgement is missing")
    acknowledgement = _read_json(acknowledgement_path, label="disclosure acknowledgement")
    required = {"study_id", "preview_sha256", "acknowledged", "acknowledged_at"}
    if set(acknowledgement) != required or acknowledgement.get("study_id") != preview["study_id"] or acknowledgement.get("preview_sha256") != preview_sha or acknowledgement.get("acknowledged") is not True or not isinstance(acknowledgement.get("acknowledged_at"), str) or not acknowledgement["acknowledged_at"]:
        raise ValueError("Revision-gain disclosure acknowledgement binding drifted")
    return acknowledgement


def _route_identity(value: Mapping[str, Any], route_id: str) -> dict[str, Any]:
    route = value["provider_routes"].get(route_id)
    if not isinstance(route, Mapping):
        raise ValueError("Lineage route is not predeclared")
    return {"route_id": route_id, **dict(route)}


def _sha256_string(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_sampler(sampler: Any) -> None:
    if not isinstance(sampler, Mapping) or set(sampler) != {"temperature", "top_p", "seed", "max_output_tokens"}:
        raise ValueError("Provider sampler schema drifted")
    temperature, top_p, seed, maximum = sampler["temperature"], sampler["top_p"], sampler["seed"], sampler["max_output_tokens"]
    if any(isinstance(item, bool) for item in (temperature, top_p, seed, maximum)) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2 or not isinstance(top_p, (int, float)) or not 0 < top_p <= 1 or not isinstance(seed, int) or seed < 0 or not isinstance(maximum, int) or maximum < 1:
        raise ValueError("Provider sampler values drifted")


def _require_trusted_native_provenance(_receipt: Mapping[str, Any]) -> None:
    raise ValueError(
        "Provider-native acceptance is non-promotable without a trusted executor, adapter/parser "
        "commitment, and immutable provider-generated raw receipt/session artifacts"
    )


def _validate_receipt(work_root: Path, receipt: Any) -> dict[str, Any]:
    hashes = ("request_sha256", "payload_sha256", "response_sha256")
    fields = {"provider_request_id", "route_intent_profile", "request", "payload", "response", "native", *hashes}
    if not isinstance(receipt, Mapping) or set(receipt) != fields or not isinstance(receipt.get("provider_request_id"), str) or not receipt["provider_request_id"] or not all(_sha256_string(receipt.get(name)) for name in hashes):
        raise ValueError("Provider receipt or request/payload/response hash drifted")
    for field, digest in (("request", "request_sha256"), ("payload", "payload_sha256"), ("response", "response_sha256")):
        payload = _committed_bytes(work_root, receipt[field], field=field)
        if hashlib.sha256(payload).hexdigest() != receipt[digest]:
            raise ValueError("Provider receipt or request/payload/response hash drifted")
    _canonical_receipt_object(work_root, receipt["route_intent_profile"], field="route intent profile")
    _canonical_receipt_object(work_root, receipt["request"], field="request")
    _canonical_receipt_object(work_root, receipt["payload"], field="payload")
    native = receipt["native"]
    native_fields = {"accepted", "status", "model", "reasoning", "session_id", "provider_request_id", "transmitted_payload_sha256", "returned_response_sha256"}
    if not isinstance(native, Mapping) or set(native) != native_fields or native.get("accepted") is not True or not isinstance(native.get("status"), int) or not 200 <= native["status"] < 300 or not all(isinstance(native.get(field), str) and native[field] for field in ("model", "reasoning", "session_id", "provider_request_id")) or native["provider_request_id"] != receipt["provider_request_id"] or native.get("transmitted_payload_sha256") != receipt["payload_sha256"] or native.get("returned_response_sha256") != receipt["response_sha256"]:
        raise ValueError("Provider native receipt acceptance binding drifted")
    _require_trusted_native_provenance(receipt)
    return dict(receipt)


def _validate_execution_identity(work_root: Path, identity: Any, expected: Mapping[str, Any], *, role_key: str, role_value: str, event_id: str, payload: Mapping[str, Any], evidence_field: str = "provider_ready") -> tuple[dict[str, Any], Any]:
    required = set(expected) | {role_key, "sampler", "receipt"}
    if not isinstance(identity, Mapping) or set(identity) != required or {key: identity.get(key) for key in expected} != dict(expected) or identity.get(role_key) != role_value:
        raise ValueError("Provider identity drifted")
    _validate_sampler(identity["sampler"])
    receipt = _validate_receipt(work_root, identity["receipt"])
    route = {key: expected[key] for key in ("route_id", "destination", "model", "reasoning", "paid_api")}
    request = _canonical_receipt_object(work_root, receipt["request"], field="request")
    expected_request = {"event_id": event_id, "role": role_value, "route": route, "sampler": dict(identity["sampler"])}
    if request != expected_request:
        raise ValueError("Provider request semantic binding drifted")
    expected_payload = {"event_id": event_id, "role": role_value, "request_sha256": receipt["request_sha256"], **dict(payload)}
    actual_payload = _canonical_receipt_object(work_root, receipt["payload"], field="payload")
    if set(actual_payload) != set(expected_payload) | {evidence_field} or {key: actual_payload[key] for key in expected_payload} != expected_payload:
        raise ValueError("Provider payload semantic binding drifted")
    if _canonical_receipt_object(work_root, receipt["route_intent_profile"], field="route intent profile") != route:
        raise ValueError("Provider route intent profile drifted")
    native = receipt["native"]
    if native["model"] != route["model"] or native["reasoning"] != route["reasoning"]:
        raise ValueError("Provider native accepted model or reasoning drifted")
    return receipt, actual_payload[evidence_field]


def _register_receipt(receipt: Mapping[str, Any], seen: dict[str, set[str]], *, unique_response: bool) -> None:
    required = ("provider_request_id", "request_sha256", "payload_sha256") + (("response_sha256",) if unique_response else ())
    for key in required:
        if receipt[key] in seen[key]:
            raise ValueError(f"Provider receipt {key} must be globally unique where semantically required")
        seen[key].add(receipt[key])


def _validate_feedback_packet(payload: bytes, instructions: Mapping[str, Any]) -> None:
    try:
        packet = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Guided feedback packet is not canonical JSON") from error
    policy = instructions["cwr_feedback_packet"]
    if not isinstance(packet, dict) or canonical(packet) != payload or set(packet) != {"findings"} or not isinstance(packet["findings"], list) or len(packet["findings"]) > policy["maximum_findings"] or len(payload.decode("utf-8").split()) > policy["maximum_words"]:
        raise ValueError("Guided feedback packet shape or size drifted")
    required = set(policy["required_fields_per_finding"])
    for finding in packet["findings"]:
        if not isinstance(finding, Mapping) or set(finding) != required or any(not isinstance(finding.get(field), str) or not finding[field].strip() for field in required):
            raise ValueError("Guided feedback finding fields drifted")


def _validate_provider_ready_payload(payload: Any, *, input_commitment: Mapping[str, Any], prompt_commitment: Mapping[str, Any], prompt_text: str, instruction_text: str, feedback_text: str | None) -> None:
    if not isinstance(payload, Mapping) or set(payload) != {"input_text", "input_sha256", "originating_prompt", "prompt_sha256", "instruction", "feedback"} or not isinstance(payload.get("input_text"), str) or payload.get("input_sha256") != input_commitment["sha256"] or hashlib.sha256(payload["input_text"].encode("utf-8")).hexdigest() != input_commitment["sha256"] or payload.get("originating_prompt") != prompt_text or payload.get("prompt_sha256") != prompt_commitment["sha256"] or hashlib.sha256(prompt_text.encode("utf-8")).hexdigest() != prompt_commitment["sha256"] or payload.get("instruction") != instruction_text or payload.get("feedback") != feedback_text:
        raise ValueError("Provider-ready payload binding drifted")


def _feedback_provider_payload(
    *,
    input_text: str,
    originating_prompt: str,
    composition: Mapping[str, Any],
    prompt: str,
    schema: str,
) -> dict[str, Any]:
    return {
        "input_text": input_text,
        "originating_prompt": originating_prompt,
        "bundle_id": composition["bundle"]["bundle_id"],
        "questions": composition["questions"],
        "feedback_prompt": prompt,
        "response_schema": schema,
    }


def _composition_input(
    *,
    value: Mapping[str, Any],
    event: Mapping[str, Any],
    input_path: Path,
    parent_revision_lineage: list[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], str]:
    input_bytes = _read_bytes(input_path, label="CWR composition input")
    input_text = input_bytes.decode("utf-8")
    if event["cycle"] == 1:
        expected = value["source_population"]["input_commitments"][event["source_item_id"]]["source.md"]
        commitment = {
            "kind": "source",
            "item_id": event["source_item_id"],
            "bytes": expected["bytes"],
            "sha256": expected["sha256"],
        }
    else:
        parent_id = event["parent_event_id"]
        parent_record = next((record for record in parent_revision_lineage or [] if record["event_id"] == parent_id), None)
        if not isinstance(parent_record, Mapping):
            raise ValueError("Second-cycle CWR composition requires validated cycle-one parent lineage")
        commitment = {"kind": "parent_descendant", "event_id": parent_id, **dict(parent_record["descendant"])}
    if commitment.get("bytes") != len(input_bytes) or commitment.get("sha256") != hashlib.sha256(input_bytes).hexdigest():
        raise ValueError("CWR composition input commitment drifted")
    return commitment, input_text


def _work_root_commitment(work_root: Path, path: Path, *, label: str) -> dict[str, Any]:
    _reject_reparse_ancestors(path)
    try:
        relative = path.resolve().relative_to(work_root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} must remain inside the authorized work root") from error
    payload = _read_bytes(path, label=label)
    return {"path": relative.as_posix(), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def cwr_feedback_composition(
    work_root: Path,
    *,
    event_id: str,
    input_path: Path,
    originating_prompt_path: Path,
    sampler: Mapping[str, Any],
    cycle1_revision_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Compose one exact, provider-free CWR feedback request in the approved work root."""
    frozen, value = validate_frozen_inputs(work_root), contract()
    validate_disclosure_acknowledgement(work_root, work_root / INITIAL_ACKNOWLEDGEMENT)
    event = next((candidate for candidate in revision_schedule(value) if candidate["event_id"] == event_id), None)
    if event is None or event["guidance_arm"] != "cwr_guided":
        raise ValueError("CWR composition requires one predeclared guided revision event")
    _validate_sampler(sampler)
    parent_lineage: list[Mapping[str, Any]] | None = None
    parent_lineage_commitment: dict[str, Any] | None = None
    if event["cycle"] == 2:
        if cycle1_revision_manifest_path is None:
            raise ValueError("Second-cycle CWR composition requires a frozen cycle-one revision manifest")
        parent_lineage = validate_revision_lineage(work_root, cycle1_revision_manifest_path, cycle=1)
        parent_lineage_commitment = _work_root_commitment(work_root, cycle1_revision_manifest_path, label="cycle-one revision lineage")
    input_binding, input_text = _composition_input(
        value=value,
        event=event,
        input_path=input_path,
        parent_revision_lineage=parent_lineage,
    )
    prompt_bytes = _read_bytes(originating_prompt_path, label="CWR composition originating prompt")
    prompt_text = prompt_bytes.decode("utf-8")
    prompt_expected = next(row["prompt"] for row in frozen["inputs"] if row["item_id"] == event["source_item_id"])
    if prompt_expected["bytes"] != len(prompt_bytes) or prompt_expected["sha256"] != hashlib.sha256(prompt_bytes).hexdigest():
        raise ValueError("CWR composition originating prompt binding drifted")
    instrument = value["generation"]["feedback_instrument"]
    prompt = _read_bytes(HERE / instrument["prompt"]["path"], label="CWR feedback prompt").decode("utf-8")
    schema = _read_bytes(HERE / instrument["schema"]["path"], label="CWR feedback schema").decode("utf-8")
    composition = _cwr_runtime_composition(value)
    payload = _feedback_provider_payload(
        input_text=input_text,
        originating_prompt=prompt_text,
        composition=composition,
        prompt=prompt,
        schema=schema,
    )
    base = {
        "format_version": 1,
        "study_id": value["study_id"],
        "role": "cwr_feedback",
        "event": dict(event),
        "input": input_binding,
        "cycle1_revision_lineage": parent_lineage_commitment,
        "originating_prompt": {"item_id": event["source_item_id"], "bytes": len(prompt_bytes), "sha256": hashlib.sha256(prompt_bytes).hexdigest()},
        **{key: composition[key] for key in ("runtime_files", "bundle", "compiled_bundle", "ordered_question_payload")},
        "feedback_prompt": _committed_asset(instrument["prompt"]),
        "response_schema": _committed_asset(instrument["schema"]),
        "route": _route_identity(value, event["cwr_feedback_route_id"]),
        "sampler": dict(sampler),
        "provider_ready_payload": payload,
        "provider_ready_payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
    }
    return {**base, "composition_manifest_sha256": hashlib.sha256(canonical(base)).hexdigest()}


def write_cwr_feedback_composition(
    work_root: Path,
    *,
    event_id: str,
    input_path: Path,
    originating_prompt_path: Path,
    sampler: Mapping[str, Any],
    cycle1_revision_manifest_path: Path | None = None,
) -> dict[str, Any]:
    manifest = cwr_feedback_composition(
        work_root,
        event_id=event_id,
        input_path=input_path,
        originating_prompt_path=originating_prompt_path,
        sampler=sampler,
        cycle1_revision_manifest_path=cycle1_revision_manifest_path,
    )
    path = work_root / "cwr-feedback-compositions" / f"{event_id}.json"
    if path.exists():
        validated = validate_cwr_feedback_composition(work_root, path)
        if _read_bytes(path, label="CWR composition manifest") != canonical(manifest):
            raise ValueError("Existing immutable CWR composition manifest does not match this exact composition")
        return validated
    _write_immutable_bytes(path, canonical(manifest), label="CWR composition manifest")
    return manifest


def _validate_cwr_feedback_composition_acknowledgement(work_root: Path, manifest: Mapping[str, Any]) -> None:
    event_id = manifest["event"]["event_id"]
    path = work_root / "cwr-feedback-compositions" / f"{event_id}.acknowledgement.json"
    acknowledgement = _read_json(path, label="CWR composition acknowledgement")
    expected = {
        "study_id": manifest["study_id"],
        "phase": "cwr_feedback",
        "event_id": event_id,
        "composition_manifest_sha256": manifest["composition_manifest_sha256"],
        "provider_ready_payload_sha256": manifest["provider_ready_payload_sha256"],
        "acknowledged": True,
    }
    if set(acknowledgement) != set(expected) | {"acknowledged_at"} or {key: acknowledgement.get(key) for key in expected} != expected or not isinstance(acknowledgement.get("acknowledged_at"), str) or not acknowledgement["acknowledged_at"]:
        raise ValueError("CWR composition acknowledgement binding drifted")


def validate_cwr_feedback_composition(work_root: Path, manifest_path: Path) -> dict[str, Any]:
    """Recompose the exact local payload and reject any drift before dispatch exists."""
    manifest = _read_json(manifest_path, label="CWR composition manifest")
    value = contract()
    required = {
        "format_version", "study_id", "role", "event", "input", "cycle1_revision_lineage", "originating_prompt",
        "runtime_files", "bundle", "compiled_bundle", "ordered_question_payload",
        "feedback_prompt", "response_schema", "route", "sampler", "provider_ready_payload",
        "provider_ready_payload_sha256", "composition_manifest_sha256",
    }
    if set(manifest) != required or manifest.get("format_version") != 1 or manifest.get("study_id") != value["study_id"] or manifest.get("role") != "cwr_feedback":
        raise ValueError("CWR composition manifest identity drifted")
    base = {key: manifest[key] for key in manifest if key != "composition_manifest_sha256"}
    if manifest["composition_manifest_sha256"] != hashlib.sha256(canonical(base)).hexdigest():
        raise ValueError("CWR composition manifest hash drifted")
    event = manifest["event"]
    if not isinstance(event, Mapping) or manifest.get("event") not in revision_schedule(value) or event.get("guidance_arm") != "cwr_guided":
        raise ValueError("CWR composition event binding drifted")
    _validate_sampler(manifest["sampler"])
    frozen = validate_frozen_inputs(work_root)
    validate_disclosure_acknowledgement(work_root, work_root / INITIAL_ACKNOWLEDGEMENT)
    prompt_commitment = next(row["prompt"] for row in frozen["inputs"] if row["item_id"] == event["source_item_id"])
    payload = manifest["provider_ready_payload"]
    if not isinstance(payload, Mapping) or not isinstance(payload.get("input_text"), str) or not isinstance(payload.get("originating_prompt"), str):
        raise ValueError("CWR composition provider payload drifted")
    input_bytes, prompt_bytes = payload["input_text"].encode("utf-8"), payload["originating_prompt"].encode("utf-8")
    input_binding = manifest["input"]
    if not isinstance(input_binding, Mapping) or input_binding.get("bytes") != len(input_bytes) or input_binding.get("sha256") != hashlib.sha256(input_bytes).hexdigest():
        raise ValueError("CWR composition input binding drifted")
    if event["cycle"] == 1:
        expected = value["source_population"]["input_commitments"][event["source_item_id"]]["source.md"]
        if dict(input_binding) != {"kind": "source", "item_id": event["source_item_id"], **expected}:
            raise ValueError("CWR composition source binding drifted")
        if manifest["cycle1_revision_lineage"] is not None:
            raise ValueError("First-cycle CWR composition cannot bind a parent lineage")
    else:
        lineage_commitment = manifest["cycle1_revision_lineage"]
        if not isinstance(lineage_commitment, Mapping) or set(lineage_commitment) != {"path", "bytes", "sha256"}:
            raise ValueError("Second-cycle CWR composition requires a cycle-one lineage commitment")
        lineage_path = work_root.joinpath(*Path(lineage_commitment["path"]).parts)
        if _work_root_commitment(work_root, lineage_path, label="cycle-one revision lineage") != dict(lineage_commitment):
            raise ValueError("Second-cycle CWR composition lineage commitment drifted")
        parents = validate_revision_lineage(work_root, lineage_path, cycle=1)
        parent = next((record for record in parents if record["event_id"] == event["parent_event_id"]), None)
        if not isinstance(parent, Mapping) or dict(input_binding) != {"kind": "parent_descendant", "event_id": event["parent_event_id"], **dict(parent["descendant"])}:
            raise ValueError("CWR composition parent binding drifted")
    if manifest["originating_prompt"] != {"item_id": event["source_item_id"], "bytes": len(prompt_bytes), "sha256": hashlib.sha256(prompt_bytes).hexdigest()} or {key: manifest["originating_prompt"][key] for key in ("bytes", "sha256")} != {key: prompt_commitment[key] for key in ("bytes", "sha256")}:
        raise ValueError("CWR composition originating prompt binding drifted")
    composition = _cwr_runtime_composition(value)
    if any(manifest[key] != composition[key] for key in ("runtime_files", "bundle", "compiled_bundle", "ordered_question_payload")):
        raise ValueError("CWR composition runtime or question ordering drifted")
    instrument = value["generation"]["feedback_instrument"]
    if manifest["feedback_prompt"] != _committed_asset(instrument["prompt"]) or manifest["response_schema"] != _committed_asset(instrument["schema"]):
        raise ValueError("CWR composition instrument binding drifted")
    prompt = _read_bytes(HERE / instrument["prompt"]["path"], label="CWR feedback prompt").decode("utf-8")
    schema = _read_bytes(HERE / instrument["schema"]["path"], label="CWR feedback schema").decode("utf-8")
    expected_payload = _feedback_provider_payload(input_text=payload["input_text"], originating_prompt=payload["originating_prompt"], composition=composition, prompt=prompt, schema=schema)
    if payload != expected_payload or manifest["provider_ready_payload_sha256"] != hashlib.sha256(canonical(payload)).hexdigest():
        raise ValueError("CWR composition provider payload drifted")
    if manifest["route"] != _route_identity(value, event["cwr_feedback_route_id"]):
        raise ValueError("CWR composition route binding drifted")
    return manifest


def dispatch_cwr_feedback(work_root: Path, manifest_path: Path) -> None:
    """Execution is intentionally absent until a provider-native transport adapter is accepted."""
    manifest = validate_cwr_feedback_composition(work_root, manifest_path)
    _validate_cwr_feedback_composition_acknowledgement(work_root, manifest)
    raise ValueError(
        "CWR feedback dispatch is unavailable: composition is provider-free and requires an "
        "owner-bound acknowledgement plus provider-native accepted status, model, reasoning, "
        "session, request, and response-hash evidence"
    )


def _validate_endpoint_provider_ready_payload(payload: Any, *, target_text: str, measure: Mapping[str, Any]) -> None:
    prompt = _read_bytes(HERE / measure["prompt"]["path"], label="endpoint prompt").decode("utf-8")
    schema = _read_bytes(HERE / measure["schema"]["path"], label="endpoint schema").decode("utf-8")
    expected = {"target_text": target_text, "prompt": prompt, "schema": schema}
    if payload != expected:
        raise ValueError("Endpoint provider-ready payload binding drifted")


def _revision_targets(value: Mapping[str, Any], records: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    outputs = {record["event_id"]: record["descendant"] for record in records}
    targets: dict[str, dict[str, Any]] = {}
    for target in _targets(value):
        event_id = target["target_event_id"]
        if target["target_kind"] == "baseline":
            expected = value["source_population"]["input_commitments"][target["source_item_id"]]["source.md"]
            commitment = {"bytes": expected["bytes"], "sha256": expected["sha256"]}
        else:
            commitment = {"bytes": outputs[event_id]["bytes"], "sha256": outputs[event_id]["sha256"]}
        targets[target["blind_target_id"]] = {**target, **commitment}
    return targets


def validate_revision_lineage(work_root: Path, manifest_path: Path, *, cycle: int | None = None) -> list[dict[str, Any]]:
    """Validate the immutable local provenance required before endpoint dispatch."""
    frozen, value = validate_frozen_inputs(work_root), contract()
    validate_disclosure_acknowledgement(work_root, work_root / INITIAL_ACKNOWLEDGEMENT)
    records = _read_jsonl(manifest_path)
    if cycle not in (None, 1, 2):
        raise ValueError("Revision lineage cycle scope is invalid")
    expected = {
        event["event_id"]: event
        for event in revision_schedule(value)
        if cycle is None or event["cycle"] == cycle
    }
    if len(records) != len(expected) or {record.get("event_id") for record in records} != set(expected):
        raise ValueError("Revision lineage must contain each frozen revision cell exactly once")
    source_commitments = {row["item_id"]: row["source"] for row in frozen["inputs"]}
    seen_receipts = {key: set() for key in ("provider_request_id", "request_sha256", "payload_sha256", "response_sha256")}
    matched_samplers: dict[tuple[int, str, str], Mapping[str, Any]] = {}
    by_event: dict[str, Mapping[str, Any]] = {}
    asset_sha = sha256(HERE / value["generation"]["instruction_asset"]["path"])
    instructions = _read_json(HERE / value["generation"]["instruction_asset"]["path"], label="revision instruction asset")
    base_sha = hashlib.sha256(instructions["neutral_base_revision_instruction"].encode("utf-8")).hexdigest()
    for record in records:
        event = expected[record["event_id"]]
        required = {"record_type", "event_id", "source", "parent", "descendant", "instruction", "feedback", "generator"}
        if set(record) != required or record["record_type"] != "revision":
            raise ValueError("Revision lineage record shape drifted")
        source = record["source"]
        if not isinstance(source, Mapping) or source != {"item_id": event["source_item_id"], **source_commitments[event["source_item_id"]]}:
            raise ValueError("Revision lineage source binding drifted")
        parent = record["parent"]
        if event["cycle"] == 1:
            if parent is not None:
                raise ValueError("First-cycle revision lineage cannot have a parent")
        else:
            parent_event_id = event["parent_event_id"]
            parent_record = by_event.get(parent_event_id)
            if not isinstance(parent, Mapping) or parent_record is None or parent != {"event_id": parent_event_id, **parent_record["descendant"]}:
                raise ValueError("Second-cycle revision lineage parent binding drifted")
        descendant = record["descendant"]
        if not isinstance(descendant, Mapping) or set(descendant) != {"path", "bytes", "sha256"}:
            raise ValueError("Revision lineage descendant commitment drifted")
        _artifact(work_root, descendant, field="descendant")
        instruction = record["instruction"]
        if instruction != {"asset_sha256": asset_sha, "neutral_base_instruction_sha256": base_sha}:
            raise ValueError("Revision lineage instruction binding drifted")
        feedback = record["feedback"]
        input_commitment = parent if event["cycle"] == 2 else source
        if event["guidance_arm"] == "cwr_guided":
            if not isinstance(feedback, Mapping) or set(feedback) != {"artifact", "composition", "generator", "source_request_sha256"} or not _sha256_string(feedback.get("source_request_sha256")) or not isinstance(feedback.get("artifact"), Mapping) or set(feedback["artifact"]) != {"path", "bytes", "sha256"} or not isinstance(feedback.get("composition"), Mapping) or set(feedback["composition"]) != {"path", "bytes", "sha256"}:
                raise ValueError("Guided revision lineage requires frozen CWR feedback")
            composition_path = work_root.joinpath(*Path(feedback["composition"]["path"]).parts)
            if _work_root_commitment(work_root, composition_path, label="CWR composition manifest") != dict(feedback["composition"]):
                raise ValueError("Guided feedback composition commitment drifted")
            composition_manifest = validate_cwr_feedback_composition(work_root, composition_path)
            _validate_cwr_feedback_composition_acknowledgement(work_root, composition_manifest)
            if composition_manifest["event"]["event_id"] != event["event_id"]:
                raise ValueError("Guided feedback composition event drifted")
            feedback_bytes = _committed_bytes(work_root, feedback["artifact"], field="feedback")
            feedback_text = feedback_bytes.decode("utf-8")
            if not feedback_text.strip():
                raise ValueError("Guided feedback must be nonempty")
            _validate_feedback_packet(feedback_bytes, instructions)
            feedback_receipt, feedback_payload = _validate_execution_identity(
                work_root,
                feedback["generator"],
                _route_identity(value, event["cwr_feedback_route_id"]),
                role_key="role",
                role_value="cwr_feedback",
                event_id=event["event_id"],
                payload={"composition": feedback["composition"], "composition_manifest_sha256": composition_manifest["composition_manifest_sha256"], "provider_ready_payload_sha256": composition_manifest["provider_ready_payload_sha256"]},
            )
            if feedback_payload != composition_manifest["provider_ready_payload"]:
                raise ValueError("Guided feedback provider payload must equal its composition manifest")
            if feedback["source_request_sha256"] != feedback_receipt["request_sha256"] or _committed_bytes(work_root, feedback_receipt["response"], field="response") != feedback_bytes:
                raise ValueError("Guided feedback receipt binding drifted")
            _register_receipt(feedback_receipt, seen_receipts, unique_response=False)
        elif feedback is not None:
            raise ValueError("Control revision lineage must not contain CWR feedback")
        generator = record["generator"]
        expected_generator = {"generator_id": event["generator_id"], **_route_identity(value, event["generator_route_id"])}
        generator_receipt, revision_payload = _validate_execution_identity(
            work_root,
            generator,
            expected_generator,
            role_key="role",
            role_value="revision_generation",
            event_id=event["event_id"],
            payload={"cycle": event["cycle"], "generator_id": event["generator_id"], "guidance_arm": event["guidance_arm"], "input": input_commitment, "instruction": instruction, "feedback": feedback["artifact"] if feedback is not None else None},
        )
        prompt_commitment = next(row["prompt"] for row in frozen["inputs"] if row["item_id"] == event["source_item_id"])
        _validate_provider_ready_payload(revision_payload, input_commitment=input_commitment, prompt_commitment=prompt_commitment, prompt_text=revision_payload.get("originating_prompt", ""), instruction_text=instructions["neutral_base_revision_instruction"], feedback_text=feedback_text if feedback is not None else None)
        if _committed_bytes(work_root, generator_receipt["response"], field="response") != _read_bytes(work_root.joinpath(*Path(descendant["path"]).parts), label="revision descendant"):
            raise ValueError("Revision descendant receipt binding drifted")
        _register_receipt(generator_receipt, seen_receipts, unique_response=False)
        matched_key = (event["cycle"], event["source_item_id"], event["generator_id"])
        earlier_sampler = matched_samplers.setdefault(matched_key, generator["sampler"])
        if dict(earlier_sampler) != dict(generator["sampler"]):
            raise ValueError("Matched guided/control revision samplers must be identical")
        by_event[event["event_id"]] = record
    return records


def endpoint_disclosure_preview(work_root: Path, revision_manifest_path: Path) -> dict[str, Any]:
    value = contract()
    targets = _revision_targets(value, validate_revision_lineage(work_root, revision_manifest_path))
    return {
        "study_id": value["study_id"],
        "phase": "post_generation_blind_endpoint_judgment",
        "provider_calls_made": 0,
        "call_count": len(endpoint_schedule(value)),
        "payload_composition": ["one blinded target artifact", "one frozen endpoint prompt", "one frozen response schema"],
        "destinations": {judge: _route_identity(value, judge) for judge in value["endpoint_evaluation"]["judges"]},
        "target_commitments": [dict(targets[blind_id]) for blind_id in sorted(targets)],
        "endpoint_measures": value["endpoint_evaluation"]["measures"],
        "revision_lineage_sha256": sha256(revision_manifest_path),
        "endpoint_schedule_sha256": hashlib.sha256(canonical(endpoint_schedule(value))).hexdigest(),
        "acknowledgement_required": True,
    }


def write_endpoint_disclosure_preview(work_root: Path, revision_manifest_path: Path) -> dict[str, Any]:
    preview = endpoint_disclosure_preview(work_root, revision_manifest_path)
    preview_path = work_root / "endpoint-disclosure-preview.json"
    hash_path = work_root / "endpoint-disclosure-preview.canonical.sha256"
    if preview_path.exists() or hash_path.exists():
        raise ValueError("Refusing to overwrite immutable endpoint disclosure preview")
    write_json(preview_path, preview)
    _write_immutable_bytes(hash_path, (hashlib.sha256(canonical(preview)).hexdigest() + "\n").encode("ascii"), label="endpoint disclosure hash")
    return preview


def validate_endpoint_disclosure_acknowledgement(work_root: Path, revision_manifest_path: Path, acknowledgement_path: Path) -> dict[str, Any]:
    expected = endpoint_disclosure_preview(work_root, revision_manifest_path)
    preview_path = work_root / "endpoint-disclosure-preview.json"
    hash_path = work_root / "endpoint-disclosure-preview.canonical.sha256"
    stored = _read_json(preview_path, label="endpoint disclosure preview")
    preview_sha = hashlib.sha256(canonical(expected)).hexdigest()
    if stored != expected or _read_bytes(hash_path, label="endpoint disclosure hash").decode("ascii") != preview_sha + "\n":
        raise ValueError("Endpoint disclosure preview binding drifted")
    acknowledgement = _read_json(acknowledgement_path, label="endpoint disclosure acknowledgement")
    required = {"study_id", "phase", "preview_sha256", "acknowledged", "acknowledged_at"}
    if set(acknowledgement) != required or acknowledgement.get("study_id") != expected["study_id"] or acknowledgement.get("phase") != expected["phase"] or acknowledgement.get("preview_sha256") != preview_sha or acknowledgement.get("acknowledged") is not True or not isinstance(acknowledgement.get("acknowledged_at"), str) or not acknowledgement["acknowledged_at"]:
        raise ValueError("Endpoint disclosure acknowledgement binding drifted")
    return acknowledgement


def _validate_endpoint_response(response: Any, measure: Mapping[str, Any], target_text: str) -> None:
    if not isinstance(response, Mapping) or not isinstance(response.get("overall"), int) or isinstance(response.get("overall"), bool) or not measure["minimum"] <= response["overall"] <= measure["maximum"]:
        raise ValueError("Endpoint response overall must be an in-scale integer")
    expected = {"overall", "rationale", "evidence"}
    if measure["measure_id"] == "compact_analytic":
        expected.add("dimensions")
        dimensions = response.get("dimensions")
        if not isinstance(dimensions, Mapping) or set(dimensions) != {"clarity", "coherence", "specificity", "control"} or any(not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5 for score in dimensions.values()):
            raise ValueError("Endpoint compact dimensions drifted")
    if set(response) != expected or not isinstance(response.get("rationale"), str) or not 1 <= len(response["rationale"]) <= 900:
        raise ValueError("Endpoint response rationale drifted")
    evidence = response.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != 2:
        raise ValueError("Endpoint response requires exactly two grounded evidence quotes")
    quotes: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {"quote", "explanation"} or not isinstance(item.get("quote"), str) or not 1 <= len(item["quote"]) <= 320 or item["quote"] not in target_text or not isinstance(item.get("explanation"), str) or not 1 <= len(item["explanation"]) <= 480 or item["quote"] in quotes:
            raise ValueError("Endpoint evidence quote is not grounded in the blinded target")
        quotes.add(item["quote"])


def validate_endpoint_lineage(work_root: Path, revision_manifest_path: Path, manifest_path: Path) -> list[dict[str, Any]]:
    value = contract()
    revisions = validate_revision_lineage(work_root, revision_manifest_path)
    validate_endpoint_disclosure_acknowledgement(work_root, revision_manifest_path, work_root / ENDPOINT_ACKNOWLEDGEMENT)
    targets = _revision_targets(value, revisions)
    events = {event["endpoint_event_id"]: event for event in endpoint_schedule(value)}
    measures = {measure["measure_id"]: measure for measure in value["endpoint_evaluation"]["measures"]}
    records = _read_jsonl(manifest_path)
    if len(records) != len(events) or {record.get("endpoint_event_id") for record in records} != set(events):
        raise ValueError("Endpoint lineage must contain all 216 frozen calls exactly once")
    seen_receipts = {key: set() for key in ("provider_request_id", "request_sha256", "payload_sha256", "response_sha256")}
    for revision in revisions:
        _register_receipt(revision["generator"]["receipt"], seen_receipts, unique_response=False)
        if revision["feedback"] is not None:
            _register_receipt(revision["feedback"]["generator"]["receipt"], seen_receipts, unique_response=False)
    for record in records:
        event = events[record["endpoint_event_id"]]
        required = {"record_type", "endpoint_event_id", "blind_target_id", "target", "instrument", "judge", "response"}
        if set(record) != required or record["record_type"] != "endpoint" or record["blind_target_id"] != event["blind_target_id"]:
            raise ValueError("Endpoint lineage identity drifted")
        expected_target = targets[event["blind_target_id"]]
        target = record["target"]
        if not isinstance(target, Mapping) or {key: target.get(key) for key in ("bytes", "sha256")} != {key: expected_target[key] for key in ("bytes", "sha256")} or set(target) != {"path", "bytes", "sha256"}:
            raise ValueError("Endpoint target commitment drifted")
        target_text = _artifact(work_root, target, field="target")
        measure = measures[event["measure_id"]]
        expected_instrument = {"prompt_sha256": measure["prompt"]["sha256"], "schema_sha256": measure["schema"]["sha256"]}
        if record["instrument"] != expected_instrument:
            raise ValueError("Endpoint instrument binding drifted")
        receipt, endpoint_payload = _validate_execution_identity(
            work_root,
            record["judge"],
            _route_identity(value, event["judge_route_id"]),
            role_key="role",
            role_value="blind_endpoint_judgment",
            event_id=event["endpoint_event_id"],
            payload={"blind_target_id": event["blind_target_id"], "target": target, "instrument": expected_instrument},
        )
        _validate_endpoint_provider_ready_payload(endpoint_payload, target_text=target_text, measure=measure)
        _validate_endpoint_response(record["response"], measure, target_text)
        if _committed_bytes(work_root, receipt["response"], field="response") != canonical(record["response"]):
            raise ValueError("Endpoint judge output receipt binding drifted")
        _register_receipt(receipt, seen_receipts, unique_response=False)
    return records


def calculate_differences(work_root: Path, revision_manifest_path: Path, endpoint_manifest_path: Path) -> dict[str, Any]:
    """Calculate frozen comparisons from the fully revalidated endpoint lineage only."""
    records = validate_endpoint_lineage(work_root, revision_manifest_path, endpoint_manifest_path)
    raise ValueError("Provider-free scaffold cannot promote executed lineage or revision gains without an exact CWR composition manifest, provider payload and schema, and provider-native transport receipts binding request ID, status, accepted model/reasoning, transmitted payload hash, and returned response hash")


def _calculate_differences_from_validated_records(endpoint_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    value = contract()
    endpoints = {event["endpoint_event_id"]: event for event in endpoint_schedule(value)}
    measures = {measure["measure_id"]: measure for measure in value["endpoint_evaluation"]["measures"]}
    if len(endpoint_records) != len(endpoints):
        raise ValueError("Revision-gain endpoint score set is incomplete")
    scores: dict[str, int] = {}
    for record in endpoint_records:
        event_id = record.get("endpoint_event_id")
        response = record.get("response")
        scalar = response.get("overall") if isinstance(response, Mapping) else None
        if event_id not in endpoints or event_id in scores or not isinstance(scalar, int) or isinstance(scalar, bool):
            raise ValueError("Revision-gain endpoint score record drifted")
        measure = measures[endpoints[event_id]["measure_id"]]
        if scalar < measure["minimum"] or scalar > measure["maximum"]:
            raise ValueError("Revision-gain endpoint scalar is outside its frozen scale")
        scores[event_id] = scalar
    targets = {target["blind_target_id"]: target for target in _targets(value)}
    lookup = {(event["blind_target_id"], event["judge_route_id"], event["measure_id"]): scores[event["endpoint_event_id"]] for event in endpoints.values()}
    rows: list[dict[str, Any]] = []
    parent_rows: list[dict[str, Any]] = []
    for event in revision_schedule(value):
        if event["cycle"] == 2:
            parent_id = event["parent_event_id"]
            parent_target = next(target for target in targets.values() if target["target_event_id"] == parent_id)
            child_target = next(target for target in targets.values() if target["target_event_id"] == event["event_id"])
            for judge in value["endpoint_evaluation"]["judges"]:
                for measure in measures:
                    parent_rows.append({"source_item_id": event["source_item_id"], "generator_id": event["generator_id"], "guidance_arm": event["guidance_arm"], "judge_route_id": judge, "measure_id": measure, "scale": {"minimum": measures[measure]["minimum"], "maximum": measures[measure]["maximum"]}, "cycle1_parent_event_id": parent_id, "cycle2_child_event_id": event["event_id"], "child_minus_cycle1_parent": lookup[(child_target["blind_target_id"], judge, measure)] - lookup[(parent_target["blind_target_id"], judge, measure)]})
        if event["guidance_arm"] != "cwr_guided":
            continue
        control_id = _revision_event_id(event["cycle"], event["source_item_id"], event["generator_id"], "generic_no_feedback")
        guided_target = next(target for target in targets.values() if target["target_event_id"] == event["event_id"])
        control_target = next(target for target in targets.values() if target["target_event_id"] == control_id)
        for judge in value["endpoint_evaluation"]["judges"]:
            for measure in measures:
                row = {"source_item_id": event["source_item_id"], "cycle": event["cycle"], "generator_id": event["generator_id"], "judge_route_id": judge, "measure_id": measure, "scale": {"minimum": measures[measure]["minimum"], "maximum": measures[measure]["maximum"]}, "guided_event_id": event["event_id"], "control_event_id": control_id, "guided_minus_control": lookup[(guided_target["blind_target_id"], judge, measure)] - lookup[(control_target["blind_target_id"], judge, measure)]}
                if event["cycle"] == 2:
                    row["comparison_scope"] = "cumulative_from_cycle1_parent"
                else:
                    row["comparison_scope"] = "cycle1_incremental"
                rows.append(row)
    summaries = []
    for judge in value["endpoint_evaluation"]["judges"]:
        for measure_id, measure in measures.items():
            values = [row["guided_minus_control"] for row in rows if row["judge_route_id"] == judge and row["measure_id"] == measure_id]
            summaries.append({"judge_route_id": judge, "measure_id": measure_id, "scale": {"minimum": measure["minimum"], "maximum": measure["maximum"]}, "equal_weight_unit": "source_generator_cycle", "sample_count": len(values), "mean_guided_minus_control": statistics.fmean(values), "directional_consistency": {"positive": sum(score > 0 for score in values), "zero": sum(score == 0 for score in values), "negative": sum(score < 0 for score in values)}, "uncertainty_reporting": {"method": "raw_paired_rows_and_directional_counts", "status": "no_interval_estimate_predeclared_for_this_development_pilot; do_not_pool_scales"}})
    return {"study_id": value["study_id"], "primary_guided_minus_control": rows, "cycle2_child_minus_cycle1_parent": parent_rows, "equal_weight_summaries_by_judge_measure_scale": summaries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--acknowledgement", type=Path)
    parser.add_argument("--freeze-inputs", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--write-preview", action="store_true")
    parser.add_argument("--validate-acknowledgement", action="store_true")
    parser.add_argument("--revision-manifest", type=Path)
    parser.add_argument("--endpoint-manifest", type=Path)
    parser.add_argument("--write-endpoint-preview", action="store_true")
    parser.add_argument("--validate-endpoint-acknowledgement", action="store_true")
    parser.add_argument("--endpoint-acknowledgement", type=Path)
    parser.add_argument("--compose-cwr-feedback", action="store_true")
    parser.add_argument("--validate-cwr-composition", type=Path)
    parser.add_argument("--event-id")
    parser.add_argument("--input-path", type=Path)
    parser.add_argument("--originating-prompt-path", type=Path)
    parser.add_argument("--cycle1-revision-manifest", type=Path)
    parser.add_argument("--sampler-json")
    args = parser.parse_args()
    if args.freeze_inputs:
        if args.source_root is None:
            parser.error("--freeze-inputs requires --source-root")
        print(json.dumps(freeze_inputs(args.source_root.resolve(), args.work_root.resolve()), sort_keys=True))
    if args.validate:
        print(json.dumps(validate_frozen_inputs(args.work_root.resolve()), sort_keys=True))
    if args.write_preview:
        print(json.dumps(write_disclosure_preview(args.work_root.resolve()), sort_keys=True))
    if args.validate_acknowledgement:
        if args.acknowledgement is None:
            parser.error("--validate-acknowledgement requires --acknowledgement")
        print(json.dumps(validate_disclosure_acknowledgement(args.work_root.resolve(), args.acknowledgement.resolve()), sort_keys=True))
    if args.revision_manifest:
        print(json.dumps(validate_revision_lineage(args.work_root.resolve(), args.revision_manifest.resolve()), sort_keys=True))
    if args.write_endpoint_preview:
        if args.revision_manifest is None:
            parser.error("--write-endpoint-preview requires --revision-manifest")
        print(json.dumps(write_endpoint_disclosure_preview(args.work_root.resolve(), args.revision_manifest.resolve()), sort_keys=True))
    if args.validate_endpoint_acknowledgement:
        if args.revision_manifest is None or args.endpoint_acknowledgement is None:
            parser.error("--validate-endpoint-acknowledgement requires --revision-manifest and --endpoint-acknowledgement")
        print(json.dumps(validate_endpoint_disclosure_acknowledgement(args.work_root.resolve(), args.revision_manifest.resolve(), args.endpoint_acknowledgement.resolve()), sort_keys=True))
    if args.endpoint_manifest:
        if args.revision_manifest is None:
            parser.error("--endpoint-manifest requires --revision-manifest")
        print(json.dumps(validate_endpoint_lineage(args.work_root.resolve(), args.revision_manifest.resolve(), args.endpoint_manifest.resolve()), sort_keys=True))
    if args.compose_cwr_feedback:
        if not all((args.event_id, args.input_path, args.originating_prompt_path, args.sampler_json)):
            parser.error("--compose-cwr-feedback requires --event-id, --input-path, --originating-prompt-path, and --sampler-json")
        try:
            sampler = json.loads(args.sampler_json)
        except json.JSONDecodeError as error:
            parser.error(f"--sampler-json is not JSON: {error.msg}")
        manifest = write_cwr_feedback_composition(
            args.work_root.resolve(),
            event_id=args.event_id,
            input_path=args.input_path.resolve(),
            originating_prompt_path=args.originating_prompt_path.resolve(),
            sampler=sampler,
            cycle1_revision_manifest_path=args.cycle1_revision_manifest.resolve() if args.cycle1_revision_manifest else None,
        )
        print(json.dumps({"event_id": manifest["event"]["event_id"], "composition_manifest_sha256": manifest["composition_manifest_sha256"], "provider_calls_made": 0}, sort_keys=True))
    if args.validate_cwr_composition:
        manifest = validate_cwr_feedback_composition(args.work_root.resolve(), args.validate_cwr_composition.resolve())
        print(json.dumps({"event_id": manifest["event"]["event_id"], "composition_manifest_sha256": manifest["composition_manifest_sha256"], "provider_calls_made": 0}, sort_keys=True))
    if not (args.freeze_inputs or args.validate or args.write_preview or args.validate_acknowledgement or args.revision_manifest or args.endpoint_manifest or args.write_endpoint_preview or args.validate_endpoint_acknowledgement or args.compose_cwr_feedback or args.validate_cwr_composition):
        parser.error("choose a provider-free action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
