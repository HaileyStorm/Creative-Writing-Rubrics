"""Create the local Dryad pilot freeze from the hash-pinned audited source.

The audited source owns archive validation and source reconstruction. This module owns
only story-level aggregation, source-only partitioning, and narrow public inputs.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import stat
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


AUDITED_SOURCE_COMMIT = "6cb64b20ce19bde24dfe86357cc744b2c71cd7cf"
AUDITED_SOURCE_SHA256 = "4184280abae4d84dad970ba3e0f994a078f083cd12e3cb3d2ff6f3f60e89746d"
AUDITED_SOURCE_RELATIVE_PATH = Path("..") / "hbq-human-alignment-dryad-source-audit-v1" / "source.py"
SOURCE_SEED = "dryad-pilot-v1-story-partitions-20260905"
PARTITIONS = ("TRAIN", "DEV", "CONFIRMATION")
WEIGHTS = {"TRAIN": 3, "DEV": 1, "CONFIRMATION": 1}
AXES = (
    "novel",
    "original",
    "rare",
    "appropriate",
    "feasible",
    "publishable",
    "well_written",
    "enjoyed",
    "boring",
    "funny",
    "twist",
    "future",
)
EXPECTED = {
    "archive_sha256": "af9c67124f94bb52368cf9eeba87ce6e77aaffafa83b9239af6d9e24b9d5f14a",
    "nested_archive_sha256": "1eeb56f8882b5eb47e971cb85959f7c947c7a95e2ecff4cfdda9a29f18473942",
    "writers_sha256": "8918b9f87d2120d331dc0e3ff19290fb3d3dec8481a534a61e83a98646844b76",
    "evaluators_sha256": "538bb43773442ee0df93d440e55f9497f618de22b42aad2f2ac2932433fef9e3",
    "v2_sha256": "e391d638f04eac7a9632811922d0c4fed4e95dd6613f07311d8513b9a52e128b",
    "retained_stories": 293,
    "retained_ratings": 3519,
    "completed_evaluators": 600,
    "unknown_story_slots": 0,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_jsonl_bytes(values: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(value) for value in values)


def audited_source_path() -> Path:
    return (Path(__file__).resolve().parent / AUDITED_SOURCE_RELATIVE_PATH).resolve()


def contract_path() -> Path:
    return Path(__file__).resolve().with_name("experiment-contract.json")


def repository_root(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ValueError("Cannot locate repository root for generator identity")


def generator_identity(fixture_identity: dict[str, str] | None = None) -> dict[str, str]:
    source = Path(__file__).resolve()
    contract = contract_path()
    identity = {
        "source_sha256": sha256_file(source),
        "contract_sha256": sha256_file(contract),
    }
    if fixture_identity is not None:
        if fixture_identity.get("kind") != "TEST_FIXTURE" or fixture_identity.get("source_sha256") != identity["source_sha256"] or fixture_identity.get("contract_sha256") != identity["contract_sha256"] or not fixture_identity.get("git_commit"):
            raise ValueError("Fixture identity must explicitly bind current source and contract bytes")
        return {**identity, "git_commit": fixture_identity["git_commit"], "mode": "TEST_FIXTURE"}
    root = repository_root(source.parent)
    relative_source = source.relative_to(root).as_posix()
    relative_contract = contract.relative_to(root).as_posix()
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        for relative, path in ((relative_source, source), (relative_contract, contract)):
            committed = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{relative}"], check=True, capture_output=True, text=False).stdout
            if committed != path.read_bytes():
                raise ValueError("Actual freeze requires generator source and contract committed at HEAD")
    except subprocess.CalledProcessError as error:
        raise ValueError("Actual freeze requires generator source and contract committed at HEAD") from error
    return {**identity, "git_commit": commit, "mode": "COMMITTED"}


def verify_generator_provenance(identity: Any, fixture_identity: dict[str, str] | None = None) -> None:
    if not isinstance(identity, dict):
        raise ValueError("Missing generator provenance")
    if fixture_identity is not None:
        if identity != generator_identity(fixture_identity):
            raise ValueError("Fixture generator provenance drift")
        return
    if identity.get("mode") != "COMMITTED" or not isinstance(identity.get("git_commit"), str):
        raise ValueError("Actual freeze requires committed generator provenance")
    source = Path(__file__).resolve()
    contract = contract_path()
    root = repository_root(source.parent)
    commit = identity["git_commit"]
    for relative, key in ((source.relative_to(root).as_posix(), "source_sha256"), (contract.relative_to(root).as_posix(), "contract_sha256")):
        try:
            historical = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{relative}"], check=True, capture_output=True, text=False).stdout
        except subprocess.CalledProcessError as error:
            raise ValueError("Recorded generator commit or path is unavailable") from error
        if sha256_bytes(historical) != identity.get(key):
            raise ValueError("Recorded generator bytes do not match provenance")


def load_audited_source() -> ModuleType:
    path = audited_source_path()
    if not path.is_file() or sha256_bytes(path.read_bytes()) != AUDITED_SOURCE_SHA256:
        raise ValueError("Audited Dryad source.py does not match the pinned commit content")
    spec = importlib.util.spec_from_file_location("dryad_source_audit_v1", path)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot import the pinned Dryad source audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_audited_v2(archive_path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    audited = load_audited_source()
    _, v2_bytes, evidence = audited.derive(archive_path)
    if not isinstance(evidence, dict):
        raise ValueError("Audited source returned malformed reconciliation evidence")
    for key, expected in EXPECTED.items():
        actual = evidence.get("unknown_story_id_exclusion", {}).get("slots") if key == "unknown_story_slots" else evidence.get(key)
        if actual != expected:
            raise ValueError(f"Audited source pin or count mismatch: {key}")
    if sha256_bytes(v2_bytes) != EXPECTED["v2_sha256"]:
        raise ValueError("Audited v2 byte stream does not match the pinned derivative")
    rows = list(csv.DictReader(io.StringIO(v2_bytes.decode("utf-8", errors="strict"))))
    required = {"evaluator_index", "story_slot", "story_id", "condition", "topic", "story_text", *AXES}
    if len(rows) != EXPECTED["retained_ratings"] or set(rows[0]) != required:
        raise ValueError("Audited v2 schema or cardinality drift")
    return rows, evidence


def opaque_story_id(story_id: str, text_sha256: str) -> str:
    payload = f"dryad-pilot-v1-opaque-id-20260905\x1f{story_id}\x1f{text_sha256}".encode("utf-8")
    return f"dryad-{sha256_bytes(payload)[:24]}"


def story_order_key(story_id: str, text_sha256: str) -> tuple[str, str]:
    payload = f"{SOURCE_SEED}{story_id}{text_sha256}".encode("utf-8")
    return sha256_bytes(payload), story_id


def exact_mean(values: list[int]) -> str:
    with localcontext() as context:
        context.prec = 28
        return format(Decimal(sum(values)) / Decimal(len(values)), "f")


def aggregate_stories(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    text_owner: dict[str, str] = {}
    for row in rows:
        story_id = row["story_id"]
        text = row["story_text"]
        text_sha = sha256_bytes(text.encode("utf-8"))
        previous = text_owner.setdefault(text_sha, story_id)
        if previous != story_id:
            raise ValueError("Duplicate story text across canonical story IDs")
        grouped[story_id].append(row)
    if len(grouped) != EXPECTED["retained_stories"]:
        raise ValueError("Story cardinality drift")
    stories: list[dict[str, Any]] = []
    for story_id, ratings in grouped.items():
        first = ratings[0]
        if any(row["story_text"] != first["story_text"] or row["condition"] != first["condition"] or row["topic"] != first["topic"] for row in ratings):
            raise ValueError("Story text or local stratum drift")
        means: dict[str, str] = {}
        for axis in AXES:
            values = [int(row[axis]) for row in ratings]
            if any(value < 1 or value > 9 for value in values):
                raise ValueError(f"Rating range drift for {axis}")
            means[axis] = exact_mean(values)
        text_sha = sha256_bytes(first["story_text"].encode("utf-8"))
        stories.append(
            {
                "source_story_id": story_id,
                "opaque_story_id": opaque_story_id(story_id, text_sha),
                "story_text": first["story_text"],
                "story_text_sha256": text_sha,
                "condition": first["condition"],
                "topic": first["topic"],
                "rating_count": len(ratings),
                "human_means": means,
            }
        )
    return stories


def partition_stories(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    opaque_ids: set[str] = set()
    for story in stories:
        opaque_id = str(story["opaque_story_id"])
        if opaque_id in opaque_ids:
            raise ValueError("Opaque story-ID collision")
        opaque_ids.add(opaque_id)
        strata[(str(story["topic"]), str(story["condition"]))].append(story)
    if len(strata) != 9:
        raise ValueError("Expected all nine topic-by-condition strata")
    assigned: list[dict[str, Any]] = []
    for stratum, members in sorted(strata.items()):
        ordered = sorted(
            members,
            key=lambda story: story_order_key(str(story["source_story_id"]), str(story["story_text_sha256"])),
        )
        total = len(ordered)
        quotas = {partition: total * WEIGHTS[partition] // 5 for partition in PARTITIONS}
        remaining = total - sum(quotas.values())
        residue_order = sorted(
            PARTITIONS,
            key=lambda partition: (-(total * WEIGHTS[partition] % 5), PARTITIONS.index(partition)),
        )
        for partition in residue_order[:remaining]:
            quotas[partition] += 1
        cursor = 0
        for partition in PARTITIONS:
            for story in ordered[cursor : cursor + quotas[partition]]:
                assigned.append({**story, "partition": partition})
            cursor += quotas[partition]
        if cursor != total:
            raise AssertionError(f"Partition quota failure for {stratum}")
    if len(assigned) != EXPECTED["retained_stories"]:
        raise ValueError("Partition assignment cardinality drift")
    return sorted(assigned, key=lambda story: str(story["opaque_story_id"]))


def write_new(path: Path, value: bytes) -> str:
    with path.open("xb") as stream:
        stream.write(value)
    return sha256_bytes(value)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify_source_evidence(evidence: dict[str, Any]) -> None:
    for key, expected in EXPECTED.items():
        actual = evidence.get("unknown_story_id_exclusion", {}).get("slots") if key == "unknown_story_slots" else evidence.get(key)
        if actual != expected:
            raise ValueError(f"Frozen source evidence mismatch: {key}")
    summaries = evidence.get("retained_rating_axis_summary")
    if set(summaries or ()) != set(AXES):
        raise ValueError("Frozen source axis inventory drift")
    for axis in AXES:
        summary = summaries[axis]
        if summary.get("nonmissing") != EXPECTED["retained_ratings"] or summary.get("missing") != 0 or summary.get("minimum") != 1 or summary.get("maximum") != 9:
            raise ValueError(f"Frozen source axis summary drift: {axis}")


def expected_stratum_partitions(records: list[dict[str, Any]]) -> dict[str, str]:
    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (str(record["topic"]), str(record["condition"]))
        expected_key = story_order_key(str(record["source_story_id"]), str(record["story_text_sha256"]))[0]
        if record.get("selection_key") != expected_key:
            raise ValueError("Split manifest selection-key drift")
        strata[key].append(record)
    if len(strata) != 9:
        raise ValueError("Split manifest stratum inventory drift")
    expected: dict[str, str] = {}
    for members in strata.values():
        ordered = sorted(members, key=lambda record: (str(record["selection_key"]), str(record["source_story_id"])))
        total = len(ordered)
        quotas = {partition: total * WEIGHTS[partition] // 5 for partition in PARTITIONS}
        remaining = total - sum(quotas.values())
        residue_order = sorted(PARTITIONS, key=lambda partition: (-(total * WEIGHTS[partition] % 5), PARTITIONS.index(partition)))
        for partition in residue_order[:remaining]:
            quotas[partition] += 1
        cursor = 0
        for partition in PARTITIONS:
            for record in ordered[cursor : cursor + quotas[partition]]:
                expected[str(record["opaque_story_id"])] = partition
            cursor += quotas[partition]
    return expected


def verify_freeze(
    freeze_root: Path,
    expected_provenance_sha256: str,
    *,
    fixture_identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify all local freeze artifacts before any public input is exposed."""
    expected_physical_names = {
        "provenance.json",
        "local-targets.jsonl",
        "confirmation-targets.jsonl",
        "split-manifest.jsonl",
        "public-inputs.json",
    }
    if not freeze_root.is_dir() or is_reparse_point(freeze_root):
        raise ValueError("Freeze root must be a direct directory")
    entries = list(freeze_root.iterdir())
    if {entry.name for entry in entries} != expected_physical_names or any(not entry.is_file() or is_reparse_point(entry) for entry in entries):
        raise ValueError("Freeze root physical artifact set drift")
    provenance_path = freeze_root / "provenance.json"
    if len(expected_provenance_sha256) != 64 or sha256_file(provenance_path) != expected_provenance_sha256.lower():
        raise ValueError("Externally bound provenance SHA-256 mismatch")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("audited_source") != {
        "commit": AUDITED_SOURCE_COMMIT,
        "path": str(AUDITED_SOURCE_RELATIVE_PATH).replace("\\", "/"),
        "sha256": AUDITED_SOURCE_SHA256,
    }:
        raise ValueError("Audited-source provenance drift")
    verify_generator_provenance(provenance.get("generator"), fixture_identity)
    source_evidence = provenance.get("source_evidence")
    if not isinstance(source_evidence, dict):
        raise ValueError("Missing source reconciliation evidence")
    verify_source_evidence(source_evidence)
    artifacts = provenance.get("artifacts")
    expected_names = {
        "local-targets.jsonl",
        "confirmation-targets.jsonl",
        "split-manifest.jsonl",
        "public-inputs.json",
    }
    if set(artifacts or ()) != expected_names:
        raise ValueError("Artifact inventory drift")
    for name in expected_names:
        path = freeze_root / name
        metadata = artifacts[name]
        if not path.is_file() or metadata.get("bytes") != path.stat().st_size or metadata.get("sha256") != sha256_file(path):
            raise ValueError(f"Artifact byte or hash mismatch: {name}")
    targets = read_jsonl(freeze_root / "local-targets.jsonl")
    confirmation = read_jsonl(freeze_root / "confirmation-targets.jsonl")
    split = read_jsonl(freeze_root / "split-manifest.jsonl")
    public = json.loads((freeze_root / "public-inputs.json").read_text(encoding="utf-8"))
    target_fields = {"condition", "human_means", "opaque_story_id", "partition", "rating_count", "source_story_id", "story_text_sha256", "topic"}
    split_fields = {"condition", "opaque_story_id", "partition", "selection_key", "source_story_id", "story_text_sha256", "topic"}
    if len(targets) != EXPECTED["retained_stories"] or len(split) != EXPECTED["retained_stories"] or any(set(record) != target_fields or set(record["human_means"]) != set(AXES) for record in targets) or any(set(record) != split_fields for record in split):
        raise ValueError("Local target or split schema inventory drift")
    split_by_opaque = {str(record["opaque_story_id"]): record for record in split}
    target_by_opaque = {str(record["opaque_story_id"]): record for record in targets}
    if len(split_by_opaque) != EXPECTED["retained_stories"] or len(target_by_opaque) != EXPECTED["retained_stories"] or set(split_by_opaque) != set(target_by_opaque):
        raise ValueError("Local target identity inventory drift")
    if len({record["source_story_id"] for record in split}) != EXPECTED["retained_stories"] or len({record["story_text_sha256"] for record in split}) != EXPECTED["retained_stories"]:
        raise ValueError("Canonical source-story or text inventory drift")
    expected_partitions = expected_stratum_partitions(split)
    if {opaque: record["partition"] for opaque, record in split_by_opaque.items()} != expected_partitions:
        raise ValueError("Source-only partition assignment drift")
    for opaque, split_record in split_by_opaque.items():
        target = target_by_opaque[opaque]
        if any(target[field] != split_record[field] for field in ("condition", "partition", "source_story_id", "story_text_sha256", "topic")) or not isinstance(target["rating_count"], int) or not 9 <= target["rating_count"] <= 14:
            raise ValueError("Local target linkage drift")
        for axis, value in target["human_means"].items():
            if axis not in AXES or not Decimal(str(value)).is_finite() or not Decimal("1") <= Decimal(str(value)) <= Decimal("9"):
                raise ValueError("Local human-mean inventory drift")
    expected_confirmation = [target for target in targets if target["partition"] == "CONFIRMATION"]
    if confirmation != expected_confirmation:
        raise ValueError("Confirmation target inventory drift")
    if set(public) != {"TRAIN", "DEV"}:
        raise ValueError("Public input partition inventory drift")
    for partition, records in public.items():
        if not isinstance(records, list) or any(set(record) != {"opaque_story_id", "story_text"} for record in records):
            raise ValueError(f"Public input schema drift: {partition}")
        expected_records = [record for record in split if record["partition"] == partition]
        if [record["opaque_story_id"] for record in records] != [record["opaque_story_id"] for record in expected_records]:
            raise ValueError(f"Public input identity or order drift: {partition}")
        for record, split_record in zip(records, expected_records, strict=True):
            opaque = str(record["opaque_story_id"])
            if opaque != split_record["opaque_story_id"] or sha256_bytes(record["story_text"].encode("utf-8")) != split_record["story_text_sha256"]:
                raise ValueError("Public input linkage drift")
    public_ids = {str(record["opaque_story_id"]) for records in public.values() for record in records}
    expected_public_ids = {opaque for opaque, record in split_by_opaque.items() if record["partition"] in {"TRAIN", "DEV"}}
    confirmation_ids = {str(record["opaque_story_id"]) for record in confirmation}
    if len(public_ids) != sum(len(records) for records in public.values()) or public_ids != expected_public_ids or public_ids & confirmation_ids:
        raise ValueError("Public input confirmation boundary drift")
    return provenance


def create_freeze(
    archive_path: Path,
    output_root: Path,
    *,
    fixture_identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create an exact-byte local freeze in a path that does not yet exist."""
    if output_root.exists():
        raise FileExistsError("Dryad freeze root already exists; create-only output refuses overwrite")
    identity = generator_identity(fixture_identity)
    rows, source_evidence = parse_audited_v2(archive_path)
    stories = partition_stories(aggregate_stories(rows))
    output_root.mkdir(parents=True)
    local_targets = [
        {
            "condition": story["condition"],
            "human_means": story["human_means"],
            "opaque_story_id": story["opaque_story_id"],
            "partition": story["partition"],
            "rating_count": story["rating_count"],
            "source_story_id": story["source_story_id"],
            "story_text_sha256": story["story_text_sha256"],
            "topic": story["topic"],
        }
        for story in stories
    ]
    confirmation_targets = [target for target in local_targets if target["partition"] == "CONFIRMATION"]
    split_manifest = [
        {
            "condition": story["condition"],
            "opaque_story_id": story["opaque_story_id"],
            "partition": story["partition"],
            "selection_key": story_order_key(str(story["source_story_id"]), str(story["story_text_sha256"]))[0],
            "source_story_id": story["source_story_id"],
            "story_text_sha256": story["story_text_sha256"],
            "topic": story["topic"],
        }
        for story in stories
    ]
    public_inputs = {
        partition: [
            {"opaque_story_id": story["opaque_story_id"], "story_text": story["story_text"]}
            for story in stories
            if story["partition"] == partition
        ]
        for partition in ("TRAIN", "DEV")
    }
    target_bytes = canonical_jsonl_bytes(local_targets)
    confirmation_bytes = canonical_jsonl_bytes(confirmation_targets)
    split_bytes = canonical_jsonl_bytes(split_manifest)
    public_bytes = canonical_json_bytes(public_inputs)
    target_hash = write_new(output_root / "local-targets.jsonl", target_bytes)
    confirmation_hash = write_new(output_root / "confirmation-targets.jsonl", confirmation_bytes)
    split_hash = write_new(output_root / "split-manifest.jsonl", split_bytes)
    public_hash = write_new(output_root / "public-inputs.json", public_bytes)
    provenance = {
        "schema_version": 1,
        "evidence_class": "source_freeze_only_no_model_measurement",
        "audited_source": {
            "commit": AUDITED_SOURCE_COMMIT,
            "path": str(AUDITED_SOURCE_RELATIVE_PATH).replace("\\", "/"),
            "sha256": AUDITED_SOURCE_SHA256,
        },
        "generator": identity,
        "source_evidence": source_evidence,
        "partition": {
            "seed": SOURCE_SEED,
            "weights": WEIGHTS,
            "counts": dict(sorted(Counter(str(story["partition"]) for story in stories).items())),
            "strata": dict(sorted(Counter(f"{story['topic']}|{story['condition']}" for story in stories).items())),
        },
        "artifacts": {
            "local-targets.jsonl": {"sha256": target_hash, "bytes": len(target_bytes)},
            "confirmation-targets.jsonl": {"sha256": confirmation_hash, "bytes": len(confirmation_bytes)},
            "split-manifest.jsonl": {"sha256": split_hash, "bytes": len(split_bytes)},
            "public-inputs.json": {"sha256": public_hash, "bytes": len(public_bytes)},
        },
        "non_claims": {
            "model_alignment": False,
            "rubric_mapping": False,
            "cross_dataset_pooling": False,
            "runtime_promotion": False,
            "provider_calls": False,
        },
    }
    provenance_bytes = canonical_json_bytes(provenance)
    provenance_hash = write_new(output_root / "provenance.json", provenance_bytes)
    return {"output_root": str(output_root), "provenance_sha256": provenance_hash, **provenance}


def load_public_inputs(
    freeze_root: Path,
    expected_provenance_sha256: str,
    *,
    fixture_identity: dict[str, str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Return only the TRAIN/DEV opaque IDs and story text from a finished freeze."""
    verify_freeze(freeze_root, expected_provenance_sha256, fixture_identity=fixture_identity)
    value = json.loads((freeze_root / "public-inputs.json").read_text(encoding="utf-8"))
    if set(value) != {"TRAIN", "DEV"}:
        raise ValueError("Public input partitions drift")
    for partition, records in value.items():
        if not isinstance(records, list) or any(set(record) != {"opaque_story_id", "story_text"} for record in records):
            raise ValueError(f"Public input schema drift: {partition}")
    return value
