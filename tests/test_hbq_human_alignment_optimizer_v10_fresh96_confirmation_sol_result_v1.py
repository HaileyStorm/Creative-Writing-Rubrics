from __future__ import annotations

import importlib.util
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-result-v1"


def module():
    spec = importlib.util.spec_from_file_location("v10_sol_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_public_result_is_sol_only_and_aggregate_only():
    value = json.loads((PACKAGE / "result.json").read_bytes())
    assert value["geometry"] == {"cells": 64, "dimensions": 6, "groups": 16, "items": 32}
    assert value["native_endpoint_contact_cardinality"] == "unproven"
    assert value["endpoint"] == "sol_later"
    assert value["judge"] == {"provider_attested": False, "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high"}
    assert value["authority"] == {
        "confirmation": "measurement_only",
        "endpoint_pooling": "forbidden",
        "generalization": "none",
        "promotion": "none",
        "runtime": "none",
        "selection": "none",
        "sol": "measurement_only",
    }
    assert value["replay"] == {
        "historical_process_launches": 64,
        "no_resend": True,
        "normal_receipt_cells": 63,
        "process_launches": 0,
        "provider_calls_made": None,
        "reconciled_terminal_cells": 1,
    }
    assert value["coverage"] == {
        "baseline": {"groups": 16, "items": 32, "score_dimensions_covered": 191, "score_dimensions_total": 192},
        "child20": {"groups": 16, "items": 32, "score_dimensions_covered": 192, "score_dimensions_total": 192},
    }
    text = (PACKAGE / "result.json").read_text()
    assert "prompt-" not in text and "session_id" not in text and "native_response" not in text


def test_external_replay_is_opt_in():
    output_root = os.getenv("CWR_V10_SOL_R1_ROOT")
    freeze_root = os.getenv("CWR_V10_FREEZE_ROOT")
    collector = os.getenv("CWR_V10_SOL_COLLECTOR")
    if not all((output_root, freeze_root, collector)):
        pytest.skip("external immutable V10 Sol evidence not supplied")
    observed = module().verify(output_root=Path(output_root), freeze_root=Path(freeze_root), collector_path=Path(collector))
    assert observed["comparison"]["wins_ties_losses"] == {"child20": 15, "ties": 0, "losses": 1}


def test_verifier_rejects_static_claim_and_unknown_field_mutations(monkeypatch, tmp_path):
    verifier = module()
    published = json.loads((PACKAGE / "result.json").read_bytes())
    observed = {key: published[key] for key in ("comparison", "coverage", "endpoint", "judge", "metrics", "replay", "source")}
    result = tmp_path / "result.json"
    monkeypatch.setattr(verifier, "RESULT", result)
    monkeypatch.setattr(verifier, "recompute", lambda **_kwargs: observed)
    result.write_bytes(verifier.canonical(published))
    assert verifier.verify() == observed
    mutations = (
        lambda value: value.__setitem__("unexpected_private_field", True),
        lambda value: value["authority"].__setitem__("promotion", "allowed"),
        lambda value: value["geometry"].__setitem__("cells", 63),
        lambda value: value.__setitem__("endpoint", "grok_primary"),
        lambda value: value["judge"].__setitem__("provider_attested", True),
        lambda value: value.__setitem__("kind", "promotion_result"),
        lambda value: value.__setitem__("native_endpoint_contact_cardinality", "proven"),
        lambda value: value["source"].__setitem__("collector_sha256", "0" * 64),
        lambda value: value["source"].__setitem__("executor_sha256", "0" * 64),
        lambda value: value.__setitem__("study_id", "different-study"),
    )
    for mutate in mutations:
        candidate = deepcopy(published)
        mutate(candidate)
        result.write_bytes(verifier.canonical(candidate))
        with pytest.raises(ValueError, match="envelope"):
            verifier.verify()
