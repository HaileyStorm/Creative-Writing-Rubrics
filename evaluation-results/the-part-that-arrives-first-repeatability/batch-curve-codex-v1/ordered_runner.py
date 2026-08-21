"""Ordered, zero-context Codex runner for the frozen batch-curve protocol."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hbqrs import load_bundles, load_modules
from hbqrs import core
from hbqrs import runner as shared
from hbqrs import scoring_v2


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_json(value) + b"\n")
    temporary.replace(path)


def _prompt(*, prefix: str, binary: str, source: Path, bundle_id: str, artifact_id: str, questions: Sequence[Mapping[str, Any]]) -> str:
    return shared._render_prompt(binary_prompt=f"{prefix.strip()}\n\n{binary.strip()}", artifact={"name": source.name, "text": source.read_text(encoding="utf-8")}, contexts=[], bundle_id=bundle_id, artifact_id=artifact_id, questions=questions)


def _rejected(*, destination: Path, number: int, prompt: str, effective_prompt: str, feedback: Mapping[str, Any] | None, content: str | None, provider: Mapping[str, Any] | None, error: Exception, retryable: bool, stage: str) -> tuple[Path, dict[str, Any]]:
    root = destination / "responses" / "rejected" / f"batch-{number:04d}"
    root.mkdir(parents=True, exist_ok=True)
    prior = shared._rejected_records(destination, number)
    path = root / f"attempt-{len(prior) + 1:04d}.json"
    if path.exists(): raise ValueError("Rejected attempt path already exists")
    all_records = sorted((destination / "responses" / "rejected").glob("batch-*/attempt-[0-9][0-9][0-9][0-9].json"))
    sequences = [json.loads(item.read_text(encoding="utf-8")).get("sequence") for item in all_records]
    if any(type(item) is not int for item in sequences) or sorted(sequences) != list(range(1, len(sequences) + 1)):
        raise ValueError("Rejected attempt sequence drifted")
    reported = provider.get("reported") if isinstance(provider, Mapping) else None
    session = reported.get("session_id") if isinstance(reported, Mapping) else None
    raw = (content or "").encode("utf-8")
    record = {"format_version": 4, "batch": number, "attempt": len(prior) + 1, "sequence": len(sequences) + 1, "previous_rejected_sha256": _sha(prior[-1][0].read_bytes()) if prior else None, "stage": stage, "retry_policy": {"batch_attempts": 3}, "prompt_sha256": _sha(effective_prompt.encode("utf-8")), "base_prompt_sha256": _sha(prompt.encode("utf-8")), "effective_prompt_sha256": _sha(effective_prompt.encode("utf-8")), "validation_feedback_policy": shared.VALIDATION_FEEDBACK_POLICY, "validation_feedback": dict(feedback) if feedback is not None else None, "raw_content": {"encoding": "utf-8", "text": content or "", "bytes": len(raw), "sha256": _sha(raw)}, "provider": shared._sanitized_provider_record(provider), "provider_session_id_sha256": _sha(session.encode("utf-8")) if isinstance(session, str) and session else None, "retryable": retryable, "error": {"class": type(error).__name__, "message": str(error)[:4000]}}
    _atomic(path, record)
    return path, record


def run(*, output_dir: Path, source: Path, registry: Path, bundles: Path, prefix: Path, binary: Path, response_schema: Path, question_items: Sequence[Mapping[str, Any]], batch_size: int, codex_bin: str, timeout_seconds: int, model: str = "gpt-5.6-sol", reasoning: str = "high", artifact_id: str = "the-part-that-arrives-first", invoke: Callable[..., Any] = shared._call_codex) -> dict[str, Any]:
    """Run an exact frozen order; every provider send has a durable precursor."""
    question_ids = [str(item.get("question", {}).get("id")) for item in question_items]
    if not question_ids or len(set(question_ids)) != len(question_ids) or any(item == "None" for item in question_ids) or type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("Ordered run needs unique frozen question IDs")
    modules = load_modules(registry)
    bundle = next(item for item in load_bundles(bundles) if item["bundle_id"] == "prose.short_story")
    ordered = list(question_items)
    chunks = [ordered[index:index + batch_size] for index in range(0, len(ordered), batch_size)]
    destination = output_dir.resolve(); destination.mkdir(parents=True, exist_ok=True)
    configuration = {"format_version": 1, "artifact_id": artifact_id, "bundle_id": "prose.short_story", "strict_ai": True, "contexts": [], "question_ids": list(question_ids), "batch_size": batch_size, "batch_attempts": 3, "timeout_seconds": timeout_seconds, "retry_semantics": "cumulative_batch_attempts_v1", "validation_feedback_policy": shared.VALIDATION_FEEDBACK_POLICY, "checkpoint_format_version": 4, "provider": {"configured": "codex", "reported": "openai", "model": model, "reasoning": reasoning}, "codex_bin": codex_bin}
    run_path = destination / "run.json"
    if run_path.exists() and json.loads(run_path.read_text(encoding="utf-8")) != configuration:
        raise ValueError("Ordered run configuration drifted")
    if not run_path.exists(): _atomic(run_path, configuration)
    previous: str | None = None; verdicts: list[dict[str, Any]] = []
    for number, questions in enumerate(chunks, 1):
        ids = [str(item["question"]["id"]) for item in questions]
        checkpoint = destination / "responses" / f"batch-{number:04d}.json"
        prompt = _prompt(prefix=prefix.read_text(encoding="utf-8"), binary=binary.read_text(encoding="utf-8"), source=source, bundle_id="prose.short_story", artifact_id=artifact_id, questions=questions)
        prompt_path = checkpoint.with_suffix(".prompt.txt.gz"); prompt_path.parent.mkdir(parents=True, exist_ok=True)
        if checkpoint.exists():
            record = json.loads(checkpoint.read_text(encoding="utf-8")); verdicts.extend(record["normalized_verdicts"]); previous = _sha(checkpoint.read_bytes()); continue
        prompt_bytes = gzip.compress(prompt.encode("utf-8"), mtime=0)
        if prompt_path.exists() and prompt_path.read_bytes() != prompt_bytes:
            raise ValueError("Persisted frozen prompt bytes drifted")
        if not prompt_path.exists(): prompt_path.write_bytes(prompt_bytes)
        rejected = shared._rejected_records(destination, number)
        if any(record.get("retryable") is False for _path, record in rejected):
            raise ValueError(f"Batch {number} has a persisted nonretryable rejection")
        for attempt in range(len(rejected) + 1, 4):
            started = destination / "responses" / "attempt-started" / f"batch-{number:04d}-attempt-{attempt:04d}.json"
            started_value = {"format_version": 1, "batch": number, "attempt": attempt, "question_ids": ids, "base_prompt_sha256": _sha(prompt.encode("utf-8"))}
            if started.exists() and json.loads(started.read_text(encoding="utf-8")) != started_value: raise ValueError("Durable attempt-started evidence drifted")
            if not started.exists(): _atomic(started, started_value)
            feedback_prompt, feedback = shared._feedback_for_rejection(base_prompt=prompt, base_prompt_sha256=_sha(prompt.encode("utf-8")), previous_rejection=rejected[-1] if rejected else None)
            content = None; provider = None
            try:
                content, provider = invoke(executable=codex_bin, model=model, reasoning=reasoning, prompt=feedback_prompt, output_dir=destination, response_schema=response_schema, batch_number=number, attempt_number=attempt, timeout=timeout_seconds)
            except shared._ProviderAttemptFailure as exc:
                rejected_path, rejected_record = _rejected(destination=destination, number=number, prompt=prompt, effective_prompt=feedback_prompt, feedback=feedback, content=exc.content, provider=exc.provider_record, error=exc, retryable=exc.retryable, stage="provider_transport")
                rejected.append((rejected_path, rejected_record))
                if not exc.retryable or attempt == 3: raise ValueError(f"Batch {number} exhausted its frozen retry budget") from exc
                continue
            except TypeError as exc:
                _rejected(destination=destination, number=number, prompt=prompt, effective_prompt=feedback_prompt, feedback=feedback, content=None, provider=None, error=exc, retryable=False, stage="local_invocation_error")
                raise ValueError(f"Batch {number} has a nonretryable programmer error") from exc
            except Exception as exc:
                rejected_path, rejected_record = _rejected(destination=destination, number=number, prompt=prompt, effective_prompt=feedback_prompt, feedback=feedback, content=content, provider=provider, error=exc, retryable=True, stage="model_output")
                rejected.append((rejected_path, rejected_record))
                if attempt == 3: raise ValueError(f"Batch {number} exhausted its frozen retry budget") from exc
                continue
            try:
                audit: list[dict[str, Any]] = []
                normalized = shared._normalize_batch(shared._parse_model_json(content), expected_ids=ids, artifact_id=artifact_id, bundle_id="prose.short_story", judge_id=f"codex:{model}", run_id="batch-curve-codex-v1", artifact_text=source.read_text(encoding="utf-8"), context_texts=[], normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
            except Exception as exc:
                rejected_path, rejected_record = _rejected(destination=destination, number=number, prompt=prompt, effective_prompt=feedback_prompt, feedback=feedback, content=content, provider=provider, error=exc, retryable=True, stage="model_output")
                rejected.append((rejected_path, rejected_record))
                if attempt == 3: raise ValueError(f"Batch {number} exhausted its frozen retry budget") from exc
                continue
            accepted = shared._write_accepted_response_artifact(output_dir=destination, batch_number=number, content=content)
            record = {"format_version": 4, "batch": number, "retry_policy": {"batch_attempts": 3}, "accepted_attempt": attempt, "question_ids": ids, "prompt_sha256": _sha(feedback_prompt.encode("utf-8")), "base_prompt_sha256": _sha(prompt.encode("utf-8")), "effective_prompt_sha256": _sha(feedback_prompt.encode("utf-8")), "validation_feedback_policy": shared.VALIDATION_FEEDBACK_POLICY, "validation_feedback": feedback, "normalization_policy": shared.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": audit, "response_sha256": _sha(content.encode("utf-8")), "response_artifact": accepted, "rejected_chain": shared._rejected_chain_binding(destination, batch_number=number, base_prompt=prompt, batch_attempts=3, normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY), "previous_checkpoint_sha256": previous, "verdicts_sha256": _sha(shared._verdicts_bytes([*verdicts, *normalized])), "provider": provider, "normalized_verdicts": normalized}
            _atomic(checkpoint, record); previous = _sha(checkpoint.read_bytes()); verdicts.extend(normalized); break
    shared._write_verdicts(destination / "verdicts.jsonl", verdicts)
    score = core.score_bundle(modules, bundle, verdicts, artifact_id=artifact_id); _atomic(destination / "score.json", score)
    score2 = scoring_v2.score_bundle(modules, bundle, verdicts, artifact_id=artifact_id); score2["parent_score_sha256"] = _sha((destination / "score.json").read_bytes()); _atomic(destination / "score.v2.json", score2)
    return {"checkpoint_chain_head_sha256": previous, "verdict_count": len(verdicts)}
