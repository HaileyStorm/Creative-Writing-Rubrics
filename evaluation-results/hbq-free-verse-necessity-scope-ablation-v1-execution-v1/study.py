"""Zero-call lifecycle planner for the reviewed necessity/scope ablation."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-free-verse-necessity-scope-ablation-v1"
STUDY_ID = "hbq-free-verse-necessity-scope-ablation-v1-execution-v1"
PREDECESSOR_PARENT = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
LEAVES = ("form.poetry.free_verse.necessity", "scope.poetry_poem.form")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
SLOTS = 36


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_prompt_bytes(value: str) -> bytes:
    raw = value.encode("utf-8")
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError("Prompt contains a lone CR byte")
    return raw.replace(b"\r\n", b"\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def _external_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        return root
    raise ValueError("private_root must be outside the CWR checkout")


def _write_immutable(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(value)
    except FileExistsError:
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate immutable private artifact: {path.name}")


@lru_cache(maxsize=1)
def predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("necessity_scope_ablation_predecessor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Reviewed predecessor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _verify_predecessor_bytes() -> None:
    binding = contract()["predecessor"]
    if binding["path"] != "evaluation-results/hbq-free-verse-necessity-scope-ablation-v1" or binding["reviewed_parent_commit"] != PREDECESSOR_PARENT:
        raise ValueError("Reviewed predecessor identity drifted")
    actual = {name: sha256_file(PREDECESSOR_ROOT / name) for name in binding["files"]}
    if actual != binding["files"]:
        raise ValueError("GO-reviewed predecessor bytes drifted")


@lru_cache(maxsize=1)
def build_schedule() -> tuple[dict[str, Any], ...]:
    source = predecessor()
    source.verify_package()
    artifacts = source.materialize_artifacts()
    rows: list[dict[str, Any]] = []
    for source_slot in source.plan_slots():
        request = source.provider_request(source_slot["slot_id"])
        leaf_id = source_slot["leaf_id"]
        if leaf_id not in LEAVES or request["leaf_id"] != leaf_id:
            raise ValueError("Predecessor one-leaf request drifted")
        prompt = str(request["prompt"])
        other_leaf = next(item for item in LEAVES if item != leaf_id)
        if leaf_id not in prompt or other_leaf in prompt:
            raise ValueError("Rendered request is not a singleton leaf prompt")
        artifact = artifacts[source_slot["case_id"]]
        rows.append({
            "slot_id": f"necessity-scope-exec-v1-{len(rows) + 1:03d}",
            "source_slot_id": source_slot["slot_id"],
            "case_id": source_slot["case_id"],
            "leaf_id": leaf_id,
            "repeat": source_slot["repeat"],
            "artifact_name": artifact["artifact_name"],
            "artifact_text": artifact["text"],
            "prompt": prompt,
            "prompt_sha256": sha256_bytes(canonical_prompt_bytes(prompt)),
        })
    expected = {(case_id, leaf_id, repeat) for case_id in source.EXPECTED for leaf_id in LEAVES for repeat in range(1, 4)}
    actual = {(row["case_id"], row["leaf_id"], row["repeat"]) for row in rows}
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS or actual != expected:
        raise ValueError("Exact 6 by 2 by 3 singleton schedule drifted")
    return tuple(rows)


def public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "source_slot_id", "case_id", "leaf_id", "repeat", "artifact_name", "prompt_sha256")}


def prompt_aggregate(schedule: tuple[dict[str, Any], ...] | None = None) -> str:
    schedule = build_schedule() if schedule is None else schedule
    return sha256_bytes(canonical_json({row["slot_id"]: row["prompt_sha256"] for row in schedule}))


def schema() -> dict[str, Any]:
    source = predecessor()
    raw = source.git_show_bytes("schema/hbq_judge_response.schema.json")
    return json.loads(raw.decode("utf-8"))


def validate_package() -> dict[str, Any]:
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_zero_call_execution_successor_unexecuted",
        "predecessor": contract()["predecessor"],
        "execution": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "selector": "exact", "zero_paid_only": True, "paid_fallback": "forbidden", "one_leaf_per_request": True, "one_physical_attempt_per_slot": True, "claim_before_contact": True, "retry_or_resume_after_claim": "forbidden", "provider_calls_authorized_by_this_freeze": False},
        "geometry": {"conditions_exact": 6, "leaves_per_condition_exact": 2, "repeats_exact": 3, "slots_exact": SLOTS},
        "prompt_commitment": contract()["prompt_commitment"],
        "validation": {"schema_path": "schema/hbq_judge_response.schema.json", "schema_git_show_sha256": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854", "exact_single_verdict": True, "question_id_must_match_singleton_leaf": True, "evidence": "at_least_one_nonempty_exact_quote_must_be_a_substring_of_the_supplied_artifact"},
        "terminal_settlement": {"terminal_record": "immutable_after_one_claim", "settlement": "immutable_after_all_36_schema_and_evidence_valid_terminals", "publication": "aggregate_only", "expected_ledger_opened_by_executor": False, "decision": "external_review_required"},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "merge", "weight")},
    }
    if contract() != expected:
        raise ValueError("Execution successor contract drifted")
    _verify_predecessor_bytes()
    source = predecessor()
    if sha256_bytes(source.git_show_bytes("schema/hbq_judge_response.schema.json")) != contract()["validation"]["schema_git_show_sha256"]:
        raise ValueError("Pinned response schema drifted")
    schedule = build_schedule()
    if prompt_aggregate(schedule) != contract()["prompt_commitment"]["rendered_prompt_aggregate_sha256"]:
        raise ValueError("Exact rendered prompt aggregate drifted")
    return {"study_id": STUDY_ID, "status": contract()["status"], "provider_calls": 0, "slots": SLOTS, "prompt_aggregate_sha256": prompt_aggregate(schedule)}


def _manifest(schedule: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "provider_calls": 0, "slots": [public_slot(row) for row in schedule], "prompt_aggregate_sha256": prompt_aggregate(schedule)}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validation = validate_package()
    root = _external_root(private_root)
    schedule = build_schedule()
    for row in schedule:
        _write_immutable(root / "rendered-prompts" / f"{row['slot_id']}.txt", canonical_prompt_bytes(row["prompt"]))
        _write_immutable(root / "inputs" / f"{row['slot_id']}.txt", row["artifact_text"].encode("utf-8"))
    _write_immutable(root / "study-manifest.json", canonical_json(_manifest(schedule)))
    _write_immutable(root / "terminal-settlement-plan.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "claim_before_contact": True, "retry_or_resume_after_claim": "forbidden", "required_terminal_slots": [row["slot_id"] for row in schedule], "publication": "aggregate_only", "promotion": "none"}))
    return {**validation, "private_root": str(root), "rendered_prompts": SLOTS, "terminal_records": 0}


def _validated_private_root(private_root: str | Path) -> tuple[Path, tuple[dict[str, Any], ...]]:
    root = _external_root(private_root)
    validation = validate_package()
    schedule = build_schedule()
    if load_json(root / "study-manifest.json") != _manifest(schedule):
        raise ValueError("Prepared manifest drifted; prepare again in a new private root")
    if validation["provider_calls"] != 0:
        raise ValueError("Zero-call preparation invariant drifted")
    return root, schedule


def claim_slot(private_root: str | Path, slot_id: str) -> dict[str, Any]:
    root, schedule = _validated_private_root(private_root)
    slot = next((row for row in schedule if row["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    if (root / "terminals" / f"{slot_id}.json").exists() or (root / "claims" / f"{slot_id}.json").exists():
        raise ValueError("Claim already terminal or claimed; retry/resume is forbidden")
    claim = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot_id, "attempt": 1, "state": "claimed_before_contact", "prompt_sha256": slot["prompt_sha256"], "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}
    _write_immutable(root / "claims" / f"{slot_id}.json", canonical_json(claim))
    return claim


def validate_response(slot: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    errors = sorted(Draft202012Validator(schema()).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        raise ValueError("Response is not schema-valid")
    verdicts = payload["verdicts"]
    if len(verdicts) != 1 or verdicts[0]["question_id"] != slot["leaf_id"] or verdicts[0]["verdict"] not in VERDICTS:
        raise ValueError("Response does not bind exactly one expected singleton leaf")
    exact_quotes = [item["exact_quote"] for item in verdicts[0]["evidence"] if item["kind"] == "exact_quote" and isinstance(item["exact_quote"], str) and item["exact_quote"].strip()]
    if not exact_quotes or any(quote not in slot["artifact_text"] for quote in exact_quotes):
        raise ValueError("Response lacks artifact-grounded exact evidence")
    return deepcopy(verdicts[0])


def record_terminal(private_root: str | Path, slot_id: str, payload: Any) -> dict[str, Any]:
    root, schedule = _validated_private_root(private_root)
    slot = next((row for row in schedule if row["slot_id"] == slot_id), None)
    if slot is None or not (root / "claims" / f"{slot_id}.json").is_file():
        raise ValueError("A claim is required before terminal recording")
    verdict = validate_response(slot, payload)
    terminal = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot_id, "attempt": 1, "state": "terminal_schema_and_evidence_valid", "prompt_sha256": slot["prompt_sha256"], "response_sha256": sha256_bytes(canonical_json(payload)), "verdict": verdict}
    _write_immutable(root / "terminals" / f"{slot_id}.json", canonical_json(terminal))
    return terminal


def settle(private_root: str | Path) -> dict[str, Any]:
    root, schedule = _validated_private_root(private_root)
    terminals: list[dict[str, Any]] = []
    for row in schedule:
        path = root / "terminals" / f"{row['slot_id']}.json"
        if not path.is_file():
            raise ValueError("All claimed slots require immutable valid terminals before settlement")
        terminals.append(load_json(path))
    aggregate = dict(sorted(Counter(item["verdict"]["verdict"] for item in terminals).items()))
    settlement = {"format_version": 1, "study_id": STUDY_ID, "planned_slots": SLOTS, "terminal_slots": SLOTS, "aggregate_verdict_counts": aggregate, "expected_ledger_opened_by_executor": False, "publication": "aggregate_only", "decision": "external_review_required", "promotion": "none"}
    _write_immutable(root / "settlement.v1.json", canonical_json(settlement))
    return settlement
