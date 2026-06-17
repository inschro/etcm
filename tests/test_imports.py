import importlib.util


def test_public_imports() -> None:
    from etcm import Resolver, load, resolve, validate

    assert Resolver is not None
    assert load is not None
    assert resolve is not None
    assert validate is not None


def test_ir_does_not_import_parser_or_codegen_dependencies() -> None:
    import etcm.ir

    assert etcm.ir is not None
    assert "lark" not in {name.split(".", 1)[0] for name in __import__("sys").modules}
    assert "pydantic" not in {name.split(".", 1)[0] for name in __import__("sys").modules}


def test_declared_runtime_dependencies_are_available() -> None:
    assert importlib.util.find_spec("lark") is not None
    assert importlib.util.find_spec("pydantic") is not None
