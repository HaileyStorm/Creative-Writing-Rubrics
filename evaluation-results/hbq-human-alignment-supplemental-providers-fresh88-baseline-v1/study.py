"""Analysis-only, manifest-bound Fresh88/Grok comparison successor."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
ANALYZER_PATH = HERE / "analyze.py"
GENERIC_VERIFIER_PATH = HERE.parent / "hbq-human-alignment-supplemental-providers-verifier-v2" / "analyze_study.py"
GENERIC_VERIFIER_SHA256 = "01058c5a92694129d035d5c2f08dd15815dd9cca3450d482eea4ba9a11cd0afa"
PRIMARY_ID = "hbq-human-alignment-v3-fresh88-analysis-v1"
GROK_ID = "grok_4_6_high"
RATING_DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
BOOTSTRAP_SEED = 560820 + 901
BOOTSTRAP_DRAWS = 1000


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_binding(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256_path(path)}


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Successor runtime path is outside the repository") from exc


def _runtime_paths() -> dict[str, Path]:
    return {"analyzer": ANALYZER_PATH, "study": Path(__file__), "contract": CONTRACT_PATH}


def _runtime_bindings() -> dict[str, dict[str, Any]]:
    return {name: {"relative_path": _relative_path(path), **file_binding(path)} for name, path in _runtime_paths().items()}


def _require_committed_clean_runtime() -> dict[str, dict[str, Any]]:
    paths = _runtime_paths()
    relative = [_relative_path(path) for path in paths.values()]
    tracked = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "ls-files", "--error-unmatch", *relative], capture_output=True)
    clean = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "diff", "--quiet", "--", *relative], capture_output=True)
    if tracked.returncode != 0 or clean.returncode != 0:
        raise ValueError("Successor runtime must be committed and clean before analysis")
    for path, item in zip(paths.values(), relative):
        expected = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "show", f"HEAD:{item}"], capture_output=True)
        if expected.returncode != 0 or expected.stdout != path.read_bytes():
            raise ValueError("Successor runtime does not match checked-in source identity")
    return _runtime_bindings()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-fresh88-baseline-v1":
        raise ValueError("Fresh88/Grok successor identity drifted")
    if value.get("status") != "analysis_only_preregistered":
        raise ValueError("Fresh88/Grok successor must remain analysis-only")
    if value.get("comparison", {}).get("bootstrap_seed") != BOOTSTRAP_SEED or value.get("comparison", {}).get("required_hanna_metrics") != list(RATING_DIMENSIONS):
        raise ValueError("Fresh88/Grok comparison contract drifted")
    return value


CONTRACT = load_contract()


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be a finite number")
    return number


def _read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Fresh88 items output is invalid JSONL") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Fresh88 items output must contain objects")
    return rows


def _exact_file_bindings(manifest: Mapping[str, Any], output: Path) -> None:
    expected = {name: file_binding(output / name) for name in ("summary.json", "items.jsonl")}
    if manifest.get("files") != expected:
        raise ValueError("Fresh88 primary manifest does not bind exactly its summary and items")


def load_primary(primary_output: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    primary_output = primary_output.resolve()
    summary_path, items_path, manifest_path = (primary_output / name for name in ("summary.json", "items.jsonl", "manifest.json"))
    if not all(path.is_file() for path in (summary_path, items_path, manifest_path)):
        raise ValueError("Fresh88 primary output requires summary.json, items.jsonl, and manifest.json")
    summary, rows, manifest = read_json(summary_path), _read_rows(items_path), read_json(manifest_path)
    if summary.get("format_version") != 1 or summary.get("study_id") != PRIMARY_ID or summary.get("analysis_kind") != "offline_primary_development_analysis" or summary.get("item_count") != 88:
        raise ValueError("Fresh88 primary summary identity or item count drifted")
    evidence = summary.get("evidence_binding")
    if manifest.get("format_version") != 1 or manifest.get("study_id") != PRIMARY_ID or set(manifest) != {"format_version", "study_id", "analysis_contract_sha256", "summary_evidence_binding_sha256", "files"}:
        raise ValueError("Fresh88 primary manifest identity drifted")
    _exact_file_bindings(manifest, primary_output)
    if not isinstance(evidence, Mapping) or not evidence.get("analysis_contract_sha256"):
        raise ValueError("Fresh88 primary summary lacks its evidence binding")
    if manifest["analysis_contract_sha256"] != evidence["analysis_contract_sha256"] or manifest["summary_evidence_binding_sha256"] != hashlib.sha256(canonical(evidence)).hexdigest():
        raise ValueError("Fresh88 primary manifest does not bind its exact evidence contract")
    generated = summary.get("primary_generated_only")
    dimensions = generated.get("dimensions") if isinstance(generated, Mapping) else None
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(RATING_DIMENSIONS):
        raise ValueError("Fresh88 primary summary lacks the six HANNA metrics")
    required = {"item_id", "story_id", "execution_ordinal", "selection_ordinal", "source_model", "quartile", "prompt_group_id", "story_sha256", "prompt_sha256", "human_ratings", "human_means", "human_overall", "hbq_full_observed_score", "hbq_mapping", "evidence"}
    if len(rows) != 88 or any(set(row) != required for row in rows):
        raise ValueError("Fresh88 primary rows do not match the frozen public schema")
    ordered = sorted(rows, key=lambda row: row["execution_ordinal"])
    if [row["execution_ordinal"] for row in ordered] != list(range(1, 89)):
        raise ValueError("Fresh88 primary execution order is not canonical")
    ids = [row["item_id"] for row in ordered]
    if len(set(ids)) != 88 or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("Fresh88 primary item identities are malformed")
    for row in ordered:
        if not isinstance(row["prompt_group_id"], str) or not row["prompt_group_id"]:
            raise ValueError("Fresh88 primary prompt group is malformed")
        _finite(row["hbq_full_observed_score"], "Fresh88 score")
        if not isinstance(row["hbq_mapping"], Mapping) or set(row["hbq_mapping"]) != set(RATING_DIMENSIONS):
            raise ValueError("Fresh88 primary row lacks six HANNA mappings")
    return summary, ordered, manifest


def _load_generic(verifier_path: Path | None = None) -> Any:
    verifier_path = (verifier_path or GENERIC_VERIFIER_PATH).resolve()
    if sha256_path(verifier_path) != GENERIC_VERIFIER_SHA256:
        raise ValueError("Generic verifier-v2 bytes drifted")
    spec = importlib.util.spec_from_file_location("fresh88_grok_generic_verifier_v2", verifier_path)
    if spec is None or spec.loader is None:
        raise ValueError("Generic verifier-v2 is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _grok_reasoning_provenance(grok_work: Path, selected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    attestation = "not_reported_by_grok_build_cli"
    count = 0
    for selection in selected:
        item_id = selection.get("item_id")
        if not isinstance(item_id, str):
            raise ValueError("Historical Grok selection item is malformed")
        response_root = grok_work / "runs" / GROK_ID / "development" / item_id / "run-01" / "responses"
        checkpoints = sorted(response_root.glob("batch-[0-9][0-9][0-9][0-9].json"))
        if len(checkpoints) != 6:
            raise ValueError("Historical Grok run lacks its six accepted checkpoints")
        for checkpoint in checkpoints:
            provider = read_json(checkpoint).get("provider")
            if not isinstance(provider, Mapping) or provider.get("reasoning_attested") is not False or provider.get("reasoning_attestation") != attestation:
                raise ValueError("Historical Grok reasoning attestation provenance drifted")
            count += 1
    if count != 528:
        raise ValueError("Historical Grok reasoning provenance does not cover all 528 checkpoints")
    return {"accepted_checkpoint_count": count, "reasoning_attested": False, "reasoning_attestation": attestation, "attestation_counts": {attestation: count}}


def verify_grok_corpus(grok_work: Path, verifier_output: Path, primary_rows: Sequence[Mapping[str, Any]], *, generic_verifier_path: Path | None = None) -> tuple[dict[str, float], dict[str, Any]]:
    """Verify all historical Grok runs before reordering only their public scores."""
    verifier_path = (generic_verifier_path or GENERIC_VERIFIER_PATH).resolve()
    verifier = _load_generic(verifier_path)
    grok_work = grok_work.resolve()
    manifest_path = verifier_output.resolve() / "verification-manifest.json"
    verifier_manifest = verifier.verify_verification_manifest(grok_work, GROK_ID, "development", verifier_output.resolve())
    corpus = verifier_manifest.get("corpus")
    if not isinstance(corpus, Mapping) or corpus.get("provider_id") != GROK_ID or corpus.get("phase") != "development" or corpus.get("run_count") != 88 or corpus.get("checkpoint_count") != 528:
        raise ValueError("Historical Grok verifier manifest does not bind the completed corpus")
    frozen = verifier.load_frozen(grok_work)
    partitions = frozen.get("selection", {}).get("partitions") if isinstance(frozen.get("selection"), Mapping) else None
    selected = partitions.get("development") if isinstance(partitions, Mapping) else None
    if not isinstance(selected, list) or len(selected) != 88:
        raise ValueError("Historical Grok generation lacks its 88-item development selection")
    by_id = {row.get("item_id"): row for row in selected if isinstance(row, Mapping)}
    primary_ids = [row["item_id"] for row in primary_rows]
    if len(by_id) != 88 or set(by_id) != set(primary_ids):
        raise ValueError("Historical Grok and Fresh88 primary do not cover the exact same 88 IDs")
    scores: dict[str, float] = {}
    for primary in primary_rows:
        item_id = str(primary["item_id"])
        selection = by_id[item_id]
        for field in ("prompt_group_id", "story_sha256", "prompt_sha256"):
            if selection.get(field) != primary.get(field):
                raise ValueError("Historical Grok selection does not match Fresh88 item metadata")
        score_path = grok_work / "runs" / GROK_ID / "development" / item_id / "run-01" / "score.json"
        score = read_json(score_path)
        final = score.get("final_score")
        scores[item_id] = _finite(final.get("observed") if isinstance(final, Mapping) else None, "Grok score")
    evidence = {"verification_manifest": file_binding(manifest_path), "generic_verifier_v2": file_binding(verifier_path), "provider_id": GROK_ID, "phase": "development", "item_count": len(scores), "receipt_session_count": corpus["checkpoint_count"], "receipt_chain_sha256": corpus["receipt_chain_sha256"], "corpus_root_sha256": corpus["root_commitment"]["sha256"], "reasoning_provenance": _grok_reasoning_provenance(grok_work, selected)}
    return scores, evidence


def paired_cluster_bootstrap(pairs: Sequence[tuple[str, float]]) -> dict[str, Any]:
    if not pairs:
        raise ValueError("Paired score delta requires at least one item")
    by_group: dict[str, list[float]] = {}
    for group, value in pairs:
        if not isinstance(group, str) or not group:
            raise ValueError("Paired score delta has an invalid prompt group")
        by_group.setdefault(group, []).append(_finite(value, "Paired score delta"))
    groups = sorted(by_group)
    randomizer = random.Random(BOOTSTRAP_SEED)
    samples = sorted(statistics.fmean(value for group in groups for value in by_group[groups[randomizer.randrange(len(groups))]]) for _ in range(BOOTSTRAP_DRAWS))
    values = [value for _, value in pairs]
    return {"statistic": "Grok HBQ observed score minus Fresh88 HBQ observed score", "cluster": "prompt_group_id", "seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS, "item_count": len(values), "estimate": statistics.fmean(values), "ci_95_low": samples[25], "ci_95_high": samples[974], "descriptive_only": True}


def _output_rows(primary_rows: Sequence[Mapping[str, Any]], grok_scores: Mapping[str, float]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for primary in primary_rows:
        item_id = str(primary["item_id"])
        if item_id not in grok_scores:
            raise ValueError("Missing verified Grok score for a Fresh88 item")
        fresh, grok = _finite(primary["hbq_full_observed_score"], "Fresh88 score"), _finite(grok_scores[item_id], "Grok score")
        records.append({"item_id": item_id, "execution_ordinal": primary["execution_ordinal"], "prompt_group_id": primary["prompt_group_id"], "fresh88_hbq_observed_score": fresh, "grok_hbq_observed_score": grok, "grok_minus_fresh88": grok - fresh})
    return records


def _public_safe(output: Path) -> None:
    forbidden = ("Worker ID", "Assignment ID", "run_id", "session_id", "responses/", "source.md", "prompt.md")
    content = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file())
    if any(value in content for value in forbidden):
        raise ValueError("Fresh88/Grok public output contains forbidden private/raw material")


def verify_output(output: Path, runtime: Mapping[str, Any]) -> dict[str, Any]:
    output = output.resolve()
    manifest = read_json(output / "manifest.json")
    if manifest.get("files") != {name: file_binding(output / name) for name in ("summary.json", "items.jsonl")}:
        raise ValueError("Fresh88/Grok output manifest file bindings drifted")
    if manifest.get("successor_runtime") != runtime:
        raise ValueError("Fresh88/Grok output manifest successor runtime binding drifted")
    _public_safe(output)
    return manifest


def analyze(primary_output: Path, grok_work: Path, verifier_output: Path, output: Path, *, generic_verifier_root: Path | None = None) -> dict[str, Any]:
    if output.exists():
        raise ValueError("Refusing to merge Fresh88/Grok analysis into an existing output")
    runtime = _require_committed_clean_runtime()
    primary_summary, primary_rows, primary_manifest = load_primary(primary_output)
    generic_path = generic_verifier_root / "evaluation-results" / "hbq-human-alignment-supplemental-providers-verifier-v2" / "analyze_study.py" if generic_verifier_root else None
    grok_scores, grok_evidence = verify_grok_corpus(grok_work, verifier_output, primary_rows, generic_verifier_path=generic_path)
    rows = _output_rows(primary_rows, grok_scores)
    delta = paired_cluster_bootstrap([(row["prompt_group_id"], row["grok_minus_fresh88"]) for row in rows])
    summary = {"format_version": 1, "study_id": CONTRACT["study_id"], "phase": "development", "item_count": 88, "canonical_order": "Fresh88 primary execution_ordinal", "fresh88_primary_hanna_metrics": {"parent_summary_sha256": file_binding(primary_output / "summary.json")["sha256"], "dimensions": list(RATING_DIMENSIONS)}, "grok_reasoning_provenance": grok_evidence["reasoning_provenance"], "paired_hbq_delta": delta, "interpretation_limits": CONTRACT["interpretation_limits"]}
    output.mkdir(parents=True)
    summary_path, rows_path = output / "summary.json", output / "items.jsonl"
    summary_path.write_bytes(canonical(summary) + b"\n")
    rows_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "phase": "development", "successor_runtime": runtime, "parents": {"fresh88_primary": {"summary": file_binding(primary_output / "summary.json"), "items": file_binding(primary_output / "items.jsonl"), "manifest": file_binding(primary_output / "manifest.json"), "identity": {"study_id": primary_manifest["study_id"], "analysis_kind": primary_summary["analysis_kind"], "analysis_contract_sha256": primary_summary["evidence_binding"]["analysis_contract_sha256"]}}, "historical_grok": grok_evidence}, "files": {"summary.json": file_binding(summary_path), "items.jsonl": file_binding(rows_path)}}
    (output / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    verify_output(output, runtime)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a verified, analysis-only Fresh88/Grok comparison.")
    parser.add_argument("--fresh88-output", required=True, type=Path)
    parser.add_argument("--grok-work", required=True, type=Path)
    parser.add_argument("--grok-verifier-manifest", required=True, type=Path)
    parser.add_argument("--generic-verifier-root", type=Path, help="clean exact-HEAD repository containing verifier-v2; needed when this checkout's verifier dependencies drift")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.fresh88_output.resolve(), args.grok_work.resolve(), args.grok_verifier_manifest.resolve(), args.output_dir.resolve(), generic_verifier_root=args.generic_verifier_root.resolve() if args.generic_verifier_root else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
