from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1"
SOURCE = DIRECTORY / "sol_frozen_core_serialization.py"
V5 = DIRECTORY / "grok_selection_freeze_v5.py"
SCHEMA = DIRECTORY / "schema_recovery.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def concurrent(callback: Any) -> list[dict[str, Any] | None]:
    barrier = threading.Barrier(10)
    results: list[dict[str, Any] | None] = [None] * 10

    def worker(index: int) -> None:
        barrier.wait()
        try:
            callback()
        except BaseException as error:  # noqa: BLE001 - the probe must record every worker failure.
            results[index] = {"success": False, "error": error}
        else:
            results[index] = {"success": True, "error": None}

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(10)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert all(result is not None for result in results)
    return results


def test_original_frozen_core_loader_collides_under_concurrency() -> None:
    schema = load(SCHEMA, "wpb_schema_original_collision")
    results = concurrent(schema._load_frozen_core)
    assert sum(isinstance(result["error"], ValueError) for result in results if result) >= 1


def test_configured_v5_uses_one_shared_narrow_loader_lock() -> None:
    adapter = load(SOURCE, "wpb_frozen_core_adapter")
    v5 = load(V5, "wpb_v5_serialized")
    state: dict[str, Any] = {}
    adapter.configure_v5_verifier(v5, state)

    def callback() -> None:
        selection = v5._pinned_selection()
        helper = selection._module(selection.SCHEMA_RECOVERY_HELPER, "wpb_schema_serialized")
        helper._load_frozen_core()

    results = concurrent(callback)
    assert len(results) == 10 and all(result and result["success"] for result in results)
    assert adapter.source_manifest() == v5._wpb_frozen_core_serialization_manifest


def test_wrong_v5_pin_is_rejected() -> None:
    adapter = load(SOURCE, "wpb_frozen_core_wrong_pin")
    v5 = load(V5, "wpb_v5_wrong_pin")
    adapter.V5_SHA256 = "0" * 64
    with pytest.raises(ValueError, match="historical v5 verifier differs"):
        adapter.configure_v5_verifier(v5, {})
