"""Retrospective scalar-order diagnostics on the opened HANNA repeat panel."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.util
from itertools import combinations
import json
import os
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_multisample_human_direction_v1"
PROFILE_SHA = "d1e9d5cc3432f5edaeba63f2c4d74fba0dac87364f26ad8f3f1bc08f123c8767"
SIGNS = (-1, 0, 1)
RATE_FIELDS = ("correct_rate_on_strict_reference_pairs", "wrong_rate_on_strict_reference_pairs",
               "directional_coverage_on_strict_reference_pairs", "directional_coverage_on_all_pairs")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def ratio(count, denominator):
    if not denominator:
        return None
    value = Fraction(count, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def sign(value):
    return (value > 0) - (value < 0)


def direction_table(items, scores, human):
    table = {str(h): {str(m): 0 for m in SIGNS} for h in SIGNS}
    pairs = list(combinations(sorted(items), 2))
    for left, right in pairs:
        table[str(sign(human[left] - human[right]))][str(sign(scores[left] - scores[right]))] += 1
    return table_statistics(table)

def views(items, by_item):
    return [("repetition", repetition + 1, {item: by_item[item][repetition] for item in items})
            for repetition in range(5)] + [("repeat_mean", None,
                {item: sum(by_item[item], Fraction()) / 5 for item in items})]


def scopes(items, scores, human, prompts):
    pairs = list(combinations(sorted(items), 2))
    same = [pair for pair in pairs if prompts[pair[0]] == prompts[pair[1]]]
    across = [pair for pair in pairs if prompts[pair[0]] != prompts[pair[1]]]
    # Selecting pair endpoints separately would accidentally introduce new cross-pairs.
    def selected(pairs):
        table = {str(h): {str(m): 0 for m in SIGNS} for h in SIGNS}
        for left, right in pairs:
            table[str(sign(human[left] - human[right]))][str(sign(scores[left] - scores[right]))] += 1
        return table_statistics(table)
    return {"all_pairs": direction_table(items, scores, human),
            "same_origin_prompt_pairs": selected(same), "across_origin_prompt_pairs": selected(across)}


def table_statistics(table):
    correct = table["-1"]["-1"] + table["1"]["1"]
    wrong = table["-1"]["1"] + table["1"]["-1"]
    tied = table["-1"]["0"] + table["1"]["0"]
    human_directions = table["0"]["-1"] + table["0"]["1"]
    both = table["0"]["0"]
    strict, planned = correct + wrong + tied, sum(sum(row.values()) for row in table.values())
    require(strict + human_directions + both == planned, "Pair accounting differs")
    return {"planned_item_pairs": planned, "available_item_pairs": planned, "missing_item_pairs": 0,
        "sign_table": table, "strict_reference_pairs": strict, "human_tied_pairs": human_directions + both,
        "correct_directions": correct, "wrong_directions": wrong,
        "usable_directions_on_strict_reference_pairs": correct + wrong,
        "model_ties_on_strict_reference_pairs": tied, "model_directions_on_human_tied_pairs": human_directions,
        "model_ties_on_human_tied_pairs": both, "model_ties_on_all_pairs": tied + both,
        "model_directions_on_all_pairs": correct + wrong + human_directions,
        "correct_rate_on_strict_reference_pairs": ratio(correct, strict),
        "wrong_rate_on_strict_reference_pairs": ratio(wrong, strict),
        "directional_coverage_on_strict_reference_pairs": ratio(correct + wrong, strict),
        "directional_coverage_on_all_pairs": ratio(correct + wrong + human_directions, planned)}


def calculate(panel, prompts, cohorts, human, profile):
    rows, sensitivity = [], []
    for cohort, items in cohorts.items():
        groups = sorted({prompts[item] for item in items})
        planned = profile["cohorts"][cohort]
        require(len(items) * (len(items) - 1) // 2 == planned["planned_pairs"] and
                sum(prompts[a] == prompts[b] for a, b in combinations(items, 2)) == planned["same_prompt_pairs"],
                "Planned pair/prompt geometry differs")
        for arm, by_item in panel.items():
            for view, repetition, scores in views(items, by_item):
                base = {"cohort": cohort, "arm": arm, "view": view, "repetition": repetition}
                rows.append({**base, "planned_items": len(items), "prompt_clusters": len(groups),
                             **scopes(items, scores, human, prompts)})
                omissions = []
                for ordinal, omitted in enumerate(groups, 1):
                    remaining = [item for item in items if prompts[item] != omitted]
                    omissions.append({"omission": ordinal, "remaining_items": len(remaining),
                        "remaining_prompt_clusters": len(groups) - 1,
                        **scopes(remaining, scores, human, prompts)})
                ranges = {}
                for scope in ("all_pairs", "same_origin_prompt_pairs", "across_origin_prompt_pairs"):
                    ranges[scope] = {}
                    for field in RATE_FIELDS:
                        values = [row[scope][field] for row in omissions if row[scope][field] is not None]
                        numeric = [Fraction(v["numerator"], v["denominator"]) for v in values]
                        ranges[scope][field] = {"defined_omissions": len(values),
                            "undefined_omissions": len(omissions) - len(values),
                            "minimum": ratio(min(numeric).numerator, min(numeric).denominator) if numeric else None,
                            "maximum": ratio(max(numeric).numerator, max(numeric).denominator) if numeric else None}
                sensitivity.append({**base, "omissions": omissions, "rate_ranges": ranges,
                                    "confidence_interval": False})
    require(len(rows) == len(sensitivity) == 72 and
            sum(row["all_pairs"]["planned_item_pairs"] for row in rows) == 900,
            "Full diagnostic denominator differs")
    return rows, sensitivity


def load_inputs(source, frozen_path, profile):
    tracked = {}
    def checked(path, pin):
        raw = path.read_bytes()
        require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Input commitment differs")
        tracked[path] = raw
        return raw
    base_raw = checked(REPO / profile["base_helper"]["locator"], profile["base_helper"])
    base_profile_raw = checked(REPO / profile["base_profile"]["locator"], profile["base_profile"])
    spec = importlib.util.spec_from_file_location("pinned_multisample_floor", REPO / profile["base_helper"]["locator"])
    base = importlib.util.module_from_spec(spec)
    exec(compile(base_raw, str(spec.origin), "exec"), base.__dict__)
    base_profile = json.loads(base_profile_raw)
    require(profile["source_pins"] == base_profile["source_pins"], "Inherited source pins differ")
    source_raw = {name: checked(source / pin["locator"], pin) for name, pin in base_profile["source_pins"].items()}
    repository_raw = {name: checked(REPO / pin["locator"], pin) for name, pin in base_profile["repository_pins"].items()}
    panel, prompts, cohorts = base.preflight(source, base_profile, repository_raw, source_raw)
    namespace = base.extract(repository_raw["lexical_reader"], ("require", "project_json"), {
        "json": SimpleNamespace(JSONDecoder=lambda: json.JSONDecoder(parse_float=Decimal,
            parse_constant=base.reject_constant))})
    project = namespace["project_json"]
    provenance = project(source_raw["consolidation-provenance.json"], {"frozen_contract": {"path": True, "sha256": True}})
    require(Path(provenance["frozen_contract"]["path"]).resolve() == frozen_path and
            provenance["frozen_contract"]["sha256"] == profile["frozen_contract"]["sha256"],
            "Frozen human-reference locator binding differs")
    frozen_raw = checked(frozen_path, profile["frozen_contract"])
    frozen = project(frozen_raw, {"samples": [{"item_id": True, "prompt_sha256": True, "human_overall": True}]})
    require(len(frozen["samples"]) == 11 and len({r["item_id"] for r in frozen["samples"]}) == 11,
            "Frozen human-reference geometry differs")
    human = {r["item_id"]: base.scalar(r["human_overall"]) for r in frozen["samples"]}
    require(set(human) == set(prompts) and all(1 <= value <= 5 for value in human.values()) and
            all(r["prompt_sha256"] == prompts[r["item_id"]] for r in frozen["samples"]),
            "Frozen reference item/prompt bindings differ")
    selected = project(source_raw["summary.json"], {"arms": {arm: {"per_sample": [
        {"item_id": True, "prompt_sha256": True, "human_overall": True}]} for arm in panel}})
    for arm in panel:
        rows = selected["arms"][arm]["per_sample"]
        require(len(rows) == 11 and len({r["item_id"] for r in rows}) == 11 and
                {r["item_id"] for r in rows} == set(human) and
                all(base.scalar(r["human_overall"]) == human[r["item_id"]] and
                    r["prompt_sha256"] == prompts[r["item_id"]] for r in rows),
                "Consolidated human references differ across arms or frozen samples")
    return panel, prompts, cohorts, human, tracked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--frozen-contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    source, frozen, output = args.source_root.resolve(), args.frozen_contract.resolve(), args.output_root.resolve()
    require(not output.exists() and all(not output.is_relative_to(p) and not p.is_relative_to(output)
            for p in (REPO, source, frozen.parent)), "Fresh output outside repository and inputs required")
    profile_raw, code = (HERE / "profile.json").read_bytes(), Path(__file__).read_bytes()
    require(sha(profile_raw) == PROFILE_SHA, "Frozen profile differs")
    profile = json.loads(profile_raw)
    require(profile["policy"] == POLICY and profile["planned_rows"] == 72 and
            profile["planned_pair_comparisons"] == 900, "Diagnostic profile differs")
    panel, prompts, cohorts, human, tracked = load_inputs(source, frozen, profile)
    rows, sensitivity = calculate(panel, prompts, cohorts, human, profile)
    report = {"schema_version": 1, "policy": POLICY, "profile_sha256": sha(profile_raw),
        "implementation_sha256": sha(code), "source_pins": profile["source_pins"],
        "base_helper": profile["base_helper"], "base_profile": profile["base_profile"],
        "frozen_contract": profile["frozen_contract"], "planned_rows": 72,
        "planned_pair_comparisons": 900, "available_pair_comparisons": 900, "missing_pair_comparisons": 0,
        "rows": rows, "leave_one_prompt_cluster_out": sensitivity,
        "interpretation": profile["interpretation"], "human_reference_aggregate_decoded": True,
        "raw_human_ratings_decoded": False, "prose_or_responses_decoded": False,
        "native_replayed": False, "provider_calls_made": 0, "new_provider_votes": 0}
    report_raw = canonical(report)
    require(all(path.read_bytes() == raw for path, raw in tracked.items()) and
            (HERE / "profile.json").read_bytes() == profile_raw and Path(__file__).read_bytes() == code,
            "An input changed during analysis")
    output.mkdir(parents=True, exist_ok=False)
    contents = {"report.json": report_raw, "profile.json": profile_raw, "analyze.py": code}
    for name, raw in contents.items():
        with (output / name).open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require((output / name).read_bytes() == raw, "Output readback differs")
    terminal = {"policy": POLICY, "state": "completed", "completed_utc": datetime.now(timezone.utc).isoformat(),
        "report_sha256": sha(report_raw), "profile_sha256": sha(profile_raw), "implementation_sha256": sha(code),
        "rows": 72, "pair_comparisons": 900, "provider_calls_made": 0, "new_provider_votes": 0}
    raw = canonical(terminal)
    with (output / "terminal.json").open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require((output / "terminal.json").read_bytes() == raw, "Terminal readback differs")
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
