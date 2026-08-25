from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import pytest
from hbqrs.paths import book_root
ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v6"
def study():
    spec=importlib.util.spec_from_file_location("s1_four_state_v6_test",ROOT / "study.py"); module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name]=module; spec.loader.exec_module(module); return module
def test_absence_control_is_one_independent_clause_without_recurrence():
    value=study(); value.one_independent_clause_recurrence_free("Limestone fog crossed a harbor.")
    with pytest.raises(ValueError,match="independent clause"):
        value.one_independent_clause_recurrence_free("Gulls wheel, shutters rattle, dusk arrives.")
    with pytest.raises(ValueError,match="independent clause"):
        value.one_independent_clause_recurrence_free("Gulls wheel and shutters rattle.")
    with pytest.raises(ValueError,match="lexical token"):
        value.one_independent_clause_recurrence_free("The lantern shook while the harbor slept.")
def test_v6_contract_binds_v5_and_preserves_the_exact_quote_four_state_gates():
    value=json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert value["v5_provider_free_predecessor"]["provider_calls"] == 0
    assert value["evidence_protocol"]["kind"] == "exact_quote_only"
    assert value["geometry"] == {"cells":4,"states":["NOT_APPLICABLE","NO","YES","CANNOT_ASSESS"],"arms":["candidate"],"repeats":3,"slots":12,"one_leaf_per_call":True,"fresh_private_prose":True}
    assert value["absence_construct_gate"]["exactly_one_independent_clause"] is True
