"""Shared test-only reconstruction for frozen established-repeatability studies."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


class HistoricalRuntimeUnavailable(ValueError):
    """The host no longer retains a pinned historical control/runtime."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_lf(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n")


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(repository), *args], capture_output=True, check=check)


def _git_show(repository: Path, commit: str, relative: Path) -> bytes:
    result = _git(repository, "show", f"{commit}:{relative.as_posix()}", check=False)
    if result.returncode:
        raise HistoricalRuntimeUnavailable(f"pinned control is unavailable: {relative.as_posix()}")
    return result.stdout


class HistoricalStudyRuntime:
    """Materialize a pinned study control and a separate historical HBQ runtime."""

    def __init__(
        self,
        *,
        root: Path,
        repository: Path,
        runtime_commit: str,
        control_commit: str,
        package_name: str,
        label: str,
        seals_path: Path,
    ) -> None:
        self.root = root
        self.repository = repository
        self.runtime_commit = runtime_commit
        self.control_commit = control_commit
        self.package_name = package_name
        self.label = label
        self.seals_path = seals_path
        self._runtime: SimpleNamespace | None = None

    def _relative(self, path: Path) -> Path:
        return path.resolve().relative_to(self.repository)

    def _seals(self) -> dict[str, dict[str, Any]]:
        payload = json.loads(self.seals_path.read_text(encoding="utf-8"))
        seals = payload.get("seals")
        if payload.get("format_version") != 1 or not isinstance(seals, dict):
            raise HistoricalRuntimeUnavailable("canonical successor-seal fixture is malformed")
        return seals

    def _matches_record(self, payload: bytes, record: dict[str, Any]) -> bool:
        return len(payload) == record.get("bytes") and _sha256(payload) == record.get("sha256")

    def _matches_seal(self, payload: bytes, record: dict[str, Any]) -> bool:
        seal = self._seals().get(str(record.get("sha256")))
        return bool(
            isinstance(seal, dict)
            and seal.get("raw_bytes") == record.get("bytes")
            and seal.get("canonical_lf_sha256") == _sha256(payload)
            and seal.get("canonical_lf_bytes") == len(payload)
        )

    def _clean_bound_worktree_payload(self, relative: Path, record: dict[str, Any]) -> bytes | None:
        path = self.repository / relative
        if not path.is_file():
            return None
        if not self.tracked_path_is_clean(relative):
            return None
        payload = path.read_bytes()
        return payload if self._matches_record(payload, record) else None

    def tracked_path_is_clean(self, relative: Path) -> bool:
        commands = (
            ["git", "-C", str(self.repository), "diff", "--no-ext-diff", "--quiet", "--", relative.as_posix()],
            ["git", "-C", str(self.repository), "diff", "--cached", "--no-ext-diff", "--quiet", "--", relative.as_posix()],
        )
        return not any(subprocess.run(command, check=False).returncode for command in commands)

    def _materialize_asset(self, snapshot: Path, relative: Path, record: dict[str, Any]) -> None:
        """Use the raw historical bytes, or their explicitly sealed LF successor only."""

        payload = _git_show(self.repository, self.control_commit, relative)
        canonical_lf = _canonical_lf(payload)
        for candidate in (payload, canonical_lf, canonical_lf.replace(b"\n", b"\r\n")):
            if self._matches_record(candidate, record) or self._matches_seal(candidate, record):
                destination = snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(candidate)
                return
        bound = self._clean_bound_worktree_payload(relative, record)
        if bound is not None:
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(bound)
            return
        raise HistoricalRuntimeUnavailable(
            f"pinned control cannot reconstruct raw asset or canonical successor: {relative.as_posix()}"
        )

    def _extract_runtime(self, snapshot: Path) -> None:
        archive = _git(
            self.repository,
            "archive",
            "--format=tar",
            self.runtime_commit,
            "src/hbqrs",
            check=False,
        )
        if archive.returncode:
            raise HistoricalRuntimeUnavailable(f"historical {self.label} runtime archive is unavailable")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as contents:
            for member in contents.getmembers():
                target = (snapshot / member.name).resolve()
                if (
                    member.issym()
                    or member.islnk()
                    or not target.is_relative_to(snapshot.resolve())
                    or not (member.isdir() or member.isfile())
                ):
                    raise HistoricalRuntimeUnavailable(f"historical {self.label} runtime archive is unsafe")
            contents.extractall(snapshot, filter="data")

    def runtime(self) -> SimpleNamespace:
        if self._runtime is not None:
            return self._runtime
        for commit, role in ((self.runtime_commit, "runtime"), (self.control_commit, "control")):
            if _git(self.repository, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode:
                raise HistoricalRuntimeUnavailable(f"pinned {self.label} {role} commit is unavailable")

        root_relative = self._relative(self.root)
        contract_relative = root_relative / "study-contract.json"
        manifest_relative = root_relative / "asset-manifest.json"
        contract_bytes = _git_show(self.repository, self.control_commit, contract_relative)
        manifest_bytes = _git_show(self.repository, self.control_commit, manifest_relative)
        contract = json.loads(contract_bytes)
        manifest = json.loads(manifest_bytes)
        assets = manifest.get("assets")
        if (
            contract.get("asset_manifest", {}).get("sha256") != _sha256(manifest_bytes)
            or manifest.get("format_version") != 1
            or not isinstance(assets, dict)
        ):
            raise HistoricalRuntimeUnavailable(f"pinned {self.label} controls are malformed")

        lease = tempfile.TemporaryDirectory(prefix=f"cwr-established-{self.label}-historical-runtime-")
        snapshot = Path(lease.name) / "repository"
        try:
            self._extract_runtime(snapshot)
            (snapshot / ".git").write_text(f"gitdir: {self.repository / '.git'}\n", encoding="utf-8")
            for relative, payload in ((contract_relative, contract_bytes), (manifest_relative, manifest_bytes)):
                destination = snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
            for name, raw_record in assets.items():
                if not isinstance(name, str) or not isinstance(raw_record, dict) or not isinstance(raw_record.get("path"), str):
                    raise HistoricalRuntimeUnavailable(f"pinned {self.label} asset record is malformed")
                relative = self._relative(self.root / raw_record["path"])
                self._materialize_asset(snapshot, relative, raw_record)
                materialized = (snapshot / relative).read_bytes()
                if not (self._matches_record(materialized, raw_record) or self._matches_seal(materialized, raw_record)):
                    raise HistoricalRuntimeUnavailable(f"pinned {self.label} asset reconstruction changed: {name}")
        except Exception:
            lease.cleanup()
            raise

        package_root = snapshot / "src" / "hbqrs"
        spec = importlib.util.spec_from_file_location(
            self.package_name,
            package_root / "__init__.py",
            submodule_search_locations=[str(package_root)],
        )
        assert spec and spec.loader
        package = importlib.util.module_from_spec(spec)
        sys.modules[self.package_name] = package
        spec.loader.exec_module(package)
        paths = sys.modules[f"{self.package_name}.paths"]
        paths.book_root = lambda: snapshot
        self._runtime = SimpleNamespace(
            lease=lease,
            root=snapshot,
            runner=sys.modules[f"{self.package_name}.runner"],
            core=sys.modules[f"{self.package_name}.core"],
            paths=paths,
            structured=sys.modules[f"{self.package_name}.longform_runner"],
            manifest=manifest,
            contract=contract,
            seals=self._seals(),
        )
        return self._runtime

    def _install_runtime(self, module: ModuleType) -> None:
        historical = self.runtime()
        assets = historical.manifest["assets"]

        def compatible(contract: dict[str, object]) -> dict[str, object]:
            if contract != historical.contract:
                raise ValueError("Historical study control drifted; create a successor protocol")
            for name, record in assets.items():
                path = historical.root / self._relative(self.root / record["path"])
                payload = path.read_bytes()
                if not (self._matches_record(payload, record) or self._matches_seal(payload, record)):
                    raise ValueError(f"Historical asset reconstruction changed: {name}")
            return historical.manifest

        module._asset_manifest = compatible
        module.HERE = historical.root / self._relative(self.root)
        module.CONTRACT_PATH = module.HERE / "study-contract.json"
        module.ASSET_MANIFEST_PATH = module.HERE / "asset-manifest.json"
        module.compile_bundle = historical.core.compile_bundle
        module.compiled_questions = historical.core.compiled_questions
        module.load_bundles = historical.core.load_bundles
        module.load_modules = historical.core.load_modules
        module.resolve_bundle = historical.core.resolve_bundle
        module.bundles_path = historical.paths.bundles_path
        module.registry_path = historical.paths.registry_path
        module.run_judge = historical.runner.run_judge
        module.EVIDENCE_NORMALIZATION_POLICY = historical.runner.EVIDENCE_NORMALIZATION_POLICY
        module.VALIDATION_FEEDBACK_POLICY = historical.runner.VALIDATION_FEEDBACK_POLICY
        module._next_codex_message_attempt = getattr(historical.runner, "_next_codex_message_attempt", None)
        module._provider_response_schema = historical.structured._provider_response_schema
        module._reject_structured_checkpoint = getattr(historical.structured, "_reject_structured_checkpoint", None)
        module._run_structured_pass = historical.structured._run_structured_pass

    def _install_analysis(self, module: ModuleType, runner: ModuleType) -> None:
        historical = self.runtime()
        module.HERE = historical.root / self._relative(self.root)
        module.CONTRACT = historical.contract
        module._runner = lambda: runner
        module.load_bundles = historical.core.load_bundles
        module.load_modules = historical.core.load_modules
        module.resolve_bundle = historical.core.resolve_bundle
        module.score_bundle = historical.core.score_bundle
        module.bundles_path = historical.paths.bundles_path
        module.registry_path = historical.paths.registry_path
        module.schema_dir = historical.paths.schema_dir
        module.EVIDENCE_NORMALIZATION_POLICY = historical.runner.EVIDENCE_NORMALIZATION_POLICY
        module._runner_json_bytes = historical.runner._json_bytes
        module._load_checkpoints = historical.runner._load_checkpoints
        module._verdicts_bytes = historical.runner._verdicts_bytes
        module._validate_provider_artifacts = historical.runner._validate_provider_artifacts
        module._structured_json_bytes = historical.structured._json_bytes
        module._parse_model_json = historical.structured._parse_model_json
        module._provider_response_schema = historical.structured._provider_response_schema
        module._v2_helper = lambda: self._v2_helper(module, runner)

    def _v2_helper(self, analysis: ModuleType, runner: ModuleType) -> ModuleType:
        historical = self.runtime()
        path = historical.root / self._relative(self.root.parent / "established-v2" / "analyze_study.py")
        spec = importlib.util.spec_from_file_location(f"{self.package_name}_v2_metrics", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.HERE = analysis.HERE
        module.CONTRACT = analysis.CONTRACT
        module._study_runner = lambda: runner
        module.load_bundles = historical.core.load_bundles
        module.load_modules = historical.core.load_modules
        module.resolve_bundle = historical.core.resolve_bundle
        module.score_bundle = historical.core.score_bundle
        module.bundles_path = historical.paths.bundles_path
        module.registry_path = historical.paths.registry_path
        module.schema_dir = historical.paths.schema_dir
        module._runner_json_bytes = historical.runner._json_bytes
        module._load_checkpoints = historical.runner._load_checkpoints
        module._verdicts_bytes = historical.runner._verdicts_bytes
        module._structured_json_bytes = historical.structured._json_bytes
        module._parse_model_json = historical.structured._parse_model_json
        module._provider_response_schema = historical.structured._provider_response_schema
        return module

    def raw_module(self, name: str) -> ModuleType:
        root = self.runtime().root / self._relative(self.root)
        spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def module(self, name: str) -> ModuleType:
        module = self.raw_module(name)
        if name == "run_study":
            self._install_runtime(module)
        elif name == "analyze_study":
            self._install_analysis(module, self.module("run_study"))
        return module
