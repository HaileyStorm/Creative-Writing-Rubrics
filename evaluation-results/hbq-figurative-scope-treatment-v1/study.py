"""Frozen development-only planning for the manual figurative-scope comparison."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-scope-treatment-v1"
ARMS = ("baseline", "scope_rendering_only")
LEAVES = {"core.freshness_and_non_genericness.no_default_metaphors", "penalty.purple_prose.proportion", "penalty.purple_prose.fatigue"}
EXPECTED_CONTRACT_PROJECTION_SHA256 = "d4ac67e247fa3ae915aa1aa80c2ae39699a620ad8ae77349cc4e0f9f771f3bb1"

def canonical_json(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
def sha256_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def sha256_file(path: Path) -> str: return sha256_bytes(path.read_bytes())
def load_json(name: str) -> dict[str, Any]: return json.loads((ROOT / name).read_text(encoding="utf-8"))

def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract["study_id"] != STUDY_ID or contract["frozen_before_execution"] is not True or contract["execution"] != {"provider_calls_permitted_by_this_package": False, "manual_arms": list(ARMS), "development_repeats": 3, "one_leaf_per_request": True}:
        raise ValueError("Development contract drifted")
    for key, name in {"synthetic_corpus":"public-synthetic-prompt-scope-corpus.json", "response_schema":"response.schema.json", "external_manifest":"external-real-text-holdout-manifest.json"}.items():
        if contract["bindings"].get(key) != name or contract["bindings"].get(f"{key}_sha256") != sha256_file(ROOT / name): raise ValueError("Source binding drifted")
    projection = dict(contract); bindings = dict(projection["bindings"]); bindings.pop("contract_projection_sha256"); projection["bindings"] = bindings
    if contract["bindings"].get("contract_projection_sha256") != EXPECTED_CONTRACT_PROJECTION_SHA256 or sha256_bytes(canonical_json(projection)) != EXPECTED_CONTRACT_PROJECTION_SHA256: raise ValueError("Contract pin drifted")

def validate_corpus(corpus: Mapping[str, Any]) -> None:
    records = corpus.get("records")
    if corpus.get("format_version") != 2 or not isinstance(records, list) or len(records) != 18: raise ValueError("Corpus geometry drifted")
    cells = sum(len(record["target_verdicts"]) for record in records)
    if cells != 28 or any(not set(record["target_verdicts"]).issubset(LEAVES) for record in records): raise ValueError("Leaf geometry drifted")

def build_plan(corpus: Mapping[str, Any], contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_contract(contract); validate_corpus(corpus); plan=[]
    for record in corpus["records"]:
        for leaf, verdict in record["target_verdicts"].items():
            for arm in ARMS:
                for repeat in range(1,4):
                    units=list(record["units"]); request_id=f"fst-v1-dev-{record['case_id']}-{leaf.rsplit('.',1)[-1]}-{arm}-repeat-{repeat}"
                    plan.append({"request_id":request_id,"study_id":STUDY_ID,"partition":"development","arm":arm,"case_id":record["case_id"],"leaf_id":leaf,"repeat":repeat,"units":units,"artifact_sha256":sha256_bytes(canonical_json(units)),"expected_verdict":verdict,"controller_scope_materiality":record["controller_scope_materiality"],"controller_scope_verdict":record.get("controller_scope_verdict")})
    return sorted(plan,key=lambda item:item["request_id"])

def verify_package() -> dict[str, Any]:
    contract=load_json("study-contract.json"); corpus=load_json("public-synthetic-prompt-scope-corpus.json"); validate_contract(contract); validate_corpus(corpus); plan=build_plan(corpus,contract)
    if len(plan)!=168: raise ValueError("Development plan must contain 168 requests")
    return {"study_id":STUDY_ID,"development_cells":28,"manual_arms":list(ARMS),"development_requests":168,"provider_calls_permitted":False,"successor_rule":"Freeze a separate successor only after this manual development comparison has a result.","synthetic_corpus_sha256":sha256_file(ROOT/"public-synthetic-prompt-scope-corpus.json")}
