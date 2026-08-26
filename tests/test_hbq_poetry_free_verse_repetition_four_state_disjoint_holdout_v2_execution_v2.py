from __future__ import annotations

import gzip
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

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v2"


def load_current_study():
    spec = importlib.util.spec_from_file_location("s1_v2_execution_v2_current_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def study():
    spec = importlib.util.spec_from_file_location("s1_v2_execution_v2_test", ROOT / "study.py")
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


def test_contract_classifies_the_predecessor_as_one_contact_non_voting_no_result():
    module = study()
    assert module.contract() == module.expected_contract()
    predecessor = module.contract()["predecessor"]
    assert predecessor["classification"] == "NO_RESULT_PROMPT_BYTE_BINDING_FAILURE"
    assert predecessor["contacts"] == 1
    assert predecessor["completed_slots"] == 0
    assert predecessor["untouched_slots"] == 11
    assert predecessor["semantic_output"] == "non_voting"
    bindings = json.loads((ROOT / "predecessor-bindings.json").read_text(encoding="utf-8"))
    assert bindings == module.PREDECESSOR
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_fresh_schedule_has_no_predecessor_slots_or_logical_samples():
    module = study()
    slots = module.slots()
    predecessor = module._v2().slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 12
    assert {(slot["case_id"], slot["repeat"]) for slot in slots} == {(row["case_id"], repeat) for row in module.corpus() for repeat in (1, 2, 3)}
    assert {slot["slot_id"] for slot in slots}.isdisjoint({slot["slot_id"] for slot in predecessor})
    assert {slot["case_id"] for slot in slots}.isdisjoint({slot["case_id"] for slot in predecessor})


def test_dry_freeze_writes_exact_runner_prompt_bytes_and_rejects_crlf_mutation(tmp_path: Path):
    module = study()
    module.set_work_root(tmp_path)
    result = module.dry_freeze()
    assert result["provider_calls"] == 0 and result["slots"] == 12
    root = module.dry_root()
    manifest = json.loads((root / "dry-manifest.v1.json").read_text(encoding="utf-8"))
    assert manifest["claim"] == "absent" and manifest["live_execution"] == "unavailable"
    assert not any((root / name).exists() for name in ("future-runs", "execution-claim.v1.json", "execution-terminal.v1.json", "settlement.v1.json"))
    assert len(manifest["commands"]) == 12
    assert all("--resume" not in command and command[command.index("--batch-attempts") + 1] == "1" for command in manifest["commands"].values())
    for slot in module.slots():
        slot_id = slot["slot_id"]
        frozen = (root / "frozen-prompts" / f"{slot_id}.prompt.txt").read_bytes()
        assert frozen == module._render(slot, root).encode("utf-8")
        assert manifest["prompts"][slot_id]["sha256"] == __import__("hashlib").sha256(frozen).hexdigest()
    assert manifest["prompts"]["r-5af1"]["crlf_pairs"] == 6
    source = (root / "frozen-prompts" / f"{module.slots()[0]['slot_id']}.prompt.txt").read_bytes()
    mutated = tmp_path / "text-mode-mutated.txt"
    mutated.write_text(source.decode("utf-8").replace("\r\n", "\n"), encoding="utf-8", newline="\r\n")
    assert mutated.read_bytes() != source
    checkpoint = tmp_path / "checkpoint.prompt.txt.gz"
    checkpoint.write_bytes(gzip.compress(source, mtime=0))
    assert module.validate_checkpoint_prompt(module.slots()[0]["slot_id"], checkpoint)["sha256"] == __import__("hashlib").sha256(source).hexdigest()
    checkpoint.write_bytes(gzip.compress(mutated.read_bytes(), mtime=0))
    with pytest.raises(ValueError, match="raw prompt bytes"):
        module.validate_checkpoint_prompt(module.slots()[0]["slot_id"], checkpoint)


def test_provider_execution_and_claim_are_unavailable():
    with pytest.raises(ValueError, match="provider execution"):
        study().execution_unavailable()
    assert "--execute" not in (ROOT / "run.py").read_text(encoding="utf-8")


def test_public_package_excludes_private_paths_and_outcome_material():
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    for forbidden in ("C:\\Users\\", "sealed-outcomes", "expected_states", "target_verdict"):
        assert forbidden not in public
