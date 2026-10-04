"""Development-only metadata selection and mechanical, outcome-blind text extraction."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "mfa_two_target_development_quality_v1"
PINS = {
    "private-metadata.json": "ba0b418384d55af5b3b97ca40acc67e82f71eebff3fc22d0011196d5870e600a",
    "summary.json": "5a224007e7c7b264c464c47de0d8c8a1c529dc3913b5c32510fa2dd46373ed94",
    "source-recipe.json": "74acddc9ac4c60d0ad813046ef33191e880365a3460c0e356475daf5a04abc77",
    "private-membership.json": "202ec58ddc0e4cb103bbb62b31c250d92bd8d53bdee84d73f52d4bd1dc0cda6e",
    "partition-summary.json": "e27a1ce3c90cde9719f2e7c186145247cae1fc12fc1ad8f17ae4fe12644bfa09",
}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def within(root, relative):
    root = Path(root).resolve()
    destination = (root / relative).resolve()
    require(destination.is_relative_to(root), "Artifact path escapes input root")
    return destination


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def private_output(path, inputs):
    path = Path(path).resolve()
    require(not path.exists(), "Output must be fresh")
    for root in [REPO, *map(Path, inputs)]:
        root = root.resolve()
        require(not path.is_relative_to(root) and not root.is_relative_to(path),
                "Output overlaps repository or retained inputs")
    return path


def load_inputs(metadata_root, partition_root):
    files = {}
    for name in ("private-metadata.json", "summary.json", "source-recipe.json"):
        files[name] = within(metadata_root, name).read_bytes()
    files["private-membership.json"] = within(partition_root, "private-membership.json").read_bytes()
    files["partition-summary.json"] = within(partition_root, "summary.json").read_bytes()
    for name, raw in files.items():
        require(sha(raw) == PINS[name], "Pinned metadata or partition bytes differ")
    metadata = json.loads(files["private-metadata.json"])
    summary = json.loads(files["summary.json"])
    ledger = json.loads(files["private-membership.json"])
    partition_summary = json.loads(files["partition-summary.json"])
    require(partition_summary["private_membership_ledger_sha256"] == sha(files["private-membership.json"]),
            "Partition ledger commitment differs")
    require(all(summary.get(key) is False for key in
                ("target_values_released", "rationales_released", "excerpts_released")), "Metadata seal is not blinded")
    return select(metadata, ledger, summary["source_receipts"]), files


def select(metadata, ledger, source_receipts):
    """Select one fine and one fewshot-only development target using hashes only."""
    rows = metadata["rows"]
    components = ledger["components"]
    assignments, forced = {}, set()
    for component in components:
        for target in component["target_hashes"]:
            require(target not in assignments, "Duplicate target partition")
            assignments[target] = component["partition"]
            if component["forced_development"]:
                require(component["partition"] == "development", "Exposed component outside development")
                forced.add(target)
    quality = [r for r in rows if r["release"] == "author-style" and r["task"] == "quality"]
    fine = {r["target_hash"] for r in quality if r["condition"] == "finetuned"}
    development = {t for t, part in assignments.items() if part == "development"}
    available = {r["target_hash"] for r in quality}
    strata = (development & available & fine, (development & available) - fine)
    require(all(strata), "Both development strata are required")
    chosen = [min(group, key=lambda t: (t not in forced, t)) for group in strata]
    require(len(set(chosen)) == 2 and all(assignments[t] == "development" for t in chosen),
            "Selection must contain exactly two development targets")
    selected_rows = [r for r in quality if r["target_hash"] in chosen]
    require(all(r["panel"] in ("expert", "lay") and r["original_hash"] is None for r in selected_rows),
            "Only no-reference primary expert/lay quality rows are permitted")
    row_index = {sha(canonical(r)): r for r in selected_rows}
    require(len(row_index) == len(selected_rows), "Duplicate exact metadata rows")
    units = [u for u in ledger["evaluation_units"] if u["release"] == "author-style"
             and u["task"] == "quality" and u["target_hash"] in chosen]
    joined = []
    for unit in units:
        require(unit["partition"] == "development" and unit["eligible"] and unit["row_original_hash"] is None,
                "Confirmation, unassigned or reference-conditioned unit rejected")
        require(unit["rows"] == len(unit["row_memberships"]), "Unit row count differs")
        for membership in unit["row_memberships"]:
            key = membership["metadata_row_sha256"]
            require(key in row_index, "Unit references absent selected metadata row")
            row = row_index[key]
            require(all(row[k] == unit[k] for k in ("release", "task", "panel", "condition", "target_hash"))
                    and sorted(row["excerpt_hashes"]) == unit["candidate_excerpt_hashes"]
                    and row["writer_hash"] == membership["writer_hash"]
                    and row["ordered_pair_hash"] == membership["ordered_pair_hash"], "Unit membership differs")
            joined.append(key)
    require(len(joined) == len(set(joined)) and set(joined) == set(row_index), "Incomplete expert/lay quality row join")
    require(all({r["panel"] for r in selected_rows if r["target_hash"] == t} == {"expert", "lay"} for t in chosen),
            "Both panels must be complete for each target")
    texts, pairs = {}, {}
    for row in selected_rows:
        for digest, size in zip(row["excerpt_hashes"], row["excerpt_bytes"]):
            if digest in texts:
                require(texts[digest]["bytes"] == size, "Text hash has conflicting lengths")
            texts.setdefault(digest, {"id": "mfa-" + digest, "sha256": digest, "bytes": size, "target_hashes": []})
            if row["target_hash"] not in texts[digest]["target_hashes"]:
                texts[digest]["target_hashes"].append(row["target_hash"])
        identity = {"target_hash": row["target_hash"], "condition": row["condition"],
                    "excerpt_hashes": sorted(row["excerpt_hashes"])}
        key = sha(canonical(identity))
        pair = pairs.setdefault(key, {**identity, "pair_id": key, "unit_sha256s": [], "metadata_row_sha256s": [],
                                      "ordered_pair_hashes": []})
        pair["metadata_row_sha256s"].append(sha(canonical(row)))
        if row["ordered_pair_hash"] not in pair["ordered_pair_hashes"]:
            pair["ordered_pair_hashes"].append(row["ordered_pair_hash"])
    for unit in units:
        key = sha(canonical({"target_hash": unit["target_hash"], "condition": unit["condition"],
                             "excerpt_hashes": unit["candidate_excerpt_hashes"]}))
        pairs[key]["unit_sha256s"].append(unit["unit_sha256"])
    sentinels, pair_sentinels = [], []
    for target in chosen:
        candidates = sorted([t for t in texts.values() if target in t["target_hashes"]],
                            key=lambda t: (t["bytes"], t["sha256"]))
        sentinels.append(candidates[(len(candidates) - 1) // 2]["id"])
        target_pairs = [p for p in pairs.values() if p["target_hash"] == target]
        pair_sentinels.append(min(target_pairs, key=lambda p: (p["condition"] != "finetuned" if target in fine else False,
                                                               p["pair_id"]))["pair_id"])
    sources = {r["source_path"] for r in selected_rows}
    receipts = [r for r in source_receipts if r["release"] == "author-style" and r["path"] in sources]
    require({r["path"] for r in receipts} == sources and len(receipts) == len(sources), "Missing selected source receipts")
    result = {"policy": POLICY, "partition": "development", "release": "author-style", "task": "quality",
              "selected_targets": [{"target_hash": t, "stratum": "fine" if t in fine else "fewshot_only",
                                     "quarantined": t in forced} for t in chosen],
              "selection_rule": "per-stratum minimum (not forced_development, target_hash); no target values",
              "metadata_rows": selected_rows, "evaluation_units": units,
              "texts": sorted(texts.values(), key=lambda t: t["id"]),
              "pairs": sorted(pairs.values(), key=lambda p: p["pair_id"]),
              "bank_sentinel_ids": sentinels, "pair_sentinel_ids": pair_sentinels, "source_receipts": receipts}
    result["selection_sha256"] = sha(canonical(result))
    return result


def selected_texts(data, rows):
    """Only exact positional Excerpt1/Excerpt2 fields leave the parsed source."""
    require(isinstance(data, dict), "Unexpected source root")
    targets = list(data.items())
    texts = {}
    for row in rows:
        require(row["release"] == "author-style" and row["task"] == "quality", "Only primary quality extraction is permitted")
        target, writers = targets[row["target_position"]]
        require(sha(canonical(target)) == row["target_hash"] and isinstance(writers, dict), "Target position or identity differs")
        writer, judgments = list(writers.items())[row["writer_position"]]
        require(sha(canonical(writer)) == row["writer_hash"] and isinstance(judgments, list), "Writer position or identity differs")
        judgment = judgments[row["source_position"]]
        require(isinstance(judgment, list) and len(judgment) in (2, 3) and isinstance(judgment[-1], dict), "Judgment envelope differs")
        record = judgment[-1]
        rater = judgment[1] if len(judgment) == 3 else record.get("user")
        require(sha(canonical(rater)) == row["rater_hash"]
                and sha(canonical(record.get("id"))) == row["judgment_identity_hash"], "Record or rater identity differs")
        for index, field in enumerate(("Excerpt1", "Excerpt2")):
            text = record.get(field)
            require(isinstance(text, str) and bool(text), "Missing committed candidate text")
            raw = text.encode("utf-8")
            require(sha(raw) == row["excerpt_hashes"][index] and len(raw) == row["excerpt_bytes"][index], "Exact text hash, order or length differs")
            texts[row["excerpt_hashes"][index]] = raw
    return texts


def extract_source(selection, source_root):
    texts = {}
    for receipt in selection["source_receipts"]:
        raw = within(source_root, "author-style/" + receipt["path"]).read_bytes()
        require(len(raw) == receipt["bytes"] and sha(raw) == receipt["sha256"], "Sealed source bytes differ")
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == receipt["git_blob_sha1"], "Sealed source Git blob differs")
        rows = [r for r in selection["metadata_rows"] if r["source_path"] == receipt["path"]]
        texts.update(selected_texts(json.loads(raw), rows))
    require(set(texts) == {t["sha256"] for t in selection["texts"]}, "Incomplete selected text extraction")
    return texts


def summary(selection):
    return {"policy": POLICY, "partition": "development", "targets": len(selection["selected_targets"]),
            "quarantined_targets": sum(t["quarantined"] for t in selection["selected_targets"]),
            "unique_texts": len(selection["texts"]), "pairs": len(selection["pairs"]),
            "evaluation_units": len(selection["evaluation_units"]), "metadata_rows": len(selection["metadata_rows"]),
            "rows_by_panel_condition": dict(Counter(r["panel"] + ":" + r["condition"] for r in selection["metadata_rows"])),
            "selection_sha256": selection["selection_sha256"], "provider_calls": 0, "labels_released": False,
            "human_alignment_claim": False, "fresh_confirmation_claim": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-root", required=True, type=Path)
    parser.add_argument("--partition-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    selection, input_files = load_inputs(args.metadata_root, args.partition_root)
    output = private_output(args.output_root, [args.metadata_root, args.partition_root, *([args.source_root] if args.source_root else [])])
    result = summary(selection)
    if not args.dry_run:
        require(args.source_root is not None, "Actual extraction requires the reviewed retained source root")
        texts = extract_source(selection, args.source_root)
        files = {"selection.json": canonical(selection), "implementation/extract.py": Path(__file__).read_bytes()}
        files.update({"commitments/" + name: raw for name, raw in input_files.items() if name != "private-metadata.json" and name != "private-membership.json"})
        files.update({"inputs/" + digest + ".txt": raw for digest, raw in texts.items()})
        inventory = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}
        receipt = {**result, "artifacts": inventory, "source_pins": PINS, "text_fields_only": ["Excerpt1", "Excerpt2"]}
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            write_new(output / name, raw)
        write_new(output / "extraction.json", canonical(receipt))
        result["extraction_sha256"] = sha(canonical(receipt))
    print(json.dumps({**result, "dry_run": args.dry_run, "source_texts_read": not args.dry_run}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
