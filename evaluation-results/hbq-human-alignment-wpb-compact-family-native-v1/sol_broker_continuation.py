"""Prospective WPB bridge to the current source-pinned Sol broker package."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
LEGACY = HERE / "sol_batched_execution.py"
LEGACY_SHA256 = "5d8b0237a8e8819f5e42c1eb80a50d9b7c872a5d629b6c8e9cfb3ad577b0c474"
QUEUE_PACKAGE = Path(r"C:\Users\Haile\.codex\tools\model_work_queue")
DEFAULT_CAMPAIGN = Path(r"C:\Users\Haile\Documents\cwr-wpb-sol-batched-validation-20260910-r1\campaign.json")
DEFAULT_FREEZE = Path(r"C:\Users\Haile\Documents\cwr-wpb-grok-selection-freeze-20260910-r1\grok-selection-freeze.json")
DEFAULT_FREEZE_REVIEW = Path(r"C:\Users\Haile\Documents\cwr-wpb-grok-selection-freeze-independent-review-20260910-r1.json")
CAMPAIGN_SHA256 = "de7cdfc40a8748e9a168a9065f318c5342ee4476ea034ae72b45c67dae3b359a"
FREEZE_SHA256 = "3728ab40a311fcf9cc89c7adb218cc16f1adac7b81ffd970de6318e109fa1eac"
FREEZE_REVIEW_SHA256 = "bc685bb8b84a25d515d44dd5783f056dd89e30828554bd77a3604b08488a1a40"
SOL_ROUTE_SHA256 = "58a8cc27685cd9e61bd134301efec6248dce3f1ce69e42b6df7aa765adb3c16e"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_PINS = {
    "adapters/codex_exec.py": "89b906fe488c663d23cc1f5d0d8d3b5d0bf105fbdae96a848598bc2a1f6e3cee",
    "adapters/json_schema_subset.py": "9b593fbc7f45b9fd965b567e3153b34fd8efd842248f6c5bb10821c643592c95",
    "broker.py": "4cfe6b0b41172e9ecc32d572fbaa27c725b1aceb3beda95c3505c57bc2a6c02a",
    "grok_usage_evidence.py": "dc5e00849699858445d966783bfa2b2afc5255b896f41544196ac023c82be99f",
    "image_canary.py": "17104449da596b2be542d7670f6dee5034a13b78b13f16732da63c852f5e4998",
    "prepare_grok_evidence.py": "8562536fecbb417365003ec86db606c87fc2e434043cbf1fc98cee34ec7539b3",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read(path: Path, label: str, expected_sha256: str | None = None) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    _require(isinstance(value, dict) and raw == canonical(value), f"noncanonical {label}")
    if expected_sha256 is not None:
        _require(sha256(raw) == expected_sha256, f"{label} anchor drifted")
    return value, raw


def _read_source(path: Path, expected_sha256: str, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"missing {label}") from error
    _require(sha256(raw) == expected_sha256, f"{label} source drifted")
    return raw


def _load_legacy() -> ModuleType:
    raw = _read_source(LEGACY, LEGACY_SHA256, "WPB Sol legacy helper")
    name = f"_wpb_sol_legacy_{uuid.uuid4().hex}"
    module = ModuleType(name)
    module.__file__ = str(LEGACY)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(LEGACY), "exec"), module.__dict__)  # noqa: S102 - hash-pinned raw bytes avoid unverified .pyc.
    finally:
        sys.modules.pop(name, None)
    _require(_read_source(LEGACY, LEGACY_SHA256, "WPB Sol legacy helper") == raw,
             "WPB Sol legacy helper changed while loading")
    return module


def _source_manifest() -> dict[str, Any]:
    files: dict[str, str] = {}
    for relative, expected in _SOURCE_PINS.items():
        path = QUEUE_PACKAGE.joinpath(*relative.split("/"))
        _read_source(path, expected, f"current Sol broker {relative}")
        files[relative] = expected
    legacy = _read_source(LEGACY, LEGACY_SHA256, "WPB Sol legacy helper")
    wrapper = HERE / "sol_broker_continuation.py"
    try:
        wrapper_raw = wrapper.read_bytes()
    except OSError as error:
        raise ValueError("missing WPB Sol bridge helper") from error
    return {
        "format_version": 1,
        "kind": "wpb_sol_current_broker_source_manifest_v1",
        "legacy_helper": {"path": str(LEGACY.resolve()), "sha256": sha256(legacy)},
        "bridge_helper": {"path": str(wrapper.resolve()), "sha256": sha256(wrapper_raw)},
        "queue_package": {"path": str(QUEUE_PACKAGE.resolve()), "files": files},
        "canonical_json_trailing_newline": True,
        "sol_route_sha256": SOL_ROUTE_SHA256,
    }


def source_manifest() -> dict[str, Any]:
    """Return the current verified source closure without touching a queue or provider."""
    value = _source_manifest()
    return {**value, "sha256": sha256(value)}


def _verify_source_manifest(value: Mapping[str, Any]) -> None:
    supplied = dict(value)
    declared = supplied.pop("sha256", None)
    expected = _source_manifest()
    _require(declared is None or declared == sha256(expected), "WPB Sol bridge source manifest digest differs")
    _require(supplied == expected, "WPB Sol bridge source manifest drifted")


def _execute_module(name: str, path: Path, raw: bytes, package: str) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = package
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - hash-pinned raw bytes avoid unverified .pyc.
    return module


def _load_current_broker(source: Mapping[str, Any]) -> type[Any]:
    _verify_source_manifest(source)
    root = QUEUE_PACKAGE.resolve()
    package = f"_wpb_sol_current_broker_{uuid.uuid4().hex}"
    loaded: list[str] = []
    try:
        container = ModuleType(package)
        container.__path__ = [str(root)]
        container.__package__ = package
        sys.modules[package] = container
        loaded.append(package)
        adapters_name = f"{package}.adapters"
        adapters = ModuleType(adapters_name)
        adapters.__path__ = [str(root / "adapters")]
        adapters.__package__ = adapters_name
        sys.modules[adapters_name] = adapters
        loaded.append(adapters_name)
        for relative in ("adapters/json_schema_subset.py", "grok_usage_evidence.py", "image_canary.py", "prepare_grok_evidence.py"):
            path = root.joinpath(*relative.split("/"))
            name = f"{package}.{relative[:-3].replace('/', '.')}"
            _execute_module(name, path, _read_source(path, _SOURCE_PINS[relative], f"current Sol broker {relative}"),
                            name.rpartition(".")[0])
            loaded.append(name)
        broker_name = f"{package}.broker"
        broker_path = root / "broker.py"
        broker = _execute_module(broker_name, broker_path, _read_source(
            broker_path, _SOURCE_PINS["broker.py"], "current Sol broker broker.py"), package)
        loaded.append(broker_name)
        result = getattr(broker, "Broker", None)
        _require(isinstance(result, type) and result.__module__ == broker_name,
                 "current Sol Broker did not originate from the pinned package")
        _verify_source_manifest(source)
        return result
    finally:
        for name in reversed(loaded):
            sys.modules.pop(name, None)


def broker_factory(source: Mapping[str, Any], *, before_create: Callable[[], None] | None = None) -> Callable[[Path], Any]:
    """The legacy hook loads the real package and verifies it on every route check."""
    captured = dict(source)

    def create(queue_root: Path) -> Any:
        if before_create is not None:
            before_create()
        return _load_current_broker(captured)(Path(queue_root))

    return create


def _anchors(campaign_root: Path, freeze_path: Path, freeze_review_path: Path) -> dict[str, Any]:
    campaign_path = Path(campaign_root).resolve() / "campaign.json"
    _require(campaign_path == DEFAULT_CAMPAIGN.resolve(), "WPB Sol campaign path differs")
    _require(Path(freeze_path).resolve() == DEFAULT_FREEZE.resolve(), "WPB Sol freeze path differs")
    _require(Path(freeze_review_path).resolve() == DEFAULT_FREEZE_REVIEW.resolve(), "WPB Sol freeze review path differs")
    campaign, _ = _read(campaign_path, "WPB Sol campaign", CAMPAIGN_SHA256)
    freeze, _ = _read(DEFAULT_FREEZE, "WPB Sol freeze", FREEZE_SHA256)
    review, _ = _read(DEFAULT_FREEZE_REVIEW, "WPB Sol freeze review", FREEZE_REVIEW_SHA256)
    _require(campaign.get("kind") == "wpb_sol_batched_campaign" and campaign.get("format_version") == 1
             and freeze.get("kind") == "wpb_grok_train_dev_selection_freeze" and freeze.get("format_version") == 1
             and review.get("kind") == "wpb_grok_selection_freeze_independent_review"
             and review.get("decision") == "approved_wpb_grok_selection_freeze" and review.get("format_version") == 1,
             "WPB Sol campaign/freeze/review schema differs")
    _require(campaign.get("freeze_sha256") == FREEZE_SHA256
             and campaign.get("independent_freeze_review_sha256") == FREEZE_REVIEW_SHA256
             and campaign.get("schedule_sha256") == freeze.get("schedule_sha256")
             and campaign.get("freeze_source_bindings_sha256") == review.get("freeze_source_bindings_sha256")
             and campaign.get("freeze_verifier_sha256") == review.get("freeze_verifier_sha256")
             and campaign.get("freeze_verifier_path") == review.get("freeze_verifier_path")
             and review.get("freeze_sha256") == FREEZE_SHA256,
             "WPB Sol campaign/freeze/review binding differs")
    return {
        "campaign": {"path": str(campaign_path), "sha256": CAMPAIGN_SHA256},
        "freeze": {"path": str(DEFAULT_FREEZE.resolve()), "sha256": FREEZE_SHA256},
        "independent_freeze_review": {"path": str(DEFAULT_FREEZE_REVIEW.resolve()), "sha256": FREEZE_REVIEW_SHA256},
    }


def _bridge_review(path: Path, expected_sha256: str, *, anchors: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    _require(isinstance(expected_sha256, str) and _HASH.fullmatch(expected_sha256) is not None,
             "WPB Sol bridge review anchor is invalid")
    value, raw = _read(Path(path), "WPB Sol bridge independent review", expected_sha256)
    expected = {
        "format_version": 1,
        "kind": "wpb_sol_broker_bridge_independent_review_v1",
        "decision": "approved_wpb_sol_broker_bridge",
        "campaign_sha256": anchors["campaign"]["sha256"],
        "freeze_sha256": anchors["freeze"]["sha256"],
        "independent_freeze_review_sha256": anchors["independent_freeze_review"]["sha256"],
        "source_manifest_sha256": sha256(source),
        "bridge_helper_sha256": source["bridge_helper"]["sha256"],
        "legacy_helper_sha256": LEGACY_SHA256,
        "sol_route_sha256": SOL_ROUTE_SHA256,
    }
    _require(value == expected, "WPB Sol bridge independent review differs")
    return sha256(raw)


def _companion_path(campaign_root: Path, batch_number: int) -> Path:
    return Path(campaign_root).resolve() / "batches" / f"{batch_number:04d}" / "bridge-companion.json"


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    raw = canonical(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return raw


def _recorded_source_manifest(value: Any) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "WPB Sol recorded source manifest differs")
    source = dict(value)
    expected_keys = {"format_version", "kind", "legacy_helper", "bridge_helper", "queue_package",
                     "canonical_json_trailing_newline", "sol_route_sha256"}
    _require(set(source) == expected_keys and source.get("format_version") == 1
             and source.get("kind") == "wpb_sol_current_broker_source_manifest_v1"
             and source.get("canonical_json_trailing_newline") is True and source.get("sol_route_sha256") == SOL_ROUTE_SHA256,
             "WPB Sol recorded source manifest schema differs")
    _require(source.get("legacy_helper") == {"path": str(LEGACY.resolve()), "sha256": LEGACY_SHA256},
             "WPB Sol recorded legacy source differs")
    bridge = source.get("bridge_helper")
    package = source.get("queue_package")
    _require(isinstance(bridge, Mapping) and bridge.get("path") == str((HERE / "sol_broker_continuation.py").resolve())
             and isinstance(bridge.get("sha256"), str) and _HASH.fullmatch(bridge["sha256"]) is not None
             and package == {"path": str(QUEUE_PACKAGE.resolve()), "files": _SOURCE_PINS},
             "WPB Sol recorded bridge source differs")
    return source


def _companion(campaign_root: Path, batch_number: int, *, anchors: Mapping[str, Any], source: Mapping[str, Any] | None,
               bridge_review_path: Path, bridge_review_sha256: str, require_current_source: bool) -> tuple[dict[str, Any], str]:
    path = _companion_path(campaign_root, batch_number)
    value, raw = _read(path, "WPB Sol bridge companion")
    plan, plan_raw = _read(path.with_name("plan.json"), "WPB Sol legacy batch plan")
    _require(plan.get("route_sha256") == SOL_ROUTE_SHA256, "WPB Sol legacy route hash differs")
    recorded = _recorded_source_manifest(value.get("source_manifest"))
    if source is not None:
        _require(dict(source) == recorded, "WPB Sol bridge companion source differs")
    review_sha = _bridge_review(bridge_review_path, bridge_review_sha256, anchors=anchors, source=recorded)
    expected = {
        "format_version": 1,
        "kind": "wpb_sol_broker_bridge_companion_v1",
        "batch_number": batch_number,
        "legacy_plan_sha256": sha256(plan_raw),
        **dict(anchors),
        "source_manifest": recorded,
        "source_manifest_sha256": sha256(recorded),
        "bridge_review": {"path": str(Path(bridge_review_path).resolve()), "sha256": review_sha},
        "legacy_broker_pin_executed": False,
    }
    _require(value == expected, "WPB Sol bridge companion differs")
    if require_current_source:
        _verify_source_manifest(recorded)
    return value, sha256(raw)


def prepare_next_batch(*, bridge_review_path: Path, expected_bridge_review_sha256: str, **kwargs: Any) -> dict[str, Any]:
    """Prepare through the frozen helper and add a separately reviewed bridge companion."""
    campaign_root = Path(kwargs["campaign_root"])
    anchors = _anchors(campaign_root, Path(kwargs["freeze_path"]), DEFAULT_FREEZE_REVIEW)
    source = _source_manifest()
    _bridge_review(bridge_review_path, expected_bridge_review_sha256, anchors=anchors, source=source)
    result = _load_legacy().prepare_next_batch(**(kwargs | {"broker_factory": broker_factory(source)}))
    _require(set(result) == {"batch_number", "plan_sha256", "prepared_cells", "provider_calls_made", "process_launches", "native_contact_count"}
             and result["provider_calls_made"] == 0 and result["process_launches"] == 0 and result["native_contact_count"] == 0,
             "WPB Sol legacy prepare result differs")
    batch_number = result["batch_number"]
    _require(type(batch_number) is int and batch_number >= 1, "WPB Sol legacy batch number differs")
    plan, plan_raw = _read(_companion_path(campaign_root, batch_number).with_name("plan.json"), "WPB Sol legacy batch plan")
    _require(sha256(plan_raw) == result["plan_sha256"] and plan.get("route_sha256") == SOL_ROUTE_SHA256,
             "WPB Sol legacy prepared plan differs")
    _verify_source_manifest(source)
    review_sha = _bridge_review(bridge_review_path, expected_bridge_review_sha256, anchors=anchors, source=source)
    companion = {
        "format_version": 1,
        "kind": "wpb_sol_broker_bridge_companion_v1",
        "batch_number": batch_number,
        "legacy_plan_sha256": sha256(plan_raw),
        **anchors,
        "source_manifest": source,
        "source_manifest_sha256": sha256(source),
        "bridge_review": {"path": str(Path(bridge_review_path).resolve()), "sha256": review_sha},
        "legacy_broker_pin_executed": False,
    }
    raw = _write_new(_companion_path(campaign_root, batch_number), companion)
    return {**result, "bridge_companion_sha256": sha256(raw), "legacy_broker_pin_executed": False}


def dispatch_batch(*, bridge_review_path: Path, expected_bridge_review_sha256: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Dispatch only a companion-bound batch through the old helper's rechecked factory hook."""
    campaign_root = Path(kwargs["campaign_root"]); batch_number = kwargs["batch_number"]
    _require(type(batch_number) is int and batch_number >= 1, "WPB Sol bridge batch number is invalid")
    anchors = _anchors(campaign_root, Path(kwargs["freeze_path"]), DEFAULT_FREEZE_REVIEW)
    source = _source_manifest()

    def recheck_companion() -> None:
        _companion(campaign_root, batch_number, anchors=anchors, source=source, bridge_review_path=bridge_review_path,
                   bridge_review_sha256=expected_bridge_review_sha256, require_current_source=True)

    recheck_companion()
    return _load_legacy().dispatch_batch(**(kwargs | {"broker_factory": broker_factory(source, before_create=recheck_companion)}))


def settle_batch(*, bridge_review_path: Path, expected_bridge_review_sha256: str, **kwargs: Any) -> dict[str, Any]:
    """Settle with recorded bridge provenance; it never claims the superseded broker pin executed."""
    campaign_root = Path(kwargs["campaign_root"]); batch_number = kwargs["batch_number"]
    anchors = _anchors(campaign_root, Path(kwargs["freeze_path"]), DEFAULT_FREEZE_REVIEW)
    companion, digest = _companion(campaign_root, batch_number, anchors=anchors, source=None,
                                    bridge_review_path=bridge_review_path, bridge_review_sha256=expected_bridge_review_sha256,
                                    require_current_source=False)
    result = _load_legacy().settle_batch(**kwargs)
    return {**result, "bridge_companion_sha256": digest,
            "legacy_broker_pin_executed": companion["legacy_broker_pin_executed"]}


def report(*, bridge_review_path: Path, expected_bridge_review_sha256: str, **kwargs: Any) -> dict[str, Any]:
    """Replay recorded bridge provenance before delegating to the frozen report helper."""
    campaign_root = Path(kwargs["campaign_root"])
    anchors = _anchors(campaign_root, Path(kwargs["freeze_path"]), DEFAULT_FREEZE_REVIEW)
    companions: dict[str, str] = {}
    batches = Path(campaign_root).resolve() / "batches"
    if batches.exists():
        for child in sorted(batches.iterdir()):
            if child.is_dir() and child.name.isdigit():
                _value, digest = _companion(campaign_root, int(child.name), anchors=anchors, source=None,
                                             bridge_review_path=bridge_review_path, bridge_review_sha256=expected_bridge_review_sha256,
                                             require_current_source=False)
                companions[child.name] = digest
    return {**_load_legacy().report(**kwargs), "bridge_companions": companions,
            "legacy_broker_pin_executed": False}
