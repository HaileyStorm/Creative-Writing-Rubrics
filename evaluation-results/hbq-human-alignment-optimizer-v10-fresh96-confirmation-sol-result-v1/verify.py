"""Independently recompute the public V10 Sol-only aggregate result."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = HERE / "result.json"
COLLECTOR_SHA256 = "8f881c2f655cc454764d42a816865c2439f0dfd543742bf4fb083a835a8223b0"
EXECUTOR_COMMIT = "cc59778"
EXECUTOR_SHA256 = "9bd6e8ab7673a379eb6206b8d7c2ff25ce64db3861e85d8d4b649999acc0a248"
ACKNOWLEDGEMENT_SHA256 = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ENDPOINT = "sol_later"
JUDGE = {"provider_attested": False, "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high"}
AUTHORITY = {
    "confirmation": "measurement_only",
    "endpoint_pooling": "forbidden",
    "generalization": "none",
    "promotion": "none",
    "runtime": "none",
    "selection": "none",
    "sol": "measurement_only",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    before = path.lstat()
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe artifact")
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, before.st_size)
    if identity != (opened.st_dev, opened.st_ino, opened.st_size) or identity != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("artifact changed while read")
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
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def load_executor() -> Any:
    path = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-exec-v1" / "executor.py"
    raw = stable(path)
    pinned = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{EXECUTOR_COMMIT}:{path.relative_to(REPO).as_posix()}"],
        capture_output=True,
        check=False,
    )
    if pinned.returncode or sha256(raw) != EXECUTOR_SHA256 or pinned.stdout != raw:
        raise ValueError("pinned Sol executor drifted")
    spec = importlib.util.spec_from_file_location("_v10_sol_result_executor", path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned Sol executor cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if stable(path) != raw:
        raise ValueError("pinned Sol executor changed during load")
    return module


def recompute(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    executor = load_executor()
    replay = executor.replay_collector(
        output_root=Path(output_root),
        freeze_root=Path(freeze_root),
        collector_path=Path(collector_path),
        authorization_acknowledgement_sha256=ACKNOWLEDGEMENT_SHA256,
    )
    raw = stable(Path(collector_path))
    if sha256(raw) != COLLECTOR_SHA256:
        raise ValueError("collector commitment drifted")
    collector = strict(raw, "Sol collector")
    schedule = strict(stable(Path(freeze_root) / "schedule.json"), "frozen schedule")
    cells = collector.get("cells")
    rows = schedule.get("cells")
    if not isinstance(cells, list) or not isinstance(rows, list) or len(cells) != 64 or len(rows) != 64:
        raise ValueError("cell geometry drifted")
    schedule_sha256 = schedule.get("schedule_sha256")
    if not isinstance(schedule_sha256, str) or collector.get("schedule_sha256") != schedule_sha256:
        raise ValueError("schedule commitment drifted")
    if replay.get("native_endpoint_contact_cardinality") != "unproven":
        raise ValueError("native cardinality claim drifted")
    index = {row.get("cell_id"): row for row in rows if isinstance(row, Mapping)}
    if len(index) != 64:
        raise ValueError("schedule cell identity drifted")
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    covered: dict[str, int] = defaultdict(int)
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise TypeError("invalid collector cell")
        row = index.get(cell.get("source_cell_id"))
        projection = cell.get("human_score_projection")
        if not isinstance(row, Mapping) or cell.get("candidate_id") != row.get("candidate_id") or not isinstance(projection, Mapping):
            raise ValueError("collector-to-schedule binding drifted")
        target, scores, coverage = row.get("target"), projection.get("scores"), projection.get("coverage")
        if not all(isinstance(value, Mapping) and set(value) == set(DIMS) for value in (target, scores, coverage)):
            raise ValueError("score projection shape drifted")
        endpoints = row.get("endpoint_payload_sha256s")
        if not isinstance(endpoints, Mapping) or set(endpoints) != {"grok_primary", ENDPOINT} or endpoints[ENDPOINT] != row.get("payload_sha256"):
            raise ValueError("Sol endpoint binding drifted")
        settings, identity = cell.get("effective_settings"), cell.get("identity")
        if isinstance(settings, Mapping):
            observed_judge = {key: settings.get(key) for key in JUDGE}
        elif isinstance(identity, Mapping):
            observed_judge = {
                "provider_attested": identity.get("provider_reported_model") is not None or identity.get("reasoning_attested") is True,
                "requested_model": identity.get("requested_model"),
                "requested_reasoning_effort": identity.get("requested_reasoning_effort"),
            }
        else:
            raise TypeError("Sol judge identity is unavailable")
        if observed_judge != JUDGE:
            raise ValueError("Sol judge identity drifted")
        candidate, group = str(row["candidate_id"]), str(row["prompt_group_id"])
        if candidate not in {BASELINE, CHILD20} or any(type(coverage[dimension]) is not bool for dimension in DIMS):
            raise ValueError("candidate or coverage drifted")
        try:
            groups[candidate][group].append(sum(abs(float(scores[dimension]) - float(target[dimension])) for dimension in DIMS) / len(DIMS))
        except (TypeError, ValueError) as error:
            raise ValueError("numeric score projection drifted") from error
        covered[candidate] += sum(coverage.values())
    metrics = []
    group_mae: dict[str, dict[str, float]] = {}
    for candidate in (BASELINE, CHILD20):
        candidate_groups = groups[candidate]
        if len(candidate_groups) != 16 or any(len(values) != 2 for values in candidate_groups.values()):
            raise ValueError("equal-group geometry drifted")
        group_mae[candidate] = {group: sum(values) / len(values) for group, values in candidate_groups.items()}
        metrics.append({"candidate_id": candidate, "equal_group_mae": sum(group_mae[candidate].values()) / 16})
    baseline, child20 = metrics
    wins = sum(group_mae[CHILD20][group] < group_mae[BASELINE][group] for group in group_mae[BASELINE])
    ties = sum(group_mae[CHILD20][group] == group_mae[BASELINE][group] for group in group_mae[BASELINE])
    return {
        "metrics": metrics,
        "comparison": {
            "baseline_candidate_id": BASELINE,
            "child20_minus_baseline": child20["equal_group_mae"] - baseline["equal_group_mae"],
            "child_candidate_id": CHILD20,
            "relative_reduction": (baseline["equal_group_mae"] - child20["equal_group_mae"]) / baseline["equal_group_mae"],
            "wins_ties_losses": {"child20": wins, "ties": ties, "losses": 16 - wins - ties},
        },
        "coverage": {
            "baseline": {"groups": 16, "items": 32, "score_dimensions_covered": covered[BASELINE], "score_dimensions_total": 192},
            "child20": {"groups": 16, "items": 32, "score_dimensions_covered": covered[CHILD20], "score_dimensions_total": 192},
        },
        "endpoint": ENDPOINT,
        "judge": JUDGE,
        "replay": {
            key: replay[key]
            for key in ("historical_process_launches", "no_resend", "normal_receipt_cells", "process_launches", "provider_calls_made", "reconciled_terminal_cells")
        },
        "source": {
            "authorization_acknowledgement_sha256": ACKNOWLEDGEMENT_SHA256,
            "collector_sha256": sha256(raw),
            "executor_commit": EXECUTOR_COMMIT,
            "executor_sha256": EXECUTOR_SHA256,
            "schedule_sha256": schedule_sha256,
        },
    }


def expected_result(observed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "comparison": observed["comparison"],
        "coverage": observed["coverage"],
        "endpoint": observed["endpoint"],
        "format_version": 1,
        "geometry": {"cells": 64, "dimensions": 6, "groups": 16, "items": 32},
        "judge": observed["judge"],
        "kind": "fresh96_future_confirmation_sol_measurement_only_result",
        "metrics": observed["metrics"],
        "native_endpoint_contact_cardinality": "unproven",
        "replay": observed["replay"],
        "source": observed["source"],
        "study_id": "hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-result-v1",
    }


def verify(**kwargs: Any) -> dict[str, Any]:
    observed = recompute(**kwargs)
    published = strict(stable(RESULT), "published result")
    if published != expected_result(observed):
        raise ValueError("published result envelope drifted")
    return observed
