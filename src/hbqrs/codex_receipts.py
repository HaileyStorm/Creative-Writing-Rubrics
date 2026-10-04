"""Own-thread native execution receipts; no provider contact or account-log scan."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

POLICY = "codex_native_rollout_v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 8 * 1024 * 1024
STARTUP_DIAGNOSTIC = (
    "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; "
    "enable `features.code_mode_host` and install `codex-code-mode-host`."
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def binding() -> dict[str, str]:
    return {"policy": POLICY, "reader_sha256": sha(Path(__file__).read_bytes())}


def _rows(raw: bytes) -> list[tuple[bytes, dict[str, Any]]]:
    if not raw or len(raw) > MAX_BYTES or not raw.endswith(b"\n"):
        raise ValueError("Native receipt is missing, truncated or exceeds its byte bound")
    result = []
    for line in raw.splitlines():
        if not line or len(line) > MAX_LINE_BYTES:
            raise ValueError("Native receipt line is empty or exceeds its byte bound")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("Native receipt record is not an object")
        result.append((line, value))
    return result


def _uuid(value: Any) -> str:
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Native receipt identity is invalid")
    return value


def event_identity(raw: bytes, final_raw: bytes) -> tuple[str, list[str]]:
    rows = [row for _, row in _rows(raw)]
    starts = [r for r in rows if r.get("type") == "thread.started"]
    if len(starts) != 1 or rows[0] != starts[0]:
        raise ValueError("Native events require one initial thread identity")
    thread_id = _uuid(starts[0].get("thread_id"))
    turn_started = False
    turn_completed = False
    messages, diagnostics = [], []
    for row in rows[1:]:
        kind = row.get("type")
        if turn_completed:
            raise ValueError("Native events continue after turn completion")
        if row.get("thread_id", thread_id) != thread_id:
            raise ValueError("Native events contain a foreign thread")
        if kind == "turn.started" and not turn_started:
            turn_started = True
        elif kind == "turn.completed" and turn_started:
            if not isinstance(row.get("usage"), dict):
                raise ValueError("Native completed turn lacks usage")
            turn_completed = True
        elif kind in {"item.started", "item.updated", "item.completed"}:
            item = row.get("item", {})
            if not isinstance(item, dict):
                raise ValueError("Native events item is not an object")
            if (kind == "item.completed" and not turn_started and not diagnostics
                    and item.get("type") == "error" and item.get("message") == STARTUP_DIAGNOSTIC):
                diagnostics.append("code_mode_host_disabled_startup_v1")
            elif not turn_started or item.get("type") not in {"agent_message", "reasoning"}:
                raise ValueError("Native events contain an error, tool or unsupported item")
            elif kind == "item.completed" and item.get("type") == "agent_message":
                messages.append(item.get("text"))
        else:
            raise ValueError("Native events contain an unsupported lifecycle record")
    if not turn_completed or messages != [final_raw.decode("utf-8")]:
        raise ValueError("Native events do not bind one completed final answer")
    return thread_id, diagnostics


def _text(payload: dict, content_type: str) -> str:
    content = payload.get("content")
    if (not isinstance(content, list) or not content or any(
            not isinstance(part, dict) or part.get("type") != content_type
            or not isinstance(part.get("text"), str) for part in content)):
        raise ValueError("Native message content is unsupported")
    return "".join(part["text"] for part in content)


def project(rollout_raw: bytes, events_raw: bytes, final_raw: bytes, *, prompt: str,
            model: str, reasoning: str, cwd: Path) -> dict[str, Any]:
    thread_id, diagnostics = event_identity(events_raw, final_raw)
    rows = _rows(rollout_raw)
    if any(not isinstance(record.get("payload"), dict) for _, record in rows):
        raise ValueError("Native rollout payload is not an object")
    metas = [(line, r["payload"]) for line, r in rows if r.get("type") == "session_meta"]
    if len(metas) != 1:
        raise ValueError("Native rollout requires exactly one session metadata record")
    meta = metas[0][1]
    if (meta.get("id") != thread_id or meta.get("source") != "exec"
            or meta.get("model_provider") != "openai" or meta.get("forked_from_id") is not None
            or not isinstance(meta.get("cwd"), str) or not meta["cwd"]
            or Path(meta.get("cwd", "")).resolve() != cwd.resolve()):
        raise ValueError("Native rollout session identity, provider or workspace differs")
    starts = [(line, r["payload"]) for line, r in rows
              if r.get("type") == "event_msg" and r.get("payload", {}).get("type") == "task_started"]
    completes = [(line, r["payload"]) for line, r in rows
                 if r.get("type") == "event_msg" and r.get("payload", {}).get("type") == "task_complete"]
    contexts = [(line, r["payload"]) for line, r in rows if r.get("type") == "turn_context"]
    if len(starts) != 1 or len(completes) != 1 or len(contexts) != 1:
        raise ValueError("Native rollout requires one own started, contextualized and completed turn")
    turn_id = _uuid(starts[0][1].get("turn_id"))
    context = contexts[0][1]
    if (context.get("turn_id") != turn_id or completes[0][1].get("turn_id") != turn_id
            or context.get("model") != model or context.get("effort") != reasoning
            or context.get("model_provider", "openai") != "openai"
            or not isinstance(context.get("cwd"), str) or not context["cwd"]
            or Path(context.get("cwd", "")).resolve() != cwd.resolve()):
        raise ValueError("Native turn identity, model, effort or workspace differs")
    prompts, finals = [], []
    allowed = {"session_meta", "turn_context", "event_msg", "response_item", "world_state", "token_usage_record"}
    for line, record in rows:
        kind, payload = record.get("type"), record.get("payload", {})
        if kind not in allowed or not isinstance(payload, dict):
            raise ValueError("Native rollout contains an unsupported record")
        metadata = payload.get("internal_chat_message_metadata_passthrough", {})
        if not isinstance(metadata, dict):
            raise ValueError("Native message metadata is unsupported")
        if payload.get("turn_id", turn_id) != turn_id or metadata.get("turn_id", turn_id) != turn_id:
            raise ValueError("Native rollout contains a foreign turn")
        if payload.get("thread_id", thread_id) != thread_id:
            raise ValueError("Native rollout contains a foreign thread")
        if kind == "event_msg":
            if payload.get("type") not in {"task_started", "task_complete", "token_count",
                                           "item_started", "item_updated", "item_completed"}:
                raise ValueError("Native rollout contains an error or unsupported event")
            if "item" in payload and (not isinstance(payload["item"], dict) or
                    payload["item"].get("type") not in {"UserMessage", "AgentMessage", "Reasoning", "AgentReasoning"}):
                raise ValueError("Native rollout contains tool activity")
        if kind == "response_item":
            if payload.get("type") == "reasoning":
                continue
            if payload.get("type") != "message" or metadata.get("turn_id") != turn_id:
                raise ValueError("Native rollout contains tool activity or unbound message")
            if payload.get("role") == "user":
                kinds = metadata.get("content_item_kinds")
                if kinds == ["user.text"]:
                    prompts.append((line, _text(payload, "input_text")))
                elif kinds != ["environments.environment_context"]:
                    raise ValueError("Native rollout contains an unexpected user message")
            elif payload.get("role") == "assistant":
                if payload.get("phase") != "final_answer":
                    raise ValueError("Native rollout assistant message is not a final answer")
                finals.append((line, _text(payload, "output_text")))
            elif payload.get("role") not in {"developer", "system"}:
                raise ValueError("Native rollout message role is unsupported")
    final = final_raw.decode("utf-8")
    if (len(prompts) != 1 or prompts[0][1] != prompt or len(finals) != 1
            or finals[0][1] != final or completes[0][1].get("last_agent_message") != final):
        raise ValueError("Native rollout prompt or final answer differs")
    selected = [metas[0][0], starts[0][0], contexts[0][0], prompts[0][0], finals[0][0], completes[0][0]]
    positions = [[line for line, _ in rows].index(line) for line in selected]
    if positions[0] != 0 or positions != sorted(set(positions)):
        raise ValueError("Native rollout lifecycle order differs")
    return {"schema_version": 1, "policy": POLICY, "evidence_class": "native_own_turn_execution_settings",
            "thread_id": thread_id, "turn_id": turn_id,
            "reported": {"model": model, "provider": "openai", "reasoning_effort": reasoning,
                         "session_id": thread_id},
            "cwd": str(cwd.resolve()), "prompt_sha256": sha(prompt.encode("utf-8")),
            "rollout_sha256": sha(rollout_raw), "events_sha256": sha(events_raw),
            "final_sha256": sha(final_raw), "turn_context_sha256": sha(contexts[0][0]),
            "selected_line_sha256": [sha(line) for line in selected], "startup_diagnostics": diagnostics,
            "one_turn_observed": True, "zero_tool_activity_observed": True,
            "provider_backend_model_attested": False, "physical_contact_cardinality_proven": False}


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Native receipt exceeds its byte bound")
    return raw


def locate(codex_home: Path, thread_id: str, *, started_at: datetime) -> Path:
    _uuid(thread_id)
    root = (codex_home / "sessions").resolve()
    days = {started_at.date(), started_at.astimezone().date(), datetime.now(timezone.utc).date()}
    days |= {day + timedelta(days=offset) for day in list(days) for offset in (-1, 1)}
    if len(days) > 8:
        raise ValueError("Native receipt date range is no longer bounded to this attempt")
    matches = []
    for day in sorted(days):
        folder = root / day.strftime("%Y/%m/%d")
        matches.extend(folder.glob(f"rollout-*-{thread_id}.jsonl"))
    if len(matches) != 1 or not matches[0].resolve().is_relative_to(root):
        raise ValueError("Exact own-thread native rollout is missing or ambiguous")
    return matches[0]


def capture(output_dir: Path, stem: str, *, events_path: Path, message_path: Path,
            prompt: str, model: str, reasoning: str, codex_home: Path,
            started_at: datetime, rollout_path: Path | None = None) -> tuple[dict, dict]:
    events_raw, final_raw = read_bounded(events_path), read_bounded(message_path)
    thread_id, _ = event_identity(events_raw, final_raw)
    original = rollout_path if rollout_path is not None else locate(codex_home, thread_id, started_at=started_at)
    raw = read_bounded(original)
    # Retain even a rejected own receipt for local reconciliation, never overwrite it.
    raw_path = output_dir / "responses" / f"{stem}.rollout.jsonl"
    with raw_path.open("xb") as handle:
        handle.write(raw)
    receipt = project(raw, events_raw, final_raw, prompt=prompt, model=model, reasoning=reasoning, cwd=output_dir)
    receipt["reader_sha256"] = binding()["reader_sha256"]
    receipt_path = output_dir / "responses" / f"{stem}.receipt.json"
    with receipt_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, sort_keys=True, indent=2)
        handle.write("\n")
    artifacts = {}
    for name, path in (("codex_events", events_path), ("codex_message", message_path),
                       ("codex_rollout", raw_path), ("codex_receipt", receipt_path)):
        artifact_raw = read_bounded(path)
        artifacts[name] = {"path": path.relative_to(output_dir).as_posix(), "bytes": len(artifact_raw), "sha256": sha(artifact_raw)}
    return receipt, artifacts


def verify(output_dir: Path, provider: dict, *, prompt: str, model: str, reasoning: str,
           final_raw: bytes | None = None) -> None:
    if provider.get("receipt_policy") != POLICY:
        raise ValueError("Native receipt policy is missing")
    artifacts = provider.get("provider_artifacts", {})
    if set(artifacts) != {"codex_events", "codex_message", "codex_rollout", "codex_receipt"}:
        raise ValueError("Native receipt artifact inventory differs")
    raw = {}
    for name, item in artifacts.items():
        path = (output_dir / item["path"]).resolve()
        if not path.is_relative_to(output_dir.resolve()):
            raise ValueError("Native receipt path escapes the run")
        raw[name] = read_bounded(path)
        if len(raw[name]) != item["bytes"] or sha(raw[name]) != item["sha256"]:
            raise ValueError("Native receipt artifact is not bound")
    expected = project(raw["codex_rollout"], raw["codex_events"], raw["codex_message"],
                       prompt=prompt, model=model, reasoning=reasoning, cwd=output_dir)
    if final_raw is not None and final_raw != raw["codex_message"]:
        raise ValueError("Native final message differs from the accepted response")
    expected["reader_sha256"] = binding()["reader_sha256"]
    if json.loads(raw["codex_receipt"]) != expected or provider.get("reported") != expected["reported"]:
        raise ValueError("Native execution receipt is not replayable")
