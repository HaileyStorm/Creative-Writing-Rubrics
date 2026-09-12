"""Provider-free explicit-runtime verification for the adopted local prefix."""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
E33_PATH = ROOT / "baseline_grok_selected_local_continuation.py"
E33_SHA256 = "e33e5c9276cdcdcdf22f4182787fae97d3a9f6315b6ff1dbac66f29148731e7a"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _load_e33() -> ModuleType:
    raw = E33_PATH.read_bytes()
    _need(_sha(raw) == E33_SHA256 and E33_PATH.read_bytes() == raw, "e33 source differs")
    spec = importlib.util.spec_from_file_location("dryad_e33_runtime_prefix", E33_PATH)
    _need(spec is not None and spec.loader is not None, "e33 source cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _need(E33_PATH.read_bytes() == raw, "e33 source changed while loading")
    return module


def _verify_runtime(runtime: Any, stage: str) -> None:
    verify = getattr(runtime, "verify", None)
    _need(callable(verify), "explicit runtime verifier differs")
    try:
        verify()
    except Exception as error:
        raise ValueError(f"explicit runtime verification failed {stage}") from error


def _provenance(*, runtime_verified_before: bool, runtime_verified_after: bool) -> dict[str, Any]:
    return {"kind": "dryad_explicit_runtime_data_prefix_v1", "adapter": {"path": str(Path(__file__).resolve()), "sha256": _sha(Path(__file__).read_bytes())},
            "e33": {"path": str(E33_PATH), "sha256": E33_SHA256},
            "runtime_verified_before": runtime_verified_before, "runtime_verified_after": runtime_verified_after,
            "provider_calls_made": 0}


def _local_context(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str,
                   runtime: Any) -> tuple[ModuleType, Path, Mapping[str, Any], bytes, Any, Path, Mapping[int, Any], Mapping[str, Any], Mapping[str, Any]]:
    e33 = _load_e33()
    root = Path(continuation_root).resolve()
    manifest, raw = e33._manifest(root, expected_manifest_sha256)
    _need(expected_controller_sha256 == manifest["controller_sha256"] == E33_SHA256, "local controller pin differs")
    _successor, parent, _source_manifest, _epoch_raw, plan_root, requests, partial = e33._source_guard(manifest)
    return e33, root, manifest, raw, parent, plan_root, requests, partial, runtime


def verify_local_continuation_with_runtime(*, continuation_root: Path, expected_manifest_sha256: str,
                                           expected_controller_sha256: str, runtime: Any) -> dict[str, Any]:
    """Verify the local 254 projection using the supplied runtime instance."""
    _verify_runtime(runtime, "before")
    e33, root, manifest, raw, parent, plan_root, requests, partial, runtime = _local_context(
        continuation_root=continuation_root, expected_manifest_sha256=expected_manifest_sha256,
        expected_controller_sha256=expected_controller_sha256, runtime=runtime)
    proposal = e33._proposal(Path(manifest["proposal"]["path"]), manifest["proposal"]["sha256"])
    adoption = e33._adoption(Path(manifest["adoption"]["path"]), manifest["adoption"]["sha256"], e33._sha(e33._canon(proposal)))
    review = e33._review(Path(manifest["independent_review"]["path"]), manifest["independent_review"]["sha256"], proposal)
    standing = e33._standing(Path(manifest["standing_authority"]["path"]), manifest["standing_authority"]["sha256"], proposal)
    projection = e33._project(e33._retained_answer(proposal), proposal)
    projection_path = Path(manifest["local_projection"]["path"])
    _need(projection_path.read_bytes() == e33._canon(projection)
          and e33._sha(projection_path.read_bytes()) == manifest["local_projection"]["sha256"], "stored local projection differs")
    protected = e33._protected_identities(manifest)
    epoch, epoch_raw = parent._load_epoch(Path(manifest["successor_root"]), manifest["inner_epoch"]["sha256"])
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]
    row = requests[e33.LOCAL_ORDINAL]
    passed = parent._pass_index(plan)[row["pass_id"]]
    source = parent._source_for_pass(plan_root, passed)
    normalized = runtime.runner._normalize_batch(
        projection, expected_ids=row["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story",
        judge_id="grok:grok-4.6", run_id="dryad-local-schema-projection/0254", artifact_text=source["story_text"],
        context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
    _need([item["question_id"] for item in normalized] == row["question_ids"] and len(normalized) == 8
          and partial["failed_attempts"][0]["question_ids"] == row["question_ids"], "local projection verdict coverage differs")
    peer_records = [dict(item) for item in partial["records"]]
    _need([item.get("ordinal") for item in peer_records] == partial["completed_ordinals"]
          and all(item.get("native_identity") in protected for item in peer_records), "partial peer ownership differs")
    e33._identity([item["native_identity"] for item in peer_records])
    local_identity = {"kind": "local_schema_projection", "ordinal": e33.LOCAL_ORDINAL,
                      "projection_sha256": e33.PROJECTED_SHA,
                      "identity_sha256": e33._sha(e33._canon({"kind": "local_schema_projection", "ordinal": e33.LOCAL_ORDINAL,
                                                                  "projection_sha256": e33.PROJECTED_SHA}))}
    _verify_runtime(runtime, "after")
    return {"ordinal": e33.LOCAL_ORDINAL, "evidence_class": adoption["evidence_class"], "verdicts": normalized,
            "local_identity": local_identity,
            "local_provenance": {"proposal_sha256": manifest["proposal"]["sha256"], "adoption_sha256": manifest["adoption"]["sha256"],
                                 "independent_review_sha256": manifest["independent_review"]["sha256"], "standing_authority_sha256": manifest["standing_authority"]["sha256"],
                                 "original_message_sha256": e33.ORIGINAL_SHA, "projected_message_sha256": e33.PROJECTED_SHA,
                                 "source_story_sha256": e33.SOURCE_STORY_SHA, "ordinary_native_admission": False,
                                 "new_provider_attempts_authorized": 0},
            "ownership": dict(manifest["ownership"]),
            "source": {"root": str(root), "manifest_sha256": e33._sha(raw), "controller_sha256": manifest["controller_sha256"],
                       "successor_root": manifest["successor_root"], "successor_manifest_sha256": manifest["successor_manifest_sha256"],
                       "partial_sha256": manifest["partial"]["sha256"], "inner_epoch_sha256": e33._sha(epoch_raw)},
            "protected_paths": {"continuation_root": {"path": str(root), "inventory_sha256": e33._sha(e33._canon(e33._inventory(root)))},
                                "continuation_manifest": {"path": str(root / "local-continuation-manifest.json"), "sha256": e33._sha(raw)},
                                "controller": {"path": str(E33_PATH), "sha256": manifest["controller_sha256"]},
                                "successor_root": {"path": manifest["successor_root"], "inventory_sha256": manifest["successor_inventory"]["sha256"]},
                                "successor_manifest": {"path": str(Path(manifest["successor_root"]) / "successor-manifest.json"), "sha256": manifest["successor_manifest_sha256"]},
                                "partial": dict(manifest["partial"]), "proposal": dict(manifest["proposal"]), "adoption": dict(manifest["adoption"]),
                                "independent_review": dict(manifest["independent_review"]), "standing_authority": dict(manifest["standing_authority"]),
                                "local_projection": dict(manifest["local_projection"]), "protected_native_identities": dict(manifest["protected_native_identities"]),
                                "inner_epoch": dict(manifest["inner_epoch"])},
            "partial_peer_records": peer_records,
            "partial_peer_source": {"root": manifest["successor_root"], "successor_manifest_sha256": manifest["successor_manifest_sha256"],
                                    "inner_epoch_sha256": manifest["inner_epoch"]["sha256"], "partial": dict(manifest["partial"])},
            "provider_calls_made": 0, "full_original_study_admitted": False, "review_decision": review["decision"],
            "standing_authority_kind": standing["kind"], "verifier_provenance": _provenance(runtime_verified_before=True, runtime_verified_after=True)}


def verify_untouched_replay_chain_with_runtime(*, continuation_root: Path, expected_manifest_sha256: str,
                                               expected_controller_sha256: str, runtime: Any,
                                               approved_v5_routes: Mapping[str, Any]) -> dict[str, Any]:
    """Replay retained local terminals through the supplied runtime without creating one."""
    _verify_runtime(runtime, "before")
    e33, root, manifest, raw, parent, plan_root, requests, _partial, runtime = _local_context(
        continuation_root=continuation_root, expected_manifest_sha256=expected_manifest_sha256,
        expected_controller_sha256=expected_controller_sha256, runtime=runtime)
    replayed, native_identities = e33._replayed(root, parent, manifest, raw)
    epoch, _epoch_raw = parent._load_epoch(Path(manifest["successor_root"]), manifest["inner_epoch"]["sha256"])
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]
    passes = parent._pass_index(plan)
    terminals: list[dict[str, Any]] = []
    replay_paths = sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else []
    for path in replay_paths:
        record = e33._json(path, "local replay record")
        for ordinal, terminal in zip(record["ordinals"], record["terminals"], strict=True):
            row = requests[ordinal]
            verdicts, identity = parent._replay_suffix_terminal(
                root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, runtime=runtime,
                plan_root=plan_root, passed=passes[row["pass_id"]], row=row, approved_v5_routes=approved_v5_routes)
            _need(verdicts and identity in record["native_identities"]
                  and terminal["terminal_sha256"] == e33._sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()),
                  "local replay semantic verification differs")
            terminals.append(dict(terminal))
    _need([item["ordinal"] for item in terminals] == sorted(replayed), "local replay terminal ownership differs")
    e33._identity(native_identities)
    _verify_runtime(runtime, "after")
    return {"untouched_replay_ordinals": sorted(replayed), "untouched_native_identities": native_identities,
            "untouched_terminals": terminals, "provider_calls_made": 0, "protected_native_identity_count": 259,
            "verifier_provenance": _provenance(runtime_verified_before=True, runtime_verified_after=True)}
