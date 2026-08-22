#!/usr/bin/env python3
"""Explicit no-contact entry point for the Ox successor recovery overlay."""
from __future__ import annotations

import argparse
from pathlib import Path

from recovery import prepare_retry_successor, reconcile


parser = argparse.ArgumentParser()
parser.add_argument("--work-dir", required=True, type=Path)
parser.add_argument("--prepare-retry-successor", type=Path)
args = parser.parse_args()

if args.prepare_retry_successor:
    print(prepare_retry_successor(args.work_dir, args.prepare_retry_successor))
else:
    print(reconcile(args.work_dir))
