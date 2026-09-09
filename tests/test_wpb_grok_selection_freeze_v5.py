from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/grok_selection_freeze_v5.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("wpb_grok_selection_freeze_v5_test", SOURCE)
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
    return {"A": {"score": number}, "B": {"score": -number}}


class Core:
    STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"

    def __init__(self) -> None:
        self.fit_calls = 0

    @staticmethod
    def canonical(value: object) -> bytes:
        return canonical(value)

    @staticmethod
    def sha256(value: object) -> str:
        return digest(value)

    def fit_train_select_dev(self, _root: Path, measurements: list[dict[str, object]], *, trials: int) -> dict[str, object]:
        self.fit_calls += 1
        assert trials == 128 and len(measurements) == 129
        return {
            "study_id": self.STUDY_ID,
            "optuna": {"version": "4.9.0", "seed": 20260904, "trials": 128},
            "selected_profile_name": "all_one",
            "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
        }


class Recovery:
    PLAN_NAME = "recovery-plan.json"

    def __init__(self, plan: dict[str, object], root: Path) -> None:
        self.plan, self.root = plan, root

    def _read_plan(self, root: Path, expected: str) -> dict[str, object]:
        assert root == self.root and expected == digest((root / self.PLAN_NAME).read_bytes())
        return self.plan

    @staticmethod
    def _verify_origin(_plan: dict[str, object]) -> None:
        return None

    def _verify_admission(self, plan: dict[str, object], root: Path, item: dict[str, object]) -> dict[str, object]:
        assert plan is self.plan and root == self.root
        cell_id = str(item["cell_id"])
        number = int(cell_id.rsplit("-", 1)[1])
        return admission(cell_id, str(item["payload_sha256"]), number)


def admission(cell_id: str, payload_sha256: str, number: int) -> dict[str, object]:
    return {
        "cell_id": cell_id, "payload_sha256": payload_sha256, "response": response(number),
        "identity_sha256": digest(f"identity-{cell_id}"), "request_id_sha256": digest(f"request-{cell_id}"),
        "session_id_sha256": digest(f"session-{cell_id}"), "result_sha256": digest(f"result-{cell_id}"),
        "envelope_sha256": digest(f"envelope-{cell_id}"),
    }


class V5:
    FIRST_V5_CELL = "v5-000"

    def __init__(self, plan: dict[str, object], candidate: dict[str, object], review_path: Path, review_hash: str, count: int = 27) -> None:
        self.plan, self.candidate, self.review_path, self.review_hash, self.count = plan, candidate, review_path, review_hash, count

    def verify_authority(self, **kwargs: Any) -> dict[str, object]:
        assert kwargs["candidate"] == self.candidate
        assert Path(kwargs["reviewed_path"]) == self.review_path
        assert kwargs["expected_review_sha256"] == self.review_hash
        return {"cell_ids": [f"v5-{number:03d}" for number in range(self.count)], "candidate": self.candidate,
                "provider_calls_made": 0, "native_admission_permitted": False}

    @staticmethod
    def _json(path: Path, _label: str) -> tuple[dict[str, object], bytes]:
        raw = path.read_bytes()
        return json.loads(raw), raw

    def _verify_admission(self, **kwargs: Any) -> dict[str, object]:
        assert kwargs["candidate"] == self.candidate
        cell_id = kwargs["cell_id"]
        attempt, _raw = self._json(Path(kwargs["suffix_root"]) / "cells" / cell_id / "v5-attempt.json", "v5 attempt")
        number = int(cell_id.rsplit("-", 1)[1])
        row = next(item for item in self.plan["cells"] if item["cell_id"] == cell_id)
        value = admission(cell_id, row["payload_sha256"], number + 100)
        value["review_sha256"] = attempt["review"]["sha256"]
        return value


def fixture(value: Any, tmp_path: Path, *, v5_count: int = 27) -> tuple[Core, dict[str, object]]:
    root, suffix, freeze_root, output = tmp_path / "recovery", tmp_path / "suffix", tmp_path / "freeze-root", tmp_path / "output"
    root.mkdir(); suffix.mkdir(); freeze_root.mkdir()
    candidate = {"isolated_queue_root": str((tmp_path / "isolated-queue").resolve())}
    Path(candidate["isolated_queue_root"]).mkdir()
    review_path = tmp_path / "review.json"; review_path.write_bytes(canonical({"review": "current"}))
    review_hash = digest(review_path.read_bytes())
    early_review_path = tmp_path / "early-review.json"; early_review_path.write_bytes(canonical({"review": "early"}))
    early_review_hash = digest(early_review_path.read_bytes())
    v4 = [{"cell_id": f"v4-{number:03d}", "payload_sha256": digest(f"v4-{number}")} for number in range(12)]
    schema = {"cell_id": "wpb-pair-wpb-en-0843", "payload_sha256": digest("schema")}
    v5_cells = [{"cell_id": f"v5-{number:03d}", "payload_sha256": digest(f"v5-{number}")} for number in range(27)]
    plan = {
        "study_id": Core.STUDY_ID, "schedule_sha256": "a" * 64, "freeze_root": str(freeze_root),
        "origin": {"root": str(tmp_path / "origin"), "ambiguous_terminal_cell": "old", "ambiguous_claim_sha256": "b" * 64},
        "legacy_executor": {"path": "legacy", "sha256": "c" * 64}, "cells": [v4[0], schema, *v4[1:], *v5_cells],
    }
    plan_raw = canonical(plan); (root / "recovery-plan.json").write_bytes(plan_raw)
    for number, item in enumerate(v5_cells):
        review_binding = ({"path": str(early_review_path), "sha256": early_review_hash} if number == 0
                          else {"path": str(review_path), "sha256": review_hash})
        attempt_path = suffix / "cells" / item["cell_id"] / "v5-attempt.json"
        attempt_path.parent.mkdir(parents=True)
        attempt_path.write_bytes(canonical({"cell_id": item["cell_id"], "review": review_binding}))
    core, recovery = Core(), Recovery(plan, root)
    row_ids = [f"legacy-{number:03d}" for number in range(89)] + [item["cell_id"] for item in v4] + [schema["cell_id"]] + [item["cell_id"] for item in v5_cells]
    rows = {cell_id: {"cell_id": cell_id, "payload_sha256": digest(f"row-{cell_id}")} for cell_id in row_ids}
    for item in [*v4, schema, *v5_cells]:
        rows[item["cell_id"]]["payload_sha256"] = item["payload_sha256"]

    def legacy(_core: Any, _recovery: Any, _plan: Any) -> tuple[list[dict[str, object]], set[str]]:
        values = []
        for number in range(89):
            cell_id, payload = f"legacy-{number:03d}", rows[f"legacy-{number:03d}"]["payload_sha256"]
            body = response(number)
            values.append({"endpoint": "grok", "cell_id": cell_id, "payload_sha256": payload,
                           "measurement_provenance": {"endpoint": "grok", "cell_id": cell_id, "payload_sha256": payload,
                                                      "parsed_response_sha256": digest(body)}, "response": body})
        return values, {item["cell_id"] for item in values}

    recovered_body = response(843)
    recovered = {"endpoint": "grok", "cell_id": schema["cell_id"], "payload_sha256": schema["payload_sha256"],
                 "measurement_provenance": {"endpoint": "grok", "cell_id": schema["cell_id"], "payload_sha256": schema["payload_sha256"],
                                            "parsed_response_sha256": digest(recovered_body)}, "response": recovered_body}
    schema_context = {"measurement": recovered, "helper": {"path": "schema", "sha256": "d" * 64},
                      "adoption": {"path": "adoption", "sha256": "e" * 64}, "proposal_root": "proposal",
                      "source_cell_root": "source", "provenance": {"classification": "local_session_schema_recovered"}}
    options = {"synthetic": True}

    def source_bindings(_core: Any, _recovery: Any, bound_root: Path, _plan: Any, raw: bytes, schema_value: Any) -> dict[str, object]:
        return {"core_study": {}, "core_contract": {}, "recovery_helper": {},
                "recovery_plan": {"path": str((bound_root / "recovery-plan.json").resolve()), "sha256": digest(raw)},
                "freeze_root": str(freeze_root.resolve()), "legacy_executor": plan["legacy_executor"],
                "schema_recovery": {key: schema_value[key] for key in ("helper", "adoption", "proposal_root", "source_cell_root", "provenance")}}

    def validate(_core: Any, _freeze_root: Path, _schedule: str, passed_rows: Any, measurements: Any) -> list[dict[str, object]]:
        assert len(measurements) == 129 and len({item["cell_id"] for item in measurements}) == 129
        assert set(passed_rows) == {item["cell_id"] for item in measurements}
        return sorted((dict(item) for item in measurements), key=lambda item: item["cell_id"])

    def normalized(bindings: Any, schedule: str, measurements: Any, admissions: Any) -> dict[str, object]:
        return {"kind": "normalized", "source_bindings": dict(bindings), "schedule_sha256": schedule, "endpoint": "grok",
                "measurements": [dict(item) for item in measurements], "recovery_admission_commitments": [dict(item) for item in admissions]}

    def freeze_document(**kwargs: Any) -> dict[str, object]:
        return {"kind": "wpb_grok_train_dev_selection_freeze", "schedule_sha256": kwargs["schedule_sha256"],
                "source_bindings": dict(kwargs["source_bindings"]), "selected_profile": dict(kwargs["fit_result"]["selected_profile"]),
                "selected_profile_name": kwargs["fit_result"]["selected_profile_name"], "selection_frozen_at": kwargs["selection_frozen_at"],
                "evidence_files": {}, "inner_core_native_admission": "not_claimed"}

    def verify_static(_core: Any, _recovery: Any, path: Path, expected: str) -> Any:
        freeze, freeze_raw = json.loads(path.read_bytes()), path.read_bytes()
        assert digest(freeze_raw) == expected
        normalized_path, fit_path = path.parent / "grok-normalized-measurements.json", path.parent / "grok-core-fit-result.json"
        normalized, normalized_raw = json.loads(normalized_path.read_bytes()), normalized_path.read_bytes()
        fit, fit_raw = json.loads(fit_path.read_bytes()), fit_path.read_bytes()
        return freeze, normalized, fit, dict(freeze["source_bindings"]), normalized_raw, fit_raw

    selection = SimpleNamespace(
        STUDY_ID=Core.STUDY_ID, SCHEMA_RECOVERY_CELL=schema["cell_id"], NORMALIZED_NAME="grok-normalized-measurements.json",
        FIT_NAME="grok-core-fit-result.json", FREEZE_NAME="grok-selection-freeze.json", _pinned_core=lambda: core,
        _pinned_recovery=lambda: recovery, _hex=lambda value, _label: value, _sha256=digest,
        _json=lambda path, _label: (json.loads(path.read_bytes()), path.read_bytes()), _schema_options=lambda **kwargs: options,
        _schema_context=lambda _options, _plan: schema_context,
        _schedule=lambda _core, _recovery, _plan: ({}, rows, []), _legacy_measurements=legacy,
        _validate_measurements=validate, _source_bindings=source_bindings, _normalized_document=normalized,
        _freeze_document=freeze_document, _canonical=lambda _core, item: canonical(item), _verify_static=verify_static,
        _verify_bindings=lambda _core, _recovery, bindings, _schedule: (plan, plan_raw),
        _schema_options_from_binding=lambda _bindings: options,
    )
    value._pinned_selection = lambda: selection
    value._pinned_v5 = lambda: V5(plan, candidate, review_path, review_hash, v5_count)
    return core, {"recovery_root": root, "expected_plan_sha256": digest(plan_raw), "suffix_root": suffix,
                  "reviewed_path": review_path, "expected_review_sha256": review_hash, "candidate": candidate,
                  "output_root": output, "schema_adoption_path": tmp_path / "adoption", "expected_schema_adoption_sha256": "f" * 64,
                  "schema_proposal_root": tmp_path / "proposal", "schema_source_cell_root": tmp_path / "source",
                  "expected_schema_recovery_sha256": "a" * 64}


def test_create_replays_mixed_89_12_27_1_context_and_core_fit(tmp_path: Path) -> None:
    value = load()
    core, arguments = fixture(value, tmp_path)
    result = value.create_freeze(**arguments)
    freeze = json.loads(Path(result["freeze_path"]).read_bytes())
    normalized = json.loads((Path(result["freeze_path"]).parent / "grok-normalized-measurements.json").read_bytes())
    reviews = freeze["source_bindings"]["v5_recorded_reviews"]
    assert reviews[0] == {"cell_id": "v5-000", "path": str((tmp_path / "early-review.json").resolve()),
                          "sha256": digest((tmp_path / "early-review.json").read_bytes())}
    assert {item["path"] for item in reviews} == {str((tmp_path / "review.json").resolve()), str((tmp_path / "early-review.json").resolve())}
    assert normalized["source_bindings"]["v5_recorded_reviews"] == reviews
    assert core.fit_calls == 1
    context = value.verify_freeze_context(result["freeze_path"], result["freeze_sha256"])
    mixed = context[value.MIXED_CONTEXT_KEY]
    assert mixed["legacy_measurement_count"] == 89
    assert mixed["v4_native_measurement_count"] == 12
    assert mixed["v5_native_measurement_count"] == 27
    assert mixed["local_session_schema_recovered_measurement_count"] == 1
    assert mixed["native_measurement_count"] == 128
    assert mixed["measurement_count"] == 129
    assert core.fit_calls == 2


def test_partial_102_rejects_before_fit(tmp_path: Path) -> None:
    value = load()
    core, arguments = fixture(value, tmp_path, v5_count=0)
    with pytest.raises(ValueError, match="exactly 27"):
        value.create_freeze(**arguments)
    assert core.fit_calls == 0
    assert not Path(arguments["output_root"]).exists()


def test_v5_candidate_drift_rejects_before_fit(tmp_path: Path) -> None:
    value = load()
    core, arguments = fixture(value, tmp_path)
    candidate = dict(arguments["candidate"])
    candidate["isolated_queue_root"] = str((tmp_path / "wrong-queue").resolve())
    arguments["candidate"] = candidate
    with pytest.raises(AssertionError):
        value.create_freeze(**arguments)
    assert core.fit_calls == 0


def test_v5_review_drift_rejects_before_fit(tmp_path: Path) -> None:
    value = load()
    core, arguments = fixture(value, tmp_path)
    Path(arguments["reviewed_path"]).write_bytes(canonical({"review": "changed"}))
    with pytest.raises(ValueError, match="reviewed authority source drifted"):
        value.create_freeze(**arguments)
    assert core.fit_calls == 0


def test_early_recorded_review_byte_drift_rejects_replay(tmp_path: Path) -> None:
    value = load()
    _core, arguments = fixture(value, tmp_path)
    result = value.create_freeze(**arguments)
    (tmp_path / "early-review.json").write_bytes(canonical({"review": "changed"}))
    with pytest.raises(ValueError, match="v5 v5-000 recorded review source drifted"):
        value.verify_freeze_context(result["freeze_path"], result["freeze_sha256"])


def test_early_recorded_review_path_drift_rejects_replay(tmp_path: Path) -> None:
    value = load()
    _core, arguments = fixture(value, tmp_path)
    result = value.create_freeze(**arguments)
    attempt_path = tmp_path / "suffix" / "cells" / "v5-000" / "v5-attempt.json"
    attempt_path.write_bytes(canonical({"cell_id": "v5-000", "review": {
        "path": str((tmp_path / "review.json").resolve()), "sha256": digest((tmp_path / "review.json").read_bytes()),
    }}))
    with pytest.raises(ValueError, match="recorded review binding drifted"):
        value.verify_freeze_context(result["freeze_path"], result["freeze_sha256"])


def test_pinned_v5_helper_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    replacement = tmp_path / "recovery_v5_suffix.py"; replacement.write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(value, "V5_SUFFIX", replacement)
    monkeypatch.setattr(value, "V5_SUFFIX_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="v5 suffix helper source drifted"):
        value._pinned_v5()
