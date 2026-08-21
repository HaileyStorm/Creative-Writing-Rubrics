from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import gzip
from copy import deepcopy
import sys
import threading
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v3"


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    old = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules.update(aliases or {})
    try: spec.loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None: sys.modules.pop(key, None)
            else: sys.modules[key] = value
    return module


study = load("supplemental_hanna_v3_study", "study.py")
pilot = load("supplemental_hanna_v3_pilot", "run_transport_pilot.py", {"study": study})
verify = load("supplemental_hanna_v3_verify", "verify_transport_pilot.py", {"study": study})
enable = load("supplemental_hanna_v3_enable", "enable_development.py", {"study": study, "verify_transport_pilot": verify})
development = load("supplemental_hanna_v3_development", "run_development.py", {"study": study, "enable_development": enable})


def frozen() -> dict:
    return {"cells": [{"cell_id": f"pilot-{n:02d}", "item_id": f"item-{n}", "inputs": {}, "question_ids": [str(i) for i in range(8)]} for n in range(1, 4)]}


def test_contract_is_batch_8_sequential_and_closes_after_failure():
    policy = study.CONTRACT["transport_pilot"]
    assert {key: policy[key] for key in ("cells", "batch_size", "question_count", "batch_attempts", "workers")} == {"cells": 3, "batch_size": 8, "question_count": 8, "batch_attempts": 1, "workers": 1}
    text = (ROOT / "study-contract.json").read_text(encoding="utf-8")
    assert "No automatic size step" in text and "Nous Pro" in text and "DSPy" in text
    assert study.CONTRACT["development"]["comparison_status"] == "unmatched_to_primary_32_and_v2_16"


def test_failed_v2_predecessor_commitments_are_exact_and_tamper_fails(monkeypatch, tmp_path):
    configured = os.environ.get("CWR_FAILED_V2_ROOT")
    if not configured:
        pytest.skip("set CWR_FAILED_V2_ROOT to check the external predecessor commitments")
    root = Path(configured)
    observed = study.failed_v2_commitments(root)
    assert observed["commitments"]["pilot-journal/0001-pilot-01.json"]["sha256"] == study.CONTRACT["failed_v2"]["commitments"]["pilot-journal/0001-pilot-01.json"]["sha256"]
    assert observed["raw_evidence_tree"]["files"] == 7
    with pytest.raises(ValueError, match="drifted"):
        study.failed_v2_commitments(tmp_path)


def test_real_failed_v2_root_can_prepare_a_v3_freeze(tmp_path):
    configured = os.environ.get("CWR_FAILED_V2_ROOT")
    if not configured:
        pytest.skip("set CWR_FAILED_V2_ROOT to run the external failed-root preparation regression")
    root = Path(configured)
    frozen = study.freeze_work(root, tmp_path)
    assert [cell["question_ids"] for cell in frozen["cells"]] == [frozen["cells"][0]["question_ids"]] * 3
    assert len(frozen["cells"][0]["question_ids"]) == 8
    assert study.load_frozen(tmp_path) == frozen


@pytest.mark.parametrize("kind", ["item", "questions", "selection", "inputs"])
def test_load_frozen_rejects_coherent_selection_or_input_tamper(tmp_path, kind):
    configured = os.environ.get("CWR_FAILED_V2_ROOT")
    if not configured:
        pytest.skip("set CWR_FAILED_V2_ROOT to run the external frozen-selection regression")
    frozen = study.freeze_work(Path(configured), tmp_path)
    forged = deepcopy(frozen)
    if kind == "item":
        forged["cells"][1]["item_id"] = forged["cells"][0]["item_id"]
    elif kind == "questions":
        forged["cells"][0]["question_ids"] = list(reversed(forged["cells"][0]["question_ids"]))
    elif kind == "selection":
        forged["cells"][0]["selection"] = {"forged": True}
    else:
        forged["cells"][0]["inputs"]["source.md"]["sha256"] = "0" * 64
    (tmp_path / "frozen-transport-contract.json").write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(ValueError, match="selection/questions/inputs"):
        study.load_frozen(tmp_path)


def test_parent_package_hash_tamper_fails_closed(monkeypatch):
    changed = dict(study.CONTRACT); changed["parent_v2"] = {**changed["parent_v2"], "files": {**changed["parent_v2"]["files"], "study.py": "0" * 64}}
    monkeypatch.setattr(study, "CONTRACT", changed)
    with pytest.raises(ValueError, match="v2 parent file drifted"):
        study._parent_v2()


def test_timeout_rejected_before_any_provider_work(tmp_path):
    with pytest.raises(ValueError, match="timeout 600"):
        pilot.execute(tmp_path, timeout=599)
    assert not (tmp_path / "runs").exists()


def test_failure_is_journaled_once_and_permanently_closes_root(monkeypatch, tmp_path):
    (tmp_path / "frozen-transport-contract.json").write_text("{}", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {})
    monkeypatch.setattr(pilot, "_execute_one", lambda *_: calls.append("sent") or (_ for _ in ()).throw(RuntimeError("HTTP 524")))
    with pytest.raises(RuntimeError, match="524"):
        pilot.execute(tmp_path)
    assert calls == ["sent"]
    with pytest.raises(ValueError, match="no further automatic successor"):
        pilot.execute(tmp_path)
    assert calls == ["sent"]


def test_exclusive_claim_blocks_racing_processes(monkeypatch, tmp_path):
    (tmp_path / "frozen-transport-contract.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    gate = threading.Barrier(2); outcome: list[str] = []
    def claim():
        gate.wait()
        try: pilot._claim(tmp_path); outcome.append("claimed")
        except ValueError: outcome.append("blocked")
    left, right = threading.Thread(target=claim), threading.Thread(target=claim); left.start(); right.start(); left.join(); right.join()
    assert sorted(outcome) == ["blocked", "claimed"]


def test_journal_rejects_duplicate_and_torn_records(tmp_path):
    pilot._append_journal(tmp_path, {"cell_id": "pilot-01", "status": "completed"})
    with pytest.raises(ValueError, match="already"):
        pilot._append_journal(tmp_path, {"cell_id": "pilot-01", "status": "completed"})
    (tmp_path / "pilot-journal" / "0002-pilot-02.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        pilot._journal_records(tmp_path)


def test_import_order_does_not_leave_generic_study_alias():
    before = sys.modules.get("study")
    parent = study._parent_v2()
    assert parent.CONTRACT["study_id"] == "hbq-human-alignment-supplemental-providers-v2"
    assert sys.modules.get("study") is before


def test_verifier_rejects_missing_three_and_duration_boundary(monkeypatch, tmp_path):
    journal = tmp_path / "pilot-journal"; journal.mkdir()
    (journal / "0001-pilot-01.json").write_text(json.dumps({"sequence": 1, "cell_id": "pilot-01", "status": "completed"}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(verify, "_invocation", lambda _: {})
    monkeypatch.setattr(verify, "_claim", lambda _: {})
    with pytest.raises(ValueError, match="exactly three"):
        verify.verify_pilot(tmp_path)
    assert verify._timely(99.999) and not verify._timely(100) and not verify._timely(True)


def test_verifier_rejects_reused_sessions(monkeypatch, tmp_path):
    paths = tmp_path / "pilot-journal"; paths.mkdir()
    value = frozen()
    receipts = [{"cell_id": cell["cell_id"], "raw_transport": {"evidence": {"run_id": "same"}}} for cell in value["cells"]]
    for n, receipt in enumerate(receipts, 1):
        (paths / f"{n:04d}-{receipt['cell_id']}.json").write_text(json.dumps({"sequence": n, "cell_id": receipt["cell_id"], "status": "completed"}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: value); monkeypatch.setattr(verify, "_invocation", lambda _: {}); monkeypatch.setattr(verify, "_claim", lambda _: {})
    monkeypatch.setattr(verify, "_verify_cell", lambda _w, _f, cell: next(item for item in receipts if item["cell_id"] == cell["cell_id"]))
    with pytest.raises(ValueError, match="reused"):
        verify.verify_pilot(tmp_path)


def test_raw_verifier_composes_hash_pinned_v2_and_has_no_score_surface():
    text = (ROOT / "verify_transport_pilot.py").read_text(encoding="utf-8")
    assert "_parent_v2" in text and "score.json" not in text and "HANNA ratings" not in text


def test_verifier_rejects_coherent_wrong_persisted_prompt_before_raw_validation(monkeypatch, tmp_path):
    run = tmp_path / "runs" / "pilot" / "pilot-01"; responses = run / "responses"; responses.mkdir(parents=True)
    source = {"name": "source.md", "bytes": 1, "sha256": "a"}; context = {"name": "prompt.md", "bytes": 1, "sha256": "b"}; task = {"name": "task-contract.json", "bytes": 1, "sha256": "c"}
    cell = {"cell_id": "pilot-01", "item_id": "item-1", "inputs": {"source.md": source, "prompt.md": context, "task-contract.json": task}, "question_ids": [str(i) for i in range(8)]}
    config = {"provider": "nous", "model": study.CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 8, "retry_policy": {"batch_attempts": 1}, "artifact_id": "item-1", "bundle_id": "prose.short_story", "question_ids": cell["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True, "artifact": source, "contexts": [context], "task_contract": task}
    (run / "run.json").write_text(json.dumps({"format_version": 3, "configuration": config, "config_sha256": hashlib.sha256(verify._json_bytes(config)).hexdigest()}), encoding="utf-8")
    wrong = b"coherent but wrong prompt"
    checkpoint = {"format_version": 4, "batch": 1, "question_ids": cell["question_ids"], "retry_policy": {"batch_attempts": 1}, "base_prompt_sha256": hashlib.sha256(wrong).hexdigest(), "prompt_sha256": hashlib.sha256(wrong).hexdigest(), "provider": {"synthetic": "HMAC-valid-in-the-later-raw-gate"}}
    (responses / "batch-0001.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (responses / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(wrong))
    receipt = tmp_path / "pilot-receipts"; receipt.mkdir(); (receipt / "pilot-01.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(verify, "input_folder", lambda *_: tmp_path)
    monkeypatch.setattr(verify, "_expected_prompt", lambda *_: b"the frozen canonical prompt")
    monkeypatch.setattr(verify, "_raw_transport", lambda *_: pytest.fail("raw evidence must not rescue a wrong prompt"))
    with pytest.raises(ValueError, match="does not reconstruct"):
        verify._verify_cell(tmp_path, {"cells": [cell]}, cell)


def test_enablement_and_development_cannot_cross_pilot_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(enable, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(enable, "verify_pilot", lambda _: (_ for _ in ()).throw(ValueError("pilot failed")))
    with pytest.raises(ValueError, match="pilot failed"):
        enable.enable(tmp_path)
    monkeypatch.setattr(development, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(development, "enable", lambda _: (_ for _ in ()).throw(ValueError("pilot not verified")))
    monkeypatch.setattr(development, "run_judge", lambda **_: pytest.fail("development must not send"))
    with pytest.raises(ValueError, match="pilot not verified"):
        development.execute(tmp_path)


def test_development_claim_allows_one_launcher_and_pins_one_attempt(tmp_path):
    (tmp_path / "development-invocation.json").write_text("{}", encoding="utf-8")
    gate = threading.Barrier(2); outcome: list[str] = []
    def claim():
        gate.wait()
        try: development._claim(tmp_path); outcome.append("claimed")
        except ValueError: outcome.append("blocked")
    left, right = threading.Thread(target=claim), threading.Thread(target=claim); left.start(); right.start(); left.join(); right.join()
    assert sorted(outcome) == ["blocked", "claimed"]
    text = (ROOT / "run_development.py").read_text(encoding="utf-8")
    assert '"batch_attempts": 1' in text and "development-journal" in text


def test_invocation_pins_runner_and_verifier(monkeypatch, tmp_path):
    (tmp_path / "frozen-transport-contract.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    record = pilot._invocation(tmp_path, frozen(), 600)
    assert record["study"] == study.fingerprint(ROOT / "study.py")
    forged = {**record, "pilot_verifier": {**record["pilot_verifier"], "sha256": "0" * 64}}
    with pytest.raises(ValueError, match="Immutable"):
        study.immutable_json(tmp_path / "pilot-invocation.json", forged)


def test_contract_parent_hashes_match_current_bytes():
    for name, digest in study.CONTRACT["parent_v2"]["files"].items():
        assert hashlib.sha256((study.PARENT_ROOT / name).read_bytes()).hexdigest() == digest
