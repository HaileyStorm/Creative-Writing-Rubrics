from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/schema_recovery_execution.py"
RECOVERY_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-grok-recovery-20260907-r3")
ADOPTION = Path(r"C:\Users\Haile\Documents\cwr-wpb-0843-schema-owner-adoption-20260908-r1.json")
PROPOSAL = Path(r"C:\Users\Haile\Documents\cwr-wpb-0843-schema-recovery-proposal-20260907-r1")
BROKER_TEST = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\test_grok_adapter.py")
UNCONTACTED_0847 = {
    "attempt.json": "ffc751cee160cfb75d8392f36950c4ae94b86b91e950d9b467e943ebc0d3dd1e",
    "request.json": "69efa7c8f107142f26eeb1c366bff085a96cf3d62f17cdf5e210308e388a4636",
    "response-schema.json": "3e7ff15aa844dd6f6b3c8c091cae5335eb1b290ca5eeddabb0eab6c29afc6b0e",
    "route.json": "2c332e2b92d5143471493fbcc723662cfa7f5f32c7de00bd93936ec170bc2aeb",
}


def load():
    spec = importlib.util.spec_from_file_location("wpb_schema_recovery_execution_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return digest(raw)


@pytest.fixture()
def case(tmp_path: Path):
    value = load()
    root = tmp_path / "recovery"
    shutil.copytree(RECOVERY_ROOT, root)
    source_attempt = RECOVERY_ROOT / "cells" / "wpb-pair-wpb-en-0847"
    for name, expected_hash in UNCONTACTED_0847.items():
        assert digest((source_attempt / name).read_bytes()) == expected_hash
        (root / "cells" / "wpb-pair-wpb-en-0847" / name).unlink()
    source_cell = RECOVERY_ROOT / "cells" / value.SCHEMA_CELL
    schema = importlib.util.spec_from_file_location("wpb_schema_marker_fixture", value.SCHEMA_PATH)
    assert schema and schema.loader
    helper = importlib.util.module_from_spec(schema)
    schema.loader.exec_module(helper)
    adoption_hash = digest(ADOPTION.read_bytes())
    materialized = helper.materialize_adopted_projection(
        adoption_path=ADOPTION, expected_adoption_sha256=adoption_hash, proposal_root=PROPOSAL,
        source_cell_root=source_cell, expected_payload_sha256=json.loads((root / "recovery-plan.json").read_bytes())["cells"][1]["payload_sha256"],
    )
    marker = root / "cells" / value.SCHEMA_CELL / "schema-recovery-marker.json"
    marker_hash = write_json(marker, materialized["marker"])
    trace = tmp_path / "broker-contacted"
    broker = tmp_path / "broker.py"
    broker.write_text(
        "from pathlib import Path\nfrom uuid import UUID\n"
        "class Broker:\n"
        " def __init__(self, root): self.root = root\n"
        " def run_grok_native_request(self, *args, before_contact, **kwargs):\n"
        "  assert str(UUID(kwargs['session_id'])) == kwargs['session_id']\n"
        "  before_contact()\n"
        f"  Path(r'{trace}').write_text('contacted', encoding='utf-8')\n"
        "  return {'state':'terminal','result':None,'failure':{'code':'synthetic'}}\n"
        " def read_grok_native_envelope(self, descriptor): raise AssertionError('not completed')\n",
        encoding="utf-8",
    )
    runtime, helper_source = tmp_path / "runtime.py", tmp_path / "helper.py"
    runtime.write_text("# synthetic runtime\n", encoding="utf-8")
    helper_source.write_text("# synthetic helper\n", encoding="utf-8")
    route = {"name": "synthetic-grok", "timeout_seconds": 1}
    plan_hash = digest((root / "recovery-plan.json").read_bytes())
    now = datetime.now(UTC)

    def review(*, expires_at: datetime = now + timedelta(minutes=5), reviewed_at: datetime = now - timedelta(minutes=1)) -> tuple[Path, str]:
        record = {
            "format_version": 1, "kind": "wpb0843_schema_recovery_continuation_review",
            "decision": "approved_wpb_remaining_native_dispatch", "recovery_plan_sha256": plan_hash,
            "remaining_cell_ids": [item["cell_id"] for item in json.loads((root / "recovery-plan.json").read_bytes())["cells"][2:]],
            "route_sha256": digest(json.dumps(route, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")),
            "adoption": value._descriptor(ADOPTION, adoption_hash), "marker": value._descriptor(marker, marker_hash),
            "sources": value._sources(broker_path=broker, runtime_source_path=runtime, helper_source_path=helper_source,
                                        expected_schema_helper_sha256=digest(value.SCHEMA_PATH.read_bytes())),
            "reviewer_task": "independent-fixture-review",
            "reviewed_at": reviewed_at.isoformat(), "expires_at": expires_at.isoformat(),
        }
        path = tmp_path / "review.json"
        return path, write_json(path, record)

    return value, root, source_cell, marker, marker_hash, adoption_hash, broker, runtime, helper_source, route, trace, review, now


def arguments(case, review_path: Path, review_hash: str) -> dict[str, object]:
    value, root, source_cell, marker, marker_hash, adoption_hash, broker, runtime, helper_source, route, _trace, _review, _now = case
    return {
        "recovery_root": root, "expected_plan_sha256": digest((root / "recovery-plan.json").read_bytes()), "cell_id": "wpb-pair-wpb-en-0847",
        "route": route, "reviewed_continuation_path": review_path, "expected_review_sha256": review_hash,
        "adoption_path": ADOPTION, "expected_adoption_sha256": adoption_hash, "marker_path": marker, "expected_marker_sha256": marker_hash,
        "proposal_root": PROPOSAL, "source_cell_root": source_cell, "expected_schema_helper_sha256": digest(value.SCHEMA_PATH.read_bytes()),
        "broker_path": broker, "runtime_source_path": runtime, "helper_source_path": helper_source,
        "queue_root": Path(value._load(value.RECOVERY_PATH, value.RECOVERY_SHA256, "fixture recovery").QUEUE_ROOT),
    }


def canonical_output(value, payload: bytes) -> dict[str, object]:
    tools_root = BROKER_TEST.parent.parent
    prior_modules = set(sys.modules)
    sys.path.insert(0, str(tools_root))
    fixture_case = None
    try:
        spec = importlib.util.spec_from_file_location("wpb_schema_execution_canonical_fixture", BROKER_TEST)
        assert spec and spec.loader
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        fixture_case = fixture.GrokAdapterTests("runTest")
        fixture_case.setUp()
        fixture_case.fake.write_text(
            fixture.FAKE.replace('"form": "not_assessable"', '"form": "assessed"'), encoding="utf-8",
        )
        schema = json.loads(fixture.WPB_SCHEMA_PATH.read_bytes())
        outcome = fixture_case.broker._run_grok_exec(
            fixture_case.route("wpb_schema", output_schema=schema), {"prompt": payload.decode("utf-8")},
        )
        assert outcome.state == "completed" and isinstance(outcome.result, dict)
        return dict(outcome.result["output"])
    finally:
        if fixture_case is not None:
            fixture_case.tearDown()
            fixture_case.doCleanups()
        sys.path.remove(str(tools_root))
        for name in set(sys.modules) - prior_modules:
            sys.modules.pop(name, None)


def write_completed_broker(path: Path, artifact_root: Path, output: dict[str, object]) -> None:
    source = f'''import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

ARTIFACT_ROOT = Path(r"{artifact_root}")
OUTPUT = json.loads({json.dumps(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))})

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()

class Broker:
    def __init__(self, root):
        self.root = root

    def run_grok_native_request(self, _name, request, *, output_schema, session_id, before_contact, **_kwargs):
        before_contact()
        request_id = "fixture-" + session_id
        envelope = {{"structuredOutput": OUTPUT, "sessionId": session_id, "requestId": request_id,
                    "stopReason": "end_turn", "num_turns": 1, "text": json.dumps(OUTPUT, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    "modelUsage": {{"grok-4.6-build": {{"costUSD": 0.0}}}}}}
        raw = canonical(envelope)
        digest = sha(raw)
        ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_ROOT / digest).write_bytes(raw)
        result = {{"schema_version": 2, "request_hash": sha({{"prompt": request["prompt"]}}), "output": OUTPUT,
                  "output_hash": sha(OUTPUT), "runtime": {{"adapter_version": 4,
                  "execution_policy": "bounded_nonvisual_deny_wins_attested", "tool_policy_attestation_hash": "e" * 64,
                  "execution_contract": {{"tools": "deny_wins_none_attested", "max_turns": 1, "output_schema_hash": sha(output_schema),
                  "staged_prompt_sha256": sha(request["prompt"].encode("utf-8")), "staged_prompt_byte_length": len(request["prompt"].encode("utf-8"))}},
                  "session_id_hash": sha(session_id.encode("utf-8")), "request_id_hash": sha(request_id.encode("utf-8")),
                  "envelope_hash": digest, "reasoning_attested": False}},
                  "native_envelope_artifact": {{"schema_version": 1, "sha256": digest, "byte_length": len(raw)}}}}
        return {{"state": "completed", "result": result, "failure": None}}

    def read_grok_native_envelope(self, descriptor):
        return (ARTIFACT_ROOT / descriptor["sha256"]).read_bytes()

    def _parse_grok_exec_envelope(self, projection, _route, _request, *, expected_session_id):
        value = json.loads(projection)
        assert value["result"]["runtime"]["session_id_hash"] == sha(expected_session_id.encode("utf-8"))
        return SimpleNamespace(state="completed", result=value["result"])
'''
    path.write_text(source, encoding="utf-8")


def test_provider_free_continuation_gates_and_intervening_drift(case) -> None:
    value, root, source_cell, marker, marker_hash, adoption_hash, broker, _runtime, _helper, _route, trace, review, now = case
    expected = [item["cell_id"] for item in json.loads((root / "recovery-plan.json").read_bytes())["cells"][2:]]
    assert value.remaining_candidates(
        recovery_root=root, expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), adoption_path=ADOPTION,
        expected_adoption_sha256=adoption_hash, marker_path=marker, expected_marker_sha256=marker_hash,
        proposal_root=PROPOSAL, source_cell_root=source_cell, expected_schema_helper_sha256=digest(value.SCHEMA_PATH.read_bytes()),
    ) == expected
    frozen = value._load(value.RECOVERY_PATH, value.RECOVERY_SHA256, "fixture frozen")
    plan = frozen._read_plan(root, digest((root / "recovery-plan.json").read_bytes()))
    frozen._dispatchable(plan, root, expected[0])
    with pytest.raises(ValueError):
        frozen._verify_admission(plan, root, plan["cells"][1])
    marker_raw = marker.read_bytes()
    fresh_review, fresh_hash = review()
    bad_adoption = arguments(case, fresh_review, fresh_hash)
    bad_adoption["expected_adoption_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        value.dispatch_one(**bad_adoption)
    marker.write_bytes(b"{}")
    with pytest.raises(ValueError):
        value.dispatch_one(**arguments(case, fresh_review, fresh_hash))
    marker.write_bytes(marker_raw)
    expired_review, expired_hash = review(expires_at=now - timedelta(seconds=1))
    with pytest.raises(ValueError, match="expired"):
        value.dispatch_one(**arguments(case, expired_review, expired_hash))
    sources = value._sources(broker_path=broker, runtime_source_path=_runtime, helper_source_path=_helper,
                             expected_schema_helper_sha256=digest(value.SCHEMA_PATH.read_bytes()))
    remaining = [dict(item) for item in json.loads((root / "recovery-plan.json").read_bytes())["cells"][2:]]
    future_review, future_hash = review(reviewed_at=now + timedelta(seconds=1))
    with pytest.raises(ValueError, match="not yet active"):
        value._review(review_path=future_review, expected_review_sha256=future_hash,
                      expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), remaining=remaining, route=_route,
                      adoption_path=ADOPTION, expected_adoption_sha256=adoption_hash, marker_path=marker,
                      expected_marker_sha256=marker_hash, sources=sources, now=now)
    short_review, short_hash = review(expires_at=now + timedelta(milliseconds=500))
    with pytest.raises(ValueError, match="does not cover"):
        value._review(review_path=short_review, expected_review_sha256=short_hash,
                      expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), remaining=remaining, route=_route,
                      adoption_path=ADOPTION, expected_adoption_sha256=adoption_hash, marker_path=marker,
                      expected_marker_sha256=marker_hash, sources=sources, now=now)
    assert not trace.exists()

    broker.write_text(
        "from pathlib import Path\nfrom uuid import UUID\n"
        "class Broker:\n"
        " def __init__(self, root): self.root = root\n"
        " def run_grok_native_request(self, *args, before_contact, **kwargs):\n"
        "  assert str(UUID(kwargs['session_id'])) == kwargs['session_id']\n"
        f"  Path(r'{marker}').write_bytes(b'{{}}')\n"
        "  before_contact()\n"
        f"  Path(r'{trace}').write_text('contacted', encoding='utf-8')\n"
        "  return {'state':'terminal','result':None,'failure':{'code':'synthetic'}}\n"
        " def read_grok_native_envelope(self, descriptor): raise AssertionError('not completed')\n",
        encoding="utf-8",
    )
    review_path, review_hash = review()
    with pytest.raises(ValueError, match="marker"):
        value.dispatch_one(**arguments(case, review_path, review_hash))
    assert not trace.exists()



def test_static_preflight_time_cannot_freeze_review_window(case) -> None:
    value, root, _source, marker, marker_hash, adoption_hash, broker, runtime, helper, route, _trace, review, now = case
    review_path, review_hash = review()
    sources = value._sources(broker_path=broker, runtime_source_path=runtime, helper_source_path=helper,
                             expected_schema_helper_sha256=digest(value.SCHEMA_PATH.read_bytes()))
    remaining = [dict(item) for item in json.loads((root / "recovery-plan.json").read_bytes())["cells"][2:]]
    value._review(review_path=review_path, expected_review_sha256=review_hash,
                  expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), remaining=remaining, route=route,
                  adoption_path=ADOPTION, expected_adoption_sha256=adoption_hash, marker_path=marker,
                  expected_marker_sha256=marker_hash, sources=sources, now=now)
    with pytest.raises(ValueError, match="expired"):
        value._review(review_path=review_path, expected_review_sha256=review_hash,
                      expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), remaining=remaining, route=route,
                      adoption_path=ADOPTION, expected_adoption_sha256=adoption_hash, marker_path=marker,
                      expected_marker_sha256=marker_hash, sources=sources, now=now + timedelta(minutes=6))


def test_terminal_attempt_consumes_one_ordinary_cell_and_cannot_resend(case) -> None:
    value, root, _source_cell, _marker, _marker_hash, _adoption_hash, _broker, _runtime, _helper, _route, trace, review, _now = case
    review_path, review_hash = review()
    result = value.dispatch_one(**arguments(case, review_path, review_hash))
    assert result["status"] == "terminal_no_resend" and result["provider_calls_made"] == 1 and trace.read_text(encoding="utf-8") == "contacted"
    compact = uuid.uuid4().hex
    assert str(uuid.UUID(compact)) != compact
    with pytest.raises(ValueError, match="already consumed"):
        value.dispatch_one(**arguments(case, review_path, review_hash))
    assert (root / "cells" / "wpb-pair-wpb-en-0847" / "admission.json").exists() is False
    attempt = json.loads((root / "cells" / "wpb-pair-wpb-en-0847" / "attempt.json").read_bytes())
    assert {name: attempt[name] for name in ("broker_path", "runtime_source_path", "helper_source_path", "queue_root")} == {
        "broker_path": str(_broker.resolve()), "runtime_source_path": str(_runtime.resolve()),
        "helper_source_path": str(_helper.resolve()), "queue_root": str(Path(value._load(value.RECOVERY_PATH, value.RECOVERY_SHA256, "fixture queue").QUEUE_ROOT).resolve()),
    }
    with pytest.raises(ValueError, match="no completed native result"):
        value.admit_native_suffix(
            recovery_root=root, expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), cell_id="wpb-pair-wpb-en-0847",
            adoption_path=ADOPTION, expected_adoption_sha256=_adoption_hash, marker_path=_marker,
            expected_marker_sha256=_marker_hash, proposal_root=PROPOSAL, source_cell_root=_source_cell,
            expected_schema_helper_sha256=digest(value.SCHEMA_PATH.read_bytes()),
        )


def test_completed_canonical_fixture_result_delegates_to_frozen_admission(case, tmp_path: Path) -> None:
    value, root, source_cell, marker, marker_hash, adoption_hash, broker, _runtime, _helper_source, _route, _trace, review, _now = case
    recovery = value._load(value.RECOVERY_PATH, value.RECOVERY_SHA256, "fixture admission recovery")
    plan = recovery._read_plan(root, digest((root / "recovery-plan.json").read_bytes()))
    legacy = recovery._load_legacy()
    resolution, _rows = recovery._rows(legacy, Path(plan["freeze_root"]))
    output = canonical_output(value, resolution["payloads"]["wpb-pair-wpb-en-0847"])
    write_completed_broker(broker, tmp_path / "native-artifacts", output)
    review_path, review_hash = review()
    result = value.dispatch_one(**arguments(case, review_path, review_hash))
    assert result["status"] == "completed_pending_native_admission"
    admitted = value.admit_native_suffix(
        recovery_root=root, expected_plan_sha256=digest((root / "recovery-plan.json").read_bytes()), cell_id="wpb-pair-wpb-en-0847",
        adoption_path=ADOPTION, expected_adoption_sha256=adoption_hash, marker_path=marker,
        expected_marker_sha256=marker_hash, proposal_root=PROPOSAL, source_cell_root=source_cell,
        expected_schema_helper_sha256=digest(value.SCHEMA_PATH.read_bytes()),
    )
    assert admitted["status"] == "admitted" and admitted["provider_calls_made"] == 0
