"""Provider-free settlement repair for the committed final-manual execution."""
from __future__ import annotations

import hashlib
import gzip
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner
from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SOURCE_COMMIT = "ac216eb4ca2f34f2bc8baa89b7b885b9bdf3f7db"
STUDY_ID = "hbq-nonpoetry-scope-final-manual-v1-execution-v1"
SUCCESSOR_ID = "hbq-nonpoetry-scope-final-manual-v1-settlement-successor-v1"
EXECUTION_DIRECTORY = "execution-v4-stable-portable-terminal-v1"
LEAF_ID = "scope.passage.status"
SLOTS = 24
ORIGINAL_INCOMPLETE_SETTLEMENT_SHA256 = "f401892f788f424a57b90dca01f52bbbf7ea7649aaac6e214455c2d153f3954a"
ORIGINAL_RUNTIME_SCHEDULE_SHA256 = "6e365dd049d41ea8014ec8a6864d0019ecca0c400fe0e2afd3e8214155106c34"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_prompt_bytes(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""):
        raise ValueError("Checkpoint prompt contains a lone carriage return")
    return value.replace(b"\r\n", b"\n")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def write_once(path: Path, value: Any) -> None:
    data = canonical_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to replace immutable settlement output: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def private_execution_root(private_root: str | Path) -> Path:
    value = Path(private_root).resolve()
    repository = REPOSITORY.resolve()
    if value == repository or repository.is_relative_to(value) or value.is_relative_to(repository):
        raise ValueError("private_root must be disjoint from the CWR checkout")
    root = value / EXECUTION_DIRECTORY
    if not (root / "runtime-schedule.json").is_file():
        raise ValueError("Exact committed private execution root is unavailable")
    return root


def source_commit_is_ancestor() -> bool:
    done = subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    return done.returncode == 0


def expected_questions(registry: Path, bundles: Path, task: Mapping[str, Any], bundle_id: str) -> tuple[str, str]:
    compiled = compile_bundle(load_modules(registry), resolve_bundle(load_bundles(bundles), bundle_id), task_contract=task)
    questions = [record for record in compiled_questions(compiled) if record["question"]["id"] == LEAF_ID]
    if len(questions) != 1:
        raise ValueError("Private catalog does not compile exactly the frozen leaf")
    return runner._sha256_bytes(runner._json_bytes(compiled)), runner._sha256_bytes(runner._json_bytes(runner._question_payload(questions)))


def verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run = root / "runs" / str(slot["slot_id"])
    manifest = read_json(run / "run.json")
    config = manifest.get("configuration")
    if manifest.get("format_version") != 5 or not isinstance(config, Mapping):
        raise ValueError("Production run is not terminal-sidecar format 5")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": "terminal_sidecar_v1", "artifact_id": slot["fixture_id"], "bundle_id": "diagnostic.nonpoetry_scope_final_manual", "question_ids": [LEAF_ID]}
    if any(config.get(key) != value for key, value in expected.items()) or manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Production configuration binding drifted")
    artifact = root / "inputs" / f"{slot['fixture_id']}.txt"
    task_path = root / "contracts" / f"{slot['fixture_id']}.json"
    override = root / "overrides" / f"{slot['fixture_id']}.json"
    contexts = sorted((root / "contexts" / str(slot["fixture_id"])).glob("context-*.txt"))
    prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    registry = root / "catalog" / f"{slot['arm']}-registry.json"
    bundles = root / "catalog" / "bundles.json"
    if config.get("artifact", {}).get("sha256") != sha256_file(artifact) or [item.get("sha256") for item in config.get("contexts", [])] != [sha256_file(path) for path in contexts] or config.get("task_contract", {}).get("sha256") != sha256_file(task_path) or config.get("scope_compatibility", {}).get("sha256") != sha256_file(override):
        raise ValueError("Private input binding drifted")
    compiled_sha, questions_sha = expected_questions(registry, bundles, read_json(task_path), str(config["bundle_id"]))
    if config.get("compiled_bundle_sha256") != compiled_sha or config.get("questions_sha256") != questions_sha:
        raise ValueError("Regenerated bundle or question commitment drifted")
    runner._validate_or_reconstruct_attempt_lifecycle(run, config_sha256=str(manifest["config_sha256"]), batch_attempts=3, reconstruct=False, strict_v5=True, require_durable=True)
    checkpoint = read_json(run / "responses" / "batch-0001.json")
    if checkpoint.get("accepted_attempt") != 1 or runner._rejected_records(run, 1):
        raise ValueError("Slot is not an exact first-attempt acceptance")
    reported = checkpoint.get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider identity drifted")
    verdicts, checkpoints, chain = runner._load_checkpoints(run, artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[path.read_text(encoding="utf-8") for path in contexts], batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != LEAF_ID or verdicts[0].get("run_id") != manifest.get("run_id"):
        raise ValueError("Checkpoint leaf or run identity drifted")
    runner._validate_typed_checkpoint_evidence(verdicts[0].get("evidence"), question_id=LEAF_ID)
    runner._validate_exact_quotes(verdicts[0].get("evidence"), artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[path.read_text(encoding="utf-8") for path in contexts], question_id=LEAF_ID)
    if sha256_file(prompt) != slot["rendered_prompt_sha256"]:
        raise ValueError("Frozen rendered prompt drifted")
    checkpoint_prompt = gzip.decompress((run / "responses" / "batch-0001.prompt.txt.gz").read_bytes())
    if canonical_prompt_bytes(checkpoint_prompt) != prompt.read_bytes():
        raise ValueError("Checkpoint prompt differs from frozen rendered prompt")
    return {"slot_id": slot["slot_id"], "arm": slot["arm"], "fixture_id": slot["fixture_id"], "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "verdict": verdicts[0].get("verdict"), "expected": slot["expected_verdict"], "checkpoint_chain_head_sha256": chain}


def settle(private_root: str | Path) -> dict[str, Any]:
    if not source_commit_is_ancestor():
        raise ValueError("Settlement successor requires the committed source lineage")
    root = private_execution_root(private_root)
    original = read_json(root / "settlement.v1.json")
    original_path = root / "settlement.v1.json"
    if sha256_file(original_path) != ORIGINAL_INCOMPLETE_SETTLEMENT_SHA256 or original.get("study_id") != STUDY_ID or original.get("decision") != "INCOMPLETE" or original.get("completed_slots") != 0 or original.get("planned_slots") != SLOTS or original.get("promotion") != "none" or not isinstance(original.get("failures"), list):
        raise ValueError("Original committed settlement must remain the preserved INCOMPLETE evidence")
    schedule_path = root / "runtime-schedule.json"
    runtime = read_json(schedule_path)
    if sha256_file(schedule_path) != ORIGINAL_RUNTIME_SCHEDULE_SHA256 or runtime.get("study_id") != STUDY_ID or runtime.get("provider_calls") != 0:
        raise ValueError("Committed runtime schedule identity drifted")
    schedule = runtime.get("slots")
    if not isinstance(schedule, list) or len(schedule) != SLOTS:
        raise ValueError("Committed runtime schedule geometry drifted")
    arms = [slot.get("arm") for slot in schedule]
    candidate_slots = [slot for slot in schedule if slot.get("arm") == "candidate"]
    baseline_slots = [slot for slot in schedule if slot.get("arm") == "baseline"]
    if len(candidate_slots) != 12 or len(baseline_slots) != 12 or set(arms) != {"baseline", "candidate"} or {slot.get("repeat") for slot in schedule} != {1, 2, 3}:
        raise ValueError("Committed A/B schedule provenance drifted")
    records = [verify_slot(root, slot) for slot in schedule]
    by_slot = {record["slot_id"]: record for record in records}
    candidate_all = all(by_slot[slot["slot_id"]]["correct"] for slot in candidate_slots)
    no_localized_or_inactive_regression = all(by_slot[slot["slot_id"]]["correct"] for slot in schedule if slot["expected_verdict"] in {"YES", "NOT_APPLICABLE"})
    if len(by_slot) != SLOTS or not candidate_all or not no_localized_or_inactive_regression:
        raise ValueError("Executed candidate gate did not pass exactly")
    result = {"format_version": 1, "successor_id": SUCCESSOR_ID, "source_commit": SOURCE_COMMIT, "preserved_original_settlement_sha256": sha256_file(root / "settlement.v1.json"), "status": "completed_provider_free_settlement", "completed_slots": SLOTS, "first_attempt_sol_high_slots": SLOTS, "candidate_all_four_cells_3_of_3": candidate_all, "no_localized_or_inactive_regression": no_localized_or_inactive_regression, "decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "promotion": "none"}
    public = {"format_version": 1, "successor_id": SUCCESSOR_ID, "status": result["status"], "completed_slots": SLOTS, "first_attempt_sol_high_slots": SLOTS, "decision": result["decision"], "promotion": "none"}
    write_once(ROOT / "result.v1.json", result)
    write_once(ROOT / "public-aggregate.v1.json", public)
    return result
