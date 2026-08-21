"""Freeze the small, provisional Ox Alpha HANNA comparison without copying prose."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as runner_module


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
SUPPLEMENTAL_V1_ROOT = HERE.parent / "hbq-human-alignment-supplemental-providers-v1"
CANONICAL_GPT_ITEM_KEYS = {"item_id", "story_id", "source_model", "quartile", "prompt_group_id", "story_sha256", "prompt_sha256", "human_ratings", "human_means", "human_overall", "hbq_full_observed_score", "hbq_mapping", "evidence"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Required file is unavailable: {path}")
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def strict_json(text: str, *, label: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {label}") from exc


def read_json(path: Path) -> dict[str, Any]:
    value = strict_json(path.read_text(encoding="utf-8"), label=str(path))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _external_separate(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if any(_inside(path, REPO_ROOT) for path in resolved):
        raise ValueError("Primary/work/proof roots must remain outside the repository")
    if any(left == right or _inside(left, right) or _inside(right, left) for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("Primary/work/proof roots must be distinct and non-overlapping")


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    runtime = value.get("runtime")
    if (
        value.get("format_version") != 1
        or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v1"
        or value.get("frozen_before_execution") is not True
        or value.get("provider") != {
            "provider_id": "ox_alpha_max",
            "provider": "nous",
            "model": "stealth/ox-alpha",
            "provider_canonical_model": "stealth/ox-alpha",
            "reported_models": ["stealth/ox-alpha"],
            "reasoning": "max",
            "allow_unattested_reasoning": True,
            "provisional_reasoning": True,
            "maximum_workers": 1,
            "evidence_status": "provisional_only",
        }
        or not isinstance(runtime, Mapping)
    ):
        raise ValueError("Ox Alpha contract is not the frozen provisional protocol")
    expected = {
        "bundle_id": "prose.short_story", "question_count": 178, "batch_size": 32,
        "expected_batches_per_item": 6, "batch_attempts": 1, "workers": 1,
        "maximum_logical_requests": 18, "maximum_physical_http_attempts_per_logical_request": 2,
        "maximum_physical_http_attempts": 36, "retry_or_fallback": "forbidden",
    }
    if {key: runtime.get(key) for key in expected} != expected:
        raise ValueError("Ox Alpha runtime geometry drifted")
    if value.get("zero_cost", {}).get("no_purchase") is not True:
        raise ValueError("Ox Alpha zero-cost policy drifted")
    return value


CONTRACT = load_contract()


def runtime_bindings() -> dict[str, dict[str, Any]]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    bridge = launcher.parent / "nous_codex_bridge.py"
    return {"runner": fingerprint(Path(runner_module.__file__)), "launcher": fingerprint(launcher), "bridge": fingerprint(bridge)}


def _external_input(folder: Path, row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    expected = row.get("external_input")
    if not isinstance(expected, Mapping) or set(expected) != {"source.md", "prompt.md", "task-contract.json"}:
        raise ValueError("Primary selection lacks exact external input commitments")
    observed = {name: fingerprint(folder / name) for name in expected}
    if observed != expected:
        raise ValueError("Primary input bytes drifted")
    return observed


def _canonical_primary(primary_work: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("ox_alpha_primary_validator", SUPPLEMENTAL_V1_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Canonical supplemental-v1 primary validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    frozen, _ = module._validate_primary_frozen(primary_work)
    return frozen


def _primary(primary_work: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frozen = _canonical_primary(primary_work)
    rows = frozen.get("partitions", {}).get("development")
    question_ids = frozen.get("question_ids")
    runtime_files = frozen.get("runtime_files")
    seed = frozen.get("selection", {}).get("seed")
    if (
        frozen.get("study_id") != "hbq-human-alignment-v3"
        or frozen.get("frozen_before_execution") is not True
        or not isinstance(rows, list)
        or len(rows) != 88
        or not isinstance(question_ids, list)
        or len(question_ids) != CONTRACT["runtime"]["question_count"]
        or len(set(question_ids)) != len(question_ids)
        or not isinstance(runtime_files, Mapping)
        or not {"src/hbqrs/core.py", "prompts/judge/BINARY_EVALUATION_PROMPT.md", "schema/hbq_judge_response.schema.json"} <= set(runtime_files)
        or not isinstance(seed, int)
        or isinstance(seed, bool)
    ):
        raise ValueError("Primary development freeze cannot supply the Ox Alpha pilot")
    typed = [dict(row) for row in rows if isinstance(row, Mapping)]
    if len(typed) != len(rows) or any(not all(isinstance(row.get(key), str) and row[key] for key in ("item_id", "story_sha256", "prompt_sha256", "model")) for row in typed):
        raise ValueError("Primary development selection is malformed")
    if len({row["item_id"] for row in typed}) != len(typed):
        raise ValueError("Primary development selection reuses an item")
    return frozen, typed


def selected_cells(primary_work: Path) -> list[dict[str, Any]]:
    frozen, rows = _primary(primary_work)
    selected = sorted(rows, key=lambda row: (row["story_sha256"], row["prompt_sha256"], row["item_id"]))[:3]
    cells: list[dict[str, Any]] = []
    for number, row in enumerate(selected, 1):
        folder = primary_work / "inputs" / "development" / row["item_id"]
        cells.append({
            "cell_id": f"ox-alpha-{number:02d}", "item_id": row["item_id"], "source_model": row["model"],
            "story_sha256": row["story_sha256"], "prompt_sha256": row["prompt_sha256"],
            "inputs": _external_input(folder, row), "question_ids": list(frozen["question_ids"]),
        })
    if len({cell["item_id"] for cell in cells}) != 3:
        raise ValueError("Ox Alpha selection is not three distinct primary stories")
    return cells


def _gpt_reference(gpt_output: Path, primary: Mapping[str, Any], cells: list[Mapping[str, Any]]) -> dict[str, Any]:
    files = {name: fingerprint(gpt_output / name) for name in ("items.jsonl", "summary.json", "manifest.json")}
    summary = read_json(gpt_output / "summary.json")
    manifest = read_json(gpt_output / "manifest.json")
    expected = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": "development", "study_contract_sha256": primary.get("study_contract_sha256"), "runtime_sha256": primary.get("runtime_sha256"), "package_commit": primary.get("package_commit")}
    if any(summary.get(key) != value for key, value in expected.items() if key != "package_commit") or summary.get("item_count") != 88 or any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("GPT paired reference does not bind the canonical primary development study/phase")
    actual_files = {path.relative_to(gpt_output).as_posix(): {"bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(gpt_output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    if manifest.get("files") != actual_files:
        raise ValueError("GPT paired reference manifest does not exactly bind its public output")
    rows = [strict_json(line, label=f"{gpt_output / 'items.jsonl'}:{number}") for number, line in enumerate((gpt_output / "items.jsonl").read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        item_id = row.get("item_id") if isinstance(row, Mapping) else None
        if not isinstance(item_id, str) or not item_id or item_id in by_id:
            raise ValueError("GPT paired reference has an invalid or duplicate item_id")
        by_id[item_id] = row
    expected_rows = {str(row["item_id"]): row for row in primary["partitions"]["development"]}
    if len(by_id) != 88 or set(by_id) != set(expected_rows):
        raise ValueError("GPT paired reference does not cover the exact canonical 88-item development selection")
    for item_id, selection in expected_rows.items():
        row = by_id[item_id]
        if (
            set(row) != CANONICAL_GPT_ITEM_KEYS
            or row.get("story_sha256") != selection["story_sha256"]
            or row.get("prompt_sha256") != selection["prompt_sha256"]
            or row.get("source_model") != selection["model"]
        ):
            raise ValueError("GPT paired reference does not bind canonical primary source metadata")
    for cell in cells:
        row = by_id.get(str(cell["item_id"]))
        if not isinstance(row, Mapping) or any(row.get(key) != cell[key] for key in ("story_sha256", "prompt_sha256", "source_model")):
            raise ValueError("GPT paired reference does not bind the selected published HANNA source hashes")
    # Selection is already frozen before score-bearing item rows are parsed.
    return {"output": str(gpt_output.resolve()), "files": files, "study": expected}


def _validate_bridge_evidence(root: Path) -> Mapping[str, Any]:
    bridge = runner_module.NOUS_LAUNCHER_PATH.parent / "nous_codex_bridge.py"
    if not bridge.is_file():
        raise ValueError("Canonical Nous bridge validator is unavailable")
    spec = importlib.util.spec_from_file_location("ox_alpha_sealed_bridge_validator", bridge)
    if spec is None or spec.loader is None:
        raise ValueError("Canonical Nous bridge validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.validate_evidence(root)
    if not isinstance(result, Mapping) or result.get("valid") is not True:
        raise ValueError("Canonical Nous bridge evidence validation failed")
    return result


def _has_structured_billing_signal(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if "charge" in lowered or "payment" in lowered:
                return True
            if key != "choices" and _has_structured_billing_signal(nested):
                return True
    elif isinstance(value, list):
        return any(_has_structured_billing_signal(item) for item in value)
    return False


def _zero_cost_proof(proof: Path) -> dict[str, Any]:
    value = read_json(proof)
    catalog_text, usage_text = value.get("catalog_evidence_root"), value.get("usage_evidence_root")
    if value.get("schema") != "codex-nous-ox-alpha-zero-cost-proof-v3" or not isinstance(catalog_text, str) or not catalog_text or not isinstance(usage_text, str) or not usage_text:
        raise ValueError("External sealed Nous zero-cost catalog/usage proof is invalid")
    catalog_root, usage_root = Path(catalog_text).resolve(), Path(usage_text).resolve()
    if (
        catalog_root == usage_root
        or _inside(catalog_root, usage_root)
        or _inside(usage_root, catalog_root)
        or not catalog_root.is_dir()
        or not usage_root.is_dir()
        or _inside(catalog_root, REPO_ROOT)
        or _inside(usage_root, REPO_ROOT)
    ):
        raise ValueError("Zero-cost proof EvidenceRoot must remain outside the repository")
    catalog_validation, usage_validation = _validate_bridge_evidence(catalog_root), _validate_bridge_evidence(usage_root)
    catalog_manifest, catalog_receipt = read_json(catalog_root / "manifest.json"), read_json(catalog_root / "receipt.json")
    manifest, receipt = read_json(usage_root / "manifest.json"), read_json(usage_root / "receipt.json")
    if (
        catalog_manifest.get("schema") != "codex-nous-evidence-v1" or catalog_manifest.get("mode") != "catalog"
        or catalog_receipt.get("schema") != "codex-nous-outcome-v1" or catalog_receipt.get("status") != "success"
        or catalog_receipt.get("receipt_sha256") != catalog_validation.get("receipt_sha256")
        or manifest.get("schema") != "codex-nous-evidence-v1" or manifest.get("requested_provider") != "nous"
        or manifest.get("requested_model") != "stealth/ox-alpha" or manifest.get("requested_reasoning_effort") != "max"
        or receipt.get("schema") != "codex-nous-outcome-v1" or receipt.get("status") != "success"
        or receipt.get("receipt_sha256") != usage_validation.get("receipt_sha256")
    ):
        raise ValueError("Sealed Nous catalog/usage evidence has the wrong route or receipt binding")
    try:
        sealed_at = datetime.fromisoformat(str(receipt["sealed_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("Sealed Nous catalog/usage evidence has no timestamp") from exc
    if sealed_at.tzinfo is None:
        raise ValueError("Sealed Nous catalog/usage evidence has no timezone")
    catalog_events = [strict_json(line, label=f"{catalog_root / 'events.jsonl'}:{number}") for number, line in enumerate((catalog_root / "events.jsonl").read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    catalog_records = [record for event in catalog_events if isinstance(event, Mapping) and event.get("event_type") == "http_attempt" for record in (event.get("data", {}).get("response_body", {}).get("data", []) if isinstance(event.get("data"), Mapping) else [])]
    ox = [record for record in catalog_records if isinstance(record, Mapping) and record.get("id") == "stealth/ox-alpha" and record.get("canonical_slug") == "stealth/ox-alpha"]
    if len(ox) != 1 or not isinstance(ox[0].get("pricing"), Mapping) or ox[0]["pricing"].get("prompt") not in {"0", "0.0", "0.0000000000"} or ox[0]["pricing"].get("completion") not in {"0", "0.0", "0.0000000000"}:
        raise ValueError("Sealed Nous catalog evidence does not show one zero-priced Ox Alpha record")
    events = [strict_json(line, label=f"{usage_root / 'events.jsonl'}:{number}") for number, line in enumerate((usage_root / "events.jsonl").read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    attempts = [event.get("data") for event in events if isinstance(event, Mapping) and event.get("event_type") == "http_attempt"]
    if not attempts:
        raise ValueError("Sealed Nous catalog/usage evidence lacks a provider attempt")
    for attempt in attempts:
        body = attempt.get("response_body") if isinstance(attempt, Mapping) else None
        usage = body.get("usage") if isinstance(body, Mapping) else None
        costs = usage.get("cost_details") if isinstance(usage, Mapping) else None
        if (
            not isinstance(attempt, Mapping) or attempt.get("status") != 200 or not isinstance(body, Mapping)
            or body.get("model") != "stealth/ox-alpha" or not isinstance(usage, Mapping) or usage.get("cost") != 0
            or not isinstance(costs, Mapping) or any(not isinstance(costs.get(key), (int, float)) or isinstance(costs.get(key), bool) or costs.get(key) != 0 for key in ("upstream_inference_completions_cost", "upstream_inference_cost", "upstream_inference_prompt_cost"))
            or _has_structured_billing_signal(body)
        ):
            raise ValueError("Sealed Nous catalog/usage evidence records cost, charge, payment, or model drift")
    return {"path": str(proof.resolve()), "fingerprint": fingerprint(proof), "catalog": {"root": str(catalog_root), "manifest": fingerprint(catalog_root / "manifest.json"), "events": fingerprint(catalog_root / "events.jsonl"), "receipt": fingerprint(catalog_root / "receipt.json"), "sealed_at": catalog_receipt["sealed_at"]}, "usage": {"root": str(usage_root), "manifest": fingerprint(usage_root / "manifest.json"), "events": fingerprint(usage_root / "events.jsonl"), "receipt": fingerprint(usage_root / "receipt.json"), "sealed_at": receipt["sealed_at"]}}


def _assert_fresh_at(proof: Mapping[str, Any], checked_at: str) -> None:
    try:
        checked = datetime.fromisoformat(checked_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (KeyError, ValueError) as exc:
        raise ValueError("Ox Alpha zero-cost freshness record is malformed") from exc
    for section in ("catalog", "usage"):
        try: sealed = datetime.fromisoformat(str(proof[section]["sealed_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError) as exc: raise ValueError("Ox Alpha zero-cost freshness record is malformed") from exc
        age = (checked - sealed).total_seconds()
        if age < 0 or age > 86_400: raise ValueError("Sealed Nous catalog/usage evidence was not fresh at preparation")


def freeze_work(primary_work: Path, gpt_output: Path, zero_cost_proof: Path, work: Path) -> dict[str, Any]:
    path = work / "frozen-ox-alpha-contract.json"
    if path.exists():
        raise ValueError("Refusing to overwrite a frozen Ox Alpha work contract")
    _external_separate(primary_work, gpt_output, zero_cost_proof, work)
    frozen, _ = _primary(primary_work)
    cells = selected_cells(primary_work)
    zero = _zero_cost_proof(zero_cost_proof)
    checked_at = datetime.now(timezone.utc).isoformat()
    _assert_fresh_at(zero, checked_at)
    _external_separate(
        primary_work,
        gpt_output,
        zero_cost_proof,
        Path(zero["catalog"]["root"]),
        Path(zero["usage"]["root"]),
        work,
    )
    value = {
        "format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True,
        "contract_sha256": sha(CONTRACT_PATH), "primary_work_dir": str(primary_work.resolve()),
        "primary_frozen": fingerprint(primary_work / "frozen-run-contract.json"),
        "primary_protocol": {key: frozen.get(key) for key in ("study_id", "study_contract_sha256", "runtime_sha256", "provider", "runner")},
        "primary_runtime_files": frozen.get("runtime_files"),
        "primary_question_ids_sha256": hashlib.sha256(canonical(frozen["question_ids"])).hexdigest(),
        "selection_seed": frozen.get("selection", {}).get("seed"),
        "gpt_reference": _gpt_reference(gpt_output, frozen, cells), "zero_cost_proof": {**zero, "freshness_checked_at": checked_at}, "runtime": runtime_bindings(),
        "provider": CONTRACT["provider"], "pilot": CONTRACT["runtime"], "cells": cells,
    }
    immutable_json(path, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / "frozen-ox-alpha-contract.json")
    primary = Path(str(value.get("primary_work_dir", "")))
    reference = value.get("gpt_reference")
    proof = value.get("zero_cost_proof")
    if not isinstance(reference, Mapping) or not isinstance(proof, Mapping):
        raise ValueError("Frozen Ox Alpha contract lacks its external public/cost bindings")
    current_proof = _zero_cost_proof(Path(str(proof.get("path", ""))))
    if proof != {**current_proof, "freshness_checked_at": proof.get("freshness_checked_at")}:
        raise ValueError("Frozen Nous zero-cost proof drifted")
    _assert_fresh_at(current_proof, str(proof.get("freshness_checked_at", "")))
    _external_separate(
        primary,
        Path(str(reference.get("output", ""))),
        Path(str(proof.get("path", ""))),
        Path(current_proof["catalog"]["root"]),
        Path(current_proof["usage"]["root"]),
        work,
    )
    expected = {
        "format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True,
        "contract_sha256": sha(CONTRACT_PATH), "primary_frozen": fingerprint(primary / "frozen-run-contract.json"),
        "runtime": runtime_bindings(), "provider": CONTRACT["provider"], "pilot": CONTRACT["runtime"],
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Frozen Ox Alpha contract does not bind this protocol/runtime")
    frozen, _ = _primary(primary)
    protocol = {key: frozen.get(key) for key in ("study_id", "study_contract_sha256", "runtime_sha256", "provider", "runner")}
    if (
        value.get("primary_protocol") != protocol
        or value.get("primary_runtime_files") != frozen.get("runtime_files")
        or value.get("primary_question_ids_sha256") != hashlib.sha256(canonical(frozen["question_ids"])).hexdigest()
        or value.get("selection_seed") != frozen.get("selection", {}).get("seed")
        or value.get("cells") != selected_cells(primary)
    ):
        raise ValueError("Frozen Ox Alpha selection or primary binding drifted")
    if reference != _gpt_reference(Path(str(reference.get("output", ""))), frozen, value["cells"]):
        raise ValueError("Frozen GPT paired reference hashes drifted")
    return value


def input_folder(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> Path:
    folder = Path(str(frozen["primary_work_dir"])) / "inputs" / "development" / str(cell["item_id"])
    if {name: fingerprint(folder / name) for name in cell["inputs"]} != cell["inputs"]:
        raise ValueError("Ox Alpha cell input bytes drifted")
    return folder
