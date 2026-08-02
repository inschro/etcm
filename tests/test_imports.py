import ast
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "etcm"

PUBLIC_EXPORTS = {
    "etcm": ["Resolver", "convert", "load", "resolve", "validate"],
    "etcm.cli": ["build_parser", "main"],
    "etcm.codegen": ["ViewTarget", "convert", "pydantic_schema_summary"],
    "etcm.ir": [
        "Assignment",
        "ComparisonConstraint",
        "Document",
        "Expression",
        "ExpressionKind",
        "FieldDef",
        "ImplDef",
        "LiteralValue",
        "ParameterReference",
        "RefAssignment",
        "Selector",
        "SelectorTarget",
        "SourceSpan",
        "SpecDef",
        "SpecRef",
        "TypeExpr",
    ],
    "etcm.resolve": [
        "PathExistsPolicy",
        "PathResolution",
        "ResolvedEdge",
        "ResolvedField",
        "ResolvedGraph",
        "ResolvedNode",
        "ResolvedValue",
        "Resolver",
        "ViewTarget",
        "convert",
        "load",
        "resolve",
        "validate",
    ],
    "etcm.syntax": [
        "SyntaxAssignment",
        "SyntaxComparisonConstraint",
        "SyntaxDiagnostic",
        "SyntaxDocument",
        "SyntaxExpression",
        "SyntaxField",
        "SyntaxImpl",
        "SyntaxItem",
        "SyntaxLiteral",
        "SyntaxParameterReference",
        "SyntaxRefAssignment",
        "SyntaxSpec",
        "SyntaxSpecRef",
        "SyntaxTypeExpr",
        "build_parser",
        "parse_document",
        "parse_file",
        "parse_syntax",
    ],
}


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
        for path in (PACKAGE_ROOT / "ir").glob("*.py")
    )

    assert "lark" not in ir_sources
    assert "pydantic" not in ir_sources


def test_declared_runtime_dependencies_are_available() -> None:
    assert importlib.util.find_spec("lark") is not None
    assert importlib.util.find_spec("pydantic") is not None


@pytest.mark.parametrize(("module_name", "exports"), PUBLIC_EXPORTS.items())
def test_public_exports_are_stable(module_name: str, exports: list[str]) -> None:
    module = importlib.import_module(module_name)

    assert module.__all__ == exports
    assert all(hasattr(module, name) for name in exports)


def test_package_initializers_are_declarative_facades() -> None:
    for path in PACKAGE_ROOT.rglob("__init__.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        unexpected = [
            statement
            for statement in tree.body
            if not isinstance(statement, (ast.Import, ast.ImportFrom, ast.Assign))
            and not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]

        assert unexpected == [], f"{path} contains executable package implementation"


@pytest.mark.parametrize(
    "module_order",
    [
        ("etcm.codegen", "etcm.resolve", "etcm"),
        (
            "etcm.syntax.parser",
            "etcm.resolve.graph",
            "etcm.resolve.relations",
            "etcm.cli",
        ),
        ("etcm.cli", "etcm.syntax", "etcm.codegen", "etcm"),
    ],
)
def test_supported_modules_import_in_any_order(module_order: tuple[str, ...]) -> None:
    source_root = str(PACKAGE_ROOT.parent)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (source_root, environment.get("PYTHONPATH"))
        if part is not None
    )
    code = "; ".join(f"import {module_name}" for module_name in module_order)

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
