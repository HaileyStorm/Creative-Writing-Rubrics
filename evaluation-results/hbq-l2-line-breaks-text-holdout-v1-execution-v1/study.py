"""One-shot text-only executor for the frozen L2 line-break holdout."""
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
STUDY_ID = "hbq-l2-line-breaks-text-holdout-v1-execution-v1"
SOURCE_COMMIT = "1290b6e7a244fc9388003240959e21504ca8cbf5"
SOURCE_TREE = "c392848ea50fb8eb1c19e409db73a0899fa24dc6"
SOURCE_PATH = "evaluation-results/hbq-l2-line-breaks-text-holdout-v1"
SOURCE_ROOT = ROOT.parent / "hbq-l2-line-breaks-text-holdout-v1"
LIFECYCLE_PATH = "evaluation-results/hbq-l2-construct-microgate-v2-execution-v2/study.py"
LIFECYCLE_BLOB = "0ea7a50d9c5c1ee1e1a4c54761605d8fd89c51fc"
SLOTS = MAX_SENDS = 24
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
NORMALIZATION_POLICY = "invalid_exact_quote_to_summary_v1"
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
NECESSITY = "form.poetry.free_verse.necessity"
CASE_IDS = ("t01", "t02", "t03", "t04")
SOURCE_FILES = {
    "README.md": "8f32f886e784eca8670f3314133ebed677bbdf43",
    "expected-ledger.json": "772affac15ba42d5fdf8cdce6dad01a7b4c59292",
    "public-synthetic-corpus.json": "3aca91931f5c7dc02e6f3fd2d4a0d88f7a927910",
    "run.py": "51cdf0d8655bfed738aa38e7fa1fbfaaa151181f",
    "study-contract.json": "91b35854954cd97c4539f25c5e40fd250d88a797",
    "study.py": "bc491525b54cfc27a4c619c56db2a9294ea3d12e",
}
SOURCE_LINEAGE = {
    "evaluation-results/hbq-l2-construct-microgate-v2": (
        SOURCE_COMMIT,
        {"README.md": "0d8e8a7f1472cdaa1f7173fe0da5cab58fa1965f", "public-synthetic-corpus.json": "ed266a1b73c052694fad64e4e5812048c4c86a97", "expected-ledger.json": "464f3d02cefdaf98f5ba2f5b6ff1e3e12fae6384", "study-contract.json": "6b9f6868d8a185a955a8f34bf4374972f45e0b3a", "study.py": "baf26d8da07ebcb067a62dd0c865fee77f1f2447", "run.py": "ac6a2ef22e2e49db0bcf957be44c7656e94b7fce"},
    ),
    "evaluation-results/hbq-l2-construct-microgate-v2-execution-v2-public-result-v1": (
        SOURCE_COMMIT,
        {"README.md": "d854cab65e5be6d2bcf89c85859d0648b79bfee2", "public-result.json": "5b53c472083bc7eed0167808282c1822bb10209f"},
    ),
    "evaluation-results/hbq-l2-c03-visual-control-successor-v1-execution-v1-public-result-v1": (
        "650f18dfee724db65d8bbc7fa2c7920ebcec1a9d",
        {"README.md": "c04ee365669ece0c5deb4ff07330ae8c30d0c218", "public-result.json": "b7522afcb3b323f48a1d2e98a1f5419b33eea245"},
    ),
}
RUNTIME_BLOBS = {
    "src/hbqrs/runner.py": "cc244ad40924c2a11c044268ca89af0fc1ba5f65",
    "src/hbqrs/study_identity.py": "a61aec19ac9be33fe8d8a45da4db5d74ba3a96ea",
    "prompts/judge/JUDGE_PREFIX.md": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "d2662edfccc115c6d0c4d97af82a10c9e926b853",
    "schema/hbq_judge_response.schema.json": "1034a35dcd6c30a75101f369627d60e155d65c2c",
    "registry/all_modules.json": "d94af34c80cf32b4d5a380167e66e2af39f29ad7",
    "bundles/all_bundles.jsonl": "718a935081abbf2d1949ceacfb9e5a45e81b85eb",
    "registry/criterion_ownership.json": "685846945ddd562992b313b17e8efa72692b8036",
    "registry/question_index.jsonl": "4ab3b7e11fe2e150cc0defafc22a29929cf5799c",
}
COMPILED_LEAF_HASHES = {
    LINE_BREAKS: "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c",
    NECESSITY: "a8c36e24125ba32db2694051252a5c17e9fc05abe48cd185f014b7b2a704e0eb",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git binding lookup failed")
    return result.stdout.strip()


def _git_bytes(*args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "git blob lookup failed")
    return bytes(result.stdout)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _verify_files(commit: str, root: Path, relative_root: str, files: Mapping[str, str], label: str) -> None:
    for name, blob in files.items():
        relative = f"{relative_root}/{name}"
        if _git("rev-parse", f"{commit}:{relative}") != blob or _git("hash-object", str(root / name)) != blob:
            raise ValueError(f"{label} differs from its pinned source bytes: {name}")


def _runtime_bindings() -> dict[str, str]:
    return {path: _git("rev-parse", f"{SOURCE_COMMIT}:{path}") for path in RUNTIME_BLOBS}


def _verify_current_runtime_bytes() -> None:
    if _runtime_bindings() != RUNTIME_BLOBS:
        raise ValueError("Pinned runtime Git blob provenance drifted")
    for path, blob in RUNTIME_BLOBS.items():
        if _git("hash-object", path) != blob:
            raise ValueError(f"Current runtime differs from pinned source bytes: {path}")


def validate_package() -> dict[str, Any]:
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "status": "frozen_unexecuted",
        "source": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "path": SOURCE_PATH},
        "lifecycle_dependency": {"commit": SOURCE_COMMIT, "path": LIFECYCLE_PATH, "blob": LIFECYCLE_BLOB},
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_call": True, "slots": SLOTS, "one_physical_attempt_per_slot": True, "retry_or_resume": "forbidden", "canonical_quote_normalization": NORMALIZATION_POLICY, "paid_route": "forbidden"},
        "delivery": {"text_only": True, "image_slots": 0, "image_flags": "forbidden", "attachments": "forbidden", "text_as_image": "forbidden"},
        "privacy": {"expected_ledger_read_by_executor": False, "external_boolean_scorer_required": True, "publication": "aggregate_only"},
        "gating": {"all_eight_cells_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "any_complete_cell_miss": "NO_GO", "incomplete_or_ambiguous": "no_result"}, "promotion": "none",
    }
    if contract() != expected:
        raise ValueError("Execution contract drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{SOURCE_PATH}") != SOURCE_TREE:
        raise ValueError("Pinned text-only source tree is unavailable")
    _verify_files(SOURCE_COMMIT, SOURCE_ROOT, SOURCE_PATH, SOURCE_FILES, "Frozen text-only source")
    for path, (commit, files) in SOURCE_LINEAGE.items():
        _verify_files(commit, ROOT.parent / Path(path).name, path, files, "Source-declared lineage")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{LIFECYCLE_PATH}") != LIFECYCLE_BLOB:
        raise ValueError("Pinned lifecycle dependency is unavailable")
    _verify_current_runtime_bytes()
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "image_slots": 0}


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
    return _exec_frozen_module("hbq_l2_line_breaks_text_holdout_frozen_v1", SOURCE_ROOT / "study.py", _git_bytes("show", f"{SOURCE_COMMIT}:{SOURCE_PATH}/study.py"))


@lru_cache(maxsize=1)
def _lifecycle() -> ModuleType:
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    module = _exec_frozen_module("hbq_l2_text_holdout_lifecycle_frozen_v2", REPOSITORY / LIFECYCLE_PATH, _git_bytes("show", f"{SOURCE_COMMIT}:{LIFECYCLE_PATH}"))
    module.STUDY_ID, module.SLOTS, module.MAX_SENDS = STUDY_ID, SLOTS, MAX_SENDS
    module.VERDICTS, module.NORMALIZATION_POLICY = VERDICTS, NORMALIZATION_POLICY
    module.RUNTIME_PATHS, module.PINNED_RUNTIME_HASHES = tuple(RUNTIME_BLOBS), RUNTIME_BLOBS
    module.validate_package, module._verify_current_runtime_bytes, module._runtime_bindings = validate_package, _verify_current_runtime_bytes, _runtime_bindings
    module.build_schedule, module.prepare, module.dry_run = build_schedule, prepare, dry_run
    module._validated_schedule, module._aggregate_test_only = _validated_schedule, _aggregate_test_only
    module._validate_response, module._production_runner = _validate_response, _production_runner
    return module


def _canonical_prompt_bytes(value: bytes) -> bytes:
    if b"\r" in value.replace(b"\r\n", b""):
        raise ValueError("Prompt contains a lone CR byte")
    return value.replace(b"\r\n", b"\n")


def _run_id(slot_id: str, logical_id: str) -> str:
    return "l2textexec-v1-" + slot_id + "-" + sha256_bytes(logical_id.encode("utf-8"))[:20]


@lru_cache(maxsize=1)
def _schedule_template() -> tuple[bytes, ...]:
    source = _source()
    artifacts = source.materialize_artifacts(source.load_corpus())
    compiled = source.compiled_leaf_records()
    if {leaf_id: sha256_bytes(source.canonical_bytes(compiled[leaf_id])) for leaf_id in (LINE_BREAKS, NECESSITY)} != COMPILED_LEAF_HASHES:
        raise ValueError("Pinned compiled leaf provenance drifted")
    questions = {leaf_id: source.deepcopy(compiled[leaf_id]) for leaf_id in (LINE_BREAKS, NECESSITY)}
    questions[LINE_BREAKS]["question"]["text"] = source.CANDIDATE_TEXT
    restored = source.deepcopy(questions[LINE_BREAKS])
    restored["question"]["text"] = compiled[LINE_BREAKS]["question"]["text"]
    if restored != compiled[LINE_BREAKS] or questions[NECESSITY] != compiled[NECESSITY]:
        raise ValueError("Candidate-only question override drifted")
    rows: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        artifact = artifacts[case_id]
        for leaf_id in (LINE_BREAKS, NECESSITY):
            question = questions[leaf_id]
            prompt = source.production_runner._render_prompt(binary_prompt=source.binary_prompt(), artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[question], task_contract_context=source.task_context_for(artifact))
            for forbidden in (case_id, "expected_verdict", "expected-ledger", "text-holdout", "YES/YES", "NO/NO", "NOT_APPLICABLE/NO", "YES/NO", "holdout"):
                if forbidden in prompt:
                    raise ValueError("Provider-facing prompt leaked frozen metadata")
            prompt_bytes = _canonical_prompt_bytes(prompt.encode("utf-8"))
            artifact_id = "l2text-artifact-" + sha256_bytes(case_id.encode("utf-8"))[:16]
            artifact_sha256 = sha256_bytes(b"text\x00" + str(artifact["text"]).encode("utf-8"))
            for repeat in range(1, 4):
                slot_id = f"l2textexec-v1-{len(rows) + 1:03d}"
                condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "attempt_lifecycle_policy": "terminal_sidecar_v1", "leaf_id": leaf_id, "prompt_sha256": sha256_bytes(prompt_bytes), "rubric_sha256": sha256_bytes(_git_bytes("show", f"{SOURCE_COMMIT}:registry/all_modules.json"))}
                from hbqrs.study_identity import logical_sample_id
                logical_id = logical_sample_id(study_id=STUDY_ID, artifact_id=artifact_id, artifact_sha256=artifact_sha256, condition=condition, repetition=repeat, rubric_revision="1.2.0")
                rows.append({"slot_id": slot_id, "case_id": case_id, "artifact_id": artifact_id, "artifact_name": artifact["artifact_name"], "artifact_kind": artifact["artifact_type"], "artifact_text": artifact["text"], "artifact_sha256": artifact_sha256, "bundle_id": artifact["bundle_id"], "leaf_id": leaf_id, "repeat": repeat, "completion_status": artifact["completion_status"], "prompt": prompt_bytes.decode("utf-8"), "prompt_sha256": sha256_bytes(prompt_bytes), "image_input": None, "condition": condition, "logical_sample_id": logical_id, "run_id": _run_id(slot_id, logical_id)})
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS or len({row["logical_sample_id"] for row in rows}) != SLOTS or len({row["run_id"] for row in rows}) != SLOTS or len({(row["case_id"], row["leaf_id"]) for row in rows}) != 8 or any(row["image_input"] is not None for row in rows):
        raise ValueError("Text-only singleton schedule geometry drifted")
    return tuple(canonical_json(row) for row in rows)


def build_schedule() -> list[dict[str, Any]]:
    return [json.loads(value.decode("utf-8")) for value in _schedule_template()]


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("slot_id", "case_id", "artifact_id", "artifact_name", "artifact_kind", "artifact_sha256", "bundle_id", "leaf_id", "repeat", "completion_status", "prompt_sha256", "image_input", "condition", "logical_sample_id", "run_id")
    return {key: slot[key] for key in keys}


def _prepare(private_root: str | Path) -> dict[str, Any]:
    base, root, schedule = _lifecycle(), _lifecycle()._external_root(private_root), build_schedule()
    base._write_or_verify(base._frozen_schema_path(root), _git_bytes("show", f"{SOURCE_COMMIT}:schema/hbq_judge_response.schema.json"))
    for slot in schedule:
        base._write_or_verify(base._input_path(root, slot), str(slot["artifact_text"]).encode("utf-8"))
        base._write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", _canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    base._write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0, "text_input_slots": SLOTS, "image_slots": 0}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validate_package()
    return _prepare(private_root)


def _validated_schedule(private_root: str | Path) -> list[dict[str, Any]]:
    base, root, schedule = _lifecycle(), _lifecycle()._external_root(private_root), build_schedule()
    validate_package()
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    if _load_json(root / "study-manifest.json") != manifest:
        raise ValueError("Prepared manifest or runtime binding drifted; dry-run again")
    expected_runtime = {"format_version": 1, "study_id": STUDY_ID, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": sha256_bytes(canonical_json({str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}))}
    if _load_json(root / "runtime-schedule.json") != expected_runtime:
        raise ValueError("Prepared runtime schedule drifted; dry-run again")
    authentication = _load_json(root / "receipts" / "subscription-authentication.v1.json")
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != base._disclosure(schedule, root, codex_binary=str(authentication["binary_path"])):
        raise ValueError("Exact text-only preexecution disclosure is unavailable or drifted")
    return schedule


def dry_run(private_root: str | Path, *, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    base, root = _lifecycle(), _lifecycle()._external_root(private_root)
    validate_package()
    environment = base._minimal_environment()
    authentication = base.subscription_authentication(runner_call=auth_call, environment=environment)
    prepared, schedule = _prepare(root), build_schedule()
    for slot in schedule:
        if slot["image_input"] is not None or "--image" in base.command_for(slot, root, codex_binary=authentication["binary_path"]):
            raise ValueError("Text-only execution may not attach images")
        if (root / "rendered-prompts" / f"{slot['slot_id']}.txt").read_bytes() != _canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")):
            raise ValueError("Frozen prompt bytes drifted")
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}))
    runtime = {"format_version": 1, "study_id": STUDY_ID, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": aggregate}
    base._write_or_verify(root / "runtime-schedule.json", canonical_json(runtime))
    base._write_or_verify(root / "receipts" / "subscription-authentication.v1.json", canonical_json(authentication))
    base._write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(base._disclosure(schedule, root, codex_binary=authentication["binary_path"])))
    report = {"mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS, "text_input_slots": SLOTS, "image_slots": 0, "first_command": base.command_for(schedule[0], root, codex_binary=authentication["binary_path"]), "last_command": base.command_for(schedule[-1], root, codex_binary=authentication["binary_path"]), "rendered_prompt_aggregate_sha256": aggregate}
    base._write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", canonical_json(report))
    return {**prepared, **report}


def _production_runner() -> Any:
    _verify_current_runtime_bytes()
    from hbqrs import runner
    if runner.EVIDENCE_NORMALIZATION_POLICY != NORMALIZATION_POLICY:
        raise ValueError("Imported production normalization policy drifted")
    return runner


def _validate_response(slot: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    audit: list[dict[str, Any]] = []
    try:
        normalized = _production_runner()._normalize_batch(payload, expected_ids=[str(slot["leaf_id"])], artifact_id=str(slot["artifact_id"]), bundle_id=str(slot["bundle_id"]), judge_id="codex:gpt-5.6-sol", run_id=str(slot["run_id"]), artifact_text=str(slot["artifact_text"]), context_texts=[], normalization_policy=NORMALIZATION_POLICY, repair_audit=audit)
    except Exception as exc:
        raise ValueError("Response violates canonical production normalization: " + str(exc)) from exc
    if len(normalized) != 1 or normalized[0].get("question_id") != slot["leaf_id"] or normalized[0].get("verdict") not in VERDICTS:
        raise ValueError("Frozen singleton response identity drifted")
    return {"verdict": normalized[0], "normalization_audit": audit}


def execute(private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    return _lifecycle().execute(private_root, allow_remote=allow_remote, acknowledged_zero_incremental_charge=acknowledged_zero_incremental_charge, runner_call=runner_call, auth_call=auth_call)


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, codex_binary: str | None = None) -> list[str]:
    return _lifecycle().command_for(slot, private_root, codex_binary=codex_binary)


def _aggregate_test_only(*, schedule: list[dict[str, Any]], records: list[Mapping[str, Any]], scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(records) != SLOTS or len({str(record.get("slot_id")) for record in records}) != SLOTS:
        raise ValueError("Settlement requires every unique singleton record")
    by_slot = {str(record["slot_id"]): record for record in records}
    matches: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for slot in schedule:
        record = by_slot.get(str(slot["slot_id"]))
        if record is None or record.get("logical_sample_id") != slot["logical_sample_id"] or record.get("run_id") != slot["run_id"] or record.get("verdict") not in VERDICTS:
            raise ValueError("Settlement record has malformed singleton identity")
        correct = scorer(slot, record)
        if type(correct) is not bool:
            raise ValueError("External scorer must return a boolean only")
        matches[(str(slot["case_id"]), str(slot["leaf_id"]))].append(correct)
    if len(matches) != 8 or any(len(values) != 3 for values in matches.values()):
        raise ValueError("Settlement requires eight complete cells")
    totals = Counter(sum(values) for values in matches.values())
    groups = {"candidate": [], "control": []}
    for (_, leaf_id), values in matches.items():
        groups["candidate" if leaf_id == LINE_BREAKS else "control"].append(sum(values))
    if len(groups["candidate"]) != 4 or len(groups["control"]) != 4:
        raise ValueError("Candidate/control partition drifted")
    aggregate_cells = {"zero_of_three": totals[0], "one_of_three": totals[1], "two_of_three": totals[2], "three_of_three": totals[3], "total": 8}
    cell_groups = {name: {"three_of_three": values.count(3), "below_three_of_three": len(values) - values.count(3)} for name, values in groups.items()}
    decision = "HOLDOUT_ELIGIBLE_ON_SUCCESS" if totals[3] == 8 else "NO_GO"
    normalization_events = sum(len(record.get("normalization_audit", [])) for record in by_slot.values())
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "aggregate_cells": aggregate_cells, "target_control_cells": cell_groups, "normalization_events": normalization_events, "text_input_slots": SLOTS, "image_slots": 0, "expected_ledger_opened_by_executor": False, "publication_requires": "settlement-publication.v1.json", "promotion": "none"}
    public = {key: value for key, value in settlement.items() if key not in {"format_version", "expected_ledger_opened_by_executor"}}
    return settlement, public


def settle(private_root: str | Path, *, scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None) -> dict[str, Any]:
    if scorer is None:
        raise ValueError("Settlement requires an external expected-ledger boolean scorer")
    return _lifecycle().settle(private_root, scorer=scorer)
