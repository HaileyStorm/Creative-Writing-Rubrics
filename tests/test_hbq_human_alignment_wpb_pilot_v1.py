from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-wpb-pilot-v1"
SOURCE = PACKAGE / "source.py"
PINNED_SOURCE = Path(r"C:\Users\Haile\Documents\cwr-wpb-source-c6ac5821-20260904")


def _module():
    spec = importlib.util.spec_from_file_location("hbq_human_alignment_wpb_pilot_v1", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture(scope="module")
def study():
    if not PINNED_SOURCE.is_dir():
        pytest.skip("the pinned public WPB source checkout is unavailable")
    return _module()


@pytest.fixture(scope="module")
def frozen(study, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    output_root = tmp_path_factory.mktemp("wpb-freeze") / "frozen"
    return output_root, study.freeze(PINNED_SOURCE, output_root)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_selection(items: list[dict[str, Any]]) -> list[tuple[int, str, str]]:
    return sorted(
        (item["source_index"], item["category"], item["selection_key_sha256"])
        for item in items
    )


def test_pinned_source_hashes_schema_and_geometry(study) -> None:
    rows, binding = study.load_source(PINNED_SOURCE)
    assert binding == {
        "commit": "c6ac5821582e77fb34d27f6b54aac937904ee112",
        "readme_sha256": "529c50e79d43dd637d4210c3362d66aeeb8a32220ce460ed852f6a1ef3d74fa3",
        "english_json_sha256": "c80907b42f83673f026280b3af6cc998b69db4045081745b994f1c20c11a8bdd",
    }
    assert len(rows) == study.EXPECTED_ROWS == 1200
    assert len({row["tag"] for row in rows}) == study.EXPECTED_CATEGORIES == 51
    assert all(set(row) == {"prompt", "prompt_id", "tag", "chosen", "rejected"} for row in rows)
    assert all(
        set(row[side]) == study.RESPONSE_FIELDS
        for row in rows
        for side in ("chosen", "rejected")
    )
    selected, excluded, components = study._selected_rows(rows)
    assert len(selected) == 153 and len(excluded) == 1047 and len(components) == 350
    assert sum(item["reason"] == "cross_category_component" for item in excluded) == 22
    cross_category_components = {
        item["component_sha256"]
        for item in excluded
        if item["reason"] == "cross_category_component"
    }
    assert len(cross_category_components) == 3
    assert Counter(item["category"] for item in selected) == {
        category: 3 for category in sorted({row["tag"] for row in rows})
    }
    assert all(
        len({item["component_sha256"] for item in category_items}) == 3
        for category_items in defaultdict(list, {
            category: [item for item in selected if item["category"] == category]
            for category in {item["category"] for item in selected}
        }).values()
    )


def test_selection_is_preference_blind_under_side_score_and_model_changes(study) -> None:
    rows, _ = study.load_source(PINNED_SOURCE)
    baseline, _, _ = study._selected_rows(rows)
    altered = copy.deepcopy(rows)
    for row in altered:
        row["chosen"], row["rejected"] = row["rejected"], row["chosen"]
        row["chosen"]["score"] = 3 - row["chosen"]["score"]
        row["rejected"]["score"] = 3 - row["rejected"]["score"]
        row["chosen"]["model"] = "selection-irrelevant-model-a"
        row["rejected"]["model"] = "selection-irrelevant-model-b"
    changed, _, _ = study._selected_rows(altered)
    assert _stable_selection(changed) == _stable_selection(baseline)


def test_freeze_keeps_categories_and_components_partition_disjoint(frozen) -> None:
    output_root, receipt = frozen
    assert receipt == {
        "study_id": "hbq-human-alignment-wpb-pilot-v1",
        "source_rows": 1200,
        "categories": 51,
        "components": 350,
        "selected": 153,
        "excluded": 1047,
        "cross_category_excluded": 22,
        "default_schedule_cells": 129,
        "confirmation_cells": 24,
        "output_root": str(output_root.resolve()),
    }
    provenance = _read(output_root / "provenance-selection-manifest.json")
    split = _read(output_root / "split-manifest.json")
    selected = provenance["selected"]
    assert split["counts"] == {"train": 35, "dev": 8, "confirmation": 8}
    by_category = {item["category"]: item["partition"] for item in selected}
    assert Counter(by_category.values()) == {"train": 35, "dev": 8, "confirmation": 8}
    assert Counter(item["partition"] for item in selected) == {"train": 105, "dev": 24, "confirmation": 24}
    components = defaultdict(set)
    for item in selected:
        components[item["component_sha256"]].add(item["partition"])
    assert all(len(partitions) == 1 for partitions in components.values())
    assert all(
        len({item["category"] for item in selected if item["component_sha256"] == component}) == 1
        for component in components
    )


def test_execution_inputs_are_endpoint_neutral_and_preference_blind(study, frozen) -> None:
    output_root, _ = frozen
    inputs = _read(output_root / "execution-inputs.json")
    targets = _read(output_root / "local-targets.json")
    default = study.load_default_schedule(output_root)
    assert inputs["endpoint_neutral"] is True
    assert inputs["preference_labels_or_scores_present"] is False
    assert len(inputs["cells"]) == 153 and len(targets["targets"]) == 153
    assert len(default["cells"]) == 129 and default["confirmation_excluded"] is True
    assert {cell["cell_id"] for cell in default["cells"]} == {
        cell["cell_id"] for cell in inputs["cells"] if cell["partition"] != "confirmation"
    }
    assert all(cell["partition"] != "confirmation" for cell in default["cells"])
    forbidden = {"chosen", "rejected", "score", "model", "tag", "target", "preferred", "side"}
    for payload in (inputs, default):
        rendered = study.canonical_json(payload).decode("utf-8").lower()
        assert not any(f'"{field}"' in rendered for field in forbidden)
    assert targets["local_only"] is True and targets["not_for_provider_disclosure"] is True
    by_id = {target["cell_id"]: target for target in targets["targets"]}
    for cell in inputs["cells"]:
        assert cell["response_a_sha256"] < cell["response_b_sha256"]
        payload = base64.b64decode(cell["payload_utf8_base64"], validate=True)
        assert hashlib.sha256(payload).hexdigest() == cell["payload_sha256"]
        assert payload == study._make_payload(cell["prompt"], cell["response_a"], cell["response_b"])
        assert cell["cell_id"] in by_id


def test_confirmation_has_no_opening_api_or_cli_surface(study) -> None:
    assert not hasattr(study, "open_confirmation_schedule")
    source_text = SOURCE.read_text(encoding="utf-8")
    assert "open-confirmation" not in source_text
    assert "confirmation-opening.json" not in source_text
    assert "frozen_profile_analysis" not in source_text


def test_default_schedule_reconstructs_exactly_and_rejects_schedule_tampering(study, frozen) -> None:
    output_root, _ = frozen
    schedule_path = output_root / "default-schedule.json"
    original = schedule_path.read_bytes()
    schedule = _read(schedule_path)
    assert len(schedule["cells"]) == 129

    mutations = {
        "noncanonical": lambda value: schedule_path.write_bytes(original + b" "),
        "omitted": lambda value: value["cells"].pop(),
        "extra": lambda value: value["cells"].append(copy.deepcopy(value["cells"][0])),
        "cell-id": lambda value: value["cells"][0].update(cell_id="wpb-pair-tampered"),
        "partition": lambda value: value["cells"][0].update(partition="dev"),
        "payload": lambda value: value["cells"][0].update(payload_sha256="0" * 64),
        "kind": lambda value: value.update(kind="tampered"),
        "open-partitions": lambda value: value.update(open_partitions=["train"]),
        "confirmation-flag": lambda value: value.update(confirmation_excluded=False),
    }
    for name, mutate in mutations.items():
        value = copy.deepcopy(schedule)
        mutate(value)
        if name != "noncanonical":
            schedule_path.write_bytes(study.canonical_json(value) + b"\n")
        try:
            with pytest.raises(ValueError):
                study.load_default_schedule(output_root)
        finally:
            schedule_path.write_bytes(original)


def test_default_schedule_rejects_execution_input_tampering(study, frozen) -> None:
    output_root, _ = frozen
    inputs_path = output_root / "execution-inputs.json"
    original = inputs_path.read_bytes()
    inputs = _read(inputs_path)
    default_index = next(
        index for index, cell in enumerate(inputs["cells"]) if cell["partition"] != "confirmation"
    )
    mutations = {
        "noncanonical": lambda value: inputs_path.write_bytes(original + b" "),
        "cell-id": lambda value: value["cells"][default_index].update(cell_id="wpb-pair-tampered"),
        "partition": lambda value: value["cells"][default_index].update(partition="confirmation"),
        "payload": lambda value: value["cells"][default_index].update(payload_sha256="0" * 64),
        "omitted": lambda value: value["cells"].pop(default_index),
    }
    for name, mutate in mutations.items():
        value = copy.deepcopy(inputs)
        mutate(value)
        if name != "noncanonical":
            inputs_path.write_bytes(study.canonical_json(value) + b"\n")
        try:
            with pytest.raises(ValueError):
                study.load_default_schedule(output_root)
        finally:
            inputs_path.write_bytes(original)


def test_fresh_freeze_and_tamper_guards(study, frozen, tmp_path: Path) -> None:
    output_root, _ = frozen
    with pytest.raises(FileExistsError, match="never reused"):
        study.freeze(PINNED_SOURCE, output_root)

    tampered_source = tmp_path / "tampered-source"
    tampered_source.mkdir()
    (tampered_source / "WP_bench_english.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        study.freeze(tampered_source, tmp_path / "tampered-freeze")

    schedule = output_root / "default-schedule.json"
    original = schedule.read_bytes()
    illegal = _read(schedule)
    illegal["cells"][0]["partition"] = "confirmation"
    schedule.write_bytes(study.canonical_json(illegal) + b"\n")
    try:
        with pytest.raises(ValueError):
            study.load_default_schedule(output_root)
    finally:
        schedule.write_bytes(original)
