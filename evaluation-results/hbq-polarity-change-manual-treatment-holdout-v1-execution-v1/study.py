"""Sealed P1 same-fixture current-versus-treatment A/B holdout executor.

The executor deliberately has no expected-label data.  Settlement is the only
entry point allowed to open the separate ledger after execution completes.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-polarity-change-manual-treatment-holdout-v1-execution-v1"
REPEATS, ARMS, FIXTURE_COUNT, SLOT_COUNT, MAX_SENDS = 3, ("CURRENT", "TREATMENT"), 20, 120, 360
BUNDLE_ID = "p1-manual-treatment-holdout"
CANDIDATE_APPENDIX_SHA256 = "00ce0c5f1063c1fb36cc663bd2c522ce5eda254ee8f9079ec21774277e0d3722"
PRIVATE_CORPUS_SHA256 = "2baff4dcd7c96054cd6208bd61b243a4435f15de323c42db152702dc2299ff1b"
SEALED_EXPECTED_LEDGER_SHA256 = "231448f3bbcfcd88f12ed4cf8510c16ddd48d907cc203d3a99d6ba62893536e9"

# Public commitment only.  Fixture texts remain in the sealed private corpus.
FIXTURE_SPEC = (
    ("H01", "form.hybrid.translation_or_transcreation.culture"), ("H02", "form.hybrid.translation_or_transcreation.culture"),
    ("H03", "op.select.pairwise_comparison.same_criteria"), ("H04", "op.select.pairwise_comparison.same_criteria"),
    ("H05", "core.change_authorization.voice"), ("H06", "core.change_authorization.voice"),
    ("H07", "core.economy_and_relevance.functional_repetition"), ("H08", "core.economy_and_relevance.functional_repetition"),
    ("H09", "form.multimodal.text_image_alignment.focus"), ("H10", "form.multimodal.text_image_alignment.focus"),
    ("H11", "op.critique.structural_audit.opening_ending"), ("H12", "op.critique.structural_audit.opening_ending"),
    ("H13", "op.ingest.context_provenance.superseded"), ("H14", "op.ingest.context_provenance.superseded"),
    ("H15", "form.drama.game_narrative_quest_writing.state_dialogue"), ("H16", "form.drama.game_narrative_quest_writing.state_dialogue"),
    ("H17", "core.coherence_and_comprehensibility.referents"), ("H18", "core.mechanics_and_presentation.dialogue_mechanics"),
    ("H19", "craft.narrative.setting_and_atmosphere.no_inventory"), ("H20", "core.coherence_and_comprehensibility.sentence_meaning"),
)

def canonical(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
def digest(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def sha(path: Path) -> str: return digest(path.read_bytes())
def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError(f"Expected object: {path}")
    return value
def outside(value: str | Path) -> Path:
    path = Path(value).resolve()
    if REPOSITORY.resolve() in path.parents or path == REPOSITORY.resolve(): raise ValueError("private_root must be outside the CWR checkout")
    return path
def frozen(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != value: raise ValueError(f"Refusing to mutate frozen artifact: {path}")
    if not path.exists(): path.write_bytes(value)
def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); temp = path.with_name(path.name + ".tmp"); temp.write_bytes(canonical(value)); temp.replace(path)
def appendix() -> str:
    source = ROOT.parent / "hbq-polarity-change-manual-treatment-v1" / "study.py"
    spec = importlib.util.spec_from_file_location("p1_holdout_appendix_source", source)
    if spec is None or spec.loader is None: raise ValueError("Cannot load frozen candidate appendix")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    value = module.TREATMENT_APPENDIX
    if digest(value.encode("utf-8")) != CANDIDATE_APPENDIX_SHA256: raise ValueError("Candidate appendix hash drifted")
    return value
def leaf_records() -> dict[str, dict[str, Any]]:
    wanted = {leaf for _, leaf in FIXTURE_SPEC}; found = {}
    for line in (REPOSITORY / "registry/question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in wanted: found[row["id"]] = {key: row[key] for key in ("module_id", "text", "question_type", "applies_when", "evidence_policy")}
    if set(found) != wanted: raise ValueError("Holdout leaf binding drifted")
    return found
def fixture_spec() -> list[dict[str, str]]: return [{"fixture_id": fixture_id, "leaf_id": leaf_id} for fixture_id, leaf_id in FIXTURE_SPEC]
def private_corpus(root: Path) -> list[dict[str, Any]]:
    if sha(root / "private-corpus.json") != PRIVATE_CORPUS_SHA256: raise ValueError("Private holdout corpus commitment drifted")
    value = load(root / "private-corpus.json")
    required = {"format_version", "study_id", "privacy", "authorship", "fixtures"}
    if set(value) != required or value["format_version"] != 1 or value["study_id"] != STUDY_ID or value["privacy"] != "fixture_text_and_leaf_mapping_only_no_labels_or_arms" or value["authorship"] != "post-development independent authored holdout without private-response access": raise ValueError("Private holdout corpus contract drifted")
    rows = value["fixtures"]
    if not isinstance(rows, list) or [{"fixture_id": row.get("fixture_id"), "leaf_id": row.get("leaf_id")} for row in rows] != fixture_spec() or any(set(row) != {"fixture_id", "leaf_id", "artifact_kind", "declared_scope", "completion_status", "text"} or not isinstance(row.get("text"), str) or not row["text"] for row in rows): raise ValueError("Private holdout corpus mapping or privacy drifted")
    return rows
def contract() -> dict[str, Any]: return load(ROOT / "study-contract.json")
def validate_package() -> dict[str, Any]:
    value = contract()
    expected = {"format_version": 1, "study_id": STUDY_ID, "status": "frozen_same_fixture_ab_holdout_unexecuted", "candidate_appendix_sha256": CANDIDATE_APPENDIX_SHA256, "private_corpus_sha256": PRIVATE_CORPUS_SHA256, "sealed_expected_ledger_sha256": SEALED_EXPECTED_LEDGER_SHA256, "geometry": {"fixtures": 20, "target_fixtures": 16, "control_fixtures": 4, "leaves": 12, "arms": ["CURRENT", "TREATMENT"], "repeats": 3, "slots": 120}, "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "batch_attempts": 3, "maximum_provider_sends": 360, "attempt_lifecycle_policy": "terminal_sidecar_v1", "zero_incremental_charge_only": True, "paid_fallback_forbidden": True}, "privacy": {"executor_reads_expected_ledger": False, "dry_run_reads_expected_ledger": False, "private_corpus_contains_labels": False, "private_corpus_contains_arms": False, "settlement_opens_ledger_only_after_execution": True}, "promotion": "none_pending_settlement_and_independent_review"}
    if value != expected: raise ValueError("Holdout contract drifted")
    if digest(appendix().encode("utf-8")) != CANDIDATE_APPENDIX_SHA256: raise ValueError("Candidate appendix drifted")
    if len({row["leaf_id"] for row in fixture_spec()}) != 12: raise ValueError("Holdout leaf geometry drifted")
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": SLOT_COUNT, "sealed_ledger_unopened": True}
def _bundle() -> list[dict[str, Any]]:
    records = leaf_records(); leaves = list(dict.fromkeys(row["leaf_id"] for row in fixture_spec()))
    modules = list(dict.fromkeys(records[leaf]["module_id"] for leaf in leaves))
    return [{"$schema": "../schema/hbq_bundle.schema.json", "standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 1, "task_contract_domain_id": "p1ab-01", "title": "P1 sealed same-fixture A/B holdout", "artifact_types": ["synthetic_diagnostic"], "valid_scopes": ["excerpt", "passage", "scene", "work"], "profile": {}, "module_ids": modules, "domains": [{"domain_id": f"p1ab-{i:02d}", "title": leaf, "points": 1.0, "components": [{"module_id": records[leaf]["module_id"], "weight": 1.0, "include_question_ids": [leaf]}], "score_mode": "weighted_binary_mean"} for i, leaf in enumerate(leaves, 1)], "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": False, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True}, "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True}, "judge_policy": {"artifact_assumed_ai_generated": True, "strict_but_fair": True, "no_glazing": True, "judge_execution_not_intent": True, "do_not_invent_defects": True, "brief_evidence_required": True, "private_chain_of_thought_not_requested": True, "verdict_states": ["CANNOT_ASSESS", "NO", "NOT_APPLICABLE", "YES"]}, "notes": []}]
def schedule(root: Path) -> list[dict[str, Any]]:
    rows = []
    for fixture in private_corpus(root):
        artifact_hash = digest(fixture["text"].encode("utf-8")); artifact_id = "p1ab-a-" + digest(canonical({"text": fixture["text"], "leaf": fixture["leaf_id"]}))[:24]
        for arm in ARMS:
            for repeat in range(1, REPEATS + 1):
                slot_seed = canonical({"artifact": artifact_id, "arm": arm, "repeat": repeat})
                rows.append({**fixture, "artifact_id": artifact_id, "artifact_sha256": artifact_hash, "arm": arm, "repeat": repeat, "slot_id": "p1ab-s-" + digest(slot_seed)[:24], "judge_id": "p1ab-j-" + digest(canonical({"slot": digest(slot_seed), "leaf": fixture["leaf_id"]}))[:24]})
    if len(rows) != SLOT_COUNT or len({row["slot_id"] for row in rows}) != SLOT_COUNT or len({row["judge_id"] for row in rows}) != SLOT_COUNT: raise ValueError("Holdout execution geometry or identity drifted")
    return rows
def task(slot: Mapping[str, Any]) -> dict[str, Any]: return {"contract_version": 1, "contract_id": "p1ab-c-" + digest(str(slot["artifact_id"]).encode("utf-8"))[:20], "artifact_id": slot["artifact_id"], "context": {"artifact_kind": slot["artifact_kind"], "declared_scope": slot["declared_scope"], "completion_status": slot["completion_status"], "background": ["Sealed synthetic holdout evaluation."], "constraints": ["Evaluate only supplied evidence."], "audience": ["rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}
def override(slot: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]: return {"format_version": 1, "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": digest(canonical(payload)), "contract_id": payload["contract_id"], "artifact_kind": slot["artifact_kind"], "declared_scope": slot["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "p1ab-holdout-scope-compatibility", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for sealed singleton holdout bundle."}
def overlay(arm: str) -> dict[str, bytes]:
    binary = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")
    if arm == "TREATMENT": binary += b"\n\n" + appendix().encode("utf-8")
    return {"prompts/judge/JUDGE_PREFIX.md": (REPOSITORY / "prompts/judge/JUDGE_PREFIX.md").read_bytes(), "prompts/judge/BINARY_EVALUATION_PROMPT.md": binary + b"\n", "schema/hbq_judge_response.schema.json": (REPOSITORY / "schema/hbq_judge_response.schema.json").read_bytes(), "schema/hbq_task_contract.schema.json": (REPOSITORY / "schema/hbq_task_contract.schema.json").read_bytes(), "schema/hbq_verdict.schema.json": (REPOSITORY / "schema/hbq_verdict.schema.json").read_bytes(), "schema/hbq_diagnostic_report.schema.json": (REPOSITORY / "schema/hbq_diagnostic_report.schema.json").read_bytes(), "registry/all_modules.json": (REPOSITORY / "registry/all_modules.json").read_bytes()}
def prepare(private_root: str | Path) -> dict[str, Any]:
    root = outside(private_root); validate_package(); rows = schedule(root); frozen(root / "runtime-bundle.json", canonical(_bundle()))
    for arm in ARMS:
        for relative, value in overlay(arm).items(): frozen(root / "runtime-book" / arm.lower() / relative, value)
    for slot in rows:
        frozen(root / "inputs" / f"{slot['artifact_id']}.txt", str(slot["text"]).encode("utf-8")); payload = task(slot); frozen(root / "task-contracts" / f"{slot['artifact_id']}.json", canonical(payload)); frozen(root / "scope-overrides" / f"{slot['artifact_id']}.json", canonical(override(slot, payload)))
    arm_contract = {arm: {"overlay_sha256": {key: digest(value) for key, value in overlay(arm).items()}} for arm in ARMS}
    frozen(root / "arm-contract.json", canonical({"format_version": 1, "study_id": STUDY_ID, "same_fixture_ab": True, "arm_contract": arm_contract, "only_prompt_difference": "TREATMENT has exact candidate appendix; CURRENT has none", "candidate_appendix_sha256": CANDIDATE_APPENDIX_SHA256}))
    frozen(root / "remote-disclosure.json", canonical({"format_version": 1, "study_id": STUDY_ID, "destination": "Codex CLI -> authenticated OpenAI service", "material": "sealed private synthetic holdout fixtures plus frozen public judge prompts", "planned_slots": SLOT_COUNT, "paid_route": "forbidden", "expected_ledger": "not sent"}))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha(ROOT / "study-contract.json"), "private_corpus_sha256": sha(root / "private-corpus.json"), "arm_contract_sha256": sha(root / "arm-contract.json"), "slots": [{key: row[key] for key in ("slot_id", "artifact_id", "artifact_sha256", "leaf_id", "arm", "repeat", "judge_id")} for row in rows]}
    frozen(root / "study-manifest.json", canonical(manifest)); return {"private_root": str(root), "provider_calls": 0, "slots": SLOT_COUNT}
def env(root: Path, arm: str) -> dict[str, str]:
    value = dict(os.environ); value["HBQRS_ROOT"] = str(root / "runtime-book" / arm.lower()); return value
def question(slot: Mapping[str, Any]) -> dict[str, Any]:
    record = leaf_records()[str(slot["leaf_id"])]; return {"module_id": record["module_id"], "domain_id": record["module_id"], "role": "primary", "question": {"id": slot["leaf_id"], "text": record["text"], "question_type": record["question_type"], "applies_when": record["applies_when"], "evidence_policy": record["evidence_policy"]}}
def command(slot: Mapping[str, Any], root: Path, *, resume: bool = False) -> list[str]:
    result = [sys.executable, "-m", "hbqrs", "--registry", str(root / "runtime-book" / str(slot["arm"]).lower() / "registry" / "all_modules.json"), "--bundles", str(root / "runtime-bundle.json"), "judge", str(root / "inputs" / f"{slot['artifact_id']}.txt"), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai", "--batch-size", "1", "--batch-attempts", "3", "--attempt-lifecycle-policy", "terminal_sidecar_v1", "--artifact-id", slot["artifact_id"], "--judge-id", slot["judge_id"], "--task-contract", str(root / "task-contracts" / f"{slot['artifact_id']}.json"), "--scope-compatibility-override", str(root / "scope-overrides" / f"{slot['artifact_id']}.json"), "--question-id", slot["leaf_id"], "--output-dir", str(root / "runs" / slot["slot_id"])]
    if resume: result.append("--resume")
    return result
def render_command(slot: Mapping[str, Any], root: Path, output: Path) -> list[str]: return [sys.executable, "-m", "hbqrs", "--registry", str(root / "runtime-book" / str(slot["arm"]).lower() / "registry" / "all_modules.json"), "--bundles", str(root / "runtime-bundle.json"), "render-judge", "--bundle", BUNDLE_ID, "--artifact", str(root / "inputs" / f"{slot['artifact_id']}.txt"), "--artifact-id", slot["artifact_id"], "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--task-contract", str(root / "task-contracts" / f"{slot['artifact_id']}.json"), "--scope-compatibility-override", str(root / "scope-overrides" / f"{slot['artifact_id']}.json"), "--question-id", slot["leaf_id"], "--output", str(output)]
def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    root = outside(private_root); prepare(root); rendered = {}
    for slot in schedule(root):
        output = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if output.is_file():
            rendered[slot["slot_id"]] = digest(output.read_bytes())
            continue
        done = runner_call([*command(slot, root, resume=(root / "runs" / slot["slot_id"] / "run.json").is_file()), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False, env=env(root, str(slot["arm"])))
        if getattr(done, "returncode", 1) and (root / "runs" / slot["slot_id"] / "run.json").is_file():
            done = runner_call([*command(slot, root, resume=True), "--dry-run"], text=True, encoding="utf-8", capture_output=True, check=False, env=env(root, str(slot["arm"])))
        if getattr(done, "returncode", 1): raise RuntimeError(f"Dry run stopped at {slot['slot_id']}")
        output.parent.mkdir(parents=True, exist_ok=True); done = runner_call(render_command(slot, root, output), text=True, encoding="utf-8", capture_output=True, check=False, env=env(root, str(slot["arm"])))
        if getattr(done, "returncode", 1) or not output.is_file(): raise RuntimeError(f"Prompt rendering stopped at {slot['slot_id']}")
        data = output.read_bytes().replace(b"\r\n", b"\n"); output.write_bytes(data); rendered[slot["slot_id"]] = digest(data)
    by_pair = defaultdict(dict)
    for slot in schedule(root): by_pair[(slot["artifact_id"], slot["repeat"])][slot["arm"]] = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    for pair in by_pair.values():
        current, treatment = pair["CURRENT"].read_text(encoding="utf-8"), pair["TREATMENT"].read_text(encoding="utf-8")
        current_binary = overlay("CURRENT")["prompts/judge/BINARY_EVALUATION_PROMPT.md"].decode("utf-8")
        treatment_binary = overlay("TREATMENT")["prompts/judge/BINARY_EVALUATION_PROMPT.md"].decode("utf-8")
        if current.count(current_binary) != 1 or treatment != current.replace(current_binary, treatment_binary, 1): raise ValueError("A/B prompts differ by more or less than exact appendix")
    atomic(root / "runtime-schedule.json", {"format_version": 1, "slots": schedule(root), "rendered_prompt_sha256s": rendered, "aggregate_sha256": digest(canonical(rendered))})
    return {"mode": "dry_run", "provider_calls": 0, "slots": SLOT_COUNT, "expected_ledger_opened": False}
def execute(private_root: str | Path, *, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge: raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    root = outside(private_root); schedule_path = root / "runtime-schedule.json"
    if not schedule_path.is_file(): raise ValueError("Execution requires prior dry run")
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "destination": "Codex CLI -> authenticated OpenAI service", "material": "sealed private synthetic holdout fixtures plus frozen public judge prompts", "planned_slots": SLOT_COUNT, "paid_route": "forbidden", "expected_ledger": "not sent"}
    if not (root / "remote-disclosure.json").is_file() or (root / "remote-disclosure.json").read_bytes() != canonical(disclosure): raise ValueError("Execution requires exact remote disclosure")
    for slot in schedule(root):
        done = runner_call([*command(slot, root, resume=True), "--allow-remote"], text=True, encoding="utf-8", capture_output=True, check=False, env=env(root, str(slot["arm"])))
        if getattr(done, "returncode", 1): raise RuntimeError(f"Execution stopped at {slot['slot_id']}")
    return {"mode": "resume" if resume else "execute", "slots": SLOT_COUNT, "route": "codex", "expected_ledger_opened": False}
def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"]); manifest = load(run / "run.json"); config = manifest.get("configuration")
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping) or config.get("provider") != "codex" or config.get("model") != "gpt-5.6-sol" or config.get("reasoning") != "high" or config.get("artifact_id") != slot["artifact_id"] or config.get("judge_id") != slot["judge_id"] or config.get("question_ids") != [slot["leaf_id"]] or config.get("attempt_lifecycle_policy") != "terminal_sidecar_v1": raise ValueError("Run contract drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=3, reconstruct=False, strict_v5=True, require_durable=True)
    raw = gzip.decompress((run / "responses" / "batch-0001.prompt.txt.gz").read_bytes()).replace(b"\r\n", b"\n"); frozen_prompt = (root / "rendered-prompts" / f"{slot['slot_id']}.txt").read_bytes()
    if raw != frozen_prompt: raise ValueError("Receipt prompt differs from frozen prompt")
    verdicts, count, chain = runner._load_checkpoints(run, artifact_text=str(slot["text"]), context_texts=[], batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if count != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]: raise ValueError("Singleton receipt drifted")
    runner._validate_typed_checkpoint_evidence(verdicts[0].get("evidence"), question_id=str(slot["leaf_id"])); runner._validate_exact_quotes(verdicts[0].get("evidence"), artifact_text=str(slot["text"]), context_texts=[], question_id=str(slot["leaf_id"]))
    response = load(run / "responses" / "batch-0001.json"); reported = response.get("provider", {}).get("reported", {}); session = reported.get("session_id")
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"} or not isinstance(session, str) or not session: raise ValueError("Provider receipt drifted")
    return {"slot_id": slot["slot_id"], "verdict": verdicts[0].get("verdict"), "run_id": manifest.get("run_id"), "session_id_sha256": digest(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain}
def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    root = outside(private_root)
    if sha(root / "sealed-expected-ledger.json") != SEALED_EXPECTED_LEDGER_SHA256: raise ValueError("Sealed expected ledger commitment drifted")
    ledger = load(root / "sealed-expected-ledger.json")
    if ledger.get("format_version") != 1 or ledger.get("study_id") != STUDY_ID or set(ledger.get("expected", {})) != {row["fixture_id"] for row in fixture_spec()} or set(ledger["expected"].values()) - {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}: raise ValueError("Sealed expected ledger drifted")
    records = [verifier(root, slot) for slot in schedule(root)]; slots = {row["slot_id"]: row for row in schedule(root)}
    if len(records) != SLOT_COUNT or len({row["slot_id"] for row in records}) != SLOT_COUNT or any(not isinstance(row.get("run_id"), str) for row in records): raise ValueError("Incomplete holdout receipts")
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for record in records:
        slot = slots[record["slot_id"]]; cells[(slot["fixture_id"], slot["arm"])].append(record["verdict"] == ledger["expected"][slot["fixture_id"]])
    if len(cells) != 40 or any(len(value) != 3 for value in cells.values()): raise ValueError("Holdout cell geometry drifted")
    passed = {key: all(value) for key, value in cells.items()}; target = [f"H{i:02d}" for i in range(1, 17)]; controls = [f"H{i:02d}" for i in range(17, 21)]
    current_target, treatment_target = sum(passed[(item, "CURRENT")] for item in target), sum(passed[(item, "TREATMENT")] for item in target)
    current_controls, treatment_controls = sum(passed[(item, "CURRENT")] for item in controls), sum(passed[(item, "TREATMENT")] for item in controls)
    improved = [item for item in target if not passed[(item, "CURRENT")] and passed[(item, "TREATMENT")]]; defect_families = {"applicability": set(target[:8]), "comparison": set(target[8:])}
    stable = all(any(item in improved for item in family) for family in defect_families.values())
    if treatment_target == 16 and treatment_controls == 4 and current_controls == 4 and len(improved) >= 4 and stable: decision = "GO_PROMOTION"
    elif treatment_target == current_target and treatment_controls == current_controls: decision = "NO_EFFECT"
    elif treatment_target < 16 or treatment_controls < 4 or current_controls < 4: decision = "DIAGNOSTIC_FAIL"
    else: decision = "UNRESOLVED"
    summary = {"study_id": STUDY_ID, "candidate_appendix_sha256": CANDIDATE_APPENDIX_SHA256, "decision": decision, "completed_slots": SLOT_COUNT, "gates": {"treatment_target_48_of_48": treatment_target == 16, "treatment_60_of_60": treatment_target == 16 and treatment_controls == 4, "current_controls_12_of_12": current_controls == 4, "treatment_controls_12_of_12": treatment_controls == 4, "both_controls_24_of_24": current_controls == treatment_controls == 4, "target_improvements": len(improved), "stable_defect_in_both_families": stable}, "cells": {f"{fixture}|{arm}": {"match": sum(value), "denominator": 3, "passed": all(value)} for (fixture, arm), value in sorted(cells.items())}, "promotion_scope": "exact_candidate_appendix_only" if decision == "GO_PROMOTION" else "none", "promotion": "none_pending_independent_review" if decision == "GO_PROMOTION" else "none"}
    atomic(root / "settlement.json", summary); atomic(root / "public-aggregate.json", {key: value for key, value in summary.items() if key != "cells"}); return summary
def main() -> None:
    parser = argparse.ArgumentParser(); subs = parser.add_subparsers(dest="command", required=True); subs.add_parser("verify")
    for name in ("prepare", "dry-run", "execute", "settle"):
        item = subs.add_parser(name); item.add_argument("--private-root", required=True, type=Path)
        if name == "execute": item.add_argument("--resume", action="store_true"); item.add_argument("--allow-remote", action="store_true"); item.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    args = parser.parse_args(); result = validate_package() if args.command == "verify" else prepare(args.private_root) if args.command == "prepare" else dry_run(args.private_root) if args.command == "dry-run" else execute(args.private_root, resume=args.resume, allow_remote=args.allow_remote, acknowledged_zero_incremental_charge=args.acknowledge_zero_incremental_charge) if args.command == "execute" else settle(args.private_root); print(json.dumps(result, sort_keys=True))
if __name__ == "__main__": main()
