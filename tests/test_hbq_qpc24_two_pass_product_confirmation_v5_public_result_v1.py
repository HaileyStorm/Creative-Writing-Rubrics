from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PUBLIC = REPO / "evaluation-results" / "hbq-qpc24-two-pass-product-confirmation-v5-public-result-v1"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_public_qpc24_v5_result_is_aggregate_only_and_consistent():
    value = load(PUBLIC / "verify_output.py", "qpc24_v5_public_result").verify()
    assert value["protocol_geometry"] == {
        "accepted_new_calls": 10,
        "complete_passes": 6,
        "inherited_complete_calls": 50,
        "verdict_positions": 1326,
    }
    stable = value["stable_two_pass_cross_artifact_differences"]
    assert stable["author_original_vs_public_control_story"] == {"common_stable_leaves": 200, "different": 48, "no_left_only": 41, "no_right_only": 1}
    assert stable["gpt_5_6_pro_rewrite_vs_public_control_story"] == {"common_stable_leaves": 195, "different": 43, "no_left_only": 41, "no_right_only": 1}
