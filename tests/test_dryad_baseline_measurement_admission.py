from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


subject = _module("dryad_baseline_measurement_admission", PACKAGE / "baseline_measurement_admission.py")
ORIGINAL_SOURCE = subject._source


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _terminal_identities() -> tuple[bytes, str, str]:
    records = []
    for ordinal in (number for number in range(1, 35) if number != 28):
        records.append({
            "campaign": "qualification-v2",
            "ordinal": ordinal,
            "receipt_path": f"receipts/{ordinal}.json",
            "receipt_sha256": _hash(f"receipt-{ordinal}".encode()),
            "request_id_hash": _hash(f"trusted-request-{ordinal}".encode()),
            "session_id_hash": _hash(f"trusted-session-{ordinal}".encode()),
        })
    return _json({
        "schema_version": 2,
        "evidence_class": "preserved_predecessor_native_identity_exclusion",
        "completed_identity_records": 33,
        "native_admission": False,
        "execution_authority": False,
        "empirical_batch_cap": None,
        "records": records,
        "unresolved_contact": {
            "automatic_resend_permitted": False,
            "campaign": "qualification-v2",
            "native_identity_claimed": False,
            "ordinal": 28,
            "state": "ambiguous_terminal_no_trusted_native_identity",
            "terminal_proof_sha256": "b35a84feebcdd948bf2a827b67421f9142efa7698650a439a13e9d6ce59e22ba",
        },
    }), records[0]["request_id_hash"], records[0]["session_id_hash"]


@pytest.fixture
def baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Synthetic composition only; it does not load native state or contact a provider."""
    plan_root, execution_root = tmp_path / "plan", tmp_path / "execution"
    plan_root.mkdir()
    execution_root.mkdir()
    public_inputs = tmp_path / "public-inputs.json"
    public_inputs.write_bytes(b"synthetic public inputs")
    runtime_manifest = tmp_path / "runtime.json"
    runtime_manifest.write_bytes(b"synthetic runtime manifest")
    questions = [f"question-{number:03d}" for number in range(178)]
    prompt, schema = b"synthetic prompt", b"synthetic schema"
    (plan_root / "prompts").mkdir()
    (plan_root / "prompts" / "shared.txt").write_bytes(prompt)
    (plan_root / "schemas").mkdir()
    (plan_root / "schemas" / "shared.json").write_bytes(schema)
    route = _hash(b"reviewed route")
    executor = _hash(b"reviewed executor")
    settlement = _hash(b"final settlement")
    passes, requests, contacts, by_pass, by_run_batch = [], [], {}, {}, {}
    ordinal = 0
    for pass_number in range(1, 237):
        pass_id = f"pass-{pass_number:03d}"
        logical_id, opaque_id = f"logical-{pass_number:03d}", f"opaque-{pass_number:03d}"
        source = f"synthetic source {pass_number}".encode()
        source_path = plan_root / "inputs" / f"{pass_id}.txt"
        source_path.parent.mkdir(exist_ok=True)
        source_path.write_bytes(source)
        run_path = f"runs/{pass_id}"
        run_root = execution_root / run_path
        run_root.mkdir(parents=True)
        record = {
            "pass_id": pass_id,
            "logical_sample_id": logical_id,
            "opaque_story_id": opaque_id,
            "input_path": source_path.relative_to(plan_root).as_posix(),
            "run_path": run_path,
            "source_sha256": _hash(source),
            "source_bytes": len(source),
            "batch_size": 8,
            "batches": 23,
        }
        passes.append(record)
        by_pass[pass_id] = []
        for batch_number, start in enumerate(range(0, 178, 8), start=1):
            ordinal += 1
            request = {
                "ordinal": ordinal,
                "pass_id": pass_id,
                "logical_sample_id": logical_id,
                "batch_number": batch_number,
                "question_ids": questions[start:start + 8],
                "prompt_path": "prompts/shared.txt",
                "prompt_sha256": _hash(prompt),
                "prompt_bytes": len(prompt),
                "schema_path": "schemas/shared.json",
                "schema_sha256": _hash(schema),
                "schema_bytes": len(schema),
                "endpoint_user_payloads": {
                    "grok": {"sha256": _hash(prompt), "bytes": len(prompt)},
                    "sol": {"sha256": _hash(prompt), "bytes": len(prompt)},
                },
            }
            requests.append(request)
            by_pass[pass_id].append(request)
            by_run_batch[(run_root, batch_number)] = request
            contacts[ordinal] = {
                "pass_id": pass_id,
                "logical_sample_id": logical_id,
                "source_sha256": record["source_sha256"],
                "prompt_sha256": request["prompt_sha256"],
                "schema_sha256": request["schema_sha256"],
                "execution_source_sha256": executor,
                "checkpoint_sha256": _hash(f"checkpoint-{ordinal}".encode()),
                "route_sha256": route,
                "request_id_hash": _hash(f"request-{ordinal}".encode()),
                "session_id_hash": _hash(f"session-{ordinal}".encode()),
            }
    assert len(passes) == 236 and len(requests) == ordinal == 5428
    plan = {"passes": passes, "requests": requests}
    plan_raw = _json(plan)
    (plan_root / "plan.json").write_bytes(plan_raw)
    plan_artifacts = {
        f"synthetic-artifacts/{number:05d}.json": _hash(f"artifact-{number}".encode())
        for number in range(1, 11095)
    }
    initialization = execution_root / "initialization.json"
    initialization.write_bytes(_json({
        "schema_version": 1,
        "evidence_class": "provider_free_baseline_initialization",
        "plan_sha256": subject.PLAN_SHA256,
        "plan_inventory_sha256": _hash(subject._canonical(plan_artifacts)),
        "plan_files": len(plan_artifacts),
        "runtime_manifest_sha256": _hash(runtime_manifest.read_bytes()),
        "route_sha256": route,
        "execution_source_sha256": executor,
        "public_inputs_sha256": _hash(public_inputs.read_bytes()),
    }))
    terminal_raw, trusted_request, trusted_session = _terminal_identities()
    source_pin = tmp_path / "pinned-dependency.py"
    source_pin.write_bytes(b"synthetic pinned dependency")
    captured = {
        Path(subject.__file__).resolve(): Path(subject.__file__).read_bytes(),
        source_pin: source_pin.read_bytes(),
    }
    state = {
        "native_calls": 0,
        "ledger_calls": 0,
        "runtime_verifications": 0,
        "identity_mode": "unique",
        "checkpoint_mismatch": None,
        "mutation": None,
    }

    def verify_ledger(root, inputs, raw, expected_plan, expected_settlement, **kwargs):
        assert root == execution_root and inputs == public_inputs.read_bytes() and raw == plan_raw
        assert expected_plan == subject.PLAN_SHA256 and expected_settlement == settlement
        assert kwargs == {
            "expected_route_sha256": route,
            "expected_execution_source_sha256": executor,
            "expected_reviewer_task": "synthetic-review",
        }
        state["ledger_calls"] += 1
        return {
            "evidence_class": "provider_free_baseline_ledger_consistency",
            "native_admission": False,
            "execution_authority": False,
            "contacts": contacts,
            "routes": {route: {"kind": "synthetic"}},
            "authorizations": {"synthetic": {"reviewed": True}},
            "head": {"cohort_number": 543, "settlement_sha256": settlement},
        }

    def verify_runtime():
        state["runtime_verifications"] += 1
        if state["mutation"] == "runtime" and state["runtime_verifications"] == 2:
            raise ValueError("Synthetic runtime changed during admission")

    runtime = SimpleNamespace(
        questions=[{"question": {"id": question}} for question in questions],
        verify=verify_runtime,
    )

    def load_runtime(path, *, expected_manifest_sha256):
        assert path == runtime_manifest and expected_manifest_sha256 == _hash(runtime_manifest.read_bytes())
        return runtime

    def admit_pass(run_root, *, source, batch_size, approved_routes, runtime):
        assert batch_size == 8 and approved_routes == {route: {"kind": "synthetic"}}
        state["native_calls"] += 1
        record = next(item for item in passes if item["run_path"] == run_root.relative_to(execution_root).as_posix())
        identities = []
        for request in by_pass[record["pass_id"]]:
            contact = contacts[request["ordinal"]]
            identities.append({
                "request_id_hash": contact["request_id_hash"],
                "session_id_hash": contact["session_id_hash"],
            })
        if state["identity_mode"] == "duplicate":
            identities[1] = identities[0]
        if state["identity_mode"] == "trusted":
            identities[0] = {"request_id_hash": trusted_request, "session_id_hash": trusted_session}
            contacts[by_pass[record["pass_id"]][0]["ordinal"]].update(identities[0])
        if state["mutation"] == "source" and state["native_calls"] == 1:
            source_pin.write_bytes(b"drifted")
        if state["mutation"] == "input" and state["native_calls"] == 1:
            public_inputs.write_bytes(b"drifted")
        return {
            "verdicts": [{"question_id": question, "verdict": "YES"} for question in questions],
            "score": 1,
            "coverage": 1,
            "native_identities": identities,
            "run_manifest_sha256": _hash(record["pass_id"].encode()),
            "checkpoint_head_sha256": _hash((record["pass_id"] + "-head").encode()),
            "evidence_class": "native_record_replay_only",
        }

    monkeypatch.setattr(subject, "_sources", lambda: (
        captured,
        (SimpleNamespace(), SimpleNamespace(verify_ledger=verify_ledger),
         SimpleNamespace(load_runtime=load_runtime), SimpleNamespace(admit_pass=admit_pass)),
        terminal_raw,
    ))
    monkeypatch.setattr(subject, "_plan", lambda *_: (plan, plan_raw, plan_artifacts))

    def synthetic_rows(value, root, execution, runtime_ids):
        assert value is plan and root == plan_root and execution == execution_root and runtime_ids == questions
        if len(passes) != 236 or len(requests) != 5428:
            raise ValueError("Baseline plan geometry differs")
        for record in passes:
            subject._relative(execution_root, record["run_path"], "Baseline execution run", directory=True)
        return {record["pass_id"]: record for record in passes}, by_pass, requests

    monkeypatch.setattr(subject, "_rows", synthetic_rows)
    monkeypatch.setattr(
        subject,
        "_tree",
        lambda root, label: (
            plan_artifacts,
            frozenset(parent.as_posix() for path in plan_artifacts for parent in Path(path).parents if parent != Path(".")),
        ) if root == plan_root else pytest.fail(f"Unexpected tree root: {root}"),
    )
    monkeypatch.setattr(
        subject,
        "_execution_inventory",
        lambda *_: ({"initialization.json": _hash(initialization.read_bytes())}, frozenset()),
    )
    monkeypatch.setattr(
        subject,
        "_checkpoint_hash",
        lambda run_root, batch_number: (
            _hash(b"mismatch") if state["checkpoint_mismatch"] == (run_root, batch_number)
            else contacts[by_run_batch[(run_root, batch_number)]["ordinal"]]["checkpoint_sha256"]
        ),
    )
    monkeypatch.setattr(
        subject,
        "_run_artifact_hash",
        lambda run_root, batch_number, relative, label: by_run_batch[(run_root, batch_number)][
            "prompt_sha256" if label == "Baseline replay prompt" else "schema_sha256"
        ],
    )
    monkeypatch.setattr(subject, "_receipt_route_hash", lambda *_: route)
    return SimpleNamespace(
        state=state,
        plan=plan,
        contacts=contacts,
        by_pass=by_pass,
        public_inputs=public_inputs,
        plan_root=plan_root,
        execution_root=execution_root,
        runtime_manifest=runtime_manifest,
        initialization=initialization,
        source_pin=source_pin,
        route=route,
        executor=executor,
        settlement=settlement,
    )


def _admit(state):
    return subject.admit_baseline(
        state.public_inputs,
        state.plan_root,
        state.execution_root,
        state.runtime_manifest,
        expected_plan_sha256=subject.PLAN_SHA256,
        expected_final_settlement_sha256=state.settlement,
        expected_execution_source_sha256=state.executor,
        expected_route_sha256=state.route,
        expected_runtime_manifest_sha256=_hash(state.runtime_manifest.read_bytes()),
        expected_admission_sha256=_hash(Path(subject.__file__).read_bytes()),
        expected_reviewer_task="synthetic-review",
        expected_initialization_sha256=_hash(state.initialization.read_bytes()),
    )


def test_complete_synthetic_composition_has_no_native_or_provider_authority(baseline):
    result = _admit(baseline)
    assert result["admitted_passes"] == 236 and result["logical_requests"] == 5428
    assert result["provider_calls"] == 0 and result["execution_authority"] is False
    assert len(result["endpoint_grok_rows"]) == 236
    assert baseline.state == {
        "native_calls": 236,
        "ledger_calls": 2,
        "runtime_verifications": 2,
        "identity_mode": "unique",
        "checkpoint_mismatch": None,
        "mutation": None,
    }


def test_rejects_missing_pass_before_native_replay(baseline):
    missing = baseline.execution_root / baseline.plan["passes"][-1]["run_path"]
    missing.rmdir()
    with pytest.raises(ValueError, match="Path is missing"):
        _admit(baseline)
    assert baseline.state["native_calls"] == 0


def test_rejects_unbound_initialization(baseline):
    initialization = json.loads(baseline.initialization.read_text())
    initialization["plan_files"] = 11093
    baseline.initialization.write_bytes(_json(initialization))
    with pytest.raises(ValueError, match="initialization bindings"):
        _admit(baseline)
    assert baseline.state["native_calls"] == 0


@pytest.mark.parametrize("field", ["unexpected", "execution_authority"])
def test_rejects_unexpected_or_authorizing_initialization_field(baseline, field):
    initialization = json.loads(baseline.initialization.read_text())
    initialization[field] = True
    baseline.initialization.write_bytes(_json(initialization))
    with pytest.raises(ValueError, match="initialization bindings"):
        _admit(baseline)
    assert baseline.state["native_calls"] == 0


@pytest.mark.parametrize("identity_mode", ["duplicate", "trusted"])
def test_rejects_duplicate_or_predecessor_colliding_native_ids(baseline, identity_mode):
    baseline.state["identity_mode"] = identity_mode
    with pytest.raises(ValueError, match="native identity binding or exclusion"):
        _admit(baseline)
    assert baseline.state["native_calls"] == 1


def test_rejects_wrong_logical_artifact_source_binding(baseline, monkeypatch: pytest.MonkeyPatch):
    def wrong_source(record, root):
        result = ORIGINAL_SOURCE(record, root)
        result["opaque_story_id"] = "wrong-logical-id"
        return result

    monkeypatch.setattr(subject, "_source", wrong_source)
    with pytest.raises(ValueError, match="logical/native source identity"):
        _admit(baseline)
    assert baseline.state["native_calls"] == 0


def test_rejects_ledger_native_checkpoint_mismatch(baseline):
    first = baseline.plan["passes"][0]
    run_root = baseline.execution_root / first["run_path"]
    baseline.state["checkpoint_mismatch"] = (run_root, 1)
    with pytest.raises(ValueError, match="checkpoint, prompt, or schema binding"):
        _admit(baseline)
    assert baseline.state["native_calls"] == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [("runtime", "Synthetic runtime changed"), ("source", "source changed during admission"),
     ("input", "Public inputs changed during baseline admission")],
)
def test_rejects_runtime_source_or_input_drift(baseline, mutation, message):
    baseline.state["mutation"] = mutation
    with pytest.raises(ValueError, match=message):
        _admit(baseline)
    assert baseline.state["native_calls"] == 236
