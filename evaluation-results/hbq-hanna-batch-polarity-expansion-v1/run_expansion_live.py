"""Explicit one-attempt live caller for the sealed HANNA four-story expansion.

This command sends the already disclosed private prompts to OpenAI through the
repository-bound, tool-disabled Codex primitive.  It is deliberately serial:
the first uncertain call freezes the complete expansion.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
EXECUTOR_PATH = HERE / "run_expansion.py"
RUNNER_PATH = REPOSITORY / "src" / "hbqrs" / "runner.py"
TIMEOUT_SECONDS = 600.0
CODEX_EXECUTABLE = "codex"
LIVE_LOCK_NAME = ".hbq-hanna-expansion-live.lock"


def _module() -> Any:
    specification = importlib.util.spec_from_file_location("hbq_hanna_batch_polarity_expansion_executor", EXECUTOR_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError("Cannot load expansion executor")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


executor = _module()
from hbqrs.runner import _call_codex  # noqa: E402
if Path(inspect.getsourcefile(_call_codex) or "").resolve() != RUNNER_PATH.resolve():
    raise RuntimeError("Expansion live caller must import the repository-bound Codex provider primitive")


def _receipt(provider_record: Mapping[str, Any]) -> dict[str, str]:
    reported = provider_record.get("reported")
    required = {"provider", "model", "reasoning_effort", "session_id"}
    if not isinstance(reported, Mapping) or set(reported) != required or any(not isinstance(reported[key], str) or not reported[key] for key in required):
        raise RuntimeError("Codex primitive did not provide the exact reported receipt")
    return {key: reported[key] for key in sorted(required)}


def _callback(item: Mapping[str, Any], private_root: Path) -> dict[str, Any]:
    sequence = item.get("sequence")
    if type(sequence) is not int or sequence < 1:
        raise RuntimeError("Expansion callback requires a positive integer sequence")
    output_dir, _, _ = executor._attempt_paths(private_root, sequence)
    response, provider_record = _call_codex(
        executable=CODEX_EXECUTABLE,
        model=executor.MODEL,
        reasoning=executor.REASONING,
        prompt=str(item["prompt"]),
        output_dir=output_dir,
        response_schema=executor.SCHEMA_PATH,
        batch_number=sequence,
        attempt_number=1,
        timeout=TIMEOUT_SECONDS,
    )
    if not isinstance(provider_record, Mapping):
        raise RuntimeError("Codex primitive did not return a provider record")
    return {"receipt": _receipt(provider_record), "response": response}


@contextmanager
def _exclusive_live_run(private_root: Path):
    """Keep a crashed or concurrent invocation fail-closed until inspected."""
    lock = private_root / LIVE_LOCK_NAME
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise RuntimeError("Expansion live run is already active or needs crash recovery") from error
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except OSError as error:
            raise RuntimeError("Expansion live-run lock could not be released; inspect before retrying") from error


def execute_live(work: Path, private_root: Path, *, repo: Path = REPOSITORY) -> dict[str, Any]:
    if not executor._paths_disjoint(work, private_root):
        raise RuntimeError("Public work and private raw roots must be disjoint")
    with _exclusive_live_run(private_root):
        return executor.execute(work, private_root, lambda item: _callback(item, private_root), repo=repo)


def _confirmed_contract(work: Path, disclosure_sha256: str) -> None:
    contract = executor.study.read_json(work / executor.EXECUTION_NAME)
    if contract.get("live_caller") != executor._safe_fingerprint(Path(__file__)):
        raise RuntimeError("Prepared execution contract does not bind this live caller; re-prepare first")
    if contract.get("provider_primitive") != executor._safe_fingerprint(RUNNER_PATH):
        raise RuntimeError("Prepared execution contract does not bind the current provider primitive; re-prepare first")
    disclosure = contract.get("disclosure")
    if not isinstance(disclosure, Mapping) or disclosure.get("sha256") != disclosure_sha256:
        raise RuntimeError("Remote disclosure confirmation does not match the prepared execution contract")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPOSITORY)
    parser.add_argument("--execute-live", action="store_true", help="permit the explicit sequential live caller")
    parser.add_argument("--confirm-remote-disclosure-sha256", required=True)
    arguments = parser.parse_args(argv)
    if arguments.execute_live is not True:
        raise RuntimeError("Live execution requires --execute-live")
    _confirmed_contract(arguments.work, arguments.confirm_remote_disclosure_sha256)
    print(json.dumps(execute_live(arguments.work, arguments.private_root, repo=arguments.repo), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
