from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from _hbq_s1_historical_runtime import (
    LegacyHistoricalRuntimeUnbound,
    install_historical_runtime,
)

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v3"


def load_current_study():
    spec = importlib.util.spec_from_file_location("s1_v2_execution_v3_current_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def study():
    spec = importlib.util.spec_from_file_location("s1_v2_execution_v3_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return install_historical_runtime(module)
    except LegacyHistoricalRuntimeUnbound as error:
        pytest.skip(str(error))


def test_current_checkout_fails_closed_before_historical_install():
    with pytest.raises(ValueError, match="Exact CWR source binding drifted"):
        load_current_study().validate_package()


def test_contract_truthfully_binds_execution_v2_no_go_lineage_and_freshness():
    module = study()
    assert module.contract() == module.expected_contract()
    assert module.contract()["predecessor"]["classification"] == "provider_free_no_go_template_reuse"
    assert module.contract()["geometry"] == {"independent_carriers": 4, "repeats_per_carrier": 3, "repeated_logical_samples": True, "opaque_slots": 12}
    bindings = json.loads((ROOT / "predecessor-bindings.json").read_text(encoding="utf-8"))
    assert bindings == module.V2_BINDINGS
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())
    assert all(value is False for value in module.contract()["freshness"].values())


def test_execution_v2_no_go_label_is_backed_by_its_two_template_collisions():
    module = study()
    execution_cases = {row["case_id"]: row["text"] for row in module._v2_execution().corpus()}
    prior_cases = {row["case_id"]: row["text"] for row in module._base_v2().corpus()}
    v1_cases = {row["case_id"]: row["text"] for row in module._base_v2()._v1().corpus()}

    item_place_line = re.compile(r"^Item: .+ / Place: .+$")
    assert all(item_place_line.fullmatch(line) for line in execution_cases["s1x-b782"].splitlines())
    assert all(item_place_line.fullmatch(line) for line in prior_cases["s1h-garnet"].splitlines())

    meta_refrain_signature = re.compile(r"\b(refrain)\b.*\b(only|one)\b.*\b(occurrence|instance)\b", re.IGNORECASE)
    assert meta_refrain_signature.search(execution_cases["s1x-e630"])
    assert meta_refrain_signature.search(v1_cases["s1h-drift"])


def test_four_selected_carriers_and_twelve_opaque_repeats_are_disjoint_and_motif_clean():
    module = study()
    slots, rows = module.slots(), module.corpus()
    previous_slots = [*module._base_v2()._v1().slots(), *module._base_v2().slots(), *module._v2_execution().slots()]
    assert len(rows) == len({row["case_id"] for row in rows}) == 4
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 12
    assert {(slot["case_id"], slot["repeat"]) for slot in slots} == {(row["case_id"], repeat) for row in rows for repeat in (1, 2, 3)}
    assert {slot["slot_id"] for slot in slots}.isdisjoint({slot["slot_id"] for slot in previous_slots})
    assert {slot["case_id"] for slot in slots}.isdisjoint({slot["case_id"] for slot in previous_slots})
    assert module.motif_template_audit()["status"] == "disjoint"


def test_dry_freeze_uses_raw_production_prompt_bytes_and_rejects_crlf_mutation(tmp_path: Path):
    module = study()
    module.set_work_root(tmp_path)
    result = module.dry_freeze()
    assert result["provider_calls"] == 0 and result["slots"] == 12
    root = module.dry_root()
    manifest = json.loads((root / "dry-manifest.v1.json").read_text(encoding="utf-8"))
    assert manifest["claim"] == "absent" and manifest["live_execution"] == "unavailable"
    assert len(manifest["commands"]) == 12
    assert not any((root / name).exists() for name in ("future-runs", "execution-claim.v1.json", "execution-terminal.v1.json", "settlement.v1.json"))
    for slot in module.slots():
        raw = (root / "frozen-prompts" / f"{slot['slot_id']}.prompt.txt").read_bytes()
        assert raw == module._render(slot, root).encode("utf-8")
        assert manifest["prompts"][slot["slot_id"]]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["prompts"]["u-5af1"]["crlf_pairs"] == 6
    source = (root / "frozen-prompts" / "u-5af1.prompt.txt").read_bytes()
    mutated = tmp_path / "text-mode-mutated.txt"
    mutated.write_text(source.decode("utf-8").replace("\r\n", "\n"), encoding="utf-8", newline="\r\n")
    assert mutated.read_bytes() != source
    checkpoint = tmp_path / "checkpoint.prompt.txt.gz"
    checkpoint.write_bytes(gzip.compress(source, mtime=0))
    assert module.validate_checkpoint_prompt("u-5af1", checkpoint)["sha256"] == hashlib.sha256(source).hexdigest()
    checkpoint.write_bytes(gzip.compress(mutated.read_bytes(), mtime=0))
    with pytest.raises(ValueError, match="raw prompt bytes"):
        module.validate_checkpoint_prompt("u-5af1", checkpoint)


def test_public_package_excludes_private_design_and_answer_material_and_execution():
    with pytest.raises(ValueError, match="provider execution"):
        study().execution_unavailable()
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    for forbidden in ("C:\\Users\\", "sealed-outcomes", "candidate-pool", "expected_states", "target_verdict", "--execute"):
        assert forbidden not in public
