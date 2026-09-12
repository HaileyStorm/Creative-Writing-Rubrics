from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1"
BROKER = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\broker.py")


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def wave(callback: Any) -> list[dict[str, Any] | None]:
    barrier = threading.Barrier(10); results: list[dict[str, Any] | None] = [None] * 10
    def worker(index: int) -> None:
        barrier.wait()
        try: callback()
        except BaseException as error:  # noqa: BLE001 - collision witness records every failure.
            results[index] = {"success": False, "error": error}
        else: results[index] = {"success": True, "error": None}
    threads = [threading.Thread(target=worker, args=(index,)) for index in range(10)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert all(result is not None for result in results)
    return results


def test_original_broker_loader_collides() -> None:
    recovery = load(DIRECTORY / "recovery.py", "wpb_recovery_original")
    results = wave(lambda: recovery._load_broker(BROKER))
    assert any(not result["success"] for result in results if result)


def test_configured_broker_loader_all_workers_succeed() -> None:
    adapter = load(DIRECTORY / "sol_frozen_import_serialization.py", "wpb_import_adapter")
    for name in list(sys.modules):
        if name == "_wpb_recovery_model_work_queue" or name.startswith("_wpb_recovery_model_work_queue."):
            sys.modules.pop(name, None)
    recovery = adapter.install_on_legacy(load(DIRECTORY / "recovery.py", "wpb_recovery_serialized"), {})
    results = wave(lambda: recovery._load_broker(BROKER))
    assert len(results) == 10 and all(result and result["success"] for result in results)


def test_configured_nested_v5_selection_recovery_broker_path_succeeds() -> None:
    adapter = load(DIRECTORY / "sol_frozen_import_serialization.py", "wpb_import_nested_adapter")
    v5 = adapter.install_on_legacy(load(DIRECTORY / "grok_selection_freeze_v5.py", "wpb_import_nested_v5"), {})

    def nested() -> None:
        selection = v5._pinned_selection()
        recovery = selection._pinned_recovery()
        recovery._load_broker(BROKER)

    results = wave(nested)
    assert len(results) == 10 and all(result and result["success"] for result in results)


def test_configured_continuation_suffix_broker_path_succeeds() -> None:
    adapter = load(DIRECTORY / "sol_frozen_import_serialization.py", "wpb_import_continuation_adapter")
    continuation = adapter.install_on_legacy(load(DIRECTORY / "recovery_v5_continuation.py", "wpb_import_continuation"), {})

    def nested() -> None:
        suffix = continuation._load(continuation.FROZEN_HELPER, continuation.FROZEN_HELPER_SHA256, "wpb_import_suffix")
        recovery = suffix._frozen()
        recovery._load_broker(BROKER)

    results = wave(nested)
    assert len(results) == 10 and all(result and result["success"] for result in results)


def test_manifest_is_self_bound() -> None:
    adapter = load(DIRECTORY / "sol_frozen_import_serialization.py", "wpb_import_manifest")
    assert adapter.source_manifest()["successor"]["path"] == str((DIRECTORY / "sol_frozen_import_serialization.py").resolve())


def test_post_import_work_can_overlap_across_all_workers() -> None:
    adapter = load(DIRECTORY / "sol_frozen_import_serialization.py", "wpb_import_overlap")
    recovery = adapter.install_on_legacy(load(DIRECTORY / "recovery.py", "wpb_overlap_recovery"), {})
    imported = threading.Barrier(10)

    def import_then_work() -> None:
        recovery._load_broker(BROKER)
        imported.wait(timeout=30)

    results = wave(import_then_work)
    assert len(results) == 10 and all(result and result["success"] for result in results)
