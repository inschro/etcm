from typing import Any, get_type_hints

from etcm import Resolver, convert, load
from etcm.codegen import convert as codegen_convert


def test_load_and_convert_are_dynamic_boundaries() -> None:
    assert get_type_hints(load)["return"] is Any
    assert get_type_hints(convert)["return"] is Any
    assert get_type_hints(Resolver.load)["return"] is Any
    assert get_type_hints(Resolver.convert)["return"] is Any
    assert get_type_hints(codegen_convert)["return"] is Any
