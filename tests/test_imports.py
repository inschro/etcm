import importlib.util
from pathlib import Path


def test_public_imports() -> None:
    from etcm import Resolver, convert, load, resolve, validate

    assert Resolver is not None
    assert convert is not None
    assert load is not None
    assert resolve is not None
    assert validate is not None


def test_ir_does_not_import_parser_or_codegen_dependencies() -> None:
    import etcm.ir

    assert etcm.ir is not None
    ir_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).resolve().parents[1] / "src" / "etcm" / "ir").glob("*.py")
    )

    assert "lark" not in ir_sources
    assert "pydantic" not in ir_sources


def test_declared_runtime_dependencies_are_available() -> None:
    assert importlib.util.find_spec("lark") is not None
    assert importlib.util.find_spec("pydantic") is not None
