"""Provider-free L2 lexical-overlap freeze and production prompt planner."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping
from functools import lru_cache

from hbqrs import runner as production_runner


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-other-lexical-overlap-ownership-v1"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
FINDING_IDS = (
    "338b510127809018cc8f14b2674e5960ac6bb70d8692e7af300d74a3eab0ed80",
    "984e94e56c811360f817c98f76022d74e2c399454dec8874078bc70e59198bc4",
    "ff3c0acd77e9eae45b077e6ffe458c8c7b34e00fac6606f1e581d5a37755cb9a",
)
BLOCK_LEAVES = {
    "free_verse_form_scope": ("form.poetry.free_verse.necessity", "scope.poetry_poem.form"),
    "prose_poem_image_relation": ("form.poetry.general_poetry.image_relation", "form.poetry.prose_poem.image_system"),
    "visual_perspective": ("form.visual.environment_or_location_illustration.perspective", "form.visual.visual_craft_and_artifact_control.perspective"),
}
MODULE_PATHS = {
    "form.poetry.free_verse.necessity": "registry/modules/form.poetry.free_verse.yaml",
    "scope.poetry_poem.form": "registry/modules/scope.poetry_poem.yaml",
    "form.poetry.general_poetry.image_relation": "registry/modules/form.poetry.general_poetry.yaml",
    "form.poetry.prose_poem.image_system": "registry/modules/form.poetry.prose_poem.yaml",
    "form.visual.environment_or_location_illustration.perspective": "registry/modules/form.visual.environment_or_location_illustration.yaml",
    "form.visual.visual_craft_and_artifact_control.perspective": "registry/modules/form.visual.visual_craft_and_artifact_control.yaml",
}
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", *MODULE_PATHS.values(),
    "registry/question_index.jsonl", "registry/criterion_ownership.json", "src/hbqrs/runner.py",
)
SCORING = {
    "applicable_cells": "must_be_3_of_3_expected_with_grounded_typed_evidence",
    "not_applicable": "completed_unscored",
    "cannot_assess": "coverage_uncertainty",
    "missing_or_ambiguous_slot": "INCOMPLETE",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def load_asset_manifest() -> dict[str, Any]:
    return load_json(ROOT / "assets" / "fixture-manifest.json")


def source_leaf_records() -> dict[str, dict[str, Any]]:
    leaves = {leaf for pair in BLOCK_LEAVES.values() for leaf in pair}
    records: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in leaves:
            records[row["id"]] = {key: row[key] for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity")}
    if set(records) != leaves:
        raise ValueError("Canonical source leaves are unavailable")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in source_leaf_records().items()}


def materialize_artifacts(corpus: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    corpus = load_corpus() if corpus is None else corpus
    artifacts: list[dict[str, Any]] = []
    for block in corpus["blocks"]:
        for condition in block["conditions"]:
            for carrier in ("isolated", "composite"):
                contexts = [] if carrier == "isolated" else [{"name": "context-01.txt", "text": "Public synthetic matched-carrier control; no additional artistic evidence."}]
                artifacts.append({
                    "case_id": f"{block['block_id']}-{condition['condition_id']}-{carrier}",
                    "block_id": block["block_id"], "finding_id": block["finding_id"], "bundle_id": block["bundle_id"],
                    "carrier": carrier, "artifact_type": block["artifact_type"], "leaves": tuple(block["leaves"]),
                    "artifact_name": condition["artifact_name"], "completion_status": condition["completion_status"], "text": condition.get("text", ""), "contexts": contexts,
                    "image_fixture": condition.get("image_fixture"), "expected": dict(zip(block["leaves"], condition["expected"], strict=True)),
                })
    return artifacts


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "blocks"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    blocks = corpus["blocks"]
    if not isinstance(blocks, list) or len(blocks) != 3:
        raise ValueError("Three paired blocks are required")
    seen_ids, labels = set(), set()
    for block in blocks:
        required = {"block_id", "finding_id", "bundle_id", "artifact_type", "leaves", "conditions"}
        if set(block) != required or block["block_id"] not in BLOCK_LEAVES or block["block_id"] in seen_ids or block["finding_id"] not in FINDING_IDS or tuple(block["leaves"]) != BLOCK_LEAVES[block["block_id"]]:
            raise ValueError("Block identity or exact leaf pairing drifted")
        seen_ids.add(block["block_id"])
        if not isinstance(block["conditions"], list) or len(block["conditions"]) != 6:
            raise ValueError("Each block requires six semantic conditions")
        condition_ids = set()
        for condition in block["conditions"]:
            base = {"condition_id", "artifact_name", "completion_status", "expected"}
            if block["block_id"] == "visual_perspective":
                base.add("image_fixture")
            else:
                base.add("text")
            if set(condition) != base or not isinstance(condition["condition_id"], str) or condition["condition_id"] in condition_ids or not isinstance(condition["artifact_name"], str) or not isinstance(condition["completion_status"], str) or condition["completion_status"] not in {"complete", "unknown"} or not isinstance(condition["expected"], list) or len(condition["expected"]) != 2 or not set(condition["expected"]) <= VERDICTS:
                raise ValueError("Condition surface or verdict ledger drifted")
            condition_ids.add(condition["condition_id"])
            labels.update(condition["expected"])
            if block["block_id"] == "visual_perspective":
                if not isinstance(condition["image_fixture"], str) or "text" in condition:
                    raise ValueError("Visual condition must bind an image, not an image description")
            elif not isinstance(condition["text"], str) or not condition["text"].strip():
                raise ValueError("Text condition is malformed")
        expected = {"both-yes", "form-only", "scope-only", "both-no", "coverage-ablation", "inactive-control"} if block["block_id"] == "free_verse_form_scope" else None
        if expected is not None and condition_ids != expected:
            raise ValueError("Free-verse semantic condition set drifted")
    if seen_ids != set(BLOCK_LEAVES) or labels != VERDICTS:
        raise ValueError("Four-state coverage or block set drifted")
    artifacts = materialize_artifacts(corpus)
    if len(artifacts) != 36 or len({item["case_id"] for item in artifacts}) != 36:
        raise ValueError("Matched-carrier artifact geometry drifted")
    for block_id in BLOCK_LEAVES:
        members = [item for item in artifacts if item["block_id"] == block_id]
        for condition_id in {item["case_id"].rsplit("-", 1)[0] for item in members}:
            pair = [item for item in members if item["case_id"].rsplit("-", 1)[0] == condition_id]
            if len(pair) != 2 or {item["carrier"] for item in pair} != {"isolated", "composite"} or pair[0]["expected"] != pair[1]["expected"]:
                raise ValueError("Matched carrier pairing drifted")
    free = {item["case_id"]: item["expected"] for item in artifacts if item["block_id"] == "free_verse_form_scope" and item["carrier"] == "isolated"}
    if ("YES", "NO") not in {tuple(item.values()) for item in free.values()} or ("NO", "YES") not in {tuple(item.values()) for item in free.values()}:
        raise ValueError("Free-verse block must expose both asymmetric directions")
    prose = [tuple(item["expected"].values()) for item in artifacts if item["block_id"] == "prose_poem_image_relation" and item["carrier"] == "isolated"]
    if prose.count(("YES", "NOT_APPLICABLE")) != 1 or any(values in {("YES", "NO"), ("NO", "YES")} for values in prose):
        raise ValueError("Prose-image routing-oracle constraint drifted")
    visual = [tuple(item["expected"].values()) for item in artifacts if item["block_id"] == "visual_perspective"]
    if any(left != right for left, right in visual):
        raise ValueError("Visual block may not manufacture cross-leaf opposite verdicts")


def verify_assets(contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    asset_binding = contract["bindings"]["assets"]
    manifest_path = ROOT / asset_binding["manifest_path"]
    if sha256_file(manifest_path) != asset_binding["manifest_sha256"] or sha256_file(ROOT / "assets" / "generate_visual_fixtures.py") != asset_binding["generator_sha256"]:
        raise ValueError("Frozen visual fixture binding drifted")
    manifest = load_json(manifest_path)
    if manifest.get("generator") != "assets/generate_visual_fixtures.py" or manifest.get("generator_sha256") != asset_binding["generator_sha256"]:
        raise ValueError("Visual fixture generator provenance drifted")
    fixtures = {item["fixture_id"]: item for item in manifest.get("fixtures", [])}
    if set(fixtures) != {condition["image_fixture"] for block in load_corpus()["blocks"] if block["block_id"] == "visual_perspective" for condition in block["conditions"]}:
        raise ValueError("Visual fixture membership drifted")
    generator_spec = importlib.util.spec_from_file_location("l2_visual_fixture_generator", ROOT / "assets" / "generate_visual_fixtures.py")
    generator = importlib.util.module_from_spec(generator_spec)
    assert generator_spec and generator_spec.loader
    generator_spec.loader.exec_module(generator)
    for fixture in fixtures.values():
        path = ROOT / fixture["path"]
        generated = generator.png_bytes(fixture["fixture_id"])
        if fixture.get("mime_type") != "image/png" or not path.is_file() or path.read_bytes() != generated or generated[:8] != b"\x89PNG\r\n\x1a\n" or sha256_file(path) != fixture["sha256"] or path.stat().st_size != fixture["bytes"]:
            raise ValueError("Visual fixture bytes or MIME contract drifted")
    return fixtures


def verify_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    if bindings["corpus"] != {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}:
        raise ValueError("Public synthetic corpus binding drifted")
    if bindings["runtime"] != {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}:
        raise ValueError("Current production runtime binding drifted")
    if bindings["source_leaves"] != source_leaf_hashes():
        raise ValueError("Exact current leaf binding drifted")
    ownership = load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    records = source_leaf_records()
    expected = {leaf: {"module_id": records[leaf]["module_id"], "question_id": leaf} for leaf in records}
    if {leaf: ownership.get(leaf) for leaf in records} != expected:
        raise ValueError("Criterion ownership invariant drifted")
    portfolio = contract["portfolio_binding"]
    manifest_path = REPOSITORY / portfolio["manifest_path"]
    if sha256_file(manifest_path) != portfolio["manifest_sha256"]:
        raise ValueError("Frozen L2 portfolio binding drifted")
    package = next((item for item in load_json(manifest_path)["packages"] if item["package_id"] == "L2"), None)
    if not package or package["finding_ids"] != portfolio["finding_ids"] or package["initial_calls_exact"] != portfolio["frozen_initial_slots_exact"]:
        raise ValueError("Exact L2 finding membership or call geometry drifted")
    verify_assets(contract)


@lru_cache(maxsize=1)
def verified_assets() -> dict[str, dict[str, Any]]:
    return verify_assets(load_contract())


def plan_slots() -> list[dict[str, Any]]:
    slots = []
    for artifact in materialize_artifacts():
        for leaf_id in artifact["leaves"]:
            for repeat in range(1, 4):
                slots.append({"slot_id": f"l2-v1-{len(slots)+1:03d}", "case_id": artifact["case_id"], "block_id": artifact["block_id"], "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": artifact["expected"][leaf_id]})
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "portfolio_binding", "geometry", "labels", "screen", "image_delivery", "scoring", "promotion", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_development_only_current_wording_screen" or contract["development_only"] is not True:
        raise ValueError("Contract identity or status drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True} or contract["geometry"] != {"blocks_exact": 3, "semantic_conditions_per_block_exact": 6, "matched_carriers_exact": 2, "leaves_per_block_exact": 2, "repeats_exact": 3, "slots_exact": 216} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"] or contract["scoring"] != SCORING:
        raise ValueError("Provider, geometry, label, or scoring contract drifted")
    if contract["screen"] != {"name": "current_wording", "prompt_policy": "unchanged_production_prompt", "prompt_paths": ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md"], "schema_path": "schema/hbq_judge_response.schema.json", "renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False}:
        raise ValueError("Production prompt/schema/renderer contract drifted")
    if contract["image_delivery"] != {"visual_block_id": "visual_perspective", "fixture_manifest_path": "assets/fixture-manifest.json", "generator_path": "assets/generate_visual_fixtures.py", "input_contract": "attach_exact_png_bytes_as_image_input", "text_substitution_forbidden": True, "execution_successor_required": True}:
        raise ValueError("Image-input delivery contract drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Promotion boundary drifted")
    verify_corpus(load_corpus())
    verify_bindings(contract)
    slots = plan_slots()
    if len(slots) != 216 or len({slot["slot_id"] for slot in slots}) != 216 or {slot["expected_verdict"] for slot in slots} != VERDICTS:
        raise ValueError("Singleton slot ledger drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "artifacts": 36, "slots": 216, "visual_png_inputs": 6}


def production_question(leaf_id: str) -> dict[str, Any]:
    record = source_leaf_records()[leaf_id]
    return {"question": {"id": leaf_id, **record, "evidence_policy": {"required": True, "minimum_references": 1, "reference_style": "artifact span, unit ID, timestamp, or source ID"}}, "module_id": record["module_id"], "domain_id": None, "role": "core"}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_type"], "declared_scope": "current synthetic artifact only", "completion_status": artifact["completion_status"], "background": "Public synthetic current-wording validation.", "constraints": [{"id": "carrier", "statement": "Use only supplied artifact and contexts."}, {"id": "image_input", "statement": "image_input_required=true" if artifact["image_fixture"] else "image_input_required=false"}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def provider_request(slot_id: str) -> dict[str, Any]:
    slot = next((item for item in plan_slots() if item["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = next(item for item in materialize_artifacts() if item["case_id"] == slot["case_id"])
    binary_prompt = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt, artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=artifact["contexts"], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[production_question(slot["leaf_id"])], task_contract_context=task_context_for(artifact))
    for forbidden in (slot_id, artifact["finding_id"], "expected_verdict", "oracle", "condition_id"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local ledger metadata")
    inputs: list[dict[str, str]] = []
    if artifact["image_fixture"]:
        fixture = verified_assets()[artifact["image_fixture"]]
        inputs = [{"path": fixture["path"], "mime_type": fixture["mime_type"], "sha256": fixture["sha256"]}]
        if artifact["text"]:
            raise ValueError("Visual PNG must not be replaced with textual image content")
    return {"prompt": prompt, "image_inputs": inputs}


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    inputs = {slot["slot_id"]: provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(inputs) != 216:
        raise ValueError("All singleton inputs were not rendered")
    return inputs
