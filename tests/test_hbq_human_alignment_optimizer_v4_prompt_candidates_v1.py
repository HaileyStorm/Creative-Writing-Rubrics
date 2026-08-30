from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-prompt-candidates-v1"


def _load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _instruction(candidate: dict, luna: dict) -> str:
    instruction = candidate["instruction"]
    assert instruction["common_prefix_ref"] == "luna-source.json#/common_prefix"
    if "delta_ref" in instruction:
        index = int(instruction["delta_ref"].split("/")[2])
        return luna["common_prefix"] + "\n\n" + luna["candidates"][index]["delta"]
    return luna["common_prefix"] + "\n\n" + instruction["local_delta"]


def test_catalog_binds_exact_raw_inputs_and_keeps_all_sixteen_sources() -> None:
    catalog = _load("catalog.json")
    luna = _load("luna-source.json")
    nous = _load("nous-result.json")
    request = _load("nous-request.json")

    bindings = catalog["raw_input_bindings"]
    assert bindings["nous_request"]["sha256"] == _sha(PACKAGE / "nous-request.json")
    assert bindings["nous_result"]["sha256"] == _sha(PACKAGE / "nous-result.json")
    assert bindings["luna_source"]["sha256"] == _sha(PACKAGE / "luna-source.json")
    assert len(luna["candidates"]) == 8
    assert len(nous["result"]["candidate_prompts"]) == 8
    assert request["model"] == nous["metadata"]["requested_model"]
    assert catalog["source_inventory"]["deepseek"]["exact_gate_eligible"] is False
    assert catalog["source_inventory"]["deepseek"]["exact_gate_blockers"] == nous["metadata"]["exact_gate_blockers"]
    assert "PENDING" not in (PACKAGE / "catalog.json").read_text(encoding="utf-8")


def test_shortlist_is_unique_public_safe_and_has_no_runtime_authority() -> None:
    catalog = _load("catalog.json")
    luna = _load("luna-source.json")
    nous = _load("nous-result.json")
    shortlist = catalog["shortlist"]

    assert len(shortlist) == 12
    assert len({candidate["candidate_id"] for candidate in shortlist}) == len(shortlist)
    assert len({candidate["mechanical_class"] for candidate in shortlist}) == len(shortlist)
    assert catalog["authority"] == {
        "runtime": "none",
        "selection": "none",
        "confirmation": "unopened",
        "empirical_claim": "none",
    }
    for index, candidate in enumerate(shortlist):
        rendered = _instruction(candidate, luna)
        assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == candidate["instruction_sha256"]
        assert "\n" in rendered and "story text" not in rendered.lower()
        source = candidate["source"]
        if index < 8:
            assert source["derivation"] == "verbatim_luna"
            assert rendered.endswith(luna["candidates"][index]["delta"])
        else:
            assert source["derivation"] == "new_local_descendant_rewrite"
            raw = nous["result"]["candidate_prompts"][source["source_candidate_index"]]
            assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == source["source_prompt_sha256"]
            assert rendered != raw
