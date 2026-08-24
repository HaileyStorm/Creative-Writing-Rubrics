"""Provider-free pair renderer for a contextual-justification L2 treatment."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs import runner as production_runner

STUDY_ID = "hbq-l2-line-breaks-contextual-justification-treatment-v1"
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
NECESSITY = "form.poetry.free_verse.necessity"
CASE_IDS = ("t01", "t02", "t03", "t04", "t05", "t06")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE"))
CANDIDATE_TEXT = "Does each supplied line break make a controlled, legible, and contextually justified contribution to rhythm, syntax, emphasis, image, ambiguity, or pace? A detectable pause, syntactic interruption, or repeated pattern alone is not enough; YES evidence must explain what the break contributes in its immediate context."

PUBLIC_RESULT = {
    "commit": "f1dd530d621a2341aeb860e9f091166b6497f075",
    "tree": "b82d40188811c480b61a22b0fc047f448073e4c7",
    "path": "evaluation-results/hbq-l2-line-breaks-text-holdout-v1-execution-v1-public-result-v1",
    "files": {
        "README.md": {"git_blob": "1060b37e13eec3e1769b4d252c495e23495b3adc", "sha256": "65525b2d6f73dafff3e7c1ddc91196a58b96e45ccc97853370f8ce4c39b94758"},
        "public-result.json": {"git_blob": "a7baf7e3f7f9c9d7daa14dadb496868f34498c28", "sha256": "4126e5e113d57a415565eae99e34cc1c48e7644d11f88e05a04afcc23fda43ab"},
    },
}
EXECUTOR = {
    "commit": "b7a3f8e569f09f98e8f40cf6759cd7c6c4e8d0df",
    "tree": "a0122260b684952061cf34a58f12e781df58e81a",
    "path": "evaluation-results/hbq-l2-line-breaks-text-holdout-v1-execution-v1",
    "files": {
        "README.md": {"git_blob": "36029ce8db4d915add1dfb3a48f972e5e28c6820", "sha256": "273df2ca3ca03abdb7fc003ec4f02dce75e0cd2ad64a88662438a7491cc09826"},
        "run.py": {"git_blob": "4fe292922cfb68c2b98b29901ee697797f5cca1e", "sha256": "341f22922cb1db299d869ff453dbc7684be59f4a0e928d7c7bc72bc59063d88b"},
        "study-contract.json": {"git_blob": "facefe22f2e6f10e5e94f1c8d262fa35a63e462b", "sha256": "a62211f74a1c99166bd2895cbf79b4733b82f0d4beccec1799663997da3b8759"},
        "study.py": {"git_blob": "6b11879cf2885e835e9d8e4b1c0479e50c1af908", "sha256": "e224109e8a45445807822fa742f28ed2d39992bdb64888432398e8dfdbdb4997"},
    },
}
FREEZE = {
    "commit": "1290b6e7a244fc9388003240959e21504ca8cbf5",
    "tree": "a8bc25c5a723abce5ce990b29a5b96a4e6267e7a",
    "path": "evaluation-results/hbq-l2-line-breaks-text-holdout-v1",
    "files": {
        "README.md": {"git_blob": "8f32f886e784eca8670f3314133ebed677bbdf43", "sha256": "d55cd3015ff5d91467a28a8b1cf46cde7a39e0309948d074ee3d9360c2bb34cd"},
        "expected-ledger.json": {"git_blob": "772affac15ba42d5fdf8cdce6dad01a7b4c59292", "sha256": "61f47e1eb145de78b5ed090c7a1391d9f80b6ff2cf78b8ad3d3d581e9bfbaa33"},
        "public-synthetic-corpus.json": {"git_blob": "3aca91931f5c7dc02e6f3fd2d4a0d88f7a927910", "sha256": "4f0dff1277d687a0bc821fe45dbc723dcecebe839cf812fcf8ffc9727bdd56d0"},
        "run.py": {"git_blob": "51cdf0d8655bfed738aa38e7fa1fbfaaa151181f", "sha256": "edd67cea31ce553827472a4b207302ac4b1dba50f4673cb41bca73216a9d7d8e"},
        "study-contract.json": {"git_blob": "91b35854954cd97c4539f25c5e40fd250d88a797", "sha256": "11156c33ce3a7b2316f2ae32510d68006a580006a594fbb150dce3968ff98c13"},
        "study.py": {"git_blob": "bc491525b54cfc27a4c619c56db2a9294ea3d12e", "sha256": "625b97eee00ad06679d394b47fe5cd0e66fe6f04b03955bd16a41e219cc64f94"},
    },
}
RUNTIME = {
    "src/hbqrs/runner.py": {"git_blob": "cc244ad40924c2a11c044268ca89af0fc1ba5f65", "sha256": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2"},
    "prompts/judge/JUDGE_PREFIX.md": {"git_blob": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e", "sha256": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74"},
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": {"git_blob": "d2662edfccc115c6d0c4d97af82a10c9e926b853", "sha256": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2"},
    "schema/hbq_judge_response.schema.json": {"git_blob": "1034a35dcd6c30a75101f369627d60e155d65c2c", "sha256": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"},
    "registry/all_modules.json": {"git_blob": "d94af34c80cf32b4d5a380167e66e2af39f29ad7", "sha256": "4da342cc24881c70be11e5e2cd92a7beccbeb024e5808a5c779935f29989a4ed"},
    "bundles/all_bundles.jsonl": {"git_blob": "718a935081abbf2d1949ceacfb9e5a45e81b85eb", "sha256": "18fe55b796b2809f9b8fe3b8cfbc9ef672d990141c79839cf291b6ace7308f5f"},
    "registry/criterion_ownership.json": {"git_blob": "685846945ddd562992b313b17e8efa72692b8036", "sha256": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876"},
    "registry/question_index.jsonl": {"git_blob": "4ab3b7e11fe2e150cc0defafc22a29929cf5799c", "sha256": "0de8eec70a5a4de74770570253af96f6483c07fcf00ebad198fe951cf2af1fb6"},
}
COMPILED_LEAF_HASHES = {
    LINE_BREAKS: "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c",
    NECESSITY: "a8c36e24125ba32db2694051252a5c17e9fc05abe48cd185f014b7b2a704e0eb",
}


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


def _verify_lineage(binding: Mapping[str, Any], label: str) -> None:
    root = REPOSITORY / str(binding["path"])
    if not root.is_dir():
        raise ValueError(f"{label} is unavailable")
    expected_hashes = {name: details["sha256"] for name, details in binding["files"].items()}
    if {name: sha256_file(root / name) for name in expected_hashes} != expected_hashes:
        raise ValueError(f"{label} bytes drifted")
    refs = [f"{binding['commit']}:{binding['path']}/{name}" for name in binding["files"]]
    result = subprocess.run(["git", "rev-parse", *refs], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if result.returncode or result.stdout.split() != [details["git_blob"] for details in binding["files"].values()]:
        raise ValueError(f"{label} Git binding drifted")
    tree = subprocess.run(["git", "rev-parse", f"{binding['commit']}^{{tree}}"], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if tree.returncode or tree.stdout.strip() != binding["tree"]:
        raise ValueError(f"{label} tree binding drifted")


@lru_cache(maxsize=1)
def compiled_leaf_records() -> dict[str, dict[str, Any]]:
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundle = resolve_bundle(load_bundles(REPOSITORY / "bundles" / "all_bundles.jsonl"), "poetry.free_verse")
    available = {str(item["question"]["id"]): item for item in compiled_questions(compile_bundle(modules, bundle))}
    records = {leaf_id: json.loads(canonical_bytes(available[leaf_id]).decode("utf-8")) for leaf_id in COMPILED_LEAF_HASHES if leaf_id in available}
    if set(records) != set(COMPILED_LEAF_HASHES):
        raise ValueError("The poetry bundle no longer activates the required leaves")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf_id: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf_id, record in compiled_leaf_records().items()}


def canonical_question() -> dict[str, Any]:
    return deepcopy(compiled_leaf_records()[LINE_BREAKS])


def treatment_question() -> dict[str, Any]:
    question = canonical_question()
    question["question"]["text"] = CANDIDATE_TEXT
    return question


def verify_bindings() -> None:
    for binding, label in ((PUBLIC_RESULT, "Pinned public result"), (EXECUTOR, "Pinned executor"), (FREEZE, "Pinned freeze")):
        _verify_lineage(binding, label)
    runtime = {path: sha256_file(REPOSITORY / path) for path in RUNTIME}
    if runtime != {path: details["sha256"] for path, details in RUNTIME.items()}:
        raise ValueError("Pinned production runtime bytes drifted")
    result = subprocess.run(["git", "rev-parse", *(f"{EXECUTOR['commit']}:{path}" for path in RUNTIME)], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if result.returncode or result.stdout.split() != [details["git_blob"] for details in RUNTIME.values()]:
        raise ValueError("Pinned production runtime Git binding drifted")
    if source_leaf_hashes() != COMPILED_LEAF_HASHES:
        raise ValueError("Pinned compiled leaf binding drifted")
    ownership = load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    if ownership.get(LINE_BREAKS) != {"module_id": "form.poetry.free_verse", "question_id": LINE_BREAKS} or ownership.get(NECESSITY) != {"module_id": "form.poetry.free_verse", "question_id": NECESSITY}:
        raise ValueError("Poetry leaf ownership drifted")


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    expected_text = {
        "t01": "Before dawn\nthe tram rail\ngives back\nthe green of its signal.",
        "t02": "Clerks archived the\nminutes beneath the\ncabinet after the\nnoon delivery.",
        "t03": "The mineral exhibit dimmed behind its glass at closing.",
        "t04": "A narrow moon hangs white above the lane;\nthe last bus leaves, and leaves the rain again.",
        "t05": "At the quay\nthe bell answers:\nonce\nfor departure,\nonce\nfor return,\nonce\nfor the dark.",
        "t06": "At closing, staff recorded gallery temperatures\nbefore wheeling two sealed crates through the service\ndoor.",
    }
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != 6:
        raise ValueError("Exactly six treatment cases are required")
    expected_keys = {"case_id", "artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"}
    for index, case in enumerate(cases, start=21):
        if set(case) != expected_keys or case["case_id"] not in CASE_IDS:
            raise ValueError("Case shape drifted")
        surface = (f"artifact-{index}.txt", "poetry", "poetry.free_verse", "poem", "complete", expected_text[case["case_id"]], False, None)
        actual = tuple(case[key] for key in ("artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"))
        if actual != surface:
            raise ValueError("Case surface drifted")
    if [case["case_id"] for case in cases] != list(CASE_IDS) or "the\n" in expected_text["t06"] or "a\n" in expected_text["t06"]:
        raise ValueError("Case freshness or negative mechanism drifted")


def verify_ledger(ledger: Mapping[str, Any]) -> None:
    expected = {"t01": "YES", "t02": "NO", "t03": "NOT_APPLICABLE", "t04": "YES", "t05": "YES", "t06": "NO"}
    if ledger != {"format_version": 1, "study_id": STUDY_ID, "cells": expected} or set(expected.values()) != VERDICTS:
        raise ValueError("Protected outcome ledger drifted")


def materialize_artifacts() -> dict[str, dict[str, Any]]:
    return {case["case_id"]: dict(case) for case in load_corpus()["cases"]}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_type"], "declared_scope": artifact["declared_scope"], "completion_status": artifact["completion_status"], "background": "Public synthetic construct validation.", "constraints": [{"id": "scope", "statement": "Use only the supplied artifact."}, {"id": "image_input", "statement": "image_input_required=false"}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def binary_prompt() -> str:
    return "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))


def rendered_prompt(case_id: str, *, candidate: bool) -> str:
    artifact = materialize_artifacts().get(case_id)
    if artifact is None:
        raise ValueError("Unknown treatment case")
    question = treatment_question() if candidate else canonical_question()
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt(), artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[question], task_contract_context=task_context_for(artifact))
    for forbidden in ("expected-ledger", "ledger", "baseline", "treatment", "holdout", "arm", case_id):
        if forbidden in prompt.casefold():
            raise ValueError(f"Rendered prompt leaked local study metadata: {forbidden}")
    return prompt


def render_pairs() -> dict[str, dict[str, str]]:
    verify_bindings()
    pairs = {case_id: {"canonical": rendered_prompt(case_id, candidate=False), "candidate": rendered_prompt(case_id, candidate=True)} for case_id in CASE_IDS}
    if len(pairs) != 6 or any(set(pair) != {"canonical", "candidate"} for pair in pairs.values()):
        raise ValueError("Pair geometry drifted")
    for pair in pairs.values():
        if pair["candidate"].count(CANDIDATE_TEXT) != 1 or pair["canonical"].count(canonical_question()["question"]["text"]) != 1:
            raise ValueError("Question rendering drifted")
        if pair["candidate"].replace(CANDIDATE_TEXT, canonical_question()["question"]["text"], 1) != pair["canonical"]:
            raise ValueError("Candidate changed more than the question text")
    return pairs


def plan_treatment_slots() -> list[dict[str, Any]]:
    labels = load_ledger()["cells"]
    slots = [{"slot_id": f"l2context-v1-{index:03d}", "case_id": case_id, "leaf_id": LINE_BREAKS, "repeat": repeat, "expected_verdict": labels[case_id]} for index, (case_id, repeat) in enumerate(((case_id, repeat) for case_id in CASE_IDS for repeat in range(1, 4)), start=1)]
    if len(slots) != 18 or len({slot["slot_id"] for slot in slots}) != 18:
        raise ValueError("Future treatment geometry drifted")
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "status": "frozen_provider_free_contextual_justification_treatment", "development_only": True,
        "pair_screen": {"cases_exact": 6, "canonical_renders_exact": 6, "candidate_renders_exact": 6, "renders_exact": 12, "only_delta": "form.poetry.free_verse.line_breaks.question.text"},
        "future_treatment_execution": {"permitted_here": False, "leaf_id": LINE_BREAKS, "cells_exact": 6, "repeats_exact": 3, "slots_exact": 18, "all_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY", "invalid_or_incomplete": "no_result"},
        "candidate_override": {"leaf_id": LINE_BREAKS, "field": "question.text", "text": CANDIDATE_TEXT, "registry_promotion": "none"},
        "scope": {"necessity": "excluded_from_pairs_and_future_treatment_but_bound_unchanged", "images": "forbidden", "remote_contact": "forbidden", "dspy": "forbidden", "promotion": "none"},
        "privacy": {"expected_ledger_in_rendered_prompts": False, "case_or_variant_metadata_in_rendered_prompts": False, "public_synthetic_only": True},
        "bindings": {"public_result": PUBLIC_RESULT, "executor": EXECUTOR, "freeze": FREEZE, "runtime": RUNTIME, "compiled_source_leaves": COMPILED_LEAF_HASHES, "corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}, "expected_ledger": {"path": "expected-ledger.json", "sha256": sha256_file(ROOT / "expected-ledger.json")}},
    }
    if contract != expected:
        raise ValueError("Treatment contract drifted")
    verify_bindings()
    verify_corpus(load_corpus())
    verify_ledger(load_ledger())
    pairs = render_pairs()
    slots = plan_treatment_slots()
    if len(pairs) * 2 != 12 or len(slots) != 18 or any(slot["leaf_id"] != LINE_BREAKS for slot in slots):
        raise ValueError("Treatment screen geometry drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "new_remote_calls": 0, "pair_renders": 12, "future_treatment_slots": 18}


def dry_run_report() -> dict[str, Any]:
    report = verify_package()
    pairs = render_pairs()
    hashes = {case_id: {variant: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for variant, prompt in pair.items()} for case_id, pair in pairs.items()}
    return {"mode": "dry_run", "verification": report, "rendered_pairs": len(pairs), "rendered_prompts": 12, "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(hashes)).hexdigest()}
