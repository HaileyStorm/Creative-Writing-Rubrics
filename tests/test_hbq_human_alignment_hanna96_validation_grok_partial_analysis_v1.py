from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-grok-partial-analysis-v1"
LIVE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna96-validation-grok-c280729-20260831a")


def module():
    spec = importlib.util.spec_from_file_location("_hanna96_grok_partial_analysis", PACKAGE / "analyze.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def actual_root() -> Path:
    if not LIVE_ROOT.is_dir():
        pytest.skip("the local immutable Grok validation root is unavailable")
    return LIVE_ROOT


def rewrite(analyzer, path, mutate):
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_bytes(analyzer.canonical(value))


def test_actual_live_shaped_root_reports_only_public_partial_metrics(tmp_path):
    analyzer = module()
    output = tmp_path / "fresh-result.json"
    result = analyzer.write_result(actual_root(), output)
    assert output.read_bytes() == analyzer.canonical(result)
    assert result["coverage"] == {"scheduled_cells": 64, "baseline_scheduled_cells": 32, "descendant13_scheduled_cells": 32, "receipt_backed_cells": 63, "baseline_receipt_backed_cells": 32, "descendant13_receipt_backed_cells": 31, "terminal_ambiguous_cells": 1, "paired_items": 31, "unpaired_items": 1, "paired_groups": 16, "fully_complete_groups": 15, "native_endpoint_contact_cardinality": "unproven"}
    first, second = result["metrics"]
    assert {key: first[key] for key in ("subset", "groups", "paired_items")} == {"subset": "all_31_paired_items", "groups": 16, "paired_items": 31}
    assert first["baseline_equal_group_mae"] == pytest.approx(1.0434027777777777)
    assert first["descendant13_equal_group_mae"] == pytest.approx(0.8307291666666666)
    assert first["percent_reduction"] == pytest.approx(20.382695507487515)
    assert {key: second[key] for key in ("subset", "groups", "paired_items")} == {"subset": "15_fully_complete_groups", "groups": 15, "paired_items": 30}
    assert second["baseline_equal_group_mae"] == pytest.approx(1.0537037037037036)
    assert second["descendant13_equal_group_mae"] == pytest.approx(0.8416666666666667)
    assert second["percent_reduction"] == pytest.approx(20.123022847100167)
    public = json.dumps(result, sort_keys=True)
    assert all(token not in public for token in ("h96-", "item-", "prompt-", "request_id", "session_id", "C:\\Users"))


def test_actual_live_shaped_copy_rejects_extra_artifact(tmp_path):
    analyzer = module()
    copied = tmp_path / "copy"
    shutil.copytree(actual_root(), copied)
    (copied / "h96-02381d00cae5743fb072" / "unapproved.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="successful cell inventory"):
        analyzer.analyze(copied)


def test_actual_live_shaped_copy_rejects_native_envelope_tamper(tmp_path):
    analyzer = module()
    copied = tmp_path / "copy"
    shutil.copytree(actual_root(), copied)
    response = copied / "h96-02381d00cae5743fb072" / "native-response.bin"
    raw = response.read_bytes()
    response.write_bytes(b"X" + raw[1:])
    with pytest.raises(ValueError, match="native envelope"):
        analyzer.analyze(copied)


def test_actual_live_shaped_copy_rejects_fabricated_request_prompt_and_settings_chains(tmp_path):
    analyzer = module()
    copied = tmp_path / "copy"
    shutil.copytree(actual_root(), copied)
    cell = copied / "h96-02381d00cae5743fb072"
    receipt_path, result_path = cell / "execution-receipt.json", cell / "result.json"
    request_path, prompt_path, settings_path = cell / "native-request.bin", cell / "prompt-request.bin", cell / "effective-settings.json"
    original_request, original_prompt, original_settings = request_path.read_bytes(), prompt_path.read_bytes(), settings_path.read_bytes()
    original_receipt, original_result = receipt_path.read_bytes(), result_path.read_bytes()

    request_path.write_bytes(b"X" + original_request[1:])
    rewrite(analyzer, receipt_path, lambda value: value.__setitem__("native_request_sha256", analyzer.sha256(request_path.read_bytes())))
    rewrite(analyzer, result_path, lambda value: value.__setitem__("receipt_sha256", analyzer.sha256(receipt_path.read_bytes())))
    with pytest.raises(ValueError):
        analyzer.analyze(copied)
    request_path.write_bytes(original_request)
    receipt_path.write_bytes(original_receipt)
    result_path.write_bytes(original_result)

    prompt_path.write_bytes(b"X" + original_prompt[1:])
    with pytest.raises(ValueError):
        analyzer.analyze(copied)
    prompt_path.write_bytes(original_prompt)

    rewrite(analyzer, settings_path, lambda value: value.__setitem__("route_name", "fabricated"))
    rewrite(analyzer, receipt_path, lambda value: value.__setitem__("effective_settings_sha256", analyzer.sha256(json.loads(settings_path.read_text(encoding="utf-8")))))
    rewrite(analyzer, result_path, lambda value: value.__setitem__("receipt_sha256", analyzer.sha256(receipt_path.read_bytes())))
    with pytest.raises(ValueError):
        analyzer.analyze(copied)
    settings_path.write_bytes(original_settings)
    receipt_path.write_bytes(original_receipt)
    result_path.write_bytes(original_result)


def test_contract_pins_closed_root_and_partial_geometry():
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["geometry"] == {"scheduled_cells": 64, "receipt_backed_cells": 63, "terminal_ambiguous_cells": 1, "paired_items": 31, "paired_groups": 16, "fully_complete_groups": 15}
    assert contract["authority"] == {"confirmation": "none", "generalization": "none", "imputation": "forbidden", "pooling": "forbidden", "runtime": "none", "selection": "none"}
    assert contract["evidence"] == {"closed_source_root": True, "pinned_executor_admission_replay": "per_receipt_required", "receipt_envelope_association": "required", "runner_prompt_artifact": "exact_required", "scheduled_native_request": "exact_required", "terminal_ambiguity": "preserved_and_excluded"}
