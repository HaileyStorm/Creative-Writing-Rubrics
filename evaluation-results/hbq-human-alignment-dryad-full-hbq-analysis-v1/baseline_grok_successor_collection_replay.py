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
STANDING_V6_CONTINUATION = ROOT / "baseline_grok_runtime_data_successor.py"
RENEWED_CONTINUATION = ROOT / "baseline_grok_renewed_successor.py"
PARALLEL_CONTINUATION = ROOT / "baseline_grok_parallel_successor.py"
CONTEXT_ADAPTER = ROOT / "baseline_runtime_data_collection_context.py"
PREFIX_ADAPTER = ROOT / "baseline_runtime_data_prefix.py"
COMPOSITE_SHA256 = "efd33ba0fcce7ae8c64a9aea280830998cb974c0250a411d657304a2fd0c50f6"
SUFFIX_SHA256 = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
RECOVERY_SHA256 = "687a60bcdd26227b3bcb6ae5081f3357bceb84b4b29312653617ef3d36887399"
SUCCESSOR_SHA256 = "fc0dbe04b3699522271157a87fc2f5a5659ffc108bd7eb3a68d6bf393e49bac8"
RENEWED_SUCCESSOR_SHA256 = (
    "e476b47fa4fc88f13fde1752d691352892d80af415f2bb6425077e66facc1696"
)
PARALLEL_SUCCESSOR_SHA256 = "99875e9997a98057086f63fec04fea2f7a40dda472b8d5452b35c8005ae2236d"
LOCAL_PROJECTION_SHA256 = (
    "0ae9213b33a51315f082f9091fe40601f21efbdc32475d8010956d9cd8ee716b"
)
LOCAL_ADOPTION_SHA256 = (
    "62eb162e148df15dd992e71952cd05a702c018163ec6759cb4ff508743ce1e8c"
)
LOCAL370_ADOPTION_SHA256 = (
    "7cc7f154d58e07f239eabf5a18780e5ae255963dec310ec38f4244141efc6528"
)
CONTEXT_ADAPTER_SHA256 = (
    "bf765db7d3aced1cdda1059037eda84972d160a75aba32869165d74823fb22e9"
)
PREFIX_ADAPTER_SHA256 = (
    "a30f0ded60dd783dac07bab45ca4e547f198fc82f98ad0f7fdf834f55e1da6a0"
)
SNAPSHOT_MANIFEST_SHA256 = (
    "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"
)
QUESTION_COUNT, STORY_COUNT = 178, 100
LOGICAL_COUNT, NATIVE_COUNT, VERDICT_COUNT = 2300, 2299, 17800
RECOVERED_ORDINAL = 70
OLD_V5_ORDINALS = [*range(81, 88), *range(89, 92)]
SUCCESSOR_SCHEDULE = [88, *range(92, 1611), *range(4049, 4739)]
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _digest(value: Any, label: str) -> str:
    _need(
        isinstance(value, str) and _HASH.fullmatch(value) is not None,
        f"{label} must be a lowercase SHA-256",
    )
    return value


def _read(path: Path | str, expected: str, label: str) -> bytes:
    checked = Path(path).resolve()
    _need(checked.is_file(), f"{label} is missing")
    raw = checked.read_bytes()
    _need(
        _sha(raw) == _digest(expected, label + " hash") and checked.read_bytes() == raw,
        f"{label} drifted",
    )
    return raw


def _json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error


def _module(path: Path, expected: str, label: str) -> ModuleType:
    raw = _read(path, expected, label)
    spec = importlib.util.spec_from_file_location(
        "_dryad_successor_collection_" + label.replace(" ", "_"), path
    )
    _need(spec is not None and spec.loader is not None, f"{label} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _need(path.read_bytes() == raw, f"{label} changed while loading")
    return module


def _source_descriptor(
    value: Any, *, path: Path, expected: str, label: str
) -> dict[str, str]:
    _need(
        isinstance(value, Mapping) and set(value) == {"path", "sha256"},
        f"{label} descriptor differs",
    )
    actual = Path(value["path"]).resolve()
    _need(
        actual == path.resolve() and value.get("sha256") == expected,
        f"{label} descriptor differs",
    )
    _read(actual, expected, label)
    return {"path": str(actual), "sha256": expected}


def _runtime_data(value: Any) -> tuple[ModuleType, ModuleType, dict[str, Any]]:
    _need(
        isinstance(value, Mapping)
        and set(value)
        == {
            "context_adapter",
            "snapshot_manifest",
            "prefix_adapter",
            "source_bindings",
        },
        "runtime data binding differs",
    )
    context_descriptor = _source_descriptor(
        value["context_adapter"],
        path=CONTEXT_ADAPTER,
        expected=CONTEXT_ADAPTER_SHA256,
        label="runtime context adapter",
    )
    prefix_descriptor = _source_descriptor(
        value["prefix_adapter"],
        path=PREFIX_ADAPTER,
        expected=PREFIX_ADAPTER_SHA256,
        label="runtime prefix adapter",
    )
    snapshot = value["snapshot_manifest"]
    _need(
        isinstance(snapshot, Mapping)
        and set(snapshot) == {"path", "sha256"}
        and snapshot.get("sha256") == SNAPSHOT_MANIFEST_SHA256,
        "runtime snapshot manifest binding differs",
    )
    snapshot_descriptor = {
        "path": str(Path(snapshot["path"]).resolve()),
        "sha256": SNAPSHOT_MANIFEST_SHA256,
    }
    _read(
        snapshot_descriptor["path"],
        snapshot_descriptor["sha256"],
        "runtime snapshot manifest",
    )
    bindings = value["source_bindings"]
    _need(
        isinstance(bindings, Mapping)
        and set(bindings)
        == {
            "runtime_data_snapshot_v4",
            "runtime_data_snapshot_v5",
            "native_data_admission",
            "recovered_data_admission",
        },
        "runtime data source bindings differ",
    )
    expected = {
        "runtime_data_snapshot_v4": (
            ROOT / "baseline_runtime_data_snapshot_v4.py",
            "7bc63e52688d7b0f4546fe3d8681b7e446ea5b6ddc2c20c7ae6f05c6a0199513",
        ),
        "runtime_data_snapshot_v5": (
            ROOT / "baseline_runtime_data_snapshot.py",
            "eb068749b2483d4b8ca480e5e57865692b89518fe924848f57d324574d167b0c",
        ),
        "native_data_admission": (
            ROOT / "baseline_native_data_admission.py",
            "719dd0af186f38bdeff2ee08cf9b90275003c28cd08b1c7abd246882f585b366",
        ),
        "recovered_data_admission": (
            ROOT / "baseline_recovered_data_admission.py",
            "cee3fa24b15031632ced4681e69fdd8c5ee0119728d768b0026db46ad66a0997",
        ),
    }
    bound = {
        name: _source_descriptor(
            bindings[name], path=path, expected=digest, label=name.replace("_", " ")
        )
        for name, (path, digest) in expected.items()
    }
    return (
        _module(CONTEXT_ADAPTER, CONTEXT_ADAPTER_SHA256, "runtime context adapter"),
        _module(PREFIX_ADAPTER, PREFIX_ADAPTER_SHA256, "runtime prefix adapter"),
        {
            "context_adapter": context_descriptor,
            "snapshot_manifest": snapshot_descriptor,
            "prefix_adapter": prefix_descriptor,
            "source_bindings": bound,
        },
    )


def _verify_runtime_data_sources(runtime_data: Mapping[str, Any]) -> None:
    _read(
        runtime_data["context_adapter"]["path"],
        runtime_data["context_adapter"]["sha256"],
        "runtime context adapter",
    )
    _read(
        runtime_data["prefix_adapter"]["path"],
        runtime_data["prefix_adapter"]["sha256"],
        "runtime prefix adapter",
    )
    _read(
        runtime_data["snapshot_manifest"]["path"],
        runtime_data["snapshot_manifest"]["sha256"],
        "runtime snapshot manifest",
    )
    for name, descriptor in runtime_data["source_bindings"].items():
        _read(descriptor["path"], descriptor["sha256"], name.replace("_", " "))


def _v5_runtime_for_epoch(runtime_config: Mapping[str, Any], epoch: Mapping[str, Any]) -> Any:
    _verify_runtime_data_sources(runtime_config)
    descriptor = runtime_config["source_bindings"]["runtime_data_snapshot_v5"]
    loader = _module(Path(descriptor["path"]), descriptor["sha256"], "V5 runtime data loader")
    runtime = loader.load_runtime_from_epoch(
        dict(epoch), snapshot_manifest_path=Path(runtime_config["snapshot_manifest"]["path"]),
        expected_snapshot_manifest_sha256=runtime_config["snapshot_manifest"]["sha256"],
    )
    runtime.verify()
    _verify_runtime_data_sources(runtime_config)
    return runtime


def _runtime_data_protected_paths(
    *,
    context: Any,
    runtime_config: Mapping[str, Any],
    recovery_root: Path,
    recovery_commitment: Mapping[str, Any],
    recovery_runtime: Any,
) -> dict[str, dict[str, str]]:
    protected = {
        name: dict(descriptor)
        for name, descriptor in runtime_config["source_bindings"].items()
    }
    protected.update(
        {
            "context_adapter": dict(runtime_config["context_adapter"]),
            "prefix_adapter": dict(runtime_config["prefix_adapter"]),
            "snapshot_manifest": dict(runtime_config["snapshot_manifest"]),
            "old_epoch": dict(context.old_snapshot_descriptor["epoch"]),
        }
    )
    for runtime_name, runtime in (
        ("old", context.old_runtime),
        ("suffix", context.suffix_runtime),
        ("recovery", recovery_runtime),
    ):
        provenance = runtime.provenance
        data = provenance["data"]
        for index, schema in enumerate(data["schema_pins"]):
            protected[f"{runtime_name}_schema_{index}"] = {
                "path": schema["storage_path"],
                "sha256": schema["sha256"],
            }
        canonical = data["current_canonical_schema"]
        protected[f"{runtime_name}_current_canonical_schema"] = {
            "path": canonical["path"],
            "sha256": canonical["sha256"],
        }
    recovery_epoch = recovery_root / "suffix-epoch.json"
    recovery_epoch_sha256 = recovery_commitment["inner_epoch_sha256"]
    _read(recovery_epoch, recovery_epoch_sha256, "recovery epoch")
    protected["recovery_epoch"] = {
        "path": str(recovery_epoch),
        "sha256": recovery_epoch_sha256,
    }
    for name, descriptor in protected.items():
        _need(
            isinstance(descriptor, Mapping) and set(descriptor) == {"path", "sha256"},
            "runtime data protected path differs",
        )
        _read(
            descriptor["path"], descriptor["sha256"], f"runtime data protected {name}"
        )
    return protected


def _identity(value: Any, label: str) -> dict[str, str]:
    fields = {"request_id_hash", "session_id_hash"}
    _need(
        isinstance(value, Mapping)
        and set(value) in (fields, fields | {"observed_turns"}),
        f"{label} identity differs",
    )
    result = {key: value[key] for key in fields}
    _need(
        all(
            isinstance(item, str) and _HASH.fullmatch(item) for item in result.values()
        ),
        f"{label} identity differs",
    )
    if "observed_turns" in value:
        _need(
            type(value["observed_turns"]) is int and value["observed_turns"] >= 1,
            f"{label} identity differs",
        )
    return result


def _unique(identities: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = [_identity(item, "collection") for item in identities]
    request_ids = [item["request_id_hash"] for item in result]
    session_ids = [item["session_id_hash"] for item in result]
    _need(
        len(request_ids) == len(set(request_ids))
        and len(session_ids) == len(set(session_ids)),
        "collection native identity duplicate",
    )
    return result


def _verdicts(
    value: Any, question_ids: Sequence[str], label: str
) -> list[dict[str, Any]]:
    _need(
        isinstance(value, list) and question_ids and len(value) == len(question_ids),
        f"{label} verdict count differs",
    )
    rows = [dict(item) for item in value if isinstance(item, Mapping)]
    _need(
        len(rows) == len(question_ids)
        and [item.get("question_id") for item in rows] == list(question_ids),
        f"{label} criterion order differs",
    )
    normalized = [
        {"question_id": item["question_id"], "verdict": item.get("verdict")}
        for item in rows
    ]
    _need(
        all(isinstance(item["verdict"], str) for item in normalized),
        f"{label} verdict differs",
    )
    return normalized


def _score(
    runtime: Any, *, verdicts: Sequence[Mapping[str, Any]], artifact_id: str
) -> tuple[float | int, float | int]:
    result = runtime.core.score_bundle(
        runtime.modules,
        runtime.bundle,
        list(verdicts),
        artifact_id=artifact_id,
        task_contract=None,
    )
    final = result.get("final_score") if isinstance(result, Mapping) else None
    observed = final.get("observed") if isinstance(final, Mapping) else None
    coverage = result.get("coverage") if isinstance(result, Mapping) else None
    _need(
        type(observed) in (int, float)
        and math.isfinite(observed)
        and 0 <= observed <= 100
        and type(coverage) in (int, float)
        and math.isfinite(coverage)
        and 0 <= coverage <= 1,
        "canonical collection score differs",
    )
    return observed, coverage


def _source_commitment(record: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "sha256": record.get("source_sha256"),
        "bytes": record.get("source_bytes"),
    }
    _need(
        isinstance(result["sha256"], str)
        and _HASH.fullmatch(result["sha256"])
        and type(result["bytes"]) is int
        and result["bytes"] >= 0,
        "story source commitment differs",
    )
    return result


def _record(
    *,
    record: Mapping[str, Any],
    ordinals: Sequence[int],
    verdicts: Sequence[Mapping[str, Any]],
    runtime: Any,
    provenance: Mapping[str, Any],
    replay_input_commitments: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_id = record.get("opaque_story_id")
    _need(
        isinstance(artifact_id, str)
        and artifact_id
        and isinstance(provenance, Mapping)
        and isinstance(replay_input_commitments, Mapping),
        "story replay record differs",
    )
    score, coverage = _score(runtime, verdicts=verdicts, artifact_id=artifact_id)
    normalized = list(verdicts)
    return {
        "pass_id": record["pass_id"],
        "partition": record["partition"],
        "opaque_story_id": artifact_id,
        "source": _source_commitment(record),
        "ordinals": list(ordinals),
        "provenance": dict(provenance),
        "replay_input_commitments": dict(replay_input_commitments),
        "verdict_rows": normalized,
        "verdicts_sha256": _sha(_canonical(normalized)),
        "score": score,
        "coverage": coverage,
    }


def _descriptor(value: Any) -> tuple[Path, str]:
    _need(
        isinstance(value, Mapping)
        and set(value) == {"root", "manifest_sha256"}
        and isinstance(value.get("root"), str),
        "successor root descriptor differs",
    )
    root = Path(value["root"]).resolve()
    _need(root.is_dir() and not root.is_symlink(), "successor root differs")
    return root, _digest(value["manifest_sha256"], "successor manifest")


def _local_descriptor(value: Any) -> tuple[Path, str, str]:
    _need(
        isinstance(value, Mapping)
        and set(value) == {"root", "manifest_sha256", "controller_sha256"}
        and isinstance(value.get("root"), str),
        "local continuation descriptor differs",
    )
    root = Path(value["root"]).resolve()
    _need(root.is_dir() and not root.is_symlink(), "local continuation root differs")
    return (
        root,
        _digest(value["manifest_sha256"], "local continuation manifest"),
        _digest(value["controller_sha256"], "local continuation controller"),
    )


def _terminal_commitment(
    parent: Any, owner: Mapping[str, Any], ordinal: int
) -> dict[str, Any]:
    raw = parent._attempt_path(
        Path(owner["root"]), ordinal, "terminal.json"
    ).read_bytes()
    digest = _sha(raw)
    _need(
        owner.get("terminal_sha256") in (None, digest), "partial peer terminal changed"
    )
    return {"ordinal": ordinal, "terminal_sha256": digest, "owner": dict(owner)}


def _local_continuation(
    *,
    descriptor: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
    successor_root: Path,
    successor_manifest_sha256: str,
    include_untouched: bool,
    runtime: Any | None = None,
    prefix_adapter: Any | None = None,
) -> tuple[
    dict[str, Any], dict[int, dict[str, Any]], list[dict[str, str]], dict[str, Any]
]:
    root, manifest_sha256, controller_sha256 = _local_descriptor(descriptor)
    controller = _module(
        LOCAL_CONTINUATION, controller_sha256, "local continuation controller"
    )
    if runtime is None:
        local = controller.verify_local_continuation(
            continuation_root=root,
            expected_manifest_sha256=manifest_sha256,
            expected_controller_sha256=controller_sha256,
        )
        native = (
            controller.verify_untouched_replay_chain(
                continuation_root=root,
                expected_manifest_sha256=manifest_sha256,
                expected_controller_sha256=controller_sha256,
                approved_v5_routes=approved_v5_routes,
            )
            if include_untouched
            else None
        )
    else:
        _need(prefix_adapter is not None, "runtime prefix adapter differs")
        local = prefix_adapter.verify_local_continuation_with_runtime(
            continuation_root=root,
            expected_manifest_sha256=manifest_sha256,
            expected_controller_sha256=controller_sha256,
            runtime=runtime,
        )
        native = (
            prefix_adapter.verify_untouched_replay_chain_with_runtime(
                continuation_root=root,
                expected_manifest_sha256=manifest_sha256,
                expected_controller_sha256=controller_sha256,
                runtime=runtime,
                approved_v5_routes=approved_v5_routes,
            )
            if include_untouched
            else None
        )
    local_required = {
        "ordinal",
        "evidence_class",
        "verdicts",
        "local_identity",
        "local_provenance",
        "ownership",
        "source",
        "protected_paths",
        "partial_peer_records",
        "partial_peer_source",
        "provider_calls_made",
        "full_original_study_admitted",
        "review_decision",
        "standing_authority_kind",
    }
    native_required = {
        "untouched_replay_ordinals",
        "untouched_native_identities",
        "untouched_terminals",
        "provider_calls_made",
        "protected_native_identity_count",
    }
    if runtime is not None:
        local_required = local_required | {"verifier_provenance"}
        native_required = native_required | {"verifier_provenance"}
    _need(
        isinstance(local, Mapping)
        and set(local) == local_required
        and local.get("ordinal") == 254
        and local.get("evidence_class") == "owner_adopted_local_session_schema_recovery"
        and local.get("provider_calls_made") == 0
        and local.get("full_original_study_admitted") is False
        and isinstance(local.get("source"), Mapping)
        and local["source"]
        == {
            "root": str(root),
            "manifest_sha256": manifest_sha256,
            "controller_sha256": controller_sha256,
            "successor_root": str(successor_root),
            "successor_manifest_sha256": successor_manifest_sha256,
            "partial_sha256": "889429a738d3b7724abc7652518d5fab46041b5db4db1c4fb3ae9db85752a1e2",
            "inner_epoch_sha256": local["source"].get("inner_epoch_sha256"),
        },
        "local continuation source binding differs",
    )
    local_identity = local.get("local_identity")
    _need(
        isinstance(local_identity, Mapping)
        and set(local_identity)
        == {"kind", "ordinal", "projection_sha256", "identity_sha256"}
        and local_identity.get("kind") == "local_schema_projection"
        and local_identity.get("ordinal") == 254
        and local_identity.get("projection_sha256") == LOCAL_PROJECTION_SHA256
        and isinstance(local_identity.get("identity_sha256"), str)
        and _HASH.fullmatch(local_identity["identity_sha256"]),
        "local continuation identity differs",
    )
    provenance = local.get("local_provenance")
    _need(
        isinstance(provenance, Mapping)
        and provenance.get("adoption_sha256") == LOCAL_ADOPTION_SHA256
        and provenance.get("ordinary_native_admission") is False
        and provenance.get("new_provider_attempts_authorized") == 0,
        "local continuation provenance differs",
    )
    protected_paths = local.get("protected_paths")
    protected_path_keys = {
        "continuation_root",
        "continuation_manifest",
        "controller",
        "successor_root",
        "successor_manifest",
        "partial",
        "proposal",
        "adoption",
        "independent_review",
        "standing_authority",
        "local_projection",
        "protected_native_identities",
        "inner_epoch",
    }
    _need(
        isinstance(protected_paths, Mapping)
        and set(protected_paths) == protected_path_keys
        and protected_paths.get("controller")
        == {"path": str(LOCAL_CONTINUATION.resolve()), "sha256": controller_sha256}
        and protected_paths.get("continuation_manifest")
        == {
            "path": str(root / "local-continuation-manifest.json"),
            "sha256": manifest_sha256,
        },
        "local continuation protected paths differ",
    )
    peer_source = local.get("partial_peer_source")
    expected_peer_ordinals = [252, 253, 255, 256, 257, 258, 259, 260, 261]
    _need(
        isinstance(peer_source, Mapping)
        and peer_source
        == {
            "root": str(successor_root),
            "successor_manifest_sha256": successor_manifest_sha256,
            "inner_epoch_sha256": local["source"]["inner_epoch_sha256"],
            "partial": {
                "path": peer_source.get("partial", {}).get("path")
                if isinstance(peer_source.get("partial"), Mapping)
                else None,
                "sha256": "889429a738d3b7724abc7652518d5fab46041b5db4db1c4fb3ae9db85752a1e2",
            },
        },
        "local continuation partial source binding differs",
    )
    peer_records = local.get("partial_peer_records")
    _need(
        isinstance(peer_records, list)
        and [item.get("ordinal") for item in peer_records if isinstance(item, Mapping)]
        == expected_peer_ordinals,
        "local continuation partial peer ordinals differ",
    )
    peer_identities: list[dict[str, str]] = []
    for record in peer_records:
        _need(
            isinstance(record, Mapping)
            and set(record)
            == {
                "ordinal",
                "criterion_verdict_count",
                "native_identity",
                "terminal_sha256",
                "controller_authorization_sha256",
            }
            and record.get("ordinal") in expected_peer_ordinals
            and type(record.get("criterion_verdict_count")) is int
            and all(
                isinstance(record.get(key), str) and _HASH.fullmatch(record[key])
                for key in ("terminal_sha256", "controller_authorization_sha256")
            ),
            "local continuation partial peer differs",
        )
        peer_identities.append(
            _identity(record["native_identity"], "local continuation partial peer")
        )
    peer_identities = _unique(peer_identities)
    ordinals: list[int] = []
    identities: list[dict[str, str]] = []
    terminals: list[Mapping[str, Any]] = []
    if include_untouched:
        _need(
            isinstance(native, Mapping)
            and set(native) == native_required
            and native.get("provider_calls_made") == 0
            and native.get("protected_native_identity_count") == 259,
            "local continuation native replay differs",
        )
        ordinals, identities, terminals = (
            native["untouched_replay_ordinals"],
            _unique(native["untouched_native_identities"]),
            native["untouched_terminals"],
        )
        expected = [*range(262, 1611), *range(4049, 4739)]
        _need(
            ordinals == expected
            and len(identities) == len(expected)
            and isinstance(terminals, list)
            and len(terminals) == len(expected),
            "local continuation untouched schedule differs",
        )
    terminal_by_ordinal: dict[int, dict[str, Any]] = {}
    for ordinal, terminal in zip(ordinals, terminals, strict=True):
        _need(
            isinstance(terminal, Mapping)
            and set(terminal)
            == {"ordinal", "terminal_sha256", "controller_authorization_sha256"}
            and terminal.get("ordinal") == ordinal
            and all(
                isinstance(terminal[key], str) and _HASH.fullmatch(terminal[key])
                for key in ("terminal_sha256", "controller_authorization_sha256")
            ),
            "local continuation terminal differs",
        )
        terminal_by_ordinal[ordinal] = dict(terminal)
    local_owner = {
        "kind": "local_schema_recovery",
        "root": str(root),
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "ordinal": 254,
        "local_identity": dict(local_identity),
        "local_provenance": dict(local["local_provenance"]),
        "replay_receipt": "local_projection",
    }
    owners = {
        record["ordinal"]: {
            "kind": "partial_predecessor_peer",
            "root": str(successor_root),
            "manifest_sha256": successor_manifest_sha256,
            "controller_sha256": SUCCESSOR_SHA256,
            "epoch_sha256": peer_source["inner_epoch_sha256"],
            "partial_202_sha256": peer_source["partial"]["sha256"],
            "terminal_sha256": record["terminal_sha256"],
            "controller_authorization_sha256": record[
                "controller_authorization_sha256"
            ],
            "replay_receipt": "retained_partial_202",
        }
        for record in peer_records
    }
    owners[254] = local_owner
    for ordinal, terminal in terminal_by_ordinal.items():
        owners[ordinal] = {
            "kind": "local_continuation_native",
            "root": str(root),
            "manifest_sha256": manifest_sha256,
            "controller_sha256": controller_sha256,
            "epoch_sha256": local["source"]["inner_epoch_sha256"],
            "terminal_sha256": terminal["terminal_sha256"],
            "controller_authorization_sha256": terminal[
                "controller_authorization_sha256"
            ],
            "replay_receipt": "local_continuation",
        }
    commitment = {
        "root": str(root),
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "local_identity": dict(local_identity),
        "local_provenance": dict(local["local_provenance"]),
        "protected_paths": dict(protected_paths),
        "protected_paths_sha256": _sha(_canonical(dict(protected_paths))),
        "partial_peer_ordinals": expected_peer_ordinals,
        "untouched_replay_ordinals": list(ordinals),
        "untouched_native_identity_commitment_sha256": _sha(_canonical(identities)),
    }
    if runtime is not None:
        _need(
            isinstance(local.get("verifier_provenance"), Mapping)
            and (
                not include_untouched
                or isinstance(native, Mapping)
                and isinstance(native.get("verifier_provenance"), Mapping)
            ),
            "runtime prefix verifier provenance differs",
        )
        commitment["runtime_verifier_provenance"] = {
            "local": dict(local["verifier_provenance"]),
            "untouched": dict(native["verifier_provenance"])
            if include_untouched
            else None,
        }
    return dict(local), owners, _unique([*peer_identities, *identities]), commitment


def _candidate_native_continuation(
    *, descriptor: Mapping[str, Any], local_descriptor: Mapping[str, Any]
) -> tuple[
    dict[int, dict[str, Any]],
    list[dict[str, str]],
    dict[int, list[dict[str, Any]]],
    dict[str, Any],
]:
    root, manifest_sha256, controller_sha256 = _local_descriptor(descriptor)
    controller = _module(
        STANDING_V6_CONTINUATION,
        controller_sha256,
        "standing v6 continuation controller",
    )
    state = controller.verify_runtime_data_successor(
        continuation_root=root, expected_manifest_sha256=manifest_sha256
    )
    replay = controller.verify_runtime_data_replay_chain(
        continuation_root=root,
        expected_manifest_sha256=manifest_sha256,
        expected_controller_sha256=controller_sha256,
    )
    originals = list(range(262, 279))
    future = [*range(280, 1611), *range(4049, 4739)]
    expected = [*range(262, 1611), *range(4049, 4739)]
    context = state.get("context") if isinstance(state, Mapping) else None
    records = getattr(context, "records", None)
    recovered = state.get("recovered") if isinstance(state, Mapping) else None
    adoption = state.get("adoption") if isinstance(state, Mapping) else None
    successor_manifest = state.get("manifest") if isinstance(state, Mapping) else None
    _need(
        isinstance(state, Mapping)
        and isinstance(successor_manifest, Mapping)
        and successor_manifest.get("pending_ordinals") == future
        and isinstance(records, list)
        and [item.get("ordinal") for item in records if isinstance(item, Mapping)]
        == originals
        and isinstance(recovered, Mapping)
        and recovered.get("ordinal") == 279
        and isinstance(adoption, Mapping)
        and recovered.get("original_terminal_state") == "ambiguous"
        and state.get("provider_calls_made") == 0,
        "runtime data successor binding differs",
    )
    required = {
        "candidate_native_replay_ordinals",
        "candidate_native_identities",
        "candidate_native_terminals",
        "candidate_native_verdicts",
        "recovered_279",
        "adoption",
        "provider_calls_made",
    }
    _need(
        isinstance(replay, Mapping)
        and set(replay) == required
        and replay.get("candidate_native_replay_ordinals") == future
        and replay.get("recovered_279") == recovered
        and replay.get("adoption") == adoption
        and replay.get("provider_calls_made") == 0,
        "runtime data successor replay differs",
    )
    record_by_ordinal = {
        item["ordinal"]: item for item in records if isinstance(item, Mapping)
    }
    _need(
        set(record_by_ordinal) == set(originals)
        and all(
            isinstance(item.get("terminal"), Mapping)
            and isinstance(item.get("native_identity"), Mapping)
            and isinstance(item.get("verdicts"), list)
            for item in record_by_ordinal.values()
        ),
        "runtime data original terminal binding differs",
    )
    terminal_source_roots = getattr(context, "manifest", {}).get(
        "terminal_source_roots", {}
    )
    _need(
        isinstance(terminal_source_roots, Mapping),
        "runtime data original root bindings differ",
    )
    tail_identities = _unique(
        [
            item.get("native_identity")
            for item in replay["candidate_native_terminals"]
            if isinstance(item, Mapping)
        ]
    )
    identities = _unique(
        [
            *(item["native_identity"] for item in records),
            recovered["native_identity"],
            *tail_identities,
        ]
    )
    terminals = replay["candidate_native_terminals"]
    verdict_batches = replay["candidate_native_verdicts"]
    _need(
        len(identities) == len(expected)
        and isinstance(terminals, list)
        and len(terminals) == len(future)
        and isinstance(verdict_batches, Mapping)
        and {int(key) for key in verdict_batches} == set(future),
        "runtime data successor cardinality differs",
    )
    owners: dict[int, dict[str, Any]] = {}
    batches: dict[int, list[dict[str, Any]]] = {}
    for ordinal in originals:
        record = record_by_ordinal[ordinal]
        batch = record["verdicts"]
        descriptor = terminal_source_roots.get(
            str(ordinal), {"root": str(context.root), "terminal": record["terminal"]}
        )
        _need(
            isinstance(descriptor, Mapping)
            and type(descriptor.get("root")) is str
            and descriptor["root"]
            and descriptor.get("terminal") == record["terminal"],
            "runtime data original root binding differs",
        )
        batches[ordinal] = [dict(item) for item in batch]
        owners[ordinal] = {
            "kind": "standing_v6_runtime_data_original_native",
            "root": descriptor["root"],
            "terminal_source_root": dict(descriptor),
            "terminal_sha256": record["terminal"]["sha256"],
            "native_identity": dict(record["native_identity"]),
            "replay_receipt": "runtime_data_original",
        }
    batches[279] = [dict(item) for item in recovered["verdicts"]]
    owners[279] = {
        "kind": "standing_v6_runtime_data_recovered_native",
        "root": str(root),
        "original_terminal": dict(recovered["original_terminal"]),
        "recovery_adoption": dict(adoption),
        "terminal_sha256": recovered["original_terminal"]["sha256"],
        "native_identity": dict(recovered["native_identity"]),
        "replay_receipt": "runtime_data_recovery_adoption",
    }
    for ordinal, terminal, identity in zip(
        future, terminals, tail_identities, strict=True
    ):
        _need(
            isinstance(terminal, Mapping)
            and terminal.get("ordinal") == ordinal
            and terminal.get("native_identity") == identity
            and isinstance(terminal.get("terminal_sha256"), str)
            and _HASH.fullmatch(terminal["terminal_sha256"]) is not None,
            "standing v6 candidate terminal differs",
        )
        batch = verdict_batches.get(ordinal, verdict_batches.get(str(ordinal)))
        _need(
            isinstance(batch, Mapping)
            and batch.get("terminal_sha256") == terminal["terminal_sha256"]
            and isinstance(batch.get("question_ids"), list)
            and isinstance(batch.get("verdicts"), list)
            and [
                item.get("question_id")
                for item in batch["verdicts"]
                if isinstance(item, Mapping)
            ]
            == batch["question_ids"],
            "standing v6 candidate verdict binding differs",
        )
        batches[ordinal] = [dict(item) for item in batch["verdicts"]]
        owners[ordinal] = {
            "kind": "standing_v6_runtime_data_successor_native",
            "root": str(root),
            "manifest_sha256": manifest_sha256,
            "controller_sha256": controller_sha256,
            "terminal_sha256": terminal["terminal_sha256"],
            "native_identity": dict(identity),
            "replay_receipt": "runtime_data_successor",
        }
    commitment = {
        "root": str(root),
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "candidate": dict(context.manifest["candidate"]),
        "packet": dict(context.manifest["packet"]),
        "standing_source": dict(context.manifest["standing_source"]),
        "protected_paths": {
            "continuation_root": {
                "root": str(root),
                "manifest_sha256": manifest_sha256,
            },
            "original_root": {
                "root": str(context.root),
                "manifest_sha256": _sha(context.manifest_raw),
            },
            "candidate": dict(context.manifest["candidate"]),
            "snapshot_manifest": dict(
                successor_manifest["source_closure"]["snapshot_manifest"]
            ),
            "runtime_storage": dict(
                successor_manifest["source_closure"]["runtime_loader"]
            ),
            "recovery_record": dict(
                successor_manifest["source_closure"]["recovery_record"]
            ),
            "recovery_adoption": dict(
                successor_manifest["source_closure"]["recovery_adoption"]
            ),
            **{
                f"original_terminal_{ordinal}": dict(
                    record_by_ordinal[ordinal]["terminal"]
                )
                for ordinal in originals
            },
        },
        "terminal_source_roots": {
            str(key): dict(value) for key, value in terminal_source_roots.items()
        },
        "original_replay_ordinals": originals,
        "recovered_replay_ordinals": [279],
        "future_replay_ordinals": future,
        "replay_ordinals": expected,
        "native_identity_commitment_sha256": _sha(_canonical(identities)),
    }
    return owners, identities, batches, commitment


def _renewed_native_continuation(
    *,
    descriptor: Mapping[str, Any],
    plan_root: Path,
    _expected_prefix_ordinals: Sequence[int] | None = None,
) -> tuple[
    dict[int, dict[str, Any]],
    list[dict[str, str]],
    dict[int, list[dict[str, Any]]],
    dict[str, Any],
]:
    root, manifest_sha256, controller_sha256 = _local_descriptor(descriptor)
    _need(
        controller_sha256 == RENEWED_SUCCESSOR_SHA256,
        "renewed successor controller differs",
    )
    controller = _module(
        RENEWED_CONTINUATION,
        controller_sha256,
        "renewed successor controller",
    )
    state = controller.verify(
        continuation_root=root, expected_manifest_sha256=manifest_sha256
    )
    manifest = state.get("manifest") if isinstance(state, Mapping) else None
    context = state.get("context") if isinstance(state, Mapping) else None
    historical = state.get("historical") if isinstance(state, Mapping) else None
    prefix = state.get("prefix") if isinstance(state, Mapping) else None
    source_epoch = state.get("source_epoch") if isinstance(state, Mapping) else None
    _need(
        isinstance(manifest, Mapping)
        and context is not None
        and isinstance(historical, Mapping)
        and isinstance(prefix, Mapping)
        and source_epoch == getattr(controller, "SOURCE_EPOCH", None)
        and Path(str(getattr(context, "plan_root", ""))).resolve() == plan_root,
        "renewed successor source epoch differs",
    )
    controller._records(root)
    replayed, _previous = controller._replayed(root, state)
    pending = list(state.get("pending_ordinals", []))
    controller_pending = list(getattr(controller, "PENDING", pending))
    if _expected_prefix_ordinals is None:
        _need(
            pending
            and replayed == set(pending)
            and pending == controller_pending,
            "renewed successor replay boundary differs",
        )
    else:
        expected_prefix = list(_expected_prefix_ordinals)
        _need(
            expected_prefix
            and expected_prefix == controller_pending[: len(expected_prefix)]
            and replayed == set(expected_prefix),
            "renewed successor replay prefix differs",
        )
        pending = expected_prefix
    closure = manifest.get("source_closure")
    historical_state = historical.get("state")
    prior_identities = historical.get("prior_identities")
    prefix_value = prefix.get("value")
    prefix_identities = prefix.get("identities")
    requests = getattr(context, "requests", None)
    _need(
        isinstance(closure, Mapping)
        and isinstance(historical_state, Mapping)
        and isinstance(prior_identities, list)
        and len(prior_identities) == 277
        and isinstance(prefix_value, Mapping)
        and isinstance(prefix_identities, list)
        and len(prefix_identities) == 58
        and len(state.get("prior_identities", [])) == 335
        and _unique(prior_identities + prefix_identities)
        and isinstance(requests, Mapping),
        "renewed historical identity boundary differs",
    )

    owners: dict[int, dict[str, Any]] = {}
    identities: list[dict[str, str]] = []
    batches: dict[int, list[dict[str, Any]]] = {}

    def bind_historical(
        *,
        ordinal: int,
        record: Mapping[str, Any],
        kind: str,
        receipt: str,
        root_value: str,
        manifest_value: str | None = None,
        controller_value: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        request = requests.get(ordinal)
        _need(
            isinstance(request, Mapping)
            and record.get("ordinal") == ordinal
            and isinstance(record.get("native_identity"), Mapping)
            and isinstance(record.get("verdicts"), list),
            "renewed historical record differs",
        )
        identity = _identity(record["native_identity"], "renewed historical")
        terminal = record.get("terminal")
        _need(
            isinstance(terminal, Mapping)
            and set(terminal) >= {"path", "sha256"},
            "renewed historical terminal differs",
        )
        terminal_raw = _read(
            Path(terminal["path"]), terminal["sha256"], "renewed historical terminal"
        )
        terminal_value = _json(terminal_raw, "renewed historical terminal")
        _need(
            isinstance(terminal_value, Mapping)
            and terminal_value.get("ordinal") == ordinal
            and terminal_value.get("state") == "completed"
            and _identity(terminal_value.get("native_identity"), "renewed historical terminal")
            == identity,
            "renewed historical terminal differs",
        )
        verdicts = _verdicts(
            record["verdicts"],
            request.get("question_ids", []),
            "renewed historical",
        )
        owner: dict[str, Any] = {
            "kind": kind,
            "root": root_value,
            "terminal_sha256": terminal["sha256"],
            "native_identity": dict(identity),
            "replay_receipt": receipt,
        }
        if manifest_value is not None:
            owner["manifest_sha256"] = manifest_value
        if controller_value is not None:
            owner["controller_sha256"] = controller_value
        if isinstance(extra, Mapping):
            owner.update(dict(extra))
        _need(ordinal not in owners, "renewed historical ordinal ownership collision")
        owners[ordinal] = owner
        identities.append(identity)
        batches[ordinal] = verdicts

    historical_context = historical_state.get("context")
    historical_records = getattr(historical_context, "records", None)
    _need(
        isinstance(historical_records, list)
        and [item.get("ordinal") for item in historical_records if isinstance(item, Mapping)]
        == list(range(262, 279)),
        "renewed original historical records differ",
    )
    historical_manifest = closure.get("historical_continuation")
    historical_controller = closure.get("historical_controller")
    _need(
        isinstance(historical_manifest, Mapping)
        and isinstance(historical_controller, Mapping),
        "renewed historical source descriptors differ",
    )
    terminal_source_roots = getattr(historical_context, "manifest", {}).get(
        "terminal_source_roots", {}
    )
    _need(
        isinstance(terminal_source_roots, Mapping),
        "renewed original terminal roots differ",
    )
    historical_manifest_value = historical.get("manifest")
    queue = (
        historical_manifest_value.get("source_closure", {}).get("queue")
        if isinstance(historical_manifest_value, Mapping)
        else None
    )
    _need(
        isinstance(queue, Mapping)
        and type(queue.get("path")) is str
        and bool(queue["path"]),
        "renewed historical queue differs",
    )
    broker = historical_context.candidate.Broker(Path(queue["path"]))
    for record in historical_records:
        ordinal = record["ordinal"]
        source_root = terminal_source_roots.get(str(ordinal))
        if source_root is None:
            source_root = {
                "root": str(getattr(historical_context, "root", root)),
                "terminal": dict(record["terminal"]),
            }
        _need(
            isinstance(source_root, Mapping)
            and type(source_root.get("root")) is str
            and bool(source_root["root"])
            and source_root.get("terminal") == record["terminal"],
            "renewed original terminal root differs",
        )
        bind_historical(
            ordinal=ordinal,
            record=record,
            kind="standing_v6_runtime_data_original_native",
            receipt="runtime_data_original",
            root_value=source_root["root"],
            extra={"terminal_source_root": dict(source_root)},
        )

    recovered = historical_state.get("recovered")
    request_279 = requests.get(279)
    _need(
        isinstance(recovered, Mapping)
        and isinstance(request_279, Mapping)
        and recovered.get("ordinal") == 279
        and isinstance(recovered.get("native_identity"), Mapping)
        and isinstance(recovered.get("verdicts"), list),
        "renewed recovered historical record differs",
    )
    recovered_identity = _identity(
        recovered["native_identity"], "renewed recovered historical"
    )
    recovered_verdicts = _verdicts(
        recovered["verdicts"], request_279.get("question_ids", []), "renewed recovered"
    )
    recovered_terminal = recovered.get("original_terminal")
    _need(
        isinstance(recovered_terminal, Mapping)
        and set(recovered_terminal) >= {"path", "sha256"},
        "renewed recovered historical terminal differs",
    )
    owners[279] = {
        "kind": "standing_v6_runtime_data_recovered_native",
        "root": historical_manifest["root"],
        "original_terminal": dict(recovered_terminal),
        "recovery_adoption": dict(historical_state.get("adoption", {})),
        "terminal_sha256": recovered_terminal["sha256"],
        "native_identity": dict(recovered_identity),
        "replay_receipt": "runtime_data_recovery_adoption",
    }
    identities.append(recovered_identity)
    batches[279] = recovered_verdicts

    prefix_records = prefix_value.get("current_records")
    _need(
        isinstance(prefix_records, list)
        and [item.get("ordinal") for item in prefix_records if isinstance(item, Mapping)]
        == list(range(280, 338)),
        "renewed retained prefix records differ",
    )
    for record in prefix_records:
        ordinal = record["ordinal"]
        request = requests.get(ordinal)
        _need(isinstance(request, Mapping), "renewed retained prefix request differs")
        terminal = record.get("terminal")
        replay = record.get("replay")
        _need(
            isinstance(terminal, Mapping)
            and isinstance(replay, Mapping)
            and set(terminal) >= {"path", "sha256"}
            and set(replay) >= {"path", "sha256"},
            "renewed retained prefix source differs",
        )
        terminal_raw = _read(
            Path(terminal["path"]), terminal["sha256"], "renewed retained terminal"
        )
        terminal_value = _json(terminal_raw, "renewed retained terminal")
        replay_raw = _read(
            Path(replay["path"]), replay["sha256"], "renewed retained replay"
        )
        replay_value = _json(replay_raw, "renewed retained replay")
        identity = _identity(record["native_identity"], "renewed retained identity")
        _need(
            terminal_value.get("ordinal") == ordinal
            and terminal_value.get("state") == "completed"
            and _identity(terminal_value.get("native_identity"), "renewed retained terminal")
            == identity
            and replay_value.get("ordinals") == [ordinal]
            and replay_value.get("native_identities")
            and _identity(replay_value["native_identities"][0], "renewed retained replay")
            == identity,
            "renewed retained prefix semantic binding differs",
        )
        semantic_identity, semantic_verdicts, semantic_descriptor = (
            historical_context.base._semantic_replay_terminal(
                candidate=historical_context.candidate,
                broker=broker,
                terminal=terminal_value,
                terminal_path=Path(terminal["path"]),
                parent=historical_context.parent,
                runtime=historical_context.runtime,
                plan_root=historical_context.plan_root,
                passes=historical_context.passes,
                requests=historical_context.requests,
            )
        )
        _need(
            _identity(semantic_identity, "renewed retained semantic identity") == identity
            and semantic_verdicts == terminal_value.get("verdicts")
            and isinstance(semantic_descriptor, Mapping)
            and semantic_descriptor.get("sha256")
            == replay_value.get("terminals", [{}])[0].get("native_envelope_sha256"),
            "renewed retained semantic replay differs",
        )
        _need(ordinal not in owners, "renewed retained ordinal ownership collision")
        owners[ordinal] = {
            "kind": "standing_v6_runtime_data_successor_native",
            "root": historical_manifest["root"],
            "manifest_sha256": historical_manifest["manifest_sha256"],
            "controller_sha256": historical_controller["sha256"],
            "terminal_sha256": terminal["sha256"],
            "native_identity": dict(identity),
            "terminal_source": dict(terminal),
            "replay_source": dict(replay),
            "replay_receipt": "runtime_data_successor",
        }
        identities.append(identity)
        batches[ordinal] = _verdicts(
            semantic_verdicts,
            request.get("question_ids", []),
            "renewed retained prefix",
        )

    for ordinal in pending:
        request = requests.get(ordinal)
        terminal_path = controller._attempt(root, ordinal, "terminal.json")
        replay_path = controller._replay(root, ordinal)
        terminal_raw = terminal_path.read_bytes()
        replay_raw = replay_path.read_bytes()
        terminal = _json(terminal_raw, "renewed terminal")
        replay = _json(replay_raw, "renewed replay")
        _need(
            isinstance(request, Mapping)
            and isinstance(terminal, Mapping)
            and isinstance(replay, Mapping)
            and terminal.get("source_epoch") == source_epoch
            and terminal.get("ordinal") == ordinal
            and terminal.get("state") == "completed"
            and replay.get("ordinals") == [ordinal]
            and replay.get("native_identities")
            and _identity(replay["native_identities"][0], "renewed replay identity")
            == _identity(terminal.get("native_identity"), "renewed terminal identity"),
            "renewed successor terminal binding differs",
        )
        identity = _identity(terminal["native_identity"], "renewed successor")
        _need(ordinal not in owners, "renewed successor ordinal ownership collision")
        replay_terminals = replay.get("terminals")
        _need(
            isinstance(replay_terminals, list)
            and len(replay_terminals) == 1
            and replay_terminals[0].get("ordinal") == ordinal
            and replay_terminals[0].get("terminal_sha256") == _sha(terminal_raw)
            and isinstance(replay_terminals[0].get("native_envelope_sha256"), str)
            and _HASH.fullmatch(replay_terminals[0]["native_envelope_sha256"]),
            "renewed successor replay descriptor differs",
        )
        semantic_identity, semantic_verdicts, semantic_descriptor = (
            controller._semantic_replay_terminal(
                candidate=historical_context.candidate,
                broker=broker,
                terminal=terminal,
                terminal_path=terminal_path,
                parent=historical_context.parent,
                runtime=historical_context.runtime,
                plan_root=historical_context.plan_root,
                passes=historical_context.passes,
                requests=historical_context.requests,
            )
        )
        _need(
            _identity(semantic_identity, "renewed semantic identity") == identity
            and semantic_verdicts == terminal.get("verdicts")
            and isinstance(semantic_descriptor, Mapping)
            and semantic_descriptor.get("sha256")
            == replay_terminals[0].get("native_envelope_sha256"),
            "renewed semantic replay differs",
        )
        owners[ordinal] = {
            "kind": "standing_v6_renewed_successor_native",
            "root": str(root),
            "manifest_sha256": manifest_sha256,
            "controller_sha256": controller_sha256,
            "source_epoch": source_epoch,
            "terminal_sha256": _sha(terminal_raw),
            "native_envelope_sha256": replay_terminals[0]["native_envelope_sha256"],
            "native_identity": dict(identity),
            "replay_receipt": "renewed_successor",
        }
        identities.append(identity)
        batches[ordinal] = _verdicts(
            semantic_verdicts,
            request.get("question_ids", []),
            "renewed successor",
        )

    expected_ordinals = [*range(262, 338), *pending]
    _need(
        sorted(owners) == expected_ordinals
        and len(identities) == len(expected_ordinals)
        and len(_unique(identities)) == len(expected_ordinals),
        "renewed successor ownership cardinality differs",
    )
    source_epoch_descriptor = {
        "source_epoch": source_epoch,
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "source_closure_sha256": manifest["source_closure_sha256"],
        "historical_manifest_sha256": historical_manifest["manifest_sha256"],
        "retained_prefix_sha256": closure["retained_prefix"]["sha256"],
    }
    manifest_path = root / "grok-renewed-successor-manifest.json"
    protected_paths = {
        "renewed_root": {"root": str(root), "manifest_sha256": manifest_sha256},
        "renewed_manifest": {"path": str(manifest_path), "sha256": manifest_sha256},
        "historical_controller": dict(historical_controller),
        "historical_manifest": {
            "path": historical_manifest["manifest_path"],
            "sha256": historical_manifest["manifest_sha256"],
        },
        "retained_prefix": dict(closure["retained_prefix"]),
        **{
            name: dict(closure[name])
            for name in ("gate", "standing_source", "packet")
        },
    }
    protected_roots = list(
        dict.fromkeys(
            [
                historical_manifest["root"],
                *(
                    item["root"]
                    for item in terminal_source_roots.values()
                    if isinstance(item, Mapping) and isinstance(item.get("root"), str)
                ),
            ]
        )
    )
    commitment = {
        "root": str(root),
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "source_epoch": dict(source_epoch_descriptor),
        "historical_identity_count": 335,
        "historical_identity_commitment_sha256": _sha(
            _canonical(state["prior_identities"])
        ),
        "retained_prefix_ordinals": list(range(280, 338)),
        "replay_ordinals": expected_ordinals,
        "native_identity_commitment_sha256": _sha(_canonical(identities)),
        "protected_roots": protected_roots,
        "protected_paths": protected_paths,
    }
    return owners, identities, batches, commitment


def _parallel_native_continuation(
    *, descriptor: Mapping[str, Any], plan_root: Path
) -> tuple[
    dict[int, dict[str, Any]],
    list[dict[str, str]],
    dict[int, list[dict[str, Any]]],
    dict[str, Any],
]:
    root, manifest_sha256, controller_sha256 = _local_descriptor(descriptor)
    controller = _module(
        PARALLEL_CONTINUATION,
        controller_sha256,
        "parallel successor controller",
    )
    result = controller.replay_collection(
        continuation_root=root,
        expected_manifest_sha256=manifest_sha256,
        require_complete=True,
    )
    _need(isinstance(result, Mapping), "parallel successor replay differs")
    source_epoch = result.get("source_epoch")
    manifest = result.get("manifest")
    prior = result.get("prior_continuation")
    prior_completed = result.get("prior_completed_ordinals")
    pending = result.get("pending_ordinals")
    completed = result.get("completed_ordinals")
    records = result.get("records")
    local_recoveries = result.get("local_recoveries", [])
    protected_paths = result.get("protected_paths")
    _need(
        isinstance(source_epoch, str)
        and isinstance(manifest, Mapping)
        and result.get("manifest_sha256") == manifest_sha256
        and isinstance(prior, Mapping)
        and set(prior) == {"root", "manifest_sha256", "controller_sha256"}
        and isinstance(prior_completed, list)
        and isinstance(pending, list)
        and isinstance(completed, list)
        and isinstance(records, list)
        and isinstance(local_recoveries, list)
        and isinstance(protected_paths, Mapping)
        and result.get("provider_calls_made") == 0,
        "parallel successor replay boundary differs",
    )
    _need(
        all(type(item) is int for item in prior_completed + pending + completed)
        and len(prior_completed) == len(set(prior_completed))
        and len(pending) == len(set(pending))
        and len(completed) == len(set(completed)),
        "parallel successor ordinal inventory differs",
    )
    _need(
        prior_completed
        == [*range(338, 1611), *range(4049, 4739)][: len(prior_completed)]
        and completed == [record.get("ordinal") for record in records]
        and completed == sorted(completed)
        and not set(prior_completed) & set(completed),
        "parallel successor ordinal boundary differs",
    )
    _need(
        all(
            type(item) is str and item
            for item in [
                result.get("plan_root"),
                prior.get("root"),
                prior.get("manifest_sha256"),
                prior.get("controller_sha256"),
            ]
        ),
        "parallel successor source descriptors differ",
    )
    _need(
        Path(str(result["plan_root"])).resolve() == plan_root,
        "parallel successor plan root differs",
    )
    serial_owners, serial_identities, serial_batches, serial_commitment = (
        _renewed_native_continuation(
            descriptor=prior,
            plan_root=plan_root,
            _expected_prefix_ordinals=prior_completed,
        )
    )
    owners = dict(serial_owners)
    identities = list(serial_identities)
    batches = dict(serial_batches)
    local_records: list[dict[str, Any]] = []
    for local in local_recoveries:
        _need(
            isinstance(local, Mapping)
            and local.get("ordinal") == 370
            and local.get("ordinary_native_admission") is False
            and isinstance(local.get("local_identity"), Mapping)
            and local["local_identity"].get("ordinal") == 370
            and isinstance(local["local_identity"].get("session_id"), str)
            and bool(local["local_identity"]["session_id"])
            and isinstance(local["local_identity"].get("answer_sha256"), str)
            and _HASH.fullmatch(local["local_identity"]["answer_sha256"])
            and isinstance(local.get("adoption"), Mapping)
            and set(local["adoption"]) == {"path", "sha256"}
            and local["adoption"]["sha256"] == LOCAL370_ADOPTION_SHA256
            and isinstance(local.get("original_terminal"), Mapping)
            and set(local["original_terminal"]) == {"path", "sha256"}
            and isinstance(local.get("protected_paths"), Mapping)
            and local["protected_paths"],
            "parallel local recovery record differs",
        )
        _read(
            local["adoption"]["path"],
            local["adoption"]["sha256"],
            "parallel local recovery adoption",
        )
        _read(
            local["original_terminal"]["path"],
            local["original_terminal"]["sha256"],
            "parallel local recovery terminal",
        )
        for name, item in local["protected_paths"].items():
            _need(
                isinstance(name, str)
                and isinstance(item, Mapping)
                and set(item) == {"path", "sha256"}
                and isinstance(item.get("path"), str)
                and _HASH.fullmatch(item.get("sha256", "")),
                "parallel local recovery protected path differs",
            )
            _read(item["path"], item["sha256"], "parallel local recovery protected path")
        verdict_rows = local.get("verdicts")
        question_ids = [
            item.get("question_id")
            for item in verdict_rows
            if isinstance(item, Mapping)
        ] if isinstance(verdict_rows, list) else []
        _need(
            isinstance(verdict_rows, list)
            and question_ids
            and len(question_ids) == len(set(question_ids))
            and all(isinstance(item, str) and item for item in question_ids),
            "parallel local recovery verdicts differ",
        )
        batch = _verdicts(verdict_rows, question_ids, "parallel local recovery")
        _need(
            all(item["verdict"] in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} for item in batch),
            "parallel local recovery verdicts differ",
        )
        local_copy = dict(local)
        local_copy["verdicts"] = batch
        local_records.append(local_copy)
    _need(
        len(local_records) <= 1
        and all(item["ordinal"] == 370 for item in local_records),
        "parallel local recovery ordinal differs",
    )
    if "source_closure" in manifest:
        closure = manifest.get("source_closure")
        declared_local = isinstance(closure, Mapping) and isinstance(
            closure.get("local_recovery"), Mapping
        )
        _need(
            bool(local_records) == declared_local,
            "parallel local recovery source declaration differs",
        )
    local_by_ordinal = {item["ordinal"]: item for item in local_records}
    if local_by_ordinal:
        local = local_by_ordinal[370]
        source_root = str(Path(local["original_terminal"]["path"]).resolve().parents[2])
        owners[370] = {
            "kind": "parallel_local_recovery",
            "root": source_root,
            "source_epoch": source_epoch,
            "manifest_sha256": manifest_sha256,
            "controller_sha256": controller_sha256,
            "local_identity": dict(local["local_identity"]),
            "adoption": dict(local["adoption"]),
            "original_terminal": dict(local["original_terminal"]),
            "protected_paths": {
                name: dict(item) for name, item in local["protected_paths"].items()
            },
            "ordinary_native_admission": False,
            "replay_receipt": "parallel_local_recovery",
        }
        batches[370] = list(local["verdicts"])
    parallel_ordinals: list[int] = []
    for record in records:
        _need(
            isinstance(record, Mapping)
            and type(record.get("ordinal")) is int
            and record["ordinal"] in completed
            and record["ordinal"] not in owners
            and isinstance(record.get("native_identity"), Mapping)
            and isinstance(record.get("terminal"), Mapping)
            and set(record["terminal"]) >= {"path", "sha256"}
            and record.get("source_epoch") == source_epoch
            and record.get("root") == str(root)
            and record.get("manifest_sha256") == manifest_sha256
            and record.get("controller_sha256") == controller_sha256
            and isinstance(record.get("native_envelope_sha256"), str)
            and _HASH.fullmatch(record["native_envelope_sha256"]),
            "parallel successor record differs",
        )
        ordinal = record["ordinal"]
        terminal = record["terminal"]
        _read(Path(terminal["path"]), terminal["sha256"], "parallel successor terminal")
        identity = _identity(record["native_identity"], "parallel successor identity")
        verdict_rows = record.get("verdicts")
        _need(isinstance(verdict_rows, list), "parallel successor verdicts differ")
        question_ids = [item.get("question_id") for item in verdict_rows if isinstance(item, Mapping)]
        _need(
            question_ids
            and len(question_ids) == len(set(question_ids))
            and all(isinstance(item, str) and item for item in question_ids),
            "parallel successor verdicts differ",
        )
        batch = _verdicts(verdict_rows, question_ids, "parallel successor")
        owners[ordinal] = {
            "kind": "parallel_renewal_native",
            "root": str(root),
            "manifest_sha256": manifest_sha256,
            "controller_sha256": controller_sha256,
            "source_epoch": source_epoch,
            "terminal_sha256": terminal["sha256"],
            "native_envelope_sha256": record["native_envelope_sha256"],
            "native_identity": dict(identity),
            "replay_receipt": "parallel_successor",
        }
        identities.append(identity)
        batches[ordinal] = batch
        parallel_ordinals.append(ordinal)
    _need(
        parallel_ordinals == completed
        and len(_unique(identities)) == len(identities)
        and all(ordinal not in serial_owners for ordinal in parallel_ordinals),
        "parallel successor identity or ownership collision",
    )
    source_epoch_descriptor = {
        "source_epoch": source_epoch,
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "prior_continuation": dict(prior),
    }
    protected_roots = list(serial_commitment.get("protected_roots", []))
    protected_roots.append(str(root))
    if local_records:
        protected_roots.append(
            str(Path(local_records[0]["original_terminal"]["path"]).resolve().parents[2])
        )
    merged_protected_paths = {
        **{
            f"serial_{name}": dict(item)
            for name, item in serial_commitment.get("protected_paths", {}).items()
        },
        **{
            f"parallel_{name}": dict(item)
            for name, item in protected_paths.items()
        },
    }
    commitment = {
        "root": str(root),
        "manifest_sha256": manifest_sha256,
        "controller_sha256": controller_sha256,
        "source_epoch": source_epoch_descriptor,
        "prior_continuation": dict(prior),
        "prior_completed_ordinals": list(prior_completed),
        "pending_ordinals": list(pending),
        "completed_ordinals": list(completed),
        "replay_ordinals": [*sorted(serial_owners), *parallel_ordinals],
        "native_identity_commitment_sha256": _sha(_canonical(identities)),
        "protected_roots": list(dict.fromkeys(protected_roots)),
        "protected_paths": merged_protected_paths,
    }
    if local_records:
        commitment.update(
            {
                "owner_ordinals": [
                    *sorted(serial_owners),
                    *[item["ordinal"] for item in local_records],
                    *parallel_ordinals,
                ],
                "local_recovery_ordinals": [item["ordinal"] for item in local_records],
                "local_recoveries": local_records,
                "local_recovery_adoption_sha256": (
                    local_records[0]["adoption"]["sha256"]
                    if len(local_records) == 1
                    else [item["adoption"]["sha256"] for item in local_records]
                ),
            }
        )
    return owners, identities, batches, commitment


def _historical_exclusions(predecessor: Mapping[str, Any]) -> list[dict[str, str]]:
    descriptor = predecessor.get("identity_exclusion")
    _need(
        isinstance(descriptor, Mapping) and set(descriptor) >= {"path", "sha256"},
        "historical identity exclusion differs",
    )
    value = _json(
        _read(
            descriptor["path"], descriptor["sha256"], "Historical identity exclusion"
        ),
        "Historical identity exclusion",
    )
    records = value.get("records") if isinstance(value, Mapping) else None
    _need(
        isinstance(records, list) and len(records) == 33,
        "historical identity exclusion differs",
    )
    return _unique(records)


def _recovery_chain(
    *,
    root: Path,
    recovery: Any,
    expected_controller_sha256: str,
    expected_manifest_sha256: str,
) -> tuple[
    Any,
    dict[str, Any],
    Path,
    dict[int, Any],
    set[int],
    list[dict[str, str]],
    dict[int, dict[str, Any]],
    dict[str, Any],
]:
    manifest_raw = _read(
        root / "recovery-manifest.json", expected_manifest_sha256, "Recovery manifest"
    )
    manifest = _json(manifest_raw, "Recovery manifest")
    _need(
        isinstance(manifest, Mapping)
        and manifest.get("controller_sha256") == expected_controller_sha256
        and _sha(RECOVERY.read_bytes()) == expected_controller_sha256,
        "recovery controller binding differs",
    )
    parent = recovery._load_parent(manifest["parent_source"]["sha256"])
    epoch, epoch_raw, plan_root, requests = recovery._inner(
        parent, root, manifest["inner_epoch"]["sha256"]
    )
    recovery._source_guard(parent, manifest, epoch_raw)
    replayed, identities = recovery._validated_replay_chain(
        root, parent, manifest, manifest_raw, epoch
    )
    _need(
        set(replayed) <= set(manifest["pending_ordinals"]),
        "recovery replay outside pending schedule",
    )
    protected = recovery._identity_file(
        Path(manifest["protected_native_identities"]["path"]),
        manifest["protected_native_identities"]["sha256"],
    )
    _unique([*protected, *identities])
    owner_base = {
        "kind": "first_recovery",
        "root": str(root),
        "manifest_sha256": _sha(manifest_raw),
        "controller_sha256": expected_controller_sha256,
        "epoch_sha256": manifest["inner_epoch"]["sha256"],
    }
    owners = {
        ordinal: {**owner_base, "replay_receipt": "recovery"} for ordinal in replayed
    }
    commitment = {
        "kind": "first_recovery",
        "root": str(root),
        "manifest_sha256": _sha(manifest_raw),
        "controller_sha256": expected_controller_sha256,
        "parent_sha256": manifest["parent_source"]["sha256"],
        "inner_epoch_sha256": manifest["inner_epoch"]["sha256"],
        "source_epoch_sha256": manifest["source_epoch"]["sha256"],
        "source_inventory_sha256": manifest["source_epoch_inventory"]["sha256"],
        "partial_replay_sha256": manifest["partial_replay"]["sha256"],
        "protected_native_identities_sha256": manifest["protected_native_identities"][
            "sha256"
        ],
        "replayed_ordinals": sorted(replayed),
    }
    return (
        parent,
        dict(epoch),
        plan_root,
        requests,
        set(replayed),
        _unique(identities),
        owners,
        commitment,
    )


def _partial_peer_owners(
    *,
    controller: Any,
    source_root: Path,
    manifest: Mapping[str, Any],
    partial: Mapping[str, Any],
    requests: Mapping[int, Any],
) -> tuple[dict[int, dict[str, Any]], list[dict[str, str]]]:
    """Bind a partial-wave success to the root that actually contains its terminal."""
    controller._verify_partial_source(
        source_root,
        partial,
        manifest["prior_manifest_sha256"],
        manifest["prior_controller_sha256"],
        requests,
    )
    records = {
        item.get("ordinal"): item
        for item in partial["records"]
        if isinstance(item, Mapping)
    }
    completed = partial["completed_ordinals"]
    _need(
        set(records) == set(completed)
        and all(type(ordinal) is int for ordinal in completed),
        "partial peer records differ",
    )
    protected = _unique(partial["all_protected_native_identities"])
    identities = _unique(partial["native_identities"])
    _need(
        all(identity in protected for identity in identities),
        "partial protected identity differs",
    )
    owners: dict[int, dict[str, Any]] = {}
    for ordinal, identity in zip(completed, identities, strict=True):
        record = records[ordinal]
        _need(
            ordinal in SUCCESSOR_SCHEDULE
            and _identity(record.get("native_identity"), "partial peer") == identity,
            "partial peer identity differs",
        )
        owners[ordinal] = {
            "kind": "partial_predecessor_peer",
            "root": str(source_root),
            "manifest_sha256": manifest["prior_manifest_sha256"],
            "controller_sha256": manifest["prior_controller_sha256"],
            "epoch_sha256": manifest["inner_epoch"]["sha256"],
            "partial_202_sha256": manifest["partial_202"]["sha256"],
            "terminal_sha256": record["terminal_sha256"],
            "replay_receipt": "partial_202",
        }
    return owners, identities


def _successor_chain(
    *,
    roots: Sequence[Mapping[str, Any]],
    controller: Any,
    parent: Any,
    recovery_root: Path,
    recovery_epoch: Mapping[str, Any],
    recovery_plan_root: Path,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    owners: dict[int, dict[str, Any]] = {}
    identities: list[dict[str, str]] = []
    commitments: list[dict[str, Any]] = []
    previous_root = recovery_root
    for descriptor in roots:
        root, expected_manifest = _descriptor(descriptor)
        manifest, manifest_raw = controller._manifest(root)
        _need(
            _sha(manifest_raw) == expected_manifest
            and Path(manifest["prior_root"]).resolve() == previous_root,
            "successor lineage differs",
        )
        partial = controller._partial(
            Path(manifest["partial_202"]["path"]), manifest["partial_202"]["sha256"]
        )
        prior = (
            _module(controller.PRIOR, controller.PRIOR_SHA, "prior controller")
            if manifest["prior_controller_sha256"] == controller.PRIOR_SHA
            else None
        )
        epoch, _epoch_raw, plan_root, requests = controller._source_guard(
            parent, prior, manifest, partial
        )
        _need(
            epoch == recovery_epoch and plan_root == recovery_plan_root,
            "successor epoch or plan differs",
        )
        partial_owners, partial_identities = _partial_peer_owners(
            controller=controller,
            source_root=previous_root,
            manifest=manifest,
            partial=partial,
            requests=requests,
        )
        replayed, replay_identities = controller._validated_replays(
            root, parent, manifest, manifest_raw
        )
        _need(
            set(replayed) <= set(manifest["pending_ordinals"])
            and set(
                manifest["predecessor_root_ownership"]["successor_replacements"]
            ).issubset(replayed),
            "successor replacement replay missing",
        )
        owner_base = {
            "kind": "successor",
            "root": str(root),
            "manifest_sha256": expected_manifest,
            "controller_sha256": manifest["controller_sha256"],
            "epoch_sha256": manifest["inner_epoch"]["sha256"],
        }
        for ordinal in replayed:
            _need(ordinal not in owners, "successor ordinal ownership collision")
            owners[ordinal] = {**owner_base, "replay_receipt": "successor"}
        for ordinal, owner in partial_owners.items():
            _need(
                ordinal not in owners, "successor partial ordinal ownership collision"
            )
            owners[ordinal] = owner
        identities.extend([*partial_identities, *replay_identities])
        commitments.append(
            {
                "kind": "successor",
                "root": str(root),
                "manifest_sha256": expected_manifest,
                "controller_sha256": manifest["controller_sha256"],
                "prior_root": str(previous_root),
                "prior_manifest_sha256": manifest["prior_manifest_sha256"],
                "parent_sha256": manifest["parent_sha256"],
                "prior_inventory_sha256": manifest["prior_inventory"]["sha256"],
                "inner_epoch_sha256": manifest["inner_epoch"]["sha256"],
                "partial_202_sha256": manifest["partial_202"]["sha256"],
                "protected_native_identities_sha256": manifest[
                    "protected_native_identities"
                ]["sha256"],
                "partial_completed_ordinals": list(partial["completed_ordinals"]),
                "partial_native_identity_commitment_sha256": _sha(
                    _canonical(partial_identities)
                ),
                "replayed_ordinals": sorted(replayed),
            }
        )
        previous_root = root
    _need(previous_root != recovery_root, "successor root chain is empty")
    return owners, _unique(identities), commitments


def _owner(owners: Mapping[int, Mapping[str, Any]], ordinal: int) -> dict[str, Any]:
    value = owners.get(ordinal)
    _need(isinstance(value, Mapping), "selected ordinal owner is missing")
    return dict(value)


def read_selected_successor_collection(
    *,
    plan_root: Path | str,
    predecessor_path: Path | str,
    old_suffix_root: Path | str,
    recovery_root: Path | str,
    expected_plan_sha256: str,
    expected_predecessor_sha256: str,
    expected_old_epoch_sha256: str,
    expected_suffix_source_sha256: str,
    expected_recovery_controller_sha256: str,
    expected_recovery_manifest_sha256: str,
    approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
    successor_roots: Sequence[Mapping[str, Any]],
    local_continuation: Mapping[str, Any] | None = None,
    candidate_native_continuation: Mapping[str, Any] | None = None,
    renewed_continuation: Mapping[str, Any] | None = None,
    parallel_continuation: Mapping[str, Any] | None = None,
    allow_legacy_local_v2_fixture: bool = False,
    runtime_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconstruct all selected stories from validated historic and successor terminals without dispatch."""
    reader_raw = Path(__file__).read_bytes()
    _need(
        expected_suffix_source_sha256 == SUFFIX_SHA256
        and expected_recovery_controller_sha256 == RECOVERY_SHA256,
        "frozen collection helper binding differs",
    )
    _need(
        sum(
            item is not None
            for item in (
                candidate_native_continuation,
                renewed_continuation,
                parallel_continuation,
            )
        )
        <= 1,
        "candidate and renewed continuations cannot be combined",
    )
    composite = _module(COMPOSITE, COMPOSITE_SHA256, "composite helper")
    suffix = _module(SUFFIX, expected_suffix_source_sha256, "suffix helper")
    recovery = _module(
        RECOVERY, expected_recovery_controller_sha256, "recovery controller"
    )
    controller = _module(SUCCESSOR, SUCCESSOR_SHA256, "successor controller")
    plan_root, old_root, recovery_root = (
        Path(plan_root).resolve(),
        Path(old_suffix_root).resolve(),
        Path(recovery_root).resolve(),
    )
    _need(
        plan_root.is_dir()
        and old_root.is_dir()
        and recovery_root.is_dir()
        and successor_roots,
        "collection root differs",
    )
    _predecessor_raw, predecessor = composite._predecessor(
        predecessor_path, expected_predecessor_sha256
    )
    runtime_adapter = prefix_adapter = None
    runtime_config: dict[str, Any] | None = None
    if runtime_data is None:
        _need(allow_legacy_local_v2_fixture is True, "runtime data binding is required")
        context = composite._actual_replay_context(
            suffix_root=old_root,
            plan_root=plan_root,
            expected_epoch_sha256=expected_old_epoch_sha256,
            expected_suffix_source_sha256=expected_suffix_source_sha256,
            predecessor=predecessor,
        )
    else:
        runtime_adapter, prefix_adapter, runtime_config = _runtime_data(runtime_data)
        context = runtime_adapter.build_snapshot_replay_context(
            suffix_root=old_root,
            plan_root=plan_root,
            expected_epoch_sha256=expected_old_epoch_sha256,
            expected_suffix_source_sha256=expected_suffix_source_sha256,
            predecessor=predecessor,
            snapshot_manifest_path=Path(runtime_config["snapshot_manifest"]["path"]),
            expected_snapshot_manifest_sha256=runtime_config["snapshot_manifest"][
                "sha256"
            ],
            source_bindings=runtime_config["source_bindings"],
        )
        _verify_runtime_data_sources(runtime_config)
    historical_exclusions = _historical_exclusions(predecessor)
    (
        parent,
        recovery_epoch,
        recovery_plan_root,
        requests_by_ordinal,
        _recovery_replayed,
        recovery_identities,
        recovery_owners,
        recovery_commitment,
    ) = _recovery_chain(
        root=recovery_root,
        recovery=recovery,
        expected_controller_sha256=expected_recovery_controller_sha256,
        expected_manifest_sha256=expected_recovery_manifest_sha256,
    )
    _need(
        parent.__file__ == suffix.__file__ and recovery_plan_root == plan_root,
        "recovery suffix or plan differs",
    )
    successor_runtime = (
        _v5_runtime_for_epoch(runtime_config, recovery_epoch)
        if runtime_config is not None else suffix._runtime_from_epoch(recovery_epoch)
    )
    successor_owners, successor_identities, successor_commitments = _successor_chain(
        roots=successor_roots,
        controller=controller,
        parent=suffix,
        recovery_root=recovery_root,
        recovery_epoch=recovery_epoch,
        recovery_plan_root=recovery_plan_root,
    )
    local, local_owners, local_identities, local_commitment = (None, {}, [], None)
    if local_continuation is not None:
        _need(
            candidate_native_continuation is not None
            or renewed_continuation is not None
            or parallel_continuation is not None
            or allow_legacy_local_v2_fixture is True,
            "standing v6 candidate continuation is required",
        )
        last_root, last_manifest_sha256 = _descriptor(successor_roots[-1])
        if runtime_config is not None:
            _verify_runtime_data_sources(runtime_config)
        local, local_owners, local_identities, local_commitment = _local_continuation(
            descriptor=local_continuation,
            approved_v5_routes=approved_v5_routes,
            successor_root=last_root,
            successor_manifest_sha256=last_manifest_sha256,
            include_untouched=(
                candidate_native_continuation is None
                and renewed_continuation is None
                and parallel_continuation is None
            ),
            runtime=successor_runtime if runtime_config is not None else None,
            prefix_adapter=prefix_adapter,
        )
        if runtime_config is not None:
            _verify_runtime_data_sources(runtime_config)
    candidate_owners, candidate_identities, candidate_batches, candidate_commitment = (
        {},
        [],
        {},
        None,
    )
    if candidate_native_continuation is not None:
        _need(
            local_continuation is not None,
            "standing v6 continuation requires local prefix",
        )
        (
            candidate_owners,
            candidate_identities,
            candidate_batches,
            candidate_commitment,
        ) = _candidate_native_continuation(
            descriptor=candidate_native_continuation,
            local_descriptor=local_continuation,
        )
    renewed_owners, renewed_identities, renewed_batches, renewed_commitment = (
        {},
        [],
        {},
        None,
    )
    if renewed_continuation is not None:
        _need(
            local_continuation is not None,
            "renewed continuation requires local prefix",
        )
        (
            renewed_owners,
            renewed_identities,
            renewed_batches,
            renewed_commitment,
        ) = _renewed_native_continuation(
            descriptor=renewed_continuation,
            plan_root=plan_root,
        )
    parallel_owners, parallel_identities, parallel_batches, parallel_commitment = (
        {},
        [],
        {},
        None,
    )
    if parallel_continuation is not None:
        _need(
            local_continuation is not None,
            "parallel continuation requires local prefix",
        )
        (
            parallel_owners,
            parallel_identities,
            parallel_batches,
            parallel_commitment,
        ) = _parallel_native_continuation(
            descriptor=parallel_continuation,
            plan_root=plan_root,
        )
    parallel_local_recoveries = (
        list(parallel_commitment.get("local_recoveries", []))
        if isinstance(parallel_commitment, Mapping)
        else []
    )
    parallel_local_ordinals = [item.get("ordinal") for item in parallel_local_recoveries]
    _need(
        all(type(item) is int for item in parallel_local_ordinals)
        and len(parallel_local_ordinals) == len(set(parallel_local_ordinals)),
        "parallel local recovery inventory differs",
    )
    owners = {**recovery_owners}
    _need(
        not (set(owners) & set(successor_owners)),
        "root-chain ordinal ownership collision",
    )
    owners.update(successor_owners)
    _need(
        not (set(owners) & set(local_owners)),
        "local continuation ordinal ownership collision",
    )
    owners.update(local_owners)
    _need(
        not (set(owners) & set(candidate_owners)),
        "standing v6 continuation ordinal ownership collision",
    )
    owners.update(candidate_owners)
    _need(
        not (set(owners) & set(renewed_owners)),
        "renewed continuation ordinal ownership collision",
    )
    owners.update(renewed_owners)
    _need(
        not (set(owners) & set(parallel_owners)),
        "parallel continuation ordinal ownership collision",
    )
    owners.update(parallel_owners)
    _need(set(owners) == set(SUCCESSOR_SCHEDULE), "successor chain is incomplete")
    receipt_identities = _unique(
        [
            *recovery_identities,
            *successor_identities,
            *local_identities,
            *candidate_identities,
            *renewed_identities,
            *parallel_identities,
        ]
    )
    expected_replayed_native = len(owners) - int(local is not None) - len(parallel_local_recoveries)
    _need(
        len(receipt_identities) == expected_replayed_native,
        "successor replay identity cardinality differs",
    )
    plan, _plan_raw, passes, pass_index, question_ids = composite._plan(
        plan_root, expected_plan_sha256
    )
    schedule = context.epoch["selected_request_ordinals"]
    _need(
        schedule
        == [
            item["ordinal"]
            for item in plan["requests"]
            if item.get("ordinal") in schedule
        ]
        and schedule == [*range(1, 1611), *range(4049, 4739)]
        and len(schedule) == LOGICAL_COUNT,
        "selected request schedule differs",
    )
    records_by_pass = {item["pass_id"]: item for item in passes}
    selected_ids = {
        request["pass_id"]
        for request in plan["requests"]
        if request.get("ordinal") in schedule
    }
    selected = [
        records_by_pass[item["pass_id"]]
        for item in plan["passes"]
        if item.get("pass_id") in selected_ids
    ]
    _need(len(selected) == STORY_COUNT, "selected pass inventory differs")
    runtime = (
        context.suffix_runtime
        if runtime_config is not None
        else context.suffix._runtime_from_epoch(context.epoch)
    )
    _need(
        successor_runtime.transport_sha256 == runtime.transport_sha256,
        "recovery runtime transport differs",
    )
    identities: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    for record in selected[:3]:
        run_root = next(
            item["run_root"]
            for item in context.old_passes
            if item["pass_id"] == record["pass_id"]
        )
        if runtime_config is not None:
            _verify_runtime_data_sources(runtime_config)
        replay = (
            runtime_adapter.admit_old_with_runtime_data(
                context,
                plan_root=plan_root,
                pass_record=record,
                run_root=Path(run_root),
                approved_v4_routes=approved_v4_routes,
            )
            if runtime_config is not None
            else composite._actual_old_admit(
                context,
                plan_root=plan_root,
                pass_record=record,
                run_root=Path(run_root),
                approved_v4_routes=approved_v4_routes,
            )
        )
        if runtime_config is not None:
            _verify_runtime_data_sources(runtime_config)
        verdicts = _verdicts(replay.get("verdicts"), question_ids, "old prefix")
        identities.extend(
            _identity(item, "old prefix")
            for item in replay.get("native_identities", [])
        )
        ordinals = [
            item["ordinal"]
            for item in plan["requests"]
            if item.get("pass_id") == record["pass_id"]
        ]
        rows.append(
            _record(
                record=record,
                ordinals=ordinals,
                verdicts=verdicts,
                runtime=runtime,
                provenance={"kind": "original_v4_prefix"},
                replay_input_commitments={
                    "run_manifest_sha256": replay["run_manifest_sha256"],
                    "checkpoint_head_sha256": replay["checkpoint_head_sha256"],
                },
            )
        )
    mixed = selected[3]
    recovered = (
        _module(
            Path(runtime_config["source_bindings"]["recovered_data_admission"]["path"]),
            runtime_config["source_bindings"]["recovered_data_admission"]["sha256"],
            "recovered data admission",
        )
        if runtime_config is not None
        else composite._load_module(
            Path(context.epoch["recovered_study_source"]["path"]),
            context.epoch["recovered_study_source"]["sha256"],
            "recovered study",
        )
    )
    if runtime_config is not None:
        _verify_runtime_data_sources(runtime_config)
    prefix = (
        recovered.admit_prefix_with_runtime_data(
            context.epoch["old_prefix_run_root"],
            source=composite._measurement_source(plan_root, mixed),
            batch_size=8,
            approved_routes=dict(approved_v4_routes),
            expected_batches=11,
            expected_recovered_manifest_sha256=context.epoch[
                "recovered_study_manifest"
            ]["sha256"],
            expected_adoption_sha256=context.epoch["recovery_adoption_sha256"],
            expected_amendment_sha256=context.epoch["recovery_amendment_sha256"],
            runtime=context.old_runtime,
            snapshot_descriptor=context.old_snapshot_descriptor,
        )
        if runtime_config is not None
        else recovered.admit_prefix(
            context.epoch["old_prefix_run_root"],
            source=composite._measurement_source(plan_root, mixed),
            batch_size=8,
            approved_routes=dict(approved_v4_routes),
            expected_batches=11,
            expected_recovered_manifest_sha256=context.epoch[
                "recovered_study_manifest"
            ]["sha256"],
            expected_adoption_sha256=context.epoch["recovery_adoption_sha256"],
            expected_amendment_sha256=context.epoch["recovery_amendment_sha256"],
            runtime=context.old_runtime,
        )
    )
    if runtime_config is not None:
        _verify_runtime_data_sources(runtime_config)
    mixed_verdicts = list(prefix["verdicts"])
    identities.extend(
        _identity(item, "mixed prefix") for item in prefix["native_identities"]
    )
    terminals: list[dict[str, Any]] = []
    for ordinal in range(81, 93):
        request = requests_by_ordinal[ordinal]
        if ordinal in OLD_V5_ORDINALS:
            owner = {
                "kind": "old_v5",
                "root": str(old_root),
                "epoch_sha256": expected_old_epoch_sha256,
            }
            epoch, replay_runtime = context.epoch, runtime
        else:
            owner = _owner(owners, ordinal)
            epoch, replay_runtime = recovery_epoch, successor_runtime
        batch, identity = suffix._replay_suffix_terminal(
            root=Path(owner["root"]),
            epoch_sha256=owner["epoch_sha256"],
            epoch=epoch,
            runtime=replay_runtime,
            plan_root=plan_root,
            passed=pass_index[request["pass_id"]],
            row=request,
            approved_v5_routes=approved_v5_routes,
        )
        mixed_verdicts.extend(batch)
        identities.append(_identity(identity, "mixed suffix"))
        terminals.append(_terminal_commitment(suffix, owner, ordinal))
    rows.append(
        _record(
            record=mixed,
            ordinals=list(range(70, 93)),
            verdicts=_verdicts(mixed_verdicts, question_ids, "mixed pass"),
            runtime=runtime,
            provenance={"kind": "v4_recovered70_old_v5_successor_replacements"},
            replay_input_commitments={
                "prefix_run_manifest_sha256": prefix["run_manifest_sha256"],
                "prefix_checkpoint_head_sha256": prefix["checkpoint_head_sha256"],
                "recovered_manifest_sha256": prefix["recovered_manifest_sha256"],
                "terminals": terminals,
            },
        )
    )
    native_batches = {**candidate_batches, **renewed_batches, **parallel_batches}
    parallel_local_by_ordinal = {
        item["ordinal"]: item for item in parallel_local_recoveries
    }
    for record in selected[4:]:
        verdicts: list[dict[str, Any]] = []
        terminals = []
        requests = sorted(
            (
                item
                for item in plan["requests"]
                if item.get("pass_id") == record["pass_id"]
            ),
            key=lambda item: item["ordinal"],
        )
        for request in requests:
            ordinal = request["ordinal"]
            owner = _owner(owners, ordinal)
            if owner["kind"] == "local_schema_recovery":
                _need(
                    local is not None
                    and ordinal == local["ordinal"]
                    and [item.get("question_id") for item in local["verdicts"]]
                    == request["question_ids"],
                    "local projection request binding differs",
                )
                verdicts.extend(local["verdicts"])
                terminals.append(
                    {
                        "ordinal": ordinal,
                        "owner": owner,
                        "local_identity": local["local_identity"],
                    }
                )
                continue
            if owner["kind"] == "parallel_local_recovery":
                local370 = parallel_local_by_ordinal.get(ordinal)
                _need(
                    ordinal == 370
                    and isinstance(local370, Mapping)
                    and local370.get("ordinary_native_admission") is False
                    and [item.get("question_id") for item in local370.get("verdicts", [])]
                    == request["question_ids"],
                    "parallel local recovery request binding differs",
                )
                verdicts.extend(local370["verdicts"])
                terminals.append(
                    {
                        "ordinal": ordinal,
                        "owner": owner,
                        "local_identity": local370["local_identity"],
                    }
                )
                continue
            if owner["kind"] in {
                "standing_v6_runtime_data_original_native",
                "standing_v6_runtime_data_recovered_native",
                "standing_v6_runtime_data_successor_native",
                "standing_v6_renewed_successor_native",
                "parallel_renewal_native",
            }:
                batch = native_batches.get(ordinal)
                _need(
                    isinstance(batch, list)
                    and [item.get("question_id") for item in batch]
                    == request["question_ids"],
                    "successor native request binding differs",
                )
                verdicts.extend(batch)
                identities.append(
                    _identity(owner["native_identity"], "runtime data successor")
                )
                terminals.append(
                    {
                        "ordinal": ordinal,
                        "owner": owner,
                        "terminal_sha256": owner["terminal_sha256"],
                    }
                )
                continue
            batch, identity = suffix._replay_suffix_terminal(
                root=Path(owner["root"]),
                epoch_sha256=owner["epoch_sha256"],
                epoch=recovery_epoch,
                runtime=successor_runtime,
                plan_root=plan_root,
                passed=pass_index[record["pass_id"]],
                row=request,
                approved_v5_routes=approved_v5_routes,
            )
            verdicts.extend(batch)
            identities.append(_identity(identity, "successor suffix"))
            terminals.append(_terminal_commitment(suffix, owner, ordinal))
        rows.append(
            _record(
                record=record,
                ordinals=[item["ordinal"] for item in requests],
                verdicts=_verdicts(verdicts, question_ids, "successor pass"),
                runtime=successor_runtime,
                provenance={
                    "kind": "root_chain",
                    "owners": [_owner(owners, item["ordinal"]) for item in requests],
                },
                replay_input_commitments={"terminals": terminals},
            )
        )
    all_identities = _unique(identities)
    _need(len(rows) == STORY_COUNT, "collection story cardinality differs")
    expected_native_count = (
        NATIVE_COUNT - int(local is not None) - len(parallel_local_recoveries)
    )
    _need(
        len(all_identities) == expected_native_count,
        "collection native identity cardinality differs",
    )
    _need(
        len(receipt_identities) == expected_replayed_native,
        "replay receipt identity cardinality differs",
    )
    actual_pairs = sorted(
        (item["request_id_hash"], item["session_id_hash"]) for item in all_identities
    )
    receipt_pairs = sorted(
        (item["request_id_hash"], item["session_id_hash"])
        for item in receipt_identities
    )
    _need(set(receipt_pairs).issubset(actual_pairs), "semantic replay identity differs")
    _need(
        not (
            {item["request_id_hash"] for item in all_identities}
            & {item["request_id_hash"] for item in historical_exclusions}
        )
        and not (
            {item["session_id_hash"] for item in all_identities}
            & {item["session_id_hash"] for item in historical_exclusions}
        ),
        "historical native identity collision",
    )
    normalized_verdict_rows = [
        {
            "pass_id": row["pass_id"],
            "opaque_story_id": row["opaque_story_id"],
            **verdict,
        }
        for row in rows
        for verdict in row["verdict_rows"]
    ]
    _need(
        len(normalized_verdict_rows) == VERDICT_COUNT,
        "collection verdict cardinality differs",
    )
    runtime_provenance = runtime_protected_paths = None
    if runtime_config is not None:
        context.old_runtime.verify()
        context.suffix_runtime.verify()
        successor_runtime.verify()
        _verify_runtime_data_sources(runtime_config)
        runtime_protected_paths = _runtime_data_protected_paths(
            context=context,
            runtime_config=runtime_config,
            recovery_root=recovery_root,
            recovery_commitment=recovery_commitment,
            recovery_runtime=successor_runtime,
        )
        runtime_provenance = {
            "config": dict(runtime_data),
            "old_runtime": dict(context.old_runtime.provenance),
            "suffix_runtime": dict(context.suffix_runtime.provenance),
            "recovery_runtime": dict(successor_runtime.provenance),
            "old_snapshot_descriptor": dict(context.old_snapshot_descriptor),
            "suffix_snapshot_descriptor": dict(context.suffix_snapshot_descriptor),
        }
    _need(Path(__file__).read_bytes() == reader_raw, "collection reader source drifted")
    root_descriptors = [
        {"root": str(_descriptor(item)[0]), "manifest_sha256": _descriptor(item)[1]}
        for item in successor_roots
    ]
    coverage_failures = [row["pass_id"] for row in rows if row["coverage"] < 0.88]
    result = {
        "schema_version": (
            6
            if parallel_local_recoveries
            else (
                1
                if local is None
                else (
                    4
                    if renewed_commitment is not None
                    else (
                        5
                        if parallel_commitment is not None
                        else (3 if candidate_commitment is not None else 2)
                    )
                )
            )
        ),
        "evidence_class": "selected100_grok_successor_collection_replay_only_v1"
        if local is None
        else (
            "selected100_grok_successor_renewed_replay_only_v4"
            if renewed_commitment is not None
            else (
                "selected100_grok_successor_parallel_local_replay_only_v6"
                if parallel_local_recoveries
                else (
                    "selected100_grok_successor_parallel_replay_only_v5"
                    if parallel_commitment is not None
                    else (
                        "selected100_grok_successor_standing_v6_candidate_replay_only_v3"
                        if candidate_commitment is not None
                        else "selected100_grok_successor_local_schema_recovery_replay_only_v2"
                    )
                )
            )
        ),
        "counts": {
            "stories": STORY_COUNT,
            "logical_requests": LOGICAL_COUNT,
            "native_requests": expected_native_count,
            "study_recovered_requests": 1,
            "criterion_verdicts": VERDICT_COUNT,
        },
        "input_commitments": {
            "reader_sha256": _sha(reader_raw),
            "plan_sha256": expected_plan_sha256,
            "predecessor_sha256": expected_predecessor_sha256,
            "old_suffix_epoch_sha256": expected_old_epoch_sha256,
            "selected_schedule_sha256": context.epoch["selected_schedule"]["sha256"],
            "selected_schedule_source_sha256": context.epoch[
                "selected_schedule_source"
            ]["sha256"],
            "composite_helper_sha256": COMPOSITE_SHA256,
            "suffix_helper_sha256": SUFFIX_SHA256,
            "recovery_controller_sha256": RECOVERY_SHA256,
            "recovery_manifest_sha256": recovery_commitment["manifest_sha256"],
            "successor_controller_sha256": SUCCESSOR_SHA256,
            "successor_root_chain_sha256": _sha(_canonical(root_descriptors)),
            "root_chain": [recovery_commitment, *successor_commitments],
        },
        "successor_root_chain": root_descriptors,
        "recovered_ordinals": [
            RECOVERED_ORDINAL,
            *([254] if local is not None else []),
            *parallel_local_ordinals,
        ],
        "root_chain_ordinal_owners": dict(sorted(owners.items())),
        "root_chain_native_identities": receipt_identities,
        "historical_excluded_native_identities": historical_exclusions,
        "native_identities": all_identities,
        "native_identity_commitment_sha256": _sha(_canonical(all_identities)),
        "rows": rows,
        "normalized_verdict_rows": normalized_verdict_rows,
        "coverage_failures": coverage_failures,
        "full_study_admitted": False,
        "authority": False,
        "provider_calls_made": 0,
        "historical_prototype_only": local is None
        or (
            candidate_commitment is None
            and renewed_commitment is None
            and parallel_commitment is None
        ),
    }
    if runtime_provenance is not None:
        result["runtime_data_provenance"] = runtime_provenance
        result["runtime_data_protected_paths"] = runtime_protected_paths
        config_sha256 = _sha(_canonical(runtime_data))
        result["input_commitments"]["runtime_data_config_sha256"] = config_sha256
        result["source_commitments"] = {"runtime_data_config_sha256": config_sha256}
    if local is not None:
        _need(
            local_continuation is not None and local_commitment is not None,
            "local continuation result differs",
        )
        result["counts"]["local_recovered_requests"] = 1
        result["input_commitments"].update(
            {
                "local_continuation_manifest_sha256": local_commitment[
                    "manifest_sha256"
                ],
                "local_continuation_controller_sha256": local_commitment[
                    "controller_sha256"
                ],
                "local_continuation_descriptor_sha256": _sha(
                    _canonical(dict(local_continuation))
                ),
                "local_recovery_identity_sha256": local["local_identity"][
                    "identity_sha256"
                ],
            }
        )
        result["local_continuation"] = dict(local_continuation)
        result["local_continuation_commitment"] = local_commitment
        result["local_recovery_identity"] = dict(local["local_identity"])
        result["local_recovery_provenance"] = dict(local["local_provenance"])
        result["local_recovery_protected_paths"] = dict(
            local_commitment["protected_paths"]
        )
    if candidate_commitment is not None:
        _need(
            candidate_native_continuation is not None,
            "standing v6 continuation descriptor differs",
        )
        result["input_commitments"].update(
            {
                "standing_v6_continuation_manifest_sha256": candidate_commitment[
                    "manifest_sha256"
                ],
                "standing_v6_continuation_controller_sha256": candidate_commitment[
                    "controller_sha256"
                ],
                "standing_v6_continuation_descriptor_sha256": _sha(
                    _canonical(dict(candidate_native_continuation))
                ),
                "standing_v6_candidate_native_identity_commitment_sha256": candidate_commitment[
                    "native_identity_commitment_sha256"
                ],
            }
        )
        result["candidate_native_continuation"] = dict(candidate_native_continuation)
        result["standing_v6_candidate_commitment"] = candidate_commitment
        result["standing_v6_candidate_protected_paths"] = dict(
            candidate_commitment["protected_paths"]
        )
    if renewed_commitment is not None:
        _need(
            renewed_continuation is not None,
            "renewed continuation descriptor differs",
        )
        renewed_descriptor = dict(renewed_commitment["source_epoch"])
        renewed_commitment_sha256 = _sha(_canonical(renewed_commitment))
        result["input_commitments"].update(
            {
                "renewed_continuation_manifest_sha256": renewed_commitment[
                    "manifest_sha256"
                ],
                "renewed_continuation_controller_sha256": renewed_commitment[
                    "controller_sha256"
                ],
                "renewed_continuation_descriptor_sha256": _sha(
                    _canonical(dict(renewed_continuation))
                ),
                "renewed_source_epoch": renewed_descriptor,
                "renewed_successor_commitment_sha256": renewed_commitment_sha256,
            }
        )
        result["renewed_continuation"] = dict(renewed_continuation)
        result["renewed_source_epoch"] = renewed_descriptor
        result["renewed_successor_commitment"] = dict(renewed_commitment)
        result["renewed_successor_protected_paths"] = dict(
            renewed_commitment["protected_paths"]
        )
        result.setdefault("source_commitments", {})[
            "renewed_successor_commitment_sha256"
        ] = renewed_commitment_sha256
    if parallel_commitment is not None:
        _need(
            parallel_continuation is not None,
            "parallel continuation descriptor differs",
        )
        parallel_epoch = dict(parallel_commitment["source_epoch"])
        parallel_commitment_sha256 = _sha(_canonical(parallel_commitment))
        result["input_commitments"].update(
            {
                "parallel_continuation_manifest_sha256": parallel_commitment[
                    "manifest_sha256"
                ],
                "parallel_continuation_controller_sha256": parallel_commitment[
                    "controller_sha256"
                ],
                "parallel_continuation_descriptor_sha256": _sha(
                    _canonical(dict(parallel_continuation))
                ),
                "parallel_source_epoch": parallel_epoch,
                "parallel_successor_commitment_sha256": parallel_commitment_sha256,
            }
        )
        result["parallel_continuation"] = dict(parallel_continuation)
        result["parallel_source_epoch"] = parallel_epoch
        result["parallel_successor_commitment"] = dict(parallel_commitment)
        result["parallel_successor_protected_paths"] = dict(
            parallel_commitment["protected_paths"]
        )
        result.setdefault("source_commitments", {})[
            "parallel_successor_commitment_sha256"
        ] = parallel_commitment_sha256
        if parallel_local_recoveries:
            local_recovery_sha256 = _sha(_canonical(parallel_local_recoveries))
            result["counts"]["local_recovered_requests"] = (
                result["counts"].get("local_recovered_requests", 0)
                + len(parallel_local_recoveries)
            )
            result["counts"]["parallel_local_recovered_requests"] = len(
                parallel_local_recoveries
            )
            result["parallel_local_recoveries"] = [
                dict(item) for item in parallel_local_recoveries
            ]
            result["input_commitments"].update(
                {
                    "parallel_local_recovery_ordinals": list(parallel_local_ordinals),
                    "parallel_local_recoveries_sha256": local_recovery_sha256,
                    "parallel_local_recovery_adoption_sha256": parallel_local_recoveries[0][
                        "adoption"
                    ]["sha256"]
                    if len(parallel_local_recoveries) == 1
                    else [item["adoption"]["sha256"] for item in parallel_local_recoveries],
                }
            )
            result.setdefault("source_commitments", {})[
                "parallel_local_recoveries_sha256"
            ] = local_recovery_sha256
    return result
