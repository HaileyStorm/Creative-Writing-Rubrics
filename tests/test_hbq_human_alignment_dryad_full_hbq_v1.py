import importlib.util
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-v1" / "source.py"
SPEC = importlib.util.spec_from_file_location("dryad_full_hbq_v1", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(subject)


class _PublicInputs:
    def load_public_inputs(self, root, provenance):
        return {
            "TRAIN": [{"opaque_story_id": f"train-{index}", "story_text": f"Train story {index}"} for index in range(176)],
            "DEV": [{"opaque_story_id": f"dev-{index}", "story_text": f"Dev story {index}"} for index in range(60)],
        }


class DryadFullHBQTests(unittest.TestCase):
    def test_generator_identity_rejects_inter_read_mutation(self) -> None:
        original = Path.read_bytes
        captured = {path: original(path) for path in (SOURCE, subject.CONTRACT_PATH, subject.DRYAD_SOURCE)}
        reads = 0

        def changing_read(path):
            nonlocal reads
            if path == SOURCE:
                reads += 1
                if reads > 1:
                    return captured[path] + b" "
            return original(path)

        def git_blob(args, **kwargs):
            relative = args[-1].split(":", 1)[1]
            return SimpleNamespace(returncode=0, stdout=captured[ROOT / relative])

        with patch.object(Path, "read_bytes", changing_read), patch.object(subject.subprocess, "run", git_blob):
            with self.assertRaisesRegex(ValueError, "changed during verification"):
                subject._generator_identity("0" * 40)

    def test_cached_same_path_runtime_cannot_change_bank_or_preview(self) -> None:
        from hbqrs import core, runner
        expected = subject.compiled_question_bank(subject.load_contract())
        with patch.object(subject, "load_dryad_source", return_value=_PublicInputs()):
            preview = subject.preview_story(Path("unused"), "train-0")
            with patch.object(core, "compile_bundle", side_effect=AssertionError("cached code executed")), patch.object(runner, "_render_prompt", return_value="tampered"):
                self.assertEqual(subject.compiled_question_bank(subject.load_contract()), expected)
                self.assertEqual(subject.preview_story(Path("unused"), "train-0"), preview)
                with patch.object(core, "__file__", str(ROOT / "foreign-checkout" / "core.py")):
                    self.assertEqual(subject.compiled_question_bank(subject.load_contract()), expected)

    def test_contract_change_between_reads_is_rejected(self) -> None:
        original = Path.read_bytes
        reads = 0

        def changing_read(path):
            nonlocal reads
            raw = original(path)
            if path == subject.CONTRACT_PATH:
                reads += 1
                if reads > 1:
                    return raw + b" "
            return raw

        with patch.object(Path, "read_bytes", changing_read):
            with self.assertRaisesRegex(ValueError, "changed during load"):
                subject.load_contract()

    def test_complete_canonical_short_story_question_bank(self) -> None:
        contract = subject.load_contract()
        first = subject.compiled_question_bank(contract)
        second = subject.compiled_question_bank(contract)
        self.assertEqual(first, second)
        self.assertEqual(len(first["questions"]), 178)
        self.assertEqual(len(first["ordered_question_ids"]), 178)
        self.assertEqual(first["bundle_id"], "prose.short_story")

    def test_packet_verifier_rejects_byte_mutation(self) -> None:
        identity = {"evidence_class": "TEST_FIXTURE", "git_commit": "0" * 40}
        with patch.object(subject, "load_dryad_source", return_value=_PublicInputs()), patch.object(subject, "_generator_identity", return_value=identity):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                artifacts = subject.expected_artifacts(root)
                for name, value in artifacts.items():
                    (root / name).write_bytes(value)
                self.assertEqual(subject.verify(root, root), {name: subject.sha256_bytes(value) for name, value in artifacts.items()})
                (root / "story-index.json").write_bytes(b"mutation")
                with self.assertRaisesRegex(ValueError, "byte drift"):
                    subject.verify(root, root)
                (root / "story-index.json").write_bytes(artifacts["story-index.json"])
                provenance = json.loads(artifacts["provenance.json"])
                provenance["source_freeze"]["loader_sha256"] = "0" * 64
                (root / "provenance.json").write_bytes(subject.canonical_json_bytes(provenance))
                with self.assertRaisesRegex(ValueError, "byte drift"):
                    subject.verify(root, root)

    def test_packet_creation_never_overwrites_an_inserted_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "packet"
            original_mkdir = Path.mkdir

            def insert_file(path, *args, **kwargs):
                result = original_mkdir(path, *args, **kwargs)
                if path == output:
                    (path / "question-bank.json").write_bytes(b"owned by another writer")
                return result

            with patch.object(subject, "expected_artifacts", return_value={"question-bank.json": b"new"}), patch.object(Path, "mkdir", insert_file):
                with self.assertRaises(FileExistsError):
                    subject.prepare(Path("unused"), output)
            self.assertEqual((output / "question-bank.json").read_bytes(), b"owned by another writer")

    def test_public_story_index_rejects_confirmation_partition(self) -> None:
        class InvalidPublic:
            def load_public_inputs(self, root, provenance):
                return {"TRAIN": [], "DEV": [], "CONFIRMATION": []}

        with patch.object(subject, "load_dryad_source", return_value=InvalidPublic()):
            with self.assertRaisesRegex(ValueError, "partition drift"):
                subject.public_story_index(Path("unused"), subject.load_contract())


if __name__ == "__main__":
    unittest.main()
