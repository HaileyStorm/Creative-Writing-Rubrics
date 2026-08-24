"""Provider-free pair renderer for the contextual-justification L2 treatment v2."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs import runner as production_runner

STUDY_ID = "hbq-l2-line-breaks-contextual-justification-treatment-v2"
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
NECESSITY = "form.poetry.free_verse.necessity"
CASE_IDS = ("t01", "t02", "t03", "t04", "t05", "t06")
CANDIDATE_TEXT = "Does each supplied line break materially strengthen its immediate poetic context through rhythm, syntax, emphasis, image, ambiguity, or pace, beyond merely creating a detectable pause, syntactic interruption, or repeated pattern?"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE"))
FREEZE_COMMIT = "9fe172f2887a06a33638bca1965ebdeb40bf30a8"
FREEZE_TREE = "e5c5af45967bb7a8de14fee1c359d329cb7c6174"
PREDECESSOR_EXECUTOR = {"commit": "9c09ac4315ffa270a43e9b8a1f636b2cb5f31095", "tree": "555bdf222374851087ca7ce836cce31d6e8f2234", "path": "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1", "files": {"README.md": "c8b36bb33ce284a267b69299e4328f8a0b07d1c9", "run.py": "7a2c751060d25cb50fe27779be0514109affe170", "study-contract.json": "68b1579063a1a4e2a902cbfea1f2f36fb18a6e6c", "study.py": "91ae447481498f5db3a2aee73d6d315ca2195ae5"}}
SETTLED_PARENT = {"commit": "47a7dea714111496a22dd484eae05b6428c2a0ed", "tree": "0c6f073390ccb202666bd1df53969fd28a16167b", "path": "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1-public-result-v1", "files": {"README.md": "be8f966dbbf8e7ff1f0f0baf167421b6f9dabe96", "public-result.json": "4ce3ec6845302d6ac994884a7727b783ee7220db"}}
RUNTIME_BLOBS = {"src/hbqrs/runner.py": "cc244ad40924c2a11c044268ca89af0fc1ba5f65", "prompts/judge/JUDGE_PREFIX.md": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e", "prompts/judge/BINARY_EVALUATION_PROMPT.md": "d2662edfccc115c6d0c4d97af82a10c9e926b853", "registry/all_modules.json": "d94af34c80cf32b4d5a380167e66e2af39f29ad7", "bundles/all_bundles.jsonl": "718a935081abbf2d1949ceacfb9e5a45e81b85eb", "registry/criterion_ownership.json": "685846945ddd562992b313b17e8efa72692b8036"}
COMPILED_LEAF_HASHES = {LINE_BREAKS: "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c", NECESSITY: "a8c36e24125ba32db2694051252a5c17e9fc05abe48cd185f014b7b2a704e0eb"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def load_ledger() -> dict[str, Any]:
    return load_json(ROOT / "expected-ledger.json")


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.strip() or "Git binding lookup failed")
    return done.stdout.strip()


@lru_cache(maxsize=1)
def compiled_leaf_records() -> dict[str, dict[str, Any]]:
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundle = resolve_bundle(load_bundles(REPOSITORY / "bundles" / "all_bundles.jsonl"), "poetry.free_verse")
    available = {str(item["question"]["id"]): item for item in compiled_questions(compile_bundle(modules, bundle))}
    return {leaf: json.loads(canonical_bytes(available[leaf]).decode("utf-8")) for leaf in COMPILED_LEAF_HASHES}


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in compiled_leaf_records().items()}


def canonical_question() -> dict[str, Any]:
    return deepcopy(compiled_leaf_records()[LINE_BREAKS])


def candidate_question() -> dict[str, Any]:
    value = canonical_question()
    value["question"]["text"] = CANDIDATE_TEXT
    return value


def materialize_artifacts() -> dict[str, dict[str, Any]]:
    return {case["case_id"]: dict(case) for case in load_corpus()["cases"]}


def binary_prompt() -> str:
    return "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_type"], "declared_scope": artifact["declared_scope"], "completion_status": artifact["completion_status"], "background": "Public synthetic construct validation.", "constraints": [{"id": "scope", "statement": "Use only the supplied artifact."}, {"id": "image_input", "statement": "image_input_required=false"}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def rendered_prompt(case_id: str, *, candidate: bool) -> str:
    artifact = materialize_artifacts().get(case_id)
    if artifact is None:
        raise ValueError("Unknown case")
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt(), artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[candidate_question() if candidate else canonical_question()], task_contract_context=task_context_for(artifact))
    for forbidden in ("expected-ledger", "baseline", "candidate", "treatment", "holdout", "necessity", case_id):
        if forbidden in prompt.casefold():
            raise ValueError("Rendered prompt leaked local metadata")
    return prompt


def render_pairs() -> dict[str, dict[str, str]]:
    pairs = {case_id: {"canonical": rendered_prompt(case_id, candidate=False), "candidate": rendered_prompt(case_id, candidate=True)} for case_id in CASE_IDS}
    canonical = canonical_question()["question"]["text"]
    for pair in pairs.values():
        if pair["candidate"].count(CANDIDATE_TEXT) != 1 or pair["candidate"].replace(CANDIDATE_TEXT, canonical, 1) != pair["canonical"]:
            raise ValueError("Candidate changed more than question text")
    return pairs


def pair_prompt_hashes() -> dict[str, dict[str, str]]:
    return {case: {variant: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for variant, prompt in pair.items()} for case, pair in render_pairs().items()}


def plan_treatment_slots() -> list[dict[str, Any]]:
    slots = [{"slot_id": f"l2context-v2-{index:03d}", "case_id": case, "leaf_id": LINE_BREAKS, "repeat": repeat} for index, (case, repeat) in enumerate(((case, repeat) for case in CASE_IDS for repeat in range(1, 4)), start=1)]
    if len(slots) != 18 or len({slot["slot_id"] for slot in slots}) != 18:
        raise ValueError("Treatment slot geometry drifted")
    return slots


def verify_package() -> dict[str, Any]:
    expected = {"format_version": 1, "study_id": STUDY_ID, "status": "frozen_provider_free_contextual_justification_treatment_v2", "development_only": True, "candidate_override": {"leaf_id": LINE_BREAKS, "field": "question.text", "text": CANDIDATE_TEXT, "registry_promotion": "none"}, "pair_screen": {"cases_exact": 6, "renders_exact": 12, "only_delta": "form.poetry.free_verse.line_breaks.question.text"}, "future_treatment_execution": {"permitted_here": False, "leaf_id": LINE_BREAKS, "cells_exact": 6, "repeats_exact": 3, "slots_exact": 18, "all_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY", "invalid_or_incomplete": "no_result"}, "scope": {"baseline": "excluded", "necessity": "excluded_but_bound_unchanged", "images": "forbidden", "remote_contact": "forbidden", "dspy": "forbidden", "promotion": "none"}, "bindings": {"freeze_commit": FREEZE_COMMIT, "freeze_tree": FREEZE_TREE, "predecessor_executor": PREDECESSOR_EXECUTOR, "settled_parent": SETTLED_PARENT, "runtime": RUNTIME_BLOBS, "compiled_source_leaves": COMPILED_LEAF_HASHES, "corpus_sha256": sha256_file(ROOT / "public-synthetic-corpus.json"), "expected_ledger_sha256": sha256_file(ROOT / "expected-ledger.json")}}
    if load_contract() != expected:
        raise ValueError("Treatment contract drifted")
    if _git("rev-parse", f"{FREEZE_COMMIT}:evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v1") != FREEZE_TREE or _git("rev-parse", f"{PREDECESSOR_EXECUTOR['commit']}^{{tree}}") != PREDECESSOR_EXECUTOR["tree"]:
        raise ValueError("Pinned freeze or executor tree drifted")
    for name, blob in PREDECESSOR_EXECUTOR["files"].items():
        if _git("rev-parse", f"{PREDECESSOR_EXECUTOR['commit']}:{PREDECESSOR_EXECUTOR['path']}/{name}") != blob or _git("hash-object", str(REPOSITORY / PREDECESSOR_EXECUTOR["path"] / name)) != blob:
            raise ValueError("Pinned executor bytes drifted")
    if _git("rev-parse", f"{SETTLED_PARENT['commit']}^{{tree}}") != SETTLED_PARENT["tree"]:
        raise ValueError("Settled parent tree drifted")
    for name, blob in SETTLED_PARENT["files"].items():
        if _git("rev-parse", f"{SETTLED_PARENT['commit']}:{SETTLED_PARENT['path']}/{name}") != blob or _git("hash-object", str(REPOSITORY / SETTLED_PARENT["path"] / name)) != blob:
            raise ValueError("Settled parent bytes drifted")
    if {path: _git("rev-parse", f"{FREEZE_COMMIT}:{path}") for path in RUNTIME_BLOBS} != RUNTIME_BLOBS or any(_git("hash-object", path) != blob for path, blob in RUNTIME_BLOBS.items()):
        raise ValueError("Runtime binding drifted")
    if source_leaf_hashes() != COMPILED_LEAF_HASHES or load_ledger()["cells"] != {"t01": "YES", "t02": "NO", "t03": "NOT_APPLICABLE", "t04": "YES", "t05": "YES", "t06": "NO"}:
        raise ValueError("Leaf or protected-state binding drifted")
    return {"study_id": STUDY_ID, "provider_calls": 0, "pair_renders": 12, "future_treatment_slots": 18}


def dry_run_report() -> dict[str, Any]:
    report = verify_package()
    hashes = pair_prompt_hashes()
    return {"mode": "dry_run", "verification": report, "rendered_prompts": 12, "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(hashes)).hexdigest()}
