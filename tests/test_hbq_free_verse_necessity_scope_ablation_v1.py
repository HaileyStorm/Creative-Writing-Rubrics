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


ROOT = book_root() / "evaluation-results" / "hbq-free-verse-necessity-scope-ablation-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("free_verse_necessity_scope_ablation", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_freeze_binds_exact_parent_and_zero_call_singleton_geometry():
    study = load_study()
    assert study.verify_package() == {
        "study_id": "hbq-free-verse-necessity-scope-ablation-v1",
        "status": "frozen_provider_free_paired_scope_evidence_ablation",
        "provider_calls": 0,
        "conditions": 6,
        "slots": 36,
    }
    assert study.PINNED_COMMIT == "4ce1204d8dd97feff2c7bd88237e265fac742adb"
    slots = study.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 36
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["leaf_id"] for slot in slots} == set(study.LEAVES)
    assert {slot["expected_verdict"] for slot in slots} == study.VERDICTS
    assert {(slot["case_id"], slot["leaf_id"], slot["repeat"]) for slot in slots} == {(case_id, leaf_id, repeat) for case_id in study.EXPECTED for leaf_id in study.LEAVES for repeat in range(1, 4)}
    assert study.load_contract()["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}


def test_original_public_fixtures_cover_lineation_scope_and_all_four_states():
    study = load_study()
    corpus = study.load_corpus()
    cases = {case["case_id"]: case for case in corpus["cases"]}
    assert tuple(corpus["leaves"]) == study.LEAVES
    assert [case["source_fixture_id"] for case in corpus["cases"]] == ["new-v1-complete-necessary", "artifact-03.txt", "new-v1-complete-necessary#lines-1-5", "artifact-01.txt#line-3", "artifact-05.txt", "artifact-06.txt"]
    assert tuple(cases["complete-necessary"]["expected"]) == ("YES", "YES")
    assert tuple(cases["complete-arbitrary"]["expected"]) == ("NO", "YES")
    assert tuple(cases["stanza-excerpt"]["expected"]) == ("YES", "NOT_APPLICABLE")
    assert tuple(cases["line-excerpt"]["expected"]) == ("CANNOT_ASSESS", "NOT_APPLICABLE")
    assert tuple(cases["missing-poem-coverage"]["expected"]) == ("CANNOT_ASSESS", "CANNOT_ASSESS")
    assert tuple(cases["inactive-metadata-control"]["expected"]) == ("NOT_APPLICABLE", "NOT_APPLICABLE")
    assert {state for case in cases.values() for state in case["expected"]} == study.VERDICTS
    assert cases["stanza-excerpt"]["declared_scope"] == "stanza"
    assert cases["line-excerpt"]["declared_scope"] == "line"
    assert cases["missing-poem-coverage"]["completion_status"] == "unknown"
    assert cases["complete-arbitrary"]["lineage_expected"] == ["NO", "YES"]
    assert cases["complete-arbitrary"]["text"] == study.predecessor_fixtures()["artifact-03.txt"]["text"]
    assert cases["stanza-excerpt"]["text"] == "\n".join(cases["complete-necessary"]["text"].splitlines()[:5])


def test_production_rendering_is_single_leaf_and_keeps_expected_ledger_out_of_prompts():
    study = load_study()
    requests = study.render_all_provider_inputs()
    assert len(requests) == 36
    rendered = "\n".join(request["prompt"] for request in requests.values())
    assert study.FINDING_ID not in rendered
    assert "expected_verdict" not in rendered and "source_fixture_id" not in rendered and "oracle" not in rendered
    for slot in study.plan_slots():
        request = requests[slot["slot_id"]]
        assert request["leaf_id"] == slot["leaf_id"]
        assert request["prompt"].count(slot["leaf_id"]) >= 1
    form = study.production_question("form.poetry.free_verse.necessity")
    scope = study.production_question("scope.poetry_poem.form")
    assert form["role"] == "direct_only_form_leaf" and form["domain_id"] == "form"
    assert scope["role"] == "direct_only_scope_overlay" and scope["domain_id"] == "scope.poetry_poem"
    assert all(item["question"]["applies_when"] == "The criterion is relevant to the requested artifact, scope, and operation." for item in (form, scope))


def test_scope_oracle_and_bindings_fail_closed_on_drift(monkeypatch):
    study = load_study()
    corpus = deepcopy(study.load_corpus())
    corpus["cases"][2]["expected"] = ["YES", "YES"]
    with pytest.raises(ValueError, match="Four-state"):
        study.verify_corpus(corpus)
    contract = deepcopy(study.load_contract())
    contract["scope_rule"]["ordinary_bundle_activation_claimed"] = True
    monkeypatch.setattr(study, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Scope ablation"):
        study.verify_package()


def test_bound_runtime_and_predecessor_bytes_match_exact_pinned_git_parent():
    study = load_study()
    contract = study.load_contract()
    study.verify_bound_paths_unchanged((*study.RUNTIME_PATHS, contract["bindings"]["source_fixture"]["path"]))
    for path, digest in contract["bindings"]["runtime"].items():
        frozen = study.git_show_bytes(path)
        assert hashlib.sha256(frozen).hexdigest() == digest
    fixture = contract["bindings"]["source_fixture"]
    assert hashlib.sha256(study.git_show_bytes(fixture["path"])).hexdigest() == fixture["git_object_sha256"]
    assert study.predecessor_fixtures()["artifact-01.txt"]["text"].splitlines()[2] == study.materialize_artifacts()["line-excerpt"]["text"]


def test_provider_free_commands_have_no_execution_surface():
    verified = subprocess.run([sys.executable, str(ROOT / "run.py"), "--verify"], text=True, capture_output=True, check=True)
    plan = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(verified.stdout)["verification"]["provider_calls"] == 0
    assert len(json.loads(plan.stdout)["rendered_slots"]) == 36
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "import dspy" not in text and "from dspy" not in text
        assert "import requests" not in text and "from requests" not in text
        assert "--execute" not in text
