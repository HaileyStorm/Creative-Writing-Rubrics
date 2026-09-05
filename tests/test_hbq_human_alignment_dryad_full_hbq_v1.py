import importlib.util
import hashlib
import subprocess
import json
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-v1" / "source.py"
SPEC = importlib.util.spec_from_file_location("dryad_full_hbq_v1", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(subject)
FROZEN_COMMIT = "6ee872b9d969ede9576bdf518a9be2a3576ffd11"
# The generator bound working-tree CRLF bytes for these files.  Git's stored
# blobs are LF-normalized, so this recipe reconstructs only the documented
# CRLF ranges recorded on 2026-09-05 after verifying normalized equality.
# The frozen contract hash, not today's worktree, verifies reconstruction.
CRLF_REPRESENTATION_RANGES = {
    "src/hbqrs/core.py": ((1, 254), (264, 326), (333, 345), (347, 392), (400, 423), (425, 443), (554, 554), (556, 565), (568, 579), (597, 734), (743, 744), (746, 964), (968, 993), (996, 1026)),
    "src/hbqrs/paths.py": ((1, 52),),
    "registry/all_modules.json": ((1, 52038),),
    "bundles/all_bundles.json": ((1, 16988),),
}


def reconstruct_frozen_bytes(relative: str, git_blob: bytes) -> bytes:
    ranges = CRLF_REPRESENTATION_RANGES.get(relative)
    if not ranges:
        return git_blob
    lines = git_blob.splitlines(keepends=True)
    for start, end in ranges:
        for index in range(start - 1, end):
            if lines[index].endswith(b"\n"):
                lines[index] = lines[index][:-1] + b"\r\n"
    return b"".join(lines)


@contextmanager
def frozen_runtime():
    contract = subject.load_contract()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for relative, expected in contract["runtime_bindings"].items():
            raw = subprocess.run(
                ["git", "-C", str(ROOT), "show", f"{FROZEN_COMMIT}:{relative}"],
                check=True,
                capture_output=True,
            ).stdout
            raw = reconstruct_frozen_bytes(relative, raw)
            assert hashlib.sha256(raw).hexdigest() == expected
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        dryad_copy = root / "evaluation-results" / "hbq-human-alignment-dryad-pilot-v1" / "source.py"
        dryad_copy.parent.mkdir(parents=True, exist_ok=True)
        dryad_copy.write_bytes(subject.DRYAD_SOURCE.read_bytes())
        assert hashlib.sha256(dryad_copy.read_bytes()).hexdigest() == subject.DRYAD_SOURCE_SHA256
        yield root


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

    def test_historical_runtime_compiles_and_rejects_actual_drift(self) -> None:
        with frozen_runtime() as runtime, patch.object(subject, "REPOSITORY", runtime):
            expected = subject.compiled_question_bank(subject.load_contract())
            self.assertEqual(subject.compiled_question_bank(subject.load_contract()), expected)
            runner = runtime / "src" / "hbqrs" / "runner.py"
            runner.write_bytes(runner.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "Runtime hash drift"):
                subject.compiled_question_bank(subject.load_contract())

    def test_same_path_cached_modules_cannot_change_bank_or_preview(self) -> None:
        from hbqrs import core, runner

        with frozen_runtime() as runtime, patch.object(subject, "REPOSITORY", runtime), patch.object(subject, "DRYAD_SOURCE", runtime / "evaluation-results" / "hbq-human-alignment-dryad-pilot-v1" / "source.py"), patch.object(subject, "load_dryad_source", return_value=_PublicInputs()):
            expected = subject.compiled_question_bank(subject.load_contract())
            preview = subject.preview_story(Path("unused"), "train-0")
            with patch.object(core, "__file__", str(runtime / "src" / "hbqrs" / "core.py")), patch.object(runner, "__file__", str(runtime / "src" / "hbqrs" / "runner.py")), patch.object(core, "compile_bundle", side_effect=AssertionError("cached normal module executed")), patch.object(runner, "_render_prompt", return_value="tampered"):
                self.assertEqual(subject.compiled_question_bank(subject.load_contract()), expected)
                self.assertEqual(subject.preview_story(Path("unused"), "train-0"), preview)

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
        with frozen_runtime() as runtime, patch.object(subject, "REPOSITORY", runtime):
            contract = subject.load_contract()
            first = subject.compiled_question_bank(contract)
            second = subject.compiled_question_bank(contract)
            self.assertEqual(first, second)
            self.assertEqual(len(first["questions"]), 178)
            self.assertEqual(len(first["ordered_question_ids"]), 178)
            self.assertEqual(first["bundle_id"], "prose.short_story")

    def test_packet_verifier_rejects_byte_mutation(self) -> None:
        identity = {"evidence_class": "TEST_FIXTURE", "git_commit": "0" * 40}
        with frozen_runtime() as runtime, patch.object(subject, "REPOSITORY", runtime), patch.object(subject, "DRYAD_SOURCE", runtime / "evaluation-results" / "hbq-human-alignment-dryad-pilot-v1" / "source.py"), patch.object(subject, "load_dryad_source", return_value=_PublicInputs()), patch.object(subject, "_generator_identity", return_value=identity):
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
