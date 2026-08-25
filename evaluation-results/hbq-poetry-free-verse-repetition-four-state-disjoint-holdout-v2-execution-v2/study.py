"""Provider-free fresh-sample successor for the terminal S1 execution attempt."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import gzip
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v2"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V2_ROOT = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2"
V2_STUDY_SHA256 = "449493bf8fcc4bbbe43e4566e9d21dc9c04e360f3e581bb7a2031ca70deeabf1"
V2_CONTRACT_SHA256 = "188dce8250e57d9fd17623d9c7ff2a072d0d4b226e2ceca8dac30498d0de9807"
V2_CORPUS_SHA256 = "b5143ede9665af44edeacdefdbdfc470ce2a754f0c9f9a22cd51d91feb36ac2d"
V2_CANDIDATE_LEAF_SHA256 = "b8b874772e62965042bc75c8171a933bc3d85e3d785da911019d52cbfd268219"
PREDECESSOR = {
    "claim_sha256": "cd1924031f8e75e4b0357ba42106d9e0591954d9ec649e555fa3b1423783d7d4",
    "snapshot_receipt_sha256": "73322f35955f97e770a94f356c2b77aef348b706c5c66a971d2728540274b6e1",
    "review_sha256": "989668f75456f79d652fef98249b330820beacae2e9286cde963b7804559c910",
    "driver_sha256": "e04ee70ab059124ddc58c88b262159f8bf5764fb11e7256c8b61ac4347d8a209",
    "frozen_configurations_sha256": "5a534ca94aa0609bb1bd8dbba11fcce6574e062c58cbda4de34dcbe7b09e378b",
    "preexecution_disclosure_sha256": "4b0452394cbd529a0d65785ec42659bb73f78a888fc56e4d3cd91628f26310d5",
    "driver_freeze_sha256": "3302e98f252f3ad3ed845a6f87d15b4e060193600a70fb8bda35e4bd7ae38810",
    "terminal_sha256": "6dcd80f0692881d42e7f84ff8cba4489dc27d0e848855b04192f0f2e71b7140e",
    "run_sha256": "91c7d0ad6e1bd6b63372e8009da3ddb4d5db5c5e80265c774b2407c417a73a0b",
    "checkpoint_sha256": "fda9c827f3a8430a4525ebb8a401f0485367f8215f880739c32f0558ed76562b",
    "raw_response_sha256": "fe41f77a2ea49be4fae8f6199bf423ac22de9dcabd9aef7a5768fa79e95eb660",
    "prompt_gzip_sha256": "e8370af26ef0682b1839161b9cb08b3f1be58790943299a495428dc12ba8d8db",
}
LEAF_ID = "form.poetry.free_verse.repetition"
BUNDLE_ID = "poetry_free_verse_repetition_singleton_v2"
WORK_ROOT: Path | None = None

sys.path.insert(0, str(REPOSITORY / "src"))
from hbqrs import core, runner  # noqa: E402
from hbqrs.weights import materialize_weight_profile  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Write-once artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _v2() -> Any:
    study = V2_ROOT / "study.py"
    if sha(study) != V2_STUDY_SHA256 or sha(V2_ROOT / "study-contract.json") != V2_CONTRACT_SHA256 or sha(V2_ROOT / "public-synthetic-corpus.json") != V2_CORPUS_SHA256:
        raise ValueError("Bound v2 study drifted")
    spec = importlib.util.spec_from_file_location("s1_v2_execution_v2_bound", study)
    if spec is None or spec.loader is None:
        raise ValueError("Bound v2 study is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def corpus() -> list[dict[str, str]]:
    value = load(ROOT / "public-synthetic-corpus.json").get("cases")
    if not isinstance(value, list) or len(value) != 4 or not all(isinstance(row, dict) and set(row) == {"case_id", "text"} and isinstance(row["case_id"], str) and isinstance(row["text"], str) for row in value):
        raise ValueError("Fresh public-synthetic corpus is invalid")
    return [{"case_id": str(row["case_id"]), "text": str(row["text"])} for row in value]


def slots() -> list[dict[str, Any]]:
    plan = (("r-8c13", "s1x-b782", 2), ("r-5af1", "s1x-e630", 1), ("r-d462", "s1x-4d91", 3), ("r-190e", "s1x-2ac5", 2), ("r-a7d9", "s1x-b782", 1), ("r-63c4", "s1x-e630", 3), ("r-f08b", "s1x-4d91", 1), ("r-2e76", "s1x-2ac5", 3), ("r-c951", "s1x-b782", 3), ("r-71bd", "s1x-e630", 2), ("r-4f2a", "s1x-4d91", 2), ("r-9e35", "s1x-2ac5", 1))
    rows = {row["case_id"]: row for row in corpus()}
    if len(plan) != 12 or len({slot for slot, _, _ in plan}) != 12 or {(case, repeat) for _, case, repeat in plan} != {(case, repeat) for case in rows for repeat in (1, 2, 3)}:
        raise ValueError("Fresh opaque schedule drifted")
    return [{"slot_id": slot, "case_id": case, "repeat": repeat} for slot, case, repeat in plan]


def contract() -> dict[str, Any]:
    return load(ROOT / "study-contract.json")


def expected_contract() -> dict[str, Any]:
    lineage_keys = ("claim_sha256", "review_sha256", "driver_sha256", "terminal_sha256", "run_sha256", "checkpoint_sha256", "raw_response_sha256", "prompt_gzip_sha256")
    return {"format_version": 1, "study_id": STUDY_ID, "status": "provider_free_fresh_carrier_execution_successor", "source_checkout": {"commit": SOURCE_HEAD, "tree": SOURCE_TREE}, "v2_semantics": {"study_sha256": V2_STUDY_SHA256, "contract_sha256": V2_CONTRACT_SHA256, "public_corpus_sha256": V2_CORPUS_SHA256, "candidate_leaf_sha256": V2_CANDIDATE_LEAF_SHA256}, "predecessor": {"classification": "NO_RESULT_PROMPT_BYTE_BINDING_FAILURE", "contacts": 1, "completed_slots": 0, "untouched_slots": 11, "semantic_output": "non_voting", "bindings": {key: PREDECESSOR[key] for key in lineage_keys}}, "fresh_geometry": {"cases": 4, "repeats_per_case": 3, "slots": 12, "fresh_carriers": True, "fresh_opaque_slots": True, "reused_predecessor_logical_samples": False}, "execution": {"provider_calls": 0, "claim": "unavailable_until_independent_review", "live_execution": "unavailable", "one_attempt": True, "retry_or_resume": "forbidden", "normalization_or_settlement_repair": "forbidden"}, "promotion": "none"}


def set_work_root(path: str | Path) -> Path:
    root = Path(path).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("External work root is required")
    global WORK_ROOT
    WORK_ROOT = root
    return root


def dry_root() -> Path:
    if WORK_ROOT is None:
        raise ValueError("An explicit external work root is required")
    return WORK_ROOT / "execution-v2-dry"


def _head() -> tuple[str, str]:
    values = []
    for argument in ("HEAD", f"{SOURCE_HEAD}^{{tree}}"):
        result = subprocess.run(["git", "rev-parse", argument], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
        if result.returncode:
            raise ValueError("CWR Git binding unavailable")
        values.append(result.stdout.strip())
    return values[0], values[1]


def validate_package() -> dict[str, Any]:
    if contract() != expected_contract():
        raise ValueError("Successor contract drifted")
    if load(ROOT / "predecessor-bindings.json") != PREDECESSOR:
        raise ValueError("Predecessor binding drifted")
    if _head() != (SOURCE_HEAD, SOURCE_TREE):
        raise ValueError("Exact CWR source binding drifted")
    v2 = _v2()
    if v2.candidate_leaf() is None or hashlib.sha256(v2.canonical_json(v2.candidate_leaf())).hexdigest() != V2_CANDIDATE_LEAF_SHA256:
        raise ValueError("Candidate wording drifted")
    if any(row["case_id"] == "s1h-cinder" for row in corpus()) or any(slot["slot_id"] == "q-46ac81" for slot in slots()):
        raise ValueError("Predecessor sample was reused")
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": 12, "promotion": "none"}


def _render(slot: Mapping[str, Any], root: Path) -> str:
    v2 = _v2(); slot_id = str(slot["slot_id"])
    artifact_path = root / "inputs" / f"{slot_id}.txt"
    task_path = root / "contracts" / f"{slot_id}.json"
    registry, bundles = root / "catalog" / "candidate-registry.json", root / "catalog" / "bundles.json"
    task = core.load_data(task_path)
    modules = core.load_modules(registry)
    bundle = core.resolve_bundle(core.load_bundles(bundles), BUNDLE_ID)
    materialized_modules, materialized_bundle, _ = materialize_weight_profile(modules, bundle, None)
    compiled = core.compile_bundle(materialized_modules, materialized_bundle, task_contract=task)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order.get(str(item.get("role")), 99))
    prompts = [root / "runtime-book" / "prompts" / "judge" / "JUDGE_PREFIX.md", root / "runtime-book" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md"]
    binary = "\n\n".join(str(runner._read_text_record(path)["text"]).strip() for path in prompts)
    return runner._render_prompt(binary_prompt=binary, artifact=runner._read_text_record(artifact_path), contexts=(), bundle_id=BUNDLE_ID, artifact_id=slot_id, questions=questions, task_contract_context=runner._task_contract_judge_context(task), prompt_rendering_version=runner.PROMPT_RENDERING_VERSION, provider="codex", model="gpt-5.6-sol")


def frozen_command(slot: Mapping[str, Any], root: Path) -> list[str]:
    slot_id = str(slot["slot_id"])
    return [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "candidate-registry.json"), "--bundles", str(root / "catalog" / "bundles.json"), "judge", str(root / "inputs" / f"{slot_id}.txt"), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--reasoning", "high", "--strict-ai", "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", "terminal_sidecar_v1", "--artifact-id", slot_id, "--question-id", LEAF_ID, "--task-contract", str(root / "contracts" / f"{slot_id}.json"), "--scope-compatibility-override", str(root / "overrides" / f"{slot_id}.json"), "--output-dir", str(root / "future-runs" / slot_id), "--allow-remote"]


def dry_freeze() -> dict[str, Any]:
    validate_package(); root = dry_root()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fresh dry root already exists")
    root.mkdir(parents=True, exist_ok=False)
    v2 = _v2()
    v2.overlay(root)
    v2.write_once(root / "catalog" / "candidate-registry.json", v2.canonical_json(v2.candidate_registry()))
    v2.write_once(root / "catalog" / "bundles.json", v2.canonical_json(v2.bundle()))
    by_case = {row["case_id"]: row for row in corpus()}
    prompts: dict[str, dict[str, Any]] = {}
    for slot in slots():
        slot_id = str(slot["slot_id"])
        v2.write_once(root / "inputs" / f"{slot_id}.txt", by_case[str(slot["case_id"])]["text"].encode("utf-8"))
        task = v2.task(slot)
        v2.write_once(root / "contracts" / f"{slot_id}.json", v2.canonical_json(task))
        v2.write_once(root / "overrides" / f"{slot_id}.json", v2.canonical_json(v2.override(slot, task)))
        raw = _render(slot, root).encode("utf-8")
        destination = root / "frozen-prompts" / f"{slot_id}.prompt.txt"
        write_once(destination, raw)
        prompts[slot_id] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "crlf_pairs": raw.count(b"\r\n")}
    commands = {str(slot["slot_id"]): frozen_command(slot, root) for slot in slots()}
    manifest = {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": [str(slot["slot_id"]) for slot in slots()], "prompts": prompts, "commands": commands, "predecessor": PREDECESSOR, "claim": "absent", "live_execution": "unavailable", "promotion": "none"}
    write_once(root / "dry-manifest.v1.json", canonical(manifest))
    return {"provider_calls": 0, "dry_manifest_sha256": sha(root / "dry-manifest.v1.json"), "slots": 12, "promotion": "none"}


def validate_checkpoint_prompt(slot_id: str, gzip_path: str | Path) -> dict[str, Any]:
    expected = dry_root() / "frozen-prompts" / f"{slot_id}.prompt.txt"
    if not expected.is_file():
        raise ValueError("Frozen prompt is unavailable")
    try:
        observed = gzip.decompress(Path(gzip_path).read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt gzip is invalid") from exc
    if observed != expected.read_bytes():
        raise ValueError("Checkpoint raw prompt bytes differ from the frozen production render")
    return {"slot_id": slot_id, "bytes": len(observed), "sha256": hashlib.sha256(observed).hexdigest()}


def execution_unavailable() -> None:
    raise ValueError("No claim or provider execution is available in this provider-free successor")
