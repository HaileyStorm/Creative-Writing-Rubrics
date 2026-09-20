"""Provider-free selected100 Sol validation after a frozen Grok DEV choice."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
GROK_ANALYSIS_PATH = ROOT / "baseline_grok_successor_analysis.py"
SELECTED_ENGINE_PATH = ROOT / "baseline_selected_analysis_runtime.py"
SOL_REPLAY_PATH = ROOT / "sol_selected_collection_replay.py"

PUBLIC_INPUTS_SHA256 = "6254f58d3366667c9578e2661a1ca0d105a603a0f8affe2d925a767957937c42"
DEV_TARGETS_SHA256 = "d9071d48465faf7beb37b249b5120e33645a3bc0925aec7856402d75fc2d35b5"
SELECTED_SCHEDULE_SHA256 = "2836a81d26836274440318338b395a04dad51a80f7d339ca0612f8135dc0e82f"
SELECTED_SCHEDULE_SOURCE_SHA256 = "20b38d4f14415d2e61da4cc01c002aa82662814ea451e2d83133a1161b971e41"

SOL_REPLAY_SOURCE_SHA256 = "e3430d8808f3b6a36f9d421efc40db1d550a40fb34e7666c2b5fb020becbe715"
SOL_REPLAY_RECEIPT_SHA256 = "fc70eb43be0608e787eeb877b0d42bb81cc08efe47646c8759f69c5f3c57613f"
SOL_CAMPAIGN_MANIFEST_SHA256 = "66d4f52f7b8ed19fd7ce805cb937eec4f30ff887be8cf7d32624fad0a190f5f6"
SOL_COLLECTION_RESULT_SHA256 = "bbc48b02e2ed17977bd3c8b2900aa58656484dbd5503a3116c8f96905383d140"

GROK_REPLAY_KEYS = frozenset(
    {
        "reader_inputs",
        "public_inputs_path",
        "expected_public_inputs_sha256",
        "dev_targets_path",
        "fit_path",
        "train_freeze_path",
        "dev_comparison_path",
        "dev_freeze_path",
        "expected_fit_sha256",
        "expected_train_freeze_sha256",
        "expected_dev_comparison_sha256",
        "expected_dev_freeze_sha256",
        "source_pins",
        "scoring_inputs",
    }
)
SOL_REPLAY_KEYS = frozenset(
    {
        "campaign_root",
        "expected_campaign_manifest_sha256",
        "expected_collection_result_sha256",
        "expected_composer_sha256",
    }
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _hash(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _read(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, f"{label} expected hash"):
        raise ValueError(f"{label} hash drift")
    return checked, raw


def _strict_json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{label} has duplicate keys")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error


def _load_pinned(path: Path, expected: str, label: str) -> ModuleType:
    checked, raw = _read(path, expected, label)
    spec = importlib.util.spec_from_loader(
        f"_dryad_selected_sol_{label.replace(' ', '_')}_{uuid.uuid4().hex}",
        loader=None,
    )
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(checked)
    exec(compile(raw, str(checked), "exec"), module.__dict__)  # noqa: S102 - exact pinned local source.
    if checked.read_bytes() != raw:
        raise ValueError(f"{label} changed while loading")
    return module


def _descriptor(path: Path | str, raw: bytes) -> dict[str, Any]:
    return {"path": str(Path(path).resolve()), "sha256": _sha(raw), "bytes": len(raw)}


def _mapping(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{label} keys differ")
    return dict(value)


def _output_preflight(path: Path | str, protected: Sequence[Path | str]) -> Path:
    output = Path(os.path.abspath(path)).resolve()
    if output.exists():
        raise ValueError("Selected Sol validation output must be fresh")
    roots = [ROOT.parents[1]]
    for item in protected:
        checked = Path(os.path.abspath(item)).resolve()
        roots.append(checked.parent if checked.is_file() else checked)
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots):
        raise ValueError("Selected Sol validation output overlaps protected input")
    return output


def _write(output: Path, artifacts: Mapping[str, bytes]) -> dict[str, str]:
    staging = output.with_name(f".{output.name}.staging-{uuid.uuid4().hex}")
    try:
        staging.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            with (staging / name).open("xb") as stream:
                stream.write(raw)
        reported = {name: _sha((staging / name).read_bytes()) for name in artifacts}
        if any((staging / name).read_bytes() != raw for name, raw in artifacts.items()):
            raise ValueError("Selected Sol validation artifact changed while writing")
        staging.replace(output)
        return reported
    except Exception as error:
        raise RuntimeError(f"Selected Sol validation staging retained at {staging}") from error


def _protected_paths(grok: ModuleType, grok_kwargs: Mapping[str, Any]) -> list[Path | str]:
    reader_inputs = grok_kwargs["reader_inputs"]
    scoring_inputs = grok_kwargs["scoring_inputs"]
    try:
        values = grok._protected_inputs(reader_inputs, scoring_inputs)
    except (AttributeError, TypeError, ValueError):
        values = (
            reader_inputs.get("plan_root"),
            reader_inputs.get("predecessor_path"),
            reader_inputs.get("old_suffix_root"),
            reader_inputs.get("recovery_root"),
            *(item.get("root") for item in reader_inputs.get("successor_roots", []) if isinstance(item, Mapping)),
            scoring_inputs.get("scoring_manifest_path"),
            scoring_inputs.get("v5_runtime_manifest_path"),
            scoring_inputs.get("v5_runtime_package_root"),
        )
    result = [item for item in values if item]
    runtime_data = reader_inputs.get("runtime_data")
    if isinstance(runtime_data, Mapping):
        descriptors = [runtime_data.get("context_adapter"), runtime_data.get("snapshot_manifest"), runtime_data.get("prefix_adapter")]
        bindings = runtime_data.get("source_bindings")
        if isinstance(bindings, Mapping):
            descriptors.extend(bindings.values())
        result.extend(item.get("path") for item in descriptors if isinstance(item, Mapping) and item.get("path"))
    return result


def _sol_rows(result: Mapping[str, Any], binding: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = result.get("endpoint_sol_rows")
    if not isinstance(rows, list) or len(rows) != 100:
        raise ValueError("Selected Sol replay must contain 100 rows")
    train_ids = binding.get("TRAIN")
    dev_ids = binding.get("DEV")
    if not isinstance(train_ids, list) or not isinstance(dev_ids, list):
        raise ValueError("Frozen selected binding lacks TRAIN/DEV IDs")  # noqa: TRY004 - persisted contract errors use ValueError.
    expected = {"TRAIN": set(train_ids), "DEV": set(dev_ids)}
    seen: set[str] = set()
    normalized: dict[str, list[dict[str, Any]]] = {"TRAIN": [], "DEV": []}
    question_ids: list[str] | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Selected Sol row is malformed")  # noqa: TRY004 - persisted contract errors use ValueError.
        story = row.get("original_opaque_story_id")
        partition = row.get("partition")
        verdicts = row.get("canonical_verdicts")
        if type(story) is not str or not story or story in seen or partition not in normalized:
            raise ValueError("Selected Sol row identity differs")
        if story not in expected[partition]:
            raise ValueError("Selected Sol row is outside the frozen selection")
        if not isinstance(verdicts, list) or len(verdicts) != 178:
            raise ValueError("Selected Sol row verdict count differs")
        coverage = row.get("coverage")
        if partition == "DEV" and (
            isinstance(coverage, bool)
            or not isinstance(coverage, (int, float))
            or coverage < 0.88
        ):
            raise ValueError("Selected Sol DEV coverage failure")
        ids: list[str] = []
        checked: list[dict[str, str]] = []
        for verdict in verdicts:
            if not isinstance(verdict, Mapping) or set(verdict) != {"question_id", "verdict"}:
                raise ValueError("Selected Sol verdict shape differs")
            question_id, value = verdict.get("question_id"), verdict.get("verdict")
            if type(question_id) is not str or not question_id or value not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}:
                raise ValueError("Selected Sol verdict value differs")
            ids.append(question_id)
            checked.append({"question_id": question_id, "verdict": value})
        if question_ids is None:
            question_ids = ids
        elif ids != question_ids:
            raise ValueError("Selected Sol question order differs")
        normalized[partition].append({"opaque_story_id": story, "verdicts": checked})
        seen.add(story)
    for partition in ("TRAIN", "DEV"):
        normalized[partition].sort(key=lambda item: item["opaque_story_id"])
        if {item["opaque_story_id"] for item in normalized[partition]} != expected[partition]:
            raise ValueError("Selected Sol partition inventory differs")
    failures = result.get("qualification_failures")
    if not isinstance(failures, list) or len(failures) != 2:
        raise ValueError("Selected Sol coverage-failure inventory differs")
    row_by_pass = {row.get("pass_id"): row for row in rows}
    for failure in failures:
        if not isinstance(failure, Mapping) or failure.get("reason") != "coverage_below_0.88":
            raise ValueError("Selected Sol coverage-failure record differs")
        source = row_by_pass.get(failure.get("pass_id"))
        if not isinstance(source, Mapping) or source.get("partition") != "TRAIN" or source.get("coverage", 1) >= 0.88:
            raise ValueError("Selected Sol coverage failure is not a retained TRAIN failure")
    return normalized["TRAIN"], normalized["DEV"], [dict(item) for item in failures]


def validate_selected_successor_sol(
    *,
    grok_replay_kwargs: Mapping[str, Any],
    sol_replay_kwargs: Mapping[str, Any],
    sol_replay_receipt_path: Path | str,
    output_root: Path | str,
) -> dict[str, Any]:
    """Validate the selected Sol DEV endpoint against a frozen selected100 Grok choice."""
    grok_kwargs = _mapping(grok_replay_kwargs, GROK_REPLAY_KEYS, "Grok replay kwargs")
    sol_kwargs = _mapping(sol_replay_kwargs, SOL_REPLAY_KEYS, "Sol replay kwargs")
    if grok_kwargs["expected_public_inputs_sha256"] != PUBLIC_INPUTS_SHA256:
        raise ValueError("Selected public-input hash differs")
    if sol_kwargs["expected_composer_sha256"] != SOL_REPLAY_SOURCE_SHA256:
        raise ValueError("Selected Sol replay source differs")
    receipt_path, receipt_raw = _read(sol_replay_receipt_path, SOL_REPLAY_RECEIPT_SHA256, "Selected Sol replay receipt")

    source_pins = grok_kwargs["source_pins"]
    if not isinstance(source_pins, Mapping):
        raise ValueError("Grok source pins differ")  # noqa: TRY004 - persisted contract errors use ValueError.
    analysis = _load_pinned(GROK_ANALYSIS_PATH, source_pins["analysis"], "Grok successor analysis")
    sol_root = Path(sol_kwargs["campaign_root"]).resolve()
    protected = _protected_paths(analysis, grok_kwargs)
    protected.extend(
        [
            sol_root,
            sol_root / "campaign-manifest.json",
            sol_root / "collection-result.json",
            receipt_path,
            grok_kwargs["public_inputs_path"],
            grok_kwargs["dev_targets_path"],
            grok_kwargs["fit_path"],
            grok_kwargs["train_freeze_path"],
            grok_kwargs["dev_comparison_path"],
            grok_kwargs["dev_freeze_path"],
        ]
    )
    output = _output_preflight(output_root, protected)

    # This is deliberately the first replay call. It validates the complete Grok
    # admission and both frozen Grok stages before Sol evidence is consumed.
    grok_result = analysis.replay_selected_successor_dev(**grok_kwargs)
    if not isinstance(grok_result, Mapping) or not {"comparison_raw", "freeze_raw", "freeze"} <= set(grok_result):
        raise ValueError("Grok DEV replay result differs")

    fit_path, fit_raw = _read(grok_kwargs["fit_path"], grok_kwargs["expected_fit_sha256"], "Selected Grok fit")
    train_path, train_raw = _read(grok_kwargs["train_freeze_path"], grok_kwargs["expected_train_freeze_sha256"], "Selected Grok TRAIN freeze")
    dev_comparison_path, dev_comparison_raw = _read(grok_kwargs["dev_comparison_path"], grok_kwargs["expected_dev_comparison_sha256"], "Selected Grok DEV comparison")
    dev_freeze_path, dev_freeze_raw = _read(grok_kwargs["dev_freeze_path"], grok_kwargs["expected_dev_freeze_sha256"], "Selected Grok DEV freeze")
    if grok_result["comparison_raw"] != dev_comparison_raw or grok_result["freeze_raw"] != dev_freeze_raw:
        raise ValueError("Grok DEV replay bytes differ from frozen artifacts")
    train_freeze = _strict_json(train_raw, "Selected Grok TRAIN freeze")
    dev_freeze = _strict_json(dev_freeze_raw, "Selected Grok DEV freeze")
    binding = train_freeze.get("engine_binding") if isinstance(train_freeze, Mapping) else None
    if not isinstance(binding, Mapping) or dev_freeze.get("engine_binding") != binding:
        raise ValueError("Frozen selected TRAIN/DEV binding differs")
    if binding.get("selected_schedule_sha256") != SELECTED_SCHEDULE_SHA256 or binding.get("selected_schedule_source_sha256") != SELECTED_SCHEDULE_SOURCE_SHA256:
        raise ValueError("Frozen selected schedule binding differs")
    if dev_freeze.get("train") != {"fit_sha256": grok_kwargs["expected_fit_sha256"], "freeze_sha256": grok_kwargs["expected_train_freeze_sha256"]}:
        raise ValueError("Frozen Grok DEV TRAIN lineage differs")

    captured, _reader, _controller, _old, _composite, composite_analysis, engine, _local, _standing = analysis._capture(source_pins)
    captured[fit_path] = fit_raw
    captured[train_path] = train_raw
    captured[dev_comparison_path] = dev_comparison_raw
    captured[dev_freeze_path] = dev_freeze_raw
    public_path, public_raw = _read(grok_kwargs["public_inputs_path"], PUBLIC_INPUTS_SHA256, "Selected public inputs")
    dev_targets_path, dev_targets_raw = _read(grok_kwargs["dev_targets_path"], DEV_TARGETS_SHA256, "Selected DEV targets")
    captured[public_path] = public_raw
    captured[dev_targets_path] = dev_targets_raw
    workflow_path = Path(composite_analysis.WORKFLOW_PATH).resolve()
    workflow_path, workflow_raw = _read(workflow_path, source_pins["workflow"], "Workflow pure helpers")
    pure = composite_analysis._load(workflow_path, workflow_raw, "workflow")
    captured[workflow_path] = workflow_raw
    target_path, target_raw, selected_targets, target_projection = composite_analysis._selected_targets(
        pure,
        dev_targets_path,
        pure.DEV_TARGETS_SHA256,
        "DEV",
        set(binding["DEV"]),
        public_raw,
    )
    if target_path != dev_targets_path or target_raw != dev_targets_raw:
        raise ValueError("Selected DEV target source changed during projection")
    if (
        target_projection.get("original_target_sha256") != DEV_TARGETS_SHA256
        or target_projection.get("original_count") != 60
        or target_projection.get("selected_count") != 30
        or not isinstance(target_projection.get("selected_target_sha256"), str)
    ):
        raise ValueError("Selected DEV target projection differs")
    sol_module = _load_pinned(SOL_REPLAY_PATH, SOL_REPLAY_SOURCE_SHA256, "Selected Sol replay")

    # Sol replay is the second and only Sol collection call. No fit or recollection occurs here.
    sol_result = sol_module.replay_collected(**sol_kwargs)
    if not isinstance(sol_result, Mapping) or sol_result.get("provider_calls") != 0 or sol_result.get("full_study_admitted") is not False:
        raise ValueError("Selected Sol replay authority differs")
    train_rows, dev_rows, coverage_failures = _sol_rows(sol_result, binding)
    if len(train_rows) != 70 or len(dev_rows) != 30:
        raise ValueError("Selected Sol selected-story counts differ")

    engine.validate_frozen_fit(
        fit_raw,
        expected_fit_sha256=grok_kwargs["expected_fit_sha256"],
        selection_binding=binding,
        expected_successor_sha256=source_pins["selected_engine"],
        baseline_manifest_path=grok_kwargs["scoring_inputs"]["scoring_manifest_path"],
        baseline_manifest_sha256=grok_kwargs["scoring_inputs"]["expected_scoring_manifest_sha256"],
    )
    comparison = engine.evaluate_dev(
        dev_rows,
        selected_targets,
        fit_raw,
        expected_fit_sha256=grok_kwargs["expected_fit_sha256"],
        selection_binding=binding,
        expected_successor_sha256=source_pins["selected_engine"],
        baseline_manifest_path=grok_kwargs["scoring_inputs"]["scoring_manifest_path"],
        baseline_manifest_sha256=grok_kwargs["scoring_inputs"]["expected_scoring_manifest_sha256"],
    )
    if not isinstance(comparison, Mapping) or comparison.get("evidence_class") != "selected100_amended_dev_comparison_unadmitted":
        raise ValueError("Selected Sol DEV comparison class differs")

    campaign_path, campaign_raw = _read(sol_root / "campaign-manifest.json", sol_kwargs["expected_campaign_manifest_sha256"], "Selected Sol campaign manifest")
    result_path, result_raw = _read(sol_root / "collection-result.json", sol_kwargs["expected_collection_result_sha256"], "Selected Sol collection result")
    captured.update({campaign_path: campaign_raw, result_path: result_raw, receipt_path: receipt_raw, SOL_REPLAY_PATH.resolve(): SOL_REPLAY_PATH.read_bytes()})
    inner = {
        "schema_version": 1,
        "evidence_class": "selected100_sol_dev_comparison_unadmitted",
        "provider_calls": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
        "full_study_admitted": False,
        "sequence_label": "sequencing_amended_after_partial_sol_observation",
        "grok_selection": {
            "fit_sha256": grok_kwargs["expected_fit_sha256"],
            "train_freeze_sha256": grok_kwargs["expected_train_freeze_sha256"],
            "dev_comparison_sha256": grok_kwargs["expected_dev_comparison_sha256"],
            "dev_freeze_sha256": grok_kwargs["expected_dev_freeze_sha256"],
            "engine_binding": dict(binding),
            "dev_target_projection": dict(target_projection),
        },
        "sol_collection": {
            "campaign_manifest_sha256": sol_kwargs["expected_campaign_manifest_sha256"],
            "collection_result_sha256": sol_kwargs["expected_collection_result_sha256"],
            "composer_sha256": SOL_REPLAY_SOURCE_SHA256,
            "replay_receipt_sha256": SOL_REPLAY_RECEIPT_SHA256,
            "selected_requests": sol_result.get("selected_requests"),
            "canonical_verdicts": sol_result.get("canonical_verdicts"),
            "qualification_failures": coverage_failures,
            "unknown_exit_commitments": sol_result.get("unknown_exit_commitments", []),
            "accepted_native_thread_ids": sol_result.get("accepted_native_thread_ids", []),
        },
        "endpoint_sol_rows": sol_result["endpoint_sol_rows"],
        "comparison": dict(comparison),
    }
    inner_raw = _canonical(inner)
    freeze = {
        "schema_version": 1,
        "evidence_class": "selected100_sol_validation_sequencing_amended_after_partial_sol_observation_v1",
        "stage": "SOL_DEV",
        "provider_calls": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
        "full_study_admitted": False,
        "sequence_label": "sequencing_amended_after_partial_sol_observation",
        "grok_selection": inner["grok_selection"],
        "sol_collection": inner["sol_collection"],
        "inner": {"sha256": _sha(inner_raw), "evidence_class": inner["evidence_class"]},
        "source_hashes": {
            str(path): _sha(raw) for path, raw in captured.items()
        },
    }
    for path, raw in captured.items():
        if path.read_bytes() != raw:
            raise ValueError("Selected Sol validation input changed before publication")
    artifacts = _write(output, {
        "selected100-sol-dev-comparison-v1.json": inner_raw,
        "selected100-sol-validation-freeze-v1.json": _canonical(freeze),
    })
    for path, raw in captured.items():
        if path.read_bytes() != raw:
            raise ValueError("Selected Sol validation input changed before publication")
    return {"artifacts": artifacts, "comparison": comparison, "freeze": freeze}


def compare_selected_successor_sol(**kwargs: Any) -> dict[str, Any]:
    """Compatibility alias for callers that name the operation as a comparison."""
    return validate_selected_successor_sol(**kwargs)
