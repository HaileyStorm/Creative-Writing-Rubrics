"""Frozen resumable execution successor for the premise-scale ownership screen.

The public package deliberately contains only code and contracts.  Oracle labels
and slot identifiers are written solely to an external private execution root.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import runner
from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-premise-scale-ownership-v1"
STUDY_ID = "hbq-premise-scale-ownership-v1-execution-v1"
PREDECESSOR_COMMIT = "95a86b8353b4d27c85914d4258e4da33d080f9d7"
PREDECESSOR_TREE = "094d160babf3b6a33436431e834c37adac23b036"
LEAVES = (
    "artifact.support.premise_story_seed.extensibility",
    "op.ideation.premise_stress_test.scale",
)
VERDICTS = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})
BUNDLE_ID = "default.ideation"
REPETITIONS = 3
SLOTS = 72
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/all_modules.json",
    "registry/question_index.jsonl", "bundles/all_bundles.json", "src/hbqrs/runner.py",
    "src/hbqrs/cli.py",
)
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git binding lookup failed")
    return result.stdout.strip()


def _external_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        return root
    raise ValueError("private_root must be outside the CWR checkout")


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate frozen private artifact: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_summary(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("premise_scale_predecessor_execution", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load frozen predecessor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _predecessor_file_bindings() -> dict[str, str]:
    return {
        "external-real-text-holdout-commitment.json": "c8d2d1c00970f2bedf3357ad532f38233f456ca1",
        "public-synthetic-corpus.json": "aef71cff1a8d21df74f051af6fda75de6b259bcf",
        "study-contract.json": "9baa45b9057b5c7e0311104c6ee25a3d3f0288eb",
        "study.py": "4f234e0da9bc1c307327d7105ca42c0703f1080b",
    }


def validate_package() -> dict[str, Any]:
    value = contract()
    if value.get("study_id") != STUDY_ID or value.get("format_version") != 1 or value.get("status") != "frozen_execution_successor_unexecuted":
        raise ValueError("Execution contract identity drifted")
    predecessor = value.get("predecessor")
    if predecessor != {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": _predecessor_file_bindings()}:
        raise ValueError("Predecessor contract binding drifted")
    if value.get("execution") != {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "batch_attempts": 3, "maximum_provider_sends": 216, "one_leaf_per_call": True, "owner_attested_zero_incremental_charge_only": True, "paid_api_or_fallback_route": "forbidden"}:
        raise ValueError("Execution route binding drifted")
    if value.get("geometry") != {"artifacts": 12, "leaves": 2, "repeats": 3, "slots": SLOTS} or value.get("public_result_policy") != "aggregate_only_after_execution" or value.get("holdout") != "sealed_unread_and_inaccessible" or value.get("promotion") != "none":
        raise ValueError("Execution contract surface drifted")
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-premise-scale-ownership-v1") != PREDECESSOR_TREE:
        raise ValueError("Predecessor tree is unavailable")
    for path, blob in _predecessor_file_bindings().items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-premise-scale-ownership-v1/{path}") != blob:
            raise ValueError("Predecessor file binding drifted")
        if _git("hash-object", str(PREDECESSOR_ROOT / path)) != blob:
            raise ValueError("Current predecessor bytes differ from pinned committed source")
    predecessor_study = _predecessor()
    predecessor_study.verify_package()
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "holdout": "unread"}


def _runtime_bindings() -> dict[str, Any]:
    return {
        "runtime_head": _git("rev-parse", "HEAD"),
        "cwr_files": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS},
        "successor_files": {path: sha256_file(ROOT / path) for path in SUCCESSOR_FILES},
    }


def _case_sections(case: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    sections = case["sections"]
    if not isinstance(sections, Mapping) or not isinstance(sections.get("premise"), str):
        raise ValueError("Frozen public synthetic case is malformed")
    premise = sections["premise"]
    contexts = {str(name): str(text) for name, text in sections.items() if name != "premise"}
    if not premise.strip() or any(not value.strip() for value in contexts.values()):
        raise ValueError("Frozen public synthetic case text is malformed")
    return premise, contexts


def build_schedule() -> list[dict[str, Any]]:
    """Reconstruct the exact 72-slot ledger from the committed public predecessor."""
    validate_package()
    predecessor = _predecessor()
    corpus = predecessor.load_corpus()
    predecessor.verify_corpus(corpus)
    schedule: list[dict[str, Any]] = []
    for case_ordinal, case in enumerate(corpus["artifacts"], start=1):
        premise, contexts = _case_sections(case)
        artifact_id = f"synthetic-{case_ordinal:02d}"
        for leaf_id in LEAVES:
            expected = case["expected_verdicts"][leaf_id]
            for repeat in range(1, REPETITIONS + 1):
                ordinal = len(schedule) + 1
                artifact_sha = sha256_bytes(premise.encode("utf-8"))
                schedule.append({
                    "slot_id": f"psoexec-v1-{ordinal:03d}", "artifact_id": artifact_id,
                    "case_id": case["case_id"], "pair_id": case["pair_id"], "carrier": case["carrier"], "operation_active": case["operation_active"],
                    "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": expected,
                    "artifact_text": premise, "contexts": contexts, "artifact_sha256": artifact_sha,
                })
    if len(schedule) != SLOTS or len({row["slot_id"] for row in schedule}) != SLOTS:
        raise ValueError("Exact 72-slot schedule drifted")
    return schedule


def _private_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return dict(slot)


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "artifact_id", "leaf_id", "repeat", "artifact_sha256")}


def _context_paths(root: Path, slot: Mapping[str, Any]) -> list[Path]:
    return sorted((root / "contexts" / str(slot["artifact_id"])).glob("context-*.txt"))


def prepare(private_root: str | Path) -> dict[str, Any]:
    root = _external_root(private_root)
    schedule = build_schedule()
    for slot in schedule:
        _write_or_verify(root / "inputs" / f"{slot['artifact_id']}.txt", slot["artifact_text"].encode("utf-8"))
        for index, text in enumerate(slot["contexts"].values(), start=1):
            _write_or_verify(root / "contexts" / slot["artifact_id"] / f"context-{index:02d}.txt", text.encode("utf-8"))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    _write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    _write_or_verify(root / "private-schedule.json", canonical_json({"format_version": 1, "slots": [_private_slot(slot) for slot in schedule]}))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, resume: bool = False) -> list[str]:
    root = _external_root(private_root)
    command = [sys.executable, "-m", "hbqrs", "judge", str(root / "inputs" / f"{slot['artifact_id']}.txt"), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai", "--batch-size", "1", "--batch-attempts", "3", "--artifact-id", slot["artifact_id"], "--question-id", slot["leaf_id"], "--output-dir", str(root / "runs" / slot["slot_id"])]
    for path in _context_paths(root, slot):
        command.extend(["--context", str(path)])
    if resume:
        command.append("--resume")
    return command


def _render_command(slot: Mapping[str, Any], root: Path) -> list[str]:
    command = [sys.executable, "-m", "hbqrs", "render-judge", "--artifact", str(root / "inputs" / f"{slot['artifact_id']}.txt"), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", slot["artifact_id"], "--question-id", slot["leaf_id"]]
    for path in _context_paths(root, slot):
        command.extend(["--context", str(path)])
    return command


def _runtime_schedule(root: Path, schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = []
    for slot in schedule:
        prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if not prompt.is_file():
            raise ValueError(f"Missing rendered prompt: {slot['slot_id']}")
        result = dict(slot)
        result["rendered_prompt_sha256"] = sha256_file(prompt)
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": slot["leaf_id"], "prompt_sha256": result["rendered_prompt_sha256"], "rubric_sha256": sha256_file(REPOSITORY / "registry" / "all_modules.json")}
        result["condition"] = condition
        result["logical_sample_id"] = logical_sample_id(
            study_id=STUDY_ID, artifact_id=result["artifact_id"], artifact_sha256=result["artifact_sha256"],
            condition=condition, repetition=result["repeat"], rubric_revision="1.2.0",
        )
        resolved.append(result)
    return resolved


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    result = prepare(private_root)
    root = _external_root(private_root)
    for slot in build_schedule():
        command = [*command_for(slot, root, resume=(root / "runs" / slot["slot_id"] / "run.json").is_file()), "--dry-run"]
        finished = runner_call(command, text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(finished, "returncode", 1):
            raise RuntimeError(f"CWR dry run stopped at {slot['slot_id']}")
        finished = runner_call(_render_command(slot, root), text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(finished, "returncode", 1):
            raise RuntimeError(f"CWR prompt render stopped at {slot['slot_id']}")
        _write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", str(getattr(finished, "stdout", "")).encode("utf-8"))
    schedule = _runtime_schedule(root, build_schedule())
    prompt_hashes = {slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in schedule}
    preview = {"mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS, "first_command": command_for(schedule[0], root), "last_command": command_for(schedule[-1], root), "rendered_prompt_sha256s": prompt_hashes, "rendered_prompt_aggregate_sha256": sha256_bytes(canonical_json(prompt_hashes))}
    _write_summary(root / "runtime-schedule.json", {"format_version": 1, "slots": schedule, "rendered_prompt_aggregate_sha256": preview["rendered_prompt_aggregate_sha256"]})
    _write_summary(root / "dry-run.json", preview)
    return {**result, **preview}


def _validate_runtime_bindings(root: Path) -> list[dict[str, Any]]:
    manifest = _load_json(root / "study-manifest.json")
    if manifest.get("runtime_bindings") != _runtime_bindings():
        raise ValueError("CWR runtime/schema/runner binding drifted; prepare again")
    stored = _load_json(root / "runtime-schedule.json")
    expected = _runtime_schedule(root, build_schedule())
    if stored.get("slots") != expected or stored.get("rendered_prompt_aggregate_sha256") != sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected})):
        raise ValueError("Prepared prompt schedule drifted; dry run again")
    return expected


def _fresh_execute_preflight(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    """A dry-run creates manifests; a fresh remote pass may continue only those empty runs."""
    for slot in schedule:
        run_dir = root / "runs" / str(slot["slot_id"])
        if not (run_dir / "run.json").is_file():
            raise ValueError("Fresh execute requires a complete dry-run manifest for every slot")
        responses = run_dir / "responses"
        attempted = list(responses.rglob("*") if responses.is_dir() else ())
        if any(path.is_file() for path in attempted):
            raise ValueError("Fresh execute rejects a slot with prior provider attempts; use --resume")


def execute(private_root: str | Path, *, resume: bool = False, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit allow-remote and zero-incremental-charge acknowledgement")
    root = _external_root(private_root)
    schedule = _validate_runtime_bindings(root)
    if not resume:
        _fresh_execute_preflight(root, schedule)
    for slot in schedule:
        # CWR dry-run already materialized the exact configuration manifest, so both
        # modes continue that manifest; only fresh execute forbids prior attempts.
        command = [*command_for(slot, root, resume=True), "--allow-remote"]
        finished = runner_call(command, text=True, encoding="utf-8", capture_output=True, check=False)
        if getattr(finished, "returncode", 1):
            raise RuntimeError(f"Execution stopped at {slot['slot_id']}")
    return {"mode": "resume" if resume else "execute", "inspected_slots": SLOTS, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "billing": "owner_attested_subscription_zero_incremental_charge"}


def _case_for(slot: Mapping[str, Any]) -> dict[str, Any]:
    predecessor = _predecessor()
    return next(item for item in predecessor.load_corpus()["artifacts"] if item["case_id"] == slot["case_id"])


def _input_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "name": path.name, "bytes": len(data), "sha256": sha256_bytes(data)}


def _validate_production_evidence(evidence: Any, *, artifact_text: str, context_texts: Sequence[str], question_id: str) -> None:
    if not isinstance(evidence, list):
        raise ValueError("Production normalized evidence is unavailable")
    runner._validate_typed_checkpoint_evidence(evidence, question_id=question_id)
    runner._validate_exact_quotes(evidence, artifact_text=artifact_text, context_texts=context_texts, question_id=question_id)


def _verify_checkpoint_prompt(run_dir: Path, prompt_path: Path) -> dict[str, str]:
    checkpoint = run_dir / "responses" / "batch-0001.prompt.txt.gz"
    try:
        checkpoint_bytes = gzip.decompress(checkpoint.read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt is unavailable or malformed") from exc
    rendered = prompt_path.read_bytes()
    if checkpoint_bytes != rendered:
        raise ValueError("Checkpoint prompt content differs from frozen rendered prompt")
    return {"rendered_prompt_sha256": sha256_bytes(rendered), "checkpoint_prompt_sha256": sha256_bytes(checkpoint_bytes)}


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    run_dir = root / "runs" / slot["slot_id"]
    manifest = _load_json(run_dir / "run.json")
    config = manifest.get("configuration")
    expected = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "artifact_id": slot["artifact_id"], "bundle_id": BUNDLE_ID, "question_ids": [slot["leaf_id"]]}
    if manifest.get("format_version") != 4 or not isinstance(config, Mapping) or any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Production singleton run binding drifted")
    prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
    if sha256_file(prompt) != slot["rendered_prompt_sha256"]:
        raise ValueError("Run prompt hash differs from prepared schedule")
    artifact_path = root / "inputs" / f"{slot['artifact_id']}.txt"
    context_paths = _context_paths(root, slot)
    context_texts = [path.read_text(encoding="utf-8") for path in context_paths]
    if config.get("artifact") != _input_record(artifact_path) or config.get("contexts") != [_input_record(path) for path in context_paths]:
        raise ValueError("Production artifact or ordered context binding drifted")
    expected_prompt_hashes = [sha256_file(REPOSITORY / "prompts" / "judge" / name) for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")]
    actual_prompt_hashes = [item.get("sha256") for item in config.get("prompts", [])] if isinstance(config.get("prompts"), list) else []
    if actual_prompt_hashes != expected_prompt_hashes or config.get("response_schema", {}).get("sha256") != sha256_file(REPOSITORY / "schema" / "hbq_judge_response.schema.json"):
        raise ValueError("Strict prompt or response schema binding drifted")
    if manifest.get("config_sha256") != runner._sha256_bytes(runner._json_bytes(config)):
        raise ValueError("Run manifest configuration hash drifted")
    prompt_commitment = _verify_checkpoint_prompt(run_dir, prompt)
    verdicts, checkpoints, chain = runner._load_checkpoints(run_dir, artifact_text=slot["artifact_text"], context_texts=context_texts, batch_attempts=3, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoints != 1 or len(verdicts) != 1 or verdicts[0].get("question_id") != slot["leaf_id"]:
        raise ValueError("Run does not contain exactly one accepted selected leaf")
    _validate_production_evidence(verdicts[0].get("evidence"), artifact_text=slot["artifact_text"], context_texts=context_texts, question_id=slot["leaf_id"])
    if verdicts[0].get("run_id") != manifest.get("run_id") or not isinstance(verdicts[0].get("run_id"), str):
        raise ValueError("Checkpoint run identity drifted")
    checkpoint = _load_json(run_dir / "responses" / "batch-0001.json")
    reported = checkpoint.get("provider", {}).get("reported", {})
    if not isinstance(reported, Mapping) or {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider/model/reasoning report drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session:
        raise ValueError("Provider session identity missing")
    if checkpoint.get("accepted_attempt") != len(runner._rejected_records(run_dir, 1)) + 1:
        raise ValueError("Retry did not replace one logical slot cumulatively")
    return {"slot_id": slot["slot_id"], "verdict": verdicts[0].get("verdict"), "expected": slot["expected_verdict"], "correct": verdicts[0].get("verdict") == slot["expected_verdict"], "evidence": verdicts[0]["evidence"], "run_id": verdicts[0].get("run_id"), "session_id_sha256": sha256_bytes(session.encode("utf-8")), "checkpoint_chain_head_sha256": chain, "prompt_commitment": prompt_commitment}


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    value = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_slots": completed, "planned_slots": SLOTS, "failures": failures}
    _write_summary(root / "settlement.json", value)
    _write_summary(root / "public-aggregate.json", {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS})
    return value


def _overlap(records: Sequence[Mapping[str, Any]], schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    slot_map = {slot["slot_id"]: slot for slot in schedule}
    grouped: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        slot = slot_map[record["slot_id"]]
        grouped[(slot["case_id"], slot["repeat"])].append(record)
    exact_quote_overlap = 0
    same_reference_overlap = 0
    section_span_overlap = 0
    comparable = 0
    for rows in grouped.values():
        if len(rows) != 2:
            continue
        comparable += 1
        references = [{str(item["reference"]) for item in row["evidence"] if isinstance(item.get("reference"), str)} for row in rows]
        if references[0] & references[1]:
            same_reference_overlap += 1
        slot = slot_map[rows[0]["slot_id"]]
        sections = {"artifact": str(slot["artifact_text"])}
        sections.update({f"context-{index:02d}": text for index, text in enumerate(slot["contexts"].values(), start=1)})
        spans: list[list[tuple[str, int, int, str]]] = []
        for row in rows:
            row_spans: list[tuple[str, int, int, str]] = []
            for item in row["evidence"]:
                quote = item.get("exact_quote")
                if not isinstance(quote, str):
                    continue
                for section, text in sections.items():
                    start = text.find(quote)
                    while start >= 0:
                        row_spans.append((section, start, start + len(quote), quote))
                        start = text.find(quote, start + 1)
            spans.append(row_spans)
        if {quote for _, _, _, quote in spans[0]} & {quote for _, _, _, quote in spans[1]}:
            exact_quote_overlap += 1
        if any(section == other_section and max(start, other_start) < min(end, other_end) for section, start, end, _ in spans[0] for other_section, other_start, other_end, _ in spans[1]):
            section_span_overlap += 1
    return {"joint_leaf_repetitions": comparable, "same_reference_overlap": same_reference_overlap, "section_span_overlap": section_span_overlap, "exact_quote_overlap": exact_quote_overlap}


def _clarification_eligibility(records: Sequence[Mapping[str, Any]], schedule: Sequence[Mapping[str, Any]], overlap: Mapping[str, Any]) -> dict[str, Any]:
    slot_map = {slot["slot_id"]: slot for slot in schedule}
    bad = [row for row in records if not row["correct"] and row["expected"] in {"YES", "NO", "CANNOT_ASSESS"}]
    repeated: dict[tuple[str, str, str], dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for row in bad:
        slot = slot_map[row["slot_id"]]
        repeated[(slot["leaf_id"], str(row["expected"]), str(row["verdict"]))][slot["pair_id"]][slot["case_id"]] += 1
    duplicate_signal = False
    # A same-verdict jointly active pair with shared exact evidence is a duplication/route signal, not a prompt omission.
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        groups[(slot_map[row["slot_id"]]["case_id"], slot_map[row["slot_id"]]["repeat"])].append(row)
    for rows in groups.values():
        slot = slot_map[rows[0]["slot_id"]] if rows else None
        if len(rows) == 2 and slot and slot["operation_active"] and all(row["expected"] in {"YES", "NO"} for row in rows) and rows[0]["verdict"] == rows[1]["verdict"]:
            sections = {"artifact": str(slot["artifact_text"])}
            sections.update({f"context-{index:02d}": text for index, text in enumerate(slot["contexts"].values(), start=1)})
            located: list[list[tuple[str, int, int]]] = []
            for row in rows:
                row_spans: list[tuple[str, int, int]] = []
                for item in row["evidence"]:
                    quote = item.get("exact_quote")
                    if isinstance(quote, str):
                        for section, text in sections.items():
                            start = text.find(quote)
                            while start >= 0:
                                row_spans.append((section, start, start + len(quote)))
                                start = text.find(quote, start + 1)
                located.append(row_spans)
            duplicate_signal = duplicate_signal or any(section == other_section and max(start, other_start) < min(end, other_end) for section, start, end in located[0] for other_section, other_start, other_end in located[1])
    qualifying = {
        signature: sorted(pair for pair, cases in pairs.items() if any(count >= 2 for count in cases.values()))
        for signature, pairs in repeated.items()
    }
    eligible = len(records) == SLOTS and any(len(pairs) >= 2 for pairs in qualifying.values()) and not duplicate_signal
    return {"eligible": eligible, "requires_independent_sol_attribution": "one_missing_rendering_rule", "same_verdict_same_premise_duplication_signal": duplicate_signal, "same_repeated_error_pair_types": {"|".join(signature): pairs for signature, pairs in qualifying.items()}, "cross_leaf_overlap": dict(overlap)}


def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] = _verify_slot) -> dict[str, Any]:
    root = _external_root(private_root)
    try:
        schedule = _validate_runtime_bindings(root)
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "schedule", "reason": str(exc)}])
    records, failures = [], []
    for slot in schedule:
        try:
            record = verifier(root, slot)
            if record.get("slot_id") != slot["slot_id"] or record.get("verdict") not in VERDICTS:
                raise ValueError("Verifier slot identity or four-state verdict malformed")
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": slot["slot_id"], "reason": str(exc)})
    if failures or len(records) != SLOTS or len({row["slot_id"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), failures or [{"slot_id": "identity", "reason": "Duplicate logical slot"}])
    if len({row["session_id_sha256"] for row in records}) != SLOTS or len({row["checkpoint_chain_head_sha256"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Session or checkpoint identity repeated"}])
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    state_counts: dict[str, Counter[str]] = {leaf: Counter() for leaf in LEAVES}
    for row in records:
        slot = next(item for item in schedule if item["slot_id"] == row["slot_id"])
        cells[(slot["case_id"], slot["leaf_id"])].append(bool(row["correct"]))
        state_counts[slot["leaf_id"]][row["verdict"]] += 1
    cell_states = {(slot["case_id"], slot["leaf_id"]): slot["expected_verdict"] for slot in schedule}
    per_cell = {
        f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": cell_states[cell_key]}
        for index, (cell_key, values) in enumerate(cells.items(), start=1)
    }
    overlap = _overlap(records, schedule)
    def accuracy(states: set[str]) -> dict[str, int]:
        selected = [row for row in records if row["expected"] in states]
        return {"correct": sum(bool(row["correct"]) for row in selected), "denominator": len(selected)}
    scored_pass = all(value["passed"] for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE")
    decision = "PASS_NO_CHANGE" if scored_pass else "DIAGNOSTIC_FAIL"
    metrics = {"applicable_yes_no": accuracy({"YES", "NO"}), "cannot_assess": accuracy({"CANNOT_ASSESS"}), "not_applicable_unscored": accuracy({"NOT_APPLICABLE"}), "all_cell_diagnostic": accuracy(set(VERDICTS))}
    opposed = [row for row in records if (slot := next(item for item in schedule if item["slot_id"] == row["slot_id"]))["pair_id"] == "mismatched-form" and slot["operation_active"] and row["expected"] in {"YES", "NO"}]
    opposed_accuracy = {"correct": sum(bool(row["correct"]) for row in opposed), "denominator": len(opposed)}
    canonical_counts = {leaf: {state: state_counts[leaf][state] for state in sorted(VERDICTS)} for leaf in LEAVES}
    scored_cell_values = [value for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE"]
    not_applicable_cell_values = [value for value in per_cell.values() if value["expected_state"] == "NOT_APPLICABLE"]
    settlement = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "per_cell_three_of_three": per_cell, "canonical_four_state_counts": canonical_counts, "accuracy": metrics, "jointly_active_opposed_target_accuracy": opposed_accuracy, "cross_leaf_evidence_section_span_overlap": overlap, "clarification": _clarification_eligibility(records, schedule, overlap), "promotion": "none", "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "scored_cells": {"passed": sum(value["passed"] for value in scored_cell_values), "total": len(scored_cell_values)}, "not_applicable_diagnostic_cells": {"matched": sum(value["passed"] for value in not_applicable_cell_values), "total": len(not_applicable_cell_values)}, "canonical_four_state_counts": canonical_counts, "accuracy": metrics, "promotion": "none"}
    _write_summary(root / "settlement.json", settlement)
    _write_summary(root / "public-aggregate.json", public)
    return settlement


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    for name in ("prepare", "settle"):
        child = commands.add_parser(name)
        child.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        result = validate_package()
    elif args.command == "prepare":
        result = prepare(args.private_root)
    else:
        result = settle(args.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
