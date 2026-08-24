"""Provider-free renderer for a fresh, disjoint material-context holdout."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs import runner as production_runner

STUDY_ID = "hbq-l2-material-context-disjoint-holdout-v1"
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
CASE_IDS = ("h01", "h02", "h03", "h04", "h05")
CANDIDATE_TEXT = "Does each supplied line break materially strengthen its immediate poetic context through rhythm, syntax, emphasis, image, ambiguity, or pace, beyond merely creating a detectable pause, syntactic interruption, or repeated pattern?"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE"))
TREATMENT_FREEZE = "fd96e808d1bf29f968a1fa2c532e41a84fb8fd3e"
EXECUTOR_COMMIT = "7be37a22d1dac7f50f3a802d72927edd102319d6"
PUBLIC_RESULT_COMMIT = "45e7d309cb03ad7c9cbe45194653cc7e2a9132a5"
RUNTIME_BLOBS = {
    "src/hbqrs/runner.py": "cc244ad40924c2a11c044268ca89af0fc1ba5f65",
    "prompts/judge/JUDGE_PREFIX.md": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "d2662edfccc115c6d0c4d97af82a10c9e926b853",
    "registry/all_modules.json": "d94af34c80cf32b4d5a380167e66e2af39f29ad7",
    "bundles/all_bundles.jsonl": "718a935081abbf2d1949ceacfb9e5a45e81b85eb",
    "src/hbqrs/core.py": "9dd1d9be694baa1e08ab7e829afa3af8c0df5145",
    "src/hbqrs/__init__.py": "d5b57e1d99e6590ac75002a8d7768f2542da65b8",
}
COMPILED_LEAF_HASH = "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c"
EXPECTED_PROVIDER_EXECUTION = {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}
EXPECTED_SCOPE = {"images": "forbidden", "remote_contact": "forbidden", "dspy": "forbidden", "promotion": "none", "case_metadata_provider_facing": False, "expected_labels_provider_facing": False}
EXPECTED_CASES = {
    "h01": ("artifact-51.txt", "The witness examined\nby the quiet magistrate trembled.", "semantic_reduced_relative_garden_path_sole_break_contributes"),
    "h02": ("artifact-52.txt", "Before curfew\none window remained lit\nabove the harbor.", "pacing_and_emphasis_without_rhyme_or_refrain"),
    "h03": ("artifact-53.txt", "Riveters documented each transverse fastening\nalong the spillway and forwarded the numbered\nentries to the docket clerk.", "clause_insensitive_neutral_prose_wrap"),
    "h04": ("artifact-54.txt", "The anemometer reads eight.\nThe anemometer reads eight.\nThe anemometer reads eight.", "regular_repeated_complete_proposition_without_contextual_function"),
    "h05": ("artifact-55.txt", "Lichen whitens the slate beneath a cold constellation.", "single_line_not_applicable"),
}
EXPECTED_LEDGER = {"h01": "YES", "h02": "YES", "h03": "NO", "h04": "NO", "h05": "NOT_APPLICABLE"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(name: str) -> dict[str, Any]:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {name}")
    return value


def load_contract() -> dict[str, Any]:
    return load_json("study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json("public-synthetic-corpus.json")


def load_ledger() -> dict[str, Any]:
    return load_json("expected-ledger.json")


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "Git binding lookup failed")
    return completed.stdout.strip()


def canonical_question() -> dict[str, Any]:
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundle = resolve_bundle(load_bundles(REPOSITORY / "bundles" / "all_bundles.jsonl"), "poetry.free_verse")
    compiled = {record["question"]["id"]: record for record in compiled_questions(compile_bundle(modules, bundle))}
    if LINE_BREAKS not in compiled:
        raise ValueError("Line-break leaf is inactive")
    return json.loads(canonical_bytes(compiled[LINE_BREAKS]).decode("utf-8"))


def candidate_question() -> dict[str, Any]:
    question = deepcopy(canonical_question())
    question["question"]["text"] = CANDIDATE_TEXT
    return question


def materialize_artifacts() -> dict[str, dict[str, Any]]:
    return {case["case_id"]: dict(case) for case in load_corpus()["cases"]}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION,
        "untrusted_evaluation_data": True,
        "artifact_kind": artifact["artifact_type"],
        "declared_scope": artifact["declared_scope"],
        "completion_status": artifact["completion_status"],
        "background": "Public synthetic construct validation.",
        "constraints": [{"id": "scope", "statement": "Use only the supplied artifact."}],
        "audience": "development-only rubric validation",
        "preferences": [],
        "priorities": [],
    }


def binary_prompt() -> str:
    return "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))


def plan_slots() -> list[dict[str, Any]]:
    slots = [{"slot_id": f"l2material-holdout-v1-{index:03d}", "case_id": case_id, "leaf_id": LINE_BREAKS, "repeat": repeat} for index, (case_id, repeat) in enumerate(((case_id, repeat) for case_id in CASE_IDS for repeat in range(1, 4)), 1)]
    if len(slots) != 15 or len({slot["slot_id"] for slot in slots}) != 15:
        raise ValueError("Fresh singleton schedule drifted")
    return slots


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _trigrams(text: str) -> set[tuple[str, str, str]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return set(zip(words, words[1:], words[2:]))


def load_inventory() -> dict[str, Any]:
    return load_json("prior-corpus-motif-inventory.json")


def prior_inventory_texts() -> list[str]:
    inventory = load_inventory()
    values: list[str] = []
    for source in inventory["sources"]:
        text = _git("show", f"{inventory['inventory_commit']}:{source['path']}")
        try:
            values.extend(_strings(json.loads(text)))
        except json.JSONDecodeError:
            values.append(text)
    return values


def verify_disjointness() -> None:
    targets = [case["text"] for case in load_corpus()["cases"]]
    inventory = load_inventory()
    prior = prior_inventory_texts()
    if any(text in prior for text in targets):
        raise ValueError("Fresh text byte-collides with an inventoried prior corpus")
    for text in targets:
        grams = _trigrams(text)
        if any(grams & _trigrams(previous) for previous in prior if _trigrams(previous)):
            raise ValueError("Fresh text shares a lexical trigram with an inventoried prior corpus")
    target_words = set(re.findall(r"[a-z0-9]+", " ".join(targets).lower()))
    target_surface = " ".join(targets).casefold()
    for source in inventory["sources"]:
        for motif in source["declared_motifs"]:
            if " " in motif and motif.casefold() in target_surface or " " not in motif and motif.casefold() in target_words:
                raise ValueError("Fresh text reuses an inventoried declared motif")
    for motif in inventory["discarded_unexecuted_draft_motifs"]:
        if " " in motif and motif.casefold() in target_surface or " " not in motif and motif.casefold() in target_words:
            raise ValueError("Fresh text reuses a rejected draft motif")


def verify_bindings() -> None:
    contract = load_contract()["bindings"]
    expected_refs = {
        ("treatment_freeze_commit",): TREATMENT_FREEZE,
        ("executor_commit",): EXECUTOR_COMMIT,
        ("public_result_commit",): PUBLIC_RESULT_COMMIT,
    }
    for (key,), value in expected_refs.items():
        if contract[key] != value:
            raise ValueError("Pinned lineage reference drifted")
    if contract["runtime"] != RUNTIME_BLOBS or contract["compiled_line_break_leaf_sha256"] != COMPILED_LEAF_HASH:
        raise ValueError("Pinned compile-owner binding drifted")
    if _git("rev-parse", f"{TREATMENT_FREEZE}^{{tree}}") != contract["treatment_freeze_tree"] or _git("rev-parse", f"{EXECUTOR_COMMIT}^{{tree}}") != contract["executor_tree"] or _git("rev-parse", f"{PUBLIC_RESULT_COMMIT}^{{tree}}") != contract["public_result_tree"]:
        raise ValueError("Pinned lineage tree drifted")
    if _git("rev-parse", f"{TREATMENT_FREEZE}:evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v2/study.py") != contract["treatment_study_blob"] or _git("rev-parse", f"{EXECUTOR_COMMIT}:evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v2-execution-v1/study.py") != contract["executor_study_blob"]:
        raise ValueError("Pinned treatment or executor bytes drifted")
    result_path = "evaluation-results/hbq-l2-line-breaks-contextual-justification-treatment-v2-execution-v1-public-result-v1"
    if {name: _git("rev-parse", f"{PUBLIC_RESULT_COMMIT}:{result_path}/{name}") for name in contract["public_result_files"]} != contract["public_result_files"]:
        raise ValueError("Pinned public-result bytes drifted")
    result = json.loads(_git("show", f"{PUBLIC_RESULT_COMMIT}:{result_path}/public-result.json"))
    if result.get("source_bindings") != contract["settled_commitments"]:
        raise ValueError("Settled commitments do not match the pinned public result")
    if {path: _git("rev-parse", f"{TREATMENT_FREEZE}:{path}") for path in RUNTIME_BLOBS} != RUNTIME_BLOBS or any(_git("hash-object", path) != blob for path, blob in RUNTIME_BLOBS.items()):
        raise ValueError("Runtime binding drifted")
    inventory = load_inventory()
    expected_inventory_binding = {"path": "prior-corpus-motif-inventory.json", "sha256": sha256_file(ROOT / "prior-corpus-motif-inventory.json"), "object": inventory}
    if contract["prior_corpus_motif_inventory"] != expected_inventory_binding or inventory["inventory_commit"] != PUBLIC_RESULT_COMMIT:
        raise ValueError("Prior-corpus inventory commit drifted")
    for source in inventory["sources"]:
        if _git("rev-parse", f"{inventory['inventory_commit']}:{source['path']}") != source["git_blob"]:
            raise ValueError("Prior-corpus inventory bytes drifted")
    leaf = canonical_question()
    if hashlib.sha256(canonical_bytes(leaf)).hexdigest() != COMPILED_LEAF_HASH:
        raise ValueError("Compiled leaf binding drifted")


def verify_render_surface() -> None:
    contract = load_contract()
    if contract["study_id"] != STUDY_ID or contract["provider_execution"] != EXPECTED_PROVIDER_EXECUTION or contract["scope"] != EXPECTED_SCOPE or contract["geometry"] != {"cases_exact": 5, "leaves_per_case_exact": 1, "repeats_exact": 3, "slots_exact": 15, "cells_exact": 5, "labels": {"YES": 2, "NO": 2, "NOT_APPLICABLE": 1}}:
        raise ValueError("Holdout contract policy or geometry drifted")
    if contract["candidate_override"] != {"leaf_id": LINE_BREAKS, "field": "question.text", "text": CANDIDATE_TEXT, "registry_promotion": "none"}:
        raise ValueError("Candidate wording drifted")
    if contract["decision_rule"] != {"all_cells_three_of_three": "PROMOTION_REVIEW_ELIGIBLE", "any_complete_valid_miss": "NO_GO", "invalid_or_incomplete": "no_result"}:
        raise ValueError("Decision rule drifted")
    corpus = load_corpus()
    required = {"case_id", "artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "mechanism", "image_input_required", "image_fixture"}
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only" or len(corpus["cases"]) != 5:
        raise ValueError("Corpus identity drifted")
    observed = {case["case_id"]: case for case in corpus["cases"]}
    if set(observed) != set(CASE_IDS) or any(set(case) != required for case in observed.values()):
        raise ValueError("Corpus case shape drifted")
    for case_id, (name, text, mechanism) in EXPECTED_CASES.items():
        case = observed[case_id]
        if tuple(case[key] for key in ("artifact_name", "text", "mechanism")) != (name, text, mechanism) or tuple(case[key] for key in ("artifact_type", "bundle_id", "declared_scope", "completion_status", "image_input_required", "image_fixture")) != ("poetry", "poetry.free_verse", "poem", "complete", False, None):
            raise ValueError("Frozen public-synthetic surface drifted")
    canonical = canonical_question()
    candidate = candidate_question()
    restored = deepcopy(candidate)
    restored["question"]["text"] = canonical["question"]["text"]
    if restored != canonical:
        raise ValueError("Candidate changed more than question text")
    verify_bindings()
    verify_disjointness()
    hashes = _prompt_hashes_unchecked()
    expected_prompt_bindings = {"slots": hashes, "aggregate_sha256": hashlib.sha256(canonical_bytes(hashes)).hexdigest()}
    if contract["bindings"].get("prompt_bindings") != expected_prompt_bindings:
        raise ValueError("Exact provider prompt bindings drifted")


def verify_oracle_ledger() -> None:
    if load_ledger() != {"format_version": 1, "study_id": STUDY_ID, "cells": EXPECTED_LEDGER} or set(EXPECTED_LEDGER.values()) != VERDICTS:
        raise ValueError("Expected labels drifted")


def verify_package() -> dict[str, Any]:
    verify_render_surface()
    verify_oracle_ledger()
    return {"study_id": STUDY_ID, "provider_calls": 0, "cases": 5, "cells": 5, "future_slots": 15, "image_input_slots": 0}


def provider_request(slot_id: str) -> dict[str, Any]:
    slot = next((entry for entry in plan_slots() if entry["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = materialize_artifacts()[slot["case_id"]]
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt(), artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[candidate_question()], task_contract_context=task_context_for(artifact))
    forbidden = (slot_id, slot["case_id"], artifact["mechanism"], "expected-ledger", "holdout", "candidate", "PROMOTION_REVIEW_ELIGIBLE", "NO_GO")
    if any(token.casefold() in prompt.casefold() for token in forbidden):
        raise ValueError("Provider-facing prompt leaked local metadata")
    return {"prompt": prompt, "image_inputs": []}


def _render_all_unchecked() -> dict[str, dict[str, Any]]:
    rendered = {slot["slot_id"]: provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(rendered) != 15 or any(row["image_inputs"] for row in rendered.values()):
        raise ValueError("Provider input geometry drifted")
    return rendered


def _prompt_hashes_unchecked() -> dict[str, str]:
    return {slot_id: hashlib.sha256(request["prompt"].encode("utf-8")).hexdigest() for slot_id, request in _render_all_unchecked().items()}


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    verify_render_surface()
    return _render_all_unchecked()


def dry_run_report() -> dict[str, Any]:
    verification = verify_package()
    hashes = _prompt_hashes_unchecked()
    return {"mode": "dry_run", "verification": verification, "rendered_slots": 15, "attached_image_slots": 0, "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(hashes)).hexdigest()}
