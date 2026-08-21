"""Offline contract validator for the AI-writer/preface experiments."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
CURRENT_PREFIX = ROOT / "prompts" / "judge" / "JUDGE_PREFIX.md"
ARM_IDS = ("none", "current_full", "strictness_only")
STAGES = (("pilot", 4), ("development", 12), ("holdout", 24))
NETWORK_IMPORTS = frozenset({"httpx", "requests", "socket", "subprocess", "urllib"})
CURRENT_PREFIX_INFO = {"path": "prompts/judge/JUDGE_PREFIX.md", "bytes": 1191, "sha256": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74"}
EXPECTED_ASSET_HASHES = {
    "current_judge_prefix": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "strictness_only": "1474f9aaf75da2a83dcf9e16cadac7f1dae7621c76b1ed1ef85e496358ebe375",
    "writer_identity_reminder": "9a48fade33280c1ed302c3b8bb9c41e5e8becefa43f940da39bde3684de5383e",
    "writer_dont_hold_back": "00cb0e36570127d24f8ff6f4feb9bd86bf6d7f174648f4379b43bdfe863a229c",
}
STRICTNESS_PLACEMENT = "Immediately before the unchanged binary-evaluation prompt; no other judge input moves."
EXPECTED_A_ARMS = (
    {"id": "none", "prefix": "", "placement": "No comparable prefix is inserted."},
    {"id": "current_full", "prefix_asset": "current_judge_prefix", "placement": "Immediately before the unchanged binary-evaluation prompt."},
    {"id": "strictness_only", "prefix_asset": "strictness_only", "placement": "Immediately before the unchanged binary-evaluation prompt."},
)
A_PAIR_DEFINITION = "One frozen input evaluated under every arm, with two independent fresh sessions in each arm."
A_ESTIMANDS = [
    "Within each actual-origin level, current_full minus strictness_only measures the current AI-framed preface package against origin-neutral strictness.",
    "The difference of those two within-level effects estimates whether declared AI framing has a different effect for actually AI-written versus non-AI-written text.",
    "none contrasts are descriptive preface-presence controls; A does not claim to isolate the AI sentence from the production strictness clause.",
]
PRIMARY_OUTCOMES = [
    "canonical leaf flips", "dimension and overall score shifts", "coverage shifts", "same-input repeatability", "confidence shifts", "HANNA-overlap Kendall tau-b and Spearman", "actual-origin-stratified and actual-by-declared interaction estimates",
]
EXPECTED_ORIGIN_LEVELS = {"ai_written": {"pilot": 2, "development": 6, "holdout": 12}, "non_ai_written": {"pilot": 2, "development": 6, "holdout": 12}}
EXPECTED_DECLARED_ORIGIN = {"none": "no_declaration", "current_full": "ai_stated", "strictness_only": "origin_neutral"}
HUMAN_RATINGS_POLICY = "Published HANNA ratings are read and analyzed offline only. No rating, label, source text, or request is sent to a human or paid evaluation route."
CONFIDENCE_POLICY = "Confidence is diagnostic only. It never changes canonical aggregation or coverage in this study."
BLIND_GRADING = "Downstream judges receive no writer-arm name, stated writer identity, or actual provenance label."
WRITER_IDENTITY_PLACEMENT = "After the unchanged writer role/context scaffold and before project materials."
WRITER_DONT_HOLD_BACK_PLACEMENT = "After any identity-reminder treatment and before project materials."
EXPECTED_CROSSOVER = {
    "purpose": "Resolve a reproduced judge-preface signal without retrofitting Experiment A.",
    "design": "2x2 crossover: exact production declared-AI-origin sentence absent/present by exact production strictness clause absent/present; heading and all other production-prefix bytes stay fixed.",
    "production_reconstruction": "The present/present cell byte-reconstructs the current production prefix. No paraphrase or literal do-not-hold-back bridge is used.",
    "estimands": "Within actual-origin and source-model strata, estimate the exact declared-origin sentence effect at each strictness level, the exact strictness-clause effect at each declared-origin level, their interaction, and whether each differs by actual origin.",
    "entry_gate": "Only after Experiment A's development signal reproduces in its pilot and development stages; freeze a successor before any call.",
    "no_auto_execution": True,
}
FRAGMENT_LAYOUT = {
    "constant_opening": (0, 40, "370b06f93c67190943462209385ca7717d1fd0800eb3fa42312a590492c5811a"),
    "declared_ai_origin": (40, 111, "83036efe9a6c4e373b818a404a1bfa77590d6ebdabd558a986af6a263dd57819"),
    "origin_strictness_separator": (111, 112, "36a9e7f1c95b82ffb99743e0c5c4ce95d83c9a430aac59f84ef3cbfab6145068"),
    "strictness_clause": (112, 371, "2ba5ff2976d253c2a2b5c9591bc32ba1b8a5f97065fca5a2cc41f0c0a7a71155"),
    "constant_suffix": (371, 1191, "95b369249eb95e9f95c1ea0d67fe10625c776c34a613d8ae34759870e5a16b5a"),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_contract() -> dict[str, Any]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Invalid study contract") from error
    if not isinstance(contract, dict):
        raise ValueError("Study contract must be an object")
    validate_contract(contract)
    return contract


def _asset_text(contract: Mapping[str, Any], name: str) -> str:
    asset = contract["bound_assets"][name]
    if not isinstance(asset, Mapping) or not isinstance(asset.get("text"), str):
        raise ValueError(f"Missing text asset: {name}")
    return str(asset["text"])


def bound_asset_fingerprints(contract: Mapping[str, Any] | None = None) -> dict[str, str]:
    value = load_contract() if contract is None else contract
    return {
        "current_judge_prefix": sha256_path(CURRENT_PREFIX),
        "strictness_only": sha256_bytes(_asset_text(value, "strictness_only").encode("utf-8")),
        "writer_identity_reminder": sha256_bytes(_asset_text(value, "writer_identity_reminder").encode("utf-8")),
        "writer_dont_hold_back": sha256_bytes(_asset_text(value, "writer_dont_hold_back").encode("utf-8")),
    }


def planned_judge_cells(contract: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = load_contract() if contract is None else contract
    levels = value["provenance"]["actual_origin_levels"]
    cells: list[dict[str, Any]] = []
    for stage, pairs in STAGES:
        level_pairs = [(level, counts[stage]) for level, counts in levels.items()]
        if sum(count for _, count in level_pairs) != pairs:
            raise ValueError("Actual-origin allocation does not match judge geometry")
        pair = 0
        for actual_origin, count in level_pairs:
            for _ in range(count):
                pair += 1
                for arm in ARM_IDS:
                    for session in (1, 2):
                        cells.append({"stage": stage, "pair": pair, "actual_origin": actual_origin, "arm": arm, "fresh_session": session})
    if len(cells) != 240:
        raise ValueError("Judge geometry drifted")
    return cells


def _validate_fragments(assets: Mapping[str, Any]) -> None:
    fragments = assets.get("production_prefix_fragments")
    expected_keys = {"source", *FRAGMENT_LAYOUT, "rendering"}
    if not isinstance(fragments, Mapping) or set(fragments) != expected_keys or fragments.get("source") != "current_judge_prefix":
        raise ValueError("Production-prefix decomposition drifted")
    raw = CURRENT_PREFIX.read_bytes()
    for name, (start, end, expected_hash) in FRAGMENT_LAYOUT.items():
        if fragments.get(name) != {"byte_range": [start, end], "sha256": expected_hash} or sha256_bytes(raw[start:end]) != expected_hash:
            raise ValueError(f"Production-prefix fragment drifted: {name}")
    if fragments.get("rendering") != "constant_opening + optional declared_ai_origin + optional origin_strictness_separator only when both factors are present + optional strictness_clause + constant_suffix":
        raise ValueError("Production-prefix rendering policy drifted")
    if raw[0:40] + raw[40:111] + raw[111:112] + raw[112:371] + raw[371:1191] != raw:
        raise ValueError("Production-prefix fragments no longer reconstruct current bytes")


def validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {"format_version", "study_id", "status", "frozen_before_execution", "scope", "bound_assets", "shared_judge_inputs", "provenance", "human_ratings_policy", "experiments", "outcomes", "batch_and_polarity", "model_policy", "decision_policy", "limitations"}
    if set(contract) != expected or contract.get("format_version") != 1 or contract.get("study_id") != "hbq-ai-writer-preface-v1":
        raise ValueError("Study identity drifted")
    if contract.get("status") != "preregistered_protocol_only_no_provider_or_human_execution" or contract.get("frozen_before_execution") is not True:
        raise ValueError("Study must remain frozen and execution-free")
    assets = contract["bound_assets"]
    if not isinstance(assets, Mapping) or assets.get("current_judge_prefix") != CURRENT_PREFIX_INFO:
        raise ValueError("Current-prefix binding drifted")
    if sha256_path(CURRENT_PREFIX) != CURRENT_PREFIX_INFO["sha256"] or CURRENT_PREFIX.stat().st_size != CURRENT_PREFIX_INFO["bytes"]:
        raise ValueError("Current-prefix bytes drifted")
    if set(assets["strictness_only"]) != {"text", "sha256", "placement", "removes"} or assets["strictness_only"].get("placement") != STRICTNESS_PLACEMENT or assets["strictness_only"].get("removes") != ["AI-origin declaration", "protect-the-system-feelings instruction"]:
        raise ValueError("Strictness-only mapping drifted")
    strictness = _asset_text(contract, "strictness_only")
    if any(token in strictness.lower() for token in (" ai", "feelings", "protect the system")):
        raise ValueError("Strictness control leaks origin or feelings language")
    for name, actual_hash in bound_asset_fingerprints(contract).items():
        declared_hash = CURRENT_PREFIX_INFO["sha256"] if name == "current_judge_prefix" else assets[name].get("sha256")
        if declared_hash != EXPECTED_ASSET_HASHES[name] or actual_hash != EXPECTED_ASSET_HASHES[name]:
            raise ValueError(f"Bound asset hash drifted: {name}")
    _validate_fragments(assets)
    experiment_a = contract["experiments"].get("A_judge_preface")
    if not isinstance(experiment_a, Mapping) or tuple(experiment_a.get("arms", ())) != EXPECTED_A_ARMS or [(stage.get("name"), stage.get("pairs")) for stage in experiment_a.get("stages", []) if isinstance(stage, Mapping)] != list(STAGES):
        raise ValueError("Judge-arm mapping or stage geometry drifted")
    if experiment_a.get("session_rule") != "Two independent fresh sessions per input per arm; equal calls and no outcome-dependent retries or stopping.":
        raise ValueError("Fresh-session parity drifted")
    if experiment_a.get("pair_definition") != A_PAIR_DEFINITION:
        raise ValueError("Matched-pair same-text definition drifted")
    if experiment_a.get("estimands") != A_ESTIMANDS:
        raise ValueError("Actual-origin interaction estimand drifted")
    provenance = contract["provenance"]
    if provenance.get("actual") != "Internal selection and matching label. It is never sent as a judge disclosure token." or provenance.get("declared") != "A treatment-controlled prompt statement, distinct from actual provenance." or provenance.get("matching") != ["actual provenance is matched across every arm of an input", "source-model strata are balanced within each phase and actual-origin level", "the same frozen input is used across that input's judge arms"] or provenance.get("eligible_corpus") != "Only existing HANNA corpus items with verified pre-existing actual-origin and source-model evidence are eligible. Exclude unknown, inferred, or newly solicited provenance." or provenance.get("actual_origin_levels") != EXPECTED_ORIGIN_LEVELS or provenance.get("declared_origin_by_A_arm") != EXPECTED_DECLARED_ORIGIN:
        raise ValueError("Actual/declared provenance policy drifted")
    if contract.get("human_ratings_policy") != HUMAN_RATINGS_POLICY:
        raise ValueError("HANNA outbound boundary drifted")
    writer = contract["experiments"].get("B_writer_preface")
    if not isinstance(writer, Mapping) or writer.get("blind_grading") != BLIND_GRADING:
        raise ValueError("Blind downstream grading drifted")
    if set(assets["writer_identity_reminder"]) != {"text", "sha256", "placement"} or assets["writer_identity_reminder"].get("placement") != WRITER_IDENTITY_PLACEMENT or set(assets["writer_dont_hold_back"]) != {"text", "sha256", "placement"} or assets["writer_dont_hold_back"].get("placement") != WRITER_DONT_HOLD_BACK_PLACEMENT:
        raise ValueError("Writer-treatment mapping drifted")
    if contract["experiments"].get("C_crossover") != EXPECTED_CROSSOVER:
        raise ValueError("Conditional crossover decomposition drifted")
    if contract["outcomes"].get("primary") != PRIMARY_OUTCOMES:
        raise ValueError("Actual-origin interaction outcome drifted")
    if contract["outcomes"].get("confidence") != CONFIDENCE_POLICY:
        raise ValueError("Confidence weighting is forbidden")
    if contract["batch_and_polarity"] != {"status": "deferred_targeted_interaction_only", "rule": "Test only the 27 HANNA-overlap leaves, only at sizes already validated on at least one module stack, and only in a separately frozen successor."}:
        raise ValueError("Batch/polarity boundary drifted")
    if contract.get("model_policy") != "GPT-5.6 is primary. Every other model, runtime, prompt rendering, and provider fingerprint is analyzed separately and cannot be pooled into its estimate.":
        raise ValueError("Model-separation policy drifted")
    planned_judge_cells(contract)


def execution_surface() -> str:
    return "forbidden: this package validates a protocol and has no provider, writer, or human-evaluation executor"


def execute() -> None:
    raise RuntimeError("This preregistration cannot make provider calls or execute an evaluation")
