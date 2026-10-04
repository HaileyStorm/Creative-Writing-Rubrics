"""Synthetic extraction and offline canonical-contract witnesses; no provider proof."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "evaluation-results/hbq-matched-mfa-v1"
spec = importlib.util.spec_from_file_location("matched_mfa_prepare_test", HERE / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
extract = prepare.extract
spec = importlib.util.spec_from_file_location("matched_mfa_validate_test", HERE / "validate_response.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def fixture():
    targets = [("fine_exposed", "development", True, True), ("fine_unused", "development", False, True),
               ("few_exposed", "development", True, False), ("few_unused", "development", False, False),
               ("confirmation", "confirmation", False, True)]
    rows, sources, receipts = [], {}, []
    for condition in ("fewshot", "finetuned"):
        for panel in ("expert", "lay"):
            path = f"data/quality_{condition}_{panel}_anon.json"
            data = {}
            for name, _, _, fine in targets:
                if condition == "finetuned" and not fine:
                    continue
                texts = [f"Exact synthetic {name} shared prose.\r\nSecond line.", f"Different synthetic {name} {condition} prose."]
                record = {"Excerpt1": texts[0], "Excerpt2": texts[1], "id": name + condition + panel,
                          "user": "synthetic_rater_" + panel, "Preference": "DO_NOT_RELEASE",
                          "Winner": "DO_NOT_RELEASE", "Rationale": "DO_NOT_RELEASE", "Original": "DO_NOT_RELEASE",
                          "unknown": {"private": "DO_NOT_RELEASE"}}
                data[name] = {"shared_synthetic_writer": [["synthetic_record", record]]}
            sources[path] = data
            raw = extract.canonical(data)
            receipts.append({"release": "author-style", "path": path, "sha256": extract.sha(raw), "bytes": len(raw),
                             "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()})
            for target_position, (target, writers) in enumerate(data.items()):
                for writer_position, (writer, judgments) in enumerate(writers.items()):
                    record = judgments[0][-1]
                    hashes = [extract.sha(record[field].encode()) for field in ("Excerpt1", "Excerpt2")]
                    th, wh = extract.sha(extract.canonical(target)), extract.sha(extract.canonical(writer))
                    row = {"release": "author-style", "source_path": path, "task": "quality", "condition": condition,
                           "panel": panel, "target_hash": th, "writer_hash": wh,
                           "rater_hash": extract.sha(extract.canonical(record["user"])),
                           "judgment_identity_hash": extract.sha(extract.canonical(record["id"])),
                           "source_position": 0, "target_position": target_position, "writer_position": writer_position,
                           "excerpt_hashes": hashes, "excerpt_bytes": [len(record[f].encode()) for f in ("Excerpt1", "Excerpt2")],
                           "pair_hash": extract.sha(extract.canonical({"target": th, "condition": condition, "excerpts": sorted(hashes)})),
                           "ordered_pair_hash": extract.sha(extract.canonical({"target": th, "condition": condition, "excerpts": hashes})),
                           "original_present": False, "original_is_text": False, "original_hash": None, "original_bytes": None}
                    row["metadata_record_hash"] = extract.sha(extract.canonical({k: v for k, v in row.items() if k not in ("release", "source_path")}))
                    rows.append(row)
    components = [{"component_sha256": extract.sha(extract.canonical(name)), "partition": part,
                   "forced_development": forced, "target_hashes": [extract.sha(extract.canonical(name))], "text_hashes": []}
                  for name, part, forced, _ in targets]
    units = []
    for row in rows:
        identity = {k: row[k] for k in ("release", "task", "panel", "condition", "target_hash")}
        identity.update(candidate_excerpt_hashes=sorted(row["excerpt_hashes"]), row_original_hash=None)
        part = next(c["partition"] for c in components if row["target_hash"] in c["target_hashes"])
        units.append({**identity, "unit_sha256": extract.sha(extract.canonical(identity)), "partition": part,
                      "eligible": True, "rows": 1, "catalogue_reference_match": False,
                      "row_memberships": [{"metadata_row_sha256": extract.sha(extract.canonical(row)),
                                            "writer_hash": row["writer_hash"], "ordered_pair_hash": row["ordered_pair_hash"]}]})
    return {"rows": rows, "references": []}, {"components": components, "evaluation_units": units}, receipts, sources


class MatchedMFAPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        cls.cli = root / "codex.exe"
        cls.cli.write_bytes(b"synthetic nonexecutable CLI identity; never executed")
        cls.helper = root / "secondary.py"
        home = root / "collection-accounts/cwr-sol-secondary"
        cls.helper.write_text("from pathlib import Path\nCLI = Path(" + repr(str(cls.cli)) + ")\nCOLLECTION_HOME = Path(" + repr(str(home)) + ")\n", encoding="utf-8")
        cls.metadata, cls.ledger, cls.receipts, cls.sources = fixture()
        cls.selection = extract.select(cls.metadata, cls.ledger, cls.receipts)
        cls.input_files = {name: extract.canonical({"synthetic_test_only": True}) for name in
                           ("summary.json", "source-recipe.json", "partition-summary.json")}
        cls.tools = Path("C:/Users/Haile/.codex/tools")
        cls.manifest, cls.files = prepare.build(cls.selection, cls.input_files, cls.helper, cls.cli, cls.tools)
        cls.subset = prepare.load_module("mfa_test_schema_subset", cls.tools / "model_work_queue/adapters/json_schema_subset.py")

    def test_hash_strata_prefer_quarantined_development_and_complete_panels(self):
        selected = self.selection
        self.assertEqual({t["stratum"] for t in selected["selected_targets"]}, {"fine", "fewshot_only"})
        self.assertTrue(all(t["quarantined"] for t in selected["selected_targets"]))
        confirmation = next(c["target_hashes"][0] for c in self.ledger["components"] if c["partition"] == "confirmation")
        self.assertNotIn(confirmation, {t["target_hash"] for t in selected["selected_targets"]})
        self.assertEqual({r["panel"] for r in selected["metadata_rows"]}, {"expert", "lay"})
        self.assertEqual(len(selected["metadata_rows"]), 6)
        self.assertEqual(len(selected["texts"]), 5)
        self.assertEqual(len(selected["pairs"]), 3)

    def test_confirmation_or_missing_membership_is_rejected(self):
        ledger = deepcopy(self.ledger)
        target = self.selection["selected_targets"][0]["target_hash"]
        next(u for u in ledger["evaluation_units"] if u["target_hash"] == target)["partition"] = "confirmation"
        with self.assertRaisesRegex(ValueError, "Confirmation"):
            extract.select(self.metadata, ledger, self.receipts)
        ledger = deepcopy(self.ledger)
        ledger["evaluation_units"] = [u for u in ledger["evaluation_units"] if u["target_hash"] != target or u["panel"] != "lay"]
        with self.assertRaisesRegex(ValueError, "Incomplete expert/lay"):
            extract.select(self.metadata, ledger, self.receipts)

    def test_mechanical_whitelist_never_releases_outcomes_reference_or_identifiers(self):
        texts = {}
        for path, source in self.sources.items():
            rows = [r for r in self.selection["metadata_rows"] if r["source_path"] == path]
            texts.update(extract.selected_texts(source, rows))
        self.assertEqual(set(texts), {t["sha256"] for t in self.selection["texts"]})
        self.assertNotIn(b"DO_NOT_RELEASE", b"".join(texts.values()))
        self.assertNotIn(b"synthetic_rater_", b"".join(texts.values()))
        self.assertIn(b"\r\n", b"".join(texts.values()))

    def test_exact_source_identity_position_hash_and_order_fail_closed(self):
        row = self.selection["metadata_rows"][0]
        source = self.sources[row["source_path"]]
        for field, value in (("target_hash", "0" * 64), ("writer_hash", "0" * 64),
                             ("rater_hash", "0" * 64), ("judgment_identity_hash", "0" * 64),
                             ("excerpt_hashes", list(reversed(row["excerpt_hashes"]))),
                             ("excerpt_bytes", [1, 1])):
            wrong = deepcopy(row)
            wrong[field] = value
            with self.assertRaises(ValueError):
                extract.selected_texts(source, [wrong])

    def test_pinned_metadata_rejects_a_different_partition_before_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("private-metadata.json", "summary.json", "source-recipe.json", "private-membership.json"):
                (root / name).write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "Pinned metadata"):
                extract.load_inputs(root, root)

    def test_complete_canonical_scope_context_and_schema_readiness(self):
        self.assertEqual(self.manifest["counts"]["canonical_leaves"], 170)
        self.assertEqual(self.manifest["counts"]["canonical_packets"], 22)
        self.assertEqual(self.manifest["state"], "metadata_only_prospective_plan")
        self.assertFalse(any("prompt_path" in r for r in self.manifest["requests"]))
        self.assertFalse(self.manifest["runtime"]["strict_ai_prefix"])
        self.assertEqual(prepare.contract("test")["context"]["completion_status"], "excerpt")
        self.assertEqual(prepare.contract("test")["binding_requirements"], [])
        self.assertNotIn("Original\n", prepare.CONTEXT)
        for row in self.manifest["requests"]:
            self.subset.validate_schema(json.loads(self.files[row["schema_path"]]))

    def test_every_pair_has_both_orders_and_independent_three_cycle_sentinels(self):
        rows = [r for r in self.manifest["requests"] if r["arm"] == "pairwise" and r["endpoint"] == "sol"]
        for pair in self.selection["pairs"]:
            initial = [r for r in rows if r["pair_id"] == pair["pair_id"] and r["repeat"] == 0]
            self.assertEqual({r["orientation"] for r in initial}, {"AB", "BA"})
            self.assertEqual([s["id"] for s in initial[0]["sources"]], list(reversed([s["id"] for s in initial[1]["sources"]])))
        for pair_id in self.selection["pair_sentinel_ids"]:
            sentinel = [r for r in rows if r["pair_id"] == pair_id]
            self.assertEqual(len(sentinel), 6)
            self.assertEqual(len({r["logical_sample_id"] for r in sentinel}), 6)
        for artifact_id in self.selection["bank_sentinel_ids"]:
            packets = [r for r in self.manifest["requests"] if r["arm"] == "hbq" and r["endpoint"] == "sol" and r["artifact_id"] == artifact_id]
            self.assertEqual(len(packets), 66)
            self.assertEqual(len({r["logical_sample_id"] for r in packets}), 66)

    def test_exact_text_freeze_and_changed_bytes_rejected(self):
        texts = {}
        for path, source in self.sources.items():
            rows = [r for r in self.selection["metadata_rows"] if r["source_path"] == path]
            texts.update({"mfa-" + h: raw for h, raw in extract.selected_texts(source, rows).items()})
        manifest, files = prepare.build(self.selection, self.input_files, self.helper, self.cli, self.tools,
                                        texts=texts, extraction_sha="synthetic-test-only")
        self.assertEqual(manifest["state"], "frozen_development_canary")
        for row in manifest["requests"]:
            self.assertEqual(extract.sha(files[row["prompt_path"]]), row["prompt_sha256"])
            self.assertEqual(extract.sha(prepare.canonical({k: v for k, v in row.items() if k != "request_sha256"})), row["request_sha256"])
        texts[next(iter(texts))] += b"changed"
        with self.assertRaisesRegex(ValueError, "Exact input"):
            prepare.build(self.selection, self.input_files, self.helper, self.cli, self.tools, texts=texts)

    def test_pairwise_quotes_side_ties_and_abstention_are_distinct(self):
        row = next(r for r in self.manifest["requests"] if r["arm"] == "pairwise")
        values = {s["id"]: "Excerpt on " + s["side"] + "." for s in row["sources"]}
        answer = {"method": "mfa_excerpt_pairwise_v1", "winner": "TIE", "tradeoff": "Synthetic test tradeoff",
                  "evidence": [{"side": side, "quote": "Excerpt on " + side + ".", "explanation": "Synthetic observation"} for side in "AB"],
                  "abstention_reason": None}
        result = validator.semantic_validate("pairwise", answer, row, values, self.subset)
        self.assertTrue(result["accepted"])
        self.assertFalse(result["abstention"])
        answer["evidence"][0]["quote"] = "not in either source"
        self.assertFalse(validator.semantic_validate("pairwise", answer, row, values, self.subset)["accepted"])
        answer.update(winner="CANNOT_ASSESS", evidence=[], abstention_reason="Synthetic insufficient material")
        result = validator.semantic_validate("pairwise", answer, row, values, self.subset)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["abstention"])

    def test_portable_hbq_union_keeps_typed_evidence_and_inventory_admission(self):
        row = next(r for r in self.manifest["requests"] if r["arm"] == "hbq")
        source = {row["sources"][0]["id"]: "synthetic excerpt evidence"}
        schema = json.loads(self.files[row["schema_path"]])
        answer = {"verdicts": [{"question_id": qid, "verdict": "YES", "confidence": .8,
            "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": "synthetic", "summary": None}],
            "note": "Synthetic test observation"} for qid in row["question_ids"]]}
        self.assertTrue(validator.semantic_validate("hbq", answer, row, source, self.subset, schema=schema)["accepted"])
        answer["verdicts"][0]["evidence"][0]["summary"] = "Union conflict"
        self.assertTrue(self.subset.matches_schema(answer, schema))
        self.assertFalse(validator.semantic_validate("hbq", answer, row, source, self.subset, schema=schema)["accepted"])
        answer["verdicts"][0]["evidence"][0]["summary"] = None
        answer["verdicts"][0]["question_id"] = answer["verdicts"][-1]["question_id"]
        self.assertFalse(validator.semantic_validate("hbq", answer, row, source, self.subset, schema=schema)["accepted"])

    def test_immutable_private_output_and_secondary_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "fresh"):
                extract.private_output(Path(tmp), [])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            extract.private_output(REPO / "would-be-private-canary", [])
        raw = self.helper.read_bytes().replace(b"cwr-sol-secondary", b"wrong-account")
        with self.assertRaisesRegex(ValueError, "Wrong secondary"):
            prepare.helper_settings(raw)


if __name__ == "__main__":
    unittest.main()
