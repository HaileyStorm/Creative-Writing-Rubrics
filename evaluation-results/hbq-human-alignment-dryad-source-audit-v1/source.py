"""Deterministically derive and verify the privacy-minimized Dryad rating tables.

This program reads ZIP members only. It never executes source scripts, extracts their
trees, or performs network/provider work.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import pathlib
import stat
import sys
import tempfile
import zipfile


OUTER_MEMBER = "GenAI_creativity_scripts.zip"
INNER_PREFIX = "GenAI_creativity_scripts/"
WRITERS_MEMBER = INNER_PREFIX + "raw_data/writers-2023-06-28.csv"
EVALUATORS_MEMBER = INNER_PREFIX + "raw_data/evaluators-2023-07-06.csv"
PAGE = "participant._current_page_name"
STORY_ID = "ai_story_gen.1.player.story_id"
CONDITION = "participant.condition"
STORY_TEXT = "ai_story_gen.1.player.story"
CREATIVE_AXES = ["novel", "original", "rare", "appropriate", "feasible", "publishable"]
WRITING_AXES = ["well_written", "enjoyed", "boring", "funny", "twist", "future"]
RAW_WRITING_AXES = {
    "well_written": "tt_badly_written",
    "enjoyed": "tt_enjoyed",
    "boring": "tt_boring",
    "funny": "tt_funny",
    "twist": "tt_twist",
    "future": "tt_future",
}
V1_FIELDS = ["evaluator_index", "story_slot", "story_id", "condition", "topic", "story_text", *CREATIVE_AXES]
V2_FIELDS = [*V1_FIELDS, *WRITING_AXES]
EXPECTED_ARCHIVE_BYTES = 2476017
EXPECTED_ARCHIVE_SHA256 = "af9c67124f94bb52368cf9eeba87ce6e77aaffafa83b9239af6d9e24b9d5f14a"
EXPECTED_OUTER_MEMBERS = {
    "README.md": (3657, 3657, "a3e75d5d884777ce634c69a305928654d2a1e63ca6bb45600a4261529b461bf0"),
    OUTER_MEMBER: (2472080, 2472080, "1eeb56f8882b5eb47e971cb85959f7c947c7a95e2ecff4cfdda9a29f18473942"),
}
EXPECTED_NESTED_ENTRIES = 64
EXPECTED_NESTED_UNCOMPRESSED_BYTES = 11787648
EXPECTED_INPUT_MEMBERS = {
    WRITERS_MEMBER: (889777, 225518, "8918b9f87d2120d331dc0e3ff19290fb3d3dec8481a534a61e83a98646844b76"),
    EVALUATORS_MEMBER: (7669681, 1595359, "538bb43773442ee0df93d440e55f9497f618de22b42aad2f2ac2932433fef9e3"),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unsafe_member(info: zipfile.ZipInfo) -> bool:
    name = info.filename.replace("\\", "/")
    parts = pathlib.PurePosixPath(name).parts
    mode = (info.external_attr >> 16) & 0o170000
    return (
        name.startswith("/")
        or name.startswith("../")
        or ".." in parts
        or (parts and ":" in parts[0])
        or mode == stat.S_IFLNK
    )


def read_csv(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="strict"))))


def human_admitted(row: dict[str, str]) -> bool:
    values = [row.get(f"follow_up.{index}.player.used_ai_tool") for index in (1, 2)]
    used = next((value for value in values if value not in ("", None)), "")
    return row.get(CONDITION) == "human" and used not in ("", "0", "0.0")


def csv_bytes(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def assert_source_archive_pin(archive: pathlib.Path) -> None:
    if not archive.is_file() or archive.stat().st_size != EXPECTED_ARCHIVE_BYTES:
        raise ValueError("Archive size does not match the pinned source before decompression")
    if sha256_file(archive) != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("Archive SHA-256 does not match the pinned source before decompression")


def read_pinned_inputs(archive: pathlib.Path) -> tuple[bytes, bytes]:
    assert_source_archive_pin(archive)
    with zipfile.ZipFile(archive) as outer:
        outer_infos = outer.infolist()
        infos = {info.filename: info for info in outer_infos}
        if len(outer_infos) != len(EXPECTED_OUTER_MEMBERS) or len(infos) != len(EXPECTED_OUTER_MEMBERS) or set(infos) != set(EXPECTED_OUTER_MEMBERS):
            raise ValueError("Outer archive member set does not match the pinned source")
        if any(unsafe_member(info) for info in infos.values()):
            raise ValueError("Unsafe outer archive member")
        for name, (size, compressed, digest) in EXPECTED_OUTER_MEMBERS.items():
            info = infos[name]
            if info.file_size != size or info.compress_size != compressed:
                raise ValueError(f"Outer member size mismatch: {name}")
            value = outer.read(name)
            if sha256_bytes(value) != digest:
                raise ValueError(f"Outer member SHA-256 mismatch: {name}")
        nested = outer.read(OUTER_MEMBER)
    if len(nested) != EXPECTED_OUTER_MEMBERS[OUTER_MEMBER][0]:
        raise ValueError("Nested archive byte length mismatch")
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        if len(inner.infolist()) != EXPECTED_NESTED_ENTRIES:
            raise ValueError("Nested archive entry count mismatch")
        if sum(info.file_size for info in inner.infolist()) != EXPECTED_NESTED_UNCOMPRESSED_BYTES:
            raise ValueError("Nested archive uncompressed-size mismatch")
        if any(unsafe_member(info) for info in inner.infolist()):
            raise ValueError("Unsafe nested archive member")
        values = []
        for name, (size, compressed, digest) in EXPECTED_INPUT_MEMBERS.items():
            info = inner.getinfo(name)
            if info.file_size != size or info.compress_size != compressed:
                raise ValueError(f"Nested member size mismatch: {name}")
            value = inner.read(name)
            if sha256_bytes(value) != digest:
                raise ValueError(f"Nested member SHA-256 mismatch: {name}")
            values.append(value)
    return tuple(values)  # type: ignore[return-value]


def derive(archive: pathlib.Path) -> tuple[bytes, bytes, dict[str, object]]:
    writers_bytes, evaluators_bytes = read_pinned_inputs(archive)
    writers = read_csv(writers_bytes)
    evaluators = read_csv(evaluators_bytes)
    final_writers = [row for row in writers if row.get(PAGE) == "Finally" and row.get(STORY_ID)]
    admitted_story_ids = {row[STORY_ID] for row in final_writers if human_admitted(row)}
    retained = {
        row[STORY_ID]: row
        for row in final_writers
        if not human_admitted(row)
    }
    all_writer_story_ids = {row[STORY_ID] for row in writers if row.get(STORY_ID)}
    nonfinal_story_ids = all_writer_story_ids - set(retained) - admitted_story_ids
    v1_rows: list[dict[str, object]] = []
    v2_rows: list[dict[str, object]] = []
    evaluator_index = 0
    final_slots = 0
    admitted_ai_slots = 0
    nonfinal_writer_slots = 0
    unknown_slots = 0
    admitted_assigned_story_ids: set[str] = set()
    nonfinal_assigned_story_ids: set[str] = set()
    retained_story_ids: set[str] = set()
    for source_row in evaluators:
        if source_row.get(PAGE) != "Finally":
            continue
        evaluator_index += 1
        for slot in range(1, 7):
            prefix = f"evaluator.{slot}.player."
            sid = source_row.get(prefix + "story_id")
            final_slots += 1
            writer = retained.get(sid)
            if writer is None:
                if sid in admitted_story_ids:
                    admitted_ai_slots += 1
                    admitted_assigned_story_ids.add(sid)
                elif sid in nonfinal_story_ids:
                    nonfinal_writer_slots += 1
                    nonfinal_assigned_story_ids.add(sid)
                else:
                    unknown_slots += 1
                continue
            retained_story_ids.add(sid)
            text = writer.get(STORY_TEXT)
            if not text or text != source_row.get(prefix + "story"):
                raise ValueError(f"Story text mismatch for {sid}")
            row: dict[str, object] = {
                "evaluator_index": evaluator_index,
                "story_slot": slot,
                "story_id": sid,
                "condition": writer[CONDITION],
                "topic": source_row.get(prefix + "topic"),
                "story_text": text,
            }
            for axis in CREATIVE_AXES:
                value = source_row.get(prefix + axis)
                if not value or not value.isdigit() or not 1 <= int(value) <= 9:
                    raise ValueError(f"Invalid {axis} rating for {sid}")
                row[axis] = value
            v1_rows.append(row)
            for axis, raw_axis in RAW_WRITING_AXES.items():
                value = source_row.get(prefix + raw_axis)
                if not value or not value.isdigit() or not 1 <= int(value) <= 9:
                    raise ValueError(f"Invalid {axis} rating for {sid}")
                row[axis] = value
            v2_rows.append(row.copy())
    if len(writers) != 500 or len(final_writers) != 296 or len(retained) != 293:
        raise ValueError("Writer reconciliation failed")
    if evaluator_index != 600 or final_slots != 3600:
        raise ValueError("Evaluator reconciliation failed")
    if unknown_slots != 0:
        raise ValueError("Unknown evaluator story ID; refusing source substitution or untracked linkage")
    if admitted_ai_slots != 35 or len(admitted_assigned_story_ids) != 3:
        raise ValueError("Admitted-AI exclusion reconciliation failed")
    if nonfinal_writer_slots != 46 or len(nonfinal_assigned_story_ids) != 4:
        raise ValueError("Nonfinal-writer exclusion reconciliation failed")
    if len(v1_rows) != 3519 or len({row["story_id"] for row in v1_rows}) != 293:
        raise ValueError("Retained-rating reconciliation failed")
    axis_summary = {
        axis: {
            "nonmissing": len(v2_rows),
            "missing": 0,
            "minimum": min(int(row[axis]) for row in v2_rows),
            "maximum": max(int(row[axis]) for row in v2_rows),
            "mean": sum(int(row[axis]) for row in v2_rows) / len(v2_rows),
        }
        for axis in [*CREATIVE_AXES, *WRITING_AXES]
    }
    story_records = {str(row["story_id"]): row for row in v2_rows}
    evidence = {
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "nested_archive_sha256": EXPECTED_OUTER_MEMBERS[OUTER_MEMBER][2],
        "nested_archive_bytes": EXPECTED_OUTER_MEMBERS[OUTER_MEMBER][0],
        "writers_sha256": sha256_bytes(writers_bytes),
        "evaluators_sha256": sha256_bytes(evaluators_bytes),
        "writer_rows": len(writers),
        "completed_writers": len(final_writers),
        "retained_stories": len(retained),
        "completed_evaluators": evaluator_index,
        "final_evaluator_slots": final_slots,
        "retained_story_ids": len(retained_story_ids),
        "admitted_ai_exclusion": {"slots": admitted_ai_slots, "assigned_story_ids": len(admitted_assigned_story_ids)},
        "nonfinal_writer_exclusion": {"slots": nonfinal_writer_slots, "assigned_story_ids": len(nonfinal_assigned_story_ids)},
        "unknown_story_id_exclusion": {"slots": unknown_slots},
        "retained_ratings": len(v1_rows),
        "retained_stories_by_condition": dict(sorted(Counter(str(row["condition"]) for row in story_records.values()).items())),
        "retained_stories_by_topic": dict(sorted(Counter(str(row["topic"]) for row in story_records.values()).items())),
        "retained_rating_axis_summary": axis_summary,
        "v1_sha256": sha256_bytes(csv_bytes(V1_FIELDS, v1_rows)),
        "v2_sha256": sha256_bytes(csv_bytes(V2_FIELDS, v2_rows)),
    }
    return csv_bytes(V1_FIELDS, v1_rows), csv_bytes(V2_FIELDS, v2_rows), evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=pathlib.Path)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--write-v2", action="store_true")
    parser.add_argument("--refresh-reconciliation", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    modes = [args.write_v2, args.refresh_reconciliation, args.check_only, args.self_test]
    if sum(modes) != 1:
        parser.error("Specify exactly one mode")
    v1, v2, evidence = derive(args.archive)
    v1_path = args.root / "data" / "dryad_story_ratings_selected_v1.csv"
    v2_path = args.root / "data" / "dryad_story_ratings_selected_v2.csv"
    reconciliation_path = args.root / "v2-reconciliation.json"
    if not v1_path.is_file() or v1_path.read_bytes() != v1:
        raise ValueError("Existing immutable v1 derivative does not match deterministic reconstruction")
    if args.check_only:
        if not v2_path.is_file() or v2_path.read_bytes() != v2:
            raise ValueError("Existing v2 derivative does not match deterministic reconstruction")
        if not reconciliation_path.is_file() or json.loads(reconciliation_path.read_text(encoding="utf-8")) != evidence:
            raise ValueError("Existing retained-reconciliation evidence does not match deterministic reconstruction")
    elif args.write_v2:
        if v2_path.exists():
            raise FileExistsError("Refusing to overwrite existing v2 derivative")
        v2_path.write_bytes(v2)
        reconciliation_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    elif args.refresh_reconciliation:
        if not v2_path.is_file() or v2_path.read_bytes() != v2:
            raise ValueError("Existing v2 derivative does not match deterministic reconstruction")
        reconciliation_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    else:
        with zipfile.ZipFile(args.archive) as outer:
            nested = outer.read(OUTER_MEMBER)
        with tempfile.TemporaryDirectory() as temporary_directory:
            altered = pathlib.Path(temporary_directory) / "README-only-altered.zip"
            with zipfile.ZipFile(altered, "w", compression=zipfile.ZIP_STORED) as replacement:
                replacement.writestr("README.md", b"altered README only\n")
                replacement.writestr(OUTER_MEMBER, nested)
            try:
                assert_source_archive_pin(altered)
            except ValueError:
                pass
            else:
                raise AssertionError("README-only altered archive unexpectedly passed source pin")
    result = dict(evidence)
    if args.self_test:
        result["readme_only_source_substitution_rejected"] = True
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
