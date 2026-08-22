#!/usr/bin/env python3
"""Byte-preserving verification for historical supplemental-provider v1 runs."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from hbqrs import core as core_module
from hbqrs import paths as paths_module
from hbqrs import runner as runner_module
from hbqrs import weights as weights_module
from hbqrs.core import compile_bundle, score_bundle
from hbqrs.paths import prompts_dir
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, VALIDATION_FEEDBACK_POLICY, _json_bytes, _load_checkpoints, _question_payload, _render_prompt

HERE = Path(__file__).resolve().parent
GENERATION_ROOT = HERE.parent / "hbq-human-alignment-supplemental-providers-v1"
GENERATION_ANALYZER_PATH = GENERATION_ROOT / "analyze_study.py"
VERIFIER_RUNTIME_PATH = Path(__file__).resolve()
VERIFIER_CONTRACT_PATH = HERE / "verifier-contract.json"
REPOSITORY_ROOT = HERE.parents[1]


def _load_generation() -> tuple[Any, Any]:
    study_spec = importlib.util.spec_from_file_location("supplemental_verifier_v2_generation_study", GENERATION_ROOT / "study.py")
    if study_spec is None or study_spec.loader is None:
        raise ValueError("Historical supplemental-provider study helper is unavailable")
    study = importlib.util.module_from_spec(study_spec)
    sys.modules[study_spec.name] = study
    study_spec.loader.exec_module(study)
    analysis_spec = importlib.util.spec_from_file_location("supplemental_verifier_v2_generation_analysis", GENERATION_ANALYZER_PATH)
    if analysis_spec is None or analysis_spec.loader is None:
        raise ValueError("Historical supplemental-provider analyzer is unavailable")
    analysis = importlib.util.module_from_spec(analysis_spec)
    prior = sys.modules.get("study")
    sys.modules["study"] = study
    try:
        analysis_spec.loader.exec_module(analysis)
    finally:
        if prior is None:
            del sys.modules["study"]
        else:
            sys.modules["study"] = prior
    return study, analysis


GENERATION_STUDY, GENERATION_ANALYSIS = _load_generation()
CONTRACT = GENERATION_STUDY.CONTRACT
provider = GENERATION_STUDY.provider
primary_input = GENERATION_STUDY.primary_input
load_frozen = GENERATION_STUDY.load_frozen
VERIFIER_DEPENDENCY_PATHS = {
    "hbqrs_core": Path(core_module.__file__).resolve(),
    "hbqrs_paths": Path(paths_module.__file__).resolve(),
    "hbqrs_runner": Path(runner_module.__file__).resolve(),
    "hbqrs_weights": Path(weights_module.__file__).resolve(),
    "v1_analyzer": Path(GENERATION_ANALYSIS.__file__).resolve(),
    "v1_primary_analyzer": Path(GENERATION_ANALYSIS.PRIMARY_ANALYSIS.__file__).resolve(),
    "v1_primary_study": Path(GENERATION_ANALYSIS.PRIMARY_STUDY.__file__).resolve(),
    "v1_study": Path(GENERATION_STUDY.__file__).resolve(),
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _frozen_text(path: Path) -> str:
    value = runner_module._read_text_record(path).get("text")
    if not isinstance(value, str):
        raise ValueError(f"Frozen text input is unreadable: {path}")
    return value


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Runtime path is outside the repository: {path}") from exc


def _contract() -> dict[str, Any]:
    contract = _read(VERIFIER_CONTRACT_PATH)
    if contract.get("format_version") != 1 or contract.get("verifier_id") != "hbq-human-alignment-supplemental-providers-verifier-v2" or contract.get("algorithm") != "historical_generation_v1_raw_utf8_sig_verification_v1":
        raise ValueError("Verifier contract is malformed")
    siblings = contract.get("required_siblings")
    if not isinstance(siblings, Mapping):
        raise ValueError("Verifier contract lacks required sibling bindings")
    for relative, expected in siblings.items():
        if not isinstance(relative, str) or not isinstance(expected, Mapping):
            raise ValueError("Verifier contract sibling binding is malformed")
        path = HERE / relative
        data = path.read_bytes()
        if set(expected) != {"bytes", "sha256"} or expected.get("bytes") != len(data) or expected.get("sha256") != hashlib.sha256(data).hexdigest():
            raise ValueError("Verifier contract sibling binding drifted")
    return contract


def _historical_blob(commit: str, relative_path: str) -> bytes:
    if Path(relative_path).as_posix() != relative_path or relative_path.startswith("../"):
        raise ValueError("Historical generation component path is unsafe")
    result = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "show", f"{commit}:{relative_path}"], capture_output=True)
    if result.returncode != 0:
        raise ValueError("Pinned historical generation source is unavailable")
    return result.stdout


def _historical_path_suffix(path: Any, relative_path: str) -> bool:
    if not isinstance(path, str):
        return False
    expected = [item for item in relative_path.replace("\\", "/").split("/") if item]
    observed = [item for item in path.replace("\\", "/").split("/") if item]
    if not expected or any(item in {".", ".."} for item in expected + observed):
        return False
    return len(observed) >= len(expected) and [item.casefold() for item in observed[-len(expected):]] == [item.casefold() for item in expected]


def _historical_component(record: Mapping[str, Any], name: str, expected: Mapping[str, Any], commit: str) -> dict[str, Any]:
    relative_path, expected_bytes, expected_sha256 = expected.get("relative_path"), expected.get("bytes"), expected.get("sha256")
    observed = record.get(name)
    if not isinstance(relative_path, str) or not isinstance(expected_bytes, int) or not isinstance(expected_sha256, str) or not isinstance(observed, Mapping) or set(observed) != {"path", "bytes", "sha256"}:
        raise ValueError("Historical generation component binding is malformed")
    if not _historical_path_suffix(observed.get("path"), relative_path) or observed.get("bytes") != expected_bytes or observed.get("sha256") != expected_sha256:
        raise ValueError("Immutable invocation generation component binding drifted")
    blob = _historical_blob(commit, relative_path)
    if len(blob) != expected_bytes or hashlib.sha256(blob).hexdigest() != expected_sha256:
        raise ValueError("Pinned historical generation component does not match its committed source")
    return {"relative_path": relative_path, "bytes": expected_bytes, "sha256": expected_sha256}


def _generation_runtime(work: Path, provider_id: str, phase: str) -> dict[str, Any]:
    contract = _contract()
    generation = contract.get("historical_generation")
    if not isinstance(generation, Mapping):
        raise ValueError("Verifier contract lacks historical generation bindings")
    key = f"{provider_id}/{phase}"
    invocations = generation.get("invocations")
    expected = invocations.get(key) if isinstance(invocations, Mapping) else None
    if not isinstance(expected, Mapping):
        raise ValueError("Verifier contract does not support this historical generation invocation")
    invocation_path = work / "invocations" / provider_id / f"{phase}.json"
    frozen_path = work / "frozen-provider-contract.json"
    if not invocation_path.is_file() or not frozen_path.is_file():
        raise ValueError("Historical generation evidence is incomplete")
    raw = invocation_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected.get("sha256") or hashlib.sha256(frozen_path.read_bytes()).hexdigest() != generation.get("frozen_provider_contract_sha256"):
        raise ValueError("Historical invocation or frozen provider contract hash drifted")
    record = _read(invocation_path)
    frozen = _read(frozen_path)
    providers = frozen.get("providers")
    expected_provider = generation.get("provider")
    observed_provider = next((item for item in providers if isinstance(item, Mapping) and item.get("provider_id") == provider_id), None) if isinstance(providers, list) else None
    if not isinstance(expected_provider, Mapping) or observed_provider != expected_provider:
        raise ValueError("Historical frozen provider/model settings drifted")
    settings = expected.get("settings")
    if not isinstance(settings, Mapping) or any(record.get(name) != value for name, value in settings.items()):
        raise ValueError("Historical invocation settings drifted")
    commit = generation.get("package_commit")
    components = expected.get("components")
    if not isinstance(commit, str) or not isinstance(components, Mapping) or set(components) != {"analyzer", "promotion_gate", "runner", "study", "study_runner"}:
        raise ValueError("Verifier contract historical component map is malformed")
    bound = {name: _historical_component(record, name, value, commit) for name, value in components.items() if isinstance(value, Mapping)}
    if set(bound) != set(components):
        raise ValueError("Verifier contract historical component entry is malformed")
    return {"package_commit": commit, "frozen_provider_contract_sha256": generation["frozen_provider_contract_sha256"], "invocation": {"relative_path": f"invocations/{provider_id}/{phase}.json", "sha256": expected["sha256"]}, "components": bound}


def receipt(run: Path, record: Mapping[str, Any], expected: Mapping[str, Any]) -> str:
    return GENERATION_ANALYSIS.receipt(run, record, expected)


def verify_run(work: Path, frozen: Mapping[str, Any], provider_id: str, phase: str, selection: Mapping[str, Any], repetition: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    item = provider(provider_id)
    folder, _ = primary_input(frozen, phase, str(selection["item_id"]))
    run = work / "runs" / provider_id / phase / str(selection["item_id"]) / f"run-{repetition:02d}"
    manifest, score = _read(run / "run.json"), _read(run / "score.json")
    config = manifest.get("configuration")
    if manifest.get("format_version") != 3 or not isinstance(config, Mapping) or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(config)).hexdigest():
        raise ValueError("Provider manifest-v3 is malformed or unbound")
    task_contract = _read(folder / "task-contract.json")
    modules, bundle, rows, ids, default_weight = GENERATION_ANALYSIS._expected_rows(task_contract)
    expected_inputs = frozen["input_commitments"]["development" if phase in {"development", "repeatability"} else "confirmatory"][str(selection["item_id"])]
    required = {
        "artifact": expected_inputs["source.md"], "contexts": [expected_inputs["prompt.md"]], "task_contract": expected_inputs["task-contract.json"],
        "bundle_id": "prose.short_story", "question_ids": ids, "provider": item["provider"], "model": item["model"], "reasoning": item["reasoning"],
        "batch_size": 32, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY,
        "artifact_id": selection["item_id"], "judge_id": f"{item['provider']}:{item['model']}", "strict_ai": False, "allow_unattested_reasoning": True,
    }
    compact = GENERATION_ANALYSIS._compact
    if compact(config.get("artifact")) != required["artifact"] or [compact(value) for value in config.get("contexts", [])] != required["contexts"] or compact(config.get("task_contract")) != required["task_contract"] or config.get("task_contract", {}).get("contract_id") != "hanna" or any(config.get(key) != value for key, value in required.items() if key not in {"artifact", "contexts", "task_contract"}):
        raise ValueError("Provider run does not exactly reuse the frozen primary inputs/settings")
    runtime = frozen.get("primary_runtime_files", {})
    binary_record = runtime.get("prompts/judge/BINARY_EVALUATION_PROMPT.md") if isinstance(runtime, Mapping) else None
    schema_record = runtime.get("schema/hbq_judge_response.schema.json") if isinstance(runtime, Mapping) else None
    if [compact(value) for value in config.get("prompts", [])] != [compact(binary_record)] or compact(config.get("response_schema")) != compact(schema_record):
        raise ValueError("Provider run prompt/schema files do not match the exact primary runtime")
    if config.get("weight_profile") != default_weight or config.get("questions_sha256") != hashlib.sha256(_json_bytes(_question_payload(rows))).hexdigest() or config.get("compiled_bundle_sha256") != hashlib.sha256(_json_bytes(compile_bundle(modules, bundle, task_contract=task_contract))).hexdigest():
        raise ValueError("Provider run weight/question binding drifted")
    source, prompt = _frozen_text(folder / "source.md"), _frozen_text(folder / "prompt.md")
    binary = _frozen_text(prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md")
    expected_prompts = [_render_prompt(binary_prompt=binary, artifact={"name": "source.md", "text": source}, contexts=[{"name": "prompt.md", "text": prompt}], bundle_id="prose.short_story", artifact_id=str(selection["item_id"]), questions=rows[offset:offset + 32]).encode("utf-8") for offset in range(0, len(rows), 32)]
    checkpoints = GENERATION_ANALYSIS._checkpoint_files(run)
    if len(checkpoints) != len(expected_prompts):
        raise ValueError("Provider run does not contain the complete frozen batch schedule")
    receipts: list[str] = []
    previous = None
    for number, (checkpoint, expected_prompt) in enumerate(zip(checkpoints, expected_prompts), 1):
        try:
            observed_prompt = gzip.decompress(checkpoint.with_suffix(".prompt.txt.gz").read_bytes())
        except (OSError, EOFError) as exc:
            raise ValueError("Provider checkpoint prompt is unreadable") from exc
        record = _read(checkpoint)
        expected_ids = ids[(number - 1) * 32:number * 32]
        if observed_prompt != expected_prompt or record.get("format_version") != 4 or record.get("batch") != number or record.get("question_ids") != expected_ids or record.get("previous_checkpoint_sha256") != previous or record.get("base_prompt_sha256") != hashlib.sha256(expected_prompt).hexdigest() or record.get("prompt_sha256") != hashlib.sha256(expected_prompt).hexdigest() or record.get("retry_policy") != {"batch_attempts": 3}:
            raise ValueError("Provider checkpoint does not bind the exact primary rendered batch bytes")
        receipts.append(receipt(run, record, item))
        previous = GENERATION_STUDY.sha(checkpoint)
    try:
        verdicts, count, _ = _load_checkpoints(run, artifact_text=source, context_texts=[prompt], batch_attempts=3, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("Provider checkpoint-v4 recovery/retry verification failed") from exc
    stored = [json.loads(line) for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if count != len(expected_prompts) or verdicts != stored or [row.get("question_id") for row in stored] != ids or len(receipts) != len(set(receipts)):
        raise ValueError("Provider verdicts or receipts are not complete and unique")
    recomputed = score_bundle(modules, bundle, stored, artifact_id=str(selection["item_id"]), task_contract=task_contract)
    recomputed["weight_profile"] = default_weight
    if recomputed != score:
        raise ValueError("Provider score does not deterministically reconstruct")
    return stored, score, receipts


def _require_committed_verifier_runtime() -> None:
    paths = [VERIFIER_RUNTIME_PATH, VERIFIER_CONTRACT_PATH, HERE / "README.md", *VERIFIER_DEPENDENCY_PATHS.values()]
    relative = [_relative_path(path) for path in paths]
    tracked = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "ls-files", "--error-unmatch", *relative], capture_output=True)
    clean = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "diff", "--quiet", "--", *relative], capture_output=True)
    if tracked.returncode != 0 or clean.returncode != 0:
        raise ValueError("Verifier runtime must be committed and clean before corpus verification")
    for path, item in zip(paths, relative):
        expected = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), "show", f"HEAD:{item}"], capture_output=True)
        if expected.returncode != 0 or expected.stdout != path.read_bytes():
            raise ValueError("Verifier runtime does not match the checked-in source identity")


def _runtime_binding(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"relative_path": _relative_path(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _tree_commitment(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError("Historical corpus root is missing")
    files = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"relative_path": root.name, "file_count": len(files), "sha256": hashlib.sha256(_json_bytes(files)).hexdigest()}


def verify_corpus(work: Path, provider_id: str, phase: str) -> dict[str, Any]:
    generation = _generation_runtime(work, provider_id, phase)
    contract = _contract()["historical_generation"]
    expected_corpus = contract.get("corpus") if isinstance(contract, Mapping) else None
    if not isinstance(expected_corpus, Mapping) or provider_id != expected_corpus.get("provider_id") or phase != expected_corpus.get("phase"):
        raise ValueError("Verifier contract does not support this historical corpus")
    frozen = load_frozen(work)
    partitions = frozen.get("selection", {}).get("partitions") if isinstance(frozen, Mapping) else None
    selected = partitions.get("development") if phase == "development" and isinstance(partitions, Mapping) else None
    if not isinstance(selected, list) or len(selected) != expected_corpus.get("run_count"):
        raise ValueError("Historical corpus does not contain the exact frozen 88-run selection")
    root = work / "runs" / provider_id / phase
    expected_paths = {root / str(row["item_id"]) / "run-01" / "run.json" for row in selected if isinstance(row, Mapping) and isinstance(row.get("item_id"), str)}
    actual_paths = set(root.glob("*/run-*/run.json")) if root.is_dir() else set()
    if len(expected_paths) != len(selected) or actual_paths != expected_paths:
        raise ValueError("Historical corpus has missing, extra, or mislocated runs")
    receipts: list[list[str]] = []
    checkpoints = 0
    for row in selected:
        run = root / str(row["item_id"]) / "run-01"
        _, _, run_receipts = verify_run(work, frozen, provider_id, phase, row, 1)
        receipts.append(run_receipts)
        checkpoints += len(GENERATION_ANALYSIS._checkpoint_files(run))
    flat_receipts = [value for row in receipts for value in row]
    if checkpoints != expected_corpus.get("checkpoint_count"):
        raise ValueError("Historical corpus does not contain the exact 528 checkpoint schedule")
    if len(flat_receipts) != len(set(flat_receipts)):
        raise ValueError("Historical corpus reuses a provider receipt")
    return {"generation_runtime": generation, "provider_id": provider_id, "phase": phase, "run_count": len(selected), "checkpoint_count": checkpoints, "receipt_chain_sha256": hashlib.sha256(_json_bytes(receipts)).hexdigest(), "root_commitment": _tree_commitment(root)}


def _manifest(work: Path, provider_id: str, phase: str) -> dict[str, Any]:
    _require_committed_verifier_runtime()
    corpus = verify_corpus(work, provider_id, phase)
    return {
        "format_version": 2,
        "verifier_id": "hbq-human-alignment-supplemental-providers-verifier-v2",
        "verifier_contract": _runtime_binding(VERIFIER_CONTRACT_PATH),
        "verifier_runtime": {"analyzer": _runtime_binding(VERIFIER_RUNTIME_PATH), "dependencies": {name: _runtime_binding(path) for name, path in sorted(VERIFIER_DEPENDENCY_PATHS.items())}},
        "corpus": corpus,
    }


def write_verification_manifest(work: Path, provider_id: str, phase: str, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("Refusing to merge verifier output into an existing path")
    manifest = _manifest(work, provider_id, phase)
    output.mkdir(parents=True)
    (output / "verification-manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def verify_verification_manifest(work: Path, provider_id: str, phase: str, output: Path) -> dict[str, Any]:
    observed = _read(output / "verification-manifest.json")
    expected = _manifest(work, provider_id, phase)
    if observed != expected:
        raise ValueError("Verification manifest does not bind the exact generation and verifier runtimes")
    return observed
