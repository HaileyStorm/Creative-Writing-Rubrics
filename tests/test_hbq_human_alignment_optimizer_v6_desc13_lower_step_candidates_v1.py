"""Provider-free regressions for the four descendant-13 lower-step candidates."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-candidates-v1"
PARENT = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1" / "profile.json"


def module():
    spec = importlib.util.spec_from_file_location("desc13_lower_step_candidates", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_exact_four_candidate_freeze_preserves_parent_instruction_and_all_unchanged_profile_fields():
    study = module()
    manifest = study.materialize()
    assert manifest["candidate_count"] == len(manifest["candidates"]) == 4
    assert [row["candidate_id"] for row in manifest["candidates"]] == [row[0] for row in study.CHILDREN]
    _document, instruction, parent_profile, _profile, _ancestry = study._parent()
    for candidate, (_candidate_id, factor, addendum) in zip(manifest["candidates"], study.CHILDREN, strict=True):
        profile = json.loads(base64.b64decode(candidate["profile_base64"], validate=True))
        assert base64.b64decode(candidate["instruction_base64"], validate=True) == instruction
        assert set(profile["factors"]) == set(parent_profile["factors"])
        assert [key for key in parent_profile["factors"] if profile["factors"][key] != parent_profile["factors"][key]] == [factor]
        assert profile["factors"][factor] == parent_profile["factors"][factor] + "\n" + addendum
        assert profile["factors"][factor].count(addendum) == 1
        assert {key: value for key, value in profile.items() if key != "factors"} == {key: value for key, value in parent_profile.items() if key != "factors"}


def test_frozen_candidate_bytes_and_manifest_reparse_exactly(tmp_path: Path):
    study = module()
    root = tmp_path / "freeze"
    manifest = study.freeze(output_root=root)
    assert (root / "manifest.json").read_bytes() == study.canonical(manifest)
    assert {path.name for path in root.iterdir()} == {"manifest.json", *(row["candidate_id"] + ".json" for row in manifest["candidates"])}
    for candidate in manifest["candidates"]:
        assert (root / f"{candidate['candidate_id']}.json").read_bytes() == study.canonical(candidate)
    assert study.validate_frozen_root(root) == manifest


def test_geometry_factor_instruction_and_duplicate_addendum_drift_are_rejected(monkeypatch: pytest.MonkeyPatch):
    study = module()
    original = study.CHILDREN
    monkeypatch.setattr(study, "CHILDREN", original[:3])
    with pytest.raises(ValueError, match="geometry"):
        study.materialize()
    monkeypatch.setattr(study, "CHILDREN", ((original[0][0], "unknown_factor", original[0][2]), *original[1:]))
    with pytest.raises(ValueError, match="factor surface"):
        study.materialize()
    monkeypatch.setattr(study, "CHILDREN", ((original[0][0], original[0][1], original[1][2]), *original[1:]))
    with pytest.raises(ValueError, match="addendum uniqueness"):
        study.materialize()
    monkeypatch.setattr(study, "CHILDREN", ((original[0][0], original[0][1], original[0][2] + " drift"), *original[1:]))
    with pytest.raises(ValueError, match="commitments"):
        study.materialize()


def test_parent_or_persisted_bytes_cannot_change_between_materialization_phases(tmp_path: Path):
    study = module()
    parent = tmp_path / "parent.json"
    shutil.copyfile(PARENT, parent)
    root = tmp_path / "freeze"
    study.freeze(output_root=root, parent_path=parent)
    parent.write_bytes(parent.read_bytes().replace(b"localized_revision_note", b"localized_revision_notex", 1))
    with pytest.raises(ValueError, match="immutable recommended descendant13 document"):
        study.validate_frozen_root(root, parent_path=parent)
    manifest_path = root / "manifest.json"
    tampered = json.loads(manifest_path.read_bytes())
    tampered["candidates"][0]["candidate_id"] += "-tampered"
    manifest_path.write_bytes(study.canonical(tampered))
    with pytest.raises(ValueError, match="persisted manifest|commitments"):
        study.validate_frozen_root(root)


def test_stable_read_and_freeze_reject_adversarial_same_byte_swaps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    study = module()
    parent = tmp_path / "parent.json"
    replacement = tmp_path / "replacement.json"
    shutil.copyfile(PARENT, parent)
    shutil.copyfile(PARENT, replacement)
    original_ancestry = study._ancestry
    calls = 0

    def swap_between_read_snapshots(path: Path, *, directory: bool):
        nonlocal calls
        calls += 1
        if calls == 2:
            os.replace(replacement, parent)
        return original_ancestry(path, directory=directory)

    monkeypatch.setattr(study, "_ancestry", swap_between_read_snapshots)
    with pytest.raises(ValueError, match="stable full-ancestry read drift"):
        study._stable(parent)

    monkeypatch.setattr(study, "_ancestry", original_ancestry)
    shutil.copyfile(PARENT, parent)
    shutil.copyfile(PARENT, replacement)
    original_materialize = study._materialize
    phases = 0

    def swap_between_materialization_phases(*, parent_path: Path):
        nonlocal phases
        result = original_materialize(parent_path=parent_path)
        phases += 1
        if phases == 1:
            os.replace(replacement, parent)
        return result

    monkeypatch.setattr(study, "_materialize", swap_between_materialization_phases)
    with pytest.raises(ValueError, match="parent changed between materialization phases"):
        study.freeze(output_root=tmp_path / "freeze", parent_path=parent)


def test_final_validation_rejects_same_byte_parent_swap_after_second_materialization(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    study = module()
    parent = tmp_path / "parent.json"
    replacement = tmp_path / "replacement.json"
    shutil.copyfile(PARENT, parent)
    shutil.copyfile(PARENT, replacement)
    root = tmp_path / "freeze"
    original_write = Path.write_bytes
    swapped = False

    def swap_before_persist(path: Path, data: bytes) -> int:
        nonlocal swapped
        if not swapped and path.parent == root:
            swapped = True
            os.replace(replacement, parent)
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", swap_before_persist)
    with pytest.raises(ValueError, match="parent changed before final frozen-root validation"):
        study.freeze(output_root=root, parent_path=parent)


def test_inventory_extra_candidate_corruption_and_reparse_are_rejected(tmp_path: Path):
    study = module()
    root = tmp_path / "freeze"
    manifest = study.freeze(output_root=root)
    (root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        study.validate_frozen_root(root)
    (root / "extra.json").unlink()
    candidate_path = root / f"{manifest['candidates'][0]['candidate_id']}.json"
    candidate_path.write_bytes(study.canonical({**manifest["candidates"][0], "addendum": "tampered"}))
    with pytest.raises(ValueError, match="persisted candidate"):
        study.validate_frozen_root(root)
    candidate_path.write_bytes(study.canonical(manifest["candidates"][0]))
    link = root / "unsafe.json"
    try:
        os.symlink(root / "manifest.json", link)
    except OSError:
        pytest.skip("symlink privilege is unavailable")
    with pytest.raises(ValueError, match="inventory"):
        study.validate_frozen_root(root)


def test_ancestor_reparse_is_rejected_for_parent_output_and_frozen_root_when_supported(tmp_path: Path):
    study = module()
    real = tmp_path / "real"
    real.mkdir()
    parent = real / "parent.json"
    shutil.copyfile(PARENT, parent)
    linked = tmp_path / "linked"
    try:
        os.symlink(real, linked, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink or junction privilege is unavailable")
    with pytest.raises(ValueError, match="unsafe reparse artifact ancestry"):
        study.materialize(parent_path=linked / "parent.json")
    with pytest.raises(ValueError, match="unsafe reparse artifact ancestry"):
        study.freeze(output_root=linked / "freeze", parent_path=PARENT)
    root = real / "freeze"
    study.freeze(output_root=root)
    with pytest.raises(ValueError, match="unsafe reparse artifact ancestry"):
        study.validate_frozen_root(linked / "freeze")


def test_fresh96_validation_private_identifier_path_and_score_leakage_variants_are_rejected():
    study = module()
    manifest = study.materialize()
    study.assert_no_fresh96_leakage(manifest)
    with pytest.raises(ValueError, match="Fresh96"):
        study.assert_no_fresh96_leakage({"synthetic": "prompt-1234", "score": 5})
    with pytest.raises(ValueError, match="Fresh96"):
        study.assert_no_fresh96_leakage({"synthetic": 4.2}, forbidden=("4.2",))
    with pytest.raises(ValueError, match="Fresh96"):
        study.assert_no_fresh96_leakage({"synthetic": r"C:\\Users\\Haile\\Documents\\cwr-hanna96-fresh-private-freeze"})
    for marker in ("Fresh96", "fresh-96", "fresh_96", "fresh 96", "future-confirmation", "future_confirmation", "future confirmation", "private-freeze", "private_freeze", "private freeze"):
        with pytest.raises(ValueError, match="Fresh96"):
            study.assert_no_fresh96_leakage({"synthetic": marker})
    source = (PACKAGE / "study.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert "def execute" not in source and "requests." not in source
