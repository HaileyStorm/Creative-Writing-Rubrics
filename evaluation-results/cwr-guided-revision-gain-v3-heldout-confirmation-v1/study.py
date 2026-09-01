"""Provider-free immutable freeze and receipt-only projection for revision-gain v3."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
STUDY_ID = "cwr-guided-revision-gain-v3-heldout-confirmation-v1"
CONTRACT_SHA256 = "0a8f8543e6cceecc9351ef191708874e7cdb51ae4e90b138e258dd9ac5de28fe"
_ITEMS = ("hanna-594", "hanna-731", "hanna-817", "hanna-907")
_INPUTS = {
    "hanna-594": {"source.md": {"bytes": 1224, "sha256": "1ac8b69bb3f547425e3a02270ed168040b15554f37859f5beaf84fdc7d8042ba"}, "prompt.md": {"bytes": 137, "sha256": "6b7fff0c3794370cee85bf2f63a80d3efc87e72e006254c048ddd37147e34025"}},
    "hanna-731": {"source.md": {"bytes": 1750, "sha256": "92b20bdd4bc34ed3c89a48918d7ce6475f85af87b7aa652b61f0d3adac10a26d"}, "prompt.md": {"bytes": 29, "sha256": "2c4f2e59857191f6cdfdde6936dc633d61f7d6e29b7f486f557d6d1068498541"}},
    "hanna-817": {"source.md": {"bytes": 499, "sha256": "62f66a845d4bf5f4bc0d2c9c8c15aa67b5ef88776793baed483ecce64052972c"}, "prompt.md": {"bytes": 185, "sha256": "f88bef9d00608441ac76b289ea3dc71c0f2a3989f4a6a205deb9c2e9c350b4ff"}},
    "hanna-907": {"source.md": {"bytes": 350, "sha256": "2c5ba1624e7e370d39e9c51f838da9fa3f27d1f5c5cb647db9da18f45e9783fc"}, "prompt.md": {"bytes": 194, "sha256": "3286f1e85780066d24b6c48f7db645648dcea6e25736248a38bcae8c414802ab"}},
}
_ARMS = ("cwr_guided", "generic_no_feedback")
_JUDGES = ("gpt-5.6-sol-high", "grok-4.6-high")
_MEASURES = ("holistic", "compact")
_ASSETS = {
    "revision_instruction": {"path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/revision-instruction.md", "sha256": "edbd7e178e5c7c65f1ec8866c423d8baf52d882610efbb173365793e55737da7"},
    "cwr_feedback": {"path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/cwr-feedback.prompt.md", "sha256": "4bb001fb7b8d3496744e4fc258c1c4bb1beb62fc2f742b1f62923b3642142f4d"},
    "cwr_feedback_schema": {"path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/cwr-feedback.schema.json", "sha256": "5a6aa2765f0f5fb6081d14b484370bf0da403ac11cc77434a941cfacb6521ad1"},
    "holistic": {"path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/holistic.prompt.md", "sha256": "96893ebc4ec0fbae33f621559d46ab79e1fda61c61c8bfdf837bb9fd5eb55e44"},
    "compact": {"path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/compact.prompt.md", "sha256": "1fa3e54b4ffaf4508d91d7852a7501e698bc039a87fdadc7951b53cf45b6714a"},
    "score_schema": {"path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/score.schema.json", "sha256": "341eafa1feb4eb35126ad8b3b5c26fa5a0d69ecd589075f9c07ad1290671d1ab"},
}
_ASSET_TEXT: dict[str, str] = {}
_V2_STUDY: Any | None = None


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_regular(path: Path, *, label: str) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError as error:
            raise ValueError(f"v3 {label} is missing: {current}") from error
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(f"v3 {label} contains a reparse point: {current}")
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise ValueError(f"v3 {label} is not a regular file")
    return path.read_bytes()


def _hex(value: object, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"v3 {label} must be lowercase SHA-256")
    return value


def _asset(key: str, value: Mapping[str, Any]) -> str:
    if key in _ASSET_TEXT:
        return _ASSET_TEXT[key]
    binding = value["predecessors"]["v2_assets"][key]
    raw = _read_regular(REPOSITORY / binding["path"], label=f"predecessor asset {key}")
    if _sha256(raw) != binding["sha256"]:
        raise ValueError(f"v3 predecessor asset {key} drifted")
    _ASSET_TEXT[key] = raw.decode("utf-8")
    return _ASSET_TEXT[key]


@lru_cache(maxsize=1)
def contract() -> dict[str, Any]:
    raw = _read_regular(CONTRACT_PATH, label="contract")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("v3 contract is invalid JSON") from error
    if not isinstance(value, dict) or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID:
        raise ValueError("v3 contract identity drifted")
    if _sha256(raw) != CONTRACT_SHA256:
        raise ValueError("v3 whole contract bytes drifted")
    predecessor = value.get("predecessors", {}).get("v1_contract", {})
    if predecessor != {"path": "evaluation-results/cwr-guided-revision-gain-v1/study-contract.json", "sha256": "035f946ebaaf9211b6b0933473dd09ce204713518a409b4b6d2bc9578c8480ab"}:
        raise ValueError("v3 V1 predecessor binding drifted")
    if _sha256(_read_regular(REPOSITORY / predecessor["path"], label="V1 predecessor contract")) != predecessor["sha256"]:
        raise ValueError("v3 V1 predecessor contract bytes drifted")
    if value.get("predecessors", {}).get("v2_assets") != _ASSETS:
        raise ValueError("v3 predecessor asset binding drifted")
    sources = value.get("sources")
    if not isinstance(sources, Mapping) or sources.get("source_root_layout") != "inputs/<item-id>/{source.md,prompt.md}" or sorted(sources.get("items", {})) != list(_ITEMS):
        raise ValueError("v3 heldout source selection drifted")
    for item in _ITEMS:
        if sources["items"][item] != _INPUTS[item]:
            raise ValueError("v3 exact V1 heldout source commitment drifted")
    routes = value.get("routes")
    if not isinstance(routes, Mapping) or routes.get("generator") != {"destination": "xai_grok_build_subscription", "model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "paid_api": False}:
        raise ValueError("v3 sole Grok generator route drifted")
    if routes.get("cwr_feedback") != {"destination": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "tools_enabled": False, "paid_api": False} or routes.get("judges") != {
        "gpt-5.6-sol-high": {"destination": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "tools_enabled": False, "paid_api": False},
        "grok-4.6-high": {"destination": "xai_grok_build_subscription", "model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "paid_api": False},
    }:
        raise ValueError("v3 endpoint route identity drifted")
    if value.get("design") != {"cycles": 1, "arms": list(_ARMS), "adaptive_repeats": False, "best_of_n": False, "tuning": False, "source_policy": "immutable_versioned_descendants_only", "endpoint_policy": "blinded_receipt_only_separate_endpoints_no_pooling"}:
        raise ValueError("v3 one-cycle nonadaptive design drifted")
    if value.get("geometry") != {"sources": 4, "revision_descendants": 8, "source_baselines": 4, "blind_targets": 12, "endpoint_cells": 48}:
        raise ValueError("v3 geometry drifted")
    if value.get("execution_status") != "NO_GO_no_disclosure_route_prepared_record_or_native_receipt_executor":
        raise ValueError("v3 execution gate drifted")
    for key in ("revision_instruction", "cwr_feedback", "cwr_feedback_schema", "holistic", "compact", "score_schema"):
        _asset(key, value)
    return value


def revision_schedule(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else value
    return [
        {"event_id": f"revision-v3-c1-{item}-grok-4.6-{arm}", "cycle": 1, "source_item_id": item, "generator_id": "grok-4.6", "guidance_arm": arm, "parent_event_id": None, "feedback_event_id": None if arm == "generic_no_feedback" else f"feedback-v3-c1-{item}-sol"}
        for item in _ITEMS for arm in _ARMS
    ]


def targets(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else value
    rows = [{"blind_target_id": f"blind-v3-{index:02d}", "kind": "source_baseline", "target_event_id": None, "source_item_id": item} for index, item in enumerate(_ITEMS, 1)]
    rows.extend({"blind_target_id": f"blind-v3-{index:02d}", "kind": "revision_descendant", "target_event_id": event["event_id"], "source_item_id": event["source_item_id"]} for index, event in enumerate(revision_schedule(value), 5))
    return rows


def endpoint_schedule(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else value
    return [
        {"endpoint_event_id": f"endpoint-v3-{target['blind_target_id']}-{measure}-{judge}", "blind_target_id": target["blind_target_id"], "measure_id": measure, "judge_route_id": judge}
        for target in targets(value) for measure in _MEASURES for judge in _JUDGES
    ]


def freeze_inputs(*, source_root: Path) -> dict[str, Any]:
    """Verify, but never copy, the authorized external V1 heldout source bytes."""
    value = contract()
    rows: list[dict[str, Any]] = []
    for item in _ITEMS:
        row: dict[str, Any] = {"item_id": item}
        for filename in ("source.md", "prompt.md"):
            raw = _read_regular(Path(source_root) / "inputs" / item / filename, label=f"external {item} {filename}")
            binding = value["sources"]["items"][item][filename]
            if {"bytes": len(raw), "sha256": _sha256(raw)} != binding:
                raise ValueError(f"v3 external {item} {filename} drifted")
            row[filename] = {"path": f"inputs/{item}/{filename}", **binding}
        rows.append(row)
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "verified_external_heldout_inputs",
        "contract_sha256": CONTRACT_SHA256,
        "source_root": str(Path(source_root).resolve()),
        "source_material_copied": False,
        "items": rows,
        "revision_schedule_sha256": _sha256(canonical(revision_schedule(value))),
        "endpoint_schedule_sha256": _sha256(canonical(endpoint_schedule(value))),
    }


def _load_frozen_inputs(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path, label="frozen heldout inputs")
    try:
        frozen = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("v3 frozen input manifest is invalid") from error
    expected_rows = [{"item_id": item, "source.md": {"path": f"inputs/{item}/source.md", **_INPUTS[item]["source.md"]}, "prompt.md": {"path": f"inputs/{item}/prompt.md", **_INPUTS[item]["prompt.md"]}} for item in _ITEMS]
    if canonical(frozen) + b"\n" != raw or frozen.get("study_id") != STUDY_ID or frozen.get("kind") != "verified_external_heldout_inputs" or frozen.get("contract_sha256") != CONTRACT_SHA256 or frozen.get("source_material_copied") is not False or not isinstance(frozen.get("source_root"), str) or frozen.get("items") != expected_rows or frozen.get("revision_schedule_sha256") != _sha256(canonical(revision_schedule())) or frozen.get("endpoint_schedule_sha256") != _sha256(canonical(endpoint_schedule())):
        raise ValueError("v3 frozen input manifest is not authenticated")
    return frozen, raw


def _read_frozen_source(frozen: Mapping[str, Any], item_id: str) -> tuple[str, str]:
    root = Path(frozen["source_root"])
    bindings = _INPUTS[item_id]
    values = []
    for filename in ("source.md", "prompt.md"):
        raw = _read_regular(root / "inputs" / item_id / filename, label=f"frozen {item_id} {filename}")
        if {"bytes": len(raw), "sha256": _sha256(raw)} != bindings[filename]:
            raise ValueError("v3 frozen source bytes drifted")
        values.append(raw.decode("utf-8"))
    return values[0], values[1]


def _pinned_cwr_question_payload() -> list[dict[str, Any]]:
    """Reuse the V2 runtime binding rather than trusting a copied question manifest."""
    global _V2_STUDY
    if _V2_STUDY is None:
        path = REPOSITORY / "evaluation-results" / "cwr-guided-revision-gain-v2-lean-pilot" / "study.py"
        spec = importlib.util.spec_from_file_location("cwr_revision_gain_v2_pinned", path)
        if spec is None or spec.loader is None:
            raise ValueError("v3 pinned V2 CWR runtime is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _V2_STUDY = module
    v1_raw = _read_regular(REPOSITORY / "evaluation-results" / "cwr-guided-revision-gain-v1" / "study-contract.json", label="V1 runtime contract")
    if _sha256(v1_raw) != "035f946ebaaf9211b6b0933473dd09ce204713518a409b4b6d2bc9578c8480ab":
        raise ValueError("v3 V1 runtime contract drifted")
    v1 = json.loads(v1_raw.decode("utf-8"))
    for path in ("src/hbqrs/runner.py", "registry/all_modules.json", "bundles/all_bundles.json"):
        binding = v1.get("cwr_runtime", {}).get("files", {}).get(path)
        actual = _read_regular(REPOSITORY / path, label=f"pinned runtime {path}")
        if not isinstance(binding, Mapping) or binding.get("bytes") != len(actual) or binding.get("sha256") != _sha256(actual):
            raise ValueError(f"v3 pinned V1 runtime {path} drifted")
    return _V2_STUDY._cwr_question_payload(_V2_STUDY.contract())


def _replay_feedback_chain(path: Path, *, expected_event_id: str, frozen: Mapping[str, Any], frozen_sha256: str) -> list[Mapping[str, str]]:
    root = Path(path)
    prepared_raw = _read_regular(root / "prepared-cell.json", label="prepared CWR feedback")
    intent_raw = _read_regular(root / "launch-intent.json", label="CWR feedback intent")
    payload_raw = _read_regular(root / "payload.json", label="CWR feedback payload")
    native_raw = _read_regular(root / "native-receipt.json", label="CWR feedback native receipt")
    response_raw = _read_regular(root / "response.json", label="CWR feedback response")
    prepared, intent, payload, native, response = (json.loads(raw.decode("utf-8")) for raw in (prepared_raw, intent_raw, payload_raw, native_raw, response_raw))
    value, expected_route = contract(), contract()["routes"]["cwr_feedback"]
    if canonical(prepared) + b"\n" != prepared_raw or canonical(intent) + b"\n" != intent_raw or canonical(payload) + b"\n" != payload_raw or canonical(native) + b"\n" != native_raw or canonical(response) + b"\n" != response_raw:
        raise ValueError("v3 CWR feedback artifacts are not canonical")
    event = next((row for row in revision_schedule(value) if row["feedback_event_id"] == expected_event_id), None)
    required_prepared = {"format_version", "study_id", "kind", "event_id", "contract_sha256", "frozen_inputs_sha256", "source_item_id", "route", "question_root", "question_payload", "runtime_contract_sha256", "payload_sha256", "provider_calls_made", "process_launches", "no_resend"}
    if event is None or set(prepared) != required_prepared or prepared.get("format_version") != 1 or prepared.get("kind") != "prepared_cwr_feedback" or prepared.get("study_id") != STUDY_ID or prepared.get("event_id") != expected_event_id or prepared.get("contract_sha256") != CONTRACT_SHA256 or prepared.get("frozen_inputs_sha256") != frozen_sha256 or prepared.get("source_item_id") != event["source_item_id"] or prepared.get("route") != expected_route or prepared.get("payload_sha256") != _sha256(payload_raw) or prepared.get("runtime_contract_sha256") != "035f946ebaaf9211b6b0933473dd09ce204713518a409b4b6d2bc9578c8480ab" or prepared.get("provider_calls_made") != 0 or prepared.get("process_launches") != 0 or prepared.get("no_resend") is not True:
        raise ValueError("v3 CWR feedback preparation lineage drifted")
    question_raw = _bound(Path(prepared.get("question_root", "")), prepared.get("question_payload"), label="pinned CWR question payload")
    source_text, source_prompt = _read_frozen_source(frozen, event["source_item_id"])
    questions = json.loads(question_raw.decode("utf-8"))
    if questions != _pinned_cwr_question_payload():
        raise ValueError("v3 CWR question payload does not match pinned runtime recomputation")
    expected_payload = {"source_text": source_text, "source_prompt": source_prompt, "question_payload": questions, "feedback_prompt": _asset("cwr_feedback", value), "response_schema": json.loads(_asset("cwr_feedback_schema", value))}
    if payload != expected_payload:
        raise ValueError("v3 CWR feedback payload reconstruction drifted")
    if intent != {"format_version": 1, "study_id": STUDY_ID, "kind": "one_launch_intent", "prepared_record_sha256": _sha256(prepared_raw), "process_launches": 1, "no_resend": True}:
        raise ValueError("v3 CWR feedback launch intent drifted")
    required = {"status", "provider_request_id", "provider_session_id", "native_response_id", "provider_model", "reasoning", "tools_enabled", "transmitted_payload_sha256", "response_sha256"}
    if set(native) != required or native.get("status") != 200 or native.get("provider_model") != expected_route["model"] or native.get("reasoning") != expected_route["reasoning"] or native.get("tools_enabled") is not False or native.get("transmitted_payload_sha256") != _sha256(payload_raw) or native.get("response_sha256") != _sha256(response_raw) or any(not isinstance(native.get(field), str) or not native[field] for field in ("provider_request_id", "provider_session_id", "native_response_id")):
        raise ValueError("v3 CWR feedback native receipt drifted")
    findings = response.get("findings") if isinstance(response, Mapping) else None
    if set(response) != {"findings"} or not isinstance(findings, list) or not findings or len(findings) > 3 or any(not isinstance(row, Mapping) or set(row) != {"location", "observation", "repair_target"} or any(not isinstance(row[key], str) or not row[key] for key in row) for row in findings):
        raise ValueError("v3 CWR feedback response schema drifted")
    return findings


def prepare_revision_cell(*, prepared_root: Path, frozen_inputs_path: Path, event_id: str, feedback_prepared_root: Path | None = None) -> dict[str, Any]:
    """Bind one exact one-cycle descendant preparation; dispatch remains closed elsewhere."""
    event = next((row for row in revision_schedule() if row["event_id"] == event_id), None)
    if event is None or Path(prepared_root).exists():
        raise ValueError("v3 revision preparation requires one fresh scheduled root")
    frozen, frozen_raw = _load_frozen_inputs(frozen_inputs_path)
    source_text, source_prompt = _read_frozen_source(frozen, event["source_item_id"])
    feedback = None
    feedback_sha = None
    if event["guidance_arm"] == "cwr_guided":
        if feedback_prepared_root is None:
            raise ValueError("v3 guided revision requires its verified CWR feedback receipt")
        feedback = _replay_feedback_chain(Path(feedback_prepared_root), expected_event_id=event["feedback_event_id"], frozen=frozen, frozen_sha256=_sha256(frozen_raw))
        feedback_sha = _sha256(_read_regular(Path(feedback_prepared_root) / "native-receipt.json", label="CWR feedback native receipt"))
    payload = revision_payload(source_text=source_text, source_prompt=source_prompt, guidance_arm=event["guidance_arm"], cwr_feedback=feedback)
    payload_path = Path(prepared_root) / "payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=False)
    payload_path.write_bytes(payload)
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_revision_cell", "event_id": event_id, "contract_sha256": CONTRACT_SHA256, "frozen_inputs_sha256": _sha256(frozen_raw), "source_item_id": event["source_item_id"], "guidance_arm": event["guidance_arm"], "generator": contract()["routes"]["generator"], "payload": _commitment(payload_path, root=Path(prepared_root)), "feedback_receipt_sha256": feedback_sha, "provider_calls_made": 0, "process_launches": 0, "no_resend": True}
    _write_once(Path(prepared_root) / "prepared-cell.json", prepared)
    return prepared


def revision_payload(*, source_text: str, source_prompt: str, guidance_arm: str, cwr_feedback: list[Mapping[str, str]] | None = None) -> bytes:
    """Build the single local payload body; no internal arm/event identity leaves this boundary."""
    value = contract()
    if guidance_arm not in _ARMS or not isinstance(source_text, str) or not isinstance(source_prompt, str):
        raise ValueError("v3 revision payload inputs are invalid")
    body: dict[str, Any] = {
        "source_prompt": source_prompt,
        "source_text": source_text,
        "revision_instruction": _asset("revision_instruction", value),
        "response_contract": {"return_only": "complete_revised_story"},
    }
    if guidance_arm == "cwr_guided":
        if not isinstance(cwr_feedback, list) or not cwr_feedback:
            raise ValueError("v3 guided revision requires frozen CWR feedback")
        if any(not isinstance(row, Mapping) or set(row) != {"location", "observation", "repair_target"} or any(not isinstance(row[field], str) or not row[field] for field in row) for row in cwr_feedback):
            raise ValueError("v3 guided revision feedback schema drifted")
        body["cwr_feedback"] = [dict(row) for row in cwr_feedback]
    elif cwr_feedback is not None:
        raise ValueError("v3 generic control must not carry CWR feedback")
    return canonical(body)


def opaque_target_id(*, blind_target_id: str, target_sha256: str) -> str:
    if blind_target_id not in {row["blind_target_id"] for row in targets()}:
        raise ValueError("v3 blind target is not scheduled")
    _hex(target_sha256, label="target commitment")
    return "target-" + _sha256(canonical({"v": 3, "target": blind_target_id, "sha": target_sha256}))[:24]


def endpoint_payload(*, blind_target_id: str, target_text: str, target_sha256: str, measure_id: str) -> bytes:
    """Return endpoint-identical serialized bytes; routes belong only to an outer envelope."""
    value = contract()
    if measure_id not in _MEASURES or not isinstance(target_text, str):
        raise ValueError("v3 endpoint payload input is invalid")
    return canonical({
        "opaque_target_id": opaque_target_id(blind_target_id=blind_target_id, target_sha256=target_sha256),
        "blind_target_text": target_text,
        "endpoint_prompt": _asset(measure_id, value),
        "response_schema": json.loads(_asset("score_schema", value)),
    })


def endpoint_envelope(*, endpoint_event_id: str, payload: bytes) -> dict[str, Any]:
    value = contract()
    event = next((row for row in endpoint_schedule(value) if row["endpoint_event_id"] == endpoint_event_id), None)
    if event is None:
        raise ValueError("v3 endpoint event is not scheduled")
    route = value["routes"]["judges"][event["judge_route_id"]]
    return {"route": dict(route), "endpoint_event_id": endpoint_event_id, "payload_sha256": _sha256(payload)}


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")


def _commitment(path: Path, *, root: Path) -> dict[str, Any]:
    raw = _read_regular(path, label="bound artifact")
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("v3 artifact escapes its approved root") from error
    return {"path": relative, "bytes": len(raw), "sha256": _sha256(raw)}


def _bound(root: Path, binding: Mapping[str, Any], *, label: str) -> bytes:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "bytes", "sha256"}:
        raise ValueError(f"v3 {label} commitment shape drifted")
    relative = binding["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"v3 {label} path is unsafe")
    path = Path(root) / relative
    if _commitment(path, root=Path(root)) != dict(binding):
        raise ValueError(f"v3 {label} commitment drifted")
    return _read_regular(path, label=label)


def _replay_revision_descendant(root: Path, record: Mapping[str, Any], event: Mapping[str, Any], frozen: Mapping[str, Any], frozen_sha256: str) -> dict[str, Any]:
    required = {"event_id", "descendant", "prepared_root", "native_receipt", "response", "feedback_root"}
    if set(record) != required or record.get("event_id") != event["event_id"]:
        raise ValueError("v3 revision descendant record drifted")
    prepared_root = Path(record.get("prepared_root", ""))
    prepared_raw = _read_regular(prepared_root / "prepared-cell.json", label="prepared Grok revision")
    native_raw = _bound(root, record.get("native_receipt"), label="Grok revision native receipt")
    response_raw = _bound(root, record.get("response"), label="Grok revision response")
    descendant_raw = _bound(root, record.get("descendant"), label="Grok revision descendant")
    prepared, native, response = (json.loads(raw.decode("utf-8")) for raw in (prepared_raw, native_raw, response_raw))
    route = contract()["routes"]["generator"]
    expected_prepared = {"format_version", "study_id", "kind", "event_id", "contract_sha256", "frozen_inputs_sha256", "source_item_id", "guidance_arm", "generator", "payload", "feedback_receipt_sha256", "provider_calls_made", "process_launches", "no_resend"}
    if canonical(prepared) + b"\n" != prepared_raw or canonical(native) + b"\n" != native_raw or canonical(response) + b"\n" != response_raw or set(prepared) != expected_prepared or prepared.get("format_version") != 1 or prepared.get("study_id") != STUDY_ID or prepared.get("kind") != "prepared_revision_cell" or prepared.get("event_id") != event["event_id"] or prepared.get("contract_sha256") != CONTRACT_SHA256 or prepared.get("frozen_inputs_sha256") != frozen_sha256 or prepared.get("source_item_id") != event["source_item_id"] or prepared.get("guidance_arm") != event["guidance_arm"] or prepared.get("generator") != route or prepared.get("provider_calls_made") != 0 or prepared.get("process_launches") != 0 or prepared.get("no_resend") is not True:
        raise ValueError("v3 prepared Grok revision lineage drifted")
    source_text, source_prompt = _read_frozen_source(frozen, event["source_item_id"])
    feedback = None
    if event["guidance_arm"] == "cwr_guided":
        if not isinstance(record.get("feedback_root"), str):
            raise ValueError("v3 guided descendant lacks replayable feedback root")
        feedback = _replay_feedback_chain(Path(record["feedback_root"]), expected_event_id=event["feedback_event_id"], frozen=frozen, frozen_sha256=frozen_sha256)
        feedback_native_sha = _sha256(_read_regular(Path(record["feedback_root"]) / "native-receipt.json", label="CWR feedback native receipt"))
        if prepared.get("feedback_receipt_sha256") != feedback_native_sha:
            raise ValueError("v3 guided descendant feedback receipt hash drifted")
    elif record.get("feedback_root") is not None or prepared.get("feedback_receipt_sha256") is not None:
        raise ValueError("v3 generic descendant carries feedback")
    payload_raw = _bound(prepared_root, prepared.get("payload"), label="prepared Grok revision payload")
    if payload_raw != revision_payload(source_text=source_text, source_prompt=source_prompt, guidance_arm=event["guidance_arm"], cwr_feedback=feedback):
        raise ValueError("v3 Grok revision payload reconstruction drifted")
    required_native = {"status", "provider_request_id", "provider_session_id", "native_response_id", "provider_model", "reasoning", "tools_enabled", "transmitted_payload_sha256", "response_sha256"}
    if set(native) != required_native or native.get("status") != 200 or native.get("provider_model") != route["model"] or native.get("reasoning") != route["reasoning"] or native.get("tools_enabled") is not False or native.get("transmitted_payload_sha256") != _sha256(payload_raw) or native.get("response_sha256") != _sha256(response_raw) or any(not isinstance(native.get(field), str) or not native[field] for field in ("provider_request_id", "provider_session_id", "native_response_id")):
        raise ValueError("v3 Grok revision native receipt drifted")
    if set(response) != {"story"} or not isinstance(response.get("story"), str) or not response["story"] or descendant_raw != response["story"].encode("utf-8"):
        raise ValueError("v3 Grok descendant bytes are not its native response")
    return dict(record["descendant"])


def _replay_target_lineage(target_root: Path, manifest_path: Path, *, blind_target_id: str) -> tuple[dict[str, Any], bytes, bytes]:
    raw = _read_regular(manifest_path, label="frozen target manifest")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("v3 frozen target manifest is invalid") from error
    required = {"format_version", "study_id", "kind", "contract_sha256", "frozen_inputs_root", "frozen_inputs", "revision_root", "revision_descendant_manifest", "targets"}
    if canonical(manifest) + b"\n" != raw or set(manifest) != required or manifest.get("format_version") != 1 or manifest.get("study_id") != STUDY_ID or manifest.get("kind") != "frozen_target_lineage" or manifest.get("contract_sha256") != CONTRACT_SHA256:
        raise ValueError("v3 frozen target lineage is not authenticated")
    frozen_root, revision_root = Path(manifest["frozen_inputs_root"]), Path(manifest["revision_root"])
    frozen_raw = _bound(frozen_root, manifest.get("frozen_inputs"), label="committed frozen input manifest")
    frozen, reread_frozen = _load_frozen_inputs(frozen_root / manifest["frozen_inputs"]["path"])
    if reread_frozen != frozen_raw:
        raise ValueError("v3 frozen input manifest reparse drifted")
    descendant_raw = _bound(revision_root, manifest.get("revision_descendant_manifest"), label="committed revision descendant manifest")
    descendants = json.loads(descendant_raw.decode("utf-8"))
    expected_events = {row["event_id"]: row for row in revision_schedule()}
    if canonical(descendants) + b"\n" != descendant_raw or descendants.get("study_id") != STUDY_ID or descendants.get("kind") != "frozen_revision_descendants" or descendants.get("contract_sha256") != CONTRACT_SHA256 or descendants.get("frozen_inputs_sha256") != _sha256(frozen_raw):
        raise ValueError("v3 revision descendant manifest drifted")
    descendant_by_event = {row.get("event_id"): row for row in descendants.get("events", []) if isinstance(row, Mapping)}
    if set(descendant_by_event) != set(expected_events):
        raise ValueError("v3 revision descendant inventory is incomplete")
    replayed_descendants = {event_id: _replay_revision_descendant(revision_root, record, expected_events[event_id], frozen, _sha256(frozen_raw)) for event_id, record in descendant_by_event.items()}
    expected_targets = {row["blind_target_id"]: row for row in targets()}
    target_by_id = {row.get("blind_target_id"): row for row in manifest.get("targets", []) if isinstance(row, Mapping)}
    if set(target_by_id) != set(expected_targets) or any(set(row) != {"blind_target_id", "target", "origin"} for row in target_by_id.values()):
        raise ValueError("v3 frozen target inventory is incomplete")
    for target_id, expected in expected_targets.items():
        row = target_by_id[target_id]
        if expected["kind"] == "source_baseline":
            origin = {"kind": "source_baseline", "source_item_id": expected["source_item_id"], "target_event_id": None, "source": _INPUTS[expected["source_item_id"]]["source.md"]}
        else:
            descendant = replayed_descendants[expected["target_event_id"]]
            origin = {"kind": "revision_descendant", "source_item_id": expected["source_item_id"], "target_event_id": expected["target_event_id"], "descendant": descendant}
        if row.get("origin") != origin:
            raise ValueError("v3 frozen target origin drifted")
    selected, expected = target_by_id.get(blind_target_id), expected_targets.get(blind_target_id)
    if selected is None or expected is None:
        raise ValueError("v3 blind target is not scheduled")
    target_raw = _bound(target_root, selected.get("target"), label="frozen endpoint target")
    if expected["kind"] == "source_baseline":
        source_raw, _ = _read_frozen_source(frozen, expected["source_item_id"])
        if target_raw != source_raw.encode("utf-8"):
            raise ValueError("v3 baseline target bytes are not frozen source bytes")
    else:
        descendant = selected["origin"]["descendant"]
        descendant_raw = _bound(revision_root, descendant, label="revision descendant")
        if target_raw != descendant_raw:
            raise ValueError("v3 descendant target bytes drifted")
    return selected, target_raw, raw


def prepare_endpoint_cell(*, prepared_root: Path, target_root: Path, target_manifest_path: Path, endpoint_event_id: str) -> dict[str, Any]:
    """Freeze one endpoint payload; this is preparation only and never contacts a provider."""
    value = contract()
    event = next((row for row in endpoint_schedule(value) if row["endpoint_event_id"] == endpoint_event_id), None)
    if event is None or Path(prepared_root).exists():
        raise ValueError("v3 endpoint preparation requires one fresh scheduled root")
    target, target_raw, _manifest_raw = _replay_target_lineage(Path(target_root), Path(target_manifest_path), blind_target_id=event["blind_target_id"])
    payload = endpoint_payload(blind_target_id=event["blind_target_id"], target_text=target_raw.decode("utf-8"), target_sha256=_sha256(target_raw), measure_id=event["measure_id"])
    payload_path = Path(prepared_root) / "payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=False)
    payload_path.write_bytes(payload)
    prepared = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "prepared_endpoint_cell", "event_id": endpoint_event_id,
        "contract_sha256": CONTRACT_SHA256, "target_root": str(Path(target_root).resolve()), "target_manifest": _commitment(Path(target_manifest_path), root=Path(target_root)), "target": dict(target["target"]),
        "route": value["routes"]["judges"][event["judge_route_id"]], "payload": _commitment(payload_path, root=Path(prepared_root)),
        "provider_calls_made": 0, "process_launches": 0, "no_resend": True,
    }
    _write_once(Path(prepared_root) / "prepared-cell.json", prepared)
    return prepared


def begin_one_launch(*, prepared_root: Path) -> dict[str, Any]:
    raw = _read_regular(Path(prepared_root) / "prepared-cell.json", label="prepared endpoint cell")
    prepared = json.loads(raw.decode("utf-8"))
    if canonical(prepared) + b"\n" != raw or prepared.get("kind") != "prepared_endpoint_cell" or prepared.get("process_launches") != 0 or (Path(prepared_root) / "launch-intent.json").exists():
        raise ValueError("v3 endpoint cell cannot launch")
    intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "one_launch_intent", "prepared_record_sha256": _sha256(raw), "process_launches": 1, "no_resend": True}
    _write_once(Path(prepared_root) / "launch-intent.json", intent)
    return intent


def validate_endpoint_receipt(*, prepared_root: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Reopen artifacts and authenticate a settled native success before projection may consume it."""
    root = Path(prepared_root)
    prepared_raw = _read_regular(root / "prepared-cell.json", label="prepared endpoint cell")
    intent_raw = _read_regular(root / "launch-intent.json", label="launch intent")
    prepared = json.loads(prepared_raw.decode("utf-8"))
    intent = json.loads(intent_raw.decode("utf-8"))
    expected_keys = {"format_version", "study_id", "kind", "event_id", "contract_sha256", "target_root", "target_manifest", "target", "route", "payload", "provider_calls_made", "process_launches", "no_resend"}
    if canonical(prepared) + b"\n" != prepared_raw or canonical(intent) + b"\n" != intent_raw or set(prepared) != expected_keys or prepared.get("format_version") != 1 or prepared.get("study_id") != STUDY_ID or prepared.get("kind") != "prepared_endpoint_cell" or prepared.get("contract_sha256") != CONTRACT_SHA256 or prepared.get("provider_calls_made") != 0 or prepared.get("process_launches") != 0 or prepared.get("no_resend") is not True:
        raise ValueError("v3 prepared endpoint evidence drifted")
    if intent != {"format_version": 1, "study_id": STUDY_ID, "kind": "one_launch_intent", "prepared_record_sha256": _sha256(prepared_raw), "process_launches": 1, "no_resend": True}:
        raise ValueError("v3 endpoint launch intent is not authenticated")
    event = next((row for row in endpoint_schedule() if row["endpoint_event_id"] == prepared.get("event_id")), None)
    if event is None or prepared.get("route") != contract()["routes"]["judges"][event["judge_route_id"]]:
        raise ValueError("v3 prepared endpoint route drifted")
    target_root = Path(prepared.get("target_root", ""))
    manifest_raw = _bound(target_root, prepared.get("target_manifest"), label="frozen target manifest")
    target, target_raw, replayed_manifest_raw = _replay_target_lineage(target_root, target_root / prepared["target_manifest"]["path"], blind_target_id=event["blind_target_id"])
    if manifest_raw != replayed_manifest_raw or target.get("target") != prepared.get("target"):
        raise ValueError("v3 prepared endpoint target lineage drifted")
    payload_raw = _bound(root, prepared.get("payload"), label="prepared endpoint payload")
    if payload_raw != endpoint_payload(blind_target_id=event["blind_target_id"], target_text=target_raw.decode("utf-8"), target_sha256=_sha256(target_raw), measure_id=event["measure_id"]):
        raise ValueError("v3 prepared endpoint payload reconstruction drifted")
    native_raw = _read_regular(root / "native-receipt.json", label="native endpoint receipt")
    response_raw = _read_regular(root / "response.json", label="native endpoint response")
    native, response = json.loads(native_raw.decode("utf-8")), json.loads(response_raw.decode("utf-8"))
    if event is None or canonical(native) + b"\n" != native_raw or canonical(response) + b"\n" != response_raw:
        raise ValueError("v3 native endpoint artifacts are not canonical")
    route = contract()["routes"]["judges"][event["judge_route_id"]]
    required = {"status", "provider_request_id", "provider_session_id", "native_response_id", "provider_model", "reasoning", "tools_enabled", "transmitted_payload_sha256", "response_sha256"}
    if set(native) != required or native.get("status") != 200 or native.get("provider_model") != route["model"] or native.get("reasoning") != route["reasoning"] or native.get("tools_enabled") is not False or native.get("transmitted_payload_sha256") != _sha256(payload_raw) or native.get("response_sha256") != _sha256(response_raw):
        raise ValueError("v3 native endpoint receipt is not a settled bound success")
    if any(not isinstance(native.get(field), str) or not native[field] for field in ("provider_request_id", "provider_session_id", "native_response_id")):
        raise ValueError("v3 native endpoint identity is missing")
    score = response.get("overall") if isinstance(response, Mapping) else None
    limits = (1, 7) if event["measure_id"] == "holistic" else (1, 5)
    if set(response) != {"overall", "rationale"} or not isinstance(score, int) or isinstance(score, bool) or not limits[0] <= score <= limits[1] or not isinstance(response["rationale"], str) or not response["rationale"]:
        raise ValueError("v3 native endpoint response schema drifted")
    verified = {"format_version": 1, "study_id": STUDY_ID, "kind": "verified_endpoint_receipt", "prepared_root": str(root.resolve()), "endpoint_event_id": event["endpoint_event_id"], "prepared_record_sha256": _sha256(prepared_raw), "launch_intent_sha256": _sha256(intent_raw), "payload_sha256": _sha256(payload_raw), "native_receipt_sha256": _sha256(native_raw), "response_sha256": _sha256(response_raw), **native, "response": response}
    if output_path is not None:
        _write_once(Path(output_path), verified)
    return verified


def project_independent_metrics(*, endpoint_receipt_paths: list[Path]) -> dict[str, Any]:
    """Reopen all 48 receipt chains and recompute endpoint-separated paired outcomes."""
    schedule = {row["endpoint_event_id"]: row for row in endpoint_schedule()}
    if len(endpoint_receipt_paths) != len(schedule):
        raise ValueError("v3 endpoint evidence is incomplete")
    scores: dict[str, int] = {}
    payloads: dict[tuple[str, str], str] = {}
    request_ids: set[str] = set()
    session_ids: set[str] = set()
    native_ids: set[str] = set()
    for path in endpoint_receipt_paths:
        raw = _read_regular(Path(path), label="persisted verified endpoint receipt")
        try:
            receipt = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("v3 persisted endpoint receipt is invalid JSON") from error
        event = schedule.get(receipt.get("endpoint_event_id")) if isinstance(receipt, Mapping) else None
        if event is None or event["endpoint_event_id"] in scores:
            raise ValueError("v3 endpoint evidence is unscheduled or duplicated")
        if canonical(receipt) + b"\n" != raw or receipt.get("kind") != "verified_endpoint_receipt" or not isinstance(receipt.get("prepared_root"), str):
            raise ValueError("v3 endpoint projection requires persisted verified receipts")
        reopened = validate_endpoint_receipt(prepared_root=Path(receipt["prepared_root"]))
        if reopened != receipt:
            raise ValueError("v3 endpoint receipt failed independent artifact replay")
        if receipt["provider_request_id"] in request_ids or receipt["provider_session_id"] in session_ids or receipt["native_response_id"] in native_ids:
            raise ValueError("v3 endpoint native identity is duplicated")
        request_ids.add(receipt["provider_request_id"])
        session_ids.add(receipt["provider_session_id"])
        native_ids.add(receipt["native_response_id"])
        key = (event["blind_target_id"], event["measure_id"])
        previous = payloads.setdefault(key, receipt["payload_sha256"])
        if previous != receipt["payload_sha256"]:
            raise ValueError("v3 judge payload bytes differ for a target and measure")
        scores[event["endpoint_event_id"]] = receipt["response"]["overall"]
    target_by_event = {row["target_event_id"]: row["blind_target_id"] for row in targets() if row["target_event_id"]}
    baseline_by_item = {row["source_item_id"]: row["blind_target_id"] for row in targets() if row["kind"] == "source_baseline"}
    primary, arm_baseline = [], []
    for event in revision_schedule():
        control = event["event_id"].replace("-cwr_guided", "-generic_no_feedback")
        for judge in _JUDGES:
            for measure in _MEASURES:
                def endpoint(target: str, *, _measure: str = measure, _judge: str = judge) -> str:
                    return f"endpoint-v3-{target}-{_measure}-{_judge}"
                if event["guidance_arm"] == "cwr_guided":
                    primary.append({"source_item_id": event["source_item_id"], "cycle": 1, "generator_id": "grok-4.6", "judge_route_id": judge, "measure_id": measure, "guided_event_id": event["event_id"], "control_event_id": control, "guided_minus_control": scores[endpoint(target_by_event[event["event_id"]])] - scores[endpoint(target_by_event[control])]})
                arm_baseline.append({"source_item_id": event["source_item_id"], "cycle": 1, "guidance_arm": event["guidance_arm"], "judge_route_id": judge, "measure_id": measure, "event_id": event["event_id"], "baseline_target_id": baseline_by_item[event["source_item_id"]], "arm_minus_baseline": scores[endpoint(target_by_event[event["event_id"]])] - scores[endpoint(baseline_by_item[event["source_item_id"]])]})
    summaries = []
    for judge in _JUDGES:
        for measure in _MEASURES:
            deltas = [row["guided_minus_control"] for row in primary if row["judge_route_id"] == judge and row["measure_id"] == measure]
            summaries.append({"judge_route_id": judge, "measure_id": measure, "sample_count": len(deltas), "mean_guided_minus_control": sum(deltas) / len(deltas)})
    return {"study_id": STUDY_ID, "kind": "replayed_native_endpoint_projection", "endpoint_results_are_not_pooled": True, "primary_guided_minus_control": primary, "guided_minus_baseline": [row for row in arm_baseline if row["guidance_arm"] == "cwr_guided"], "generic_minus_baseline": [row for row in arm_baseline if row["guidance_arm"] == "generic_no_feedback"], "summaries": summaries}
