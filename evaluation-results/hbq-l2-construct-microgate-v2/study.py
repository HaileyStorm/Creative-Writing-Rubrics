"""Provider-free freeze and prompt planner for the L2 construct microgate v2."""
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

STUDY_ID = "hbq-l2-construct-microgate-v2"
LINE_BREAKS = "form.poetry.free_verse.line_breaks"
NECESSITY = "form.poetry.free_verse.necessity"
POETRY_LEAVES = (LINE_BREAKS, NECESSITY)
VISUAL_LEAVES = (
    "form.visual.environment_or_location_illustration.perspective",
    "form.visual.visual_craft_and_artifact_control.perspective",
)
CASE_LEAVES = {**{case_id: POETRY_LEAVES for case_id in ("p01", "p02", "p03", "p04")}, "c03": VISUAL_LEAVES, "c04": VISUAL_LEAVES}
CANDIDATE_TEXT = "Does each supplied line break make a controlled, legible contribution to rhythm, syntax, emphasis, image, ambiguity, or pace?"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
PREDECESSOR_HASHES = {
    "README.md": "bb9730ae39f4bba93246fead492d43b0ad0277367100178962668b09787c8872",
    "public-synthetic-corpus.json": "bafbfa4b5860b43ba4d28aa1268380c36339167e2503d94498ce26bfe8e85681",
    "expected-ledger.json": "b7db8890ea1184ca86cd693fbc9161e0658d83e9bdc3064d5aaf7f965e621065",
    "study-contract.json": "53833245c8740db30dcc7bd8cccc5c647321d2ce84904a8b29e63b170d24c829",
    "study.py": "1c07a14715f6c40daf4eb2f067261fe7be25d0fb162f538c39815baf3bbacc72",
    "run.py": "957c75649e0fb51969a1ff149d0c04b51d68907a4254157fd4e5f23478c9d241",
    "assets/generate_geometry_fixture.py": "2a9bfcd505be18928a2c0dd795cfcb40133df8ce65586883b58b7d523b1576f2",
}
ACTIVE_RUNTIME_HASHES = {
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
    "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
    "registry/all_modules.json": "4da342cc24881c70be11e5e2cd92a7beccbeb024e5808a5c779935f29989a4ed",
    "bundles/all_bundles.jsonl": "18fe55b796b2809f9b8fe3b8cfbc9ef672d990141c79839cf291b6ace7308f5f",
    "registry/criterion_ownership.json": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876",
    "registry/question_index.jsonl": "0de8eec70a5a4de74770570253af96f6483c07fcf00ebad198fe951cf2af1fb6",
}
COMPILED_LEAF_HASHES = {
    "form.poetry.free_verse.line_breaks": "3f116cec873adbd329445f2312201355086dabcd8742b0d000402a0022058d0c",
    "form.poetry.free_verse.necessity": "a8c36e24125ba32db2694051252a5c17e9fc05abe48cd185f014b7b2a704e0eb",
    "form.visual.environment_or_location_illustration.perspective": "54d9fe2f3c2ca408579182aac4fb24f14a47c326081ec2787f381b957989e52b",
    "form.visual.visual_craft_and_artifact_control.perspective": "e460ad109be2a1d2cb5a13fcb58ca5ad3cc55b87a158fcc6a7757763bade44bf",
}
FAILED_EXECUTION = {
    "execution_checkout_commit": "608025bf2c230aae594b9ed3b75371cc0a6267e3",
    "failed_root_manifest_study_source_commit": "a711c856e33516d4cc1f29fac889a802143623a8",
    "root_basename": "cwr-l2-v2-final-608025b-20260824-01a02ca3",
    "execution_claim_sha256": "3dbe81d2e1f75fb9ae16a934c4df933cf0b6a5ea5fcd35ebbf9b3a78b1f60dcc",
    "accepted_slots": 6,
    "slot_7": {"relative_attempt_path": "runs/l2microexec-v2-007/attempts/attempt-01", "receipt_sha256": "e28ae2e046f0dc5debf366b81aae2657ed653ad544043c2502879fbc6fd37191", "terminal_sidecar_sha256": "5f8e668f8060ac405b67610c4f85573e154f6370ed38c73f6a62bbf52aa8189c", "response_sha256": "8422011443b9583406a3a2a1372640b318fc6de54bdf6dce223dc79c68b98803", "provider_verdict": "NOT_APPLICABLE", "local_enum": ["YES", "NO", "CANNOT_ASSESS"], "disposition": "schema_valid_response_rejected_by_local_three_state_enum"},
    "later_slots_blocked_before_dispatch": 17,
    "rubric_result": "none",
    "aggregate": "none",
    "settlement": "none",
    "non_voting": True,
}
HISTORY = {
    "predecessor_package": "evaluation-results/hbq-l2-construct-microgate-v1",
    "predecessor_ledger": "evaluation-results/hbq-l2-construct-microgate-v1/expected-ledger.json",
    "predecessor_disposition": "immutable_historical_provenance",
    "failed_execution": FAILED_EXECUTION,
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


@lru_cache(maxsize=1)
def predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("hbq_l2_construct_microgate_v1_pinned", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Pinned predecessor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_predecessor() -> None:
    if not PREDECESSOR_ROOT.is_dir():
        raise ValueError("Pinned predecessor package is unavailable")
    actual = {name: sha256_file(PREDECESSOR_ROOT / name) for name in PREDECESSOR_HASHES}
    if actual != PREDECESSOR_HASHES:
        raise ValueError("Pinned predecessor provenance drifted")
    if predecessor().load_ledger() != {
        "format_version": 2,
        "study_id": "hbq-l2-construct-microgate-v1",
        "fixture_binding": {"c03": "impossible_stairwell_v1"},
        "cells": {"c01": ["YES", "YES"], "c02": ["NO", "NO"], "c03": ["NO", "NO"], "c04": ["CANNOT_ASSESS", "CANNOT_ASSESS"]},
    }:
        raise ValueError("Pinned predecessor ledger drifted")


def verify_active_bindings() -> None:
    verify_predecessor()
    runtime = {path: sha256_file(REPOSITORY / path) for path in ACTIVE_RUNTIME_HASHES}
    if runtime != ACTIVE_RUNTIME_HASHES:
        raise ValueError("Active runtime provenance drifted")
    if predecessor().source_leaf_hashes() != COMPILED_LEAF_HASHES:
        raise ValueError("Compiled source leaf provenance drifted")


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    expected = {
        "p01": ("poem-01.txt", "I step\noff the last stair\nand keep\nfalling\nlong after\nthe floor.", False, None),
        "p02": ("artifact-02.txt", "On Tuesday I carried the\nblue folder from the front\ndesk to the back office and\nplaced it beside the copier\nbefore lunch.", False, None),
        "p03": ("artifact-03.txt", "On Tuesday I carried the blue folder from the front desk to the back office and placed it beside the copier before lunch.", False, None),
        "p04": ("poem-04.txt", "I crossed the floor\nand closed the door.", False, None),
        "c03": ("asset-03.png", "", True, "impossible_stairwell_v1"),
        "c04": ("asset-04.png", "", True, None),
    }
    required = {"case_id", "artifact_name", "artifact_type", "bundle_id", "declared_scope", "completion_status", "text", "image_input_required", "image_fixture"}
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != 6:
        raise ValueError("Exactly six microgate cases are required")
    observed_ids = set()
    for case in cases:
        if set(case) != required or case["case_id"] in observed_ids or case["case_id"] not in expected:
            raise ValueError("Case identity drifted")
        observed_ids.add(case["case_id"])
        artifact_type = "poetry" if case["case_id"].startswith("p") else "visual_asset"
        bundle_id = "poetry.free_verse" if artifact_type == "poetry" else "visual.environment"
        scope = "poem" if artifact_type == "poetry" else "asset"
        if (case["artifact_name"], case["text"], case["image_input_required"], case["image_fixture"]) != expected[case["case_id"]] or (case["artifact_type"], case["bundle_id"], case["declared_scope"], case["completion_status"]) != (artifact_type, bundle_id, scope, "complete"):
            raise ValueError("Case surface drifted")
    if observed_ids != set(expected) or "\\n" in expected["p01"][1] or expected["p01"][1].count("\n") != 5:
        raise ValueError("Lineation fixture drifted")


def verify_ledger(ledger: Mapping[str, Any]) -> None:
    expected = {
        "p01": ["YES", "YES"], "p02": ["NO", "NO"], "p03": ["NOT_APPLICABLE", "NO"],
        "p04": ["YES", "NO"], "c03": ["NO", "NO"],
        "c04": ["CANNOT_ASSESS", "CANNOT_ASSESS"],
    }
    if ledger != {"format_version": 1, "study_id": STUDY_ID, "fixture_binding": {"c03": "impossible_stairwell_v1"}, "cells": expected}:
        raise ValueError("Four-state expected ledger drifted")
    if {verdict for values in expected.values() for verdict in values} != VERDICTS:
        raise ValueError("Four-state ledger membership drifted")


def materialize_artifacts(corpus: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    corpus = load_corpus() if corpus is None else corpus
    return {case["case_id"]: dict(case) for case in corpus["cases"]}


def canonical_question(leaf_id: str) -> dict[str, Any]:
    return deepcopy(predecessor().production_question(leaf_id))


def question_for(leaf_id: str) -> dict[str, Any]:
    record = canonical_question(leaf_id)
    if leaf_id != LINE_BREAKS:
        return record
    baseline = deepcopy(record)
    record["question"]["text"] = CANDIDATE_TEXT
    candidate = deepcopy(record)
    candidate["question"]["text"] = baseline["question"]["text"]
    if candidate != baseline:
        raise ValueError("Candidate override changed more than question.text")
    return record


def verify_candidate_override(contract: Mapping[str, Any]) -> None:
    expected = {"leaf_id": LINE_BREAKS, "field": "question.text", "text": CANDIDATE_TEXT, "registry_promotion": "none"}
    if contract["candidate_override"] != expected or contract["canonical_control"] != {"leaf_id": NECESSITY, "registry_text": "unchanged"}:
        raise ValueError("Candidate-only override policy drifted")
    if question_for(LINE_BREAKS)["question"]["text"] != CANDIDATE_TEXT or question_for(NECESSITY) != canonical_question(NECESSITY):
        raise ValueError("Candidate-only override implementation drifted")


def plan_slots() -> list[dict[str, Any]]:
    ledger = load_ledger()["cells"]
    rows: list[dict[str, Any]] = []
    for case_id, leaves in CASE_LEAVES.items():
        for leaf_index, leaf_id in enumerate(leaves):
            for repeat in range(1, 4):
                rows.append({"slot_id": f"l2micro-v2-{len(rows) + 1:03d}", "case_id": case_id, "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": ledger[case_id][leaf_index]})
    if len(rows) != 36 or len({row["slot_id"] for row in rows}) != 36:
        raise ValueError("Microgate slot geometry drifted")
    return rows


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected_keys = {"format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "labels", "candidate_override", "canonical_control", "screen", "lifecycle", "promotion", "history", "bindings"}
    if set(contract) != expected_keys or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_provider_free_candidate_line_breaks_microgate" or contract["development_only"] is not True:
        raise ValueError("Contract identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True} or contract["geometry"] != {"cases_exact": 6, "leaves_per_case_exact": 2, "repeats_exact": 3, "slots_exact": 36, "cells_exact": 12} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]:
        raise ValueError("Contract geometry drifted")
    if contract["screen"] != {"renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False, "image_text_substitution_forbidden": True} or contract["lifecycle"] != {"remote_execution_surface": "absent", "retry_or_resume": "not_authorized_by_freeze"} or contract["promotion"] != {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"}:
        raise ValueError("Contract policy drifted")
    if contract["history"] != HISTORY:
        raise ValueError("Historical provenance policy drifted")
    expected_bindings = {"corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}, "expected_ledger": {"path": "expected-ledger.json", "sha256": sha256_file(ROOT / "expected-ledger.json")}, "predecessor": PREDECESSOR_HASHES, "active_runtime": ACTIVE_RUNTIME_HASHES, "compiled_source_leaves": COMPILED_LEAF_HASHES}
    if contract["bindings"] != expected_bindings:
        raise ValueError("Package binding drifted")
    verify_active_bindings()
    verify_corpus(load_corpus())
    verify_ledger(load_ledger())
    verify_candidate_override(contract)
    slots = plan_slots()
    if len({(row["case_id"], row["leaf_id"]) for row in slots}) != 12 or {row["expected_verdict"] for row in slots} != VERDICTS:
        raise ValueError("Cell geometry drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "cases": 6, "cells": 12, "slots": 36, "image_fixture_bytes": len(predecessor().stairwell_png_bytes())}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return predecessor().task_context_for(artifact)


def _provider_request(slot_id: str) -> dict[str, Any]:
    slot = next((row for row in plan_slots() if row["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = materialize_artifacts()[slot["case_id"]]
    prompt = production_runner._render_prompt(binary_prompt=predecessor().binary_prompt(), artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id=artifact["bundle_id"], artifact_id="public-synthetic-artifact", questions=[question_for(slot["leaf_id"])], task_contract_context=task_context_for(artifact))
    for forbidden in (slot["slot_id"], slot["case_id"], "expected_verdict", "expected-ledger", "non_voting_diagnostic"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local metadata")
    image_inputs: list[dict[str, Any]] = []
    if artifact["image_fixture"] == "impossible_stairwell_v1":
        value = predecessor().stairwell_png_bytes()
        image_inputs.append({"fixture_id": "stairwell-01.png", "mime_type": "image/png", "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest(), "attachment_bytes": value})
    if artifact["image_input_required"] and artifact["image_fixture"] is None and image_inputs:
        raise ValueError("Absent-image control must not attach an image")
    return {"prompt": prompt, "image_inputs": image_inputs}


def provider_request(slot_id: str) -> dict[str, Any]:
    verify_active_bindings()
    return _provider_request(slot_id)


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    verify_active_bindings()
    inputs = {slot["slot_id"]: _provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(inputs) != 36:
        raise ValueError("All singleton inputs were not rendered")
    return inputs


def public_attachment_record(image_input: Mapping[str, Any]) -> dict[str, Any]:
    return {key: image_input[key] for key in ("fixture_id", "mime_type", "bytes", "sha256")}


def dry_run_report() -> dict[str, Any]:
    report = verify_package()
    inputs = render_all_provider_inputs()
    prompts = {slot_id: hashlib.sha256(request["prompt"].encode("utf-8")).hexdigest() for slot_id, request in inputs.items()}
    return {"mode": "dry_run", "verification": report, "rendered_slots": len(inputs), "attached_image_slots": sum(bool(request["image_inputs"]) for request in inputs.values()), "prompt_aggregate_sha256": hashlib.sha256(canonical_bytes(prompts)).hexdigest()}
