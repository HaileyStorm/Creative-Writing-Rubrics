from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-other-lexical-overlap-ownership-v1-settlement-crlf-lf-repair-v1"
ARCHIVED_REASON = (
    "Archived lexical-overlap mechanics require six exact historical module snapshots "
    "that are unavailable in CWR Git history; preserve the frozen package and await a "
    "versioned successor or restored snapshot."
)


def study():
    spec = importlib.util.spec_from_file_location("l2_crlf_lf_settlement_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_checkout_fails_closed_while_settlement_contract_remains_bound():
    s = study()
    with pytest.raises(ValueError, match="Current production runtime binding drifted"):
        s.validate_package()
    assert s.contract()["geometry"] == {"execution_slots": 216, "three_repeat_cells": 72, "visual_attachment_slots": 72}
    assert s.contract()["provider_calls"] == "forbidden"
    assert s.contract()["public_result_policy"] == "aggregate_only_verified_diagnostic_fail_or_incomplete_no_promotion"
    assert s.contract()["promotion"] == "none"
    assert "--execute" not in (ROOT / "run.py").read_text(encoding="utf-8")
    assert "--allow-remote" not in (ROOT / "run.py").read_text(encoding="utf-8")


def test_prompt_compatibility_accepts_only_crlf_to_lf_and_retains_both_hashes():
    s = study()
    expected = b"first\nsecond\n"
    commitment = s._prompt_commitment(b"first\r\nsecond\r\n", expected)
    assert commitment["line_ending_transform"] == "crlf_to_lf"
    assert commitment["raw_sha256"] != commitment["canonical_sha256"]
    assert s._prompt_commitment(expected, expected)["line_ending_transform"] == "identity"
    with pytest.raises(ValueError, match="lone CR"):
        s._prompt_commitment(b"first\rsecond\n", expected)
    with pytest.raises(ValueError, match="differs beyond"):
        s._prompt_commitment(b"first\r\nchanged\r\n", expected)


@pytest.mark.skip(reason=ARCHIVED_REASON)
def test_manifest_contract_and_runtime_bindings_are_required():
    s = study()
    temporary = Path(tempfile.mkdtemp(prefix="l2-crlf-lf-manifest-"))
    try:
        execution_root = temporary / "execution"
        execution = s._execution()
        execution.dry_run(execution_root)
        schedule = s._schedule(execution)
        manifest_path = execution_root / "study-manifest.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in ("contract_sha256", "runtime_bindings"):
            altered = dict(original)
            altered[field] = {} if field == "runtime_bindings" else "0" * 64
            manifest_path.write_text(json.dumps(altered), encoding="utf-8")
            with pytest.raises(ValueError, match="Execution manifest"):
                s._validate_execution_root(execution_root, execution, schedule)
        manifest_path.write_text(json.dumps(original), encoding="utf-8")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def test_external_failed_settlement_is_incomplete_and_non_publicable():
    s = study()
    temporary = Path(tempfile.mkdtemp(prefix="l2-crlf-lf-settlement-"))
    try:
        execution_root = temporary / "execution"
        execution_root.mkdir()
        settlement_root = temporary / "settlement"
        result = s.settle(execution_root, settlement_root)
        assert result["decision"] == "INCOMPLETE" and result["provider_calls"] == 0
        public = json.loads((settlement_root / "public-aggregate.json").read_text(encoding="utf-8"))
        assert public["decision"] == "INCOMPLETE"
        assert public["publicable"] is False
        assert public["promotion"] == "none"
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
