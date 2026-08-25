from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hbqrs.cli import main as hbq_cli_main

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-hinge-treatment-successor-v1"
HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
TARGET = "penalty.purple_prose.metaphor"
PRIVATE_DIRECTORY = "figurative-hinge-treatment-v1-private"
LEDGER = "expected-ledger.json"
QUOTE = "Include at least one exact_quote copied verbatim from the supplied artifact. Summary-only evidence is invalid."


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canon(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract() -> dict[str, Any]:
    return load(ROOT / "study-contract.json")


def corpus() -> list[dict[str, str]]:
    return load(ROOT / "public-synthetic-corpus.json")["cases"]


def schedule() -> list[dict[str, str]]:
    return [{"slot_id": f"hinge-{case['case_id']}-r{repeat}", "case_id": case["case_id"], "repeat": str(repeat), "leaf_id": TARGET} for case in corpus() for repeat in (1, 2)]


def validate() -> dict[str, Any]:
    value, rows = contract(), corpus()
    if value["study_id"] != STUDY_ID or value["source_anchor"]["commit"] != HEAD or value["target"]["leaf_id"] != TARGET:
        raise ValueError("identity or exact-head drift")
    if value["geometry"] != {"public_synthetic_cases": 4, "positive_controls": 2, "negative_controls": 2, "repeats": 2, "provider_calls": 8, "train_or_dev": "none", "one_leaf_per_call": True}:
        raise ValueError("small pilot geometry drift")
    if len(rows) != 4 or len({row["case_id"] for row in rows}) != 4 or len(schedule()) != 8:
        raise ValueError("opaque case or repeat geometry drift")
    text = value["treatment"]["exact_text"]
    if "connective" not in text or "additional artifact-grounded mechanism" not in text or "familiarity/defaultness" not in text or "density" not in text:
        raise ValueError("hinge or ownership boundary drift")
    return {"study_id": STUDY_ID, "slots": 8, "provider_calls": 0, "promotion": "none"}


def require_head() -> None:
    observed = subprocess.run(["git", "-C", str(ROOT.parents[1]), "rev-parse", "HEAD"], capture_output=True, check=True, text=True).stdout.strip()
    if observed != HEAD:
        raise ValueError(f"exact source HEAD required: {HEAD}, found {observed}")


def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"frozen material drift: {path}")
    if not path.exists():
        path.write_bytes(content)


def bundle() -> list[dict[str, Any]]:
    leaf = next(json.loads(line) for line in (ROOT.parents[1] / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(line).get("id") == TARGET)
    return [{"standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": STUDY_ID, "version": 1, "title": "Figurative hinge singleton diagnostic", "module_ids": [leaf["module_id"]], "task_contract_domain_id": "figurative-hinge-1", "domains": [{"domain_id": "figurative-hinge-1", "title": TARGET, "points": 1.0, "components": [{"module_id": leaf["module_id"], "weight": 1.0, "include_question_ids": [TARGET]}], "score_mode": "weighted_binary_mean"}], "penalty_modules": [], "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True}, "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True}}]


def task(slot: dict[str, str]) -> dict[str, Any]:
    treatment = contract()["treatment"]["exact_text"]
    return {"contract_version": 1, "contract_id": f"{STUDY_ID}-{slot['slot_id']}", "artifact_id": slot["slot_id"], "context": {"artifact_kind": "prose.short_story", "declared_scope": "complete supplied passage", "completion_status": "complete", "background": ["Public synthetic figurative hinge diagnostic."], "constraints": ["Use only the supplied artifact.", QUOTE, treatment], "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def override(slot: dict[str, str], item: dict[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["slot_id"], "bundle_id": STUDY_ID, "task_contract_sha256": hashlib.sha256(canon(item)).hexdigest(), "contract_id": item["contract_id"], "artifact_kind": item["context"]["artifact_kind"], "declared_scope": item["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "figurative-hinge-treatment-scope-v1", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for a public synthetic figurative hinge diagnostic."}


def root(private_root: Path) -> Path:
    return private_root / PRIVATE_DIRECTORY


def render_command(slot: dict[str, str], private_root: Path) -> list[str]:
    r = root(private_root)
    return [sys.executable, "-m", "hbqrs", "--registry", str(r / "catalog" / "registry.json"), "--bundles", str(r / "catalog" / "bundles.json"), "render-judge", "--artifact", str(r / "inputs" / f"{slot['slot_id']}.txt"), "--bundle", STUDY_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", slot["slot_id"], "--question-id", TARGET, "--task-contract", str(r / "contracts" / f"{slot['slot_id']}.json"), "--scope-compatibility-override", str(r / "overrides" / f"{slot['slot_id']}.json"), "--output", str(r / "rendered-prompts" / f"{slot['slot_id']}.txt")]


def local(command: list[str], **_kwargs: Any) -> SimpleNamespace:
    output, error = io.StringIO(), io.StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        code = hbq_cli_main(command[3:])
    return SimpleNamespace(returncode=int(code), stdout=output.getvalue(), stderr=error.getvalue())


def dry_run(private_root: Path, *, runner_call: Any = local) -> dict[str, Any]:
    validate(); require_head()
    labels = load(private_root / LEDGER)["labels"]
    if set(labels) != {case["case_id"] for case in corpus()} or set(labels.values()) != {"YES", "NO"}:
        raise ValueError("private construct-pure control ledger drift")
    r, slots = root(private_root), schedule()
    write_once(r / "catalog" / "registry.json", (ROOT.parents[1] / "registry" / "all_modules.json").read_bytes())
    write_once(r / "catalog" / "bundles.json", canon(bundle()))
    by_id = {case["case_id"]: case for case in corpus()}
    for slot in slots:
        item = task(slot)
        write_once(r / "inputs" / f"{slot['slot_id']}.txt", by_id[slot["case_id"]]["text"].encode("utf-8"))
        write_once(r / "contracts" / f"{slot['slot_id']}.json", canon(item))
        write_once(r / "overrides" / f"{slot['slot_id']}.json", canon(override(slot, item)))
        prompt = r / "rendered-prompts" / f"{slot['slot_id']}.txt"; prompt.parent.mkdir(parents=True, exist_ok=True)
        result = runner_call(render_command(slot, private_root), check=False, text=True, encoding="utf-8", capture_output=True)
        if getattr(result, "returncode", 1):
            raise RuntimeError(f"provider-free render failed for {slot['slot_id']}: {getattr(result, 'stderr', '')}")
        prompt.write_bytes(prompt.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    material = sorted([*r.glob("catalog/*.json"), *r.glob("inputs/*.txt"), *r.glob("contracts/*.json"), *r.glob("overrides/*.json")])
    prompts = sorted((r / "rendered-prompts").glob("*.txt"))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "source_head": HEAD, "provider_calls": 0, "slots": slots, "max_future_provider_calls": 8, "promotion": "none", "bindings": {"contract_sha256": sha(ROOT / "study-contract.json"), "study_sha256": sha(ROOT / "study.py"), "corpus_sha256": sha(ROOT / "public-synthetic-corpus.json"), "ledger_sha256": sha(private_root / LEDGER), "material_sha256": hashlib.sha256(canon({str(p.relative_to(r)): sha(p) for p in material})).hexdigest(), "prompt_sha256": hashlib.sha256(canon({str(p.relative_to(r)): sha(p) for p in prompts})).hexdigest(), "commands_sha256": hashlib.sha256(canon({slot["slot_id"]: render_command(slot, private_root) for slot in slots})).hexdigest()}}
    write_once(r / "frozen-dry-run.v1.json", canon(manifest))
    return {"provider_calls": 0, "slots": 8, "manifest_sha256": sha(r / "frozen-dry-run.v1.json")}
