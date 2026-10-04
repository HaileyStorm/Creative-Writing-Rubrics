"""Offline, label-free preparation of the frozen matched TTCW benchmark."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import importlib.util
from itertools import combinations
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARM_ORDER = ("hbq", "ttcw14", "holistic", "compact", "oregon")
ENDPOINTS = ("grok", "sol")
SEED = "matched-ttcw-20261004-v1"
PINS = {
    "plan": ("ttcw-expert-plan-r129/plan.json", "31e7a0fc06a52808ff0e0f3d20642c1ad65274603ebdaf6f0f43a474ff407180"),
    "author": ("ttcw-expert-source-r125/author-stories.json", "5ff3138ead096c50ecafc86c7be88837c96fd2d6a0d903042c0fb3ed867c2bcf"),
    "tests": ("ttcw-expert-source-r125/author-tests.json", "1f305d408e3f89bb526023a0f04d58428b096aef66b5d748b81579036f3be5a8"),
}
EXPECTED_COUNTS = {"hbq": 1242, "ttcw14": 54, "holistic": 54, "compact": 54, "oregon": 54, "pairwise": 96}


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def checked(path: Path, expected: str, size: int | None = None) -> bytes:
    raw = path.read_bytes()
    if digest(raw) != expected or size is not None and len(raw) != size:
        raise ValueError(f"Frozen artifact differs: {path}")
    return raw


def within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes its frozen root")
    return path


def load_subset(path: Path) -> Any:
    # This standalone offline module imports no broker, provider, or auth code.
    spec = importlib.util.spec_from_file_location("matched_ttcw_schema_subset", path)
    if spec is None or spec.loader is None:
        raise ValueError("Shared offline schema validator unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def portable_schema(node: Any, *, root: bool = True) -> Any:
    """Transport-only conversion; exact cardinality remains a semantic check."""
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key == "maxItems" or key == "$schema" and not root:
            continue
        if key == "const":
            result["enum"] = [value]
        elif key in {"properties", "$defs", "definitions"}:
            result[key] = {name: portable_schema(child, root=False) for name, child in value.items()}
        elif key == "items":
            result[key] = portable_schema(value, root=False)
        else:
            result[key] = value
    return result


def load_source(control: Path) -> dict[str, Any]:
    # Deliberately enumerated inputs: no globbing or annotation/label file reads.
    raw = {name: checked(control / rel, pin) for name, (rel, pin) in PINS.items()}
    plan, author, tests = (json.loads(raw[name]) for name in ("plan", "author", "tests"))
    if len(author) != 48 or len(plan["passes"]) != 36 or len(plan["requests"]) != 828:
        raise ValueError("Frozen source geometry differs")
    if [test["ttcw_idx"] for test in tests] != list(range(1, 15)):
        raise ValueError("TTCW test identity/order differs")
    plan_root = control / "ttcw-expert-plan-r129"
    context = checked(within(plan_root, plan["context"]["path"]), plan["context"]["sha256"], plan["context"]["bytes"])
    stories = []
    packet_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for request in plan["requests"]:
        packet_groups[request["pass_id"]].append(request)
    for row in plan["passes"]:
        original = author[row["source_position"] - 1]
        generator = original["story_id"].split("_", 1)[1]
        if generator not in {"Claude", "GPT3.5", "GPT4"}:
            raise ValueError("Non-AI reference included")
        text = original["content"].encode("utf-8")
        if digest(text) != row["source_sha256"] or len(text) != row["source_bytes"]:
            raise ValueError("Author story and retained plan differ")
        checked(within(plan_root, row["input_path"]), row["source_sha256"], row["source_bytes"])
        if int(original["story_id"].split("_", 1)[0]) != row["plot_group"]:
            raise ValueError("Plot group differs")
        packets = []
        for request in packet_groups[row["pass_id"]]:
            prompt = checked(within(plan_root, request["prompt_path"]), request["prompt_sha256"], request["prompt_bytes"])
            schema = checked(within(plan_root, request["schema_path"]), request["schema_sha256"], request["schema_bytes"])
            packets.append({"prompt": prompt, "schema": schema, "question_ids": request["question_ids"],
                            "batch": request["batch_number"]})
        if (len(packets) != 23 or [p["batch"] for p in packets] != list(range(1, 24))
                or [qid for p in packets for qid in p["question_ids"]] != plan["runtime"]["question_ids"]):
            raise ValueError("HBQ packet identity/order differs")
        stories.append({"id": row["opaque_story_id"], "retained_artifact_id": row["logical_sample_id"],
                        "plot": row["plot_group"], "generator": generator,
                        "text": text, "sha256": digest(text), "length": len(text), "packets": packets})
    if (len({s["id"] for s in stories}) != 36
            or Counter(s["plot"] for s in stories) != Counter({i: 3 for i in range(12)})
            or Counter(s["generator"] for s in stories) != Counter({g: 12 for g in ("Claude", "GPT3.5", "GPT4")})):
        raise ValueError("Story cohort balance differs")
    return {"stories": stories, "tests": tests, "tests_raw": raw["tests"], "context": context,
            "runtime": plan["runtime"]}


def select_sentinels(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for generator in sorted({s["generator"] for s in stories}):
        ordered = sorted((s for s in stories if s["generator"] == generator), key=lambda s: (s["length"], s["sha256"]))
        if len(ordered) != 12:
            raise ValueError("Length strata require twelve stories per generator")
        # Three four-story strata; select lower median within each stratum.
        for stratum, offset in enumerate((1, 5, 9)):
            selected.append({"id": ordered[offset]["id"], "generator": generator, "length_stratum": stratum,
                             "length_bytes": ordered[offset]["length"]})
    return selected


def all_pairs(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = []
    for plot in range(12):
        group = sorted((s for s in stories if s["plot"] == plot), key=lambda s: s["id"])
        if len(group) != 3 or len({s["generator"] for s in group}) != 3:
            raise ValueError("Each plot requires three distinct generator stories")
        for left, right in combinations(group, 2):
            pair_id = "pair-" + digest(canonical([left["id"], right["id"]]))[:24]
            pairs.append({"id": pair_id, "plot": plot, "left": left["id"], "right": right["id"],
                          "generator_pair": sorted([left["generator"], right["generator"]])})
    return pairs


def select_pairs(pairs: list[dict[str, Any]]) -> list[str]:
    chosen, plots = [], set()
    for generator_pair in sorted({tuple(p["generator_pair"]) for p in pairs}):
        candidates = sorted((p for p in pairs if tuple(p["generator_pair"]) == generator_pair),
                            key=lambda p: digest(canonical([SEED, "repeat-pair", p["id"]])))
        for pair in candidates:
            if pair["plot"] not in plots:
                chosen.append(pair["id"])
                plots.add(pair["plot"])
                if sum(tuple(p["generator_pair"]) == generator_pair for p in pairs if p["id"] in chosen) == 2:
                    break
    if len(chosen) != 6 or len(plots) != 6:
        raise ValueError("Repeat-pair balance differs")
    return chosen


def adapted_tests(tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for test in tests:
        full = test["full_prompt"]
        definition, marker, _terminal = full.partition("\n\nGiven the story")
        if not marker or not definition.strip() or not test["question"].strip():
            raise ValueError("Original TTCW definition/question boundary differs")
        result.append({"test_id": f"ttcw-{test['ttcw_idx']:02d}", "dimension": test["torrance_dimension"],
                       "category": test["category"], "definition": definition, "question": test["question"],
                       "source_full_prompt_sha256": digest(full.encode("utf-8"))})
    return result


def build(source: dict[str, Any], subset: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    stories = source["stories"]
    by_id = {s["id"]: s for s in stories}
    sentinels = select_sentinels(stories)
    sentinel_ids = {s["id"] for s in sentinels}
    pairs = all_pairs(stories)
    repeat_pair_ids = select_pairs(pairs)
    arm_assets = {}
    public_assets: dict[str, bytes] = {}
    for arm in (*ARM_ORDER[1:], "pairwise"):
        prompt = (HERE / "arms" / f"{arm}.prompt.md").read_bytes()
        schema_raw = (HERE / "arms" / f"{arm}.schema.json").read_bytes()
        subset.validate_schema(json.loads(schema_raw))
        arm_assets[arm] = (prompt, schema_raw)
        public_assets[f"arms/{arm}.prompt.md"] = prompt
        public_assets[f"arms/{arm}.schema.json"] = schema_raw
    definition_raw = (HERE / "arm-definitions.json").read_bytes()
    public_assets["arm-definitions.json"] = definition_raw
    registration_raw = (HERE / "REGISTRATION.md").read_bytes()
    public_assets["REGISTRATION.md"] = registration_raw
    artifacts = dict(public_assets)
    artifacts["sources/author-tests.json"] = source["tests_raw"]
    artifacts["context.txt"] = source["context"]
    for story in stories:
        artifacts[f"inputs/{story['id']}.txt"] = story["text"]
    units = []
    for repeat in range(3):
        for story in stories:
            if repeat and story["id"] not in sentinel_ids:
                continue
            for arm in ARM_ORDER:
                units.append({"arm": arm, "repeat": repeat, "story_id": story["id"]})
        for pair in pairs:
            if repeat and pair["id"] not in repeat_pair_ids:
                continue
            for orientation in (0, 1):
                units.append({"arm": "pairwise", "repeat": repeat, "pair_id": pair["id"], "orientation": orientation})
    units.sort(key=lambda unit: (unit["repeat"], digest(canonical([SEED, unit]))))
    pair_by_id = {p["id"]: p for p in pairs}
    test_payload = canonical(adapted_tests(source["tests"])).decode("utf-8")
    context = source["context"].decode("utf-8")
    requests, endpoint_ordinals = [], Counter()
    for unit in units:
        arm = unit["arm"]
        if arm == "hbq":
            packets = by_id[unit["story_id"]]["packets"]
        else:
            template, schema = arm_assets[arm]
            header = template.decode("utf-8") + "\n## Common evaluation context\n\n" + context
            if arm == "pairwise":
                pair = pair_by_id[unit["pair_id"]]
                ids = [pair["left"], pair["right"]]
                if unit["orientation"]:
                    ids.reverse()
                text = header + "\n\n## Story A\n\n" + by_id[ids[0]]["text"].decode("utf-8")
                text += "\n\n## Story B\n\n" + by_id[ids[1]]["text"].decode("utf-8") + "\n"
            else:
                text = header + "\n\n## Story\n\n" + by_id[unit["story_id"]]["text"].decode("utf-8") + "\n"
                if arm == "ttcw14":
                    text += "\n## Original questions and interpretive definitions\n\n" + test_payload
            packets = [{"prompt": text.encode("utf-8"), "schema": schema, "question_ids": [], "batch": 1}]
        for packet in packets:
            prompt = packet["prompt"]
            retained_schema_sha = digest(packet["schema"])
            schema_raw = canonical(portable_schema(json.loads(packet["schema"])))
            subset.validate_schema(json.loads(schema_raw))
            prompt_path = f"prompts/{digest(prompt)}.txt"
            schema_path = f"schemas/{digest(schema_raw)}.json"
            artifacts[prompt_path], artifacts[schema_path] = prompt, schema_raw
            source_ids = [unit["story_id"]] if arm != "pairwise" else ids
            source_descriptors = [{"id": sid, "input_path": f"inputs/{sid}.txt", "sha256": by_id[sid]["sha256"],
                                   **({"side": "AB"[index]} if arm == "pairwise" else {})}
                                  for index, sid in enumerate(source_ids)]
            condition = {**unit, "batch": packet["batch"], "question_ids": packet["question_ids"],
                         "sources": source_descriptors, "bundle_id": "prose.short_story",
                         "artifact_id": by_id[unit["story_id"]]["retained_artifact_id"] if arm == "hbq" else unit.get("story_id", unit.get("pair_id")),
                         "prompt_sha256": digest(prompt), "schema_sha256": digest(schema_raw)}
            logical_id = digest(canonical(condition))
            # Alternate which endpoint leads each unit, independent of outcomes.
            endpoints = ENDPOINTS if int(logical_id[-1], 16) % 2 == 0 else ENDPOINTS[::-1]
            for endpoint in endpoints:
                endpoint_ordinals[endpoint] += 1
                request = {**condition, "logical_sample_id": logical_id, "endpoint": endpoint,
                           "endpoint_ordinal": endpoint_ordinals[endpoint], "ordinal": len(requests) + 1,
                           "prompt_path": prompt_path, "prompt_bytes": len(prompt), "schema_path": schema_path,
                           "schema_bytes": len(schema_raw), "retained_schema_sha256": retained_schema_sha}
                request["request_sha256"] = digest(canonical(request))
                requests.append(request)
    for endpoint in ENDPOINTS:
        endpoint_rows = [r for r in requests if r["endpoint"] == endpoint]
        if (Counter(r["arm"] for r in endpoint_rows) != Counter(EXPECTED_COUNTS)
                or len(endpoint_rows) != 1554 or sum(r["repeat"] == 0 for r in endpoint_rows) != 1044):
            raise ValueError("Matched request geometry differs")
    file_inventory = {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(artifacts.items())}
    manifest = {
        "schema_version": 1, "study_id": SEED, "evidence_class": "opened_development_matched_comparison_preparation",
        "provider_calls_made": 0, "execution_authority": False, "provider_binding_required": True,
        "labels_read": False, "source_pins": {name: {"path": rel, "sha256": pin} for name, (rel, pin) in PINS.items()},
        "implementation": {"prepare_sha256": digest((HERE / "prepare.py").read_bytes()),
                           "semantic_validator_sha256": digest((HERE / "validate_response.py").read_bytes()),
                           "schema_subset_sha256": digest(Path(subset.__file__).read_bytes())},
        "runtime": source["runtime"], "seed": SEED,
        "context": {"path": "context.txt", "sha256": digest(source["context"]), "bytes": len(source["context"])},
        "order": "repeat phases 0/1/2; SHA256(seed,unit) shuffle within phase; hash-alternated endpoint lead; HBQ batch order retained",
        "stories": [{k: s[k] for k in ("id", "plot", "generator", "sha256", "length")} for s in stories],
        "sentinels": sentinels, "pairs": pairs, "repeat_pair_ids": repeat_pair_ids,
        "counts": {"stories": 36, "plot_clusters": 12, "unordered_pairs": 36, "sentinel_stories": 9,
                   "repeat_pairs": 6, "initial_requests_per_endpoint": 1044, "repeat_requests_per_endpoint": 510,
                   "requests_per_endpoint": 1554, "requests_total": 3108, "by_arm_per_endpoint": EXPECTED_COUNTS,
                   "hbq_initial_verdict_positions_per_endpoint": 6408, "ttcw14_initial_test_positions_per_endpoint": 504,
                   "initial_expert_ballots": 1512, "initial_expert_test_story_cells": 504},
        "bytes": {"prompt_transmission_per_endpoint": sum(r["prompt_bytes"] for r in requests if r["endpoint"] == "grok"),
                  "prompt_transmission_total": sum(r["prompt_bytes"] for r in requests),
                  "schema_transmission_total": sum(r["schema_bytes"] for r in requests),
                  "unique_artifacts_total": sum(len(raw) for raw in artifacts.values())},
        "public_asset_hashes": {path: digest(raw) for path, raw in public_assets.items()},
        "artifacts": file_inventory, "requests": requests,
    }
    manifest["manifest_content_sha256"] = digest(canonical(manifest))
    artifacts["manifest.json"] = canonical(manifest)
    return manifest, artifacts


def require_private_output(path: Path, control: Path) -> Path:
    path = path.resolve()
    if path == control.resolve() or path.is_relative_to(REPO) or REPO.is_relative_to(path):
        raise ValueError("Private output must be a distinct directory outside the repository")
    # Refuse placing generated descendants inside either frozen input directory.
    for rel, _pin in PINS.values():
        if path.is_relative_to((control / rel).parent.resolve()):
            raise ValueError("Private output cannot overlap frozen source inputs")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--schema-validator", type=Path, default=Path.home() / ".codex/tools/model_work_queue/adapters/json_schema_subset.py")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate/render in memory without writing")
    mode.add_argument("--verify", action="store_true", help="Compare every output artifact to a fresh offline render")
    args = parser.parse_args()
    output = require_private_output(args.private_output, args.control_root)
    if not args.dry_run and not args.verify and output.exists():
        raise ValueError("Private output already exists; use a fresh path or --verify")
    source = load_source(args.control_root)
    manifest, artifacts = build(source, load_subset(args.schema_validator))
    if args.verify:
        actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
        if actual != set(artifacts) or any((output / name).read_bytes() != raw for name, raw in artifacts.items()):
            raise ValueError("Prepared artifact inventory/bytes differ")
    elif not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for relative, raw in artifacts.items():
            path = within(output, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
    print(json.dumps({"mode": "dry-run" if args.dry_run else "verified" if args.verify else "prepared",
                      "manifest_content_sha256": manifest["manifest_content_sha256"], "counts": manifest["counts"],
                      "bytes": manifest["bytes"], "artifact_count": len(artifacts), "labels_read": False,
                      "provider_calls_made": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
