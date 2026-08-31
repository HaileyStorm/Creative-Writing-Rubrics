from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-sol-composite-partial-analysis-v1"
A = Path(r"C:\Users\Haile\Documents\cwr-hanna96-validation-sol-c280729-20260831a")
B = Path(r"C:\Users\Haile\Documents\cwr-hanna96-validation-sol-c280729-20260831b")
FREEZE = Path(r"C:\Users\Haile\Documents\cwr-hanna96-validation-freeze-c280729-20260831a")


def module(package: Path = PACKAGE):
    spec = importlib.util.spec_from_file_location("_hanna96_sol_composite", package / "analyze.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def copied_package(tmp_path: Path) -> Path:
    copied = tmp_path / "package"
    shutil.copytree(PACKAGE, copied)
    return copied


def live() -> tuple[Path, Path, Path]:
    if not (A.is_dir() and B.is_dir() and FREEZE.is_dir()):
        pytest.skip("the local immutable Fresh96 Sol roots are unavailable")
    return A, B, FREEZE


def test_actual_live_shaped_roots_report_public_composite_metrics(tmp_path):
    analyzer = module()
    result = analyzer.write_result(*live(), tmp_path / "result.json")
    assert (tmp_path / "result.json").read_bytes() == analyzer.canonical(result)
    assert result["coverage"] == {"scheduled_cells": 64, "receipt_backed_logical_cells": 63, "uncovered_logical_cells": 1, "A": {"success": 57, "unstarted": 7}, "B": {"success": 60, "terminal_ambiguous": 4}, "repeat_success_overlap": 54, "selected_from_A": 3, "selected_from_B": 60, "paired_items": 31, "paired_groups": 16, "fully_complete_groups": 15, "native_endpoint_contact_cardinality": "unproven"}
    assert result["metrics"][0]["baseline_equal_group_mae"] == pytest.approx(1.4061631944444444)
    assert result["metrics"][0]["descendant13_equal_group_mae"] == pytest.approx(1.20625)
    assert result["metrics"][0]["percent_reduction"] == pytest.approx(14.216926970800658)
    assert result["metrics"][1]["baseline_equal_group_mae"] == pytest.approx(1.3832407407407408)
    assert result["metrics"][1]["descendant13_equal_group_mae"] == pytest.approx(1.1933333333333336)
    assert result["metrics"][1]["percent_reduction"] == pytest.approx(13.72916527210655)
    public = json.dumps(result, sort_keys=True)
    assert all(token not in public for token in ("h96-", "item-", "prompt-", "thread_id", "session_id", "C:\\Users"))


def test_actual_live_shaped_copy_rejects_extra_artifact(tmp_path):
    analyzer = module()
    _a, b, freeze = live()
    copied = tmp_path / "b"
    shutil.copytree(b, copied)
    (copied / "h96-sol-h96-02381d00cae5743fb072" / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="cell inventory"):
        analyzer.analyze(live()[0], copied, freeze)


def test_actual_live_shaped_copy_rejects_final_response_tamper(tmp_path):
    analyzer = module()
    _a, b, freeze = live()
    copied = tmp_path / "b"
    shutil.copytree(b, copied)
    final = copied / "h96-sol-h96-02381d00cae5743fb072" / "raw-codex-final-response.bin"
    final.write_bytes(b"X" + final.read_bytes()[1:])
    with pytest.raises(ValueError, match="invalid final response"):
        analyzer.analyze(live()[0], copied, freeze)


def test_actual_live_shaped_copy_rejects_forged_launch_intent(tmp_path):
    analyzer = module()
    _a, b, freeze = live()
    copied = tmp_path / "b"
    shutil.copytree(b, copied)
    intent = copied / "h96-sol-h96-02381d00cae5743fb072" / "launch-intent.json"
    value = json.loads(intent.read_text(encoding="utf-8"))
    value["prepared_sha256"] = "0" * 64
    intent.write_bytes(analyzer.canonical(value))
    with pytest.raises(ValueError, match="pinned Sol admission/projection"):
        analyzer.analyze(live()[0], copied, freeze)


@pytest.mark.parametrize("mutation", ("non_null", "extra", "missing"))
def test_actual_live_shaped_copy_rejects_any_reported_compatibility_drift(tmp_path, mutation):
    analyzer = module()
    _a, b, freeze = live()
    copied = tmp_path / "b"
    shutil.copytree(b, copied)
    record = copied / "h96-sol-h96-02381d00cae5743fb072" / "codex-record.json"
    value = json.loads(record.read_text(encoding="utf-8"))
    if mutation == "non_null":
        value["reported"]["model"] = "gpt-5.6-sol"
    elif mutation == "extra":
        value["reported"]["unexpected"] = None
    else:
        value["reported"].pop("session_id")
    record.write_bytes(analyzer.canonical(value))
    with pytest.raises(ValueError, match="codex record compatibility ceiling"):
        analyzer.analyze(live()[0], copied, freeze)


def test_disjoint_output_is_required():
    analyzer = module()
    a, b, freeze = live()
    with pytest.raises(ValueError, match="result output must be disjoint"):
        analyzer.write_result(a, b, freeze, a / "would-be-result.json")


def test_contract_pins_composite_geometry_and_authority():
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["geometry"] == {"A_success": 57, "A_unstarted": 7, "B_success": 60, "B_terminal_ambiguous": 4, "fully_complete_groups": 15, "logical_receipt_backed_cells": 63, "paired_groups": 16, "paired_items": 31, "repeat_success_overlap": 54, "scheduled_cells": 64, "uncovered_cells": 1}
    assert contract["authority"] == {"confirmation": "none", "generalization": "none", "imputation": "forbidden", "pooling": "forbidden", "runtime": "none", "selection": "none"}
    assert contract["compatibility"] == {"codex_record_reported": "exact_all_null_in_memory_projection_only"}
    assert contract["pins"]["public_result"] == {"sha256": "967d3f8c372d95b3eec61e9bf7fdf4b3680a29dfdcc8c8e446553fcefcff786a", "result_sha256": "cf0da171a1d26fed20f26e562791ea60a1de7ce8c22995dce7514852d6a83715"}


def test_package_rejects_public_result_byte_tamper(tmp_path):
    copied = copied_package(tmp_path)
    result = copied / "result.json"
    result.write_bytes(b"X" + result.read_bytes()[1:])
    with pytest.raises(ValueError, match="invalid public result"):
        module(copied).validate_package()


def test_package_rejects_public_result_removal(tmp_path):
    copied = copied_package(tmp_path)
    (copied / "result.json").unlink()
    with pytest.raises(ValueError, match="package inventory"):
        module(copied).validate_package()


def test_package_rejects_extra_artifact(tmp_path):
    copied = copied_package(tmp_path)
    (copied / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="package inventory"):
        module(copied).validate_package()
