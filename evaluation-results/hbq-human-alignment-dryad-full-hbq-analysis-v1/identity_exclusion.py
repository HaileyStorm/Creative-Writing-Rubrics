"""Read-only exclusion of identities preserved by the terminal Dryad campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXCLUSION = ROOT / "terminal-identities-v1.json"
EXCLUSION_SHA256 = "62fe2cc523cf8d22dff7f1010980ae98a19338f881d861bdf371ab5f3e37a52f"
_HASH = re.compile(r"[0-9a-f]{64}\Z")

def _hash(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def _need(value: bool, message: str) -> None:
    if not value: raise ValueError(message)

def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None

def _plain(path: Path, *, file: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        try: info = item.lstat()
        except FileNotFoundError: continue
        _need(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "Path contains a link or reparse point")
    result = absolute.resolve()
    if file is True: _need(result.is_file(), "Expected file")
    if file is False: _need(result.is_dir(), "Expected directory")
    return result

def _object(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, f"{label} duplicate key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} malformed"); return value

def _relative(root: Path, name: Any, *, file: bool = True) -> Path:
    _need(isinstance(name, str) and bool(name), "Relative path malformed")
    path = Path(name)
    _need(not path.is_absolute() and not path.drive and ".." not in path.parts, "Relative path escapes root")
    result = _plain(root / path, file=file)
    _need(result.is_relative_to(root), "Relative path escapes root")
    return result

def _tree(root: Path) -> dict[str, str]:
    root = _plain(root, file=False); result = {}
    for current, dirs, files in os.walk(root):
        for name in dirs + files:
            info = (Path(current) / name).lstat()
            _need(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "Snapshot tree contains a link")
        for name in files:
            path = Path(current) / name; _need(stat.S_ISREG(path.stat().st_mode), "Snapshot tree contains special file")
            result[path.relative_to(root).as_posix()] = _hash(path.read_bytes())
    return result

def _manifest() -> dict[str, Any]:
    raw = _plain(EXCLUSION, file=True).read_bytes(); _need(_hash(raw) == EXCLUSION_SHA256, "Exclusion manifest hash differs")
    value = _object(raw, "Exclusion manifest")
    _need(set(value) == {"schema_version", "evidence_class", "predecessor_plan_sha256", "terminal_snapshot_path_hash_map_sha256", "terminal_snapshot_files", "records", "native_admission"} and value["schema_version"] == 1 and value["native_admission"] is False, "Exclusion manifest schema differs")
    _need(value["evidence_class"] == "preserved_terminal_native_identity_exclusion"
          and type(value["terminal_snapshot_files"]) is int and value["terminal_snapshot_files"] == 73,
          "Exclusion manifest evidence contract differs")
    records = value["records"]
    _need(isinstance(records, list) and len(records) == 6 and [item.get("ordinal") if isinstance(item, dict) else None for item in records] == list(range(1, 7)), "Exclusion record inventory differs")
    for item in records:
        _need(set(item) == {"ordinal", "receipt_path", "receipt_sha256", "request_id_hash", "session_id_hash"} and isinstance(item["receipt_path"], str) and all(_valid_hash(item[key]) for key in ("receipt_sha256", "request_id_hash", "session_id_hash")), "Exclusion record differs")
    return value

def verify_identity_exclusion(prior_snapshot_root: Path, plan_root: Path, execution_root: Path, *, expected_plan_sha256: str, expected_contacts: int) -> dict[str, Any]:
    _need(_valid_hash(expected_plan_sha256) and type(expected_contacts) is int and expected_contacts >= 0, "Exclusion arguments differ")
    manifest = _manifest(); _need(manifest["predecessor_plan_sha256"] != expected_plan_sha256, "Current plan must differ from predecessor")
    snapshot, plan_root, execution_root = _plain(prior_snapshot_root, file=False), _plain(plan_root, file=False), _plain(execution_root, file=False)
    roots = (snapshot, plan_root, execution_root)
    _need(all(not a.is_relative_to(b) and not b.is_relative_to(a) for index, a in enumerate(roots) for b in roots[index + 1:]), "Evidence roots overlap")
    before = _tree(snapshot); _need(len(before) == manifest["terminal_snapshot_files"] and _hash(_canonical(before)) == manifest["terminal_snapshot_path_hash_map_sha256"], "Terminal snapshot tree differs")
    prior_request, prior_session = set(), set()
    for record in manifest["records"]:
        raw = _relative(snapshot, record["receipt_path"]).read_bytes(); _need(_hash(raw) == record["receipt_sha256"], "Terminal receipt differs")
        receipt = _object(raw, "Terminal receipt"); _need(receipt.get("request_id_hash") == record["request_id_hash"] and receipt.get("session_id_hash") == record["session_id_hash"], "Terminal receipt identity differs")
        prior_request.add(record["request_id_hash"]); prior_session.add(record["session_id_hash"])
    _need(len(prior_request) == len(prior_session) == 6, "Terminal identities are duplicated")
    plan_raw = _plain(plan_root / "plan.json", file=True).read_bytes(); _need(_hash(plan_raw) == expected_plan_sha256, "Plan hash differs")
    plan = _object(plan_raw, "Plan"); requests = plan.get("requests"); passes = plan.get("passes")
    _need(isinstance(requests, list) and isinstance(passes, list), "Plan schema differs")
    _need(all(isinstance(item, dict) and type(item.get("ordinal")) is int for item in requests)
          and [item["ordinal"] for item in requests] == list(range(1, len(requests) + 1))
          and expected_contacts <= len(requests), "Plan request inventory differs")
    _need(all(isinstance(item, dict) and isinstance(item.get("pass_id"), str) for item in passes)
          and len({item["pass_id"] for item in passes}) == len(passes), "Plan pass inventory differs")
    by_ordinal = {item.get("ordinal"): item for item in requests if isinstance(item, dict)}; by_pass = {item.get("pass_id"): item for item in passes if isinstance(item, dict)}
    current_before = _tree(execution_root)
    contacts_dir = _plain(execution_root / "contacts", file=False); contact_paths = sorted(contacts_dir.glob("request-*.json"))
    _need([path.name for path in contact_paths] == [f"request-{number:04d}.json" for number in range(1, expected_contacts + 1)], "Current contact inventory differs")
    _need(set(contacts_dir.iterdir()) == set(contact_paths), "Extra current contact inventory")
    current_request, current_session, receipts = set(), set(), {}
    for ordinal, contact_path in enumerate(contact_paths, start=1):
        contact = _object(_plain(contact_path, file=True).read_bytes(), "Contact")
        _need(contact.get("ordinal") == ordinal and contact.get("plan_sha256") == expected_plan_sha256, "Current contact differs")
        request = by_ordinal.get(ordinal); _need(isinstance(request, dict) and request.get("pass_id") in by_pass, "Plan ordinal differs")
        run = by_pass[request["pass_id"]].get("run_path"); batch = request.get("batch_number")
        _need(isinstance(run, str) and type(batch) is int and batch > 0, "Plan receipt path differs")
        receipt_path = _relative(execution_root, f"{run}/responses/grok-broker/batch-{batch:04d}-attempt-0001/receipt.json")
        raw = receipt_path.read_bytes(); receipt = _object(raw, "Current receipt")
        request_id, session_id = receipt.get("request_id_hash"), receipt.get("session_id_hash")
        _need(_valid_hash(request_id) and _valid_hash(session_id), "Current receipt identity differs")
        _need(request_id not in current_request | prior_request and session_id not in current_session | prior_session, "Identity collision differs")
        current_request.add(request_id); current_session.add(session_id); receipts[receipt_path.relative_to(execution_root).as_posix()] = _hash(raw)
    _need({name for name in current_before if Path(name).name == "receipt.json"} == set(receipts), "Current native receipt inventory differs")
    _need(all(current_before.get(name) == value for name, value in receipts.items()), "Current receipts changed during verification")
    _need(_tree(snapshot) == before and _manifest() == manifest, "Terminal snapshot changed during verification")
    _need(_tree(execution_root) == current_before and (plan_root / "plan.json").read_bytes() == plan_raw, "Current evidence changed during verification")
    return {"evidence_class": "read_only_terminal_identity_exclusion", "native_admission": False, "execution_authority": False, "prior_records": 6, "current_contacts": expected_contacts, "plan_sha256": expected_plan_sha256, "terminal_snapshot_sha256": manifest["terminal_snapshot_path_hash_map_sha256"], "exclusion_sha256": EXCLUSION_SHA256, "current_receipts_sha256": _hash(_canonical(receipts)), "current_evidence_sha256": _hash(_canonical(current_before)), "vacuous": expected_contacts == 0}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--prior-snapshot-root", type=Path, required=True); parser.add_argument("--plan-root", type=Path, required=True); parser.add_argument("--execution-root", type=Path, required=True); parser.add_argument("--plan-sha256", required=True); parser.add_argument("--contacts", type=int, required=True); args = parser.parse_args()
    print(json.dumps(verify_identity_exclusion(args.prior_snapshot_root, args.plan_root, args.execution_root, expected_plan_sha256=args.plan_sha256, expected_contacts=args.contacts), sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
