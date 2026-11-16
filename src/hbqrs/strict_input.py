"""Opt-in, unambiguous verdict-file parsing for new imports.

This validates source syntax and JSON-compatible finite values. It does not
ground evidence or change the historic parser or scorer.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

from .core import HBQError

POLICY = "unique_keys_finite_v1"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate mapping key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


class _UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, yaml.nodes.MappingNode):
            raise ValueError("expected YAML mapping")
        self.flatten_mapping(node)
        result: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str:
                raise ValueError("mapping keys must be strings")
            if key in result:
                raise ValueError("duplicate mapping key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _check_tree(value: Any, active: set[int], checked: set[int]) -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        return
    if type(value) not in (dict, list):
        raise ValueError("value is not JSON-compatible")
    identity = id(value)
    if identity in active:
        raise ValueError("recursive alias")
    if identity in checked:
        return
    active.add(identity)
    try:
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str:
                    raise ValueError("mapping keys must be strings")
                _check_tree(child, active, checked)
        else:
            for child in value:
                _check_tree(child, active, checked)
    finally:
        active.remove(identity)
    checked.add(identity)


def load_verdict_input(path: str | Path) -> tuple[Any, dict[str, str]]:
    """Read once and return parsed data with a source-byte digest and policy."""
    source = Path(path)
    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8")
        suffix = source.suffix.lower()
        if suffix == ".json":
            value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        elif suffix == ".jsonl":
            value = [json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                     for line in text.splitlines() if line.strip()]
        elif suffix in {".yaml", ".yml"}:
            value = yaml.load(text, Loader=_UniqueSafeLoader)
        else:
            raise ValueError("expected JSON, JSONL, YAML, or YML")
        _check_tree(value, set(), set())
    except yaml.YAMLError as exc:
        # PyYAML diagnostics can include lines of the private source text.
        raise HBQError(f"Invalid verdict input under {POLICY}: invalid YAML") from exc
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise HBQError(f"Invalid verdict input under {POLICY}: {exc}") from exc
    return value, {"policy": POLICY, "sha256": hashlib.sha256(raw).hexdigest()}
