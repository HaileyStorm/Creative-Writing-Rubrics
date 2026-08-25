from __future__ import annotations

import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v9"
PRIVATE_ROOT_ENV = "CWR_S1_FOUR_STATE_V9_PRIVATE_ROOT"


def private_root() -> Path:
    value = os.environ.get(PRIVATE_ROOT_ENV)
    if not value:
        pytest.skip("private S1 v9 evidence root is not configured")
    return Path(value)


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v9_test", ROOT / "study.py")
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
    root = private_root() / "execution-v9-preexecution-freeze-v1"
    manifest = json.loads((root / "study-manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "receipts" / "evidence-protocol-scan.v9.json").read_text(encoding="utf-8"))
    public = module.sha256_file(ROOT / "exact-quote-response.schema.json")
    assert receipt["schema_sha256"] == public
    assert manifest["generated_input_bindings"]["runtime-book-v3/schema/hbq_judge_response.schema.json"] == public
    assert (root / "runtime-book-v3" / "schema" / "hbq_judge_response.schema.json").read_bytes() == (ROOT / "exact-quote-response.schema.json").read_bytes()


def test_prompt_is_byte_identical_to_v7_and_declared_across_the_frozen_dry_root():
    module = study()
    v7 = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v7" / "exact-quote-binary-prompt.md"
    assert (ROOT / "exact-quote-binary-prompt.md").read_bytes() == v7.read_bytes()
    assert len(v7.read_bytes()) == 1267
    root = private_root() / "execution-v9-preexecution-freeze-v1"
    manifest = json.loads((root / "study-manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "receipts" / "evidence-protocol-scan.v9.json").read_text(encoding="utf-8"))
    assert module.PROMPT_SHA256 == "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
    assert module.sha256_file(ROOT / "exact-quote-binary-prompt.md") == module.PROMPT_SHA256
    assert module.sha256_file(root / "runtime-book-v3" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md") == module.PROMPT_SHA256
    assert manifest["generated_input_bindings"]["runtime-book-v3/prompts/judge/BINARY_EVALUATION_PROMPT.md"] == module.PROMPT_SHA256
    assert receipt["prompt_sha256"] == receipt["binary_prompt_sha256"] == module.PROMPT_SHA256
