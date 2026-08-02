from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Token, Tree, UnexpectedInput

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import SourceSpan


def reject_tab_indentation(text: str, source_path: Path) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for column, char in enumerate(line, start=1):
            if char == "\t":
                raise_syntax_error(
                    "E_PARSE_TAB_INDENT",
                    "Tabs cannot be used for indentation in ETCM.",
                    source_path,
                    SourceSpan(
                        source_path=source_path,
                        line=line_number,
                        column=column,
                        end_line=line_number,
                        end_column=column + 1,
                    ),
                )
            if char != " ":
                break


def diagnostic_from_unexpected(exc: UnexpectedInput, source_path: Path) -> Diagnostic:
    expected = set(getattr(exc, "expected", []) or [])
    token = getattr(exc, "token", None)
    token_type = getattr(token, "type", None)
    code = "E_PARSE_UNEXPECTED_TOKEN"
    message = "Unexpected token while parsing ETCM."

    if token_type in {"_INDENT", "_DEDENT"} or expected.intersection({"_INDENT", "_DEDENT"}):
        code = "E_PARSE_BAD_INDENT"
        message = "Invalid indentation in ETCM document."

    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)

    return Diagnostic(
        code=code,
        message=message,
        source_path=source_path,
        line=line,
        column=column,
        end_line=line,
        end_column=column + 1 if column is not None else None,
        details={"expected": sorted(str(value) for value in expected)},
    )


def raise_syntax_error(
    code: str,
    message: str,
    source_path: Path,
    span: SourceSpan | None,
    *,
    selector: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    raise ETCMError(
        Diagnostic(
            code=code,
            message=message,
            source_path=source_path,
            line=span.line if span is not None else None,
            column=span.column if span is not None else None,
            end_line=span.end_line if span is not None else None,
            end_column=span.end_column if span is not None else None,
            selector=selector,
            details=details,
        )
    )


def source_span(node: Tree[Token] | Token, source_path: Path) -> SourceSpan:
    meta = node.meta if isinstance(node, Tree) else node
    line = int(getattr(meta, "line", 1) or 1)
    column = int(getattr(meta, "column", 1) or 1)
    end_line = int(getattr(meta, "end_line", line) or line)
    end_column = int(getattr(meta, "end_column", column) or column)
    return SourceSpan(
        source_path=source_path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        start_pos=getattr(meta, "start_pos", None),
        end_pos=getattr(meta, "end_pos", None),
    )


def span_from_positions(
    source_text: str,
    source_path: Path,
    start_pos: int,
    end_pos: int,
) -> SourceSpan:
    line = source_text.count("\n", 0, start_pos) + 1
    previous_newline = source_text.rfind("\n", 0, start_pos)
    column = start_pos - previous_newline
    end_line = source_text.count("\n", 0, end_pos) + 1
    end_previous_newline = source_text.rfind("\n", 0, end_pos)
    end_column = end_pos - end_previous_newline
    return SourceSpan(
        source_path=source_path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        start_pos=start_pos,
        end_pos=end_pos,
    )


def required_token(tree: Tree[Token], token_type: str) -> Token:
    for child in tree.children:
        if isinstance(child, Token) and child.type == token_type:
            return child
    raise AssertionError(f"missing token {token_type}")


def tokens(tree: Tree[Token], token_type: str) -> tuple[Token, ...]:
    return tuple(
        child for child in tree.children if isinstance(child, Token) and child.type == token_type
    )


def required_tree(tree: Tree[Token]) -> Tree[Token]:
    for child in tree.children:
        if isinstance(child, Tree):
            return child
    raise AssertionError("missing child tree")
