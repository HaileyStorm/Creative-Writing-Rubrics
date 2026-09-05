"""Run explicit, focused local pytest checks in fresh processes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
LANES = {
    "core": (
        "tests/test_release_identity_v123.py",
        "tests/test_cli.py",
        "tests/test_batch.py",
        "tests/test_run_verify.py",
        "tests/test_public_v2_execution.py",
        "tests/test_runner.py",
        "tests/test_longform.py",
        "tests/test_longform_runner.py",
        "tests/test_scoring.py",
        "tests/test_weights.py",
    ),
    "package": ("tests/test_public_surface.py",),
}


def _study_path(value: str) -> str:
    path = (ROOT / value).resolve()
    try:
        path.relative_to(TESTS)
    except ValueError as error:
        raise argparse.ArgumentTypeError("study must be under tests/") from error
    if path.parent != TESTS or not path.is_file() or not path.name.startswith("test_") or path.suffix != ".py":
        raise argparse.ArgumentTypeError("study must name an existing tests/test_*.py file")
    return path.relative_to(ROOT).as_posix()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list the maintained lanes")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--lane", choices=sorted(LANES), help="run a maintained focused lane")
    choice.add_argument("--study", action="append", type=_study_path, help="run an explicit test module")
    return parser


def _list_lanes() -> None:
    for lane, studies in LANES.items():
        print(f"{lane}:")
        for study in studies:
            print(f"  {study}")


def _run(studies: tuple[str, ...] | list[str]) -> int:
    failure = 0
    for study in studies:
        print(f"\n==> {study}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", study], cwd=ROOT, check=False
        )
        if result.returncode:
            print(f"FAILED ({result.returncode}): {study}", file=sys.stderr, flush=True)
            failure = failure or result.returncode
    return failure


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list:
        _list_lanes()
        return 0
    if args.lane:
        return _run(LANES[args.lane])
    if args.study:
        return _run(args.study)
    _parser().error("choose --lane or --study, or use --list")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
