"""Cap-one recovery executor for the quota-stopped Codex batch curve."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping

from hbqrs import compile_bundle, load_bundles, load_modules
from hbqrs import core, scoring_v2
from hbqrs import runner as shared


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT_PATH = HERE / "study-contract.json"
RECEIPT = "preexecution-disclosure-receipt.json"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REMAINDER = _load("batch_curve_remainder_v1_lineage", HERE.parent / "batch-curve-codex-remainder-v1" / "remainder_successor.py")


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
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(_bytes(value) + b"\n")
    temp.replace(path)


def _same(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(_same(value, right[key]) for key, value in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs an offset")
    return parsed


def _root_sha(path: Path) -> str:
    return _sha_text(str(path.resolve()))


def _overlap(left: Path, right: Path) -> bool:
    first, second = left.resolve(), right.resolve()
    return first == second or first in second.parents or second in first.parents


def _bound(binding: Mapping[str, Any]) -> Path:
    if set(binding) != {"path", "bytes", "sha256"} or not isinstance(binding.get("path"), str) or type(binding.get("bytes")) is not int or not isinstance(binding.get("sha256"), str):
        raise ValueError("Binding shape drifted")
    path = (HERE / str(binding["path"])).resolve()
    if not path.is_file() or path.stat().st_size != binding["bytes"] or _sha_path(path) != binding["sha256"]:
        raise ValueError(f"Bound bytes drifted: {binding['path']}")
    return path


def contract() -> dict[str, Any]:
    value = _read(CONTRACT_PATH)
    if set(value) != {"format_version", "study_id", "status", "lineage", "current_stack", "execution", "privacy"} or value.get("format_version") != 2 or value.get("study_id") != "the-part-that-arrives-first-batch-curve-codex-remainder-v2" or value.get("status") != "preregistered_live_recovery_no_results":
        raise ValueError("Recovery contract shape drifted")
    if set(value["lineage"]) != {"remainder_contract", "remainder_module", "codex_v1_contract"}:
        raise ValueError("Recovery lineage binding set drifted")
    required_stack = {"source", "registry", "bundles", "prefix", "binary", "response_schema", "preflight_schema", "score_v1_schema", "score_v2_schema", "v2_contract", "harness", "runner", "core", "scoring_v2"}
    if set(value["current_stack"]) != required_stack:
        raise ValueError("Current runtime binding set drifted")
    for binding in [*value["lineage"].values(), *value["current_stack"].values()]:
        _bound(binding)
    execution = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "logical_units": 47, "max_physical_attempts_per_unit": 1, "planned_epoch_preflights": 6, "preflight_epoch_units": 8, "timeout_seconds": 600, "preflight_max_age_minutes": 15, "result_status": "incomplete_nonlive_analysis_pending"}
    if value["execution"] != execution or set(value["privacy"]) != {"remote_destination", "outbound", "raw_evidence", "public_projection"}:
        raise ValueError("Recovery execution or privacy contract drifted")
    REMAINDER.contract()
    return value


def _lineage() -> dict[str, Any]:
    contract()
    return REMAINDER.validate_closed_parent()


def _stack(name: str) -> Path:
    return _bound(contract()["current_stack"][name])


def _frozen_items() -> list[dict[str, Any]]:
    codex_v1 = _read(_bound(contract()["lineage"]["codex_v1_contract"]))
    if not isinstance(codex_v1.get("parent"), dict) or not isinstance(codex_v1.get("frozen_inputs"), dict):
        raise ValueError("Frozen Codex-v1 schedule source is malformed")
    frozen = list(_read(_stack("v2_contract"))["runtime"]["frozen_question_ids"])
    harness = _load("batch_curve_v2_harness_recovery", _stack("harness"))
    modules = load_modules(_stack("registry"))
    bundle = next(item for item in load_bundles(_stack("bundles")) if item["bundle_id"] == "prose.short_story")
    items = list(harness.all_question_items(compile_bundle(modules, bundle)))
    if [item["question"]["id"] for item in items] != frozen or len(items) != 178:
        raise ValueError("Current stack cannot reconstruct frozen question order")
    return items


def plan() -> list[dict[str, Any]]:
    ids = [item["question"]["id"] for item in _frozen_items()]
    rows: list[dict[str, Any]] = []
    for sequence, item in enumerate(REMAINDER.schedule(), 1):
        size, batch = int(item["size"]), int(item["batch"])
        question_ids = ids[(batch - 1) * size : batch * size]
        if not question_ids:
            raise ValueError("Scheduled recovery batch has no questions")
        rows.append({"sequence": sequence, **item, "question_ids": question_ids, "question_count": len(question_ids)})
    if len(rows) != 47 or len({(row["parent_cell"], row["batch"]) for row in rows}) != 47 or any(row["parent_cell"] == 36 and row["batch"] <= 31 for row in rows):
        raise ValueError("Recovery schedule is not exactly the sealed remainder")
    return rows


def _git_state(run: Callable[..., Any]) -> dict[str, str]:
    def command(args: list[str]) -> str:
        done = run(args, cwd=ROOT, capture_output=True, text=True, check=False)
        if getattr(done, "returncode", 1) != 0:
            raise ValueError("Cannot establish exact pushed source state")
        return str(getattr(done, "stdout", "")).strip()
    head, remote = command(["git", "rev-parse", "HEAD"]), command(["git", "rev-parse", "origin/main"])
    if head != remote or len(head) != 40 or command(["git", "status", "--porcelain=v1", "--untracked-files=all"]):
        raise ValueError("Recovery requires a clean committed pushed exact HEAD")
    for path in (CONTRACT_PATH, HERE / "batch_recovery.py"):
        relative = path.resolve().relative_to(ROOT).as_posix()
        done = run(["git", "ls-files", "--error-unmatch", relative], cwd=ROOT, capture_output=True, text=True, check=False)
        if getattr(done, "returncode", 1) != 0 or str(getattr(done, "stdout", "")).strip() != relative:
            raise ValueError("Recovery source must be tracked at exact HEAD")
    return {"head": head, "remote": "origin/main"}


def _runtime(executable: str, run: Callable[..., Any], resolve: Callable[[str], str | None]) -> dict[str, str]:
    resolved = resolve(executable)
    if not resolved:
        raise ValueError("Codex executable cannot be resolved")
    done = run([resolved, "--version"], capture_output=True, text=True, check=False)
    version = str(getattr(done, "stdout", "")).strip()
    if getattr(done, "returncode", 1) != 0 or not version:
        raise ValueError("Native Codex runtime probe failed")
    return {"executable": str(Path(resolved).resolve()), "version": version}


def _receipt(private_root: Path, executable: str, run: Callable[..., Any], resolve: Callable[[str], str | None]) -> dict[str, Any]:
    value = contract()
    return {"format_version": 2, "study_id": value["study_id"], "contract_sha256": _sha_path(CONTRACT_PATH), "git": _git_state(run), "runtime": _runtime(executable, run, resolve), "private_evidence_root_sha256": _root_sha(private_root), "stack_sha256": hashlib.sha256(_bytes(value["current_stack"])).hexdigest(), "schedule": plan(), "outbound_disclosure": value["privacy"], "provider_calls_made": 0}


def _fresh_roots(work_root: Path, private_root: Path) -> None:
    protected = [Path(REMAINDER.PARENT_PUBLIC).resolve(), Path(REMAINDER.PARENT_PRIVATE).resolve(), ROOT]
    if work_root.exists() or private_root.exists() or _overlap(work_root, private_root) or any(_overlap(root, protected_root) for root in (work_root, private_root) for protected_root in protected):
        raise ValueError("Recovery needs fresh external public and private roots")


def prepare(work_root: Path, private_root: Path, *, executable: str = "codex", subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    _lineage(); _fresh_roots(work_root, private_root)
    work_root.mkdir(parents=True); private_root.mkdir(parents=True)
    receipt = _receipt(private_root, executable, subprocess_run, executable_resolver)
    _atomic(work_root / RECEIPT, receipt)
    return receipt


def _names(path: Path) -> set[str]:
    if not path.is_dir():
        raise ValueError(f"Expected directory: {path}")
    return {item.name for item in path.iterdir()}


def _validate_prepared(work_root: Path, private_root: Path, *, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    if not work_root.is_dir() or not private_root.is_dir() or _overlap(work_root, private_root):
        raise ValueError("Recovery roots are unavailable")
    if not _names(work_root) <= {RECEIPT, "preflights", "cells", "claims", "analysis.json"} or not _names(private_root) <= {"preflights", "runs", "evidence-index"}:
        raise ValueError("Recovery root has an unbound member")
    receipt = _read(work_root / RECEIPT)
    expected = _receipt(private_root, receipt.get("runtime", {}).get("executable", "codex"), subprocess_run, executable_resolver)
    if not _same(receipt, expected):
        raise ValueError("Prepared recovery is not current pushed source/runtime")
    return receipt


def _preflight_name(epoch: int) -> str:
    if type(epoch) is not int or epoch < 1:
        raise ValueError("Epoch must be a positive integer")
    return f"epoch-{epoch:04d}.json"


def _epoch_directory(epoch: int) -> str:
    return _preflight_name(epoch).removesuffix(".json")


def _refresh_name(refresh: int) -> str:
    if type(refresh) is not int or refresh < 1:
        raise ValueError("Refresh must be a positive integer")
    return f"refresh-{refresh:04d}.json"


def _refresh_numbers(directory: Path, *, private: bool) -> set[int]:
    if not directory.is_dir():
        return set()
    paths = directory.glob("refresh-[0-9][0-9][0-9][0-9].json")
    result: set[int] = set()
    for path in paths:
        if private != path.is_dir():
            raise ValueError("Native preflight refresh has an invalid path type")
        value = path.name.removeprefix("refresh-").removesuffix(".json")
        result.add(int(value))
    return result


def _preflight_attempt_count(work_root: Path, private_root: Path) -> int:
    public_epochs = {path.name: path for path in (work_root / "preflights").glob("epoch-[0-9][0-9][0-9][0-9]") if path.is_dir()}
    private_epochs = {path.name: path for path in (private_root / "preflights").glob("epoch-[0-9][0-9][0-9][0-9]") if path.is_dir()}
    return sum(len(_refresh_numbers(public_epochs.get(name, Path("__missing__")), private=False) | _refresh_numbers(private_epochs.get(name, Path("__missing__")), private=True)) for name in public_epochs.keys() | private_epochs.keys())


def _settle_private_only_preflights(work_root: Path, private_root: Path, epoch: int) -> None:
    public_dir = work_root / "preflights" / _epoch_directory(epoch)
    private_dir = private_root / "preflights" / _epoch_directory(epoch)
    public_numbers = _refresh_numbers(public_dir, private=False)
    private_numbers = _refresh_numbers(private_dir, private=True)
    used = public_numbers | private_numbers
    if used and used != set(range(1, max(used) + 1)):
        raise ValueError("Native preflight refresh sequence has a gap or collision")
    for number in sorted(private_numbers - public_numbers):
        outcome = private_dir / _refresh_name(number) / "preflight-outcome.json"
        if not outcome.is_file():
            raise ValueError("Private-only preflight cannot be adjudicated without terminal evidence")
        private_value = _read(outcome)
        required = {"format_version", "study_id", "epoch", "refresh", "previous_public_sha256", "checked_at", "git", "runtime", "model", "reasoning", "native_argv", "receipt_sha256", "status", "account_surface_sha256", "response_sha256", "error", "content", "provider"}
        if set(private_value) != required or private_value.get("format_version") != 3 or private_value.get("epoch") != epoch or private_value.get("refresh") != number or private_value.get("status") not in {"accepted", "failed"}:
            raise ValueError("Private-only preflight terminal evidence is malformed")
        public_value = {key: value for key, value in private_value.items() if key not in {"content", "provider"}}
        public_value.update({"private_path": outcome.relative_to(private_root).as_posix(), "private_bytes": outcome.stat().st_size, "private_sha256": _sha_path(outcome)})
        _atomic(public_dir / _refresh_name(number), public_value)


def native_preflight(work_root: Path, private_root: Path, *, epoch: int, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which, now: datetime | None = None, invoke: Callable[..., Any] = shared._call_codex) -> dict[str, Any]:
    """Prove the exact native CLI model/account surface without caller-authored availability."""
    now = now or datetime.now().astimezone()
    receipt = _validate_prepared(work_root, private_root, subprocess_run=subprocess_run, executable_resolver=executable_resolver)
    value = contract()
    _settle_private_only_preflights(work_root, private_root, epoch)
    public_dir = work_root / "preflights" / _epoch_directory(epoch)
    private_dir = private_root / "preflights" / _epoch_directory(epoch)
    public_numbers = _refresh_numbers(public_dir, private=False)
    private_numbers = _refresh_numbers(private_dir, private=True)
    used = public_numbers | private_numbers
    refresh = max(used, default=0) + 1
    if used and used != set(range(1, refresh)):
        raise ValueError("Native preflight refresh sequence has a gap or collision")
    existing = [public_dir / _refresh_name(number) for number in sorted(public_numbers)]
    if existing:
        prior = _read(existing[-1])
        if _time(prior["checked_at"]) >= now:
            raise ValueError("Native preflight refresh timestamp must advance")
        previous_public_sha256 = _sha_path(existing[-1])
    else:
        previous_public_sha256 = None
    private = private_dir / _refresh_name(refresh)
    public = public_dir / _refresh_name(refresh)
    private.mkdir(parents=True, exist_ok=False)
    base = {"format_version": 3, "study_id": value["study_id"], "epoch": epoch, "refresh": refresh, "previous_public_sha256": previous_public_sha256, "checked_at": now.isoformat(), "git": receipt["git"], "runtime": receipt["runtime"], "model": value["execution"]["model"], "reasoning": value["execution"]["reasoning"], "native_argv": ["exec", "--model", value["execution"]["model"]], "receipt_sha256": _sha_path(work_root / RECEIPT)}
    def terminal(status: str, *, content: str | None, provider: Mapping[str, Any] | None, error: Exception | None = None) -> dict[str, Any]:
        reported = provider.get("reported") if isinstance(provider, Mapping) else None
        session = reported.get("session_id") if isinstance(reported, Mapping) else None
        record = {**base, "status": status, "account_surface_sha256": _sha_text(session) if isinstance(session, str) and session else None, "response_sha256": _sha_text(content) if isinstance(content, str) else None, "error": None if error is None else {"class": type(error).__name__, "message": str(error)}}
        private_value = {**record, "content": content, "provider": provider}
        _atomic(private / "preflight-outcome.json", private_value)
        saved = _read(private / "preflight-outcome.json")
        public_value = {**record, "private_path": (private / "preflight-outcome.json").relative_to(private_root).as_posix(), "private_bytes": len(_bytes(saved)) + 1, "private_sha256": hashlib.sha256(_bytes(saved) + b"\n").hexdigest()}
        _atomic(public, public_value)
        return _read(public)
    try:
        content, provider = invoke(executable=receipt["runtime"]["executable"], model=value["execution"]["model"], reasoning=value["execution"]["reasoning"], prompt="Return exactly the JSON object {\"ready\":true} and no other text.", output_dir=private, response_schema=_stack("preflight_schema"), batch_number=1, attempt_number=1, timeout=value["execution"]["timeout_seconds"])
    except shared._ProviderAttemptFailure as error:
        terminal("failed", content=error.content, provider=error.provider_record, error=error)
        raise ValueError("Native Codex capacity preflight failed") from error
    try:
        if json.loads(content) != {"ready": True}:
            raise ValueError("unexpected preflight response")
    except (json.JSONDecodeError, ValueError) as error:
        terminal("failed", content=content, provider=provider, error=error)
        raise ValueError("Native Codex capacity preflight returned malformed output") from error
    reported = provider.get("reported") if isinstance(provider, Mapping) else None
    session = reported.get("session_id") if isinstance(reported, Mapping) else None
    if not isinstance(session, str) or not session:
        terminal("failed", content=content, provider=provider, error=ValueError("missing session identity"))
        raise ValueError("Native Codex capacity preflight lacks session identity")
    return terminal("accepted", content=content, provider=provider)


def _active_preflight(work_root: Path, private_root: Path, epoch: int, now: datetime, *, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, Any] | None:
    _settle_private_only_preflights(work_root, private_root, epoch)
    directory = work_root / "preflights" / _epoch_directory(epoch)
    records = sorted(directory.glob("refresh-[0-9][0-9][0-9][0-9].json")) if directory.is_dir() else []
    if not records:
        return None
    if [path.name for path in records] != [_refresh_name(number) for number in range(1, len(records) + 1)]:
        raise ValueError("Native preflight refresh sequence has a gap or collision")
    public = records[-1]; record = _read(public)
    if set(record) != {"format_version", "study_id", "epoch", "refresh", "previous_public_sha256", "checked_at", "git", "runtime", "model", "reasoning", "native_argv", "receipt_sha256", "status", "account_surface_sha256", "response_sha256", "error", "private_path", "private_bytes", "private_sha256"} or record.get("format_version") != 3 or record.get("refresh") != len(records) or record.get("previous_public_sha256") != (_sha_path(records[-2]) if len(records) > 1 else None):
        raise ValueError("Native preflight public evidence shape drifted")
    receipt = _validate_prepared(work_root, private_root, subprocess_run=subprocess_run, executable_resolver=executable_resolver)
    value = contract(); checked = _time(record["checked_at"])
    private = private_root / record["private_path"]
    if record["epoch"] != epoch or record["study_id"] != value["study_id"] or record["git"] != receipt["git"] or record["runtime"] != receipt["runtime"] or record["model"] != value["execution"]["model"] or record["reasoning"] != value["execution"]["reasoning"] or record["native_argv"] != ["exec", "--model", value["execution"]["model"]] or record["receipt_sha256"] != _sha_path(work_root / RECEIPT) or not private.is_file() or private.stat().st_size != record["private_bytes"] or _sha_path(private) != record["private_sha256"]:
        raise ValueError("Native preflight is mismatched")
    return record if record["status"] == "accepted" and checked <= now <= checked + timedelta(minutes=value["execution"]["preflight_max_age_minutes"]) else None


def _unit_name(row: Mapping[str, Any]) -> str:
    return f"cell-{int(row['parent_cell']):02d}-batch-{int(row['batch']):04d}"


def _unit_path(private_root: Path, row: Mapping[str, Any]) -> Path:
    return private_root / "runs" / _unit_name(row)


def _items_for(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    requested = list(row["question_ids"])
    selected = [item for item in _frozen_items() if item["question"]["id"] in set(requested)]
    if [item["question"]["id"] for item in selected] != requested:
        raise ValueError("Recovery partition drifted")
    return selected


def _prompt(items: list[dict[str, Any]]) -> str:
    return shared._render_prompt(binary_prompt=f"{_stack('prefix').read_text(encoding='utf-8').strip()}\n\n{_stack('binary').read_text(encoding='utf-8').strip()}", artifact={"name": _stack("source").name, "text": _stack("source").read_text(encoding="utf-8")}, contexts=[], bundle_id="prose.short_story", artifact_id="the-part-that-arrives-first", questions=items)


def _prepare_unit(private_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    value = contract(); destination = _unit_path(private_root, row)
    if destination.exists():
        raise ValueError("Recovery unit private destination already exists")
    items = _items_for(row); prompt = _prompt(items); schema = _stack("response_schema")
    configuration = {"format_version": 1, "protocol": "batch-curve-codex-remainder-v2-cap1", "plan": dict(row), "artifact_id": "the-part-that-arrives-first", "bundle_id": "prose.short_story", "batch_attempts": 1, "timeout_seconds": value["execution"]["timeout_seconds"], "provider": {"configured": "codex", "reported": "openai", "model": value["execution"]["model"], "reasoning": value["execution"]["reasoning"]}}
    return {"value": value, "destination": destination, "items": items, "prompt": prompt, "schema": schema, "configuration": configuration}


def _run_unit(private_root: Path, row: Mapping[str, Any], executable: str, *, invoke: Callable[..., Any] = shared._call_codex, prepared: Mapping[str, Any] | None = None) -> dict[str, Any]:
    prepared = dict(prepared or _prepare_unit(private_root, row)); value = prepared["value"]; destination = prepared["destination"]; prompt = prepared["prompt"]
    if not isinstance(destination, Path) or destination.exists():
        raise ValueError("Recovery unit private destination already exists")
    destination.mkdir(parents=True)
    configuration = prepared["configuration"]
    _atomic(destination / "run.json", configuration)
    prompt_path = destination / "responses" / "batch-0001.prompt.txt.gz"; prompt_path.parent.mkdir(parents=True)
    prompt_path.write_bytes(gzip.compress(prompt.encode("utf-8"), mtime=0))
    _atomic(destination / "responses" / "attempt-started.json", {"format_version": 1, "logical_unit": _unit_name(row), "physical_attempt": 1, "question_ids": row["question_ids"], "prompt_sha256": _sha_text(prompt)})
    try:
        content, provider = invoke(executable=executable, model=value["execution"]["model"], reasoning=value["execution"]["reasoning"], prompt=prompt, output_dir=destination, response_schema=prepared["schema"], batch_number=1, attempt_number=1, timeout=value["execution"]["timeout_seconds"])
    except shared._ProviderAttemptFailure as error:
        _atomic(destination / "responses" / "attempt-outcome.json", {"format_version": 1, "status": "failed", "physical_attempt": 1, "stage": "provider_transport", "error": {"class": type(error).__name__, "message": str(error)}, "content": error.content, "provider": error.provider_record})
        raise ValueError("Recovery unit failed after its only physical attempt") from error
    accepted = shared._write_accepted_response_artifact(output_dir=destination, batch_number=1, content=content)
    try:
        audit: list[dict[str, Any]] = []
        verdicts = shared._normalize_batch(shared._parse_model_json(content), expected_ids=row["question_ids"], artifact_id="the-part-that-arrives-first", bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id="batch-curve-codex-remainder-v2", artifact_text=_stack("source").read_text(encoding="utf-8"), context_texts=[], normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
    except Exception as error:
        _atomic(destination / "responses" / "attempt-outcome.json", {"format_version": 1, "status": "failed", "physical_attempt": 1, "stage": "model_output", "error": {"class": type(error).__name__, "message": str(error)}, "response_artifact": accepted, "provider": provider})
        raise ValueError("Recovery unit returned malformed model output after its only attempt") from error
    reported = provider.get("reported") if isinstance(provider, Mapping) else None
    session = reported.get("session_id") if isinstance(reported, Mapping) else None
    if not isinstance(session, str) or not session:
        raise ValueError("Successful recovery unit lacks a native Codex session identity")
    modules = load_modules(_stack("registry")); bundle = next(item for item in load_bundles(_stack("bundles")) if item["bundle_id"] == "prose.short_story")
    score = core.score_bundle(modules, bundle, verdicts, artifact_id="the-part-that-arrives-first")
    score2 = scoring_v2.score_bundle(modules, bundle, verdicts, artifact_id="the-part-that-arrives-first"); score2["parent_score_sha256"] = _sha_path(destination / "score.json") if (destination / "score.json").is_file() else None
    _atomic(destination / "score.json", score); score2["parent_score_sha256"] = _sha_path(destination / "score.json"); _atomic(destination / "score.v2.json", score2)
    shared._write_verdicts(destination / "verdicts.jsonl", verdicts)
    outcome = {"format_version": 1, "status": "accepted", "physical_attempt": 1, "question_ids": row["question_ids"], "prompt_sha256": _sha_text(prompt), "response_artifact": accepted, "response_sha256": _sha_text(content), "provider": provider, "session_id_sha256": _sha_text(session), "normalization_policy": shared.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": audit, "normalized_verdicts": verdicts}
    _atomic(destination / "responses" / "attempt-outcome.json", outcome)
    return _verify_unit(private_root, row, executable)


def _verify_unit(private_root: Path, row: Mapping[str, Any], executable: str) -> dict[str, Any]:
    destination = _unit_path(private_root, row); value = contract(); items = _items_for(row); prompt = _prompt(items)
    expected_run = {"format_version": 1, "protocol": "batch-curve-codex-remainder-v2-cap1", "plan": dict(row), "artifact_id": "the-part-that-arrives-first", "bundle_id": "prose.short_story", "batch_attempts": 1, "timeout_seconds": value["execution"]["timeout_seconds"], "provider": {"configured": "codex", "reported": "openai", "model": value["execution"]["model"], "reasoning": value["execution"]["reasoning"]}}
    if _read(destination / "run.json") != expected_run or gzip.decompress((destination / "responses" / "batch-0001.prompt.txt.gz").read_bytes()).decode("utf-8") != prompt:
        raise ValueError("Recovery unit source/prompt evidence drifted")
    started = _read(destination / "responses" / "attempt-started.json")
    if started != {"format_version": 1, "logical_unit": _unit_name(row), "physical_attempt": 1, "question_ids": row["question_ids"], "prompt_sha256": _sha_text(prompt)}:
        raise ValueError("Recovery unit durable attempt evidence drifted")
    outcome = _read(destination / "responses" / "attempt-outcome.json")
    if outcome.get("status") != "accepted" or outcome.get("physical_attempt") != 1 or outcome.get("question_ids") != row["question_ids"] or outcome.get("prompt_sha256") != _sha_text(prompt) or outcome.get("normalization_policy") != shared.EVIDENCE_NORMALIZATION_POLICY:
        raise ValueError("Recovery unit did not accept exactly one physical attempt")
    artifact = outcome.get("response_artifact"); path = destination / artifact["path"] if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str) else None
    if path is None or not path.is_file() or path.stat().st_size != artifact.get("bytes") or _sha_path(path) != artifact.get("sha256") or _sha_text(path.read_text(encoding="utf-8")) != outcome.get("response_sha256"):
        raise ValueError("Recovery unit accepted response evidence drifted")
    audit: list[dict[str, Any]] = []
    verdicts = shared._normalize_batch(shared._parse_model_json(path.read_text(encoding="utf-8")), expected_ids=row["question_ids"], artifact_id="the-part-that-arrives-first", bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id="batch-curve-codex-remainder-v2", artifact_text=_stack("source").read_text(encoding="utf-8"), context_texts=[], normalization_policy=shared.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
    provider = outcome.get("provider", {}).get("reported", {}) if isinstance(outcome.get("provider"), Mapping) else {}
    session = provider.get("session_id") if isinstance(provider, Mapping) else None
    if verdicts != outcome.get("normalized_verdicts") or audit != outcome.get("normalization_audit") or provider.get("provider") != "openai" or provider.get("model") != value["execution"]["model"] or provider.get("reasoning_effort") != value["execution"]["reasoning"] or not isinstance(session, str) or not session or outcome.get("session_id_sha256") != _sha_text(session):
        raise ValueError("Recovery unit result/provider evidence drifted")
    return {"run_sha256": _sha_path(destination / "run.json"), "score_sha256": _sha_path(destination / "score.json"), "score_v2_sha256": _sha_path(destination / "score.v2.json"), "verdict_count": len(verdicts), "sessions": [{"session_id_sha256": _sha_text(session)}]}


def _historical_session_hashes() -> set[str]:
    _lineage(); root = Path(REMAINDER.PARENT_PRIVATE); result: set[str] = set()
    for path in sorted(root.glob("runs/cell-*/responses/batch-[0-9][0-9][0-9][0-9].json")):
        provider = _read(path).get("provider", {}).get("reported", {})
        session = provider.get("session_id") if isinstance(provider, Mapping) else None
        if not isinstance(session, str) or not session:
            raise ValueError("Accepted historical batch lacks a session identity")
        result.add(_sha_text(session))
    for path in sorted(root.glob("runs/cell-36/responses/rejected/batch-0032/attempt-[0-9][0-9][0-9][0-9].json")):
        digest = _read(path).get("provider_session_id_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Rejected historical batch lacks a session hash")
        result.add(digest)
    if len(result) < 3:
        raise ValueError("Historical session exclusion set is incomplete")
    return result


def _raw_index(private_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    run = _unit_path(private_root, row)
    files = [{"path": path.relative_to(private_root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha_path(path)} for path in sorted(run.rglob("*")) if path.is_file()]
    if not files:
        raise ValueError("Recovery unit has no private evidence")
    value = {"format_version": 1, "private_root_sha256": _root_sha(private_root), "run_path": run.relative_to(private_root).as_posix(), "files": files}
    target = private_root / "evidence-index" / f"{_unit_name(row)}.json"
    if target.exists() and _read(target) != value:
        raise ValueError("Private evidence index drifted")
    _atomic(target, value)
    return {"private_root_sha256": _root_sha(private_root), "relative_path": target.relative_to(private_root).as_posix(), "bytes": target.stat().st_size, "sha256": _sha_path(target)}


def _completed_unit(cell: Mapping[str, Any], row: Mapping[str, Any], private_root: Path, executable: str, verifier: Callable[[Path, Mapping[str, Any], str], dict[str, Any]] = _verify_unit) -> dict[str, Any] | None:
    if set(cell) != {"format_version", "plan", "calls", "status"} or cell.get("format_version") != 1 or cell.get("status") != "completed" or not _same(cell.get("plan"), row) or cell.get("calls", [])[:1] != [{"event": "attempt_started", "physical_attempt": 1}] or len(cell.get("calls", [])) != 2:
        return None
    accepted, raw = cell["calls"][1], cell["calls"][1].get("raw_evidence_index") if isinstance(cell["calls"][1], Mapping) else None
    if not isinstance(raw, Mapping) or set(raw) != {"private_root_sha256", "relative_path", "bytes", "sha256"} or raw.get("private_root_sha256") != _root_sha(private_root):
        return None
    index = private_root / str(raw["relative_path"])
    if not index.is_file() or index.stat().st_size != raw["bytes"] or _sha_path(index) != raw["sha256"]:
        return None
    try:
        verified = verifier(private_root, row, executable)
        return verified if _same(accepted, {"event": "accepted", "raw_evidence_index": dict(raw), **verified}) else None
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _assert_pending(cell: Mapping[str, Any], row: Mapping[str, Any], private_root: Path) -> None:
    if not _same(cell.get("plan"), row) or cell.get("status") not in {"pending", "in_progress"} or not isinstance(cell.get("calls"), list):
        raise ValueError("Recovery checkpoint drifted")
    if cell["calls"] or _unit_path(private_root, row).exists():
        raise ValueError("Recovery unit is uncertain and cannot be resent")


def execute(work_root: Path, private_root: Path, *, subprocess_run: Callable[..., Any] = subprocess.run, executable_resolver: Callable[[str], str | None] = shutil.which, invoke: Callable[..., Any] = shared._call_codex, preflight_invoke: Callable[..., Any] = shared._call_codex, clock: Callable[[], datetime] = lambda: datetime.now().astimezone(), unit_runner: Callable[[Path, Mapping[str, Any], str], dict[str, Any]] | None = None, verifier: Callable[[Path, Mapping[str, Any], str], dict[str, Any]] = _verify_unit, max_scored_units: int | None = None) -> dict[str, Any]:
    receipt = _validate_prepared(work_root, private_root, subprocess_run=subprocess_run, executable_resolver=executable_resolver)
    claims = work_root / "claims"; cells = work_root / "cells"; claims.mkdir(exist_ok=True); cells.mkdir(exist_ok=True)
    if any(claims.iterdir()):
        raise ValueError("A recovery unit is already claimed")
    rows = plan(); seen = _historical_session_hashes(); completed = 0; first_pending: int | None = None
    for index, row in enumerate(rows):
        path = cells / f"{_unit_name(row)}.json"; cell = _read(path) if path.exists() else {"format_version": 1, "plan": row, "calls": [], "status": "pending"}
        if cell.get("status") == "completed":
            if first_pending is not None:
                raise ValueError("Recovery completed cells must form a prefix")
            verified = _completed_unit(cell, row, private_root, receipt["runtime"]["executable"], verifier)
            if verified is None:
                raise ValueError("Completed recovery unit cannot be replayed")
            digest = verified["sessions"][0]["session_id_sha256"]
            if digest in seen:
                raise ValueError("Historical or recovery session was reused")
            seen.add(digest); completed += 1; continue
        _assert_pending(cell, row, private_root)
        first_pending = index if first_pending is None else first_pending
    scored_this_invocation = 0; preflights_this_invocation = 0
    for row in rows[first_pending if first_pending is not None else len(rows):]:
        if max_scored_units is not None and scored_this_invocation >= max_scored_units:
            break
        epoch = (int(row["sequence"]) - 1) // int(contract()["execution"]["preflight_epoch_units"]) + 1
        now = clock(); active = _active_preflight(work_root, private_root, epoch, now, subprocess_run=subprocess_run, executable_resolver=executable_resolver)
        if active is None:
            native_preflight(work_root, private_root, epoch=epoch, subprocess_run=subprocess_run, executable_resolver=executable_resolver, now=now, invoke=preflight_invoke)
            preflights_this_invocation += 1
        if _active_preflight(work_root, private_root, epoch, clock(), subprocess_run=subprocess_run, executable_resolver=executable_resolver) is None:
            raise ValueError("Native preflight expired before scored-unit contact")
        path = cells / f"{_unit_name(row)}.json"; cell = _read(path) if path.exists() else {"format_version": 1, "plan": row, "calls": [], "status": "pending"}
        claim = claims / f"{_unit_name(row)}.claim"
        try:
            handle = claim.open("x", encoding="utf-8")
        except FileExistsError as error:
            raise ValueError("Recovery unit is already claimed") from error
        try:
            with handle:
                handle.write(str(row["sequence"]))
                prepared = _prepare_unit(private_root, row)
                if _active_preflight(work_root, private_root, epoch, clock(), subprocess_run=subprocess_run, executable_resolver=executable_resolver) is None:
                    raise ValueError("Native preflight expired before scored-unit contact")
                if not _same(receipt, _receipt(private_root, receipt["runtime"]["executable"], subprocess_run, executable_resolver)):
                    raise ValueError("Exact pushed source/runtime changed before recovery unit")
                if _active_preflight(work_root, private_root, epoch, clock(), subprocess_run=subprocess_run, executable_resolver=executable_resolver) is None:
                    raise ValueError("Native preflight expired before scored-unit contact")
                cell.update({"status": "in_progress", "calls": [{"event": "attempt_started", "physical_attempt": 1}]}); _atomic(path, cell)
                verified = (unit_runner or (lambda root, item, executable: _run_unit(root, item, executable, invoke=invoke, prepared=prepared)))(private_root, row, receipt["runtime"]["executable"])
                digest = verified["sessions"][0]["session_id_sha256"]
                if digest in seen:
                    raise ValueError("Historical or recovery session was reused")
                seen.add(digest)
                raw = _raw_index(private_root, row)
                cell.update({"status": "completed", "calls": [{"event": "attempt_started", "physical_attempt": 1}, {"event": "accepted", "raw_evidence_index": raw, **verified}]}); _atomic(path, cell); completed += 1
                scored_this_invocation += 1
        finally:
            claim.unlink(missing_ok=True)
    value = contract(); result = {"format_version": 2, "study_id": value["study_id"], "contract_sha256": _sha_path(CONTRACT_PATH), "completed_units": completed, "scheduled_scored_provider_calls": 47, "planned_epoch_preflight_provider_calls": value["execution"]["planned_epoch_preflights"], "recorded_preflight_provider_calls": _preflight_attempt_count(work_root, private_root), "preflight_provider_calls_this_invocation": preflights_this_invocation, "scored_provider_calls_this_invocation": scored_this_invocation, "status": value["execution"]["result_status"], "screening_recommendation": None}
    _atomic(work_root / "analysis.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare, natively preflight, or execute the cap-one 47-unit recovery.")
    parser.add_argument("command", choices=("plan", "prepare", "native-preflight", "execute")); parser.add_argument("work_root", type=Path, nargs="?"); parser.add_argument("private_root", type=Path, nargs="?"); parser.add_argument("--epoch", type=int)
    args = parser.parse_args()
    if args.command == "plan": print(json.dumps(plan(), indent=2)); return
    if args.work_root is None or args.private_root is None: raise SystemExit(f"{args.command} requires WORK_ROOT PRIVATE_ROOT")
    if args.command == "prepare": print(json.dumps(prepare(args.work_root, args.private_root), indent=2)); return
    if args.command == "native-preflight":
        if args.epoch is None: raise SystemExit("native-preflight requires --epoch")
        print(json.dumps(native_preflight(args.work_root, args.private_root, epoch=args.epoch), indent=2)); return
    print(json.dumps(execute(args.work_root, args.private_root), indent=2))


if __name__ == "__main__":
    main()
