from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
from typing import Any, Iterator, Mapping


HISTORICAL_INPUTS = (
    ("registry", "registry/all_modules.json"),
    ("bundles", "bundles/all_bundles.json"),
)


def _is_reparse_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & 0x400)


def _mounted_root(runtime: Path, snapshot_root: Path | None) -> Path:
    root = snapshot_root if snapshot_root is not None else runtime
    if _is_reparse_like(root) or not root.is_dir():
        raise ValueError("Fresh88 historical runtime root must be a real directory")
    return root


def _normalize_crlf(data: bytes, *, label: str) -> bytes:
    newline_count = data.count(b"\n")
    crlf_count = data.count(b"\r\n")
    bare_cr_count = data.count(b"\r") - crlf_count
    if newline_count == 0 or bare_cr_count or crlf_count not in (0, newline_count):
        raise ValueError(f"Fresh88 {label} historical input has mixed or bare-CR line endings")
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _source_bytes(
    plan: Mapping[str, Any], freeze_receipt: Mapping[str, Any], runtime: Path, *, label: str, relative: str, snapshot_root: Path | None
) -> tuple[bytes, dict[str, Any]]:
    base = plan.get("base_frozen")
    binding = base.get(label) if isinstance(base, Mapping) else None
    if not isinstance(binding, Mapping) or not isinstance(binding.get("bytes"), int) or isinstance(binding.get("bytes"), bool) or binding["bytes"] < 1 or not isinstance(binding.get("sha256"), str) or len(binding["sha256"]) != 64:
        raise ValueError(f"Fresh88 {label} plan binding is malformed")
    expected = {"bytes": binding["bytes"], "sha256": binding["sha256"]}
    source_map = freeze_receipt.get("runtime_source_map")
    receipt_binding = source_map.get(relative) if isinstance(source_map, Mapping) else None
    if not isinstance(receipt_binding, Mapping) or receipt_binding.get("source") != "current_copy":
        raise ValueError(f"Fresh88 {label} freeze receipt lacks a current-copy binding")
    if receipt_binding.get("entry") != f"current-runtime/{relative}":
        raise ValueError(f"Fresh88 {label} freeze receipt requires the exact current-runtime entry")
    receipt_expected = {"bytes": receipt_binding.get("bytes"), "sha256": receipt_binding.get("sha256")}
    if receipt_expected != expected:
        raise ValueError(f"Fresh88 {label} plan and freeze-receipt bindings disagree")
    root = _mounted_root(runtime, snapshot_root)
    candidate = root / relative
    try:
        if _is_reparse_like(candidate) or not candidate.is_file():
            raise ValueError
        candidate.resolve().relative_to(root.resolve())
        data = _normalize_crlf(candidate.read_bytes(), label=label)
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("Fresh88 "):
            raise
        raise ValueError(f"Fresh88 {label} historical runtime input is unavailable") from error
    if {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} != expected:
        raise ValueError(f"Fresh88 {label} historical CRLF snapshot does not match its frozen binding")
    return data, expected


def project_plan(
    plan: Mapping[str, Any],
    freeze_receipt: Mapping[str, Any],
    runtime: Path,
    *,
    snapshot_root: Path | None = None,
    projection_root: Path,
) -> dict[str, Any]:
    projected_plan = deepcopy(plan)
    projected_base = projected_plan.get("base_frozen")
    if not isinstance(projected_base, dict):
        raise ValueError("Fresh88 execution plan lacks a mutable base projection")
    projection_root.mkdir(parents=True, exist_ok=True)
    for label, relative in HISTORICAL_INPUTS:
        data, expected = _source_bytes(plan, freeze_receipt, runtime, label=label, relative=relative, snapshot_root=snapshot_root)
        target = projection_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if {"bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()} != expected:
            raise ValueError(f"Fresh88 projected {label} bytes failed exact CRLF verification")
        _normalize_crlf(target.read_bytes(), label=label)
        binding = dict(projected_base[label])
        binding["path"] = str(target)
        projected_base[label] = binding
    return projected_plan


@contextmanager
def historical_input_projection(
    analysis_module: Any, *, runtime: Path, snapshot_root: Path | None = None
) -> Iterator[None]:
    """Temporarily route a loaded analysis module through exact test-only inputs."""
    original_load_inputs = analysis_module._load_inputs
    with tempfile.TemporaryDirectory(prefix="fresh88-historical-inputs-") as temporary:
        projection_root = Path(temporary)

        def projected_load_inputs(work: Path, authority: Path, artifacts: Path, historical_runtime: Path):
            frozen, freeze_receipt, plan, work_artifacts = original_load_inputs(work, authority, artifacts, historical_runtime)
            projected = project_plan(
                plan,
                freeze_receipt,
                Path(historical_runtime),
                snapshot_root=snapshot_root,
                projection_root=projection_root,
            )
            return frozen, freeze_receipt, projected, work_artifacts

        analysis_module._load_inputs = projected_load_inputs
        try:
            yield
        finally:
            analysis_module._load_inputs = original_load_inputs
