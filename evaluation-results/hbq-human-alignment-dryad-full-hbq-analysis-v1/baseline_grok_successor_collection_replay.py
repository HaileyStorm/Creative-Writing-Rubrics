"""Read-only replay assembly for the complete selected Grok successor chain."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
COMPOSITE = ROOT / "baseline_composite_admission_v5.py"
SUFFIX = ROOT / "baseline_grok_v5_suffix.py"
RECOVERY = ROOT / "baseline_grok_selected_recovery.py"
SUCCESSOR = ROOT / "baseline_grok_selected_successor.py"
LOCAL_CONTINUATION = ROOT / "baseline_grok_selected_local_continuation.py"
STANDING_V6_CONTINUATION = ROOT / "baseline_grok_standing_v6_continuation.py"
COMPOSITE_SHA256 = "efd33ba0fcce7ae8c64a9aea280830998cb974c0250a411d657304a2fd0c50f6"
SUFFIX_SHA256 = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
RECOVERY_SHA256 = "687a60bcdd26227b3bcb6ae5081f3357bceb84b4b29312653617ef3d36887399"
SUCCESSOR_SHA256 = "fc0dbe04b3699522271157a87fc2f5a5659ffc108bd7eb3a68d6bf393e49bac8"
LOCAL_PROJECTION_SHA256 = "0ae9213b33a51315f082f9091fe40601f21efbdc32475d8010956d9cd8ee716b"
LOCAL_ADOPTION_SHA256 = "62eb162e148df15dd992e71952cd05a702c018163ec6759cb4ff508743ce1e8c"
QUESTION_COUNT, STORY_COUNT = 178, 100
LOGICAL_COUNT, NATIVE_COUNT, VERDICT_COUNT = 2300, 2299, 17800
RECOVERED_ORDINAL = 70
OLD_V5_ORDINALS = [*range(81, 88), *range(89, 92)]
SUCCESSOR_SCHEDULE = [88, *range(92, 1611), *range(4049, 4739)]
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _digest(value: Any, label: str) -> str:
    _need(isinstance(value, str) and _HASH.fullmatch(value) is not None, f"{label} must be a lowercase SHA-256")
    return value


def _read(path: Path | str, expected: str, label: str) -> bytes:
    checked = Path(path).resolve()
    _need(checked.is_file(), f"{label} is missing")
    raw = checked.read_bytes()
    _need(_sha(raw) == _digest(expected, label + " hash") and checked.read_bytes() == raw, f"{label} drifted")
    return raw


def _json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error


def _module(path: Path, expected: str, label: str) -> ModuleType:
    raw = _read(path, expected, label)
    spec = importlib.util.spec_from_file_location("_dryad_successor_collection_" + label.replace(" ", "_"), path)
    _need(spec is not None and spec.loader is not None, f"{label} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _need(path.read_bytes() == raw, f"{label} changed while loading")
    return module


def _identity(value: Any, label: str) -> dict[str, str]:
    fields = {"request_id_hash", "session_id_hash"}
    _need(isinstance(value, Mapping) and set(value) in (fields, fields | {"observed_turns"}), f"{label} identity differs")
    result = {key: value[key] for key in fields}
    _need(all(isinstance(item, str) and _HASH.fullmatch(item) for item in result.values()), f"{label} identity differs")
    if "observed_turns" in value:
        _need(type(value["observed_turns"]) is int and value["observed_turns"] >= 1, f"{label} identity differs")
    return result


def _unique(identities: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = [_identity(item, "collection") for item in identities]
    request_ids = [item["request_id_hash"] for item in result]
    session_ids = [item["session_id_hash"] for item in result]
    _need(len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "collection native identity duplicate")
    return result


def _verdicts(value: Any, question_ids: Sequence[str], label: str) -> list[dict[str, Any]]:
    _need(isinstance(value, list) and len(value) == QUESTION_COUNT, f"{label} verdict count differs")
    rows = [dict(item) for item in value if isinstance(item, Mapping)]
    _need(len(rows) == QUESTION_COUNT and [item.get("question_id") for item in rows] == list(question_ids), f"{label} criterion order differs")
    normalized = [{"question_id": item["question_id"], "verdict": item.get("verdict")} for item in rows]
    _need(all(isinstance(item["verdict"], str) for item in normalized), f"{label} verdict differs")
    return normalized


def _score(runtime: Any, *, verdicts: Sequence[Mapping[str, Any]], artifact_id: str) -> tuple[float | int, float | int]:
    result = runtime.core.score_bundle(runtime.modules, runtime.bundle, list(verdicts), artifact_id=artifact_id, task_contract=None)
    final = result.get("final_score") if isinstance(result, Mapping) else None
    observed = final.get("observed") if isinstance(final, Mapping) else None
    coverage = result.get("coverage") if isinstance(result, Mapping) else None
    _need(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100
          and type(coverage) in (int, float) and math.isfinite(coverage) and 0 <= coverage <= 1, "canonical collection score differs")
    return observed, coverage


def _source_commitment(record: Mapping[str, Any]) -> dict[str, Any]:
    result = {"sha256": record.get("source_sha256"), "bytes": record.get("source_bytes")}
    _need(isinstance(result["sha256"], str) and _HASH.fullmatch(result["sha256"])
          and type(result["bytes"]) is int and result["bytes"] >= 0, "story source commitment differs")
    return result


def _record(*, record: Mapping[str, Any], ordinals: Sequence[int], verdicts: Sequence[Mapping[str, Any]], runtime: Any,
            provenance: Mapping[str, Any], replay_input_commitments: Mapping[str, Any]) -> dict[str, Any]:
    artifact_id = record.get("opaque_story_id")
    _need(isinstance(artifact_id, str) and artifact_id and isinstance(provenance, Mapping)
          and isinstance(replay_input_commitments, Mapping), "story replay record differs")
    score, coverage = _score(runtime, verdicts=verdicts, artifact_id=artifact_id)
    normalized = list(verdicts)
    return {"pass_id": record["pass_id"], "partition": record["partition"], "opaque_story_id": artifact_id,
            "source": _source_commitment(record), "ordinals": list(ordinals), "provenance": dict(provenance),
            "replay_input_commitments": dict(replay_input_commitments), "verdict_rows": normalized,
            "verdicts_sha256": _sha(_canonical(normalized)), "score": score, "coverage": coverage}


def _descriptor(value: Any) -> tuple[Path, str]:
    _need(isinstance(value, Mapping) and set(value) == {"root", "manifest_sha256"} and isinstance(value.get("root"), str),
          "successor root descriptor differs")
    root = Path(value["root"]).resolve()
    _need(root.is_dir() and not root.is_symlink(), "successor root differs")
    return root, _digest(value["manifest_sha256"], "successor manifest")


def _local_descriptor(value: Any) -> tuple[Path, str, str]:
    _need(isinstance(value, Mapping) and set(value) == {"root", "manifest_sha256", "controller_sha256"}
          and isinstance(value.get("root"), str), "local continuation descriptor differs")
    root = Path(value["root"]).resolve()
    _need(root.is_dir() and not root.is_symlink(), "local continuation root differs")
    return root, _digest(value["manifest_sha256"], "local continuation manifest"), _digest(value["controller_sha256"], "local continuation controller")


def _terminal_commitment(parent: Any, owner: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    raw = parent._attempt_path(Path(owner["root"]), ordinal, "terminal.json").read_bytes()
    digest = _sha(raw)
    _need(owner.get("terminal_sha256") in (None, digest), "partial peer terminal changed")
    return {"ordinal": ordinal, "terminal_sha256": digest, "owner": dict(owner)}


def _local_continuation(*, descriptor: Mapping[str, Any], approved_v5_routes: Mapping[str, Any],
                        successor_root: Path, successor_manifest_sha256: str, include_untouched: bool) -> tuple[dict[str, Any], dict[int, dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    root, manifest_sha256, controller_sha256 = _local_descriptor(descriptor)
    controller = _module(LOCAL_CONTINUATION, controller_sha256, "local continuation controller")
    local = controller.verify_local_continuation(continuation_root=root, expected_manifest_sha256=manifest_sha256,
                                                 expected_controller_sha256=controller_sha256)
    native = controller.verify_untouched_replay_chain(continuation_root=root, expected_manifest_sha256=manifest_sha256,
                                                       expected_controller_sha256=controller_sha256, approved_v5_routes=approved_v5_routes) if include_untouched else None
    local_required = {"ordinal", "evidence_class", "verdicts", "local_identity", "local_provenance", "ownership", "source",
                      "protected_paths", "partial_peer_records", "partial_peer_source", "provider_calls_made", "full_original_study_admitted",
                      "review_decision", "standing_authority_kind"}
    native_required = {"untouched_replay_ordinals", "untouched_native_identities", "untouched_terminals", "provider_calls_made",
                       "protected_native_identity_count"}
    _need(isinstance(local, Mapping) and set(local) == local_required and local.get("ordinal") == 254
          and local.get("evidence_class") == "owner_adopted_local_session_schema_recovery" and local.get("provider_calls_made") == 0
          and local.get("full_original_study_admitted") is False and isinstance(local.get("source"), Mapping)
          and local["source"] == {"root": str(root), "manifest_sha256": manifest_sha256, "controller_sha256": controller_sha256,
                                  "successor_root": str(successor_root), "successor_manifest_sha256": successor_manifest_sha256,
                                  "partial_sha256": "889429a738d3b7724abc7652518d5fab46041b5db4db1c4fb3ae9db85752a1e2",
                                  "inner_epoch_sha256": local["source"].get("inner_epoch_sha256")}, "local continuation source binding differs")
    local_identity = local.get("local_identity")
    _need(isinstance(local_identity, Mapping) and set(local_identity) == {"kind", "ordinal", "projection_sha256", "identity_sha256"}
          and local_identity.get("kind") == "local_schema_projection" and local_identity.get("ordinal") == 254
          and local_identity.get("projection_sha256") == LOCAL_PROJECTION_SHA256
          and isinstance(local_identity.get("identity_sha256"), str) and _HASH.fullmatch(local_identity["identity_sha256"]),
          "local continuation identity differs")
    provenance = local.get("local_provenance")
    _need(isinstance(provenance, Mapping) and provenance.get("adoption_sha256") == LOCAL_ADOPTION_SHA256
          and provenance.get("ordinary_native_admission") is False and provenance.get("new_provider_attempts_authorized") == 0,
          "local continuation provenance differs")
    protected_paths = local.get("protected_paths")
    protected_path_keys = {"continuation_root", "continuation_manifest", "controller", "successor_root", "successor_manifest", "partial",
                           "proposal", "adoption", "independent_review", "standing_authority", "local_projection",
                           "protected_native_identities", "inner_epoch"}
    _need(isinstance(protected_paths, Mapping) and set(protected_paths) == protected_path_keys
          and protected_paths.get("controller") == {"path": str(LOCAL_CONTINUATION.resolve()), "sha256": controller_sha256}
          and protected_paths.get("continuation_manifest") == {"path": str(root / "local-continuation-manifest.json"), "sha256": manifest_sha256},
          "local continuation protected paths differ")
    peer_source = local.get("partial_peer_source")
    expected_peer_ordinals = [252, 253, 255, 256, 257, 258, 259, 260, 261]
    _need(isinstance(peer_source, Mapping) and peer_source == {"root": str(successor_root),
          "successor_manifest_sha256": successor_manifest_sha256, "inner_epoch_sha256": local["source"]["inner_epoch_sha256"],
          "partial": {"path": peer_source.get("partial", {}).get("path") if isinstance(peer_source.get("partial"), Mapping) else None,
                      "sha256": "889429a738d3b7724abc7652518d5fab46041b5db4db1c4fb3ae9db85752a1e2"}},
          "local continuation partial source binding differs")
    peer_records = local.get("partial_peer_records")
    _need(isinstance(peer_records, list) and [item.get("ordinal") for item in peer_records if isinstance(item, Mapping)] == expected_peer_ordinals,
          "local continuation partial peer ordinals differ")
    peer_identities: list[dict[str, str]] = []
    for record in peer_records:
        _need(isinstance(record, Mapping) and set(record) == {"ordinal", "criterion_verdict_count", "native_identity", "terminal_sha256", "controller_authorization_sha256"}
              and record.get("ordinal") in expected_peer_ordinals and type(record.get("criterion_verdict_count")) is int
              and all(isinstance(record.get(key), str) and _HASH.fullmatch(record[key]) for key in ("terminal_sha256", "controller_authorization_sha256")),
              "local continuation partial peer differs")
        peer_identities.append(_identity(record["native_identity"], "local continuation partial peer"))
    peer_identities = _unique(peer_identities)
    ordinals: list[int] = []; identities: list[dict[str, str]] = []; terminals: list[Mapping[str, Any]] = []
    if include_untouched:
        _need(isinstance(native, Mapping) and set(native) == native_required and native.get("provider_calls_made") == 0
              and native.get("protected_native_identity_count") == 259, "local continuation native replay differs")
        ordinals, identities, terminals = native["untouched_replay_ordinals"], _unique(native["untouched_native_identities"]), native["untouched_terminals"]
        expected = [*range(262, 1611), *range(4049, 4739)]
        _need(ordinals == expected and len(identities) == len(expected) and isinstance(terminals, list) and len(terminals) == len(expected),
              "local continuation untouched schedule differs")
    terminal_by_ordinal: dict[int, dict[str, Any]] = {}
    for ordinal, terminal in zip(ordinals, terminals, strict=True):
        _need(isinstance(terminal, Mapping) and set(terminal) == {"ordinal", "terminal_sha256", "controller_authorization_sha256"}
              and terminal.get("ordinal") == ordinal and all(isinstance(terminal[key], str) and _HASH.fullmatch(terminal[key])
              for key in ("terminal_sha256", "controller_authorization_sha256")), "local continuation terminal differs")
        terminal_by_ordinal[ordinal] = dict(terminal)
    local_owner = {"kind": "local_schema_recovery", "root": str(root), "manifest_sha256": manifest_sha256,
                   "controller_sha256": controller_sha256, "ordinal": 254, "local_identity": dict(local_identity),
                   "local_provenance": dict(local["local_provenance"]), "replay_receipt": "local_projection"}
    owners = {record["ordinal"]: {"kind": "partial_predecessor_peer", "root": str(successor_root),
                                   "manifest_sha256": successor_manifest_sha256, "controller_sha256": SUCCESSOR_SHA256,
                                   "epoch_sha256": peer_source["inner_epoch_sha256"], "partial_202_sha256": peer_source["partial"]["sha256"],
                                   "terminal_sha256": record["terminal_sha256"], "controller_authorization_sha256": record["controller_authorization_sha256"],
                                   "replay_receipt": "retained_partial_202"} for record in peer_records}
    owners[254] = local_owner
    for ordinal, terminal in terminal_by_ordinal.items():
        owners[ordinal] = {"kind": "local_continuation_native", "root": str(root), "manifest_sha256": manifest_sha256,
                           "controller_sha256": controller_sha256, "epoch_sha256": local["source"]["inner_epoch_sha256"],
                           "terminal_sha256": terminal["terminal_sha256"], "controller_authorization_sha256": terminal["controller_authorization_sha256"],
                           "replay_receipt": "local_continuation"}
    commitment = {"root": str(root), "manifest_sha256": manifest_sha256, "controller_sha256": controller_sha256,
                  "local_identity": dict(local_identity), "local_provenance": dict(local["local_provenance"]),
                  "protected_paths": dict(protected_paths), "protected_paths_sha256": _sha(_canonical(dict(protected_paths))),
                  "partial_peer_ordinals": expected_peer_ordinals,
                  "untouched_replay_ordinals": list(ordinals), "untouched_native_identity_commitment_sha256": _sha(_canonical(identities))}
    return dict(local), owners, _unique([*peer_identities, *identities]), commitment


def _candidate_native_continuation(*, descriptor: Mapping[str, Any], local_descriptor: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, str]], dict[int, list[dict[str, Any]]], dict[str, Any]]:
    root, manifest_sha256, controller_sha256 = _local_descriptor(descriptor)
    controller = _module(STANDING_V6_CONTINUATION, controller_sha256, "standing v6 continuation controller")
    verified = controller.verify_standing_v6_continuation(continuation_root=root, expected_manifest_sha256=manifest_sha256,
                                                          expected_controller_sha256=controller_sha256)
    replay = controller.verify_standing_v6_replay_chain(continuation_root=root, expected_manifest_sha256=manifest_sha256,
                                                         expected_controller_sha256=controller_sha256)
    expected = [*range(262, 1611), *range(4049, 4739)]
    _need(isinstance(verified, Mapping) and verified.get("pending_ordinals") == expected and verified.get("provider_calls_made") == 0
          and verified.get("prefix", {}).get("source", {}).get("root") == local_descriptor["root"]
          and isinstance(verified.get("protected_paths"), Mapping), "standing v6 continuation binding differs")
    required = {"candidate_native_replay_ordinals", "candidate_native_identities", "candidate_native_terminals", "candidate_native_verdicts",
                "candidate", "packet", "standing_source", "queue", "provider_calls_made"}
    _need(isinstance(replay, Mapping) and set(replay) == required and replay.get("candidate_native_replay_ordinals") == expected
          and replay.get("provider_calls_made") == 0, "standing v6 candidate replay differs")
    identities = _unique(replay["candidate_native_identities"])
    terminals = replay["candidate_native_terminals"]
    verdict_batches = replay["candidate_native_verdicts"]
    _need(len(identities) == len(expected) and isinstance(terminals, list) and len(terminals) == len(expected)
          and isinstance(verdict_batches, Mapping) and {int(key) for key in verdict_batches} == set(expected), "standing v6 candidate cardinality differs")
    owners: dict[int, dict[str, Any]] = {}
    batches: dict[int, list[dict[str, Any]]] = {}
    for ordinal, terminal, identity in zip(expected, terminals, identities, strict=True):
        _need(isinstance(terminal, Mapping) and terminal.get("ordinal") == ordinal and terminal.get("native_identity") == identity and isinstance(terminal.get("terminal_sha256"), str)
              and _HASH.fullmatch(terminal["terminal_sha256"]) is not None, "standing v6 candidate terminal differs")
        batch = verdict_batches.get(ordinal, verdict_batches.get(str(ordinal)))
        _need(isinstance(batch, Mapping) and batch.get("terminal_sha256") == terminal["terminal_sha256"]
              and isinstance(batch.get("question_ids"), list) and isinstance(batch.get("verdicts"), list)
              and [item.get("question_id") for item in batch["verdicts"] if isinstance(item, Mapping)] == batch["question_ids"],
              "standing v6 candidate verdict binding differs")
        batches[ordinal] = [dict(item) for item in batch["verdicts"]]
        owners[ordinal] = {"kind": "standing_v6_candidate_native", "root": str(root), "manifest_sha256": manifest_sha256,
                           "controller_sha256": controller_sha256, "terminal_sha256": terminal["terminal_sha256"],
                           "native_identity": dict(identity),
                           "candidate": dict(replay["candidate"]), "packet": dict(replay["packet"]),
                           "standing_source": dict(replay["standing_source"]), "replay_receipt": "standing_v6_candidate"}
    commitment = {"root": str(root), "manifest_sha256": manifest_sha256, "controller_sha256": controller_sha256,
                  "candidate": dict(replay["candidate"]), "packet": dict(replay["packet"]), "standing_source": dict(replay["standing_source"]),
                  "protected_paths": dict(verified["protected_paths"]), "queue": dict(replay["queue"]),
                  "replay_ordinals": expected, "native_identity_commitment_sha256": _sha(_canonical(identities))}
    return owners, identities, batches, commitment


def _historical_exclusions(predecessor: Mapping[str, Any]) -> list[dict[str, str]]:
    descriptor = predecessor.get("identity_exclusion")
    _need(isinstance(descriptor, Mapping) and set(descriptor) >= {"path", "sha256"}, "historical identity exclusion differs")
    value = _json(_read(descriptor["path"], descriptor["sha256"], "Historical identity exclusion"), "Historical identity exclusion")
    records = value.get("records") if isinstance(value, Mapping) else None
    _need(isinstance(records, list) and len(records) == 33, "historical identity exclusion differs")
    return _unique(records)


def _recovery_chain(*, root: Path, recovery: Any, expected_controller_sha256: str, expected_manifest_sha256: str) -> tuple[Any, dict[str, Any], Path, dict[int, Any], set[int], list[dict[str, str]], dict[int, dict[str, Any]], dict[str, Any]]:
    manifest_raw = _read(root / "recovery-manifest.json", expected_manifest_sha256, "Recovery manifest")
    manifest = _json(manifest_raw, "Recovery manifest")
    _need(isinstance(manifest, Mapping) and manifest.get("controller_sha256") == expected_controller_sha256
          and _sha(RECOVERY.read_bytes()) == expected_controller_sha256, "recovery controller binding differs")
    parent = recovery._load_parent(manifest["parent_source"]["sha256"])
    epoch, epoch_raw, plan_root, requests = recovery._inner(parent, root, manifest["inner_epoch"]["sha256"])
    recovery._source_guard(parent, manifest, epoch_raw)
    replayed, identities = recovery._validated_replay_chain(root, parent, manifest, manifest_raw, epoch)
    _need(set(replayed) <= set(manifest["pending_ordinals"]), "recovery replay outside pending schedule")
    protected = recovery._identity_file(Path(manifest["protected_native_identities"]["path"]), manifest["protected_native_identities"]["sha256"])
    _unique([*protected, *identities])
    owner_base = {"kind": "first_recovery", "root": str(root), "manifest_sha256": _sha(manifest_raw),
                  "controller_sha256": expected_controller_sha256, "epoch_sha256": manifest["inner_epoch"]["sha256"]}
    owners = {ordinal: {**owner_base, "replay_receipt": "recovery"} for ordinal in replayed}
    commitment = {"kind": "first_recovery", "root": str(root), "manifest_sha256": _sha(manifest_raw),
                  "controller_sha256": expected_controller_sha256, "parent_sha256": manifest["parent_source"]["sha256"],
                  "inner_epoch_sha256": manifest["inner_epoch"]["sha256"], "source_epoch_sha256": manifest["source_epoch"]["sha256"],
                  "source_inventory_sha256": manifest["source_epoch_inventory"]["sha256"], "partial_replay_sha256": manifest["partial_replay"]["sha256"],
                  "protected_native_identities_sha256": manifest["protected_native_identities"]["sha256"], "replayed_ordinals": sorted(replayed)}
    return parent, dict(epoch), plan_root, requests, set(replayed), _unique(identities), owners, commitment


def _partial_peer_owners(*, controller: Any, source_root: Path, manifest: Mapping[str, Any], partial: Mapping[str, Any],
                         requests: Mapping[int, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, str]]]:
    """Bind a partial-wave success to the root that actually contains its terminal."""
    controller._verify_partial_source(source_root, partial, manifest["prior_manifest_sha256"], manifest["prior_controller_sha256"], requests)
    records = {item.get("ordinal"): item for item in partial["records"] if isinstance(item, Mapping)}
    completed = partial["completed_ordinals"]
    _need(set(records) == set(completed) and all(type(ordinal) is int for ordinal in completed), "partial peer records differ")
    protected = _unique(partial["all_protected_native_identities"])
    identities = _unique(partial["native_identities"])
    _need(all(identity in protected for identity in identities), "partial protected identity differs")
    owners: dict[int, dict[str, Any]] = {}
    for ordinal, identity in zip(completed, identities, strict=True):
        record = records[ordinal]
        _need(ordinal in SUCCESSOR_SCHEDULE and _identity(record.get("native_identity"), "partial peer") == identity,
              "partial peer identity differs")
        owners[ordinal] = {"kind": "partial_predecessor_peer", "root": str(source_root),
                           "manifest_sha256": manifest["prior_manifest_sha256"], "controller_sha256": manifest["prior_controller_sha256"],
                           "epoch_sha256": manifest["inner_epoch"]["sha256"], "partial_202_sha256": manifest["partial_202"]["sha256"],
                           "terminal_sha256": record["terminal_sha256"], "replay_receipt": "partial_202"}
    return owners, identities


def _successor_chain(*, roots: Sequence[Mapping[str, Any]], controller: Any, parent: Any, recovery_root: Path,
                     recovery_epoch: Mapping[str, Any], recovery_plan_root: Path) -> tuple[dict[int, dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    owners: dict[int, dict[str, Any]] = {}
    identities: list[dict[str, str]] = []
    commitments: list[dict[str, Any]] = []
    previous_root = recovery_root
    for descriptor in roots:
        root, expected_manifest = _descriptor(descriptor)
        manifest, manifest_raw = controller._manifest(root)
        _need(_sha(manifest_raw) == expected_manifest and Path(manifest["prior_root"]).resolve() == previous_root,
              "successor lineage differs")
        partial = controller._partial(Path(manifest["partial_202"]["path"]), manifest["partial_202"]["sha256"])
        prior = _module(controller.PRIOR, controller.PRIOR_SHA, "prior controller") if manifest["prior_controller_sha256"] == controller.PRIOR_SHA else None
        epoch, _epoch_raw, plan_root, requests = controller._source_guard(parent, prior, manifest, partial)
        _need(epoch == recovery_epoch and plan_root == recovery_plan_root, "successor epoch or plan differs")
        partial_owners, partial_identities = _partial_peer_owners(
            controller=controller, source_root=previous_root, manifest=manifest, partial=partial, requests=requests)
        replayed, replay_identities = controller._validated_replays(root, parent, manifest, manifest_raw)
        _need(set(replayed) <= set(manifest["pending_ordinals"])
              and set(manifest["predecessor_root_ownership"]["successor_replacements"]).issubset(replayed),
              "successor replacement replay missing")
        owner_base = {"kind": "successor", "root": str(root), "manifest_sha256": expected_manifest,
                      "controller_sha256": manifest["controller_sha256"], "epoch_sha256": manifest["inner_epoch"]["sha256"]}
        for ordinal in replayed:
            _need(ordinal not in owners, "successor ordinal ownership collision")
            owners[ordinal] = {**owner_base, "replay_receipt": "successor"}
        for ordinal, owner in partial_owners.items():
            _need(ordinal not in owners, "successor partial ordinal ownership collision")
            owners[ordinal] = owner
        identities.extend([*partial_identities, *replay_identities])
        commitments.append({"kind": "successor", "root": str(root), "manifest_sha256": expected_manifest,
                            "controller_sha256": manifest["controller_sha256"], "prior_root": str(previous_root),
                            "prior_manifest_sha256": manifest["prior_manifest_sha256"], "parent_sha256": manifest["parent_sha256"],
                            "prior_inventory_sha256": manifest["prior_inventory"]["sha256"], "inner_epoch_sha256": manifest["inner_epoch"]["sha256"],
                            "partial_202_sha256": manifest["partial_202"]["sha256"],
                            "protected_native_identities_sha256": manifest["protected_native_identities"]["sha256"],
                            "partial_completed_ordinals": list(partial["completed_ordinals"]),
                            "partial_native_identity_commitment_sha256": _sha(_canonical(partial_identities)),
                            "replayed_ordinals": sorted(replayed)})
        previous_root = root
    _need(previous_root != recovery_root, "successor root chain is empty")
    return owners, _unique(identities), commitments


def _owner(owners: Mapping[int, Mapping[str, Any]], ordinal: int) -> dict[str, Any]:
    value = owners.get(ordinal)
    _need(isinstance(value, Mapping), "selected ordinal owner is missing")
    return dict(value)


def read_selected_successor_collection(
    *, plan_root: Path | str, predecessor_path: Path | str, old_suffix_root: Path | str, recovery_root: Path | str,
    expected_plan_sha256: str, expected_predecessor_sha256: str, expected_old_epoch_sha256: str,
    expected_suffix_source_sha256: str, expected_recovery_controller_sha256: str,
    expected_recovery_manifest_sha256: str, approved_v4_routes: Mapping[str, Any], approved_v5_routes: Mapping[str, Any],
    successor_roots: Sequence[Mapping[str, Any]], local_continuation: Mapping[str, Any] | None = None,
    candidate_native_continuation: Mapping[str, Any] | None = None, allow_legacy_local_v2_fixture: bool = False,
) -> dict[str, Any]:
    """Reconstruct all selected stories from validated historic and successor terminals without dispatch."""
    reader_raw = Path(__file__).read_bytes()
    _need(expected_suffix_source_sha256 == SUFFIX_SHA256 and expected_recovery_controller_sha256 == RECOVERY_SHA256,
          "frozen collection helper binding differs")
    composite = _module(COMPOSITE, COMPOSITE_SHA256, "composite helper")
    suffix = _module(SUFFIX, expected_suffix_source_sha256, "suffix helper")
    recovery = _module(RECOVERY, expected_recovery_controller_sha256, "recovery controller")
    controller = _module(SUCCESSOR, SUCCESSOR_SHA256, "successor controller")
    plan_root, old_root, recovery_root = Path(plan_root).resolve(), Path(old_suffix_root).resolve(), Path(recovery_root).resolve()
    _need(plan_root.is_dir() and old_root.is_dir() and recovery_root.is_dir() and successor_roots, "collection root differs")
    _predecessor_raw, predecessor = composite._predecessor(predecessor_path, expected_predecessor_sha256)
    context = composite._actual_replay_context(suffix_root=old_root, plan_root=plan_root, expected_epoch_sha256=expected_old_epoch_sha256,
                                                expected_suffix_source_sha256=expected_suffix_source_sha256, predecessor=predecessor)
    historical_exclusions = _historical_exclusions(predecessor)
    parent, recovery_epoch, recovery_plan_root, requests_by_ordinal, _recovery_replayed, recovery_identities, recovery_owners, recovery_commitment = _recovery_chain(
        root=recovery_root, recovery=recovery, expected_controller_sha256=expected_recovery_controller_sha256,
        expected_manifest_sha256=expected_recovery_manifest_sha256)
    _need(parent.__file__ == suffix.__file__ and recovery_plan_root == plan_root, "recovery suffix or plan differs")
    successor_owners, successor_identities, successor_commitments = _successor_chain(
        roots=successor_roots, controller=controller, parent=suffix, recovery_root=recovery_root,
        recovery_epoch=recovery_epoch, recovery_plan_root=recovery_plan_root)
    local, local_owners, local_identities, local_commitment = (None, {}, [], None)
    if local_continuation is not None:
        _need(candidate_native_continuation is not None or allow_legacy_local_v2_fixture is True,
              "standing v6 candidate continuation is required")
        last_root, last_manifest_sha256 = _descriptor(successor_roots[-1])
        local, local_owners, local_identities, local_commitment = _local_continuation(
            descriptor=local_continuation, approved_v5_routes=approved_v5_routes, successor_root=last_root,
            successor_manifest_sha256=last_manifest_sha256, include_untouched=candidate_native_continuation is None)
    candidate_owners, candidate_identities, candidate_batches, candidate_commitment = ({}, [], {}, None)
    if candidate_native_continuation is not None:
        _need(local_continuation is not None, "standing v6 continuation requires local prefix")
        candidate_owners, candidate_identities, candidate_batches, candidate_commitment = _candidate_native_continuation(
            descriptor=candidate_native_continuation, local_descriptor=local_continuation)
    owners = {**recovery_owners}
    _need(not (set(owners) & set(successor_owners)), "root-chain ordinal ownership collision")
    owners.update(successor_owners)
    _need(not (set(owners) & set(local_owners)), "local continuation ordinal ownership collision")
    owners.update(local_owners)
    _need(not (set(owners) & set(candidate_owners)), "standing v6 continuation ordinal ownership collision")
    owners.update(candidate_owners)
    _need(set(owners) == set(SUCCESSOR_SCHEDULE), "successor chain is incomplete")
    receipt_identities = _unique([*recovery_identities, *successor_identities, *local_identities, *candidate_identities])
    expected_replayed_native = len(owners) - int(local is not None)
    _need(len(receipt_identities) == expected_replayed_native, "successor replay identity cardinality differs")
    plan, _plan_raw, passes, pass_index, question_ids = composite._plan(plan_root, expected_plan_sha256)
    schedule = context.epoch["selected_request_ordinals"]
    _need(schedule == [item["ordinal"] for item in plan["requests"] if item.get("ordinal") in schedule]
          and schedule == [*range(1, 1611), *range(4049, 4739)] and len(schedule) == LOGICAL_COUNT, "selected request schedule differs")
    records_by_pass = {item["pass_id"]: item for item in passes}
    selected_ids = {request["pass_id"] for request in plan["requests"] if request.get("ordinal") in schedule}
    selected = [records_by_pass[item["pass_id"]] for item in plan["passes"] if item.get("pass_id") in selected_ids]
    _need(len(selected) == STORY_COUNT, "selected pass inventory differs")
    runtime = context.suffix._runtime_from_epoch(context.epoch)
    successor_runtime = suffix._runtime_from_epoch(recovery_epoch)
    _need(successor_runtime.transport_sha256 == runtime.transport_sha256, "recovery runtime transport differs")
    identities: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    for record in selected[:3]:
        run_root = next(item["run_root"] for item in context.old_passes if item["pass_id"] == record["pass_id"])
        replay = composite._actual_old_admit(context, plan_root=plan_root, pass_record=record, run_root=Path(run_root), approved_v4_routes=approved_v4_routes)
        verdicts = _verdicts(replay.get("verdicts"), question_ids, "old prefix")
        identities.extend(_identity(item, "old prefix") for item in replay.get("native_identities", []))
        ordinals = [item["ordinal"] for item in plan["requests"] if item.get("pass_id") == record["pass_id"]]
        rows.append(_record(record=record, ordinals=ordinals, verdicts=verdicts, runtime=runtime,
                            provenance={"kind": "original_v4_prefix"}, replay_input_commitments={
                                "run_manifest_sha256": replay["run_manifest_sha256"], "checkpoint_head_sha256": replay["checkpoint_head_sha256"]}))
    mixed = selected[3]
    recovered = composite._load_module(Path(context.epoch["recovered_study_source"]["path"]), context.epoch["recovered_study_source"]["sha256"], "recovered study")
    prefix = recovered.admit_prefix(context.epoch["old_prefix_run_root"], source=composite._measurement_source(plan_root, mixed), batch_size=8,
                                    approved_routes=dict(approved_v4_routes), expected_batches=11,
                                    expected_recovered_manifest_sha256=context.epoch["recovered_study_manifest"]["sha256"],
                                    expected_adoption_sha256=context.epoch["recovery_adoption_sha256"],
                                    expected_amendment_sha256=context.epoch["recovery_amendment_sha256"], runtime=context.old_runtime)
    mixed_verdicts = list(prefix["verdicts"])
    identities.extend(_identity(item, "mixed prefix") for item in prefix["native_identities"])
    terminals: list[dict[str, Any]] = []
    for ordinal in range(81, 93):
        request = requests_by_ordinal[ordinal]
        if ordinal in OLD_V5_ORDINALS:
            owner = {"kind": "old_v5", "root": str(old_root), "epoch_sha256": expected_old_epoch_sha256}
            epoch, replay_runtime = context.epoch, runtime
        else:
            owner = _owner(owners, ordinal)
            epoch, replay_runtime = recovery_epoch, successor_runtime
        batch, identity = suffix._replay_suffix_terminal(root=Path(owner["root"]), epoch_sha256=owner["epoch_sha256"], epoch=epoch,
            runtime=replay_runtime, plan_root=plan_root, passed=pass_index[request["pass_id"]], row=request, approved_v5_routes=approved_v5_routes)
        mixed_verdicts.extend(batch)
        identities.append(_identity(identity, "mixed suffix"))
        terminals.append(_terminal_commitment(suffix, owner, ordinal))
    rows.append(_record(record=mixed, ordinals=list(range(70, 93)), verdicts=_verdicts(mixed_verdicts, question_ids, "mixed pass"), runtime=runtime,
                        provenance={"kind": "v4_recovered70_old_v5_successor_replacements"}, replay_input_commitments={
                            "prefix_run_manifest_sha256": prefix["run_manifest_sha256"], "prefix_checkpoint_head_sha256": prefix["checkpoint_head_sha256"],
                            "recovered_manifest_sha256": prefix["recovered_manifest_sha256"], "terminals": terminals}))
    for record in selected[4:]:
        verdicts: list[dict[str, Any]] = []
        terminals = []
        requests = sorted((item for item in plan["requests"] if item.get("pass_id") == record["pass_id"]), key=lambda item: item["ordinal"])
        for request in requests:
            ordinal = request["ordinal"]
            owner = _owner(owners, ordinal)
            if owner["kind"] == "local_schema_recovery":
                _need(local is not None and ordinal == local["ordinal"]
                      and [item.get("question_id") for item in local["verdicts"]] == request["question_ids"], "local projection request binding differs")
                verdicts.extend(local["verdicts"])
                terminals.append({"ordinal": ordinal, "owner": owner, "local_identity": local["local_identity"]})
                continue
            if owner["kind"] == "standing_v6_candidate_native":
                batch = candidate_batches.get(ordinal)
                _need(isinstance(batch, list) and [item.get("question_id") for item in batch] == request["question_ids"],
                      "standing v6 candidate request binding differs")
                verdicts.extend(batch)
                identities.append(_identity(owner["native_identity"], "standing v6 candidate"))
                terminals.append({"ordinal": ordinal, "owner": owner, "terminal_sha256": owner["terminal_sha256"]})
                continue
            batch, identity = suffix._replay_suffix_terminal(root=Path(owner["root"]), epoch_sha256=owner["epoch_sha256"], epoch=recovery_epoch,
                runtime=successor_runtime, plan_root=plan_root, passed=pass_index[record["pass_id"]], row=request, approved_v5_routes=approved_v5_routes)
            verdicts.extend(batch)
            identities.append(_identity(identity, "successor suffix"))
            terminals.append(_terminal_commitment(suffix, owner, ordinal))
        rows.append(_record(record=record, ordinals=[item["ordinal"] for item in requests], verdicts=_verdicts(verdicts, question_ids, "successor pass"),
                            runtime=successor_runtime, provenance={"kind": "root_chain", "owners": [_owner(owners, item["ordinal"]) for item in requests]},
                            replay_input_commitments={"terminals": terminals}))
    all_identities = _unique(identities)
    _need(len(rows) == STORY_COUNT, "collection story cardinality differs")
    expected_native_count = NATIVE_COUNT - int(local is not None)
    _need(len(all_identities) == expected_native_count, "collection native identity cardinality differs")
    _need(len(receipt_identities) == expected_replayed_native, "replay receipt identity cardinality differs")
    actual_pairs = sorted((item["request_id_hash"], item["session_id_hash"]) for item in all_identities)
    receipt_pairs = sorted((item["request_id_hash"], item["session_id_hash"]) for item in receipt_identities)
    _need(set(receipt_pairs).issubset(actual_pairs), "semantic replay identity differs")
    _need(not ({item["request_id_hash"] for item in all_identities} & {item["request_id_hash"] for item in historical_exclusions})
          and not ({item["session_id_hash"] for item in all_identities} & {item["session_id_hash"] for item in historical_exclusions}),
          "historical native identity collision")
    normalized_verdict_rows = [{"pass_id": row["pass_id"], "opaque_story_id": row["opaque_story_id"], **verdict}
                               for row in rows for verdict in row["verdict_rows"]]
    _need(len(normalized_verdict_rows) == VERDICT_COUNT, "collection verdict cardinality differs")
    _need(Path(__file__).read_bytes() == reader_raw, "collection reader source drifted")
    root_descriptors = [{"root": str(_descriptor(item)[0]), "manifest_sha256": _descriptor(item)[1]} for item in successor_roots]
    coverage_failures = [row["pass_id"] for row in rows if row["coverage"] < 0.88]
    result = {"schema_version": 1 if local is None else (3 if candidate_commitment is not None else 2),
            "evidence_class": "selected100_grok_successor_collection_replay_only_v1" if local is None else (
                "selected100_grok_successor_standing_v6_candidate_replay_only_v3" if candidate_commitment is not None else "selected100_grok_successor_local_schema_recovery_replay_only_v2"),
            "counts": {"stories": STORY_COUNT, "logical_requests": LOGICAL_COUNT, "native_requests": expected_native_count,
                       "study_recovered_requests": 1, "criterion_verdicts": VERDICT_COUNT},
            "input_commitments": {"reader_sha256": _sha(reader_raw), "plan_sha256": expected_plan_sha256,
                                  "predecessor_sha256": expected_predecessor_sha256, "old_suffix_epoch_sha256": expected_old_epoch_sha256,
                                  "selected_schedule_sha256": context.epoch["selected_schedule"]["sha256"],
                                  "selected_schedule_source_sha256": context.epoch["selected_schedule_source"]["sha256"],
                                  "composite_helper_sha256": COMPOSITE_SHA256, "suffix_helper_sha256": SUFFIX_SHA256,
                                  "recovery_controller_sha256": RECOVERY_SHA256, "recovery_manifest_sha256": recovery_commitment["manifest_sha256"],
                                  "successor_controller_sha256": SUCCESSOR_SHA256, "successor_root_chain_sha256": _sha(_canonical(root_descriptors)),
                                  "root_chain": [recovery_commitment, *successor_commitments]},
            "successor_root_chain": root_descriptors, "recovered_ordinals": [RECOVERED_ORDINAL] if local is None else [RECOVERED_ORDINAL, 254],
            "root_chain_ordinal_owners": dict(sorted(owners.items())), "root_chain_native_identities": receipt_identities,
            "historical_excluded_native_identities": historical_exclusions, "native_identities": all_identities,
            "native_identity_commitment_sha256": _sha(_canonical(all_identities)), "rows": rows,
            "normalized_verdict_rows": normalized_verdict_rows, "coverage_failures": coverage_failures,
            "full_study_admitted": False, "authority": False, "provider_calls_made": 0,
            "historical_prototype_only": local is None or candidate_commitment is None}
    if local is not None:
        _need(local_continuation is not None and local_commitment is not None, "local continuation result differs")
        result["counts"]["local_recovered_requests"] = 1
        result["input_commitments"].update({"local_continuation_manifest_sha256": local_commitment["manifest_sha256"],
                                             "local_continuation_controller_sha256": local_commitment["controller_sha256"],
                                             "local_continuation_descriptor_sha256": _sha(_canonical(dict(local_continuation))),
                                             "local_recovery_identity_sha256": local["local_identity"]["identity_sha256"]})
        result["local_continuation"] = dict(local_continuation)
        result["local_continuation_commitment"] = local_commitment
        result["local_recovery_identity"] = dict(local["local_identity"])
        result["local_recovery_provenance"] = dict(local["local_provenance"])
        result["local_recovery_protected_paths"] = dict(local_commitment["protected_paths"])
    if candidate_commitment is not None:
        _need(candidate_native_continuation is not None, "standing v6 continuation descriptor differs")
        result["input_commitments"].update({"standing_v6_continuation_manifest_sha256": candidate_commitment["manifest_sha256"],
                                             "standing_v6_continuation_controller_sha256": candidate_commitment["controller_sha256"],
                                             "standing_v6_continuation_descriptor_sha256": _sha(_canonical(dict(candidate_native_continuation))),
                                             "standing_v6_candidate_native_identity_commitment_sha256": candidate_commitment["native_identity_commitment_sha256"]})
        result["candidate_native_continuation"] = dict(candidate_native_continuation)
        result["standing_v6_candidate_commitment"] = candidate_commitment
        result["standing_v6_candidate_protected_paths"] = dict(candidate_commitment["protected_paths"])
    return result
