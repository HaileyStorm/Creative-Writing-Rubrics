"""One independently identified maximum-prompt native transport qualification."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
POLICY = "grok_longform_transport_v6_native_qualification_once_v1"
WRAPPER = HERE.parent / "hbq-longform-dependency-pilot-v1/collector_longform_v6.py"
WRAPPER_SHA = "8346f65731673b2a8008405012eefea835e8168ff887f6ee10799feafc82a55f"
PROMPT_SHA = "6d120a83c102d54a834ead21b784a31fb1eda0600d3ef723e4f177be1dca8c1d"
SCHEMA_SHA = "e485d49a37c69f147ffe0b199dd3e80ffe3a902b5fe073e53c9cf69acfc03c22"


def implementation():
    import hashlib
    import importlib.util
    if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != WRAPPER_SHA:
        raise ValueError("Frozen P4 v6 interface differs")
    spec = importlib.util.spec_from_file_location("cwr_v6_qualification_p4", WRAPPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


w = implementation()
c = w.c
canonical, digest, require = w.canonical, w.digest, w.require


def build_plan(manifest_path, tools, plan_dir, results_dir):
    require(sys.version_info[:3] == (3, 12, 12), "Qualification requires frozen CPython 3.12.12")
    _, commitment = w.profile(tools)
    manifest, root, subset, validator, receipts = c.load_manifest(manifest_path, w.MANIFEST_SHA, w.COLLECTOR_SHA, tools)
    rows = [r for r in manifest["requests"] if r["endpoint"] == "grok"]
    row = max(rows, key=lambda r: r["prompt_bytes"])
    require(row["endpoint_ordinal"] == 88 and row["prompt_bytes"] == 248426
            and row["prompt_sha256"] == PROMPT_SHA and row["schema_sha256"] == SCHEMA_SHA,
            "Pinned maximum P4 qualification condition differs")
    prompt, schema, _, _ = c.inputs(root, manifest, row)
    plan = {"schema_version": 1, "policy": POLICY, "execution_authority": False,
        "study_vote": False, "semantic_quality_claim": False, "model_read_whole_body_proven": False,
        "raw_own_history_exported_or_independently_recomputed": False,
        "source_manifest_path_local_only": str(manifest_path.resolve()), "source_manifest_sha256": w.MANIFEST_SHA,
        "source_artifacts": manifest["artifacts"], "source_condition": row,
        "tools_root_local_only": str(tools.resolve()), "plan_dir_local_only": str(plan_dir.resolve()),
        "results_dir_local_only": str(results_dir.resolve()), "qualifier_sha256": digest(Path(__file__).read_bytes()),
        "p4_interface_sha256": WRAPPER_SHA, "predecessor_collector_sha256": w.COLLECTOR_SHA,
        "v6_entry_sha256s": w.V6_PINS, "v6_execution_profile": commitment, "python_runtime": w.python_runtime(),
        "workers": 1, "timeout_seconds": 900, "max_turns": 1, "automatic_retries": 0, "no_resend": True,
        "outbound_receipt": {"destination": "xAI Grok Build saved subscription session",
            "payload_classification": "public_synthetic", "source_policy": row["prompt_policy"],
            "purpose": "transport qualification only; excluded from study votes and quality analysis",
            "prompt": {"sha256": digest(prompt), "byte_length": len(prompt)},
            "schema": {"sha256": digest(schema), "byte_length": len(schema)},
            "source_artifacts": row["sources"], "task_context": row["task_context"],
            "additional_prompt_text": False, "private_selection_or_human_labels_transmitted": False,
            "paid_fallback": False, "cost_token_cache_attestation": "only fields actually reported by native receipt"}}
    plan["qualification_id"] = digest(canonical([POLICY, w.MANIFEST_SHA, row["request_sha256"],
        plan["plan_dir_local_only"], plan["results_dir_local_only"]]))
    require(plan["qualification_id"] != row["logical_sample_id"], "Qualification must be independently identified")
    plan["content_sha256"] = digest(canonical(plan))
    return plan, manifest, root, subset, validator, receipts


def validate_route(plan, route, route_sha, tools):
    derived, commitment = w.profile(tools)
    allowed = {"public_repo", "public_synthetic", "json_object", "identity_requested_only",
        "reasoning_unattested", "bounded_nonvisual_read_only", derived.CONTRACT_NAME}
    require(digest(canonical(route).rstrip(b"\n")) == route_sha, "Exact qualification route pin differs")
    require(route["name"] == "grok-build-grok-4.7" and route["adapter"] == "grok_exec"
            and route["provider"] == "xai_grok_build" and route["account_class"] == "subscription"
            and route["model"] == "grok-4.7" and route["reported_model"] == "grok-4.7-build"
            and route["reasoning_effort"] == "high" and route["armed"] is True
            and route["health"] == "healthy" and route["trusted"] is True and route["zero_charge"] is True
            and route["timeout_seconds"] == 900 and route["nonvisual_max_turns"] == 1
            and route["nonvisual_transport_contract"] == derived.CONTRACT_NAME
            and set(route["capabilities"]) <= allowed and derived.CONTRACT_NAME in route["capabilities"]
            and "public_synthetic" in route["allowed_payload_classes"], "Exact no-tool zero-charge v6 route differs")
    require(plan["python_runtime"] == w.python_runtime() and plan["v6_execution_profile"] == commitment,
            "Frozen qualification runtime/profile differs")
    require(route["command"] == [str(Path(sys.executable).resolve()), str(HERE / "adapters/grok_exec.py"),
            "--tools-root", str(tools.resolve())], "Named v6 adapter/interpreter/tools command differs")
    require(c.grok_contact_allowed(route), "Expiry/campaign 900-second margin prevents qualification")
    return derived


def verify_native(sample, job, prompt, schema, derived):
    native = json.loads((sample / "native-result.json").read_bytes())
    identity = json.loads((sample / "native-identity.json").read_bytes())
    started = json.loads((sample / "attempt-started.json").read_bytes())
    session = identity["session_id"]
    require(json.loads((sample.parent / "job.json").read_bytes()) == job and job["policy"] == POLICY
            and job["study_vote"] is False and job["plan"]["qualification_id"] == job["qualification_id"]
            and (sample / "prompt.txt").read_bytes() == prompt and (sample / "schema.json").read_bytes() == schema,
            "Own immutable qualification job/input differs")
    require(native["state"] == "completed" and str(uuid.UUID(session)) == session
            and identity["qualification_id"] == job["qualification_id"]
            and started["session_id"] == session and started["qualification_id"] == job["qualification_id"]
            and started["job_sha256"] == digest((sample.parent / "job.json").read_bytes())
            and started["prompt_sha256"] == digest(prompt) and started["schema_sha256"] == digest(schema)
            and started["source_manifest_sha256"] == job["plan"]["source_manifest_sha256"]
            and started["source_request_sha256"] == job["plan"]["source_condition"]["request_sha256"]
            and started["attempt"] == 1 and started["no_resend"] is True
            and datetime.fromisoformat(started["time"]).utcoffset() is not None,
            "Own qualification started/session/job/prompt/schema binding differs")
    result = native["result"]
    require(result["runtime"]["adapter_version"] == 6
            and result["runtime"]["execution_contract"]["nonvisual_transport_contract"] == derived.CONTRACT,
            "Own native execution is not exact v6")
    envelope = (sample / "native-envelope.json").read_bytes()
    module = derived.load_broker()

    class OwnEnvelope(module.Broker):
        def read_grok_native_envelope(self, descriptor):
            require(descriptor["sha256"] == digest(envelope) and descriptor["byte_length"] == len(envelope),
                    "Own native envelope bytes differ")
            return envelope

    parsed = OwnEnvelope(sample.parent)._parse_grok_exec_envelope(module._canonical({
        "control": {"version": 1, "state": "completed"}, "result": result}),
        {**job["route"], "output_schema": json.loads(schema)}, {"prompt": prompt.decode("utf-8")},
        expected_session_id=session)
    require(parsed.state == "completed", "Full native qualification receipt rejected; no resend")
    return result["output"]


def execute(output, plan, plan_sha, route, route_sha, root, manifest, subset, validator, broker, derived):
    require(not output.exists(), "Qualification handle already reserved; no resend")
    require(c.grok_contact_allowed(route), "Expiry/campaign margin prevents qualification")
    prompt, schema, texts, context = c.inputs(root, manifest, plan["source_condition"])
    job = {"policy": POLICY, "qualification_id": plan["qualification_id"], "plan_sha256": plan_sha,
        "route": route, "route_sha256": route_sha, "plan": plan, "study_vote": False,
        "automatic_retries": 0, "timeout_seconds": 900, "workers": 1, "no_resend": True}
    output.mkdir(parents=True, exist_ok=False)
    c.record(output / "job.json", job); c.record(output / "qualification-plan.json", plan)
    c.write_bytes(output / "frozen-manifest.json", (root / "manifest.json").read_bytes())
    sample = output / "attempt-0001"; sample.mkdir(exist_ok=False)
    session = str(uuid.uuid4())
    c.record(sample / "native-identity.json", {"session_id": session, "qualification_id": plan["qualification_id"]})
    c.write_bytes(sample / "prompt.txt", prompt); c.write_bytes(sample / "schema.json", schema)
    terminal = {"policy": POLICY, "qualification_id": plan["qualification_id"], "session_id": session,
        "job_sha256": digest((output / "job.json").read_bytes()), "study_vote": False, "no_resend": True,
        "transport_qualified": False, "semantic_quality_claim": False, "model_read_whole_body_proven": False,
        "semantic_admission": "not_evaluated", "state": "unadmitted_no_resend"}

    def before():
        require(not (output / "STOP").exists(), "STOP prevents qualification contact")
        require(c.grok_contact_allowed(route), "Expiry/campaign margin prevents qualification contact")
        c.record(sample / "attempt-started.json", {"time": datetime.now(timezone.utc).isoformat(),
            "session_id": session, "qualification_id": plan["qualification_id"], "attempt": 1, "no_resend": True,
            "job_sha256": terminal["job_sha256"], "prompt_sha256": digest(prompt), "schema_sha256": digest(schema),
            "source_manifest_sha256": plan["source_manifest_sha256"],
            "source_request_sha256": plan["source_condition"]["request_sha256"]})

    try:
        require(not (output / "STOP").exists(), "STOP prevents qualification dispatch")
        native = broker.run_grok_native_request(route["name"], {"prompt": prompt.decode("utf-8")},
            output_schema=json.loads(schema), nonvisual_max_turns=1, session_id=session,
            before_contact=before, expected_route_sha256=route_sha)
        c.record(sample / "native-result.json", native)
        terminal["state"] = native["state"]
        if native["state"] == "completed":
            c.write_bytes(sample / "native-envelope.json", broker.read_grok_native_envelope(native["result"]["native_envelope_artifact"]))
            answer = verify_native(sample, job, prompt, schema, derived)
            terminal.update(transport_qualified=True, state="transport_qualified")
            c.record(sample / "response.json", answer)
            acceptance = validator.semantic_validate(plan["source_condition"]["arm"], answer,
                plan["source_condition"], texts, subset, context=context, schema=json.loads(schema))
            c.record(sample / "semantic-admission.json", acceptance)
            terminal["semantic_admission"] = "accepted_unscored" if acceptance["accepted"] else "rejected_unscored"
        else:
            failure = native.get("failure") or {}
            if failure.get("diagnostic_hash"):
                path = broker._artifact_path(failure["diagnostic_hash"])
                raw = path.read_bytes(); require(digest(raw) == failure["diagnostic_hash"], "Own failure diagnostic differs")
                c.write_bytes(sample / "native-failure-diagnostic.json", raw)
    except BaseException as error:
        terminal["error_class"] = type(error).__name__
        if not terminal["transport_qualified"]: terminal["state"] = "unadmitted_no_resend"
        if not isinstance(error, Exception):
            terminal["artifact_sha256s"] = {p.name: digest(p.read_bytes()) for p in sample.iterdir() if p.is_file()}
            c.record(sample / "terminal.json", terminal)
            raise
    terminal["stop_observed_after_settlement"] = (output / "STOP").exists()
    terminal["artifact_sha256s"] = {p.name: digest(p.read_bytes()) for p in sample.iterdir() if p.is_file()}
    c.record(sample / "terminal.json", terminal)
    return terminal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("tools-root", "results-dir"): parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prepare", action="store_true"); parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    for name in ("manifest", "plan-dir", "plan", "route-root"): parser.add_argument("--" + name, type=Path)
    parser.add_argument("--plan-sha256"); parser.add_argument("--route-sha256")
    args = parser.parse_args(argv)
    output = args.results_dir.resolve()
    if args.prepare:
        require(args.manifest is not None and args.plan_dir is not None, "Preparation needs manifest and fresh plan directory")
        plan, _, root, _, _, _ = build_plan(args.manifest, args.tools_root, args.plan_dir, output)
        w.safe_output(args.plan_dir, [root, args.tools_root, output]); w.safe_output(output, [root, args.tools_root, args.plan_dir])
        if not (args.dry_run or args.validate_only):
            args.plan_dir.mkdir(parents=True, exist_ok=False)
            c.record(args.plan_dir / "plan.json", plan)
            c.write_bytes(args.plan_dir / "source-manifest.json", args.manifest.read_bytes())
        print(json.dumps({"state": "provider_free_prepared", "plan_sha256": digest(canonical(plan)),
            "content_sha256": plan["content_sha256"], "profile_sha256": w.PROFILE_SHA,
            "prompt_bytes": 248426, "requests": 1, "provider_calls": 0, "study_votes": 0})); return 0
    require(args.plan is not None and args.plan_sha256 is not None, "Pinned qualification plan required")
    raw = args.plan.read_bytes(); require(digest(raw) == args.plan_sha256, "Qualification plan pin differs")
    saved = json.loads(raw)
    plan, manifest, root, subset, validator, _ = build_plan(Path(saved["source_manifest_path_local_only"]),
        args.tools_root, args.plan.parent, output)
    require(saved == plan and (args.plan.parent / "source-manifest.json").read_bytes() == (root / "manifest.json").read_bytes(),
            "Frozen qualification inputs/runtime/code/handle differ")
    w.safe_output(output, [root, args.tools_root, args.plan.parent] + ([args.route_root] if args.route_root else []))
    require(args.route_root is not None or args.validate_only or args.dry_run, "Execution requires exact armed v6 route")
    if args.route_root is None:
        print(json.dumps({"state": "provider_free_validated_route_pending", "provider_calls": 0, "study_votes": 0})); return 0
    require(args.route_sha256 is not None, "Exact v6 route pin required")
    route = next(r for r in json.loads((args.route_root / "routes.json").read_bytes())["routes"] if r["name"] == "grok-build-grok-4.7")
    derived = validate_route(plan, route, args.route_sha256, args.tools_root)
    broker = derived.load_broker().Broker(args.route_root.resolve())
    broker._validate_route(route, verify_command_identity=True, validate_current_evidence=True)
    if args.validate_only or args.dry_run:
        print(json.dumps({"state": "provider_free_validated", "provider_calls": 0, "study_votes": 0})); return 0
    terminal = execute(output, plan, args.plan_sha256, route, args.route_sha256, root, manifest, subset, validator, broker, derived)
    print(json.dumps({k: terminal[k] for k in ("state", "transport_qualified", "semantic_admission", "study_vote", "stop_observed_after_settlement")}))
    return 0 if terminal["transport_qualified"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
