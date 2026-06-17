from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from etcm import convert, load, resolve, validate
from etcm.codegen import pydantic_schema_summary
from etcm.errors import ETCMError

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def test_load_dict_materializes_nested_refs() -> None:
    cfg = load(str(FIXTURES / "valid/typed_refs/train.etcm#smoke"), target="dict")

    assert cfg == {"max_steps": 2, "model": {"depth": 4}}


def test_convert_dataclass_materializes_frozen_nested_objects() -> None:
    graph = validate(resolve(str(FIXTURES / "valid/typed_refs/train.etcm#smoke")))

    cfg: Any = convert(graph, target="dataclass")

    assert hasattr(cfg, "__dataclass_fields__")
    assert cfg.max_steps == 2
    assert cfg.model.depth == 4
    with pytest.raises(FrozenInstanceError):
        cfg.max_steps = 3


def test_convert_pydantic_materializes_frozen_nested_objects() -> None:
    graph = validate(resolve(str(FIXTURES / "valid/typed_refs/train.etcm#smoke")))

    cfg: Any = convert(graph, target="pydantic")

    assert cfg.max_steps == 2
    assert cfg.model.depth == 4
    assert cfg.model_dump(mode="json") == {"max_steps": 2, "model": {"depth": 4}}
    with pytest.raises(ValidationError):
        cfg.max_steps = 3


def test_path_values_materialize_as_strings_for_dict_and_paths_for_objects() -> None:
    selector = str(FIXTURES / "valid/path_policies/data.etcm")

    dict_cfg = cast(dict[str, Any], load(selector, target="dict"))
    dataclass_cfg: Any = load(selector, target="dataclass")

    assert isinstance(dict_cfg["existing_file"], str)
    assert dict_cfg["existing_file"].endswith(
        "tests/fixtures/valid/path_policies/data/existing.txt"
    )
    assert isinstance(dataclass_cfg.existing_file, Path)


def test_convert_requires_validated_graph_unless_forced() -> None:
    graph = resolve(str(FIXTURES / "valid/typed_refs/train.etcm#smoke"))

    with pytest.raises(ETCMError, match="unvalidated graph"):
        convert(graph, target="dict")

    assert convert(graph, target="dict", force=True) == {"max_steps": 2, "model": {"depth": 4}}


def test_pydantic_schema_summary_matches_golden() -> None:
    graph = validate(resolve(str(FIXTURES / "valid/typed_refs/train.etcm#smoke")))

    assert pydantic_schema_summary(graph) == _read_golden("pydantic", "typed_refs")


def _read_golden(kind: str, name: str) -> dict[str, Any]:
    path = FIXTURES / "golden" / kind / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
