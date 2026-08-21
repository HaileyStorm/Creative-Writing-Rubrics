#!/usr/bin/env python3
"""Create and replay-verify the one-way HANNA development promotion decision."""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from analyze_study import verify_phase_analysis, verify_primary_phase
from study import CONTRACT, load_frozen, read_json, sha, write_json


def _delta(left: float, right: float) -> str:
    return str(Decimal(str(left)) - Decimal(str(right)))


def _primary_development(data: Path, output: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    if not output.is_dir():
        raise ValueError("GPT development output does not bind the frozen primary work")
    verify_primary_phase(data, frozen, "development", output)
    summary = read_json(output / "summary.json")
    macro = summary.get("primary_generated_only", {}).get("macro_spearman", {}).get("estimate")
    if not isinstance(macro, (int, float)):
        raise ValueError("GPT development output lacks its generated-only macro estimate")
    return summary


def _binding(output: Path) -> dict[str, Any]:
    files = {name: output / name for name in ("summary.json", "items.jsonl", "manifest.json")}
    if any(not path.is_file() for path in files.values()):
        raise ValueError("Development analysis lacks a required public artifact")
    return {"output_dir": str(output), **{name: {"sha256": sha(path), "bytes": path.stat().st_size} for name, path in files.items()}}


def _replay(work: Path, data: Path, gate: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frozen = load_frozen(work)
    bindings = [gate.get(key) for key in ("gpt_development", "grok_development", "flash_development")]
    if not all(isinstance(value, Mapping) and isinstance(value.get("output_dir"), str) for value in bindings):
        raise ValueError("Promotion decision lacks development-analysis bindings")
    gpt_output, grok_output, flash_output = (Path(value["output_dir"]) for value in bindings)
    gpt = _primary_development(data, gpt_output, frozen)
    grok = verify_phase_analysis(data, work, "grok_4_6_high", "development", grok_output, gpt_phase_items=gpt_output / "items.jsonl")
    flash = verify_phase_analysis(data, work, "nous_flash_max", "development", flash_output, gpt_phase_items=gpt_output / "items.jsonl")
    for value, output in zip(bindings, (gpt_output, grok_output, flash_output)):
        if dict(value) != _binding(output):
            raise ValueError("Promotion decision analysis artifact binding drifted")
    return gpt, grok, flash


def create_gate(work: Path, data: Path, gpt_output: Path, grok_output: Path, flash_output: Path) -> dict[str, Any]:
    frozen = load_frozen(work)
    path = work / CONTRACT["nous_promotion"]["decision_artifact"]
    if path.exists():
        raise ValueError("Refusing to overwrite immutable promotion decision")
    bindings = {"gpt_development": _binding(gpt_output), "grok_development": _binding(grok_output), "flash_development": _binding(flash_output)}
    provisional = {"format_version": 1, "study_id": CONTRACT["study_id"], "supplemental_contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "primary_frozen_sha256": frozen["primary_frozen"]["sha256"], **bindings}
    gpt, _grok, flash = _replay(work, data, provisional)
    gpt_macro = float(gpt["primary_generated_only"]["macro_spearman"]["estimate"])
    flash_macro = float(flash["primary_generated_only"]["macro_spearman"]["estimate"])
    delta = _delta(gpt_macro, flash_macro)
    promoted = Decimal(delta) >= Decimal(str(CONTRACT["nous_promotion"]["macro_delta_threshold"]))
    gate = {**provisional, "gpt_macro_estimate": gpt_macro, "flash_macro_estimate": flash_macro, "flash_macro_delta_vs_gpt": delta, "promotion_reason": "flash_generated_only_macro_delta" if promoted else "not_triggered", "eligible_provider_ids": ["grok_4_6_high", "nous_flash_max"] + (["nous_pro_max"] if promoted else [])}
    write_json(path, gate)
    return gate


def validate_gate(work: Path, data: Path) -> dict[str, Any]:
    frozen = load_frozen(work)
    path = work / CONTRACT["nous_promotion"]["decision_artifact"]
    gate = read_json(path)
    required = {"format_version": 1, "study_id": CONTRACT["study_id"], "supplemental_contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "primary_frozen_sha256": frozen["primary_frozen"]["sha256"]}
    if any(gate.get(key) != value for key, value in required.items()):
        raise ValueError("Promotion decision does not bind this frozen supplemental protocol")
    gpt, _grok, flash = _replay(work, data, gate)
    gpt_macro = float(gpt["primary_generated_only"]["macro_spearman"]["estimate"])
    flash_macro = float(flash["primary_generated_only"]["macro_spearman"]["estimate"])
    delta = _delta(gpt_macro, flash_macro)
    promoted = Decimal(delta) >= Decimal(str(CONTRACT["nous_promotion"]["macro_delta_threshold"]))
    expected_ids = ["grok_4_6_high", "nous_flash_max"] + (["nous_pro_max"] if promoted else [])
    expected_reason = "flash_generated_only_macro_delta" if promoted else "not_triggered"
    if gate.get("gpt_macro_estimate") != gpt_macro or gate.get("flash_macro_estimate") != flash_macro or gate.get("flash_macro_delta_vs_gpt") != delta or gate.get("promotion_reason") != expected_reason or gate.get("eligible_provider_ids") != expected_ids:
        raise ValueError("Promotion decision does not exactly satisfy the frozen development-only rule")
    return gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--gpt-development-output", type=Path, required=True)
    parser.add_argument("--grok-development-output", type=Path, required=True)
    parser.add_argument("--flash-development-output", type=Path, required=True)
    args = parser.parse_args()
    create_gate(args.work_dir.resolve(), args.data_dir.resolve(), args.gpt_development_output.resolve(), args.grok_development_output.resolve(), args.flash_development_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
