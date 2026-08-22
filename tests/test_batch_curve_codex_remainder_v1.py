from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "batch-curve-codex-remainder-v1"


def _module():
    spec = importlib.util.spec_from_file_location("batch_curve_codex_remainder_v1", ROOT / "remainder_successor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_closed_parent_geometry_and_remainder_schedule_are_exact() -> None:
    module = _module()
    value, lineage, rows = module.contract(), module.validate_closed_parent(), module.schedule()
    assert value["closed_parent"]["git_commit"] == "ae234403707f2005383188a185123d7a85a16002"
    assert lineage["completed_cells"] == 35
    assert lineage["accepted_parent_batches"] == 31
    assert lineage["quota_rejections"] == 3
    assert len(rows) == 47
    assert rows[:2] == [
        {"parent_cell": 36, "size": 4, "repetition": 3, "batch": 32},
        {"parent_cell": 36, "size": 4, "repetition": 3, "batch": 33},
    ]
    assert rows[-1] == {"parent_cell": 39, "size": 48, "repetition": 3, "batch": 4}
    assert not any(row["parent_cell"] == 36 and row["batch"] <= 31 for row in rows)


def test_prepare_is_local_only_and_requires_fresh_disjoint_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "validate_closed_parent", lambda: {"public_root_sha256": "a" * 64, "private_root_sha256": "b" * 64, "completed_cells": 35, "accepted_parent_batches": 31, "quota_rejections": 3})
    with tempfile.TemporaryDirectory(prefix="cwr-batch-remainder-") as directory:
        root = Path(directory); work, private = root / "work", root / "private"
        receipt = module.prepare(work, private)
        assert receipt["provider_calls_made"] == 0
        assert receipt["scheduled_provider_calls"] == 47
        assert (work / module.PREPARATION).is_file()
        assert list(private.iterdir()) == []
        with pytest.raises(ValueError, match="fresh"):
            module.prepare(work, root / "another-private")
        parent = Path(module.contract()["closed_parent"]["public_root"])
        with pytest.raises(ValueError, match="fresh"):
            module.prepare(parent, root / "parent-private")
        outer = root / "outer"
        with pytest.raises(ValueError, match="disjoint"):
            module.prepare(outer, outer / "private")


def test_quota_gate_needs_explicit_post_retry_preflight_and_is_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "validate_closed_parent", lambda: {"public_root_sha256": "a" * 64, "private_root_sha256": "b" * 64, "completed_cells": 35, "accepted_parent_batches": 31, "quota_rejections": 3})
    with tempfile.TemporaryDirectory(prefix="cwr-batch-remainder-") as directory:
        root = Path(directory); work, private = root / "work", root / "private"
        module.prepare(work, private)
        assert module.live_eligible(work, private, now="2026-08-27T19:22:00-06:00") is False
        with pytest.raises(ValueError, match="before"):
            module.record_current_quota_preflight(work, checked_at="2026-08-27T19:20:59-06:00", availability="available", note="observed")
        record = module.record_current_quota_preflight(work, checked_at="2026-08-27T19:22:00-06:00", availability="available", note="operator observed usable quota")
        assert record["evidence_class"] == "operator_observed_current_quota_preflight"
        assert module.live_eligible(work, private, now="2026-08-27T19:20:59-06:00") is False
        assert module.live_eligible(work, private, now="2026-08-27T19:22:01-06:00") is True
        assert module.live_eligible(work, private, now="2026-08-27T19:37:01-06:00") is False
        preparation = work / module.PREPARATION
        tampered = json.loads(preparation.read_text(encoding="utf-8"))
        tampered["schedule_sha256"] = "0" * 64
        preparation.write_text(json.dumps(tampered), encoding="utf-8")
        assert module.live_eligible(work, private, now="2026-08-27T19:22:01-06:00") is False
        with pytest.raises(ValueError, match="immutable"):
            module.record_current_quota_preflight(work, checked_at="2026-08-27T19:23:00-06:00", availability="available", note="different")


def test_contract_rejects_adversarial_geometry_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    original = module._read

    def altered(path: Path) -> dict:
        value = original(path)
        if path == module.CONTRACT_PATH:
            value["closed_parent"]["partial_cell"]["quota_rejections"]["attempts"] = 2
        return value

    monkeypatch.setattr(module, "_read", altered)
    with pytest.raises(ValueError, match="Quota-rejection"):
        module.contract()

    def extra_key(path: Path) -> dict:
        value = original(path)
        if path == module.CONTRACT_PATH:
            value["quota_gate"]["unexpected"] = True
        return value

    monkeypatch.setattr(module, "_read", extra_key)
    with pytest.raises(ValueError, match="Quota gate"):
        module.contract()


def test_closed_parent_rejects_an_extra_later_public_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    original = module._names

    def extra_cell(directory: Path) -> set[str]:
        names = original(directory)
        return names | {"cell-37.json"} if directory.name == "cells" else names

    monkeypatch.setattr(module, "_names", extra_cell)
    with pytest.raises(ValueError, match="public cell membership"):
        module.validate_closed_parent()


def test_closed_parent_rejects_an_extra_top_level_member(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    original = module._names
    parent_root = Path(module.contract()["closed_parent"]["public_root"]).resolve()

    def extra_top_level(directory: Path) -> set[str]:
        names = original(directory)
        return names | {"unbound.txt"} if directory.resolve() == parent_root else names

    monkeypatch.setattr(module, "_names", extra_top_level)
    with pytest.raises(ValueError, match="top-level"):
        module.validate_closed_parent()


def test_live_eligibility_rejects_any_successor_root_member(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "validate_closed_parent", lambda: {"public_root_sha256": "a" * 64, "private_root_sha256": "b" * 64, "completed_cells": 35, "accepted_parent_batches": 31, "quota_rejections": 3})
    with tempfile.TemporaryDirectory(prefix="cwr-batch-remainder-") as directory:
        root = Path(directory); work, private = root / "work", root / "private"
        module.prepare(work, private)
        module.record_current_quota_preflight(work, checked_at="2026-08-27T19:22:00-06:00", availability="available", note="operator observed usable quota")
        assert module.live_eligible(work, private, now="2026-08-27T19:22:01-06:00") is True
        (private / "unexpected.txt").write_text("x", encoding="utf-8")
        assert module.live_eligible(work, private, now="2026-08-27T19:22:01-06:00") is False
        other_work, other_private = root / "other-work", root / "other-private"
        module.prepare(other_work, other_private)
        module.record_current_quota_preflight(other_work, checked_at="2026-08-27T19:22:00-06:00", availability="available", note="operator observed usable quota")
        (other_work / "unexpected.txt").write_text("x", encoding="utf-8")
        assert module.live_eligible(other_work, other_private, now="2026-08-27T19:22:01-06:00") is False
