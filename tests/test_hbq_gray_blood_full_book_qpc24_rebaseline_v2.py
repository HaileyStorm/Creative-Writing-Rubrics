"""Clone-portable contract tests for the clean-head QPC24 full-book freeze."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-gray-blood-full-book-qpc24-rebaseline-v2"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
PRIVATE_FIELDS = {"source_text", "source_path", "prompt", "response", "evidence_quote", "provider_session_id"}


def keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys(child)


class PublicFullBookQpc24CleanHeadFreezeTests(unittest.TestCase):
    def test_public_record_is_opaque_provider_free_and_clone_portable(self) -> None:
        self.assertEqual(MANIFEST["status"], "FROZEN_PROVIDER_FREE_PENDING_INDEPENDENT_REVIEW")
        self.assertEqual(MANIFEST["cwr_commit"], "3e840f3d100c81ce863b1e5bb5d2e72a8fabcfbc")
        self.assertEqual(MANIFEST["standard"], {"id": "HBQ-RS", "version": "1.2.1"})
        self.assertEqual(MANIFEST["artifact_provenance"], [{"artifact_id": "gbq24a7-mss-01", "origin": "author-original"}, {"artifact_id": "gbq24r6-mss-02", "origin": "gpt-5.6-pro-rewrite"}])
        self.assertEqual(MANIFEST["privacy"], {"source_text_published": False, "source_paths_published": False, "brief_published": False, "provider_calls_made": 0})
        self.assertEqual(MANIFEST["private_package"]["package_id"], "hbq-qpc24-full-book-freeze-v3-3e840f3-20260825")
        self.assertRegex(MANIFEST["private_package"]["freeze_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual({path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()}, {"README.md", "manifest.json"})
        self.assertTrue(PRIVATE_FIELDS.isdisjoint(keys(MANIFEST)))
        public_bytes = b"".join(path.read_bytes() for path in ROOT.rglob("*") if path.is_file())
        self.assertNotIn(b"Gray Blood 11-25-23.txt", public_bytes)
        self.assertNotIn(b"Gray_Blood_NOTES.txt", public_bytes)
        self.assertNotIn(b"C:\\Users\\", public_bytes)

    def test_exact_full_fidelity_geometry_and_controller_ceiling(self) -> None:
        self.assertEqual(MANIFEST["full_fidelity_policy"], {"global_leaves": 221, "chapter_leaves": 228, "batch_size": 24, "leaf_sampling": "forbidden", "not_applicable": "returned_verdict_not_prefilter"})
        self.assertEqual(MANIFEST["first_pass"], {"positions": 3406, "binary_calls": 150, "structured_calls": 6, "logical_calls": 156, "hard_max_sends": 468})
        self.assertEqual(MANIFEST["controller"], {"provider": "codex", "model": "gpt-5.6-sol", "structured_reasoning": "high", "judge_reasoning": "high", "structured_retry_ceiling_per_pass": 3, "structured_nonretryable_rejection": "terminal_no_retry", "sleep_safe_resume": "running_intent_before_every_first_or_resumed_spawn_distinct_partial_resume_preflight_explicit_reconcile_then_runner_durable_resume", "review_receipt_sha256_bound": True, "reviewed_freeze_manifest_sha256_bound": True, "completion_audit": ["provider_model_reasoning", "frozen_source_derived_scope_artifact", "accepted_response_artifacts", "normalized_verdict_replay", "checkpoint_chain"], "execution_requires_independent_review": True})
        self.assertEqual(MANIFEST["comparison"], {"paired_chapters": [1, 2, 3, 4, 5, 6], "author_chapter_7": "unpaired", "manuscript_scope": "separate_due_to_unequal_spans"})


if __name__ == "__main__":
    unittest.main()
