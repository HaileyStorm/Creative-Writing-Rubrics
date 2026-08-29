#!/usr/bin/env python3
"""Provider-free descriptive checks for CWR-guided revision descendants.

The output records mechanically reproducible changes between an immutable input
and a descendant.  It deliberately does not score prose quality or decide
whether a revision gained anything; endpoint judgments remain a separate,
blind measurement path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ANALYSIS_VERSION = "cwr-guided-revision-deterministic-checks-v1"
NGRAM_SIZE = 3
FIRST_PERSON_MARKERS = frozenset({"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"})
COLLATERAL_DAMAGE_THRESHOLDS = {
    "minimum_descendant_character_fraction": 0.5,
    "minimum_descendant_word_fraction": 0.5,
    "maximum_unbalanced_delimiter_increase": 0,
    "maximum_repeated_whitespace_run_increase": 2,
    "maximum_terminal_punctuation_ratio_drop": 0.35,
    "maximum_trigram_duplicate_occurrence_rate": 0.2,
    "minimum_trigram_duplicate_rate_increase": 0.15,
}

_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+(?=$)")
_REPEATED_WHITESPACE_RE = re.compile(r"[ \t]{2,}|(?:\r?\n){3,}")


def canonical_json(value: Any) -> bytes:
    """Return the deterministic UTF-8 JSON representation used by this tool."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_utf8(payload: bytes, label: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} is not UTF-8 text") from error


def _words(text: str) -> list[str]:
    return [word.casefold() for word in _WORD_RE.findall(unicodedata.normalize("NFC", text))]


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [sentence.strip() for sentence in _SENTENCE_RE.findall(normalized) if sentence.strip()]


def _paragraph_count(text: str) -> int:
    return len([part for part in re.split(r"(?:\r?\n){2,}", text) if part.strip()])


def _terminal_punctuation_ratio(text: str) -> dict[str, int | float]:
    sentences = _sentences(text)
    terminal = sum(sentence.endswith((".", "!", "?")) for sentence in sentences)
    return {
        "sentence_units": len(sentences),
        "terminal_punctuated_sentence_units": terminal,
        "ratio": round(terminal / len(sentences), 6) if sentences else 0.0,
    }


def _text_counts(text: str, raw: bytes) -> dict[str, int]:
    return {
        "bytes": len(raw),
        "characters": len(text),
        "words": len(_words(text)),
        "paragraphs": _paragraph_count(text),
        "sentence_units": len(_sentences(text)),
    }


def _delta(source: Mapping[str, int], descendant: Mapping[str, int]) -> dict[str, int]:
    return {key: descendant[key] - source[key] for key in source}


def _repetition_proxy(text: str) -> dict[str, int | float]:
    normalized_lines = [unicodedata.normalize("NFC", re.sub(r"\s+", " ", line).strip()).casefold() for line in text.splitlines()]
    nonblank_lines = [line for line in normalized_lines if line]
    words = _words(text)
    ngrams = [tuple(words[index:index + NGRAM_SIZE]) for index in range(max(0, len(words) - NGRAM_SIZE + 1))]
    line_duplicates = len(nonblank_lines) - len(set(nonblank_lines))
    ngram_duplicates = len(ngrams) - len(set(ngrams))
    return {
        "n_gram_size": NGRAM_SIZE,
        "nonblank_lines": len(nonblank_lines),
        "duplicate_line_occurrences": line_duplicates,
        "eligible_n_gram_occurrences": len(ngrams),
        "duplicate_n_gram_occurrences": ngram_duplicates,
        "duplicate_n_gram_occurrence_rate": round(ngram_duplicates / len(ngrams), 6) if ngrams else 0.0,
    }


def _delimiter_counts(text: str) -> dict[str, int]:
    return {
        "parentheses": abs(text.count("(") - text.count(")")),
        "brackets": abs(text.count("[") - text.count("]")),
        "braces": abs(text.count("{") - text.count("}")),
        "ascii_double_quotes": text.count('"') % 2,
        "curly_double_quotes": abs(text.count("“") - text.count("”")),
    }


def _mechanics_counts(text: str) -> dict[str, Any]:
    delimiters = _delimiter_counts(text)
    repeated_runs = _REPEATED_WHITESPACE_RE.findall(text)
    return {
        "unbalanced_common_delimiters": delimiters,
        "unbalanced_common_delimiter_total": sum(delimiters.values()),
        "repeated_whitespace_runs": len(repeated_runs),
        "longest_repeated_whitespace_run_characters": max((len(run) for run in repeated_runs), default=0),
        "terminal_punctuation": _terminal_punctuation_ratio(text),
    }


def _sentence_length_distribution(text: str) -> dict[str, Any]:
    lengths = [len(_words(sentence)) for sentence in _sentences(text)]
    histogram = Counter(lengths)
    return {
        "sentence_units": len(lengths),
        "word_length_histogram": {str(length): histogram[length] for length in sorted(histogram)},
        "minimum_words": min(lengths, default=0),
        "maximum_words": max(lengths, default=0),
        "mean_words": round(statistics.fmean(lengths), 6) if lengths else 0.0,
    }


def _quoted_character_count(text: str) -> int:
    total = 0
    opener_at: int | None = None
    expected_closer: str | None = None
    for index, character in enumerate(text):
        if expected_closer is None:
            if character == '"':
                opener_at, expected_closer = index, '"'
            elif character == "“":
                opener_at, expected_closer = index, "”"
        elif character == expected_closer:
            total += max(0, index - opener_at - 1)
            opener_at, expected_closer = None, None
    return total


def _voice_style_proxy(text: str) -> dict[str, Any]:
    words = _words(text)
    non_whitespace_characters = sum(not character.isspace() for character in text)
    first_person = sum(word in FIRST_PERSON_MARKERS for word in words)
    return {
        "sentence_length_distribution": _sentence_length_distribution(text),
        "dialogue_character_ratio": round(_quoted_character_count(text) / non_whitespace_characters, 6) if non_whitespace_characters else 0.0,
        "first_person_marker_rate": round(first_person / len(words), 6) if words else 0.0,
        "type_token_ratio": round(len(set(words)) / len(words), 6) if words else 0.0,
    }


def _prompt_lexical_overlap(prompt_bytes: bytes | None, prompt_text: str | None, descendant_text: str) -> dict[str, Any]:
    if prompt_bytes is None or prompt_text is None:
        return {"provided": False, "prompt_bytes": None, "prompt_sha256": None, "unique_prompt_token_count": None, "matching_descendant_token_count": None, "matching_descendant_token_fraction": None}
    prompt_tokens = sorted(set(_words(prompt_text)))
    descendant_tokens = set(_words(descendant_text))
    matching_tokens = [token for token in prompt_tokens if token in descendant_tokens]
    return {
        "provided": True,
        "prompt_bytes": len(prompt_bytes),
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "unique_prompt_token_count": len(prompt_tokens),
        "matching_descendant_token_count": len(matching_tokens),
        "matching_descendant_token_fraction": round(len(matching_tokens) / len(prompt_tokens), 6) if prompt_tokens else None,
        "matching_descendant_tokens": matching_tokens,
        "definition": "Whole-prompt, NFC-normalized and casefolded unique-token overlap only. It is descriptive and non-causal; it does not parse constraints or establish instruction-following, preservation, quality, or revision gain.",
    }


def _paired_numeric_delta(source: Mapping[str, Any], descendant: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in keys:
        source_value, descendant_value = source[key], descendant[key]
        result[key] = None if source_value is None or descendant_value is None else round(descendant_value - source_value, 6)
    return result


def _collateral_damage_flags(
    counts: Mapping[str, Mapping[str, int]], mechanics: Mapping[str, Mapping[str, Any]],
    repetition: Mapping[str, Mapping[str, int | float]],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    source, descendant = counts["source"], counts["descendant"]
    character_fraction = descendant["characters"] / source["characters"] if source["characters"] else None
    word_fraction = descendant["words"] / source["words"] if source["words"] else None
    if character_fraction is not None and character_fraction < COLLATERAL_DAMAGE_THRESHOLDS["minimum_descendant_character_fraction"]:
        flags.append({"flag_id": "source_character_fraction_below_minimum", "observed": round(character_fraction, 6), "threshold": COLLATERAL_DAMAGE_THRESHOLDS["minimum_descendant_character_fraction"]})
    if word_fraction is not None and word_fraction < COLLATERAL_DAMAGE_THRESHOLDS["minimum_descendant_word_fraction"]:
        flags.append({"flag_id": "source_word_fraction_below_minimum", "observed": round(word_fraction, 6), "threshold": COLLATERAL_DAMAGE_THRESHOLDS["minimum_descendant_word_fraction"]})
    delimiter_increase = mechanics["descendant"]["unbalanced_common_delimiter_total"] - mechanics["source"]["unbalanced_common_delimiter_total"]
    if delimiter_increase > COLLATERAL_DAMAGE_THRESHOLDS["maximum_unbalanced_delimiter_increase"]:
        flags.append({"flag_id": "unbalanced_delimiter_count_increased", "observed": delimiter_increase, "threshold": COLLATERAL_DAMAGE_THRESHOLDS["maximum_unbalanced_delimiter_increase"]})
    whitespace_increase = mechanics["descendant"]["repeated_whitespace_runs"] - mechanics["source"]["repeated_whitespace_runs"]
    if whitespace_increase > COLLATERAL_DAMAGE_THRESHOLDS["maximum_repeated_whitespace_run_increase"]:
        flags.append({"flag_id": "repeated_whitespace_runs_increase_exceeds_maximum", "observed": whitespace_increase, "threshold": COLLATERAL_DAMAGE_THRESHOLDS["maximum_repeated_whitespace_run_increase"]})
    terminal_drop = mechanics["source"]["terminal_punctuation"]["ratio"] - mechanics["descendant"]["terminal_punctuation"]["ratio"]
    if terminal_drop > COLLATERAL_DAMAGE_THRESHOLDS["maximum_terminal_punctuation_ratio_drop"]:
        flags.append({"flag_id": "terminal_punctuation_ratio_drop_exceeds_maximum", "observed": round(terminal_drop, 6), "threshold": COLLATERAL_DAMAGE_THRESHOLDS["maximum_terminal_punctuation_ratio_drop"]})
    source_rate = repetition["source"]["duplicate_n_gram_occurrence_rate"]
    descendant_rate = repetition["descendant"]["duplicate_n_gram_occurrence_rate"]
    if descendant_rate > COLLATERAL_DAMAGE_THRESHOLDS["maximum_trigram_duplicate_occurrence_rate"] and descendant_rate - source_rate >= COLLATERAL_DAMAGE_THRESHOLDS["minimum_trigram_duplicate_rate_increase"]:
        flags.append({"flag_id": "trigram_duplicate_occurrence_rate_increased", "observed": descendant_rate, "threshold": COLLATERAL_DAMAGE_THRESHOLDS["maximum_trigram_duplicate_occurrence_rate"]})
    return flags


def analyze_revision_bytes(source_bytes: bytes, descendant_bytes: bytes, *, originating_prompt_bytes: bytes | None = None) -> dict[str, Any]:
    """Produce deterministic, non-semantic source-versus-descendant checks."""
    source_text = _decode_utf8(source_bytes, "source")
    descendant_text = _decode_utf8(descendant_bytes, "descendant")
    prompt_text = _decode_utf8(originating_prompt_bytes, "originating prompt") if originating_prompt_bytes is not None else None
    counts = {"source": _text_counts(source_text, source_bytes), "descendant": _text_counts(descendant_text, descendant_bytes)}
    repetition = {"source": _repetition_proxy(source_text), "descendant": _repetition_proxy(descendant_text)}
    mechanics = {"source": _mechanics_counts(source_text), "descendant": _mechanics_counts(descendant_text)}
    voice = {"source": _voice_style_proxy(source_text), "descendant": _voice_style_proxy(descendant_text)}
    prompt_overlap = _prompt_lexical_overlap(originating_prompt_bytes, prompt_text, descendant_text)
    flags = _collateral_damage_flags(counts, mechanics, repetition)
    return {
        "analysis_version": ANALYSIS_VERSION,
        "runtime_provenance": {
            "python_version": sys.version,
            "unicodedata_version": unicodedata.unidata_version,
        },
        "interpretation": {
            "classification": "provider_free_descriptive_checks",
            "quality_or_gain_verdict": "not_available",
            "limitations": [
                "Repetition, mechanics, prompt overlap, and voice/style values are mechanical proxies, not literary-quality measures.",
                "Whole-prompt lexical overlap is descriptive only and does not establish semantic instruction-following.",
                "Collateral-damage flags identify predeclared conditions for review; they are not a gain or loss verdict.",
            ],
        },
        "input_hashes": {
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "descendant_sha256": hashlib.sha256(descendant_bytes).hexdigest(),
            "originating_prompt_sha256": hashlib.sha256(originating_prompt_bytes).hexdigest() if originating_prompt_bytes is not None else None,
        },
        "exact_text_counts": {**counts, "descendant_minus_source": _delta(counts["source"], counts["descendant"])},
        "repetition_proxies": {
            "definition": "Lines are casefolded with internal whitespace collapsed; n-grams are casefolded word-token trigrams. Duplicate occurrences equal total eligible occurrences minus unique occurrences.",
            **repetition,
            "descendant_minus_source": _paired_numeric_delta(repetition["source"], repetition["descendant"], ("duplicate_line_occurrences", "duplicate_n_gram_occurrences", "duplicate_n_gram_occurrence_rate")),
        },
        "mechanics_counts": {
            "definition": "Counts only formatting and delimiter patterns. Common delimiters are (), [], {}, ASCII double quotes, and curly double quotes; apostrophes and single quotes are intentionally excluded.",
            **mechanics,
            "descendant_minus_source": {
                "unbalanced_common_delimiter_total": mechanics["descendant"]["unbalanced_common_delimiter_total"] - mechanics["source"]["unbalanced_common_delimiter_total"],
                "repeated_whitespace_runs": mechanics["descendant"]["repeated_whitespace_runs"] - mechanics["source"]["repeated_whitespace_runs"],
                "terminal_punctuation_ratio": round(mechanics["descendant"]["terminal_punctuation"]["ratio"] - mechanics["source"]["terminal_punctuation"]["ratio"], 6),
            },
        },
        "originating_prompt_lexical_overlap": prompt_overlap,
        "voice_style_proxies": {
            "definition": "Non-semantic descriptive proxies only; they do not identify authorship, voice fidelity, or quality.",
            **voice,
            "descendant_minus_source": {
                "dialogue_character_ratio": round(voice["descendant"]["dialogue_character_ratio"] - voice["source"]["dialogue_character_ratio"], 6),
                "first_person_marker_rate": round(voice["descendant"]["first_person_marker_rate"] - voice["source"]["first_person_marker_rate"], 6),
                "type_token_ratio": round(voice["descendant"]["type_token_ratio"] - voice["source"]["type_token_ratio"], 6),
            },
        },
        "collateral_damage_review": {
            "thresholds": COLLATERAL_DAMAGE_THRESHOLDS,
            "flags": flags,
            "has_flags": bool(flags),
            "interpretation": "Flags are review prompts from fixed mechanical thresholds, never a quality or revision-gain verdict.",
        },
    }


def analyze_revision(source_text: str, descendant_text: str, *, originating_prompt: str | None = None) -> dict[str, Any]:
    """String convenience wrapper; file callers should prefer byte-exact inputs."""
    return analyze_revision_bytes(
        source_text.encode("utf-8"), descendant_text.encode("utf-8"),
        originating_prompt_bytes=originating_prompt.encode("utf-8") if originating_prompt is not None else None,
    )


def _read_file(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {path}")
    return path.read_bytes()


def _write_new_output(path: Path, payload: bytes) -> None:
    if not path.parent.is_dir():
        raise ValueError(f"Deterministic-check output parent must already exist: {path.parent}")
    descriptor = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as error:
        raise ValueError(f"Refusing to overwrite existing deterministic-check output: {path}") from error
    except OSError as error:
        raise ValueError(f"Could not publish deterministic-check output: {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _write_stdout(payload: bytes) -> None:
    binary = getattr(sys.stdout, "buffer", None)
    if binary is not None:
        binary.write(payload)
        binary.flush()
    else:
        sys.stdout.write(payload.decode("utf-8"))
        sys.stdout.flush()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Immutable source UTF-8 text file")
    parser.add_argument("--descendant", type=Path, required=True, help="Versioned descendant UTF-8 text file")
    parser.add_argument("--originating-prompt", type=Path, help="Optional originating prompt UTF-8 text file")
    parser.add_argument("--output", type=Path, help="Optional new JSON output path; existing outputs are refused")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = analyze_revision_bytes(
            _read_file(args.source, "source"), _read_file(args.descendant, "descendant"),
            originating_prompt_bytes=_read_file(args.originating_prompt, "originating prompt") if args.originating_prompt else None,
        )
        payload = canonical_json(result) + b"\n"
        if args.output:
            _write_new_output(args.output, payload)
        else:
            _write_stdout(payload)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
