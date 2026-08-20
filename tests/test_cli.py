from __future__ import annotations

import json
from pathlib import Path

from hbqrs.cli import main
from hbqrs.pack import pack_book


def test_list_bundles(capsys) -> None:
    assert main(["list", "bundles"]) == 0
    payload = json.loads(capsys.readouterr().out)
    ids = {item["bundle_id"] for item in payload}
    assert "prose.scene" in ids
    assert len(payload) == 85


def test_show_and_export(capsys, tmp_path: Path) -> None:
    assert main(["show", "prose.scene"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["bundle"]["bundle_id"] == "prose.scene"
    assert shown["compiled_counts"]["domain_questions"] > 0

    out = tmp_path / "scene.jsonl"
    assert main(["export", "questions", "--bundle", "prose.scene", "--output", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert rows
    assert all(row["bundle_id"] == "prose.scene" for row in rows)


def test_score_example(capsys) -> None:
    assert main(["score", "prose.scene", "examples/verdicts_example.jsonl"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["bundle_id"] == "prose.scene"
    assert "final_score" in report


def test_render_judge(tmp_path: Path) -> None:
    dest = tmp_path / "judge.md"
    assert (
        main(
            [
                "render-judge",
                "--bundle",
                "prose.scene",
                "--artifact",
                "examples/sample_scene.md",
                "--output",
                str(dest),
            ]
        )
        == 0
    )
    text = dest.read_text(encoding="utf-8")
    assert "YES, NO, NOT_APPLICABLE, or CANNOT_ASSESS" in text
    assert "Mara counted the coins" in text
    assert "core.task_and_brief_fidelity" in text


def test_validate() -> None:
    assert main(["validate"]) == 0


def test_pack_roundtrip(tmp_path: Path) -> None:
    import shutil

    from hbqrs import book_root

    src = book_root()
    dest = tmp_path / "book"
    shutil.copytree(src / "registry", dest / "registry")
    shutil.copytree(src / "bundles", dest / "bundles")
    summary = pack_book(dest)
    assert summary["modules"] == 277
    assert summary["questions"] == 2139
    assert summary["bundles"] == 85
    rebuilt = json.loads((dest / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    assert {item["module_id"] for item in rebuilt} == {
        path.stem for path in (src / "registry" / "modules").glob("*.yaml")
    }
