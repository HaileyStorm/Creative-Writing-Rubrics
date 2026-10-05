"""Versioned local admission of task-context literals already present in MFA prompts."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collector as old

POLICY = "rendered_task_context_admission_v2"
PREDECESSOR_SHA256 = "a4a7073ff5d24875fcc1d866b727792ebdafa4ad70df327691a72e17cbcacc94"
canonical, digest, require = old.prepare.canonical, old.prepare.sha, old.require


def rendered_context(root, manifest, row, runner):
    _, _, _, context = old.inputs(root, manifest, row)
    if row["arm"] != "hbq":
        return context
    task_raw = old.pinned(root, row["task_contract_path"], manifest["artifacts"][row["task_contract_path"]])
    require(digest(task_raw) == row["task_contract_sha256"], "Frozen task contract differs")
    task = json.loads(task_raw)
    require(task["artifact_id"] == row["artifact_id"] and all(task[k] == [] for k in ("preferences", "priorities", "weighted_goals", "binding_requirements")), "Task context is not the registered context-only contract")
    literal = json.dumps(runner._task_contract_judge_context(task), ensure_ascii=False, indent=2)
    prompt = old.pinned(root, row["prompt_path"], manifest["artifacts"][row["prompt_path"]]).decode("utf-8")
    require(literal in prompt, "Exact rendered task-context projection is absent from pinned prompt")
    return context + "\n" + literal


def admission(root, manifest, validator, runner):
    def semantic_validate(arm, response, request, source_texts, subset, context="", schema=None):
        require(arm == request["arm"], "Admission arm differs")
        committed_context = rendered_context(root, manifest, request, runner)
        return validator.semantic_validate(arm, response, request, source_texts, subset, context=committed_context, schema=schema)
    return SimpleNamespace(semantic_validate=semantic_validate)


def frozen_runner(root, manifest):
    sys.path.insert(0, str(old.REPO / "src"))
    import hbqrs
    path = root / "implementation/runner.py"
    require(digest(path.read_bytes()) == manifest["artifacts"]["implementation/runner.py"]["sha256"], "Frozen runner differs")
    spec = importlib.util.spec_from_file_location("hbqrs.mfa_context_frozen_runner_v2", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_binding(output, endpoint, manifest, manifest_sha, expected_job_sha):
    raw = (output / "job.json").read_bytes()
    require(digest(raw) == expected_job_sha, "Exact original source job differs")
    job = json.loads(raw)
    require(job["manifest_sha256"] == manifest_sha and job["extraction_sha256"] == manifest["extraction_sha256"]
            and job["endpoint"] == endpoint and job["runtime"] == manifest["runtime"][endpoint]
            and job["collector_sha256"] == PREDECESSOR_SHA256 and job["policy"] == old.POLICY
            and job["workers"] == 1 and job["timeout_seconds"] == 900 and job["automatic_retries"] == 0
            and job["payload_classification"] == "public_repo" and job["implementation"] == manifest["implementation"]
            and job["artifacts_commitment_sha256"] == digest(canonical(manifest["artifacts"])), "Original source job contract differs")
    require((output / "STOP").is_file() and (output / "stop-observed.json").is_file(), "Original source job must have observed its STOP")
    stopped = json.loads((output / "stop-observed.json").read_bytes())
    require(stopped["behavior"] == "prevent new contact; current bounded call settles"
            and stopped["cooperative_cancellation_claimed"] is False, "Original STOP behavior differs")
    if endpoint == "grok":
        route = job["route"]
        require(job["route_sha256"] == digest(canonical(route).rstrip(b"\n")) and route["model"] == "grok-4.7"
                and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900
                and job["campaign_deadline"] == old.CUTOFF.isoformat() and job["deadline_margin_seconds"] == 900, "Original Grok route/deadline differs")
    return job


def inventory(sample):
    return {p.relative_to(sample).as_posix(): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
            for p in sorted(sample.rglob("*")) if p.is_file()}


def project_prefix(manifest, manifest_sha, root, output, endpoint, job_sha, receipts, subset, validator, runner):
    job = source_binding(output, endpoint, manifest, manifest_sha, job_sha)
    rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
    expected_dirs = {old.sample_path(output, r).name: r for r in rows}
    observed = {p.name for p in output.iterdir() if p.is_dir()}
    require(observed <= set(expected_dirs), "Unknown source attempt directory")
    prefix = [r for r in rows if old.sample_path(output, r).exists()]
    require([r["endpoint_ordinal"] for r in prefix] == list(range(1, len(prefix) + 1)), "Original source prefix has an unsettled gap")
    revised, summary = [], Counter({k: 0 for k in ("source_accepted", "source_semantic_rejected", "reconciled_accepted", "reconciled_semantic_rejected", "correctable_context_rejections", "still_invalid")})
    wrapped = admission(root, manifest, validator, runner)
    for row in prefix:
        sample = old.sample_path(output, row)
        terminal, _ = old.replay(sample, row, manifest, job, root, receipts, subset, validator)
        require(terminal["state"] in old.SETTLED, "Prefix native failure needs separate reconciliation; no resend")
        answer = json.loads((sample / "response.json").read_bytes())
        prompt, schema, texts, _ = old.inputs(root, manifest, row)
        require(answer == old.validate_native(sample, row, job, prompt, schema, receipts), "Original native final differs")
        corrected = wrapped.semantic_validate(row["arm"], answer, row, texts, subset, schema=json.loads(schema))
        state = "accepted" if corrected["accepted"] else "semantic_rejected"
        summary["source_" + terminal["state"]] += 1
        summary["reconciled_" + state] += 1
        summary["correctable_context_rejections"] += terminal["state"] == "semantic_rejected" and corrected["accepted"]
        summary["still_invalid"] += not corrected["accepted"]
        require(terminal["state"] != "accepted" or corrected["accepted"], "Context addition unexpectedly invalidates prior admission")
        revised.append({"request_sha256": row["request_sha256"], "logical_sample_id": row["logical_sample_id"],
            "endpoint_ordinal": row["endpoint_ordinal"], "original_state": terminal["state"], "state": state,
            "source_terminal_sha256": digest((sample / "terminal.json").read_bytes()), "source_artifacts": inventory(sample),
            "context_sha256": digest(rendered_context(root, manifest, row, runner).encode()), "admission": corrected,
            "no_resend": True, "new_votes": 0, "creative_source_unchanged": True})
    return {"endpoint": endpoint, "source_job_sha256": job_sha, "source_root_local_only": str(output.resolve()),
        "source_stop_sha256": digest((output / "STOP").read_bytes()), "source_stop_observed_sha256": digest((output / "stop-observed.json").read_bytes()),
        "planned_requests": len(rows), "reserved_prefix": len(prefix), "untouched_suffix": len(rows) - len(prefix),
        "physical_contact_completeness_proven": False, "slot_inventory_scope": "this exact stopped source job only",
        "summary": dict(summary), "prefix": revised,
        "untouched_request_sha256s": [r["request_sha256"] for r in rows if r["endpoint_ordinal"] > len(prefix)]}


def build(manifest, manifest_sha, root, sources, job_pins, receipts, subset, validator):
    require(digest((HERE / "collector.py").read_bytes()) == PREDECESSOR_SHA256, "Original collector implementation differs")
    runner = frozen_runner(root, manifest)
    endpoints = {e: project_prefix(manifest, manifest_sha, root, sources[e], e, job_pins[e], receipts, subset, validator, runner) for e in old.prepare.ENDPOINTS}
    return {"schema_version": 1, "policy": POLICY, "manifest_sha256": manifest_sha, "extraction_sha256": manifest["extraction_sha256"],
        "predecessor_collector_sha256": PREDECESSOR_SHA256, "reconciler_sha256": digest(Path(__file__).read_bytes()),
        "runner_sha256": manifest["artifacts"]["implementation/runner.py"]["sha256"], "endpoints": endpoints,
        "new_votes": 0, "new_provider_calls": 0, "source_attempts_unchanged": True, "human_labels_opened": False,
        "candidate_gain_claim": False, "denominators": {"per_endpoint": 434, "total": 868}}


def verify_descendant(receipt_path, expected_sha, manifest, manifest_sha, root, receipts, subset, validator):
    raw = receipt_path.read_bytes()
    require(digest(raw) == expected_sha, "Exact reconciliation receipt differs")
    saved = json.loads(raw)
    sources = {e: Path(saved["endpoints"][e]["source_root_local_only"]) for e in old.prepare.ENDPOINTS}
    pins = {e: saved["endpoints"][e]["source_job_sha256"] for e in old.prepare.ENDPOINTS}
    require(build(manifest, manifest_sha, root, sources, pins, receipts, subset, validator) == saved, "Reconciliation source or admission replay differs")
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--sol-source", type=Path, required=True)
    parser.add_argument("--grok-source", type=Path, required=True)
    parser.add_argument("--sol-job-sha256", required=True)
    parser.add_argument("--grok-job-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest, root, subset, validator = old.load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    sources = {"sol": args.sol_source.resolve(), "grok": args.grok_source.resolve()}
    output = old.prepare.extract.private_output(args.output_root, [root, *sources.values()])
    from hbqrs import codex_receipts
    result = build(manifest, args.manifest_sha256, root, sources, {"sol": args.sol_job_sha256, "grok": args.grok_job_sha256}, codex_receipts, subset, validator)
    raw = canonical(result)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        old.prepare.extract.write_new(output / "reconciliation.json", raw)
    print(json.dumps({"dry_run": args.dry_run, "policy": POLICY, "receipt_sha256": digest(raw), "provider_calls": 0,
        "endpoints": {e: {k: v for k, v in r.items() if k in ("planned_requests", "reserved_prefix", "untouched_suffix", "summary")} for e, r in result["endpoints"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
