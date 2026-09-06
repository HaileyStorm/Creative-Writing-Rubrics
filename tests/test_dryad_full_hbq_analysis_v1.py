import csv
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/source.py"
SPEC = importlib.util.spec_from_file_location("dryad_analysis_v1", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
COUNTS = {"TRAIN": 1, "DEV": 1, "CONFIRMATION": 1}
SPLIT = [
    {"source_story_id": "source-train", "opaque_story_id": "opaque-train", "partition": "TRAIN"},
    {"source_story_id": "source-dev", "opaque_story_id": "opaque-dev", "partition": "DEV"},
    {"source_story_id": "source-closed", "opaque_story_id": "opaque-closed", "partition": "CONFIRMATION"},
]


def records():
    first = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1, 2, 3]
    second = [4, 5, 6, 7, 8, 9, 1, 2, 3, 4, 5, 6]
    return [
        ["EVALUATOR-PRIVATE", "1", "source-train", "condition", "topic", "STORY-PRIVATE", *first],
        ["EVALUATOR-OTHER", "1", "source-train", "condition", "topic", "STORY-PRIVATE", *second],
        ["EVALUATOR-PRIVATE", "2", "source-dev", "condition", "topic", "STORY-PRIVATE", *([2] * 12)],
        ["", "", "source-closed", "condition", "topic", "CLOSED-PRIVATE", *(["POISON-CLOSED"] * 12)],
    ]


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(subject.REQUIRED_CSV_FIELDS)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def test_exact_source_indices_and_confirmation_exclusion():
    targets = subject.derive_targets(csv_bytes(records()), SPLIT, COUNTS)
    assert set(targets) == {"TRAIN", "DEV"}
    train = targets["TRAIN"][0]
    assert train["rating_count"] == 2
    assert train["indices"] == {
        "novelty": {"numerator": 7, "denominator": 2},
        "usefulness": {"numerator": 13, "denominator": 2},
    }
    assert train["axis_means"]["novel"] == {"numerator": 5, "denominator": 2}
    raw = subject.canonical_json_bytes(targets)
    assert all(value not in raw for value in (b"PRIVATE", b"EVALUATOR", b"source-", b"opaque-closed", b"condition", b"topic", b"POISON"))


@pytest.mark.parametrize("bad", ["duplicate_slot", "missing_story", "unknown_story", "rating_range", "rating_missing", "row_width", "duplicate_opaque"])
def test_source_shape_errors_never_produce_partial_targets(bad):
    rows = records()
    split = [dict(record) for record in SPLIT]
    if bad == "duplicate_slot":
        rows[1][0] = rows[0][0]
    elif bad == "missing_story":
        rows.pop(2)
    elif bad == "unknown_story":
        rows[0][2] = "unknown"
    elif bad == "rating_range":
        rows[0][6] = 10
    elif bad == "rating_missing":
        rows[0][6] = ""
    elif bad == "row_width":
        rows[0].pop()
    else:
        split[1]["opaque_story_id"] = split[0]["opaque_story_id"]
    with pytest.raises(ValueError):
        subject.derive_targets(csv_bytes(rows), split, COUNTS)


def fixture_inputs(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    ratings = inputs / "ratings.csv"
    ratings.write_bytes(csv_bytes(records()))
    freeze = tmp_path / "freeze"
    freeze.mkdir()
    split = b"".join(subject.canonical_json_bytes(record) for record in SPLIT)
    (freeze / "split-manifest.jsonl").write_bytes(split)
    parent = {"artifacts": {"split-manifest.jsonl": {"sha256": subject.sha256_bytes(split)}}}
    parent_bytes = subject.canonical_json_bytes(parent)
    (freeze / "provenance.json").write_bytes(parent_bytes)
    protocol = json.loads(subject.PROTOCOL_PATH.read_bytes())
    protocol["source"].update({"ratings_sha256": subject.sha256_bytes(ratings.read_bytes()), "split_sha256": subject.sha256_bytes(split), "parent_provenance_sha256": subject.sha256_bytes(parent_bytes), "partitions": COUNTS})
    repository = tmp_path / "repository"
    repository.mkdir()
    protocol_path = repository / "protocol.json"
    protocol_path.write_bytes(subject.canonical_json_bytes(protocol))
    monkeypatch.setattr(subject, "PROTOCOL_PATH", protocol_path)
    monkeypatch.setattr(subject, "PROTOCOL_SHA256", subject.sha256_bytes(protocol_path.read_bytes()))
    monkeypatch.setattr(subject, "REPOSITORY", repository)
    monkeypatch.setattr(subject, "_generator_identity", lambda commit=None: {"git_commit": "0" * 40, "evidence_class": "TEST_FIXTURE"})
    return ratings, freeze


def test_actual_prepare_verify_path_and_mutations(tmp_path, monkeypatch):
    ratings, freeze = fixture_inputs(tmp_path, monkeypatch)
    output = tmp_path / "targets"
    hashes = subject.prepare(ratings, freeze, output)
    assert subject.verify(ratings, freeze, output) == hashes
    with pytest.raises(FileExistsError):
        subject.prepare(ratings, freeze, output)
    target = output / "dev-targets.json"
    original = target.read_bytes()
    target.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="byte drift"):
        subject.verify(ratings, freeze, output)
    target.write_bytes(original)
    ratings.write_bytes(ratings.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash drift"):
        subject.verify(ratings, freeze, output)


def test_source_change_during_derive_is_rejected(tmp_path, monkeypatch):
    ratings, freeze = fixture_inputs(tmp_path, monkeypatch)
    derive = subject.derive_targets
    def changed(*args, **kwargs):
        result = derive(*args, **kwargs)
        ratings.write_bytes(ratings.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(subject, "derive_targets", changed)
    with pytest.raises(ValueError, match="changed during"):
        subject.prepare(ratings, freeze, tmp_path / "targets")
    assert not (tmp_path / "targets").exists()


def test_qualification_document_binding_and_request_budget():
    protocol, _ = subject._load_protocol()
    raw = SOURCE.with_name("qualification-v2.json").read_bytes()
    assert subject.sha256_bytes(raw) == protocol["execution"]["qualification_protocol_sha256"]
    qualification = json.loads(raw)
    passes = len(qualification["cohort"]) * qualification["complete_passes_per_story_per_size"]
    count = qualification["question_set"]["count"]
    for name, size_key in (("reference", "reference_batch_size"), ("candidate", "candidate_batch_size")):
        size = qualification[size_key]
        assert qualification["logical_requests"][name] == passes * ((count + size - 1) // size)
    assert qualification["logical_requests"]["total"] == 261
    assert qualification["execution_authority"] is False
    assert qualification["current_empirical_cap"] is None


@pytest.mark.parametrize("location", ["repository", "freeze", "inputs"])
def test_prepare_cannot_write_into_immutable_source_roots(tmp_path, monkeypatch, location):
    ratings, freeze = fixture_inputs(tmp_path, monkeypatch)
    output = tmp_path / location / "new-targets"
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid output location reached target derivation")
    monkeypatch.setattr(subject, "_expected_artifacts", forbidden)
    with pytest.raises(ValueError, match="disjoint"):
        subject.prepare(ratings, freeze, output)
    assert not output.exists()


def test_prepare_rejects_reparse_ancestor_before_creation(tmp_path, monkeypatch):
    ratings, freeze = fixture_inputs(tmp_path, monkeypatch)
    original = Path.lstat
    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == tmp_path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info
    monkeypatch.setattr(Path, "lstat", reparse)
    output = tmp_path / "targets"
    with pytest.raises(ValueError, match="reparse"):
        subject.prepare(ratings, freeze, output)
    assert not output.exists()
