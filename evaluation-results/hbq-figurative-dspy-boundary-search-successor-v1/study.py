from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from contextlib import redirect_stderr, redirect_stdout

from hbqrs import runner
from hbqrs.cli import main as hbq_cli_main

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-dspy-boundary-search-successor-v1"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
TARGET = "penalty.purple_prose.metaphor"
PRIVATE_DIRECTORY = "figurative-dspy-boundary-search-v1-private"
EXPECTED_LEDGER = "expected-ledger.json"
STRICT_EVIDENCE = "Include at least one exact_quote copied verbatim from the supplied artifact. Summary-only evidence is invalid."
REVIEW_RECORD = "independent-sol-review.v1.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract() -> dict[str, Any]:
    return _json(ROOT / "study-contract.json")


def corpus() -> list[dict[str, str]]:
    return _json(ROOT / "public-synthetic-corpus.json")["cases"]


def candidates() -> list[dict[str, str]]:
    return _json(ROOT / "candidate-appendices.json")["candidates"]


def _require_exact_head() -> None:
    observed = subprocess.run(
        ["git", "-C", str(ROOT.parents[1]), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if observed != SOURCE_HEAD:
        raise ValueError(f"exact source HEAD required: {SOURCE_HEAD}, found {observed}")


def validate_package() -> dict[str, Any]:
    study = contract()
    if study["study_id"] != STUDY_ID or study["source_anchor"]["commit"] != SOURCE_HEAD:
        raise ValueError("study identity or source anchor drift")
    if study["target"]["leaf_id"] != TARGET or study["holds"]["promotion"] != "none":
        raise ValueError("target or promotion invariant drift")
    if study["candidate_search"]["candidate_appendices_exact"] != 4:
        raise ValueError("exactly four static candidate appendices required")
    candidate_rows = candidates()
    if len(candidate_rows) != 4 or len({row["candidate_id"] for row in candidate_rows}) != 4:
        raise ValueError("candidate identity drift")
    forbidden = ("generate", "dspy", "pilot", "gray blood")
    for row in candidate_rows:
        if not row["text"].strip() or "familiarity/defaultness" not in row["text"]:
            raise ValueError("candidate ownership boundary missing")
        if row["candidate_id"] != "appendix-a" and any(word in row["text"].casefold() for word in forbidden):
            raise ValueError("candidate text contains forbidden generation or lineage token")
    rows = corpus()
    if len(rows) != 18 or len({row["case_id"] for row in rows}) != 18:
        raise ValueError("corpus cardinality or opaque-ID invariant failed")
    if any(not row["case_id"].startswith(("tr-", "dv-")) for row in rows):
        raise ValueError("provider-facing IDs must be opaque split IDs")
    train = [row for row in rows if row["split"] == "train"]
    dev = [row for row in rows if row["split"] == "dev"]
    if len(train) != 12 or len(dev) != 6:
        raise ValueError("train/dev geometry drift")
    if {row["boundary_type"] for row in train} != {"dimension", "role", "contrast", "sequence", "double_meaning", "relation"}:
        raise ValueError("train boundary types drift")
    if {row["boundary_type"] for row in dev} != {"dimension", "role", "contrast", "sequence", "double_meaning", "relation"}:
        raise ValueError("dev boundary types drift")
    return {"study_id": STUDY_ID, "candidates": 4, "train_slots": 48, "selected_dev_slots": 24, "materialized_dev_slots": 48, "provider_calls": 0, "promotion": "none"}


def _load_private_ledger(private_root: Path) -> dict[str, Any]:
    ledger = _json(private_root / EXPECTED_LEDGER)
    expected_ids = {row["case_id"] for row in corpus()}
    if set(ledger["labels"]) != expected_ids:
        raise ValueError("private ledger must contain exactly the frozen opaque case IDs")
    if any(label not in {"YES", "NO"} for label in ledger["labels"].values()):
        raise ValueError("private labels must be YES or NO")
    if "candidate" in json.dumps(ledger).casefold() or "appendix" in json.dumps(ledger).casefold():
        raise ValueError("private expected ledger cannot encode candidate selection")
    return ledger


def build_train_schedule() -> list[dict[str, str]]:
    return [
        {"slot_id": f"train-{candidate['candidate_id']}-{case['case_id']}", "stage": "train", "candidate_id": candidate["candidate_id"], "case_id": case["case_id"], "leaf_id": TARGET}
        for candidate in candidates() for case in corpus() if case["split"] == "train"
    ]


def build_reserved_dev_schedule() -> list[dict[str, str]]:
    return [
        {"slot_id": f"dev-rank-{rank}-{case['case_id']}-repeat-{repeat}", "stage": "dev", "candidate_rank": str(rank), "case_id": case["case_id"], "repeat": str(repeat), "leaf_id": TARGET}
        for rank in (1, 2) for case in corpus() if case["split"] == "dev" for repeat in (1, 2)
    ]


def build_all_dev_schedule() -> list[dict[str, str]]:
    return [
        {"slot_id": f"dev-{candidate['candidate_id']}-{case['case_id']}-repeat-{repeat}", "stage": "dev", "candidate_id": candidate["candidate_id"], "case_id": case["case_id"], "repeat": str(repeat), "leaf_id": TARGET}
        for candidate in candidates() for case in corpus() if case["split"] == "dev" for repeat in (1, 2)
    ]


def ownership_preserved(candidate: dict[str, str]) -> bool:
    text = candidate["text"].casefold()
    return "familiarity/defaultness" in text and ("density" in text or "figurative load" in text or "figurative quantity" in text)


def rank_train_records(records: list[dict[str, str]], private_root: Path) -> list[dict[str, Any]]:
    ledger = _load_private_ledger(private_root)["labels"]
    slots = build_train_schedule()
    expected_slots = {slot["slot_id"] for slot in slots}
    received = {record.get("slot_id") for record in records}
    if received != expected_slots or len(records) != len(expected_slots):
        raise ValueError("train records must contain every frozen slot exactly once")
    cases = {case["case_id"]: case for case in corpus()}
    candidate_rows = {candidate["candidate_id"]: candidate for candidate in candidates()}
    scored = []
    for candidate_id, candidate in candidate_rows.items():
        candidate_records = [record for record in records if record["candidate_id"] == candidate_id]
        if any(record.get("verdict") not in {"YES", "NO"} for record in candidate_records):
            raise ValueError("only strict binary train verdicts can be ranked")
        by_type = {boundary: 0 for boundary in {case["boundary_type"] for case in cases.values() if case["split"] == "train"}}
        exact = 0
        for record in candidate_records:
            correct = record["verdict"] == ledger[record["case_id"]]
            exact += int(correct)
            by_type[cases[record["case_id"]]["boundary_type"]] += int(correct)
        scored.append({
            "candidate_id": candidate_id,
            "exact_label_correct": exact,
            "boundary_type_stability": min(by_type.values()),
            "ownership_preserved": ownership_preserved(candidate),
        })
    eligible = [row for row in scored if row["ownership_preserved"]]
    if len(eligible) < 2:
        raise ValueError("two ownership-preserving candidates are required")
    return sorted(eligible, key=lambda row: (-row["exact_label_correct"], -row["boundary_type_stability"], row["candidate_id"]))


def build_selected_dev_schedule(selected_candidate_ids: list[str]) -> list[dict[str, str]]:
    if len(selected_candidate_ids) != 2 or len(set(selected_candidate_ids)) != 2:
        raise ValueError("exactly two distinct ranked candidates are required for DEV")
    candidate_ids = {candidate["candidate_id"] for candidate in candidates()}
    if set(selected_candidate_ids) - candidate_ids:
        raise ValueError("DEV candidate is outside frozen appendix set")
    return [
        {"slot_id": f"dev-{candidate_id}-{case['case_id']}-repeat-{repeat}", "stage": "dev", "candidate_id": candidate_id, "case_id": case["case_id"], "repeat": str(repeat), "leaf_id": TARGET}
        for candidate_id in selected_candidate_ids for case in corpus() if case["split"] == "dev" for repeat in (1, 2)
    ]


def render_train_prompt(slot: dict[str, str]) -> str:
    case = next(item for item in corpus() if item["case_id"] == slot["case_id"])
    candidate = next(item for item in candidates() if item["candidate_id"] == slot["candidate_id"])
    return "\n".join([
        "Evaluate only the supplied public synthetic artifact against the selected production leaf.",
        f"Leaf: {TARGET}",
        "Artifact:", case["text"], "", "Experimental appendix:", candidate["text"], "",
        "Use only the supplied artifact.", STRICT_EVIDENCE,
        "Return one verdict: YES or NO, with grounded evidence.",
    ])


def _execution_root(private_root: Path) -> Path:
    return private_root / PRIVATE_DIRECTORY


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"frozen file drift: {path}")
        return
    path.write_bytes(content)


def _target_bundle() -> list[dict[str, Any]]:
    leaf = next(json.loads(line) for line in (ROOT.parents[1] / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(line).get("id") == TARGET)
    return [{
        "standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": STUDY_ID, "version": 1,
        "title": "Figurative static boundary-search singleton diagnostic", "module_ids": [leaf["module_id"]],
        "task_contract_domain_id": "figurative-boundary-1",
        "domains": [{"domain_id": "figurative-boundary-1", "title": TARGET, "points": 1.0,
                     "components": [{"module_id": leaf["module_id"], "weight": 1.0, "include_question_ids": [TARGET]}],
                     "score_mode": "weighted_binary_mean"}],
        "penalty_modules": [],
        "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
    }]


def _task(slot: dict[str, str]) -> dict[str, Any]:
    case = next(item for item in corpus() if item["case_id"] == slot["case_id"])
    candidate = next(item for item in candidates() if item["candidate_id"] == slot["candidate_id"])
    return {"contract_version": 1, "contract_id": f"{STUDY_ID}-{slot['slot_id']}", "artifact_id": slot["slot_id"],
            "context": {"artifact_kind": "prose.short_story", "declared_scope": "complete supplied passage", "completion_status": "complete",
                        "background": ["Public synthetic figurative boundary-search artifact."],
                        "constraints": ["Use only the supplied artifact.", STRICT_EVIDENCE, candidate["text"]],
                        "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _override(slot: dict[str, str], task: dict[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["slot_id"], "bundle_id": STUDY_ID,
            "task_contract_sha256": hashlib.sha256(_canonical_bytes(task)).hexdigest(), "contract_id": task["contract_id"],
            "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"],
            "compatibility_mode": "reviewed_override", "decision_id": "figurative-dspy-boundary-search-scope-v1",
            "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for a public synthetic figurative boundary-search diagnostic."}


def prepare_execution(private_root: Path, slots: list[dict[str, str]]) -> Path:
    root = _execution_root(private_root)
    _write_once(root / "catalog" / "registry.json", (ROOT.parents[1] / "registry" / "all_modules.json").read_bytes())
    _write_once(root / "catalog" / "bundles.json", _canonical_bytes(_target_bundle()))
    for slot in slots:
        case = next(item for item in corpus() if item["case_id"] == slot["case_id"])
        task = _task(slot)
        _write_once(root / "inputs" / f"{slot['slot_id']}.txt", case["text"].encode("utf-8"))
        _write_once(root / "contracts" / f"{slot['slot_id']}.json", _canonical_bytes(task))
        _write_once(root / "overrides" / f"{slot['slot_id']}.json", _canonical_bytes(_override(slot, task)))
    return root


def command_for(slot: dict[str, str], private_root: Path, *, output_root: str = "runs", allow_remote: bool = False) -> list[str]:
    root = _execution_root(private_root)
    command = [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "registry.json"), "--bundles", str(root / "catalog" / "bundles.json"),
               "judge", str(root / "inputs" / f"{slot['slot_id']}.txt"), "--bundle", STUDY_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai",
               "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", "terminal_sidecar_v1", "--artifact-id", slot["slot_id"], "--question-id", TARGET,
               "--task-contract", str(root / "contracts" / f"{slot['slot_id']}.json"), "--scope-compatibility-override", str(root / "overrides" / f"{slot['slot_id']}.json"), "--output-dir", str(root / output_root / slot["slot_id"])]
    if allow_remote:
        command.append("--allow-remote")
    return command


def render_command(slot: dict[str, str], private_root: Path) -> list[str]:
    root = _execution_root(private_root)
    return [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "registry.json"), "--bundles", str(root / "catalog" / "bundles.json"),
            "render-judge", "--artifact", str(root / "inputs" / f"{slot['slot_id']}.txt"), "--bundle", STUDY_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai",
            "--artifact-id", slot["slot_id"], "--question-id", TARGET, "--task-contract", str(root / "contracts" / f"{slot['slot_id']}.json"),
            "--scope-compatibility-override", str(root / "overrides" / f"{slot['slot_id']}.json"), "--output", str(root / "rendered-prompts" / f"{slot['slot_id']}.txt")]


def _canonical_prompt_bytes(raw: bytes) -> bytes:
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _local_cli_runner(command: list[str], **_kwargs: Any) -> SimpleNamespace:
    if command[:3] != [sys.executable, "-m", "hbqrs"]:
        raise ValueError("provider-free renderer received an unexpected command prefix")
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        returncode = int(hbq_cli_main(command[3:]))
    return SimpleNamespace(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def _hash_map(paths: list[Path], root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in sorted(paths)}


def _freeze_bindings(private_root: Path, slots: list[dict[str, str]]) -> dict[str, Any]:
    root = _execution_root(private_root)
    material_paths = [root / "catalog" / "registry.json", root / "catalog" / "bundles.json"]
    for slot in slots:
        material_paths.extend([root / "inputs" / f"{slot['slot_id']}.txt", root / "contracts" / f"{slot['slot_id']}.json", root / "overrides" / f"{slot['slot_id']}.json"])
    prompt_paths = [root / "rendered-prompts" / f"{slot['slot_id']}.txt" for slot in slots]
    materials = _hash_map(material_paths, root)
    prompts = _hash_map(prompt_paths, root)
    commands = {slot["slot_id"]: command_for(slot, private_root, allow_remote=True) for slot in slots}
    return {
        "study_contract_sha256": _sha256(ROOT / "study-contract.json"), "study_code_sha256": _sha256(ROOT / "study.py"), "run_code_sha256": _sha256(ROOT / "run.py"),
        "candidate_appendices_sha256": _sha256(ROOT / "candidate-appendices.json"), "public_corpus_sha256": _sha256(ROOT / "public-synthetic-corpus.json"),
        "private_expected_ledger_sha256": _sha256(private_root / EXPECTED_LEDGER), "schedule_sha256": hashlib.sha256(_canonical_bytes(slots)).hexdigest(),
        "provider_materials_sha256": hashlib.sha256(_canonical_bytes(materials)).hexdigest(), "provider_material_hashes": materials,
        "rendered_prompts_sha256": hashlib.sha256(_canonical_bytes(prompts)).hexdigest(), "rendered_prompt_hashes": prompts,
        "provider_commands_sha256": hashlib.sha256(_canonical_bytes(commands)).hexdigest(), "provider_commands": commands,
    }


def dry_run(private_root: Path, *, runner_call: Any = _local_cli_runner) -> dict[str, Any]:
    validate_package()
    _require_exact_head()
    _load_private_ledger(private_root)
    private = _execution_root(private_root)
    train = build_train_schedule()
    all_dev = build_all_dev_schedule()
    slots = [*train, *all_dev]
    prepare_execution(private_root, slots)
    def materialize(slot: dict[str, str]) -> None:
        dry = runner_call([*command_for(slot, private_root, output_root="dry-runs"), "--dry-run"], check=False, text=True, encoding="utf-8", capture_output=True)
        if getattr(dry, "returncode", 1):
            raise RuntimeError(f"provider-free runtime dry-run failed for {slot['slot_id']}: {getattr(dry, 'stderr', '')}")
        prompt = private / "rendered-prompts" / f"{slot['slot_id']}.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        rendered = runner_call(render_command(slot, private_root), check=False, text=True, encoding="utf-8", capture_output=True)
        if getattr(rendered, "returncode", 1):
            raise RuntimeError(f"provider-free prompt rendering failed for {slot['slot_id']}: {getattr(rendered, 'stderr', '')}")
        canonical = _canonical_prompt_bytes(prompt.read_bytes())
        if prompt.read_bytes() != canonical:
            prompt.write_bytes(canonical)
    for slot in slots:
        materialize(slot)
    bindings = _freeze_bindings(private_root, slots)
    manifest = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "source_head": SOURCE_HEAD,
        "provider_calls": 0,
        "train_slots": len(train),
        "selected_dev_slots": 24,
        "materialized_potential_dev_slots": len(all_dev),
        "materialized_provider_visible_slots": len(slots),
        "maximum_provider_sends": 72,
        "stage_order": "all_train_before_any_dev",
        "review_bindings": bindings,
        "train_schedule": train,
        "all_potential_dev_schedule": all_dev,
        "selection": "top_two_by_exact_label_then_stability_then_ownership; independent_sol_review_required",
        "promotion": "none",
    }
    (private / "frozen-dry-run.v1.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"provider_calls": 0, "train_prompts": len(train), "materialized_dev_prompts": len(all_dev), "materialized_provider_visible_slots": len(slots), "manifest_sha256": _sha256(private / "frozen-dry-run.v1.json")}


def _require_review(private_root: Path, dry: dict[str, Any]) -> dict[str, Any]:
    review_path = private_root / REVIEW_RECORD
    review = _json(review_path)
    required = {"study_id": STUDY_ID, "source_head": SOURCE_HEAD, "decision": "GO"}
    if any(review.get(key) != value for key, value in required.items()):
        raise ValueError("independent Sol GO review is missing or does not bind this frozen study")
    expected_bindings = {"dry_manifest_sha256": _sha256(_execution_root(private_root) / "frozen-dry-run.v1.json"), **dry["review_bindings"]}
    if review.get("bindings") != expected_bindings:
        raise ValueError("independent Sol GO record does not bind the exact dry manifest and provider-visible material")
    return review


def _verify_live_slot(private_root: Path, slot: dict[str, str]) -> dict[str, str]:
    root = _execution_root(private_root)
    run = root / "runs" / slot["slot_id"]
    manifest = _json(run / "run.json")
    config = manifest.get("configuration", {})
    required = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1,
                "retry_policy": {"batch_attempts": 1}, "retry_semantics": "cumulative_batch_attempts_v1", "attempt_lifecycle_policy": "terminal_sidecar_v1",
                "artifact_id": slot["slot_id"], "bundle_id": STUDY_ID, "question_ids": [TARGET]}
    if manifest.get("format_version") != 5 or any(config.get(key) != value for key, value in required.items()):
        raise ValueError("live run configuration drifted from Sol/high singleton policy")
    artifact = (root / "inputs" / f"{slot['slot_id']}.txt").read_text(encoding="utf-8")
    verdicts, checkpoint_count, _chain = runner._load_checkpoints(run, artifact_text=artifact, context_texts=[], batch_attempts=1, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    checkpoint = _json(run / "responses" / "batch-0001.json")
    if checkpoint_count != 1 or len(verdicts) != 1 or checkpoint.get("normalization_audit") != []:
        raise ValueError("live slot has retry, non-singleton, or normalization evidence")
    if checkpoint.get("accepted_attempt") != 1 or runner._rejected_records(run, 1):
        raise ValueError("live slot violates one physical attempt with no retry")
    reported = checkpoint.get("provider", {}).get("reported", {})
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("live slot lacks reported Sol/high identity")
    verdict = verdicts[0]
    if verdict.get("question_id") != TARGET or verdict.get("verdict") not in {"YES", "NO"}:
        raise ValueError("live slot does not contain one strict target verdict")
    evidence = verdict.get("evidence")
    runner._validate_typed_checkpoint_evidence(evidence, question_id=TARGET)
    runner._validate_exact_quotes(evidence, artifact_text=artifact, context_texts=[], question_id=TARGET)
    return {"slot_id": slot["slot_id"], "candidate_id": slot["candidate_id"], "case_id": slot["case_id"], "verdict": verdict["verdict"]}


def execute(private_root: Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Any = subprocess.run) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("execution requires both remote and zero-incremental-charge acknowledgements")
    validate_package()
    _require_exact_head()
    root = _execution_root(private_root)
    dry = _json(root / "frozen-dry-run.v1.json")
    if dry.get("provider_calls") != 0 or dry.get("source_head") != SOURCE_HEAD:
        raise ValueError("execution requires the matching zero-call dry freeze")
    _require_review(private_root, dry)
    materialized = [*build_train_schedule(), *build_all_dev_schedule()]
    prepare_execution(private_root, materialized)
    if _freeze_bindings(private_root, materialized) != dry.get("review_bindings"):
        raise ValueError("provider-visible material drifted after the zero-call dry freeze")
    claim = root / "execution-claim.v1.json"
    if claim.exists():
        raise ValueError("execution is one-shot; existing claim forbids retry or resume")
    train = build_train_schedule()
    _write_once(claim, _canonical_bytes({"format_version": 1, "study_id": STUDY_ID, "source_head": SOURCE_HEAD, "planned_train_slots": len(train), "maximum_provider_sends": 72, "retry_or_resume": "forbidden"}))
    train_records = []
    for slot in train:
        runner_call(command_for(slot, private_root, allow_remote=True), check=True, text=True, encoding="utf-8", capture_output=True)
        train_records.append(_verify_live_slot(private_root, slot))
    ranked = rank_train_records(train_records, private_root)
    selected = [row["candidate_id"] for row in ranked[:2]]
    dev = build_selected_dev_schedule(selected)
    prepare_execution(private_root, dev)
    dev_records = []
    for slot in dev:
        runner_call(command_for(slot, private_root, allow_remote=True), check=True, text=True, encoding="utf-8", capture_output=True)
        dev_records.append(_verify_live_slot(private_root, slot))
    result = {"study_id": STUDY_ID, "train_slots": len(train), "dev_slots": len(dev), "provider_sends": len(train) + len(dev),
              "ranked_train": ranked, "selected_candidates": selected, "train_records": train_records, "dev_records": dev_records,
              "promotion": "none", "next_gate": "independent_sol_review_of_dev_then_fresh_disjoint_confirmation"}
    _write_once(root / "sealed-execution-result.v1.json", _canonical_bytes(result))
    return result


def execution_command(private_root: Path) -> str:
    return f"python run.py --execute --private-root {private_root} --allow-remote --acknowledge-zero-incremental-charge"
