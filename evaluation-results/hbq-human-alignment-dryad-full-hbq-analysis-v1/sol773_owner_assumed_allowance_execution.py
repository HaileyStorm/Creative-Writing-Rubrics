"""One approved Sol 773 contact under the owner's explicit allowance assumption."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).with_name("sol773_replacement_execution.py")
BASE_SHA = "2138e139599b17de719e55d49b0ba6d0d98e5f645427a3e79d564ae673d272ba"
AUTHORITY = Path("C:/Users/Haile/Documents/cwr-dryad-sol773-replacement-authority-20260909-r1")
QUEUE = Path("C:/Users/Haile/.codex/state/model-work-queue")


def execute() -> dict:
    import hashlib
    import jsonschema

    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == BASE_SHA
    spec = importlib.util.spec_from_file_location("_sol773_reviewed_predecessor", BASE)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    manifest_raw, manifest = base._manifest(AUTHORITY / "manifest-candidate-v3.json")
    review_raw, _ = base._review(AUTHORITY / "independent-review-v1.json", manifest_raw)
    decision_path = AUTHORITY / "owner-decision-v1.json"
    base._decision(decision_path, manifest_raw, review_raw)
    prompt, schema = base._frozen_payload(manifest)
    output = Path(manifest["replacement_root"]).resolve()
    base._require(output == Path("C:/Users/Haile/Documents/sol773-replacement-execution-v1")
                  and not output.exists(), "Replacement slot already exists or differs")
    source_raw = Path(__file__).read_bytes()

    def route():
        value = next(row for row in json.loads((QUEUE / "routes.json").read_bytes())["routes"]
                     if row["name"] == base.ROUTE_NAME)
        base._require({key: value[key] for key in manifest["route_identity"]} == manifest["route_identity"]
                      and value["armed"] is True and value["health"] == "healthy"
                      and value["zero_charge"] is True, "Existing subscription route differs")
        base._require(base._sha(Path(value["codex_command"][0]).read_bytes())
                      == value["codex_command_identity"]["artifacts"][0]["sha256"], "CLI differs")
        return value

    selected = route()
    output.mkdir(exist_ok=False)
    base._write_new(output / "payload/request-0773.txt", prompt)
    base._write_new(output / "payload/request-0773.json", schema)
    base._write_new(output / "runtime/route.json", base._canonical(selected))
    start = {"evidence_class": "sol773_owner_assumed_allowance_attempt_v1", "ordinal": 773,
             "manifest_sha256": base._sha(manifest_raw), "owner_decision_sha256": base._sha(decision_path.read_bytes()),
             "reviewed_predecessor_sha256": BASE_SHA, "actual_driver_sha256": base._sha(source_raw),
             "started_at": datetime.now(timezone.utc).isoformat(), "original_outcome": "unknown",
             "replacement_is_original": False, "automatic_774_dispatch": False,
             "allowance_policy": "owner_explicitly_requested_assume_limits_available_no_fresh_evidence",
             "override_reference": "User instruction on 2026-09-09 in task 01a07849-5012-7171-a6c4-8d13100e3464",
             "fresh_allowance_verified": False, "paid_fallback": False, "maximum_attempts": 1}
    start_raw = base._canonical(start)
    base._write_new(output / "replacement-start.json", start_raw)

    def gate():
        base._require(Path(__file__).read_bytes() == source_raw and BASE.read_bytes()
                      and base._sha(BASE.read_bytes()) == BASE_SHA, "Driver source differs")
        base._require(route() == selected and (output / "replacement-start.json").read_bytes() == start_raw
                      and (output / "payload/request-0773.txt").read_bytes() == prompt
                      and (output / "payload/request-0773.json").read_bytes() == schema, "Contact binding differs")
        base._write_new(output / "replacement-authorization.json", base._canonical({
            "start_sha256": base._sha(start_raw), "authorized_at": datetime.now(timezone.utc).isoformat(),
            "allowance_policy": start["allowance_policy"], "fresh_allowance_verified": False}))

    adapter = base._load(base.ADAPTER_PATH, base.ADAPTER_SHA256, "adapter")
    try:
        content, record = adapter.call_codex(executable=selected["codex_command"][0], model=base.MODEL,
            reasoning=base.REASONING, prompt=prompt.decode("utf-8"), output_dir=output,
            response_schema=output / "payload/request-0773.json", batch_number=14,
            timeout=base.TIMEOUT, attempt_number=1, before_provider_attempt=gate)
        raw = content.encode("utf-8")
        base._write_new(output / "replacement-response.json", raw)
        base._write_new(output / "replacement-provider-record.json", base._canonical(record))
        response = json.loads(raw)
        jsonschema.validate(response, json.loads(schema))
        base._require([row["question_id"] for row in response["verdicts"]] == base.QUESTION_IDS, "Question IDs differ")
        base._require((output / "responses/batch-0014.attempt-0001.message.json").read_bytes() == raw, "Native message differs")
        v3 = adapter._base()
        artifacts = record["provider_artifacts"]
        for descriptor in artifacts.values():
            path = (output / descriptor["path"]).resolve()
            base._require(path.is_relative_to(output) and base._sha(path.read_bytes()) == descriptor["sha256"]
                          and len(path.read_bytes()) == descriptor["bytes"], "Native artifact differs")
        projection = v3._codex_event_projection((output / artifacts["codex_events"]["path"]).read_bytes(), v3._load_parse_codex_events())
        base._require(projection["completed_agent_message_text"].encode("utf-8") == raw
                      and record["reported"] == v3._strict_stderr_labels((output / artifacts["codex_stderr"]["path"]).read_bytes()),
                      "Native event or stderr differs")
        base._frozen_payload(manifest)
        result = {"state": "replacement_accepted_under_owner_allowance_assumption", "response_sha256": base._sha(raw),
                  "thread_id": projection["thread_id"], "verdict_count": len(response["verdicts"])}
    except Exception as error:
        result = {"state": "replacement_stopped_no_retry", "error_type": type(error).__name__}
    result.update({"evidence_class": "sol773_owner_assumed_allowance_result_v1", "start_sha256": base._sha(start_raw),
                   "original_ordinal": 773, "replacement_is_original": False, "fresh_allowance_verified": False,
                   "automatic_774_dispatch": False, "full_study_admission": False})
    base._write_new(output / "replacement-terminal.json", base._canonical(result))
    return result


if __name__ == "__main__":
    print(json.dumps(execute()), flush=True)
