import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/identity_exclusion.py"
SPEC = importlib.util.spec_from_file_location("dryad_identity_exclusion", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else _canonical(value)
    path.write_bytes(raw)
    return raw


def _receipt_path(case, ordinal):
    return case.execution / f"runs/pass-0001/responses/grok-broker/batch-{ordinal:04d}-attempt-0001/receipt.json"


@pytest.fixture
def case(tmp_path, monkeypatch):
    prior = tmp_path / "prior"
    plan_root = tmp_path / "plan"
    execution = tmp_path / "execution"
    exclusion = tmp_path / "exclusion.json"
    old_plan_sha = _hash(b"old qualification plan")
    prior_request = []
    prior_session = []
    records = []
    for ordinal in range(1, 7):
        request_id = _hash(f"old-request-{ordinal}".encode())
        session_id = _hash(f"old-session-{ordinal}".encode())
        receipt_path = Path("receipts") / f"receipt-{ordinal:04d}.json"
        raw = _write(prior / receipt_path, {"request_id_hash": request_id, "session_id_hash": session_id})
        records.append({
            "ordinal": ordinal,
            "receipt_path": receipt_path.as_posix(),
            "receipt_sha256": _hash(raw),
            "request_id_hash": request_id,
            "session_id_hash": session_id,
        })
        prior_request.append(request_id)
        prior_session.append(session_id)
    for number in range(67):
        _write(prior / f"synthetic-snapshot-file-{number:02d}.txt", b"synthetic fixture")
    tree = {
        path.relative_to(prior).as_posix(): _hash(path.read_bytes())
        for path in prior.rglob("*")
        if path.is_file()
    }
    manifest = {
        "schema_version": 1,
        "evidence_class": "preserved_terminal_native_identity_exclusion",
        "predecessor_plan_sha256": old_plan_sha,
        "terminal_snapshot_path_hash_map_sha256": _hash(_canonical(tree)),
        "terminal_snapshot_files": len(tree),
        "records": records,
        "native_admission": False,
    }
    exclusion_raw = _write(exclusion, manifest)

    requests = [
        {"ordinal": ordinal, "pass_id": "pass-0001", "batch_number": ordinal}
        for ordinal in (1, 2)
    ]
    plan = {"passes": [{"pass_id": "pass-0001", "run_path": "runs/pass-0001"}], "requests": requests}
    plan_raw = _write(plan_root / "plan.json", plan)
    plan_sha = _hash(plan_raw)
    assert plan_sha != old_plan_sha
    current_request = [_hash(f"new-request-{ordinal}".encode()) for ordinal in (1, 2)]
    current_session = [_hash(f"new-session-{ordinal}".encode()) for ordinal in (1, 2)]
    for ordinal in (1, 2):
        _write(execution / f"contacts/request-{ordinal:04d}.json", {"ordinal": ordinal, "plan_sha256": plan_sha})
        _write(_receipt_path(SimpleNamespace(execution=execution), ordinal), {
            "request_id_hash": current_request[ordinal - 1],
            "session_id_hash": current_session[ordinal - 1],
        })

    monkeypatch.setattr(subject, "EXCLUSION", exclusion)
    monkeypatch.setattr(subject, "EXCLUSION_SHA256", _hash(exclusion_raw))
    return SimpleNamespace(
        prior=prior,
        plan_root=plan_root,
        execution=execution,
        plan_sha=plan_sha,
        plan_raw=plan_raw,
        prior_request=prior_request,
        prior_session=prior_session,
        current_request=current_request,
        current_session=current_session,
    )


def _verify(case, contacts=2):
    return subject.verify_identity_exclusion(
        case.prior,
        case.plan_root,
        case.execution,
        expected_plan_sha256=case.plan_sha,
        expected_contacts=contacts,
    )


def test_vacuous_zero_contacts(case):
    for path in (case.execution / "contacts").iterdir():
        path.unlink()
    import shutil
    shutil.rmtree(case.execution / "runs")
    result = _verify(case, contacts=0)
    assert result["vacuous"] is True
    assert result["current_contacts"] == 0
    assert result["current_receipts_sha256"] == _hash(_canonical({}))
    assert result["current_evidence_sha256"] == _hash(_canonical({}))


def test_two_valid_contacts_are_disjoint(case):
    result = _verify(case)
    expected_receipts = {
        f"runs/pass-0001/responses/grok-broker/batch-{ordinal:04d}-attempt-0001/receipt.json": _hash(
            _receipt_path(case, ordinal).read_bytes()
        )
        for ordinal in (1, 2)
    }
    assert result["native_admission"] is False
    assert result["execution_authority"] is False
    assert result["prior_records"] == 6
    assert result["current_contacts"] == 2
    assert result["plan_sha256"] == case.plan_sha
    assert result["current_receipts_sha256"] == _hash(_canonical(expected_receipts))
    assert result["vacuous"] is False


@pytest.mark.parametrize("field", ["request_id_hash", "session_id_hash"])
def test_old_identity_collision_is_rejected(case, field):
    receipt = _receipt_path(case, 2)
    value = json.loads(receipt.read_bytes())
    value[field] = case.prior_request[0] if field == "request_id_hash" else case.prior_session[0]
    receipt.write_bytes(_canonical(value))
    with pytest.raises(ValueError):
        _verify(case)


@pytest.mark.parametrize("field", ["request_id_hash", "session_id_hash"])
def test_current_identity_duplicate_is_rejected(case, field):
    receipt = _receipt_path(case, 2)
    value = json.loads(receipt.read_bytes())
    value[field] = case.current_request[0] if field == "request_id_hash" else case.current_session[0]
    receipt.write_bytes(_canonical(value))
    with pytest.raises(ValueError):
        _verify(case)


@pytest.mark.parametrize("mode", ["missing", "malformed"])
def test_missing_or_malformed_receipt_is_rejected(case, mode):
    receipt = _receipt_path(case, 2)
    if mode == "missing":
        receipt.unlink()
    else:
        receipt.write_bytes(b"{")
    with pytest.raises(ValueError):
        _verify(case)


def test_extra_receipt_inventory_is_rejected(case):
    _write(case.execution / "runs/pass-0001/responses/grok-broker/batch-0099-attempt-0001/receipt.json", b"{}")
    with pytest.raises(ValueError):
        _verify(case)


def test_plan_and_snapshot_drift_are_rejected(case):
    plan_path = case.plan_root / "plan.json"
    plan_path.write_bytes(case.plan_raw + b" ")
    with pytest.raises(ValueError):
        _verify(case)
    plan_path.write_bytes(case.plan_raw)
    snapshot_receipt = case.prior / "receipts/receipt-0001.json"
    snapshot_receipt.write_bytes(snapshot_receipt.read_bytes() + b" ")
    with pytest.raises(ValueError):
        _verify(case)


def test_read_time_current_tamper_is_rejected(case, monkeypatch):
    target = _receipt_path(case, 1).resolve()
    original = Path.read_bytes
    reads = 0

    def changing_read(path):
        nonlocal reads
        raw = original(path)
        if path.resolve() == target:
            reads += 1
            if reads >= 2:
                return raw + b" "
        return raw

    monkeypatch.setattr(Path, "read_bytes", changing_read)
    with pytest.raises(ValueError):
        _verify(case)
