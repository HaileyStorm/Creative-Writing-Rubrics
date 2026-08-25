from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("s1_v2_execution_v1_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_frozen(root: Path) -> Path:
    source = root / "frozen" / "execution-v2-6ae9ee0"
    (source / "catalog").mkdir(parents=True)
    for directory in ("contracts", "inputs", "overrides", "rendered-prompts", "runtime-book"):
        (source / directory).mkdir()
    (source / "catalog" / "one.json").write_text("{}", encoding="utf-8")
    (source / "contracts" / "one.json").write_text("{}", encoding="utf-8")
    (source / "inputs" / "one.txt").write_text("text", encoding="utf-8")
    (source / "overrides" / "one.json").write_text("{}", encoding="utf-8")
    (source / "rendered-prompts" / "one.txt").write_text("prompt", encoding="utf-8")
    (source / "runtime-book" / "one.txt").write_text("runtime", encoding="utf-8")
    (source / "dry-manifest.v2.json").write_text("{}", encoding="utf-8")
    return source.parent


def test_contract_binds_all_v2_and_reusable_v1_inputs_and_exposes_no_live_execute():
    module = study()
    assert module.contract() == module.expected_contract()
    bindings = module.contract()["v2_bindings"]
    assert set(bindings) == {"study_contract_sha256", "study_sha256", "public_corpus_sha256", "sealed_outcomes_sha256", "dry_manifest_sha256", "v1_public_corpus_sha256"}
    assert module.contract()["execution"]["live_execution_entrypoint"] == "unavailable_until_independent_review"
    assert "--execute" not in (ROOT / "run.py").read_text(encoding="utf-8")


def test_derive_snapshot_is_byte_exact_and_never_renders(tmp_path: Path, monkeypatch):
    module = study()
    monkeypatch.setattr(module, "REPOSITORY", tmp_path / "unrelated")
    frozen = make_frozen(tmp_path)
    work = tmp_path / "work"
    module.set_roots(frozen_root=frozen, work_root=work)
    monkeypatch.setattr(module, "validate_package", lambda: {"source_snapshot_sha256": "a" * 64})
    result = module.derive_snapshot()
    source = frozen / module.FROZEN_EXECUTION_DIRECTORY
    target = module.preclaim_root() / module.SNAPSHOT_DIRECTORY
    assert result["provider_calls"] == 0
    assert module.snapshot_map(source) == module.snapshot_map(target)
    assert not (target / "runs").exists()


def test_claim_only_writes_once_and_rejects_preexisting_execution_state(tmp_path: Path, monkeypatch):
    module = study()
    monkeypatch.setattr(module, "REPOSITORY", tmp_path / "unrelated")
    work = tmp_path / "work"; frozen = tmp_path / "frozen"
    module.set_roots(frozen_root=frozen, work_root=work)
    root = module.preclaim_root(); root.mkdir(parents=True)
    monkeypatch.setattr(module, "derive_snapshot", lambda: {"snapshot_receipt_sha256": "b" * 64})
    first = module.claim_only()
    assert first["provider_calls"] == 0
    with pytest.raises(ValueError, match="already exists"):
        module.claim_only()
    (tmp_path / "work-two").mkdir()
    module.set_roots(frozen_root=frozen, work_root=tmp_path / "work-two")
    root = module.preclaim_root(); root.mkdir(parents=True); (root / "runs").mkdir()
    with pytest.raises(ValueError, match="execution state"):
        module.claim_only()


def test_live_execution_is_explicitly_unavailable():
    with pytest.raises(ValueError, match="unavailable"):
        study().execution_unavailable()


def test_public_package_contains_no_external_path_or_private_result_material():
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    for forbidden in ("C:\\Users\\", "target_verdict", "oracle", "expected_states"):
        assert forbidden not in public
