"""Clone-portable public contract tests for the QPC24 full-book freeze record."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-gray-blood-full-book-qpc24-rebaseline-v1"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
PRIVATE_FIELDS = {
    "source_text",
    "source_path",
    "prompt",
    "response",
    "evidence_quote",
    "provider_session_id",
}


def keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys(child)


class PublicFullBookQpc24FreezeTests(unittest.TestCase):
    def test_public_record_is_opaque_provider_free_and_clone_portable(self) -> None:
        self.assertEqual(MANIFEST["status"], "FROZEN_PROVIDER_FREE_PENDING_INDEPENDENT_REVIEW")
        self.assertEqual(MANIFEST["privacy"], {"source_text_published": False, "source_paths_published": False, "brief_published": False, "provider_calls_made": 0})
        self.assertEqual(MANIFEST["artifact_ids"], ["gbq24a7-mss-01", "gbq24r6-mss-02"])
        self.assertEqual(MANIFEST["historical_predecessor"], {"retained": True, "superseded_planning_ceiling": 10224})
        private = MANIFEST["private_package"]
        self.assertEqual(private["package_id"], "hbq-qpc24-full-book-freeze-v2-4ce1204-20260825")
        self.assertRegex(private["freeze_manifest_sha256"], r"^[0-9a-f]{64}$")
        files = [path for path in ROOT.rglob("*") if path.is_file()]
        self.assertEqual({path.relative_to(ROOT).as_posix() for path in files}, {"README.md", "manifest.json"})
        self.assertTrue(PRIVATE_FIELDS.isdisjoint(keys(MANIFEST)))
        public_bytes = b"".join(path.read_bytes() for path in files)
        self.assertNotIn(b"Gray Blood 11-25-23.txt", public_bytes)
        self.assertNotIn(b"Gray_Blood_NOTES.txt", public_bytes)
        self.assertNotIn(b"C:\\Users\\", public_bytes)

    def test_exact_full_fidelity_geometry_and_controller_ceiling(self) -> None:
        self.assertEqual(MANIFEST["full_fidelity_policy"], {"global_leaves": 221, "chapter_leaves": 228, "batch_size": 24, "leaf_sampling": "forbidden", "not_applicable": "returned_verdict_not_prefilter"})
        self.assertEqual(MANIFEST["first_pass"], {"positions": 3406, "binary_calls": 150, "structured_calls": 6, "logical_calls": 156, "hard_max_sends": 468})
        self.assertEqual(MANIFEST["controller"], {"provider": "codex", "model": "gpt-5.6-sol", "structured_reasoning": "high", "judge_reasoning": "high", "structured_retry_ceiling_per_pass": 3, "sleep_safe_resume": "explicit_reconcile_then_runner_durable_resume", "execution_requires_independent_review": True})
        self.assertEqual(MANIFEST["comparison"], {"paired_chapters": [1, 2, 3, 4, 5, 6], "author_chapter_7": "unpaired", "manuscript_scope": "separate_due_to_unequal_spans"})


if __name__ == "__main__":
    unittest.main()
