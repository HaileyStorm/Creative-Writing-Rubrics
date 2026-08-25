#!/usr/bin/env python3
"""Verify the public provider-free QPC24 v2 successor contract."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
from hbqrs.core import compile_bundle, compiled_questions, load_data, resolve_bundle

STUDY_ID = "hbq-qpc24-two-pass-product-confirmation-v2"
HEAD = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
QUESTION_SEQUENCE_SHA256 = "22c7c011189072b746eef4cd6aaf0b4da8cb21fd4786e9920593a4e9828602ce"
RUNTIME_BINDINGS = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))["runtime_bindings"]

def sha256_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def canonical(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def contract() -> dict[str, Any]:
    value = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))
    if value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("source_head") != HEAD: raise ValueError("QPC24 v2 public identity drift")
    if value.get("execution", {}).get("dispatch_surface") != "absent" or value["execution"].get("remote_provider_call_count_now") != 0: raise ValueError("QPC24 v2 provider boundary drift")
    geometry = value.get("geometry", {})
    if {key: geometry.get(key) for key in ("complete_eligible_question_count", "questions_per_provider_call", "full_batches_per_pass", "final_remainder_questions", "calls_per_pass", "target_voting_calls", "target_voting_positions", "maximum_unique_contacts")} != {"complete_eligible_question_count":221, "questions_per_provider_call":24, "full_batches_per_pass":9, "final_remainder_questions":5, "calls_per_pass":10, "target_voting_calls":60, "target_voting_positions":1326, "maximum_unique_contacts":60}: raise ValueError("QPC24 v2 geometry drift")
    if value.get("fidelity", {}).get("per_selected_pass") != "full_prose.novel_221_leaves_in_9x24_plus_5" or value["fidelity"].get("historical_five_repeat_plan") != "retained_as_extended_validation_path_not_replaced": raise ValueError("QPC24 v2 fidelity drift")
    if value.get("non_claims") != {"runtime_default":"none", "new_evaluation_mode":"none", "replacement_of_five_repeat_validation":"none"}: raise ValueError("QPC24 v2 default boundary drift")
    return value
def validate() -> dict[str, Any]:
    value = contract()
    if subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, capture_output=True, check=False).stdout.strip() != HEAD: raise ValueError("QPC24 v2 exact-head drift")
    for relative, digest in RUNTIME_BINDINGS.items():
        if sha256_bytes((REPOSITORY / relative).read_bytes()) != digest: raise ValueError(f"QPC24 v2 runtime binding drift: {relative}")
    rows = compiled_questions(compile_bundle(load_data(REPOSITORY / "registry" / "all_modules.json"), resolve_bundle(load_data(REPOSITORY / "bundles" / "all_bundles.json"), "prose.novel")))
    if len(rows) != 221 or sha256_bytes(canonical([str(row["question"]["id"]) for row in rows])) != QUESTION_SEQUENCE_SHA256: raise ValueError("QPC24 v2 question geometry drift")
    return {"study_id":STUDY_ID, "provider_calls":0, "logical_work_evaluations":6, "planned_voting_calls":60, "maximum_unique_contacts":60, "verdict_positions":1326, "status":"FROZEN_PROVIDER_FREE_PREEXECUTION", "runtime_bindings":RUNTIME_BINDINGS}
def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("command", choices=("verify",)); parser.parse_args(argv); print(json.dumps(validate(), sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
