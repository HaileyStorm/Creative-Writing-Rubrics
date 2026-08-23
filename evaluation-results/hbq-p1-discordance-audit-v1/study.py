"""Freeze a private, provider-disabled audit plan for P1 raw discordances."""
from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-p1-discordance-audit-v1"
SOURCE_STUDY_ID = "hbq-polarity-change-manual-treatment-holdout-v1-execution-v1"
ARMS = ("CURRENT", "TREATMENT")
TARGET_FIXTURES = tuple(f"H{ordinal:02d}" for ordinal in range(1, 17))
SOURCE_PRIVATE_CORPUS_SHA256 = "2baff4dcd7c96054cd6208bd61b243a4435f15de323c42db152702dc2299ff1b"
SOURCE_LEDGER_SHA256 = "231448f3bbcfcd88f12ed4cf8510c16ddd48d907cc203d3a99d6ba62893536e9"
CANDIDATE_APPENDIX_SHA256 = "00ce0c5f1063c1fb36cc663bd2c522ce5eda254ee8f9079ec21774277e0d3722"
APPENDIX_PROMPT_DELTA_SHA256 = "2c5143d87dc42afe3224a51c06250b1defdac98e6bede7d94f2f11a9d530864e"
MECHANISM_CLASSIFICATIONS = (
    "FIXTURE_OR_LEDGER_AMBIGUITY",
    "SAME_INPUT_VARIANCE",
    "EVIDENCE_OR_VALIDATOR_DEFECT",
    "APPENDIX_HARM",
    "SHARED_PROMPT_GAP",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return digest(path.read_bytes())


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def frozen(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != value:
        raise ValueError(f"Refusing to mutate frozen artifact: {path.name}")
    if not path.exists():
        path.write_bytes(value)


def private_root(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    if REPOSITORY.resolve() in resolved.parents or resolved == REPOSITORY.resolve():
        raise ValueError("private root must be outside the CWR checkout")
    return resolved


def contract() -> dict[str, Any]:
    value = load(ROOT / "study-contract.json")
    if not isinstance(value, dict):
        raise ValueError("audit contract must be an object")
    return value


def validate_package() -> dict[str, Any]:
    value = contract()
    if value.get("study_id") != STUDY_ID or value.get("mode") != "provider_free_freeze_only":
        raise ValueError("audit contract identity drifted")
    selection = value.get("selection")
    review = value.get("review_plan")
    privacy = value.get("privacy")
    if selection != {"rule": "every target fixture with any wrong raw slot in either arm", "maximum_unique_fixtures": 1, "receipts_per_fixture": 6}:
        raise ValueError("audit selection contract drifted")
    expected_review = {
        "reviews_per_fixture": 2, "maximum_provider_calls": 2, "model": "gpt-5.6-sol", "reasoning": "high",
        "batch_size": 1, "physical_attempts_per_review": 1, "retries": 0, "zero_incremental_charge_only": True, "paid_fallback_forbidden": True, "attempt_lifecycle_policy": "terminal_sidecar_v1",
        "provider_execution_enabled": False, "dspy_enabled": False, "mechanism_classifications": list(MECHANISM_CLASSIFICATIONS),
    }
    arming = {"provider_free": True, "explicit_confirmation_required": True, "arming_receipt_required_before_execution": True, "execution_state_written_after_exact_two_calls": True}
    if review != expected_review or value.get("arming") != arming or privacy != {"public_projection": "aggregate_only", "state_review_hides": ["label", "verdicts", "arm", "appendix", "session"], "source_private_root_recorded": False}:
        raise ValueError("audit review or privacy contract drifted")
    if value.get("appendix_disposition") != "FAILED_APPENDIX_RETIRED_NOT_REUSABLE" or value.get("drift_status") != "INCOMPLETE":
        raise ValueError("appendix or drift disposition changed")
    return {"study_id": STUDY_ID, "provider_calls": 0, "execution_enabled": False}


def _source_json(root: Path, name: str) -> Mapping[str, Any]:
    value = load(root / name)
    if not isinstance(value, Mapping):
        raise ValueError(f"source {name} must be an object")
    return value


def _normalize_prompt(path: Path) -> str:
    return gzip.decompress(path.read_bytes()).decode("utf-8").replace("\r\n", "\n")


def _terminal_receipt(run: Path) -> dict[str, str]:
    terminal = run / "responses" / "attempt-lifecycle" / "batch-0001"
    start = terminal / "attempt-0001.start.json"
    settled = terminal / "attempt-0001.settled.json"
    if not start.is_file() or not settled.is_file():
        raise ValueError("receipt terminal lifecycle is incomplete")
    start_value, settled_value = load(start), load(settled)
    if not isinstance(start_value, Mapping) or not isinstance(settled_value, Mapping):
        raise ValueError("receipt terminal lifecycle is malformed")
    if settled_value.get("outcome") != "accepted" or settled_value.get("attempt") != 1 or settled_value.get("policy") != "terminal_sidecar_v1" or settled_value.get("state") != "settled":
        raise ValueError("receipt is not a first-attempt accepted terminal")
    return {"start_sha256": sha(start), "settled_sha256": sha(settled)}


def _source_receipt(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    slot_id = slot.get("slot_id")
    if not isinstance(slot_id, str):
        raise ValueError("source slot identifier is malformed")
    run = root / "runs" / slot_id
    manifest = _source_json(run, "run.json")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ValueError("receipt configuration is missing")
    required_configuration = {
        "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1,
        "attempt_lifecycle_policy": "terminal_sidecar_v1", "artifact_id": slot.get("artifact_id"),
        "judge_id": slot.get("judge_id"), "question_ids": [slot.get("leaf_id")],
    }
    if {key: configuration.get(key) for key in required_configuration} != required_configuration or configuration.get("retry_policy") != {"batch_attempts": 3}:
        raise ValueError("receipt model or singleton binding drifted")
    verdict_lines = (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()
    if len(verdict_lines) != 1:
        raise ValueError("receipt is not singleton")
    verdict = json.loads(verdict_lines[0])
    if not isinstance(verdict, Mapping) or verdict.get("question_id") != slot.get("leaf_id") or verdict.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}:
        raise ValueError("receipt verdict drifted")
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("receipt evidence is absent")
    response = _source_json(run / "responses", "batch-0001.json")
    reported = response.get("provider", {}).get("reported", {}) if isinstance(response.get("provider"), Mapping) else {}
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("receipt provider report drifted")
    session = reported.get("session_id")
    if not isinstance(session, str) or not session:
        raise ValueError("receipt session is absent")
    prompt = _normalize_prompt(run / "responses" / "batch-0001.prompt.txt.gz")
    return {
        "source_slot_sha256": digest(canonical({key: slot[key] for key in ("slot_id", "fixture_id", "artifact_id", "leaf_id", "arm", "repeat", "judge_id")})),
        "prompt": prompt,
        "prompt_sha256": digest(prompt.encode("utf-8")),
        "verdict": verdict["verdict"],
        "evidence": evidence,
        "evidence_sha256": digest(canonical(evidence)),
        "model": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
        "terminal": _terminal_receipt(run),
        "response_sha256": sha(run / "responses" / "batch-0001.json"),
        "verdict_sha256": sha(run / "verdicts.jsonl"),
        "session_sha256": digest(session.encode("utf-8")),
    }


def _raw_verdict(root: Path, slot: Mapping[str, Any]) -> str:
    slot_id, leaf_id = slot.get("slot_id"), slot.get("leaf_id")
    if not isinstance(slot_id, str) or not isinstance(leaf_id, str):
        raise ValueError("source slot verdict binding is malformed")
    lines = (root / "runs" / slot_id / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise ValueError("source raw verdict is not singleton")
    value = json.loads(lines[0])
    if not isinstance(value, Mapping) or value.get("question_id") != leaf_id or value.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}:
        raise ValueError("source raw verdict drifted")
    return str(value["verdict"])


def _fixture_texts(corpus: Mapping[str, Any]) -> dict[str, str]:
    fixtures = corpus.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 20:
        raise ValueError("source corpus fixture geometry drifted")
    result: dict[str, str] = {}
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise ValueError("source corpus fixture is malformed")
        fixture_id, text = fixture.get("fixture_id"), fixture.get("text")
        if not isinstance(fixture_id, str) or not isinstance(text, str) or not text:
            raise ValueError("source corpus fixture text is malformed")
        result[fixture_id] = text
    if set(result) != {f"H{ordinal:02d}" for ordinal in range(1, 21)}:
        raise ValueError("source corpus fixture identities drifted")
    return result


def _question_records() -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    index = REPOSITORY / "registry" / "question_index.jsonl"
    for line in index.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, Mapping) and isinstance(value.get("id"), str):
            result[value["id"]] = value
    return result


def _difference(left: str, right: str) -> str:
    return "".join(difflib.unified_diff(left.splitlines(keepends=True), right.splitlines(keepends=True), fromfile="variant-a", tofile="variant-b", lineterm=""))


def _appendix_delta(root: Path) -> tuple[str, str, str]:
    current = (root / "runtime-book" / "current" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")
    treatment = (root / "runtime-book" / "treatment" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")
    if not treatment.startswith(current):
        raise ValueError("treatment prompt is not a current-prompt extension")
    delta = treatment[len(current):]
    if digest(delta) != APPENDIX_PROMPT_DELTA_SHA256 or digest(delta.lstrip(b"\n")) != CANDIDATE_APPENDIX_SHA256:
        raise ValueError("retired appendix or exact prompt delta drifted")
    return current.decode("utf-8"), treatment.decode("utf-8"), delta.decode("utf-8")


def _source_analysis(source_root: str | Path) -> dict[str, Any]:
    root = private_root(source_root)
    validate_package()
    corpus_path, ledger_path = root / "private-corpus.json", root / "sealed-expected-ledger.json"
    if sha(corpus_path) != SOURCE_PRIVATE_CORPUS_SHA256 or sha(ledger_path) != SOURCE_LEDGER_SHA256:
        raise ValueError("source corpus or ledger commitment drifted")
    corpus, ledger = _source_json(root, "private-corpus.json"), _source_json(root, "sealed-expected-ledger.json")
    if corpus.get("study_id") != SOURCE_STUDY_ID or ledger.get("study_id") != SOURCE_STUDY_ID:
        raise ValueError("source study identity drifted")
    expected = ledger.get("expected")
    if not isinstance(expected, Mapping) or set(expected) != set(TARGET_FIXTURES) | {"H17", "H18", "H19", "H20"}:
        raise ValueError("source ledger coverage drifted")
    fixture_text = _fixture_texts(corpus)
    schedule_value = load(root / "runtime-schedule.json")
    slots = schedule_value.get("slots") if isinstance(schedule_value, Mapping) else None
    if not isinstance(slots, list) or len(slots) != 120:
        raise ValueError("source schedule geometry drifted")
    by_fixture: dict[str, list[tuple[Mapping[str, Any], dict[str, Any]]]] = defaultdict(list)
    expected_pairs = {(fixture, arm, repeat) for fixture in fixture_text for arm in ARMS for repeat in range(1, 4)}
    actual_pairs: set[tuple[str, str, int]] = set()
    for slot in slots:
        if not isinstance(slot, Mapping):
            raise ValueError("source schedule slot is malformed")
        fixture, arm, repeat = slot.get("fixture_id"), slot.get("arm"), slot.get("repeat")
        if not isinstance(fixture, str) or arm not in ARMS or not isinstance(repeat, int):
            raise ValueError("source schedule slot binding drifted")
        actual_pairs.add((fixture, arm, repeat))
        by_fixture[fixture].append((slot, {}))
    if actual_pairs != expected_pairs or set(by_fixture) != set(fixture_text):
        raise ValueError("source schedule pairing drifted")
    base_binary, treatment_binary, appendix_delta = _appendix_delta(root)
    candidates: list[dict[str, Any]] = []
    question_records = _question_records()
    for fixture in TARGET_FIXTURES:
        scheduled_rows = by_fixture[fixture]
        if len(scheduled_rows) != 6:
            raise ValueError("source fixture does not have six receipts")
        raw_verdicts = {_raw_verdict(root, slot) for slot, _ in scheduled_rows}
        if any(verdict != expected[fixture] for verdict in raw_verdicts):
            rows = [(slot, _source_receipt(root, slot)) for slot, _ in scheduled_rows]
            leaves = {str(slot.get("leaf_id")) for slot, _ in rows}
            if len(leaves) != 1 or next(iter(leaves)) not in question_records:
                raise ValueError("source criterion binding drifted")
            ordered = sorted(rows, key=lambda item: (str(item[0]["arm"]), int(item[0]["repeat"])))
            variants = {arm: [receipt for slot, receipt in ordered if slot["arm"] == arm] for arm in ARMS}
            if any(len(variants[arm]) != 3 for arm in ARMS):
                raise ValueError("source A/B receipt geometry drifted")
            current_prompts, treatment_prompts = {item["prompt"] for item in variants["CURRENT"]}, {item["prompt"] for item in variants["TREATMENT"]}
            if len(current_prompts) != 1 or len(treatment_prompts) != 1:
                raise ValueError("source prompt repetition drifted")
            current_prompt, treatment_prompt = next(iter(current_prompts)), next(iter(treatment_prompts))
            if current_prompt.count(base_binary) != 1 or treatment_prompt != current_prompt.replace(base_binary, treatment_binary, 1):
                raise ValueError("source prompt delta is not the retired appendix exactly once")
            candidates.append({
                "fixture": fixture,
                "fixture_text": fixture_text[fixture],
                "leaf_id": next(iter(leaves)),
                "question": {key: question_records[next(iter(leaves))][key] for key in ("id", "text", "question_type", "applies_when", "evidence_policy")},
                "expected_label": expected[fixture],
                "receipts": ordered,
                "difference": _difference(current_prompt, treatment_prompt),
                "appendix_delta_sha256": digest(appendix_delta.encode("utf-8")),
                "source_slot_ids": sorted(str(slot["slot_id"]) for slot, _ in rows),
            })
    if len(candidates) != 1:
        raise ValueError("source discordance selection must contain exactly one fixture for the two-call audit")
    source_commitments = {name: sha(root / name) for name in ("private-corpus.json", "sealed-expected-ledger.json", "runtime-schedule.json", "study-manifest.json", "settlement.json", "arm-contract.json", "runtime-bundle.json", "remote-disclosure.json")}
    return {"source_commitments": source_commitments, "candidates": candidates}


def _blind_id(candidate: Mapping[str, Any], ordinal: int) -> str:
    return f"p1da-{ordinal:02d}-" + digest(canonical({"fixture": candidate["fixture"], "slots": candidate["source_slot_ids"]}))[:16]


def _receipt_projection(rows: list[tuple[Mapping[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    variants = {"CURRENT": "variant-a", "TREATMENT": "variant-b"}
    for ordinal, (slot, receipt) in enumerate(rows, 1):
        projected.append({
            "receipt_alias": f"receipt-{ordinal}", "variant": variants[str(slot["arm"])], "repeat_alias": f"repeat-{slot['repeat']}",
            "source_judgment": receipt["verdict"], "evidence": receipt["evidence"], "evidence_sha256": receipt["evidence_sha256"],
            "prompt_sha256": receipt["prompt_sha256"], "model": receipt["model"], "terminal": receipt["terminal"],
            "receipt_commitment": digest(canonical({key: receipt[key] for key in ("source_slot_sha256", "response_sha256", "verdict_sha256", "session_sha256")})),
        })
    return projected


def _state_plan(blind_id: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "review_id": blind_id + "-state", "review_type": "state_review",
        "execution": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "physical_attempts": 1, "retries": 0, "attempt_lifecycle_policy": "terminal_sidecar_v1", "zero_incremental_charge_only": True, "paid_fallback": "forbidden", "enabled": False},
        "visibility": {"hidden": ["label", "verdicts", "arm", "appendix", "session"]},
        "material": {"artifact_text": candidate["fixture_text"], "criterion": candidate["question"]},
        "response_contract": {"judgment_states": ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"], "evidence_required": True, "session_identifier_prohibited": True},
    }


def _mechanism_plan(blind_id: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "review_id": blind_id + "-mechanism", "review_type": "mechanism_review",
        "execution": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "physical_attempts": 1, "retries": 0, "attempt_lifecycle_policy": "terminal_sidecar_v1", "zero_incremental_charge_only": True, "paid_fallback": "forbidden", "enabled": False},
        "input_requirements": {"verified_blinded_state_judgment": "required_before_send", "source_label": "never_disclosed", "source_session": "never_disclosed"},
        "material": {"blinded_state_judgment": {"state_review_id": blind_id + "-state", "required": True, "source_label_disclosed": False}, "anonymized_receipts": _receipt_projection(candidate["receipts"]), "exact_variant_a_to_b_difference": candidate["difference"]},
        "response_contract": {"classification": list(MECHANISM_CLASSIFICATIONS), "only_permitted_classifications": True, "evidence_required": True},
    }


def _manifest(analysis: Mapping[str, Any]) -> dict[str, Any]:
    candidates = analysis["candidates"]
    entries = []
    for ordinal, candidate in enumerate(candidates, 1):
        blind_id = _blind_id(candidate, ordinal)
        entries.append({
            "blind_id": blind_id,
            "source_fixture_commitment": digest(canonical({"fixture": candidate["fixture"], "label": candidate["expected_label"], "slots": candidate["source_slot_ids"]})),
            "source_slot_commitments": [digest(canonical({key: receipt[key] for key in ("source_slot_sha256", "prompt_sha256", "evidence_sha256", "response_sha256", "verdict_sha256", "session_sha256", "terminal")})) for _, receipt in candidate["receipts"]],
            "state_plan_sha256": digest(canonical(_state_plan(blind_id, candidate))),
            "mechanism_plan_sha256": digest(canonical(_mechanism_plan(blind_id, candidate))),
            "a_b_difference_sha256": digest(candidate["difference"].encode("utf-8")), "appendix_delta_sha256": candidate["appendix_delta_sha256"],
        })
    disclosure = _pre_execution_disclosure(analysis)
    return {
        "format_version": 1, "study_id": STUDY_ID, "status": "INCOMPLETE", "provider_calls": 0,
        "execution_enabled": False, "dspy_enabled": False, "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE",
        "source_commitments": analysis["source_commitments"], "candidates": entries,
        "maximum_provider_calls": len(entries) * 2, "source_private_root_recorded": False,
        "pre_execution_disclosure_sha256": digest(canonical(disclosure)),
    }


def _pre_execution_disclosure(analysis: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for ordinal, candidate in enumerate(analysis["candidates"], 1):
        blind_id = _blind_id(candidate, ordinal)
        candidates.append({
            "blind_id": blind_id,
            "state_review_transmission": {"private_excerpt": candidate["fixture_text"], "criterion": candidate["question"], "prompt_sha256": digest(canonical(_state_plan(blind_id, candidate)))},
            "mechanism_review_transmission": {
                "blinded_state_judgment": "sanitized committed state output only; provider/session metadata prohibited",
                "anonymized_six_receipts": _receipt_projection(candidate["receipts"]),
                "exact_a_b_prompt_difference": candidate["difference"],
                "prompt_sha256": digest(canonical(_mechanism_plan(blind_id, candidate))),
            },
        })
    return {
        "format_version": 1, "study_id": STUDY_ID, "status": "pre_execution_frozen",
        "endpoint_profile": {"destination": "Codex CLI -> authenticated OpenAI service", "endpoint": "authenticated_openai_codex_cli", "profile": "authenticated_codex_profile"},
        "candidate_transmissions": candidates,
        "excluded_materials": ["sealed expected ledger", "expected labels", "source session identifiers"],
        "expected_ledger_sent": False, "candidate_count": len(candidates), "maximum_provider_calls": len(candidates) * 2,
        "sequence": "commit validated state result before rendering and sending each mechanism review", "paid_route": "forbidden", "fallback": "forbidden",
    }


def _public_aggregate(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "status": "INCOMPLETE", "provider_calls": 0,
        "selected_fixture_count": len(manifest["candidates"]), "bound_receipts": len(manifest["candidates"]) * 6,
        "frozen_future_singleton_reviews": len(manifest["candidates"]) * 2, "maximum_provider_calls": manifest["maximum_provider_calls"],
        "privacy": "aggregate_only", "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE",
        "promotion": "none", "dspy_enabled": False,
    }


def freeze(source_private_root: str | Path, packet_private_root: str | Path) -> dict[str, Any]:
    packet = private_root(packet_private_root)
    if packet == private_root(source_private_root):
        raise ValueError("audit packet root must differ from source root")
    analysis = _source_analysis(source_private_root)
    manifest = _manifest(analysis)
    for ordinal, candidate in enumerate(analysis["candidates"], 1):
        blind_id = _blind_id(candidate, ordinal)
        frozen(packet / "review-plans" / f"{blind_id}-state.json", canonical(_state_plan(blind_id, candidate)))
        frozen(packet / "review-plans" / f"{blind_id}-mechanism.json", canonical(_mechanism_plan(blind_id, candidate)))
    frozen(packet / "audit-manifest.json", canonical(manifest))
    frozen(packet / "remote-disclosure.json", canonical(_pre_execution_disclosure(analysis)))
    frozen(packet / "audit-state.json", canonical({"format_version": 1, "study_id": STUDY_ID, "status": "INCOMPLETE", "reason": "review calls are frozen but disabled and unexecuted", "provider_calls": 0}))
    frozen(packet / "public-aggregate.json", canonical(_public_aggregate(manifest)))
    return {"status": "INCOMPLETE", "provider_calls": 0, "selected_fixture_count": len(manifest["candidates"]), "frozen_reviews": manifest["maximum_provider_calls"]}


def verify(source_private_root: str | Path, packet_private_root: str | Path) -> dict[str, Any]:
    try:
        packet = private_root(packet_private_root)
        analysis = _source_analysis(source_private_root)
        expected_manifest = _manifest(analysis)
        actual_manifest = _source_json(packet, "audit-manifest.json")
        if actual_manifest != expected_manifest:
            raise ValueError("audit manifest or source binding drifted")
        for ordinal, candidate in enumerate(analysis["candidates"], 1):
            blind_id = _blind_id(candidate, ordinal)
            if _source_json(packet / "review-plans", f"{blind_id}-state.json") != _state_plan(blind_id, candidate):
                raise ValueError("state review plan drifted")
            if _source_json(packet / "review-plans", f"{blind_id}-mechanism.json") != _mechanism_plan(blind_id, candidate):
                raise ValueError("mechanism review plan drifted")
        if _source_json(packet, "public-aggregate.json") != _public_aggregate(expected_manifest):
            raise ValueError("public aggregate drifted")
        if _source_json(packet, "remote-disclosure.json") != _pre_execution_disclosure(analysis):
            raise ValueError("pre-execution disclosure drifted")
        state = _source_json(packet, "audit-state.json")
        if state != {"format_version": 1, "study_id": STUDY_ID, "status": "INCOMPLETE", "reason": "review calls are frozen but disabled and unexecuted", "provider_calls": 0}:
            raise ValueError("audit state drifted")
        return {"status": "INCOMPLETE", "provider_calls": 0, "drift": []}
    except (OSError, ValueError, json.JSONDecodeError, gzip.BadGzipFile) as error:
        return {"status": "INCOMPLETE", "provider_calls": 0, "drift": [str(error)]}


def dry_run(source_private_root: str | Path, packet_private_root: str | Path) -> dict[str, Any]:
    result = verify(source_private_root, packet_private_root)
    result["mode"] = "dry_run"
    return result


def _review_plan(packet: Path, review_id: str) -> dict[str, Any]:
    suffix = "-state.json" if review_id.endswith("-state") else "-mechanism.json"
    value = _source_json(packet / "review-plans", review_id.removesuffix("-state").removesuffix("-mechanism") + suffix)
    if value.get("review_id") != review_id or value.get("execution", {}).get("enabled") is not False:
        raise ValueError("frozen review plan drifted")
    return dict(value)


def _attempt_paths(packet: Path, review_id: str) -> tuple[Path, Path, Path, Path]:
    run = packet / "review-runs" / review_id
    terminal = run / "attempt-lifecycle" / "batch-0001"
    return run, terminal, terminal / "attempt-0001.start.json", terminal / "attempt-0001.settled.json"


def _review_request(plan: Mapping[str, Any], *, arming_receipt_sha256: str | None = None, state_receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(arming_receipt_sha256, str) or len(arming_receipt_sha256) != 64:
        raise ValueError("review request requires a provider-free arming receipt")
    execution = dict(plan["execution"])
    execution["enabled"] = True
    request = {"format_version": 1, "review_id": plan["review_id"], "review_type": plan["review_type"], "model": execution, "arming_receipt_sha256": arming_receipt_sha256, "material": plan["material"], "response_contract": plan["response_contract"]}
    if plan["review_type"] == "mechanism_review":
        if state_receipt is None:
            raise ValueError("mechanism request requires a committed state receipt")
        request["material"] = dict(plan["material"])
        request["material"]["blinded_state_judgment"] = {"review_id": state_receipt["review_id"], "output": state_receipt["output"], "output_sha256": state_receipt["output_sha256"]}
    return request


def _validate_provider_result(value: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    reported = value.get("reported")
    output = value.get("output")
    if not isinstance(reported, Mapping) or not isinstance(output, Mapping):
        raise ValueError("review result must contain reported provider identity and structured output")
    if {key: reported.get(key) for key in ("provider", "model", "reasoning_effort")} != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("review provider identity drifted")
    if not isinstance(reported.get("session_id"), str) or not reported["session_id"]:
        raise ValueError("review session commitment is absent")
    if request["review_type"] == "state_review":
        if set(output) != {"judgment_state", "evidence"} or output.get("judgment_state") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or not isinstance(output.get("evidence"), str) or not output["evidence"]:
            raise ValueError("state review output drifted")
        if re.search(r"\b(?:session|provider|model|endpoint|profile|request|response)[_-]?id\s*[:=]", output["evidence"], flags=re.IGNORECASE):
            raise ValueError("state review output contains prohibited provider metadata")
    elif output.get("classification") not in MECHANISM_CLASSIFICATIONS or not output.get("evidence"):
        raise ValueError("mechanism review taxonomy or evidence drifted")
    return dict(reported), dict(output)


def _expected_review_ids(manifest: Mapping[str, Any]) -> tuple[str, str]:
    if len(manifest.get("candidates", [])) != 1 or manifest.get("maximum_provider_calls") != 2:
        raise ValueError("audit is not the exact two-call packet")
    blind_id = manifest["candidates"][0].get("blind_id")
    if not isinstance(blind_id, str):
        raise ValueError("audit blind identifier drifted")
    return blind_id + "-state", blind_id + "-mechanism"


def _run_tree_manifest(run: Path, review_id: str) -> dict[str, Any]:
    allowed = ("request.json", "receipt.json", "lifecycle.json", "attempt-lifecycle/batch-0001/attempt-0001.start.json", "attempt-lifecycle/batch-0001/attempt-0001.settled.json")
    files = {relative: sha(run / relative) for relative in allowed}
    return {"format_version": 1, "review_id": review_id, "files": files, "complete_tree_sha256": digest(canonical(files))}


def _validate_review_receipt(packet: Path, review_id: str) -> dict[str, Any]:
    run, terminal, start, settled = _attempt_paths(packet, review_id)
    if sorted(path.name for path in run.iterdir()) != ["attempt-lifecycle", "lifecycle.json", "receipt.json", "request.json", "run-tree.json"]:
        raise ValueError("review run has unexpected top-level files")
    actual_tree = sorted(path.relative_to(run).as_posix() for path in run.rglob("*") if path.is_file()) if run.is_dir() else []
    expected_tree = sorted((*_run_tree_manifest(run, review_id)["files"], "run-tree.json")) if run.is_dir() else []
    if actual_tree != expected_tree:
        raise ValueError("review run tree has unexpected or missing files")
    lifecycle_parent = terminal.parent
    if sorted(path.name for path in lifecycle_parent.iterdir()) != ["batch-0001"]:
        raise ValueError("review has unexpected batch directory")
    files = sorted(path.name for path in terminal.iterdir()) if terminal.is_dir() else []
    if files != ["attempt-0001.settled.json", "attempt-0001.start.json"]:
        raise ValueError("review terminal lifecycle has extra or missing attempt files")
    start_value, settled_value, receipt = _source_json(terminal, start.name), _source_json(terminal, settled.name), _source_json(run, "receipt.json")
    request = _source_json(run, "request.json")
    if start_value != {"format_version": 1, "review_id": review_id, "batch": 1, "attempt": 1, "policy": "terminal_sidecar_v1", "request_sha256": digest(canonical(request))}:
        raise ValueError("review start sidecar drifted")
    expected_settled = {"format_version": 1, "review_id": review_id, "batch": 1, "attempt": 1, "policy": "terminal_sidecar_v1", "state": "settled", "outcome": "accepted", "receipt_sha256": sha(run / "receipt.json"), "start_sha256": sha(start)}
    if settled_value != expected_settled:
        raise ValueError("review settled sidecar drifted")
    required = {"format_version": 1, "review_id": review_id, "request_sha256": digest(canonical(request)), "provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_sha256": receipt.get("session_sha256"), "output_sha256": receipt.get("output_sha256")}
    if any(receipt.get(key) != value for key, value in required.items()) or not isinstance(receipt.get("output"), Mapping) or not isinstance(receipt.get("session_sha256"), str):
        raise ValueError("review receipt commitment drifted")
    lifecycle = _source_json(run, "lifecycle.json")
    expected_lifecycle = {"format_version": 1, "review_id": review_id, "full_lifecycle_sha256": digest(canonical({"start_sha256": sha(start), "settled_sha256": sha(settled), "receipt_sha256": sha(run / "receipt.json")}))}
    if lifecycle != expected_lifecycle:
        raise ValueError("review full lifecycle commitment drifted")
    if _source_json(run, "run-tree.json") != _run_tree_manifest(run, review_id):
        raise ValueError("review complete run-tree commitment drifted")
    return dict(receipt)


def _validate_review_namespace(packet: Path, manifest: Mapping[str, Any], *, require_all: bool) -> None:
    expected = set(_expected_review_ids(manifest))
    root = packet / "review-runs"
    actual = {path.name for path in root.iterdir()} if root.is_dir() else set()
    if actual - expected:
        raise ValueError("unexpected review-run identifier")
    if require_all and actual != expected:
        raise ValueError("exact two physical review runs are required")
    for review_id in actual:
        _validate_review_receipt(packet, review_id)


def _record_review(packet: Path, plan: Mapping[str, Any], runner_call: Any, *, arming_receipt_sha256: str, state_receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    review_id = str(plan["review_id"])
    run, terminal, start, settled = _attempt_paths(packet, review_id)
    if run.exists():
        return _validate_review_receipt(packet, review_id)
    request = _review_request(plan, arming_receipt_sha256=arming_receipt_sha256, state_receipt=state_receipt)
    frozen(run / "request.json", canonical(request))
    frozen(start, canonical({"format_version": 1, "review_id": review_id, "batch": 1, "attempt": 1, "policy": "terminal_sidecar_v1", "request_sha256": digest(canonical(request))}))
    value = runner_call(request)
    if not isinstance(value, Mapping):
        raise ValueError("review runner returned no structured result")
    reported, output = _validate_provider_result(value, request)
    receipt = {"format_version": 1, "review_id": review_id, "request_sha256": digest(canonical(request)), "provider": reported["provider"], "model": reported["model"], "reasoning_effort": reported["reasoning_effort"], "session_sha256": digest(str(reported["session_id"]).encode("utf-8")), "output": output, "output_sha256": digest(canonical(output))}
    frozen(run / "receipt.json", canonical(receipt))
    frozen(settled, canonical({"format_version": 1, "review_id": review_id, "batch": 1, "attempt": 1, "policy": "terminal_sidecar_v1", "state": "settled", "outcome": "accepted", "receipt_sha256": sha(run / "receipt.json"), "start_sha256": sha(start)}))
    frozen(run / "lifecycle.json", canonical({"format_version": 1, "review_id": review_id, "full_lifecycle_sha256": digest(canonical({"start_sha256": sha(start), "settled_sha256": sha(settled), "receipt_sha256": sha(run / "receipt.json")}))}))
    frozen(run / "run-tree.json", canonical(_run_tree_manifest(run, review_id)))
    return _validate_review_receipt(packet, review_id)


def _arming_receipt(packet: Path) -> dict[str, Any]:
    if not (packet / "arming-receipt.json").is_file():
        raise ValueError("arming receipt is required before execution")
    manifest = _source_json(packet, "audit-manifest.json")
    disclosure = _source_json(packet, "remote-disclosure.json")
    expected = {"format_version": 1, "study_id": STUDY_ID, "status": "ARMED", "provider_calls": 0, "execution_enabled": True, "maximum_provider_calls": 2, "audit_manifest_sha256": sha(packet / "audit-manifest.json"), "remote_disclosure_sha256": sha(packet / "remote-disclosure.json"), "expected_ledger_sent": False}
    receipt = _source_json(packet, "arming-receipt.json")
    if receipt != expected or manifest.get("pre_execution_disclosure_sha256") != digest(canonical(disclosure)):
        raise ValueError("provider-free arming receipt drifted")
    return receipt


def arm(source_private_root: str | Path, packet_private_root: str | Path, *, confirm_pre_execution_contract: bool = False) -> dict[str, Any]:
    if not confirm_pre_execution_contract:
        raise ValueError("arming requires explicit pre-execution contract confirmation")
    preflight = verify(source_private_root, packet_private_root)
    if preflight["drift"]:
        raise ValueError("arming refuses drifted packet")
    packet = private_root(packet_private_root)
    manifest = _source_json(packet, "audit-manifest.json")
    _expected_review_ids(manifest)
    disclosure = _source_json(packet, "remote-disclosure.json")
    receipt = {"format_version": 1, "study_id": STUDY_ID, "status": "ARMED", "provider_calls": 0, "execution_enabled": True, "maximum_provider_calls": 2, "audit_manifest_sha256": sha(packet / "audit-manifest.json"), "remote_disclosure_sha256": sha(packet / "remote-disclosure.json"), "expected_ledger_sent": False}
    if manifest.get("pre_execution_disclosure_sha256") != digest(canonical(disclosure)):
        raise ValueError("arming disclosure commitment drifted")
    frozen(packet / "arming-receipt.json", canonical(receipt))
    return receipt


def execute(source_private_root: str | Path, packet_private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Any = None) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge or runner_call is None:
        raise ValueError("execution requires explicit remote and zero-incremental-charge acknowledgement plus a runner")
    preflight = verify(source_private_root, packet_private_root)
    if preflight["drift"]:
        raise ValueError("execution refuses drifted packet")
    packet = private_root(packet_private_root)
    manifest = _source_json(packet, "audit-manifest.json")
    _arming_receipt(packet)
    _validate_review_namespace(packet, manifest, require_all=False)
    state_id, mechanism_id = _expected_review_ids(manifest)
    arming_sha = sha(packet / "arming-receipt.json")
    state = _record_review(packet, _review_plan(packet, state_id), runner_call, arming_receipt_sha256=arming_sha)
    mechanism = _record_review(packet, _review_plan(packet, mechanism_id), runner_call, arming_receipt_sha256=arming_sha, state_receipt=state)
    _validate_review_namespace(packet, manifest, require_all=True)
    executed = {"format_version": 1, "study_id": STUDY_ID, "status": "EXECUTED_PENDING_SETTLEMENT", "physical_provider_calls": 2, "arming_receipt_sha256": sha(packet / "arming-receipt.json"), "review_tree_sha256": digest(canonical({review_id: _source_json(packet / "review-runs" / review_id, "run-tree.json")["complete_tree_sha256"] for review_id in (state_id, mechanism_id)}))}
    frozen(packet / "executed-state.json", canonical(executed))
    return {**executed, "review_ids": [state_id, mechanism_id]}


def settle(source_private_root: str | Path, packet_private_root: str | Path) -> dict[str, Any]:
    preflight = verify(source_private_root, packet_private_root)
    if preflight["drift"]:
        return {"status": "INCOMPLETE", "provider_calls": 0, "drift": preflight["drift"]}
    packet = private_root(packet_private_root)
    manifest = _source_json(packet, "audit-manifest.json")
    if not (packet / "review-runs").exists():
        return {"status": "INCOMPLETE", "provider_calls": 0, "reason": "review calls are frozen but unexecuted", "drift": []}
    receipts = []
    try:
        _arming_receipt(packet)
        _validate_review_namespace(packet, manifest, require_all=True)
        state_id, mechanism_id = _expected_review_ids(manifest)
        receipts = [_validate_review_receipt(packet, state_id), _validate_review_receipt(packet, mechanism_id)]
        executed = _source_json(packet, "executed-state.json")
        expected_executed = {"format_version": 1, "study_id": STUDY_ID, "status": "EXECUTED_PENDING_SETTLEMENT", "physical_provider_calls": 2, "arming_receipt_sha256": sha(packet / "arming-receipt.json"), "review_tree_sha256": digest(canonical({review_id: _source_json(packet / "review-runs" / review_id, "run-tree.json")["complete_tree_sha256"] for review_id in (state_id, mechanism_id)}))}
        if executed != expected_executed:
            raise ValueError("executed state drifted")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": "INCOMPLETE", "provider_calls": 0, "drift": [str(error)]}
    classifications = {name: 0 for name in MECHANISM_CLASSIFICATIONS}
    for receipt in receipts:
        if receipt["review_id"].endswith("-mechanism"):
            classifications[receipt["output"]["classification"]] += 1
    result = {"format_version": 1, "study_id": STUDY_ID, "status": "SETTLED_AGGREGATE_ONLY", "review_count": len(receipts), "mechanism_classifications": classifications, "promotion": "none", "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE"}
    frozen(packet / "settlement.json", canonical(result))
    successor = {"format_version": 1, "study_id": STUDY_ID, "status": "SETTLED_AGGREGATE_ONLY", "predecessor_incomplete_aggregate_sha256": sha(packet / "public-aggregate.json"), "review_count": len(receipts), "mechanism_classifications": classifications, "promotion": "none", "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE"}
    frozen(packet / "public-aggregate.settled.v1.json", canonical(successor))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    for name in ("freeze", "verify", "dry-run", "settle", "arm"):
        command = commands.add_parser(name)
        command.add_argument("--source-private-root", required=True, type=Path)
        command.add_argument("--packet-private-root", required=True, type=Path)
        if name == "arm":
            command.add_argument("--confirm-pre-execution-contract", action="store_true")
    args = parser.parse_args()
    if args.command == "validate":
        result = validate_package()
    elif args.command == "freeze":
        result = freeze(args.source_private_root, args.packet_private_root)
    elif args.command == "verify":
        result = verify(args.source_private_root, args.packet_private_root)
    elif args.command == "settle":
        result = settle(args.source_private_root, args.packet_private_root)
    elif args.command == "arm":
        result = arm(args.source_private_root, args.packet_private_root, confirm_pre_execution_contract=args.confirm_pre_execution_contract)
    else:
        result = dry_run(args.source_private_root, args.packet_private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
