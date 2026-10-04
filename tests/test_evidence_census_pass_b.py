"""Accepted request/native joins retain missingness and historical completion classes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "evaluation-results/hbq-evidence-census-pass-b-v1/census.py"
SPEC = importlib.util.spec_from_file_location("evidence_census_b", MODULE)
assert SPEC is not None and SPEC.loader is not None
census = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(census)


def write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(census.canonical(value))
    return census.sha(path.read_bytes())


@pytest.fixture
def retained(tmp_path: Path) -> dict:
    control, campaign, plan_root = (tmp_path / name for name in ("control", "campaign", "plan"))
    peer_names = {name: name for name in ("plan", "original", "replacement", "parallel", "recovery",
                                        "recovery_1328", "recovery_4486")}
    inputs = {
        "census_a": {"root": "control", "path": "a.json"},
        "validation": {"root": "control", "path": "dryad-sol-validation-r28/sol.json"},
        "replay": {"root": "campaign", "path": "selected100-complete-collection-replay.json"},
        "manifest": {"root": "campaign", "path": "campaign-manifest.json"},
        "result": {"root": "campaign", "path": "collection-result.json"},
        "schedule": {"root": "campaign", "path": "selected-schedule.json"},
        "plan": {"root": "plan", "path": "plan.json"},
        "replacement": {"root": "replacement", "path": "replacement-terminal.json"},
        "recovery_1328": {"root": "recovery_1328", "path": "reconciliation.json"},
        "recovery_4486": {"root": "recovery_4486", "path": "reconciliation.json"},
        "validation_reader": {"root": "repository", "path": MODULE.relative_to(
            census.REPOSITORY).as_posix(), "kind": "code_pin", "sha256": census.sha(MODULE.read_bytes())},
    }
    descriptor = {"schema_version": 1, "scope": "fixture_partial_census", "inputs": inputs,
                  "peer_roots": peer_names, "retained_replay_composer_sha256": "a" * 64,
                  "expected": {"passes": 6, "requests": 6, "leaves": 12, "unknown_exit": 3,
                               "original_events": 1, "replacement": 1, "ordinary_terminal": 2,
                               "reconciliation": 2, "census_a_observed_leaves": 1},
                  "unresolved": ["Failed predecessors and physical contacts remain unresolved."]}
    requests, passes, selected, rows, recoveries = [], [], [], [], {}
    unknown_ordinals = {1328, 4486, 4493}
    for ordinal, root_name in ((1, "original"), (773, "replacement"), (829, "parallel"),
                               (1328, "parallel"), (4486, "recovery"), (4493, "recovery")):
        sample, pass_id = f"sample-{ordinal}", f"pass-{ordinal}"
        source = plan_root / f"inputs/{ordinal}.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"private-source-prose")
        prompt = plan_root / f"prompts/{ordinal}.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_bytes(b"private-prompt-prose")
        schema = plan_root / f"schemas/{ordinal}.json"
        schema_sha = write(schema, {"question_ids": ["q1", "q2"]})
        request = {"ordinal": ordinal, "batch_number": 1, "pass_id": pass_id, "logical_sample_id": sample,
                   "question_ids": ["q1", "q2"], "prompt_path": prompt.relative_to(plan_root).as_posix(),
                   "prompt_sha256": census.sha(prompt.read_bytes()), "prompt_bytes": len(prompt.read_bytes()),
                   "schema_path": schema.relative_to(plan_root).as_posix(), "schema_sha256": schema_sha,
                   "schema_bytes": len(schema.read_bytes())}
        requests.append(request)
        passes.append({"pass_id": pass_id, "logical_sample_id": sample, "partition": "TRAIN",
                       "input_path": source.relative_to(plan_root).as_posix(),
                       "source_sha256": census.sha(source.read_bytes()), "source_bytes": len(source.read_bytes())})
        selected.append({"pass_id": pass_id, "logical_sample_id": sample, "partition": "TRAIN",
                         "request_ordinals": [ordinal], "leaves": 2})
        verdicts = [{"question_id": "q1", "verdict": "YES"}, {"question_id": "q2", "verdict": "CANNOT_ASSESS"}]
        path = tmp_path / root_name / ("run/responses/batch-0001.json" if ordinal == 1
                                     else "replacement-response.json" if ordinal == 773
                                     else f"requests/{ordinal}/response.json")
        thread = f"private-native-thread-{ordinal}"
        response = {"normalized_verdicts" if ordinal == 1 else "verdicts": verdicts,
                    "unused_rationale": "never-export-this-rationale"}
        if ordinal == 1:
            event_path = path.parent / "events.jsonl"
            event_path.parent.mkdir(parents=True, exist_ok=True)
            event_path.write_bytes(census.canonical({"type": "thread.started", "thread_id": thread}) + b"\n" +
                                   census.canonical({"type": "turn.completed", "usage": {}}) + b"\n")
            response.update(accepted_attempt=1, provider={"provider_artifacts": {"codex_events": {
                "path": "responses/events.jsonl", "sha256": census.sha(event_path.read_bytes()),
                "bytes": len(event_path.read_bytes())}}})
        response_sha = write(path, response)
        unknown = ordinal in unknown_ordinals
        commitment = {"ordinal": ordinal, "path": str(path), "sha256": response_sha,
                      "source_class": census.source_class(ordinal, unknown),
                      "completion_class": "completed_with_unknown_exit" if unknown else None,
                      "process_success_proven": False if unknown else None}
        rows.append({"pass_id": pass_id, "partition": "TRAIN", "canonical_verdicts": verdicts,
                     "request_commitments": [commitment]})
        if ordinal in {1328, 4486}:
            recoveries[ordinal] = {"ordinal": ordinal, "thread_id": thread, "process_success_proven": False,
                                   "derived_response_sha256": response_sha,
                                   "native_files": {"message": {"path": str(path), "sha256": response_sha}}}
        elif ordinal != 1:
            start_name = "replacement-start.json" if ordinal == 773 else "start.json"
            start_sha = write(path.parent / start_name, {"ordinal": ordinal, "attempt": 1,
                "logical_attempt": 1, "prompt_sha256": request["prompt_sha256"], "schema_sha256": schema_sha})
            terminal_name = "replacement-terminal.json" if ordinal == 773 else "terminal.json"
            write(path.parent / terminal_name, {"original_ordinal" if ordinal == 773 else "ordinal": ordinal,
                "thread_id": thread, "response_sha256": response_sha, "start_sha256": start_sha,
                "state": "replacement_accepted_under_owner_allowance_assumption" if ordinal == 773
                else "completed_with_unknown_exit" if unknown else "accepted"})
    roots = {"control": control, "campaign": campaign, "repository": census.REPOSITORY,
             **{name: tmp_path / relative for name, relative in peer_names.items()}}
    values = {
        "plan": {"requests": requests, "passes": passes,
                 "runtime": {"question_payload_sha256": "b" * 64, "compiled_bundle_sha256": "c" * 64}},
        "schedule": {"selected_passes": selected, "selected_request_ordinals": [r["ordinal"] for r in requests],
                     "question_ids": ["q1", "q2"]},
        "result": {"state": "collected", "failures": []},
        "recovery_1328": {"recoveries": [recoveries[1328]]},
        "recovery_4486": {"recoveries": [recoveries[4486]]},
        "manifest": {"plan_root": str(plan_root), "reconciliation_path": str(tmp_path / "recovery_4486/reconciliation.json")},
        "replay": {"composer_sha256": "a" * 64, "provider_calls": 0, "full_study_admitted": False,
                   "selected_requests": 6, "canonical_verdicts": 12, "endpoint_sol_rows": rows,
                   "accepted_native_thread_ids": [f"private-native-thread-{r['ordinal']}" for r in requests],
                   "unknown_exit_commitments": [row["request_commitments"][0] for row in rows
                                                if row["request_commitments"][0]["process_success_proven"] is False],
                   "qualification_failures": [{"pass_id": "pass-1", "reason": "coverage_below_0.88"}]},
        "validation": {}, "census_a": {},
    }
    fixture = {"control": control, "campaign": campaign, "roots": roots, "values": values,
               "descriptor": descriptor}
    refresh(fixture)
    return fixture


def refresh(fixture: dict) -> None:
    values, specs, roots = fixture["values"], fixture["descriptor"]["inputs"], fixture["roots"]
    for name in ("plan", "result", "recovery_1328", "recovery_4486", "replacement"):
        spec = specs[name]
        path = roots[spec["root"]] / spec["path"]
        specs[name]["sha256"] = write(path, values[name]) if name in values else census.sha(path.read_bytes())
    values["schedule"]["original_plan_sha256"] = specs["plan"]["sha256"]
    spec = specs["schedule"]
    spec["sha256"] = write(roots[spec["root"]] / spec["path"], values["schedule"])
    values["manifest"].update(original_plan_sha256=specs["plan"]["sha256"],
        selected_schedule_sha256=specs["schedule"]["sha256"], reconciliation_sha256=specs["recovery_4486"]["sha256"])
    spec = specs["manifest"]
    spec["sha256"] = write(roots[spec["root"]] / spec["path"], values["manifest"])
    values["replay"].update(campaign_manifest_sha256=specs["manifest"]["sha256"],
        collection_result_sha256=specs["result"]["sha256"], collection_result=values["result"])
    spec = specs["replay"]
    spec["sha256"] = write(roots[spec["root"]] / spec["path"], values["replay"])
    freeze = {key: values["replay"][key] for key in ("campaign_manifest_sha256", "collection_result_sha256",
              "canonical_verdicts", "selected_requests", "accepted_native_thread_ids", "unknown_exit_commitments")}
    freeze.update(composer_sha256=specs["validation_reader"]["sha256"], replay_receipt_sha256=spec["sha256"])
    values["validation"] = {"freeze": {"sol_collection": freeze}}
    spec = specs["validation"]
    spec["sha256"] = write(roots[spec["root"]] / spec["path"], values["validation"])
    values["census_a"] = {"totals": {"observed_ttcw_pron_dryad_native_verdict_rows": 1,
        "retained_declared_ttcw_pron_dryad_native_verdicts": 13},
        "sources": [{"id": "dryad-sol", "source_sha256": specs["validation"]["sha256"], "observed": {}}]}
    spec = specs["census_a"]
    spec["sha256"] = write(roots[spec["root"]] / spec["path"], values["census_a"])


def build(fixture: dict) -> tuple[dict, dict]:
    return census.build_census(fixture["control"], fixture["campaign"], fixture["descriptor"])


def test_complete_join_preserves_unknown_exit_and_omits_private_content(retained: dict) -> None:
    report, ledger = build(retained)
    assert report["observed"]["accepted_request_native_joins"] == 6
    assert report["observed"]["normalized_native_verdict_rows"] == 12
    assert report["totals"]["observed_ttcw_pron_dryad_native_verdict_rows_after_join"] == 13
    assert report["observed"]["identity_sources"] == {
        "pinned_own_events": 1, "replacement_terminal": 1, "ordinary_terminal": 2, "reconciliation": 2}
    unknown = [row for row in ledger["slots"] if row["process_success_proven"] is False]
    assert [row["ordinal"] for row in unknown] == [1328, 4486, 4493]
    assert all(row["completion_class"] == "completed_with_unknown_exit" and row["no_resend"] for row in unknown)
    assert report["provenance"]["retained_replay_composer_sha256"] != report["provenance"]["later_validation_reader_sha256"]
    assert report["status"] == "partial_census" and report["new_provider_votes"] == 0
    replacement = next(row for row in ledger["slots"] if row["ordinal"] == 773)
    assert replacement["attempt_lineage"]["retained_terminal_state"] == "replacement_accepted_under_owner_allowance_assumption"
    for value in (report, ledger):
        raw = census.canonical(value)
        for secret in (b"private-native-thread", b"private-source-prose", b"private-prompt-prose", b"never-export-this-rationale"):
            assert secret not in raw


def test_wrong_native_thread_fails_closed(retained: dict) -> None:
    path = retained["roots"]["parallel"] / "requests/829/terminal.json"
    terminal = json.loads(path.read_bytes())
    terminal["thread_id"] = "foreign-native-thread"
    write(path, terminal)
    with pytest.raises(ValueError, match="Wrong or duplicate accepted native thread"):
        build(retained)


def test_duplicate_request_ordinal_fails_closed(retained: dict) -> None:
    retained["values"]["replay"]["endpoint_sol_rows"][1]["request_commitments"][0]["ordinal"] = 1
    refresh(retained)
    with pytest.raises(ValueError, match="selected request ordinal"):
        build(retained)


@pytest.mark.parametrize("change", ["reorder", "missing"])
def test_reordered_or_missing_leaf_fails_closed(retained: dict, change: str) -> None:
    leaves = retained["values"]["replay"]["endpoint_sol_rows"][0]["canonical_verdicts"]
    if change == "reorder":
        leaves.reverse()
    else:
        leaves.pop()
    refresh(retained)
    with pytest.raises(ValueError, match="retained leaf"):
        build(retained)


def test_absent_recovery_receipt_fails_closed(retained: dict) -> None:
    (retained["roots"]["recovery_4486"] / "reconciliation.json").unlink()
    with pytest.raises(ValueError, match="Missing or unreadable retained input: recovery_4486"):
        build(retained)


def test_changed_prompt_bytes_fail_closed(retained: dict) -> None:
    (retained["roots"]["plan"] / "prompts/829.txt").write_bytes(b"changed condition")
    with pytest.raises(ValueError, match="packet prompt"):
        build(retained)


def test_fresh_private_output_guard_rejects_source_and_repository(retained: dict) -> None:
    inputs = census.Inputs(retained["control"], retained["campaign"], retained["descriptor"])
    for path in (retained["roots"]["plan"] / "new-output", census.REPOSITORY / "new-census-output"):
        with pytest.raises(ValueError, match="overlaps retained evidence|outside the repository"):
            census.output_preflight(path, inputs)
        assert not path.exists()
