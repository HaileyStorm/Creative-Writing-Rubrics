"""Pure prompt, schema, input, and pass rendering for Dryad measurement plans."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[2]
_OPAQUE_STORY_ID = re.compile(r"dryad-[0-9a-f]{24}\Z")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_sources(sources: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Reject ambiguous source identities before they become artifact paths or prompts."""
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        require(isinstance(source, Mapping) and set(source) == {"partition", "position", "opaque_story_id", "story_text"}, "Public input source shape differs")
        partition, position = source["partition"], source["position"]
        opaque_story_id, story_text = source["opaque_story_id"], source["story_text"]
        require(partition in {"TRAIN", "DEV"} and isinstance(position, str) and position.isascii() and position.isdecimal() and int(position) > 0 and isinstance(opaque_story_id, str) and _OPAQUE_STORY_ID.fullmatch(opaque_story_id) and opaque_story_id not in seen and isinstance(story_text, str), "Public input identity differs")
        seen.add(opaque_story_id)
        result.append({"partition": partition, "position": position, "opaque_story_id": opaque_story_id, "story_text": story_text})
    return result


def load_inputs(raw: bytes, *, expected_sha256: str) -> list[dict[str, str]]:
    """Validate the frozen public input geometry without a plan-specific policy."""
    require(digest(raw) == expected_sha256, "Public inputs hash differs")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            require(key not in value, "Public inputs has duplicate keys")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("Public inputs is malformed") from error
    require(isinstance(value, dict) and set(value) == {"TRAIN", "DEV"} and isinstance(value["TRAIN"], list) and isinstance(value["DEV"], list) and len(value["TRAIN"]) == 176 and len(value["DEV"]) == 60, "Public input partition geometry differs")
    sources: list[dict[str, str]] = []
    for partition in ("TRAIN", "DEV"):
        for position, row in enumerate(value[partition], start=1):
            require(isinstance(row, dict) and set(row) == {"opaque_story_id", "story_text"} and isinstance(row["opaque_story_id"], str) and isinstance(row["story_text"], str), "Public input identity differs")
            sources.append({"partition": partition, "position": str(position), "opaque_story_id": row["opaque_story_id"], "story_text": row["story_text"]})
    sources = validate_sources(sources)
    require(len(sources) == 236, "Public measurement source count differs")
    return sources


def render(
    sources: Sequence[Mapping[str, str]], runtime: Any, *, batch_size: int,
    namespace: Mapping[str, str], purpose: str, protocol: Mapping[str, Any],
    response_schema_mode: str | None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Render immutable plan parts without deciding admission or writing a plan file."""
    require(type(batch_size) is int and batch_size > 0, "Measurement batch size differs")
    require(set(namespace) == {"logical_sample_prefix", "pass_prefix"}
            and all(isinstance(value, str) and value for value in namespace.values()),
            "Measurement namespace differs")
    require(isinstance(purpose, str) and purpose, "Measurement purpose differs")
    sources = validate_sources(sources)
    runtime.verify()
    require(response_schema_mode in {None, "batch_question_ids_v1"}, "Unsupported response schema mode")
    require(getattr(runtime, "response_schema_mode", None) == response_schema_mode, "Runtime response schema mode differs")
    question_ids = [item["question"]["id"] for item in runtime.questions]
    require(len(question_ids) == len(set(question_ids)) == 178, "Canonical question identities differ")
    schema_raw = runtime.runner._json_bytes(runtime.runner._response_schema())
    binary_raw = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes()
    require(digest(binary_raw) == protocol["runtime_bindings"]["prompts/judge/BINARY_EVALUATION_PROMPT.md"], "Judge prompt hash differs")
    binary = binary_raw.decode("utf-8-sig").strip()
    artifacts: dict[str, bytes] = {"response.schema.json": schema_raw}
    passes: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    ordinal = 0
    for sample_number, source in enumerate(sources, start=1):
        partition = source["partition"]
        opaque_story_id = source["opaque_story_id"]
        story_text = source["story_text"]
        logical_sample_id = f"{namespace['logical_sample_prefix']}{partition.lower()}-{sample_number:04d}-{opaque_story_id}"
        pass_id = f"{namespace['pass_prefix']}{partition.lower()}/{sample_number:04d}/{opaque_story_id}"
        for batch_number, start in enumerate(range(0, len(question_ids), batch_size), start=1):
            ordinal += 1
            chunk = runtime.questions[start:start + batch_size]
            payloads = {
                endpoint: runtime.runner._render_prompt(
                    binary_prompt=binary,
                    artifact={"name": f"{opaque_story_id}.txt", "text": story_text},
                    contexts=[], bundle_id="prose.short_story", artifact_id=logical_sample_id,
                    questions=chunk, provider=provider, model=model,
                ).encode("utf-8")
                for endpoint, provider, model in (
                    ("grok", "grok", "grok-4.6"),
                    ("sol", "codex", "gpt-5.6-sol"),
                )
            }
            require(payloads["grok"] == payloads["sol"], "Endpoint user payload differs")
            prompt_path = f"prompts/request-{ordinal:04d}.txt"
            artifacts[prompt_path] = payloads["grok"]
            request_question_ids = [item["question"]["id"] for item in chunk]
            request_schema_raw, request_schema_path = schema_raw, "response.schema.json"
            if response_schema_mode is not None:
                request_schema_raw = runtime.runner._json_bytes(runtime.runner._batch_response_schema(request_question_ids))
                request_schema_path = f"schemas/request-{ordinal:04d}.json"
                artifacts[request_schema_path] = request_schema_raw
            requests.append({
                "ordinal": ordinal, "logical_sample_id": logical_sample_id, "pass_id": pass_id,
                "batch_number": batch_number, "question_ids": request_question_ids,
                "prompt_path": prompt_path, "prompt_sha256": digest(payloads["grok"]),
                "prompt_bytes": len(payloads["grok"]),
                "endpoint_user_payloads": {
                    endpoint: {"sha256": digest(raw), "bytes": len(raw)}
                    for endpoint, raw in payloads.items()
                },
                "schema_path": request_schema_path, "schema_sha256": digest(request_schema_raw),
                "schema_bytes": len(request_schema_raw),
            })
        raw = story_text.encode("utf-8")
        artifacts[f"inputs/{opaque_story_id}.txt"] = raw
        passes.append({
            "logical_sample_id": logical_sample_id, "pass_id": pass_id, "purpose": purpose,
            "partition": partition, "opaque_story_id": opaque_story_id,
            "input_path": f"inputs/{opaque_story_id}.txt", "source_sha256": digest(raw),
            "source_bytes": len(raw), "batch_size": batch_size,
            "batches": (len(question_ids) + batch_size - 1) // batch_size,
            "run_path": f"runs/{pass_id}",
        })
    require(len(passes) == len(sources) and len(requests) == len(sources) * ((len(question_ids) + batch_size - 1) // batch_size), "Measurement plan geometry differs")
    runtime_identity: dict[str, Any] = {
        "question_ids": question_ids,
        "compiled_bundle_sha256": digest(runtime.runner._json_bytes(runtime.compiled)),
        "question_payload_sha256": digest(runtime.runner._json_bytes(runtime.runner._question_payload(runtime.questions))),
    }
    if response_schema_mode is not None:
        runtime_identity["response_schema_mode"] = response_schema_mode
    runtime.verify()
    return {
        "runtime": runtime_identity,
        "response_schema": {"path": "response.schema.json", "sha256": digest(schema_raw), "bytes": len(schema_raw)},
        "counts": {"train_stories": 176, "dev_stories": 60, "stories": len(sources), "questions_per_story": len(question_ids), "logical_requests": len(requests)},
        "passes": passes,
        "requests": requests,
        "response_schema_mode": response_schema_mode,
    }, artifacts
