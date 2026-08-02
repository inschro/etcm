from __future__ import annotations

import ast as py_ast
from dataclasses import replace
from pathlib import Path
from typing import Any

from lark import Token, Tree, UnexpectedInput

from etcm.errors import ETCMError
from etcm.ir import SourceSpan
from etcm.syntax._grammar import build_parser
from etcm.syntax._source import (
    diagnostic_from_unexpected,
    required_token,
    required_tree,
    source_span,
    span_from_positions,
)
from etcm.syntax.ast import (
    SyntaxComparisonConstraint,
    SyntaxExpression,
    SyntaxLiteral,
    SyntaxParameterReference,
)


class ExpressionBuilder:
    def __init__(self, source_path: Path, source_text: str) -> None:
        self._source_path = source_path
        self._source_text = source_text

    def comparison_constraint(self, tree: Tree[Token]) -> SyntaxComparisonConstraint:
        operator = str(required_token(tree, "COMPARE"))
        expression_trees = [child for child in tree.children if isinstance(child, Tree)]
        span = source_span(tree, self._source_path)
        if tree.data == "implicit_comparison_constraint":
            if len(expression_trees) != 1:
                raise AssertionError("implicit comparison constraint is incomplete")
            left = SyntaxExpression(kind="current", span=span)
            right = self.expression(expression_trees[0])
        else:
            if len(expression_trees) != 2:
                raise AssertionError("transformed comparison constraint is incomplete")
            left = self.expression(expression_trees[0])
            right = self.expression(expression_trees[1])
        return SyntaxComparisonConstraint(
            left=left,
            operator=operator,
            right=right,
            raw=self._raw(tree).strip(),
            span=span,
        )

    def derived_block(self, tree: Tree[Token]) -> SyntaxExpression:
        line_tokens = [
            child
            for child in tree.children
            if isinstance(child, Token) and child.type == "DERIVED_LINE"
        ]
        expression_text, position_map = self._normalized_derived_expression(line_tokens)
        if not expression_text:
            raise AssertionError("derived expression block is empty")
        try:
            parsed = build_parser().parse(expression_text, start="expression_start")
        except UnexpectedInput as exc:
            diagnostic = diagnostic_from_unexpected(exc, self._source_path)
            error_position = getattr(exc, "pos_in_stream", None)
            if isinstance(error_position, int) and position_map:
                if error_position < len(position_map):
                    source_position = position_map[error_position]
                else:
                    source_position = position_map[-1] + 1
                error_span = span_from_positions(
                    self._source_text,
                    self._source_path,
                    source_position,
                    min(source_position + 1, len(self._source_text)),
                )
                diagnostic = replace(
                    diagnostic,
                    line=error_span.line,
                    column=error_span.column,
                    end_line=error_span.end_line,
                    end_column=error_span.end_column,
                )
            else:
                diagnostic = replace(
                    diagnostic,
                    line=tree.meta.line,
                    column=tree.meta.column,
                    end_line=tree.meta.end_line,
                    end_column=tree.meta.end_column,
                )
            raise ETCMError(diagnostic) from exc
        expression_tree = required_tree(parsed)
        parsed_expression = ExpressionBuilder(self._source_path, expression_text).expression(
            expression_tree
        )
        return self._rebase_block_expression(
            parsed_expression,
            position_map=position_map,
        )

    def expression(self, tree: Tree[Token]) -> SyntaxExpression:
        span = source_span(tree, self._source_path)
        raw = self._raw(tree).strip()

        if tree.data in {"sum_expr", "product_expr"}:
            return self._binary_chain(tree)

        if tree.data == "unary_expression":
            operator = str(required_token(tree, "UNARY_OP"))
            operand = self.expression(required_tree(tree))
            return SyntaxExpression(
                kind="unary",
                operator=operator,
                operands=(operand,),
                raw=raw,
                span=span,
            )

        if tree.data == "power_expr":
            expression_trees = [child for child in tree.children if isinstance(child, Tree)]
            if len(expression_trees) == 1:
                return replace(self.expression(expression_trees[0]), raw=raw, span=span)
            if len(expression_trees) != 2:
                raise AssertionError("power expression is incomplete")
            return SyntaxExpression(
                kind="binary",
                operator="**",
                operands=(
                    self.expression(expression_trees[0]),
                    self.expression(expression_trees[1]),
                ),
                raw=raw,
                span=span,
            )

        if tree.data == "grouped_expression":
            return replace(self.expression(required_tree(tree)), raw=raw, span=span)

        if tree.data == "parameter_reference":
            token = required_token(tree, "PARAM_REF")
            reference_raw = str(token)
            return SyntaxExpression(
                kind="reference",
                reference=SyntaxParameterReference(
                    parts=tuple(reference_raw[1:].split(".")),
                    raw=reference_raw,
                    span=source_span(token, self._source_path),
                ),
                raw=reference_raw,
                span=span,
            )

        literal_kind: str
        literal_value: Any
        if tree.data == "expression_string":
            literal_kind = "string"
            literal_value = py_ast.literal_eval(str(tree.children[0]))
        elif tree.data == "expression_number":
            number_raw = str(tree.children[0])
            literal_kind = "float" if "." in number_raw or "e" in number_raw.lower() else "int"
            literal_value = float(number_raw) if literal_kind == "float" else int(number_raw)
        elif tree.data == "expression_true":
            literal_kind = "bool"
            literal_value = True
        elif tree.data == "expression_false":
            literal_kind = "bool"
            literal_value = False
        elif tree.data == "expression_null":
            literal_kind = "null"
            literal_value = None
        else:
            if tree.data in {
                "continued_current_sum",
                "continued_current_product",
            }:
                return self._binary_chain(tree)
            if tree.data in {"current_sum", "current_product", "current_power"}:
                current_span = span
                if span.start_pos is not None:
                    current_span = span_from_positions(
                        self._source_text,
                        self._source_path,
                        span.start_pos,
                        span.start_pos,
                    )
                return self._binary_chain(
                    tree,
                    initial=SyntaxExpression(kind="current", span=current_span),
                )
            raise AssertionError(f"unsupported expression: {tree.data}")

        return SyntaxExpression(
            kind="literal",
            literal=SyntaxLiteral(kind=literal_kind, value=literal_value, span=span),
            raw=raw,
            span=span,
        )

    def _binary_chain(
        self,
        tree: Tree[Token],
        *,
        initial: SyntaxExpression | None = None,
    ) -> SyntaxExpression:
        children = list(tree.children)
        index = 0
        if initial is None:
            if not children or not isinstance(children[0], Tree):
                raise AssertionError("binary expression is missing its first operand")
            result = self.expression(children[0])
            index = 1
        else:
            result = initial

        while index < len(children):
            operator = children[index]
            if not isinstance(operator, Token):
                raise AssertionError("binary expression is missing an operator")
            index += 1
            if index >= len(children):
                raise AssertionError("binary expression is missing its right operand")
            right_node = children[index]
            if not isinstance(right_node, Tree):
                raise AssertionError("binary expression is missing its right operand")
            right = self.expression(right_node)
            index += 1
            span = self._expression_span(result, right, tree)
            result = SyntaxExpression(
                kind="binary",
                operator=str(operator),
                operands=(result, right),
                raw=self._raw_span(span),
                span=span,
            )
        return result

    def _raw(self, node: Tree[Token] | Token) -> str:
        span = source_span(node, self._source_path)
        return self._raw_span(span)

    def _raw_span(self, span: SourceSpan) -> str:
        if span.start_pos is None or span.end_pos is None:
            return ""
        return self._source_text[span.start_pos : span.end_pos]

    def _expression_span(
        self,
        left: SyntaxExpression,
        right: SyntaxExpression,
        fallback: Tree[Token],
    ) -> SourceSpan:
        if (
            left.span is None
            or right.span is None
            or left.span.start_pos is None
            or right.span.end_pos is None
        ):
            return source_span(fallback, self._source_path)
        return span_from_positions(
            self._source_text,
            self._source_path,
            left.span.start_pos,
            right.span.end_pos,
        )

    def _normalized_derived_expression(
        self,
        line_tokens: list[Token],
    ) -> tuple[str, tuple[int, ...]]:
        characters: list[str] = []
        positions: list[int] = []
        previous_end: int | None = None
        for token in line_tokens:
            if token.start_pos is None:
                raise AssertionError("derived expression line is missing a source position")
            raw_line = str(token)
            content = raw_line.strip()
            if not content:
                continue
            offset = raw_line.find(content)
            source_start = token.start_pos + offset
            if characters:
                characters.append(" ")
                positions.append(previous_end if previous_end is not None else source_start)
            characters.extend(content)
            positions.extend(range(source_start, source_start + len(content)))
            previous_end = source_start + len(content)
        return "".join(characters), tuple(positions)

    def _rebase_block_expression(
        self,
        expression: SyntaxExpression,
        *,
        position_map: tuple[int, ...],
    ) -> SyntaxExpression:
        def rebase_span(span: SourceSpan | None) -> SourceSpan | None:
            if span is None or span.start_pos is None or span.end_pos is None:
                return span
            if span.start_pos >= span.end_pos:
                source_position = position_map[min(span.start_pos, len(position_map) - 1)]
                return span_from_positions(
                    self._source_text,
                    self._source_path,
                    source_position,
                    source_position,
                )
            start_pos = position_map[span.start_pos]
            end_pos = position_map[span.end_pos - 1] + 1
            return span_from_positions(
                self._source_text,
                self._source_path,
                start_pos,
                end_pos,
            )

        def rebase(node: SyntaxExpression) -> SyntaxExpression:
            span = rebase_span(node.span)
            reference = node.reference
            if reference is not None:
                reference = replace(reference, span=rebase_span(reference.span))
            literal = node.literal
            if literal is not None:
                literal = replace(literal, span=rebase_span(literal.span))
            operands = tuple(rebase(operand) for operand in node.operands)
            return replace(
                node,
                literal=literal,
                reference=reference,
                operands=operands,
                raw=self._raw_span(span).strip() if span is not None else node.raw,
                span=span,
            )

        return rebase(expression)
