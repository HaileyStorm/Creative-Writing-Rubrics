"""Provider-free prompt planner for a fresh text-only L2 line-break holdout."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SOURCE_PREDECESSOR_ROOT = ROOT.parent / "hbq-l2-construct-microgate-v2"
DECISION_LINEAGE_ROOT = ROOT.parent / "hbq-l2-construct-microgate-v2-execution-v2-public-result-v1"
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs import runner as production_runner

STUDY_ID = "hbq-l2-line-breaks-text-holdout-v1"
PINNED_COMMIT = "9bbba7b053705a8c5e58403d9a5af4acd4567fad"
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
NECESSITY = "form.poetry.free_verse.necessity"
LEAVES = (LINE_BREAKS, NECESSITY)
CASE_IDS = ("t01", "t02", "t03", "t04")
CANDIDATE_TEXT = "Does each supplied line break make a controlled, legible contribution to rhythm, syntax, emphasis, image, ambiguity, or pace?"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE"))

SOURCE_PREDECESSOR = {
    "path": "evaluation-results/hbq-l2-construct-microgate-v2",
    "git_tree_commit": PINNED_COMMIT,
    "files": {
        "README.md": {"git_blob": "0d8e8a7f1472cdaa1f7173fe0da5cab58fa1965f", "sha256": "c4a8006ab479637fa9954befadea92309d2f90f185b185b57987a1afe46f5a0b"},
        "public-synthetic-corpus.json": {"git_blob": "ed266a1b73c052694fad64e4e5812048c4c86a97", "sha256": "05a5a8011a1a360235b7d724158f3be2bd4e51ca0cf997266d963849d2ed222b"},
        "expected-ledger.json": {"git_blob": "464f3d02cefdaf98f5ba2f5b6ff1e3e12fae6384", "sha256": "0ac0a0816e17dd45d5cf432036ae3b2dd811fbab924dd9dc6097adeeafd2c15d"},
        "study-contract.json": {"git_blob": "6b9f6868d8a185a955a8f34bf4374972f45e0b3a", "sha256": "e6c95cf718dd0ab8a7962dec5b16a41138af0994e7115ee1ecb46e9dd0ce06e7"},
        "study.py": {"git_blob": "baf26d8da07ebcb067a62dd0c865fee77f1f2447", "sha256": "62e99cadbb091301d8b6789a2e8e428acb51e074fc6c3c195221e9c95a55a8f5"},
        "run.py": {"git_blob": "ac6a2ef22e2e49db0bcf957be44c7656e94b7fce", "sha256": "8e31117d3955da618fbf78c67d34aeaf0c2f7275bb97432dc87ca6f5cf87dcba"},
    },
}
DECISION_LINEAGE = {
    "path": "evaluation-results/hbq-l2-construct-microgate-v2-execution-v2-public-result-v1",
    "git_tree_commit": PINNED_COMMIT,
    "files": {
        "README.md": {"git_blob": "d854cab65e5be6d2bcf89c85859d0648b79bfee2", "sha256": "1a48ed680cbd8886a9f6233ba37794021123e4e9d88d245e671448a20d9d551b"},
        "public-result.json": {"git_blob": "5b53c472083bc7eed0167808282c1822bb10209f", "sha256": "67df592ba43f842dc2338a29a82a19adb74358a7f294dbc22dd5ba9602727cf8"},
    },
}
VISUAL_DIAGNOSTIC_LINEAGE = {
    "path": "evaluation-results/hbq-l2-c03-visual-control-successor-v1-execution-v1-public-result-v1",
    "git_tree_commit": "650f18dfee724db65d8bbc7fa2c7920ebcec1a9d",
    "files": {
        "README.md": {"git_blob": "c04ee365669ece0c5deb4ff07330ae8c30d0c218", "sha256": "890b6b8217e512782d1deae957072a373db111ed72b624732ce82d014c880a1c"},
        "public-result.json": {"git_blob": "b7522afcb3b323f48a1d2e98a1f5419b33eea245", "sha256": "3b13893b7bea1f7f95d9700e796619635cbc14a80170d22f511b8ad9721e75b3"},
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


def _verify_pinned_files(root: Path, binding: Mapping[str, Any], label: str) -> None:
    if not root.is_dir():
        raise ValueError(f"{label} is unavailable")
    actual = {name: sha256_file(root / name) for name in binding["files"]}
    expected = {name: details["sha256"] for name, details in binding["files"].items()}
    if actual != expected:
        raise ValueError(f"{label} provenance drifted")


def _verify_git_blobs(root: Path, binding: Mapping[str, Any], label: str) -> None:
    base = str(binding["path"]).replace("\\", "/")
    relative_paths = tuple(binding["files"])
    result = subprocess.run(["git", "rev-parse", *(f"{binding['git_tree_commit']}:{base}/{relative_path}" for relative_path in relative_paths)], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if result.returncode != 0 or result.stdout.split() != [binding["files"][relative_path]["git_blob"] for relative_path in relative_paths]:
        raise ValueError(f"{label} Git blob provenance drifted")


def _verify_runtime_git_blobs() -> None:
    paths = tuple(RUNTIME)
    result = subprocess.run(["git", "rev-parse", *(f"{PINNED_COMMIT}:{path}" for path in paths)], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if result.returncode != 0 or result.stdout.split() != [RUNTIME[path]["git_blob"] for path in paths]:
        raise ValueError("Pinned production runtime Git blob provenance drifted")


def verify_bindings() -> None:
    _verify_pinned_files(SOURCE_PREDECESSOR_ROOT, SOURCE_PREDECESSOR, "Pinned source predecessor")
    _verify_pinned_files(DECISION_LINEAGE_ROOT, DECISION_LINEAGE, "Pinned decision lineage")
    _verify_pinned_files(ROOT.parent / "hbq-l2-c03-visual-control-successor-v1-execution-v1-public-result-v1", VISUAL_DIAGNOSTIC_LINEAGE, "Pinned visual diagnostic lineage")
    _verify_git_blobs(SOURCE_PREDECESSOR_ROOT, SOURCE_PREDECESSOR, "Pinned source predecessor")
    _verify_git_blobs(DECISION_LINEAGE_ROOT, DECISION_LINEAGE, "Pinned decision lineage")
    _verify_git_blobs(ROOT.parent / "hbq-l2-c03-visual-control-successor-v1-execution-v1-public-result-v1", VISUAL_DIAGNOSTIC_LINEAGE, "Pinned visual diagnostic lineage")
    _verify_runtime_git_blobs()
    actual_runtime = {path: sha256_file(REPOSITORY / path) for path in RUNTIME}
    expected_runtime = {path: details["sha256"] for path, details in RUNTIME.items()}
    if actual_runtime != expected_runtime:
        raise ValueError("Pinned production runtime drifted")
    if source_leaf_hashes() != COMPILED_LEAF_HASHES:
        raise ValueError("Pinned compiled leaf provenance drifted")


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    expected_text = {
        "t01": "Before dawn\nthe tram rail\ngives back\nthe green of its signal.",
        "t02": "Clerks archived the\nminutes beneath the\ncabinet after the\nnoon delivery.",
        "t03": "The mineral exhibit dimmed behind its glass at closing.",
        "t04": "A narrow moon hangs white above the lane;\nthe last bus leaves, and leaves the rain again.",
    }
    required = {"case_id", "artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"}
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("Exactly four text-only holdout cases are required")
    observed: set[str] = set()
    for index, case in enumerate(cases, start=11):
        if set(case) != required or case["case_id"] in observed or case["case_id"] not in expected_text:
            raise ValueError("Case identity drifted")
        observed.add(case["case_id"])
        expected_surface = (f"artifact-{index}.txt", "poetry", "poetry.free_verse", "poem", "complete", expected_text[case["case_id"]], False, None)
        actual_surface = tuple(case[key] for key in ("artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"))
        if actual_surface != expected_surface:
            raise ValueError("Case surface drifted")
    if observed != set(CASE_IDS):
        raise ValueError("Case membership drifted")
    if expected_text["t01"].count("\n") != 3 or expected_text["t02"].count("\n") != 3 or "\n" in expected_text["t03"] or expected_text["t04"].count("\n") != 1:
        raise ValueError("Text-lineation fixture drifted")


def verify_ledger(ledger: Mapping[str, Any]) -> None:
    expected = {"t01": ["YES", "YES"], "t02": ["NO", "NO"], "t03": ["NOT_APPLICABLE", "NO"], "t04": ["YES", "NO"]}
    if ledger != {"format_version": 1, "study_id": STUDY_ID, "cells": expected}:
        raise ValueError("Expected holdout ledger drifted")
    if {state for states in expected.values() for state in states} != VERDICTS:
        raise ValueError("Mixed-state holdout ledger drifted")


def materialize_artifacts(corpus: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    corpus = load_corpus() if corpus is None else corpus
    return {case["case_id"]: dict(case) for case in corpus["cases"]}


def compiled_leaf_records() -> dict[str, dict[str, Any]]:
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundle = resolve_bundle(load_bundles(REPOSITORY / "bundles" / "all_bundles.jsonl"), "poetry.free_verse")
    available = {str(item["question"]["id"]): item for item in compiled_questions(compile_bundle(modules, bundle))}
    records = {leaf_id: json.loads(canonical_bytes(available[leaf_id]).decode("utf-8")) for leaf_id in LEAVES if leaf_id in available}
    if set(records) != set(LEAVES):
        raise ValueError("Compiled poetry bundle does not activate the required leaves")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf_id: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf_id, record in compiled_leaf_records().items()}


def canonical_question(leaf_id: str) -> dict[str, Any]:
    return deepcopy(compiled_leaf_records()[leaf_id])


def binary_prompt() -> str:
    return "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_type"], "declared_scope": artifact["declared_scope"], "completion_status": artifact["completion_status"], "background": "Public synthetic construct validation.", "constraints": [{"id": "scope", "statement": "Use only the supplied artifact."}, {"id": "image_input", "statement": "image_input_required=false"}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def question_for(leaf_id: str) -> dict[str, Any]:
    record = canonical_question(leaf_id)
    if leaf_id == LINE_BREAKS:
        record["question"]["text"] = CANDIDATE_TEXT
    return record


def verify_candidate_override() -> None:
    canonical = canonical_question(LINE_BREAKS)
    candidate = question_for(LINE_BREAKS)
    restored = deepcopy(candidate)
    restored["question"]["text"] = canonical["question"]["text"]
    if restored != canonical or candidate["question"]["text"] != CANDIDATE_TEXT or question_for(NECESSITY) != canonical_question(NECESSITY):
        raise ValueError("Candidate-only wording override drifted")


def plan_slots() -> list[dict[str, Any]]:
    ledger = load_ledger()["cells"]
    slots: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        for leaf_index, leaf_id in enumerate(LEAVES):
            for repeat in range(1, 4):
                slots.append({"slot_id": f"l2text-v1-{len(slots) + 1:03d}", "case_id": case_id, "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": ledger[case_id][leaf_index]})
    if len(slots) != 24 or len({slot["slot_id"] for slot in slots}) != 24:
        raise ValueError("Singleton slot geometry drifted")
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_text_only_candidate_line_break_holdout",
        "development_only": True,
        "provider_execution": {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True},
        "geometry": {"cases_exact": 4, "leaves_per_case_exact": 2, "repeats_exact": 3, "slots_exact": 24, "cells_exact": 8},
        "labels": ["YES", "NO", "NOT_APPLICABLE"],
        "candidate_override": {"leaf_id": LINE_BREAKS, "field": "question.text", "text": CANDIDATE_TEXT, "registry_promotion": "none"},
        "canonical_control": {"leaf_id": NECESSITY, "registry_text": "unchanged"},
        "screen": {"renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False, "image_input_required": False, "image_text_substitution_forbidden": True},
        "lifecycle": {"remote_execution_surface": "absent", "retry_or_resume": "not_authorized_by_freeze"},
        "promotion": {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"},
        "history": {"source_predecessor": SOURCE_PREDECESSOR["path"], "decision_lineage": DECISION_LINEAGE["path"], "visual_diagnostic_lineage": VISUAL_DIAGNOSTIC_LINEAGE["path"], "visual_controls": "excluded_from_fresh_text_only_holdout_not_reused"},
    }
    if {key: contract.get(key) for key in expected} != expected or set(contract) != {*expected, "bindings"}:
        raise ValueError("Contract policy drifted")
    expected_bindings = {
        "pinned_commit": PINNED_COMMIT,
        "corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")},
        "expected_ledger": {"path": "expected-ledger.json", "sha256": sha256_file(ROOT / "expected-ledger.json")},
        "source_predecessor": SOURCE_PREDECESSOR,
        "decision_lineage": DECISION_LINEAGE,
        "visual_diagnostic_lineage": VISUAL_DIAGNOSTIC_LINEAGE,
        "runtime": RUNTIME,
        "compiled_source_leaves": COMPILED_LEAF_HASHES,
    }
    if contract["bindings"] != expected_bindings:
        raise ValueError("Frozen package binding drifted")
    verify_bindings()
    verify_corpus(load_corpus())
    verify_ledger(load_ledger())
    verify_candidate_override()
    slots = plan_slots()
    if len({(slot["case_id"], slot["leaf_id"]) for slot in slots}) != 8 or {slot["expected_verdict"] for slot in slots} != VERDICTS:
        raise ValueError("Text-only holdout geometry drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "cases": 4, "cells": 8, "slots": 24, "image_input_slots": 0}


def _provider_request(slot_id: str) -> dict[str, Any]:
    slot = next((row for row in plan_slots() if row["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = materialize_artifacts()[slot["case_id"]]
    prompt = production_runner._render_prompt(
        binary_prompt=binary_prompt(),
        artifact={"name": artifact["artifact_name"], "text": artifact["text"]},
        contexts=[],
        bundle_id=artifact["bundle_id"],
        artifact_id="public-synthetic-artifact",
        questions=[question_for(slot["leaf_id"])],
        task_contract_context=task_context_for(artifact),
    )
    for forbidden in (slot["slot_id"], slot["case_id"], "expected_verdict", "expected-ledger", "text-holdout", "YES/YES", "NO/NO", "NOT_APPLICABLE/NO", "YES/NO"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local holdout metadata")
    return {"prompt": prompt, "image_inputs": []}


def provider_request(slot_id: str) -> dict[str, Any]:
    verify_bindings()
    return _provider_request(slot_id)


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    verify_bindings()
    rendered = {slot["slot_id"]: _provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(rendered) != 24 or any(request["image_inputs"] for request in rendered.values()):
        raise ValueError("Text-only prompt rendering drifted")
    return rendered


def dry_run_report() -> dict[str, Any]:
    verification = verify_package()
    inputs = render_all_provider_inputs()
    prompt_hashes = {slot_id: hashlib.sha256(request["prompt"].encode("utf-8")).hexdigest() for slot_id, request in inputs.items()}
    return {"mode": "dry_run", "verification": verification, "rendered_slots": len(inputs), "attached_image_slots": 0, "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(prompt_hashes)).hexdigest()}
