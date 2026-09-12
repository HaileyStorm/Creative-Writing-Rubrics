"""Provider-free checks for recovered-prefix runtime-data admission."""

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
ADAPTER = PACKAGE / "baseline_recovered_data_admission.py"
LOADER = PACKAGE / "baseline_runtime_data_snapshot_v4.py"
SOURCE_HELPER = PACKAGE / "baseline_grok_v5_suffix.py"
FROZEN_RECOVERED = PACKAGE / "baseline_recovered_study.py"
SHARED = PACKAGE / "baseline_native_data_admission.py"
EPOCH = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-local254-continuation-20260910-r1\suffix-epoch.json")
PLAN = Path(r"C:\Users\Haile\Documents\cwr-dryad-baseline8-plan-20260906-r1\plan.json")
SNAPSHOT = Path(r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\snapshot-manifest.json")
ROUTES = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok51-recovery-20260907-r1\native")
RECOVERED_RUN = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok70-study-recovery-20260908-r1\run")
EPOCH_SHA256 = "74012a612915137c43e35eff5bb64b413be0b2dabbdc3aa52ceb4b88d1a245d6"
SNAPSHOT_SHA256 = "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"
RECOVERED_MANIFEST_SHA256 = "2605dba0333f8648b25644c34400965b34d1c151b0e3793962eb88721a70607a"
ADOPTION_SHA256 = "ff3e1a1f4038e48c13341c290e20c1b50285593cf9c8c76d476e4dcca014b8ca"
AMENDMENT_SHA256 = "1ff8b1cc48d3c00bc68a2a0611de0464f025803da5621f6e01312669d86cf3b3"


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
    adapter = load(ADAPTER, "baseline_recovered_data_admission_test")
    loader = load(LOADER, "baseline_recovered_data_admission_loader_test")
    helper = load(SOURCE_HELPER, "baseline_recovered_data_admission_source_test")
    epoch_raw = EPOCH.read_bytes()
    assert digest(epoch_raw) == EPOCH_SHA256
    runtime = loader.load_old_runtime_from_epoch(json.loads(epoch_raw), snapshot_manifest_path=SNAPSHOT, expected_snapshot_manifest_sha256=SNAPSHOT_SHA256)
    plan = json.loads(PLAN.read_bytes())
    source = helper._source_for_pass(PLAN.parent, plan["passes"][3])
    descriptor = {"epoch": {"path": str(EPOCH), "sha256": EPOCH_SHA256}, "schema": runtime.provenance["data"]["schema_pins"][0]}
    return {"adapter": adapter, "runtime": runtime, "source": source, "routes": routes(), "descriptor": descriptor}


def test_replays_actual_eleven_batch_prefix_with_explicit_runtime_data(replay_context: dict[str, Any]) -> None:
    recovered_before = FROZEN_RECOVERED.read_bytes()
    shared_before = SHARED.read_bytes()
    loader_before = LOADER.read_bytes()
    result = replay_context["adapter"].admit_prefix_with_runtime_data(
        RECOVERED_RUN, source=replay_context["source"], batch_size=8, approved_routes=replay_context["routes"], expected_batches=11,
        expected_recovered_manifest_sha256=RECOVERED_MANIFEST_SHA256, expected_adoption_sha256=ADOPTION_SHA256,
        expected_amendment_sha256=AMENDMENT_SHA256, runtime=replay_context["runtime"], snapshot_descriptor=replay_context["descriptor"],
    )
    assert result["evidence_class"] == "mixed_native_and_study_recovered_record_replay"
    assert result["native_record_count"] == len(result["native_identities"]) == 10
    assert result["study_recovered_record_count"] == 1 and result["study_recovered_ordinals"] == [70]
    assert result["accepted_count"] == len(result["verdicts"]) == 88
    provenance = result["runtime_data_provenance"]
    assert provenance["schema"]["sha256"] == "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"
    assert provenance["frozen_recovered_study"]["sha256"] == "573fbd9b05659aff80c7db4dfae9cf7c7c549b7e28d99260c50a98aa458bb8b3"
    assert provenance["data"]["current_canonical_schema"]["preserved"] is True
    assert FROZEN_RECOVERED.read_bytes() == recovered_before and SHARED.read_bytes() == shared_before and LOADER.read_bytes() == loader_before


def test_rejects_altered_explicit_schema_metadata(replay_context: dict[str, Any]) -> None:
    shared = replay_context["adapter"]._shared()
    config = json.loads((RECOVERED_RUN / "run.json").read_bytes())["configuration"]
    altered = copy.deepcopy(config)
    altered["response_schema"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Judge instruction/schema metadata"):
        shared._metadata(altered, schema_descriptor=replay_context["descriptor"]["schema"])
    descriptor = copy.deepcopy(replay_context["descriptor"])
    descriptor["schema"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="schema descriptor binding"):
        replay_context["adapter"].admit_prefix_with_runtime_data(
            RECOVERED_RUN, source=replay_context["source"], batch_size=8, approved_routes=replay_context["routes"], expected_batches=11,
            expected_recovered_manifest_sha256=RECOVERED_MANIFEST_SHA256, expected_adoption_sha256=ADOPTION_SHA256,
            expected_amendment_sha256=AMENDMENT_SHA256, runtime=replay_context["runtime"], snapshot_descriptor=descriptor,
        )
