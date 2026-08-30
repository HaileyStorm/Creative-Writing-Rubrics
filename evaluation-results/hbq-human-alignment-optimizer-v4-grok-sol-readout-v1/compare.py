#!/usr/bin/env python3
"""Provider-free descriptive readout of exact matched Grok and Sol lifecycle evidence."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
EXEC_V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
EXEC_V3_CONTRACT_PATH = EXEC_V3_PATH.with_name("study-contract.json")
ADMISSION_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-admission-v1" / "admit.py"
ADMISSION_CONTRACT_PATH = ADMISSION_PATH.with_name("study-contract.json")
ANALYZER_CONTRACT_PATH = HERE / "study-contract.json"
EXEC_V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
EXEC_V3_CONTRACT_SHA256 = "d92970c60a538a229c8f5470d53e8fd3dd4d163aff25b0110b6453f6caf080f5"
ADMISSION_SHA256 = "a1c18d224c40e51a822cf2a46b2da273fef37d47df0fe207d1abe8b49bc75304"
ADMISSION_CONTRACT_SHA256 = "43f8bdab947a360224d5f9c02d0e69f5dd98fc261bc8d5e94dc17fc9997f92e8"
FROZEN_SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
HANNA_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
STUDY_ID = "hbq-human-alignment-optimizer-v4-grok-sol-readout-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PROMPT_FIELDS = (
    "task_payload_sha256",
    "candidate_instruction_sha256",
    "candidate_profile_sha256",
    "response_schema_sha256",
    "prompt_sha256",
    "story_sha256",
)
IDENTITY_FIELDS = (
    "provider", "requested_model", "effective_model", "provider_reported_model",
    "requested_reasoning_effort", "reasoning_attested", "route_name", "transport_identity",
    "identity_evidence",
)
EXPECTED_ENDPOINT_IDENTITIES = {
    "grok": {
        "provider": "xai_grok_build",
        "requested_model": "grok-4.6",
        "effective_model": "grok-4.6-build",
        "provider_reported_model": "grok-4.6-build",
        "requested_reasoning_effort": "high",
        "reasoning_attested": False,
        "route_name": "grok-build-grok-4.6",
        "transport_identity": "grok_build_saved_session_subscription_tool_free_v1",
        "identity_evidence": "requested_and_cli_envelope_reported_model_reasoning_unattested",
    },
    "sol": {
        "provider": "openai_codex",
        "requested_model": "gpt-5.6-sol",
        "effective_model": "gpt-5.6-sol",
        "provider_reported_model": None,
        "requested_reasoning_effort": "high",
        "reasoning_attested": False,
        "route_name": "codex-chatgpt-gpt-5.6-sol",
        "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
        "identity_evidence": (
            "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_"
            "not_provider_attested"
        ),
    },
}
SOL_SUCCESS_ROOTS = (
    ("v4-cell-b389399871064622", "cwr-hanna-v4-native-pilot-42ef2e9-v3"),
    ("v4-cell-162aad37c6e3abf4", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-162aad37c6e3abf4"),
    ("v4-cell-4e5b47579bfd2a05", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-4e5b47579bfd2a05"),
    ("v4-cell-64bdf1a35f2dfb07", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-64bdf1a35f2dfb07"),
    ("v4-cell-73bdb8cddb3a83c2", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-73bdb8cddb3a83c2"),
    ("v4-cell-b3fd55dcdaeb08e3", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-b3fd55dcdaeb08e3"),
    ("v4-cell-c3e02c02a94115ae", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-c3e02c02a94115ae"),
    ("v4-cell-e8ad23961fb0c080", "cwr-hanna-v4-sol-wave-eed083d-r2-v4-cell-e8ad23961fb0c080"),
    ("v4-cell-094e2614a97cee52", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-094e2614a97cee52"),
    ("v4-cell-26568898d9115f0f", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-26568898d9115f0f"),
    ("v4-cell-29a699cbfc75b35b", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-29a699cbfc75b35b"),
    ("v4-cell-59184fa02b71eee9", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-59184fa02b71eee9"),
    ("v4-cell-67d0b1c2ac1df5b3", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-67d0b1c2ac1df5b3"),
    ("v4-cell-74cc1f3c212340cc", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-74cc1f3c212340cc"),
    ("v4-cell-8349eb6336efc8d4", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-8349eb6336efc8d4"),
    ("v4-cell-83f52f0914ef0605", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-83f52f0914ef0605"),
    ("v4-cell-8537110aaa35c031", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-8537110aaa35c031"),
    ("v4-cell-9972efd190758c5a", "cwr-hanna-v4-sol-wave2-eed083d-v4-cell-9972efd190758c5a"),
    ("v4-cell-1f75f5f67f17cf89", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-1f75f5f67f17cf89"),
    ("v4-cell-24daba4c6c1e4b89", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-24daba4c6c1e4b89"),
    ("v4-cell-265f0b037d888dd9", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-265f0b037d888dd9"),
    ("v4-cell-3df6c46c9b19a3bb", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-3df6c46c9b19a3bb"),
    ("v4-cell-653a2cec006c90e7", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-653a2cec006c90e7"),
    ("v4-cell-7a51de68cb5b7f38", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-7a51de68cb5b7f38"),
    ("v4-cell-9c0d98ecbcb57b15", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-9c0d98ecbcb57b15"),
    ("v4-cell-9f83290526c311cd", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-9f83290526c311cd"),
    ("v4-cell-a1986d5885ffe473", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-a1986d5885ffe473"),
    ("v4-cell-a7f7b7b216c1ac90", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-a7f7b7b216c1ac90"),
    ("v4-cell-ae0087f2c0379253", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-ae0087f2c0379253"),
    ("v4-cell-b139a8250f2379dd", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-b139a8250f2379dd"),
    ("v4-cell-b1fb398aeffbca1e", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-b1fb398aeffbca1e"),
    ("v4-cell-da7b0276e717de6a", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-da7b0276e717de6a"),
    ("v4-cell-ffce809d8c7eaf0c", "cwr-hanna-v4-sol-wave3-eed083d-v4-cell-ffce809d8c7eaf0c"),
)
SOL_CELLS = tuple(cell_id for cell_id, _root_name in SOL_SUCCESS_ROOTS)
EXCLUDED_TERMINAL_CELLS = frozenset({"v4-cell-2eb4f20b3db15aac", "v4-cell-2333370999fb84f3"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(value: Any) -> str:
    return sha256_bytes(canonical(value))


def _rounded(value: float) -> float:
    return round(float(value), 4)


def _stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise ValueError(f"HANNA matched readout pinned path is reparsed: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA matched readout file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("HANNA matched readout file changed during read")
    return raw


def _load_exact(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError(f"HANNA matched readout pinned dependency drifted: {path.name}")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if sha256_bytes(_stable_bytes(path)) != expected_sha256:
        raise ValueError(f"HANNA matched readout dependency changed during load: {path.name}")
    return module


def _load_dependencies() -> tuple[ModuleType, ModuleType]:
    if (
        sha256_bytes(_stable_bytes(EXEC_V3_CONTRACT_PATH)) != EXEC_V3_CONTRACT_SHA256
        or sha256_bytes(_stable_bytes(ADMISSION_CONTRACT_PATH)) != ADMISSION_CONTRACT_SHA256
    ):
        raise ValueError("HANNA matched readout pinned contract bytes drifted")
    execution = _load_exact(EXEC_V3_PATH, EXEC_V3_SHA256, "_hanna_readout_exec_v3")
    admission = _load_exact(ADMISSION_PATH, ADMISSION_SHA256, "_hanna_readout_admission_v1")
    execution._load_predecessor().contract()
    admission.contract()
    return execution, admission


def _read_canonical(path: Path) -> dict[str, Any]:
    raw = _stable_bytes(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA matched readout canonical artifact is invalid: {path.name}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA matched readout canonical artifact drifted: {path.name}")
    return value


def default_pair_specs(documents_root: Path | None = None) -> list[dict[str, Any]]:
    documents = Path(documents_root) if documents_root is not None else Path.home() / "Documents"
    return [
        {
            "sol_cell_id": sol_cell_id,
            "sol_execution_root": documents / root_name,
        }
        for sol_cell_id, root_name in SOL_SUCCESS_ROOTS
    ]


def _schedule_rows(
    execution: ModuleType, *, frozen_successor_path: Path, hanna_csv_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    native = execution._load_predecessor()
    schedule = native.derive_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    rows = schedule["mandatory_development"]
    by_cell = {row["cell_id"]: dict(row) for row in rows}
    matched: dict[str, dict[str, Any]] = {}
    for sol_cell_id in SOL_CELLS:
        sol = by_cell.get(sol_cell_id)
        if not isinstance(sol, dict) or sol["route_name"] != "sol_validation":
            raise ValueError("HANNA matched readout frozen Sol cell identity drifted")
        grok = [
            row for row in rows
            if row["route_name"] == "grok_primary"
            and row["item_id"] == sol["item_id"]
            and row["candidate_id"] == sol["candidate_id"]
        ]
        if len(grok) != 1 or any(grok[0][field] != sol[field] for field in PROMPT_FIELDS):
            raise ValueError("HANNA matched readout frozen Grok/Sol prompt binding drifted")
        matched[sol_cell_id] = dict(grok[0])
    return by_cell, matched


def _sol_event(execution: ModuleType, root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    predecessor = execution._load_predecessor()
    receipt = _read_canonical(root / "execution-receipt.json")
    return {
        "cell": dict(row),
        "identity": receipt["identity"],
        "native_request_bytes": _stable_bytes(root / "prompt-request.bin"),
        "outbound_payload": _stable_bytes(root / "predecessor-payload.json"),
        "effective_settings": {
            "route_name": row["route"]["route_name"],
            "effective_model": row["route"]["effective_model"],
            "requested_reasoning_effort": row["route"]["requested_reasoning_effort"],
            "tools_enabled": False,
            "web_search_enabled": False,
            "subagents_enabled": False,
            "output_schema_sha256": row["response_schema_sha256"],
            "provider_attested": False,
            "source": "codex_cli_local_events_and_invocation_v1",
        },
    }


def _verify_sol(
    execution: ModuleType, *, execution_root: Path, row: Mapping[str, Any], queue_root: Path,
    frozen_successor_path: Path, hanna_csv_path: Path,
) -> dict[str, Any]:
    root = Path(execution_root) / row["cell_id"]
    prepared = _read_canonical(root / "prepared.json")
    proof = _read_canonical(root / "zero-charge-route-proof.json")
    receipt = _read_canonical(root / "execution-receipt.json")
    effective = _read_canonical(root / "effective-settings.json")
    if not (
        prepared.get("route_evidence") == proof.get("route_evidence") == receipt.get("route_evidence")
        and proof.get("provider_calls_made") == 0
        and proof.get("zero_charge_only") is True
        and proof.get("paid_fallback_forbidden") is True
    ):
        raise ValueError("HANNA matched readout persisted Sol route evidence drifted")
    historical_route = {
        "codex_command": [prepared["executable"]],
        "codex_cli_version": effective["codex_cli_version"],
        "codex_command_identity": effective["codex_command_identity"],
    }
    original = execution.validate_live_sol_route
    execution.validate_live_sol_route = lambda _queue, broker_factory=None: (
        historical_route,
        dict(prepared["route_evidence"]),
    )
    try:
        outcome = execution.verify_predecessor_receipt(
            _sol_event(execution, root, row),
            execution_root=Path(execution_root), queue_root=Path(queue_root),
            frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        )
    finally:
        execution.validate_live_sol_route = original
    expected = {
        "accepted": False,
        "local_lifecycle_verified": True,
        "native_endpoint_contact_cardinality": "unproven",
        "reason": "local_codex_thread_events_do_not_attest_native_endpoint_contact_cardinality",
    }
    if outcome != expected:
        raise ValueError("HANNA matched readout Sol lifecycle ceiling drifted")
    final = _stable_bytes(root / "raw-codex-final-response.bin")
    try:
        value = json.loads(final.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA matched readout Sol final response is invalid") from error
    v2 = execution._load_predecessor()._load_v3().v2_module()
    scores = v2._validate_scores(value)
    return {
        "request": _stable_bytes(root / "prompt-request.bin"),
        "schema": _stable_bytes(root / "response-schema.json"),
        "scores": scores,
        "identity": receipt["identity"],
        "final_response_sha256": sha256_bytes(final),
        "evidence_status": "local_codex_lifecycle_verified_native_endpoint_contact_cardinality_unproven",
    }


def _verify_grok(
    admission: ModuleType, *, documents_root: Path, row: Mapping[str, Any],
    frozen_successor_path: Path, hanna_csv_path: Path,
) -> dict[str, Any]:
    cell_id = row["cell_id"]
    output_root = Path(documents_root) / f"cwr-hanna-v4-native-observations-f22bf26-{cell_id}"
    root = output_root / cell_id
    proof_path = Path(documents_root) / f"cwr-hanna-v4-native-admission-proof-f22bf26-{cell_id}.json"
    proof = _read_canonical(proof_path)
    inventory = admission._plain_inventory(root, admission.DESTINATION_FILES)
    if (
        proof.get("format_version") != 1
        or proof.get("study_id") != admission.STUDY_ID
        or proof.get("kind") != "completed_grok_admission_proof"
        or proof.get("cell_id") != cell_id
        or Path(proof.get("destination_root", "")) != root
        or proof.get("destination_inventory") != inventory
        or proof.get("admit_py_sha256") != ADMISSION_SHA256
        or proof.get("admission_contract_sha256") != ADMISSION_CONTRACT_SHA256
        or proof.get("source_exec_executor_sha256") != admission.EXEC_SHA256
        or proof.get("predecessor_executor_sha256") != admission.PREDECESSOR_SHA256
        or proof.get("predecessor_contract_sha256") != admission.PREDECESSOR_CONTRACT_SHA256
        or proof.get("provider_calls_made") != 0
    ):
        raise ValueError("HANNA matched readout Grok admission proof drifted")
    predecessor, _execution_v1 = admission._load_pinned()
    prepared = admission._read_canonical(predecessor, root / "prepared.json", "Grok prepared")
    result = predecessor._validate_persisted_result(
        root, row=row, prepared=prepared, inventory_state="native_returned_unprojected"
    )
    request = _stable_bytes(root / "native-request.bin")
    response = _stable_bytes(root / "native-response.bin")
    payload = _stable_bytes(root / "outbound-payload.json")
    expected_payload = predecessor._payload(
        predecessor._load_v3(), row,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    parsed = json.loads(payload.decode("utf-8"))
    components = parsed.get("components", {})
    schema = components.get("response_schema", "").encode("utf-8")
    if (
        payload != expected_payload
        or components.get("task_payload", "").encode("utf-8") != request
        or sha256_bytes(request) != row["task_payload_sha256"]
        or sha256_bytes(schema) != row["response_schema_sha256"]
        or proof.get("native_request_sha256") != sha256_bytes(request)
        or proof.get("native_response_sha256") != sha256_bytes(response)
        or result.get("native_request_sha256") != sha256_bytes(request)
        or result.get("native_response_sha256") != sha256_bytes(response)
    ):
        raise ValueError("HANNA matched readout Grok request/response/prompt binding drifted")
    identity = predecessor._validate_identity(result.get("identity"), row)
    expected_deduplication = {
        "cell_id": cell_id,
        "contact_id": identity["contact_id"],
        "session_id": identity["session_id"],
        "native_request_sha256": sha256_bytes(request),
        "native_response_sha256": sha256_bytes(response),
    }
    if (
        proof.get("destination_result_sha256") != sha256_bytes(_stable_bytes(root / "result.json"))
        or proof.get("source_identity_sha256") != predecessor.digest(identity)
        or proof.get("deduplication_key") != expected_deduplication
    ):
        raise ValueError("HANNA matched readout Grok admission identity proof drifted")
    scores, coverage = predecessor._extract_native(response, row=row, identity=identity)
    return {
        "request": request,
        "schema": schema,
        "scores": scores,
        "coverage": coverage,
        "identity": identity,
        "native_response_sha256": sha256_bytes(response),
        "evidence_status": "admitted_grok_native_observation",
    }


def _public_pair(
    *, sol_row: Mapping[str, Any], grok_row: Mapping[str, Any], sol: Mapping[str, Any], grok: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        sol_row["item_id"] != grok_row["item_id"]
        or sol_row["candidate_id"] != grok_row["candidate_id"]
        or sol["request"] != grok["request"]
        or sol["schema"] != grok["schema"]
        or sha256_bytes(sol["request"]) != sol_row["task_payload_sha256"]
        or sha256_bytes(sol["schema"]) != sol_row["response_schema_sha256"]
    ):
        raise ValueError("HANNA matched readout exact prompt/schema pair is misassociated")
    differences = {
        dimension: _rounded(abs(float(grok["scores"][dimension]) - float(sol["scores"][dimension])))
        for dimension in DIMENSIONS
    }
    coverage = {dimension: bool(grok["coverage"][dimension]) for dimension in DIMENSIONS}
    grok_endpoint_identity = {field: grok["identity"][field] for field in IDENTITY_FIELDS}
    sol_endpoint_identity = {field: sol["identity"][field] for field in IDENTITY_FIELDS}
    if (
        grok_endpoint_identity != EXPECTED_ENDPOINT_IDENTITIES["grok"]
        or sol_endpoint_identity != EXPECTED_ENDPOINT_IDENTITIES["sol"]
    ):
        raise ValueError("HANNA matched readout endpoint provider/model/reasoning identity drifted")
    return {
        "pair_id": "grok-sol-pair-" + sha256({
            "grok_cell_id": grok_row["cell_id"], "sol_cell_id": sol_row["cell_id"]
        })[:16],
        "item_id": sol_row["item_id"],
        "candidate_id": sol_row["candidate_id"],
        "grok_cell_id": grok_row["cell_id"],
        "sol_cell_id": sol_row["cell_id"],
        "prompt_sha256": sha256_bytes(sol["request"]),
        "response_schema_sha256": sha256_bytes(sol["schema"]),
        "grok_scores": {dimension: _rounded(grok["scores"][dimension]) for dimension in DIMENSIONS},
        "grok_coverage": coverage,
        "covered_for_paired_aggregate": coverage,
        "uncovered_dimensions": [dimension for dimension in DIMENSIONS if not coverage[dimension]],
        "sol_local_lifecycle_scores": {
            dimension: _rounded(sol["scores"][dimension]) for dimension in DIMENSIONS
        },
        "absolute_difference": differences,
        "grok_evidence_status": grok["evidence_status"],
        "sol_evidence_status": sol["evidence_status"],
        "sol_native_endpoint_contact_cardinality": "unproven",
        "grok_endpoint_identity": grok_endpoint_identity,
        "sol_endpoint_identity": sol_endpoint_identity,
    }


def _reserve_identity(
    identity: Mapping[str, Any], *, provider_contacts: set[tuple[str, str]],
    provider_sessions: set[tuple[str, str]],
) -> None:
    provider = identity["provider"]
    contact = (provider, identity["contact_id"])
    session = (provider, identity["session_id"])
    if contact in provider_contacts:
        raise ValueError("HANNA matched readout duplicate provider/contact identity")
    if session in provider_sessions:
        raise ValueError("HANNA matched readout duplicate provider/session identity")
    provider_contacts.add(contact)
    provider_sessions.add(session)


def _reserve_item_candidate(
    item_id: str, candidate_id: str, *, item_candidates: set[tuple[str, str]],
) -> None:
    item_candidate = (item_id, candidate_id)
    if item_candidate in item_candidates:
        raise ValueError("HANNA matched readout duplicate item/candidate pair")
    item_candidates.add(item_candidate)


def _aggregate_pairs(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible = {
        dimension: [pair for pair in pairs if pair["covered_for_paired_aggregate"][dimension]]
        for dimension in DIMENSIONS
    }
    if any(not dimension_pairs for dimension_pairs in eligible.values()):
        raise ValueError("HANNA matched readout has no covered pair for a required dimension")
    mean_abs = {
        dimension: _rounded(statistics.fmean(
            pair["absolute_difference"][dimension] for pair in dimension_pairs
        ))
        for dimension, dimension_pairs in eligible.items()
    }
    mean_grok = {
        dimension: _rounded(statistics.fmean(
            pair["grok_scores"][dimension] for pair in dimension_pairs
        ))
        for dimension, dimension_pairs in eligible.items()
    }
    mean_sol = {
        dimension: _rounded(statistics.fmean(
            pair["sol_local_lifecycle_scores"][dimension] for pair in dimension_pairs
        ))
        for dimension, dimension_pairs in eligible.items()
    }
    all_eligible_differences = [
        pair["absolute_difference"][dimension]
        for dimension, dimension_pairs in eligible.items()
        for pair in dimension_pairs
    ]
    covered_counts = {dimension: len(dimension_pairs) for dimension, dimension_pairs in eligible.items()}
    return {
        "coverage_policy": "exclude_uncovered_grok_dimensions_from_all_paired_aggregates",
        "covered_pair_count_by_dimension": covered_counts,
        "uncovered_pair_count_by_dimension": {
            dimension: len(pairs) - covered_counts[dimension] for dimension in DIMENSIONS
        },
        "mean_absolute_difference_by_dimension_covered_only": mean_abs,
        "overall_mean_absolute_difference_covered_only": _rounded(
            statistics.fmean(all_eligible_differences)
        ),
        "overall_covered_pair_dimension_count": len(all_eligible_differences),
        "mean_grok_score_by_dimension_covered_only": mean_grok,
        "mean_sol_local_lifecycle_score_by_dimension_covered_only": mean_sol,
    }


def publication_result(readout: Mapping[str, Any]) -> dict[str, Any]:
    public_pair_fields = (
        "pair_id", "item_id", "candidate_id", "grok_cell_id", "sol_cell_id",
        "prompt_sha256", "uncovered_dimensions", "absolute_difference",
    )
    pairs = readout.get("pairs", ())
    if readout.get("pair_count") != len(SOL_SUCCESS_ROOTS) or len(pairs) != len(SOL_SUCCESS_ROOTS):
        raise ValueError("HANNA matched readout publication requires the frozen 33-success set")
    expected_claims = {
        "selection": False,
        "substitution": False,
        "generalization": False,
        "provider_quality_ranking": False,
    }
    expected_ceiling = "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"
    expected_pair_sol_status = (
        "local_codex_lifecycle_verified_native_endpoint_contact_cardinality_unproven"
    )
    expected_inputs = {
        "frozen_successor_sha256": FROZEN_SUCCESSOR_SHA256,
        "hanna_csv_sha256": HANNA_CSV_SHA256,
        "exec_v3_sha256": EXEC_V3_SHA256,
        "exec_v3_contract_sha256": EXEC_V3_CONTRACT_SHA256,
        "admission_sha256": ADMISSION_SHA256,
        "admission_contract_sha256": ADMISSION_CONTRACT_SHA256,
        "analyzer_sha256": sha256_bytes(_stable_bytes(Path(__file__))),
        "analyzer_contract_sha256": sha256_bytes(_stable_bytes(ANALYZER_CONTRACT_PATH)),
    }
    if (
        readout.get("format_version") != 1
        or readout.get("study_id") != STUDY_ID
        or readout.get("claims") != expected_claims
        or readout.get("sol_evidence_ceiling") != expected_ceiling
        or readout.get("story_text_included") is not False
        or readout.get("inputs") != expected_inputs
    ):
        raise ValueError("HANNA matched readout publication semantics drifted")
    sol_cells = [pair.get("sol_cell_id") for pair in pairs]
    grok_cells = [pair.get("grok_cell_id") for pair in pairs]
    item_candidates = [(pair.get("item_id"), pair.get("candidate_id")) for pair in pairs]
    if (
        set(sol_cells) != set(SOL_CELLS)
        or len(set(grok_cells)) != len(SOL_SUCCESS_ROOTS)
        or len(set(item_candidates)) != len(SOL_SUCCESS_ROOTS)
    ):
        raise ValueError("HANNA matched readout publication pair identities drifted")
    for pair in pairs:
        expected_pair_id = "grok-sol-pair-" + sha256({
            "grok_cell_id": pair["grok_cell_id"], "sol_cell_id": pair["sol_cell_id"]
        })[:16]
        coverage = pair.get("covered_for_paired_aggregate")
        differences = {
            dimension: _rounded(abs(
                float(pair["grok_scores"][dimension])
                - float(pair["sol_local_lifecycle_scores"][dimension])
            ))
            for dimension in DIMENSIONS
        }
        if (
            pair.get("pair_id") != expected_pair_id
            or coverage != pair.get("grok_coverage")
            or pair.get("uncovered_dimensions") != [
                dimension for dimension in DIMENSIONS if not coverage[dimension]
            ]
            or pair.get("absolute_difference") != differences
            or pair.get("grok_endpoint_identity") != EXPECTED_ENDPOINT_IDENTITIES["grok"]
            or pair.get("sol_endpoint_identity") != EXPECTED_ENDPOINT_IDENTITIES["sol"]
            or pair.get("grok_evidence_status") != "admitted_grok_native_observation"
            or pair.get("sol_evidence_status") != expected_pair_sol_status
            or pair.get("sol_native_endpoint_contact_cardinality") != "unproven"
        ):
            raise ValueError("HANNA matched readout publication pair semantics drifted")
    if readout.get("aggregate") != _aggregate_pairs(pairs):
        raise ValueError("HANNA matched readout publication semantics drifted")
    response_schema_hashes = {pair["response_schema_sha256"] for pair in readout["pairs"]}
    if len(response_schema_hashes) != 1:
        raise ValueError("HANNA matched readout publication response schemas drifted")
    result = {
        "format_version": readout["format_version"],
        "study_id": readout["study_id"],
        "kind": "public_matched_grok_sol_33_pair_descriptive_result",
        "pair_count": readout["pair_count"],
        "inputs": expected_inputs,
        "response_schema_sha256": next(iter(response_schema_hashes)),
        "pairs": [
            {field: pair[field] for field in public_pair_fields}
            for pair in readout["pairs"]
        ],
        "aggregate": {
            key: value for key, value in readout["aggregate"].items()
            if key not in {
                "mean_grok_score_by_dimension_covered_only",
                "mean_sol_local_lifecycle_score_by_dimension_covered_only",
            }
        },
        "endpoint_identities": EXPECTED_ENDPOINT_IDENTITIES,
        "grok_evidence_status": "admitted_grok_native_observation",
        "sol_evidence_ceiling": expected_ceiling,
        "claims": expected_claims,
        "story_text_included": False,
    }
    return result


def build_readout(
    *, pair_specs: Sequence[Mapping[str, Any]], documents_root: Path, queue_root: Path,
    frozen_successor_path: Path, hanna_csv_path: Path,
) -> dict[str, Any]:
    if len(pair_specs) != len(SOL_SUCCESS_ROOTS):
        raise ValueError("HANNA matched readout requires exactly the frozen 33-success set")
    sol_ids = [spec.get("sol_cell_id") for spec in pair_specs]
    roots = [str(Path(spec.get("sol_execution_root", ""))) for spec in pair_specs]
    expected_roots = {
        cell_id: Path(os.path.abspath(Path(documents_root) / root_name))
        for cell_id, root_name in SOL_SUCCESS_ROOTS
    }
    if (
        len(set(sol_ids)) != len(SOL_SUCCESS_ROOTS)
        or len(set(roots)) != len(SOL_SUCCESS_ROOTS)
        or set(sol_ids) != set(SOL_CELLS)
        or set(sol_ids) & EXCLUDED_TERMINAL_CELLS
        or any(
            Path(os.path.abspath(Path(spec["sol_execution_root"]))) != expected_roots[spec["sol_cell_id"]]
            for spec in pair_specs
        )
    ):
        raise ValueError("HANNA matched readout rejects duplicate or misassociated pair specifications")
    execution, admission = _load_dependencies()
    by_cell, matched = _schedule_rows(
        execution,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    pairs = []
    provider_contacts: set[tuple[str, str]] = set()
    provider_sessions: set[tuple[str, str]] = set()
    item_candidates: set[tuple[str, str]] = set()
    grok_cells: set[str] = set()
    for spec in pair_specs:
        sol_row = by_cell[spec["sol_cell_id"]]
        grok_row = matched[spec["sol_cell_id"]]
        if grok_row["cell_id"] in grok_cells:
            raise ValueError("HANNA matched readout duplicate Grok pair")
        grok_cells.add(grok_row["cell_id"])
        _reserve_item_candidate(
            sol_row["item_id"], sol_row["candidate_id"], item_candidates=item_candidates
        )
        sol = _verify_sol(
            execution, execution_root=Path(spec["sol_execution_root"]), row=sol_row,
            queue_root=Path(queue_root), frozen_successor_path=Path(frozen_successor_path),
            hanna_csv_path=Path(hanna_csv_path),
        )
        grok = _verify_grok(
            admission, documents_root=Path(documents_root), row=grok_row,
            frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        )
        for evidence in (sol, grok):
            _reserve_identity(
                evidence["identity"], provider_contacts=provider_contacts,
                provider_sessions=provider_sessions,
            )
        pairs.append(_public_pair(sol_row=sol_row, grok_row=grok_row, sol=sol, grok=grok))
    pairs.sort(key=lambda pair: pair["sol_cell_id"])
    frozen_successor_sha256 = sha256_bytes(_stable_bytes(Path(frozen_successor_path)))
    hanna_csv_sha256 = sha256_bytes(_stable_bytes(Path(hanna_csv_path)))
    if frozen_successor_sha256 != FROZEN_SUCCESSOR_SHA256 or hanna_csv_sha256 != HANNA_CSV_SHA256:
        raise ValueError("HANNA matched readout frozen successor or HANNA CSV bytes drifted")
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "matched_grok_native_vs_sol_local_lifecycle_descriptive_readout",
        "pair_count": len(pairs),
        "inputs": {
            "frozen_successor_sha256": frozen_successor_sha256,
            "hanna_csv_sha256": hanna_csv_sha256,
            "exec_v3_sha256": EXEC_V3_SHA256,
            "exec_v3_contract_sha256": EXEC_V3_CONTRACT_SHA256,
            "admission_sha256": ADMISSION_SHA256,
            "admission_contract_sha256": ADMISSION_CONTRACT_SHA256,
            "analyzer_sha256": sha256_bytes(_stable_bytes(Path(__file__))),
            "analyzer_contract_sha256": sha256_bytes(_stable_bytes(ANALYZER_CONTRACT_PATH)),
        },
        "pairs": pairs,
        "aggregate": _aggregate_pairs(pairs),
        "sol_evidence_ceiling": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven",
        "claims": {
            "selection": False,
            "substitution": False,
            "generalization": False,
            "provider_quality_ranking": False,
        },
        "story_text_included": False,
    }
