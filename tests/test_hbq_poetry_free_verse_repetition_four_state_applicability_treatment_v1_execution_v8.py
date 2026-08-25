from __future__ import annotations

import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v8"
PRIVATE_ROOT_ENV = "CWR_S1_FOUR_STATE_V8_PRIVATE_ROOT"


def private_root() -> Path:
    value = os.environ.get(PRIVATE_ROOT_ENV)
    if not value:
        pytest.skip("private S1 v8 evidence root is not configured")
    return Path(value)


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v8_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_schema_subset_rejects_the_v6_string_type_omissions():
    module = study()
    schema = json.loads((ROOT / "exact-quote-response.schema.json").read_text(encoding="utf-8"))
    module.provider_schema_subset(schema)
    bad = deepcopy(schema)
    bad["properties"]["verdicts"]["items"]["properties"]["verdict"].pop("type")
    with pytest.raises(ValueError, match="enum"):
        module.provider_schema_subset(bad)
    bad = deepcopy(schema)
    bad["properties"]["verdicts"]["items"]["properties"]["evidence"]["items"]["properties"]["kind"].pop("type")
    with pytest.raises(ValueError, match="const"):
        module.provider_schema_subset(bad)


def test_contract_distinguishes_the_settled_v6_attempt_from_an_outer_settlement():
    outcome = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))["v6_consumed_outcome"]
    assert outcome["physical_attempts"] == outcome["provider_attempt_settlements"] == 1
    assert outcome["outer_dispatch_settlements"] == 0
    assert outcome["accepted"] == 0 and outcome["wording_inference"] == "forbidden"


def test_frozen_dry_root_binds_public_runtime_receipt_and_manifest_to_one_schema():
    module = study()
    root = private_root() / "execution-v8-preexecution-freeze-v1"
    manifest = json.loads((root / "study-manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "receipts" / "evidence-protocol-scan.v8.json").read_text(encoding="utf-8"))
    public = module.sha256_file(ROOT / "exact-quote-response.schema.json")
    assert receipt["schema_sha256"] == public
    assert manifest["generated_input_bindings"]["runtime-book-v3/schema/hbq_judge_response.schema.json"] == public
    assert (root / "runtime-book-v3" / "schema" / "hbq_judge_response.schema.json").read_bytes() == (ROOT / "exact-quote-response.schema.json").read_bytes()
