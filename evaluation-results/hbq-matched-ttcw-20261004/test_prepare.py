"""Small behavioral proofs of schedule identity, privacy, and response admission."""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import unittest

import prepare
from validate_response import semantic_validate


def fixture() -> dict:
    stories = []
    ids = [f"question-{i:03d}" for i in range(178)]
    for plot in range(12):
        for generator in ("Claude", "GPT3.5", "GPT4"):
            text = ("Evidence sentence. " + "x" * (plot * 8 + len(generator))).encode()
            opaque = "story-" + prepare.digest(prepare.canonical([plot, generator]))[:24]
            packets = []
            for batch, start in enumerate(range(0, 178, 8), 1):
                schema = {"type": "object", "required": ["verdicts"], "properties": {
                    "verdicts": {"type": "array", "minItems": len(ids[start:start + 8]), "maxItems": len(ids[start:start + 8]),
                                 "items": {"type": "object"}}}}
                packets.append({"prompt": b"Anonymous HBQ packet\n" + text + prepare.canonical(ids[start:start + 8]),
                                "schema": prepare.canonical(schema), "batch": batch, "question_ids": ids[start:start + 8]})
            stories.append({"id": opaque, "retained_artifact_id": opaque, "plot": plot, "generator": generator,
                            "text": text, "sha256": prepare.digest(text), "length": len(text), "packets": packets})
    tests = [{"ttcw_idx": i, "torrance_dimension": "Source dimension", "category": "Source category",
              "question": f"Literal source question {i}?",
              "full_prompt": f"Literal source definition {i}.\n\nGiven the story above, explain step by step."}
             for i in range(1, 15)]
    return {"stories": stories, "tests": tests, "tests_raw": prepare.canonical(tests),
            "context": b"Complete anonymous fiction story.", "runtime": {"question_ids": ids}}


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.subset = prepare.load_subset(Path.home() / ".codex/tools/model_work_queue/adapters/json_schema_subset.py")
        cls.source = fixture()
        cls.manifest, cls.artifacts = prepare.build(cls.source, cls.subset)

    def test_complete_geometry_and_repeat_selection(self) -> None:
        manifest = self.manifest
        self.assertEqual(len(manifest["requests"]), 3108)
        self.assertEqual(Counter(s["generator"] for s in manifest["sentinels"]), Counter({g: 3 for g in ("Claude", "GPT3.5", "GPT4")}))
        self.assertEqual(len({s["id"] for s in manifest["sentinels"]}), 9)
        pairs = [p for p in manifest["pairs"] if p["id"] in manifest["repeat_pair_ids"]]
        self.assertEqual(len({p["plot"] for p in pairs}), 6)
        self.assertEqual(sorted(Counter(tuple(p["generator_pair"]) for p in pairs).values()), [2, 2, 2])
        for endpoint in prepare.ENDPOINTS:
            rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
            initial = [r for r in rows if r["repeat"] == 0]
            self.assertEqual(Counter(r["arm"] for r in rows), Counter(prepare.EXPECTED_COUNTS))
            self.assertEqual(len(initial), 1044)
            for arm in prepare.ARM_ORDER:
                self.assertEqual(len({r["story_id"] for r in initial if r["arm"] == arm}), 36)
            self.assertEqual(len({r["pair_id"] for r in initial if r["arm"] == "pairwise"}), 36)

    def test_condition_hashes_repeat_identity_and_outbound_blinding(self) -> None:
        ids = set()
        for request in self.manifest["requests"]:
            base = {k: v for k, v in request.items() if k != "request_sha256"}
            self.assertEqual(request["request_sha256"], prepare.digest(prepare.canonical(base)))
            self.assertNotIn(request["request_sha256"], ids)
            ids.add(request["request_sha256"])
            prompt = self.artifacts[request["prompt_path"]]
            self.assertEqual(prepare.digest(prompt), request["prompt_sha256"])
            for hidden in (b"Claude", b"GPT3.5", b"GPT4", b"story_name", b"expert_label"):
                self.assertNotIn(hidden, prompt)
        chosen = self.manifest["sentinels"][0]["id"]
        rows = [r for r in self.manifest["requests"] if r.get("story_id") == chosen and r["arm"] == "holistic" and r["endpoint"] == "sol"]
        self.assertEqual(len({r["prompt_sha256"] for r in rows}), 1)
        self.assertEqual(len({r["logical_sample_id"] for r in rows}), 3)

    def test_deterministic_source_only_selection_and_schema_portability(self) -> None:
        self.assertEqual(prepare.select_sentinels(self.source["stories"]), prepare.select_sentinels(self.source["stories"][::-1]))
        changed = copy.deepcopy(self.source["stories"])
        for story in changed:
            story["unread_quality_outcome"] = 999
        self.assertEqual(prepare.select_sentinels(changed), prepare.select_sentinels(self.source["stories"]))
        for path, raw in self.artifacts.items():
            if path.endswith(".json") and path.startswith(("schemas/", "arms/")):
                self.subset.validate_schema(json.loads(raw))

    def test_abstention_is_valid_and_cannot_carry_invented_score(self) -> None:
        request = next(r for r in self.manifest["requests"] if r["arm"] == "holistic")
        texts = {s["id"]: s["text"].decode() for s in self.source["stories"]}
        response = {"status": "CANNOT_ASSESS", "result": None, "abstention_reason": "Text unavailable to judge."}
        result = semantic_validate("holistic", response, request, texts, self.subset)
        self.assertEqual(result, {"accepted": True, "abstention": True, "errors": []})
        response["status"] = "SCORED"
        self.assertFalse(semantic_validate("holistic", response, request, texts, self.subset)["accepted"])

    def test_duplicate_tests_and_fabricated_quotes_are_rejected(self) -> None:
        request = next(r for r in self.manifest["requests"] if r["arm"] == "ttcw14")
        texts = {s["id"]: s["text"].decode() for s in self.source["stories"]}
        rows = [{"test_id": f"ttcw-{i:02d}", "verdict": "YES", "observation": "Supported observation.",
                 "evidence": [{"quote": "Evidence sentence.", "explanation": "Observable evidence."}],
                 "abstention_reason": None} for i in range(1, 15)]
        response = {"method": "ttcw14_concise_evidence_v1", "verdicts": rows}
        self.assertTrue(semantic_validate("ttcw14", response, request, texts, self.subset)["accepted"])
        rows[-1]["test_id"] = rows[0]["test_id"]
        self.assertFalse(semantic_validate("ttcw14", response, request, texts, self.subset)["accepted"])
        rows[-1]["test_id"] = "ttcw-14"
        rows[-1]["evidence"][0]["quote"] = "Fabricated source quotation"
        self.assertFalse(semantic_validate("ttcw14", response, request, texts, self.subset)["accepted"])

    def test_private_repository_output_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            prepare.require_private_output(prepare.HERE / "private", Path("C:/external-control"))

    def test_pairwise_tie_and_abstention_and_oregon_sum(self) -> None:
        texts = {s["id"]: s["text"].decode() for s in self.source["stories"]}
        request = next(r for r in self.manifest["requests"] if r["arm"] == "pairwise")
        response = {"method": "ttcw_independent_editorial_pairwise_v1", "winner": "TIE",
                    "tradeoff": "Comparable strengths.", "evidence": [], "abstention_reason": None}
        self.assertFalse(semantic_validate("pairwise", response, request, texts, self.subset)["accepted"])
        response["evidence"] = [{"side": side, "quote": "Evidence sentence.", "explanation": "Observed strength."}
                                for side in ("A", "B")]
        self.assertEqual(semantic_validate("pairwise", response, request, texts, self.subset),
                         {"accepted": True, "abstention": False, "errors": []})
        response.update(winner="CANNOT_ASSESS", evidence=[], abstention_reason="Cannot evaluate supplied material.")
        self.assertEqual(semantic_validate("pairwise", response, request, texts, self.subset),
                         {"accepted": True, "abstention": True, "errors": []})
        request = next(r for r in self.manifest["requests"] if r["arm"] == "oregon")
        schema = json.loads((prepare.HERE / "arms/oregon.schema.json").read_bytes())
        trait_ids = schema["properties"]["result"]["properties"]["traits"]["items"]["properties"]["trait_id"]["enum"]
        response = {"status": "SCORED", "abstention_reason": None, "result": {
            "method": "oregon_narrative_2017_ttcw_research_v1", "total_score": 12, "overall_note": "Supported.",
            "traits": [{"trait_id": tid, "score": 2, "exact_quote": "Evidence sentence.", "observation": "Observed."}
                       for tid in trait_ids]}}
        self.assertTrue(semantic_validate("oregon", response, request, texts, self.subset)["accepted"])
        response["result"]["total_score"] = 13
        self.assertFalse(semantic_validate("oregon", response, request, texts, self.subset)["accepted"])


if __name__ == "__main__":
    unittest.main()
