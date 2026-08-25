from __future__ import annotations
import importlib.util,json,sys
from copy import deepcopy
from pathlib import Path
import pytest
from hbqrs.paths import book_root
ROOT=book_root()/"evaluation-results"/"hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v7"
def study():
 s=importlib.util.spec_from_file_location("s1v7test",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_provider_schema_subset_requires_type_for_string_const_and_enum():
 m=study();schema=json.loads((ROOT/"exact-quote-response.schema.json").read_text());m.provider_schema_subset(schema)
 bad=deepcopy(schema);bad["properties"]["verdicts"]["items"]["properties"]["verdict"].pop("type")
 with pytest.raises(ValueError,match="enum"):m.provider_schema_subset(bad)
 bad=deepcopy(schema);bad["properties"]["verdicts"]["items"]["properties"]["evidence"]["items"]["properties"]["kind"].pop("type")
 with pytest.raises(ValueError,match="const"):m.provider_schema_subset(bad)
def test_v7_contract_records_v6_schema_no_result_without_wording_inference():
 x=json.loads((ROOT/"study-contract.json").read_text());o=x["v6_consumed_outcome"]
 assert (o["physical_attempts"],o["accepted"],o["untouched_slots"],o["formal_result"],o["wording_inference"])==(1,0,11,"NO_RESULT","forbidden")
 assert x["provider_schema_subset_gate"]["checked_before_claim"] is True
