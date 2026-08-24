"""Image-only executor for the frozen L2 C03 visual-control successor."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-l2-c03-visual-control-successor-v1-execution-v1"
SOURCE_COMMIT = "15f30863eee60619382c4b87fd3a13dd778ec50d"
SOURCE_TREE = "ed6780dac562e4d1789de79b32428b07a38464e1"
SOURCE_PATH = "evaluation-results/hbq-l2-c03-visual-control-successor-v1"
SOURCE_ROOT = ROOT.parent / "hbq-l2-c03-visual-control-successor-v1"
PREDECESSOR_PATH = "evaluation-results/hbq-l2-construct-microgate-v1"
PREDECESSOR_ROOT = ROOT.parent / "hbq-l2-construct-microgate-v1"
PREDECESSOR_TREE = "77fe3c82a8ea94a83bf01cb870b0e01a9d750071"
LIFECYCLE_PATH = "evaluation-results/hbq-l2-construct-microgate-v2-execution-v2/study.py"
LIFECYCLE_BLOB = "0ea7a50d9c5c1ee1e1a4c54761605d8fd89c51fc"
SLOTS = 12
MAX_SENDS = 12
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
NORMALIZATION_POLICY = "invalid_exact_quote_to_summary_v1"
SOURCE_FILES = {
    "README.md": "b8c8a8d391e98ab254154bfc9fa01340197b48fd",
    "assets/generate_structural_planes.py": "c4d576d7ac8f0a4a070bcbdda58cf561ebb955ef",
    "expected-ledger.json": "441415e540ced8a07062feb94a0400260ff532dd",
    "public-synthetic-corpus.json": "cd2095b3dcd0ba4af01e93f555803f62a3253bc6",
    "run.py": "6b3d9c00cd2fa86f6209c23aebd1df953e981ba1",
    "study-contract.json": "4968fb0d2d70e80fb8660d925096b71a045af9b7",
    "study.py": "446d7397da0d8faf1407e1a78b55eda280619c40",
}
PREDECESSOR_FILES = {
    "README.md": "0e9eb52414200c33f338a8b0ef76c08244e820d6",
    "assets/generate_geometry_fixture.py": "1b6b7a35e4c9553880a81baeb441e658267cd8ea",
    "expected-ledger.json": "6bec05c3684aa2ef0b2d907ada1ea0b55f7c73cb",
    "public-synthetic-corpus.json": "4d40ce2013a728fb05f62e406e53f8dbd2063aec",
    "run.py": "2aa7a4f9a5541c6b7b8368f446a572a4f822657f",
    "study-contract.json": "a276231aaa8b8cf1c510fad6cf9ec52336abd528",
    "study.py": "283b78ef85e5290eb8bb3a3010b15095e6af8c3d",
}
RUNTIME_PATHS = (
    "src/hbqrs/runner.py", "src/hbqrs/study_identity.py", "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md", "schema/hbq_judge_response.schema.json",
    "registry/question_index.jsonl", "registry/criterion_ownership.json",
    "registry/all_modules.json", "bundles/all_bundles.jsonl",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.strip() or "git binding lookup failed")
    return done.stdout.strip()


def _git_bytes(*args: str) -> bytes:
    done = subprocess.run(["git", *args], cwd=REPOSITORY, capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.decode("utf-8", errors="replace").strip() or "git blob lookup failed")
    return bytes(done.stdout)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _runtime_bindings() -> dict[str, str]:
    return {path: _git("rev-parse", f"{SOURCE_COMMIT}:{path}") for path in RUNTIME_PATHS}


def _verify_current_runtime_bytes() -> None:
    for relative, expected in _runtime_bindings().items():
        if _git("hash-object", relative) != expected:
            raise ValueError(f"Current runtime differs from pinned source bytes: {relative}")


def validate_package() -> dict[str, Any]:
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "status": "frozen_unexecuted",
        "source": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "path": SOURCE_PATH, "files": SOURCE_FILES},
        "predecessor": {"commit": SOURCE_COMMIT, "tree": PREDECESSOR_TREE, "path": PREDECESSOR_PATH, "files": PREDECESSOR_FILES},
        "lifecycle_dependency": {"commit": SOURCE_COMMIT, "path": LIFECYCLE_PATH, "blob": LIFECYCLE_BLOB},
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_call": True, "slots": SLOTS, "one_physical_attempt_per_slot": True, "retry_or_resume": "forbidden", "canonical_quote_normalization": NORMALIZATION_POLICY, "paid_route": "forbidden"},
        "privacy": {"expected_ledger_read_by_executor": False, "external_boolean_scorer_required": True, "publication": "aggregate_only"},
        "gating": {"all_four_cells_three_of_three": "FIXTURE_DIAGNOSIS_SUPPORTED", "any_complete_cell_miss": "NO_GO", "incomplete_or_ambiguous": "no_result"}, "promotion": "none",
    }
    if contract() != expected:
        raise ValueError("Execution contract drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{SOURCE_PATH}") != SOURCE_TREE:
        raise ValueError("Pinned C03 source tree is unavailable")
    for name, blob in SOURCE_FILES.items():
        relative = f"{SOURCE_PATH}/{name}"
        if _git("rev-parse", f"{SOURCE_COMMIT}:{relative}") != blob or _git("hash-object", relative) != blob:
            raise ValueError(f"Current C03 freeze differs from pinned bytes: {name}")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{PREDECESSOR_PATH}") != PREDECESSOR_TREE:
        raise ValueError("Pinned C03 predecessor tree is unavailable")
    for name, blob in PREDECESSOR_FILES.items():
        relative = f"{PREDECESSOR_PATH}/{name}"
        if _git("rev-parse", f"{SOURCE_COMMIT}:{relative}") != blob or _git("hash-object", relative) != blob:
            raise ValueError(f"Current C03 predecessor differs from pinned bytes: {name}")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{LIFECYCLE_PATH}") != LIFECYCLE_BLOB:
        raise ValueError("Pinned lifecycle dependency is unavailable")
    _verify_current_runtime_bytes()
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0}


def _exec_frozen_module(name: str, path: Path, source: bytes) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


@lru_cache(maxsize=1)
def _source() -> ModuleType:
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    source = _exec_frozen_module(
        "hbq_l2_c03_visual_control_successor_frozen_v1",
        SOURCE_ROOT / "study.py",
        _git_bytes("show", f"{SOURCE_COMMIT}:{SOURCE_PATH}/study.py"),
    )
    source.predecessor = _frozen_predecessor
    return source


@lru_cache(maxsize=1)
def _frozen_predecessor() -> ModuleType:
    """Execute the bound C03 dependency only after all its bytes are verified."""
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    return _exec_frozen_module(
        "hbq_l2_construct_microgate_v1_frozen_for_c03_execution",
        PREDECESSOR_ROOT / "study.py",
        _git_bytes("show", f"{SOURCE_COMMIT}:{PREDECESSOR_PATH}/study.py"),
    )


@lru_cache(maxsize=1)
def _lifecycle() -> ModuleType:
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    module = _exec_frozen_module(
        "hbq_l2_construct_lifecycle_frozen_v2",
        REPOSITORY / LIFECYCLE_PATH,
        _git_bytes("show", f"{SOURCE_COMMIT}:{LIFECYCLE_PATH}"),
    )
    module.STUDY_ID = STUDY_ID
    module.SLOTS = SLOTS
    module.MAX_SENDS = MAX_SENDS
    module.VERDICTS = VERDICTS
    module.NORMALIZATION_POLICY = NORMALIZATION_POLICY
    module.RUNTIME_PATHS = RUNTIME_PATHS
    module.PINNED_RUNTIME_HASHES = _runtime_bindings()
    module.validate_package = validate_package
    module._verify_current_runtime_bytes = _verify_current_runtime_bytes
    module._runtime_bindings = _runtime_bindings
    module.build_schedule = build_schedule
    module.prepare = prepare
    module.dry_run = dry_run
    module._validated_schedule = _validated_schedule
    module._aggregate_test_only = _aggregate_test_only
    return module


def _canonical_prompt_bytes(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""):
        raise ValueError("Prompt contains a lone CR byte")
    return value.replace(b"\r\n", b"\n")


def _run_id(slot_id: str, logical_id: str) -> str:
    return "l2c03exec-v1-" + slot_id + "-" + sha256_bytes(logical_id.encode("utf-8"))[:20]


@lru_cache(maxsize=1)
def _schedule_template() -> tuple[bytes, ...]:
    source = _source()
    artifacts = {str(case["case_id"]): dict(case) for case in source.load_corpus()["cases"]}
    leaves = (
        "form.visual.environment_or_location_illustration.perspective",
        "form.visual.visual_craft_and_artifact_control.perspective",
    )
    rows: list[dict[str, Any]] = []
    for case_id in ("s01", "s02"):
        artifact = artifacts[case_id]
        png = source.fixture_module().fixture_png_bytes()[artifact["image_fixture"]]
        image_input = {
            "name": str(artifact["artifact_name"]), "mime_type": "image/png",
            "bytes": len(png), "sha256": sha256_bytes(png),
        }
        for leaf_id in leaves:
            question = source.deepcopy(source.predecessor().production_question(leaf_id))
            prompt = source.production_runner._render_prompt(
                binary_prompt=source.predecessor().binary_prompt(),
                artifact={"name": artifact["artifact_name"], "text": ""}, contexts=[],
                bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact",
                questions=[question], task_contract_context=source.predecessor().task_context_for(artifact),
            )
            for forbidden in (case_id, "expected_verdict", "expected-ledger", "structural_plane_incompatible_v1", "structural_plane_coherent_v1"):
                if forbidden in prompt:
                    raise ValueError("Provider-facing prompt leaked fixture or ledger metadata")
            prompt_bytes = _canonical_prompt_bytes(prompt.encode("utf-8"))
            artifact_id = "l2c03-artifact-" + sha256_bytes(case_id.encode("utf-8"))[:16]
            artifact_sha256 = sha256_bytes(b"text\x00\x00image/png\x00" + png)
            for repeat in range(1, 4):
                slot_id = f"l2c03exec-v1-{len(rows) + 1:03d}"
                condition = {
                    "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high",
                    "strict_ai": True, "batch_size": 1, "attempt_lifecycle_policy": "terminal_sidecar_v1",
                    "leaf_id": leaf_id, "prompt_sha256": sha256_bytes(prompt_bytes),
                    "rubric_sha256": sha256_bytes(_git_bytes("show", f"{SOURCE_COMMIT}:registry/all_modules.json")),
                }
                from hbqrs.study_identity import logical_sample_id
                logical_id = logical_sample_id(
                    study_id=STUDY_ID, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
                    condition=condition, repetition=repeat, rubric_revision="1.2.0",
                )
                rows.append({
                    "slot_id": slot_id, "case_id": case_id, "artifact_id": artifact_id,
                    "artifact_name": artifact["artifact_name"], "artifact_kind": artifact["artifact_type"],
                    "artifact_text": "", "artifact_sha256": artifact_sha256,
                    "bundle_id": artifact["bundle_id"], "leaf_id": leaf_id, "repeat": repeat,
                    "completion_status": artifact["completion_status"], "prompt": prompt_bytes.decode("utf-8"),
                    "prompt_sha256": sha256_bytes(prompt_bytes), "image_input": image_input,
                    "condition": condition, "logical_sample_id": logical_id,
                    "run_id": _run_id(slot_id, logical_id),
                })
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS:
        raise ValueError("C03 execution slot geometry drifted")
    if len({(row["case_id"], row["leaf_id"]) for row in rows}) != 4 or not all(row["image_input"] for row in rows):
        raise ValueError("C03 execution requires four image-backed cells")
    return tuple(canonical_json(row) for row in rows)


def build_schedule() -> list[dict[str, Any]]:
    return [json.loads(value.decode("utf-8")) for value in _schedule_template()]


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("slot_id", "case_id", "artifact_id", "artifact_name", "artifact_kind", "artifact_sha256", "bundle_id", "leaf_id", "repeat", "completion_status", "prompt_sha256", "image_input", "condition", "logical_sample_id", "run_id")
    return {key: slot[key] for key in keys}


def _prepare(private_root: str | Path) -> dict[str, Any]:
    base = _lifecycle()
    root = base._external_root(private_root)
    schedule = build_schedule()
    source = _source()
    fixtures = source.fixture_module().fixture_png_bytes()
    base._write_or_verify(base._frozen_schema_path(root), _git_bytes("show", f"{SOURCE_COMMIT}:schema/hbq_judge_response.schema.json"))
    for slot in schedule:
        image = slot["image_input"]
        path = base._input_path(root, slot)
        source_bytes = fixtures[next(case["image_fixture"] for case in source.load_corpus()["cases"] if case["artifact_name"] == image["name"])]
        base._write_or_verify(path, source_bytes)
        if base._attachment_record(path) != image:
            raise ValueError("Prepared C03 PNG attachment bytes drifted")
        base._write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", _canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    base._write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0, "visual_png_slots": SLOTS}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validate_package()
    return _prepare(private_root)


def _validated_schedule(private_root: str | Path) -> list[dict[str, Any]]:
    base = _lifecycle()
    root = base._external_root(private_root)
    validate_package()
    schedule = build_schedule()
    manifest = {
        "format_version": 1, "study_id": STUDY_ID,
        "contract_sha256": sha256_file(ROOT / "study-contract.json"),
        "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS,
        "slots": [_public_slot(slot) for slot in schedule],
    }
    if _load_json(root / "study-manifest.json") != manifest:
        raise ValueError("C03 prepared manifest or runtime binding drifted; dry-run again")
    hashes = {str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}
    expected_runtime = {
        "format_version": 1, "study_id": STUDY_ID,
        "slots": [_public_slot(slot) for slot in schedule],
        "rendered_prompt_aggregate_sha256": sha256_bytes(canonical_json(hashes)),
    }
    if _load_json(root / "runtime-schedule.json") != expected_runtime:
        raise ValueError("C03 prepared runtime schedule drifted; dry-run again")
    authentication = _load_json(root / "receipts" / "subscription-authentication.v1.json")
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != base._disclosure(schedule, root, codex_binary=str(authentication["binary_path"])):
        raise ValueError("Exact C03 preexecution disclosure is unavailable or drifted")
    return schedule


def dry_run(private_root: str | Path, *, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    base = _lifecycle()
    root = base._external_root(private_root)
    validate_package()
    environment = base._minimal_environment()
    authentication = base.subscription_authentication(runner_call=auth_call, environment=environment)
    prepared = _prepare(root)
    schedule = build_schedule()
    for slot in schedule:
        prompt_path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if prompt_path.read_bytes() != _canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")):
            raise ValueError("Frozen C03 prompt bytes drifted")
        if base._attachment_record(base._input_path(root, slot)) != slot["image_input"]:
            raise ValueError("C03 requires every exact PNG attachment")
    hashes = {str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}
    aggregate = sha256_bytes(canonical_json(hashes))
    runtime = {"format_version": 1, "study_id": STUDY_ID, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": aggregate}
    base._write_or_verify(root / "runtime-schedule.json", canonical_json(runtime))
    base._write_or_verify(root / "receipts" / "subscription-authentication.v1.json", canonical_json(authentication))
    base._write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(base._disclosure(schedule, root, codex_binary=authentication["binary_path"])))
    report = {
        "mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS,
        "visual_png_slots": SLOTS, "first_command": base.command_for(schedule[0], root, codex_binary=authentication["binary_path"]),
        "last_command": base.command_for(schedule[-1], root, codex_binary=authentication["binary_path"]),
        "rendered_prompt_aggregate_sha256": aggregate,
    }
    base._write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json(report))
    return {**prepared, **report}


def execute(private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Dispatch exactly one image-backed attempt per C03 slot when explicitly authorized."""
    return _lifecycle().execute(
        private_root, allow_remote=allow_remote,
        acknowledged_zero_incremental_charge=acknowledged_zero_incremental_charge,
        runner_call=runner_call, auth_call=auth_call,
    )


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, codex_binary: str | None = None) -> list[str]:
    return _lifecycle().command_for(slot, private_root, codex_binary=codex_binary)


def _aggregate_test_only(*, schedule: list[dict[str, Any]], records: list[Mapping[str, Any]], scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(records) != SLOTS:
        raise ValueError("Settlement requires all twelve singleton records")
    by_slot = {str(record.get("slot_id")): record for record in records}
    if len(by_slot) != SLOTS:
        raise ValueError("Settlement has duplicate singleton identities")
    matches: dict[tuple[str, str], list[bool]] = defaultdict(list)
    verdict_counts: Counter[str] = Counter()
    for slot in schedule:
        record = by_slot.get(str(slot["slot_id"]))
        if record is None or record.get("logical_sample_id") != slot["logical_sample_id"] or record.get("run_id") != slot["run_id"] or record.get("verdict") not in VERDICTS:
            raise ValueError("Settlement record has malformed singleton identity")
        correct = scorer(slot, record)
        if type(correct) is not bool:
            raise ValueError("External scorer must return a boolean only")
        matches[(str(slot["case_id"]), str(slot["leaf_id"]))].append(correct)
        verdict_counts[str(record["verdict"])] += 1
    if len(matches) != 4 or any(len(values) != 3 for values in matches.values()):
        raise ValueError("Settlement requires four complete C03 cells")
    totals = Counter(sum(values) for values in matches.values())
    decision = "FIXTURE_DIAGNOSIS_SUPPORTED" if totals[3] == 4 else "NO_GO"
    aggregate_cells = {"zero_of_three": totals[0], "one_of_three": totals[1], "two_of_three": totals[2], "three_of_three": totals[3], "total": 4}
    normalization_events = sum(len(record.get("normalization_audit", [])) for record in by_slot.values())
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "aggregate_cells": aggregate_cells, "verdict_counts": {state: verdict_counts[state] for state in sorted(VERDICTS)}, "normalization_events": normalization_events, "visual_attachment_slots": SLOTS, "expected_ledger_opened_by_executor": False, "publication_requires": "settlement-publication.v1.json", "promotion": "none"}
    public = {"study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "aggregate_cells": aggregate_cells, "normalization_events": normalization_events, "visual_attachment_slots": SLOTS, "publication_requires": "settlement-publication.v1.json", "promotion": "none"}
    return settlement, public


def settle(private_root: str | Path, *, scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None) -> dict[str, Any]:
    """Settle only with an external post-terminal boolean scorer."""
    if scorer is None:
        raise ValueError("Settlement requires an external expected-ledger boolean scorer")
    return _lifecycle().settle(private_root, scorer=scorer)
