"""Immutable mixed WPB selection freezes that replay the v4 and v5 recovery evidence."""
from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
FROZEN_SELECTION = HERE / "grok_selection_freeze.py"
FROZEN_SELECTION_SHA256 = "b393c057506d2b0dd4a35cb61e11c35517650d24f4f0add22c0579a9924e2c1e"
V5_SUFFIX = HERE / "recovery_v5_suffix.py"
V5_SUFFIX_SHA256 = "2d1b1a5a3a9191a8580325da3d303d158ab4a736052c38a1fc01e8bcd41ab504"
LEGACY_COUNT = 89
V4_NATIVE_COUNT = 12
V5_TOTAL_COUNT = 27
V5_NATIVE_COUNT = 26
RECOVERED_COUNT = 2
NATIVE_COUNT = 127
MEASUREMENT_COUNT = 129
MIXED_CONTEXT_KEY = "mixed_v5_selection_context"
V5_RECOVERY_CELL = "wpb-pair-wpb-en-1088"
RECOVERED_CELL_IDS = ("wpb-pair-wpb-en-0843", V5_RECOVERY_CELL)
PRE_V5_PREFIX_COUNT = V4_NATIVE_COUNT + 1
_HEX = set("0123456789abcdef")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"cannot load pinned {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pinned_selection() -> ModuleType:
    raw = FROZEN_SELECTION.read_bytes()
    _require(_sha256(raw) == FROZEN_SELECTION_SHA256, "frozen Grok selection helper source drifted")
    module = _module(FROZEN_SELECTION, "wpb_grok_selection_freeze_v5_base")
    _require(FROZEN_SELECTION.read_bytes() == raw, "frozen Grok selection helper changed during load")
    return module


def _pinned_v5() -> ModuleType:
    raw = V5_SUFFIX.read_bytes()
    _require(_sha256(raw) == V5_SUFFIX_SHA256, "frozen WPB v5 suffix helper source drifted")
    module = _module(V5_SUFFIX, "wpb_grok_selection_freeze_v5_suffix")
    _require(V5_SUFFIX.read_bytes() == raw, "frozen WPB v5 suffix helper changed during load")
    return module


def _continuation(path: Path | str, expected_sha256: str) -> tuple[ModuleType, dict[str, str]]:
    descriptor = _descriptor(path, expected_sha256, "v5 continuation helper")
    source = Path(descriptor["path"])
    raw = source.read_bytes()
    module = _module(source, "wpb_grok_selection_freeze_v5_continuation")
    _require(source.read_bytes() == raw, "v5 continuation helper changed during load")
    _require(callable(getattr(module, "verify_projection", None)), "v5 continuation projection verifier is unavailable")
    return module, descriptor


def _descriptor(path: Path | str, expected_sha256: str, label: str) -> dict[str, str]:
    resolved = Path(path).resolve()
    _require(resolved.is_file() and _sha256(resolved.read_bytes()) == _hex(expected_sha256, label), f"{label} source drifted")
    return {"path": str(resolved), "sha256": expected_sha256}


def _write_new(path: Path, raw: bytes) -> str:
    with path.open("xb") as handle:
        handle.write(raw)
    return _sha256(raw)


def _measurement(selection: ModuleType, core: ModuleType, admission: Mapping[str, Any]) -> dict[str, Any]:
    cell_id, payload_sha, response = admission.get("cell_id"), admission.get("payload_sha256"), admission.get("response")
    _require(isinstance(cell_id, str) and isinstance(payload_sha, str) and isinstance(response, Mapping), "native admission lacks a normalized response")
    return {
        "endpoint": "grok",
        "cell_id": cell_id,
        "payload_sha256": payload_sha,
        "measurement_provenance": {
            "endpoint": "grok",
            "cell_id": cell_id,
            "payload_sha256": payload_sha,
            "parsed_response_sha256": core.sha256(selection._canonical(core, response)),
        },
        "response": dict(response),
    }


def _v4_cells(selection: ModuleType, plan: Mapping[str, Any], v5: ModuleType) -> list[dict[str, Any]]:
    cells = plan.get("cells")
    _require(isinstance(cells, list) and len(cells) == 40, "recovery plan must contain exactly 40 cells")
    values = [dict(item) for item in cells if isinstance(item, Mapping)]
    _require(len(values) == 40 and len({item.get("cell_id") for item in values}) == 40, "recovery plan cells are malformed")
    start = next((index for index, item in enumerate(values) if item.get("cell_id") == v5.FIRST_V5_CELL), None)
    _require(start == PRE_V5_PREFIX_COUNT, "v4/v5 recovery boundary drifted")
    _require(values[1].get("cell_id") == selection.SCHEMA_RECOVERY_CELL, "0843 schema-recovered cell moved")
    prefix = values[:start]
    result = [item for item in prefix if item.get("cell_id") != selection.SCHEMA_RECOVERY_CELL]
    _require(len(result) == V4_NATIVE_COUNT, "v4 native predecessor count drifted")
    return result


def _identity_sets(admissions: Sequence[Mapping[str, Any]]) -> tuple[set[str], set[str], set[str]]:
    values: list[set[str]] = []
    for key in ("identity_sha256", "request_id_sha256", "session_id_sha256"):
        current = {item.get(key) for item in admissions}
        _require(all(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX for value in current)
                 and len(current) == len(admissions), f"native {key} inventory drifted")
        values.append(set(current))
    return values[0], values[1], values[2]


def _projection_binding(value: Mapping[str, Any] | None) -> dict[str, str]:
    _require(isinstance(value, Mapping) and set(value) == {
        "proposal_root", "expected_proposal_sha256", "adoption_path", "expected_adoption_sha256",
    }, "1088 projection binding is malformed")
    proposal_root, adoption_path = value.get("proposal_root"), value.get("adoption_path")
    _require(isinstance(proposal_root, (str, Path)) and isinstance(adoption_path, (str, Path)),
             "1088 projection paths are malformed")
    return {
        "proposal_root": str(Path(proposal_root).resolve()),
        "expected_proposal_sha256": _hex(value.get("expected_proposal_sha256"), "1088 proposal hash"),
        "adoption_path": str(Path(adoption_path).resolve()),
        "expected_adoption_sha256": _hex(value.get("expected_adoption_sha256"), "1088 adoption hash"),
    }


def _projection(continuation: ModuleType, binding: Mapping[str, str], plan: Mapping[str, Any]) -> dict[str, Any]:
    value = continuation.verify_projection(**dict(binding))
    _require(isinstance(value, Mapping) and set(value) == {"measurement", "provenance", "bindings", "local_identity"},
             "1088 projection result is malformed")
    measurement, provenance, bindings, identity = (value.get(key) for key in ("measurement", "provenance", "bindings", "local_identity"))
    _require(isinstance(measurement, Mapping) and isinstance(provenance, Mapping)
             and set(provenance) == {"classification", "native_admission_permitted", "proposal_kind", "schema_sha256", "frozen_core", "full_field_diff"}
             and bindings == binding
             and isinstance(identity, Mapping) and set(identity) == {"request_id_sha256", "session_id_sha256"},
             "1088 projection bindings differ")
    row = next((item for item in plan.get("cells", []) if isinstance(item, Mapping) and item.get("cell_id") == V5_RECOVERY_CELL), None)
    _require(isinstance(row, Mapping) and measurement.get("endpoint") == "grok" and measurement.get("cell_id") == V5_RECOVERY_CELL
             and measurement.get("payload_sha256") == row.get("payload_sha256") and isinstance(measurement.get("response"), Mapping)
             and provenance.get("classification") == "local_session_schema_recovered"
             and provenance.get("native_admission_permitted") is False
             and all(_hex(identity.get(key), f"1088 {key}") for key in identity), "1088 projection provenance differs")
    return {"measurement": dict(measurement), "provenance": dict(provenance), "bindings": dict(bindings),
            "local_identity": dict(identity)}


def _schema_recovery_binding(schema: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "classification": str(schema["provenance"]["classification"]),
        "source_binding": {
            "helper": dict(schema["helper"]), "adoption": dict(schema["adoption"]),
            "proposal_root": schema["proposal_root"], "source_cell_root": schema["source_cell_root"],
            "provenance": dict(schema["provenance"]),
        },
    }


def _mixed_context(*, v4_cells: Sequence[Mapping[str, Any]], v5_cells: Sequence[str],
                   schema: Mapping[str, Any], continuation_descriptor: Mapping[str, str], projection: Mapping[str, Any]) -> dict[str, Any]:
    recovery_bindings = {
        RECOVERED_CELL_IDS[0]: _schema_recovery_binding(schema),
        V5_RECOVERY_CELL: {"classification": str(projection["provenance"]["classification"]),
                           "continuation_helper": dict(continuation_descriptor), "projection": dict(projection)},
    }
    return {
        "legacy_measurement_count": LEGACY_COUNT,
        "v4_native_measurement_count": V4_NATIVE_COUNT,
        "v5_native_measurement_count": V5_NATIVE_COUNT,
        "local_session_schema_recovered_measurement_count": RECOVERED_COUNT,
        "native_measurement_count": NATIVE_COUNT,
        "measurement_count": MEASUREMENT_COUNT,
        "v4_cell_ids": [str(item["cell_id"]) for item in v4_cells],
        "v5_native_cell_ids": list(v5_cells),
        "recovered_cell_ids": list(RECOVERED_CELL_IDS),
        "recovery_bindings": recovery_bindings,
        "authority": "development_only_no_runtime_or_confirmation_authority",
        "release_or_promotion_authority": "none",
    }


def _v5_authority(v5: ModuleType, *, recovery_root: Path, suffix_root: Path, expected_plan_sha256: str,
                  reviewed_path: Path, expected_review_sha256: str, candidate: Mapping[str, Any]) -> tuple[list[str], dict[str, Any], dict[str, str]]:
    review = _descriptor(reviewed_path, expected_review_sha256, "v5 reviewed authority")
    verified = v5.verify_authority(
        recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
        reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256, candidate=candidate,
    )
    cells, bound_candidate = verified.get("cell_ids"), verified.get("candidate")
    _require(isinstance(cells, list) and len(cells) == V5_TOTAL_COUNT and len(set(cells)) == V5_TOTAL_COUNT
             and all(isinstance(cell_id, str) for cell_id in cells) and cells.count(V5_RECOVERY_CELL) == 1,
             "v5 suffix has not supplied exactly 27 cells")
    _require(isinstance(bound_candidate, Mapping) and verified.get("provider_calls_made") == 0
             and verified.get("native_admission_permitted") is False, "v5 authority exceeds provider-free replay scope")
    return list(cells), dict(bound_candidate), review


def _recorded_reviews(v5: ModuleType, suffix_root: Path, cell_ids: Sequence[str], *, expected_count: int) -> list[dict[str, str]]:
    reviews: list[dict[str, str]] = []
    for cell_id in cell_ids:
        attempt, _raw = v5._json(suffix_root / "cells" / cell_id / "v5-attempt.json", "v5 attempt")
        review = attempt.get("review")
        _require(attempt.get("cell_id") == cell_id and isinstance(review, Mapping), "v5 attempt review binding is malformed")
        descriptor = _descriptor(str(review.get("path", "")), str(review.get("sha256", "")), f"v5 {cell_id} recorded review")
        reviews.append({"cell_id": cell_id, **descriptor})
    _require(len(reviews) == expected_count and len({item["cell_id"] for item in reviews}) == expected_count,
             "v5 recorded review inventory drifted")
    return reviews


def _continuation_targets(continuation: ModuleType, v5_native_ids: Sequence[str]) -> tuple[str, ...]:
    value = getattr(continuation, "REMAINING_CELL_IDS", None)
    _require(isinstance(value, tuple) and len(value) == 11 and all(isinstance(cell_id, str) for cell_id in value)
             and len(set(value)) == len(value) and set(value) <= set(v5_native_ids),
             "v5 continuation target inventory drifted")
    return value


def _continuation_reviews(selection: ModuleType, value: Mapping[str, Any] | None,
                          cell_ids: Sequence[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    _require(isinstance(value, Mapping) and set(value) == set(cell_ids), "v5 continuation review bindings are malformed")
    parsed: dict[str, dict[str, Any]] = {}
    descriptors: dict[str, dict[str, str]] = {}
    for cell_id in cell_ids:
        descriptor = value.get(cell_id)
        _require(isinstance(descriptor, Mapping) and set(descriptor) == {"path", "sha256"},
                 "v5 continuation review descriptor is malformed")
        bound = _descriptor(str(descriptor["path"]), str(descriptor["sha256"]), f"v5 continuation {cell_id} review")
        review, raw = selection._json(Path(bound["path"]), f"v5 continuation {cell_id} review")
        _require(_sha256(raw) == bound["sha256"] and isinstance(review, Mapping), "v5 continuation review bytes drifted")
        parsed[cell_id], descriptors[cell_id] = dict(review), bound
    return parsed, descriptors


def _continuation_old_review(selection: ModuleType, cell_id: str, review: Mapping[str, Any]) -> tuple[Path, str]:
    descriptor = review.get("old_review")
    _require(isinstance(descriptor, Mapping) and set(descriptor) == {"path", "sha256"},
             "v5 continuation old review descriptor is malformed")
    bound = _descriptor(str(descriptor["path"]), str(descriptor["sha256"]), f"v5 continuation {cell_id} old review")
    parsed, raw = selection._json(Path(bound["path"]), f"v5 continuation {cell_id} old review")
    _require(_sha256(raw) == bound["sha256"] and isinstance(parsed, Mapping), "v5 continuation old review bytes drifted")
    return Path(bound["path"]), bound["sha256"]


def _continuation_admission(selection: ModuleType, continuation: ModuleType, *, recovery_root: Path, suffix_root: Path,
                            expected_plan_sha256: str, cell_id: str, candidate: Mapping[str, Any],
                            projection_binding: Mapping[str, str], review: Mapping[str, Any]) -> dict[str, Any]:
    reviewed_path, expected_review_sha256 = _continuation_old_review(selection, cell_id, review)
    value = continuation.verify_native(
        recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
        cell_id=cell_id, reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
        candidate=candidate, projection_binding=projection_binding, independent_continuation_review=review,
    )
    _require(isinstance(value, Mapping) and value.get("cell_id") == cell_id,
             "v5 continuation native admission differs")
    return dict(value)


def _mixed_inputs(selection: ModuleType, v5: ModuleType, *, recovery_root: Path, expected_plan_sha256: str,
                  suffix_root: Path, reviewed_path: Path, expected_review_sha256: str, candidate: Mapping[str, Any],
                  schema_options: Mapping[str, Any] | None, continuation: ModuleType,
                  continuation_descriptor: Mapping[str, str], recovery_projection_binding: Mapping[str, str],
                  continuation_reviews: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    _require(schema_options is not None, "0843 owner-adopted schema projection arguments are required for the mixed freeze")
    core, recovery = selection._pinned_core(), selection._pinned_recovery()
    plan = recovery._read_plan(recovery_root, selection._hex(expected_plan_sha256, "expected recovery plan hash"))
    plan_value, plan_raw = selection._json(recovery_root / recovery.PLAN_NAME, "recovery plan")
    _require(plan == plan_value and selection._sha256(plan_raw) == expected_plan_sha256, "recovery plan reader and immutable bytes disagree")
    recovery._verify_origin(plan)
    schema = selection._schema_context(schema_options, plan)
    _require(schema is not None, "0843 owner-adopted schema projection is unavailable")
    _resolution, rows, _tasks = selection._schedule(core, recovery, plan)
    legacy, legacy_ids = selection._legacy_measurements(core, recovery, plan)
    _require(len(legacy) == LEGACY_COUNT and len(legacy_ids) == LEGACY_COUNT, "legacy Grok prefix count drifted")
    v4_cells = _v4_cells(selection, plan, v5)
    v4_admissions = [recovery._verify_admission(plan, recovery_root, item) for item in v4_cells]
    _require(len(v4_admissions) == V4_NATIVE_COUNT, "v4 native predecessor admissions are incomplete")
    v5_ids, bound_candidate, review = _v5_authority(
        v5, recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
        reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256, candidate=candidate,
    )
    _require(v5_ids == [str(item["cell_id"]) for item in plan["cells"][PRE_V5_PREFIX_COUNT:]], "v5 suffix cell sequence drifted")
    v5_native_ids = [cell_id for cell_id in v5_ids if cell_id != V5_RECOVERY_CELL]
    _require(len(v5_native_ids) == V5_NATIVE_COUNT, "v5 native admission inventory drifted")
    continuation_ids = _continuation_targets(continuation, v5_native_ids)
    original_v5_ids = [cell_id for cell_id in v5_native_ids if cell_id not in continuation_ids]
    _require(len(original_v5_ids) == 15 and v5_native_ids[:15] == original_v5_ids
             and tuple(v5_native_ids[15:]) == continuation_ids, "v5 continuation boundary drifted")
    recorded_reviews = _recorded_reviews(v5, suffix_root, original_v5_ids, expected_count=15)
    continuation_review_values, continuation_review_descriptors = _continuation_reviews(
        selection, continuation_reviews, continuation_ids,
    )
    v5_admissions = []
    for cell_id, recorded_review in zip(original_v5_ids, recorded_reviews, strict=True):
        admission = v5._verify_admission(
            recovery_root=recovery_root, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
            cell_id=cell_id, reviewed_path=reviewed_path, expected_review_sha256=expected_review_sha256,
            candidate=bound_candidate,
        )
        _require(admission.get("cell_id") == cell_id and admission.get("review_sha256") == recorded_review["sha256"],
                 "v5 admission recorded review differs")
        v5_admissions.append(admission)
    for cell_id in continuation_ids:
        v5_admissions.append(_continuation_admission(
            selection, continuation, recovery_root=recovery_root, suffix_root=suffix_root,
            expected_plan_sha256=expected_plan_sha256, cell_id=cell_id, candidate=bound_candidate,
            projection_binding=recovery_projection_binding, review=continuation_review_values[cell_id],
        ))
    _require(len(v5_admissions) == V5_NATIVE_COUNT, "v5 suffix native admissions are incomplete")
    admissions = [dict(item) for item in v4_admissions + v5_admissions]
    _require(len(admissions) == V4_NATIVE_COUNT + V5_NATIVE_COUNT, "mixed native admission count drifted")
    _identity_sets(admissions)
    v4_ids = {str(item["cell_id"]) for item in v4_admissions}
    v5_id_set = {str(item["cell_id"]) for item in v5_admissions}
    schema_measurement = dict(schema["measurement"])
    projected = _projection(continuation, recovery_projection_binding, plan)
    recovered = [schema_measurement, dict(projected["measurement"])]
    all_measurements = [dict(item) for item in legacy] + [_measurement(selection, core, item) for item in admissions] + recovered
    native_ids = set(legacy_ids) | v4_ids | v5_id_set
    _require(len(native_ids) == NATIVE_COUNT and not (set(legacy_ids) & v4_ids) and not (set(legacy_ids) & v5_id_set)
             and not (v4_ids & v5_id_set) and not (set(RECOVERED_CELL_IDS) & native_ids)
             and {item["cell_id"] for item in recovered} == set(RECOVERED_CELL_IDS), "127 native measurement identities overlap")
    _require(len(all_measurements) == MEASUREMENT_COUNT, "mixed recovery must supply exactly 129 measurements before fit")
    measurements = selection._validate_measurements(core, Path(str(plan["freeze_root"])), str(plan["schedule_sha256"]), rows, all_measurements)
    bindings = selection._source_bindings(core, recovery, recovery_root, plan, plan_raw, schema)
    bindings.update({
        "selection_freeze_helper": _descriptor(FROZEN_SELECTION, FROZEN_SELECTION_SHA256, "frozen selection helper"),
        "v5_suffix_helper": _descriptor(V5_SUFFIX, V5_SUFFIX_SHA256, "v5 suffix helper"),
        "v5_review": review,
        "v5_recorded_reviews": recorded_reviews,
        "v5_candidate": bound_candidate,
        "v5_isolated_queue_root": bound_candidate["isolated_queue_root"],
        "v5_suffix_root": str(suffix_root.resolve()),
        "recovery_v5_continuation_helper": dict(continuation_descriptor),
        "recovery_v5_projection_binding": dict(recovery_projection_binding),
        "v5_continuation_reviews": continuation_review_descriptors,
    })
    context = _mixed_context(v4_cells=v4_cells, v5_cells=v5_native_ids, schema=schema,
                             continuation_descriptor=continuation_descriptor, projection=projected)
    return plan, bindings, measurements, admissions, context


def _normalized_document(selection: ModuleType, *, bindings: Mapping[str, Any], plan: Mapping[str, Any],
                          measurements: Sequence[Mapping[str, Any]], admissions: Sequence[Mapping[str, Any]],
                          context: Mapping[str, Any]) -> dict[str, Any]:
    document = selection._normalized_document(bindings, str(plan["schedule_sha256"]), measurements, admissions)
    return _rewrite_mixed_document(document, context)


def _freeze_document(selection: ModuleType, *, bindings: Mapping[str, Any], plan: Mapping[str, Any], normalized: Path,
                     normalized_raw: bytes, fit: Path, fit_raw: bytes, fit_result: Mapping[str, Any],
                     selection_frozen_at: str, context: Mapping[str, Any]) -> dict[str, Any]:
    document = selection._freeze_document(
        source_bindings=bindings, schedule_sha256=str(plan["schedule_sha256"]), normalized=normalized,
        normalized_raw=normalized_raw, fit=fit, fit_raw=fit_raw, fit_result=fit_result,
        selection_frozen_at=selection_frozen_at, plan=plan,
    )
    return _rewrite_mixed_document(document, context)


def _rewrite_mixed_document(document: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(document)
    for key in ("native_measurement_count", "native_measurement_classification",
                "local_session_schema_recovered_measurement_count", "measurement_evidence_classification",
                "schema_recovery", "recovered_cell_ids", "recovery_bindings", MIXED_CONTEXT_KEY):
        result.pop(key, None)
    result.update({
        "measurement_count": MEASUREMENT_COUNT,
        "native_measurement_count": NATIVE_COUNT,
        "local_session_schema_recovered_measurement_count": RECOVERED_COUNT,
        "measurement_evidence_classification": {
            "ordinary_measurements": NATIVE_COUNT,
            "local_session_schema_recovered_measurements": RECOVERED_COUNT,
            "recovered_cell_ids": list(RECOVERED_CELL_IDS),
        },
        "recovered_cell_ids": list(RECOVERED_CELL_IDS),
        "recovery_bindings": dict(context["recovery_bindings"]),
        MIXED_CONTEXT_KEY: dict(context),
    })
    return result


def _schema_options(selection: ModuleType, *, schema_adoption_path: Path | str | None,
                    expected_schema_adoption_sha256: str | None, schema_proposal_root: Path | str | None,
                    schema_source_cell_root: Path | str | None, expected_schema_recovery_sha256: str | None) -> dict[str, Any] | None:
    return selection._schema_options(
        schema_adoption_path=schema_adoption_path, expected_schema_adoption_sha256=expected_schema_adoption_sha256,
        schema_proposal_root=schema_proposal_root, schema_source_cell_root=schema_source_cell_root,
        expected_schema_recovery_sha256=expected_schema_recovery_sha256,
    )


def create_freeze(recovery_root: Path | str, expected_plan_sha256: str, suffix_root: Path | str,
                  reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any], output_root: Path | str, *,
                  schema_adoption_path: Path | str | None = None,
                  expected_schema_adoption_sha256: str | None = None,
                  schema_proposal_root: Path | str | None = None,
                  schema_source_cell_root: Path | str | None = None,
                  expected_schema_recovery_sha256: str | None = None,
                  recovery_v5_continuation_path: Path | str | None = None,
                  expected_recovery_v5_continuation_sha256: str | None = None,
                  recovery_projection_binding: Mapping[str, Any] | None = None,
                  continuation_reviews: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Create an immutable mixed freeze only after every retained input replays."""
    _require(isinstance(candidate, Mapping), "v5 candidate must be a mapping")
    selection, v5 = _pinned_selection(), _pinned_v5()
    options = _schema_options(
        selection, schema_adoption_path=schema_adoption_path,
        expected_schema_adoption_sha256=expected_schema_adoption_sha256,
        schema_proposal_root=schema_proposal_root, schema_source_cell_root=schema_source_cell_root,
        expected_schema_recovery_sha256=expected_schema_recovery_sha256,
    )
    _require(recovery_v5_continuation_path is not None and expected_recovery_v5_continuation_sha256 is not None,
             "1088 continuation helper arguments are required for the mixed freeze")
    continuation, continuation_descriptor = _continuation(
        recovery_v5_continuation_path, expected_recovery_v5_continuation_sha256,
    )
    projection_binding = _projection_binding(recovery_projection_binding)
    output = Path(output_root).resolve()
    _require(not output.exists(), "selection freeze output root already exists")
    root, suffix, review = Path(recovery_root).resolve(), Path(suffix_root).resolve(), Path(reviewed_path).resolve()
    plan, bindings, measurements, admissions, context = _mixed_inputs(
        selection, v5, recovery_root=root, expected_plan_sha256=expected_plan_sha256, suffix_root=suffix,
        reviewed_path=review, expected_review_sha256=expected_review_sha256, candidate=candidate, schema_options=options,
        continuation=continuation, continuation_descriptor=continuation_descriptor,
        recovery_projection_binding=projection_binding, continuation_reviews=continuation_reviews,
    )
    core = selection._pinned_core()
    normalized_value = _normalized_document(selection, bindings=bindings, plan=plan, measurements=measurements,
                                            admissions=admissions, context=context)
    normalized_raw = selection._canonical(core, normalized_value)
    fit_result = core.fit_train_select_dev(Path(str(plan["freeze_root"])), measurements, trials=128)
    _require(isinstance(fit_result, Mapping) and fit_result.get("study_id") == selection.STUDY_ID
             and fit_result.get("optuna") == {"version": "4.9.0", "seed": 20260904, "trials": 128},
             "frozen core fit contract drifted")
    fit_raw = selection._canonical(core, dict(fit_result))
    post_plan, post_bindings, post_measurements, post_admissions, post_context = _mixed_inputs(
        selection, v5, recovery_root=root, expected_plan_sha256=expected_plan_sha256, suffix_root=suffix,
        reviewed_path=review, expected_review_sha256=expected_review_sha256, candidate=candidate, schema_options=options,
        continuation=continuation, continuation_descriptor=continuation_descriptor,
        recovery_projection_binding=projection_binding, continuation_reviews=continuation_reviews,
    )
    _require(plan == post_plan and bindings == post_bindings and context == post_context
             and normalized_raw == selection._canonical(core, _normalized_document(
                 selection, bindings=post_bindings, plan=post_plan, measurements=post_measurements,
                 admissions=post_admissions, context=post_context,
             )), "mixed inputs drifted during TRAIN/DEV selection")
    output.mkdir(parents=True, exist_ok=False)
    normalized_path = output / selection.NORMALIZED_NAME
    fit_path = output / selection.FIT_NAME
    freeze_path = output / selection.FREEZE_NAME
    _write_new(normalized_path, normalized_raw)
    _write_new(fit_path, fit_raw)
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    freeze_raw = selection._canonical(core, _freeze_document(
        selection, bindings=bindings, plan=plan, normalized=normalized_path, normalized_raw=normalized_raw,
        fit=fit_path, fit_raw=fit_raw, fit_result=fit_result, selection_frozen_at=frozen_at, context=context,
    ))
    return {"freeze_path": str(freeze_path), "freeze_sha256": _write_new(freeze_path, freeze_raw)}


def _verify_mixed_context(context: Any) -> dict[str, Any]:
    _require(isinstance(context, Mapping), "mixed v5 selection context is absent")
    expected_counts = {
        "legacy_measurement_count": LEGACY_COUNT,
        "v4_native_measurement_count": V4_NATIVE_COUNT,
        "v5_native_measurement_count": V5_NATIVE_COUNT,
        "local_session_schema_recovered_measurement_count": RECOVERED_COUNT,
        "native_measurement_count": NATIVE_COUNT,
        "measurement_count": MEASUREMENT_COUNT,
    }
    required = set(expected_counts) | {"v4_cell_ids", "v5_native_cell_ids", "recovered_cell_ids", "recovery_bindings",
                                       "authority", "release_or_promotion_authority"}
    _require(set(context) == required and all(context.get(key) == value for key, value in expected_counts.items())
             and context.get("authority") == "development_only_no_runtime_or_confirmation_authority"
             and context.get("release_or_promotion_authority") == "none", "mixed v5 selection context differs")
    v4, v5, recovered = context.get("v4_cell_ids"), context.get("v5_native_cell_ids"), context.get("recovered_cell_ids")
    _require(isinstance(v4, list) and isinstance(v5, list) and len(v4) == V4_NATIVE_COUNT and len(v5) == V5_NATIVE_COUNT
             and isinstance(recovered, list) and recovered == list(RECOVERED_CELL_IDS)
             and all(isinstance(cell_id, str) for cell_id in v4 + v5)
             and len(set(v4)) == V4_NATIVE_COUNT and len(set(v5)) == V5_NATIVE_COUNT and not (set(v4) & set(v5))
             and not (set(v4) | set(v5)) & set(recovered),
             "mixed v5 cell inventory differs")
    bindings = context.get("recovery_bindings")
    _require(isinstance(bindings, Mapping) and set(bindings) == set(RECOVERED_CELL_IDS)
             and all(isinstance(bindings.get(cell_id), Mapping)
                     and bindings[cell_id].get("classification") == "local_session_schema_recovered"
                     for cell_id in RECOVERED_CELL_IDS), "mixed recovery bindings differ")
    return dict(context)


def validate_mixed_context(context: Any) -> dict[str, Any]:
    """Validate the prospective mixed-freeze geometry for downstream consumers."""
    return _verify_mixed_context(context)


def _mixed_static(selection: ModuleType, core: ModuleType, recovery: ModuleType, freeze_path: Path,
                  expected_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], bytes, bytes]:
    freeze, freeze_raw = selection._json(freeze_path, "selection freeze")
    _require(selection._sha256(freeze_raw) == selection._hex(expected_sha256, "expected selection freeze hash")
             and freeze_raw == selection._canonical(core, freeze)
             and freeze.get("kind") == "wpb_grok_train_dev_selection_freeze"
             and freeze.get("inner_core_native_admission") == "not_claimed", "mixed selection freeze bytes drifted")
    normalized_path, fit_path = freeze_path.parent / selection.NORMALIZED_NAME, freeze_path.parent / selection.FIT_NAME
    normalized, normalized_raw = selection._json(normalized_path, "normalized measurements")
    fit, fit_raw = selection._json(fit_path, "core fit result")
    evidence = freeze.get("evidence_files")
    _require(isinstance(evidence, Mapping) and set(evidence) == {selection.NORMALIZED_NAME, selection.FIT_NAME}
             and evidence[selection.NORMALIZED_NAME] == selection._evidence_descriptor(normalized_path, normalized_raw)
             and evidence[selection.FIT_NAME] == selection._evidence_descriptor(fit_path, fit_raw),
             "mixed selection evidence commitment drifted")
    bindings = freeze.get("source_bindings")
    _require(isinstance(bindings, Mapping) and normalized.get("source_bindings") == bindings
             and normalized.get("schedule_sha256") == freeze.get("schedule_sha256") and normalized.get("endpoint") == "grok",
             "mixed normalized export binding drifted")
    context = _verify_mixed_context(freeze.get(MIXED_CONTEXT_KEY))
    expected_classification = {
        "ordinary_measurements": NATIVE_COUNT,
        "local_session_schema_recovered_measurements": RECOVERED_COUNT,
        "recovered_cell_ids": list(RECOVERED_CELL_IDS),
    }
    for document in (freeze, normalized):
        _require(document.get(MIXED_CONTEXT_KEY) == context and document.get("measurement_count") == MEASUREMENT_COUNT
                 and document.get("native_measurement_count") == NATIVE_COUNT
                 and document.get("local_session_schema_recovered_measurement_count") == RECOVERED_COUNT
                 and document.get("measurement_evidence_classification") == expected_classification
                 and document.get("recovered_cell_ids") == list(RECOVERED_CELL_IDS)
                 and document.get("recovery_bindings") == context["recovery_bindings"]
                 and "schema_recovery" not in document, "mixed selection recovery classification differs")
    return dict(freeze), dict(normalized), dict(fit), dict(bindings), normalized_raw, fit_raw


def _verify_bindings(selection: ModuleType, v5: ModuleType, bindings: Mapping[str, Any], schedule_sha256: str) -> tuple[dict[str, Any], bytes]:
    plan, plan_raw = selection._verify_bindings(selection._pinned_core(), selection._pinned_recovery(), bindings, schedule_sha256)
    _require(bindings.get("selection_freeze_helper") == _descriptor(FROZEN_SELECTION, FROZEN_SELECTION_SHA256, "frozen selection helper")
             and bindings.get("v5_suffix_helper") == _descriptor(V5_SUFFIX, V5_SUFFIX_SHA256, "v5 suffix helper"),
             "mixed selection helper binding drifted")
    suffix = bindings.get("v5_suffix_root")
    review = bindings.get("v5_review")
    candidate = bindings.get("v5_candidate")
    _require(isinstance(suffix, str) and isinstance(review, Mapping) and isinstance(candidate, Mapping)
             and bindings.get("v5_isolated_queue_root") == candidate.get("isolated_queue_root"), "mixed v5 source bindings are malformed")
    _require(review == _descriptor(str(review.get("path", "")), str(review.get("sha256", "")), "v5 reviewed authority"),
             "mixed v5 review binding drifted")
    verified = v5.verify_authority(
        recovery_root=Path(str(bindings["recovery_plan"]["path"])).parent, suffix_root=Path(suffix),
        expected_plan_sha256=str(bindings["recovery_plan"]["sha256"]), reviewed_path=Path(str(review["path"])),
        expected_review_sha256=str(review["sha256"]), candidate=candidate,
    )
    _require(verified.get("candidate") == candidate and verified.get("provider_calls_made") == 0
             and verified.get("native_admission_permitted") is False, "mixed v5 candidate or authority replay differs")
    cells = verified.get("cell_ids")
    recorded_reviews = bindings.get("v5_recorded_reviews")
    continuation_reviews = bindings.get("v5_continuation_reviews")
    _require(isinstance(cells, list) and len(cells) == V5_TOTAL_COUNT and cells.count(V5_RECOVERY_CELL) == 1
             and isinstance(recorded_reviews, list) and isinstance(continuation_reviews, Mapping)
             and recorded_reviews == _recorded_reviews(v5, Path(suffix),
                                                        [cell_id for cell_id in cells
                                                         if cell_id != V5_RECOVERY_CELL and cell_id not in continuation_reviews],
                                                        expected_count=15)
             and len(recorded_reviews) == 15,
             "mixed v5 recorded review binding drifted")
    return plan, plan_raw


def _verify_projection_binding(selection: ModuleType, bindings: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[ModuleType, dict[str, str], dict[str, Any], dict[str, dict[str, Any]]]:
    descriptor = bindings.get("recovery_v5_continuation_helper")
    binding = bindings.get("recovery_v5_projection_binding")
    _require(isinstance(descriptor, Mapping) and set(descriptor) == {"path", "sha256"},
             "1088 continuation helper binding is malformed")
    continuation, actual_descriptor = _continuation(str(descriptor.get("path", "")), str(descriptor.get("sha256", "")))
    projection_binding = _projection_binding(binding if isinstance(binding, Mapping) else None)
    _require(actual_descriptor == descriptor, "1088 continuation helper binding drifted")
    cells = [str(item["cell_id"]) for item in plan["cells"][PRE_V5_PREFIX_COUNT:] if isinstance(item, Mapping)]
    v5_native_ids = [cell_id for cell_id in cells if cell_id != V5_RECOVERY_CELL]
    continuation_ids = _continuation_targets(continuation, v5_native_ids)
    _require(v5_native_ids[:15] == [cell_id for cell_id in v5_native_ids if cell_id not in continuation_ids]
             and tuple(v5_native_ids[15:]) == continuation_ids, "v5 continuation boundary drifted")
    review_values, _review_descriptors = _continuation_reviews(selection, bindings.get("v5_continuation_reviews"), continuation_ids)
    recovery_root = Path(str(bindings["recovery_plan"]["path"])).parent
    suffix_root = Path(str(bindings["v5_suffix_root"]))
    for cell_id in continuation_ids:
        _continuation_admission(
            selection, continuation, recovery_root=recovery_root, suffix_root=suffix_root,
            expected_plan_sha256=str(bindings["recovery_plan"]["sha256"]), cell_id=cell_id,
            candidate=bindings["v5_candidate"], projection_binding=projection_binding, review=review_values[cell_id],
        )
    return continuation, projection_binding, _projection(continuation, projection_binding, plan), review_values


def verify_freeze_context(freeze_path: Path | str, expected_sha256: str, replay_native: bool = True) -> dict[str, Any]:
    """Verify a mixed immutable freeze and replay every source record by default."""
    _require(type(replay_native) is bool, "replay_native must be boolean")
    selection, v5 = _pinned_selection(), _pinned_v5()
    core, recovery = selection._pinned_core(), selection._pinned_recovery()
    path = Path(freeze_path).resolve()
    freeze, normalized, fit, bindings, _normalized_raw, fit_raw = _mixed_static(selection, core, recovery, path, expected_sha256)
    _require(normalized.get(MIXED_CONTEXT_KEY) == freeze.get(MIXED_CONTEXT_KEY), "mixed normalized and freeze contexts differ")
    context = _verify_mixed_context(freeze.get(MIXED_CONTEXT_KEY))
    plan, _plan_raw = _verify_bindings(selection, v5, bindings, str(freeze.get("schedule_sha256")))
    continuation, projection_binding, projection, _continuation_review_values = _verify_projection_binding(selection, bindings, plan)
    _require(isinstance(bindings.get("schema_recovery"), Mapping)
             and context["recovery_bindings"].get(RECOVERED_CELL_IDS[0])
             == _schema_recovery_binding(bindings["schema_recovery"]), "0843 recovery binding drifted")
    _require(context["recovery_bindings"].get(V5_RECOVERY_CELL) == {
        "classification": "local_session_schema_recovered",
        "continuation_helper": dict(bindings["recovery_v5_continuation_helper"]), "projection": projection,
    }, "1088 recovery binding drifted")
    _require(normalized.get("source_bindings") == bindings and normalized.get("schedule_sha256") == freeze.get("schedule_sha256")
             and normalized.get("endpoint") == "grok", "mixed normalized export binding drifted")
    measurements = normalized.get("measurements")
    _require(isinstance(measurements, list), "mixed normalized export lacks measurements")
    _resolution, rows, _tasks = selection._schedule(core, recovery, plan)
    validated = selection._validate_measurements(core, Path(str(plan["freeze_root"])), str(plan["schedule_sha256"]), rows, measurements)
    _require(measurements == validated, "mixed normalized measurement order drifted")
    if replay_native:
        options = selection._schema_options_from_binding(bindings)
        post_plan, post_bindings, post_measurements, post_admissions, post_context = _mixed_inputs(
            selection, v5, recovery_root=Path(str(bindings["recovery_plan"]["path"])).parent,
            expected_plan_sha256=str(bindings["recovery_plan"]["sha256"]), suffix_root=Path(str(bindings["v5_suffix_root"])),
            reviewed_path=Path(str(bindings["v5_review"]["path"])), expected_review_sha256=str(bindings["v5_review"]["sha256"]),
            candidate=bindings["v5_candidate"], schema_options=options,
            continuation=continuation, continuation_descriptor=bindings["recovery_v5_continuation_helper"],
            recovery_projection_binding=projection_binding, continuation_reviews=bindings["v5_continuation_reviews"],
        )
        _require(post_bindings == bindings and post_context == context
                 and selection._canonical(core, _normalized_document(selection, bindings=post_bindings, plan=post_plan,
                                                                     measurements=post_measurements, admissions=post_admissions,
                                                                     context=post_context)) == selection._canonical(core, normalized),
                 "mixed native replay differs from frozen export")
        replayed_fit = core.fit_train_select_dev(Path(str(post_plan["freeze_root"])), post_measurements, trials=128)
        _require(selection._canonical(core, dict(replayed_fit)) == fit_raw, "mixed core TRAIN/DEV fit replay differs from frozen result")
    selected = freeze.get("selected_profile")
    _require(isinstance(selected, Mapping) and fit.get("selected_profile") == selected
             and fit.get("selected_profile_name") == freeze.get("selected_profile_name"), "mixed selection profile binding drifted")
    return {
        "freeze_sha256": expected_sha256, "selection_frozen_at": freeze.get("selection_frozen_at"),
        "selected_profile": dict(selected), "schedule_sha256": freeze.get("schedule_sha256"),
        "source_bindings": dict(bindings), MIXED_CONTEXT_KEY: context,
    }
