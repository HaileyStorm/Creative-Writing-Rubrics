"""Direct, one-attempt continuation of the frozen Sol schedule after ordinal 773."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
HELPER_PATH = ROOT / "sol_continuation_native_v1.py"
EXPECTED_CAMPAIGN_ROOT = Path("C:/Users/Haile/Documents/cwr-dryad-sol-post773-continuation-20260909-r1")
CAMPAIGN_ROOT = EXPECTED_CAMPAIGN_ROOT
START_ORDINAL = 774
MAX_ORDINAL = 5428
MODEL = "gpt-5.6-sol"
REASONING = "high"
TIMEOUT = 300
def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} differs")
    return value


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _helper() -> Any:
    raw = HELPER_PATH.read_bytes()
    spec = importlib.util.spec_from_file_location("_sol_continuation_native", HELPER_PATH)
    _require(spec is not None and spec.loader is not None, "Sol continuation helper cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(HELPER_PATH.read_bytes() == raw, "Sol continuation helper changed during load")
    return module, _sha(raw)


def _prefix(helper: Any, plan_root: Path, original_root: Path, replacement_root: Path) -> dict[str, Any]:
    value = helper.predecessor(plan_root, original_root, replacement_root)
    _require(isinstance(value, Mapping) and value.get("through_ordinal") == 773 and value.get("verdict_count") == 5986
             and isinstance(value.get("plan_sha256"), str) and len(value["plan_sha256"]) == 64
             and isinstance(value.get("thread_ids"), list) and len(value["thread_ids"]) == len(set(value["thread_ids"]))
             and isinstance(value.get("commitments"), Mapping) and isinstance(value.get("route_identity"), Mapping),
             "Sol continuation predecessor differs")
    return dict(value)


def _route(helper: Any, queue_root: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    value = helper.route_snapshot(queue_root, dict(identity))
    _require(isinstance(value, dict) and {key: value.get(key) for key in identity} == dict(identity),
             "Sol continuation route differs")
    return value


def _manifest(helper_sha: str, predecessor: Mapping[str, Any], plan_root: Path, original_root: Path,
              replacement_root: Path) -> dict[str, Any]:
    return {"schema_version": 1, "evidence_class": "sol_continuation_execution_v1", "start_ordinal": START_ORDINAL,
            "helper_sha256": helper_sha, "driver_sha256": _sha(Path(__file__).read_bytes()),
            "plan_root": str(plan_root.resolve()), "original_root": str(original_root.resolve()),
            "replacement_root": str(replacement_root.resolve()), "predecessor": dict(predecessor),
            "route_identity": dict(predecessor["route_identity"]), "full_study_admitted": False}


def _campaign_manifest(root: Path, expected: Mapping[str, Any]) -> bytes:
    path = root / "campaign-manifest.json"
    raw = _canonical(expected)
    if path.exists():
        _require(path.read_bytes() == raw, "Sol continuation campaign manifest differs")
    else:
        _write_new(path, raw)
    return raw


def _request(helper: Any, plan_root: Path, ordinal: int) -> tuple[dict[str, Any], bytes, bytes]:
    request, prompt, schema = helper.request_payload(plan_root, ordinal)
    _require(isinstance(request, dict) and request.get("ordinal") == ordinal and isinstance(prompt, bytes) and isinstance(schema, bytes),
             "Sol continuation request differs")
    _require(_sha(prompt) == request.get("prompt_sha256") and len(prompt) == request.get("prompt_bytes")
             and _sha(schema) == request.get("schema_sha256") and len(schema) == request.get("schema_bytes"),
             "Sol continuation frozen payload differs")
    return request, prompt, schema


def _accepted(helper: Any, root: Path, request: Mapping[str, Any], manifest_sha: str, identity: Mapping[str, Any], threads: set[str]) -> dict[str, Any]:
    start_raw = (root / "start.json").read_bytes(); start = _json(start_raw, "Sol continuation start")
    expected_start = {"schema_version": 1, "state": "started", "ordinal": request["ordinal"], "manifest_sha256": manifest_sha,
                      "payload": {"prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"]}, "attempt": 1}
    _require(start == expected_start, "Sol continuation start differs")
    route_raw = (root / "route.json").read_bytes(); route = _json(route_raw, "Sol continuation route")
    _require(_canonical(route) == route_raw and {key: route.get(key) for key in identity} == dict(identity),
             "Sol continuation recorded route differs")
    authorization = _json((root / "authorization.json").read_bytes(), "Sol continuation authorization")
    _require(authorization == {"start_sha256": _sha(start_raw), "ordinal": request["ordinal"],
                               "route_sha256": _sha(route_raw), "authorized_at": authorization.get("authorized_at"),
                               "allowance_policy": "owner_assumed_allowance_no_fresh_evidence"},
             "Sol continuation authorization differs")
    stamp = authorization["authorized_at"]
    try:
        parsed = datetime.fromisoformat(stamp[:-1] + "+00:00" if isinstance(stamp, str) and stamp.endswith("Z") else stamp)
    except (TypeError, ValueError) as error:
        raise ValueError("Sol continuation authorization time differs") from error
    _require(parsed.tzinfo is not None, "Sol continuation authorization time differs")
    terminal_path = root / "terminal.json"
    _require(terminal_path.is_file(), "Sol continuation started or incomplete slot cannot resume")
    terminal = _json(terminal_path.read_bytes(), "Sol continuation terminal")
    _require(terminal.get("state") == "accepted" and terminal.get("ordinal") == request["ordinal"]
             and terminal.get("start_sha256") == _sha(start_raw), "Sol continuation terminal differs")
    response = (root / "response.json").read_bytes(); record = _json((root / "provider-record.json").read_bytes(), "Sol continuation record")
    native = helper.validate_native(root, request, route, response, record)
    _require(isinstance(native, Mapping) and native.get("response_sha256") == _sha(response)
             and isinstance(native.get("thread_id"), str) and native["thread_id"] and native["thread_id"] not in threads
             and isinstance(native.get("verdicts"), list), "Sol continuation accepted slot differs")
    _require(terminal.get("response_sha256") == native["response_sha256"] and terminal.get("thread_id") == native["thread_id"],
             "Sol continuation terminal evidence differs")
    threads.add(native["thread_id"])
    return dict(native)


def collect(plan_root: Path, original_root: Path, replacement_root: Path, queue_root: Path, *, through_ordinal: int,
            adapter_override: Any | None = None) -> dict[str, Any]:
    """Continue 774..through_ordinal exactly once per ordinal; never dispatch the prefix again."""
    _require(type(through_ordinal) is int and START_ORDINAL <= through_ordinal <= MAX_ORDINAL,
             "Sol continuation ordinal boundary differs")
    helper, helper_sha = _helper()
    plan_root, original_root, replacement_root = Path(plan_root).resolve(), Path(original_root).resolve(), Path(replacement_root).resolve()
    _require(CAMPAIGN_ROOT.resolve() == EXPECTED_CAMPAIGN_ROOT.resolve(),
             "Sol continuation root differs")
    predecessor = _prefix(helper, plan_root, original_root, replacement_root)
    route = _route(helper, Path(queue_root), predecessor["route_identity"])
    adapter = adapter_override or helper.adapter()
    root = CAMPAIGN_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".collect.lock"
    _require(not lock.exists(), "Sol continuation existing campaign lock cannot be reclaimed")
    manifest_raw = _campaign_manifest(root, _manifest(helper_sha, predecessor, plan_root, original_root, replacement_root))
    token = uuid.uuid4().hex.encode("ascii")
    _write_new(lock, token)
    try:
        threads = set(predecessor["thread_ids"])
        completed: list[int] = []
        requests_root = root / "requests"
        existing = sorted(int(path.name) for path in requests_root.iterdir() if path.is_dir() and path.name.isdigit()) if requests_root.exists() else []
        _require(all(START_ORDINAL <= ordinal <= MAX_ORDINAL for ordinal in existing)
                 and existing == list(range(START_ORDINAL, (existing[-1] if existing else START_ORDINAL - 1) + 1)),
                 "Sol continuation existing ordinal gap differs")
        for ordinal in range(START_ORDINAL, through_ordinal + 1):
            request, prompt, schema = _request(helper, plan_root, ordinal)
            slot = root / "requests" / f"{ordinal:04d}"
            if slot.exists():
                if (slot / "terminal.json").is_file():
                    _accepted(helper, slot, request, _sha(manifest_raw), predecessor["route_identity"], threads); completed.append(ordinal); continue
                raise ValueError("Sol continuation existing attempt is ambiguous")
            _write_new(slot / "payload" / f"request-{ordinal:04d}.txt", prompt)
            _write_new(slot / "payload" / f"request-{ordinal:04d}.json", schema)
            start = {"schema_version": 1, "state": "started", "ordinal": ordinal, "manifest_sha256": _sha(manifest_raw),
                     "payload": {"prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}, "attempt": 1}
            start_raw = _canonical(start); _write_new(slot / "start.json", start_raw)
            selected = route
            def gate() -> None:
                _require(_sha(HELPER_PATH.read_bytes()) == helper_sha
                         and _campaign_manifest(root, _manifest(helper_sha, predecessor, plan_root, original_root, replacement_root)) == manifest_raw
                         and _route(helper, Path(queue_root), predecessor["route_identity"]) == selected
                         and (slot / "start.json").read_bytes() == start_raw
                         and (slot / "payload" / f"request-{ordinal:04d}.txt").read_bytes() == prompt
                         and (slot / "payload" / f"request-{ordinal:04d}.json").read_bytes() == schema,
                         "Sol continuation pre-contact binding differs")
                route_raw = _canonical(selected)
                _write_new(slot / "route.json", route_raw)
                _write_new(slot / "authorization.json", _canonical({"start_sha256": _sha(start_raw), "ordinal": ordinal,
                           "route_sha256": _sha(route_raw), "authorized_at": datetime.now(timezone.utc).isoformat(),
                           "allowance_policy": "owner_assumed_allowance_no_fresh_evidence"}))
            try:
                content, record = adapter.call_codex(executable=selected["codex_command"][0], model=MODEL, reasoning=REASONING,
                    prompt=prompt.decode("utf-8"), output_dir=slot, response_schema=slot / "payload" / f"request-{ordinal:04d}.json",
                    batch_number=request["batch_number"], timeout=TIMEOUT, attempt_number=1, before_provider_attempt=gate)
                response = content.encode("utf-8"); _write_new(slot / "response.json", response); _write_new(slot / "provider-record.json", _canonical(record))
                native = helper.validate_native(slot, request, selected, response, record)
                _require(isinstance(native, Mapping) and native.get("response_sha256") == _sha(response)
                         and isinstance(native.get("thread_id"), str) and native["thread_id"] not in threads, "Sol continuation native result differs")
                terminal = {"schema_version": 1, "state": "accepted", "ordinal": ordinal, "start_sha256": _sha(start_raw),
                            "response_sha256": native["response_sha256"], "thread_id": native["thread_id"]}
                _write_new(slot / "terminal.json", _canonical(terminal)); threads.add(native["thread_id"]); completed.append(ordinal)
            except Exception as error:
                _write_new(slot / "terminal.json", _canonical({"schema_version": 1, "state": "stopped_no_retry", "ordinal": ordinal,
                           "start_sha256": _sha(start_raw), "error_type": type(error).__name__}))
                return {"state": "stopped_no_retry", "through_ordinal": ordinal, "completed_ordinals": completed,
                        "full_study_admitted": False, "automatic_dispatch": False}
        return {"state": "collected", "through_ordinal": through_ordinal, "completed_ordinals": completed,
                "full_study_admitted": False, "automatic_dispatch": False}
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
