from __future__ import annotations

import json
from pathlib import Path

import hbqrs.cli as cli
import pytest
from hbqrs.cli import build_parser, main
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


def test_compile_accepts_documented_short_output_option(tmp_path: Path) -> None:
    out = tmp_path / "scene.json"
    assert main(["compile", "prose.scene", "-o", str(out)]) == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["bundle_id"] == "prose.scene"
    assert packet["counts"]["domain_questions"] > 0


def test_short_output_option_is_consistent_across_commands() -> None:
    cases = (
        ["validate", "-o", "result.json"],
        ["compile", "prose.scene", "-o", "result.json"],
        ["score", "prose.scene", "verdicts.jsonl", "-o", "result.json"],
        ["list", "bundles", "-o", "result.json"],
        ["show", "prose.scene", "-o", "result.json"],
        ["export", "questions", "-o", "result.jsonl"],
        ["render-judge", "--bundle", "prose.scene", "-o", "result.txt"],
        ["pack", "-o", "result.json"],
        ["init-score-profile", "draft.txt", "-o", "profile.json"],
        ["render-report", "report.json", "-o", "report.html"],
    )
    parser = build_parser()
    for argv in cases:
        assert parser.parse_args(argv).output == argv[-1]


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


def test_judge_command_dispatches_runner(monkeypatch, capsys, tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("test", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_judge(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "DRY_RUN", "run_id": "test-run"}

    monkeypatch.setattr(cli, "run_judge", fake_run_judge)
    assert (
        main(
            [
                "judge",
                str(artifact),
                "--bundle",
                "prose.scene",
                "--provider",
                "openai",
                "--model",
                "fake-local",
                "--output-dir",
                str(tmp_path / "run"),
                "--dry-run",
            ]
        )
        == 0
    )
    assert captured["artifact_path"] == str(artifact)
    assert captured["bundle_id"] == "prose.scene"
    assert captured["batch_attempts"] == 3
    assert captured["grok_bin"] == "grok"
    assert captured["allow_unattested_reasoning"] is False
    assert captured["upgrade_legacy_normalization"] is False
    assert json.loads(capsys.readouterr().out)["status"] == "DRY_RUN"


def test_longform_command_dispatches_workflow(monkeypatch, capsys, tmp_path: Path) -> None:
    artifact = tmp_path / "manuscript.txt"
    brief = tmp_path / "brief.txt"
    artifact.write_text("Chapter One\n\nTest.", encoding="utf-8")
    brief.write_text("Prefer quiet tension.", encoding="utf-8")
    score_profile = tmp_path / "score-profile.json"
    score_profile.write_text(
        json.dumps(
            {
                "profile_version": 1,
                "profile_id": "balanced",
                "global_weight": 7,
                "local_weight": 3,
                "local_reducer": "weighted_mean",
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run_longform_judge(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "DRY_RUN", "unit_count": 1}

    monkeypatch.setattr(cli, "run_longform_judge", fake_run_longform_judge)
    assert (
        main(
            [
                "longform",
                str(artifact),
                "--brief",
                str(brief),
                "--provider",
                "codex",
                "--model",
                "gpt-5.6-sol",
                "--wip",
                "--bundle",
                "prose.novel",
                "--module",
                "core.language_craft",
                "--hierarchical-score-profile",
                str(score_profile),
                "--output-dir",
                str(tmp_path / "run"),
                "--frozen-sample-ordinal",
                "1",
                "--frozen-sample-ordinal",
                "3",
                "--openai-structured-outputs",
                "--batch-attempts",
                "5",
                "--allow-remote",
                "--dry-run",
            ]
        )
        == 0
    )
    assert captured["artifact_path"] == str(artifact)
    assert captured["brief_paths"] == [str(brief)]
    assert captured["artifact_kind"] == "prose_fiction"
    assert captured["completion_status"] == "work_in_progress"
    assert captured["bundle_id"] == "prose.novel"
    assert captured["module_ids"] == ["core.language_craft"]
    assert captured["task_contract_path"] is None
    assert captured["hierarchical_score_profile"] == {
        "profile_version": 1,
        "profile_id": "balanced",
        "global_weight": 7,
        "local_weight": 3,
        "local_reducer": "weighted_mean",
    }
    assert captured["structured_reasoning"] == "high"
    assert captured["judge_reasoning"] == "medium"
    assert captured["local_sample_limit"] is None
    assert captured["frozen_sample_ordinals"] == [1, 3]
    assert captured["binary_workers"] == 1
    assert captured["batch_attempts"] == 5
    assert captured["grok_bin"] == "grok"
    assert captured["allow_unattested_reasoning"] is False
    assert captured["upgrade_legacy_normalization"] is False
    assert captured["openai_structured_outputs"] is True
    assert captured["plan_only"] is False
    assert json.loads(capsys.readouterr().out)["status"] == "DRY_RUN"


def test_resume_normalization_upgrade_is_explicit_and_help_describes_cumulative_retries(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("test", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_judge(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "DRY_RUN"}

    monkeypatch.setattr(cli, "run_judge", fake_run_judge)
    assert main(
        [
            "judge", str(artifact), "--bundle", "prose.scene", "--provider", "openai",
            "--model", "fake-local", "--output-dir", str(tmp_path / "run"), "--resume",
            "--upgrade-legacy-normalization", "--dry-run",
        ]
    ) == 0
    assert captured["upgrade_legacy_normalization"] is True
    with pytest.raises(SystemExit):
        main(
            [
                "judge", str(artifact), "--bundle", "prose.scene", "--provider", "openai",
                "--model", "fake-local", "--output-dir", str(tmp_path / "new-run"),
                "--upgrade-legacy-normalization", "--dry-run",
            ]
        )
    with pytest.raises(SystemExit):
        main(["judge", "--help"])
    help_text = capsys.readouterr().out
    assert "--upgrade-legacy-normalization" in help_text
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if action.dest == "command"
    )
    judge = subparsers.choices["judge"]
    batch_attempts = next(action for action in judge._actions if action.dest == "batch_attempts")
    assert batch_attempts.help == (
        "maximum cumulative provider attempts per batch; new-policy retries include validation feedback"
    )


def test_longform_html_renders_for_a_valid_control_state(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "manuscript.txt"
    artifact.write_text("Chapter One\n\nTest.", encoding="utf-8")
    output = tmp_path / "run"

    def fake_run_longform_judge(**kwargs: object) -> dict[str, object]:
        output.mkdir(parents=True, exist_ok=True)
        (output / "report.json").write_text("{}", encoding="utf-8")
        return {"status": "VALID"}

    monkeypatch.setattr(cli, "run_longform_judge", fake_run_longform_judge)
    monkeypatch.setattr(cli, "render_html_report", lambda report: "full")
    monkeypatch.setattr(cli, "render_html_scorecard", lambda report: "card")
    assert main(
        [
            "longform", str(artifact), "--provider", "codex", "--model", "gpt-5.6-sol",
            "--output-dir", str(output), "--html-report",
        ]
    ) == 0
    assert (output / "report.html").read_text(encoding="utf-8") == "full"
    assert (output / "scorecard.html").read_text(encoding="utf-8") == "card"


def test_init_weight_profile_and_configurator_commands(tmp_path: Path) -> None:
    profile = tmp_path / "weights.json"
    setup = tmp_path / "setup.html"
    weight_setup = tmp_path / "weights.html"
    assert main(["init-weight-profile", "prose.scene", "-o", str(profile)]) == 0
    value = json.loads(profile.read_text(encoding="utf-8"))
    assert value["bundle_id"] == "prose.scene"
    assert value["domain_weights"]
    assert value["component_weights"]
    assert value["group_weights"]
    assert value["question_weights"]
    assert main(["configure", "-o", str(setup)]) == 0
    html = setup.read_text(encoding="utf-8")
    assert "Automatic route selection" in html
    assert "Confirm compatible modules" in html
    assert main(["configure-weights", "prose.scene", "-o", str(weight_setup)]) == 0
    weight_html = weight_setup.read_text(encoding="utf-8")
    assert "Every deterministic scoring layer" not in weight_html
    assert "Penalty caps" in weight_html
    assert "--weight-profile" in weight_html


def test_longform_wip_flag_is_explicit_and_mutually_exclusive() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "longform",
            "draft.txt",
            "--provider",
            "codex",
            "--model",
            "gpt-5.6-sol",
            "--output-dir",
            "run",
            "--wip",
        ]
    )
    assert args.completion_status == "work_in_progress"
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "longform",
                "draft.txt",
                "--provider",
                "codex",
                "--model",
                "gpt-5.6-sol",
                "--output-dir",
                "run",
                "--wip",
                "--completion-status",
                "complete",
            ]
        )


def test_init_score_profile_binds_shared_modifiers_to_segmented_units(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "draft.txt"
    artifact.write_text(
        "Gray Blood\n\nChapter One\n\nComplete chapter.\n\nChapter Two\n\nPartial chapter.",
        encoding="utf-8",
    )
    output = tmp_path / "weights.json"
    assert (
        main(
            [
                "init-score-profile",
                str(artifact),
                "-o",
                str(output),
                "--unfinished-unit-ordinal",
                "3",
                "--unfinished-unit-weight",
                "0.4",
                "--prologue-epilogue-weight",
                "0.75",
            ]
        )
        == 0
    )
    profile = json.loads(output.read_text(encoding="utf-8"))
    assert profile["global_weight"] == 7.0
    assert profile["local_weight"] == 3.0
    assert profile["unfinished_unit_weight"] == 0.4
    assert len(profile["unfinished_unit_ids"]) == 1
    assert profile["unfinished_unit_ids"][0].startswith("unit-0003-")
    assert profile["prologue_epilogue_weight"] == 0.75
    assert "unit_weights" not in profile


def test_init_score_profile_exports_trim_profile_that_the_cli_reloads(tmp_path: Path) -> None:
    artifact = tmp_path / "draft.txt"
    artifact.write_text(
        "Chapter One\n\nFirst.\n\nChapter Two\n\nSecond.\n\nChapter Three\n\nThird.",
        encoding="utf-8",
    )
    output = tmp_path / "profile.json"
    assert (
        main(
            [
                "init-score-profile",
                str(artifact),
                "-o",
                str(output),
                "--local-reducer",
                "trim_one_per_tail",
            ]
        )
        == 0
    )
    profile = json.loads(output.read_text(encoding="utf-8"))
    assert profile["local_reducer"] == "trim_one_per_tail"
    assert cli._load_hierarchical_score_profile(output) == profile


def test_init_score_profile_rejects_noneligible_front_matter_ordinal(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "draft.txt"
    artifact.write_text("Title\n\nChapter One\n\nProse.", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(
            [
                "init-score-profile",
                str(artifact),
                "-o",
                str(tmp_path / "weights.json"),
                "--unfinished-unit-ordinal",
                "1",
            ]
        )


def test_render_report_writes_full_and_compact_html(tmp_path: Path) -> None:
    from hbqrs.html_report import render_html_report
    from test_html_report import _report

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    full = tmp_path / "report.html"
    compact = tmp_path / "scorecard.html"
    assert main(["render-report", str(report_path), "-o", str(full)]) == 0
    assert main(["render-report", str(report_path), "-o", str(compact), "--scorecard"]) == 0
    assert "<!doctype html>" in full.read_text(encoding="utf-8").lower()
    assert "Custom-weighted composite" in compact.read_text(encoding="utf-8")


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
    assert summary["modules"] == 278
    assert summary["questions"] == 2145
    assert summary["bundles"] == 85
    rebuilt = json.loads((dest / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    assert {item["module_id"] for item in rebuilt} == {
        path.stem for path in (src / "registry" / "modules").glob("*.yaml")
    }
