#!/usr/bin/env python3
"""Tee one adapter's stdout to immutable evidence while preserving broker Job Object ownership."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-path", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not args.capture_path.is_absolute() or args.capture_path.exists():
        return 125
    try:
        # Broker assigns the wrapper to its Job Object before it writes stdin.
        # EOF therefore confirms assignment before this wrapper can create a child.
        payload = sys.stdin.buffer.read()
        with args.capture_path.open("xb") as capture:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            errors: list[BaseException] = []
            def copy_stdin() -> None:
                try:
                    assert proc.stdin is not None
                    proc.stdin.write(payload); proc.stdin.close()
                except BaseException as error:
                    errors.append(error)
            def copy_stdout() -> None:
                assert proc.stdout is not None
                try:
                    while block := proc.stdout.read(4096):
                        capture.write(block); capture.flush(); os.fsync(capture.fileno())
                        sys.stdout.buffer.write(block); sys.stdout.buffer.flush()
                except BaseException as error:
                    errors.append(error)
            def copy_stderr() -> None:
                assert proc.stderr is not None
                try:
                    while block := proc.stderr.read(4096):
                        sys.stderr.buffer.write(block); sys.stderr.buffer.flush()
                except BaseException as error:
                    errors.append(error)
            writers = [threading.Thread(target=copy_stdin, daemon=True), threading.Thread(target=copy_stdout, daemon=True), threading.Thread(target=copy_stderr, daemon=True)]
            for writer in writers: writer.start()
            code = proc.wait()
            for writer in writers: writer.join(timeout=2)
            return code if not errors and all(not writer.is_alive() for writer in writers) else 125
    except OSError:
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
