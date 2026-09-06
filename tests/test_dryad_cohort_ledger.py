from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SPEC = importlib.util.spec_from_file_location("dryad_cohort_ledger", ROOT / "cohort_ledger.py")
assert SPEC and SPEC.loader
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


BASE_TIME = datetime(2026, 9, 5, tzinfo=timezone.utc)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _raw(value: object, *, pretty: bool = False) -> bytes:
    if pretty:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write(root: Path, relative: str, value: object, *, pretty: bool = False) -> bytes:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _raw(value, pretty=pretty)
    path.write_bytes(raw)
    return raw


def _plan() -> dict[str, object]:
    passes: list[dict[str, object]] = []
    requests: list[dict[str, object]] = []
    ordinal = 0
    stories = ("story-a", "story-b", "story-c")
    for batch_size in (8, 32):
        for repetition in range(1, 4):
            for story in stories:
                pass_id = f"size-{batch_size:04d}/repetition-{repetition:02d}/{story}"
                passes.append({"pass_id": pass_id, "batch_size": batch_size, "source_sha256": _hash("source-" + story)})
                for batch in range(1, (178 + batch_size - 1) // batch_size + 1):
                    ordinal += 1
                    requests.append({
                        "ordinal": ordinal,
                        "pass_id": pass_id,
                        "batch_number": batch,
                        "prompt_sha256": _hash(f"prompt-{ordinal}"),
                        "schema_sha256": _hash("schema"),
                    })
    assert ordinal == 261
    return {"passes": passes, "requests": requests}


def _build_ledger(
    root: Path,
    plan: dict[str, object],
    *,
    plan_sha256: str,
    duplicate_identity: bool = False,
    prepared_schema_version: object = 1,
    cohort_minutes: int = 20,
    admission_offset_minutes: int = 5,
    expiry_offset_minutes: int = 10,
) -> str:
    (root / "runs").mkdir(parents=True)
    (root / "runs" / "unrelated-native-evidence.txt").write_text("outside the ledger", encoding="utf-8")
    requests = {entry["ordinal"]: entry for entry in plan["requests"]}  # type: ignore[index]
    groups = ledger.cohort_groups(plan)
    previous = ledger.GENESIS_SETTLEMENT_SHA256
    for number, ordinals in enumerate(groups, start=1):
        prefix = f"cohorts/{number:04d}"
        reviewed_at = BASE_TIME + timedelta(minutes=(number - 1) * cohort_minutes)
        expires_at = reviewed_at + timedelta(minutes=expiry_offset_minutes)
        admitted_at = reviewed_at + timedelta(minutes=admission_offset_minutes)
        settled_at = reviewed_at + timedelta(minutes=max(admission_offset_minutes, 15))
        route = {"provider": "grok", "timeout_seconds": 60, "cohort": number % 2}
        route_sha256 = hashlib.sha256(_raw(route)).hexdigest()
        prepared = {
            "execution_source_sha256": _hash("reviewed-execution-source"),
            "schema_version": prepared_schema_version,
            "cohort_number": number,
            "plan_sha256": plan_sha256,
            "previous_settlement_sha256": previous,
            "request_ordinals": list(ordinals),
            "route_sha256": route_sha256,
        }
        prepared_raw = _write(root, f"{prefix}/prepared.json", prepared)
        review = {
            "schema_version": 1,
            "reviewer_task": ledger.REVIEWER_TASK,
            "decision": "approved_cohort",
            "prepared_sha256": _sha256(prepared_raw),
            "reviewed_at": _timestamp(reviewed_at),
            "expires_at": _timestamp(expires_at),
        }
        review_raw = _write(root, f"{prefix}/review.json", review, pretty=True)
        _write(root, f"{prefix}/route.json", route, pretty=True)
        settlement_contacts = []
        for ordinal in ordinals:
            request = requests[ordinal]
            contact = {
                "schema_version": 1,
                "cohort_number": number,
                "ordinal": ordinal,
                "plan_sha256": plan_sha256,
                "prepared_sha256": _sha256(prepared_raw),
                "review_sha256": _sha256(review_raw),
                "route_sha256": route_sha256,
                "prompt_sha256": request["prompt_sha256"],
                "schema_sha256": request["schema_sha256"],
                "admitted_at": _timestamp(admitted_at),
            }
            contact_raw = _write(root, f"contacts/request-{ordinal:04d}.json", contact, pretty=ordinal % 2 == 0)
            identity = _hash(f"identity-{ordinal if not duplicate_identity else 1}")
            settlement_contacts.append({
                "ordinal": ordinal,
                "contact_sha256": _sha256(contact_raw),
                "checkpoint_sha256": _hash(f"checkpoint-{ordinal}"),
                "request_id_hash": identity,
                "session_id_hash": _hash(f"session-{ordinal if not duplicate_identity else 1}"),
            })
        settlement = {
            "schema_version": 1,
            "cohort_number": number,
            "plan_sha256": plan_sha256,
            "prepared_sha256": _sha256(prepared_raw),
            "review_sha256": _sha256(review_raw),
            "route_sha256": route_sha256,
            "previous_settlement_sha256": previous,
            "settled_at": _timestamp(settled_at),
            "contacts": settlement_contacts,
        }
        settlement_raw = _write(root, f"{prefix}/settlement.json", settlement, pretty=number % 2 == 0)
        previous = _sha256(settlement_raw)
    return previous


def _truncate_ledger(root: Path, plan: dict[str, object], through_cohort: int) -> str:
    groups = ledger.cohort_groups(plan)
    for number in range(through_cohort + 1, len(groups) + 1):
        shutil.rmtree(root / "cohorts" / f"{number:04d}")
    for group in groups[through_cohort:]:
        for ordinal in group:
            (root / "contacts" / f"request-{ordinal:04d}.json").unlink()
    return ledger.GENESIS_SETTLEMENT_SHA256 if through_cohort == 0 else _sha256((root / "cohorts" / f"{through_cohort:04d}" / "settlement.json").read_bytes())


def test_cohort_groups_match_the_qualification_geometry() -> None:
    groups = ledger.cohort_groups(_plan())
    assert len(groups) == 27
    assert [len(group) for group in groups] == [10] * 20 + [7] + [10] * 5 + [4]
    assert [ordinal for group in groups for ordinal in group] == list(range(1, 262))


def test_verify_ledger_accepts_a_full_reviewed_chain(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    verified = ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)
    assert len(verified["routes"]) == 2
    assert len(verified["contacts"]) == 261
    assert verified["contacts"][1]["source_sha256"] == _hash("source-story-a")
    assert verified["head"] == {"cohort_number": 27, "settlement_sha256": head}


def test_verify_ledger_rejects_tampered_contact(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    (tmp_path / "contacts" / "request-0001.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)


def test_verify_ledger_rejects_wrong_plan_raw_and_closing_anchor(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    wrong_plan = _plan()
    wrong_plan["requests"][0]["prompt_sha256"] = "f" * 64  # type: ignore[index]
    wrong_plan_raw = _raw(wrong_plan)
    with pytest.raises(ValueError):
        ledger.verify_ledger(tmp_path, wrong_plan_raw, _sha256(wrong_plan_raw), head)
    with pytest.raises(ValueError, match="Exact plan hash"):
        ledger.verify_ledger(tmp_path, wrong_plan_raw, plan_sha256, head)
    with pytest.raises(ValueError, match="closing"):
        ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, "0" * 64)


def test_verify_ledger_rejects_duplicate_native_identity(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256, duplicate_identity=True)
    with pytest.raises(ValueError, match="duplicated"):
        ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)


def test_verify_ledger_rejects_boolean_schema_version(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256, prepared_schema_version=True)
    with pytest.raises(ValueError, match="integer"):
        ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)


def test_verify_ledger_rejects_contact_two_minutes_after_valid_expiry(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256, admission_offset_minutes=12)
    with pytest.raises(ValueError, match="outside the review window"):
        ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)


def test_verify_ledger_rejects_overlapping_review_windows_after_rehash(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256, cohort_minutes=5)
    with pytest.raises(ValueError, match="precedes previous settlement"):
        ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)


def test_verify_ledger_rejects_missing_and_extra_inventory(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    missing = tmp_path / "missing"
    missing_head = _build_ledger(missing, plan, plan_sha256=plan_sha256)
    (missing / "contacts" / "request-0261.json").unlink()
    with pytest.raises(ValueError, match="inventory"):
        ledger.verify_ledger(missing, plan_raw, plan_sha256, missing_head)
    extra = tmp_path / "extra"
    extra_head = _build_ledger(extra, plan, plan_sha256=plan_sha256)
    (extra / "contacts" / "orphan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        ledger.verify_ledger(extra, plan_raw, plan_sha256, extra_head)


def test_verify_prefix_zero_requires_empty_ledger_directories(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    (tmp_path / "cohorts").mkdir()
    (tmp_path / "contacts").mkdir()
    verified = ledger.verify_prefix(tmp_path, plan_raw, plan_sha256, ledger.GENESIS_SETTLEMENT_SHA256, 0)
    assert verified == {"routes": {}, "contacts": {}, "head": {"cohort_number": 0, "settlement_sha256": ledger.GENESIS_SETTLEMENT_SHA256}}


def test_verify_prefix_one_returns_only_the_settled_prefix(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    head = _truncate_ledger(tmp_path, plan, 1)
    verified = ledger.verify_prefix(tmp_path, plan_raw, plan_sha256, head, 1)
    assert len(verified["contacts"]) == 10
    assert verified["head"] == {"cohort_number": 1, "settlement_sha256": head}


def test_verify_prefix_accepts_only_explicit_pending_paths(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    head = _truncate_ledger(tmp_path, plan, 1)
    pending = frozenset({
        "cohorts/0002/prepared.json",
        "cohorts/0002/review.json",
        "cohorts/0002/route.json",
        "contacts/request-0011.json",
    })
    for relative in pending:
        _write(tmp_path, relative, {"caller": "authenticates-pending-content"})
    with pytest.raises(ValueError, match="inventory"):
        ledger.verify_prefix(tmp_path, plan_raw, plan_sha256, head, 1)
    verified = ledger.verify_prefix(tmp_path, plan_raw, plan_sha256, head, 1, pending)
    assert verified["head"]["settlement_sha256"] == head


def test_verify_prefix_rejects_unlisted_orphan_paths(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    head = _truncate_ledger(tmp_path, plan, 1)
    _write(tmp_path, "contacts/request-0011.json", {"orphan": True})
    with pytest.raises(ValueError, match="inventory"):
        ledger.verify_prefix(tmp_path, plan_raw, plan_sha256, head, 1)


def test_verify_prefix_all_cohorts_matches_full_verification(tmp_path: Path) -> None:
    plan = _plan()
    plan_raw = _raw(plan)
    plan_sha256 = _sha256(plan_raw)
    head = _build_ledger(tmp_path, plan, plan_sha256=plan_sha256)
    assert ledger.verify_prefix(tmp_path, plan_raw, plan_sha256, head, 27) == ledger.verify_ledger(tmp_path, plan_raw, plan_sha256, head)
