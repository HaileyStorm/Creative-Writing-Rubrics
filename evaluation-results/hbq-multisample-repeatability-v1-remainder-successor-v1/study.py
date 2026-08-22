"""Seal the closed multisample prefix and derive its fresh-only remainder."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "study-contract.json"
JOURNAL = "remainder-schedule-journal.jsonl"
BINDING = "closed-successor-binding.json"
EXECUTION = "remainder-execution-contract.json"
RETRY_AFTER = "2026-08-28T01:21:00+00:00"
EXPECTED_CLOSED = {
    "file_count": 1008,
    "manifest_sha256": "1fbf47b97a9cc1f71242e0ec32afef9a2faab89ccdf6943d4e253118c3e5f01e",
    "journal_sha256": "df0e6eafc4f6f7c91a419e7e1cbc6b46e36fa1abba9dae24bb9393890246fcaa",
    "predecessor_binding_sha256": "3a63744f2cef2748b17a31dd53e23ac62aa802283e12dd983cae813151ed939e",
    "execution_contract_sha256": "27b37be23f3f24f1c904b809cc454c81a536f3f610d5e43c95838623139a8ccf",
    "partial_sequence": 178,
    "partial_output_manifest_sha256": "c471a4f5b2dd188a1307e8318c46185fba00cf6617672a550951992c8230aa85",
}
PARTIAL_RELATIVE = Path("runs/hanna-52/hbq_short_story_batch32/run-05")
REJECTION_HASHES = (
    "c31481aac59c19c8bb1adcbdaecb8df533ce8a90970e3b3c5faab9fd7b777be6",
    "9ebc4b55f7589c69602d022940a8ead5b40999027bd73ac9d81819f68c90840d",
    "b42731639ae5914cc09b024bae0a4ccd4a73c0052caed68c6647c8c79168766d",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid strict JSON: {label}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {label}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        return parse_json_object(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"Immutable remainder artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise ValueError(f"Uncertain partial artifact exists: {temporary.name}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def manifest(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Closed successor root must be a real directory")
    rows: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Closed successor root contains a symlink/reparse entry")
        if path.is_file():
            rows.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
    return sorted(rows, key=lambda row: row["path"])


def manifest_sha256(rows: list[Mapping[str, Any]]) -> str:
    payload = b"".join(f"{row['path']}\t{row['bytes']}\t{row['sha256']}\n".encode("utf-8") for row in rows)
    return hashlib.sha256(payload).hexdigest()


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if value.get("study_id") != "hbq-multisample-repeatability-v1-remainder-successor-v1" or value.get("format_version") != 1:
        raise ValueError("Remainder contract identity drifted")
    if value.get("closed_successor") != EXPECTED_CLOSED or value.get("retry_after") != RETRY_AFTER:
        raise ValueError("Remainder contract commitments drifted")
    return value


def read_journal(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError("Closed successor journal is missing")
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("Closed successor journal has an uncertain partial tail")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        rows.append(parse_json_object(line.decode("utf-8"), "closed successor journal row"))
    return rows


def schedule_from_closed(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = read_journal(root / "successor-schedule-journal.jsonl")
    if len(rows) != 355:
        raise ValueError("Closed successor journal does not have its sealed 254-cell plan plus 101 completions")
    planned, completed = rows[:254], rows[254:]
    sequences = [row.get("sequence") for row in planned]
    if sequences != list(range(77, 331)):
        raise ValueError("Closed successor planned schedule is not the immutable 77-330 range")
    for row in planned:
        if row.get("event") != "planned":
            raise ValueError("Closed successor planned row drifted")
    if [row.get("sequence") for row in completed] != list(range(77, 178)):
        raise ValueError("Closed successor completed cells are not the exact 77-177 contiguous prefix")
    for plan, result in zip(planned, completed):
        binding = result.get("run_binding_sha256")
        if result != {**plan, "event": "completed", "run_binding_sha256": binding} or not isinstance(binding, str) or len(binding) != 64:
            raise ValueError("Closed successor completion record drifted")
    return planned, completed


def partial_record(root: Path, planned: list[Mapping[str, Any]]) -> dict[str, Any]:
    event = planned[101]
    if event.get("sequence") != EXPECTED_CLOSED["partial_sequence"] or {key: event.get(key) for key in ("item_id", "arm_id", "repetition")} != {"item_id": "hanna-52", "arm_id": "hbq_short_story_batch32", "repetition": 5}:
        raise ValueError("Closed successor partial cell identity drifted")
    folder = root / PARTIAL_RELATIVE
    rows = manifest(folder)
    if len(rows) != 15 or manifest_sha256(rows) != EXPECTED_CLOSED["partial_output_manifest_sha256"]:
        raise ValueError("Closed successor partial output manifest drifted")
    for batch in (1, 2):
        if not (folder / "responses" / f"batch-000{batch}.json").is_file():
            raise ValueError("Closed successor accepted-batch lineage drifted")
    if (folder / "responses" / "batch-0003.json").exists():
        raise ValueError("Closed successor partial batch was incorrectly treated as accepted")
    rejected = [sha(folder / "responses" / "rejected" / "batch-0003" / f"attempt-000{index}.json") for index in range(1, 4)]
    if tuple(rejected) != REJECTION_HASHES:
        raise ValueError("Closed successor quota-rejection lineage drifted")
    for index in range(1, 4):
        record = read_json(folder / "responses" / "rejected" / "batch-0003" / f"attempt-000{index}.json")
        message = record.get("error", {}).get("message") if isinstance(record.get("error"), Mapping) else None
        if record.get("attempt") != index or record.get("batch") != 3 or not isinstance(message, str) or "usage limit" not in message or "Aug 27th, 2026 7:21 PM" not in message:
            raise ValueError("Closed successor quota-rejection semantics drifted")
    return {
        "event": dict(event),
        "accepted_batches": [1, 2],
        "rejected_batch": 3,
        "rejection_sha256": rejected,
        "retry_after": RETRY_AFTER,
        "output_manifest_sha256": manifest_sha256(rows),
    }


def bind_closed_successor(root: Path) -> dict[str, Any]:
    root = root.resolve()
    rows = manifest(root)
    if len(rows) != EXPECTED_CLOSED["file_count"] or manifest_sha256(rows) != EXPECTED_CLOSED["manifest_sha256"]:
        raise ValueError("Closed successor full manifest drifted")
    for filename, expected in (("successor-schedule-journal.jsonl", EXPECTED_CLOSED["journal_sha256"]), ("predecessor-binding.json", EXPECTED_CLOSED["predecessor_binding_sha256"]), ("successor-execution-contract.json", EXPECTED_CLOSED["execution_contract_sha256"])):
        if sha(root / filename) != expected:
            raise ValueError(f"Closed successor commitment drifted: {filename}")
    planned, completed = schedule_from_closed(root)
    return {
        "root": {"file_count": len(rows), "manifest_sha256": manifest_sha256(rows)},
        "journal_sha256": sha(root / "successor-schedule-journal.jsonl"),
        "predecessor_binding_sha256": sha(root / "predecessor-binding.json"),
        "execution_contract_sha256": sha(root / "successor-execution-contract.json"),
        "completed": {"count": len(completed), "first_sequence": 77, "last_sequence": 177},
        "partial": partial_record(root, planned),
        "remaining": {"count": len(planned) - len(completed), "first_sequence": 178, "last_sequence": 330},
    }


def fresh_schedule(root: Path) -> list[dict[str, Any]]:
    planned, completed = schedule_from_closed(root)
    if len(completed) != 101:
        raise ValueError("Closed successor completion count drifted")
    return [{"event": "planned", "fresh_dispatch": True, **{key: value for key, value in row.items() if key != "event"}} for row in planned[len(completed):]]
