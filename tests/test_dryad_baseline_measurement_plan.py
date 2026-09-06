from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_measurement_plan.py"
PUBLIC_INPUTS = Path.home() / "Documents/cwr-dryad-pilot-source-freeze-20260905-r1/public-inputs.json"


def load():
    spec = importlib.util.spec_from_file_location("dryad_baseline_measurement_plan", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rendered_baseline():
    subject = load()
    runtime, _ = subject._runtime(
        subject.PROTOCOL_PATH.read_bytes(),
        subject._contract()[1]["execution"]["response_schema_mode"],
    )
    generator = {"evidence_class": "synthetic_test_only", "git_commit": "0" * 40, "files": {}}
    plan, artifacts = subject.build_plan(PUBLIC_INPUTS.read_bytes(), runtime, generator=generator)
    return subject, plan, artifacts


def test_fixed_baseline_geometry_schema_and_payload_identity(rendered_baseline) -> None:
    subject, plan, artifacts = rendered_baseline
    assert plan["evidence_class"] == "provider_free_fixed_baseline_measurement_plan"
    assert plan["dispatch_batch_size"] == 8
    assert plan["empirical_batch_cap"] is None
    assert plan["native_admission"] is False
    assert plan["execution_authority"] is False
    assert "cap" not in plan and "qualification_admission" not in plan
    assert plan["counts"] == {
        "train_stories": 176,
        "dev_stories": 60,
        "stories": 236,
        "questions_per_story": 178,
        "logical_requests": 5428,
        "complete_passes_per_endpoint": 236,
        "logical_requests_per_endpoint": 5428,
    }
    assert len(plan["passes"]) == 236 and len(plan["requests"]) == 5428
    assert plan["namespace"] == {
        "name": "baseline8-v1",
        "pass_prefix": "baseline8-v1/",
        "logical_sample_prefix": "baseline8-v1-",
        "disallowed_qualification_pass_prefixes": ["size-", "measurement/"],
        "disallowed_qualification_logical_sample_prefixes": ["qualification-", "measurement-"],
    }
    assert all(
        item["purpose"] == "fresh_fixed_baseline_measurement"
        and item["batch_size"] == 8
        and item["batches"] == 23
        and item["logical_sample_id"].startswith("baseline8-v1-")
        and item["pass_id"].startswith("baseline8-v1/")
        for item in plan["passes"]
    )
    assert len({item["opaque_story_id"] for item in plan["passes"]}) == 236
    for item in plan["requests"]:
        assert item["endpoint_user_payloads"]["grok"] == item["endpoint_user_payloads"]["sol"]
        schema_raw = artifacts[item["schema_path"]]
        schema = json.loads(schema_raw)
        assert hashlib.sha256(schema_raw).hexdigest() == item["schema_sha256"]
        assert len(schema_raw) == item["schema_bytes"]
        assert schema["properties"]["verdicts"]["minItems"] == len(item["question_ids"])
        assert schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"] == item["question_ids"]
    assert hashlib.sha256(artifacts["plan.json"]).hexdigest() == hashlib.sha256(subject._canonical(plan)).hexdigest()


def test_baseline_inherits_only_whitelisted_parent_sections(rendered_baseline) -> None:
    _, plan, _ = rendered_baseline
    assert set(plan["parent_protocol"]) == {"path", "sha256", "inherited_sections"}
    assert set(plan["parent_protocol"]["inherited_sections"]) == {
        "source", "human_targets", "model_score", "optimization", "comparison", "runtime_bindings"
    }
    contract = json.loads((PACKAGE / "baseline-measurement-v1.json").read_bytes())
    assert contract["parent_protocol"]["excluded_sections"] == ["execution", "shared_runtime_bindings"]
    assert plan["predecessor_evidence"] == contract["predecessor_evidence"]
    assert "shared_runtime_bindings" not in plan["parent_protocol"]["inherited_sections"]


def test_contract_rejects_unknown_and_malformed_shapes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    original = json.loads((PACKAGE / "baseline-measurement-v1.json").read_bytes())
    unknown = tmp_path / "unknown-contract.json"
    unknown.write_text(json.dumps({**original, "unexpected": True}), encoding="utf-8")
    monkeypatch.setattr(subject, "CONTRACT_PATH", unknown)
    monkeypatch.setattr(subject, "CONTRACT_SHA256", hashlib.sha256(unknown.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="contract"):
        subject._contract()
    malformed = tmp_path / "malformed-contract.json"
    malformed.write_bytes(b'{"schema_version": 1, "schema_version": 2}')
    monkeypatch.setattr(subject, "CONTRACT_PATH", malformed)
    monkeypatch.setattr(subject, "CONTRACT_SHA256", hashlib.sha256(malformed.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="malformed"):
        subject._contract()


def test_predecessor_evidence_drift_rejects_without_mutating_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    _, contract = subject._contract()
    first = subject.ROOT / contract["predecessor_evidence"][0]["path"]
    original_read_bytes = Path.read_bytes

    def drift(path: Path) -> bytes:
        if path.resolve() == first.resolve():
            return b"synthetic predecessor drift"
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", drift)
    with pytest.raises(ValueError, match="predecessor hash drift"):
        subject._predecessors(contract)


def test_renderer_rejects_unsafe_synthetic_opaque_id() -> None:
    subject = load()
    renderer, _ = subject._renderer()
    rows = [
        {"opaque_story_id": f"dryad-{index:024x}", "story_text": "synthetic"}
        for index in range(236)
    ]
    rows[0]["opaque_story_id"] = "../synthetic-escape"
    raw = json.dumps({"TRAIN": rows[:176], "DEV": rows[176:]}).encode("utf-8")
    with pytest.raises(ValueError, match="identity"):
        renderer.load_inputs(raw, expected_sha256=renderer.digest(raw))


def test_runtime_compilation_does_not_read_shared_provider_state_or_open_network(monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    original_read_bytes = Path.read_bytes
    original_helper = subject._helper
    reads: list[Path] = []
    blocked_roots = (
        (Path.home() / ".codex" / "tools" / "model_work_queue").resolve(),
        (Path.home() / ".codex" / "state" / "model-work-queue").resolve(),
    )

    def guarded_read(path: Path) -> bytes:
        resolved = path.resolve()
        assert not any(resolved.is_relative_to(root) for root in blocked_roots)
        reads.append(resolved)
        return original_read_bytes(path)

    def guarded_helper():
        helper, raw = original_helper()
        helper.load_runtime = lambda *args, **kwargs: pytest.fail("native load_runtime must not run")
        return helper, raw

    def blocked_network(*args, **kwargs):
        pytest.fail("baseline runtime compilation must not open a network connection")

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(subject, "_helper", guarded_helper)
    monkeypatch.setattr(socket, "create_connection", blocked_network)
    monkeypatch.setattr(socket, "socket", blocked_network)
    runtime, _ = subject._runtime(
        subject.PROTOCOL_PATH.read_bytes(),
        subject._contract()[1]["execution"]["response_schema_mode"],
    )
    runtime.verify()
    assert reads and all(path.is_relative_to(subject.REPOSITORY) for path in reads)


def test_prepare_verify_rejects_extra_and_drift_with_synthetic_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "public-inputs.json"
    source.write_bytes(b"synthetic public inputs")
    captured = {
        Path(subject.__file__).resolve(): Path(subject.__file__).read_bytes(),
        subject.PROTOCOL_PATH: subject.PROTOCOL_PATH.read_bytes(),
    }
    generator = {"evidence_class": "synthetic_test_only", "git_commit": "a" * 40, "files": {}}
    runtime = type("Runtime", (), {"verify": lambda self: None})()

    monkeypatch.setattr(subject, "_sources", lambda: captured)
    monkeypatch.setattr(subject, "_generator_identity", lambda value, commit=None: generator)
    monkeypatch.setattr(subject, "_runtime", lambda protocol, response_schema_mode: (runtime, {}))
    def build(raw, received_runtime, *, generator):
        assert raw == b"synthetic public inputs" and received_runtime is runtime
        plan = {"generator": generator}
        return plan, {"plan.json": subject._canonical(plan), "inputs/synthetic.txt": b"synthetic"}
    monkeypatch.setattr(subject, "build_plan", build)

    output = tmp_path / "output"
    prepared = subject.prepare(source, output)
    assert subject.verify(source, output) == prepared
    (output / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        subject.verify(source, output)
    (output / "extra.txt").unlink()
    (output / "inputs/synthetic.txt").write_bytes(b"drift")
    with pytest.raises(ValueError, match="byte drift"):
        subject.verify(source, output)


def test_output_rejects_source_overlap(tmp_path: Path) -> None:
    subject = load()
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "public-inputs.json"
    source.write_bytes(PUBLIC_INPUTS.read_bytes())
    with pytest.raises(ValueError, match="overlaps"):
        subject._output(source, source.parent / "baseline", fresh=True)
    with pytest.raises(ValueError, match="overlaps"):
        subject._output(source, PACKAGE / "baseline", fresh=True)
