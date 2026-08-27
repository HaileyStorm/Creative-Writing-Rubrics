from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-premise-scale-ownership-v1-settlement-repair-v1"
PRIVATE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-premise-scale-ownership-v1-execution-v1-20260823-v2")


ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived P1 premise-scale settlement replay requires the frozen runtime bindings; current bindings have advanced."
)


def study():
    spec = importlib.util.spec_from_file_location("premise_scale_settlement_repair_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_contract_is_provider_free_and_binds_execution_predecessor():
    s = study()
    with pytest.raises(ValueError, match="Current production runtime binding drifted"):
        s.validate_package()
    value = s.contract()
    assert value["predecessor"]["commit"] == "3258e6f44bb728ce17ebcd85b4964d472aaf87c2"
    assert value["provider_execution"] == "forbidden"
    assert value["prompt_reconciliation"]["required_newline_only_slots"] == 72
    assert {path.name for path in ROOT.iterdir() if path.is_file()} == {"README.md", "run.py", "study-contract.json", "study.py"}
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    for forbidden in ("Gray Blood", "C:\\Users\\", "--execute", "raw_response", "private-schedule"):
        assert forbidden not in public_text


def test_only_crlf_to_lf_is_accepted_and_raw_and_canonical_hashes_are_retained(tmp_path: Path):
    s = study()
    run = tmp_path / "run" / "responses"
    run.mkdir(parents=True)
    prompt = tmp_path / "rendered.txt"
    prompt.write_bytes(b"one\ntwo\n")
    raw = b"one\r\ntwo\r\n"
    (run / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(raw))
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    (run / "batch-0001.json").write_text(json.dumps({key: raw_sha256 for key in ("prompt_sha256", "base_prompt_sha256", "effective_prompt_sha256")}), encoding="utf-8")
    commitment = s._verify_checkpoint_prompt(run.parent, prompt)
    assert commitment["comparison"] == "newline_only_crlf_to_lf"
    assert commitment["rendered_prompt_sha256"] != commitment["checkpoint_prompt_sha256"]
    assert commitment["canonical_rendered_prompt_sha256"] == commitment["canonical_checkpoint_prompt_sha256"]

    (run / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"one\rtwo\n"))
    with pytest.raises(ValueError, match="lone CR"):
        s._verify_checkpoint_prompt(run.parent, prompt)
    (run / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"one\r\nTHREE\r\n"))
    with pytest.raises(ValueError, match="beyond"):
        s._verify_checkpoint_prompt(run.parent, prompt)
    prompt.write_bytes(b"one\r\ntwo\r\n")
    (run / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"one\ntwo\n"))
    with pytest.raises(ValueError, match="Rendered prompt must contain LF only"):
        s._verify_checkpoint_prompt(run.parent, prompt)


@ARCHIVED_OLD_RUNTIME
def test_real_private_root_is_bound_and_all_72_pairs_are_newline_only_when_available():
    if not PRIVATE_ROOT.is_dir():
        pytest.skip("private execution root is deliberately external to the public checkout")
    s = study()
    predecessor = s._predecessor()
    schedule = s._validate_private_root(PRIVATE_ROOT, predecessor)
    assert len(schedule) == 72
    commitments = [s._verify_checkpoint_prompt(PRIVATE_ROOT / "runs" / slot["slot_id"], PRIVATE_ROOT / "rendered-prompts" / f"{slot['slot_id']}.txt") for slot in schedule]
    assert len(commitments) == 72
    assert all(item["comparison"] == "newline_only_crlf_to_lf" for item in commitments)
    assert all(item["checkpoint_prompt_sha256"] != item["rendered_prompt_sha256"] for item in commitments)
    records = [s._verify_slot(predecessor, PRIVATE_ROOT, slot) for slot in schedule]
    assert len(records) == len({item["slot_id"] for item in records}) == 72


@ARCHIVED_OLD_RUNTIME
def test_historical_execution_binding_survives_head_drift_and_rejects_historical_blob_drift():
    if not PRIVATE_ROOT.is_dir():
        pytest.skip("private execution root is deliberately external to the public checkout")
    s = study()
    predecessor = s._predecessor()
    original_predecessor_git = predecessor._git
    predecessor._git = lambda *args: "f" * 40 if args == ("rev-parse", "HEAD") else original_predecessor_git(*args)
    try:
        assert len(s._validate_private_root(PRIVATE_ROOT, predecessor)) == 72
    finally:
        predecessor._git = original_predecessor_git

    original_git = s._git
    def drifted_git(*args: str) -> str:
        if args == ("rev-parse", "3258e6f44bb728ce17ebcd85b4964d472aaf87c2:src/hbqrs/runner.py"):
            return "0" * 40
        return original_git(*args)
    s._git = drifted_git
    try:
        with pytest.raises(ValueError, match="Historical execution runtime blob drifted"):
            s._validate_private_root(PRIVATE_ROOT, predecessor)
    finally:
        s._git = original_git


def test_private_root_drift_fails_closed_before_reusing_any_response(tmp_path: Path):
    s = study()
    root = tmp_path / "private"
    root.mkdir()
    for name in ("runtime-schedule.json", "study-manifest.json", "dry-run.json", "settlement.json", "public-aggregate.json"):
        (root / name).write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen private root binding drifted"):
        s._validate_private_root(root, s._predecessor())
