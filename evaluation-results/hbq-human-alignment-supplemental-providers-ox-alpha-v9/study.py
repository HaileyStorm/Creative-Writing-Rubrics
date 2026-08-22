"""Immutable v8-failure lineage and v9 unit scheduling helpers."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from hbqrs import runner

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
V8_ROOT = HERE.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v8"
FROZEN_NAME = "frozen-ox-alpha-v9-contract.json"
CONTRACT_PATH = HERE / "study-contract.json"
V8_FILES = {"study.py": "26dbb20f152c5efe0d8d01ed263a24fbd2620cb12c9c0a5de87b9882ee3e7014", "analyze_pilot.py": "3822d044c82c4d731e63d714bdd81ba01fc4ec608cd3e71fa1dd6544cba94cd7", "run_pilot.py": "96843753bd62f53afce43f0e271693785cd07a970c527238b9884b3b3ac44885", "prepare_pilot.py": "3358ea9d4fb46fcb8fa4359a80f0932c9fd51978c15088d97ccfee7a254c1a3f", "study-contract.json": "9f9da4d8c0143bcef3ba881498b4a0fd8378eee87e19525bd6b8c71e95203df6", "README.md": "f58dfefcf2c0404cffbf7e13393e5384143b4f8b3dae193785589601d5a79393"}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    if not isinstance(value, dict): raise ValueError(f"Expected JSON object: {path}")
    return value


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def fingerprint(path: Path) -> dict[str, Any]: return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}
def canonical(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"; path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out: out.write(rendered); out.flush(); os.fsync(out.fileno())
        try: os.link(temp, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered: raise ValueError(f"Immutable record drifted: {path}")
    finally: Path(temp).unlink(missing_ok=True)


def _inside(path: Path, root: Path) -> bool:
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False


def external_separate(*paths: Path) -> None:
    roots = [path.resolve() for path in paths]
    if any(_inside(path, REPO_ROOT) for path in roots): raise ValueError("v9 external evidence root is inside repository")
    if any(a == b or _inside(a, b) or _inside(b, a) for i, a in enumerate(roots) for b in roots[i + 1:]): raise ValueError("v9 external roots overlap")


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None: raise ValueError("Unable to import v8 predecessor")
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod


def parent_v8():
    for name, expected in V8_FILES.items():
        if sha(V8_ROOT / name) != expected: raise ValueError(f"v8 package drifted: {name}")
    return _module(V8_ROOT / "study.py", "ox_alpha_v9_parent_v8")


def _pinned_bridge(v8: Any) -> Any:
    bridge_path = runner.NOUS_LAUNCHER_PATH.parent / "nous_codex_bridge.py"
    if fingerprint(bridge_path) != v8.runtime_bindings()["bridge"]:
        raise ValueError("v9 canonical bridge drifted from v8 runtime")
    spec = importlib.util.spec_from_file_location("ox_alpha_v9_study_bridge", bridge_path)
    if spec is None or spec.loader is None: raise ValueError("v9 canonical bridge is unavailable")
    module = importlib.util.module_from_spec(spec); prior = sys.modules.get(spec.name); sys.modules[spec.name] = module
    try: spec.loader.exec_module(module)
    finally:
        if prior is None: sys.modules.pop(spec.name, None)
        else: sys.modules[spec.name] = prior
    return module


def tree(root: Path) -> dict[str, Any]:
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file() and path.name != ".evidence-hmac.key"]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "evidence_status": "provisional_only"}
    protocol = {"units": 135, "batch_size": 4, "last_batch_size": 3, "attempts_per_unit": 5, "maximum_eligible_524": 135, "maximum_physical_requests": 270, "request_schema": "codex-nous-tool-free-judge-request-v2", "cap": 1, "rounds": value.get("protocol", {}).get("rounds")}
    parent={"study_id":"hbq-human-alignment-supplemental-providers-ox-alpha-v8","commit":"73308d2","failed_root":"immutable sealed 524 failure; never resume or mutate"}
    pause={"consecutive_eligible_524":6,"same_unit_minutes":15,"after_three_consecutive_minutes":30,"fresh_proof_after_hours":24}
    if set(value)!={"format_version","study_id","status","frozen_before_execution","parent","provider","protocol","pause","zero_cost","limits"} or value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v9" or value.get("status") != "preregistered_unit_retry_successor_unexecuted" or value.get("frozen_before_execution") is not True or value.get("parent")!=parent or value.get("provider") != provider or value.get("protocol") != protocol or not isinstance(protocol["rounds"], str) or value.get("pause")!=pause or value.get("zero_cost") != {"no_purchase": True, "stop_on_charge_signal": True, "stop_on_http_402": True} or not isinstance(value.get("limits"),list) or len(value["limits"])!=2: raise ValueError("v9 contract drifted")
    return value


CONTRACT = contract()


def runtime_bindings() -> dict[str, Any]:
    launcher = runner.NOUS_LAUNCHER_PATH
    return {"study": fingerprint(Path(__file__)), "contract": fingerprint(CONTRACT_PATH), "preparer": fingerprint(HERE / "prepare_pilot.py"), "executor": fingerprint(HERE / "run_pilot.py"), "verifier": fingerprint(HERE / "analyze_pilot.py"), "runner": fingerprint(Path(runner.__file__)), "launcher": fingerprint(launcher), "bridge": fingerprint(launcher.parent / "nous_codex_bridge.py")}


def v8_failure(root: Path) -> dict[str, Any]:
    """Accept only the sealed, one-attempt, no-completion 524 that v9 supersedes."""
    external_separate(root); v8 = parent_v8()
    uncertain = read_json(root / "pilot-uncertain.json"); journal = read_json(root / "pilot-journal" / "0001-ox-alpha-v8-01.json")
    if uncertain.get("status") is not None or uncertain.get("kind") != "blocked_uncertain_full_scoring_outcome" or journal.get("status") != "failed_uncertain": raise ValueError("v8 root is not sealed failed lineage")
    rejected = root / "runs" / "ox-alpha-v8-01" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    record = read_json(rejected)
    if record.get("provider") is not None or record.get("stage") != "provider" or record.get("validation_feedback") is not None or "HTTP 524" not in str(record.get("error", {}).get("message", "")): raise ValueError("v8 failure is not eligible sealed 524 lineage")
    run = root / "runs" / "ox-alpha-v8-01"
    evidence_root = run / "responses" / "batch-0001.attempt-0001.nous.evidence"
    leaves = [path for path in evidence_root.iterdir() if path.is_dir()]
    judge = []
    for leaf in leaves:
        events = [json.loads(line) for line in (leaf / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if any(row.get("event_type") == "judge_boundary" for row in events): judge.append((leaf, events))
    if len(judge) != 1: raise ValueError("v8 failure lacks one sealed Judge evidence leaf")
    proofs = sorted(evidence_root.rglob("serialization-proof.json"))
    if len(proofs) != 1: raise ValueError("v8 failure lacks one serialization proof")
    try: leaf, prove = v8.v7_verifier()._judge_leaf(evidence_root, proofs[0])
    except Exception as exc: raise ValueError("v8 failure lacks canonical Judge/ProveLock topology") from exc
    bridge = _pinned_bridge(v8)
    for evidence_leaf in (leaf, prove):
        try: bridge.validate_evidence(evidence_leaf)
        except Exception as exc: raise ValueError("v8 failure evidence chain or HMAC is invalid") from exc
    if not getattr(bridge.serialization_proof_status(evidence_root, str(proofs[0]), expected_sha256=sha(proofs[0])), "valid", False):
        raise ValueError("v8 failure serialization proof is not canonical")
    events = [json.loads(line) for line in (leaf / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [row.get("data") for row in events if row.get("event_type") == "http_attempt"]
    prove_events = [json.loads(line) for line in (prove / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    receipt = read_json(leaf / "receipt.json") if (leaf / "receipt.json").is_file() else {}
    logical_id = attempts[0].get("logical_request_id") if len(attempts) == 1 and isinstance(attempts[0], Mapping) else None
    session_id = receipt.get("run_id")
    receipt_sha, proof_sha = receipt.get("receipt_sha256"), sha(proofs[0])
    if len(attempts) != 1 or attempts[0].get("status") != 524 or any(row.get("event_type") == "http_attempt" for row in prove_events) or any(row.get("event_type") == "message" and row.get("data", {}).get("direction") == "inbound" for row in events) or receipt.get("status") != "failure" or any(not isinstance(value,str) or len(value)!=64 for value in (receipt_sha,proof_sha)) or not isinstance(logical_id, str) or not logical_id or not isinstance(session_id, str) or not session_id: raise ValueError("v8 524 lineage has completion, wrong status, or no sealed receipt")
    if any((run / name).exists() for name in ("verdicts.jsonl", "score.json", "score.v2.json")): raise ValueError("v8 failure unexpectedly produced a result or verdict")
    return {"root": str(root.resolve()), "tree": tree(root), "frozen": fingerprint(root / v8.FROZEN_NAME), "uncertain": fingerprint(root / "pilot-uncertain.json"), "journal": fingerprint(root / "pilot-journal" / "0001-ox-alpha-v8-01.json"), "rejected": fingerprint(rejected), "request": fingerprint(run / "responses" / "batch-0001.attempt-0001.nous.request.json"), "failed_identities": {"logical_request_id": logical_id, "session_id": session_id, "receipt_sha256": receipt_sha, "serialization_proof_sha256": proof_sha}, "provider": CONTRACT["provider"]}


def units(v8_frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for cell in v8_frozen["cells"]:
        for ordinal, ids in enumerate(cell["primary_batches"], 1):
            result.append({"unit_id": f"{cell['cell_id']}-batch-{ordinal:04d}", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "batch": ordinal, "question_ids": ids, "inputs": cell["inputs"], "paths": cell["paths"], "gpt_reference": cell["gpt_reference"]})
    if len(result) != 135 or [len(row["question_ids"]) for row in result] != ([4] * 44 + [3]) * 3: raise ValueError("v9 unit geometry drifted")
    return result


def freeze_work(v8_root: Path, proof_path: Path, work: Path) -> dict[str, Any]:
    external_separate(v8_root, proof_path, work); v8 = parent_v8(); parent = v8_failure(v8_root); base = v8.load_frozen(v8_root)
    zero = v8._zero_cost_proof(proof_path); now = datetime.now(timezone.utc).isoformat(); v8.assert_fresh_at(zero, now)
    external_separate(v8_root, proof_path, Path(str(zero["catalog"]["root"])), Path(str(zero["usage"]["root"])), work)
    if work.exists() and any(work.iterdir()): raise ValueError("v9 requires empty work root")
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "runtime": runtime_bindings(), "v8_failure": parent, "v8_frozen": fingerprint(v8_root / v8.FROZEN_NAME), "zero_cost_proof": {**zero, "freshness_checked_at": now}, "units": units(base)}
    immutable_json(work / FROZEN_NAME, value); return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    required = {"format_version", "study_id", "frozen_before_execution", "contract", "runtime", "v8_failure", "v8_frozen", "zero_cost_proof", "units"}
    if set(value) != required or value.get("format_version") != 1 or value.get("study_id") != CONTRACT["study_id"] or value.get("frozen_before_execution") is not True or value.get("contract") != fingerprint(CONTRACT_PATH) or value.get("runtime") != runtime_bindings(): raise ValueError("v9 frozen contract drifted")
    proof = value["zero_cost_proof"]; v8 = parent_v8(); live_zero = v8._zero_cost_proof(Path(str(proof.get("path", ""))))
    if proof != {**live_zero, "freshness_checked_at": proof.get("freshness_checked_at")} : raise ValueError("v9 zero-cost proof drifted")
    v8.assert_fresh_at(proof, proof["freshness_checked_at"])
    parent = value["v8_failure"]
    if parent != v8_failure(Path(str(parent.get("root", "")))): raise ValueError("v8 failed lineage drifted")
    base = v8.load_frozen(Path(str(parent["root"])))
    if value["v8_frozen"] != fingerprint(Path(str(parent["root"])) / v8.FROZEN_NAME) or value["units"] != units(base): raise ValueError("v9 units do not exactly reconstruct")
    external_separate(work, Path(str(parent["root"])), Path(str(proof["path"])), Path(str(proof["catalog"]["root"])), Path(str(proof["usage"]["root"])))
    return value
