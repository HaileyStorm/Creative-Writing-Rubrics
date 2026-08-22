"""Schema-corrected successor for the stopped v2 batch-curve recovery."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping

from hbqrs import runner as shared


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT_PATH = HERE / "study-contract.json"
RECEIPT = "preexecution-disclosure-receipt.json"
V2_PUBLIC = Path(r"C:\Users\Haile\Documents\cwr-batch-curve-v2-live-8cd6ee5-20260822")
V2_PRIVATE = Path(r"C:\Users\Haile\Documents\cwr-batch-curve-v2-private-8cd6ee5-20260822")


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


V2 = _load("batch_curve_remainder_v2_schema_predecessor", HERE.parent / "batch-curve-codex-remainder-v2" / "batch_recovery.py")
BASE_PLAN = V2.plan
BASE_PREPARE_UNIT = V2._prepare_unit
PROTOCOL = "batch-curve-codex-remainder-v3-cap1"
RUN_ID = "batch-curve-codex-remainder-v3"


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp"); temp.write_bytes(_bytes(value) + b"\n"); temp.replace(path)


def _same(left: Any, right: Any) -> bool:
    if type(left) is not type(right): return False
    if isinstance(left, dict): return set(left) == set(right) and all(_same(item, right[key]) for key, item in left.items())
    if isinstance(left, list): return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def _bound(binding: Mapping[str, Any]) -> Path:
    if set(binding) != {"path", "bytes", "sha256"} or not isinstance(binding.get("path"), str) or type(binding.get("bytes")) is not int or not isinstance(binding.get("sha256"), str):
        raise ValueError("Binding shape drifted")
    path = (HERE / binding["path"]).resolve()
    if not path.is_file() or path.stat().st_size != binding["bytes"] or _sha_path(path) != binding["sha256"]:
        raise ValueError(f"Bound bytes drifted: {binding['path']}")
    return path


def _tree(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir(): raise ValueError("Frozen predecessor root is unavailable")
    return [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha_path(path)} for path in sorted(root.rglob("*")) if path.is_file()]


def contract() -> dict[str, Any]:
    value = _read(CONTRACT_PATH)
    expected = {"format_version", "study_id", "status", "lineage", "current_stack", "predecessor", "execution", "privacy"}
    if set(value) != expected or value.get("format_version") != 3 or value.get("study_id") != "the-part-that-arrives-first-batch-curve-codex-remainder-v3" or value.get("status") != "preregistered_live_recovery_no_results":
        raise ValueError("Recovery contract shape drifted")
    if set(value["lineage"]) != {"remainder_contract", "remainder_module", "codex_v1_contract", "v2_contract"}:
        raise ValueError("Recovery lineage binding set drifted")
    required_stack = {"source", "registry", "bundles", "prefix", "binary", "response_schema", "preflight_schema", "score_v1_schema", "score_v2_schema", "v2_contract", "harness", "runner", "core", "scoring_v2", "executor"}
    if set(value["current_stack"]) != required_stack:
        raise ValueError("Current runtime binding set drifted")
    for binding in [*value["lineage"].values(), *value["current_stack"].values()]: _bound(binding)
    execution = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "logical_units": 47, "max_physical_attempts_per_unit": 1, "planned_epoch_preflights": 6, "preflight_epoch_units": 8, "timeout_seconds": 600, "preflight_max_age_minutes": 15, "inherited_preflight_provider_calls": 1, "inherited_scored_provider_calls": 0, "result_status": "incomplete_nonlive_analysis_pending"}
    if value["execution"] != execution or set(value["privacy"]) != {"remote_destination", "outbound", "raw_evidence", "public_projection"}:
        raise ValueError("Recovery execution or privacy contract drifted")
    return value


def _stack(name: str) -> Path:
    return _bound(contract()["current_stack"][name])


def _predecessor() -> dict[str, Any]:
    value = contract()["predecessor"]
    if set(value) != {"v2_public", "v2_private", "old_schema", "attempt"} or value["v2_public"].get("path") != str(V2_PUBLIC) or value["v2_private"].get("path") != str(V2_PRIVATE):
        raise ValueError("Frozen v2 predecessor identity drifted")
    for key, root in (("v2_public", V2_PUBLIC), ("v2_private", V2_PRIVATE)):
        record = value[key]
        if set(record) != {"path", "files"} or record["files"] != _tree(root):
            raise ValueError("Frozen v2 predecessor tree drifted")
    attempt = value["attempt"]
    if attempt != {"logical_attempt": 1, "epoch": 1, "refresh": 1, "status": "failed_invalid_json_schema", "scored_provider_calls": 0}:
        raise ValueError("Frozen v2 attempt accounting drifted")
    if _read(_bound(value["old_schema"])) != {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "required": ["ready"], "properties": {"ready": {"const": True}}}:
        raise ValueError("Frozen v2 invalid preflight schema drifted")
    public = _read(V2_PUBLIC / "preflights/epoch-0001/refresh-0001.json")
    private = _read(V2_PRIVATE / "preflights/epoch-0001/refresh-0001.json/preflight-outcome.json")
    message = private.get("error", {}).get("message") if isinstance(private.get("error"), Mapping) else None
    if public.get("study_id") != "the-part-that-arrives-first-batch-curve-codex-remainder-v2" or public.get("status") != "failed" or public.get("refresh") != 1 or public.get("private_sha256") != _sha_path(V2_PRIVATE / public.get("private_path", "")) or private.get("content") is not None or not isinstance(message, str) or "invalid_json_schema" not in message or "must have a 'type' key" not in message:
        raise ValueError("Frozen v2 invalid-schema evidence drifted")
    if (V2_PUBLIC / "cells").exists() or (V2_PRIVATE / "runs").exists():
        raise ValueError("Frozen v2 predecessor contains scored work")
    return value


def plan() -> list[dict[str, Any]]:
    contract(); _predecessor(); rows = BASE_PLAN()
    if len(rows) != 47 or any(row["parent_cell"] == 36 and row["batch"] <= 31 for row in rows):
        raise ValueError("Recovery schedule is not exactly the sealed remainder")
    return rows


def _git_state(run: Callable[..., Any]) -> dict[str, str]:
    def command(args: list[str]) -> str:
        done = run(args, cwd=ROOT, capture_output=True, text=True, check=False)
        if getattr(done, "returncode", 1) != 0: raise ValueError("Cannot establish exact pushed source state")
        return str(getattr(done, "stdout", "")).strip()
    head, remote = command(["git", "rev-parse", "HEAD"]), command(["git", "rev-parse", "origin/main"])
    if head != remote or len(head) != 40 or command(["git", "status", "--porcelain=v1", "--untracked-files=all"]):
        raise ValueError("Recovery requires a clean committed pushed exact HEAD")
    for path in (CONTRACT_PATH, HERE / "batch_recovery.py", HERE / "capacity-preflight.schema.json"):
        relative = path.resolve().relative_to(ROOT).as_posix(); done = run(["git", "ls-files", "--error-unmatch", relative], cwd=ROOT, capture_output=True, text=True, check=False)
        if getattr(done, "returncode", 1) != 0 or str(getattr(done, "stdout", "")).strip() != relative: raise ValueError("Recovery source must be tracked at exact HEAD")
    return {"head": head, "remote": "origin/main"}


def _runtime(executable: str, run: Callable[..., Any], resolve: Callable[[str], str | None]) -> dict[str, str]:
    resolved = resolve(executable)
    if not resolved: raise ValueError("Codex executable cannot be resolved")
    done = run([resolved, "--version"], capture_output=True, text=True, check=False); version = str(getattr(done, "stdout", "")).strip()
    if getattr(done, "returncode", 1) != 0 or not version: raise ValueError("Native Codex runtime probe failed")
    return {"executable": str(Path(resolved).resolve()), "version": version}


def _root_sha(path: Path) -> str:
    return _sha_text(str(path.resolve()))


def _overlap(left: Path, right: Path) -> bool:
    first, second = left.resolve(), right.resolve()
    return first == second or first in second.parents or second in first.parents


def _receipt(private_root: Path, executable: str, run: Callable[..., Any], resolve: Callable[[str], str | None]) -> dict[str, Any]:
    value = contract(); predecessor = _predecessor()
    return {"format_version": 3, "study_id": value["study_id"], "contract_sha256": _sha_path(CONTRACT_PATH), "git": _git_state(run), "runtime": _runtime(executable, run, resolve), "private_evidence_root_sha256": _root_sha(private_root), "stack_sha256": hashlib.sha256(_bytes(value["current_stack"])).hexdigest(), "schedule": plan(), "predecessor_sha256": _sha_text(json.dumps(predecessor, sort_keys=True, separators=(",", ":"))), "inherited_preflight_provider_calls": 1, "inherited_scored_provider_calls": 0, "outbound_disclosure": value["privacy"], "provider_calls_made": 0}


def _fresh_roots(work_root: Path, private_root: Path) -> None:
    protected = [V2_PUBLIC.resolve(), V2_PRIVATE.resolve(), ROOT]
    if work_root.exists() or private_root.exists() or _overlap(work_root, private_root) or any(_overlap(root, protected_root) for root in (work_root, private_root) for protected_root in protected):
        raise ValueError("Recovery needs fresh external public and private roots")


def prepare(work_root: Path, private_root: Path, *, executable: str = "codex", subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    plan(); _fresh_roots(work_root, private_root); work_root.mkdir(parents=True); private_root.mkdir(parents=True)
    receipt = _receipt(private_root, executable, subprocess_run, executable_resolver); _atomic(work_root / RECEIPT, receipt)
    return receipt


def _names(path: Path) -> set[str]:
    if not path.is_dir(): raise ValueError(f"Expected directory: {path}")
    return {item.name for item in path.iterdir()}


def _validate_prepared(work_root: Path, private_root: Path, *, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    if not work_root.is_dir() or not private_root.is_dir() or _overlap(work_root, private_root): raise ValueError("Recovery roots are unavailable")
    if not _names(work_root) <= {RECEIPT, "preflights", "cells", "claims", "analysis.json"} or not _names(private_root) <= {"preflights", "runs", "evidence-index"}: raise ValueError("Recovery root has an unbound member")
    receipt = _read(work_root / RECEIPT); expected = _receipt(private_root, receipt.get("runtime", {}).get("executable", "codex"), subprocess_run, executable_resolver)
    if not _same(receipt, expected): raise ValueError("Prepared recovery is not current pushed source/runtime")
    return receipt


def _preflight_schema() -> Path:
    path = _stack("preflight_schema")
    expected = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "required": ["ready"], "properties": {"ready": {"type": "boolean", "const": True}}}
    if _read(path) != expected: raise ValueError("V3 preflight schema is not the strict ready boolean schema")
    return path


def _refresh_numbers(directory: Path, *, private: bool) -> set[int]:
    if not directory.is_dir(): return set()
    result: set[int] = set()
    for path in directory.glob("refresh-[0-9][0-9][0-9][0-9].json"):
        if path.is_dir() != private: raise ValueError("Native preflight refresh has an invalid path type")
        result.add(int(path.name[8:12]))
    return result


def _settle_private_only_preflights(work_root: Path, private_root: Path, epoch: int) -> None:
    public_dir = work_root / "preflights" / f"epoch-{epoch:04d}"; private_dir = private_root / "preflights" / f"epoch-{epoch:04d}"
    public_numbers = _refresh_numbers(public_dir, private=False); private_numbers = _refresh_numbers(private_dir, private=True); used = public_numbers | private_numbers
    if used and used != set(range(1, max(used) + 1)): raise ValueError("Native preflight refresh sequence has a gap or collision")
    required = {"format_version", "study_id", "epoch", "refresh", "previous_public_sha256", "checked_at", "git", "runtime", "model", "reasoning", "native_argv", "receipt_sha256", "status", "account_surface_sha256", "response_sha256", "error", "content", "provider"}
    for number in sorted(private_numbers - public_numbers):
        outcome = private_dir / f"refresh-{number:04d}.json" / "preflight-outcome.json"
        if not outcome.is_file(): raise ValueError("Private-only preflight cannot be adjudicated without terminal evidence")
        private_value = _read(outcome)
        if set(private_value) != required or private_value.get("format_version") != 3 or private_value.get("epoch") != epoch or private_value.get("refresh") != number or private_value.get("study_id") != contract()["study_id"] or private_value.get("status") not in {"accepted", "failed"}: raise ValueError("Private-only preflight terminal evidence is malformed")
        public_value = {key: item for key, item in private_value.items() if key not in {"content", "provider"}}
        public_value.update({"private_path": outcome.relative_to(private_root).as_posix(), "private_bytes": outcome.stat().st_size, "private_sha256": _sha_path(outcome)})
        _atomic(public_dir / f"refresh-{number:04d}.json", public_value)


def _preflight_paths(work_root: Path, private_root: Path, epoch: int) -> tuple[Path, Path, int]:
    if type(epoch) is not int or epoch < 1: raise ValueError("Epoch must be a positive integer")
    public = work_root / "preflights" / f"epoch-{epoch:04d}"; private = private_root / "preflights" / f"epoch-{epoch:04d}"
    _settle_private_only_preflights(work_root, private_root, epoch)
    numbers = _refresh_numbers(public, private=False) | _refresh_numbers(private, private=True)
    if numbers and numbers != set(range(1, max(numbers) + 1)): raise ValueError("Native preflight refresh sequence has a gap or collision")
    return public, private, max(numbers, default=0) + 1


def native_preflight(work_root: Path, private_root: Path, *, epoch: int, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which, now: datetime | None = None, invoke: Callable[..., Any] = shared._call_codex) -> dict[str, Any]:
    now = now or datetime.now().astimezone(); receipt = _validate_prepared(work_root, private_root, subprocess_run=subprocess_run, executable_resolver=executable_resolver)
    value = contract(); schema = _preflight_schema(); public_dir, private_dir, refresh = _preflight_paths(work_root, private_root, epoch)
    logical_attempt = refresh + (1 if epoch == 1 else 0); private = private_dir / f"refresh-{refresh:04d}.json"; public = public_dir / f"refresh-{refresh:04d}.json"
    private.mkdir(parents=True, exist_ok=False)
    previous = public_dir / f"refresh-{refresh - 1:04d}.json"
    base = {"format_version": 3, "study_id": value["study_id"], "epoch": epoch, "refresh": refresh, "previous_public_sha256": _sha_path(previous) if refresh > 1 else None, "checked_at": now.isoformat(), "git": receipt["git"], "runtime": receipt["runtime"], "model": value["execution"]["model"], "reasoning": value["execution"]["reasoning"], "native_argv": ["exec", "--model", value["execution"]["model"]], "receipt_sha256": _sha_path(work_root / RECEIPT)}
    def terminal(status: str, *, content: str | None, provider: Mapping[str, Any] | None, error: Exception | None = None) -> dict[str, Any]:
        reported = provider.get("reported") if isinstance(provider, Mapping) else None; session = reported.get("session_id") if isinstance(reported, Mapping) else None
        record = {**base, "status": status, "account_surface_sha256": _sha_text(session) if isinstance(session, str) and session else None, "response_sha256": _sha_text(content) if isinstance(content, str) else None, "error": None if error is None else {"class": type(error).__name__, "message": str(error)}}
        private_value = {**record, "content": content, "provider": provider}; _atomic(private / "preflight-outcome.json", private_value); saved = _read(private / "preflight-outcome.json")
        public_value = {**record, "private_path": (private / "preflight-outcome.json").relative_to(private_root).as_posix(), "private_bytes": len(_bytes(saved)) + 1, "private_sha256": hashlib.sha256(_bytes(saved) + b"\n").hexdigest()}; _atomic(public, public_value)
        result = _read(public); result["logical_attempt"] = logical_attempt; return result
    try:
        content, provider = invoke(executable=receipt["runtime"]["executable"], model=value["execution"]["model"], reasoning=value["execution"]["reasoning"], prompt="Return exactly the JSON object {\"ready\":true} and no other text.", output_dir=private, response_schema=schema, batch_number=1, attempt_number=logical_attempt, timeout=value["execution"]["timeout_seconds"])
    except shared._ProviderAttemptFailure as error:
        terminal("failed", content=error.content, provider=error.provider_record, error=error); raise ValueError("Native Codex capacity preflight failed") from error
    try:
        if json.loads(content) != {"ready": True}: raise ValueError("unexpected preflight response")
    except (json.JSONDecodeError, ValueError) as error:
        terminal("failed", content=content, provider=provider, error=error); raise ValueError("Native Codex capacity preflight returned malformed output") from error
    reported = provider.get("reported") if isinstance(provider, Mapping) else None; session = reported.get("session_id") if isinstance(reported, Mapping) else None
    if not isinstance(session, str) or not session:
        terminal("failed", content=content, provider=provider, error=ValueError("missing session identity")); raise ValueError("Native Codex capacity preflight lacks session identity")
    return terminal("accepted", content=content, provider=provider)


def _prepare_unit(private_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    prepared = dict(BASE_PREPARE_UNIT(private_root, row)); configuration = dict(prepared["configuration"])
    configuration["protocol"] = PROTOCOL; prepared["configuration"] = configuration
    return prepared


def _expected_run(row: Mapping[str, Any]) -> dict[str, Any]:
    value = contract()
    return {"format_version": 1, "protocol": PROTOCOL, "plan": dict(row), "artifact_id": "the-part-that-arrives-first", "bundle_id": "prose.short_story", "batch_attempts": 1, "timeout_seconds": value["execution"]["timeout_seconds"], "provider": {"configured": "codex", "reported": "openai", "model": value["execution"]["model"], "reasoning": value["execution"]["reasoning"]}}


def _run_unit(private_root: Path, row: Mapping[str, Any], executable: str, *, invoke: Callable[..., Any] = shared._call_codex, prepared: Mapping[str, Any] | None = None) -> dict[str, Any]:
    prepared = dict(prepared or _prepare_unit(private_root, row)); value = prepared["value"]; destination = prepared["destination"]; prompt = prepared["prompt"]
    if not isinstance(destination, Path) or destination.exists(): raise ValueError("Recovery unit private destination already exists")
    destination.mkdir(parents=True); _atomic(destination / "run.json", prepared["configuration"])
    prompt_path = destination / "responses" / "batch-0001.prompt.txt.gz"; prompt_path.parent.mkdir(parents=True); prompt_path.write_bytes(gzip.compress(prompt.encode("utf-8"), mtime=0))
    _atomic(destination / "responses" / "attempt-started.json", {"format_version": 1, "logical_unit": V2._unit_name(row), "physical_attempt": 1, "question_ids": row["question_ids"], "prompt_sha256": _sha_text(prompt)})
    try:
        content, provider = invoke(executable=executable, model=value["execution"]["model"], reasoning=value["execution"]["reasoning"], prompt=prompt, output_dir=destination, response_schema=prepared["schema"], batch_number=1, attempt_number=1, timeout=value["execution"]["timeout_seconds"])
    except shared._ProviderAttemptFailure as error:
        _atomic(destination / "responses" / "attempt-outcome.json", {"format_version": 1, "status": "failed", "physical_attempt": 1, "stage": "provider_transport", "error": {"class": type(error).__name__, "message": str(error)}, "content": error.content, "provider": error.provider_record}); raise ValueError("Recovery unit failed after its only physical attempt") from error
    accepted = shared._write_accepted_response_artifact(output_dir=destination, batch_number=1, content=content)
    try:
        audit: list[dict[str, Any]] = []; verdicts = shared._normalize_batch(shared._parse_model_json(content), expected_ids=row["question_ids"], artifact_id="the-part-that-arrives-first", bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id=RUN_ID, artifact_text=_stack("source").read_text(encoding="utf-8"), context_texts=[], normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
    except Exception as error:
        _atomic(destination / "responses" / "attempt-outcome.json", {"format_version": 1, "status": "failed", "physical_attempt": 1, "stage": "model_output", "error": {"class": type(error).__name__, "message": str(error)}, "response_artifact": accepted, "provider": provider}); raise ValueError("Recovery unit returned malformed model output after its only attempt") from error
    reported = provider.get("reported") if isinstance(provider, Mapping) else None; session = reported.get("session_id") if isinstance(reported, Mapping) else None
    if not isinstance(session, str) or not session: raise ValueError("Successful recovery unit lacks a native Codex session identity")
    modules = V2.load_modules(_stack("registry")); bundle = next(item for item in V2.load_bundles(_stack("bundles")) if item["bundle_id"] == "prose.short_story")
    score = V2.core.score_bundle(modules, bundle, verdicts, artifact_id="the-part-that-arrives-first"); _atomic(destination / "score.json", score)
    score2 = V2.scoring_v2.score_bundle(modules, bundle, verdicts, artifact_id="the-part-that-arrives-first"); score2["parent_score_sha256"] = _sha_path(destination / "score.json"); _atomic(destination / "score.v2.json", score2)
    shared._write_verdicts(destination / "verdicts.jsonl", verdicts)
    _atomic(destination / "responses" / "attempt-outcome.json", {"format_version": 1, "status": "accepted", "physical_attempt": 1, "question_ids": row["question_ids"], "prompt_sha256": _sha_text(prompt), "response_artifact": accepted, "response_sha256": _sha_text(content), "provider": provider, "session_id_sha256": _sha_text(session), "normalization_policy": shared.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": audit, "normalized_verdicts": verdicts})
    return _verify_unit(private_root, row, executable)


def _verify_unit(private_root: Path, row: Mapping[str, Any], executable: str) -> dict[str, Any]:
    destination = V2._unit_path(private_root, row); prompt = V2._prompt(V2._items_for(row))
    if _read(destination / "run.json") != _expected_run(row) or gzip.decompress((destination / "responses" / "batch-0001.prompt.txt.gz").read_bytes()).decode("utf-8") != prompt: raise ValueError("Recovery unit source/prompt evidence drifted")
    started = _read(destination / "responses" / "attempt-started.json")
    if started != {"format_version": 1, "logical_unit": V2._unit_name(row), "physical_attempt": 1, "question_ids": row["question_ids"], "prompt_sha256": _sha_text(prompt)}: raise ValueError("Recovery unit durable attempt evidence drifted")
    outcome = _read(destination / "responses" / "attempt-outcome.json")
    if outcome.get("status") != "accepted" or outcome.get("physical_attempt") != 1 or outcome.get("question_ids") != row["question_ids"] or outcome.get("prompt_sha256") != _sha_text(prompt) or outcome.get("normalization_policy") != shared.EVIDENCE_NORMALIZATION_POLICY: raise ValueError("Recovery unit did not accept exactly one physical attempt")
    artifact = outcome.get("response_artifact"); path = destination / artifact["path"] if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str) else None
    if path is None or not path.is_file() or path.stat().st_size != artifact.get("bytes") or _sha_path(path) != artifact.get("sha256") or _sha_text(path.read_text(encoding="utf-8")) != outcome.get("response_sha256"): raise ValueError("Recovery unit accepted response evidence drifted")
    audit: list[dict[str, Any]] = []; verdicts = shared._normalize_batch(shared._parse_model_json(path.read_text(encoding="utf-8")), expected_ids=row["question_ids"], artifact_id="the-part-that-arrives-first", bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id=RUN_ID, artifact_text=_stack("source").read_text(encoding="utf-8"), context_texts=[], normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
    provider = outcome.get("provider", {}).get("reported", {}) if isinstance(outcome.get("provider"), Mapping) else {}; session = provider.get("session_id") if isinstance(provider, Mapping) else None
    if verdicts != outcome.get("normalized_verdicts") or audit != outcome.get("normalization_audit") or provider.get("provider") != "openai" or provider.get("model") != contract()["execution"]["model"] or provider.get("reasoning_effort") != contract()["execution"]["reasoning"] or not isinstance(session, str) or not session or outcome.get("session_id_sha256") != _sha_text(session): raise ValueError("Recovery unit result/provider evidence drifted")
    return {"run_sha256": _sha_path(destination / "run.json"), "score_sha256": _sha_path(destination / "score.json"), "score_v2_sha256": _sha_path(destination / "score.v2.json"), "verdict_count": len(verdicts), "sessions": [{"session_id_sha256": _sha_text(session)}]}


def _delegate() -> None:
    V2.HERE = HERE; V2.ROOT = ROOT; V2.CONTRACT_PATH = CONTRACT_PATH; V2.RECEIPT = RECEIPT
    V2.contract = contract; V2._stack = _stack; V2._lineage = lambda: V2.REMAINDER.validate_closed_parent(); V2.plan = plan
    V2._receipt = _receipt; V2.native_preflight = native_preflight; V2._prepare_unit = _prepare_unit; V2._run_unit = _run_unit; V2._verify_unit = _verify_unit


def execute(work_root: Path, private_root: Path, **kwargs: Any) -> dict[str, Any]:
    _delegate(); kwargs.setdefault("verifier", _verify_unit); result = V2.execute(work_root, private_root, **kwargs)
    result["inherited_preflight_provider_calls"] = 1
    result["recorded_preflight_provider_calls"] += 1
    V2._atomic(work_root / "analysis.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the schema-corrected batch-curve successor.")
    parser.add_argument("command", choices=("plan", "prepare", "native-preflight", "execute")); parser.add_argument("work_root", type=Path, nargs="?"); parser.add_argument("private_root", type=Path, nargs="?"); parser.add_argument("--epoch", type=int)
    args = parser.parse_args()
    if args.command == "plan": print(json.dumps(plan(), indent=2)); return
    if args.work_root is None or args.private_root is None: raise SystemExit(f"{args.command} requires WORK_ROOT PRIVATE_ROOT")
    if args.command == "prepare": print(json.dumps(prepare(args.work_root, args.private_root), indent=2)); return
    if args.command == "native-preflight":
        if args.epoch is None: raise SystemExit("native-preflight requires --epoch")
        print(json.dumps(native_preflight(args.work_root, args.private_root, epoch=args.epoch), indent=2)); return
    print(json.dumps(execute(args.work_root, args.private_root), indent=2))


if __name__ == "__main__": main()
