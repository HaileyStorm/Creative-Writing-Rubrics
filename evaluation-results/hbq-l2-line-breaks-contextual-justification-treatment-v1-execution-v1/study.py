"""One-shot executor for the frozen contextual-justification L2 treatment."""
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
STUDY_ID = "hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1"
SOURCE_COMMIT = "9fe172f2887a06a33638bca1965ebdeb40bf30a8"
SOURCE_TREE = "e5c5af45967bb7a8de14fee1c359d329cb7c6174"
SOURCE_PATH = "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v1"
SOURCE_ROOT = ROOT.parent / "hbq-l2-line-breaks-contextual-justification-treatment-v1"
LIFECYCLE_COMMIT = "1290b6e7a244fc9388003240959e21504ca8cbf5"
LIFECYCLE_PATH = "evaluation-results/hbq-l2-construct-microgate-v2-execution-v2/study.py"
LIFECYCLE_BLOB = "0ea7a50d9c5c1ee1e1a4c54761605d8fd89c51fc"
SLOTS = MAX_SENDS = 18
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
NORMALIZATION_POLICY = "invalid_exact_quote_to_summary_v1"
SOURCE_FILES = {
    "README.md": "cc60e1cd8ddc6566b14780a4b9b63cf6ad3c1456",
    "expected-ledger.json": "7cf4d54756efc36b79acf384f54ced13798b35df",
    "public-synthetic-corpus.json": "a5d7c471647659782052b1b902986ba95d32226c",
    "run.py": "74f185c97a33c1784785fbbf54623f4f732ff613",
    "study-contract.json": "bd50fc5bf9182d8378b8219e2db6018c90b94951",
    "study.py": "c533aac56da06ff3a94d49350616bcf797e88227",
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
COMPILED_LEAF_HASH = "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c"
PAIR_PROMPT_HASHES = {
    "t01": {"canonical": "87c969674debbd5e36a6f2ecebeb2340154477333da5fe510390352a979f9c46", "candidate": "c307cfbb2f2ce2be13b9cea5f81b378a2132e34518e979471d2369005b234336"},
    "t02": {"canonical": "66806b03680ba61efea8e39a453717fba40a712a9871963fff321a06e9ca3a54", "candidate": "0295136688010ab167b1ce2825c5c46c2d3e871c1b0236b77db5793f93360f19"},
    "t03": {"canonical": "2badad74e6a0d313999236758ff3e695c4997503de59ab941d55cfd0b20a6fd2", "candidate": "17c328115c6361e291f7ff49a0c0c5bc5f489d68d2d57b64b94a18d623d5b76b"},
    "t04": {"canonical": "e3a5b73ff3977ab8b5756f1b27a6fa00dc730ea94cb1ff268572606115962e71", "candidate": "729f2f9f0d49bf8afdcb35777f38dbcad6ea77bd0b1b44e3872b5b92598b7981"},
    "t05": {"canonical": "7964f4a3e7e60f4633038537bf4a31ef80f731dc2783144c2e4ef7d9cc5dab6a", "candidate": "456e4ca7bda80f00169158c129add0785493bc4bf53492a9844a32aa41d5cc7d"},
    "t06": {"canonical": "46aa5411046f81d0160f8fc57859e4e4f3ba42f77a7bb9cab88e2dea7b40c027", "candidate": "5d6378d9c2fce2459a56f37a7a24733d83250ac1725790072479f1c36aae5153"},
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
        raise ValueError(result.stderr.strip() or "Git binding lookup failed")
    return result.stdout.strip()


def _git_bytes(*args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "Git blob lookup failed")
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
        if _git("rev-parse", f"{commit}:{relative_root}/{name}") != blob or _git("hash-object", str(root / name)) != blob:
            raise ValueError(f"{label} differs from pinned bytes: {name}")


def _runtime_bindings() -> dict[str, str]:
    return {path: _git("rev-parse", f"{SOURCE_COMMIT}:{path}") for path in RUNTIME_BLOBS}


def _verify_current_runtime_bytes() -> None:
    if _runtime_bindings() != RUNTIME_BLOBS:
        raise ValueError("Pinned runtime Git blob provenance drifted")
    if any(_git("hash-object", path) != blob for path, blob in RUNTIME_BLOBS.items()):
        raise ValueError("Current runtime differs from pinned source bytes")


def validate_package() -> dict[str, Any]:
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "status": "frozen_unexecuted_treatment_only",
        "source": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "path": SOURCE_PATH, "files": SOURCE_FILES},
        "lifecycle_dependency": {"commit": LIFECYCLE_COMMIT, "path": LIFECYCLE_PATH, "blob": LIFECYCLE_BLOB},
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "sequence": "strict", "one_leaf_per_call": True, "slots": SLOTS, "one_physical_attempt_per_slot": True, "retry_or_resume": "forbidden", "canonical_quote_normalization": NORMALIZATION_POLICY, "paid_route": "forbidden"},
        "delivery": {"text_only": True, "baseline_slots": 0, "necessity_slots": 0, "image_slots": 0, "attachments": "forbidden"},
        "privacy": {"expected_ledger_read_by_executor": False, "external_boolean_scorer_required": True, "publication": "aggregate_only"},
        "gating": {"all_six_cells_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY", "invalid_or_incomplete": "no_result"},
        "pair_prompt_hashes": PAIR_PROMPT_HASHES, "compiled_leaf_hash": COMPILED_LEAF_HASH, "runtime": RUNTIME_BLOBS, "promotion": "none", "dspy": "not_implemented",
    }
    if contract() != expected:
        raise ValueError("Execution contract drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{SOURCE_PATH}") != SOURCE_TREE:
        raise ValueError("Pinned treatment source tree is unavailable")
    _verify_files(SOURCE_COMMIT, SOURCE_ROOT, SOURCE_PATH, SOURCE_FILES, "Frozen treatment source")
    if _git("rev-parse", f"{LIFECYCLE_COMMIT}:{LIFECYCLE_PATH}") != LIFECYCLE_BLOB:
        raise ValueError("Pinned lifecycle dependency is unavailable")
    _verify_current_runtime_bytes()
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "image_slots": 0}


def _exec_frozen_module(name: str, path: Path, source: bytes) -> ModuleType:
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


@lru_cache(maxsize=1)
def _source() -> ModuleType:
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    return _exec_frozen_module("hbq_l2_contextual_treatment_frozen_v1", SOURCE_ROOT / "study.py", _git_bytes("show", f"{SOURCE_COMMIT}:{SOURCE_PATH}/study.py"))


@lru_cache(maxsize=1)
def _lifecycle() -> ModuleType:
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    module = _exec_frozen_module("hbq_l2_contextual_treatment_lifecycle", REPOSITORY / LIFECYCLE_PATH, _git_bytes("show", f"{LIFECYCLE_COMMIT}:{LIFECYCLE_PATH}"))
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


@lru_cache(maxsize=1)
def _schedule_template() -> tuple[bytes, ...]:
    source = _source()
    pairs = source.render_pairs()
    observed = {case_id: {variant: sha256_bytes(prompt.encode("utf-8")) for variant, prompt in pair.items()} for case_id, pair in pairs.items()}
    if observed != PAIR_PROMPT_HASHES:
        raise ValueError("Frozen pair-render hashes drifted")
    artifacts = source.materialize_artifacts()
    compiled = source.compiled_leaf_records()[LINE_BREAKS]
    if sha256_bytes(source.canonical_bytes(compiled)) != COMPILED_LEAF_HASH:
        raise ValueError("Frozen compiled line-break leaf drifted")
    question = source.treatment_question()
    restored = source.deepcopy(question)
    restored["question"]["text"] = compiled["question"]["text"]
    if restored != compiled:
        raise ValueError("Candidate changed more than the line-break question text")
    rows: list[dict[str, Any]] = []
    for case_id in source.CASE_IDS:
        artifact = artifacts[case_id]
        prompt = pairs[case_id]["candidate"]
        for forbidden in ("expected-ledger", "ledger", "canonical", "baseline", "treatment", "holdout", "necessity"):
            if forbidden in prompt.casefold():
                raise ValueError("Provider-facing prompt leaked local metadata")
        artifact_id = "l2context-artifact-" + sha256_bytes(case_id.encode("utf-8"))[:16]
        artifact_sha256 = sha256_bytes(b"text\x00" + str(artifact["text"]).encode("utf-8"))
        prompt_bytes = _canonical_prompt_bytes(prompt.encode("utf-8"))
        for repeat in range(1, 4):
            slot_id = f"l2contextexec-v1-{len(rows) + 1:03d}"
            condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "attempt_lifecycle_policy": "terminal_sidecar_v1", "leaf_id": LINE_BREAKS, "prompt_sha256": sha256_bytes(prompt_bytes), "rubric_sha256": sha256_bytes(_git_bytes("show", f"{SOURCE_COMMIT}:registry/all_modules.json"))}
            from hbqrs.study_identity import logical_sample_id
            logical_id = logical_sample_id(study_id=STUDY_ID, artifact_id=artifact_id, artifact_sha256=artifact_sha256, condition=condition, repetition=repeat, rubric_revision="1.2.0")
            rows.append({"slot_id": slot_id, "case_id": case_id, "artifact_id": artifact_id, "artifact_name": artifact["artifact_name"], "artifact_kind": artifact["artifact_type"], "artifact_text": artifact["text"], "artifact_sha256": artifact_sha256, "bundle_id": artifact["bundle_id"], "leaf_id": LINE_BREAKS, "repeat": repeat, "completion_status": artifact["completion_status"], "prompt": prompt_bytes.decode("utf-8"), "prompt_sha256": sha256_bytes(prompt_bytes), "image_input": None, "condition": condition, "logical_sample_id": logical_id, "run_id": "l2contextexec-v1-" + slot_id + "-" + sha256_bytes(logical_id.encode("utf-8"))[:20]})
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS or len({row["logical_sample_id"] for row in rows}) != SLOTS or any(row["leaf_id"] != LINE_BREAKS or row["image_input"] is not None for row in rows):
        raise ValueError("Treatment-only schedule geometry drifted")
    return tuple(canonical_json(row) for row in rows)


def build_schedule() -> list[dict[str, Any]]:
    return [json.loads(value.decode("utf-8")) for value in _schedule_template()]


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "case_id", "artifact_id", "artifact_name", "artifact_kind", "artifact_sha256", "bundle_id", "leaf_id", "repeat", "completion_status", "prompt_sha256", "image_input", "condition", "logical_sample_id", "run_id")}


def _prepare(private_root: str | Path) -> dict[str, Any]:
    base, root, schedule = _lifecycle(), _lifecycle()._external_root(private_root), build_schedule()
    base._write_or_verify(base._frozen_schema_path(root), _git_bytes("show", f"{SOURCE_COMMIT}:schema/hbq_judge_response.schema.json"))
    for slot in schedule:
        base._write_or_verify(base._input_path(root, slot), str(slot["artifact_text"]).encode("utf-8"))
        base._write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", _canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "pair_prompt_hashes": PAIR_PROMPT_HASHES, "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    base._write_or_verify(root / "study-manifest.json", canonical_json(manifest))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0, "text_input_slots": SLOTS, "image_slots": 0}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validate_package()
    return _prepare(private_root)


def _validated_schedule(private_root: str | Path) -> list[dict[str, Any]]:
    validate_package()
    base, root, schedule = _lifecycle(), _lifecycle()._external_root(private_root), build_schedule()
    manifest = {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "pair_prompt_hashes": PAIR_PROMPT_HASHES, "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}
    if _load_json(root / "study-manifest.json") != manifest:
        raise ValueError("Prepared manifest or binding drifted; dry-run again")
    expected_runtime = {"format_version": 1, "study_id": STUDY_ID, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": sha256_bytes(canonical_json({str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}))}
    if _load_json(root / "runtime-schedule.json") != expected_runtime:
        raise ValueError("Prepared runtime schedule drifted; dry-run again")
    authentication = _load_json(root / "receipts" / "subscription-authentication.v1.json")
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != base._disclosure(schedule, root, codex_binary=str(authentication["binary_path"])):
        raise ValueError("Preexecution disclosure is unavailable or drifted")
    return schedule


def dry_run(private_root: str | Path, *, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    base, root = _lifecycle(), _lifecycle()._external_root(private_root)
    validate_package()
    environment = base._minimal_environment()
    authentication = base.subscription_authentication(runner_call=auth_call, environment=environment)
    prepared, schedule = _prepare(root), build_schedule()
    for slot in schedule:
        if slot["image_input"] is not None or "--image" in base.command_for(slot, root, codex_binary=authentication["binary_path"]):
            raise ValueError("Treatment-only execution may not attach images")
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}))
    runtime = {"format_version": 1, "study_id": STUDY_ID, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": aggregate}
    base._write_or_verify(root / "runtime-schedule.json", canonical_json(runtime))
    base._write_or_verify(root / "receipts" / "subscription-authentication.v1.json", canonical_json(authentication))
    base._write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", canonical_json(base._disclosure(schedule, root, codex_binary=authentication["binary_path"])))
    report = {"mode": "dry_run", "provider_calls": 0, "planned_slots": SLOTS, "text_input_slots": SLOTS, "image_slots": 0, "rendered_prompt_aggregate_sha256": aggregate}
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
    if len(normalized) != 1 or normalized[0].get("question_id") != LINE_BREAKS or normalized[0].get("verdict") not in VERDICTS:
        raise ValueError("Frozen singleton response identity drifted")
    return {"verdict": normalized[0], "normalization_audit": audit}


def execute(private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    return _lifecycle().execute(private_root, allow_remote=allow_remote, acknowledged_zero_incremental_charge=acknowledged_zero_incremental_charge, runner_call=runner_call, auth_call=auth_call)


def _aggregate_test_only(*, schedule: list[dict[str, Any]], records: list[Mapping[str, Any]], scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(records) != SLOTS or len({str(record.get("slot_id")) for record in records}) != SLOTS:
        raise ValueError("Settlement requires every unique singleton record")
    matches: dict[str, list[bool]] = defaultdict(list)
    for slot in schedule:
        record = {str(item["slot_id"]): item for item in records}.get(str(slot["slot_id"]))
        if record is None or record.get("logical_sample_id") != slot["logical_sample_id"] or record.get("run_id") != slot["run_id"] or record.get("verdict") not in VERDICTS:
            raise ValueError("Settlement record has malformed singleton identity")
        correct = scorer(slot, record)
        if type(correct) is not bool:
            raise ValueError("External scorer must return a boolean only")
        matches[str(slot["case_id"])].append(correct)
    if set(matches) != {row["case_id"] for row in schedule} or any(len(values) != 3 for values in matches.values()):
        raise ValueError("Settlement requires six complete treatment cells")
    totals = Counter(sum(values) for values in matches.values())
    decision = "HOLDOUT_ELIGIBLE_ON_SUCCESS" if totals[3] == 6 else "NO_GO_DSPY_ELIGIBLE_ONLY"
    aggregate_cells = {"zero_of_three": totals[0], "one_of_three": totals[1], "two_of_three": totals[2], "three_of_three": totals[3], "total": 6}
    normalization_events = sum(len(record.get("normalization_audit", [])) for record in records)
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "aggregate_cells": aggregate_cells, "normalization_events": normalization_events, "text_input_slots": SLOTS, "image_slots": 0, "expected_ledger_opened_by_executor": False, "publication_requires": "settlement-publication.v1.json", "promotion": "none", "dspy": "not_implemented"}
    public = {key: value for key, value in settlement.items() if key not in {"format_version", "expected_ledger_opened_by_executor"}}
    return settlement, public


def settle(private_root: str | Path, *, scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None) -> dict[str, Any]:
    if scorer is None:
        raise ValueError("Settlement requires an external expected-ledger boolean scorer")
    return _lifecycle().settle(private_root, scorer=scorer)
