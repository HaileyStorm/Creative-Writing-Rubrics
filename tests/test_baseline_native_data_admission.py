"""Provider-free checks for the explicit V4 schema-data admission adapter."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1"
ADAPTER = PACKAGE / "baseline_native_data_admission.py"
LOADER = PACKAGE / "baseline_runtime_data_snapshot_v4.py"
SOURCE_HELPER = PACKAGE / "baseline_grok_v5_suffix.py"
FROZEN_NATIVE = PACKAGE / "native_admission.py"
EPOCH = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-local254-continuation-20260910-r1\suffix-epoch.json")
PLAN = Path(r"C:\Users\Haile\Documents\cwr-dryad-baseline8-plan-20260906-r1\plan.json")
SNAPSHOT = Path(r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\snapshot-manifest.json")
ROUTES = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok51-recovery-20260907-r1\native")
NATIVE_RUN = ROUTES / "runs/baseline8-v1/train/0001/dryad-00a698c1870a4ce884189546"
EPOCH_SHA256 = "74012a612915137c43e35eff5bb64b413be0b2dabbdc3aa52ceb4b88d1a245d6"
SNAPSHOT_SHA256 = "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def routes() -> dict[str, dict[str, Any]]:
    value = {}
    for cohort in range(1, 9):
        root = ROUTES / f"cohorts/{cohort:04d}"
        review = json.loads((root / "review.json").read_bytes())
        prepared_raw = (root / "prepared.json").read_bytes()
        prepared = json.loads(prepared_raw)
        route_raw = (root / "route.json").read_bytes()
        route = json.loads(route_raw)
        assert review["decision"] == "approved_cohort" and review["prepared_sha256"] == digest(prepared_raw)
        assert prepared["route_sha256"] == digest(route_raw) == digest(canonical(route))
        value[prepared["route_sha256"]] = route
    assert len(value) == 5
    return value


@pytest.fixture(scope="module")
def replay_context() -> dict[str, Any]:
    adapter = load(ADAPTER, "baseline_native_data_admission_test")
    loader = load(LOADER, "baseline_runtime_data_snapshot_v4_admission_test")
    helper = load(SOURCE_HELPER, "baseline_grok_v5_suffix_admission_test")
    epoch_raw = EPOCH.read_bytes()
    assert digest(epoch_raw) == EPOCH_SHA256
    epoch = json.loads(epoch_raw)
    runtime = loader.load_old_runtime_from_epoch(epoch, snapshot_manifest_path=SNAPSHOT, expected_snapshot_manifest_sha256=SNAPSHOT_SHA256)
    plan = json.loads(PLAN.read_bytes())
    source = helper._source_for_pass(PLAN.parent, plan["passes"][0])
    descriptor = {"epoch": {"path": str(EPOCH), "sha256": EPOCH_SHA256}, "schema": runtime.provenance["data"]["schema_pins"][0]}
    return {"adapter": adapter, "runtime": runtime, "source": source, "routes": routes(), "descriptor": descriptor}


def test_replays_actual_first_pass_without_altering_frozen_sources(replay_context: dict[str, Any]) -> None:
    frozen_before = FROZEN_NATIVE.read_bytes()
    loader_before = LOADER.read_bytes()
    result = replay_context["adapter"].admit_pass_with_runtime_data(NATIVE_RUN, source=replay_context["source"], batch_size=8, approved_routes=replay_context["routes"], runtime=replay_context["runtime"], snapshot_descriptor=replay_context["descriptor"])
    assert result["evidence_class"] == "native_record_replay_with_explicit_historical_schema_data"
    assert len(result["native_identities"]) == 23 and len(result["verdicts"]) == 178
    provenance = result["runtime_data_provenance"]
    assert provenance["frozen_native_admission"]["sha256"] == "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
    assert provenance["schema"]["sha256"] == "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"
    assert provenance["data"]["current_canonical_schema"]["preserved"] is True
    assert FROZEN_NATIVE.read_bytes() == frozen_before and LOADER.read_bytes() == loader_before


def test_rejects_wrong_schema_descriptor_before_checkpoint_replay(replay_context: dict[str, Any]) -> None:
    descriptor = copy.deepcopy(replay_context["descriptor"])
    descriptor["schema"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="schema descriptor binding"):
        replay_context["adapter"].admit_pass_with_runtime_data(NATIVE_RUN, source=replay_context["source"], batch_size=8, approved_routes=replay_context["routes"], runtime=replay_context["runtime"], snapshot_descriptor=descriptor)


def test_rejects_wrong_epoch_and_source_bindings(replay_context: dict[str, Any]) -> None:
    epoch_descriptor = copy.deepcopy(replay_context["descriptor"])
    epoch_descriptor["epoch"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="runtime epoch differs"):
        replay_context["adapter"].admit_pass_with_runtime_data(NATIVE_RUN, source=replay_context["source"], batch_size=8, approved_routes=replay_context["routes"], runtime=replay_context["runtime"], snapshot_descriptor=epoch_descriptor)
    source = {**replay_context["source"], "story_text": "different source"}
    with pytest.raises(ValueError, match="Story source binding differs"):
        replay_context["adapter"].admit_pass_with_runtime_data(NATIVE_RUN, source=source, batch_size=8, approved_routes=replay_context["routes"], runtime=replay_context["runtime"], snapshot_descriptor=replay_context["descriptor"])
