"""Native-record replay using only isolated shared-broker fake CLI fixtures."""

import importlib.util
import json
from pathlib import Path

import pytest

from test_grok_broker_transport import fixture, execute, bind


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/native_admission.py"
SPEC = importlib.util.spec_from_file_location("dryad_native_admission", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


@pytest.fixture
def completed(tmp_path, fixture):
    case, _ = fixture
    raw = case.fake.read_text(encoding="utf-8")
    case.fake.write_text(raw.replace('"fixture-request"', '"fixture-" + session'), encoding="utf-8")
    route = case.route("hbq", timeout_seconds=30)
    case.write_route(route)
    transport = bind(case, route, lambda context: None)
    execute(tmp_path, transport, batch_size=32, response_schema_mode="batch_question_ids_v1")
    routes = {subject.digest(subject.canonical(route)): route}
    runtime = subject.load_runtime()
    source = {"opaque_story_id": "artifact", "story_text": "A short test scene.", "artifact_path": str(tmp_path / "artifact.txt")}
    return tmp_path / "run", routes, runtime, source


@pytest.fixture
def partial(tmp_path, fixture):
    case, _ = fixture
    raw = case.fake.read_text(encoding="utf-8")
    case.fake.write_text(raw.replace('"fixture-request"', '"fixture-" + session'), encoding="utf-8")
    route = case.route("hbq", timeout_seconds=30)
    case.write_route(route)
    transport = bind(case, route, lambda context: None)
    runtime = subject.load_runtime()

    def pause_after_prefix(context):
        if context["batch"]["number"] == 3:
            raise runtime.runner.RetryDisclosurePause("test prefix pause")

    with pytest.raises(runtime.runner.RetryDisclosurePause):
        execute(tmp_path, transport, batch_size=32, response_schema_mode="batch_question_ids_v1", before_provider_attempt=pause_after_prefix)
    routes = {subject.digest(subject.canonical(route)): route}
    source = {"opaque_story_id": "artifact", "story_text": "A short test scene.", "artifact_path": str(tmp_path / "artifact.txt")}
    return tmp_path / "run", routes, runtime, source


def test_replay_recomputes_full_pass_without_writes(completed):
    root, routes, runtime, source = completed
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    admitted = subject.admit_pass(root, source=source, batch_size=32, approved_routes=routes, runtime=runtime)
    assert len(admitted["verdicts"]) == 178
    assert len(admitted["native_identities"]) == 6
    assert len({item["request_id_hash"] for item in admitted["native_identities"]}) == 6
    assert admitted["coverage"] == 1
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_batch_schema_records_bind_exact_question_ids_and_counts(completed):
    root, _, runtime, _ = completed
    manifest = json.loads((root / "run.json").read_bytes())
    config = manifest["configuration"]
    assert config["response_schema_mode"] == "batch_question_ids_v1"
    records = config["batch_response_schemas"]
    assert len(records) == 6
    for number, record in enumerate(records, start=1):
        raw = (root / record["path"]).read_bytes()
        schema = json.loads(raw)
        question_ids = [item["question"]["id"] for item in runtime.questions[(number - 1) * 32:number * 32]]
        assert record == {
            "path": f"responses/schemas/batch-{number:04d}.json",
            "sha256": subject.digest(raw),
            "bytes": len(raw),
        }
        assert schema["properties"]["verdicts"]["minItems"] == len(question_ids)
        assert schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"] == question_ids


def test_batch_schema_tamper_is_rejected(completed):
    root, routes, runtime, source = completed
    path = root / "responses/schemas/batch-0001.json"
    schema = json.loads(path.read_bytes())
    schema["properties"]["verdicts"]["minItems"] += 1
    path.write_bytes(subject.canonical(schema))
    with pytest.raises(ValueError, match="schema|configuration|drift|inventory"):
        subject.admit_pass(root, source=source, batch_size=32, approved_routes=routes, runtime=runtime)


@pytest.mark.parametrize("fault", ["score", "source", "route", "missing_checkpoint", "orphan_file", "orphan_dir"])
def test_pass_admission_rejects_unqualified_evidence(completed, fault):
    root, routes, runtime, source = completed
    if fault == "score":
        path = root / "score.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "source":
        source = {**source, "story_text": "different source"}
    elif fault == "route":
        routes = {}
    elif fault == "missing_checkpoint":
        (root / "responses/batch-0006.json").unlink()
    elif fault == "orphan_file":
        (root / "responses/grok-broker/orphan.json").write_bytes(b"{}")
    else:
        (root / "responses/orphan").mkdir()
    with pytest.raises(Exception):
        subject.admit_pass(root, source=source, batch_size=32, approved_routes=routes, runtime=runtime)


@pytest.mark.parametrize("field", ["paid", "turns", "model", "stop", "schema_error", "telemetry"])
def test_raw_native_semantics_are_rechecked(completed, field):
    root, routes, runtime, _ = completed
    prefix = root / "responses/grok-broker/batch-0001-attempt-0001"
    result = json.loads((prefix / "outcome.json").read_bytes())["result"]
    native = json.loads((prefix / "native-envelope.json").read_bytes())
    if field == "paid":
        native["weeklyAllowanceExhausted"] = True
    elif field == "turns":
        native["num_turns"] = 2
    elif field == "model":
        native["modelUsage"] = {"other-model": {"costUSD": 0}}
    elif field == "stop":
        native["stopReason"] = "max_turns"
    elif field == "schema_error":
        native["structuredOutputError"] = "failure"
    else:
        native["modelUsage"]["grok-4.6-build"]["costUSD"] = 12
    raw = subject.canonical(native)
    result["native_envelope_artifact"].update({"sha256": subject.digest(raw), "byte_length": len(raw)})
    result["runtime"]["envelope_hash"] = subject.digest(raw)
    result["runtime"]["transport"]["stdout_byte_length"] = len(raw)
    request = json.loads((prefix / "request.json").read_bytes())
    with pytest.raises(ValueError):
        strict_schema = runtime.runner._batch_response_schema(
            [item["question"]["id"] for item in runtime.questions[:32]]
        )
        subject._native_result(runtime, result, raw, next(iter(routes.values())), request["prompt"],
                               strict_schema, result["runtime"]["session_id_hash"])


def forge_receipt_context(root, runtime, field, count):
    prefix = root / "responses/grok-broker/batch-0001-attempt-0001"
    receipt_path = prefix / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    if field == "context":
        context_path = prefix / "context-bindings.json"
        context = json.loads(context_path.read_bytes())
        context["run"]["run_id"] = "forged-run-id"
        context_path.write_bytes(subject.canonical(context))
        receipt["context_sha256"] = subject.digest(context_path.read_bytes())
    elif field == "source":
        receipt["source_sha256"] = "0" * 64
    else:
        receipt["request_id_hash"] = "0" * 64
    receipt_path.write_bytes(subject.canonical(receipt))
    previous = None
    for number in range(1, count + 1):
        path = root / f"responses/batch-{number:04d}.json"
        checkpoint = json.loads(path.read_bytes())
        checkpoint["previous_checkpoint_sha256"] = previous
        if number == 1:
            metadata = checkpoint["provider"]
            for name, descriptor in list(metadata["provider_artifacts"].items()):
                metadata["provider_artifacts"][name] = runtime.runner._provider_artifact(root, root / descriptor["path"])
            metadata["evidence_sha256"] = subject.digest(receipt_path.read_bytes())
        path.write_bytes(runtime.runner._json_bytes(checkpoint))
        previous = subject.digest(path.read_bytes())
        settled_path = root / f"responses/attempt-lifecycle/batch-{number:04d}/attempt-0001.settled.json"
        settled = json.loads(settled_path.read_bytes())
        settled["evidence"]["sha256"] = previous
        settled_path.write_bytes(runtime.runner._json_bytes(settled))


@pytest.mark.parametrize("field", ["context", "source", "request_id"])
def test_rehashed_forged_receipt_context_is_rejected_semantically(completed, field):
    root, routes, runtime, source = completed
    forge_receipt_context(root, runtime, field, 6)
    with pytest.raises(ValueError, match="semantic reconstruction"):
        subject.admit_pass(root, source=source, batch_size=32, approved_routes=routes, runtime=runtime)


@pytest.mark.parametrize("field", ["context", "request_id"])
def test_partial_settlement_cannot_accept_rehashed_semantic_forgery(partial, field):
    root, routes, runtime, source = partial
    forge_receipt_context(root, runtime, field, 2)
    with pytest.raises(ValueError, match="semantic reconstruction"):
        subject.admit_prefix(root, source=source, batch_size=32, approved_routes=routes, expected_batches=2, runtime=runtime)


@pytest.mark.parametrize("field", ["extra_config", "prompt_path", "schema_path", "batch_schema_path"])
def test_rehashed_configuration_metadata_is_exact(completed, field):
    root, routes, runtime, source = completed
    path = root / "run.json"
    manifest = json.loads(path.read_bytes())
    config = manifest["configuration"]
    if field == "extra_config":
        config["unrecognized_execution_policy"] = "different policy"
    elif field == "prompt_path":
        config["prompts"][0]["path"] = str(root / "different-prompt.md")
    elif field == "batch_schema_path":
        config["batch_response_schemas"][0]["path"] = str(root / "different-batch-schema.json")
    else:
        config["response_schema"]["path"] = str(root / "different-schema.json")
    manifest["config_sha256"] = subject.digest(runtime.runner._json_bytes(config))
    path.write_bytes(runtime.runner._json_bytes(manifest))
    with pytest.raises(
        ValueError,
        match="shape differs|metadata differs|Run configuration differs from qualification",
    ):
        subject.admit_pass(root, source=source, batch_size=32, approved_routes=routes, runtime=runtime)


def test_prefix_replay_validates_pause_prompt_without_score_or_writes(partial):
    root, routes, runtime, source = partial
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    admitted = subject.admit_prefix(root, source=source, batch_size=32, approved_routes=routes,
                                    expected_batches=2, runtime=runtime)
    assert admitted["accepted_count"] == 64
    assert admitted["score"] is None and admitted["coverage"] is None
    assert len(admitted["native_identities"]) == 2
    assert (root / "responses/batch-0003.prompt.txt.gz").is_file()
    assert not (root / "responses/batch-0003.json").exists()
    assert not (root / "responses/attempt-lifecycle/batch-0003").exists()
    assert not (root / "responses/grok-broker/batch-0003-attempt-0001").exists()
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_full_admission_rejects_partial_prefix(partial):
    root, routes, runtime, source = partial
    with pytest.raises(ValueError, match="prefix inventory"):
        subject.admit_pass(root, source=source, batch_size=32, approved_routes=routes, runtime=runtime)


@pytest.mark.parametrize("expected_batches", [0, 1, 3, 7])
def test_prefix_admission_rejects_wrong_expected_count(partial, expected_batches):
    root, routes, runtime, source = partial
    with pytest.raises(ValueError):
        subject.admit_prefix(root, source=source, batch_size=32, approved_routes=routes,
                             expected_batches=expected_batches, runtime=runtime)
