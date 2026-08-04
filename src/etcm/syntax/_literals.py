from __future__ import annotations

from pathlib import Path

from lark import UnexpectedInput

from etcm.errors import ETCMError
from etcm.ir import LiteralValue
from etcm.syntax._builder import SyntaxBuilder
from etcm.syntax._grammar import build_parser
from etcm.syntax._source import diagnostic_from_unexpected, required_tree
from etcm.syntax.ast import SyntaxLiteral


def parse_literal(text: str, source_path: str | Path = "<override>") -> LiteralValue:
    source = Path(source_path)
    try:
        tree = build_parser().parse(text, start="literal_start")
    except UnexpectedInput as exc:
        raise ETCMError(diagnostic_from_unexpected(exc, source)) from exc
    literal = SyntaxBuilder(source, text).literal(required_tree(tree))
    return _literal_to_ir(literal)


def _literal_to_ir(literal: SyntaxLiteral) -> LiteralValue:
    if literal.kind == "list":
        return LiteralValue(
            kind="list",
            value=tuple(_literal_to_ir(value) for value in literal.value),
        )
    if literal.kind == "map":
        return LiteralValue(
            kind="map",
            value=tuple((key, _literal_to_ir(value)) for key, value in literal.value),
        )
    return LiteralValue(kind=literal.kind, value=literal.value)
