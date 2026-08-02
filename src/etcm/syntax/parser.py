from __future__ import annotations

from pathlib import Path

from lark import UnexpectedInput

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import Document
from etcm.syntax._builder import SyntaxBuilder
from etcm.syntax._grammar import build_parser
from etcm.syntax._lowering import syntax_to_ir
from etcm.syntax._source import diagnostic_from_unexpected, reject_tab_indentation
from etcm.syntax._validation import validate_document
from etcm.syntax.ast import SyntaxDocument

SyntaxDiagnostic = Diagnostic


def parse_syntax(text: str, source_path: str | Path = "<string>") -> SyntaxDocument:
    source = Path(source_path)
    reject_tab_indentation(text, source)
    try:
        tree = build_parser().parse(text, start="start")
    except UnexpectedInput as exc:
        raise ETCMError(diagnostic_from_unexpected(exc, source)) from exc

    document = SyntaxBuilder(source, text).document(tree)
    validate_document(document)
    return document


def parse_document(text: str, source_path: str | Path = "<string>") -> Document:
    return syntax_to_ir(parse_syntax(text, source_path))


def parse_file(path: str | Path) -> Document:
    source = Path(path)
    return parse_document(source.read_text(encoding="utf-8"), source)
