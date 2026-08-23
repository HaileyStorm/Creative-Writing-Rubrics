"""Provider-free freeze and prompt planner for the L2 construct microgate."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import (
    compile_bundle,
    compiled_questions,
    load_bundles,
    load_modules,
    resolve_bundle,
)
from hbqrs import runner as production_runner

STUDY_ID = "hbq-l2-construct-microgate-v1"
VERDICTS = frozenset(("YES", "NO", "CANNOT_ASSESS"))
POETRY_LEAVES = ("form.poetry.free_verse.line_breaks", "form.poetry.free_verse.necessity")
VISUAL_LEAVES = (
    "form.visual.environment_or_location_illustration.perspective",
    "form.visual.visual_craft_and_artifact_control.perspective",
)
CASE_LEAVES = {"c01": POETRY_LEAVES, "c02": POETRY_LEAVES, "c03": VISUAL_LEAVES, "c04": VISUAL_LEAVES}
CASE_ACTIVATIONS = {
    "c01": ("poetry.free_verse", "poetry", "poem"),
    "c02": ("poetry.free_verse", "poetry", "poem"),
    "c03": ("visual.environment", "visual_asset", "asset"),
    "c04": ("visual.environment", "visual_asset", "asset"),
}
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "src/hbqrs/runner.py",
    "registry/all_modules.json",
    "bundles/all_bundles.jsonl",
)


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


@lru_cache(maxsize=1)
def stairwell_png_bytes() -> bytes:
    spec = importlib.util.spec_from_file_location("l2_construct_stairwell_fixture", ROOT / "assets" / "generate_geometry_fixture.py")
    if spec is None or spec.loader is None:
        raise ValueError("Stairwell fixture generator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.png_bytes()
    if not isinstance(value, bytes) or not value.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Stairwell fixture is not a PNG")
    return value


@lru_cache(maxsize=1)
def stairwell_pixel_invariants() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("l2_construct_stairwell_invariants", ROOT / "assets" / "generate_geometry_fixture.py")
    if spec is None or spec.loader is None:
        raise ValueError("Stairwell fixture generator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.pixel_invariants()
    if not isinstance(value, dict):
        raise ValueError("Stairwell pixel invariants are unavailable")
    return json.loads(canonical_bytes(value).decode("utf-8"))


@lru_cache(maxsize=1)
def compiled_leaf_records() -> dict[str, dict[str, Any]]:
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundles = load_bundles(REPOSITORY / "bundles" / "all_bundles.jsonl")
    records: dict[str, dict[str, Any]] = {}
    for bundle_id, leaves in (("poetry.free_verse", POETRY_LEAVES), ("visual.environment", VISUAL_LEAVES)):
        compiled = compile_bundle(modules, resolve_bundle(bundles, bundle_id))
        available = {str(item["question"]["id"]): item for item in compiled_questions(compiled)}
        for leaf_id in leaves:
            item = available.get(leaf_id)
            if item is None:
                raise ValueError("Compiled bundle does not activate the required leaf")
            records[leaf_id] = json.loads(canonical_bytes(item).decode("utf-8"))
    if set(records) != {*POETRY_LEAVES, *VISUAL_LEAVES}:
        raise ValueError("Compiled leaf membership drifted")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in compiled_leaf_records().items()}


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("Exactly four microgate cases are required")
    required = {"case_id", "artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"}
    expected = {
        "c01": ("artifact-01.txt", "poetry", "poetry.free_verse", "poem", "complete", False, None),
        "c02": ("artifact-02.txt", "poetry", "poetry.free_verse", "poem", "complete", False, None),
        "c03": ("asset-03.png", "visual_asset", "visual.environment", "asset", "complete", True, "impossible_stairwell_v1"),
        "c04": ("asset-04.png", "visual_asset", "visual.environment", "asset", "complete", True, None),
    }
    seen = set()
    for case in cases:
        if set(case) != required or case["case_id"] in seen or case["case_id"] not in expected:
            raise ValueError("Case identity drifted")
        seen.add(case["case_id"])
        observed = (case["artifact_name"], case["artifact_type"], case["bundle_id"], case["declared_scope"], case["completion_status"], case["image_input_required"], case["image_fixture"])
        if observed != expected[case["case_id"]] or not isinstance(case["text"], str):
            raise ValueError("Case surface drifted")
        if case["case_id"] in {"c01", "c02"} and not case["text"].strip():
            raise ValueError("Poetry case text is required")
        if case["case_id"] in {"c03", "c04"} and case["text"]:
            raise ValueError("Visual cases must not substitute an image description")
    if seen != set(expected):
        raise ValueError("Case membership drifted")
    if corpus["cases"][0]["text"].count("\n") != 3 or "\\n" in corpus["cases"][0]["text"]:
        raise ValueError("Lineation-dependent case must contain exact linefeeds")


def verify_ledger(ledger: Mapping[str, Any]) -> None:
    expected = {"c01": ["YES", "YES"], "c02": ["NO", "NO"], "c03": ["NO", "NO"], "c04": ["CANNOT_ASSESS", "CANNOT_ASSESS"]}
    if ledger != {"format_version": 2, "study_id": STUDY_ID, "fixture_binding": {"c03": "impossible_stairwell_v1"}, "cells": expected}:
        raise ValueError("Expected ledger drifted")


def materialize_artifacts(corpus: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    corpus = load_corpus() if corpus is None else corpus
    return {case["case_id"]: dict(case) for case in corpus["cases"]}


def plan_slots() -> list[dict[str, Any]]:
    ledger = load_ledger()["cells"]
    rows: list[dict[str, Any]] = []
    for case_id, leaves in CASE_LEAVES.items():
        for leaf_index, leaf_id in enumerate(leaves):
            for repeat in range(1, 4):
                rows.append({"slot_id": f"l2micro-v1-{len(rows)+1:03d}", "case_id": case_id, "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": ledger[case_id][leaf_index]})
    if len(rows) != 24 or len({row["slot_id"] for row in rows}) != 24:
        raise ValueError("Microgate slot geometry drifted")
    return rows


def verify_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    expected_local = {
        "corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")},
        "expected_ledger": {"path": "expected-ledger.json", "sha256": sha256_file(ROOT / "expected-ledger.json")},
        "stairwell_generator": {"path": "assets/generate_geometry_fixture.py", "sha256": sha256_file(ROOT / "assets" / "generate_geometry_fixture.py"), "png_sha256": hashlib.sha256(stairwell_png_bytes()).hexdigest(), "pixel_geometry_invariants": stairwell_pixel_invariants()},
        "source_leaves": source_leaf_hashes(),
        "runtime": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS},
    }
    if bindings != expected_local:
        raise ValueError("Frozen package binding drifted")
    ownership = load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    records = compiled_leaf_records()
    expected_ownership = {leaf: {"module_id": record["module_id"], "question_id": leaf} for leaf, record in records.items()}
    if {leaf: ownership.get(leaf) for leaf in records} != expected_ownership:
        raise ValueError("Criterion ownership invariant drifted")
    artifacts = materialize_artifacts()
    for case_id, (bundle_id, artifact_type, scope) in CASE_ACTIVATIONS.items():
        artifact = artifacts[case_id]
        if (artifact["bundle_id"], artifact["artifact_type"], artifact["declared_scope"]) != (bundle_id, artifact_type, scope):
            raise ValueError("Case activation declaration drifted")
        bundle = resolve_bundle(load_bundles(REPOSITORY / "bundles" / "all_bundles.jsonl"), bundle_id)
        if artifact_type not in bundle["artifact_types"] or scope not in bundle["valid_scopes"]:
            raise ValueError("Case activation is not production-valid")
        selected = {
            str(item["question"]["id"])
            for item in compiled_questions(compile_bundle(load_modules(REPOSITORY / "registry" / "all_modules.json"), bundle))
        }
        if not set(CASE_LEAVES[case_id]) <= selected:
            raise ValueError("Case leaves are not activated by the selected production bundle")


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "labels", "screen", "activation", "attachment_delivery", "lifecycle", "review_requirement", "gating", "promotion", "history", "bindings"}
    expected_execution = {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}
    expected_geometry = {"cases_exact": 4, "leaves_per_case_exact": 2, "repeats_exact": 3, "slots_exact": 24, "cells_exact": 8}
    expected_screen = {"prompt_policy": "unchanged_production_prompt", "prompt_paths": ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md"], "schema_path": "schema/hbq_judge_response.schema.json", "renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False, "image_text_substitution_forbidden": True}
    expected_activation = {"mode": "compiled_production_bundle_singleton_v1", "poetry": {"bundle_id": "poetry.free_verse", "artifact_type": "poetry", "scope": "poem"}, "visual": {"bundle_id": "visual.environment", "artifact_type": "visual_asset", "scope": "asset"}}
    expected_attachment_delivery = {"present_stairwell_case": "attach_exact_stairwell_png_bytes_as_image_input", "absent_image_case": "image_input_required_true_with_no_attachment_and_completion_status_complete", "text_substitution": "forbidden"}
    expected_lifecycle = {"policy": "terminal_sidecar_v1", "remote_execution_surface": "absent", "retry_or_resume": "not_authorized_by_freeze"}
    expected_review = {"required_before_execution_successor": True, "reviewer": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "independence": "independent"}, "status": "pending"}
    expected_gating = {"fixture_driven_close": "24_of_24_slots_and_8_of_8_cells_at_3_of_3", "one_of_three": "variance_no_go", "two_of_three": "variance_no_go", "systematic_miss": "any_cell_at_0_of_3_may_authorize_leaf_specific_treatment_design_only"}
    expected_promotion = {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_provider_free_construct_microgate" or contract["development_only"] is not True:
        raise ValueError("Contract identity drifted")
    if contract["provider_execution"] != expected_execution or contract["geometry"] != expected_geometry or contract["labels"] != ["YES", "NO", "CANNOT_ASSESS"] or contract["screen"] != expected_screen or contract["activation"] != expected_activation or contract["attachment_delivery"] != expected_attachment_delivery or contract["lifecycle"] != expected_lifecycle or contract["review_requirement"] != expected_review or contract["gating"] != expected_gating or contract["promotion"] != expected_promotion:
        raise ValueError("Contract policy drifted")
    if contract["history"] != {"earlier_l2_package": "evaluation-results/hbq-other-lexical-overlap-ownership-v1", "disposition": "retained_history_not_replaced"}:
        raise ValueError("Historical retention policy drifted")
    if not (REPOSITORY / contract["history"]["earlier_l2_package"]).is_dir():
        raise ValueError("Earlier L2 fixture history is unavailable")
    verify_corpus(load_corpus())
    verify_ledger(load_ledger())
    if load_ledger()["fixture_binding"]["c03"] != materialize_artifacts()["c03"]["image_fixture"]:
        raise ValueError("Stairwell ledger binding does not match the frozen artifact")
    verify_bindings(contract)
    slots = plan_slots()
    if {row["expected_verdict"] for row in slots} != VERDICTS or len({(row["case_id"], row["leaf_id"]) for row in slots}) != 8:
        raise ValueError("Expected-state or cell geometry drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "cases": 4, "cells": 8, "slots": 24, "image_fixture_bytes": len(stairwell_png_bytes())}


def production_question(leaf_id: str) -> dict[str, Any]:
    return dict(compiled_leaf_records()[leaf_id])


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_type"], "declared_scope": artifact["declared_scope"], "completion_status": artifact["completion_status"], "background": "Public synthetic L2 construct validation.", "constraints": [{"id": "scope", "statement": "Use only the supplied artifact."}, {"id": "image_input", "statement": f"image_input_required={str(artifact['image_input_required']).lower()}"}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


@lru_cache(maxsize=1)
def binary_prompt() -> str:
    return "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))


def provider_request(slot_id: str) -> dict[str, Any]:
    slot = next((row for row in plan_slots() if row["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = materialize_artifacts()[slot["case_id"]]
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt(), artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[production_question(slot["leaf_id"])], task_contract_context=task_context_for(artifact))
    for forbidden in (slot["slot_id"], slot["case_id"], "expected_verdict", "expected-ledger", "systematic_miss"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local ledger metadata")
    image_inputs: list[dict[str, Any]] = []
    if artifact["image_fixture"] == "impossible_stairwell_v1":
        value = stairwell_png_bytes()
        image_inputs.append({"fixture_id": "stairwell-01.png", "mime_type": "image/png", "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest(), "attachment_bytes": value})
    if artifact["image_input_required"] and artifact["image_fixture"] is None and image_inputs:
        raise ValueError("Absent-image control must not attach an image")
    return {"prompt": prompt, "image_inputs": image_inputs}


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    inputs = {slot["slot_id"]: provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(inputs) != 24:
        raise ValueError("All microgate singleton inputs were not rendered")
    return inputs


def public_attachment_record(image_input: Mapping[str, Any]) -> dict[str, Any]:
    return {key: image_input[key] for key in ("fixture_id", "mime_type", "bytes", "sha256")}


def dry_run_report() -> dict[str, Any]:
    report = verify_package()
    inputs = render_all_provider_inputs()
    prompts = {slot_id: hashlib.sha256(request["prompt"].encode("utf-8")).hexdigest() for slot_id, request in inputs.items()}
    return {"mode": "dry_run", "verification": report, "rendered_slots": len(inputs), "attached_image_slots": sum(bool(request["image_inputs"]) for request in inputs.values()), "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(prompts)).hexdigest()}
