from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from etcm import load
from etcm.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_ml_example_validates_from_cli(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(EXAMPLES / "ml/train.etcm#TrainRun:smoke")

    exit_code = main(["validate", selector, "--short"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out == f"OK: {selector}\n"


def test_ml_example_loads_as_dict() -> None:
    cfg = cast(
        dict[str, Any],
        load(str(EXAMPLES / "ml/train.etcm#TrainRun:smoke"), target="dict"),
    )

    assert cfg["run_name"] == "smoke"
    assert cfg["max_steps"] == 2
    assert cfg["global_batch_size"] == 4
    assert cfg["model_hidden_size"] == 128
    assert cfg["model"] == {"name": "tiny-lm", "layers": 4, "hidden_size": 128}
    assert cfg["runtime"]["accelerator"] == "cpu"
    assert cfg["runtime"]["checkpoint_dir"].endswith("examples/ml/outputs/local")
    assert cfg["system_prompt"] == "Answer each training request precisely and concisely.\n"
    assert cfg["artifact"] == b"ETCM example binary artifact\n"
