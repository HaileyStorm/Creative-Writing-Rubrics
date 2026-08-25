#!/usr/bin/env python3
"""Provider-free QPC24 controller verifier and 24-question native renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import runner  # noqa: E402
from hbqrs.core import compile_bundle, compiled_questions, load_data, resolve_bundle  # noqa: E402


STUDY_ID = "hbq-qpc24-exact-head-successor-v1"
HEAD = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
CONTRACT_PATH = HERE / "study-contract.json"
BUNDLE_ID = "prose.novel"
QUESTION_SEQUENCE_SHA256 = "22c7c011189072b746eef4cd6aaf0b4da8cb21fd4786e9920593a4e9828602ce"
ROLE_ORDER = ("author_original", "gpt_5_6_pro_rewrite", "public_control_story")
REQUIRED_LEAVES = (
    "penalty.purple_prose.metaphor",
    "core.freshness_and_non_genericness.no_default_metaphors",
    "penalty.purple_prose.proportion",
    "penalty.purple_prose.fatigue",
)
RUNTIME_BINDINGS = {
    "registry/all_modules.json": "12149c9ee556113b1c2865fa8a09a9cb6d60b554a8685219300e48dc1bf52de6",
    "bundles/all_bundles.json": "ca20defa2e3350f949dc9da5e69bb9061d5a0c2d6ddcd71bb9399262dad10f86",
    "bundles/prose.novel.yaml": "96e2b27d4324a368eb3c6cc76bf51ec1b82f02c3a92e8dd6a6e68efad00b9f38",
    "registry/question_index.jsonl": "683f32cffbe4d5f57de288a7c6fab8b79ffa02a6b99635349d2945ed0af1fde0",
    "registry/criterion_ownership.json": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
    "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON object: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def contract() -> dict[str, Any]:
    value = read_object(CONTRACT_PATH)
    if value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("source_head") != HEAD:
        raise ValueError("QPC24 contract identity drift")
    execution = value.get("execution")
    if execution != {
        "provider_free_now": True, "remote_provider_call_count_now": 0,
        "logical_work_evaluations_exact": 15, "questions_per_provider_call": 24,
        "final_remainder_questions": 5, "provider_calls_per_logical_work": 10,
        "planned_provider_calls_exact": 150, "batch_attempts": 1,
        "retry": "forbidden", "resume": "forbidden", "normalization": "forbidden",
        "post_holdout_iteration": "forbidden", "future_execution": "requires_separate_exact_binding_review",
    }:
        raise ValueError("QPC24 batch execution contract drift")
    if value.get("geometry", {}).get("artifact_roles") != list(ROLE_ORDER) or value.get("geometry", {}).get("complete_eligible_question_count") != 221:
        raise ValueError("QPC24 role or eligible-set geometry drift")
    if value.get("eligible_question_set", {}).get("required_figurative_and_owner_leaves") != list(REQUIRED_LEAVES):
        raise ValueError("QPC24 figurative ownership set drift")
    if value.get("runtime_bindings") != RUNTIME_BINDINGS:
        raise ValueError("QPC24 runtime binding contract drift")
    return value


def verify_exact_head_and_bindings() -> dict[str, str]:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode or result.stdout.strip() != HEAD:
        raise ValueError("QPC24 requires exact source HEAD 4ce1204")
    observed: dict[str, str] = {}
    for relative, expected in RUNTIME_BINDINGS.items():
        actual = sha256_bytes((REPOSITORY / relative).read_bytes())
        if actual != expected:
            raise ValueError(f"QPC24 runtime binding drift: {relative}")
        observed[relative] = actual
    return observed


def question_rows() -> list[dict[str, Any]]:
    modules = load_data(REPOSITORY / "registry" / "all_modules.json")
    bundles = load_data(REPOSITORY / "bundles" / "all_bundles.json")
    rows = compiled_questions(compile_bundle(modules, resolve_bundle(bundles, BUNDLE_ID)))
    ids = [str(row["question"]["id"]) for row in rows]
    if len(ids) != 221 or sha256_bytes(canonical(ids)) != QUESTION_SEQUENCE_SHA256:
        raise ValueError("QPC24 complete eligible question sequence drift")
    if not set(REQUIRED_LEAVES).issubset(ids):
        raise ValueError("QPC24 required figurative ownership leaf is absent")
    return rows


def controller(path: Path) -> dict[str, Any]:
    value = read_object(path)
    if value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("source_head") != HEAD:
        raise ValueError("QPC24 controller identity drift")
    if value.get("bundle_id") != BUNDLE_ID or value.get("repetitions_per_role") != 5 or value.get("provider_calls_made") != 0:
        raise ValueError("QPC24 controller execution drift")
    if value.get("whole_work_scope") != contract()["whole_work_scope"]:
        raise ValueError("QPC24 controller whole-work scope drift")
    roles = value.get("roles")
    if not isinstance(roles, list) or [row.get("role") for row in roles if isinstance(row, Mapping)] != list(ROLE_ORDER) or len(roles) != 3:
        raise ValueError("QPC24 controller role order drift")
    clean_roles: list[dict[str, str]] = []
    for row in roles:
        if not isinstance(row, Mapping) or set(row) != {"role", "source_path", "source_sha256", "qpc1_blind_id", "qpc1_artifact_commitment_sha256"}:
            raise ValueError("QPC24 controller role schema drift")
        role, source_path, digest = row["role"], row["source_path"], row["source_sha256"]
        blind_id, qpc1_commitment = row["qpc1_blind_id"], row["qpc1_artifact_commitment_sha256"]
        if not all(isinstance(item, str) and item for item in (role, source_path, digest, blind_id, qpc1_commitment)):
            raise ValueError("QPC24 controller role field is malformed")
        try:
            source_bytes = Path(source_path).read_bytes()
            text = source_bytes.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError("QPC24 controller source is unavailable") from error
        if not text.strip() or sha256_bytes(source_bytes) != digest:
            raise ValueError("QPC24 controller source commitment drift")
        clean_roles.append({"role": role, "source_text": text, "source_sha256": digest, "qpc1_blind_id": blind_id, "qpc1_artifact_commitment_sha256": qpc1_commitment})
    if len({row["source_sha256"] for row in clean_roles}) != len(clean_roles):
        raise ValueError("QPC24 controller sources must be nonduplicate")
    return {"roles": clean_roles}


def schedule(controller_value: Mapping[str, Any]) -> list[dict[str, Any]]:
    questions = question_rows()
    batches = [questions[index:index + 24] for index in range(0, len(questions), 24)]
    if [len(batch) for batch in batches] != [24] * 9 + [5]:
        raise ValueError("QPC24 fixed batch/remainder geometry drift")
    role_map = {row["role"]: row for row in controller_value["roles"]}
    slots: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        for repetition in range(1, 6):
            for batch_number, batch in enumerate(batches, start=1):
                slots.append({"role": role, "repetition": repetition, "batch_number": batch_number, "question_rows": batch, "source_text": role_map[role]["source_text"]})
    if len(slots) != 150 or sum(len(slot["question_rows"]) for slot in slots) != 3315:
        raise ValueError("QPC24 scheduled provider-call count drift")
    return slots


def task_contract(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "contract_id": f"{STUDY_ID}-{slot['role']}-r{slot['repetition']}-b{slot['batch_number']:02d}",
        "artifact_id": f"qpc24-{slot['role']}-r{slot['repetition']}",
        "context": {
            "artifact_kind": "prose.novel",
            "declared_scope": contract()["whole_work_scope"]["whole_work_declared_scope"],
            "completion_status": contract()["whole_work_scope"]["completion_status"],
            "background": ["QPC24 whole-work confirmation; all supplied work is in scope."],
            "constraints": ["Use only the supplied complete work.", "Cite exact source text when evidence is required."],
            "audience": ["development-only rubric validation"],
        },
        "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": [],
    }


def render_slot(slot: Mapping[str, Any]) -> str:
    prompt_parts = [(REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")]
    return runner._render_prompt(
        binary_prompt="\n\n".join(prompt_parts), artifact={"name": "complete-work.txt", "text": slot["source_text"]}, contexts=[],
        bundle_id=BUNDLE_ID, artifact_id=task_contract(slot)["artifact_id"], questions=slot["question_rows"],
        task_contract_context=runner._task_contract_judge_context(task_contract(slot)), provider="codex", model="gpt-5.6-sol",
    )


def validate(controller_path: Path) -> dict[str, Any]:
    bindings = verify_exact_head_and_bindings()
    slots = schedule(controller(controller_path))
    renders: list[dict[str, Any]] = []
    for slot in slots:
        prompt = render_slot(slot)
        question_ids = [row["question"]["id"] for row in slot["question_rows"]]
        if prompt.count('"question_id"') != len(question_ids) or any(question_id not in prompt for question_id in question_ids):
            raise ValueError("QPC24 prompt question partition drift")
        if "WHOLE_WORK: complete supplied work" not in prompt or '"completion_status": "complete"' not in prompt:
            raise ValueError("QPC24 true whole-work scope is not visible in prompt")
        renders.append({"role": slot["role"], "repetition": slot["repetition"], "batch_number": slot["batch_number"], "question_count": len(question_ids), "prompt_sha256": sha256_bytes(prompt.encode("utf-8"))})
    if sum(row["question_count"] for row in renders) != 3315 or sum(row["question_count"] == 5 for row in renders) != 15:
        raise ValueError("QPC24 final-remainder coverage drift")
    return {"study_id": STUDY_ID, "source_head": HEAD, "provider_calls": 0, "logical_work_evaluations": 15, "planned_provider_calls": len(renders), "verdict_positions": 3315, "rendered_schedule_sha256": sha256_bytes(canonical(renders)), "runtime_bindings": bindings, "status": "FROZEN_PROVIDER_FREE_PREEXECUTION"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify",))
    parser.add_argument("--controller", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(validate(args.controller), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
