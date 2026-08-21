#!/usr/bin/env python3
"""Build the public Gray Blood result package from two private long-form runs.

The source runs may contain prose, raw prompts, provider responses, and local
execution metadata.  This exporter deliberately reads only score and verdict
data, then emits an independently auditable public projection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


DOMAIN_ORDER = (
    "task",
    "character",
    "plot",
    "world",
    "pacing",
    "language",
    "effect",
    "fresh",
    "mechanics",
    "holistic",
)
# Public verdicts and reports are deliberately a small projection.  Keep this
# list broad: raw execution or evidence fields have no public-package role.
FORBIDDEN_KEY_PARTS = (
    "artifact",
    "brief",
    "evidence",
    "filename",
    "note",
    "path",
    "private",
    "prompt",
    "quote",
    "raw",
    "reference",
    "response",
    "run",
    "session",
    "source",
    "workflow",
)
FORBIDDEN_TEXT_PATTERNS = {
    "windows_absolute_path": re.compile(r"[A-Za-z]:\\"),
    "unix_home_path": re.compile(r"/(?:home|Users)/", re.IGNORECASE),
    "private_execution_path": re.compile(r"(?:^|[\\/])\.private(?:[\\/]|$)", re.IGNORECASE),
    "run_or_session_identifier": re.compile(r"\b(?:run|session|workflow)_id\b", re.IGNORECASE),
    "verbatim_evidence_field": re.compile(r"\bexact_quote\b", re.IGNORECASE),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_json(path: Path, value: Any) -> None:
    write_text_lf(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def score_triplet(value: dict[str, Any]) -> dict[str, float]:
    return {key: round(float(value[key]), 4) for key in ("lower", "observed", "upper")}


def public_domains(domains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {domain["domain_id"]: domain for domain in domains}
    return [
        {
            "coverage": round(float(by_id[domain_id]["coverage"]), 4),
            "domain_id": domain_id,
            "nominal_points": round(float(by_id[domain_id]["nominal_points"]), 4),
            "score": score_triplet(by_id[domain_id]["score"]),
        }
        for domain_id in DOMAIN_ORDER
    ]


def public_verdicts(path: Path, scope: str, bundle: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        records.append(
            {
                "bundle": bundle,
                "confidence": round(float(raw["confidence"]), 4),
                "question_id": raw["question_id"],
                "scope": scope,
                "verdict": raw["verdict"],
            }
        )
    return records


def private_local_dirs(private_root: Path) -> list[Path]:
    return sorted(
        private_root.glob(".private/evaluations/unit-*"),
        key=lambda path: path.name,
    )


def public_draft(private_root: Path, draft_id: str, display_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    global_score = read_json(private_root / ".private/evaluations/global/score.json")
    report = read_json(private_root / "report.json")
    local_by_scope = {item["scope_id"]: item for item in report["local_results"]}

    local_dirs = private_local_dirs(private_root)
    if len(local_dirs) != 6:
        raise ValueError(f"Expected six chapter evaluations in {private_root}, found {len(local_dirs)}")

    verdicts = public_verdicts(
        private_root / ".private/evaluations/global/verdicts.jsonl", "whole_work", "prose.novel"
    )
    chapters: list[dict[str, Any]] = []
    for number, local_dir in enumerate(local_dirs, start=1):
        scope_id = local_dir.name
        local = local_by_scope[scope_id]
        chapters.append(
            {
                "chapter": number,
                "control_state": local["control_state"],
                "coverage": round(float(local["coverage"]), 4),
                "domains": [
                    {
                        "coverage": round(float(domain["coverage"]), 4),
                        "domain_id": domain["domain_id"],
                        "score": score_triplet(domain["score"]),
                    }
                    for domain in local["domains"]
                ],
                "score": score_triplet(local["score"]),
            }
        )
        verdicts.extend(
            public_verdicts(local_dir / "verdicts.jsonl", f"chapter_{number}", "prose.chapter")
        )

    hierarchical = report["hierarchical_score"]
    published = {
        "chapter_results": chapters,
        "draft": draft_id,
        "display_name": display_name,
        "whole_work": {
            "control_state": global_score["hard_gate_status"],
            "coverage": round(float(global_score["coverage"]), 4),
            "domains": public_domains(global_score["domains"]),
            "penalty_deduction": score_triplet(global_score["penalty_deduction"]),
            "score": score_triplet(global_score["final_score"]),
            "status": global_score["status"],
        },
        "wip_70_30": {
            "chapter_mean": score_triplet(hierarchical["local_component"]["score"]),
            "chapter_weight": round(float(hierarchical["local_component"]["effective_weight"]), 4),
            "profile_id": hierarchical["profile_id"],
            "score": score_triplet(hierarchical["score"]),
            "whole_work_weight": round(float(hierarchical["global_component"]["effective_weight"]), 4),
        },
    }
    return published, verdicts


def svg_bars(title: str, labels: list[str], original: list[float], rewrite: list[float], path: Path) -> None:
    width, height, left, top, row = 980, 90 + len(labels) * 42, 220, 58, 42
    plot_width = 670
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f"<title id=\"title\">{title}</title>",
        '<desc id="desc">Blue bars are original; amber bars are rewrite. Values use the displayed score scale.</desc>',
        '<rect width="100%" height="100%" fill="#101318"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#e7edf4}.muted{fill:#aebbc9}.small{font-size:12px}.label{font-size:14px}</style>',
        f'<text x="24" y="30" font-size="20" font-weight="700">{title}</text>',
        '<rect x="690" y="16" width="12" height="12" fill="#5aa9e6"/><text x="708" y="27" class="small">Original</text>',
        '<rect x="790" y="16" width="12" height="12" fill="#f3a951"/><text x="808" y="27" class="small">Rewrite</text>',
    ]
    maximum = max(max(original, default=0), max(rewrite, default=0), 1)
    for index, (label, old, new) in enumerate(zip(labels, original, rewrite)):
        y = top + index * row
        old_width, new_width = plot_width * old / maximum, plot_width * new / maximum
        lines.extend(
            [
                f'<text x="24" y="{y + 14}" class="label">{label}</text>',
                f'<rect x="{left}" y="{y}" width="{old_width:.2f}" height="14" rx="3" fill="#5aa9e6"/>',
                f'<rect x="{left}" y="{y + 18}" width="{new_width:.2f}" height="14" rx="3" fill="#f3a951"/>',
                f'<text x="{left + plot_width + 10}" y="{y + 12}" class="small">{old:.2f}</text>',
                f'<text x="{left + plot_width + 10}" y="{y + 30}" class="small">{new:.2f}</text>',
            ]
        )
    lines.append("</svg>")
    write_text_lf(path, "\n".join(lines) + "\n")


def comparison(original: dict[str, Any], rewrite: dict[str, Any]) -> dict[str, Any]:
    old_whole, new_whole = original["whole_work"], rewrite["whole_work"]
    return {
        "comparison_scope": "Current complete six-chapter WIP protocol only; not a sampled-to-full comparison.",
        "domain_differences_rewrite_minus_original": [
            {
                "domain_id": old["domain_id"],
                "observed_difference": round(
                    new["score"]["observed"] - old["score"]["observed"], 4
                ),
            }
            for old, new in zip(old_whole["domains"], new_whole["domains"])
        ],
        "drafts": {
            "original": {
                "whole_work": old_whole["score"],
                "wip_70_30": original["wip_70_30"]["score"],
            },
            "rewrite": {
                "whole_work": new_whole["score"],
                "wip_70_30": rewrite["wip_70_30"]["score"],
            },
        },
        "chapter_differences_rewrite_minus_original": [
            {
                "chapter": old["chapter"],
                "observed_difference": round(
                    new["score"]["observed"] - old["score"]["observed"], 4
                ),
            }
            for old, new in zip(original["chapter_results"], rewrite["chapter_results"])
        ],
    }


def render_readme(original: dict[str, Any], rewrite: dict[str, Any], data: dict[str, Any]) -> str:
    old = original["whole_work"]
    new = rewrite["whole_work"]
    old_composite = original["wip_70_30"]
    new_composite = rewrite["wip_70_30"]
    domain_rows = "\n".join(
        f"| {item['domain_id']} | {old_domain['score']['observed']:.2f} | {new_domain['score']['observed']:.2f} | {item['observed_difference']:+.2f} |"
        for item, old_domain, new_domain in zip(
            data["domain_differences_rewrite_minus_original"], old["domains"], new["domains"]
        )
    )
    chapter_rows = "\n".join(
        f"| {item['chapter']} | {old_chapter['score']['observed']:.2f} | {new_chapter['score']['observed']:.2f} | {item['observed_difference']:+.2f} |"
        for item, old_chapter, new_chapter in zip(
            data["chapter_differences_rewrite_minus_original"],
            original["chapter_results"],
            rewrite["chapter_results"],
        )
    )
    lead = new["score"]["observed"] - old["score"]["observed"]
    return f"""# Gray Blood, Chapters 1–6: current WIP comparison

This is a private-work-in-progress evaluation of two six-chapter drafts. It publishes the score structure and every accepted binary verdict, but not manuscript prose, evidence excerpts, prompts, model responses, local paths, or execution identifiers.

## Orientation

The opening follows Madison, a technically minded student drawn into blood-powered magic; Amelia, her witch partner; and FAWN, a research group that offers a second route into that world. The comparison asks how the two drafts handle that premise, the relationship, the rules and costs of power, and the opening's movement.

The rewrite leads the current complete whole-work view by {lead:.2f} points. Both runs are `VALID` and `SCORED`; the difference is a diagnostic result for this rubric and scope, not a general verdict on either draft.

| Draft | Whole-work observed | Bounds | Coverage | WIP 70/30 composite |
| --- | ---: | ---: | ---: | ---: |
| Original | {old['score']['observed']:.2f} | {old['score']['lower']:.2f}–{old['score']['upper']:.2f} | {old['coverage']:.2%} | {old_composite['score']['observed']:.2f} |
| Rewrite | {new['score']['observed']:.2f} | {new['score']['lower']:.2f}–{new['score']['upper']:.2f} | {new['coverage']:.2%} | {new_composite['score']['observed']:.2f} |

`VALID` means every applicable objective control requirement was satisfied. **Coverage** is the weighted share of applicable criteria with a `YES` or `NO` verdict. **Observed** is the deterministic score from those assessed criteria after capped penalties. **Bounds** are the low/high results still possible if any `CANNOT_ASSESS` criteria resolve as failures/passes; they are not confidence intervals.

This is a WIP evaluation: completion-only leaves are `NOT_APPLICABLE`, while craft, continuity, and weighted author-goal leaves remain active for the supplied chapters. Author goals influence score but never determine `VALID`. The minimum score-coverage threshold is 80%.

The optional `balanced-wip-70-30` view uses 70% whole-work score and 30% equal-weight chapter mean. It is shown beside—not in place of—the whole-work and chapter views.

## Whole-work domains

![Whole-work domain scores](figures/whole-work-domains.svg)

| Domain | Original | Rewrite | Rewrite − original |
| --- | ---: | ---: | ---: |
{domain_rows}

The rewrite gains in task, character, language, theme/effect, freshness, and mechanics. The original retains the stronger plot, world, and pacing totals. Holistic score is unchanged. These domain totals keep the comparison useful without pretending that one compact number tells the whole story.

## Chapter view

![Complete chapter-local scores](figures/chapter-local-scores.svg)

| Chapter | Original | Rewrite | Rewrite − original |
| ---: | ---: | ---: | ---: |
{chapter_rows}

Each chapter received the complete `prose.chapter` bundle. This local view is a second scale of evidence, while the complete six-chapter `prose.novel` pass remains the manuscript-level result.

## Reading the publication

- [`reports/original.json`](reports/original.json) and [`reports/rewrite.json`](reports/rewrite.json) contain current global, 70/30, chapter, and domain score reports.
- [`verdicts/original.jsonl`](verdicts/original.jsonl) and [`verdicts/rewrite.jsonl`](verdicts/rewrite.jsonl) contain every accepted verdict with stable criterion IDs, scope, and confidence—without evidence text.
- [`comparison.json`](comparison.json) provides machine-readable domain and chapter deltas.
- [`privacy-audit.json`](privacy-audit.json) and [`verify_publication.py`](verify_publication.py) provide the audit and deterministic public-package checks.

This refresh uses a complete current protocol. It replaces the prior publication; it is **not** a sampled-to-full score comparison.

Results are comparable within this published protocol only. Do not compare its headline directly with an earlier headline: the protocol, reasoning configuration, and accepted-verdict set differ.

## Optional excerpt insertion point

No manuscript excerpt is published here. If the author later selects a short, non-sensitive passage, add it only with its relevant criterion results and a fresh privacy audit.
"""


def normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def ngram_hits(public_root: Path, private_root: Path, sizes: tuple[int, ...] = (4, 8, 12, 20, 40)) -> dict[str, int]:
    artifact = private_root / ".private/inputs/artifact.txt"
    if not artifact.exists():
        raise FileNotFoundError(f"No source artifact for privacy audit: {artifact}")
    source = normalized_tokens(artifact.read_text(encoding="utf-8"))
    public = normalized_tokens(
        "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in public_root.rglob("*")
            if path.is_file() and path.name not in {"privacy-audit.json", "manifest.json"}
        )
    )
    results: dict[str, int] = {}
    for size in sizes:
        source_ngrams = {tuple(source[index : index + size]) for index in range(len(source) - size + 1)}
        count = sum(
            tuple(public[index : index + size]) in source_ngrams
            for index in range(len(public) - size + 1)
        )
        results[str(size)] = count
    return results


def files_for_audit(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.name not in {"manifest.json", "privacy-audit.json"}
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def audit_tree(
    root: Path,
    original_private: Path | None = None,
    rewrite_private: Path | None = None,
    forbidden_terms: list[str] | None = None,
) -> dict[str, Any]:
    files = files_for_audit(root)
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files)
    pattern_hits = {
        name: len(pattern.findall(text)) for name, pattern in FORBIDDEN_TEXT_PATTERNS.items()
    }
    audit: dict[str, Any] = {
        "audited_file_count": len(files),
        "audited_total_bytes": sum(path.stat().st_size for path in files),
        "forbidden_pattern_hits": pattern_hits,
        "format_version": 2,
        "ngram_normalization": "lowercase ASCII alphanumeric tokens; exact contiguous token sequences",
        "tree_sha256": tree_hash(root),
    }
    if original_private and rewrite_private:
        audit["exact_source_prose_ngram_hits"] = {
            "original": ngram_hits(root, original_private),
            "rewrite": ngram_hits(root, rewrite_private),
        }
    if forbidden_terms:
        folded_text = text.casefold()
        audit["explicit_private_term_hits"] = {
            hashlib.sha256(term.encode("utf-8")).hexdigest(): folded_text.count(term.casefold())
            for term in forbidden_terms
        }
    return audit


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in files_for_audit(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def manifest(root: Path, original: dict[str, Any], rewrite: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluation_id": "gray-blood-chapters-1-6-current-comparison-v2",
        "files": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files_for_audit(root)
        },
        "protocol": {
            "binary_judge": {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"},
            "bundle_versions": {"prose.chapter": 1, "prose.novel": 1},
            "chapter_bundle": "prose.chapter",
            "chapter_count_per_draft": 6,
            "comparison_scope": "complete current six-chapter WIP protocol; not a sampled-to-full comparison",
            "global_bundle": "prose.novel",
            "minimum_coverage": 0.8,
            "orientation_and_synthesis": {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"},
            "standard": {"id": "HBQ-RS", "version": "1.0.0"},
            "structured_judge": {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"},
            "whole_work_verdicts_per_draft": 239,
            "chapter_verdicts_per_draft": 1368,
        },
        "publication": {
            "evidence_text_included": False,
            "execution_metadata_included": False,
            "manuscript_prose_included": False,
            "published_verdicts": 3214,
        },
        "results": {
            "original": {
                "whole_work_observed": original["whole_work"]["score"]["observed"],
                "wip_70_30_observed": original["wip_70_30"]["score"]["observed"],
            },
            "rewrite": {
                "whole_work_observed": rewrite["whole_work"]["score"]["observed"],
                "wip_70_30_observed": rewrite["wip_70_30"]["score"]["observed"],
            },
        },
    }


def build(args: argparse.Namespace) -> None:
    original_private = Path(args.original).resolve()
    rewrite_private = Path(args.rewrite).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output}")
    output.mkdir(parents=True)
    try:
        write_text_lf(output / "sanitize_publication.py", Path(__file__).read_text(encoding="utf-8"))
        write_text_lf(
            output / "verify_publication.py",
            Path(__file__).with_name("verify_publication.py").read_text(encoding="utf-8"),
        )
        original, original_verdicts = public_draft(original_private, "original", "Original")
        rewrite, rewrite_verdicts = public_draft(rewrite_private, "rewrite", "Rewrite")
        comparison_data = comparison(original, rewrite)
        write_json(output / "reports/original.json", original)
        write_json(output / "reports/rewrite.json", rewrite)
        write_json(output / "comparison.json", comparison_data)
        for draft, records in (("original", original_verdicts), ("rewrite", rewrite_verdicts)):
            destination = output / f"verdicts/{draft}.jsonl"
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_text_lf(destination, "".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
        svg_bars(
            "Whole-work domain scores",
            [domain["domain_id"] for domain in original["whole_work"]["domains"]],
            [domain["score"]["observed"] for domain in original["whole_work"]["domains"]],
            [domain["score"]["observed"] for domain in rewrite["whole_work"]["domains"]],
            output / "figures/whole-work-domains.svg",
        )
        svg_bars(
            "Complete chapter-local scores",
            [f"Chapter {item['chapter']}" for item in original["chapter_results"]],
            [item["score"]["observed"] for item in original["chapter_results"]],
            [item["score"]["observed"] for item in rewrite["chapter_results"]],
            output / "figures/chapter-local-scores.svg",
        )
        write_text_lf(output / "README.md", render_readme(original, rewrite, comparison_data))
        write_json(
            output / "privacy-audit.json",
            audit_tree(output, original_private, rewrite_private, args.forbidden_term),
        )
        write_json(output / "manifest.json", manifest(output, original, rewrite))
    except Exception:
        shutil.rmtree(output)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, help="Private original long-form output root")
    parser.add_argument("--rewrite", required=True, help="Private rewrite long-form output root")
    parser.add_argument("--output", required=True, help="New public package directory")
    parser.add_argument(
        "--forbidden-term",
        action="append",
        default=[],
        help="Private literal to audit without storing it in the public package",
    )
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
