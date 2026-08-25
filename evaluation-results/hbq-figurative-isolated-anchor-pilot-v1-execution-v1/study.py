"""Control-first, one-attempt executor for the figurative isolated-anchor pilot."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from hbqrs import runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
BASE_RELATIVE = "evaluation-results/hbq-figurative-metaphor-checklist-successor-v1-execution-v1/study.py"
BASE_BLOB = "35dd5c38b5ea8873576f29c9a4ef5300c0b316cb"
BASE_SHA256 = "8f7fdfb539a37e557b3ad27bacbf240bdeeb9f468c57013c1c3178335468461b"
STUDY_ID = "hbq-figurative-isolated-anchor-pilot-v1-execution-v1"
PRIVATE_EXECUTION_DIRECTORY = "figurative-isolated-anchor-pilot-v1"
TARGET = "penalty.purple_prose.metaphor"
STOCKNESS = "core.freshness_and_non_genericness.no_default_metaphors"
PROPORTION = "penalty.purple_prose.proportion"
CONTROLS = (STOCKNESS, PROPORTION)
LEAVES = (STOCKNESS, PROPORTION, TARGET)
REPEATS = (1, 2, 3)
CONTROL_SLOTS = 12
TARGET_SLOTS = 6
SLOTS = 18
BUNDLE_ID = "figurative-isolated-anchor-pilot-v1"
ATTEMPT_LIFECYCLE_POLICY = "terminal_sidecar_v1"
SUCCESSOR_FILES = (
    "README.md",
    "expected-verdict-ledger.json",
    "public-synthetic-corpus.json",
    "run.py",
    "study-contract.json",
    "study.py",
)
TARGET_TREATMENT = (
    "Inspect each material metaphor or image in the declared scope and compare the implications "
    "attached to the same subject or linked subjects. Return YES when those implications can coexist "
    "and jointly clarify the passage. Return NO only when the passage presents incompatible figurative "
    "implications without a supported shift, contrast, or deliberate double meaning, so the images "
    "materially compete or destabilize the declared scope. Do not judge familiarity/defaultness or sheer "
    "figurative load relative to content; cite the cooperating or conflicting spans."
)
STRICT_EVIDENCE_INSTRUCTION = (
    "For this pilot, include at least one exact_quote copied verbatim from the supplied artifact; "
    "summary-only evidence is invalid."
)


def _load_base():
    path = REPOSITORY / BASE_RELATIVE
    spec = importlib.util.spec_from_file_location("figurative_anchor_base_executor", path)
    if spec is None or spec.loader is None:
        raise ValueError("Base executor cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_base = _load_base()
canonical_json = _base.canonical_json
sha256_bytes = _base.sha256_bytes
sha256_file = _base.sha256_file
canonical_prompt_bytes = _base.canonical_prompt_bytes
_load_json = _base._load_json
_git = _base._git


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _corpus() -> list[dict[str, Any]]:
    value = _load_json(ROOT / "public-synthetic-corpus.json")
    fixtures = value.get("fixtures")
    if (
        value.get("format_version") != 1
        or value.get("study_id") != STUDY_ID
        or value.get("privacy") != "public_synthetic_only"
        or not isinstance(fixtures, list)
        or len(fixtures) != 6
    ):
        raise ValueError("Public synthetic corpus drifted")
    return [dict(item) for item in fixtures if isinstance(item, Mapping)]


def _ledger() -> dict[str, str]:
    value = _load_json(ROOT / "expected-verdict-ledger.json")
    expected = value.get("expected_verdicts")
    if (
        value.get("format_version") != 1
        or value.get("study_id") != STUDY_ID
        or value.get("provider_disclosure") != "forbidden"
        or not isinstance(expected, Mapping)
        or set(expected.values()) - {"YES", "NO"}
    ):
        raise ValueError("Expected verdict ledger drifted")
    return {str(key): str(item) for key, item in expected.items()}


def _source_anchor() -> dict[str, str]:
    return {
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "base_executor": BASE_RELATIVE,
        "base_executor_blob": BASE_BLOB,
        "base_executor_sha256": BASE_SHA256,
    }


def validate_package() -> dict[str, Any]:
    value = contract()
    if value.get("format_version") != 1 or value.get("study_id") != STUDY_ID:
        raise ValueError("Pilot identity drifted")
    if value.get("status") != "frozen_control_first_provider_free_preexecution":
        raise ValueError("Pilot status drifted")
    if value.get("source_anchor") != _source_anchor():
        raise ValueError("Source anchor drifted")
    if _git("rev-parse", SOURCE_COMMIT) != SOURCE_COMMIT:
        raise ValueError("Exact source commit is unavailable")
    if _git("rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("Pilot preparation requires exact CWR HEAD 6ae9ee0")
    if _git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Exact source tree is unavailable")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{BASE_RELATIVE}") != BASE_BLOB:
        raise ValueError("Frozen base executor blob drifted")
    if sha256_file(REPOSITORY / BASE_RELATIVE) != BASE_SHA256:
        raise ValueError("Current base executor bytes drifted")
    geometry = {
        "public_synthetic_fixtures": 6,
        "repeats": 3,
        "stage_1_control_slots": CONTROL_SLOTS,
        "stage_2_target_slots": TARGET_SLOTS,
        "maximum_provider_sends": SLOTS,
        "stage_order": "all_controls_before_any_target",
    }
    if value.get("geometry") != geometry:
        raise ValueError("Pilot geometry drifted")
    if value.get("leaves") != {
        "target": TARGET,
        "stockness_owner": STOCKNESS,
        "density_owner": PROPORTION,
    }:
        raise ValueError("Leaf ownership contract drifted")
    treatment = value.get("target_treatment")
    if not isinstance(treatment, Mapping) or treatment.get("exact_text") != TARGET_TREATMENT:
        raise ValueError("Target treatment drifted")
    if treatment.get("applies_only_to") != TARGET or treatment.get("rubric_runtime_change") != "none":
        raise ValueError("Target treatment scope drifted")
    expected_execution = {
        "route": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "one_leaf_per_call": True,
        "batch_size": 1,
        "batch_attempts": 1,
        "physical_attempts_per_slot": 1,
        "retry_or_resume": "forbidden",
        "attempt_lifecycle_policy": ATTEMPT_LIFECYCLE_POLICY,
        "run_manifest_format_version": 5,
        "zero_incremental_charge_only": True,
        "paid_fallback": "forbidden",
        "authentication": "chatgpt_subscription_via_exact_codex_exe_no_api_billing_environment",
        "sole_provider_capable_mode": "run.py --execute with dual acknowledgement",
    }
    if value.get("execution") != expected_execution:
        raise ValueError("Execution contract drifted")
    if value.get("evidence_gate") != {
        "accepted_slot": "at_least_one_source_exact_quote",
        "summary_only": "reject",
        "normalization_audit": "must_be_empty",
        "invalid_quote_demotion": "reject",
        "source_scope": "supplied_artifact_only",
        "model_facing_instruction": STRICT_EVIDENCE_INSTRUCTION,
    }:
        raise ValueError("Strict source-exact evidence gate drifted")
    claims = value.get("claims")
    if not isinstance(claims, Mapping) or any(claims.get(key) != "unchanged" for key in ("rubric_wording", "stable_ids", "ownership", "weights", "splits")):
        raise ValueError("Non-promotion invariants drifted")
    schedule = build_schedule(validate=False)
    if len(schedule) != SLOTS:
        raise ValueError("Pilot schedule drifted")
    return {
        "study_id": STUDY_ID,
        "slots": SLOTS,
        "control_slots": CONTROL_SLOTS,
        "target_slots": TARGET_SLOTS,
        "provider_calls": 0,
        "promotion": "none",
    }


def build_schedule(*, validate: bool = True) -> list[dict[str, Any]]:
    if validate:
        validate_package()
    fixtures, ledger = _corpus(), _ledger()
    if len(fixtures) != 6 or set(ledger) != {str(item.get("case_id")) for item in fixtures}:
        raise ValueError("Fixture and ledger identity drifted")
    controls = [item for item in fixtures if item.get("stage") == "control"]
    targets = [item for item in fixtures if item.get("stage") == "target"]
    if len(controls) != 4 or len(targets) != 2:
        raise ValueError("Control-first fixture geometry drifted")
    if [item.get("leaf_id") for item in controls] != [STOCKNESS, STOCKNESS, PROPORTION, PROPORTION]:
        raise ValueError("Control ownership or ordering drifted")
    if any(item.get("leaf_id") != TARGET for item in targets):
        raise ValueError("Target ownership drifted")
    rows: list[dict[str, Any]] = []
    for fixture in [*controls, *targets]:
        case_id, leaf_id, text, stage = (
            fixture.get("case_id"),
            fixture.get("leaf_id"),
            fixture.get("text"),
            fixture.get("stage"),
        )
        if not all(isinstance(item, str) and item for item in (case_id, leaf_id, text, stage)):
            raise ValueError("Fixture shape drifted")
        fixture_number = len(rows) // 3 + 1
        artifact_id = f"figurative-anchor-{fixture_number:02d}"
        for repeat in REPEATS:
            rows.append({
                "slot_id": f"figurative-anchor-{fixture_number:02d}-r{repeat}",
                "artifact_id": artifact_id,
                "case_id": case_id,
                "stage": stage,
                "leaf_id": leaf_id,
                "repeat": repeat,
                "artifact_text": text,
                "artifact_sha256": sha256_bytes(text.encode("utf-8")),
                "expected_verdict": ledger[case_id],
                "treatment": "manual_leaf_appendix_v1" if stage == "target" else "current_production_prompt",
            })
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS:
        raise ValueError("Exact 18-slot schedule drifted")
    if any(row["stage"] != "control" for row in rows[:CONTROL_SLOTS]) or any(row["stage"] != "target" for row in rows[CONTROL_SLOTS:]):
        raise ValueError("Control-first slot ordering drifted")
    return rows


def _task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    target = slot["stage"] == "target"
    return {
        "contract_version": 1,
        "contract_id": f"figurative-anchor-{slot['artifact_id']}",
        "artifact_id": slot["artifact_id"],
        "context": {
            "artifact_kind": "prose.short_story",
            "declared_scope": "complete supplied passage",
            "completion_status": "complete",
            "background": ["Public synthetic isolated figurative anchor."],
            "constraints": (
                ["Use only the supplied artifact.", STRICT_EVIDENCE_INSTRUCTION, TARGET_TREATMENT]
                if target
                else ["Use only the supplied artifact.", STRICT_EVIDENCE_INSTRUCTION]
            ),
            "audience": ["development-only rubric validation"],
        },
        "preferences": [],
        "priorities": [],
        "weighted_goals": [],
        "binding_requirements": [],
    }


def _scope_override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "artifact_id": slot["artifact_id"],
        "bundle_id": BUNDLE_ID,
        "task_contract_sha256": sha256_bytes(canonical_json(task)),
        "contract_id": task["contract_id"],
        "artifact_kind": task["context"]["artifact_kind"],
        "declared_scope": task["context"]["declared_scope"],
        "compatibility_mode": "reviewed_override",
        "decision_id": "figurative-anchor-pilot-scope-compatibility-v1",
        "reviewer": "hbqrs-reviewed-v1",
        "reason": "Reviewed compatibility for the isolated public synthetic figurative anchor pilot.",
    }


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: slot[key]
        for key in (
            "slot_id",
            "artifact_id",
            "stage",
            "leaf_id",
            "repeat",
            "artifact_sha256",
            "treatment",
        )
    }


def _runtime_bindings() -> dict[str, Any]:
    return {
        "source_anchor_commit": SOURCE_COMMIT,
        "cwr_head": _git("rev-parse", "HEAD"),
        "base_executor": {
            "path": BASE_RELATIVE,
            "blob": _git("rev-parse", f"{SOURCE_COMMIT}:{BASE_RELATIVE}"),
            "sha256": sha256_file(REPOSITORY / BASE_RELATIVE),
        },
        "cwr_files": {
            path: sha256_file(REPOSITORY / path)
            for path in _base.RUNTIME_PATHS
        },
        "successor_files": {
            path: sha256_file(ROOT / path)
            for path in SUCCESSOR_FILES
        },
    }


def _configure_base() -> None:
    _base.ROOT = ROOT
    _base.REPOSITORY = REPOSITORY
    _base.STUDY_ID = STUDY_ID
    _base.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY
    _base.TARGET = TARGET
    _base.CONTROLS = CONTROLS
    _base.LEAVES = LEAVES
    _base.REPEATS = REPEATS
    _base.SLOTS = SLOTS
    _base.BUNDLE_ID = BUNDLE_ID
    _base.ATTEMPT_LIFECYCLE_POLICY = ATTEMPT_LIFECYCLE_POLICY
    _base.SUCCESSOR_FILES = SUCCESSOR_FILES
    _base.contract = contract
    _base.validate_package = validate_package
    _base.build_schedule = build_schedule
    _base._task_contract = _task_contract
    _base._scope_override = _scope_override
    _base._public_slot = _public_slot
    _base._runtime_bindings = _runtime_bindings


_configure_base()


def prepare(private_root: str | Path) -> dict[str, Any]:
    return _base.prepare(private_root)


def dry_run(
    private_root: str | Path,
    *,
    runner_call: Callable[..., Any] = subprocess.run,
    auth_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    report = _base.dry_run(private_root, runner_call=runner_call, auth_call=auth_call)
    root = _base._root(private_root)
    schedule = _base._validated_runtime_schedule(private_root)
    control_prompts = [slot["rendered_prompt_sha256"] for slot in schedule if slot["stage"] == "control"]
    target_prompts = [slot["rendered_prompt_sha256"] for slot in schedule if slot["stage"] == "target"]
    _base._write_or_verify(
        root / "receipts" / "control-first-provider-free-dry-run.v1.json",
        canonical_json({
            "format_version": 1,
            "study_id": STUDY_ID,
            "provider_calls": 0,
            "control_slots": len(control_prompts),
            "target_slots": len(target_prompts),
            "stage_order": "all_controls_before_any_target",
            "control_prompt_aggregate_sha256": sha256_bytes(canonical_json(control_prompts)),
            "target_prompt_aggregate_sha256": sha256_bytes(canonical_json(target_prompts)),
            "target_treatment_sha256": sha256_bytes(TARGET_TREATMENT.encode("utf-8")),
            "promotion": "none",
        }),
    )
    return {
        **report,
        "control_slots": CONTROL_SLOTS,
        "target_slots": TARGET_SLOTS,
        "control_first": True,
        "promotion": "none",
    }


def _zero_charge_receipt(authentication: Mapping[str, Any]) -> dict[str, Any]:
    return _base._zero_charge_receipt(authentication)


def _terminal_paths(root: Path) -> tuple[Path, ...]:
    return (
        root / "anchor-pilot-settlement.v1.json",
        root / "public-aggregate.v1.json",
        root / "terminal-sidecar.v5.json",
    )


def _dispatch_slot(
    slot: Mapping[str, Any],
    private_root: str | Path,
    *,
    runner_call: Callable[..., Any],
    environment: Mapping[str, str],
    codex_binary: str,
) -> None:
    done = runner_call(
        _base.command_for(slot, private_root, allow_remote=True, codex_binary=codex_binary),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=dict(environment),
    )
    if getattr(done, "returncode", 1):
        raise RuntimeError(f"Execution stopped at {slot['slot_id']}; do not retry or resume this successor")


def _valid_binary(record: Mapping[str, Any]) -> bool:
    return record.get("verdict") in {"YES", "NO"}


def _validate_strict_evidence(
    evidence: Sequence[Mapping[str, Any]],
    *,
    artifact_text: str,
    question_id: str,
    normalization_audit: Any,
) -> dict[str, Any]:
    if normalization_audit != []:
        raise ValueError("Accepted anchor evidence must have an empty normalization audit")
    runner._validate_typed_checkpoint_evidence(evidence, question_id=question_id)
    exact = [item for item in evidence if isinstance(item.get("exact_quote"), str) and item["exact_quote"].strip()]
    if not exact:
        raise ValueError("Accepted anchor evidence requires at least one source-exact quote; summary-only evidence is rejected")
    runner._validate_exact_quotes(
        exact,
        artifact_text=artifact_text,
        context_texts=[],
        question_id=question_id,
    )
    return {
        "exact_quote_count": len(exact),
        "exact_quote_aggregate_sha256": sha256_bytes(canonical_json(exact)),
        "normalization_audit": "empty",
    }


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    record = _base._verify_slot(root, slot)
    checkpoint = _load_json(root / "runs" / str(slot["slot_id"]) / "responses" / "batch-0001.json")
    normalized = checkpoint.get("normalized_verdicts")
    if not isinstance(normalized, list) or len(normalized) != 1 or not isinstance(normalized[0], Mapping):
        raise ValueError("Accepted anchor checkpoint must contain exactly one normalized verdict")
    verdict = normalized[0]
    if verdict.get("question_id") != slot["leaf_id"]:
        raise ValueError("Accepted anchor checkpoint leaf drifted")
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, Mapping) for item in evidence):
        raise ValueError("Accepted anchor checkpoint evidence shape drifted")
    strict = _validate_strict_evidence(
        evidence,
        artifact_text=str(slot["artifact_text"]),
        question_id=str(slot["leaf_id"]),
        normalization_audit=checkpoint.get("normalization_audit"),
    )
    return {**record, "strict_evidence": strict}


def _control_gate_payload(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    correct = sum(bool(record.get("correct")) for record in records)
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "immutable_control_gate",
        "completed_control_slots": len(records),
        "correct_control_slots": correct,
        "passed": len(records) == CONTROL_SLOTS and correct == CONTROL_SLOTS and all(_valid_binary(record) for record in records),
        "target_dispatch_authorized": len(records) == CONTROL_SLOTS and correct == CONTROL_SLOTS and all(_valid_binary(record) for record in records),
        "record_aggregate_sha256": sha256_bytes(canonical_json(list(records))),
    }


def _write_terminal(root: Path, settlement: Mapping[str, Any]) -> None:
    _base._write_summary(
        root / "terminal-sidecar.v5.json",
        {
            "format": "terminal_sidecar_v1",
            "format_version": 5,
            "study_id": STUDY_ID,
            "decision": settlement["decision"],
            "completed_slots": settlement["completed_slots"],
            "planned_slots": SLOTS,
            "settlement_sha256": sha256_file(root / "anchor-pilot-settlement.v1.json"),
            "promotion": "none",
        },
    )


def _publish_settlement(root: Path, settlement: Mapping[str, Any]) -> dict[str, Any]:
    public = {
        "study_id": STUDY_ID,
        "decision": settlement["decision"],
        "completed_slots": settlement["completed_slots"],
        "planned_slots": SLOTS,
        "controls": settlement.get("controls"),
        "target": settlement.get("target"),
        "dspy_eligible": settlement.get("dspy_eligible", False),
        "target_treatment": "experimental_not_promoted",
        "promotion": "none",
    }
    _base._write_summary(root / "anchor-pilot-settlement.v1.json", settlement)
    _base._write_summary(root / "public-aggregate.v1.json", public)
    _write_terminal(root, settlement)
    return dict(settlement)


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]]) -> dict[str, Any]:
    return _publish_settlement(
        root,
        {
            "format_version": 1,
            "study_id": STUDY_ID,
            "decision": "INCOMPLETE_NO_RETRY",
            "completed_slots": completed,
            "planned_slots": SLOTS,
            "failures": failures,
            "controls": None,
            "target": None,
            "dspy_eligible": False,
            "promotion": "none",
        },
    )


def execute(
    private_root: str | Path,
    *,
    allow_remote: bool = False,
    acknowledged_zero_incremental_charge: bool = False,
    runner_call: Callable[..., Any] = subprocess.run,
    auth_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires --allow-remote and zero-incremental-charge acknowledgement")
    root = _base._root(private_root)
    if any(path.exists() for path in _terminal_paths(root)):
        raise ValueError("Pilot execution is forbidden after any terminal settlement artifact")
    _base._claim_execution(root)
    schedule = _base._validated_runtime_schedule(private_root)
    controls = [slot for slot in schedule if slot["stage"] == "control"]
    targets = [slot for slot in schedule if slot["stage"] == "target"]
    if len(controls) != CONTROL_SLOTS or len(targets) != TARGET_SLOTS or schedule != [*controls, *targets]:
        raise ValueError("Prepared schedule is not exact control-first geometry")
    dispatch_environment = _base._minimal_environment()
    frozen_authentication = _load_json(root / "receipts" / "subscription-authentication.v1.json")
    current_authentication = _base.subscription_authentication(
        runner_call=auth_call,
        environment=dispatch_environment,
    )
    if frozen_authentication != current_authentication:
        raise ValueError("Codex CLI subscription authentication evidence drifted; use a fresh dry run")
    runs_root = root / "runs"
    if runs_root.exists() and any(runs_root.iterdir()):
        raise ValueError("One-attempt pilot rejects pre-existing run directories; no retry or resume exists")
    _base._write_or_verify(
        root / "receipts" / "zero-charge-acknowledgement.v1.json",
        canonical_json(_zero_charge_receipt(current_authentication)),
    )
    control_records: list[dict[str, Any]] = []
    for slot in controls:
        _dispatch_slot(
            slot,
            private_root,
            runner_call=runner_call,
            environment=dispatch_environment,
            codex_binary=str(current_authentication["codex_executable_path"]),
        )
        try:
            record = _verify_slot(root, slot)
        except (OSError, ValueError, runner.HBQError) as exc:
            raise RuntimeError(f"Control verification stopped at {slot['slot_id']}; target remained unopened: {exc}") from exc
        if not _valid_binary(record):
            raise RuntimeError(f"Control {slot['slot_id']} returned a non-binary verdict; target remained unopened")
        control_records.append(record)
    gate = _control_gate_payload(control_records)
    _base._write_or_verify(root / "control-gate.v1.json", canonical_json(gate))
    if not gate["passed"]:
        controls_summary = {
            leaf: {
                "correct": sum(
                    bool(record["correct"])
                    for record, slot in zip(control_records, controls, strict=True)
                    if slot["leaf_id"] == leaf
                ),
                "total": 6,
                "passed": False,
            }
            for leaf in CONTROLS
        }
        return _publish_settlement(
            root,
            {
                "format_version": 1,
                "study_id": STUDY_ID,
                "decision": "CONTROL_FIXTURE_OR_PROMPT_NO_GO",
                "completed_slots": CONTROL_SLOTS,
                "planned_slots": SLOTS,
                "controls": controls_summary,
                "target": {"executed": False, "correct": 0, "total": TARGET_SLOTS},
                "dspy_eligible": False,
                "promotion": "none",
            },
        )
    for slot in targets:
        _dispatch_slot(
            slot,
            private_root,
            runner_call=runner_call,
            environment=dispatch_environment,
            codex_binary=str(current_authentication["codex_executable_path"]),
        )
    return {
        "mode": "execute",
        "executed_slots": SLOTS,
        "control_gate": "12_of_12_passed_before_target",
        "route": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "billing": "owner_attested_zero_incremental_charge",
        "promotion": "none",
    }


def _runtime_execution_evidence(private_root: str | Path) -> tuple[Path, list[dict[str, Any]]]:
    root = _base._root(private_root)
    schedule = _base._validated_runtime_schedule(private_root)
    try:
        claim = _load_json(root / "execution-claim.v1.json")
    except OSError as exc:
        raise ValueError("Atomic precontact execution claim is unavailable or drifted") from exc
    if claim != _base._execution_claim_payload(root):
        raise ValueError("Atomic precontact execution claim is unavailable or drifted")
    authentication = _load_json(root / "receipts" / "subscription-authentication.v1.json")
    if _load_json(root / "receipts" / "zero-charge-acknowledgement.v1.json") != _zero_charge_receipt(authentication):
        raise ValueError("Zero-charge acknowledgement is unavailable or drifted")
    return root, schedule


def _verify_stage(
    root: Path,
    slots: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for slot in slots:
        try:
            record = _verify_slot(root, slot)
            if not _valid_binary(record):
                raise ValueError("Anchor produced a non-binary verdict")
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    return records, failures


def settle(private_root: str | Path) -> dict[str, Any]:
    root = _base._root(private_root)
    existing = root / "anchor-pilot-settlement.v1.json"
    if existing.is_file():
        return _load_json(existing)
    try:
        root, schedule = _runtime_execution_evidence(private_root)
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "runtime", "reason": str(exc)}])
    controls = [slot for slot in schedule if slot["stage"] == "control"]
    targets = [slot for slot in schedule if slot["stage"] == "target"]
    control_records, failures = _verify_stage(root, controls)
    if failures or len(control_records) != CONTROL_SLOTS:
        return _incomplete(root, len(control_records), failures or [{"slot_id": "controls", "reason": "Control receipt count drifted"}])
    if len({record["session_id_sha256"] for record in control_records}) != CONTROL_SLOTS:
        return _incomplete(root, CONTROL_SLOTS, [{"slot_id": "controls", "reason": "Repeated provider session receipt"}])
    gate = _control_gate_payload(control_records)
    gate_path = root / "control-gate.v1.json"
    if not gate_path.is_file() or _load_json(gate_path) != gate:
        return _incomplete(root, CONTROL_SLOTS, [{"slot_id": "controls", "reason": "Immutable control gate is unavailable or drifted"}])
    controls_summary = {
        leaf: {
            "correct": sum(
                bool(record["correct"])
                for record, slot in zip(control_records, controls, strict=True)
                if slot["leaf_id"] == leaf
            ),
            "total": 6,
            "passed": all(
                bool(record["correct"])
                for record, slot in zip(control_records, controls, strict=True)
                if slot["leaf_id"] == leaf
            ),
        }
        for leaf in CONTROLS
    }
    if not gate["passed"]:
        if any((root / "runs" / str(slot["slot_id"])).exists() for slot in targets):
            return _incomplete(root, CONTROL_SLOTS, [{"slot_id": "target", "reason": "Target was dispatched despite a failed control gate"}])
        return _publish_settlement(
            root,
            {
                "format_version": 1,
                "study_id": STUDY_ID,
                "decision": "CONTROL_FIXTURE_OR_PROMPT_NO_GO",
                "completed_slots": CONTROL_SLOTS,
                "planned_slots": SLOTS,
                "controls": controls_summary,
                "target": {"executed": False, "correct": 0, "total": TARGET_SLOTS},
                "dspy_eligible": False,
                "promotion": "none",
            },
        )
    target_records, failures = _verify_stage(root, targets)
    if failures or len(target_records) != TARGET_SLOTS:
        return _incomplete(root, CONTROL_SLOTS + len(target_records), failures or [{"slot_id": "target", "reason": "Target receipt count drifted"}])
    records = [*control_records, *target_records]
    if len({record["session_id_sha256"] for record in records}) != SLOTS or len({record["checkpoint_chain_head_sha256"] for record in records}) != SLOTS:
        return _incomplete(root, SLOTS, [{"slot_id": "identity", "reason": "Repeated provider-session or checkpoint-chain receipt"}])
    cells: dict[str, list[bool]] = defaultdict(list)
    for record, slot in zip(target_records, targets, strict=True):
        cells[str(slot["artifact_id"])].append(bool(record["correct"]))
    if len(cells) != 2 or any(len(items) != 3 for items in cells.values()):
        return _incomplete(root, SLOTS, [{"slot_id": "geometry", "reason": "Expected two three-repeat target cells"}])
    target_correct = sum(sum(items) for items in cells.values())
    mixed_cells = sum(1 for items in cells.values() if 0 < sum(items) < 3)
    stable_miss_cells = sum(1 for items in cells.values() if sum(items) == 0)
    if target_correct == TARGET_SLOTS:
        decision = "MANUAL_TARGET_ANCHOR_PILOT_PASS"
        dspy_eligible = False
    elif mixed_cells:
        decision = "MANUAL_TARGET_UNSTABLE_NO_GO_DSPY_ELIGIBLE"
        dspy_eligible = True
    else:
        decision = "MANUAL_TARGET_STABLE_MISS_NO_GO_DSPY_ELIGIBLE"
        dspy_eligible = True
    return _publish_settlement(
        root,
        {
            "format_version": 1,
            "study_id": STUDY_ID,
            "decision": decision,
            "completed_slots": SLOTS,
            "planned_slots": SLOTS,
            "controls": controls_summary,
            "target": {
                "executed": True,
                "correct": target_correct,
                "total": TARGET_SLOTS,
                "mixed_cells": mixed_cells,
                "stable_miss_cells": stable_miss_cells,
            },
            "dspy_eligible": dspy_eligible,
            "dspy_trigger": "controls_12_of_12_and_valid_target_below_6_of_6" if dspy_eligible else None,
            "baseline_comparison": "none",
            "promotion": "none",
        },
    )


command_for = _base.command_for
subscription_authentication = _base.subscription_authentication
canonical_prompt_bytes = _base.canonical_prompt_bytes
_validated_runtime_schedule = _base._validated_runtime_schedule
_verify_checkpoint_prompt = _base._verify_checkpoint_prompt
_minimal_environment = _base._minimal_environment
_root = _base._root
