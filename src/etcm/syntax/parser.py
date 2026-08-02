from __future__ import annotations

import ast as py_ast
from dataclasses import replace
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from lark import Lark, Token, Tree, UnexpectedInput
from lark.indenter import Indenter

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import (
    Assignment,
    ComparisonConstraint,
    Document,
    Expression,
    FieldDef,
    ImplDef,
    LiteralValue,
    ParameterReference,
    RefAssignment,
    Selector,
    SelectorTarget,
    SourceSpan,
    SpecDef,
    SpecRef,
    TypeExpr,
)
from etcm.syntax.ast import (
    SyntaxAssignment,
    SyntaxComparisonConstraint,
    SyntaxDocument,
    SyntaxExpression,
    SyntaxField,
    SyntaxImpl,
    SyntaxItem,
    SyntaxLiteral,
    SyntaxParameterReference,
    SyntaxRefAssignment,
    SyntaxSpec,
    SyntaxSpecRef,
    SyntaxTypeExpr,
)

SyntaxDiagnostic = Diagnostic


class ETCMIndenter(Indenter):
    @property
    def NL_type(self) -> str:
        return "_NL"

    @property
    def OPEN_PAREN_types(self) -> list[str]:
        return ["LPAR", "LSQB", "META_LSQB", "LBRACE"]

    @property
    def CLOSE_PAREN_types(self) -> list[str]:
        return ["RPAR", "RSQB", "RBRACE"]

    @property
    def INDENT_type(self) -> str:
        return "_INDENT"

    @property
    def DEDENT_type(self) -> str:
        return "_DEDENT"

    @property
    def tab_len(self) -> int:
        return 8


@lru_cache(maxsize=1)
def build_parser() -> Lark:
    grammar = files("etcm.syntax").joinpath("grammar.lark").read_text(encoding="utf-8")
    return Lark(
        grammar,
        parser="lalr",
        start=["start", "expression_start"],
        propagate_positions=True,
        maybe_placeholders=False,
        postlex=ETCMIndenter(),
    )


def parse_syntax(text: str, source_path: str | Path = "<string>") -> SyntaxDocument:
    source = Path(source_path)
    _reject_tab_indentation(text, source)
    try:
        tree = build_parser().parse(text, start="start")
    except UnexpectedInput as exc:
        raise ETCMError(_diagnostic_from_unexpected(exc, source)) from exc

    document = _SyntaxBuilder(source, text).document(tree)
    _validate_document(document)
    return document


def parse_document(text: str, source_path: str | Path = "<string>") -> Document:
    return _syntax_to_ir(parse_syntax(text, source_path))


def parse_file(path: str | Path) -> Document:
    source = Path(path)
    return parse_document(source.read_text(encoding="utf-8"), source)


class _SyntaxBuilder:
    def __init__(self, source_path: Path, source_text: str) -> None:
        self._source_path = source_path
        self._source_text = source_text

    def document(self, tree: Tree[Token]) -> SyntaxDocument:
        items: list[SyntaxItem] = []
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "spec":
                items.append(self.spec(child))
            elif child.data == "spec_ref":
                items.append(self.spec_ref(child))
            elif child.data == "impl":
                items.append(self.impl(child))
        return SyntaxDocument(source_path=self._source_path, items=tuple(items))

    def spec(self, tree: Tree[Token]) -> SyntaxSpec:
        name = _required_token(tree, "NAME")
        parent: str | None = None
        fields: list[SyntaxField] = []
        implementations: list[SyntaxImpl] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "spec_parent":
                parent = self._selector(
                    str(_required_token(child, "SELECTOR")),
                    child,
                    expected="spec",
                )
            elif child.data == "field":
                fields.append(self.field(child))
            elif child.data == "spec_ref_field":
                fields.append(self.spec_ref_field(child))
            elif child.data == "nested_field":
                fields.append(self.nested_field(child))
            elif child.data == "impl":
                implementations.append(self.impl(child))

        return SyntaxSpec(
            name=str(name),
            parent=parent,
            fields=tuple(fields),
            implementations=tuple(implementations),
            span=_span(tree, self._source_path),
        )

    def spec_ref(self, tree: Tree[Token]) -> SyntaxSpecRef:
        return SyntaxSpecRef(
            selector=self._selector(
                str(_required_token(tree, "SELECTOR")),
                tree,
                expected="spec",
                require_path=True,
            ),
            span=_span(tree, self._source_path),
        )

    def impl(self, tree: Tree[Token]) -> SyntaxImpl:
        name = _required_token(tree, "NAME")
        parent: str | None = None
        assignments: list[SyntaxAssignment | SyntaxRefAssignment] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "impl_parent":
                parent = self._selector(
                    str(_required_token(child, "SELECTOR")),
                    child,
                    expected="implementation",
                )
            elif child.data == "value_assignment":
                assignments.append(self.value_assignment(child))
            elif child.data == "ref_assignment":
                assignments.append(self.ref_assignment(child))

        return SyntaxImpl(
            name=str(name),
            parent=parent,
            assignments=tuple(assignments),
            span=_span(tree, self._source_path),
        )

    def field(self, tree: Tree[Token]) -> SyntaxField:
        name = _required_token(tree, "NAME")
        type_expr: SyntaxTypeExpr | None = None
        default: SyntaxLiteral | None = None
        derived: SyntaxExpression | None = None
        constraints: tuple[SyntaxComparisonConstraint, ...] = ()
        metadata: dict[str, SyntaxLiteral] = {}
        override = "allow"

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data in {"union_type", "generic_type", "named_type"}:
                type_expr = self.type_expr(child)
            elif child.data == "field_default":
                default = self.literal(_required_tree(child))
            elif child.data == "field_derived":
                derived = self.expression(_required_tree(child))
            elif child.data == "derived_block":
                derived = self.derived_block(child)
            elif child.data == "field_meta":
                meta, constraints = self.field_meta(child)
                override_literal = meta.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)
                metadata = meta

        if type_expr is None:
            raise AssertionError("field is missing type expression")

        return SyntaxField(
            name=str(name),
            type_expr=type_expr,
            default=default,
            derived=derived,
            constraints=constraints,
            metadata=metadata,
            override=override,
            span=_span(tree, self._source_path),
        )

    def spec_ref_field(self, tree: Tree[Token]) -> SyntaxField:
        name = str(_required_token(tree, "NAME"))
        ref_selector = self._selector(
            str(_required_token(tree, "SELECTOR")),
            tree,
            expected="spec",
        )
        metadata: dict[str, SyntaxLiteral] = {}
        constraints: tuple[SyntaxComparisonConstraint, ...] = ()
        override = "allow"

        for child in tree.children:
            if isinstance(child, Tree) and child.data == "field_meta":
                metadata, constraints = self.field_meta(child)
                override_literal = metadata.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)

        return SyntaxField(
            name=name,
            constraints=constraints,
            metadata=metadata,
            override=override,
            ref_selector=ref_selector,
            span=_span(tree, self._source_path),
        )

    def nested_field(self, tree: Tree[Token]) -> SyntaxField:
        name = str(_required_token(tree, "NAME"))
        metadata: dict[str, SyntaxLiteral] = {}
        constraints: tuple[SyntaxComparisonConstraint, ...] = ()
        override = "allow"
        fields: list[SyntaxField] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "field_meta":
                metadata, constraints = self.field_meta(child)
                override_literal = metadata.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)
            elif child.data == "field":
                fields.append(self.field(child))
            elif child.data == "spec_ref_field":
                fields.append(self.spec_ref_field(child))
            elif child.data == "nested_field":
                fields.append(self.nested_field(child))

        return SyntaxField(
            name=name,
            constraints=constraints,
            metadata=metadata,
            override=override,
            fields=tuple(fields),
            span=_span(tree, self._source_path),
        )

    def field_meta(
        self,
        tree: Tree[Token],
    ) -> tuple[dict[str, SyntaxLiteral], tuple[SyntaxComparisonConstraint, ...]]:
        metadata: dict[str, SyntaxLiteral] = {}
        constraints: list[SyntaxComparisonConstraint] = []
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "meta_pair":
                metadata[str(_required_token(child, "NAME"))] = self.literal(
                    _required_tree(child)
                )
            elif child.data in {
                "implicit_comparison_constraint",
                "transformed_comparison_constraint",
            }:
                constraints.append(self.comparison_constraint(child))
            elif child.data == "in_constraint":
                metadata["choices"] = self.literal(_required_tree(child))
        return metadata, tuple(constraints)

    def comparison_constraint(self, tree: Tree[Token]) -> SyntaxComparisonConstraint:
        operator = str(_required_token(tree, "COMPARE"))
        expression_trees = [child for child in tree.children if isinstance(child, Tree)]
        span = _span(tree, self._source_path)
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
            diagnostic = _diagnostic_from_unexpected(exc, self._source_path)
            error_position = getattr(exc, "pos_in_stream", None)
            if isinstance(error_position, int) and position_map:
                if error_position < len(position_map):
                    source_position = position_map[error_position]
                else:
                    source_position = position_map[-1] + 1
                error_span = _span_from_positions(
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
        expression_tree = _required_tree(parsed)
        parsed_expression = _SyntaxBuilder(self._source_path, expression_text).expression(
            expression_tree
        )
        return self._rebase_block_expression(
            parsed_expression,
            position_map=position_map,
        )

    def expression(self, tree: Tree[Token]) -> SyntaxExpression:
        span = _span(tree, self._source_path)
        raw = self._raw(tree).strip()

        if tree.data in {"sum_expr", "product_expr"}:
            return self._binary_chain(tree)

        if tree.data == "unary_expression":
            operator = str(_required_token(tree, "UNARY_OP"))
            operand = self.expression(_required_tree(tree))
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
            return replace(self.expression(_required_tree(tree)), raw=raw, span=span)

        if tree.data == "parameter_reference":
            token = _required_token(tree, "PARAM_REF")
            reference_raw = str(token)
            return SyntaxExpression(
                kind="reference",
                reference=SyntaxParameterReference(
                    parts=tuple(reference_raw[1:].split(".")),
                    raw=reference_raw,
                    span=_span(token, self._source_path),
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
                    current_span = _span_from_positions(
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
        span = _span(node, self._source_path)
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
            return _span(fallback, self._source_path)
        return _span_from_positions(
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
                return _span_from_positions(
                    self._source_text,
                    self._source_path,
                    source_position,
                    source_position,
                )
            start_pos = position_map[span.start_pos]
            end_pos = position_map[span.end_pos - 1] + 1
            return _span_from_positions(
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

    def value_assignment(self, tree: Tree[Token]) -> SyntaxAssignment:
        field_path: tuple[str, ...] | None = None
        value: SyntaxLiteral | None = None

        for child in tree.children:
            if isinstance(child, Tree) and child.data == "field_path":
                field_path = tuple(str(token) for token in _tokens(child, "NAME"))
            elif isinstance(child, Tree):
                value = self.literal(child)

        if field_path is None or value is None:
            raise AssertionError("value assignment is incomplete")

        return SyntaxAssignment(
            field_path=field_path,
            value=value,
            span=_span(tree, self._source_path),
        )

    def ref_assignment(self, tree: Tree[Token]) -> SyntaxRefAssignment:
        field_name = str(_required_token(tree, "NAME"))
        selector = self._selector(
            str(_required_token(tree, "SELECTOR")),
            tree,
            expected="implementation",
        )
        return SyntaxRefAssignment(
            field_name=field_name,
            selector=selector,
            span=_span(tree, self._source_path),
        )

    def type_expr(self, tree: Tree[Token]) -> SyntaxTypeExpr:
        if tree.data == "union_type":
            parts = [self.type_expr(child) for child in tree.children if isinstance(child, Tree)]
            if len(parts) == 1:
                return parts[0]
            return SyntaxTypeExpr(kind="union", args=tuple(parts))

        if tree.data == "generic_type":
            name = str(_required_token(tree, "NAME"))
            args = tuple(
                self.type_expr(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxTypeExpr(kind="generic", name=name, args=args)

        if tree.data == "named_type":
            return SyntaxTypeExpr(kind="named", name=str(_required_token(tree, "NAME")))

        raise AssertionError(f"unsupported type expression: {tree.data}")

    def literal(self, tree: Tree[Token]) -> SyntaxLiteral:
        span = _span(tree, self._source_path)

        if tree.data == "string":
            return SyntaxLiteral(
                kind="string",
                value=py_ast.literal_eval(str(tree.children[0])),
                span=span,
            )

        if tree.data == "number":
            raw = str(tree.children[0])
            if "." in raw or "e" in raw.lower():
                return SyntaxLiteral(kind="float", value=float(raw), span=span)
            return SyntaxLiteral(kind="int", value=int(raw), span=span)

        if tree.data == "true":
            return SyntaxLiteral(kind="bool", value=True, span=span)

        if tree.data == "false":
            return SyntaxLiteral(kind="bool", value=False, span=span)

        if tree.data == "null":
            return SyntaxLiteral(kind="null", value=None, span=span)

        if tree.data == "list_lit":
            values = tuple(
                self.literal(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxLiteral(kind="list", value=values, span=span)

        if tree.data == "map_lit":
            values = tuple(
                self.map_pair(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxLiteral(kind="map", value=values, span=span)

        raise AssertionError(f"unsupported literal: {tree.data}")

    def map_pair(self, tree: Tree[Token]) -> tuple[str, SyntaxLiteral]:
        key: str | None = None
        value: SyntaxLiteral | None = None

        for child in tree.children:
            if isinstance(child, Tree) and child.data in {"bare_key", "string_key"}:
                key = self.map_key(child)
            elif isinstance(child, Tree):
                value = self.literal(child)

        if key is None or value is None:
            raise AssertionError("map pair is incomplete")

        return (key, value)

    def map_key(self, tree: Tree[Token]) -> str:
        if tree.data == "bare_key":
            return str(_required_token(tree, "NAME"))
        if tree.data == "string_key":
            return str(py_ast.literal_eval(str(tree.children[0])))
        raise AssertionError(f"unsupported map key: {tree.data}")

    def _selector(
        self,
        raw: str,
        node: Tree[Token],
        *,
        expected: SelectorTarget,
        require_path: bool = False,
    ) -> str:
        try:
            selector = Selector.parse(raw)
            if selector.target != expected:
                required_form = (
                    "path.etcm#Spec or #Spec"
                    if expected == "spec"
                    else (
                        "path.etcm#Spec:implementation, "
                        "#Spec:implementation, or :implementation"
                    )
                )
                raise ValueError(f"expected {expected} selector ({required_form})")
            if require_path and selector.path is None:
                raise ValueError("this selector position requires a file path")
        except ValueError as exc:
            _raise(
                "E_PARSE_SELECTOR",
                f"Invalid {expected} selector '{raw}': {exc}.",
                self._source_path,
                _span(node, self._source_path),
                selector=raw,
            )
            raise AssertionError("unreachable") from exc
        return raw


def _syntax_to_ir(document: SyntaxDocument) -> Document:
    spec_ref = next((item for item in document.items if isinstance(item, SyntaxSpecRef)), None)
    implementations = tuple(
        _impl_to_ir(item) for item in document.items if isinstance(item, SyntaxImpl)
    )
    return Document(
        source_path=document.source_path,
        specs=tuple(_spec_to_ir(item) for item in document.items if isinstance(item, SyntaxSpec)),
        spec_ref=_spec_ref_to_ir(spec_ref) if spec_ref is not None else None,
        implementations=implementations,
    )


def _spec_to_ir(spec: SyntaxSpec) -> SpecDef:
    return SpecDef(
        name=spec.name,
        parent=Selector.parse(spec.parent) if spec.parent is not None else None,
        fields=tuple(_field_to_ir(field, spec.name) for field in spec.fields),
        implementations=tuple(_impl_to_ir(impl) for impl in spec.implementations),
        span=spec.span,
    )


def _spec_ref_to_ir(spec_ref: SyntaxSpecRef) -> SpecRef:
    return SpecRef(selector=Selector.parse(spec_ref.selector), span=spec_ref.span)


def _field_to_ir(field: SyntaxField, owner_name: str) -> FieldDef:
    type_expr = (
        TypeExpr(kind="named", name=_nested_type_name(owner_name, field.name))
        if field.fields
        else TypeExpr(kind="named", name="__ref__")
        if field.ref_selector is not None
        else _type_to_ir(_required_type_expr(field))
    )
    return FieldDef(
        name=field.name,
        type_expr=type_expr,
        default=_literal_to_ir(field.default) if field.default is not None else None,
        derived=_expression_to_ir(field.derived) if field.derived is not None else None,
        constraints=tuple(_constraint_to_ir(item) for item in field.constraints),
        metadata={key: _literal_to_ir(value) for key, value in field.metadata.items()},
        override=field.override,
        ref_selector=Selector.parse(field.ref_selector) if field.ref_selector is not None else None,
        fields=tuple(_field_to_ir(child, str(type_expr.name)) for child in field.fields),
        span=field.span,
    )


def _impl_to_ir(impl: SyntaxImpl) -> ImplDef:
    return ImplDef(
        name=impl.name,
        parent=Selector.parse(impl.parent) if impl.parent is not None else None,
        assignments=tuple(_assignment_to_ir(assignment) for assignment in impl.assignments),
        span=impl.span,
    )


def _assignment_to_ir(
    assignment: SyntaxAssignment | SyntaxRefAssignment,
) -> Assignment | RefAssignment:
    if isinstance(assignment, SyntaxRefAssignment):
        return RefAssignment(
            field_name=assignment.field_name,
            selector=Selector.parse(assignment.selector),
            span=assignment.span,
        )
    return Assignment(
        field_path=assignment.field_path,
        value=_literal_to_ir(assignment.value),
        span=assignment.span,
    )


def _type_to_ir(type_expr: SyntaxTypeExpr) -> TypeExpr:
    return TypeExpr(
        kind=type_expr.kind,
        name=type_expr.name,
        args=tuple(_type_to_ir(arg) for arg in type_expr.args),
    )


def _required_type_expr(field: SyntaxField) -> SyntaxTypeExpr:
    if field.type_expr is None:
        raise AssertionError(f"field '{field.name}' is missing type expression")
    return field.type_expr


def _nested_type_name(owner_name: str, field_name: str) -> str:
    return f"{owner_name}_{field_name}"


def _literal_to_ir(literal: SyntaxLiteral) -> LiteralValue:
    if literal.kind == "list":
        return LiteralValue(
            kind=literal.kind,
            value=tuple(_literal_to_ir(value) for value in literal.value),
        )
    if literal.kind == "map":
        return LiteralValue(
            kind=literal.kind,
            value=tuple((key, _literal_to_ir(value)) for key, value in literal.value),
        )
    return LiteralValue(kind=literal.kind, value=literal.value)


def _expression_to_ir(expression: SyntaxExpression) -> Expression:
    return Expression(
        kind=expression.kind,
        operator=expression.operator,
        literal=_literal_to_ir(expression.literal) if expression.literal is not None else None,
        reference=(
            ParameterReference(
                parts=expression.reference.parts,
                raw=expression.reference.raw,
                span=expression.reference.span,
            )
            if expression.reference is not None
            else None
        ),
        operands=tuple(_expression_to_ir(operand) for operand in expression.operands),
        raw=expression.raw,
        span=expression.span,
    )


def _constraint_to_ir(constraint: SyntaxComparisonConstraint) -> ComparisonConstraint:
    return ComparisonConstraint(
        left=_expression_to_ir(constraint.left),
        operator=constraint.operator,
        right=_expression_to_ir(constraint.right),
        raw=constraint.raw,
        span=constraint.span,
    )


def _validate_document(document: SyntaxDocument) -> None:
    specs = [item for item in document.items if isinstance(item, SyntaxSpec)]
    spec_refs = [item for item in document.items if isinstance(item, SyntaxSpecRef)]

    seen_specs: dict[str, SyntaxSpec] = {}
    for spec in specs:
        previous = seen_specs.get(spec.name)
        if previous is not None:
            _raise(
                "E_DUPLICATE_SPEC",
                f"Duplicate spec definition '{spec.name}'.",
                document.source_path,
                spec.span,
                details={"previous": previous.name},
            )
        seen_specs[spec.name] = spec

    if specs and any(isinstance(item, SyntaxImpl) for item in document.items):
        _raise(
            "E_DUPLICATE_IMPL",
            "Top-level implementations require top-level $spec.",
            document.source_path,
            next(item.span for item in document.items if isinstance(item, SyntaxImpl)),
        )

    if specs and spec_refs:
        second = _second_of(document.items, SyntaxSpec, SyntaxSpecRef)
        _raise(
            "E_SPEC_AND_SPEC_REF",
            "Document may define either inline spec or top-level $spec, not both.",
            document.source_path,
            second.span,
        )

    for spec in specs:
        _validate_fields(document.source_path, spec)
        _validate_impl_group(document.source_path, spec.implementations)

    _validate_implementations(document)


def _validate_fields(source_path: Path, spec: SyntaxSpec) -> None:
    _validate_field_group(source_path, spec.name, spec.fields)


def _validate_field_group(
    source_path: Path,
    owner_name: str,
    fields: tuple[SyntaxField, ...],
) -> None:
    seen: dict[str, SyntaxField] = {}
    for field in fields:
        previous = seen.get(field.name)
        if previous is not None:
            _raise(
                "E_DUPLICATE_FIELD",
                f"Duplicate field '{field.name}' in spec '{owner_name}'.",
                source_path,
                field.span,
                details={
                    "previous_line": previous.span.line if previous.span is not None else None
                },
            )
        seen[field.name] = field
        if field.fields:
            _validate_field_group(source_path, f"{owner_name}.{field.name}", field.fields)


def _validate_implementations(document: SyntaxDocument) -> None:
    if any(isinstance(item, SyntaxSpecRef) for item in document.items):
        _validate_impl_group(
            document.source_path,
            tuple(item for item in document.items if isinstance(item, SyntaxImpl)),
        )


def _validate_impl_group(source_path: Path, implementations: tuple[SyntaxImpl, ...]) -> None:
    seen: dict[str, SyntaxImpl] = {}
    for impl in implementations:
        previous = seen.get(impl.name)
        if previous is not None:
            _raise(
                "E_DUPLICATE_IMPL",
                f"Duplicate implementation '{impl.name}'.",
                source_path,
                impl.span,
                details={
                    "previous_line": previous.span.line if previous.span is not None else None
                },
            )
        seen[impl.name] = impl


def _second_of(items: tuple[SyntaxItem, ...], left: type[Any], right: type[Any]) -> Any:
    seen = False
    for item in items:
        if isinstance(item, left | right):
            if seen:
                return item
            seen = True
    raise AssertionError("expected two matching items")


def _reject_tab_indentation(text: str, source_path: Path) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for column, char in enumerate(line, start=1):
            if char == "\t":
                _raise(
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


def _diagnostic_from_unexpected(exc: UnexpectedInput, source_path: Path) -> Diagnostic:
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


def _raise(
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


def _span(node: Tree[Token] | Token, source_path: Path) -> SourceSpan:
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


def _span_from_positions(
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


def _required_token(tree: Tree[Token], token_type: str) -> Token:
    for child in tree.children:
        if isinstance(child, Token) and child.type == token_type:
            return child
    raise AssertionError(f"missing token {token_type}")


def _tokens(tree: Tree[Token], token_type: str) -> tuple[Token, ...]:
    return tuple(
        child for child in tree.children if isinstance(child, Token) and child.type == token_type
    )


def _required_tree(tree: Tree[Token]) -> Tree[Token]:
    for child in tree.children:
        if isinstance(child, Tree):
            return child
    raise AssertionError("missing child tree")
