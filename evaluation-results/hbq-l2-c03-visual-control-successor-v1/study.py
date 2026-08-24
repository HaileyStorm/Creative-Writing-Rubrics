"""Provider-free freeze and prompt planner for an L2 c03 visual successor."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-l2-construct-microgate-v1"
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs import runner as production_runner

STUDY_ID = "hbq-l2-c03-visual-control-successor-v1"
VISUAL_LEAVES = (
    "form.visual.environment_or_location_illustration.perspective",
    "form.visual.visual_craft_and_artifact_control.perspective",
)
CASE_LEAVES = {case_id: VISUAL_LEAVES for case_id in ("s01", "s02")}
VERDICTS = frozenset(("YES", "NO"))


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
def predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("hbq_l2_construct_microgate_v1_for_c03_successor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Canonical L2 predecessor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def fixture_module() -> Any:
    spec = importlib.util.spec_from_file_location("hbq_l2_c03_structural_planes", ROOT / "assets" / "generate_structural_planes.py")
    if spec is None or spec.loader is None:
        raise ValueError("Structural-plane generator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    required = {"case_id", "artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"}
    expected = {"s01": ("asset-01.png", "structural_plane_incompatible_v1"), "s02": ("asset-02.png", "structural_plane_coherent_v1")}
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    if not isinstance(corpus["cases"], list) or len(corpus["cases"]) != 2:
        raise ValueError("Exactly two visual cases are required")
    observed = set()
    for case in corpus["cases"]:
        if set(case) != required or case["case_id"] in observed or case["case_id"] not in expected:
            raise ValueError("Case identity drifted")
        observed.add(case["case_id"])
        if (case["artifact_name"], case["image_fixture"]) != expected[case["case_id"]] or (case["artifact_type"], case["bundle_id"], case["declared_scope"], case["completion_status"], case["text"], case["image_input_required"]) != ("visual_asset", "visual.environment", "asset", "complete", "", True):
            raise ValueError("Case surface drifted")
    if observed != set(expected):
        raise ValueError("Case membership drifted")


def verify_ledger(ledger: Mapping[str, Any]) -> None:
    expected = {"format_version": 1, "study_id": STUDY_ID, "fixture_binding": {"s01": "structural_plane_incompatible_v1", "s02": "structural_plane_coherent_v1"}, "cells": {"s01": ["NO", "NO"], "s02": ["YES", "YES"]}}
    if ledger != expected:
        raise ValueError("Expected ledger drifted")


def plan_slots() -> list[dict[str, Any]]:
    cells = load_ledger()["cells"]
    slots: list[dict[str, Any]] = []
    for case_id, leaves in CASE_LEAVES.items():
        for leaf_index, leaf_id in enumerate(leaves):
            for repeat in range(1, 4):
                slots.append({"slot_id": f"l2c03-v1-{len(slots) + 1:03d}", "case_id": case_id, "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": cells[case_id][leaf_index]})
    if len(slots) != 12 or len({slot["slot_id"] for slot in slots}) != 12:
        raise ValueError("Singleton slot geometry drifted")
    return slots


def materialize_artifacts() -> dict[str, dict[str, Any]]:
    return {case["case_id"]: dict(case) for case in load_corpus()["cases"]}


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected_contract = {
        "format_version": 1, "study_id": STUDY_ID, "status": "frozen_provider_free_visual_control_successor", "development_only": True,
        "provider_execution": {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True},
        "geometry": {"cases_exact": 2, "leaves_per_case_exact": 2, "repeats_exact": 3, "slots_exact": 12, "cells_exact": 4},
        "labels": ["YES", "NO"],
        "screen": {"renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False, "image_text_substitution_forbidden": True, "presentation_labels_forbidden": True},
        "lifecycle": {"remote_execution_surface": "absent", "retry_or_resume": "not_authorized_by_freeze"},
        "review_requirement": {"required_before_execution_successor": True, "reviewer": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "independence": "independent"}, "status": "satisfied", "reviewed": True, "conclusion": "GO_for_diagnosis_only_execution_successor_design"},
        "gating": {"fixture_diagnosis_only": "12_of_12_slots_and_4_of_4_cells_at_3_of_3", "any_miss": "no_go", "promotion_without_independent_treatment": "none"},
        "promotion": {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"},
        "history": {"earlier_visual_control": "evaluation-results/hbq-l2-construct-microgate-v1", "earlier_disposition": "immutable_no_go_history_not_reused"},
    }
    if {key: contract.get(key) for key in expected_contract} != expected_contract or set(contract) != {*expected_contract, "bindings"}:
        raise ValueError("Contract policy drifted")
    verify_corpus(load_corpus())
    verify_ledger(load_ledger())
    fixtures = fixture_module().fixture_png_bytes()
    expected_bindings = {
        "corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")},
        "expected_ledger": {"path": "expected-ledger.json", "sha256": sha256_file(ROOT / "expected-ledger.json")},
        "fixture_generator": {"path": "assets/generate_structural_planes.py", "sha256": sha256_file(ROOT / "assets" / "generate_structural_planes.py"), "png_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in fixtures.items()}, "pixel_invariants": json.loads(canonical_bytes(fixture_module().pixel_invariants()).decode("utf-8"))},
    }
    if contract["bindings"] != expected_bindings:
        raise ValueError("Frozen source or PNG binding drifted")
    records = predecessor().compiled_leaf_records()
    if tuple(records) != ("form.poetry.free_verse.line_breaks", "form.poetry.free_verse.necessity", *VISUAL_LEAVES):
        raise ValueError("Canonical visual leaves drifted")
    slots = plan_slots()
    if {slot["expected_verdict"] for slot in slots} != VERDICTS or len({(slot["case_id"], slot["leaf_id"]) for slot in slots}) != 4:
        raise ValueError("Expected-state geometry drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "cases": 2, "cells": 4, "slots": 12, "image_fixture_bytes": {name: len(value) for name, value in fixtures.items()}}


def provider_request(slot_id: str) -> dict[str, Any]:
    verify_package()
    slot = next((candidate for candidate in plan_slots() if candidate["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = materialize_artifacts()[slot["case_id"]]
    record = deepcopy(predecessor().production_question(slot["leaf_id"]))
    prompt = production_runner._render_prompt(binary_prompt=predecessor().binary_prompt(), artifact={"name": artifact["artifact_name"], "text": ""}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[record], task_contract_context=predecessor().task_context_for(artifact))
    for forbidden in (slot["slot_id"], slot["case_id"], "expected_verdict", "expected-ledger", "structural_plane_incompatible_v1", "structural_plane_coherent_v1"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked fixture or ledger metadata")
    value = fixture_module().fixture_png_bytes()[artifact["image_fixture"]]
    return {"prompt": prompt, "image_inputs": [{"fixture_id": artifact["artifact_name"], "mime_type": "image/png", "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest(), "attachment_bytes": value}]}


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    inputs = {slot["slot_id"]: provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(inputs) != 12 or not all(len(value["image_inputs"]) == 1 for value in inputs.values()):
        raise ValueError("Visual attachment delivery drifted")
    return inputs


def public_attachment_record(image_input: Mapping[str, Any]) -> dict[str, Any]:
    return {key: image_input[key] for key in ("fixture_id", "mime_type", "bytes", "sha256")}


def dry_run_report() -> dict[str, Any]:
    report = verify_package()
    rendered = render_all_provider_inputs()
    prompts = {slot_id: hashlib.sha256(value["prompt"].encode("utf-8")).hexdigest() for slot_id, value in rendered.items()}
    return {"mode": "dry_run", "verification": report, "rendered_slots": len(rendered), "attached_image_slots": sum(bool(value["image_inputs"]) for value in rendered.values()), "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(prompts)).hexdigest()}
