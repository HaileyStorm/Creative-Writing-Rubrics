"""Immutable predecessor binding and schedule helpers for the multisample successor."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PREDECESSOR = {
    "file_count": 801,
    "manifest_sha256": "82eea667468f89d01ab7502a24e875953239fee9f3f2552f2b86cc41a3e6a697",
    "frozen_contract_sha256": "5fb06e5a4775ecfe1cee10132e52100733c7e765e8eae9865374bb23f1addddd",
    "journal_sha256": "c8e568e14d60ccf8d2f538ab32c4c67f8484dc0d2094f94039b9582f0c8bda71",
    "sessions_sha256": "ee03ef608ad9f97ed09f97701de8e00c5e64905a126a4fa16580562b870dd591",
    "sequence77_artifacts_sha256": "858a7a5754e4d0d6876e70d08f184dae45712d3e97adbb32d64b124581f10fc9",
    "sequence77_prompt_sha256": "4c5233945dfe02b99e3ddf3c51acc818ef005105cbbefa5ad252428c1e1f58db",
    "sequence77_schema_sha256": "60d88c9c6611416a5f380807ea646ff96d0a4fe0e89eff8d9c48fcd46c743256",
}
REJECTIONS = {
    "runs/hanna-1035/cambridge_igcse_0500_p2_mj_2024/run-02/attempts/rejected-0001.json": "48b23c209a8fde84163f6fa832dec1b44e0cf23bbc9a9f5126a9cf3581fb6bfb",
    "runs/hanna-225/cambridge_igcse_0500_p2_mj_2024/run-01/attempts/rejected-0001.json": "fe70d58da10a5447e2255e755236f9091f140f4bc5f4e17cb9ec37d7a8d04a58",
    "runs/hanna-225/cambridge_igcse_0500_p2_mj_2024/run-03/attempts/rejected-0001.json": "41eb8e6be751eaf485a8d29cefe94c627bc2005f3ceef6da4ad9aeee3408b08f",
    "runs/hanna-225/cambridge_igcse_0500_p2_mj_2024/run-03/attempts/rejected-0002.json": "b8937b5f491f42a51d8a5f800db38134ba49997376bb688345060a5c67399d8f",
    "runs/hanna-225/cambridge_igcse_0500_p2_mj_2024/run-03/attempts/rejected-0003.json": "29ac1d03db93e395ea7e6a871b20e8f930049a30273898078fabfd8024468d4e",
}
SEQUENCE77_PREFIX = "runs/hanna-225/cambridge_igcse_0500_p2_mj_2024/run-03/"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def write_immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"Immutable successor artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise ValueError(f"Uncertain partial successor artifact exists: {temporary.name}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if value.get("study_id") != "hbq-multisample-repeatability-v1-successor-v1" or value.get("format_version") != 1:
        raise ValueError("Successor contract identity drifted")
    if value.get("predecessor") != PREDECESSOR:
        raise ValueError("Successor predecessor pins drifted")
    return value


def plans(frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    schedule = frozen.get("schedule")
    if not isinstance(schedule, list) or len(schedule) != 330:
        raise ValueError("Predecessor schedule is not the sealed 330-cell plan")
    return [{"event": "planned", "sequence": ordinal, **event} for ordinal, event in enumerate(schedule, 1)]


def _manifest(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Predecessor root must be a real directory")
    records: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Predecessor root contains a reparse/symlink entry")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            records.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha(path)})
    return sorted(records, key=lambda row: row["path"])


def _manifest_sha256(records: list[Mapping[str, Any]]) -> str:
    payload = b"".join(
        f"{row['path']}\t{row['bytes']}\t{row['sha256']}\n".encode("utf-8")
        for row in records
    )
    return hashlib.sha256(payload).hexdigest()


def _session_ids(root: Path) -> list[str]:
    values: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            parsed: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Predecessor JSON is malformed: {path.name}") from exc
        stack = [parsed]
        while stack:
            value = stack.pop()
            if isinstance(value, Mapping):
                if set(value) >= {"session_id"} and isinstance(value.get("session_id"), str):
                    values.append(value["session_id"])
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    if len(values) != 146 or len(set(values)) != 146:
        raise ValueError("Predecessor session set is missing or non-unique")
    return sorted(values)


def _session_sha256(values: list[str]) -> str:
    return hashlib.sha256(b"".join((value + "\n").encode("utf-8") for value in values)).hexdigest()


def predecessor_session_ids(root: Path) -> list[str]:
    """Return the verified predecessor session IDs for post-hoc disjointness checks."""
    return _session_ids(root)


def _sequence77_artifacts(root: Path) -> list[dict[str, Any]]:
    folder = root / Path(SEQUENCE77_PREFIX)
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Predecessor sequence 77 failure directory is unavailable")
    records = _manifest(folder)
    if len(records) != 9 or any(not row["path"].startswith(("attempts/", "responses/")) and row["path"] not in {"pass.json", "request.prompt.txt.gz", "response.schema.json"} for row in records):
        raise ValueError("Predecessor sequence 77 failure artifact set drifted")
    if _manifest_sha256(records) != PREDECESSOR["sequence77_artifacts_sha256"]:
        raise ValueError("Predecessor sequence 77 failure artifact commitment drifted")
    pass_record = next(row for row in records if row["path"] == "pass.json")
    manifest = read_json(folder / "pass.json")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping) or configuration.get("prompt_sha256") != PREDECESSOR["sequence77_prompt_sha256"] or configuration.get("schema_sha256") != PREDECESSOR["sequence77_schema_sha256"]:
        raise ValueError("Predecessor sequence 77 prompt/schema binding drifted")
    return {"files": records, "failure_manifest_sha256": pass_record["sha256"], "artifact_list_sha256": _manifest_sha256(records)}


def bind_predecessor(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = _manifest(root)
    if len(manifest) != PREDECESSOR["file_count"] or _manifest_sha256(manifest) != PREDECESSOR["manifest_sha256"]:
        raise ValueError("Full predecessor manifest drifted")
    frozen_path, journal_path = root / "frozen-run-contract.json", root / "schedule-journal.jsonl"
    if sha(frozen_path) != PREDECESSOR["frozen_contract_sha256"] or sha(journal_path) != PREDECESSOR["journal_sha256"]:
        raise ValueError("Predecessor contract or journal drifted")
    frozen = read_json(frozen_path)
    expected = plans(frozen)
    records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    if records[:330] != expected or len(records) != 406:
        raise ValueError("Predecessor journal does not contain the sealed plan plus exact prefix")
    completed = records[330:]
    for ordinal, record in enumerate(completed, 1):
        plan = expected[ordinal - 1]
        binding = record.get("run_binding_sha256")
        if record != {**plan, "event": "completed", "run_binding_sha256": binding} or not isinstance(binding, str) or len(binding) != 64:
            raise ValueError("Predecessor accepted prefix is not contiguous")
    if expected[76]["sequence"] != 77 or completed[-1]["sequence"] != 76:
        raise ValueError("Successor must begin exactly at sequence 77")
    for relative, digest in REJECTIONS.items():
        if sha(root / relative) != digest:
            raise ValueError("Historical rejection artifact drifted")
    sessions = _session_ids(root)
    if _session_sha256(sessions) != PREDECESSOR["sessions_sha256"]:
        raise ValueError("Predecessor session commitment drifted")
    return {
        "root_manifest": {"file_count": len(manifest), "sha256": _manifest_sha256(manifest)},
        "frozen_contract_sha256": sha(frozen_path),
        "journal_sha256": sha(journal_path),
        "accepted_prefix": {"count": 76, "first_sequence": 1, "last_sequence": 76},
        "historical_rejections": [{"path": path, "sha256": digest} for path, digest in REJECTIONS.items()],
        "sequence77_failure": {"accepted": False, "artifact_list": _sequence77_artifacts(root), "prompt_sha256": PREDECESSOR["sequence77_prompt_sha256"], "schema_sha256": PREDECESSOR["sequence77_schema_sha256"]},
        "sessions": {"count": len(sessions), "sha256": _session_sha256(sessions), "ids_sha256": [hashlib.sha256(item.encode("utf-8")).hexdigest() for item in sessions]},
        "schedule_sha256": hashlib.sha256(canonical(expected)).hexdigest(),
    }
