from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-scope-dspy-successor-v2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    return module


def study():
    return load_module("dspy_successor_v2_study", ROOT / "study.py")


def read_json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_settled_contract_and_aggregate_only_result_are_pinned():
    s = study()
    contract = read_json("study-contract.json")
    result = read_json("public-result.json")
    assert contract["status"] == "SETTLED_INCOMPLETE_NO_PROMOTION"
    assert contract["result_lineage"] == {
        "execution_commit": "7febc77483f674a929d1778b7285a3a02c4d3a5a",
        "private_aggregate_sha256": "49052db5d5684be418d1b5c563615b206a31a97459189cf3b5436ccdaa363126",
        "private_result_sha256": "67bb8bbecf7abbbaf84fac5c94a583e1e87f7b4a692ee8c27291aa73ef258b61",
    }
    assert hashlib.sha256((ROOT / "public-result.json").read_bytes()).hexdigest() == contract["public_result_sha256"]
    assert result["status"] == "INCOMPLETE"
    assert result["decision"] == "NO_PROMOTION"
    assert result["execution"] == {
        "logical_train_calls": 2,
        "accepted_grounded_scored_misses": 1,
        "terminal_schema_or_quote_failures": 1,
        "retries": 0,
        "selection_accessed": False,
        "selection_read": False,
        "confirmation_accessed": False,
    }
    assert result["scored_miss"] == {"expected": "YES", "observed": "NO"}
    assert result["terminal_failure"] == {
        "reason": "schema_or_quote_failure",
        "cause": "v2_validator_rejected_schema_valid_mixed_exact_quote_and_summary_response",
    }
    assert s.verify_package()["provider_calls"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["candidate_commitments"][0].update({"sha256": "0" * 64}),
        lambda value: value["gates"].update({"both_candidates_must_pass_composite_train": False}),
        lambda value: value.update({"allowed_terminal_statuses": []}),
        lambda value: value.update({"forbidden": []}),
    ],
)
def test_retained_freeze_contract_mutations_fail_closed(monkeypatch, mutation):
    s = study()
    changed = deepcopy(read_json("study-contract.json"))
    mutation(changed)
    monkeypatch.setattr(s, "load_json", lambda name: changed if name == "study-contract.json" else read_json(name))
    with pytest.raises(ValueError, match="freeze contract"):
        s.verify_package()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["execution"].__setitem__("retries", 1),
        lambda value: value["execution"].__setitem__("selection_read", True),
        lambda value: value.__setitem__("decision", "NO_GO"),
        lambda value: value["scored_miss"].__setitem__("observed", "YES"),
        lambda value: value["terminal_failure"].__setitem__("reason", "retry"),
    ],
)
def test_public_result_mutations_fail_closed(monkeypatch, mutation):
    s = study()
    changed = deepcopy(read_json("public-result.json"))
    mutation(changed)
    monkeypatch.setattr(s, "load_json", lambda name: changed if name == "public-result.json" else read_json(name))
    with pytest.raises(ValueError):
        s.validate_public_result()


@pytest.mark.parametrize(
    "key,value",
    [
        ("raw_response", "hidden"),
        ("session_id", "hidden"),
        ("artifact_path", "hidden"),
        ("candidate_text", "hidden"),
    ],
)
def test_private_material_additions_fail_closed(monkeypatch, key, value):
    s = study()
    changed = deepcopy(read_json("public-result.json"))
    changed[key] = value
    monkeypatch.setattr(s, "load_json", lambda name: changed if name == "public-result.json" else read_json(name))
    with pytest.raises(ValueError):
        s.validate_public_result()


def test_dry_run_is_provider_free_and_execute_is_refused():
    dry_run = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--dry-run"],
        text=True,
        capture_output=True,
        check=True,
    )
    value = json.loads(dry_run.stdout)
    assert value["mode"] == "dry_run"
    assert value["verification"]["provider_calls"] == 0
    assert value["verification"]["execution_refused"] is True
    execute = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--execute"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert execute.returncode != 0
    assert "settled INCOMPLETE" in execute.stderr


def test_public_package_has_no_private_content_or_runtime_dependency():
    forbidden_content = (
        "default-one-charged", "default-three-charged", "specific-three-routine",
        "Grief was thunder", "Nets breathed on pegs", "Mara's world shattered",
    )
    for path in ROOT.iterdir():
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in forbidden_content)
        assert "import dspy" not in text and "from dspy" not in text
        assert "C:\\Users\\" not in text and "C:/Users/" not in text
