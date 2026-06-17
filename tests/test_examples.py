from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from etcm import load
from etcm.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_ml_example_validates_from_cli(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(EXAMPLES / "ml/train.etcm#smoke")

    exit_code = main(["validate", selector, "--short"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out == f"OK: {selector}\n"


def test_ml_example_loads_as_dict() -> None:
    cfg = cast(dict[str, Any], load(str(EXAMPLES / "ml/train.etcm#smoke"), target="dict"))

    assert cfg["run_name"] == "smoke"
    assert cfg["max_steps"] == 2
    assert cfg["model"] == {"name": "tiny-lm", "layers": 4, "hidden_size": 128}
    assert cfg["runtime"]["accelerator"] == "cpu"
    assert cfg["runtime"]["checkpoint_dir"].endswith("examples/ml/outputs/local")
