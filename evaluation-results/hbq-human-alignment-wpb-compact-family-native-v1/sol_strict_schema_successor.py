"""WPB Sol successor that projects only the rejected root schema requirement."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
BRIDGE = HERE / "sol_broker_continuation.py"
BRIDGE_SHA256 = "f66167b9d2e20259de3dc5bb7f053e88a4fd223a405613a5317a254772c5da0a"
LEGACY = HERE / "sol_batched_execution.py"
LEGACY_SHA256 = "5d8b0237a8e8819f5e42c1eb80a50d9b7c872a5d629b6c8e9cfb3ad577b0c474"
FROZEN = HERE / "executor.py"
FROZEN_SHA256 = "b41ef08b9f93e0f6cb8646e96746240a058ce6d13392a80484caa61272421c10"
V3 = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
RECONCILIATION_SHA256 = "d3318ce3d18d6328062f0d31df09bf4d49a71dc67980c5e1975114cc94488ed5"
BASE_CAMPAIGN_SHA256 = "de7cdfc40a8748e9a168a9065f318c5342ee4476ea034ae72b45c67dae3b359a"
PREDECESSOR_SETTLEMENT_SHA256 = "c63c57a85300bb49e7b98f89ca5b89025b3db6889a9eba78c01d2c14bc194e95"
FAILED_CELL = "wpb-pair-wpb-en-0082"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    _require(isinstance(value, dict) and raw == canonical(value), f"noncanonical {label}")
    return value, raw


def _write_new(path: Path, value: Mapping[str, Any] | bytes) -> bytes:
    raw = value if isinstance(value, bytes) else canonical(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return raw


def _exact(path: Path, expected: str, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"missing {label}") from error
    _require(sha256(raw) == expected, f"{label} source drifted")
    return raw


def _time(value: Any, label: str) -> datetime:
    _require(type(value) is str and value.endswith("Z"), f"{label} must be UTC Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error


def _load_bridge() -> ModuleType:
    raw = _exact(BRIDGE, BRIDGE_SHA256, "broker bridge")
    module = ModuleType("_wpb_sol_strict_schema_bridge")
    module.__file__ = str(BRIDGE)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(BRIDGE), "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(module.__name__, None)
    _exact(BRIDGE, BRIDGE_SHA256, "broker bridge")
    _exact(LEGACY, LEGACY_SHA256, "legacy helper")
    _exact(FROZEN, FROZEN_SHA256, "frozen executor")
    _exact(V3, V3_SHA256, "V3 runtime")
    return module


def source_manifest() -> dict[str, Any]:
    """Return the entire source closure, including this executable successor."""
    bridge = _load_bridge()
    own = Path(__file__).resolve().read_bytes()
    return {
        "format_version": 2,
        "kind": "wpb_sol_strict_native_schema_successor_source_manifest_v2",
        "strict_successor": {"path": str(Path(__file__).resolve()), "sha256": sha256(own)},
        "bridge": {"path": str(BRIDGE.resolve()), "sha256": BRIDGE_SHA256},
        "legacy": {"path": str(LEGACY.resolve()), "sha256": LEGACY_SHA256},
        "frozen_executor": {"path": str(FROZEN.resolve()), "sha256": FROZEN_SHA256},
        "v3_runtime": {"path": str(V3.resolve()), "sha256": V3_SHA256},
        "broker_source_manifest": bridge.source_manifest(),
    }


def strict_native_schema(evaluation_schema: Mapping[str, Any]) -> dict[str, Any]:
    """The native schema differs solely by requiring observed_winner at the root."""
    value = copy.deepcopy(dict(evaluation_schema))
    _require(value.get("type") == "object" and value.get("additionalProperties") is False,
             "evaluation schema root is not a closed object")
    properties, required = value.get("properties"), value.get("required")
    _require(isinstance(properties, dict) and required == ["A", "B"]
             and set(properties) == {"A", "B", "observed_winner"}, "evaluation schema root differs")
    _require(isinstance(properties["observed_winner"], Mapping)
             and properties["observed_winner"].get("enum") == ["A", "B", "TIE"],
             "observed_winner contract differs")
    value["required"] = ["A", "B", "observed_winner"]
    return value


def _pointer(root: Mapping[str, Any], pointer: str, label: str) -> Mapping[str, Any]:
    _require(pointer.startswith("#/"), f"{label} has an unsupported $ref")
    value: Any = root
    for part in pointer[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        _require(isinstance(value, Mapping) and key in value, f"{label} $ref is missing")
        value = value[key]
    _require(isinstance(value, Mapping), f"{label} $ref is not a schema")
    return value


def _validate(schema: Mapping[str, Any], value: Any, label: str = "response", *, _root: Mapping[str, Any] | None = None,
              _refs: set[tuple[str, int]] | None = None) -> None:
    """Validate strict JSON-schema features used by the recorded native response schema."""
    root, refs = (schema if _root is None else _root), (set() if _refs is None else _refs)
    if "$ref" in schema:
        reference = schema["$ref"]
        _require(isinstance(reference, str), f"{label} $ref differs")
        marker = (reference, id(value)); _require(marker not in refs, f"{label} recursive $ref differs")
        _validate(_pointer(root, reference, label), value, label, _root=root, _refs=refs | {marker})
        schema = {key: item for key, item in schema.items() if key != "$ref"}
    if "const" in schema:
        _require(value == schema["const"], f"{label} const differs")
    if "enum" in schema:
        _require(value in schema["enum"], f"{label} enum differs")
    for key, exact in (("allOf", None), ("anyOf", False), ("oneOf", True)):
        if key in schema:
            options = schema[key]; _require(isinstance(options, list), f"{label} {key} differs")
            matches = 0
            for option in options:
                try:
                    _require(isinstance(option, Mapping), f"{label} {key} differs")
                    _validate(option, value, label, _root=root, _refs=refs); matches += 1
                except ValueError:
                    pass
            _require(matches >= 1 if exact is False else (matches == 1 if exact else matches == len(options)), f"{label} {key} differs")
    if "not" in schema:
        try:
            _validate(schema["not"], value, label, _root=root, _refs=refs)
        except ValueError:
            pass
        else:
            raise ValueError(f"{label} not differs")
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
             "number": type(value) in (int, float), "integer": type(value) is int, "boolean": type(value) is bool,
             "null": value is None}
    _require(kind is None or any(valid.get(item, False) for item in kinds), f"{label} must match its schema type")
    if isinstance(value, dict):
        properties, required = schema.get("properties", {}), schema.get("required", [])
        _require(isinstance(properties, Mapping) and isinstance(required, list), f"{label} object schema differs")
        _require(all(key in value for key in required), f"{label} required property is missing")
        _require(len(value) >= schema.get("minProperties", 0), f"{label} has too few properties")
        if "maxProperties" in schema:
            _require(len(value) <= schema["maxProperties"], f"{label} has too many properties")
        patterns = schema.get("patternProperties", {}); _require(isinstance(patterns, Mapping), f"{label} pattern properties differ")
        for key, item in value.items():
            children = ([properties[key]] if key in properties else []) + [child for pattern, child in patterns.items() if re.search(pattern, key)]
            if not children and schema.get("additionalProperties", True) is False:
                raise ValueError(f"{label} has an unexpected property")
            for child in children:
                _require(isinstance(child, Mapping), f"{label}.{key} schema differs")
                _validate(child, item, f"{label}.{key}", _root=root, _refs=refs)
            additional = schema.get("additionalProperties")
            if not children and isinstance(additional, Mapping):
                _validate(additional, item, f"{label}.{key}", _root=root, _refs=refs)
    if isinstance(value, list):
        _require(len(value) >= schema.get("minItems", 0), f"{label} has too few items")
        if "maxItems" in schema:
            _require(len(value) <= schema["maxItems"], f"{label} has too many items")
        if schema.get("uniqueItems") is True:
            _require(len({canonical(item) for item in value}) == len(value), f"{label} items are not unique")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                _validate(items, item, f"{label}[{index}]", _root=root, _refs=refs)
        elif isinstance(items, list):
            for index, item in enumerate(value):
                if index < len(items):
                    _validate(items[index], item, f"{label}[{index}]", _root=root, _refs=refs)
                elif schema.get("additionalItems") is False:
                    raise ValueError(f"{label} has an unexpected item")
    if isinstance(value, str):
        _require(len(value) >= schema.get("minLength", 0), f"{label} is too short")
        if "maxLength" in schema:
            _require(len(value) <= schema["maxLength"], f"{label} is too long")
        if "pattern" in schema:
            _require(re.search(schema["pattern"], value) is not None, f"{label} pattern differs")
    if type(value) in (int, float):
        for key, relation in (("minimum", lambda a, b: a >= b), ("maximum", lambda a, b: a <= b),
                              ("exclusiveMinimum", lambda a, b: a > b), ("exclusiveMaximum", lambda a, b: a < b)):
            if key in schema and not isinstance(schema[key], bool):
                _require(relation(value, schema[key]), f"{label} {key} differs")
        if schema.get("exclusiveMinimum") is True:
            _require("minimum" in schema and value > schema["minimum"], f"{label} exclusiveMinimum differs")
        if schema.get("exclusiveMaximum") is True:
            _require("maximum" in schema and value < schema["maximum"], f"{label} exclusiveMaximum differs")


def _reconciliation(path: Path) -> str:
    value, raw = _read(path, "first-batch reconciliation")
    _require(sha256(raw) == RECONCILIATION_SHA256 and value.get("automatic_resend_authorized") is False
             and value.get("campaign_sha256") == BASE_CAMPAIGN_SHA256 and value.get("settlement_sha256") == PREDECESSOR_SETTLEMENT_SHA256
             and value.get("failed_cell_id") == FAILED_CELL
             and any(isinstance(cell, Mapping) and cell.get("cell_id") == FAILED_CELL for cell in value.get("cells", [])),
             "first-batch reconciliation differs")
    return sha256(raw)


def _batch(root: Path, number: int) -> Path:
    _require(type(number) is int and number > 0, "batch number is invalid")
    return root / "batches" / f"{number:04d}"


def _successor_path(root: Path) -> Path:
    return root / "strict-schema-successor-manifest.json"


def _projection_path(batch: Path) -> Path:
    return batch / "strict-schema-projection.json"


def _binding_path(batch: Path) -> Path:
    return batch / "strict-schema-review-binding.json"


def _strict_path(batch: Path) -> Path:
    return batch / "strict-native-schema.json"


def _successor(root: Path) -> tuple[dict[str, Any], str]:
    value, raw = _read(_successor_path(root), "strict successor manifest")
    campaign_raw = _exact(root / "campaign.json", value.get("campaign", {}).get("sha256", ""), "successor campaign")
    current = source_manifest()
    _require(value.get("format_version") == 2 and value.get("kind") == "wpb_sol_strict_native_schema_successor_campaign_v2"
             and value.get("campaign") == {"path": str((root / "campaign.json").resolve()), "sha256": sha256(campaign_raw)}
             and value.get("source_manifest") == current and value.get("source_manifest_sha256") == sha256(current)
             and value.get("automatic_resend_authorized") is False
             and value.get("base_campaign", {}).get("sha256") == BASE_CAMPAIGN_SHA256
             and value.get("reconciliation", {}).get("sha256") == RECONCILIATION_SHA256, "strict successor manifest differs")
    lineage = value.get("cell_lineage")
    _require(isinstance(lineage, list) and len(lineage) == 129
             and [item for item in lineage if item.get("kind") == "replacement_after_unadmitted_failed_attempt"]
             == [{"cell_id": FAILED_CELL, "kind": "replacement_after_unadmitted_failed_attempt"}], "strict successor lineage differs")
    return value, sha256(raw)


def _schema_for_output(output_root: Path) -> tuple[Path, bytes]:
    cell = Path(output_root).resolve()
    _require(cell.parent.name == "execution" and cell.parent.parent.name.isdecimal(), "strict schema output root differs")
    original, _original_raw = _read(cell / "response-schema.json", "prepared evaluation schema")
    strict_path = _strict_path(cell.parent.parent); strict, strict_raw = _read(strict_path, "strict native schema")
    _require(strict == strict_native_schema(original), "strict native schema differs from evaluation schema")
    return strict_path, strict_raw


def _configure_runtime(runtime: ModuleType, resolution: Mapping[str, Any]) -> None:
    original_loader, original_validate = runtime._load_v3, runtime._validate_answer
    schemas = {canonical(json.loads(payload.decode("utf-8"))["response_schema"]) for payload in resolution["payloads"].values()}
    _require(len(schemas) == 1, "WPB evaluation schemas differ")
    strict = strict_native_schema(json.loads(next(iter(schemas)).decode("utf-8")))

    def validate(value: Mapping[str, Any]) -> dict[str, Any]:
        _validate(strict, value)
        return original_validate(value)

    def load_v3() -> ModuleType:
        v3 = original_loader()
        if getattr(v3, "_wpb_strict_schema_successor_configured", False):
            return v3
        _require(Path(v3.__file__).resolve() == V3.resolve() and sha256(V3.read_bytes()) == V3_SHA256, "strict successor V3 runtime differs")
        original_command = v3._expected_codex_command

        def command(executable: str, output_root: Path) -> list[str]:
            result = original_command(executable, output_root)
            index = result.index("--output-schema")
            _require(result[index + 1] == str(Path(output_root) / "response-schema.json"), "V3 command schema position drifted")
            strict_path, _raw = _schema_for_output(Path(output_root))
            result = list(result); result[index + 1] = str(strict_path)
            return result

        v3._expected_codex_command = command
        v3._wpb_strict_schema_successor_configured = True
        return v3

    runtime._validate_answer = validate
    runtime._load_v3 = load_v3


def _configured_legacy() -> tuple[ModuleType, ModuleType]:
    bridge = _load_bridge(); legacy = bridge._load_legacy(); original_frozen = legacy._frozen

    def frozen() -> ModuleType:
        module = original_frozen(); original_runtime = module._sol_runtime

        def sol_runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType, tuple[dict[str, Any], ...]]:
            lifecycle, runtime, rows = original_runtime(resolution)
            _configure_runtime(runtime, resolution)
            return lifecycle, runtime, rows

        module._sol_runtime = sol_runtime
        return module

    legacy._frozen = frozen
    return legacy, bridge


def _source_guard(expected: Mapping[str, Any]) -> None:
    _require(source_manifest() == expected, "strict successor source closure drifted")


def create_campaign(*, campaign_root: Path, base_campaign_path: Path, reconciliation_path: Path, **kwargs: Any) -> dict[str, Any]:
    """Create a fresh campaign and successor lineage before a route or provider is touched."""
    root = Path(campaign_root).resolve(); base, base_raw = _read(Path(base_campaign_path), "predecessor base campaign")
    _require(sha256(base_raw) == BASE_CAMPAIGN_SHA256 and base.get("kind") == "wpb_sol_batched_campaign"
             and isinstance(base.get("cells"), list) and len(base["cells"]) == 129, "predecessor base campaign differs")
    reconciliation_sha, source = _reconciliation(Path(reconciliation_path)), source_manifest()
    legacy, _bridge = _configured_legacy(); result = legacy.create_campaign(campaign_root=root, **kwargs)
    campaign, campaign_raw = _read(root / "campaign.json", "fresh successor campaign")
    ids, base_ids = [str(cell.get("cell_id")) for cell in campaign["cells"]], [str(cell.get("cell_id")) for cell in base["cells"]]
    _require(ids == base_ids and len(set(ids)) == 129, "fresh successor schedule differs")
    _source_guard(source)
    manifest = {
        "format_version": 2, "kind": "wpb_sol_strict_native_schema_successor_campaign_v2",
        "campaign": {"path": str((root / "campaign.json").resolve()), "sha256": sha256(campaign_raw)},
        "base_campaign": {"path": str(Path(base_campaign_path).resolve()), "sha256": sha256(base_raw)},
        "reconciliation": {"path": str(Path(reconciliation_path).resolve()), "sha256": reconciliation_sha},
        "source_manifest": source, "source_manifest_sha256": sha256(source),
        "cell_lineage": [{"cell_id": cell_id, "kind": "replacement_after_unadmitted_failed_attempt" if cell_id == FAILED_CELL else "first_contact_successor"} for cell_id in ids],
        "automatic_resend_authorized": False,
    }
    raw = _write_new(_successor_path(root), manifest)
    return {**result, "strict_successor_manifest_sha256": sha256(raw), "provider_calls_made": 0, "process_launches": 0}


def _projection(root: Path, number: int) -> tuple[dict[str, Any], str]:
    batch = _batch(root, number); value, raw = _read(_projection_path(batch), "strict schema projection")
    _manifest, successor_sha = _successor(root); plan, plan_raw = _read(batch / "plan.json", "legacy batch plan")
    strict, strict_raw = _read(_strict_path(batch), "strict native schema"); cells = plan.get("cell_ids")
    _require(isinstance(cells, list) and all(isinstance(cell, str) for cell in cells), "legacy batch cells differ")
    original_hashes = {}
    for cell_id in cells:
        original, original_raw = _read(batch / "execution" / cell_id / "response-schema.json", "prepared evaluation schema")
        _require(strict == strict_native_schema(original), "strict schema projection differs")
        original_hashes[cell_id] = sha256(original_raw)
    expected = {"format_version": 2, "kind": "wpb_sol_strict_native_schema_projection_v2", "successor_manifest_sha256": successor_sha,
                "legacy_plan_sha256": sha256(plan_raw), "batch_number": number, "cell_ids": cells,
                "evaluation_schema_sha256s": original_hashes, "strict_native_schema_sha256": sha256(strict_raw),
                "actual_commands": value.get("actual_commands"), "actual_command_sha256s": value.get("actual_command_sha256s"),
                "source_manifest_sha256": sha256(source_manifest())}
    _require(value == expected and isinstance(value["actual_commands"], Mapping)
             and value["actual_command_sha256s"] == {key: sha256(command) for key, command in value["actual_commands"].items()}
             and set(value["actual_commands"]) == set(cells), "strict schema projection differs")
    return value, sha256(raw)


def prepare_next_batch(*, strict_review_path: Path | None = None, expected_strict_review_sha256: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Use the frozen preparation path, then record an external strict-schema command projection."""
    del strict_review_path, expected_strict_review_sha256
    root, source = Path(kwargs["campaign_root"]).resolve(), source_manifest(); _successor(root)
    legacy, bridge = _configured_legacy()
    supplied_factory = kwargs.pop("broker_factory", None)
    _require(supplied_factory is None or callable(supplied_factory), "strict successor broker factory differs")
    factory = supplied_factory or bridge.broker_factory(source["broker_source_manifest"], before_create=lambda: _source_guard(source))
    result = legacy.prepare_next_batch(**(kwargs | {"broker_factory": factory}))
    number, batch = result["batch_number"], _batch(root, result["batch_number"])
    plan, plan_raw = _read(batch / "plan.json", "legacy batch plan"); cells = plan["cell_ids"]
    originals = [_read(batch / "execution" / cell_id / "response-schema.json", "prepared evaluation schema")[0] for cell_id in cells]
    _require(all(item == originals[0] for item in originals), "per-cell evaluation schema differs")
    strict_raw = canonical(strict_native_schema(originals[0])); _write_new(_strict_path(batch), strict_raw)
    frozen = legacy._frozen(); resolution = legacy._resolution(frozen, Path(kwargs["freeze_root"])); _lifecycle, runtime, _rows = frozen._sol_runtime(resolution)
    v3 = runtime._load_v3(); executable = plan["route"]["codex_command"][0]
    commands = {cell_id: v3._expected_codex_command(executable, batch / "execution" / cell_id) for cell_id in cells}
    _source_guard(source)
    _manifest, successor_sha = _successor(root)
    projection = {"format_version": 2, "kind": "wpb_sol_strict_native_schema_projection_v2", "successor_manifest_sha256": successor_sha,
                  "legacy_plan_sha256": sha256(plan_raw), "batch_number": number, "cell_ids": cells,
                  "evaluation_schema_sha256s": {cell_id: sha256((batch / "execution" / cell_id / "response-schema.json").read_bytes()) for cell_id in cells},
                  "strict_native_schema_sha256": sha256(strict_raw), "actual_commands": commands,
                  "actual_command_sha256s": {cell_id: sha256(command) for cell_id, command in commands.items()},
                  "source_manifest_sha256": sha256(source)}
    raw = _write_new(_projection_path(batch), projection)
    return {**result, "strict_schema_projection_sha256": sha256(raw), "provider_calls_made": 0, "process_launches": 0}


def review_material(*, campaign_root: Path, batch_number: int) -> dict[str, Any]:
    """Supply the exact record an independent reviewer must approve after preparation."""
    root = Path(campaign_root).resolve(); projection, projection_sha = _projection(root, batch_number)
    return {"format_version": 2, "kind": "wpb_sol_strict_native_schema_successor_independent_review_v2",
            "decision": "approved_wpb_sol_strict_native_schema_successor_dispatch", "projection_sha256": projection_sha,
            "successor_manifest_sha256": projection["successor_manifest_sha256"], "legacy_plan_sha256": projection["legacy_plan_sha256"],
            "batch_number": batch_number, "cell_ids": projection["cell_ids"],
            "strict_native_schema_sha256": projection["strict_native_schema_sha256"],
            "actual_command_sha256s": projection["actual_command_sha256s"],
            "source_manifest_sha256": projection["source_manifest_sha256"], "reviewed_at": None, "expires_at": None}


def _review(path: Path, expected_sha256: str, root: Path, number: int, *, require_unexpired: bool) -> str:
    _require(isinstance(expected_sha256, str) and _HASH.fullmatch(expected_sha256) is not None, "strict review anchor is invalid")
    value, raw = _read(path, "strict successor independent review"); expected = review_material(campaign_root=root, batch_number=number)
    _require(sha256(raw) == expected_sha256 and set(value) == set(expected)
             and all(value[key] == item for key, item in expected.items() if key not in {"reviewed_at", "expires_at"})
             and _time(value["reviewed_at"], "strict review reviewed_at") < _time(value["expires_at"], "strict review expires_at"),
             "strict successor independent review differs")
    if require_unexpired:
        _require(datetime.now(timezone.utc) < _time(value["expires_at"], "strict review expires_at"), "strict successor independent review has expired")
    return sha256(raw)


def _bind_review(root: Path, number: int, review_path: Path, review_sha256: str) -> dict[str, Any]:
    batch = _batch(root, number); projection, projection_sha = _projection(root, number)
    digest = _review(review_path, review_sha256, root, number, require_unexpired=True)
    value = {"format_version": 2, "kind": "wpb_sol_strict_native_schema_review_binding_v2", "projection_sha256": projection_sha,
             "review": {"path": str(Path(review_path).resolve()), "sha256": digest}, "source_manifest_sha256": projection["source_manifest_sha256"],
             "automatic_resend_authorized": False}
    _write_new(_binding_path(batch), value)
    return value


def _binding(root: Path, number: int, *, require_unexpired: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    batch = _batch(root, number); projection, projection_sha = _projection(root, number); value, _raw = _read(_binding_path(batch), "strict review binding")
    expected = {"format_version": 2, "kind": "wpb_sol_strict_native_schema_review_binding_v2", "projection_sha256": projection_sha,
                "review": value.get("review"), "source_manifest_sha256": projection["source_manifest_sha256"], "automatic_resend_authorized": False}
    _require(value == expected and isinstance(value["review"], Mapping) and isinstance(value["review"].get("path"), str)
             and isinstance(value["review"].get("sha256"), str), "strict review binding differs")
    _review(Path(value["review"]["path"]), value["review"]["sha256"], root, number, require_unexpired=require_unexpired)
    return value, projection


def dispatch_batch(*, strict_review_path: Path, expected_strict_review_sha256: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Dispatch through the frozen launcher only after every strict companion check passes."""
    root, number, source = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"], source_manifest(); _successor(root)
    legacy, bridge = _configured_legacy()
    supplied_factory = kwargs.pop("broker_factory", None)
    _require(supplied_factory is None or callable(supplied_factory), "strict successor broker factory differs")
    factory = supplied_factory or bridge.broker_factory(source["broker_source_manifest"], before_create=lambda: _source_guard(source))
    _bind_review(root, number, Path(strict_review_path), expected_strict_review_sha256)
    frozen = legacy._frozen(); resolution = legacy._resolution(frozen, Path(kwargs["freeze_root"])); _lifecycle, runtime, _rows = frozen._sol_runtime(resolution)
    base_call = kwargs.get("call_codex") or legacy._current_call_codex(runtime, receipt_root=_batch(root, number) / "sol-process-receipts")

    def strict_call(**call_kwargs: Any) -> tuple[str, dict[str, Any]]:
        _binding(root, number, require_unexpired=True); _source_guard(source)
        _bound, projection = _binding(root, number, require_unexpired=True)
        output_root = Path(call_kwargs["output_dir"]); cell_id = output_root.name
        actual = runtime._load_v3()._expected_codex_command(call_kwargs["executable"], output_root)
        _require(actual == projection["actual_commands"].get(cell_id),
                 "strict successor command drifted before contact")
        before = call_kwargs.get("before_provider_attempt"); _require(callable(before), "frozen Sol runtime omitted precontact gate")

        def guarded() -> None:
            _binding(root, number, require_unexpired=True); _source_guard(source); before()
        return base_call(**(call_kwargs | {"before_provider_attempt": guarded}))

    return legacy.dispatch_batch(**(kwargs | {"broker_factory": factory, "call_codex": strict_call}))


def settle_batch(**kwargs: Any) -> dict[str, Any]:
    root, number = Path(kwargs["campaign_root"]).resolve(), kwargs["batch_number"]; _successor(root); _binding(root, number, require_unexpired=False)
    legacy, _bridge = _configured_legacy()
    return legacy.settle_batch(**kwargs)


def report(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs["campaign_root"]).resolve(); _successor(root)
    batches = root / "batches"
    if batches.exists():
        for path in sorted(batches.iterdir()):
            if path.is_dir() and path.name.isdecimal():
                _binding(root, int(path.name), require_unexpired=False)
    legacy, _bridge = _configured_legacy(); result = legacy.report(**kwargs)
    return {**result, "strict_native_schema_successor": "v2", "native_admissions": result.get("measurement_count")}
