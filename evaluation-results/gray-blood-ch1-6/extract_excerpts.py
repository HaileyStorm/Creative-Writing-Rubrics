#!/usr/bin/env python3
"""Extract the four owner-authorized Gray Blood case-study excerpts.

Inputs are supplied at invocation time and are never recorded as paths in the
public receipt. The script performs no model or network work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SELECTIONS: tuple[dict[str, Any], ...] = (
    {
        "excerpt_id": "gb-new-ch01-relationship-approach-v2",
        "file": "excerpts/ch01-new-relationship.md",
        "title": "Chapter 1: an early relationship approach",
        "segments": (("new-ch01", "new", "chapter-01", 9499, 10019),),
    },
    {
        "excerpt_id": "gb-new-ch03-magic-cost-v1",
        "file": "excerpts/ch03-new-magic-cost.md",
        "title": "Chapter 3: the cost of magic",
        "segments": (("new-ch03", "new", "chapter-03", 12322, 12860),),
    },
    {
        "excerpt_id": "gb-new-ch04-engraving-v1",
        "file": "excerpts/ch04-new-engraving.md",
        "title": "Chapter 4: an embodied rule of magic",
        "segments": (("new-ch04", "new", "chapter-04", 9864, 10420),),
    },
    {
        "excerpt_id": "gb-ch05-revision-pair-relationship-magic-v2",
        "file": "excerpts/ch05-revision-pair.md",
        "title": "Chapter 5: preserved core and a revised relationship/magic passage",
        "segments": (
            ("original-ch05", "original", "chapter-05", 25551, 26045),
            ("new-ch05", "new", "chapter-05", 25679, 26237),
        ),
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def segment_record(raw: bytes, input_key: str, draft_id: str, chapter_id: str, start: int, end: int) -> tuple[dict[str, Any], str]:
    text = raw.decode("utf-8")
    if not 0 <= start < end <= len(text):
        raise ValueError(f"invalid character range for {input_key}: {start}:{end}")
    selected = text[start:end]
    selected_bytes = selected.encode("utf-8")
    return (
        {
            "chapter_id": chapter_id,
            "char_end": end,
            "char_start": start,
            "draft_id": draft_id,
            "excerpt_sha256": sha256(selected_bytes),
            "input_sha256": sha256(raw),
            "utf8_byte_end": len(text[:end].encode("utf-8")),
            "utf8_byte_start": len(text[:start].encode("utf-8")),
            "word_count": word_count(selected),
        },
        normalized(selected),
    )


def render(selection: dict[str, Any], parts: list[tuple[str, str]]) -> str:
    if len(parts) == 1:
        body = parts[0][1]
    else:
        grouped: dict[str, list[str]] = {}
        for draft_id, text in parts:
            grouped.setdefault(draft_id, []).append(text)
        body = "\n\n".join(
            f"## {draft_id.title()} draft\n\n" + "\n\n[…]\n\n".join(texts)
            for draft_id, texts in grouped.items()
        )
    return f"# {selection['title']}\n\n{body}\n"


def build_receipt(inputs: dict[str, Path]) -> tuple[dict[str, Any], dict[str, str]]:
    receipt_entries: list[dict[str, Any]] = []
    rendered: dict[str, str] = {}
    for selection in SELECTIONS:
        records: list[dict[str, Any]] = []
        parts: list[tuple[str, str]] = []
        for input_key, draft_id, chapter_id, start, end in selection["segments"]:
            if input_key not in inputs:
                raise ValueError(f"missing required input: {input_key}")
            record, text = segment_record(inputs[input_key].read_bytes(), input_key, draft_id, chapter_id, start, end)
            records.append(record)
            parts.append((draft_id, text))
        content = render(selection, parts)
        rendered[selection["file"]] = content
        receipt_entries.append(
            {
                "excerpt_id": selection["excerpt_id"],
                "file": selection["file"],
                "published_file_sha256": sha256(content.encode("utf-8")),
                "segments": records,
                "word_count": sum(record["word_count"] for record in records),
            }
        )
    receipt = {
        "authorization": "The owner provisionally accepted these exact four selections pending confirmation for public case-study use; no other Gray Blood manuscript prose is authorized here.",
        "curated_excerpts": receipt_entries,
        "format_version": 1,
        "total_word_count": sum(entry["word_count"] for entry in receipt_entries),
        "word_count_method": "non-whitespace tokens in selected source character ranges",
    }
    return receipt, rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", nargs=2, metavar=("KEY", "PATH"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    inputs = {key: Path(value).resolve() for key, value in args.input}
    if len(inputs) != len(args.input):
        raise SystemExit("duplicate input key")
    receipt, rendered = build_receipt(inputs)
    output = args.output.resolve()
    for relative, content in rendered.items():
        destination = output / relative
        if destination.exists() and not args.replace:
            raise SystemExit(f"refusing to overwrite {destination}; pass --replace")
        write_text(destination, content)
    receipt_path = output / "excerpts" / "provenance.json"
    if receipt_path.exists() and not args.replace:
        raise SystemExit(f"refusing to overwrite {receipt_path}; pass --replace")
    write_text(receipt_path, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
