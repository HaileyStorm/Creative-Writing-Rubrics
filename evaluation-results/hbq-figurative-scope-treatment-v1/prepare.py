"""Validate the frozen package and print its deterministic, provider-free request plan."""
from __future__ import annotations

import json

from study import build_plan, load_json, verify_package


def main() -> None:
    contract = load_json("study-contract.json")
    corpus = load_json("public-synthetic-prompt-scope-corpus.json")
    plan = build_plan(corpus, contract)
    print(json.dumps({"verification": verify_package(), "requests": plan}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
