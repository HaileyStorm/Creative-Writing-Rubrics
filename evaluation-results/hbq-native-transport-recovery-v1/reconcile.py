"""Saved native transport recovery; originals and contact history remain evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
from hbqrs import codex_receipts

POLICY = "saved_transport_recovery_v1"
DENOMINATORS = {"mfa": 868, "p1": 1584, "ttcw-sol": 3108}
DNS = "No such host is known. (os error 11001)"
SOL_WS = "stream disconnected before completion: " + DNS
SOL_FALLBACK = "Falling back from WebSockets to HTTPS transport. " + SOL_WS
GROK_DECODE = "reqwest error stream: Transport error: error decoding response body"
GROK_DNS = "request error: error sending request for url (https://cli-chat-proxy.grok.com/v1/responses): client error (Connect): dns error: " + DNS


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def timestamp(value):
    result = datetime.fromtimestamp(value, timezone.utc) if isinstance(value, (int, float)) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Native timestamp lacks timezone")
    return result


class ReadSet:
    def __init__(self, snapshot=None, commitments=None):
        self.snapshot, self.expected = snapshot, commitments or {}
        self.raws, self.paths = {}, {}

    def raw(self, name, path):
        if self.snapshot is not None and name in self.expected:
            raw = (self.snapshot / self.expected[name]["snapshot"]).read_bytes()
            require(digest(raw) == self.expected[name]["sha256"] and len(raw) == self.expected[name]["bytes"], "Private native snapshot differs")
        else:
            raw = codex_receipts.read_bounded(path)
        require(name not in self.raws or raw == self.raws[name], "Native source changed during reconciliation")
        self.raws[name], self.paths[name] = raw, str(path)
        return raw

    def commitments(self):
        return {name: {"sha256": digest(raw), "bytes": len(raw), "source_locator_local_only": self.paths[name],
                       "snapshot": "native/" + name + ".bin"} for name, raw in self.raws.items()}


def sol_projection(events_raw):
    rows = codex_receipts._rows(events_raw)
    require(rows[0][1].get("type") == "thread.started", "Missing own native thread")
    thread = codex_receipts._uuid(rows[0][1].get("thread_id"))
    kept, diagnostics = [], []
    started = finished = False
    for line, row in rows:
        kind, item = row.get("type"), row.get("item", {})
        require(row.get("thread_id", thread) == thread, "Transport diagnostic has foreign thread")
        diagnostic = kind == "error" or (kind == "item.completed" and item.get("type") == "error" and item.get("message") != codex_receipts.STARTUP_DIAGNOSTIC)
        if diagnostic:
            require(started and not finished, "Transport diagnostic outside own turn")
            if kind == "error":
                require(set(row) == {"type", "message"}, "Unsupported transport error fields")
                message = row["message"]
                match = re.fullmatch(r"Reconnecting\.\.\. ([1-5])/5 \((.*)\)", message)
                require(match is not None and match[2] in {SOL_WS, "Connection failed: error sending request"}, "Unknown native transport error")
            else:
                require(set(row) == {"type", "item"} and set(item) == {"id", "type", "message"}
                        and item["message"] == SOL_FALLBACK, "Unknown native transport diagnostic")
                message = item["message"]
            diagnostics.append({"line_sha256": digest(line), "type": kind, "message": message})
            continue
        kept.append(line)
        started = started or kind == "turn.started"
        finished = finished or kind == "turn.completed"
    require(diagnostics and any(DNS in d["message"] for d in diagnostics), "No demonstrated DNS transport recovery")
    return b"\n".join(kept) + b"\n", diagnostics


def recover_sol(reads, sample, prompt, home, started, rollout_path=None):
    stem = sample / "responses/batch-0001.attempt-0001"
    events = reads.raw("events", Path(str(stem) + ".events.jsonl"))
    final = reads.raw("final", Path(str(stem) + ".message.json"))
    filtered, diagnostics = sol_projection(events)
    thread, _ = codex_receipts.event_identity(filtered, final)
    if rollout_path is None:
        if reads.snapshot is not None:
            rollout_path = Path(reads.expected["rollout"]["source_locator_local_only"])
        else:
            rollout_path = codex_receipts.locate(home, thread, started_at=timestamp(started["time"]))
    rollout = reads.raw("rollout", rollout_path)
    records = [row for _, row in codex_receipts._rows(rollout)]
    completed = [row for row in records if row.get("type") == "event_msg" and row["payload"].get("type") == "task_complete"]
    require(len(completed) == 1 and timestamp(started["time"]) - timedelta(seconds=120) <= timestamp(records[0]["timestamp"])
            <= timestamp(completed[0]["timestamp"]) <= datetime(2026, 10, 16, 5, 40, tzinfo=timezone.utc), "Own rollout start/completion time differs")
    receipt = codex_receipts.project(rollout, filtered, final, prompt=prompt, model="gpt-6.1-sol", reasoning="high", cwd=sample)
    reads.raws["events_projection"], reads.paths["events_projection"] = filtered, "derived:validated_dns_transport_projection"
    return json.loads(final), {"policy": POLICY, "native_reader_receipt": receipt,
        "diagnostics": diagnostics, "raw_events_sha256": digest(events), "filtered_events_sha256": digest(filtered),
        "original_receipt_policy_satisfied": False, "physical_contact_cardinality_proven": False}


def grok_projection(updates, summary, session, prompt):
    kept, diagnostics, previous, event_ids = [], [], None, set()
    created, ended = timestamp(summary["created_at"]), timestamp(summary["updated_at"])
    require(summary.get("reasoning_effort") == "high", "Saved Grok effort differs")
    for row in updates:
        require(set(row) == {"timestamp", "method", "params"}, "Unknown native update fields")
        params, at = row["params"], timestamp(row["timestamp"])
        require(set(params) == {"sessionId", "update", "_meta"} and params["sessionId"] == session
                and created - timedelta(seconds=120) <= at <= ended + timedelta(seconds=120)
                and (previous is None or previous <= at), "Native update identity/time differs")
        previous = at
        update, meta = params["update"], params["_meta"]
        require(isinstance(update, dict) and isinstance(meta, dict), "Native update metadata differs")
        event_id = meta.get("eventId")
        require(isinstance(event_id, str) and event_id and event_id not in event_ids
                and type(meta.get("agentTimestampMs")) is int and meta["agentTimestampMs"] >= 0, "Native event identity differs")
        event_ids.add(event_id)
        kind = update.get("sessionUpdate")
        if kind == "retry_state":
            require(row["method"] == "_x.ai/session/update" and set(update) == {"sessionUpdate", "type", "attempt", "max_retries", "reason", "error_type"}
                    and update["type"] == "retrying" and update["error_type"] == "http" and update["max_retries"] == 15
                    and update["attempt"] == len(diagnostics) + 1 and update["reason"] in {GROK_DECODE, GROK_DNS}
                    and set(meta) == {"eventId", "agentTimestampMs"}
                    and isinstance(meta["eventId"], str) and isinstance(meta["agentTimestampMs"], int), "Unknown Grok retry state")
            require(kept and kept[-1]["params"]["update"]["sessionUpdate"] == "user_message_chunk", "Retry state outside prospective native response")
            diagnostics.append({"record_sha256": digest(canonical(row)), "reason": update["reason"], "attempt": update["attempt"]})
            continue
        require(kind in {"user_message_chunk", "agent_thought_chunk", "agent_message_chunk", "turn_completed"}
                and row["method"] == ("_x.ai/session/update" if kind == "turn_completed" else "session/update"), "Unknown/tool native update")
        expected_meta = {"eventId", "agentTimestampMs"} if kind in {"user_message_chunk", "turn_completed"} else {
            "totalTokens", "eventId", "agentTimestampMs", "promptId", "streamStartMs", "turnStartMs", "updateType", "chunkId"}
        require(set(meta) == expected_meta, "Unknown/tool native metadata")
        if kind != "turn_completed":
            content = update.get("content")
            require(isinstance(content, dict) and set(content) == {"type", "text"} and content["type"] == "text"
                    and isinstance(content["text"], str), "Native content is not exact text")
            if kind == "user_message_chunk":
                require(set(update) == {"sessionUpdate", "content", "_meta"} and update["_meta"] == {"modelId": "grok-4.7", "promptIndex": 0}, "Native user model/ordinal differs")
                require(content["text"] == prompt or prompt.endswith("\n") and content["text"] == prompt[:-1], "Native user update differs from exact prompt")
            else:
                require(set(update) == {"sessionUpdate", "content"} and meta.get("promptId") == summary["request_id"]
                    and meta["updateType"] == ("AgentThoughtChunk" if kind == "agent_thought_chunk" else "AgentMessageChunk")
                    and all(type(meta[k]) is int and meta[k] >= 0 for k in ("totalTokens", "streamStartMs", "turnStartMs", "chunkId")), "Native agent prompt identity differs")
        else:
            require(set(update) == {"sessionUpdate", "elapsed_ms", "prompt_id", "stop_reason", "usage"}
                    and update["stop_reason"] == "end_turn" and update["prompt_id"] == summary["request_id"]
                    and type(update["elapsed_ms"]) is int and update["elapsed_ms"] >= 0 and isinstance(update["usage"], dict), "Native completed update differs")
        kept.append(row)
    require(diagnostics and any(d["reason"] == GROK_DNS for d in diagnostics), "No demonstrated Grok DNS recovery")
    require([r["params"]["update"]["sessionUpdate"] for r in kept] == ["user_message_chunk", "agent_thought_chunk", "agent_message_chunk", "turn_completed"], "Native response lifecycle differs")
    return kept, diagnostics


def recover_grok(reads, sample, prompt, session_root, started, job):
    history = load("transport_ttcw_history_reader", REPO / "evaluation-results/hbq-matched-ttcw-20261004/reconcile_history.py")
    session = json.loads((sample / "native-identity.json").read_bytes())["session_id"]
    require(session_root.name == session, "Selected saved session differs")
    summary = json.loads(reads.raw("summary", session_root / "summary.json"))
    raw = reads.raw("updates", session_root / "updates.jsonl")
    projected, diagnostics = grok_projection([json.loads(v) for v in raw.splitlines()], summary, session, prompt)
    class Adapter:
        def raw(self, name, path):
            return reads.raw(name, path)
        def json(self, name, path):
            return json.loads(self.raw(name, path))
        def lines(self, name, path):
            values = [json.loads(v) for v in self.raw(name, path).splitlines()]
            return projected if name == "updates" else values
    normalized_job = {"model": "grok-4.7", "route": job["route"], "cutoff": job.get("campaign_deadline", job.get("cutoff"))}
    response, native = history.history_response(Adapter(), session_root, {"session_id": session}, dict(started, session_id=session), normalized_job, prompt.encode())
    projection = b"".join(canonical(v) for v in projected)
    reads.raws["updates_projection"], reads.paths["updates_projection"] = projection, "derived:validated_dns_retry_state_projection"
    return json.loads(response), {"policy": POLICY, "saved_history": native, "history_reader_sha256": digest(Path(history.__file__).read_bytes()),
        "diagnostics": diagnostics, "raw_updates_sha256": digest(raw), "filtered_updates_sha256": digest(projection),
        "source_session_root_local_only": str(session_root),
        "original_native_envelope_reconstructed": False, "physical_contact_cardinality_proven": False}


def study_context(config):
    tools, study = Path(config["tools_root_local_only"]), config["study"]
    manifest_path = Path(config["manifest_path_local_only"])
    if study == "mfa":
        sys.path.insert(0, str(REPO / "evaluation-results/hbq-matched-mfa-v1"))
        import context_reconciliation as context
        import collector_context_v2 as continuation
        module = context.old
        manifest, root, subset, validator = module.load_manifest(manifest_path, config["manifest_sha256"], tools)
        pin = config["context_reconciliation"]
        previous = context.verify_descendant(Path(pin["path_local_only"]), pin["sha256"], manifest, config["manifest_sha256"], root, codex_receipts, subset, validator)
        runner = context.frozen_runner(root, manifest)
        wrapped = context.admission(root, manifest, validator, runner)
        return {"module": module, "manifest": manifest, "root": root, "subset": subset, "validator": wrapped,
                "prior": previous, "context": context, "continuation": continuation, "tools": tools, "runner": runner}
    if study == "p1":
        module = load("transport_p1_collector", REPO / "evaluation-results/hbq-semantic-crossform-p1b-matched-v1/collector.py")
        manifest, root, subset, validator = module.load_manifest(manifest_path, config["manifest_sha256"], tools)
        return {"module": module, "manifest": manifest, "root": root, "subset": subset, "validator": validator, "tools": tools}
    raise ValueError("Study needs an explicitly implemented source adapter")


def bound_source(context, config, source):
    module, root, manifest, tools = (context[k] for k in ("module", "root", "manifest", "tools"))
    output, endpoint = Path(source["root_local_only"]), source["endpoint"]
    raw = (output / "job.json").read_bytes()
    require(digest(raw) == source["job_sha256"], "Exact stopped source job differs")
    if config["study"] == "mfa":
        return context["continuation"].verify_job_binding(output, manifest, config["manifest_sha256"], context["prior"], config["context_reconciliation"]["sha256"], endpoint, tools)
    return module.verify_job_binding(output, manifest, root, config["manifest_sha256"], endpoint, tools)


def validate_started(module, sample, row, binding, manifest_sha, root, manifest):
    require(json.loads((sample / "condition.json").read_bytes()) == row, "Reserved condition differs")
    started = json.loads((sample / "attempt-started.json").read_bytes())
    require(started["manifest_sha256"] == manifest_sha and started["logical_sample_id"] == row["logical_sample_id"]
            and started["attempt"] == 1 and started["no_resend"] is True
            and started["job_sha256"] == digest((sample.parent / "job.json").read_bytes())
            and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"], "Reserved attempt start differs")
    identity = json.loads((sample / "native-identity.json").read_bytes())
    require(identity["logical_sample_id"] == row["logical_sample_id"] and started.get("session_id") == identity.get("session_id"), "Reserved native identity differs")
    prompt, schema, texts, context = module.inputs(root, manifest, row)
    require((sample / "prompt.txt").read_bytes() == prompt and (sample / "schema.json").read_bytes() == schema, "Reserved exact prompt/schema differs")
    if row["endpoint"] == "sol":
        account = (sample.parent / "account-binding.json").read_bytes()
        require(digest(account) == started["account_binding_sha256"] and json.loads(account) == module.account_receipt(binding), "Reserved secondary account differs")
    return started, prompt, schema, texts, context


def recover_slot(context, config, source, row, binding, saved=None, snapshot=None):
    module, manifest, root = (context[k] for k in ("module", "manifest", "root"))
    sample = module.sample_path(Path(source["root_local_only"]), row)
    terminal, answer = module.replay(sample, row, manifest, binding, root, codex_receipts, context["subset"], context["validator"])
    started, prompt, schema, texts, task_context = validate_started(module, sample, row, binding, config["manifest_sha256"], root, manifest)
    state, native, acceptance = terminal["state"], None, None
    reads = ReadSet(snapshot, saved.get("native_sources") if saved else None)
    recovered = False
    if state not in module.SETTLED:
        require(state in {"unadmitted_no_resend", "ambiguous", "definitely_not_contacted", "unavailable"}, "Unknown reserved terminal")
        try:
            if row["endpoint"] == "sol":
                home = Path(config["secondary_home_local_only"]).resolve()
                expected = binding["runtime"]["secondary_home_sha256"]
                require(home.name == "cwr-sol-secondary" and digest(str(home).encode()) == expected, "Designated own rollout home differs")
                answer, native = recover_sol(reads, sample, prompt.decode(), home, started)
            else:
                failure = json.loads((sample / "native-result.json").read_bytes())
                require(failure["state"] == "ambiguous" and failure["result"] is None
                        and failure["failure"]["code"] == "validation_tool_policy_attestation", "Grok failure is outside demonstrated recovery")
                session = json.loads((sample / "native-identity.json").read_bytes())["session_id"]
                if saved and "source_session_root_local_only" in (saved.get("native_proof") or {}):
                    selected = Path(saved["native_proof"]["source_session_root_local_only"])
                elif saved and "summary" in saved.get("native_sources", {}):
                    selected = Path(saved["native_sources"]["summary"]["source_locator_local_only"]).parent
                else:
                    matches = list(Path(config["grok_sessions_root_local_only"]).glob("*/" + codex_receipts._uuid(session)))
                    require(len(matches) == 1, "Exact own saved Grok session missing or ambiguous")
                    selected = matches[0]
                answer, native = recover_grok(reads, sample, prompt.decode(), selected, started, binding)
            acceptance = context["validator"].semantic_validate(row["arm"], answer, row, texts, context["subset"], context=task_context, schema=json.loads(schema))
            state = "accepted" if acceptance["accepted"] else "semantic_rejected"
            recovered = True
        except (OSError, ValueError, KeyError, TypeError) as error:
            answer = None
            native = {"recovery_unadmitted": True, "reason": str(error), "error_class": type(error).__name__}
    entry = {"endpoint": row["endpoint"], "endpoint_ordinal": row["endpoint_ordinal"], "logical_sample_id": row["logical_sample_id"],
        "request_sha256": row["request_sha256"], "source_root_local_only": str(sample.parent.resolve()),
        "source_job_sha256": source["job_sha256"], "source_terminal_sha256": digest((sample / "terminal.json").read_bytes()),
        "source_inventory": source_inventory(sample),
        "original_state": terminal["state"], "state": state, "transport_recovered": recovered,
        "native_proof": native, "admission": acceptance, "response": answer if state == "accepted" else None,
        "no_resend": True, "new_votes": 0, "source_attempt_unchanged": True}
    key = row["endpoint"] + "-" + str(row["endpoint_ordinal"])
    commitments = reads.commitments()
    for name, meta in commitments.items():
        meta["snapshot"] = "native/" + key + "/" + name + ".bin"
    entry["native_sources"] = commitments
    return entry, {commitments[name]["snapshot"]: raw for name, raw in reads.raws.items()}


def source_inventory(sample):
    return {p.relative_to(sample).as_posix(): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
            for p in sorted(sample.rglob("*")) if p.is_file()
            and p.relative_to(sample).parts[0] not in {"transport-native", "transport-reconciliation.json", "effective-terminal.json"}}


def build(config, saved=None, snapshot=None):
    context = study_context(config)
    module, manifest = context["module"], context["manifest"]
    require(len(manifest["requests"]) == DENOMINATORS[config["study"]], "Full original planned denominator differs")
    entries, snapshots, reserved = [], {}, {"grok": 0, "sol": 0}
    if config["study"] == "mfa":
        for endpoint, prior in context["prior"]["endpoints"].items():
            reserved[endpoint] = prior["reserved_prefix"]
            for entry in prior["prefix"]:
                row = next(r for r in manifest["requests"] if r["endpoint"] == endpoint and r["logical_sample_id"] == entry["logical_sample_id"])
                response = json.loads((module.sample_path(Path(prior["source_root_local_only"]), row) / "response.json").read_bytes()) if entry["state"] == "accepted" else None
                entries.append(dict(entry, endpoint=endpoint, transport_recovered=False, response=response,
                                    source_root_local_only=prior["source_root_local_only"], native_sources={}))
    require({s["endpoint"] for s in config["sources"]} == {"grok", "sol"} and len(config["sources"]) == 2, "One exact source chain per endpoint required")
    previous = {(e["endpoint"], e["logical_sample_id"]): e for e in saved["prefix"]} if saved else {}
    for source in config["sources"]:
        endpoint, output = source["endpoint"], Path(source["root_local_only"])
        binding = bound_source(context, config, source)
        rows = [row for row in manifest["requests"] if row["endpoint"] == endpoint]
        expected = {module.sample_path(output, row).name: row for row in rows if row["endpoint_ordinal"] > reserved[endpoint]}
        names = sorted(p.name for p in output.iterdir() if p.is_dir())
        require(set(names) <= set(expected), "Unknown or reserved source slot directory")
        require([expected[n]["endpoint_ordinal"] for n in names] == list(range(reserved[endpoint] + 1, reserved[endpoint] + len(names) + 1)), "Stopped source inventory has an unsettled gap")
        for name in names:
            row = expected[name]
            entry, retained = recover_slot(context, config, source, row, binding, previous.get((endpoint, row["logical_sample_id"])), snapshot)
            entries.append(entry)
            require(not set(snapshots) & set(retained), "Duplicate native snapshot identity")
            snapshots.update(retained)
            reserved[endpoint] = row["endpoint_ordinal"]
    require(len({(e["endpoint"], e["logical_sample_id"]) for e in entries}) == len(entries), "Duplicate reserved vote identity")
    receipt = {"schema_version": 1, "policy": POLICY, "config": config, "config_sha256": digest(canonical(config)),
        "manifest_sha256": config["manifest_sha256"], "implementation_sha256": digest(Path(__file__).read_bytes()),
        "receipt_reader_sha256": digest(Path(codex_receipts.__file__).read_bytes()), "prefix": entries,
        "reserved_through": reserved, "planned_denominator": len(manifest["requests"]),
        "untouched_request_sha256s": {endpoint: [r["request_sha256"] for r in manifest["requests"] if r["endpoint"] == endpoint and r["endpoint_ordinal"] > reserved[endpoint]] for endpoint in reserved},
        "summary": dict(Counter(e["state"] for e in entries)), "transport_recovered": sum(e["transport_recovered"] for e in entries),
        "new_provider_calls": 0, "new_votes": 0, "human_labels_opened": False,
        "original_native_envelopes_reconstructed": False, "physical_contact_cardinality_proven": False}
    return receipt, snapshots, context


def verify(receipt_path, expected_sha):
    raw = receipt_path.read_bytes()
    require(digest(raw) == expected_sha, "Exact transport descendant differs")
    saved = json.loads(raw)
    actual, _, context = build(saved["config"], saved, receipt_path.parent)
    require(actual == saved, "Transport descendant/source/native admission replay differs")
    return actual, context


def fresh_output(output, config):
    output = output.resolve()
    protected = [REPO, Path(config["manifest_path_local_only"]).parent, *(Path(s["root_local_only"]) for s in config["sources"])]
    protected.extend(Path(config[k]) for k in ("secondary_home_local_only", "grok_sessions_root_local_only"))
    if config.get("context_reconciliation"):
        protected.append(Path(config["context_reconciliation"]["path_local_only"]).parent)
    require(not output.exists() and all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in protected), "Fresh private descendant overlaps retained inputs")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raw = args.config.read_bytes()
    require(digest(raw) == args.config_sha256, "Exact recovery config differs")
    config = json.loads(raw)
    output = fresh_output(args.output_root, config)
    receipt, snapshots, _ = build(config)
    result = canonical(receipt)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for relative, content in snapshots.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(content)
        with (output / "reconciliation.json").open("xb") as stream:
            stream.write(result)
    print(json.dumps({"study": config["study"], "policy": POLICY, "dry_run": args.dry_run, "receipt_sha256": digest(result),
        "reserved_through": receipt["reserved_through"], "summary": receipt["summary"], "transport_recovered": receipt["transport_recovered"],
        "untouched": {e: len(rows) for e, rows in receipt["untouched_request_sha256s"].items()},
        "full_planned_denominator": receipt["planned_denominator"], "provider_calls": 0, "new_votes": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
