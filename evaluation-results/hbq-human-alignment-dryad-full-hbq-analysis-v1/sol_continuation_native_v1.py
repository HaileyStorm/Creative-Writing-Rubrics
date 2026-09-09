"""Native replay shared by the post-773 Sol continuation and its read-only checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent
AUTHORITY = Path("C:/Users/Haile/Documents/cwr-dryad-sol773-replacement-authority-20260909-r1")
PREDECESSOR_SOURCE_SHA = "2138e139599b17de719e55d49b0ba6d0d98e5f645427a3e79d564ae673d272ba"
REPLACEMENT_DRIVER_SHA = "a4a956e1449524ce43a9014e5dd74e4720e7e52874647197e4db788de3dea222"
PREFIX_SHA = "83e80e62f47f28a4aefef01f39c9455b16108029ab7e8395709b2f27c33ab6cd"
TERMINAL_SHA = "b4400854ad04ed8913f0cdccd775c215e5a3183af61dc6c28f5a8833c7fccdca"
AUTHORIZATION_SHA = "8c2740c8f3ecd359d2daf1690d9b35965b7bc160da6c1e2034a504f4f1c9b7ab"
PLAN_SHA = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
ROUTE_KEYS = ("name", "provider", "adapter", "destination", "account_class", "model", "reasoning_effort",
              "timeout_seconds", "codex_command", "codex_command_identity")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _base():
    path = ROOT / "sol773_replacement_execution.py"
    _require(_sha(path.read_bytes()) == PREDECESSOR_SOURCE_SHA, "Reviewed predecessor source differs")
    spec = importlib.util.spec_from_file_location("_sol_continuation_predecessor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def adapter():
    base = _base()
    return base._load(base.ADAPTER_PATH, base.ADAPTER_SHA256, "adapter")


def request_payload(plan_root: Path, ordinal: int) -> tuple[dict, bytes, bytes]:
    plan_root = Path(plan_root)
    raw = (plan_root / "plan.json").read_bytes()
    _require(_sha(raw) == PLAN_SHA and type(ordinal) is int and 773 <= ordinal <= 5428,
             "Frozen plan or ordinal differs")
    plan = json.loads(raw)
    request = next(row for row in plan["requests"] if row["ordinal"] == ordinal)
    passed = next(row for row in plan["passes"] if row["pass_id"] == request["pass_id"])
    source = (plan_root / passed["input_path"]).read_bytes()
    _require(_sha(source) == passed["source_sha256"] and len(source) == passed["source_bytes"], "Frozen story differs")
    payloads = []
    for name in ("prompt", "schema"):
        value = (plan_root / request[f"{name}_path"]).read_bytes()
        _require(_sha(value) == request[f"{name}_sha256"] and len(value) == request[f"{name}_bytes"], "Frozen payload differs")
        payloads.append(value)
    return request, *payloads


def route_snapshot(queue_root: Path, expected_identity: dict) -> dict:
    rows = json.loads((Path(queue_root) / "routes.json").read_bytes())["routes"]
    selected = [row for row in rows if row.get("name") == "codex-chatgpt-gpt-5.6-sol"]
    _require(len(selected) == 1, "Sol route is absent or duplicated")
    route = selected[0]
    _require({key: route[key] for key in ROUTE_KEYS} == expected_identity
             and route["provider"] == "openai_codex" and route["adapter"] == "codex_exec"
             and route["destination"] == "openai_codex_chatgpt_subscription"
             and route["account_class"] == "subscription" and route["model"] == "gpt-5.6-sol"
             and route["reasoning_effort"] == "high" and route["armed"] is True
             and route["health"] == "healthy" and route["zero_charge"] is True, "Subscription route differs")
    _require(_sha(Path(route["codex_command"][0]).read_bytes())
             == route["codex_command_identity"]["artifacts"][0]["sha256"], "Sol CLI differs")
    return route


def validate_native(output_root: Path, request: dict, route: dict, response_raw: bytes, record: dict) -> dict:
    root = Path(output_root).resolve()
    ordinal, batch = request["ordinal"], request["batch_number"]
    for name, suffix in (("prompt", "txt"), ("schema", "json")):
        raw = (root / f"payload/request-{ordinal:04d}.{suffix}").read_bytes()
        _require(_sha(raw) == request[f"{name}_sha256"] and len(raw) == request[f"{name}_bytes"], "Saved payload differs")
    schema_path = root / f"payload/request-{ordinal:04d}.json"
    schema = json.loads(schema_path.read_bytes())
    response = json.loads(response_raw)
    jsonschema.validate(response, schema)
    _require([row["question_id"] for row in response["verdicts"]] == request["question_ids"], "Response IDs differ")
    message_path = root / f"responses/batch-{batch:04d}.attempt-0001.message.json"
    _require(message_path.read_bytes() == response_raw, "Native final message differs")
    native = adapter()._base()
    expected = list(native._expected_codex_command(route["codex_command"][0], root))
    expected[expected.index("--output-schema") + 1] = str(schema_path)
    expected[expected.index("--output-last-message") + 1] = str(message_path)
    expected[-1:-1] = ["--disable", "code_mode"]
    _require(record.get("command") == expected, "Native command differs")
    artifacts = record.get("provider_artifacts")
    _require(isinstance(artifacts, dict) and set(artifacts) == {"codex_events", "codex_stderr"}, "Native artifacts differ")
    contents = {}
    for key, descriptor in artifacts.items():
        path = (root / descriptor["path"]).resolve()
        _require(path.is_relative_to(root), "Native artifact path differs")
        raw = path.read_bytes()
        _require(_sha(raw) == descriptor["sha256"] and len(raw) == descriptor["bytes"], "Native artifact bytes differ")
        contents[key] = raw
    projection = native._codex_event_projection(contents["codex_events"], native._load_parse_codex_events())
    _require(record.get("reported") == native._strict_stderr_labels(contents["codex_stderr"])
             and projection["completed_agent_message_text"].encode("utf-8") == response_raw
             and isinstance(projection["thread_id"], str) and bool(projection["thread_id"])
             and isinstance(projection["usage"], dict), "Native projection differs")
    return {"verdicts": response["verdicts"], "thread_id": projection["thread_id"],
            "usage": projection["usage"], "response_sha256": _sha(response_raw)}


def predecessor(plan_root: Path, original_root: Path, replacement_root: Path) -> dict:
    base = _base()
    manifest_raw, manifest = base._manifest(AUTHORITY / "manifest-candidate-v3.json")
    review_raw, _ = base._review(AUTHORITY / "independent-review-v1.json", manifest_raw)
    decision = AUTHORITY / "owner-decision-v1.json"
    base._decision(decision, manifest_raw, review_raw)
    _require(Path(plan_root).resolve() == Path(manifest["plan"]["path"]).parent.resolve()
             and Path(original_root).resolve() == Path(manifest["native"]["root"]).resolve()
             and Path(replacement_root).resolve() == Path(manifest["replacement_root"]).resolve(), "Predecessor roots differ")
    base._frozen_payload(manifest)
    root = Path(replacement_root)
    terminal_raw = (root / "replacement-terminal.json").read_bytes()
    _require(_sha(terminal_raw) == TERMINAL_SHA, "Accepted replacement terminal differs")
    terminal = json.loads(terminal_raw)
    authorization_raw = (root / "replacement-authorization.json").read_bytes()
    _require(_sha(authorization_raw) == AUTHORIZATION_SHA, "Replacement authorization differs")
    authorization = json.loads(authorization_raw)
    start_raw = (root / "replacement-start.json").read_bytes()
    start = json.loads(start_raw)
    _require(_sha(start_raw) == terminal["start_sha256"] and start["manifest_sha256"] == _sha(manifest_raw)
             and authorization["start_sha256"] == _sha(start_raw)
             and start["owner_decision_sha256"] == _sha(decision.read_bytes())
             and start["actual_driver_sha256"] == REPLACEMENT_DRIVER_SHA
             and _sha((ROOT / "sol773_owner_assumed_allowance_execution.py").read_bytes()) == REPLACEMENT_DRIVER_SHA,
             "Replacement execution lineage differs")
    request, _, _ = request_payload(Path(plan_root), 773)
    route = json.loads((root / "runtime/route.json").read_bytes())
    _require({key: route[key] for key in ROUTE_KEYS} == manifest["route_identity"], "Replacement route differs")
    response_raw = (root / "replacement-response.json").read_bytes()
    result = validate_native(root, request, route, response_raw, json.loads((root / "replacement-provider-record.json").read_bytes()))
    _require(result["response_sha256"] == terminal["response_sha256"] and result["thread_id"] == terminal["thread_id"],
             "Replacement result differs")
    prefix_path = AUTHORITY.parent / "cwr-dryad-sol772-interruption-prefix-reconciliation-20260909-r1.json"
    _require(_sha(prefix_path.read_bytes()) == PREFIX_SHA, "Preserved prefix differs")
    threads = []
    for path in sorted(Path(original_root).glob("runs/**/responses/batch-*.attempt-0001.events.jsonl")):
        for line in path.read_bytes().splitlines():
            event = json.loads(line)
            if event.get("type") == "thread.started":
                threads.append(event["thread_id"])
    _require(len(threads) == len(set(threads)) == 772 and result["thread_id"] not in threads, "Inherited native identities differ")
    return {"plan_sha256": PLAN_SHA, "through_ordinal": 773, "verdict_count": 5986,
            "thread_ids": threads + [result["thread_id"]], "route_identity": manifest["route_identity"],
            "commitments": {"prefix772_sha256": PREFIX_SHA, "replacement_terminal_sha256": TERMINAL_SHA,
                            "replacement_authorization_sha256": AUTHORIZATION_SHA,
                            "replacement_authorized_at": authorization["authorized_at"],
                            "replacement_response_sha256": result["response_sha256"],
                            "replacement_driver_sha256": REPLACEMENT_DRIVER_SHA,
                            "original_native_tree_sha256": manifest["native"]["tree_sha256"],
                            "owner_decision_sha256": _sha(decision.read_bytes()),
                            "allowance_policy": "owner_assumed_available_without_fresh_receipts",
                            "recovered_transport_adopted_ordinal": 221,
                            "pass19_coverage_rejection_retained": True,
                            "full_study_admission": False}}
