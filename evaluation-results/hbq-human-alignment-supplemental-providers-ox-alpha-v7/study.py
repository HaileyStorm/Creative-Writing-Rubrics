"""Immutable bindings for the score-blind Ox Alpha v7 transport successor."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from hbqrs import runner as runner_module
from hbqrs.paths import prompts_dir, schema_dir


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PARENT_ROOT = (HERE / "../hbq-human-alignment-supplemental-providers-ox-alpha-v6").resolve()
FROZEN_NAME = "frozen-ox-alpha-v7-transport-contract.json"
V6_COMPLETE_TREE = {"files": 21, "sha256": "edde3576988462c51b8aca82196507b04ba4d8f8d470ce1068c701406f86f918"}
V6_FILES = {
    "README.md": "8ffaf81490ec180686213c8c66697368235a7b8bff9fb94b2eeed57ea4da7cd2",
    "prepare_transport_successor.py": "e874e912beda7e2140da0603a4406d0511cc32b0c7724ba61813715492686be3",
    "run_transport_pilot.py": "a1d4cbd354275faab3654bbcd6dc42b6db8d0fff47cd603d156d42e61341c792",
    "study-contract.json": "9396d574fb3d6815adf2cd7a5e199ddca0c732c27b39e7c3d249df3b6c0e089c",
    "study.py": "846e8c232cce67a95f6a130822602cbfa49db27e29466998ba0f8283bee1a318",
    "verify_transport_pilot.py": "8cc0f5da62d541d02ed58cb15d2d7e99692ff7af7613581ac1cc265d1b6819a3",
}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Required file is unavailable: {path}")
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _tree(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"Required evidence tree is unavailable: {root}")
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _external_disjoint(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if any(_inside(path, REPO_ROOT) for path in resolved):
        raise ValueError("Ox v7 roots must remain outside the repository")
    for index, left in enumerate(resolved):
        if any(left == right or _inside(left, right) or _inside(right, left) for right in resolved[index + 1:]):
            raise ValueError("Ox v7 work, predecessor, cost, and input roots must be disjoint")


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered); output.flush(); os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    expected = {"cells": 3, "batch_size": 4, "question_count": 4, "batch_attempts": 1, "workers": 1, "timeout_seconds": 240, "maximum_http_seconds_exclusive": 150}
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "evidence_status": "provisional_only"}
    parent = {"path": "../hbq-human-alignment-supplemental-providers-ox-alpha-v6", "study_id": "hbq-human-alignment-supplemental-providers-ox-alpha-v6", "commit": "c36f380", "source_files_are_verified_before_freeze": True}
    predecessor = {"source": "The caller supplies the exact immutable uncertain v6 root; no machine-specific path is recorded in the package.", "required_state": "One cap-1 request-v2 HTTP 200 completed at raw duration 111.5274232 seconds, with four schema-valid verdicts plus run, verdict, diagnostic, accepted-message, request, result, checkpoint, and raw-evidence artifacts, but no journal or semantic receipt. V6 first failed because its checkpoint selector globbed request and result JSON as checkpoints; byte-normalizing expected prompt assets or source/context text is a second deterministic latent verifier defect. The v6 root is permanently blocked and uncertain; it cannot be resumed, mutated, or followed by a live child run.", "complete_tree_is_verified": True, "later_mutation_forbidden": True}
    pilot = value.get("transport_pilot")
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v7" or value.get("frozen_before_execution") is not True or not isinstance(pilot, Mapping) or {key: pilot.get(key) for key in expected} != expected or pilot.get("sla_revision_evidence") != "The raw-HTTP ceiling remains below 150 seconds. The exact v6 four-leaf predecessor took 111.5274232 seconds, confirming the endpoint floor without changing the cap-1 transport policy." or value.get("parent_v6") != parent or value.get("uncertain_v6") != predecessor or value.get("provider") != provider:
        raise ValueError("Ox v7 transport contract drifted")
    return value


CONTRACT = load_contract()


def _parent_v6() -> Any:
    for name, digest in V6_FILES.items():
        path = PARENT_ROOT / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"Ox v6 parent file drifted: {name}")
    spec = importlib.util.spec_from_file_location("ox_alpha_v7_parent_v6", PARENT_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Ox v6 parent helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get("study")
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if prior is None: sys.modules.pop("study", None)
        else: sys.modules["study"] = prior
    if module.CONTRACT.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v6":
        raise ValueError("Ox v6 parent contract is not the pinned study")
    return module


def _parent_v6_verifier(parent: Any) -> Any:
    spec = importlib.util.spec_from_file_location("ox_alpha_v7_parent_v6_verify", PARENT_ROOT / "verify_transport_pilot.py")
    if spec is None or spec.loader is None:
        raise ValueError("Ox v6 parent verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get("study")
    sys.modules[spec.name] = module
    sys.modules["study"] = parent
    try:
        spec.loader.exec_module(module)
    finally:
        if prior is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = prior
    return module


def _corrected_v7_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("ox_alpha_v7_corrected_verifier", HERE / "verify_transport_pilot.py")
    if spec is None or spec.loader is None:
        raise ValueError("Ox v7 corrected verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get("study")
    sys.modules[spec.name] = module
    sys.modules["study"] = sys.modules[__name__]
    try:
        spec.loader.exec_module(module)
    finally:
        if prior is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = prior
    return module


def _http_attempts(evidence: Path) -> list[dict[str, int]]:
    attempts: list[dict[str, int]] = []
    for path in sorted(evidence.rglob("events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line, object_pairs_hook=_unique)
            if not isinstance(event, Mapping) or event.get("event_type") != "http_attempt": continue
            data = event.get("data")
            if not isinstance(data, Mapping): raise ValueError("Uncertain Ox v6 HTTP event is malformed")
            status, started, finished = data.get("status"), data.get("http_started_monotonic_ns"), data.get("http_finished_monotonic_ns")
            if any(isinstance(item, bool) or not isinstance(item, int) for item in (status, started, finished)) or finished <= started:
                raise ValueError("Uncertain Ox v6 HTTP event is malformed")
            attempts.append({"status": status, "duration_ns": finished - started})
    return attempts


def _accepted_v6_global_ids(checkpoint: Mapping[str, Any], evidence: Path) -> dict[str, str]:
    provider = checkpoint.get("provider")
    if not isinstance(provider, Mapping) or provider.get("logical_provider_request_count") != 1 or provider.get("physical_http_attempt_count") != 1 or provider.get("recovered_request_count") != 0:
        raise ValueError("Uncertain Ox v6 root lacks its accepted cap-1 identity binding")
    leaves: list[tuple[Path, list[Any]]] = []
    for child in sorted(path for path in evidence.iterdir() if path.is_dir()):
        try:
            records = [json.loads(line, object_pairs_hook=_unique) for line in (child / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Uncertain Ox v6 identity evidence is unreadable") from exc
        leaves.append((child, records))
    judge = [(child, records) for child, records in leaves if sum(isinstance(record, Mapping) and record.get("event_type") == "judge_boundary" for record in records) == 1]
    if len(leaves) != 2 or len(judge) != 1:
        raise ValueError("Uncertain Ox v6 identity evidence lacks one Judge leaf")
    judge_leaf, judge_records = judge[0]
    if any(record.get("event_type") == "http_attempt" for child, records in leaves if child != judge_leaf for record in records if isinstance(record, Mapping)):
        raise ValueError("Uncertain Ox v6 identity evidence has a ProveLock HTTP attempt")
    attempts = [record.get("data") for record in judge_records if isinstance(record, Mapping) and record.get("event_type") == "http_attempt"]
    if len(attempts) != 1 or not isinstance(attempts[0], Mapping):
        raise ValueError("Uncertain Ox v6 identity evidence lacks one Judge HTTP attempt")
    logical = attempts[0].get("logical_request_id")
    receipt = read_json(judge_leaf / "receipt.json")
    session = receipt.get("run_id")
    evidence_sha, proof_sha = provider.get("evidence_sha256"), provider.get("serialization_proof_sha256")
    if any(not isinstance(value, str) or not value for value in (logical, session)) or any(not isinstance(value, str) or len(value) != 64 for value in (evidence_sha, proof_sha)):
        raise ValueError("Uncertain Ox v6 identity binding is malformed")
    return {"logical_request_id": logical, "session_id": session, "receipt_id": f"nous:{evidence_sha}:{proof_sha}"}


def uncertain_v6_commitments(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if _tree(root) != V6_COMPLETE_TREE:
        raise ValueError("Uncertain Ox v6 root has extra, missing, or drifted evidence")
    committed = {relative: fingerprint(root / relative) for relative in ("frozen-ox-alpha-v6-transport-contract.json", "pilot-execution-claim.json", "pilot-invocation.json", "pilot-uncertain.json", "runs/pilot/ox-alpha-v6-01/run.json", "runs/pilot/ox-alpha-v6-01/verdicts.jsonl", "runs/pilot/ox-alpha-v6-01/diagnostic.json", "runs/pilot/ox-alpha-v6-01/responses/batch-0001.json", "runs/pilot/ox-alpha-v6-01/responses/batch-0001.accepted-0001.message.txt", "runs/pilot/ox-alpha-v6-01/responses/batch-0001.attempt-0001.nous.request.json", "runs/pilot/ox-alpha-v6-01/responses/batch-0001.attempt-0001.nous.result.json")}
    uncertain = read_json(root / "pilot-uncertain.json")
    if uncertain.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v6" or uncertain.get("kind") != "blocked_uncertain_transport_outcome" or uncertain.get("cell_id") != "ox-alpha-v6-01" or uncertain.get("reason") != "terminal_bridge_quiescence_unproven:ValueError" or uncertain.get("error") != {"class": "ValueError", "message": "Ox v6 requires one clean batch"}:
        raise ValueError("Ox v6 root is not permanently blocked by the recorded first-observed selector defect")
    if (root / "pilot-journal").exists() or (root / "pilot-receipts").exists():
        raise ValueError("Uncertain Ox v6 root has forbidden later completion mutation")
    if sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir() and path.relative_to(root).as_posix().startswith("runs/pilot/") and path.relative_to(root).as_posix().count("/") == 2) != ["runs/pilot/ox-alpha-v6-01"]:
        raise ValueError("Uncertain Ox v6 root has a forbidden live child or later run mutation")
    run = root / "runs" / "pilot" / "ox-alpha-v6-01"
    parent = _parent_v6()
    parent_frozen = parent.load_frozen(root)
    parent_verifier = _parent_v6_verifier(parent)
    invocation = parent_verifier._invocation(root)
    claim = parent_verifier._claim(root)
    checkpoint = read_json(run / "responses" / "batch-0001.json")
    provider = checkpoint.get("provider")
    if checkpoint.get("accepted_attempt") != 1 or not isinstance(provider, Mapping) or provider.get("logical_provider_request_count") != 1 or provider.get("physical_http_attempt_count") != 1 or provider.get("recovered_request_count") != 0:
        raise ValueError("Uncertain Ox v6 root lacks its cap-1 accepted checkpoint")
    message = run / "responses" / "batch-0001.accepted-0001.message.txt"
    if not message.is_file() or not message.read_text(encoding="utf-8").strip():
        raise ValueError("Uncertain Ox v6 root lacks its accepted message")
    verdicts = [json.loads(line, object_pairs_hook=_unique) for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    diagnostic = read_json(run / "diagnostic.json")
    if len(verdicts) != 4 or any(not isinstance(verdict, Mapping) or verdict.get("question_id") not in checkpoint.get("question_ids", []) for verdict in verdicts) or diagnostic.get("selected_question_count") != 4 or diagnostic.get("selected_question_ids") != checkpoint.get("question_ids"):
        raise ValueError("Uncertain Ox v6 root lacks its schema-valid four-verdict diagnostic receipt")
    corrected = _corrected_v7_verifier()
    v6_cell = parent_frozen["cells"][0]
    artifact, prompt, _ = input_paths(parent_frozen, v6_cell)
    loaded, checkpoint_count, previous = corrected._load_checkpoints(run, artifact_text=artifact.read_bytes().decode("utf-8"), context_texts=[prompt.read_bytes().decode("utf-8")], batch_attempts=1, normalization_policy=corrected.EVIDENCE_NORMALIZATION_POLICY)
    if checkpoint_count != 1 or previous != sha(run / "responses" / "batch-0001.json") or loaded != verdicts or [verdict.get("question_id") for verdict in loaded] != checkpoint.get("question_ids"):
        raise ValueError("Uncertain Ox v6 root does not pass corrected schema validation for its ordered four verdicts")
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}:
        raise ValueError("Uncertain Ox v6 root lacks its bound request, result, proof, and evidence receipt")
    if any(not (run / str(artifacts[name].get("path", ""))).is_file() for name in ("judge_request", "judge_result", "serialization_proof")):
        raise ValueError("Uncertain Ox v6 root has an unbound request, result, or proof artifact")
    evidence = run / "responses" / "batch-0001.attempt-0001.nous.evidence"
    attempts = _http_attempts(evidence)
    if attempts != [{"status": 200, "duration_ns": 111_527_423_200}]:
        raise ValueError("Uncertain Ox v6 does not prove one cap-1 HTTP 200 at the sealed raw duration")
    semantic = corrected.verify_cell(root, parent_frozen, v6_cell)
    accepted_ids = _accepted_v6_global_ids(checkpoint, evidence)
    if any(semantic[key] != accepted_ids[key] for key in accepted_ids):
        raise ValueError("Uncertain Ox v6 corrected semantic verification has drifted provider identities")
    return {"work_dir": str(root), "complete_work_tree": V6_COMPLETE_TREE, "commitments": committed, "frozen_runtime": parent_frozen["runtime"], "invocation": invocation, "claim": claim, "historical_http_attempts": attempts, "accepted_global_ids": accepted_ids, "corrected_selector_semantic_verification": semantic, "accepted_message_and_checkpoint": True, "journal_present": False, "semantic_receipt_present": False, "status": "permanently_blocked_uncertain"}


def runtime_bindings() -> dict[str, Any]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    paths = {"runner": Path(runner_module.__file__), "launcher": launcher, "bridge": launcher.parent / "nous_codex_bridge.py"}
    if any(not path.is_file() for path in paths.values()): raise ValueError("Canonical Nous transport runtime is unavailable")
    return {name: fingerprint(path) for name, path in paths.items()}


def judge_assets() -> dict[str, Any]:
    prefix = prompts_dir() / "judge" / "JUDGE_PREFIX.md"
    binary = prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"
    schema = schema_dir() / "hbq_judge_response.schema.json"
    return {"strict_ai": False, "judge_prefix": {"included": False, "file": fingerprint(prefix)}, "active_prompts": [fingerprint(binary)], "response_schema": fingerprint(schema)}


def _cells(uncertain_root: Path) -> tuple[Any, list[dict[str, Any]], list[Path]]:
    parent = _parent_v6()
    frozen = read_json(uncertain_root / parent.FROZEN_NAME)
    inherited = frozen.get("cells")
    if not isinstance(inherited, list) or len(inherited) != 3: raise ValueError("Uncertain Ox v6 root lacks three frozen public cells")
    result, input_roots = [], []
    for number, cell in enumerate(inherited, 1):
        if not isinstance(cell, Mapping) or not isinstance(cell.get("inputs"), Mapping) or not isinstance(cell.get("paths"), Mapping): raise ValueError("Uncertain Ox v6 cell is malformed")
        paths = dict(cell["paths"])
        artifact, prompt, task = (Path(str(paths.get(key, ""))) for key in ("artifact", "prompt", "task_contract"))
        observed = {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)}
        if observed != cell["inputs"] or artifact.parent != prompt.parent or artifact.parent != task.parent: raise ValueError("Uncertain Ox v6 public input bytes drifted")
        question_ids = list(cell.get("question_ids", []))[:4]
        if len(question_ids) != 4 or len(set(question_ids)) != 4 or any(not isinstance(item, str) for item in question_ids): raise ValueError("Uncertain Ox v6 cannot supply four transport leaves")
        item_id = cell.get("item_id")
        if not isinstance(item_id, str) or not item_id: raise ValueError("Uncertain Ox v6 cell lacks a public item identifier")
        result.append({"cell_id": f"ox-alpha-v7-{number:02d}", "item_id": item_id, "inputs": observed, "paths": paths, "question_ids": question_ids})
        input_roots.append(artifact.parent.resolve())
    if len({cell["item_id"] for cell in result}) != 3: raise ValueError("Ox v7 requires three distinct public cells")
    return parent, result, input_roots


def _fresh_zero_proof(parent: Any, proof_path: Path, checked_at: str) -> dict[str, Any]:
    return parent._fresh_zero_proof(parent._parent_v5(), proof_path, checked_at)


def _external_roots(work: Path, predecessor: Mapping[str, Any], proof: Mapping[str, Any], input_roots: list[Path]) -> dict[str, Any]:
    parent_root = Path(str(predecessor.get("work_dir", "")))
    proof_path = Path(str(proof.get("path", "")))
    catalog = Path(str(proof.get("catalog", {}).get("root", ""))) if isinstance(proof.get("catalog"), Mapping) else Path()
    usage = Path(str(proof.get("usage", {}).get("root", ""))) if isinstance(proof.get("usage"), Mapping) else Path()
    roots = [work, parent_root, proof_path, catalog, usage, *input_roots]
    if any(not str(path) or str(path) == "." for path in roots): raise ValueError("Ox v7 external root binding is malformed")
    _external_disjoint(*roots)
    return {"work": str(work.resolve()), "uncertain_v6": str(parent_root.resolve()), "zero_cost_proof": str(proof_path.resolve()), "zero_cost_catalog": str(catalog.resolve()), "zero_cost_usage": str(usage.resolve()), "inputs": [str(path.resolve()) for path in input_roots]}


def freeze_work(uncertain_v6_work: Path, zero_cost_proof: Path, work: Path) -> dict[str, Any]:
    if work.exists() and any(work.iterdir()): raise ValueError("Ox v7 requires a fresh empty external work root")
    predecessor = uncertain_v6_commitments(uncertain_v6_work)
    parent, cells, input_roots = _cells(uncertain_v6_work)
    checked_at = datetime.now(timezone.utc).isoformat()
    proof = _fresh_zero_proof(parent, zero_cost_proof, checked_at)
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, predecessor, proof, input_roots), "uncertain_v6": predecessor, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**proof, "freshness_checked_at": checked_at}, "cells": cells}
    immutable_json(work / FROZEN_NAME, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    predecessor = value.get("uncertain_v6")
    if not isinstance(predecessor, Mapping): raise ValueError("Ox v7 frozen contract lacks uncertain-v6 binding")
    parent, cells, input_roots = _cells(Path(str(predecessor.get("work_dir", ""))))
    current_predecessor = uncertain_v6_commitments(Path(str(predecessor.get("work_dir", ""))))
    proof = value.get("zero_cost_proof")
    if not isinstance(proof, Mapping) or not isinstance(proof.get("freshness_checked_at"), str): raise ValueError("Ox v7 frozen contract lacks zero-cost proof")
    current_proof = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), proof["freshness_checked_at"])
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, current_predecessor, current_proof, input_roots), "uncertain_v6": current_predecessor, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**current_proof, "freshness_checked_at": proof["freshness_checked_at"]}, "cells": cells}
    if value != expected: raise ValueError("Ox v7 frozen transport contract drifted")
    return value


def assert_invocation_freshness(frozen: Mapping[str, Any], checked_at: str) -> None:
    parent, _, _ = _cells(Path(str(frozen["uncertain_v6"]["work_dir"])))
    proof = frozen.get("zero_cost_proof")
    if not isinstance(proof, Mapping): raise ValueError("Ox v7 zero-cost proof is malformed")
    current = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), checked_at)
    if proof != {**current, "freshness_checked_at": proof.get("freshness_checked_at")}:
        raise ValueError("Ox v7 zero-cost proof drifted at the required freshness point")


def assert_launch_freshness(frozen: Mapping[str, Any]) -> None:
    assert_invocation_freshness(frozen, datetime.now(timezone.utc).isoformat())


def input_paths(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    if cell not in frozen.get("cells", []): raise ValueError("Ox v7 cell is not frozen")
    paths = cell.get("paths")
    if not isinstance(paths, Mapping): raise ValueError("Ox v7 cell paths are malformed")
    artifact, prompt, task = (Path(str(paths.get(key, ""))) for key in ("artifact", "prompt", "task_contract"))
    observed = {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)}
    if observed != cell.get("inputs"): raise ValueError("Ox v7 cell input bytes drifted")
    return artifact, prompt, task
