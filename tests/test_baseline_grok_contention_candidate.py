from __future__ import annotations

import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_contention_candidate.py"
CANDIDATE = Path(r"C:\Users\Haile\Documents\Codex\2026-08-12\universal-harness\work\grok-host-gate-contention-candidate-20260912\isolated\candidate-gate-contention-v1")


def load() -> Any:
    spec = importlib.util.spec_from_file_location("grok_contention_candidate_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_candidate(tmp_path: Path) -> Path:
    destination = tmp_path / "candidate"
    manifest_path = CANDIDATE / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for item in manifest["files"]:
        source = CANDIDATE / item["path"]
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    destination.mkdir(exist_ok=True)
    (destination / "candidate-manifest.json").write_bytes(manifest_path.read_bytes())
    return destination


def test_actual_sealed_candidate_has_one_concurrent_code_module() -> None:
    value = load()
    with ThreadPoolExecutor(max_workers=10) as executor:
        modules = list(executor.map(lambda _: value.load_candidate(CANDIDATE, value.CANDIDATE_MANIFEST_SHA256)[0], range(10)))
    assert len({id(module) for module in modules}) == 1
    assert Path(modules[0].__file__).resolve() == (CANDIDATE / "model_work_queue" / "broker.py").resolve()
    assert not list(CANDIDATE.rglob("__pycache__"))


def test_verified_copy_is_inert_and_source_or_cache_drift_is_rejected(tmp_path: Path) -> None:
    value = load()
    candidate = copy_candidate(tmp_path)
    verified = value.verify_candidate(candidate, value.CANDIDATE_MANIFEST_SHA256)
    assert verified == {
        "manifest_sha256": value.CANDIDATE_MANIFEST_SHA256,
        "broker_path": str((candidate / "model_work_queue" / "broker.py").resolve()),
        "provider_calls_made": 0,
        "staging_record": {"provider_invocations": 0, "activation_performed": False, "installation_performed": False},
    }
    broker = candidate / "model_work_queue" / "broker.py"
    broker.write_bytes(broker.read_bytes() + b"\n# source drift\n")
    with pytest.raises(ValueError, match="candidate root drift"):
        value.load_candidate(candidate, value.CANDIDATE_MANIFEST_SHA256)
    candidate = copy_candidate(tmp_path / "cache")
    value.load_candidate(candidate, value.CANDIDATE_MANIFEST_SHA256)
    cache = candidate / "model_work_queue" / "__pycache__" / "broker.pyc"
    cache.parent.mkdir()
    cache.write_bytes(hashlib.sha256(b"cache drift").digest())
    with pytest.raises(ValueError, match="candidate root drift"):
        value.load_candidate(candidate, value.CANDIDATE_MANIFEST_SHA256)
