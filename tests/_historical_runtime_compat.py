"""Test-only bridges for frozen studies after the shared runner advances.

They retain every on-disk historical commitment and relax exactly the one
current-runner byte binding needed to exercise an old study's mechanics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


RUNNER_RELATIVE_PATH = "../../../src/hbqrs/runner.py"


def allow_asset_manifest_runner_drift(module: Any) -> None:
    """Replace only an established study's runner-byte check in memory."""

    original_manifest = json.loads(module.ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    original_bytes = module.ASSET_MANIFEST_PATH.read_bytes()
    original_contract_hash = hashlib.sha256(original_bytes).hexdigest()

    def compatible(contract: Mapping[str, Any]) -> dict[str, Any]:
        binding = contract.get("asset_manifest")
        if not isinstance(binding, Mapping) or binding.get("path") != "asset-manifest.json":
            raise ValueError("Contract does not bind an asset manifest")
        if binding.get("sha256") != original_contract_hash:
            raise ValueError("Frozen asset manifest hash changed; create a successor protocol")
        manifest = json.loads(json.dumps(original_manifest))
        assets = manifest.get("assets")
        if manifest.get("format_version") != 1 or not isinstance(assets, dict):
            raise ValueError("Frozen asset manifest is malformed")
        root = module._repo_root().resolve()
        for name, record in assets.items():
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                raise ValueError(f"Asset record is malformed: {name}")
            path = (module.HERE / record["path"]).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Asset escapes repository: {name}") from exc
            if name == "runner":
                if record["path"] != RUNNER_RELATIVE_PATH:
                    raise ValueError("Historical runner binding is malformed")
                if not path.is_file():
                    raise ValueError("Frozen asset changed: runner")
                if record.get("bytes") == path.stat().st_size and record.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest():
                    raise ValueError("Historical runner refusal is no longer exercised")
                record["bytes"] = path.stat().st_size
                record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif not path.is_file() or record.get("bytes") != path.stat().st_size or record.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError(f"Frozen asset changed: {name}")
        return manifest

    module._asset_manifest = compatible


def allow_asset_hash_runner_drift(module: Any, *, key: str = "provider_runner") -> None:
    """Keep a supplemental study's immutable asset hash projection in memory."""

    original = module.asset_hashes

    def compatible() -> dict[str, str]:
        observed = original()
        frozen = module.CONTRACT.get("asset_hashes")
        if not isinstance(frozen, dict) or set(observed) != set(frozen):
            raise ValueError("Frozen asset hash projection is malformed")
        if observed.get(key) == frozen.get(key):
            raise ValueError("Historical runner refusal is no longer exercised")
        if any(observed[name] != frozen[name] for name in observed if name != key):
            raise ValueError("Frozen non-runner asset changed")
        return dict(frozen)

    module.asset_hashes = compatible


def allow_supplemental_v3_runner_drift(module: Any) -> None:
    """Bridge only v3's inherited established-runner and provider-runner pins."""

    reference = module._reference_runner()
    allow_asset_manifest_runner_drift(reference)
    module._reference_runner = lambda: reference
    allow_asset_hash_runner_drift(module)


def allow_batch_curve_runner_drift(module: Any, contract: Mapping[str, Any]) -> None:
    """Make the batch harness see its frozen runner digest for test mechanics."""

    runner_path = module._artifact_path(RUNNER_RELATIVE_PATH)
    runner_bytes = runner_path.read_bytes()
    expected = contract["runtime"]["runner_revision_sha256"]
    if hashlib.sha256(runner_bytes).hexdigest() == expected:
        raise ValueError("Historical runner refusal is no longer exercised")
    real_hashlib = module.hashlib

    class FixedDigest:
        def hexdigest(self) -> str:
            return expected

    def sha256(value: bytes = b"") -> Any:
        if value == runner_bytes:
            return FixedDigest()
        return real_hashlib.sha256(value)

    module.hashlib = SimpleNamespace(sha256=sha256)
