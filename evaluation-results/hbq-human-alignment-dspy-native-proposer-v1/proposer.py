"""Development-only, one-shot Grok execution of an actual DSPy-rendered request.

This module deliberately has no evaluator, optimizer, selection, confirmation, or
runtime authority.  Preparation is provider-free: a local CaptureLM stops DSPy
after its real ChatAdapter has rendered the request.  The saved request is the
only payload execution may hand to the existing, pinned Grok queue path.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-dspy-native-proposer-v1"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
V11_STUDY_ID = "hbq-human-alignment-optimizer-v11-child20-train-screen-v1"
V4_GROK_EXEC = REPO / "evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2/executor.py"
V4_GROK_EXEC_SHA256 = "475f5d2fb02cdddcf5b14810d25ef63bd166c85f129dc64106b443f33895fbc4"
V4_HELDOUT_EXEC = REPO / "evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1/executor.py"
V4_HELDOUT_EXEC_SHA256 = "c8798475ae335b3a24f6deddbee627090718359a1e3b283396d892a15cb0720c"
V4_NATIVE_EXEC = REPO / "evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v1/executor.py"
V4_NATIVE_EXEC_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
V10_CANDIDATES = REPO / "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1/study.py"
V10_CANDIDATES_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
V11_TRAIN = REPO / "evaluation-results/hbq-human-alignment-optimizer-v11-child20-train-screen-v1/study.py"
V11_TRAIN_SHA256 = "af2d326934f51ddb83b6449a760295f46921c87189c653558de37930af018f11"

PREPARED_FILES = frozenset({
    "training-report.json", "dspy-request.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "prepared.json",
})
BOUND_FILES = PREPARED_FILES | {"authorization-acknowledgement.json"}
COMPLETED_FILES = BOUND_FILES | {
    "launch-intent.json", "adapter-stdout.bin", "adapter-control-envelope.json", "runtime-identity.json",
    "execution-receipt.json", "result.json",
}
def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(raw).hexdigest()


def stable(path: Path) -> bytes:
    value = Path(path)
    if not value.is_file() or value.is_symlink():
        raise ValueError(f"expected regular immutable file: {value}")
    return value.read_bytes()


def _load(path: Path, expected_sha256: str, name: str) -> ModuleType:
    if sha256(stable(path)) != expected_sha256:
        raise ValueError(f"pinned dependency drifted: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load pinned dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dspy() -> Any:
    try:
        import dspy  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("DSPy 3.3.1 is required for native prompt rendering") from error
    if getattr(dspy, "__version__", None) != "3.3.1":
        raise ValueError("DSPy version drifted; expected exactly 3.3.1")
    return dspy


def _plain(path: Path, *, directory: bool) -> bool:
    return path.exists() and not path.is_symlink() and (path.is_dir() if directory else path.is_file())


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite immutable artifact: {path}")
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not canonical JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"{label} is not a canonical object")
    return value


def _safe_new_root(root: Path) -> None:
    absolute = Path(os.path.abspath(root))
    if root.exists():
        raise ValueError("proposer root must be fresh")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True):
            raise ValueError(f"unsafe output ancestry: {current}")


def _disjoint_output(root: Path, *sources: Path) -> None:
    target = Path(root).resolve()
    for source in sources:
        source_path = Path(source).resolve()
        protected = source_path if source_path.is_dir() else source_path.parent
        if target == protected or protected in target.parents:
            raise ValueError(f"output root is inside immutable source inventory: {protected}")


def _parent() -> dict[str, Any]:
    v10 = _load(V10_CANDIDATES, V10_CANDIDATES_SHA256, "_native_dspy_v10")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_native_dspy_validation")
    rows = [row for row in v10._panel(validation) if row.get("candidate_id") == CHILD20]
    if len(rows) != 1:
        raise ValueError("pinned child20 candidate is absent or ambiguous")
    row = rows[0]
    required = {"candidate_id", "candidate_sha256", "instruction", "instruction_sha256", "profile_raw", "profile_sha256", "kind"}
    if set(row) != required or row["kind"] != "retained_child20" or not isinstance(row["instruction"], bytes) or not isinstance(row["profile_raw"], bytes):
        raise ValueError("pinned child20 candidate shape drifted")
    if sha256(row["instruction"]) != row["instruction_sha256"] or sha256(row["profile_raw"]) != row["profile_sha256"]:
        raise ValueError("pinned child20 candidate bytes drifted")
    return {
        "candidate_id": row["candidate_id"], "candidate_sha256": row["candidate_sha256"],
        "instruction_bytes": row["instruction"], "profile_bytes": row["profile_raw"],
        "instruction_sha256": row["instruction_sha256"], "profile_sha256": row["profile_sha256"],
    }


def _training_report(*, v11_grok_root: Path, v11_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", v11_acknowledgement_sha256):
        raise ValueError("V11 acknowledgement must be a lowercase SHA-256")
    study = _load(V11_TRAIN, V11_TRAIN_SHA256, "_native_dspy_v11_train")
    report = study.report(
        output_root=Path(v11_grok_root), authorization_acknowledgement_sha256=v11_acknowledgement_sha256,
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract),
    )
    if (not isinstance(report, dict) or report.get("study_id") != V11_STUDY_ID
            or report.get("kind") != "receipt_derived_8_cell_grok_train_screen_report"
            or report.get("endpoint") != "grok_primary" or report.get("partition") != "train"
            or report.get("unique_request_ids") != 8 or report.get("unique_session_ids") != 8
            or report.get("confirmation") is not None):
        raise ValueError("V11 TRAIN receipt replay drifted")
    cells = report.get("cells")
    if not isinstance(cells, list) or len(cells) != 8 or len({row.get("cell_id") for row in cells if isinstance(row, dict)}) != 8:
        raise ValueError("V11 TRAIN receipt replay geometry drifted")
    per_candidate: dict[str, int] = {"candidate-102cc7f06c9a99a7": 0, CHILD20: 0}
    for row in cells:
        if not isinstance(row, dict) or row.get("partition") != "train" or row.get("candidate_id") not in per_candidate:
            raise ValueError("V11 TRAIN replay contains a non-TRAIN or unknown candidate cell")
        per_candidate[row["candidate_id"]] += 1
    if per_candidate != {"candidate-102cc7f06c9a99a7": 4, CHILD20: 4}:
        raise ValueError("V11 TRAIN replay pair geometry drifted")
    return report


def _diagnostics(report: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    cells = report.get("cells")
    if not isinstance(cells, list):
        raise TypeError("V11 TRAIN report cells are invalid")
    commitments = {
        "native_training_evidence_sha256": sha256(canonical(dict(report))),
        "endpoint_sha256": sha256(canonical(cells)),
        "train_partition": "train",
    }
    examples = []
    for row in cells:
        if not isinstance(row, Mapping) or row.get("candidate_id") != CHILD20:
            continue
        scores, target = row.get("scores"), row.get("target")
        if not isinstance(scores, Mapping) or not isinstance(target, Mapping) or set(scores) != set(target):
            raise ValueError("V11 child20 TRAIN scores or targets drifted")
        errors = {
            dimension: {"signed_error": float(scores[dimension]) - float(target[dimension]), "absolute_error": abs(float(scores[dimension]) - float(target[dimension]) )}
            for dimension in sorted(scores)
        }
        examples.append({"cell_id": row["cell_id"], "prompt_group_id": row["prompt_group_id"], "scores": dict(scores), "target": dict(target), "errors": errors})
    if len(examples) != 4:
        raise ValueError("V11 child20 TRAIN diagnostic example geometry drifted")
    teaching_input = {
        "partition": "train", "candidate_id": CHILD20, "source_report_sha256": commitments["native_training_evidence_sha256"],
        "examples": sorted(examples, key=lambda row: row["cell_id"]),
        "instruction": "Make one modest evidence-aware edit to the parent instruction. Keep the supplied profile unchanged. Do not claim evaluation, selection, confirmation, or runtime authority.",
    }
    return commitments, teaching_input


class _CapturedDSPyRequest(Exception):
    pass


def _signature(dspy: Any) -> Any:
    class NativeDescendantSignature(dspy.Signature):
        """Write one versionable instruction edit from frozen TRAIN-only diagnostics."""
        parent_candidate_id: str = dspy.InputField()
        parent_instruction: str = dspy.InputField()
        parent_profile_json: str = dspy.InputField()
        frozen_train_diagnostics_json: str = dspy.InputField()
        descendant_instruction: str = dspy.OutputField()
    return NativeDescendantSignature


def _render_dspy_request(*, parent: Mapping[str, Any], diagnostics: Mapping[str, str], teaching_input: Mapping[str, Any]) -> tuple[dict[str, Any], bytes, Any, Any, Mapping[str, Any], str]:
    """Run Predict once against a local capture LM; the sentinel precludes contact or fallback."""
    dspy = _dspy()
    diagnostic_sha = sha256(diagnostics)

    proposer = dspy.Predict(_signature(dspy))
    try:
        parent_instruction = parent["instruction_bytes"].decode("utf-8")
        parent_profile = json.loads(parent["profile_bytes"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("pinned child20 parent is not readable versionable text/profile") from error
    inputs = {
        "parent_candidate_id": parent["candidate_id"], "parent_instruction": parent_instruction,
        "parent_profile_json": canonical(parent_profile).decode("utf-8"),
        "frozen_train_diagnostics_json": canonical(dict(teaching_input)).decode("utf-8"),
    }

    class CaptureLM(dspy.BaseLM):
        forward_contract = "typed_lm"

        def __init__(self) -> None:
            super().__init__(model="grok-4.6", model_type="chat", cache=False, num_retries=0)
            self.request: Any | None = None

        def forward(self, request: Any) -> Any:
            if self.request is not None:
                raise ValueError("DSPy tried to render more than one request")
            if getattr(request, "tools", None):
                raise ValueError("DSPy request unexpectedly enabled tools")
            self.request = request
            raise _CapturedDSPyRequest()

    lm = CaptureLM()
    adapter = dspy.ChatAdapter(use_native_function_calling=False, use_json_adapter_fallback=False)
    try:
        with dspy.context(lm=lm, adapter=adapter):
            proposer(**inputs)
    except _CapturedDSPyRequest:
        pass
    else:
        raise ValueError("DSPy capture unexpectedly completed without its local sentinel")
    if lm.request is None:
        raise ValueError("DSPy did not render an LM request")
    request = lm.request.model_dump(mode="json", exclude_none=True)
    if request.get("model") != "grok-4.6" or request.get("tools") not in ([], None) or not isinstance(request.get("messages"), list) or not request["messages"]:
        raise ValueError("DSPy rendered request policy drifted")
    payload = canonical(request)
    return request, payload, adapter, proposer, inputs, diagnostic_sha


def _schema() -> bytes:
    return canonical({
        "$schema_version": 1, "type": "object", "additionalProperties": False,
        "required": ["completion"], "properties": {"completion": {"type": "string", "minLength": 1}},
    })


def _route(queue_root: Path) -> tuple[ModuleType, ModuleType, Any, dict[str, Any], dict[str, Any]]:
    grok = _load(V4_GROK_EXEC, V4_GROK_EXEC_SHA256, "_native_dspy_grok")
    heldout = _load(V4_HELDOUT_EXEC, V4_HELDOUT_EXEC_SHA256, "_native_dspy_heldout")
    native = _load(V4_NATIVE_EXEC, V4_NATIVE_EXEC_SHA256, "_native_dspy_native")
    route, evidence = native.validate_live_grok_route(Path(queue_root))
    if (sha256(stable(grok.GROK_ADAPTER_PATH)) != grok.GROK_ADAPTER_SHA256
            or sha256(stable(grok.CAPTURE_WRAPPER_PATH)) != grok.CAPTURE_WRAPPER_SHA256
            or route.get("adapter") != "grok_exec" or route.get("nonvisual_max_turns") != 4
            or len(route.get("command", [])) < 2 or Path(route["command"][1]).resolve() != grok.GROK_ADAPTER_PATH.resolve()):
        raise ValueError("pinned Grok shared route identity drifted")
    # The shared route remains its live, independently validated four-turn inventory.
    # Only this task-local adapter invocation receives the reviewed one-turn override.
    effective_route = {**route, "nonvisual_max_turns": 1}
    return grok, heldout, native._load_broker_class()(Path(queue_root)), effective_route, evidence


def _artifacts(*, report: Mapping[str, Any], request: Mapping[str, Any], payload: bytes, parent: Mapping[str, Any], diagnostics: Mapping[str, str], route: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    schema = _schema()
    route_identity = {name: route[name] for name in ("name", "provider", "model", "adapter", "destination")}
    disclosure = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure",
        "route_identity": route_identity,
        "payload": {"bytes": len(payload), "sha256": sha256(payload), "text": payload.decode("utf-8")},
        "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")},
        "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False,
        "nonvisual_max_turns": 1, "automatic_retries": False, "provider_calls_made": 0, "process_launches": 0,
    }
    prepared = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "dspy_native_proposer_preparation",
        "candidate_commitment_algorithm": "canonical_json_sha256_v1", "dspy_version": "3.3.1",
        "parent_candidate_id": parent["candidate_id"], "parent_candidate_sha256": parent["candidate_sha256"],
        "parent_instruction_sha256": parent["instruction_sha256"], "parent_profile_sha256": parent["profile_sha256"],
        "training_report_sha256": sha256(canonical(dict(report))), "training_diagnostics": dict(diagnostics),
        "dspy_request_sha256": sha256(canonical(dict(request))), "payload_sha256": sha256(payload),
        "response_schema_sha256": sha256(schema), "disclosure_sha256": sha256(canonical(disclosure)),
        "route_evidence": dict(evidence), "live_route_nonvisual_max_turns": 4, "effective_route_nonvisual_max_turns": 1,
        "provider_calls_made": 0, "process_launches": 0,
        "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "selection_authority": "none",
    }
    files = {
        "training-report.json": canonical(dict(report)), "dspy-request.json": canonical(dict(request)),
        "prompt-request.bin": payload, "response-schema.json": schema, "disclosure.json": canonical(disclosure),
        "prepared.json": canonical(prepared),
    }
    return prepared, files


def _verify_root(root: Path, expected_files: Mapping[str, bytes]) -> None:
    if not _plain(root, directory=True):
        raise ValueError("prepared root is missing or unsafe")
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != set(expected_files) or any(not _plain(entry, directory=False) for entry in entries.values()):
        raise ValueError("prepared root inventory drifted")
    for name, raw in expected_files.items():
        if stable(root / name) != raw:
            raise ValueError(f"prepared artifact drifted: {name}")


def prepare_one(*, output_root: Path, v11_grok_root: Path, v11_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, queue_root: Path) -> dict[str, Any]:
    """Provider-free prepare phase.  A later scoped acknowledgement is required to execute."""
    root = Path(output_root)
    _safe_new_root(root)
    _disjoint_output(root, Path(v11_grok_root), Path(split_manifest), Path(hanna_csv), Path(successor_contract), Path(queue_root))
    parent = _parent()
    report = _training_report(
        v11_grok_root=Path(v11_grok_root), v11_acknowledgement_sha256=v11_acknowledgement_sha256,
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract),
    )
    diagnostics, teaching_input = _diagnostics(report)
    request, payload, _adapter, _proposer, _inputs, _diagnostic_sha = _render_dspy_request(parent=parent, diagnostics=diagnostics, teaching_input=teaching_input)
    _grok, _heldout, _broker, route, evidence = _route(Path(queue_root))
    prepared, files = _artifacts(report=report, request=request, payload=payload, parent=parent, diagnostics=diagnostics, route=route, evidence=evidence)
    root.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        _write_new(root / name, raw)
    return {
        "study_id": STUDY_ID, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0,
        "prepared_sha256": sha256(canonical(prepared)), "disclosure_sha256": sha256(files["disclosure.json"]),
        "payload_sha256": sha256(payload),
    }


def _stored_prepared(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not _plain(root, directory=True):
        raise ValueError("prepared root is missing or unsafe")
    names = {entry.name for entry in root.iterdir()}
    if names not in (set(PREPARED_FILES), set(BOUND_FILES)):
        raise ValueError("prepared root has an unexpected inventory")
    raw = {name: stable(root / name) for name in names}
    _object(raw["training-report.json"], label="stored V11 report")
    request = _object(raw["dspy-request.json"], label="stored DSPy request")
    schema = _object(raw["response-schema.json"], label="stored response schema")
    disclosure = _object(raw["disclosure.json"], label="stored disclosure")
    prepared = _object(raw["prepared.json"], label="stored prepared record")
    if raw["prompt-request.bin"] != canonical(request) or raw["response-schema.json"] != _schema() or schema != json.loads(_schema().decode("utf-8")):
        raise ValueError("stored DSPy request, payload, or schema drifted")
    required = {
        "format_version", "study_id", "kind", "candidate_commitment_algorithm", "dspy_version", "parent_candidate_id",
        "parent_candidate_sha256", "parent_instruction_sha256", "parent_profile_sha256", "training_report_sha256",
        "training_diagnostics", "dspy_request_sha256", "payload_sha256", "response_schema_sha256", "disclosure_sha256",
        "route_evidence", "live_route_nonvisual_max_turns", "effective_route_nonvisual_max_turns", "provider_calls_made", "process_launches", "confirmation", "runtime_authority", "selection_authority",
    }
    if (set(prepared) != required or prepared.get("format_version") != 1 or prepared.get("study_id") != STUDY_ID
            or prepared.get("kind") != "dspy_native_proposer_preparation" or prepared.get("candidate_commitment_algorithm") != "canonical_json_sha256_v1"
            or prepared.get("dspy_version") != "3.3.1" or prepared.get("provider_calls_made") != 0
            or prepared.get("process_launches") != 0 or prepared.get("confirmation") != {"status": "unopened", "cells": 0}
            or prepared.get("runtime_authority") != "none" or prepared.get("selection_authority") != "none"
            or prepared.get("live_route_nonvisual_max_turns") != 4 or prepared.get("effective_route_nonvisual_max_turns") != 1):
        raise ValueError("stored preparation policy drifted")
    if (prepared.get("training_report_sha256") != sha256(raw["training-report.json"])
            or prepared.get("dspy_request_sha256") != sha256(raw["dspy-request.json"])
            or prepared.get("payload_sha256") != sha256(raw["prompt-request.bin"])
            or prepared.get("response_schema_sha256") != sha256(raw["response-schema.json"])
            or prepared.get("disclosure_sha256") != sha256(raw["disclosure.json"])):
        raise ValueError("stored preparation hash binding drifted")
    expected_disclosure = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure",
        "route_identity": disclosure.get("route_identity"),
        "payload": {"bytes": len(raw["prompt-request.bin"]), "sha256": sha256(raw["prompt-request.bin"]), "text": raw["prompt-request.bin"].decode("utf-8")},
        "response_schema": {"bytes": len(raw["response-schema.json"]), "sha256": sha256(raw["response-schema.json"]), "text": raw["response-schema.json"].decode("utf-8")},
        "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False,
        "nonvisual_max_turns": 1, "automatic_retries": False, "provider_calls_made": 0, "process_launches": 0,
    }
    route = disclosure.get("route_identity")
    if (not isinstance(route, dict) or set(route) != {"name", "provider", "model", "adapter", "destination"}
            or route.get("provider") != "xai_grok_build" or route.get("model") != "grok-4.6" or route.get("adapter") != "grok_exec"
            or disclosure != expected_disclosure):
        raise ValueError("stored disclosure route or payload binding drifted")
    return prepared, raw


def verify_prepared(*, output_root: Path, v11_grok_root: Path, v11_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    """Offline replay of source inputs and DSPy rendering; it makes no native call."""
    root = Path(output_root)
    prepared, raw = _stored_prepared(root)
    report = _training_report(
        v11_grok_root=Path(v11_grok_root), v11_acknowledgement_sha256=v11_acknowledgement_sha256,
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract),
    )
    parent = _parent(); diagnostics, teaching_input = _diagnostics(report)
    request, payload, _adapter, _proposer, _inputs, _diagnostic_sha = _render_dspy_request(parent=parent, diagnostics=diagnostics, teaching_input=teaching_input)
    route = _object(raw["disclosure.json"], label="stored disclosure")["route_identity"]
    _expected, files = _artifacts(report=report, request=request, payload=payload, parent=parent, diagnostics=diagnostics, route=route, evidence=prepared["route_evidence"])
    _verify_root(root, {**files, **({"authorization-acknowledgement.json": raw["authorization-acknowledgement.json"]} if "authorization-acknowledgement.json" in raw else {})})
    return {"study_id": STUDY_ID, "state": "prepared_replayed_no_contact", "provider_calls_made": 0, "process_launches": 0, "prepared_sha256": sha256(raw["prepared.json"])}


def bind_authorization(*, output_root: Path, acknowledgement_path: Path) -> dict[str, Any]:
    """Bind caller-supplied acknowledgement bytes to the already-disclosed exact payload."""
    root = Path(output_root)
    _prepared, raw = _stored_prepared(root)
    if "authorization-acknowledgement.json" in raw:
        raise ValueError("prepared root already has immutable acknowledgement bytes")
    acknowledgement_raw = stable(Path(acknowledgement_path))
    acknowledgement = _object(acknowledgement_raw, label="caller acknowledgement")
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": STUDY_ID,
        "disclosure_sha256": sha256(raw["disclosure.json"]), "acknowledgement_sha256": acknowledgement.get("acknowledgement_sha256"),
    }
    if (not re.fullmatch(r"[0-9a-f]{64}", str(acknowledgement.get("acknowledgement_sha256")))
            or acknowledgement != expected):
        raise ValueError("caller acknowledgement does not scope to this exact disclosure")
    _write_new(root / "authorization-acknowledgement.json", acknowledgement_raw)
    return {"study_id": STUDY_ID, "state": "prepared_authorized_no_contact", "provider_calls_made": 0, "process_launches": 0, "acknowledgement_sha256": sha256(acknowledgement_raw), "prepared_sha256": sha256(raw["prepared.json"])}


def _terminal(root: Path, *, state: str, detail: str | None, launches: int, control_raw: bytes = b"") -> dict[str, Any]:
    capture = root / "adapter-stdout.bin"
    if control_raw and not capture.exists():
        _write_new(capture, control_raw)
    elif capture.exists() and control_raw and stable(capture) != control_raw:
        raise ValueError("adapter stdout capture drifted")
    result = {
        "format_version": 1, "study_id": STUDY_ID, "kind": state, "detail": detail,
        "provider_calls_made": 0 if state == "definitely_not_contacted" else None,
        "process_launches": launches, "native_contact_proven": False,
        "native_endpoint_contact_cardinality": "zero" if state == "definitely_not_contacted" else "unknown",
    }
    _write_new(root / "result.json", canonical(result))
    return result


def execute_one(*, output_root: Path, queue_root: Path, allow_remote: bool, v11_grok_root: Path, v11_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    """Dispatch the already-frozen DSPy payload once; a terminal root can never resend."""
    if allow_remote is not True:
        raise ValueError("explicit allow_remote=True is required")
    root = Path(output_root)
    if any((root / name).exists() for name in ("launch-intent.json", "adapter-stdout.bin", "execution-receipt.json", "result.json")):
        raise ValueError("launched or terminal root cannot resend")
    prepared, raw = _stored_prepared(root)
    if "authorization-acknowledgement.json" not in raw:
        raise ValueError("prepare first, then bind a scoped acknowledgement before execution")
    acknowledgement = _object(raw["authorization-acknowledgement.json"], label="bound acknowledgement")
    expected_acknowledgement = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": STUDY_ID,
        "disclosure_sha256": sha256(raw["disclosure.json"]), "acknowledgement_sha256": acknowledgement.get("acknowledgement_sha256"),
    }
    if (not re.fullmatch(r"[0-9a-f]{64}", str(acknowledgement.get("acknowledgement_sha256")))
            or acknowledgement != expected_acknowledgement):
        raise ValueError("bound acknowledgement disclosure scope drifted")
    verify_prepared(
        output_root=root, v11_grok_root=Path(v11_grok_root), v11_acknowledgement_sha256=v11_acknowledgement_sha256,
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract),
    )
    try:
        grok, heldout, broker, route, evidence = _route(Path(queue_root))
        disclosure = _object(raw["disclosure.json"], label="stored disclosure")
        if disclosure["route_identity"] != {name: route[name] for name in ("name", "provider", "model", "adapter", "destination")} or prepared["route_evidence"] != evidence:
            return _terminal(root, state="definitely_not_contacted", detail="route_drift", launches=0)
    except BaseException as error:  # noqa: BLE001 - a precontact route error is terminal evidence.
        return _terminal(root, state="definitely_not_contacted", detail=type(error).__name__, launches=0)
    intent = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact",
        "prepared_sha256": sha256(raw["prepared.json"]), "payload_sha256": sha256(raw["prompt-request.bin"]),
        "route_evidence": evidence, "native_contact_proven": False,
    }
    _write_new(root / "launch-intent.json", canonical(intent))
    try:
        outcome, control_raw = heldout._grok_invoke(
            grok, broker, route, raw["prompt-request.bin"], json.loads(raw["response-schema.json"].decode("utf-8")), root / "adapter-stdout.bin",
        )
    except BaseException as error:  # noqa: BLE001 - post-launch uncertainty must strand the root.
        return _terminal(root, state="reconcile_required_after_process_launch", detail=type(error).__name__, launches=1)
    if getattr(outcome, "state", None) == "definitely_not_contacted":
        return _terminal(root, state="definitely_not_contacted", detail=getattr(outcome, "detail", None), launches=1, control_raw=control_raw)
    if getattr(outcome, "state", None) != "completed":
        return _terminal(root, state="reconcile_required_after_process_launch", detail=getattr(outcome, "detail", None), launches=1, control_raw=control_raw)
    try:
        control = _object(control_raw, label="adapter control envelope")
        result = control.get("result")
        if control.get("control") != {"version": 1, "state": "completed"} or not isinstance(result, Mapping):
            raise ValueError("adapter did not report one completed native response")
        output = result.get("output")
        runtime = result.get("runtime")
        if (not isinstance(output, Mapping) or set(output) != {"completion"} or not isinstance(output.get("completion"), str)
                or result.get("output_hash") != sha256(canonical(dict(output))) or not isinstance(runtime, Mapping)
                or runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != "grok-4.6-build"
                or runtime.get("requested_reasoning_effort") != "high" or runtime.get("nonvisual_max_turns") != 1
                or runtime.get("observed_turns") != 1):
            raise ValueError("adapter output or one-shot runtime identity drifted")
        parent = _parent(); report = _object(raw["training-report.json"], label="stored V11 report"); diagnostics, _teaching_input = _diagnostics(report)
        dspy = _dspy(); adapter = dspy.ChatAdapter(use_native_function_calling=False, use_json_adapter_fallback=False)
        parsed = adapter.parse(_signature(dspy), output["completion"])
        instruction = parsed["descendant_instruction"].encode("utf-8")
        if not instruction.strip() or len(instruction) > 16_384 or instruction == parent["instruction_bytes"] or b"\x00" in instruction:
            raise ValueError("DSPy response did not contain one distinct versionable instruction edit")
        fixed_profile = parent["profile_bytes"]
        candidate_commitment = {
            "format_version": 1, "candidate_kind": "dspy_native_train_instruction_descendant",
            "parent_candidate_sha256": parent["candidate_sha256"], "instruction_sha256": sha256(instruction),
            "profile_sha256": sha256(fixed_profile), "training_diagnostics_sha256": sha256(diagnostics),
        }
        candidate_sha = sha256(candidate_commitment)
        descendant = {
            "format_version": 1, "candidate_kind": "dspy_native_train_instruction_descendant",
            "instruction_base64": base64.b64encode(instruction).decode("ascii"),
            "profile_base64": base64.b64encode(fixed_profile).decode("ascii"), "candidate_sha256": candidate_sha,
            "parent": {"candidate_id": parent["candidate_id"], "candidate_sha256": parent["candidate_sha256"], "instruction_sha256": parent["instruction_sha256"], "profile_sha256": parent["profile_sha256"]},
            "training_diagnostics": diagnostics, "candidate_commitment": candidate_commitment,
            "selection_authority": "none", "runtime_authority": "none",
        }
        lineage = {
            "parent_candidate_id": parent["candidate_id"], "parent_candidate_sha256": parent["candidate_sha256"],
            "parent_instruction_sha256": parent["instruction_sha256"], "parent_profile_sha256": parent["profile_sha256"],
            "descendant_instruction_sha256": sha256(base64.b64decode(descendant["instruction_base64"], validate=True)),
            "descendant_profile_sha256": sha256(base64.b64decode(descendant["profile_base64"], validate=True)),
            "descendant_candidate_sha256": descendant["candidate_sha256"],
        }
        receipt = {
            "format_version": 1, "study_id": STUDY_ID, "kind": "dspy_native_grok_receipt",
            "prepared_sha256": sha256(raw["prepared.json"]), "launch_intent_sha256": sha256(canonical(intent)),
            "adapter_stdout_sha256": sha256(control_raw), "adapter_control_sha256": sha256(canonical(control)),
            "payload_sha256": sha256(raw["prompt-request.bin"]), "response_schema_sha256": sha256(raw["response-schema.json"]),
            "route_evidence": evidence, "runtime": dict(runtime), "native_contact_proven": False,
            "native_contact_observed_via_local_adapter_control": True, "native_endpoint_contact_cardinality": "unproven",
            "provider_calls_made": None, "process_launches": 1,
            "lineage": lineage, "descendant_sha256": sha256(canonical(descendant)),
        }
        final = {
            "format_version": 1, "study_id": STUDY_ID, "kind": "dspy_native_development_descendant",
            "descendant": descendant, "descendant_sha256": sha256(canonical(descendant)), "receipt_sha256": sha256(canonical(receipt)),
            "provider_calls_made": None, "process_launches": 1, "confirmation": {"status": "unopened", "cells": 0},
            "selection_authority": "none", "runtime_authority": "none",
        }
        if stable(root / "adapter-stdout.bin") != control_raw:
            raise ValueError("captured native stdout differs from parsed stdout")
        _write_new(root / "adapter-control-envelope.json", canonical(control))
        _write_new(root / "runtime-identity.json", canonical(dict(runtime)))
        _write_new(root / "execution-receipt.json", canonical(receipt))
        _write_new(root / "result.json", canonical(final))
        return {"study_id": STUDY_ID, "state": "native_descendant_received", "provider_calls_made": None, "process_launches": 1, "descendant_sha256": final["descendant_sha256"]}
    except BaseException as error:  # noqa: BLE001 - post-launch parse/validation uncertainty must strand the root.
        return _terminal(root, state="reconcile_required_after_process_launch", detail=type(error).__name__, launches=1, control_raw=control_raw)
