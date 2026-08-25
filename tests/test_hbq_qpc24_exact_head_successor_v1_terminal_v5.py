from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1]
PACKAGE = HERE / "evaluation-results" / "hbq-qpc24-exact-head-successor-v1-terminal-v5"


def _load_module():
    spec = importlib.util.spec_from_file_location("qpc24_terminal_v5", PACKAGE / "verify_terminal.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_tampered_projection(tmp_path: Path, mutate) -> Path:
    source = PACKAGE / "qpc24-public-terminal-v5-aggregate.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    mutate(value)
    target = tmp_path / source.name
    target.write_text(json.dumps(value), encoding="utf-8")
    return target


def test_public_v5_terminal_projection_is_aggregate_only_and_nonvoting() -> None:
    value = _load_module().verify()
    assert value["planned_provider_calls"] == 150
    assert value["planned_verdict_positions"] == 3315
    assert value["contacted_provider_calls"] == 13
    assert value["accepted_provider_calls"] == value["voting_provider_calls"] == 12
    assert value["accepted_verdict_positions"] == value["voting_verdict_positions"] == 269
    assert value["nonvoting_structured_provider_calls"] == 1
    assert value["nonvoting_structured_verdict_positions"] == 24
    assert value["untouched_provider_calls"] == 137
    assert value["untouched_verdict_positions"] == 3022


def test_public_v5_terminal_rejects_arithmetic_tampering(tmp_path: Path) -> None:
    module = _load_module()
    module.TERMINAL = _write_tampered_projection(
        tmp_path, lambda value: value.__setitem__("untouched_verdict_positions", 3021)
    )
    with pytest.raises(ValueError, match="aggregate drift"):
        module.verify()


def test_public_v5_terminal_rejects_private_detail(tmp_path: Path) -> None:
    module = _load_module()
    module.TERMINAL = _write_tampered_projection(
        tmp_path, lambda value: value.__setitem__("source_path", "private")
    )
    with pytest.raises(ValueError, match="private detail"):
        module.verify()


def test_public_v5_terminal_rejects_nested_junk(tmp_path: Path) -> None:
    module = _load_module()
    module.TERMINAL = _write_tampered_projection(
        tmp_path, lambda value: value.__setitem__("aggregate", {"count": 1})
    )
    with pytest.raises(ValueError, match="extra detail"):
        module.verify()


def test_public_v5_terminal_rejects_commitment_tampering(tmp_path: Path) -> None:
    module = _load_module()
    module.TERMINAL = _write_tampered_projection(
        tmp_path,
        lambda value: value.__setitem__(
            "opaque_private_receipt_tree_commitment_sha256", "not-a-sha256-commitment"
        ),
    )
    with pytest.raises(ValueError, match="receipt-tree commitment drift"):
        module.verify()
