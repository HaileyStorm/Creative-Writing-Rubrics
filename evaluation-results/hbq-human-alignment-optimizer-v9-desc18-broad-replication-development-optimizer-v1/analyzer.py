#!/usr/bin/env python3
"""Replay open Fresh96 Desc18 receipts and freeze a Grok-primary Sol-veto decision."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-development-optimizer-v1"
EXECUTOR_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1"
EXECUTOR_ROOT = HERE.parent / EXECUTOR_ID
FREEZE_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1"
FREEZE_ROOT = HERE.parent / FREEZE_ID
FREEZE_COMMIT = "83d7be718c99c1135302ccb4f8d339a4c68f292f"
FREEZE_STUDY_SHA256 = "99387d9626ae13f20ef58f0a7f6624ebe850d8477ba17934c4f35735ca9eda16"
FREEZE_CONTRACT_SHA256 = "5115e46f3f8c858e7954ceffa77d2d9dbff3e781f36a5aaf04fb2506c7c07dd2"
FREEZE_SCHEDULE_SHA256 = "1e45510b99e328388ea663ef42523d202322011959ad7f0e62629c3ec8075dfa"
EXECUTOR_COMMIT = "4d3b2ef20f5fad4ea0974e888f37550d4b8480f2"
EXECUTOR_FILES = {
    "README.md": "ebd7397922aa57e043f54f4facf85e0a513020b318c7b56f8aac49a3bc43b0b4",
    "executor.py": "d719d484fabc12110fe36f61c379edf8d15aa701f97f025d1ff2ac24f1d2f4a4",
    "study-contract.json": "43a41a10f2a56e8518bd34fb265a870d55e5d8c58a9227c11f05618b9b50ac77",
    "tests/test_hbq_human_alignment_optimizer_v9_desc18_broad_replication_grok_exec_v1.py": "863498d736128d17af9434f5854f03f6105886a18778415344141c67d3e90613",
}
PARENT = "broader-nextwave-13-missing_evidence_not_no"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CANDIDATES = (PARENT, CHILD)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
WORST_GROUP_WEIGHTS = (0.0, 0.15, 0.30)
STABILITY_WEIGHTS = (0.0, 0.10)
SEED = 202609012
PUBLIC_FILES = {"README.md", "analyzer.py", "study-contract.json"}
AUTHORITY = {
    "confirmation": "unopened",
    "endpoint_pooling": "forbidden",
    "generalization": "none",
    "promotion": "none",
    "runtime": "none",
    "selection": "grok_open_validation_qualification_only_pending_sol_veto",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe or reparsed Desc18 input")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("Desc18 input type drifted")


def stable(path: Path, *, directory: bool = False) -> bytes:
    target = Path(os.path.abspath(path))
    for current in (target, *target.parents):
        _plain(current, directory=current != target or directory)
    before = os.lstat(target)
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode), before.st_size)
    if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size) or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("Desc18 input changed during stable read")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _load_freeze() -> Any:
    path = FREEZE_ROOT / "study.py"
    raw = stable(path)
    if sha256(raw) != FREEZE_STUDY_SHA256:
        raise ValueError("pinned Desc18 freeze study drifted")
    relative = path.relative_to(REPO).as_posix()
    import subprocess

    committed = subprocess.run(["git", "-C", str(REPO), "show", f"{FREEZE_COMMIT}:{relative}"], capture_output=True, check=False)
    if committed.returncode or committed.stdout != raw:
        raise ValueError("Desc18 freeze study is not exact committed bytes")
    spec = importlib.util.spec_from_file_location("_desc18_open_freeze", path)
    if spec is None or spec.loader is None:
        raise ValueError("Desc18 freeze cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if module.STUDY_ID != FREEZE_ID or module.CONTRACT_SHA256 != FREEZE_CONTRACT_SHA256:
        raise ValueError("Desc18 freeze identity drifted")
    return module


def validate_executor_binding() -> None:
    """Require the reviewed executor, contract, README, and regression test at one commit."""
    if len(EXECUTOR_COMMIT) != 40 or set(EXECUTOR_FILES) != {"README.md", "executor.py", "study-contract.json", "tests/test_hbq_human_alignment_optimizer_v9_desc18_broad_replication_grok_exec_v1.py"}:
        raise ValueError("Desc18 executor binding is malformed")
    import subprocess

    for name, digest in EXECUTOR_FILES.items():
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Desc18 executor binding is malformed")
        relative = name if name.startswith("tests/") else (EXECUTOR_ROOT / name).relative_to(REPO).as_posix()
        path = REPO / relative
        raw = stable(path)
        committed = subprocess.run(["git", "-C", str(REPO), "show", f"{EXECUTOR_COMMIT}:{relative}"], capture_output=True, check=False)
        if committed.returncode or committed.stdout != raw or sha256(raw) != digest:
            raise ValueError("Desc18 executor binding drifted or is not committed")


def reconstruct_open_targets(freeze_root: Path) -> dict[str, Any]:
    """Rebuild the public/open schedule and its targets; never accept caller metrics."""
    freeze = _load_freeze()
    schedule = freeze.validate_frozen_root(Path(freeze_root))
    if schedule != freeze.materialize() or schedule.get("schedule_sha256") != FREEZE_SCHEDULE_SHA256:
        raise ValueError("persisted Fresh96 open schedule differs from frozen reconstruction")
    expected_geometry = {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}
    if schedule.get("geometry") != expected_geometry or schedule.get("study_id") != FREEZE_ID:
        raise ValueError("Fresh96 open schedule geometry drifted")
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 64:
        raise ValueError("Fresh96 open schedule cell inventory drifted")
    pairs = {(row.get("candidate_id"), row.get("item_id")) for row in cells if isinstance(row, Mapping)}
    groups = {row.get("prompt_group_id") for row in cells if isinstance(row, Mapping)}
    if pairs != {(candidate, row.get("item_id")) for candidate in CANDIDATES for row in cells if isinstance(row, Mapping) and row.get("candidate_id") == PARENT} or len(groups) != 16:
        raise ValueError("Fresh96 candidate or prompt-group pairing drifted")
    targets: dict[str, dict[str, float]] = {}
    for row in cells:
        if not isinstance(row, Mapping) or row.get("partition") != "open_validation_development":
            raise ValueError("confirmation/private partition leakage")
        raw = base64.b64decode(row.get("payload_base64", ""), validate=True)
        if sha256(raw) != row.get("payload_sha256"):
            raise ValueError("Fresh96 payload binding drifted")
        rendered = raw.decode("utf-8").lower()
        if any(marker in rendered for marker in ("future_confirmation", "private-freeze", "c:/users/", "\\\\users\\\\")):
            raise ValueError("private partition leakage")
        target = row.get("target")
        if not isinstance(target, Mapping) or set(target) != set(DIMENSIONS):
            raise ValueError("Fresh96 target shape drifted")
        values = {name: target[name] for name in DIMENSIONS}
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values.values()):
            raise ValueError("Fresh96 target value drifted")
        existing = targets.setdefault(str(row["item_id"]), {name: float(values[name]) for name in DIMENSIONS})
        if existing != {name: float(values[name]) for name in DIMENSIONS}:
            raise ValueError("mixed target identity")
    if len(targets) != 32:
        raise ValueError("Fresh96 target cardinality drifted")
    return schedule


def _native_scores(raw: bytes) -> tuple[dict[str, float], dict[str, bool]]:
    response = strict(raw, "native Grok response")
    structured = response.get("structuredOutput")
    if not isinstance(structured, Mapping) or set(structured) != {"coverage", "evidence", "scores"}:
        raise ValueError("native Grok structured response drifted")
    scores, coverage, evidence = structured["scores"], structured["coverage"], structured["evidence"]
    if not isinstance(scores, Mapping) or set(scores) != set(DIMENSIONS) or not isinstance(coverage, Mapping) or set(coverage) != set(DIMENSIONS) or not isinstance(evidence, Mapping) or set(evidence) != set(DIMENSIONS):
        raise ValueError("native Grok response field drifted")
    values = {name: scores[name] for name in DIMENSIONS}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= float(value) <= 5 for value in values.values()):
        raise ValueError("invalid, all-zero, or out-of-scale native scores")
    if all(float(value) == 0.0 for value in values.values()) or any(type(coverage[name]) is not bool for name in DIMENSIONS):
        raise ValueError("invalid native coverage")
    for item in evidence.values():
        if not isinstance(item, str):
            raise TypeError("schema-invalid native evidence")
        normalized = " ".join(item.split()).casefold()
        if (not normalized or normalized in {"x", "n/a", "na", "none", "missing", "redacted", "[placeholder]", "placeholder"}
                or "placeholder" in normalized
                or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", normalized)
                or re.search(r"\bworkspace (?:search|lookup)\b", normalized)
                or normalized.startswith(("file:", "source:", "http:", "https:", "\\\\", "/", "./", "../", "see attached", "see workspace", "workspace:", "path:"))):
            raise ValueError("placeholder native evidence")
    return ({name: float(values[name]) for name in DIMENSIONS}, {name: coverage[name] for name in DIMENSIONS})


def _project(schedule: Mapping[str, Any], collector: Mapping[str, Any]) -> dict[str, Any]:
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 64:
        raise ValueError("Fresh96 schedule is incomplete")
    index = {row.get("cell_id"): row for row in cells if isinstance(row, Mapping)}
    if len(index) != 64:
        raise ValueError("duplicate Fresh96 schedule cell")
    required_collector = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    supplied = collector.get("cells")
    if (set(collector) != required_collector or collector.get("format_version") != 1 or collector.get("study_id") != EXECUTOR_ID or collector.get("kind") != "complete_64_desc18_open_validation_grok_receipts_cardinality_unproven" or collector.get("schedule_sha256") != schedule.get("schedule_sha256") or collector.get("native_endpoint_contact_cardinality") != "unproven" or collector.get("provider_calls_made") is not None or collector.get("process_launches") != 64 or not isinstance(supplied, list) or len(supplied) != 64):
        raise ValueError("64-cell native collector or caller aggregate surface drifted")
    required_entry = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
    observations: dict[str, dict[str, list[tuple[str, float]]]] = {candidate: defaultdict(list) for candidate in CANDIDATES}
    coverage_false: dict[str, list[dict[str, str]]] = {candidate: [] for candidate in CANDIDATES}
    identities: set[tuple[str, str]] = set()
    seen: set[str] = set()
    for entry in supplied:
        if not isinstance(entry, Mapping) or set(entry) != required_entry:
            raise ValueError("native collector cell fields drifted")
        cell_id = entry.get("cell_id")
        row = index.get(cell_id)
        if not isinstance(cell_id, str) or cell_id in seen or not isinstance(row, Mapping):
            raise ValueError("duplicate or misassociated native collector cell")
        try:
            request = base64.b64decode(entry["native_request_base64"], validate=True)
            response = base64.b64decode(entry["native_response_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("native receipt encoding drifted") from error
        if (entry.get("payload_base64") != row.get("payload_base64") or entry.get("payload_sha256") != row.get("payload_sha256") or entry.get("native_request_sha256") != sha256(request) or entry.get("native_response_sha256") != sha256(response) or entry.get("effective_settings_sha256") != sha256(entry.get("effective_settings"))):
            raise ValueError("native receipt/payload binding drifted")
        identity, settings = entry.get("identity"), entry.get("effective_settings")
        if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or identity.get("provider") != "xai" or identity.get("requested_model") != "grok-4.6" or identity.get("reported_model") != "grok-4.6-build" or identity.get("tools_enabled") is not False or settings.get("tools_enabled") is not False:
            raise ValueError("native provider identity or tool-free settings drifted")
        native_id = (identity.get("request_id"), identity.get("session_id"))
        if not all(isinstance(value, str) and value for value in native_id) or native_id in identities:
            raise ValueError("duplicate or absent native identity")
        scores, coverage = _native_scores(response)
        target = row.get("target")
        if not isinstance(target, Mapping) or set(target) != set(DIMENSIONS):
            raise ValueError("independent Fresh96 target binding drifted")
        candidate, item, group = str(row["candidate_id"]), str(row["item_id"]), str(row["prompt_group_id"])
        observations[candidate][group].append((item, sum(abs(scores[name] - float(target[name])) for name in DIMENSIONS) / len(DIMENSIONS)))
        coverage_false[candidate].extend({"dimension": name, "item_id": item, "prompt_group_id": group} for name in DIMENSIONS if not coverage[name])
        identities.add(native_id)
        seen.add(cell_id)
    if seen != set(index):
        raise ValueError("partial native collector cannot be analyzed")
    expected: dict[str, set[str]] = defaultdict(set)
    for row in cells:
        expected[str(row["prompt_group_id"])].add(str(row["item_id"]))
    metrics = []
    for candidate in CANDIDATES:
        if set(observations[candidate]) != set(expected):
            raise ValueError("candidate lacks an open prompt group")
        group_mae: dict[str, float] = {}
        for group, items in expected.items():
            rows = observations[candidate][group]
            if len(rows) != len(items) or {item for item, _value in rows} != items:
                raise ValueError("partial or duplicated group cannot be imputed")
            group_mae[group] = sum(value for _item, value in rows) / len(rows)
        ordered = dict(sorted(group_mae.items()))
        metrics.append({"candidate_id": candidate, "cells": 32, "equal_group_mae": sum(ordered.values()) / 16, "group_mae": ordered, "coverage_false": sorted(coverage_false[candidate], key=lambda row: (row["item_id"], row["dimension"]))})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "desc18_open_fresh96_equal_group_projection", "authority": AUTHORITY, "claim": "GROK_OPEN_VALIDATION_DEVELOPMENT_ONLY; 32 item MAEs are averaged within 16 frozen public/open prompt groups, then groups are weighted equally. No endpoint pooling, confirmation, promotion, runtime, or general claim follows.", "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 64, "provider_calls_made": None}, "metrics": metrics}


def objective(metric: Mapping[str, Any], worst_weight: float, stability_weight: float) -> float:
    values = tuple(float(value) for value in metric["group_mae"].values())
    mean = float(metric["equal_group_mae"])
    return mean + worst_weight * (max(values) - mean) + stability_weight * sum(abs(value - mean) for value in values) / len(values)


def run_optuna(metrics: list[Mapping[str, Any]]) -> dict[str, Any]:
    import optuna

    by_id = {str(row["candidate_id"]): row for row in metrics}
    if set(by_id) != set(CANDIDATES):
        raise ValueError("optimizer candidate geometry drifted")
    grid = {"candidate_id": list(CANDIDATES), "worst_group_weight": list(WORST_GROUP_WEIGHTS), "stability_weight": list(STABILITY_WEIGHTS)}
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.GridSampler(grid, seed=SEED))

    def evaluate(trial: Any) -> float:
        return objective(by_id[trial.suggest_categorical("candidate_id", list(CANDIDATES))], float(trial.suggest_categorical("worst_group_weight", list(WORST_GROUP_WEIGHTS))), float(trial.suggest_categorical("stability_weight", list(STABILITY_WEIGHTS))))

    study.optimize(evaluate, n_trials=12)
    if len(study.trials) != 12 or any(trial.state.name != "COMPLETE" for trial in study.trials):
        raise ValueError("Optuna GridSampler did not complete the frozen grid")
    records = sorted(({"candidate_id": str(trial.params["candidate_id"]), "objective": float(trial.value), "stability_weight": float(trial.params["stability_weight"]), "worst_group_weight": float(trial.params["worst_group_weight"])} for trial in study.trials), key=lambda row: (row["worst_group_weight"], row["stability_weight"], row["candidate_id"]))
    settings = []
    for worst in WORST_GROUP_WEIGHTS:
        for stability in STABILITY_WEIGHTS:
            setting = {row["candidate_id"]: row["objective"] for row in records if row["worst_group_weight"] == worst and row["stability_weight"] == stability}
            if set(setting) != set(CANDIDATES):
                raise ValueError("incomplete Optuna robustness setting")
            settings.append({"worst_group_weight": worst, "stability_weight": stability, "objective_by_candidate": dict(sorted(setting.items()))})
    return {"library": f"optuna@{optuna.__version__}", "sampler": "GridSampler", "seed": SEED, "completed_trials": 12, "settings": settings, "trial_records_sha256": sha256(records)}


def qualify(metrics: list[Mapping[str, Any]], optimizer: Mapping[str, Any]) -> dict[str, Any]:
    by_id = {str(row["candidate_id"]): row for row in metrics}
    parent, child = by_id.get(PARENT), by_id.get(CHILD)
    settings = optimizer.get("settings")
    if parent is None or child is None or not isinstance(settings, list) or len(settings) != 6:
        raise ValueError("qualification geometry drifted")
    raw_better = child["equal_group_mae"] < parent["equal_group_mae"]
    no_worse = all(isinstance(row, Mapping) and set(row.get("objective_by_candidate", {})) == set(CANDIDATES) and float(row["objective_by_candidate"][CHILD]) <= float(row["objective_by_candidate"][PARENT]) for row in settings)
    qualifiers = [CHILD] if raw_better and no_worse else []
    return {"assessments": [{"candidate_id": CHILD, "raw_equal_group_mae": child["equal_group_mae"], "raw_equal_group_mae_strictly_below_parent": raw_better, "no_worse_than_parent_all_six_robustness_settings": no_worse, "qualifies_for_sol_veto": bool(qualifiers)}], "frozen_before_sol": True, "parent_candidate_id": PARENT, "parent_equal_group_mae": parent["equal_group_mae"], "qualifiers": qualifiers, "rule": "child20 raw equal-group MAE strictly below descendant13 AND objective no worse in every one of six frozen robustness settings", "sol_veto": {"calls_made": 0, "eligible_candidates": qualifiers, "role": "veto_only_no_sol_favored_substitution", "status": "pending_for_frozen_qualifiers" if qualifiers else "not_required_no_qualifiers"}, "development_decision": "freeze_child20_pending_sol_veto" if qualifiers else "retain_descendant13_zero_sol_calls"}


def build_dspy_evidence(metrics: list[Mapping[str, Any]], qualification: Mapping[str, Any]) -> dict[str, Any]:
    import dspy

    class ReplayedDesc18Evidence(dspy.Signature):
        candidate_id: str = dspy.InputField()
        group_mae_json: str = dspy.InputField()
        equal_group_mae: float = dspy.OutputField()

    examples = [dspy.Example(candidate_id=row["candidate_id"], group_mae_json=canonical(row["group_mae"]).decode("utf-8"), equal_group_mae=row["equal_group_mae"]).with_inputs("candidate_id", "group_mae_json") for row in metrics]
    return {"evidence_chain_sha256": sha256([example.toDict() for example in examples]), "evidence_examples": len(examples), "library": f"dspy@{dspy.__version__}", "lm_calls": 0, "predict_calls": 0, "proposal_generated": False, "qualifiers_frozen_before_sol": list(qualification["qualifiers"]), "signature": ReplayedDesc18Evidence.__name__}


def replay_projection(*, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    validate_executor_binding()
    schedule = reconstruct_open_targets(Path(freeze_root))
    collector_raw = stable(Path(collector_path))
    collector = strict(collector_raw, "64-cell Desc18 collector")
    projection = _project(schedule, collector)
    projection["source_execution"] = {"collector_sha256": sha256(collector_raw), "executor_binding": {"commit": EXECUTOR_COMMIT, "files": dict(sorted(EXECUTOR_FILES.items())), "status": "exact_committed"}, "frozen_schedule_sha256": FREEZE_SCHEDULE_SHA256, "schedule_sha256": schedule["schedule_sha256"]}
    projection["projection_sha256"] = sha256(projection)
    return projection


def analyze(*, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    projection = replay_projection(freeze_root=freeze_root, collector_path=collector_path)
    metrics = projection["metrics"]
    optimizer = run_optuna(metrics)
    qualification = qualify(metrics, optimizer)
    dspy_evidence = build_dspy_evidence(metrics, qualification)
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "desc18_open_fresh96_replication_optimizer_and_sol_veto_freeze", "source": {"collector_sha256": projection["source_execution"]["collector_sha256"], "executor_binding": projection["source_execution"]["executor_binding"], "projection_sha256": projection["projection_sha256"]}, "geometry": {"candidates": 2, "open_validation_groups": 16, "open_validation_items": 32, "grok_cells": 64, "optuna_trials": 12, "sol_cells_executed": 0, "confirmation_cells": 0}, "metrics": metrics, "optimizer": optimizer, "qualification": qualification, "dspy_evidence": dspy_evidence, "authority": {"confirmation": {"cells": 0, "status": "unopened"}, "promotion": "none", "runtime": "none", "selection": qualification["development_decision"], "sol": "veto_only_pending" if qualification["qualifiers"] else "not_required_zero_calls"}, "claim": "This public/open Fresh96 development replay freezes child20 only if it improves raw prompt-group-equal MAE over descendant13 and is no worse under all six frozen robustness settings. Sol may veto a frozen qualifier but cannot substitute a Sol-favored candidate. No confirmation, promotion, runtime, pooled-endpoint, or general claim follows."}
    result["result_sha256"] = sha256(result)
    return result


def _contract() -> dict[str, Any]:
    return {"authority": {"confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_open_validation_qualification_only", "sol": "veto_only"}, "executor_binding": "committed_exact_executor_contract_readme_test_hashes", "format_version": 1, "geometry": {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "optuna_grid_settings": 6}, "kind": "provider_free_desc18_open_fresh96_replication_optimizer", "pinned_executor": {"commit": EXECUTOR_COMMIT, "files": dict(sorted(EXECUTOR_FILES.items())), "study_id": EXECUTOR_ID}, "pinned_freeze": {"commit": FREEZE_COMMIT, "schedule_sha256": FREEZE_SCHEDULE_SHA256, "study_contract_sha256": FREEZE_CONTRACT_SHA256, "study_sha256": FREEZE_STUDY_SHA256}, "qualification_rule": {"raw_equal_group_mae": "child20_strictly_below_descendant13", "robustness": "child20_no_worse_than_descendant13_in_all_six_settings", "sol": "freeze_child20_before_sol_then_veto_only", "zero_qualifiers": "retain_descendant13_and_make_zero_sol_calls"}, "runtime_dependencies": {"dspy": "development_only_zero_lm_calls", "optuna": "development_only_grid_sampler", "production": "none"}, "study_id": STUDY_ID}


def validate_package() -> dict[str, Any]:
    _plain(HERE, directory=True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("Desc18 optimizer package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "Desc18 study contract")
    if contract != _contract():
        raise ValueError("Desc18 optimizer contract drifted")
    validate_executor_binding()
    return contract


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("Desc18 result output must be a fresh plain file")
    raw = canonical(dict(result))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with os.fdopen(os.open(target, flags, 0o600), "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if stable(target) != raw:
        raise ValueError("Desc18 result write drifted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--collector-path", type=Path, required=True)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv)
    validate_package()
    result = analyze(freeze_root=args.freeze_root, collector_path=args.collector_path)
    if args.result_output is not None:
        write_result(args.result_output, result)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
