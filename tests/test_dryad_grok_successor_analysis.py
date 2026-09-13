"""Successor analysis admission and frozen TRAIN boundary tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime as RealDatetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_successor_analysis.py"
COMPOSITE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_composite_admission_v5.py"
READER_TEST = ROOT / "tests/test_dryad_grok_successor_collection_replay.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def reader_canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load() -> Any:
    spec = importlib.util.spec_from_file_location("dryad_grok_successor_analysis_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_reader_fixture() -> Any:
    spec = importlib.util.spec_from_file_location("dryad_grok_successor_reader_fixture", READER_TEST)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identities(count: int = 2299) -> list[dict[str, str]]:
    return [{"request_id_hash": digest(f"request-{number}".encode()),
             "session_id_hash": digest(f"session-{number}".encode())} for number in range(count)]


def historical_identities() -> list[dict[str, str]]:
    return [{"request_id_hash": digest(f"historical-request-{number}".encode()),
             "session_id_hash": digest(f"historical-session-{number}".encode())} for number in range(33)]


def collection(subject: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, Any]]:
    train = [f"pass-train-{number:03d}" for number in range(70)]
    dev = [f"pass-dev-{number:03d}" for number in range(30)]
    ordinals = [*range(1, 1611), *range(4049, 4739)]
    rows = []
    for number, pass_id in enumerate(train + dev):
        start = number * 23 if number < 70 else 1610 + (number - 70) * 23
        rows.append({"pass_id": pass_id, "partition": "TRAIN" if number < 70 else "DEV",
                     "opaque_story_id": pass_id.removeprefix("pass-"), "ordinals": ordinals[start:start + 23],
                     "source": {"sha256": "a" * 64, "bytes": 1}, "score": 50.0, "coverage": .88,
                     "verdict_rows": [{"question_id": f"q-{item:03d}", "verdict": "YES"} for item in range(178)]})
    chain = [{"root": "C:/fixture/successor-a", "manifest_sha256": "b" * 64}]
    data = {"schema_version": 1, "evidence_class": "selected100_grok_successor_collection_replay_only_v1",
            "counts": subject.EXPECTED_COUNTS, "recovered_ordinals": [70], "coverage_failures": [],
            "full_study_admitted": False, "historical_prototype_only": True, "authority": False, "provider_calls_made": 0, "rows": rows,
            "native_identities": identities(), "historical_excluded_native_identities": historical_identities(),
            "successor_root_chain": chain, "root_chain_ordinal_owners": {88: {"kind": "first_recovery"}}}
    data["native_identity_commitment_sha256"] = digest(reader_canonical(data["native_identities"]))
    pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    pins.update({"analysis": digest(SOURCE.read_bytes()), "reader": "1" * 64,
                 "successor_controller": "2" * 64, "old_helper_closure": subject.OLD_HELPER_SHA256,
                 "composite": digest(COMPOSITE.read_bytes())})
    inputs = {"expected_plan_sha256": "3" * 64, "expected_predecessor_sha256": "4" * 64,
              "expected_old_epoch_sha256": "5" * 64, "expected_suffix_source_sha256": "6" * 64,
              "expected_recovery_controller_sha256": "f" * 64,
              "expected_recovery_manifest_sha256": "7" * 64}
    data["input_commitments"] = {"reader_sha256": pins["reader"],
        "successor_controller_sha256": pins["successor_controller"],
        "successor_root_chain_sha256": digest(reader_canonical(chain)), "plan_sha256": inputs["expected_plan_sha256"],
        "predecessor_sha256": inputs["expected_predecessor_sha256"],
        "old_suffix_epoch_sha256": inputs["expected_old_epoch_sha256"],
        "suffix_helper_sha256": inputs["expected_suffix_source_sha256"],
        "composite_helper_sha256": pins["composite"],
        "recovery_controller_sha256": inputs["expected_recovery_controller_sha256"],
        "recovery_manifest_sha256": inputs["expected_recovery_manifest_sha256"],
        "selected_schedule_sha256": "8" * 64, "selected_schedule_source_sha256": "9" * 64,
        "root_chain": [{"kind": "first_recovery", "replayed_ordinals": [88]},
                       {"kind": "successor", "root": chain[0]["root"],
                        "partial_completed_ordinals": [], "replayed_ordinals": []}]}
    selection = {"schedule": {"sha256": "8" * 64}, "source": {"sha256": "9" * 64},
                 "verified": {"selected_train_ids": train, "selected_dev_ids": dev,
                 "selected_request_ordinals": ordinals, "question_ids": [f"q-{item:03d}" for item in range(178)]}}
    data["normalized_verdict_rows"] = [{"pass_id": row["pass_id"], "opaque_story_id": row["opaque_story_id"], **item}
                                       for row in rows for item in row["verdict_rows"]]
    return data, selection, pins, inputs | {"successor_roots": chain}


def test_standing_v6_loader_routes_only_to_serialized_replacement() -> None:
    subject = load()
    replacement = "baseline_grok_runtime_data_successor.py"
    predecessor = "baseline_grok_standing_v6_partial_successor.py"
    assert subject.STANDING_V6_CONTROLLER_PATH.name == replacement
    assert predecessor not in SOURCE.read_text(encoding="utf-8")
    assert predecessor not in subject.READER_PATH.read_text(encoding="utf-8")


def test_capture_binds_the_partial_successor_controller_source() -> None:
    subject = load()
    pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    paths = {"analysis": SOURCE, "reader": subject.READER_PATH, "successor_controller": subject.CONTROLLER_PATH,
             "local_controller": subject.LOCAL_CONTROLLER_PATH, "standing_v6_controller": subject.STANDING_V6_CONTROLLER_PATH,
             "old_helper_closure": subject.OLD_HELPER_PATH, "composite": subject.COMPOSITE_PATH,
             "composite_analysis": subject.ANALYSIS_PATH, "selected_engine": subject.ENGINE_PATH,
             "runtime_data_scoring": subject.RUNTIME_DATA_SCORING_PATH}
    pins.update({key: digest(path.read_bytes()) for key, path in paths.items()})
    _captured, _reader, _controller, _old, _composite, _analysis, _engine, _local, standing = subject._capture(pins)
    assert Path(standing.__file__).resolve() == subject.STANDING_V6_CONTROLLER_PATH


def test_admission_binds_complete_successor_chain_and_preserves_local70() -> None:
    subject = load()
    data, selection, pins, inputs = collection(subject)
    admitted = subject._admit_collection(data, SimpleNamespace(_canonical=reader_canonical, _sha=digest), source_pins=pins,
        reader_inputs=inputs, selection=selection, predecessor={}, exclusions={
            "requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
            "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    assert admitted.record["evidence_class"] == "selected100_dryad_grok_successor_admission_v1"
    assert admitted.record["successor_root_chain"] == data["successor_root_chain"]
    assert admitted.record["selection"]["request_ordinals"].count(70) == 1
    assert len(admitted.endpoint_view["endpoint_grok_rows"]) == 100


def test_public_admission_rejects_historical_prototype_before_reader_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subject = load()
    _data, _selection, pins, inputs = collection(subject)
    inputs.update({"plan_root": tmp_path, "predecessor_path": tmp_path / "predecessor.json", "old_suffix_root": tmp_path,
                   "recovery_root": tmp_path, "expected_public_inputs_sha256": "a" * 64,
                   "approved_v4_routes": {}, "approved_v5_routes": {}, "local_continuation": None,
                   "candidate_native_continuation": None})
    monkeypatch.setattr(subject, "_capture", lambda _pins: pytest.fail("reader capture must remain closed"))
    with pytest.raises(ValueError, match="local continuation is required"):
        subject.admit_selected_successor(reader_inputs=inputs, source_pins=pins)


def test_public_admission_rejects_missing_candidate_before_reader_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subject = load()
    _data, _selection, pins, inputs = collection(subject)
    inputs.update({"plan_root": tmp_path, "predecessor_path": tmp_path / "predecessor.json", "old_suffix_root": tmp_path,
                   "recovery_root": tmp_path, "expected_public_inputs_sha256": "a" * 64,
                   "approved_v4_routes": {}, "approved_v5_routes": {},
                   "local_continuation": {"root": str(tmp_path / "local"), "manifest_sha256": "a" * 64, "controller_sha256": "b" * 64},
                   "candidate_native_continuation": None})
    monkeypatch.setattr(subject, "_capture", lambda _pins: pytest.fail("reader capture must remain closed"))
    with pytest.raises(ValueError, match="Standing v6 candidate continuation is required"):
        subject.admit_selected_successor(reader_inputs=inputs, source_pins=pins)


def test_public_admission_requires_explicit_runtime_data_before_reader_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subject = load()
    _data, _selection, pins, inputs = collection(subject)
    descriptor = {"root": str(tmp_path), "manifest_sha256": "a" * 64, "controller_sha256": "b" * 64}
    inputs.update({"plan_root": tmp_path, "predecessor_path": tmp_path / "predecessor.json", "old_suffix_root": tmp_path,
                   "recovery_root": tmp_path, "expected_public_inputs_sha256": "a" * 64,
                   "approved_v4_routes": {}, "approved_v5_routes": {}, "local_continuation": descriptor,
                   "candidate_native_continuation": descriptor})
    monkeypatch.setattr(subject, "_capture", lambda _pins: pytest.fail("reader capture must remain closed"))
    with pytest.raises(ValueError, match="Explicit runtime data configuration is required"):
        subject.admit_selected_successor(reader_inputs=inputs, source_pins=pins)


def test_runtime_data_proof_is_captured_and_protected_during_fit(tmp_path: Path) -> None:
    subject = load()
    _data, _selection, _pins, inputs = collection(subject)
    sources = {name: {"path": str(tmp_path / (name + ".py")), "sha256": digest(name.encode())}
               for name in ("context_adapter", "snapshot_manifest", "prefix_adapter", "runtime_data_snapshot_v4",
                            "runtime_data_snapshot_v5", "native_data_admission", "recovered_data_admission")}
    for name, item in sources.items():
        Path(item["path"]).write_bytes(name.encode())
    config = {name: sources[name] for name in ("context_adapter", "snapshot_manifest", "prefix_adapter")}
    config["source_bindings"] = {name: item for name, item in sources.items() if name not in config}
    schema = tmp_path / "historical-schema.json"
    schema.write_bytes(b"historical")
    protected = {"historical_schema": {"path": str(schema), "sha256": digest(schema.read_bytes())}}
    captured = {}
    subject._capture_runtime_data(captured, subject._runtime_data_descriptors(config))
    subject._capture_runtime_data(captured, protected)
    inputs.update({"plan_root": tmp_path / "plan", "predecessor_path": tmp_path / "predecessor.json",
                   "old_suffix_root": tmp_path / "old", "recovery_root": tmp_path / "recovery", "runtime_data": config})
    scoring = {"scoring_manifest_path": tmp_path / "scoring.json", "v5_runtime_manifest_path": tmp_path / "runtime.json",
               "v5_runtime_package_root": tmp_path / "package"}
    paths = subject._protected_inputs(inputs, scoring, runtime_data_paths=protected)
    assert {item["path"] for item in sources.values()} | {str(schema)} <= set(paths)
    math_spec = importlib.util.spec_from_file_location("runtime_data_preflight_math", subject.ANALYSIS_PATH)
    assert math_spec and math_spec.loader
    math = importlib.util.module_from_spec(math_spec)
    math_spec.loader.exec_module(math)
    with pytest.raises(ValueError, match="fresh external"):
        math._output_preflight(schema / "fit", *paths)
    schema.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source changed"):
        subject._unchanged(captured)


def test_admission_accepts_reader_partial_predecessor_peer_ownership() -> None:
    subject = load()
    data, selection, pins, inputs = collection(subject)
    data["root_chain_ordinal_owners"][202] = {
        "kind": "partial_predecessor_peer", "root": "C:/fixture/recovery", "manifest_sha256": "c" * 64,
        "controller_sha256": "d" * 64, "epoch_sha256": "e" * 64, "partial_202_sha256": "f" * 64,
        "terminal_sha256": "1" * 64, "replay_receipt": "partial_202"}
    data["input_commitments"]["root_chain"][1]["partial_completed_ordinals"] = [202]
    admitted = subject._admit_collection(data, SimpleNamespace(_canonical=reader_canonical, _sha=digest), source_pins=pins,
        reader_inputs=inputs, selection=selection, predecessor={}, exclusions={
            "requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
            "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    assert admitted.record["collection_record"]["root_chain_ordinal_owners"]["202"]["replay_receipt"] == "partial_202"


def test_admission_binds_local254_projection_without_native_identity(tmp_path: Path) -> None:
    subject = load()
    data, selection, pins, inputs = collection(subject)
    root = tmp_path / "continuation"; root.mkdir()
    descriptor = {"root": str(root), "manifest_sha256": "a" * 64, "controller_sha256": "b" * 64}
    pins.update({"local_controller": descriptor["controller_sha256"], "local_proposal": "c" * 64, "local_adoption": "d" * 64})
    protected = {"continuation_root": {"path": str(root), "inventory_sha256": "e" * 64},
                 "successor_root": {"path": str(tmp_path / "successor"), "inventory_sha256": "e" * 64}}
    for name in ("continuation_manifest", "controller", "successor_manifest", "partial", "proposal", "adoption",
                 "independent_review", "standing_authority", "local_projection", "protected_native_identities", "inner_epoch"):
        protected[name] = {"path": str(tmp_path / f"{name}.json"), "sha256": "e" * 64}
    identity = {"kind": "local_schema_projection", "ordinal": 254, "projection_sha256": "f" * 64, "identity_sha256": "1" * 64}
    provenance = {"proposal_sha256": pins["local_proposal"], "adoption_sha256": pins["local_adoption"]}
    data["schema_version"] = 2
    data["evidence_class"] = "selected100_grok_successor_local_schema_recovery_replay_only_v2"
    data["historical_prototype_only"] = False
    data["counts"] = subject.LOCAL_EXPECTED_COUNTS
    data["recovered_ordinals"] = [70, 254]
    data["native_identities"].pop()
    data["native_identity_commitment_sha256"] = digest(reader_canonical(data["native_identities"]))
    data["root_chain_ordinal_owners"][254] = {"kind": "local_schema_recovery", "root": str(root),
        "manifest_sha256": descriptor["manifest_sha256"], "controller_sha256": descriptor["controller_sha256"], "ordinal": 254,
        "local_identity": identity, "local_provenance": provenance, "replay_receipt": "local_projection"}
    data["local_continuation"] = descriptor
    data["local_recovery_identity"] = identity
    data["local_recovery_provenance"] = provenance
    data["local_recovery_protected_paths"] = protected
    data["local_continuation_commitment"] = {**descriptor, "local_identity": identity, "local_provenance": provenance,
        "partial_peer_ordinals": [], "untouched_replay_ordinals": [], "untouched_native_identity_commitment_sha256": "2" * 64,
        "protected_paths_sha256": digest(reader_canonical(protected))}
    data["input_commitments"].update({"local_continuation_manifest_sha256": descriptor["manifest_sha256"],
        "local_continuation_controller_sha256": descriptor["controller_sha256"],
        "local_continuation_descriptor_sha256": digest(reader_canonical(descriptor)),
        "local_recovery_identity_sha256": identity["identity_sha256"]})
    inputs["local_continuation"] = descriptor
    admitted = subject._admit_collection(data, SimpleNamespace(_canonical=reader_canonical, _sha=digest), source_pins=pins,
        reader_inputs=inputs, selection=selection, predecessor={}, exclusions={
            "requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
            "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    assert admitted.record["local_recovery"]["identity"] == identity
    assert len(admitted.record["collection_record"]["native_identities"]) == 2298
    assert 254 not in {item.get("ordinal") for item in admitted.record["collection_record"]["native_identities"]}


def test_reader_local_fixture_admits_partial_peers_and_local254(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subject, reader_test = load(), load_reader_fixture()
    reader, inputs, _calls = reader_test._local_fixture(monkeypatch, tmp_path)
    inputs["allow_legacy_local_v2_fixture"] = True
    local = reader._module(reader.LOCAL_CONTINUATION).verify_local_continuation()
    for name, descriptor in local["protected_paths"].items():
        key = "inventory_sha256" if name in {"continuation_root", "successor_root"} else "sha256"
        if any(character not in "0123456789abcdef" for character in descriptor[key]):
            descriptor[key] = digest(name.encode())
    data = reader.read_selected_successor_collection(**inputs)
    rows = data["rows"]
    selection = {"schedule": {"sha256": data["input_commitments"]["selected_schedule_sha256"]},
                 "source": {"sha256": data["input_commitments"]["selected_schedule_source_sha256"]},
                 "verified": {"selected_train_ids": [row["pass_id"] for row in rows[:70]],
                              "selected_dev_ids": [row["pass_id"] for row in rows[70:]],
                              "selected_request_ordinals": [ordinal for row in rows for ordinal in row["ordinals"]],
                              "question_ids": [item["question_id"] for item in rows[0]["verdict_rows"]]}}
    pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    pins.update({"analysis": digest(SOURCE.read_bytes()), "reader": data["input_commitments"]["reader_sha256"],
                 "successor_controller": data["input_commitments"]["successor_controller_sha256"],
                 "local_controller": inputs["local_continuation"]["controller_sha256"],
                 "local_proposal": data["local_recovery_provenance"]["proposal_sha256"],
                 "local_adoption": data["local_recovery_provenance"]["adoption_sha256"],
                 "old_helper_closure": subject.OLD_HELPER_SHA256, "composite": digest(COMPOSITE.read_bytes())})
    admitted = subject._admit_collection(data, reader, source_pins=pins, reader_inputs=inputs, selection=selection, predecessor={},
        exclusions={"requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
                    "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    owners = admitted.record["collection_record"]["root_chain_ordinal_owners"]
    assert all(owners[str(ordinal)]["kind"] == "partial_predecessor_peer" for ordinal in [252, 253, 255, 256, 257, 258, 259, 260, 261])
    assert owners["254"]["kind"] == "local_schema_recovery"


def test_reader_candidate_fixture_admits_full_standing_v6_ownership(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subject, reader_test = load(), load_reader_fixture()
    reader, inputs, _calls = reader_test._candidate_fixture(monkeypatch, tmp_path)
    local = reader._module(reader.LOCAL_CONTINUATION).verify_local_continuation()
    for name, descriptor in local["protected_paths"].items():
        key = "inventory_sha256" if name in {"continuation_root", "successor_root"} else "sha256"
        if any(character not in "0123456789abcdef" for character in descriptor[key]):
            descriptor[key] = digest(name.encode())
    data = reader.read_selected_successor_collection(**inputs)
    rows = data["rows"]
    selection = {"schedule": {"sha256": data["input_commitments"]["selected_schedule_sha256"]},
                 "source": {"sha256": data["input_commitments"]["selected_schedule_source_sha256"]},
                 "verified": {"selected_train_ids": [row["pass_id"] for row in rows[:70]],
                              "selected_dev_ids": [row["pass_id"] for row in rows[70:]],
                              "selected_request_ordinals": [ordinal for row in rows for ordinal in row["ordinals"]],
                              "question_ids": [item["question_id"] for item in rows[0]["verdict_rows"]]}}
    candidate = data["standing_v6_candidate_commitment"]
    pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    pins.update({"analysis": digest(SOURCE.read_bytes()), "reader": data["input_commitments"]["reader_sha256"],
                 "successor_controller": data["input_commitments"]["successor_controller_sha256"],
                 "local_controller": inputs["local_continuation"]["controller_sha256"],
                 "local_proposal": data["local_recovery_provenance"]["proposal_sha256"],
                 "local_adoption": data["local_recovery_provenance"]["adoption_sha256"],
                 "standing_v6_controller": inputs["candidate_native_continuation"]["controller_sha256"],
                 "standing_v6_candidate": candidate["candidate"]["manifest_sha256"],
                 "standing_v6_packet": candidate["packet"]["sha256"], "standing_v6_source": candidate["standing_source"]["sha256"],
                 "old_helper_closure": subject.OLD_HELPER_SHA256, "composite": digest(COMPOSITE.read_bytes())})
    admitted = subject._admit_collection(data, reader, source_pins=pins, reader_inputs=inputs, selection=selection, predecessor={},
        exclusions={"requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
                    "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    assert admitted.record["local_recovery"]["candidate"]["commitment"]["replay_ordinals"] == [*range(262, 1611), *range(4049, 4739)]


@pytest.mark.parametrize("fault", ["missing_chain", "coverage", "question_order", "native_count"])
def test_admission_rejects_incomplete_or_noncanonical_collection(fault: str) -> None:
    subject = load()
    data, selection, pins, inputs = collection(subject)
    if fault == "missing_chain":
        data["successor_root_chain"] = []
    elif fault == "coverage":
        data["rows"][0]["coverage"] = .879
    elif fault == "question_order":
        data["rows"][0]["verdict_rows"].reverse()
    else:
        data["native_identities"].pop()
        data["native_identity_commitment_sha256"] = digest(canonical(data["native_identities"]))
    with pytest.raises(ValueError):
        subject._admit_collection(data, SimpleNamespace(_canonical=reader_canonical, _sha=digest), source_pins=pins,
            reader_inputs=inputs, selection=selection, predecessor={}, exclusions={
                "requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
                "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})


def test_train_binding_requires_successor_evidence_and_root_chain() -> None:
    subject = load()
    data, selection, pins, inputs = collection(subject)
    admission = subject._admit_collection(data, SimpleNamespace(_canonical=reader_canonical, _sha=digest), source_pins=pins,
        reader_inputs=inputs, selection=selection, predecessor={}, exclusions={
            "requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
            "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    projection = {"projected_rows_sha256": {"TRAIN": "a" * 64, "DEV": "b" * 64}}
    binding = {"selection": "fixture"}
    fit = {"evidence_class": "selected100_amended_fit_unadmitted",
           "input_commitments": {"verdict_rows_sha256": "a" * 64, "target_rows_sha256": "d" * 64}}
    fit_raw = canonical(fit)
    freeze = subject._freeze("TRAIN", admission, source_pins=pins, scoring={"commitment_sha256": "e" * 64},
        engine_binding=binding, projection=projection,
        target_projection={"original_target_sha256": "c" * 64, "original_count": 176,
                           "selected_target_sha256": "d" * 64, "selected_count": 70}, inner_raw=fit_raw, inner=fit)
    subject._train_binding(fit_raw, canonical(freeze), admission=admission, source_pins=pins,
        scoring={"commitment_sha256": "e" * 64}, binding=binding, projection=projection,
        expected_train_target_sha256="c" * 64)
    del freeze["successor_root_chain"]
    with pytest.raises(ValueError, match="successor TRAIN freeze"):
        subject._train_binding(fit_raw, canonical(freeze), admission=admission, source_pins=pins,
            scoring={"commitment_sha256": "e" * 64}, binding=binding, projection=projection,
            expected_train_target_sha256="c" * 64)


def test_real_output_preflight_rejects_nested_successor_root(tmp_path: Path) -> None:
    subject = load()
    data, _selection, _pins, inputs = collection(subject)
    roots = [tmp_path / "earlier-successor", tmp_path / "later-successor"]
    for root in roots:
        root.mkdir()
    inputs["successor_roots"] = [{"root": str(root), "manifest_sha256": "a" * 64} for root in roots]
    inputs.update({"plan_root": tmp_path / "plan", "predecessor_path": tmp_path / "predecessor.json",
                   "old_suffix_root": tmp_path / "old-suffix", "recovery_root": tmp_path / "recovery"})
    scoring = {"scoring_manifest_path": tmp_path / "scoring.json", "v5_runtime_manifest_path": tmp_path / "runtime.json",
               "v5_runtime_package_root": tmp_path / "package"}
    module_spec = importlib.util.spec_from_file_location("successor_preflight_math", subject.ANALYSIS_PATH)
    assert module_spec and module_spec.loader
    math = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(math)
    protected = subject._protected_inputs(inputs, scoring)
    assert {str(root) for root in roots}.issubset(set(protected))
    with pytest.raises(ValueError, match="fresh external"):
        math._output_preflight(roots[0] / "analysis", *protected)
    assert data["successor_root_chain"]


def test_output_protection_includes_local_continuation_provenance_paths(tmp_path: Path) -> None:
    subject = load()
    _data, _selection, _pins, inputs = collection(subject)
    root = tmp_path / "continuation"; root.mkdir()
    inputs.update({"plan_root": tmp_path / "plan", "predecessor_path": tmp_path / "predecessor.json",
                   "old_suffix_root": tmp_path / "old-suffix", "recovery_root": tmp_path / "recovery",
                   "local_continuation": {"root": str(root), "manifest_sha256": "a" * 64, "controller_sha256": "b" * 64}})
    protected = {"continuation_root": {"path": str(root), "inventory_sha256": "a" * 64},
                 "successor_root": {"path": str(tmp_path / "successor"), "inventory_sha256": "a" * 64}}
    for name in ("continuation_manifest", "controller", "successor_manifest", "partial", "proposal", "adoption",
                 "independent_review", "standing_authority", "local_projection", "protected_native_identities", "inner_epoch"):
        path = tmp_path / f"{name}.json"; path.write_text("fixture", encoding="utf-8")
        protected[name] = {"path": str(path), "sha256": "c" * 64}
    scoring = {"scoring_manifest_path": tmp_path / "scoring.json", "v5_runtime_manifest_path": tmp_path / "runtime.json",
               "v5_runtime_package_root": tmp_path / "package"}
    module_spec = importlib.util.spec_from_file_location("local_preflight_math", subject.ANALYSIS_PATH)
    assert module_spec and module_spec.loader
    math = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(math)
    all_protected = subject._protected_inputs(inputs, scoring, {"protected_paths": protected})
    assert {item["path"] for item in protected.values()}.issubset(set(all_protected))
    with pytest.raises(ValueError, match="fresh external"):
        math._output_preflight(tmp_path / "proposal.json" / "analysis", *all_protected)


def test_candidate_descriptor_is_protected_after_admission_before_fit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject, reader_test = load(), load_reader_fixture()
    reader, inputs, _calls = reader_test._candidate_fixture(monkeypatch, tmp_path)
    local = reader._module(reader.LOCAL_CONTINUATION).verify_local_continuation()
    for name, descriptor in local["protected_paths"].items():
        key = "inventory_sha256" if name in {"continuation_root", "successor_root"} else "sha256"
        if any(character not in "0123456789abcdef" for character in descriptor[key]):
            descriptor[key] = digest(name.encode())
    data = reader.read_selected_successor_collection(**inputs)
    rows = data["rows"]
    selection = {"schedule": {"sha256": data["input_commitments"]["selected_schedule_sha256"]},
                 "source": {"sha256": data["input_commitments"]["selected_schedule_source_sha256"]},
                 "verified": {"selected_train_ids": [row["pass_id"] for row in rows[:70]],
                              "selected_dev_ids": [row["pass_id"] for row in rows[70:]],
                              "selected_request_ordinals": [ordinal for row in rows for ordinal in row["ordinals"]],
                              "question_ids": [item["question_id"] for item in rows[0]["verdict_rows"]]}}
    candidate = data["standing_v6_candidate_commitment"]
    pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    pins.update({"analysis": digest(SOURCE.read_bytes()), "reader": data["input_commitments"]["reader_sha256"],
                 "successor_controller": data["input_commitments"]["successor_controller_sha256"],
                 "local_controller": inputs["local_continuation"]["controller_sha256"],
                 "local_proposal": data["local_recovery_provenance"]["proposal_sha256"],
                 "local_adoption": data["local_recovery_provenance"]["adoption_sha256"],
                 "standing_v6_controller": inputs["candidate_native_continuation"]["controller_sha256"],
                 "standing_v6_candidate": candidate["candidate"]["manifest_sha256"],
                 "standing_v6_packet": candidate["packet"]["sha256"], "standing_v6_source": candidate["standing_source"]["sha256"],
                 "old_helper_closure": subject.OLD_HELPER_SHA256, "composite": digest(COMPOSITE.read_bytes())})
    admission = subject._admit_collection(data, reader, source_pins=pins, reader_inputs=inputs, selection=selection, predecessor={},
        exclusions={"requests": {item["request_id_hash"] for item in data["historical_excluded_native_identities"]},
                    "sessions": {item["session_id_hash"] for item in data["historical_excluded_native_identities"]}})
    scoring = {"scoring_manifest_path": tmp_path / "scoring.json", "v5_runtime_manifest_path": tmp_path / "runtime.json",
               "v5_runtime_package_root": tmp_path / "package"}
    protected = subject._protected_inputs(inputs, scoring, admission.record["local_recovery"])
    candidate_root = data["standing_v6_candidate_protected_paths"]["candidate"]["root"]
    partial_root = inputs["candidate_native_continuation"]["root"]
    peer_root = candidate["terminal_source_roots"]["262"]["root"]
    assert candidate_root in protected and partial_root in protected and peer_root in protected
    module_spec = importlib.util.spec_from_file_location("candidate_preflight_math", subject.ANALYSIS_PATH)
    assert module_spec and module_spec.loader
    math = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(math)
    with pytest.raises(ValueError, match="fresh external"):
        math._output_preflight(Path(partial_root) / "fit", *protected)


def test_train_dev_and_replay_preserve_admission_target_order_without_real_targets(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    public, train_target, dev_target = tmp_path / "public.json", tmp_path / "train.json", tmp_path / "dev.json"
    public.write_bytes(canonical({"fixture": True}))
    train_target.write_bytes(canonical([{"opaque_story_id": f"train-{number:03d}"} for number in range(70)]))
    dev_target.write_bytes(canonical([{"opaque_story_id": f"dev-{number:03d}"} for number in range(30)]))
    source_pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    source_pins.update({"analysis": digest(SOURCE.read_bytes()), "old_helper_closure": subject.OLD_HELPER_SHA256})
    reader_inputs = {"plan_root": tmp_path / "plan", "predecessor_path": tmp_path / "predecessor.json",
                     "old_suffix_root": tmp_path / "old-suffix", "recovery_root": tmp_path / "recovery",
                     "expected_public_inputs_sha256": digest(public.read_bytes()),
                     "successor_roots": [{"root": str(tmp_path / "successor"), "manifest_sha256": "a" * 64}]}
    scoring_inputs = {"scoring_manifest_path": public, "v5_runtime_manifest_path": public,
                      "v5_runtime_package_root": tmp_path, "expected_scoring_manifest_sha256": "a" * 64,
                      "expected_v5_runtime_manifest_sha256": "b" * 64,
                      "expected_v5_runtime_package_manifest_sha256": "c" * 64}
    calls: list[str] = []
    record = {"collection_sha256": "d" * 64, "successor_root_chain": reader_inputs["successor_roots"]}
    admission = subject.SelectedSuccessorAdmission(record=record, sha256=digest(canonical(record)))
    projection = {"projected_rows_sha256": {"TRAIN": "e" * 64, "DEV": "f" * 64}}
    binding = {"TRAIN": ["train"], "DEV": ["dev"]}
    train_rows, dev_rows = [{"opaque_story_id": "train", "verdicts": []}], [{"opaque_story_id": "dev", "verdicts": []}]

    def selected_targets(_pure: Any, path: Path, expected: str, partition: str, _ids: set[str], _public: bytes):
        calls.append("targets-" + partition)
        rows = json.loads(Path(path).read_bytes())
        return Path(path), Path(path).read_bytes(), rows, {"original_target_sha256": expected,
            "original_count": 176 if partition == "TRAIN" else 60, "selected_target_sha256": digest(canonical(rows)),
            "selected_count": len(rows)}

    def write(output: Path, artifacts: dict[str, bytes]) -> dict[str, str]:
        output.mkdir()
        for name, raw in artifacts.items():
            (output / name).write_bytes(raw)
        return {name: digest(raw) for name, raw in artifacts.items()}

    analysis = SimpleNamespace(_output_preflight=lambda output, *_protected: Path(output), _selected_targets=selected_targets,
                               _write=write, WORKFLOW_PATH=Path("workflow"))
    old = SimpleNamespace(_stage=lambda *_args, **_kwargs: ({"TRAIN": {"train"}, "DEV": {"dev"}},
        {"TRAIN": train_rows, "DEV": dev_rows}, projection, binding))
    pure = SimpleNamespace(TRAIN_TARGETS_SHA256="1" * 64, DEV_TARGETS_SHA256="2" * 64)

    def commitments(inner: dict[str, Any], rows: list[dict[str, Any]], targets: list[dict[str, Any]], target_sha: str) -> None:
        assert inner["input_commitments"] == {"verdict_rows_sha256": projection["projected_rows_sha256"]["TRAIN" if rows == train_rows else "DEV"],
                                                "target_rows_sha256": target_sha}
    pure._inner_commitments = commitments

    def fit(rows: list[dict[str, Any]], targets: list[dict[str, Any]], **_kwargs: Any) -> dict[str, Any]:
        calls.append("fit")
        return {"evidence_class": "selected100_amended_fit_unadmitted", "input_commitments": {
            "verdict_rows_sha256": projection["projected_rows_sha256"]["TRAIN"], "target_rows_sha256": digest(canonical(targets))}}

    def preflight(*_args: Any, **_kwargs: Any) -> None:
        calls.append("fit-preflight")

    def compare(rows: list[dict[str, Any]], targets: list[dict[str, Any]], _fit: bytes, **_kwargs: Any) -> dict[str, Any]:
        calls.append("compare")
        return {"evidence_class": "selected100_amended_dev_comparison_unadmitted", "input_commitments": {
            "verdict_rows_sha256": projection["projected_rows_sha256"]["DEV"], "target_rows_sha256": digest(canonical(targets))}}

    engine = SimpleNamespace(fit_train=fit, validate_frozen_fit=preflight, evaluate_dev=compare)
    monkeypatch.setattr(subject, "admit_selected_successor", lambda **_kwargs: (calls.append("admit") or admission))
    monkeypatch.setattr(subject, "_capture", lambda _pins: ({}, SimpleNamespace(), SimpleNamespace(), old,
        SimpleNamespace(), analysis, engine, SimpleNamespace(), SimpleNamespace()))
    monkeypatch.setattr(subject, "_runtime", lambda *_args, **_kwargs: {"commitment_sha256": "3" * 64})
    monkeypatch.setattr(subject, "_load", lambda _path, _raw, _label: pure if _label == "workflow" else analysis)
    monkeypatch.setattr(subject, "_read", lambda path, _expected, _label: (Path(path), Path(path).read_bytes())
                        if Path(path).exists() else (Path(path), b"fixture"))
    monkeypatch.setattr(subject, "datetime", SimpleNamespace(
        now=lambda _zone: RealDatetime(2026, 9, 10, tzinfo=timezone.utc), fromisoformat=RealDatetime.fromisoformat))
    train_output, dev_output = tmp_path / "train-output", tmp_path / "dev-output"
    fitted = subject.fit_selected_successor_train(reader_inputs=reader_inputs, public_inputs_path=public,
        expected_public_inputs_sha256=digest(public.read_bytes()), train_targets_path=train_target, output_root=train_output,
        source_pins=source_pins, scoring_inputs=scoring_inputs)
    fit_path, freeze_path = train_output / "selected100-grok-successor-fit-v1.json", train_output / "selected100-grok-successor-train-freeze-v1.json"
    compared = subject.compare_selected_successor_dev(reader_inputs=reader_inputs, public_inputs_path=public,
        expected_public_inputs_sha256=digest(public.read_bytes()), dev_targets_path=dev_target, fit_path=fit_path,
        train_freeze_path=freeze_path, output_root=dev_output, expected_fit_sha256=digest(fit_path.read_bytes()),
        expected_train_freeze_sha256=digest(freeze_path.read_bytes()), source_pins=source_pins, scoring_inputs=scoring_inputs)
    replay = subject.replay_selected_successor_dev(reader_inputs=reader_inputs, public_inputs_path=public,
        expected_public_inputs_sha256=digest(public.read_bytes()), dev_targets_path=dev_target, fit_path=fit_path,
        train_freeze_path=freeze_path, dev_comparison_path=dev_output / "selected100-grok-successor-dev-comparison-v1.json",
        dev_freeze_path=dev_output / "selected100-grok-successor-dev-freeze-v1.json", expected_fit_sha256=digest(fit_path.read_bytes()),
        expected_train_freeze_sha256=digest(freeze_path.read_bytes()),
        expected_dev_comparison_sha256=compared["artifacts"]["selected100-grok-successor-dev-comparison-v1.json"],
        expected_dev_freeze_sha256=compared["artifacts"]["selected100-grok-successor-dev-freeze-v1.json"],
        source_pins=source_pins, scoring_inputs=scoring_inputs)
    assert fitted["freeze"]["stage"] == "TRAIN"
    assert replay["freeze_raw"] == (dev_output / "selected100-grok-successor-dev-freeze-v1.json").read_bytes()
    assert calls == ["admit", "targets-TRAIN", "fit", "admit", "admit", "fit-preflight", "targets-DEV", "compare",
                     "admit", "fit-preflight", "targets-DEV", "compare"]
