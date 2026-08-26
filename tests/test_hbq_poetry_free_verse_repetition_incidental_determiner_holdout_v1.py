from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v1"

ARCHIVED_FREEZE = pytest.mark.skip(
    reason=(
        "Archived freeze mechanics require reconstructing a package absent from "
        "declared source commit 6ae9ee0; the current checkout remains fail-closed."
    )
)


def study():
    spec = importlib.util.spec_from_file_location("s1_incidental_determiner_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_checkout_fails_closed_before_archival_mechanics():
    with pytest.raises(ValueError, match="Exact CWR source binding drifted"):
        study().validate_package()


def test_archived_contract_preserves_candidate_and_private_expected_state_boundary():
    module = study()
    contract = module.contract()
    assert contract["study_id"] == module.STUDY_ID
    assert contract["status"] == "provider_free_frozen_unexecuted"
    assert contract["execution"]["provider"] == "codex"
    assert contract["execution"]["slots"] == 3
    assert contract["promotion"] == "none"
    assert contract["candidate"] == {
        "leaf_id": module.LEAF_ID,
        "text": module._base().candidate_leaf()["text"],
    }
    assert contract["candidate_sha256"] == hashlib.sha256(module.canonical(contract["candidate"])).hexdigest()
    assert contract["predecessor"] == {
        "settled_state_count": 9,
        "terminal_sha256": module.PREDECESSOR_TERMINAL_SHA256,
        "v3_disposition": "settled_without_rerun",
    }
    assert contract["freshness_audit"] == {
        "frozen_prior_corpus_roots": list(module.FRESHNESS_AUDIT_ROOTS),
        "excluded_declared_descendants": list(module.EXCLUDED_DECLARED_DESCENDANTS),
    }
    assert not set(module.FRESHNESS_AUDIT_ROOTS) & set(module.EXCLUDED_DECLARED_DESCENDANTS)
    assert module.ROOT.name not in module.FRESHNESS_AUDIT_ROOTS
    assert module.motif_audit() == {
        "algorithm": "frozen-literal-carrier-and-distinctive-phrase-v2",
        "prior_public_corpora": 4,
        "status": "disjoint",
    }
    assert module.artifact()["text"] == (
        "At noon: the empty platform.\nA parcel under the bench.\n"
        "Three pigeons by the fountain—\nthen the timetable, still blank."
    )
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    assert '"expected_state":"private_controller_only"' in public
    assert '"expected_verdict"' not in public


@ARCHIVED_FREEZE
def test_three_opaque_singletons_freeze_raw_production_prompt_bytes(tmp_path: Path):
    module = study()
    result = module.dry_freeze(tmp_path)
    assert result["provider_calls"] == 0 and result["slots"] == 3
    root = tmp_path / "execution-dry"
    manifest = json.loads((root / "dry-manifest.v1.json").read_text(encoding="utf-8"))
    assert manifest["claim"] == "absent" and manifest["live_execution"] == "unavailable"
    assert set(manifest["slots"]) == {"n-6fe2", "n-a319", "n-c405"}
    slots = module.slots()
    for slot in slots:
        slot_id = slot["slot_id"]
        raw = (root / "frozen-prompts" / f"{slot_id}.prompt.txt").read_bytes()
        assert raw == module._render(slot, root).encode("utf-8")
        assert manifest["prompts"][slot_id]["sha256"] == hashlib.sha256(raw).hexdigest()
    source = (root / "frozen-prompts" / "n-6fe2.prompt.txt").read_bytes()
    checkpoint = tmp_path / "checkpoint.prompt.txt.gz"
    checkpoint.write_bytes(gzip.compress(source, mtime=0))
    assert module.validate_checkpoint_prompt("n-6fe2", checkpoint)["sha256"] == hashlib.sha256(source).hexdigest()
    checkpoint.write_bytes(gzip.compress(source.replace(b"\r\n", b"\n"), mtime=0))
    if b"\r\n" in source:
        with pytest.raises(ValueError, match="raw prompt bytes"):
            module.validate_checkpoint_prompt("n-6fe2", checkpoint)


def test_fresh_private_root_and_repeat_geometry_are_required(tmp_path: Path):
    module = study()
    assert {slot["repeat"] for slot in module.slots()} == {1, 2, 3}
    assert {slot["condition"]["batch_size"] for slot in module.slots()} == {1}
    assert {slot["condition"]["batch_attempts"] for slot in module.slots()} == {1}
    with pytest.raises(ValueError, match="Exact CWR source binding drifted"):
        module.dry_freeze(tmp_path)
    assert not (tmp_path / "execution-dry").exists()
    with pytest.raises(ValueError, match="External private"):
        module.set_work_root(book_root())
