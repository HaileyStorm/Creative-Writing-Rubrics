"""Provider-free freeze for a small S1 incidental-determiner NO control."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v1"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
LEAF_ID = "form.poetry.free_verse.repetition"
BUNDLE_ID = "poetry_free_verse_repetition_singleton_v2"
PREDECESSOR_TERMINAL_SHA256 = "d3bc263ddd7f9c1df624b6b627803b96f2e19412944d5e4d1c0af63397f67ea9"
BASE_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2" / "study.py"
FRESHNESS_AUDIT_ROOTS = (
    "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1",
    "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2",
    "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v2",
    "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v3",
)
EXCLUDED_DECLARED_DESCENDANTS = (
    "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v2-execution-v2",
)
WORK_ROOT: Path | None = None

sys.path.insert(0, str(REPOSITORY / "src"))
from hbqrs import core, runner  # noqa: E402
from hbqrs.weights import materialize_weight_profile  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Frozen artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def _base() -> Any:
    spec = importlib.util.spec_from_file_location("s1_incidental_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Bound S1 candidate source is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def artifact() -> dict[str, str]:
    value = load(ROOT / "public-synthetic-corpus.json").get("artifact")
    if not isinstance(value, Mapping) or set(value) != {"case_id", "text"}:
        raise ValueError("Public artifact is invalid")
    return {"case_id": str(value["case_id"]), "text": str(value["text"])}


def slots() -> list[dict[str, Any]]:
    row = artifact()
    plan = (("n-6fe2", 2), ("n-a319", 1), ("n-c405", 3))
    candidate = _base().candidate_leaf()
    condition = {
        "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True,
        "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID,
        "question_sha256": hashlib.sha256(canonical(candidate)).hexdigest(),
    }
    result = [
        {"slot_id": slot_id, "case_id": row["case_id"], "repeat": repeat, "condition": condition}
        for slot_id, repeat in plan
    ]
    if len({item["slot_id"] for item in result}) != 3 or {item["repeat"] for item in result} != {1, 2, 3}:
        raise ValueError("Opaque three-slot schedule drifted")
    return result


def set_work_root(path: str | Path) -> Path:
    root = Path(path).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("External private work root is required")
    global WORK_ROOT
    WORK_ROOT = root
    return root


def dry_root() -> Path:
    if WORK_ROOT is None:
        raise ValueError("An explicit external private work root is required")
    return WORK_ROOT / "execution-dry"


def contract() -> dict[str, Any]:
    return load(ROOT / "study-contract.json")


def _head() -> tuple[str, str]:
    values = []
    for value in ("HEAD", f"{SOURCE_HEAD}^{{tree}}"):
        result = subprocess.run(["git", "rev-parse", value], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
        if result.returncode:
            raise ValueError("CWR source binding is unavailable")
        values.append(result.stdout.strip())
    return values[0], values[1]


def motif_audit() -> dict[str, Any]:
    text = artifact()["text"]
    prior_paths = [ROOT.parent / name / "public-synthetic-corpus.json" for name in FRESHNESS_AUDIT_ROOTS]
    if any(not path.is_file() for path in prior_paths):
        raise ValueError("Frozen incidental-determiner freshness audit source is unavailable")
    if ROOT.name in FRESHNESS_AUDIT_ROOTS or set(FRESHNESS_AUDIT_ROOTS) & set(EXCLUDED_DECLARED_DESCENDANTS):
        raise ValueError("Freshness audit successor exclusion drifted")
    prior = [path.read_text(encoding="utf-8") for path in prior_paths]
    tokens = re.findall(r"[a-z]+", text.casefold())
    if text in prior or "the empty platform" in "\n".join(prior).casefold() or tokens.count("the") != 4:
        raise ValueError("Incidental-determiner carrier freshness drifted")
    return {"algorithm": "frozen-literal-carrier-and-distinctive-phrase-v2", "prior_public_corpora": len(prior), "status": "disjoint"}


def validate_package() -> dict[str, Any]:
    expected = contract()
    if expected.get("study_id") != STUDY_ID or expected.get("status") != "provider_free_frozen_unexecuted":
        raise ValueError("Study contract identity drifted")
    if expected.get("source_checkout") != {"commit": SOURCE_HEAD, "tree": SOURCE_TREE} or _head() != (SOURCE_HEAD, SOURCE_TREE):
        raise ValueError("Exact CWR source binding drifted")
    if expected.get("predecessor", {}).get("terminal_sha256") != PREDECESSOR_TERMINAL_SHA256 or expected.get("predecessor", {}).get("settled_state_count") != 9:
        raise ValueError("Settled v3 predecessor binding drifted")
    base = _base()
    candidate = base.candidate_leaf()
    if expected.get("candidate") != {"leaf_id": LEAF_ID, "text": candidate["text"]}:
        raise ValueError("Approved S1 candidate wording drifted")
    if expected.get("candidate_sha256") != hashlib.sha256(canonical(expected["candidate"])).hexdigest():
        raise ValueError("Approved S1 candidate commitment drifted")
    if expected.get("freshness_audit") != {
        "frozen_prior_corpus_roots": list(FRESHNESS_AUDIT_ROOTS),
        "excluded_declared_descendants": list(EXCLUDED_DECLARED_DESCENDANTS),
    }:
        raise ValueError("Incidental-determiner freshness audit declaration drifted")
    if expected.get("execution") != {"batch_attempts": 1, "batch_size": 1, "model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high", "retry_or_resume": "forbidden", "slots": 3}:
        raise ValueError("Singleton execution policy drifted")
    if artifact()["text"] != "At noon: the empty platform.\nA parcel under the bench.\nThree pigeons by the fountain—\nthen the timetable, still blank.":
        raise ValueError("Approved incidental-determiner artifact drifted")
    motif_audit()
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": 3, "motif_audit": "disjoint", "promotion": "none"}


def _task(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"incidental-determiner-{slot['slot_id']}", "artifact_id": slot["slot_id"], "context": {"artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied poem", "completion_status": "complete", "background": ["Evaluate the recurrence of the determiner ‘the’ across the supplied poem."], "constraints": ["Use only the supplied poem as verdict evidence."], "audience": []}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["slot_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": hashlib.sha256(canonical(task)).hexdigest(), "contract_id": task["contract_id"], "artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied poem", "compatibility_mode": "reviewed_override", "decision_id": "incidental-determiner-singleton-v1", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for a supplied poem."}


def _render(slot: Mapping[str, Any], root: Path) -> str:
    artifact_path = root / "inputs" / f"{slot['slot_id']}.txt"
    task_path = root / "contracts" / f"{slot['slot_id']}.json"
    registry, bundles = root / "catalog" / "candidate-registry.json", root / "catalog" / "bundles.json"
    task = core.load_data(task_path)
    modules = core.load_modules(registry)
    bundle = core.resolve_bundle(core.load_bundles(bundles), BUNDLE_ID)
    materialized, materialized_bundle, _ = materialize_weight_profile(modules, bundle, None)
    compiled = core.compile_bundle(materialized, materialized_bundle, task_contract=task)
    questions = core.compiled_questions(compiled)
    binary = "\n\n".join(str(runner._read_text_record(path)["text"]).strip() for path in (root / "runtime-book" / "prompts" / "judge" / "JUDGE_PREFIX.md", root / "runtime-book" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md"))
    return runner._render_prompt(binary_prompt=binary, artifact=runner._read_text_record(artifact_path), contexts=(), bundle_id=BUNDLE_ID, artifact_id=str(slot["slot_id"]), questions=questions, task_contract_context=runner._task_contract_judge_context(task), prompt_rendering_version=runner.PROMPT_RENDERING_VERSION, provider="codex", model="gpt-5.6-sol")


def _snapshot(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda value: value.as_posix())}


def dry_freeze(private_root: str | Path) -> dict[str, Any]:
    set_work_root(private_root); validate_package(); root = dry_root()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fresh private dry root already exists")
    root.mkdir(parents=True, exist_ok=False)
    base = _base(); base.overlay(root)
    write_once(root / "catalog" / "candidate-registry.json", canonical(base.candidate_registry()))
    write_once(root / "catalog" / "bundles.json", canonical(base.bundle()))
    prompt_rows: dict[str, dict[str, Any]] = {}
    for slot in slots():
        slot_id = str(slot["slot_id"]); task = _task(slot)
        write_once(root / "inputs" / f"{slot_id}.txt", artifact()["text"].encode("utf-8"))
        write_once(root / "contracts" / f"{slot_id}.json", canonical(task))
        write_once(root / "overrides" / f"{slot_id}.json", canonical(_override(slot, task)))
        raw = _render(slot, root).encode("utf-8")
        write_once(root / "frozen-prompts" / f"{slot_id}.prompt.txt", raw)
        prompt_rows[slot_id] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "crlf_pairs": raw.count(b"\r\n")}
    receipt = {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "snapshot_files": _snapshot(root), "derivation": "production_renderer_raw_utf8_bytes"}
    write_once(root / "snapshot-receipt.v1.json", canonical(receipt))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": [slot["slot_id"] for slot in slots()], "prompts": prompt_rows, "snapshot_receipt_sha256": sha(root / "snapshot-receipt.v1.json"), "predecessor_terminal_sha256": PREDECESSOR_TERMINAL_SHA256, "claim": "absent", "live_execution": "unavailable", "promotion": "none"}
    write_once(root / "dry-manifest.v1.json", canonical(manifest))
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": 3, "dry_manifest_sha256": sha(root / "dry-manifest.v1.json"), "promotion": "none"}


def validate_checkpoint_prompt(slot_id: str, gzip_path: str | Path) -> dict[str, Any]:
    expected = dry_root() / "frozen-prompts" / f"{slot_id}.prompt.txt"
    observed = gzip.decompress(Path(gzip_path).read_bytes())
    if observed != expected.read_bytes():
        raise ValueError("Checkpoint raw prompt bytes differ from the frozen production render")
    return {"slot_id": slot_id, "sha256": hashlib.sha256(observed).hexdigest(), "bytes": len(observed)}
