"""Provider-free selected100 analysis over the complete Dryad Grok successor chain."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
READER_PATH = ROOT / "baseline_grok_successor_collection_replay.py"
CONTROLLER_PATH = ROOT / "baseline_grok_selected_successor.py"
LOCAL_CONTROLLER_PATH = ROOT / "baseline_grok_selected_local_continuation.py"
OLD_HELPER_PATH = ROOT / "baseline_grok_recovery_analysis.py"
COMPOSITE_PATH = ROOT / "baseline_composite_admission_v5.py"
ANALYSIS_PATH = ROOT / "baseline_composite_analysis_v5.py"
ENGINE_PATH = ROOT / "baseline_selected_analysis_runtime.py"
OLD_HELPER_SHA256 = "ae10578a9d1bd12b3e2b02744d06c216974508f196d7ba865776c6b0b200c808"
PIN_KEYS = frozenset({
    "analysis", "reader", "successor_controller", "old_helper_closure", "composite",
    "composite_analysis", "selected_engine", "workflow", "v1_runtime_loader", "v5_runtime_loader",
    "local_controller", "local_proposal", "local_adoption",
})
EXPECTED_COUNTS = {"stories": 100, "logical_requests": 2300, "native_requests": 2299,
                   "study_recovered_requests": 1, "criterion_verdicts": 17800}
LOCAL_EXPECTED_COUNTS = {"stories": 100, "logical_requests": 2300, "native_requests": 2298,
                         "study_recovered_requests": 1, "local_recovered_requests": 1, "criterion_verdicts": 17800}
TRAIN_COUNT, DEV_COUNT, QUESTION_COUNT = 70, 30, 178
ORIGINAL_COUNTS = {"TRAIN": 176, "DEV": 60}
CANONICAL_VERDICTS = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _strict_json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{label} has duplicate keys")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error


def _read(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, label + " expected hash") or checked.read_bytes() != raw:
        raise ValueError(f"{label} hash drift")
    return checked, raw


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    spec = importlib.util.spec_from_loader(f"_dryad_grok_successor_{label}", loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local helper.
    return module


def _pins(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != PIN_KEYS:
        raise ValueError("Successor source pins differ")
    result = {key: _hash(value[key], "Successor source pin " + key) for key in PIN_KEYS}
    if result["old_helper_closure"] != OLD_HELPER_SHA256:
        raise ValueError("Frozen recovery helper closure differs")
    return result


def _capture(source_pins: Mapping[str, Any]) -> tuple[dict[Path, bytes], ModuleType, ModuleType, ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]:
    pins = _pins(source_pins)
    paths = (
        (Path(__file__).resolve(), pins["analysis"], "analysis"),
        (READER_PATH, pins["reader"], "reader"),
        (CONTROLLER_PATH, pins["successor_controller"], "successor_controller"),
        (LOCAL_CONTROLLER_PATH, pins["local_controller"], "local_controller"),
        (OLD_HELPER_PATH, pins["old_helper_closure"], "old_helper_closure"),
        (COMPOSITE_PATH, pins["composite"], "composite"),
        (ANALYSIS_PATH, pins["composite_analysis"], "composite_analysis"),
        (ENGINE_PATH, pins["selected_engine"], "selected_engine"),
    )
    captured: dict[Path, bytes] = {}
    loaded: dict[str, ModuleType] = {}
    for path, expected, label in paths:
        checked, raw = _read(path, expected, label)
        captured[checked] = raw
        loaded[label] = _load(checked, raw, label)
    if getattr(loaded["reader"], "SUCCESSOR_SHA256", None) != pins["successor_controller"]:
        raise ValueError("Successor reader controller source pin differs")
    return (captured, loaded["reader"], loaded["successor_controller"], loaded["old_helper_closure"],
            loaded["composite"], loaded["composite_analysis"], loaded["selected_engine"], loaded["local_controller"])


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned successor analysis source changed during execution")


def _capture_local_closure(captured: dict[Path, bytes], admission: SelectedSuccessorAdmission,
                           source_pins: Mapping[str, str]) -> None:
    local = admission.record.get("local_recovery")
    if local is None:
        return
    protected = local.get("protected_paths")
    if not isinstance(protected, Mapping):
        raise ValueError("Selected local continuation protected paths differ")  # noqa: TRY004
    for name, pin in (("proposal", source_pins["local_proposal"]), ("adoption", source_pins["local_adoption"])):
        descriptor = protected.get(name)
        if not isinstance(descriptor, Mapping):
            raise ValueError("Selected local continuation proof closure differs")  # noqa: TRY004
        path, raw = _read(descriptor.get("path"), pin, "Local " + name)
        captured[path] = raw


def _endpoint_view(record: Mapping[str, Any]) -> dict[str, Any]:
    selection = record["selection"]
    return {"selection": {"schedule": selection["schedule"], "source": selection["source"],
                           "train_pass_ids": list(selection["train_pass_ids"]), "dev_pass_ids": list(selection["dev_pass_ids"])},
            "endpoint_grok_rows": [{"pass_id": row["pass_id"], "opaque_story_id": row["opaque_story_id"],
                                    "verdicts": row["verdict_rows"]} for row in record["collection_record"]["rows"]]}


class SelectedSuccessorAdmission:
    def __init__(self, *, record: dict[str, Any], sha256: str) -> None:
        self.record = record
        self.sha256 = sha256

    @property
    def endpoint_view(self) -> dict[str, Any]:
        return _endpoint_view(self.record)


def _root_chain(collection: Mapping[str, Any]) -> Any:
    chain = collection.get("successor_root_chain")
    if not isinstance(chain, list) or not chain:
        raise ValueError("Complete successor root chain is required")
    return chain


def _local_descriptor(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"root", "manifest_sha256", "controller_sha256"}:
        raise ValueError("Selected local continuation descriptor differs")
    root = value.get("root")
    if type(root) is not str or not root:
        raise ValueError("Selected local continuation descriptor differs")
    return {"root": root, "manifest_sha256": _hash(value.get("manifest_sha256"), "Local continuation manifest"),
            "controller_sha256": _hash(value.get("controller_sha256"), "Local continuation controller")}


def _admit_collection(collection: Mapping[str, Any], reader: ModuleType, *, source_pins: Mapping[str, str],
                      reader_inputs: Mapping[str, Any], selection: Mapping[str, Any], predecessor: Mapping[str, Any],
                      exclusions: Mapping[str, set[str]]) -> SelectedSuccessorAdmission:
    local_descriptor = _local_descriptor(reader_inputs.get("local_continuation"))
    expected_schema, expected_evidence, expected_counts, expected_recovered = (
        (2, "selected100_grok_successor_local_schema_recovery_replay_only_v2", LOCAL_EXPECTED_COUNTS, [70, 254])
        if local_descriptor is not None else (1, "selected100_grok_successor_collection_replay_only_v1", EXPECTED_COUNTS, [70]))
    if (not isinstance(collection, Mapping) or collection.get("schema_version") != expected_schema
            or collection.get("evidence_class") != expected_evidence
            or collection.get("counts") != expected_counts or collection.get("recovered_ordinals") != expected_recovered
            or collection.get("coverage_failures") != [] or collection.get("full_study_admitted") is not False
            or collection.get("authority") is not False or collection.get("provider_calls_made") != 0
            or collection.get("historical_prototype_only") is not (local_descriptor is None)):
        raise ValueError("Complete selected successor collection replay is required")
    commitments = collection.get("input_commitments")
    if not isinstance(commitments, Mapping) or commitments.get("reader_sha256") != source_pins["reader"]:
        raise ValueError("Selected successor collection reader binding differs")
    if commitments.get("successor_controller_sha256") != source_pins["successor_controller"]:
        raise ValueError("Selected successor controller binding differs")
    expected_commitments = {
        "plan_sha256": reader_inputs["expected_plan_sha256"],
        "predecessor_sha256": reader_inputs["expected_predecessor_sha256"],
        "old_suffix_epoch_sha256": reader_inputs["expected_old_epoch_sha256"],
        "suffix_helper_sha256": reader_inputs["expected_suffix_source_sha256"],
        "composite_helper_sha256": source_pins["composite"],
        "recovery_controller_sha256": reader_inputs["expected_recovery_controller_sha256"],
        "recovery_manifest_sha256": reader_inputs["expected_recovery_manifest_sha256"],
    }
    if any(commitments.get(key) != value for key, value in expected_commitments.items()):
        raise ValueError("Selected successor predecessor binding differs")
    roots = _root_chain(collection)
    if reader._sha(reader._canonical(roots)) != commitments.get("successor_root_chain_sha256"):
        raise ValueError("Selected successor root chain commitment differs")
    owners = collection.get("root_chain_ordinal_owners")
    chain_commitments = commitments.get("root_chain")
    if (not isinstance(owners, Mapping) or not isinstance(chain_commitments, list) or len(chain_commitments) != len(roots) + 1
            or not isinstance(chain_commitments[0], Mapping) or chain_commitments[0].get("kind") != "first_recovery"
            or any(not isinstance(item, Mapping) or item.get("kind") != "successor"
                   for item in chain_commitments[1:])):
        raise ValueError("Selected successor root ownership differs")
    if [item.get("root") for item in chain_commitments[1:]] != [item.get("root") for item in roots]:
        raise ValueError("Selected successor root chain order differs")
    root_owned = []
    for item in chain_commitments:
        for field in ("partial_completed_ordinals", "replayed_ordinals"):
            ordinals = item.get(field, [])
            if not isinstance(ordinals, list) or any(type(ordinal) is not int for ordinal in ordinals):
                raise ValueError("Selected successor root ownership coverage differs")
            root_owned.extend(ordinals)
    local_record: dict[str, Any] | None = None
    if local_descriptor is not None:
        local_commitment = collection.get("local_continuation_commitment")
        local_identity = collection.get("local_recovery_identity")
        local_provenance = collection.get("local_recovery_provenance")
        protected_paths = collection.get("local_recovery_protected_paths")
        local_owner = owners.get(254)
        protected_names = {"continuation_root", "continuation_manifest", "controller", "successor_root", "successor_manifest",
                           "partial", "proposal", "adoption", "independent_review", "standing_authority", "local_projection",
                           "protected_native_identities", "inner_epoch"}
        protected_hash = reader._sha(reader._canonical(protected_paths)) if isinstance(protected_paths, Mapping) else None
        local_expected = {"local_continuation_manifest_sha256": local_descriptor["manifest_sha256"],
                          "local_continuation_controller_sha256": local_descriptor["controller_sha256"],
                          "local_continuation_descriptor_sha256": reader._sha(reader._canonical(local_descriptor)),
                          "local_recovery_identity_sha256": local_identity.get("identity_sha256") if isinstance(local_identity, Mapping) else None}
        if (collection.get("local_continuation") != local_descriptor or not isinstance(local_commitment, Mapping)
                or local_commitment.get("root") != local_descriptor["root"]
                or local_commitment.get("manifest_sha256") != local_descriptor["manifest_sha256"]
                or local_commitment.get("controller_sha256") != local_descriptor["controller_sha256"]
                or not isinstance(local_identity, Mapping) or local_identity.get("kind") != "local_schema_projection"
                or local_identity.get("ordinal") != 254 or not isinstance(local_provenance, Mapping)
                or local_provenance.get("proposal_sha256") != source_pins["local_proposal"]
                or local_provenance.get("adoption_sha256") != source_pins["local_adoption"]
                or not isinstance(protected_paths, Mapping) or set(protected_paths) != protected_names
                or any(not isinstance(item, Mapping) or type(item.get("path")) is not str or not item["path"]
                       or _hash(item.get("inventory_sha256") if name in {"continuation_root", "successor_root"} else item.get("sha256"),
                                "Local protected path " + name) != (item.get("inventory_sha256") if name in {"continuation_root", "successor_root"} else item.get("sha256"))
                       for name, item in protected_paths.items())
                or local_commitment.get("protected_paths_sha256") != protected_hash
                or not isinstance(local_owner, Mapping) or local_owner.get("kind") != "local_schema_recovery"
                or local_owner.get("local_identity") != dict(local_identity)
                or local_owner.get("local_provenance") != dict(local_provenance)
                or local_owner.get("replay_receipt") != "local_projection"
                or any(commitments.get(key) != value for key, value in local_expected.items())):
            raise ValueError("Selected local continuation binding differs")
        partial_peers, untouched = local_commitment.get("partial_peer_ordinals"), local_commitment.get("untouched_replay_ordinals")
        combined_local_ordinals = [*partial_peers, *untouched] if isinstance(partial_peers, list) and isinstance(untouched, list) else []
        if (not isinstance(partial_peers, list) or not isinstance(untouched, list)
                or any(type(ordinal) is not int for ordinal in combined_local_ordinals)
                or 254 in partial_peers or 254 in untouched or len(combined_local_ordinals) != len(set(combined_local_ordinals))):
            raise ValueError("Selected local continuation ownership differs")
        root_owned.extend([*partial_peers, 254, *untouched])
        local_record = {"descriptor": local_descriptor, "commitment": dict(local_commitment),
                        "identity": dict(local_identity), "provenance": dict(local_provenance),
                        "protected_paths": {name: dict(item) for name, item in protected_paths.items()}}
    if (len(root_owned) != len(set(root_owned)) or set(owners) != set(root_owned) or 70 in owners):
        raise ValueError("Selected successor root ownership coverage differs")
    rows, identities = collection.get("rows"), collection.get("native_identities")
    expected_native = 2298 if local_descriptor is not None else 2299
    if not isinstance(rows, list) or len(rows) != 100 or not isinstance(identities, list) or len(identities) != expected_native:
        raise ValueError("Selected successor collection cardinality differs")
    if collection.get("native_identity_commitment_sha256") != reader._sha(reader._canonical(identities)):
        raise ValueError("Selected successor identity commitment differs")
    historical = collection.get("historical_excluded_native_identities")
    if (not isinstance(historical, list) or len(historical) != 33
            or {item.get("request_id_hash") for item in historical if isinstance(item, Mapping)} != exclusions["requests"]
            or {item.get("session_id_hash") for item in historical if isinstance(item, Mapping)} != exclusions["sessions"]):
        raise ValueError("Selected successor historical identity exclusions differ")
    verified = selection["verified"]
    train_passes, dev_passes = verified["selected_train_ids"], verified["selected_dev_ids"]
    expected_ordinals = [*range(1, 1611), *range(4049, 4739)]
    if (not isinstance(train_passes, list) or not isinstance(dev_passes, list) or len(train_passes) != TRAIN_COUNT
            or len(dev_passes) != DEV_COUNT or len(set(train_passes + dev_passes)) != 100
            or verified.get("selected_request_ordinals") != expected_ordinals):
        raise ValueError("Original selected schedule differs")
    if ([row.get("pass_id") for row in rows] != train_passes + dev_passes
            or [row.get("partition") for row in rows] != ["TRAIN"] * TRAIN_COUNT + ["DEV"] * DEV_COUNT
            or [ordinal for row in rows for ordinal in row.get("ordinals", [])] != expected_ordinals):
        raise ValueError("Selected successor collection schedule differs")
    if (len({row.get("opaque_story_id") for row in rows}) != 100
            or any(not isinstance(row.get("source"), Mapping) or type(row.get("score")) not in (int, float)
                   or not math.isfinite(row["score"]) or not 0 <= row["score"] <= 100
                   or type(row.get("coverage")) not in (int, float) or not math.isfinite(row["coverage"])
                   or not .88 <= row["coverage"] <= 1 for row in rows)):
        raise ValueError("Selected successor score or coverage differs")
    question_ids = verified.get("question_ids")
    if not isinstance(question_ids, list) or len(question_ids) != QUESTION_COUNT or len(set(question_ids)) != QUESTION_COUNT:
        raise ValueError("Selected schedule question inventory differs")
    for row in rows:
        verdicts = row.get("verdict_rows")
        if (not isinstance(verdicts, list) or len(verdicts) != QUESTION_COUNT
                or any(not isinstance(item, Mapping) or item.get("verdict") not in CANONICAL_VERDICTS for item in verdicts)
                or [item.get("question_id") for item in verdicts] != question_ids):
            raise ValueError("Selected successor verdict rows differ")
    normalized = collection.get("normalized_verdict_rows")
    expected_normalized = [{"pass_id": row["pass_id"], "opaque_story_id": row["opaque_story_id"], **item}
                           for row in rows for item in row["verdict_rows"]]
    if not isinstance(normalized, list) or len(normalized) != 17800 or normalized != expected_normalized:
        raise ValueError("Selected successor normalized verdict rows differ")
    if (commitments.get("selected_schedule_sha256") != selection["schedule"]["sha256"]
            or commitments.get("selected_schedule_source_sha256") != selection["source"]["sha256"]):
        raise ValueError("Selected successor schedule binding differs")
    composite = _load(COMPOSITE_PATH, _read(COMPOSITE_PATH, source_pins["composite"], "composite")[1], "composite")
    composite._identity_sets(identities, exclusions["requests"], exclusions["sessions"])
    local_70 = [row for row in rows if 70 in row["ordinals"]]
    if len(local_70) != 1:
        raise ValueError("Selected successor local ordinal 70 binding differs")
    collection_raw = reader._canonical(collection)
    collection_record = _strict_json(collection_raw, "Selected successor collection")
    record = {"schema_version": expected_schema, "evidence_class": "selected100_dryad_grok_successor_admission_v1" if local_record is None else "selected100_dryad_grok_successor_local_schema_admission_v2",
              "selected_successor_admitted": True, "original_full_study_admitted": False,
              "provider_calls_made": 0, "execution_authority": False, "promotion_authority": False,
              "confirmation_authority": False, "source_pins": dict(source_pins),
              "collection_record": collection_record, "collection_sha256": reader._sha(collection_raw),
              "successor_root_chain": roots, "predecessor": dict(predecessor),
              "selection": {"schedule": selection["schedule"], "source": selection["source"],
                            "train_pass_ids": list(train_passes), "dev_pass_ids": list(dev_passes),
                            "request_ordinals": expected_ordinals},
              "native_identity_commitment_sha256": collection["native_identity_commitment_sha256"]}
    if local_record is not None:
        record["local_recovery"] = local_record
    return SelectedSuccessorAdmission(record=record, sha256=_sha(_canonical(record)))


def admit_selected_successor(*, reader_inputs: Mapping[str, Any], source_pins: Mapping[str, Any]) -> SelectedSuccessorAdmission:
    """Re-admit every complete successor root before opening either target partition."""
    pins = _pins(source_pins)
    required = {"plan_root", "predecessor_path", "old_suffix_root", "recovery_root", "expected_plan_sha256",
                "expected_predecessor_sha256", "expected_old_epoch_sha256", "expected_suffix_source_sha256",
                "expected_recovery_controller_sha256", "expected_recovery_manifest_sha256", "expected_public_inputs_sha256", "approved_v4_routes",
                "approved_v5_routes", "successor_roots", "local_continuation"}
    if not isinstance(reader_inputs, Mapping) or set(reader_inputs) != required:
        raise ValueError("Selected successor reader inputs differ")
    if _local_descriptor(reader_inputs["local_continuation"]) is None:
        raise ValueError("Selected successor local continuation is required")
    captured, reader, _controller, old, composite, _analysis, _engine, _local = _capture(pins)
    inputs = dict(reader_inputs)
    reader_call = {key: value for key, value in inputs.items() if key not in {"expected_public_inputs_sha256", "successor_roots", "local_continuation"}}
    collection = reader.read_selected_successor_collection(successor_roots=inputs["successor_roots"],
                                                           local_continuation=inputs["local_continuation"], **reader_call)
    selection, predecessor, exclusions = old._selection(
        composite, plan_root=Path(inputs["plan_root"]).resolve(), predecessor_path=inputs["predecessor_path"],
        suffix_root=inputs["old_suffix_root"], expected_plan_sha256=inputs["expected_plan_sha256"],
        expected_predecessor_sha256=inputs["expected_predecessor_sha256"],
        expected_suffix_epoch_sha256=inputs["expected_old_epoch_sha256"],
        expected_suffix_source_sha256=inputs["expected_suffix_source_sha256"],
        expected_public_inputs_sha256=inputs["expected_public_inputs_sha256"])
    admitted = _admit_collection(collection, reader, source_pins=pins, reader_inputs=inputs, selection=selection,
                                 predecessor=predecessor, exclusions=exclusions)
    _capture_local_closure(captured, admitted, pins)
    _unchanged(captured)
    return admitted


def _runtime(old: ModuleType, analysis: ModuleType, *, source_pins: Mapping[str, str], scoring_inputs: Mapping[str, Any], captured: dict[Path, bytes]) -> dict[str, Any]:
    return old._runtime(analysis, source_pins=source_pins, scoring_inputs=scoring_inputs, captured=captured)


def _stage(old: ModuleType, admission: SelectedSuccessorAdmission, analysis: ModuleType, *, public_inputs_path: Path | str,
           expected_public_inputs_sha256: str) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, Any]]:
    return old._stage(admission, analysis, public_inputs_path=public_inputs_path,
                      expected_public_inputs_sha256=expected_public_inputs_sha256)


def _reader_public(reader_inputs: Mapping[str, Any], expected_public_inputs_sha256: str) -> None:
    if reader_inputs.get("expected_public_inputs_sha256") != expected_public_inputs_sha256:
        raise ValueError("Selected successor admission public-input binding differs")


def _protected_inputs(reader_inputs: Mapping[str, Any], scoring_inputs: Mapping[str, Any],
                      local_recovery: Mapping[str, Any] | None = None) -> tuple[Any, ...]:
    roots = reader_inputs.get("successor_roots")
    if (not isinstance(roots, (list, tuple)) or not roots
            or any(not isinstance(item, Mapping) or set(item) != {"root", "manifest_sha256"}
                   or not isinstance(item.get("root"), str) or not item["root"]
                   or _hash(item.get("manifest_sha256"), "Successor root manifest") != item["manifest_sha256"]
                   for item in roots)):
        raise ValueError("Selected successor roots differ")
    descriptor = _local_descriptor(reader_inputs.get("local_continuation"))
    local_paths: tuple[Any, ...] = ()
    if local_recovery is not None:
        protected = local_recovery.get("protected_paths")
        if not isinstance(protected, Mapping) or not protected:
            raise ValueError("Selected local continuation protected paths differ")
        local_paths = tuple(value.get("path") for value in protected.values() if isinstance(value, Mapping))
        if len(local_paths) != len(protected) or any(type(path) is not str or not path for path in local_paths):
            raise ValueError("Selected local continuation protected paths differ")
    return (reader_inputs["plan_root"], reader_inputs["predecessor_path"], reader_inputs["old_suffix_root"],
            reader_inputs["recovery_root"], *(item["root"] for item in roots),
            *(() if descriptor is None else (descriptor["root"],)), *local_paths,
            scoring_inputs["scoring_manifest_path"], scoring_inputs["v5_runtime_manifest_path"],
            scoring_inputs["v5_runtime_package_root"])


def _freeze(stage: str, admission: SelectedSuccessorAdmission, *, source_pins: Mapping[str, str], scoring: Mapping[str, Any],
            engine_binding: Mapping[str, Any], projection: Mapping[str, Any], target_projection: Mapping[str, Any],
            inner_raw: bytes, inner: Mapping[str, Any], train: Mapping[str, str] | None = None) -> dict[str, Any]:
    local = admission.record.get("local_recovery")
    result = {"schema_version": 2 if local is not None else 1,
              "evidence_class": f"selected100_dryad_grok_successor_{'local_schema_' if local is not None else ''}{stage.lower()}_freeze_v{'2' if local is not None else '1'}",
              "stage": stage, "provider_calls_made": 0, "execution_authority": False, "promotion_authority": False,
              "confirmation_authority": False, "admission": {"sha256": admission.sha256,
                                                                 "collection_sha256": admission.record["collection_sha256"],
                                                                 "record": admission.record},
              "successor_root_chain": admission.record["successor_root_chain"], "source_pins": dict(source_pins),
              "scoring_commitment_sha256": scoring["commitment_sha256"], "engine_binding": dict(engine_binding),
              "verdict_projection": dict(projection), "target_projection": dict(target_projection),
              "inner": {"sha256": _sha(inner_raw), "evidence_class": inner.get("evidence_class")}}
    if train is not None:
        result["train"] = dict(train)
    if local is not None:
        result["local_recovery"] = local
    return result


def fit_selected_successor_train(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str,
                                 expected_public_inputs_sha256: str, train_targets_path: Path | str, output_root: Path | str,
                                 source_pins: Mapping[str, Any], scoring_inputs: Mapping[str, Any]) -> dict[str, Any]:
    pins = _pins(source_pins); _reader_public(reader_inputs, expected_public_inputs_sha256)
    admission = admit_selected_successor(reader_inputs=reader_inputs, source_pins=pins)
    captured, _reader, _controller, old, _composite, analysis, engine, _local = _capture(pins)
    output = analysis._output_preflight(output_root, *_protected_inputs(reader_inputs, scoring_inputs, admission.record.get("local_recovery")), public_inputs_path, train_targets_path)
    partitions, projected, projection, binding = _stage(old, admission, analysis, public_inputs_path=public_inputs_path,
                                                          expected_public_inputs_sha256=expected_public_inputs_sha256)
    scoring = _runtime(old, analysis, source_pins=pins, scoring_inputs=scoring_inputs, captured=captured)
    pure = _load(analysis.WORKFLOW_PATH, _read(analysis.WORKFLOW_PATH, pins["workflow"], "workflow")[1], "workflow")
    target_path, target_raw, targets, target_projection = analysis._selected_targets(
        pure, train_targets_path, pure.TRAIN_TARGETS_SHA256, "TRAIN", partitions["TRAIN"],
        _read(public_inputs_path, expected_public_inputs_sha256, "public inputs")[1])
    captured[target_path] = target_raw; _unchanged(captured)
    fit = engine.fit_train(projected["TRAIN"], targets, selection_binding=binding,
                           expected_successor_sha256=pins["selected_engine"],
                           baseline_manifest_path=scoring_inputs["scoring_manifest_path"],
                           baseline_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"])
    if not isinstance(fit, Mapping) or fit.get("evidence_class") != "selected100_amended_fit_unadmitted":
        raise ValueError("Unchanged selected TRAIN engine class differs")
    pure._inner_commitments(fit, projected["TRAIN"], targets, target_projection["selected_target_sha256"])
    fit_raw = _canonical(fit); _unchanged(captured)
    freeze = _freeze("TRAIN", admission, source_pins=pins, scoring=scoring, engine_binding=binding,
                     projection=projection, target_projection=target_projection, inner_raw=fit_raw, inner=fit)
    return {"artifacts": analysis._write(output, {"selected100-grok-successor-fit-v1.json": fit_raw,
                                                     "selected100-grok-successor-train-freeze-v1.json": _canonical(freeze)}),
            "freeze": freeze}


def _train_binding(fit_raw: bytes, freeze_raw: bytes, *, admission: SelectedSuccessorAdmission, source_pins: Mapping[str, str],
                   scoring: Mapping[str, Any], binding: Mapping[str, Any], projection: Mapping[str, Any],
                   expected_train_target_sha256: str) -> None:
    fit = _strict_json(fit_raw, "Frozen selected successor TRAIN fit")
    freeze = _strict_json(freeze_raw, "Frozen selected successor TRAIN freeze")
    local = admission.record.get("local_recovery")
    expected_evidence = "selected100_dryad_grok_successor_local_schema_train_freeze_v2" if local is not None else "selected100_dryad_grok_successor_train_freeze_v1"
    if (not isinstance(fit, Mapping) or not isinstance(freeze, Mapping)
            or freeze.get("evidence_class") != expected_evidence
            or freeze.get("stage") != "TRAIN" or freeze.get("admission") != {"sha256": admission.sha256,
                "collection_sha256": admission.record["collection_sha256"], "record": admission.record}
            or freeze.get("successor_root_chain") != admission.record["successor_root_chain"]
            or (local is not None and freeze.get("local_recovery") != local)
            or freeze.get("source_pins") != dict(source_pins) or freeze.get("scoring_commitment_sha256") != scoring["commitment_sha256"]
            or freeze.get("engine_binding") != dict(binding) or freeze.get("verdict_projection") != dict(projection)
            or freeze.get("inner", {}).get("sha256") != _sha(fit_raw)
            or fit.get("input_commitments", {}).get("verdict_rows_sha256") != projection["projected_rows_sha256"]["TRAIN"]):
        raise ValueError("Selected successor TRAIN freeze binding differs")
    target, commitments = freeze.get("target_projection"), fit.get("input_commitments", {})
    if (not isinstance(target, Mapping) or target.get("original_target_sha256") != expected_train_target_sha256
            or target.get("original_count") != ORIGINAL_COUNTS["TRAIN"] or target.get("selected_count") != TRAIN_COUNT
            or target.get("selected_target_sha256") != commitments.get("target_rows_sha256")
            or any(_hash(target.get(name), "Selected successor TRAIN target " + name) != target[name]
                   for name in ("original_target_sha256", "selected_target_sha256"))):
        raise ValueError("Selected successor TRAIN target projection differs")


def _compute_dev(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str, expected_public_inputs_sha256: str,
                 dev_targets_path: Path | str, fit_path: Path | str, train_freeze_path: Path | str,
                 expected_fit_sha256: str, expected_train_freeze_sha256: str, source_pins: Mapping[str, Any],
                 scoring_inputs: Mapping[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[Path, bytes]]:
    pins = _pins(source_pins); _reader_public(reader_inputs, expected_public_inputs_sha256)
    admission = admit_selected_successor(reader_inputs=reader_inputs, source_pins=pins)
    captured, _reader, _controller, old, _composite, analysis, engine, _local = _capture(pins)
    partitions, projected, projection, binding = _stage(old, admission, analysis, public_inputs_path=public_inputs_path,
                                                          expected_public_inputs_sha256=expected_public_inputs_sha256)
    scoring = _runtime(old, analysis, source_pins=pins, scoring_inputs=scoring_inputs, captured=captured)
    fit_checked, fit_raw = _read(fit_path, expected_fit_sha256, "Frozen selected successor TRAIN fit")
    freeze_checked, freeze_raw = _read(train_freeze_path, expected_train_freeze_sha256, "Frozen selected successor TRAIN freeze")
    captured[fit_checked], captured[freeze_checked] = fit_raw, freeze_raw
    pure = _load(analysis.WORKFLOW_PATH, _read(analysis.WORKFLOW_PATH, pins["workflow"], "workflow")[1], "workflow")
    _train_binding(fit_raw, freeze_raw, admission=admission, source_pins=pins, scoring=scoring, binding=binding,
                   projection=projection, expected_train_target_sha256=pure.TRAIN_TARGETS_SHA256)
    _unchanged(captured)
    engine.validate_frozen_fit(fit_raw, expected_fit_sha256=expected_fit_sha256, selection_binding=binding,
                               expected_successor_sha256=pins["selected_engine"],
                               baseline_manifest_path=scoring_inputs["scoring_manifest_path"],
                               baseline_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"])
    _unchanged(captured)
    target_path, target_raw, targets, target_projection = analysis._selected_targets(
        pure, dev_targets_path, pure.DEV_TARGETS_SHA256, "DEV", partitions["DEV"],
        _read(public_inputs_path, expected_public_inputs_sha256, "public inputs")[1])
    captured[target_path] = target_raw
    result = engine.evaluate_dev(projected["DEV"], targets, fit_raw, expected_fit_sha256=expected_fit_sha256,
                                 selection_binding=binding, expected_successor_sha256=pins["selected_engine"],
                                 baseline_manifest_path=scoring_inputs["scoring_manifest_path"],
                                 baseline_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"])
    if not isinstance(result, Mapping) or result.get("evidence_class") != "selected100_amended_dev_comparison_unadmitted":
        raise ValueError("Unchanged selected DEV engine class differs")
    pure._inner_commitments(result, projected["DEV"], targets, target_projection["selected_target_sha256"])
    raw = _canonical(result); _unchanged(captured)
    freeze = _freeze("DEV", admission, source_pins=pins, scoring=scoring, engine_binding=binding, projection=projection,
                     target_projection=target_projection, inner_raw=raw, inner=result,
                     train={"fit_sha256": expected_fit_sha256, "freeze_sha256": expected_train_freeze_sha256})
    return dict(result), raw, freeze, captured


def compare_selected_successor_dev(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str,
                                  expected_public_inputs_sha256: str, dev_targets_path: Path | str, fit_path: Path | str,
                                  train_freeze_path: Path | str, output_root: Path | str, expected_fit_sha256: str,
                                  expected_train_freeze_sha256: str, source_pins: Mapping[str, Any],
                                  scoring_inputs: Mapping[str, Any]) -> dict[str, Any]:
    pins = _pins(source_pins); _reader_public(reader_inputs, expected_public_inputs_sha256)
    admission = admit_selected_successor(reader_inputs=reader_inputs, source_pins=pins)
    analysis = _load(ANALYSIS_PATH, _read(ANALYSIS_PATH, pins["composite_analysis"], "composite analysis")[1], "output")
    output = analysis._output_preflight(output_root, *_protected_inputs(reader_inputs, scoring_inputs, admission.record.get("local_recovery")), public_inputs_path,
                                         dev_targets_path, fit_path, train_freeze_path)
    result, raw, freeze, _captured = _compute_dev(reader_inputs=reader_inputs, public_inputs_path=public_inputs_path,
        expected_public_inputs_sha256=expected_public_inputs_sha256, dev_targets_path=dev_targets_path, fit_path=fit_path,
        train_freeze_path=train_freeze_path, expected_fit_sha256=expected_fit_sha256,
        expected_train_freeze_sha256=expected_train_freeze_sha256, source_pins=pins, scoring_inputs=scoring_inputs)
    freeze["selection_frozen_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"artifacts": analysis._write(output, {"selected100-grok-successor-dev-comparison-v1.json": raw,
                                                     "selected100-grok-successor-dev-freeze-v1.json": _canonical(freeze)}),
            "freeze": freeze, "comparison": result}


def replay_selected_successor_dev(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str,
                                  expected_public_inputs_sha256: str, dev_targets_path: Path | str, fit_path: Path | str,
                                  train_freeze_path: Path | str, dev_comparison_path: Path | str, dev_freeze_path: Path | str,
                                  expected_fit_sha256: str, expected_train_freeze_sha256: str, expected_dev_comparison_sha256: str,
                                  expected_dev_freeze_sha256: str, source_pins: Mapping[str, Any],
                                  scoring_inputs: Mapping[str, Any]) -> dict[str, Any]:
    _reader_public(reader_inputs, expected_public_inputs_sha256)
    comparison_path, comparison_raw = _read(dev_comparison_path, expected_dev_comparison_sha256, "Stored successor DEV comparison")
    freeze_path, freeze_raw = _read(dev_freeze_path, expected_dev_freeze_sha256, "Stored successor DEV freeze")
    stored = _strict_json(freeze_raw, "Stored successor DEV freeze")
    timestamp = stored.get("selection_frozen_at") if isinstance(stored, Mapping) else None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if type(timestamp) is str else None
    except ValueError as error:
        raise ValueError("Stored successor DEV timestamp differs") from error
    if parsed is None or parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != timestamp:
        raise ValueError("Stored successor DEV timestamp differs")
    result, raw, freeze, captured = _compute_dev(reader_inputs=reader_inputs, public_inputs_path=public_inputs_path,
        expected_public_inputs_sha256=expected_public_inputs_sha256, dev_targets_path=dev_targets_path, fit_path=fit_path,
        train_freeze_path=train_freeze_path, expected_fit_sha256=expected_fit_sha256,
        expected_train_freeze_sha256=expected_train_freeze_sha256, source_pins=source_pins, scoring_inputs=scoring_inputs)
    freeze["selection_frozen_at"] = timestamp
    if raw != comparison_raw or _canonical(freeze) != freeze_raw:
        raise ValueError("Stored successor DEV replay differs")
    captured[comparison_path], captured[freeze_path] = comparison_raw, freeze_raw
    _unchanged(captured)
    return {"comparison_raw": comparison_raw, "freeze_raw": freeze_raw, "freeze": freeze, "comparison": result}
