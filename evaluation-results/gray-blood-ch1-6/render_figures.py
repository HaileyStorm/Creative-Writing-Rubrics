"""Render the case-study SVGs from the published score and verdict files."""

from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verdicts(path: Path) -> dict[str, str]:
    return {
        record["question_id"]: record["verdict"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for record in [json.loads(line)]
    }


def domain_comparison() -> str:
    reports = {name: _json(ROOT / "whole" / f"{name}-score.json") for name in ("original", "new")}
    by_name = {
        name: {
            domain["domain_id"]: 100 * domain["score"]["observed"] / domain["nominal_points"]
            for domain in report["domains"]
            if domain["score"]["observed"] is not None
        }
        for name, report in reports.items()
    }
    titles = {domain["domain_id"]: domain["title"] for domain in reports["original"]["domains"]}
    order = [domain["domain_id"] for domain in reports["original"]["domains"]]
    width, left, right, top, row = 960, 190, 56, 86, 42
    chart = width - left - right
    height = top + len(order) * row + 54
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Whole-work domain comparison</title>',
        '<desc id="desc">Original and rewrite observed domain scores normalized to each domain’s available points.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="30" font-family="sans-serif" font-size="20" font-weight="700" fill="#111827">Whole-work domain comparison</text>',
        '<circle cx="28" cy="57" r="6" fill="#2563eb"/><text x="42" y="61" font-family="sans-serif" font-size="12" fill="#374151">Original</text>',
        '<circle cx="116" cy="57" r="6" fill="#d97706"/><text x="130" y="61" font-family="sans-serif" font-size="12" fill="#374151">Rewrite</text>',
    ]
    for tick in range(0, 101, 20):
        x = left + chart * tick / 100
        parts.extend(
            [
                f'<line x1="{x:.1f}" y1="{top - 16}" x2="{x:.1f}" y2="{height - 38}" stroke="#e5e7eb"/>',
                f'<text x="{x:.1f}" y="{height - 16}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#6b7280">{tick}%</text>',
            ]
        )
    for index, domain_id in enumerate(order):
        y = top + index * row
        original = by_name["original"][domain_id]
        rewrite = by_name["new"][domain_id]
        x1 = left + chart * original / 100
        x2 = left + chart * rewrite / 100
        parts.extend(
            [
                f'<text x="{left - 14}" y="{y + 4}" text-anchor="end" font-family="sans-serif" font-size="12" fill="#111827">{escape(titles[domain_id])}</text>',
                f'<line x1="{min(x1, x2):.1f}" y1="{y}" x2="{max(x1, x2):.1f}" y2="{y}" stroke="#9ca3af" stroke-width="2"/>',
                f'<circle cx="{x1:.1f}" cy="{y}" r="6" fill="#2563eb"><title>Original {original:.1f}%</title></circle>',
                f'<circle cx="{x2:.1f}" cy="{y}" r="6" fill="#d97706"><title>Rewrite {rewrite:.1f}%</title></circle>',
                f'<text x="{x1:.1f}" y="{y - 10}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#1d4ed8">{original:.1f}</text>',
                f'<text x="{x2:.1f}" y="{y + 18}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#b45309">{rewrite:.1f}</text>',
            ]
        )
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def chapter_transitions() -> str:
    rows = []
    for chapter in range(1, 7):
        original = _verdicts(ROOT / "chapters" / "original" / f"chapter-{chapter:02d}-verdicts.jsonl")
        rewrite = _verdicts(ROOT / "chapters" / "new" / f"chapter-{chapter:02d}-verdicts.jsonl")
        counts = Counter()
        for question_id, before in original.items():
            after = rewrite[question_id]
            if before == after:
                counts["unchanged"] += 1
            elif before == "NO" and after == "YES":
                counts["improved"] += 1
            elif before == "YES" and after == "NO":
                counts["regressed"] += 1
            else:
                counts["control shift"] += 1
        rows.append((chapter, counts))
    width, left, right, top, row = 960, 130, 68, 94, 48
    chart = width - left - right
    height = top + len(rows) * row + 58
    colors = {"improved": "#059669", "regressed": "#dc2626", "unchanged": "#9ca3af", "control shift": "#7c3aed"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Paired chapter-diagnostic verdict transitions</title>',
        '<desc id="desc">Counts of the 28 paired selected-question verdicts that improved, regressed, stayed unchanged, or changed assessability state in each chapter.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="30" font-family="sans-serif" font-size="20" font-weight="700" fill="#111827">Paired chapter-diagnostic verdict transitions</text>',
    ]
    legend_x = 24
    for name in ("improved", "regressed", "unchanged", "control shift"):
        parts.extend(
            [
                f'<rect x="{legend_x}" y="48" width="12" height="12" fill="{colors[name]}"/>',
                f'<text x="{legend_x + 18}" y="59" font-family="sans-serif" font-size="12" fill="#374151">{name.title()}</text>',
            ]
        )
        legend_x += 46 + len(name) * 7
    for tick in range(0, 29, 7):
        x = left + chart * tick / 28
        parts.extend(
            [
                f'<line x1="{x:.1f}" y1="{top - 14}" x2="{x:.1f}" y2="{height - 42}" stroke="#e5e7eb"/>',
                f'<text x="{x:.1f}" y="{height - 18}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#6b7280">{tick}</text>',
            ]
        )
    for index, (chapter, counts) in enumerate(rows):
        y = top + index * row
        parts.append(f'<text x="{left - 14}" y="{y + 17}" text-anchor="end" font-family="sans-serif" font-size="12" fill="#111827">Chapter {chapter}</text>')
        x = left
        for name in ("improved", "regressed", "unchanged", "control shift"):
            count = counts[name]
            segment = chart * count / 28
            if count:
                parts.extend(
                    [
                        f'<rect x="{x:.1f}" y="{y}" width="{segment:.1f}" height="26" fill="{colors[name]}"><title>{name.title()}: {count}</title></rect>',
                        f'<text x="{x + segment / 2:.1f}" y="{y + 18}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#ffffff">{count}</text>',
                    ]
                )
            x += segment
    parts.append(f'<text x="{left}" y="{height - 4}" font-family="sans-serif" font-size="11" fill="#6b7280">Each bar contains the same 28 selected leaves; these are transitions, not chapter grades.</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    (FIGURES / "domain-comparison.svg").write_text(domain_comparison(), encoding="utf-8")
    (FIGURES / "chapter-verdict-transitions.svg").write_text(chapter_transitions(), encoding="utf-8")


if __name__ == "__main__":
    main()
