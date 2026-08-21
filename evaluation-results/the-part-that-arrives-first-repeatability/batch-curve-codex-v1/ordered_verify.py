"""Independent local replay verifier for zero-context ordered Codex runs."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from hbqrs import runner as shared
from hbqrs import core, scoring_v2
from jsonschema import Draft202012Validator
from ordered_runner import _prompt, _sha


def verify(*, run_dir: Path, source: Path, prefix: Path, binary: Path, registry: Path, bundles: Path, score_v1_schema: Path, score_v2_schema: Path, question_items: Sequence[Mapping[str, Any]], batch_size: int, codex_bin: str, artifact_id: str = "the-part-that-arrives-first") -> dict[str, Any]:
    root = run_dir.resolve(); manifest = json.loads((root / "run.json").read_text(encoding="utf-8"))
    ids = [str(item["question"]["id"]) for item in question_items]
    expected = {"format_version": 1, "artifact_id": artifact_id, "bundle_id": "prose.short_story", "strict_ai": True, "contexts": [], "question_ids": ids, "batch_size": batch_size, "batch_attempts": 3, "retry_semantics": "cumulative_batch_attempts_v1", "validation_feedback_policy": shared.VALIDATION_FEEDBACK_POLICY, "checkpoint_format_version": 4, "provider": {"configured": "codex", "reported": "openai", "model": "gpt-5.6-sol", "reasoning": "high"}, "codex_bin": codex_bin}
    if manifest != expected: raise ValueError("Ordered run manifest drifted")
    shared._validate_rejected_attempt_store(root)
    all_verdicts: list[dict[str, Any]] = []; sessions: set[str] = set(); previous = None; rejected_count = 0; expected_started: set[str] = set()
    for number, start in enumerate(range(0, len(ids), batch_size), 1):
        questions = question_items[start:start + batch_size]; expected_ids = ids[start:start + batch_size]
        path = root / "responses" / f"batch-{number:04d}.json"; record = json.loads(path.read_text(encoding="utf-8"))
        prompt = _prompt(prefix=prefix.read_text(encoding="utf-8"), binary=binary.read_text(encoding="utf-8"), source=source, bundle_id="prose.short_story", artifact_id=artifact_id, questions=questions)
        prompt_path = path.with_suffix(".prompt.txt.gz")
        if gzip.decompress(prompt_path.read_bytes()).decode("utf-8") != prompt or record.get("format_version") != 4 or record.get("question_ids") != expected_ids or record.get("previous_checkpoint_sha256") != previous or record.get("base_prompt_sha256") != _sha(prompt.encode("utf-8")) or record.get("retry_policy") != {"batch_attempts": 3} or record.get("normalization_policy") != shared.EVIDENCE_NORMALIZATION_POLICY or record.get("validation_feedback_policy") != shared.VALIDATION_FEEDBACK_POLICY: raise ValueError("Ordered v4 checkpoint or exact prompt drifted")
        response = record.get("response_artifact"); content_path = root / response["path"] if isinstance(response, Mapping) else None
        if content_path is None or not content_path.is_file() or response.get("bytes") != content_path.stat().st_size or response.get("sha256") != _sha(content_path.read_bytes()) or record.get("response_sha256") != _sha(content_path.read_bytes()): raise ValueError("Accepted raw evidence is missing")
        shared._validate_provider_artifacts(root, record)
        audit: list[dict[str, Any]] = []
        normalized = shared._normalize_batch(shared._parse_model_json(content_path.read_text(encoding="utf-8")), expected_ids=expected_ids, artifact_id=artifact_id, bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id="batch-curve-codex-v1", artifact_text=source.read_text(encoding="utf-8"), context_texts=[], normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
        expected_effective, expected_feedback = shared._feedback_for_rejection(base_prompt=prompt, base_prompt_sha256=_sha(prompt.encode("utf-8")), previous_rejection=shared._rejected_records(root, number)[-1] if shared._rejected_records(root, number) else None)
        if normalized != record.get("normalized_verdicts") or audit != record.get("normalization_audit") or record.get("validation_feedback") != expected_feedback or record.get("effective_prompt_sha256") != _sha(expected_effective.encode("utf-8")) or record.get("prompt_sha256") != _sha(expected_effective.encode("utf-8")) or record.get("verdicts_sha256") != _sha(shared._verdicts_bytes([*all_verdicts, *normalized])): raise ValueError("Accepted raw response cannot replay its verdicts")
        provider = record.get("provider", {}).get("reported", {}); session = provider.get("session_id")
        session_hash = hashlib.sha256(session.encode("utf-8")).hexdigest() if isinstance(session, str) else None
        if provider.get("provider") != "openai" or provider.get("model") != "gpt-5.6-sol" or provider.get("reasoning_effort") != "high" or not isinstance(session, str) or not session or session_hash in sessions: raise ValueError("Provider/session provenance drifted")
        sessions.add(session_hash); rejected = shared._rejected_records(root, number)
        if record.get("accepted_attempt") != len(rejected) + 1: raise ValueError("Cumulative retry evidence drifted")
        for attempt in range(1, int(record["accepted_attempt"]) + 1):
            name = f"batch-{number:04d}-attempt-{attempt:04d}.json"; expected_started.add(name)
            started_path = root / "responses" / "attempt-started" / name
            started = json.loads(started_path.read_text(encoding="utf-8")) if started_path.is_file() else None
            if started != {"format_version": 1, "batch": number, "attempt": attempt, "question_ids": expected_ids, "base_prompt_sha256": _sha(prompt.encode("utf-8"))}: raise ValueError("Durable attempt-started evidence drifted")
        if record.get("rejected_chain") != shared._rejected_chain_binding(root, batch_number=number, base_prompt=prompt, batch_attempts=3, normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY): raise ValueError("Rejected chain binding drifted")
        for attempt, (rejected_path, rejected_record) in enumerate(rejected, 1):
            raw = rejected_record.get("raw_content")
            shared._validate_provider_artifacts(root, rejected_record)
            rejected_provider = rejected_record.get("provider", {}).get("reported", {})
            rejected_session = rejected_provider.get("session_id")
            rejected_hash = rejected_record.get("provider_session_id_sha256")
            if rejected_record.get("format_version") != 4 or rejected_record.get("batch") != number or rejected_record.get("attempt") != attempt or rejected_record.get("base_prompt_sha256") != _sha(prompt.encode("utf-8")) or rejected_record.get("retryable") is not True and rejected_record.get("retryable") is not False or not isinstance(raw, Mapping) or raw.get("encoding") != "utf-8" or not isinstance(raw.get("text"), str) or raw.get("bytes") != len(raw["text"].encode("utf-8")) or raw.get("sha256") != _sha(raw["text"].encode("utf-8")) or rejected_provider.get("provider") != "openai" or rejected_provider.get("model") != "gpt-5.6-sol" or rejected_provider.get("reasoning_effort") != "high" or isinstance(rejected_session, str) or not isinstance(rejected_hash, str) or len(rejected_hash) != 64 or rejected_hash in sessions: raise ValueError("Rejected v4 raw/provider evidence drifted")
            sessions.add(rejected_hash)
            rejected_count += 1
        all_verdicts.extend(normalized); previous = _sha(path.read_bytes())
    started_root = root / "responses" / "attempt-started"
    if {path.name for path in started_root.glob("*.json")} != expected_started: raise ValueError("Attempt-started evidence has extras or gaps")
    expected_checkpoints = {f"batch-{number:04d}.json" for number in range(1, (len(ids) + batch_size - 1) // batch_size + 1)}
    if {path.name for path in (root / "responses").glob("batch-[0-9][0-9][0-9][0-9].json")} != expected_checkpoints: raise ValueError("Checkpoint store has extras or gaps")
    persisted = [json.loads(line) for line in (root / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if persisted != all_verdicts or [item["question_id"] for item in persisted] != ids: raise ValueError("Ordered verdict sequence drifted")
    modules = core.load_modules(registry); bundle = core.resolve_bundle(core.load_bundles(bundles), "prose.short_story")
    score = core.score_bundle(modules, bundle, persisted, artifact_id=artifact_id)
    if json.loads((root / "score.json").read_text(encoding="utf-8")) != score or list(Draft202012Validator(json.loads(score_v1_schema.read_text(encoding="utf-8"))).iter_errors(score)):
        raise ValueError("v1 score recomputation or schema drifted")
    score2 = scoring_v2.score_bundle(modules, bundle, persisted, artifact_id=artifact_id); score2["parent_score_sha256"] = _sha((root / "score.json").read_bytes())
    if json.loads((root / "score.v2.json").read_text(encoding="utf-8")) != score2 or list(Draft202012Validator(json.loads(score_v2_schema.read_text(encoding="utf-8"))).iter_errors(score2)):
        raise ValueError("v2 score recomputation or schema drifted")
    return {"run_sha256": _sha((root / "run.json").read_bytes()), "score_sha256": _sha((root / "score.json").read_bytes()), "score_v2_sha256": _sha((root / "score.v2.json").read_bytes()), "checkpoint_chain_head_sha256": previous, "verdict_count": len(all_verdicts), "rejected_attempt_count": rejected_count, "sessions": [{"session_id_sha256": item} for item in sorted(sessions)]}
