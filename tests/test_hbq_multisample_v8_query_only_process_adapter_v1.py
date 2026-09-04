from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = (
    Path(__file__).parents[1]
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-v8-query-only-process-adapter-v1"
    / "adapter.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("query_only_test", PATH)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_loaded_guard_substitutes_only_each_target_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    original_probe = lambda _pid: True
    guard = SimpleNamespace(
        STUDY_ID="guard",
        _load_v8=lambda _executor: SimpleNamespace(
            _pid_is_dead=original_probe, unchanged="ok"
        ),
    )
    monkeypatch.setattr(
        module, "_load_exact_one", lambda: SimpleNamespace(_load_guard=lambda: guard)
    )
    loaded = module.load_query_only_guard()._load_v8(Path("executor.py"))
    assert loaded._pid_is_dead is module.query_only_pid_is_dead
    assert loaded.unchanged == "ok"


def test_native_query_does_not_terminate_disposable_child() -> None:
    if os.name != "nt":
        pytest.skip("Windows native process-query proof")
    module = _module()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        assert module.query_only_pid_is_dead(child.pid) is False
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=10)
    assert module.query_only_pid_is_dead(child.pid) is True


@pytest.mark.parametrize("pid", [-1, 0, True, False, 1.5, "1", 0x100000000])
def test_invalid_pid_fails_closed(pid) -> None:
    assert _module().query_only_pid_is_dead(pid) is False


@pytest.mark.parametrize(
    "handle,error,query_ok,exit_code,expected",
    [
        (0, 87, True, 0, True),
        (0, 5, True, 0, False),
        (0, 999, True, 0, False),
        (2**40, 0, False, 0, False),
        (2**40, 0, True, 259, False),
        (2**40, 0, True, 0, True),
    ],
)
def test_query_semantics_and_full_width_handle(
    monkeypatch, handle, error, query_ok, exit_code, expected
):
    module = _module()
    calls = []
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(module.ctypes, "get_last_error", lambda: error, raising=False)

    def open_process(access, inherit, pid):
        assert (access, inherit, pid) == (0x1000, False, 17088)
        return handle

    def query(value, pointer):
        assert value == handle
        pointer._obj.value = exit_code
        return query_ok

    monkeypatch.setattr(
        module,
        "_kernel32",
        lambda: SimpleNamespace(
            OpenProcess=open_process,
            GetExitCodeProcess=query,
            CloseHandle=lambda value: calls.append(value),
        ),
    )
    assert module.query_only_pid_is_dead(17088) is expected
    assert calls == ([handle] if handle else [])


def test_real_pinned_loader_patches_every_fresh_target_without_preflight():
    module = _module()
    exact = module.load_query_only_exact_one()
    runtime = exact.DEFAULT_V8_RUNTIME
    if not runtime.is_dir():
        pytest.skip("local frozen V8 runtime is not present")
    guard, target, _, executor = exact._load_pinned_modules(runtime)
    before = {
        path: module.sha(path)
        for path in (module.EXACT_ONE, exact.GUARD_PATH, executor)
    }
    targets = [
        target,
        guard._load_v8(executor),
        guard._load_v8(executor),
        exact._load_guard()._load_v8(executor),
    ]
    assert len({id(item) for item in targets}) == 4
    assert all(item._pid_is_dead is module.query_only_pid_is_dead for item in targets)
    assert before == {path: module.sha(path) for path in before}


def test_binding_roundtrip_rejects_every_top_level_mutation(tmp_path):
    module = _module()
    exact = module.load_query_only_exact_one()
    if not exact.DEFAULT_V8_RUNTIME.is_dir():
        pytest.skip("local frozen V8 runtime is not present")
    root = tmp_path / "supplement"
    record = module.prepare_operational_binding(
        root, v8_runtime_root=exact.DEFAULT_V8_RUNTIME
    )
    assert module._binding(root, exact.DEFAULT_V8_RUNTIME) == record
    path = root / module.BINDING
    baseline = path.read_bytes()
    for key in record:
        changed = dict(record)
        changed[key] = "tampered"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match="binding drifted"):
            module._binding(root, exact.DEFAULT_V8_RUNTIME)
    path.write_bytes(baseline)
    (root / "orphan").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="binding drifted"):
        module._binding(root, exact.DEFAULT_V8_RUNTIME)


def test_preflight_and_dispatch_are_default_off_and_forward_only_expected_arguments(
    monkeypatch, tmp_path
):
    module = _module()
    monkeypatch.setattr(module, "_binding", lambda *args: {})
    calls = []

    def precontact(*, guard, v8, runtime, source_root):
        calls.append((guard, v8, runtime, source_root))
        return "checked"

    exact = SimpleNamespace(
        _load_pinned_modules=lambda runtime: ("guard", "target", runtime, "executor"),
        _precontact=precontact,
        dispatch_one=lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(module, "load_query_only_exact_one", lambda: exact)
    kwargs = {
        "binding_root": tmp_path,
        "v8_runtime_root": tmp_path,
        "source_root": tmp_path,
    }
    for function in (module.preflight_one, module.dispatch_one):
        with pytest.raises(ValueError, match="explicit remote authority"):
            function(**kwargs)
    assert calls == []
    assert module.preflight_one(**kwargs, allow_remote=True, timeout=1) == "checked"
    module.dispatch_one(**kwargs, allow_remote=True)
    assert calls == [
        ("guard", "target", tmp_path, tmp_path),
        {"allow_remote": True, "v8_runtime_root": tmp_path, "source_root": tmp_path},
    ]


def test_native_terminated_child_is_absent() -> None:
    if os.name != "nt":
        pytest.skip("Windows native process-query proof")
    module = _module()
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=10)
    assert module.query_only_pid_is_dead(child.pid) is True
