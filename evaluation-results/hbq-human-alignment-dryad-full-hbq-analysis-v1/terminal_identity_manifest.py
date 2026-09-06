"""Recompute predecessor identity commitments without altering failed evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PINS = {
    "identity_exclusion.py": "efc3c445137eff401ea2f422eb002d9db20767a2c3b39a674054b047d2c2131b",
    "historical_replay_runtime.py": "d98686761c4af296c4132a477bc54c3bcdfc3bb8b0140ffd2681919652fe81f9",
    "native_replay_core.py": "e19ff366586bf6097ceca9b3c74c44033f42d67bd1b2a2042578811288cc1900",
    "terminal_residue.py": "d525e6eebdd5d6864057c71dd1c6141f3423cfde78459a2f4b8e18fb00789f94",
    "qualification-attempt-2.json": "90639b16cd68d0a4b36821acdcc8ed802d510122973a8621cc0bbea6cc4a0be8",
    "terminal-identities-v1.json": "62fe2cc523cf8d22dff7f1010980ae98a19338f881d861bdf371ab5f3e37a52f",
    "cohort_ledger.py": "3b07db6d58c5bfdbca5c662c8b4fb5fdcc833fd1e421d58ce7e7d0e9928fe44a",
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _read_source(path: Path) -> bytes:
    for candidate in (path, *path.parents):
        info = candidate.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Identity source path contains a link or reparse point")
    require(path.is_file(), "Identity source must be a file")
    return path.read_bytes()


def _sources() -> tuple[dict[Path, bytes], dict[str, ModuleType]]:
    captures = {ROOT / name: _read_source(ROOT / name) for name in PINS}
    require(all(digest(captures[ROOT / name]) == expected for name, expected in PINS.items()), "Identity generator dependency differs")
    captures[Path(__file__).resolve()] = _read_source(Path(__file__).resolve())
    loaded = {}
    for name in ("identity_exclusion", "historical_replay_runtime", "native_replay_core", "cohort_ledger"):
        path = ROOT / (name + ".py")
        module = ModuleType("_dryad_identity_" + name)
        module.__file__ = str(path)
        exec(compile(captures[path], str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local definitions.
        loaded[name] = module
    return captures, loaded


def _generator(captures: dict[Path, bytes], commit: str | None = None) -> dict[str, Any]:
    if commit is None:
        result = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, check=False)
        require(result.returncode == 0, "Identity generation requires a Git commit")
        commit = result.stdout.decode("ascii").strip()
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Identity generator commit differs")
    files = {}
    for path, raw in captures.items():
        relative = path.relative_to(REPOSITORY).as_posix()
        stored = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{commit}:{relative}"], capture_output=True, check=False)
        require(stored.returncode == 0 and stored.stdout == raw, "Identity generation requires committed byte-exact source")
        files[relative] = digest(raw)
    return {"git_commit": commit, "files": files}


def _unsettled_contact(contact: dict[str, Any], review: dict[str, Any], *, prepared_sha256: str, authorization_sha256: str, route_sha256: str) -> None:
    require(contact["cohort_number"] == 3 and contact["review_sha256"] == authorization_sha256 and contact["prepared_sha256"] == prepared_sha256 and contact["route_sha256"] == route_sha256, "Unsettled prefix authorization or route differs")
    require(datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(contact["admitted_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00")), "Unsettled prefix contact outside review")


def build_manifest(prior_snapshot_root: Path, snapshot_root: Path, plan_root: Path, *, generator_commit: str | None = None) -> dict[str, Any]:
    captures, loaded = _sources()
    generator = _generator(captures, generator_commit)
    helper, loader, replay = (loaded[name] for name in ("identity_exclusion", "historical_replay_runtime", "native_replay_core"))
    prior, snapshot, plan_root = (helper._plain(path, file=False) for path in (prior_snapshot_root, snapshot_root, plan_root))
    roots = (prior, snapshot, plan_root)
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a) for index, a in enumerate(roots) for b in roots[index + 1:]), "Identity evidence roots overlap")
    old = helper._manifest()
    before_old, before = helper._tree(prior), helper._tree(snapshot)
    require(len(before_old) == old["terminal_snapshot_files"] == 73 and digest(canonical(before_old)) == old["terminal_snapshot_path_hash_map_sha256"], "V1 snapshot differs")
    attempt = helper._object(captures[ROOT / "qualification-attempt-2.json"], "V2 attempt")
    require(len(before) == 372 and digest(canonical(before)) == attempt["preserved_snapshot"]["path_hash_map_sha256"], "V2 snapshot differs")
    plan_raw = helper._plain(plan_root / "plan.json", file=True).read_bytes()
    require(digest(plan_raw) == attempt["qualification_plan_sha256"], "Historical plan differs")
    plan = helper._object(plan_raw, "Historical plan")
    pending = frozenset(name for name in before if name.startswith("cohorts/0003/") or name in {f"contacts/request-{ordinal:04d}.json" for ordinal in range(21, 29)})
    settled = loaded["cohort_ledger"].verify_prefix(snapshot, plan_raw, attempt["qualification_plan_sha256"], "837671ea2b2ce17ea7b6f5805dd954d4737cc950cb71391be9e26ff3588d8311", 2, pending)
    records = []
    for record in old["records"]:
        raw = helper._relative(prior, record["receipt_path"]).read_bytes()
        receipt = helper._object(raw, "V1 receipt")
        require(digest(raw) == record["receipt_sha256"] and all(receipt[key] == record[key] for key in ("request_id_hash", "session_id_hash")), "V1 identity commitment differs")
        records.append({"campaign": "qualification-v1", **record})
    runtime = loader.load_runtime()
    routes = {}
    for number in (1, 2, 3):
        route = helper._object(helper._relative(snapshot, f"cohorts/{number:04d}/route.json").read_bytes(), "Historical route")
        routes[digest(canonical(route))] = route
    results = []
    inputs = {}
    for index in (0, 1):
        passed = plan["passes"][index]
        path = helper._relative(plan_root, passed["input_path"])
        text_raw = path.read_bytes()
        inputs[path] = text_raw
        require(digest(text_raw) == passed["source_sha256"], "Historical input differs")
        source = {"opaque_story_id": passed["opaque_story_id"], "story_text": text_raw.decode("utf-8"), "artifact_path": str(path)}
        kwargs = {"source": source, "batch_size": 8, "approved_routes": routes, "runtime": runtime}
        run = helper._relative(snapshot, passed["run_path"], file=False)
        result = replay.admit_pass(run, **kwargs) if index == 0 else replay.admit_prefix(run, expected_batches=4, terminal_residue=True, **kwargs)
        results.append(result)
    require(len(results[0]["native_identities"]) == 23 and len(results[1]["native_identities"]) == 4 and results[1]["accepted_count"] == 32 and results[1]["score"] is None and results[1]["coverage"] is None, "Replayed identity geometry differs")
    identities = results[0]["native_identities"] + results[1]["native_identities"]
    passes = {item["pass_id"]: item for item in plan["passes"]}
    review_raw = helper._relative(snapshot, "cohorts/0003/review.json").read_bytes()
    review = helper._object(review_raw, "Third review")
    prepared_raw = helper._relative(snapshot, "cohorts/0003/prepared.json").read_bytes()
    prepared_sha = digest(prepared_raw)
    prepared = helper._object(prepared_raw, "Third preparation")
    third_route = helper._object(helper._relative(snapshot, "cohorts/0003/route.json").read_bytes(), "Third route")
    third_route_sha = digest(canonical(third_route))
    require(prepared["route_sha256"] == third_route_sha, "Third cohort prepared route differs")
    for ordinal, identity in enumerate(identities, start=1):
        request = plan["requests"][ordinal - 1]
        passed = passes[request["pass_id"]]
        relative = f"{passed['run_path']}/responses/grok-broker/batch-{request['batch_number']:04d}-attempt-0001/receipt.json"
        raw = helper._relative(snapshot, relative).read_bytes()
        receipt = helper._object(raw, "Replayed receipt")
        contact = helper._object(helper._relative(snapshot, f"contacts/request-{ordinal:04d}.json").read_bytes(), "Replayed contact")
        require(request["ordinal"] == ordinal == contact["ordinal"] and contact["plan_sha256"] == attempt["qualification_plan_sha256"] and contact["prompt_sha256"] == request["prompt_sha256"] and contact["schema_sha256"] == request["schema_sha256"] == receipt["schema_sha256"] and contact["route_sha256"] == receipt["route_sha256"], "Replayed contact binding differs")
        require(digest(raw) == before[relative] and all(receipt[key] == identity[key] for key in ("request_id_hash", "session_id_hash")), "Replayed native identity differs")
        checkpoint_path = f"{passed['run_path']}/responses/batch-{request['batch_number']:04d}.json"
        if ordinal <= 20:
            admitted = settled["contacts"][ordinal]
            require(admitted["checkpoint_sha256"] == before[checkpoint_path] and all(admitted[key] == identity[key] for key in ("request_id_hash", "session_id_hash")), "Settled prefix identity differs")
        else:
            require(digest(review_raw) == results[1]["terminal_residue"]["authorization_sha256"], "Unsettled prefix review differs")
            _unsettled_contact(contact, review, prepared_sha256=prepared_sha, authorization_sha256=digest(review_raw), route_sha256=third_route_sha)
        records.append({"campaign": "qualification-v2", "ordinal": ordinal, "receipt_path": relative, "receipt_sha256": digest(raw), "request_id_hash": identity["request_id_hash"], "session_id_hash": identity["session_id_hash"]})
    require(len(records) == 33 and len({item["request_id_hash"] for item in records}) == len({item["session_id_hash"] for item in records}) == 33, "Predecessor identities overlap")
    runtime.verify()
    require(helper._tree(prior) == before_old and helper._tree(snapshot) == before and helper._plain(plan_root / "plan.json", file=True).read_bytes() == plan_raw and all(helper._plain(path, file=True).read_bytes() == raw for path, raw in inputs.items()), "Identity evidence changed during replay")
    require(all(_read_source(path) == raw for path, raw in captures.items()), "Identity generator changed during replay")
    return {
        "schema_version": 2,
        "evidence_class": "preserved_predecessor_native_identity_exclusion",
        "generator": generator,
        "historical_rollback_manifest_sha256": loader.MANIFEST_SHA256,
        "historical_protocol_sha256": loader.PROTOCOL_SHA256,
        "v1_snapshot_sha256": digest(canonical(before_old)),
        "v2_snapshot_sha256": digest(canonical(before)),
        "v1_prior_committed_receipt_identities": 6,
        "v2_semantically_replayed_receipt_identities": 27,
        "completed_identity_records": 33,
        "records": records,
        "partial_replay_sha256": digest(canonical(results[1])),
        "unresolved_contact": {"campaign": "qualification-v2", "ordinal": 28, "state": "ambiguous_terminal_no_trusted_native_identity", "native_identity_claimed": False, "automatic_resend_permitted": False, "terminal_proof_sha256": digest(canonical(results[1]["terminal_residue"]))},
        "native_admission": False,
        "execution_authority": False,
        "qualification_satisfied": False,
        "alignment_result": False,
        "empirical_batch_cap": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-snapshot-root", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--plan-root", type=Path, required=True)
    parser.add_argument("--generator-commit", help="Recorded commit for byte-exact regeneration after HEAD advances")
    args = parser.parse_args()
    print(json.dumps(build_manifest(args.prior_snapshot_root, args.snapshot_root, args.plan_root, generator_commit=args.generator_commit), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
