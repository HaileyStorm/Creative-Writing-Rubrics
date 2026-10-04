"""One-attempt secondary native Sol generation; intent review remains a later stage."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
_SPEC = importlib.util.spec_from_file_location("p1b_generation_prepare", HERE / "prepare.py")
prepare = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prepare)


def now():
    return datetime.now(timezone.utc).isoformat()


def record(path, value):
    prepare.write_new(path, prepare.canonical(value))


def read_pinned(root, relative, metadata):
    raw = prepare.within(root, relative).read_bytes()
    prepare.require(len(raw) == metadata["bytes"] and prepare.digest(raw) == metadata["sha256"], "Frozen request artifact differs")
    return raw


def mechanical_validate(row, answer, schema, subset):
    reasons, counts = [], {}
    if not subset.matches_schema(answer, schema):
        return {"accepted_generation": False, "reasons": ["response_schema"], "oracle_accepted": False,
                "eligible_for_scoring": False, "eligible_for_independent_intent_review": False}
    family = row["family"]
    if (answer["family_id"] != family["family_id"] or answer["form"] != family["form"]
            or answer["scope"] != family["scope"] or set(answer["variants"]) != set(prepare.VARIANTS)):
        reasons.append("family_variant_identity")
    if not 3 <= len(answer["preservation_anchors"]) <= 8:
        reasons.append("preservation_anchor_count")
    texts = []
    for role in prepare.VARIANTS:
        variant = answer["variants"][role]
        if variant["variant_id"] != family["variant_ids"][role]:
            reasons.append("variant_id")
        text = variant["text"]
        texts.append(text)
        words = len(re.findall(r"\S+", text))
        lines = len([line for line in text.splitlines() if line.strip()])
        counts[role] = {"words": words, "nonempty_lines": lines, "utf8_bytes": len(text.encode("utf-8"))}
        bounds = family["bounds"]
        if not bounds["min_words"] <= words <= bounds["max_words"]:
            reasons.append(role + "_word_bounds")
        if family["form"] == "poem" and not bounds["min_nonempty_lines"] <= lines <= bounds["max_nonempty_lines"]:
            reasons.append(role + "_line_bounds")
    if len(set(texts)) != 3:
        reasons.append("identical_variants")
    original_words = counts["original"]["words"]
    for role in prepare.VARIANTS[1:]:
        if abs(counts[role]["words"] - original_words) > original_words * family["max_variant_word_delta_fraction"]:
            reasons.append(role + "_word_delta")
    if family["form"] == "novel_work_segment" and not 50 <= len(re.findall(r"\S+", answer["work_context"])) <= 150:
        reasons.append("shared_work_context_word_bounds")
    accepted = not reasons
    return {"accepted_generation": accepted, "reasons": reasons, "mechanical_counts": counts,
            "oracle_accepted": False, "eligible_for_scoring": False,
            "eligible_for_independent_intent_review": accepted,
            "intent_status": "proposed_requires_independent_blinded_ai_intent_review",
            "semantic_intent_and_style_preservation_verified": False}


def verify_external_pins(manifest):
    pins, artifacts = manifest["external_pins"], manifest["artifacts"]
    checks = [(Path(pins["secondary_helper_path_local_only"]), artifacts["implementation/secondary-helper.py"]["sha256"]),
              (Path(pins["cli_path_local_only"]), pins["cli_sha256"]),
              (Path(pins["tools_root_local_only"]) / "adaptive_settings/account_probe.py", pins["account_probe_sha256"]),
              (REPO / "src/hbqrs/runner.py", artifacts["implementation/runner.py"]["sha256"]),
              (REPO / "src/hbqrs/codex_receipts.py", artifacts["implementation/codex_receipts.py"]["sha256"]),
              (Path(pins["tools_root_local_only"]) / "model_work_queue/adapters/json_schema_subset.py", artifacts["implementation/schema_subset.py"]["sha256"]),
              (HERE / "prepare.py", artifacts["implementation/prepare.py"]["sha256"]),
              (HERE / "collect.py", artifacts["implementation/collect.py"]["sha256"])]
    for path, expected in checks:
        prepare.require(prepare.digest(path.read_bytes()) == expected, "Frozen runtime/helper/CLI code pin differs")


def secondary_environment(manifest, helper):
    pins, runtime = manifest["external_pins"], manifest["runtime"]
    env = helper.collection_environment()
    home = Path(env.get("CODEX_HOME", "")).resolve()
    prepare.require(home == Path(pins["collection_home_path_local_only"]).resolve()
                    and home == helper.COLLECTION_HOME.resolve()
                    and home.name == "cwr-sol-secondary" and home.parent.name == "collection-accounts"
                    and prepare.digest(str(home).encode("utf-8")) == runtime["codex_home_sha256"]
                    and helper.CLI.resolve() == Path(pins["cli_path_local_only"]).resolve(), "Designated secondary home/CLI binding differs")
    prepare.require(not any(env.get(key) for key in ("CODEX_SQLITE_HOME", "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")),
                    "Secondary environment retains an alternate auth/state override")
    return env


def secondary_binding(manifest, helper, account):
    """Check an already obtained local account receipt; never probe here."""
    env = secondary_environment(manifest, helper)
    runtime = manifest["runtime"]
    identity = prepare.digest(prepare.canonical({"type": account.get("account_type"), "email": account.get("email", "").lower()}))
    prepare.require(account.get("account_type") == "chatgpt" and account.get("probe_exit_confirmed") is True
                    and identity == runtime["account_identity_sha256"] == prepare.SECONDARY_ACCOUNT_SHA256,
                    "Designated secondary subscription identity is unavailable")
    return env, {"account_identity_sha256": identity, "codex_home_sha256": runtime["codex_home_sha256"],
                 "probe_exit_confirmed": True, "destination": runtime["destination"]}


def job_binding(manifest, manifest_sha):
    return {"schema_version": 1, "manifest_sha256": manifest_sha, "design": prepare.DESIGN,
            "runtime": manifest["runtime"], "collector_sha256": manifest["artifacts"]["implementation/collect.py"]["sha256"],
            "runner_sha256": manifest["artifacts"]["implementation/runner.py"]["sha256"],
            "receipt_reader_sha256": manifest["artifacts"]["implementation/codex_receipts.py"]["sha256"],
            "helper_sha256": manifest["artifacts"]["implementation/secondary-helper.py"]["sha256"],
            "cli_sha256": manifest["external_pins"]["cli_sha256"], "automatic_retries": 0,
            "provider_contact_cardinality_proven": False, "eligible_for_scoring": False}


def expected_account_binding(manifest):
    runtime = manifest["runtime"]
    return {"account_identity_sha256": runtime["account_identity_sha256"], "codex_home_sha256": runtime["codex_home_sha256"],
            "probe_exit_confirmed": True, "destination": runtime["destination"]}


def sample_path(output, row):
    return output / f"{row['ordinal']:04d}-{row['logical_sample_id'][:12]}"


def verify_accepted(sample, row, manifest, manifest_sha, frozen, receipts, subset):
    terminal = sample / "terminal.json"
    prepare.require(terminal.is_file(), "Existing started attempt is unresolved; no resend")
    state = json.loads(terminal.read_bytes())
    prepare.require(state.get("state") == "accepted_generation" and state.get("no_resend") is True
                    and state.get("manifest_sha256") == manifest_sha,
                    "Existing rejected/unadmitted attempt requires reconciliation; no resend")
    prepare.require(json.loads((sample / "condition.json").read_bytes()) == row, "Accepted condition changed")
    for name in ("condition", "attempt-started", "native-result", "response", "validation"):
        prepare.require(prepare.digest((sample / f"{name}.json").read_bytes()) == state[name + "_sha256"], "Accepted generation evidence changed")
    started = json.loads((sample / "attempt-started.json").read_bytes())
    prepare.require(started["logical_sample_id"] == row["logical_sample_id"] and started["manifest_sha256"] == manifest_sha
                    and started["attempt"] == 1 and started["no_resend"] is True
                    and started["prompt_sha256"] == row["prompt_sha256"] and started["schema_sha256"] == row["schema_sha256"],
                    "Accepted attempt identity changed")
    prepare.require(prepare.digest((sample.parent / "account-binding.json").read_bytes()) == started["account_binding_sha256"],
                    "Accepted secondary account receipt changed")
    prepare.require(json.loads((sample.parent / "account-binding.json").read_bytes()) == expected_account_binding(manifest),
                    "Accepted secondary account receipt differs from prospective binding")
    prompt = read_pinned(frozen, row["prompt_path"], manifest["artifacts"][row["prompt_path"]]).decode("utf-8")
    schema_raw = read_pinned(frozen, row["schema_path"], manifest["artifacts"][row["schema_path"]])
    prepare.require((sample / "schema.json").read_bytes() == schema_raw and (sample / "prompt.txt").read_text(encoding="utf-8") == prompt,
                    "Accepted prompt/schema copy changed")
    provider = json.loads((sample / "native-result.json").read_bytes())
    message = prepare.within(sample, provider["provider_artifacts"]["codex_message"]["path"])
    final_raw = message.read_bytes()
    receipts.verify(sample, provider, prompt=prompt, model=prepare.MODEL, reasoning=prepare.EFFORT, final_raw=final_raw)
    answer = json.loads((sample / "response.json").read_bytes())
    prepare.require(answer == json.loads(final_raw), "Derived response differs from native final")
    validation = mechanical_validate(row, answer, json.loads(schema_raw), subset)
    prepare.require(validation["accepted_generation"] and json.loads((sample / "validation.json").read_bytes()) == validation,
                    "Accepted generation mechanical validation changed")
    for role in prepare.VARIANTS:
        metadata = state["derived_artifacts"][role]
        raw = prepare.within(sample, metadata["path"]).read_bytes()
        prepare.require(raw == answer["variants"][role]["text"].encode("utf-8") and len(raw) == metadata["bytes"]
                        and prepare.digest(raw) == metadata["sha256"], "Derived creative source changed")
    return state


def note_stop(output, row=None):
    path = output / "stop-observed.json"
    if not path.exists():
        record(path, {"observed_at": now(), "logical_sample_id": row["logical_sample_id"] if row else None,
                      "behavior": "prevent_new_contact; current bounded call settles", "no_cooperative_cancel_claim": True})


def collect_one(row, manifest, manifest_sha, frozen, output, call_codex, receipts, subset):
    sample = sample_path(output, row)
    sample.mkdir(exist_ok=False)
    record(sample / "condition.json", row)
    prompt_raw = read_pinned(frozen, row["prompt_path"], manifest["artifacts"][row["prompt_path"]])
    schema_raw = read_pinned(frozen, row["schema_path"], manifest["artifacts"][row["schema_path"]])
    prepare.write_new(sample / "prompt.txt", prompt_raw)
    prepare.write_new(sample / "schema.json", schema_raw)
    attempt_id = str(uuid.uuid4())
    terminal = {"schema_version": 1, "manifest_sha256": manifest_sha, "logical_sample_id": row["logical_sample_id"],
                "attempt_id": attempt_id, "no_resend": True, "oracle_accepted": False, "eligible_for_scoring": False}
    def before_contact():
        if (output / "STOP").exists():
            note_stop(output, row)
            raise RuntimeError("Stop observed before native launch")
        record(sample / "attempt-started.json", {"started_at": now(), "attempt_id": attempt_id, "attempt": 1,
            "manifest_sha256": manifest_sha, "logical_sample_id": row["logical_sample_id"],
            "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
            "account_binding_sha256": prepare.digest((output / "account-binding.json").read_bytes()),
            "state": "before_native_launch", "physical_contact_proven": False, "no_resend": True})
    try:
        content, provider = call_codex(executable=manifest["external_pins"]["cli_path_local_only"],
            model=prepare.MODEL, reasoning=prepare.EFFORT, prompt=prompt_raw.decode("utf-8"), output_dir=sample,
            response_schema=sample / "schema.json", batch_number=1, attempt_number=1,
            timeout=manifest["runtime"]["timeout_seconds"], before_provider_attempt=before_contact,
            codex_receipt_policy=prepare.POLICY)
        record(sample / "native-result.json", provider)
        final_raw = prepare.within(sample, provider["provider_artifacts"]["codex_message"]["path"]).read_bytes()
        receipts.verify(sample, provider, prompt=prompt_raw.decode("utf-8"), model=prepare.MODEL,
                        reasoning=prepare.EFFORT, final_raw=final_raw)
        answer = json.loads(final_raw)
        prepare.require(answer == json.loads(content), "Returned JSON differs from immutable native final")
        record(sample / "response.json", answer)
        validation = mechanical_validate(row, answer, json.loads(schema_raw), subset)
        record(sample / "validation.json", validation)
        terminal["state"] = "accepted_generation" if validation["accepted_generation"] else "generation_rejected"
        terminal["eligible_for_independent_intent_review"] = validation["accepted_generation"]
        terminal["derived_artifacts"] = {}
        if validation["accepted_generation"]:
            for role in prepare.VARIANTS:
                raw = answer["variants"][role]["text"].encode("utf-8")
                relative = f"variants/{role}.txt"
                prepare.write_new(sample / relative, raw)
                terminal["derived_artifacts"][role] = {"path": relative, "bytes": len(raw), "sha256": prepare.digest(raw)}
        for name in ("condition", "attempt-started", "native-result", "response", "validation"):
            terminal[name + "_sha256"] = prepare.digest((sample / f"{name}.json").read_bytes())
    except BaseException as error:
        terminal.update(state="unadmitted_no_resend", eligible_for_independent_intent_review=False,
                        error_class=type(error).__name__, started=(sample / "attempt-started.json").exists())
        if getattr(error, "provider_record", None) is not None:
            terminal["provider_record"] = error.provider_record
        terminal["retained_artifacts"] = {path.relative_to(sample).as_posix(): {"bytes": path.stat().st_size,
            "sha256": prepare.digest(path.read_bytes())} for path in sample.rglob("*") if path.is_file()}
        record(sample / "terminal.json", terminal)
        if (output / "STOP").exists():
            note_stop(output, row)
        if not isinstance(error, Exception):
            raise
        return False
    record(sample / "terminal.json", terminal)
    if (output / "STOP").exists():
        note_stop(output, row)
    return terminal["state"] == "accepted_generation"


def output_preflight(output, frozen):
    output, frozen = output.resolve(), frozen.resolve()
    prepare.require(not output.is_relative_to(REPO) and not REPO.is_relative_to(output)
                    and not output.is_relative_to(frozen) and not frozen.is_relative_to(output),
                    "Private results must be outside repository and frozen inputs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    manifest, frozen, manifest_sha = prepare.read_manifest(args.manifest)
    prepare.require(manifest_sha == args.manifest_sha256, "Exact prospective manifest hash differs")
    output_preflight(args.results_dir, frozen)
    verify_external_pins(manifest)
    tools = Path(manifest["external_pins"]["tools_root_local_only"])
    subset = prepare.load_module("p1b_schema_subset", tools / "model_work_queue/adapters/json_schema_subset.py")
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import codex_receipts
    binding = job_binding(manifest, manifest_sha)
    job = args.results_dir / "job.json"
    if args.results_dir.exists():
        prepare.require(job.is_file() and json.loads(job.read_bytes()) == binding, "Existing generation job binding differs")
    pending, accepted = [], 0
    for row in manifest["requests"]:
        sample = sample_path(args.results_dir, row)
        schema = json.loads(read_pinned(frozen, row["schema_path"], manifest["artifacts"][row["schema_path"]]))
        subset.validate_schema(schema)
        if sample.exists():
            verify_accepted(sample, row, manifest, manifest_sha, frozen, codex_receipts, subset)
            accepted += 1
        else:
            pending.append(row)
    if args.validate_only:
        print(json.dumps({"state": "provider_free_validated", "accepted_generation": accepted, "untouched_requests": len(pending),
                          "provider_calls": 0, "eligible_for_scoring": False}, sort_keys=True))
        return 0
    if not pending:
        print(json.dumps({"state": "generation_complete_requires_independent_intent_review", "accepted_generation": accepted}))
        return 0
    if (args.results_dir / "STOP").exists():
        note_stop(args.results_dir)
        return 3
    helper = prepare.load_module("p1b_secondary_helper", Path(manifest["external_pins"]["secondary_helper_path_local_only"]))
    env = secondary_environment(manifest, helper)
    os.environ.clear()
    os.environ.update(env)
    sys.path.insert(0, str(tools))
    from adaptive_settings.account_probe import probe
    from hbqrs import runner
    _, account = secondary_binding(manifest, helper, probe(helper.CLI))
    if not args.results_dir.exists():
        args.results_dir.mkdir(parents=True, exist_ok=False)
        record(job, binding)
    account_path = args.results_dir / "account-binding.json"
    if account_path.exists():
        prepare.require(json.loads(account_path.read_bytes()) == account, "Secondary account binding changed")
    else:
        record(account_path, account)
    for row in pending:
        if (args.results_dir / "STOP").exists():
            note_stop(args.results_dir, row)
            return 3
        if not collect_one(row, manifest, manifest_sha, frozen, args.results_dir, runner._call_codex, codex_receipts, subset):
            print(json.dumps({"state": "generation_stopped_no_resend", "family_id": row["family"]["family_id"]}))
            return 3
        accepted += 1
        print(json.dumps({"state": "accepted_generation_pending_intent_review", "accepted_generation": accepted,
                          "family_id": row["family"]["family_id"], "eligible_for_scoring": False}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
