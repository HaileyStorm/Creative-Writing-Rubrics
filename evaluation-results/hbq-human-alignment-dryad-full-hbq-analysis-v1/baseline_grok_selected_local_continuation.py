"""Schema-3 local continuation for the retained Dryad request 254 answer.

This controller records a bounded local projection.  It does not turn that
projection into a native Grok result and it never authorizes a resend of 254.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PARENT = ROOT / "baseline_grok_v5_suffix.py"
SUCCESSOR = ROOT / "baseline_grok_selected_successor.py"
PARENT_SHA = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
SUCCESSOR_SHA = "fc0dbe04b3699522271157a87fc2f5a5659ffc108bd7eb3a68d6bf393e49bac8"
PARTIAL_SHA = "889429a738d3b7724abc7652518d5fab46041b5db4db1c4fb3ae9db85752a1e2"
PROPOSAL_SHA = "a00f74e15c7acf2904e3b5ce859b086dd9d3bf254051f576b99261ff1393c650"
ADOPTION_SHA = "62eb162e148df15dd992e71952cd05a702c018163ec6759cb4ff508743ce1e8c"
REVIEW_SHA = "516e3d197bdaa6b65b62e26726eaa7b91af2f669b66b45792e0251c43640d221"
STANDING_SHA = "58c76458cac9285e5be9c766ba62ea393198687ac660bf963c58a9cdcdf11e9e"
SOURCE_STORY_SHA = "5b679cb359eff67d6e5a8f8655982dce67979e152414b0ff58f391be4e3000eb"
ORIGINAL_SHA = "f1c8357431193805c0e54e3ec7b2c19dab707871d32e093e89b5e79a718f10ff"
PROJECTED_SHA = "0ae9213b33a51315f082f9091fe40601f21efbdc32475d8010956d9cd8ee716b"
MAX_WAVE = 10
LOCAL_ORDINAL = 254
PENDING = [*range(262, 1611), *range(4049, 4739)]
_HASH = re.compile(r"[0-9a-f]{64}")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object")
    return value


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _load(path: Path, expected: str, label: str) -> Any:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, f"{label} differs")
    spec = importlib.util.spec_from_file_location(f"_dryad_local_{label}", path)
    _need(spec is not None and spec.loader is not None, f"{label} load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _need(path.read_bytes() == raw, f"{label} changed")
    return module


def _inventory(root: Path) -> dict[str, str]:
    _need(root.is_dir() and not root.is_symlink(), "source root differs")
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        _need(not path.is_symlink(), "source root contains link")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
    return dict(sorted(result.items()))


def _identity(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = [dict(item) for item in values if isinstance(item, Mapping)]
    _need(len(result) == len(values) and all(set(item) == {"request_id_hash", "session_id_hash"} for item in result), "native identities differ")
    request_ids = [item["request_id_hash"] for item in result]
    session_ids = [item["session_id_hash"] for item in result]
    _need(all(isinstance(item, str) and _HASH.fullmatch(item) for item in request_ids + session_ids)
          and len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "native identity collision")
    return result


def _identity_file(path: Path) -> list[dict[str, str]]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("protected native identities malformed") from error
    _need(isinstance(value, list), "protected native identities differ")
    return _identity(value)


def _protected_identities(manifest: Mapping[str, Any]) -> list[dict[str, str]]:
    descriptor = manifest["protected_native_identities"]
    _need(isinstance(descriptor, Mapping), "protected native identity descriptor differs")
    identities = _identity_file(Path(descriptor["path"]))
    commitment = _sha(_canon(identities))
    _need(descriptor.get("count") == len(identities) == 259 and descriptor.get("sha256") == commitment
          and descriptor.get("commitment_sha256") == commitment, "protected native identities changed")
    return identities


def _time(value: Any, label: str) -> datetime:
    _need(isinstance(value, str), f"{label} differs")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _need(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _source_file(path: Path, expected: str, label: str) -> bytes:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, f"{label} differs")
    return raw


def _proposal(path: Path, expected: str) -> dict[str, Any]:
    value = _json(path, "local projection proposal")
    raw = _source_file(path, expected, "local projection proposal")
    required = {
        "all_other_values_unchanged", "attestation_time_basis", "authorizes_new_attempt", "changes",
        "exact_question_id_order_preserved", "kind", "local_summary_request_id_sha256", "native_cli_envelope_binding",
        "ordinal", "ordinary_native_admission", "original_message_sha256", "original_outcome_preserved",
        "process_exit_code", "projected_message_sha256", "provider_calls_made", "provider_identity_attested",
        "result_promotion_authority", "retained_message_matches_update", "schema_sha256", "schema_version",
        "session_attestation_sha256", "session_id_sha256", "source_artifact_sha256", "source_bindings", "status",
    }
    _need(_sha(raw) == expected == PROPOSAL_SHA and set(value) == required and value.get("schema_version") == 1
          and value.get("kind") == "dryad254_local_session_quote_projection_proposal" and value.get("ordinal") == LOCAL_ORDINAL
          and value.get("original_message_sha256") == ORIGINAL_SHA and value.get("projected_message_sha256") == PROJECTED_SHA
          and value.get("source_artifact_sha256") == SOURCE_STORY_SHA and value.get("provider_calls_made") == 0
          and value.get("authorizes_new_attempt") is False and value.get("ordinary_native_admission") is False
          and value.get("all_other_values_unchanged") is True and value.get("exact_question_id_order_preserved") is True
          and isinstance(value.get("changes"), list) and value["changes"] == [{"operation": "retain_first_500_characters", "original_characters": 579, "original_quote_is_exact_full_source": True, "path": "verdicts[3].evidence[0].exact_quote", "projected_characters": 500}]
          and isinstance(value.get("source_bindings"), Mapping) and len(value["source_bindings"]) == 11,
          "local projection proposal differs")
    for raw_path, source_hash in value["source_bindings"].items():
        _need(isinstance(raw_path, str) and isinstance(source_hash, str) and _HASH.fullmatch(source_hash), "proposal source binding differs")
        _source_file(Path(raw_path), source_hash, "proposal source")
    return value


def _adoption(path: Path, expected: str, proposal_sha256: str) -> dict[str, Any]:
    value = _json(path, "local projection adoption")
    raw = _source_file(path, expected, "local projection adoption")
    required = {"schema_version", "kind", "decision", "ordinal", "proposal_sha256", "independent_projection_review_sha256",
                "standing_authority_provenance_sha256", "authority_basis", "original_message_sha256", "projected_message_sha256",
                "projection", "original_quote_equals_frozen_source", "all_eight_verdicts_and_question_ids_unchanged",
                "original_failed_attempt_preserved", "evidence_class", "ordinary_native_admission", "new_provider_attempts_authorized",
                "full_collection_accounting", "coverage_floor", "coverage_waiver", "full_original_study_admitted"}
    _need(_sha(raw) == expected == ADOPTION_SHA and set(value) == required and value.get("schema_version") == 1
          and value.get("kind") == "dryad254_local_session_quote_projection_adoption" and value.get("ordinal") == LOCAL_ORDINAL
          and value.get("decision") == "adopt_exact_independently_reviewed_local_schema_projection" and value.get("proposal_sha256") == proposal_sha256
          and value.get("independent_projection_review_sha256") == REVIEW_SHA and value.get("standing_authority_provenance_sha256") == STANDING_SHA
          and value.get("original_message_sha256") == ORIGINAL_SHA and value.get("projected_message_sha256") == PROJECTED_SHA
          and value.get("original_quote_equals_frozen_source") is True and value.get("all_eight_verdicts_and_question_ids_unchanged") is True
          and value.get("original_failed_attempt_preserved") is True and value.get("ordinary_native_admission") is False
          and value.get("new_provider_attempts_authorized") == 0 and value.get("coverage_waiver") is False
          and value.get("full_original_study_admitted") is False and value.get("full_collection_accounting") == {"logical_requests": 2300, "native_results": 2298, "local_recovery_ordinals": [70, 254]},
          "local projection adoption differs")
    return value


def _review(path: Path, expected: str, proposal: Mapping[str, Any]) -> dict[str, Any]:
    value = _json(path, "local projection independent review")
    raw = _source_file(path, expected, "local projection independent review")
    required = {"all_11_source_hashes_verified", "decision", "full_study_admitted", "kind", "ordinary_native_admission",
                "proposal_sha256", "question_id_order_verified", "resend_authority", "reviewer", "schema_version",
                "session_attestation_sha256", "sole_change", "source_quote_grounding_verified"}
    _need(_sha(raw) == expected == REVIEW_SHA and set(value) == required and value.get("schema_version") == 1
          and value.get("decision") == "GO_for_explicit_LOCAL_schema_recovered_adoption" and value.get("proposal_sha256") == _sha(_canon(dict(proposal)))
          and value.get("all_11_source_hashes_verified") is True and value.get("question_id_order_verified") is True
          and value.get("source_quote_grounding_verified") is True and value.get("resend_authority") is False
          and value.get("ordinary_native_admission") is False and value.get("full_study_admitted") is False,
          "local projection independent review differs")
    return value


def _standing(path: Path, expected: str, proposal: Mapping[str, Any]) -> dict[str, Any]:
    value = _json(path, "local projection standing authority")
    raw = _source_file(path, expected, "local projection standing authority")
    required = {"application", "coverage_floor", "full_study_admitted", "kind", "new_direct_user_decision_claimed",
                "ordinary_native_admission", "proposal_sha256", "schema_version", "user_instruction", "user_message_at"}
    _need(_sha(raw) == expected == STANDING_SHA and set(value) == required and value.get("schema_version") == 1
          and value.get("proposal_sha256") == _sha(_canon(dict(proposal))) and value.get("new_direct_user_decision_claimed") is False
          and value.get("ordinary_native_admission") is False and value.get("full_study_admitted") is False and value.get("coverage_floor") == 0.88,
          "local projection standing authority differs")
    return value


def _retained_answer(proposal: Mapping[str, Any]) -> dict[str, Any]:
    history = next(Path(path) for path in proposal["source_bindings"] if path.endswith("chat_history.jsonl"))
    answer: str | None = None
    for line in _source_file(history, proposal["source_bindings"][str(history)], "retained chat history").splitlines():
        item = json.loads(line)
        if isinstance(item, Mapping) and item.get("type") == "assistant" and isinstance(item.get("content"), str):
            candidate = item["content"]
            if candidate.startswith('{"verdicts"'):
                answer = candidate
    _need(answer is not None and _sha(answer.encode()) == ORIGINAL_SHA, "retained local answer differs")
    value = json.loads(answer)
    _need(isinstance(value, dict) and set(value) == {"verdicts"} and isinstance(value["verdicts"], list) and len(value["verdicts"]) == 8, "retained local answer schema differs")
    return value


def _project(answer: Mapping[str, Any], proposal: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(_canon(dict(answer)))
    quote = value["verdicts"][3]["evidence"][0]["exact_quote"]
    _need(isinstance(quote, str) and len(quote) == 579 and _sha(quote.encode()) == SOURCE_STORY_SHA, "retained source quote differs")
    value["verdicts"][3]["evidence"][0]["exact_quote"] = quote[:500]
    _need(_sha(_canon(value)) == PROJECTED_SHA, "projected local answer differs")
    return value


def _partial(path: Path, expected: str, successor_manifest_sha256: str) -> dict[str, Any]:
    value = _json(path, "partial successor replay")
    raw = _source_file(path, expected, "partial successor replay")
    required = {"all_protected_native_identities", "all_protected_native_identity_commitment_sha256", "completed_ordinals",
                "controller_sha256", "evidence_class", "failed_attempts", "failed_ordinals", "failed_wave_admitted",
                "inner_epoch_sha256", "native_identities", "partial_criterion_verdict_count", "prior_logical_count",
                "provider_calls_made", "recognized_logical_count", "recognized_native_identity_count", "records",
                "resend_authority", "schema_recovery_adopted", "schema_recovery_proposal_sha256", "schema_version",
                "settlement_sha256", "successor_manifest_sha256", "wave_start_sha256"}
    _need(_sha(raw) == expected == PARTIAL_SHA and set(value) == required and value.get("schema_version") == 1
          and value.get("evidence_class") == "source_bound_partial_successor_wave_with_retained_schema_failure_v1"
          and value.get("controller_sha256") == SUCCESSOR_SHA and value.get("successor_manifest_sha256") == successor_manifest_sha256
          and value.get("prior_logical_count") == 251 and value.get("recognized_logical_count") == 260
          and value.get("recognized_native_identity_count") == 259 and value.get("partial_criterion_verdict_count") == 66
          and value.get("completed_ordinals") == [252, 253, 255, 256, 257, 258, 259, 260, 261]
          and value.get("failed_ordinals") == [LOCAL_ORDINAL] and value.get("failed_wave_admitted") is False
          and value.get("resend_authority") is False and value.get("provider_calls_made") == 0
          and value.get("schema_recovery_adopted") is False and value.get("schema_recovery_proposal_sha256") == PROPOSAL_SHA,
          "partial successor replay differs")
    identities = _identity(value["all_protected_native_identities"])
    _need(len(identities) == 259 and value.get("all_protected_native_identity_commitment_sha256") == _sha(_canon(identities))
          and _identity(value["native_identities"]) == [dict(item["native_identity"]) for item in value["records"]], "partial native identities differ")
    failed = value["failed_attempts"]
    _need(isinstance(failed, list) and len(failed) == 1 and failed[0].get("ordinal") == LOCAL_ORDINAL
          and failed[0].get("retained_complete_answer") is True and failed[0].get("question_ids") == [
              "core.task_and_brief_fidelity.intervention", "core.task_and_brief_fidelity.completion_flag",
              "core.task_and_brief_fidelity.no_meta_substitution", "core.length_and_scope_fit.form",
              "core.length_and_scope_fit.operation", "core.length_and_scope_fit.development",
              "core.length_and_scope_fit.density", "core.length_and_scope_fit.ending"], "partial failed cell differs")
    return value


def _source_guard(manifest: Mapping[str, Any]) -> tuple[Any, Any, dict[str, Any], bytes, Path, dict[int, Any], dict[str, Any]]:
    root = Path(manifest["successor_root"])
    _need(_inventory(root) == manifest["successor_inventory"]["files"]
          and _sha(_canon(manifest["successor_inventory"]["files"])) == manifest["successor_inventory"]["sha256"], "successor inventory changed")
    successor = _load(SUCCESSOR, SUCCESSOR_SHA, "successor controller")
    parent = _load(PARENT, PARENT_SHA, "frozen parent")
    source_manifest, source_raw = successor._manifest(root)
    _need(_sha(source_raw) == manifest["successor_manifest_sha256"] and source_manifest["controller_sha256"] == SUCCESSOR_SHA, "successor manifest changed")
    epoch, epoch_raw = parent._load_epoch(root, manifest["inner_epoch"]["sha256"])
    plan_root, _old, _prefix, requests = parent._epoch_integrity(root, epoch)
    _need(epoch_raw == Path(manifest["inner_epoch"]["path"]).read_bytes(), "copied epoch differs")
    partial = _partial(Path(manifest["partial"]["path"]), manifest["partial"]["sha256"], manifest["successor_manifest_sha256"])
    _need(partial["inner_epoch_sha256"] == manifest["inner_epoch"]["sha256"], "partial epoch differs")
    return successor, parent, source_manifest, epoch_raw, plan_root, requests, partial


def _manifest(root: Path, expected: str | None = None) -> tuple[dict[str, Any], bytes]:
    path = root / "local-continuation-manifest.json"
    raw, value = path.read_bytes(), _json(path, "local continuation manifest")
    required = {"schema_version", "evidence_class", "controller_sha256", "parent_sha256", "successor_controller_sha256",
                "successor_root", "successor_manifest_sha256", "successor_inventory", "inner_epoch", "partial",
                "proposal", "adoption", "independent_review", "standing_authority", "protected_native_identities",
                "local_projection", "pending_ordinals", "ownership", "provider_calls_made", "execution_authority"}
    _need((expected is None or _sha(raw) == expected) and set(value) == required and value.get("schema_version") == 3
          and value.get("evidence_class") == "dryad_grok_selected_local_schema_recovery_continuation_v3"
          and value.get("controller_sha256") == _sha(Path(__file__).read_bytes()) and value.get("parent_sha256") == PARENT_SHA
          and value.get("successor_controller_sha256") == SUCCESSOR_SHA and value.get("pending_ordinals") == PENDING
          and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False
          and value.get("ownership") == {"protected_native_identity_count": 259, "local_recovery_ordinals": [70, LOCAL_ORDINAL], "never_contact_ordinals": [LOCAL_ORDINAL]},
          "local continuation manifest differs")
    return value, raw


def prepare_local_continuation(
    *, continuation_root: Path, successor_root: Path, expected_successor_manifest_sha256: str,
    partial_path: Path, expected_partial_sha256: str, proposal_path: Path, expected_proposal_sha256: str,
    adoption_path: Path, expected_adoption_sha256: str, independent_review_path: Path,
    expected_independent_review_sha256: str, standing_authority_path: Path, expected_standing_authority_sha256: str,
) -> dict[str, Any]:
    """Create a fresh inert schema-3 root without a provider contact."""
    _need(expected_partial_sha256 == PARTIAL_SHA and expected_proposal_sha256 == PROPOSAL_SHA and expected_adoption_sha256 == ADOPTION_SHA
          and expected_independent_review_sha256 == REVIEW_SHA and expected_standing_authority_sha256 == STANDING_SHA, "local source pin differs")
    proposal = _proposal(Path(proposal_path), expected_proposal_sha256)
    _adoption(Path(adoption_path), expected_adoption_sha256, _sha(_canon(proposal)))
    _review(Path(independent_review_path), expected_independent_review_sha256, proposal)
    _standing(Path(standing_authority_path), expected_standing_authority_sha256, proposal)
    projection = _project(_retained_answer(proposal), proposal)
    source = Path(successor_root).resolve()
    successor = _load(SUCCESSOR, SUCCESSOR_SHA, "successor controller")
    _source_manifest, source_raw = successor._manifest(source)
    _need(_sha(source_raw) == expected_successor_manifest_sha256, "successor manifest pin differs")
    parent = _load(PARENT, PARENT_SHA, "frozen parent")
    epoch, epoch_raw = parent._load_epoch(source, "74012a612915137c43e35eff5bb64b413be0b2dabbdc3aa52ceb4b88d1a245d6")
    _plan, _old, _prefix, requests = parent._epoch_integrity(source, epoch)
    partial = _partial(Path(partial_path), expected_partial_sha256, expected_successor_manifest_sha256)
    _need(requests[LOCAL_ORDINAL]["question_ids"] == partial["failed_attempts"][0]["question_ids"], "254 request binding differs")
    root = Path(continuation_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _need(not any(root.iterdir()), "local continuation root must be fresh")
    protected = _identity(partial["all_protected_native_identities"])
    _new(root / "suffix-epoch.json", epoch_raw)
    _new(root / "protected-native-identities.json", _canon(protected))
    _new(root / "local-projection.json", _canon(projection))
    inventory = _inventory(source)
    manifest = {
        "schema_version": 3, "evidence_class": "dryad_grok_selected_local_schema_recovery_continuation_v3", "controller_sha256": _sha(Path(__file__).read_bytes()),
        "parent_sha256": PARENT_SHA, "successor_controller_sha256": SUCCESSOR_SHA, "successor_root": str(source), "successor_manifest_sha256": expected_successor_manifest_sha256,
        "successor_inventory": {"sha256": _sha(_canon(inventory)), "files": inventory},
        "inner_epoch": {"path": str(root / "suffix-epoch.json"), "sha256": _sha(epoch_raw)},
        "partial": {"path": str(Path(partial_path).resolve()), "sha256": expected_partial_sha256},
        "proposal": {"path": str(Path(proposal_path).resolve()), "sha256": expected_proposal_sha256},
        "adoption": {"path": str(Path(adoption_path).resolve()), "sha256": expected_adoption_sha256},
        "independent_review": {"path": str(Path(independent_review_path).resolve()), "sha256": expected_independent_review_sha256},
        "standing_authority": {"path": str(Path(standing_authority_path).resolve()), "sha256": expected_standing_authority_sha256},
        "protected_native_identities": {"path": str(root / "protected-native-identities.json"), "sha256": _sha(_canon(protected)), "commitment_sha256": _sha(_canon(protected)), "count": 259},
        "local_projection": {"path": str(root / "local-projection.json"), "sha256": PROJECTED_SHA, "original_sha256": ORIGINAL_SHA, "ordinal": LOCAL_ORDINAL},
        "pending_ordinals": PENDING, "ownership": {"protected_native_identity_count": 259, "local_recovery_ordinals": [70, LOCAL_ORDINAL], "never_contact_ordinals": [LOCAL_ORDINAL]},
        "provider_calls_made": 0, "execution_authority": False,
    }
    _new(root / "local-continuation-manifest.json", _canon(manifest))
    return {"manifest_sha256": _sha((root / "local-continuation-manifest.json").read_bytes()), "controller_sha256": manifest["controller_sha256"], "provider_calls_made": 0}


def verify_local_continuation(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str) -> dict[str, Any]:
    """Read-only validation and normalization of the adopted local projection."""
    root = Path(continuation_root).resolve()
    manifest, raw = _manifest(root, expected_manifest_sha256)
    _need(expected_controller_sha256 == manifest["controller_sha256"] == _sha(Path(__file__).read_bytes()), "local controller pin differs")
    _successor, parent, _source_manifest, _epoch_raw, plan_root, requests, partial = _source_guard(manifest)
    proposal = _proposal(Path(manifest["proposal"]["path"]), manifest["proposal"]["sha256"])
    adoption = _adoption(Path(manifest["adoption"]["path"]), manifest["adoption"]["sha256"], _sha(_canon(proposal)))
    review = _review(Path(manifest["independent_review"]["path"]), manifest["independent_review"]["sha256"], proposal)
    standing = _standing(Path(manifest["standing_authority"]["path"]), manifest["standing_authority"]["sha256"], proposal)
    answer = _retained_answer(proposal)
    projection = _project(answer, proposal)
    projection_path = Path(manifest["local_projection"]["path"])
    _need(projection_path.read_bytes() == _canon(projection) and _sha(projection_path.read_bytes()) == manifest["local_projection"]["sha256"], "stored local projection differs")
    protected = _protected_identities(manifest)
    epoch, epoch_raw = parent._load_epoch(Path(manifest["successor_root"]), manifest["inner_epoch"]["sha256"])
    runtime, plan = parent._runtime_from_epoch(epoch), parent._plan(plan_root, epoch["plan_sha256"])[0]
    row, passed = requests[LOCAL_ORDINAL], parent._pass_index(plan)[requests[LOCAL_ORDINAL]["pass_id"]]
    source = parent._source_for_pass(plan_root, passed)
    normalized = runtime.runner._normalize_batch(
        projection, expected_ids=row["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story",
        judge_id="grok:grok-4.6", run_id="dryad-local-schema-projection/0254", artifact_text=source["story_text"],
        context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[],
    )
    _need([item["question_id"] for item in normalized] == row["question_ids"] and len(normalized) == 8
          and partial["failed_attempts"][0]["question_ids"] == row["question_ids"], "local projection verdict coverage differs")
    peer_records = [dict(item) for item in partial["records"]]
    _need([item.get("ordinal") for item in peer_records] == partial["completed_ordinals"]
          and all(set(item) == {"controller_authorization_sha256", "criterion_verdict_count", "native_identity", "ordinal", "terminal_sha256"}
                  and item.get("native_identity") in protected for item in peer_records), "partial peer ownership differs")
    local_identity = {"kind": "local_schema_projection", "ordinal": LOCAL_ORDINAL, "projection_sha256": PROJECTED_SHA,
                      "identity_sha256": _sha(_canon({"kind": "local_schema_projection", "ordinal": LOCAL_ORDINAL, "projection_sha256": PROJECTED_SHA}))}
    return {
        "ordinal": LOCAL_ORDINAL, "evidence_class": adoption["evidence_class"], "verdicts": normalized,
        "local_identity": local_identity,
        "local_provenance": {"proposal_sha256": manifest["proposal"]["sha256"], "adoption_sha256": manifest["adoption"]["sha256"],
                             "independent_review_sha256": manifest["independent_review"]["sha256"], "standing_authority_sha256": manifest["standing_authority"]["sha256"],
                             "original_message_sha256": ORIGINAL_SHA, "projected_message_sha256": PROJECTED_SHA, "source_story_sha256": SOURCE_STORY_SHA,
                             "ordinary_native_admission": False, "new_provider_attempts_authorized": 0},
        "ownership": dict(manifest["ownership"]),
        "source": {"root": str(root), "manifest_sha256": _sha(raw), "controller_sha256": manifest["controller_sha256"],
                   "successor_root": manifest["successor_root"], "successor_manifest_sha256": manifest["successor_manifest_sha256"],
                   "partial_sha256": manifest["partial"]["sha256"], "inner_epoch_sha256": _sha(epoch_raw)},
        "protected_paths": {"continuation_root": {"path": str(root), "inventory_sha256": _sha(_canon(_inventory(root)))},
                            "continuation_manifest": {"path": str(root / "local-continuation-manifest.json"), "sha256": _sha(raw)},
                            "controller": {"path": str(Path(__file__).resolve()), "sha256": manifest["controller_sha256"]},
                            "successor_root": {"path": manifest["successor_root"], "inventory_sha256": manifest["successor_inventory"]["sha256"]},
                            "successor_manifest": {"path": str(Path(manifest["successor_root"]) / "successor-manifest.json"), "sha256": manifest["successor_manifest_sha256"]},
                            "partial": dict(manifest["partial"]), "proposal": dict(manifest["proposal"]), "adoption": dict(manifest["adoption"]),
                            "independent_review": dict(manifest["independent_review"]), "standing_authority": dict(manifest["standing_authority"]),
                            "local_projection": dict(manifest["local_projection"]), "protected_native_identities": dict(manifest["protected_native_identities"]),
                            "inner_epoch": dict(manifest["inner_epoch"])},
        "partial_peer_records": peer_records,
        "partial_peer_source": {"root": manifest["successor_root"], "successor_manifest_sha256": manifest["successor_manifest_sha256"],
                                "inner_epoch_sha256": manifest["inner_epoch"]["sha256"], "partial": dict(manifest["partial"])},
        "provider_calls_made": 0, "full_original_study_admitted": False, "review_decision": review["decision"], "standing_authority_kind": standing["kind"],
    }


def _execution_review(path: Path, expected: str, *, manifest: Mapping[str, Any], manifest_raw: bytes, parent: Any, epoch: Mapping[str, Any], live: bool) -> dict[str, Any]:
    value = _json(path, "local continuation execution review")
    _source_file(path, expected, "local continuation execution review")
    required = {"schema_version", "decision", "controller_sha256", "continuation_manifest_sha256", "parent_sha256", "inner_epoch_sha256",
                "route_sha256", "gate_sha256", "parent_review_path", "parent_review_sha256", "reviewed_at", "expires_at"}
    _need(set(value) == required and value.get("schema_version") == 1 and value.get("decision") == "approved_dryad_grok_selected_local_continuation_untouched_waves"
          and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("continuation_manifest_sha256") == _sha(manifest_raw)
          and value.get("parent_sha256") == PARENT_SHA and value.get("inner_epoch_sha256") == manifest["inner_epoch"]["sha256"], "local execution review differs")
    parent_review = parent._review(Path(value["parent_review_path"]), value["parent_review_sha256"], epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, live=live)
    _need(parent_review["route_sha256"] == value["route_sha256"] and parent_review["gate_sha256"] == value["gate_sha256"], "local execution route differs")
    if live:
        reviewed, expires, now = _time(value["reviewed_at"], "local execution review time"), _time(value["expires_at"], "local execution review expiry"), datetime.now(timezone.utc)
        _need(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "local execution review is not fresh for 300 seconds")
    return {**value, "parent_review": parent_review}


def _attempts(root: Path, parent: Any) -> dict[int, dict[str, Any] | None]:
    base = root / "attempts"
    if not base.exists():
        return {}
    result: dict[int, dict[str, Any] | None] = {}
    for directory in base.iterdir():
        match = re.fullmatch(r"request-(\d{4})", directory.name)
        _need(match is not None and directory.is_dir() and not directory.is_symlink(), "local attempt inventory differs")
        ordinal = int(match.group(1))
        start, terminal = parent._attempt_path(root, ordinal, "attempt-start.json"), parent._attempt_path(root, ordinal, "terminal.json")
        _need(ordinal in PENDING and start.is_file() and ordinal not in result, "local attempt inventory differs")
        result[ordinal] = _json(terminal, "local terminal") if terminal.is_file() else None
    return result


def _replay_path(root: Path, start: int, size: int) -> Path:
    return root / "replays" / f"wave-{start:04d}-slots-{size:02d}.json"


def _replayed(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes) -> tuple[set[int], list[dict[str, str]]]:
    complete: set[int] = set(); identities: list[dict[str, str]] = []
    paths = sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else []
    for path in paths:
        value = _json(path, "local replay")
        required = {"schema_version", "evidence_class", "controller_sha256", "continuation_manifest_sha256", "inner_epoch_sha256",
                    "wave_start_sha256", "settlement_sha256", "ordinals", "terminals", "native_identities", "provider_calls_made"}
        ordinals = value.get("ordinals")
        _need(set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "source_bound_local_continuation_untouched_wave_replay_v1"
              and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("continuation_manifest_sha256") == _sha(manifest_raw)
              and value.get("inner_epoch_sha256") == manifest["inner_epoch"]["sha256"] and value.get("provider_calls_made") == 0
              and isinstance(ordinals, list) and ordinals and len(ordinals) == len(value.get("terminals", [])) == len(value.get("native_identities", []))
              and all(ordinal in PENDING for ordinal in ordinals) and not (complete & set(ordinals)), "local replay differs")
        start = parent._wave_path(root, ordinals[0], len(ordinals), "start")
        settlement = parent._wave_path(root, ordinals[0], len(ordinals), "settlement")
        _need(_sha(start.read_bytes()) == value["wave_start_sha256"] and _sha(settlement.read_bytes()) == value["settlement_sha256"], "local replay binding differs")
        for ordinal, terminal in zip(ordinals, value["terminals"], strict=True):
            _need(isinstance(terminal, Mapping) and terminal.get("ordinal") == ordinal
                  and terminal.get("terminal_sha256") == _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()), "local replay terminal differs")
        complete.update(ordinals); identities.extend(_identity(value["native_identities"]))
    _identity(identities)
    return complete, identities


def _next(records: Mapping[int, Mapping[str, Any] | None], replayed: set[int]) -> int:
    _need(set(records) <= set(PENDING), "local attempt outside schedule")
    for index, ordinal in enumerate(PENDING):
        terminal = records.get(ordinal)
        if terminal is None:
            _need(not any(value in records for value in PENDING[index + 1:]) and all(value in replayed for value in PENDING[:index]), "local continuation cannot skip or bypass unreplayed cell")
            return ordinal
        _need(terminal.get("status") == "completed" and ordinal in replayed, "local continuation prior cell incomplete or unreplayed")
    raise ValueError("local continuation has no remaining ordinal")


def _authorization(root: Path, ordinal: int, manifest: Mapping[str, Any], manifest_raw: bytes, start: Path, review_path: Path, review_sha: str, route: str, gate: str) -> str:
    path = root / "controller-authorizations" / f"request-{ordinal:04d}.json"
    value = {"schema_version": 1, "ordinal": ordinal, "controller_sha256": manifest["controller_sha256"], "continuation_manifest_sha256": _sha(manifest_raw),
             "attempt_start_sha256": _sha(start.read_bytes()), "local_adoption_sha256": manifest["adoption"]["sha256"], "execution_review_path": str(review_path),
             "execution_review_sha256": review_sha, "route_sha256": route, "gate_sha256": gate, "authorized_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _new(path, _canon(value))
    return _sha(path.read_bytes())


def dispatch_untouched_wave(
    *, continuation_root: Path, start_ordinal: int, wave_size: int, execution_review_path: Path,
    expected_execution_review_sha256: str, queue_root: Path, broker_factory: Any | None = None,
) -> dict[str, Any]:
    """Contact one exact untouched native wave; 254 is deliberately unreachable."""
    root = Path(continuation_root).resolve(); manifest, manifest_raw = _manifest(root)
    _need(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"] and type(start_ordinal) is int and type(wave_size) is int
          and 1 <= wave_size <= MAX_WAVE and start_ordinal in PENDING, "local dispatch geometry or source differs")
    queue = Path(queue_root).resolve(); _need(queue.is_dir() and not queue.is_symlink(), "local queue is inactive")
    _successor, parent, _source_manifest, epoch_raw, plan_root, requests, _partial_value = _source_guard(manifest)
    epoch, _raw = parent._load_epoch(Path(manifest["successor_root"]), manifest["inner_epoch"]["sha256"])
    review = _execution_review(Path(execution_review_path), expected_execution_review_sha256, manifest=manifest, manifest_raw=manifest_raw, parent=parent, epoch=epoch, live=True)
    records, replayed, prior_ids = _attempts(root, parent), *_replayed(root, parent, manifest, manifest_raw)
    ordinals = PENDING[PENDING.index(start_ordinal):PENDING.index(start_ordinal) + wave_size]
    _need(len(ordinals) == wave_size and ordinals[0] == _next(records, replayed), "local wave is not exact next pending")
    starts = [parent._attempt_path(root, ordinal, "attempt-start.json") for ordinal in ordinals]
    _need(not any(path.exists() for path in starts) and LOCAL_ORDINAL not in ordinals, "local wave would resend an existing or local cell")
    protected = _protected_identities(manifest)
    identities = _identity([*protected, *prior_ids])
    prepared = [parent._prepare_wave_cell(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, plan_root=plan_root, requests=requests,
                                         review_path=Path(review["parent_review_path"]), review_sha256=review["parent_review_sha256"], review=review["parent_review"],
                                         ordinal=ordinal, wave_start_ordinal=ordinals[0], wave_ordinals=ordinals, slot_index=index)
                for index, ordinal in enumerate(ordinals)]
    for item in prepared:
        _new(item["start_path"], _canon(item["start"]))
    wave = {"format_version": 1, "epoch_sha256": manifest["inner_epoch"]["sha256"], "epoch_source_sha256": _sha(epoch_raw), "execution_mode": epoch["execution_mode"],
            "max_concurrency": epoch["max_concurrency"], "start_ordinal": ordinals[0], "wave_size": len(ordinals), "ordinals": ordinals,
            "review": {"path": str(review["parent_review_path"]), "sha256": review["parent_review_sha256"]}, "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"],
            "runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"], "runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"], "v3_sha256": epoch["v3_source"]["sha256"],
            "selected_schedule_sha256": epoch["selected_schedule"]["sha256"], "rows": [{"ordinal": item["row"]["ordinal"], "slot_index": index, "pass_id": item["row"]["pass_id"], "source_sha256": item["source"]["sha256"], "context_sha256": item["start"]["context_sha256"], "attempt_start_sha256": _sha(item["start_path"].read_bytes())} for index, item in enumerate(prepared)]}
    wave_path = parent._wave_path(root, ordinals[0], len(ordinals), "start"); _new(wave_path, _canon(wave))
    results: dict[int, dict[str, Any]] = {}; failures: list[dict[str, Any]] = []
    admitted: set[int] = set(); contacted: set[int] = set(); stop, lock = threading.Event(), threading.Lock()

    def cell(item: Mapping[str, Any]) -> None:
        ordinal, admission, content, metadata = item["row"]["ordinal"], False, None, None
        try:
            _need(not stop.is_set(), "local continuation stopped before contact")
            runtime, source = item["runtime"], item["source"]
            broker = parent._broker(runtime, queue, broker_factory)
            def before_contact(context: Mapping[str, Any]) -> None:
                nonlocal admission
                _need(not stop.is_set() and _sha(_canon(dict(context))) == item["start"]["context_sha256"], "local context changed")
                _need(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"] and (root / "local-continuation-manifest.json").read_bytes() == manifest_raw, "local controller changed before contact")
                _source_guard(manifest)
                proposal = _proposal(Path(manifest["proposal"]["path"]), manifest["proposal"]["sha256"])
                _adoption(Path(manifest["adoption"]["path"]), manifest["adoption"]["sha256"], _sha(_canon(proposal)))
                _review(Path(manifest["independent_review"]["path"]), manifest["independent_review"]["sha256"], proposal)
                _standing(Path(manifest["standing_authority"]["path"]), manifest["standing_authority"]["sha256"], proposal)
                live = _execution_review(Path(execution_review_path), expected_execution_review_sha256, manifest=manifest, manifest_raw=manifest_raw, parent=parent, epoch=epoch, live=True)
                _need(live["route_sha256"] == review["route_sha256"] and live["gate_sha256"] == review["gate_sha256"], "local route or gate changed before contact")
                _protected_identities(manifest)
                runtime.verify(); _need(parent._source_for_pass(plan_root, item["passed"]) == source, "local payload changed before contact")
                with lock:
                    _need(not stop.is_set(), "local continuation stopped before admission")
                    _authorization(root, ordinal, manifest, manifest_raw, item["start_path"], Path(execution_review_path), expected_execution_review_sha256, live["route_sha256"], live["gate_sha256"])
                    _new(parent._attempt_path(root, ordinal, "contact-admission.json"), _canon({"format_version": 1, "ordinal": ordinal, "epoch_sha256": manifest["inner_epoch"]["sha256"], "attempt_start_sha256": _sha(item["start_path"].read_bytes()), "context_sha256": item["start"]["context_sha256"], "route_sha256": live["route_sha256"], "gate_sha256": live["gate_sha256"], "admitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}))
                    admission = True; admitted.add(ordinal); contacted.add(ordinal)
            transport = runtime.transport.bind_grok_broker_transport(broker=broker, route=review["parent_review"]["route"], before_contact=before_contact, runtime_check=runtime.verify)
            content, metadata = transport(item["context"])
            _need(isinstance(content, str) and isinstance(metadata, Mapping) and admission, "local transport returned without admission")
            runtime.runner._validate_grok_transport_evidence(item["run_root"], metadata)
            normalized = runtime.runner._normalize_batch(runtime.runner._parse_model_json(content), expected_ids=item["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=item["context"]["run"]["run_id"], artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
            identity = {"request_id_hash": metadata["request_id_sha256"], "session_id_hash": metadata["session_id_sha256"]}
            with lock:
                _identity([*identities, identity]); identities.append(identity)
            parent._terminal(root=root, ordinal=ordinal, epoch_sha256=manifest["inner_epoch"]["sha256"], start_path=item["start_path"], status="completed", run_root=item["run_root"], contact_admitted=True, context=item["context"], content=content, metadata=metadata, verdicts=normalized)
            with lock:
                results[ordinal] = {"ordinal": ordinal, "status": "completed_pending_replay", "provider_calls_made": 1}
        except BaseException as error:  # noqa: BLE001
            with lock:
                stop.set()
            if not parent._attempt_path(root, ordinal, "terminal.json").exists():
                parent._terminal(root=root, ordinal=ordinal, epoch_sha256=manifest["inner_epoch"]["sha256"], start_path=item["start_path"], status="ambiguous", run_root=item["run_root"], contact_admitted=admission, context=item["context"], content=content, metadata=metadata)
            with lock:
                failures.append({"ordinal": ordinal, "error_type": type(error).__name__, "contact_admitted": admission, "contact_started": admission})

    with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="dryad-grok-local-continuation") as executor:
        futures = {executor.submit(cell, item): item["row"]["ordinal"] for item in prepared}
        while futures:
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future); future.result()
    settlement = parent._wave_settlement(root, epoch_sha256=manifest["inner_epoch"]["sha256"], start_ordinal=ordinals[0], wave_ordinals=ordinals, wave_start_sha256=_sha(wave_path.read_bytes()))
    _new(parent._wave_path(root, ordinals[0], len(ordinals), "settlement"), _canon(settlement))
    return {"state": "stopped_no_retry" if failures else "completed_pending_replay", "ordinals": ordinals, "failures": sorted(failures, key=lambda item: item["ordinal"]), "admitted_ordinals": sorted(admitted), "contact_started_ordinals": sorted(contacted), "completed_ordinals": sorted(results), "uncontacted_ordinals": sorted(set(ordinals) - contacted), "provider_calls_made": len(contacted)}


def _historical_authorization(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes, ordinal: int) -> str:
    path = root / "controller-authorizations" / f"request-{ordinal:04d}.json"
    raw, value = path.read_bytes(), _json(path, "local historical authorization")
    required = {"schema_version", "ordinal", "controller_sha256", "continuation_manifest_sha256", "attempt_start_sha256", "local_adoption_sha256",
                "execution_review_path", "execution_review_sha256", "route_sha256", "gate_sha256", "authorized_at"}
    _need(set(value) == required and value.get("schema_version") == 1 and value.get("ordinal") == ordinal
          and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("continuation_manifest_sha256") == _sha(manifest_raw)
          and value.get("attempt_start_sha256") == _sha(parent._attempt_path(root, ordinal, "attempt-start.json").read_bytes())
          and value.get("local_adoption_sha256") == manifest["adoption"]["sha256"], "local historical authorization differs")
    return _sha(raw)


def replay_untouched_wave(
    *, continuation_root: Path, start_ordinal: int, wave_size: int, approved_v5_routes: Mapping[str, Any],
    protected_native_identities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Replay actual settled terminals through the frozen parent without provider contact."""
    root = Path(continuation_root).resolve(); manifest, manifest_raw = _manifest(root)
    _need(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE and start_ordinal in PENDING, "local replay geometry differs")
    _successor, parent, _source_manifest, _epoch_raw, plan_root, requests, _partial_value = _source_guard(manifest)
    wave_path = parent._wave_path(root, start_ordinal, wave_size, "start")
    wave = _json(wave_path, "local wave")
    ordinals = wave.get("ordinals")
    _need(isinstance(ordinals, list) and len(ordinals) == wave_size and ordinals[0] == start_ordinal and all(item in PENDING for item in ordinals), "local replay wave differs")
    protected = _protected_identities(manifest)
    _need([dict(item) for item in protected_native_identities] == protected, "local replay protected identities differ")
    previous_ordinals, previous_ids = _replayed(root, parent, manifest, manifest_raw)
    _need(not (set(ordinals) & previous_ordinals), "local replay already exists")
    settlement_path = parent._wave_path(root, start_ordinal, wave_size, "settlement")
    settlement = _json(settlement_path, "local settlement")
    _need(settlement.get("ordinals") == ordinals and settlement.get("wave_start_sha256") == _sha(wave_path.read_bytes())
          and isinstance(settlement.get("rows"), list) and len(settlement["rows"]) == wave_size, "local replay settlement differs")
    epoch, _epoch_raw = parent._load_epoch(Path(manifest["successor_root"]), manifest["inner_epoch"]["sha256"])
    plan, runtime = parent._plan(plan_root, epoch["plan_sha256"])[0], parent._runtime_from_epoch(epoch)
    passes, identities = parent._pass_index(plan), []
    terminals: list[dict[str, Any]] = []
    for ordinal, settled in zip(ordinals, settlement["rows"], strict=True):
        row, terminal_path = requests[ordinal], parent._attempt_path(root, ordinal, "terminal.json")
        _need(isinstance(settled, Mapping) and settled.get("ordinal") == ordinal and settled.get("status") == "completed"
              and settled.get("terminal_sha256") == _sha(terminal_path.read_bytes()), "local replay terminal differs")
        verdicts, identity = parent._replay_suffix_terminal(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, runtime=runtime,
                                                             plan_root=plan_root, passed=passes[row["pass_id"]], row=row, approved_v5_routes=approved_v5_routes)
        _need(verdicts and settled.get("native_identity") == identity, "local replay native identity differs")
        identities.append(identity)
        terminals.append({"ordinal": ordinal, "terminal_sha256": _sha(terminal_path.read_bytes()), "controller_authorization_sha256": _historical_authorization(root, parent, manifest, manifest_raw, ordinal)})
    _identity([*protected, *previous_ids, *identities])
    result = {"schema_version": 1, "evidence_class": "source_bound_local_continuation_untouched_wave_replay_v1", "controller_sha256": manifest["controller_sha256"],
              "continuation_manifest_sha256": _sha(manifest_raw), "inner_epoch_sha256": manifest["inner_epoch"]["sha256"],
              "wave_start_sha256": _sha(wave_path.read_bytes()), "settlement_sha256": _sha(settlement_path.read_bytes()), "ordinals": ordinals,
              "terminals": terminals, "native_identities": identities, "provider_calls_made": 0}
    _new(_replay_path(root, start_ordinal, wave_size), _canon(result))
    return result


def verify_untouched_replay_chain(
    *, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str,
    approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Read every immutable replay record and semantically replay each retained terminal."""
    root = Path(continuation_root).resolve(); manifest, manifest_raw = _manifest(root, expected_manifest_sha256)
    _need(expected_controller_sha256 == manifest["controller_sha256"] == _sha(Path(__file__).read_bytes()), "local controller pin differs")
    _successor, parent, _source_manifest, _epoch_raw, plan_root, requests, _partial_value = _source_guard(manifest)
    replayed, native_identities = _replayed(root, parent, manifest, manifest_raw)
    epoch, _raw = parent._load_epoch(Path(manifest["successor_root"]), manifest["inner_epoch"]["sha256"])
    plan, runtime = parent._plan(plan_root, epoch["plan_sha256"])[0], parent._runtime_from_epoch(epoch)
    passes = parent._pass_index(plan)
    terminals: list[dict[str, Any]] = []
    for path in sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else []:
        record = _json(path, "local replay record")
        for ordinal, terminal in zip(record["ordinals"], record["terminals"], strict=True):
            row = requests[ordinal]
            verdicts, identity = parent._replay_suffix_terminal(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, runtime=runtime,
                                                                 plan_root=plan_root, passed=passes[row["pass_id"]], row=row, approved_v5_routes=approved_v5_routes)
            _need(verdicts and identity in record["native_identities"] and terminal["terminal_sha256"] == _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()), "local replay semantic verification differs")
            terminals.append(dict(terminal))
    _need([item["ordinal"] for item in terminals] == sorted(replayed), "local replay terminal ownership differs")
    return {"untouched_replay_ordinals": sorted(replayed), "untouched_native_identities": native_identities,
            "untouched_terminals": terminals, "provider_calls_made": 0, "protected_native_identity_count": 259}
