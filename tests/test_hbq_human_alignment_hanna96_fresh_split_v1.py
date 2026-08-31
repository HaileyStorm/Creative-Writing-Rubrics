from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest
from _scoped_module_loader import load_module

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-fresh-split-v1"
FRESH88_CONTRACT = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v1" / "study-contract.json"
SOURCE = Path.home() / "Documents" / "cwr-hanna-official-source-282f275-20260831" / "hanna_stories_annotations.csv"
PRIVATE_ROOT = Path.home() / "Documents" / "cwr-hanna96-fresh-private-freeze-20260831a"
TEST_PRIVATE_SEED = "a" * 64
study = load_module(PACKAGE / "study.py", name="hanna96_fresh_split_v1")


@pytest.fixture(scope="session")
def actual_rows() -> list[dict[str, str]]:
    return study.read_source(SOURCE)


@pytest.fixture(scope="session")
def actual_manifest_and_private_digest() -> tuple[dict, str]:
    return study._public_manifest_from_files(csv_path=SOURCE, private_root=PRIVATE_ROOT)


def _synthetic_csv(rows: list[dict[str, str]], path: Path) -> list[dict[str, str]]:
    synthetic = copy.deepcopy(rows)
    counters: dict[tuple[str, str], int] = {}
    for row in synthetic:
        key = (row["Prompt"], row["Story ID"])
        counters[key] = counters.get(key, 0) + 1
        for dimension in study.DIMENSIONS:
            row[dimension] = str(counters[key])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(study.CSV_FIELDS))
        writer.writeheader()
        writer.writerows(synthetic)
    return study._rows_from_bytes(path.read_bytes())


def _selection_identity(value: dict) -> list[tuple[str, str, str, str, str]]:
    return [(item["item_id"], item["prompt_group_id"], item["story_id"], item["model"], item["partition"]) for item in value["selected_items"]]


def test_actual_source_replay_is_canonical_and_byte_identical(actual_manifest_and_private_digest: tuple[dict, str]) -> None:
    expected, private_digest = actual_manifest_and_private_digest
    raw = (PACKAGE / "manifest.json").read_bytes()
    assert raw == study.canonical(expected) + b"\n"
    manifest_digest, replayed_private_digest = study.verify_manifest_file(csv_path=SOURCE, private_root=PRIVATE_ROOT)
    assert manifest_digest == hashlib.sha256(raw).hexdigest()
    assert replayed_private_digest == private_digest == expected["commitments"]["private_freeze_sha256"]


def test_public_geometry_and_withholding_boundary(actual_manifest_and_private_digest: tuple[dict, str]) -> None:
    manifest, _ = actual_manifest_and_private_digest
    assert len(manifest["fresh88"]["group_ids"]) == 39
    assert len(manifest["partitions"]["validation"]["group_ids"]) == 16
    assert manifest["partitions"]["future_confirmation"] == {"group_count": 16, "item_count": 32, "status": "privately_frozen_unopened"}
    assert manifest["partitions"]["reserve"] == {"group_count": 25, "item_count": 50, "status": "privately_frozen_unopened"}
    assert len(manifest["groups"]) == len(manifest["selected_items"]) // 2 == 16
    assert len(manifest["selected_items"]) == 32
    assert {item["partition"] for item in manifest["selected_items"]} == {"validation"}
    assert all(item["status"] == "open" and item["annotation_count"] == 3 and set(item["target"]) == set(study.DIMENSIONS) for item in manifest["selected_items"])
    assert manifest["commitments"]["private_frozen_group_count"] == 41
    assert manifest["commitments"]["private_frozen_item_count"] == 82


def test_private_freeze_is_absent_from_public_projection(actual_manifest_and_private_digest: tuple[dict, str], actual_rows: list[dict[str, str]]) -> None:
    manifest, private_digest = actual_manifest_and_private_digest
    private, actual_private_digest = study._private_freeze(PRIVATE_ROOT / study.PRIVATE_FILENAME, actual_rows)
    public = study.canonical(manifest).decode("utf-8")
    assert actual_private_digest == private_digest
    assert private["private_seed"] not in public
    assert all(group_id not in public for partition in private["partitions"].values() for group_id in partition["group_ids"])
    public_items = manifest["selected_items"]
    private_items = private["selected_items"]
    assert not ({item["story_id"] for item in public_items} & {item["story_id"] for item in private_items})
    assert not ({item["prompt"] for item in public_items} & {item["prompt"] for item in private_items})
    assert not ({item["story"] for item in public_items} & {item["story"] for item in private_items})
    assert not ({item["source_binding_sha256"] for item in public_items} & {item["source_binding_sha256"] for item in private_items})
    assert "C:\\Users\\" not in public
    assert str(PRIVATE_ROOT) not in public


def test_fixture_private_root_builds_and_score_changes_do_not_change_selection(tmp_path: Path, actual_rows: list[dict[str, str]]) -> None:
    private_root = tmp_path / "private-root"
    private_digest = study.freeze_private_file(csv_path=SOURCE, private_root=private_root, private_seed=TEST_PRIVATE_SEED)
    public_path = tmp_path / "public.json"
    built_digest, built_private_digest = study.build_public_manifest_file(csv_path=SOURCE, private_root=private_root, output_path=public_path)
    verified_digest, verified_private_digest = study.verify_manifest_file(csv_path=SOURCE, private_root=private_root, manifest_path=public_path)
    assert built_digest == verified_digest == hashlib.sha256(public_path.read_bytes()).hexdigest()
    assert built_private_digest == verified_private_digest == private_digest
    synthetic_rows = _synthetic_csv(actual_rows, tmp_path / "synthetic.csv")
    first_private = study.make_private_freeze_from_rows(synthetic_rows, private_seed=TEST_PRIVATE_SEED)
    first = study.derive_manifest_from_rows(synthetic_rows, private_freeze_sha256=study.sha256(study.canonical(first_private) + b"\n"))
    changed_rows = _synthetic_csv(actual_rows, tmp_path / "synthetic-changed.csv")
    for row in changed_rows:
        for dimension in study.DIMENSIONS:
            row[dimension] = "999"
    changed_private = study.make_private_freeze_from_rows(changed_rows, private_seed=TEST_PRIVATE_SEED)
    second = study.derive_manifest_from_rows(changed_rows, private_freeze_sha256=study.sha256(study.canonical(changed_private) + b"\n"))
    assert _selection_identity(first) == _selection_identity(second)
    assert _selection_identity(first_private) == _selection_identity(changed_private)
    assert all(set(item["target"].values()) == {2.0} for item in first["selected_items"])
    assert all(set(item["target"].values()) == {999.0} for item in second["selected_items"])


def test_fresh88_pin_replays_current_optimizer_v1_contract() -> None:
    fresh88 = json.loads(FRESH88_CONTRACT.read_text(encoding="utf-8"))["eligible_universe"]
    assert study.CONTRACT["fresh88"]["group_ids"] == fresh88["group_ids"]
    assert study.CONTRACT["fresh88"]["group_ids_sha256"] == fresh88["group_ids_sha256"]
    assert hashlib.sha256(FRESH88_CONTRACT.read_bytes()).hexdigest() == study.CONTRACT["fresh88"]["contract_sha256"]


@pytest.mark.parametrize("mutation", ["extra", "missing", "target", "commitment"])
def test_exact_key_and_commitment_tampering_is_rejected(mutation: str, actual_manifest_and_private_digest: tuple[dict, str], actual_rows: list[dict[str, str]]) -> None:
    manifest, private_digest = actual_manifest_and_private_digest
    tampered = copy.deepcopy(manifest)
    if mutation == "extra":
        tampered["unsafe"] = True
    elif mutation == "missing":
        del tampered["commitments"]
    elif mutation == "target":
        tampered["selected_items"][0]["target"]["Relevance"] += 1.0
    else:
        tampered["commitments"]["private_freeze_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="missing, extra, or unsafe keys|exact public derivation"):
        study.validate_manifest(tampered, rows=actual_rows, private_freeze_sha256=private_digest)
