"""Provider-free, one-shot controller freeze for whole-poem architecture treatment."""
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
PREDECESSOR_ROOT = ROOT.parent / "hbq-poetry-whole-poem-architecture-treatment-v1"
STUDY_ID = "hbq-poetry-whole-poem-architecture-treatment-v1-execution-v1"
PINNED_COMMIT = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
SOURCE_LEAF_ID = "scope.poetry_poem.form"
ARMS = ("current_wording", "candidate_architecture_wording")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
SLOTS = 42


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


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
            raise ValueError(f"Refusing to mutate frozen private artifact: {path.name}")


@lru_cache(maxsize=1)
def predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("whole_poem_architecture_predecessor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Frozen whole-poem treatment predecessor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def _predecessor_files() -> dict[str, str]:
    return {
        "README.md": "e99e361c3a0a495d8c368c0f1b8c1680cebf9771cbe6dcf0fba105bc858867d7",
        "public-synthetic-corpus.json": "21cc24b1e29d72a193853c806eb0d1bf74ca1368c92ea28a5a32aaeb765e5f03",
        "run.py": "b0e6eb1b95f3fb102311fb4872c2f7022e7707d3bcca415aa3702397476da693",
        "study-contract.json": "d74092ddcdd39b14cb4ab20cc4e4116e42625cd691e29fd7b9e8b420497b7f51",
        "study.py": "ac15b24adfc672f829512220419a4c137783296288d9a37f05907eb169f249cb",
    }


def _verify_predecessor() -> None:
    expected = _predecessor_files()
    actual = {name: sha256_file(PREDECESSOR_ROOT / name) for name in expected}
    if actual != expected:
        raise ValueError("Reviewed whole-poem treatment bytes drifted")
    source = predecessor()
    source.verify_package()
    bindings = source.load_contract()["bindings"]
    if bindings["pinned_commit"] != PINNED_COMMIT:
        raise ValueError("Reviewed treatment is not bound to 4ce1204")


def _source_and_candidate() -> tuple[str, str]:
    source = predecessor()
    return str(source.source_leaf()["text"]), str(source.CANDIDATE_TEXT)


def _expected_contract() -> dict[str, Any]:
    source_text, candidate_text = _source_and_candidate()
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_one_shot_execution_successor_unexecuted",
        "development_only": True,
        "privacy": {"provider_facing_artifacts": "public_synthetic_fixtures_and_singleton_prompts_only", "private_root_required": True},
        "predecessor": {
            "path": "evaluation-results/hbq-poetry-whole-poem-architecture-treatment-v1",
            "pinned_commit": PINNED_COMMIT,
            "files": _predecessor_files(),
            "negative_result": {"path": "evaluation-results/hbq-free-verse-necessity-scope-ablation-v1-public-result-v1/aggregate.v1.json", "sha256": "7b21d67529a86313f3b1d4a62c90b22960ac47ec4a57cbb9d49ac05b11c12911", "classification": "VALID_EXECUTION_NEGATIVE_DISCRIMINATION_NO_PROMOTION"},
        },
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "zero_paid_only": True, "api_or_paid_fallback": "forbidden", "provider_calls_authorized_by_this_freeze": False, "one_physical_attempt_per_slot": True, "retry": "forbidden", "replacement": "forbidden", "resampling": "forbidden", "extension": "forbidden", "resume": "forbidden"},
        "geometry": {"fixtures_exact": 7, "controls_exact": 21, "candidate_targets_exact": 21, "repeats_exact": 3, "slots_exact": SLOTS, "schedule_order": "all_current_wording_controls_in_frozen_fixture_repeat_order_then_all_candidate_targets_in_same_order"},
        "wording": {"source_leaf_id": SOURCE_LEAF_ID, "current_wording": source_text, "candidate_wording": candidate_text, "current_wording_sha256": sha256_bytes(source_text.encode("utf-8")), "candidate_wording_sha256": sha256_bytes(candidate_text.encode("utf-8"))},
        "control_gate": {"semantic_expected_labels": "not_recorded", "requires": ["route", "model", "reasoning", "prompt", "fixture", "schema", "grounding", "unique_terminal", "unambiguous_singleton_response"], "technical_failure": "stop_before_candidate_targets"},
        "candidate_gate": {"technical_failure": "one_attempt_consumed_then_stop_TECHNICAL_INCOMPLETE", "semantic_miss": "record_and_continue", "expected_labels": "sealed_private_target_ledger_only"},
        "settlement": {"requires_all_42_valid_terminals": True, "go": "GO_TO_BROADER_VALIDATION iff candidate_21_of_21_correct and at_least_one_stable_3_of_3_arm_gap", "no_clear_discrimination": "NO_GO_NO_CLEAR_DISCRIMINATION iff candidate_21_of_21_correct and no_stable_3_of_3_arm_gap", "no_candidate": "NO_GO_CANDIDATE iff any_candidate_cell_misses_3_of_3", "technical_incomplete": "no_semantic_decision"},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "merge", "weight", "execution")},
    }


@lru_cache(maxsize=1)
def validate_package() -> dict[str, Any]:
    _verify_predecessor()
    if contract() != _expected_contract():
        raise ValueError("Execution successor contract drifted")
    slots = build_schedule()
    if len(slots) != SLOTS or len({row["slot_id"] for row in slots}) != SLOTS:
        raise ValueError("Exact 42-slot singleton schedule drifted")
    if [row["arm"] for row in slots[:21]] != ["current_wording"] * 21 or [row["arm"] for row in slots[21:]] != ["candidate_architecture_wording"] * 21:
        raise ValueError("Control-first execution order drifted")
    return {"study_id": STUDY_ID, "status": contract()["status"], "provider_calls": 0, "slots": SLOTS}


def _prompt(leaf_text: str, case: Mapping[str, Any]) -> str:
    return "\n\n".join((
        "HBQ-RS direct-only singleton validation. Use only the supplied public synthetic artifact.",
        f"Declared scope: {case['declared_scope']}. Completion status: {case['completion_status']}.",
        f"Question ID: {SOURCE_LEAF_ID}\nQuestion: {leaf_text}",
        f"Artifact ({case['artifact_name']}):\n{case['text']}",
        "Return one schema-valid HBQ-RS verdict with one or more nonempty exact-quote evidence items from this artifact. Do not evaluate any other criterion.",
    ))


@lru_cache(maxsize=1)
def build_schedule() -> tuple[dict[str, Any], ...]:
    source = predecessor()
    corpus = source.load_corpus()
    source.verify_corpus(corpus)
    source_text, candidate_text = _source_and_candidate()
    rows: list[dict[str, Any]] = []
    for arm, leaf_text in ((ARMS[0], source_text), (ARMS[1], candidate_text)):
        for case in corpus["cases"]:
            for repeat in range(1, 4):
                prompt = _prompt(leaf_text, case)
                rows.append({
                    "slot_id": f"whole-poem-architecture-exec-v1-{len(rows) + 1:03d}",
                    "case_id": case["case_id"],
                    "arm": arm,
                    "repeat": repeat,
                    "artifact_name": case["artifact_name"],
                    "artifact_text": case["text"],
                    "fixture_sha256": sha256_bytes(case["text"].encode("utf-8")),
                    "prompt": prompt,
                    "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                })
    expected = [(case["case_id"], repeat) for case in corpus["cases"] for repeat in range(1, 4)]
    if [(row["case_id"], row["repeat"]) for row in rows[:21]] != expected or [(row["case_id"], row["repeat"]) for row in rows[21:]] != expected:
        raise ValueError("Frozen fixture/repeat order drifted")
    return tuple(rows)


def public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "case_id", "arm", "repeat", "artifact_name", "fixture_sha256", "prompt_sha256")}


def _manifest(schedule: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "provider_calls": 0, "slots": [public_slot(row) for row in schedule], "prompt_aggregate_sha256": sha256_bytes(canonical_json({row["slot_id"]: row["prompt_sha256"] for row in schedule}))}


def _candidate_ledger() -> dict[str, Any]:
    cases = predecessor().load_corpus()["cases"]
    return {"format_version": 1, "study_id": STUDY_ID, "sealed": True, "rows": [{"case_id": case["case_id"], "expected_verdict": case["candidate_expected"]} for case in cases]}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validation = validate_package()
    root = _external_root(private_root)
    schedule = build_schedule()
    for slot in schedule:
        _write_immutable(root / "inputs" / f"{slot['slot_id']}.txt", slot["artifact_text"].encode("utf-8"))
        _write_immutable(root / "rendered-prompts" / f"{slot['slot_id']}.txt", slot["prompt"].encode("utf-8"))
    _write_immutable(root / "controller-manifest.json", canonical_json(_manifest(schedule)))
    _write_immutable(root / "sealed-candidate-ledger.v1.json", canonical_json(_candidate_ledger()))
    _write_immutable(root / "settlement-plan.v1.json", canonical_json({"format_version": 1, "study_id": STUDY_ID, "valid_terminals_required": SLOTS, "promotion": "none", "technical_incomplete_has_no_semantic_decision": True}))
    _write_immutable(root / "operator-instructions.md", b"This controller is receipt-only: it never contacts a provider. Claim one frozen slot, retain one terminal receipt, and record it exactly once. Controls must all be technically valid before targets begin. Do not retry, replace, resample, extend, or resume.\n")
    return {**validation, "private_root": str(root), "rendered_prompts": SLOTS, "provider_calls": 0}


def _prepared(private_root: str | Path) -> tuple[Path, tuple[dict[str, Any], ...]]:
    root = _external_root(private_root)
    schedule = build_schedule()
    validate_package()
    if load_json(root / "controller-manifest.json") != _manifest(schedule):
        raise ValueError("Prepared controller manifest drifted")
    if load_json(root / "sealed-candidate-ledger.v1.json") != _candidate_ledger():
        raise ValueError("Sealed candidate ledger drifted")
    _verify_prepared_slot_bytes(root, schedule)
    return root, schedule


def _verify_prepared_slot_bytes(root: Path, schedule: tuple[dict[str, Any], ...]) -> None:
    expected = {f"{slot['slot_id']}.txt" for slot in schedule}
    for directory, key in (("inputs", "artifact_text"), ("rendered-prompts", "prompt")):
        actual = {path.name for path in (root / directory).glob("*.txt") if path.is_file()}
        if actual != expected or len(actual) != SLOTS:
            raise ValueError(f"Prepared {directory} filename set drifted")
        for slot in schedule:
            if (root / directory / f"{slot['slot_id']}.txt").read_bytes() != str(slot[key]).encode("utf-8"):
                raise ValueError(f"Prepared {directory} bytes drifted")


def _slot(schedule: tuple[dict[str, Any], ...], slot_id: str) -> tuple[int, dict[str, Any]]:
    for index, value in enumerate(schedule):
        if value["slot_id"] == slot_id:
            return index, value
    raise ValueError("Unknown frozen slot")


def _terminal(root: Path, slot_id: str) -> Path:
    return root / "terminals" / f"{slot_id}.json"


def _validated_terminal(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    terminal = load_json(_terminal(root, str(slot["slot_id"])))
    common = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot["slot_id"], "attempt": 1}
    if any(terminal.get(key) != value for key, value in common.items()):
        raise ValueError("Terminal identity drifted")
    if terminal.get("state") == "terminal_technical_failure":
        if set(terminal) != {*common, "state", "reason"} or not isinstance(terminal["reason"], str) or not terminal["reason"].strip():
            raise ValueError("Technical terminal shape drifted")
        return terminal
    if terminal.get("state") != "terminal_valid" or set(terminal) != {*common, "state", "response_sha256", "receipt", "payload", "verdict"}:
        raise ValueError("Terminal shape drifted")
    payload = terminal["payload"]
    if terminal["response_sha256"] != sha256_bytes(canonical_json(payload)):
        raise ValueError("Terminal response hash drifted")
    if not isinstance(terminal["receipt"], Mapping):
        raise ValueError("Terminal receipt shape drifted")
    verdict = _validate_response(slot, terminal["receipt"], payload)
    if terminal["verdict"] != verdict:
        raise ValueError("Terminal verdict projection drifted")
    return terminal


def claim_slot(private_root: str | Path, slot_id: str) -> dict[str, Any]:
    root, schedule = _prepared(private_root)
    index, slot = _slot(schedule, slot_id)
    if (root / "claims" / f"{slot_id}.json").exists() or _terminal(root, slot_id).exists():
        raise ValueError("One physical attempt is already claimed or terminal; retry/resume is forbidden")
    for prior in schedule[:index]:
        if not _terminal(root, prior["slot_id"]).is_file() or _validated_terminal(root, prior).get("state") != "terminal_valid":
            raise ValueError("Frozen sequence requires each prior control/target terminal to be valid")
    claim = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot_id, "attempt": 1, "state": "claimed_before_contact", "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "prompt_sha256": slot["prompt_sha256"], "fixture_sha256": slot["fixture_sha256"]}
    _write_immutable(root / "claims" / f"{slot_id}.json", canonical_json(claim))
    return claim


def _validate_response(slot: Mapping[str, Any], receipt: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    if {key: receipt.get(key) for key in ("route", "model", "reasoning", "prompt_sha256", "fixture_sha256")} != {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "prompt_sha256": slot["prompt_sha256"], "fixture_sha256": slot["fixture_sha256"]}:
        raise ValueError("Route/model/reasoning/prompt/fixture receipt drifted")
    errors = sorted(Draft202012Validator(predecessor().load_json(REPOSITORY / "schema" / "hbq_judge_response.schema.json")).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        raise ValueError("Response is not schema-valid")
    verdicts = payload.get("verdicts")
    if not isinstance(verdicts, list) or len(verdicts) != 1 or verdicts[0].get("question_id") != SOURCE_LEAF_ID or verdicts[0].get("verdict") not in VERDICTS:
        raise ValueError("Response is not an unambiguous singleton terminal")
    quotes = [item.get("exact_quote") for item in verdicts[0].get("evidence", []) if isinstance(item, dict) and item.get("kind") == "exact_quote" and isinstance(item.get("exact_quote"), str) and item["exact_quote"].strip()]
    if not quotes or any(quote not in slot["artifact_text"] for quote in quotes):
        raise ValueError("Response lacks fixture-grounded exact evidence")
    return deepcopy(verdicts[0])


def record_response(private_root: str | Path, slot_id: str, receipt: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    root, schedule = _prepared(private_root)
    _, slot = _slot(schedule, slot_id)
    if not (root / "claims" / f"{slot_id}.json").is_file() or _terminal(root, slot_id).exists():
        raise ValueError("Exactly one prior claim and no terminal are required")
    try:
        verdict = _validate_response(slot, receipt, payload)
    except ValueError as exc:
        terminal = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot_id, "attempt": 1, "state": "terminal_technical_failure", "reason": str(exc)}
        _write_immutable(_terminal(root, slot_id), canonical_json(terminal))
        return terminal
    terminal = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot_id, "attempt": 1, "state": "terminal_valid", "response_sha256": sha256_bytes(canonical_json(payload)), "receipt": dict(receipt), "payload": payload, "verdict": verdict}
    _write_immutable(_terminal(root, slot_id), canonical_json(terminal))
    return terminal


def record_technical_failure(private_root: str | Path, slot_id: str, reason: str) -> dict[str, Any]:
    root, schedule = _prepared(private_root)
    _slot(schedule, slot_id)
    if not reason.strip() or not (root / "claims" / f"{slot_id}.json").is_file() or _terminal(root, slot_id).exists():
        raise ValueError("A claimed unterminated slot and nonempty reason are required")
    terminal = {"format_version": 1, "study_id": STUDY_ID, "slot_id": slot_id, "attempt": 1, "state": "terminal_technical_failure", "reason": reason}
    _write_immutable(_terminal(root, slot_id), canonical_json(terminal))
    return terminal


def technical_status(private_root: str | Path) -> dict[str, Any]:
    root, schedule = _prepared(private_root)
    terminals = {slot["slot_id"]: _validated_terminal(root, slot) for slot in schedule if _terminal(root, slot["slot_id"]).is_file()}
    invalid = [slot_id for slot_id, terminal in terminals.items() if terminal["state"] != "terminal_valid"]
    complete = sum(terminal["state"] == "terminal_valid" for terminal in terminals.values())
    return {"study_id": STUDY_ID, "status": "TECHNICAL_INCOMPLETE" if invalid or complete != SLOTS else "TECHNICALLY_COMPLETE", "valid_terminals": complete, "planned_slots": SLOTS, "failed_slot_ids": invalid}


def classify(candidate_correct: Mapping[str, list[bool]], control_values: Mapping[str, list[str]], candidate_values: Mapping[str, list[str]]) -> tuple[str, list[str]]:
    if set(candidate_correct) != set(control_values) or set(candidate_correct) != set(candidate_values) or any(len(values) != 3 for values in [*candidate_correct.values(), *control_values.values(), *candidate_values.values()]):
        raise ValueError("Exact seven three-repeat arm geometry is required")
    candidate_all = all(all(values) for values in candidate_correct.values()) and sum(map(len, candidate_correct.values())) == 21
    stable_gap_cases = sorted(case_id for case_id in candidate_correct if len(set(control_values[case_id])) == 1 and len(set(candidate_values[case_id])) == 1 and control_values[case_id][0] != candidate_values[case_id][0])
    if candidate_all:
        return ("GO_TO_BROADER_VALIDATION" if stable_gap_cases else "NO_GO_NO_CLEAR_DISCRIMINATION", stable_gap_cases)
    return "NO_GO_CANDIDATE", stable_gap_cases


def settle(private_root: str | Path) -> dict[str, Any]:
    root, schedule = _prepared(private_root)
    status = technical_status(root)
    if status["status"] != "TECHNICALLY_COMPLETE":
        raise ValueError("Settlement requires all 42 valid terminals; technical incompleteness has no semantic decision")
    ledger = load_json(root / "sealed-candidate-ledger.v1.json")["rows"]
    expected = {row["case_id"]: row["expected_verdict"] for row in ledger}
    terminals = {slot["slot_id"]: _validated_terminal(root, slot) for slot in schedule}
    candidate_correct: dict[str, list[bool]] = {}
    control_values: dict[str, list[str]] = {}
    candidate_values: dict[str, list[str]] = {}
    for slot in schedule:
        verdict = str(terminals[slot["slot_id"]]["verdict"]["verdict"])
        if slot["arm"] == ARMS[0]:
            control_values.setdefault(slot["case_id"], []).append(verdict)
        else:
            candidate_values.setdefault(slot["case_id"], []).append(verdict)
            candidate_correct.setdefault(slot["case_id"], []).append(verdict == expected[slot["case_id"]])
    decision, stable_gap_cases = classify(candidate_correct, control_values, candidate_values)
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "planned_slots": SLOTS, "valid_terminals": SLOTS, "candidate_correct": sum(sum(values) for values in candidate_correct.values()), "candidate_total": 21, "stable_3_of_3_arm_gap_case_ids": stable_gap_cases, "promotion": "none"}
    _write_immutable(root / "settlement.v1.json", canonical_json(settlement))
    return settlement
