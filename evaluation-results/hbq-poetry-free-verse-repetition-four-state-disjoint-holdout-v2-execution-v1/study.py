"""Provider-free one-shot preclaim successor for the S1 v2 holdout."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v1"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
V2_ROOT = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2"
V2_STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2"
V2_BINDINGS = {
    "study_contract_sha256": "188dce8250e57d9fd17623d9c7ff2a072d0d4b226e2ceca8dac30498d0de9807",
    "study_sha256": "449493bf8fcc4bbbe43e4566e9d21dc9c04e360f3e581bb7a2031ca70deeabf1",
    "public_corpus_sha256": "b5143ede9665af44edeacdefdbdfc470ce2a754f0c9f9a22cd51d91feb36ac2d",
    "sealed_outcomes_sha256": "fead2cb67c5a346a4f65663d056c045f0591743744642689b23b573e81d79867",
    "dry_manifest_sha256": "232e87def4d16291a63ebca6d205a5cbabba83b1531a7b4153f7cd0e8a36b1ae",
    "v1_public_corpus_sha256": "877cd802bb16fd2799b2fde9378b6c22e68834186266a84743264fea7e19bb43",
}
FROZEN_EXECUTION_DIRECTORY = "execution-v2-6ae9ee0"
SEALED_OUTCOMES_NAME = "sealed-outcomes.v2.json"
SNAPSHOT_DIRECTORY = "frozen-input-snapshot"
PRECLAIM_DIRECTORY = "execution-v1-preclaim"
REQUIRED_FILES = ("dry-manifest.v2.json",)
REQUIRED_DIRECTORIES = ("catalog", "contracts", "inputs", "overrides", "rendered-prompts", "runtime-book")
FROZEN_ROOT: Path | None = None
WORK_ROOT: Path | None = None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def write_once(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Write-once artifact drifted: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _v2() -> Any:
    study = V2_ROOT / "study.py"
    contract = V2_ROOT / "study-contract.json"
    corpus = V2_ROOT / "public-synthetic-corpus.json"
    if not study.is_file() or sha256_file(study) != V2_BINDINGS["study_sha256"] or not contract.is_file() or sha256_file(contract) != V2_BINDINGS["study_contract_sha256"] or not corpus.is_file() or sha256_file(corpus) != V2_BINDINGS["public_corpus_sha256"]:
        raise ValueError("V2 public freeze binding drifted")
    spec = importlib.util.spec_from_file_location("s1_v2_execution_bound", study)
    if spec is None or spec.loader is None:
        raise ValueError("V2 study is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def set_roots(*, frozen_root: str | Path, work_root: str | Path) -> tuple[Path, Path]:
    frozen, work = Path(frozen_root).resolve(), Path(work_root).resolve()
    for root in (frozen, work):
        try:
            root.relative_to(REPOSITORY.resolve())
        except ValueError:
            continue
        raise ValueError("External roots must be outside the CWR checkout")
    if frozen == work:
        raise ValueError("Frozen and preclaim roots must differ")
    global FROZEN_ROOT, WORK_ROOT
    FROZEN_ROOT, WORK_ROOT = frozen, work
    return frozen, work


def frozen_execution_root() -> Path:
    if FROZEN_ROOT is None:
        raise ValueError("An explicit frozen root is required")
    return FROZEN_ROOT / FROZEN_EXECUTION_DIRECTORY


def preclaim_root() -> Path:
    if WORK_ROOT is None:
        raise ValueError("An explicit preclaim root is required")
    return WORK_ROOT / PRECLAIM_DIRECTORY


def expected_contract() -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "status": "provider_free_preclaim_only",
        "source_checkout": {"commit": SOURCE_HEAD, "exact_head_required_before_claim": True},
        "v2_bindings": V2_BINDINGS,
        "source_snapshot": {"frozen_execution_directory": FROZEN_EXECUTION_DIRECTORY, "required_files": list(REQUIRED_FILES), "required_directories": list(REQUIRED_DIRECTORIES), "regenerate_or_replace_frozen_inputs": False},
        "execution": {"provider": "openai", "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "slots": 12, "one_fresh_session_per_slot": True, "one_physical_attempt_per_slot": True, "maximum_provider_sends": 12, "resume_or_retry": "forbidden", "normalization": "forbidden", "source_exact_evidence": "required", "paid_or_fallback_route": "forbidden", "live_execution_entrypoint": "unavailable_until_independent_review"},
        "lifecycle": {"claim_write_once": True, "terminal_write_once": True, "settlement_write_once": True, "preexisting_runs_rejected": True, "automatic_promotion": False},
        "promotion": "none",
    }


def _head() -> str:
    value = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if value.returncode:
        raise ValueError(value.stderr.strip() or "CWR HEAD is unavailable")
    return value.stdout.strip()


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in REQUIRED_FILES:
        path = root / name
        if not path.is_file():
            raise ValueError(f"Frozen input is missing: {name}")
        files.append(path)
    for name in REQUIRED_DIRECTORIES:
        directory = root / name
        if not directory.is_dir():
            raise ValueError(f"Frozen input directory is missing: {name}")
        files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def snapshot_map(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in _source_files(root)}


def verify_frozen_root() -> dict[str, Any]:
    _v2()
    if _head() != SOURCE_HEAD:
        raise ValueError("Exact CWR HEAD is required")
    v1_corpus = V2_ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1" / "public-synthetic-corpus.json"
    if not v1_corpus.is_file() or sha256_file(v1_corpus) != V2_BINDINGS["v1_public_corpus_sha256"]:
        raise ValueError("Reusable V1 public-corpus composition binding drifted")
    source = frozen_execution_root()
    sealed = source.parent / SEALED_OUTCOMES_NAME
    if not sealed.is_file() or sha256_file(sealed) != V2_BINDINGS["sealed_outcomes_sha256"]:
        raise ValueError("V2 sealed-outcomes binding drifted")
    manifest = source / "dry-manifest.v2.json"
    if sha256_file(manifest) != V2_BINDINGS["dry_manifest_sha256"]:
        raise ValueError("V2 dry-manifest binding drifted")
    data = load_json(manifest)
    if data.get("study_id") != V2_STUDY_ID or data.get("provider_calls") != 0 or data.get("rendered_slots") != 12 or data.get("execution_entrypoint") != "unavailable_until_independent_review":
        raise ValueError("V2 frozen dry-manifest is not a provider-free preclaim source")
    if any((source / name).exists() for name in ("runs", "responses", "execution-claim.v1.json", "execution-terminal.v1.json", "settlement.v1.json")):
        raise ValueError("Frozen source contains disallowed execution state")
    return {"source_snapshot_sha256": hashlib.sha256(canonical_json(snapshot_map(source))).hexdigest(), "files": len(snapshot_map(source)), "provider_calls": 0}


def validate_package() -> dict[str, Any]:
    if contract() != expected_contract():
        raise ValueError("Execution successor contract drifted")
    return verify_frozen_root()


def derive_snapshot() -> dict[str, Any]:
    verified = validate_package()
    source, target = frozen_execution_root(), preclaim_root() / SNAPSHOT_DIRECTORY
    mapping = snapshot_map(source)
    for relative, digest in mapping.items():
        destination = target / relative
        if destination.exists():
            if sha256_file(destination) != digest:
                raise ValueError("Existing derived input drifted")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
        if sha256_file(destination) != digest:
            raise ValueError("Derived input copy drifted")
    if snapshot_map(target) != mapping:
        raise ValueError("Derived snapshot differs from frozen inputs")
    receipt = {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "source_bindings": V2_BINDINGS, "source_snapshot_sha256": verified["source_snapshot_sha256"], "snapshot_files": mapping, "derivation": "byte_exact_copy_without_regeneration_or_replacement"}
    write_once(preclaim_root() / "snapshot-receipt.v1.json", canonical_json(receipt))
    return {"provider_calls": 0, "snapshot_files": len(mapping), "snapshot_receipt_sha256": sha256_file(preclaim_root() / "snapshot-receipt.v1.json")}


def _assert_preclaim_clean(root: Path) -> None:
    if any((root / name).exists() for name in ("runs", "responses", "execution-terminal.v1.json", "settlement.v1.json")):
        raise ValueError("Preclaim root already contains execution state")


def claim_only() -> dict[str, Any]:
    derived = derive_snapshot(); root = preclaim_root(); _assert_preclaim_clean(root)
    claim = root / "execution-claim.v1.json"
    if claim.exists():
        raise ValueError("One-shot preclaim already exists")
    value = {"format_version": 1, "study_id": STUDY_ID, "phase": "preclaim_only_no_provider_dispatch", "provider_calls": 0, "maximum_provider_sends": 12, "resume_or_retry": "forbidden", "normalization": "forbidden", "snapshot_receipt_sha256": derived["snapshot_receipt_sha256"], "live_execution_entrypoint": "unavailable_until_independent_review", "promotion": "none"}
    write_once(claim, canonical_json(value))
    return {"provider_calls": 0, "claim_sha256": sha256_file(claim), "promotion": "none"}


def execution_unavailable() -> None:
    raise ValueError("Live execution is unavailable until independent review")


def settle_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    root = preclaim_root(); receipt = root / "snapshot-receipt.v1.json"
    if not receipt.is_file() or not (root / "execution-claim.v1.json").is_file():
        raise ValueError("Write-once snapshot receipt and preclaim are required")
    if len(records) != 12 or len({str(row.get("slot_id")) for row in records}) != 12:
        raise ValueError("Settlement requires exactly twelve unique slots")
    sessions: set[str] = set(); grouped: dict[str, list[str]] = defaultdict(list)
    for row in records:
        session = str(row.get("session_sha256", ""))
        if len(session) != 64 or session in sessions:
            raise ValueError("Each slot requires one fresh committed provider session")
        sessions.add(session)
        if row.get("accepted_attempt") != 1 or row.get("rejected_retries") != 0 or row.get("normalization_events") != 0 or row.get("exact_quote_valid") is not True:
            raise ValueError("Settlement record violates one-shot exact-evidence policy")
        grouped[str(row.get("case_id"))].append(str(row.get("raw_verdict")))
    v2 = _v2(); v2.set_work_root(FROZEN_ROOT)
    outcomes = v2.sealed_outcomes()
    matched = set(grouped) == set(outcomes) and all(values == [outcomes[case_id]] * 3 for case_id, values in grouped.items())
    terminal = {"format_version": 1, "study_id": STUDY_ID, "phase": "all_twelve_settled", "provider_calls": 12, "promotion": "none"}
    result = {"format_version": 1, "study_id": STUDY_ID, "decision": "INDEPENDENT_PROMOTION_REVIEW_ELIGIBLE" if matched else "NO_GO", "completed_slots": 12, "promotion": "none", "automatic_promotion": False}
    write_once(root / "execution-terminal.v1.json", canonical_json(terminal)); write_once(root / "settlement.v1.json", canonical_json(result))
    return result
