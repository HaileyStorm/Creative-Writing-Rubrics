"""Provider-free checks for the prospective current-Broker WPB bridge."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_broker_continuation.py"


def load():
    spec = importlib.util.spec_from_file_location("wpb_sol_broker_bridge_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(module, path: Path, value: dict) -> str:
    raw = module.canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return module.sha256(raw)


def review(module, path: Path, anchors: dict, source: dict) -> str:
    return write(module, path, {
        "format_version": 1,
        "kind": "wpb_sol_broker_bridge_independent_review_v1",
        "decision": "approved_wpb_sol_broker_bridge",
        "campaign_sha256": anchors["campaign"]["sha256"],
        "freeze_sha256": anchors["freeze"]["sha256"],
        "independent_freeze_review_sha256": anchors["independent_freeze_review"]["sha256"],
        "source_manifest_sha256": module.sha256(source),
        "bridge_helper_sha256": source["bridge_helper"]["sha256"],
        "legacy_helper_sha256": module.LEGACY_SHA256,
        "sol_route_sha256": module.SOL_ROUTE_SHA256,
    })


def companion(module, root: Path, number: int, anchors: dict, source: dict, review_path: Path, review_sha: str) -> Path:
    plan_path = root / "batches" / f"{number:04d}" / "plan.json"
    plan_sha = write(module, plan_path, {"route_sha256": module.SOL_ROUTE_SHA256})
    path = plan_path.with_name("bridge-companion.json")
    write(module, path, {
        "format_version": 1,
        "kind": "wpb_sol_broker_bridge_companion_v1",
        "batch_number": number,
        "legacy_plan_sha256": plan_sha,
        **anchors,
        "source_manifest": source,
        "source_manifest_sha256": module.sha256(source),
        "bridge_review": {"path": str(review_path.resolve()), "sha256": review_sha},
        "legacy_broker_pin_executed": False,
    })
    return path


def test_real_current_package_loads_without_provider_contact(tmp_path: Path) -> None:
    module = load()
    manifest = module.source_manifest()
    queue = tmp_path / "queue"
    queue.mkdir()
    shutil.copyfile(Path.home() / ".codex/state/model-work-queue/routes.json", queue / "routes.json")
    broker = module.broker_factory(manifest)(queue)
    broker.init()
    registry = broker._load_registry_live()
    routes = [route for route in registry["routes"] if route.get("name") == "codex-chatgpt-gpt-5.6-sol"]
    assert len(routes) == 1
    assert module.sha256(routes[0]) == module.SOL_ROUTE_SHA256
    assert type(broker).__name__ == "Broker"
    assert broker.root == queue.resolve()
    assert (queue / "queue.sqlite3").is_file()
    assert manifest["queue_package"]["files"]["broker.py"] == module._SOURCE_PINS["broker.py"]
    assert module.canonical({"route": "sol"}).endswith(b"\n")


def test_actual_campaign_freeze_and_review_are_required() -> None:
    module = load()
    anchors = module._anchors(module.DEFAULT_CAMPAIGN.parent, module.DEFAULT_FREEZE, module.DEFAULT_FREEZE_REVIEW)
    assert anchors["campaign"]["sha256"] == module.CAMPAIGN_SHA256
    with pytest.raises(ValueError, match="campaign path"):
        module._anchors(Path("."), module.DEFAULT_FREEZE, module.DEFAULT_FREEZE_REVIEW)
    with pytest.raises(ValueError, match="freeze path"):
        module._anchors(module.DEFAULT_CAMPAIGN.parent, Path("arbitrary-freeze.json"), module.DEFAULT_FREEZE_REVIEW)
    with pytest.raises(ValueError, match="freeze review path"):
        module._anchors(module.DEFAULT_CAMPAIGN.parent, module.DEFAULT_FREEZE, Path("arbitrary-review.json"))


def test_outer_review_rejects_mismatched_campaign_freeze_or_source_binding(tmp_path: Path) -> None:
    module = load()
    source = module._source_manifest()
    anchors = {"campaign": {"path": "campaign", "sha256": "a" * 64}, "freeze": {"path": "freeze", "sha256": "b" * 64},
               "independent_freeze_review": {"path": "review", "sha256": "c" * 64}}
    path = tmp_path / "bridge-review.json"
    digest = review(module, path, anchors, source)
    assert module._bridge_review(path, digest, anchors=anchors, source=source) == digest
    value, _raw = module._read(path, "test review")
    value["freeze_sha256"] = "0" * 64
    changed = write(module, path, value)
    with pytest.raises(ValueError, match="independent review differs"):
        module._bridge_review(path, changed, anchors=anchors, source=source)


def test_missing_or_cross_batch_companion_is_rejected(tmp_path: Path) -> None:
    module = load()
    source = module._source_manifest()
    anchors = {"campaign": {"path": "campaign", "sha256": "a" * 64}, "freeze": {"path": "freeze", "sha256": "b" * 64},
               "independent_freeze_review": {"path": "review", "sha256": "c" * 64}}
    review_path = tmp_path / "bridge-review.json"
    review_sha = review(module, review_path, anchors, source)
    companion(module, tmp_path, 1, anchors, source, review_path, review_sha)
    module._companion(tmp_path, 1, anchors=anchors, source=source, bridge_review_path=review_path,
                      bridge_review_sha256=review_sha, require_current_source=True)
    with pytest.raises(ValueError, match="invalid WPB Sol bridge companion"):
        module._companion(tmp_path, 2, anchors=anchors, source=source, bridge_review_path=review_path,
                          bridge_review_sha256=review_sha, require_current_source=True)
    companion(module, tmp_path, 2, anchors, source, review_path, review_sha)
    copied = (tmp_path / "batches" / "0001" / "bridge-companion.json").read_bytes()
    (tmp_path / "batches" / "0002" / "bridge-companion.json").write_bytes(copied)
    with pytest.raises(ValueError, match="bridge companion differs"):
        module._companion(tmp_path, 2, anchors=anchors, source=source, bridge_review_path=review_path,
                          bridge_review_sha256=review_sha, require_current_source=True)


def test_source_drift_rejects_before_legacy_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load()
    source = module._source_manifest()
    anchors = {"campaign": {"path": "campaign", "sha256": "a" * 64}, "freeze": {"path": "freeze", "sha256": "b" * 64},
               "independent_freeze_review": {"path": "review", "sha256": "c" * 64}}
    review_path = tmp_path / "bridge-review.json"
    review_sha = review(module, review_path, anchors, source)
    companion(module, tmp_path, 1, anchors, source, review_path, review_sha)
    changed = {**source, "bridge_helper": {**source["bridge_helper"], "sha256": "0" * 64}}
    monkeypatch.setattr(module, "_anchors", lambda *_args: anchors)
    monkeypatch.setattr(module, "_source_manifest", lambda: changed)
    monkeypatch.setattr(module, "_load_legacy", lambda: pytest.fail("legacy dispatch must not run after source drift"))
    with pytest.raises(ValueError, match="companion source differs"):
        module.dispatch_batch(campaign_root=tmp_path, freeze_path=tmp_path / "freeze.json", batch_number=1,
                              allow_remote=True, bridge_review_path=review_path, expected_bridge_review_sha256=review_sha)


@pytest.mark.parametrize("mutation, message", [("review", "review anchor drifted"), ("companion", "invalid WPB Sol bridge companion")])
def test_dispatch_factory_rechecks_outer_review_and_companion_before_later_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, message: str,
) -> None:
    module = load()
    source = module._source_manifest()
    anchors = {"campaign": {"path": "campaign", "sha256": "a" * 64}, "freeze": {"path": "freeze", "sha256": "b" * 64},
               "independent_freeze_review": {"path": "review", "sha256": "c" * 64}}
    review_path = tmp_path / "bridge-review.json"
    review_sha = review(module, review_path, anchors, source)
    companion_path = companion(module, tmp_path, 1, anchors, source, review_path, review_sha)
    contacts = 0

    def dispatch_batch(**kwargs):
        nonlocal contacts
        factory = kwargs["broker_factory"]
        factory(tmp_path / "queue")
        if mutation == "review":
            value, _raw = module._read(review_path, "test review")
            value["freeze_sha256"] = "0" * 64
            write(module, review_path, value)
        else:
            companion_path.unlink()
        try:
            factory(tmp_path / "queue")
        except ValueError as error:
            assert message in str(error)
        else:
            contacts += 1
        return []

    monkeypatch.setattr(module, "_anchors", lambda *_args: anchors)
    monkeypatch.setattr(module, "_source_manifest", lambda: source)
    monkeypatch.setattr(module, "_load_legacy", lambda: SimpleNamespace(dispatch_batch=dispatch_batch))
    assert module.dispatch_batch(campaign_root=tmp_path, freeze_path=tmp_path / "freeze.json", batch_number=1,
                                 allow_remote=True, bridge_review_path=review_path,
                                 expected_bridge_review_sha256=review_sha) == []
    assert contacts == 0


def test_dispatch_preserves_legacy_stop_no_resend_and_capture_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load()
    source = module._source_manifest()
    anchors = {"campaign": {"path": "campaign", "sha256": "a" * 64}, "freeze": {"path": "freeze", "sha256": "b" * 64},
               "independent_freeze_review": {"path": "review", "sha256": "c" * 64}}
    review_path = tmp_path / "bridge-review.json"
    review_sha = review(module, review_path, anchors, source)
    companion(module, tmp_path, 1, anchors, source, review_path, review_sha)
    captured: dict[str, object] = {}
    sentinel = object()

    def dispatch_batch(**kwargs):
        captured.update(kwargs)
        return [{"cell_id": "cell-1", "status": "terminal_no_resend", "provider_calls_made": 0}]

    monkeypatch.setattr(module, "_anchors", lambda *_args: anchors)
    monkeypatch.setattr(module, "_source_manifest", lambda: source)
    monkeypatch.setattr(module, "_load_legacy", lambda: SimpleNamespace(dispatch_batch=dispatch_batch))
    result = module.dispatch_batch(campaign_root=tmp_path, freeze_path=tmp_path / "freeze.json", batch_number=1,
                                   allow_remote=True, call_codex=sentinel, bridge_review_path=review_path,
                                   expected_bridge_review_sha256=review_sha)
    assert result == [{"cell_id": "cell-1", "status": "terminal_no_resend", "provider_calls_made": 0}]
    assert captured["call_codex"] is sentinel
    assert callable(captured["broker_factory"])
