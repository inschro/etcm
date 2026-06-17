from __future__ import annotations

import json
from pathlib import Path

import pytest

from etcm.cli import main

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def test_resolve_command_prints_unvalidated_graph_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#smoke")

    exit_code = main(["resolve", selector])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["root_selector"] == selector
    assert payload["validated"] is False
    assert [node["id"] for node in payload["nodes"]] == ["root", "root.model"]


def test_validate_command_prints_validated_graph_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#smoke")

    exit_code = main(["validate", selector])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["root_selector"] == selector
    assert payload["validated"] is True


def test_validate_short_reports_success(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#smoke")

    exit_code = main(["validate", selector, "--short"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == f"OK: {selector}\n"
    assert captured.err == ""


def test_validate_command_reports_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "invalid/missing_required.etcm")

    exit_code = main(["validate", selector])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "E_MISSING_FIELD: Missing required field 'name'." in captured.err
    assert "graph_path: root.name" in captured.err


def test_load_command_defaults_to_dict_target(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "valid/spec_inheritance_resolver/cuda.etcm#default")

    exit_code = main(["load", selector])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"device": "cuda", "gpus": 2}


@pytest.mark.parametrize("target", ["dict", "dataclass", "pydantic"])
def test_load_command_target_modes_emit_json(
    target: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/spec_inheritance_resolver/cuda.etcm#default")

    exit_code = main(["load", selector, "--target", target])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"device": "cuda", "gpus": 2}


def test_load_dataclass_target_serializes_paths_as_strings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/path_policies/data.etcm")

    exit_code = main(["load", selector, "--target", "dataclass"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert isinstance(payload["existing_file"], str)
    assert payload["existing_file"].endswith(
        "tests/fixtures/valid/path_policies/data/existing.txt"
    )


def test_load_command_reports_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "invalid/missing_required.etcm")

    exit_code = main(["load", selector])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "E_MISSING_FIELD: Missing required field 'name'." in captured.err


@pytest.mark.parametrize("command", ["inspect", "graph"])
def test_removed_commands_fail_argparse(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#smoke")

    with pytest.raises(SystemExit) as raised:
        main([command, selector])

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert captured.out == ""
    assert "invalid choice" in captured.err
