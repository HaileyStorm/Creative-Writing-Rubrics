"""Rebuild aggregate registry files from per-module and per-bundle YAML."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .core import walk_tree
from .paths import book_root


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _json_dump(path: Path, value: Any) -> None:
    if path.is_file() and json.loads(path.read_text(encoding="utf-8")) == value:
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _yaml_dump(path: Path, value: Any) -> None:
    if path.is_file() and yaml.safe_load(path.read_text(encoding="utf-8")) == value:
        return
    path.write_text(
        yaml.dump(value, Dumper=_NoAliasDumper, sort_keys=False, allow_unicode=True, width=110),
        encoding="utf-8",
    )


def _jsonl_dump(path: Path, records: list[Any]) -> None:
    if path.is_file():
        existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if existing == records:
            return
    lines = [json.dumps(item, ensure_ascii=False) for item in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _load_yaml_records(directory: Path, *, skip_prefixes: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith(skip_prefixes):
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            records.extend(item for item in loaded if isinstance(item, dict))
        elif isinstance(loaded, dict):
            records.append(loaded)
        else:
            raise ValueError(f"Expected a mapping in {path}")
    return records


def _flatten_questions(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module in modules:
        for leaf, group_ids, _weight in walk_tree(module.get("tree", [])):
            row = {
                "module_id": module["module_id"],
                "module_title": module.get("title"),
                "kind": module.get("kind"),
                "group_ids": list(group_ids),
                **leaf,
            }
            rows.append(row)
    return rows


def pack_book(root: Path | None = None) -> dict[str, int]:
    """Rewrite aggregate JSON/YAML/JSONL files from per-record YAML sources."""

    book = root or book_root()
    modules = sorted(
        _load_yaml_records(book / "registry" / "modules"),
        key=lambda item: item["module_id"],
    )
    bundles = sorted(
        _load_yaml_records(book / "bundles", skip_prefixes=("all_bundles",)),
        key=lambda item: item["bundle_id"],
    )
    questions = _flatten_questions(modules)

    _json_dump(book / "registry" / "all_modules.json", modules)
    _yaml_dump(book / "registry" / "all_modules.yaml", modules)
    _jsonl_dump(book / "registry" / "all_modules.jsonl", modules)
    _jsonl_dump(book / "registry" / "question_index.jsonl", questions)
    _json_dump(
        book / "registry" / "title_index.json",
        {str(item.get("title")): item["module_id"] for item in modules},
    )
    _json_dump(
        book / "registry" / "criterion_ownership.json",
        {
            leaf["criterion_key"]: {
                "module_id": module["module_id"],
                "question_id": leaf["id"],
            }
            for module in modules
            for leaf, _, _ in walk_tree(module.get("tree", []))
        },
    )

    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for module in modules:
        categories[module["module_id"].split(".", 1)[0]].append(module)
    category_dir = book / "registry" / "categories"
    category_dir.mkdir(parents=True, exist_ok=True)
    for name, records in categories.items():
        _yaml_dump(category_dir / f"{name}.yaml", records)

    _json_dump(book / "bundles" / "all_bundles.json", bundles)
    _yaml_dump(book / "bundles" / "all_bundles.yaml", bundles)
    _jsonl_dump(book / "bundles" / "all_bundles.jsonl", bundles)

    return {
        "modules": len(modules),
        "questions": len(questions),
        "bundles": len(bundles),
        "categories": len(categories),
    }
