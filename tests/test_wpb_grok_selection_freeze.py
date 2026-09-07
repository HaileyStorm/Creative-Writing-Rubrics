from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/grok_selection_freeze.py"


def load():
    spec = importlib.util.spec_from_file_location("wpb_grok_selection_freeze_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: object) -> str:
    raw = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(raw).hexdigest()


def response(number: int) -> dict[str, object]:
    score_a, score_b = (5, 1) if number % 2 == 0 else (1, 5)
    return {
        side: {
            "scores": {"core": score, "craft": score, "form": score},
            "coverage": {"core": "assessed", "craft": "assessed", "form": "assessed"},
            "evidence": {"core": "synthetic", "craft": "synthetic", "form": "synthetic"},
        }
        for side, score in (("A", score_a), ("B", score_b))
    }


class SyntheticCore:
    STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"

    @staticmethod
    def canonical(value: object) -> bytes:
        return canonical(value)

    @staticmethod
    def sha256(value: object) -> str:
        return digest(value)

    def build_tasks(self, _freeze_root: Path) -> dict[str, object]:
        return {
            "tasks": [
                {"cell_id": f"cell-{number:03d}", "payload_sha256": digest(f"payload-{number}"), "partition": "train" if number < 105 else "dev"}
                for number in range(129)
            ]
        }

    def analyze(self, _freeze_root: Path, measurements: list[dict[str, object]], _profile: dict[str, float]) -> dict[str, object]:
        assert len(measurements) == 129
        assert {measurement["endpoint"] for measurement in measurements} == {"grok"}
        ordered = [
            {key: measurement[key] for key in ("endpoint", "cell_id", "payload_sha256", "measurement_provenance")}
            for measurement in sorted(measurements, key=lambda value: str(value["cell_id"]))
        ]
        return {
            "native_admission": "not_claimed",
            "mae": "not_applicable_pairwise_preference_target",
            "ordered_measurement_commitment_sha256": digest(ordered),
        }

    def fit_train_select_dev(self, _freeze_root: Path, measurements: list[dict[str, object]], *, trials: int) -> dict[str, object]:
        assert trials == 128
        assert len(measurements) == 129
        return {
            "study_id": self.STUDY_ID,
            "optuna": {"version": "4.9.0", "seed": 20260904, "trials": 128},
            "selected_profile_name": "all_one",
            "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
            "confirmation": "unopened_no_api_surface",
        }


class SyntheticRecovery:
    STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"
    PLAN_NAME = "recovery-plan.json"

    def __init__(self, plan: dict[str, object], root: Path) -> None:
        self.plan, self.root = plan, root

    def _read_plan(self, root: Path, expected: str) -> dict[str, object]:
        assert root == self.root
        assert expected == digest((self.root / self.PLAN_NAME).read_bytes())
        return self.plan

    def _verify_origin(self, plan: dict[str, object]) -> None:
        assert plan is self.plan

    @staticmethod
    def _load_legacy() -> object:
        return SimpleNamespace()

    def _rows(self, _legacy: object, _freeze_root: Path):
        rows = tuple(
            {"cell_id": f"cell-{number:03d}", "payload_sha256": digest(f"payload-{number}")}
            for number in range(129)
        )
        return {"rows": rows, "schedule_sha256": self.plan["schedule_sha256"]}, {row["cell_id"]: row for row in rows}

    def _legacy_prefix(self, *, plan: dict[str, object]):
        assert plan is self.plan
        values = [measurement(number) for number in range(89)]
        return values, {str(value["cell_id"]) for value in values}

    def _verify_admission(self, plan: dict[str, object], root: Path, cell: dict[str, object]):
        assert plan is self.plan and root == self.root
        number = int(str(cell["cell_id"]).split("-")[1])
        return {
            "cell_id": cell["cell_id"],
            "payload_sha256": cell["payload_sha256"],
            "response": response(number),
            "result_sha256": digest(f"result-{number}"),
            "envelope_sha256": digest(f"envelope-{number}"),
            "identity_sha256": digest(f"identity-{number}"),
            "request_id_sha256": digest(f"request-{number}"),
            "session_id_sha256": digest(f"session-{number}"),
        }


def measurement(number: int) -> dict[str, object]:
    body = response(number)
    payload = digest(f"payload-{number}")
    return {
        "endpoint": "grok",
        "cell_id": f"cell-{number:03d}",
        "payload_sha256": payload,
        "measurement_provenance": {
            "endpoint": "grok",
            "cell_id": f"cell-{number:03d}",
            "payload_sha256": payload,
            "parsed_response_sha256": digest(body),
        },
        "response": body,
    }


def fixture(value, tmp_path: Path, count: int = 40):
    recovery_root, freeze_root = tmp_path / "recovery", tmp_path / "freeze"
    recovery_root.mkdir()
    freeze_root.mkdir()
    cells = [
        {"cell_id": f"cell-{number:03d}", "payload_sha256": digest(f"payload-{number}")}
        for number in range(89, 89 + count)
    ]
    plan = {
        "study_id": value.STUDY_ID,
        "schedule_sha256": "a" * 64,
        "freeze_root": str(freeze_root),
        "origin": {"root": str(tmp_path / "historical"), "ambiguous_terminal_cell": "cell-089", "ambiguous_claim_sha256": "b" * 64},
        "legacy_executor": {"path": "legacy.py", "sha256": "c" * 64},
        "cells": cells,
    }
    plan_raw = canonical(plan)
    (recovery_root / "recovery-plan.json").write_bytes(plan_raw)
    recovery = SyntheticRecovery(plan, recovery_root)
    value._pinned_core = lambda: SyntheticCore()
    value._pinned_recovery = lambda: recovery
    value._source_bindings = lambda _core, _recovery, root, _plan, raw: {
        "core_study": {"path": str(value.CORE_STUDY.resolve()), "sha256": value.CORE_STUDY_SHA256},
        "core_contract": {"path": str(value.CORE_CONTRACT.resolve()), "sha256": value.CORE_CONTRACT_SHA256},
        "recovery_helper": {"path": str(value.RECOVERY_HELPER.resolve()), "sha256": value.RECOVERY_HELPER_SHA256},
        "recovery_plan": {"path": str((root / "recovery-plan.json").resolve()), "sha256": digest(raw)},
        "freeze_root": str(freeze_root.resolve()),
        "legacy_executor": plan["legacy_executor"],
    }
    return recovery_root, digest(plan_raw)


def test_create_refuses_incomplete_campaign_before_any_fit(tmp_path: Path) -> None:
    value = load()
    recovery_root, plan_hash = fixture(value, tmp_path, count=39)
    with pytest.raises(ValueError, match="exactly 40"):
        value.create_freeze(recovery_root, plan_hash, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_create_exports_immutable_lf_bound_selection_freeze(tmp_path: Path) -> None:
    value = load()
    recovery_root, plan_hash = fixture(value, tmp_path)
    result = value.create_freeze(recovery_root, plan_hash, tmp_path / "output")
    freeze_path = Path(result["freeze_path"])
    assert freeze_path.read_bytes().endswith(b"\n")
    context = value.verify_freeze(freeze_path, result["freeze_sha256"], replay_native=True)
    assert context["native_measurement_count"] == 129
    assert context["selected_profile"] == {"core": 1.0, "craft": 1.0, "form": 1.0}
    with pytest.raises(ValueError, match="already exists"):
        value.create_freeze(recovery_root, plan_hash, tmp_path / "output")


def test_verify_rejects_export_drift_even_in_cheap_mode(tmp_path: Path) -> None:
    value = load()
    recovery_root, plan_hash = fixture(value, tmp_path)
    result = value.create_freeze(recovery_root, plan_hash, tmp_path / "output")
    export = Path(result["freeze_path"]).parent / value.NORMALIZED_NAME
    export.write_bytes(export.read_bytes().replace(b'"grok"', b'"sol"', 1))
    with pytest.raises(ValueError, match="canonical JSON|commitment"):
        value.verify_freeze(result["freeze_path"], result["freeze_sha256"], replay_native=False)


def test_measurement_gate_rejects_non_grok_endpoint(tmp_path: Path) -> None:
    value = load()
    core = SyntheticCore()
    rows = {f"cell-{number:03d}": {"payload_sha256": digest(f"payload-{number}")} for number in range(129)}
    measurements = [measurement(number) for number in range(129)]
    measurements[0]["endpoint"] = "sol"
    measurements[0]["measurement_provenance"]["endpoint"] = "sol"
    with pytest.raises(ValueError, match="Grok"):
        value._validate_measurements(core, tmp_path, "a" * 64, rows, measurements)


def test_fit_receipt_is_synthetic_and_explicitly_development_only(tmp_path: Path) -> None:
    value = load()
    recovery_root, plan_hash = fixture(value, tmp_path)
    result = value.create_freeze(recovery_root, plan_hash, tmp_path / "output")
    fit = json.loads((Path(result["freeze_path"]).parent / value.FIT_NAME).read_bytes())
    freeze = json.loads(Path(result["freeze_path"]).read_bytes())
    assert fit["optuna"] == {"version": "4.9.0", "seed": 20260904, "trials": 128}
    assert freeze["authority"] == "development_only_no_runtime_or_confirmation_authority"
    assert freeze["mae"] == "not_applicable_pairwise_preference_target"
