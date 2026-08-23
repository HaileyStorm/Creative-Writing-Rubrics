"""Freeze a private, provider-disabled audit plan for P1 raw discordances."""
from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import re
import subprocess
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
ADAPTER_ENVELOPE = "p1-discordance-codex-adapter-v2-result"
NOT_ATTESTED = "NOT_ATTESTED_BY_CODEX_JSONL"
REQUESTED_IDENTITY = {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}


class PrecontactFailure(RuntimeError):
    def __init__(self, adapter: Mapping[str, Any]):
        super().__init__("adapter reported PRECONTACT_FAILED_NO_MODEL_CONTACT")
        self.adapter = dict(adapter)


def _sha256(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a SHA-256 hex string")
    return value


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
        "reviews_per_fixture": 2, "maximum_model_contact_processes": 2, "model": "gpt-5.6-sol", "reasoning": "high",
        "batch_size": 1, "physical_attempts_per_review": 1, "retries": 0, "zero_incremental_charge_only": True, "paid_fallback_forbidden": True, "attempt_lifecycle_policy": "terminal_sidecar_v1",
        "provider_execution_enabled": False, "dspy_enabled": False, "mechanism_classifications": list(MECHANISM_CLASSIFICATIONS),
    }
    arming = {"provider_free": True, "explicit_confirmation_required": True, "arming_receipt_required_before_execution": True, "execution_state_written_after_exact_two_model_contact_processes": True, "adapter_contract_hash_required_before_execution": True}
    adapter_execution = {"result_envelope": ADAPTER_ENVELOPE, "adapter_statuses": ["ACCEPTED", "AMBIGUOUS_NO_RETRY", "PRECONTACT_FAILED_NO_MODEL_CONTACT"], "one_model_contact_process_per_callback": True, "requested_model_contact_processes": 2, "precontact_failure_is_recoverable": True, "stable_adapter_evidence_root_required": True, "contiguous_attempt_names_required": True, "request_binds_exact_review_id_and_arming_receipt": True, "started_process_counting": "callback_local_envelope_and_cumulative_study_result", "provider_http_attempts_observed": None, "model_and_reasoning_identity_evidence": "requested_only"}
    if review != expected_review or value.get("arming") != arming or value.get("adapter_execution") != adapter_execution or privacy != {"public_projection": "aggregate_only", "state_review_hides": ["label", "verdicts", "arm", "appendix", "session"], "source_private_root_recorded": False}:
        raise ValueError("audit review or privacy contract drifted")
    if value.get("appendix_disposition") != "FAILED_APPENDIX_RETIRED_NOT_REUSABLE" or value.get("drift_status") != "INCOMPLETE":
        raise ValueError("appendix or drift disposition changed")
    return {"study_id": STUDY_ID, "model_contact_processes_started": 0, "execution_enabled": False}


def _source_json(root: Path, name: str) -> Mapping[str, Any]:
    value = load(root / name)
    if not isinstance(value, Mapping):
        raise ValueError(f"source {name} must be an object")
    return value


def _arming_projection_sha256(value: Mapping[str, Any]) -> str:
    return digest(canonical({key: value[key] for key in sorted(value) if key != "adapter_contract_sha256"}))


def _validate_frozen_adapter_contract(path: Path, packet: Path, manifest: Mapping[str, Any], disclosure: Mapping[str, Any]) -> str:
    value = _source_json(path.parent, path.name)
    expected_keys = {"format_version", "status", "cwr_head", "study_sha256", "study_contract_sha256", "private_namespace_sha256", "packet_root", "packet_manifest_sha256", "packet_disclosure_sha256", "packet_arming_receipt_projection_sha256", "expected_review_ids", "codex_cli_version", "direct_codex_binary_sha256", "login_status", "login_status_sha256"}
    if set(value) != expected_keys or value.get("format_version") != 1 or value.get("status") != "FROZEN" or value.get("packet_root") != str(packet):
        raise ValueError("adapter contract is not a frozen packet-specific contract")
    for name in ("study_sha256", "study_contract_sha256", "private_namespace_sha256", "packet_manifest_sha256", "packet_disclosure_sha256", "packet_arming_receipt_projection_sha256", "direct_codex_binary_sha256", "login_status_sha256"):
        _sha256(value.get(name), name=f"adapter contract {name}")
    head = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", check=False)
    if head.returncode or value.get("cwr_head") != head.stdout.strip() or value.get("study_sha256") != sha(ROOT / "study.py") or value.get("study_contract_sha256") != sha(ROOT / "study-contract.json") or value.get("packet_manifest_sha256") != sha(packet / "audit-manifest.json") or value.get("packet_disclosure_sha256") != sha(packet / "remote-disclosure.json"):
        raise ValueError("adapter contract public or packet binding drifted")
    state_id, mechanism_id = _expected_review_ids(manifest)
    if value.get("expected_review_ids") != [state_id, mechanism_id] or value.get("codex_cli_version") != "codex-cli 0.149.0" or value.get("login_status") != "Logged in using ChatGPT":
        raise ValueError("adapter contract execution identity drifted")
    projection = {"format_version": 2, "study_id": STUDY_ID, "status": "ARMED", "model_contact_processes_started": 0, "execution_enabled": True, "maximum_model_contact_processes": 2, "audit_manifest_sha256": sha(packet / "audit-manifest.json"), "remote_disclosure_sha256": sha(packet / "remote-disclosure.json"), "expected_ledger_sent": False, "provider_http_attempts_observed": None}
    if value.get("packet_arming_receipt_projection_sha256") != _arming_projection_sha256({**projection, "adapter_contract_sha256": sha(path)}):
        raise ValueError("adapter contract arming projection drifted")
    if manifest.get("pre_execution_disclosure_sha256") != digest(canonical(disclosure)):
        raise ValueError("adapter contract disclosure binding drifted")
    return sha(path)


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
        "format_version": 2, "study_id": STUDY_ID, "status": "INCOMPLETE", "model_contact_processes_started": 0,
        "execution_enabled": False, "dspy_enabled": False, "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE",
        "source_commitments": analysis["source_commitments"], "candidates": entries,
        "maximum_model_contact_processes": len(entries) * 2, "source_private_root_recorded": False,
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
        "expected_ledger_sent": False, "candidate_count": len(candidates), "maximum_model_contact_processes": len(candidates) * 2,
        "sequence": "commit validated state result before rendering and sending each mechanism review", "paid_route": "forbidden", "fallback": "forbidden",
    }


def _public_aggregate(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 2, "study_id": STUDY_ID, "status": "INCOMPLETE", "model_contact_processes_started": 0,
        "selected_fixture_count": len(manifest["candidates"]), "bound_receipts": len(manifest["candidates"]) * 6,
        "frozen_future_singleton_reviews": len(manifest["candidates"]) * 2, "maximum_model_contact_processes": manifest["maximum_model_contact_processes"],
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
    frozen(packet / "audit-state.json", canonical({"format_version": 2, "study_id": STUDY_ID, "status": "INCOMPLETE", "reason": "model-contact reviews are frozen but disabled and unexecuted", "model_contact_processes_started": 0}))
    frozen(packet / "public-aggregate.json", canonical(_public_aggregate(manifest)))
    return {"status": "INCOMPLETE", "model_contact_processes_started": 0, "selected_fixture_count": len(manifest["candidates"]), "frozen_reviews": manifest["maximum_model_contact_processes"]}


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
        if state != {"format_version": 2, "study_id": STUDY_ID, "status": "INCOMPLETE", "reason": "model-contact reviews are frozen but disabled and unexecuted", "model_contact_processes_started": 0}:
            raise ValueError("audit state drifted")
        return {"status": "INCOMPLETE", "model_contact_processes_started": 0, "drift": []}
    except (OSError, ValueError, json.JSONDecodeError, gzip.BadGzipFile) as error:
        return {"status": "INCOMPLETE", "model_contact_processes_started": 0, "drift": [str(error)]}


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


def _validate_adapter_result(value: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    required = {
        "envelope", "status", "review_id", "request_sha256", "contact_process_started",
        "adapter_contract_sha256", "evidence_attempt_id", "preflight_sha256", "contact_sha256", "ambiguity_sha256", "precontact_sha256",
        "external_evidence_sha256", "requested", "observed", "output",
    }
    if set(value) != required or value.get("envelope") != ADAPTER_ENVELOPE:
        raise ValueError("review runner envelope drifted")
    if value.get("review_id") != request["review_id"] or value.get("request_sha256") != digest(canonical(request)):
        raise ValueError("review runner request binding drifted")
    if not isinstance(value.get("evidence_attempt_id"), str) or not re.fullmatch(r"attempt-[0-9]{4}", value["evidence_attempt_id"]):
        raise ValueError("review runner evidence attempt identity drifted")
    if value.get("status") not in {"ACCEPTED", "AMBIGUOUS_NO_RETRY", "PRECONTACT_FAILED_NO_MODEL_CONTACT"}:
        raise ValueError("review runner contact state drifted")
    if value.get("requested") != {**REQUESTED_IDENTITY, "model_contact_processes": 1}:
        raise ValueError("review runner requested identity drifted")
    observed = value.get("observed")
    if not isinstance(observed, Mapping) or set(observed) != {"authenticated_service", "model", "reasoning_effort", "thread_id_sha256", "model_contact_processes_started", "provider_http_attempts_observed"}:
        raise ValueError("review runner observed identity drifted")
    expected_started = 0 if value["status"] == "PRECONTACT_FAILED_NO_MODEL_CONTACT" else 1
    if value.get("contact_process_started") is not (expected_started == 1) or observed.get("authenticated_service") != "authenticated_openai_codex_cli" or observed.get("model") != NOT_ATTESTED or observed.get("reasoning_effort") != NOT_ATTESTED or observed.get("model_contact_processes_started") != expected_started or observed.get("provider_http_attempts_observed") is not None:
        raise ValueError("review runner observed identity is not honest")
    for name in ("adapter_contract_sha256", "preflight_sha256", "external_evidence_sha256"):
        _sha256(value.get(name), name=name)
    _sha256(observed.get("thread_id_sha256"), name="thread_id_sha256")
    if value["status"] == "PRECONTACT_FAILED_NO_MODEL_CONTACT":
        _sha256(value.get("precontact_sha256"), name="precontact_sha256")
        if value.get("contact_sha256") is not None or value.get("ambiguity_sha256") is not None or value.get("output") is not None:
            raise ValueError("precontact result must not claim model-contact evidence or output")
        return dict(value), {}
    _sha256(value.get("contact_sha256"), name="contact_sha256")
    if value["status"] == "AMBIGUOUS_NO_RETRY":
        _sha256(value.get("ambiguity_sha256"), name="ambiguity_sha256")
        if value.get("precontact_sha256") is not None or value.get("output") is not None:
            raise ValueError("ambiguous review result must not contain output")
        return dict(value), {}
    if value.get("ambiguity_sha256") is not None or value.get("precontact_sha256") is not None:
        raise ValueError("accepted review result cannot carry ambiguity evidence")
    output = value.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("accepted review result must contain structured output")
    if request["review_type"] == "state_review":
        if set(output) != {"judgment_state", "evidence"} or output.get("judgment_state") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or not isinstance(output.get("evidence"), str) or not output["evidence"]:
            raise ValueError("state review output drifted")
        if re.search(r"\b(?:session|provider|model|endpoint|profile|request|response)[_-]?id\s*[:=]", output["evidence"], flags=re.IGNORECASE):
            raise ValueError("state review output contains prohibited provider metadata")
    elif set(output) != {"classification", "evidence"} or output.get("classification") not in MECHANISM_CLASSIFICATIONS or not isinstance(output.get("evidence"), str) or not output["evidence"]:
        raise ValueError("mechanism review taxonomy or evidence drifted")
    return dict(value), dict(output)


def _reconcile_private_adapter_evidence(adapter: Mapping[str, Any], request: Mapping[str, Any], *, adapter_contract_sha256: str, adapter_evidence_root: Path) -> None:
    if adapter.get("adapter_contract_sha256") != adapter_contract_sha256:
        raise ValueError("adapter contract hash does not match the armed receipt")
    review_root = adapter_evidence_root / str(request["review_id"]) / "attempts" / str(adapter["evidence_attempt_id"])
    preflight_path = review_root / "preflight.json"
    external_path = review_root / "external-evidence.json"
    if not preflight_path.is_file() or not external_path.is_file():
        raise ValueError("private adapter preflight or external evidence is absent")
    expected_files = {
        "PRECONTACT_FAILED_NO_MODEL_CONTACT": {"preflight.json", "precontact-receipt.json", "external-evidence.json"},
        "ACCEPTED": {"preflight.json", "contact.json", "external-evidence.json"},
        "AMBIGUOUS_NO_RETRY": {"preflight.json", "contact.json", "ambiguity-receipt.json", "external-evidence.json"},
    }.get(adapter.get("status"))
    if expected_files is None or any(path.is_dir() for path in review_root.iterdir()) or {path.name for path in review_root.iterdir()} != expected_files:
        raise ValueError("private adapter attempt namespace has extra or missing artifacts")
    if sha(preflight_path) != adapter["preflight_sha256"] or sha(external_path) != adapter["external_evidence_sha256"]:
        raise ValueError("private adapter evidence hash drifted")
    preflight = _source_json(review_root, preflight_path.name)
    external = _source_json(review_root, external_path.name)
    if preflight.get("review_id") != request["review_id"] or preflight.get("request_sha256") != digest(canonical(request)) or preflight.get("contract_sha256") != adapter_contract_sha256:
        raise ValueError("private adapter preflight binding drifted")
    if external.get("review_id") != request["review_id"] or external.get("request_sha256") != digest(canonical(request)) or external.get("preflight_sha256") != adapter["preflight_sha256"] or external.get("status") != adapter["status"]:
        raise ValueError("private adapter external evidence binding drifted")
    if adapter["status"] == "PRECONTACT_FAILED_NO_MODEL_CONTACT":
        path = review_root / "precontact-receipt.json"
        if not path.is_file() or sha(path) != adapter["precontact_sha256"] or (review_root / "contact.json").exists() or (review_root / "ambiguity-receipt.json").exists():
            raise ValueError("private precontact evidence drifted")
        receipt = _source_json(review_root, path.name)
        expected_receipt = {"format_version": 1, "review_id": request["review_id"], "request_sha256": digest(canonical(request)), "status": adapter["status"], "preflight_sha256": adapter["preflight_sha256"], "model_contact_processes_started": 0, "retries": "permitted_before_any_model_contact"}
        if set(external) != {"format_version", "review_id", "request_sha256", "preflight_sha256", "precontact_sha256", "status"} or external.get("precontact_sha256") != adapter["precontact_sha256"] or receipt != expected_receipt:
            raise ValueError("private precontact receipt binding drifted")
        return
    contact_path = review_root / "contact.json"
    if not contact_path.is_file() or sha(contact_path) != adapter["contact_sha256"]:
        raise ValueError("private adapter contact evidence drifted")
    contact = _source_json(review_root, contact_path.name)
    if contact.get("review_id") != request["review_id"] or contact.get("request_sha256") != digest(canonical(request)) or contact.get("retries") != 0:
        raise ValueError("private adapter contact binding drifted")
    if external.get("contact_sha256") != adapter["contact_sha256"]:
        raise ValueError("private adapter external contact binding drifted")
    if adapter["status"] == "ACCEPTED":
        projection = external.get("event_projection")
        expected_external = {"format_version", "review_id", "request_sha256", "preflight_sha256", "contact_sha256", "events_sha256", "status", "event_projection", "output_sha256"}
        if set(external) != expected_external or external.get("output_sha256") != digest(canonical(adapter["output"])) or external.get("events_sha256") != contact.get("events_sha256") or not isinstance(projection, Mapping) or set(projection) != {"thread_id_sha256", "usage", "tool_items_observed"} or projection.get("thread_id_sha256") != adapter["observed"]["thread_id_sha256"] or projection.get("tool_items_observed") != 0 or not isinstance(projection.get("usage"), Mapping) or not all(isinstance(key, str) and type(amount) is int and amount >= 0 for key, amount in projection["usage"].items()):
            raise ValueError("private accepted adapter output or event binding drifted")
    ambiguity_path = review_root / "ambiguity-receipt.json"
    if adapter["status"] == "AMBIGUOUS_NO_RETRY":
        if not ambiguity_path.is_file() or sha(ambiguity_path) != adapter["ambiguity_sha256"]:
            raise ValueError("private adapter ambiguity evidence drifted")
        ambiguity = _source_json(review_root, ambiguity_path.name)
        if set(external) != {"format_version", "review_id", "request_sha256", "preflight_sha256", "contact_sha256", "ambiguity_sha256", "status"} or external.get("ambiguity_sha256") != adapter["ambiguity_sha256"] or ambiguity.get("status") != "AMBIGUOUS_NO_RETRY" or ambiguity.get("review_id") != request["review_id"] or ambiguity.get("contact_process_started") is not True:
            raise ValueError("private adapter ambiguity receipt binding drifted")
    elif ambiguity_path.exists():
        raise ValueError("accepted adapter evidence contains an ambiguity receipt")


def _expected_review_ids(manifest: Mapping[str, Any]) -> tuple[str, str]:
    if len(manifest.get("candidates", [])) != 1 or manifest.get("maximum_model_contact_processes") != 2:
        raise ValueError("audit is not the exact two-call packet")
    blind_id = manifest["candidates"][0].get("blind_id")
    if not isinstance(blind_id, str):
        raise ValueError("audit blind identifier drifted")
    return blind_id + "-state", blind_id + "-mechanism"


def _run_tree_manifest(run: Path, review_id: str) -> dict[str, Any]:
    allowed = ("request.json", "external-evidence.json", "receipt.json", "lifecycle.json", "attempt-lifecycle/batch-0001/attempt-0001.start.json", "attempt-lifecycle/batch-0001/attempt-0001.settled.json")
    files = {relative: sha(run / relative) for relative in allowed}
    return {"format_version": 1, "review_id": review_id, "files": files, "complete_tree_sha256": digest(canonical(files))}


def _validate_review_receipt(packet: Path, review_id: str) -> dict[str, Any]:
    run, terminal, start, settled = _attempt_paths(packet, review_id)
    if sorted(path.name for path in run.iterdir()) != ["attempt-lifecycle", "external-evidence.json", "lifecycle.json", "receipt.json", "request.json", "run-tree.json"]:
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
    external = _source_json(run, "external-evidence.json")
    required = {"format_version": 2, "review_id": review_id, "request_sha256": digest(canonical(request)), "requested": {**REQUESTED_IDENTITY, "model_contact_processes": 1}, "observed": receipt.get("observed"), "adapter_evidence_sha256": sha(run / "external-evidence.json"), "output_sha256": receipt.get("output_sha256")}
    if set(receipt) != {"format_version", "review_id", "request_sha256", "requested", "observed", "adapter_evidence_sha256", "output", "output_sha256"} or any(receipt.get(key) != value for key, value in required.items()) or not isinstance(receipt.get("output"), Mapping):
        raise ValueError("review receipt commitment drifted")
    adapter, output = _validate_adapter_result(external, request)
    if adapter["status"] != "ACCEPTED" or output != receipt["output"] or receipt["observed"] != adapter["observed"]:
        raise ValueError("review adapter evidence drifted")
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


def _completed_model_contact_processes(packet: Path, manifest: Mapping[str, Any]) -> int:
    expected = set(_expected_review_ids(manifest))
    root = packet / "review-runs"
    actual = {path.name for path in root.iterdir()} if root.is_dir() else set()
    if actual - expected:
        raise ValueError("unexpected review-run identifier")
    started = 0
    for review_id in actual:
        receipt = _validate_review_receipt(packet, review_id)
        observed = receipt.get("observed")
        if not isinstance(observed, Mapping) or observed.get("model_contact_processes_started") != 1:
            raise ValueError("accepted review does not prove one started model-contact process")
        started += 1
    return started


def _record_review(packet: Path, plan: Mapping[str, Any], runner_call: Any, *, arming_receipt_sha256: str, adapter_contract_sha256: str, adapter_evidence_root: Path, state_receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    review_id = str(plan["review_id"])
    run, terminal, start, settled = _attempt_paths(packet, review_id)
    if run.exists():
        receipt = _validate_review_receipt(packet, review_id)
        request = _source_json(run, "request.json")
        _reconcile_private_adapter_evidence(_source_json(run, "external-evidence.json"), request, adapter_contract_sha256=adapter_contract_sha256, adapter_evidence_root=adapter_evidence_root)
        return receipt
    request = _review_request(plan, arming_receipt_sha256=arming_receipt_sha256, state_receipt=state_receipt)
    value = runner_call(request)
    if not isinstance(value, Mapping):
        raise ValueError("review runner returned no structured result")
    adapter, output = _validate_adapter_result(value, request)
    _reconcile_private_adapter_evidence(adapter, request, adapter_contract_sha256=adapter_contract_sha256, adapter_evidence_root=adapter_evidence_root)
    if adapter["status"] == "PRECONTACT_FAILED_NO_MODEL_CONTACT":
        receipt = {"format_version": 1, "study_id": STUDY_ID, "status": adapter["status"], "review_id": review_id, "adapter_contract_sha256": adapter_contract_sha256, "preflight_sha256": adapter["preflight_sha256"], "precontact_sha256": adapter["precontact_sha256"], "external_evidence_sha256": adapter["external_evidence_sha256"], "model_contact_processes_started": 0, "retries": "permitted_before_any_model_contact"}
        frozen(packet / "precontact-receipts" / f"{review_id}-{adapter['precontact_sha256']}.json", canonical(receipt))
        raise PrecontactFailure(adapter)
    if adapter["status"] == "AMBIGUOUS_NO_RETRY":
        ambiguity = {"format_version": 2, "study_id": STUDY_ID, "status": "AMBIGUOUS_NO_RETRY", "review_id": review_id, "contact_process_started": True, "adapter_contract_sha256": adapter_contract_sha256, "preflight_sha256": adapter["preflight_sha256"], "contact_sha256": adapter["contact_sha256"], "adapter_evidence_sha256": adapter["external_evidence_sha256"], "ambiguity_sha256": adapter["ambiguity_sha256"], "retries": 0}
        frozen(packet / "ambiguity-receipt.json", canonical(ambiguity))
        raise ValueError("adapter reported AMBIGUOUS_NO_RETRY; no later callback is permitted")
    frozen(run / "request.json", canonical(request))
    frozen(start, canonical({"format_version": 1, "review_id": review_id, "batch": 1, "attempt": 1, "policy": "terminal_sidecar_v1", "request_sha256": digest(canonical(request))}))
    frozen(run / "external-evidence.json", canonical(adapter))
    receipt = {"format_version": 2, "review_id": review_id, "request_sha256": digest(canonical(request)), "requested": adapter["requested"], "observed": adapter["observed"], "adapter_evidence_sha256": sha(run / "external-evidence.json"), "output": output, "output_sha256": digest(canonical(output))}
    frozen(run / "receipt.json", canonical(receipt))
    frozen(settled, canonical({"format_version": 1, "review_id": review_id, "batch": 1, "attempt": 1, "policy": "terminal_sidecar_v1", "state": "settled", "outcome": "accepted", "receipt_sha256": sha(run / "receipt.json"), "start_sha256": sha(start)}))
    frozen(run / "lifecycle.json", canonical({"format_version": 1, "review_id": review_id, "full_lifecycle_sha256": digest(canonical({"start_sha256": sha(start), "settled_sha256": sha(settled), "receipt_sha256": sha(run / "receipt.json")}))}))
    frozen(run / "run-tree.json", canonical(_run_tree_manifest(run, review_id)))
    return _validate_review_receipt(packet, review_id)


def _arming_receipt(packet: Path, *, adapter_contract_path: Path | None = None) -> dict[str, Any]:
    if not (packet / "arming-receipt.json").is_file():
        raise ValueError("arming receipt is required before execution")
    manifest = _source_json(packet, "audit-manifest.json")
    disclosure = _source_json(packet, "remote-disclosure.json")
    receipt = _source_json(packet, "arming-receipt.json")
    contract_sha = receipt.get("adapter_contract_sha256")
    _sha256(contract_sha, name="armed adapter contract")
    if adapter_contract_path is not None and sha(adapter_contract_path) != contract_sha:
        raise ValueError("adapter contract file drifted from the armed receipt")
    expected = {"format_version": 2, "study_id": STUDY_ID, "status": "ARMED", "model_contact_processes_started": 0, "execution_enabled": True, "maximum_model_contact_processes": 2, "audit_manifest_sha256": sha(packet / "audit-manifest.json"), "remote_disclosure_sha256": sha(packet / "remote-disclosure.json"), "adapter_contract_sha256": contract_sha, "expected_ledger_sent": False, "provider_http_attempts_observed": None}
    if receipt != expected or manifest.get("pre_execution_disclosure_sha256") != digest(canonical(disclosure)):
        raise ValueError("provider-free arming receipt drifted")
    return receipt


def _refuse_after_ambiguity(packet: Path) -> None:
    path = packet / "ambiguity-receipt.json"
    if not path.exists():
        return
    value = _source_json(packet, path.name)
    required = {"format_version", "study_id", "status", "review_id", "contact_process_started", "adapter_contract_sha256", "preflight_sha256", "contact_sha256", "adapter_evidence_sha256", "ambiguity_sha256", "retries"}
    if set(value) != required or value.get("format_version") != 2 or value.get("study_id") != STUDY_ID or value.get("status") != "AMBIGUOUS_NO_RETRY" or value.get("contact_process_started") is not True or value.get("retries") != 0:
        raise ValueError("terminal ambiguity receipt drifted")
    for name in ("adapter_contract_sha256", "preflight_sha256", "contact_sha256", "adapter_evidence_sha256"):
        _sha256(value.get(name), name=f"terminal {name}")
    _sha256(value.get("ambiguity_sha256"), name="terminal ambiguity evidence")
    raise ValueError("terminal AMBIGUOUS_NO_RETRY receipt blocks all later callbacks")


def _execution_evidence(packet: Path, review_ids: tuple[str, str], *, adapter_contract_sha256: str) -> dict[str, Any]:
    adapters = {review_id: _source_json(packet / "review-runs" / review_id, "external-evidence.json") for review_id in review_ids}
    for review_id, adapter in adapters.items():
        if adapter.get("review_id") != review_id or adapter.get("status") != "ACCEPTED" or adapter.get("adapter_contract_sha256") != adapter_contract_sha256:
            raise ValueError("execution adapter evidence is incomplete")
    return {
        "requested_model_contact_processes": 2,
        "observed_model_contact_processes_started": sum(adapter["observed"]["model_contact_processes_started"] for adapter in adapters.values()),
        "provider_http_attempts_observed": None,
        "identity_evidence": "requested_model_and_reasoning_only",
        "adapter_contract_sha256": adapter_contract_sha256,
        "adapter_evidence_sha256": digest(canonical({review_id: sha(packet / "review-runs" / review_id / "external-evidence.json") for review_id in review_ids})),
        "adapter_preflight_chain_sha256": digest(canonical({review_id: {name: adapters[review_id][name] for name in ("adapter_contract_sha256", "preflight_sha256", "contact_sha256")} for review_id in review_ids})),
    }


def arm(source_private_root: str | Path, packet_private_root: str | Path, *, confirm_pre_execution_contract: bool = False, adapter_contract_path: str | Path | None = None) -> dict[str, Any]:
    if not confirm_pre_execution_contract or adapter_contract_path is None:
        raise ValueError("arming requires explicit pre-execution contract confirmation")
    contract_path = Path(adapter_contract_path).resolve()
    if not contract_path.is_file() or REPOSITORY.resolve() in contract_path.parents:
        raise ValueError("arming requires an external frozen adapter contract file")
    preflight = verify(source_private_root, packet_private_root)
    if preflight["drift"]:
        raise ValueError("arming refuses drifted packet")
    packet = private_root(packet_private_root)
    manifest = _source_json(packet, "audit-manifest.json")
    _expected_review_ids(manifest)
    disclosure = _source_json(packet, "remote-disclosure.json")
    contract_sha = _validate_frozen_adapter_contract(contract_path, packet, manifest, disclosure)
    receipt = {"format_version": 2, "study_id": STUDY_ID, "status": "ARMED", "model_contact_processes_started": 0, "execution_enabled": True, "maximum_model_contact_processes": 2, "audit_manifest_sha256": sha(packet / "audit-manifest.json"), "remote_disclosure_sha256": sha(packet / "remote-disclosure.json"), "adapter_contract_sha256": contract_sha, "expected_ledger_sent": False, "provider_http_attempts_observed": None}
    if manifest.get("pre_execution_disclosure_sha256") != digest(canonical(disclosure)):
        raise ValueError("arming disclosure commitment drifted")
    frozen(packet / "arming-receipt.json", canonical(receipt))
    return receipt


def execute(source_private_root: str | Path, packet_private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Any = None, adapter_contract_path: str | Path | None = None, adapter_evidence_root: str | Path | None = None) -> dict[str, Any]:
    if not allow_remote or not acknowledged_zero_incremental_charge or runner_call is None or adapter_contract_path is None or adapter_evidence_root is None:
        raise ValueError("execution requires explicit remote and zero-incremental-charge acknowledgement plus a runner")
    contract_path = Path(adapter_contract_path).resolve()
    evidence_root = Path(adapter_evidence_root).resolve()
    if not contract_path.is_file() or (evidence_root.exists() and not evidence_root.is_dir()) or REPOSITORY.resolve() in contract_path.parents or REPOSITORY.resolve() in evidence_root.parents:
        raise ValueError("execution requires external adapter contract and evidence roots")
    preflight = verify(source_private_root, packet_private_root)
    if preflight["drift"]:
        raise ValueError("execution refuses drifted packet")
    packet = private_root(packet_private_root)
    manifest = _source_json(packet, "audit-manifest.json")
    arming = _arming_receipt(packet, adapter_contract_path=contract_path)
    _refuse_after_ambiguity(packet)
    _validate_review_namespace(packet, manifest, require_all=False)
    state_id, mechanism_id = _expected_review_ids(manifest)
    arming_sha = sha(packet / "arming-receipt.json")
    try:
        state = _record_review(packet, _review_plan(packet, state_id), runner_call, arming_receipt_sha256=arming_sha, adapter_contract_sha256=arming["adapter_contract_sha256"], adapter_evidence_root=evidence_root)
        mechanism = _record_review(packet, _review_plan(packet, mechanism_id), runner_call, arming_receipt_sha256=arming_sha, adapter_contract_sha256=arming["adapter_contract_sha256"], adapter_evidence_root=evidence_root, state_receipt=state)
    except PrecontactFailure as error:
        return {"status": "PRECONTACT_FAILED_NO_MODEL_CONTACT", "review_id": error.adapter["review_id"], "model_contact_processes_started": _completed_model_contact_processes(packet, manifest), "provider_http_attempts_observed": None, "drift": []}
    _validate_review_namespace(packet, manifest, require_all=True)
    executed = {"format_version": 3, "study_id": STUDY_ID, "status": "EXECUTED_PENDING_SETTLEMENT", "arming_receipt_sha256": sha(packet / "arming-receipt.json"), "review_tree_sha256": digest(canonical({review_id: _source_json(packet / "review-runs" / review_id, "run-tree.json")["complete_tree_sha256"] for review_id in (state_id, mechanism_id)})), **_execution_evidence(packet, (state_id, mechanism_id), adapter_contract_sha256=arming["adapter_contract_sha256"])}
    frozen(packet / "executed-state.json", canonical(executed))
    return {**executed, "review_ids": [state_id, mechanism_id]}


def settle(source_private_root: str | Path, packet_private_root: str | Path, *, adapter_contract_path: str | Path | None = None, adapter_evidence_root: str | Path | None = None) -> dict[str, Any]:
    preflight = verify(source_private_root, packet_private_root)
    if preflight["drift"]:
        return {"status": "INCOMPLETE", "model_contact_processes_started": 0, "drift": preflight["drift"]}
    packet = private_root(packet_private_root)
    manifest = _source_json(packet, "audit-manifest.json")
    if not (packet / "review-runs").exists():
        return {"status": "INCOMPLETE", "model_contact_processes_started": 0, "reason": "model-contact reviews are frozen but unexecuted", "drift": []}
    receipts = []
    try:
        if adapter_contract_path is None or adapter_evidence_root is None:
            raise ValueError("settlement requires the external adapter contract and evidence roots")
        contract_path, evidence_root = Path(adapter_contract_path).resolve(), Path(adapter_evidence_root).resolve()
        arming = _arming_receipt(packet, adapter_contract_path=contract_path)
        _validate_review_namespace(packet, manifest, require_all=True)
        state_id, mechanism_id = _expected_review_ids(manifest)
        receipts = [_validate_review_receipt(packet, state_id), _validate_review_receipt(packet, mechanism_id)]
        for review_id in (state_id, mechanism_id):
            run = packet / "review-runs" / review_id
            _reconcile_private_adapter_evidence(_source_json(run, "external-evidence.json"), _source_json(run, "request.json"), adapter_contract_sha256=arming["adapter_contract_sha256"], adapter_evidence_root=evidence_root)
        executed = _source_json(packet, "executed-state.json")
        expected_executed = {"format_version": 3, "study_id": STUDY_ID, "status": "EXECUTED_PENDING_SETTLEMENT", "arming_receipt_sha256": sha(packet / "arming-receipt.json"), "review_tree_sha256": digest(canonical({review_id: _source_json(packet / "review-runs" / review_id, "run-tree.json")["complete_tree_sha256"] for review_id in (state_id, mechanism_id)})), **_execution_evidence(packet, (state_id, mechanism_id), adapter_contract_sha256=arming["adapter_contract_sha256"])}
        if executed != expected_executed:
            raise ValueError("executed state drifted")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": "INCOMPLETE", "model_contact_processes_started": 0, "drift": [str(error)]}
    classifications = {name: 0 for name in MECHANISM_CLASSIFICATIONS}
    for receipt in receipts:
        if receipt["review_id"].endswith("-mechanism"):
            classifications[receipt["output"]["classification"]] += 1
    result = {"format_version": 3, "study_id": STUDY_ID, "status": "SETTLED_AGGREGATE_ONLY", "review_count": len(receipts), "mechanism_classifications": classifications, "promotion": "none", "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE", **_execution_evidence(packet, (state_id, mechanism_id), adapter_contract_sha256=arming["adapter_contract_sha256"])}
    frozen(packet / "settlement.json", canonical(result))
    successor = {"format_version": 3, "study_id": STUDY_ID, "status": "SETTLED_AGGREGATE_ONLY", "predecessor_incomplete_aggregate_sha256": sha(packet / "public-aggregate.json"), "review_count": len(receipts), "mechanism_classifications": classifications, "promotion": "none", "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE", **_execution_evidence(packet, (state_id, mechanism_id), adapter_contract_sha256=arming["adapter_contract_sha256"])}
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
        if name in {"arm", "settle"}:
            command.add_argument("--adapter-contract-path", type=Path)
            command.add_argument("--adapter-evidence-root", type=Path)
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
        result = settle(args.source_private_root, args.packet_private_root, adapter_contract_path=args.adapter_contract_path, adapter_evidence_root=args.adapter_evidence_root)
    elif args.command == "arm":
        result = arm(args.source_private_root, args.packet_private_root, confirm_pre_execution_contract=args.confirm_pre_execution_contract, adapter_contract_path=args.adapter_contract_path)
    else:
        result = dry_run(args.source_private_root, args.packet_private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
