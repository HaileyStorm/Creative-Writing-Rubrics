"""Synthetic contract tests for the bounded Dryad v5 suffix executor."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_grok_v5_suffix.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def old_prefix_identities() -> list[dict[str, object]]:
    return [
        *[{"request_id_hash": f"{1000 + index:064x}", "session_id_hash": f"{2000 + index:064x}", "observed_turns": 1} for index in range(69)],
        *[{"request_id_hash": f"{index + 1:064x}", "session_id_hash": f"{index + 31:064x}", "observed_turns": 1} for index in range(10)],
    ]


def load():
    spec = importlib.util.spec_from_file_location("dryad_grok_v5_suffix_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_layout(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    subject = load()
    plan_root = tmp_path / "plan"
    old_execution = tmp_path / "old-execution"
    old_prefix = tmp_path / "old-prefix-run"
    suffix = tmp_path / "suffix"
    package_root = tmp_path / "candidate-package"
    for path in (plan_root, old_execution, old_prefix, suffix, package_root):
        path.mkdir()
    (old_execution / "immutable.txt").write_text("old execution", encoding="utf-8")
    (old_prefix / "immutable.txt").write_text("old recovered pass", encoding="utf-8")
    recovered_manifest = old_prefix / "recovered-study.json"
    recovered_manifest.write_bytes(canonical({"synthetic": "recovered-study"}))
    story = plan_root / "inputs" / "story.txt"
    story.parent.mkdir()
    story.write_text("A synthetic Dryad story.", encoding="utf-8")
    prompt = plan_root / "prompts" / "fixed.txt"
    prompt.parent.mkdir()
    prompt.write_text("synthetic frozen prompt", encoding="utf-8")
    schema = plan_root / "schemas" / "fixed.json"
    schema.parent.mkdir()
    schema.write_bytes(canonical({"type": "object"}))
    story_raw, prompt_raw, schema_raw = story.read_bytes(), prompt.read_bytes(), schema.read_bytes()
    passes = []
    requests = []
    for index in range(1, 237):
        pass_id = f"baseline8-v1/train/{index:04d}/synthetic-{index:03d}"
        passes.append({
            "pass_id": pass_id,
            "logical_sample_id": f"logical-{index:03d}",
            "opaque_story_id": f"opaque-{index:03d}",
            "input_path": "inputs/story.txt",
            "source_sha256": digest(story_raw),
            "source_bytes": len(story_raw),
        })
        for batch in range(1, 24):
            ordinal = (index - 1) * 23 + batch
            questions = [f"q{(batch - 1) * 8 + offset:03d}" for offset in range(8 if batch < 23 else 2)]
            requests.append({
                "ordinal": ordinal,
                "pass_id": pass_id,
                "logical_sample_id": f"logical-{index:03d}",
                "batch_number": batch,
                "question_ids": questions,
                "prompt_path": "prompts/fixed.txt",
                "prompt_sha256": digest(prompt_raw),
                "prompt_bytes": len(prompt_raw),
                "schema_path": "schemas/fixed.json",
                "schema_sha256": digest(schema_raw),
                "schema_bytes": len(schema_raw),
            })
    plan = {"dispatch_batch_size": 8, "empirical_batch_cap": None, "passes": passes, "requests": requests}
    plan_raw = canonical(plan)
    (plan_root / "plan.json").write_bytes(plan_raw)
    subject.PLAN_SHA256 = digest(plan_raw)
    prefix_manifest = tmp_path / "prefix.json"
    prefix_review = tmp_path / "prefix-review.json"
    prefix_manifest.write_bytes(canonical({
        "schema_version": 1,
        "decision": "GO_actual_prefix_through80",
        "evidence_class": "independent_actual_cohort8_settlement_and_mixed_prefix_replay",
        "anchors": {"plan_sha256": subject.PLAN_SHA256, "study70_manifest_sha256": digest(recovered_manifest.read_bytes())},
        "counts": {"logical_contacts": 80, "native_contacts": 79, "study_recovered_contacts": 1,
                   "study_recovered_ordinals": [70], "new_native_contacts": 10, "remaining_logical_requests": 5348},
        "evidence_limits": {"request81_present": False, "execution_or_resend_authority": False, "native_or_source_or_route_writes": 0},
        "native_identity_commitment_fields": ["request_id_hash", "session_id_hash", "observed_turns"],
        "native_identity_commitment_sha256": subject.OLD_PREFIX_NATIVE_IDENTITY_COMMITMENT_SHA256,
        "unique_native_request_ids": 79, "unique_native_session_ids": 79,
        "per_pass": [
            {"pass_id": passes[0]["pass_id"], "checkpoint_count": 23, "run_root": str(old_execution / "run-1"), "native_records": 23, "study_recovered_records": 0},
            {"pass_id": passes[1]["pass_id"], "checkpoint_count": 23, "run_root": str(old_execution / "run-2"), "native_records": 23, "study_recovered_records": 0},
            {"pass_id": passes[2]["pass_id"], "checkpoint_count": 23, "run_root": str(old_execution / "run-3"), "native_records": 23, "study_recovered_records": 0},
            {"pass_id": passes[3]["pass_id"], "checkpoint_count": 11, "run_root": str(old_prefix), "accepted_verdicts": 88, "native_records": 10, "study_recovered_records": 1},
        ],
    }))
    prefix_review.write_bytes(canonical({
        "schema_version": 1, "decision": "GO_cohort8_71_through80",
        "evidence_class": "independent_actual_dryad_cohort8_review", "provider_calls": 0,
        "requests71_through80_absent": True, "resend70_authority": False,
        "root_run_cohort8_arguments": {"execution_root": str(old_execution), "expected_plan_sha256": subject.PLAN_SHA256},
    }))
    (package_root / "candidate-manifest.json").write_bytes(canonical({"synthetic": "candidate"}))
    runtime_manifest = tmp_path / "runtime-v5.json"
    runtime_manifest.write_bytes(canonical({"synthetic": "runtime-v5"}))
    return SimpleNamespace(
        subject=subject, plan_root=plan_root, old_execution=old_execution, old_prefix=old_prefix, suffix=suffix,
        package_root=package_root, prefix_manifest=prefix_manifest, prefix_review=prefix_review,
        recovered_manifest=recovered_manifest, runtime_manifest=runtime_manifest,
        runtime_loader=PACKAGE / "baseline_native_runtime_v5.py",
        old_runtime_manifest=PACKAGE / "baseline-runtime-v1.json",
        old_runtime_loader=PACKAGE / "baseline_native_runtime.py",
        v3=ROOT / "src/hbqrs/grok_broker_transport_v3.py", recovered_source=PACKAGE / "baseline_recovered_study.py",
        executor=SOURCE, plan=plan,
    )


def prepare(layout) -> str:
    subject = layout.subject
    result = subject.prepare_suffix_epoch(
        plan_root=layout.plan_root,
        old_execution_root=layout.old_execution,
        old_prefix_run_root=layout.old_prefix,
        suffix_root=layout.suffix,
        old_prefix_manifest_path=layout.prefix_manifest,
        old_prefix_review_path=layout.prefix_review,
        recovered_study_manifest_path=layout.recovered_manifest,
        runtime_manifest_path=layout.runtime_manifest,
        runtime_package_root=layout.package_root,
        runtime_loader_path=layout.runtime_loader,
        old_runtime_manifest_path=layout.old_runtime_manifest,
        old_runtime_loader_path=layout.old_runtime_loader,
        expected_plan_sha256=subject.PLAN_SHA256,
        expected_old_prefix_manifest_sha256=digest(layout.prefix_manifest.read_bytes()),
        expected_old_prefix_review_sha256=digest(layout.prefix_review.read_bytes()),
        expected_recovered_study_manifest_sha256=digest(layout.recovered_manifest.read_bytes()),
        expected_recovery_adoption_sha256="a" * 64,
        expected_recovery_amendment_sha256="b" * 64,
        expected_runtime_manifest_sha256=digest(layout.runtime_manifest.read_bytes()),
        expected_runtime_package_manifest_sha256=digest((layout.package_root / "candidate-manifest.json").read_bytes()),
        expected_runtime_loader_sha256=digest(layout.runtime_loader.read_bytes()),
        expected_old_runtime_manifest_sha256=digest(layout.old_runtime_manifest.read_bytes()),
        expected_old_runtime_loader_sha256=digest(layout.old_runtime_loader.read_bytes()),
        expected_v3_sha256=digest(layout.v3.read_bytes()),
        expected_recovered_study_sha256=digest(layout.recovered_source.read_bytes()),
        expected_executor_sha256=digest(layout.executor.read_bytes()),
    )
    assert result["provider_calls_made"] == 0 and result["execution_authority"] is False
    return result["epoch_sha256"]


@pytest.fixture
def layout(tmp_path: Path):
    return build_layout(tmp_path)


@pytest.fixture
def epoch(layout) -> tuple[object, str]:
    return layout, prepare(layout)


def reviewed(layout, epoch_sha256: str) -> tuple[Path, str, dict[str, object]]:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    route = {
        "name": "synthetic-v5-route", "provider": "xai_grok_build", "adapter": "grok_exec",
        "model": "grok-4.6", "reasoning_effort": "high", "timeout_seconds": 300,
        "max_concurrency": 1, "nonvisual_max_turns": 1,
        "capabilities": ["public_synthetic", "grok_nonvisual_history_v5"],
        "nonvisual_transport_contract": "grok_nonvisual_history_v5",
    }
    epoch_value = json.loads((layout.suffix / "suffix-epoch.json").read_bytes())
    value = {
        "schema_version": 1, "decision": "approved_dryad_grok_v5_suffix_epoch", "epoch_sha256": epoch_sha256,
        "plan_sha256": layout.subject.PLAN_SHA256, "executor_sha256": epoch_value["executor_source"]["sha256"],
        "runtime_manifest_sha256": epoch_value["runtime_manifest"]["sha256"],
        "runtime_package_manifest_sha256": epoch_value["runtime_package"]["manifest_sha256"],
        "v3_sha256": epoch_value["v3_source"]["sha256"],
        "old_prefix_manifest_sha256": epoch_value["old_prefix_manifest"]["sha256"],
        "old_prefix_review_sha256": epoch_value["old_prefix_review"]["sha256"],
        "candidate_package_root": epoch_value["runtime_package"]["root"],
        "old_execution_inventory_sha256": epoch_value["old_execution_inventory_sha256"],
        "old_prefix_run_inventory_sha256": epoch_value["old_prefix_run_inventory_sha256"],
        "suffix_ordinals": [81, 5428],
        "route": route, "route_sha256": digest(canonical(route)), "gate": {"state": "synthetic-healthy"},
        "gate_sha256": digest(canonical({"state": "synthetic-healthy"})),
        "reviewed_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + __import__("datetime").timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    }
    path = layout.suffix / "independent-review.json"
    path.write_bytes(canonical(value))
    return path, digest(path.read_bytes()), value


class SyntheticRunner:
    VALIDATION_FEEDBACK_POLICY = "invalid_exact_quote_to_summary_v1"
    EVIDENCE_NORMALIZATION_POLICY = "invalid_exact_quote_to_summary_v1"

    def __init__(self) -> None:
        self.contexts: list[dict[str, object]] = []

    def _before_provider_attempt_context(self, **kwargs):
        value = {
            "run": {"run_id": kwargs["run_id"], "config_sha256": kwargs["config_sha256"]},
            "provider": {"provider": kwargs["provider"], "model": kwargs["model"], "reasoning": kwargs["reasoning"], "endpoint": kwargs["endpoint"]},
            "batch": {"number": kwargs["batch_number"], "question_ids": list(kwargs["question_ids"])},
            "attempt": {"number": kwargs["attempt_number"], "batch_attempts": kwargs["batch_attempts"]},
            "prompt": {"text": kwargs["effective_prompt"], "sha256": digest(kwargs["effective_prompt"].encode("utf-8"))},
            "response_schema": {"text": kwargs["schema_path"].read_text(encoding="utf-8"), "sha256": digest(kwargs["schema_path"].read_bytes())},
            "validation_feedback_policy": kwargs["feedback_policy"], "validation_feedback": kwargs["feedback"],
            "rejected_chain": dict(kwargs["rejected_chain"]), "output_dir": str(kwargs["destination"]),
        }
        self.contexts.append(value)
        return value

    def _validate_grok_transport_evidence(self, output_dir: Path, metadata: object) -> None:
        assert Path(output_dir).is_dir()
        assert isinstance(metadata, dict) and metadata["model"] == "grok-4.6"
        assert set(metadata["provider_artifacts"]) == {"request", "context", "outcome", "envelope", "receipt"}

    @staticmethod
    def _provider_artifact(output_dir: Path, path: Path) -> dict[str, object]:
        raw = path.read_bytes()
        return {"path": path.relative_to(output_dir).as_posix(), "bytes": len(raw), "sha256": digest(raw)}

    def _parse_model_json(self, raw: str):
        return json.loads(raw)

    def _normalize_batch(self, payload: dict[str, object], *, expected_ids, **_kwargs):
        verdicts = payload["verdicts"]
        assert [item["question_id"] for item in verdicts] == list(expected_ids)
        return [dict(item) for item in verdicts]


class SyntheticAdapter:
    @staticmethod
    def _parse_grok_envelope(raw: bytes, *, session_id: str, **_kwargs):
        value = json.loads(raw)
        assert value["sessionId"] == session_id and isinstance(value["requestId"], str)
        return value["structuredOutput"], {
            "request_id_hash": digest(value["requestId"].encode("utf-8")),
            "session_id_hash": digest(session_id.encode("utf-8")),
            "observed_turns": 1,
        }, {"status": "not_reported"}


class SyntheticBroker:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _parse_grok_exec_envelope(self, raw: bytes, _route: dict[str, object], _request: dict[str, object], *, expected_session_id: str):
        value = json.loads(raw)
        assert value["control"] == {"version": 1, "state": "completed"}
        result = value["result"]
        assert result["runtime"]["session_id_hash"] == digest(expected_session_id.encode("utf-8"))
        return SimpleNamespace(state="completed", result=result)


class SyntheticTransport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.bound: list[dict[str, object]] = []
        self._V5_NONVISUAL_TRANSPORT_CONTRACT = {
            "schema_version": 1, "name": "grok_nonvisual_history_v5", "prompt_utf8_bytes": 73_728,
        }
        self._V5_TRANSPORT_CONTRACT_SHA256 = digest(canonical(self._V5_NONVISUAL_TRANSPORT_CONTRACT))

    def bind_grok_broker_transport(self, *, broker, route, before_contact, runtime_check):
        self.bound.append({"broker": broker, "route": dict(route)})

        def invoke(context):
            runtime_check()
            before_contact(context)
            if self.fail:
                raise RuntimeError("synthetic post-admission failure")
            destination = Path(context["output_dir"])
            evidence_root = destination / "responses" / "grok-broker" / f"batch-{context['batch']['number']:04d}-attempt-0001"
            evidence_root.mkdir(parents=True, exist_ok=True)
            verdicts = [{"question_id": question_id, "verdict": "YES"} for question_id in context["batch"]["question_ids"]]
            batch = context["batch"]["number"]
            prompt, _schema, _output_dir, _batch, _attempt, bindings = self._context_bindings(context, route)
            request = {"prompt": prompt}
            output = {"verdicts": verdicts}
            run_seed = int(digest(context["run"]["run_id"].encode("utf-8"))[:12], 16)
            session = f"00000000-0000-0000-0000-{(run_seed + batch) % 10**12:012d}"
            request_id = f"request-{digest(context['run']['run_id'].encode('utf-8'))[:16]}-{batch}"
            envelope = canonical({"sessionId": session, "requestId": request_id, "structuredOutput": output})
            runtime = {
                "adapter_version": 5, "requested_model": route["model"], "requested_reasoning_effort": route["reasoning_effort"],
                "identity_evidence": "requested_only", "reasoning_attested": False,
                "execution_policy": "bounded_nonvisual_deny_wins_attested", "nonvisual_max_turns": 1, "observed_turns": 1,
                "tool_policy_attestation_hash": "a" * 64, "execution_contract": bindings["execution_contract"],
                "usage_telemetry": {"status": "not_reported"}, "session_id_hash": digest(session.encode("utf-8")),
                "request_id_hash": digest(request_id.encode("utf-8")), "envelope_hash": digest(envelope),
            }
            result = {
                "schema_version": 2, "request_hash": digest(canonical(request)), "output": output,
                "output_hash": digest(canonical(output)), "runtime": runtime,
                "native_envelope_artifact": {"schema_version": 1, "sha256": digest(envelope), "byte_length": len(envelope)},
            }
            payloads = {
                "request": canonical(request), "context": canonical(bindings),
                "outcome": canonical({"state": "completed", "result": result, "failure": None}), "envelope": envelope,
            }
            for name, raw in payloads.items():
                (evidence_root / f"{name}.json").write_bytes(raw)
            receipt = {
                "schema_version": 1, "source_sha256": self.source_sha256, "route_sha256": digest(canonical(route)),
                "request_sha256": digest(payloads["request"]), "context_sha256": digest(payloads["context"]),
                "schema_sha256": bindings["response_schema_sha256"], "result_sha256": digest(canonical(result)),
                "outcome_sha256": digest(payloads["outcome"]), "envelope_sha256": digest(envelope),
                "session_id_hash": runtime["session_id_hash"], "request_id_hash": runtime["request_id_hash"],
            }
            (evidence_root / "receipt.json").write_bytes(canonical(receipt))
            artifacts = {name: {"path": path.relative_to(destination).as_posix(), "bytes": len(path.read_bytes()), "sha256": digest(path.read_bytes())}
                         for name in ("request", "context", "outcome", "envelope", "receipt")
                         for path in [evidence_root / f"{name}.json"]}
            return json.dumps(output, ensure_ascii=False), {
                "model": "grok-4.6", "evidence_sha256": artifacts["receipt"]["sha256"],
                "request_id_sha256": runtime["request_id_hash"], "session_id_sha256": runtime["session_id_hash"],
                "reasoning_attested": False, "tool_free": True, "provider_artifacts": artifacts,
            }

        return invoke

    def _context_bindings(self, context: dict[str, object], route: dict[str, object]):
        prompt = context["prompt"]["text"]
        schema = json.loads(context["response_schema"]["text"])
        execution = {
            "schema_version": 1, "output_schema_hash": digest(canonical(schema)), "max_turns": 1,
            "tools": "deny_wins_none_attested", "staged_prompt_sha256": digest(prompt.encode("utf-8")),
            "staged_prompt_byte_length": len(prompt.encode("utf-8")),
            "nonvisual_transport_contract": self._V5_NONVISUAL_TRANSPORT_CONTRACT,
            "nonvisual_transport_contract_sha256": self._V5_TRANSPORT_CONTRACT_SHA256,
        }
        bindings = {
            "response_schema_sha256": digest(context["response_schema"]["text"].encode("utf-8")),
            "execution_contract": execution, "batch": context["batch"], "route": dict(route),
        }
        return prompt, schema, Path(context["output_dir"]), context["batch"]["number"], 1, bindings


def install_synthetic_runtime(layout, monkeypatch: pytest.MonkeyPatch, *, fail: bool = False):
    subject = layout.subject
    runner = SyntheticRunner()
    transport = SyntheticTransport(fail=fail)
    transport.source_sha256 = digest(layout.v3.read_bytes())
    ids = [f"q{index:03d}" for index in range(178)]
    runtime = SimpleNamespace(
        runner=runner,
        transport=transport,
        transport_sha256=digest(layout.v3.read_bytes()),
        broker=SimpleNamespace(Broker=SyntheticBroker),
        adapter=SyntheticAdapter(),
        questions=[{"question": {"id": question_id}} for question_id in ids],
        verify=lambda: None,
        core=SimpleNamespace(),
        modules={},
        bundle={},
    )
    monkeypatch.setattr(subject, "_runtime_from_epoch", lambda _epoch: runtime)
    return runtime, runner, transport


def test_prepare_is_provider_free_and_rejects_plan_or_prefix_drift(layout) -> None:
    before = {path: path.read_bytes() for path in (layout.old_execution / "immutable.txt", layout.old_prefix / "immutable.txt")}
    epoch_sha256 = prepare(layout)
    epoch = json.loads((layout.suffix / "suffix-epoch.json").read_bytes())
    assert epoch["first_ordinal"] == 81 and epoch["last_ordinal"] == 5428
    assert epoch["provider_calls_made"] == 0 and epoch["execution_authority"] is False
    assert {path: path.read_bytes() for path in before} == before
    assert isinstance(epoch_sha256, str) and len(epoch_sha256) == 64

    drift = build_layout(layout.suffix.parent / "plan-drift")
    drift.plan_root.joinpath("plan.json").write_bytes(drift.plan_root.joinpath("plan.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="plan"):
        prepare(drift)
    assert not (drift.suffix / "suffix-epoch.json").exists()

    drift = build_layout(layout.suffix.parent / "prefix-drift")
    prefix = json.loads(drift.prefix_manifest.read_bytes())
    prefix["counts"]["native_contacts"] = 78
    drift.prefix_manifest.write_bytes(canonical(prefix))
    with pytest.raises(ValueError, match="prefix"):
        prepare(drift)
    assert not (drift.suffix / "suffix-epoch.json").exists()


def test_dispatch_rejects_preexisting_or_nonnext_attempt_without_broker(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, _review = reviewed(layout, epoch_sha256)
    calls: list[object] = []
    monkeypatch.setattr(subject, "_runtime_from_epoch", lambda _epoch: pytest.fail("runtime must not load before attempt guard"))
    path = subject._attempt_path(layout.suffix, 81, "attempt-start.json")
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical({"ordinal": 81, "epoch_sha256": epoch_sha256}))
    with pytest.raises(ValueError, match="terminal status"):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
            reviewed_path=review_path, expected_review_sha256=review_sha256,
            queue_root=layout.suffix.parent / "queue", broker_factory=lambda *_: calls.append(True),
        )
    assert calls == []

    future = build_layout(layout.suffix.parent / "future-attempt")
    future_epoch = prepare(future)
    future_review, future_review_sha, _ = reviewed(future, future_epoch)
    future_start = future.subject._attempt_path(future.suffix, 82, "attempt-start.json")
    future_start.parent.mkdir(parents=True)
    future_start.write_bytes(canonical({"ordinal": 82, "epoch_sha256": future_epoch}))
    with pytest.raises(ValueError, match="reconcil"):
        future.subject.dispatch_one(
            suffix_root=future.suffix, expected_epoch_sha256=future_epoch, ordinal=81,
            reviewed_path=future_review, expected_review_sha256=future_review_sha,
            queue_root=future.suffix.parent / "queue", broker_factory=lambda *_: pytest.fail("future attempt must block broker"),
        )


@pytest.mark.parametrize("field,value", [("timeout_seconds", 300.0), ("max_concurrency", True), ("nonvisual_max_turns", True)])
def test_review_route_geometry_rejects_wrong_numeric_types_before_attempt_start(epoch, monkeypatch: pytest.MonkeyPatch, field: str, value: object) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, _review_sha, review_value = reviewed(layout, epoch_sha256)
    review_value["route"][field] = value
    review_value["route_sha256"] = digest(canonical(review_value["route"]))
    review_path.write_bytes(canonical(review_value))
    review_sha = digest(review_path.read_bytes())
    monkeypatch.setattr(subject, "_runtime_from_epoch", lambda _epoch: pytest.fail("invalid route must not load runtime"))
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    with pytest.raises(ValueError, match="route"):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
            reviewed_path=review_path, expected_review_sha256=review_sha, queue_root=queue,
        )
    assert not subject._attempt_path(layout.suffix, 81, "attempt-start.json").exists()


def test_direct_callback_binds_exact_frozen_prompt_schema_ids_and_v3_hash(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, _review = reviewed(layout, epoch_sha256)
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    runtime, runner, transport = install_synthetic_runtime(layout, monkeypatch)
    factories: list[tuple[Path, object]] = []

    result = subject.dispatch_one(
        suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
        reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
        broker_factory=lambda root, constructor: (factories.append((root, constructor)), constructor(root))[1],
    )
    assert result["status"] == "completed_pending_replay" and result["provider_calls_made"] == 1
    assert len(factories) == len(transport.bound) == len(runner.contexts) == 1
    context = runner.contexts[0]
    row = layout.plan["requests"][80]
    assert context["batch"] == {"number": 12, "question_ids": row["question_ids"]}
    assert context["prompt"]["text"].encode("utf-8") == (layout.plan_root / row["prompt_path"]).read_bytes()
    assert context["response_schema"]["text"].encode("utf-8") == (layout.plan_root / row["schema_path"]).read_bytes()
    start = json.loads(subject._attempt_path(layout.suffix, 81, "attempt-start.json").read_bytes())
    assert start["v3_sha256"] == runtime.transport_sha256 == digest(layout.v3.read_bytes())
    assert (subject._attempt_path(layout.suffix, 81, "contact-admission.json")).is_file()
    terminal = json.loads(subject._attempt_path(layout.suffix, 81, "terminal.json").read_bytes())
    assert terminal["status"] == "completed" and terminal["contact_admitted"] is True


def test_dispatches_later_pass_batch_one_and_final_batch_5428(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, _review = reviewed(layout, epoch_sha256)
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    _runtime, runner, _transport = install_synthetic_runtime(layout, monkeypatch)
    monkeypatch.setattr(subject, "_next_ordinal", lambda *_args: 93)
    subject.dispatch_one(
        suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=93,
        reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
    )
    assert runner.contexts[-1]["batch"]["number"] == 1
    assert json.loads(subject._attempt_path(layout.suffix, 93, "attempt-start.json").read_bytes())["pass_id"].endswith("synthetic-005")

    final_layout = build_layout(layout.suffix.parent / "final-boundary")
    final_epoch = prepare(final_layout)
    final_review, final_review_sha, _ = reviewed(final_layout, final_epoch)
    final_queue = final_layout.suffix.parent / "queue"
    final_queue.mkdir()
    _runtime, final_runner, _transport = install_synthetic_runtime(final_layout, monkeypatch)
    monkeypatch.setattr(final_layout.subject, "_next_ordinal", lambda *_args: 5428)
    final_layout.subject.dispatch_one(
        suffix_root=final_layout.suffix, expected_epoch_sha256=final_epoch, ordinal=5428,
        reviewed_path=final_review, expected_review_sha256=final_review_sha, queue_root=final_queue,
    )
    assert final_runner.contexts[-1]["batch"]["number"] == 23
    assert json.loads(final_layout.subject._attempt_path(final_layout.suffix, 5428, "attempt-start.json").read_bytes())["pass_id"].endswith("synthetic-236")


def test_dispatch_rejects_wrong_broker_type_or_root(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, _review = reviewed(layout, epoch_sha256)
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    _runtime, _runner, transport = install_synthetic_runtime(layout, monkeypatch)

    class WrongBroker:
        def __init__(self, root: Path) -> None:
            self.root = root

    with pytest.raises(ValueError, match="broker instance"):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
            reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
            broker_factory=lambda _root, _constructor: WrongBroker(queue),
        )
    assert transport.bound == []

    root_layout = build_layout(layout.suffix.parent / "wrong-root")
    root_epoch = prepare(root_layout)
    root_review, root_review_sha, _ = reviewed(root_layout, root_epoch)
    root_queue = root_layout.suffix.parent / "queue"
    root_queue.mkdir()
    _runtime, _runner, transport = install_synthetic_runtime(root_layout, monkeypatch)
    with pytest.raises(ValueError, match="broker instance"):
        root_layout.subject.dispatch_one(
            suffix_root=root_layout.suffix, expected_epoch_sha256=root_epoch, ordinal=81,
            reviewed_path=root_review, expected_review_sha256=root_review_sha, queue_root=root_queue,
            broker_factory=lambda _root, constructor: constructor(root_layout.suffix),
        )
    assert transport.bound == []


def test_failure_and_crash_consume_ordinal_and_missing_terminal_requires_reconciliation(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, _review = reviewed(layout, epoch_sha256)
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    _runtime, _runner, transport = install_synthetic_runtime(layout, monkeypatch, fail=True)
    calls: list[object] = []
    with pytest.raises(RuntimeError, match="post-admission"):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
            reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
            broker_factory=lambda root, constructor: (calls.append(root), constructor(root))[1],
        )
    terminal = json.loads(subject._attempt_path(layout.suffix, 81, "terminal.json").read_bytes())
    assert terminal["status"] == "ambiguous" and terminal["contact_admitted"] is True
    with pytest.raises(ValueError, match="exact next"):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
            reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
            broker_factory=lambda *_: pytest.fail("no automatic resend"),
        )
    assert len(calls) == 1 and len(transport.bound) == 1

    crash_layout = build_layout(layout.suffix.parent / "crash")
    crash_epoch = prepare(crash_layout)
    crash_review, crash_review_sha, _ = reviewed(crash_layout, crash_epoch)
    crash_queue = crash_layout.suffix.parent / "queue"
    crash_queue.mkdir()
    install_synthetic_runtime(crash_layout, monkeypatch, fail=True)
    monkeypatch.setattr(crash_layout.subject, "_terminal", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic crash")))
    with pytest.raises(RuntimeError, match="synthetic crash"):
        crash_layout.subject.dispatch_one(
            suffix_root=crash_layout.suffix, expected_epoch_sha256=crash_epoch, ordinal=81,
            reviewed_path=crash_review, expected_review_sha256=crash_review_sha, queue_root=crash_queue,
        )
    assert crash_layout.subject._attempt_path(crash_layout.suffix, 81, "attempt-start.json").is_file()
    assert not crash_layout.subject._attempt_path(crash_layout.suffix, 81, "terminal.json").exists()
    with pytest.raises(ValueError, match="reconcile"):
        crash_layout.subject.dispatch_one(
            suffix_root=crash_layout.suffix, expected_epoch_sha256=crash_epoch, ordinal=82,
            reviewed_path=crash_review, expected_review_sha256=crash_review_sha, queue_root=crash_queue,
            broker_factory=lambda *_: pytest.fail("missing terminal must block broker"),
        )


def test_mixed_old11_new12_replay_requires_canonical_order_unique_identities_and_scores_once(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, review_value = reviewed(layout, epoch_sha256)
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    runtime, _runner, _transport = install_synthetic_runtime(layout, monkeypatch)
    score_inputs: list[list[dict[str, object]]] = []

    def score_bundle(_modules, _bundle, verdicts, *, artifact_id, task_contract):
        assert artifact_id in {"logical-004", "logical-005"} and task_contract is None
        score_inputs.append([dict(item) for item in verdicts])
        return {"final_score": {"observed": 73.5}, "coverage": 1.0}

    runtime.core = SimpleNamespace(score_bundle=score_bundle)
    old_runtime = SimpleNamespace(questions=runtime.questions, verify=lambda: None)
    monkeypatch.setattr(subject, "_old_runtime_from_epoch", lambda _epoch: old_runtime)
    old_calls: list[dict[str, object]] = []

    def admit_prefix(_root, **kwargs):
        old_calls.append(kwargs)
        return {
            "evidence_class": "mixed_native_and_study_recovered_record_replay",
            "native_record_count": 10, "study_recovered_record_count": 1, "study_recovered_ordinals": [70],
            "verdicts": [{"question_id": f"q{index:03d}", "verdict": "YES"} for index in range(88)],
            "native_identities": [{"request_id_hash": f"{index + 1:064x}", "session_id_hash": f"{index + 31:064x}"} for index in range(10)],
        }

    monkeypatch.setattr(subject, "_load_module", lambda *_args: SimpleNamespace(admit_prefix=admit_prefix))
    monkeypatch.setattr(subject, "_old_prefix_native_identities", lambda **_kwargs: old_prefix_identities())
    for ordinal in range(81, 93):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=ordinal,
            reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
        )
    old_before = {path: path.read_bytes() for path in layout.old_prefix.rglob("*") if path.is_file()}
    result = subject.admit_pass(
        suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256,
        pass_id="baseline8-v1/train/0004/synthetic-004",
        approved_v4_routes={}, approved_v5_routes={review_value["route_sha256"]: review_value["route"]},
    )
    assert old_calls[0]["expected_batches"] == 11
    assert result["old_v4_native_records"] == 10 and result["old_recovered70_records"] == 1
    assert result["new_v5_native_records"] == 12 and result["score"] == 73.5
    assert [item["question_id"] for item in result["verdicts"]] == [f"q{index:03d}" for index in range(178)]
    assert len(score_inputs) == 1 and len(score_inputs[0]) == 178
    assert {path: path.read_bytes() for path in layout.old_prefix.rglob("*") if path.is_file()} == old_before

    for ordinal in range(93, 116):
        subject.dispatch_one(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=ordinal,
            reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
        )
    next_pass = subject.admit_pass(
        suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256,
        pass_id="baseline8-v1/train/0005/synthetic-005",
        approved_v4_routes={}, approved_v5_routes={review_value["route_sha256"]: review_value["route"]},
    )
    assert next_pass["evidence_class"] == "v5_native_full_pass_replay"
    assert (next_pass["old_v4_native_records"], next_pass["old_recovered70_records"], next_pass["new_v5_native_records"]) == (0, 0, 23)
    assert [item["question_id"] for item in next_pass["verdicts"]] == [f"q{index:03d}" for index in range(178)]
    assert len(score_inputs) == 2 and len(score_inputs[1]) == 178


@pytest.mark.parametrize("fault", ["missing", "order", "identity"])
def test_mixed_replay_rejects_missing_order_or_identity_collision(epoch, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    runtime, _runner, _transport = install_synthetic_runtime(layout, monkeypatch)
    runtime.core = SimpleNamespace(score_bundle=lambda *_args, **_kwargs: {"final_score": {"observed": 1.0}, "coverage": 1.0})
    monkeypatch.setattr(subject, "_old_runtime_from_epoch", lambda _epoch: SimpleNamespace(questions=runtime.questions, verify=lambda: None))
    monkeypatch.setattr(subject, "_load_module", lambda *_args: SimpleNamespace(admit_prefix=lambda *_args, **_kwargs: {
        "evidence_class": "mixed_native_and_study_recovered_record_replay", "native_record_count": 10,
        "study_recovered_record_count": 1, "study_recovered_ordinals": [70],
        "verdicts": [{"question_id": f"q{index:03d}", "verdict": "YES"} for index in range(88)],
        "native_identities": [{"request_id_hash": f"{index + 1:064x}", "session_id_hash": f"{index + 31:064x}"} for index in range(10)],
    }))

    def replay(**kwargs):
        row = kwargs["row"]
        batch = row["batch_number"]
        ids = list(row["question_ids"])
        if fault == "missing" and batch == 12:
            ids = ids[:-1]
        if fault == "order" and batch == 12:
            ids = list(reversed(ids))
        identity = {"request_id_hash": f"{batch + 100:064x}", "session_id_hash": f"{batch + 200:064x}"}
        if fault == "identity" and batch == 13:
            identity = {"request_id_hash": f"{12 + 100:064x}", "session_id_hash": f"{12 + 200:064x}"}
        return [{"question_id": question_id, "verdict": "YES"} for question_id in ids], identity

    monkeypatch.setattr(subject, "_replay_suffix_terminal", replay)
    monkeypatch.setattr(subject, "_old_prefix_native_identities", lambda **_kwargs: old_prefix_identities())
    before = {path: path.read_bytes() for path in layout.old_prefix.rglob("*") if path.is_file()}
    with pytest.raises(ValueError):
        subject.admit_pass(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256,
            pass_id="baseline8-v1/train/0004/synthetic-004", approved_v4_routes={}, approved_v5_routes={},
        )
    assert {path: path.read_bytes() for path in layout.old_prefix.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("pass_id", ["baseline8-v1/train/0004/synthetic-004", "baseline8-v1/train/0005/synthetic-005"])
@pytest.mark.parametrize("old_index", [0, 69])
def test_every_pass_rejects_collisions_with_all_79_old_native_identities(epoch, monkeypatch: pytest.MonkeyPatch, pass_id: str, old_index: int) -> None:
    layout, epoch_sha256 = epoch
    subject = layout.subject
    runtime, _runner, _transport = install_synthetic_runtime(layout, monkeypatch)
    runtime.core = SimpleNamespace(score_bundle=lambda *_args, **_kwargs: {"final_score": {"observed": 1.0}, "coverage": 1.0})
    monkeypatch.setattr(subject, "_old_runtime_from_epoch", lambda _epoch: SimpleNamespace(questions=runtime.questions, verify=lambda: None))
    monkeypatch.setattr(subject, "_load_module", lambda *_args: SimpleNamespace(admit_prefix=lambda *_args, **_kwargs: {
        "evidence_class": "mixed_native_and_study_recovered_record_replay", "native_record_count": 10,
        "study_recovered_record_count": 1, "study_recovered_ordinals": [70],
        "verdicts": [{"question_id": f"q{index:03d}", "verdict": "YES"} for index in range(88)],
        "native_identities": old_prefix_identities()[-10:],
    }))
    monkeypatch.setattr(subject, "_old_prefix_native_identities", lambda **_kwargs: old_prefix_identities())
    rows, mixed = subject._pass_requests(layout.plan, pass_id)

    def replay(**kwargs):
        row = kwargs["row"]
        batch = row["batch_number"]
        return ([{"question_id": question_id, "verdict": "YES"} for question_id in row["question_ids"]],
                {"request_id_hash": f"{8000 + batch:064x}", "session_id_hash": f"{9000 + batch:064x}"})

    monkeypatch.setattr(subject, "_replay_suffix_terminal", replay)
    monkeypatch.setattr(subject, "_completed_v5_identities", lambda *_args: [old_prefix_identities()[old_index]])
    with pytest.raises(ValueError, match="overlaps old"):
        subject.admit_pass(
            suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, pass_id=pass_id,
            approved_v4_routes={}, approved_v5_routes={},
        )
    assert mixed is pass_id.endswith("004") and len(rows) == 23


@pytest.mark.parametrize("score", [
    {"final_score": {"observed": True}, "coverage": 1.0},
    {"final_score": {"observed": float("nan")}, "coverage": 1.0},
    {"final_score": {"observed": 101.0}, "coverage": 1.0},
    {"final_score": {"observed": 50.0}, "coverage": True},
    {"final_score": {"observed": 50.0}, "coverage": 0.8799},
    {"final_score": {"observed": 50.0}, "coverage": 1.0, "provisional": True},
    {"final_score": {"observed": 50.0}, "coverage": 1.0, "fail_contract": True},
])
def test_score_qualification_rejects_bool_nonfinite_bounds_and_contract_failures(score) -> None:
    with pytest.raises(ValueError, match="qualified"):
        load()._qualified_score(score)


def test_score_qualification_accepts_exact_numeric_boundaries() -> None:
    assert load()._qualified_score({"final_score": {"observed": 0.0}, "coverage": 0.88}) == (0.0, 0.88)
    assert load()._qualified_score({"final_score": {"observed": 100}, "coverage": 1.0}) == (100, 1.0)


def _semantic_terminal(epoch, monkeypatch: pytest.MonkeyPatch):
    layout, epoch_sha256 = epoch
    subject = layout.subject
    review_path, review_sha256, review_value = reviewed(layout, epoch_sha256)
    queue = layout.suffix.parent / "queue"
    queue.mkdir()
    runtime, _runner, _transport = install_synthetic_runtime(layout, monkeypatch)
    subject.dispatch_one(
        suffix_root=layout.suffix, expected_epoch_sha256=epoch_sha256, ordinal=81,
        reviewed_path=review_path, expected_review_sha256=review_sha256, queue_root=queue,
    )
    epoch_value = json.loads((layout.suffix / "suffix-epoch.json").read_bytes())
    plan = layout.plan
    row = plan["requests"][80]
    passed = next(item for item in plan["passes"] if item["pass_id"] == row["pass_id"])
    terminal_path = subject._attempt_path(layout.suffix, 81, "terminal.json")
    return SimpleNamespace(
        layout=layout, subject=subject, epoch_sha256=epoch_sha256, epoch=epoch_value, runtime=runtime,
        row=row, passed=passed, terminal_path=terminal_path, routes={review_value["route_sha256"]: review_value["route"]},
    )


def _replay_semantic(case) -> None:
    case.subject._replay_suffix_terminal(
        root=case.layout.suffix, epoch_sha256=case.epoch_sha256, epoch=case.epoch,
        runtime=case.runtime, plan_root=case.layout.plan_root, passed=case.passed,
        row=case.row, approved_v5_routes=case.routes,
    )


@pytest.mark.parametrize("artifact", ["request", "context", "envelope", "receipt"])
def test_v3_replay_rejects_each_retained_artifact_binding(epoch, monkeypatch: pytest.MonkeyPatch, artifact: str) -> None:
    case = _semantic_terminal(epoch, monkeypatch)
    terminal = json.loads(case.terminal_path.read_bytes())
    descriptor = terminal["provider_metadata"]["provider_artifacts"][artifact]
    path = case.layout.suffix / "passes" / case.row["pass_id"] / descriptor["path"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        _replay_semantic(case)


def test_v3_replay_rejects_semantic_runtime_drift_after_rebinding_hashes(epoch, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _semantic_terminal(epoch, monkeypatch)
    terminal = json.loads(case.terminal_path.read_bytes())
    run_root = case.layout.suffix / "passes" / case.row["pass_id"]
    artifacts = terminal["provider_metadata"]["provider_artifacts"]
    outcome_path = run_root / artifacts["outcome"]["path"]
    outcome = json.loads(outcome_path.read_bytes())
    outcome["result"]["runtime"]["adapter_version"] = 4
    outcome_path.write_bytes(canonical(outcome))
    receipt_path = run_root / artifacts["receipt"]["path"]
    receipt = json.loads(receipt_path.read_bytes())
    receipt["result_sha256"] = digest(canonical(outcome["result"]))
    receipt["outcome_sha256"] = digest(outcome_path.read_bytes())
    receipt_path.write_bytes(canonical(receipt))
    for name in ("outcome", "receipt"):
        path = run_root / artifacts[name]["path"]
        raw = path.read_bytes()
        artifacts[name] = {"path": artifacts[name]["path"], "bytes": len(raw), "sha256": digest(raw)}
    terminal["provider_metadata"]["evidence_sha256"] = artifacts["receipt"]["sha256"]
    terminal["provider_metadata_sha256"] = digest(canonical(terminal["provider_metadata"]))
    inventory = terminal["provider_evidence_inventory"]
    for name in ("outcome", "receipt"):
        inventory[artifacts[name]["path"]] = artifacts[name]["sha256"]
    case.terminal_path.write_bytes(canonical(terminal))
    with pytest.raises(ValueError, match="v5 runtime"):
        _replay_semantic(case)
