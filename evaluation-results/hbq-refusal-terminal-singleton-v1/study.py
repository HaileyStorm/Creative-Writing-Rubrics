#!/usr/bin/env python3
"""Provider-free terminal matrix executed through ``hbqrs.runner.run_judge``."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr
import hashlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterator, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import runner  # noqa: E402


CONTRACT_PATH = HERE / "study-contract.json"
FIXTURES_PATH = HERE / "fixtures.json"
BASE_REVISION = "fb77e8a61bff6b130147acd7a7c43ce20e88dd14"
QUESTION_ID = "core.substantive_task_engagement_true_non_refusal.no_refusal"
ARTIFACT_TEXT = "Synthetic terminal-matrix artifact: direct work is present."
RAW_REFUSAL = "SYNTHETIC TERMINAL REFUSAL FIXTURE: no work is returned."
MAXIMUM_ATTEMPTS = 2
PASS = "PASS_MATRIX"
NO_GO = "NO_GO_COLLAPSED_TERMINALS"
INCOMPLETE = "INCOMPLETE"
SCENARIO_IDS = (
    "accepted",
    "refusal-deflection-exhausted",
    "blank-quote-schema-exhausted",
    "retryable-then-accepted",
    "nonretryable-provider-stop",
    "ambiguous-started-unsettled",
)
EXPECTED = {
    "accepted": ("accepted", 1, 1, 0, 1, 0, 0, "no_resume", "settled"),
    "refusal-deflection-exhausted": ("refusal_deflection_exhausted", 2, 2, 0, 0, 2, 0, "no_more_injected_attempts", "settled"),
    "blank-quote-schema-exhausted": ("schema_or_quote_failure_exhausted", 2, 2, 0, 0, 2, 0, "no_more_injected_attempts", "settled"),
    "retryable-then-accepted": ("retryable_then_accepted", 2, 2, 0, 1, 1, 0, "no_resume", "settled"),
    "nonretryable-provider-stop": ("nonretryable_provider_stop", 1, 1, 0, 0, 1, 0, "stop_no_retry", "settled"),
    "ambiguous-started-unsettled": ("ambiguous_unsettled_no_auto_resend", 1, 1, 0, 0, 0, 1, "hold_no_auto_resend", "unsettled"),
}


class _AmbiguousInjectedCall(BaseException):
    """Deliberately bypasses the runner's retry handler after dispatch begins."""


def _sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON object: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def _git_bytes(revision: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{path}"], cwd=REPOSITORY, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if completed.returncode:
        raise ValueError(f"Cannot read canonical Git blob: {path}")
    return completed.stdout


def _checkout_has_base_revision() -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_REVISION, "HEAD"], cwd=REPOSITORY, check=False
    ).returncode == 0


def contract() -> dict[str, Any]:
    value = _read_object(CONTRACT_PATH)
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-refusal-terminal-singleton-v1" or value.get("base_revision") != BASE_REVISION:
        raise ValueError("Unexpected immutable study contract")
    if value.get("rubric") != {
        "bundle_id": "default.first_pass_screening",
        "module_id": "core.substantive_task_engagement_true_non_refusal",
        "leaf_id": QUESTION_ID,
    }:
        raise ValueError("Unexpected rubric contract")
    expected_execution = {
        "provider_free": True,
        "remote_provider_call_count": 0,
        "logical_sample_count": len(SCENARIO_IDS),
        "maximum_attempts_per_logical_sample": MAXIMUM_ATTEMPTS,
        "injected_attempt_count": 9,
        "fixture_kind": "public_synthetic_typed_attempts_v1",
        "scenario_ids": list(SCENARIO_IDS),
        "attempts_per_scenario": {
            "accepted": 1,
            "refusal-deflection-exhausted": 2,
            "blank-quote-schema-exhausted": 2,
            "retryable-then-accepted": 2,
            "nonretryable-provider-stop": 1,
            "ambiguous-started-unsettled": 1,
        },
    }
    if value.get("execution") != expected_execution:
        raise ValueError("Unexpected execution geometry")
    expected_gate = {
        "pass": PASS,
        "failure": NO_GO,
        "incomplete": INCOMPLETE,
        "pass_effect": "authorizes Sol review and a separately designed production exercise only",
        "automatic_promotion": False,
    }
    if value.get("gate") != expected_gate:
        raise ValueError("Unexpected gate contract")
    return value


def verify_bindings() -> dict[str, str]:
    value = contract()
    bindings = value.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ValueError("Missing binding map")
    if not _checkout_has_base_revision():
        raise ValueError("Executing checkout does not descend from fb77e8a")
    observed: dict[str, str] = {}
    for relative, expected in bindings.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("Malformed binding")
        if relative == "fixtures.json":
            actual = _sha256(FIXTURES_PATH.read_bytes())
        else:
            if subprocess.run(["git", "diff", "--quiet", BASE_REVISION, "--", relative], cwd=REPOSITORY, check=False).returncode:
                raise ValueError(f"Executing checkout input drifted: {relative}")
            actual = _sha256(_git_bytes(BASE_REVISION, relative))
        if actual != expected:
            raise ValueError(f"Canonical binding drifted: {relative}")
        observed[relative] = actual
    return observed


def _response(*, verdict: str = "YES", invalid: str | None = None) -> str:
    if invalid == "empty_schema":
        return json.dumps({"verdicts": []})
    quote = "" if invalid == "blank_exact_quote" else ARTIFACT_TEXT
    return json.dumps({"verdicts": [{"question_id": QUESTION_ID, "verdict": verdict, "confidence": 1.0, "evidence": [{"kind": "exact_quote", "reference": "public-synthetic-artifact", "exact_quote": quote, "summary": None}], "note": "Public synthetic singleton fixture."}]})


def _injected_call(events: list[Mapping[str, Any]], calls: list[str]) -> Callable[..., tuple[str, dict[str, Any]]]:
    def invoke(**_kwargs: Any) -> tuple[str, dict[str, Any]]:
        if not events:
            raise AssertionError("poison continuation invoked")
        event = events.pop(0).get("event")
        calls.append(str(event))
        if event == "valid_yes":
            return _response(), {"model": "injected-local"}
        if event == "raw_refusal":
            return RAW_REFUSAL, {"model": "injected-local"}
        if event == "blank_exact_quote":
            return _response(invalid="blank_exact_quote"), {"model": "injected-local"}
        if event == "empty_schema":
            return _response(invalid="empty_schema"), {"model": "injected-local"}
        if event == "retryable_failure":
            raise runner._ProviderAttemptFailure("synthetic retryable transport", retryable=True)
        if event == "nonretryable_failure":
            raise runner._ProviderAttemptFailure("synthetic nonretryable provider stop", retryable=False)
        if event == "ambiguous_interrupt":
            raise _AmbiguousInjectedCall("synthetic started-but-unsettled attempt")
        raise AssertionError("poison continuation invoked")
    return invoke


@contextmanager
def _patch_openai(callback: Callable[..., tuple[str, dict[str, Any]]]) -> Iterator[None]:
    original = runner._call_openai
    runner._call_openai = callback
    try:
        yield
    finally:
        runner._call_openai = original


def _rejections(output: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((output / "responses" / "rejected" / "batch-0001").glob("attempt-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["_artifact_sha256"] = _sha256(path.read_bytes())
        records.append(record)
    return records


def _checkpoint(output: Path) -> dict[str, Any] | None:
    path = output / "responses" / "batch-0001.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _terminal_from_artifacts(*, checkpoint: Mapping[str, Any] | None, rejected: list[Mapping[str, Any]], ambiguous: bool) -> tuple[str | None, str, str]:
    if ambiguous:
        return "ambiguous_unsettled_no_auto_resend", "hold_no_auto_resend", "unsettled"
    raw = [record.get("raw_content", {}).get("text") for record in rejected if isinstance(record.get("raw_content"), Mapping)]
    if checkpoint is not None:
        if len(rejected) == 1 and rejected[0].get("stage") == "provider":
            return "retryable_then_accepted", "no_resume", "settled"
        return "accepted", "no_resume", "settled"
    if len(rejected) == 2 and raw == [RAW_REFUSAL, RAW_REFUSAL]:
        return "refusal_deflection_exhausted", "no_more_injected_attempts", "settled"
    if len(rejected) == 2 and all(record.get("stage") == "model_output" for record in rejected):
        return "schema_or_quote_failure_exhausted", "no_more_injected_attempts", "settled"
    if len(rejected) == 1 and rejected[0].get("stage") == "provider":
        return "nonretryable_provider_stop", "stop_no_retry", "settled"
    return None, "unverifiable", "incomplete"


def _incomplete(scenario_id: str, expected: Any) -> dict[str, Any]:
    return {"scenario_id": scenario_id, "expected_terminal_class": expected, "observed_terminal_class": None, "maximum_attempts": MAXIMUM_ATTEMPTS, "attempt_started_count": 0, "injected_attempt_count": 0, "remote_provider_call_count": 0, "accepted_response_count": 0, "rejected_retry_count": 0, "ambiguous_attempt_count": 0, "accepted_response_sha256": None, "rejected_chain_head_sha256": None, "resume_action": "unverifiable", "settlement_status": "incomplete"}


def evaluate_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    scenario_id, expected, fixture_attempts = scenario.get("scenario_id"), scenario.get("expected_terminal_class"), scenario.get("attempts")
    if not isinstance(scenario_id, str) or scenario_id not in EXPECTED or not isinstance(expected, str) or not isinstance(fixture_attempts, list):
        return _incomplete(str(scenario_id), expected)
    events = [dict(item) for item in fixture_attempts if isinstance(item, Mapping)]
    if len(events) != len(fixture_attempts):
        return _incomplete(scenario_id, expected)
    calls: list[str] = []
    ambiguous = False
    with tempfile.TemporaryDirectory(prefix="hbq-refusal-terminal-") as temporary:
        root = Path(temporary)
        artifact, output = root / "artifact.txt", root / "run"
        artifact.write_text(ARTIFACT_TEXT, encoding="utf-8")
        try:
            with _patch_openai(_injected_call(events, calls)), redirect_stderr(StringIO()):
                runner.run_judge(
                    artifact_path=artifact, bundle_id="default.first_pass_screening", provider="openai", model="injected-local",
                    output_dir=output, registry=REPOSITORY / "registry" / "all_modules.json", bundles=REPOSITORY / "bundles" / "all_bundles.json",
                    question_ids=[QUESTION_ID], batch_size=1, batch_attempts=MAXIMUM_ATTEMPTS, base_url="http://127.0.0.1:1/v1",
                    timeout=1.0, artifact_id="public-synthetic-terminal-matrix", judge_id="injected-terminal-matrix",
                )
        except _AmbiguousInjectedCall:
            ambiguous = True
        except runner.HBQError:
            pass
        checkpoint = _checkpoint(output)
        rejected = _rejections(output)
        observed, resume, settlement = _terminal_from_artifacts(checkpoint=checkpoint, rejected=rejected, ambiguous=ambiguous)
        return {
            "scenario_id": scenario_id,
            "expected_terminal_class": expected,
            "observed_terminal_class": observed,
            "maximum_attempts": MAXIMUM_ATTEMPTS,
            "attempt_started_count": len(calls),
            "injected_attempt_count": len(calls),
            "remote_provider_call_count": 0,
            "accepted_response_count": 1 if checkpoint is not None else 0,
            "rejected_retry_count": len(rejected),
            "ambiguous_attempt_count": 1 if ambiguous else 0,
            "accepted_response_sha256": checkpoint.get("response_sha256") if checkpoint is not None else None,
            "rejected_chain_head_sha256": rejected[-1].get("_artifact_sha256") if rejected else None,
            "resume_action": resume,
            "settlement_status": settlement,
        }


def _gate(slots: list[dict[str, Any]]) -> str:
    if len(slots) != len(SCENARIO_IDS) or {slot.get("scenario_id") for slot in slots} != set(SCENARIO_IDS):
        return INCOMPLETE
    for slot in slots:
        scenario_id = slot["scenario_id"]
        expected = EXPECTED[scenario_id]
        if slot.get("maximum_attempts") != MAXIMUM_ATTEMPTS:
            return NO_GO
        observed_values = (
            slot.get("observed_terminal_class"), slot.get("attempt_started_count"), slot.get("injected_attempt_count"),
            slot.get("remote_provider_call_count"), slot.get("accepted_response_count"), slot.get("rejected_retry_count"),
            slot.get("ambiguous_attempt_count"), slot.get("resume_action"), slot.get("settlement_status"),
        )
        if slot.get("observed_terminal_class") is None or slot.get("settlement_status") == "incomplete":
            return INCOMPLETE
        if slot.get("expected_terminal_class") != expected[0] or observed_values != expected:
            return NO_GO
        accepted_hash = slot.get("accepted_response_sha256")
        rejected_hash = slot.get("rejected_chain_head_sha256")
        if bool(slot.get("accepted_response_count")) != isinstance(accepted_hash, str):
            return NO_GO
        if bool(slot.get("rejected_retry_count")) != isinstance(rejected_hash, str):
            return NO_GO
    if sum(slot["injected_attempt_count"] for slot in slots) != 9 or sum(slot["remote_provider_call_count"] for slot in slots) != 0:
        return NO_GO
    return PASS


def run_matrix() -> dict[str, Any]:
    bindings = verify_bindings()
    fixtures = _read_object(FIXTURES_PATH)
    if fixtures.get("artifact", {}).get("text") != ARTIFACT_TEXT or not isinstance(fixtures.get("scenarios"), list):
        raise ValueError("Fixture is not the bound public synthetic matrix")
    slots = [evaluate_scenario(item) if isinstance(item, Mapping) else _incomplete("invalid", None) for item in fixtures["scenarios"]]
    return {"format_version": 1, "study_id": contract()["study_id"], "provider_free": True, "base_revision": BASE_REVISION, "bindings": bindings, "logical_sample_count": len(slots), "injected_attempt_count": sum(slot["injected_attempt_count"] for slot in slots), "remote_provider_call_count": 0, "slots": slots, "gate": _gate(slots), "pass_effect": contract()["gate"]["pass_effect"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "write"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_matrix()
    if args.command == "write":
        if args.output is None:
            parser.error("write requires --output")
        args.output.write_bytes(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    print(json.dumps({"gate": result["gate"], "injected_attempt_count": result["injected_attempt_count"], "remote_provider_call_count": 0}, sort_keys=True))
    return 0 if result["gate"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
