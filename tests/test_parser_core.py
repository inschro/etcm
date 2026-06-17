from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import Assignment, Document, LiteralValue, RefAssignment, SourceSpan, TypeExpr
from etcm.syntax import (
    SyntaxDocument,
    SyntaxImpl,
    SyntaxLiteral,
    SyntaxSpec,
    SyntaxSpecRef,
    SyntaxTypeExpr,
    parse_document,
    parse_syntax,
)

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"

PARSER_VALID_FIXTURES = [
    "valid/comments_blank_lines.etcm",
    "valid/impl_inheritance.etcm",
    "valid/inline_spec.etcm",
    "valid/inline_spec_with_defaults.etcm",
    "valid/nested_literals.etcm",
    "valid/no_impl.etcm",
    "valid/spec_inheritance.etcm",
    "valid/spec_ref_impls.etcm",
]

PARSER_INVALID_FIXTURES = {
    "invalid/bad_indent.etcm": "E_PARSE_BAD_INDENT",
    "invalid/duplicate_field.etcm": "E_DUPLICATE_FIELD",
    "invalid/duplicate_impl.etcm": "E_DUPLICATE_IMPL",
    "invalid/duplicate_spec.etcm": "E_DUPLICATE_SPEC",
    "invalid/malformed_literal.etcm": "E_PARSE_UNEXPECTED_TOKEN",
    "invalid/malformed_syntax.etcm": "E_PARSE_UNEXPECTED_TOKEN",
    "invalid/path_selector_ambiguity.etcm": "E_PARSE_SELECTOR",
    "invalid/spec_inheritance_fragment.etcm": "E_PARSE_UNEXPECTED_TOKEN",
    "invalid/spec_and_spec_ref.etcm": "E_SPEC_AND_SPEC_REF",
    "invalid/spec_ref_fragment.etcm": "E_PARSE_UNEXPECTED_TOKEN",
    "invalid/tab_indent.etcm": "E_PARSE_TAB_INDENT",
}


@pytest.mark.parametrize("fixture_name", PARSER_VALID_FIXTURES)
def test_valid_fixtures_match_ast_golden(fixture_name: str) -> None:
    source = FIXTURES / fixture_name
    document = parse_syntax(source.read_text(encoding="utf-8"), fixture_name)

    assert _ast_summary(document) == _read_golden("ast", fixture_name)


@pytest.mark.parametrize("fixture_name", PARSER_VALID_FIXTURES)
def test_valid_fixtures_match_ir_golden(fixture_name: str) -> None:
    source = FIXTURES / fixture_name
    document = parse_document(source.read_text(encoding="utf-8"), fixture_name)

    assert _ir_summary(document) == _read_golden("ir", fixture_name)


@pytest.mark.parametrize(("fixture_name", "code"), PARSER_INVALID_FIXTURES.items())
def test_invalid_fixtures_match_diagnostic_golden(fixture_name: str, code: str) -> None:
    source = FIXTURES / fixture_name

    with pytest.raises(ETCMError) as raised:
        parse_document(source.read_text(encoding="utf-8"), fixture_name)

    assert raised.value.diagnostic.code == code
    assert _diagnostic_summary(raised.value.diagnostic) == _read_golden(
        "diagnostics",
        fixture_name,
    )


def test_syntax_module_does_not_import_resolver_codegen_or_pydantic() -> None:
    syntax_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT.parent / "src" / "etcm" / "syntax").glob("*.py")
    )

    assert "pydantic" not in syntax_sources
    assert "etcm.resolve" not in syntax_sources
    assert "etcm.codegen" not in syntax_sources


def _read_golden(kind: str, fixture_name: str) -> dict[str, Any]:
    golden_path = FIXTURES / "golden" / kind / f"{Path(fixture_name).stem}.json"
    return json.loads(golden_path.read_text(encoding="utf-8"))


def _ast_summary(document: SyntaxDocument) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in document.items:
        if isinstance(item, SyntaxSpec):
            items.append(
                {
                    "kind": "spec",
                    "name": item.name,
                    "parent": str(item.parent) if item.parent is not None else None,
                    "field_count": len(item.fields),
                    "span": _span_summary(item.span),
                }
            )
        elif isinstance(item, SyntaxSpecRef):
            items.append(
                {
                    "kind": "spec_ref",
                    "path": str(item.path),
                    "span": _span_summary(item.span),
                }
            )
        elif isinstance(item, SyntaxImpl):
            items.append(
                {
                    "kind": "impl",
                    "name": item.name,
                    "parent": item.parent,
                    "assignment_count": len(item.assignments),
                    "span": _span_summary(item.span),
                }
            )
    return {"source_path": str(document.source_path), "items": items}


def _ir_summary(document: Document) -> dict[str, Any]:
    return {
        "source_path": str(document.source_path),
        "spec": None
        if document.spec is None
        else {
            "name": document.spec.name,
            "parent": str(document.spec.parent) if document.spec.parent is not None else None,
            "fields": [
                {
                    "name": field.name,
                    "type": _type_summary(field.type_expr),
                    "default": _literal_summary(field.default),
                    "metadata": {
                        key: _literal_summary(value) for key, value in field.metadata.items()
                    },
                    "override": field.override,
                }
                for field in document.spec.fields
            ],
        },
        "spec_ref": None
        if document.spec_ref is None
        else {"path": str(document.spec_ref.path)},
        "implementations": [
            {
                "name": impl.name,
                "parent": impl.parent.raw if impl.parent is not None else None,
                "assignments": [_assignment_summary(assignment) for assignment in impl.assignments],
            }
            for impl in document.implementations
        ],
    }


def _assignment_summary(assignment: Assignment | RefAssignment) -> dict[str, Any]:
    if isinstance(assignment, RefAssignment):
        return {
            "kind": "ref",
            "field_name": assignment.field_name,
            "selector": assignment.selector.raw,
        }
    return {
        "kind": "literal",
        "field_path": list(assignment.field_path),
        "value": _literal_summary(assignment.value),
    }


def _type_summary(type_expr: TypeExpr | SyntaxTypeExpr) -> dict[str, Any]:
    return {
        "kind": type_expr.kind,
        "name": type_expr.name,
        "args": [_type_summary(arg) for arg in type_expr.args],
    }


def _literal_summary(literal: LiteralValue | SyntaxLiteral | None) -> dict[str, Any] | None:
    if literal is None:
        return None
    if literal.kind == "list":
        return {
            "kind": literal.kind,
            "value": [_literal_summary(value) for value in literal.value],
        }
    if literal.kind == "map":
        return {
            "kind": literal.kind,
            "value": [
                {"key": key, "value": _literal_summary(value)} for key, value in literal.value
            ],
        }
    return {"kind": literal.kind, "value": literal.value}


def _diagnostic_summary(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "source_path": str(diagnostic.source_path) if diagnostic.source_path is not None else None,
        "span": {
            "line": diagnostic.line,
            "column": diagnostic.column,
            "end_line": diagnostic.end_line,
            "end_column": diagnostic.end_column,
        },
        "selector": diagnostic.selector,
        "graph_path": diagnostic.graph_path,
        "details": dict(diagnostic.details) if diagnostic.details is not None else {},
    }


def _span_summary(span: SourceSpan | None) -> dict[str, int] | None:
    if span is None:
        return None
    return {
        "line": span.line,
        "column": span.column,
        "end_line": span.end_line,
        "end_column": span.end_column,
    }
