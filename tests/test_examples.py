from __future__ import annotations

import importlib.util
from dataclasses import is_dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from etcm import load
from etcm.cli import main
from etcm.errors import ETCMError

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_EXAMPLES = ROOT / "documentation/examples"
QUICKSTART_EXAMPLE = DOCUMENTATION_EXAMPLES / "pet-boarding/01-quickstart"
BASIC_ML_EXAMPLE = DOCUMENTATION_EXAMPLES / "ml-training/01-basic"
ADVANCED_ML_EXAMPLE = DOCUMENTATION_EXAMPLES / "ml-training/02-advanced"


def test_documentation_examples_validate(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["validate-all", str(DOCUMENTATION_EXAMPLES), "--quiet"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out == "12 total, 12 OK, 0 fail\n"


def test_pet_quickstart_loads_as_dict() -> None:
    selector = QUICKSTART_EXAMPLE / "pets.etcm#Pet:pepper"

    pet = cast(dict[str, Any], load(str(selector), target="dict"))

    assert pet == {"name": "Pepper", "daily_food_grams": 300}


def test_basic_ml_example_composes_and_recalculates_derived_values() -> None:
    selector = BASIC_ML_EXAMPLE / "train.etcm#TrainRun:smoke"

    base = cast(dict[str, Any], load(str(selector), target="dict"))
    overridden = cast(
        dict[str, Any],
        load(
            str(selector),
            target="dict",
            overrides={
                "micro_batch_size": 4,
                "gradient_accumulation_steps": 3,
            },
        ),
    )

    assert base["model"] == {"name": "tiny-mlp", "hidden_size": 16, "layers": 1}
    assert base["effective_batch_size"] == 8
    assert overridden["effective_batch_size"] == 12

    with pytest.raises(ETCMError) as constraint_error:
        load(str(selector), overrides={"learning_rate": -0.1})
    assert constraint_error.value.diagnostic.code == "E_CONSTRAINT"


def test_advanced_ml_example_materializes_a_nested_dataclass() -> None:
    selector = ADVANCED_ML_EXAMPLE / "train.etcm#TrainRun:baseline"

    config: Any = load(str(selector), target="dataclass")

    assert is_dataclass(config)
    dynamic = cast(Any, config)
    model = cast(Any, dynamic.model)
    runtime = cast(Any, dynamic.runtime)
    optimizer = cast(Any, dynamic.optimizer)
    assert model.name == "baseline-mlp"
    assert runtime.device == "cpu"
    assert isinstance(runtime.output_dir, Path)
    assert runtime.output_dir.name == "local"
    assert is_dataclass(model)
    assert is_dataclass(runtime)
    assert is_dataclass(optimizer)
    assert dynamic.dataset == {
        "name": "synthetic-classification",
        "input_features": 8,
        "classes": 3,
    }
    assert dynamic.tags == ["training", "smoke", "baseline"]
    assert dynamic.metadata == {"team": "research", "purpose": "baseline"}
    assert dynamic.effective_batch_size == 32


def test_advanced_ml_override_policies_protect_seed_and_version() -> None:
    selector = str(ADVANCED_ML_EXAMPLE / "train.etcm#TrainRun:smoke")

    with pytest.raises(ETCMError) as seed_error:
        load(selector, overrides={"seed": 11})
    assert seed_error.value.diagnostic.code == "E_INVALID_OVERRIDE"

    forced: Any = load(
        selector,
        target="dataclass",
        overrides={"seed": 11},
        force_overrides=True,
    )
    assert forced.seed == 11

    with pytest.raises(ETCMError) as version_error:
        load(
            selector,
            overrides={"config_version": 2},
            force_overrides=True,
        )
    assert version_error.value.diagnostic.code == "E_INVALID_OVERRIDE"

    with pytest.raises(ETCMError) as assertion_error:
        load(selector, overrides={"checkpoint_every": 3})
    assert assertion_error.value.diagnostic.code == "E_ASSERTION"


def test_advanced_argparse_wrapper_forwards_deep_overrides() -> None:
    script = cast(Any, _load_advanced_script())
    args = script.build_parser().parse_args(
        [
            "--set",
            "model.hidden_size=32",
            "--set",
            "optimizer.learning_rate=0.0005",
            "--set",
            "seed=11",
            "--force-overrides",
        ]
    )

    config: Any = script.load_config(args)

    assert config.model.hidden_size == 32
    assert config.optimizer.learning_rate == 0.0005
    assert config.seed == 11


@pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="PyTorch is optional")
def test_advanced_script_builds_pytorch_objects_when_available() -> None:
    script = cast(Any, _load_advanced_script())
    config: Any = script.load_config(script.build_parser().parse_args([]))

    inputs, model, optimizer, logits, checkpoint = script.build_objects(config)

    assert tuple(inputs.shape) == (8, 8)
    assert model.__class__.__name__ == "Sequential"
    assert optimizer.__class__.__name__ == "AdamW"
    assert tuple(logits.shape) == (8, 3)
    assert checkpoint == config.runtime.output_dir / "smoke.pt"


def _load_advanced_script() -> ModuleType:
    path = ADVANCED_ML_EXAMPLE / "train.py"
    spec = importlib.util.spec_from_file_location("etcm_advanced_tutorial", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import tutorial script at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
