from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v12-development-panel-v1"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("v12_development_panel", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def route_provider():
    now = datetime.now(timezone.utc)
    route = {
        "name": "grok-build-grok-4.6",
        "model": "grok-4.6",
        "reported_model": "grok-4.6-build",
        "adapter": "grok_exec",
        "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription",
        "account_class": "subscription",
        "identity_evidence": "requested_only",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "trusted": True,
        "reasoning_effort": "high",
        "grok_command": ["fixture"],
        "grok_command_identity": {"version": 1, "artifacts": []},
        "cli_version_identity": {"version": 1, "artifacts": []},
        "grok_cli_version": "fixture",
        "subscription_receipt_hash": "2" * 64,
        "cost_evidence": {
            "allowance_state": "available",
            "checked_at": (now - timedelta(seconds=1)).isoformat(),
            "evidence_hash": "1" * 64,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "kind": "subscription_included",
            "version": 1,
        },
        "allowed_payload_classes": ["public_repo"],
        "timeout_seconds": 1.0,
    }
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    evidence = {
        "route_name": route["name"],
        "route_sha256": hashlib.sha256(canonical(route)).hexdigest(),
        "cost_evidence_hash": route["cost_evidence"]["evidence_hash"],
        "subscription_receipt_hash": route["subscription_receipt_hash"],
        "grok_cli_version": route["grok_cli_version"],
        "cli_version_identity_sha256": hashlib.sha256(canonical(route["cli_version_identity"])).hexdigest(),
        "grok_command_identity_sha256": hashlib.sha256(canonical(route["grok_command_identity"])).hexdigest(),
        "registry_sha256": "3" * 64,
    }
    return lambda _queue: (route, evidence)


def common(tmp_path: Path) -> dict:
    return {
        "output_root": tmp_path / "output",
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
        "route_provider": route_provider(),
    }


def fixture_runner(value, cells: list[dict], contacts: list[str], concurrency: dict[str, int]):
    targets = {cell["cell_id"]: cell["target"] for cell in cells}
    group_members: dict[tuple[str, str], list[str]] = defaultdict(list)
    for cell in cells:
        group_members[(cell["candidate_id"], cell["prompt_group_id"])].append(cell["cell_id"])
    signs = {
        cell_id: (0.25 if index % 2 == 0 else -0.25)
        for members in group_members.values()
        for index, cell_id in enumerate(sorted(members))
    }
    lock = threading.Lock()

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        assert json.loads(schema_path.read_bytes())["required"] == ["scores", "evidence", "coverage"]
        cell_id = output_dir.name
        target = targets[cell_id]
        with lock:
            concurrency["active"] += 1
            concurrency["maximum"] = max(concurrency["maximum"], concurrency["active"])
        try:
            time.sleep(0.015)
            scores = {
                dimension: 2.0 if dimension == "Coherence" else float(target[dimension]) + signs[cell_id]
                for dimension in value.DIMS
            }
            structured = {
                "scores": scores,
                "evidence": {dimension: "Fixture evidence is present." for dimension in value.DIMS},
                "coverage": {dimension: False for dimension in value.DIMS},
            }
            response = json.dumps({
                "modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}},
                "num_turns": 1,
                "requestId": f"request-{cell_id}",
                "sessionId": f"session-{cell_id}",
                "stopReason": "end_turn",
                "structuredOutput": structured,
                "text": json.dumps(structured, sort_keys=True, separators=(",", ":")),
                "thought": "I evaluated every requested criterion.",
                "total_cost_usd": 0.0,
                "total_cost_usd_ticks": 0,
                "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4},
            }, ensure_ascii=False, indent=2).encode()
            responses = output_dir / "responses"
            responses.mkdir()
            (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
            before_contact()
            contacts.append(cell_id)
            (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
            return {
                "native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
                "native_response_bytes": response,
                "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": f"request-{cell_id}", "session_id": f"session-{cell_id}", "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
                "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False},
            }
        finally:
            with lock:
                concurrency["active"] -= 1

    return run


def test_schedule_is_exact_target_free_matched_26_cell_panel():
    value = module()
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    cells = schedule["cells"]
    assert len(cells) == 26
    assert {cell["candidate_id"] for cell in cells} == {BASELINE, CHILD20}
    assert len({cell["item_id"] for cell in cells}) == 13
    assert schedule["historical_baseline_context"] == {
        "adopted_into_metrics": False,
        "extra_votes": False,
        "prior_baseline_cells": 3,
        "schedule_sha256": "e8de7435e7cb1cab43f2a4d99438b2d136f6b763e758766cf3fe8626e1eda9e5",
        "status": "planned_repeats_context_only",
    }
    grouped = defaultdict(set)
    for cell in cells:
        grouped[cell["prompt_group_id"]].add(cell["item_id"])
        payload = base64.b64decode(cell["payload_base64"], validate=True)
        assert cell["payload_sha256"] == value.sha256(payload)
        assert "target" not in json.loads(payload)
        assert cell["endpoint_payload_sha256s"]["grok_primary"] == cell["endpoint_payload_sha256s"]["sol_later"] == cell["payload_sha256"]
    assert sorted(map(len, grouped.values())) == [1, 2, 2, 2, 2, 2, 2]


def test_prepare_all_is_provider_free_and_keeps_confirmation_this_study_closed(tmp_path: Path):
    value = module()
    prepared = value.prepare_all(**common(tmp_path))
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 26
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["authority"] == {
        "confirmation_access": "forbidden_in_this_study",
        "confirmation_cells": 0,
        "development_only": True,
        "dspy_optuna_runtime": False,
        "previous_results": "unchanged",
        "promotion": "none",
        "selection": "none",
        "sol_execution": "unopened",
    }


def test_native_26_receipts_are_bounded_one_shot_and_reported_with_group_weighted_errors(tmp_path: Path):
    value, args = module(), common(tmp_path)
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    value.prepare_all(**args)
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    results = value.execute_wave(**args, allow_remote=True, runner=fixture_runner(value, schedule["cells"], contacts, concurrency))
    assert len(results) == len(contacts) == 26
    assert 2 <= concurrency["maximum"] <= 10
    assert all(result["process_launches"] == 1 and result["native_endpoint_contact_cardinality"] == "unproven" for result in results)
    report = value.report(**{key: args[key] for key in args if key not in {"queue_root", "route_provider"}})
    assert len(report["cells"]) == report["unique_request_ids"] == report["unique_session_ids"] == 26
    assert all(not all(cell["coverage"].values()) and all(isinstance(score, float) for score in cell["scores"].values()) for cell in report["cells"])

    expected = {}
    for candidate in (BASELINE, CHILD20):
        groups: dict[str, list[float]] = defaultdict(list)
        for cell in report["cells"]:
            if cell["candidate_id"] == candidate:
                groups[cell["prompt_group_id"]].append(sum(abs(cell["scores"][name] - cell["target"][name]) for name in value.DIMS) / len(value.DIMS))
        expected[candidate] = sum(sum(errors) / len(errors) for errors in groups.values()) / len(groups)
    observed = {row["candidate_id"]: row["equal_group_mean_item_mae"] for row in report["metrics"]}
    assert observed == pytest.approx(expected)
    assert all(row["item_count"] == 13 and row["group_count"] == 7 and len(row["per_group_mean_item_mae"]) == 7 for row in report["metrics"])
    assert report["rank_correlations"][BASELINE]["item_13"]["Coherence"] is None
    assert report["rank_correlations"][CHILD20]["group_mean_7"]["Coherence"] is None
    claims = args["output_root"] / ".claims"
    assert {path.name for path in claims.iterdir()} == set(contacts)
    assert all(json.loads((claims / cell_id / "claim.json").read_text(encoding="utf-8"))["cell_id"] == cell_id for cell_id in contacts)

    before = {path.relative_to(args["output_root"]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="no resend"):
        value.execute_wave(**args, allow_remote=True, runner=lambda **_kwargs: pytest.fail("replayed cell contacted runner"))
    after = {path.relative_to(args["output_root"]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in args["output_root"].rglob("*") if path.is_file()}
    assert after == before

    mutated = args["output_root"] / contacts[1] / "prepared.json"
    original_prepared = mutated.read_bytes()
    prepared = json.loads(mutated.read_text(encoding="utf-8"))
    prepared["route"]["name"] = "mixed-route"
    mutated.write_bytes(value.canonical(prepared))
    with pytest.raises(ValueError, match="mixed receipt route or evidence"):
        value.report(**{key: args[key] for key in args if key not in {"queue_root", "route_provider"}})
    mutated.write_bytes(original_prepared)
    (claims / contacts[0] / "claim.json").unlink()
    with pytest.raises(ValueError):
        value.report(**{key: args[key] for key in args if key not in {"queue_root", "route_provider"}})


def test_precontact_mutation_is_rejected_before_any_native_contact(tmp_path: Path):
    value, args = module(), common(tmp_path)
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    value.prepare_all(**args)
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    clean = fixture_runner(value, schedule["cells"], contacts, concurrency)

    def mutate_then_run(**kwargs):
        (kwargs["output_dir"] / "prepared.json").write_bytes(b"{}\n")
        return clean(**kwargs)

    results = value.execute_wave(**args, allow_remote=True, runner=mutate_then_run)
    assert contacts == []
    assert len(results) == 26 and all(result["process_launches"] == 0 for result in results)
    with pytest.raises((TypeError, ValueError)):
        value.report(**{key: args[key] for key in args if key not in {"queue_root", "route_provider"}})


def test_runtime_has_no_dspy_optuna_or_confirmation_adoption_path():
    source = (PACKAGE / "study.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert "v7-" not in source and "v8-" not in source
