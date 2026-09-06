import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/campaign_plan.py"
SPEC = importlib.util.spec_from_file_location("dryad_campaign_plan", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
INPUTS = Path.home() / "Documents/cwr-dryad-pilot-source-freeze-20260905-r1/public-inputs.json"


@pytest.fixture(scope="module")
def built():
    if not INPUTS.is_file():
        pytest.skip("Local frozen public inputs are unavailable")
    runtime = subject._load_runtime()
    return subject.build_plan(INPUTS.read_bytes(), runtime), runtime


def test_complete_geometry_and_identical_repetitions(built):
    (plan, artifacts), runtime = built
    assert plan["execution_authority"] is False
    assert plan["provider_calls"] == 0
    assert plan["response_schema_mode"] == "batch_question_ids_v1"
    assert len(plan["passes"]) == 18
    assert len(plan["requests"]) == 261
    assert len(artifacts) == 527
    assert [row["ordinal"] for row in plan["requests"]] == list(range(1, 262))
    expected_ids = [row["question"]["id"] for row in runtime.questions]
    prompts = {}
    for item in plan["passes"]:
        requests = [row for row in plan["requests"] if row["pass_id"] == item["pass_id"]]
        assert len(requests) == (23 if item["batch_size"] == 8 else 6)
        assert len(requests[-1]["question_ids"]) == (2 if item["batch_size"] == 8 else 18)
        assert [qid for row in requests for qid in row["question_ids"]] == expected_ids
        for row in requests:
            raw = artifacts[row["prompt_path"]]
            assert subject.digest(raw) == row["prompt_sha256"]
            assert len(raw) == row["prompt_bytes"]
            schema_raw = artifacts[row["schema_path"]]
            schema = json.loads(schema_raw)
            assert row["schema_path"].startswith("schemas/request-")
            assert subject.digest(schema_raw) == row["schema_sha256"]
            assert len(schema_raw) == row["schema_bytes"]
            assert schema["properties"]["verdicts"]["minItems"] == len(row["question_ids"])
            assert schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"] == row["question_ids"]
            key = (item["batch_size"], item["opaque_story_id"], row["batch_number"])
            assert prompts.setdefault(key, raw) == raw
    assert not any(path.startswith("runs/") for path in artifacts)


def test_wrong_source_rejected(built):
    with pytest.raises(ValueError, match="Public inputs hash drift"):
        subject.build_plan(b"{}", built[1])


@pytest.fixture
def prepared(tmp_path, monkeypatch, built):
    # Only committed-source discovery is synthetic; rendering and pinned runtime are real.
    identity = {"evidence_class": "test_only", "git_commit": "a" * 40,
                "files": {"campaign_plan.py": subject.digest(SOURCE.read_bytes())}}
    monkeypatch.setattr(subject, "_generator_identity", lambda commit=None: identity)
    monkeypatch.setattr(subject, "_load_runtime", lambda: built[1])
    output = tmp_path / "plan"
    hashes = subject.prepare(INPUTS, output)
    return output, hashes


def test_prepared_replays_without_writes(prepared):
    output, hashes = prepared
    before = {path: path.stat().st_mtime_ns for path in output.rglob("*")}
    assert subject.verify(INPUTS, output) == hashes
    assert before == {path: path.stat().st_mtime_ns for path in output.rglob("*")}


@pytest.mark.parametrize("mutation", ["prompt", "schema", "extra_file", "extra_directory", "generator", "schedule"])
def test_mutated_package_rejected(prepared, mutation):
    output, _ = prepared
    if mutation == "prompt":
        (output / "prompts/request-0001.txt").write_bytes(b"changed")
    elif mutation == "schema":
        path = output / "schemas/request-0001.json"
        schema = json.loads(path.read_bytes())
        schema["properties"]["verdicts"]["minItems"] += 1
        path.write_bytes(subject._canonical(schema))
    elif mutation == "extra_file":
        (output / "extra.json").write_bytes(b"{}")
    elif mutation == "extra_directory":
        (output / "runs").mkdir()
    else:
        path = output / "plan.json"
        plan = json.loads(path.read_bytes())
        if mutation == "generator":
            plan["generator"]["files"] = {}
        else:
            plan["requests"][0]["question_ids"].reverse()
        path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="identity differs|inventory drift|byte drift"):
        subject.verify(INPUTS, output)


def test_existing_output_rejected(prepared):
    with pytest.raises(ValueError, match="must be fresh"):
        subject.prepare(INPUTS, prepared[0])


def test_runtime_input_drift_rejected(monkeypatch, built):
    original = Path.read_bytes
    def read(path):
        raw = original(path)
        return raw + b" " if path == subject.PROTOCOL_PATH else raw
    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="Analysis protocol hash drift"):
        subject.build_plan(INPUTS.read_bytes(), built[1])
