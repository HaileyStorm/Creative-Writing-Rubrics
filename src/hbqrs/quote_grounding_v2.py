"""Opt-in whitespace grounding with offsets into unchanged source text."""
from __future__ import annotations

import hashlib
import unicodedata
from typing import Any

__all__ = ["POLICY", "ground_hbq_quote"]
POLICY = "hbq_unicode_whitespace_grounding_v2"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _collapse(text: str) -> tuple[str, list[int], list[int], list[int]]:
    """Collapse whitespace runs and map each resulting character to its source."""
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    byte_offsets = [0]
    for index, char in enumerate(text):
        byte_offsets.append(byte_offsets[-1] + len(char.encode("utf-8")))
        if char.isspace():
            if index and text[index - 1].isspace():
                ends[-1] = index + 1
            else:
                chars.append(" ")
                starts.append(index)
                ends.append(index + 1)
        else:
            chars.append(char)
            starts.append(index)
            ends.append(index + 1)
    return "".join(chars), starts, ends, byte_offsets


def ground_hbq_quote(
    quote: str, *, artifact_text: str, context_text: str = ""
) -> dict[str, Any]:
    """Return source-span proofs under an explicitly selected whitespace policy.

    Artifact and context are searched separately. Callers supply only the texts
    permitted by their request contract. Every match is retained, including
    ambiguity. This function neither modifies responses nor admits or scores them.

    Offsets are zero-based, half-open Unicode codepoint and UTF-8 byte positions
    in the original scope. ``raw_span`` and ``unique_raw_span`` contain source text.
    """
    if not all(isinstance(value, str) for value in (quote, artifact_text, context_text)):
        raise TypeError("Quote and both permitted scope texts must be strings")
    normalized, _, _, _ = _collapse(quote)
    result: dict[str, Any] = {
        "policy": POLICY,
        "quote_sha256": _sha(quote),
        "quote_bytes": len(quote.encode("utf-8")),
        "normalized_quote_sha256": _sha(normalized),
        "unicode_database_version": unicodedata.unidata_version,
        "normalization": "str.isspace runs -> one ASCII space; no trimming/case/punctuation/other-character changes",
        "permitted_scope_commitments": {
            name: {"sha256": _sha(text), "bytes": len(text.encode("utf-8"))}
            for name, text in (("artifact", artifact_text), ("context", context_text))
        },
        "grounded": False,
        "literal_raw_substring_found": False,
        "match_count": 0,
        "matches": [],
        "span_status": "not_found",
        "unique_raw_span": None,
        "scientific_admission": None,
        "raw_response_modified": False,
    }
    if not quote or not any(not char.isspace() for char in quote):
        result["state"] = "REJECTED_BLANK_QUOTE"
        return result
    for name, text in (("artifact", artifact_text), ("context", context_text)):
        result["literal_raw_substring_found"] |= quote in text
        scope, starts, ends, byte_offsets = _collapse(text)
        position = scope.find(normalized)
        while position != -1:
            first = starts[position]
            last = ends[position + len(normalized) - 1]
            raw_span = text[first:last]
            result["matches"].append({
                "scope": name,
                "char_start": first,
                "char_end": last,
                "utf8_byte_start": byte_offsets[first],
                "utf8_byte_end": byte_offsets[last],
                "raw_span": raw_span,
                "raw_span_sha256": _sha(raw_span),
                "match_kind": "literal_exact" if raw_span == quote else "whitespace_only",
                "offset_convention": "zero-based half-open in original scope",
            })
            position = scope.find(normalized, position + 1)
    result["match_count"] = len(result["matches"])
    result["grounded"] = bool(result["matches"])
    if result["match_count"] == 1:
        result["span_status"] = "unique"
        result["unique_raw_span"] = result["matches"][0]["raw_span"]
    elif result["match_count"] > 1:
        result["span_status"] = "ambiguous_all_locations_retained_no_choice"
    result["state"] = "GROUNDED_LITERAL" if result["literal_raw_substring_found"] else (
        "GROUNDED_WHITESPACE_ONLY" if result["grounded"] else "REJECTED_NOT_IN_PERMITTED_SCOPES"
    )
    return result
