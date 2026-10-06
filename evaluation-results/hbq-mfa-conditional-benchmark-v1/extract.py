"""Source-disjoint conditional benchmark membership and positional text projection."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "mfa_conditional_outcome_blind_benchmark_v1"
READER_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
ROW_FIELDS = "condition excerpt_bytes excerpt_hashes judgment_identity_hash metadata_record_hash ordered_pair_hash original_bytes original_hash original_is_text original_present pair_hash panel rater_hash release source_path source_position target_hash target_position task writer_hash writer_position".split()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, digest):
    raw = Path(path).read_bytes()
    require(sha(raw) == digest, "Pinned source bytes differ: " + str(path))
    return raw


@lru_cache(maxsize=1)
def metadata_reader():
    raw = checked(HERE.parent / "hbq-matched-hanna-20261004/prepare.py", READER_SHA)
    tree = ast.parse(raw.decode("utf-8"))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ("require", "project_json")]
    namespace = {"json": json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "pinned_metadata_reader", "exec"), namespace)
    return namespace["project_json"]


def within(root, relative):
    root = Path(root).resolve()
    destination = (root / relative).resolve()
    require(destination.is_relative_to(root), "Artifact escapes input root")
    return destination


def private_output(path, inputs):
    path = Path(path).resolve()
    require(not path.exists(), "Output must be fresh")
    for root in [REPO, *map(Path, inputs)]:
        root = root.resolve()
        require(not path.is_relative_to(root) and not root.is_relative_to(path), "Output overlaps retained input")
    return path


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def profile():
    raw = (HERE / "membership-profile.json").read_bytes()
    value = json.loads(raw)
    require(value["policy"] == POLICY and value["ballot_field"] == "Preference"
            and value["ballots_per_source_row"] == 1 and value["primary_repeat"] == 0,
            "Benchmark membership policy differs")
    checked(HERE.parent / "hbq-matched-mfa-v1/ladder-candidate-profile.json",
            value["candidate_profile_sha256"])
    return value, raw


def load_inputs(metadata_root, partition_root, audit_root):
    policy, policy_raw = profile()
    locations = {name: within(metadata_root, name) for name in
                 ("private-metadata.json", "summary.json", "source-recipe.json")}
    locations.update({"private-membership.json": within(partition_root, "private-membership.json"),
                      "partition-summary.json": within(partition_root, "summary.json"),
                      "audit003.json": within(audit_root, "mfa-unused-eligibility-metadata-audit-003.json"),
                      "audit004.json": within(audit_root, "mfa-unused-eligibility-metadata-audit-004.json")})
    files = {name: checked(path, policy["source_pins"][name]) for name, path in locations.items()}
    reader = metadata_reader()
    summary = reader(files["summary.json"], {k: True for k in
                     ("target_values_released", "rationales_released", "excerpts_released", "source_receipts")})
    require(all(summary[k] is False for k in ("target_values_released", "rationales_released", "excerpts_released")),
            "Source metadata seal differs")
    partition = reader(files["partition-summary.json"], {"private_membership_ledger_sha256": True,
        "crosspartition_checks": True, "partition_target_counts": True, "partition_fine_target_counts": True})
    require(partition["private_membership_ledger_sha256"] == sha(files["private-membership.json"])
            and all(v == 0 for v in partition["crosspartition_checks"].values()), "Partition commitments differ")
    metadata = reader(files["private-metadata.json"], {"rows": [{k: True for k in ROW_FIELDS}]})
    unit_fields = {k: True for k in "candidate_excerpt_hashes catalogue_reference_match condition eligible panel partition release row_original_hash rows target_hash task unit_sha256".split()}
    unit_fields["row_memberships"] = [{k: True for k in ("metadata_row_sha256", "ordered_pair_hash", "writer_hash")}]
    ledger = reader(files["private-membership.json"], {
        "components": [{k: True for k in ("component_sha256", "forced_development", "partition", "target_hashes", "text_hashes")}],
        "evaluation_units": [unit_fields]})
    selection = select(metadata["rows"], ledger, summary["source_receipts"], policy)
    files["membership-profile.json"] = policy_raw
    return selection, files


def select(rows, ledger, source_receipts, policy):
    assignments, text_partitions = {}, {}
    for component in ledger["components"]:
        require(not component["forced_development"] or component["partition"] == "development", "Exposed component outside development")
        for target in component["target_hashes"]:
            require(target not in assignments, "Duplicate target assignment")
            assignments[target] = component["partition"]
        for digest in component["text_hashes"]:
            text_partitions.setdefault(digest, set()).add(component["partition"])
    require(all(len(parts) == 1 for parts in text_partitions.values()), "Text crosses partitions")
    targets = {t for t, part in assignments.items() if part == "confirmation"}
    selected = [r for r in rows if r["release"] == "author-style" and r["task"] == "quality" and r["target_hash"] in targets]
    require(all(r["panel"] in ("expert", "lay") and r["condition"] in ("fewshot", "finetuned")
                and r["original_hash"] is None for r in selected), "Unsupported primary quality row")
    index = {sha(canonical(r)): r for r in selected}
    require(len(index) == len(selected), "Duplicate metadata row")
    units = [u for u in ledger["evaluation_units"] if u["release"] == "author-style"
             and u["task"] == "quality" and u["target_hash"] in targets]
    joined, pairs, texts, ballots = [], {}, {}, []
    for unit in units:
        require(unit["partition"] == "confirmation" and unit["eligible"] and unit["row_original_hash"] is None
                and unit["rows"] == len(unit["row_memberships"]), "Quality unit eligibility differs")
        identity = {"target_hash": unit["target_hash"], "condition": unit["condition"],
                    "excerpt_hashes": unit["candidate_excerpt_hashes"]}
        pair_id = sha(canonical(identity))
        pair = pairs.setdefault(pair_id, {**identity, "pair_id": pair_id, "unit_sha256s": [],
            "metadata_row_sha256s": [], "ordered_pair_hashes": [], "planned_ballot_ids": [], "panels": [],
            "fine_model_variant": "UNKNOWN"})
        pair["unit_sha256s"].append(unit["unit_sha256"])
        if unit["panel"] not in pair["panels"]:
            pair["panels"].append(unit["panel"])
        for membership in unit["row_memberships"]:
            key = membership["metadata_row_sha256"]
            require(key in index, "Unit references absent source row")
            row = index[key]
            require(all(row[k] == unit[k] for k in ("release", "task", "panel", "condition", "target_hash"))
                    and sorted(row["excerpt_hashes"]) == unit["candidate_excerpt_hashes"]
                    and row["writer_hash"] == membership["writer_hash"]
                    and row["ordered_pair_hash"] == membership["ordered_pair_hash"], "Source membership differs")
            joined.append(key)
            pair["metadata_row_sha256s"].append(key)
            if row["ordered_pair_hash"] not in pair["ordered_pair_hashes"]:
                pair["ordered_pair_hashes"].append(row["ordered_pair_hash"])
            ballot = {"metadata_row_sha256": key, "source_field": "Preference", "pair_id": pair_id,
                      **{k: row[k] for k in ("release", "task", "panel", "condition", "target_hash", "writer_hash",
                         "rater_hash", "ordered_pair_hash", "source_path", "target_position", "writer_position",
                         "source_position", "judgment_identity_hash")}, "fine_model_variant": "UNKNOWN"}
            ballot["ballot_id"] = sha(canonical(ballot))
            ballots.append(ballot)
            pair["planned_ballot_ids"].append(ballot["ballot_id"])
            for digest, size in zip(row["excerpt_hashes"], row["excerpt_bytes"]):
                require(text_partitions.get(digest) == {"confirmation"}, "Candidate text outside confirmation component")
                if digest in texts:
                    require(texts[digest]["bytes"] == size, "Text byte lengths differ")
                text = texts.setdefault(digest, {"id": "mfa-" + digest, "sha256": digest, "bytes": size, "target_hashes": []})
                if row["target_hash"] not in text["target_hashes"]:
                    text["target_hashes"].append(row["target_hash"])
    require(len(joined) == len(set(joined)) and set(joined) == set(index), "Incomplete or duplicate row join")
    fine = {r["target_hash"] for r in selected if r["condition"] == "finetuned"}
    require(fine and targets - fine, "Both target strata required")
    sentinel_targets = [min(fine), min(targets - fine)]
    bank_sentinels = [min(t["id"] for t in texts.values() if target in t["target_hashes"]) for target in sentinel_targets]
    pair_sentinels = [min(p["pair_id"] for p in pairs.values() if p["target_hash"] == target
                          and p["condition"] == ("finetuned" if target in fine else "fewshot")) for target in sentinel_targets]
    require(len(set(bank_sentinels)) == len(set(pair_sentinels)) == 2, "Sentinels must be distinct")
    paths = {r["source_path"] for r in selected}
    receipts = [r for r in source_receipts if r["release"] == "author-style" and r["path"] in paths]
    require(len(receipts) == len(paths) and {r["path"] for r in receipts} == paths, "Missing source receipt")
    for receipt in receipts:
        expected = policy["source_files"][receipt["path"]]
        require(all(receipt[k] == expected[k] for k in ("sha256", "bytes", "git_blob_sha1")), "Source receipt differs")
    result = {"policy": POLICY, "partition": "confirmation", "cohort_designation": "conditional_outcome_blind_benchmark",
              "release": "author-style", "task": "quality", "fine_model_variant": "UNKNOWN",
              "selected_targets": [{"target_hash": t, "stratum": "fine" if t in fine else "fewshot_only"} for t in sorted(targets)],
              "metadata_rows": selected, "evaluation_units": units, "planned_ballots": sorted(ballots, key=lambda b: b["ballot_id"]),
              "texts": sorted(texts.values(), key=lambda t: t["id"]), "pairs": sorted(pairs.values(), key=lambda p: p["pair_id"]),
              "bank_sentinel_ids": bank_sentinels, "pair_sentinel_ids": pair_sentinels, "source_receipts": receipts,
              "primary_repeat": 0, "diagnostic_repeats": [1, 2], "unused_data_certified": "UNKNOWN"}
    actual = summary(result)
    for key in ("targets", "fine_targets", "unique_texts", "pairs", "evaluation_units", "metadata_rows", "lay_only_pairs"):
        require(actual[key] == policy["expected"][key], "Frozen cohort geometry differs: " + key)
    require(len({b["ballot_id"] for b in ballots}) == len(selected), "Ballot identity duplicated")
    result["selection_sha256"] = sha(canonical(result))
    return result


def summary(selection):
    return {"policy": POLICY, "targets": len(selection["selected_targets"]),
            "fine_targets": sum(t["stratum"] == "fine" for t in selection["selected_targets"]),
            "unique_texts": len(selection["texts"]), "pairs": len(selection["pairs"]),
            "evaluation_units": len(selection["evaluation_units"]), "metadata_rows": len(selection["metadata_rows"]),
            "planned_Preference_ballots": len(selection["planned_ballots"]),
            "lay_only_pairs": sum(set(p["panels"]) == {"lay"} for p in selection["pairs"]),
            "rows_by_panel_condition": dict(Counter(r["panel"] + ":" + r["condition"] for r in selection["metadata_rows"])),
            "fine_model_variant": "UNKNOWN", "unused_data_certified": "UNKNOWN", "labels_released": False,
            "fresh_confirmation_claim": False, "human_alignment_claim": False, "provider_calls": 0}


class SourceProjection:
    """Positional ranges skip all values; only selected text/identity fields decode."""
    def __init__(self, raw):
        self.text = raw.decode("utf-8")
        self.decoder = json.JSONDecoder()
        self.cache = {}

    def white(self, i):
        while i < len(self.text) and self.text[i].isspace():
            i += 1
        return i

    def skip(self, i):
        i = self.white(i)
        text = self.text
        if text[i] == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == '"':
                    return i + 1
                else:
                    i += 1
        elif text[i] in "[{":
            end = "]" if text[i] == "[" else "}"
            i = self.white(i + 1)
            while text[i] != end:
                i = self.white(i + 1) if text[i] in ",:" else self.white(self.skip(i))
            return i + 1
        else:
            end = i
            while end < len(text) and text[end] not in ",]} \r\n\t":
                end += 1
            return end
        raise ValueError("Unterminated source string")

    def entries(self, start, *, object_keys):
        key = (start, object_keys)
        if key in self.cache:
            return self.cache[key]
        require(self.text[start] == ("{" if object_keys else "["), "Source container shape differs")
        close = "}" if object_keys else "]"
        i, result = self.white(start + 1), []
        while self.text[i] != close:
            name = None
            if object_keys:
                name, i = self.decoder.raw_decode(self.text, i)
                require(isinstance(name, str), "Invalid object key")
                i = self.white(i)
                require(self.text[i] == ":", "Missing source key separator")
                i = self.white(i + 1)
            begin, end = i, self.skip(i)
            result.append((name, begin, end) if object_keys else (begin, end))
            i = self.white(end)
            if self.text[i] == ",":
                i = self.white(i + 1)
            else:
                require(self.text[i] == close, "Invalid source container separator")
        self.cache[key] = result
        return result

    def value(self, begin, end):
        value, consumed = self.decoder.raw_decode(self.text, begin)
        require(consumed == end, "Source value boundary differs")
        return value

    def selected_texts(self, rows):
        targets = self.entries(self.white(0), object_keys=True)
        texts = {}
        for row in rows:
            target, start, _ = targets[row["target_position"]]
            require(sha(canonical(target)) == row["target_hash"], "Target position differs")
            writer, start, _ = self.entries(start, object_keys=True)[row["writer_position"]]
            require(sha(canonical(writer)) == row["writer_hash"], "Writer position differs")
            start, _ = self.entries(start, object_keys=False)[row["source_position"]]
            envelope = self.entries(start, object_keys=False)
            require(len(envelope) == (3 if row["panel"] == "expert" else 2), "Rater envelope differs")
            record_start, _ = envelope[-1]
            entries = {name: (a, b) for name, a, b in self.entries(record_start, object_keys=True)}
            require("Preference" in entries and self.text[entries["Preference"][0]] not in "[{", "Preference field shape differs")
            rater_range = envelope[1] if len(envelope) == 3 else entries["user"]
            require(sha(canonical(self.value(*rater_range))) == row["rater_hash"]
                    and sha(canonical(self.value(*entries["id"]))) == row["judgment_identity_hash"], "Rater or judgment differs")
            for index, field in enumerate(("Excerpt1", "Excerpt2")):
                value = self.value(*entries[field])
                require(isinstance(value, str) and value, "Missing candidate text")
                raw = value.encode("utf-8")
                require(sha(raw) == row["excerpt_hashes"][index] and len(raw) == row["excerpt_bytes"][index], "Candidate text commitment differs")
                texts[row["excerpt_hashes"][index]] = raw
        return texts


def extract_source(selection, source_root):
    texts = {}
    for receipt in selection["source_receipts"]:
        raw = checked(within(source_root, "author-style/" + receipt["path"]), receipt["sha256"])
        require(len(raw) == receipt["bytes"] and hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                == receipt["git_blob_sha1"], "Source length or Git blob differs")
        rows = [r for r in selection["metadata_rows"] if r["source_path"] == receipt["path"]]
        texts.update(SourceProjection(raw).selected_texts(rows))
    require(set(texts) == {t["sha256"] for t in selection["texts"]}, "Incomplete candidate projection")
    return texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("metadata-root", "partition-root", "audit-root", "output-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    require(not args.dry_run or args.source_root is None, "Metadata dry-run must omit source root")
    selection, inputs = load_inputs(args.metadata_root, args.partition_root, args.audit_root)
    output = private_output(args.output_root, [args.metadata_root, args.partition_root, args.audit_root,
                                             *([args.source_root] if args.source_root else [])])
    result = {**summary(selection), "selection_sha256": selection["selection_sha256"], "dry_run": args.dry_run}
    if not args.dry_run:
        require(args.source_root is not None, "Actual extraction requires retained source root")
        texts = extract_source(selection, args.source_root)
        files = {"selection.json": canonical(selection), "implementation/extract.py": Path(__file__).read_bytes(),
                 "membership-profile.json": inputs["membership-profile.json"]}
        files.update({"inputs/" + digest + ".txt": raw for digest, raw in texts.items()})
        files.update({"commitments/" + name: raw for name, raw in inputs.items()
                      if name not in ("private-metadata.json", "private-membership.json", "membership-profile.json")})
        receipt = {**result, "source_pins": profile()[0]["source_pins"], "labels_released": False,
                   "decoded_source_value_fields": ["Excerpt1", "Excerpt2", "id", "expert envelope rater or lay user"],
                   "excluded_value_fields": ["Preference", "win", "Reason", "key", "unknown fields"],
                   "artifacts": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}}
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            write_new(output / name, raw)
        write_new(output / "extraction.json", canonical(receipt))
        result["extraction_sha256"] = sha(canonical(receipt))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
