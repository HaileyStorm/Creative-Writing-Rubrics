"""Source and geometry witnesses; these do not attest native collection."""
from collections import Counter, defaultdict
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hanna_preparation_test", REPO / "evaluation-results/hbq-matched-hanna-20261004/prepare.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def items():
    result = []
    for n in range(120):
        development = n < 88
        model = "Human" if 80 <= n < 88 else "Generator" + str(n // 8 if development else n % 10)
        prompt_number = n % 39 if n < 80 else 39 if n < 88 else 39 if n < 90 else 40 + (n - 90) // 2
        prompt = ("Originating prompt " + str(prompt_number) + " \r\n\n").encode()
        source = ("Synthetic complete story " + str(n) + ". Exact tail \r\n\n").encode()
        native = str(n + 1)
        original = "hanna-" + native if development else "item-" + p.digest(native.encode())[:16]
        result.append(p.source_item(original, native, model, "prompt-" + p.digest(prompt)[:16], source, prompt,
                                    "fresh88_open_development" if development else "fresh96_open_validation"))
    return result


class HannaPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.items = items()

    def source_fixture(self):
        rows, cells, validation = [], [], []
        for item in self.items:
            if item["origin"] == "fresh88_open_development":
                folder = self.root / "cwr-human-reference-v3-d9038f1/inputs/development" / item["original_id"]
                folder.mkdir(parents=True)
                pins = {}
                for name, raw in (("source.md", item["raw"]), ("prompt.md", item["prompt"]), ("task-contract.json", b'{"source_only":true}\n')):
                    (folder / name).write_bytes(raw)
                    pins[name] = {"bytes": len(raw), "name": name, "sha256": p.digest(raw)}
                row = {"item_id": item["original_id"], "story_id": item["native_story_id"], "model": item["model_role"],
                       "prompt_group_id": item["group"], "story_sha256": item["sha256"], "prompt_sha256": item["prompt_sha256"],
                       "external_input": pins, "quartile": "DO_NOT_DECODE"}
                rows.append(row)
                physical = {name: {"path": str(folder / name), "sha256": pin["sha256"], "bytes": pin["bytes"]} for name, pin in pins.items()}
                cells.append({"item_id": item["original_id"], "artifact": physical["source.md"], "contexts": [physical["prompt.md"]],
                              "task_contract": physical["task-contract.json"], "external_input": pins})
            else:
                row = {"item_id": item["original_id"], "story_id": item["native_story_id"], "model": item["model_role"], "prompt_group_id": item["group"],
                       "partition": "validation", "status": "open", "annotation_count": 3, "story": item["raw"].decode(), "prompt": item["prompt"].decode(),
                       "target": {"Relevance": "DO_NOT_DECODE"}}
                binding = {k: row[k] for k in ("prompt_group_id", "story_id", "model", "prompt", "story")}
                row["source_binding_sha256"] = p.digest(p.canonical(binding).rstrip(b"\n"))
                validation.append(row)
        contents = {"authority": {"selection": {"development": rows, "confirmatory": {"sealed": "DO_NOT_DECODE"}}},
                    "work": {"cells": cells}, "authority_receipt": {}, "work_receipt": {}}
        contents["prior_exposure"] = {"samples": [{"inputs": {"source.md": {"sha256": i["sha256"]}, "prompt.md": {"sha256": i["prompt_sha256"]}},
                                                  "human_overall": "DO_NOT_DECODE"} for i in self.items[:10] + [self.items[39]]]}
        pins = {}
        for name, value in contents.items():
            raw = p.canonical(value)
            (self.root / (name + ".json")).write_bytes(raw)
            pins[name] = (name + ".json", p.digest(raw), len(raw))
        raw = p.canonical({"selected_items": validation, "private_freeze": "DO_NOT_DECODE"})
        path = self.root / "validation.json"
        path.write_bytes(raw)
        return path, pins, (p.digest(raw), len(raw))

    def test_source_identity_pins_and_labels_skipped_before_decoding(self):
        validation, pins, valpin = self.source_fixture()
        original_decode = json.JSONDecoder.raw_decode

        def guarded(decoder, text, index=0):
            if text[index:].startswith('"DO_NOT_DECODE"'):
                raise AssertionError("Human-value or sealed field was decoded")
            return original_decode(decoder, text, index)

        with patch.object(json.JSONDecoder, "raw_decode", guarded):
            actual, provenance = p.load_sources(self.root, validation, pins=pins, validation_pin=valpin)
        self.assertEqual({i["id"] for i in actual}, {i["id"] for i in self.items})
        self.assertEqual(len(provenance["physical_input_commitments"]), 264)
        (self.root / "cwr-human-reference-v3-d9038f1/inputs/development/hanna-1/source.md").write_bytes(b"changed source")
        with self.assertRaisesRegex(ValueError, "Frozen source/code"):
            p.load_sources(self.root, validation, pins=pins, validation_pin=valpin)
        raw = (self.root / "work.json").read_bytes()
        broken = json.loads(raw)
        broken["cells"][1]["item_id"] = broken["cells"][0]["item_id"]
        modified = p.canonical(broken)
        (self.root / "work.json").write_bytes(modified)
        pins["work"] = ("work.json", p.digest(modified), len(modified))
        with self.assertRaisesRegex(ValueError, "identity membership"):
            p.load_sources(self.root, validation, pins=pins, validation_pin=valpin)

    def test_full_cohort_and_sentinels_preserve_shared_group_and_roles(self):
        p.validate_cohort(self.items)
        chosen = p.select_sentinels(self.items)
        self.assertEqual(chosen, p.select_sentinels(list(reversed(self.items))))
        selected = [i for i in self.items if i["id"] in chosen]
        self.assertEqual(len({i["group"] for i in selected}), 6)
        self.assertEqual(Counter((i["role"], i["origin"]) for i in selected), Counter({("human_source", "fresh88_open_development"): 1,
            ("generated", "fresh88_open_development"): 3, ("generated", "fresh96_open_validation"): 2}))
        with self.assertRaisesRegex(ValueError, "Full120"):
            p.validate_cohort(self.items[:-1])
        with self.assertRaisesRegex(ValueError, "fresh and nonexistent"):
            p.output_preflight(self.root, [])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            p.output_preflight(self.root / "source/child", [self.root / "source"])

    def test_full_bank_matched_context_original_schemas_and_closed_gate(self):
        frozen = self.root / "frozen"
        (frozen / "inputs").mkdir(parents=True)
        for name, relative in (("all_modules.yaml", "registry/all_modules.yaml"), ("all_bundles.yaml", "bundles/all_bundles.yaml")):
            (frozen / "inputs" / name).write_bytes((REPO / relative).read_bytes())
        subset = p.load_module("hanna_test_subset", Path.home() / ".codex/tools/model_work_queue/adapters/json_schema_subset.py")
        source_runtime = {"runtime": {"account_identity_sha256": "synthetic", "codex_home_sha256": "synthetic"}, "external_pins": {}}
        tests = p.canonical([{"ttcw_idx": n, "full_prompt": "Synthetic source definition.\n\nGiven the story, evaluate it.",
                              "question": "Does the synthetic story meet criterion " + str(n) + "?", "torrance_dimension": "synthetic", "category": "synthetic"} for n in range(1, 15)])
        original_checked = p.checked

        def fixture_checked(path, pin, size=None):
            return tests if Path(path).name == "synthetic-tests.json" else original_checked(path, pin, size)

        with patch.object(p, "read_runtime", return_value=(source_runtime, {}, subset)), patch.object(p, "checked", side_effect=fixture_checked):
            manifest, files = p.build(self.items, {"source_commitments": {}}, frozen / "manifest.json",
                                     self.root / "synthetic-tests.json")
        self.assertEqual(manifest["counts"]["requests_total"], 6864)
        self.assertEqual(manifest["counts"]["canonical_leaves"], 170)
        self.assertFalse(manifest["labels_read"])
        self.assertFalse(manifest["execution_authority"])
        self.assertFalse(manifest["human_gate"]["release_granted"])
        self.assertEqual(manifest["human_gate"]["required_verified_terminal_requests"], 6864)
        by_id = {i["id"]: i for i in self.items}
        passes = defaultdict(list)
        for row in manifest["requests"]:
            item = by_id[row["artifact_id"]]
            prompt = files[row["prompt_path"]].decode()
            self.assertIn(item["raw"].decode(), prompt)
            self.assertIn(item["prompt"].decode(), prompt)
            self.assertIn(files[row["task_context"]["path"]].decode(), prompt)
            self.assertNotIn(item["original_id"], prompt)
            self.assertNotIn(item["model_role"], prompt)
            self.assertEqual(files[row["originating_prompt"]["path"]], item["prompt"])
            self.assertNotIn("role", row)
            if row["endpoint"] == "sol" and row["arm"] == "hbq":
                passes[(row["artifact_id"], row["repeat"])].extend(row["question_ids"])
        self.assertEqual(len(passes), 132)
        self.assertTrue(all(len(qs) == len(set(qs)) == 171 for qs in passes.values()))
        self.assertEqual(len({tuple(qs) for qs in passes.values()}), 1)
        for arm in p.ARMS[1:]:
            self.assertEqual(files['arms/' + arm + '.original.schema.json'], (REPO / 'evaluation-results/hbq-matched-ttcw-20261004/arms' / (arm + '.schema.json')).read_bytes())


if __name__ == "__main__":
    unittest.main()
