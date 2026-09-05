from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-pilot-v1"
AUDIT_SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-source-audit-v1" / "source.py"
PILOT_SOURCE_SHA256 = "ebe3792f8f8255d18528e55a7a5ae5749a1a0f811e841181fbffa45562024d63"
study = load_module(PACKAGE / "source.py", name="dryad_pilot_v1")


def _synthetic_rows() -> list[dict[str, str]]:
    """Non-empirical fixture: 100 stories with ten ratings each."""
    rows: list[dict[str, str]] = []
    for topic in range(3):
        for condition in range(3):
            for ordinal in range(20 if (topic, condition) == (2, 2) else 10):
                for rating in range(10):
                    row = {
                        "evaluator_index": str(rating + 1),
                        "story_slot": "1",
                        "story_id": f"synthetic-{topic}-{condition}-{ordinal}",
                        "condition": f"treatment-{condition}",
                        "topic": f"theme-{topic}",
                        "story_text": f"Synthetic fixture prose {topic} {condition} {ordinal}.",
                    }
                    row.update({axis: str((topic + condition + ordinal + rating + offset) % 9 + 1) for offset, axis in enumerate(study.AXES)})
                    rows.append(row)
    return rows


def _stories() -> list[dict[str, object]]:
    return study.aggregate_stories(_synthetic_rows())


def _fixture_identity() -> dict[str, str]:
    return {
        "kind": "TEST_FIXTURE",
        "source_sha256": study.sha256_file(PACKAGE / "source.py"),
        "contract_sha256": study.sha256_file(PACKAGE / "experiment-contract.json"),
        "git_commit": "fixture-only-not-an-empirical-freeze",
    }


def _source_evidence() -> dict[str, object]:
    evidence = {key: value for key, value in study.EXPECTED.items() if key != "unknown_story_slots"}
    evidence["unknown_story_id_exclusion"] = {"slots": study.EXPECTED["unknown_story_slots"]}
    evidence["retained_rating_axis_summary"] = {
        axis: {"nonmissing": study.EXPECTED["retained_ratings"], "missing": 0, "minimum": 1, "maximum": 9}
        for axis in study.AXES
    }
    return evidence


def _synthetic_freeze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, dict[str, str]]:
    rows = _synthetic_rows()
    monkeypatch.setitem(study.EXPECTED, "retained_stories", 100)
    monkeypatch.setitem(study.EXPECTED, "retained_ratings", len(rows))
    monkeypatch.setattr(study, "parse_audited_v2", lambda _archive: (rows, _source_evidence()))
    freeze = tmp_path / "freeze"
    fixture_identity = _fixture_identity()
    result = study.create_freeze(tmp_path / "unused-synthetic-archive.zip", freeze, fixture_identity=fixture_identity)
    return freeze, result["provenance_sha256"], fixture_identity


def test_source_pins_contract_and_complete_twelve_axis_aggregation(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = json.loads((PACKAGE / "experiment-contract.json").read_text(encoding="utf-8"))
    dataset = contract["dataset"]
    assert study.sha256_bytes((PACKAGE / "source.py").read_bytes()) == PILOT_SOURCE_SHA256
    assert study.sha256_bytes(AUDIT_SOURCE.read_bytes()) == study.AUDITED_SOURCE_SHA256
    assert dataset["audited_source_commit"] == study.AUDITED_SOURCE_COMMIT
    assert dataset["audited_source_sha256"] == study.AUDITED_SOURCE_SHA256
    assert dataset["twelve_axis_derivative_sha256"] == study.EXPECTED["v2_sha256"]
    assert tuple(contract["target_definition"]["axes"]) == study.AXES
    assert contract["partition"]["seed"] == study.SOURCE_SEED
    assert contract["partition"]["weights"] == study.WEIGHTS

    monkeypatch.setitem(study.EXPECTED, "retained_stories", 100)
    stories = _stories()
    assert len(stories) == 100
    assert len({story["source_story_id"] for story in stories}) == len(stories)
    assert len({story["story_text_sha256"] for story in stories}) == len(stories)
    assert all(set(story["human_means"]) == set(study.AXES) for story in stories)
    assert all(story["rating_count"] == 10 for story in stories)
    assert all(story["source_story_id"] not in story["opaque_story_id"] for story in stories)


def test_partition_is_deterministic_label_independent_and_stratified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(study.EXPECTED, "retained_stories", 100)
    stories = _stories()
    assigned = study.partition_stories(stories)
    repeated = study.partition_stories(list(reversed(copy.deepcopy(stories))))
    assert [(story["opaque_story_id"], story["partition"]) for story in assigned] == [
        (story["opaque_story_id"], story["partition"]) for story in repeated
    ]
    relabeled = [{**story, "human_means": {axis: "9" for axis in study.AXES}} for story in stories]
    assert [(story["opaque_story_id"], story["partition"]) for story in assigned] == [
        (story["opaque_story_id"], story["partition"]) for story in study.partition_stories(relabeled)
    ]
    assert Counter(story["partition"] for story in assigned) == {"TRAIN": 60, "DEV": 20, "CONFIRMATION": 20}
    per_stratum = Counter((story["topic"], story["condition"], story["partition"]) for story in assigned)
    assert len({(story["topic"], story["condition"]) for story in assigned}) == 9
    assert set(per_stratum.values()) == {2, 4, 6, 12}
    for topic in range(3):
        for condition in range(3):
            expected = [12, 4, 4] if (topic, condition) == (2, 2) else [6, 2, 2]
            assert [per_stratum[(f"theme-{topic}", f"treatment-{condition}", partition)] for partition in study.PARTITIONS] == expected


def test_rejects_duplicate_or_mutated_source_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(study.EXPECTED, "retained_stories", 100)
    duplicate_text = _synthetic_rows()
    duplicate_text[10]["story_text"] = duplicate_text[0]["story_text"]
    with pytest.raises(ValueError, match="Duplicate story text"):
        study.aggregate_stories(duplicate_text)

    out_of_range = _synthetic_rows()
    out_of_range[0]["novel"] = "10"
    with pytest.raises(ValueError, match="Rating range"):
        study.aggregate_stories(out_of_range)

    missing_axis = _synthetic_rows()
    del missing_axis[0]["future"]
    with pytest.raises(KeyError):
        study.aggregate_stories(missing_axis)

    incomplete_strata = [row for row in _synthetic_rows() if row["topic"] != "theme-2"]
    monkeypatch.setitem(study.EXPECTED, "retained_stories", len({row["story_id"] for row in incomplete_strata}))
    with pytest.raises(ValueError, match="nine topic-by-condition strata"):
        study.partition_stories(study.aggregate_stories(incomplete_strata))


def test_freeze_is_create_only_and_loader_excludes_local_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    freeze, provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path, monkeypatch)
    provenance = study.verify_freeze(freeze, provenance_sha256, fixture_identity=fixture_identity)
    assert provenance["partition"]["counts"] == {"CONFIRMATION": 20, "DEV": 20, "TRAIN": 60}
    public = study.load_public_inputs(freeze, provenance_sha256, fixture_identity=fixture_identity)
    assert set(public) == {"TRAIN", "DEV"}
    assert len(public["TRAIN"]) == 60 and len(public["DEV"]) == 20
    assert all(set(record) == {"opaque_story_id", "story_text"} for records in public.values() for record in records)
    public_ids = {record["opaque_story_id"] for records in public.values() for record in records}
    confirmation = [json.loads(line) for line in (freeze / "confirmation-targets.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(confirmation) == 20
    assert public_ids.isdisjoint({record["opaque_story_id"] for record in confirmation})
    raw_public = (freeze / "public-inputs.json").read_text(encoding="utf-8")
    assert all(field not in raw_public for field in ("human_means", "condition", "topic", "confirmation", "source_story_id"))
    with pytest.raises(FileExistsError, match="create-only"):
        study.create_freeze(tmp_path / "unused-synthetic-archive.zip", freeze, fixture_identity=fixture_identity)

    altered = json.loads(raw_public)
    altered["TRAIN"][0]["topic"] = "forbidden"
    (freeze / "public-inputs.json").write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="Artifact byte or hash mismatch"):
        study.load_public_inputs(freeze, provenance_sha256, fixture_identity=fixture_identity)


def test_schema_valid_text_mutation_cannot_bypass_external_provenance_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    freeze, provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path, monkeypatch)
    public_path = freeze / "public-inputs.json"
    rewritten_public = json.loads(public_path.read_text(encoding="utf-8"))
    rewritten_public["TRAIN"][0]["story_text"] = "Schema-valid but substituted fixture prose."
    public_path.write_bytes(study.canonical_json_bytes(rewritten_public))
    rewritten_provenance = json.loads((freeze / "provenance.json").read_text(encoding="utf-8"))
    rewritten_provenance["artifacts"]["public-inputs.json"] = {
        "bytes": public_path.stat().st_size,
        "sha256": study.sha256_file(public_path),
    }
    (freeze / "provenance.json").write_bytes(study.canonical_json_bytes(rewritten_provenance))
    rewritten_sha256 = study.sha256_file(freeze / "provenance.json")
    with pytest.raises(ValueError, match="Externally bound provenance"):
        study.verify_freeze(freeze, provenance_sha256, fixture_identity=fixture_identity)
    with pytest.raises(ValueError, match="Public input linkage drift"):
        study.verify_freeze(freeze, rewritten_sha256, fixture_identity=fixture_identity)


def test_verifier_rejects_missing_extra_hashed_and_sized_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    freeze, provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path / "missing", monkeypatch)
    (freeze / "local-targets.jsonl").unlink()
    with pytest.raises(ValueError, match="physical artifact set drift"):
        study.verify_freeze(freeze, provenance_sha256, fixture_identity=fixture_identity)

    freeze, provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path / "extra", monkeypatch)
    (freeze / "unexpected.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="physical artifact set drift"):
        study.verify_freeze(freeze, provenance_sha256, fixture_identity=fixture_identity)

    freeze, provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path / "hash", monkeypatch)
    (freeze / "public-inputs.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Artifact byte or hash mismatch"):
        study.verify_freeze(freeze, provenance_sha256, fixture_identity=fixture_identity)

    freeze, _provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path / "size", monkeypatch)
    altered_provenance = json.loads((freeze / "provenance.json").read_text(encoding="utf-8"))
    altered_provenance["artifacts"]["public-inputs.json"]["bytes"] += 1
    (freeze / "provenance.json").write_bytes(study.canonical_json_bytes(altered_provenance))
    with pytest.raises(ValueError, match="Artifact byte or hash mismatch"):
        study.verify_freeze(freeze, study.sha256_file(freeze / "provenance.json"), fixture_identity=fixture_identity)


def test_generator_identity_is_recorded_and_contract_mutation_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    freeze, provenance_sha256, fixture_identity = _synthetic_freeze(tmp_path, monkeypatch)
    provenance = study.verify_freeze(freeze, provenance_sha256, fixture_identity=fixture_identity)
    assert provenance["generator"] == {
        "source_sha256": fixture_identity["source_sha256"],
        "contract_sha256": fixture_identity["contract_sha256"],
        "git_commit": fixture_identity["git_commit"],
        "mode": "TEST_FIXTURE",
    }
    with pytest.raises(ValueError, match="Fixture identity"):
        study.create_freeze(
            tmp_path / "unused-synthetic-archive.zip",
            tmp_path / "bad-identity",
            fixture_identity={**fixture_identity, "contract_sha256": "0" * 64},
        )
    altered_provenance = json.loads((freeze / "provenance.json").read_text(encoding="utf-8"))
    altered_provenance["generator"]["contract_sha256"] = "0" * 64
    (freeze / "provenance.json").write_bytes(study.canonical_json_bytes(altered_provenance))
    with pytest.raises(ValueError, match="generator provenance drift"):
        study.verify_freeze(freeze, study.sha256_file(freeze / "provenance.json"), fixture_identity=fixture_identity)


def test_production_generator_identity_compares_git_show_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    package = root / "pilot"
    package.mkdir(parents=True)
    (root / ".git").mkdir()
    source = package / "source.py"
    contract = package / "experiment-contract.json"
    source.write_bytes(b"production source bytes\n")
    contract.write_bytes(b"production contract bytes\n")
    monkeypatch.setattr(study, "__file__", str(source))
    monkeypatch.setattr(study, "repository_root", lambda _path: root)

    def git_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-1] == "HEAD":
            assert kwargs.get("text") is True
            return SimpleNamespace(stdout="post-unrelated-advance\n")
        assert kwargs.get("text") is not True
        requested = command[-1].split(":", 1)[1]
        return SimpleNamespace(stdout=(root / requested).read_bytes())

    monkeypatch.setattr(study.subprocess, "run", git_run)
    assert study.generator_identity() == {
        "source_sha256": study.sha256_file(source),
        "contract_sha256": study.sha256_file(contract),
        "git_commit": "post-unrelated-advance",
        "mode": "COMMITTED",
    }
