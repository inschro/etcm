from pathlib import Path

import pytest

from etcm import Resolver, convert, load, resolve, validate
from etcm.errors import ETCMError

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_resolver_accepts_path_policy() -> None:
    assert Resolver().path_exists == "allow_missing"
    assert Resolver(path_exists="must_exist").path_exists == "must_exist"


def test_resolver_rejects_unknown_path_policy() -> None:
    with pytest.raises(ValueError, match="path_exists"):
        Resolver(path_exists="sometimes")  # type: ignore[arg-type]


def test_resolve_validate_convert_pipeline() -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#smoke")

    graph = resolve(selector)
    assert graph.validated is False

    validated = validate(graph)
    assert validated.validated is True
    assert convert(validated, target="dict") == {"max_steps": 2, "model": {"depth": 4}}


def test_load_orchestrates_full_pipeline() -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#smoke")

    cfg = load(selector, target="dict")

    assert cfg == {"max_steps": 2, "model": {"depth": 4}}


def test_convert_requires_validated_graph_unless_forced() -> None:
    graph = resolve(str(FIXTURES / "valid/typed_refs/train.etcm#smoke"))

    with pytest.raises(ETCMError, match="unvalidated graph"):
        convert(graph, target="dict")

    assert convert(graph, target="dict", force=True) == {"max_steps": 2, "model": {"depth": 4}}


def test_convert_rejects_unknown_target() -> None:
    graph = validate(resolve(str(FIXTURES / "valid/typed_refs/train.etcm#smoke")))

    with pytest.raises(ValueError, match="target"):
        convert(graph, target="yaml")  # type: ignore[arg-type]
