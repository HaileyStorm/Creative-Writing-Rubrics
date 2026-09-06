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


subject = _module("dryad_campaign_admission", PACKAGE / "campaign_admission.py")
ledger_tree = _module("dryad_campaign_ledger_tree", PACKAGE / "cohort_ledger.py")
math = _module("dryad_campaign_math", PACKAGE / "qualification_math.py")
ORIGINAL_SOURCES = subject._sources


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Synthetic evidence only: no native CLI, broker, or provider is used here."""
    plan_root, execution_root = tmp_path / "plan", tmp_path / "execution"
    plan_root.mkdir()
    execution_root.mkdir()
    public_inputs = tmp_path / "public-inputs.json"
    public_inputs.write_bytes(b"public fixture")
    question_ids = [f"q-{number:03d}" for number in range(178)]
    routes = {_hash(b"route-a"): {"route": "a"}, _hash(b"route-b"): {"route": "b"}}
    route_a, route_b = tuple(routes)
    passes, requests, contacts, by_pass, run_by_id = [], [], {}, {}, {}
    ordinal = 0
    for batch_size in (8, 32):
        for repetition in range(1, 4):
            for story in math.COHORT:
                pass_id = f"size-{batch_size:04d}/repetition-{repetition:02d}/{story}"
                input_path, run_path = f"inputs/{story}.txt", f"runs/{pass_id}"
                source = story.encode("utf-8")
                source_path = plan_root / input_path
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_bytes(source)
                record = {"pass_id": pass_id, "opaque_story_id": story, "batch_size": batch_size, "repetition": repetition,
                          "input_path": input_path, "run_path": run_path, "source_sha256": _hash(source)}
                passes.append(record)
                planned = by_pass[pass_id] = []
                run_root = execution_root / run_path
                run_by_id[pass_id] = run_root
                for batch_number, start in enumerate(range(0, 178, batch_size), start=1):
                    ordinal += 1
                    prompt = f"prompt-{ordinal}".encode("utf-8")
                    prompt_path = f"prompts/request-{ordinal:04d}.txt"
                    path = plan_root / prompt_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(prompt)
                    request = {"ordinal": ordinal, "pass_id": pass_id, "batch_number": batch_number,
                               "question_ids": question_ids[start:start + batch_size], "prompt_path": prompt_path,
                               "prompt_sha256": _hash(prompt), "prompt_bytes": len(prompt),
                               "schema_sha256": _hash(b"schema"), "schema_bytes": 6}
                    requests.append(request)
                    planned.append(request)
                    checkpoint = f"checkpoint-{ordinal}".encode("utf-8")
                    checkpoint_path = run_root / f"responses/batch-{batch_number:04d}.json"
                    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                    checkpoint_path.write_bytes(checkpoint)
                    receipt = run_root / f"responses/grok-broker/batch-{batch_number:04d}-attempt-0001/receipt.json"
                    receipt.parent.mkdir(parents=True, exist_ok=True)
                    receipt.write_bytes(_json({"route_sha256": route_a}))
                    contacts[ordinal] = {"source_sha256": record["source_sha256"], "checkpoint_sha256": _hash(checkpoint),
                                         "execution_source_sha256": _hash(b"reviewed executor"),
                                         "request_id_hash": _hash(f"request-{ordinal}".encode()), "session_id_hash": _hash(f"session-{ordinal}".encode()),
                                         "route_sha256": route_a}
    assert ordinal == 261 and len(passes) == 18
    plan = {"passes": passes, "requests": requests, "runtime": {"question_ids": question_ids}}
    plan_raw = _json(plan)
    plan_sha256 = _hash(plan_raw)
    (plan_root / "plan.json").write_bytes(plan_raw)
    head = _hash(b"settled")
    state = {"calls": 0, "mutator": None, "ledger_calls": 0, "plan": plan, "plan_raw": plan_raw,
             "plan_sha256": plan_sha256, "head": head, "contacts": contacts, "routes": routes,
             "by_pass": by_pass, "run_by_id": run_by_id, "question_ids": question_ids}

    def verify_plan(path: Path, root: Path):
        assert path == public_inputs and root == plan_root
        return {"plan.json": plan_sha256}

    def verify_ledger(root: Path, raw: bytes, expected_plan: str, expected_head: str):
        assert root == execution_root and raw == plan_raw and expected_plan == plan_sha256 and expected_head == head
        state["ledger_calls"] += 1
        return {"routes": routes, "contacts": contacts, "head": {"cohort_number": 27, "settlement_sha256": head}}

    runtime = SimpleNamespace(verify=lambda: None)

    def admit_pass(run_root: Path, *, source: dict, batch_size: int, approved_routes: dict, runtime: object):
        state["calls"] += 1
        pass_id = next(key for key, value in run_by_id.items() if value == run_root)
        planned = by_pass[pass_id]
        assert source["opaque_story_id"] == next(row["opaque_story_id"] for row in plan["passes"] if row["pass_id"] == pass_id)
        result = {"verdicts": [{"question_id": value, "verdict": "YES"} for value in question_ids], "score": state.get("candidate_score", 50) if batch_size == 32 else 50,
                  "coverage": 1, "native_identities": [{"request_id_hash": contacts[item["ordinal"]]["request_id_hash"],
                                                           "session_id_hash": contacts[item["ordinal"]]["session_id_hash"]} for item in planned],
                  "checkpoint_head_sha256": _hash(pass_id.encode())}
        if state["mutator"] is not None:
            state["mutator"](state, pass_id)
        return result

    pins = {}
    for name in ("plan", "ledger", "native", "math", "self"):
        path = tmp_path / f"{name}.py"
        path.write_bytes(name.encode())
        pins[path] = path.read_bytes()
    own_path = Path(subject.__file__).resolve()
    pins[own_path] = own_path.read_bytes()
    monkeypatch.setattr(subject, "_sources", lambda: (pins, (SimpleNamespace(verify=verify_plan),
                                                               SimpleNamespace(verify_ledger=verify_ledger, _regular_tree=ledger_tree._regular_tree),
                                                               SimpleNamespace(load_runtime=lambda: runtime, admit_pass=admit_pass), math)))
    return SimpleNamespace(**state, state=state, plan_root=plan_root, execution_root=execution_root, public_inputs=public_inputs, route_a=route_a, route_b=route_b)


def _admit(state):
    return subject.admit_campaign(state.public_inputs, state.plan_root, state.execution_root,
                                  expected_plan_sha256=state.plan_sha256, expected_final_settlement_sha256=state.head,
                                  expected_admission_sha256=_hash(Path(subject.__file__).read_bytes()), expected_execution_sha256=_hash(b"reviewed executor"))


def test_complete_mocked_composition_has_no_native_or_provider_evidence(campaign):
    result = _admit(campaign)
    assert result["cap"] == 32
    assert result["admitted_passes"] == 18 and result["logical_requests"] == 261
    assert result["provider_calls"] == 0 and result["execution_authority"] is False
    assert result["admission_sha256"] == _hash(Path(subject.__file__).read_bytes())
    assert result["dependency_source_sha256"] == {path.name: value for path, value in subject.SOURCE_PINS.items()}
    assert campaign.state["calls"] == 18 and campaign.state["ledger_calls"] == 2


def test_complete_but_noncomparable_campaign_retains_reference_cap(campaign):
    campaign.state["candidate_score"] = 56
    result = _admit(campaign)
    assert result["cap"] == 8
    assert result["comparability"]["overall_candidate_comparable"] is False


def test_mixed_executor_sources_rejected_before_native_replay(campaign):
    campaign.contacts[261]["execution_source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="execution source"):
        _admit(campaign)
    assert campaign.state["calls"] == 0


def test_rejects_route_swapped_to_another_approved_route(campaign):
    receipt = campaign.run_by_id[campaign.plan["passes"][0]["pass_id"]] / "responses/grok-broker/batch-0001-attempt-0001/receipt.json"
    receipt.write_bytes(_json({"route_sha256": campaign.route_b}))
    with pytest.raises(ValueError, match="route binding"):
        _admit(campaign)


def test_rejects_checkpoint_binding_and_duplicate_native_identity(campaign):
    checkpoint = campaign.run_by_id[campaign.plan["passes"][0]["pass_id"]] / "responses/batch-0001.json"
    checkpoint.write_bytes(b"wrong checkpoint")
    with pytest.raises(ValueError, match="checkpoint binding"):
        _admit(campaign)

    checkpoint.write_bytes(b"checkpoint-1")
    duplicate = campaign.contacts[1]["request_id_hash"]
    campaign.contacts[2]["request_id_hash"] = duplicate
    campaign.contacts[2]["session_id_hash"] = campaign.contacts[1]["session_id_hash"]
    with pytest.raises(ValueError, match="duplicated"):
        _admit(campaign)


@pytest.mark.parametrize("kind", ["missing_pass", "source_change", "later_run_mutation"])
def test_rejects_incomplete_or_mutated_evidence(campaign, kind):
    if kind == "missing_pass":
        run = campaign.run_by_id[campaign.plan["passes"][-1]["pass_id"]]
        for path in sorted(run.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        run.rmdir()
        with pytest.raises(ValueError, match="Expected a directory"):
            _admit(campaign)
        return

    if kind == "source_change":
        target = campaign.plan_root / campaign.plan["passes"][1]["input_path"]
        campaign.state["mutator"] = lambda state, pass_id: target.write_bytes(b"changed") if state["calls"] == 1 else None
        with pytest.raises(ValueError, match="source artifact"):
            _admit(campaign)
        return

    first = campaign.run_by_id[campaign.plan["passes"][0]["pass_id"]] / "responses/batch-0001.json"
    campaign.state["mutator"] = lambda state, pass_id: first.write_bytes(b"later mutation") if state["calls"] == 2 else None
    with pytest.raises(ValueError, match="evidence changed"):
        _admit(campaign)


def test_rejects_missing_anchors_and_source_pin_drift(campaign, monkeypatch):
    with pytest.raises(ValueError, match="anchors"):
        subject.admit_campaign(campaign.public_inputs, campaign.plan_root, campaign.execution_root,
                               expected_plan_sha256="bad", expected_final_settlement_sha256=campaign.head,
                               expected_admission_sha256=_hash(Path(subject.__file__).read_bytes()), expected_execution_sha256=_hash(b"reviewed executor"))
    with pytest.raises(ValueError, match="Reviewed admission source"):
        subject.admit_campaign(campaign.public_inputs, campaign.plan_root, campaign.execution_root,
                               expected_plan_sha256=campaign.plan_sha256, expected_final_settlement_sha256=campaign.head,
                               expected_admission_sha256="0" * 64, expected_execution_sha256=_hash(b"reviewed executor"))
    monkeypatch.setitem(subject.SOURCE_PINS, subject.PLAN_SOURCE, "0" * 64)
    with pytest.raises(ValueError, match="source pin"):
        ORIGINAL_SOURCES()
