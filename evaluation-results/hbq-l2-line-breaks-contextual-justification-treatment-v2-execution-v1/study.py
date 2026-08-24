"""One-shot executor for the frozen material-context line-break treatment."""
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
STUDY_ID = "hbq-l2-line-breaks-contextual-justification-treatment-v2-execution-v1"
SOURCE_COMMIT = "fd96e808d1bf29f968a1fa2c532e41a84fb8fd3e"
SOURCE_TREE = "f685190cb734f7a5738b2f5a93c6b0aa8c60fe82"
SOURCE_PATH = "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v2"
SOURCE_ROOT = ROOT.parent / "hbq-l2-line-breaks-contextual-justification-treatment-v2"
LIFECYCLE_COMMIT = "9c09ac4315ffa270a43e9b8a1f636b2cb5f31095"
LIFECYCLE_PATH = "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1/study.py"
LIFECYCLE_BLOB = "91ae447481498f5db3a2aee73d6d315ca2195ae5"
SLOTS = MAX_SENDS = 18
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
NECESSITY = "form.poetry.free_verse.necessity"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
NORMALIZATION_POLICY = "invalid_exact_quote_to_summary_v1"
SOURCE_FILES = {
    "README.md": "de287427ce1208462856d9154603d34fdf365e0a",
    "expected-ledger.json": "95eb5e7b36582574401107dca60ff3c9de32cc73",
    "public-synthetic-corpus.json": "c3e4b879aa70e11399a728c64dcca326ec23e0d5",
    "run.py": "d062c37fa2b81aab20a87d7c977eb37421c08375",
    "study-contract.json": "c2cc5dafa54559a92e6f27ab47fae312a66df35e",
    "study.py": "8a6f84e904667bc720842019edf906f75e6d7968",
}
PARENT_RESULT = {"commit": "47a7dea714111496a22dd484eae05b6428c2a0ed", "tree": "0c6f073390ccb202666bd1df53969fd28a16167b", "path": "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1-public-result-v1", "files": {"README.md": "be8f966dbbf8e7ff1f0f0baf167421b6f9dabe96", "public-result.json": "4ce3ec6845302d6ac994884a7727b783ee7220db"}}
RUNTIME_BLOBS = {
    "src/hbqrs/runner.py": "cc244ad40924c2a11c044268ca89af0fc1ba5f65", "src/hbqrs/study_identity.py": "a61aec19ac9be33fe8d8a45da4db5d74ba3a96ea",
    "prompts/judge/JUDGE_PREFIX.md": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e", "prompts/judge/BINARY_EVALUATION_PROMPT.md": "d2662edfccc115c6d0c4d97af82a10c9e926b853",
    "schema/hbq_judge_response.schema.json": "1034a35dcd6c30a75101f369627d60e155d65c2c", "registry/all_modules.json": "d94af34c80cf32b4d5a380167e66e2af39f29ad7",
    "bundles/all_bundles.jsonl": "718a935081abbf2d1949ceacfb9e5a45e81b85eb", "registry/criterion_ownership.json": "685846945ddd562992b313b17e8efa72692b8036",
    "registry/question_index.jsonl": "4ab3b7e11fe2e150cc0defafc22a29929cf5799c",
}
COMPILED_LEAF_HASHES = {LINE_BREAKS: "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c", NECESSITY: "a8c36e24125ba32db2694051252a5c17e9fc05abe48cd185f014b7b2a704e0eb"}
PAIR_PROMPT_HASHES = {
    "t01": {"canonical": "ea9a2596cfe22178420f80c8d09a0f76d01f5115c52cba77e9b672df035b6498", "candidate": "771de618a0e39108b39be29281eb21642b7c1545d8ca9ff07e414d06dd9e5c15"},
    "t02": {"canonical": "bcd024015c808fac5596268ab897a284ce9ad6c76926351f652ab93f0884e3a8", "candidate": "1bba5a2b123157f7583ce8233dcf9b94cc188c14eb7200602b7fa60dea10ff09"},
    "t03": {"canonical": "0e5448131c34394cc46fcedd5e322f2d3845ca5c1377e57ff54113e889b0fd5e", "candidate": "aad8ab02e855f0d5c44523f82387b1a9da3029360a3d4787eb980e9452e9e331"},
    "t04": {"canonical": "7201ea12d99856e4a7b58cab7a339d5b626b3a9ccac7f421f1cb7a1f539fea85", "candidate": "9986336253a32c70f0320bbccff15009f49f96fa432fe253da883d7916aca597"},
    "t05": {"canonical": "35f0c86f345aefa9ee7ea2ff14e68292ebac1d6088a72c8d08865ec816c93c4f", "candidate": "8e1228204cf9c3ba40e9f5fa6ca371b1e1b82523177e546ea692b9fd8ddf4c7b"},
    "t06": {"canonical": "fa9fdf3b3ff742860b34e39ebc63fc01203797f716dee66babc96f57af334e0b", "candidate": "f94116706e5cc0024d09a9315e68ff93dac858ae720349239ce76b06d3f00bd9"},
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
        "lifecycle": {"commit": LIFECYCLE_COMMIT, "path": LIFECYCLE_PATH, "blob": LIFECYCLE_BLOB, "validated_schedule_before_contact": True}, "parent_result": PARENT_RESULT,
        "geometry": {"slots": SLOTS, "cells": 6, "repeats": 3, "leaf_id": LINE_BREAKS, "baseline_slots": 0, "necessity_slots": 0, "image_slots": 0},
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "sequence": "strict", "one_leaf_per_call": True, "one_physical_attempt_per_slot": True, "retry_or_resume": "forbidden", "canonical_quote_normalization": NORMALIZATION_POLICY, "paid_route": "forbidden"},
        "privacy": {"expected_ledger_read_by_executor": False, "external_boolean_scorer_required": True, "publication": "aggregate_only"},
        "gating": {"all_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY", "invalid_or_incomplete": "no_result"},
        "pair_prompt_hashes": PAIR_PROMPT_HASHES, "compiled_leaf_hashes": COMPILED_LEAF_HASHES, "runtime": RUNTIME_BLOBS, "promotion": "none", "dspy": "not_implemented",
    }
    if contract() != expected:
        raise ValueError("Execution contract drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{SOURCE_PATH}") != SOURCE_TREE:
        raise ValueError("Pinned treatment source tree is unavailable")
    _verify_files(SOURCE_COMMIT, SOURCE_ROOT, SOURCE_PATH, SOURCE_FILES, "Frozen treatment source")
    if _git("rev-parse", f"{LIFECYCLE_COMMIT}:{LIFECYCLE_PATH}") != LIFECYCLE_BLOB:
        raise ValueError("Pinned lifecycle dependency is unavailable")
    if _git("rev-parse", f"{PARENT_RESULT['commit']}^{{tree}}") != PARENT_RESULT["tree"]:
        raise ValueError("Pinned parent result tree is unavailable")
    _verify_files(PARENT_RESULT["commit"], ROOT.parent / Path(PARENT_RESULT["path"]).name, PARENT_RESULT["path"], PARENT_RESULT["files"], "Pinned parent result")
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
    return _exec_frozen_module("hbq_l2_contextual_treatment_v2_source", SOURCE_ROOT / "study.py", _git_bytes("show", f"{SOURCE_COMMIT}:{SOURCE_PATH}/study.py"))


@lru_cache(maxsize=1)
def _lifecycle() -> ModuleType:
    validate_package()
    if str(REPOSITORY / "src") not in sys.path:
        sys.path.insert(0, str(REPOSITORY / "src"))
    module = _exec_frozen_module("hbq_l2_contextual_treatment_v2_frozen_lifecycle", REPOSITORY / LIFECYCLE_PATH, _git_bytes("show", f"{LIFECYCLE_COMMIT}:{LIFECYCLE_PATH}"))
    module.STUDY_ID, module.SLOTS, module.MAX_SENDS = STUDY_ID, SLOTS, MAX_SENDS
    module.VERDICTS, module.NORMALIZATION_POLICY = VERDICTS, NORMALIZATION_POLICY
    module.RUNTIME_PATHS, module.PINNED_RUNTIME_HASHES = tuple(RUNTIME_BLOBS), RUNTIME_BLOBS
    module.validate_package, module._verify_current_runtime_bytes, module._runtime_bindings = validate_package, _verify_current_runtime_bytes, _runtime_bindings
    module.build_schedule, module.prepare, module.dry_run = build_schedule, prepare, dry_run
    module._validated_schedule, module._aggregate_test_only = _validated_schedule, _aggregate_test_only
    module._validate_response, module._production_runner = _validate_response, _production_runner
    return module


def _base_lifecycle() -> ModuleType:
    """Return the cached terminal lifecycle behind the exact frozen adapter."""
    return _lifecycle()._lifecycle()


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
    compiled = source.compiled_leaf_records()
    if {leaf: sha256_bytes(source.canonical_bytes(compiled[leaf])) for leaf in COMPILED_LEAF_HASHES} != COMPILED_LEAF_HASHES:
        raise ValueError("Frozen compiled leaf provenance drifted")
    candidate, canonical = source.candidate_question(), source.canonical_question()
    restored = source.deepcopy(candidate)
    restored["question"]["text"] = canonical["question"]["text"]
    if restored != canonical:
        raise ValueError("Candidate changed more than the line-break question text")
    artifacts = source.materialize_artifacts()
    rows: list[dict[str, Any]] = []
    for case_id in source.CASE_IDS:
        artifact, prompt = artifacts[case_id], pairs[case_id]["candidate"]
        for forbidden in ("expected-ledger", "ledger", "canonical", "baseline", "treatment", "holdout", "necessity"):
            if forbidden in prompt.casefold():
                raise ValueError("Provider-facing prompt leaked local metadata")
        artifact_id = "l2contextv2-artifact-" + sha256_bytes(case_id.encode("utf-8"))[:16]
        artifact_sha256 = sha256_bytes(b"text\x00" + str(artifact["text"]).encode("utf-8"))
        prompt_bytes = _canonical_prompt_bytes(prompt.encode("utf-8"))
        for repeat in range(1, 4):
            slot_id = f"l2contextv2exec-v1-{len(rows) + 1:03d}"
            condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "attempt_lifecycle_policy": "terminal_sidecar_v1", "leaf_id": LINE_BREAKS, "prompt_sha256": sha256_bytes(prompt_bytes), "rubric_sha256": sha256_bytes(_git_bytes("show", f"{SOURCE_COMMIT}:registry/all_modules.json"))}
            from hbqrs.study_identity import logical_sample_id
            logical_id = logical_sample_id(study_id=STUDY_ID, artifact_id=artifact_id, artifact_sha256=artifact_sha256, condition=condition, repetition=repeat, rubric_revision="1.2.0")
            rows.append({"slot_id": slot_id, "case_id": case_id, "artifact_id": artifact_id, "artifact_name": artifact["artifact_name"], "artifact_kind": artifact["artifact_type"], "artifact_text": artifact["text"], "artifact_sha256": artifact_sha256, "bundle_id": artifact["bundle_id"], "leaf_id": LINE_BREAKS, "repeat": repeat, "completion_status": artifact["completion_status"], "prompt": prompt_bytes.decode("utf-8"), "prompt_sha256": sha256_bytes(prompt_bytes), "image_input": None, "condition": condition, "logical_sample_id": logical_id, "run_id": "l2contextv2exec-v1-" + slot_id + "-" + sha256_bytes(logical_id.encode("utf-8"))[:20]})
    if len(rows) != SLOTS or len({row["slot_id"] for row in rows}) != SLOTS or len({row["logical_sample_id"] for row in rows}) != SLOTS or any(row["leaf_id"] != LINE_BREAKS or row["image_input"] is not None for row in rows):
        raise ValueError("Treatment-only schedule geometry drifted")
    return tuple(canonical_json(row) for row in rows)


def build_schedule() -> list[dict[str, Any]]:
    return [json.loads(value.decode("utf-8")) for value in _schedule_template()]


def _public_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in ("slot_id", "case_id", "artifact_id", "artifact_name", "artifact_kind", "artifact_sha256", "bundle_id", "leaf_id", "repeat", "completion_status", "prompt_sha256", "image_input", "condition", "logical_sample_id", "run_id")}


def _manifest(schedule: list[dict[str, Any]]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "contract_sha256": sha256_file(ROOT / "study-contract.json"), "runtime_bindings": _runtime_bindings(), "pair_prompt_hashes": PAIR_PROMPT_HASHES, "planned_slots": SLOTS, "slots": [_public_slot(slot) for slot in schedule]}


def _prepare(private_root: str | Path) -> dict[str, Any]:
    base = _base_lifecycle()
    root, schedule = base._external_root(private_root), build_schedule()
    base._write_or_verify(base._frozen_schema_path(root), _git_bytes("show", f"{SOURCE_COMMIT}:schema/hbq_judge_response.schema.json"))
    for slot in schedule:
        base._write_or_verify(base._input_path(root, slot), str(slot["artifact_text"]).encode("utf-8"))
        base._write_or_verify(root / "rendered-prompts" / f"{slot['slot_id']}.txt", _canonical_prompt_bytes(str(slot["prompt"]).encode("utf-8")))
    base._write_or_verify(root / "study-manifest.json", canonical_json(_manifest(schedule)))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0, "text_input_slots": SLOTS, "image_slots": 0}


def prepare(private_root: str | Path) -> dict[str, Any]:
    validate_package()
    return _prepare(private_root)


def _validated_schedule(private_root: str | Path) -> list[dict[str, Any]]:
    validate_package()
    base = _base_lifecycle()
    root, schedule = base._external_root(private_root), build_schedule()
    if (base._frozen_schema_path(root)).read_bytes() != _git_bytes("show", f"{SOURCE_COMMIT}:schema/hbq_judge_response.schema.json"):
        raise ValueError("Prepared frozen response schema drifted; dry-run again")
    if _load_json(root / "study-manifest.json") != _manifest(schedule):
        raise ValueError("Prepared manifest or binding drifted; dry-run again")
    aggregate = sha256_bytes(canonical_json({str(slot["slot_id"]): str(slot["prompt_sha256"]) for slot in schedule}))
    runtime = {"format_version": 1, "study_id": STUDY_ID, "slots": [_public_slot(slot) for slot in schedule], "rendered_prompt_aggregate_sha256": aggregate}
    if _load_json(root / "runtime-schedule.json") != runtime:
        raise ValueError("Prepared runtime schedule drifted; dry-run again")
    authentication = _load_json(root / "receipts" / "subscription-authentication.v1.json")
    if _load_json(root / "receipts" / "preexecution-disclosure.v1.json") != base._disclosure(schedule, root, codex_binary=str(authentication["binary_path"])):
        raise ValueError("Preexecution disclosure is unavailable or drifted")
    return schedule


def dry_run(private_root: str | Path, *, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    base = _base_lifecycle()
    root = base._external_root(private_root)
    validate_package()
    authentication = base.subscription_authentication(runner_call=auth_call, environment=base._minimal_environment())
    prepared, schedule = _prepare(root), build_schedule()
    for slot in schedule:
        if slot["image_input"] is not None or "--image" in base.command_for(slot, root, codex_binary=authentication["binary_path"]):
            raise ValueError("Treatment-only execution may not attach images")
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
    if len(normalized) != 1 or normalized[0].get("question_id") != LINE_BREAKS or normalized[0].get("verdict") not in VERDICTS:
        raise ValueError("Frozen singleton response identity drifted")
    return {"verdict": normalized[0], "normalization_audit": audit}


def execute(private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = subprocess.run, auth_call: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    return _lifecycle().execute(private_root, allow_remote=allow_remote, acknowledged_zero_incremental_charge=acknowledged_zero_incremental_charge, runner_call=runner_call, auth_call=auth_call)


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, codex_binary: str | None = None) -> list[str]:
    return _base_lifecycle().command_for(slot, private_root, codex_binary=codex_binary)


def _aggregate_test_only(*, schedule: list[dict[str, Any]], records: list[Mapping[str, Any]], scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(records) != SLOTS or len({str(record.get("slot_id")) for record in records}) != SLOTS:
        raise ValueError("Settlement requires every unique singleton record")
    by_slot = {str(record["slot_id"]): record for record in records}
    matches: dict[str, list[bool]] = defaultdict(list)
    verdict_counts: Counter[str] = Counter()
    for slot in schedule:
        record = by_slot.get(str(slot["slot_id"]))
        if record is None or record.get("logical_sample_id") != slot["logical_sample_id"] or record.get("run_id") != slot["run_id"] or record.get("verdict") not in VERDICTS:
            raise ValueError("Settlement record has malformed singleton identity")
        correct = scorer(slot, record)
        if type(correct) is not bool:
            raise ValueError("External scorer must return a boolean only")
        matches[str(slot["case_id"])].append(correct)
        verdict_counts[str(record["verdict"])] += 1
    if set(matches) != {row["case_id"] for row in schedule} or any(len(values) != 3 for values in matches.values()):
        raise ValueError("Settlement requires six complete treatment cells")
    totals = Counter(sum(values) for values in matches.values())
    decision = "HOLDOUT_ELIGIBLE_ON_SUCCESS" if totals[3] == 6 else "NO_GO_DSPY_ELIGIBLE_ONLY"
    aggregate_cells = {"zero_of_three": totals[0], "one_of_three": totals[1], "two_of_three": totals[2], "three_of_three": totals[3], "total": 6}
    normalization_events = sum(len(record.get("normalization_audit", [])) for record in by_slot.values())
    settlement = {"format_version": 1, "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS, "aggregate_cells": aggregate_cells, "verdict_counts": {state: verdict_counts[state] for state in sorted(VERDICTS)}, "normalization_events": normalization_events, "text_input_slots": SLOTS, "image_slots": 0, "expected_ledger_opened_by_executor": False, "publication_requires": "settlement-publication.v1.json", "promotion": "none", "dspy": "not_implemented"}
    public = {key: value for key, value in settlement.items() if key not in {"format_version", "expected_ledger_opened_by_executor", "verdict_counts"}}
    return settlement, public


def settle(private_root: str | Path, *, scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None) -> dict[str, Any]:
    if scorer is None:
        raise ValueError("Settlement requires an external expected-ledger boolean scorer")
    return _lifecycle().settle(private_root, scorer=scorer)
