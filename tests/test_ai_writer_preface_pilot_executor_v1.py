from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import csv
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-pilot-executor-v1"
PINNED_HANNA = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")


def _executor():
    specification = importlib.util.spec_from_file_location("ai_writer_preface_pilot_executor_v1", PACKAGE / "executor.py")
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _binding(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(data), "sha256": _sha(data)}


def _contract(item_id: str) -> dict[str, object]:
    return {
        "contract_version": 1,
        "contract_id": f"preface.{item_id}",
        "artifact_id": item_id,
        "context": {"artifact_kind": "short story", "declared_scope": "complete story", "completion_status": "complete", "background": ["test fixture"], "constraints": ["none"], "audience": ["adult readers"]},
        "preferences": [],
        "priorities": [],
        "weighted_goals": [],
        "binding_requirements": [],
    }


def _write_projection(private: Path, authority_items: list[dict[str, object]]) -> dict[str, object]:
    with (private / "hanna-authority.csv").open(encoding="utf-8", newline="") as source:
        stories = {row["hanna_item_id"]: (row["Story"], row["Prompt"]) for row in csv.DictReader(source)}
    projection = {
        "format_version": 1,
        "recipe": "hanna-story-prompt-projection-v1: sort by executor_id; bind exact CSV Story and Prompt plus verified provenance",
        "parent_dataset_sha256": _binding(private / "hanna-parent-dataset.csv")["sha256"],
        "extraction_output_sha256": _binding(private / "hanna-authority.csv")["sha256"],
        "pinned_provenance_sha256": _binding(private / "provenance-authority.json")["sha256"],
        "items": sorted([{"executor_id": str(item["executor_id"]), "hanna_item_id": str(item["hanna_item_id"]), "story": stories[str(item["hanna_item_id"])][0], "prompt": stories[str(item["hanna_item_id"])][1], "actual_origin": str(item["actual_origin"]), "source_model": str(item["source_model"]), "matching_stratum": str(item["matching_stratum"])} for item in authority_items], key=lambda item: item["executor_id"]),
    }
    output = private / "hanna-projection.json"
    output.write_text(json.dumps(projection, sort_keys=True), encoding="utf-8")
    receipt = private / "hanna-projection-receipt.json"
    receipt.write_text(json.dumps({"format_version": 1, "extraction_recipe": "hanna-story-prompt-extraction-v1: preserve parent CSV row order and emit hanna_item_id,Story,Prompt with LF records", "parent_dataset_sha256": projection["parent_dataset_sha256"], "extraction_output_sha256": projection["extraction_output_sha256"], "recipe": projection["recipe"], "pinned_provenance_sha256": projection["pinned_provenance_sha256"], "projection": _binding(output), "projection_output_sha256": _binding(output)["sha256"]}, sort_keys=True), encoding="utf-8")
    return _binding(receipt)


def _private_root(tmp_path: Path) -> Path:
    private = tmp_path / "private"
    items = []
    authority_items = []
    hanna_source = private / "hanna-authority.csv"
    parent_hanna_dataset = private / "hanna-parent-dataset.csv"
    provenance_source = private / "provenance-authority.json"
    hanna_source.parent.mkdir(parents=True, exist_ok=True)
    parent_hanna_dataset.write_bytes(PINNED_HANNA.read_bytes())
    with PINNED_HANNA.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    groups: dict[str, tuple[str, str, str, int]] = {}
    order = []
    for row in rows:
        story_id = row["Story ID"]
        triple = (row["Prompt"], row["Story"], row["Model"])
        if story_id not in groups:
            groups[story_id] = (*triple, 1)
            order.append(story_id)
        else:
            assert groups[story_id][:3] == triple
            groups[story_id] = (*triple, groups[story_id][3] + 1)
    selected_ids = order[:4]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["hanna_item_id", "Story", "Prompt"], lineterminator="\n")
    writer.writeheader()
    writer.writerows({"hanna_item_id": story_id, "Story": groups[story_id][1], "Prompt": groups[story_id][0]} for story_id in order)
    hanna_source.write_bytes(output.getvalue().encode("utf-8"))
    provenance_source.write_text("{}\n", encoding="utf-8")
    for number, origin in enumerate(("ai_written", "ai_written", "non_ai_written", "non_ai_written"), 1):
        item_id = f"{number:016x}"
        artifact = private / f"{item_id}.md"
        context = private / f"{item_id}.context.md"
        task = private / f"{item_id}.task-contract.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        story_id = selected_ids[number - 1]
        artifact.write_text(groups[story_id][1], encoding="utf-8")
        context.write_text(groups[story_id][0], encoding="utf-8")
        task.write_text(json.dumps(_contract(item_id), sort_keys=True), encoding="utf-8")
        items.append({"executor_id": item_id, "artifact": _binding(artifact), "contexts": [_binding(context)], "task_contract": _binding(task)})
        authority_items.append({"executor_id": item_id, "hanna_item_id": story_id, "actual_origin": origin, "source_model": "writer-model-a" if origin == "ai_written" else "human-source", "matching_stratum": "stratum-a" if number in {1, 3} else "stratum-b"})
    provenance_source.write_text(json.dumps({"format_version": 1, "records": [{key: item[key] for key in ("hanna_item_id", "actual_origin", "source_model", "matching_stratum")} for item in authority_items]}, sort_keys=True), encoding="utf-8")
    (private / "pilot-inputs.json").write_text(json.dumps({"format_version": 1, "base_study_id": "hbq-ai-writer-preface-v1", "phase": "pilot", "items": items}, sort_keys=True), encoding="utf-8")
    (private / "hanna-provenance-authority.json").write_text(json.dumps({"format_version": 1, "base_study_id": "hbq-ai-writer-preface-v1", "parent_hanna_dataset": _binding(parent_hanna_dataset), "hanna_source": _binding(hanna_source), "provenance_source": _binding(provenance_source), "projection_receipt": _write_projection(private, authority_items), "items": authority_items}, sort_keys=True), encoding="utf-8")
    return private


def _complete_fixture(executor, private: Path, work: Path, cell: dict[str, object], session_id: str) -> None:
    terminal = private / executor.PRIVATE_CELLS / f"{int(cell['sequence']):04d}" / "terminal.json"
    terminal.parent.mkdir(parents=True, exist_ok=True)
    item = executor._item(private, str(cell["item_id"]))
    artifact_text = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8")
    _, question_ids, _ = executor._rendered_prompt(item, str(cell["arm"]))
    response = json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.5, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": artifact_text[:120], "summary": None}], "note": "fixture"} for question_id in question_ids]})
    provider = {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": session_id}}
    verdicts = executor._reparse_verdicts(response, item, cell)
    terminal.write_text(json.dumps({"format_version": 1, "status": "completed", "cell": cell, "response": response, "response_sha256": _sha(response), "provider_record": provider, "provider_record_sha256": _sha(json.dumps(provider, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), "session_id_sha256": _sha(session_id), "verdicts": verdicts, "verdicts_sha256": _sha(json.dumps(verdicts, ensure_ascii=False, sort_keys=True, separators=(",", ":")))}, sort_keys=True), encoding="utf-8")
    executor._append(work / executor.PUBLIC_JOURNAL, {"event": "attempt-intent", **cell})
    executor._append(work / executor.PUBLIC_JOURNAL, {"event": "completed", "sequence": cell["sequence"], "prompt_sha256": cell["prompt_sha256"], "private_terminal_sha256": _sha(terminal.read_bytes()), "provider_record_sha256": _sha(json.dumps(provider, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), "session_id_sha256": _sha(session_id), "verdicts_sha256": _sha(json.dumps(verdicts, ensure_ascii=False, sort_keys=True, separators=(",", ":")))})


def test_prepare_freezes_exact_24_cell_geometry_and_does_not_call_provider(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    result = executor.prepare(work, private)
    rows = executor._rows(work / executor.PUBLIC_SCHEDULE)
    assert result == {"provider_calls": 0, "pilot_cells": 24, "scored_cells_remaining": 24}
    assert len(rows) == 24
    assert {(row["arm"], row["fresh_session"]) for row in rows} == {("none", 1), ("none", 2), ("current_full", 1), ("current_full", 2), ("strictness_only", 1), ("strictness_only", 2)}
    assert all("actual_origin" not in row for row in rows)
    binding = json.loads((work / executor.PUBLIC_BINDING).read_text(encoding="utf-8"))
    assert binding["actual_provenance"].startswith("private")
    assert "actual_origin" not in json.dumps(binding)


def test_rendering_changes_only_the_frozen_arm_prefix_and_never_injects_actual_origin(tmp_path: Path):
    executor = _executor()
    private = _private_root(tmp_path)
    item = executor._private_manifest(private)["items"][0]
    none, ids, payload = executor._rendered_prompt(item, "none")
    current, current_ids, current_payload = executor._rendered_prompt(item, "current_full")
    strict, strict_ids, strict_payload = executor._rendered_prompt(item, "strictness_only")
    assert ids == current_ids == strict_ids
    assert payload == current_payload == strict_payload
    assert none != current != strict
    assert "ai_written" not in current and "ai_written" not in strict and "ai_written" not in none
    assert executor._prefix("current_full") in current
    assert executor._prefix("strictness_only") in strict


def test_prepare_rejects_provenance_mismatch_and_overlapping_evidence_roots(tmp_path: Path):
    executor = _executor()
    private = _private_root(tmp_path)
    authority = json.loads((private / "hanna-provenance-authority.json").read_text(encoding="utf-8"))
    authority["items"][3]["actual_origin"] = "ai_written"
    (private / "hanna-provenance-authority.json").write_text(json.dumps(authority), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        executor.prepare(tmp_path / "public", private)
    with pytest.raises(ValueError, match="disjoint"):
        executor.prepare(private / "overlap", private)


def test_prepare_rejects_context_provenance_metadata_leak(tmp_path: Path):
    executor = _executor()
    private = _private_root(tmp_path)
    context = private / "0000000000000001.context.md"
    context.write_text("source_model: forbidden outbound metadata\n", encoding="utf-8")
    manifest = json.loads((private / "pilot-inputs.json").read_text(encoding="utf-8"))
    manifest["items"][0]["contexts"] = [_binding(context)]
    (private / "pilot-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="(context leaks|artifact/context)"):
        executor.prepare(tmp_path / "public", private)


def test_prepare_requires_exact_hanna_story_and_prompt_bindings_and_feasible_matching_strata(tmp_path: Path):
    executor = _executor()
    private = _private_root(tmp_path)
    artifact = private / "0000000000000001.md"
    artifact.write_text("not the selected HANNA Story", encoding="utf-8")
    manifest = json.loads((private / "pilot-inputs.json").read_text(encoding="utf-8"))
    manifest["items"][0]["artifact"] = _binding(artifact)
    (private / "pilot-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Story/Prompt"):
        executor.prepare(tmp_path / "public", private)

    private = _private_root(tmp_path / "strata")
    authority = json.loads((private / "hanna-provenance-authority.json").read_text(encoding="utf-8"))
    provenance = json.loads((private / "provenance-authority.json").read_text(encoding="utf-8"))
    authority["items"][2]["matching_stratum"] = "stratum-b"
    provenance["records"][2]["matching_stratum"] = "stratum-b"
    (private / "provenance-authority.json").write_text(json.dumps(provenance), encoding="utf-8")
    authority["provenance_source"] = _binding(private / "provenance-authority.json")
    authority["projection_receipt"] = _write_projection(private, authority["items"])
    (private / "hanna-provenance-authority.json").write_text(json.dumps(authority), encoding="utf-8")
    with pytest.raises(ValueError, match="matching strata"):
        executor.prepare(tmp_path / "public-strata", private)


def test_prepare_rejects_a_hanna_projection_that_no_longer_matches_its_pinned_receipt(tmp_path: Path):
    executor = _executor()
    private = _private_root(tmp_path)
    projection = private / "hanna-projection.json"
    payload = json.loads(projection.read_text(encoding="utf-8"))
    payload["items"][0]["story"] = "tampered"
    projection.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="projection output"):
        executor.prepare(tmp_path / "public", private)


def test_prepare_rejects_wrong_pinned_hanna_parent_hash(tmp_path: Path):
    executor = _executor()
    private = _private_root(tmp_path)
    parent = private / "hanna-parent-dataset.csv"
    parent.write_bytes(parent.read_bytes() + b"\n")
    authority = json.loads((private / "hanna-provenance-authority.json").read_text(encoding="utf-8"))
    authority["parent_hanna_dataset"] = _binding(parent)
    (private / "hanna-provenance-authority.json").write_text(json.dumps(authority), encoding="utf-8")
    with pytest.raises(ValueError, match="pinned exact source hash"):
        executor.prepare(tmp_path / "public", private)


def test_real_hanna_extraction_rejects_inconsistent_annotation_duplicates(tmp_path: Path):
    executor = _executor()
    with PINNED_HANNA.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames
        rows = [next(reader) for _ in range(3)]
    rows[1]["Prompt"] = "inconsistent fixture prompt"
    parent = tmp_path / "bad-parent.csv"
    with parent.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="disagrees"):
        executor._hanna_story_prompt_projection(parent)


def test_execute_requires_explicit_remote_gate_before_any_capacity_or_provider_call(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    with pytest.raises(ValueError, match="allow-remote"):
        executor.execute_one(work, private)
    assert not (work / executor.CLAIM).exists()
    assert not (work / executor.PUBLIC_JOURNAL).exists()


def test_capacity_receipt_is_sequence_bound_and_freshness_bound(tmp_path: Path):
    executor = _executor()
    path = tmp_path / "capacity-preflight-0001-v0001.json"
    receipt = {"format_version": 1, "study_id": executor.contract()["study_id"], "sequence": 1, "version": 1, "status": "ready", "observed_at": datetime.now(UTC).isoformat(), "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}, "prompt_sha256": "a" * 64, "response_sha256": "b" * 64, "provider_record_sha256": "d" * 64, "session_id_sha256": "e" * 64, "private_terminal_sha256": "c" * 64}
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON object"):
        executor._parse_capacity(path, 1, tmp_path / "private")


def test_contract_forbids_non_gpt_paid_or_writer_side_execution():
    executor = _executor()
    value = executor.contract()
    assert value["provider"]["model"] == "gpt-5.6-sol"
    assert value["provider"]["paid_api"] is False
    assert "writer-side Experiment B" in value["out_of_scope"]


def test_current_full_uses_the_exact_production_text_composition_and_safe_render_command(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    current = executor._binary_prompt_for_arm("current_full")
    assert len(current.encode("utf-8")) == 2644
    assert _sha(current) == "5498a254cc9e3fe2ce2fcfa11aab318bd0b4996c1c441f0a7d540d9b1bfc7e96"
    preview = executor.render_next_disclosure(work, private)
    assert preview["provider_calls"] == 0
    assert "actual_origin" not in json.dumps(preview["disclosure"])
    assert "source_model" not in json.dumps(preview["disclosure"])


def test_duplicate_private_session_commitments_fail_closed(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    rows = executor._rows(work / executor.PUBLIC_SCHEDULE)
    for cell in rows[:2]:
        terminal = private / executor.PRIVATE_CELLS / f"{cell['sequence']:04d}" / "terminal.json"
        terminal.parent.mkdir(parents=True, exist_ok=True)
        item = executor._item(private, cell["item_id"])
        artifact_text = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8")
        provider = {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "same-session"}}
        _, question_ids, _ = executor._rendered_prompt(item, cell["arm"])
        response = json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.5, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": artifact_text[:120], "summary": None}], "note": "fixture"} for question_id in question_ids]})
        verdicts = executor._reparse_verdicts(response, item, cell)
        terminal.write_text(json.dumps({"format_version": 1, "status": "completed", "cell": cell, "response": response, "response_sha256": _sha(response), "provider_record": provider, "provider_record_sha256": _sha(json.dumps(provider, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), "session_id_sha256": _sha("same-session"), "verdicts": verdicts, "verdicts_sha256": _sha(json.dumps(verdicts, ensure_ascii=False, sort_keys=True, separators=(",", ":")))}, sort_keys=True), encoding="utf-8")
        executor._append(work / executor.PUBLIC_JOURNAL, {"event": "attempt-intent", **cell})
        executor._append(work / executor.PUBLIC_JOURNAL, {"event": "completed", "sequence": cell["sequence"], "prompt_sha256": cell["prompt_sha256"], "private_terminal_sha256": _sha(terminal.read_bytes()), "provider_record_sha256": _sha(json.dumps(provider, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), "session_id_sha256": _sha("same-session"), "verdicts_sha256": _sha(json.dumps(verdicts, ensure_ascii=False, sort_keys=True, separators=(",", ":")))})
    with pytest.raises(ValueError, match="reused"):
        executor._completed(work, rows, private)


def test_offline_zero_contact_orphan_adjudication_allows_only_provable_pre_dispatch_gap(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    cell = executor._rows(work / executor.PUBLIC_SCHEDULE)[0]
    claim = work / executor.CLAIM
    claim.write_text(json.dumps({"format_version": 1, "pid": 99999999, "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((executor.HERE / "executor.py").read_bytes()), "pre_intent_journal_sha256": _sha(b"")}), encoding="utf-8")
    attempt = private / executor.PRIVATE_CELLS / "0001" / "attempt-intent.json"
    attempt.parent.mkdir(parents=True, exist_ok=True)
    attempt.write_text(json.dumps({"cell": cell, "claim_sha256": _sha(claim.read_bytes())}), encoding="utf-8")
    executor._append(work / executor.PUBLIC_JOURNAL, {"event": "attempt-intent", **cell})
    result = executor.adjudicate_orphan(work, private)
    assert result["status"] == "zero_contact_orphan_adjudicated"
    assert executor._completed(work, executor._rows(work / executor.PUBLIC_SCHEDULE), private) == []


def test_dead_zero_contact_capacity_claim_is_sealed_before_a_new_version_can_be_started(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    claim = work / executor.CLAIM
    claim.write_text(json.dumps({"format_version": 1, "pid": 99999999, "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((executor.HERE / "executor.py").read_bytes()), "pre_intent_journal_sha256": _sha(b"")}), encoding="utf-8")
    attempt = private / executor.PRIVATE_CAPACITY / "0001" / "v0001" / "attempt-intent.json"
    attempt.parent.mkdir(parents=True, exist_ok=True)
    attempt.write_text(json.dumps({"format_version": 1, "sequence": 1, "version": 1, "status": "started", "kind": "unscored_capacity_preflight", "prompt_sha256": "a" * 64}), encoding="utf-8")
    executor._adjudicate_zero_contact_capacity_orphan(work, private, executor._rows(work / executor.PUBLIC_SCHEDULE), 1)
    assert not claim.exists()
    public = json.loads((work / "capacity-zero-contact-0001-v0001.json").read_text(encoding="utf-8"))
    assert public["status"] == "zero_contact_proved"
    assert public["version"] == 1


def test_capacity_dispatch_marker_makes_a_crash_ambiguous_and_nonrenewable(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    claim = work / executor.CLAIM
    claim.write_text(json.dumps({"format_version": 1, "pid": 99999999, "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((executor.HERE / "executor.py").read_bytes()), "pre_intent_journal_sha256": _sha(b"")}), encoding="utf-8")
    attempt_root = private / executor.PRIVATE_CAPACITY / "0001" / "v0001"
    attempt_root.mkdir(parents=True, exist_ok=True)
    (attempt_root / "attempt-intent.json").write_text(json.dumps({"format_version": 1, "sequence": 1, "version": 1, "status": "started", "kind": "unscored_capacity_preflight", "prompt_sha256": "a" * 64}), encoding="utf-8")
    (attempt_root / "dispatch-start.json").write_text(json.dumps({"format_version": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="contact cannot be disproved"):
        executor._adjudicate_zero_contact_capacity_orphan(work, private, executor._rows(work / executor.PUBLIC_SCHEDULE), 1)
    assert claim.exists()


def test_later_cell_zero_contact_capacity_recovery_binds_the_current_journal_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    schedule = executor._rows(work / executor.PUBLIC_SCHEDULE)
    monkeypatch.setattr(executor, "_completed", lambda *_args: [dict(schedule[0])])
    executor._append(work / executor.PUBLIC_JOURNAL, {"event": "already-settled-fixture"})
    prefix = (work / executor.PUBLIC_JOURNAL).read_bytes()
    claim = work / executor.CLAIM
    claim.write_text(json.dumps({"format_version": 1, "pid": 99999999, "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((executor.HERE / "executor.py").read_bytes()), "pre_intent_journal_sha256": _sha(prefix)}), encoding="utf-8")
    attempt = private / executor.PRIVATE_CAPACITY / "0002" / "v0001" / "attempt-intent.json"
    attempt.parent.mkdir(parents=True, exist_ok=True)
    attempt.write_text(json.dumps({"format_version": 1, "sequence": 2, "version": 1, "status": "started", "kind": "unscored_capacity_preflight", "prompt_sha256": "a" * 64}), encoding="utf-8")
    executor._adjudicate_zero_contact_capacity_orphan(work, private, schedule, 2)
    authority = json.loads((work / "capacity-zero-contact-0002-v0001.json").read_text(encoding="utf-8"))
    assert authority["journal_prefix_sha256"] == _sha(prefix)
    assert not claim.exists()


def test_later_cell_stale_capacity_receipt_can_renew_despite_prior_completed_cells(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    schedule = executor._rows(work / executor.PUBLIC_SCHEDULE)
    monkeypatch.setattr(executor, "_completed", lambda *_args: [dict(schedule[0])])
    real_runner = executor._runner()

    class FakeRunner:
        calls = 0

        @classmethod
        def _call_codex(cls, **_kwargs):
            cls.calls += 1
            return '{"ready":true}', {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"capacity-session-{cls.calls}"}}

        def __getattr__(self, name: str):
            return getattr(real_runner, name)

    fake_runner = FakeRunner()
    monkeypatch.setattr(executor, "_runner", lambda: fake_runner)
    first = executor.run_capacity_preflight(work, private, allow_remote=True)
    assert first["sequence"] == 2 and first["version"] == 1
    receipt_path = work / "capacity-preflight-0002-v0001.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["observed_at"] = "2000-01-01T00:00:00+00:00"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    second = executor.run_capacity_preflight(work, private, allow_remote=True)
    assert second["sequence"] == 2 and second["version"] == 2
    assert FakeRunner.calls == 2


def test_stale_orphan_and_post_journal_epoch_claims_are_cleaned_without_dispatch(tmp_path: Path):
    executor = _executor()
    private, work = _private_root(tmp_path), tmp_path / "public"
    executor.prepare(work, private)
    schedule = executor._rows(work / executor.PUBLIC_SCHEDULE)
    claim = work / executor.CLAIM
    claim.write_text(json.dumps({"format_version": 1, "pid": 99999999, "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((executor.HERE / "executor.py").read_bytes()), "pre_intent_journal_sha256": _sha(b"")}), encoding="utf-8")
    stale_hash = _sha(claim.read_bytes())
    (work / executor.ORPHAN_CLAIM).write_text(json.dumps({"format_version": 1, "pid": 99999999, "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((executor.HERE / "executor.py").read_bytes()), "stale_claim_sha256": stale_hash}), encoding="utf-8")
    executor._cleanup_stale_orphan_claim(work, stale_claim_sha256=stale_hash)
    assert not (work / executor.ORPHAN_CLAIM).exists()
    executor._cleanup_completed_epoch_claim(work, private, schedule)
    assert not claim.exists()


def test_private_capacity_terminal_and_provider_record_are_cryptographically_bound(tmp_path: Path):
    executor = _executor()
    private = tmp_path / "private"
    terminal = private / executor.PRIVATE_CAPACITY / "0001" / "v0001" / "terminal.json"
    terminal.parent.mkdir(parents=True, exist_ok=True)
    provider_record = {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "private-session"}}
    prompt = "capacity prompt"
    response = '{"ready":true}'
    (terminal.parent / "attempt-intent.json").write_text(json.dumps({"prompt_sha256": _sha(prompt), "version": 1}), encoding="utf-8")
    terminal_value = {"format_version": 1, "status": "ready", "prompt_sha256": _sha(prompt), "response": response, "response_sha256": _sha(response), "provider_record": provider_record, "error_sha256": None}
    terminal.write_text(json.dumps(terminal_value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    receipt = tmp_path / "capacity-preflight-0001-v0001.json"
    receipt.write_text(json.dumps({"format_version": 1, "study_id": executor.contract()["study_id"], "sequence": 1, "version": 1, "status": "ready", "observed_at": datetime.now(UTC).isoformat(), "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}, "prompt_sha256": _sha(prompt), "response_sha256": _sha(response), "provider_record_sha256": _sha(json.dumps(provider_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), "session_id_sha256": _sha("private-session"), "private_terminal_sha256": _sha(terminal.read_bytes())}), encoding="utf-8")
    assert executor._parse_capacity(receipt, 1, private)["status"] == "ready"
    terminal_value["provider_record"]["reported"]["model"] = "gpt-5.6-luna"
    terminal.write_text(json.dumps(terminal_value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not bind"):
        executor._parse_capacity(receipt, 1, private)
