"""Frozen v5 batch-8 schedule derived from the immutable v4 compatibility snapshot."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STUDY_ID = "hbq-human-alignment-supplemental-providers-v5"
ACKNOWLEDGEMENT_SHA256 = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
MODEL = "deepseek/deepseek-v4-flash-0731"
PREPARED_FILES = frozenset({"prepared.json", "schedule.json", "inputs.json", "runtime.json", "disclosure.json", "authorization-acknowledgement.json", "zero-new-spend-route-proof.json", "scope-compatibility-override.json"})


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def fingerprint(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    raw = canonical(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if stable_bytes(path) != raw:
                raise ValueError(f"immutable record drifted: {path}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def plain_entry(path: Path, *, directory: bool = False) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"v5 path is reparsed: {path}")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError(f"v5 path type drifted: {path}")


def stable_bytes(path: Path) -> bytes:
    path = path.resolve(strict=True)
    plain_entry(path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"v5 file changed while read: {path}")
    return raw


def read_json(path: Path, *, canonical_required: bool = True) -> dict[str, Any]:
    try:
        raw = stable_bytes(path)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"v5 JSON is unreadable: {path}") from error
    if not isinstance(value, dict) or (canonical_required and canonical(value) != raw):
        raise ValueError(f"v5 JSON is not canonical: {path}")
    return value


def runtime_bindings() -> dict[str, dict[str, Any]]:
    runner = ROOT / "src" / "hbqrs" / "runner.py"
    launcher = Path.home() / ".codex" / "tools" / "launch-bridge.ps1"
    bridge = launcher.parent / "nous_codex_bridge.py"
    required = {"runner": runner, "launcher": launcher, "bridge": bridge}
    if any(not path.is_file() for path in required.values()):
        raise ValueError("current Nous runtime is unavailable")
    return {name: fingerprint(path) for name, path in required.items()}


def _input_folder(v4_frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> Path:
    parent = Path(str(v4_frozen.get("failed_v2", {}).get("v1_parent_work_dir", "")))
    parent_frozen = read_json(parent / "frozen-provider-contract.json", canonical_required=False)
    primary = Path(str(parent_frozen.get("primary_work_dir", "")))
    folder = primary / "inputs" / "development" / str(cell["item_id"])
    expected = cell.get("inputs")
    actual = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
    if actual != expected:
        raise ValueError("v5 immutable v4 input lineage drifted")
    return folder


def load_v4_cells(v4_work_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frozen = read_json(v4_work_dir / "frozen-transport-contract.json", canonical_required=False)
    if frozen.get("study_id") != "hbq-human-alignment-supplemental-providers-v4" or frozen.get("frozen_before_execution") is not True or frozen.get("provider_calls_made") != 0:
        raise ValueError("v5 requires a provider-free v4 compatibility freeze")
    historical = frozen.get("failed_v2", {}).get("cells")
    if not isinstance(historical, list) or len(historical) != 3:
        raise ValueError("v4 snapshot lacks three historical cells")
    cells: list[dict[str, Any]] = []
    for index, old in enumerate(historical, 1):
        if not isinstance(old, Mapping):
            raise TypeError("v4 historical cell is malformed")
        questions = old.get("question_ids")
        if not isinstance(questions, list) or len(questions) != 16 or len(set(questions)) != 16:
            raise ValueError("v4 historical question lineage is malformed")
        folder = _input_folder(frozen, old)
        cells.append({
            "cell_id": f"pilot-{index:02d}",
            "historical_cell_id": old.get("cell_id"),
            "item_id": old.get("item_id"),
            "selection": old.get("selection"),
            "inputs": old.get("inputs"),
            "input_folder": str(folder),
            "question_ids": questions[:8],
            "historical_question_ids_sha256": sha_bytes(canonical(questions)),
        })
    if len({str(cell["item_id"]) for cell in cells}) != 3:
        raise ValueError("v5 needs three distinct v4 cells")
    return frozen, cells


def scope_compatibility_override(cell: Mapping[str, Any]) -> dict[str, Any]:
    contract_path = Path(str(cell["input_folder"])) / "task-contract.json"
    contract = read_json(contract_path, canonical_required=False)
    context = contract.get("context")
    if not isinstance(context, Mapping):
        raise TypeError("v5 task contract lacks scope context")
    return {
        "format_version": 1,
        "artifact_id": cell["item_id"],
        "bundle_id": "prose.short_story",
        "task_contract_sha256": cell["inputs"]["task-contract.json"]["sha256"],
        "contract_id": contract.get("contract_id"),
        "artifact_kind": context.get("artifact_kind"),
        "declared_scope": context.get("declared_scope"),
        "compatibility_mode": "reviewed_override",
        "decision_id": "hanna-nous-v5-batch8-reviewed-compatibility",
        "reviewer": "CWR/HBQ-RS continuity owner",
        "reason": "Reviewed existing HANNA task-contract scope for the bounded prose.short_story diagnostic.",
    }


def validate_route_proof(proof: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "provider": "nous", "model": MODEL, "reasoning": "max", "tools_enabled": False,
        "zero_new_spend_existing_credit_only": True, "paid_fallback_forbidden": True, "armed": True,
    }
    if any(proof.get(name) != value for name, value in expected.items()):
        raise ValueError("v5 route proof is not the exact armed zero-new-spend existing-credit tool-free Nous route")
    if not isinstance(proof.get("checked_at"), str) or not isinstance(proof.get("expires_at"), str):
        raise TypeError("v5 route proof lacks currentness bounds")
    try:
        checked_at = datetime.fromisoformat(proof["checked_at"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(proof["expires_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("v5 route proof has invalid currentness bounds") from error
    now = datetime.now(UTC)
    if checked_at.tzinfo is None or expires_at.tzinfo is None or checked_at > now or expires_at <= now or expires_at <= checked_at:
        raise ValueError("v5 route proof is not currently valid")
    return dict(proof)


def fresh_root(path: Path) -> None:
    parent = path.parent
    plain_entry(parent, directory=True)
    if path.exists():
        raise ValueError("v5 requires a fresh nonexistent output root")
    try:
        path.mkdir()
    except FileExistsError as error:
        raise ValueError("v5 output-root creation raced") from error
