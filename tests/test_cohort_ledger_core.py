from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "cohort_ledger_core.py"
BASE_TIME = datetime(2026, 9, 6, tzinfo=timezone.utc)


def load(source: Path = SOURCE):
    spec = importlib.util.spec_from_file_location("dryad_cohort_ledger_core", source)
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
        "run_path": "runs/synthetic.json",
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
    write(tmp_path, "initialization.json", {"route_sha256": "1" * 64, "execution_source_sha256": "2" * 64})
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


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(("git", "-C", str(repo), *arguments), check=True, capture_output=True, text=True).stdout.strip()


def operational_core(tmp_path: Path):
    temporary = tempfile.TemporaryDirectory(prefix="cohort-ledger-")
    repo = Path(temporary.name)
    package = repo / PACKAGE.relative_to(PACKAGE.parents[1])
    package.mkdir(parents=True)
    relative_files = (
        "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/cohort_ledger_core.py",
        "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_ledger.py",
        "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_admission.py",
        "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_execution.py",
    )
    source_root = SOURCE.parents[2]
    for relative in relative_files:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / relative).read_bytes())
    git(repo, "init")
    git(repo, "config", "user.email", "synthetic@example.invalid")
    git(repo, "config", "user.name", "Synthetic Ledger Test")
    git(repo, "add", "-f", ".")
    git(repo, "commit", "-m", "operational epoch zero")
    revisions = [git(repo, "rev-parse", "HEAD")]
    execution = repo / relative_files[-1]
    for epoch in ("one", "two"):
        execution.write_bytes(execution.read_bytes() + f"\n# synthetic operational epoch {epoch}\n".encode())
        git(repo, "add", relative_files[-1])
        git(repo, "commit", "-m", f"operational epoch {epoch}")
        revisions.append(git(repo, "rev-parse", "HEAD"))
    core = load(repo / relative_files[0])
    core.HISTORICAL_OPERATIONAL_REVISION = revisions[0]
    core._synthetic_source_directory = temporary

    def manifest(revision: str) -> dict[str, object]:
        return {"revision": revision, "files": {
            relative: hashlib.sha256(
                subprocess.run(("git", "-C", str(repo), "show", f"{revision}:{relative}"), check=True,
                               capture_output=True).stdout
            ).hexdigest()
            for relative in relative_files
        }}

    return core, revisions, manifest


def renewal_route(receipt: str, evidence: str, at: datetime) -> dict[str, object]:
    return {
        "provider": "synthetic",
        "route": "baseline",
        "subscription_receipt_hash": receipt,
        "cost_evidence": {
            "allowance_state": "available",
            "checked_at": stamp(at),
            "evidence_hash": evidence,
            "expires_at": stamp(at + timedelta(hours=1)),
            "kind": "subscription_included",
            "version": 1,
        },
    }


def write_closed_cohort(root: Path, core, *, cohort: int, ordinal: int, route: dict[str, object], source: str,
                        previous_settlement: str, reviewer: str, reviewed_at: datetime,
                        renewal_sha256: str | None = None) -> str:
    prepared = {
        "schema_version": 2 if renewal_sha256 else 1,
        "cohort_number": cohort,
        "plan_sha256": "a" * 64,
        "previous_settlement_sha256": previous_settlement,
        "request_ordinals": [ordinal],
        "route_sha256": sha(route),
        "execution_source_sha256": source,
    }
    if renewal_sha256:
        prepared["operational_renewal_sha256"] = renewal_sha256
    prepared_raw = write(root, f"cohorts/{cohort:04d}/prepared.json", prepared)
    review = {"schema_version": 1, "reviewer_task": reviewer, "decision": "approved_cohort",
              "prepared_sha256": sha(prepared_raw), "reviewed_at": stamp(reviewed_at),
              "expires_at": stamp(reviewed_at + timedelta(minutes=10))}
    review_raw = write(root, f"cohorts/{cohort:04d}/review.json", review)
    write(root, f"cohorts/{cohort:04d}/route.json", route)
    contact = {"schema_version": 1, "cohort_number": cohort, "ordinal": ordinal, "plan_sha256": "a" * 64,
               "prepared_sha256": sha(prepared_raw), "review_sha256": sha(review_raw), "route_sha256": sha(route),
               "prompt_sha256": f"{ordinal:064x}", "schema_sha256": "c" * 64,
               "admitted_at": stamp(reviewed_at + timedelta(minutes=1))}
    contact_raw = write(root, f"contacts/request-{ordinal:04d}.json", contact)
    settlement = {
        "schema_version": 1, "cohort_number": cohort, "plan_sha256": "a" * 64,
        "prepared_sha256": sha(prepared_raw), "review_sha256": sha(review_raw), "route_sha256": sha(route),
        "previous_settlement_sha256": previous_settlement, "settled_at": stamp(reviewed_at + timedelta(minutes=2)),
        "contacts": [{"ordinal": ordinal, "contact_sha256": sha(contact_raw), "checkpoint_sha256": f"{ordinal + 20:064x}",
                      "request_id_hash": f"{ordinal + 30:064x}", "session_id_hash": f"{ordinal + 40:064x}"}],
    }
    return sha(write(root, f"cohorts/{cohort:04d}/settlement.json", settlement))


def write_operational_renewal(root: Path, *, cohort: int, initialization_sha256: str, previous: str,
                              settlement: str, old_route: dict[str, object], new_route: dict[str, object],
                              old_manifest: dict[str, object], new_manifest: dict[str, object],
                              remaining: list[int], aggregate: bytes, reviewed_at: datetime) -> str:
    initialization_raw = (root / "initialization.json").read_bytes()
    value = {
        "schema_version": 1,
        "evidence_class": "independently_reviewed_operational_renewal",
        "reviewer_task": "synthetic-operational-reviewer",
        "decision": "approved_operational_renewal",
        "original_initialization_sha256": initialization_sha256,
        "previous_renewal_sha256": previous,
        "settled_cohort_number": cohort,
        "settled_head_settlement_sha256": settlement,
        "preserved_prefix": {
            "immutable_files": {"initialization.json": sha(initialization_raw)},
            "derived_aggregate_prefixes": {
                "runner-normalized-verdicts.jsonl": {
                    "derivation": "runner_normalized_verdicts_v1",
                    "sha256": sha(aggregate),
                    "bytes": len(aggregate),
                    "verdict_count": aggregate.count(b"\n"),
                },
            },
        },
        "next_cohort_number": cohort + 1,
        "remaining_ordinals": remaining,
        "old_route": old_route,
        "old_route_sha256": sha(old_route),
        "new_route": new_route,
        "new_route_sha256": sha(new_route),
        "old_receipt_sha256": old_route["subscription_receipt_hash"],
        "new_receipt_sha256": new_route["subscription_receipt_hash"],
        "old_operational_source_manifest": old_manifest,
        "new_operational_source_manifest": new_manifest,
        "reviewed_at": stamp(reviewed_at),
    }
    return sha(write(root, f"cohorts/{cohort:04d}/operational-renewals/0001.json", value))


def operational_renewal_ledger(tmp_path: Path):
    core, revisions, manifest = operational_core(tmp_path)
    root = tmp_path / "ledger"
    reviewer = "synthetic-reviewer"
    routes = [
        renewal_route("1" * 64, "2" * 64, BASE_TIME),
        renewal_route("3" * 64, "4" * 64, BASE_TIME + timedelta(minutes=3)),
        renewal_route("5" * 64, "6" * 64, BASE_TIME + timedelta(minutes=7)),
    ]
    manifests = [manifest(revision) for revision in revisions]
    sources = [item["files"][core._OPERATIONAL_FILES[-1]] for item in manifests]
    initialization_raw = write(root, "initialization.json", {
        "route_sha256": sha(routes[0]), "execution_source_sha256": sources[0],
    })
    aggregate = b'{"ordinal":1}\n'
    (root / "runner-normalized-verdicts.jsonl").write_bytes(aggregate)
    geometry = core.LedgerGeometry("a" * 64, {
        ordinal: {"ordinal": ordinal, "pass_id": "pass-1", "prompt_sha256": f"{ordinal:064x}", "schema_sha256": "c" * 64}
        for ordinal in (1, 2, 3)
    }, {"pass-1": {"pass_id": "pass-1", "logical_sample_id": "sample-1", "source_sha256": "b" * 64,
                       "run_path": "runs/synthetic.json"}}, ((1,), (2,), (3,)))
    first = write_closed_cohort(root, core, cohort=1, ordinal=1, route=routes[0], source=sources[0],
                                previous_settlement=core.GENESIS_SETTLEMENT_SHA256, reviewer=reviewer, reviewed_at=BASE_TIME)
    first_renewal = write_operational_renewal(root, cohort=1, initialization_sha256=sha(initialization_raw),
                                              previous=core.GENESIS_RENEWAL_SHA256, settlement=first,
                                              old_route=routes[0], new_route=routes[1], old_manifest=manifests[0],
                                              new_manifest=manifests[1], remaining=[2, 3], aggregate=aggregate,
                                              reviewed_at=BASE_TIME + timedelta(minutes=3))
    aggregate += b'{"ordinal":2}\n'
    (root / "runner-normalized-verdicts.jsonl").write_bytes(aggregate)
    second = write_closed_cohort(root, core, cohort=2, ordinal=2, route=routes[1], source=sources[1],
                                 previous_settlement=first, reviewer=reviewer,
                                 reviewed_at=BASE_TIME + timedelta(minutes=4), renewal_sha256=first_renewal)
    second_renewal = write_operational_renewal(root, cohort=2, initialization_sha256=sha(initialization_raw),
                                               previous=first_renewal, settlement=second, old_route=routes[1],
                                               new_route=routes[2], old_manifest=manifests[1], new_manifest=manifests[2],
                                               remaining=[3], aggregate=aggregate, reviewed_at=BASE_TIME + timedelta(minutes=7))
    aggregate += b'{"ordinal":3}\n'
    (root / "runner-normalized-verdicts.jsonl").write_bytes(aggregate)
    head = write_closed_cohort(root, core, cohort=3, ordinal=3, route=routes[2], source=sources[2],
                               previous_settlement=second, reviewer=reviewer,
                               reviewed_at=BASE_TIME + timedelta(minutes=8), renewal_sha256=second_renewal)
    return {"core": core, "root": root, "geometry": geometry, "head": head, "routes": routes, "sources": sources,
            "reviewer": reviewer, "renewals": (first_renewal, second_renewal), "aggregate": aggregate}


def verify_operational_ledger(fixture: dict[str, object]):
    return fixture["core"].verify_prefix(
        fixture["root"], fixture["geometry"], fixture["head"], 3,
        expected_route_sha256=sha(fixture["routes"][0]), expected_execution_source_sha256=fixture["sources"][0],
        reviewer_task=fixture["reviewer"],
    )


def test_core_reads_two_operational_renewal_epochs_with_exact_boundary_bindings(tmp_path: Path) -> None:
    fixture = operational_renewal_ledger(tmp_path)
    verified = verify_operational_ledger(fixture)
    assert [item["sha256"] for item in verified["renewals"]] == list(fixture["renewals"])
    assert [item["value"]["remaining_ordinals"] for item in verified["renewals"]] == [[2, 3], [3]]
    assert verified["epochs"] == {
        1: {"route_sha256": sha(fixture["routes"][0]), "execution_source_sha256": fixture["sources"][0], "operational_renewal_sha256": None},
        2: {"route_sha256": sha(fixture["routes"][1]), "execution_source_sha256": fixture["sources"][1], "operational_renewal_sha256": fixture["renewals"][0]},
        3: {"route_sha256": sha(fixture["routes"][2]), "execution_source_sha256": fixture["sources"][2], "operational_renewal_sha256": fixture["renewals"][1]},
    }
    prepared = [json.loads((fixture["root"] / f"cohorts/{number:04d}/prepared.json").read_bytes()) for number in (1, 2, 3)]
    assert [item["schema_version"] for item in prepared] == [1, 2, 2]
    assert [prepared[index]["operational_renewal_sha256"] for index in (1, 2)] == list(fixture["renewals"])


@pytest.mark.parametrize(("expected_route", "expected_source"), (("0" * 64, None), (None, "0" * 64)))
def test_core_rejects_stale_external_initialization_anchors(tmp_path: Path, expected_route: str | None, expected_source: str | None) -> None:
    fixture = operational_renewal_ledger(tmp_path)
    with pytest.raises(ValueError, match="Initialization epoch|Operational renewal initialization differs"):
        fixture["core"].verify_prefix(
            fixture["root"], fixture["geometry"], fixture["head"], 3,
            expected_route_sha256=expected_route or sha(fixture["routes"][0]),
            expected_execution_source_sha256=expected_source or fixture["sources"][0], reviewer_task=fixture["reviewer"],
        )


def test_core_rejects_operational_route_source_settlement_suffix_and_inventory_drift(tmp_path: Path) -> None:
    fixture = operational_renewal_ledger(tmp_path / "route")
    renewal_path = fixture["root"] / "cohorts/0001/operational-renewals/0001.json"
    renewal = json.loads(renewal_path.read_bytes())
    renewal["new_route"]["provider"] = "forged"
    renewal["new_route_sha256"] = sha(renewal["new_route"])
    write(fixture["root"], "cohorts/0001/operational-renewals/0001.json", renewal)
    with pytest.raises(ValueError, match="Renewal route contract"):
        verify_operational_ledger(fixture)

    fixture = operational_renewal_ledger(tmp_path / "source")
    renewal_path = fixture["root"] / "cohorts/0001/operational-renewals/0001.json"
    renewal = json.loads(renewal_path.read_bytes())
    renewal["old_operational_source_manifest"]["files"][fixture["core"]._OPERATIONAL_FILES[0]] = "0" * 64
    write(fixture["root"], "cohorts/0001/operational-renewals/0001.json", renewal)
    with pytest.raises(ValueError, match="source manifest Git evidence"):
        verify_operational_ledger(fixture)

    fixture = operational_renewal_ledger(tmp_path / "boundary")
    renewal_path = fixture["root"] / "cohorts/0002/operational-renewals/0001.json"
    renewal = json.loads(renewal_path.read_bytes())
    renewal["settled_head_settlement_sha256"] = "0" * 64
    renewal["remaining_ordinals"] = [2, 3]
    write(fixture["root"], "cohorts/0002/operational-renewals/0001.json", renewal)
    with pytest.raises(ValueError, match="Operational renewal binding"):
        verify_operational_ledger(fixture)

    fixture = operational_renewal_ledger(tmp_path / "inventory")
    write(fixture["root"], "cohorts/0001/operational-renewals/0002.json", {"unexpected": True})
    with pytest.raises(ValueError, match="Ledger inventory"):
        verify_operational_ledger(fixture)


def test_core_preserves_renewal_prefixes_while_derived_aggregate_grows(tmp_path: Path) -> None:
    fixture = operational_renewal_ledger(tmp_path)
    assert verify_operational_ledger(fixture)["head"]["settlement_sha256"] == fixture["head"]
    aggregate_path = fixture["root"] / "runner-normalized-verdicts.jsonl"
    aggregate = aggregate_path.read_bytes()
    aggregate_path.write_bytes(b"X" + aggregate[1:])
    with pytest.raises(ValueError, match="aggregate prefix"):
        verify_operational_ledger(fixture)


def test_core_rejects_a_renewal_after_the_final_cohort(tmp_path: Path) -> None:
    fixture = operational_renewal_ledger(tmp_path)
    preceding = json.loads((fixture["root"] / "cohorts/0002/operational-renewals/0001.json").read_bytes())
    write_operational_renewal(
        fixture["root"], cohort=3, initialization_sha256=sha((fixture["root"] / "initialization.json").read_bytes()),
        previous=fixture["renewals"][1], settlement=fixture["head"], old_route=fixture["routes"][2],
        new_route=renewal_route("7" * 64, "8" * 64, BASE_TIME + timedelta(minutes=11)),
        old_manifest=preceding["new_operational_source_manifest"], new_manifest=preceding["new_operational_source_manifest"],
        remaining=[], aggregate=fixture["aggregate"], reviewed_at=BASE_TIME + timedelta(minutes=11),
    )
    with pytest.raises(ValueError, match="Operational renewal.*(?:final|suffix|binding)"):
        verify_operational_ledger(fixture)


def test_precontact_recovery_moves_only_an_empty_cohort_to_the_current_source(tmp_path: Path) -> None:
    core, revisions, manifest = operational_core(tmp_path)
    root, reviewer = tmp_path / "precontact", "synthetic-reviewer"
    routes = [renewal_route("1" * 64, "2" * 64, BASE_TIME), renewal_route("3" * 64, "4" * 64, BASE_TIME + timedelta(minutes=3))]
    manifests = [manifest(revision) for revision in revisions]
    sources = [item["files"][core._OPERATIONAL_FILES[-1]] for item in manifests]
    initialization = write(root, "initialization.json", {"route_sha256": sha(routes[0]), "execution_source_sha256": sources[0]})
    aggregate = b'{"ordinal":1}\n'
    (root / "runner-normalized-verdicts.jsonl").write_bytes(aggregate)
    (root / "runs/sample").mkdir(parents=True)
    (root / "runs/sample/verdicts.jsonl").write_bytes(aggregate)
    geometry = core.LedgerGeometry("a" * 64, {ordinal: {"ordinal": ordinal, "pass_id": "pass-1", "prompt_sha256": f"{ordinal:064x}", "schema_sha256": "c" * 64} for ordinal in (1, 2, 3, 4)}, {"pass-1": {"pass_id": "pass-1", "logical_sample_id": "sample-1", "source_sha256": "b" * 64}}, ((1,), (2, 3), (4,)))
    first = write_closed_cohort(root, core, cohort=1, ordinal=1, route=routes[0], source=sources[0], previous_settlement=core.GENESIS_SETTLEMENT_SHA256, reviewer=reviewer, reviewed_at=BASE_TIME)
    renewal = write_operational_renewal(root, cohort=1, initialization_sha256=sha(initialization), previous=core.GENESIS_RENEWAL_SHA256, settlement=first, old_route=routes[0], new_route=routes[1], old_manifest=manifests[0], new_manifest=manifests[1], remaining=[2, 3, 4], aggregate=aggregate, reviewed_at=BASE_TIME + timedelta(minutes=3))
    prepared = {"schema_version": 2, "cohort_number": 2, "plan_sha256": "a" * 64, "previous_settlement_sha256": first, "request_ordinals": [2, 3], "route_sha256": sha(routes[1]), "execution_source_sha256": sources[1], "operational_renewal_sha256": renewal}
    prepared_raw = write(root, "cohorts/0002/prepared.json", prepared)
    original_review = {"schema_version": 1, "reviewer_task": reviewer, "decision": "approved_cohort", "prepared_sha256": sha(prepared_raw), "reviewed_at": stamp(BASE_TIME + timedelta(minutes=4)).replace("Z", "+00:00"), "expires_at": stamp(BASE_TIME + timedelta(minutes=14)).replace("Z", "+00:00")}
    original_raw = write(root, "cohorts/0002/review.json", original_review)
    write(root, "cohorts/0002/route.json", routes[1])
    candidate = core.precontact_recovery_candidate(root, cohort_number=2, ordinals=(2,), initialization_sha256=sha(initialization), previous_settlement_sha256=first, operational_renewal={"sha256": renewal, "new_source": manifests[1]}, prepared_sha256=sha(prepared_raw), review_sha256=sha(original_raw), route_sha256=sha(routes[1]), reviewer_task=reviewer, old_source_sha256=sources[1], new_source_manifest=core.current_operational_source_manifest())
    recovery_at = BASE_TIME + timedelta(minutes=15)
    recovery = {**candidate, "reviewed_at": stamp(recovery_at), "expires_at": stamp(recovery_at + timedelta(minutes=10))}
    recovery_raw = write(root, "cohorts/0002/review-continuations/0001.json", recovery)
    pending = frozenset({"cohorts/0002/prepared.json", "cohorts/0002/review.json", "cohorts/0002/route.json", "cohorts/0002/review-continuations/0001.json"})
    prior = core.verify_prefix(root, geometry, first, 1, expected_route_sha256=sha(routes[0]), expected_execution_source_sha256=sources[0], reviewer_task=reviewer, allowed_pending_paths=pending)
    assert prior["precontact_recovery"]["sha256"] == sha(recovery_raw)
    contact = {"schema_version": 1, "cohort_number": 2, "ordinal": 2, "plan_sha256": "a" * 64, "prepared_sha256": sha(prepared_raw), "review_sha256": sha(recovery_raw), "route_sha256": sha(routes[1]), "prompt_sha256": f"{2:064x}", "schema_sha256": "c" * 64, "admitted_at": stamp(recovery_at + timedelta(minutes=1))}
    contact_raw = write(root, "contacts/request-0002.json", contact)
    summary = {"ordinal": 2, "contact_sha256": sha(contact_raw), "checkpoint_sha256": f"{22:064x}", "request_id_hash": f"{32:064x}", "session_id_hash": f"{42:064x}"}
    continuation = {"schema_version": 2, "reviewer_task": reviewer, "decision": "approved_continuation", "prepared_sha256": sha(prepared_raw), "route_sha256": sha(routes[1]), "prior_authorization_sha256": sha(recovery_raw), "previous_execution_source_sha256": sources[2], "execution_source_sha256": sources[2], "completed_prefix": {"ordinals": [2], "contacts": [summary], "run_files": core._run_files(root), "run_tree_sha256": sha(core.canonical(core._run_files(root)))}, "reviewed_at": stamp(recovery_at + timedelta(minutes=11)), "expires_at": stamp(recovery_at + timedelta(minutes=21))}
    continuation_raw = write(root, "cohorts/0002/review-continuations/0002.json", continuation)
    contact3 = {**contact, "ordinal": 3, "review_sha256": sha(continuation_raw), "prompt_sha256": f"{3:064x}", "admitted_at": stamp(recovery_at + timedelta(minutes=12))}
    contact3_raw = write(root, "contacts/request-0003.json", contact3)
    summary3 = {"ordinal": 3, "contact_sha256": sha(contact3_raw), "checkpoint_sha256": f"{23:064x}", "request_id_hash": f"{33:064x}", "session_id_hash": f"{43:064x}"}
    settlement = {"schema_version": 3, "cohort_number": 2, "plan_sha256": "a" * 64, "prepared_sha256": sha(prepared_raw), "review_sha256": sha(original_raw), "route_sha256": sha(routes[1]), "previous_settlement_sha256": first, "settled_at": stamp(recovery_at + timedelta(minutes=13)), "contacts": [summary, summary3], "authorization_chain": [{"authorization_sha256": sha(original_raw), "execution_source_sha256": sources[1], "ordinals": []}, {"authorization_sha256": sha(recovery_raw), "execution_source_sha256": sources[2], "ordinals": [2]}, {"authorization_sha256": sha(continuation_raw), "execution_source_sha256": sources[2], "ordinals": [3]}]}
    second = sha(write(root, "cohorts/0002/settlement.json", settlement))
    routes.append(renewal_route("5" * 64, "6" * 64, recovery_at + timedelta(minutes=14)))
    renewal2 = write_operational_renewal(root, cohort=2, initialization_sha256=sha(initialization), previous=renewal, settlement=second, old_route=routes[1], new_route=routes[2], old_manifest=manifests[2], new_manifest=manifests[2], remaining=[4], aggregate=aggregate, reviewed_at=recovery_at + timedelta(minutes=14))
    third = write_closed_cohort(root, core, cohort=3, ordinal=4, route=routes[2], source=sources[2], previous_settlement=second, reviewer=reviewer, reviewed_at=recovery_at + timedelta(minutes=22), renewal_sha256=renewal2)
    verified = core.verify_prefix(root, geometry, third, 3, expected_route_sha256=sha(routes[0]), expected_execution_source_sha256=sources[0], reviewer_task=reviewer)
    assert verified["epochs"][2]["execution_source_sha256"] == sources[2]
    assert verified["contacts"][2]["authorization_sha256"] == sha(recovery_raw)
