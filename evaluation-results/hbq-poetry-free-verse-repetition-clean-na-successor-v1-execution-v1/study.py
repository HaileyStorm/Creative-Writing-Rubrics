"""Three-slot clean-N/A successor using the frozen proven S1 lifecycle."""
from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
TEMPLATE_PATH = "evaluation-results/hbq-poetry-free-verse-repetition-treatment-v1-execution-v1/study.py"
TEMPLATE_BLOB = "36056696fc6ed7c926cd0a319d371da41ae32867"
RESULT_PATH = "evaluation-results/hbq-poetry-free-verse-repetition-treatment-v1-execution-v1-public-result-v1"
RESULT_TREE = "b0c41c99632ef63a1df55546703ceb3fb1d116f9"
RESULT_FILES = {
    "README.md": "7b9c889586a0994fba61aa438c422c29cff65cdd",
    "public-result.json": "326968f0e93ca0edc5d21e1846d772b0cb4557d1",
}
CONTROLLER_SHA256 = "9a4d493af953f59a5669aff5c8a87ab3725154a3ec07747a899494551a298d76"
LEDGER_SHA256 = "a1782776708b50e8052e9ea750389530da32a0808d1f2420db00704d925595ec"
VERIFIER_SHA256 = "aec06bf86f6be541e1357f72487637d5cfc31b5d00f8b1ec0691e5ae242b7b56"
FIXTURE_SHA256 = "ac769c306651f8f0f9b4157f84dd09afd4f536217655c1f4028ca546773019ec"
PRIVATE_EXECUTION_DIRECTORY = "execution-v1-terminal-sidecar-v1"
SLOTS = 3
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_clean_na_successor"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")
RUNTIME_SHA256 = {
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
    "src/hbqrs/study_identity.py": "0e263a43e13f97a2c5abfa2f320c0fb78c362b9e4741cc8b12f1471e12d7eb10",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
    "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
    "registry/all_modules.json": "b8c453f7eb86889f2e76b593eb44a6660f9f7cd695dbd6ac3d13b23d3635102b",
    "bundles/all_bundles.jsonl": "18fe55b796b2809f9b8fe3b8cfbc9ef672d990141c79839cf291b6ace7308f5f",
    "registry/criterion_ownership.json": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876",
    "registry/question_index.jsonl": "d89706f0d32b4b8f5393a81d2d2382d58890452a55e0549c5bac77dd2497892a",
}


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8",
        capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git binding lookup failed")
    return result.stdout.strip()


def _git_bytes(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=REPOSITORY, capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


@lru_cache(maxsize=1)
def _base() -> ModuleType:
    if _git("rev-parse", f"{SOURCE_COMMIT}:{TEMPLATE_PATH}") != TEMPLATE_BLOB:
        raise ValueError("Frozen S1 lifecycle template binding drifted")
    source = _git_bytes("show", f"{SOURCE_COMMIT}:{TEMPLATE_PATH}")
    module = ModuleType("_s1_clean_na_frozen_lifecycle")
    module.__file__ = f"git:{SOURCE_COMMIT}:{TEMPLATE_PATH}"
    sys.modules[module.__name__] = module
    # Execute only the exact Git-bound source bytes verified immediately above.
    exec(compile(source, module.__file__, "exec"), module.__dict__)  # noqa: S102
    _configure(module)
    return module


def _configure(base: ModuleType) -> None:
    base.ROOT = ROOT
    base.REPOSITORY = REPOSITORY
    base.STUDY_ID = STUDY_ID
    base.EXECUTION_SUCCESSOR_VERSION = 1
    base.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY
    base.SLOTS = SLOTS
    base.ARMS = ARMS
    base.REPEATS = REPEATS
    base.BUNDLE_ID = BUNDLE_ID
    base.SUCCESSOR_FILES = SUCCESSOR_FILES
    base.CONTROLLER_SHA256 = CONTROLLER_SHA256
    base.LEDGER_SHA256 = LEDGER_SHA256
    base.VERIFIER_SHA256 = VERIFIER_SHA256
    base._private_freeze = _private_freeze
    base._questions = _questions
    base._task_contract = _task_contract
    base._scope_override = _scope_override
    base._generated_input_bindings = _generated_input_bindings
    base._manifest = _manifest
    base.validate_package = validate_package
    base.prepare = prepare
    base._verify_prompt_pairs = _verify_prompt_pairs
    base.dry_run = _dry_run_core
    base._derive_gate = _derive_gate
    base.settle = _settle


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    base = _base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = (
        (controller_path, CONTROLLER_SHA256),
        (ledger_path, LEDGER_SHA256),
        (verifier_path, VERIFIER_SHA256),
    )
    if any(not path.is_file() or base.sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private clean-N/A controller, ledger, or verifier drifted")
    controller = base._load_json(controller_path)
    ledger = base._load_json(ledger_path)
    fixture_matrix = controller.get("fixture_matrix")
    slot_mapping = ledger.get("slot_mapping")
    if (
        controller.get("study_id") != STUDY_ID
        or controller.get("format_version") != 1
        or controller.get("visibility") != "private_controller_only"
        or not isinstance(fixture_matrix, list)
        or len(fixture_matrix) != 1
        or not isinstance(slot_mapping, list)
        or len(slot_mapping) != SLOTS
    ):
        raise ValueError("Private clean-N/A geometry drifted")
    fixture = fixture_matrix[0]
    if (
        fixture.get("role") != "control"
        or fixture.get("expected_verdict") != "NOT_APPLICABLE"
        or fixture.get("completion_status") != "complete"
        or base.sha256_bytes(str(fixture.get("text")).encode("utf-8")) != FIXTURE_SHA256
    ):
        raise ValueError("Private clean-N/A fixture boundary drifted")
    expected_slots = {
        (f"s1cleanna-v1-slot-{repeat:02d}", fixture["fixture_id"], "candidate", repeat)
        for repeat in REPEATS
    }
    actual_slots = {
        (item.get("opaque_slot_id"), item.get("fixture_id"), item.get("arm"), item.get("repeat"))
        for item in slot_mapping
        if isinstance(item, Mapping)
    }
    if actual_slots != expected_slots:
        raise ValueError("Private clean-N/A slot mapping drifted")
    return controller, ledger


def _questions() -> dict[str, dict[str, Any]]:
    base = _base()
    original = base._predecessor_contract()
    candidate = original.get("candidate")
    source = base._source_leaf()
    preserved = candidate.get("preserved_fields") if isinstance(candidate, Mapping) else None
    if not isinstance(candidate, Mapping) or not isinstance(preserved, Mapping):
        raise TypeError("Frozen predecessor candidate is unavailable")
    if any(source.get(key) != value for key, value in preserved.items()):
        raise ValueError("Canonical repetition leaf fields drifted")
    source_leaf = {key: source[key] for key in (*preserved, "text")}
    treatment = dict(source_leaf)
    treatment["text"] = str(candidate["text"])
    if base.sha256_bytes(base.canonical_json(source_leaf)) != candidate.get("source_leaf_sha256"):
        raise ValueError("Frozen source leaf digest drifted")
    if base.sha256_bytes(base.canonical_json(treatment)) != candidate.get("candidate_leaf_sha256"):
        raise ValueError("Frozen candidate leaf digest drifted")
    return {"candidate": treatment}


def _task_contract(fixture: Mapping[str, Any]) -> dict[str, Any]:
    base = _base()
    return {
        "contract_version": 1,
        "contract_id": f"s1-clean-na-{base._fixture_token(str(fixture['fixture_id']))}",
        "artifact_id": str(fixture["fixture_id"]),
        "context": {
            "artifact_kind": "poetry",
            "declared_scope": fixture["declared_scope"],
            "completion_status": fixture["completion_status"],
            "background": ["Private synthetic development screen."],
            "constraints": ["Use only supplied artifact and contexts."],
            "audience": ["development-only rubric validation"],
        },
        "preferences": [],
        "priorities": [],
        "weighted_goals": [],
        "binding_requirements": [],
    }


def _scope_override(fixture: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    base = _base()
    return {
        "format_version": 1,
        "artifact_id": str(fixture["fixture_id"]),
        "bundle_id": BUNDLE_ID,
        "task_contract_sha256": base.sha256_bytes(base.canonical_json(task)),
        "contract_id": task["contract_id"],
        "artifact_kind": "poetry",
        "declared_scope": fixture["declared_scope"],
        "compatibility_mode": "reviewed_override",
        "decision_id": "s1-clean-na-execution-v1-scope-compatibility",
        "reviewer": "hbqrs-reviewed-v1",
        "reason": "Reviewed compatibility for the frozen candidate-only singleton diagnostic.",
    }


def _generated_input_bindings(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    base = _base()
    paths = {
        "catalog/bundles.json": root / "catalog" / "bundles.json",
        "catalog/registry-b.json": base._registry_path(root, "candidate"),
        "private-schedule.json": root / "private-schedule.json",
    }
    for slot in schedule:
        token = base._fixture_token(str(slot["fixture_id"]))
        paths[f"inputs/artifact-{token}.txt"] = base._artifact_path(root, slot)
        paths[f"contracts/task-{token}.json"] = base._task_path(root, slot)
        paths[f"overrides/scope-{token}.json"] = base._override_path(root, slot)
        for path in base._context_paths(root, slot):
            paths[path.relative_to(root).as_posix()] = path
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("Generated clean-N/A execution input is unavailable")
    return {name: base.sha256_file(path) for name, path in sorted(paths.items())}


def _manifest(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = _base()
    slots = [
        {key: slot[key] for key in ("opaque_slot_id", "repeat", "condition", "logical_sample_id")}
        for slot in schedule
    ]
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "execution_successor_version": 1,
        "contract_sha256": base.sha256_file(ROOT / "study-contract.json"),
        "runtime_bindings": base._runtime_bindings(),
        "generated_input_bindings": _generated_input_bindings(base._execution_root(), schedule),
        "planned_slots": SLOTS,
        "slots": slots,
    }


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def validate_package() -> dict[str, Any]:
    base = _base()
    value = contract()
    if (
        value.get("study_id") != STUDY_ID
        or value.get("format_version") != 1
        or value.get("status") != "frozen_unexecuted_candidate_only_clean_na_successor"
    ):
        raise ValueError("Clean-N/A contract identity drifted")
    if value.get("source_checkout") != {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE}:
        raise ValueError("Clean-N/A source checkout binding drifted")
    expected_template = {"commit": SOURCE_COMMIT, "path": TEMPLATE_PATH, "blob": TEMPLATE_BLOB}
    if value.get("template_executor") != expected_template:
        raise ValueError("Clean-N/A template binding drifted")
    expected_result = {
        "commit": SOURCE_COMMIT,
        "tree": RESULT_TREE,
        "path": RESULT_PATH,
        "files": RESULT_FILES,
        "disposition": "immutable_formal_no_go_with_disputed_na_oracle",
    }
    if value.get("predecessor_result") != expected_result:
        raise ValueError("Clean-N/A predecessor lineage drifted")
    if value.get("geometry") != {
        "fixtures": 1, "arms": ["candidate"], "repeats": 3,
        "slots": 3, "one_leaf_per_call": True,
    }:
        raise ValueError("Clean-N/A geometry drifted")
    if value.get("private_commitments") != {
        "controller_sha256": CONTROLLER_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "verifier_sha256": VERIFIER_SHA256,
        "fixture_text_sha256": FIXTURE_SHA256,
    }:
        raise ValueError("Clean-N/A private commitments drifted")
    if value.get("runtime_sha256") != RUNTIME_SHA256:
        raise ValueError("Clean-N/A runtime contract drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen source tree is unavailable")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{RESULT_PATH}") != RESULT_TREE:
        raise ValueError("Frozen predecessor result tree is unavailable")
    for name, blob in RESULT_FILES.items():
        if _git("rev-parse", f"{SOURCE_COMMIT}:{RESULT_PATH}/{name}") != blob:
            raise ValueError("Frozen predecessor result file drifted")
    for path, digest in RUNTIME_SHA256.items():
        if base.sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    questions = _questions()
    candidate = value.get("candidate")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("leaf_id") != base.LEAF_ID
        or candidate.get("text") != questions["candidate"]["text"]
        or candidate.get("source_leaf_sha256") != "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a"
        or candidate.get("candidate_leaf_sha256") != "762e514431bd72cf91236f46100b3c8808b961450d914ad6bbcdd20f216ec539"
        or candidate.get("prompt_delta") != "none_from_predecessor_candidate"
    ):
        raise ValueError("Unchanged candidate wording binding drifted")
    _private_freeze()
    schedule = base.build_schedule()
    if len(schedule) != 3 or {slot["arm"] for slot in schedule} != {"candidate"}:
        raise ValueError("Candidate-only schedule drifted")
    return {
        "study_id": STUDY_ID,
        "source_commit": SOURCE_COMMIT,
        "slots": 3,
        "provider_calls": 0,
        "success_authorizes_only": "fresh_disjoint_holdout",
    }


def prepare() -> dict[str, Any]:
    base = _base()
    validate_package()
    root, schedule = base._execution_root(), base.build_schedule()
    if base._claim_path(root).exists():
        raise ValueError("Preparation cannot rewrite a claimed root")
    base._write_or_verify(root / "catalog" / "bundles.json", base.canonical_json(base._bundle()))
    base._write_or_verify(base._registry_path(root, "candidate"), base.canonical_json(base._registry("candidate")))
    controller, _ledger = _private_freeze()
    fixture = controller["fixture_matrix"][0]
    slot = schedule[0]
    base._write_or_verify(base._artifact_path(root, slot), str(fixture["text"]).encode("utf-8"))
    task = _task_contract(fixture)
    base._write_or_verify(base._task_path(root, slot), base.canonical_json(task))
    base._write_or_verify(base._override_path(root, slot), base.canonical_json(_scope_override(fixture, task)))
    for index, context in enumerate(fixture["contexts"], start=1):
        path = root / "contexts" / base._fixture_token(str(fixture["fixture_id"])) / f"context-{index:02d}.txt"
        base._write_or_verify(path, str(context).encode("utf-8"))
    base._write_or_verify(root / "private-schedule.json", base.canonical_json({"format_version": 1, "slots": schedule}))
    base._write_prepared_manifest(root / "study-manifest.json", base.canonical_json(_manifest(schedule)))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _verify_prompt_pairs(
    root: Path,
    schedule: Sequence[Mapping[str, Any]],
    prompts: Mapping[str, bytes],
) -> None:
    del root
    base = _base()
    candidate = _questions()["candidate"]["text"].encode("utf-8")
    source = base._source_leaf()["text"].encode("utf-8")
    if len(schedule) != 3 or set(prompts) != {str(slot["opaque_slot_id"]) for slot in schedule}:
        raise ValueError("Clean-N/A rendered prompt geometry drifted")
    for slot in schedule:
        prompt = prompts[str(slot["opaque_slot_id"])]
        if candidate not in prompt or source in prompt:
            raise ValueError("Clean-N/A provider prompt leaked or changed its treatment boundary")


def _dry_run_core(*, runner_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    base = _base()
    prepared = prepare()
    root, schedule = base._execution_root(), base.build_schedule()
    prompts: dict[str, bytes] = {}
    for slot in schedule:
        rendered = base._run_render(slot, runner_call)
        prompts[str(slot["opaque_slot_id"])] = rendered
        base._write_or_verify(root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt", rendered)
    _verify_prompt_pairs(root, schedule, prompts)
    disclosure = base._disclosure(schedule, prompts)
    base._write_or_verify(
        root / "receipts" / "preexecution-disclosure.v1.json",
        base.canonical_json(disclosure),
    )
    base._write_or_verify(
        root / "receipts" / "provider-free-dry-run.v1.json",
        base.canonical_json({
            "format_version": 1,
            "study_id": STUDY_ID,
            "provider_calls": 0,
            "candidate_prompt_checks": SLOTS,
            "disclosure_sha256": base.sha256_bytes(base.canonical_json(disclosure)),
        }),
    )
    return {
        **prepared,
        "rendered_prompts": SLOTS,
        "provider_calls": 0,
        "candidate_prompt_checks": SLOTS,
    }


def _derive_gate(root: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = _base()
    record_path = root / "terminal-slot-records.v1.json"
    base._write_or_verify(record_path, base.canonical_json(list(records)))
    verifier = base._private_paths()[2]
    result = subprocess.run(
        [sys.executable, str(verifier), "--assess-records", str(record_path)],
        cwd=base._controller_root(), text=True, encoding="utf-8",
        capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError("Private clean-N/A verifier rejected settlement evidence")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("decision") not in {"HOLDOUT_ELIGIBLE_ON_SUCCESS", "NO_GO"}:
        raise ValueError("Private clean-N/A verifier returned an invalid gate")
    return value


def _settle(
    *,
    verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base = _base()
    validate_package()
    root, schedule = base._execution_root(), base._runtime_schedule()
    if base._load_json(root / "receipts" / "zero-charge-acknowledgement.v1.json") != base._zero_charge_receipt():
        raise ValueError("Zero-charge acknowledgement is unavailable or drifted")
    prompts = {
        str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes()
        for slot in schedule
    }
    if base._load_json(root / "receipts" / "preexecution-disclosure.v1.json") != base._disclosure(schedule, prompts):
        raise ValueError("Preexecution disclosure is unavailable or drifted")
    claim = base._require_execution_claim(root, schedule)
    if (root / "settlement.v1.json").exists() or (root / "public-aggregate.v1.json").exists():
        raise ValueError("Original settlement is write-once")
    verify = verifier or base._verify_slot
    records = [verify(root, slot) for slot in schedule]
    gate = _derive_gate(root, records)
    decision = str(gate["decision"])
    settlement = {
        "study_id": STUDY_ID,
        "decision": decision,
        "completed_slots": SLOTS,
        "planned_slots": SLOTS,
        "clean_na_matches": gate["clean_na_matches"],
        "promotion": "none",
        "success_authorizes_only": "fresh_disjoint_holdout",
        "records": records,
        "execution_claim_sha256": base.sha256_file(claim),
    }
    public = {
        "study_id": STUDY_ID,
        "decision": decision,
        "completed_slots": SLOTS,
        "planned_slots": SLOTS,
        "aggregate": {"clean_na_matches": gate["clean_na_matches"], "required": 3},
        "promotion": "none",
        "success_authorizes_only": "fresh_disjoint_holdout",
    }
    base._write_terminal(root, settlement, public)
    return settlement


def set_private_root(value: str | Path) -> Path:
    return _base().set_private_root(value)


def build_schedule() -> list[dict[str, Any]]:
    return _base().build_schedule()


def dry_run(
    private_root: str | Path,
    *,
    runner_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    set_private_root(private_root)
    return _base().dry_run(runner_call=runner_call)


def execute(
    private_root: str | Path,
    *,
    allow_remote: bool = False,
    acknowledged_zero_incremental_charge: bool = False,
    runner_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if not allow_remote:
        raise ValueError("Execution requires explicit allow-remote authority")
    if not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit zero-incremental-charge acknowledgement")
    set_private_root(private_root)
    return _base().execute(
        acknowledged_zero_incremental_charge=True,
        runner_call=runner_call,
    )


def settle(
    private_root: str | Path,
    *,
    verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    set_private_root(private_root)
    return _settle(verifier=verifier)


def command_for(
    slot: Mapping[str, Any],
    private_root: str | Path,
    *,
    render: bool = False,
) -> list[str]:
    set_private_root(private_root)
    return _base()._command(slot, render=render)


def canonical_json(value: Any) -> bytes:
    return _base().canonical_json(value)


def sha256_file(path: Path) -> str:
    return _base().sha256_file(path)
