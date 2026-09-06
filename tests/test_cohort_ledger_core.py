from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "cohort_ledger_core.py"
BASE_TIME = datetime(2026, 9, 6, tzinfo=timezone.utc)


def load():
    spec = importlib.util.spec_from_file_location("dryad_cohort_ledger_core", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)


def raw(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(value: object) -> str:
    return hashlib.sha256(raw(value) if not isinstance(value, bytes) else value).hexdigest()


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def write(root: Path, relative: str, value: object) -> bytes:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = raw(value)
    path.write_bytes(encoded)
    return encoded


def geometry(core):
    plan_sha256 = "a" * 64
    passes = {"baseline8-v1/train/0001/dryad-000000000000000000000001": {
        "pass_id": "baseline8-v1/train/0001/dryad-000000000000000000000001",
        "logical_sample_id": "baseline8-v1-train-0001-dryad-000000000000000000000001",
        "source_sha256": "b" * 64,
    }}
    requests = {
        ordinal: {"ordinal": ordinal, "pass_id": next(iter(passes)), "prompt_sha256": f"{ordinal:064x}", "schema_sha256": "c" * 64}
        for ordinal in (1, 2)
    }
    return core.LedgerGeometry(plan_sha256, requests, passes, ((1, 2),))


def ledger(root: Path, core, *, duplicate_identity: bool = False, continuation_before_prefix: bool = False):
    value = geometry(core)
    route = {"provider": "synthetic", "route": "baseline"}
    route_sha256 = sha(route)
    execution_sha256 = "d" * 64
    reviewer = "synthetic-reviewer"
    prepared = {"schema_version": 1, "cohort_number": 1, "plan_sha256": value.plan_sha256,
                "previous_settlement_sha256": core.GENESIS_SETTLEMENT_SHA256, "request_ordinals": [1, 2],
                "route_sha256": route_sha256, "execution_source_sha256": execution_sha256}
    prepared_raw = write(root, "cohorts/0001/prepared.json", prepared)
    review = {"schema_version": 1, "reviewer_task": reviewer, "decision": "approved_cohort",
              "prepared_sha256": sha(prepared_raw), "reviewed_at": stamp(BASE_TIME),
              "expires_at": stamp(BASE_TIME + timedelta(minutes=10))}
    review_raw = write(root, "cohorts/0001/review.json", review)
    write(root, "cohorts/0001/route.json", route)
    summaries = []
    for ordinal in (1, 2):
        contact = {"schema_version": 1, "cohort_number": 1, "ordinal": ordinal,
                   "plan_sha256": value.plan_sha256, "prepared_sha256": sha(prepared_raw),
                   "review_sha256": sha(review_raw), "route_sha256": route_sha256,
                   "prompt_sha256": value.requests[ordinal]["prompt_sha256"], "schema_sha256": "c" * 64,
                   "admitted_at": stamp(BASE_TIME + timedelta(minutes=ordinal))}
        contact_raw = write(root, f"contacts/request-{ordinal:04d}.json", contact)
        identity = "e" * 64 if duplicate_identity else f"{ordinal + 14:064x}"
        summaries.append({"ordinal": ordinal, "contact_sha256": sha(contact_raw), "checkpoint_sha256": f"{ordinal + 24:064x}",
                          "request_id_hash": identity, "session_id_hash": f"{(1 if duplicate_identity else ordinal) + 34:064x}"})
    continuation_at = BASE_TIME if continuation_before_prefix else BASE_TIME + timedelta(minutes=2)
    continuation = {"schema_version": 1, "reviewer_task": reviewer, "decision": "approved_continuation",
                    "prepared_sha256": sha(prepared_raw), "route_sha256": route_sha256,
                    "prior_authorization_sha256": sha(review_raw), "previous_execution_source_sha256": execution_sha256,
                    "execution_source_sha256": execution_sha256,
                    "completed_prefix": {"ordinals": [1], "contacts": [summaries[0]], "run_files": {"result.json": "f" * 64},
                                         "run_tree_sha256": sha({"result.json": "f" * 64})},
                    "reviewed_at": stamp(continuation_at), "expires_at": stamp(continuation_at + timedelta(minutes=10))}
    continuation_raw = write(root, "cohorts/0001/review-continuations/0001.json", continuation)
    contacts = [summaries[0], {**summaries[1], "contact_sha256": summaries[1]["contact_sha256"]}]
    second = json.loads((root / "contacts/request-0002.json").read_bytes())
    second["review_sha256"] = sha(continuation_raw)
    second_raw = write(root, "contacts/request-0002.json", second)
    contacts[1]["contact_sha256"] = sha(second_raw)
    settlement = {"schema_version": 2, "cohort_number": 1, "plan_sha256": value.plan_sha256,
                  "prepared_sha256": sha(prepared_raw), "review_sha256": sha(review_raw), "route_sha256": route_sha256,
                  "previous_settlement_sha256": core.GENESIS_SETTLEMENT_SHA256, "settled_at": stamp(BASE_TIME + timedelta(minutes=4)),
                  "contacts": contacts,
                  "authorization_chain": [{"authorization_sha256": sha(review_raw), "execution_source_sha256": execution_sha256, "ordinals": [1]},
                                          {"authorization_sha256": sha(continuation_raw), "execution_source_sha256": execution_sha256, "ordinals": [2]}]}
    settlement_raw = write(root, "cohorts/0001/settlement.json", settlement)
    return value, sha(settlement_raw), route_sha256, execution_sha256, reviewer


def verify(root: Path, core, **kwargs):
    value, head, route, execution, reviewer = ledger(root, core, **kwargs)
    return core.verify_prefix(root, value, head, 1, expected_route_sha256=route,
                              expected_execution_source_sha256=execution, reviewer_task=reviewer)


def renewal_ledger(root: Path, core, *, first_renewal_at: datetime | None = None):
    value = geometry(core)
    route = {"provider": "synthetic", "route": "baseline"}
    route_sha256 = sha(route)
    execution_sha256 = "d" * 64
    reviewer = "synthetic-reviewer"
    prepared = {"schema_version": 1, "cohort_number": 1, "plan_sha256": value.plan_sha256,
                "previous_settlement_sha256": core.GENESIS_SETTLEMENT_SHA256, "request_ordinals": [1, 2],
                "route_sha256": route_sha256, "execution_source_sha256": execution_sha256}
    prepared_raw = write(root, "cohorts/0001/prepared.json", prepared)
    review = {"schema_version": 1, "reviewer_task": reviewer, "decision": "approved_cohort",
              "prepared_sha256": sha(prepared_raw), "reviewed_at": stamp(BASE_TIME),
              "expires_at": stamp(BASE_TIME + timedelta(minutes=10))}
    review_raw = write(root, "cohorts/0001/review.json", review)
    write(root, "cohorts/0001/route.json", route)

    renewal_one = first_renewal_at or BASE_TIME + timedelta(minutes=11)
    renewal_two = renewal_one + timedelta(minutes=11)
    renewal_three = renewal_two + timedelta(minutes=11)
    summaries = []
    for ordinal, authorization, admitted_at in (
        (1, None, renewal_one + timedelta(minutes=1)),
        (2, None, renewal_three + timedelta(minutes=1)),
    ):
        contact = {"schema_version": 1, "cohort_number": 1, "ordinal": ordinal,
                   "plan_sha256": value.plan_sha256, "prepared_sha256": sha(prepared_raw),
                   "review_sha256": authorization, "route_sha256": route_sha256,
                   "prompt_sha256": value.requests[ordinal]["prompt_sha256"], "schema_sha256": "c" * 64,
                   "admitted_at": stamp(admitted_at)}
        summaries.append({"ordinal": ordinal, "contact": contact,
                          "checkpoint_sha256": f"{ordinal + 24:064x}",
                          "request_id_hash": f"{ordinal + 14:064x}",
                          "session_id_hash": f"{ordinal + 34:064x}"})

    def continuation(prior: str, start: datetime, prefix: list[dict[str, object]]) -> tuple[dict[str, object], str]:
        files = {"runs/prefix.json": "f" * 64} if prefix else {}
        value = {"schema_version": 2, "reviewer_task": reviewer, "decision": "approved_continuation",
                 "prepared_sha256": sha(prepared_raw), "route_sha256": route_sha256,
                 "prior_authorization_sha256": prior, "previous_execution_source_sha256": execution_sha256,
                 "execution_source_sha256": execution_sha256,
                 "completed_prefix": {"ordinals": [item["ordinal"] for item in prefix],
                                      "contacts": prefix, "run_files": files,
                                      "run_tree_sha256": sha(files)},
                 "reviewed_at": stamp(start), "expires_at": stamp(start + timedelta(minutes=10))}
        encoded = raw(value)
        return value, sha(encoded)

    first, first_sha = continuation(sha(review_raw), renewal_one, [])
    summaries[0]["contact"]["review_sha256"] = first_sha
    write(root, "cohorts/0001/review-continuations/0001.json", first)
    first_contact_raw = write(root, "contacts/request-0001.json", summaries[0]["contact"])
    summary_one = {
        "ordinal": 1,
        "contact_sha256": sha(first_contact_raw),
        "checkpoint_sha256": summaries[0]["checkpoint_sha256"],
        "request_id_hash": summaries[0]["request_id_hash"],
        "session_id_hash": summaries[0]["session_id_hash"],
    }
    second, second_sha = continuation(first_sha, renewal_two, [summary_one])
    third, third_sha = continuation(second_sha, renewal_three, [summary_one])
    summaries[1]["contact"]["review_sha256"] = third_sha
    for number, candidate in ((2, second), (3, third)):
        write(root, f"cohorts/0001/review-continuations/{number:04d}.json", candidate)
    second_contact_raw = write(root, "contacts/request-0002.json", summaries[1]["contact"])
    contacts = [summary_one, {
        "ordinal": 2,
        "contact_sha256": sha(second_contact_raw),
        "checkpoint_sha256": summaries[1]["checkpoint_sha256"],
        "request_id_hash": summaries[1]["request_id_hash"],
        "session_id_hash": summaries[1]["session_id_hash"],
    }]
    settlement = {"schema_version": 3, "cohort_number": 1, "plan_sha256": value.plan_sha256,
                  "prepared_sha256": sha(prepared_raw), "review_sha256": sha(review_raw), "route_sha256": route_sha256,
                  "previous_settlement_sha256": core.GENESIS_SETTLEMENT_SHA256,
                  "settled_at": stamp(renewal_three + timedelta(minutes=2)), "contacts": contacts,
                  "authorization_chain": [
                      {"authorization_sha256": sha(review_raw), "execution_source_sha256": execution_sha256, "ordinals": []},
                      {"authorization_sha256": first_sha, "execution_source_sha256": execution_sha256, "ordinals": [1]},
                      {"authorization_sha256": second_sha, "execution_source_sha256": execution_sha256, "ordinals": []},
                      {"authorization_sha256": third_sha, "execution_source_sha256": execution_sha256, "ordinals": [2]},
                  ]}
    settlement_raw = write(root, "cohorts/0001/settlement.json", settlement)
    return value, sha(settlement_raw), route_sha256, execution_sha256, reviewer


def test_core_binds_append_only_hash_chain_route_and_logical_identity(tmp_path: Path) -> None:
    core = load()
    verified = verify(tmp_path, core)
    assert verified["head"]["cohort_number"] == 1
    assert len(verified["head"]["settlement_sha256"]) == 64
    assert verified["evidence_class"] == "provider_free_baseline_ledger_consistency"
    assert verified["native_admission"] is False and verified["execution_authority"] is False
    assert verified["contacts"][1]["logical_sample_id"] == "baseline8-v1-train-0001-dryad-000000000000000000000001"
    assert verified["contacts"][2]["route_sha256"] in verified["routes"]


def test_core_returns_distinct_initial_and_continuation_authorizations(tmp_path: Path) -> None:
    core = load()
    verified = verify(tmp_path, core)
    initial = verified["contacts"][1]["authorization_sha256"]
    continuation = verified["contacts"][2]["authorization_sha256"]
    assert initial != continuation
    assert verified["authorizations"][initial] == {
        "execution_source_sha256": "d" * 64,
        "reviewed_at": "2026-09-06T00:00:00+00:00",
        "expires_at": "2026-09-06T00:10:00+00:00",
        "cohort_number": 1,
    }
    assert verified["authorizations"][continuation] == {
        "execution_source_sha256": "d" * 64,
        "reviewed_at": "2026-09-06T00:02:00+00:00",
        "expires_at": "2026-09-06T00:12:00+00:00",
        "cohort_number": 1,
    }
    settlement = json.loads((tmp_path / "cohorts/0001/settlement.json").read_bytes())
    assert [item["authorization_sha256"] for item in settlement["authorization_chain"]] == [initial, continuation]
    assert [verified["contacts"][ordinal]["authorization_sha256"] for ordinal in (1, 2)] == [initial, continuation]


def test_core_rejects_continuation_before_completed_contact_and_duplicate_native_identity(tmp_path: Path) -> None:
    core = load()
    with pytest.raises(ValueError, match="Continuation review precedes completed prefix"):
        verify(tmp_path / "early", core, continuation_before_prefix=True)
    with pytest.raises(ValueError, match="Native identity is duplicated"):
        verify(tmp_path / "duplicate", core, duplicate_identity=True)


def test_core_rejects_drift_and_terminal_like_extra_inventory(tmp_path: Path) -> None:
    core = load()
    verified = verify(tmp_path / "drift", core)
    drift = tmp_path / "drift" / "contacts/request-0001.json"
    drift.write_bytes(b"{}")
    with pytest.raises(ValueError):
        core.verify_prefix(tmp_path / "drift", geometry(core), verified["head"]["settlement_sha256"], 1,
                           expected_route_sha256=verified["contacts"][1]["route_sha256"], expected_execution_source_sha256="d" * 64,
                           reviewer_task="synthetic-reviewer")
    extra = tmp_path / "extra"
    verified = verify(extra, core)
    write(extra, "contacts/terminal-sidecar.json", {"synthetic": "not admitted"})
    with pytest.raises(ValueError, match="inventory"):
        core.verify_prefix(extra, geometry(core), verified["head"]["settlement_sha256"], 1,
                           expected_route_sha256=verified["contacts"][1]["route_sha256"], expected_execution_source_sha256="d" * 64,
                           reviewer_task="synthetic-reviewer")


def test_core_pending_paths_remain_unadmitted(tmp_path: Path) -> None:
    core = load()
    (tmp_path / "cohorts").mkdir(); (tmp_path / "contacts").mkdir()
    write(tmp_path, "contacts/request-0001.json", {"synthetic": "pending"})
    value = geometry(core)
    with pytest.raises(ValueError, match="inventory"):
        core.verify_prefix(tmp_path, value, core.GENESIS_SETTLEMENT_SHA256, 0, expected_route_sha256="1" * 64,
                           expected_execution_source_sha256="2" * 64, reviewer_task="synthetic-reviewer")
    verified = core.verify_prefix(tmp_path, value, core.GENESIS_SETTLEMENT_SHA256, 0, expected_route_sha256="1" * 64,
                                  expected_execution_source_sha256="2" * 64, reviewer_task="synthetic-reviewer",
                                  allowed_pending_paths=frozenset({"contacts/request-0001.json"}))
    assert verified["contacts"] == {}


def test_core_schema3_retains_unused_approval_history_across_renewals(tmp_path: Path) -> None:
    core = load()
    value, head, route, execution, reviewer = renewal_ledger(tmp_path, core)
    verified = core.verify_prefix(tmp_path, value, head, 1, expected_route_sha256=route,
                                  expected_execution_source_sha256=execution, reviewer_task=reviewer)
    settlement = json.loads((tmp_path / "cohorts/0001/settlement.json").read_bytes())
    assert settlement["schema_version"] == 3
    assert [entry["ordinals"] for entry in settlement["authorization_chain"]] == [[], [1], [], [2]]
    assert [verified["contacts"][ordinal]["authorization_sha256"] for ordinal in (1, 2)] == [
        settlement["authorization_chain"][1]["authorization_sha256"],
        settlement["authorization_chain"][3]["authorization_sha256"],
    ]


def test_core_schema3_rejects_premature_or_erased_unused_authorization_history(tmp_path: Path) -> None:
    core = load()
    value, head, route, execution, reviewer = renewal_ledger(
        tmp_path / "premature", core, first_renewal_at=BASE_TIME + timedelta(minutes=5),
    )
    with pytest.raises(ValueError, match="Unused authorization renewal"):
        core.verify_prefix(tmp_path / "premature", value, head, 1, expected_route_sha256=route,
                           expected_execution_source_sha256=execution, reviewer_task=reviewer)

    value, head, route, execution, reviewer = renewal_ledger(tmp_path / "forged", core)
    settlement_path = tmp_path / "forged" / "cohorts/0001/settlement.json"
    settlement = json.loads(settlement_path.read_bytes())
    settlement["authorization_chain"][0]["ordinals"] = [1]
    settlement_path.write_bytes(raw(settlement))
    with pytest.raises(ValueError, match="Settlement authorization"):
        core.verify_prefix(tmp_path / "forged", value, sha(settlement_path.read_bytes()), 1,
                           expected_route_sha256=route, expected_execution_source_sha256=execution,
                           reviewer_task=reviewer)

    value, head, route, execution, reviewer = renewal_ledger(tmp_path / "erased", core)
    settlement_path = tmp_path / "erased" / "cohorts/0001/settlement.json"
    settlement = json.loads(settlement_path.read_bytes())
    settlement["authorization_chain"].pop(2)
    settlement_path.write_bytes(raw(settlement))
    with pytest.raises(ValueError, match="Settlement authorization"):
        core.verify_prefix(tmp_path / "erased", value, sha(settlement_path.read_bytes()), 1,
                           expected_route_sha256=route, expected_execution_source_sha256=execution,
                           reviewer_task=reviewer)
