"""Build a provenance-preserving, cross-root view of the 330-cell study.

This adapter deliberately does not reconstruct ``schedule-journal.jsonl``:
the original analyzer's journal contract describes one work root, while this
study's completed cells are immutable evidence retained in several roots.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import posixpath
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ANALYZER = HERE / "analyze_study.py"
STUDY = HERE / "study.py"
V8_RUNTIME_DEFAULT = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-v8-runtime-e50dd50")
QUERY_ONLY = HERE.parent / "hbq-multisample-repeatability-v1-v8-query-only-process-adapter-v1" / "adapter.py"
QUERY_ONLY_SHA256 = "39405850d20f9963b7ea7a760441611133ecc2d6b0b3d6a26efa17af432e0b53"
CELL_COUNT = 330
MISSING_181 = {"sequence": 181, "item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "repetition": 1}
RETAINED_CORE_RELATIVE = "src/hbqrs/core.py"
GIT_RUNTIME_SOURCES = {
    "evaluation-results/hbq-multisample-repeatability-v1/study-contract.json": {"oid": "3db1cfd8e32b35c0c8c86ca4fdeed40146d02831", "transform": "identity"},
    "evaluation-results/hbq-multisample-repeatability-v1/study.py": {"oid": "f1ad4375385dfb75fbe9fe6736c6c23eaca9bb47", "transform": "identity"},
    "evaluation-results/hbq-multisample-repeatability-v1/prepare_study.py": {"oid": "fc33fb697e84814eb8bdb13436afec51554a40d1", "transform": "identity"},
    "evaluation-results/hbq-multisample-repeatability-v1/run_study.py": {"oid": "3569c2ea8170ce88df174cff6c214bb650c8dfc9", "transform": "identity"},
    "evaluation-results/hbq-multisample-repeatability-v1/analyze_study.py": {"oid": "d32b9e9e363da7fb70b11d799ad40b904a8aa841", "transform": "identity"},
    "evaluation-results/hbq-human-alignment-v3/study.py": {"oid": "dafcd49087eef15a3d42f615907a52ea390b2183", "transform": "identity"},
    "evaluation-results/hbq-human-alignment-v3/study-contract.json": {"oid": "612a523fdce2244c76e4842d5c83f31acd83a19d", "transform": "identity"},
    "evaluation-results/hbq-human-alignment-v3/run_study.py": {"oid": "b83a39283700ba0beca290a57ccd7fe6c95b45a2", "transform": "identity"},
    "evaluation-results/hbq-human-alignment-v3/analyze_study.py": {"oid": "95da2893a8dd878716a4945aa0990119e3d3b950", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v4/run_study.py": {"oid": "974e26f621a96b132720c17992251c8f01731283", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v4/analyze_study.py": {"oid": "289c5a5936ee38d355dfe2ce8fd30b9dfd7039ea", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v4/study-contract.json": {"oid": "ae9dc4cc580b7fab167fae0ecbb609b1f1a9a6fe", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v2/arms/naplan-narrative-2022.prompt.md": {"oid": "a3783aff97388c85f9c15eb18306bb3511766079", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v4/arms/naplan-narrative-2022.strict.schema.json": {"oid": "abe864b207695b07370ec6a39a3e3ada50bef11a", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v2/arms/cambridge-igcse-0500-p2-mj-2024.prompt.md": {"oid": "6b0b462f71792f522d88363b6b75d8ee3ab641ab", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v4/arms/cambridge-igcse-0500-p2-mj-2024.strict.schema.json": {"oid": "17754a04d200c7eb28dde6c483fff985ad53ac52", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v2/arms/oregon-narrative-2017.prompt.md": {"oid": "ce3b90560841e82b42c9fc8253fc7a487a15fda6", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/established-v2/arms/oregon-narrative-2017.schema.json": {"oid": "f3c2775264f17442aa107873758ff61f6f2370ea", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/arms/compact-analytic.prompt.md": {"oid": "c8e356e414ea899467cba7eec62dae743e4e5159", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/arms/compact-analytic.schema.json": {"oid": "10eb06c813516723eaf5b54f3428128a35a598e3", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/arms/holistic-anchored.prompt.md": {"oid": "13c58fb1fc538db2b8638f1cd853ce093d98f83e", "transform": "identity"},
    "evaluation-results/the-part-that-arrives-first-repeatability/arms/holistic-anchored.schema.json": {"oid": "8dec7e61e2cd5042271aaf52dd20816e6299d321", "transform": "identity"},
    "registry/all_modules.json": {"oid": "d991ebc7f28f00d7cd301a0bdce208d7d6b04974", "transform": "lf_to_crlf"},
    "bundles/all_bundles.json": {"oid": "e6dc8b31fe6709acec7d4b5dbf95c8f21c1df8d6", "transform": "lf_to_crlf"},
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": {"oid": "d2662edfccc115c6d0c4d97af82a10c9e926b853", "transform": "identity"},
    "prompts/judge/JUDGE_PREFIX.md": {"oid": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e", "transform": "lf_to_crlf"},
    "schema/hbq_judge_response.schema.json": {"oid": "1034a35dcd6c30a75101f369627d60e155d65c2c", "transform": "identity"},
    "schema/hbq_score_report.schema.json": {"oid": "2d08e4a42af6b9b9b2bf5845f9df1a5a4db81094", "transform": "lf_to_crlf"},
    "src/hbqrs/runner.py": {"oid": "80780321485df23e741ee414aa799c011f769e3a", "transform": "identity"},
    "src/hbqrs/longform_runner.py": {"oid": "5c46a564bf50daf31e6c7d8aa19b75b0f77c2cc0", "transform": "identity"},
    "src/hbqrs/weights.py": {"oid": "5b0a59489d03a8b2f7a7b7647a59ac4d97913071", "transform": "identity"},
    "src/hbqrs/__init__.py": {"oid": "69e4844d594cd92419528fc024493508ae7542e1", "transform": "identity"},
    "src/hbqrs/paths.py": {"oid": "4950dd03104189a93c2e9d23cd2d98315be1a31a", "transform": "lf_to_crlf"},
}
SUPPORT_FILES = {
    "src/hbqrs/longform.py": {
        "oid": "95c0c540cd9f6ec1d874f3c1fa0db3b439455cec",
        "sha256": "de8db9bba3ddf332646facaa63e57c46afb70e3eb8d47bdaa5b50fe788b6f016",
        "bytes": 78971,
        "transform": "identity",
        "purpose": "longform_runner import closure",
    },
    "src/hbqrs/scoring_v2.py": {
        "oid": "228885e8ca2ec71913c52cd67b1c62da744808f5",
        "sha256": "80592c5ffb5972ad391bd5e870da8311c888307081e5eed86c9b160b69148049",
        "bytes": 8227,
        "transform": "identity",
        "purpose": "longform scoring import closure",
    },
    "evaluation-results/hbq-human-alignment-v2/study.py": {
        "oid": "b3c1a6c809774c75eccc28eee342c97e66d050b0",
        "sha256": "ffacff20b4b267bc13eccf826b33138a23b24a0c5b1b15a563899c15604e9a42",
        "bytes": 18838,
        "transform": "identity",
        "purpose": "HANNA v3 compatibility core",
    },
    "evaluation-results/hbq-human-alignment-v2/study-contract.json": {
        "oid": "545a01bc331508fdcb01f803c85ec10839097efe",
        "sha256": "9ec0aa16f0d3bc4d8f2d06e45c9a96a27bf9ba9ea9ca8719b8163eaab1d18ece",
        "bytes": 2820,
        "transform": "identity",
        "purpose": "HANNA v3 compatibility-contract binding",
    },
    "schema/hbq_verdict.schema.json": {
        "oid": "d11fbcfa0c98865b75d246dd5e2bedac149cebb8",
        "sha256": "5cd3dd25ce506689e75cbc290620a2f22198c8f9581a5fa7bd3debe90237f3f4",
        "bytes": 3482,
        "transform": "identity",
        "purpose": "HBQ checkpoint replay verdict schema",
    },
}
LEGACY_ACCEPTED_CHECKPOINT_GLOB = 'checkpoints = sorted((path / "responses").glob("batch-*.json"))'
EXACT_ACCEPTED_CHECKPOINT_GLOB = 'checkpoints = sorted((path / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"JSONL has a partial tail: {path}")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSONL: {path}") from exc
        if not isinstance(value, dict):
            raise TypeError(f"JSONL record is not an object: {path}")
        rows.append(value)
    return rows


def _is_reparse(path: Path) -> bool:
    try:
        return bool(path.lstat().st_file_attributes & 0x400)
    except AttributeError:
        return path.is_symlink()


def _plain_tree(root: Path, label: str) -> Path:
    root = root.absolute()
    if not root.is_dir():
        raise ValueError(f"{label} is missing or not a directory: {root}")
    for path in [root, *root.rglob("*")]:
        if _is_reparse(path):
            raise ValueError(f"{label} contains a symlink/reparse point: {path}")
    return root


def _fresh_output(output: Path, roots: list[Path]) -> Path:
    output = output.absolute()
    if output.exists():
        raise ValueError("Refusing to merge into or overwrite consolidation output")
    parent = output.parent
    if not parent.is_dir():
        raise ValueError("Consolidation output parent is unavailable or redirected")
    probe = parent
    while True:
        if _is_reparse(probe):
            raise ValueError("Consolidation output ancestry contains a symlink/reparse point")
        if probe.parent == probe:
            break
        probe = probe.parent
    for root in roots:
        if output == root or output in root.parents or root in output.parents:
            raise ValueError("Consolidation output must be disjoint from immutable evidence roots")
    return output


def _runtime_manifest(original_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    frozen = _json(original_root / "frozen-run-contract.json")
    rows = frozen.get("runtime_files")
    if not isinstance(rows, list) or len(rows) != 34:
        raise ValueError("Original frozen contract lacks its exact 34-file runtime manifest")
    if frozen.get("runtime_sha256") != hashlib.sha256(_canonical(rows)).hexdigest():
        raise ValueError("Original frozen runtime manifest commitment drifted")
    manifest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"bytes", "path", "sha256"} or not isinstance(row["path"], str) or not isinstance(row["bytes"], int) or not isinstance(row["sha256"], str):
            raise ValueError("Original frozen runtime manifest record is malformed")
        relative = posixpath.normpath(row["path"])
        if "\\" in relative or relative.startswith("../") or relative == "." or Path(relative).is_absolute() or relative in manifest:
            raise ValueError("Original frozen runtime manifest path is unsafe or duplicated")
        manifest[relative] = dict(row)
    if set(manifest) != {*GIT_RUNTIME_SOURCES, RETAINED_CORE_RELATIVE}:
        raise ValueError("Original frozen runtime manifest does not match the reviewed reconstruction inventory")
    return frozen, manifest


def _git_blob(oid: str, git_blob_reader: Callable[[str], bytes] | None) -> bytes:
    if git_blob_reader is not None:
        value = git_blob_reader(oid)
        if not isinstance(value, bytes):
            raise TypeError("Injected Git blob reader did not return bytes")
        return value
    try:
        return subprocess.run(["git", "cat-file", "blob", oid], cwd=HERE.parent.parent, check=True, capture_output=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Cannot read required local Git blob {oid}") from exc


def _reconstruction_bytes(raw: bytes, transform: str) -> bytes:
    if transform == "identity":
        return raw
    if transform == "lf_to_crlf":
        return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    raise ValueError("Reconstruction transform is not reviewed")


def reconstruct_original_analysis_runtime(
    *,
    output_root: Path,
    original_root: Path,
    historical_core_root: Path,
    git_blob_reader: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    """Derive a hash-checked analysis runtime; it is not a historic execution root."""
    original_root = _plain_tree(Path(original_root), "Original evidence")
    historical_core_root = _plain_tree(Path(historical_core_root), "Retained historical core snapshot")
    repository_root = _plain_tree(HERE.parent.parent, "CWR repository")
    frozen, manifest = _runtime_manifest(original_root)
    core_path = historical_core_root / RETAINED_CORE_RELATIVE
    if not core_path.is_file() or _is_reparse(core_path):
        raise ValueError("Retained historical core snapshot is missing or redirected")
    assembled: list[tuple[str, bytes, dict[str, Any]]] = []
    for relative, expected in sorted(manifest.items()):
        if relative == RETAINED_CORE_RELATIVE:
            value = core_path.read_bytes()
            provenance = {"source_kind": "retained_historical_snapshot", "source_path": str(core_path), "source_sha256": _sha(core_path), "transform": "identity"}
        else:
            source = GIT_RUNTIME_SOURCES[relative]
            raw = _git_blob(source["oid"], git_blob_reader)
            value = _reconstruction_bytes(raw, source["transform"])
            provenance = {"source_kind": "local_git_blob", "git_blob_oid": source["oid"], "blob_sha256": hashlib.sha256(raw).hexdigest(), "transform": source["transform"]}
        if len(value) != expected["bytes"] or hashlib.sha256(value).hexdigest() != expected["sha256"]:
            raise ValueError(f"Reconstructed runtime bytes do not match the original frozen manifest: {relative}")
        assembled.append((relative, value, {"path": relative, "bytes": len(value), "sha256": expected["sha256"], **provenance}))
    support: list[tuple[str, bytes, dict[str, Any]]] = []
    for relative, expected in sorted(SUPPORT_FILES.items()):
        if relative in manifest:
            raise ValueError("Derived analysis support overlaps the original frozen runtime manifest")
        raw = _git_blob(expected["oid"], git_blob_reader)
        value = _reconstruction_bytes(raw, expected["transform"])
        if len(value) != expected["bytes"] or hashlib.sha256(value).hexdigest() != expected["sha256"]:
            raise ValueError(f"Derived analysis support bytes drifted: {relative}")
        support.append(
            (
                relative,
                value,
                {
                    "path": relative,
                    "bytes": len(value),
                    "sha256": expected["sha256"],
                    "purpose": expected["purpose"],
                    "source_kind": "local_git_blob",
                    "git_blob_oid": expected["oid"],
                    "blob_sha256": hashlib.sha256(raw).hexdigest(),
                    "transform": expected["transform"],
                },
            )
        )
    output_root = _fresh_output(Path(output_root), [original_root, historical_core_root, repository_root])
    output_root.mkdir(parents=False)
    for relative, value, _provenance in [*assembled, *support]:
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    provenance = {
        "format_version": 1,
        "kind": "derived_exact_byte_analysis_runtime",
        "original_frozen_contract": {"path": str(original_root / "frozen-run-contract.json"), "sha256": _sha(original_root / "frozen-run-contract.json"), "runtime_sha256": frozen.get("runtime_sha256")},
        "not_a_single_historical_git_snapshot": True,
        "not_an_original_execution_root": True,
        "files": [record for _relative, _value, record in assembled],
        "support_files_are_not_part_of_original_runtime_manifest": True,
        "support_files": [record for _relative, _value, record in support],
    }
    _write_json(output_root / "reconstruction-provenance.json", provenance)
    if [_sha(output_root / relative) for relative, _value, _provenance in assembled] != [record["sha256"] for _relative, _value, record in assembled]:
        raise ValueError("Published reconstructed runtime bytes drifted")
    if [_sha(output_root / relative) for relative, _value, _provenance in support] != [record["sha256"] for _relative, _value, record in support]:
        raise ValueError("Published derived analysis support bytes drifted")
    return {"format_version": 1, "status": "derived_exact_manifest", "output_root": str(output_root), "provenance_path": str(output_root / "reconstruction-provenance.json"), "runtime_sha256": frozen.get("runtime_sha256"), "file_count": len(assembled), "support_file_count": len(support)}


class _SplitWork:
    """Route original inputs and one immutable evidence root without copying either."""

    def __init__(self, inputs_root: Path, runs_root: Path) -> None:
        self._inputs_root = inputs_root
        self._runs_root = runs_root

    def __truediv__(self, part: str) -> Path:
        if part == "inputs":
            return self._inputs_root / part
        if part == "runs":
            return self._runs_root / part
        raise ValueError(f"Unexpected original-analyzer work path segment: {part!r}")


def _verify_analysis_runtime(runtime_root: Path, original_root: Path) -> None:
    """Bind the imported derived closure to its authenticated 34-file source manifest."""
    frozen, manifest = _runtime_manifest(original_root)
    provenance = _json(runtime_root / "reconstruction-provenance.json")
    if (
        provenance.get("kind") != "derived_exact_byte_analysis_runtime"
        or provenance.get("not_an_original_execution_root") is not True
        or provenance.get("support_files_are_not_part_of_original_runtime_manifest") is not True
    ):
        raise ValueError("Derived original analysis runtime provenance is not the reviewed reconstruction format")
    original_binding = provenance.get("original_frozen_contract")
    if (
        not isinstance(original_binding, Mapping)
        or original_binding.get("sha256") != _sha(original_root / "frozen-run-contract.json")
        or original_binding.get("runtime_sha256") != frozen.get("runtime_sha256")
    ):
        raise ValueError("Derived original analysis runtime does not bind the selected original frozen contract")

    def records(rows: Any, expected: Mapping[str, Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
        if not isinstance(rows, list) or len(rows) != len(expected) or not all(isinstance(row, Mapping) for row in rows):
            raise ValueError(f"Derived original analysis runtime {label} provenance is incomplete")
        by_path = {row.get("path"): row for row in rows}
        if len(by_path) != len(rows) or set(by_path) != set(expected):
            raise ValueError(f"Derived original analysis runtime {label} provenance paths drifted")
        for relative, expected_row in expected.items():
            row = by_path[relative]
            path = runtime_root / relative
            if (
                row.get("bytes") != expected_row["bytes"]
                or row.get("sha256") != expected_row["sha256"]
                or not path.is_file()
                or _is_reparse(path)
                or path.stat().st_size != expected_row["bytes"]
                or _sha(path) != expected_row["sha256"]
            ):
                raise ValueError(f"Derived original analysis runtime {label} bytes drifted: {relative}")
        return by_path

    files = records(provenance.get("files"), manifest, "original-manifest")
    for relative, expected in manifest.items():
        if relative == RETAINED_CORE_RELATIVE:
            continue
        if files[relative].get("source_kind") != "local_git_blob" or files[relative].get("git_blob_oid") != GIT_RUNTIME_SOURCES[relative]["oid"] or files[relative].get("transform") != GIT_RUNTIME_SOURCES[relative]["transform"]:
            raise ValueError(f"Derived original analysis runtime original-manifest provenance drifted: {relative}")
    core = files[RETAINED_CORE_RELATIVE]
    if core.get("source_kind") != "retained_historical_snapshot" or core.get("transform") != "identity":
        raise ValueError("Derived original analysis runtime retained-core provenance drifted")
    support = records(provenance.get("support_files"), SUPPORT_FILES, "support")
    for relative, expected in SUPPORT_FILES.items():
        row = support[relative]
        if (
            row.get("purpose") != expected["purpose"]
            or row.get("source_kind") != "local_git_blob"
            or row.get("git_blob_oid") != expected["oid"]
            or row.get("blob_sha256") != expected["sha256"]
            or row.get("transform") != expected["transform"]
        ):
            raise ValueError(f"Derived original analysis runtime support provenance drifted: {relative}")


def _derived_analyzer_source(analyzer_path: Path) -> str:
    source = analyzer_path.read_text(encoding="utf-8")
    if source.count(LEGACY_ACCEPTED_CHECKPOINT_GLOB) != 1 or EXACT_ACCEPTED_CHECKPOINT_GLOB in source:
        raise ValueError("Original analyzer accepted-checkpoint enumeration is not the reviewed legacy form")
    return source.replace(LEGACY_ACCEPTED_CHECKPOINT_GLOB, EXACT_ACCEPTED_CHECKPOINT_GLOB)


def _load_frozen_analyzer(runtime_root: Path) -> Any:
    """Load an in-memory, filename-compatible derivation of the original analyzer."""
    runtime_root = _plain_tree(runtime_root, "Derived original analysis runtime")
    analyzer_path = runtime_root / ANALYZER.relative_to(HERE.parent.parent)
    study_path = runtime_root / STUDY.relative_to(HERE.parent.parent)
    source_root = runtime_root / "src"
    if not analyzer_path.is_file() or not study_path.is_file() or not source_root.is_dir():
        raise ValueError("Derived original analysis runtime lacks the original analyzer or its source package")
    if _sha(analyzer_path) != _sha(ANALYZER) or _sha(study_path) != _sha(STUDY):
        raise ValueError("Derived original analysis runtime analyzer/study bytes drift from this adapter's pinned source")
    sys.path.insert(0, str(source_root))
    try:
        for name in tuple(sys.modules):
            if name == "hbqrs" or name.startswith("hbqrs."):
                sys.modules.pop(name, None)
        if "study" in sys.modules:
            sys.modules.pop("study")
        study_spec = importlib.util.spec_from_file_location("study", study_path)
        analyzer_spec = importlib.util.spec_from_file_location("consolidated_original_analyzer", analyzer_path)
        if study_spec is None or study_spec.loader is None or analyzer_spec is None or analyzer_spec.loader is None:
            raise RuntimeError("Cannot load frozen original analyzer")
        study = importlib.util.module_from_spec(study_spec)
        sys.modules["study"] = study
        study_spec.loader.exec_module(study)
        analyzer = importlib.util.module_from_spec(analyzer_spec)
        source = _derived_analyzer_source(analyzer_path)
        # The exact pinned source is byte-checked; this in-memory one-token derivation avoids mutating evidence.
        exec(compile(source, str(analyzer_path), "exec"), analyzer.__dict__)  # noqa: S102
        return analyzer
    finally:
        sys.path.remove(str(source_root))


def _v8_runtime_dir(runtime_root: Path) -> Path:
    directory = runtime_root / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8"
    if not (directory / "executor.py").is_file():
        raise ValueError("Frozen V8 runtime lacks the pinned executor directory")
    return directory


def _load_frozen_successor_normalizer(runtime_root: Path) -> Any:
    folder = runtime_root / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1"
    path, study_path = folder / "run_successor.py", folder / "study.py"
    if not path.is_file() or not study_path.is_file():
        raise ValueError("Frozen V8 runtime lacks the successor-v1 normalization validator")
    study_spec = importlib.util.spec_from_file_location("study", study_path)
    spec = importlib.util.spec_from_file_location("consolidated_successor_v1_normalizer", path)
    if study_spec is None or study_spec.loader is None or spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen successor-v1 normalization validator")
    previous_study = sys.modules.get("study")
    study = importlib.util.module_from_spec(study_spec)
    sys.modules["study"] = study
    try:
        study_spec.loader.exec_module(study)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous_study is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous_study
    if not callable(getattr(module, "_validate_normalization", None)) or not callable(getattr(module, "_v1_runner", None)):
        raise TypeError("Frozen successor-v1 normalization validator is incomplete")
    return module


def _load_query_safe_v8(runtime_root: Path, query_binding_root: Path) -> tuple[Any, Any]:
    if not QUERY_ONLY.is_file() or _sha(QUERY_ONLY) != QUERY_ONLY_SHA256:
        raise ValueError("Pinned query-only terminal-admission adapter drifted")
    spec = importlib.util.spec_from_file_location("consolidated_v8_query_only", QUERY_ONLY)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen V8 query-only adapter")
    query = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(query)
    query._binding(query_binding_root, runtime_root)
    exact = query.load_query_only_exact_one()
    guard = exact._load_guard()
    runtime, executor = guard._canonical_runtime(runtime_root)
    v8 = guard._load_v8(executor)
    if runtime != runtime_root or not callable(getattr(v8, "_accepted", None)):
        raise ValueError("Pinned query-only terminal-admission runtime drifted")
    return guard, v8


def _verify_missing181_receipt(missing181_root: Path, runtime_root: Path) -> None:
    path = HERE.parent / "hbq-multisample-repeatability-v1-missing181-completion-v1" / "executor.py"
    spec = importlib.util.spec_from_file_location("consolidated_missing181", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load missing181 receipt validator")
    missing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(missing)
    binding = missing._binding(missing181_root)
    historical = binding.get("v7_zero_contact_settlement")
    if not isinstance(historical, Mapping):
        raise TypeError("Missing181 binding lacks its immutable V7 zero-contact settlement")
    missing._settlement(Path(str(historical.get("path", ""))))
    _guard, v8, runtime, executor = missing._load_runtime(_v8_runtime_dir(runtime_root))
    if binding.get("runtime") != {"root": str(runtime), "executor": str(executor), "executor_sha256": missing.sha(executor), "study_id": v8.contract()["study_id"]}:
        raise ValueError("Missing181 binding does not match the frozen V8 runtime")
    source = v8._external(Path(str(binding.get("source", {}).get("root", ""))))
    frozen = v8.read_json(source / "frozen-run-contract.json")
    missing._validate_original_binding(source, frozen)
    projection = binding.get("source", {}).get("runtime_projection")
    if not isinstance(projection, Mapping) or v8._runtime_projection(frozen) != projection:
        raise ValueError("Missing181 source runtime projection drifted")
    profile = binding.get("profile")
    if not isinstance(profile, Mapping):
        raise TypeError("Missing181 source provider profile is malformed")
    policy = missing._source_provider_policy(frozen, profile)
    if hashlib.sha256(missing.canonical(policy)).hexdigest() != binding.get("source", {}).get("provider_policy_sha256"):
        raise ValueError("Missing181 source provider policy commitment drifted")
    missing._assert_frozen_hbq_imports(v8, projection)
    disclosure, overrides, expected_question_ids = missing._event_and_questions(v8, source, frozen)
    question_ids = binding.get("question_ids")
    if not isinstance(question_ids, list) or question_ids != expected_question_ids or binding.get("question_ids_sha256") != hashlib.sha256(missing.canonical(question_ids)).hexdigest() or binding.get("event") != MISSING_181:
        raise ValueError("Missing181 binding does not carry the exact frozen event and question identities")
    if _json(missing181_root / missing.DISCLOSURE) != disclosure or missing.sha(missing181_root / missing.DISCLOSURE) != binding.get("disclosure_sha256") or _json(missing181_root / missing.ACKNOWLEDGEMENT) != missing._expected_ack(binding):
        raise ValueError("Missing181 acknowledgement does not bind its exact immutable disclosure")
    if len(overrides) != 1:
        raise ValueError("Missing181 has an invalid scope-compatibility override geometry")
    override = overrides[0]
    override_path = missing181_root / missing.OVERRIDES / Path(str(override["path"])).name
    if _json(override_path) != override["schema"] or missing.sha(override_path) != override["sha256"]:
        raise ValueError("Missing181 scope-compatibility override drifted")
    claim = _json(missing181_root / missing.CLAIM)
    if set(claim) != {"format_version", "study_id", "event", "binding_sha256", "capacity_evidence_sha256", "capacity_observed_at", "claim_policy"} or claim.get("format_version") != 1 or claim.get("study_id") != missing.STUDY_ID or claim.get("event") != MISSING_181 or claim.get("binding_sha256") != missing.sha(missing181_root / missing.BINDING) or claim.get("claim_policy") != "one dispatch only; retain this claim after every outcome" or not isinstance(claim.get("capacity_evidence_sha256"), str) or len(claim["capacity_evidence_sha256"]) != 64:
        raise ValueError("Missing181 immutable dispatch claim drifted")
    v8._validate_time(claim.get("capacity_observed_at"))
    output = missing._completed_output(v8, missing181_root, question_ids)
    receipt = _json(missing181_root / "normal-receipt.json")
    expected = {
        "format_version": 1,
        "study_id": missing.STUDY_ID,
        "status": "NORMAL_RECEIPT_WITH_PERSISTED_EVIDENCE",
        "event": dict(MISSING_181),
        "binding_sha256": missing.sha(missing181_root / missing.BINDING),
        "output": output,
        "attestation_limit": "Persisted attempts and unique session-bearing records are locally validated evidence, not independent provider endpoint contact proof.",
    }
    if receipt != expected:
        raise ValueError("Detached missing181 normal receipt does not fully replay its controller and raw output")


def _require_terminal_journal(v8: Any, work: Path) -> None:
    rows = _jsonl(work / v8.JOURNAL)
    completed = [row.get("sequence") for row in rows if row.get("event") == "completed"]
    if completed != list(range(183, 331)) or not rows or rows[-1].get("event") != "completed" or rows[-1].get("sequence") != 330:
        raise ValueError("V8 journal is not a terminal 183-330 completion")
    active: set[int] = set()
    contacts: set[int] = set()
    for row in rows:
        event, sequence = row.get("event"), row.get("sequence")
        if event in {"attempt-intent", "retry-intent", "retry-disclosure-pause"}:
            if not isinstance(sequence, int):
                raise ValueError("V8 journal has a malformed active sequence")
            active.add(sequence)
        elif event == "provider-contacts":
            if not isinstance(sequence, int):
                raise ValueError("V8 journal has a malformed contact sequence")
            contacts.add(sequence)
        elif event == "completed":
            active.discard(sequence)
            contacts.discard(sequence)
    if active or contacts:
        raise ValueError("V8 journal has unresolved state; terminal admission would not be query-safe")


def _terminal_admission(
    *,
    original_root: Path,
    closed_successor_root: Path,
    v7_root: Path,
    v8_root: Path,
    guard_root: Path,
    query_binding_root: Path,
    runtime_root: Path,
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    v8_runtime_root = _v8_runtime_dir(runtime_root)
    guard, v8 = _load_query_safe_v8(v8_runtime_root, query_binding_root)
    _require_terminal_journal(v8, v8_root)
    binding, schedule, admission = v8._verify_prepared(original_root, closed_successor_root, v7_root, v8_root)
    guard._assert_no_unresolved_v8_state(v8, v8_root)
    accepted = v8._accepted(v8_root, schedule, admission)
    v8._validate_contact_sessions(original_root, v8_root, admission, accepted)
    if [event.get("sequence") for event in accepted] != list(range(182, 331)) or binding.get("runtime") is None:
        raise ValueError("Pinned V8 terminal admission is incomplete")
    try:
        guard.preflight(
            source_root=original_root,
            closed_root=closed_successor_root,
            v7_root=v7_root,
            work_root=v8_root,
            guard_root=guard_root,
            v8_runtime_root=v8_runtime_root,
        )
    except ValueError as exc:
        if str(exc) != "V8 has no untouched sequence remaining":
            raise
    else:
        raise ValueError("Query-safe guard unexpectedly found a nonterminal V8 event")
    record = guard._guard_binding(guard_root)
    runtime, executor = guard._canonical_runtime(v8_runtime_root)
    if record.get("v8_identity") != guard._v8_static_identity(v8, runtime, executor, v8_root) or record.get("v8_prepared_runtime_projection") != binding.get("runtime"):
        raise ValueError("Query-safe guard binding does not match the terminal V8 admission")
    terminal_sentinel = {"sequence": -1}
    completed = guard._validate_guard_journal(guard_root, accepted, terminal_sentinel)
    guard._validate_claims(guard_root, accepted, terminal_sentinel, completed)
    if 330 not in completed or guard._recompute_contacts(v8, v8_root, accepted) < 148:
        raise ValueError("Query-safe guard does not prove all terminal V8 claims and contact topology")
    return v8, schedule, admission


def _event_key(event: Mapping[str, Any]) -> tuple[int, str, str, int]:
    sequence, item, arm, repetition = (event.get(name) for name in ("sequence", "item_id", "arm_id", "repetition"))
    if not isinstance(sequence, int) or not isinstance(item, str) or not isinstance(arm, str) or not isinstance(repetition, int):
        raise TypeError("Study event lacks a complete sequence/item/arm/repetition identity")
    return sequence, item, arm, repetition


def _frozen_events(original_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frozen = _json(original_root / "frozen-run-contract.json")
    schedule = frozen.get("schedule")
    if not isinstance(schedule, list) or len(schedule) != CELL_COUNT:
        raise ValueError("Original frozen schedule is not the required 330-cell geometry")
    events = [{"sequence": sequence, **dict(row)} for sequence, row in enumerate(schedule, 1) if isinstance(row, Mapping)]
    if len(events) != CELL_COUNT or [_event_key(event)[0] for event in events] != list(range(1, CELL_COUNT + 1)):
        raise ValueError("Original frozen schedule contains malformed events")
    if len({_event_key(event) for event in events}) != CELL_COUNT:
        raise ValueError("Original frozen schedule contains duplicate cell identities")
    return frozen, events


def _completed_prefix(path: Path, expected: list[dict[str, Any]], *, planned_count: int, completed_sequences: list[int]) -> list[dict[str, Any]]:
    rows = _jsonl(path)
    plans = [{"event": "planned", **event} for event in expected]
    if rows[:planned_count] != plans[:planned_count]:
        raise ValueError(f"Journal planned prefix drifted: {path}")
    completed = [row for row in rows[planned_count:] if row.get("event") == "completed"]
    if [row.get("sequence") for row in completed] != completed_sequences:
        raise ValueError(f"Journal completed prefix drifted: {path}")
    return completed


def _v6_and_v4_roots(v7_root: Path) -> tuple[Path, Path]:
    binding = _json(v7_root / "v7-binding.json")
    v6 = Path(str(binding.get("roots", {}).get("v6", "")))
    v6 = _plain_tree(v6, "V6 prefix evidence")
    rows = _jsonl(v6 / "execution-journal.jsonl")
    if not rows or rows[0].get("event") != "admitted-prefix" or rows[0].get("sequence") != 178:
        raise ValueError("V6 evidence does not admit the exact sequence 178 prefix")
    v4 = Path(str(rows[0].get("v4_root", "")))
    return v6, _plain_tree(v4, "V4 sequence-178 evidence")


def _run_path(root: Path, event: Mapping[str, Any], kind: str) -> Path:
    binding = "run.json" if kind == "hbq" else "pass.json"
    return root / "runs" / str(event["item_id"]) / str(event["arm_id"]) / f"run-{int(event['repetition']):02d}" / binding


def _tree_hash(root: Path) -> str:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if _is_reparse(path):
            raise ValueError(f"Run evidence contains a symlink/reparse point: {path}")
        if path.is_file():
            records.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha(path)})
    if not records:
        raise ValueError(f"Run evidence is empty: {root}")
    return hashlib.sha256(_canonical(records)).hexdigest()


def _scheduled_rows(path: Path, expected: list[dict[str, Any]], label: str) -> None:
    rows = _jsonl(path)
    if len(rows) != len(expected) or [_event_key(row) for row in rows] != [_event_key(row) for row in expected]:
        raise ValueError(f"{label} schedule does not match the frozen cell identities")


def _completed_rows(path: Path, expected_sequences: list[int], label: str) -> list[dict[str, Any]]:
    rows = _jsonl(path)
    completed = [row for row in rows if row.get("event") == "completed"]
    if [row.get("sequence") for row in completed] != expected_sequences:
        raise ValueError(f"{label} does not have the exact required completed sequence range")
    return completed


def _check_completed_bindings(
    root: Path,
    events: list[dict[str, Any]],
    completed: list[dict[str, Any]],
    arms: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    by_sequence = {event["sequence"]: event for event in events}
    for row in completed:
        sequence = row.get("sequence")
        event = by_sequence.get(sequence)
        digest = row.get("run_binding_sha256", row.get("output_sha256"))
        if event is None or not isinstance(digest, str):
            raise ValueError(f"{label} completion record is malformed")
        if any(key in row and row[key] != event[key] for key in ("item_id", "arm_id", "repetition")):
            raise ValueError(f"{label} completion record relabels its frozen event")
        arm = arms.get(str(event["arm_id"]))
        if arm is None:
            raise ValueError(f"{label} event has an unknown arm")
        binding = _run_path(root, event, str(arm["kind"]))
        if not binding.is_file() or _sha(binding) != digest:
            raise ValueError(f"{label} completion does not bind its exact raw run manifest")


def _source_map(
    *,
    original_root: Path,
    closed_successor_root: Path,
    v7_root: Path,
    missing181_root: Path,
    v8_root: Path,
    v8_schedule: list[dict[str, Any]],
    v8_admission: Mapping[str, Any],
    frozen: Mapping[str, Any],
    events: list[dict[str, Any]],
) -> tuple[dict[int, tuple[str, Path]], list[Path]]:
    arms_value = frozen.get("contract", {}).get("arms") if isinstance(frozen.get("contract"), Mapping) else None
    if not isinstance(arms_value, list):
        raise TypeError("Frozen contract lacks arm definitions")
    arms = {str(arm.get("arm_id")): arm for arm in arms_value if isinstance(arm, Mapping)}
    if len(arms) != 6:
        raise ValueError("Frozen contract arm geometry drifted")

    original_completed = _completed_prefix(original_root / "schedule-journal.jsonl", events, planned_count=CELL_COUNT, completed_sequences=list(range(1, 77)))
    _check_completed_bindings(original_root, events, original_completed, arms, "Original")
    closed_completed = _completed_prefix(closed_successor_root / "successor-schedule-journal.jsonl", events[76:], planned_count=254, completed_sequences=list(range(77, 178)))
    _check_completed_bindings(closed_successor_root, events, closed_completed, arms, "Closed successor")

    v6_root, v4_root = _v6_and_v4_roots(v7_root)
    v6_schedule = _jsonl(v6_root / "schedule.jsonl")
    if [_event_key(row) for row in v6_schedule[:2]] != [_event_key(event) for event in events[178:180]]:
        raise ValueError("V6 schedule does not bind sequences 179-180")
    v6_completed = _completed_rows(v6_root / "execution-journal.jsonl", [179, 180], "V6")
    _check_completed_bindings(v6_root, events, v6_completed, arms, "V6")

    v4_event = events[177]
    if _event_key(v4_event)[0] != 178:
        raise ValueError("Frozen schedule no longer places the V4 adoption at sequence 178")
    v4_binding = _run_path(v4_root, v4_event, str(arms[str(v4_event["arm_id"])]["kind"]))
    admitted = _jsonl(v6_root / "execution-journal.jsonl")[0]
    if not v4_binding.is_file() or admitted.get("v4_run_sha256") != _sha(v4_binding):
        raise ValueError("V4 sequence 178 admission no longer binds its raw run manifest")

    v7_schedule = _jsonl(v7_root / "schedule.jsonl")
    if len(v7_schedule) < 2 or _event_key(v7_schedule[1]) != _event_key(events[181]):
        raise ValueError("V7 schedule does not bind adopted sequence 182")
    v7_journal = _jsonl(v7_root / "execution-journal.jsonl")
    if [row.get("event") for row in v7_journal] != ["admitted-prefix", "forensic-precontact", "attempt-intent"]:
        raise ValueError("V7 immutable journal is not the sealed adopted-output state")
    v7_binding = _run_path(v7_root, events[181], str(arms[str(events[181]["arm_id"])]["kind"]))
    if not v7_binding.is_file():
        raise ValueError("Adopted V7 sequence 182 raw output is missing")

    missing_binding = _json(missing181_root / "completion-binding.json")
    missing_receipt = _json(missing181_root / "normal-receipt.json")
    if missing_binding.get("event") != MISSING_181 or missing_receipt.get("event") != MISSING_181:
        raise ValueError("Detached missing181 evidence does not identify the exact sequence 181 cell")
    if missing_receipt.get("binding_sha256") != _sha(missing181_root / "completion-binding.json"):
        raise ValueError("Detached missing181 receipt does not bind its completion controller")
    missing_path = _run_path(missing181_root, events[180], str(arms[str(events[180]["arm_id"])]["kind"]))
    output = missing_receipt.get("output")
    if not isinstance(output, Mapping) or output.get("path") != str(missing_path) or output.get("sha256") != _sha(missing_path):
        raise ValueError("Detached missing181 receipt does not bind its raw run manifest")

    _scheduled_rows(v8_root / "schedule.jsonl", events[181:], "V8")
    if [_event_key(event) for event in v8_schedule] != [_event_key(event) for event in events[181:]]:
        raise ValueError("Pinned V8 terminal schedule does not match the frozen source geometry")
    v8_rows = _jsonl(v8_root / "execution-journal.jsonl")
    if len(v8_rows) < 2 or v8_rows[0] != {"event": "admitted-prefix", **dict(v8_admission)} or v8_rows[1] != {"event": "adopted-v7-output", "sequence": 182, "settlement_sha256": v8_admission.get("settlement_sha256")}:
        raise ValueError("V8 does not retain the adopted V7 sequence 182 provenance")

    sources: dict[int, tuple[str, Path]] = {}
    for sequence in range(1, 77):
        sources[sequence] = ("original_1_76", original_root)
    for sequence in range(77, 178):
        sources[sequence] = ("closed_successor_77_177", closed_successor_root)
    sources[178] = ("adopted_v4_178", v4_root)
    sources[179] = sources[180] = ("admitted_v6_179_180", v6_root)
    sources[181] = ("missing181_detached_completion", missing181_root)
    sources[182] = ("adopted_v7_182", v7_root)
    for sequence in range(183, 331):
        sources[sequence] = ("v8_accepted_183_330", v8_root)
    if sorted(sources) != list(range(1, CELL_COUNT + 1)):
        raise ValueError("Consolidation source map is incomplete or nonunique")
    return sources, [original_root, closed_successor_root, v4_root, v6_root, v7_root, missing181_root, v8_root]


def _source_record(root: Path) -> dict[str, Any]:
    return {"path": str(root), "tree_sha256": _tree_hash(root)}


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _analysis_summary(
    analyzer: Any,
    frozen: Mapping[str, Any],
    rows_by_arm: Mapping[str, list[dict[str, Any]]],
    leaves_by_arm: Mapping[str, list[dict[str, Any]]],
    sessions: list[str | None],
    commitments: list[str],
) -> dict[str, Any]:
    arms = frozen["contract"]["arms"]
    repetitions = frozen["contract"]["repetitions"]
    summaries: dict[str, Any] = {}
    for arm in arms:
        arm_id = arm["arm_id"]
        rows = rows_by_arm[arm_id]
        leaves = leaves_by_arm[arm_id]
        macro = {key: analyzer.statistics.fmean(row[key] for row in rows) for key in ("exact_all_repetition_agreement", "modal_proportion", "pairwise_exact_agreement", "normalized_sample_sd", "normalized_mapd", "normalized_range")}
        leaf_summary = None
        if leaves:
            leaf_summary = {key: analyzer.statistics.fmean(row[key] for row in leaves) for key in ("exact_all_repetition_agreement", "mean_modal_proportion", "mean_pairwise_agreement")}
            leaf_summary["per_sample_confidence_diagnostics"] = [{"item_id": row["item_id"], **row["confidence_diagnostics"]} for row in leaves]
            leaf_summary["confidence_macro"] = {
                "mean_raw_confidence": analyzer.statistics.fmean(row["confidence_diagnostics"]["raw_confidence"]["mean_raw_confidence"] for row in leaves),
                "mean_same_input_empirical_repeat_probability": analyzer.statistics.fmean(row["confidence_diagnostics"]["same_input_empirical_repeat_probability"] for row in leaves),
                "mean_effective_confidence_mass": analyzer.statistics.fmean(row["confidence_diagnostics"]["effective_confidence_mass"] for row in leaves),
                "repeat_consensus_is_not_truth": True,
                "canonical_score_and_coverage_unchanged": True,
            }
        summaries[arm_id] = {
            "native_scale": arm["native_scale"],
            "sample_count": len(rows),
            "repetitions": repetitions,
            "equal_sample_macro": macro,
            "per_sample": rows,
            "full_sample_distributions": {row["item_id"]: row["values"] for row in rows},
            "leaf_repeatability": leaf_summary,
            "quality_sensitivity": analyzer._quality(rows, repetitions),
        }
    observed = [session for session in sessions if session is not None]
    if len(observed) != len(sessions) or len(observed) != len(set(observed)):
        raise ValueError("Consolidated fresh-session requirement failed across source roots")
    return {
        "format_version": 1,
        "study_id": frozen["study_id"],
        "analysis_kind": "cross_root_immutable_consolidation",
        "sample_count": len(frozen["samples"]),
        "prompt_cluster_count": len({sample["prompt_sha256"] for sample in frozen["samples"]}),
        "repetitions": repetitions,
        "native_scales_are_not_cross_compared": True,
        "canonical_scores_and_coverage_are_not_confidence_weighted": True,
        "frozen_full_development_quality_cutpoints": frozen["full_development_quality_cutpoints"],
        "arms": summaries,
        "paired_prompt_cluster_bootstrap": {
            "seed": frozen["contract"]["primary_metrics"]["bootstrap"]["seed"],
            "draws": 10000,
            "unit": "prompt_cluster",
            "cluster_count": len({sample["prompt_sha256"] for sample in frozen["samples"]}),
            "estimand": "equal_sample_mean_paired_delta",
            "results": analyzer._bootstrap(rows_by_arm, seed=560820, draws=10000),
        },
        "fresh_session_commitment": {
            "status": "verified_unique",
            "source_record_count": len(sessions),
            "session_id_record_count": len(observed),
            "unavailable_record_count": 0,
            "unique_observed_session_count": len(set(observed)),
            "observed_session_sha256": hashlib.sha256("\n".join(sorted(observed)).encode()).hexdigest(),
            "artifact_commitment_count": len(commitments),
            "artifact_commitments_sha256": hashlib.sha256("\n".join(sorted(commitments)).encode()).hexdigest(),
        },
        "privacy": "No prose, prompts, raw HANNA ratings, or copied source artifacts are emitted into this analysis.",
    }


def _validate_native_normalizations(
    events: list[dict[str, Any]],
    sources: Mapping[int, tuple[str, Path]],
    frozen: Mapping[str, Any],
    original_root: Path,
    normalizer: Any,
    normalization_runner: Any,
) -> None:
    arms = {arm["arm_id"]: arm for arm in frozen["contract"]["arms"]}
    for event in events:
        if arms[event["arm_id"]]["kind"] != "native":
            continue
        sequence = int(event["sequence"])
        _source_kind, root = sources[sequence]
        binding = _run_path(root, event, arms[event["arm_id"]]["kind"])
        if not binding.is_file():
            raise ValueError(f"Mapped source run manifest is missing: sequence {sequence}")
        source = (original_root / "inputs" / str(event["item_id"]) / "source.md").read_text(encoding="utf-8")
        normalizer._validate_normalization(normalization_runner, binding.parent, source)


def consolidate(
    *,
    original_root: Path,
    closed_successor_root: Path,
    v7_root: Path,
    missing181_root: Path,
    v8_root: Path,
    guard_root: Path,
    query_binding_root: Path,
    output_root: Path,
    data_dir: Path,
    analysis_runtime_root: Path,
    runtime_root: Path = V8_RUNTIME_DEFAULT,
) -> dict[str, Any]:
    """Replay complete cross-root evidence into a fresh derived analysis view."""
    original_root = _plain_tree(Path(original_root), "Original evidence")
    closed_successor_root = _plain_tree(Path(closed_successor_root), "Closed-successor evidence")
    v7_root = _plain_tree(Path(v7_root), "V7 evidence")
    missing181_root = _plain_tree(Path(missing181_root), "Detached missing181 evidence")
    v8_root = _plain_tree(Path(v8_root), "V8 evidence")
    guard_root = _plain_tree(Path(guard_root), "V8 query-safe guard evidence")
    query_binding_root = _plain_tree(Path(query_binding_root), "V8 query-only binding evidence")
    runtime_root = _plain_tree(Path(runtime_root), "Frozen V8 runtime")
    analysis_runtime_root = _plain_tree(Path(analysis_runtime_root), "Derived original analysis runtime")
    data_dir = _plain_tree(Path(data_dir), "Pinned HANNA data")
    repository_root = _plain_tree(HERE.parent.parent, "CWR repository")
    normalizer = _load_frozen_successor_normalizer(runtime_root)
    normalization_runner = normalizer._v1_runner()
    frozen, events = _frozen_events(original_root)
    _verify_missing181_receipt(missing181_root, runtime_root)
    _v8, v8_schedule, v8_admission = _terminal_admission(
        original_root=original_root,
        closed_successor_root=closed_successor_root,
        v7_root=v7_root,
        v8_root=v8_root,
        guard_root=guard_root,
        query_binding_root=query_binding_root,
        runtime_root=runtime_root,
    )
    sources, all_roots = _source_map(
        original_root=original_root,
        closed_successor_root=closed_successor_root,
        v7_root=v7_root,
        missing181_root=missing181_root,
        v8_root=v8_root,
        v8_schedule=v8_schedule,
        v8_admission=v8_admission,
        frozen=frozen,
        events=events,
    )
    _validate_native_normalizations(events, sources, frozen, original_root, normalizer, normalization_runner)
    output_root = _fresh_output(Path(output_root), [*all_roots, guard_root, query_binding_root, runtime_root, analysis_runtime_root, data_dir, repository_root])
    _verify_analysis_runtime(analysis_runtime_root, original_root)
    analyzer = _load_frozen_analyzer(analysis_runtime_root)
    if analyzer.validate(original_root, data_dir) != frozen:
        raise ValueError("Original frozen study validation did not reproduce the source contract")

    arms = {arm["arm_id"]: arm for arm in frozen["contract"]["arms"]}
    samples = {sample["item_id"]: sample for sample in frozen["samples"]}
    values: dict[tuple[str, str], list[tuple[int, float, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]] = {}
    provenance_cells: list[dict[str, Any]] = []
    all_sessions: list[str | None] = []
    all_commitments: list[str] = []
    for event in events:
        sequence, item_id, arm_id, repetition = _event_key(event)
        source_kind, root = sources[sequence]
        sample, arm = samples.get(item_id), arms.get(arm_id)
        if sample is None or arm is None:
            raise ValueError("Frozen event does not resolve a unique sample and arm")
        binding = _run_path(root, event, arm["kind"])
        if not binding.is_file():
            raise ValueError(f"Mapped source run manifest is missing: sequence {sequence}")
        work = _SplitWork(original_root, root)
        score, sessions, commitments, verdicts, metadata = analyzer._load_run(work, sample, arm, repetition)
        all_sessions.extend(sessions)
        all_commitments.extend(commitments)
        values.setdefault((item_id, arm_id), []).append((repetition, score, verdicts, metadata))
        run_root = binding.parent
        provenance_cells.append(
            {
                "sequence": sequence,
                "item_id": item_id,
                "arm_id": arm_id,
                "repetition": repetition,
                "source_kind": source_kind,
                "source_root": str(root),
                "run_binding_path": str(binding),
                "run_binding_sha256": _sha(binding),
                "run_tree_sha256": _tree_hash(run_root),
                "session_ids": [session for session in sessions if session is not None],
                "artifact_commitments": commitments,
            }
        )

    if len(provenance_cells) != CELL_COUNT or len({_event_key(cell) for cell in provenance_cells}) != CELL_COUNT:
        raise ValueError("Consolidated geometry is incomplete or nonunique")
    expected_keys = {(sample["item_id"], arm["arm_id"]) for sample in frozen["samples"] for arm in frozen["contract"]["arms"]}
    if set(values) != expected_keys or any(len(rows) != 5 or [row[0] for row in sorted(rows)] != [1, 2, 3, 4, 5] for rows in values.values()):
        raise ValueError("Consolidated repetitions are incomplete or nonunique")

    rows_by_arm: dict[str, list[dict[str, Any]]] = {arm_id: [] for arm_id in arms}
    leaves_by_arm: dict[str, list[dict[str, Any]]] = {arm_id: [] for arm_id in arms}
    for arm_id, arm in arms.items():
        for sample in frozen["samples"]:
            loaded = sorted(values[(sample["item_id"], arm_id)])
            scores = [row[1] for row in loaded]
            metrics = analyzer._numeric_metrics(scores, analyzer._scale(arm_id))
            lower, upper = analyzer._scale(arm_id)
            row = {
                "item_id": sample["item_id"],
                "source_model": sample["model"],
                "prompt_sha256": sample["prompt_sha256"],
                "human_overall": sample["human_overall"],
                "frozen_quality_band": sample["frozen_quality_band"],
                **metrics,
                "normalized_values": [(score - lower) / (upper - lower) for score in scores],
                "mean_normalized_score": analyzer.statistics.fmean((score - lower) / (upper - lower) for score in scores),
            }
            rows_by_arm[arm_id].append(row)
            verdict_runs = [row[2] for row in loaded if row[2] is not None]
            if verdict_runs:
                metadata = loaded[0][3]
                if metadata is None or any(row[3] != metadata for row in loaded):
                    raise ValueError("HBQ question metadata drifted across consolidated repetitions")
                leaf = analyzer._leaf_metrics(verdict_runs, metadata)
                leaf["item_id"] = sample["item_id"]
                leaves_by_arm[arm_id].append(leaf)

    summary = _analysis_summary(analyzer, frozen, rows_by_arm, leaves_by_arm, all_sessions, all_commitments)
    source_counts = Counter(cell["source_kind"] for cell in provenance_cells)
    provenance = {
        "format_version": 1,
        "study_id": frozen["study_id"],
        "analysis_kind": "cross_root_immutable_consolidation",
        "geometry": {"expected_cells": CELL_COUNT, "observed_cells": len(provenance_cells), "unique_cell_identities": len({_event_key(cell) for cell in provenance_cells})},
        "source_kind_counts": dict(sorted(source_counts.items())),
        "missing181_not_v8_acceptance": True,
        "v8_accepted_suffix": {"first_sequence": 183, "last_sequence": 330, "count": 148},
        "source_roots": [_source_record(root) for root in all_roots],
        "terminal_admission": {
            "guard_root": _source_record(guard_root),
            "query_binding_root": _source_record(query_binding_root),
            "runtime_root": _source_record(runtime_root),
            "query_only_adapter": {"path": str(QUERY_ONLY), "sha256": _sha(QUERY_ONLY)},
            "accepted_sequence_count": len(v8_schedule),
            "adopted_sequence": v8_admission.get("sequence"),
        },
        "frozen_contract": {"path": str(original_root / "frozen-run-contract.json"), "sha256": _sha(original_root / "frozen-run-contract.json")},
        "original_analyzer": {
            "path": str(analysis_runtime_root / ANALYZER.relative_to(HERE.parent.parent)),
            "sha256": _sha(analysis_runtime_root / ANALYZER.relative_to(HERE.parent.parent)),
            "executed_derived_source_sha256": hashlib.sha256(_derived_analyzer_source(analysis_runtime_root / ANALYZER.relative_to(HERE.parent.parent)).encode("utf-8")).hexdigest(),
            "consolidator_sha256": _sha(Path(__file__)),
            "derived_checkpoint_filename_compatibility": {
                "in_memory_only": True,
                "legacy_glob": "batch-*.json",
                "accepted_checkpoint_glob": "batch-[0-9][0-9][0-9][0-9].json",
                "preserved_attempt_artifacts_remain_validated": True,
            },
        },
        "analysis_runtime": {"root": str(analysis_runtime_root), "reconstruction_provenance_sha256": _sha(analysis_runtime_root / "reconstruction-provenance.json")},
        "cells": provenance_cells,
    }
    output_root.mkdir(parents=False)
    _write_json(output_root / "summary.json", summary)
    _write_json(output_root / "consolidation-provenance.json", provenance)
    files = {path.name: {"bytes": path.stat().st_size, "sha256": _sha(path)} for path in sorted(output_root.iterdir()) if path.is_file()}
    _write_json(output_root / "manifest.json", {"format_version": 1, "study_id": frozen["study_id"], "files": files})
    return {
        "format_version": 1,
        "status": "complete_330",
        "geometry": provenance["geometry"],
        "source_kind_counts": provenance["source_kind_counts"],
        "summary_path": str(output_root / "summary.json"),
        "provenance_path": str(output_root / "consolidation-provenance.json"),
        "manifest_path": str(output_root / "manifest.json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay the completed 330-cell study from immutable per-cell roots.")
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--closed-successor-root", required=True, type=Path)
    parser.add_argument("--v7-root", required=True, type=Path)
    parser.add_argument("--missing181-root", required=True, type=Path)
    parser.add_argument("--v8-root", required=True, type=Path)
    parser.add_argument("--guard-root", required=True, type=Path)
    parser.add_argument("--query-binding-root", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--analysis-runtime-root", required=True, type=Path)
    parser.add_argument("--runtime-root", type=Path, default=V8_RUNTIME_DEFAULT)
    args = parser.parse_args()
    print(json.dumps(consolidate(**vars(args)), ensure_ascii=False, sort_keys=True))
