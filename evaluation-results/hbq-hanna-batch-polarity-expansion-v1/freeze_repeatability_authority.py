"""Freeze the repeatability prefix extension from source commitments only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "repeatability-authority-contract.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    actual = path.resolve()
    if not actual.is_file():
        raise ValueError(f"Missing bound file: {path}")
    return {"path": str(actual), "bytes": actual.stat().st_size, "sha256": sha256(actual.read_bytes())}


def runtime_binding(path: Path) -> dict[str, Any]:
    actual = path.resolve()
    try:
        relative_path = actual.relative_to(HERE.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"Runtime file is outside the authority package: {path}") from error
    if not actual.is_file():
        raise ValueError(f"Missing bound runtime file: {path}")
    return {"relative_path": relative_path, "bytes": actual.stat().st_size, "sha256": sha256(actual.read_bytes())}


def _matches(binding: Any) -> bool:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "bytes", "sha256"}:
        return False
    actual = Path(str(binding["path"])).resolve()
    return actual.is_file() and type(binding["bytes"]) is int and binding["bytes"] == actual.stat().st_size and binding["sha256"] == sha256(actual.read_bytes())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate object key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite(item)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        _reject_non_finite(value)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Immutable authority drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_contract() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    required = {"format_version", "authority_id", "status", "source_frozen_contract", "first_eleven_story_ids", "eligible_partition", "metadata_fields", "ranking_namespace", "ranking", "outcome_inputs", "supersedes"}
    expected_metadata = ["item_id", "model", "story_id", "source_sha256", "prompt_sha256", "task_contract_sha256"]
    if (set(contract) != required or contract["format_version"] != 2
            or contract["authority_id"] != "hbq-hanna-repeatability-twelfth-authority-v2"
            or contract["status"] != "frozen_before_expansion_execution"
            or contract["eligible_partition"] != "development"
            or contract["metadata_fields"] != expected_metadata
            or contract["ranking_namespace"] != "hbq-hanna-repeatability-twelfth-authority-v1"
            or contract["outcome_inputs"] != "forbidden"):
        raise ValueError("Repeatability authority contract drifted")
    source = contract["source_frozen_contract"]
    if not isinstance(source, Mapping) or set(source) != {"study_id", "format_version", "sha256"} or source["study_id"] != "hbq-human-alignment-v3-successor-v1" or source["format_version"] != 2 or not _hex(source["sha256"]):
        raise ValueError("Repeatability authority source binding drifted")
    prefix = contract["first_eleven_story_ids"]
    if not _story_ids(prefix) or len(prefix) != 11:
        raise ValueError("Repeatability authority prefix drifted")
    supersedes = contract["supersedes"]
    if not isinstance(supersedes, list) or len(supersedes) != 2 or any(not isinstance(item, Mapping) or set(item) != {"authority_sha256", "reason"} or not _hex(item["authority_sha256"]) or not isinstance(item["reason"], str) or not item["reason"] for item in supersedes) or len({item["authority_sha256"] for item in supersedes}) != len(supersedes):
        raise ValueError("Repeatability authority supersession drifted")
    return contract


def _hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _story_ids(values: Any) -> bool:
    return isinstance(values, list) and len(values) == len(set(values)) and all(isinstance(value, str) and value.startswith("hanna-") and value[6:].isdigit() for value in values)


def _input_hash(entry: Any, name: str) -> str:
    if not isinstance(entry, Mapping) or set(entry) != {"name", "bytes", "sha256"} or entry.get("name") != name or type(entry.get("bytes")) is not int or not _hex(entry.get("sha256")):
        raise ValueError(f"Frozen source metadata lacks {name} commitment")
    return str(entry["sha256"])


def _metadata_rows(source: Mapping[str, Any], contract: Mapping[str, Any]) -> list[dict[str, str]]:
    source_binding = contract["source_frozen_contract"]
    if source.get("study_id") != source_binding["study_id"] or source.get("format_version") != source_binding["format_version"]:
        raise ValueError("Source frozen contract identity drifted")
    selection = source.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("Source frozen contract lacks selection metadata")
    repeatability = selection.get("repeatability")
    if not isinstance(repeatability, list):
        raise ValueError("Source repeatability metadata drifted")
    prefix = [item.get("item_id") for item in repeatability if isinstance(item, Mapping)]
    if prefix != contract["first_eleven_story_ids"]:
        raise ValueError("Source repeatability prefix does not match the frozen authority contract")
    if not isinstance(selection.get(contract["eligible_partition"]), list):
        raise ValueError("Source contract lacks the eligible frozen partition")
    rows: list[dict[str, str]] = []
    for raw in selection[contract["eligible_partition"]]:
        if not isinstance(raw, Mapping):
            raise ValueError("Source frozen partition has malformed metadata")
        item_id, story_id, model = raw.get("item_id"), raw.get("story_id"), raw.get("model")
        if not isinstance(item_id, str) or not isinstance(story_id, str) or not isinstance(model, str) or item_id != f"hanna-{story_id}" or not item_id.startswith("hanna-"):
            raise ValueError("Source frozen partition has malformed story metadata")
        external = raw.get("external_input")
        if not isinstance(external, Mapping) or set(external) != {"source.md", "prompt.md", "task-contract.json"}:
            raise ValueError("Source frozen partition has malformed input commitments")
        rows.append({
            "item_id": item_id, "model": model, "story_id": story_id,
            "source_sha256": _input_hash(external["source.md"], "source.md"),
            "prompt_sha256": _input_hash(external["prompt.md"], "prompt.md"),
            "task_contract_sha256": _input_hash(external["task-contract.json"], "task-contract.json"),
        })
    if len(rows) < 12 or len({row["item_id"] for row in rows}) != len(rows):
        raise ValueError("Source frozen partition lacks a unique eligible universe")
    if not set(contract["first_eleven_story_ids"]).issubset({row["item_id"] for row in rows}):
        raise ValueError("Source repeatability prefix is not in the eligible universe")
    return sorted(rows, key=lambda row: row["item_id"])


def _ranked_ids(rows: Sequence[Mapping[str, str]], contract: Mapping[str, Any]) -> list[str]:
    prefix = set(contract["first_eleven_story_ids"])
    eligible = [dict(row) for row in rows if row["item_id"] not in prefix]
    if not eligible:
        raise ValueError("Frozen source metadata has no twelfth-story candidate")
    # The fixed projection preserves the previously sealed v1 draw while leaving artifact IDs free to evolve.
    return [row["item_id"] for row in sorted(eligible, key=lambda row: (sha256(canonical({"authority_id": contract["ranking_namespace"], "candidate_metadata": row})), row["item_id"]))]


def authority_record(source_frozen_contract: Path) -> dict[str, Any]:
    contract = load_contract()
    binding = fingerprint(source_frozen_contract)
    if binding["sha256"] != contract["source_frozen_contract"]["sha256"]:
        raise ValueError("Source frozen contract hash does not match the authority contract")
    rows = _metadata_rows(read_json(source_frozen_contract), contract)
    ranked = _ranked_ids(rows, contract)
    ordered = [*contract["first_eleven_story_ids"], *ranked]
    metadata_sha256 = sha256(canonical(rows))
    selection = {"first_eleven_story_ids": contract["first_eleven_story_ids"], "ordered_story_ids": ordered, "twelfth_story_id": ordered[11]}
    return {
        "format_version": 2,
        "status": "frozen_before_expansion_execution",
        "authority_id": contract["authority_id"],
        "ranking_namespace": contract["ranking_namespace"],
        "outcome_inputs": "forbidden",
        "selector": contract["ranking"],
        "input_commitments": {"authority_contract": runtime_binding(CONTRACT_PATH), "source_frozen_contract": binding, "source_metadata_sha256": metadata_sha256},
        **selection,
        "selection_sha256": sha256(canonical(selection)),
        "supersedes": contract["supersedes"],
    }


def freeze(source_frozen_contract: Path, output: Path) -> dict[str, Any]:
    record = authority_record(source_frozen_contract)
    immutable_json(output, record)
    return record


def verify_authority(path: Path) -> dict[str, Any]:
    authority = read_json(path)
    required = {"format_version", "status", "authority_id", "ranking_namespace", "outcome_inputs", "selector", "input_commitments", "first_eleven_story_ids", "ordered_story_ids", "twelfth_story_id", "selection_sha256", "supersedes"}
    if set(authority) != required or authority["format_version"] != 2 or authority["status"] != "frozen_before_expansion_execution" or authority["outcome_inputs"] != "forbidden":
        raise ValueError("Twelfth-story authority is not a frozen pre-outcome input")
    contract = load_contract()
    if authority["authority_id"] != contract["authority_id"] or authority["ranking_namespace"] != contract["ranking_namespace"] or authority["selector"] != contract["ranking"]:
        raise ValueError("Twelfth-story authority contract drifted")
    bindings = authority["input_commitments"]
    if not isinstance(bindings, Mapping) or set(bindings) != {"authority_contract", "source_frozen_contract", "source_metadata_sha256"} or bindings["authority_contract"] != runtime_binding(CONTRACT_PATH) or not _matches(bindings["source_frozen_contract"]) or not _hex(bindings["source_metadata_sha256"]):
        raise ValueError("Twelfth-story authority input commitments drifted")
    if authority["supersedes"] != contract["supersedes"]:
        raise ValueError("Twelfth-story authority supersession drifted")
    expected = authority_record(Path(str(bindings["source_frozen_contract"]["path"])))
    if authority != expected:
        raise ValueError("Twelfth-story authority selection drifted")
    return authority


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-frozen-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    freeze(arguments.source_frozen_contract, arguments.output)


if __name__ == "__main__":
    main()
