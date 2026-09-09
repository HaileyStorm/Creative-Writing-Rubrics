"""Provider-free checks of the post-773 native evidence boundary."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_continuation_native_v1.py"


@pytest.fixture
def case(tmp_path):
    spec = importlib.util.spec_from_file_location("_continuation_native_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "0774"
    (root / "payload").mkdir(parents=True)
    (root / "responses").mkdir()
    schema = json.dumps({"type": "object", "required": ["verdicts"], "properties": {"verdicts": {
        "type": "array", "items": {"type": "object", "required": ["question_id", "verdict"]}}}}).encode()
    prompt = b"synthetic frozen prompt"
    schema_path = root / "payload/request-0774.json"
    schema_path.write_bytes(schema)
    (root / "payload/request-0774.txt").write_bytes(prompt)
    request = {"ordinal": 774, "batch_number": 15, "question_ids": ["a", "b"],
               "prompt_sha256": module._sha(prompt), "prompt_bytes": len(prompt),
               "schema_sha256": module._sha(schema), "schema_bytes": len(schema)}
    response = json.dumps({"verdicts": [{"question_id": "a", "verdict": "YES"}, {"question_id": "b", "verdict": "NO"}]}).encode()
    message = root / "responses/batch-0015.attempt-0001.message.json"
    message.write_bytes(response)
    events = root / "responses/events.jsonl"
    rows = [{"type": "thread.started", "thread_id": "synthetic-thread"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": response.decode()}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0,
             "cache_write_input_tokens": 0, "output_tokens": 4, "reasoning_output_tokens": 0}}]
    events.write_bytes(b"\n".join(json.dumps(row).encode() for row in rows) + b"\n")
    stderr = root / "responses/stderr.bin"
    stderr.write_bytes(b"")
    route = {"codex_command": [str(tmp_path / "synthetic-codex.exe")]}
    native = module.adapter()._base()
    command = list(native._expected_codex_command(route["codex_command"][0], root))
    command[command.index("--output-schema") + 1] = str(schema_path)
    command[command.index("--output-last-message") + 1] = str(message)
    command[-1:-1] = ["--disable", "code_mode"]
    def descriptor(path):
        return {"path": path.relative_to(root).as_posix(), "bytes": len(path.read_bytes()), "sha256": module._sha(path.read_bytes())}
    record = {"command": command, "reported": native._strict_stderr_labels(b""),
              "provider_artifacts": {"codex_events": descriptor(events), "codex_stderr": descriptor(stderr)}}
    return SimpleNamespace(module=module, root=root, request=request, route=route, response=response,
                           record=record, message=message, events=events, schema=schema)


def test_accepts_exact_native_evidence(case):
    result = case.module.validate_native(case.root, case.request, case.route, case.response, case.record)
    assert result["thread_id"] == "synthetic-thread"
    assert [row["question_id"] for row in result["verdicts"]] == ["a", "b"]
    assert result["response_sha256"] == hashlib.sha256(case.response).hexdigest()


@pytest.mark.parametrize("change", ["prompt", "schema", "message", "events", "command", "ids"])
def test_rejects_changed_evidence(case, change):
    if change in {"prompt", "schema"}:
        suffix = "txt" if change == "prompt" else "json"
        (case.root / f"payload/request-0774.{suffix}").write_bytes(b"changed")
    elif change == "message":
        case.message.write_bytes(b"changed")
    elif change == "events":
        case.events.write_bytes(case.events.read_bytes() + b" ")
    elif change == "command":
        case.record["command"].append("changed")
    else:
        case.request["question_ids"] = ["b", "a"]
    with pytest.raises(ValueError):
        case.module.validate_native(case.root, case.request, case.route, case.response, case.record)


def test_route_uses_owner_assumption_but_keeps_subscription_identity(case, tmp_path):
    executable = Path(case.route["codex_command"][0])
    executable.write_bytes(b"synthetic CLI")
    route = {"name": "codex-chatgpt-gpt-5.6-sol", "provider": "openai_codex", "adapter": "codex_exec",
             "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "model": "gpt-5.6-sol",
             "reasoning_effort": "high", "timeout_seconds": 900, "armed": True, "health": "healthy", "zero_charge": True,
             "codex_command": [str(executable)], "codex_command_identity": {"artifacts": [{"sha256": case.module._sha(executable.read_bytes())}]},
             "cost_evidence": {"expires_at": "2000-01-01T00:00:00Z"}}
    (tmp_path / "routes.json").write_text(json.dumps({"routes": [route]}))
    identity = {key: route[key] for key in case.module.ROUTE_KEYS}
    assert case.module.route_snapshot(tmp_path, identity) == route
    route["account_class"] = "api"
    (tmp_path / "routes.json").write_text(json.dumps({"routes": [route]}))
    with pytest.raises(ValueError, match="Subscription"):
        case.module.route_snapshot(tmp_path, identity)
