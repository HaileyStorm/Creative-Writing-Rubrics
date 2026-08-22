"""Deterministic, prose-free analysis of the accepted Ox Alpha v9 slice."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

STUDY_ID = "hbq-ox-alpha-v9-accepted-slice-v1"
V9_ID = "hbq-human-alignment-supplemental-providers-ox-alpha-v9"
ITEMS = ("hanna-827", "hanna-957", "hanna-201")
VERDICTS = ("YES", "NO", "CANNOT_ASSESS", "NOT_APPLICABLE")
EXPECTED_OX = {
    "frozen": {"bytes": 1075069, "sha256": "a1dc8faae01bf701a441fbad4a30f6114ada65ad99e7c7df88eaac570b09c21a"},
    "state": {"bytes": 200309, "sha256": "df71e16dc66a7dab061ac921586b724eaec358f72901ea10cd26e5606c9c8559"},
}
EXPECTED_GROK = {
    "hanna-201": {"bytes": 116238, "sha256": "fb08f307a2b4341625cdd8b8ddbf56172b10cf4548aa62414d3ea2e10c98aa40"},
    "hanna-827": {"bytes": 113554, "sha256": "9c75e0e1af397ef7a9c8f83b5f11093881345910c81988ea88509dceaf739185"},
    "hanna-957": {"bytes": 104914, "sha256": "dbca389a863ac365c5dc4576f17bd70cfc152324bc2d0d2e4a1fc631c9d81ef0"},
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _binding(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _assert_ordered_questions(rows: list[dict[str, Any]], expected: list[str], label: str) -> None:
    if [row.get("question_id") for row in rows] != expected:
        raise ValueError(f"{label} question order/content drifted")


def _mean(values: Iterable[float]) -> float | None:
    rows = list(values)
    return round(statistics.fmean(rows), 6) if rows else None


def _kappa(left: list[str], right: list[str]) -> float | None:
    if len(left) != len(right) or not left:
        raise ValueError("kappa inputs must be nonempty and paired")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = sum((left.count(label) / len(left)) * (right.count(label) / len(right)) for label in VERDICTS)
    return None if math.isclose(expected, 1.0) else round((observed - expected) / (1.0 - expected), 6)


def _load_reference(root: Path, item: str, kind: str) -> tuple[Path, dict[str, dict[str, Any]]]:
    path = root / "runs" / item / "verdicts.jsonl" if kind == "gpt" else root / "runs" / "grok_4_6_high" / "development" / item / "run-01" / "verdicts.jsonl"
    rows = _jsonl(path)
    if len(rows) != 179 or any(row.get("artifact_id") != item for row in rows):
        raise ValueError(f"{kind} reference for {item} is not the exact 179-leaf run")
    indexed = {str(row["question_id"]): row for row in rows}
    if len(indexed) != 179 or any(row.get("verdict") not in VERDICTS for row in rows):
        raise ValueError(f"{kind} reference for {item} has duplicate or malformed verdicts")
    return path, indexed


def _quarantine_class(row: dict[str, Any]) -> str:
    message = str(row.get("error", {}).get("message", ""))
    if "response has no text" in message:
        return "empty_provider_response"
    if "validate_judge_result" in message:
        return "malformed_provider_response"
    return "other_non_524_provider_failure"


def _bin(confidence: float) -> str:
    if confidence < 0.6:
        return "0.00-0.59"
    if confidence < 0.8:
        return "0.60-0.79"
    if confidence < 0.9:
        return "0.80-0.89"
    return "0.90-1.00"


def analyze(ox_work: Path, gpt_root: Path, grok_root: Path, input_root: Path) -> dict[str, Any]:
    frozen_path, state_path = ox_work / "frozen-ox-alpha-v9-contract.json", ox_work / "state.json"
    if _binding(frozen_path) != EXPECTED_OX["frozen"] or _binding(state_path) != EXPECTED_OX["state"]:
        raise ValueError("Ox v9 accepted-slice freeze drifted")
    frozen, state = _json(frozen_path), _json(state_path)
    if frozen.get("study_id") != V9_ID or state.get("study_id") != V9_ID or len(frozen.get("units", [])) != 135:
        raise ValueError("Ox v9 frozen contract or state identity drifted")
    units = {str(row["unit_id"]): row for row in frozen["units"]}
    histories = state.get("units")
    if set(units) != set(histories or {}):
        raise ValueError("Ox v9 state does not cover the exact frozen unit set")

    references: dict[str, dict[str, dict[str, dict[str, Any]]]] = {"gpt": {}, "grok": {}}
    reference_bindings: dict[str, dict[str, dict[str, Any]]] = {"gpt": {}, "grok": {}}
    inputs: dict[str, tuple[str, str]] = {}
    for item in ITEMS:
        unit = next(row for row in frozen["units"] if row["item_id"] == item)
        source_path, prompt_path = input_root / item / "source.md", input_root / item / "prompt.md"
        if _binding(source_path) != {key: unit["inputs"]["source.md"][key] for key in ("bytes", "sha256")}:
            raise ValueError(f"input source binding drifted for {item}")
        if _binding(prompt_path) != {key: unit["inputs"]["prompt.md"][key] for key in ("bytes", "sha256")}:
            raise ValueError(f"input prompt binding drifted for {item}")
        inputs[item] = (source_path.read_text(encoding="utf-8"), prompt_path.read_text(encoding="utf-8"))
        for kind, root in (("gpt", gpt_root), ("grok", grok_root)):
            path, rows = _load_reference(root, item, kind)
            references[kind][item] = rows
            reference_bindings[kind][item] = _binding(path)
        expected_gpt = unit["gpt_reference"]["repair1_artifacts"]["verdicts"]
        if reference_bindings["gpt"][item] != {key: expected_gpt[key] for key in ("bytes", "sha256")}:
            raise ValueError(f"GPT verdict binding drifted for {item}")
        if reference_bindings["grok"][item] != EXPECTED_GROK[item]:
            raise ValueError(f"Grok verdict binding drifted for {item}")

    accepted: list[dict[str, Any]] = []
    quarantine = Counter()
    story = {item: {"expected_leaves": 179, "accepted_units": 0, "accepted_leaves": 0, "eligible_524_units": 0, "quarantined_units": 0} for item in ITEMS}
    accepted_bindings: list[dict[str, Any]] = []
    normalization_audit_count = 0
    for unit_id, unit in units.items():
        history = histories[unit_id]
        terminal = history[-1]
        status, item = terminal.get("status"), unit["item_id"]
        if status == "eligible_524":
            story[item]["eligible_524_units"] += 1
            continue
        if status == "quarantined":
            story[item]["quarantined_units"] += 1
            quarantine[_quarantine_class(terminal)] += 1
            continue
        if status != "accepted":
            raise ValueError(f"unexpected Ox terminal status: {status}")
        attempt = int(terminal["attempt"])
        run = ox_work / "attempts" / unit_id / f"attempt-{attempt:02d}"
        verdict_path = run / "verdicts.jsonl"
        checkpoint_path = run / "responses" / "batch-0001.json"
        if _binding(verdict_path) != {key: terminal["verdicts"][key] for key in ("bytes", "sha256")}:
            raise ValueError(f"accepted Ox verdict binding drifted for {unit_id}")
        if _binding(checkpoint_path) != {key: terminal["checkpoint"][key] for key in ("bytes", "sha256")}:
            raise ValueError(f"accepted Ox checkpoint binding drifted for {unit_id}")
        rows, checkpoint = _jsonl(verdict_path), _json(checkpoint_path)
        _assert_ordered_questions(rows, unit["question_ids"], f"accepted Ox verdict in {unit_id}")
        if checkpoint.get("normalized_verdicts") != rows:
            raise ValueError(f"accepted Ox verdict order/content drifted for {unit_id}")
        normalization_audit_count += len(checkpoint.get("normalization_audit", []))
        story[item]["accepted_units"] += 1
        story[item]["accepted_leaves"] += len(rows)
        accepted_bindings.append({"unit_id": unit_id, "attempt": attempt, "verdicts": _binding(verdict_path), "checkpoint": _binding(checkpoint_path)})
        for position, row in enumerate(rows, 1):
            if row.get("artifact_id") != item or row.get("judge_id") != "nous:stealth/ox-alpha" or row.get("verdict") not in VERDICTS:
                raise ValueError(f"malformed accepted Ox verdict in {unit_id}")
            confidence = row.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ValueError(f"malformed Ox confidence in {unit_id}")
            accepted.append({**row, "unit_id": unit_id, "batch": int(unit["batch"]), "position": position})

    if len(accepted) != 327:
        raise ValueError(f"expected the frozen 327-verdict accepted slice, got {len(accepted)}")
    for values in story.values():
        values["missing_leaves"] = values["expected_leaves"] - values["accepted_leaves"]
        values["acceptance_rate"] = round(values["accepted_leaves"] / values["expected_leaves"], 6)

    agreements: dict[str, dict[str, Any]] = {}
    for kind in ("gpt", "grok"):
        left = [row["verdict"] for row in accepted]
        right = [references[kind][row["artifact_id"]][row["question_id"]]["verdict"] for row in accepted]
        agree = [a == b for a, b in zip(left, right)]
        agreements[kind] = {
            "n": len(left),
            "exact_agreement": round(sum(agree) / len(agree), 6),
            "cohen_kappa": _kappa(left, right),
            "confidence_mean_when_agree": _mean(row["confidence"] for row, same in zip(accepted, agree) if same),
            "confidence_mean_when_disagree": _mean(row["confidence"] for row, same in zip(accepted, agree) if not same),
        }

    bins: dict[str, Any] = {}
    for label in ("0.00-0.59", "0.60-0.79", "0.80-0.89", "0.90-1.00"):
        rows = [row for row in accepted if _bin(float(row["confidence"])) == label]
        bins[label] = {"n": len(rows), "mean_confidence": _mean(row["confidence"] for row in rows)}
        for kind in ("gpt", "grok"):
            bins[label][f"{kind}_agreement"] = round(sum(row["verdict"] == references[kind][row["artifact_id"]][row["question_id"]]["verdict"] for row in rows) / len(rows), 6) if rows else None

    positions: dict[str, Any] = {}
    for position in range(1, 5):
        rows = [row for row in accepted if row["position"] == position]
        positions[str(position)] = {"n": len(rows), "mean_confidence": _mean(row["confidence"] for row in rows)}
        for kind in ("gpt", "grok"):
            positions[str(position)][f"{kind}_agreement"] = round(sum(row["verdict"] == references[kind][row["artifact_id"]][row["question_id"]]["verdict"] for row in rows) / len(rows), 6) if rows else None

    quote_count = invalid_quotes = 0
    for row in accepted:
        sources = inputs[row["artifact_id"]]
        for evidence in row.get("evidence", []):
            quote = evidence.get("exact_quote")
            if quote is not None:
                quote_count += 1
                invalid_quotes += not any(quote in source for source in sources)

    binding_chain = hashlib.sha256(_canonical(accepted_bindings)).hexdigest()
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "scope": {"accepted_verdicts": len(accepted), "expected_verdicts": 537, "complete_story_scores": False, "imputation": False},
        "story_coverage": story,
        "verdict_distribution": dict(sorted(Counter(row["verdict"] for row in accepted).items())),
        "agreement": agreements,
        "confidence_bins": bins,
        "within_batch_position": positions,
        "quote_evidence": {"retained_exact_quotes": quote_count, "retained_quotes_valid": quote_count - invalid_quotes, "invalid_retained_quotes": invalid_quotes, "normalizations_to_summary": normalization_audit_count},
        "quarantine_classes": dict(sorted(quarantine.items())),
        "evidence": {
            "ox_v9_frozen_contract": _binding(frozen_path),
            "ox_v9_state": _binding(state_path),
            "accepted_unit_count": len(accepted_bindings),
            "accepted_record_chain_sha256": binding_chain,
            "gpt_verdicts": reference_bindings["gpt"],
            "grok_verdicts": reference_bindings["grok"],
        },
        "interpretation": {"reasoning_effort_note": "Ox Alpha max reasoning was requested but not provider-attested.", "successor": "Run a small clean polarity-by-batch-size (1 and 4) comparison before generalizing batching or polarity effects."},
    }


def publish(summary: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    summary_path = output / "summary.json"
    summary_path.write_bytes(_canonical(summary) + b"\n")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "files": {"summary.json": _binding(summary_path)}}
    (output / "manifest.json").write_bytes(_canonical(manifest) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ox-work", required=True, type=Path)
    parser.add_argument("--gpt-root", required=True, type=Path)
    parser.add_argument("--grok-root", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    publish(analyze(*(path.resolve() for path in (args.ox_work, args.gpt_root, args.grok_root, args.input_root))), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
